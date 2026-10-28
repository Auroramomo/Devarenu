#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Der Systemcheck sieht den nachgezogenen Vorrat (A4c, 28.10.2026).

    python pruefstand/vorrat_nachziehen_test.py

Nach dem Update in Rostock stand am Pult "Der Vorrat gehoert zu Fassung
0.5.0", obwohl er danach auf 0.5.1 nachgezogen worden war: der
Systemcheck lief beim Neustart, VOR dem Nachziehen, und nie wieder.

Hier: ein Server auf einer Wegwerfkopie, sein Vorrat (DEVARENU_VORRAT)
in einem Wegwerfordner, erst mit alter Fassung. Dann wird vorrat.json
neu geschrieben -- wie vorrat_bauen.sh es tut -- und der Befund muss
ohne Neustart verschwinden.
"""
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
from hilfe import arbeitskopie, rufen, server_starten, server_stoppen  # noqa: E402

FEHLER = 0
PORT = 8147


def pruefe(was, erwartet, ist):
    global FEHLER
    if erwartet == ist:
        print(f"   ok    {was}")
    else:
        FEHLER += 1
        print(f"   FEHL  {was}: erwartet {erwartet!r}, ist {ist!r}")


def kennungen():
    status, roh = rufen(PORT, "/api/zustand")
    if status != 200:
        return None
    return sorted(b["kennung"] for b in json.loads(roh).get("befunde") or [])


ARBEIT = Path(tempfile.mkdtemp(prefix="devarenu-vorrat-", dir=WURZEL / ".tmp"))
VORRAT = ARBEIT / "opt-vorrat"
VORRAT.mkdir()
os.environ["DEVARENU_VORRAT"] = str(VORRAT)
(VORRAT / "vorrat.json").write_text(json.dumps({"fassung": "0.5.0"}),
                                    encoding="utf-8")
lauf = None
try:
    arbeitskopie(ARBEIT / "kopie")
    lauf = server_starten(ARBEIT / "kopie", PORT)
    vorher = kennungen()
    if vorher is None:
        print("   FEHL  der Server kam nicht hoch")
        sys.exit(1)
    pruefe("beim Start: der Vorrat gehoert zu 0.5.0", True,
           "vorrat_alt" in vorher)

    # Wie vorrat_bauen.sh: neu geschrieben, mit der laufenden Fassung.
    time.sleep(1.1)
    (VORRAT / "vorrat.json").write_text(
        json.dumps({"fassung": config.VERSION}), encoding="utf-8")
    nachher = vorher
    for _ in range(45):
        nachher = kennungen() or []
        if "vorrat_alt" not in nachher:
            break
        time.sleep(1)
    pruefe("nach dem Nachziehen ist der Befund weg, ohne Neustart", False,
           "vorrat_alt" in nachher)
    pruefe("die anderen Befunde bleiben, wie sie waren",
           [k for k in vorher if k != "vorrat_alt"], nachher)
finally:
    server_stoppen(lauf)
    shutil.rmtree(ARBEIT, ignore_errors=True)

print()
if FEHLER:
    print(f"{FEHLER} FEHLER")
    sys.exit(1)
print("Alles in Ordnung.")
