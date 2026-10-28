#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ist irgendeine Ansicht breiter als das Handy? (28.10.2026)

    .venv/bin/python pruefstand/seitenbreite_test.py

Beim Handytest am 28.10.2026 (Samsung, Hochformat) war Einrichtung ->
Update breiter als der Bildschirm: man musste seitwaerts wischen, die
untere Leiste verrutschte, "Service" verschwand nach links. Schuld war
der lange Link auf Devarenu-Update.zip, der nirgends umbrechen durfte.
Dazu die bekannte Stelle auf der Hoererseite: Russisch mit 150 Prozent
Schrift, "Язык" in der Leiste angeschnitten.

Gemessen in zwei echten Browsern, beide headless und ohne Grafikkarte:
Firefox, und Chromium aus dem Electron des Arbeitsrechners
(chromium_laden.cjs). Beide braucht es: Firefox bricht einen langen
Verweis nach jedem "/" um, Chromium -- der Browser der Android-Handys
-- nicht; den Fehler vom Handytest zeigte nur Chromium. Die Seiten
kommen von einem echten Server auf einer Wegwerfkopie. In ihnen liegt ein
Messskript: es schaltet nacheinander jede Ansicht ein -- die vier
Reiter, jede Unterseite der Einrichtung, Briefkasten, Fehler melden,
Stoerungen; auf der Hoererseite Start, Zuhoeren und jedes Blatt --,
klappt jede Hilfe auf und schickt die Masse an einen kleinen Melder.
Das Repo und seine Seiten bleiben, wie sie sind.

Je Ansicht, Pult und Hoererseite, DE und EN, 360 und 390 px:
  * document.documentElement.scrollWidth <= Fensterbreite
  * die untere Leiste liegt ganz im Fenster, jeder Knopf darin auch,
    und keine Beschriftung ist abgeschnitten
Dazu die Hoererseite russisch mit 150 Prozent Schrift.

Die Feineinstellung im Reiter Vorbereiten bleibt zu: sie startet den
Tonscan, und der macht fremde Geraete auf.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hilfe import (WURZEL, arbeitskopie, firefox_ohne_karte,  # noqa: E402
                   rufen, server_starten, server_stoppen)

ROT, GRUEN, GELB, AUS = "\033[31m", "\033[32m", "\033[33m", "\033[0m"
FEHLER = 0
PORT = 8203
ZWISCHEN = WURZEL / ".tmp"
# So lange haelt der Melder ein Bild zurueck, das in der Seite steht.
# Erst danach feuert load -- bis dahin sind die Antworten des Servers
# da, die das Pult gleich zu Beginn abruft.
WARTEN_S = 2.5


def pruefe(was, erwartet, ist, einzelheit=""):
    global FEHLER
    if erwartet == ist:
        print(f"   ok    {was}")
    else:
        FEHLER += 1
        print(f"   {ROT}FEHL{AUS}  {was}: erwartet {erwartet!r}, ist {ist!r}")
        for z in einzelheit.splitlines():
            print(f"           {z}")


def titel(t):
    print(f"\n\033[1m== {t}\033[0m")


# ------------------------------------------------------------ Melder
berichte = []


class Melder(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        # Das Bild, auf das load wartet.
        time.sleep(WARTEN_S)
        gif = (b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff"
               b"!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01"
               b"\x00\x00\x02\x02D\x01\x00;")
        self.send_response(200)
        self.send_header("Content-Type", "image/gif")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(gif)))
        self.end_headers()
        self.wfile.write(gif)

    def do_POST(self):
        laenge = int(self.headers.get("Content-Length") or 0)
        berichte.append(json.loads(self.rfile.read(laenge).decode("utf-8")))
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()


