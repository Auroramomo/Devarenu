#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pakete.sperre auswerten (0.5.2).

    python3 werkzeuge/sperre_pruefen.py pakete.sperre wheels/
        Welche Pakete liegen NICHT (mit passender sha256) im Wheel-Ordner?
        Eine Zeile "name fassung (nicht oeffentlich), name fassung, ..."
        -- leer, wenn alles da ist. Rueckgabe 0 wenn vollstaendig, sonst 1.
        Fuer die Meldung in aktualisierung.sh.

    python3 werkzeuge/sperre_pruefen.py --nicht-oeffentlich pakete.sperre
        Die Wheel-Namen (name_mit_unterstrich) der Pakete, die nicht ins
        oeffentliche Devarenu-Update.zip duerfen, je Zeile einer. Fuer
        stick_bauen.sh.
"""
import hashlib
import re
import sys
from pathlib import Path

MARKE = "# NICHT OEFFENTLICH"


def sperre_lesen(datei):
    """[(name, fassung, {hashes}, nicht_oeffentlich)]"""
    text = Path(datei).read_text(encoding="utf-8").replace("\\\n", " ")
    pakete, gesperrt = [], False
    for zeile in text.splitlines():
        z = zeile.strip()
        # "# NVIDIA" stand so bis zum Nachtrag vom 28.10.2026.
        if z.startswith(MARKE) or z == "# NVIDIA":
            gesperrt = True
            continue
        m = re.match(r"^([A-Za-z0-9._-]+)==(\S+)(.*)$", z)
        if not m:
            continue
        hashes = set(re.findall(r"--hash=sha256:([0-9a-f]{64})", m.group(3)))
        pakete.append((m.group(1).lower(), m.group(2), hashes, gesperrt))
        gesperrt = False
    return pakete


def main():
    if sys.argv[1] == "--nicht-oeffentlich":
        for name, _v, _h, gesperrt in sperre_lesen(sys.argv[2]):
            if gesperrt:
                print(re.sub(r"[-.]+", "_", name))
        return 0
    pakete = sperre_lesen(sys.argv[1])
    ordner = Path(sys.argv[2])
    da = set()
    if ordner.is_dir():
        for w in ordner.glob("*.whl"):
            da.add(hashlib.sha256(w.read_bytes()).hexdigest())
    fehlt = [f"{n} {v}" + (" (nicht oeffentlich)" if g else "")
             for n, v, h, g in pakete if not (h & da)]
    print(", ".join(fehlt))
    return 1 if fehlt else 0


if __name__ == "__main__":
    sys.exit(main())
