#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Der Befund "stimme_fehlt" -- und warum er ein HINWEIS ist.

    python pruefstand/stimmenbefund_test.py

Fehlt zu einer EINGESCHALTETEN Sprache die Stimme, laeuft sie am
Sonntag als Untertitel, ohne Ton. Bis 0.4.1 stand das nur im Journal.

Die Stufe ist HINWEIS, nicht FEHLT, und das ist eine Entscheidung mit
Narben: mit FEHLT rollte der Gesundheitscheck nach JEDEM Update
zurueck -- er wertet einen neuen FEHLT-Befund als "der Rechner ist
nach dem Update nicht gesund". Eine Gemeinde, der eine Stimme fehlt,
haette damit nie wieder ein Update bekommen, und ausgerechnet das
Update haette die Stimme mitgebracht. Gefunden im Einspielweg von
0.4.2: alle drei Wege rollten zurueck.
"""
import json
import sys
import tempfile
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))

import config                                            # noqa: E402
import systemcheck                                       # noqa: E402

fehler = 0


def pruefe(was, erwartet, ist):
    global fehler
    if erwartet == ist:
        print(f"   ok    {was}")
    else:
        fehler += 1
        print(f"   FEHLER {was}: erwartet {erwartet!r}, ist {ist!r}")


def befund(gewaehlt, vorhanden):
    """Ruft _stimmen mit gestellter Lage auf."""
    import zustand as zustandsdatei
    ordner = Path(tempfile.mkdtemp(prefix="devarenu-stimmen-"))
    (ordner / "voices").mkdir()
    for name in vorhanden:
        (ordner / "voices" / f"{name}.onnx").write_text("x")
        (ordner / "voices" / f"{name}.onnx.json").write_text("{}")
    alt_basis, alt_laden = config.BASIS, zustandsdatei.laden
    config.BASIS = ordner
    zustandsdatei.laden = lambda: (
        {"quelle": gewaehlt[0], "ziele": list(gewaehlt[1:])}, "pruefstand")
    try:
        b = []
        systemcheck._stimmen(b)
        return b
    finally:
        config.BASIS, zustandsdatei.laden = alt_basis, alt_laden


ROSTOCK = ["de", "en", "ru", "fa"]
ALLE_DA = [Path(config.STIMMEN[sp]).name for sp in ROSTOCK]

print("\n1. Alles da -- kein Befund")
pruefe("kein Befund", [], befund(ROSTOCK, ALLE_DA))

print("\n2. Farsi fehlt")
ohne_fa = [n for n in ALLE_DA if not n.startswith("fa_")]
b = befund(ROSTOCK, ohne_fa)
pruefe("genau ein Befund", 1, len(b))
pruefe("er nennt die Sprache", True, "fa" in b[0].was)
pruefe("und sagt, was das heisst", True, "Untertitel" in b[0].was)
pruefe("er nennt einen Weg", True, len(b[0].tun) > 10)

print("\n3. Die Stufe -- der Grund steht im Kopf dieser Datei")
pruefe("HINWEIS, nicht FEHLT", systemcheck.HINWEIS, b[0].schwere)
pruefe("der Gesundheitscheck rollt deshalb NICHT zurueck", False,
       b[0].schwere == systemcheck.FEHLT)

print("\n4. Er gehoert NICHT in die reine Wartungsliste")
# Wartungsbefunde stehen nur unter Fehlersuche. Eine fehlende Stimme
# geht den Sonntag an und muss am Pult sichtbar sein.
pruefe("nicht als Wartung einsortiert", False,
       "stimme_fehlt" in systemcheck.WARTUNG)

print("\n5. Eine Sprache, die gar nicht gewaehlt ist, zaehlt nicht")
# Dass fuer Georgisch keine Stimme daliegt, geht eine Gemeinde nichts
# an, die Georgisch nicht anbietet.
pruefe("Georgisch ohne Stimme, aber nicht gewaehlt: kein Befund",
       [], befund(["de", "en"], [Path(config.STIMMEN[s]).name
                                 for s in ("de", "en")]))

print("\n6. Eine Sprache ohne eingetragene Stimme zaehlt auch nicht")
# Sprachen ohne Stimme laufen absichtlich als Untertitel. Das ist
# kein Mangel, sondern die Einstellung.
alt = dict(config.STIMMEN)
try:
    config.STIMMEN = dict(alt, xx="")
    pruefe("leerer Eintrag ergibt keinen Befund", [],
           befund(["de", "xx"], [Path(alt["de"]).name]))
finally:
    config.STIMMEN = alt

print("\n7. Nur die halbe Stimme ist auch keine")
# Ohne die Beschreibung laedt Piper nicht. Eine Sprache, die am Pult
# waehlbar ist und stumm bleibt, ist der Fall, um den es geht.
ordner = Path(tempfile.mkdtemp(prefix="devarenu-halb-"))
(ordner / "voices").mkdir()
name = Path(config.STIMMEN["de"]).name
(ordner / "voices" / f"{name}.onnx").write_text("x")   # ohne .json
alt_basis = config.BASIS
import zustand as zustandsdatei                          # noqa: E402
alt_laden = zustandsdatei.laden
config.BASIS = ordner
zustandsdatei.laden = lambda: ({"quelle": "de", "ziele": []}, "pruefstand")
try:
    b = []
    systemcheck._stimmen(b)
    pruefe("fehlende Beschreibung gilt als fehlende Stimme", 1, len(b))
finally:
    config.BASIS, zustandsdatei.laden = alt_basis, alt_laden

if fehler:
    print(f"\n{fehler} FEHLER")
    sys.exit(1)
print("\nAlle Faelle wie erwartet.")
