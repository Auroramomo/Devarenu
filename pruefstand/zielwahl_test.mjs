// Gehen am Pult Zielsprachen verloren, wenn die Quelle wechselt?
//
//     node pruefstand/zielwahl_test.mjs
//
// Gemeldet fuer 0.5.0 (aus dem Code gelesen): die Kachel der gerade
// gesprochenen Sprache ist ausgeblendet, und sprachenSetzen() schickte
// nur die sichtbaren, angehakten Kacheln. Eine Zielsprache, die gerade
// Quelle ist, fiel beim naechsten Haken still heraus:
//
//   1. Quelle de, Ziele en, ru, fa
//   2. Quelle auf ru            -> die ru-Kachel ist weg
//   3. de anhaken              -> gespeichert: en, fa, de
//   4. Quelle zurueck auf de    -> Russisch laeuft nicht mehr
//
// In Rostock hoeren Ukrainer auf Russisch.
//
// Hier laeuft das echte Pult-Skript aus server.py gegen einen kleinen
// nachgebauten Server, der /api/sprachen und /api/sprachwahl so
// beantwortet wie der echte (sprachwahl, versuch_erlaubt,
// Lauf.sprachen_setzen). Was der echte Server mit einer Zielliste macht,
// in der die Quelle steht, prueft sprachen_test.py.
//
// node gibt es nur auf dem Arbeitsrechner.

import { pultBauen, baumBauen } from "./pultnachbau.mjs";

let fehler = 0;
function pruefe(was, erwartet, ist) {
  if (JSON.stringify(erwartet) === JSON.stringify(ist)) {
    console.log(`   ok    ${was}`);
  } else {
    console.log(`   FEHL  ${was}: erwartet ${JSON.stringify(erwartet)}, ` +
                `ist ${JSON.stringify(ist)}`);
    fehler++;
  }
}
function block(t) { console.log(`\n\x1b[1m== ${t}\x1b[0m`); }
const ruhe = () => new Promise((f) => setTimeout(f, 0));

// ------------------------------------------------- der nachgebaute Server
// Auszug aus config.py: genug Sprachen fuer die Faelle, dazu Twi als
// Versuchssprache, die nicht Quelle sein kann.
const SPRACHNAMEN = { de: "Deutsch", en: "Englisch", ru: "Russisch",
                      fa: "Persisch", uk: "Ukrainisch", tw: "Twi (Asante)" };
const NUR_ZIEL = new Set(["tw"]);
const VERSUCHSSPRACHEN = new Set(["tw"]);

function serverBauen({ quelle, ziele, versuch = false }) {
  const s = { quelle, ziele: [...ziele], versuch,
              gespeichert: [...ziele], gesendet: [], getrennt: [] };
  const sprachen = () => [s.quelle, ...s.ziele.filter((z) => z !== s.quelle)];
  const erlaubt = (sp) => !VERSUCHSSPRACHEN.has(sp) || s.versuch
                          || s.ziele.includes(sp);
  s.sprachen = sprachen;
  s.antworten = {
    "/api/sprachen": () => ({
      quelle: s.quelle, ziele: [...s.ziele],
      liste: sprachen().map((sp) => ({ code: sp, name: SPRACHNAMEN[sp],
                                       original: sp === s.quelle })),
      moeglich: Object.keys(SPRACHNAMEN).filter(erlaubt).map((sp) => ({
        code: sp, name: SPRACHNAMEN[sp], stimme: true, geprueft: true,
        glossar: true, quelle: !NUR_ZIEL.has(sp) })),
    }),
    "/api/sprachwahl": (daten) => {
      s.gesendet.push(daten);
      let z = daten.ziele;
      if (Array.isArray(z)) z = z.filter(erlaubt);
      const vorher = new Set(sprachen());
      let q = daten.quelle;
      if (q && NUR_ZIEL.has(q)) q = null;
      if (q) s.quelle = q;
      if (Array.isArray(z)) s.ziele = z.filter((x) => x in SPRACHNAMEN);
      const jetzt = new Set(sprachen());
      const entfallen = [...vorher].filter((x) => !jetzt.has(x)).sort();
      s.getrennt.push(...entfallen);
      s.gespeichert = [...s.ziele];        // zustand.json
      return { quelle: s.quelle, ziele: s.ziele, getrennt: entfallen };
    },
  };
  return s;
}