# ------------------------------------------------------- Messskripte
# Gemeinsam: eine Ansicht vermessen. Gemessen wird gegen clientWidth,
# die Breite ohne Rollbalken -- am Handy ist das dasselbe wie die
# Fensterbreite, im Firefox am Rechner ehrlicher.
MESSEN = r"""
function _name(el){
  let s = el.tagName.toLowerCase();
  if(el.id) return s + "#" + el.id;
  if(typeof el.className === "string" && el.className.trim())
    s += "." + el.className.trim().split(/\s+/).join(".");
  // Ohne eigene Kennung: der naechste Vorfahr mit einer, und der Anfang
  // des Textes -- sonst steht im Bericht nur "span".
  const vorfahr = el.parentElement && el.parentElement.closest("[id]");
  if(vorfahr) s = "#" + vorfahr.id + " " + s;
  const text = (el.textContent || "").trim().slice(0, 30);
  return text ? s + ' "' + text + '"' : s;
}
function _messen(ansicht, leiste, wort){
  const doc = document.documentElement;
  const breit = doc.clientWidth;
  const r = {ansicht, fenster: innerWidth, breit, inhalt: doc.scrollWidth,
             ueber: [], leiste: []};
  // Wer ueber den Rand ragt -- nur zur Auskunft im Bericht.
  for(const el of document.body.querySelectorAll("*")){
    if(!el.getClientRects().length) continue;
    const q = el.getBoundingClientRect();
    if(q.right > breit + 0.5 || q.left < -0.5)
      r.ueber.push(_name(el) + " " + Math.round(q.left) + ".."
                   + Math.round(q.right));
  }
  r.ueber = r.ueber.slice(0, 8);
  if(!leiste) return r;
  const l = document.querySelector(leiste);
  if(!l || !l.getClientRects().length){
    r.leiste.push("Leiste nicht zu sehen");
    return r;
  }
  const raus = q => q.left < -0.5 || q.right > breit + 0.5
                    || q.top < -0.5 || q.bottom > innerHeight + 0.5;
  const lq = l.getBoundingClientRect();
  if(raus(lq))
    r.leiste.push("Leiste " + Math.round(lq.left) + ".." + Math.round(lq.right)
                  + " / " + Math.round(lq.top) + ".." + Math.round(lq.bottom));
  for(const k of l.querySelectorAll("button")){
    if(!k.getClientRects().length) continue;
    const kq = k.getBoundingClientRect();
    if(raus(kq))
      r.leiste.push(_name(k) + " " + Math.round(kq.left) + ".."
                    + Math.round(kq.right));
    const w = k.querySelector(wort);
    if(w && w.getClientRects().length && w.scrollWidth > w.clientWidth + 1)
      r.leiste.push(_name(k) + " abgeschnitten: " + w.textContent
                    + " (" + w.scrollWidth + " > " + w.clientWidth + ")");
  }
  return r;
}
function _melden(seite, ergebnisse){
  const x = new XMLHttpRequest();
  // Synchron: firefox --screenshot beendet sich kurz nach load. Ein
  // Abruf, der noch unterwegs ist, kaeme nie an.
  x.open("POST", "MELDER/bericht", false);
  x.setRequestHeader("Content-Type", "text/plain");
  x.send(JSON.stringify({seite, adresse: location.search, ergebnisse}));
}
"""

PULT_MESSEN = r"""
(function(){
const p = new URLSearchParams(location.search);
const sprache = p.get("messung");
if(!sprache) return;
if(UI !== sprache) uiSprache();
// Was hinter den Unterseiten steht, gleich holen -- bis load ist es da.
try{ wlanLaden(); updateLaden(); betriebLaden(); }catch(e){}
// Fehler melden holt den Betreuer erst beim Oeffnen: auf und gleich zu.
try{ fehlerZeigen(); fehlerZeigen(); }catch(e){}
addEventListener("load", ()=>{
  const erg = [];
  const LEISTE = ".reiter", WORT = ".wort";
  try{
    document.getElementById("_warte").remove();
    for(const d of document.querySelectorAll("details"))
      if(d.id !== "feineinstellung") d.open = true;
    for(const r of REITER){
      reiterWaehlen(r);
      erg.push(_messen(r, LEISTE, WORT));
    }
    reiterWaehlen("einrichtung");
    for(const u of UNTERSEITEN){
      if(u.id === "trenner") continue;
      unterseiteWaehlen(u.id);
      erg.push(_messen("einrichtung/" + u.id, LEISTE, WORT));
      unterseiteZu();
    }
    reiterWaehlen("gottesdienst");
    for(const [n, f] of [["briefkasten", postZeigen],
                         ["fehler melden", fehlerZeigen],
                         ["stoerungen", stoerungZeigen]]){
      f();
      erg.push(_messen(n, LEISTE, WORT));
      f();
    }
  }catch(e){ erg.push({ansicht: "FEHLER " + e.message}); }
  _melden("pult", erg);
});
})();
"""

