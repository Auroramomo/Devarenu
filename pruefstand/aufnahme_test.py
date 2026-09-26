#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Haelt die Aufnahme, was die Einwilligung verspricht?

    python pruefstand/aufnahme_test.py

Zwei Teile. Zuerst das Modul fuer sich -- Einwilligung, Frist,
Altbestand, Platz -- gegen einen Wegwerfordner mit kuenstlich
gealterten Dateien. Dann ein ECHTER Server: Start ohne Einwilligung
wird abgelehnt, Anhalten beendet die Aufnahme, ein Neustart setzt sie
nicht fort, und Abrufen geht nur am Rechner selbst.

Der zweite Teil ist der wichtigere. Dass das Modul richtig rechnet,
sagt nichts darueber, ob die Pflicht auch am Endpunkt gilt -- und
genau dort muss sie gelten: das Pult haengt im Saalnetz.

NICHTS wird an der Arbeitskopie geaendert. Weder zustand.json noch
ergebnisse/ werden angefasst.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import aufnahme      # noqa: E402
from hilfe import eigene_adresse  # noqa: E402
import pultschutz    # noqa: E402

GRUEN, ROT, AUS = "\033[32m", "\033[31m", "\033[0m"
FEHLER = 0
PORT = 8153
RATE = 16000


def pruefe(was, erwartet, ist):
    global FEHLER
    if erwartet == ist:
        print(f"   ok    {was}")
    else:
        print(f"   {ROT}FEHL{AUS}  {was}: erwartet {erwartet!r}, ist {ist!r}")
        FEHLER += 1


def titel(t):
    print(f"\n\033[1m== {t}\033[0m")


def alt_machen(pfad, tage):
    """Setzt eine Datei kuenstlich zurueck."""
    wann = time.time() - tage * 86400
    os.utime(pfad, (wann, wann))


# ============================================================ Teil 1
titel("1) Die Einwilligung")

voll = aufnahme.Einwilligung(True, True)
pruefe("beide Haken genuegen", True, voll.vollstaendig)
pruefe("einer allein nicht", False,
       aufnahme.Einwilligung(True, False).vollstaendig)
pruefe("der andere allein auch nicht", False,
       aufnahme.Einwilligung(False, True).vollstaendig)
pruefe("keiner erst recht nicht", False,
       aufnahme.Einwilligung().vollstaendig)
pruefe("fehlende Haken werden benannt", ["person_gefragt", "nur_predigt"],
       aufnahme.Einwilligung().fehlend)
pruefe("aus einem leeren Feld wird keine Einwilligung", False,
       aufnahme.Einwilligung.aus_daten(None).vollstaendig)
pruefe("aus Unsinn auch nicht", False,
       aufnahme.Einwilligung.aus_daten("ja").vollstaendig)
# Der Zettel belegt, DASS gefragt wurde -- nicht, wer geantwortet hat.
text = voll.als_text()
pruefe("der Vermerk traegt den Zeitpunkt", True, voll.zeit in text)
pruefe("und sagt ausdruecklich, dass kein Name darin steht", True,
       "Kein Name" in text)


titel("2) Starten, beenden, Frist")

