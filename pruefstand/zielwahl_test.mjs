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
// Seit 0.5.1 (zweiter Schritt) gilt mehr: die gesprochene Sprache steht
// als Kachel da, fest an, mit "Original, ohne Uebersetzung". Wechselt
// die Quelle, bleibt die bisherige als Ziel angewaehlt und wird ab dann
// uebersetzt. Kein Haken springt, nur die Kennzeichnung wandert:
//
//   gesprochen de, Ziele en, ru, fa
//   -> ru:  de an (ru -> de), ru Original, en und fa bleiben
//   -> de:  ru an, de Original
//
// Die Bloecke 1 bis 5 lassen das echte Pult-Skript aus server.py gegen
// einen kleinen nachgebauten Server laufen, der /api/sprachen und
// /api/sprachwahl so beantwortet wie der echte (sprachwahl,
// versuch_erlaubt, Lauf.sprachen_setzen) -- und ein zweites Mal gegen
// einen ohne die neue Regel (beideServer). Block 6 ruft den ECHTEN
// Server (Kopie, --nur-text) am Pult vorbei auf: die Regel muss auch
// dort gelten.
//
// node gibt es nur auf dem Arbeitsrechner.

import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import { pultBauen, baumBauen } from "./pultnachbau.mjs";

let fehler = 0;
let zusatz = "";
function pruefe(was, erwartet, ist) {
  was += zusatz;
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
// Ein Fall, der mit einer Ausnahme abbricht -- etwa weil es eine Kachel
// gar nicht gibt --, zaehlt als ein Fehler; die uebrigen laufen weiter.
async function fall(fn) {
  try { await fn(); }
  catch (e) {
    console.log(`   FEHL  Abbruch: ${e.message}${zusatz}`);
    fehler++;
  }
}
// Die Pult-Faelle laufen zweimal: gegen den nachgebauten Server mit der
// Regel (wie der echte) und gegen einen ohne sie. Im zweiten Lauf muss
// das Pult die Regel allein halten -- wie gegenueber einem Server, der
// noch nicht aktualisiert ist.
async function beideServer(fn) {
  for (const regel of [true, false]) {
    zusatz = regel ? "" : "  [Server ohne Regel]";
    await fall(() => fn(regel));
  }
  zusatz = "";
}

// ------------------------------------------------- der nachgebaute Server
// Auszug aus config.py: genug Sprachen fuer die Faelle, dazu Twi als
// Versuchssprache, die nicht Quelle sein kann.
const SPRACHNAMEN = { de: "Deutsch", en: "Englisch", ru: "Russisch",
                      fa: "Persisch", uk: "Ukrainisch", tw: "Twi (Asante)" };
// Und auf Englisch, fuer das Pult auf EN (0.5.2, config.SPRACHNAMEN_EN).
const SPRACHNAMEN_EN = { de: "German", en: "English", ru: "Russian",
                         fa: "Persian", uk: "Ukrainian", tw: "Twi (Asante)" };
const NUR_ZIEL = new Set(["tw"]);
const VERSUCHSSPRACHEN = new Set(["tw"]);

// regel: false baut den Server von vor 0.5.1 nach -- ohne die Regel,
// dass die bisherige Quelle Ziel bleibt. Damit laesst sich pruefen,
// dass das Pult sie auch allein einhaelt.
// arten: true macht uk ungeprueft (mit Glossar) und Twi zu einer Sprache
// ohne Glossar und ohne Stimme -- damit alle Hinweise unter den Kacheln
// erscheinen. Sonst gelten alle als geprueft, mit Glossar und Stimme.
function serverBauen({ quelle, ziele, versuch = false, regel = true,
                       arten = false }) {
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
                                       name_en: SPRACHNAMEN_EN[sp],
                                       original: sp === s.quelle })),
      moeglich: Object.keys(SPRACHNAMEN).filter(erlaubt).map((sp) => ({
        code: sp, name: SPRACHNAMEN[sp], name_en: SPRACHNAMEN_EN[sp],
        stimme: !(arten && sp === "tw"),
        geprueft: !(arten && (sp === "uk" || sp === "tw")),
        glossar: !(arten && sp === "tw"), quelle: !NUR_ZIEL.has(sp) })),
    }),
    "/api/sprachwahl": (daten) => {
      s.gesendet.push(daten);
      let z = daten.ziele;
      if (Array.isArray(z)) z = z.filter(erlaubt);
      const vorher = new Set(sprachen());
      const alt = s.quelle;
      let q = daten.quelle;
      if (q && NUR_ZIEL.has(q)) q = null;
      if (q) s.quelle = q;
      if (Array.isArray(z)) s.ziele = z.filter((x) => x in SPRACHNAMEN);
      if (regel && s.quelle !== alt && !s.ziele.includes(alt))
        s.ziele.push(alt);
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
        if (e.tagName === "INPUT") {
          e.checked = "checked" in e.attribute;
          e.disabled = "disabled" in e.attribute;
        }
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
  // Der Browser nimmt die Option mit "selected"; der Nachbau nicht.
  nachId.get("quellwahl").value = server.quelle;
  const kacheln =() => [...zielwahl.alle()].filter((e) => e.tagName === "INPUT");
  const kachel = (sp) => kacheln().find((x) => x.value === sp);
  // Das Etikett um eine Kachel, mit Klassen und Text.
  const etikett = (sp) => [...zielwahl.alle()].find((e) => e.tagName === "LABEL"
    && [...e.alle()].some((k) => k.tagName === "INPUT" && k.value === sp));
  return {
    server, fenster,
    // Textknoten legt der Nachbau nicht an; der Wortlaut steht im HTML.
    html: () => zielwahl.innerHTML,
    sichtbar: () => kacheln().map((e) => e.value),
    angehakt: () => kacheln().filter((e) => e.checked).map((e) => e.value),
    kachel, etikett,
    // Welche Kachel traegt die Kennzeichnung "Original"?
    original: () => kacheln().filter((e) => {
      const l = etikett(e.value);
      return l && l.classList.contains("original");
    }).map((e) => e.value),
    quellen: () => [...nachId.get("quellwahl").alle()]
      .filter((e) => e.tagName === "OPTION").map((e) => e.attribute.value),
    // Was ein Mensch am Pult tut -- und was der Browser dann aufruft.
    async quelleStellen(sp) {
      nachId.get("quellwahl").value = sp;
      await fenster.sprachenSetzen(); await ruhe();
    },
    async haken(sp, an) {
      const e = kachel(sp);
      if (!e) throw new Error(`keine Kachel ${sp}`);
      e.checked = an;
      await fenster.sprachenSetzen(); await ruhe();
    },
    // Ein Klick so, wie der Browser ihn behandelt: gesperrt heisst kein
    // Ereignis; onclick="return false" nimmt den Haken zurueck, und
    // change kommt nicht. Sonst kippt der Haken und onchange laeuft.
    async klicken(sp) {
      const e = kachel(sp);
      if (!e) throw new Error(`keine Kachel ${sp}`);
      if (e.disabled) return "gesperrt";
      if (/return\s+false/.test(e.attribute.onclick || "")) return "abgefangen";
      e.checked = !e.checked;
      if (e.attribute.onchange) { await fenster.sprachenSetzen(); await ruhe(); }
      return "geklickt";
    },
  };
}

