#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Schreibt das Testprotokoll nur mit Einwilligung -- und haelt nichts auf?

    python pruefstand/pruefprotokoll_test.py

Zwei Dinge stehen auf dem Spiel. Im Protokoll steht der Predigttext,
Wort fuer Wort, in allen Sprachen -- es darf also nur mit Einwilligung
entstehen, nur am Rechner selbst lesbar sein und nach sieben Tagen
verschwinden. Und es haengt mitten in der Segmentschleife: ein Fehler
beim Schreiben darf die Uebersetzung NIE anhalten.
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))

import aufnahme          # noqa: E402
import pruefprotokoll    # noqa: E402

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


ERGEBNISSE = [
    {"sprache": "en", "text": "In the beginning", "mt": 0.41,
     "tts": 0.22, "dauer": 1.8},
    {"sprache": "ru", "text": "В начале", "mt": 0.55, "tts": 0.31,
     "dauer": 2.1},
]

titel("1) Ohne Einwilligung faengt nichts an")

with tempfile.TemporaryDirectory() as o:
    p = pruefprotokoll.Protokoll(Path(o) / "pp")
    pruefe("gar nichts uebergeben", "einwilligung_fehlt",
           p.starten(None)[1])
    pruefe("leerer Haken", "einwilligung_fehlt",
           p.starten({"person_gefragt": False})[1])
    # Der zweite Haken der Aufnahme wird hier NICHT verlangt -- ein
    # Test laeuft nicht im Gottesdienst.
    pruefe("nur der zweite Haken genuegt nicht", "einwilligung_fehlt",
           p.starten({"nur_predigt": True})[1])
    pruefe("es laeuft nichts", False, p.laeuft)
    pruefe("und es liegt keine Datei", False, (Path(o) / "pp").exists())

    datei, fehler = p.starten({"person_gefragt": True})
    pruefe("mit dem ersten Haken geht es los", "", fehler)
    pruefe("und es laeuft", True, p.laeuft)

titel("2) Was in der Zeile steht")

with tempfile.TemporaryDirectory() as o:
    p = pruefprotokoll.Protokoll(Path(o) / "pp")
    datei, _ = p.starten({"person_gefragt": True})
    p.segment(7, "de", "Am Anfang", 4.2, 0.31, 1.44, ERGEBNISSE)
    zeile = json.loads(datei.read_text(encoding="utf-8").strip())

    pruefe("die Segmentnummer", 7, zeile["nummer"])
    pruefe("die Ausgangssprache", "de", zeile["quelle"])
    pruefe("der erkannte Satz", "Am Anfang", zeile["text"])
    pruefe("die Whisper-Dauer", 0.31, zeile["stt_s"])
    pruefe("die Tondauer", 4.2, zeile["audio_s"])
    pruefe("zwei Zielsprachen", 2, len(zeile["ziele"]))
    pruefe("die Uebersetzung", "В начале", zeile["ziele"][1]["text"])
    pruefe("die Dauer der Uebersetzung", 0.55, zeile["ziele"][1]["mt_s"])
    pruefe("die Dauer von Piper", 0.31, zeile["ziele"][1]["tts_s"])
    pruefe("ein Zeitstempel ist dabei", True, len(zeile["zeit"]) == 19)

    # Eine Ausnahme aus gather() gehoert ins Protokoll -- gerade sie:
    # sie ist der Fall, den man sucht.
    p.segment(8, "de", "Und Gott sprach", 3.0, 0.2, 0.9,
              [RuntimeError("Ollama antwortet nicht")])
    letzte = json.loads(datei.read_text(encoding="utf-8").strip()
                        .splitlines()[-1])
    pruefe("ein Fehler steht als Fehler darin", True,
           "Ollama" in letzte["ziele"][0]["fehler"])

titel("3) Ein Fehler hier haelt die Uebersetzung nicht auf")

