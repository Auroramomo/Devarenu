// Ein nachgebauter Browser fuer die Zuhoererseite.
//
// Gemeinsam genutzt von sprachwechsel_test.mjs und
// verbindung_test.mjs. Zwei Kopien waeren zwei Baustellen: wer eine
// Luecke im einen schliesst, laesst sie im anderen stehen -- und ein
// Prueflauf, dem eine DOM-Methode fehlt, meldet einen Fehler im
// Programm, wo keiner ist.
//
// Nur so viel Browser, wie das Skript anfasst. Was fehlt, faellt beim
// Laden sofort auf.
import { readFileSync } from "node:fs";
import vm from "node:vm";

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



/** Laedt das <script> aus client.html in den Nachbau.
 *
 *  "const zustand = ..." landet im lexikalischen Bereich des
 *  Kontexts, nicht am globalen Objekt -- von aussen also unsichtbar.
 *  Ein zweiter Lauf IM SELBEN Kontext reicht die Namen heraus. */
export function skriptLaden(umgebung, pfad) {
  const html = readFileSync(pfad, "utf8");
  const stuecke = [...html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g)]
    .map((m) => m[1]);
  if (!stuecke.length) throw new Error("kein <script> in " + pfad);
  vm.createContext(umgebung);
  vm.runInContext(stuecke.join("\n;\n"), umgebung, { filename: pfad });
  vm.runInContext(
    "globalThis.__pruef = {zustand, Verbindung, Ton, spracheWechseln, " +
    "SPRACHEN, zustandZeigen, TEXTE};", umgebung);
  return umgebung.__pruef;
}

export { browserBauen };
