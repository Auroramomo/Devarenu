#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Die Sprachen von 0.5.0, so wie der Server sie meldet.

    .venv/bin/python pruefstand/sprachen_test.py

  * Ukrainisch ist geprueft und hat ein Glossar.
  * Twi (Asante) ist waehlbar, ungeprueft, ohne Glossar -- und taugt
    NICHT als Predigtsprache: Whisper kennt Twi nicht
    (config.NUR_ZIEL). Das Pult bietet es dort nicht an, und der
    Server nimmt es dort nicht an, auch wenn jemand es schickt.
  * An Rostock (de -> en, ru, fa) aendert sich nichts.

Gestartet wird eine Kopie mit --nur-text, ohne Whisper und ohne Stimmen.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hilfe import (WURZEL, arbeitskopie, rufen, server_starten,  # noqa: E402
                   server_stoppen, wegwerfordner)

sys.path.insert(0, str(WURZEL))
import config  # noqa: E402

ROT, GRUEN, AUS = "\033[31m", "\033[32m", "\033[0m"
FEHLER = 0
PORT = 8173


def pruefe(was, erwartet, ist):
    global FEHLER
    if erwartet == ist:
        print(f"   ok    {was}")
    else:
        print(f"   {ROT}FEHL{AUS}  {was}: erwartet {erwartet!r}, ist {ist!r}")
        FEHLER += 1


def titel(t):
    print(f"\n\033[1m== {t}\033[0m")


titel("1) Die Konfiguration")
pruefe("tw heisst Twi (Asante)", "Twi (Asante)", config.SPRACHNAMEN.get("tw"))
pruefe("auch auf Englisch", "Twi (Asante)", config.SPRACHNAMEN_EN.get("tw"))
pruefe("tw ist ungeprueft", False, "tw" in config.GEPRUEFT)
pruefe("tw ist nur Zielsprache", True, "tw" in config.NUR_ZIEL)
pruefe("uk ist geprueft", True, "uk" in config.GEPRUEFT)
pruefe("ZIELSPRACHEN unveraendert", ["en", "ru", "fa"], list(config.ZIELSPRACHEN))
client = (WURZEL / "client.html").read_text(encoding="utf-8")
pruefe("die Hoererseite nennt Twi in seinem eigenen Namen", True,
       'tw:{name:"Twi"' in client)

titel("1b) Wiederholungsschleifen bei Twi")
from server import schleife_kappen  # noqa: E402

pruefe("gilt nur fuer tw", {"tw"}, set(config.SCHLEIFE_KAPPEN))
# Echte Ausgaben von gemma4:12b aus der Probe zu 0.5.0, gekuerzt.
schleife = ("Yesu kyerɛw Yohanna 3:16 mu sɛ Onyankopɔnnimo " +
            "honnim " * 40).strip()
pruefe("eine Ein-Wort-Schleife wird nach dem ersten Wort gekappt",
       "Yesu kyerɛw Yohanna 3:16 mu sɛ Onyankopɔnnimo honnim …",
       schleife_kappen(schleife))
gruppe = "Anigye, mmoaanom, anaa " + "yɛn bɛnni no, " * 6
pruefe("eine Drei-Wort-Schleife ebenso",
       "Anigye, mmoaanom, anaa yɛn bɛnni no …", schleife_kappen(gruppe))
kette = schleife_kappen("nnyɛnneɛnnɔnnɔnnɔnɔnɔnɔnɔnɔnɔnɔnɔ")
pruefe("Silbenketten werden gekuerzt", (False, True),
       ("nɔnɔnɔ" in kette, len(kette) < 20))
for satz in ("Heilig, heilig, heilig ist der Herr.",
             "Awurade ne me hwɛfo, hwee renhia me.",
             "Na, na, na, wɔka sɛ yɛnkɔ.",
             "Ɔdɔ nni awiei."):
    pruefe(f"bleibt stehen: {satz}", satz, schleife_kappen(satz))

ordner = arbeitskopie(wegwerfordner("devarenu-sprachen-"))
p = server_starten(ordner, PORT)
try:
    titel("2) Was der Server meldet")
    code, text = rufen(PORT, "/api/sprachen")
    pruefe("der Server antwortet", 200, code)
    d = json.loads(text) if code == 200 else {"moeglich": []}
    m = {x["code"]: x for x in d["moeglich"]}
    pruefe("tw ist waehlbar", True, "tw" in m)
    pruefe("tw: ungeprueft, ohne Glossar",
           (False, False), (m["tw"]["geprueft"], m["tw"]["glossar"]))
    pruefe("tw taugt nicht als Predigtsprache", False, m["tw"]["quelle"])
    pruefe("uk: geprueft, mit Glossar",
           (True, True), (m["uk"]["geprueft"], m["uk"]["glossar"]))
    pruefe("de taugt als Predigtsprache", True, m["de"]["quelle"])
    pruefe("nur tw ist ausgenommen", ["tw"],
           sorted(c for c, x in m.items() if not x["quelle"]))

    titel("3) Twi als Ziel ja, als Quelle nein")
    code, _ = rufen(PORT, "/api/sprachwahl", {"quelle": "tw",
                                              "ziele": ["en", "tw"]})
    pruefe("die Sprachwahl antwortet", 200, code)
    d = json.loads(rufen(PORT, "/api/sprachen")[1])
    pruefe("die Quelle bleibt Deutsch", "de", d["quelle"])
    pruefe("Twi ist als Ziel dabei", ["en", "tw"], d["ziele"])
    eintrag = next(x for x in d["liste"] if x["code"] == "tw")
    pruefe("und heisst dort Twi (Asante)", "Twi (Asante)", eintrag["name"])
finally:
    server_stoppen(p)

print()
if FEHLER:
    print(f"{ROT}{FEHLER} Fehler.{AUS}")
    sys.exit(1)
print(f"{GRUEN}Alle Faelle wie erwartet.{AUS}")
