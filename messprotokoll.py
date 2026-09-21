#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Schreibt mit, was ein Messlauf gekostet hat. Nur fuer die Fehlersuche.

Aus im Normalbetrieb (config.MESSUNG). Wer das einschaltet, misst gegen
eine Datei, nicht gegen den Saal: nur dort sind zwei Laeufe vergleichbar.

Eine Uhr fuer alles: time.perf_counter(), monoton, unabhaengig von der
Wanduhr. Gespeichert wird nicht der rohe Zaehlerstand -- der ist die
Laufzeit des Rechners und in einer CSV unlesbar --, sondern der Abstand
zum Beginn des Laufs. Differenzen zwischen zwei Spalten bleiben dadurch
exakt dieselben, und man kann die Zahlen lesen.

Zwei Dateien je Lauf, plus eine dritte mit dem Zustand der Maschine:

    ergebnisse/messung/<zeitstempel>/
        lauf.json        Sprachen, Modell, Tempo, Poolgroesse, Fassung
        segmente.csv     eine Zeile je Segment UND Zielsprache
        wiedergabe.csv   eine Zeile je Haeppchen auf einem Handy

Geschrieben wird sofort und durchgespuelt. Ein Messlauf wird haeufiger
abgebrochen als zu Ende gefahren, und die halbe Messung ist mehr wert als
keine.

