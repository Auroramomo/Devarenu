// Ein nachgebauter Browser fuer das Pult.
//
// Anders als browsernachbau.mjs (Zuhoererseite) braucht das Pult einen
// echten Baum: es greift Elemente ueber ihre Kennung als globale Namen
// an -- so, wie es jeder Browser anbietet -- und fragt Teilbaeume mit
// querySelector ab. Ein Nachbau, der jede Anfrage mit einem frischen
// leeren Element beantwortet, bestaetigt jede Behauptung und findet
// nichts.
//
// Deshalb steht hier ein kleiner Parser. Er kann genau so viel, wie die
// Vorlage im Server braucht: Kennungen, Klassen, data-t, hidden, und
// wer in wem steckt.

import { readFileSync } from "node:fs";
import vm from "node:vm";

const LEER = new Set(["img", "input", "br", "hr", "meta", "link", "source"]);

export class Element {
  constructor(tag = "div", attribute = {}) {
    this.tagName = tag.toUpperCase();
    this.attribute = attribute;
    this.kinder = [];
    this.eltern = null;
    this.dataset = {};
    this.style = new Proxy({}, {get:(z,k)=>z[k]??"", set:(z,k,w)=>{z[k]=w;return true}});
    this.horcher = {};
    this._text = "";
    this._html = "";
    const k = new Set(String(attribute.class || "").split(/\s+/).filter(Boolean));
    this.classList = {
      _: k,
      add: (...x) => x.forEach(y => k.add(y)),
      remove: (...x) => x.forEach(y => k.delete(y)),
      toggle: (x, an) => { if (an === undefined) an = !k.has(x);
                           an ? k.add(x) : k.delete(x); return an; },
      contains: (x) => k.has(x),
    };
    for (const [n, w] of Object.entries(attribute)) {
      if (n.startsWith("data-")) this.dataset[n.slice(5)] = w;
    }
    this._hidden = "hidden" in attribute;
    this.value = attribute.value ?? "";
    this.checked = false;
    this.disabled = false;
    this.open = "open" in attribute;
  }
  get id() { return this.attribute.id || ""; }
  // title ist im Browser Eigenschaft UND Attribut. Ein Nachbau, der
  // nur die Eigenschaft kennt, laesst getAttribute("title") ins Leere
  // laufen -- und ein Pruefstand, der dort null findet, meldet einen
  // Fehler, den es nicht gibt.
  get title() { return this.attribute.title || ""; }
  set title(w) { this.attribute.title = String(w); }
  get hidden() { return this._hidden; }
  set hidden(w) { this._hidden = !!w; }
  get className() { return [...this.classList._].join(" "); }
  set className(w) {
    this.classList._.clear();
    String(w).split(/\s+/).filter(Boolean).forEach(x => this.classList._.add(x));
  }
  get textContent() { return this._text || this.volltext(); }
  set textContent(w) { this._text = String(w); this.kinder = []; this._html = ""; }
  get innerHTML() { return this._html; }
  set innerHTML(w) { this._html = String(w); this.kinder = []; this._text = ""; }
  setAttribute(n, w) { this.attribute[n] = String(w); }
  getAttribute(n) { return this.attribute[n] ?? null; }
  removeAttribute(n) { delete this.attribute[n]; }
  addEventListener(n, f) { (this.horcher[n] ||= []).push(f); }
  ausloesen(n, e = {}) { (this.horcher[n] || []).forEach(f => f.call(this, e)); }
  appendChild(k) { k.eltern = this; this.kinder.push(k); return k; }
  append(...k) { k.forEach(x => this.appendChild(x)); }
  remove() {}
  scrollIntoView() {}
  focus() { this.fokussiert = true; }
  showModal() { this.offen = true; }
  close() { this.offen = false; }
  // --- Suche ---
  *alle() { for (const k of this.kinder) { yield k; yield* k.alle(); } }
  passt(wahl) {
    wahl = wahl.trim();
    let m;
    if ((m = wahl.match(/^\[data-t=([^\]]+)\]$/)))
      return this.dataset.t === m[1].replace(/^["']|["']$/g, "");
    if ((m = wahl.match(/^#(.+)$/))) return this.id === m[1];
    if ((m = wahl.match(/^\.(.+)$/))) return this.classList.contains(m[1]);
    if (wahl === "[data-t]") return this.dataset.t !== undefined;
    return this.tagName === wahl.toUpperCase();
  }
  querySelector(wahl) { for (const k of this.alle()) if (k.passt(wahl)) return k; return null; }
  querySelectorAll(wahl) { return [...this.alle()].filter(k => k.passt(wahl)); }
  // Wo stecke ich drin?
  vorfahren() { const w = []; let e = this.eltern; while (e) { w.push(e); e = e.eltern; } return w; }
  // Sichtbar heisst: weder ich noch ein Vorfahr ist versteckt.
  sichtbar() { return !this.hidden && this.vorfahren().every(e => !e.hidden); }
  volltext() {
    let t = this._text + (this._html ? " " + this._html.replace(/<[^>]*>/g, " ") : "");
    for (const k of this.kinder) t += " " + k.volltext();
    return t;
  }
}

export function baumBauen(html) {
  const wurzel = new Element("body");
  const stapel = [wurzel];
  const marke = /<!--[\s\S]*?-->|<\/([a-zA-Z][\w-]*)\s*>|<([a-zA-Z][\w-]*)((?:\s+[^<>"']+(?:=(?:"[^"]*"|'[^']*'|[^\s<>]+))?)*)\s*\/?>/g;
  let m;
  while ((m = marke.exec(html))) {
    if (m[0].startsWith("<!--")) continue;
    if (m[1]) {                               // schliessend
      if (stapel.length > 1) stapel.pop();
      continue;
    }
    const tag = m[2].toLowerCase();
    const attribute = {};
    const ra = /([\w:-]+)(?:=(?:"([^"]*)"|'([^']*)'|([^\s<>]+)))?/g;
    let a;
    while ((a = ra.exec(m[3] || ""))) attribute[a[1]] = a[2] ?? a[3] ?? a[4] ?? "";
    const e = new Element(tag, attribute);
    stapel[stapel.length - 1].appendChild(e);
    if (!LEER.has(tag) && !m[0].endsWith("/>")) stapel.push(e);
  }
  return wurzel;
}

export function pultLesen(pfad) {
  const quelle = readFileSync(pfad, "utf8");
  const pult = quelle.split('PULT = """')[1].split('"""')[0];
  const i = pult.indexOf("<script>");
  return { koerper: pult.slice(0, i),
           skript: pult.slice(i + 8).replace(/<\/script>[\s\S]*$/, "") };
}

export function pultBauen({ zustand, pegel, extra = {} } = {}) {
  const { koerper, skript } = pultLesen(
    new URL("../server.py", import.meta.url).pathname);
  const wurzel = baumBauen(koerper);
  const nachId = new Map();
  for (const e of wurzel.alle()) if (e.id) nachId.set(e.id, e);

  const html = new Element("html");
  const body = new Element("body");
  body.kinder = wurzel.kinder;
  for (const k of body.kinder) k.eltern = body;

  const doc = {
    getElementById: (id) => nachId.get(id) ?? null,
    querySelector: (w) => body.querySelector(w),
    querySelectorAll: (w) => body.querySelectorAll(w),
    createElement: (t) => new Element(t),
    addEventListener(n, f) { (this.horcher ||= {})[n] ||= []; this.horcher[n].push(f); },
    documentElement: html,
    body,
    activeElement: null,
  };

  const schmal = { matches: extra.schmal ?? false, addEventListener() {} };
  const antworten = {
    "/api/zustand": zustand ?? {},
    "/api/pegel": pegel ?? {},
    "/api/sprachen": { liste: [], moeglich: [], quelle: "de", ziele: [] },
    "/api/aufnahmen": { liste: [], tage: 7 },
    "/api/wlan": { ssid: "", passwort: "" },
    "/api/update": {},
    "/api/tonscan": { aktiv: false },
    "/api/betreuer": { name: "", mail: "", bericht_link: "" },
  };
  const gerufen = [];
  const fenster = {
    document: doc,
    location: { hash: extra.hash ?? "", href: "http://10.0.0.1/", protocol: "http:" },
    history: { replaceState() {} },
    localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
    matchMedia: () => schmal,
    setTimeout, clearTimeout, setInterval: () => 0, clearInterval,
    queueMicrotask, console, JSON, Math, Object, String, Number, Array, Date,
    URLSearchParams, URL, Promise, parseInt, parseFloat, isNaN,
    FormData: function () { this.append = () => {}; },
    confirm: () => (extra.confirm ?? true),
    alert: () => {},
    fetch: (u, o) => {
      gerufen.push({ url: String(u), optionen: o });
      const schluessel = Object.keys(antworten)
        .find(k => String(u).startsWith(k));
      const d = schluessel ? antworten[schluessel] : {};
      return Promise.resolve({ ok: true, status: 200,
                               json: () => Promise.resolve(d) });
    },
  };
  fenster.addEventListener = function (n, f) {
    (fenster.horcher ||= {})[n] ||= []; fenster.horcher[n].push(f);
  };
  fenster.window = fenster;
  fenster.globalThis = fenster;
  // Was ein Browser von selbst anbietet: jede Kennung ist ein Name.
  for (const [id, e] of nachId) if (!(id in fenster)) fenster[id] = e;

  const zusammenhang = vm.createContext(fenster);
  vm.runInContext(skript, zusammenhang, { filename: "pult.js" });
  return { fenster, doc, body, nachId, gerufen, schmal, koerper };
}
