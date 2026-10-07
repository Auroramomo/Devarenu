#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Versuchssprachen: Twi hinter einem Schalter (Nachtrag zu 0.5.0).

    .venv/bin/python pruefstand/versuchssprachen_test.py

  * Twi bleibt im Programm, mit Stimme und Code -- erscheint aber weder
    am Pult in der Sprachauswahl noch auf der Hoererseite, solange der
    Schalter "Versuchssprachen" aus ist. Vorgabe aus.
  * Der Server nimmt Twi dann auch nicht an, wenn jemand es am Pult
    vorbei schickt.
  * Ist Twi schon eingeschaltet, bleibt es eingeschaltet; der
    Systemcheck weist darauf hin.
  * Der Schalter steht unter Einrichtung -> Fehlersuche -> Erweitert,
    zugeklappt, mit dem Satz, warum diese Sprachen nicht fuer den
    Gottesdienst taugen.

Gestartet werden zwei Kopien mit --nur-text, ohne Whisper und Stimmen.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hilfe import (WURZEL, arbeitskopie, rufen, server_starten,  # noqa: E402
                   server_stoppen, wegwerfordner)

sys.path.insert(0, str(WURZEL))
import config  # noqa: E402
import systemcheck  # noqa: E402
import zustand as zustandsdatei  # noqa: E402

ROT, GRUEN, AUS = "\033[31m", "\033[32m", "\033[0m"
FEHLER = 0
PORT = 8185
PORT_ALT = 8186


def pruefe(was, erwartet, ist):
    global FEHLER
    if erwartet == ist:
        print(f"   ok    {was}")
    else:
        print(f"   {ROT}FEHL{AUS}  {was}: erwartet {erwartet!r}, ist {ist!r}")
        FEHLER += 1


def titel(t):
    print(f"\n\033[1m== {t}\033[0m")


def sprachen(port):
    d = json.loads(rufen(port, "/api/sprachen")[1])
    return (d, {x["code"] for x in d["moeglich"]},
            [x["code"] for x in d["liste"]])


titel("1) Konfiguration und Vorgabe")
pruefe("tw ist Versuchssprache", {"tw"}, set(config.VERSUCHSSPRACHEN))
pruefe("tw hat weiter einen Namen", "Twi (Asante)", config.SPRACHNAMEN.get("tw"))
pruefe("tw hat weiter eine Stimme", True, bool(config.STIMMEN.get("tw")))
pruefe("der Schalter ist per Vorgabe aus", False,
       zustandsdatei.vorgabe()["versuchssprachen"])
daten = zustandsdatei.vorgabe()
pruefe("ein Unsinnswert kostet nur sich selbst", ["versuchssprachen"],
       zustandsdatei._uebernehmen({"versuchssprachen": "ja"}, daten))
pruefe("und bleibt dann aus", False, daten["versuchssprachen"])
pruefe("tw steht nicht in den Vorgabe-Zielsprachen", False,
       "tw" in config.ZIELSPRACHEN)

titel("2) Der Schalter am Pult: versteckt, mit Begruendung")
quelle = (WURZEL / "server.py").read_text(encoding="utf-8")
seite = quelle.split('<div class=unterseite id=eSprachen hidden>')[1] \
              .split("</div>")[0]
pruefe("nicht unter Sprachen", False, "versuchsschalter" in seite)
fehlersuche = quelle.split('<div class=unterseite id=eFehlersuche hidden>')[1] \
                    .split("<!-- Was gerade nicht stimmt")[0]
erweitert = fehlersuche.split("<details class=hilfe id=erweitert>")
pruefe("unter Fehlersuche, in einem zugeklappten Bereich", True,
       len(erweitert) == 2 and "id=versuchsschalter" in erweitert[1])
pruefe("der Bereich ist nicht von sich aus offen", False,
       "id=erweitert open" in fehlersuche)
for s in ("versuch_an:", "versuch_hin:", "erweitert:"):
    pruefe(f"{s} auf Deutsch und Englisch", 2, quelle.count(f"   {s}"))
hin = quelle.split("   versuch_hin:")[1].split("pw_kurz_ueber")[0]
pruefe("der Satz sagt, warum: nicht fuer den Gottesdienst", True,
       "taugen sie deshalb nicht" in hin)

ordner = arbeitskopie(wegwerfordner("devarenu-versuch-"),
                      {"quelle": "de", "ziele": ["en", "ru", "fa"]})
