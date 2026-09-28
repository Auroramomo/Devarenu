#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ein Testprotokoll der ganzen Kette -- je Segment eine Zeile.

WOZU

Bei einem Test steht die Frage: wo kippt es? Der Zuhoerer hoert, dass
das Russische falsch war. Daraus laesst sich nicht sagen, ob Whisper
den Satz schon falsch verstanden hat, ob das Modell ihn falsch
uebersetzt hat oder ob nur die Stimme unverstaendlich war. Man braucht
alle drei Zwischenstaende nebeneinander.

Gemessen wurde das alles laengst -- eine_sprache() in server.py gibt
je Zielsprache die Dauer der Uebersetzung und die von Piper zurueck,
die Segmentschleife kennt Tondauer und Whisper-Zeit. Es fehlte nur
jemand, der es aufschreibt.

WAS DAS HIER NICHT IST

Nicht der Schalter "Mitschrift im Protokoll" (protokoll_mitschrift in
zustand.json). Der legt den erkannten Satz ins JOURNAL, gekuerzt, zur
Fehlersuche im Betrieb. Dieses Protokoll ist ausfuehrlich, liegt in
einer Datei und laeuft nur, solange jemand es ausdruecklich
eingeschaltet hat.

DIE REGELN SIND DIE DER AUFNAHME

Was hier steht, ist der Predigttext -- Wort fuer Wort, in allen
Sprachen. Das gehoert der predigenden Person und nicht dem Rechner.
Also:

  * Ohne bestaetigte Einwilligung faengt nichts an. Die Pflicht steht
    HIER und nicht in der Oberflaeche.
  * Nur EIN Haken, anders als bei der Aufnahme: die predigende Person
    wurde gefragt. Der zweite Haken der Aufnahme ("nur die Predigt")
    ergibt hier keinen Sinn -- ein Test laeuft ohnehin nicht im
    Gottesdienst, und ein Haken, den man ohne Inhalt setzt, entwertet
    den anderen.
  * Es stoppt beim Neustart. Der Schalter steht NICHT in
    zustand.json: was mitschreibt, soll nicht aus Versehen ueber
    einen Sonntag weiterlaufen.
  * Sieben Tage, dann weg. Wie die Aufnahme.
  * 700 auf dem Ordner, 600 auf den Dateien, abrufbar nur vom Rechner
    selbst.
