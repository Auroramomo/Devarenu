#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Uebersteht der Schwellenmodus den Neustart -- und das Update?

    python pruefstand/schwellenmodus_test.py

Bis 0.4.0 kannte der Server zwei Zustaende, und beide steckten in einer
Zahl: None hiess mitlaufend, alles andere festgenagelt. Der Helfer in
Rostock stellte den Regler jeden Gottesdienst auf null, weil mit
Schwelle mehr Erkennungsfehler kamen -- der Server machte daraus die
kleinste feste Schwelle, 0.0005. Sein Wunsch war nie gespeichert,
sondern jedes Mal neu getippt, und beim naechsten Einmessen weg.

Geprueft wird ohne Tongeraet und ohne Modell: nur zustand.py und der
Segmentierer.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))

fehler = 0


def pruefe(was, bedingung, einzelheit=""):
    global fehler
    if bedingung:
        print(f"   ok    {was}")
    else:
        fehler += 1
        print(f"   FEHLER {was}" + (f"  -> {einzelheit}" if einzelheit else ""))


def frisch_laden(inhalt):
    """Schreibt eine zustand.json und laedt sie mit einem frischen Modul."""
    ordner = tempfile.mkdtemp(prefix="devarenu-schwelle-")
    pfad = Path(ordner) / "zustand.json"
    if inhalt is not None:
        pfad.write_text(json.dumps(inhalt), encoding="utf-8")
    for name in ("zustand",):
        sys.modules.pop(name, None)
    import zustand                                       # noqa: E402
    zustand.DATEI = pfad
    daten, woher = zustand.laden()
    return zustand, daten, woher, pfad


print("\n1. Vorgabe ohne zustand.json")
z, daten, woher, _ = frisch_laden(None)
pruefe('Vorgabe ist "aus"', daten["schwelle"]["modus"] == "aus",
       daten["schwelle"])
pruefe('grundmodus ist "aus"', daten["schwelle"]["grundmodus"] == "aus")
pruefe("kein fester Wert", daten["schwelle"]["wert"] is None)

print("\n2. Alte Datei, Regler stand auf null (0.0005)")
z, daten, woher, _ = frisch_laden(
    {"fassung": 3, "schwelle": {"wert": 0.0005, "gemessen": "2026-09-28 09:41:00"}})
pruefe('wird zu "aus"', daten["schwelle"]["modus"] == "aus",
       daten["schwelle"])
pruefe("der Wert faellt weg", daten["schwelle"]["wert"] is None)
pruefe("der Zeitstempel faellt mit weg",
       daten["schwelle"]["gemessen"] is None)

print("\n2b. Dasselbe mit Werten UNTER 0,0005")
# zustand.py klemmt beim Lesen auf 0.0005 ab. Ein von Hand
# eingetragenes 0.0001 ist derselbe Wunsch: keine Schwelle.
for wert in (0.0001, 0.00025, 0.0004, 0.0005):
    z, daten, woher, _ = frisch_laden(
        {"fassung": 3, "schwelle": {"wert": wert, "gemessen": None}})
    pruefe(f'{wert} wird "aus"', daten["schwelle"]["modus"] == "aus",
           daten["schwelle"])
# Knapp darueber ist eine Entscheidung und bleibt eine.
z, daten, woher, _ = frisch_laden(
    {"fassung": 3, "schwelle": {"wert": 0.0006, "gemessen": None}})
pruefe('0.0006 bleibt "fest"', daten["schwelle"]["modus"] == "fest",
       daten["schwelle"])

print("\n3. Alte Datei, echte eingemessene Schwelle")
z, daten, woher, _ = frisch_laden(
    {"fassung": 3, "schwelle": {"wert": 0.0120, "gemessen": "2026-09-28 09:41:00"}})
pruefe('bleibt "fest"', daten["schwelle"]["modus"] == "fest",
       daten["schwelle"])
pruefe("der Wert bleibt stehen", daten["schwelle"]["wert"] == 0.012)
pruefe('Geraetewechsel faellt auf "automatisch" zurueck -- wie bisher',
       daten["schwelle"]["grundmodus"] == "automatisch")

