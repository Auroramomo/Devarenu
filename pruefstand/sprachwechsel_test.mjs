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

// ---------------------------------------------------------- Nachbau
// Nur so viel Browser, wie das Skript anfasst. Ein vollstaendiges DOM
// waere eine zweite Baustelle; was fehlt, faellt beim Laden sofort auf.
function browserBauen() {
  const offeneDraehte = [];

  class Element {
    constructor(tag = "div") {
      this.tagName = tag.toUpperCase();
      this.kinder = [];
      this.style = { cssText: "", setProperty() {} };
      this.dataset = {};
      this.classList = {
        _: new Set(),
        add(...k) { k.forEach((x) => this._.add(x)); },
        remove(...k) { k.forEach((x) => this._.delete(x)); },
        toggle(k, an) { an ? this._.add(k) : this._.delete(k); },
        contains(k) { return this._.has(k); },
      };
      this._text = "";
      this._html = "";
      this.attribute = {};
      this.horcher = {};
    }
    get textContent() { return this._text; }
    set textContent(v) { this._text = String(v); this.kinder = []; }
    get innerHTML() { return this._html; }
    set innerHTML(v) { this._html = String(v); this.kinder = []; }
    append(...k) { this.kinder.push(...k); }
    appendChild(k) { this.kinder.push(k); return k; }
    get firstChild() { return this.kinder[0] ?? null; }
    get lastChild() { return this.kinder[this.kinder.length - 1] ?? null; }
    get children() { return this.kinder; }
    removeChild(k) {
      const i = this.kinder.indexOf(k);
      if (i >= 0) this.kinder.splice(i, 1);
      return k;
    }
    remove() {}
    setAttribute(n, w) { this.attribute[n] = String(w); }
    getAttribute(n) { return this.attribute[n] ?? null; }
    removeAttribute(n) { delete this.attribute[n]; }
    addEventListener(n, f) { (this.horcher[n] ||= []).push(f); }
    // Ein Kindelement je Wahlspruch, dauerhaft: das Skript setzt
    // Beschriftungen ueber querySelector, und ein null dort waere ein
    // Absturz im Nachbau, nicht im Programm.
    querySelector(wahl) {
      this._gefunden ||= {};
      return (this._gefunden[wahl] ||= new Element("span"));
    }
    querySelectorAll() { return []; }
    closest() { return null; }
    scrollIntoView() {}
    focus() {}
    showModal() { this.offen = true; }
    close() { this.offen = false; }
    play() { return Promise.resolve(); }
    pause() {}
    // Alles, was im Baum an Text haengt. Der Abschnitt baut eine
    // <article> mit Kindern; nur deren eigenen Text zu lesen faende
    // NIE etwas -- und ein Test, der nie etwas findet, bestaetigt
    // jede Behauptung.
    volltext() {
      let t = this._text;
      if (this._html) t += " " + this._html;
      for (const k of this.kinder) t += " " + (k.volltext ? k.volltext() : "");
      return t;
    }
  }

  const bekannt = new Map();
  const doc = {
    createElement: (t) => new Element(t),
    getElementById(id) {
      if (!bekannt.has(id)) bekannt.set(id, new Element("div"));
      return bekannt.get(id);
    },
    _gefunden: {},
    querySelector(wahl) {
      return (this._gefunden[wahl] ||= new Element("span"));
    },
    querySelectorAll: () => [],
    addEventListener() {},
    documentElement: new Element("html"),
    body: new Element("body"),
    hidden: false,
    visibilityState: "visible",
  };

  class WS {
    static OPEN = 1;
    constructor(url) {
      this.url = url;
      this.readyState = WS.OPEN;
      this.geschlossen = false;
      offeneDraehte.push(this);
      queueMicrotask(() => this.onopen && this.onopen());
    }
    close() { this.geschlossen = true; this.readyState = 3; }
    send() {}
    // Was der Server schickt. Absichtlich OHNE Ruecksicht darauf, ob
    // jemand zugehoert hat: genau so verhaelt sich ein Draht, dessen
    // close() noch nicht durch ist.
    liefern(d) { this.onmessage && this.onmessage({ data: JSON.stringify(d) }); }
  }

  const fenster = {
    document: doc,
    location: { protocol: "http:", host: "10.0.0.1", hash: "", search: "" },
    navigator: {
      language: "de", languages: ["de"], userAgent: "pruefstand",
      wakeLock: undefined,
      mediaSession: { metadata: null, playbackState: "none",
                      setActionHandler() {} },
    },
    WebSocket: WS,
    Audio: function () { return new Element("audio"); },
    AudioContext: undefined,
    localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
    fetch: () => Promise.reject(new Error("kein Netz im Pruefstand")),
    setTimeout, clearTimeout, setInterval, clearInterval,
    queueMicrotask, console,
    matchMedia: () => ({ matches: false, addEventListener() {} }),
    requestAnimationFrame: (f) => setTimeout(f, 0),
    MediaMetadata: function (x) { Object.assign(this, x); },
    offeneDraehte,
  };
  fenster.URLSearchParams = URLSearchParams;
  fenster.URL = URL;
  fenster.JSON = JSON;
  fenster.Date = Date;
  fenster.Math = Math;
  fenster.Promise = Promise;
  fenster.Intl = Intl;
  fenster.performance = performance;
  fenster.addEventListener = () => {};
  fenster.removeEventListener = () => {};
  fenster.dispatchEvent = () => true;
  fenster.window = fenster;
  fenster.self = fenster;
  fenster.globalThis = fenster;
  return fenster;
}

// Das Skript aus client.html -- die echte Datei, nicht eine Kopie.
function skriptHolen() {
  const html = readFileSync(join(WURZEL, "client.html"), "utf8");
  const stuecke = [...html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g)]
    .map((m) => m[1]);
  if (!stuecke.length) throw new Error("kein <script> in client.html");
  return stuecke.join("\n;\n");
}

const umgebung = browserBauen();
vm.createContext(umgebung);
try {
  vm.runInContext(skriptHolen(), umgebung, { filename: "client.html" });
} catch (e) {
  console.log(`   FEHL  client.html liess sich nicht laden: ${e.message}`);
  process.exit(1);
}
// "const zustand = ..." landet im lexikalischen Bereich des Kontexts,
// nicht am globalen Objekt -- von aussen also unsichtbar. Ein zweiter
// Lauf IM SELBEN Kontext reicht sie heraus.
vm.runInContext(
  "globalThis.__pruef = {zustand, Verbindung, Ton, spracheWechseln, SPRACHEN};",
  umgebung);

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
