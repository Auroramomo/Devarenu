#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rechnet das Wartungsfenster richtig -- und faellt es zur sicheren Seite?

    python pruefstand/fenster_test.py

Zwei Dinge stehen hier auf dem Spiel, und sie sind ungleich schwer.
Ein Fenster, das nicht aufgeht, kostet eine Woche Wartezeit. Ein
Fenster, das nicht zugeht, laesst den Gemeinderechner im WLAN haengen,
ohne dass jemand davon weiss. Deshalb prueft dieser Lauf vor allem
eins: dass jeder Zweifel zu "aus" fuehrt.

Nichts hier faehrt etwas herunter oder verbindet etwas -- gerechnet
wird nur. Die Uhrzeit wird uebergeben, nicht gelesen.
"""

import sys
from datetime import datetime
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))

import wartungsfenster as wf  # noqa: E402

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


def fenster(**anders):
    roh = {"an": True, "profil": "Gemeinde-WLAN", "wochentag": "Do",
           "von": "18:00", "bis": "22:00"}
    roh.update(anders)
    return wf.einstellung({"wartungsfenster": roh})


# 2026: der 1. Oktober ist ein Donnerstag.
DO = lambda h, m=0: datetime(2026, 10, 1, h, m)      # noqa: E731
MI = lambda h, m=0: datetime(2026, 9, 30, h, m)      # noqa: E731
FR = lambda h, m=0: datetime(2026, 10, 2, h, m)      # noqa: E731

titel("1) Wann ist Fenster")

e = fenster()
pruefe("Donnerstag 17:59 -- noch nicht", False, wf.im_fenster(DO(17, 59), e))
pruefe("Donnerstag 18:00 -- der Beginn zaehlt dazu", True,
       wf.im_fenster(DO(18, 0), e))
pruefe("Donnerstag 21:59 -- noch", True, wf.im_fenster(DO(21, 59), e))
pruefe("Donnerstag 22:00 -- das Ende zaehlt nicht mehr", False,
       wf.im_fenster(DO(22, 0), e))
pruefe("Mittwoch 20:00 -- falscher Tag", False, wf.im_fenster(MI(20), e))
pruefe("Freitag 20:00 -- falscher Tag", False, wf.im_fenster(FR(20), e))

titel("2) Unklar heisst AUS, nie AN")

# Jede einzelne dieser Zeilen war einmal ein denkbarer Tippfehler in
# netz.json. Keiner davon darf ein WLAN aufmachen.
for was, anders in [
        ("kein Profil", {"profil": ""}),
        ("Profil nur Leerzeichen", {"profil": "   "}),
        ("Wochentag mit Zusatz", {"wochentag": "Donnerstag Abend"}),
        ("Wochentag ganz falsch", {"wochentag": "Thursday"}),
        ("Wochentag leer", {"wochentag": ""}),
        ("von unbrauchbar", {"von": "achtzehn Uhr"}),
        ("bis unbrauchbar", {"bis": "22"}),
        ("Stunde 25", {"von": "25:00"}),
        ("Minute 61", {"von": "18:61"}),
        ("bis vor von", {"von": "22:00", "bis": "18:00"}),
        ("von gleich bis", {"von": "18:00", "bis": "18:00"}),
        ("an ist eine Zeichenkette", {"an": "ja"}),
        ("an ist eine Zahl", {"an": 1}),
]:
    pruefe(f"{was} -> aus", False, fenster(**anders)["an"])

pruefe("gar kein Block in netz.json -> aus", False,
       wf.einstellung({})["an"])
pruefe("Block ist eine Liste -> aus", False,
       wf.einstellung({"wartungsfenster": []})["an"])
pruefe("ein leerer Block -> aus (die Vorgabe ist aus)", False,
       wf.einstellung({"wartungsfenster": {}})["an"])

titel("3) Der naechste Beginn und der Wecker")

pruefe("Mittwoch -> morgen 18:00", "2026-10-01 18:00",
       wf.naechster_beginn(MI(20), e).strftime("%Y-%m-%d %H:%M"))
pruefe("Donnerstag frueh -> heute 18:00", "2026-10-01 18:00",
       wf.naechster_beginn(DO(9), e).strftime("%Y-%m-%d %H:%M"))
# Der Fall, der beim Herunterfahren zaehlt: es ist 22 Uhr, das Fenster
# ist eben zu. Der naechste Beginn ist nicht heute -- sonst stellte
# sich der Wecker in die Vergangenheit, und rtcwake wiese ihn ab.
pruefe("Donnerstag 22:00 -> naechste Woche", "2026-10-08 18:00",
       wf.naechster_beginn(DO(22), e).strftime("%Y-%m-%d %H:%M"))
pruefe("mitten im Fenster -> ebenfalls naechste Woche", "2026-10-08 18:00",
       wf.naechster_beginn(DO(20), e).strftime("%Y-%m-%d %H:%M"))
pruefe("Wecker fuenf Minuten frueher", "2026-10-01 17:55",
       wf.wecker_zeit(MI(20), e).strftime("%Y-%m-%d %H:%M"))
pruefe("aus heisst kein Wecker", None, wf.wecker_zeit(MI(20), fenster(an=False)))
pruefe("ausgeschrieben geht auch", True,
       wf.im_fenster(DO(20), fenster(wochentag="Donnerstag")))
pruefe("und klein geschrieben", True,
       wf.im_fenster(DO(20), fenster(wochentag="do")))

# Ueber die Zeitumstellung hinweg. Am 25.10.2026 wird zurueckgestellt;
# der Donnerstag davor ist Sommerzeit, der danach Winterzeit. Gerechnet
# wird in Ortszeit, die Unix-Sekunde muss den Sprung mitmachen.
e_okt = fenster()
vor = wf.wecker_zeit(datetime(2026, 10, 21, 23), e_okt)    # -> Do 22.10., Sommer
nach = wf.wecker_zeit(datetime(2026, 10, 28, 23), e_okt)   # -> Do 29.10., Winter
pruefe("vor der Umstellung: 17:55 Ortszeit", "2026-10-22 17:55",
       vor.strftime("%Y-%m-%d %H:%M"))
pruefe("nach der Umstellung: wieder 17:55 Ortszeit", "2026-10-29 17:55",
       nach.strftime("%Y-%m-%d %H:%M"))
# Sieben Tage Ortszeit sind ueber die Umstellung 7*24+1 Stunden echte
# Zeit. Wer in Sekunden rechnet statt in Tagen, kaeme hier eine Stunde
# zu frueh -- und der Rechner staende um 16:55 im WLAN.
pruefe("dazwischen liegen 169 echte Stunden", 169.0,
       round((nach.timestamp() - vor.timestamp()) / 3600, 2))

titel("4) Auto-Aus")

pruefe("mitten im Fenster: nichts", "",
       wf.abschalten_faellig(False, DO(20), e, stunden=3)[0])
pruefe("kurz nach Fensterende: aus", "fensterende",
       wf.abschalten_faellig(False, DO(22, 1), e, stunden=3)[0])
pruefe("eine Stunde nach Fensterende: nicht mehr", "",
       wf.abschalten_faellig(False, DO(23, 30), e, stunden=3)[0])
# Der Fall, der sonst jemanden aussperrt: um 23 Uhr faehrt jemand den
# Rechner absichtlich hoch. Er darf nicht sofort wieder ausgehen.
pruefe("absichtlich um 23:00 eingeschaltet: bleibt an", "",
       wf.abschalten_faellig(False, DO(23), e, stunden=0.1)[0])
pruefe("Mittwoch, 25 Stunden Laufzeit: aus", "laufzeit",
       wf.abschalten_faellig(False, MI(14), e, stunden=25)[0])
pruefe("Mittwoch, 23 Stunden: noch nicht", "",
       wf.abschalten_faellig(False, MI(14), e, stunden=23)[0])

# C2: die Uebersetzung schiebt auf, aber nicht auf ewig.
pruefe("25 Stunden, aber es wird uebersetzt: warten", "",
       wf.abschalten_faellig(True, MI(14), e, stunden=25)[0])
pruefe("35 Stunden und Uebersetzung: immer noch warten", "",
       wf.abschalten_faellig(True, MI(14), e, stunden=35)[0])
pruefe("36 Stunden: die harte Grenze gilt auch dann", "laufzeit_hart",
       wf.abschalten_faellig(True, MI(14), e, stunden=36)[0])
pruefe("auch mitten im Fenster gilt die harte Grenze", "laufzeit_hart",
       wf.abschalten_faellig(True, DO(20), e, stunden=40)[0])
pruefe("Fenster aus: gar kein Auto-Aus", "",
       wf.abschalten_faellig(False, MI(14), fenster(an=False), stunden=99)[0])
pruefe("Laufzeit unbekannt: keine Behauptung", "",
       wf.abschalten_faellig(False, MI(14), e, stunden=None)[0])

# Wer die harte Grenze unter die weiche setzt, meint nicht, was er
# schreibt. Gezogen wird dann die weiche.
eng = fenster(hoechstlaufzeit_h=24, hoechstlaufzeit_hart_h=12)
pruefe("harte Grenze unter der weichen wird angehoben", 24,
       eng["hoechstlaufzeit_hart_h"])
pruefe("0 Stunden heisst: keine Laufzeitgrenze", "",
       wf.abschalten_faellig(False, MI(14),
                             fenster(hoechstlaufzeit_h=0,
                                     hoechstlaufzeit_hart_h=0),
                             stunden=500)[0])

titel("5) Ein- und Ausschalten schreibt netz.json")

# --einschalten prueft mit DERSELBEN Funktion, die spaeter auch liest.
# Was hier durchgeht, gilt auch fuer den Timer -- sonst stuende ein
# Fenster in netz.json, das er wortlos ignoriert, und niemand wuesste
# warum.
import tempfile                                             # noqa: E402
from pathlib import Path as _P                              # noqa: E402
import netzzustand                                          # noqa: E402

with tempfile.TemporaryDirectory() as ordner:
    alt_datei = netzzustand.DATEI
    netzzustand.DATEI = _P(ordner) / "netz.json"
    try:
        for was, werte in [
                ("Wochentag mit Zusatz", dict(profil="W", wochentag="Donnerstagabend",
                                              von="18:00", bis="22:00")),
                ("kein Profil", dict(profil="  ", wochentag="Do",
                                     von="18:00", bis="22:00")),
                ("bis vor von", dict(profil="W", wochentag="Do",
                                     von="22:00", bis="18:00")),
                ("Uhrzeit ohne Doppelpunkt", dict(profil="W", wochentag="Do",
                                                  von="1800", bis="22:00")),
        ]:
            probleme = wf.schreiben(werte)
            pruefe(f"{was} wird abgewiesen", True, len(probleme) > 0)
        # Und zwar OHNE etwas zu schreiben. Eine halb geschriebene
        # Einstellung waere schlimmer als gar keine.
        pruefe("nach lauter Fehlern gibt es keine netz.json", False,
               netzzustand.DATEI.exists())

        pruefe("gueltige Werte gehen durch", [],
               wf.schreiben(dict(profil="Gemeinde-WLAN", wochentag="Do",
                                 von="18:00", bis="22:00")))
        e = wf.einstellung()
        pruefe("und stehen danach auch so da", True, e["an"])
        pruefe("Profil", "Gemeinde-WLAN", e["profil"])
        pruefe("die Laufzeitgrenzen kommen mit", (24, 36),
               (e["hoechstlaufzeit_h"], e["hoechstlaufzeit_hart_h"]))

        # Wer nur die Uhrzeit aendert, soll die Grenzen nicht verlieren.
        netz, _ = netzzustand.laden()
        netz["wartungsfenster"]["hoechstlaufzeit_h"] = 12
        netzzustand.speichern(netz)
        wf.schreiben(dict(profil="Gemeinde-WLAN", wochentag="Fr",
                          von="19:00", bis="21:00"))
        e = wf.einstellung()
        pruefe("eine Aenderung laesst den Rest stehen", 12,
               e["hoechstlaufzeit_h"])
        pruefe("und aendert, was gemeint war", ("Fr", "19:00"),
               (e["wochentag"], e["von"]))

        wf.abschalten()
        e = wf.einstellung()
        pruefe("ausschalten schaltet aus", False, e["an"])
        pruefe("laesst Profil und Uhrzeit aber stehen",
               ("Gemeinde-WLAN", "Fr"), (e["profil"], e["wochentag"]))
    finally:
        netzzustand.DATEI = alt_datei

print()
if FEHLER:
    print(f"{ROT}{FEHLER} Fehler.{AUS}")
    sys.exit(1)
print(f"{GRUEN}Alle Faelle wie erwartet.{AUS}")
