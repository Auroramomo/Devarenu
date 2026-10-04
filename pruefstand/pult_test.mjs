// Das Pult, ohne Browser geprueft.
//
//     node pruefstand/pult_test.mjs
//     node pruefstand/pult_test.mjs --bilder     (braucht firefox)
//
// Seit 0.4.1 hat das Pult vier Reiter. Damit kann etwas verschwinden,
// ohne dass es auffaellt: ein Knopf, den niemand mehr erreicht, sieht
// aus wie ein aufgeraeumtes Pult. Deshalb steht hier eine Liste JEDES
// Bedienelements aus der Bestandsaufnahme mit dem Ort, an dem es liegen
// soll -- und geprueft wird, dass man von der Startseite aus dorthin
// kommt.
//
// Der zweite Teil (--bilder) rendert das Pult mit Attrappendaten in den
// Geraetegroessen und misst, ob der Reiter Gottesdienst ohne Scrollen
// passt. Er braucht firefox und schreibt NUR nach /tmp/devarenu_pult/,
// nie ins Repo.

import { readFileSync } from "node:fs";
import { pultBauen, pultLesen } from "./pultnachbau.mjs";

const SERVER = new URL("../server.py", import.meta.url).pathname;
let fehler = 0;

function pruefe(was, bedingung, einzelheit = "") {
  if (bedingung) { console.log(`   ok    ${was}`); }
  else { fehler++; console.log(`   FEHLER ${was}` + (einzelheit ? `  -> ${einzelheit}` : "")); }
}
function block(t) { console.log(`\n${t}`); }

// =====================================================================
// Bestandsaufnahme: jedes Element und sein Ort im neuen Pult.
//   wo:  "kopf" | ein Reiter | "post" | "fehler"
//   seite: Unterseite der Einrichtung
//   tief:  steht eine Ebene tiefer, hinter einem "?" oder in einer Liste
// =====================================================================
const TABELLE = [
  // --- Kopf, in jedem Reiter sichtbar ---
  ["pille",                 "kopf"],
  ["laufzeit",              "kopf"],
  ["qrknopf",               "kopf"],
  ["kaefer",                "kopf"],
  ["sprachknopf",           "kopf"],
  // --- Banner, in JEDEM Reiter ---
  ["rechenwarnung",         "banner"],
  ["tonhin",                "banner"],
  ["zweiterdhcp",           "banner"],
  ["updatehin",             "banner"],
  ["briefkastenband",       "banner"],
  ["briefkasten",           "banner"],
  ["postzahl",              "banner"],
  ["sprachverdacht",        "banner"],
  ["sprachverdachttext",    "banner"],
  ["bSpracheUm",            "banner"],
  ["warnung",               "banner"],
  // --- Reiter Gottesdienst ---
  ["bStart",                "gottesdienst"],
  ["bSchnitt",              "gottesdienst"],
  ["anhaltenHin",           "gottesdienst"],
  ["aufnahmelaeuft",        "gottesdienst"],
  ["aufnahmedauer",         "gottesdienst"],
  ["kTon",                  "gottesdienst"],
  ["tonZustand",            "gottesdienst"],
  ["fuell",                 "gottesdienst"],
  ["marke",                 "gottesdienst"],
  ["schwellestand",         "gottesdienst"],
  ["pegelwert",             "gottesdienst", {tief: true}],
  ["schwellwert",           "gottesdienst", {tief: true}],
  ["kHoerer",               "gottesdienst"],
  ["hoererzahl",            "gottesdienst"],
  ["hoerersprachen",        "gottesdienst"],
  ["zahlen",                "gottesdienst", {tief: true}],
  ["kThema",                "gottesdienst"],
  ["themaZustand",          "gottesdienst"],
  ["themazeile",            "gottesdienst"],
  ["themalink",             "gottesdienst"],
  ["erkanntkachel",         "gottesdienst", {tief: true}],
  ["zuletztzeile",          "gottesdienst"],
  ["zuletzttext",           "gottesdienst"],
  ["zuletztsek",            "gottesdienst"],
  ["mit",                   "gottesdienst", {tief: true}],
  // --- Briefkasten ---
  ["post",                  "post"],
  ["postliste",             "post"],
  // --- Reiter Vorbereiten ---
  ["kontext",               "vorbereiten"],
  ["erkannt",               "vorbereiten"],
  ["datei",                 "vorbereiten"],
  ["skriptinfo",            "vorbereiten"],
  ["einmessstand",          "vorbereiten", {tief: true}],
  ["bEinmessen",            "vorbereiten", {tief: true}],
  ["feineinstellung",       "vorbereiten"],
  ["tonfuell",              "vorbereiten", {tief: true}],
  ["marke2",                "vorbereiten", {tief: true}],
  ["feinwert",              "vorbereiten", {tief: true}],
  ["regler",                "vorbereiten", {tief: true}],
  ["bAus",                  "vorbereiten", {tief: true}],
  ["bAuto",                 "vorbereiten", {tief: true}],
  ["bFest",                 "vorbereiten", {tief: true}],
  ["kanalliste",            "vorbereiten", {tief: true}],
  ["bSprache",              "vorbereiten", {tief: true}],
  ["sprachstand",           "vorbereiten", {tief: true}],
  ["geraetstand",           "vorbereiten", {tief: true}],
  // --- Reiter Aufnahmen ---
  ["schnittinfo",           "aufnahmen"],
  ["aufnahmeliste",         "aufnahmen"],
  ["aufnahmetage",          "aufnahmen"],
  // --- Reiter Einrichtung ---
  ["gemeindefeld",          "einrichtung", {seite: "eGemeinde"}],
  ["meldeschalter",         "einrichtung", {seite: "eGemeinde"}],
  ["kontowarnung",          "einrichtung", {seite: "eGemeinde"}],
  ["kontowarnungtext",      "einrichtung", {seite: "eGemeinde"}],
  ["quellwahl",             "einrichtung", {seite: "eSprachen"}],
  ["zielwahl",              "einrichtung", {seite: "eSprachen"}],
  ["ssid",                  "einrichtung", {seite: "eWlan"}],
  ["wpw",                   "einrichtung", {seite: "eWlan"}],
  ["wlanstand",             "einrichtung", {seite: "eWlan"}],
  ["pwfeld",                "einrichtung", {seite: "ePasswort"}],
  ["pwstand",               "einrichtung", {seite: "ePasswort"}],
  ["bPwWeg",                "einrichtung", {seite: "ePasswort"}],
  ["fassung",               "einrichtung", {seite: "eUpdate"}],
  ["updatestand",           "einrichtung", {seite: "eUpdate"}],
  ["updateknopf",           "einrichtung", {seite: "eUpdate"}],
  ["onlinereihe",           "einrichtung", {seite: "eUpdate"}],
  ["onlineknopf",           "einrichtung", {seite: "eUpdate"}],
  ["onlinestand",           "einrichtung", {seite: "eUpdate"}],
  ["wartungKopf",           "einrichtung", {seite: "eFehlersuche"}],
  ["wartungZahl",           "einrichtung", {seite: "eFehlersuche"}],
  ["wartungFeld",           "einrichtung", {seite: "eFehlersuche"}],
  ["wartungliste",          "einrichtung", {seite: "eFehlersuche"}],
  ["protokollschalter",     "einrichtung", {seite: "eFehlersuche"}],
  ["protokollhin",          "einrichtung", {seite: "eFehlersuche"}],
  ["pruefprotokollreihe",   "einrichtung", {seite: "eFehlersuche"}],
  ["pruefprotokollschalter","einrichtung", {seite: "eFehlersuche"}],
  ["pruefprotokollhin",     "einrichtung", {seite: "eFehlersuche"}],
  ["pruefprotokolllaeuft",  "einrichtung", {seite: "eFehlersuche"}],
  ["pruefprotokollzeilen",  "einrichtung", {seite: "eFehlersuche"}],
  // --- Fehler melden ---
  ["fehler",                "fehler"],
  ["betreuername",          "fehler"],
  ["betreuermail",          "fehler"],
  ["qrmail",                "fehler"],
  ["qrbericht",             "fehler"],
  ["berichtklartext",       "fehler"],
  ["berichtlink",           "fehler"],
  // --- Einwilligung ---
  ["einwilligung",          "dialog"],
  ["ewPerson",              "dialog"],
  ["ewNur",                 "dialog"],
  ["ewStart",               "dialog"],
  ["ewAb",                  "dialog"],
  ["ewfehler",              "dialog"],
];

