// "Bildschirm anlassen" -- seit 0.4.6 der Normalfall.
//
//     node pruefstand/wachvideo_test.mjs
//
// Bis 0.4.5 war es ein Versuch hinter ?versuch=wach. Jetzt gilt:
//
//   * Ohne Zusatz in der Adresse ist der Wach-Weg an und startet in
//     der ERSTEN Geste -- nicht erst bei "Zuhoeren". Wer nur mitliest,
//     braucht den Bildschirm genauso.
//   * Erst der echte Wake Lock; fehlt er, lehnt er ab oder geht er
//     verloren, das Video mit stiller Tonspur.
//   * Ein Schalter unter "Mehr", gemerkt. Aus heisst: kein Wake Lock,
//     kein Video im Dokument.
//   * ?versuch=wach und ?versuch=aus setzen den Schalter.
//   * Das Protokollkaestchen nur mit ?versuch=protokoll.

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
// es einen, der sich etwas merkt -- daran haengt, ob der Schalter ein
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
  //
  //   wakeLock: true        jede Anforderung gelingt
  //   wakeLock: "ablehnen"  jede Anforderung scheitert (Akkusparmodus)
  //   wakeLock: [true, false, ...]  der Reihe nach
  //
  // Jede erteilte Sperre landet in sperren[]; der Test kann sie
  // verlieren lassen und sehen, ob sie freigegeben wurde.
  const sperren = [];
  if (wakeLock) {
    const plan = Array.isArray(wakeLock) ? [...wakeLock] : null;
    umgebung.navigator.wakeLock = {
      request: () => {
        const ja = plan ? plan.shift() !== false : wakeLock !== "ablehnen";
        if (!ja) {
          const e = new Error("abgelehnt");
          e.name = "NotAllowedError";
          return Promise.reject(e);
        }
        const s = {
          frei: false,
          horcher: [],
          addEventListener(n, f) { if (n === "release") this.horcher.push(f); },
          release() { this.frei = true; this.horcher.forEach((f) => f()); },
        };
        sperren.push(s);
        return Promise.resolve(s);
      },
    };
  }
  const p = skriptLaden(umgebung, SEITE);
  return { ...p, umgebung, kasten, sperren };
}
// Ein paar Takte warten: Wake-Lock-Anfragen, "Zuhoeren" und der
// visibilitychange-Horcher sind async.
const takte = () => new Promise((r) => setTimeout(r, 20));
// Eine Geste irgendwo auf der Seite -- so, wie der Browser sie dem
// Dokument im Einfang meldet. Etwa der Tipp auf eine Sprachkachel.
async function geste(p, art = "click") {
  for (const f of p.umgebung.document.horcher[art] || []) f();
  await takte();
}
async function zuhoeren(p) {
  p.zustand.sprache = "de";
  await geste(p);           // der Klick erreicht zuerst das Dokument
  (p.umgebung.document.getElementById("starten").horcher.click || [])
    .forEach((f) => f());
  await takte();
}
async function sichtbarkeit(p, wert) {
  p.umgebung.document.visibilityState = wert;
  p.umgebung.document.hidden = wert !== "visible";
  for (const f of p.umgebung.document.horcher.visibilitychange || []) f();
  await takte();
}
// Das Element, das Wach selbst gebaut hat -- NICHT ueber
// getElementById: der Nachbau liefert fuer jede Kennung eines zurueck,
// und dann liesse sich "es gibt keines" gar nicht pruefen.
const video = (p) => p.Wach.element;
const imDokument = (u) => u.document.body.kinder
                           .filter((k) => k.tagName === "VIDEO");
// Ein echter Klick loest ALLE Horcher aus, nicht nur den ersten.
const klick = (el) => (el.horcher.click || []).forEach((f) => f());
const schalter = (p) => p.umgebung.document.getElementById("w-wach");
async function schalterDruecken(p) {
  await geste(p);
  klick(schalter(p));
  await takte();
}