"""

import json
import os
import time
from pathlib import Path

import aufnahme

TAGE_VORGABE = aufnahme.TAGE_VORGABE
AUFRAEUMEN_ALLE = aufnahme.AUFRAEUMEN_ALLE


class Protokoll:
    """Schreibt je Segment eine Zeile JSON. Aus, bis jemand es einschaltet."""

    def __init__(self, ordner):
        self.ordner = Path(ordner)
        self.datei = None
        self.einwilligung = None
        self.zeilen = 0
        self.seit = 0.0
        self.fehler = ""

    @property
    def laeuft(self):
        return self.datei is not None

    def starten(self, einwilligung):
        """(datei, fehler). Ohne Einwilligung: (None, "einwilligung_fehlt").

        Die Pruefung steht hier und nicht nur im Browser. Eine Pflicht,
        die sich mit einem curl umgehen laesst, ist keine -- und das
        Pult haengt im Saalnetz."""
        if self.datei:
            return self.datei, ""
        if not isinstance(einwilligung, aufnahme.Einwilligung):
            einwilligung = aufnahme.Einwilligung.aus_daten(einwilligung)
        # NUR der erste Haken. Siehe Modulkopf.
        if not einwilligung.person_gefragt:
            return None, "einwilligung_fehlt"

        self.ordner.mkdir(parents=True, exist_ok=True)
        aufnahme._ordner_sichern(self.ordner)
        stempel = time.strftime("%Y-%m-%d_%H-%M")
        self.datei = self.ordner / f"pruefprotokoll_{stempel}.jsonl"
        try:
            with open(self.datei, "a", encoding="utf-8"):
                pass
        except OSError as e:
            self.datei = None
            return None, f"nicht_schreibbar: {str(e)[:80]}"
        aufnahme._datei_sichern(self.datei)

        # Der Vermerk liegt NEBEN dem Protokoll und heisst wie es. Wer
        # es weitergibt, gibt den Beleg mit; wer es loescht, loescht
        # ihn mit. Kein Name darin -- er belegt, dass gefragt wurde,
        # nicht wer geantwortet hat.
        zettel = self.datei.with_suffix(".einwilligung.txt")
        zettel.write_text(
            "Einwilligung zum Testprotokoll\n"
            f"Bestaetigt am {einwilligung.zeit}\n"
            "\n"
            "[x] Die sprechende Person wurde gefragt und ist "
            "einverstanden.\n"
            "\n"
            "Im Protokoll steht der gesprochene Text und jede\n"
            "Uebersetzung davon, Wort fuer Wort.\n"
            "\n"
            "Kein Name vermerkt. Dieser Zettel belegt, dass gefragt\n"
            "wurde -- nicht, wer geantwortet hat.\n", encoding="utf-8")
        aufnahme._datei_sichern(zettel)

        self.einwilligung = einwilligung
        self.zeilen = 0
        self.seit = time.time()
        self.fehler = ""
        return self.datei, ""

    def beenden(self):
        if not self.datei:
            return None
        lage = {"datei": self.datei.name, "zeilen": self.zeilen,
                "minuten": round((time.time() - self.seit) / 60, 1)}
        self.datei = None
        self.einwilligung = None
        return lage

    def lage(self):
        if not self.datei:
            return None
        return {"datei": self.datei.name, "zeilen": self.zeilen,
                "seit": self.seit,
                "minuten": round((time.time() - self.seit) / 60, 1),
                "fehler": self.fehler}

    # --------------------------------------------------- schreiben

    def segment(self, nummer, quelle, text, audiodauer, stt_s, gesamt_s,
                ergebnisse):
        """Eine Zeile. Fehler hier duerfen die Uebersetzung NIE stoppen.

        Das ist die wichtigste Zeile dieses Moduls. Was hier laeuft,
        haengt mitten in der Segmentschleife -- zwischen dem fertigen
        Satz und dem Ton, der gleich im Saal ankommt. Ein Protokoll,
        das den Gottesdienst anhaelt, waere schlimmer als gar keins.
        Deshalb faengt diese Methode ALLES, und was schiefging, steht
        danach in self.fehler und am Pult."""
        if not self.datei:
            return
        try:
            zeile = {
                "zeit": time.strftime("%Y-%m-%d %H:%M:%S"),
                "nummer": nummer,
                "quelle": quelle,
                "audio_s": round(float(audiodauer), 2),
                "stt_s": round(float(stt_s), 3),
                "gesamt_s": round(float(gesamt_s), 3),
                "text": text,
                "ziele": [],
            }
            for e in ergebnisse or []:
                if not isinstance(e, dict):
                    # Eine Ausnahme aus gather() -- sie gehoert ins
                    # Protokoll, gerade sie.
                    zeile["ziele"].append({"fehler": str(e)[:200]})
                    continue
                zeile["ziele"].append({
                    "sprache": e.get("sprache", ""),
                    "text": e.get("text", ""),
                    "mt_s": round(float(e.get("mt") or 0), 3),
                    "tts_s": round(float(e.get("tts") or 0), 3),
                    "ton_s": round(float(e.get("dauer") or 0), 2),
                })
            with open(self.datei, "a", encoding="utf-8") as f:
                f.write(json.dumps(zeile, ensure_ascii=False) + "\n")
            self.zeilen += 1
        except Exception as e:      # noqa: BLE001 -- siehe Docstring
            self.fehler = str(e)[:120]


# ------------------------------------------------------- Aufraeumen

def protokolle(ordner):
    o = Path(ordner)
    if not o.exists():
        return []
    jetzt = time.time()
    liste = []
    for p in sorted(o.glob("pruefprotokoll_*.jsonl")):
        try:
            st = p.stat()
        except OSError:
            continue
        liste.append({"name": p.name, "pfad": p, "bytes": st.st_size,
                      "stand": st.st_mtime,
                      "tage": (jetzt - st.st_mtime) / 86400})
    liste.sort(key=lambda a: a["stand"], reverse=True)
    return liste


def aufraeumen(ordner, tage=TAGE_VORGABE, jetzt=None, trocken=False):
    """Loescht, was zu alt ist. tage=0 heisst NICHT loeschen.

    Dieselbe Falle wie bei der Aufnahme: ohne die erste Zeile rechnete
    die Grenze auf null Sekunden, und aus "nicht loeschen" wuerde
    "alles sofort loeschen"."""
    if tage <= 0:
        return []
    jetzt = jetzt if jetzt is not None else time.time()
    grenze = tage * 86400
    weg = []
    for a in protokolle(ordner):
        if jetzt - a["stand"] < grenze:
            continue
        weg.append(a)
        if trocken:
            continue
        for p in (a["pfad"], a["pfad"].with_suffix(".einwilligung.txt")):
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass
    return weg