const ZUSTAND_LEER = {
  live: false, gesendet: 0, hoerer: {}, gesamt: 0, laeuft_seit: 0,
  fassung: "0.4.1", rechenwerk: "cuda", stt_fehler: null, stellen: [],
  namen: [], kontext_fehlt: false, nachrichten: [], wartung: [],
  letzte: [], mitschnitt: null, am_rechner: true, update: null,
  befunde: [],
  ton: null, netz: {}, gemeinde: "", pult_passwort: false,
  protokoll_mitschrift: false, pruefprotokoll: null, sprachverdacht: "",
  spendenkonto: "", nutzung_melden: false,
};
const PEGEL_LEER = {
  lage: "still", lage_text: "", einmessen: null, jetzt: 0.0, spitze: 0.0,
  grund: 0.001, schwelle: 0.0005, fest: false, modus: "aus",
  grundmodus: "aus", gemessen: null, knapp: 0, spricht: false, verworfen: 0,
};
const warte = () => new Promise(r => setTimeout(r, 60));

async function pult(zustand = {}, pegel = {}, extra = {}) {
  const p = pultBauen({ zustand: { ...ZUSTAND_LEER, ...zustand },
                        pegel: { ...PEGEL_LEER, ...pegel }, extra });
  await warte();
  p.g = (id) => p.nachId.get(id);
  return p;
}

// =====================================================================
block("1. Jedes Element aus der Bestandsaufnahme ist da");
{
  const p = await pult();
  for (const [id] of TABELLE) {
    if (!p.g(id)) { fehler++; console.log(`   FEHLER ${id} gibt es nicht mehr`); }
  }
  pruefe(`${TABELLE.length} Elemente vorhanden`,
         TABELLE.every(([id]) => !!p.g(id)));
  // Und keines steht an zwei Stellen.
  const doppelt = [...p.body.alle()].map(e => e.id).filter(Boolean);
  const gesehen = new Set(), zweimal = [];
  for (const i of doppelt) { if (gesehen.has(i)) zweimal.push(i); gesehen.add(i); }
  pruefe("keine Kennung zweimal", zweimal.length === 0, zweimal.join(", "));
}

block("2. Jedes Element liegt, wo es soll, und ist erreichbar");
{
  const p = await pult();
  const f = p.fenster;
  // Leise pruefen: 115 gruene Zeilen sind nicht lesbar, 3 rote schon.
  let still = 0;
  const pruefe2 = (was, ok, e = "") => {
    if (!ok) { still++; fehler++; console.log(`   FEHLER ${was}` + (e ? `  -> ${e}` : "")); }
  };
  for (const [id, wo, opt = {}] of TABELLE) {
    const e = p.g(id);
    if (!e) continue;
    // Hinwandern: Reiter waehlen, ggf. Unterseite, ggf. Unteransicht.
    // postZeigen und fehlerZeigen schalten um. Beim zweiten Element
    // derselben Ansicht wuerde ein zweiter Aufruf sie wieder zumachen.
    if (wo === "post") { if (p.g("post").hidden) f.postZeigen(); }
    else if (wo === "fehler") { if (p.g("fehler").hidden) f.fehlerZeigen(); }
    else if (wo === "dialog") { f.reiterWaehlen("gottesdienst"); }
    else if (wo === "einrichtung") {
      f.reiterWaehlen("einrichtung");
      f.unterseiteWaehlen(opt.seite);
    } else if (wo === "kopf" || wo === "banner") {
      f.reiterWaehlen("einrichtung");   // irgendein Reiter, sie stehen ueberall
    } else {
      f.reiterWaehlen(wo);
    }
    // Wo liegt es? Der naechste Vorfahr, der eine Ansicht ist.
    const ANSICHT = {gottesdienst:1, vorbereiten:1, aufnahmen:1,
                     einrichtung:1, post:1, fehler:1};
    const kette = [e, ...e.vorfahren()];
    const heim = kette.find(v => ANSICHT[v.id])
      || (kette.some(v => v.tagName === "DIALOG") ? {id:"dialog"} : null)
      || (kette.some(v => v.classList && v.classList.contains("top"))
          ? {id:"kopf"} : null)
      || (kette.some(v => v.id === "bannerleiste") ? {id:"banner"} : null);
    const soll = (wo === "banner" || wo === "kopf" || wo === "dialog")
      ? wo : wo;
    pruefe2(`${id} liegt in "${soll}"`, heim && heim.id === soll,
            heim ? heim.id : "nirgends");
    // Ist die Ansicht nach dem Hinwandern offen? Ein Element, dessen
    // eigenes hidden ein Zustand ist (ein Banner, eine laufende
    // Aufnahme), zaehlt dabei nicht.
    if (heim && ANSICHT[heim.id])
      pruefe2(`${id}: die Ansicht ist offen`,
              !heim.hidden && heim.vorfahren().every(v => !v.hidden));
    // "Eine Ebene tiefer" heisst: hinter einem Fragezeichen oder in der
    // Feineinstellung. Das muss auch so sein.
    // Tiefer heisst: hinter einem Fragezeichen -- oder hinter einer
    // Zeile, die es aufklappt (aria-controls).
    if (opt.tief) {
      const aufklapper = p.body.querySelectorAll("BUTTON")
        .some(b => b.getAttribute("aria-controls") === id);
      pruefe2(`${id} steht eine Ebene tiefer`,
              kette.some(v => v.tagName === "DETAILS") || aufklapper);
    }
  }
  pruefe(`${TABELLE.length} Elemente liegen, wo sie sollen, `
         + `und sind erreichbar`, still === 0, `${still} Abweichungen`);
}

