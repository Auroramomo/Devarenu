#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Der Server.

    Mikrofon -> Segmentierung -> Whisper -> Uebersetzung -> Piper -> Zuhoerer

Zwei Entscheidungen tragen den Aufbau:

  Segmente NACHEINANDER, die Zielsprachen eines Segments GLEICHZEITIG.
  Nacheinander, weil die Reihenfolge beim Zuhoerer stimmen muss;
  gleichzeitig, weil drei parallele Anfragen bei kleinen Modellen kaum
  mehr kosten als eine -- und das traegt die Latenz.

  Geschnitten wird an Sprechpausen, nicht an Satzzeichen. Satzzeichen
  kennt man erst nach Whisper, also zu spaet.

Aufruf:
    python server.py --geraete            # welche Mikrofone gibt es?
    python server.py --geraet 3 --nur-text
"""

import argparse
import asyncio
import io
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import wave
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np

import config
import messprotokoll
import netzpruefung
import netzzustand
import systemcheck
import ton
import grafikkarte
# Unter anderem Namen, weil weiter unten ein Endpunkt /api/zustand mit der
# Funktion zustand() steht. Die wuerde das Modul im ganzen Namensraum von
# app_bauen verdecken, und zwar still: der Zugriff schluege erst zur
# Laufzeit fehl, beim ersten Speichern am Pult.
import pultschutz
import qr_texte
import zustand as zustandsdatei
from glossar import Glossar, glossarzeilen, vokalisieren

# Die Ausgangssprache wird nicht uebersetzt: der Text kommt aus der
# Spracherkennung, der Ton ist die Originalaufnahme des Predigers. Damit
# ist sie die einzige Ausgabe ohne Uebersetzungsfehler, und zugleich die
# fuer Schwerhoerige, die mitlesen wollen.
QUELLE = config.AUSGANGSSPRACHE
ZIELSPRACHEN = list(config.ZIELSPRACHEN)
SPRACHEN = [QUELLE] + [s for s in ZIELSPRACHEN if s != QUELLE]
MIKRO_RATE = 16000          # was Whisper erwartet

# ------------------------------------------------- Was ins Protokoll darf
#
# Bis 0.2.13 stand bei JEDEM Abschnitt der gesprochene Satz im Journal,
# sechzig Zeichen lang. Dazu die Zuschriften aus dem Saal im Wortlaut
# und die Personennamen aus dem Predigtmanuskript. Das Journal einer
# Gemeinde enthielt damit ueber Monate hinweg Predigtinhalte, Namen und
# das, was Zuhoerer gemeldet haben.
#
# Fuer das Tonband gilt in dieser Gemeinde: es wird nicht aufgehoben.
# Fuer das Transkript gilt dasselbe.
#
# Der Schalter steht in zustand.json, NICHT in config.py: eine
# Aenderung an einer versionierten Datei laesst jedes Update abbrechen.
# Vorgabe ist aus. Am Pult unter Einrichtung laesst er sich zur
# Fehlersuche einschalten; der Systemcheck meldet das, solange er an
# ist.
PROTOKOLL_MITSCHRIFT = False


def schutz(text, laenge=60):
    """Der Text -- oder nur seine Laenge, wenn er nicht ins Protokoll darf.

    Nie ein leeres Feld: eine Zeile ohne jede Angabe waere schlechter
    zu lesen als eine mit "42 Z.". Die Laenge verraet nichts und hilft
    beim Einordnen ("kam da ueberhaupt etwas an?")."""
    if PROTOKOLL_MITSCHRIFT:
        return str(text)[:laenge]
    return f"{len(str(text))} Z."


# systemd legt ALLES, was auf stdout und stderr geht, auf Stufe 6
# (info) -- gemessen mit einer eigenen Unit, stdout und stderr
# gleichermassen. "journalctl -p warning" liefert damit von diesem
# Dienst gar nichts.
#
# Ein vorangestelltes <4> bzw. <3> liest systemd als Stufe. Damit wird
# aus "alles ist info" eine brauchbare Unterscheidung -- und der
# Fehlerbericht, der nur ab Warnstufe sammelt, kann Mitschrift
# konstruktiv nicht enthalten: die Segmentzeilen bleiben info.
#
# Nur, wenn die Ausgabe wirklich ins Journal geht. JOURNAL_STREAM
# allein genuegt nicht: die Variable wird VERERBT. Ein Terminal, das
# unter einer systemd-Sitzung gestartet wurde, traegt sie mit, und
# "bash start.sh" schriebe dann "<4>" in die Konsole -- gemessen, genau
# das passierte.
#
# Haengt die Ausgabe an einem Terminal, liest sie ein Mensch und kein
# Journal.
_UNTER_SYSTEMD = bool(os.environ.get("JOURNAL_STREAM")) and \
    not sys.stdout.isatty()


def warnung(text):
    """Eine Warnung -- im Journal als solche erkennbar."""
    return f"<4>{text}" if _UNTER_SYSTEMD else text


def fehler(text):
    """Ein Fehler -- im Journal als solcher erkennbar."""
    return f"<3>{text}" if _UNTER_SYSTEMD else text
BLOCK = 512                 # Aufnahmeblock, gut 30 ms

# Wie lange auf die Netzwerkadresse gewartet wird. ANLAUF haelt die
# Startausgabe kurz an, FRIST laeuft danach im Hintergrund weiter.
# Gemessen am Dienststart nach dem Einschalten: Ausgabe bei +4s, Adresse
# bei +8s. Fuenf Sekunden fangen den Normalfall, zwei Minuten decken auch
# eine DHCP-Anfrage ab, die in die Frist von 45s laeuft.
ADRESSE_ANLAUF = 5.0
ADRESSE_FRIST = 120.0


# ================================================================
# Segmentierung
# ================================================================

class Segmentierer:
    """Erkennt Sprechpausen und schneidet daran.

    Bewusst energiebasiert und nicht ueber ein VAD-Modell: laeuft ohne
    zusaetzliche Abhaengigkeit, ohne GPU und ohne Latenz.

    Die Schwelle folgt normalerweise dem Grundpegel des Raums, laesst sich
    am Pult aber festnageln. Das ist der Unterschied zwischen Wohnzimmer
    und Gottesdienst: dort soll das Mikrofon uebersetzt werden, nicht das
    Kind in der ersten Reihe. Eine automatische Schwelle zieht bei einem
    ruhigen Prediger irgendwann so weit herunter, dass sie Nebengeraeusche
    mitnimmt."""

    def __init__(self, pause=0.45, min_dauer=1.6, max_dauer=8.0,
                 vorlauf=0.25, min_sprachdauer=0.9):
        self.pause = pause
        self.min_dauer = min_dauer
        self.max_dauer = max_dauer
        self.min_sprachdauer = min_sprachdauer
        self.grundpegel = 0.004
        self.feste_schwelle = None      # None = automatisch
        self.puffer = []
        self.vorpuffer = deque(maxlen=int(vorlauf * MIKRO_RATE / BLOCK) + 1)
        self.stille_bloecke = 0
        self.spricht = False
        self.pegel_jetzt = 0.0
        self.pegel_spitze = 0.0
        self.verworfen = 0
        # Zeitpunkte statt reiner Zaehler: entscheidend ist nicht, wie oft
        # ueberhaupt verworfen wurde, sondern ob es GERADE passiert,
        # waehrend jemand spricht. Vor dem Gottesdienst ist ein voller
        # Zaehler belanglos, mitten in der Predigt ein Notfall.
        self.messung = None
        self.verworfen_zeiten = deque(maxlen=40)
        self.zu_leise = deque(maxlen=400)
        self.durchgelassen_zeiten = deque(maxlen=40)
        self.letzter_laut = 0.0

    def pegel(self, block):
        return float(np.sqrt(np.mean(block.astype(np.float64) ** 2)))

    @property
    def schwelle(self):
        if self.feste_schwelle is not None:
            return self.feste_schwelle
        return max(0.0025, self.grundpegel * 3.5)

    def schub(self, block):
        """Nimmt einen Audioblock, gibt ein fertiges Segment zurueck oder None.

        Die Pausenlaenge wird in Audioblöcken gezaehlt, nicht ueber die
        Wanduhr. Sonst wuerde ein kurzer Hänger des Rechners als Sprechpause
        gelten und mitten im Wort schneiden."""
        p = self.pegel(block)
        self.pegel_jetzt = p
        self.pegel_spitze = max(p, self.pegel_spitze * 0.995)

        messung = getattr(self, "messung", None)
        if messung and time.time() < messung["bis"]:
            messung["werte"].append(p)

        # Auch bei fester Schwelle weiterfuehren: er ist der Bezugspunkt,
        # an dem sich erkennen laesst, ob gerade zu leise gesprochen wird
        # oder ob tatsaechlich niemand spricht.
        if p < self.grundpegel:
            self.grundpegel = 0.9 * self.grundpegel + 0.1 * p
        else:
            self.grundpegel = 0.9995 * self.grundpegel + 0.0005 * p
        laut = p > self.schwelle
        if laut:
            self.letzter_laut = time.time()
        elif p > max(self.grundpegel * 2.5, 0.0015):
            # Hoerbar, aber unter der Schwelle: da spricht jemand zu leise,
            # etwa weil er vom Mikrofon weggetreten ist. Fuer die
            # Segmentierung ist das Stille, fuer den Techniker ein Problem.
            self.zu_leise.append(time.time())

        if not self.spricht:
            self.vorpuffer.append(block)
            if laut:
                self.spricht = True
                self.puffer = list(self.vorpuffer)
                self.vorpuffer.clear()
                self.stille_bloecke = 0
                self.laute_bloecke = 1
            return None

        self.puffer.append(block)
        if laut:
            self.laute_bloecke = getattr(self, "laute_bloecke", 0) + 1
        dauer = len(self.puffer) * BLOCK / MIKRO_RATE
        self.stille_bloecke = 0 if laut else self.stille_bloecke + 1
        stille_dauer = self.stille_bloecke * BLOCK / MIKRO_RATE

        fertig = (stille_dauer >= self.pause and dauer >= self.min_dauer) \
            or dauer >= self.max_dauer
        if not fertig:
            return None

        behalten = max(1, len(self.puffer) - max(0, self.stille_bloecke - 3))
        sprachdauer = getattr(self, "laute_bloecke", 0) * BLOCK / MIKRO_RATE
        audio = np.concatenate(self.puffer[:behalten])
        self.puffer = []
        self.spricht = False
        self.stille_bloecke = 0
        self.laute_bloecke = 0

        # Ein Segment mit weniger als knapp einer Sekunde echtem Schall ist
        # kein Sprechen, sondern ein Huster, eine zuschlagende Tuer oder ein
        # Stuhlruecken. Whisper erfindet daraus zuverlaessig einen
        # plausiblen Satz, deshalb gar nicht erst hinschicken.
        if sprachdauer < self.min_sprachdauer:
            self.verworfen += 1
            self.verworfen_zeiten.append(time.time())
            return None
        self.durchgelassen_zeiten.append(time.time())
        return audio

    def einmessen_starten(self, dauer=12.0):
        """Beginnt eine Messung, aus der sich die Schwelle ableiten laesst.

        Beim ersten Einsatz war die Mindestlautstaerke zu hoch eingestellt,
        und es fehlten Saetze. Das ist kein Bedienfehler, sondern eine
        Zumutung: niemand kann aus einem Balken ablesen, wo genau zwischen
        Raumgeraeusch und Prediger die Grenze liegen muss.

        Waehrend der Messung wird nur beobachtet. Die Schwelle wird erst
        danach gesetzt, aus dem, was tatsaechlich zu hoeren war."""
        self.messung = {"bis": time.time() + dauer, "werte": []}

    def einmessen_lage(self):
        if not getattr(self, "messung", None):
            return None
        rest = self.messung["bis"] - time.time()
        return {"laeuft": rest > 0, "rest": max(0.0, round(rest, 1)),
                "proben": len(self.messung["werte"])}

    def einmessen_auswerten(self, sicherheit=0.6):
        """Leitet aus der Messung eine Schwelle ab.

        Der Gedanke: waehrend der Messung spricht jemand, also gibt es
        laute und leise Abschnitte. Das untere Viertel der Messwerte ist
        der Raum, das obere Viertel die Stimme. Die Schwelle gehoert
        dazwischen, aber naeher am Raum als an der Stimme: eine zu hohe
        Schwelle verschluckt Saetze, eine zu niedrige laesst hoechstens
        ein Rascheln durch, das die Mindestsprechdauer ohnehin abfaengt.

        Deshalb sicherheit=0.6, also sechzig Prozent des Weges vom
        Raumgeraeusch zur Stimme, statt der Mitte."""
        messung = getattr(self, "messung", None)
        self.messung = None
        if not messung or len(messung["werte"]) < 40:
            return None
        werte = sorted(messung["werte"])
        ruhe = werte[len(werte) // 10]                 # unteres Zehntel
        stimme = werte[int(len(werte) * 0.85)]         # oberes Sechstel
        if stimme < ruhe * 2.0 or stimme < 0.004:
            # Kein deutlicher Unterschied: entweder hat niemand gesprochen
            # oder der Raum ist so laut wie die Stimme. Dann lieber nichts
            # setzen als etwas Falsches.
            return {"erfolg": False, "ruhe": round(ruhe, 5),
                    "stimme": round(stimme, 5),
                    "text": "Kein klarer Unterschied zwischen Raum und "
                            "Stimme. Beim Einmessen sprechen lassen und "
                            "den Abstand zum Mikrofon wie im Gottesdienst "
                            "halten."}
        schwelle = ruhe + (stimme - ruhe) * sicherheit
        self.feste_schwelle = max(0.0015, min(0.3, schwelle))
        return {"erfolg": True, "ruhe": round(ruhe, 5),
                "stimme": round(stimme, 5),
                "schwelle": round(self.feste_schwelle, 5),
                "text": f"Schwelle gesetzt. Raum {ruhe:.4f}, "
                        f"Stimme {stimme:.4f}."}

    def lage(self, fenster=90.0):
        """Beurteilt, ob die Einstellung gerade Schaden anrichtet.

        Drei Faelle, die im Betrieb verschieden zu bewerten sind:
        still, wenn seit einer Weile niemand spricht; gut, wenn Abschnitte
        durchkommen; und der Notfall, wenn zwar jemand spricht, aber nichts
        durchkommt oder das meiste verworfen wird."""
        jetzt = time.time()
        v = sum(1 for t in self.verworfen_zeiten if jetzt - t < fenster)
        d = sum(1 for t in self.durchgelassen_zeiten if jetzt - t < fenster)
        seit_laut = jetzt - self.letzter_laut if self.letzter_laut else 999

        # Zu leise: hoerbares Signal, das die Schwelle nicht erreicht.
        # Rund 30 Bloecke sind eine Sekunde; ab drei Sekunden solchen
        # Signals in einer halben Minute stimmt die Einstellung nicht mehr.
        leise = sum(1 for t in self.zu_leise if jetzt - t < 30)
        if leise > 90 and seit_laut > 8:
            return {"stufe": "alarm", "verworfen": v, "durch": d,
                    "text": "Es wird gesprochen, aber zu leise für die "
                            "eingestellte Schwelle. Steht der Prediger "
                            "weiter weg? Regler nach links oder neu "
                            "einmessen."}
        if leise > 30 and d == 0 and seit_laut > 8:
            return {"stufe": "warnung", "verworfen": v, "durch": d,
                    "text": "Leises Sprechen unterhalb der Schwelle. "
                            "Wenn Text fehlt, Regler etwas nach links."}

        if seit_laut > 25 and not v:
            return {"stufe": "still", "verworfen": v, "durch": d,
                    "text": "niemand spricht"}
        if v and v >= max(3, 2 * d):
            return {"stufe": "alarm", "verworfen": v, "durch": d,
                    "text": f"{v} Abschnitte verworfen, nur {d} übersetzt. "
                            f"Mindestlautstärke zu hoch?"}
        if seit_laut < 12 and d == 0 and self.spricht is False:
            return {"stufe": "alarm", "verworfen": v, "durch": d,
                    "text": "Ton kommt an, aber nichts wird übersetzt"}
        if v and v >= d:
            return {"stufe": "warnung", "verworfen": v, "durch": d,
                    "text": f"{v} verworfen gegenüber {d} übersetzt"}
        return {"stufe": "gut", "verworfen": v, "durch": d,
                "text": f"{d} Abschnitte übersetzt"}


# ================================================================
# Verarbeitung
# ================================================================

class Werk:
    """Whisper, Uebersetzung und Piper. Alles blockierend, deshalb laeuft es
    in Threads und nicht im Ereignisschleifen-Thread."""

    def __init__(self, nur_text=False):
        # Vor dem Import von faster_whisper: ctranslate2 darunter oeffnet
        # libcublas erst beim ersten transcribe. Liegt sie nur in der venv,
        # findet der Lader sie nicht, und es scheitert still, Segment fuer
        # Segment. grafikkarte.py schreibt es ausfuehrlich auf.
        geladen = grafikkarte.vorladen()
        from faster_whisper import WhisperModel
        import requests
        self.requests = requests
        self.nur_text = nur_text
        if geladen:
            print(f"CUDA-Bibliotheken vorgeladen: {', '.join(geladen)}")

        self.whisper, self.rechenwerk = self._whisper_laden(WhisperModel)
        self.quelle = QUELLE
        self.glossar = Glossar.laden(config.GLOSSAR_CSV)
        from bibelstellen import Namensindex
        self.namen = Namensindex.laden(config.BASIS / "namen_block_b.csv")
        if self.namen.eintraege:
            print(f"Namensindex: {len(self.namen.eintraege)} Bibelnamen")
        else:
            print("Kein Namensindex (namen_block_b.csv fehlt). Der Prompt "
                  "nutzt dann nur den eingetippten Text.")
        self.stt_prompt = ""
        self.letzter_satz = ""
        self.kontext_stellen = []
        self.kontext_namen = []
        self.skript_namen = []
        self.skript_info = None
        self.verlauf = deque(maxlen=3)

        # Piper einmal laden und behalten. Vorher wurde es je Abschnitt
        # als eigenes Programm gestartet, und die Messung hat gezeigt, dass
        # darin fast die ganze Zeit steckt: 1,7 Sekunden bei nur 1,1- bis
        # 1,5-facher Echtzeit, waehrend Piper laut Herstellerangabe ein
        # Vielfaches schafft. Nicht die Rechenzeit war das Problem, sondern
        # Python-Start, ONNX-Laden und Modell-Einlesen bei jedem Haeppchen.
        # Genau deshalb brachte auch --cuda nichts.
        self.stimmen = {}
        # Welche Datei hinter einer Sprache steckt, als blosser Name:
        # "de_DE-thorsten-medium". Das Tempo haengt an der Stimme, nicht
        # an der Sprache -- zwei portugiesische Stimmen liegen 0,38
        # auseinander, die Sprachmittel nur 0,01.
        self.stimmennamen = {}
        self.piper = None
        self.synth_art = None
        if not nur_text:
            gefunden = stimmen_finden()
            try:
                from piper import PiperVoice
                for sp, datei in gefunden.items():
                    t0 = time.perf_counter()
                    self.stimmennamen[sp] = datei.stem
                    self.stimmen[sp] = PiperVoice.load(str(datei))
                    print(f"Stimme {sp}: {datei.name} "
                          f"({time.perf_counter()-t0:.1f}s)")
                if self.stimmen:
                    self.synth_art = self._synthese_pruefen()
                    self.piper = "modul"
                    print(f"Piper laeuft als Modul ({self.synth_art}).")
            except Exception as e:
                print(f"Piper nicht als Modul nutzbar ({str(e)[:90]}), "
                      f"weiche auf Programmaufruf aus.")
                from laengenfaktor import piper_pfad
                self.piper = piper_pfad()
                self.stimmen = gefunden
                self.stimmennamen = {sp: d.stem for sp, d in gefunden.items()}
            fehlt = [s for s in SPRACHEN if s not in self.stimmen]
            if fehlt:
                print(f"Ohne Stimme, nur Text: {', '.join(fehlt)}")
        self.tmp = config.ERGEBNIS_ORDNER / "live"
        self.tmp.mkdir(parents=True, exist_ok=True)

    def tempo_fuer(self, sprache):
        """Wie schnell diese Sprache gesprochen wird.

        Drei Stufen, von genau nach grob: die gemessene Stimme, die
        Sprache, die Vorgabe. Darauf der Aufschlag fuer schnelle Redner
        und der globale Hebel, am Ende in die Grenzen gestutzt.

        Warum in dieser Reihenfolge: gemessen wird eine Stimme. Wer eine
        andere einsetzt als die ausgelieferte, faellt auf den Sprachwert
        zurueck -- grob, aber naeher dran als eine Zahl fuer alles.

        Die Untergrenze ist kein Schoenheitsfehler, sondern Absicht: eine
        Stimme mit Faktor 0,96 ist schon kuerzer als das Original und hat
        keinen Rueckstand aufzuholen. Sie zusaetzlich zu bremsen, waere
        ein Nachteil ohne Gegenwert."""
        name = self.stimmennamen.get(sprache, "")
        wert = (config.TEMPO_STIMME.get(name)
                or config.TEMPO_SPRACHE.get(sprache)
                or config.TEMPO_VORGABE)
        wert *= config.TEMPO_AUFSCHLAG * config.TEMPO_GLOBAL
        return max(config.TEMPO_MIN, min(config.TEMPO_MAX, wert))

    def stimme_nachladen(self, sprache):
        """Laedt die Stimme einer Sprache, die beim Start nicht dabei war.

        Ohne das waere die Sprachumstellung am Pult eine Falle: die
        Stimmen werden einmal beim Start geladen, und wer spaeter eine
        Sprache dazuwaehlt, bekam stumme Untertitel -- auch dann, wenn
        die Datei laengst auf der Platte lag.

        Laeuft nur am Pult, nie in der Livepipeline: das Laden kostet
        eine knappe Sekunde. Schlaegt es fehl, bleibt es beim
        Untertitel, so wie bisher auch."""
        if self.nur_text or sprache in self.stimmen or self.piper is None:
            return sprache in self.stimmen
        gefunden = stimmen_finden([sprache], quelle=None)
        datei = gefunden.get(sprache)
        if datei is None:
            return False
        try:
            self.stimmennamen[sprache] = datei.stem
            if self.piper == "modul":
                from piper import PiperVoice
                t0 = time.perf_counter()
                self.stimmen[sprache] = PiperVoice.load(str(datei))
                print(f"Stimme {sprache} nachgeladen: {datei.name} "
                      f"({time.perf_counter()-t0:.1f}s)")
            else:
                self.stimmen[sprache] = datei
            return True
        except Exception as e:
            print(f"Stimme {sprache} liess sich nicht laden "
                  f"({str(e)[:70]}). Laeuft als Untertitel.")
            return False

    def _whisper_laden(self, WhisperModel):
        """Laedt Whisper und prueft, ob es wirklich rechnet.

        Zwei Dinge koennen schiefgehen, und sie sahen bisher verschieden
        aus, obwohl beide dasselbe bedeuten: ohne Grafikkarte wirft schon
        das Laden, ohne die CUDA-Bibliotheken laedt es anstandslos und
        jedes einzelne Segment faellt spaeter um. Beides endet hier im
        selben Rueckfall auf die CPU, einmal deutlich gemeldet.

        Zurueck kommt das Modell und eine Zeile, worauf tatsaechlich
        gerechnet wird. Die gehoert in die Startausgabe und ans Pult:
        ohne sie sieht niemand, dass die Karte nicht laeuft."""
        def laden(geraet, rechenart):
            print(f"Whisper {config.WHISPER_MODELL} laedt ({geraet}, "
                  f"{rechenart}) ...")
            return WhisperModel(config.WHISPER_MODELL, device=geraet,
                                compute_type=rechenart,
                                download_root=str(config.MODELL_ORDNER))

        geraet, rechenart = config.WHISPER_DEVICE, config.WHISPER_COMPUTE
        modell, grund = None, ""
        try:
            modell = laden(geraet, rechenart)
        except Exception as e:
            grund = str(e).replace("\n", " ")[:160]
        if modell is not None:
            geht, fehler = grafikkarte.probe(modell)
            if geht:
                return modell, f"{geraet} ({rechenart})"
            grund = fehler

        if geraet == "cpu":
            # Schon die Vorgabe war die CPU. Dann gibt es nichts, worauf
            # zurueckzufallen waere.
            print("\n" + "=" * 62)
            print("WHISPER RECHNET NICHT")
            print(f"  {grund}")
            print("=" * 62 + "\n")
            return modell, f"cpu ({rechenart}), fehlerhaft"

        print("\n" + "=" * 62)
        print("KEINE ERKENNUNG AUF DER GRAFIKKARTE")
        print(f"  {grund}")
        print()
        print("  Es wird auf die CPU zurueckgefallen. Das laeuft, ist fuer")
        print("  den Livebetrieb aber zu langsam: der Rueckstand waechst")
        print("  ueber die Predigt hinweg und holt sich nicht wieder ein.")
        print("  Pruefen mit: .venv/bin/python selbsttest.py")
        print("=" * 62 + "\n")
        modell = laden("cpu", "int8")
        geht, fehler = grafikkarte.probe(modell)
        if not geht:
            print(f"Auch auf der CPU scheitert die Erkennung: {fehler}")
            return modell, "cpu (int8), fehlerhaft"
        return modell, "cpu (int8), Rückfall von der Grafikkarte"

    def _synthese_pruefen(self):
        """Findet heraus, wie diese Piper-Fassung angesprochen werden will.

        Die Schnittstelle hat sich zwischen den Versionen mehrfach
        geaendert: mal nimmt synthesize_wav eine SynthesisConfig, mal
        einzelne Argumente, mal nur Text und Datei. Statt eine Variante zu
        raten und im Gottesdienst damit aufzulaufen, wird sie einmal beim
        Start ausprobiert."""
        import io
        stimme = next(iter(self.stimmen.values()))
        probe = "Test."
        # Hier zaehlt nur, OB Piper einen Tempowert entgegennimmt.
        # Welcher, entscheidet spaeter tempo_fuer je Sprache.
        skala = 1.0 / config.TEMPO_VORGABE

        try:
            from piper import SynthesisConfig
            puffer = io.BytesIO()
            with wave.open(puffer, "wb") as w:
                stimme.synthesize_wav(probe, w,
                                      syn_config=SynthesisConfig(
                                          length_scale=skala))
            return "syn_config"
        except Exception:
            pass
        try:
            puffer = io.BytesIO()
            with wave.open(puffer, "wb") as w:
                stimme.synthesize_wav(probe, w, length_scale=skala)
            return "length_scale"
        except Exception:
            pass
        puffer = io.BytesIO()
        with wave.open(puffer, "wb") as w:
            stimme.synthesize_wav(probe, w)
        # Ohne Tempoeinstellung: der Laengenueberhang von Russisch und
        # Persisch muss dann anders aufgefangen werden.
        print("  Hinweis: diese Piper-Fassung nimmt kein Tempo entgegen, "
              "die Tempotabelle bleibt wirkungslos.")
        return "schlicht"

    # ---- Whisper ----
    # Bei leisen oder rauschigen Abschnitten erfindet Whisper zuverlaessig
    # Standardsaetze aus seinen Trainingsdaten: Abspaenne von
    # Untertitelungsdiensten, Dankesformeln, Kanalnamen. Die klingen
    # plausibel und wandern sonst ungeprueft in die Uebersetzung.
    # Die Senderabspaenne sind gemessen dazugekommen: auf Orgel und
    # Gemeindegesang antwortete large-v3-turbo unter anderem mit
    # "Die Sendung wurde vom NDR live untertitelt." und "WDR mediagroup
    # GmbH im Auftrag des WDR". Beides faengt die alte Fassung nicht,
    # weil sie am Wortanfang haengt und dort "die" bzw. "wdr" steht.
    # Ein Prediger sagt keines von beidem, der Zusatz ist also auch fuer
    # die Livepipeline unbedenklich.
    ERFUNDEN = re.compile(
        r"^\W*(untertitel|untertitelung|amara\.org|copyright|abonniert|"
        r"vielen dank( fuer|für)? (das|ihre|eure)|"
        r"vielen dank\.?$|danke\.?$|tschüss\.?$|"
        r"bis zum n(ä|ae)chsten mal|"
        r"die sendung wurde|"
        r"(wdr|ndr|zdf|ard|swr|mdr|rbb|arte)[ -]?(mediagroup|presse|text)|"
        r"im auftrag (des|der) (wdr|ndr|zdf|ard|swr|mdr|rbb)|"
        r"mit freundlicher unterst(ü|ue)tzung)", re.IGNORECASE)

    def hoeren(self, audio):
        kwargs = dict(language=self.quelle, beam_size=1,
                      vad_filter=False, condition_on_previous_text=False)
        teile = [t for t in [self.stt_prompt, " ".join(self.verlauf)] if t]
        if teile:
            kwargs["initial_prompt"] = " ".join(teile)[-700:]
        segmente, _ = self.whisper.transcribe(audio, **kwargs)
        text = " ".join(s.text.strip() for s in segmente).strip()

        if not text:
            return ""
        if self.ERFUNDEN.match(text):
            return ""
        # Ein Wort, das sich immer wiederholt, ist eine Schleife im Dekoder.
        woerter = text.lower().split()
        if len(woerter) >= 4 and len(set(woerter)) <= 2:
            return ""

        self.verlauf.append(text)
        return text

    # ---- Sprachpruefung am Eingang ----
    # Ab hier gilt ein Abschnitt als "kein Sprechen". Beide Werte sind
    # NEU: no_speech_prob und avg_logprob wurden bisher nirgends
    # ausgewertet, hoeren() wirft die Segmentobjekte weg und behaelt nur
    # den Text.
    #
    # ---- TOT: KEINE_SPRACHE_AB wird nicht weiterverfolgt -------------
    #
    # Die Konstante bleibt stehen und wird weiter geprueft, aber sie
    # kann bei dem Modell, das die Livepipeline benutzt, niemals
    # ausloesen. Nicht nachbessern, nicht feiner einstellen, nicht
    # gegen andere Werte tauschen -- es gibt nichts einzustellen. Wer
    # hier Zeit hineinsteckt, sucht einen Fehler, der keiner ist.
    #
    # Ein anderes Modell koennte den Wert liefern. Das zu pruefen ist
    # eine Aufgabe fuer NACH der Beta: es ginge um das Modell der
    # Livepipeline, und daran wird waehrend der Erprobung in Rostock
    # nichts getauscht.
    #
    # KEINE_SPRACHE_AB ist bei DIESEM Modell wirkungslos, und zwar aus
    # einem nachgewiesenen Grund, nicht aus Zufall: der Token
    # <|nospeech|> (id 50363) steht in suppress_ids der Konvertierung
    # mobiuslabsgmbh/faster-whisper-large-v3-turbo. CTranslate2
    # unterdrueckt ihn beim Dekodieren, seine Wahrscheinlichkeit ist
    # damit zwangsweise null. Gemessen ueber Sprache, Rauschen, Stille
    # und einen 1-kHz-Sinus: immer exakt 0.0. Gegengeprueft auf drei
    # Wegen -- am Segmentfeld, an faster-whispers eigener
    # Unterdrueckung mit no_speech_threshold=1e-7 (unterdrueckt nichts)
    # und direkt an ctranslate2.Whisper.generate (gibt 0.0).
    #
    # Wer ein anderes Modell einsetzt, sollte das nachmessen, bevor er
    # sich auf den Wert verlaesst. Er bleibt stehen, weil er nichts
    # kostet und bei einer Konvertierung ohne diese Unterdrueckung
    # einen Fall abfaengt, den keine Phrasenliste kennt.
    #
    # LOGPROB_MINDESTENS greift dagegen wirklich, wenn auch nicht
    # zuverlaessig. Gemessen auf 1,8-Sekunden-Abschnitten:
    #
    #   Sprache          logp -0.19 bis -0.53   -> durch
    #   Rauschen         logp -0.40             -> durch (Phrasenliste faengt)
    #   Orgel            logp -0.10 bis -0.97   -> durch
    #   Gesang           logp -0.98 bis -1.57   -> teils gefangen
    #
    # Sprache und Musik ueberschneiden sich also. Die Schwelle nimmt
    # einen Teil des Gesangs mit, trennt aber nicht. Was wirklich
    # traegt, ist die Leerlaufphrasenliste ERFUNDEN, davor der Pegel
    # und dahinter MINDESTWOERTER.
    #
    # Zum Nachziehen stehen die Rohwerte je geprueftem Kanal im
    # Ergebnis, nicht nur das Urteil.
    KEINE_SPRACHE_AB = 0.6      # tot bei large-v3-turbo, siehe oben
    LOGPROB_MINDESTENS = -1.0

    def sprache_messen(self, audio):
        """Laesst Whisper einen kurzen Abschnitt hoeren.

        Gibt die Rohwerte zurueck und faellt kein Urteil: das faellt der
        Kanalscan, der auch den Pegel kennt. Hier steht nur, was das
        Modell gesagt hat.

        Kein VAD-Paket: das waere eine neue Abhaengigkeit, eine neue
        Lizenz und ein weiteres Wheel auf den Stick, und der Rechner in
        der Gemeinde hat kein Netz. Whisper liegt ohnehin geladen da und
        liefert zusaetzlich den erkannten Text -- der beantwortet die
        Frage "ist das der Prediger oder das Radio in der Kueche"
        besser als jede Wahrscheinlichkeit.

        Ohne initial_prompt und ohne Verlauf: der Prompt soll die
        Erkennung hier gerade NICHT stuetzen. Ein Glossar, das dem
        Modell Predigtbegriffe nahelegt, macht aus Rauschen eher einen
        frommen Satz, und genau den wollen wir nicht sehen."""
        segmente, _ = self.whisper.transcribe(
            audio, language=self.quelle, beam_size=1, vad_filter=False,
            condition_on_previous_text=False)
        segmente = list(segmente)
        text = " ".join(s.text.strip() for s in segmente).strip()
        if not segmente:
            # Whisper hat gar nichts geschnitten. Das ist die deutlichste
            # Form von "hier spricht niemand".
            return {"text": "", "no_speech_prob": 1.0, "avg_logprob": -9.9}
        # Der schwaechste Beleg zaehlt. Ein einzelnes zuversichtliches
        # Segment neben drei unsicheren ist kein Sprechen, sondern ein
        # Treffer im Rauschen.
        return {
            "text": text,
            "no_speech_prob": max(float(s.no_speech_prob) for s in segmente),
            "avg_logprob": min(float(s.avg_logprob) for s in segmente),
        }

    # ---- Uebersetzung ----
    def uebersetzen(self, text, sprache, kontext=None):
        treffer = self.glossar.finde_in(text, self.quelle)
        gtext = glossarzeilen(treffer, sprache, quelle=self.quelle)
        von = config.SPRACHNAMEN.get(self.quelle, self.quelle)
        system = (f"Du bist Fachuebersetzer fuer christliche Predigttexte. "
                  f"Uebersetze den Abschnitt von {von} nach "
                  f"{config.SPRACHNAMEN[sprache]}.\n"
                  f"Regeln:\n"
                  f"- Gib ausschliesslich die Uebersetzung aus. Keine "
                  f"Erklaerung, keine Anfuehrungszeichen, kein Markdown.\n"
                  f"- Der Abschnitt stammt aus fortlaufender Rede. "
                  f"Uebersetze genau das Gegebene, ohne es zu "
                  f"vervollstaendigen.\n"
                  f"- Achte auf grammatisch korrekte Endungen und darauf, "
                  f"dass Adjektive und Substantive zusammenpassen.\n"
                  f"- Fuege nichts hinzu und lass nichts weg.")
        if kontext:
            system += (f"\n\nDavor wurde bereits gesprochen und uebersetzt:"
                       f"\n---\n{kontext}\n---\n"
                       f"Das dient NUR der Einordnung: es sagt dir, woran "
                       f"der neue Abschnitt anknuepft, welche Personen und "
                       f"Dinge gemeint sind und in welchem Fall und "
                       f"Geschlecht sie stehen. Uebersetze diesen Teil "
                       f"NICHT und gib ihn NICHT aus. Setze nur den neuen "
                       f"Abschnitt passend fort.")
        if gtext:
            system += ("\n\nWortwahlvorgaben fuer einzelne Fachbegriffe. Sie "
                       "sagen nichts ueber Satzbau oder Betonung.\n" + gtext)
        a = self.requests.post(
            f"{config.OLLAMA_URL}/api/chat",
            json={"model": config.LIVE_MODELL, "stream": False, "think": False,
                  "options": {"temperature": 0.1, "num_predict": 400},
                  "messages": [{"role": "system", "content": system},
                               {"role": "user", "content": text}]},
            timeout=30)
        a.raise_for_status()
        t = a.json()["message"]["content"]
        if "</think>" in t:
            t = t.split("</think>", 1)[1]
        return re.sub(r"[*`]+", "", t).strip().strip('"').strip()

    # ---- Piper ----
    def original_ablegen(self, audio, nummer):
        """Legt den aufgenommenen Abschnitt als Datei ab, unveraendert.

        Fuer die Ausgangssprache wird nichts synthetisiert. Wer mitliest,
        hoert den Prediger selbst, und Schwerhoerige bekommen seine Stimme
        direkt ins Ohr statt einer Nachbildung."""
        datei = self.tmp / f"{self.quelle}_{nummer:05d}.wav"
        with wave.open(str(datei), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(MIKRO_RATE)
            w.writeframes((np.clip(audio, -1.0, 1.0) * 32767)
                          .astype(np.int16).tobytes())
        return datei, len(audio) / MIKRO_RATE

    def sprechen(self, text, sprache, nummer):
        if self.nur_text or sprache not in self.stimmen:
            return None, 0.0
        if sprache == "fa":
            # Erst hier, nicht frueher: der Uebersetzungsprompt und die
            # Compliance-Messung arbeiten mit der unvokalisierten Form.
            text = vokalisieren(self.glossar, text)

        datei = self.tmp / f"{sprache}_{nummer:05d}.wav"
        if self.piper == "modul":
            # Piper rechnet umgekehrt: kleinere length_scale bedeutet
            # kuerzere Phoneme, also schnelleres Sprechen.
            skala = 1.0 / self.tempo_fuer(sprache)
            stimme = self.stimmen[sprache]
            with wave.open(str(datei), "wb") as ziel:
                if self.synth_art == "syn_config":
                    from piper import SynthesisConfig
                    stimme.synthesize_wav(
                        text, ziel, syn_config=SynthesisConfig(
                            length_scale=skala))
                elif self.synth_art == "length_scale":
                    stimme.synthesize_wav(text, ziel, length_scale=skala)
                else:
                    stimme.synthesize_wav(text, ziel)
            with wave.open(str(datei)) as w:
                return datei, w.getnframes() / w.getframerate()

        from laengenfaktor import sprich
        dauer = sprich(self.piper, self.stimmen[sprache], text, datei,
                       self.tempo_fuer(sprache))
        return datei, dauer

    @staticmethod
    def lautstaerke_angleichen(datei, ziel=0.85):
        """Bringt eine erzeugte Datei auf einen einheitlichen Pegel.

        Die Piper-Stimmen stammen von verschiedenen Sprechern und sind
        unterschiedlich laut aufgenommen. Im Gottesdienst faellt das sofort
        auf: die persische Stimme war deutlich leiser als die anderen, und
        wer sie hoerte, verstand weniger. Statt eine Stimme einzeln
        hochzudrehen, wird jede Ausgabe auf dieselbe Spitze gebracht.

        Sehr leise Ausgaben werden hoechstens verachtfacht: sonst wuerde
        bei einem fast stillen Stueck nur das Rauschen verstaerkt."""
        try:
            with wave.open(str(datei)) as w:
                anzahl, rate, breite = (w.getnframes(), w.getframerate(),
                                        w.getsampwidth())
                roh = np.frombuffer(w.readframes(anzahl), dtype=np.int16)
            if not len(roh):
                return
            spitze = float(np.abs(roh).max()) / 32768.0
            if spitze < 0.001:
                return
            faktor = min(ziel / spitze, 8.0)
            if abs(faktor - 1.0) < 0.05:
                return
            neu = np.clip(roh.astype(np.float32) * faktor,
                          -32768, 32767).astype(np.int16)
            with wave.open(str(datei), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(breite)
                w.setframerate(rate)
                w.writeframes(neu.tobytes())
        except Exception:
            # Eine misslungene Anpassung darf die Ausgabe nicht verhindern.
            pass

    def eine_sprache(self, text, sprache, nummer, kontext=None, rohton=None):
        t0 = time.perf_counter()
        ziel = (text if sprache == self.quelle
                else self.uebersetzen(text, sprache, kontext))
        t1 = time.perf_counter()

        if sprache == self.quelle and rohton is not None:
            # Kein Piper: der echte Prediger klingt besser als jede
            # synthetische Stimme, und der Ton liegt ohnehin vor. Spart
            # nebenbei eine Synthese je Abschnitt.
            datei, dauer = self.original_ablegen(rohton, nummer)
        else:
            datei, dauer = self.sprechen(ziel, sprache, nummer)
        if datei and sprache != self.quelle:
            # Nur synthetische Stimmen angleichen. Am Originalton wird
            # nichts gedreht, sonst atmet die Lautstaerke von Abschnitt zu
            # Abschnitt und klingt unruhig.
            self.lautstaerke_angleichen(datei, config.LIVE_LAUTSTAERKE)
        t2 = time.perf_counter()
        # mt/tts bleiben als Differenz stehen, die absoluten Stempel kommen
        # dazu: nur mit ihnen laesst sich spaeter sagen, ob zwei Sprachen
        # wirklich gleichzeitig liefen oder hintereinander im Pool warteten.
        return {"sprache": sprache, "text": ziel, "datei": datei,
                "dauer": dauer, "mt": t1 - t0, "tts": t2 - t1,
                "llm_start": t0, "llm_ende": t1,
                "piper_start": t1, "piper_ende": t2}


# ================================================================
# Der Lauf
# ================================================================

SATZENDE = re.compile(r"[.!?…]\s*[\"»)]?\s*$")


class Satzsammler:
    """Fasst Sprechabschnitte zu ganzen Saetzen zusammen.

    Einzeln uebersetzte Bruchstuecke ergeben falsche Wortendungen -- von
    einer russischen Muttersprachlerin bemaengelt. Russisch hat sechs
    Faelle, und welcher richtig ist, ergibt sich aus der Rolle im Satz:
    bei "die Rechtfertigung" allein raet das Modell, ob Subjekt oder
    Objekt. Adjektive richten sich nach ihrem Substantiv, und das steht
    womoeglich erst im naechsten Bruchstueck.

    Deshalb wird gesammelt, bis Whisper ein Satzzeichen setzt. Damit die
    Ausgabe bei einem Redner ohne Punkt nicht stehenbleibt, greifen zwei
    Notbremsen: eine Hoechstzahl an Woertern und eine Hoechstwartezeit."""

    def __init__(self, max_woerter=40, max_warten=9.0):
        self.max_woerter = max_woerter
        self.max_warten = max_warten
        self.teile = []
        self.seit = None
        # Der Ton zu den gesammelten Abschnitten, in derselben
        # Reihenfolge. Die Ausgangssprache liefert den Prediger selbst,
        # und der gehoert zum ganzen Satz, nicht zu seinem letzten
        # Viertel.
        self.toene = []
        # Sprechposition des zuletzt gesammelten Abschnitts. Nur im
        # Dateimodus belegt; sie sagt, wie weit der Prediger war, als
        # das hier zu Ende gesprochen wurde.
        self.pos = None

    def anfang(self):
        """Der bisher gesammelte Satzanfang, ohne ihn abzuschliessen.

        Damit laesst sich ein Bruchstueck sofort uebersetzen und trotzdem
        einordnen: das Modell sieht, woran es anknuepft, und muss den Fall
        nicht raten. Kostet keine Wartezeit."""
        return " ".join(self.teile)

    def mitlesen(self, text):
        """Wie schub, aber ohne zurueckzuhalten: sammelt nur mit, damit
        anfang() weiss, wo im Satz man gerade ist."""
        if not text.strip():
            return
        if SATZENDE.search(text):
            self.teile = []
            self.seit = None
        else:
            self.teile.append(text.strip())
            if self.seit is None:
                self.seit = time.time()
            # Nicht unbegrenzt sammeln: bei einem Redner ohne Punkt wuerde
            # der Kontext sonst immer laenger und irgendwann unbrauchbar.
            if len(" ".join(self.teile).split()) > self.max_woerter:
                self.teile = self.teile[-2:]

    def schub(self, text, ton=None, pos=None):
        """Nimmt einen erkannten Abschnitt.

        Zurueck kommt (Text, Ton, Sprechposition), wenn der Satz fertig
        ist, sonst (None, None, None)."""
        if not text.strip():
            return None, None, None
        self.teile.append(text.strip())
        if ton is not None:
            self.toene.append(ton)
        if pos is not None:
            self.pos = pos
        if self.seit is None:
            self.seit = time.time()
        gesamt = " ".join(self.teile)

        fertig = bool(SATZENDE.search(gesamt)) \
            or len(gesamt.split()) >= self.max_woerter \
            or (time.time() - self.seit) >= self.max_warten
        if not fertig:
            return None, None, None
        return self.abholen()

    def ueberfaellig(self):
        """Liegt etwas da, dessen Frist abgelaufen ist?

        Muss von aussen gefragt werden, und zwar auch dann, wenn nichts
        ankommt. Genau das war die Luecke: schub() prueft die Uhr, aber
        schub() wird nur aufgerufen, wenn ein Abschnitt eintrifft.
        Schweigt der Prediger mitten im Satz, kommt keiner."""
        return bool(self.teile) and self.seit is not None \
            and (time.time() - self.seit) >= self.max_warten

    def abholen(self):
        """Gibt heraus, was dasteht, und macht den Puffer leer.

        Zurueck kommt (Text, Ton, Sprechposition). Der Ton ist der
        aneinandergehaengte Originalton der gesammelten Abschnitte, oder
        None, wenn keiner mitgegeben wurde."""
        if not self.teile:
            return None, None, None
        gesamt = " ".join(self.teile)
        # Nur zusammenhaengen, wenn zu jedem Abschnitt ein Stueck Ton
        # gehoert. Lieber kein Originalton als der falsche -- ein
        # verschobener Ton unter dem richtigen Text faellt niemandem auf
        # und ist doch verkehrt.
        ton = (np.concatenate(self.toene)
               if self.toene and len(self.toene) == len(self.teile) else None)
        pos = self.pos
        self.teile = []
        self.toene = []
        self.seit = None
        self.pos = None
        return gesamt, ton, pos

    def rest(self):
        """Was am Ende noch im Puffer liegt, damit der letzte Satz einer
        Predigt nicht verlorengeht."""
        return self.abholen()[0]


class Mitschnitt:
    """Schreibt den eingehenden Ton in eine Datei.

    Der Ton laeuft ohnehin durch, die Aufnahme kostet also nichts ausser
    Speicherplatz: eine Stunde belegt rund 115 MB. Sie ist zugleich der
    Ersatz fuer die Aufnahme auf USB-Stick, die am Mischpult nicht mehr
    moeglich ist, sobald der Rechner ueber USB angeschlossen ist. Beides
    zugleich unterstuetzt das Pult nicht.

    Geschrieben wird fortlaufend, nicht erst am Ende. Faellt der Strom aus
    oder stuerzt etwas ab, ist alles bis zu diesem Zeitpunkt erhalten."""

    def __init__(self, ordner):
        self.ordner = Path(ordner)
        self.datei = None
        self.griff = None
        self.rahmen = 0

    @property
    def laeuft(self):
        return self.griff is not None

    def starten(self):
        if self.griff:
            return self.datei
        self.ordner.mkdir(parents=True, exist_ok=True)
        self.datei = self.ordner / f"predigt_{time.strftime('%Y-%m-%d_%H-%M')}.wav"
        self.griff = wave.open(str(self.datei), "wb")
        self.griff.setnchannels(1)
        self.griff.setsampwidth(2)
        self.griff.setframerate(MIKRO_RATE)
        self.rahmen = 0
        print(f"Mitschnitt laeuft: {self.datei.name}")
        return self.datei

    def schreiben(self, block):
        if not self.griff:
            return
        try:
            self.griff.writeframes(
                (np.clip(block, -1.0, 1.0) * 32767).astype(np.int16).tobytes())
            self.rahmen += len(block)
        except Exception:
            pass

    def beenden(self):
        if not self.griff:
            return None
        try:
            self.griff.close()
        except Exception:
            pass
        self.griff = None
        dauer = self.rahmen / MIKRO_RATE
        print(f"Mitschnitt beendet: {self.datei.name}, {dauer/60:.1f} min")
        return {"datei": self.datei.name, "minuten": round(dauer / 60, 1)}

    def lage(self):
        if not self.griff:
            return None
        return {"datei": self.datei.name,
                "minuten": round(self.rahmen / MIKRO_RATE / 60, 1)}


class Lauf:
    def __init__(self, werk, segmentierer=None):
        self.werk = werk
        self.segmentierer = segmentierer
        self.laeuft = False
        self.n = 0
        self.begonnen = None
        self.hoerer = defaultdict(set)
        self.toene = {}                    # (sprache, nummer) -> Path
        self.warteschlange = queue.Queue()
        self.letzte = deque(maxlen=30)
        self.latenzen = []
        # Eigene Zeitbasis fuer den Dateimodus. self.begonnen zaehlt ab dem
        # Druck aufs Pult, die Datei startet aber erst nach dem Dekodieren,
        # und das dauert bei einer halben Stunde Ton mehrere Sekunden. Ohne
        # eigene Basis waere die gemessene Latenz um diesen Betrag zu hoch.
        self.datei_beginn = None
        self.datei_tempo = 1.0
        self.wlan = {"ssid": "", "passwort": ""}
        # Was diese Gemeinde eingestellt hat, so wie es in zustand.json
        # steht. main() ersetzt es beim Start durch das Gelesene; hier die
        # Vorgaben, damit die Endpunkte sich auf das Feld verlassen
        # koennen, egal wie der Lauf entstanden ist.
        self.zustand = zustandsdatei.vorgabe()
        # Sprachen sind zur Laufzeit umschaltbar, nicht fest verdrahtet.
        # Eine Gemeinde braucht nie alle gleichzeitig, sondern zwei bis
        # vier, und die Rechenzeit haengt genau daran. Dasselbe Geraet
        # bedient damit den deutschen und den ukrainischen Gottesdienst,
        # nur mit anderer Einstellung.
        self.quelle = QUELLE
        self.ziele = list(ZIELSPRACHEN)
        self.sammler = Satzsammler()
        self._letzte_warnung = -1
        # "kontext" ist der Mittelweg: sofort uebersetzen wie bisher, aber
        # mit dem bisherigen Satzanfang als Einordnung. Keine zusaetzliche
        # Wartezeit, trotzdem weiss das Modell, woran es anknuepft.
        self.betrieb = "kontext"
        # Rueckkanal vom Saal ans Pult. Zuhoerer koennen etwas melden, was
        # sonst niemand erfaehrt: dass eine Sprache fehlt, der Ton zu leise
        # ist oder schlicht, dass es hilft. Bewusst nur in diese Richtung
        # und ohne Antwort: es ist eine Meldung, kein Gespraech.
        self.nachrichten = deque(maxlen=40)
        # Erkennungsfehler: einmal ausschreiben, danach zaehlen. Vorher
        # stand dieselbe Zeile bei jedem Segment neu im Log, und was sich
        # endlos wiederholt, liest niemand mehr.
        self.stt_fehler = {"text": "", "anzahl": 0, "seit": None}
        self.audio_quelle = None
        # Die zuletzt gefundene Netzwerkadresse, None solange es keine
        # gibt. Steht hier, damit sie nicht an drei Stellen neu geraten
        # wird: das Pult, die QR-Notloesung und dienst.sh lesen dasselbe.
        self.adresse = None
        self.mitschnitt = Mitschnitt(config.ERGEBNIS_ORDNER / "predigten")
        self.schleife = None
        self.pool = ThreadPoolExecutor(max_workers=len(SPRACHEN) + 1)
        # Beim Start aus der damaligen Sprachzahl bestimmt und danach nie
        # wieder angefasst -- auch nicht, wenn am Pult eine Sprache
        # dazukommt. Hier festgehalten, damit die Messung beide Zahlen
        # nebeneinanderstellen kann.
        self.pool_groesse = len(SPRACHEN) + 1
        # Fehlersuche, im Normalbetrieb aus. Wird hier angelegt und nicht
        # erst beim Start, damit die Uhr schon laeuft, bevor das erste
        # Segment kommt.
        self.messung = (messprotokoll.Protokoll(time.perf_counter())
                        if config.MESSUNG else None)

    # ---- Zuhoerer ----
    async def anmelden(self, ws, sprache):
        self.hoerer[sprache].add(ws)
        await self._senden(ws, {"typ": "zustand", "live": self.laeuft,
                                "gesendet": self.n})

    def abmelden(self, ws, sprache):
        self.hoerer[sprache].discard(ws)

    @property
    def sprachen(self):
        """Quellsprache zuerst, dann die Zielsprachen ohne Dubletten."""
        return [self.quelle] + [s for s in self.ziele if s != self.quelle]

    @property
    def anzahl(self):
        return {sp: len(self.hoerer.get(sp, ())) for sp in self.sprachen}

    def sprachen_setzen(self, quelle=None, ziele=None):
        """Stellt um, waehrend der Server laeuft.

        Zuhoerer einer abgewaehlten Sprache werden getrennt, sonst warten
        sie auf Abschnitte, die nie kommen. Das Whisper-Modell bleibt
        geladen: die Erkennungssprache ist ein Aufrufparameter, kein
        Bestandteil des Modells."""
        vorher = set(self.sprachen)
        if quelle:
            self.quelle = quelle
        if ziele is not None:
            self.ziele = [z for z in ziele if z in config.SPRACHNAMEN]
        self.werk.quelle = self.quelle
        # Was jetzt neu dazukommt, braucht seine Stimme. Sie wird hier
        # geholt und nicht beim Start: welche Sprachen laufen, entscheidet
        # das Pult, und zwar jederzeit.
        for sp in self.sprachen:
            if sp != self.quelle:
                self.werk.stimme_nachladen(sp)
        self.sammler.teile = []
        self.sammler.toene = []
        self.sammler.seit = None
        self.werk.letzter_satz = ""
        entfallen = vorher - set(self.sprachen)
        return entfallen

    # ---- Steuerung ----
    async def starten(self):
        """Anlaufen und die Zuhoerer davon in Kenntnis setzen.

        Beim Anhalten wurde das immer gemeldet, beim Starten nicht: wer
        waehrend einer Pause wartete, sah nicht, dass es weitergeht."""
        if not self.laeuft:
            self.laeuft = True
            self.begonnen = self.begonnen or time.time()
        await self._streuen_alle({"typ": "zustand", "live": True})

    async def anhalten(self):
        self.laeuft = False
        await self._streuen_alle({"typ": "zustand", "live": False})

    async def zuruecksetzen(self):
        await self.anhalten()
        self.n = 0
        self.begonnen = None
        self.letzte.clear()
        self.werk.verlauf.clear()

    # ---- Verarbeitung ----
    async def verarbeiten(self):
        """Nimmt Segmente aus der Warteschlange und schiebt sie durch die
        Kette. Ein Segment nach dem anderen, damit die Reihenfolge stimmt."""
        eis = asyncio.get_running_loop()
        while True:
            try:
                audio, sprechende, audio_ende = self.warteschlange.get_nowait()
            except queue.Empty:
                # Nichts zu tun -- und genau das ist der Moment, in dem
                # ein angefangener Satz liegenbleibt. schub() prueft die
                # Frist nur beim Eintreffen eines Abschnitts; schweigt
                # der Prediger mitten im Satz, trifft keiner ein.
                if (self.laeuft and self.betrieb == "satz"
                        and getattr(config, "SATZ_NOTBREMSE", True)
                        and self.sammler.ueberfaellig()):
                    text, ton, pos = self.sammler.abholen()
                    if text:
                        jetzt = time.perf_counter()
                        dauer = (len(ton) / MIKRO_RATE if ton is not None
                                 else 0.0)
                        print(warnung(
                            f"[   !] Notbremse nach "
                            f"{self.sammler.max_warten:.0f}s | "
                            f"{schutz(text, 56)}"))
                        # Kein Whisper gelaufen: die Kette faengt hier an
                        # und hoert hier auf. Die Messung soll das sehen,
                        # statt eine Erkennungszeit von null zu melden,
                        # die es nie gab.
                        await self._ausliefern(
                            eis, text, ton, dauer, None,
                            jetzt, jetzt, 0.0, jetzt,
                            self.warteschlange.qsize(), pos)
                await asyncio.sleep(0.05)
                continue
            if not self.laeuft:
                continue

            if self.messung and not self.messung.zeilen:
                # Beim ersten Segment, nicht beim Druck aufs Pult:
                # --datei und --sofort setzen laeuft direkt und
                # kaemen sonst ohne Kopfdaten durch -- also genau die
                # drei Wege, auf denen ueberhaupt gemessen wird.
                self.messung.kopf(
                    quelle=self.quelle, ziele=list(self.ziele),
                    sprachen=list(self.sprachen), betrieb=self.betrieb,
                    pool_groesse=self.pool_groesse,
                    sprachzahl=len(self.sprachen),
                    datei_tempo=self.datei_tempo)

            t0 = time.perf_counter()
            # Vor der Arbeit gemessen: wie viele Abschnitte warten schon.
            # Rueckstau erkennt man nicht am Einzelwert, sondern daran,
            # dass diese Zahl ueber den Lauf waechst.
            schlange_ein = self.warteschlange.qsize()
            audiodauer = len(audio) / MIKRO_RATE
            try:
                text = await eis.run_in_executor(self.pool, self.werk.hoeren, audio)
            except Exception as e:
                meldung = str(e).replace("\n", " ")[:160]
                if meldung != self.stt_fehler["text"]:
                    self.stt_fehler = {"text": meldung, "anzahl": 1,
                                       "seit": time.time()}
                    print("\n" + "=" * 62)
                    print("WHISPER ERKENNT NICHTS")
                    print(f"  {meldung}")
                    print("  Weitere gleiche Fehler werden nur noch gezaehlt")
                    print("  und stehen am Pult.")
                    print("=" * 62 + "\n")
                else:
                    self.stt_fehler["anzahl"] += 1
                continue
            whisper_ende = time.perf_counter()
            if not text or len(text) < 2:
                continue
            stt = whisper_ende - t0

            vorlauf = None
            if self.betrieb == "satz":
                gesammelt, sammelton, sammelpos = self.sammler.schub(
                    text, audio, sprechende)
                if gesammelt is None:
                    print(f"[   .] {audiodauer:4.1f}s Ton, sammle | "
                          f"{schutz(text, 56)}")
                    continue
                text = gesammelt
                if sammelpos is not None:
                    sprechende = sammelpos
                if sammelton is not None:
                    # Der Originalton des GANZEN Satzes, nicht nur seines
                    # letzten Viertels. Vorher bekam die Ausgangssprache
                    # in "satz" nur den ausloesenden Abschnitt, waehrend
                    # der Untertitel daneben den vollen Satz zeigte.
                    audio = sammelton
                    audiodauer = len(audio) / MIKRO_RATE
            elif self.betrieb == "kontext":
                vorlauf = self.sammler.anfang()
                self.sammler.mitlesen(text)

            await self._ausliefern(eis, text, audio, audiodauer, vorlauf,
                                   t0, whisper_ende, stt, audio_ende,
                                   schlange_ein, sprechende)

    async def _ausliefern(self, eis, text, audio, audiodauer, vorlauf,
                          t0, whisper_ende, stt, audio_ende, schlange_ein,
                          sprechende=None):
        """Uebersetzen, vertonen, abschicken, mitschreiben.

        Herausgeloest, weil es zwei Wege hierher gibt: der gewoehnliche
        aus der Warteschlange, und die Notbremse, wenn ein angefangener
        Satz zu lange liegt. Beide muessen dasselbe tun."""
        nummer = self.n
        self.n += 1

        # Deutsch braucht keine Uebersetzung, nur Vertonung. Es laeuft
        # trotzdem im selben Rutsch, damit die Reihenfolge stimmt.
        # Der zuletzt uebersetzte Satz geht als Kontext mit. Er loest
        # Bezuege auf, an denen ein isolierter Satz scheitert: Pronomen,
        # Geschlecht, Zeitform. Fuer flektierende Sprachen wie Russisch
        # ist das der Unterschied zwischen passender und geratener
        # Endung.
        if self.betrieb == "kontext":
            # Der angefangene Satz zaehlt mehr als der letzte fertige:
            # er sagt, woran das Bruchstueck grammatisch anschliesst.
            kontext = vorlauf or self.werk.letzter_satz
        elif self.betrieb == "satz":
            kontext = self.werk.letzter_satz
        else:
            kontext = None
        auftraege = [eis.run_in_executor(self.pool, self.werk.eine_sprache,
                                         text, sp, nummer, kontext,
                                         audio if sp == self.quelle else None)
                     for sp in self.sprachen]
        ergebnisse = await asyncio.gather(*auftraege, return_exceptions=True)

        gesamt = time.perf_counter() - t0
        schlange_aus = self.warteschlange.qsize()
        print(f"[{nummer:4}] {audiodauer:4.1f}s Ton, STT {stt:.2f}s, "
              f"gesamt {gesamt:.2f}s | {schutz(text, 60)}")
        if self.segmentierer:
            lage = self.segmentierer.lage()
            if lage["stufe"] == "alarm" and nummer != self._letzte_warnung:
                print(f"       ACHTUNG: {lage['text']}")
                self._letzte_warnung = nummer

        for e in ergebnisse:
            if isinstance(e, Exception):
                print(f"        Fehler: {str(e)[:80]}")
                continue
            nachricht = {"typ": "segment", "id": nummer, "text": e["text"],
                         "absatz_ende": False, "dauer": round(e["dauer"], 2)}
            if e["datei"]:
                self.toene[(e["sprache"], nummer)] = e["datei"]
                nachricht["audio"] = f"/ton/{e['sprache']}/{nummer}"
            await self._streuen(e["sprache"], nachricht)
            if self.messung:
                m = self.messung
                m.segment(
                    segment=nummer, sprache=e["sprache"],
                    ist_quelle=1 if e["sprache"] == self.quelle else 0,
                    audio_ende=m.seit_null(audio_ende),
                    whisper_start=m.seit_null(t0),
                    whisper_ende=m.seit_null(whisper_ende),
                    llm_start=m.seit_null(e["llm_start"]),
                    llm_ende=m.seit_null(e["llm_ende"]),
                    piper_start=m.seit_null(e["piper_start"]),
                    piper_ende=m.seit_null(e["piper_ende"]),
                    ws_send=round(m.jetzt(), 4),
                    quelle_pos=(round(sprechende, 3)
                                if sprechende is not None else None),
                    segment_audio_s=round(audiodauer, 3),
                    ton_audio_s=round(e["dauer"], 3),
                    zeichen=len(e["text"] or ""),
                    schlange_ein=schlange_ein, schlange_aus=schlange_aus,
                    pool_groesse=self.pool_groesse,
                    sprachzahl=len(self.sprachen),
                    quelltext=text, zieltext=e["text"])

        self.werk.letzter_satz = text
        eintrag = {"id": nummer, "deutsch": text,
                   "stt": round(stt, 2), "gesamt": round(gesamt, 2)}
        if sprechende is not None and self.datei_beginn:
            # Echte Latenz: wie lange nach dem letzten gesprochenen Wort
            # steht die Uebersetzung bereit. Nur im Dateimodus messbar,
            # weil dort die Sprechposition bekannt ist.
            # Wanduhr seit Beginn der Wiedergabe, minus dem Zeitpunkt,
            # zu dem der Abschnitt zu Ende gesprochen war. Bei
            # beschleunigter Wiedergabe muss die Sprechposition
            # entsprechend umgerechnet werden.
            eintrag["latenz"] = round(
                (time.perf_counter() - self.datei_beginn)
                - sprechende / self.datei_tempo, 2)
            self.latenzen.append(eintrag["latenz"])
        self.letzte.append(eintrag)

    def bericht(self):
        """Fasst zusammen, was der Dauerlauf ergeben hat."""
        if self.messung:
            ordner = self.messung.schliessen()
            print(f"\nMessung: {self.messung.zeilen} Segmentzeilen, "
                  f"{self.messung.wiedergabezeilen} Wiedergabezeilen")
            print(f"  {ordner}")
            print(f"  Auswertung:  python auswertung.py {ordner}")
            self.messung = None
        if not self.latenzen:
            print("Keine Latenzen gemessen.")
            return
        import statistics
        n = max(1, len(self.latenzen) // 10)
        anfang = statistics.median(self.latenzen[:n])
        ende = statistics.median(self.latenzen[-n:])
        print("\n" + "=" * 58)
        print(f"{len(self.latenzen)} Segmente")
        print(f"  Latenz Median   {statistics.median(self.latenzen):6.1f}s")
        print(f"  Latenz p90      {sorted(self.latenzen)[int(len(self.latenzen)*0.9)]:6.1f}s")
        print(f"  Latenz maximal  {max(self.latenzen):6.1f}s")
        print(f"  Anfang          {anfang:6.1f}s")
        print(f"  Ende            {ende:6.1f}s")
        print(f"  Drift           {ende-anfang:+6.1f}s")
        if abs(ende - anfang) > 60 or statistics.median(self.latenzen) < 0:
            print("\n  Werte unplausibel. Bei beschleunigter Wiedergabe "
                  "(--tempo) ist die\n  Latenzmessung nicht aussagekraeftig, "
                  "dafuer braucht es Echtzeit.")
        elif ende - anfang > 5:
            print(warnung(
                "\n  Laeuft davon. Uebersetzung muss schneller werden, "
                "oder feiner\n  geschnitten, oder die Wiedergabe staerker "
                "beschleunigt."))
        elif ende - anfang > 2:
            print("\n  Leichter Anstieg. Ueber eine laengere Predigt "
                  "beobachten.")
        else:
            print("\n  Stabil.")
        print("=" * 58)

    # ---- Senden ----
    async def _senden(self, ws, daten):
        try:
            await ws.send_text(json.dumps(daten, ensure_ascii=False))
            return True
        except Exception:
            return False

    async def _streuen(self, sprache, daten):
        tot = []
        for ws in list(self.hoerer[sprache]):
            if not await self._senden(ws, daten):
                tot.append(ws)
        for ws in tot:
            self.hoerer[sprache].discard(ws)

    async def _streuen_alle(self, daten):
        for sp in SPRACHEN:
            await self._streuen(sp, daten)


# ================================================================
# Mikrofon
# ================================================================

def stimmen_finden(sprachen=None, quelle=None):
    """Sucht im Ordner voices die Stimmen zu den genannten Sprachen.

    Ohne Angabe die eingestellten. Mit Angabe beliebige -- das Pult will
    wissen, was auf der Platte LIEGT, nicht nur, was gerade geladen ist.
    Wofuer keine Stimme da ist, laeuft als reiner Untertitel weiter,
    statt den Start zu verhindern."""
    ordner = config.BASIS / "voices"
    treffer = {}
    for sprache in (SPRACHEN if sprachen is None else sprachen):
        if sprache == (QUELLE if quelle is None else quelle):
            continue          # Originalton, keine Stimme noetig
        pfad = config.STIMMEN.get(sprache)
        if not pfad:
            continue
        name = pfad.split("/")[-1]
        if (ordner / f"{name}.onnx").exists() and \
                (ordner / f"{name}.onnx.json").exists():
            treffer[sprache] = ordner / f"{name}.onnx"
    return treffer


def auf_16k(block, rate):
    """Rechnet einen Audioblock auf 16000 Hz herunter.

    Zwei Schritte, beide noetig. Erst ein gleitender Mittelwert als Tiefpass,
    sonst wird alles oberhalb von 8 kHz zurueckgefaltet und landet als
    tieferes Rauschen im Signal. Dann die eigentliche Ratenaenderung: bei
    ganzzahligen Verhaeltnissen wie 48000 exakt, sonst linear interpoliert.
    44100 ist kein Vielfaches von 16000, deshalb reicht Dezimieren dort
    nicht."""
    if rate == MIKRO_RATE:
        return block
    faktor = rate / MIKRO_RATE
    ganz = int(faktor)
    if ganz > 1:
        rest = len(block) % ganz
        gefiltert = (block[:-rest] if rest else block).reshape(-1, ganz).mean(axis=1)
    else:
        gefiltert = block
    if abs(faktor - ganz) < 1e-9:
        return gefiltert
    ziel = int(round(len(block) / faktor))
    return np.interp(np.linspace(0, len(gefiltert) - 1, ziel),
                     np.arange(len(gefiltert)), gefiltert).astype(np.float32)


def mikrofon_thread(lauf, geraet, segmentierer, stoppen, rate, blockgroesse,
                    offen=None, melder=None, kanal=0, kanaele=1):
    """Nimmt auf, bis stoppen gesetzt wird.

    stoppen gehoert diesem einen Thread und ist bewusst nicht das
    Abschalt-Event des Servers: beim Geraetewechsel wird es gesetzt, und
    ein gemeinsames Event waere danach fuer immer gesetzt.

    offen wird gesetzt, sobald der Datenstrom wirklich steht, melder
    nimmt den Grund auf, wenn nicht. Ohne beides wuesste der Aufrufer nur,
    dass er einen Thread gestartet hat, nicht ob Ton ankommt.

    kanal ist der Kanal innerhalb des Geraets. Bei 0 wird geoeffnet wie
    bisher: channels=1, erste Spalte. Das ist kein Sparen, sondern
    Absicht -- die Gemeinden, die heute laufen, laufen auf Kanal 0, und
    sie sollen nach dem Update durch denselben Code laufen. Mehrkanalig
    geoeffnet wird ausschliesslich, wenn wirklich ein hinterer Kanal
    gewaehlt ist: ein Stereogeraet, das man auf zwei Kanaele aufmacht,
    obwohl man nur den linken will, kann an Geraeten scheitern, die
    mono problemlos hergeben."""
    sd = ton.holen()
    if sd is None:
        if melder is not None:
            melder["fehler"] = ton.grund()
        return

    mehrkanal = kanal > 0
    offen_kanaele = kanaele if mehrkanal else 1
    spalte = kanal if mehrkanal else 0

    def rueckruf(daten, rahmen, zeit, status):
        if status:
            print(f"  Audio: {status}")
        # Lebenszeichen. PortAudio ruft hier im festen Takt auf, auch wenn
        # niemand spricht -- Stille setzt den Zeitstempel genauso wie
        # Sprache. Deshalb heisst "seit Sekunden kein Block" wirklich toter
        # Strom und nicht Gebet, Lied oder Pause.
        #
        # Stand frueher nur im WebSocket-Zweig. Am Pult konnte "Ton kommt
        # an" bei lokalem Mikrofon damit ueberhaupt nie aufleuchten.
        lauf.audio_quelle = time.time()
        # Bei kanal=0 ist das buchstaeblich daten[:, 0] wie bisher: der
        # Strom ist dann einkanalig aufgemacht, spalte ist 0. Ein
        # Grossmembranmikrofon liefert ohnehin mono.
        block = auf_16k(daten[:, spalte].copy(), rate)
        lauf.mitschnitt.schreiben(block)
        segment = segmentierer.schub(block)
        if segment is not None and lauf.laeuft:
            lauf.warteschlange.put((segment, None, time.perf_counter()))

    try:
        with sd.InputStream(device=geraet, channels=offen_kanaele,
                            samplerate=rate,
                            blocksize=blockgroesse, dtype="float32",
                            callback=rueckruf):
            if offen is not None:
                offen.set()
            wo = (f", Kanal {zustandsdatei.kanalname(kanal, kanaele)}"
                  if mehrkanal else "")
            print(f"Mikrofon offen: {rate} Hz -> {MIKRO_RATE} Hz{wo}.")
            while not stoppen.is_set():
                time.sleep(0.2)
    except Exception as e:
        if melder is not None:
            melder["fehler"] = str(e).replace("\n", " ")[:200]
        print("\n" + "=" * 62)
        print("MIKROFON LAESST SICH NICHT OEFFNEN")
        print(f"  {str(e)[:200]}")
        print()
        if "WDM-KS" in str(e) or "-9999" in str(e):
            print("  Das ist ein WDM-KS-Geraet. Diese Schnittstelle greift")
            print("  exklusiv auf den Treiber zu und scheitert haeufig, wenn")
            print("  Windows das Mikrofon noch belegt. Nimm stattdessen einen")
            print("  MME- oder WASAPI-Eintrag desselben Mikrofons.")
        print("  Verfuegbare Geraete mit Schnittstelle: server.py --geraete")
        print("  Anderes Geraet waehlen: am Pult unter Einrichtung.")
        print("=" * 62 + "\n")


def datei_thread(lauf, pfad, segmentierer, stoppen, tempo=1.0):
    """Speist eine Aufnahme ein, als kaeme sie aus dem Mikrofon.

    Fuer den Dauerlauf ist das der ehrlichere Test als Vorlesen: dieselbe
    Predigt, reproduzierbar, ohne dass jemand eine halbe Stunde reden muss.
    Und weil die Sprechposition in der Datei bekannt ist, laesst sich die
    echte Latenz messen statt nur die Rechenzeit.

    Eingespeist wird im Echtzeittakt. Schneller einzuspeisen wuerde die
    Warteschlange fluten und genau den Drift verdecken, um den es geht.
    Die Taktung laeuft ueber eine absolute Zeitbasis, weil sich der Fehler
    von time.sleep sonst ueber eine halbe Stunde aufsummiert."""
    from faster_whisper.audio import decode_audio
    print(f"Lade {Path(pfad).name} ...")
    audio = np.asarray(decode_audio(str(pfad), sampling_rate=MIKRO_RATE),
                       dtype=np.float32)
    dauer = len(audio) / MIKRO_RATE
    print(f"{dauer/60:.1f} Minuten Ton, Wiedergabe {tempo}x. "
          f"Der Lauf dauert etwa {dauer/60/tempo:.0f} Minuten.")
    if tempo != 1.0:
        print("ACHTUNG: nicht in Echtzeit. Die Latenzwerte sind dann nicht "
              "auf den Livebetrieb uebertragbar.")

    beginn = time.perf_counter()
    lauf.datei_beginn = beginn
    lauf.datei_tempo = tempo
    i = 0
    while i + BLOCK <= len(audio) and not stoppen.is_set():
        block = audio[i:i + BLOCK]
        i += BLOCK
        segment = segmentierer.schub(block)
        if segment is not None and lauf.laeuft:
            lauf.warteschlange.put((segment, i / MIKRO_RATE, time.perf_counter()))
        soll = beginn + (i / MIKRO_RATE) / tempo
        warte = soll - time.perf_counter()
        if warte > 0:
            time.sleep(warte)

    print(f"\nDatei zu Ende nach {(time.perf_counter()-beginn)/60:.1f} Minuten.")

    # Die Datei ist durch, die Schlange muss es nicht sein. Genau im
    # interessanten Fall -- Rueckstau -- warten hier noch Abschnitte, und
    # ohne dieses Warten fielen sie aus der Messung heraus: der Bericht
    # schliesst das Protokoll. Die Messung wuerde sich damit ausgerechnet
    # dort selbst beschneiden, wo sie etwas zu zeigen haette.
    #
    # Nur im Dateimodus. Der Livebetrieb kommt hier nie vorbei.
    if not stoppen.is_set():
        frist = time.perf_counter() + 300
        while (not lauf.warteschlange.empty()
               and time.perf_counter() < frist):
            time.sleep(0.5)
        # Das zuletzt herausgenommene Segment haengt noch in der Kette.
        # Kurz nachlaufen lassen, statt es abzuschneiden.
        time.sleep(3.0)
        rest = lauf.warteschlange.qsize()
        if rest:
            print(f"ACHTUNG: {rest} Abschnitte blieben in der Schlange "
                  f"liegen. Die Messung ist unvollstaendig.")

    lauf.bericht()


def sockel(port):
    """Ein horchender Socket auf allen Adressen, oder None.

    Getrennt angelegt und nicht uvicorn ueberlassen, weil der Server auf
    ZWEI Ports hoeren soll: 8000 wie bisher und 80 fuer die Handys. Ein
    Handy tippt "10.0.0.1" ohne Port, und die Pruefadressen der
    Hersteller fragen ausschliesslich Port 80."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("0.0.0.0", port))
    except OSError:
        s.close()
        return None
    s.listen(128)
    s.set_inheritable(True)
    return s


def starten_auf(app, port):
    """Startet den Server auf Port 8000 und, wenn moeglich, auch auf 80.

    Port 80 braucht unter tausend das Recht dazu. Der Server laeuft
    trotzdem als gewoehnlicher Benutzer: die Unit gibt ihm
    CAP_NET_BIND_SERVICE. Wo das fehlt -- auf dem Entwicklungsrechner,
    beim Start von Hand --, laeuft er auf 8000 weiter und sagt es.
    Abbrechen waere falsch: Port 80 ist eine Bequemlichkeit fuer die
    Zuhoerer, keine Bedingung fuer den Gottesdienst."""
    import uvicorn
    haupt = sockel(port)
    if haupt is None:
        raise OSError(f"Port {port} ist belegt")
    sockets = [haupt]

    lage = netzzustand.laden()[0]
    if getattr(config, "NETZ_PORT_80", False) and port != 80 and lage["router"]:
        achtzig = sockel(80)
        if achtzig is not None:
            sockets.append(achtzig)
            adresse = lage["adresse"] or config.NETZ_ADRESSE
            print(f"  Zusaetzlich auf Port 80 -- http://{adresse}/")
        else:
            print("  Port 80 nicht moeglich, es bleibt bei "
                  f"{port}. Handys muessen dann die Portnummer mittippen.")
            print("  Dem Dienst fehlt CAP_NET_BIND_SERVICE, oder der Port")
            print("  ist belegt. Siehe AUFSTELLEN.md.")

    kfg = uvicorn.Config(app, log_level="warning")
    uvicorn.Server(kfg).run(sockets=sockets)


def rate_waehlen(geraet, wunsch=None, kanaele=1):
    """Sucht eine Aufnahmerate, die das Geraet wirklich kann.

    Kein handelsuebliches USB-Mikrofon laeuft nativ auf 16000 Hz. 48000 wird
    bevorzugt, weil es genau das Dreifache ist und sich exakt dezimieren
    laesst. 44100 geht auch, kostet aber eine Interpolation.

    kanaele muss zu dem passen, womit der Strom danach wirklich
    aufgemacht wird. Geprueft mit 1, geoeffnet mit 2, waere die Pruefung
    keine: ein Geraet kann mono koennen und stereo nicht."""
    sd = ton.holen()
    if sd is None:
        # Kein PortAudio. Frueher flog der Fehler aus dem Import hier
        # vorbei bis aus main() heraus, und systemd startete in einer
        # Schleife neu. Jetzt ist es dasselbe Ergebnis wie ein Geraet,
        # das keine Rate hergibt -- und der Aufseher behandelt das.
        return None
    kandidaten = [wunsch] if wunsch else [48000, 32000, 16000, 44100]
    for rate in kandidaten:
        try:
            sd.check_input_settings(device=geraet, channels=kanaele,
                                    samplerate=rate, dtype="float32")
            return rate, int(round(BLOCK * rate / MIKRO_RATE))
        except Exception:
            continue
    # Frueher ein SystemExit. Das war vertretbar, solange die Rate nur beim
    # Start gewaehlt wurde. Seit der Gerätewechsel im Betrieb geht, ruft
    # auch ein Endpunkt hier an, und ein unbrauchbares Geraet darf nicht
    # den ganzen Server mitnehmen.
    return None


# Reihenfolge der Schnittstellen. Windows meldet dasselbe Mikrofon
# mehrfach, einmal je Schnittstelle, und die Unterschiede sind erheblich:
# WDM-KS greift exklusiv zu und scheitert oft, MME ist am vertraeglichsten,
# WASAPI hat die geringste Latenz.
#
# Was hier nicht steht, gilt als brauchbar. Frueher fiel alles Unbekannte
# auf 5 und bekam damit das Ausrufezeichen: auf Linux, dem Zielsystem, war
# das jedes einzelne Geraet, mit der Begruendung "WDM-KS" darunter, die es
# dort gar nicht gibt.
API_RANG = {"MME": 0, "Windows WASAPI": 1, "Windows DirectSound": 2,
            "Windows WDM-KS": 9,
            "ALSA": 1, "PulseAudio": 0, "JACK Audio Connection Kit": 3,
            "OSS": 4}


def geraete_liste():
    """Alle Eingabegeraete mit Schnittstelle, empfohlene zuerst.

    Eine Quelle fuer beides: die Terminalausgabe von --geraete und die
    Auswahl am Pult. Zwei getrennte Listen liefen sonst irgendwann
    auseinander, und dann zeigt das Pult eine Nummer an, die das Terminal
    anders zaehlt."""
    sd = ton.holen()
    if sd is None:
        return []
    # Zugehalten: die Aufzaehlung ist es, die ALSA hunderte Zeilen
    # "Expression 'ret' failed" auf stderr schreiben laesst.
    with ton.stumm():
        apis = {i: a["name"] for i, a in enumerate(sd.query_hostapis())}
        geraete = list(enumerate(sd.query_devices()))
    zeilen = []
    for i, g in geraete:
        if g["max_input_channels"] > 0:
            api = apis.get(g["hostapi"], "?")
            rang = API_RANG.get(api, 3)
            zeilen.append({"nummer": i, "name": g["name"],
                           "schnittstelle": api,
                           "kanaele": g["max_input_channels"],
                           "hz": int(g["default_samplerate"]),
                           "empfohlen": rang < 5, "rang": rang})
    zeilen.sort(key=lambda z: (z["rang"], z["nummer"]))
    return zeilen


def geraete_neu_aufzaehlen():
    """PortAudio die Geraete neu aufzaehlen lassen.

    Noetig, weil PortAudio die Liste beim Initialisieren einmal festhaelt.
    Ein Mikrofon, das danach eingesteckt wird, taucht in query_devices()
    NICHT auf -- gemessen: 29 Geraete vorher, 29 nach dem Anstecken, 30
    erst nach diesem Aufruf.

    NUR aufrufen, wenn kein Datenstrom offen ist. _terminate() reisst
    einen offenen Strom mit, wirft dabei aber keine Ausnahme: der Rueckruf
    hoert einfach auf zu feuern. Das ist genau der stille Ausfall, gegen
    den der Aufseher gebaut ist -- an der falschen Stelle wuerde er ihn
    selbst erzeugen. Deshalb steht jeder Aufruf hier unter dem Schloss der
    Tonquelle und hinter der Frage, ob ein Thread laeuft."""
    sd = ton.holen()
    if sd is None:
        return False
    try:
        with ton.stumm():
            sd._terminate()
            sd._initialize()
        return True
    except Exception as e:
        print(f"Geraete neu aufzaehlen fehlgeschlagen: {str(e)[:120]}")
        return False


def geraete_zeigen():
    """Druckt die Geraeteliste ins Terminal.

    Mit dem Hinweis, dass diese Nummern nur hier gelten. Der Systemdienst
    zaehlt anders, und ohne diesen Satz wandert eine Nummer von hier in
    die Einstellung und trifft dort ein anderes Geraet."""
    zeilen = geraete_liste()
    print("Eingabegeraete, empfohlene zuerst:\n")
    print(f"  {'Nr':>3}  {'Schnittstelle':20} {'Hz':>6}  Name")
    for g in zeilen:
        marke = "  " if g["empfohlen"] else " !"
        print(f"{marke}{g['nummer']:3}  {g['schnittstelle']:20} "
              f"{g['hz']:6}  {g['name']}")
    if any(not g["empfohlen"] for g in zeilen):
        print("\n  ! = WDM-KS, greift exklusiv zu und scheitert haeufig.")
    print("\n  ACHTUNG: Diese Nummern gelten fuer einen Start aus diesem")
    print("  Terminal. Der Systemdienst zaehlt anders -- er haelt das")
    print("  benutzte Mikrofon exklusiv offen, und ohne angemeldete Sitzung")
    print("  zeigt ALSA andere Plugin-Eintraege. Auf einem Rechner gemessen:")
    print("  13 Geraete beim Dienst gegen 7 hier, mit anderer Zaehlung.")
    print("  Eine Nummer von hier trifft dort womoeglich ein anderes Geraet.")
    print("\n  Deshalb: am Pult unter Einrichtung AUSWAEHLEN, keine Nummern")
    print("  abtippen. Am Pult wird der Name mitgeschrieben, und nach dem")
    print("  wird gesucht -- der gilt in beiden Zaehlungen.")
    print("\n  Fest vorgeben (nur zur Fehlersuche, aus diesem Terminal):")
    print("    python server.py --geraet <Nummer>")


class Tonquelle:
    """Haelt den Mikrofon-Thread und wechselt ihn im laufenden Betrieb.

    Jeder Thread bekommt sein eigenes Stopp-Event. Vorher war es ein
    einziges, geteilt mit dem Abschalten des Servers -- der neue Thread
    startete dann in eine bereits gesetzte Bedingung, und der Ton war bis
    zum Neustart weg.

    Scheitert ein Wechsel, kommt das vorherige Geraet zurueck. Scheitert
    auch das, laeuft der Server ohne Ton weiter und sagt es: am Pult sitzt
    jemand, der genau jetzt ein anderes Geraet auswaehlen koennen muss."""

    # So lange wird auf den offenen Datenstrom gewartet, bevor der Versuch
    # als gescheitert gilt. Ein USB-Mikrofon meldet sich in Sekundenbruch-
    # teilen; wer laenger braucht, ist belegt oder defekt.
    WARTEN = 5.0

    # Wie oft der Aufseher nachsieht.
    TAKT = 2.0
    # Untergrenze der Totfrist und Deckel fuer den Rueckzug nach
    # gescheitertem Wiederoeffnen.
    FRIST_MINDESTENS = 5.0
    RUECKZUG_MAX = 15.0

    def __init__(self, lauf, segmentierer, wunschrate=None):
        self.lauf = lauf
        self.segmentierer = segmentierer
        self.wunschrate = wunschrate
        self.geraet = None
        self.geraet_name = ""
        # Kanal innerhalb des Geraets und wie viele es hat. 0/1 ist das
        # Verhalten vor der Kanalwahl und bleibt die Vorgabe.
        self.kanal = 0
        self.kanaele = 1
        self.rate = None
        self.blockgroesse = None
        self.fehler = ""
        self._thread = None
        self._stoppen = None
        # Threads, die beim Anhalten die Frist gerissen haben und noch im
        # Treiber stehen. Sie halten ihr Geraet weiter offen; frei()
        # raeumt sie weg, sobald sie durch sind.
        self._haengt = []
        # Zwei Anfragen vom Pult gleichzeitig wuerden sonst zwei Threads
        # auf dasselbe Geraet setzen.
        self._schloss = threading.Lock()

        # Auf welches Geraet der Server eingestellt ist -- Nummer, Name,
        # Kanal und Kanalzahl, so wie sie in zustand.json stehen. Der
        # Aufseher sucht danach.
        self._wunsch = None
        self.wartet_auf = ""
        # Seit wann gewartet wird. Steuert, wie oft gesucht wird.
        self._wartet_seit = None
        self._naechste_suche = 0.0
        self.offen_seit = None
        # Zeitpunkt des letzten selbsttaetigen Wiederoeffnens. Das Pult
        # zeigt es eine Minute lang an: es ist ein Ereignis, kein Zustand.
        self.neu_geoeffnet_um = None
        self._rueckzug = 0.0
        self._naechster_versuch = 0.0
        self._aufseher = None
        self._ende = threading.Event()
        # Worauf zurueckzukehren ist, waehrend der Kanalscan das Geraet
        # hat. Solange das gesetzt ist, liegt _wunsch brach und der
        # Aufseher haelt still -- sonst risse er dem Scan das Geraet
        # unter den Haenden weg, weil kein Block mehr ankommt.
        self._abgegeben = None

    @property
    def laeuft(self):
        return self._thread is not None and self._thread.is_alive()

    @property
    def tot_frist(self):
        """Ab wann ein Strom ohne Block als tot gilt.

        Aus der Blockgroesse abgeleitet statt fest hingeschrieben: bei
        48000 Hz und 2048 Samples kommt alle 43 ms ein Block, bei anderer
        Einstellung anders. Das Zweihundertfache sind rund neun Sekunden
        -- zweihundert ausgefallene Blocke sind kein Ruckler mehr."""
        if not self.rate or not self.blockgroesse:
            return self.FRIST_MINDESTENS
        return max(self.FRIST_MINDESTENS, 200.0 * self.blockgroesse / self.rate)

    def starten(self, geraet, name="", kanal=0, kanaele=1):
        """Einstellen und oeffnen. Gibt (gelungen, lage, einzelheit).

        Ist das Geraet nicht da, wird NICHTS geoeffnet: der Aufseher
        wartet darauf und meldet es ans Pult."""
        with self._schloss:
            self._wunsch = (geraet, name, kanal, kanaele)
            ergebnis = self._versuchen()
        self._aufseher_anwerfen()
        return ergebnis

    def anhalten(self):
        with self._schloss:
            self._wunsch = None
            self.wartet_auf = ""
            self._anhalten()

    def beenden(self):
        """Beim Herunterfahren: den Aufseher gehen lassen."""
        self._ende.set()

    def abgeben(self):
        """Gibt das Geraet an den Kanalscan ab.

        Gibt zurueck, ob der Strom wirklich zu ist. False heisst, er
        haengt noch im Treiber -- dann darf der Scan dieses Geraet noch
        nicht aufmachen.

        Der Aufseher ruht waehrenddessen: _wunsch wird geleert, und
        _nachsehen() steigt darauf sofort aus. Ohne das wuerde er nach
        wenigen Sekunden "Tonstrom tot" feststellen -- richtig erkannt,
        aber falsch geschlossen -- und mitten in die Messreihe hinein
        das alte Geraet wieder aufmachen."""
        with self._schloss:
            if self._abgegeben is None:
                self._abgegeben = self._wunsch or (None, "", 0, 1)
            self._wunsch = None
            self.wartet_auf = ""
            return self._anhalten()

    def zurueckholen(self):
        """Nimmt nach dem Scan wieder die eingestellte Quelle.

        Auch wenn zwischendurch am Pult etwas anderes gewaehlt wurde:
        wechseln() setzt _abgegeben zurueck, und dann gibt es hier nichts
        mehr zu tun."""
        with self._schloss:
            if self._abgegeben is None:
                return True, "", ""
            self._wunsch, self._abgegeben = self._abgegeben, None
            if self._wunsch[0] is None and not self._wunsch[1]:
                # Vor dem Scan lief gar nichts. Dann soll danach auch
                # nichts laufen, statt das Vorgabegeraet aufzumachen.
                self._wunsch = None
                return True, "", ""
            ergebnis = self._versuchen()
        self._aufseher_anwerfen()
        return ergebnis

    # Wie lange "wurde neu geoeffnet" am Pult stehen bleibt. Das ist ein
    # Ereignis und kein Zustand: eine Minute lang soll es jemand sehen
    # koennen, danach ist der Ton einfach wieder da. Im Journal bleibt es.
    EREIGNIS_SICHTBAR = 60.0

    def auffrischen(self):
        """Die Geraeteliste neu aufzaehlen, wenn das gefahrlos geht.

        Gefahrlos heisst: kein Datenstrom offen. Die Pruefung und das
        Aufzaehlen muessen unter demselben Schloss liegen -- sonst oeffnet
        der Aufseher dazwischen einen Strom, und _terminate() nimmt ihn
        still mit."""
        with self._schloss:
            # frei() statt self._thread: ein Strom, der beim Anhalten die
            # Frist gerissen hat, steht noch offen, auch wenn _thread
            # schon geleert ist. _terminate() risse ihn mit.
            if not self.frei():
                return False
            return geraete_neu_aufzaehlen()

    def lage(self):
        """Was das Pult ueber die Tonquelle wissen muss, als Wort.

        Eine Quelle fuer die Einrichtung und fuer die Betriebsansicht.
        Nichts zu melden gibt None zurueck -- dann zeigt das Pult auch
        nichts an, statt einer leeren Zeile."""
        if self.wartet_auf:
            return {"lage": "warte_auf_geraet", "name": self.wartet_auf,
                    "einzelheit": ""}
        if self.fehler:
            return {"lage": "kein_ton", "name": self.geraet_name or "",
                    "einzelheit": self.fehler}
        if (self.neu_geoeffnet_um
                and time.time() - self.neu_geoeffnet_um < self.EREIGNIS_SICHTBAR):
            return {"lage": "neu_geoeffnet", "name": self.geraet_name or "",
                    "einzelheit": ""}
        return None

    # ---- Aufseher ----------------------------------------------------
    def _aufseher_anwerfen(self):
        if self._aufseher is None or not self._aufseher.is_alive():
            self._aufseher = threading.Thread(target=self._aufseher_schleife,
                                              daemon=True)
            self._aufseher.start()

    def _aufseher_schleife(self):
        """Sieht im Takt nach, ob der Ton noch da ist.

        Eigener Thread und keine asyncio-Aufgabe: das Oeffnen eines
        Datenstroms blockiert bis zu fuenf Sekunden. In der
        Ereignisschleife stuenden so lange alle Zuhoerer still -- derselbe
        Grund, aus dem /api/geraete kein async ist.

        Jeder Durchlauf faengt alles ab. Der Aufseher darf den Prozess
        nicht beenden: unter systemd startet Restart=always ihn zwar neu,
        aber ein Neustart mitten im Gottesdienst ist genau das, was hier
        vermieden werden soll. Ein Fehler steht im Journal, dann wird
        weitergemacht."""
        while not self._ende.wait(self.TAKT):
            try:
                self._nachsehen()
            except Exception as e:
                print(f"Aufseher: {type(e).__name__}: {str(e)[:150]}")

    def _nachsehen(self):
        with self._schloss:
            if self._wunsch is None:
                return
            if self.wartet_auf:
                self._warten_pruefen()
            elif self._thread is not None and self._tot():
                self._wiederoeffnen()

    def _suchtakt(self):
        """Wie oft nach dem vermissten Geraet gesehen wird.

        Gestaffelt, weil die beiden Faelle verschieden dringend sind. Beim
        Hochfahren zaehlt jede Sekunde: das Mikrofon ist gleich da, und
        bis dahin steht der Gottesdienst. Fehlt es dagegen dauerhaft --
        Kabel ab, Geraet getauscht --, laeuft der Rechner womoeglich
        stundenlang weiter, und jede Suche zaehlt PortAudio komplett neu
        auf. Alle zwei Sekunden waere das den ganzen Tag lang."""
        gewartet = time.time() - (self._wartet_seit or time.time())
        if gewartet < 60:
            return self.TAKT
        return 10.0 if gewartet < 300 else 30.0

    def _warten_pruefen(self):
        """Ist das vermisste Geraet inzwischen da?

        Hier ist sicher kein Strom offen -- das Warten beginnt ja gerade
        deshalb, weil keiner aufgemacht wurde. Nur darum darf an dieser
        Stelle neu aufgezaehlt werden."""
        jetzt = time.time()
        if jetzt < self._naechster_versuch or jetzt < self._naechste_suche:
            return
        self._naechste_suche = jetzt + self._suchtakt()
        geraete_neu_aufzaehlen()
        nummer, vermisst = self._aufloesen(*self._wunsch)
        if vermisst:
            return
        print(f"Tonquelle \"{self.wartet_auf}\" ist da.")
        self.wartet_auf = ""
        self._wartet_seit = None
        gelungen, _, einzelheit = self._versuchen()
        if not gelungen:
            self._zurueckziehen(einzelheit)

    def _tot(self):
        """Keine Bloecke mehr -- nicht: es ist still.

        Der Rueckruf setzt audio_quelle bei jedem Block, auch bei einem
        voellig leisen. Ein Gebet oder eine Pause im Lied haelt den
        Zeitstempel also frisch; nur ein abgerissener Strom laesst ihn
        altern."""
        letzter = self.lauf.audio_quelle
        if letzter is None:
            # Nie ein Block angekommen. Ein Strom, der aufging und seither
            # schweigt, ist ebenso tot -- nur merkt man es sonst nie.
            return (self.offen_seit is not None
                    and time.time() - self.offen_seit > self.tot_frist)
        return time.time() - letzter > self.tot_frist

    def _wiederoeffnen(self):
        if time.time() < self._naechster_versuch:
            return
        alt = self.geraet_name or self.geraet
        print(f"Tonstrom tot (seit ueber {self.tot_frist:.0f} s kein Block), "
              f"oeffne {alt} neu.")
        # Erst schliessen, dann neu aufzaehlen: vorher waere der Strom noch
        # offen, und _terminate() risse ihn mit, ohne etwas zu melden.
        # Haengt er noch im Treiber, wird NICHT neu aufgezaehlt -- lieber
        # mit der alten Liste oeffnen als den haengenden Strom zerreissen.
        if self._anhalten():
            geraete_neu_aufzaehlen()
        gelungen, _, einzelheit = self._versuchen()
        if gelungen:
            self._rueckzug = 0.0
            self._naechster_versuch = 0.0
            self.neu_geoeffnet_um = time.time()
            print("Tonstrom wieder offen.")
        else:
            self._zurueckziehen(einzelheit)

    def _zurueckziehen(self, grund):
        """Nach einem gescheiterten Versuch laenger warten.

        Ein abgezogener Stecker wuerde sonst im Zweisekundentakt dieselbe
        Zeile ins Journal schreiben, bis ihn jemand wieder einsteckt."""
        self._rueckzug = min(self.RUECKZUG_MAX,
                             self._rueckzug * 2 if self._rueckzug else 2.0)
        self._naechster_versuch = time.time() + self._rueckzug
        print(f"Tonquelle nicht offen ({str(grund)[:100]}), "
              f"naechster Versuch in {self._rueckzug:.0f} s.")

    def _versuchen(self):
        """Aufloesen und oeffnen. Immer unter dem Schloss."""
        nummer, vermisst = self._aufloesen(*self._wunsch)
        _, _, kanal, kanaele = self._wunsch
        if vermisst:
            if self.wartet_auf != vermisst:
                print(f"Tonquelle \"{vermisst}\" ist nicht da. Es wird auf "
                      f"sie gewartet, kein anderes Geraet genommen.")
                self._wartet_seit = time.time()
                self._naechste_suche = 0.0
            self.wartet_auf = vermisst
            return False, "warte_auf_geraet", ""
        self.wartet_auf = ""
        gelungen, einzelheit = self._starten(nummer, kanal, kanaele)
        return gelungen, ("" if gelungen else "kein_ton"), einzelheit

    def wechseln(self, geraet, kanal=0, kanaele=1):
        """Stellt auf ein anderes Aufnahmegeraet um.

        Gibt (True, "", "") zurueck oder (False, Lage, Einzelheit).

        Lage ist ein Wort, aus dem das Pult seinen Satz baut -- auf
        Deutsch oder Englisch, je nachdem, was dort eingestellt ist.
        Einzelheit ist die Meldung des Treibers und bleibt, wie sie kommt:
        sie ist meist ohnehin englisch, und uebersetzen liesse sie sich
        nicht, ohne sie zu verfaelschen."""
        with self._schloss:
            # Erst fragen, dann anfassen. Vorher wurde der laufende Strom
            # bedingungslos geschlossen und erst danach geprueft, ob das
            # neue Geraet ueberhaupt taugt. Auf dem Gemeinderechner stand
            # deshalb im Wechsel
            #     "Mikrofon offen: 48000 Hz -> 16000 Hz"
            #     "Geraetewechsel gescheitert (zurueck): Keine der
            #      ueblichen Aufnahmeraten funktioniert mit diesem Geraet."
            # -- die erste Zeile war die Rueckkehr, nicht der Wechsel. Ein
            # gescheiterter Wechsel darf die laufende Quelle nicht
            # anruehren.
            pruef_kanaele = kanaele if kanal > 0 else 1
            if rate_waehlen(geraet, self.wunschrate, pruef_kanaele) is None:
                grund = ("Keine der ueblichen Aufnahmeraten funktioniert "
                         "mit diesem Geraet.")
                self.fehler = grund
                return False, "kein_ton", grund

            vorher = (self.geraet, self.geraet_name, self.kanal, self.kanaele)
            self._anhalten()
            gelungen, grund = self._starten(geraet, kanal, kanaele)
            if gelungen:
                # Die Wahl am Pult sticht jedes Warten. Ab jetzt sucht der
                # Aufseher dieses Geraet, nicht mehr das vermisste.
                self.wartet_auf = ""
                self._wunsch = (self.geraet, self.geraet_name,
                                self.kanal, self.kanaele)
                # Die Wahl am Pult sticht auch die Rueckkehr nach dem
                # Scan. Sonst waehlt jemand waehrend der Messreihe eine
                # Quelle, und das Schliessen der Liste holt die alte
                # zurueck.
                self._abgegeben = None
                self._rueckzug = 0.0
                self._naechster_versuch = 0.0
                return True, "", ""
            # Zurueck auf das, was vorher lief -- Kanal eingeschlossen.
            # Ohne ihn landete ein gescheiterter Wechsel auf dem rechten
            # Kanal still wieder auf dem linken desselben Geraets, und am
            # Pult stuende weiter R.
            if vorher[0] is not None and (vorher[0], vorher[2]) != (geraet, kanal):
                zurueck, _ = self._starten(vorher[0], vorher[2], vorher[3])
                if zurueck:
                    self._wunsch = vorher
                    return False, "zurueck", grund
            self.fehler = grund
            return False, "kein_ton", grund

    @staticmethod
    def _name_zu(nummer):
        """Wie das Geraet mit dieser Nummer gerade heisst."""
        try:
            for g in geraete_liste():
                if g["nummer"] == nummer:
                    return g["name"]
        except Exception:
            pass
        return ""

    @staticmethod
    def _aufloesen(nummer, name, kanal=0, kanaele=1):
        """Welche Nummer heute zu dieser Auswahl gehoert.

        Der Name zuerst, die Nummer nur als Rueckfall. Die Nummern sind
        nicht stabil: ohne angemeldete Sitzung zaehlt ALSA weniger
        Geraete auf als mit einer, weil die Eintraege fuer PipeWire und
        Pulse wegfallen und alles dahinter rutscht. Im Systemdienst haette
        dieselbe Nummer damit ein anderes Geraet bezeichnet als am Pult.
        Beim Umstecken eines USB-Mikrofons verschieben sich auch die
        vorderen Nummern.

        Gibt (nummer, vermisst) zurueck. Ist vermisst gesetzt, wurde das
        Geraet nicht gefunden und es darf KEINES geoeffnet werden -- auch
        nicht das unter der alten Nummer. Genau dieser Rueckfall hat einen
        Rechner nach dem Hochfahren still auf den Onboard-Eingang gelegt:
        der Strom ging auf, der Thread lief, kein Fehler nirgends, und es
        kam nie Ton. Lieber gar kein Geraet und eine Meldung am Pult.

        Der Kanal gehoert zum Schluessel. Ein Geraet, das heute weniger
        Kanaele aufzaehlt als beim Speichern, traegt den gesuchten Kanal
        nicht mehr -- dann gilt es als vermisst, statt still auf den
        linken zurueckzufallen. "Rechter Kanal" waere auf einem
        Monogeraet eine Auskunft, die nicht stimmt."""
        if not name:
            return nummer, ""

        def passt(g):
            """Hat dieses Geraet den gesuchten Kanal noch?"""
            return kanal < g["kanaele"]

        def vermisst_name():
            """Wie das Geraet in der gelben Zeile am Pult heisst."""
            if kanaele > 1:
                return f"{name} ({zustandsdatei.kanalname(kanal, kanaele)})"
            return name
        try:
            liste = geraete_liste()
        except Exception:
            return nummer, ""
        for g in liste:
            if g["name"] == name and passt(g):
                if g["nummer"] != nummer:
                    print(f"Tonquelle \"{name}\" hat jetzt Nummer "
                          f"{g['nummer']} statt {nummer}.")
                return g["nummer"], ""
        # Zweiter Versuch ohne den Kartenindex. ALSA schreibt ihn in den
        # Namen -- "Auna Mic CM900: USB Audio (hw:4,0)" --, und er
        # verschiebt sich, sobald ein anderes USB-Audiogeraet fehlt oder
        # dazukommt. Ohne diesen Vergleich wartete der Server auf ein
        # Mikrofon, das angesteckt danebensteht, nur unter hw:2 statt hw:4.
        kern = Tonquelle._namenskern(name)
        for g in liste:
            if Tonquelle._namenskern(g["name"]) == kern and passt(g):
                print(f"Tonquelle \"{kern}\" gefunden als \"{g['name']}\", "
                      f"Nummer {g['nummer']}.")
                return g["nummer"], ""
        # Der Name ist da, nur der Kanal nicht: das ist der Fall, der
        # sonst am schwersten zu deuten waere. Er gehoert ins Journal,
        # sonst sucht jemand nach einem Mikrofon, das angesteckt ist.
        if kanaele > 1 and any(Tonquelle._namenskern(g["name"]) == kern
                               for g in liste):
            print(f"Tonquelle \"{kern}\" ist da, hat aber keinen "
                  f"{zustandsdatei.kanalname(kanal, kanaele)}-Kanal mehr. "
                  f"Es wird kein anderer genommen.")
        return None, vermisst_name()

    @staticmethod
    def _namenskern(name):
        """Der Geraetename ohne den ALSA-Kartenindex.

        "Auna Mic CM900: USB Audio (hw:4,0)" -> "Auna Mic CM900: USB Audio".
        Zwei baugleiche Mikrofone am selben Rechner waeren danach nicht
        mehr zu unterscheiden; dann gewinnt das erste. Eine Gemeinde hat
        ein Mikrofon, und ein falsch geratenes ist immer noch besser als
        eines, auf das ewig gewartet wird, obwohl es angesteckt ist."""
        return name.split(" (hw:")[0].strip()

    @staticmethod
    def _vorgabegeraet():
        """Die Nummer, die sounddevice ohne Angabe nehmen wuerde.

        Aufgeloest statt als None weitergereicht: am Pult soll stehen,
        welches Geraet tatsaechlich aufnimmt. "Vorgabegeraet" ist keine
        Auskunft, wenn die Frage lautet, warum kein Ton kommt."""
        sd = ton.holen()
        if sd is None:
            return None
        try:
            nummer = sd.default.device[0]
            return int(nummer) if nummer is not None and nummer >= 0 else None
        except Exception:
            return None

    # ---- innen, immer unter dem Schloss ----
    def _starten(self, geraet, kanal=0, kanaele=1):
        if geraet is None:
            geraet = self._vorgabegeraet()
        # Wie bei mikrofon_thread: nur ein hinterer Kanal zwingt zum
        # mehrkanaligen Oeffnen. Kanal 0 wird mono geprueft und mono
        # aufgemacht, genau wie vor der Kanalwahl.
        pruef_kanaele = kanaele if kanal > 0 else 1
        gewaehlt = rate_waehlen(geraet, self.wunschrate, pruef_kanaele)
        if gewaehlt is None:
            return False, ("Keine der ueblichen Aufnahmeraten funktioniert "
                           "mit diesem Geraet.")
        rate, blockgroesse = gewaehlt
        stoppen = threading.Event()
        offen = threading.Event()
        melder = {"fehler": ""}
        thread = threading.Thread(
            target=mikrofon_thread,
            args=(self.lauf, geraet, self.segmentierer, stoppen, rate,
                  blockgroesse),
            kwargs={"offen": offen, "melder": melder,
                    "kanal": kanal, "kanaele": kanaele},
            daemon=True)
        thread.start()
        # Auf den offenen Datenstrom warten. Ohne das meldete das Pult
        # Erfolg, waehrend im Terminal der Fehler steht und kein Ton kommt.
        offen.wait(self.WARTEN)
        if not offen.is_set():
            stoppen.set()
            return False, (melder["fehler"]
                           or "Das Geraet liess sich nicht oeffnen.")
        self.geraet, self.rate, self.blockgroesse = geraet, rate, blockgroesse
        self.kanal, self.kanaele = kanal, kanaele
        self.geraet_name = self._name_zu(geraet)
        self._thread, self._stoppen = thread, stoppen
        self.fehler = ""
        # Der Zeitstempel des alten Stroms darf den neuen nicht decken:
        # ungeloescht haette der Aufseher ihn fuer lebendig gehalten, bis
        # die Frist ein zweites Mal abgelaufen waere.
        self.lauf.audio_quelle = None
        self.offen_seit = time.time()
        return True, ""

    def _anhalten(self):
        """Schliesst den Datenstrom. Gibt zurueck, ob er wirklich zu ist.

        False heisst: der Thread haengt nach der Frist noch im Treiber,
        der Strom ist also NICHT geschlossen und das Geraet weiter
        belegt. Frueher ging diese Auskunft verloren -- self._thread
        wurde bedingungslos geleert, und der Server hielt ein Geraet fuer
        frei, das noch offen war.

        Fuer den Livebetrieb aendert das nichts: wer danach ein anderes
        Geraet aufmacht, kommt damit durch. Fuer den Reihum-Scan ist es
        der Unterschied zwischen "naechster Kanal" und einem EBUSY auf
        einem Geraet, das wir selbst noch festhalten. Der Scan fragt
        deshalb frei() und laesst einen Takt aus, statt draufzuoeffnen."""
        if self._stoppen is not None:
            self._stoppen.set()
        zu = True
        if self._thread is not None:
            # Der Thread prueft alle 0,2 s; danach schliesst der
            # Kontextmanager den Datenstrom. Wer laenger braucht, haengt im
            # Treiber, und darauf wartet das Pult nicht.
            self._thread.join(timeout=3.0)
            if self._thread.is_alive():
                zu = False
                # Nicht vergessen, sondern merken: der Thread schliesst
                # den Strom, wenn der Treiber ihn freigibt. Bis dahin
                # muss frei() ihn sehen koennen.
                self._haengt.append(self._thread)
                print(f"Tonstrom haengt noch im Treiber "
                      f"({self.geraet_name or self.geraet}). Das Geraet "
                      f"bleibt belegt, bis er sich loest.")
        self._thread = None
        self._stoppen = None
        self.offen_seit = None
        return zu

    def frei(self):
        """Ist gerade kein Datenstrom von uns offen?

        Sieht auch nach den haengenden Threads: ein Strom, der beim
        Anhalten die Frist gerissen hat, schliesst sich spaeter von
        selbst, und danach ist das Geraet wieder zu haben."""
        self._haengt = [t for t in self._haengt if t.is_alive()]
        return self._thread is None and not self._haengt


# ================================================================
# Kanalscan: welcher Eingang fuehrt Ton?
# ================================================================

def kanal_schluessel(name, kanal, kanaele):
    """Der stabile Schluessel einer Zeile.

    Nicht die Geraetenummer: die verschiebt sich beim Umstecken und
    zaehlt im Systemdienst anders als in der angemeldeten Sitzung.
    Anzeigename, Kanalzahl und Kanalindex zusammen bezeichnen den
    Eingang so, wie ein Mensch ihn wiedererkennt."""
    return f"{name}␟{kanaele}␟{kanal}"


# Ab wie vielen Kanaelen ein Eintrag nicht mehr als Karte gilt.
#
# Gemessen auf dem Entwicklungsrechner: die ALSA-Umsetzer melden
# "default", "pipewire", "sysdefault", "lavrate", "samplerate" und
# "speexrate" mit je 128 Eingangskanaelen, "pulse" mit 32. Das sind
# keine Buchsen, sondern die Obergrenze, die ein Umsetzer eben
# entgegennimmt -- er reicht ohnehin an dieselbe Karte weiter. Ohne
# Deckel ergab die Liste 826 Zeilen und ein Umlauf haette elf Minuten
# gedauert; mit Deckel sind es rund 40.
#
# 16 und nicht kleiner, weil es Tonkarten mit acht und mehr echten
# Eingaengen gibt. Wer mehr meldet, bekommt eine einzige Zeile auf
# Kanal 0 -- das ist der Kanal, den ein Umsetzer ohne weitere Angabe
# auch liefern wuerde.
KANAELE_HOECHSTENS = 16

# ALSA-Umsetzer, die nicht aufgemacht werden duerfen.
#
# Das sind keine Eingaenge, sondern Glieder in ALSAs Umrechnungskette:
# sie wandeln Abtastrate oder Kanalzahl eines Stromes, der schon da ist.
# Als Aufnahmequelle ergeben sie nichts, und einer von ihnen ist
# gefaehrlich: "upmix" stuerzt beim Aufnehmen im Plugin selbst ab.
#
#   libasound_module_pcm_upmix.so -> snd_pcm_area_copy -> Segfault
#
# Gemessen auf dem Entwicklungsrechner, reproduzierbar beim ersten
# Block. Ein Segfault laesst sich nicht abfangen -- kein try, kein
# except --, er nimmt den ganzen Serverprozess mit. Waehrend eines
# Gottesdienstes waere das der Ausfall der Uebersetzung, ausgeloest
# davon, dass jemand die Geraeteliste aufgeklappt hat.
#
# Bewusst eine Sperrliste und keine Erlaubnisliste: eine Erlaubnisliste
# verschwiege auf einem ungewoehnlichen Rechner eine echte Karte, und
# dann fehlt genau das Mikrofon, das gesucht wird. Hier stehen nur
# Namen, die per Bauart kein Mikrofon sein koennen.
#
# "pulse", "pipewire", "default" und "sysdefault" stehen mit Absicht
# NICHT hier: das sind die ueblichen Wege zur Karte und oft der
# einzige, der funktioniert, wenn der hw-Eingang belegt ist.
UMSETZER = {"upmix", "vdownmix", "lavrate", "samplerate", "speexrate",
            "speex"}


def kanaele_aufzaehlen():
    """Jeder Eingangskanal als eigene Zeile.

    Einheit ist der Kanal und nicht das Geraet: ein Stereogeraet haengt
    am Mischpult regelmaessig so, dass links die Summe liegt und rechts
    das Predigtmikrofon. Wer nur Geraete sieht, waehlt dann die Summe
    und wundert sich ueber die Uebersetzung der Gemeinde.

    Duplikate derselben Karte ueber verschiedene Schnittstellen fallen
    zusammen. geraete_liste() ist bereits nach Rang sortiert, der erste
    Treffer ist also der vertraeglichste -- unter Windows MME statt
    WDM-KS. Unterschieden wird nach Namenskern und Kanalzahl: zwei
    baugleiche Mikrofone waeren danach eines, und das ist derselbe
    Handel, den _namenskern ohnehin schon eingeht."""
    zeilen = []
    gesehen = set()
    # Echte Karten zuerst messen. Unter ALSA steht der Kartenindex im
    # Namen -- "(hw:4,0)" --, und genau die sind gesucht; die Umsetzer
    # dahinter reichen nur weiter. Unter Windows trifft das Muster auf
    # nichts zu, dort bleibt die Reihenfolge wie sie war.
    karten = sorted(geraete_liste(),
                    key=lambda g: 0 if "(hw:" in g["name"] else 1)
    for g in karten:
        if g["name"].strip().lower() in UMSETZER:
            continue
        kanaele = max(1, int(g["kanaele"]))
        marke = (Tonquelle._namenskern(g["name"]), kanaele)
        if marke in gesehen:
            continue
        gesehen.add(marke)
        # Ein Umsetzer, der 128 Kanaele meldet, hat keine 128 Buchsen.
        zeigen = 1 if kanaele > KANAELE_HOECHSTENS else kanaele
        for kanal in range(zeigen):
            zeilen.append({
                "schluessel": kanal_schluessel(g["name"], kanal, kanaele),
                "nummer": g["nummer"],
                "name": g["name"],
                "kanal": kanal,
                "kanaele": kanaele,
                "kanalname": zustandsdatei.kanalname(kanal, kanaele),
                "empfohlen": g["empfohlen"],
            })
    return zeilen


# Aufnahmeraten, die der Reihe nach probiert werden. Dieselbe Liste wie
# rate_waehlen: 48000 zuerst, weil es genau das Dreifache von 16000 ist
# und sich exakt dezimieren laesst. Der Helfer bekommt sie uebergeben,
# statt sie ein zweites Mal hinzuschreiben -- die Entscheidung, was
# bevorzugt wird, gehoert hierher.
HELFER_RATEN = (48000, 32000, 16000, 44100)

# Wie lange auf den Helfer gewartet wird, ueber das Messfenster hinaus.
# Deckt Prozessstart (gemessen rund 220 ms) und ein zaehes Geraet ab.
# Wer laenger braucht, haengt im Treiber; dann wird er abgeraeumt und
# die Zeile sagt "nicht lesbar".
HELFER_ZUSCHLAG = 6.0


def kanal_holen(geraet, kanal, kanaele, dauer, wunschrate=None):
    """Laesst den Helfer einen Kanal aufmachen und zurueckreichen.

    Gibt (pegel, audio, fehler). audio ist 16-kHz-Mono, durch auf_16k --
    dieselbe Funktion wie die Livepipeline. Der Helfer reicht bewusst
    Rohdaten zurueck und rechnet nicht selbst herunter: zwei
    Umrechnungen nebeneinander liefen auseinander, und die
    Sprachpruefung hoerte etwas anderes als der Server nachher.

    Der ganze Zweck des eigenen Prozesses ist, dass ein Treiber ihn
    mitnehmen darf. "upmix" tut das -- Segfault in
    libasound_module_pcm_upmix.so, reproduzierbar beim ersten Block.
    Stirbt der Helfer, kommt hier ein Fehler heraus, die Zeile im Pult
    bleibt mit "nicht lesbar" stehen und der Scan geht weiter. Im
    Serverprozess waere an derselben Stelle der Gottesdienst zu Ende
    gewesen.

    Whisper bleibt im Hauptprozess: das Modell liegt dort geladen und
    darf nicht je Geraet neu geladen werden. Der Helfer liefert Ton,
    kein Urteil."""
    helfer = Path(__file__).resolve().parent / "tonhelfer.py"
    if not helfer.exists():
        return None, None, "tonhelfer.py fehlt"
    # --rate gilt auch hier. Wer eine Rate erzwingt, will sie auch beim
    # Scan erzwungen sehen: eine Karte, die nur bei 44100 laeuft, zeigte
    # sonst in der Liste einen Pegel, den sie im Betrieb nie liefert.
    raten = (wunschrate,) if wunschrate else HELFER_RATEN
    befehl = [sys.executable, str(helfer), str(geraet), str(kanal),
              str(kanaele), f"{dauer:.3f}",
              ",".join(str(r) for r in raten)]
    try:
        fertig = subprocess.run(
            befehl, capture_output=True,
            timeout=dauer + HELFER_ZUSCHLAG)
    except subprocess.TimeoutExpired:
        # subprocess.run raeumt den Prozess bei Zeitueberschreitung selbst
        # ab. Ein Geraet, das nicht aufgeht und nicht zurueckkommt, darf
        # die Reihe nicht anhalten.
        return None, None, "Zeitueberschreitung"
    except Exception as e:
        return None, None, str(e)[:120]

    if fertig.returncode != 0:
        # Negativer Rueckgabewert heisst unter POSIX: durch Signal
        # beendet. -11 ist SIGSEGV, und genau dafuer steht der Helfer
        # hier. Das gehoert ins Journal, nicht nur an die Zeile: es ist
        # ein Treiberfehler auf diesem Rechner und kein Bedienfehler.
        if fertig.returncode < 0:
            print(f"Tonhelfer bei Geraet {geraet}, Kanal {kanal} durch "
                  f"Signal {-fertig.returncode} beendet. Das Geraet wird "
                  f"uebersprungen, der Scan laeuft weiter.")
            return None, None, "Treiber abgestuerzt"
        return None, None, f"Helfer endete mit {fertig.returncode}"

    kopf, _, rest = fertig.stdout.partition(b"\n")
    try:
        auskunft = json.loads(kopf.decode("utf-8"))
    except Exception:
        return None, None, "Helfer ohne brauchbare Antwort"
    if not auskunft.get("ok"):
        return None, None, str(auskunft.get("fehler", "unbekannt"))[:120]

    roh = np.frombuffer(rest, dtype=np.float32)
    if not len(roh):
        return auskunft["pegel"], None, ""
    audio = auf_16k(np.ascontiguousarray(roh), auskunft["rate"])
    return auskunft["pegel"], audio, ""


class Testton:
    """Eine WAV-Datei anstelle der Soundkarte.

    Damit laesst sich die Kanaltrennung ohne Mischpult pruefen: eine
    Stereodatei mit Sprache links und Stille rechts muss genau eine
    Zeile mit Pegel ergeben und bei der Sprachpruefung genau ein
    "sprache". Der Oeffnungspfad wird damit NICHT geprueft -- dafuer
    braucht es ein echtes Geraet.

    Stdlib-wave und kein neues Paket: es geht um PCM-WAV, und das kann
    Python selbst. av liegt zwar im Ordner, liefert ueber decode_audio
    aber Mono -- und genau die Kanaltrennung soll hier geprueft werden.
    """

    def __init__(self, pfad):
        self.pfad = Path(pfad)
        with wave.open(str(self.pfad), "rb") as w:
            self.kanaele = w.getnchannels()
            self.rate = w.getframerate()
            breite = w.getsampwidth()
            roh = w.readframes(w.getnframes())
        if breite == 2:
            daten = np.frombuffer(roh, dtype="<i2").astype(np.float32) / 32768.0
        elif breite == 4:
            daten = (np.frombuffer(roh, dtype="<i4").astype(np.float32)
                     / 2147483648.0)
        elif breite == 1:
            # 8-Bit-WAV ist vorzeichenlos, 128 ist die Null.
            daten = (np.frombuffer(roh, dtype="u1").astype(np.float32)
                     - 128.0) / 128.0
        else:
            raise ValueError(f"{breite * 8} Bit je Abtastwert kann ich nicht "
                             f"lesen. Erwartet werden 8, 16 oder 32 Bit PCM.")
        self.spuren = daten.reshape(-1, self.kanaele)
        self.name = f"Testton: {self.pfad.name}"
        # Die Leseposition folgt der Wanduhr, nicht der Zahl der
        # Lesevorgaenge.
        #
        # Das ist der Unterschied zwischen einer Datei und einem Geraet,
        # und er ist der Grund, warum die Probe sonst luegt: ein
        # Zaehler, den jede Messung weiterrueckt, laeuft bei vier
        # Kanaelen vierfach zu schnell durch die Datei, und zwei Kanaele
        # zeigen nie denselben Augenblick. Am Mischpult liegt auf allen
        # Kanaelen dieselbe Sekunde an; wer L misst und eine Sekunde
        # spaeter R, hoert bei R eine Sekunde spaeter -- genau das.
        self._beginn = time.time()
        self._schloss = threading.Lock()

    def zeilen(self):
        return [{
            "schluessel": kanal_schluessel(self.name, k, self.kanaele),
            "nummer": -1,
            "name": self.name,
            "kanal": k,
            "kanaele": self.kanaele,
            "kanalname": zustandsdatei.kanalname(k, self.kanaele),
            "empfohlen": True,
        } for k in range(self.kanaele)]

    def _schneiden(self, kanal, dauer):
        laenge = max(1, int(dauer * self.rate))
        verstrichen = time.time() - self._beginn
        anfang = int(verstrichen * self.rate) % len(self.spuren)
        # Umlaufend lesen: die Datei faengt von vorne an, statt in Stille
        # auszulaufen. Sonst zeigte eine kurze Probe nach einer Minute
        # nur noch "still", und die Pruefung haette nichts mehr zu
        # hoeren.
        i = np.arange(anfang, anfang + laenge) % len(self.spuren)
        return self.spuren[i, kanal]

    def messen(self, kanal, fenster):
        spur = self._schneiden(kanal, fenster).astype(np.float64)
        # Das Fenster wird abgewartet, obwohl die Daten schon dastehen.
        # Sonst liefe die Probe um Groessenordnungen schneller als der
        # Ernstfall, und genau das Verhalten, das geprueft werden soll
        # -- wie sich eine Liste von dreissig Zeilen anfuehlt, die
        # reihum einzeln aktualisiert wird --, waere nicht zu sehen.
        threading.Event().wait(fenster)
        return float(np.sqrt(np.mean(spur ** 2))), ""

    def aufnehmen(self, kanal, dauer):
        spur = self._schneiden(kanal, dauer)
        threading.Event().wait(dauer)
        return auf_16k(np.ascontiguousarray(spur, dtype=np.float32),
                       self.rate), ""


class Kanalscan:
    """Misst reihum jeden Eingangskanal und sagt, wo Ton anliegt.

    Im Serverprozess und in genau einem Thread. Kein zweiter Prozess:
    ALSA-hw-Geraete sind exklusiv, ein fremder Prozess bekaeme EBUSY auf
    genau dem Geraet, das der Server selbst haelt, und ob PipeWire das
    abfaengt, haengt an der Installation vor Ort. Sequenziell und nicht
    parallel, aus demselben Grund: nie zwei Geraete gleichzeitig offen.

    Gelaufen wird nur, solange die Uebersetzung steht. Waehrend einer
    Predigt wird nichts gemessen und nichts geoeffnet -- der aktive
    Kanal zeigt seinen normalen Pegel weiter, alle anderen Zeilen
    stehen still da. Ein Messfenster von 800 ms auf dem Predigtmikrofon
    waere ein Loch in der Uebersetzung, und dafuer gibt es keinen Grund,
    der eine Gemeinde interessiert.

    Die Zeilen bleiben ueber die Runden stehen, auch fehlerhafte. Eine
    Zeile, die bei EBUSY verschwindet und beim naechsten Umlauf
    wiederkommt, laesst die Liste springen, und der Techniker klickt
    daneben."""

    # Messfenster je Kanal. Kurz genug, dass ein Umlauf ueber ein
    # Dutzend Eingaenge im zweistelligen Sekundenbereich bleibt, lang
    # genug fuer ein paar Silben.
    FENSTER = 0.8
    # Verschnaufen zwischen zwei Geraeten. Manche USB-Karten geben den
    # Descriptor nicht sofort frei, und der naechste Griff faellt dann
    # unnoetig auf EBUSY.
    RUHE = 0.12
    # Ab hier gilt ein Kanal als "fuehrt Ton". Derselbe Wert, den das
    # Pult schon als Hoerbarkeitsgrenze benutzt -- unterhalb davon ist
    # es Rauschen der Vorverstaerkung, nicht Signal.
    RAUSCHGRENZE = 0.0015

    def __init__(self, lauf, tonquelle, testton=None, wunschrate=None):
        self.lauf = lauf
        self.tonquelle = tonquelle
        self.testton = testton
        self.wunschrate = wunschrate
        self._zeilen = {}
        self._reihenfolge = []
        self._schloss = threading.Lock()
        self._thread = None
        self._ende = threading.Event()
        # Haelt An und Aus auseinander. Wer die Liste hastig zu- und
        # wieder aufklappt, loest sonst ein Aufraeumen aus, das erst
        # fertig wird, wenn die naechste Reihe schon laeuft -- und
        # zurueckholen() naehme ihr dann mitten im Umlauf das Geraet weg.
        self._wechsel = threading.Lock()
        # Wird gesetzt, solange die Sprachpruefung laeuft. Der Scan
        # macht dann nichts auf, statt um dasselbe Geraet zu streiten.
        self._pause = threading.Event()
        # Das eigentliche Geraeteschloss. Messung und Sprachpruefung
        # halten es abwechselnd; damit ist ausgeschlossen, dass zwei
        # Stroeme gleichzeitig offen sind. _pause ist nur die
        # Hoeflichkeit davor, dieses Schloss ist die Zusicherung.
        self._geraet_schloss = threading.Lock()
        self._pruef_thread = None
        self._pruef_ende = threading.Event()
        self._pruef_schloss = threading.Lock()
        self._pruef_jetzt = ""
        self.hinweis = ""

    @property
    def laeuft(self):
        # _ende zaehlt mit: das Aufraeumen laeuft in einem eigenen
        # Thread und darf ein paar Sekunden brauchen. Bis dahin ist der
        # Scan am Pult schon aus, sonst zeigte die Liste noch "misst",
        # waehrend niemand mehr hinsieht.
        if self._ende.is_set():
            return False
        return self._thread is not None and self._thread.is_alive()

    # ---- an und aus --------------------------------------------------
    def starten(self):
        """Beim Oeffnen des Abschnitts "Tonquelle".

        Nicht dauerhaft im Hintergrund: der Scan macht fremde Geraete
        auf, und das gehoert an eine Stelle, an der jemand hinsieht."""
        with self._wechsel:
            if self._thread is not None and self._thread.is_alive():
                self._ende.clear()
                return True
            self._ende.clear()
            self._thread = threading.Thread(target=self._schleife,
                                            daemon=True)
            self._thread.start()
            return True

    def stoppen(self, warten=True):
        """Beim Schliessen des Abschnitts.

        Holt die eingestellte Quelle zurueck. Ohne das bliebe der Server
        nach einem Blick in die Liste ohne Ton da -- der Scan hat das
        Geraet ja zuletzt einem anderen Kanal ueberlassen."""
        self._ende.set()
        with self._wechsel:
            # Unter dem Schloss noch einmal nachsehen: wer in der
            # Zwischenzeit wieder aufgeklappt hat, hat _ende geloescht,
            # und dann gibt es hier nichts mehr aufzuraeumen.
            if not self._ende.is_set():
                return
            thread = self._thread
            if warten and thread is not None:
                # Grosszuegiger als das Messfenster: der letzte Strom
                # muss zugehen, bevor die eigentliche Quelle aufmacht.
                thread.join(timeout=self.FENSTER + 3.0)
            self._thread = None
            if self.tonquelle is not None:
                gelungen, lage, grund = self.tonquelle.zurueckholen()
                if not gelungen and lage == "kein_ton":
                    print(f"Tonquelle nach dem Scan nicht zurueck: {grund}")

    # ---- was das Pult sieht ------------------------------------------
    def lage(self):
        """Alle Zeilen, in fester Reihenfolge, plus der Gesamtzustand."""
        with self._schloss:
            zeilen = [dict(self._zeilen[s]) for s in self._reihenfolge
                      if s in self._zeilen]
        laeuft_uebersetzung = bool(self.lauf.laeuft)
        aktiv = self._aktiver_schluessel()
        for z in zeilen:
            z["aktiv"] = (z["schluessel"] == aktiv)
            # Waehrend der Uebersetzung wird nicht gemessen. Das ist kein
            # Fehler, und die Zeile soll auch nicht wie einer aussehen --
            # sie ist nur gerade nicht zu beurteilen.
            z["ruht"] = laeuft_uebersetzung and not z["aktiv"]
        if laeuft_uebersetzung and aktiv:
            # Der aktive Kanal zeigt den normalen Betriebspegel weiter,
            # aus derselben Quelle wie der Balken oben: gemessen wird er
            # ohnehin laufend, nur eben vom Segmentierer.
            for z in zeilen:
                if z["aktiv"]:
                    z["pegel"] = round(self.lauf.segmentierer.pegel_jetzt, 5)
                    z["gemessen"] = time.time()
                    z["fehler"] = ""
        return {
            "laeuft": self.laeuft,
            "uebersetzung": laeuft_uebersetzung,
            "pruefung": self.pruefung_laeuft,
            "pruefung_jetzt": self._pruef_jetzt,
            "testton": self.testton.name if self.testton else "",
            "rauschgrenze": self.RAUSCHGRENZE,
            "vermisst": (self.tonquelle.wartet_auf
                         if self.tonquelle is not None else ""),
            "hinweis": self.hinweis,
            "zeilen": zeilen,
        }

    def _aktiver_schluessel(self):
        if self.testton is not None or self.tonquelle is None:
            return ""
        if not self.tonquelle.geraet_name:
            return ""
        return kanal_schluessel(self.tonquelle.geraet_name,
                                self.tonquelle.kanal,
                                self.tonquelle.kanaele)

    def kandidaten(self):
        """Die Kanaele, die ueberhaupt Pegel gezeigt haben.

        Nur die kommen in die Sprachpruefung. Whisper auf einen Eingang
        loszulassen, an dem nachweislich nichts anliegt, kostet nur
        Zeit: das Ergebnis steht vorher fest."""
        with self._schloss:
            return [dict(self._zeilen[s]) for s in self._reihenfolge
                    if s in self._zeilen
                    and (self._zeilen[s].get("pegel") or 0) > self.RAUSCHGRENZE]

    # ---- die Reihe ---------------------------------------------------
    def _eintragen(self, zeile):
        """Legt eine Zeile an oder frischt ihre Stammdaten auf.

        Der gemessene Wert bleibt stehen: die Nummer eines Geraets kann
        sich zwischen zwei Umlaeufen verschieben, sein letzter Pegel
        wird davon nicht falsch."""
        with self._schloss:
            vorhanden = self._zeilen.get(zeile["schluessel"])
            if vorhanden is None:
                self._zeilen[zeile["schluessel"]] = dict(
                    zeile, pegel=None, gemessen=None, fehler="",
                    sprache=None)
                self._reihenfolge.append(zeile["schluessel"])
            else:
                vorhanden.update({k: zeile[k] for k in
                                  ("nummer", "name", "kanalname", "empfohlen")})

    def _ergebnis(self, schluessel, pegel, fehler):
        with self._schloss:
            z = self._zeilen.get(schluessel)
            if z is None:
                return
            z["gemessen"] = time.time()
            z["fehler"] = fehler
            if pegel is not None:
                z["pegel"] = round(pegel, 5)

    def sprachurteil_setzen(self, schluessel, urteil):
        with self._schloss:
            z = self._zeilen.get(schluessel)
            if z is not None:
                z["sprache"] = urteil

    def _schleife(self):
        """Round-Robin, bis jemand den Abschnitt zuklappt.

        Faengt alles ab. Ein Treiber, der beim Aufmachen wirft, darf die
        Reihe nicht beenden -- die naechste Karte ist womoeglich genau
        die gesuchte."""
        # Das Geraet abgeben, bevor irgendetwas anderes aufgemacht wird.
        # Der Aufseher ruht dann ebenfalls; ohne das riefe er mitten in
        # die Messreihe hinein "Tonstrom tot" und oeffnete die alte
        # Quelle wieder.
        if self.tonquelle is not None and self.testton is None:
            if not self.tonquelle.abgeben():
                self.hinweis = ("Der bisherige Tonstrom haengt noch im "
                                "Treiber. Die Messung faengt an, sobald "
                                "er zu ist.")
        while not self._ende.is_set():
            try:
                self._umlauf()
            except Exception as e:
                print(f"Kanalscan: {type(e).__name__}: {str(e)[:150]}")
                self._ende.wait(1.0)

    def _umlauf(self):
        zeilen = (self.testton.zeilen() if self.testton is not None
                  else kanaele_aufzaehlen())
        for z in zeilen:
            self._eintragen(z)

        for z in zeilen:
            if self._ende.is_set():
                return
            # Waehrend einer Uebersetzung wird nichts geoeffnet. Nicht
            # abbrechen, sondern warten: der Techniker klappt die Liste
            # oft auf, drueckt Start und laesst sie offen stehen.
            if self.lauf.laeuft:
                self._ende.wait(1.0)
                return
            # Die Sprachpruefung hat Vorrang: sie haelt gerade selbst ein
            # Geraet offen.
            if self._pause.is_set():
                self._ende.wait(0.3)
                return
            self._messen(z)
            self._ende.wait(self.RUHE)

    def _messen(self, z):
        # Unter demselben Schloss wie die Sprachpruefung: nie zwei
        # Stroeme gleichzeitig, auch nicht fuer einen Wimpernschlag.
        # Das gilt auch ueber Prozessgrenzen hinweg -- zwei Helfer
        # gleichzeitig waeren zwei offene Geraete.
        with self._geraet_schloss:
            if self.testton is not None:
                pegel, fehler = self.testton.messen(z["kanal"], self.FENSTER)
            else:
                pegel, _, fehler = kanal_holen(z["nummer"], z["kanal"],
                                               z["kanaele"], self.FENSTER,
                                               self.wunschrate)
        if fehler:
            # Die Zeile bleibt stehen und der Scan laeuft weiter. Ein
            # belegtes Geraet ist die Regel, nicht die Ausnahme: der
            # Rechner spielt womoeglich gerade Musik ueber dieselbe
            # Karte, und der naechste Umlauf trifft es wieder frei.
            self._ergebnis(z["schluessel"], None, "nicht lesbar")
        else:
            self._ergebnis(z["schluessel"], pegel, "")

    # ---- Stufe 2: liegt wirklich Sprache an? -------------------------
    # Wie lange je Kandidat aufgenommen wird. Kuerzer als eineinhalb
    # Sekunden schneidet Whisper regelmaessig mitten im ersten Wort ab
    # und meldet dann Unsinn; laenger kostet nur Wartezeit, weil hier
    # niemand einen Satz mitlesen will, sondern nur wissen muss, ob
    # ueberhaupt geredet wird.
    PRUEF_DAUER = 1.8
    # Wie viele Fenster je Kandidat gehoert werden, und zwar alle
    # nacheinander auf demselben Kanal.
    #
    # Eins reichte nicht. Gemessen an Orgel, Chor und Gemeindegesang
    # bekam ein Fenster von fuenf das Urteil "sprache", mit einem frei
    # erfundenen frommen Satz darunter, den keine Phrasenliste kennt.
    # Echte Rede dagegen war in zwei von zwei Fenstern Rede. Ein
    # Halluzinat wiederholt sich nicht.
    #
    # Zwei und nicht grundsaetzlich drei, weil es Wartezeit am Pult ist:
    # geprueft werden nur Kanaele mit Pegel aus Stufe 1, in der Praxis
    # zwei bis vier. Das sind rund neun Sekunden.
    PRUEF_FENSTER = 2

    # Ein drittes Fenster, aber nur wenn die ersten beiden uneins sind.
    #
    # Zwei Fenster, die uebereinstimmen muessen, sind streng gegen Musik
    # -- und ebenso streng gegen einen Prediger, der zwischen den
    # Fenstern Luft holt. Der zweite Fall ist der teurere: wer den
    # richtigen Kanal als "kein Sprechen erkannt" gemeldet bekommt,
    # waehlt das falsche Geraet und merkt es erst im Gottesdienst. Ein
    # Halluzinat auf der Orgel dagegen faellt beim Lesen des Textes auf,
    # der daneben steht.
    #
    # Bei Uneinigkeit entscheidet deshalb ein drittes Fenster, zwei von
    # dreien gewinnen. Das kostet nur im Zweifelsfall: stimmen die
    # ersten beiden ueberein -- der Normalfall -- bleibt es bei zwei.
    STICHENTSCHEID = 3
    # Wieviel Text am Pult stehenbleibt. Genug, um das Gesprochene
    # wiederzuerkennen, zu wenig, um die Zeile zu sprengen.
    TEXT_ZEICHEN = 40

    # Wie viele Woerter ein Fenster mindestens hergeben muss, damit es
    # als Sprechen gilt.
    #
    # Gemessen: 1,8 Sekunden zusammenhaengende deutsche Rede ergeben
    # vier bis sechs Woerter. Auf Orgel und Gesang antwortete Whisper
    # dagegen mit "Musik" oder "Amen." -- ein Wort fuer ein volles,
    # lautes Fenster. Das ist keine Rede, das ist ein Etikett, das das
    # Modell auf Klang klebt. Und gerade "Amen." wiegt schwer: im
    # Gottesdienst sieht es nach dem richtigen Kanal aus.
    #
    # Nur hier und NICHT in der Livepipeline: dort ist ein kurzer
    # Einwurf ein echter Satz, der uebersetzt gehoert. Hier ist die
    # Frage eine andere -- es wird ausdruecklich hineingesprochen, und
    # wer das tut, sagt mehr als ein Wort.
    MINDESTWOERTER = 3

    def pruefung_starten(self):
        """Knopf "Sprache pruefen".

        Gibt (gestartet, grund). Nicht von selbst beim Oeffnen der
        Liste: die Pruefung haelt jeden Kandidaten noch einmal auf und
        laesst Whisper darueber laufen. Das ist nichts, was im
        Hintergrund passieren soll, waehrend jemand nur nachsieht,
        welches Kabel steckt."""
        with self._pruef_schloss:
            if self._pruef_thread is not None and self._pruef_thread.is_alive():
                return False, "laeuft_schon"
            if self.lauf.laeuft:
                # Waehrend einer Uebersetzung wird nichts aufgemacht.
                return False, "uebersetzung"
            kandidaten = self.kandidaten()
            if not kandidaten:
                return False, "keine_kandidaten"
            self._pruef_ende.clear()
            self._pruef_thread = threading.Thread(
                target=self._pruef_schleife, args=(kandidaten,), daemon=True)
            self._pruef_thread.start()
            return True, ""

    def pruefung_abbrechen(self):
        """Knopf "Abbrechen".

        Setzt nur das Signal und wartet nicht: der laufende Kandidat
        wird zu Ende gehoert -- das dauert keine zwei Sekunden --, und
        danach hoert die Reihe auf. Am Pult haengen darf das nicht."""
        self._pruef_ende.set()

    @property
    def pruefung_laeuft(self):
        return (self._pruef_thread is not None
                and self._pruef_thread.is_alive()
                and not self._pruef_ende.is_set())

    def _pruef_schleife(self, kandidaten):
        """Geht die Kandidaten der Reihe nach durch.

        Nur Kanaele, die in Stufe 1 ueberhaupt Pegel gezeigt haben:
        Whisper auf einen Eingang loszulassen, an dem nachweislich
        nichts anliegt, kostet Zeit, deren Ergebnis vorher feststeht.

        Der Scan ruht solange. Beide messen ueber dasselbe Geraet, und
        zwei Stroeme gleichzeitig ist genau das, was hier nie passieren
        darf."""
        self._pause.set()
        try:
            for z in kandidaten:
                if self._pruef_ende.is_set() or self._ende.is_set():
                    break
                if self.lauf.laeuft:
                    # Jemand hat mitten in der Reihe auf Start gedrueckt.
                    # Dann gehoert das Geraet der Predigt.
                    break
                self.pruefung_zeigen(z["schluessel"])
                self._einen_pruefen(z)
        except Exception as e:
            print(f"Sprachpruefung: {type(e).__name__}: {str(e)[:150]}")
        finally:
            self.pruefung_zeigen("")
            self._pause.clear()

    def pruefung_zeigen(self, schluessel):
        """Welcher Kanal gerade abgehoert wird -- fuer das Pult."""
        with self._schloss:
            self._pruef_jetzt = schluessel

    def _einen_pruefen(self, z):
        """Hoert denselben Kanal mehrfach ab und fasst zusammen."""
        fenster = []
        while len(fenster) < self.STICHENTSCHEID:
            if self._pruef_ende.is_set() or self._ende.is_set():
                # Mitten im Kandidaten abgebrochen. Kein halbes Urteil
                # hinschreiben: "ein Fenster von zwei" ist keine
                # Auskunft, sondern eine, die man falsch liest.
                return
            erg = self._ein_fenster(z)
            fenster.append(erg)
            # Weiterhoeren lohnt nur, wenn ueberhaupt etwas ankam. Ein
            # stummer oder belegter Kanal wird vom naechsten Fenster
            # nicht gespraechiger.
            if erg["grund"] in ("kein Pegel", "nicht lesbar",
                                "kein Modell geladen"):
                break
            if len(fenster) >= self.PRUEF_FENSTER and self._einig(fenster):
                # Die ersten beiden sind sich einig. Ein drittes Fenster
                # koennte daran nichts mehr aendern und waere nur
                # Wartezeit am Pult.
                break
        if fenster:
            self.sprachurteil_setzen(z["schluessel"],
                                     self._zusammenfassen(fenster))

    @staticmethod
    def _einig(fenster):
        """Sagen alle bisherigen Fenster dasselbe ueber Sprache?"""
        return len({f["urteil"] == "sprache" for f in fenster}) == 1

    def _zusammenfassen(self, fenster):
        """Aus mehreren Fenstern ein Urteil. Die Mehrheit entscheidet.

        Zwei Fenster, die uebereinstimmen, reichen. Sind sie uneins, hat
        ein drittes den Ausschlag gegeben und es zaehlen zwei von
        dreien.

        Warum ueberhaupt mehrfach: auf Orgel sagte das Modell in einem
        von fuenf Fenstern "sprache" und erfand dazu einen frommen Satz,
        auf echter Rede in zwei von zwei. Ein Halluzinat wiederholt sich
        nicht, ein Prediger hoert nach 1,8 Sekunden nicht auf. Das ist
        der einzige gemessene Weg, Musik von Rede zu trennen, nachdem
        der Text es nicht kann.

        Warum Mehrheit und nicht Einstimmigkeit: Einstimmigkeit ist
        ebenso streng gegen einen Prediger, der zwischen zwei Fenstern
        Luft holt. Und dieser Fehler ist der teurere -- wer den
        richtigen Kanal als "kein Sprechen erkannt" gemeldet bekommt,
        waehlt das falsche Geraet und merkt es erst im Gottesdienst. Ein
        Halluzinat auf der Orgel faellt dagegen beim Lesen des Textes
        auf, der daneben steht."""
        dafuer = [f for f in fenster if f["urteil"] == "sprache"]
        dagegen = [f for f in fenster if f["urteil"] != "sprache"]
        sprache = len(dafuer) > len(dagegen)

        # Das Fenster, dessen Rohwerte angezeigt werden, gehoert zur
        # Mehrheit: sonst stuende am Pult ein Grund neben Zahlen, die
        # ihn nicht belegen.
        entscheidend = (dafuer[0] if sprache
                        else (dagegen[0] if dagegen else fenster[0]))

        ergebnis = dict(entscheidend)
        ergebnis["fenster"] = [
            {k: f[k] for k in ("urteil", "grund", "rms",
                               "no_speech_prob", "avg_logprob")}
            for f in fenster]
        ergebnis["zeit"] = time.time()
        # Wie knapp es war. Am Pult steht das nur bei Uneinigkeit, aber
        # im Ergebnis steht es immer -- zum Nachziehen nach der Beta.
        ergebnis["stimmen"] = [len(dafuer), len(fenster)]

        if sprache:
            ergebnis["urteil"] = "sprache"
            ergebnis["text"] = entscheidend["text"]
            # Zwei von drei ist ein Urteil, aber ein knappes, und das
            # soll man sehen, bevor man das Geraet uebernimmt.
            ergebnis["grund"] = ("" if not dagegen
                                 else f"{len(dafuer)} von {len(fenster)} Fenstern")
            return ergebnis

        ergebnis["text"] = ""
        if dafuer:
            # Genau der Orgelfall. Er gehoert benannt und nicht unter
            # "keine Sprache" versteckt: beim naechsten Mal will jemand
            # wissen, warum hier einmal ein Satz stand.
            ergebnis["urteil"] = "ton_ohne_sprache"
            ergebnis["grund"] = (f"nur in {len(dafuer)} von "
                                 f"{len(fenster)} Fenstern, sonst "
                                 + (dagegen[0]["grund"] or "nichts"))
        return ergebnis

    def _ein_fenster(self, z):
        """Ein Abschnitt aufnehmen und beurteilen."""
        # Das Geraeteschloss: der Scan haelt es waehrend seiner Messung,
        # hier wird es fuer die Aufnahme gehalten. Nie zwei Stroeme.
        with self._geraet_schloss:
            if self.testton is not None:
                audio, fehler = self.testton.aufnehmen(z["kanal"],
                                                       self.PRUEF_DAUER)
            else:
                # Derselbe Helfer wie in Stufe 1, nur laenger. Er gibt
                # Ton zurueck, kein Urteil -- Whisper liegt im
                # Hauptprozess geladen und bleibt dort.
                _, audio, fehler = kanal_holen(
                    z["nummer"], z["kanal"], z["kanaele"], self.PRUEF_DAUER,
                    self.wunschrate)

        leer = {"text": "", "rms": None, "no_speech_prob": None,
                "avg_logprob": None, "zeit": time.time()}
        if fehler or audio is None or not len(audio):
            return dict(leer, urteil="nichts", grund="nicht lesbar")

        # Der Pegel der Aufnahme selbst, nicht der aus Stufe 1: zwischen
        # Messung und Pruefung koennen Sekunden liegen, und in denen hat
        # der Prediger womoeglich aufgehoert zu reden.
        rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))

        # Erste Stufe des Gates: der Pegel. Darunter braucht Whisper gar
        # nicht erst zu laufen -- es gibt nichts zu hoeren.
        if rms <= self.RAUSCHGRENZE:
            return dict(leer, urteil="nichts", grund="kein Pegel",
                        rms=round(rms, 5))

        werk = getattr(self.lauf, "werk", None)
        if werk is None or getattr(werk, "whisper", None) is None:
            return dict(leer, urteil="ton_ohne_sprache",
                        grund="kein Modell geladen", rms=round(rms, 5))

        mass = werk.sprache_messen(audio)
        urteil, grund = self._urteilen(werk, mass)
        return {
            "urteil": urteil,
            "text": mass["text"][:self.TEXT_ZEICHEN],
            "grund": grund,
            "rms": round(rms, 5),
            "no_speech_prob": round(mass["no_speech_prob"], 4),
            "avg_logprob": round(mass["avg_logprob"], 4),
            "zeit": time.time(),
        }

    @staticmethod
    def _urteilen(werk, mass):
        """Das Gate, in dieser Reihenfolge.

        Pegel hat der Aufrufer schon geprueft. Hier: no_speech_prob
        (bei diesem Modell tot, siehe KEINE_SPRACHE_AB), avg_logprob,
        dann die Leerlaufphrasen. Ein Treffer der
        Phrasenliste gilt als KEINE Sprache -- das ist dieselbe Liste,
        die im Livebetrieb erfundene Abspaenne abfaengt.

        Nach den Messungen an KEINE_SPRACHE_AB ist sie hier der
        tragende Schritt: auf Rauschen antwortet large-v3-turbo mit
        "Vielen Dank." bei no_speech_prob 0.0. Ohne die Phrasenliste
        saehe das am Pult nach einem gefundenen Predigtkanal aus.

        Eine Luecke bleibt und laesst sich mit Text nicht schliessen.
        Auf Orgel antwortete das Modell einmal mit "Vertraue und
        glaube, es hilft, es heilt die goettliche Kraft!" -- zehn
        Woerter, sauberes Deutsch, fromm. Keine Regel hier
        unterscheidet das von einem Prediger. Das Pult darf deshalb
        nicht versprechen, dass "sprache" den richtigen Kanal
        beweist; es ist ein starker Hinweis, mehr nicht."""
        if mass["no_speech_prob"] > werk.KEINE_SPRACHE_AB:
            return "ton_ohne_sprache", "no_speech_prob"
        if mass["avg_logprob"] < werk.LOGPROB_MINDESTENS:
            return "ton_ohne_sprache", "avg_logprob"
        text = mass["text"]
        if not text:
            return "ton_ohne_sprache", "kein Text"
        if werk.ERFUNDEN.match(text):
            return "ton_ohne_sprache", "Leerlaufphrase"
        woerter = text.lower().split()
        if len(woerter) >= 4 and len(set(woerter)) <= 2:
            return "ton_ohne_sprache", "Schleife im Dekoder"
        if len(woerter) < Kanalscan.MINDESTWOERTER:
            return "ton_ohne_sprache", "zu wenig Worte"
        return "sprache", ""


# ================================================================
# Web
# ================================================================

def app_bauen(lauf, basis, port=8000, tonquelle=None, kanalscan=None):
    a_port = [port]
    from fastapi import (FastAPI, File, Form, Request, UploadFile, WebSocket,
                         WebSocketDisconnect)
    from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                                   PlainTextResponse, RedirectResponse,
                                   Response)
    from html import escape as html_escape

    @asynccontextmanager
    async def lebenszyklus(app):
        aufgabe = asyncio.create_task(lauf.verarbeiten())
        yield
        aufgabe.cancel()
        # Der Aufseher ist ein Daemon-Thread und wuerde auch so mit dem
        # Prozess enden. Ihm hier Bescheid zu sagen erspart beim Neustart
        # des Dienstes den halben Takt, in dem er noch einmal nachsieht.
        if tonquelle is not None:
            tonquelle.beenden()
        # Der Scan haelt womoeglich gerade ein fremdes Geraet offen.
        # Ohne Warten: beim Herunterfahren wird niemand mehr bedient,
        # und der Strom geht mit dem Prozess ohnehin zu.
        if kanalscan is not None and kanalscan.laeuft:
            kanalscan.stoppen(warten=False)

    app = FastAPI(title=f"Devarenu {config.VERSION}", lifespan=lebenszyklus)

    # Die Adressen, mit denen Handys fragen, ob sie Internet haben.
    # Zuerst eingehaengt, damit sie nicht von einer allgemeineren Route
    # verdeckt werden -- und weil keine davon umleiten darf.
    #
    # Sie stoeren nichts: /pult, /qr und die Zuhoererseite haben andere
    # Pfade. Ohne den Umbau fragt sie ohnehin niemand, dann liegen sie
    # nur da.
    app.include_router(netzpruefung.router)

    # ------------------------------------------------ Pult-Passwort
    # Freiwillig. Ist keines gesetzt -- die Vorgabe --, aendert sich
    # gar nichts: die Wache winkt jeden durch, und es kostet einen
    # stat auf zustand.json.
    wache = pultschutz.Wache(zustandsdatei.DATEI)

    @app.middleware("http")
    async def pult_schuetzen(request, weiter):
        pfad = request.url.path
        host = request.client.host if request.client else ""
        ja, grund = wache.darf(
            pfad, host,
            request.cookies.get(pultschutz.KEKS),
            request.query_params.get("schluessel"))
        if ja:
            return await weiter(request)
        # 401 und nicht 403: der Aufrufer KANN etwas tun, naemlich sich
        # anmelden. Eine Seite statt eines nackten Fehlers, damit am
        # Handy nicht "Unauthorized" steht und sonst nichts.
        return HTMLResponse(
            ANMELDUNG.format(ziel=html_escape(request.url.path), fehler=""),
            status_code=401)

    @app.post("/pult-anmeldung")
    async def pult_anmelden(request: Request):
        daten = await request.form()
        passwort = str(daten.get("passwort") or "")
        ziel = str(daten.get("ziel") or "/pult")
        # Kein offener Umleitungspunkt: nur Wege auf diesem Server.
        if not ziel.startswith("/") or ziel.startswith("//"):
            ziel = "/pult"
        if not wache.gesetzt:
            return RedirectResponse(ziel, status_code=303)
        if not pultschutz.stimmt(passwort, wache.hash):
            host = request.client.host if request.client else "?"
            print(warnung(f"Pult: Anmeldung abgelehnt (von {host})."))
            return HTMLResponse(
                ANMELDUNG.format(ziel=html_escape(ziel),
                                 fehler=ANMELDUNG_FEHLER),
                status_code=401)
        antwort = RedirectResponse(ziel, status_code=303)
        antwort.set_cookie(
            pultschutz.KEKS, pultschutz.ausweis(wache.hash),
            max_age=pultschutz.KEKS_DAUER, httponly=True, samesite="lax",
            path="/")
        return antwort

    @app.post("/api/pult-passwort")
    async def pult_passwort(daten: dict):
        """Setzen, aendern oder loeschen -- vom Pult aus.

        Ein leeres Passwort loescht es. Wer schon angemeldet ist, darf
        das: er sitzt entweder am Rechner oder hat sich vorher
        ausgewiesen. Ein zweites Mal danach zu fragen hiesse, es
        zweimal zu tippen."""
        neu_wort = str(daten.get("passwort") or "")
        stand = zustandsdatei.laden()[0]
        if neu_wort and len(neu_wort) < 4:
            return JSONResponse({"grund": "zu_kurz"}, status_code=400)
        stand["pult_passwort"] = pultschutz.hashen(neu_wort) if neu_wort else ""
        if not zustandsdatei.speichern(stand):
            return JSONResponse({"grund": "nicht_schreibbar"}, status_code=500)
        print(f"Pult-Passwort {'gesetzt' if neu_wort else 'geloescht'}.")
        # Der Keks dieses Browsers wird mit dem neuen Hash ungueltig --
        # also gleich einen neuen mitgeben, sonst sperrt sich aus, wer
        # es gerade erst gesetzt hat.
        antwort = JSONResponse({"gesetzt": bool(neu_wort)})
        if neu_wort:
            antwort.set_cookie(
                pultschutz.KEKS, pultschutz.ausweis(stand["pult_passwort"]),
                max_age=pultschutz.KEKS_DAUER, httponly=True,
                samesite="lax", path="/")
        else:
            antwort.delete_cookie(pultschutz.KEKS, path="/")
        return antwort

    client = basis / "client.html"

    def schwelle_sichern():
        """Haelt die Mindestlautstaerke in zustand.json nach.

        Zusammen mit dem Zeitpunkt: eine Schwelle vom letzten Jahr ist
        etwas anderes als eine von heute frueh, und wer sie im Herbst
        wiederfindet, soll sehen, ob sie noch zum Raum passt. Wird die
        Schwelle wieder freigegeben, faellt auch der Zeitpunkt weg -- es
        gibt dann keine Messung mehr, die gilt."""
        seg = lauf.segmentierer
        fest = seg.feste_schwelle is not None
        lauf.zustand["schwelle"] = {
            "wert": round(seg.feste_schwelle, 5) if fest else None,
            "gemessen": zustandsdatei.jetzt() if fest else None}
        zustandsdatei.speichern(lauf.zustand)

    @app.get("/")
    def wurzel():
        if not client.exists():
            return HTMLResponse(f"<h1>client.html fehlt</h1><p>{client}</p>",
                                status_code=500)
        return FileResponse(client, media_type="text/html; charset=utf-8")

    @app.get("/spende.svg")
    def spende_qr():
        """Bank-QR nach europaeischer Norm, den jede Banking-App liest.

        Der Betrag ist Vorgabe und in der App aenderbar; ohne Betrag
        laesst die Norm keinen Datensatz zu."""
        spende = getattr(config, "SPENDE", {}) or {}
        if not spende.get("iban"):
            return Response(status_code=404)
        try:
            import segno
            # Der Datensatz von Hand, weil die Hilfsfunktion von segno
            # einen Betrag erzwingt. Die Norm laesst ihn frei, sodass hier
            # beides moeglich ist: mit Vorgabe, wenn ein Betrag in der
            # Konfiguration steht, sonst ohne.
            betrag = spende.get("betrag")
            zeilen = [
                "BCD", "002", "1", "SCT",
                (spende.get("bic") or "").replace(" ", ""),
                spende.get("name", "")[:70],
                spende["iban"].replace(" ", ""),
                f"EUR{float(betrag):.2f}" if betrag else "",
                "", "",                  # Zweckschluessel, Referenz
                spende.get("zweck", "")[:140],
            ]
            while zeilen and not zeilen[-1]:
                zeilen.pop()
            code = segno.make("\n".join(zeilen), error="m")
            puffer = io.BytesIO()
            code.save(puffer, kind="svg", scale=6, border=2,
                      dark="#141f52", light=None)
            return Response(puffer.getvalue(), media_type="image/svg+xml")
        except Exception as e:
            print(f"Spenden-QR nicht erzeugt: {str(e)[:100]}")
            return Response(status_code=404)

    @app.get("/favicon.ico")
    def favicon():
        # Sonst steht in jeder Browserkonsole ein 404. Das Logo tut es.
        d = basis / "logo.png"
        if d.exists():
            return FileResponse(d, media_type="image/png")
        return Response(status_code=404)

    @app.get("/logo.png")
    def logo():
        d = basis / "logo.png"
        if d.exists():
            return FileResponse(d, media_type="image/png")
        # Ohne Logo laeuft alles weiter; die Seiten blenden die Marke dann
        # selbst aus, statt ein kaputtes Bild zu zeigen.
        return Response(status_code=404)

    @app.get("/ton/{sprache}/{nummer}")
    def ton(sprache: str, nummer: int):
        datei = lauf.toene.get((sprache, nummer))
        if not datei or not Path(datei).exists():
            return JSONResponse({"fehler": "kein Ton"}, status_code=404)
        return FileResponse(datei, media_type="audio/wav",
                            headers={"Cache-Control": "no-store"})

    @app.websocket("/strom")
    async def strom(ws: WebSocket):
        sprache = ws.query_params.get("sprache", "")
        if sprache not in lauf.sprachen:
            await ws.close(code=1008)
            return
        await ws.accept()
        if ws.client is not None:
            netzpruefung.beobachten(ws.client.host)
        await lauf.anmelden(ws, sprache)
        try:
            while True:
                await ws.receive_text()
        except (WebSocketDisconnect, Exception):
            pass
        finally:
            lauf.abmelden(ws, sprache)

    @app.get("/api/geraete")
    def geraete():
        """Die Aufnahmegeraete, dieselbe Liste wie server.py --geraete.

        Bewusst kein async: das Abfragen geht ueber den Treiber und kann
        haengen. Als gewoehnliche Funktion laeuft es im Threadpool, statt
        die Ereignisschleife und damit alle Zuhoerer anzuhalten."""
        # lage ist das Wort fuers Pult, einzelheit die Meldung des
        # Treibers. Frueher stand hier ein fertiger deutscher Satz, und
        # der blieb auch unter englischer Oberflaeche deutsch.
        if tonquelle is None:
            return {"aktiv": False, "aktuell": None, "liste": [],
                    "lage": "nicht_lokal", "einzelheit": ""}
        # Ist kein Strom offen, vorher neu aufzaehlen: sonst fehlt in der
        # Liste genau das Mikrofon, das gerade eingesteckt wurde, und der
        # Techniker kann es nicht waehlen. Bei offenem Strom NICHT --
        # _terminate() risse ihn mit, ohne etwas zu melden, und aus einem
        # Blick in die Einrichtung wuerde ein Tonausfall.
        tonquelle.auffrischen()
        try:
            liste = geraete_liste()
        except Exception as e:
            return {"aktiv": True, "aktuell": tonquelle.geraet, "liste": [],
                    "lage": "liste_unlesbar", "einzelheit": str(e)[:120]}
        lage = tonquelle.lage() or {}
        return {"aktiv": True, "aktuell": tonquelle.geraet,
                "name": lage.get("name") or tonquelle.geraet_name,
                "kanal": tonquelle.kanal, "kanaele": tonquelle.kanaele,
                "rate": tonquelle.rate, "laeuft": tonquelle.laeuft,
                "liste": liste,
                "lage": lage.get("lage", ""),
                "einzelheit": lage.get("einzelheit", "")}

    @app.post("/api/geraet")
    def geraet_waehlen(daten: dict):
        """Stellt im Betrieb auf ein anderes Aufnahmegeraet um.

        Auch hier kein async, aus demselben Grund: der Wechsel schliesst
        einen Datenstrom und oeffnet einen anderen, und das dauert."""
        if tonquelle is None:
            return JSONResponse({"lage": "nicht_lokal"}, status_code=400)
        try:
            nummer = int(daten.get("nummer"))
        except (TypeError, ValueError):
            return JSONResponse({"lage": "keine_nummer"}, status_code=400)
        # Ohne Kanalangabe der erste: das ist, was jede Fassung vor der
        # Kanalwahl gemeint hat, und was ein Monogeraet ohnehin hergibt.
        try:
            kanal = int(daten.get("kanal") or 0)
            kanaele = int(daten.get("kanaele") or 1)
        except (TypeError, ValueError):
            return JSONResponse({"lage": "kein_kanal"}, status_code=400)
        if kanal < 0 or kanal >= kanaele:
            return JSONResponse({"lage": "kein_kanal"}, status_code=400)
        # Vorher merken: ob die Schwelle zu verwerfen ist, haengt daran,
        # ob sich wirklich etwas geaendert hat.
        war = (tonquelle.geraet, tonquelle.kanal, tonquelle.kanaele)
        gelungen, lage, einzelheit = tonquelle.wechseln(nummer, kanal, kanaele)
        if gelungen:
            lauf.zustand["geraet"] = tonquelle.geraet
            lauf.zustand["geraet_name"] = tonquelle.geraet_name
            lauf.zustand["geraet_kanal"] = tonquelle.kanal
            lauf.zustand["geraet_kanaele"] = tonquelle.kanaele
            # Die eingemessene Schwelle gehoerte zur alten Quelle. Ein
            # anderes Mikrofon, eine andere Vorverstaerkung, ein anderer
            # Kanal -- der Wert passt nicht mehr, und stehenbleiben waere
            # schlimmer als fehlen: er wuerde still zu viel verschlucken
            # oder zu viel durchlassen. Also mitlaufend, bis neu
            # eingemessen ist.
            #
            # Nur bei einer echten Aenderung. Wer dieselbe Quelle und
            # denselben Kanal noch einmal waehlt -- ein Doppelklick am
            # Pult, ein wiederholter Aufruf -- verliert sonst eine
            # Einmessung, die weiterhin gilt.
            seg = lauf.segmentierer
            anders = war != (tonquelle.geraet, tonquelle.kanal,
                             tonquelle.kanaele)
            if anders and (lauf.zustand["schwelle"]["wert"] is not None
                           or seg.feste_schwelle is not None):
                seg.feste_schwelle = None
                lauf.zustand["schwelle"] = {"wert": None, "gemessen": None}
                print("Schwelle verworfen: sie galt der alten Tonquelle. "
                      "Nach dem Start einmal neu einmessen.")
            zustandsdatei.speichern(lauf.zustand)
            wo = (f", {zustandsdatei.kanalname(tonquelle.kanal, tonquelle.kanaele)}"
                  if tonquelle.kanaele > 1 else "")
            print(f"Tonquelle: {tonquelle.geraet_name or nummer} "
                  f"(Nr. {tonquelle.geraet}{wo}), {tonquelle.rate} Hz")
        else:
            print(f"Geraetewechsel gescheitert ({lage}): {einzelheit}")
        return {"gelungen": gelungen, "lage": lage, "einzelheit": einzelheit,
                "aktuell": tonquelle.geraet, "name": tonquelle.geraet_name,
                "kanal": tonquelle.kanal, "kanaele": tonquelle.kanaele,
                "rate": tonquelle.rate, "laeuft": tonquelle.laeuft}

    @app.get("/api/tonscan")
    def tonscan():
        """Was der Kanalscan gerade weiss.

        Kein async, wie bei /api/geraete: die Auskunft selbst ist zwar
        billig, aber sie steht unter demselben Schloss wie der messende
        Thread, und der haelt es, waehrend ein Treiber aufmacht."""
        if kanalscan is None:
            return {"aktiv": False, "laeuft": False, "zeilen": []}
        return dict(kanalscan.lage(), aktiv=True)

    @app.post("/api/tonscan")
    def tonscan_schalten(daten: dict):
        """Scan an und aus, gebunden an den Abschnitt "Tonquelle".

        Kein Dauerlauf im Hintergrund: der Scan macht fremde Geraete auf,
        und das soll nur geschehen, solange jemand hinsieht."""
        if kanalscan is None:
            return JSONResponse({"lage": "nicht_lokal"}, status_code=400)
        if daten.get("an"):
            kanalscan.starten()
        else:
            # Ohne Warten: das Zuklappen der Liste soll nicht bis zu vier
            # Sekunden am Pult haengen. Der Thread raeumt selbst auf und
            # holt die eingestellte Quelle zurueck.
            threading.Thread(target=kanalscan.stoppen, daemon=True).start()
        return {"laeuft": kanalscan.laeuft}

    @app.post("/api/sprachpruefung")
    def sprachpruefung(daten: dict):
        """Stufe 2 an und aus.

        Kein async: das Starten faellt zwar sofort zurueck, aber die
        Auskunft darueber steht unter demselben Schloss wie der
        pruefende Thread."""
        if kanalscan is None:
            return JSONResponse({"lage": "nicht_lokal"}, status_code=400)
        if not daten.get("an"):
            kanalscan.pruefung_abbrechen()
            return {"laeuft": False, "lage": ""}
        gestartet, grund = kanalscan.pruefung_starten()
        return {"laeuft": kanalscan.pruefung_laeuft, "lage": grund}

    # Nur angelegt, wenn der Schalter steht. Das ist der Unterschied
    # zwischen "antwortet 404" und "prueft erst und lehnt dann ab": ohne
    # Schalter gibt es die Route nicht, es wird kein Rumpf gelesen und
    # nichts angefasst. Im Gottesdienst ist das der Normalzustand.
    if getattr(config, "MESSUNG_WIEDERGABE", False):
        @app.post("/api/messung/wiedergabe")
        async def messung_wiedergabe(request: Request):
            """Nimmt entgegen, was ein Handy ueber seine Wiedergabe weiss.

            Der Weg ueber den Server statt ueber localStorage: die Daten
            vom Handy zu holen braeuchte sonst USB-Debugging oder einen
            Mac mit Safari. Im Gemeindesaal ist beides unbrauchbar."""
            if lauf.messung is None:
                # Wiedergabe an, Messung aus -- dann gibt es nichts, wo
                # die Zeilen hinkoennten.
                return JSONResponse({"lage": "keine_messung"}, status_code=404)
            hoechstens = getattr(config, "MESSUNG_RUMPF_MAX", 65536)
            # Erst die Ankuendigung, dann der Rumpf: was zu gross angesagt
            # ist, wird gar nicht erst eingelesen.
            angesagt = request.headers.get("content-length")
            if angesagt and angesagt.isdigit() and int(angesagt) > hoechstens:
                return JSONResponse({"lage": "zu_gross"}, status_code=413)
            rumpf = await request.body()
            if len(rumpf) > hoechstens:
                return JSONResponse({"lage": "zu_gross"}, status_code=413)
            try:
                daten = json.loads(rumpf.decode("utf-8"))
            except Exception:
                return JSONResponse({"lage": "unlesbar"}, status_code=400)
            zeilen = daten.get("zeilen") if isinstance(daten, dict) else None
            if not isinstance(zeilen, list):
                return JSONResponse({"lage": "unlesbar"}, status_code=400)
            return {"genommen": lauf.messung.wiedergabe(zeilen[:500])}

    def glossar_sprachen():
        """Fuer welche Sprachen hat das geladene Glossar eine Spalte.

        Die Quellsprache zaehlt mit: fuer sie gibt es die Begriffe im
        Original, sie steht in der Spalte "de"."""
        g = getattr(lauf.werk, "glossar", None)
        return set(getattr(g, "sprachen", ())) | {lauf.quelle}

    def glossar_nachricht(sp: str) -> dict:
        """Der Briefkasteneintrag fuer eine ungeprueufte Sprache.

        Zwei Texte, weil es zwei verschiedene Zustaende sind. Ein
        Glossar, das niemand gegengelesen hat, ist etwas anderes als gar
        keines -- im ersten Fall stehen die Begriffe fest und koennten
        falsch sein, im zweiten stehen sie gar nicht fest.

        Und beide Male dieselbe Bitte: wer das aendern kann, ist ein
        Mensch aus der Gemeinde, kein Rechner."""
        name = config.SPRACHNAMEN.get(sp, sp)
        name_en = getattr(config, "SPRACHNAMEN_EN", {}).get(sp, name)
        hat_glossar = sp in glossar_sprachen()
        if hat_glossar:
            de = (f"{name} ist eingeschaltet. Die Fachbegriffe für diese "
                  f"Sprache hat noch kein Muttersprachler gesehen.")
            en = (f"{name_en} is switched on. The technical terms for this "
                  f"language have not yet been seen by a native speaker.")
        else:
            de = (f"{name} ist eingeschaltet. Für diese Sprache gibt es "
                  f"noch kein Fachwortverzeichnis. Begriffe wie Sabbat, "
                  f"Gemeinde oder Vereinigung werden wörtlich übersetzt.")
            en = (f"{name_en} is switched on. There is no glossary for this "
                  f"language yet. Terms like Sabbath, church or "
                  f"conference are translated literally.")
        bitte_de = (" Gesucht wird jemand, der " + name + " als "
                    "Muttersprache spricht und Deutsch oder Englisch "
                    "versteht — rund eine Stunde Zeit für eine Liste mit "
                    "93 Begriffen. Meldung an " + config.RUECKMELDUNG_MAIL + ". Bis "
                    "dahin ist die Sprache experimentell.")
        bitte_en = (" We are looking for someone who speaks " + name_en +
                    " as a native language and understands German or "
                    "English — about one hour for a list of 93 terms. "
                    "Please write to " + config.RUECKMELDUNG_MAIL + ". Until then "
                    "the language is experimental.")
        return {"text": de + bitte_de, "text_en": en + bitte_en,
                "sprache": sp, "zeit": time.strftime("%H:%M"),
                # Als Systemhinweis erkennbar und nicht als Zuschrift
                # aus dem Saal: anderes Zeichen, eigener Absender.
                "art": "system", "absender": "Devarenu",
                # Anders als eine Zuschrift bleibt sie stehen, bis sie
                # einmal geoeffnet wurde.
                "gelesen": False,
                "glossar": hat_glossar}

    def systemnachricht():
        """Was am Rechner nicht stimmt, als eine Nachricht fuers Pult.

        Der Server aendert NICHTS. Er sieht beim Start nach und legt
        das Ergebnis in den Briefkasten -- wie eine Zuschrift aus dem
        Saal, nur als Systemhinweis gekennzeichnet.

        Quittiert wird ueber einen Fingerabdruck der Befundmenge, nicht
        ueber ein blosses Ja: wer einmal gelesen hat, wird nicht jeden
        Sonntag wieder gefragt -- aber sobald ein Punkt dazukommt oder
        wegfaellt, ist es eine neue Lage und die Nachricht kommt
        wieder."""
        try:
            befunde = systemcheck.pruefen()
        except Exception as e:
            print(f"Systemcheck fehlgeschlagen ({str(e)[:90]}).")
            return None
        if not befunde:
            return None
        marke = systemcheck.kennung(befunde)
        if lauf.zustand.get("systemcheck_quittiert") == marke:
            return None

        schwer = [b for b in befunde if b.schwere == systemcheck.FEHLT]
        kopf_de = (f"{len(schwer)} Punkt(e) halten den Betrieb auf"
                   if schwer else "Ein paar Punkte stehen noch offen")
        kopf_en = (f"{len(schwer)} item(s) block operation"
                   if schwer else "A few items are still open")
        zeilen_de = [f"• {b.was} → {b.tun}" for b in befunde]
        zeilen_en = [f"• {b.was_en} → {b.tun_en}" for b in befunde]
        return {
            "text": kopf_de + ":\n" + "\n".join(zeilen_de),
            "text_en": kopf_en + ":\n" + "\n".join(zeilen_en),
            "sprache": "", "zeit": time.strftime("%H:%M"),
            "art": "system", "absender": "Devarenu",
            "gelesen": False, "systemcheck": marke,
        }

    @app.get("/api/sprachen")
    def sprachen():
        """Welche Sprachen dieser Server anbietet.

        Der Client baut seine Auswahl daraus, statt eine feste Liste zu
        haben. Damit genuegt ein Eintrag in der Konfiguration, um eine
        Sprache zu ergaenzen, und niemand muss die Seite anfassen."""
        vorhanden = getattr(lauf.werk, "stimmen", {})
        # Nicht nur die geladenen: eine Stimme, die daliegt, wird beim
        # Umstellen nachgeladen und zaehlt deshalb als vorhanden.
        auf_platte = ({} if getattr(lauf.werk, "nur_text", False)
                      else stimmen_finden(list(config.SPRACHNAMEN),
                                          quelle=lauf.quelle))
        spende = getattr(config, "SPENDE", {}) or {}
        return {
            "rueckmeldung": getattr(config, "RUECKMELDUNG_MAIL", ""),
            # Stellt dieser Rechner das Netz selbst? Dann hat das WLAN
            # kein Internet, und die Seite sagt, dass die mobilen Daten
            # aus muessen. Sonst waere der Satz falsch.
            "saalnetz": netzzustand.ist_router(),
            "spende": ({"name": spende.get("name", ""),
                        "iban": spende.get("iban", ""),
                        "bic": spende.get("bic", ""),
                        "bank": spende.get("bank", ""),
                        "zweck": spende.get("zweck", "")}
                       if spende.get("iban") else None),
            "quelle": lauf.quelle,
            "ziele": lauf.ziele,
            "liste": [{
                "code": sp,
                "name": config.SPRACHNAMEN.get(sp, sp),
                "original": sp == lauf.quelle,
                "ton": sp == lauf.quelle or sp in vorhanden,
                # Geprueft heisst: ein Muttersprachler hat das
                # Fachwortverzeichnis durchgesehen.
                "geprueft": sp in getattr(config, "GEPRUEFT", set()),
                # Davon getrennt: gibt es ueberhaupt eine Spalte im
                # Glossar? Das sind zwei verschiedene Dinge, und bisher
                # sahen sie gleich aus. Ohne Spalte laufen Begriffe wie
                # Sabbat oder Vereinigung woertlich durch die Maschine.
                "glossar": sp in glossar_sprachen(),
            } for sp in lauf.sprachen],
            # Sprachen ohne Stimme sind nicht ausgeschlossen: sie laufen
            # als reiner Untertitel.
            #
            # Gemeldet wird, was auf der PLATTE liegt, nicht was gerade
            # geladen ist. Wer hier waehlt, bekommt die Stimme beim
            # Umstellen nachgeladen -- und soll vorher sehen, ob es eine
            # gibt. Sonst stuende an einer Sprache "nur Text", obwohl
            # sie eine Stimme hat.
            "moeglich": [{
                "code": sp,
                "name": name,
                "stimme": (sp in vorhanden or sp == lauf.quelle
                           or sp in auf_platte),
                "geprueft": sp in getattr(config, "GEPRUEFT", set()),
                "glossar": sp in glossar_sprachen(),
            } for sp, name in sorted(config.SPRACHNAMEN.items(),
                                     key=lambda x: x[1])],
        }

    @app.post("/api/sprachwahl")
    async def sprachwahl(daten: dict):
        """Stellt Quell- und Zielsprachen um.

        Alle Stimmen und Glossareintraege liegen auf der Platte; hier wird
        nur ausgewaehlt, was tatsaechlich mitlaeuft. Damit bleibt die
        Rechenzeit dort, wo eine Gemeinde sie braucht, und dasselbe Geraet
        bedient je nach Einstellung einen deutschen oder einen
        anderssprachigen Gottesdienst."""
        entfallen = lauf.sprachen_setzen(daten.get("quelle"),
                                         daten.get("ziele"))
        for sp in entfallen:
            for ws in list(lauf.hoerer.get(sp, ())):
                try:
                    await ws.close(code=1000)
                except Exception:
                    pass
            lauf.hoerer.pop(sp, None)
        print(f"Sprachen: {lauf.quelle} -> {', '.join(lauf.ziele)}")

        # Wer eine ungeprueufte Sprache einschaltet, soll wissen, worauf
        # er sich einlaesst -- aber nicht durch ein Fenster, das
        # aufspringt. Am Pult darf im Gottesdienst nichts aufpoppen.
        # Also derselbe Briefkasten wie fuer Zuschriften aus dem Saal,
        # nur als Systemhinweis gekennzeichnet.
        #
        # Und nur einmal je Sprache: wer es gelesen hat, bekommt danach
        # die kleine Zeile an der Sprache. Sonst klickt der Techniker es
        # beim dritten Mal ungelesen weg, und dann traegt es nichts mehr.
        quittiert = set(lauf.zustand.get("glossar_quittiert") or [])
        offen = [sp for sp in lauf.ziele
                 if sp not in getattr(config, "GEPRUEFT", set())
                 and sp != lauf.quelle
                 and sp not in quittiert
                 and not any(n.get("sprache") == sp and
                             n.get("art") == "system"
                             for n in lauf.nachrichten)]
        for sp in offen:
            lauf.nachrichten.append(glossar_nachricht(sp))
            print(f"Hinweis ins Pult gelegt: {sp} ist ungeprueft.")

        lauf.zustand["quelle"] = lauf.quelle
        lauf.zustand["ziele"] = list(lauf.ziele)
        zustandsdatei.speichern(lauf.zustand)
        return {"quelle": lauf.quelle, "ziele": lauf.ziele,
                "getrennt": sorted(entfallen)}

    @app.post("/api/nachricht")
    async def nachricht(daten: dict):
        text = (daten.get("text") or "").strip()
        if not text:
            return JSONResponse({"fehler": "leer"}, status_code=400)
        # Kurz halten: das Feld ist fuer einen Satz gedacht, nicht fuer
        # einen Brief, und alles landet ungefiltert vor dem Techniker.
        eintrag = {"text": text[:200],
                   "sprache": (daten.get("sprache") or "")[:5],
                   "zeit": time.strftime("%H:%M"),
                   # Ausdruecklich, nicht durch Abwesenheit: das Pult
                   # unterscheidet danach, und "kein Feld" waere eine
                   # Annahme, die beim naechsten Umbau kippt.
                   "art": "saal"}
        lauf.nachrichten.append(eintrag)
        print(f"Nachricht aus dem Saal ({eintrag['sprache'] or '?'}): "
              f"{schutz(eintrag['text'], 200)}")
        return {"angekommen": True}

    @app.post("/api/nachrichten/leeren")
    async def nachrichten_leeren():
        """Raeumt den Briefkasten -- bis auf Ungelesenes vom System.

        Zuschriften aus dem Saal sind fluechtig: gelesen, erledigt, weg.
        Ein Systemhinweis ist es nicht. Er soll stehen bleiben, bis ihn
        jemand einmal geoeffnet hat, sonst verschwindet er beim
        Aufraeumen genau an dem Tag, an dem er gebraucht wird."""
        bleibt = [n for n in lauf.nachrichten
                  if n.get("art") == "system" and not n.get("gelesen")]
        lauf.nachrichten.clear()
        lauf.nachrichten.extend(bleibt)
        return {"anzahl": len(bleibt)}

    @app.post("/api/nachrichten/gelesen")
    async def nachrichten_gelesen():
        """Das Pult meldet, dass der Briefkasten offen war.

        Ab hier gilt der Hinweis als gelesen: er verschwindet beim
        naechsten Aufraeumen, und dieselbe Sprache fragt nicht wieder
        nach. An der Sprache selbst bleibt die kleine Zeile stehen."""
        neu = []
        marke = None
        for n in lauf.nachrichten:
            if n.get("art") == "system" and not n.get("gelesen"):
                n["gelesen"] = True
                if n.get("sprache"):
                    neu.append(n["sprache"])
                if n.get("systemcheck"):
                    marke = n["systemcheck"]
        if marke:
            lauf.zustand["systemcheck_quittiert"] = marke
            zustandsdatei.speichern(lauf.zustand)
        if neu:
            quittiert = list(lauf.zustand.get("glossar_quittiert") or [])
            for sp in neu:
                if sp not in quittiert:
                    quittiert.append(sp)
            lauf.zustand["glossar_quittiert"] = quittiert
            zustandsdatei.speichern(lauf.zustand)
        return {"quittiert": neu}

    @app.get("/api/zustand")
    def zustand():
        return {"live": lauf.laeuft, "gesendet": lauf.n, "hoerer": lauf.anzahl,
                # Worauf tatsaechlich gerechnet wird. Stand vorher nur im
                # Terminal, und das liest im Gottesdienst niemand.
                "fassung": config.VERSION,
                # Leer, solange keine gefunden ist. Wer aus der Ferne
                # fragt, soll den Unterschied sehen zwischen "noch keine"
                # und einer Adresse, die nicht stimmt.
                "adresse": lauf.adresse or "",
                "rechenwerk": getattr(lauf.werk, "rechenwerk", ""),
                "stt_fehler": (lauf.stt_fehler
                               if lauf.stt_fehler["anzahl"] else None),
                "gesamt": sum(lauf.anzahl.values()),
                "laeuft_seit": round(time.time() - lauf.begonnen, 1)
                if lauf.begonnen else 0,
                "prompt": lauf.werk.stt_prompt,
                "stellen": lauf.werk.kontext_stellen,
                "namen": lauf.werk.kontext_namen,
                "skript": lauf.werk.skript_info,
                "audio_quelle": (round(time.time() - lauf.audio_quelle, 1)
                                 if lauf.audio_quelle else None),
                "mitschnitt": lauf.mitschnitt.lage(),
                "protokoll_mitschrift": PROTOKOLL_MITSCHRIFT,
                # Nur ob eines gesetzt ist, nie der Hash. Das Pult muss
                # den Schalter richtig anzeigen und sonst nichts.
                "pult_passwort": wache.gesetzt,
                "nachrichten": list(lauf.nachrichten),
                # Steht hier und nicht nur unter Einrichtung: ein Update,
                # das aufs Anhalten wartet, geht den Techniker waehrend
                # des Gottesdienstes an -- und da hat er die Einrichtung
                # nicht offen. Leer, solange nichts ansteht.
                "update": update_kurz(),
                # Gehoert in die Betriebsansicht und nicht nur unter
                # Einrichtung: ein Rechner, der auf sein Mikrofon wartet,
                # sieht sonst aus wie einer, der aufnimmt. Genau das hat
                # einen Gottesdienst gekostet.
                "ton": tonquelle.lage() if tonquelle is not None else None,
                # Nur gefuellt, wenn dieser Rechner der Router ist. Was
                # den Betrieb verhindert, gehoert ans Pult und nicht nur
                # in pruefen.sh -- sonntags liest das niemand.
                "netz": netzpruefung.lage(),
                "letzte": list(lauf.letzte)[-8:]}

    @app.post("/api/steuerung/{was}")
    async def steuerung(was: str):
        if was == "start":
            await lauf.starten()
        elif was == "pause":
            await lauf.anhalten()
        elif was == "reset":
            await lauf.zuruecksetzen()
        else:
            return JSONResponse({"fehler": "unbekannt"}, status_code=400)
        return {"live": lauf.laeuft, "gesendet": lauf.n}

    @app.get("/api/pegel")
    def pegel():
        """Wird vom Pult mehrmals je Sekunde abgefragt, deshalb bewusst
        schlank gehalten."""
        seg = lauf.segmentierer
        lage = seg.lage()
        return {"lage": lage["stufe"], "lage_text": lage["text"],
                "einmessen": seg.einmessen_lage(),
                "jetzt": round(seg.pegel_jetzt, 5),
                "spitze": round(seg.pegel_spitze, 5),
                "grund": round(seg.grundpegel, 5),
                "schwelle": round(seg.schwelle, 5),
                "fest": seg.feste_schwelle is not None,
                "knapp": sum(1 for t in seg.zu_leise
                             if time.time() - t < 30),
                "spricht": seg.spricht,
                "verworfen": seg.verworfen}

    @app.post("/api/einmessen")
    async def einmessen(daten: dict):
        """Startet oder beendet das Einmessen der Mindestlautstaerke."""
        seg = lauf.segmentierer
        if daten.get("beenden"):
            erg = seg.einmessen_auswerten()
            if erg:
                print(f"Eingemessen: {erg['text']}")
            # Nur bei Erfolg: sonst steht die Schwelle unveraendert, und
            # ein Zeitstempel darauf wuerde eine Messung behaupten, die es
            # nicht gab.
            if erg and erg.get("erfolg"):
                schwelle_sichern()
            return erg or {"erfolg": False,
                           "text": "Zu wenig gemessen. Länger sprechen lassen."}
        seg.einmessen_starten(float(daten.get("dauer", 12)))
        return {"gestartet": True, "dauer": float(daten.get("dauer", 12))}

    @app.post("/api/schwelle")
    async def schwelle(daten: dict):
        """Setzt die Mindestlautstaerke oder gibt sie wieder frei.

        Im Gottesdienst wird sie einmal vor Beginn festgenagelt: Prediger
        sprechen lassen, Wert knapp unter dessen Pegel setzen, fertig. Alles
        Leisere wird dann gar nicht erst zu einem Segment."""
        seg = lauf.segmentierer
        if daten.get("automatisch"):
            seg.feste_schwelle = None
        else:
            wert = float(daten.get("wert", 0))
            seg.feste_schwelle = max(0.0005, min(0.5, wert))
        schwelle_sichern()
        return {"schwelle": round(seg.schwelle, 5),
                "fest": seg.feste_schwelle is not None}

    @app.post("/api/mitschnitt")
    async def mitschnitt(daten: dict):
        if daten.get("beenden"):
            return lauf.mitschnitt.beenden() or {"lief": False}
        datei = lauf.mitschnitt.starten()
        return {"datei": Path(datei).name}

    @app.get("/mitschnitt/{name}")
    def mitschnitt_holen(name: str):
        # Nur Dateinamen ohne Pfadanteile: sonst liesse sich ueber die
        # Adresse jede Datei des Rechners abrufen.
        datei = lauf.mitschnitt.ordner / Path(name).name
        if not datei.exists():
            return JSONResponse({"fehler": "nicht gefunden"}, status_code=404)
        return FileResponse(datei, media_type="audio/wav", filename=datei.name)

    @app.post("/api/kontext")
    async def kontext(daten: dict):
        """Nimmt Thema und Bibelstellen vom Pult und baut daraus den Prompt.

        Der Techniker fragt den Prediger vor dem Gottesdienst und tippt zwei
        Zeilen ein. Daraus werden die Kapitel gelesen und die Namen gezogen,
        die dort vorkommen, seltene zuerst. Der erste Nachtlauf hat gezeigt,
        warum das noetig ist: ein fester Prompt mit Lehrbegriffen brachte
        nichts, weil Whisper sich nicht an Begriffen verhoert, sondern an
        Eigennamen."""
        from bibelstellen import aus_pulttext
        text = (daten.get("text") or "").strip()
        erg = aus_pulttext(text, lauf.werk.namen, config.PROMPT_EINLEITUNG,
                           config.PROMPT_MAX_ZEICHEN,
                           zusatznamen=lauf.werk.skript_namen)
        lauf.werk.stt_prompt = erg["prompt"]
        lauf.werk.kontext_stellen = erg["stellen"]
        lauf.werk.kontext_namen = erg["namen"]
        print(f"Prompt gesetzt: {len(erg['stellen'])} Stellen, "
              f"{len(erg['namen'])} von {erg['namen_gefunden']} Namen")
        return {"prompt": erg["prompt"], "stellen": erg["stellen"],
                "namen": erg["namen"], "gefunden": erg["namen_gefunden"]}

    @app.post("/api/skript")
    async def skript(datei: UploadFile = File(None), text: str = Form("")):
        """Nimmt ein Predigtmanuskript und zieht die Namen daraus.

        Der Text wird ausdruecklich NICHT ausgeliefert, nur die Namen --
        und zwar die, die in keiner Bibelstelle stehen. Ausfuehrlich
        begruendet im Modulkommentar von skript_lesen.py."""
        from skript_lesen import auswerten, text_aus_datei
        if datei is not None and datei.filename:
            roh = await datei.read()
            inhalt = text_aus_datei(datei.filename, io.BytesIO(roh))
            quelle = datei.filename
        else:
            inhalt = text
            quelle = "eingefuegter Text"
        if not inhalt.strip():
            return JSONResponse({"fehler": "leer"}, status_code=400)

        erg = auswerten(inhalt, lauf.werk.namen)
        lauf.werk.skript_namen = erg["namen"]
        lauf.werk.skript_info = {
            "quelle": quelle, "woerter": erg["woerter"],
            "stellen": erg["stellen"], "namen": erg["namen"]}
        # Bibelstellen duerfen dastehen -- sie sind oeffentlich. Die
        # Namen nicht: das sind Menschen aus der Predigt.
        print(f"Manuskript: {quelle}, {erg['woerter']} Woerter, "
              f"{len(erg['namen'])} Namen"
              + (f" ({schutz(', '.join(erg['namen']), 120)})"
                 if erg['namen'] else "")
              + f", Stellen: {', '.join(erg['stellen']) or 'keine'}")

        # Falls im Manuskript Stellen stehen und das Kontextfeld leer war,
        # gleich den Prompt setzen. Ein Handgriff weniger am Pult.
        if erg["stellen"] and not lauf.werk.kontext_stellen:
            from bibelstellen import aus_pulttext
            neu = aus_pulttext(" ".join(erg["stellen"]), lauf.werk.namen,
                               config.PROMPT_EINLEITUNG,
                               config.PROMPT_MAX_ZEICHEN,
                               zusatznamen=erg["namen"])
            lauf.werk.stt_prompt = neu["prompt"]
            lauf.werk.kontext_stellen = neu["stellen"]
            lauf.werk.kontext_namen = neu["namen"]
        return {"quelle": quelle, "woerter": erg["woerter"],
                "stellen": erg["stellen"], "namen": erg["namen"],
                "bekannt": erg["sicher"], "neu": erg["unsicher"],
                "prompt": lauf.werk.stt_prompt}

    @app.get("/qr")
    def qr(request: Request, ssid: str = "", passwort: str = "",
           adresse: str = "", herunterladen: int = 0):
        """Projektionsseite mit zwei QR-Codes.

        Zwei Schritte, weil sie zwei verschiedene Dinge tun: der erste
        verbindet das Handy mit dem WLAN, der zweite oeffnet die Seite.
        Beide Codes lassen sich mit der Kamera scannen, es muss nichts
        getippt werden.

        Ausgelegt fuer den Beamer: heller Grund, sehr grosse Codes,
        wenig Text. Aus fuenfzehn Metern muss der Code noch scharf genug
        sein, deshalb bekommt er den groessten Teil der Flaeche."""
        import segno
        ssid = ssid or lauf.wlan.get("ssid", "")
        passwort = passwort or lauf.wlan.get("passwort", "")

        # Die Adresse kommt aus dem Aufruf selbst, nicht aus der eigenen
        # Netzkonfiguration. Wer die Seite ueber den Tunnel oeffnet, bekommt
        # die Tunneladresse in den Code, wer sie lokal oeffnet, die lokale.
        # Das ist immer die Adresse, unter der der Aufrufer den Server
        # tatsaechlich erreicht hat, und damit die einzige, die auch fuer
        # die Handys im Raum funktioniert.
        if not adresse:
            # Die Adresse im QR-Code muss die sein, unter der ein HANDY
            # IM SAAL diesen Rechner erreicht -- nicht die, unter der
            # gerade jemand das Pult geoeffnet hat. Wer das Pult ueber
            # http://localhost:8000/pult aufruft, bekam bis 0.2.11
            # "localhost" in den Code gedruckt. Der Beamer zeigte das
            # dann dem ganzen Saal, und jedes Handy landete bei sich
            # selbst.
            lage = netzzustand.laden()[0]
            if lage["router"] and lage["adresse"]:
                # Ist dieser Rechner der Router, steht die Adresse fest.
                # Port 80, denn darauf hoert er dann auch.
                adresse = f"http://{lage['adresse']}/"
            elif lauf.adresse:
                # Sonst die erkannte LAN-Adresse. Sie ist das, was
                # adresse_suchen() gefunden hat, und die kennen die
                # Handys.
                adresse = f"http://{lauf.adresse}:{a_port[0]}/"
            else:
                # Erst als Letztes das, womit der Aufrufer gekommen
                # ist. Ein Tunnel (x-forwarded-host) gehoert hierher:
                # wer von aussen zusieht, hat keine LAN-Adresse.
                weiter = request.headers.get("x-forwarded-host")
                gastgeber = weiter or request.headers.get("host") \
                    or request.url.netloc
                schema = (request.headers.get("x-forwarded-proto")
                          or ("https" if weiter else request.url.scheme))
                adresse = f"{schema}://{gastgeber}/"

            # localhost taugt nie: das ist fuer jedes Handy es selbst.
            if re.search(r"//(localhost|127\.|\[::1\])", adresse):
                if lauf.adresse:
                    adresse = f"http://{lauf.adresse}:{a_port[0]}/"
                else:
                    adresse = ""
        elif not adresse.startswith("http"):
            adresse = "https://" + adresse
        if not adresse.endswith("/"):
            adresse += "/"

        def bild(inhalt, groesse=14):
            code = segno.make(inhalt, error="m")
            return code.svg_data_uri(scale=groesse, border=2,
                                     dark="#141f52", light="#ffffff")

        seiten_qr = bild(adresse)
        if ssid:
            # Das Format fuer WLAN-Zugangsdaten, das Android und iOS seit
            # Jahren verstehen. Semikolon und Doppelpunkt im Passwort
            # muessen maskiert werden, sonst bricht der Datensatz.
            def maskieren(t):
                for z in ("\\", ";", ",", ":", '"'):
                    t = t.replace(z, "\\" + z)
                return t
            wlan_qr = bild(f"WIFI:T:WPA;S:{maskieren(ssid)};"
                           f"P:{maskieren(passwort)};;")
        else:
            wlan_qr = None

        # ------------------------------------------- Sprachen
        # Durchlaufen werden die Sprachen, die am Pult EINGESCHALTET
        # sind, dazu Englisch -- aber NICHT die Ausgangssprache. Wer
        # die Predigt direkt hoert, braucht keine Anleitung zum
        # Mithoeren; und der Platz im Durchlauf ist knapp genug, dass
        # jede ueberfluessige Sprache die anderen seltener zeigt.
        # Aus dem LAUFENDEN Dienst, nicht aus zustand.json. Die Datei
        # waere die zweite Quelle fuer dieselbe Frage -- und die
        # Zugangsdaten daneben kommen ohnehin aus dem Speicher. Zwei
        # Quellen laufen irgendwann auseinander, und dann zeigt die
        # Wand etwas anderes als das Pult.
        #
        # lauf.sprachen fuehrt die Ausgangssprache mit; sie faellt hier
        # heraus. Wer die Predigt direkt hoert, braucht keine Anleitung
        # zum Mithoeren, und jede ueberfluessige Sprache zeigt die
        # anderen seltener.
        quelle = lauf.quelle
        folge = [sp for sp in lauf.sprachen if sp != quelle]
        if "en" != quelle and "en" not in folge:
            folge.append("en")
        if not folge:
            # Nur denkbar, wenn auf Englisch gepredigt wird und keine
            # Zielsprache eingeschaltet ist. Dann ist die Seite ohnehin
            # gegenstandslos -- aber leer soll sie nicht sein.
            folge = ["en"]

        sprachdaten = [{
            "code": sp,
            "name": qr_texte.name(sp),
            "rtl": qr_texte.rtl(sp),
            "titel1": qr_texte.fuer(sp)["schritt1"],
            "titel2": qr_texte.fuer(sp)["schritt2"],
            "geduld": qr_texte.fuer(sp)["geduld"],
            "internet": qr_texte.fuer(sp)["internet"],
            "hoeren": qr_texte.fuer(sp)["hoeren"],
        } for sp in folge]

        # ------------------------------------------- Bausteine
        nr_seite = "2" if wlan_qr else "1"
        if wlan_qr:
            # Netzname UND Passwort im Klartext darunter. Der QR ist
            # der bequeme Weg, nicht der einzige: aeltere Handys,
            # Laptops und schlechtes Licht gibt es. Verborgen waere das
            # Passwort ohnehin nicht -- es steckt im Code.
            wlan_block = (
                '<div class=schritt>'
                '<span class=nr>1</span>'
                '<div class=kopf>' + ZEICHEN["wlan"] +
                '<p class=was id=titel1></p></div>'
                '<div class=codefeld>'
                f'<img src="{wlan_qr}" alt="">'
                '<p class=zugang>'
                f'<b>Netz</b><span>{html_escape(ssid)}</span>'
                f'<b>Passwort</b><span>{html_escape(passwort)}</span>'
                '</p></div></div>')
        else:
            wlan_block = ""

        def drucksatz():
            """Eine Seite je Sprache, fertig im Server gebaut."""
            teile = []
            for d in sprachdaten:
                richtung = "rtl" if d["rtl"] else "ltr"
                zugang = ""
                if wlan_qr:
                    zugang = (f'<div><img src="{wlan_qr}" alt="">'
                              f'<p><b>Netz</b>{html_escape(ssid)}<br>'
                              f'<b>Passwort</b>{html_escape(passwort)}</p>'
                              f'</div>')
                teile.append(
                    f'<section class=druckseite lang="{d["code"]}">'
                    f'<h2 dir="{richtung}">{html_escape(d["name"])}</h2>'
                    f'<div class=druckcodes>{zugang}'
                    f'<div><img src="{seiten_qr}" alt="">'
                    f'<p><b>{html_escape(d["titel2"])}</b>'
                    f'{html_escape(adresse)}</p></div></div>'
                    + "".join(
                        f'<div class="kasten {farbe}">'
                        f'<span class=zeichen>{zeichen}</span>'
                        f'<p class=satz dir="{richtung}">'
                        f'{html_escape(d[feld])}</p></div>'
                        for farbe, feld, zeichen in KAESTEN)
                    + '</section>')
            return "".join(teile)

        if herunterladen:
            # Eigenstaendig: keine Adresse dieses Servers darin, sonst
            # bliebe die Seite auf einem Laptop ausserhalb des
            # Saalnetzes leer. Das Logo wandert als Datenadresse
            # hinein, die Verweise auf PNG-Dateien fallen weg.
            logo = logo_datenadresse(basis)
            holen = ('<a href="javascript:window.print()">'
                     'Diese Seite drucken</a>')
        else:
            logo = "/logo.png"
            holen = (
                '<a href="/qr.png?was=seite" download>Adress-Code als PNG</a>'
                + ('<a href="/qr.png?was=wlan" download>WLAN-Code als PNG</a>'
                   if wlan_qr else "")
                + '<a href="/qr?herunterladen=1" download="Devarenu-QR.html">'
                  'Als Datei herunterladen</a>'
                + '<a href="javascript:window.print()">Seite drucken</a>')

        seite = QR_SEITE
        for marke, wert in (
                ("<!--LOGO-->", logo),
                ("<!--WLANSCHRITT-->", wlan_block),
                ("<!--NRSEITE-->", nr_seite),
                ("<!--SEITENQR-->", seiten_qr),
                ("<!--ADRESSE-->", html_escape(adresse)),
                ("<!--HOLEN-->", holen),
                ("<!--ZEICHENSEITE-->", ZEICHEN["kopfhoerer"]),
                ("<!--KAESTEN-->", "".join(
                    f'<div class="kasten {farbe}">'
                    f'<span class=zeichen>{zeichen}</span>'
                    f'<p class=satz id={feld}></p></div>'
                    for farbe, feld, zeichen in KAESTEN)),
                ("<!--DRUCKSATZ-->", drucksatz()),
                ("<!--SPRACHDATEN-->",
                 json.dumps(sprachdaten, ensure_ascii=False)),
        ):
            seite = seite.replace(marke, wert)

        if herunterladen:
            return HTMLResponse(seite, headers={
                "Content-Disposition":
                    'attachment; filename="Devarenu-QR.html"'})
        return HTMLResponse(seite)

    @app.get("/fehlerbericht.txt")
    def fehlerbericht_txt(schnell: int = 0):
        """Der Bericht zum Anhaengen an eine Mail.

        Erzeugt beim Abruf, nie gespeichert: er beschreibt den Rechner
        in DIESEM Moment, und eine alte Kopie waere schlimmer als
        keine."""
        import fehlerbericht as fb
        try:
            if schnell:
                # pruefen.sh dauert Minuten. Vom Handy aus, im Saal,
                # will niemand so lange warten.
                alt = fb._pruefen_zusammen
                fb._pruefen_zusammen = lambda: ["(uebersprungen, "
                                                "siehe pruefen.sh)"]
                try:
                    text = fb.bauen()
                finally:
                    fb._pruefen_zusammen = alt
            else:
                text = fb.bauen()
        except Exception as e:
            text = (f"Devarenu -- Fehlerbericht\n\nDer Bericht liess "
                    f"sich nicht erzeugen: {type(e).__name__}\n")
        name = f"devarenu-{config.VERSION}-fehlerbericht.txt"
        return PlainTextResponse(
            text, headers={"Cache-Control": "no-store",
                           "Content-Disposition":
                               f'attachment; filename="{name}"'})

    @app.get("/fehler-qr.png")
    def fehler_qr(was: str = "mail"):
        """Zwei QR-Codes fuer den Fehler-Dialog.

        mail     oeffnet auf dem Handy eine fertige Mail
        bericht  laedt den Fehlerbericht aufs Handy

        Der zweite ist noetig, weil das Pult meist am Rechner selbst
        bedient wird -- ein Download DORT kommt nie in die Mail. Das
        Handy im Saalnetz kann ihn holen und spaeter anhaengen.

        Beide bewusst klein gehalten: gemessen wird ein mailto mit
        Betreff und kurzem Rumpf zu QR-Version 9. Nimmt man die Befunde
        mit hinein, sind es Version 10 bis 14 -- und ab 10 wird es fuer
        Handykameras zaeh. Die Einzelheiten stehen deshalb im Bericht,
        nicht im Code."""
        import segno
        import urllib.parse
        if was == "bericht":
            # Ueber Port 80, damit keine Portnummer im Code steht und
            # der Link auch ohne sie geht. Mit gesetztem Pult-Passwort
            # haengt ein Einmalschluessel dran -- sonst kaeme das Handy
            # nicht hinein: es ist im Saalnetz und hat keinen Keks.
            inhalt = bericht_link()
            if not inhalt:
                return JSONResponse({"fehler": "keine Adresse bekannt"},
                                    status_code=404)
        else:
            betreff = f"Devarenu {config.VERSION}: Fehlermeldung"
            rumpf = (f"Datum: {time.strftime('%d.%m.%Y %H:%M')}\n"
                     f"Fassung: {config.VERSION}\n\n"
                     f"Was ist passiert?\n\n")
            inhalt = "mailto:" + config.RUECKMELDUNG_MAIL + "?" \
                + urllib.parse.urlencode({"subject": betreff, "body": rumpf})
        code = segno.make(inhalt, error="m")
        puffer = io.BytesIO()
        module = code.symbol_size(border=2)[0]
        code.save(puffer, kind="png", scale=max(4, 560 // module), border=2,
                  dark="#141f52", light="#ffffff")
        return Response(content=puffer.getvalue(), media_type="image/png",
                        headers={"Cache-Control": "no-store"})

    def bericht_link():
        """Der Link, unter dem ein Handy im Saal den Bericht holt.

        Eine Funktion und nicht zweimal derselbe Code: der QR und der
        Text darunter muessen auf dieselbe Adresse zeigen. Stimmten sie
        nicht ueberein, fiele es genau dann auf, wenn jemand den einen
        Weg probiert, weil der andere nicht ging.

        Mit gesetztem Pult-Passwort haengt ein Einmalschluessel dran.
        Ohne Passwort bleibt der Link kurz."""
        lage = netzzustand.laden()[0]
        if lage["router"] and lage["adresse"]:
            grund = f"http://{lage['adresse']}/fehlerbericht.txt?schnell=1"
        elif lauf.adresse:
            grund = (f"http://{lauf.adresse}:{a_port[0]}"
                     f"/fehlerbericht.txt?schnell=1")
        else:
            return ""
        if wache.gesetzt:
            grund += "&schluessel=" + wache.schluessel.neu()
        return grund

    @app.get("/api/betreuer")
    def betreuer():
        """Name und Adresse fuers Pult -- aus betreuer.txt.

        Dazu der Berichtlink im Klartext. Wer den QR nicht scannen kann
        -- aelteres Handy, schlechtes Licht --, tippt ihn ab. Dieselbe
        Ueberlegung wie beim WLAN-Passwort auf der QR-Seite: der Code
        ist der bequeme Weg, nicht der einzige."""
        return {"name": config.BETREUER_NAME,
                "mail": config.RUECKMELDUNG_MAIL,
                "bericht_link": bericht_link()}

    @app.get("/anleitung.pdf")
    def anleitung(teil: str = "alles", sprache: str = ""):
        """Die Bedienungsanleitung. Fertig gebaut, liegt im Repo.

        Gebaut wird sie auf dem Arbeitsrechner (bash anleitung_bauen.sh);
        hier wird nur ausgeliefert. Der Gemeinderechner bekommt dafuer
        kein zusaetzliches Paket -- und er hat im Betrieb ohnehin kein
        Netz, ueber das eines nachkommen koennte."""
        if teil != "zuhoerer":
            name = "Devarenu-Anleitung.pdf"
        else:
            # In der Sprache, die der Zuhoerer gewaehlt hat. Wer
            # uebersetzt mithoert, spricht ja gerade kein Deutsch --
            # eine Anleitung nur auf Deutsch waere fuer genau die
            # Leute unlesbar, fuer die sie gedacht ist.
            kurz = (sprache or "")[:2].lower()
            name = ("Devarenu-Zuhoerer.pdf" if kurz == "de"
                    else f"Devarenu-Zuhoerer-{kurz}.pdf")
            if kurz and not (basis / "anleitung" / name).exists():
                # Keine Fassung in dieser Sprache: dann Englisch, nicht
                # Deutsch. Wer hier eine andere Sprache gewaehlt hat,
                # versteht mit einiger Wahrscheinlichkeit kein Deutsch
                # -- das ist ja der Grund, warum er mithoert. Englisch
                # ist die bessere Wette.
                name = "Devarenu-Zuhoerer-en.pdf"
            if not (basis / "anleitung" / name).exists():
                # Auch die englische fehlt: dann die deutsche, statt
                # gar nichts.
                name = "Devarenu-Zuhoerer.pdf"
        datei = basis / "anleitung" / name
        if not datei.exists():
            return JSONResponse(
                {"fehler": "Die Anleitung ist nicht gebaut.",
                 "abhilfe": "bash anleitung_bauen.sh (auf dem "
                            "Arbeitsrechner), dann einchecken"},
                status_code=404)
        return FileResponse(datei, media_type="application/pdf",
                            filename=name)

    @app.get("/qr.png")
    def qr_png(was: str = "seite"):
        """Ein QR-Code als PNG, gross genug fuer Beamer und Druck.

        Erzeugt bei jedem Abruf neu und NIE im Repo abgelegt: der
        WLAN-Code enthaelt das Passwort der Gemeinde, und das Repo ist
        oeffentlich.

        1200 Pixel Kantenlaenge. Auf einem Beamer mit 1920 Bildpunkten
        Breite fuellt das gut die halbe Hoehe, und gedruckt auf A4
        bleibt der Code auch aus zwei Metern lesbar. Kleiner waere die
        haeufigste Ursache fuer "der Code geht nicht"."""
        import segno
        if was == "wlan":
            ssid = lauf.wlan.get("ssid", "")
            if not ssid:
                return JSONResponse({"fehler": "kein WLAN hinterlegt"},
                                    status_code=404)
            def maskieren(t):
                for z in ("\\", ";", ",", ":", '"'):
                    t = t.replace(z, "\\" + z)
                return t
            inhalt = (f"WIFI:T:WPA;S:{maskieren(ssid)};"
                      f"P:{maskieren(lauf.wlan.get('passwort', ''))};;")
            name = "devarenu-wlan.png"
        else:
            lage = netzzustand.laden()[0]
            if lage["router"] and lage["adresse"]:
                inhalt = f"http://{lage['adresse']}/"
            elif lauf.adresse:
                inhalt = f"http://{lauf.adresse}:{a_port[0]}/"
            else:
                return JSONResponse({"fehler": "keine Adresse bekannt"},
                                    status_code=404)
            name = "devarenu-seite.png"

        code = segno.make(inhalt, error="m")
        puffer = io.BytesIO()
        # scale so waehlen, dass ungefaehr 1200 Pixel herauskommen --
        # die Modulzahl haengt vom Inhalt ab, eine feste Skalierung
        # ergaebe je nach Passwortlaenge ganz verschiedene Groessen.
        module = code.symbol_size(border=2)[0]
        code.save(puffer, kind="png", scale=max(4, 1200 // module),
                  border=2, dark="#141f52", light="#ffffff")
        return Response(
            content=puffer.getvalue(), media_type="image/png",
            headers={"Cache-Control": "no-store",
                     "Content-Disposition": f'attachment; filename="{name}"'})

    @app.get("/api/wlan")
    def wlan_lesen():
        return lauf.wlan

    @app.post("/api/protokoll")
    async def protokoll(daten: dict):
        """Schaltet die Mitschrift im Protokoll an oder aus.

        Sofort wirksam, ohne Neustart: wer zur Fehlersuche einschaltet,
        will die naechste Zeile sehen und nicht den naechsten Dienst."""
        global PROTOKOLL_MITSCHRIFT
        an = bool(daten.get("an"))
        PROTOKOLL_MITSCHRIFT = an
        lauf.zustand["protokoll_mitschrift"] = an
        zustandsdatei.speichern(lauf.zustand)
        print(warnung("Mitschrift im Protokoll EINGESCHALTET.") if an
              else "Mitschrift im Protokoll ausgeschaltet.")
        return {"an": an}

    @app.post("/api/wlan")
    async def wlan(daten: dict):
        lauf.wlan = {"ssid": (daten.get("ssid") or "").strip(),
                     "passwort": (daten.get("passwort") or "").strip()}
        lauf.zustand["wlan"] = dict(lauf.wlan)
        zustandsdatei.speichern(lauf.zustand)
        return lauf.wlan

    # ------------------------------------------------------------ Update
    # Was das Update per USB-Stick zuletzt gemacht hat. Geschrieben wird
    # die Datei von stick_update.sh, hier wird sie nur gelesen: ueber
    # Updates entscheidet der Server nichts, er richtet aus.
    #
    # Der Umweg ueber eine Datei und nicht ueber den Speicher ist Absicht.
    # Ein Update startet den Dienst neu -- was sich der Server gemerkt
    # haette, waere genau dann weg, wenn die Meldung gebraucht wird.
    stand_zwischen = {"zeit": 0.0, "wert": {}}

    def update_stand():
        """Liest update/stand.json, hoechstens einmal je Sekunde.

        Das Pult fragt /api/zustand mehrmals je Minute ab; ohne den
        Zwischenspeicher laege bei jeder Abfrage ein Dateizugriff dahinter,
        nur damit meistens dasselbe herauskommt."""
        jetzt = time.time()
        if jetzt - stand_zwischen["zeit"] < 1.0:
            return stand_zwischen["wert"]
        try:
            wert = json.loads(
                (basis / "update" / "stand.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            wert = {}
        stand_zwischen.update(zeit=jetzt, wert=wert)
        return wert

    def update_kurz():
        """Was die Betriebsansicht braucht, oder nichts.

        Nur was ansteht, nicht was war: ein eingespieltes Update gehoert
        unter Einrichtung nachgelesen, nicht neben den Pegel.

        Lage und Fassung statt eines fertigen Satzes -- den baut das Pult,
        und zwar in der Sprache, die dort eingestellt ist. Frueher stand
        hier der deutsche Text aus der Statusdatei, und der blieb auch
        unter englischer Oberflaeche deutsch."""
        stand = update_stand()
        if stand.get("lage") in ("bereit", "wartet"):
            return {"lage": stand["lage"], "version": stand.get("version", "")}
        return None

    @app.get("/api/update")
    def update_lesen():
        stand = dict(update_stand())
        # Ob der Knopf etwas bewirken kann, weiss der Server besser als
        # die Oberflaeche: nur wenn wirklich etwas vorgemerkt ist, noch
        # nicht gedrueckt wurde und die Uebersetzung steht.
        stand["bereit"] = (basis / "update" / "bereit").exists()
        stand["gedrueckt"] = (basis / "update" / "jetzt").exists()
        stand["live"] = lauf.laeuft
        return stand

    @app.post("/api/update/jetzt")
    async def update_jetzt():
        """Setzt die Marke, auf die stick_update.sh wartet.

        Der Server startet nichts selbst neu -- er laeuft als gewoehnlicher
        Benutzer und hat mit systemd nichts zu schaffen. Er legt eine
        Datei an, und der Timer, der ohnehin jede Minute nachsieht,
        ueberspringt daraufhin die Wartezeit. Das kostet bis zu eine
        Minute und spart eine sudo-Regel, die sonst dauerhaft offenstuende."""
        ablage = basis / "update"
        if not (ablage / "bereit").exists():
            return JSONResponse({"grund": "kein_update"}, status_code=400)
        # Waehrend der Uebersetzung nicht. Der Knopf ist dann zwar
        # gesperrt, aber die Sperre sitzt in der Oberflaeche -- und wer
        # zwei Pulte offen hat, sieht auf dem einen noch den Stand von
        # vorhin. Die Entscheidung gehoert hierher.
        if lauf.laeuft:
            return JSONResponse({"grund": "laeuft"}, status_code=409)
        try:
            (ablage / "jetzt").write_text("", encoding="utf-8")
        except OSError as e:
            print(f"Update: Marke nicht schreibbar: {str(e)[:120]}")
            return JSONResponse({"grund": "nicht_schreibbar"}, status_code=500)
        print("Update: am Pult auf Einspielen gedrueckt.")
        return {"angenommen": True}

    @app.get("/pult")
    def pult():
        return HTMLResponse((basis / "pult.html").read_text(encoding="utf-8")
                            if (basis / "pult.html").exists() else PULT)

    # Einmal beim Start nachsehen, wie der Rechner eingestellt ist.
    # Hier und nicht frueher: der Briefkasten gehoert zu lauf, und die
    # Nachricht soll dastehen, bevor der erste Mensch das Pult oeffnet.
    #
    # Ein Fehler im Systemcheck darf den Server nicht aufhalten -- er
    # ist eine Auskunft, kein Betriebsteil.
    try:
        hinweis = systemnachricht()
        if hinweis:
            lauf.nachrichten.append(hinweis)
            schwer = hinweis["text"].count("•")
            print(f"Systemcheck: {schwer} Punkt(e) ins Pult gelegt.")
    except Exception as e:
        print(f"Systemcheck uebersprungen ({str(e)[:90]}).")

    return app


# Die Seite, die statt des Pults erscheint, solange sich das Geraet
# nicht ausgewiesen hat. Bewusst karg: sie ist kein Teil der Bedienung,
# sondern eine Tuer. Und sie sagt, wo das Passwort herkommt -- sonst
# steht sonntags jemand davor und weiss nicht, wen er fragen soll.
ANMELDUNG = """<!doctype html><html lang=de><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Pult</title>
<style>
 *{{box-sizing:border-box}}
 body{{font:16px/1.5 Georgia,serif;color:#141f52;background:#f7f8fa;
   margin:0;min-height:100vh;display:grid;place-items:center;padding:1.5rem}}
 form{{background:#fff;border:1px solid #d9dce4;border-radius:.6rem;
   padding:1.6rem;max-width:22rem;width:100%}}
 h1{{font-size:1.25rem;font-weight:400;margin:0 0 .3rem;
   letter-spacing:.06em;text-transform:uppercase}}
 p{{font:.9rem/1.45 system-ui,sans-serif;color:#6b7385;margin:.2rem 0 1.1rem}}
 input{{font:1.05rem system-ui,sans-serif;width:100%;padding:.7rem;
   border:1px solid #d9dce4;border-radius:.35rem;margin-bottom:.8rem}}
 button{{font:1rem Georgia,serif;letter-spacing:.06em;width:100%;
   padding:.8rem;border:0;border-radius:.35rem;background:#1c3a8f;
   color:#fff;cursor:pointer}}
 .fehler{{color:#c0392b;font:.9rem system-ui,sans-serif;margin:0 0 .8rem}}
</style>
<form method=post action="/pult-anmeldung">
 <h1>Pult</h1>
 <p>Diese Gemeinde hat das Pult mit einem Passwort versehen. Einmal
 eingeben, danach merkt sich dieses Gerät die Anmeldung.</p>
 {fehler}
 <input type=password name=passwort placeholder="Passwort" autofocus
   autocomplete="current-password">
 <input type=hidden name=ziel value="{ziel}">
 <button type=submit>Weiter</button>
</form>
</html>"""

ANMELDUNG_FEHLER = '<p class=fehler>Das war nicht das richtige Passwort.</p>'

# Die Symbole. Einmal definiert, damit Bildschirm und Druck dieselben
# zeigen -- zwei Saetze waeren zwei Baustellen, und gedruckt faellt es
# erst auf, wenn das Blatt am Eingang liegt.
#
# Eigene SVGs und kein Symbolsatz von aussen: die Seite muss ohne Netz
# laufen, auf dem Gemeinderechner UND auf einem fremden Laptop, der die
# heruntergeladene Datei oeffnet.
ZEICHEN = {
    "wlan": '<svg viewBox="0 0 24 24" aria-hidden="true">'
            '<path d="M2.5 8.5a15 15 0 0 1 19 0"/>'
            '<path d="M6 12a10 10 0 0 1 12 0"/>'
            '<path d="M9.5 15.5a5 5 0 0 1 5 0"/>'
            '<circle class=voll cx="12" cy="19" r="1.5"/></svg>',
    "kopfhoerer": '<svg viewBox="0 0 24 24" aria-hidden="true">'
                  '<path d="M4 14v-3a8 8 0 0 1 16 0v3"/>'
                  '<rect x="2" y="13" width="4" height="7" rx="1.6"/>'
                  '<rect x="18" y="13" width="4" height="7" rx="1.6"/></svg>',
    # Sanduhr
    "sanduhr": '<svg viewBox="0 0 24 24" aria-hidden="true">'
               '<path d="M7 3h10M7 21h10"/>'
               '<path d="M8 3v3.5L12 11l4-4.5V3"/>'
               '<path d="M8 21v-3.5L12 13l4 4.5V21"/></svg>',
    # Zwei Pfeile im Kreis, durchgestrichen: NICHT neu verbinden.
    "nichtneu": '<svg viewBox="0 0 24 24" aria-hidden="true">'
                '<path d="M20 10a8 8 0 0 0-14-4M4 14a8 8 0 0 0 14 4"/>'
                '<path d="M20 5v5h-5M4 19v-5h5"/>'
                '<path class=weg d="M4 4l16 16"/></svg>',
    "haken": '<svg viewBox="0 0 24 24" aria-hidden="true">'
             '<path d="M5 12l5 5L19 8"/></svg>',
    # Eine durchgestrichene WELTKUGEL -- ausdruecklich NICHT ein
    # durchgestrichenes WLAN-Zeichen. Das liest sich als "WLAN
    # ausschalten", und genau das soll niemand tun.
    #
    # Und getrennt vom WLAN-Zeichen, nicht darueber gelegt: uebereinander
    # ergaben beide zusammen einen Klecks, an dem aus zwoelf Metern
    # nichts mehr zu erkennen war. Nebeneinander lesen sie sich als
    # "WLAN ja, Internet nein" -- genau die Aussage.
    "keinglobus": '<svg viewBox="0 0 24 24" aria-hidden="true">'
                  '<circle cx="12" cy="12" r="8.5"/>'
                  '<path d="M3.5 12h17"/>'
                  '<path d="M12 3.5c2.2 2.3 3.4 5.3 3.4 8.5s-1.2 6.2-3.4 8.5'
                  'c-2.2-2.3-3.4-5.3-3.4-8.5s1.2-6.2 3.4-8.5z"/>'
                  '<path class=weg d="M5.5 18.5l13-13"/></svg>',
    "handy": '<svg viewBox="0 0 24 24" aria-hidden="true">'
             '<rect x="6.5" y="2.5" width="11" height="19" rx="2"/>'
             '<path d="M10.5 5.5h3"/>'
             '<circle class=voll cx="12" cy="18.5" r="1"/></svg>',
}

# Was in welchem Kasten steht: Farbe, Textfeld, Symbolfeld.
KAESTEN = (
    ("gelb", "geduld",
     ZEICHEN["sanduhr"] + '<span class=wort>1 min</span>'
     + ZEICHEN["nichtneu"]),
    ("blau", "internet",
     '<span class=wort>5G</span>' + ZEICHEN["haken"]
     + ZEICHEN["wlan"] + ZEICHEN["keinglobus"]),
    ("lila", "hoeren", ZEICHEN["kopfhoerer"] + ZEICHEN["handy"]),
)


def logo_datenadresse(basis):
    """Das Logo als Datenadresse -- fuer die eigenstaendige Datei.

    Sie soll auf einem Laptop ausserhalb des Saalnetzes laufen. Ein
    Verweis auf /logo.png liefe dort ins Leere, und die Seite zeigte
    ein kaputtes Bild."""
    import base64
    datei = Path(basis) / "logo.png"
    try:
        roh = base64.b64encode(datei.read_bytes()).decode("ascii")
    except OSError:
        return ""
    return "data:image/png;base64," + roh


QR_SEITE = """<!doctype html><html lang=de><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Übersetzung</title>
<style>
 /* Fuer den Beamer gebaut, 16:9. Links die zwei Schritte mit den
    Codes, rechts die drei Saetze, die sonst als Rueckfrage kommen.
    Aus zwoelf Metern liest niemand einen Nebensatz -- deshalb wenig
    Text, grosse Codes, klare Farben. */
 *{box-sizing:border-box;margin:0}
 :root{
   --tinte:#141f52; --grau:#6b7385; --linie:#d9dce4;
   --gelb-rand:#c8912b; --gelb-grund:#fff7e6; --gelb-text:#5a3f0a;
   --blau-rand:#1c6fa8; --blau-grund:#eaf4fb; --blau-text:#0d3f63;
   --lila-rand:#6b4a9e; --lila-grund:#f3eefb; --lila-text:#3b1e73;
 }
 body{font:16px/1.4 Georgia,serif;color:var(--tinte);background:#fff;
   height:100vh;display:flex;flex-direction:column;padding:2.2vh 2.4vw}
 header{display:flex;align-items:center;gap:1.2vw;flex:0 0 auto}
 .logo{height:5.2vh;width:auto;opacity:.9}
 h1{font-size:clamp(1.3rem,3.6vh,3rem);font-weight:400;
   letter-spacing:.1em;text-transform:uppercase}
 .streifen{height:.5vh;flex:1;margin-left:.6vw;
   background:linear-gradient(90deg,#3b1e73,#1c3a8f 52%,#1fa5d8)}

 main{display:grid;grid-template-columns:1fr 1fr;gap:2.4vw;
   flex:1;min-height:0;padding-top:1.6vh}

 /* ---------------------------------------------------- links */
 .links{display:grid;grid-template-rows:1fr 1fr;gap:1.6vh;min-height:0}
 .schritt{display:grid;grid-template-columns:auto 1fr;
   grid-template-rows:auto 1fr;column-gap:1.2vw;row-gap:.6vh;min-height:0}
 .nr{grid-row:1 / span 2;display:grid;place-items:center;
   width:6.4vh;height:6.4vh;border-radius:50%;
   background:var(--tinte);color:#fff;
   font:3.2vh/1 system-ui,sans-serif}
 .kopf{display:flex;align-items:center;gap:.7vw;min-width:0}
 .kopf svg{width:4.2vh;height:4.2vh;flex:0 0 auto;stroke:var(--tinte)}
 /* Alle Groessen in vh und mit hohen Obergrenzen: die Seite haengt
    am Beamer, nicht auf einem Bildschirm. Bei 1080p ist 1vh rund
    11 Pixel -- eine Obergrenze von 1,4rem haette den Text auf 22
    Pixel gedeckelt, und aus zwoelf Metern liest das niemand. */
 .was{font-size:clamp(1.1rem,3.2vh,2.6rem);min-width:0}
 .codefeld{display:flex;align-items:center;gap:1.2vw;min-height:0}
 .codefeld img{height:100%;max-height:30vh;width:auto;
   image-rendering:pixelated}
 /* Netzname, Passwort und Adresse werden von hinten abgetippt.
    Sie sind die groesste Schrift der Seite nach den Ueberschriften. */
 .zugang{font:2.9vh/1.45 ui-monospace,SFMono-Regular,Menlo,monospace;
   word-break:break-word;min-width:0;letter-spacing:.02em}
 .zugang b{display:block;font:1.9vh/1.4 system-ui,sans-serif;
   color:var(--grau);font-weight:600;letter-spacing:.04em;
   text-transform:uppercase}
 .zugang span{display:block;margin-bottom:.8vh}

 /* ---------------------------------------------------- rechts */
 .rechts{display:flex;flex-direction:column;gap:1.2vh;min-height:0}
 .sprachkopf{display:flex;align-items:center;justify-content:space-between;
   gap:1vw;flex:0 0 auto;border-bottom:1px solid var(--linie);
   padding-bottom:.6vh}
 .sprachname{font-size:clamp(1.05rem,3.1vh,2.4rem);color:var(--tinte)}
 .punkte{display:flex;gap:.5vw}
 .punkt{width:1.1vh;height:1.1vh;border-radius:50%;
   background:var(--linie)}
 .punkt.an{background:var(--tinte)}

 .kasten{display:grid;grid-template-columns:auto 1fr;gap:1.1vw;
   align-items:center;border:.25vh solid;border-radius:.7vh;
   padding:1.2vh 1.2vw;flex:1;min-height:0}
 /* Das Symbolfeld bleibt LINKS, in jeder Sprache. Wer vorn sagt
    "der gelbe Kasten oben", muss auch auf Farsi recht haben --
    also dreht sich nur der Text, nie die Anordnung. */
 .zeichen{display:flex;align-items:center;gap:.5vw;flex:0 0 auto}
 .zeichen svg{width:5.6vh;height:5.6vh}
 .zeichen .wort{font:2.4vh/1 system-ui,sans-serif;font-weight:700}
 .satz{font:clamp(1.05rem,3vh,2.3rem)/1.32 system-ui,sans-serif;
   min-width:0}
 .gelb{border-color:var(--gelb-rand);background:var(--gelb-grund);
   color:var(--gelb-text)}
 .gelb svg{stroke:var(--gelb-rand)} .gelb .wort{color:var(--gelb-rand)}
 .blau{border-color:var(--blau-rand);background:var(--blau-grund);
   color:var(--blau-text)}
 .blau svg{stroke:var(--blau-rand)} .blau .wort{color:var(--blau-rand)}
 .lila{border-color:var(--lila-rand);background:var(--lila-grund);
   color:var(--lila-text)}
 .lila svg{stroke:var(--lila-rand)} .lila .wort{color:var(--lila-rand)}

 svg{fill:none;stroke-width:1.9;stroke-linecap:round;
   stroke-linejoin:round}
 .voll{fill:currentColor;stroke:none}
 .weg{stroke:#c0392b;stroke-width:2.4}

 .holen{font:1.7vh system-ui,sans-serif;text-align:center;
   flex:0 0 auto;padding-top:1vh}
 .holen a{color:#1c3a8f;margin:0 .7em}

 /* Gedruckt: eine Seite JE SPRACHE, zum Auslegen am Eingang. Der
    Beamer zeigt immer genau eine und wechselt; Papier kann nicht
    wechseln. Die Seiten entstehen im Server, nicht im Skript --
    gedruckt wird oft aus einer Vorschau, und ob dort ein Zeitgeber
    lief, soll keine Rolle spielen. */
 .drucksatz{display:none}
 @media print{
   body{height:auto;display:block;padding:1.2cm;font-size:11pt}
   main,.holen,.streifen{display:none}
   .drucksatz{display:block}
   .druckseite{break-after:page}
   .druckseite:last-child{break-after:auto}
   .druckseite h2{font:1.2rem Georgia,serif;font-weight:400;
     margin:0 0 .5cm;padding-bottom:.2cm;
     border-bottom:1px solid var(--linie)}
   .druckcodes{display:flex;gap:1cm;margin-bottom:.6cm}
   .druckcodes img{width:6.5cm;height:auto}
   .druckcodes p{font:10pt/1.4 ui-monospace,monospace;word-break:break-all}
   .druckcodes b{display:block;font:9pt system-ui,sans-serif;
     color:var(--grau);text-transform:uppercase;letter-spacing:.04em}
   .drucksatz .kasten{break-inside:avoid;margin-bottom:.35cm;
     padding:.35cm;display:grid;grid-template-columns:auto 1fr;gap:.5cm}
   .drucksatz .zeichen svg{width:1.1cm;height:1.1cm}
   .drucksatz .satz{font-size:11pt}
 }
</style>
<header>
  <img class=logo src="<!--LOGO-->" alt="" onerror="this.remove()">
  <h1>Übersetzung</h1>
  <div class=streifen></div>
</header>

<main>
 <section class=links>
<!--WLANSCHRITT-->
  <div class=schritt>
    <span class=nr><!--NRSEITE--></span>
    <div class=kopf><!--ZEICHENSEITE--><p class=was id=titel2></p></div>
    <div class=codefeld>
      <img src="<!--SEITENQR-->" alt="">
      <p class=zugang><b>Adresse</b><span><!--ADRESSE--></span></p>
    </div>
  </div>
 </section>

 <section class=rechts>
  <div class=sprachkopf>
    <span class=sprachname id=sprachname></span>
    <span class=punkte id=punkte></span>
  </div>

<!--KAESTEN-->
 </section>
</main>

<p class=holen><!--HOLEN--></p>

<div class=drucksatz><!--DRUCKSATZ--></div>

<script>
// Die Sprachen, die am Pult eingeschaltet sind, dazu immer Englisch.
// Wer uebersetzt mithoert, liest kein Deutsch -- und Englisch ist die
// Sprache, in der am ehesten jemand mitkommt, dessen eigene fehlt.
const SPRACHEN = <!--SPRACHDATEN-->;
const FELDER = ["titel1","titel2","geduld","internet","hoeren"];
let wo = 0;

function punkteBauen(){
  const p = document.getElementById("punkte");
  p.innerHTML = "";
  for(let i = 0; i < SPRACHEN.length; i++){
    const d = document.createElement("span");
    d.className = "punkt" + (i === wo ? " an" : "");
    p.appendChild(d);
  }
}

function zeigen(i){
  const s = SPRACHEN[i];
  if(!s) return;
  document.getElementById("sprachname").textContent = s.name;
  // NUR der Text dreht sich. Kaesten, Symbole und Farben bleiben, wo
  // sie sind -- sonst stimmt kein Hinweis mehr, den jemand vorn gibt.
  for(const feld of FELDER){
    const el = document.getElementById(feld);
    if(!el) continue;
    el.textContent = s[feld] || "";
    el.lang = s.code;
    el.dir = s.rtl ? "rtl" : "ltr";
  }
  const n = document.getElementById("sprachname");
  n.lang = s.code; n.dir = s.rtl ? "rtl" : "ltr";
  punkteBauen();
}

// Mit einem Anker startet der Durchlauf bei dieser Sprache:
// /qr#fa zeigt sofort Farsi. Zum Nachsehen vor dem Gottesdienst --
// und damit sich jede Sprache pruefen laesst, ohne zu warten.
const gewuenscht = decodeURIComponent((location.hash || "").slice(1));
const start = SPRACHEN.findIndex(s => s.code === gewuenscht);
wo = start < 0 ? 0 : start;
zeigen(wo);
if(SPRACHEN.length > 1){
  // Acht Sekunden: lang genug, um drei kurze Saetze zu lesen, kurz
  // genug, dass niemand denkt, die Seite haenge.
  setInterval(() => { wo = (wo + 1) % SPRACHEN.length; zeigen(wo); }, 8000);
}
</script>
</html>"""


PULT = """<!doctype html><html lang=de><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Pult</title>
<style>
 body{font:16px/1.6 Georgia,serif;margin:0;background:#f3f4f6;color:#141f52;
      display:grid;place-items:start center;min-height:100vh;padding:2rem 1rem}
 .k{background:#fff;border:1px solid #d9dce4;padding:1.8rem;width:min(92vw,34rem)}
 h1{font-size:1.3rem;font-weight:400;letter-spacing:.06em;margin:0 0 1.2rem}
 /* Faellt still weg, wenn kein Logo im Ordner liegt: eine kaputte
    Bildmarke sieht schlimmer aus als gar keine.
    Hiess frueher .marke wie die rote Schwellenmarke des Pegelbalkens.
    Das Logo bekam dadurch deren Aussehen und wurde zu einem roten
    Strich in der Ecke. */
 .logo{height:2.1rem;width:auto;display:block;margin:0 0 .7rem;opacity:.9}
 .lage{display:flex;align-items:center;gap:.6rem;margin:0 0 1.2rem;
       font:.85rem/1.4 system-ui,sans-serif;color:#6b7385}
 .punkt{width:9px;height:9px;border-radius:50%;background:#d9dce4}
 .punkt.an{background:#1fa5d8}
 button{font:1rem Georgia,serif;letter-spacing:.06em;padding:.9rem;border:0;
        cursor:pointer;color:#fff;width:100%;margin-bottom:.5rem}
 /* Meldungen aus dem Saal duerfen nicht untergehen: sie kommen selten,
    und wenn, dann meist waehrend etwas laeuft. Deshalb ueber dem
    Hauptknopf und mit einer kleinen Bewegung, die aufhoert, sobald man
    hinsieht. */
 /* Der Kaefer sitzt neben dem Zahnrad: sichtbar, aber nicht bei den
    Betriebsknoepfen. Wer im Gottesdienst einen Fehler bemerkt, soll
    ihn finden, ohne zu suchen -- und niemand soll versehentlich
    daraufkommen statt auf Start. */
 #kaefer{background:none;border:0;color:#6b7385;cursor:pointer;
   padding:.25rem .35rem;line-height:0}
 #kaefer:hover{color:#c0392b}
 .betreuer{margin:.6rem 0 1rem;font-size:1.05rem}
 .betreuer code{font-size:.95rem;color:#1c3a8f}
 .qrpaar{display:flex;gap:1.4rem;flex-wrap:wrap;margin:.4rem 0 1rem}
 .qrpaar img{border:1px solid #d9dce4;border-radius:4px;background:#fff}
 .qrpaar>div{max-width:210px}
 .briefkasten{background:#1fa5d8;display:flex;align-items:center;
   justify-content:center;gap:.6rem;font-size:1rem}
 /* Ohne das gewinnt display:flex gegen das hidden-Attribut, und der
    Briefkasten stand mit einer Null darin da. */
 [hidden]{display:none !important}
 .briefkasten .umschlag{font-size:1.3rem;display:inline-block}
 /* Ein kleines Zeichen, das wackelt, sieht im Betrieb niemand. Auffallen
    muss die ganze Flaeche, sonst bleibt die Meldung liegen. */
 @media (prefers-reduced-motion: no-preference){
   .briefkasten{animation:pochen 1.8s ease-in-out infinite}
   .briefkasten .umschlag{animation:wackeln 1.8s ease-in-out infinite}
 }
 @keyframes pochen{0%,100%{background:#1fa5d8}
   50%{background:#0d7fab;box-shadow:0 0 0 3px rgba(31,165,216,.35)}}
 @keyframes wackeln{0%,70%,100%{transform:rotate(0)}
   78%{transform:rotate(-14deg)}86%{transform:rotate(12deg)}
   93%{transform:rotate(-6deg)}}
 #postzahl{background:#fff;color:#1c3a8f;border-radius:999px;
   min-width:1.4rem;padding:.05rem .35rem;font:600 .85rem system-ui,sans-serif}
 .start{background:linear-gradient(100deg,#3b1e73,#1c3a8f 52%,#1fa5d8)}
 .pause{background:#141f52}
 button:disabled{opacity:.4;cursor:default}
 /* Gleiche Groesse wie die anderen, aber zurueckgenommen: es ist eine
    Handlung wie die uebrigen, nur eine seltenere. Als blosser Text sah
    sie verloren aus. */
 .reset{background:none;color:#6b7385;border:1px solid #d9dce4}
 .reset:hover{border-color:#9aa3b2;color:#141f52}
 /* Zuklappbar, weil dieser Teil vor dem Gottesdienst gebraucht wird und
    waehrenddessen nur Platz kostet. */
 h2.klapp{display:flex;justify-content:space-between;align-items:center;
   cursor:pointer;user-select:none}
 h2.klapp:hover{color:#1c3a8f}
 /* Wort statt bloss eines Pfeils: ein Dreieck allein sagt nicht, was
    passiert, wenn man darauf drueckt. */
 .klapptext{display:inline-flex;align-items:center;gap:.35rem;
   font:.72rem system-ui,sans-serif;text-transform:none;letter-spacing:0;
   color:#8b93a3;font-weight:400}
 h2.klapp:hover .klapptext{color:#1c3a8f}
 .pfeil{font-size:.9rem;transition:transform .18s ease}
 .pfeil.zu{transform:rotate(-90deg)}
 h2{font:.8rem system-ui,sans-serif;text-transform:uppercase;
    letter-spacing:.1em;color:#6b7385;margin:1.8rem 0 .6rem;font-weight:600}
 /* Pegel: der Balken zeigt den Ist-Pegel, die Marke die Schwelle.
    Was links der Marke bleibt, wird nicht uebersetzt. */
 .balken{position:relative;height:26px;background:#eceef2;overflow:hidden}
 /* Drei Zustaende, die man ohne Zahlen unterscheiden kann:
    grau  = nur Raumgeraeusch, nichts geht verloren
    rot   = hoerbar, aber unter der Schwelle: genau das wird weggeworfen
    blau  = wird uebersetzt
    Der rote Bereich ist der einzige, bei dem der Techniker handeln muss,
    und er soll ihn sehen, ohne den Zahlenwert zu lesen. */
 .fuell{height:100%;width:0;background:#9aa3b2;
   transition:width .08s linear, background .2s ease}
 .fuell.knapp{background:linear-gradient(90deg,#a8737b,#c0392b)}
 .fuell.ueber{background:linear-gradient(90deg,#1c3a8f,#1fa5d8)}
 .marke{position:absolute;top:-3px;bottom:-3px;width:2px;background:#c0392b}
 .marke::after{content:"";position:absolute;top:-4px;left:-4px;
               border:5px solid transparent;border-top-color:#c0392b}
 /* Der Balken faellt nur auf, wenn etwas nicht stimmt. Im Normalbetrieb
    bleibt er unsichtbar, damit er nicht zur Tapete wird und im Ernstfall
    uebersehen wird. */
 /* Ueber das hidden-Attribut gesteuert, nicht ueber eine zweite Klasse:
    "warnung warnung" traf frueher versehentlich die Regel fuer die gelbe
    Stufe, und der Balken stand leer da. Was leer ist, wird versteckt. */
 .warnung{margin:1rem 0 0;padding:.7rem .9rem;
   font:.9rem/1.45 system-ui,sans-serif;border-left:4px solid;
   background:#fdf6e3;border-color:#c8991f;color:#7a5c12}
 .warnung.schwer{background:#fdeeec;border-color:#c0392b;color:#8c2f22}
 @keyframes puls{0%,100%{opacity:1}50%{opacity:.55}}
 @media (prefers-reduced-motion: no-preference){
   .warnung.alarm{animation:puls 1.6s ease-in-out infinite}
 }
 .werte{display:flex;justify-content:space-between;
        font:.75rem system-ui,sans-serif;color:#6b7385;margin:.35rem 0 .7rem;
        font-variant-numeric:tabular-nums}
 input[type=range]{width:100%;margin:.2rem 0 .5rem}
 select{width:100%;font:.9rem system-ui,sans-serif;padding:.5rem;
         border:1px solid #d9dce4;background:#fff;margin-bottom:.3rem}
 /* Auswahlfeld und Pegel nebeneinander: waehlen, hineinsprechen,
    Ausschlag sehen -- ohne den Blick an eine andere Stelle zu nehmen.
    Bricht auf schmalen Schirmen um, das Pult steht auch mal auf einem
    Tablet. */
 .tonreihe{display:flex;gap:.6rem;align-items:center;flex-wrap:wrap}
 .tonreihe select{flex:1 1 14rem;margin-bottom:0}
 .tonreihe .balken{flex:1 1 8rem}
 /* Kanalliste: eine Zeile je Eingang, Name links, Pegelbalken rechts.
    Die Zeile ist der Knopf -- wer den Kanal gefunden hat, drueckt genau
    dorthin, wo er gerade hingesehen hat. */
 .kanal{display:flex;align-items:center;gap:.6rem;width:100%;
   padding:.5rem .6rem;margin-bottom:.25rem;border:1px solid #d9dce4;
   background:#fff;cursor:pointer;text-align:left;
   font:.85rem system-ui,sans-serif;color:#141f52}
 .kanal:hover{border-color:#1c3a8f}
 .kanal.an{border-color:#141f52;box-shadow:inset 0 0 0 1px #141f52}
 /* Nicht messbar heisst nicht unsichtbar: die Zeile bleibt stehen, damit
    die Liste zwischen zwei Umlaeufen nicht springt und niemand daneben
    drueckt. */
 .kanal.ruht{opacity:.55;cursor:default}
 .kanal .kname{flex:1 1 10rem;min-width:0;overflow:hidden;
   text-overflow:ellipsis;white-space:nowrap}
 .kanal .kkanal{flex:0 0 auto;font-variant-numeric:tabular-nums;
   color:#6b7385;font-size:.78rem}
 .kanal .balken{flex:1 1 6rem;height:14px}
 .kanal .kwort{flex:0 0 5.5rem;text-align:right;font-size:.75rem;
   color:#6b7385}
 /* Das Ergebnis der Sprachpruefung. Der gehoerte Text steht gross, das
    Urteil klein daneben -- und zwar in dieser Rangfolge, weil der Text
    die Frage beantwortet und das Urteil sie nur zusammenfasst. Wer
    "Liebe Gemeinde, wir lesen heute" liest, weiss Bescheid; wer ein
    Haekchen mit "Sprache" liest, glaubt einer Maschine, die auf einer
    Orgel schon ganze Andachtssaetze erfunden hat. */
 .kanal .kurteil{flex:0 0 100%;padding-left:.1rem;margin-top:.15rem}
 .kanal .ktext{display:block;font-size:.92rem;color:#141f52;
   line-height:1.35}
 .kanal .kmarke{display:block;font-size:.72rem;color:#8b92a1;
   margin-top:.1rem;font-variant-numeric:tabular-nums}
 /* Die gelbe Zeile fuer eine gespeicherte Quelle, die es nicht mehr
    gibt. Sie steht oben und nicht unten: sie ist der Grund, warum der
    Techniker ueberhaupt hier ist. */
 .kanal.vermisst{background:#fdf6e3;border-color:#c8991f;color:#7a5c12;
   cursor:default;display:block}
 .zielliste{display:flex;flex-wrap:wrap;gap:.4rem;margin:.2rem 0 .3rem}
 .zielliste label{display:inline-flex;align-items:center;gap:.35rem;
   margin:0;padding:.35rem .6rem;border:1px solid #d9dce4;cursor:pointer;
   font:.85rem system-ui,sans-serif;color:#141f52}
 .zielliste label.an{background:#141f52;color:#fff;border-color:#141f52}
 .zielliste input{margin:0}
 /* Fehlende Stimme sichtbar machen, nicht nur abschwaechen. Eine
    Kachel mit 75 Prozent Deckkraft sieht aus wie ein Darstellungsfehler;
    wer sie anklickt, erfaehrt erst im Gottesdienst, dass kein Ton
    kommt. */
 .zielliste .ohneton{border-style:dotted;border-color:#b45309}
 .zielliste .ohneton .nurtext{font-size:.72rem;color:#b45309;
   white-space:nowrap}
 .zielliste .ohneton.an{border-color:#b45309;border-style:solid}
 .zielliste .ohneton.an .nurtext{color:#fbbf24}
 /* Der ganze Block ist zurueckgenommen, nicht die einzelne Kachel: so
    sieht man auf einen Blick, wo die geprueften aufhoeren. */
 .zielliste.ungeprueft label{border-style:dashed;color:#6b7385}
 /* Gar kein Glossar sieht anders aus als ein ungeprueftes: gepunktet
    statt gestrichelt. Der Unterschied muss auf den ersten Blick da
    sein, sonst haette die Trennung keinen Zweck. */
 .zielliste.ohneglossar label{border-style:dotted}
 .experiment{display:block;font:.68rem system-ui,sans-serif;
   opacity:.85;margin-top:.15rem}
 .post .systempost{border-left:3px solid #1c3a8f;background:#f3f6fd}
 .post .systempost .wann{color:#1c3a8f;font-weight:600}
 .zielliste.ungeprueft label.an{color:#fff;border-style:solid}
 .untertitel{margin:.5rem 0 .2rem;font-style:italic}
 /* Der Betrieb steht vorn, die Einrichtung dahinter. Was einmal je
    Gemeinde eingestellt wird, soll am Sonntag nicht im Weg stehen. */
 .kopfknoepfe{position:absolute;top:1.3rem;right:1.4rem;display:flex;gap:.4rem}
 .kopfknoepfe button{background:none;border:1px solid #d9dce4;color:#6b7385;
   width:auto;padding:.25rem .6rem;font:.75rem system-ui,sans-serif;
   letter-spacing:.06em;margin:0;line-height:1.4}
 #zahnrad{font-size:1rem;padding:.1rem .5rem}
 /* Der Weg zum Beamerbild soll nicht davon abhaengen, dass jemand eine
    Adresse im Kopf hat. Ein Knopf, ein neues Fenster, Vollbild. */
 #qrknopf{font-weight:600;letter-spacing:.1em}
 #zahnrad.an{background:#141f52;color:#fff;border-color:#141f52}
 #einrichtung>h2:first-of-type{margin-top:.6rem}
 .k{position:relative}
 input[type=text]{font:.9rem system-ui,sans-serif;padding:.5rem;
                  border:1px solid #d9dce4}
 a{color:#1c3a8f}
 input[type=file]{width:100%;font:.85rem system-ui,sans-serif;
                  padding:.5rem;border:1px dashed #d9dce4;background:#fbfcfd}
 .reihe{display:flex;gap:.5rem}
 .reihe button{margin:0}
 .klein{background:#141f52;font-size:.85rem;padding:.55rem}
 .aus{background:#eceef2;color:#6b7385}
 label{display:block;font:.85rem system-ui,sans-serif;color:#6b7385;
       margin:1.4rem 0 .3rem}
 textarea{width:100%;font:.9rem system-ui,sans-serif;padding:.6rem;
          border:1px solid #d9dce4;min-height:4.5rem;resize:vertical}
 table{width:100%;border-collapse:collapse;margin:1.2rem 0 0;
       font:.9rem system-ui,sans-serif}
 td{padding:.45rem 0;border-top:1px solid #d9dce4}
 td:last-child{text-align:right;font-variant-numeric:tabular-nums}
 /* Meldungen aus dem Saal stehen deutlicher da als der Verlauf: sie
    verlangen eine Entscheidung, der Verlauf nur einen Blick. */
 .post{font:.9rem/1.5 system-ui,sans-serif;margin:.2rem 0 .6rem}
 .post div{padding:.5rem .7rem;margin-bottom:.35rem;background:#eef4fb;
   border-left:3px solid #1fa5d8;color:#141f52}
 .post .wann{color:#6b7385;font-size:.78rem;margin-right:.4rem}
 .mit{font:.8rem/1.5 system-ui,sans-serif;color:#6b7385;margin:1rem 0 0;
      max-height:11rem;overflow:auto}
 .mit div{padding:.25rem 0;border-top:1px solid #eef0f4}
 .hin{font:.8rem/1.5 system-ui,sans-serif;color:#6b7385;margin:1.2rem 0 0}
</style>
<div class=k>
<div class=kopfknoepfe>
  <button id=qrknopf onclick=qrOeffnen() title="QR-Seite für den Beamer">
    QR</button>
  <button id=kaefer onclick=fehlerZeigen() title="Fehler melden"
          aria-label="Fehler melden"><svg viewBox="0 0 24 24" width="17"
    height="17" fill="none" stroke="currentColor" stroke-width="1.7"
    stroke-linecap="round"><ellipse cx="12" cy="13.5" rx="4.6" ry="5.8"/>
    <path d="M12 7.7V19.3M7.4 13.5H2.8M16.6 13.5h4.6M8 9.4 4.6 6.6M16 9.4l3.4-2.8M8 17.8l-3.4 2.6M16 17.8l3.4 2.6"/>
    <path d="M9.3 8.1a3.2 3.2 0 0 1 5.4 0"/></svg></button>
  <button id=zahnrad onclick=einrichtungZeigen() title="Einrichtung">⚙</button>
  <button id=sprachknopf onclick=uiSprache()>EN</button>
</div>
<img class=logo src="/logo.png" alt="" onerror="this.remove()">
<h1 data-t=pult>Pult</h1>
<p class=lage><span class=punkt id=punkt></span><span id=lage>…</span></p>
<div id=betrieb>
<p class="warnung schwer" id=rechenwarnung hidden></p>
<p class=warnung id=updatehin hidden></p>
<p class="warnung schwer" id=tonhin hidden></p>
<p class="warnung schwer" id=zweiterdhcp hidden></p>
<button class=briefkasten id=briefkasten onclick=postZeigen() hidden>
  <span class=umschlag>✉</span><span id=postzahl></span>
  <span data-t=post_neu>neue Meldungen aus dem Saal</span></button>
<button class=start id=bStart onclick=umschalten()>Übersetzung starten</button>
<p class=hin id=anhaltenHin data-t=anhalten_hin hidden>Anhalten stoppt die Auslieferung, ohne die
Zuhörer zu trennen. Sie bleiben verbunden und hören weiter, sobald es
weitergeht.</p>
<button class=reset onclick=s('reset')>Von vorn</button>
<p class=hin data-t=qr_hin>Mit <b>QR</b> oben rechts öffnet sich die Seite
für den Beamer. Dort scannen die Zuhörer sich selbst ein.</p>



<p class=warnung id=warnung hidden></p>
<h2 data-t=lautstaerke>Mindestlautstärke</h2>
<div class=balken>
  <div class=fuell id=fuell></div>
  <div class=marke id=marke style=left:0></div>
</div>
<div class=werte>
  <span id=pegelwert>–</span>
  <span id=schwellwert>–</span>
</div>
<input type=range id=regler min=0 max=100 value=30 oninput=schieben()>
<button class=klein id=bEinmessen onclick=einmessen()>Einmessen: Prediger
sprechen lassen</button>
<div class=reihe>
  <button class=klein id=bFest onclick=festnageln()>Regler festnageln</button>
  <button class="klein aus" id=bAuto onclick=automatisch()>Mitlaufend</button>
</div>
<p class=hin>Am einfachsten ist das Einmessen: draufdrücken, den Prediger
zwölf Sekunden normal sprechen lassen, fertig. Der Regler daneben ist für
Nachjustierung von Hand. Alles unterhalb der Marke wird gar nicht erst
übersetzt.</p>

<h2 class=klapp id=vorbereitungKopf onclick=vorbereitungKlappen()>
  <span data-t=vorbereitung>Vor dem Gottesdienst</span>
  <span class=klapptext><span id=vorbereitungWort>Zuklappen</span>
  <span class=pfeil id=vorbereitungPfeil>▾</span></span></h2>
<div id=vorbereitung>
<label for=kontext data-t=kontext>Thema und Bibelstellen</label>
<textarea id=kontext placeholder="Predigt über Vergebung. Texte: Matthäus 18, Psalm 32. Namen: Petrus, Nathan."></textarea>
<button class=klein onclick=k()>Übernehmen</button>
<p class=hin id=erkannt></p>

<label data-t=manuskript>Predigtmanuskript</label>
<p class=hin>Falls der Prediger eines hat. Es wird <b>nicht vorgelesen</b>,
sondern nur nach Namen durchsucht: Orte, Personen, Fremdwörter. Gesprochen
wird, was gesprochen wird.</p>
<input type=file id=datei accept=".txt,.md,.docx" onchange=hochladen()>
<p class=hin id=skriptinfo></p>



</div>

<h2 data-t=mitschnitt>Mitschnitt</h2>
<button class=klein id=bSchnitt onclick=schnitt()>Aufnahme starten</button>
<p class=hin id=schnittinfo>Nimmt den Ton mit, der ohnehin durchläuft. Ersetzt
die Aufnahme auf den USB-Stick, die am Mischpult nicht mehr geht, solange der
Rechner per USB angeschlossen ist.</p>



<h2 data-t=zuhoerer_ueber>Zuhörer je Sprache</h2>
<table><tbody id=zahlen></tbody></table>
<div class=mit id=mit></div>

</div>

<div id=post hidden>
<p class=hin data-t=post_hin>Antworten ist nicht vorgesehen. Wer etwas meldet, weiß das und erwartet keine Rückmeldung.</p>
  <h2 data-t=post_ueber>Aus dem Saal</h2>
  <div class=post id=postliste></div>
  <button class=klein onclick=postLeeren() data-t=post_weg>Erledigt</button>
</div>

<div id=fehler hidden>
<p class=hin data-t=fehler_text>Etwas funktioniert nicht? Schick dem
Betreuer eine Mail.</p>
<p class=betreuer><b id=betreuername></b><br><code id=betreuermail></code></p>

<div class=qrpaar>
  <div><img id=qrmail alt="" width="190" height="190">
    <p class=hin data-t=fehler_qr_mail>Scannen: öffnet auf dem Handy eine
    fertige Mail.</p></div>
  <div><img id=qrbericht alt="" width="190" height="190">
    <p class=hin data-t=fehler_qr_bericht>Scannen: lädt den Fehlerbericht
    aufs Handy, zum Anhängen.</p>
    <p class=hin><code id=berichtklartext></code></p></div>
</div>

<p class="hin" data-t=fehler_offline>Die Mail geht raus, sobald das Handy
wieder Internet hat. Im Saalnetz bleibt sie im Postausgang liegen.</p>

<p><a class=klein id=berichtlink href="/fehlerbericht.txt" download
   data-t=fehler_laden>Fehlerbericht herunterladen</a></p>
<p class=hin data-t=fehler_inhalt>Der Bericht enthält nur technische
Angaben: Fassung, Rechner, Systemcheck, Meldungen ab Warnstufe. Keine
Mitschriften, keine Zuschriften aus dem Saal, kein WLAN-Passwort.</p>
</div>

<div id=einrichtung hidden>
<p class=hin data-t=einrichtung_hin>Einmal je Gemeinde einstellen, danach
bleibt es so.</p>
<p class=hin id=fassung></p>
<p class=hin><a href="/anleitung.pdf" download data-t=anleitung_pult>Bedienungsanleitung als PDF</a></p>
<p class=hin id=updatestand hidden></p>
<button class=klein id=updateknopf onclick=updateJetzt() hidden
        data-t=upd_jetzt>Jetzt einspielen</button>
<p class=hin><label><input type=checkbox id=protokollschalter
  onchange=protokollSetzen()> <span data-t=protokoll_an>Mitschrift im
  Protokoll (nur zur Fehlersuche)</span></label></p>
<p class="hin" id=protokollhin data-t=protokoll_hin>Aus. Der gesprochene
Satz steht dann nicht im Protokoll -- nur seine Länge.</p>
<h2 class=klapp id=tonquelleKopf onclick=tonquelleKlappen()>
  <span data-t=tonquelle>Tonquelle</span>
  <span class=klapptext><span id=tonquelleWort>Zuklappen</span>
  <span class=pfeil id=tonquellePfeil>▾</span></span></h2>
<div id=tonquelleFeld>
<div class=tonreihe>
  <div class=balken><div class=fuell id=tonfuell></div></div>
</div>
<div id=kanalliste></div>
<div class=reihe>
  <button class=klein id=bSprache onclick=spracheKnopf()
          data-t=spr_pruefen>Sprache prüfen</button>
</div>
<p class=hin id=sprachstand></p>
<p class=hin data-t=spr_hin>Was hier steht, ist gehört, nicht bewiesen. Auf
Musik erfindet die Erkennung ganze Sätze. Im Zweifel den Text lesen: steht
dort, was gesprochen wurde, ist es der richtige Kanal.</p>
<p class=hin id=geraetstand></p>
<p class=hin data-t=tonquelle_hin>Jede Zeile ist ein Kanal. Hineinsprechen und
zusehen, welche ausschlägt — gemessen wird reihum, eine Zeile nach der
anderen. „Sprache prüfen“ hört bei jedem Kanal mit Pegel zweimal kurz hin und
zeigt, was es verstanden hat.</p>
</div>

<h2 data-t=sprachen>Sprachen</h2>
<label for=quellwahl data-t=quelle>Gesprochene Sprache</label>
<select id=quellwahl onchange=sprachenSetzen()></select>
<label data-t=ziele>Übersetzt nach</label>
<div id=zielwahl></div>
<p class=hin data-t=sprachen_hin>Alle Sprachen liegen auf dem Rechner. Nur die
ausgewählten laufen mit, das spart Rechenzeit. Sprachen ohne Stimme
erscheinen als Untertitel.</p>

<h2 data-t=wlan>WLAN für die Zuhörer</h2>
<p class=hin data-t=netz_wlan_hinweis>Netzname und Passwort werden nur für den
QR-Code gebraucht. Der Zugangspunkt kennt sie selbst.</p>
<div class=reihe>
  <input type=text id=ssid placeholder="Netzname" style="flex:1"
         onchange=wlanSetzen()>
  <input type=text id=wpw placeholder="Passwort" style="flex:1"
         onchange=wlanSetzen()>
</div>
<p class=hin id=wlanstand></p>
<p class=hin data-t=wlan_hin>Netzname und Passwort des Routers, an dem
dieser Rechner hängt. Sie wandern in den ersten QR-Code, damit sich die
Handys mit einem Scan verbinden, ohne dass jemand ein Passwort abtippt.
Ohne Eintrag zeigt die QR-Seite nur den zweiten Code.</p>
<p class=hin><a href="/qr" target="_blank" data-t=qr_oeffnen>QR-Seite für den
Beamer öffnen</a></p>

<h2 data-t=pw_ueber>Pult-Passwort (freiwillig)</h2>
<p class=hin data-t=pw_hin>Ohne Eintrag bleibt alles wie bisher: jeder im
Saal-WLAN kann dieses Pult bedienen. Mit Eintrag wird jedes Gerät im Saal
einmal danach gefragt und merkt sich die Anmeldung. Die Zuhörerseite bleibt
immer offen, und an diesem Rechner wird nie gefragt.</p>
<p class=hin id=pwstand></p>
<div class=reihe>
  <input type=password id=pwfeld placeholder="Passwort" style="flex:1"
    autocomplete="new-password">
  <button class=klein onclick=pultPasswortSetzen()
    data-t=pw_setzen>Übernehmen</button>
</div>
<p class=hin><button class="klein knopf-still" onclick=pultPasswortLoeschen()
  data-t=pw_weg>Passwort entfernen</button></p>
<p class=hin data-t=pw_vergessen>Vergessen? Am Rechner selbst:
<code>python werkzeuge/pult_passwort.py --loeschen</code></p>

</div>
</div>
<script>
// Beschriftungen. Nur Deutsch und Englisch, beide von Hand gepflegt: eine
// maschinell falsch uebersetzte Schaltflaeche ist aergerlicher als eine
// englische, die alle verstehen.
const TEXTE={
 de:{pult:"Pult",sprachen:"Sprachen",quelle:"Gesprochene Sprache",
   tonquelle:"Tonquelle",
   tonquelle_hin:"Jede Zeile ist ein Kanal. Hineinsprechen und zusehen, "
     +"welche ausschlägt — gemessen wird reihum, eine Zeile nach der "
     +"anderen. Geräte mit Ausrufezeichen greifen exklusiv auf den "
     +"Treiber zu und scheitern häufig.",
   ton_still:"still", ton_ruht:"läuft", ton_offen:"noch nicht gemessen",
   ton_unlesbar:"nicht lesbar",
   ton_vermisst:"Gespeicherte Quelle „{name}“ nicht gefunden. "
     +"Bitte neu wählen.",
   ton_testton:"Gemessen wird {name}, nicht die Soundkarte.",
   ton_uebernommen:"Übernommen. Nach dem Start einmal neu einmessen.",
   spr_pruefen:"Sprache prüfen", spr_abbrechen:"Abbrechen",
   spr_laeuft:"Hört hin: {name} …",
   spr_gehoert:"gehört", spr_ton:"kein Sprechen erkannt",
   spr_nichts:"nichts gehört",
   spr_keine:"Kein Kanal zeigt Pegel. Erst hineinsprechen, dann prüfen.",
   spr_hin:"Was hier steht, ist gehört, nicht bewiesen. Auf Musik erfindet "
     +"die Erkennung ganze Sätze. Im Zweifel den Text lesen: steht dort, "
     +"was gesprochen wurde, ist es der richtige Kanal.",
   tonlaeuft:"Nimmt auf, {hz} Hz.",tonaus:"Kein Gerät offen, es kommt "
     +"kein Ton.",tonwechsel:"Wird umgestellt …",
   ziele:"Übersetzt nach",lautstaerke:"Mindestlautstärke",
   mitschnitt:"Mitschnitt",wlan:"WLAN für die Zuhörer",
   manuskript:"Predigtmanuskript",start:"Übersetzung starten",
   pause:"Übersetzung anhalten",reset:"Von vorn",uebernehmen:"Übernehmen",
   einmessen:"Einmessen: Prediger sprechen lassen",
   fest:"Regler festnageln",auto:"Mitlaufend",
   schnittstart:"Aufnahme starten",schnittstop:"Aufnahme beenden",
   laeuft:"läuft",pause_an:"angehalten",segmente:"Segmente",
   hoerer:"Zuhörer",tonda:"Ton kommt an",
   sprachen_hin:"Alle Sprachen liegen auf dem Rechner. Nur die ausgewählten "
     +"laufen mit, das spart Rechenzeit. Sprachen ohne Stimme erscheinen "
     +"als Untertitel.",
   ungeprueft_ueber:"Noch nicht von einem Muttersprachler geprüft. "
     +"Funktionieren, aber die Fachbegriffe stammen unbesehen aus der "
     +"Maschine.",
   nurtext:"nur Text",
   ohnestimme_ueber:"Für diese Sprachen liegt keine Stimme auf dem "
     +"Rechner: sie werden übersetzt und mitgelesen, aber nicht "
     +"gesprochen. Wer sie wählt, bekommt Untertitel ohne Ton.",
   ohnestimme_hilfe:"Stimmen werden bei der Einrichtung geladen und "
     +"brauchen dafür Internet. Hier hat der Rechner keins. Nachholen "
     +"lässt es sich beim nächsten Besuch der Technik.",
   einrichtung:"Einrichtung",
   einrichtung_hin:"Einmal je Gemeinde einstellen, danach bleibt es so.",
   // Meldungen zum Update per USB-Stick. Der Server schickt nur die
   // Lage und die Fassungen, den Satz baut das Pult -- sonst stuende
   // unter englischer Oberflaeche der deutsche Satz aus der Statusdatei.
   // {v} ist die neue Fassung, {alt} die bisherige, {s} die Sprachen
   // ohne Stimme.
   // Tonquelle und Anzeige. Der Server schickt nur die Lage, den Satz
   // baut das Pult -- sonst stuende unter englischer Oberflaeche ein
   // deutscher. Die Einzelheit aus dem Treiber haengt unuebersetzt hinten
   // dran, sie ist meist ohnehin englisch.
   ton_nicht_lokal:"Der Ton kommt nicht vom Mikrofon dieses Rechners "
     +"(--datei).",
   ton_liste_unlesbar:"Die Geräteliste ist nicht lesbar.",
   ton_kein_ton:"Das Gerät läuft nicht, es kommt gerade kein Ton.",
   ton_zurueck:"Das Gerät ließ sich nicht öffnen. Es bleibt beim "
     +"vorherigen.",
   ton_keine_nummer:"Keine Gerätenummer.",
   ton_warte_auf_geraet:"Warte auf {name}. Es wird kein anderes Gerät "
     +"genommen — wählen Sie eines aus, wenn es nicht mehr kommt.",
   ton_neu_geoeffnet:"Der Tonstrom war tot und wurde neu geöffnet.",
   netz_zweiter_dhcp:"ACHTUNG: Ein zweiter DHCP-Server antwortet im Netz. "
     +"Am Zugangspunkt ist DHCP noch eingeschaltet. Handys bekommen dann "
     +"Adressen aus zwei Töpfen und finden diesen Rechner nicht. Am "
     +"Zugangspunkt DHCP ausschalten. Gesehen von: {was}",
   netz_wlan_hinweis:"Netzname und Passwort werden nur für den QR-Code "
     +"gebraucht. Der Zugangspunkt kennt sie selbst. Stimmen sie hier "
     +"nicht mit dem Zugangspunkt überein, enthält der QR-Code ein "
     +"falsches Passwort und niemand kommt ins WLAN.",
   ton_weg:"Der Wechsel kam nicht durch.",
   skript_leer:"Datei ist leer oder unlesbar.",
   server_weg:"Server nicht erreichbar",
   stt_hin:"Die Erkennung scheitert seit {n} Abschnitten: {was}",
   cpu_hin:"Die Erkennung läuft auf der CPU ({was}). Für den Livebetrieb "
     +"ist das zu langsam.",
   upd_jetzt:"Jetzt einspielen",
   upd_wird:"Wird eingespielt, das dauert eine Minute. Der Dienst startet "
     +"dabei neu.",
   upd_kein_update:"Es ist gerade kein Update vorgemerkt.",
   upd_laeuft:"Erst die Übersetzung anhalten, dann einspielen.",
   upd_nicht_schreibbar:"Die Marke ließ sich nicht schreiben. Platte voll "
     +"oder Rechte falsch — im Journal steht, woran es lag.",
   upd_stimmen:" Ohne Stimme, laufen als Untertitel: {s}.",
   upd_bereit:"Update {v} liegt bereit. Es wird eingespielt, wenn 20 Minuten "
     +"nichts läuft und niemand verbunden ist, oder sofort unter "
     +"Einrichtung → Jetzt einspielen.",
   upd_wartet:"Update {v} liegt bereit. Es wird eingespielt, wenn 20 Minuten "
     +"nichts läuft und niemand verbunden ist, oder sofort unter "
     +"Einrichtung → Jetzt einspielen.",
   upd_eingespielt:"Fassung {v} ist eingespielt und läuft.",
   upd_fehlgeschlagen:"Update {v} ist fehlgeschlagen. Fassung {alt} läuft "
     +"weiter.",
   upd_fehlgeschlagen_roh:"Update {v} ist fehlgeschlagen. Es wurde nichts "
     +"verändert.",
   upd_signatur:"Die Signatur des Updates {v} stimmt nicht. Es wird nicht "
     +"eingespielt.",
   upd_nicht_neuer:"Der Stick bringt Fassung {v}, hier läuft schon {alt}. "
     +"Nichts zu tun.",
   upd_schmutzig:"Im Ordner liegen lokale Änderungen. Update {v} wartet, "
     +"bis sie geklärt sind.",
   upd_unvollstaendig:"Der Stick ist unvollständig. Es fehlt das Bundle "
     +"oder das Tag {v}.",
   upd_kein_wheel:"Update {v} braucht Pakete, die nicht auf dem Stick "
     +"liegen. Fassung {alt} läuft weiter.",
   upd_unlesbar:"Auf dem Stick steht eine Datei upd-dev.txt, aber keine "
     +"Fassung darin.",
   upd_mehrdeutig:"Auf dem Stick liegen mehrere Update-Ordner. Es ist nicht "
     +"zu erkennen, welcher gemeint ist – deshalb wird keiner eingespielt. "
     +"Den Stick an einem anderen Rechner leeren, nur den neuen Ordner "
     +"daraufkopieren und noch einmal einstecken.",
   wlan_hin:"Netzname und Passwort des Routers, an dem dieser Rechner hängt. "
     +"Sie wandern in den ersten QR-Code, damit sich die Handys mit einem "
     +"Scan verbinden, ohne dass jemand ein Passwort abtippt. Ohne Eintrag "
     +"zeigt die QR-Seite nur den zweiten Code.",
   qr_oeffnen:"QR-Seite für den Beamer öffnen",
   gespeichert:"Gespeichert.",
   qr_hin:"Mit QR oben rechts öffnet sich die Seite für den Beamer. "
     +"Dort scannen die Zuhörer sich selbst ein.",
   anhalten_hin:"Anhalten stoppt die Auslieferung, ohne die Zuhörer zu "
     +"trennen. Sie bleiben verbunden und hören weiter, sobald es "
     +"weitergeht.",
   zuhoerer_ueber:"Zuhörer je Sprache",
   vorbereitung:"Vor dem Gottesdienst",kontext:"Thema und Bibelstellen",
   zuklappen:"zuklappen",ausklappen:"ausklappen",
   post_ueber:"Aus dem Saal",post_weg:"Erledigt",
   post_neu:"neue Meldungen aus dem Saal",
   post_system:"Hinweis von Devarenu",
   fehler_ueber:"Fehler melden",
   fehler_text:"Etwas funktioniert nicht? Schick dem Betreuer eine Mail.",
   fehler_qr_mail:"Scannen: öffnet auf dem Handy eine fertige Mail.",
   fehler_qr_bericht:"Scannen: lädt den Fehlerbericht aufs Handy, zum "
     +"Anhängen.",
   fehler_offline:"Die Mail geht raus, sobald das Handy wieder Internet "
     +"hat. Im Saalnetz bleibt sie im Postausgang liegen.",
   fehler_laden:"Fehlerbericht herunterladen",
   fehler_inhalt:"Der Bericht enthält nur technische Angaben: Fassung, "
     +"Rechner, Systemcheck, Meldungen ab Warnstufe. Keine Mitschriften, "
     +"keine Zuschriften aus dem Saal, kein WLAN-Passwort.",
   pw_ueber:"Pult-Passwort (freiwillig)",
   pw_hin:"Ohne Eintrag bleibt alles wie bisher: jeder im Saal-WLAN kann "
     +"dieses Pult bedienen. Mit Eintrag wird jedes Gerät im Saal einmal "
     +"danach gefragt und merkt sich die Anmeldung. Die Zuhörerseite bleibt "
     +"immer offen, und an diesem Rechner wird nie gefragt.",
   pw_setzen:"Übernehmen", pw_weg:"Passwort entfernen",
   pw_an:"Gesetzt. Geräte im Saal werden einmal gefragt.",
   pw_aus:"Keines gesetzt. Das Pult ist im Saal für jeden offen.",
   pw_leer:"Erst ein Passwort eintragen.",
   pw_kurz:"Zu kurz. Mindestens vier Zeichen.",
   pw_fehler:"Ließ sich nicht speichern.",
   pw_vergessen:"Vergessen? Am Rechner selbst: "
     +"python werkzeuge/pult_passwort.py --loeschen",
   protokoll_an:"Mitschrift im Protokoll (nur zur Fehlersuche)",
   protokoll_hin:"Aus. Der gesprochene Satz steht dann nicht im "
     +"Protokoll – nur seine Länge.",
   protokoll_warn:"EIN. Der gesprochene Satz steht jetzt im Protokoll. "
     +"Nach der Fehlersuche wieder ausschalten.",
   anleitung_pult:"Bedienungsanleitung als PDF",
   // Drei Zustaende, nicht zwei. Ein Glossar, das niemand gegengelesen
   // hat, ist etwas anderes als gar keines.
   glossar_offen_ueber:"Fachwortverzeichnis vorhanden, aber noch von "
     +"keinem Muttersprachler geprüft. Die Begriffe stehen fest und "
     +"könnten falsch sein.",
   kein_glossar_ueber:"Für diese Sprachen gibt es noch kein "
     +"Fachwortverzeichnis. Begriffe wie Sabbat, Gemeinde oder "
     +"Vereinigung werden wörtlich übersetzt.",
   experimentell:"experimentell, mehr dazu in der Nachricht",
   post_hin:"Antworten ist nicht vorgesehen. Wer etwas meldet, weiß das "
     +"und erwartet keine Rückmeldung."},
 en:{pult:"Control desk",sprachen:"Languages",quelle:"Spoken language",
   tonquelle:"Audio source",
   tonquelle_hin:"Each row is one channel. Speak and watch which one "
     +"moves — they are measured in turn, one row after another. Devices "
     +"marked with an exclamation mark claim the driver exclusively and "
     +"often fail.",
   ton_still:"silent", ton_ruht:"running", ton_offen:"not measured yet",
   ton_unlesbar:"cannot be read",
   ton_vermisst:"Saved source \u201c{name}\u201d not found. "
     +"Please pick a new one.",
   ton_testton:"Measuring {name}, not the sound card.",
   ton_uebernommen:"Saved. Calibrate once after starting.",
   spr_pruefen:"Check for speech", spr_abbrechen:"Cancel",
   spr_laeuft:"Listening: {name} …",
   spr_gehoert:"heard", spr_ton:"no speech recognised",
   spr_nichts:"nothing heard",
   spr_keine:"No channel shows any level. Speak first, then check.",
   spr_hin:"What you see here was heard, not proven. On music the "
     +"recogniser makes up whole sentences. When in doubt, read the text: "
     +"if it matches what was said, this is the right channel.",
   tonlaeuft:"Recording, {hz} Hz.",tonaus:"No device open, no audio "
     +"arriving.",tonwechsel:"Switching …",
   ziele:"Translated into",lautstaerke:"Minimum volume",
   mitschnitt:"Recording",wlan:"Wi-Fi for listeners",
   manuskript:"Sermon manuscript",start:"Start translation",
   pause:"Pause translation",reset:"Start over",uebernehmen:"Apply",
   einmessen:"Calibrate: let the preacher speak",
   fest:"Lock the slider",auto:"Follow the room",
   schnittstart:"Start recording",schnittstop:"Stop recording",
   laeuft:"running",pause_an:"paused",segmente:"segments",
   hoerer:"listeners",tonda:"audio arriving",
   sprachen_hin:"All languages are stored on the computer. Only the selected "
     +"ones run, which saves processing time. Languages without a voice "
     +"appear as subtitles.",
   ungeprueft_ueber:"Not yet reviewed by a native speaker. They work, but "
     +"their technical terms come straight from the machine.",
   nurtext:"text only",
   ohnestimme_ueber:"No voice for these languages is stored on this "
     +"computer: they are translated and can be read along, but not "
     +"spoken. Choosing one gives subtitles without audio.",
   ohnestimme_hilfe:"Voices are downloaded during setup and need an "
     +"internet connection. This computer has none. They can be added "
     +"the next time someone from technical support visits.",
   einrichtung:"Setup",
   einrichtung_hin:"Set once per congregation, then leave it alone.",
   ton_nicht_lokal:"The audio does not come from this computer's "
     +"microphone (--datei).",
   ton_liste_unlesbar:"The device list cannot be read.",
   ton_kein_ton:"The device is not running, no audio is coming in.",
   ton_zurueck:"The device could not be opened. The previous one stays "
     +"in use.",
   ton_keine_nummer:"No device number.",
   ton_warte_auf_geraet:"Waiting for {name}. No other device will be used "
     +"— pick one if it is not coming back.",
   ton_neu_geoeffnet:"The audio stream had died and was reopened.",
   netz_zweiter_dhcp:"WARNING: a second DHCP server is answering on this "
     +"network. The access point still has DHCP switched on. Phones then "
     +"get addresses from two pools and cannot find this computer. Switch "
     +"DHCP off on the access point. Seen from: {was}",
   netz_wlan_hinweis:"Network name and password are only used for the QR "
     +"code. The access point knows them itself. If they do not match the "
     +"access point, the QR code carries a wrong password and nobody gets "
     +"onto the wifi.",
   ton_weg:"The change did not go through.",
   skript_leer:"File is empty or unreadable.",
   server_weg:"Server unreachable",
   stt_hin:"Recognition has been failing for {n} segments: {was}",
   cpu_hin:"Recognition is running on the CPU ({was}). That is too slow "
     +"for live use.",
   upd_jetzt:"Install now",
   upd_wird:"Installing, this takes a minute. The service restarts while "
     +"it does.",
   upd_kein_update:"No update is pending right now.",
   upd_laeuft:"Pause the translation first, then install.",
   upd_nicht_schreibbar:"The marker could not be written. Disk full or "
     +"wrong permissions — the journal says which.",
   upd_stimmen:" No voice, running as subtitles only: {s}.",
   upd_bereit:"Update {v} is ready. It will be installed once nothing has "
     +"run for 20 minutes and nobody is connected, or straight away under "
     +"Setup → Install now.",
   upd_wartet:"Update {v} is ready. It will be installed once nothing has "
     +"run for 20 minutes and nobody is connected, or straight away under "
     +"Setup → Install now.",
   upd_eingespielt:"Version {v} is installed and running.",
   upd_fehlgeschlagen:"Update {v} failed. Version {alt} is still running.",
   upd_fehlgeschlagen_roh:"Update {v} failed. Nothing was changed.",
   upd_signatur:"The signature of update {v} does not check out. It will "
     +"not be installed.",
   upd_nicht_neuer:"The stick carries version {v}, this computer already "
     +"runs {alt}. Nothing to do.",
   upd_schmutzig:"There are local changes in the folder. Update {v} waits "
     +"until they are sorted out.",
   upd_unvollstaendig:"The stick is incomplete. The bundle or the tag {v} "
     +"is missing.",
   upd_kein_wheel:"Update {v} needs packages that are not on the stick. "
     +"Version {alt} keeps running.",
   upd_unlesbar:"The stick has a file upd-dev.txt, but no version in it.",
   upd_mehrdeutig:"The stick holds several update folders. There is no way "
     +"to tell which one is meant, so none is installed. Empty the stick on "
     +"another computer, copy only the new folder onto it and plug it in "
     +"again.",
   wlan_hin:"Network name and password of the router this computer is "
     +"connected to. They go into the first QR code so that phones can join "
     +"with one scan, without anyone typing a password. Without an entry the "
     +"QR page shows only the second code.",
   qr_oeffnen:"Open the QR page for the projector",
   gespeichert:"Saved.",
   qr_hin:"The QR button at the top right opens the page for the projector. "
     +"Listeners scan themselves in from there.",
   anhalten_hin:"Pausing stops delivery without disconnecting listeners. "
     +"They stay connected and continue as soon as it resumes.",
   zuhoerer_ueber:"Listeners per language",
   vorbereitung:"Before the service",kontext:"Topic and Bible passages",
   zuklappen:"collapse",ausklappen:"expand",
   post_ueber:"From the hall",post_weg:"Done",
   post_neu:"new messages from the hall",
   post_system:"Notice from Devarenu",
   fehler_ueber:"Report a problem",
   fehler_text:"Something not working? Send the maintainer an e-mail.",
   fehler_qr_mail:"Scan: opens a prepared e-mail on your phone.",
   fehler_qr_bericht:"Scan: downloads the report to your phone, to "
     +"attach it.",
   fehler_offline:"The e-mail goes out once the phone has internet "
     +"again. On the hall network it stays in the outbox.",
   fehler_laden:"Download the report",
   fehler_inhalt:"The report contains technical details only: version, "
     +"computer, system check, messages at warning level and above. No "
     +"transcripts, no messages from the hall, no wifi password.",
   pw_ueber:"Desk password (optional)",
   pw_hin:"Left empty, nothing changes: anyone on the hall wi-fi can "
     +"operate this desk. Once set, every device in the hall is asked once "
     +"and then remembers. The listener page always stays open, and this "
     +"computer is never asked.",
   pw_setzen:"Apply", pw_weg:"Remove password",
   pw_an:"Set. Devices in the hall are asked once.",
   pw_aus:"Not set. The desk is open to everyone in the hall.",
   pw_leer:"Enter a password first.",
   pw_kurz:"Too short. At least four characters.",
   pw_fehler:"Could not be saved.",
   pw_vergessen:"Forgotten? On the computer itself: "
     +"python werkzeuge/pult_passwort.py --loeschen",
   protokoll_an:"Transcript in the log (for troubleshooting only)",
   protokoll_hin:"Off. The spoken sentence does not go into the log – "
     +"only its length.",
   protokoll_warn:"ON. The spoken sentence now goes into the log. "
     +"Switch it off again after troubleshooting.",
   anleitung_pult:"Manual as PDF",
   glossar_offen_ueber:"A glossary exists, but no native speaker has "
     +"reviewed it yet. The terms are fixed and could be wrong.",
   kein_glossar_ueber:"There is no glossary for these languages yet. "
     +"Terms like Sabbath, church or conference are translated "
     +"literally.",
   experimentell:"experimental, see the message",
   post_hin:"Replying is not provided for. Senders know this and expect "
     +"no answer."}};
let UI=localStorage.getItem("uiSprache")||"de";
let NAMEN={};

function uiZeichnen(){
  const t=TEXTE[UI];
  document.querySelectorAll("[data-t]").forEach(e=>{
    const k=e.dataset.t; if(t[k]) e.textContent=t[k];
  });
  // Die Ueberschrift richtet sich nach der Ansicht, nicht nach data-t.
  document.querySelector("h1").textContent =
    !einrichtung.hidden ? t.einrichtung
    : (!post.hidden ? t.post_ueber : t.pult);
  // Ein Knopf statt zweier: er zeigt immer, was als naechstes passiert,
  // wenn man ihn drueckt. Zwei Knoepfe, von denen einer wirkungslos ist,
  // zwingen zum Nachdenken darueber, in welchem Zustand man gerade ist.
  bStart.textContent = zustandLive ? t.pause : t.start;
  bStart.className = zustandLive ? "pause" : "start";
  // Erklaert, was Anhalten bewirkt. Solange nichts laeuft, erklaert er
  // etwas, das gerade niemanden beschaeftigt.
  anhaltenHin.hidden = !zustandLive;
  vorbereitungWort.textContent = vorbereitung.hidden ? t.ausklappen : t.zuklappen;
  document.querySelector(".reset").textContent=t.reset;
  bFest.textContent=t.fest; bAuto.textContent=t.auto;
  if(!messlauf) bEinmessen.textContent=t.einmessen;
  bSchnitt.textContent=schnittLaeuft?t.schnittstop:t.schnittstart;
  sprachknopf.textContent=UI==="de"?"EN":"DE";
  document.documentElement.lang=UI;
}
async function postLeeren(){
  await fetch("/api/nachrichten/leeren",{method:"POST"});
  lies();
}

function qrOeffnen(){
  // Neues Fenster, damit das Pult offen bleibt: der Techniker braucht
  // beides gleichzeitig, das eine auf dem Beamer, das andere vor sich.
  window.open("/qr", "_blank");
}

function warnungZeigen(text, schwer){
  // Eine Stelle, an der ueber den Balken entschieden wird. Vorher setzten
  // zwei Stellen Klassen, und eine davon schaltete ihn versehentlich ein.
  warnung.textContent = text || "";
  warnung.hidden = !text;
  warnung.classList.toggle("schwer", !!schwer);
}

function vorbereitungKlappen(){
  const zu = vorbereitung.hidden = !vorbereitung.hidden;
  vorbereitungPfeil.classList.toggle("zu", zu);
  vorbereitungWort.textContent = zu ? TEXTE[UI].ausklappen : TEXTE[UI].zuklappen;
  try{ localStorage.setItem("vorbereitungZu", zu ? "1" : ""); }catch(e){}
}

function postZeigen(){
  // Wie die Einrichtung eine eigene Ansicht: Meldungen wollen gelesen
  // werden, nicht zwischen Reglern stehen.
  const zeigen = post.hidden;
  // Beim Oeffnen gilt der Systemhinweis als gelesen. Danach bleibt an
  // der Sprache nur noch die kleine Zeile -- dieselbe Sprache fragt
  // nicht wieder nach.
  if(zeigen) fetch("/api/nachrichten/gelesen",{method:"POST"});
  post.hidden = !zeigen;
  betrieb.hidden = zeigen;
  einrichtung.hidden = true;
  fehler.hidden = true;
  zahnrad.classList.remove("an");
  document.querySelector("h1").textContent =
    zeigen ? TEXTE[UI].post_ueber : TEXTE[UI].pult;
}

function einrichtungZeigen(){
  // Zwei Ansichten statt eines aufklappenden Bereichs: was einmal je
  // Gemeinde eingestellt wird, soll am Sabbat gar nicht erst zwischen den
  // woechentlichen Handgriffen stehen. Nebeneinander wird beides
  // unuebersichtlich.
  const zeigen = einrichtung.hidden;
  einrichtung.hidden = !zeigen;
  post.hidden = true;
  fehler.hidden = true;
  betrieb.hidden = zeigen;
  zahnrad.classList.toggle("an", zeigen);
  document.querySelector("h1").textContent =
    zeigen ? TEXTE[UI].einrichtung : TEXTE[UI].pult;
  // Auch die Geraete: wer waehrend des Betriebs ein Mikrofon einsteckt,
  // soll es finden, ohne die Seite neu zu laden.
  if(zeigen){ sprachenLaden(); wlanLaden(); updateLaden(); }
  // Der Scan macht fremde Geraete auf. Er laeuft nur, solange die
  // Einrichtung offen ist UND der Abschnitt aufgeklappt -- wer zurueck
  // aufs Pult geht, hat ihn damit aus.
  scanSchalten(zeigen && !tonquelleFeld.hidden);
}

function uiSprache(){
  UI=UI==="de"?"en":"de";
  localStorage.setItem("uiSprache",UI);
  uiZeichnen(); lies();
}

async function sprachenSetzen(){
  const ziele=[...document.querySelectorAll("#zielwahl input:checked")]
    .map(x=>x.value);
  await fetch("/api/sprachwahl",{method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({quelle:quellwahl.value,ziele:ziele})});
  await sprachenLaden(); lies();
}
async function sprachenLaden(){
  const d=await(await fetch("/api/sprachen")).json();
  NAMEN={}; d.liste.forEach(x=>NAMEN[x.code]=x.name);
  quellwahl.innerHTML=d.moeglich.map(x=>
    `<option value="${x.code}"${x.code===d.quelle?" selected":""}>`
    +`${x.name}</option>`).join("");
  // Geprüfte oben, ungeprüfte darunter mit eigener Überschrift. Eine
  // gestrichelte Kontur allein geht in einer Liste mit zwanzig Einträgen
  // unter, zumal die aktiven Sprachen gefüllt sind und den Rand verdecken.
  const t = TEXTE[UI];
  // "nur Text" ausgeschrieben und in der Sprache des Pults, nicht als
  // "(Text)": wer die Kachel waehlt, soll vorher wissen, dass daraus
  // kein Ton kommt -- und nicht erst im Gottesdienst.
  const kachel = (x) => {
    const an = d.ziele.includes(x.code);
    return `<label class="${an?"an":""}${x.stimme?"":" ohneton"}">`
      +`<input type=checkbox value="${x.code}"${an?" checked":""} `
      +`onchange="sprachenSetzen()">${x.name}`
      +(x.stimme?"":`<span class=nurtext>${t.nurtext}</span>`)
      // Nur an der EINGESCHALTETEN ungeprueften Sprache, und nur dort:
      // an einer Sprache, die niemand gewaehlt hat, waere es Beiwerk.
      +(an&&!x.geprueft?`<span class=experiment>${t.experimentell}</span>`:"")
      +`</label>`;
  };
  const wahl = d.moeglich.filter(x=>x.code!==d.quelle);
  // Drei Zustaende. Bisher waren es zwei, und "Glossar da, aber
  // ungeprueft" sah aus wie "gar kein Glossar". Das sind verschiedene
  // Dinge: im einen Fall stehen die Begriffe fest und koennten falsch
  // sein, im anderen stehen sie ueberhaupt nicht fest.
  const geprueft = wahl.filter(x=>x.geprueft);
  const offen    = wahl.filter(x=>!x.geprueft && x.glossar);
  const ohne     = wahl.filter(x=>!x.geprueft && !x.glossar);
  zielwahl.innerHTML =
    `<div class=zielliste>${geprueft.map(kachel).join("")}</div>`
    + (offen.length
       ? `<p class="hin untertitel">${t.glossar_offen_ueber}</p>`
         + `<div class="zielliste ungeprueft">${offen.map(kachel).join("")}</div>`
       : "")
    + (ohne.length
       ? `<p class="hin untertitel">${t.kein_glossar_ueber}</p>`
         + `<div class="zielliste ungeprueft ohneglossar">${ohne.map(kachel).join("")}</div>`
       : "")
    // Die Erklaerung nur, wenn es tatsaechlich eine Sprache ohne Stimme
    // gibt. Ein Hinweis, der immer dasteht, wird nicht mehr gelesen.
    + (wahl.some(x=>!x.stimme)
       ? `<p class="hin untertitel">${t.ohnestimme_ueber}<br>`
         + `${t.ohnestimme_hilfe}</p>`
       : "");
}
// Pegel sind logarithmisch wahrnehmbar. Ein linearer Balken zeigt bei
// Sprache fast nichts, deshalb wird auf Dezibel umgerechnet.
const MIN_DB=-60;
const zuProzent=v=>{if(v<=0)return 0;
  const db=20*Math.log10(v);return Math.max(0,Math.min(100,(db-MIN_DB)/MIN_DB*-100))};
const zuWert=pz=>Math.pow(10,((pz/100)*-MIN_DB+MIN_DB)/20);

let handBetrieb=false;
async function s(w){await fetch("/api/steuerung/"+w,{method:"POST"});lies()}
async function umschalten(){
  // Zustand sofort umlegen, nicht erst beim naechsten Abruf: sonst bleibt
  // die Beschriftung bis zu zwei Sekunden lang falsch stehen.
  zustandLive = !zustandLive;
  uiZeichnen();
  await s(zustandLive ? "start" : "pause");
}
async function k(){
  const a=await fetch("/api/kontext",{method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({text:kontext.value})});
  zeigeErkannt(await a.json());
  lies();
}
function zeigeErkannt(d){
  if(!d) return;
  if(!d.stellen||!d.stellen.length){
    erkannt.textContent=kontext.value.trim()
      ? "Keine Bibelstelle erkannt. Schreibweise wie „1. Samuel 15“ oder „Mt 18“."
      : "";
    return;
  }
  erkannt.innerHTML="Erkannt: <b>"+d.stellen.join(", ")+"</b><br>"
    +d.namen.length+" von "+d.gefunden+" Namen im Prompt: "+d.namen.join(", ");
}
function schieben(){handBetrieb=true;marke.style.left=regler.value+"%";
  schwellwert.textContent="Schwelle "+regler.value+" %"}
async function festnageln(){
  await fetch("/api/schwelle",{method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({wert:zuWert(+regler.value)})});
  handBetrieb=false;
}
async function automatisch(){
  await fetch("/api/schwelle",{method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({automatisch:true})});
  handBetrieb=false;
}
let schnittLaeuft=false;
async function schnitt(){
  const a=await fetch("/api/mitschnitt",{method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify(schnittLaeuft?{beenden:true}:{})});
  const d=await a.json();
  if(schnittLaeuft&&d.datei){
    schnittinfo.innerHTML=d.minuten+" Minuten aufgenommen. "
      +'<a href="/mitschnitt/'+encodeURIComponent(d.datei)+'">'+d.datei+"</a>";
  }
}

let zustandLive=false;
let messlauf=false;
async function einmessen(){
  if(messlauf) return;
  messlauf=true;
  await fetch("/api/einmessen",{method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({dauer:12})});
}
async function messungBeenden(){
  const a=await fetch("/api/einmessen",{method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({beenden:true})});
  const d=await a.json();
  messlauf=false;
  bEinmessen.textContent=d.erfolg
    ? "Eingemessen. Nochmal messen"
    : "Einmessen: Prediger sprechen lassen";
  // Frueher stand hier className="warnung warnung", und genau das ist die
  // Regel fuer die gelbe Warnstufe: der Balken ging bei jedem Einmessen an
  // und blieb leer stehen.
  warnungZeigen(d.erfolg ? "" : (d.text || ""), false);
  handBetrieb=false;
}

// ---- Tonquelle: eine Zeile je Kanal -------------------------------
// Der Scan macht fremde Geraete auf. Das darf nur laufen, solange
// jemand hinsieht, deshalb haengt er am Auf- und Zuklappen des
// Abschnitts und nicht am Laden der Seite.
let scanAn=false, kanalZeilen=[], scanUhr=null;

async function scanSchalten(an){
  if(an===scanAn) return;
  scanAn=an;
  try{
    await fetch("/api/tonscan",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({an:an})});
  }catch(e){console.error("Tonscan:", e)}
  if(an){
    kanaeleLaden();
    // Schneller als die uebrige Pult-Abfrage: das Messfenster ist
    // 800 ms, und ein Ausschlag soll waehrend des Hineinsprechens zu
    // sehen sein und nicht danach.
    scanUhr=setInterval(kanaeleLaden,500);
  }else{
    clearInterval(scanUhr); scanUhr=null;
  }
}

function tonquelleKlappen(){
  const zu = tonquelleFeld.hidden = !tonquelleFeld.hidden;
  tonquellePfeil.classList.toggle("zu", zu);
  tonquelleWort.textContent = zu ? TEXTE[UI].ausklappen : TEXTE[UI].zuklappen;
  try{ localStorage.setItem("tonquelleZu", zu ? "1" : ""); }catch(e){}
  scanSchalten(!zu);
}

async function kanaeleLaden(){
  try{
    const d=await(await fetch("/api/tonscan")).json();
    if(!d.aktiv){ kanalliste.innerHTML=""; return; }
    kanalZeilen=d.zeilen||[];
    kanalListeZeichnen(d);
    // Der Knopf macht ein Geraet auf. Waehrend einer Uebersetzung gibt
    // es dafuer keinen Grund, der eine Gemeinde interessiert.
    bSprache.disabled = d.uebersetzung;
    bSprache.textContent = d.pruefung
      ? TEXTE[UI].spr_abbrechen : TEXTE[UI].spr_pruefen;
    if(d.pruefung){
      const z=kanalZeilen.find(k=>k.schluessel===d.pruefung_jetzt);
      sprachstand.textContent = z
        ? TEXTE[UI].spr_laeuft.replace("{name}",
            z.name+" "+z.kanalname) : TEXTE[UI].spr_laeuft.replace("{name}","…");
    }else if(sprachstand.dataset.halten!=="1"){
      sprachstand.textContent="";
    }
  }catch(e){console.error("Kanaele:", e)}
}

function kanalListeZeichnen(d){
  const teile=[];
  if(d.vermisst){
    // Kein Rueckfall auf irgendein Geraet: der Server laeuft angehalten,
    // und hier steht, warum.
    teile.push(`<div class="kanal vermisst">`
      +TEXTE[UI].ton_vermisst.replace("{name}", entschaerfen(d.vermisst))
      +`</div>`);
  }
  if(d.hinweis) teile.push(`<div class="kanal vermisst">`
    +entschaerfen(d.hinweis)+`</div>`);
  if(d.testton) teile.push(`<div class="kanal vermisst">`
    +TEXTE[UI].ton_testton.replace("{name}", entschaerfen(d.testton))+`</div>`);

  for(const z of kanalZeilen){
    const pz = z.pegel===null||z.pegel===undefined ? 0 : zuProzent(z.pegel);
    // Dieselbe Farbregel wie der grosse Balken: grau nur Raum, rot
    // hoerbar aber unter der Schwelle, blau darueber. Eine zweite
    // Farblogik haette geheissen, dass dasselbe Signal an zwei Stellen
    // im Pult verschieden aussieht.
    const ueber = z.pegel > pegelSchwelle;
    const hoerbar = z.pegel > d.rauschgrenze;
    const farbe = "fuell" + (ueber ? " ueber" : (hoerbar ? " knapp" : ""));
    let wort;
    if(z.fehler) wort = TEXTE[UI].ton_unlesbar;
    else if(z.ruht) wort = TEXTE[UI].ton_ruht;
    else if(z.gemessen===null||z.gemessen===undefined) wort = TEXTE[UI].ton_offen;
    // "Still" als Wort und nicht nur als grauer Balken: ein leerer
    // Balken sieht aus wie einer, der noch nicht gemessen wurde.
    else wort = hoerbar ? Math.round(pz)+" %" : TEXTE[UI].ton_still;

    teile.push(`<button class="kanal${z.aktiv?" an":""}${z.ruht?" ruht":""}"`
      +` onclick="kanalSetzen('${entschaerfen(z.schluessel)}')"`
      +`${z.ruht?" disabled":""}>`
      +`<span class=kname>${entschaerfen(z.name)}`
      +`${z.empfohlen?"":" !"}</span>`
      +`<span class=kkanal>${entschaerfen(z.kanalname)}</span>`
      +`<span class=balken><span class="${farbe}" `
      +`style="display:block;height:100%;width:${pz}%"></span></span>`
      +`<span class=kwort>${wort}</span>`
      +(z.sprache ? `<span class=kurteil>${sprachSatz(z.sprache)}</span>` : "")
      +`</button>`);
  }
  kanalliste.innerHTML=teile.join("");
}

// Die Zeilen tragen Geraetenamen, und die kommen aus dem Treiber. Was
// von dort kommt, wird nicht als HTML eingesetzt.
function entschaerfen(t){
  return String(t==null?"":t).replace(/[&<>"']/g,
    c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}

// Die Schwelle aus dem Pegelabruf, damit die Kanalzeilen dieselbe Grenze
// faerben wie der grosse Balken. Bis zum ersten Abruf die Vorgabe.
let pegelSchwelle=0.0025;

// ---- Stufe 2: Sprache pruefen -------------------------------------
async function spracheKnopf(){
  // Derselbe Knopf schaltet an und ab. Zwei nebeneinander waeren einer
  // zu viel: abbrechen kann man nur, was laeuft.
  const an = bSprache.textContent===TEXTE[UI].spr_pruefen;
  sprachstand.dataset.halten="";
  try{
    const a=await fetch("/api/sprachpruefung",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({an:an})});
    const d=await a.json();
    if(an && !d.laeuft && d.lage==="keine_kandidaten"){
      // Der haeufigste Fall, und einer, den man beheben kann: es hat
      // einfach noch niemand ins Mikrofon gesprochen.
      sprachstand.textContent=TEXTE[UI].spr_keine;
      sprachstand.dataset.halten="1";
    }
    kanaeleLaden();
  }catch(e){console.error("Sprachpruefung:", e)}
}

// Das Ergebnis bleibt mit Zeitstempel stehen, bis erneut geprueft wird:
// wer drei Kanaele durchgeht, will den ersten noch sehen, wenn er beim
// dritten ist.
function sprachSatz(u){
  const zeit=new Date(u.zeit*1000).toLocaleTimeString(
    UI==="de"?"de-DE":"en-GB",{hour:"2-digit",minute:"2-digit"});
  // Der gehoerte Text zuerst und gross. Kein Haekchen, kein "Sprache"
  // als Urteilsspruch: die Pruefung sagt, was sie gehoert hat, und der
  // Mensch entscheidet, ob das der Prediger war. Auf einer Orgel hat
  // dasselbe Modell schon "Vertraue und glaube, es hilft, es heilt die
  // goettliche Kraft!" gehoert -- zehn Woerter sauberes Deutsch. Ein
  // Haken davor waere eine Behauptung, die das Programm nicht decken kann.
  let gross="", klein;
  if(u.urteil==="sprache"){
    gross="„"+entschaerfen(u.text||"")+"“";
    // Der Grund steht auch bei "gehoert", wenn es knapp war: zwei von
    // drei Fenstern ist ein Urteil, aber eines, das man sehen soll,
    // bevor man das Geraet uebernimmt.
    klein=TEXTE[UI].spr_gehoert
      +(u.grund?" ("+entschaerfen(u.grund)+")":"");
  }else if(u.urteil==="ton_ohne_sprache"){
    klein=TEXTE[UI].spr_ton+(u.grund?" ("+entschaerfen(u.grund)+")":"");
  }else{
    klein=TEXTE[UI].spr_nichts+(u.grund?" ("+entschaerfen(u.grund)+")":"");
  }
  // Die Rohwerte stehen mit da. Fuer den Techniker sind sie Rauschen,
  // aber die Schwellen dahinter sind neu -- ohne Zahlen liesse sich
  // nach zwei Einsaetzen nicht nachziehen, sondern nur raten.
  const roh=[u.rms!==null&&u.rms!==undefined ? "RMS "+u.rms : "",
             u.avg_logprob!==null&&u.avg_logprob!==undefined
               ? "logp "+u.avg_logprob : ""].filter(Boolean).join(" · ");
  return (gross?'<span class=ktext>'+gross+'</span>':"")
    +'<span class=kmarke>'+klein+" · "+zeit+(roh?" · "+roh:"")+'</span>';
}

async function kanalSetzen(schluessel){
  const z=kanalZeilen.find(k=>k.schluessel===schluessel);
  if(!z) return;
  geraetstand.textContent=TEXTE[UI].tonwechsel;
  try{
    const a=await fetch("/api/geraet",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({nummer:z.nummer, kanal:z.kanal,
                           kanaele:z.kanaele})});
    const d=await a.json();
    if(d.gelungen){
      // Die Schwelle gehoerte der alten Quelle und ist beim Wechsel
      // verworfen worden. Das muss dastehen, sonst geht jemand mit einer
      // mitlaufenden Schwelle in den Gottesdienst und meint, sie sei
      // noch die eingemessene.
      geraetstand.textContent=TEXTE[UI].ton_uebernommen;
      warnungZeigen("", false);
    }else{
      const satz=tonSatz(d);
      geraetstand.textContent=satz;
      warnungZeigen(satz, true);
    }
    kanaeleLaden();
  }catch(e){
    geraetstand.textContent=TEXTE[UI].ton_weg;
    console.error("Kanalwechsel:", e);
  }
}

async function wlanLaden(){
  // Was schon eingetragen ist, soll dastehen: sonst tippt jemand es
  // erneut ein, weil er die Felder leer sieht.
  try{
    const d=await(await fetch("/api/wlan")).json();
    if(!ssid.value) ssid.value=d.ssid||"";
    if(!wpw.value)  wpw.value=d.passwort||"";
    wlanstand.textContent = d.ssid ? TEXTE[UI].gespeichert : "";
  }catch(e){}
}

async function wlanSetzen(){
  // Sofort uebernehmen, so wie die Sprachauswahl daneben. Ein Knopf nur
  // fuer dieses eine Feld hatte zur Folge, dass man Sprachen aenderte und
  // beim Druecken ein leeres WLAN mit uebernahm.
  await fetch("/api/wlan",{method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({ssid:ssid.value,passwort:wpw.value})});
  wlanstand.textContent = ssid.value ? TEXTE[UI].gespeichert : "";
}

// Dasselbe fuer die Tonquelle. Die Einzelheit haengt hinten dran und
// bleibt unuebersetzt: sie kommt aus dem Treiber, ist meist ohnehin
// englisch, und wer damit suchen geht, braucht sie im Wortlaut.
function tonSatz(d){
  if(!d || !d.lage) return "";
  let s = TEXTE[UI]["ton_"+d.lage] || "";
  if(!s) return "";
  s = s.split("{name}").join(d.name || "?");
  return d.einzelheit ? s+" ("+d.einzelheit+")" : s;
}

// Baut aus der Lage einen Satz in der eingestellten Sprache. Der Server
// schickt bewusst keinen fertigen Text: der waere deutsch, auch wenn das
// Pult auf Englisch steht.
function updateSatz(d){
  const t=TEXTE[UI];
  let schluessel="upd_"+(d.lage||"");
  // Zwei Faelle fuer dasselbe Wort: scheitert es nach dem Vorspulen, gibt
  // es eine wiederhergestellte Fassung; scheitert es davor, wurde nichts
  // angefasst, und "Fassung ... laeuft weiter" waere irrefuehrend.
  if(d.lage==="fehlgeschlagen" && !d.vorher) schluessel="upd_fehlgeschlagen_roh";
  let s=t[schluessel];
  if(!s) return "";
  s=s.split("{v}").join(d.version||"?").split("{alt}").join(d.vorher||"?");
  if(d.stimmen) s+=t.upd_stimmen.split("{s}").join(d.stimmen);
  return s;
}

async function updateLaden(){
  try{
    const d=await(await fetch("/api/update")).json();
    const s=updateSatz(d);
    updatestand.hidden=!s;
    if(s) updatestand.textContent=s;
    // Der Knopf nur, wenn er etwas bewirkt: etwas ist vorgemerkt, es
    // wurde noch nicht gedrueckt, und die Uebersetzung laeuft nicht.
    // Waehrend sie laeuft bleibt er sichtbar, aber gesperrt -- sonst
    // sucht jemand einen Knopf, von dem er weiss, dass es ihn gibt.
    updateknopf.hidden = !(d.bereit && !d.gedrueckt);
    updateknopf.disabled = !!d.live;
    updateknopf.title = d.live ? TEXTE[UI].upd_laeuft : "";
  }catch(e){}
}

async function fehlerZeigen(){
  // Wie der Briefkasten eine eigene Ansicht, kein aufspringendes
  // Fenster: am Pult darf im Gottesdienst nichts aufpoppen.
  const zeigen = fehler.hidden;
  fehler.hidden = !zeigen;
  betrieb.hidden = zeigen;
  einrichtung.hidden = true;
  post.hidden = true;
  zahnrad.classList.remove("an");
  document.querySelector("h1").textContent =
    zeigen ? TEXTE[UI].fehler_ueber : TEXTE[UI].pult;
  if(!zeigen) return;
  // Erst beim Oeffnen: die QR-Bilder entstehen im Server neu, und beim
  // Betreuer steht die Adresse aus betreuer.txt.
  try{
    const a = await fetch("/api/betreuer");
    const d = await a.json();
    betreuername.textContent = d.name || "";
    betreuermail.textContent = d.mail || "";
    // Derselbe Link, den der rechte QR traegt -- zum Abtippen, wenn
    // das Scannen nicht klappt. Aelteres Handy, schlechtes Licht.
    berichtklartext.textContent = d.bericht_link || "";
  }catch(e){ /* dann bleibt das Feld leer, der QR geht trotzdem */ }
  const jetzt = Date.now();
  qrmail.src = "/fehler-qr.png?was=mail&t=" + jetzt;
  qrbericht.src = "/fehler-qr.png?was=bericht&t=" + jetzt;
  // Der Download vom Pult aus darf lange dauern -- wer hier klickt,
  // sitzt davor. Das Handy bekommt ueber den QR die schnelle Fassung.
  berichtlink.href = "/fehlerbericht.txt";
}

async function pultPasswortSetzen(){
  const w = pwfeld.value;
  if(!w){ pwstand.textContent = TEXTE[UI].pw_leer; return; }
  const a = await fetch("/api/pult-passwort",{method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({passwort:w})});
  if(!a.ok){
    const d = await a.json().catch(()=>({}));
    pwstand.textContent = d.grund==="zu_kurz"
      ? TEXTE[UI].pw_kurz : TEXTE[UI].pw_fehler;
    return;
  }
  // Nicht stehen lassen: ein Passwort im Feld liest der Nächste mit,
  // der am Pult vorbeikommt.
  pwfeld.value = "";
  pultPasswortAnzeigen(true);
}
async function pultPasswortLoeschen(){
  await fetch("/api/pult-passwort",{method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({passwort:""})});
  pwfeld.value = "";
  pultPasswortAnzeigen(false);
}
function pultPasswortAnzeigen(gesetzt){
  const t = TEXTE[UI];
  pwstand.textContent = gesetzt ? t.pw_an : t.pw_aus;
  pwstand.classList.toggle("warnung", false);
}

async function protokollSetzen(){
  const an = protokollschalter.checked;
  await fetch("/api/protokoll",{method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({an:an})});
  protokollAnzeigen(an);
}
function protokollAnzeigen(an){
  const t = TEXTE[UI];
  protokollschalter.checked = an;
  protokollhin.textContent = an ? t.protokoll_warn : t.protokoll_hin;
  protokollhin.classList.toggle("warnung", an);
}

async function updateJetzt(){
  updateknopf.disabled=true;
  try{
    const a=await fetch("/api/update/jetzt",{method:"POST"});
    const d=await a.json();
    updatestand.hidden=false;
    // Bis zu eine Minute, weil der Timer daneben so oft nachsieht. Das
    // hier zu verschweigen hiesse, dass jemand ein zweites Mal drueckt.
    updatestand.textContent = a.ok ? TEXTE[UI].upd_wird
      : (TEXTE[UI]["upd_"+(d.grund||"")] || TEXTE[UI].upd_kein_update);
    if(a.ok) updateknopf.hidden=true;
  }catch(e){
    updatestand.hidden=false;
    updatestand.textContent=String(e.message||e);
  }finally{
    if(!updateknopf.hidden) updateknopf.disabled=false;
  }
}

async function hochladen(){
  const f=datei.files[0]; if(!f) return;
  skriptinfo.textContent="wird gelesen …";
  const daten=new FormData(); daten.append("datei",f);
  try{
    const a=await fetch("/api/skript",{method:"POST",body:daten});
    const d=await a.json();
    if(d.fehler){skriptinfo.textContent=TEXTE[UI].skript_leer;return}
    skriptinfo.innerHTML=d.woerter+" Wörter gelesen. "
      +(d.stellen.length?"Stellen: <b>"+d.stellen.join(", ")+"</b>. ":"")
      +d.bekannt+" bekannte und "+d.neu+" weitere Namen.<br>"
      +d.namen.join(", ");
    lies();
  }catch(e){skriptinfo.textContent="Hochladen fehlgeschlagen."}
}

async function pegel(){
  try{
    const d=await(await fetch("/api/pegel")).json();
    const pz=zuProzent(d.jetzt), sz=zuProzent(d.schwelle);
    fuell.style.width=pz+"%";
    // Dieselbe Grenze wie bei der Warnung: hoerbar heisst deutlich ueber
    // dem Raumgeraeusch, nicht bloss ueber null.
    const hoerbar = d.jetzt > Math.max(d.grund*2.5, 0.0015);
    fuell.className = "fuell" + (d.jetzt > d.schwelle ? " ueber"
                                 : (hoerbar ? " knapp" : ""));
    // Derselbe Wert, dieselbe Farbe, nur ohne Marke und Regler: der
    // Balken in der Einrichtung dient allein der Frage, ob Ton ankommt.
    tonfuell.style.width=pz+"%";
    tonfuell.className=fuell.className;
    // Dieselbe Schwelle fuer die Kanalzeilen: sonst faerbte dasselbe
    // Signal oben blau und unten rot.
    pegelSchwelle=d.schwelle;
    if(!handBetrieb){marke.style.left=sz+"%";regler.value=Math.round(sz)}
    pegelwert.textContent=(d.spricht?"spricht":"still")+" · "+Math.round(pz)+" %";
    // "knapp darunter" ist der Fall, den man am Regler sofort beheben
    // kann: es wird gesprochen, nur zu leise fuer die Schwelle.
    schwellwert.textContent="Schwelle "+Math.round(sz)+" % · "
      +(d.fest?"fest":"automatisch")
      +(d.verworfen?" · "+d.verworfen+" verworfen":"")
      +(d.knapp>30?" · knapp darunter":"");
    bFest.className="klein"+(d.fest?"":" aus");
    bAuto.className="klein"+(d.fest?" aus":"");
    // Nur zeigen, wenn es auch etwas zu sagen gibt: ein leerer gelber
    // Balken sieht nach Warnung aus und stumpft ab.
    warnungZeigen(d.lage_text && (d.lage==="alarm"||d.lage==="warnung")
      ? (d.lage==="alarm" ? "Achtung: " : "") + d.lage_text : "",
      d.lage==="alarm");
    if(d.einmessen&&d.einmessen.laeuft){
      messlauf=true;
      bEinmessen.textContent="Messe … noch "+d.einmessen.rest+" s, "
        +"jetzt sprechen lassen";
    }else if(messlauf){
      messungBeenden();
    }
  }catch(e){
    // Frueher stand hier ein leeres catch. Das hat einen Zugriffsfehler
    // still verschluckt, den es seit Wochen gab: die Knopf-IDs hatten
    // Bindestriche, und dafuer legt der Browser keine gleichnamige
    // Variable an. Ein Fehler, den niemand sieht, wird nicht behoben.
    console.error("Pegel:", e);
  }
}
async function lies(){
  // Abruf und Verarbeitung getrennt: vorher fing ein einziges catch beides
  // ab und meldete "Server nicht erreichbar", auch wenn der Server
  // einwandfrei antwortete und nur ein Fehler in der Anzeige steckte. Die
  // Fehlersuche lief damit in die falsche Richtung.
  let d;
  try{
    const a = await fetch("/api/zustand");
    if(!a.ok) throw new Error("HTTP " + a.status);
    d = await a.json();
  }catch(e){
    lage.textContent = TEXTE[UI].server_weg + " (" + e.message + ")";
    return;
  }
  try{
    const t=TEXTE[UI];
    punkt.className="punkt"+(d.live?" an":"");
    // Eigene Zeile und nicht die Pegelwarnung: die wird zehnmal je
    // Sekunde neu gesetzt und wuerde diese hier ueberschreiben.
    // Aus der Ferne die erste Frage: was laeuft hier eigentlich?
    fassung.textContent = "Devarenu " + (d.fassung||"?") + " · " + (d.rechenwerk||"?");
    const cpu = (d.rechenwerk||"").startsWith("cpu");
    // Der Fehler zuerst: laeuft die Erkennung gar nicht, ist es
    // zweitrangig, worauf sie nicht laeuft.
    if(d.stt_fehler){
      rechenwarnung.hidden = false;
      rechenwarnung.textContent = TEXTE[UI].stt_hin
        .split("{n}").join(d.stt_fehler.anzahl)
        .split("{was}").join(d.stt_fehler.text);
    }else if(cpu){
      rechenwarnung.hidden = false;
      rechenwarnung.textContent =
        TEXTE[UI].cpu_hin.split("{was}").join(d.rechenwerk);
    }else{
      rechenwarnung.hidden = true;
    }
    // Ein wartendes Update gehoert in die Betriebsansicht, nicht nur
    // unter Einrichtung: waehrend des Gottesdienstes hat niemand die
    // Einrichtung offen. Eingespielt und fehlgeschlagen stehen dort,
    // hier steht nur, was noch bevorsteht -- der Server entscheidet das.
    // Ein zweiter DHCP-Server ist kein Hinweis, sondern der Grund,
    // warum die Haelfte der Handys nichts hoert.
    const fremd = (d.netz && d.netz.fremde_adressen) || [];
    zweiterdhcp.hidden = !fremd.length;
    if(fremd.length)
      zweiterdhcp.textContent =
        t.netz_zweiter_dhcp.split("{was}").join(fremd.join(", "));
    const uSatz = d.update ? updateSatz(d.update) : "";
    updatehin.hidden = !uSatz;
    if(uSatz) updatehin.textContent = uSatz;
    // Schwer und nicht gelb: wer auf sein Mikrofon wartet, hat gerade
    // keinen Ton. Das ist kein Hinweis, das ist der Ausfall selbst.
    const tSatz = tonSatz(d.ton);
    tonhin.hidden = !tSatz;
    if(tSatz) tonhin.textContent = tSatz;
    const quelle = (d.audio_quelle!==undefined && d.audio_quelle!==null)
      ? " · "+t.tonda : "";
    if(zustandLive!==d.live){ zustandLive=d.live; uiZeichnen(); }
    lage.textContent=(d.live?t.laeuft:t.pause_an)+" · "+d.gesendet
      +" "+t.segmente+" · "+d.gesamt+" "+t.hoerer+quelle;
    zahlen.innerHTML=Object.entries(d.hoerer||{}).map(([a,b])=>
      `<tr><td>${NAMEN[a]||a}</td><td>${b}</td></tr>`).join("");
    if(d.mitschnitt){
      schnittLaeuft=true;
      bSchnitt.textContent=t.schnittstop;
      schnittinfo.textContent=d.mitschnitt.minuten+" Minuten · "
        +d.mitschnitt.datei;
    }else if(schnittLaeuft){
      schnittLaeuft=false;
      bSchnitt.textContent=t.schnittstart;
    }
    if(d.protokoll_mitschrift!==undefined)
      protokollAnzeigen(d.protokoll_mitschrift);
    if(d.pult_passwort!==undefined) pultPasswortAnzeigen(d.pult_passwort);
    const post_=(d.nachrichten||[]);
    briefkasten.hidden = post_.length===0;
    postzahl.textContent = post_.length;
    // Steht ein Systemhinweis darin, heisst der Knopf anders: "neue
    // Meldungen aus dem Saal" waere schlicht falsch.
    const sys_ = post_.some(x=>x.art==="system");
    const knopftext = briefkasten.querySelector("[data-t=post_neu]");
    if(knopftext) knopftext.textContent =
      sys_ ? TEXTE[UI].post_system : TEXTE[UI].post_neu;
    if(post_.length===0 && !post.hidden){ postZeigen(); }
    postliste.innerHTML = post_.slice().reverse().map(x=>{
      const roh = (UI==="en" && x.text_en) ? x.text_en : x.text;
      const sicher = roh.replace(/[<>&]/g,
        c=>({"<":"&lt;",">":"&gt;","&":"&amp;"}[c]));
      // Ein Systemhinweis darf nicht aussehen wie eine Zuschrift aus
      // dem Saal. Wer die verwechselt, sucht den Absender im Saal.
      if(x.art==="system"){
        return `<div class=systempost><span class=wann>⚙ `
          +`${x.absender||"Devarenu"} · ${x.zeit}</span>${sicher}</div>`;
      }
      return `<div><span class=wann>${x.zeit}`
        +`${x.sprache?" · "+x.sprache:""}</span>${sicher}</div>`;
    }).join("");
    mit.innerHTML=(d.letzte||[]).slice().reverse().map(x=>
      `<div>${x.gesamt}s &nbsp; ${x.deutsch}</div>`).join("");
    if(d.stellen&&d.stellen.length&&!erkannt.innerHTML)
      zeigeErkannt({stellen:d.stellen,namen:d.namen||[],
                    gefunden:(d.namen||[]).length});
  }catch(e){
    lage.textContent = "Anzeigefehler: " + e.message;
    console.error(e);
  }
}
try{
  if(localStorage.getItem("vorbereitungZu")){
    vorbereitung.hidden = true;
    vorbereitungPfeil.classList.add("zu");
    vorbereitungWort.textContent = TEXTE[UI].ausklappen;
  }
}catch(e){}
try{
  if(localStorage.getItem("tonquelleZu")){
    tonquelleFeld.hidden = true;
    tonquellePfeil.classList.add("zu");
    tonquelleWort.textContent = TEXTE[UI].ausklappen;
  }
}catch(e){}
sprachenLaden().then(uiZeichnen);
lies();setInterval(lies,2000);
pegel();setInterval(pegel,150);
</script></html>"""


# ================================================================

def ollama_abwarten(frist=90.0):
    """Wartet, bis Ollama antwortet. Gibt zurueck, ob es soweit ist.

    Im Systemdienst reicht After=ollama.service nicht: systemd haelt eine
    Type=simple-Unit fuer gestartet, sobald der Prozess exec\'t ist, nicht
    wenn die Schnittstelle antwortet. Ohne dieses Warten scheitert nach
    dem Einschalten die erste Uebersetzung -- also die im Gottesdienst.

    Laeuft die Frist ab, geht es trotzdem weiter: Untertitel, Pult und
    Einrichtung funktionieren auch ohne Ollama. Ein Abbruch waere die
    schlechtere Antwort -- dann kaeme der Techniker nicht einmal ans Pult,
    um nachzusehen."""
    import requests
    ende = time.time() + frist
    gemeldet = False
    while True:
        try:
            if requests.get(config.OLLAMA_URL + "/api/tags", timeout=3).ok:
                return True
        except Exception:
            pass
        if time.time() >= ende:
            print(f"\nOllama antwortet nicht auf {config.OLLAMA_URL}. Der "
                  f"Server laeuft weiter, aber ohne Uebersetzung.")
            print("  Laeuft der Dienst?  systemctl status ollama\n")
            return False
        if not gemeldet:
            print(f"Warte auf Ollama auf {config.OLLAMA_URL} ...")
            gemeldet = True
        time.sleep(1.0)


def brauchbare_adresse(ip):
    """127.* ist der Rechner selbst und erreicht kein Handy im Saal.
    169.254.* gibt er sich selbst, wenn kein DHCP antwortet: sieht aus wie
    eine Adresse, ist aber genau das Gegenteil einer Auskunft."""
    return bool(ip) and not ip.startswith("127.") \
        and not ip.startswith("169.254.")


def ip_ueber_route():
    """Mit welcher Adresse geht dieser Rechner hinaus?

    Verschickt nichts; der Kernel waehlt nur die Route und verraet dabei
    die Absenderadresse. Bei mehreren Netzwerkkarten ist das die
    richtige, deshalb steht dieser Weg vor dem anderen."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        return ip if brauchbare_adresse(ip) else None
    except Exception:
        return None
    finally:
        s.close()


def ip_ueber_befehl():
    """Notweg fuer ein Netz ohne Standardroute.

    Ein geschlossenes Gemeindenetz ohne Router hat gueltige Adressen,
    aber keinen Weg nach draussen. Der Weg ueber die Route scheitert dort
    vollstaendig, obwohl die Handys im selben Netz haengen."""
    import subprocess
    try:
        aus = subprocess.run(
            ["ip", "-4", "-o", "addr", "show", "scope", "global"],
            capture_output=True, text=True, timeout=3)
    except Exception:
        return None
    for zeile in aus.stdout.splitlines():
        teile = zeile.split()
        if "inet" in teile:
            ip = teile[teile.index("inet") + 1].split("/")[0]
            if brauchbare_adresse(ip):
                return ip
    return None


def lokale_ip():
    """Die Adresse, unter der die Handys im Saal den Server erreichen,
    oder None, wenn es gerade keine gibt.

    Frueher stand in diesem Fall "127.0.0.1" da. Das ist keine fehlende
    Auskunft, sondern eine falsche: die Zeile aus der Startausgabe wird
    abgelesen und weitergegeben, und im Journal steht sie dauerhaft."""
    return ip_ueber_route() or ip_ueber_befehl()


def adresse_suchen(frist, takt=1.0):
    """Sucht bis zu frist Sekunden lang und kommt beim ersten Treffer
    sofort zurueck.

    Steht die Adresse schon an -- der Normalfall mit fest eingebauter
    Netzwerkkarte --, wird nicht gewartet: die Schleife greift erst,
    wenn nichts da ist."""
    ende = time.time() + frist
    while True:
        ip = lokale_ip()
        if ip:
            return ip
        if time.time() >= ende:
            return None
        time.sleep(takt)


def adresse_nachtragen(lauf, port, frist, seit, takt=1.0):
    """Sucht im Hintergrund weiter, wenn beim Start keine Adresse da war.

    Laeuft als eigener Faden, damit der Server sofort bedient: er bindet
    auf 0.0.0.0 und antwortet ab der ersten Sekunde, auch ohne Netz. Was
    fehlt, ist nur die Zeile zum Ablesen -- und die wird hier nachgereicht,
    sobald sie stimmt."""
    ip = adresse_suchen(frist, takt)
    gebraucht = round(time.time() - seit)
    if ip:
        lauf.adresse = ip
        print(f"\n  Netz da nach {gebraucht}s. Ab jetzt gilt:")
        print(f"     Zuhörer   http://{ip}:{port}/")
        print(f"     Pult      http://{ip}:{port}/pult")
        print(f"     QR-Codes  http://{ip}:{port}/qr\n")
    else:
        print(f"\n  Nach {gebraucht}s keine Netzwerkadresse gefunden. Der "
              f"Server antwortet auf")
        print(f"  Port {port}, erreichbar ist er aber nur, wenn der Rechner "
              f"ins Netz kommt.")
        print(f"  Nachsehen mit:  ip -4 addr\n")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--geraete", action="store_true")
    p.add_argument("--geraet", type=int, default=None)
    p.add_argument("--ton-test", default=None, metavar="WAV",
                   help="Kanalscan an einer WAV-Datei statt an der "
                        "Soundkarte. Zum Pruefen der Kanaltrennung ohne "
                        "Mischpult; der Oeffnungspfad wird damit nicht "
                        "geprueft.")
    p.add_argument("--kanal", type=int, default=None,
                   help="Kanal im Geraet, gezaehlt ab 1: 1 = links/mono, "
                        "2 = rechts. Ohne Angabe gilt, was am Pult "
                        "gewaehlt wurde.")
    p.add_argument("--datei", default=None,
                   help="statt Mikrofon eine Aufnahme einspeisen, fuer den "
                        "Dauerlauf")
    p.add_argument("--tempo", type=float, default=1.0,
                   help="Wiedergabetempo der Datei. Nur zum schnellen "
                        "Ausprobieren, verfaelscht die Latenzmessung.")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--nur-text", action="store_true",
                   help="ohne Sprachausgabe, nur Untertitel")
    p.add_argument("--pause", type=float, default=0.45)
    p.add_argument("--min-dauer", type=float, default=1.6)
    p.add_argument("--max-dauer", type=float, default=8.0)
    p.add_argument("--betrieb", default="kontext",
                   choices=["kontext", "satz", "roh"],
                   help="kontext: sofort uebersetzen, aber mit dem "
                        "bisherigen Satzanfang als Einordnung (schnell und "
                        "grammatisch brauchbar). satz: auf das Satzende "
                        "warten (beste Grammatik, mehrere Sekunden "
                        "langsamer). roh: wie frueher, ohne beides.")
    p.add_argument("--max-woerter", type=int, default=40,
                   help="Notbremse: ab so vielen Woertern wird auch ohne "
                        "Satzzeichen uebersetzt")
    p.add_argument("--max-warten", type=float,
                   default=getattr(config, "SATZ_MAX_WARTEN", 9.0),
                   help="Notbremse: nach so vielen Sekunden ebenso. "
                        "Vorgabe steht in config.py (SATZ_MAX_WARTEN).")
    p.add_argument("--min-sprachdauer", type=float, default=0.9,
                   help="Segmente verwerfen, die weniger echten Schall "
                        "enthalten (Sekunden)")
    p.add_argument("--rate", type=int, default=None,
                   help="Aufnahmerate erzwingen, sonst automatisch")
    p.add_argument("--sofort", action="store_true",
                   help="ohne Druck aufs Pult sofort loslegen")
    a = p.parse_args()

    if a.geraete:
        geraete_zeigen()
        return

    basis = Path(__file__).resolve().parent
    config.ERGEBNIS_ORDNER.mkdir(exist_ok=True)

    # Vor dem Werk, nicht danach. stimmen_finden() laeuft ueber die
    # Globalen hier, und Werk laedt die Piper-Stimmen genau einmal beim
    # Bauen. Wuerden die Sprachen erst danach gesetzt, liefen genau die
    # wiederhergestellten Sprachen ohne Stimme, als reiner Untertitel.
    global QUELLE, ZIELSPRACHEN, SPRACHEN
    # Zuerst das Netz: ein Rechner, der von 0.2.11 kommt, ist umgebaut,
    # hat aber noch keine netz.json -- der Zustand stand bis dahin in
    # config.py, und die wird beim Update zurueckgesetzt. Ohne diese
    # Uebernahme stuende der Saal nach dem Update ohne Port 80 und ohne
    # Pruefadressen da, also mit lauter Handys, die "kein Internet"
    # melden.
    netzzustand.uebernehmen_falls_noetig()
    netz_lage, netz_woher = netzzustand.laden()

    stand, woher = zustandsdatei.laden()
    QUELLE = stand["quelle"]
    ZIELSPRACHEN = list(stand["ziele"])
    SPRACHEN = [QUELLE] + [s for s in ZIELSPRACHEN if s != QUELLE]

    # Der Schalter auf der Kommandozeile schlaegt die Datei. Er ist zur
    # Fehlersuche da: wer ein Geraet ausprobiert, will damit nicht die
    # Einstellung der Gemeinde ueberschreiben.
    geraet = a.geraet if a.geraet is not None else stand["geraet"]
    # Der Name gilt nur fuer die Auswahl aus der Datei. Wer auf der
    # Kommandozeile eine Nummer nennt, meint diese Nummer.
    geraet_name = "" if a.geraet is not None else stand["geraet_name"]
    # --kanal steht fuer sich und haengt nicht an --geraet: man probiert
    # durchaus den rechten Kanal des eingestellten Mikrofons, ohne die
    # Geraetenummer anzufassen.
    #
    # Gezaehlt wird ab 1, innen ab 0. Das ist keine Schlamperei, sondern
    # die Zaehlweise, die im Projekt schon gilt: werkzeuge/pegel.py gibt
    # "--kanal 2" aus, und auf dem SQ5 steht auf keinem Weg eine Null.
    # Zwei Zaehlweisen im selben Projekt waeren die Falle, nicht der
    # Umrechnungsschritt hier.
    if a.kanal is not None:
        if a.kanal < 1:
            sys.exit("--kanal zaehlt ab 1: 1 ist links oder mono, "
                     "2 ist rechts. Eine 0 gibt es nicht.")
        kanal, kanaele = a.kanal - 1, max(1, a.kanal)
    elif a.geraet is not None:
        # Nummer von Hand, Kanal nicht: das meint den ersten Kanal. Die
        # gespeicherte Kanalwahl gehoert zum gespeicherten GERAET und
        # waere auf einem anderen eine Vermutung.
        kanal, kanaele = 0, 1
    else:
        kanal, kanaele = stand["geraet_kanal"], stand["geraet_kanaele"]

    werk = Werk(nur_text=a.nur_text)
    seg = Segmentierer(pause=a.pause, min_dauer=a.min_dauer,
                       max_dauer=a.max_dauer,
                       min_sprachdauer=a.min_sprachdauer)
    lauf = Lauf(werk, seg)
    lauf.betrieb = a.betrieb
    lauf.sammler = Satzsammler(a.max_woerter, a.max_warten)
    lauf.zustand = stand
    # Der Schalter gilt ab dem Start. Er steht in zustand.json, damit
    # der Ordner unveraendert bleibt und Updates nicht daran abbrechen.
    global PROTOKOLL_MITSCHRIFT
    PROTOKOLL_MITSCHRIFT = bool(stand.get("protokoll_mitschrift"))
    if PROTOKOLL_MITSCHRIFT:
        print(warnung(
            "ACHTUNG: Mitschrift im Protokoll ist EINGESCHALTET. Der "
            "gesprochene Satz steht dann im Journal. Nur zur "
            "Fehlersuche; danach am Pult wieder ausschalten."))
    lauf.wlan = dict(stand["wlan"])
    if stand["schwelle"]["wert"] is not None:
        # Die eingemessene Schwelle gilt weiter. Im Dateibetrieb wird sie
        # gleich wieder ueberschrieben, das ist Absicht: eine Aufnahme hat
        # keinen wandernden Raumklang.
        seg.feste_schwelle = stand["schwelle"]["wert"]
    # Das Abschalt-Event des Servers. Der Mikrofon-Thread haengt bewusst
    # nicht mehr daran, sondern an seinem eigenen in Tonquelle; hier bleibt,
    # was den Dateibetrieb beendet.
    stoppen = threading.Event()
    rate = MIKRO_RATE
    tonquelle = None
    kanalscan = None

    testton = None
    if a.ton_test:
        if not Path(a.ton_test).exists():
            sys.exit(f"Nicht gefunden: {a.ton_test}")
        try:
            testton = Testton(a.ton_test)
        except Exception as e:
            sys.exit(f"{Path(a.ton_test).name} laesst sich nicht lesen: {e}")
        print(f"Kanalscan an der Datei: {testton.name}, "
              f"{testton.kanaele} Kanaele, {testton.rate} Hz. "
              f"Es wird kein Geraet aufgemacht.")

    if a.datei:
        if not Path(a.datei).exists():
            sys.exit(f"Nicht gefunden: {a.datei}")
        # Eine Aufnahme hat keinen wandernden Raumklang, dem die Schwelle
        # folgen muesste. Fest eingestellt bleibt die Segmentierung ueber
        # die ganze Datei vergleichbar.
        seg.feste_schwelle = 0.006
        # Sofort loslegen, sonst laeuft die Aufnahme ins Leere, bis jemand
        # am Pult drueckt. Ohne Zuhoerer ist hier noch niemand zu
        # benachrichtigen, deshalb direkt statt ueber starten().
        lauf.laeuft = True
        lauf.begonnen = time.time()
        threading.Thread(target=datei_thread,
                         args=(lauf, a.datei, seg, stoppen, a.tempo),
                         daemon=True).start()
    else:
        tonquelle = Tonquelle(lauf, seg, a.rate)
        if a.sofort:
            lauf.laeuft = True
            lauf.begonnen = time.time()
        gelungen, lage, grund = tonquelle.starten(geraet, geraet_name,
                                                  kanal, kanaele)
        if lage == "warte_auf_geraet":
            # Kein Fehler, sondern der geordnete Fall: das eingestellte
            # Mikrofon ist noch nicht aufgezaehlt. Beim Start aus dem
            # Dienst heraus ist das der Normalfall -- USB braucht laenger
            # als systemd. Der Aufseher greift zu, sobald es da ist.
            print(f"\nWarte auf Tonquelle \"{tonquelle.wartet_auf}\".")
            print("Es wird kein anderes Geraet genommen. Ein anderes waehlen")
            print("geht am Pult unter Einrichtung.\n")
        elif not gelungen:
            # Kein Abbruchgrund mehr. Frueher lief der Server an dieser
            # Stelle ohne Ton weiter und ohne Ausweg; jetzt gibt es einen,
            # und dafuer muss er stehen.
            print(f"\nKein Ton: {grund}")
            print("Am Pult unter Einrichtung ein anderes Geraet waehlen.\n")

    ollama_da = ollama_abwarten()

    import uvicorn
    # Nachfassen, aber nur solange nichts da ist. Mit fest eingebauter
    # Netzwerkkarte steht die Adresse beim ersten Blick an und es wird
    # nicht gewartet; beim Start aus dem Dienst heraus ist das Netz oft
    # noch nicht fertig. network-online.target hilft dagegen nicht: es
    # bedeutet "NetworkManager hat nichts mehr vor", nicht "es gibt eine
    # Adresse". Gemessen wurde das Target erreicht, waehrend erst
    # loopback stand und die Netzwerkkarte noch gar nicht angemeldet war.
    adresse_seit = time.time()
    # Ist der Rechner selbst der Router, steht die Adresse fest und muss
    # nicht gesucht werden. Die Suche bleibt fuer alle anderen Faelle --
    # Entwicklung, Vorfuehrung, ein Rechner ohne den Umbau.
    if netz_lage["router"]:
        ip = netz_lage["adresse"] or config.NETZ_ADRESSE
        print(f"\n  Netz      dieser Rechner ist Router, feste Adresse {ip}")
    else:
        ip = adresse_suchen(ADRESSE_ANLAUF)
    lauf.adresse = ip
    if ip:
        print(f"\n  Zuhörer   http://{ip}:{a.port}/")
        print(f"  Pult      http://{ip}:{a.port}/pult")
        print(f"  QR-Codes  http://{ip}:{a.port}/qr")
    else:
        # Bewusst keine Adresse statt 127.0.0.1: was hier steht, liest
        # jemand ab und gibt es weiter.
        print("\n  Adresse   noch keine. Das Netz ist beim Start noch "
              "nicht fertig.")
        print("            Die Adressen erscheinen hier, sobald eine da "
              "ist.")
        threading.Thread(target=adresse_nachtragen,
                         args=(lauf, a.port, ADRESSE_FRIST, adresse_seit),
                         daemon=True).start()
    print(f"  Modell    {config.LIVE_MODELL}"
          f"{'  (nur Text)' if a.nur_text else ''}"
          f"{'' if ollama_da else '  (Ollama antwortet nicht)'}")
    print(f"  Fassung   {config.VERSION}")
    print(f"  Rechnet   {werk.rechenwerk}")
    print(f"  Zustand   {woher}")
    print(f"            {zustandsdatei.kurzfassung(stand)}")
    print(f"  Schnitt   Pause {a.pause}s, {a.min_dauer} bis {a.max_dauer}s")
    beschriftung = {"kontext": "sofort, mit Satzanfang als Einordnung",
                    "satz": f"erst am Satzende, Notbremse bei "
                            f"{a.max_woerter} Wörtern oder {a.max_warten}s",
                    "roh": "sofort, ohne Einordnung"}
    print(f"  Übersetzt {beschriftung[a.betrieb]}")
    if a.datei:
        print(f"  Quelle    {Path(a.datei).name} (Dauerlauf)\n")
    elif tonquelle is not None and tonquelle.laeuft:
        print(f"  Aufnahme  Geraet {tonquelle.geraet}, {tonquelle.rate} Hz "
              f"-> {MIKRO_RATE} Hz\n")
    else:
        print("  Aufnahme  kein Geraet offen, am Pult auswaehlen\n")

    # Der Scan gehoert auch dann ans Pult, wenn der Ton aus einer Datei
    # oder ueber das Netz kommt: dann ist er der Weg, ueberhaupt erst ein
    # Geraet zu finden. Ohne Tonquelle misst er nur und waehlt nicht --
    # dort gibt es nichts umzustellen.
    if tonquelle is not None or testton is not None:
        kanalscan = Kanalscan(lauf, tonquelle, testton, a.rate)

    try:
        starten_auf(app_bauen(lauf, basis, a.port, tonquelle, kanalscan),
                    a.port)
    except OSError as e:
        if "10048" in str(e) or "address" in str(e).lower():
            print(f"\nPort {a.port} ist belegt. Laeuft der Dienst schon?")
            print("  systemctl status devarenu")
            print(f"Anderen Port nehmen: server.py --geraet {geraet} "
                  f"--port {a.port + 1}")
        else:
            raise
    finally:
        stoppen.set()
        if tonquelle is not None:
            tonquelle.anhalten()


if __name__ == "__main__":
    main()