// =====================================================================
block("1) Rostock: de -> ru -> de, nur die Kennzeichnung wandert");
await beideServer(async (regel) => {
  const p = await pultMit({ quelle: "de", ziele: ["en", "ru", "fa"], regel });
  pruefe("Ausgang: Quelle de, Ziele en, ru, fa",
         ["de", ["en", "ru", "fa"]], [p.server.quelle, p.server.gespeichert]);
  pruefe("die de-Kachel ist zu sehen", true, p.sichtbar().includes("de"));
  pruefe("und als an zu erkennen: Haken und Klasse an",
         [true, true], [p.kachel("de")?.checked,
                        p.etikett("de")?.classList.contains("an")]);
  pruefe("nur de traegt die Kennzeichnung Original", ["de"], p.original());
  pruefe("mit dem Zusatz \"Original, ohne Übersetzung\"", true,
         p.html().includes("Deutsch<span class=originaltag>"
                           + "Original, ohne Übersetzung</span>"));
  pruefe("der Zusatz steht nur einmal da", 1,
         p.html().split("class=originaltag").length - 1);
  pruefe("nicht gesperrt, also nicht grau", false, p.kachel("de")?.disabled);
  pruefe("angehakt: de, en, ru, fa", ["de", "en", "ru", "fa"], p.angehakt());

  await p.quelleStellen("ru");
  pruefe("auf ru: gesprochen ru", "ru", p.server.quelle);
  pruefe("de ist automatisch angewaehlt (ru -> de)",
         true, p.server.gespeichert.includes("de"));
  pruefe("en und fa bleiben", [true, true],
         [p.server.gespeichert.includes("en"), p.server.gespeichert.includes("fa")]);
  pruefe("es laeuft ru -> en, fa, de", ["ru", "en", "fa", "de"],
         p.server.sprachen());
  pruefe("die Kennzeichnung ist zu ru gewandert", ["ru"], p.original());
  pruefe("alle vier Kacheln angehakt", 4, p.angehakt().length);

  await p.quelleStellen("de");
  pruefe("zurueck auf de: ru ist wieder angewaehlt",
         true, p.server.gespeichert.includes("ru"));
  pruefe("es laeuft de -> en, ru, fa", ["de", "en", "ru", "fa"],
         p.server.sprachen());
  pruefe("de ist wieder Original", ["de"], p.original());
  pruefe("die ru-Kachel ist angehakt und kein Original",
         [true, false], [p.angehakt().includes("ru"),
                         p.etikett("ru")?.classList.contains("original")]);
  pruefe("dabei wurde niemand getrennt, auch die de-Hoerer nicht",
         [], p.server.getrennt);
  pruefe("kein Absenden schickte eine Sprache doppelt", true,
         p.server.gesendet.every((d) => new Set(d.ziele).size === d.ziele.length));
  p.fenster.uiSprache(); await ruhe();
  await p.fenster.sprachenLaden();
  // Seit 0.5.2 heisst die Sprache auf EN "German" (Block 8).
  pruefe("Pult auf Englisch: \"Original, not translated\"", true,
         p.html().includes("German<span class=originaltag>"
                           + "Original, not translated</span>"));
  p.fenster.uiSprache(); await ruhe();
});

