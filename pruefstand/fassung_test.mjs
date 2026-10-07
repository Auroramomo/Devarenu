// Alte Hoererseite nach einem Update, und verpasster Text nach einem
// Abbruch (0.5.0, Teile G1 und G2).
//
//     node pruefstand/fassung_test.mjs
//
// G1. Der Server setzt beim Ausliefern seine Fassung in die Seite ein
//     und nennt sie beim Laden (/api/sprachen) und beim Verbinden
//     (zustand). Weicht sie ab, laedt die Seite sich EINMAL neu -- mit
//     "fassung=<neu>" in der Adresse. Steht das schon da, nicht noch
//     einmal: das ist der Schutz gegen eine Endlosschleife.
//
// G2. Beim Wiederverbinden sagt die Seite, was sie zuletzt hatte
//     ("seit" und "lauf"); der Server reicht nach, was dazwischen lag.
//     Doppelte Abschnitte kommen nicht in den Strom, nachgereichte
//     bringen keinen Ton, und ein neuer Lauf (Serverneustart) setzt die
//     Zaehlung zurueck.
//
// Der Server-Teil von G2 steht in pruefstand/nachholen_test.py.
import vm from "node:vm";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { browserBauen, skriptLaden } from "./browsernachbau.mjs";

// Namen aus dem Skript der Seite holen bzw. darin etwas ausfuehren --
// "const Fassung" liegt im lexikalischen Bereich des Kontexts.
const vmHolen = (u, name) => vm.runInContext(name, u);
const vmSetzen = (u, code) => vm.runInContext(code, u);

const WURZEL = new URL("..", import.meta.url).pathname;
let fehler = 0;
function pruefe(was, erwartet, ist) {
  if (JSON.stringify(erwartet) === JSON.stringify(ist)) {
    console.log(`   ok    ${was}`);
  } else {
    fehler++;
    console.log(`   FEHLER ${was}: erwartet ${JSON.stringify(erwartet)}, `
                + `ist ${JSON.stringify(ist)}`);
  }
}
const titel = (t) => console.log(`\n\x1b[1m== ${t}\x1b[0m`);
const warten = () => new Promise((f) => setTimeout(f, 0));

// Die Seite so, wie der Server sie ausliefert: mit eingesetzter Fassung.
const roh = readFileSync(WURZEL + "client.html", "utf8");
const ordner = WURZEL + ".tmp/pruefstand";
mkdirSync(ordner, { recursive: true });
const SEITE = ordner + "/client_fassung.html";
writeFileSync(SEITE, roh.replace("<!--FASSUNG-->", "0.5.0"));

function laden(suche = "") {
  const u = browserBauen();
  const ersetzt = [];
  u.location.search = suche;
  u.location.pathname = "/";
  u.location.replace = (z) => ersetzt.push(z);
  u.history = { replaceState: (_a, _b, z) => { u.location.search =
    z.includes("?") ? z.slice(z.indexOf("?")) : ""; } };
  const p = skriptLaden(u, SEITE);
  return { u, p, ersetzt };
}

titel("1) Die Seite traegt ihre Fassung");
pruefe("client.html hat genau einen Platzhalter", 1,
       roh.split("<!--FASSUNG-->").length - 1);
const server = readFileSync(WURZEL + "server.py", "utf8");
pruefe("der Server setzt VERSION ein", true,
       server.includes('"<!--FASSUNG-->", config.VERSION'));
pruefe("und nennt sie beim Verbinden", true,
       server.includes('"fassung": config.VERSION'));

titel("2) Gleiche Fassung: nichts geschieht");
{
  const { p, ersetzt, u } = laden();
  const F = vmHolen(u, "Fassung");
  pruefe("gleich", "gleich", F.pruefen("0.5.0"));
  pruefe("kein Neuladen", [], ersetzt);
  void p;
}

titel("3) Andere Fassung: einmal neu laden");
{
  const { ersetzt, u } = laden();
  const F = vmHolen(u, "Fassung");
  vmSetzen(u, "zustand.sprache = 'ru'");
  pruefe("neu laden", "neu_laden", F.pruefen("0.5.1"));
  pruefe("mit Marke und Sprache in der Adresse", ["/?fassung=0.5.1&sprache=ru"],
         ersetzt);
}

titel("4) Schutz gegen die Schleife");
{
  // Nach dem Neuladen steht die Marke in der Adresse -- und die Seite
  // ist trotzdem alt (ein Zwischenspeicher irgendwo).
  const { ersetzt, u } = laden("?fassung=0.5.1&sprache=ru");
  const F = vmHolen(u, "Fassung");
  pruefe("schon versucht", "schon_versucht", F.pruefen("0.5.1"));
  pruefe("kein zweites Neuladen", [], ersetzt);
  // Eine NOCH neuere Fassung darf wieder einmal laden.
  pruefe("eine weitere Fassung laedt wieder einmal", "neu_laden",
         F.pruefen("0.5.2"));
}

