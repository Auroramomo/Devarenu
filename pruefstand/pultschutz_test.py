#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sperrt das freiwillige Pult-Passwort das Richtige -- und nur das?

    python pruefstand/pultschutz_test.py

Zwei Teile. Zuerst die Wache fuer sich, gegen eine Zustandsdatei im
Wegwerfordner. Dann ein ECHTER Server auf einem eigenen Port, gegen den
gesprochen wird wie ein Handy im Saal: ohne Keks, mit Keks, mit
Einmalschluessel.

Der zweite Teil ist der wichtigere. Die Wache allein zu pruefen hiesse,
die Verdrahtung zu glauben -- und genau dort sitzen die Fehler: eine
Route, die vor der Middleware haengt, ein Pfad, der in der
Erlaubnisliste fehlt.

NICHTS wird an der Arbeitskopie geaendert. Der Server laeuft auf einer
Kopie im Wegwerfordner, mit einer eigenen zustand.json.
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
from http.cookiejar import CookieJar
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pultschutz  # noqa: E402
from hilfe import eigene_adresse  # noqa: E402

GRUEN, ROT, AUS = "\033[32m", "\033[31m", "\033[0m"
FEHLER = 0
PORT = 8137


def pruefe(was, erwartet, ist):
    global FEHLER
    if erwartet == ist:
        print(f"   ok    {was}")
    else:
        print(f"   {ROT}FEHL{AUS}  {was}: erwartet {erwartet!r}, ist {ist!r}")
        FEHLER += 1


def titel(t):
    print(f"\n\033[1m== {t}\033[0m")


# ============================================================ Teil 1
titel("1) Die Wache fuer sich")

with tempfile.TemporaryDirectory() as t:
    datei = Path(t) / "zustand.json"
    datei.write_text(json.dumps({"pult_passwort": ""}), encoding="utf-8")
    w = pultschutz.Wache(datei)

    pruefe("ohne Passwort ist nichts gesperrt", True,
           w.darf("/pult", "10.0.0.55", None)[0])
    pruefe("und der Grund stimmt", "kein_passwort",
           w.darf("/pult", "10.0.0.55", None)[1])

    # Jetzt eines setzen -- und zwar in der DATEI, damit zugleich
    # geprueft ist, dass die Wache eine Aenderung ohne Neustart bemerkt.
    h = pultschutz.hashen("Gemeinde2026")
    datei.write_text(json.dumps({"pult_passwort": h}), encoding="utf-8")
    # Die Wache vergleicht den Zeitstempel in Nanosekunden; zwei
    # Schreibvorgaenge in derselben Nanosekunde gibt es nicht, aber
    # sicher ist sicher.
    os.utime(datei, (time.time() + 1, time.time() + 1))

    pruefe("die Aenderung wird ohne Neustart bemerkt", True, w.gesetzt)
    pruefe("das Saalgeraet wird gesperrt", False,
           w.darf("/pult", "10.0.0.55", None)[0])
    pruefe("der Rechner selbst nie", True,
           w.darf("/pult", "127.0.0.1", None)[0])
    pruefe("auch ueber IPv6 nicht", True,
           w.darf("/pult", "::1", None)[0])
    pruefe("die Zuhoererseite bleibt offen", True,
           w.darf("/", "10.0.0.55", None)[0])
    pruefe("ihr Datenstrom auch", True,
           w.darf("/strom", "10.0.0.55", None)[0])
    pruefe("und die Tonhaeppchen", True,
           w.darf("/ton/ru/17", "10.0.0.55", None)[0])
    pruefe("eine Zuschrift aus dem Saal geht durch", True,
           w.darf("/api/nachricht", "10.0.0.55", None)[0])
    pruefe("der richtige Ausweis oeffnet", True,
           w.darf("/pult", "10.0.0.55", pultschutz.ausweis(h))[0])
    pruefe("ein fremder nicht", False,
           w.darf("/pult", "10.0.0.55", "a" * 64)[0])

    # Einmalschluessel
    s = w.schluessel.neu()
    pruefe("ein Einmalschluessel oeffnet den Bericht", True,
           w.darf("/fehlerbericht.txt", "10.0.0.55", None, s)[0])
    pruefe("und gilt noch ein zweites Mal (Handy laedt zweimal)", True,
           w.darf("/fehlerbericht.txt", "10.0.0.55", None, s)[0])
    w.darf("/fehlerbericht.txt", "10.0.0.55", None, s)
    pruefe("danach ist er verbraucht", False,
           w.darf("/fehlerbericht.txt", "10.0.0.55", None, s)[0])
    pruefe("ein erfundener Schluessel oeffnet nichts", False,
           w.darf("/fehlerbericht.txt", "10.0.0.55", None, "ausgedacht")[0])

    # Ein neues Passwort macht alte Ausweise ungueltig.
    alt = pultschutz.ausweis(h)
    h2 = pultschutz.hashen("anders")
    datei.write_text(json.dumps({"pult_passwort": h2}), encoding="utf-8")
    os.utime(datei, (time.time() + 2, time.time() + 2))
    pruefe("nach einem Passwortwechsel gilt der alte Ausweis nicht mehr",
           False, w.darf("/pult", "10.0.0.55", alt)[0])

    # Eine kaputte Datei darf niemanden aussperren.
    datei.write_text("{kaputt", encoding="utf-8")
    os.utime(datei, (time.time() + 3, time.time() + 3))
    pruefe("eine unlesbare Datei sperrt niemanden aus", True,
           w.darf("/pult", "10.0.0.55", None)[0])