with tempfile.TemporaryDirectory() as o:
    p = pruefprotokoll.Protokoll(Path(o) / "pp")
    datei, _ = p.starten({"person_gefragt": True})
    # Die Platte ist weg, die Datei nicht mehr zu beschreiben.
    datei.unlink()
    (Path(o) / "pp").chmod(0o500)
    try:
        p.segment(9, "de", "weiter", 3.0, 0.2, 0.9, ERGEBNISSE)
        pruefe("segment() wirft nichts", True, True)
    except Exception as e:
        pruefe("segment() wirft nichts", True, f"warf {e!r}")
    finally:
        (Path(o) / "pp").chmod(0o700)
    pruefe("aber es steht danach da, was war", True, bool(p.fehler))
    pruefe("und die Lage nennt es", True, bool(p.lage()["fehler"]))

    # Unsinn in den Ergebnissen darf ebenfalls nichts umwerfen.
    p2 = pruefprotokoll.Protokoll(Path(o) / "pp2")
    p2.starten({"person_gefragt": True})
    for murks in (None, "kein Ergebnis", [None], [{"sprache": None}]):
        try:
            p2.segment(1, "de", "x", 3.0, 0.1, 0.2, murks)
        except Exception as e:
            pruefe(f"Unsinn {murks!r} wirft nichts", True, f"warf {e!r}")
    pruefe("Unsinn in den Ergebnissen wirft nichts", True, True)

titel("4) Rechte, Vermerk und Frist")

with tempfile.TemporaryDirectory() as o:
    ordner = Path(o) / "pp"
    p = pruefprotokoll.Protokoll(ordner)
    datei, _ = p.starten({"person_gefragt": True})
    p.segment(1, "de", "x", 3.0, 0.1, 0.2, ERGEBNISSE)

    pruefe("der Ordner ist 700", "700", oct(ordner.stat().st_mode)[-3:])
    pruefe("die Datei ist 600", "600", oct(datei.stat().st_mode)[-3:])
    zettel = datei.with_suffix(".einwilligung.txt")
    pruefe("der Vermerk liegt daneben", True, zettel.exists())
    text = zettel.read_text(encoding="utf-8")
    pruefe("er nennt den Zeitpunkt", True, "Bestaetigt am" in text)
    pruefe("er nennt KEINEN Namen", True, "Kein Name vermerkt" in text)
    pruefe("er sagt, was darin steht", True, "Wort fuer Wort" in text)

    # Frist. Die Datei kuenstlich altern lassen.
    alt = time.time() - 9 * 86400
    os.utime(datei, (alt, alt))
    os.utime(zettel, (alt, alt))
    pruefe("tage=0 loescht NICHTS", [],
           pruefprotokoll.aufraeumen(ordner, tage=0))
    pruefe("die Datei liegt noch", True, datei.exists())
    weg = pruefprotokoll.aufraeumen(ordner, tage=7)
    pruefe("nach sieben Tagen ist sie faellig", 1, len(weg))
    pruefe("und weg", False, datei.exists())
    pruefe("der Vermerk geht mit", False, zettel.exists())

titel("5) Aus ist aus")

with tempfile.TemporaryDirectory() as o:
    p = pruefprotokoll.Protokoll(Path(o) / "pp")
    # Ohne Start schreibt segment() nichts und wirft nichts.
    p.segment(1, "de", "x", 3.0, 0.1, 0.2, ERGEBNISSE)
    pruefe("ohne Start entsteht kein Ordner", False, (Path(o) / "pp").exists())
    datei, _ = p.starten({"person_gefragt": True})
    p.segment(1, "de", "x", 3.0, 0.1, 0.2, ERGEBNISSE)
    lage = p.beenden()
    pruefe("beenden nennt die Zeilen", 1, lage["zeilen"])
    pruefe("danach laeuft nichts mehr", False, p.laeuft)
    vorher = datei.read_text(encoding="utf-8")
    p.segment(2, "de", "y", 3.0, 0.1, 0.2, ERGEBNISSE)
    pruefe("und es wird nichts mehr geschrieben", vorher,
           datei.read_text(encoding="utf-8"))

print()
if FEHLER:
    print(f"{ROT}{FEHLER} Fehler.{AUS}")
    sys.exit(1)
print(f"{GRUEN}Alle Faelle wie erwartet.{AUS}")
