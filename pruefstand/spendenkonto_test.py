#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Faellt eine falsche IBAN beim Start auf -- und faellt sonst nichts aus?

    python pruefstand/spendenkonto_test.py

Die IBAN steht fest in config.py und laesst sich am Pult nicht
aendern: wer das Programm weitergibt, soll das Spendenkonto nicht
nebenbei austauschen koennen. Fest heisst aber nicht unfehlbar -- ein
Zahlendreher faellt sonst niemandem auf, der QR-Code sieht aus wie
immer, und erst die Ueberweisung geht schief.

Der zweite Teil ist so wichtig wie der erste: bei einem Fehler wird
NICHTS geloescht und NICHTS abgeschaltet.
"""

import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))

import config           # noqa: E402
import spendenkonto as sk  # noqa: E402

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


titel("1) Das Konto, das im Repo steht")

ok, grund = sk.lage(config.SPENDE)
pruefe("die eingetragene IBAN ist gueltig", (True, ""), (ok, grund))
pruefe("sie steht in config.py und nicht in zustand.json", True,
       bool(getattr(config, "SPENDE", {}).get("iban")))

titel("2) Was die Pruefziffer faengt")

# Ein Zahlendreher in der Pruefziffer selbst.
pruefe("vertauschte Pruefziffer", False,
       sk.pruefen("DE91 2005 0550 1330 1104 44")[0])
# Eine Ziffer zu wenig.
pruefe("eine Stelle fehlt", False,
       sk.pruefen("DE19 2005 0550 1330 1104 4")[0])
# Zwei Ziffern im Kontoteil vertauscht.
pruefe("zwei Ziffern vertauscht", False,
       sk.pruefen("DE19 2005 0550 1330 1140 44")[0])
pruefe("Leerzeichen sind egal", True,
       sk.pruefen("DE192005055013301104 44")[0])
pruefe("Kleinschreibung ist egal", True,
       sk.pruefen("de19 2005 0550 1330 1104 44")[0])
pruefe("ein anderes Land geht auch", True,
       sk.pruefen("GB82 WEST 1234 5698 7654 32")[0])

titel("3) Was KEIN Fehler ist")

# Ohne IBAN erscheint der Spendenabschnitt gar nicht -- das ist ein
# erlaubter Zustand und keine Beanstandung.
pruefe("gar keine IBAN eingetragen", (True, ""), sk.lage({}))
pruefe("leere IBAN", (True, ""), sk.lage({"iban": "  "}))

titel("4) Was als ungueltig gemeldet wird")

for was, iban in [("Unsinn", "Hallo Welt"),
                  ("nur Ziffern", "1234567890"),
                  ("zu kurz", "DE19"),
                  ("Sonderzeichen", "DE19-2005-0550-1330-1104-44")]:
    gueltig, g = sk.pruefen(iban)
    pruefe(f"{was} wird abgewiesen", False, gueltig)
    pruefe(f"{was}: mit Begruendung", True, bool(g))

titel("5) Der Hinweis nennt keinen Kanal")

# Es darf KEIN Meldeziel im Code stehen -- weder hier noch im
# Server. Wer keinen Kanal eingerichtet hat, meldet nichts.
quelle = (WURZEL / "spendenkonto.py").read_text(encoding="utf-8")
for muster in ("ntfy.sh", "http://", "https://", "@"):
    pruefe(f"kein {muster!r} in spendenkonto.py", False, muster in quelle)

server = (WURZEL / "server.py").read_text(encoding="utf-8")
stelle = server[server.index("def spendenkonto_pruefen"):][:2000]
pruefe("der Server meldet nur mit vorhandener meldung.json", True,
       "meldung.json" in stelle)
pruefe("und nennt dabei kein Ziel", False, "ntfy" in stelle)
# Nichts wird abgeschaltet: der Spenden-Endpunkt darf nicht an der
# Gueltigkeit haengen.
pruefe("der QR-Code wird nicht abgeschaltet", False,
       "KONTO_GRUND" in server[server.index('def spende_qr'):][:1200])

print()
if FEHLER:
    print(f"{ROT}{FEHLER} Fehler.{AUS}")
    sys.exit(1)
print(f"{GRUEN}Alle Faelle wie erwartet.{AUS}")