// ------------------------------------------------- das Pult darum herum
async function pultMit(stand) {
  const server = serverBauen(stand);
  const p = pultBauen();
  await ruhe();                    // der erste sprachenLaden() ist durch
  const { fenster, doc, nachId } = p;
  const vorher = fenster.fetch;
  fenster.fetch = (u, o) => {
    const weg = String(u).split("?")[0];
    if (weg in server.antworten) {
      const daten = o && o.body ? JSON.parse(o.body) : undefined;
      const d = server.antworten[weg](daten);
      return Promise.resolve({ ok: true, status: 200,
                               json: () => Promise.resolve(d) });
    }
    return vorher(u, o);
  };

  // Die Kacheln entstehen ueber innerHTML. Der Nachbau legt dabei keine
  // Kinder an; hier schon, damit das Skript sie wiederfindet.
  const zielwahl = nachId.get("zielwahl");
  Object.defineProperty(zielwahl, "innerHTML", {
    get() { return this._html; },
    set(w) {
      this._html = String(w); this._text = ""; this.kinder = [];
      for (const k of baumBauen(this._html).kinder) this.appendChild(k);
      for (const e of this.alle())
        if (e.tagName === "INPUT") e.checked = "checked" in e.attribute;
    },
  });
  // Und Nachkommen-Auswahl wie "#zielwahl input:checked".
  const waehle = (wahl) => {
    let treffer = [doc.body];
    for (const teil of wahl.trim().split(/\s+/)) {
      const nurAn = teil.endsWith(":checked");
      const kern = teil.replace(/:checked$/, "");
      treffer = [...new Set(treffer.flatMap((e) => [...e.alle()]))]
        .filter((e) => e.passt(kern) && (!nurAn || e.checked));
    }
    return treffer;
  };
  doc.querySelectorAll = (w) => waehle(w);
  doc.querySelector = (w) => waehle(w)[0] ?? null;

  await fenster.sprachenLaden();
  const kacheln = () => [...zielwahl.alle()].filter((e) => e.tagName === "INPUT");
  return {
    server,
    sichtbar: () => kacheln().map((e) => e.value),
    angehakt: () => kacheln().filter((e) => e.checked).map((e) => e.value),
    quellen: () => [...nachId.get("quellwahl").alle()]
      .filter((e) => e.tagName === "OPTION").map((e) => e.attribute.value),
    // Was ein Mensch am Pult tut -- und was der Browser dann aufruft.
    async quelleStellen(sp) {
      nachId.get("quellwahl").value = sp;
      await fenster.sprachenSetzen(); await ruhe();
    },
    async haken(sp, an) {
      const e = kacheln().find((x) => x.value === sp);
      if (!e) throw new Error(`keine Kachel ${sp}`);
      e.checked = an;
      await fenster.sprachenSetzen(); await ruhe();
    },
  };
}

// =====================================================================
block("1) Die vier Schritte aus der Meldung");
{
  const p = await pultMit({ quelle: "de", ziele: ["en", "ru", "fa"] });
  pruefe("Ausgang: Quelle de, Ziele en, ru, fa",
         ["de", ["en", "ru", "fa"]], [p.server.quelle, p.server.gespeichert]);
  await p.quelleStellen("ru");
  pruefe("Quelle ru: die ru-Kachel ist ausgeblendet",
         false, p.sichtbar().includes("ru"));
  pruefe("Quelle ru: de steht leer da",
         [true, false], [p.sichtbar().includes("de"), p.angehakt().includes("de")]);
  pruefe("Quelle ru: gespeichert bleibt en, ru, fa",
         ["en", "ru", "fa"], p.server.gespeichert);
  await p.haken("de", true);
  pruefe("de angehakt: gespeichert en, ru, fa, de",
         ["en", "ru", "fa", "de"], p.server.gespeichert);
  pruefe("dabei laeuft ru nicht als Uebersetzung",
         ["ru", "en", "fa", "de"], p.server.sprachen());
  await p.quelleStellen("de");
  pruefe("Quelle zurueck auf de: gespeichert en, ru, fa, de",
         ["en", "ru", "fa", "de"], p.server.gespeichert);
  pruefe("Russisch laeuft wieder, de nicht doppelt",
         ["de", "en", "ru", "fa"], p.server.sprachen());
  pruefe("die ru-Kachel ist wieder da und angehakt",
         true, p.angehakt().includes("ru"));
  // de-Hoerer schon: zwischen Schritt 2 und 3 lief Deutsch nicht. Das
  // ist richtig so.
  pruefe("die ru-Hoerer wurden nie getrennt",
         false, p.server.getrennt.includes("ru"));
  await p.quelleStellen("ru");
  pruefe("wieder auf ru: de ist angehakt",
         true, p.angehakt().includes("de"));
  pruefe("kein Absenden schickte eine Sprache doppelt", true,
         p.server.gesendet.every((d) => new Set(d.ziele).size === d.ziele.length));
}

