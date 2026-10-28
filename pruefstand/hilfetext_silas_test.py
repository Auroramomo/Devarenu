#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Das Beispiel unter "Was erkannt wurde" (A2, 28.10.2026).

    python pruefstand/hilfetext_silas_test.py

Bis hierher stand dort der Unterschied zwischen "Sanballat" und "San
Ballard". "San Ballard" stammt aus keiner Messung (kein Messprotokoll,
kein Testprotokoll nennt es; es kam mit 5c87d29 als Beispiel in einen
Kommentar) und ist kein Fehler, den Whisper auf Deutsch macht. Jetzt
steht dort ein Paar, das jeder Deutschsprechende hoert: "Silas" und
"Sie las". Englisch mit Erklaerung, denn "Sie las" sagt einem
englischen Leser nichts.
"""
import re
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
FEHLER = 0


def pruefe(was, erwartet, ist):
    global FEHLER
    if erwartet == ist:
        print(f"   ok    {was}")
    else:
        FEHLER += 1
        print(f"   FEHLER {was}: erwartet {erwartet!r}, ist {ist!r}")


pult = (WURZEL / "web" / "pult.html").read_text(encoding="utf-8")
texte = re.findall(r'kontext_erklaert:((?:"[^"]*"\s*\+?\s*)+)', pult)
satz = ["".join(re.findall(r'"([^"]*)"', t)) for t in texte]
pruefe("kontext_erklaert gibt es zweimal (de, en)", 2, len(satz))
pruefe("deutsch", True, bool(satz) and satz[0].endswith(
    "Das ist der Unterschied zwischen „Silas“ und „Sie las“."))
pruefe("englisch", True, len(satz) > 1 and satz[1].endswith(
    "That is the difference between “Silas” and “Sie las” "
    "(German for “she read”)."))
pruefe("auch im HTML-Vorrat der Seite", True,
       "zwischen „Silas“ und „Sie las“." in pult)
for datei in ("web/pult.html", "anleitung/02_pult.md", "server.py"):
    pruefe(f"{datei} nennt \"San Ballard\" nicht mehr", False,
           "San Ballard" in (WURZEL / datei).read_text(encoding="utf-8"))
pruefe("die Anleitung hat das neue Paar", True,
       "„Silas\" und\n   „Sie las\"" in
       (WURZEL / "anleitung/02_pult.md").read_text(encoding="utf-8"))

print()
if FEHLER:
    print(f"{FEHLER} FEHLER")
    sys.exit(1)
print("Alles in Ordnung.")
