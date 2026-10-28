// Ton-Knopf und "Dunkler" auf der Hoererseite: beide zeigen die
// HANDLUNG, nicht den Zustand (0.5.2).
//
//     node pruefstand/tonknopf_test.mjs
//
// Bis 0.5.1 stand am Ton-Knopf "Ton", solange Ton lief, und "Ton aus",
// wenn er aus war -- der Zustand. Daneben sagte "Dunkler" schon, was der
// naechste Druck bringt. Zwei Logiken nebeneinander in einer Leiste:
// wer "Ton aus" las, hielt es fuer den Knopf zum Abschalten und
// drueckte -- und bekam den Ton zurueck.
//
// Jetzt sagen beide, was ein Druck tut. Das aria-pressed bleibt beim
// Zustand; es ist fuer die Vorlesefunktion und sagt "gedrueckt".
// Geprueft in allen Sprachen, die eigene Oberflaechentexte haben, und
// in einer ohne (sie faellt auf Englisch zurueck).

import { browserBauen, skriptLaden } from "./browsernachbau.mjs";

const SEITE = new URL("../client.html", import.meta.url).pathname;
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
  umgebung.localStorage = { getItem: () => null, setItem() {}, removeItem() {} };
  umgebung.URLSearchParams = URLSearchParams;
  const p = skriptLaden(umgebung, SEITE);
  return { ...p, umgebung };
}

// Was der Knopf sagen muss: [Ton laeuft, Ton ist aus].
const TON = {
  de: ["Ton aus", "Ton an"],
  en: ["Sound off", "Sound on"],
  ru: ["Выкл. звук", "Вкл. звук"],
  fa: ["صدا خاموش", "صدا روشن"],
  pl: ["Sound off", "Sound on"],     // ohne eigene Texte: Englisch
};

titel("1) Der Ton-Knopf sagt, was ein Druck tut");
{
  const { umgebung, zustand, TEXTE } = laden();
  const knopf = umgebung.document.getElementById("w-ton");
  const schrift = () => knopf.querySelector(".beschriftung").textContent;
  pruefe("eigene Texte haben genau de, en, ru, fa",
         ["de", "en", "fa", "ru"], Object.keys(TEXTE).sort());
  for (const [sp, [an, aus]] of Object.entries(TON)) {
    zustand.sprache = sp;
    umgebung.tonSchalten(true);
    pruefe(`${sp}: Ton laeuft -> "${an}"`, an, schrift());
    pruefe(`${sp}:   und gilt als gedrueckt`, "true",
           knopf.getAttribute("aria-pressed"));
    umgebung.tonSchalten(false);
    pruefe(`${sp}: Ton aus -> "${aus}"`, aus, schrift());
    pruefe(`${sp}:   und gilt als nicht gedrueckt`, "false",
           knopf.getAttribute("aria-pressed"));
  }
}

titel("2) \"Dunkler\" nach derselben Logik");
{
  const { umgebung, zustand, Dunkel, TEXTE } = laden();
  const knopf = umgebung.document.getElementById("w-dunkel");
  const schrift = () => knopf.querySelector(".beschriftung").textContent;
  for (const sp of ["de", "en", "ru", "fa"]) {
    zustand.sprache = sp;
    // Bei jeder Stufe: was dasteht, bringt der naechste Druck.
    for (const stufe of [0, 1, 2]) {
      Dunkel.setzen(stufe);
      const steht = schrift();
      const naechste = (stufe + 1) % Dunkel.STUFEN;
      const erwartet = naechste > stufe ? TEXTE[sp].dunkel : TEXTE[sp].heller;
      pruefe(`${sp}: Stufe ${stufe} -> "${steht}" (naechster Druck: Stufe ${naechste})`,
             erwartet, steht);
      pruefe(`${sp}:   aria-pressed folgt dem Zustand`, String(stufe > 0),
             knopf.getAttribute("aria-pressed"));
    }
  }
}

// Der Text-Knopf (28.10.2026): bis dahin "Text" bei sichtbarem Text und
// "Text aus" bei verborgenem -- der Zustand, wie vorher beim Ton.
const TEXT = {
  de: ["Text aus", "Text an"],
  en: ["Text off", "Text on"],
  ru: ["Выкл. текст", "Вкл. текст"],
  fa: ["متن خاموش", "متن روشن"],
  pl: ["Text off", "Text on"],       // ohne eigene Texte: Englisch
};

titel("2b) Der Text-Knopf sagt, was ein Druck tut");
{
  const { umgebung, zustand } = laden();
  const element = umgebung.document.getElementById("w-text");
  // Der Nachbau kennt kein click(); gedrueckt wird ueber die Horcher.
  const knopf = {
    click: () => (element.horcher.click || []).forEach((f) => f()),
    getAttribute: (n) => element.getAttribute(n),
  };
  const schrift = () => element.querySelector(".beschriftung").textContent;
  for (const [sp, [sichtbar, verborgen]] of Object.entries(TEXT)) {
    zustand.sprache = sp;
    // Zweimal druecken: danach ist der Text sichtbar und aria-pressed
    // vom Handler gesetzt, gleich in welchem Zustand der Fall begann.
    knopf.click(); knopf.click();
    if (!zustand.textAn) knopf.click();
    pruefe(`${sp}: Text sichtbar -> "${sichtbar}"`, sichtbar, schrift());
    pruefe(`${sp}:   und gilt als gedrueckt`, "true",
           knopf.getAttribute("aria-pressed"));
    knopf.click();
    pruefe(`${sp}: Text verborgen -> "${verborgen}"`, verborgen, schrift());
    pruefe(`${sp}:   und gilt als nicht gedrueckt`, "false",
           knopf.getAttribute("aria-pressed"));
    knopf.click();
    pruefe(`${sp}: ein zweiter Druck holt ihn zurueck`, sichtbar, schrift());
  }
}

titel("3) Beide in einem Satz: der Text ist die Handlung");
{
  const { umgebung, zustand, TEXTE } = laden();
  zustand.sprache = "de";
  umgebung.tonSchalten(true);
  const ton = umgebung.document.getElementById("w-ton")
    .querySelector(".beschriftung").textContent;
  pruefe("Ton an, der Knopf bietet das Abschalten an", "Ton aus", ton);
  pruefe("und das Wort dafuer steht in TEXTE.de", true,
         Object.values(TEXTE.de).includes(ton));
}

console.log();
if (fehler) { console.log(`${fehler} FEHLER`); process.exit(1); }
console.log("Alle Faelle wie erwartet.");
