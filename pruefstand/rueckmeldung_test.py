#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Zaehlt die Rueckmeldung nur, und wirklich nur?

    python pruefstand/rueckmeldung_test.py

Die eine Frage, die hier zaehlt: steht in der Datei irgendetwas, das
auf einen Menschen zeigt? Zwei Zahlen je Sprache und Tag sind
unbedenklich. Eine Liste von Zeitpunkten waere es nicht -- wer um
10:14 in Farsi "schwer verstaendlich" gedrueckt hat, war der eine
Mann in der dritten Reihe.
"""
import sys
import tempfile
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))

import rueckmeldung                                     # noqa: E402

fehler = 0


def pruefe(was, erwartet, ist):
    global fehler
    if erwartet == ist:
        print(f"   ok    {was}")
    else:
        fehler += 1
        print(f"   FEHLER {was}: erwartet {erwartet!r}, ist {ist!r}")


ordner = Path(tempfile.mkdtemp(prefix="devarenu-rueck-"))
rueckmeldung.DATEI = ordner / "rueckmeldung.csv"
rueckmeldung._zaehler.clear()

print("\n1. Zaehlen")
rueckmeldung.zaehlen("en", "gut")
rueckmeldung.zaehlen("en", "gut")
rueckmeldung.zaehlen("ru", "schwer")
s = rueckmeldung.stand()
pruefe("zwei Mal gut auf Englisch", 2, s["en"]["gut"])
pruefe("einmal schwer auf Russisch", 1, s["ru"]["schwer"])
pruefe("Englisch hat kein schwer", 0, s["en"]["schwer"])

print("\n2. Wer sich umentscheidet, zaehlt nicht doppelt")
rueckmeldung.zaehlen("en", "schwer", vorher="gut")
s = rueckmeldung.stand()
pruefe("gut geht zurueck", 1, s["en"]["gut"])
pruefe("schwer kommt dazu", 1, s["en"]["schwer"])

print("\n3. Unsinn aendert nichts")
vorher = rueckmeldung.stand()
rueckmeldung.zaehlen("en", "vielleicht")
rueckmeldung.zaehlen("", "gut")
pruefe("unbekannter Wert wird nicht gezaehlt", vorher, rueckmeldung.stand())
# Ein Zurueckgehen unter null gibt es nicht.
rueckmeldung._zaehler.clear()
rueckmeldung.zaehlen("fa", "gut", vorher="schwer")
pruefe("kein negativer Zaehler", 0, rueckmeldung.stand()["fa"]["schwer"])

print("\n4. In der Datei steht nichts ueber Menschen")
inhalt = rueckmeldung.DATEI.read_text(encoding="utf-8")
print("   " + inhalt.replace("\n", "\n   ").rstrip())
kopf = inhalt.splitlines()[0]
pruefe("die Spalten sind Datum, Sprache und zwei Zahlen",
       "datum;sprache;verstaendlich;schwer", kopf)
for verboten in (":", "uhr", "ip", "10.0.0", "agent", "id"):
    pruefe(f"kein {verboten!r} in der Datei", True,
           verboten not in inhalt.lower())
zeilen = inhalt.splitlines()[1:]
pruefe("eine Zeile je Sprache und Tag", True,
       all(len(z.split(";")) == 4 for z in zeilen))

print("\n5. Neu geladen stehen dieselben Zahlen da")
rueckmeldung._zaehler.clear()
pruefe("aus der Datei zurueckgelesen", 1, rueckmeldung.stand()["fa"]["gut"])

print("\n6. Eine unlesbare Datei haelt den Gottesdienst nicht auf")
rueckmeldung.DATEI.write_text("kaputt\x00\x00", encoding="utf-8")
rueckmeldung._zaehler.clear()
pruefe("faengt dann bei null an", {}, rueckmeldung.stand())
rueckmeldung.zaehlen("de", "gut")
pruefe("und zaehlt weiter", 1, rueckmeldung.stand()["de"]["gut"])

if fehler:
    print(f"\n{fehler} FEHLER")
    sys.exit(1)
print("\nAlle Faelle wie erwartet.")