with tempfile.TemporaryDirectory() as t:
    ordner = Path(t) / "predigten"
    a = aufnahme.Aufnahme(ordner, RATE, tage=7)

    datei, grund = a.starten(aufnahme.Einwilligung(True, False))
    pruefe("Start ohne beide Haken wird abgelehnt", "einwilligung_fehlt",
           grund)
    pruefe("und es entsteht keine Datei", False, ordner.exists())

    datei, grund = a.starten(aufnahme.Einwilligung(True, True))
    pruefe("mit beiden Haken faengt es an", "", grund)
    pruefe("die Aufnahme laeuft", True, a.laeuft)
    pruefe("der Ordner hat Rechte 700", "700",
           oct(ordner.stat().st_mode)[-3:])
    pruefe("die Datei hat Rechte 600", "600",
           oct(datei.stat().st_mode)[-3:])
    zettel = datei.with_suffix(".einwilligung.txt")
    pruefe("der Vermerk liegt daneben", True, zettel.exists())
    pruefe("auch er 600", "600", oct(zettel.stat().st_mode)[-3:])

    e = a.beenden("Probe")
    pruefe("beendet", False, a.laeuft)
    pruefe("und nennt die Datei", datei.name, e["datei"])

    # ---- Frist
    for tage, name in ((10, "alt"), (2, "neu")):
        p = ordner / f"predigt_2026-01-{tage:02d}_09-30.wav"
        p.write_bytes(b"RIFF")
        alt_machen(p, tage)
    weg = aufnahme.aufraeumen(ordner, tage=7, trocken=True)
    pruefe("nur die alte waere faellig", 1, len(weg))
    pruefe("und zwar die richtige", True, "01-10" in weg[0]["name"])
    pruefe("der Trockenlauf loescht nichts", True,
           (ordner / "predigt_2026-01-10_09-30.wav").exists())
    weg = aufnahme.aufraeumen(ordner, tage=7)
    pruefe("scharf ist sie weg", False,
           (ordner / "predigt_2026-01-10_09-30.wav").exists())
    pruefe("die neue bleibt", True,
           (ordner / "predigt_2026-01-02_09-30.wav").exists())

    # ---- Altbestand: die Frist laeuft ab dem Update
    p = ordner / "predigt_2025-01-01_09-30.wav"
    p.write_bytes(b"RIFF")
    alt_machen(p, 300)
    ab = time.time()
    weg = aufnahme.aufraeumen(ordner, tage=7, ab=ab, trocken=True)
    pruefe("uralte Aufnahmen gehen beim Update NICHT sofort", 0, len(weg))
    # Nach acht Tagen sind ALLE faellig: auch die eben aufgenommene
    # und die zwei Tage alte haben die Frist dann hinter sich.
    pruefe("sondern erst nach der Frist", 3,
           len(aufnahme.aufraeumen(ordner, tage=7, ab=ab,
                                   jetzt=ab + 8 * 86400, trocken=True)))
    liste = aufnahme.altbestand(ordner, ab)
    # Drei: die uralte, die zwei Tage alte und die eben beendete.
    # Alles, was vor dem Update entstand.
    pruefe("der Altbestand wird erkannt", 3, len(liste))
    faellig = aufnahme.faellig_am(liste[0], 7, ab)
    pruefe("und bekommt ein Datum", True, len(faellig) == 10)

    # ---- tage=0 heisst: nicht loeschen
    pruefe("0 Tage loescht nichts", 0,
           len(aufnahme.aufraeumen(ordner, tage=0, trocken=True)))


titel("3) Kein Platz")

with tempfile.TemporaryDirectory() as t:
    a = aufnahme.Aufnahme(Path(t) / "p", RATE)
    echt = aufnahme.PLATZ_MINDESTENS
    try:
        # So tun, als waere die Platte voll: die Grenze hochsetzen.
        aufnahme.PLATZ_MINDESTENS = 1 << 62
        datei, grund = a.starten(aufnahme.Einwilligung(True, True))
        pruefe("bei knappem Platz faengt nichts an", "platz_knapp", grund)
    finally:
        aufnahme.PLATZ_MINDESTENS = echt

    datei, grund = a.starten(aufnahme.Einwilligung(True, True))
    pruefe("mit Platz schon", "", grund)
    try:
        aufnahme.PLATZ_MINDESTENS = 1 << 62
        frei = a.platz_pruefen()
        pruefe("eine laufende Aufnahme wird gestoppt", True, frei is not None)
        pruefe("und steht", False, a.laeuft)
        pruefe("mit Grund", "platz_knapp", a.grund_aus)
    finally:
        aufnahme.PLATZ_MINDESTENS = echt


# ============================================================ Teil 4
titel("4) Ein echter Server")

ARBEIT = Path(tempfile.mkdtemp(prefix="devarenu-auf-"))
lauf = None



def holen(weg, daten=None, gastgeber="127.0.0.1"):
    b = urllib.request.Request(f"http://{gastgeber}:{PORT}{weg}")
    if daten is not None:
        b.data = json.dumps(daten).encode("utf-8")
        b.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(b, timeout=30) as a:
            return a.status, a.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return 0, str(e)


