// Autostart aus: steht der Befehl zum Einschalten da? (0.5.2)
//
//     node pruefstand/autostart_befehl_test.mjs
//
// Unter Einrichtung -> Autostart stand bis 0.5.1 bei "Autostart: aus"
// der Satz "Einschalten am Rechner: sudo systemctl enable devarenu",
// und bei "nicht eingerichtet" ein "bash dienst.sh" ohne Ordner. Jetzt
// ein Satz und darunter der Befehl, wie er auf DIESEM Rechner lautet:
// bash <Ordner>/dienst.sh, den Ordner vom Server. Kein Knopf.
//
// Zwei Teile: der Server (betriebslage.dienst_befehl, ueber Python
// gefragt) und das echte Pult-Skript im Nachbau.

import { execFileSync } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pultBauen } from "./pultnachbau.mjs";

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
const ruhe = () => new Promise((f) => setTimeout(f, 0));
const WURZEL = new URL("..", import.meta.url).pathname;

titel("1) Der Server baut den Befehl aus dem echten Ordner");
{
  const frage = (basis, heim) => {
    try {
      return execFileSync(WURZEL + ".venv/bin/python", ["-c",
        "import sys; sys.path.insert(0, sys.argv[1]); import betriebslage as b; "
        + "print(b.dienst_befehl(sys.argv[2], sys.argv[3]))",
        WURZEL, basis, heim], { encoding: "utf8" }).trim();
    } catch (e) { return "FEHLER: " + String(e.message).split("\n")[0]; }
  };
  pruefe("unter dem Heimordner: mit ~", "bash ~/Devarenu/dienst.sh",
         frage("/srv/gemeinde/Devarenu", "/srv/gemeinde"));
  pruefe("anderer Ordnername: der echte", "bash ~/devarenu-0.5/dienst.sh",
         frage("/srv/gemeinde/devarenu-0.5", "/srv/gemeinde"));
  pruefe("ausserhalb des Heimordners: der ganze Pfad",
         "bash /opt/devarenu/dienst.sh", frage("/opt/devarenu", "/srv/gemeinde"));
  pruefe("Leerzeichen sind fuer die Shell geschuetzt",
         "bash ~/'Mein Devarenu/dienst.sh'",
         frage("/srv/gemeinde/Mein Devarenu", "/srv/gemeinde"));
  // Gegen einen leeren Wegwerfordner, nicht gegen das Repo: lage()
  // liest zustand.json, und in der echten steht das WLAN-Passwort.
  const leer = mkdtempSync(join(tmpdir(), "devarenu-autostart-"));
  const lage = execFileSync(WURZEL + ".venv/bin/python", ["-c",
    "import sys, json; from pathlib import Path; sys.path.insert(0, sys.argv[1]); "
    + "import betriebslage as b; "
    + "b.dienst = lambda: {'vorhanden': True, 'eingeschaltet': 'disabled'}; "
    + "print(json.dumps(b.lage(Path(sys.argv[2]))))", WURZEL, leer],
    { encoding: "utf8" });
  rmSync(leer, { recursive: true, force: true });
  pruefe("lage() haengt ihn an den Dienst", true,
         /^bash .*dienst\.sh$/.test(JSON.parse(lage).dienst.befehl || ""));
  pruefe("und nicht als eigenen Teil", undefined, JSON.parse(lage).befehl);
}

async function pult(dienst) {
  const p = pultBauen({ extra: { antworten: { "/api/betriebslage": {
    dienst, laufart: "dienst", startprotokoll: [], fenster: null,
    wecker: null } } } });
  for (let i = 0; i < 5; i++) await ruhe();
  await p.fenster.betriebLaden();
  const liste = p.nachId.get("dienstliste");
  const codes = [...liste.alle()].filter((e) => e.tagName === "CODE")
    .map((e) => e.textContent);
  const knoepfe = [...liste.alle()].filter((e) => e.tagName === "BUTTON");
  return { p, liste, codes, knoepfe };
}
const BEFEHL = "bash ~/Devarenu/dienst.sh";

titel("2) Autostart aus: Satz und Befehl, kein Knopf");
{
  const { liste, codes, knoepfe } = await pult({
    vorhanden: true, eingeschaltet: "disabled", aktiv: "active",
    seit: "heute", befehl: BEFEHL });
  pruefe("der Befehl steht da, wie der Server ihn schickt", [BEFEHL], codes);
  pruefe("kein Knopf", 0, knoepfe.length);
  pruefe("kein festes systemctl mehr im Satz", false,
         liste.volltext().includes("systemctl enable"));
}

titel("3) Dienst nicht eingerichtet: ebenso");
{
  const { codes } = await pult({ vorhanden: false, befehl: BEFEHL });
  pruefe("der Befehl steht da", [BEFEHL], codes);
}

titel("4) Autostart an: kein Befehl");
{
  const { codes } = await pult({ vorhanden: true, eingeschaltet: "enabled",
                                 aktiv: "active", seit: "heute",
                                 befehl: BEFEHL });
  pruefe("nichts zum Abtippen", [], codes);
}

console.log();
if (fehler) { console.log(`${fehler} FEHLER`); process.exit(1); }
console.log("Alle Faelle wie erwartet.");
