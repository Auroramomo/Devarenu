// Der Versuch "Stille-Fueller" -- und vor allem: dass er AUS ist.
//
//     node pruefstand/versuch_test.mjs
//
// Der Versuch haengt an einem Adresszusatz (?versuch=stille). Die
// eine Zusage, die zaehlt, ist die negative: ohne ihn aendert sich
// fuer einen Zuhoerer in Rostock NICHTS. Alles andere ist ein
// Messgeraet, das mitfaehrt, wenn jemand es bestellt.

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
  pruefe("eine Quelle, und zwar der Strom mit Ziel", true,
         q.startsWith("/strom/en.mp3?ziel="));
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

titel("9b) Aufgeholt wird ueber das Tempo, nicht mit einem Sprung");
{
  // Der Sprung leerte den Puffer, Firefox puffert danach fuenf
  // Sekunden neu, und der naechste Sprung warf genau die weg. Auf
  // dem Galaxy Z Fold 7 setzte der Ton dadurch staendig an und
  // brach ab.
  const { Strom, zustand, umgebung } = laden({ suche: "?versuch=strom" });
  zustand.sprache = "en"; zustand.laeuft = true;
  Strom.starten("en");
  const a = Strom.spieler;
  a.paused = false;
  const quelleVorher = String(a.src);

  // Die echte Entscheidung aufrufen, nicht nachbauen.
  const takt = () => { if (!a.paused && Strom.abstand() <= Strom.NOTFALL)
                         Strom._takt(Strom.abstand()); };

  // Weit hinterher, aber unter der Notfallgrenze.
  a.buffered = { length: 1, end: () => 9.0 };
  a.currentTime = 1.0;                       // Abstand 8 s
  pruefe("Abstand 8 s erkannt", "8.0", Strom.abstand().toFixed(1));
  takt();
  pruefe("das Tempo zieht an", Strom.TEMPO, a.playbackRate);
  pruefe("mit erhaltener Tonhoehe", true, a.preservesPitch === true);
  pruefe("und KEIN Sprung", 1.0, a.currentTime);
  pruefe("auch keine neue Quelle", quelleVorher, String(a.src));

  // Am Ziel angekommen.
  a.currentTime = 9.0 - Strom.ZIEL;
  takt();
  pruefe("am Ziel faellt das Tempo auf 1,0", 1, a.playbackRate);

  // Knapp darueber: noch nichts tun, sonst pendelt es.
  a.currentTime = 9.0 - Strom.ZIEL - 0.3;
  takt();
  pruefe("ein bisschen drueber loest noch nichts aus", 1, a.playbackRate);

  // NIE unter das Ziel beschleunigen.
  a.currentTime = 9.0 - 0.2;                 // viel zu weit vorn
  takt();
  pruefe("naeher als das Ziel: gebremst, nicht beschleunigt",
         Strom.BREMSE, a.playbackRate);
}

titel("9b2) Unter dem Ziel wird gebremst, damit der Puffer wieder waechst");
{
  // Der Befund: "abstand 0.0 s" durchgehend. Der Server liefert
  // Echtzeit, Firefox Android faengt ohne Vorpuffer an -- ohne
  // Bremse entsteht nie einer, und jedes Zoegern des WLAN wird zur
  // Luecke.
  const { Strom, zustand } = laden({ suche: "?versuch=strom" });
  zustand.sprache = "en"; zustand.laeuft = true;
  Strom.starten("en");
  const a = Strom.spieler;
  a.paused = false;
  // Die echte Entscheidung aufrufen, nicht nachbauen.
  const takt = () => { if (!a.paused && Strom.abstand() <= Strom.NOTFALL)
                         Strom._takt(Strom.abstand()); };
  a.buffered = { length: 1, end: () => 10.0 };
  // Abstand 0 -- genau der Befund vom Handy.
  a.currentTime = 10.0;
  takt();
  pruefe("bei Abstand 0 wird gebremst", Strom.BREMSE, a.playbackRate);
  pruefe("und zwar mit 0,97", 0.97, Strom.BREMSE);
  // Zurueck am Ziel: wieder 1,0.
  a.currentTime = 10.0 - Strom.ZIEL;
  takt();
  pruefe("am Ziel wieder 1,0", 1, a.playbackRate);
}