Nur Standardbibliothek. Vor Ort gibt es kein Internet zum Nachinstallieren.
"""

import csv
import json
import threading
import time
from datetime import datetime
from pathlib import Path

import config


# Spalten der Segmentzeile. Reihenfolge ist die der Kette, damit man die
# CSV auch ohne Auswertung von links nach rechts lesen kann.
SEGMENT_SPALTEN = [
    "segment",          # laufende Nummer, wie am Pult
    "sprache",
    "ist_quelle",       # 1 = Originalton, kein Piper, keine Uebersetzung
    # --- die Kette, Sekunden seit Beginn des Laufs ---
    "audio_ende",       # Abschnitt war zu Ende gesprochen, kam in die Schlange
    "whisper_start",
    "whisper_ende",
    "llm_start",
    "llm_ende",
    "piper_start",
    "piper_ende",
    "ws_send",          # an den Zuhoerer abgeschickt
    # --- Mengen ---
    "segment_audio_s",  # Laenge des aufgenommenen Abschnitts
    "ton_audio_s",      # Laenge des erzeugten Haeppchens  <- Zaehler des RTF
    "zeichen",          # Zeichenzahl der Uebersetzung
    # --- Rueckstau ---
    "schlange_ein",     # qsize beim Herausnehmen des Segments
    "schlange_aus",     # qsize, nachdem das Segment fertig war
    "pool_groesse",     # max_workers des ThreadPoolExecutor
    "sprachzahl",       # wie viele Sprachen gerade laufen
    # --- zum Nachlesen ---
    "quelltext",
    "zieltext",
]

WIEDERGABE_SPALTEN = [
    "hoerer",           # zufaellige Kennung je Handy, keine Person
    "sprache",
    "segment",
    "ereignis",         # empfangen | start | ende | verworfen
    "t",                # Sekunden seit Beginn des Laufs
    "luecke_s",         # nur bei "start": Abstand zum Ende des Vorgaengers
]


class Protokoll:
    """Ein Messlauf. Wird einmal angelegt und am Ende geschlossen.

    Alle Methoden sind von mehreren Threads aus aufrufbar: die Segmente
    kommen aus der Verarbeitungsschleife, die Wiedergabezeilen aus dem
    Webserver.
    """

    def __init__(self, t_null, name="", ordner=None):
        self.t_null = t_null
        self._schloss = threading.Lock()
        stempel = datetime.now().strftime("%Y%m%d_%H%M%S")
        if name:
            stempel += "_" + "".join(
                c if c.isalnum() or c in "-_" else "_" for c in name)[:40]
        basis = Path(ordner) if ordner else (config.ERGEBNIS_ORDNER / "messung")
        self.ordner = basis / stempel
        self.ordner.mkdir(parents=True, exist_ok=True)

        self._seg_datei = (self.ordner / "segmente.csv").open(
            "w", newline="", encoding="utf-8")
        self._seg = csv.DictWriter(self._seg_datei, fieldnames=SEGMENT_SPALTEN,
                                   extrasaction="ignore")
        self._seg.writeheader()

        self._wg_datei = (self.ordner / "wiedergabe.csv").open(
            "w", newline="", encoding="utf-8")
        self._wg = csv.DictWriter(self._wg_datei, fieldnames=WIEDERGABE_SPALTEN,
                                  extrasaction="ignore")
        self._wg.writeheader()

        self.zeilen = 0
        self.wiedergabezeilen = 0

    # ---- Zeit -------------------------------------------------------
    def jetzt(self):
        """Sekunden seit Beginn des Laufs, auf derselben monotonen Uhr."""
        return time.perf_counter() - self.t_null

    def seit_null(self, stempel):
        """Rechnet einen rohen perf_counter-Wert auf den Laufbeginn um."""
        return None if stempel is None else round(stempel - self.t_null, 4)

    # ---- Kopfdaten --------------------------------------------------
    def kopf(self, **felder):
        """Was fuer den Vergleich zweier Laeufe bekannt sein muss.

        Die Poolgroesse steht bewusst hier: sie wird beim Start aus der
        damaligen Sprachzahl bestimmt und spaeter nicht mehr angefasst.
        Wer zur Laufzeit eine Sprache dazuschaltet, sieht den Unterschied
        nur, wenn beide Zahlen nebeneinander stehen."""
        felder.setdefault("fassung", config.VERSION)
        felder.setdefault("modell", config.LIVE_MODELL)
        felder.setdefault("live_tempo", config.LIVE_TEMPO)
        felder.setdefault("begonnen", datetime.now().isoformat(timespec="seconds"))
        (self.ordner / "lauf.json").write_text(
            json.dumps(felder, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")

    # ---- Zeilen -----------------------------------------------------
    def segment(self, **felder):
        with self._schloss:
            self._seg.writerow(felder)
            self._seg_datei.flush()
            self.zeilen += 1

    def wiedergabe(self, zeilen):
        """Nimmt ein Buendel vom Handy entgegen.

        Alles hier kommt von aussen, aus einem Browser, den niemand
        kontrolliert. Deshalb wird nicht geschrieben, was geliefert wird,
        sondern nur, was in die bekannten Spalten passt: unbekannte Felder
        fallen weg, Zahlen muessen Zahlen sein, Text wird gekuerzt. Eine
        Zeile, die das nicht erfuellt, wird uebersprungen und nicht
        gemeldet -- ein Messlauf ist kein Ort fuer Fehlerdialoge.

        Gibt zurueck, wie viele Zeilen brauchbar waren."""
        zahlen = {"t", "luecke_s", "segment"}
        gut = 0
        with self._schloss:
            for z in zeilen:
                if not isinstance(z, dict):
                    continue
                sauber = {}
                for spalte in WIEDERGABE_SPALTEN:
                    wert = z.get(spalte)
                    if wert is None:
                        continue
                    if spalte in zahlen:
                        if isinstance(wert, bool) or not isinstance(
                                wert, (int, float)):
                            continue
                        sauber[spalte] = round(float(wert), 4)
                    else:
                        sauber[spalte] = str(wert)[:40]
                # Ohne Ereignis und ohne Zeitpunkt ist eine Zeile nicht
                # auswertbar. Sie kaeme sonst leer in die CSV und wuerde
                # dort als Messwert gelesen.
                if not sauber.get("ereignis") or "t" not in sauber:
                    continue
                self._wg.writerow(sauber)
                gut += 1
            self._wg_datei.flush()
            self.wiedergabezeilen += gut
        return gut

    # ---- Ende -------------------------------------------------------
    def schliessen(self):
        with self._schloss:
            for datei in (self._seg_datei, self._wg_datei):
                try:
                    datei.close()
                except Exception:
                    pass
        return self.ordner
