#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Das Pult-Passwort am Gemeinderechner zuruecksetzen -- ohne Pult.

    python werkzeuge/pult_passwort.py --stand
    python werkzeuge/pult_passwort.py --loeschen

Gedacht fuer den Fall, der sicher eintritt: das Passwort wurde vor
einem halben Jahr gesetzt, der Techniker ist ein anderer, und niemand
kennt es mehr. Ohne diesen Weg bliebe nur, zustand.json von Hand zu
bearbeiten -- und darin steht das WLAN-Passwort der Gemeinde.

Der Dienst muss dafuer NICHT neu gestartet werden. Er sieht sich die
Datei bei jedem Aufruf kurz an und merkt die Aenderung von selbst.
Setzen geht hier absichtlich nicht: ein Passwort, das in der
Kommandozeile steht, landet in der Verlaufsdatei der Shell.
"""

import argparse
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))

import pultschutz          # noqa: E402
import zustand             # noqa: E402

GRUEN, GELB, AUS = "\033[32m", "\033[33m", "\033[0m"


def main():
    p = argparse.ArgumentParser(
        description="Pult-Passwort ansehen oder loeschen.")
    p.add_argument("--stand", action="store_true",
                   help="nur nachsehen, ob eines gesetzt ist")
    p.add_argument("--loeschen", action="store_true",
                   help="das Passwort entfernen, das Pult ist danach offen")
    a = p.parse_args()

    datei = zustand.DATEI
    if not datei.exists():
        print(f"   {datei} gibt es nicht. Hier wurde noch nichts eingestellt.")
        return 1

    gesetzt = bool(zustand.laden()[0].get("pult_passwort"))

    if a.loeschen:
        if not gesetzt:
            print("   Es war keines gesetzt. Nichts geaendert.")
            return 0
        pultschutz.zuruecksetzen(datei)
        print(f"   {GRUEN}Passwort geloescht.{AUS} Das Pult ist wieder offen "
              f"-- wie in der Vorgabe.")
        print("   Der Dienst merkt das von selbst, ein Neustart ist nicht")
        print("   noetig. Am Pult unter Einrichtung laesst sich ein neues")
        print("   setzen.")
        return 0

    # Ohne Angabe dasselbe wie --stand: etwas zu loeschen, weil jemand
    # keinen Schalter gesetzt hat, waere die falsche Vorgabe.
    if gesetzt:
        print(f"   {GELB}Es ist ein Pult-Passwort gesetzt.{AUS}")
        print("   Geraete im Saalnetz werden einmal danach gefragt.")
        print("   Am Rechner selbst nie.")
        print("   Loeschen:  python werkzeuge/pult_passwort.py --loeschen")
    else:
        print("   Kein Pult-Passwort gesetzt. Das Pult ist im Saalnetz")
        print("   fuer jeden offen -- das ist die Vorgabe.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
