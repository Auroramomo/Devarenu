#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Zwei Glossarfassungen vergleichen -- je Sprache, Satz für Satz.

    python werkzeuge/glossar_vergleich.py glossar_v0.4.csv glossar_v0.9.csv
    python werkzeuge/glossar_vergleich.py alt.csv neu.csv --sprachen en,ru,fa

WOFÜR

Eine neue Glossarfassung darf eine Sprache, an der niemand gearbeitet
hat, nicht anfassen. Das ist leicht gesagt und schwer zu sehen: das
Glossar wirkt nicht über die Spalte allein, sondern über die
**Suchvarianten**. `glossar.finde()` sortiert alle Varianten nach
Länge und lässt die erste, die eine Textstelle beansprucht, gewinnen.
Eine neue Zeile mit einer LÄNGEREN Variante kann damit eine alte Zeile
verdrängen -- und wenn die neue Zeile für Englisch leer ist, fehlt der
englische Begriff plötzlich im Prompt.

Beispiel, genau so passiert: eine neue Zeile "28 Glaubensüberzeugungen"
verdrängt D034 "Glaubensüberzeugungen". Für Spanisch ist das gewollt,
für Englisch ein Verlust -- und in der CSV sieht man es nicht.

Verglichen wird deshalb nicht die Datei, sondern das ERGEBNIS: der Text,
den `glossarzeilen()` dem Sprachmodell vorgibt. Gleich heißt gleich.

DER KORPUS

`testsaetze_v0.4.csv`, die 40 Sätze des Projekts, plus jede deutsche
Form, die in einer der beiden Fassungen vorkommt (Hauptwort und
Suchvarianten). Die Sätze prüfen den Normalfall, die Formen die Stellen,
an denen sich zwei Zeilen überhaupt in die Quere kommen können.

