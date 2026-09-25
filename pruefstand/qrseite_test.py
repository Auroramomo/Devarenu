#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Zeigt die QR-Seite das Richtige, in jeder Sprache?

    python pruefstand/qrseite_test.py

Zwei Teile: die Texttabelle fuer sich, und ein echter Server, dessen
Seite abgerufen und auseinandergenommen wird.

Der wichtigste Fall ist der unscheinbarste: die AUSGANGSSPRACHE darf
nicht im Durchlauf stehen. Wer die Predigt direkt hoert, braucht keine
Anleitung zum Mithoeren -- und jede ueberfluessige Sprache zeigt die
anderen seltener.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))

import qr_texte  # noqa: E402

GRUEN, ROT, AUS = "\033[32m", "\033[31m", "\033[0m"
FEHLER = 0
PORT = 8141


def pruefe(was, erwartet, ist):
    global FEHLER
    if erwartet == ist:
        print(f"   ok    {was}")
    else:
        print(f"   {ROT}FEHL{AUS}  {was}: erwartet {erwartet!r}, ist {ist!r}")
        FEHLER += 1


print("\n\033[1m== 1) Die Texttabelle\033[0m")
felder = {"schritt1", "schritt2", "geduld", "internet", "hoeren"}
pruefe("jede angebotene Sprache hat Texte", [],
       sorted(c for c in qr_texte.SPRACHEN if c not in qr_texte.TEXTE))
pruefe("keine Sprache hat zu viel oder zu wenig Felder", [],
       sorted(c for c, t in qr_texte.TEXTE.items() if set(t) != felder))
pruefe("kein Feld ist leer", [],
       sorted(f"{c}.{k}" for c, t in qr_texte.TEXTE.items()
              for k, v in t.items() if not v.strip()))
pruefe("eine unbekannte Sprache faellt auf Englisch", qr_texte.TEXTE["en"],
       qr_texte.fuer("xx"))
pruefe("die beiden Schriften von rechts nach links sind erkannt",
       ["ar", "fa"], sorted(c for c in qr_texte.SPRACHEN if qr_texte.rtl(c)))
# Jede Fassung nennt den Kern ihrer Aussage. Kein Ersatz fuer einen
# Muttersprachler -- aber es faengt eine Zeile, die beim Kopieren aus
# einer anderen Sprache stehengeblieben ist.
fremd = [c for c, t in qr_texte.TEXTE.items()
         if c not in ("de",) and t["geduld"] == qr_texte.TEXTE["de"]["geduld"]]
pruefe("keine Fassung ist eine Kopie der deutschen", [], fremd)
pruefe("ungeprueft ist als solches vermerkt", ("de",), qr_texte.GEPRUEFT)


print("\n\033[1m== 2) Die Seite, vom Server geholt\033[0m")
ARBEIT = Path(tempfile.mkdtemp(prefix="devarenu-qr-"))
lauf = None


def hole(weg):
    with urllib.request.urlopen(
            f"http://127.0.0.1:{PORT}{weg}", timeout=30) as a:
        return a.read().decode("utf-8", "replace")


