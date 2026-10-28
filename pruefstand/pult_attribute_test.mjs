// Folgen Platzhalter, title und aria-label der Sprache des Pults?
//
//     node pruefstand/pult_attribute_test.mjs
//
// Beim Handytest am 28.10.2026 stand im englischen Pult unter "Topic
// and Bible passages" der deutsche Platzhalter "Predigt über Vergebung.
// Texte: Matthäus 18, ...". uiZeichnen() setzte nur die data-t-Felder,
// also den sichtbaren Text -- was in Attributen steht, blieb deutsch.
// Ebenso "Netzname", "Passwort", der title des QR-Knopfs und das
// aria-label der Reiterleiste.
//
// Geprueft wird jedes Element im Markup, das einen dieser Texte traegt:
// Nach dem Umschalten auf Englisch steht dort nicht mehr der deutsche,
// nach dem Zurueckschalten wieder er. Ausgenommen sind nur Texte, die
// in beiden Sprachen gleich lauten (NEUTRAL).

import { pultBauen } from "./pultnachbau.mjs";

const ATTRIBUTE = ["placeholder", "title", "aria-label"];
// Gleich in beiden Sprachen: eine Beispieladresse.
const NEUTRAL = new Set(["https://ntfy.sh/…"]);
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
const warte = () => new Promise(r => setTimeout(r, 60));

const p = pultBauen({ zustand: {}, pegel: {} });
await warte();
const kennung = (e) => e.id ? `#${e.id}` : `<${e.tagName.toLowerCase()} `
  + `${Object.keys(e.attribute).filter(a => a.startsWith("data-t")).join(" ")}>`;
const lesen = (e, a) => e.getAttribute(a) ?? "";

// Was im Markup steht, ehe das Skript etwas setzt.
const deutsch = [];
for (const e of p.body.alle()) {
  for (const a of ATTRIBUTE) {
    const w = e.getAttribute(a);
    if (w && !w.includes("${") && !NEUTRAL.has(w)) deutsch.push([e, a, w]);
  }
}

titel("1) Was im Markup steht");
pruefe("mindestens die bekannten Stellen sind dabei", true,
       ["kontext", "ssid", "wpw", "pwfeld", "qrknopf", "tonzahn"]
         .every(id => deutsch.some(([e]) => e.id === id)));

titel("2) Auf Englisch umgeschaltet");
p.fenster.uiSprache();
await warte();
pruefe("das Pult steht auf Englisch", "en", p.fenster.document
       .documentElement.lang);
const blieben = deutsch.filter(([e, a, w]) => lesen(e, a) === w)
                       .map(([e, a, w]) => `${kennung(e)} ${a}="${w}"`);
pruefe("kein Attribut ist deutsch geblieben", [], blieben);
pruefe("der Platzhalter im Feld Topic ist englisch",
       "Sermon on forgiveness. Texts: Matthew 18, Psalm 32. Names: Peter, "
       + "Nathan.", lesen(p.nachId.get("kontext"), "placeholder"));
const leer = deutsch.filter(([e, a]) => !lesen(e, a))
                    .map(([e, a]) => `${kennung(e)} ${a}`);
pruefe("und keines ist leer geworden", [], leer);

titel("3) Wieder auf Deutsch");
p.fenster.uiSprache();
await warte();
const anders = deutsch.filter(([e, a, w]) => lesen(e, a) !== w)
                      .map(([e, a, w]) => `${kennung(e)} ${a}: `
                           + `"${lesen(e, a)}" statt "${w}"`);
pruefe("alles steht wieder wie im Markup", [], anders);

console.log("");
if (fehler) { console.log(`${fehler} FEHLER`); process.exit(1); }
console.log("\x1b[32mAlle Faelle wie erwartet.\x1b[0m");
