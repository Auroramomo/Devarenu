#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Die Grafikwacht -- und vor allem: dass sie nichts aufhaelt.

    python pruefstand/grafikwacht_test.py

Eine Messung ist eine Auskunft, kein Betriebsteil. Fehlt nvidia-smi,
schlaegt es fehl, haengt es oder liefert Unsinn, darf davon nichts
weiter gehen als eine fehlende Zeile.
"""
import sys
import tempfile
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))
sys.path.insert(0, str(WURZEL / "pruefstand"))

import grafikwacht                                      # noqa: E402
from hilfe import wegwerfordner                         # noqa: E402

fehler = 0


def pruefe(was, erwartet, ist):
    global fehler
    if erwartet == ist:
        print(f"   ok    {was}")
    else:
        fehler += 1
        print(f"   FEHLER {was}: erwartet {erwartet!r}, ist {ist!r}")


grafikwacht.DATEI = wegwerfordner("devarenu-gpu-") / "g.csv"
grafikwacht._tage.clear()
echt = grafikwacht._lauf


def stellen(smi=None, ps=None):
    def _lauf(befehl, frist=8):
        if befehl[0] == "nvidia-smi":
            return smi
        if befehl[0] == "ollama":
            return ps
        return None
    grafikwacht._lauf = _lauf


print("\n1. Ohne nvidia-smi passiert nichts")
stellen(smi=None)
pruefe("karte() gibt None", None, grafikwacht.karte())
pruefe("einmal() gibt None", None, grafikwacht.einmal(4))
pruefe("und schreibt keine Datei", False, grafikwacht.DATEI.exists())
pruefe("anwerfen() startet keinen Faden", None,
       grafikwacht.anwerfen(lambda: True, lambda: 4))

print("\n2. Unsinn aus nvidia-smi wird nicht geglaubt")
for unsinn in ("", "kaputt\n", "a, b, c\n", "1,2\n"):
    stellen(smi=unsinn)
    pruefe(f"{unsinn!r} ergibt None", None, grafikwacht.karte())

print("\n3. Eine saubere Messung")
stellen(smi="10504, 16303, 7\n", ps="NAME ID SIZE PROCESSOR\n"
                                    "gemma4:12b x 8.1 GB 100% GPU\n")
m = grafikwacht.einmal(4)
pruefe("belegt", 10504, m["belegt"])
pruefe("gesamt", 16303, m["gesamt"])
pruefe("Last", 7, m["last"])
pruefe("ganz auf der Karte", False, m["cpu"])
h = grafikwacht.heute()
pruefe("Hoechstwert gemerkt", 10504, h["speicher_hoechst_mb"])
pruefe("Sprachen gemerkt", 4, h["sprachen"])
pruefe("kein CPU-Anteil", False, h["cpu_anteil"])

print("\n4. Hoechstwert bleibt der Hoechstwert")
stellen(smi="9000, 16303, 3\n", ps="gemma4:12b x 8.1 GB 100% GPU\n")
grafikwacht.einmal(4)
pruefe("niedrigere Messung senkt ihn nicht", 10504,
       grafikwacht.heute()["speicher_hoechst_mb"])
pruefe("der Mittelwert wandert mit", 5, grafikwacht.heute()["last_mittel"])

print("\n5. Teils auf der CPU wird erkannt")
for zeile, erwartet in (
        ("gemma4:12b x 8.1 GB 100% GPU\n", False),
        ("gemma4:12b x 8.1 GB 48%/52% CPU/GPU\n", True),
        ("gemma4:12b x 8.1 GB 100% CPU\n", True)):
    stellen(smi="1, 2, 3\n", ps="NAME\n" + zeile)
    pruefe(f"{zeile.strip()[-16:]!r}", erwartet, grafikwacht.modell_auf_cpu())
stellen(smi="1, 2, 3\n", ps="NAME ID SIZE PROCESSOR\n")
pruefe("Modell gar nicht geladen ergibt None -- kein Befund", None,
       grafikwacht.modell_auf_cpu())
stellen(smi="1, 2, 3\n", ps=None)
pruefe("ohne ollama ebenfalls None", None, grafikwacht.modell_auf_cpu())

print("\n6. Einmal CPU-Anteil bleibt stehen")
stellen(smi="12000, 16303, 90\n",
        ps="NAME\ngemma4:12b x 8.1 GB 48%/52% CPU/GPU\n")
grafikwacht.einmal(4)
pruefe("der Tag ist markiert", True, grafikwacht.heute()["cpu_anteil"])
stellen(smi="100, 16303, 1\n", ps="NAME\ngemma4:12b x 8.1 GB 100% GPU\n")
grafikwacht.einmal(4)
pruefe("und bleibt es", True, grafikwacht.heute()["cpu_anteil"])

print("\n7. In der Datei steht nichts ueber Menschen")
inhalt = grafikwacht.DATEI.read_text(encoding="utf-8")
print("   " + inhalt.replace("\n", "\n   ").rstrip())
pruefe("die Spalten sind, was sie sein sollen",
       ";".join(grafikwacht.SPALTEN), inhalt.splitlines()[0])
for verboten in ("10.0.0", "@", "uhr", "name"):
    pruefe(f"kein {verboten!r}", True, verboten not in inhalt.lower())

print("\n8. Neu geladen stehen dieselben Zahlen da")
grafikwacht._tage.clear()
pruefe("Hoechstwert zurueckgelesen", 12000,
       grafikwacht.heute()["speicher_hoechst_mb"])
pruefe("CPU-Anteil zurueckgelesen", True, grafikwacht.heute()["cpu_anteil"])

print("\n9. Eine unlesbare Datei haelt nichts auf")
grafikwacht.DATEI.write_text("kaputt\x00", encoding="utf-8")
grafikwacht._tage.clear()
pruefe("faengt bei nichts an", None, grafikwacht.heute())
stellen(smi="500, 16303, 2\n", ps="NAME\ngemma4:12b x 8.1 GB 100% GPU\n")
grafikwacht.einmal(2)
pruefe("und misst weiter", 500, grafikwacht.heute()["speicher_hoechst_mb"])

grafikwacht._lauf = echt
if fehler:
    print(f"\n{fehler} FEHLER")
    sys.exit(1)
print("\nAlle Faelle wie erwartet.")
