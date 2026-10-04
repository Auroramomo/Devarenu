// Abdunkeln auf der Hörerseite.
//
//     node pruefstand/abdunkeln_test.mjs
//
// Der Bildschirm muss anbleiben, sonst reisst der Ton ab -- also kann
// ein Zuhoerer ihn stattdessen abdunkeln. Drei Zusagen:
//
//   1. Drei Stufen im Kreis, und der Knopf sagt, was der naechste
//      Druck bringt.
//   2. Die Stufe ueberlebt ein Neuladen, auch ueber Sonntage hinweg.
//   3. Abgedunkelt aendert sich am Ton und am Mitlesen NICHTS, und
//      der Weg zurueck bleibt sichtbar.

import { readFileSync } from "node:fs";
import { browserBauen, skriptLaden } from "./browsernachbau.mjs";

const SEITE = new URL("../client.html", import.meta.url).pathname;
const QUELLE = readFileSync(SEITE, "utf8");
const STIL = QUELLE.split("<style>")[1].split("</style>")[0];
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

function laden({ gemerkt = {} } = {}) {
  const umgebung = browserBauen();
  const kasten = { ...gemerkt };
  umgebung.localStorage = {
    getItem: (k) => (k in kasten ? kasten[k] : null),
    setItem: (k, w) => { kasten[k] = String(w); },
    removeItem: (k) => { delete kasten[k]; },
  };
  umgebung.URLSearchParams = URLSearchParams;
  const p = skriptLaden(umgebung, SEITE);
  return { ...p, umgebung, kasten };
}

// Welche Stufe das Dokument gerade traegt -- genau daran haengt der
// Stil, nicht an der Zahl im Modul.
const stufeAmDokument = (u) =>
  u.document.documentElement.getAttribute("data-dunkel");

titel("1) Drei Stufen im Kreis");
{
  const { Dunkel, umgebung, zustand, TEXTE } = laden();
  zustand.sprache = "de";
  const knopf = umgebung.document.getElementById("w-dunkel");
  const schrift = () => knopf.querySelector(".beschriftung").textContent;

  pruefe("fängt hell an", 0, Dunkel.stufe);
  pruefe("und das Dokument trägt nichts", null, stufeAmDokument(umgebung));
  Dunkel.setzen(0);
  pruefe("der Knopf lädt zum Abdunkeln ein", TEXTE.de.dunkel, schrift());
  pruefe("und gilt als nicht gedrückt", "false",
         knopf.getAttribute("aria-pressed"));

  Dunkel.weiter();
  pruefe("ein Druck: Stufe 1", 1, Dunkel.stufe);
  pruefe("das Dokument trägt sie", "1", stufeAmDokument(umgebung));
  // Solange es dunkler werden kann, steht dasselbe Wort da. Zwei
  // kurze Woerter statt dreier -- fuenf Spalten auf 320 px.
  pruefe("der Knopf bietet weiter mehr an", TEXTE.de.dunkel, schrift());
  pruefe("und gilt als gedrückt", "true", knopf.getAttribute("aria-pressed"));

  Dunkel.weiter();
  pruefe("zwei Drücke: Stufe 2", 2, Dunkel.stufe);
  pruefe("der Knopf führt zurück", TEXTE.de.heller, schrift());

  Dunkel.weiter();
  pruefe("drei Drücke sind wieder hell", 0, Dunkel.stufe);
  pruefe("und das Dokument trägt nichts mehr", null,
         stufeAmDokument(umgebung));
}

titel("2) Die Stufe überlebt das Neuladen");
{
  const { Dunkel, kasten } = laden();
  Dunkel.weiter();
  pruefe("gemerkt wird sie", "1", kasten.dunkel);
  // Ohne Datum im Schlüssel, anders als die Rückmeldung: wer einmal
  // abdunkelt, will das nächsten Sonntag wieder.
  pruefe("und zwar ohne Datum", false, /\d{4}-\d{2}-\d{2}/.test(
         Object.keys(kasten).join(" ")));
  const zweiter = laden({ gemerkt: { dunkel: "2" } });
  pruefe("beim nächsten Mal gilt sie", 2, zweiter.Dunkel.stufe);
  pruefe("und steht sofort am Dokument", "2",
         stufeAmDokument(zweiter.umgebung));
  // Was im Speicher steht, kommt nicht von uns -- jemand hat dort
  // schon einmal von Hand hineingesehen.
  for (const [wert, erwartet] of [["7", 1], ["-1", 2], ["quatsch", 0],
                                  ["", 0], ["2.9", 2]]) {
    pruefe(`"${wert}" ergibt eine gültige Stufe`, erwartet,
           laden({ gemerkt: { dunkel: wert } }).Dunkel.stufe);
  }
}