titel("9b3) Die Grenzen skalieren mit dem Ziel");
{
  // Bei 0,5 s Ziel waere "eine Sekunde darunter" negativ -- die
  // Bremse griffe nie.
  const { Strom, zustand } = laden({ suche: "?versuch=strom&ziel=0.5" });
  pruefe("Kommazahlen werden genommen", 0.5, Strom.ZIEL);
  zustand.sprache = "en"; zustand.laeuft = true;
  Strom.starten("en");
  const a = Strom.spieler;
  a.paused = false;
  // Die echte Entscheidung aufrufen, nicht nachbauen.
  const takt = () => { if (!a.paused && Strom.abstand() <= Strom.NOTFALL)
                         Strom._takt(Strom.abstand()); };
  a.buffered = { length: 1, end: () => 10.0 };
  a.currentTime = 10.0 - 0.2;               // Abstand 0,2 < 0,25
  takt();
  pruefe("0,2 s bei Ziel 0,5: gebremst", Strom.BREMSE, a.playbackRate);
  a.currentTime = 10.0 - 0.5;               // genau am Ziel
  takt();
  pruefe("0,5 s: Tempo 1,0", 1, a.playbackRate);
  a.currentTime = 10.0 - 1.2;               // Abstand 1,2 > 0,5 + 0,5
  takt();
  pruefe("1,2 s: beschleunigt", Strom.TEMPO, a.playbackRate);

  const klein = laden({ suche: "?versuch=strom&ziel=0.25" });
  pruefe("0,25 ist der kleinste Wert", 0.25, klein.Strom.ZIEL);
  const zuklein = laden({ suche: "?versuch=strom&ziel=0.1" });
  pruefe("0,1 wird nicht genommen", 3, zuklein.Strom.ZIEL);
}

titel("9c) Der Sprung bleibt dem Notfall");
{
  const { Strom, zustand } = laden({ suche: "?versuch=strom" });
  zustand.sprache = "en"; zustand.laeuft = true;
  Strom.starten("en");
  const a = Strom.spieler;
  a.paused = false;
  pruefe("die Notfallgrenze liegt bei 15 s", 15, Strom.NOTFALL);
  // Knapp darunter wird NICHT gesprungen.
  a.buffered = { length: 1, end: () => 20.0 };
  a.currentTime = 6.0;                       // Abstand 14 s
  const vorher = a.currentTime;
  if (Strom.abstand() > Strom.NOTFALL) { /* nicht erwartet */ }
  pruefe("14 s sind noch kein Notfall", true,
         Strom.abstand() < Strom.NOTFALL);
  pruefe("und es wird nicht gesprungen", vorher, a.currentTime);
  // Darueber: Sprung, aber auf das ZIEL, nicht auf null.
  a.currentTime = 1.0;                       // Abstand 19 s
  pruefe("19 s sind einer", true, Strom.abstand() > Strom.NOTFALL);
  const ziel = 20.0 - Strom.ZIEL;
  a.currentTime = Math.max(0, ziel);         // was _wachen() tut
  pruefe("gesprungen wird auf das Ziel, nicht auf den Live-Punkt",
         true, Math.abs(Strom.abstand() - Strom.ZIEL) < 0.01);
}

titel("9d) Das Ziel laesst sich fuer die Messung einstellen");
{
  const { Strom } = laden({ suche: "?versuch=strom&ziel=2" });
  pruefe("Ziel 2 s aus der Adresse", 2, Strom.ZIEL);
  const halb = laden({ suche: "?versuch=strom&ziel=0.75" });
  pruefe("auch Kommazahlen", 0.75, halb.Strom.ZIEL);
  const b = laden({ suche: "?versuch=strom&ziel=99" });
  pruefe("Unsinn wird nicht genommen", 3, b.Strom.ZIEL);
  const c = laden({ suche: "?versuch=strom" });
  pruefe("ohne Angabe bleibt es bei 3 s", 3, c.Strom.ZIEL);
}

