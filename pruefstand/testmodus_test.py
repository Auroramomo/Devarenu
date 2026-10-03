#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Der Testmodus — und vor allem: dass er im Betrieb nicht greift.

    python pruefstand/testmodus_test.py

Der Testmodus tauscht Whisper gegen ein `tiny`-Modell auf der CPU. Was
dabei herauskommt, ist als Übersetzung unbrauchbar. Auf der virtuellen
Testmaschine ist das richtig; auf dem Gemeinderechner wäre es eine
stille Katastrophe — die Übersetzung käme ja, nur als Unsinn, und am
Pult sähe man es nicht.

Darum prüft dieser Lauf hauptsächlich das NICHT-Greifen. Die eine
Zusicherung, auf die es ankommt: **die Marke allein genügt nicht.**
Liegt auf einem Rechner mit NVIDIA-Karte eine Datei `TESTMODUS`, bleibt
der Testmodus aus.
"""

import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))

import testmodus                                 # noqa: E402
import systemcheck                               # noqa: E402

GRUEN, ROT, AUS = "\033[32m", "\033[31m", "\033[0m"
FEHLER = 0


def pruefe(was, erwartet, ist):
    global FEHLER
    if erwartet == ist:
        print(f"   ok    {was}")
    else:
        print(f"   {ROT}FEHL{AUS}  {was}: erwartet {erwartet!r}, ist {ist!r}")
        FEHLER += 1


def titel(t):
    print(f"\n\033[1m== {t}\033[0m")


# Die Karte wird vorgetaeuscht, nicht abgefragt: der Lauf muss auf
# einem Rechner MIT und auf einem OHNE Karte dasselbe pruefen.
ECHT_KARTE = testmodus.karte_da
MARKE_WAR_DA = testmodus.MARKE.exists()


def mit(karte, marke):
    testmodus.karte_da = (lambda: karte)
    if marke:
        testmodus.einschalten()
    else:
        testmodus.ausschalten()
    return testmodus.lage()


try:
    titel("1) Die Wahrheitstabelle")

    an, grund = mit(karte=True, marke=False)
    pruefe("Karte da, keine Marke: aus", False, an)
    pruefe("und der Grund nennt die Marke", True, "Marke" in grund)

    an, grund = mit(karte=True, marke=True)
    pruefe("KARTE DA, MARKE DA: AUS", False, an)
    pruefe("und der Grund nennt die Karte", True, "NVIDIA" in grund)

    an, grund = mit(karte=False, marke=False)
    pruefe("keine Karte, keine Marke: aus", False, an)

    an, grund = mit(karte=False, marke=True)
    pruefe("keine Karte, Marke da: AN", True, an)
    pruefe("und der Grund sagt, was laeuft", True, testmodus.MODELL in grund)

    titel("2) Keine Auskunft heisst Betrieb, nicht Test")

    # Faellt nvidia-smi aus, ist nicht zu sagen, ob eine Karte da ist.
    # Im Zweifel gilt Betrieb: ein Gottesdienst mit grossem Modell auf
    # der CPU ist langsam, ein Gottesdienst mit tiny ist Unsinn.
    def wirft():
        raise RuntimeError("nvidia-smi antwortet nicht")

    testmodus.karte_da = ECHT_KARTE
    import grafikkarte
    echt_gefunden = grafikkarte.karte_gefunden
    grafikkarte.karte_gefunden = wirft
    try:
        pruefe("ohne Auskunft gilt: Karte da", True, testmodus.karte_da())
        testmodus.einschalten()
        pruefe("und der Testmodus bleibt aus", False, testmodus.aktiv())
    finally:
        grafikkarte.karte_gefunden = echt_gefunden

    titel("3) Die Einstellungen")

    vorgabe = ("large-v3-turbo", "cuda", "float16")
    mit(karte=True, marke=True)
    pruefe("ausserhalb des Testmodus bleibt alles, wie es ist",
           vorgabe, testmodus.einstellungen(vorgabe))
    mit(karte=False, marke=True)
    pruefe("im Testmodus ein kleines Modell auf der CPU",
           (testmodus.MODELL, "cpu", "int8"),
           testmodus.einstellungen(vorgabe))
    pruefe("und es ist wirklich ein kleines", True,
           testmodus.MODELL in ("tiny", "base", "small"))

    titel("4) Der Systemcheck sagt es in beiden Faellen")

    mit(karte=False, marke=True)
    b = []
    systemcheck._testmodus(b)
    pruefe("im Testmodus: ein Befund", 1, len(b))
    pruefe("mit der Kennung testmodus", "testmodus", b[0].kennung if b else "")
    pruefe("und dem Wort unbrauchbar", True,
           "unbrauchbar" in (b[0].was if b else ""))

    # Der Gegenfall: die Marke liegt auf einem Rechner mit Karte. Sie
    # tut nichts -- aber sie ist versehentlich hergekommen, und das
    # gehoert gesagt.
    mit(karte=True, marke=True)
    b = []
    systemcheck._testmodus(b)
    pruefe("Marke ohne Wirkung: trotzdem ein Befund", 1, len(b))
    pruefe("mit der Kennung testmodus_marke", "testmodus_marke",
           b[0].kennung if b else "")

    mit(karte=True, marke=False)
    b = []
    systemcheck._testmodus(b)
    pruefe("ohne Marke: kein Befund", 0, len(b))

    titel("5) Beide Kennungen gehoeren zur Wartung, nicht zum Sonntag")

    # systemcheck.WARTUNG entscheidet, was am Pult unter "Wartung"
    # landet und was in der Liste steht, die den Gottesdienst angeht.
    # Der Testmodus gehoert der Technik: er haelt nichts auf, und am
    # Sonntag kann niemand etwas damit anfangen.
    pruefe("testmodus", True, "testmodus" in systemcheck.WARTUNG)
    pruefe("testmodus_marke", True,
           "testmodus_marke" in systemcheck.WARTUNG)

    titel("6) Die Marke kommt mit keinem Update mit")

    gi = (WURZEL / ".gitignore").read_text(encoding="utf-8")
    pruefe("TESTMODUS steht in .gitignore", True,
           any(z.strip() == "TESTMODUS" for z in gi.splitlines()))

finally:
    testmodus.karte_da = ECHT_KARTE
    if MARKE_WAR_DA:
        testmodus.einschalten()
    else:
        testmodus.ausschalten()

print()
if FEHLER:
    print(f"{ROT}{FEHLER} Fehler.{AUS}")
    sys.exit(1)
print(f"{GRUEN}Alle Faelle wie erwartet.{AUS}")
