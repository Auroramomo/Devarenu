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
  pruefe("der Knopf bietet mehr an", TEXTE.de.dunkler, schrift());
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
  // Ganz schwarz saehe aus wie ein Geraet, das aus ist.
  const hoechste = parseFloat(
    (STIL.match(/data-dunkel="2"\] #abdunkler\{opacity:([\d.]+)\}/) || [])[1]);
  pruefe("die dunkelste Stufe ist nicht ganz schwarz", true,
         hoechste > 0 && hoechste <= 0.85);
  // Und die Fussleiste liegt darueber: wer abgedunkelt hat, muss den
  // Weg zurueck finden.
  pruefe("die Fußleiste liegt über der Decke", true,
         /html\[data-dunkel\] \.fussblock\{z-index:6\}/.test(STIL));
  const leiste = parseFloat(
    (STIL.match(/data-dunkel="2"\] \.fussblock\{opacity:([\d.]+)\}/) || [])[1]);
  pruefe("und bleibt heller als der Rest", true, leiste > 1 - hoechste);

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

titel("4) Der Knopf spricht alle Oberflächensprachen");
{
  const { TEXTE } = laden();
  for (const s of Object.keys(TEXTE)) {
    pruefe(`${s} hat alle drei Beschriftungen`, true,
           !!(TEXTE[s].dunkel && TEXTE[s].dunkler && TEXTE[s].heller));
  }
  // Der Knopf zieht beim Sprachwechsel mit.
  const p = laden();
  p.zustand.sprache = "ru";
  p.umgebung.__pruef.Dunkel.setzen(1);
  const knopf = p.umgebung.document.getElementById("w-dunkel");
  pruefe("auf Russisch steht Russisch darauf", TEXTE.ru.dunkler,
         knopf.querySelector(".beschriftung").textContent);
}

// Fingerbreit, wie im Pult gefordert.
titel("5) Der Knopf ist zu treffen");
{
  const werkzeug = STIL.split(".werkzeug{")[1].split("}")[0];
  const hoch = parseFloat((werkzeug.match(/min-height:\s*(\d+)px/) || [])[1]);
  pruefe("mindestens 44 px hoch", true, hoch >= 44);
  // Vier Knoepfe in der zweiten Reihe duerfen keine Luecke lassen.
  const neben = STIL.split(".fussleiste.neben{")[1].split("}")[0];
  pruefe("die zweite Reihe teilt sich auf, so viele es sind", true,
         /grid-auto-flow:\s*column/.test(neben));
}

console.log("");
if (fehler) { console.log(`${fehler} FEHLER`); process.exit(1); }
console.log("\x1b[32mAlle Faelle wie erwartet.\x1b[0m");