print("\n4. Alte Datei, mitlaufende Schwelle")
z, daten, woher, _ = frisch_laden({"fassung": 3, "schwelle": {"wert": None}})
pruefe('wird "automatisch", nicht "aus"',
       daten["schwelle"]["modus"] == "automatisch", daten["schwelle"])

print("\n5. Modus uebersteht Speichern und Neuladen")
z, daten, woher, pfad = frisch_laden({"fassung": 4,
                                      "schwelle": {"wert": None,
                                                   "gemessen": None,
                                                   "modus": "aus",
                                                   "grundmodus": "aus"}})
daten["schwelle"]["modus"] = "automatisch"
daten["schwelle"]["grundmodus"] = "automatisch"
z.speichern(daten)
z2, daten2, _, _2 = frisch_laden(json.loads(pfad.read_text(encoding="utf-8")))
pruefe('"automatisch" steht nach dem Neuladen noch da',
       daten2["schwelle"]["modus"] == "automatisch", daten2["schwelle"])

print("\n6. Unbrauchbarer Modus kostet nur sich selbst")
z, daten, woher, _ = frisch_laden(
    {"fassung": 4, "schwelle": {"wert": 0.02, "modus": "irgendwas",
                                "grundmodus": "aus"}})
pruefe("der Wert bleibt", daten["schwelle"]["wert"] == 0.02)
pruefe("der Modus faellt auf die Vorgabe",
       daten["schwelle"]["modus"] == "aus", daten["schwelle"])
pruefe('"grundmodus": "fest" wird nicht angenommen',
       frisch_laden({"fassung": 4,
                     "schwelle": {"wert": None, "grundmodus": "fest"}}
                    )[1]["schwelle"]["grundmodus"] == "aus")

# ------------------------------------------------- Segmentierer
print("\n7. Der Segmentierer rechnet nach dem Modus")
import server                                            # noqa: E402

seg = server.Segmentierer()
seg.grundpegel = 0.010
seg.modus_setzen("aus")
pruefe('"aus" ist die Stilleschwelle, nicht null',
       abs(seg.schwelle - server.Segmentierer.AUS_SCHWELLE) < 1e-9,
       seg.schwelle)
seg.modus_setzen("automatisch")
pruefe('"automatisch" folgt dem Grundpegel',
       abs(seg.schwelle - 0.010 * 3.5) < 1e-9, seg.schwelle)
seg.modus_setzen("fest", 0.02)
pruefe('"fest" nimmt den Wert', abs(seg.schwelle - 0.02) < 1e-9, seg.schwelle)
pruefe('grundmodus bleibt bei "automatisch"',
       seg.grundmodus == "automatisch", seg.grundmodus)
seg.modus_setzen("fest", None)
pruefe('"fest" ohne Wert aendert nichts', seg.modus == "fest")
seg.modus_setzen("aus")
pruefe("Umschalten loescht den festen Wert", seg.feste_schwelle is None)

print("\n8. Geraetewechsel faellt auf den Grundmodus")
seg = server.Segmentierer()
seg.modus_setzen("aus")          # die Gemeinde faehrt ohne Schwelle
seg.modus_setzen("fest", 0.03)   # jemand misst einmal ein
pruefe("danach ist fest", seg.modus == "fest")
seg.modus_setzen(seg.grundmodus)  # das tut der Geraetewechsel
pruefe('zurueck auf "aus", nicht auf "automatisch"', seg.modus == "aus",
       seg.modus)

print("\n9. Einmessen setzt den Modus auf fest")
seg = server.Segmentierer()
seg.modus_setzen("aus")
seg.messung = {"bis": 0, "werte": [0.002] * 60 + [0.05] * 60}
erg = seg.einmessen_auswerten()
pruefe("Einmessen gelingt", bool(erg and erg.get("erfolg")), erg)
pruefe('Modus ist danach "fest"', seg.modus == "fest", seg.modus)
pruefe('grundmodus bleibt "aus"', seg.grundmodus == "aus", seg.grundmodus)

if fehler:
    print(f"\n{fehler} FEHLER")
    sys.exit(1)
print("\nAlles in Ordnung.")