titel("5) Angekommen: die Marke verschwindet aus der Adresse");
{
  const { u } = laden("?fassung=0.5.0&sprache=ru");
  const F = vmHolen(u, "Fassung");
  pruefe("gleich", "gleich", F.pruefen("0.5.0"));
  pruefe("fassung= ist weg, sprache= bleibt fuer die Vorwahl",
         "?sprache=ru", u.location.search);
}

titel("6) Nicht vom Server (Datei, Platzhalter): nichts tun");
{
  const u = browserBauen();
  const ersetzt = [];
  u.location.replace = (z) => ersetzt.push(z);
  skriptLaden(u, WURZEL + "client.html");
  const F = vmHolen(u, "Fassung");
  pruefe("unbekannt", "unbekannt", F.pruefen("0.5.1"));
  pruefe("kein Neuladen", [], ersetzt);
}

titel("7) Beim Wiederverbinden nach einem Serverneustart");
{
  const { u, ersetzt } = laden();
  const { Verbindung, zustand } = u.__pruef;
  zustand.sprache = "fa";
  Verbindung.verbinden("fa");
  await warten();
  const draht = u.offeneDraehte.at(-1);
  draht.liefern({ typ: "zustand", live: true, fassung: "0.5.0", lauf: "L1" });
  pruefe("gleiche Fassung: bleibt", [], ersetzt);
  draht.liefern({ typ: "zustand", live: true, fassung: "0.6.0", lauf: "L2" });
  pruefe("neue Fassung: laedt mit der Sprache neu",
         ["/?fassung=0.6.0&sprache=fa"], ersetzt);
}

titel("8) Verpasster Text: seit und lauf gehen mit");
{
  const { u } = laden();
  const { Verbindung, zustand, Ton } = u.__pruef;
  const eingereiht = [];
  Ton.einreihen = (a, id) => eingereiht.push(id);
  const strom = u.document.getElementById("strom");
  zustand.sprache = "ru";
  Verbindung.verbinden("ru");
  await warten();
  let d = u.offeneDraehte.at(-1);
  pruefe("erste Verbindung ohne seit", false, d.url.includes("seit="));
  d.liefern({ typ: "zustand", live: true, lauf: "L1" });
  for (const id of [1, 2, 3])
    d.liefern({ typ: "segment", id, text: `Satz ${id}.`, absatz_ende: true,
                audio: `/ton/ru/${id}` });
  pruefe("drei Abschnitte mit Ton", [1, 2, 3], eingereiht);
  // Funkaussetzer. Der erste Versuch kommt nach 1 bis 2 Sekunden
  // (Zufallsanteil, Verbindung._wartezeit).
  const vorher = u.offeneDraehte.length;
  d.onclose();
  await new Promise((f) => setTimeout(f, 2200));
  pruefe("es wurde neu verbunden", vorher + 1, u.offeneDraehte.length);
  d = u.offeneDraehte.at(-1);
  pruefe("beim Wiederverbinden: seit=3 und lauf=L1", true,
         d.url.includes("seit=3") && d.url.includes("lauf=L1"));
  d.liefern({ typ: "zustand", live: true, lauf: "L1" });
  // Der Server reicht 4 und 5 nach -- und, zur Probe, die 3 noch einmal.
  d.liefern({ typ: "segment", id: 3, text: "Satz 3.", absatz_ende: true,
              nachgereicht: true });
  d.liefern({ typ: "segment", id: 4, text: "Satz 4.", absatz_ende: true,
              nachgereicht: true });
  d.liefern({ typ: "segment", id: 5, text: "Satz 5.", absatz_ende: true,
              nachgereicht: true });
  d.liefern({ typ: "segment", id: 6, text: "Satz 6.", absatz_ende: true,
              audio: "/ton/ru/6" });
  const text = strom.volltext();
  pruefe("Satz 3 steht genau einmal da", 1, text.split("Satz 3.").length - 1);
  pruefe("4 und 5 sind nachgereicht da", true,
         text.includes("Satz 4.") && text.includes("Satz 5."));
  pruefe("Ton nur fuer das Neue, nicht fuers Nachgereichte", [1, 2, 3, 6],
         eingereiht);
  // Neuer Lauf: die Nummern beginnen von vorn und gelten.
  d.liefern({ typ: "zustand", live: true, lauf: "L2" });
  d.liefern({ typ: "segment", id: 1, text: "Neu eins.", absatz_ende: true });
  pruefe("nach neuem Lauf gilt Nummer 1 wieder", true,
         strom.volltext().includes("Neu eins."));
  // Gewollt getrennt: nichts nachzuholen.
  Verbindung.trennen();
  Verbindung.verbinden("ru");
  await warten();
  pruefe("nach Zurueck: wieder ohne seit", false,
         u.offeneDraehte.at(-1).url.includes("seit="));
}

console.log();
if (fehler) {
  console.log(`\x1b[31m${fehler} Fehler.\x1b[0m`);
  process.exit(1);
}
console.log("\x1b[32mAlle Faelle wie erwartet.\x1b[0m");