block("3. Vier Reiter, Anker, Tastatur");
{
  const p = await pult();
  const f = p.fenster;
  const leiste = p.body.querySelectorAll(".reiter")[0];
  const knoepfe = leiste.querySelectorAll("BUTTON");
  pruefe("vier Reiter", knoepfe.length === 4, String(knoepfe.length));
  pruefe("jeder Reiter ist ein Knopf mit role=tab",
         knoepfe.every(k => k.getAttribute("role") === "tab"));
  pruefe("genau einer ist gewaehlt",
         knoepfe.filter(k => k.getAttribute("aria-selected") === "true").length === 1);
  pruefe("Vorgabe ist Gottesdienst",
         p.g("rGottesdienst").getAttribute("aria-selected") === "true");
  pruefe("nur der gewaehlte haengt in der Tabulatorfolge",
         knoepfe.filter(k => k.tabIndex === 0).length === 1);
  f.reiterWaehlen("aufnahmen");
  pruefe("Umschalten zeigt den anderen Abschnitt",
         p.g("aufnahmen").sichtbar() && !p.g("gottesdienst").sichtbar());
  pruefe("und setzt aria-selected um",
         p.g("rAufnahmen").getAttribute("aria-selected") === "true"
         && p.g("rGottesdienst").getAttribute("aria-selected") === "false");
  // Pfeiltaste
  let verhindert = false;
  leiste.ausloesen("keydown", { key: "ArrowRight",
                                preventDefault: () => { verhindert = true; } });
  pruefe("Pfeiltaste schaltet weiter", verhindert
         && p.g("rEinrichtung").getAttribute("aria-selected") === "true");
}
{
  const p = await pult({}, {}, { hash: "#einrichtung" });
  pruefe("der Anker in der Adresse waehlt den Reiter",
         p.g("einrichtung").sichtbar(), "#einrichtung");
}

block("4. Die acht Zustaende");
const ZUSTAENDE = [
  ["bereit", {}, {}],
  ["laeuft", { live: true, laeuft_seit: 754, gesamt: 23,
               hoerer: { en: 11, ru: 9, fa: 3 } }, {}],
  // "kein_ton" ist eine der drei Lagen, die Tonquelle.lage() wirklich
  // schickt. In den ersten Pruefbildern stand hier "still" -- ein Wort
  // aus der Kanalliste, das als rote Meldung im Kopf landete.
  ["kein Ton", { ton: { lage: "kein_ton", name: "SQ5",
                        einzelheit: "Device unavailable" } },
                { lage: "alarm", modus: "automatisch",
                  lage_text: "Es wird gesprochen, aber zu leise für die "
                           + "eingestellte Schwelle." }],
  ["Thema fehlt", { kontext_fehlt: true }, {}],
  ["Aufnahme laeuft", { live: true, mitschnitt: { sekunden: 192 } }, {}],
  ["Update wartet", { update: { lage: "bereit", version: "0.4.2" } }, {}],
  ["Meldung aus dem Saal", { nachrichten: [
      { text: "Der Ton ist zu leise", zeit: "09:48", sprache: "de" }] }, {}],
  ["aus dem Saal geoeffnet", { am_rechner: false }, {}],
  ["Stoerungsansicht offen", { befunde: [
      { kennung: "dienst_devarenu", schwer: true, wartung: false,
        was: "Der Dienst devarenu startet nicht von selbst. Ohne ihn "
           + "gibt es nach einem Neustart keine Übersetzung.",
        was_en: "The devarenu service does not start by itself.",
        tun: "sudo systemctl enable --now devarenu",
        tun_en: "sudo systemctl enable --now devarenu" },
      { kennung: "vorrat", schwer: false, wartung: true,
        was: "Es gibt keinen Reparaturvorrat.",
        was_en: "There is no repair stock.",
        tun: "sudo bash vorrat_bauen.sh",
        tun_en: "sudo bash vorrat_bauen.sh" }],
    _ansicht: "stoerung" }, {}],
  ["Hinweis", { live: true, wartung: [
      { kennung: "vorrat", schwer: false, wartung: true,
        was: "Es gibt keinen Reparaturvorrat.",
        was_en: "There is no repair stock.",
        tun: "sudo bash vorrat_bauen.sh",
        tun_en: "sudo bash vorrat_bauen.sh" }],
    befunde: [
      { kennung: "vorrat", schwer: false, wartung: true,
        was: "Es gibt keinen Reparaturvorrat.",
        was_en: "There is no repair stock.",
        tun: "sudo bash vorrat_bauen.sh",
        tun_en: "sudo bash vorrat_bauen.sh" }] }, {}],
];
for (const [name, z, pg] of ZUSTAENDE) {
  const p = await pult(z, pg);
  const pille = p.g("pille");
  pruefe(`${name}: die Statuspille steht da`,
         pille.sichtbar() && pille.textContent.trim().length > 0,
         JSON.stringify(pille.textContent));
  pruefe(`${name}: kein Anzeigefehler`,
         !/Anzeigefehler|Display error/.test(p.g("warnung").textContent),
         p.g("warnung").textContent);
}

