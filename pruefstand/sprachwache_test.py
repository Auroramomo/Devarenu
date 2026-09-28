#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Warnt die Sprachwache -- und schweigt sie, wo sie schweigen muss?

    python pruefstand/sprachwache_test.py

Der Nutzen liegt in einem seltenen Fall: jemand spricht Englisch,
eingestellt ist Deutsch, und alle Uebersetzungen sind Unsinn. Der
SCHADEN laege in einem haeufigen: ein Bibelvers mit hebraeischen
Namen, ein englisches Lied, ein Eigenname -- und am Pult blinkt eine
Warnung, die nicht stimmt. Nach dem dritten Fehlalarm liest sie
niemand mehr, und dann nuetzt auch der richtige nichts.

Dieser Lauf prueft deshalb vor allem das Schweigen.
"""

import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))

import sprachwache as sw  # noqa: E402

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


def reden(wache, folge, dauer=5.0, p=0.95):
    """Eine Folge von Segmenten durchlaufen lassen.

    folge ist eine Liste von Sprachkennungen -- eine je Segment. Es
    wird nur gemeldet, was die Wache auch pruefen will."""
    for sprache in folge:
        if wache.dran(dauer):
            wache.melden(sprache, p)
    return wache.verdacht


titel("1) Der Fall, um den es geht")

# Eine Minute durchgehend Englisch bei eingestelltem Deutsch.
w = sw.Sprachwache("de")
pruefe("nach zwoelf englischen Segmenten: Verdacht", "en",
       reden(w, ["en"] * 12))
pruefe("und der Satz nennt beide Sprachen", True,
       "Englisch" in w.satz() and "Deutsch" in w.satz())

titel("2) Was NICHT warnen darf")

# Drei tauglich lange Segmente Englisch -- aber nur jedes vierte wird
# geprueft, also faellt hoechstens eines darunter.
w = sw.Sprachwache("de")
pruefe("ein englisches Lied von drei Segmenten", "",
       reden(w, ["de"] * 4 + ["en"] * 3 + ["de"] * 4))

# Der haeufigste Fall: einzelne fremde Segmente zwischen deutschen.
w = sw.Sprachwache("de")
pruefe("vereinzelte Ausreisser zwischen deutschen", "",
       reden(w, ["de", "en", "de", "de", "en", "de", "de", "en",
                 "de", "de", "de", "en", "de", "de", "de", "de"]))

# Ein Bibelabschnitt mit vielen Eigennamen: Whisper raet mal so, mal
# so, aber dazwischen steht immer wieder sicheres Deutsch.
w = sw.Sprachwache("de")
pruefe("fremde Ausreisser mit Deutsch dazwischen", "",
       reden(w, ["de", "en", "de", "nl", "de", "de", "en", "de",
                 "de", "he", "de", "de", "en", "de", "de", "de"]))

# ANMERKUNG ZUM TAKT. Wechseln zwei fremde Sprachen streng ab und
# kommt gar kein Deutsch dazwischen, trifft jede vierte Probe
# dieselbe von beiden -- und es wird gewarnt, obwohl keine der
# Sprachen dreimal wirklich hintereinander kam. Das ist hingenommen:
# zwoelf lange Segmente ohne ein einziges sicheres Deutsch sind
# selbst dann ein Grund hinzusehen, wenn der genannte Name geraten
# ist. Der Fall steht hier, damit er niemanden ueberrascht.
w = sw.Sprachwache("de")
pruefe("streng abwechselnd und ohne Deutsch: es wird gewarnt", True,
       reden(w, ["en", "nl"] * 6) != "")

# Kurze Segmente werden gar nicht erst geprueft.
w = sw.Sprachwache("de")
pruefe("kurze Einwuerfe werden uebergangen", "",
       reden(w, ["en"] * 20, dauer=2.5))

# Unsicheres zaehlt nicht -- weder fuer noch gegen.
w = sw.Sprachwache("de")
pruefe("unsichere Erkennung loest nichts aus", "",
       reden(w, ["en"] * 20, p=0.55))

titel("3) Die Warnung verschwindet von selbst")

w = sw.Sprachwache("de")
reden(w, ["en"] * 12)
pruefe("erst steht sie", "en", w.verdacht)
pruefe("ein sicheres deutsches Segment raeumt auf", "",
       reden(w, ["de"] * 4))
pruefe("und der Satz ist wieder leer", "", w.satz())

# Aber ein UNSICHERES deutsches Segment loescht sie nicht: das waere
# ein Weg, die Warnung durch Rauschen loszuwerden.
w = sw.Sprachwache("de")
reden(w, ["en"] * 12)
pruefe("ein unsicheres deutsches Segment loescht sie nicht", "en",
       reden(w, ["de"] * 4, p=0.5))

titel("4) Nach einem Sprachwechsel am Pult")

w = sw.Sprachwache("de")
reden(w, ["en"] * 12)
w.quelle_setzen("en")
pruefe("die Warnung ist weg", "", w.verdacht)
pruefe("und Englisch gilt jetzt als richtig", "",
       reden(w, ["en"] * 12))
pruefe("dafuer faellt jetzt Deutsch auf", "de",
       reden(w, ["de"] * 12))

# Derselbe Wert noch einmal gesetzt darf nichts zuruecksetzen.
w = sw.Sprachwache("de")
reden(w, ["en"] * 12)
w.quelle_setzen("de")
pruefe("dieselbe Sprache noch einmal gesetzt: alles bleibt", "en",
       w.verdacht)

titel("5) Der Takt")

w = sw.Sprachwache("de")
geprueft = sum(1 for _ in range(20) if w.dran(5.0))
pruefe("von zwanzig tauglichen Segmenten wird jedes vierte geprueft", 5,
       geprueft)
w = sw.Sprachwache("de")
geprueft = sum(1 for _ in range(20) if w.dran(1.0))
pruefe("kurze zaehlen dabei gar nicht mit", 0, geprueft)
# Der Takt darf nicht an kurzen Segmenten haengenbleiben: sonst
# praegten in einer Predigt mit vielen Einwuerfen genau die
# unzuverlaessigsten den Rhythmus.
w = sw.Sprachwache("de")
folge = [1.0, 1.0, 5.0, 1.0, 5.0, 5.0, 1.0, 5.0]
pruefe("nur taugliche Segmente treiben den Takt", 1,
       sum(1 for d in folge if w.dran(d)))

print()
if FEHLER:
    print(f"{ROT}{FEHLER} Fehler.{AUS}")
    sys.exit(1)
print(f"{GRUEN}Alle Faelle wie erwartet.{AUS}")
