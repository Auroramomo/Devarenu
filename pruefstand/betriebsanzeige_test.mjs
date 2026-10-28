// Autostart, letztes Wartungsfenster und Wecker am Pult (0.5.1).
//
//     node pruefstand/betriebsanzeige_test.mjs
//
// Das echte Pult-Skript aus server.py bekommt nachgebaute Antworten von
// /api/betriebslage und /api/update. Geprueft wird, was dasteht: das
// Urteil zuerst ("aufgewacht, Update gescheitert" oder "nicht
// aufgewacht"), der Grund vollstaendig und mit Zeilenumbruch, "unbekannt"
// statt einer Vermutung, und dasselbe auf Englisch.
//
// node gibt es nur auf dem Arbeitsrechner.

import { pultBauen } from "./pultnachbau.mjs";

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

const GRUND = "git fetch fehlgeschlagen.\n"
  + "Entweder kein Netz -- oder ein Tag zeigt drueben woanders hin\n"
  + "als hier. Das wird ABSICHTLICH nicht ueberschrieben: ein\n"
  + "umgebogenes Tag darf kein geprueuftes ersetzen. Nachsehen:\n"
  + "git fetch --tags --dry-run\n"
  + "Autoupdate ist gescheitert (Rueckgabe 1).";

const FENSTER = { an: true, tag: "Do", von: "18:00", bis: "22:00",
  autoupdate: true, beginn: "2026-10-08 18:00", wach: "ja",
  beleg: "journal", versucht: "ja", ende_lauf: "", journal: true,
  wlan: "ja", internet: "nein", ziel: "", ergebnis: "gescheitert",
  grund: GRUND };

async function pult(lage, update = {}) {
  const p = pultBauen();
  await ruhe();
  const vorher = p.fenster.fetch;
  p.fenster.fetch = (u, o) => {
    const weg = String(u).split("?")[0];
    const d = weg === "/api/betriebslage" ? lage
            : weg === "/api/update" ? update : null;
    if (d === null) return vorher(u, o);
    return Promise.resolve({ ok: true, status: 200,
                             json: () => Promise.resolve(d) });
  };
  p.g = (id) => p.nachId.get(id);
  p.text = (id) => p.g(id).volltext().replace(/\s+/g, " ").trim();
  p.zeilen = (id) => p.g(id).kinder.map((k) => k.volltext().trim());
  p.schwer = (id) => p.g(id).kinder.filter((k) => k.classList.contains("schwer")).length;
  await p.fenster.betriebLaden();
  await p.fenster.updateLaden();
  return p;
}

// =====================================================================
block("A1 Autostart");
{
  const p = await pult({
    dienst: { vorhanden: true, eingeschaltet: "enabled", aktiv: "active",
              unter: "running", neustarts: 0, seit: "Do 2026-10-08 18:00:05" },
    laufart: "dienst", startprotokoll: [], fenster: null, wecker: null });
  const t = p.text("dienstliste");
  pruefe("Autostart an", true, t.includes("Autostart: an."));
  pruefe("mit Bedeutung", true, t.includes("startet Devarenu von selbst"));
  pruefe("Dienst laeuft, seit wann", true, t.includes("läuft, seit Do 2026-10-08 18:00:05"));
  pruefe("keine Neustarts", true, t.includes("seit dem Start des Dienstes: 0"));
  pruefe("Pult kommt vom Dienst", true, t.includes("Dieses Pult kommt vom Dienst."));
  pruefe("nichts rot", 0, p.schwer("dienstliste"));
  pruefe("Startprotokoll leer: das steht da", true,
         p.text("startliste").includes("Noch kein Eintrag."));
  pruefe("Fenster und Wecker ohne Angabe: keine Zeile", [0, 0],
         [p.g("fensterliste").kinder.length, p.g("weckerliste").kinder.length]);
}
{
  const p = await pult({
    dienst: { vorhanden: true, eingeschaltet: "disabled", aktiv: "inactive",
              unter: "dead", neustarts: 5, seit: "",
              befehl: "bash ~/Devarenu/dienst.sh" },
    laufart: "sitzung",
    startprotokoll: ["2026-10-10 08:01:00 | Dienst keiner | kein laufender Dienst -- hier gestartet",
                     "2026-10-11 08:02:00 | Dienst active/running | ohne Ton (nein) -- Dienst angehalten, hier gestartet"],
    fenster: null, wecker: null });
  const t = p.text("dienstliste");
  pruefe("Autostart aus, mit Wert", true, t.includes("Autostart: aus (disabled)."));
  // Seit 0.5.2 der Befehl vom Server, mit dem echten Ordner
  // (autostart_befehl_test.mjs), statt eines festen systemctl.
  pruefe("und was zu tun ist", true, t.includes("bash ~/Devarenu/dienst.sh"));
  pruefe("viele Neustarts: Hinweis aufs Journal", true,
         t.includes("seit dem Start des Dienstes: 5") && t.includes("journalctl -u devarenu -b"));
  pruefe("Pult kommt vom Schreibtischsymbol", true,
         t.includes("Dieses Pult kommt vom Schreibtischsymbol"));
  pruefe("Autostart aus und Neustarts sind rot", 2, p.schwer("dienstliste"));
  const z = p.zeilen("startliste");
  pruefe("Startprotokoll: juengste oben", true, z[0].startsWith("2026-10-11"));
  pruefe("zwei Zeilen", 2, z.length);
}
{
  const p = await pult({ dienst: null, laufart: "sitzung", startprotokoll: [],
                         fenster: null, wecker: null });
  pruefe("ohne systemctl: nur die Herkunft", 1, p.g("dienstliste").kinder.length);
}
{
  const p = await pult({ dienst: { vorhanden: false,
                                   befehl: "bash /opt/devarenu/dienst.sh" },
                         laufart: "unbekannt",
                         startprotokoll: [], fenster: null, wecker: null });
  const t = p.text("dienstliste");
  pruefe("nicht eingerichtet: bash <Ordner>/dienst.sh", true,
         t.includes("bash /opt/devarenu/dienst.sh"));
  pruefe("Herkunft unbekannt, nicht geraten", true, t.includes("unbekannt"));
}

