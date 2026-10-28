#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Jede Seite nennt ihr Symbol (A5, 28.10.2026).

    python pruefstand/symbol_test.py

Unter 10.0.0.1 zeigte der Browser in Rostock das Symbol der Fritzbox:
er hatte es sich fuer diese Adresse gemerkt, und keine Seite sagte, dass
sie ein eigenes hat. Jetzt traegt jede Seite <link rel=icon> auf
/logo.png -- Pult, Hoererseite, QR-Seite, Anmeldung, Datenschutz -- und
/logo.png ist auch mit Pult-Passwort aus dem Saal abrufbar (sonst sähe
die Anmeldeseite kein Symbol).
"""
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pultschutz  # noqa: E402
from hilfe import (arbeitskopie, eigene_adresse, rufen,  # noqa: E402
                   server_starten, server_stoppen)

FEHLER = 0
PORT = 8149
SYMBOL = re.compile(r"""<link\s+rel=["']?icon["']?\s+type=["']?image/png["']?"""
                    r"""\s+href=["']?/logo\.png""", re.I)


def pruefe(was, erwartet, ist):
    global FEHLER
    if erwartet == ist:
        print(f"   ok    {was}")
    else:
        FEHLER += 1
        print(f"   FEHL  {was}: erwartet {erwartet!r}, ist {ist!r}")


ARBEIT = Path(tempfile.mkdtemp(prefix="devarenu-symbol-", dir=WURZEL / ".tmp"))
lauf = None
try:
    arbeitskopie(ARBEIT)
    lauf = server_starten(ARBEIT, PORT)
    for weg, name in (("/", "Hoererseite"), ("/pult", "Pult"),
                      ("/qr", "QR-Seite"), ("/datenschutz", "Datenschutz")):
        status, seite = rufen(PORT, weg)
        pruefe(f"{name} ({weg}) nennt /logo.png als Symbol", (200, True),
               (status, bool(SYMBOL.search(seite))))
    pruefe("/logo.png kommt als Bild", 200, rufen(PORT, "/logo.png")[0])

    rufen(PORT, "/api/pult-passwort", {"passwort": "Saal2026"})
    saal = eigene_adresse()
    if saal:
        status, seite = rufen(PORT, "/pult", gastgeber=saal)
        pruefe("die Anmeldeseite nennt es auch", (401, True),
               (status, bool(SYMBOL.search(seite))))
        pruefe("und /logo.png ist dort ohne Anmeldung abrufbar", 200,
               rufen(PORT, "/logo.png", gastgeber=saal)[0])
    else:
        FEHLER += 1
        print("   FEHL  keine Adresse ausser Loopback")
finally:
    server_stoppen(lauf)
    shutil.rmtree(ARBEIT, ignore_errors=True)

print()
if FEHLER:
    print(f"{FEHLER} FEHLER")
    sys.exit(1)
print("Alles in Ordnung.")
