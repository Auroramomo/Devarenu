#!/usr/bin/env python3
"""Fuer web_dateilisten_test.sh: selbsttest.pruefe_dateien() gegen einen
anderen Ordner.

    python pruefstand/web_dateilisten_hilfe.py <ordner>

config.BASIS wird auf den Ordner gelegt; sonst laeuft der Abschnitt
"Dateien" des Selbsttests, wie er ist."""
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))

import config      # noqa: E402
import selbsttest  # noqa: E402

config.BASIS = Path(sys.argv[1])
config.GLOSSAR_CSV = config.BASIS / "gibt-es-nicht.csv"
try:
    selbsttest.pruefe_dateien()
except Exception as e:
    # Was nach den Dateien kommt (Glossar, Namen), braucht echte Daten;
    # hier geht es nur um die Liste davor.
    print(f"(danach abgebrochen: {type(e).__name__})")
