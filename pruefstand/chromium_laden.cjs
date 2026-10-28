// Eine Seite in Chromium laden, der Engine der Android-Handys (28.10.2026).
//
//     electron43 pruefstand/chromium_laden.cjs ADRESSE BREITE HOEHE
//
// Fuer seitenbreite_test.py. Firefox bricht einen langen Verweis nach
// jedem "/" um, Chromium nicht -- und Chromium ist der Browser auf den
// Android-Handys im Saal (Samsung Internet, Chrome). Der Link auf
// Devarenu-Update.zip lief am Handy ueber den Rand und im Firefox nicht.
//
// Electron liegt auf dem Arbeitsrechner ohnehin; geladen wird nichts.
// Ohne Grafikkarte: Hardwarebeschleunigung aus, gezeichnet wird in
// Software, und kein Fenster geht auf.
//
// Was die Seite misst, schickt sie selbst an den Melder des
// Pruefstands. Hier wird nur geladen, gewartet und beendet.

const { app, BrowserWindow } = require("electron");

const [adresse, breite, hoehe] = process.argv.slice(-3);
const B = parseInt(breite, 10), H = parseInt(hoehe, 10);

app.disableHardwareAcceleration();

app.whenReady().then(() => {
  // Offscreen gezeichnet: keine Rollbalken, die Platz nehmen -- wie am
  // Handy. Die Groesse muss ohne Bildschirm ausdruecklich gesetzt
  // werden, sonst ist das Fenster einen Pixel breit.
  //
  // Die Handy-Emulation (enableDeviceEmulation, oder ueber das
  // DevTools-Protokoll Emulation.setDeviceMetricsOverride) liess
  // Electron 43 ohne Bildschirm abstuerzen. Fuer die Frage hier braucht
  // es sie nicht: wo Chromium umbricht, haengt nicht davon ab.
  const fenster = new BrowserWindow({
    show: false, width: B, height: H, useContentSize: true,
    webPreferences: { offscreen: true },
  });
  fenster.setBounds({ x: 0, y: 0, width: B, height: H });
  // load ist durch, sobald das Messskript gemeldet hat: es meldet
  // synchron in seinem load-Horcher.
  fenster.webContents.on("did-finish-load", () => setTimeout(() => app.exit(0), 300));
  fenster.webContents.on("did-fail-load", () => app.exit(2));
  setTimeout(() => app.exit(3), 90000);
  fenster.loadURL(adresse);
});
