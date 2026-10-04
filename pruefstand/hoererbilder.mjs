// Die Hoeransicht in den Geraetegroessen.
//
//     node pruefstand/hoererbilder.mjs
//
// Gerendert wird mit firefox --headless. Die Bilder gehen nach
// .tmp/hoererbilder/ -- der Ordner steht in .gitignore und ist genau
// dafuer da. Sie sehen bei jeder Aenderung anders aus und sagen
// trotzdem niemandem, ob etwas kaputt ist; was sich messen laesst,
// steht in fussleiste_test.mjs.
//
// Gebraucht wurden sie fuer 0.4.5: aus drei Reihen mit neun Knoepfen
// wurde EINE Leiste mit fuenf Eintraegen, und fuenf Beschriftungen auf
// 320 px sind etwas, das man ansehen muss.

import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync,
         existsSync } from "node:fs";
import { join } from "node:path";
import { execFile, execFileSync } from "node:child_process";
import { createServer } from "node:http";

const AUSGABE = new URL("../.tmp/hoererbilder", import.meta.url).pathname;
const ZWISCHEN = new URL("../.tmp/hoererbilder/bau", import.meta.url).pathname;
const SEITE = new URL("../client.html", import.meta.url).pathname;

// 320x568 ist das kleinste Geraet, mit dem im Saal zu rechnen ist;
// 390x844 das haeufigste. Die Lupe nur am haeufigsten.
const GROESSEN = [
  [320, 568, "320x568", 1],
  [390, 844, "390x844", 1],
  [390, 844, "390x844-150", 1.5],
];

// Was auf dem Bild zu sehen sein soll. Der Name wird zum Dateinamen.
const LAGEN = [
  ["leiste", ""],
  ["abgedunkelt", "Dunkel.setzen(2);"],
  ["mehr-blatt", '$("mehrblatt").showModal();'],
  ["aufnahme-laeuft", "aufnahmeHinweis(true);"],
  ["ton-und-text-aus", "tonSchalten(false); $(\"w-text\").click();"],
];

const TYPEN = { ".html": "text/html; charset=utf-8", ".svg": "image/svg+xml",
                ".png": "image/png" };

function ausliefern(ordner) {
  const dienst = createServer((anfrage, antwort) => {
    const name = decodeURIComponent(
      (anfrage.url || "/").split("?")[0]).replace(/^\/+/, "");
    const pfad = join(ordner, name);
    if (!pfad.startsWith(ordner) || !name || !existsSync(pfad)) {
      antwort.writeHead(404); antwort.end(); return;
    }
    const endung = name.slice(name.lastIndexOf("."));
    antwort.writeHead(200, { "Content-Type": TYPEN[endung] || "text/plain" });
    antwort.end(readFileSync(pfad));
  });
  return new Promise((fertig) =>
    dienst.listen(0, "127.0.0.1", () => fertig(dienst)));
}

/* Die Seite in den Zustand bringen, in dem ein Zuhoerer sie sieht.
   Ueber die Oberflaeche, nicht ueber eingesetztes Markup: eine Kachel
   waehlen, Zuhoeren druecken, Text hereinlassen. Was dabei anders
   aussieht als im Saal, ist dann auch im Saal anders. */