block("2) Die Originalkachel laesst sich nicht abwaehlen");
await beideServer(async (regel) => {
  const p = await pultMit({ quelle: "de", ziele: ["en", "ru", "fa"], regel });
  pruefe("ein Klick auf de wird abgefangen", "abgefangen", await p.klicken("de"));
  pruefe("de bleibt angehakt", true, p.kachel("de")?.checked);
  pruefe("und es geht nichts an den Server", 0, p.server.gesendet.length);
  pruefe("die anderen Kacheln reagieren wie bisher", "geklickt",
         await p.klicken("fa"));
  pruefe("fa ist abgewaehlt", ["en", "ru"], p.server.gespeichert);
  pruefe("die fa-Hoerer werden getrennt", ["fa"], p.server.getrennt);
  pruefe("de kam dabei nicht in die gespeicherten Ziele",
         false, p.server.gespeichert.includes("de"));
});
await fall(async () => {
  // Das Pult haelt die Regel auch allein, gegen einen Server ohne sie --
  // selbst wenn der Haken der Originalkachel fehlt.
  const p = await pultMit({ quelle: "de", ziele: ["en", "fa"], regel: false });
  const k = p.kachel("de");
  if (k) k.checked = false;
  await p.quelleStellen("ru");
  pruefe("Pult allein: de geht beim Wechsel als Ziel mit",
         ["en", "fa", "de"], p.server.gespeichert);
});

