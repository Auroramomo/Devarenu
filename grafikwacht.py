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
# DIE SPALTE "sprachen" HAT IHRE BEDEUTUNG GEWECHSELT, und die Datei
# sagt es selbst, Zeile fuer Zeile, in der Spalte "zaehlt":
#
#   leer     bis 0.4.5: Zielsprachen PLUS die Ausgangssprache
#   "ziele"  seit 0.4.6: nur die Zielsprachen
#
# Aus "4 Sprachen" in einer alten Zeile wurde so beim Lesen leicht
# "vier Zielsprachen", gemeint waren drei. Alte Zeilen werden nicht
# umgerechnet: was dort steht, war so gemessen.
SPALTEN = ["datum", "speicher_hoechst_mb", "speicher_gesamt_mb",
           "last_hoechst", "last_mittel", "sprachen", "cpu_anteil",
           "messungen", "zaehlt"]
ZAEHLT = "ziele"

# Ab welcher Tagesspitze ein Hinweis kommt. Gemessen in 0.4.5-Vorarbeit
# (RTX 5080, 16 GB): Devarenu selbst braucht rund 10,8 GB, gleich ob mit
# einer oder vier Zielsprachen; die Spitzen liegen nur etwa 100 MB ueber
# dem Dauerwert. 90 Prozent heisst auf 16 GB noch rund 1,6 GB frei --
# Luft fuer das Uebliche, aber nicht fuer ein zweites Sprachmodell.
# Davor warnt der zweite Hinweis, unabhaengig von der Prozentzahl.
SCHWELLE = 0.90
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


def _ollama_ps():
    return _lauf(["ollama", "ps"])


def _auf_cpu(aus):
    if not aus:
        return None
    modell = config.LIVE_MODELL.split(":")[0]
    for zeile in aus.splitlines()[1:]:
        if not zeile.strip() or modell not in zeile:
            continue
        return not bool(_NUR_GPU.search(zeile))
    return None


def _modelle(aus):
    """Wie viele Modelle ollama gerade geladen hat, oder None."""
    if not aus:
        return None
    return sum(1 for z in aus.splitlines()[1:] if z.strip())


def modell_auf_cpu():
    """True, wenn das Live-Modell NICHT ganz auf der Karte liegt.

    None heisst: nicht feststellbar (ollama fehlt, oder das Modell
    ist gerade gar nicht geladen). None ist kein Befund -- zwischen
    zwei Gottesdiensten laedt ollama das Modell von selbst ab."""
    return _auf_cpu(_ollama_ps())


def geladene_modelle():
    """Wie viele Modelle ollama gerade geladen hat, oder None."""
    return _modelle(_ollama_ps())


# Zuletzt gesehene Zahl geladener Modelle, aus der laufenden Messung.
# Nicht in der Datei: sie gilt fuer den Augenblick, nicht fuer den Tag.
_zuletzt_modelle = None


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
                    "messungen": int(z["messungen"] or 0),
                    # Fehlt in Dateien bis 0.4.5 ganz -- dann leer.
                    "zaehlt": (z.get("zaehlt") or "").strip()}
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
                            d["messungen"], d.get("zaehlt", "")])
    except OSError:
        pass


def einmal(sprachen=0):
    """Eine Messung eintragen. Gibt zurueck, was abgelesen wurde.

    sprachen ist die Zahl der ZIELsprachen (seit 0.4.6)."""
    global _zuletzt_modelle
    k = karte()
    if k is None:
        return None
    belegt, gesamt, last = k
    aus = _ollama_ps()
    cpu = _auf_cpu(aus)
    _zuletzt_modelle = _modelle(aus)
    tag = date.today().isoformat()
    with _schloss:
        _laden()
        d = _tage.setdefault(tag, {
            "speicher_hoechst_mb": 0, "speicher_gesamt_mb": gesamt,
            "last_hoechst": 0, "last_summe": 0, "sprachen": 0,
            "cpu_anteil": False, "messungen": 0, "zaehlt": ZAEHLT})
        if d.get("zaehlt") != ZAEHLT:
            # Der Tag des Updates: heute frueh noch mit der alten
            # Zaehlung geschrieben. Ab hier gilt die neue, und die
            # Sprachzahl faengt neu an -- sonst stuende in derselben
            # Zeile das Maximum aus zwei Bedeutungen.
            d["zaehlt"] = ZAEHLT
            d["sprachen"] = 0
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
                "zaehlt": d.get("zaehlt", ""),
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
            + (f"{d['sprachen']} Zielsprachen" if d.get("zaehlt") == ZAEHLT
               else f"{d['sprachen']} Sprachen mit Ausgangssprache")
            + (", TEILS AUF DER CPU" if d["cpu_anteil"] else ""))
    return aus


