// Eine Leiste statt dreier Reihen -- und nichts ist verloren gegangen.
//
//     node pruefstand/fussleiste_test.mjs
//
// Bis 0.4.4 standen in der Hoeransicht neun Knoepfe in drei Reihen.
// Seit 0.4.5 ist es EINE Leiste mit fuenf Eintraegen; was selten
// gebraucht wird, steht unter "Mehr". Die Zusage dabei: keine
// Funktion faellt weg, und Abdunkeln bleibt mit einem Tipp erreichbar.

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

function laden() {
  const umgebung = browserBauen();
  umgebung.URLSearchParams = URLSearchParams;
  const p = skriptLaden(umgebung, SEITE);
  return { ...p, umgebung };
}
const klick = (el) => (el.horcher.click || []).forEach((f) => f());
const kennungen = (text) => [...text.matchAll(/id="([\w-]+)"/g)].map((m) => m[1]);

// Die Hoeransicht, ohne die Blaetter dahinter.
const SCHIRM = QUELLE.split('<section class="schirm" id="zuhoeren">')[1]
                     .split("</section>")[0];
const LEISTE = SCHIRM.split('<nav class="fussleiste" aria-label')[1]
                     .split("</nav>")[0];
const MEHR = QUELLE.split('<dialog id="mehrblatt">')[1].split("</dialog>")[0];

titel("1) Genau eine Leiste, genau fuenf Eintraege");
{
  const leisten = SCHIRM.match(/<nav class="fussleiste/g) || [];
  pruefe("eine Leiste in der Höransicht", 1, leisten.length);
  pruefe("fünf Knöpfe darin", 5, (LEISTE.match(/<button/g) || []).length);
  pruefe("und zwar diese",
         ["w-ton", "w-text", "w-dunkel", "w-sprache", "w-mehr"],
         kennungen(LEISTE));
  const regel = STIL.split(".fussleiste{")[1].split("}")[0];
  pruefe("fünf Spalten im Stil", true,
         /grid-template-columns:repeat\(5,1fr\)/.test(regel));
  // 320 px geteilt durch fuenf sind 64 px; davon geht der Seitenrand ab.
  pruefe("die Beschriftung bricht nicht um", true,
         /white-space:nowrap/.test(STIL.split(".fussleiste .beschriftung{")[1]
                                      .split("}")[0]));
}

titel("2) Keine Funktion ist verloren");
{
  // Das war die Bedienung bis 0.4.4, Reihe fuer Reihe.
  const vorher = ["w-ton", "w-text", "w-sprache",
                  "zurueck", "w-post", "w-dunkel", "rueckmeldung",
                  "u-gut", "u-schwer"];
  for (const k of vorher) {
    pruefe(`${k} gibt es noch`, true, QUELLE.includes(`id="${k}"`));
  }
  // Und jeder davon hat noch einen Horcher.
  const p = laden();
  for (const k of vorher) {
    const el = p.umgebung.document.getElementById(k);
    pruefe(`${k} reagiert auf einen Klick`, true,
           !!(el.horcher.click && el.horcher.click.length));
  }
}

titel("3) Was unter Mehr steht");
{
  // Seit 0.4.6 steht obenan der Schalter "Bildschirm anlassen".
  pruefe("die Urteilsknöpfe, der Schalter und die drei Zeilen",
         ["mehr-titel", "urteil", "u-gut", "u-schwer",
          "w-wach", "w-post", "rueckmeldung", "zurueck", "mehr-zu"],
         kennungen(MEHR));
  // Zurueck steht hier und nicht in der Leiste: es fuehrt beinahe
  // zum selben Ziel wie Sprache.
  pruefe("zurueck ist aus der Leiste heraus", false,
         LEISTE.includes('id="zurueck"'));
  pruefe("Sprache ist geblieben", true, LEISTE.includes('id="w-sprache"'));
}

titel("4) Abdunkeln mit EINEM Tipp");
{
  pruefe("der Knopf steht in der Leiste", true,
         LEISTE.includes('id="w-dunkel"'));
  pruefe("und nicht unter Mehr", false, MEHR.includes('id="w-dunkel"'));
  const p = laden();
  const knopf = p.umgebung.document.getElementById("w-dunkel");
  klick(knopf);
  pruefe("ein Tipp dunkelt ab", 1, p.umgebung.__pruef.Dunkel.stufe);
  pruefe("kein Blatt ist dafür aufgegangen", undefined,
         p.umgebung.document.getElementById("mehrblatt").offen);
}

titel("5) Das Mehr-Blatt geht auf und wieder zu");
{
  const p = laden();
  const blatt = p.umgebung.document.getElementById("mehrblatt");
  klick(p.umgebung.document.getElementById("w-mehr"));
  pruefe("Mehr öffnet das Blatt", true, blatt.offen);
  klick(p.umgebung.document.getElementById("mehr-zu"));
  pruefe("Schließen schließt es", false, blatt.offen);

  // Jede der drei Zeilen fuehrt woanders hin und laesst das Blatt zu.
  for (const k of ["w-post", "rueckmeldung", "zurueck"]) {
    klick(p.umgebung.document.getElementById("w-mehr"));
    klick(p.umgebung.document.getElementById(k));
    pruefe(`${k} schließt das Blatt`, false, blatt.offen);
  }
  // Ein Urteil nicht: die Antwort "Danke!" soll noch zu lesen sein.
  klick(p.umgebung.document.getElementById("w-mehr"));
  klick(p.umgebung.document.getElementById("u-gut"));
  pruefe("ein Urteil lässt das Blatt offen", true, blatt.offen);
}

titel("6) Beschriftet in allen Oberflaechensprachen");
{
  const { TEXTE } = laden();
  const noetig = ["ton", "tonAus", "text", "textAus", "sprache",
                  "dunkel", "heller", "mehr", "mehrTitel",
                  "post", "zurueck", "rueckmeldung", "schliessen",
                  "uGut", "uSchwer"];
  for (const s of Object.keys(TEXTE)) {
    const fehlt = noetig.filter((k) => !TEXTE[s][k]);
    pruefe(`${s} ist vollständig`, [], fehlt);
  }
  // Die fuenf Woerter in der Leiste muessen in eine schmale Zelle.
  for (const s of Object.keys(TEXTE)) {
    const lang = ["ton", "tonAus", "text", "textAus", "sprache",
                  "dunkel", "heller", "mehr"]
                 .filter((k) => TEXTE[s][k].length > 10);
    pruefe(`${s} bleibt kurz genug`, [], lang);
  }
}

titel("7) Fingerbreit");
{
  const werkzeug = STIL.split(".werkzeug{")[1].split("}")[0];
  pruefe("mindestens 44 px hoch", true,
         parseFloat((werkzeug.match(/min-height:\s*(\d+)px/) || [])[1]) >= 44);
  const zeile = STIL.split(".werkzeug.zeile{")[1].split("}")[0];
  pruefe("die Zeilen im Blatt haben eine Kontur", true,
         /border:1px solid/.test(zeile));
}

console.log("");
if (fehler) { console.log(`${fehler} FEHLER`); process.exit(1); }
console.log("\x1b[32mAlle Faelle wie erwartet.\x1b[0m");