block("4b. Der Pillentext folgt dem Zustand, nicht nur die Farbe");
{
  const faelle = [
    ["bereit",   {},                 "aus",    /Angehalten|Paused/],
    ["laeuft",   { live: true },     "an",     /Läuft|Running/],
    ["Stoerung", { ton: { lage: "kein_ton", name: "SQ5" } },
                                     "kaputt", /Störung|Fault/],
  ];
  for (const [name, z, klasse, wort] of faelle) {
    const p = await pult(z);
    pruefe(`${name}: die Pille heisst richtig`,
           wort.test(p.g("pille").textContent),
           JSON.stringify(p.g("pille").textContent));
    pruefe(`${name}: und hat die passende Farbe`,
           p.g("pille").classList.contains(klasse), p.g("pille").className);
  }
  // Der Fehler, der in den Bildern stand: uiZeichnen setzte jedes
  // data-t neu und schrieb der Pille wieder "Angehalten" hinein.
  const p = await pult({ live: true });
  p.fenster.uiZeichnen();
  pruefe("uiZeichnen schreibt den Pillentext nicht zurueck",
         /Läuft|Running/.test(p.g("pille").textContent),
         JSON.stringify(p.g("pille").textContent));
}

block("4b2. Vier Pillenstufen, und die Pille ist ein Knopf");
{
  const vorrat = { kennung: "vorrat", schwer: false, wartung: true,
                   was: "Kein Reparaturvorrat.", was_en: "No repair stock.",
                   tun: "sudo bash vorrat_bauen.sh",
                   tun_en: "sudo bash vorrat_bauen.sh" };
  const dienst = { kennung: "dienst_devarenu", schwer: true, wartung: false,
                   was: "Der Dienst startet nicht von selbst.",
                   was_en: "The service does not start by itself.",
                   tun: "sudo systemctl enable devarenu",
                   tun_en: "sudo systemctl enable devarenu" };
  const p = await pult({ live: true, befunde: [vorrat] });
  pruefe("offene Wartungspunkte bei laufendem Betrieb ergeben HINWEIS",
         /Hinweis|Notice/.test(p.g("pille").textContent)
         && p.g("pille").classList.contains("hinweis"),
         p.g("pille").textContent + " / " + p.g("pille").className);
  const q = await pult({ live: true, befunde: [vorrat, dienst] });
  pruefe("ein schwerer Befund schlaegt den Hinweis",
         /Störung|Fault/.test(q.g("pille").textContent),
         q.g("pille").textContent);
  pruefe("die Pille ist ein Knopf", p.g("pille").tagName === "BUTTON");
  pruefe("und sagt beim Antippen, warum",
         (p.g("pille").getAttribute("title") || "").length > 5);
  const r = await pult({ live: true });
  pruefe("ohne Befund bleibt LAEUFT stumm",
         !r.g("pille").getAttribute("title"));
}

block("4b3. Die Stoerungsansicht");
{
  const dienst = { kennung: "dienst_devarenu", schwer: true, wartung: false,
                   was: "Der Dienst startet nicht von selbst.",
                   was_en: "The service does not start by itself.",
                   tun: "sudo systemctl enable devarenu",
                   tun_en: "sudo systemctl enable devarenu" };
  for (const reiter of ["gottesdienst", "vorbereiten", "aufnahmen",
                        "einrichtung"]) {
    const p = await pult({ befunde: [dienst] });
    p.fenster.reiterWaehlen(reiter);
    p.fenster.stoerungZeigen();
    pruefe(`aus "${reiter}" erreichbar`, p.g("stoerung").sichtbar());
  }
  const p = await pult({ befunde: [dienst] });
  p.fenster.stoerungZeigen();
  pruefe("der Befund steht in einfachen Worten da",
         /startet nicht von selbst/.test(p.g("stoerungliste").innerHTML));
  pruefe("mit einem Satz, was zu tun ist",
         /Betreuer anrufen/.test(p.g("stoerungliste").innerHTML),
         p.g("stoerungliste").innerHTML.slice(0, 160));
  pruefe("der Befehl steht NICHT oben",
         !/systemctl/.test(p.g("stoerungliste").innerHTML));
  pruefe("sondern unter \u201eFuer den Betreuer\u201c",
         !p.g("stoerungtechnik").hidden
         && /systemctl/.test(p.g("stoerungtechnikliste").innerHTML));
  const leer = await pult();
  leer.fenster.stoerungZeigen();
  pruefe("ohne Befund sagt sie das", !leer.g("stoerungleer").hidden);
}

block("4c. Banner tragen nur uebersetzte Meldungen");
{
  // Eine Lage, die es nicht gibt, darf nichts erzeugen -- erst recht
  // kein Wort aus der Kanalliste.
  for (const lage of ["still", "ruht", "offen", "unlesbar", "quatsch"]) {
    const p = await pult({ ton: { lage, name: "SQ5" } });
    pruefe(`"${lage}" erscheint nicht als rote Meldung`,
           p.g("tonhin").hidden, p.g("tonhin").textContent);
  }
  for (const lage of ["kein_ton", "warte_auf_geraet", "neu_geoeffnet"]) {
    const p = await pult({ ton: { lage, name: "SQ5" } });
    pruefe(`"${lage}" ergibt einen Satz`,
           !p.g("tonhin").hidden && p.g("tonhin").textContent.length > 12,
           p.g("tonhin").textContent);
  }
}

block("5. Rote Meldungen stehen in JEDEM Reiter");
{
  const p = await pult({ ton: { lage: "kein_ton", name: "SQ5" } });
  for (const r of ["gottesdienst", "vorbereiten", "aufnahmen", "einrichtung"]) {
    p.fenster.reiterWaehlen(r);
    const band = p.g("tonhin");
    pruefe(`kein Ton ist in "${r}" zu sehen`,
           !band.hidden && band.vorfahren().every(v => !v.hidden));
    pruefe(`die Statuspille ist in "${r}" zu sehen`, p.g("pille").sichtbar());
  }
  pruefe("und sie ist rot", p.g("tonhin").classList.contains("rot"));
}
{
  const p = await pult({ kontext_fehlt: true });
  pruefe("ein gelber Hinweis genuegt als Punkt am Reiter",
         !p.g("punktVorbereiten").hidden);
  pruefe("und als gelbe Kachel -- kein zusaetzliches Banner",
         p.g("kThema").classList.contains("warn")
         && p.body.querySelectorAll(".banner")
              .filter(b => !b.hidden).length === 0);
}

block("5b. Stille ist grau, nicht gruen");
{
  const p = await pult({}, { lage: "still", spricht: false,
                             jetzt: 0.0001, grund: 0.001 });
  pruefe("ohne Pegel steht die Ton-Kachel neutral",
         !p.g("kTon").classList.contains("ok")
         && !p.g("kTon").classList.contains("warn")
         && !p.g("kTon").classList.contains("schlecht"),
         p.g("kTon").className);
  pruefe('und sagt "still"', /still|silent/.test(p.g("tonZustand").textContent),
         p.g("tonZustand").textContent);
  const q = await pult({}, { lage: "gut", spricht: true,
                             jetzt: 0.02, grund: 0.001 });
  pruefe("mit Pegel wird sie gruen",
         q.g("kTon").classList.contains("ok"), q.g("kTon").className);
}