titel("1) Ohne Zusatz: an, und zwar ab der ersten Geste");
{
  const p = laden();
  pruefe("der Schalter steht auf an", true, p.Wach.an);
  pruefe("und zeigt es", "true", schalter(p).getAttribute("aria-pressed"));
  // Vor jeder Geste laeuft nichts -- ohne Geste duerfte es auch nicht.
  pruefe("vor der Geste kein Video", null, video(p));
  pruefe("und keines im Dokument", 0, imDokument(p.umgebung).length);
  pruefe("auch nicht in der Auszeichnung", false, QUELLE.includes("<video"));
  // Die erste Geste ist hier der Tipp auf eine Sprachkachel -- noch
  // lange nicht "Zuhoeren".
  await geste(p);
  pruefe("nach der ersten Geste laeuft das Video", true, p.Wach.laeuft);
  pruefe("genau eines im Dokument", 1, imDokument(p.umgebung).length);
  pruefe("und es spielt", false, video(p).paused);
  pruefe("ohne dass jemand Zuhoeren gedrueckt hat", false, p.zustand.laeuft);
}

titel("1b) Auch ein Tastendruck oder ein Fingertipp zaehlt");
{
  for (const art of ["touchend", "keydown"]) {
    const p = laden();
    await geste(p, art);
    pruefe(`${art} startet`, true, p.Wach.laeuft);
  }
}

titel("2) Der Schalter aus");
{
  const p = laden();
  await geste(p);
  pruefe("vorher laeuft es", true, p.Wach.laeuft);
  await schalterDruecken(p);
  pruefe("der Schalter steht auf aus", false, p.Wach.an);
  pruefe("und zeigt es", "false", schalter(p).getAttribute("aria-pressed"));
  pruefe("nichts laeuft", false, p.Wach.laeuft);
  pruefe("das Video ist aus dem Dokument", 0, imDokument(p.umgebung).length);
  pruefe("und Wach haelt keines mehr", null, video(p));
  pruefe("gemerkt wird \"aus\"", "aus", p.kasten.bildschirm);
  // Weitere Gesten wecken nichts mehr.
  await geste(p);
  pruefe("eine weitere Geste startet nichts", 0, imDokument(p.umgebung).length);

  // Neu geladen: weiterhin aus.
  const q = laden({ gemerkt: { bildschirm: "aus" } });
  pruefe("nach dem Neuladen aus", false, q.Wach.an);
  await geste(q);
  pruefe("und auch nach einer Geste kein Video", 0,
         imDokument(q.umgebung).length);

  // Wieder an: der Druck auf den Schalter IST eine Geste.
  await schalterDruecken(q);
  pruefe("wieder an", true, q.Wach.an);
  pruefe("und es laeuft sofort", true, q.Wach.laeuft);
  pruefe("gemerkt wird \"an\"", "an", q.kasten.bildschirm);
}

titel("2b) Schalter aus gibt einen gehaltenen Wake Lock frei");
{
  const p = laden({ wakeLock: true });
  await geste(p);
  pruefe("die Sperre ist erteilt", 1, p.sperren.length);
  pruefe("und gehalten", false, p.sperren[0].frei);
  await schalterDruecken(p);
  pruefe("nach dem Ausschalten freigegeben", true, p.sperren[0].frei);
  // Die Freigabe darf NICHT das Ersatzvideo ausloesen.
  pruefe("und kein Ersatzvideo", 0, imDokument(p.umgebung).length);
  await geste(p);
  pruefe("keine neue Anforderung", 1, p.sperren.length);

  // Ist der Schalter schon beim Laden aus, wird gar nicht erst gefragt.
  const q = laden({ wakeLock: true, gemerkt: { bildschirm: "aus" } });
  await zuhoeren(q);
  pruefe("aus: Zuhoeren fordert keinen Wake Lock an", 0, q.sperren.length);
}

titel("3) ?versuch=aus und ?versuch=wach setzen den Schalter");
{
  const aus = laden({ suche: "?versuch=aus" });
  pruefe("?versuch=aus stellt aus", false, aus.Wach.an);
  pruefe("und merkt es", "aus", aus.kasten.bildschirm);
  await geste(aus);
  pruefe("wirkt wie der Schalter: kein Video", 0,
         imDokument(aus.umgebung).length);

  const wach = laden({ suche: "?versuch=wach",
                       gemerkt: { bildschirm: "aus" } });
  pruefe("?versuch=wach stellt wieder an", true, wach.Wach.an);
  pruefe("und merkt es", "an", wach.kasten.bildschirm);
  // Nicht schon beim Laden: das braucht eine Geste.
  pruefe("vor der Geste trotzdem kein Video", 0,
         imDokument(wach.umgebung).length);

  for (const suche of ["?versuch=AUS", "?versuch=aus%20", "?versuch=%20Aus"]) {
    pruefe(`${suche} stellt aus`, false, laden({ suche }).Wach.an);
  }
  for (const suche of ["?versuch=Wach", "?versuch=wach+"]) {
    pruefe(`${suche} stellt an`, true,
           laden({ suche, gemerkt: { bildschirm: "aus" } }).Wach.an);
  }
  // Ein unbekannter Wert aendert nichts.
  pruefe("?versuch=wachs laesst die Vorgabe", true,
         laden({ suche: "?versuch=wachs" }).Wach.an);
  // Der alte Speicherschluessel aus 0.4.5 bewirkt nichts mehr.
  const alt = laden({ gemerkt: { versuch: "wach" } });
  pruefe("altes \"versuch\" bleibt unangetastet", "wach", alt.kasten.versuch);
  pruefe("und der Schalter steht auf der Vorgabe", true, alt.Wach.an);
}