block("3) Die fruehere Originalsprache ist frei abwaehlbar");
await beideServer(async (regel) => {
  const p = await pultMit({ quelle: "de", ziele: ["en", "ru", "fa"], regel });
  await p.quelleStellen("ru");
  await p.haken("de", false);
  pruefe("de unter Quelle ru abgewaehlt: weg",
         false, p.server.gespeichert.includes("de"));
  pruefe("es laeuft ru -> en, fa", ["ru", "en", "fa"], p.server.sprachen());
  pruefe("die de-Hoerer werden getrennt", ["de"], p.server.getrennt);
  pruefe("ru bleibt Original und angehakt",
         [["ru"], true], [p.original(), p.angehakt().includes("ru")]);
  await p.quelleStellen("de");
  pruefe("zurueck auf de: de Original, ru angewaehlt",
         [["de"], true], [p.original(), p.server.gespeichert.includes("ru")]);
  pruefe("es laeuft de -> en, ru, fa", ["de", "en", "ru", "fa"],
         p.server.sprachen());
  await p.haken("ru", false);
  pruefe("und ru laesst sich jetzt abwaehlen", ["de", "en", "fa"],
         p.server.sprachen());
});
await beideServer(async (regel) => {
  // Ohne Haken hin und zurueck: die bisherige Quelle kommt dazu, auch
  // wenn sie vorher nicht unter den Zielen stand.
  const p = await pultMit({ quelle: "de", ziele: ["en", "fa"], regel });
  await p.quelleStellen("ru");
  pruefe("auf ru: de kommt dazu", ["ru", "en", "fa", "de"], p.server.sprachen());
  await p.quelleStellen("de");
  pruefe("zurueck auf de: ru bleibt dabei", ["de", "en", "fa", "ru"],
         p.server.sprachen());
});

block("4) Versuchssprachen und Sprachen, die nicht Quelle sein koennen");
await beideServer(async (regel) => {
  const p = await pultMit({ quelle: "de", ziele: ["en", "tw"], regel });
  pruefe("Schalter aus, Twi laeuft schon: Kachel da",
         true, p.angehakt().includes("tw"));
  pruefe("Twi steht nicht in der Quellwahl", false, p.quellen().includes("tw"));
  await p.quelleStellen("ru");
  pruefe("Wechsel auf ru: Twi bleibt, de kommt dazu",
         ["ru", "en", "tw", "de"], p.server.sprachen());
  await p.quelleStellen("de");
  pruefe("zurueck: Twi bleibt, ru kommt dazu",
         ["de", "en", "tw", "ru"], p.server.sprachen());
  await p.haken("tw", false);
  pruefe("abgewaehlt: Twi ist weg und kommt nicht wieder",
         [false, false], [p.server.sprachen().includes("tw"),
                          p.sichtbar().includes("tw")]);
  await p.quelleStellen("ru");
  pruefe("auch nicht beim naechsten Wechsel",
         false, p.server.sprachen().includes("tw"));
});
await beideServer(async (regel) => {
  const p = await pultMit({ quelle: "de", ziele: ["en"], regel });
  await p.quelleStellen("ru");
  pruefe("Schalter aus, Twi lief nie: der Wechsel bringt es nicht",
         ["ru", "en", "de"], p.server.sprachen());
});
await beideServer(async (regel) => {
  // Twi als Quelle, an der Quellwahl vorbei in das Feld gesetzt: der
  // Server nimmt es nicht. Die Quelle bleibt, also wandert auch nichts.
  const p = await pultMit({ quelle: "de", ziele: ["en", "tw"], regel });
  await p.quelleStellen("tw");
  pruefe("Twi wird nicht Quelle", "de", p.server.quelle);
  pruefe("de bleibt Original, Twi Ziel", [["de"], true],
         [p.original(), p.angehakt().includes("tw")]);
  pruefe("es laeuft weiter de -> en, tw", ["de", "en", "tw"],
         p.server.sprachen());
  pruefe("Twi traegt nie die Kennzeichnung Original",
         false, p.original().includes("tw"));
});
await beideServer(async (regel) => {
  const p = await pultMit({ quelle: "de", ziele: ["en"], versuch: true, regel });
  await p.haken("tw", true);
  pruefe("Schalter an: Twi laesst sich anhaken", ["en", "tw"], p.server.gespeichert);
  await p.quelleStellen("uk");
  pruefe("und bleibt beim Wechsel auf uk", ["uk", "en", "tw", "de"],
         p.server.sprachen());
});

