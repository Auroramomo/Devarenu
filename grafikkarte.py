#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Die CUDA-Bibliotheken der venv in den Prozess laden.

ctranslate2 unter faster_whisper bindet libcublas nicht ueber den Linker
ein, sondern oeffnet sie beim ersten transcribe mit dlopen. Bei einer
pip-Installation liegt sie nur in site-packages/nvidia/cublas/lib, und
dort sucht der Lader nicht.

Die Folge war kein Abbruch, sondern ein stiller Ausfall: das Modell laedt
einwandfrei, und erst jedes einzelne Segment scheitert mit "Library
libcublas.so.12 is not found or cannot be loaded". Der Selbsttest lief
dabei gruen, weil er torch importierte -- torch laedt dieselben
Bibliotheken beim Import nach und machte sie nebenbei auch fuer
ctranslate2 auffindbar. Er prueft also eine Umgebung, die im Betrieb
nicht existiert.

Vorladen statt LD_LIBRARY_PATH: der Lader liest die Variable beim
Prozessstart, aus dem laufenden Python heraus ist sie nicht mehr wirksam
zu setzen. Sie wirkte ausserdem nur ueber start.sh -- ein systemd-Dienst
braeuchte eine eigene Environment-Zeile, und wer server.py von Hand
aufruft, staende wieder ohne da. Das Vorladen wirkt in genau dem Prozess,
gleich wer ihn gestartet hat.
"""

import ctypes
import glob
import sysconfig
from pathlib import Path

# Was geladen wird, in dieser Reihenfolge. cublasLt VOR cublas: sonst
# zieht libcublas ueber ihren eigenen RUNPATH womoeglich ein
# systemweites, nicht passendes cublasLt nach. Torch hat dieselbe
# Reihenfolge mit derselben Begruendung im Quelltext stehen.
#
# Bewusst nur, was dieser ctranslate2-Build wirklich anfordert. cudnn
# steht nicht in seiner Liste und wird deshalb nicht geladen. Verlangt
# eine spaetere Fassung mehr, sagt es die Probe unten beim Namen, und
# der Name gehoert dann hierher.
GESUCHT = [
    ("cublas", "libcublasLt.so.*[0-9]"),
    ("cublas", "libcublas.so.*[0-9]"),
]

_geladen = None


def _venv_ordner():
    """site-packages des laufenden Interpreters."""
    pfad = sysconfig.get_paths().get("purelib")
    return Path(pfad) if pfad else None


def vorladen():
    """Laedt die CUDA-Bibliotheken aus der venv, wenn sie dort liegen.

    Gibt die Dateinamen zurueck, die geladen wurden. Findet sich nichts,
    passiert nichts: auf einem Rechner mit systemweitem CUDA greift dann
    der normale Suchpfad wie zuvor. Wirft nie -- eine fehlende Bibliothek
    soll spaeter als klare Meldung auffallen und nicht als Traceback
    beim Import."""
    global _geladen
    if _geladen is not None:
        return _geladen
    _geladen = []
    ordner = _venv_ordner()
    if ordner is None:
        return _geladen
    for paket, muster in GESUCHT:
        treffer = sorted(glob.glob(str(ordner / "nvidia" / paket / "lib" / muster)))
        for datei in treffer:
            try:
                ctypes.CDLL(datei, mode=ctypes.RTLD_GLOBAL)
                _geladen.append(Path(datei).name)
            except OSError:
                # Nicht laut werden: ob es wirklich fehlt, sagt erst die
                # Probe, und die sagt es verstaendlicher.
                pass
    return _geladen


def probe(modell):
    """Prueft, ob dieses Whisper-Modell tatsaechlich rechnen kann.

    Eine Sekunde Stille durch transcribe. Bewertet wird nur, ob der Aufruf
    ohne Ausnahme durchlaeuft; bei Stille ist leerer Text das erwartete
    Ergebnis.

    Noetig, weil das Laden des Modells nichts beweist:
    WhisperModel(device="cuda") lief anstandslos durch, und erst das erste
    transcribe fiel um. Wer nur das Laden prueft, prueft am Fehler vorbei.

    Der Rueckgabewert von transcribe ist ein Generator; ohne ihn
    auszulesen passiert gar nichts, und die Probe waere wertlos."""
    import numpy as np
    try:
        segmente, _ = modell.transcribe(np.zeros(16000, dtype=np.float32),
                                        language="de")
        list(segmente)
        return True, ""
    except Exception as e:
        return False, str(e).replace("\n", " ")[:160]


def karte_gefunden():
    """Name der Grafikkarte laut nvidia-smi, sonst None.

    Ueber das Programm des Treibers und ausdruecklich nicht ueber torch:
    ein Import von torch laedt CUDA-Bibliotheken in den Prozess, die der
    Server nicht laedt. Genau daran hat der Selbsttest frueher gruen
    gemeldet, waehrend im Gottesdienst nichts erkannt wurde. Was der Test
    prueft, muss dieselbe Umgebung sein wie die des Servers."""
    import subprocess
    try:
        a = subprocess.run(["nvidia-smi", "--query-gpu=name",
                            "--format=csv,noheader"],
                           capture_output=True, text=True, timeout=15)
    except Exception:
        return None
    if a.returncode == 0 and a.stdout.strip():
        return a.stdout.strip().splitlines()[0].strip()
    return None


if __name__ == "__main__":
    # Zum Nachsehen von Hand: python grafikkarte.py
    print("Karte:", karte_gefunden() or "keine gefunden")
    print("Geladen:", ", ".join(vorladen()) or "nichts (kein nvidia in der venv)")