titel("4) Das Protokoll sieht nur, wer es bestellt");
{
  const p = laden();
  await geste(p);
  const kasten = p.umgebung.document.getElementById("versuchkasten");
  pruefe("ohne Zusatz bleibt der Kasten versteckt", true, kasten.hidden !== false);
  pruefe("und das Feld leer", "",
         p.umgebung.document.getElementById("versuchzeilen").textContent);
  // Mitgeschrieben wird trotzdem, nur im Speicher.
  pruefe("mitgeschrieben wird trotzdem", true, p.Versuch.ereignisse.length > 0);

  const q = laden({ suche: "?versuch=protokoll" });
  await geste(q);
  pruefe("mit ?versuch=protokoll ist er da", false,
         q.umgebung.document.getElementById("versuchkasten").hidden);
  pruefe("und zeigt, was geschah", true,
         q.umgebung.document.getElementById("versuchzeilen").textContent
          .includes("Video startet"));
  pruefe("protokoll aendert den Schalter nicht", true, q.Wach.an);
  // Nicht gemerkt: ein Messgeraet soll nicht haengen bleiben.
  pruefe("nichts gemerkt", undefined, q.kasten.versuch);

  const r = laden({ suche: "?versuch=protokoll,aus" });
  pruefe("protokoll,aus: Kasten da", false,
         r.umgebung.document.getElementById("versuchkasten").hidden);
  pruefe("protokoll,aus: Schalter aus", false, r.Wach.an);
}

titel("5) Ohne Wake Lock (der Saal): das Video");
{
  const p = laden();
  pruefe("der Nachbau hat keinen Wake Lock", false,
         "wakeLock" in p.umgebung.navigator);
  await zuhoeren(p);
  pruefe("das Video laeuft", true, p.Wach.laeuft);
  pruefe("der Start steht im Protokoll", true,
         p.Versuch.ereignisse.some((z) => z.includes("Video startet")));
  // Zurueck zur Sprachwahl haelt seit 0.4.6 nichts mehr an: die naechste
  // Beruehrung startete es ohnehin wieder.
  klick(p.umgebung.document.getElementById("zurueck"));
  pruefe("zurueck laesst es laufen", true, p.Wach.laeuft);
}

titel("5b) Nicht stumm, und laut genug fuer Chromium");
{
  /* Chromium, video_wake_lock.cc, ShouldBeActive():
       bool has_volume = VideoElement().EffectiveMediaVolume() > 0;
       bool has_audio = VideoElement().HasAudio() && has_volume;
     muted oder volume 0 heisst also: keine Sperre ueber den Ton. */
  const p = laden();
  await geste(p);
  const v = video(p);
  pruefe("das Element ist NICHT stumm", false, v.muted);
  pruefe("und die Lautstaerke ist groesser als null", true, v.volume > 0);
  pruefe("aber klein", true, v.volume <= 0.05);
  pruefe("in Schleife", true, v.loop);
  const quellen = v.kinder.filter((k) => k.tagName === "SOURCE");
  pruefe("zwei Quellen", 2, quellen.length);
  pruefe("webm und mp4", ["video/webm", "video/mp4"],
         quellen.map((k) => k.type));
  for (const q of quellen) {
    const [, art, b64] = q.src.match(/^data:video\/(\w+);base64,(.+)$/) || [];
    const roh = Buffer.from(b64, "base64");
    pruefe(`${art} unter 10 KB`, true, roh.length > 0 && roh.length < 10240);
    // Die Kennung der Tonspur im Behaelter. Ohne sie ist HasAudio()
    // falsch, und genau daran scheiterte der erste Versuch am Handy.
    const text = roh.toString("latin1");
    const spur = art === "mp4" ? "mp4a" : "Opus";
    pruefe(`${art} hat eine Tonspur (${spur})`, true, text.includes(spur));
  }
}

