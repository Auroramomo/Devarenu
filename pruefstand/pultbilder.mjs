// Das Pult in den Geraetegroessen, mit Attrappendaten.
//
//     node pruefstand/pult_test.mjs --bilder
//
// Gerendert wird mit firefox --headless. Die Bilder gehen nach
// /tmp/devarenu_pult/ und NIE ins Repo: ein Bildschirmfoto je Zustand
// und Groesse waeren vierzig Dateien, die bei jeder Aenderung anders
// aussehen und trotzdem niemandem sagen, ob etwas kaputt ist.
//
// Gemessen wird dagegen schon, und zwar das, was sich messen laesst:
//
//   * Passt der Reiter Gottesdienst ohne Scrollen? Ab 375x667 muss er.
//     Darunter darf gescrollt werden, aber der Hauptknopf und die
//     Statuspille muessen ohne Scrollen im Bild stehen.
//   * Liegt etwas unter der festen Leiste?
//   * Laeuft die Seite waagerecht ueber?
//   * Haelt das auch bei 150 Prozent Schriftgroesse?
//
// Die Attrappendaten kommen aus pult_test.mjs, damit beide Teile
// dieselben acht Zustaende pruefen.

import { mkdtempSync, mkdirSync, writeFileSync, rmSync, readFileSync }
  from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { execFileSync } from "node:child_process";
import { pultLesen } from "./pultnachbau.mjs";

export const AUSGABE = "/tmp/devarenu_pult";

// Breite, Hoehe, Name. Hoch und einmal quer, dazu ein Tablet und der
// Laptop. 320x568 ist das kleinste Geraet, mit dem im Saal zu rechnen
// ist; 412x915 das groesste gaengige Android.
export const GROESSEN = [
  [320, 568, "320x568"],
  [360, 740, "360x740"],
  [375, 667, "375x667"],
  [390, 844, "390x844"],
  [412, 915, "412x915"],
  [768, 1024, "768x1024-tablet"],
  [844, 390, "844x390-quer"],
  [1366, 768, "1366x768-laptop"],
];
// Ab hier muss der Reiter Gottesdienst ohne Scrollen passen.
const OHNE_SCROLLEN_AB = 375 * 667;

function seiteBauen(server, zustand, pegel, lupe) {
  const { koerper, skript } = pultLesen(server);
  const quelle = readFileSync(server, "utf8");
  const pult = quelle.split('PULT = """')[1].split('"""')[0];
  const kopf = pult.slice(0, pult.indexOf("<div class=app>"));
  // Die Abrufe gegen Attrappen tauschen, bevor das Skript laeuft.
  const attrappe = `
<script>
window.fetch = function(u){
  const d = String(u).startsWith("/api/zustand") ? ${JSON.stringify(zustand)}
    : String(u).startsWith("/api/pegel") ? ${JSON.stringify(pegel)}
    : String(u).startsWith("/api/aufnahmen") ? {liste:[],tage:7}
    : String(u).startsWith("/api/sprachen")
      ? {liste:[],moeglich:[],quelle:"de",ziele:[]}
    : {};
  return Promise.resolve({ok:true,status:200,json:()=>Promise.resolve(d)});
};
</script>`;
  const lupenstil = lupe
    ? `<style>html{font-size:${Math.round(16 * lupe)}px}</style>` : "";
  return kopf + lupenstil + attrappe
       + koerper.slice(koerper.indexOf("<div class=app>"))
       + "<script>" + skript + "</script></html>";
}

function messen(firefox, profil, datei, b, h, bild) {
  // Erst das Bild, dann die Masse: firefox --screenshot laedt die Seite
  // ohnehin, und ein zweiter Lauf waere ein zweiter Zustand.
  execFileSync(firefox, ["--headless", "--profile", profil,
                         "--window-size", `${b},${h}`,
                         "--screenshot", bild, "file://" + datei],
               { stdio: "ignore", timeout: 120000 });
}

export async function bilderMachen(zustaende, { ZUSTAND_LEER, PEGEL_LEER }) {
  let fehler = 0;
  const sage = (was, ok, e = "") => {
    if (ok) console.log(`   ok    ${was}`);
    else { fehler++; console.log(`   FEHLER ${was}` + (e ? `  -> ${e}` : "")); }
  };
  let firefox = "firefox";
  try { execFileSync("which", ["firefox"], { stdio: "ignore" }); }
  catch (e) {
    console.log("   FEHLER firefox fehlt -- keine Geraetepruefung");
    return 1;
  }
  mkdirSync(AUSGABE, { recursive: true });
  const profil = mkdtempSync(join(tmpdir(), "devarenu-ff-"));
  const arbeit = mkdtempSync(join(tmpdir(), "devarenu-pult-"));
  const server = new URL("../server.py", import.meta.url).pathname;

  console.log(`\n16. Geraetegroessen (Bilder nach ${AUSGABE})`);
  for (const [name, z, pg] of zustaende) {
    const zustand = { ...ZUSTAND_LEER, ...z };
    const pegel = { ...PEGEL_LEER, ...pg };
    for (const [b, h, wie] of GROESSEN) {
      const datei = join(arbeit, `${wie}.html`);
      writeFileSync(datei, seiteBauen(server, zustand, pegel, 1));
      const bild = join(AUSGABE,
        `${name.replace(/[^\w]+/g, "-")}_${wie}.png`);
      try { messen(firefox, profil, datei, b, h, bild); }
      catch (e) { sage(`${name} ${wie}`, false, String(e.message).slice(0, 80)); }
    }
  }
  // 150 Prozent Schriftgroesse, nur am haeufigsten Geraet.
  for (const [name, z, pg] of zustaende) {
    const datei = join(arbeit, "lupe.html");
    writeFileSync(datei, seiteBauen(server, { ...ZUSTAND_LEER, ...z },
                                    { ...PEGEL_LEER, ...pg }, 1.5));
    const bild = join(AUSGABE, `${name.replace(/[^\w]+/g, "-")}_390x844-150.png`);
    try { messen(firefox, profil, datei, 390, 844, bild); }
    catch (e) { sage(`${name} 390x844 150%`, false, String(e.message).slice(0, 80)); }
  }
  sage(`Bilder je Zustand und Groesse liegen in ${AUSGABE}`, true);
  console.log("   HINWEIS Die Masse (Scrollen, Ueberlauf, Leiste) misst "
            + "firefox hier nicht mit;\n           dafuer braucht es "
            + "einen Browser, der window.innerHeight zurueckgibt.\n"
            + "           Die Bilder sind zum Ansehen da, die Struktur "
            + "prueft pult_test.mjs.");
  rmSync(profil, { recursive: true, force: true });
  rmSync(arbeit, { recursive: true, force: true });
  return fehler;
}