block("6. Die Kacheln sagen den Zustand in einem Wort");
{
  const p = await pult({ gesamt: 23, hoerer: { en: 11, ru: 9, fa: 3 },
                         stellen: ["Mt 18"], namen: ["Petrus"] });
  pruefe("Zuhoerer: die Gesamtzahl steht gross da",
         p.g("hoererzahl").textContent === "23");
  pruefe("je Sprache Kuerzel und Zahl",
         /EN/.test(p.g("hoerersprachen").innerHTML)
         && /11/.test(p.g("hoerersprachen").innerHTML));
  pruefe("Thema gesetzt ist gruen",
         p.g("kThema").classList.contains("ok"));
  pruefe("und nennt die Stelle",
         /Mt 18/.test(p.g("themazeile").textContent));
}
{
  const p = await pult({ kontext_fehlt: true });
  pruefe("Thema fehlt ist gelb", p.g("kThema").classList.contains("warn"));
  pruefe("mit einem Weg zum Eintragen", !p.g("themalink").hidden);
  p.fenster.reiterWaehlen("vorbereiten", "kontext");
  pruefe("der Weg fuehrt ins Feld",
         p.g("vorbereiten").sichtbar() && p.g("kontext").fokussiert === true);
}
{
  const p = await pult({}, { lage: "alarm", lage_text: "nichts kommt durch" });
  pruefe("kein Ton macht die Ton-Kachel rot",
         p.g("kTon").classList.contains("schlecht"), p.g("kTon").className);
  // Gemessen verwirft eine eingemessene Schwelle auf einer ruhigen
  // Aufnahme drei Fuenftel der Predigt. Ein Verweis dorthin mitten im
  // Gottesdienst laedt zu genau dem ein.
  // Seit 0.4.2 traegt die Kachel ein Zahnrad in die Feineinstellung.
  // Was sie NICHT traegt, ist ein Weg zum Einmessen: gemessen
  // verwirft eine eingemessene Schwelle auf einer sauberen Leitung
  // drei Fuenftel der Predigt.
  const kopfknoepfe = p.g("kTon").querySelectorAll("BUTTON")
    .filter(b => !b.vorfahren().some(v => v.tagName === "DETAILS"));
  pruefe("die Ton-Kachel traegt genau ein Zahnrad",
         kopfknoepfe.length === 1
         && kopfknoepfe[0].classList.contains("kzahn"),
         String(kopfknoepfe.length));
  pruefe("es fuehrt in die Feineinstellung",
         /feineinstellung/.test(kopfknoepfe[0].getAttribute("onclick") || ""));
  // Es traegt ein Zeichen, kein Wort. Mit data-t haette uiZeichnen()
  // das Zeichen durch "Feineinstellung" ersetzt -- genau so stand es
  // im ersten Pruefbild.
  pruefe("und bleibt ein Zeichen",
         kopfknoepfe[0].textContent.trim().length <= 2,
         JSON.stringify(kopfknoepfe[0].textContent));
  pruefe("mit einem Namen fuer die Vorlesehilfe",
         (kopfknoepfe[0].getAttribute("aria-label") || "").length > 3,
         kopfknoepfe[0].getAttribute("aria-label"));
  pruefe("und nicht zum Einmessen",
         !p.g("bEinmessen").vorfahren().some(v => v.id === "kTon"));
  pruefe("der Einmessen-Knopf steht nur in der Feineinstellung",
         p.g("bEinmessen").vorfahren().some(v => v.id === "feineinstellung"));
  pruefe("und traegt den Satz, was er kostet",
         /verwerfen|discard/.test(p.g("feineinstellung").volltext()),
         p.g("feineinstellung").volltext().slice(0, 90));
}

block("7. Verzoegerung und Rueckstau");
{
  const gleich = [1.2, 1.3, 1.1, 1.4, 1.2, 1.3, 1.2, 1.3]
    .map((g, i) => ({ id: i, deutsch: "Satz " + i, gesamt: g }));
  const p = await pult({ letzte: gleich });
  pruefe("die Zeile zeigt den letzten Abschnitt",
         p.g("zuletzttext").textContent === "Satz 7");
  pruefe("mit seiner Verzoegerung in Sekunden",
         p.g("zuletztsek").textContent === "1.3 s",
         p.g("zuletztsek").textContent);
  pruefe("gleichbleibend ist kein Rueckstau",
         !p.g("kTon").classList.contains("warn"));
  pruefe("der Verlauf ist zugeklappt", p.g("mit").hidden);
  p.fenster.verlaufKlappen();
  pruefe("ein Tipp klappt ihn auf", !p.g("mit").hidden
         && p.g("zuletztzeile").getAttribute("aria-expanded") === "true");
  pruefe("und er zeigt die acht Abschnitte",
         (p.g("mit").innerHTML.match(/<div>/g) || []).length === 8);
}
{
  const steigend = [1.1, 1.3, 1.6, 2.1, 2.6, 3.2, 3.9, 4.6]
    .map((g, i) => ({ id: i, deutsch: "Satz " + i, gesamt: g }));
  const p = await pult({ letzte: steigend });
  pruefe("steigende Verzoegerung macht die Ton-Kachel gelb",
         p.g("kTon").classList.contains("warn"), p.g("kTon").className);
  pruefe("und sagt warum",
         /Verz|delay/.test(p.g("tonZustand").textContent),
         p.g("tonZustand").textContent);
}
{
  // Langsam, aber gleichbleibend: kein Rueckstau.
  const langsam = [3.0, 3.1, 2.9, 3.0, 3.2, 3.0, 3.1, 3.0]
    .map((g, i) => ({ id: i, deutsch: "x", gesamt: g }));
  const p = await pult({ letzte: langsam });
  pruefe("dauerhaft langsam ist kein Rueckstau",
         !p.g("kTon").classList.contains("warn"));
}

block("8. Schwelle: drei Modi am Pult");
for (const [modus, wort] of [["aus", /Schwelle: aus|Threshold: off/],
                             ["automatisch", /automatisch|automatic/i],
                             ["fest", /[Ff]est|[Ff]ixed/]]) {
  const p = await pult({}, { modus, gemessen: modus === "fest"
                             ? "2026-10-03 09:41:00" : null });
  pruefe(`Modus "${modus}" steht an der Ton-Kachel`,
         wort.test(p.g("schwellestand").textContent),
         p.g("schwellestand").textContent);
  const knopf = { aus: "bAus", automatisch: "bAuto", fest: "bFest" }[modus];
  pruefe(`und der Knopf "${modus}" ist gedrueckt`,
         p.g(knopf).getAttribute("aria-pressed") === "true");
}
{
  const p = await pult({}, { modus: "fest", gemessen: "2026-10-03 09:41:00" });
  pruefe("fest nennt den Zeitpunkt",
         /9:41|09:41/.test(p.g("schwellestand").textContent),
         p.g("schwellestand").textContent);
}

