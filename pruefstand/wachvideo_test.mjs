// Der Versuch "Bildschirm wach ohne HTTPS" -- und vor allem: dass er
// AUS ist.
//
//     node pruefstand/wachvideo_test.mjs
//
// Der Versuch haengt an einem Adresszusatz (?versuch=wach). Die eine
// Zusage, die zaehlt, ist die negative: ohne ihn aendert sich fuer
// einen Zuhoerer in Rostock NICHTS.

import { readFileSync } from "node:fs";
import { browserBauen, skriptLaden } from "./browsernachbau.mjs";

const SEITE = new URL("../client.html", import.meta.url).pathname;
const QUELLE = readFileSync(SEITE, "utf8");
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
// es einen, der sich etwas merkt -- daran haengt, ob der Versuch ein
// Neuladen ueberlebt.
function laden({ suche = "", gemerkt = {}, wakeLock = false } = {}) {
  const umgebung = browserBauen();
  umgebung.location.search = suche;
  const kasten = { ...gemerkt };
  umgebung.localStorage = {
    getItem: (k) => (k in kasten ? kasten[k] : null),
    setItem: (k, w) => { kasten[k] = String(w); },
    removeItem: (k) => { delete kasten[k]; },
  };
  umgebung.URLSearchParams = URLSearchParams;
  // Der sichere Kontext, den es im Saal nicht gibt. Nur wo der Test
  // ihn ausdruecklich bestellt.
  if (wakeLock) {
    umgebung.navigator.wakeLock = {
      request: () => Promise.resolve({ addEventListener() {}, release() {} }),
    };
  }
  const p = skriptLaden(umgebung, SEITE);
  return { ...p, umgebung, kasten };
}
const video = (u) => u.document.getElementById("wachvideo");

titel("1) Ohne Adresszusatz aendert sich NICHTS");
{
  const { Versuch, Wach, umgebung } = laden();
  pruefe("der Versuch ist aus", false, Versuch.wach);
  pruefe("und merkt nichts mit", 0, Versuch.ereignisse.length);
  pruefe("der Kasten bleibt versteckt", true,
         umgebung.document.getElementById("versuchkasten").hidden !== false);
  // Die Geste "Zuhoeren" wirft nichts an.
  Wach.starten();
  pruefe("kein Video", false, Wach.laeuft);
  pruefe("und es laeuft auch keines", true, video(umgebung).paused);
}

titel("2) Mit ?versuch=wach, und gemerkt");
{
  const p = laden({ suche: "?versuch=wach" });
  pruefe("der Versuch laeuft", true, p.Versuch.wach);
  pruefe("und ist im Browser gemerkt", "wach", p.kasten.versuch);
  pruefe("der Kasten ist da", false,
         p.umgebung.document.getElementById("versuchkasten").hidden);
  pruefe("das Protokoll hat angefangen", true, p.Versuch.ereignisse.length > 0);

  const zweiter = laden({ gemerkt: { versuch: "wach" } });
  pruefe("ohne Zusatz in der Adresse weiterhin an", true, zweiter.Versuch.wach);

  const aus = laden({ suche: "?versuch=aus", gemerkt: { versuch: "wach" } });
  pruefe("?versuch=aus hebt auf", false, aus.Versuch.wach);
  pruefe("und nichts bleibt gemerkt", undefined, aus.kasten.versuch);
}

titel("3) Ohne Wake Lock laeuft das Video");
{
  // Genau der Fall im Saal: http://10.0.0.1, kein sicherer Kontext,
  // "wakeLock" in navigator ist falsch.
  const p = laden({ suche: "?versuch=wach" });
  pruefe("der Nachbau hat keinen Wake Lock", false,
         "wakeLock" in p.umgebung.navigator);
  p.Wach.starten();
  pruefe("das Video laeuft", true, p.Wach.laeuft);
  pruefe("und das Element spielt", false, video(p.umgebung).paused);
  pruefe("der Start steht im Protokoll", true,
         p.Versuch.ereignisse.some((z) => z.includes("Video startet")));

  // Zurueck zur Sprachwahl heisst: Bildschirm nicht weiter wachhalten.
  p.umgebung.document.getElementById("zurueck").horcher.click[0]();
  pruefe("zurueck haelt es an", false, p.Wach.laeuft);
  pruefe("und das Element steht", true, video(p.umgebung).paused);
}

