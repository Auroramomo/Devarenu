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
// Das Element, das der Versuch selbst gebaut hat -- NICHT ueber
// getElementById: der Nachbau liefert fuer jede Kennung eines zurueck,
// und dann liesse sich "es gibt keines" gar nicht pruefen.
const video = (p) => p.Wach.element;
const imDokument = (u) => u.document.body.kinder
                           .filter((k) => k.tagName === "VIDEO");
// Ein echter Klick loest ALLE Horcher aus, nicht nur den ersten.
const klick = (el) => (el.horcher.click || []).forEach((f) => f());

titel("1) Ohne Adresszusatz aendert sich NICHTS");
{
  const p = laden();
  const { Versuch, Wach, umgebung } = p;
  pruefe("der Versuch ist aus", false, Versuch.wach);
  pruefe("und merkt nichts mit", 0, Versuch.ereignisse.length);
  pruefe("der Kasten bleibt versteckt", true,
         umgebung.document.getElementById("versuchkasten").hidden !== false);
  // KEIN Video im Dokument. Nicht versteckt, nicht pausiert -- gar
  // keines. Ein Zuhoerer in Rostock hat auch keinen stillen Dekoder
  // im Hintergrund.
  pruefe("kein Video gebaut", null, Wach.element);
  pruefe("und keines im Dokument", 0, imDokument(umgebung).length);
  pruefe("auch nicht in der Auszeichnung", false, QUELLE.includes("<video"));
  // Die Geste "Zuhoeren" wirft nichts an.
  Wach.starten();
  pruefe("die Geste baut auch keines", null, Wach.element);
  pruefe("und nichts laeuft", false, Wach.laeuft);
}

titel("2) Mit ?versuch=wach, und gemerkt");
{
  const p = laden({ suche: "?versuch=wach" });
  pruefe("der Versuch laeuft", true, p.Versuch.wach);
  pruefe("und ist im Browser gemerkt", "wach", p.kasten.versuch);
  pruefe("der Kasten ist da", false,
         p.umgebung.document.getElementById("versuchkasten").hidden);
  pruefe("das Protokoll hat angefangen", true, p.Versuch.ereignisse.length > 0);
  // Jetzt gibt es ein Video, und zwar genau eines im Dokument.
  pruefe("ein Video im Dokument", 1, imDokument(p.umgebung).length);
  pruefe("es gehoert dem Versuch", true, video(p) === imDokument(p.umgebung)[0]);
  pruefe("und es laeuft noch nicht", true, video(p).paused);

  const zweiter = laden({ gemerkt: { versuch: "wach" } });
  pruefe("ohne Zusatz in der Adresse weiterhin an", true, zweiter.Versuch.wach);

  const aus = laden({ suche: "?versuch=aus", gemerkt: { versuch: "wach" } });
  pruefe("?versuch=aus hebt auf", false, aus.Versuch.wach);
  pruefe("und nichts bleibt gemerkt", undefined, aus.kasten.versuch);
  pruefe("und es bleibt kein Video zurueck", 0, imDokument(aus.umgebung).length);
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
  pruefe("und das Element spielt", false, video(p).paused);
  pruefe("der Start steht im Protokoll", true,
         p.Versuch.ereignisse.some((z) => z.includes("Video startet")));

  // Zurueck zur Sprachwahl heisst: Bildschirm nicht weiter wachhalten.
  klick(p.umgebung.document.getElementById("zurueck"));
  pruefe("zurueck haelt es an", false, p.Wach.laeuft);
  pruefe("und das Element steht", true, video(p).paused);
}

titel("3b) Nicht stumm, und laut genug fuer Chromium");
{
  /* Chromium, video_wake_lock.cc, ShouldBeActive():
       bool has_volume = VideoElement().EffectiveMediaVolume() > 0;
       bool has_audio = VideoElement().HasAudio() && has_volume;
     muted oder volume 0 heisst also: keine Sperre ueber den Ton. */
  const p = laden({ suche: "?versuch=wach" });
  p.Wach.starten();
  const v = video(p);
  pruefe("das Element ist NICHT stumm", false, v.muted);
  pruefe("und die Lautstaerke ist groesser als null", true, v.volume > 0);
  pruefe("aber klein", true, v.volume <= 0.05);
  pruefe("in Schleife", true, v.loop);

  // Beide Quellen haengen daran, und beide tragen eine Tonspur.
  const quellen = v.kinder.filter((k) => k.tagName === "SOURCE");
  pruefe("zwei Quellen", 2, quellen.length);
  pruefe("webm und mp4", ["video/webm", "video/mp4"],
         quellen.map((k) => k.type));
  for (const q of quellen) {
    const [, art, b64] = q.src.match(/^data:video\/(\w+);base64,(.+)$/) || [];
    const roh = Buffer.from(b64, "base64");
    pruefe(`${art} unter 10 KB`, true, roh.length > 0 && roh.length < 10240);
    // Die Kennung der Tonspur im Behaelter. Ohne sie ist HasAudio()
    // falsch, und genau daran scheiterte der Versuch auf dem Handy.
    const text = roh.toString("latin1");
    const spur = art === "mp4" ? "mp4a" : "Opus";
    pruefe(`${art} hat eine Tonspur (${spur})`, true, text.includes(spur));
  }
}

