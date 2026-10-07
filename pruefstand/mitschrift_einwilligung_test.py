#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Die Mitschrift im Journal braucht die Einwilligung (Nachtrag zu 0.5.0).

    .venv/bin/python pruefstand/mitschrift_einwilligung_test.py

Dieselbe wie beim Testprotokoll: die sprechende Person wurde gefragt.

  * Der Server prueft sie -- ohne sie bleibt die Mitschrift aus, auch
    wenn jemand das Pult umgeht.
  * Ausschalten geht immer.
  * Die Mitschrift uebersteht keinen Neustart mehr: die Einwilligung
    gilt der Person, die gerade spricht. Auch ein alter Stand mit
    "an" in zustand.json startet aus. Vorgabe bleibt aus.
  * Das Pult fragt vor dem Einschalten; Datenschutztexte und
    Gastprediger-Blatt sagen es.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hilfe import (WURZEL, arbeitskopie, rufen, server_starten,  # noqa: E402
                   server_stoppen, wegwerfordner)

sys.path.insert(0, str(WURZEL))
import datenschutz  # noqa: E402
import zustand as zustandsdatei  # noqa: E402

ROT, GRUEN, AUS = "\033[31m", "\033[32m", "\033[0m"
FEHLER = 0
PORT = 8188
JA = {"person_gefragt": True}


def pruefe(was, erwartet, ist):
    global FEHLER
    if erwartet == ist:
        print(f"   ok    {was}")
    else:
        print(f"   {ROT}FEHL{AUS}  {was}: erwartet {erwartet!r}, ist {ist!r}")
        FEHLER += 1


def titel(t):
    print(f"\n\033[1m== {t}\033[0m")


def lage(ordner):
    an = json.loads(rufen(PORT, "/api/zustand")[1]).get("protokoll_mitschrift")
    datei = json.loads((ordner / "zustand.json").read_text(encoding="utf-8"))
    return an, datei.get("protokoll_mitschrift")


titel("1) Vorgabe")
pruefe("aus", False, zustandsdatei.vorgabe()["protokoll_mitschrift"])

# Ein Rechner, auf dem die Mitschrift vor dem Update an war.
ordner = arbeitskopie(wegwerfordner("devarenu-einwilligung-"),
                      {"protokoll_mitschrift": True})
p = server_starten(ordner, PORT)
try:
    titel("2) Ein alter Stand mit 'an' startet aus")
    pruefe("aus, im Server und in zustand.json", (False, False), lage(ordner))

    titel("3) Ohne Einwilligung kein Einschalten")
    for name, daten in (("ohne Angabe", {"an": True}),
                        ("verneint", {"an": True, "einwilligung":
                                      {"person_gefragt": False}}),
                        ("Unsinn", {"an": True, "einwilligung": "ja"})):
        code, text = rufen(PORT, "/api/protokoll", daten)
        pruefe(f"{name}: abgewiesen", (400, "einwilligung_fehlt"),
               (code, json.loads(text).get("grund") if code == 400 else text))
        pruefe(f"{name}: bleibt aus", (False, False), lage(ordner))

    titel("4) Mit Einwilligung an, aus immer")
    code, _ = rufen(PORT, "/api/protokoll", {"an": True, "einwilligung": JA})
    pruefe("mit Einwilligung: an", (200, True, True), (code, *lage(ordner)))
    code, _ = rufen(PORT, "/api/protokoll", {"an": False})
    pruefe("ausschalten ohne Angabe: aus", (200, False, False),
           (code, *lage(ordner)))
    rufen(PORT, "/api/protokoll", {"an": True, "einwilligung": JA})
finally:
    server_stoppen(p)

titel("5) Neustart: die Einwilligung gilt nicht fuer den naechsten")
pruefe("vor dem Neustart stand 'an' in der Datei", True,
       json.loads((ordner / "zustand.json").read_text())
       .get("protokoll_mitschrift"))
p = server_starten(ordner, PORT)
try:
    pruefe("nach dem Neustart aus", (False, False), lage(ordner))
finally:
    server_stoppen(p)

titel("6) Pult und Texte")
quelle = (WURZEL / "server.py").read_text(encoding="utf-8")
funktion = quelle.split("async function protokollSetzen(){")[1] \
                 .split("\n}\n")[0]
pruefe("das Pult fragt vor dem Einschalten", True,
       "confirm(t.ms_frage)" in funktion)
pruefe("und schickt die Einwilligung mit", True,
       "einwilligung:{person_gefragt:true}" in funktion)
pruefe("die Frage auf Deutsch und Englisch", 2, quelle.count("   ms_frage:"))
for sp, wort in (("de", "beides nur mit Zustimmung der sprechenden Person"),
                 ("en", "both only with the speaker's consent")):
    pruefe(f"Stufe 2 {sp} sagt es", True,
           wort in datenschutz.stufe2_html(sp).replace("&#x27;", "'"))
ds = (WURZEL / "DATENSCHUTZ.md").read_text(encoding="utf-8")
pruefe("DATENSCHUTZ.md: der offene Punkt ist geschlossen", False,
       "fragt nicht nach Einwilligung" in ds)
pruefe("DATENSCHUTZ.md: Punkt 10 nennt die Einwilligung", True,
       "dieselbe Abfrage wie beim Testprotokoll" in ds)
gast = (WURZEL / "anleitung" / "05_gastprediger.md").read_text(encoding="utf-8")
pruefe("Gastprediger-Blatt: beide nur mit Zustimmung", True,
       "beide nur mit Ihrer Zustimmung" in gast
       and "ohne eigene Rückfrage" not in gast)

print()
if FEHLER:
    print(f"{ROT}{FEHLER} Fehler.{AUS}")
    sys.exit(1)
print(f"{GRUEN}Alle Faelle wie erwartet.{AUS}")