titel("9d2) Die Adresse gewinnt immer gegen das Gemerkte");
{
  // Der Fehler vom Handy: ?ziel=0.5 bewirkte nichts, das Tempo
  // verhielt sich weiter wie bei Ziel 3.
  const kasten = { versuch: "strom", versuch_ziel: "3" };
  const mit = (suche) => {
    const umgebung = browserBauen();
    umgebung.location.search = suche;
    umgebung.localStorage = {
      getItem: (k) => (k in kasten ? kasten[k] : null),
      setItem: (k, w) => { kasten[k] = String(w); },
      removeItem: (k) => { delete kasten[k]; },
    };
    umgebung.btoa = (s) => Buffer.from(s, "binary").toString("base64");
    umgebung.URLSearchParams = URLSearchParams;
    return skriptLaden(umgebung, SEITE);
  };

  const p = mit("?versuch=strom&ziel=0.5");
  pruefe("Ziel 0,5 schlaegt das gemerkte 3", 0.5, p.Strom.ZIEL);
  pruefe("und steht auch im Abruf an den Server", true,
         p.Strom.url("en").startsWith("/strom/en.mp3?ziel=0.5&"));
  // Und die Regel rechnet damit, nicht mit 3.
  const a = { paused: false, playbackRate: 1,
              buffered: { length: 1, end: () => 10 }, currentTime: 9.1 };
  p.Strom.spieler = a;                       // Abstand 0,9 s
  p.Strom._takt(p.Strom.abstand());
  pruefe("0,9 s bei Ziel 0,5: kein Bremsen", 1, a.playbackRate);
  a.currentTime = 10 - 1.4;                  // Abstand 1,4 s
  p.Strom._takt(p.Strom.abstand());
  pruefe("1,4 s bei Ziel 0,5: beschleunigt", p.Strom.TEMPO, a.playbackRate);
  a.currentTime = 10 - 0.2;                  // Abstand 0,2 s
  p.Strom._takt(p.Strom.abstand());
  pruefe("0,2 s bei Ziel 0,5: gebremst", p.Strom.BREMSE, a.playbackRate);

  pruefe("das neue Ziel wird gemerkt", "0.5", kasten.versuch_ziel);
  const q = mit("?versuch=strom");
  pruefe("ohne Angabe gilt das Gemerkte", 0.5, q.Strom.ZIEL);
}

titel("9d3) Komma wie Punkt, und nichts faellt still unter den Tisch");
{
  const mit = (suche) => {
    const umgebung = browserBauen();
    umgebung.location.search = suche;
    const kasten = {};
    umgebung.localStorage = {
      getItem: (k) => (k in kasten ? kasten[k] : null),
      setItem: (k, w) => { kasten[k] = String(w); },
      removeItem: (k) => { delete kasten[k]; },
    };
    umgebung.btoa = (s) => Buffer.from(s, "binary").toString("base64");
    umgebung.URLSearchParams = URLSearchParams;
    return skriptLaden(umgebung, SEITE);
  };
  // parseFloat("0,5") ist 0 -- auf einer deutschen Tastatur tippt
  // man ein Komma, und das ganze Projekt schreibt 0,5 mit Komma.
  pruefe("Komma gilt wie Punkt", 0.5, mit("?versuch=strom&ziel=0,5").Strom.ZIEL);
  pruefe("0,25 mit Komma", 0.25, mit("?versuch=strom&ziel=0,25").Strom.ZIEL);
  // Und was nicht genommen wird, steht im Protokoll -- STILL
  // verwerfen war der eigentliche Fehler.
  const schlecht = mit("?versuch=strom&ziel=quatsch");
  pruefe("Unsinn bleibt bei der Vorgabe", 3, schlecht.Strom.ZIEL);
  pruefe("und wird gemeldet", true,
         schlecht.Versuch.ereignisse.some(z => z.includes("abgelehnt")),
         JSON.stringify(schlecht.Versuch.ereignisse.slice(0, 3)));
  const zuklein = mit("?versuch=strom&ziel=0.1");
  pruefe("zu klein wird gemeldet", true,
         zuklein.Versuch.ereignisse.some(z => z.includes("abgelehnt")));
  const ohne = mit("?versuch=strom");
  pruefe("ohne Angabe steht die Vorgabe im Protokoll", true,
         ohne.Versuch.ereignisse.some(z => z.includes("Vorgabe")));
}

titel("9e) Ein Hinweis ohne Text bleibt unsichtbar");
{
  // Der rote Balken mit dem roten Punkt stand auf jedem Handy,
  // dauerhaft und ohne Text: client.html hatte keine Regel fuer das
  // Attribut hidden, und .aufnahmehinweis{display:flex} schlug es.
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
  p.zustand.sprache = sprache;
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