titel("3) Abgedunkelt bleibt alles bedienbar");
{
  // Die Decke faengt keine Beruehrung ab: sonst waere mit der ersten
  // Stufe die ganze Seite tot.
  const decke = STIL.split("#abdunkler{")[1].split("}")[0];
  pruefe("die Decke lässt Berührungen durch", true,
         /pointer-events:\s*none/.test(decke));
  pruefe("sie liegt über dem Inhalt", true, /z-index:\s*5/.test(decke));

  // Am Ton und am Mitlesen aendert das Abdunkeln nichts.
  const p = laden();
  p.zustand.sprache = "de";
  p.Ton.freischalten();
  p.zustand.tonAn = true;
  p.Dunkel.setzen(2);
  p.Ton.schlange = [];
  p.Ton.spielt = true;            // damit _weiter nichts abzieht
  p.Ton.einreihen("/ton/de/1", 1);
  pruefe("das Häppchen wird auch abgedunkelt eingereiht", 1,
         p.Ton.schlange.length);
  pruefe("und der Ton ist weiterhin an", true, p.zustand.tonAn);
}

titel("3b) Abgedunkelt bleibt der Text lesbar");
{
  /* Die Grenze fuer die dunkelste Stufe ist keine Geschmacksfrage.
     Eine schwarze Decke mit Deckkraft d senkt jede Leuchtdichte auf
     (1-d) -- im Kontrastbruch steht aber die 0,05 im Nenner, also
     faellt das Verhaeltnis schneller als die Helligkeit. Bei 0,82
     waere der Text bei 4,33:1 und damit unter WCAG 1.4.3. */
  const marke = {};
  for (const m of STIL.matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})/g))
    marke[m[1]] = m[2];
  const L = (hex) => {
    const k = [1, 3, 5].map((i) => parseInt(hex.substr(i, 2), 16) / 255)
      .map((c) => c <= 0.03928 ? c / 12.92
                               : Math.pow((c + 0.055) / 1.055, 2.4));
    return 0.2126 * k[0] + 0.7152 * k[1] + 0.0722 * k[2];
  };
  const K = (a, b, d) => {
    const x = L(a) * (1 - d), y = L(b) * (1 - d);
    return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
  };
  const stufen = [...STIL.matchAll(
    /data-dunkel="(\d)"\] #abdunkler\{opacity:([\d.]+)\}/g)]
    .map((m) => parseFloat(m[2]));
  pruefe("zwei Stufen im Stil", 2, stufen.length);
  pruefe("keine ist ganz schwarz", true, stufen.every((d) => d > 0 && d < 1));
  for (const d of stufen) {
    // 4,5:1 fuer den Abschnittstext, 3:1 fuer den Zeitstempel.
    const text = K(marke.tinte, marke.blatt, d);
    const leise = K(marke.leise, marke.blatt, d);
    pruefe(`bei ${d}: Text ${text.toFixed(2)}:1`, true, text >= 4.5);
    pruefe(`bei ${d}: Zeitstempel ${leise.toFixed(2)}:1`, true, leise >= 3);
  }
}

titel("4) Der Knopf spricht alle Oberflächensprachen");
{
  const { TEXTE } = laden();
  for (const s of Object.keys(TEXTE)) {
    pruefe(`${s} hat beide Beschriftungen`, true,
           !!(TEXTE[s].dunkel && TEXTE[s].heller));
    // Sie muessen in eine Zelle von rund 56 px passen.
    pruefe(`${s} bleibt kurz`, true,
           TEXTE[s].dunkel.length <= 9 && TEXTE[s].heller.length <= 9);
  }
  // Der Knopf zieht beim Sprachwechsel mit.
  const p = laden();
  p.zustand.sprache = "ru";
  p.umgebung.__pruef.Dunkel.setzen(1);
  const knopf = p.umgebung.document.getElementById("w-dunkel");
  pruefe("auf Russisch steht Russisch darauf", TEXTE.ru.dunkel,
         knopf.querySelector(".beschriftung").textContent);
}

// Fingerbreit, wie im Pult gefordert.
titel("5) Der Knopf ist zu treffen");
{
  const werkzeug = STIL.split(".werkzeug{")[1].split("}")[0];
  const hoch = parseFloat((werkzeug.match(/min-height:\s*(\d+)px/) || [])[1]);
  pruefe("mindestens 44 px hoch", true, hoch >= 44);
  // Eine Leiste, fuenf Eintraege -- und Abdunkeln ist einer davon.
  const leiste = STIL.split(".fussleiste{")[1].split("}")[0];
  pruefe("die Leiste hat fünf Spalten", true,
         /grid-template-columns:repeat\(5,1fr\)/.test(leiste));
  const bar = QUELLE.split('<nav class="fussleiste" aria-label')[1]
                    .split("</nav>")[0];
  pruefe("Abdunkeln steht darin, nicht unter Mehr", true,
         bar.includes('id="w-dunkel"'));
}

console.log("");
if (fehler) { console.log(`${fehler} FEHLER`); process.exit(1); }
console.log("\x1b[32mAlle Faelle wie erwartet.\x1b[0m");