HOERER_MESSEN = r"""
(function(){
const p = new URLSearchParams(location.search);
const sprache = p.get("messung");
if(!sprache) return;
const lupe = parseFloat(p.get("lupe") || "1");
if(lupe !== 1) document.documentElement.style.fontSize = (16 * lupe) + "px";
// Ohne Bewegung: Abschnitte und Blaetter blenden sonst erst ein.
const still = document.createElement("style");
still.textContent = "*,*::before,*::after{animation:none !important;"
                  + "transition:none !important}";
document.head.appendChild(still);
addEventListener("load", ()=>{
  const erg = [];
  const LEISTE = "#zuhoeren .fussleiste", WORT = ".beschriftung";
  try{
    document.getElementById("_warte").remove();
    for(const d of document.querySelectorAll("details")) d.open = true;
    startWaehlen(sprache);
    erg.push(_messen("start", null, null));
    // Wie ein Zuhoerer, nur ohne Verbindung -- die Masse haengen nicht
    // daran, und der Draht wuerde die Statuszeile umstellen.
    zustand.laeuft = true;
    document.getElementById("ankommen").classList.remove("an");
    document.getElementById("zuhoeren").classList.add("an");
    beschriftungenSetzen();
    zustandZeigen("live");
    abschnittZeigen("Gnade sei mit euch und Frieden von Gott, unserem "
      + "Vater, und dem Herrn Jesus Christus.", Date.now() - 60000);
    abschnittZeigen("Seid so unter euch gesinnt, wie es der Gemeinschaft "
      + "in Christus Jesus entspricht.", Date.now());
    erg.push(_messen("zuhoeren", LEISTE, WORT));
    for(const b of document.querySelectorAll("dialog")){
      b.showModal();
      erg.push(_messen("blatt " + b.id, null, null));
      b.close();
    }
  }catch(e){ erg.push({ansicht: "FEHLER " + e.message}); }
  _melden("hoerer", erg);
});
})();
"""


def einbauen(datei, skript, melder):
    """Messskript und Warte-Bild in die Seite der WEGWERFKOPIE legen."""
    roh = datei.read_text(encoding="utf-8")
    teil = (f'<img id=_warte alt="" width=1 height=1 '
            f'style="position:absolute;left:0;top:0" src="{melder}/warte">'
            "<script>" + MESSEN.replace("MELDER", melder) + skript
            + "</script>")
    if "</body>" in roh:
        neu = roh.replace("</body>", teil + "</body>", 1)
    else:
        neu = roh.replace("</html>", teil + "</html>", 1)
    if neu == roh:
        raise SystemExit(f"{datei.name}: kein Ort fuer das Messskript")
    datei.write_text(neu, encoding="utf-8")


def chromium_finden():
    """Ein Electron vom System, juengstes zuerst. None, wenn keines da ist."""
    for name in ("electron", *(f"electron{n}" for n in range(60, 29, -1))):
        if shutil.which(name):
            return shutil.which(name)
    return None


def laden(ordner, browser, weg, breite, hoehe=780):
    """Eine Seite in einem frischen Profil laden. Zurueck: ihr Bericht."""
    # Zum Nacharbeiten an einer Stelle: SEITENBREITE_NUR=ru laesst nur
    # die Laeufe zu, deren Adresse oder Browser das enthaelt.
    nur = os.environ.get("SEITENBREITE_NUR")
    if nur and nur not in f"{browser} {weg} {breite}":
        return "uebersprungen"
    profil = Path(tempfile.mkdtemp(prefix="profil-", dir=ordner))
    adresse = f"http://127.0.0.1:{PORT}{weg}"
    umgebung = firefox_ohne_karte(profil)
    # Rollbalken ueber dem Inhalt, wie am Handy: sonst gingen am Rechner
    # 12 bis 15 px fuer den Balken ab, die es dort nicht gibt.
    with open(profil / "user.js", "a", encoding="utf-8") as f:
        f.write('\nuser_pref("ui.useOverlayScrollbars", 1);\n')
    if browser == "firefox":
        befehl = ["firefox", "--headless", "--profile", str(profil),
                  "--window-size", f"{breite},{hoehe}",
                  "--screenshot", str(profil / "bild.png"), adresse]
    else:
        # Ohne Bildschirm (ozone headless), ohne Grafikkarte, mit eigenem
        # Profil unter .tmp statt in ~/.config.
        befehl = [browser, "--ozone-platform=headless", "--disable-gpu",
                  "--hide-scrollbars", f"--user-data-dir={profil}",
                  str(WURZEL / "pruefstand" / "chromium_laden.cjs"),
                  adresse, str(breite), str(hoehe)]
    vorher = len(berichte)
    try:
        subprocess.run(befehl, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=120, env=umgebung)
    except subprocess.TimeoutExpired:
        return None
    finally:
        shutil.rmtree(profil, ignore_errors=True)
    return berichte[-1] if len(berichte) > vorher else None


