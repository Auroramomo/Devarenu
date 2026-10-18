#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Was mehrere Pruefstaende gemeinsam brauchen.

Zwei Kopien derselben Hilfsfunktion sind zwei Baustellen: wer in der
einen einen Fall ergaenzt, laesst ihn in der anderen stehen. Das faellt
erst auf, wenn ein Prueflauf gruen ist, der es nicht sein duerfte.
"""

import atexit
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
# Die Glossardatei beim NAMEN aus config.py, nicht als feste
# Zeichenkette: beim Umschalten auf glossar_v0.9.csv liefen sonst vier
# Pruefstaende in "der Server kam nicht hoch", und zwar aus einem
# Grund, der mit dem Pruefgegenstand nichts zu tun hat. Dieselbe Falle
# hatte start.sh bis 0.3.0.
def _glossarname():
    import sys
    sys.path.insert(0, str(WURZEL))
    try:
        import config
        return config.GLOSSAR_CSV.name
    except Exception:
        return "glossar_v0.4.csv"


BEIWERK = ("client.html", "VERSION", "logo.png", "betreuer.txt",
           _glossarname(), "namen_block_b.csv")
# Ordner, die als KOPIE mitkommen und nicht als Verknuepfung: ein
# Pruefstand darf darin loeschen, ohne die Arbeitskopie zu treffen.
BEIWERK_ORDNER = ("web",)
VERKNUEPFT = (".venv", "voices", "models")


# ---------------------------------------------- Was der Server ausgibt
# Bis 0.5.1 ging die Ausgabe jedes gestarteten Servers nach /dev/null.
# Dort stand in 765b1d7 "Systemcheck fehlgeschlagen (too many values to
# unpack ...)", und kein Pruefstand schlug an. Jetzt liest ein Faden
# mit, und am Ende des Laufs gilt: steht eine dieser Zeilen da, ist der
# Pruefstand rot -- gleich, was er selbst gezaehlt hat.
ALARM = ("Systemcheck fehlgeschlagen", "Traceback")
_mitgehoert = []
# Ungepuffert, damit auch ein Server, der hart beendet wird, seine
# letzten Zeilen noch abgibt. Gilt fuer jeden Python-Kindprozess dieses
# Pruefstands, auch fuer die, die er selbst startet.
os.environ["PYTHONUNBUFFERED"] = "1"
# Die Grafikkarte bleibt frei: kein Pruefstand und kein Server, den er
# startet, sieht sie. Whisper faellt dann von selbst auf die CPU zurueck
# (Werk._whisper_laden); fuer einen Pruefstand reicht das.
os.environ["CUDA_VISIBLE_DEVICES"] = ""


def firefox_ohne_karte(profil):
    """Wie firefox_ohne_karte.mjs: user.js ins Profil, Mesa als GL.

    Firefox kennt --disable-gpu nicht (mit dem Schalter endete
    --screenshot still ohne Bild). Zurueck: die Umgebung fuer den Aufruf."""
    shutil.copy2(WURZEL / "pruefstand" / "firefox_ohne_karte.user.js",
                 Path(profil) / "user.js")
    return dict(os.environ, CUDA_VISIBLE_DEVICES="", LIBGL_ALWAYS_SOFTWARE="1",
                __GLX_VENDOR_LIBRARY_NAME="mesa",
                __EGL_VENDOR_LIBRARY_FILENAMES=(
                    "/usr/share/glvnd/egl_vendor.d/50_mesa.json"))


# ----------------------------------------------------- Ollama-Attrappe
# Ohne laufendes Ollama wartet der Server beim Start 90 Sekunden darauf,
# und genau so lange warten die Pruefstaende auf ihn. Die Attrappe
# (attrappen/ollama_attrappe.py) antwortet sofort; die Wegwerfkopie
# wird auf sie gelenkt. Das Repo und der Server bleiben, wie sie sind.
OLLAMA_ZEILE = 'OLLAMA_URL = "http://localhost:11434"'
_ollama_adresse = None


def ollama_attrappe():
    """Startet die Attrappe einmal je Pruefstand. Zurueck: ihre Adresse."""
    global _ollama_adresse
    if _ollama_adresse is None:
        import sys
        sys.path.insert(0, str(WURZEL / "pruefstand" / "attrappen"))
        import ollama_attrappe as attrappe
        _ollama_adresse = attrappe.starten()
    return _ollama_adresse


def ollama_umlenken(ordner):
    """Lenkt config.py einer Wegwerfkopie auf die Attrappe. Nie das Repo."""
    ordner = Path(ordner).resolve()
    if ordner == WURZEL:
        raise RuntimeError("ollama_umlenken: das ist das Repo, keine Kopie")
    datei = ordner / "config.py"
    text = datei.read_text(encoding="utf-8")
    if text.count(OLLAMA_ZEILE) != 1:
        raise RuntimeError(f"{datei}: die Zeile {OLLAMA_ZEILE!r} fehlt")
    datei.write_text(text.replace(
        OLLAMA_ZEILE, f'OLLAMA_URL = "{ollama_attrappe()}"'), encoding="utf-8")


def mithoeren(p, name="Server"):
    """Liest stdout eines Popen mit (stdout=PIPE, stderr=STDOUT).

    Gibt p zurueck, damit es um ein Popen(...) herumpasst."""
    import threading
    zeilen = []
    _mitgehoert.append((name, zeilen))

    def lesen():
        for roh in p.stdout:
            zeilen.append(roh.decode("utf-8", "replace").rstrip("\n")
                          if isinstance(roh, bytes) else roh.rstrip("\n"))

    threading.Thread(target=lesen, daemon=True).start()
    return p


def alarmzeilen():
    """[(name, zeile), ...] fuer jede Zeile, die nach ALARM aussieht."""
    return [(name, z) for name, zeilen in _mitgehoert for z in list(zeilen)
            if any(a in z for a in ALARM)]


def _urteil_am_ende():
    funde = alarmzeilen()
    if not funde:
        return
    import sys
    print(f"\n   \033[31mFEHL\033[0m  der Server meldete "
          f"{' oder '.join(ALARM)}:")
    for name, zeilen in _mitgehoert:
        if any(any(a in z for a in ALARM) for z in zeilen):
            print(f"\n   Ausgabe ({name}):")
            for z in zeilen[-80:]:
                print(f"     {z}")
    sys.stdout.flush()
    # os._exit und nicht sys.exit: aus einem atexit-Haken heraus aendert
    # sys.exit den Rueckgabewert nicht mehr. Dieser Haken wird beim
    # Import eingetragen und laeuft darum ALS LETZTER -- die
    # Wegwerfordner sind dann schon fort.
    os._exit(1)


atexit.register(_urteil_am_ende)


def wegwerfordner(praefix):
    """Ein Ordner unter /tmp, der am Ende des Laufs wieder verschwindet.

    Auch wenn ein Fall scheitert: atexit laeuft bei sys.exit(1) und bei
    einer Ausnahme, die bis oben durchschlaegt. Nur ein harter Abbruch
    (kill -9) laesst ihn liegen.

    Bis 0.4.5 legten mehrere Pruefstaende ihre Ordner an und raeumten
    sie nie weg -- auf dem Arbeitsrechner lagen am Ende ueber 700
    davon. Der Praefix bleibt Pflicht: ein Ordner ohne Namen laesst
    sich spaeter keinem Pruefstand mehr zuordnen."""
    import atexit
    import tempfile
    o = Path(tempfile.mkdtemp(prefix=praefix))
    atexit.register(shutil.rmtree, o, True)
    return o


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
    for name in BEIWERK_ORDNER:
        if (WURZEL / name).is_dir() and not (ziel / name).exists():
            shutil.copytree(WURZEL / name, ziel / name)
    for v in VERKNUEPFT:
        if (WURZEL / v).exists() and not (ziel / v).exists():
            (ziel / v).symlink_to(WURZEL / v)
    z = {"fassung": 3, "quelle": "de", "ziele": ["en"]}
    z.update(zustand or {})
    (ziel / "zustand.json").write_text(json.dumps(z), encoding="utf-8")
    os.chmod(ziel / "zustand.json", 0o600)
    ollama_umlenken(ziel)
    return ziel


def server_starten(ordner, port, warten=90):
    """Startet einen Server auf der Kopie und wartet, bis er antwortet."""
    p = mithoeren(subprocess.Popen(
        [str(Path(ordner) / ".venv/bin/python"), "server.py",
         "--port", str(port), "--nur-text"],
        cwd=str(ordner), stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT), f"Server :{port}")
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