titel("4) Mit Wake Lock bleibt das Video aus");
{
  const p = laden({ suche: "?versuch=wach", wakeLock: true });
  pruefe("der Nachbau hat einen Wake Lock", true,
         "wakeLock" in p.umgebung.navigator);
  p.Wach.starten();
  pruefe("kein Video", false, p.Wach.laeuft);
  pruefe("und das Element steht", true, video(p.umgebung).paused);
  pruefe("das Protokoll sagt, warum", true,
         p.Versuch.ereignisse.some((z) => z.includes("Vorrang")));
  // Lehnt der Wake Lock ab (Akkusparmodus), kommt das Video doch.
  p.Wach.nachreichen();
  pruefe("abgelehnt: dann doch das Video", true, p.Wach.laeuft);
  pruefe("und das steht auch da", true,
         p.Versuch.ereignisse.some((z) => z.includes("abgelehnt")));
}

titel("5) Das Video stand im Hintergrund");
{
  const p = laden({ suche: "?versuch=wach" });
  p.Wach.starten();
  // Der Browser haelt es an, wenn die Seite in den Hintergrund geht.
  video(p.umgebung).pause();
  p.Wach.nachsehen();
  pruefe("beim Zurueckkommen laeuft es wieder", false,
         video(p.umgebung).paused);
  pruefe("und es steht im Protokoll", true,
         p.Versuch.ereignisse.some((z) => z.includes("Video stand")));
}

titel("6) Das Protokoll bleibt auf dem Geraet");
{
  const p = laden({ suche: "?versuch=wach" });
  p.Wach.starten();
  // Die Seite hat keinen fetch im Pruefstand; dass merken() keinen
  // benutzt, wird an der Quelle gelesen -- ein Aufruf waere ein
  // Datenleck, kein Fehler, der von selbst auffaellt.
  const koerper = QUELLE.split("merken(was, mehr){")[1].split("\n  },")[0];
  pruefe("merken() ruft kein fetch", false,
         /fetch|XMLHttpRequest|sendBeacon/.test(koerper));
  pruefe("Ereignisse werden gesammelt", true, p.Versuch.ereignisse.length > 1);
  // Und der Kasten laeuft nicht voll.
  for (let i = 0; i < 150; i++) p.Versuch.merken("probe", String(i));
  pruefe("hoechstens hundert Zeilen", 100, p.Versuch.ereignisse.length);
}

titel("7) Das Video selbst");
{
  const roh = QUELLE.split('<video id="wachvideo"')[1].split("</video>")[0];
  for (const eig of ["muted", "loop", "playsinline"]) {
    pruefe(`das Element ist ${eig}`, true, roh.includes(eig));
  }
  pruefe("und nicht display:none",
         false, /display:\s*none/.test(QUELLE.split("#wachvideo{")[1]
                                             .split("}")[0]));
  // Zwei Formate, beide als data-URI: kein neuer Pfad, den ein Update
  // von 0.3.7 aus mitbringen muesste.
  const daten = [...roh.matchAll(/src="data:video\/(\w+);base64,([^"]+)"/g)];
  pruefe("zwei Formate", 2, daten.length);
  pruefe("webm und mp4", ["webm", "mp4"], daten.map((d) => d[1]));
  for (const [, art, b64] of daten) {
    const b = Buffer.from(b64, "base64");
    pruefe(`${art} unter 10 KB`, true, b.length > 0 && b.length < 10240);
    // Keine Tonspur: die Kennungen, die ein Audiostrom hinterlaesst,
    // kommen in diesen Dateien nicht vor.
    const text = b.toString("latin1");
    for (const spur of ["mp4a", "Opus", "Vorbis"]) {
      pruefe(`${art} ohne ${spur}`, false, text.includes(spur));
    }
  }
}

console.log("");
if (fehler) { console.log(`${fehler} FEHLER`); process.exit(1); }
console.log("\x1b[32mAlle Faelle wie erwartet.\x1b[0m");
