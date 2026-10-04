#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Schreibt mit, wie voll die Grafikkarte im Betrieb wird.

    python grafikwacht.py --jetzt      einmal nachsehen, nichts schreiben

WOFUER

Die Frage, die bisher niemand beantworten kann: reicht die Karte? Sie
stellt sich erst, wenn eine Gemeinde eine vierte Sprache einschaltet
oder ein groesseres Modell kommt -- und dann steht jemand im
Gottesdienst davor. Also wird sie vorher beantwortet, aus dem
laufenden Betrieb.

Gemessen wird alle 30 Sekunden, solange die Uebersetzung laeuft:

    nvidia-smi   belegter und gesamter Speicher, Auslastung
    ollama ps    liegt das Sprachmodell GANZ auf der Karte?

Das zweite ist das wichtigere. Faellt ein Teil des Modells auf die
CPU, laeuft alles weiter -- nur zehnmal langsamer, und niemand sieht
warum. "100% GPU" heisst gut, alles andere ist ein Befund.

WAS NICHT PASSIERT

Fehlt nvidia-smi, schlaegt es fehl oder dauert es zu lange, wird
still weggelassen. Eine Messung darf den Gottesdienst nie aufhalten;
sie ist eine Auskunft, kein Betriebsteil. Darum auch ein eigener
Faden und kein Schritt in der Uebersetzungskette.

DIE DATEI

