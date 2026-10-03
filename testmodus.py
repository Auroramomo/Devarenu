#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Der Testmodus: Devarenu ohne Grafikkarte laufen lassen.

    python testmodus.py        sagt, ob er greift, und warum

WOFUER

Jedes Update soll kuenftig erst auf einer virtuellen Maschine laufen
und dann auf dem Gemeinderechner (siehe VM-TESTUMGEBUNG.md). Eine VM
hat aber keine NVIDIA-Karte durchgereicht, und `large-v3-turbo` auf der
CPU braucht fuer fuenf Sekunden Ton ueber eine Minute -- ein Prueflauf,
der eine Stunde dauert, wird nicht gemacht.

Im Testmodus laeuft darum ein kleines Modell auf der CPU. Was dabei
herauskommt, ist als UEBERSETZUNG unbrauchbar. Das ist in Ordnung:
geprueft werden soll der Weg -- startet der Dienst, kommt das Pult, geht
das Update durch, greifen die Units --, nicht die Qualitaet.

WARUM ER IM BETRIEB NICHT GREIFEN KANN

Zwei Bedingungen, und sie muessen BEIDE erfuellt sein:

  1. Die Datei TESTMODUS liegt im Projektordner. Sie steht in
     .gitignore und kommt mit keinem Update mit.
  2. Dieser Rechner hat KEINE NVIDIA-Karte (nvidia-smi findet keine).

Die zweite Bedingung ist die eigentliche Sperre. Die erste allein
waere eine Datei, und Dateien wandern: jemand kopiert einen Ordner,
spielt eine Sicherung zurueck, baut einen Stick aus einem
Testverzeichnis. Dann lief auf dem Gemeinderechner am Sonntag ein
Tiny-Modell, und am Pult saehe man es nicht -- die Uebersetzung kaeme
ja, nur als Unsinn.

Der Gemeinderechner hat eine RTX 5080. Solange das so ist, kann der
Testmodus dort nicht greifen, auch wenn die Marke daliegt. Und wenn
die Karte einmal ausfaellt, hat der Rechner ein groesseres Problem als
diese Datei -- und der Systemcheck sagt dann beides.

SICHTBAR IST ER UEBERALL: in der Startausgabe, am Pult unter Wartung
(ueber systemcheck.py) und in pruefen.sh.
"""

import sys
from pathlib import Path

BASIS = Path(__file__).resolve().parent
MARKE = BASIS / "TESTMODUS"

# Ein Modell, das auf einer CPU in vertretbarer Zeit antwortet.
# "tiny" statt "base": es geht um die Kette, nicht um den Satz.
MODELL = "tiny"
GERAET = "cpu"
RECHENART = "int8"


def karte_da():
    """Hat dieser Rechner eine NVIDIA-Karte?

    Ueber grafikkarte.karte_gefunden(), also ueber nvidia-smi und
    ausdruecklich nicht ueber torch -- aus demselben Grund, der dort
    steht: ein torch-Import laedt CUDA-Bibliotheken, die der Server
    nicht laedt, und dann meldet der Test gruen, wo der Betrieb rot
    ist."""
    try:
        import grafikkarte
        return grafikkarte.karte_gefunden() is not None
    except Exception:
        # Keine Auskunft heisst "womoeglich doch eine Karte". Im
        # Zweifel gilt Betrieb, nicht Test.
        return True


def lage():
    """(aktiv, Grund). Der Grund gehoert in die Ausgabe, immer."""
    if not MARKE.exists():
        return False, "keine Marke TESTMODUS im Projektordner"
    if karte_da():
        return False, ("TESTMODUS liegt da, aber dieser Rechner hat eine "
                       "NVIDIA-Karte -- der Testmodus greift nicht")
    return True, (f"TESTMODUS liegt da und es gibt keine NVIDIA-Karte: "
                  f"Whisper laeuft als \"{MODELL}\" auf der {GERAET.upper()}")


def aktiv():
    return lage()[0]


def einstellungen(vorgabe):
    """(Modell, Geraet, Rechenart) -- im Testmodus klein, sonst wie gegeben."""
    if aktiv():
        return MODELL, GERAET, RECHENART
    return vorgabe


def einschalten():
    MARKE.write_text(
        "Diese Datei schaltet den Testmodus ein: Whisper laeuft als\n"
        "kleines Modell auf der CPU. Nur fuer die virtuelle\n"
        "Testumgebung -- auf einem Rechner mit NVIDIA-Karte greift sie\n"
        "nicht. Naeheres in testmodus.py und VM-TESTUMGEBUNG.md.\n",
        encoding="utf-8")


def ausschalten():
    MARKE.unlink(missing_ok=True)


if __name__ == "__main__":
    if "--ein" in sys.argv:
        einschalten()
    elif "--aus" in sys.argv:
        ausschalten()
    an, grund = lage()
    print(f"Testmodus: {'AN' if an else 'aus'}")
    print(f"  {grund}")
    if an:
        print(f"  Modell {MODELL}, {GERAET}, {RECHENART}")
        print("  Was dabei herauskommt, ist als Uebersetzung unbrauchbar.")
        print("  Geprueft wird der Weg, nicht die Qualitaet.")
