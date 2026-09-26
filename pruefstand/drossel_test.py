#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Haelt die Drossel den Saal in Schranken -- ohne den Zuhoerer zu treffen?

    python pruefstand/drossel_test.py

Zwei Teile: die Drossel fuer sich, und ein echter Server unter einer
Nachrichtenflut. Der wichtigste Fall ist der unauffaellige: ein
NORMALER Zuhoerer darf nichts davon merken. Eine Grenze, die im
Gottesdienst zuschlaegt, ist schlimmer als keine.
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

import drossel  # noqa: E402

GRUEN, ROT, AUS = "\033[32m", "\033[31m", "\033[0m"
FEHLER = 0
PORT = 8157


def pruefe(was, erwartet, ist):
    global FEHLER
    if erwartet == ist:
        print(f"   ok    {was}")
    else:
        print(f"   {ROT}FEHL{AUS}  {was}: erwartet {erwartet!r}, ist {ist!r}")
        FEHLER += 1


def titel(t):
    print(f"\n\033[1m== {t}\033[0m")


titel("1) Die Drossel")

d = drossel.Drossel()
t0 = 1000.0
pruefe("die erste Meldung geht durch", (True, ""), d.fragen("10.0.0.5", t0))
d.vermerken("10.0.0.5", t0)
pruefe("die zweite sofort danach nicht", "zu_schnell",
       d.fragen("10.0.0.5", t0 + 1)[1])
pruefe("nach fuenf Sekunden schon", True,
       d.fragen("10.0.0.5", t0 + 5.1)[0])
pruefe("ein anderes Geraet ist nicht betroffen", True,
       d.fragen("10.0.0.9", t0 + 1)[0])

# Ein normaler Zuhoerer: zwei Meldungen im ganzen Gottesdienst.
n = drossel.Drossel()
pruefe("normaler Zuhoerer, erste Meldung", True, n.fragen("10.0.0.7", t0)[0])
n.vermerken("10.0.0.7", t0)
pruefe("und eine halbe Stunde spaeter die zweite", True,
       n.fragen("10.0.0.7", t0 + 1800)[0])

# Die Tagesgrenze
v = drossel.Drossel()
for i in range(drossel.JE_GERAET):
    v.vermerken("10.0.0.8", t0 + i * 10)
pruefe("nach zwanzig ist Schluss", "zu_viele",
       v.fragen("10.0.0.8", t0 + 1000)[1])
pruefe("am naechsten Tag wieder erlaubt", True,
       v.fragen("10.0.0.8", t0 + 25 * 3600)[0])
pruefe("und die alten Zeiten sind vergessen", 0,
       v.stand("10.0.0.8", t0 + 25 * 3600))
pruefe("die Adresse ist aus der Liste", 0, len(v._zeiten))

titel("2) Kuerzen")

kurz, g = drossel.kuerzen("Der Ton ist zu leise.")
pruefe("ein normaler Satz bleibt ganz", False, g)
pruefe("und unveraendert", "Der Ton ist zu leise.", kurz)
lang, g = drossel.kuerzen("wort " * 100)
pruefe("ein Brief wird gekuerzt", True, g)
pruefe("auf hoechstens die Grenze", True, len(lang) <= drossel.LAENGE + 2)
pruefe("und endet sichtbar", True, lang.endswith("…"))
pruefe("nicht mitten im Wort", False, lang[-3:-2].isalpha() and
       not lang.rstrip("… ").endswith("wort"))
pruefe("leer bleibt leer", ("", False), drossel.kuerzen("   "))
pruefe("None auch", ("", False), drossel.kuerzen(None))


titel("3) Ein echter Server unter Beschuss")

ARBEIT = Path(tempfile.mkdtemp(prefix="devarenu-dr-"))
lauf = None


def schicken(text, weg="/api/nachricht"):
    b = urllib.request.Request(f"http://127.0.0.1:{PORT}{weg}")
    b.data = json.dumps({"text": text, "sprache": "de"}).encode("utf-8")
    b.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(b, timeout=20) as a:
            return a.status, json.loads(a.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except ValueError:
            return e.code, {}
    except Exception:
        return 0, {}


def lesen(weg):
    with urllib.request.urlopen(
            f"http://127.0.0.1:{PORT}{weg}", timeout=20) as a:
        return json.loads(a.read().decode("utf-8"))


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
    (ARBEIT / "zustand.json").write_text(
        json.dumps({"fassung": 3, "quelle": "de", "ziele": ["en"]}),
        encoding="utf-8")
    os.chmod(ARBEIT / "zustand.json", 0o600)

    lauf = subprocess.Popen(
        [str(ARBEIT / ".venv/bin/python"), "server.py",
         "--port", str(PORT), "--nur-text"],
        cwd=ARBEIT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(90):
        try:
            lesen("/api/sprachen")
            break
        except Exception:
            time.sleep(1)
    else:
        print(f"   {ROT}FEHL{AUS}  der Server kam nicht hoch")
        FEHLER += 1
        raise SystemExit

    st, d1 = schicken("Der Ton ist zu leise.")
    pruefe("die erste Meldung kommt an", 200, st)
    st, _ = schicken("Und noch eine.")
    pruefe("die zweite sofort danach wird abgewiesen", 429, st)

    # Eine Flut: hundert Meldungen so schnell es geht.
    codes = {}
    for i in range(100):
        st, _ = schicken(f"Flut {i}")
        codes[st] = codes.get(st, 0) + 1
    pruefe("keine einzige kam durch", 0, codes.get(200, 0))
    pruefe("alle wurden mit 429 abgewiesen", 100, codes.get(429, 0))

    zustand = lesen("/api/zustand")
    saal = [n for n in zustand["nachrichten"] if n.get("art") == "saal"]
    pruefe("im Briefkasten liegt genau eine", 1, len(saal))
    pruefe("und zwar die erste", "Der Ton ist zu leise.", saal[0]["text"])

    st, d2 = schicken("x" * 500)
    pruefe("ein Brief wird nicht angenommen, solange gedrosselt", 429, st)

    print("\n   -- Laenge --")
    # Warten, bis die Drossel wieder durchlaesst.
    time.sleep(drossel.ABSTAND + 0.5)
    st, d3 = schicken("y" * 500)
    pruefe("danach geht er durch", 200, st)
    pruefe("aber gekuerzt", True, d3.get("gekuerzt"))
    zustand = lesen("/api/zustand")
    lang = [n for n in zustand["nachrichten"] if n.get("text", "").startswith("y")]
    pruefe("im Briefkasten steht die kurze Fassung", True,
           len(lang[0]["text"]) <= drossel.LAENGE + 2)

finally:
    if lauf and lauf.poll() is None:
        lauf.terminate()
        try:
            lauf.wait(timeout=15)
        except subprocess.TimeoutExpired:
            lauf.kill()
    shutil.rmtree(ARBEIT, ignore_errors=True)

print()
if FEHLER:
    print(f"{ROT}{FEHLER} Fehler.{AUS}")
    sys.exit(1)
print(f"{GRUEN}Alle Faelle wie erwartet.{AUS}")