Eine Zeile je Tag. Sie darf dem Fehlerbericht und der
Nutzungsmeldung beiliegen: darin steht nichts ueber Menschen,
sondern ueber eine Grafikkarte.
"""

import csv
import re
import subprocess
import threading
import time
from datetime import date
from pathlib import Path

import config

DATEI = config.ERGEBNIS_ORDNER / "grafik.csv"
SPALTEN = ["datum", "speicher_hoechst_mb", "speicher_gesamt_mb",
           "last_hoechst", "last_mittel", "sprachen", "cpu_anteil",
           "messungen"]
TAKT = 30.0

_schloss = threading.Lock()
_tage = {}          # datum -> dict
_faden = None
_aus = threading.Event()


# ------------------------------------------------------- Ablesen

def _lauf(befehl, frist=8):
    """Ruft ein Programm auf. Gibt die Ausgabe zurueck oder None.

    Jeder Fehler ist hier derselbe Fehler: dann gibt es eben keine
    Messung. stdin wird zugemacht -- ein Unterprozess, der auf eine
    Eingabe wartet, haengt sonst bis zur Frist."""
    try:
        r = subprocess.run(befehl, capture_output=True, text=True,
                           timeout=frist, stdin=subprocess.DEVNULL)
    except Exception:
        return None
    if r.returncode != 0:
        return None
    return r.stdout


def karte():
    """(belegt_mb, gesamt_mb, last_prozent) oder None."""
    aus = _lauf(["nvidia-smi",
                 "--query-gpu=memory.used,memory.total,utilization.gpu",
                 "--format=csv,noheader,nounits"])
    if not aus:
        return None
    # Mehrere Karten: die erste Zeile. Devarenu rechnet auf einer.
    zeile = aus.strip().splitlines()[0]
    try:
        belegt, gesamt, last = [int(x.strip()) for x in zeile.split(",")]
    except ValueError:
        return None
    return belegt, gesamt, last


# "100% GPU" heisst ganz auf der Karte. Alles andere -- "48%/52%
# CPU/GPU", "100% CPU" -- heisst, dass ein Teil auf der CPU liegt.
_NUR_GPU = re.compile(r"\b100%\s*GPU\b", re.IGNORECASE)


def modell_auf_cpu():
    """True, wenn das Live-Modell NICHT ganz auf der Karte liegt.

    None heisst: nicht feststellbar (ollama fehlt, oder das Modell
    ist gerade gar nicht geladen). None ist kein Befund -- zwischen
    zwei Gottesdiensten laedt ollama das Modell von selbst ab."""
    aus = _lauf(["ollama", "ps"])
    if not aus:
        return None
    modell = config.LIVE_MODELL.split(":")[0]
    for zeile in aus.splitlines()[1:]:
        if not zeile.strip() or modell not in zeile:
            continue
        return not bool(_NUR_GPU.search(zeile))
    return None


# ------------------------------------------------------ Mitschreiben

def _laden():
    if _tage or not DATEI.exists():
        return
    try:
        with open(DATEI, encoding="utf-8", newline="") as f:
            for z in csv.DictReader(f, delimiter=";"):
                _tage[z["datum"]] = {
                    "speicher_hoechst_mb": int(z["speicher_hoechst_mb"] or 0),
                    "speicher_gesamt_mb": int(z["speicher_gesamt_mb"] or 0),
                    "last_hoechst": int(z["last_hoechst"] or 0),
                    "last_summe": int(z["last_mittel"] or 0)
                                  * int(z["messungen"] or 1),
                    "sprachen": int(z["sprachen"] or 0),
                    "cpu_anteil": z["cpu_anteil"] == "ja",
                    "messungen": int(z["messungen"] or 0)}
    except Exception:
        _tage.clear()


def _speichern():
    try:
        DATEI.parent.mkdir(parents=True, exist_ok=True)
        with open(DATEI, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, delimiter=";", lineterminator="\n")
            w.writerow(SPALTEN)
            for tag, d in sorted(_tage.items()):
                n = max(1, d["messungen"])
                w.writerow([tag, d["speicher_hoechst_mb"],
                            d["speicher_gesamt_mb"], d["last_hoechst"],
                            round(d["last_summe"] / n), d["sprachen"],
                            "ja" if d["cpu_anteil"] else "nein",
                            d["messungen"]])
    except OSError:
        pass


def einmal(sprachen=0):
    """Eine Messung eintragen. Gibt zurueck, was abgelesen wurde."""
    k = karte()
    if k is None:
        return None
    belegt, gesamt, last = k
    cpu = modell_auf_cpu()
    tag = date.today().isoformat()
    with _schloss:
        _laden()
        d = _tage.setdefault(tag, {
            "speicher_hoechst_mb": 0, "speicher_gesamt_mb": gesamt,
            "last_hoechst": 0, "last_summe": 0, "sprachen": 0,
            "cpu_anteil": False, "messungen": 0})
        d["speicher_hoechst_mb"] = max(d["speicher_hoechst_mb"], belegt)
        d["speicher_gesamt_mb"] = gesamt
        d["last_hoechst"] = max(d["last_hoechst"], last)
        d["last_summe"] += last
        d["messungen"] += 1
        d["sprachen"] = max(d["sprachen"], int(sprachen or 0))
        if cpu:
            d["cpu_anteil"] = True
        _speichern()
    return {"belegt": belegt, "gesamt": gesamt, "last": last, "cpu": cpu}


def _schleife(laeuft, sprachen):
    while not _aus.wait(TAKT):
        try:
            if laeuft():
                einmal(sprachen())
        except Exception:
            # Eine Messung, die stirbt, nimmt den Gottesdienst nicht mit.
            pass


def anwerfen(laeuft, sprachen):
    """Startet den Faden. laeuft() und sprachen() fragt er selbst ab."""
    global _faden
    if _faden is not None:
        return
    if karte() is None:
        return              # keine Karte, kein nvidia-smi: still weglassen
    _aus.clear()
    _faden = threading.Thread(target=_schleife, args=(laeuft, sprachen),
                              daemon=True)
    _faden.start()


def anhalten():
    _aus.set()


def heute():
    """Die Zeile von heute, oder None."""
    with _schloss:
        _laden()
        d = _tage.get(date.today().isoformat())
        if not d:
            return None
        n = max(1, d["messungen"])
        return {"speicher_hoechst_mb": d["speicher_hoechst_mb"],
                "speicher_gesamt_mb": d["speicher_gesamt_mb"],
                "last_hoechst": d["last_hoechst"],
                "last_mittel": round(d["last_summe"] / n),
                "sprachen": d["sprachen"],
                "cpu_anteil": d["cpu_anteil"],
                "messungen": d["messungen"]}


def zeilen(hoechstens=14):
    """Die letzten Tage als Textzeilen -- fuer das Pult und den Bericht."""
    with _schloss:
        _laden()
        tage = sorted(_tage.items())[-hoechstens:]
    aus = []
    for tag, d in tage:
        n = max(1, d["messungen"])
        voll = (100 * d["speicher_hoechst_mb"]
                / max(1, d["speicher_gesamt_mb"]))
        aus.append(
            f"{tag}  {d['speicher_hoechst_mb']} von "
            f"{d['speicher_gesamt_mb']} MB ({voll:.0f} %), "
            f"Last {d['last_hoechst']} % Spitze / "
            f"{round(d['last_summe'] / n)} % mittel, "
            f"{d['sprachen']} Sprachen"
            + (", TEILS AUF DER CPU" if d["cpu_anteil"] else ""))
    return aus


if __name__ == "__main__":
    import sys
    if "--jetzt" in sys.argv:
        k = karte()
        print("nvidia-smi:", k if k else "nicht verfuegbar")
        print("Modell teils auf der CPU:", modell_auf_cpu())
    else:
        for z in zeilen():
            print(z)
