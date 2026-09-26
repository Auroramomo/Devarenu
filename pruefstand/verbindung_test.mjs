// Macht die Zuhoererseite bei einem Abbruch ruhig weiter?
//
//     node pruefstand/verbindung_test.mjs
//
// Im Saal bricht das WLAN ab: jemand geht hinter eine Wand, der
// Zugangspunkt startet neu, das Handy wechselt kurz ins Mobilnetz.
// Die Seite darf dann nicht "Keine Verbindung" hinstellen und warten,
// bis jemand neu laedt -- im Gottesdienst tut das niemand.
//
// SERVICE WORKER GEHT NICHT, und das ist keine Vermutung: Browser
// erlauben ihn nur in einem "secure context". Dazu zaehlen https und
// localhost, NICHT aber eine private Adresse wie http://10.0.0.1.
// Genau dort laeuft die Seite. Also ohne -- mit Wiederverbinden im
// laufenden Skript, und das ist hier geprueft.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import vm from "node:vm";

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

// Denselben Nachbau wie beim Sprachwechsel benutzen, damit es nur
// einen gibt. Er liegt dort als Modul bereit.
const { browserBauen, skriptLaden } =
  await import("./browsernachbau.mjs");

const umgebung = browserBauen();
skriptLaden(umgebung, join(WURZEL, "client.html"));
const { Verbindung, zustand, SPRACHEN, TEXTE } = umgebung.__pruef;
const doc = umgebung.document;

function anzeige() {
  return doc.getElementById("zustand").textContent;
}

console.log("\n\x1b[1m== Abbruch und Wiederkehr\x1b[0m");

zustand.sprache = "ru";
zustand.tonAn = true;
Verbindung.verbinden("ru");
await new Promise((f) => queueMicrotask(f));
const erster = umgebung.offeneDraehte.at(-1);
pruefe("verbunden", true, anzeige().length > 0);

// Der Draht faellt weg -- nicht, weil jemand die Sprache wechselt,
// sondern weil das Netz weg ist. gewollt bleibt true.
erster.readyState = 3;
erster.onclose && erster.onclose();
// Sprachunabhaengig: die Anzeige muss der WARTE-Text sein, nicht der
// GETRENNT-Text. Auf deutsche Woerter zu pruefen ginge schief, sobald
// der Fall in einer anderen Sprache laeuft -- und genau das tut er
// hier, in Russisch.
pruefe("die Seite zeigt den Warte-Text", TEXTE.ru.warte, anzeige());
pruefe("und nicht 'getrennt'", true, anzeige() !== TEXTE.ru.getrennt);
for (const sp of ["de", "en", "ru", "fa"]) {
  pruefe(`${sp}: der Warte-Text ist ein Satz, kein Wort`, true,
         (TEXTE[sp].warte || "").length > 25);
  pruefe(`${sp}: er nennt Devarenu`, true,
         (TEXTE[sp].warte || "").includes("Devarenu"));
}
pruefe("ein neuer Versuch ist geplant", true, Verbindung._uhr !== null);
pruefe("die Sprache bleibt stehen", "ru", zustand.sprache);

// Die Wartezeit waechst, bleibt aber gedeckelt -- und ist nicht bei
// allen Handys gleich, sonst kommen vierzig auf die Sekunde zurueck.
const wartezeiten = [];
for (let i = 1; i <= 8; i++) {
  Verbindung.versuche = i;
  wartezeiten.push(Verbindung._wartezeit());
}
pruefe("die erste Wartezeit ist kurz", true, wartezeiten[0] <= 2000);
pruefe("sie waechst", true, wartezeiten[3] > wartezeiten[0]);
pruefe("und ist gedeckelt", true, Math.max(...wartezeiten) <= 16000);
const zweiteRunde = [];
for (let i = 0; i < 12; i++) { Verbindung.versuche = 5;
  zweiteRunde.push(Verbindung._wartezeit()); }
pruefe("zwei Handys warten nicht exakt gleich lang", true,
       new Set(zweiteRunde).size > 1);

// Das Netz ist zurueck.
Verbindung.versuche = 0;
Verbindung.verbinden("ru");
await new Promise((f) => queueMicrotask(f));
const zweiter = umgebung.offeneDraehte.at(-1);
pruefe("wieder verbunden", TEXTE.ru.live, anzeige());
pruefe("und zwar mit einem NEUEN Draht", true, zweiter !== erster);
pruefe("der alte ist zu", true, erster.geschlossen || erster.readyState === 3);
pruefe("es laeuft genau einer", 1,
       umgebung.offeneDraehte.filter((d) => !d.geschlossen &&
                                            d.readyState !== 3).length);
pruefe("noch immer dieselbe Sprache", "ru", zustand.sprache);
pruefe("und der Draht fragt sie auch ab", true,
       zweiter.url.includes("sprache=ru"));

// Ein Segment nach der Rueckkehr kommt an.
zweiter.liefern({ typ: "segment", id: 9, text: "Снова здесь.",
                  absatz_ende: true, dauer: 2.0 });
pruefe("Text nach der Rueckkehr kommt an", true,
       doc.getElementById("strom").volltext().includes("Снова"));

console.log();
if (fehler) { console.log(`\x1b[31m${fehler} Fehler.\x1b[0m`); process.exit(1); }
console.log("\x1b[32mAlle Faelle wie erwartet.\x1b[0m");