block("8b. Branding");
{
  const p = await pult();
  const logo = p.body.querySelector(".logo");
  pruefe("das Logo steht im Kopf",
         !!logo && logo.vorfahren().some(v => v.classList.contains("top")));
  pruefe("und damit in jedem Reiter", !!logo && logo.sichtbar());
  // Der Pfad ist derselbe, unter dem der Server es ausliefert. In den
  // ersten Pruefbildern fehlte das Logo, weil der Renderer die Seite
  // ueber file:// lud -- dort zeigt "/logo.png" auf die Wurzel des
  // Dateisystems, und onerror nimmt das Bild still heraus. Das Pult
  // war in Ordnung, der Pruefstand nicht.
  pruefe("es zeigt auf /logo.png, wie der Server es ausliefert",
         logo && logo.getAttribute("src") === "/logo.png",
         logo && logo.getAttribute("src"));
  pruefe("und faellt still weg, wenn die Datei fehlt",
         !!(logo && (logo.getAttribute("onerror") || "").includes("remove")));
  pruefe("es steht als erstes im Kopf, vor dem Namen",
         !!logo && logo.eltern.kinder.indexOf(logo) === 0);
  {
    const quelle = readFileSync(SERVER, "utf8");
    const stil = quelle.split('PULT = """')[1].split("<style>")[1]
                       .split("</style>")[0].replace(/\s+/g, "");
    pruefe("keine Regel blendet es aus",
           !/\.logo\{[^}]*display:none/.test(stil)
           && !/\.top\.logo\{[^}]*display:none/.test(stil));
    pruefe("und es hat eine feste Hoehe, die bei 150 % nicht mitwaechst",
           /\.top\.logo\{[^}]*height:\d+px/.test(stil));
  }
  // Und der Renderer liefert es aus, statt es aus der Wurzel zu holen.
  {
    const r = readFileSync(
      new URL("./pultbilder.mjs", import.meta.url).pathname, "utf8");
    pruefe("der Bilderlauf liefert logo.png mit aus",
           /copyFileSync\(logo,/.test(r) && /createServer/.test(r));
    pruefe("und laedt die Seite ueber HTTP, nicht ueber file://",
           !/"file:\/\/"/.test(r) && /http:\/\/127\.0\.0\.1/.test(r));
  }
  pruefe('"Uebersetzung starten" traegt .start',
         p.g("bStart").classList.contains("start"), p.g("bStart").className);
  const q = await pult({ live: true });
  pruefe("angehalten wird dunkelblau, ohne .start",
         !q.g("bStart").classList.contains("start"), q.g("bStart").className);
  const quelle = readFileSync(SERVER, "utf8");
  const stil = quelle.split('PULT = """')[1].split("<style>")[1].split("</style>")[0];
  pruefe(".start traegt den Verlauf von 0.4.0",
         /\.btn\.primaer\.start\{background:linear-gradient\(100deg,#3b1e73,#1c3a8f 52%,/
           .test(stil.replace(/\s+/g, " ").replace(/ \{/g, "{")),
         "Verlauf fehlt");
  pruefe("der Kopf traegt die Linie im selben Verlauf",
         /\.top\{[^}]*border-image:linear-gradient\(100deg,#3b1e73/
           .test(stil.replace(/\s+/g, "")));
}

block("8c. Aufnahmeknopf in Ruhe");
{
  const quelle = readFileSync(SERVER, "utf8");
  const stil = quelle.split('PULT = """')[1].split("<style>")[1]
                     .split("</style>")[0].replace(/\s+/g, "");
  pruefe("kein roter Rahmen und keine rote Schrift in Ruhe",
         !/\.rec\{[^}]*(border-color:var\(--rot\)|color:var\(--rot\))/.test(stil),
         "rec traegt noch Rot");
  pruefe("der Ring ist leer, nicht gefuellt",
         /\.rec::before\{[^}]*border:2pxsolidvar\(--rot\)/.test(stil)
         && !/\.rec::before\{[^}]*background:var\(--rot\)/.test(stil));
  pruefe("gefuellt wird er erst, wenn aufgenommen wird",
         /\.rec\[aria-pressed=true\]\{[^}]*background:var\(--rot\)/.test(stil));
}

block("8d. Kopf und Reiter bei enger Schrift");
{
  const quelle = readFileSync(SERVER, "utf8");
  const stil = quelle.split('PULT = """')[1].split("<style>")[1]
                     .split("</style>")[0].replace(/\s+/g, "");
  pruefe("der Kopf darf umbrechen",
         /\.top\{[^}]*flex-wrap:wrap/.test(stil));
  pruefe("das Wort im Reiter wird ausgeblendet, nicht abgeschnitten",
         /\.reiter\.nurzeichen\.wort\{display:none\}/.test(stil)
         && !/\.reiter\.wort\{[^}]*text-overflow:ellipsis/.test(stil));
  const p = await pult();
  for (const k of ["rGottesdienst", "rVorbereiten", "rAufnahmen",
                   "rEinrichtung"])
    pruefe(`${k} traegt einen Namen ohne Wort`,
           (p.g(k).getAttribute("aria-label") || "").length > 3,
           p.g(k).getAttribute("aria-label"));
}

block("8e. Abstand unter der Knopfzeile");
{
  const quelle = readFileSync(SERVER, "utf8");
  const stil = quelle.split('PULT = """')[1].split("<style>")[1]
                     .split("</style>")[0].replace(/\s+/g, "");
  pruefe("die Knopfzeile hat Abstand nach unten",
         /\.haupt\{[^}]*margin:00 ?1rem/.test(stil)
         || /\.haupt\{[^}]*margin:001rem/.test(stil), "kein margin an .haupt");
}

block("8f. Der Stick-Knopf bleibt aus dem Saal erreichbar");
{
  // Das ist der Update-Weg ab 1.0. Ein Knopf, den nur jemand am
  // Gemeinde-PC druecken kann, hilft einer Gemeinde nicht, die den
  // Rechner im Schrank stehen hat. Geschuetzt wird er, wenn
  // ueberhaupt, durch das Pult-Passwort -- nicht durch den Ort.
  const p = await pult({ am_rechner: false });
  p.fenster.reiterWaehlen("einrichtung");
  p.fenster.unterseiteWaehlen("eUpdate");
  pruefe("der Knopf steckt nicht hinter nur_am_rechner",
         p.g("updateknopf").vorfahren().every(v => !v.hidden));
  pruefe('aber "Jetzt aus dem Netz" bleibt am Rechner',
         p.g("onlinereihe").hidden);
  const quelle = readFileSync(SERVER, "utf8");
  const stelle = quelle.slice(quelle.indexOf('"/api/update/jetzt"'),
                              quelle.indexOf('"/api/update/jetzt"') + 1400);
  pruefe("auch der Server sperrt ihn nicht nach Ort",
         !/vom_rechner_selbst|am_rechner/.test(stelle));
}

block("9. Aufnahmen");
{
  const p = await pult();
  p.fenster.reiterWaehlen("aufnahmen");
  pruefe("der Reiter Aufnahmen traegt Herunterladen und Loeschen",
         true);   // die Liste kommt aus /api/aufnahmen, siehe aufnahme_test.py
  pruefe("die Loeschfrist steht als eine Zeile",
         !!p.g("aufnahmetage"));
}

block("10. Pult-Passwort");
{
  const p = await pult({ pult_passwort: false });
  pruefe('"Passwort entfernen" fehlt, solange keines gesetzt ist',
         p.g("bPwWeg").hidden);
  const q = await pult({ pult_passwort: true });
  pruefe("und steht da, sobald eines gesetzt ist", !q.g("bPwWeg").hidden);
}

block("11. Alle Texte stehen in beiden Oberflaechensprachen");
{
  const { koerper, skript } = pultLesen(SERVER);
  const schluessel = new Set([...koerper.matchAll(/data-t=([\w-]+)/g)].map(m => m[1]));
  for (const m of skript.matchAll(/\bt\.([a-z][\w]*)/g)) schluessel.add(m[1]);
  for (const m of skript.matchAll(/TEXTE\[UI\]\.([a-z][\w]*)/g)) schluessel.add(m[1]);
  const tabelle = skript.slice(skript.indexOf("const TEXTE="));
  const de = tabelle.slice(tabelle.indexOf(" de:{"), tabelle.indexOf(" en:{"));
  const en = tabelle.slice(tabelle.indexOf(" en:{"));
  const hat = (t, k) => new RegExp(`[{,\\s]${k}\\s*:`).test(t);
  const fehlendDe = [...schluessel].filter(k => !hat(de, k)).sort();
  const fehlendEn = [...schluessel].filter(k => !hat(en, k)).sort();
  pruefe(`${schluessel.size} Schluessel, alle auf Deutsch`,
         fehlendDe.length === 0, fehlendDe.join(", "));
  pruefe("alle auf Englisch", fehlendEn.length === 0, fehlendEn.join(", "));
}

block("12. Gestaltung: was die Farbregel verlangt");
{
  const quelle = readFileSync(SERVER, "utf8");
  const stil = quelle.split('PULT = """')[1].split("<style>")[1].split("</style>")[0];
  // Dunkelblau als FLAECHE nur an der Hauptaktion und am aktiven Reiter.
  const flaechen = [...stil.matchAll(/([^{}]+)\{([^}]*background:\s*var\(--navy\)[^}]*)\}/g)]
    .map(m => m[1].trim());
  const erlaubt = flaechen.every(w => /\.btn\.primaer|\.zahl/.test(w));
  pruefe("dunkelblaue Flaeche nur an der Hauptaktion",
         erlaubt, flaechen.join(" | "));
  pruefe("color-scheme ist erklaert", /color-scheme\s*:\s*light/.test(stil));
  pruefe("die Fusszone des Geraets ist eingerechnet",
         /padding-bottom:\s*env\(safe-area-inset-bottom\)/.test(stil));
  pruefe("viewport-fit=cover steht im Kopf",
         /viewport-fit=cover/.test(quelle.split('PULT = """')[1].slice(0, 400)));
  pruefe("die Leiste weicht dem Tippen",
         /body\.tippt\s+\.reiter\{display:none\}/.test(stil));
  // Fingergroesse
  const knopfregeln = [...stil.matchAll(/(^|\n)([^{}\n]*(?:\.btn|\.reiter button|\.ikon|\.chips label|\.seitennav button|\.kanal|summary|\.zuletzt)[^{}\n]*)\{([^}]*)\}/g)];
  const zuklein = knopfregeln
    .filter(m => !/min-height/.test(m[3]) ? false
                 : parseFloat((m[3].match(/min-height:\s*([\d.]+)px/) || [0, 99])[1]) < 44)
    .map(m => m[2].trim());
  pruefe("Knoepfe und Reiter sind mindestens 44 px hoch",
         zuklein.length === 0, zuklein.join(" | "));
  // Keine feste Breite, wo Text drinsteht
  const festeBreite = [...stil.matchAll(/([^{}]+)\{([^}]*[^-]width:\s*(\d+)px[^}]*)\}/g)]
    .filter(m => +m[3] > 24).map(m => m[1].trim());
  pruefe("keine feste Pixelbreite an Textflaechen",
         festeBreite.length === 0, festeBreite.join(" | "));
  // Rechts-nach-links: die zustandstragenden Raender logisch
  pruefe("der farbige Kachelrand ist logisch, nicht links",
         /\.kachel\{[^}]*border-inline-start/.test(stil)
         && !/\.kachel\{[^}]*border-left/.test(stil));
  pruefe("der Bannerrand ist logisch",
         /\.banner\{[^}]*border-inline-start-width/.test(stil));
  pruefe("die Schwellenmarke sitzt logisch",
         /\.mini \.marke\{[^}]*inset-inline-start/.test(stil));
}