block("A2 Das letzte Fenster");
{
  const p = await pult({ dienst: null, laufart: null, startprotokoll: [],
                         fenster: FENSTER, wecker: null });
  const z = p.zeilen("fensterliste");
  pruefe("zuerst das Urteil", true, z[0].startsWith("Aufgewacht, Update gescheitert."));
  pruefe("Einstellung", true, p.text("fensterliste").includes("Fenster: Do 18:00–22:00, Autoupdate an."));
  pruefe("wann begonnen", true, p.text("fensterliste").includes("Zuletzt begonnen: 2026-10-08 18:00."));
  pruefe("Internet nein, mit Erklaerung", true,
         p.text("fensterliste").includes("Internet erreicht: nein.")
         && p.text("fensterliste").includes("git fetch ist gescheitert"));
  const grund = p.g("fensterliste").kinder.flatMap((li) => li.kinder)
    .find((k) => k.classList.contains("grund"));
  pruefe("der Grund steht VOLLSTAENDIG da, mit Zeilenumbruch", GRUND,
         grund ? grund._text : null);
}
{
  const p = await pult({ fenster: { ...FENSTER, wach: "nein", ergebnis: "unbekannt",
                                    internet: "unbekannt", grund: "" } });
  const z = p.zeilen("fensterliste");
  pruefe("nicht aufgewacht: das Urteil", true,
         z[0].startsWith("Der Rechner ist zum Fenster nicht aufgewacht."));
  pruefe("und rot", true, p.schwer("fensterliste") >= 1);
  pruefe("keine Zeilen ueber Internet oder Ergebnis", false,
         p.text("fensterliste").includes("Internet erreicht"));
}
{
  const p = await pult({ fenster: { ...FENSTER, wach: "unbekannt", journal: false,
                                    versucht: "unbekannt", internet: "unbekannt",
                                    ergebnis: "unbekannt", grund: "" } });
  const t = p.text("fensterliste");
  pruefe("ohne Journal: aufgewacht unbekannt", true,
         t.includes("Ob der Rechner zum Fenster aufgewacht ist: unbekannt."));
  pruefe("und warum (Gruppe adm)", true, t.includes("Gruppe adm"));
  pruefe("Internet unbekannt", true, t.includes("Internet erreicht: unbekannt."));
}
{
  const p = await pult({ fenster: { ...FENSTER, wach: "ja", beleg: "marke",
                                    journal: false, ergebnis: "unbekannt",
                                    internet: "unbekannt", grund: "",
                                    ende_lauf: "2026-10-08 18:09" } });
  const t = p.text("fensterliste");
  pruefe("Marke ohne Journal: versucht, Ergebnis unbekannt", true,
         t.includes("es endete 2026-10-08 18:09") && t.includes("nur root"));
}
{
  const p = await pult({ fenster: { ...FENSTER, ergebnis: "eingespielt",
                                    internet: "ja", ziel: "0.5.1", grund: "" } });
  const t = p.text("fensterliste");
  pruefe("gelungen", true, t.includes("Aufgewacht, Update eingespielt.")
         && t.includes("Zielfassung: 0.5.1.") && t.includes("Ergebnis: eingespielt."));
  pruefe("nichts rot", 0, p.schwer("fensterliste"));
}
{
  const p = await pult({ fenster: { an: false } });
  pruefe("Fenster aus", true, p.text("fensterliste").startsWith("Wartungsfenster: aus."));
}

