#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bekommt ein Handy nach einem Update sicher die neue Hoererseite?

    .venv/bin/python pruefstand/zwischenspeicher_test.py

Bis 0.4.5 lieferte der Server client.html ohne Cache-Control aus, aber
mit Last-Modified. Damit darf ein Browser die Seite HEURISTISCH
zwischenspeichern: ueblich ist ein Zehntel ihres Alters. Eine Seite,
die ein halbes Jahr unveraendert war, gilt dann fast drei Wochen als
frisch -- und wer am Sonntag vor dem Update da war, sieht am Sonntag
danach noch die alte.

Zwei Teile:

  1. Die Kopfzeilen, Seite fuer Seite, und ob ein bedingter Abruf
     mit 304 beantwortet wird (das haelt die Ladezeit im Saal klein).
  2. Ein echter Firefox mit bleibendem Profil: erst Fassung A
     ausliefern, dann die Datei gegen Fassung B tauschen, wie es ein
     Update tut, und nachsehen, welche der Browser zeigt.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hilfe import WURZEL, arbeitskopie, server_starten, server_stoppen  # noqa

GRUEN, ROT, GELB, AUS = "\033[32m", "\033[31m", "\033[33m", "\033[0m"
FEHLER = 0
PORT = 8161

# Wegwerfordner im Arbeitsverzeichnis, nicht unter /tmp, und am Ende
# wieder weg -- auch wenn ein Fall scheitert.
ZWISCHEN = WURZEL / ".tmp" / "pruefstand"
ZWISCHEN.mkdir(parents=True, exist_ok=True)


def pruefe(was, erwartet, ist):
    global FEHLER
    if erwartet == ist:
        print(f"   ok    {was}")
    else:
        print(f"   {ROT}FEHL{AUS}  {was}: erwartet {erwartet!r}, ist {ist!r}")
        FEHLER += 1


def titel(t):
    print(f"\n\033[1m== {t}\033[0m")


def holen(weg, kopf=None):
    """(status, kopfzeilen, inhalt) -- auch bei 304, das ist hier Ziel."""
    b = urllib.request.Request(f"http://127.0.0.1:{PORT}{weg}")
    for k, v in (kopf or {}).items():
        b.add_header(k, v)
    try:
        with urllib.request.urlopen(b, timeout=30) as a:
            return a.status, {k.lower(): v for k, v in a.headers.items()}, \
                a.read()
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in e.headers.items()}, e.read()


# ------------------------------------------------------------ Melder
# Ein zweiter, winziger Dienst. Die Hoererseite im Wegwerfordner traegt
# ein Bild, dessen Adresse die Fassung nennt -- was hier ankommt, hat
# der Browser wirklich geladen. Ohne Zwischenspeicher fuer das Bild
# selbst, sonst hiesse "A" nur "das Bild kam aus dem Speicher".
gemeldet = []


class Melder(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        gemeldet.append(self.path.strip("/"))
        gif = (b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff"
               b"!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01"
               b"\x00\x00\x02\x02D\x01\x00;")
        self.send_response(200)
        self.send_header("Content-Type", "image/gif")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(gif)))
        self.end_headers()
        self.wfile.write(gif)


def fassung_setzen(seite, roh, name, alt_tage):
    """Die Seite mit Marke schreiben, und ihr Datum wie nach einem Update
    (alt_tage=0) oder wie eine lange unveraenderte Datei."""
    marke = (f'<img alt="" width="1" height="1" '
             f'src="http://127.0.0.1:{MELDER_PORT}/{name}">')
    seite.write_text(roh.replace("</body>", marke + "</body>", 1),
                     encoding="utf-8")
    t = time.time() - alt_tage * 86400
    os.utime(seite, (t, t))


