#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Was mehrere Pruefstaende gemeinsam brauchen.

Zwei Kopien derselben Hilfsfunktion sind zwei Baustellen: wer in der
einen einen Fall ergaenzt, laesst ihn in der anderen stehen. Das faellt
erst auf, wenn ein Prueflauf gruen ist, der es nicht sein duerfte.
"""

import json
import os
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent

# Was ein Server im Wegwerfordner braucht. Alle *.py kommen ohnehin
# mit -- eine gepflegte Liste vergisst genau das Modul, das gerade
# dazukam, und der Lauf meldet dann "der Server kam nicht hoch".
BEIWERK = ("client.html", "VERSION", "logo.png", "betreuer.txt",
           "glossar_v0.4.csv", "namen_block_b.csv")
VERKNUEPFT = (".venv", "voices", "models")


def eigene_adresse():
    """Eine Adresse dieses Rechners, die NICHT Loopback ist.

    Ueber 127.0.0.1 gilt jeder Aufruf als "am Rechner selbst" und wird
    nie abgewiesen. Der wichtigste Fall -- ein Handy im Saal kommt
    nicht heran -- liesse sich darueber gar nicht pruefen.

    Zur Laufzeit ermittelt und nicht eingetragen: die Adresse dieses
    Arbeitsrechners hat in einem oeffentlichen Repo nichts verloren."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Verbindet nichts, fragt nur, welche Adresse das System fuer
        # einen Weg nach draussen naehme. TEST-NET-1 geht nirgendwohin.
        s.connect(("192.0.2.1", 9))
        adresse = s.getsockname()[0]
        s.close()
        return None if adresse.startswith("127.") else adresse
    except OSError:
        return None


def arbeitskopie(ziel, zustand=None):
    """Legt eine lauffaehige Kopie des Projekts an.

    Mit EIGENER zustand.json: die der Arbeitskopie wird nie angefasst,
    in ihr steht das WLAN-Passwort der Gemeinde."""
    ziel = Path(ziel)
    ziel.mkdir(parents=True, exist_ok=True)
    for q in sorted(WURZEL.glob("*.py")):
        shutil.copy2(q, ziel / q.name)
    for name in BEIWERK:
        if (WURZEL / name).exists():
            shutil.copy2(WURZEL / name, ziel / name)
    for v in VERKNUEPFT:
        if (WURZEL / v).exists() and not (ziel / v).exists():
            (ziel / v).symlink_to(WURZEL / v)
    z = {"fassung": 3, "quelle": "de", "ziele": ["en"]}
    z.update(zustand or {})
    (ziel / "zustand.json").write_text(json.dumps(z), encoding="utf-8")
    os.chmod(ziel / "zustand.json", 0o600)
    return ziel


def server_starten(ordner, port, warten=90):
    """Startet einen Server auf der Kopie und wartet, bis er antwortet."""
    p = subprocess.Popen(
        [str(Path(ordner) / ".venv/bin/python"), "server.py",
         "--port", str(port), "--nur-text"],
        cwd=str(ordner), stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL)
    for _ in range(warten):
        if rufen(port, "/api/sprachen")[0] == 200:
            break
        time.sleep(1)
    return p


def server_stoppen(p):
    if p and p.poll() is None:
        p.terminate()
        try:
            p.wait(timeout=15)
        except subprocess.TimeoutExpired:
            p.kill()


def rufen(port, weg, daten=None, keks=None, gastgeber="127.0.0.1",
          kopf=None):
    """(status, text). Keine Ausnahme bei 4xx -- die sind hier oft das Ziel.

    daten=None ist ein GET. Wer einen Schreibweg pruefen will, muss
    mindestens {} uebergeben: mit GET kaeme 405 zurueck, der Endpunkt
    liefe nie, und der Fall bestuende aus dem falschen Grund."""
    b = urllib.request.Request(f"http://{gastgeber}:{port}{weg}")
    if keks:
        b.add_header("Cookie", f"devarenu_pult={keks}")
    for k, v in (kopf or {}).items():
        b.add_header(k, v)
    if daten is not None:
        b.data = json.dumps(daten).encode("utf-8")
        b.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(b, timeout=30) as a:
            return a.status, a.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return 0, str(e)