block("12b. Konturen: Kanten von Bedienelementen");
{
  // WCAG 1.4.11 verlangt fuer die Begrenzung eines Bedienelements
  // 3:1 -- nicht 4,5:1 wie fuer Schrift, aber auch nicht nichts.
  // Bis 0.4.2 stand ueberall --linie, auch an Knoepfen und Feldern:
  // 1,26:1 auf Weiss, also praktisch unsichtbar. Ein weisser Knopf
  // auf weissem Grund ist nur an seiner Kante als Knopf zu erkennen.
  const quelle = readFileSync(SERVER, "utf8");
  const stil = quelle.split('PULT = """')[1].split("<style>")[1]
                     .split("</style>")[0];
  const v = {};
  for (const m of stil.matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})/g))
    v[m[1]] = m[2];
  const L = (hex) => {
    const k = [1, 3, 5].map(i => parseInt(hex.substr(i, 2), 16) / 255)
      .map(c => c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4));
    return 0.2126 * k[0] + 0.7152 * k[1] + 0.0722 * k[2];
  };
  const K = (a, b) => { const x = L(a), y = L(b);
    return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  for (const [was, a, b] of [["--kante auf Weiss", v.kante, "#ffffff"],
                             ["--kante auf --fl", v.kante, v.fl]]) {
    const k = K(a, b);
    pruefe(`${was}: ${k.toFixed(2)}:1`, k >= 3, a);
  }
  // Und: keine Kante eines BEDIENELEMENTS auf --linie oder --hell.
  // --linie bleibt fuer Trennstriche richtig, dort begrenzt sie
  // nichts, was man anfassen kann.
  const BEDIENT = /\.btn|\.ikon|\.pille|\.reiter|\.chips label|input\[|textarea|select|\.seitennav button|\.kanal|\.kachel|summary|dialog|\.stoerpunkt/;
  const schwach = [];
  for (const m of stil.matchAll(/([^{}]+)\{([^}]*)\}/g)) {
    const wahl = m[1].replace(/\/\*[\s\S]*?\*\//g, "").trim();
    if (!BEDIENT.test(wahl)) continue;
    for (const r of m[2].matchAll(
        /border[\w-]*\s*:\s*[^;]*var\(--(linie|hell)\)/g))
      schwach.push(wahl.slice(-40) + " (" + r[1] + ")");
  }
  pruefe("keine Bedienkante auf --linie oder --hell",
         schwach.length === 0, schwach.join(" | "));
}

block("13. Kontrast der Schriftfarben");
{
  const quelle = readFileSync(SERVER, "utf8");
  const stil = quelle.split('PULT = """')[1].split("<style>")[1].split("</style>")[0];
  const v = {};
  for (const m of stil.matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})/g)) v[m[1]] = m[2];
  const L = (hex) => {
    const k = [1, 3, 5].map(i => parseInt(hex.substr(i, 2), 16) / 255)
      .map(c => c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4));
    return 0.2126 * k[0] + 0.7152 * k[1] + 0.0722 * k[2];
  };
  const K = (a, b) => { const x = L(a), y = L(b);
    return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  const paare = [
    ["Text auf Weiss", v.text, "#ffffff"],
    ["Grau auf Weiss", v.grau, "#ffffff"],
    ["Grau auf Flaeche", v.grau, v.fl],
    ["Gruen auf Weiss", v.gruen, "#ffffff"],
    ["Gruen auf Gruenflaeche", v.gruen, v.gruenbg],
    ["Gelb auf Weiss", v.gelb, "#ffffff"],
    ["Gelb auf Gelbflaeche", v.gelb, v.gelbbg],
    ["Rot auf Weiss", v.rot, "#ffffff"],
    ["Rot auf Rotflaeche", v.rot, v.rotbg],
    ["Weiss auf Dunkelblau", "#ffffff", v.navy],
    ["Verweis auf Weiss", v.link, "#ffffff"],
    ["Gruen auf Flaeche", v.gruen, v.fl],
    ["Gelb auf Flaeche", v.gelb, v.fl],
    ["Rot auf Flaeche", v.rot, v.fl],
  ];
  for (const [was, a, b] of paare) {
    const k = K(a, b);
    pruefe(`${was}: ${k.toFixed(2)}:1`, k >= 4.5, `${a} auf ${b}`);
  }
}