block("5) Die Fehlerkette von 0.5.0 bleibt behoben");
await beideServer(async (regel) => {
  const p = await pultMit({ quelle: "de", ziele: ["en", "ru", "fa"], regel });
  await p.quelleStellen("ru");
  await p.haken("de", true);           // schon an -- aendert nichts
  await p.quelleStellen("de");
  pruefe("Russisch laeuft nach hin, Haken, zurueck",
         ["de", "en", "ru", "fa"], p.server.sprachen());
  pruefe("die ru-Hoerer wurden nie getrennt",
         false, p.server.getrennt.includes("ru"));
});

// =====================================================================
// Der echte Server, am Pult vorbei. Eine Kopie wie in hilfe.arbeitskopie,
// mit eigener zustand.json im Rostocker Stand von 0.5.0 -- unverwandelt.
block("6) Am Pult vorbei: /api/sprachwahl am echten Server");
await fall(async () => {
  const WURZEL = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
  const PORT = 8191;
  const ordner = fs.mkdtempSync(path.join(os.tmpdir(), "devarenu-zielwahl-"));
  const beiwerk = ["client.html", "VERSION", "logo.png", "betreuer.txt"];
  for (const n of fs.readdirSync(WURZEL)) {
    if (n.endsWith(".py") || n.endsWith(".csv") || beiwerk.includes(n))
      fs.copyFileSync(path.join(WURZEL, n), path.join(ordner, n));
  }
  const verknuepft = [".venv", "voices", "models"];
  for (const v of verknuepft)
    if (fs.existsSync(path.join(WURZEL, v)))
      fs.symlinkSync(path.join(WURZEL, v), path.join(ordner, v));
  const zustand = path.join(ordner, "zustand.json");
  fs.writeFileSync(zustand, JSON.stringify(
    { fassung: 3, quelle: "de", ziele: ["en", "ru", "fa"] }));
  fs.chmodSync(zustand, 0o600);

  // Wie hilfe.ollama_umlenken: die Kopie fragt die Attrappe, nicht
  // localhost:11434 -- sonst wartet der Server 90 Sekunden auf Ollama.
  const attrappe = spawn("python3",
    [path.join(WURZEL, "pruefstand/attrappen/ollama_attrappe.py")],
    { stdio: ["ignore", "pipe", "ignore"] });
  const attrappenPort = await new Promise((f) => {
    let roh = "";
    attrappe.stdout.on("data", (b) => {
      roh += b;
      const m = roh.match(/PORT (\d+)/);
      if (m) f(m[1]);
    });
  });
  const cfgDatei = path.join(ordner, "config.py");
  const zeile = 'OLLAMA_URL = "http://localhost:11434"';
  const cfg = fs.readFileSync(cfgDatei, "utf-8");
  if (!cfg.includes(zeile)) throw new Error("config.py: OLLAMA_URL fehlt");
  // Und LLAMA_URL ins Leere (28.10.2026), wie in hilfe.ollama_umlenken:
  // sonst faende die Kopie einen echten llama-server auf diesem Rechner.
  fs.writeFileSync(cfgDatei, cfg.replace(zeile,
    `OLLAMA_URL = "http://127.0.0.1:${attrappenPort}"`)
    .replace('LLAMA_URL = "http://127.0.0.1:8091"',
             'LLAMA_URL = "http://127.0.0.1:9"'));

  let ausgabe = "";
  const kind = spawn(path.join(ordner, ".venv/bin/python"),
    ["server.py", "--port", String(PORT), "--nur-text"],
    { cwd: ordner, stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env, PYTHONUNBUFFERED: "1",
             CUDA_VISIBLE_DEVICES: "" } });
  kind.stdout.on("data", (b) => { ausgabe += b; });
  kind.stderr.on("data", (b) => { ausgabe += b; });
  const url = `http://127.0.0.1:${PORT}`;
  const holen = async () => (await fetch(`${url}/api/sprachen`)).json();
  const waehlen = async (daten) => (await fetch(`${url}/api/sprachwahl`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(daten) })).json();
  const laeuft = (d) => d.liste.map((x) => x.code);
  const gespeichert = () => JSON.parse(fs.readFileSync(zustand, "utf-8"));

  try {
    let bereit = false;
    for (let i = 0; i < 180 && !bereit; i++) {
      try { await holen(); bereit = true; }
      catch { await new Promise((f) => setTimeout(f, 500)); }
    }
    pruefe("der Server antwortet", true, bereit);
    if (bereit) {
      let d = await holen();
      pruefe("zustand.json von 0.5.0 gilt wie sie ist: de -> en, ru, fa",
             ["de", ["en", "ru", "fa"], ["de", "en", "ru", "fa"]],
             [d.quelle, d.ziele, laeuft(d)]);

      // Wie ein altes Pult oder ein Skript: nur die Ziele, die es
      // sieht, ohne de.
      let a = await waehlen({ quelle: "ru", ziele: ["en", "fa"] });
      pruefe("ru mit Zielen en, fa: de kommt trotzdem dazu",
             ["ru", ["en", "fa", "de"]], [a.quelle, a.ziele]);
      pruefe("niemand getrennt, auch de nicht", [], a.getrennt);
      pruefe("so steht es in zustand.json", ["en", "fa", "de"],
             gespeichert().ziele);
      pruefe("im Protokoll steht, dass de bleibt", true,
             ausgabe.includes("de bleibt als Uebersetzung angewaehlt"));

      a = await waehlen({ quelle: "de" });
      d = await holen();
      pruefe("nur die Quelle zurueck auf de: ru kommt dazu",
             ["de", "en", "fa", "ru"], laeuft(d));
      pruefe("de steht genau einmal da, als Original",
             [["de", true]], d.liste.filter((x) => x.code === "de")
               .map((x) => [x.code, x.original]));

      a = await waehlen({ quelle: "de", ziele: ["en"] });
      pruefe("ohne Wechsel bleibt Abwaehlen frei: de -> en",
             [["en"], ["fa", "ru"]], [a.ziele, a.getrennt]);

      a = await waehlen({ quelle: "tw", ziele: ["en"] });
      pruefe("Twi als Quelle: abgelehnt, nichts wandert",
             ["de", ["en"]], [a.quelle, a.ziele]);

      a = await waehlen({ quelle: "ru", ziele: ["en", "tw"] });
      pruefe("Versuchsschalter aus: Twi faellt weg, de kommt dazu",
             ["ru", ["en", "de"]], [a.quelle, a.ziele]);

      a = await waehlen({ quelle: "ru", ziele: ["en"] });
      pruefe("ohne Wechsel laesst sich de wieder abwaehlen",
             [["en"], ["de"]], [a.ziele, a.getrennt]);
    }
  } finally {
    if (kind.exitCode === null && kind.signalCode === null) {
      kind.kill("SIGTERM");
      await new Promise((f) => {
        const t = setTimeout(() => { kind.kill("SIGKILL"); f(); }, 15000);
        kind.on("exit", () => { clearTimeout(t); f(); });
      });
    }
    attrappe.kill("SIGTERM");
    // Wie hilfe.ALARM: bis 0.5.1 sah niemand, was der Server sagte.
    pruefe('der Server meldet kein "Systemcheck fehlgeschlagen"', false,
           ausgabe.includes("Systemcheck fehlgeschlagen"));
    pruefe("und keinen Traceback", false, ausgabe.includes("Traceback"));
    for (const v of verknuepft) {
      try { fs.unlinkSync(path.join(ordner, v)); } catch {}
    }
    fs.rmSync(ordner, { recursive: true, force: true });
  }
});