titel("3c) Ton aus haelt das Video nicht an");
{
  // Wer nur mitliest, braucht den Bildschirm genauso.
  const p = laden({ suche: "?versuch=wach" });
  p.Wach.starten();
  pruefe("das Video laeuft", true, p.Wach.laeuft);
  klick(p.umgebung.document.getElementById("w-ton"));
  pruefe("der Ton ist aus", false, p.zustand.tonAn);
  pruefe("das Video laeuft weiter", true, p.Wach.laeuft);
  pruefe("und das Element auch", false, video(p).paused);
  // Und umgekehrt: das Video fasst den Tonschalter nicht an.
  klick(p.umgebung.document.getElementById("w-ton"));
  pruefe("der Ton laesst sich wieder einschalten", true, p.zustand.tonAn);
}

titel("3d) Das Video stoert die Bedienung nicht");
{
  const stil = QUELLE.split("<style>")[1].split("</style>")[0];
  const regel = stil.split("#wachvideo{")[1].split("}")[0];
  pruefe("keine Beruehrungen", true, /pointer-events:\s*none/.test(regel));
  // Chromium verlangt mehr als 20 Prozent des Sichtfelds
  // (kSizeThreshold) und mehr als 75 Prozent Sichtbarkeit
  // (kStrictVisibilityThreshold). inset:0 deckt beides ab.
  pruefe("fest positioniert", true, /position:\s*fixed/.test(regel));
  pruefe("ueber das ganze Sichtfeld", true, /inset:\s*0/.test(regel));
  pruefe("volle Breite und Hoehe", true,
         /width:\s*100%/.test(regel) && /height:\s*100%/.test(regel));
  // Hinter dem Inhalt: .schirm hat z-index:1.
  const z = parseInt((regel.match(/z-index:\s*(\d+)/) || [])[1], 10);
  const schirm = parseInt(
    (stil.split(".schirm{")[1].split("}")[0].match(/z-index:\s*(\d+)/)
     || [])[1], 10);
  pruefe(`z-index ${z} liegt unter dem Inhalt (${schirm})`, true, z < schirm);
  // Nicht ganz durchsichtig -- siehe Kommentar in client.html.
  const deckkraft = parseFloat((regel.match(/opacity:\s*([\d.]+)/) || [])[1]);
  pruefe("praktisch unsichtbar", true, deckkraft > 0 && deckkraft <= 0.02);

  // Und die Knoepfe reagieren weiter, obwohl das Video da ist.
  const p = laden({ suche: "?versuch=wach" });
  p.Wach.starten();
  const vorher = p.umgebung.__pruef.Dunkel.stufe;
  klick(p.umgebung.document.getElementById("w-dunkel"));
  pruefe("Abdunkeln kommt an", vorher + 1, p.umgebung.__pruef.Dunkel.stufe);
  klick(p.umgebung.document.getElementById("w-mehr"));
  pruefe("Mehr geht auf", true,
         p.umgebung.document.getElementById("mehrblatt").offen);
}

titel("4) Mit Wake Lock bleibt das Video aus");
{
  const p = laden({ suche: "?versuch=wach", wakeLock: true });
  pruefe("der Nachbau hat einen Wake Lock", true,
         "wakeLock" in p.umgebung.navigator);
  p.Wach.starten();
  pruefe("kein Video", false, p.Wach.laeuft);
  // Und es wird auch keines gebaut: ein Dekoder, der nie spielt,
  // waere reine Arbeit fuer niemanden.
  pruefe("und es wurde gar keines gebaut", false, !!video(p));
  pruefe("keines im Dokument", 0, imDokument(p.umgebung).length);
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
  video(p).pause();
  p.Wach.nachsehen();
  pruefe("beim Zurueckkommen laeuft es wieder", false, video(p).paused);
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

titel("7) Vier Sekunden, damit es transient bleibt");
{
  /* Chromium, media/base/media_content_type.cc:
       const int kMinimumContentDurationSecs = 5;
       return (duration.is_zero() ||
               duration > base::Seconds(kMinimumContentDurationSecs))
                  ? MediaContentType::kPersistent
                  : MediaContentType::kTransient;

     Ueber fuenf Sekunden waere das Video "persistent" und damit ein
     Stueck Wiedergabe wie jedes andere -- mit Audiofokus und
     Benachrichtigung. Die Schleife aendert daran nichts: duration ist
     die Laenge des MEDIUMS.

     Geprueft wird am Behaelter selbst, nicht am ffmpeg-Aufruf im
     Kommentar: der Kommentar kann altern, die Datei nicht. */
  const p = laden({ suche: "?versuch=wach" });
  p.Wach.starten();
  for (const q of video(p).kinder.filter((k) => k.tagName === "SOURCE")) {
    const [, art, b64] = q.src.match(/^data:video\/(\w+);base64,(.+)$/) || [];
    const roh = Buffer.from(b64, "base64");
    let sekunden = null;
    if (art === "mp4") {
      // mvhd: Zeiteinheit und Dauer stehen direkt hinter der Kennung.
      const i = roh.indexOf("mvhd");
      const einheit = roh.readUInt32BE(i + 16);
      sekunden = roh.readUInt32BE(i + 20) / einheit;
    } else {
      // Matroska: Duration (0x4489) als Gleitkommazahl, in
      // TimecodeScale-Einheiten -- ffmpeg schreibt Millisekunden.
      const i = roh.indexOf(Buffer.from([0x44, 0x89]));
      const laenge = roh[i + 2] & 0x0f;
      sekunden = (laenge === 4 ? roh.readFloatBE(i + 3)
                               : roh.readDoubleBE(i + 3)) / 1000;
    }
    pruefe(`${art}: ${sekunden.toFixed(2)} s, unter 5`, true,
           sekunden > 0 && sekunden < 5);
  }
}

console.log("");
if (fehler) { console.log(`${fehler} FEHLER`); process.exit(1); }
console.log("\x1b[32mAlle Faelle wie erwartet.\x1b[0m");