# ------------------------------------------------------- Hinweise
#
# Bis 0.4.5 sagten Pult und Systemcheck erst etwas, wenn es zu spaet
# war: wenn das Sprachmodell schon teilweise auf die CPU ausgewichen
# war. Jetzt vorher, an zwei Stellen:
#
#   * die Tagesspitze erreicht SCHWELLE (90 Prozent) der Karte;
#   * ollama hat mehr als ein Modell geladen. Das ist der eine Weg, auf
#     dem es bei unveraenderter Sprachzahl ploetzlich eng wird -- ein
#     zweites Modell braucht Gigabytes, und ollama haelt von selbst
#     mehrere vor.
#
# Beides ist ein HINWEIS, keine Stoerung: die Uebersetzung laeuft.
# Geschrieben fuer jemanden am Pult, der mit dem Wort "Grafikspeicher"
# nichts anfangen muss.

def _hinweis(kennung, was, tun, was_en, tun_en):
    return {"kennung": kennung, "was": was, "tun": tun,
            "was_en": was_en, "tun_en": tun_en}


_entwicklung = None


def _ist_entwicklung():
    """Ist dies der Entwicklungsrechner? Einmal je Prozess gefragt.

    entwicklung.py sieht dafuer nach Marke UND privatem Schluessel und
    fragt dabei womoeglich git -- zu teuer fuer jeden Abruf des Pults,
    und die Antwort aendert sich waehrend eines Laufs nicht."""
    global _entwicklung
    if _entwicklung is None:
        try:
            import entwicklung
            _entwicklung = entwicklung.ist_entwicklungsrechner()
        except Exception:
            _entwicklung = False
    return _entwicklung


def hinweise(frisch=False):
    """Die Hinweise zur Grafikkarte, als Liste.

    frisch=True fragt ollama jetzt (Systemcheck beim Start); sonst gilt
    die letzte Messung der laufenden Grafikwacht -- billig genug fuer
    jeden Abruf des Pults.

    Der Hinweis "zu 90 Prozent belegt" faellt auf dem ENTWICKLUNGSRECHNER
    weg (0.5.0): dort liegen neben Devarenu weitere Modelle und Programme
    auf derselben Karte, und der Hinweis stand dort jeden Tag -- ein
    Hinweis, der immer da ist, wird nicht mehr gelesen. Auf einem
    Gemeinderechner bleibt er, wie er war. Der Hinweis zu mehreren
    geladenen Modellen bleibt ueberall."""
    aus = []
    d = heute()
    if d and d["speicher_gesamt_mb"] and not _ist_entwicklung():
        anteil = d["speicher_hoechst_mb"] / d["speicher_gesamt_mb"]
        if anteil >= SCHWELLE:
            p = round(100 * anteil)
            aus.append(_hinweis(
                "grafik_voll",
                f"Die Grafikkarte war heute zu {p} Prozent belegt. Die "
                f"Übersetzung läuft, aber es ist kaum noch Platz. Wird es "
                f"voller, wird sie langsamer.",
                "Während des Gottesdienstes keine weiteren Programme auf "
                "diesem Rechner öffnen. Kommt der Hinweis öfter, dem "
                "Betreuer Bescheid geben.",
                f"The graphics card was {p} % full today. Translation "
                f"works, but there is hardly any room left.",
                "Do not open other programs on this computer during the "
                "service. If this happens again, tell the maintainer."))
    n = geladene_modelle() if frisch else _zuletzt_modelle
    if n is not None and n > 1:
        aus.append(_hinweis(
            "grafik_modelle",
            f"Auf der Grafikkarte sind {n} Sprachmodelle geladen. Gebraucht "
            f"wird eines; jedes weitere nimmt Platz weg und kann die "
            f"Übersetzung verlangsamen.",
            "Nach dem Gottesdienst den Rechner neu starten. Dann lädt nur "
            "das richtige Modell.",
            f"{n} language models are loaded on the graphics card. Only "
            f"one is needed; each extra one takes space.",
            "Restart the computer after the service."))
    return aus


if __name__ == "__main__":
    import sys
    if "--jetzt" in sys.argv:
        k = karte()
        print("nvidia-smi:", k if k else "nicht verfuegbar")
        print("Modell teils auf der CPU:", modell_auf_cpu())
        print("Geladene Modelle:", geladene_modelle())
        for h in hinweise(frisch=True):
            print("HINWEIS:", h["was"])
    else:
        for z in zeilen():
            print(z)