def stelle(weg, daten):
    b = urllib.request.Request(f"http://127.0.0.1:{PORT}{weg}",
                               data=json.dumps(daten).encode("utf-8"),
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(b, timeout=30) as a:
        return a.read().decode("utf-8", "replace")


def sprachliste(html):
    m = re.search(r"const SPRACHEN = (\[.*?\]);", html, re.S)
    return json.loads(m.group(1)) if m else []


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
    for v in (".venv", "voices", "models"):
        if (WURZEL / v).exists():
            (ARBEIT / v).symlink_to(WURZEL / v)

    # Erfundene Zugangsdaten. Die echten stehen in der Arbeitskopie und
    # werden hier nicht angefasst.
    (ARBEIT / "zustand.json").write_text(json.dumps({
        "fassung": 3, "quelle": "de", "ziele": ["en", "ru", "fa"],
        "wlan": {"ssid": "Pruefnetz", "passwort": "Nur-Ein-Test-1234"},
    }), encoding="utf-8")
    os.chmod(ARBEIT / "zustand.json", 0o600)

    lauf = subprocess.Popen(
        [str(ARBEIT / ".venv/bin/python"), "server.py",
         "--port", str(PORT), "--nur-text"],
        cwd=ARBEIT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(90):
        try:
            hole("/api/sprachen")
            break
        except Exception:
            time.sleep(1)
    else:
        print(f"   {ROT}FEHL{AUS}  der Server kam nicht hoch")
        FEHLER += 1
        raise SystemExit

    seite = hole("/qr")
    codes = [s["code"] for s in sprachliste(seite)]

    pruefe("die Ausgangssprache steht NICHT im Durchlauf", False, "de" in codes)
    pruefe("die eingeschalteten Zielsprachen schon", True,
           all(c in codes for c in ("en", "ru", "fa")))
    pruefe("Englisch ist dabei", True, "en" in codes)
    pruefe("kein Platzhalter blieb stehen", [],
           re.findall(r"<!--[A-Z]+-->", seite))
    pruefe("das Passwort steht im Klartext auf der Seite", True,
           "Nur-Ein-Test-1234" in seite)
    pruefe("der Netzname auch", True, "Pruefnetz" in seite)
    # Zwei auf dem Bildschirm, dazu zwei je Druckseite: der Drucksatz
    # wiederholt sie, damit jedes Blatt fuer sich brauchbar ist.
    pruefe("die Codes sind eingebettet, auch auf jeder Druckseite",
           2 + 2 * len(codes), seite.count('src="data:image/svg'))
    pruefe("die Schreibrichtung steht je Sprache dabei", True,
           any(s["rtl"] for s in sprachliste(seite)))
    pruefe("gedruckt gibt es eine Seite je Sprache", len(codes),
           seite.count("class=druckseite"))

    # Ohne Zielsprachen: nur Englisch, und die Seite bleibt heil.
    # Ueber das Pult umstellen, nicht ueber die Datei -- die Seite liest
    # den laufenden Dienst, und so tut es das Pult auch.
    stelle("/api/sprachwahl", {"quelle": "de", "ziele": []})
    stelle("/api/wlan", {"ssid": "", "passwort": ""})
    seite2 = hole("/qr")
    pruefe("ohne Zielsprachen bleibt Englisch", ["en"],
           [s["code"] for s in sprachliste(seite2)])
    # Nicht auf "steht eine 1 da" pruefen -- die steht auch im
    # WLAN-Schritt selbst, und die Zusicherung waere immer erfuellt.
    pruefe("ohne WLAN-Daten faellt der erste Schritt weg", 1,
           seite2.count("class=schritt"))
    pruefe("und der verbliebene traegt die 1", True,
           "<span class=nr>1</span>" in seite2)
    pruefe("mit WLAN-Daten sind es zwei", 2, seite.count("class=schritt"))

    print("\n   -- die eigenstaendige Datei --")
    datei = hole("/qr?herunterladen=1")
    aussen = [v for v in re.findall(r'(?:src|href)="([^"]*)"', datei)
              if not v.startswith(("data:", "javascript:", "#"))]
    pruefe("sie laedt nichts nach", [], aussen)
    pruefe("das Logo steckt darin", True, 'src="data:image/png' in datei)
    pruefe("die Verweise auf PNG-Dateien sind weg", False,
           "/qr.png" in datei)

finally:
    if lauf and lauf.poll() is None:
        lauf.terminate()
        try:
            lauf.wait(timeout=10)
        except subprocess.TimeoutExpired:
            lauf.kill()
    shutil.rmtree(ARBEIT, ignore_errors=True)

print()
if FEHLER:
    print(f"{ROT}{FEHLER} Fehler.{AUS}")
    sys.exit(1)
print(f"{GRUEN}Alle Faelle wie erwartet.{AUS}")