// =====================================================================
// Gemeldet aus dem Browsertest zu 0.5.1: Pult auf EN umgestellt, unter
// Setup -> Languages blieben Originalzusatz, "nur Text" und die
// Hinweise unter den Kacheln deutsch. uiSprache() zeichnete nur die
// data-t-Felder neu, die Zielwahl blieb in der Sprache des letzten
// sprachenLaden(). Hier wird nur umgeschaltet, nichts von Hand geholt.
block("7) Pult von DE auf EN: die Zielwahl folgt");
await fall(async () => {
  const p = await pultMit({ quelle: "de", ziele: ["en", "uk", "tw"],
                            versuch: true, arten: true });
  const T = vm.runInContext("TEXTE", p.fenster);
  const stuecke = ["original_tag", "glossar_offen_ueber", "kein_glossar_ueber",
                   "ohnestimme_ueber", "ohnestimme_hilfe", "nurtext",
                   "experimentell"];
  const da = (ui) => stuecke.filter((k) => p.html().includes(T[ui][k]));
  pruefe("DE geladen: alle Texte der Zielwahl deutsch", stuecke, da("de"));
  p.fenster.uiSprache();
  for (let i = 0; i < 5; i++) await ruhe();
  pruefe("auf EN umgeschaltet: alle Texte der Zielwahl englisch",
         stuecke, da("en"));
  pruefe("und keiner mehr deutsch", [], da("de"));
  p.fenster.uiSprache();
  for (let i = 0; i < 5; i++) await ruhe();
  pruefe("zurueck auf DE: wieder deutsch", [stuecke, []], [da("de"), da("en")]);
});