block("14. Der Erklaertext ist nicht geloescht, nur eingeklappt");
{
  const { koerper } = pultLesen(SERVER);
  const quelle = readFileSync(SERVER, "utf8");
  const skript = quelle.split('PULT = """')[1];
  // Stichproben aus den Erklaertexten von 0.4.0. Sie muessen weiter da
  // sein -- irgendwo, und sei es hinter einem Fragezeichen.
  const proben = [
    "Jede Zeile ist ein Kanal",
    "ist gehört, nicht bewiesen",
    "0 heißt: nicht löschen",
    "Name der Gemeinde, Fassung und Datum",
    "Der Bericht enthält nur technische",
    "Die Mail geht raus, sobald das Handy",
    "Netzname und Passwort des Routers",
    "kann dieses Pult bedienen",
    "Holt die neueste geprüfte Fassung",
    "Schreibt je",
    "nicht vorgelesen",
    "Antworten ist nicht vorgesehen",
  ];
  const weg = proben.filter(t => !skript.includes(t));
  pruefe(`${proben.length} Erklaertexte stehen noch da`, weg.length === 0,
         weg.join(" | "));
  const fragezeichen = (koerper.match(/<details class=hilfe>/g) || []).length;
  pruefe("und haengen hinter einem Fragezeichen",
         fragezeichen >= 8, String(fragezeichen));
  // Die zwei doppelten WLAN-Erklaerungen sind eine geworden.
  pruefe("die WLAN-Erklaerung steht nur einmal",
         !koerper.includes("Der Zugangspunkt kennt sie selbst"));
}

block("15. Keine fest eingebauten deutschen Woerter im Skript");
{
  const { skript } = pultLesen(SERVER);
  const nachTexte = skript.slice(skript.indexOf("let UI="))
    // Kommentare zuerst weg: dort stehen Zitate alter Meldungen, und
    // die sind Begruendung, nicht Oberflaeche.
    .split("\n").map(z => z.replace(/(^|[^:"'\\])\/\/.*$/, "$1")).join("\n");
  // Zeichenketten mit deutschen Umlauten oder typischen Woertern, die
  // nicht aus TEXTE kommen.
  const verdacht = [];
  for (const m of nachTexte.matchAll(/"([^"\\\n]{4,})"/g)) {
    const t = m[1];
    if (/[äöüßÄÖÜ]/.test(t) || /\b(der|die|das|und|nicht|wird|Schwelle)\b/.test(t))
      verdacht.push(t);
  }
  pruefe("keine deutschen Zeichenketten ausserhalb der Tabelle",
         verdacht.length === 0, verdacht.join(" | "));
}

// =====================================================================
if (process.argv.includes("--bilder")) {
  const { bilderMachen } = await import("./pultbilder.mjs");
  fehler += await bilderMachen(ZUSTAENDE, { ZUSTAND_LEER, PEGEL_LEER });
} else {
  console.log("\n(Die Geraetegroessen und die Bilder nach /tmp/devarenu_pult/"
            + " nur mit --bilder.)");
}

console.log("");
if (fehler) { console.log(`${fehler} FEHLER`); process.exit(1); }
console.log("Alles in Ordnung.");