titel("2) Das Passwort selbst")
h = pultschutz.hashen("Gemeinde2026")
pruefe("das richtige Passwort passt", True,
       pultschutz.stimmt("Gemeinde2026", h))
pruefe("ein anderes nicht", False, pultschutz.stimmt("gemeinde2026", h))
pruefe("ein leeres nicht", False, pultschutz.stimmt("", h))
pruefe("zweimal dasselbe Passwort ergibt verschiedene Zeilen (Salz)",
       False, h == pultschutz.hashen("Gemeinde2026"))
pruefe("beide passen trotzdem", True,
       pultschutz.stimmt("Gemeinde2026", pultschutz.hashen("Gemeinde2026")))
pruefe("das Passwort steht nicht in der Zeile", False, "Gemeinde2026" in h)


# ============================================================ Teil 3
titel("3) Ein echter Server, angesprochen wie aus dem Saal")

ARBEIT = Path(tempfile.mkdtemp(prefix="devarenu-pw-"))


def aufraeumen(lauf):
    if lauf and lauf.poll() is None:
        lauf.terminate()
        try:
            lauf.wait(timeout=10)
        except subprocess.TimeoutExpired:
            lauf.kill()
    shutil.rmtree(ARBEIT, ignore_errors=True)



def holen(weg, keks=None, daten=None, gastgeber="127.0.0.1"):
    """(status, text). Keine Ausnahme bei 401 -- die ist hier das Ziel."""
    bitte = urllib.request.Request(f"http://{gastgeber}:{PORT}{weg}")
    if keks:
        bitte.add_header("Cookie", f"{pultschutz.KEKS}={keks}")
    if daten is not None:
        bitte.data = daten.encode("utf-8")
        bitte.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(bitte, timeout=20) as a:
            return a.status, a.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return 0, str(e)