titel("5c) Ton aus haelt das Video nicht an");
{
  const p = laden();
  await zuhoeren(p);
  pruefe("das Video laeuft", true, p.Wach.laeuft);
  klick(p.umgebung.document.getElementById("w-ton"));
  pruefe("der Ton ist aus", false, p.zustand.tonAn);
  pruefe("das Video laeuft weiter", true, p.Wach.laeuft);
  pruefe("und das Element auch", false, video(p).paused);
  klick(p.umgebung.document.getElementById("w-ton"));
  pruefe("der Ton laesst sich wieder einschalten", true, p.zustand.tonAn);
}

titel("5d) Das Video stoert die Bedienung nicht");
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
  const z = parseInt((regel.match(/z-index:\s*(\d+)/) || [])[1], 10);
  const schirm = parseInt(
    (stil.split(".schirm{")[1].split("}")[0].match(/z-index:\s*(\d+)/)
     || [])[1], 10);
  pruefe(`z-index ${z} liegt unter dem Inhalt (${schirm})`, true, z < schirm);
  const deckkraft = parseFloat((regel.match(/opacity:\s*([\d.]+)/) || [])[1]);
  pruefe("praktisch unsichtbar", true, deckkraft > 0 && deckkraft <= 0.02);

  const p = laden();
  await geste(p);
  const vorher = p.umgebung.__pruef.Dunkel.stufe;
  klick(p.umgebung.document.getElementById("w-dunkel"));
  pruefe("Abdunkeln kommt an", vorher + 1, p.umgebung.__pruef.Dunkel.stufe);
  klick(p.umgebung.document.getElementById("w-mehr"));
  pruefe("Mehr geht auf", true,
         p.umgebung.document.getElementById("mehrblatt").offen);
  // Der Schalter schliesst das Blatt nicht -- man soll sehen, dass er
  // umgesprungen ist.
  klick(schalter(p));
  pruefe("der Schalter laesst das Blatt offen", true,
         p.umgebung.document.getElementById("mehrblatt").offen);
}

titel("6) Wake Lock vorhanden und erteilt");
{
  const p = laden({ wakeLock: true });
  await geste(p);
  pruefe("die Sperre ist erteilt", 1, p.sperren.length);
  pruefe("das Video laeuft NICHT", false, p.Wach.laeuft);
  // Aber es ist gebaut und hat in der Geste einmal gespielt -- sonst
  // liesse Safari es spaeter ohne Geste nicht an.
  pruefe("das Element ist gebaut", true, !!video(p));
  pruefe("und steht wieder", true, video(p).paused);
  pruefe("das Protokoll sagt, warum", true,
         p.Versuch.ereignisse.some((z) => z.includes("Vorrang")));
  // Weitere Gesten fordern nicht noch einmal an.
  await geste(p);
  await zuhoeren(p);
  pruefe("keine zweite Anforderung", 1, p.sperren.length);
}

titel("6b) Wake Lock da, aber abgelehnt");
{
  const p = laden({ wakeLock: "ablehnen" });
  await geste(p);
  pruefe("das Video springt ein", true, p.Wach.laeuft);
  pruefe("und spielt", false, video(p).paused);
  pruefe("das Protokoll nennt die Ablehnung", true,
         p.Versuch.ereignisse.some((z) => z.includes("Wake Lock abgelehnt")));
}

titel("6c) Wake Lock geht bei sichtbarer Seite verloren");
{
  const p = laden({ wakeLock: true });
  await geste(p);
  pruefe("vorher kein Video", false, p.Wach.laeuft);
  p.sperren[0].release();
  await takte();
  pruefe("nach dem Verlust springt das Video ein", true, p.Wach.laeuft);
  pruefe("das Protokoll nennt es", true,
         p.Versuch.ereignisse.some((z) => z.includes("Wake Lock verloren")));
}

titel("6d) Verborgen, zurueck, und dann abgelehnt");
{
  const p = laden({ wakeLock: [true, false] });
  await geste(p);
  p.umgebung.document.visibilityState = "hidden";
  p.sperren[0].release();
  await sichtbarkeit(p, "hidden");
  pruefe("verborgen: kein Video", false, p.Wach.laeuft);
  await sichtbarkeit(p, "visible");
  pruefe("zurueck und abgelehnt: das Video springt ein", true, p.Wach.laeuft);
}

