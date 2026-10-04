// Der Versuch "Stille-Fueller" -- und vor allem: dass er AUS ist.
//
//     node pruefstand/versuch_test.mjs
//
// Der Versuch haengt an einem Adresszusatz (?versuch=stille). Die
// eine Zusage, die zaehlt, ist die negative: ohne ihn aendert sich
// fuer einen Zuhoerer in Rostock NICHTS. Alles andere ist ein
// Messgeraet, das mitfaehrt, wenn jemand es bestellt.

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

// Der Nachbau kennt localStorage nur als leere Attrappe. Fuer diesen
// Lauf braucht es einen, der sich etwas merkt -- genau daran haengt
// die Frage, ob der Versuch einen Neuladen ueberlebt.
function laden({ suche = "", gemerkt = null } = {}) {
  const umgebung = browserBauen();
  umgebung.location.search = suche;
  const kasten = { versuch: gemerkt };
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

titel("1) Ohne Adresszusatz aendert sich NICHTS");
{
  const { Versuch, Ton, zustand } = laden();
  pruefe("der Versuch ist aus", false, Versuch.stille);
  pruefe("und merkt nichts mit", 0, Versuch.ereignisse.length);
  // Der Kern: eine leere Schlange laesst das Element stehen, wie
  // bisher. Keine Stille, kein loop, kein zweites play().
  Ton.freischalten();
  zustand.tonAn = true;
  Ton.spielt = false;
  Ton.schlange = [];
  Ton._weiter();
  pruefe("keine Stille in Schleife", false, !!Ton.stillLaeuft);
  pruefe("das Element wird nicht auf loop gestellt", undefined,
         Ton.spieler.loop);
}

titel("2) Mit ?versuch=stille ist er an");
{
  const { Versuch, kasten } = laden({ suche: "?versuch=stille" });
  pruefe("der Versuch laeuft", true, Versuch.stille);
  pruefe("und ist im Browser gemerkt", "stille", kasten.versuch);
}

titel("3) Gemerkt ueberlebt das Neuladen");
{
  const { Versuch } = laden({ gemerkt: "stille" });
  pruefe("ohne Zusatz in der Adresse weiterhin an", true, Versuch.stille);
}

titel("4) ?versuch=aus nimmt ihn wieder weg");
{
  const { Versuch, kasten } = laden({ suche: "?versuch=aus",
                                      gemerkt: "stille" });
  pruefe("der Versuch ist aus", false, Versuch.stille);
  pruefe("und nichts bleibt gemerkt", undefined, kasten.versuch);
}

titel("5) Im Versuch endet das Element nie");
{
  const { Versuch, Ton, zustand } = laden({ suche: "?versuch=stille" });
  Ton.freischalten();
  zustand.tonAn = true;
  Ton.spielt = false;
  Ton.schlange = [];
  Ton._weiter();
  pruefe("leere Schlange ergibt Stille", true, Ton.stillLaeuft);
  pruefe("und zwar in Schleife", true, Ton.spieler.loop);
  pruefe("die Stille kommt aus dem Browser, nicht vom Server", true,
         String(Ton.spieler.src).startsWith("data:audio/wav;base64,"));
  // Kommt ein Haeppchen, uebernimmt es -- ohne loop.
  Ton.einreihen("/ton/de/7", 7);
  pruefe("das Haeppchen loest die Stille ab", false, Ton.stillLaeuft);
  pruefe("und laeuft nicht in Schleife", false, Ton.spieler.loop);
  pruefe("Ereignisse werden mitgeschrieben", true,
         Versuch.ereignisse.length > 0);
}

titel("6) Nichts davon geht an den Server");
{
  const { Versuch, umgebung } = laden({ suche: "?versuch=stille" });
  Versuch.merken("probe", "x");
  const text = Versuch.ereignisse.join(" ");
  pruefe("das Protokoll steht nur auf dem Geraet", true,
         text.includes("probe"));
  // browsernachbau liefert ein fetch, das jede Anfrage ablehnt und
  // sie vorher zaehlt waere Aufwand -- hier genuegt die Quelle:
  // merken() ruft nichts auf, was nach draussen geht.
  const quelle = Versuch.merken.toString();
  pruefe("merken() ruft kein fetch", false, /fetch|XMLHttpRequest|sendBeacon/
         .test(quelle));
}

titel("7) Versuch C: der durchgehende Strom");
{
  const { Versuch, Strom, Ton, zustand } = laden({ suche: "?versuch=strom" });
  pruefe("der Stromversuch laeuft", true, Versuch.strom);
  pruefe("der Stille-Fueller nicht", false, Versuch.stille);
  zustand.sprache = "en";
  zustand.laeuft = true;
  zustand.tonAn = true;
  Strom.starten("en");
  const q = String(Strom.spieler.src);
  pruefe("eine Quelle, und zwar der Strom", true,
         q.startsWith("/strom/en.mp3?t="));
  // OHNE den Zufallsanhang nimmt der Browser beim Neustart seinen
  // Puffer und spielt Ton von vorhin.
  const q2 = Strom.url("en");
  pruefe("jeder Aufruf ergibt eine andere Quelle", true, q !== q2);
  // Haeppchen werden im Strom gar nicht erst abgerufen.
  Ton.freischalten();
  Ton.schlange = [];
  Ton.einreihen("/ton/en/7", 7);
  pruefe("Haeppchen werden ignoriert", 0, Ton.schlange.length);
}

titel("8) Nach einer Pause wird am Live-Punkt angesetzt");
{
  const { Strom, zustand } = laden({ suche: "?versuch=strom" });
  zustand.sprache = "en"; zustand.laeuft = true;
  Strom.starten("en");
  const vorher = String(Strom.spieler.src);
  Strom.pause();
  pruefe("pausiert gemerkt", true, Strom.pausiert);
  Strom.weiter();
  pruefe("nicht mehr pausiert", false, Strom.pausiert);
  pruefe("und eine NEUE Quelle, nicht der alte Puffer", true,
         String(Strom.spieler.src) !== vorher);
}

titel("9) Abstand zum Live-Punkt");
{
  const { Strom, zustand } = laden({ suche: "?versuch=strom" });
  zustand.sprache = "en"; zustand.laeuft = true;
  Strom.starten("en");
  const a = Strom.spieler;
  pruefe("ohne Puffer kein Abstand", 0, Strom.abstand());
  a.buffered = { length: 1, end: () => 12.5 };
  a.currentTime = 4.2;
  pruefe("mit Puffer: 8,3 s", "8.3", Strom.abstand().toFixed(1));
}

titel("10) Ohne Adresszusatz bleibt alles beim Alten");
{
  const { Versuch, Strom, Ton, zustand } = laden();
  pruefe("kein Stromversuch", false, Versuch.strom);
  pruefe("der Strom hat kein Element", null, Strom.spieler);
  // Haeppchen laufen wie bisher.
  Ton.freischalten();
  zustand.tonAn = true;
  Ton.schlange = [];
  Ton.spielt = true;             // damit _weiter nichts abzieht
  Ton.einreihen("/ton/de/1", 1);
  pruefe("das Haeppchen wird eingereiht", 1, Ton.schlange.length);
}

console.log("");
if (fehler) { console.log(`${fehler} FEHLER`); process.exit(1); }
console.log("\x1b[32mAlle Faelle wie erwartet.\x1b[0m");