function seiteBauen(lage, lupe) {
  const quelle = readFileSync(SEITE, "utf8");
  const lupenstil = lupe !== 1
    ? `<style>html{font-size:${Math.round(16 * lupe)}px}</style>` : "";
  /* Ohne das sind die Bilder leer. Abschnitte tauchen mit 0,34 s von
     opacity 0 auf, der Abdunkler blendet in 0,3 s ein -- und
     firefox --screenshot knipst, sobald load durch ist, also mitten
     im ersten Bild der Animation. */
  const ohneBewegung = "<style>*,*::before,*::after{"
    + "animation:none !important; transition:none !important}</style>";
  const attrappe = `
<script>
// Kein Server: die Sprachliste bleibt beim Vorrat, die Rueckmeldung
// kommt aus der Attrappe -- sonst fehlte der Knopf dafuer im Bild.
window.fetch = function(u){
  // Irgendein wahrer Wert genuegt: davon haengt nur ab, OB der Knopf
  // "Rueckmeldung" erscheint. Eine Adresse steht hier bewusst nicht --
  // oeffentlich_pruefen.sh findet jede, und zu Recht.
  const d = String(u).startsWith("/api/texte")
    ? {rueckmeldung:"(Attrappe)", spende:null} : {};
  return Promise.resolve({ok:true,status:200,json:()=>Promise.resolve(d)});
};
// Keine Verbindung aufbauen: der Draht wuerde nur scheitern und die
// Statuszeile auf "getrennt" stellen.
window.WebSocket = function(){ this.close = function(){}; };
<\/script>`;
  const vorab = `
<script>
let _schon = false;
function _stellen(){
  // GENAU EINMAL. Lief es zweimal, standen alle Abschnitte doppelt da
  // und die Bilder sahen aus, als stimme etwas mit dem Blaettern nicht.
  if(_schon) return;
  _schon = true;
  try{
    // Alle Bilder teilen sich ein Firefox-Profil und damit den
    // Speicher des Browsers. Ohne das traegt das naechste Bild die
    // Abdunkel-Stufe des vorigen.
    try{ localStorage.clear(); Dunkel.setzen(0); }catch(e){}
    rueckmeldungSetzen("(Attrappe)", null);
    zustand.sprache = "de";
    // Druecken wie ein Zuhoerer -- und den Bildschirmwechsel gleich
    // danach SELBST setzen. Der Handler wartet erst auf die
    // Tonfreigabe, und firefox --screenshot knipst vorher.
    $("starten").click();
    zustand.laeuft = true;
    $("ankommen").classList.remove("an");
    $("zuhoeren").classList.add("an");
    beschriftungenSetzen();
    zustandZeigen("live");
    abschnittZeigen("Gnade sei mit euch und Frieden von Gott, unserem "
      + "Vater, und dem Herrn Jesus Christus.", Date.now() - 120000);
    abschnittZeigen("Wir lesen heute aus dem Brief an die Philipper, "
      + "im zweiten Kapitel.", Date.now() - 60000);
    abschnittZeigen("Seid so unter euch gesinnt, wie es der Gemeinschaft "
      + "in Christus Jesus entspricht.", Date.now());
    // NICHT gescrollt. Das Skript laeuft beim Parsen, da ist noch
    // nichts umbrochen -- scrollIntoView tut hier gar nichts, und ein
    // scrollTo landet irgendwo. Die Bilder zeigen darum den Anfang,
    // und das ist eine echte Lage: so faengt jeder Zuhoerer an.
    //
    // Die Frage, ob der neueste Abschnitt hinter der Leiste
    // verschwindet, ist nicht am Bild zu klaeren und wurde an den
    // Rechtecken nachgemessen: am Dokumentende endet er 46 px
    // DARUEBER (320x568, drei Abschnitte).
    // Die Leiste klebt zwar, nimmt am Ende aber ihren Platz im Fluss
    // ein -- es gibt keine Ueberdeckung.
    ${lage}
  }catch(e){
    // SICHTBAR, nicht nur im Titel: ein Bild, auf dem die Attrappe
    // stillschweigend gescheitert ist, sieht aus wie ein Befund.
    document.title = "FEHLER " + e.message;
    const f = $("fahne");
    if(f){ f.textContent = "ATTRAPPE: " + e.message;
           f.classList.remove("weg"); }
  }
}
// SOFORT, nicht erst bei load: dieses Skript steht am Ende des
// Koerpers, die Seite ist also fertig -- und firefox --screenshot
// knipst, sobald load durch ist.
_stellen();
addEventListener("load", _stellen);
<\/script>`;
  return quelle.replace("</head>", lupenstil + ohneBewegung + attrappe
                                   + "</head>")
               .replace("</body>", vorab + "</body>");
}

function schiessen(firefox, profil, adresse, b, h, bild) {
  return new Promise((fertig, scheitern) => {
    execFile(firefox, ["--headless", "--profile", profil,
                       "--window-size", `${b},${h}`,
                       "--screenshot", bild, adresse],
             { timeout: 120000 },
             (fehler) => fehler ? scheitern(fehler) : fertig());
  });
}

try { execFileSync("which", ["firefox"], { stdio: "ignore" }); }
catch (e) {
  console.log("firefox fehlt -- keine Bilder.");
  process.exit(1);
}

mkdirSync(AUSGABE, { recursive: true });
mkdirSync(ZWISCHEN, { recursive: true });
// Auch das Fluechtige bleibt im Arbeitsordner: Firefox-Profil und die
// gebauten Seiten unter .tmp, nicht unter /tmp.
const profil = mkdtempSync(join(ZWISCHEN, "ff-"));
const arbeit = mkdtempSync(join(ZWISCHEN, "seiten-"));
const dienst = await ausliefern(arbeit);
const wurzel = `http://127.0.0.1:${dienst.address().port}/`;

console.log(`Bilder nach ${AUSGABE}`);
try {
  for (const [name, lage] of LAGEN) {
    for (const [b, h, wie, lupe] of GROESSEN) {
      const datei = `${name}_${wie}.html`;
      writeFileSync(join(arbeit, datei), seiteBauen(lage, lupe));
      const bild = join(AUSGABE, `${name}_${wie}.png`);
      try {
        await schiessen(firefox(), profil, wurzel + datei, b, h, bild);
        console.log(`  ${bild}`);
      } catch (e) {
        console.log(`  FEHLER ${name} ${wie}: ${String(e.message).slice(0, 70)}`);
      }
    }
  }
} finally {
  // Die Bilder bleiben, Profil und gebaute Seiten nicht. Ohne das
  // wuchs .tmp/hoererbilder/bau mit jedem Lauf um ein Firefox-Profil.
  dienst.close();
  rmSync(profil, { recursive: true, force: true });
  rmSync(arbeit, { recursive: true, force: true });
}
function firefox(){ return "firefox"; }
