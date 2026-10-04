#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Zaehlt, wie verstaendlich die Uebersetzung ankommt -- je Sprache.

Zwei Knoepfe auf der Hoererseite, "verstaendlich" und "schwer
verstaendlich". Mehr nicht. Es ist die einzige Rueckmeldung, die eine
Gemeinde ohne Aufwand geben kann, und sie beantwortet die eine Frage,
die sich sonst niemand traut zu stellen: taugt das ueberhaupt?

WAS HIER NICHT STEHT
--------------------
Keine Adresse, keine Kennung, kein Zeitpunkt je Stimme. Gezaehlt wird
nur, und zwar je Sprache. Aus zwei Zaehlern laesst sich niemand
herauslesen; aus einer Liste von Zeitpunkten schon -- wer um 10:14 in
Farsi "schwer verstaendlich" gedrueckt hat, war der eine Mann in der
dritten Reihe.

Dass jedes Geraet nur einmal zaehlt, merkt sich das GERAET, nicht der
Server. Wer seine Meinung aendert, schickt die alte mit und der
Zaehler geht zurueck. Das laesst sich betruegen, indem jemand den
Browserspeicher leert -- und das ist in Ordnung: hier wird keine Wahl
ausgezaehlt, hier wird ein Eindruck gesammelt.

DIE DATEI
---------
Eine Zeile je Gottesdienst und Sprache, mit Datum. Sie darf dem
Fehlerbericht und der Nutzungsmeldung beiliegen, wenn diese
eingeschaltet sind -- sie enthaelt nichts, was auf einen Menschen
zeigt.
"""

import csv
import threading
from datetime import date
from pathlib import Path

import config

DATEI = config.ERGEBNIS_ORDNER / "rueckmeldung.csv"
SPALTEN = ["datum", "sprache", "verstaendlich", "schwer"]
WERTE = ("gut", "schwer")

_schloss = threading.Lock()
_zaehler = {}          # (datum, sprache) -> {"gut": n, "schwer": n}


def _laden():
    """Liest die Datei beim ersten Zugriff. Fehlt sie, faengt es bei 0 an."""
    if _zaehler or not DATEI.exists():
        return
    try:
        with open(DATEI, encoding="utf-8", newline="") as f:
            for z in csv.DictReader(f, delimiter=";"):
                _zaehler[(z["datum"], z["sprache"])] = {
                    "gut": int(z.get("verstaendlich") or 0),
                    "schwer": int(z.get("schwer") or 0)}
    except Exception:
        # Eine unlesbare Zaehlliste darf den Gottesdienst nicht
        # aufhalten. Dann faengt sie eben neu an.
        _zaehler.clear()


def _speichern():
    try:
        DATEI.parent.mkdir(parents=True, exist_ok=True)
        with open(DATEI, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, delimiter=";", lineterminator="\n")
            w.writerow(SPALTEN)
            for (tag, sprache), n in sorted(_zaehler.items()):
                w.writerow([tag, sprache, n["gut"], n["schwer"]])
    except OSError:
        pass


def zaehlen(sprache, wert, vorher=""):
    """Eine Stimme. Gibt den Stand des Tages zurueck.

    vorher ist, was dasselbe Geraet zuletzt gesagt hat -- dann geht
    der alte Zaehler zurueck. Ohne das zaehlte jeder, der sich
    umentscheidet, doppelt."""
    if wert not in WERTE:
        return stand()
    sprache = str(sprache or "")[:8]
    if not sprache:
        return stand()
    tag = date.today().isoformat()
    with _schloss:
        _laden()
        n = _zaehler.setdefault((tag, sprache), {"gut": 0, "schwer": 0})
        if vorher in WERTE and n[vorher] > 0:
            n[vorher] -= 1
        n[wert] += 1
        _speichern()
    return stand()


def stand(tag=None):
    """Die Zaehler des Tages, je Sprache."""
    tag = tag or date.today().isoformat()
    with _schloss:
        _laden()
        return {sp: dict(n) for (t, sp), n in _zaehler.items() if t == tag}


def zeilen():
    """Alles, als Textzeilen -- fuer den Fehlerbericht."""
    with _schloss:
        _laden()
        return [f"{t};{sp};{n['gut']};{n['schwer']}"
                for (t, sp), n in sorted(_zaehler.items())]