block("A2 Die Meldung des Updaters, ungekuerzt");
{
  const lang = "Das Bundle auf dem Stick passt nicht zu diesem Rechner. "
    + "x".repeat(400) + " Ende.";
  const p = await pult({}, { lage: "fehlgeschlagen", version: "0.5.1",
                             vorher: "0.5.0", text: lang,
                             zeit: "2026-10-08 18:09:00" });
  pruefe("steht da", false, p.g("updatetext").hidden);
  pruefe("bis zum letzten Wort", true, p.g("updatetext")._text.endsWith("Ende."));
}

block("A3 Der Wecker");
{
  const p = await pult({ wecker: { lesbar: true, gestellt: "2026-10-15 17:55",
                                   vorbei: false, geplant: "2026-10-15 17:55" } });
  const t = p.text("weckerliste");
  pruefe("naechstes Aufwachen", true, t.includes("Nächstes geplantes Aufwachen: 2026-10-15 17:55."));
  pruefe("passt", true, t.includes("Passt zum Wartungsfenster."));
  pruefe("und was er nicht kann", true, t.includes("Steckdosenleiste"));
}
{
  const p = await pult({ wecker: { lesbar: false, gestellt: "", vorbei: false, geplant: "" } });
  pruefe("nicht lesbar: unbekannt", true,
         p.text("weckerliste").includes("Nächstes geplantes Aufwachen: unbekannt."));
}
{
  const p = await pult({ wecker: { lesbar: true, gestellt: "", vorbei: false,
                                   geplant: "2026-10-15 17:55" } });
  pruefe("keiner gestellt, aber gebraucht: rot", 1, p.schwer("weckerliste"));
}

block("Englisch");
{
  const p = await pult({
    dienst: { vorhanden: true, eingeschaltet: "disabled", aktiv: "inactive",
              unter: "dead", neustarts: 0, seit: "" },
    laufart: "sitzung", startprotokoll: [], fenster: FENSTER,
    wecker: { lesbar: false, gestellt: "", vorbei: false, geplant: "" } });
  p.fenster.uiSprache();
  await p.fenster.betriebLaden();
  pruefe("Autostart off", true, p.text("dienstliste").includes("Autostart: off (disabled)."));
  pruefe("Woke up, update failed", true,
         p.text("fensterliste").includes("Woke up, update failed."));
  pruefe("Wecker unknown", true, p.text("weckerliste").includes("Next planned wake-up: unknown."));
}
{
  // Wie im Browser: Einrichtung -> Update offen, dann nur DE/EN gedrueckt,
  // nichts von Hand nachgeladen. Bis zum Fix blieb alles deutsch.
  const p = await pult({
    dienst: { vorhanden: true, eingeschaltet: "disabled", aktiv: "inactive",
              unter: "dead", neustarts: 0, seit: "" },
    laufart: "sitzung", startprotokoll: [], fenster: FENSTER,
    wecker: { lesbar: false, gestellt: "", vorbei: false, geplant: "" } });
  p.fenster.unterseiteWaehlen("eUpdate");
  for (let i = 0; i < 5; i++) await ruhe();
  pruefe("DE: Wecker deutsch", true,
         p.text("weckerliste").includes("Nächstes geplantes Aufwachen: unbekannt."));
  p.fenster.uiSprache();
  for (let i = 0; i < 5; i++) await ruhe();
  pruefe("nur umgeschaltet: Autostart off", true,
         p.text("dienstliste").includes("Autostart: off (disabled)."));
  pruefe("nur umgeschaltet: Woke up, update failed", true,
         p.text("fensterliste").includes("Woke up, update failed."));
  pruefe("nur umgeschaltet: Wecker unknown", true,
         p.text("weckerliste").includes("Next planned wake-up: unknown."));
  pruefe("nichts Deutsches mehr in Fenster und Wecker", false,
         /Aufgewacht|Nächstes geplantes/.test(p.text("fensterliste")
                                              + p.text("weckerliste")));
}

console.log();
if (fehler) { console.log(`\x1b[31m${fehler} Fehler.\x1b[0m`); process.exit(1); }
console.log("\x1b[32mAlle Faelle wie erwartet.\x1b[0m");