// =====================================================================
// 0.5.2: Auf EN heissen die Sprachen am Pult englisch -- in der
// Quellwahl, in den Kacheln und in der Zuhoererzaehlung. Bis 0.5.1
// stand dort "Russisch" unter einer englischen Oberflaeche.
block("8) Pult auf EN: die Sprachen heissen englisch");
await fall(async () => {
  const p = await pultMit({ quelle: "de", ziele: ["en", "ru"] });
  p.server.antworten["/api/zustand"] = () => ({ hoerer: { ru: 3, en: 2 },
                                                gesamt: 5 });
  const quellwahl = () => p.fenster.quellwahl.innerHTML;
  const optionen = () => [...quellwahl().matchAll(/>([^<]+)<\/option>/g)]
    .map((m) => m[1]);
  const zahlen = () => p.fenster.zahlen.innerHTML;
  await p.fenster.lies(); await ruhe();
  // Auf DE in der Reihenfolge des Servers (der Nachbau hier sortiert
  // nicht; der echte nach dem deutschen Namen).
  const DE = ["Deutsch", "Englisch", "Russisch", "Persisch", "Ukrainisch"];
  pruefe("DE: Quellwahl deutsch", DE, optionen());
  pruefe("DE: Kacheln deutsch", true,
         p.html().includes(">Russisch") && !p.html().includes(">Russian"));
  pruefe("DE: Zuhoerer je Sprache deutsch", true,
         zahlen().includes("Russisch") && !zahlen().includes("Russian"));

  p.fenster.uiSprache();
  for (let i = 0; i < 5; i++) await ruhe();
  await p.fenster.lies(); await ruhe();
  pruefe("EN: Quellwahl englisch, nach dem englischen Namen sortiert",
         ["English", "German", "Persian", "Russian", "Ukrainian"], optionen());
  pruefe("EN: Kacheln englisch", true,
         p.html().includes(">Russian") && p.html().includes(">German")
         && !p.html().includes(">Russisch") && !p.html().includes(">Deutsch"));
  pruefe("EN: Zuhoerer je Sprache englisch", true,
         zahlen().includes("Russian") && zahlen().includes("English")
         && !zahlen().includes("Russisch"));

  p.fenster.uiSprache();
  for (let i = 0; i < 5; i++) await ruhe();
  await p.fenster.lies(); await ruhe();
  pruefe("zurueck auf DE: wieder deutsch", DE, optionen());
});

