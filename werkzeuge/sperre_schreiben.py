#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pakete.sperre aus einem Ordner voller Wheels schreiben (0.5.2).

    python3 werkzeuge/sperre_schreiben.py WHEELORDNER pakete.sperre

Aufgerufen von  bash stick_bauen.sh --nur-sperre. Jede Zeile:

    name==fassung --hash=sha256:<pruefsumme>

-- das Format, das "pip install --require-hashes -r" versteht. Mehrere
Wheels desselben Pakets (etwa fuer verschiedene manylinux-Stufen) stehen
als mehrere --hash in derselben Zeile; pip nimmt, was passt.

Pakete, deren Weitergabe ungeklaert ist, bekommen den Kommentar
"# NICHT OEFFENTLICH: <Grund>" (siehe NICHT_OEFFENTLICH unten und
LIZENZEN.md): stick_bauen.sh laesst sie aus dem oeffentlichen ZIP, und
aktualisierung.sh holt sie dann aus der Originalquelle (PyPI) -- gegen
genau diese Pruefsumme.
"""
import hashlib
import sys
from pathlib import Path

# Was NICHT ins oeffentliche Devarenu-Update.zip darf, mit Grund. Geprueft
# am 28.10.2026 an den Wheels selbst (METADATA, Lizenzdateien,
# mitgebrachte Bibliotheken); Einzelheiten in LIZENZEN.md.
NICHT_OEFFENTLICH = {
    "av": "bringt FFmpeg mit libx264/libx265 (GPL) mit, ohne deren "
          "Lizenztexte und ohne Quellenangabe",
    "ctranslate2": "MIT ohne Lizenztext im Wheel; bringt libgomp "
                   "(GPL mit Laufzeitausnahme) ohne Lizenztext mit",
    "piper-tts": "GPLv3 mit uebersetztem espeak-ng; das Wheel sagt nicht, "
                 "wo der Quelltext liegt (GPLv3 Abschnitt 6)",
}


def nicht_oeffentlich(name):
    """Der Grund, oder None. NVIDIA immer: Weitergabe ungeklaert."""
    if name.startswith("nvidia-"):
        return "NVIDIA, Weitergabe ungeklaert"
    return NICHT_OEFFENTLICH.get(name)


KOPF = """\
# Jedes Python-Paket, das ein Update installiert, mit seiner sha256.
#
# NICHT VON HAND PFLEGEN. Erzeugt von:  bash stick_bauen.sh --nur-sperre
# (nach jeder Aenderung an requirements.txt oder constraints.txt, VOR
# dem Tag -- die Datei muss im signierten Baum liegen).
#
# aktualisierung.sh installiert mit
#   pip install --require-hashes --no-deps -r pakete.sperre
# Ein Wheel, dessen sha256 hier nicht steht, wird abgelehnt -- gleich,
# ob es vom Stick, aus einem ZIP oder von PyPI kommt. Bis 0.5.1 genuegte
# der passende Dateiname.
#
# "# NICHT OEFFENTLICH": nicht im oeffentlichen Devarenu-Update.zip
# (NVIDIA; GPL-Binaerteile ohne Lizenztext oder Quellenangabe -- siehe
# LIZENZEN.md). Fehlt es auf dem Stick, holt das Update es von PyPI.
"""


def name_und_fassung(wheel):
    teile = wheel.name[:-4].split("-")
    return teile[0].replace("_", "-").lower(), teile[1]


def main():
    ordner, ziel = Path(sys.argv[1]), Path(sys.argv[2])
    pakete = {}
    for w in sorted(ordner.glob("*.whl")):
        name, fassung = name_und_fassung(w)
        h = hashlib.sha256(w.read_bytes()).hexdigest()
        pakete.setdefault((name, fassung), []).append(h)
    if not pakete:
        print("   keine Wheels gefunden")
        return 1
    zeilen = []
    for (name, fassung), hashes in sorted(pakete.items()):
        z = f"{name}=={fassung}" + "".join(
            f" \\\n    --hash=sha256:{h}" for h in sorted(set(hashes)))
        grund = nicht_oeffentlich(name)
        if grund:
            z = f"# NICHT OEFFENTLICH: {grund}\n" + z
        zeilen.append(z)
    ziel.write_text(KOPF + "\n" + "\n".join(zeilen) + "\n", encoding="utf-8")
    n_nicht = sum(1 for (n, _f) in pakete if nicht_oeffentlich(n))
    print(f"   {len(pakete)} Pakete, davon {n_nicht} nicht im oeffentlichen ZIP")
    return 0


if __name__ == "__main__":
    sys.exit(main())
