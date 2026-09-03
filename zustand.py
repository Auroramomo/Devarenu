#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Was pro Gemeinde abweicht, ueber den Neustart hinweg.

config.py gilt fuer alle Gemeinden gleich und wird beim Aktualisieren
ueberschrieben. Hier steht, was genau diesem Rechner gehoert: das
Aufnahmegeraet, die Sprachen, das WLAN und die eingemessene
Mindestlautstaerke. Beides zu trennen ist der ganze Zweck der Datei --
sonst kostet jedes Update dem Techniker seine Einstellungen.

Geschrieben wird bei jeder Aenderung sofort, nicht erst beim Beenden.
Ein Rechner im Gemeindesaal wird selten sauber heruntergefahren, und was
beim Ausschalten verloren geht, muss am naechsten Sabbat neu eingetragen
werden.

Die Datei enthaelt das WLAN-Passwort im Klartext und bekommt deshalb
0600. In .gitignore steht sie ohnehin.
"""

import json
import os
import threading
import time
from pathlib import Path

import config

DATEI = config.BASIS / "zustand.json"

# Steht mit in der Datei, damit ein spaeteres Format erkennbar ist, ohne
# raten zu muessen, was die Schluessel bedeuten.
FASSUNG = 1

# Geschrieben wird aus den Request-Threads des Servers, also aus mehreren
# gleichzeitig. Ohne Schloss koennten sich zwei Schreibvorgaenge
# ueberholen und die Datei mit dem aelteren Stand ueberschreiben.
_schloss = threading.Lock()


def jetzt():
    """Zeitstempel fuer die letzte Messung. Ortszeit, weil ihn ein Mensch
    liest und nicht ein Programm."""
    return time.strftime("%Y-%m-%d %H:%M:%S")


def vorgabe():
    """Was gilt, solange nichts eingestellt wurde: die Werte aus config.py.

    geraet=None heisst Vorgabegeraet des Systems, schwelle.wert=None
    heisst mitlaufende Schwelle statt festgenagelter.

    geraet_name steht neben der Nummer, weil die Nummer allein nicht
    traegt: ohne angemeldete Sitzung zaehlt ALSA weniger Geraete auf als
    mit einer -- die Eintraege fuer PipeWire und Pulse fallen weg, und
    alles dahinter rutscht. Im Systemdienst bezeichnete dieselbe Nummer
    damit ein anderes Geraet als am Pult. Beim Umstecken eines USB-
    Mikrofons verschieben sich auch die vorderen Nummern."""
    return {
        "fassung": FASSUNG,
        "geraet": None,
        "geraet_name": "",
        "quelle": config.AUSGANGSSPRACHE,
        "ziele": list(config.ZIELSPRACHEN),
        "wlan": {"ssid": "", "passwort": ""},
        "schwelle": {"wert": None, "gemessen": None},
    }


def _sprache_pruefen(wert, ersatz):
    return wert if isinstance(wert, str) and wert in config.SPRACHNAMEN \
        else ersatz


def _uebernehmen(roh, daten):
    """Traegt ein, was in der Datei brauchbar ist, und laesst den Rest auf
    der Vorgabe stehen.

    Feld fuer Feld statt dict.update: eine von Hand verpfuschte Zeile soll
    nur ihren eigenen Wert kosten, nicht die ganze Datei. Wer im Editor
    eine Sprache falsch schreibt, soll nicht sein WLAN verlieren."""
    fehlerhaft = []

    if isinstance(roh.get("geraet"), bool):
        # bool ist in Python ein int, waere hier aber Unsinn.
        fehlerhaft.append("geraet")
    elif isinstance(roh.get("geraet"), int):
        daten["geraet"] = roh["geraet"]
    elif roh.get("geraet") is not None:
        fehlerhaft.append("geraet")

    if "geraet_name" in roh:
        if isinstance(roh["geraet_name"], str):
            daten["geraet_name"] = roh["geraet_name"]
        else:
            fehlerhaft.append("geraet_name")

    if "quelle" in roh:
        gueltig = _sprache_pruefen(roh["quelle"], None)
        if gueltig:
            daten["quelle"] = gueltig
        else:
            fehlerhaft.append("quelle")

    if "ziele" in roh:
        if isinstance(roh["ziele"], list):
            daten["ziele"] = [s for s in roh["ziele"]
                              if _sprache_pruefen(s, None)]
        else:
            fehlerhaft.append("ziele")

    wlan = roh.get("wlan")
    if isinstance(wlan, dict):
        daten["wlan"] = {"ssid": str(wlan.get("ssid") or ""),
                         "passwort": str(wlan.get("passwort") or "")}
    elif wlan is not None:
        fehlerhaft.append("wlan")

    schwelle = roh.get("schwelle")
    if isinstance(schwelle, dict):
        wert = schwelle.get("wert")
        if isinstance(wert, (int, float)) and not isinstance(wert, bool):
            # Dieselben Grenzen wie am Pult. Ein von Hand eingetragener
            # Unsinnswert soll den Ton nicht dauerhaft abwuergen.
            daten["schwelle"] = {
                "wert": max(0.0005, min(0.5, float(wert))),
                "gemessen": schwelle.get("gemessen") or None}
        elif wert is not None:
            fehlerhaft.append("schwelle")
    elif schwelle is not None:
        fehlerhaft.append("schwelle")

    return fehlerhaft


def laden():
    """Liest zustand.json. Gibt (daten, herkunft) zurueck.

    Fehlt die Datei oder ist sie kaputt, kommen die Vorgaben aus config.py
    und der Grund steht in herkunft. Kein Abbruch: eine unlesbare
    Einstellungsdatei darf den Gottesdienst nicht verhindern."""
    daten = vorgabe()
    if not DATEI.exists():
        return daten, f"Vorgaben aus config.py ({DATEI.name} gibt es noch nicht)"

    try:
        roh = json.loads(DATEI.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"{DATEI.name} ist unlesbar ({str(e)[:90]}). Es gelten die "
              f"Vorgaben aus config.py. Die Datei bleibt unangetastet, bis "
              f"am Pult etwas geaendert wird.")
        return daten, f"Vorgaben aus config.py ({DATEI.name} unlesbar)"

    if not isinstance(roh, dict):
        print(f"{DATEI.name} enthaelt kein Objekt. Es gelten die Vorgaben "
              f"aus config.py.")
        return daten, f"Vorgaben aus config.py ({DATEI.name} unbrauchbar)"

    fehlerhaft = _uebernehmen(roh, daten)
    if fehlerhaft:
        print(f"{DATEI.name}: unbrauchbare Eintraege "
              f"({', '.join(fehlerhaft)}), dafuer gilt config.py.")
        return daten, f"{DATEI.name}, teilweise (siehe oben)"
    return daten, DATEI.name


def speichern(daten):
    """Schreibt zustand.json. Gibt zurueck, ob es geklappt hat.

    Erst vollstaendig danebenschreiben, dann umbenennen: os.replace ist
    unteilbar, damit gibt es nie eine halb geschriebene Datei, auch wenn
    mitten im Schreiben der Strom ausfaellt. Die Rechte werden vor dem
    Umbenennen gesetzt, sonst laege das WLAN-Passwort einen Moment lang
    lesbar fuer alle da.

    Wirft nicht: aufgerufen wird das aus Request-Handlern, und eine
    volle Platte soll die Einstellung am Pult nicht mit einem Fehler
    quittieren, wenn sie im laufenden Betrieb doch greift."""
    daten["fassung"] = FASSUNG
    neben = DATEI.with_name(DATEI.name + ".neu")
    try:
        with _schloss:
            neben.write_text(
                json.dumps(daten, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8")
            os.chmod(neben, 0o600)
            os.replace(neben, DATEI)
        return True
    except Exception as e:
        print(f"{DATEI.name} liess sich nicht schreiben ({str(e)[:90]}). "
              f"Die Einstellung gilt fuer diesen Lauf, ueberlebt aber den "
              f"Neustart nicht.")
        try:
            neben.unlink(missing_ok=True)
        except Exception:
            pass
        return False


def kurzfassung(daten):
    """Eine Zeile fuer die Startausgabe des Servers."""
    if daten["geraet"] is None and not daten["geraet_name"]:
        geraet = "Vorgabegeraet"
    else:
        geraet = daten["geraet_name"] or f"Geraet {daten['geraet']}"
    schwelle = daten["schwelle"]["wert"]
    return (f"{geraet}, {daten['quelle']} -> "
            f"{', '.join(daten['ziele']) or 'nichts'}, "
            f"Schwelle {'mitlaufend' if schwelle is None else f'{schwelle:.4f}'}"
            f"{', WLAN gesetzt' if daten['wlan']['ssid'] else ''}")


if __name__ == "__main__":
    # Zum Nachsehen von Hand: python zustand.py
    d, woher = laden()
    print(f"Herkunft: {woher}")
    print(json.dumps(d, indent=2, ensure_ascii=False))