lauf = None
try:
    # ALLE Python-Dateien des Projekts, nicht eine gepflegte Liste.
    # Eine solche Liste vergisst genau das Modul, das gerade dazukam --
    # und der Prueflauf meldet dann "der Server kam nicht hoch", was
    # nach einem Fehler im Server aussieht und keiner ist.
    for q in sorted(WURZEL.glob("*.py")):
        shutil.copy2(q, ARBEIT / q.name)
    for name in ("client.html", "VERSION", "logo.png", "betreuer.txt",
                 "glossar_v0.4.csv", "namen_block_b.csv"):
        q = WURZEL / name
        if q.exists():
            shutil.copy2(q, ARBEIT / name)
    for verknuepft in (".venv", "voices", "models"):
        ziel = WURZEL / verknuepft
        if ziel.exists():
            (ARBEIT / verknuepft).symlink_to(ziel)

    # Eine EIGENE Zustandsdatei. Die der Arbeitskopie wird nicht
    # angefasst -- in ihr steht das WLAN-Passwort der Gemeinde.
    zdatei = ARBEIT / "zustand.json"
    zdatei.write_text(json.dumps({"fassung": 3, "pult_passwort": ""}),
                      encoding="utf-8")
    os.chmod(zdatei, 0o600)

    lauf = subprocess.Popen(
        [str(ARBEIT / ".venv/bin/python"), "server.py",
         "--port", str(PORT), "--nur-text"],
        cwd=ARBEIT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    for _ in range(90):
        if holen("/api/sprachen")[0] == 200:
            break
        time.sleep(1)
    else:
        print(f"   {ROT}FEHL{AUS}  der Server kam nicht hoch")
        FEHLER += 1
        raise SystemExit

    print("\n   -- ohne Passwort: alles wie bisher --")
    pruefe("das Pult ist offen", 200, holen("/pult")[0])
    pruefe("die Zuhoererseite auch", 200, holen("/")[0])
    pruefe("der Fehlerbericht auch", 200,
           holen("/fehlerbericht.txt?schnell=1")[0])

    print("\n   -- Passwort setzen (vom Pult aus) --")
    status, _ = holen("/api/pult-passwort", daten='{"passwort":"Gemeinde2026"}')
    pruefe("das Setzen wird angenommen", 200, status)
    gespeichert = json.loads(zdatei.read_text(encoding="utf-8"))
    pruefe("in der Datei steht kein Klartext", False,
           "Gemeinde2026" in zdatei.read_text(encoding="utf-8"))
    pruefe("dafuer ein Hash", True,
           str(gespeichert.get("pult_passwort", "")).startswith("pbkdf2_"))
    pruefe("ein zu kurzes wird abgelehnt", 400,
           holen("/api/pult-passwort", daten='{"passwort":"abc"}')[0])

    print("\n   -- mit Passwort --")
    # urllib kommt als 127.0.0.1 -- das gilt als "am Rechner selbst" und
    # darf NIE gefragt werden. Genau das ist hier die Zusicherung.
    pruefe("am Rechner selbst wird nicht gefragt", 200, holen("/pult")[0])
    pruefe("die Zuhoererseite bleibt offen", 200, holen("/")[0])
    pruefe("ihre Sprachliste auch", 200, holen("/api/sprachen")[0])

    ausweis = pultschutz.ausweis(gespeichert["pult_passwort"])

    # ---- und jetzt wie ein Handy im Saal: ueber eine Adresse, die
    # nicht Loopback ist. Ohne diesen Teil bewiese der Prueflauf nur,
    # dass die Wache im Speicher richtig rechnet -- nicht, dass sie am
    # laufenden Server ueberhaupt dazwischenkommt.
    saal = eigene_adresse()
    if not saal:
        print(f"   {ROT}!{AUS}     UEBERSPRUNGEN: keine Adresse ausser "
              f"Loopback gefunden.")
        print(f"         Damit ist NICHT geprueft, ob ein Saalgeraet "
              f"wirklich abgewiesen wird.")
        FEHLER += 1
    else:
        print(f"\n   -- aus dem Saal, ueber {saal} --")
        pruefe("das Pult wird abgewiesen", 401,
               holen("/pult", gastgeber=saal)[0])
        pruefe("und zwar mit einer Anmeldeseite, nicht mit nacktem Fehler",
               True, "<form" in holen("/pult", gastgeber=saal)[1])
        pruefe("die Einrichtung ebenso", 401,
               holen("/api/zustand", gastgeber=saal)[0])
        pruefe("Aufnahmen ebenso", 401,
               holen("/mitschnitt/predigt_2026-09-25_09-30.wav",
                     gastgeber=saal)[0])
        pruefe("der Protokollschalter ebenso", 401,
               holen("/api/protokoll", daten='{"an":true}',
                     gastgeber=saal)[0])
        pruefe("der Fehlerbericht ohne Schluessel ebenso", 401,
               holen("/fehlerbericht.txt?schnell=1", gastgeber=saal)[0])

        print(f"\n   -- was im Saal offen BLEIBEN muss --")
        pruefe("die Zuhoererseite", 200, holen("/", gastgeber=saal)[0])
        pruefe("ihre Sprachliste", 200,
               holen("/api/sprachen", gastgeber=saal)[0])
        pruefe("das Logo", 200, holen("/logo.png", gastgeber=saal)[0])

        print(f"\n   -- mit Ausweis --")
        pruefe("der Keks oeffnet das Pult", 200,
               holen("/pult", keks=ausweis, gastgeber=saal)[0])
        pruefe("ein falscher Keks nicht", 401,
               holen("/pult", keks="a" * 64, gastgeber=saal)[0])
        pruefe("ein falsches Passwort wird abgelehnt", 401,
               holen("/pult", keks=pultschutz.ausweis("etwas anderes"),
                     gastgeber=saal)[0])

        print(f"\n   -- der Fehlerbericht aufs Handy --")
        # Der ganze Weg, nicht nur seine Haelfte: das Pult erzeugt den
        # Link (am Rechner, also erlaubt), das Handy im Saal loest ihn
        # ein. Dasselbe, was der QR-Code traegt -- beide kommen aus
        # derselben Funktion.
        _, roh = holen("/api/betreuer")
        link = json.loads(roh).get("bericht_link", "")
        pruefe("der Link traegt einen Einmalschluessel", True,
               "schluessel=" in link)
        pruefe("aber nicht das Passwort", False, "Gemeinde2026" in link)
        weg = link.split(f":{PORT}", 1)[-1] if f":{PORT}" in link \
            else "/" + link.split("/", 3)[-1]
        pruefe("damit kommt das Handy an den Bericht", 200,
               holen(weg, gastgeber=saal)[0])
        pruefe("ohne Schluessel bleibt er zu", 401,
               holen("/fehlerbericht.txt?schnell=1", gastgeber=saal)[0])
        # Drei Griffe, dann ist Schluss -- ein abfotografierter
        # Bildschirm soll nach dem Gottesdienst nichts mehr oeffnen.
        holen(weg, gastgeber=saal)
        holen(weg, gastgeber=saal)
        pruefe("nach drei Griffen ist der Schluessel verbraucht", 401,
               holen(weg, gastgeber=saal)[0])

    print("\n   -- zuruecksetzen am Rechner, ohne Pult --")
    hatte = pultschutz.zuruecksetzen(zdatei)
    pruefe("es war eines gesetzt", True, hatte)
    pruefe("danach ist es leer", "",
           json.loads(zdatei.read_text(encoding="utf-8"))["pult_passwort"])
    pruefe("die Datei bleibt 0600", "600", oct(zdatei.stat().st_mode)[-3:])
    # Ohne Neustart: die Wache liest neu, sobald sich der Zeitstempel
    # aendert. Sonst muesste jemand systemctl bemuehen -- und genau
    # daran denkt niemand, der gerade ausgesperrt ist.
    pruefe("und das Pult ist sofort wieder offen", 200, holen("/pult")[0])

finally:
    aufraeumen(lauf)

print()
if FEHLER:
    print(f"{ROT}{FEHLER} Fehler.{AUS}")
    sys.exit(1)
print(f"{GRUEN}Alle Faelle wie erwartet.{AUS}")
