// Wechselt die Zuhoererseite wirklich die Sprache -- oder laufen zwei?
//
//     node pruefstand/sprachwechsel_test.mjs
//
// Gemeldet wurde: Farsi laeuft, eine andere Sprache wird gewaehlt, und
// beide Uebersetzungen stehen untereinander. Dieser Prueflauf nimmt das
// echte Skript aus client.html, stellt ihm einen nachgebauten Browser
// daneben (DOM, WebSocket, Audio) und laesst Segmente eintreffen --
// auch solche, die NACH dem Wechsel noch aus der alten Verbindung
// kommen. Genau das passiert im Saal: close() ist nicht sofort fertig.
//
// node gibt es nur auf dem Arbeitsrechner. Nichts davon geht auf den
// Gemeinderechner, und nichts davon gehoert in requirements.txt.
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { browserBauen, skriptLaden } from "./browsernachbau.mjs";

const HIER = dirname(fileURLToPath(import.meta.url));
const WURZEL = join(HIER, "..");

let fehler = 0;
function pruefe(was, erwartet, ist) {
  const gleich = JSON.stringify(erwartet) === JSON.stringify(ist);
  if (gleich) console.log(`   ok    ${was}`);
  else {
    console.log(`   FEHL  ${was}: erwartet ${JSON.stringify(erwartet)}, ` +
                `ist ${JSON.stringify(ist)}`);
    fehler++;
  }
}

const umgebung = browserBauen();
try {
  skriptLaden(umgebung, join(WURZEL, "client.html"));
} catch (e) {
  console.log(`   FEHL  client.html liess sich nicht laden: ${e.message}`);
  process.exit(1);
}

console.log("\n\x1b[1m== Nachbau\x1b[0m");
pruefe("das Skript aus client.html laeuft", true,
       typeof umgebung.__pruef?.spracheWechseln === "function");
pruefe("der Zustand ist erreichbar", "object", typeof umgebung.__pruef?.zustand);

// --------------------------------------------------------- der Fall
const { Verbindung, spracheWechseln, zustand, Ton } = umgebung.__pruef;
const { offeneDraehte } = umgebung;
const strom = umgebung.document.getElementById("strom");

function zuruecksetzen(sprache) {
  offeneDraehte.length = 0;
  strom.kinder = [];
  strom._text = "";
  zustand.sprache = sprache;
  zustand.tonAn = true;
  Verbindung.verbinden(sprache);
  return offeneDraehte[offeneDraehte.length - 1];
}

function satz(id, text) {
  return { typ: "segment", id, text, absatz_ende: true,
           dauer: 2.4, audio: `/ton/x/${id}` };
}

async function durchlauf(von, nach) {
  const alt = zuruecksetzen(von);
  await new Promise((f) => queueMicrotask(f));
  alt.liefern(satz(1, "Erster Satz in der alten Sprache."));

  spracheWechseln(nach);
  const neu = offeneDraehte[offeneDraehte.length - 1];

  // Das Entscheidende: der alte Draht liefert NACH dem Wechsel weiter.
  // close() ist nicht sofort durch, und was im Puffer des Browsers
  // liegt, wird noch zugestellt.
  alt.liefern(satz(2, "Nachzuegler aus der alten Sprache."));
  await new Promise((f) => queueMicrotask(f));
  neu.liefern(satz(3, "Erster Satz in der neuen Sprache."));

  const texte = strom.volltext();
  return { alt, neu, texte,
           // Zwei verschiedene Fehler, die gleich aussehen:
           stehenGelassen: /Erster Satz in der alten/.test(texte),
           nachzuegler: /Nachzuegler/.test(texte),
           neueSpur: /neuen Sprache/.test(texte),
           tonSchlange: Ton.schlange.length,
           tonAusAlt: Ton.schlange.some((h) => /\/(1|2)$/.test(h.url)) };
}

console.log("\n\x1b[1m== Sprachwechsel: es darf nur EINE Sprache laufen\x1b[0m");
for (const [von, nach, wie] of [
  ["fa", "ru", "von Farsi (RTL) zu einer LTR-Sprache"],
  ["ru", "fa", "von einer LTR-Sprache zu Farsi (RTL)"],
  ["en", "ru", "zwischen zwei LTR-Sprachen"],
  ["fa", "ar", "zwischen zwei RTL-Sprachen"],
]) {
  const e = await durchlauf(von, nach);
  console.log(`\n   ${wie}  (${von} -> ${nach})`);
  pruefe("die alte Verbindung ist geschlossen", true, e.alt.geschlossen);
  pruefe("die neue ist offen", false, e.neu.geschlossen);
  pruefe("der alte Verlauf ist weggeraeumt", false, e.stehenGelassen);
  pruefe("kein Nachzuegler aus dem alten Draht", false, e.nachzuegler);
  pruefe("kein Ton der alten Sprache in der Schlange", false, e.tonAusAlt);
  pruefe("der neue Text ist da", true, e.neueSpur);
  pruefe("die Sprache ist umgestellt", nach, zustand.sprache);
  // Gegenprobe: findet der Prueflauf ueberhaupt Text? Ohne sie wuerde
  // "kein alter Text da" auch dann bestehen, wenn gar nichts ankommt.
  pruefe("der Prueflauf sieht ueberhaupt Text", true, e.texte.trim().length > 0);
}

console.log();
if (fehler) { console.log(`\x1b[31m${fehler} Fehler.\x1b[0m`); process.exit(1); }
console.log("\x1b[32mAlle Faelle wie erwartet.\x1b[0m");
