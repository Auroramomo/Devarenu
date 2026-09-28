#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gehen Fehlerberichte hinaus -- und geht dabei keiner verloren?

    python pruefstand/berichtpost_test.py

Zwei Dinge stehen auf dem Spiel. Ein Bericht, der verlorengeht, weil
das WLAN im falschen Augenblick weg war, ist schlimmer als keiner:
man haelt den Rechner dann fuer gesund. Und ein Bericht, der mehr
enthaelt als die Erlaubnisliste hergibt, waere ein Datenleck per Post.
"""

import os
import sys
import tempfile
import time
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))

import berichtpost as bp  # noqa: E402

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


titel("1) Einreihen, senden, bestaetigen")

with tempfile.TemporaryDirectory() as o:
    w = bp.Warteschlange(Path(o) / "berichte")
    pruefe("am Anfang ist nichts offen", 0, len(w.offene()))

    a = w.einreihen("neustart", "Fassung 0.3.3\nDienst laeuft\n")
    b = w.einreihen("systemcheck", "Fassung 0.3.3\nautologin fehlt\n")
    pruefe("zwei liegen bereit", 2, len(w.offene()))
    pruefe("der Anlass steht im Namen", True, "neustart" in a.name)
    pruefe("der Kopf nennt ihn ausgeschrieben", True,
           "Dienst neu gestartet" in a.read_text(encoding="utf-8"))

    # ERST nach der Bestaetigung als gesendet vermerken. Das ist der
    # ganze Punkt: ginge die Marke vorher, waere ein Bericht weg,
    # sobald das Senden einmal scheitert.
    w.als_gesendet(a)
    pruefe("nach der Bestaetigung ist einer weg", 1, len(w.offene()))
    pruefe("und zwar der bestaetigte", b.name, w.offene()[0].name)
    pruefe("der Stand zaehlt beide", {"gesamt": 2, "offen": 1}, w.stand())

    # Ein zweiter Lauf schickt nur den offenen.
    w.als_gesendet(b)
    pruefe("danach ist nichts mehr offen", 0, len(w.offene()))
    pruefe("aber beide liegen noch da", 2, w.stand()["gesamt"])

titel("2) Die Laenge, die ntfy durchlaesst")

# Nachgesehen in der ntfy-Dokumentation: ueber 4096 Bytes macht der
# Server VON SELBST einen Anhang daraus, und Anhaenge verfallen nach
# drei Stunden. Ein Bericht von Donnerstagabend, den jemand freitags
# liest, waere dann weg. Also bleibt jeder darunter.
lang = "".join(f"Zeile {i}: " + "x" * 70 + "\n" for i in range(200))
kurz, wurde = bp.kuerzen(lang)
pruefe("ein langer Bericht wird gekuerzt", True, wurde)
pruefe("und passt unter die Grenze", True,
       len(kurz.encode("utf-8")) <= bp.HOECHSTENS)
pruefe("deutlich unter 4096, mit Luft fuer den Kopf", True,
       len(kurz.encode("utf-8")) < 4096)
pruefe("es steht dabei, dass gekuerzt wurde", True,
       "gekuerzt" in kurz)
pruefe("und wo der ganze liegt", True, "auf dem Rechner" in kurz)
# An einer Zeilengrenze geschnitten: ein Bericht, der mitten im Wort
# aufhoert, sieht aus wie ein Uebertragungsfehler.
pruefe("geschnitten wird an einer Zeilengrenze", True,
       all(z.startswith("Zeile ") or not z.strip()
           or z.startswith("[gekuerzt")
           for z in kurz.split("\n")))

kurzer = "Nur drei Zeilen\nmehr nicht\nfertig\n"
gleich, wurde2 = bp.kuerzen(kurzer)
pruefe("ein kurzer bleibt unangetastet", kurzer, gleich)
pruefe("und gilt nicht als gekuerzt", False, wurde2)

titel("3) Rechte und Aufraeumen")

with tempfile.TemporaryDirectory() as o:
    ordner = Path(o) / "berichte"
    w = bp.Warteschlange(ordner)
    p = w.einreihen("hand", "etwas\n")
    pruefe("der Ordner ist 700", "700", oct(ordner.stat().st_mode)[-3:])
    pruefe("die Datei ist 600", "600", oct(p.stat().st_mode)[-3:])
    w.als_gesendet(p)
    marke = p.with_suffix(".gesendet")
    pruefe("die Marke ist 600", "600", oct(marke.stat().st_mode)[-3:])

    # Ein Rechner, der stuendlich denselben Fehler meldet, soll die
    # Platte nicht vollschreiben. Die aeltesten fallen weg.
    for i in range(bp.HOECHSTENS_STUECK + 10):
        w.einreihen("neustart", f"Bericht {i}\n")
        time.sleep(0.002)
    pruefe("es liegen hoechstens so viele, wie erlaubt sind", True,
           w.stand()["gesamt"] <= bp.HOECHSTENS_STUECK)

titel("4) Nichts darf hier etwas aufhalten")

# Ein Bericht ueber einen Fehler darf nie selbst einer werden.
with tempfile.TemporaryDirectory() as o:
    ordner = Path(o) / "zu"
    ordner.mkdir()
    ordner.chmod(0o500)
    try:
        w = bp.Warteschlange(ordner / "berichte")
        pruefe("ein nicht beschreibbarer Ordner gibt None", None,
               w.einreihen("hand", "etwas\n"))
        pruefe("und offene() wirft nichts", [], w.offene())
        pruefe("und stand() auch nicht", {"gesamt": 0, "offen": 0},
               w.stand())
    finally:
        ordner.chmod(0o700)

print()
if FEHLER:
    print(f"{ROT}{FEHLER} Fehler.{AUS}")
    sys.exit(1)
print(f"{GRUEN}Alle Faelle wie erwartet.{AUS}")
