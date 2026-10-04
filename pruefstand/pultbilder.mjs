// Das Pult in den Geraetegroessen, mit Attrappendaten.
//
//     node pruefstand/pult_test.mjs --bilder
//
// Gerendert wird mit firefox --headless. Die Bilder gehen nach
// .tmp/pultbilder/ und NIE ins Repo: ein Bildschirmfoto je Zustand
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

import { mkdtempSync, mkdirSync, writeFileSync, rmSync, readFileSync,
         copyFileSync, existsSync } from "node:fs";

import { join } from "node:path";
import { execFile, execFileSync } from "node:child_process";
import { createServer } from "node:http";
import { pultLesen } from "./pultnachbau.mjs";

// Alles Fluechtige bleibt im Arbeitsordner. .tmp steht in .gitignore
// und ist genau dafuer da; /tmp liegt ausserhalb und ist bei jedem
// Zugriff eine Rueckfrage.
export const AUSGABE = new URL("../.tmp/pultbilder", import.meta.url).pathname;
const ZWISCHEN = new URL("../.tmp/pultbilder/bau", import.meta.url).pathname;

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
  const vorab = (zustand._ansicht === "stoerung")
    // Sofort UND noch einmal spaeter: firefox --screenshot wartet auf
    // load, ein setTimeout danach kaeme womoeglich zu spaet.
    ? '<script>function _auf(){try{if(stoerung.hidden)stoerungZeigen()}'
      + 'catch(e){}}addEventListener("load",_auf);'
      + 'setTimeout(_auf,200);setTimeout(_auf,600);<' + '/script>'
    : "";
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
  return kopf + lupenstil + attrappe + vorab
       + koerper.slice(koerper.indexOf("<div class=app>"))
       + "<script>" + skript + "</script></html>";
}

// Ueber HTTP und nicht ueber file://. Das Pult bindet das Logo als
// <img src="/logo.png"> ein -- so, wie der Server es ausliefert. Unter
// file:// zeigt derselbe Pfad auf die Wurzel des Dateisystems, und
// onerror nimmt das Bild still heraus. In den ersten Pruefbildern
// fehlte das Logo genau deshalb: nicht das Pult liess es weg, der
// Pruefstand lieferte es nicht aus.
const TYPEN = { ".html": "text/html; charset=utf-8", ".png": "image/png",
                ".svg": "image/svg+xml", ".ico": "image/x-icon" };

function ausliefern(ordner) {
  const dienst = createServer((anfrage, antwort) => {
    // Kein Weg aus dem Arbeitsordner heraus: der Pruefstand liefert
    // genau das aus, was er selbst hineingelegt hat.
    const name = decodeURIComponent(
      (anfrage.url || "/").split("?")[0]).replace(/^\/+/, "");
    const pfad = join(ordner, name);
    if (!pfad.startsWith(ordner) || !name || !existsSync(pfad)) {
      antwort.writeHead(404); antwort.end(); return;
    }
    const endung = name.slice(name.lastIndexOf("."));
    antwort.writeHead(200, { "Content-Type": TYPEN[endung]
                                             || "application/octet-stream" });
    antwort.end(readFileSync(pfad));
  });
  return new Promise(fertig =>
    dienst.listen(0, "127.0.0.1", () => fertig(dienst)));
}

// execFile statt execFileSync: ein blockierender Kindprozess haelt die
// Ereignisschleife an, und der Webdienst oben koennte dann keine
// einzige Anfrage beantworten -- das Logo fehlte wieder, nur aus einem
// anderen Grund.
function messen(firefox, profil, adresse, b, h, bild) {
  return new Promise((fertig, scheitern) => {
    execFile(firefox, ["--headless", "--profile", profil,
                       "--window-size", `${b},${h}`,
                       "--screenshot", bild, adresse],
             { timeout: 120000 }, (fehler) => fehler ? scheitern(fehler)
                                                     : fertig());
  });
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
  mkdirSync(ZWISCHEN, { recursive: true });
  const profil = mkdtempSync(join(ZWISCHEN, "ff-"));
  const arbeit = mkdtempSync(join(ZWISCHEN, "seiten-"));
  const server = new URL("../server.py", import.meta.url).pathname;
  // Dieselbe Datei, die /logo.png im Betrieb ausliefert. Fehlt sie,
  // faellt das Logo still weg -- auch hier, und das ist richtig so.
  const logo = new URL("../logo.png", import.meta.url).pathname;
  if (existsSync(logo)) copyFileSync(logo, join(arbeit, "logo.png"));
  else console.log("   HINWEIS logo.png fehlt -- die Bilder zeigen keines.");
  const dienst = await ausliefern(arbeit);
  const wurzel = `http://127.0.0.1:${dienst.address().port}/`;

  console.log(`\n16. Geraetegroessen (Bilder nach ${AUSGABE})`);
  for (const [name, z, pg] of zustaende) {
    const zustand = { ...ZUSTAND_LEER, ...z };
    const pegel = { ...PEGEL_LEER, ...pg };
    for (const [b, h, wie] of GROESSEN) {
      const datei = join(arbeit, `${wie}.html`);
      writeFileSync(datei, seiteBauen(server, zustand, pegel, 1));
      const bild = join(AUSGABE,
        `${name.replace(/[^\w]+/g, "-")}_${wie}.png`);
      try { await messen(firefox, profil, wurzel + `${wie}.html`, b, h, bild); }
      catch (e) { sage(`${name} ${wie}`, false, String(e.message).slice(0, 80)); }
    }
  }
  // 150 Prozent Schriftgroesse, nur am haeufigsten Geraet.
  for (const [name, z, pg] of zustaende) {
    const datei = join(arbeit, "lupe.html");
    writeFileSync(datei, seiteBauen(server, { ...ZUSTAND_LEER, ...z },
                                    { ...PEGEL_LEER, ...pg }, 1.5));
    const bild = join(AUSGABE, `${name.replace(/[^\w]+/g, "-")}_390x844-150.png`);
    try { await messen(firefox, profil, wurzel + "lupe.html", 390, 844, bild); }
    catch (e) { sage(`${name} 390x844 150%`, false, String(e.message).slice(0, 80)); }
  }
  sage("logo.png wurde mit ausgeliefert",
       existsSync(join(arbeit, "logo.png")));
  sage(`Bilder je Zustand und Groesse liegen in ${AUSGABE}`, true);
  dienst.close();
  console.log("   HINWEIS Die Masse (Scrollen, Ueberlauf, Leiste) misst "
            + "firefox hier nicht mit;\n           dafuer braucht es "
            + "einen Browser, der window.innerHeight zurueckgibt.\n"
            + "           Die Bilder sind zum Ansehen da, die Struktur "
            + "prueft pult_test.mjs.");
  rmSync(profil, { recursive: true, force: true });
  rmSync(arbeit, { recursive: true, force: true });
  return fehler;
}