ordner = Path(tempfile.mkdtemp(prefix="zwischenspeicher-", dir=ZWISCHEN))
lauf = None
melder = None
try:
    arbeitskopie(ordner)
    # Fuer die PDF-Faelle: die gebauten Anleitungen gehoeren dazu.
    shutil.copytree(WURZEL / "anleitung", ordner / "anleitung")
    seite = ordner / "client.html"
    roh = (WURZEL / "client.html").read_text(encoding="utf-8")

    melder = ThreadingHTTPServer(("127.0.0.1", 0), Melder)
    MELDER_PORT = melder.server_address[1]
    threading.Thread(target=melder.serve_forever, daemon=True).start()

    # Fassung A, ein halbes Jahr alt -- so sieht ein Rechner aus, auf
    # dem lange nichts aktualisiert wurde.
    fassung_setzen(seite, roh, "fassung-A", alt_tage=180)

    lauf = server_starten(ordner, PORT)
    if holen("/api/sprachen")[0] != 200:
        print(f"   {ROT}FEHL{AUS}  der Server kam nicht hoch")
        FEHLER += 1
        raise SystemExit

    # ----------------------------------------------------- Teil 1
    titel("1) Die Hoererseite: Kopfzeilen und bedingter Abruf")
    st, kopf, inhalt = holen("/")
    pruefe("sie kommt", 200, st)
    cc = kopf.get("cache-control", "")
    pruefe(f"Cache-Control verlangt Nachfrage ({cc!r})", True,
           "no-cache" in cc or "no-store" in cc)
    etag = kopf.get("etag", "")
    pruefe("sie traegt ein ETag", True, bool(etag))

    # Unveraendert: 304 und kein Inhalt. Das ist der Grund, warum
    # "no-cache" im Saal nichts kostet -- es geht nur die Frage ueber
    # das Netz, nicht die Seite.
    st, kopf2, inhalt2 = holen("/", {"If-None-Match": etag})
    pruefe("unveraendert: 304", 304, st)
    pruefe("und ohne Inhalt", 0, len(inhalt2))

    # Ein Update tauscht die Datei. Die alte Kennung passt nicht mehr.
    fassung_setzen(seite, roh, "fassung-B", alt_tage=0)
    st, kopf3, inhalt3 = holen("/", {"If-None-Match": etag})
    pruefe("nach dem Update: 200 statt 304", 200, st)
    pruefe("mit der neuen Seite", True, b"fassung-B" in inhalt3)
    pruefe("und einer neuen Kennung", True,
           bool(kopf3.get("etag")) and kopf3.get("etag") != etag)

    # Dieselbe Groesse, dasselbe Datum -- und trotzdem anderer Inhalt.
    # Eine Kennung aus Datum und Groesse saehe darin keinen
    # Unterschied; eine Wiederherstellung mit cp -a setzt genau das.
    gleich_lang = roh.replace("</body>", "<!--X--></body>", 1)
    seite.write_text(gleich_lang, encoding="utf-8")
    os.utime(seite, (1_700_000_000, 1_700_000_000))
    _, k_a, _ = holen("/")
    seite.write_text(gleich_lang.replace("<!--X-->", "<!--Y-->"),
                     encoding="utf-8")
    os.utime(seite, (1_700_000_000, 1_700_000_000))
    _, k_b, _ = holen("/")
    pruefe("gleiches Datum, gleiche Groesse, anderer Inhalt: neue Kennung",
           True, k_a.get("etag") != k_b.get("etag"))

    titel("2) Die uebrigen Seiten")
    for weg in ("/pult", "/qr", "/logo.png",
                "/anleitung.pdf?teil=zuhoerer&sprache=de"):
        st, kopf, _ = holen(weg)
        if st != 200:
            print(f"   {GELB}i{AUS}     {weg}: {st}, uebersprungen")
            continue
        cc = kopf.get("cache-control", "")
        pruefe(f"{weg}: Cache-Control verlangt Nachfrage ({cc!r})", True,
               "no-cache" in cc or "no-store" in cc)

    # ----------------------------------------------------- Teil 2
    titel("3) Ein echter Browser, zwei Fassungen nacheinander")
    if not shutil.which("firefox"):
        print(f"   {GELB}i{AUS}     firefox fehlt -- dieser Teil entfaellt")
    else:
        profil = Path(tempfile.mkdtemp(prefix="ff-", dir=ordner))
        # Wieder Fassung A, ein halbes Jahr alt.
        fassung_setzen(seite, roh, "fassung-A", alt_tage=180)

        def browser():
            bild = ordner / f"bild-{len(gemeldet)}.png"
            subprocess.run(
                ["firefox", "--headless", "--profile", str(profil),
                 "--window-size", "390,844", "--screenshot", str(bild),
                 f"http://127.0.0.1:{PORT}/"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=120)
            return gemeldet[-1] if gemeldet else None

        pruefe("erster Besuch: Fassung A", "fassung-A", browser())
        # Das Update, wie es auf dem Gemeinderechner aussieht: die Datei
        # wird ersetzt und traegt das Datum von jetzt.
        fassung_setzen(seite, roh, "fassung-B", alt_tage=0)
        pruefe("nach dem Update zeigt der Browser Fassung B",
               "fassung-B", browser())
finally:
    server_stoppen(lauf)
    if melder:
        melder.shutdown()
    shutil.rmtree(ordner, ignore_errors=True)

print()
if FEHLER:
    print(f"{ROT}{FEHLER} Fehler.{AUS}")
    sys.exit(1)
print(f"{GRUEN}Alle Faelle wie erwartet.{AUS}")
