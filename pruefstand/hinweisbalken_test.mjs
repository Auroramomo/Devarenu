// Der rote Balken -- und dass ein gemerkter Versuch nichts mehr tut.
//
//     node pruefstand/hinweisbalken_test.mjs
//
// Zwei Zusagen aus 0.4.4, beide negativ und beide auf einem Handy
// aufgefallen:
//
//   1. Ein Hinweis ohne Text ist nicht zu sehen. Der rote Balken mit
//      dem roten Punkt stand dauerhaft auf jedem Gerät -- client.html
//      hatte keine Regel fuer das Attribut hidden, und
//      .aufnahmehinweis{display:flex} schlug die des Browsers.
//
//   2. Die Versuche zum Ton bei gesperrtem Handy (?versuch=stille,
//      ?versuch=strom) sind fort. Wer einen davon im Browser gemerkt
//      hat, bekommt davon weder Wirkung noch Fehler.

import { readFileSync } from "node:fs";
import { browserBauen, skriptLaden } from "./browsernachbau.mjs";

const SEITE = new URL("../client.html", import.meta.url).pathname;
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

// Der Nachbau kennt localStorage nur als leere Attrappe. Hier braucht
// es einen, der sich etwas merkt -- genau daran haengt die Frage, ob
// ein alter Eintrag noch etwas anrichtet.
function laden({ suche = "", gemerkt = {} } = {}) {
  const umgebung = browserBauen();
  umgebung.location.search = suche;
  const kasten = { ...gemerkt };
  umgebung.localStorage = {
    getItem: (k) => (k in kasten ? kasten[k] : null),
    setItem: (k, w) => { kasten[k] = String(w); },
    removeItem: (k) => { delete kasten[k]; },
  };
  umgebung.btoa = (s) => Buffer.from(s, "binary").toString("base64");
  umgebung.URLSearchParams = URLSearchParams;
  const p = skriptLaden(umgebung, SEITE);
  return { ...p, umgebung, kasten };
}

titel("1) Ein Hinweis ohne Text bleibt unsichtbar");
{
  const quelle = readFileSync(SEITE, "utf8");
  const stil = quelle.split("<style>")[1].split("</style>")[0];
  pruefe("das Attribut hidden gewinnt", true,
         /\[hidden\]\{display:none !important\}/.test(stil));
  const p = laden();
  const { umgebung } = p;
  const balken = umgebung.document.getElementById("aufnahmehinweis");
  const text = umgebung.document.getElementById("aufnahmetext");
  // Einschalten OHNE Text in der Tabelle.
  const sprache = p.zustand.sprache;
  p.zustand.sprache = "de";
  const merk = p.TEXTE.de.aufnahme;
  p.TEXTE.de.aufnahme = "";
  umgebung.__pruef.aufnahmeHinweis(true);
  pruefe("ohne Text bleibt er versteckt", true, balken.hidden);
  pruefe("und es steht nichts darin", "", text.textContent);
  p.TEXTE.de.aufnahme = merk;
  umgebung.__pruef.aufnahmeHinweis(true);
  pruefe("mit Text erscheint er", false, balken.hidden);
  pruefe("und traegt ihn", merk, text.textContent);
  umgebung.__pruef.aufnahmeHinweis(false);
  pruefe("abgeschaltet ist er wieder weg", true, balken.hidden);

  // Nachtrag zu 0.5.0: Testprotokoll und Mitschrift speichern ebenfalls
  // Predigttext und stehen deshalb im selben Balken.
  umgebung.__pruef.aufnahmeHinweis(false, true);
  pruefe("Mitschrift allein: der Balken erscheint", false, balken.hidden);
  pruefe("mit dem Satz zur Mitschrift", p.TEXTE.de.mitschrift, text.textContent);
  umgebung.__pruef.aufnahmeHinweis(true);
  pruefe("Aufnahme dazu: beide Saetze, die Aufnahme zuerst",
         p.TEXTE.de.aufnahme + " " + p.TEXTE.de.mitschrift, text.textContent);
  p.zustand.sprache = "ru";
  umgebung.__pruef.aufnahmeHinweis();
  pruefe("nach dem Sprachwechsel auf Russisch",
         p.TEXTE.ru.aufnahme + " " + p.TEXTE.ru.mitschrift, text.textContent);
  umgebung.__pruef.aufnahmeHinweis(false, false);
  pruefe("beides aus: weg", true, balken.hidden);
  for (const s of ["de", "en", "ru", "fa"]) {
    pruefe(`${s} hat einen Satz zur Mitschrift`, true, !!p.TEXTE[s].mitschrift);
  }
  p.zustand.sprache = sprache;
}

titel("2) Von den Versuchen ist nichts uebrig");
{
  const quelle = readFileSync(SEITE, "utf8");
  // Der Versuchskasten als Einrichtung ist seit 0.4.5 wieder da
  // (?versuch=wach). Verboten ist, was zu DIESEN zwei Versuchen
  // gehoerte -- der Name allein genuegt dafuer nicht.
  for (const wort of ["versuch=strom", "versuch=stille", "stilleUrl",
                      "/strom/", "playbackRate", "stillLaeuft"]) {
    pruefe(`"${wort}" steht nicht mehr in der Seite`, false,
           quelle.includes(wort));
  }
  const p = laden();
  pruefe("kein Strom im Fenster", "undefined", typeof p.umgebung.Strom);
  // Das Versuchsgeruest lebt (seit 0.4.6 als ?versuch=protokoll und
  // als Kompatibilitaet fuer den Schalter), aber keiner der beiden
  // alten Versuche hat noch eine Wirkung: kein Protokoll, kein
  // Video vor der ersten Geste, der Schalter auf der Vorgabe.
  for (const alt of ["strom", "stille"]) {
    const q = laden({ gemerkt: { versuch: alt } });
    pruefe(`ein gemerktes "${alt}" zeigt kein Protokoll`, false,
           q.Versuch.protokoll);
    pruefe(`ein gemerktes "${alt}" baut kein Video`, null, q.Wach.element);
    pruefe(`ein gemerktes "${alt}" laesst den Schalter auf an`, true,
           q.Wach.an);
  }
}

titel("3) Ein gemerkter Versuch hat keine Wirkung und keinen Fehler");
{
  // Genau das, was auf dem Galaxy Z Fold 7 noch im Browser steht.
  const gemerkt = { versuch: "strom", versuch_ziel: "0.5" };
  let geplatzt = null;
  let p = null;
  try {
    p = laden({ suche: "?versuch=strom&ziel=0,5", gemerkt: gemerkt });
  } catch (e) {
    geplatzt = String(e && e.message || e);
  }
  pruefe("die Seite laedt ohne Fehler", null, geplatzt);
  pruefe("der gemerkte Eintrag bleibt unangetastet", "strom",
         p.kasten.versuch);
  // Und der Ton laeuft wie bei jedem anderen Zuhoerer: Haeppchen.
  p.Ton.freischalten();
  p.zustand.tonAn = true;
  p.Ton.schlange = [];
  p.Ton.spielt = true;             // damit _weiter nichts abzieht
  p.Ton.einreihen("/ton/de/1", 1);
  pruefe("das Haeppchen wird eingereiht", 1, p.Ton.schlange.length);
  pruefe("und kein Element steht auf loop", undefined,
         p.Ton.spieler.loop);
}

console.log("");
if (fehler) { console.log(`${fehler} FEHLER`); process.exit(1); }
console.log("\x1b[32mAlle Faelle wie erwartet.\x1b[0m");