titel("6e) Verborgen, zurueck, und wieder erteilt");
{
  const p = laden({ wakeLock: [true, true] });
  await geste(p);
  p.umgebung.document.visibilityState = "hidden";
  p.sperren[0].release();
  await sichtbarkeit(p, "hidden");
  await sichtbarkeit(p, "visible");
  pruefe("neu angefordert", 2, p.sperren.length);
  pruefe("und kein Video noetig", false, p.Wach.laeuft);
}

titel("6f) Vor der ersten Geste fordert die Rueckkehr nichts an");
{
  const p = laden({ wakeLock: true });
  await sichtbarkeit(p, "hidden");
  await sichtbarkeit(p, "visible");
  pruefe("keine Anforderung ohne Geste", 0, p.sperren.length);
}

titel("7) Das Video stand im Hintergrund");
{
  const p = laden();
  await geste(p);
  video(p).pause();
  p.Wach.nachsehen();
  pruefe("beim Zurueckkommen laeuft es wieder", false, video(p).paused);
  pruefe("und es steht im Protokoll", true,
         p.Versuch.ereignisse.some((z) => z.includes("Video stand")));
}

titel("8) Das Protokoll bleibt auf dem Geraet");
{
  const p = laden();
  await geste(p);
  const koerper = QUELLE.split("merken(was, mehr){")[1].split("\n  },")[0];
  pruefe("merken() ruft kein fetch", false,
         /fetch|XMLHttpRequest|sendBeacon/.test(koerper));
  for (let i = 0; i < 150; i++) p.Versuch.merken("probe", String(i));
  pruefe("hoechstens hundert Zeilen", 100, p.Versuch.ereignisse.length);
}

titel("9) Vier Sekunden, damit es transient bleibt");
{
  /* Chromium, media/base/media_content_type.cc:
       const int kMinimumContentDurationSecs = 5;
       return (duration.is_zero() ||
               duration > base::Seconds(kMinimumContentDurationSecs))
                  ? MediaContentType::kPersistent
                  : MediaContentType::kTransient;
     Geprueft am Behaelter selbst, nicht am ffmpeg-Aufruf im Kommentar. */
  const p = laden();
  await geste(p);
  for (const q of video(p).kinder.filter((k) => k.tagName === "SOURCE")) {
    const [, art, b64] = q.src.match(/^data:video\/(\w+);base64,(.+)$/) || [];
    const roh = Buffer.from(b64, "base64");
    let sekunden = null;
    if (art === "mp4") {
      const i = roh.indexOf("mvhd");
      const einheit = roh.readUInt32BE(i + 16);
      sekunden = roh.readUInt32BE(i + 20) / einheit;
    } else {
      const i = roh.indexOf(Buffer.from([0x44, 0x89]));
      const laenge = roh[i + 2] & 0x0f;
      sekunden = (laenge === 4 ? roh.readFloatBE(i + 3)
                               : roh.readDoubleBE(i + 3)) / 1000;
    }
    pruefe(`${art}: ${sekunden.toFixed(2)} s, unter 5`, true,
           sekunden > 0 && sekunden < 5);
  }
}

titel("10) Die Beschriftung, in allen Oberflaechensprachen");
{
  const p = laden();
  const { TEXTE } = p;
  for (const s of Object.keys(TEXTE)) {
    const t = TEXTE[s];
    const fehlt = ["wach", "wachAn", "wachAus"].filter((k) => !t[k]);
    pruefe(`${s} ist vollstaendig`, [], fehlt);
    // Die Zeile im Mehr-Blatt auf 320 px: rund 26 Zeichen Platz neben
    // dem Zeichen, gemessen an der laengsten Zeile, die schon da ist.
    const zeile = `${t.wach}: ${[t.wachAn, t.wachAus]
      .sort((a, b) => b.length - a.length)[0]}`;
    pruefe(`${s} passt aufs Mehr-Blatt (${zeile.length} Zeichen)`, true,
           zeile.length <= 26);
  }
  p.zustand.sprache = "ru";
  p.Wach.zeichnen();
  pruefe("auf Russisch steht Russisch darauf", true,
         schalter(p).querySelector(".beschriftung").textContent
           .startsWith(TEXTE.ru.wach));
}

console.log("");
if (fehler) { console.log(`${fehler} FEHLER`); process.exit(1); }
console.log("\x1b[32mAlle Faelle wie erwartet.\x1b[0m");
