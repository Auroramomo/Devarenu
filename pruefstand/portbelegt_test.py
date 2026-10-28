#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ein zweiter Server auf einem belegten Port (B5, 0.5.1).

    .venv/bin/python pruefstand/portbelegt_test.py

starten_auf() warf "Port 8000 ist belegt", main() suchte in der Meldung
nach "address" und fand nichts -- heraus kam ein Traceback statt des
Hinweises "Laeuft der Dienst schon?". Hier laeuft eine Kopie mit
--nur-text, und ein zweiter Start auf demselben Port muss mit dem
Hinweis und Rueckgabe 1 enden.

Nebenbei: /api/betriebslage antwortet auf der laufenden Kopie, mit
allen Teilen -- auch auf einem Rechner ohne Dienst und ohne Wecker.
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hilfe import (arbeitskopie, rufen, server_starten,  # noqa: E402
                   server_stoppen, wegwerfordner)

ROT, GRUEN, AUS = "\033[31m", "\033[32m", "\033[0m"
FEHLER = 0
PORT = 8179


def pruefe(was, erwartet, ist):
    global FEHLER
    if erwartet == ist:
        print(f"   ok    {was}")
    else:
        print(f"   {ROT}FEHL{AUS}  {was}: erwartet {erwartet!r}, ist {ist!r}")
        FEHLER += 1


ordner = arbeitskopie(wegwerfordner("devarenu-portbelegt-"))
p = server_starten(ordner, PORT)
try:
    print("\n\033[1m== Der erste Server, und was er ueber den Betrieb sagt\033[0m")
    code, text = rufen(PORT, "/api/betriebslage")
    pruefe("/api/betriebslage antwortet", 200, code)
    d = json.loads(text) if code == 200 else {}
    # meldekanal und wartungs_wlan seit dem 28.10.2026 (nur "gesetzt").
    pruefe("mit allen Teilen", ["dienst", "fenster", "laufart", "meldekanal",
                                "startprotokoll", "wartungs_wlan", "wecker"],
           sorted(d))
    pruefe("dieser Server kommt nicht vom Dienst", "sitzung", d.get("laufart"))

    print("\n\033[1m== Ein zweiter Start auf demselben Port\033[0m")
    try:
        zweiter = subprocess.run(
            [str(Path(ordner) / ".venv/bin/python"), "server.py",
             "--port", str(PORT), "--nur-text"],
            cwd=str(ordner), capture_output=True, text=True, timeout=240)
        aus = zweiter.stdout + zweiter.stderr
        rc = zweiter.returncode
    except subprocess.TimeoutExpired:
        aus, rc = "(lief weiter)", None
    pruefe("er endet mit Rueckgabe 1", 1, rc)
    pruefe("mit dem Hinweis auf den laufenden Dienst", True,
           f"Port {PORT} ist belegt. Laeuft der Dienst schon?" in aus)
    pruefe("und dem Befehl zum Nachsehen", True,
           "systemctl status devarenu" in aus)
    pruefe("ohne Traceback", False, "Traceback" in aus)
    code, _ = rufen(PORT, "/api/zustand")
    pruefe("der erste Server laeuft weiter", 200, code)
finally:
    server_stoppen(p)

print()
if FEHLER:
    print(f"{ROT}{FEHLER} Fehler.{AUS}")
    sys.exit(1)
print(f"{GRUEN}Alle Faelle wie erwartet.{AUS}")