block("2) Hin und zurueck, ohne etwas anzuhaken");
{
  const p = await pultMit({ quelle: "de", ziele: ["en", "ru", "fa"] });
  await p.quelleStellen("ru");
  pruefe("auf ru: Ziele unveraendert", ["en", "ru", "fa"], p.server.gespeichert);
  await p.quelleStellen("de");
  pruefe("zurueck auf de: Ziele unveraendert",
         ["en", "ru", "fa"], p.server.gespeichert);
  pruefe("und es laeuft de -> en, ru, fa",
         ["de", "en", "ru", "fa"], p.server.sprachen());
}
{
  // Gegenprobe: die Quelle stand nie in den Zielen.
  const p = await pultMit({ quelle: "de", ziele: ["en", "fa"] });
  await p.quelleStellen("ru");
  await p.quelleStellen("de");
  pruefe("Quelle nicht unter den Zielen: hin und zurueck bleibt en, fa",
         ["en", "fa"], p.server.gespeichert);
}

block("3) Abwaehlen geht weiter, und die Hoerer gehen mit");
{
  const p = await pultMit({ quelle: "de", ziele: ["en", "ru", "fa", "de"] });
  pruefe("Quelle de: keine de-Kachel", false, p.sichtbar().includes("de"));
  await p.haken("fa", false);
  pruefe("fa abgewaehlt, de bleibt gespeichert",
         ["en", "ru", "de"], p.server.gespeichert);
  pruefe("die fa-Hoerer werden getrennt", ["fa"], p.server.getrennt);
  await p.haken("ru", false);
  pruefe("ru abgewaehlt", ["en", "de"], p.server.gespeichert);
  await p.quelleStellen("ru");
  pruefe("auf ru: de ist angehakt, ru steht leer da",
         [true, false], [p.angehakt().includes("de"), p.angehakt().includes("ru")]);
  await p.haken("de", false);
  pruefe("de unter Quelle ru abgewaehlt: weg", ["en"], p.server.gespeichert);
}

block("4) Versuchssprachen und Sprachen, die nicht Quelle sein koennen");
{
  const p = await pultMit({ quelle: "de", ziele: ["en", "tw"] });
  pruefe("Schalter aus, Twi laeuft schon: Kachel da",
         true, p.angehakt().includes("tw"));
  await p.haken("tw", false);
  pruefe("abgewaehlt: Twi ist weg und kommt nicht wieder",
         [["en"], false], [p.server.gespeichert, p.sichtbar().includes("tw")]);
  pruefe("Twi steht nicht in der Quellwahl", false, p.quellen().includes("tw"));
  await p.haken("en", false);
  pruefe("und wird auch beim naechsten Absenden nicht mitgeschickt",
         [], p.server.gespeichert);
}
{
  const p = await pultMit({ quelle: "de", ziele: ["en"], versuch: true });
  await p.haken("tw", true);
  pruefe("Schalter an: Twi laesst sich anhaken", ["en", "tw"], p.server.gespeichert);
}

console.log();
if (fehler) { console.log(`\x1b[31m${fehler} Fehler.\x1b[0m`); process.exit(1); }
console.log("\x1b[32mAlle Faelle wie erwartet.\x1b[0m");