Rückgabe 0 heißt: für jede genannte Sprache kommt Zeichen für Zeichen
dasselbe heraus.
"""

import argparse
import csv
import io
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))

from glossar import Glossar, glossarzeilen   # noqa: E402

GRUEN, ROT, GELB, BLAU, AUS = (
    "\033[32m", "\033[31m", "\033[33m", "\033[1;34m", "\033[0m")


def korpus(pfade):
    """Die Testsätze plus alle deutschen Formen beider Fassungen."""
    saetze = []
    datei = WURZEL / "testsaetze_v0.4.csv"
    if datei.exists():
        with io.open(datei, encoding="utf-8-sig", newline="") as f:
            for z in csv.DictReader(f, delimiter=";"):
                for feld in ("satz", "kontext"):
                    if (z.get(feld) or "").strip():
                        saetze.append(z[feld].strip())
    formen = set()
    for p in pfade:
        with io.open(p, encoding="utf-8-sig", newline="") as f:
            for z in csv.DictReader(f, delimiter=";"):
                formen.add(z["de"])
                for v in z["suchvarianten"].split("|"):
                    if v.strip():
                        formen.add(v.strip())
    # Die Form allein und in einem Satz: allein greift der Wortanfang,
    # im Satz die Umgebung.
    for f in sorted(formen):
        saetze.append(f)
        saetze.append(f"Wir sprechen heute über {f} und über die Gemeinde.")
    return saetze


def vergleichen_ausser(alt_pfad, neu_pfad, sprachen, erlaubt=()):
    """(erlaubte, fremde) Abweichungen -- ohne Ausgabe.

    erlaubt ist eine Liste deutscher Formen. Eine Abweichung gilt als
    erlaubt, wenn der geprüfte Text eine davon enthält: dann ist genau
    die neue Suchvariante der Grund, und das war der Zweck.

    Gedacht für den Prüfstand. Eine neue Fassung soll an en, ru und fa
    nichts ändern -- ausser dort, wo jemand es ausdrücklich wollte und
    aufgeschrieben hat."""
    alt = Glossar.laden(alt_pfad)
    neu = Glossar.laden(neu_pfad)
    erlaubte, fremde = 0, 0
    for text in korpus([alt_pfad, neu_pfad]):
        for sp in sprachen:
            if glossarzeilen(alt.finde(text), sp) \
                    == glossarzeilen(neu.finde(text), sp):
                continue
            if any(e.lower() in text.lower() for e in erlaubt):
                erlaubte += 1
            else:
                fremde += 1
    return erlaubte, fremde


def vergleichen(alt_pfad, neu_pfad, sprachen, zeigen=12):
    alt = Glossar.laden(alt_pfad)
    neu = Glossar.laden(neu_pfad)
    saetze = korpus([alt_pfad, neu_pfad])
    print(f"{BLAU}== {Path(alt_pfad).name} gegen {Path(neu_pfad).name}{AUS}")
    print(f"   {len(saetze)} Texte, Sprachen: {', '.join(sprachen)}")
    fehler = 0
    for sp in sprachen:
        abweichungen = []
        for text in saetze:
            a = glossarzeilen(alt.finde(text), sp)
            n = glossarzeilen(neu.finde(text), sp)
            if a != n:
                abweichungen.append((text, a, n))
        if abweichungen:
            fehler += 1
            print(f"   {ROT}{sp}: {len(abweichungen)} Abweichungen{AUS}")
            for text, a, n in abweichungen[:zeigen]:
                print(f"      Text:    {text[:70]}")
                print(f"      {ROT}vorher:  {a[:150]}{AUS}")
                print(f"      {GRUEN}nachher: {n[:150]}{AUS}")
            if len(abweichungen) > zeigen:
                print(f"      ... und {len(abweichungen) - zeigen} weitere")
        else:
            print(f"   {GRUEN}ok{AUS}   {sp}: unverändert, {len(saetze)} Texte")

    # Der Whisper-Prompt hängt nicht an einer Sprache: er ist deutsch und
    # gilt für alle. Eine neue Zeile mit stt=1 würde ihn verlängern, und
    # faster-whisper schneidet bei 224 Token ab -- hinten fiele dann etwas
    # weg, das vorher drin war. Also auch das vergleichen.
    a_stt = alt.stt_begriffe()
    n_stt = neu.stt_begriffe()
    if a_stt != n_stt:
        fehler += 1
        dazu = [x for x in n_stt if x not in a_stt]
        weg = [x for x in a_stt if x not in n_stt]
        print(f"   {ROT}Whisper-Prompt geändert{AUS}: "
              f"{len(a_stt)} -> {len(n_stt)} Begriffe")
        if dazu:
            print(f"      dazu: {', '.join(dazu[:12])}")
        if weg:
            print(f"      weg:  {', '.join(weg[:12])}")
    else:
        print(f"   {GRUEN}ok{AUS}   Whisper-Prompt: unverändert, "
              f"{len(a_stt)} Begriffe")

    # Persisch bekommt die Vokalzeichen aus dem Glossar. Eine geänderte
    # fa-Spalte oder ein neues fa_vokal würde hier auffallen.
    probe = " ".join(e.ziel.get("fa", "") for e in alt.eintraege
                     if e.ziel.get("fa"))
    from glossar import vokalisieren
    if vokalisieren(alt, probe) != vokalisieren(neu, probe):
        fehler += 1
        print(f"   {ROT}fa-Vokalisierung geändert{AUS}")
    else:
        print(f"   {GRUEN}ok{AUS}   fa-Vokalisierung: unverändert")
    return fehler


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("alt")
    p.add_argument("neu")
    p.add_argument("--sprachen", default="en,ru,fa",
                   help="Komma-getrennt. Vorgabe: en,ru,fa")
    a = p.parse_args()
    sprachen = [s.strip() for s in a.sprachen.split(",") if s.strip()]
    fehler = vergleichen(a.alt, a.neu, sprachen)
    print()
    if fehler:
        print(f"{ROT}{fehler} Sprache(n) haben sich geändert.{AUS}")
        return 1
    print(f"{GRUEN}Keine Sprache hat sich geändert.{AUS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
