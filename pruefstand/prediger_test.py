#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Buch oder Mensch? Die Kollision "Prediger" im Glossar.

    python pruefstand/prediger_test.py

"Prediger" heisst im Deutschen zweierlei: das Bibelbuch (A021,
Ecclesiastes) und die Person auf der Kanzel (D028, pastor). Bis 0.4.1
gewann immer das Buch, weil nur A021 die blosse Form als Suchvariante
trug. Gemessen im Vergleichslauf zu 0.4.2 E:

    "Und dieser Prediger wollte darueber predigen."
    ->  "And this Ecclesiastes wanted to preach about trusting in God."

Seit 0.4.2 greift A021 nur noch im Stellenzusammenhang: mit
Kapitelzahl, als "Buch Prediger" oder als "Prediger Salomo". Sonst
gilt D028.

Die gegengelesenen Uebersetzungen sind dabei NICHT angefasst worden --
nur die Bedingung, unter der eine Zeile ueberhaupt greift.
"""
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))

import config                                            # noqa: E402
from glossar import Glossar                              # noqa: E402

fehler = 0


def pruefe(was, erwartet, ist):
    global fehler
    if erwartet == ist:
        print(f"   ok    {was}")
    else:
        fehler += 1
        print(f"   FEHLER {was}: erwartet {erwartet}, ist {ist}")


g = Glossar.laden(config.GLOSSAR_CSV)


def wer(text):
    """A021 (Buch), D028 (Person) oder None."""
    ids = [e.id for e in g.finde(text) if e.id in ("A021", "D028")]
    return ids[0] if ids else None


# -------------------------------------------------- das Buch
BUCH = [
    "Wir lesen heute Prediger 3,1.",
    "Pred 3,1 steht am Anfang.",
    "Der Predigttext steht in Prediger 12.",
    "Pred 12 ist das letzte Kapitel.",
    "Im Buch Prediger steht ein harter Satz.",
    "Prediger Salomo hat das aufgeschrieben.",
    "Kohelet nennt man es auch.",
    "Schlagt bitte Prediger 1 auf.",
    "Pred 7 und Psalm 32 gehoeren zusammen.",
    "Prediger 9,11 kennt jeder.",
    "Das Buch Prediger und das Hohelied stehen nebeneinander.",
    "In Prediger 4 geht es um Gemeinschaft.",
]

# -------------------------------------------------- die Person
PERSON = [
    "Und dieser Prediger wollte darueber predigen.",
    "Und dieser Prediger war bekannt.",
    "Der Prediger machte sich bereit, seine Sachen zu packen.",
    "Ein Prediger aus einem fernen Dorf kam zu Besuch.",
    "Unser Prediger ist heute krank.",
    "Die Gemeinde hoerte dem Prediger zu.",
    "Der Prediger stieg auf die Kanzel.",
    "Jeder Prediger kennt diese Stelle.",
    "Dem Prediger wurde das Kamel gestohlen.",
    "Zwei Prediger sprachen nacheinander.",
    "Pastor und Prediger meinen dasselbe.",
    "Danach ging der Prediger nach Hause.",
]

print(f"\n1. Das Buch ({len(BUCH)} Saetze) -- A021")
for t in BUCH:
    pruefe(repr(t[:58]), "A021", wer(t))

print(f"\n2. Die Person ({len(PERSON)} Saetze) -- D028")
for t in PERSON:
    pruefe(repr(t[:58]), "D028", wer(t))

print("\n3. Die Uebersetzungen sind nicht angefasst")
# Genau das war die Bedingung: nur die Bedingung aendern, nicht die
# gegengelesenen Werte.
alt = Glossar.laden(WURZEL / "glossar_v1.0.csv")
nach_id = {e.id: e for e in alt.eintraege}
for kennung in ("A021", "D028"):
    neu = next(e for e in g.eintraege if e.id == kennung)
    a = nach_id[kennung]
    pruefe(f"{kennung}: Zielsprachen gleich", a.ziel, neu.ziel)
    pruefe(f"{kennung}: Konfidenzen gleich", a.konfidenz, neu.konfidenz)
    pruefe(f"{kennung}: deutsche Hauptform gleich", a.de, neu.de)

print("\n4. Die Bedingung selbst")
a021 = next(e for e in g.eintraege if e.id == "A021")
d028 = next(e for e in g.eintraege if e.id == "D028")
pruefe("A021 traegt die blosse Form NICHT mehr", False,
       "Prediger" in a021.varianten)
pruefe("D028 traegt sie", True, "Prediger" in d028.varianten)
pruefe('"der Prediger" ist weg -- es waere laenger als "Prediger 3" '
       "und haette den Stellenzusammenhang geschlagen", False,
       "der Prediger" in d028.varianten)
pruefe("alle zwoelf Kapitel sind aufgezaehlt", True,
       all(f"Prediger {n}" in a021.varianten for n in range(1, 13)))
pruefe("auch abgekuerzt", True,
       all(f"Pred {n}" in a021.varianten for n in range(1, 13)))

gesamt = len(BUCH) + len(PERSON)
print(f"\n{gesamt} Saetze geprueft.")
if fehler:
    print(f"{fehler} FEHLER")
    sys.exit(1)
print("Alle Faelle wie erwartet.")
