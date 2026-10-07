// Der Hinweis zu ungeprueften Sprachen -- in der Sprache selbst, mit
// der Bitte um Mithilfe (0.5.0).
//
//     node pruefstand/hinweisband_test.mjs
//
// Bis 0.4.6 stand der Hinweis nur auf de, en, ru und fa. Weil eine
// ungepruefte Sprache nie eigene Oberflaechentexte hat, las ihn jeder
// auf Englisch -- auch wer Polnisch gewaehlt hatte. Und er bat nicht um
// das, was die Sprache brauchte: jemanden, der die Begriffe prueft.
//
// Geprueft wird mit dem echten Skript aus client.html:
//   * jede waehlbare ungepruefte Sprache hat den Hinweis in sich selbst,
//     ausser Twi (dort Englisch, mit Absicht);
//   * die Bitte um Mithilfe steht da, wenn es eine Rueckmeldeadresse
//     gibt, und fehlt, wenn nicht -- sonst fuehrte sie ins Leere;
//   * der maschinelle Ursprung ist sichtbar vermerkt;
//   * der Streifen auf der Startseite zeigt genau diesen Text.
import vm from "node:vm";
import { readFileSync } from "node:fs";
import { browserBauen, skriptLaden } from "./browsernachbau.mjs";

const SEITE = new URL("../client.html", import.meta.url).pathname;
const CONFIG = new URL("../config.py", import.meta.url).pathname;
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

const umgebung = browserBauen();
skriptLaden(umgebung, SEITE);
const js = (code) => vm.runInContext(code, umgebung);

// Welche Sprachen waehlbar und ungeprueft sind, steht in config.py.
const cfg = readFileSync(CONFIG, "utf8");
const namen = [...cfg.split("SPRACHNAMEN = {")[1].split("}")[0]
  .matchAll(/"([a-z]{2})":/g)].map((m) => m[1]);
const geprueft = [...cfg.match(/^GEPRUEFT = \{([^}]*)\}/m)[1]
  .matchAll(/"([a-z]{2})"/g)].map((m) => m[1]);
const ungeprueft = namen.filter((s) => !geprueft.includes(s));

titel("1) Jede ungepruefte Sprache hat den Hinweis in sich selbst");
const tabelle = js("Object.keys(HINWEIS_UNGEPRUEFT)");
pruefe("ausser Twi fehlt keine", [],
       ungeprueft.filter((s) => s !== "tw" && !tabelle.includes(s)));
pruefe("Twi steht mit Absicht nicht darin (Englisch)", false,
       tabelle.includes("tw"));
pruefe("keine gepruefte Sprache steht darin", [],
       tabelle.filter((s) => geprueft.includes(s)));
for (const s of tabelle) {
  const h = js(`HINWEIS_UNGEPRUEFT[${JSON.stringify(s)}]`);
  pruefe(`${s}: vier Texte, keiner leer`, true,
         ["neu", "ohne", "hilfe", "mt"].every((k) => (h[k] || "").trim()));
  pruefe(`${s}: die Bitte nennt «More» und «Feedback»`, true,
         h.hilfe.includes("«More»") && h.hilfe.includes("«Feedback»"));
  pruefe(`${s}: der uebrige Text traegt keine Knopfnamen`, false,
         /«|»/.test(h.neu + h.ohne));
}
pruefe("de, en, ru, fa haben die Bitte auch", [],
       ["de", "en", "ru", "fa"].filter((s) => !js(`TEXTE.${s}.hilfe`)));

titel("2) Die Bitte nur mit Rueckmeldeadresse");
js(`SPRACHEN.pl = {name:"Polski", kuerzel:"PL", geprueft:false, glossar:true};
    SPRACHEN.it = {name:"Italiano", kuerzel:"IT", geprueft:false, glossar:false};
    SPRACHEN.tw = {name:"Twi", kuerzel:"TW", geprueft:false, glossar:false};`);
js(`rueckmeldungSetzen("", null)`);
const pl = js(`HINWEIS_UNGEPRUEFT.pl`);
pruefe("ohne Adresse: kein Satz zur Mithilfe", false,
       js(`hinweisText("pl","pl")`).includes(pl.hilfe));
js(`rueckmeldungSetzen("betreuer@beispiel.invalid", null)`);
const text = js(`hinweisText("pl","pl")`);
pruefe("mit Adresse: der Satz zur Mithilfe steht da", true,
       text.includes(pl.hilfe));
pruefe("polnisch mit Glossar: der Text fuer 'ungeprueft'", true,
       text.startsWith(pl.neu));
pruefe("und der Vermerk 'maschinell'", true, text.endsWith(`(${pl.mt})`));
const it = js(`HINWEIS_UNGEPRUEFT.it`);
pruefe("italienisch ohne Glossar: der Text fuer 'ohne Verzeichnis'", true,
       js(`hinweisText("it","it")`).startsWith(it.ohne));
const twi = js(`hinweisText("tw","tw")`);
pruefe("Twi: englischer Hinweis ohne Glossar", true,
       twi.startsWith(js("TEXTE.en.keinGlossar")));
pruefe("Twi: mit der englischen Bitte", true,
       twi.includes(js("TEXTE.en.hilfe")));

titel("3) Der Streifen auf der Startseite");
js("startauswahlBauen()");
const wahl = umgebung.document.getElementById("sprachwahl");
const kachel = wahl.kinder.find((k) => k.dataset && k.dataset.code === "pl");
pruefe("die polnische Kachel ist da", true, !!kachel);
if (kachel) {
  kachel.horcher.click[0]();
  const band = umgebung.document.getElementById("neuband");
  pruefe("der Streifen ist sichtbar", false, band.hidden);
  pruefe("er zeigt den polnischen Text", text, band.textContent);
  pruefe("und ist als polnisch ausgezeichnet", "pl", band.lang);
}

console.log();
if (fehler) {
  console.log(`\x1b[31m${fehler} Fehler.\x1b[0m`);
  process.exit(1);
}
console.log("\x1b[32mAlle Faelle wie erwartet.\x1b[0m");