p = server_starten(ordner, PORT)
try:
    titel("3) Schalter aus: Twi taucht nirgends auf")
    d, moeglich, liste = sprachen(PORT)
    pruefe("nicht in der Auswahl am Pult", False, "tw" in moeglich)
    pruefe("Ukrainisch dagegen schon", True, "uk" in moeglich)
    pruefe("nicht auf der Hoererseite", False, "tw" in liste)
    code, _ = rufen(PORT, "/api/sprachwahl", {"quelle": "de",
                                              "ziele": ["en", "tw"]})
    pruefe("die Sprachwahl antwortet", 200, code)
    d, moeglich, liste = sprachen(PORT)
    pruefe("am Pult vorbei geschickt: abgewiesen", ["en"], d["ziele"])
    zst = json.loads(rufen(PORT, "/api/zustand")[1])
    pruefe("das Pult sieht den Schalter aus", False, zst["versuchssprachen"])

    titel("4) Schalter an: Twi ist waehlbar")
    code, text = rufen(PORT, "/api/versuchssprachen", {"an": True})
    pruefe("der Schalter laesst sich setzen", (200, {"an": True}),
           (code, json.loads(text) if code == 200 else text))
    gespeichert = json.loads((ordner / "zustand.json").read_text())
    pruefe("steht in zustand.json", True, gespeichert.get("versuchssprachen"))
    d, moeglich, liste = sprachen(PORT)
    pruefe("tw in der Auswahl", True, "tw" in moeglich)
    rufen(PORT, "/api/sprachwahl", {"quelle": "de", "ziele": ["en", "tw"]})
    d, moeglich, liste = sprachen(PORT)
    pruefe("tw laeuft mit", ["en", "tw"], d["ziele"])
    pruefe("und steht auf der Hoererseite", True, "tw" in liste)

    titel("5) Schalter wieder aus: was laeuft, bleibt")
    rufen(PORT, "/api/versuchssprachen", {"an": False})
    d, moeglich, liste = sprachen(PORT)
    pruefe("tw laeuft weiter", ["en", "tw"], d["ziele"])
    pruefe("und bleibt am Pult sichtbar, damit man es abwaehlen kann",
           True, "tw" in moeglich)
    rufen(PORT, "/api/sprachwahl", {"quelle": "de", "ziele": ["en"]})
    d, moeglich, liste = sprachen(PORT)
    pruefe("abgewaehlt verschwindet es aus der Auswahl", False, "tw" in moeglich)
finally:
    server_stoppen(p)

titel("6) Twi war vor dem Update schon an")
alt = arbeitskopie(wegwerfordner("devarenu-versuch-alt-"),
                   {"quelle": "de", "ziele": ["en", "tw"]})
p = server_starten(alt, PORT_ALT)
try:
    d, moeglich, liste = sprachen(PORT_ALT)
    pruefe("tw bleibt eingeschaltet", ["en", "tw"], d["ziele"])
    pruefe("die Hoerer finden es weiter", True, "tw" in liste)
    pruefe("am Pult steht es zum Abwaehlen", True, "tw" in moeglich)
    zst = json.loads(rufen(PORT_ALT, "/api/zustand")[1])
    pruefe("der Schalter selbst ist trotzdem aus", False, zst["versuchssprachen"])
finally:
    server_stoppen(p)

titel("7) Der Systemcheck weist darauf hin")
vorher = zustandsdatei.DATEI
try:
    for name, z, erwartet in (("mit tw", ["en", "tw"], 1),
                              ("ohne tw", ["en", "ru"], 0)):
        zustandsdatei.DATEI = alt / f"zustand-{name.replace(' ', '')}.json"
        zustandsdatei.DATEI.write_text(json.dumps({"ziele": z}),
                                       encoding="utf-8")
        befunde = []
        systemcheck._versuchssprachen(befunde)
        treffer = [b for b in befunde if b.kennung == "versuchssprache"]
        pruefe(f"{name}: {erwartet} Hinweis", erwartet, len(treffer))
        if treffer:
            b = treffer[0]
            pruefe("ein Hinweis, kein Fehler", systemcheck.HINWEIS, b.schwere)
            pruefe("fuer das Pult, nicht nur fuer die Wartung",
                   (True, False), (b.laie, b.wartung))
            pruefe("nennt die Sprache", True, "Twi (Asante)" in b.was)
            pruefe("und sagt, warum", True, "Gottesdienst" in b.was)
finally:
    zustandsdatei.DATEI = vorher

print()
if FEHLER:
    print(f"{ROT}{FEHLER} Fehler.{AUS}")
    sys.exit(1)
print(f"{GRUEN}Alle Faelle wie erwartet.{AUS}")