def starten_mit(zustand_zusatz=None):
    """Startet einen Server auf der Wegwerfkopie."""
    z = {"fassung": 3, "quelle": "de", "ziele": ["en"], "aufnahme_tage": 7}
    z.update(zustand_zusatz or {})
    (ARBEIT / "zustand.json").write_text(json.dumps(z), encoding="utf-8")
    os.chmod(ARBEIT / "zustand.json", 0o600)
    p = subprocess.Popen(
        [str(ARBEIT / ".venv/bin/python"), "server.py",
         "--port", str(PORT), "--nur-text"],
        cwd=ARBEIT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(90):
        if holen("/api/sprachen")[0] == 200:
            return p
        time.sleep(1)
    return p


def stoppen(p):
    if p and p.poll() is None:
        p.terminate()
        try:
            p.wait(timeout=15)
        except subprocess.TimeoutExpired:
            p.kill()


try:
    for q in sorted(WURZEL.glob("*.py")):
        shutil.copy2(q, ARBEIT / q.name)
    for name in ("client.html", "VERSION", "logo.png", "betreuer.txt",
                 "glossar_v0.4.csv", "namen_block_b.csv"):
        if (WURZEL / name).exists():
            shutil.copy2(WURZEL / name, ARBEIT / name)
    for v in (".venv", "voices", "models"):
        if (WURZEL / v).exists():
            (ARBEIT / v).symlink_to(WURZEL / v)

    lauf = starten_mit()
    if holen("/api/sprachen")[0] != 200:
        print(f"   {ROT}FEHL{AUS}  der Server kam nicht hoch")
        FEHLER += 1
        raise SystemExit

    print("\n   -- Einwilligung --")
    st, _ = holen("/api/mitschnitt", {})
    pruefe("Start ganz ohne Angabe wird abgelehnt", 400, st)
    st, _ = holen("/api/mitschnitt",
                  {"einwilligung": {"person_gefragt": True}})
    pruefe("mit nur einem Haken auch", 400, st)
    st, roh = holen("/api/mitschnitt",
                    {"einwilligung": {"person_gefragt": True,
                                      "nur_predigt": True}})
    pruefe("mit beiden faengt es an", 200, st)
    name = json.loads(roh).get("datei", "")
    pruefe("und nennt die Datei", True, name.startswith("predigt_"))
    pruefe("der Zeitpunkt der Einwilligung steht dabei", True,
           bool(json.loads(roh).get("einwilligung")))

    print("\n   -- Anhalten beendet die Aufnahme --")
    # POST, nicht GET: /api/steuerung ist ein Schreibweg. Mit GET
    # kaeme 405 zurueck, anhalten() liefe nie, und der Fall bestuende
    # aus dem falschen Grund.
    pruefe("starten geht", 200, holen("/api/steuerung/start", {})[0])
    pruefe("anhalten geht", 200, holen("/api/steuerung/pause", {})[0])
    st, roh = holen("/api/zustand")
    pruefe("nach dem Anhalten laeuft keine Aufnahme mehr", None,
           json.loads(roh).get("mitschnitt"))

    print("\n   -- Abrufen nur am Rechner --")
    saal = eigene_adresse()
    if not saal:
        print(f"   {ROT}!{AUS}     UEBERSPRUNGEN: keine Adresse ausser "
              f"Loopback. Damit ist NICHT geprueft, ob der Saal "
              f"abgewiesen wird.")
        FEHLER += 1
    else:
        pruefe("die Liste am Rechner", 200, holen("/api/aufnahmen")[0])
        pruefe("die Liste aus dem Saal", 403,
               holen("/api/aufnahmen", gastgeber=saal)[0])
        pruefe("der Download am Rechner", 200,
               holen(f"/mitschnitt/{name}")[0])
        pruefe("der Download aus dem Saal", 403,
               holen(f"/mitschnitt/{name}", gastgeber=saal)[0])
        pruefe("die Frist aus dem Saal", 403,
               holen("/api/aufnahme/tage", {"tage": 1}, gastgeber=saal)[0])

    print("\n   -- Neustart setzt nicht fort --")
    holen("/api/mitschnitt", {"einwilligung": {"person_gefragt": True,
                                               "nur_predigt": True}})
    st, roh = holen("/api/zustand")
    pruefe("eine Aufnahme laeuft", True,
           json.loads(roh).get("mitschnitt") is not None)
    stoppen(lauf)
    lauf = starten_mit()
    st, roh = holen("/api/zustand")
    pruefe("nach dem Neustart laeuft keine", None,
           json.loads(roh).get("mitschnitt"))
    pruefe("aber die Datei ist noch da", True,
           any(p.name.startswith("predigt_")
               for p in (ARBEIT / "ergebnisse" / "predigten").glob("*.wav")))

    print("\n   -- die Frist laesst sich umstellen --")
    st, roh = holen("/api/aufnahme/tage", {"tage": 3})
    pruefe("drei Tage angenommen", 200, st)
    pruefe("und gespeichert", 3,
           json.loads((ARBEIT / "zustand.json").read_text())["aufnahme_tage"])
    pruefe("Unsinn wird abgelehnt", 400,
           holen("/api/aufnahme/tage", {"tage": "viele"})[0])
    pruefe("und eine Jahreszahl auch", 400,
           holen("/api/aufnahme/tage", {"tage": 4000})[0])

finally:
    stoppen(lauf)
    shutil.rmtree(ARBEIT, ignore_errors=True)

print()
if FEHLER:
    print(f"{ROT}{FEHLER} Fehler.{AUS}")
    sys.exit(1)
print(f"{GRUEN}Alle Faelle wie erwartet.{AUS}")