// =====================================================================
// 0.5.2: Nach einem Wechsel der gesprochenen Sprache bleibt die
// bisherige angewaehlt (Regel seit 0.5.1). Das steht jetzt in einer
// Zeile unter den Kacheln, mit "Abwaehlen" -- bis zum naechsten Klick
// in der Sprachwahl.
block("9) Die bisherige Sprache bleibt angewaehlt: eine Zeile darunter");
await fall(async () => {
  const p = await pultMit({ quelle: "de", ziele: ["en"] });
  const hin = p.fenster.bleibthin;
  const zeile = () => (hin.hidden ? "" : hin.innerHTML);
  pruefe("vorher keine Zeile", "", zeile());

  await p.quelleStellen("ru");
  pruefe("de -> ru: de bleibt Ziel", true, p.server.ziele.includes("de"));
  pruefe("und die Zeile sagt es", true,
         zeile().startsWith("Deutsch bleibt angewählt. Nicht mehr gebraucht? "));
  pruefe("mit dem Weg zum Abwaehlen", true,
         zeile().includes('onclick="return abwaehlen()">Abwählen</a>.'));

  // Ein Klick irgendwo in der Sprachwahl: weg.
  p.fenster.zielwahl.ausloesen("click");
  pruefe("der naechste Klick in der Sprachwahl nimmt sie weg", "", zeile());

  // Zurueckstellen -- der Fall, um den es geht: ru bleibt stehen.
  await p.quelleStellen("de");
  pruefe("ru -> de: ru bleibt Ziel", true, p.server.ziele.includes("ru"));
  pruefe("die Zeile nennt ru", true,
         zeile().startsWith("Russisch bleibt angewählt."));

  // Abwaehlen ueber die Zeile selbst.
  pruefe("abwaehlen() wird abgefangen (kein Sprung nach #)", false,
         p.fenster.abwaehlen());
  for (let i = 0; i < 5; i++) await ruhe();
  pruefe("ru ist abgewaehlt", false, p.server.ziele.includes("ru"));
  pruefe("en und de bleiben", ["en", "de"], p.server.ziele);
  pruefe("und die Zeile ist weg", "", zeile());

  // Ein Haken an einer anderen Kachel nimmt sie ebenso weg.
  await p.quelleStellen("ru");
  pruefe("wieder gewechselt: die Zeile steht", true, zeile() !== "");
  p.fenster.zielwahl.ausloesen("click");
  await p.haken("fa", true);
  pruefe("ein Haken an fa: die Zeile ist weg", "", zeile());
});

block("9b) Die Zeile auf EN");
await fall(async () => {
  const p = await pultMit({ quelle: "de", ziele: ["en"] });
  p.fenster.uiSprache();
  for (let i = 0; i < 5; i++) await ruhe();
  await p.quelleStellen("ru");
  const hin = p.fenster.bleibthin;
  pruefe("German stays selected. No longer needed? Deselect.", true,
         !hin.hidden && hin.innerHTML.startsWith(
           "German stays selected. No longer needed? ")
         && hin.innerHTML.includes(">Deselect</a>."));
  p.fenster.uiSprache();
  for (let i = 0; i < 5; i++) await ruhe();
  pruefe("zurueck auf DE: die Zeile wechselt mit", true,
         hin.innerHTML.startsWith("Deutsch bleibt angewählt."));
});

block("8b) Ein Server ohne name_en (vor 0.5.2): das Pult bleibt deutsch");
await fall(async () => {
  const p = await pultMit({ quelle: "de", ziele: ["ru"] });
  const echt = p.server.antworten["/api/sprachen"];
  p.server.antworten["/api/sprachen"] = () => {
    const d = echt();
    for (const x of [...d.liste, ...d.moeglich]) delete x.name_en;
    return d;
  };
  p.fenster.uiSprache();
  for (let i = 0; i < 5; i++) await ruhe();
  pruefe("auf EN ohne name_en: die Namen kommen trotzdem (deutsch)", true,
         p.html().includes(">Russisch"));
  p.fenster.uiSprache();
  for (let i = 0; i < 5; i++) await ruhe();
});

console.log();
if (fehler) { console.log(`\x1b[31m${fehler} Fehler.\x1b[0m`); process.exit(1); }
console.log("\x1b[32mAlle Faelle wie erwartet.\x1b[0m");
