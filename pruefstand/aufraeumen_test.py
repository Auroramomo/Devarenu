#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Raeumen die Pruefstaende ihre Wegwerfordner wieder weg?

    .venv/bin/python pruefstand/aufraeumen_test.py

Bis 0.4.5 lagen auf dem Arbeitsrechner ueber 700 Ordner unter /tmp,
die Pruefstaende angelegt und nie entfernt hatten -- devarenu-schwelle-*
allein 520, rund zwanzig je Lauf. Wer das ein Jahr lang laufen laesst,
fuellt sich die Platte mit Muell, den niemand mehr zuordnen kann.

Zwei Teile:

  1. hilfe.wegwerfordner() selbst: der Ordner verschwindet, auch
     wenn der Lauf mit sys.exit(1) endet oder eine Ausnahme bis oben
     durchschlaegt. Genau das ist "auch wenn ein Test fehlschlaegt".
  2. Jeder Pruefstand, der solche Ordner anlegt, wird einmal laufen
     gelassen, und hinterher liegt unter /tmp kein einziger Ordner
     seines Praefixes mehr als vorher.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
WURZEL = HIER.parent
PY = str(WURZEL / ".venv" / "bin" / "python")
TMP = Path(tempfile.gettempdir())

GRUEN, ROT, AUS = "\033[32m", "\033[31m", "\033[0m"
FEHLER = 0


def pruefe(was, erwartet, ist):
    global FEHLER
    if erwartet == ist:
        print(f"   ok    {was}")
    else:
        print(f"   {ROT}FEHL{AUS}  {was}: erwartet {erwartet!r}, ist {ist!r}")
        FEHLER += 1


def titel(t):
    print(f"\n\033[1m== {t}\033[0m")


def kind(code):
    """Ein Python-Lauf mit hilfe.wegwerfordner; gibt (rc, ordner) zurueck."""
    vorspann = (f"import sys; sys.path.insert(0, {str(HIER)!r}); "
                "from hilfe import wegwerfordner; "
                "o = wegwerfordner('devarenu-aufraeumprobe-'); "
                "(o / 'x').write_text('x'); print(o, flush=True); ")
    p = subprocess.run([PY, "-c", vorspann + code],
                       capture_output=True, text=True, timeout=60)
    ordner = Path(p.stdout.strip().splitlines()[0]) if p.stdout.strip() else None
    return p.returncode, ordner


titel("1) Der Helfer raeumt auf, auch im Fehlerfall")
for wie, code, rc_erwartet in [
        ("normales Ende", "pass", 0),
        ("sys.exit(1), wie ein roter Pruefstand", "sys.exit(1)", 1),
        ("Ausnahme bis oben", "raise RuntimeError('absichtlich')", 1),
        ("assert scheitert", "assert False", 1)]:
    rc, ordner = kind(code)
    pruefe(f"{wie}: Rueckgabe {rc_erwartet}", rc_erwartet, rc)
    pruefe(f"{wie}: der Ordner ist weg", False,
           bool(ordner) and ordner.exists())

titel("2) Die Pruefstaende hinterlassen nichts")
# Praefix -> Pruefstand. Wer hier einen neuen Pruefstand mit einem
# Wegwerfordner unter /tmp anlegt, traegt ihn ein.
PRUEFSTAENDE = {
    "rueckmeldung_test.py": ["devarenu-rueck-"],
    "schwellenmodus_test.py": ["devarenu-schwelle-"],
    "grafikwacht_test.py": ["devarenu-gpu-"],
    "stimmenbefund_test.py": ["devarenu-stimmen-", "devarenu-halb-"],
    "bericht_test.py": ["devarenu-bericht-"],
    "teile_test.py": ["devarenu-teile-"],
}


def zaehlen(praefixe):
    return sum(1 for p in praefixe for _ in TMP.glob(p + "*"))


for datei, praefixe in PRUEFSTAENDE.items():
    vorher = zaehlen(praefixe)
    p = subprocess.run([PY, str(HIER / datei)], cwd=WURZEL,
                       capture_output=True, text=True, timeout=600)
    nachher = zaehlen(praefixe)
    pruefe(f"{datei} laeuft", 0, p.returncode)
    pruefe(f"{datei} hinterlaesst keinen Ordner", 0, nachher - vorher)

# Und kein Pruefstand legt mehr einen Ordner OHNE Praefix an: der
# liesse sich hinterher keinem mehr zuordnen.
ohne = []
for q in sorted(HIER.glob("*_test.py")):
    # Diese Datei nicht: sie nennt das Muster, nach dem sie sucht.
    if q.name == Path(__file__).name:
        continue
    text = q.read_text(encoding="utf-8")
    if "tempfile.mkdtemp()" in text:
        ohne.append(q.name)
pruefe("kein mkdtemp() ohne Praefix", [], ohne)

print()
if FEHLER:
    print(f"{ROT}{FEHLER} Fehler.{AUS}")
    sys.exit(1)
print(f"{GRUEN}Alle Faelle wie erwartet.{AUS}")