def auswerten(was, bericht, erwartet_ansichten):
    if bericht == "uebersprungen":
        return
    if bericht is None:
        pruefe(f"{was}: Bericht kam an", True, False)
        return
    erg = bericht["ergebnisse"]
    kaputt = [e["ansicht"] for e in erg if e["ansicht"].startswith("FEHLER")]
    pruefe(f"{was}: Messskript lief durch", [], kaputt)
    pruefe(f"{was}: {erwartet_ansichten} Ansichten vermessen",
           erwartet_ansichten, len(erg))
    for e in erg:
        if "breit" not in e:
            continue
        if e["breit"] > e["fenster"] or e["breit"] < e["fenster"] - 20:
            print(f"   {GELB}i{AUS}     {was} {e['ansicht']}: Fenster "
                  f"{e['fenster']}, sichtbar {e['breit']}")
        pruefe(f"{was} {e['ansicht']}: nicht breiter als das Fenster "
               f"({e['breit']} px)", True, e["inhalt"] <= e["breit"],
               f"Inhalt {e['inhalt']} px; ragt hinaus:\n  "
               + "\n  ".join(e["ueber"]))
        if e["leiste"]:
            pruefe(f"{was} {e['ansicht']}: untere Leiste ganz zu sehen",
                   [], e["leiste"])


if not shutil.which("firefox"):
    print(f"{ROT}firefox fehlt -- dieser Pruefstand braucht ihn.{AUS}")
    sys.exit(1)

ordner = Path(tempfile.mkdtemp(prefix="seitenbreite-", dir=ZWISCHEN))
lauf = None
melder = None
try:
    arbeitskopie(ordner, {"quelle": "de", "ziele": ["en", "ru", "fa"]})
    melder = ThreadingHTTPServer(("127.0.0.1", 0), Melder)
    adresse = f"http://127.0.0.1:{melder.server_address[1]}"
    threading.Thread(target=melder.serve_forever, daemon=True).start()
    einbauen(ordner / "web" / "pult.html", PULT_MESSEN, adresse)
    einbauen(ordner / "client.html", HOERER_MESSEN, adresse)

    lauf = server_starten(ordner, PORT)
    if rufen(PORT, "/api/sprachen")[0] != 200:
        pruefe("der Server kam hoch", True, False)
        raise SystemExit(1)

    # 4 Reiter, 8 Unterseiten, 3 Unteransichten.
    PULT_ANSICHTEN = 15
    # Start, Zuhoeren und jedes Blatt.
    blaetter = (WURZEL / "client.html").read_text(encoding="utf-8") \
        .count("<dialog ")
    HOERER_ANSICHTEN = 2 + blaetter

    browser = [("Firefox", "firefox")]
    chromium = chromium_finden()
    if chromium:
        browser.append(("Chromium", chromium))
    else:
        pruefe("Chromium (electron) ist da -- der Browser der Android-Handys",
               True, False)
    for kurz, wer in browser:
        for breite in (360, 390):
            for sprache in ("de", "en"):
                titel(f"{kurz}: Pult {sprache.upper()}, {breite} px")
                auswerten(f"{kurz} Pult {sprache} {breite}",
                          laden(ordner, wer, f"/pult?messung={sprache}",
                                breite), PULT_ANSICHTEN)
                titel(f"{kurz}: Hoererseite {sprache.upper()}, {breite} px")
                auswerten(f"{kurz} Hoerer {sprache} {breite}",
                          laden(ordner, wer, f"/?messung={sprache}", breite),
                          HOERER_ANSICHTEN)
            titel(f"{kurz}: Hoererseite russisch, 150 % Schrift, {breite} px")
            auswerten(f"{kurz} Hoerer ru 150% {breite}",
                      laden(ordner, wer, "/?messung=ru&lupe=1.5", breite),
                      HOERER_ANSICHTEN)
finally:
    if lauf:
        server_stoppen(lauf)
    if melder:
        melder.shutdown()
    shutil.rmtree(ordner, ignore_errors=True)

print()
if FEHLER:
    print(f"{ROT}{FEHLER} Fehler.{AUS}")
    sys.exit(1)
print(f"{GRUEN}Alle Faelle wie erwartet.{AUS}")
