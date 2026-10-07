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
import hashlib
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
import aufnahme
import berichtpost
import pruefprotokoll
import spendenkonto
import sprachwache
import drossel
import pultschutz
import grafikwacht
import rueckmeldung
import qr_texte
import datenschutz
import zustand as zustandsdatei
from glossar import Glossar, glossarzeilen, vokalisieren
import zaehlung

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

# Warum das Spendenkonto beanstandet wird, oder "" wenn alles stimmt.
# Beim Start gesetzt, siehe spendenkonto_pruefen().
KONTO_GRUND = ""


# Ein Salz, das mit dem Prozess entsteht und mit ihm verschwindet.
# Damit ist dieselbe Adresse innerhalb eines Laufs dieselbe Kennung
# -- und nach einem Neustart eine andere. Wer zwei Journale
# vergleicht, kann nichts zusammenfuehren.
_KENNUNG_SALZ = os.urandom(16)


def geraetekennung(adresse):
    """Vier Zeichen statt einer Adresse -- fuer das Journal.

    Im Saal sitzen Gemeindeglieder und Gaeste. Eine Zeile wie

        Zu viele Stroeme von 10.0.0.57, abgewiesen.

    sagt der Technik nichts, was diese Zeile nicht auch sagt:

        Zu viele Stroeme von Geraet a3f1, abgewiesen.

    Was man braucht, ist die Unterscheidung -- ein Geraet, das
    zwanzigmal auftaucht, oder zwanzig verschiedene. Dafuer genuegt
    eine Kennung. Die Adresse selbst gehoert nicht ins Journal, das
    vier Wochen haelt.

    Nicht umkehrbar: gesalzen, und das Salz steht nirgends."""
    if not adresse:
        return "Geraet ?"
    kurz = hashlib.blake2s(str(adresse).encode("utf-8"),
                           key=_KENNUNG_SALZ, digest_size=2).hexdigest()
    return f"Geraet {kurz}"


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
        # Drei Modi, ausdruecklich benannt. Bis 0.4.0 gab es zwei, und
        # beide steckten im Wert: None hiess mitlaufend, eine Zahl hiess
        # festgenagelt. Ein Regler auf null wurde zur kleinsten festen
        # Schwelle -- genau das taten die Helfer in Rostock jeden
        # Gottesdienst, weil mit Schwelle mehr Erkennungsfehler kamen.
        # Ein Wunsch, der sich nur als Zahl ausdruecken laesst, ist kein
        # eingestellter Zustand: beim naechsten Einmessen war er weg.
        self.modus = "aus"
        self.feste_schwelle = None      # nur im Modus "fest" gefuellt
        # Wohin ein Geraetewechsel zurueckfaellt. Nie "fest": die feste
        # Schwelle galt der alten Tonquelle.
        self.grundmodus = "aus"
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

    # Was "aus" bedeutet: nicht wirklich null, sondern unterhalb von
    # allem, was ein Mikrofon in einem Raum aufnimmt. Geschnitten wird
    # dann an Pausen nahe Stille und an der Hoechstdauer. Derselbe Wert,
    # den der Server bis 0.4.0 aus einem Regler auf null machte -- das
    # Verhalten bleibt damit Bit fuer Bit dasselbe, es heisst nur jetzt
    # so, wie es gemeint ist.
    AUS_SCHWELLE = 0.0005

    # Die Untergrenze der mitlaufenden Schwelle. Sie soll verhindern,
    # dass die Automatik in einem totenstillen Raum auf null faellt
    # und jedes Rascheln durchlaesst. Bei sauberem Leitungston -- ein
    # Mischpultausgang, wie in Rostock -- liegt der Grundpegel aber so
    # tief, dass IMMER diese Zahl gilt und nie der gemessene Raum.
    #
    # Sie stand bis 0.4.2 auf 0,0025, und das war zu hoch: der Median
    # aller Tonbloecke von predigt2.mp3 liegt bei 0,0033, die Grenze
    # also dicht darunter. Gemessen an derselben Aufnahme, nur diese
    # Zahl geaendert (werkzeuge/schwellenmessung.py --untergrenzen):
    #
    #   0,0025   272 Abschnitte   71 verworfen   2576 Woerter
    #   0,0015   285              52            2635
    #   0,0010   291              46            2664
    #   0,0005   294              48            2680
    #
    # Der Anteil der Schnitte an der Hoechstdauer bleibt in jeder
    # Stufe bei 1,7 bis 1,8 Prozent -- der Modus "Aus" schneidet dort
    # 12,3 Prozent. 0,001 holt also fast alle Woerter von "Aus" und
    # behaelt die ruhige Schnittfuehrung der Automatik. Unter 0,001
    # bringt es nichts mehr.
    #
    # Als Klassenattribut, damit werkzeuge/schwellenmessung.py sie
    # fuer eine Messreihe umstellen kann, ohne den Segmentierer
    # umzubauen.
    AUTO_UNTERGRENZE = 0.001

    @property
    def schwelle(self):
        if self.modus == "fest" and self.feste_schwelle is not None:
            return self.feste_schwelle
        if self.modus == "automatisch":
            return max(self.AUTO_UNTERGRENZE, self.grundpegel * 3.5)
        return self.AUS_SCHWELLE

    def modus_setzen(self, modus, wert=None):
        """Legt den Modus fest. Gibt zurueck, was tatsaechlich gilt.

        "fest" ohne Wert ist keine Einstellung, sondern ein Versehen:
        dann bleibt es beim Grundmodus. Alles andere loescht den festen
        Wert, damit er nicht als Leiche stehenbleibt und beim naechsten
        Umschalten unbemerkt wieder gilt."""
        if modus == "fest":
            if wert is None:
                return self.modus
            self.feste_schwelle = max(0.0005, min(0.5, float(wert)))
            self.modus = "fest"
            return self.modus
        if modus not in ("aus", "automatisch"):
            return self.modus
        self.feste_schwelle = None
        self.modus = modus
        self.grundmodus = modus
        return self.modus

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
        # Einmessen heisst festnageln. Der Grundmodus bleibt stehen:
        # darauf faellt ein Geraetewechsel zurueck.
        self.modus = "fest"
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
            # Im Modus "Aus" gibt es keine Mindestlautstaerke, die zu
            # hoch stehen koennte. Verworfen wird dort, weil in einem
            # Abschnitt zu wenig ECHTES Sprechen steckte -- Husten,
            # Stuhlruecken, Musik. Die Frage nach dem Regler waere da
            # eine falsche Faehrte.
            if self.modus == "aus":
                return {"stufe": "alarm", "verworfen": v, "durch": d,
                        "text": f"{v} Abschnitte ohne erkennbare Sprache, "
                                f"nur {d} übersetzt. Tonquelle prüfen."}
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

def schleife_kappen(text, mal=4, laengste=6):
    """Kappt eine Wiederholungsschleife des Sprachmodells.

    Gesucht wird die FRUEHESTE Stelle, an der sich ein Wort oder eine
    Gruppe von bis zu `laengste` Woertern mindestens `mal`-mal direkt
    hintereinander wiederholt. Stehen bleibt alles bis einschliesslich
    des ersten Vorkommens. Verglichen wird ohne Satzzeichen und
    Gross/Klein; ausgegeben werden die Woerter, wie sie dastanden.

    Drei Wiederholungen ("heilig, heilig, heilig") bleiben stehen --
    das ist Rede, keine Schleife. Dazu Silbenketten in einem Wort
    ("nɔnɔnɔnɔnɔnɔ"): sechs gleiche Silben und mehr werden auf zwei
    gekuerzt. Gilt nur fuer config.SCHLEIFE_KAPPEN."""
    woerter = text.split()
    norm = [re.sub(r"[\W_]", "", w.lower()) for w in woerter]
    schnitt = None
    for i in range(len(norm)):
        for n in range(1, laengste + 1):
            gruppe = norm[i:i + n]
            if len(gruppe) < n or not any(gruppe):
                break
            if all(norm[i + k * n:i + (k + 1) * n] == gruppe
                   for k in range(1, mal)):
                schnitt = i + n
                break
        if schnitt is not None:
            break
    if schnitt is not None:
        text = " ".join(woerter[:schnitt]).rstrip(",;:") + " …"
    return re.sub(r"(\w{1,3}?)\1{5,}", r"\1\1", text)


def fehlformen_finden(treffer, text, sprache):
    """Welche bekannten Fehlformen (config.FEHLFORMEN) stehen in der
    Uebersetzung -- nur fuer Glossarbegriffe, die im Abschnitt
    vorkommen? Liste von dicts; leer heisst: nichts gefunden.

    treffer sind die Glossartreffer, die uebersetzen() ohnehin sucht.
    Steht keiner der genannten Begriffe darin, wird kein Ausdruck
    angefasst."""
    regeln = getattr(config, "FEHLFORMEN", {}).get(sprache)
    if not regeln or not treffer:
        return []
    nach_id = {e.id: e for e in treffer}
    gefunden = []
    for r in regeln:
        e = nach_id.get(r["glossar"])
        if e is None:
            continue
        m = re.search(r["fehlform"] + r"\w*", text, re.IGNORECASE)
        if m:
            gefunden.append({"glossar": e.id, "de": e.de,
                             "richtig": e.ziel.get(sprache, ""),
                             "falsch": r["falsch"], "grund": r["grund"],
                             "formen": r.get("formen", ""),
                             "gefunden": m.group(0)})
    return gefunden


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
        # Die Zaehlungstabelle. Fehlt sie, wird nichts umgerechnet --
        # und das ist der richtige Ausfall: die Angabe der Schlachter
        # stimmt ja.
        self.zaehlung = zaehlung.Tabelle.laden()
        if self.zaehlung.vorhanden:
            print("Zaehlung: Bibelstellen werden fuer "
                  + ", ".join(sorted(zaehlung.ZAEHLUNG_JE_SPRACHE))
                  + " umgerechnet")
        else:
            print("Keine zaehlung.json. Bibelstellen bleiben in der "
                  "Zaehlung der Schlachter.")
        self.stt_prompt = ""
        # Kopf (Einleitung und Thema) getrennt vom Rest. Beim Kuerzen auf
        # das Token-Budget bleibt er stehen, die Namen weichen von hinten
        # und der Verlauf zuerst -- siehe bibelstellen.stt_prompt_bauen.
        self.stt_kopf = config.PROMPT_EINLEITUNG.strip()
        self.stt_namen = []
        self.letzter_satz = ""
        self.kontext_stellen = []
        self.kontext_namen = []
        # Soll das, was am Pult unter Thema und Bibelstellen steht,
        # auch in den UEBERSETZUNGS-Prompt? Bis 0.4.1 ging es nur an
        # Whisper. Vorgabe AUS -- ein Hinweis mehr im Prompt ist ein
        # Hinweis mehr, den das Modell missverstehen kann, und das
        # faellt erst im Gottesdienst auf.
        self.thema_im_prompt = False
        self.skript_namen = []
        self.skript_info = None
        self.verlauf = deque(maxlen=3)
        # Wie oft der Floskelfilter gegriffen hat. Einmal fuer ganze
        # Abschnitte, einmal fuer angehaengte Abspanne. Gezaehlt wird
        # fuer die Messung der Schwellenmodi und fuer die Fehlersuche:
        # steigt die erste Zahl, hoert das Mikrofon Musik.
        self.erfunden_zahl = 0
        self.erfunden_ende = 0

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

    def sprecher_fuer(self, sprache):
        """Welcher Sprecher einer Mehrsprecher-Stimme spricht -- oder None.

        config.STIMM_SPRECHER nennt ihn je Stimme beim Namen, die Nummer
        steht in der .onnx.json daneben. Ohne Eintrag None: Piper nimmt
        dann Sprecher 0, so wie bisher immer (Nachtrag zu 0.5.0)."""
        name = self.stimmennamen.get(sprache, "")
        wer = getattr(config, "STIMM_SPRECHER", {}).get(name)
        if wer is None:
            return None
        nummer = _sprecher_karte(name).get(wer)
        if nummer is None:
            print(f"Sprecher {wer!r} gibt es in {name} nicht; "
                  f"es spricht Sprecher 0.")
        return nummer

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
        # Der Testmodus (nur auf einem Rechner OHNE NVIDIA-Karte und nur
        # mit der Marke TESTMODUS). Er tauscht das Modell gegen ein
        # kleines auf der CPU -- damit der Weg pruefbar ist, nicht die
        # Qualitaet. Siehe testmodus.py.
        import testmodus
        tm_an, tm_grund = testmodus.lage()
        if tm_an:
            print("\n" + "=" * 62)
            print("TESTMODUS")
            print(f"  {tm_grund}")
            print("  Die Uebersetzung ist so UNBRAUCHBAR. Geprueft wird")
            print("  der Weg, nicht das Ergebnis.")
            print("=" * 62 + "\n")
            tm_modell, geraet, rechenart = testmodus.einstellungen(
                (config.WHISPER_MODELL, geraet, rechenart))

            def laden(g, r, _m=tm_modell):
                print(f"Whisper {_m} laedt ({g}, {r}) ...")
                return WhisperModel(_m, device=g, compute_type=r,
                                    download_root=str(config.MODELL_ORDNER))
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
    # Bis 0.4.0 stand hier "( fuer|für)?" -- das Leerzeichen nur im
    # ersten Zweig. Damit traf das Muster "vielen dank fuer das ...",
    # aber NIE "Vielen Dank fuer Ihre Aufmerksamkeit." oder "Vielen Dank
    # fuers Zuhoeren.", weil nach "dank" ein Leerzeichen steht und der
    # zweite Zweig keines mitbringt. Genau diese beiden Saetze kommen in
    # Rostock, sobald die Schwelle an ist.
    #
    # Zwei Aenderungen an der Arbeitsweise:
    #   1. Geprueft wird mit fullmatch. Ein Abschnitt faellt nur, wenn er
    #      GANZ aus der Floskel besteht. Vorher reichte der Anfang, und
    #      "Vielen Dank fuer das Wort, das heute zu uns kam" war weg.
    #   2. Steht die Floskel am Ende eines sonst echten Abschnitts, wird
    #      nur sie abgeschnitten (floskel_kuerzen).
    #
    # "Danke." allein steht NICHT mehr darin: im Gottesdienst ist das
    # ein normaler Satz. "Vielen Dank." allein bleibt gefiltert.
    _ABSPANN = (r"(zuh(ö|oe)ren|zuschauen|zusehen|mitschauen|"
                r"aufmerksamkeit|interesse|dabei\s*sein)")
    _FLOSKEL = (
        r"untertitel\w*\b.*"
        r"|amara\.org.*"
        r"|copyright.*"
        r"|abonniert.*"
        # Allein oder mit beliebigem Dank-Objekt: das ist der Abspann.
        # Dass dabei ein echter Dank des Predigers verlorengehen kann,
        # ist in Kauf genommen -- er steht am Predigtende, wo ohnehin
        # nichts mehr uebersetzt werden muss.
        r"|vielen\s+dank"
        # Mit Dank-Objekt nur, wenn das Objekt der Abspann selbst ist.
        # Das alte Muster nahm "vielen dank fuer das|ihre|eure" mit
        # BELIEBIGEM Objekt -- damit fiel auch "Vielen Dank fuer eure
        # Gebete". Ein Prediger sagt das mitten in der Predigt.
        r"|(vielen\s+|herzlichen\s+)?dank(e)?(\s+sch(ö|oe)n)?"
        r"\s+f(ü|ue)rs?\s+"
        r"(das\s+|die\s+|den\s+|ihre\s+|eure\s+|euer\s+|ihr\s+|dein\s+)?"
        + _ABSPANN + r"\b.*"
        # Ohne ".*": "Bis zum naechsten Mal werden wir den Abschnitt zu
        # Ende lesen" ist ein Predigtsatz, "Bis zum naechsten Mal!" der
        # Abspann. Der Unterschied ist, dass danach nichts mehr kommt.
        r"|bis\s+zum\s+n(ä|ae)chsten\s+mal"
        r"|tsch(ü|ue)ss"
        r"|die\s+sendung\s+wurde.*"
        r"|(wdr|ndr|zdf|ard|swr|mdr|rbb|arte)[\s-]?"
        r"(mediagroup|presse|text).*"
        r"|im\s+auftrag\s+(des|der)\s+(wdr|ndr|zdf|ard|swr|mdr|rbb).*"
        r"|mit\s+freundlicher\s+unterst(ü|ue)tzung.*"
    )
    ERFUNDEN = re.compile(r"\W*(?:" + _FLOSKEL + r")\W*", re.IGNORECASE)

    # Satzgrenze zum Abschneiden. Nur dort, wo auf ein Satzzeichen
    # Leerraum folgt -- "Dr. Luther" soll kein Satzende sein.
    SATZGRENZE = re.compile(r"(?<=[.!?…])\s+")

    @classmethod
    def floskel_kuerzen(cls, text):
        """Schneidet Abspannfloskeln am Ende ab, laesst den Rest stehen.

        "Gott segne euch. Vielen Dank fuers Zuhoeren." ist ein echter
        Abschnitt mit einem angehaengten Abspann. Ihn ganz wegzuwerfen
        kostet den Segen, ihn ganz zu behalten schickt den Abspann in
        vier Sprachen auf die Handys."""
        teile = [t for t in cls.SATZGRENZE.split((text or "").strip()) if t]
        while len(teile) > 1 and cls.ERFUNDEN.fullmatch(teile[-1]):
            teile.pop()
        return " ".join(teile).strip()

    def sprache_raten(self, audio):
        """(Kennung, Wahrscheinlichkeit) -- welche Sprache klingt das?

        Nur der Encoder und ein Dekoderschritt, kein Transkript.
        Gemessen mit large-v3-turbo, float16, auf einer RTX 5080: 76 ms,
        unabhaengig von der Tondauer -- Whisper fuellt ohnehin auf 30 s
        auf. Zum Vergleich braucht transcribe fuer fuenf Sekunden
        85 ms. Deshalb ruft die Sprachwache das nur jedes vierte
        taugliche Segment auf.

        Schlaegt es fehl, gilt "unbekannt". Eine Vermutung ueber die
        Sprache darf die Uebersetzung nie aufhalten."""
        try:
            sprache, wahrscheinlich, _ = self.whisper.detect_language(audio)
            return sprache, wahrscheinlich
        except Exception as e:
            print(f"        Spracherkennung ging nicht: {str(e)[:70]}")
            return "", None

    def stt_token(self, text):
        """Wie viele Token macht Whisper daraus?

        Gemessen mit dem Tokenizer DIESES Modells. Eine Schaetzung in
        Zeichen ginge bei Eigennamen regelmaessig daneben: "Sanballat"
        sind neun Zeichen und vier Token, "der" drei Zeichen und eines.
        Gerade die Namen sind es aber, um die es im Prompt geht.

        Faellt der Tokenizer aus, wird grob geschaetzt -- lieber zu
        vorsichtig als gar kein Prompt."""
        if not text:
            return 0
        t = getattr(self.whisper, "hf_tokenizer", None)
        if t is None:
            return len(text) // 3 + 1
        try:
            return len(t.encode(" " + text.strip()).ids)
        except Exception:
            return len(text) // 3 + 1

    def hoeren(self, audio):
        kwargs = dict(language=self.quelle, beam_size=1,
                      vad_filter=False, condition_on_previous_text=False)
        from bibelstellen import stt_prompt_bauen
        prompt = stt_prompt_bauen(self.stt_kopf, self.stt_namen,
                                  list(self.verlauf), self.stt_token)
        if prompt.strip():
            kwargs["initial_prompt"] = prompt
        segmente, _ = self.whisper.transcribe(audio, **kwargs)
        text = " ".join(s.text.strip() for s in segmente).strip()

        if not text:
            return ""
        # Erst der ganze Abschnitt, dann sein Ende: besteht er GANZ aus
        # einer Floskel, faellt er; haengt sie nur hinten dran, faellt
        # nur sie.
        if self.ERFUNDEN.fullmatch(text):
            self.erfunden_zahl += 1
            return ""
        gekuerzt = self.floskel_kuerzen(text)
        if gekuerzt != text:
            self.erfunden_ende += 1
            text = gekuerzt
            if not text:
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
    def stellen_umrechnen(self, text, sprache):
        """[(Quelltext, Zielname, Kapitel, Vers), ...] oder [].

        NUR bei deutscher Ausgangssprache: die Schlachter zaehlt wie
        der hebraeische Text, und nur davon ausgehend ist die
        Umrechnung belegt. Spricht jemand englisch, nennt er die Stelle
        schon in der englischen Zaehlung.

        Leer heisst: nichts umzurechnen. Das ist der haeufige Fall --
        "Johannes 3,16" heisst ueberall 3,16."""
        if self.quelle != "de" or not self.zaehlung.vorhanden:
            return []
        welche = zaehlung.ZAEHLUNG_JE_SPRACHE.get(sprache)
        if not welche:
            return []
        from bibelstellen import stellen_mit_versen
        aus = []
        for nummer, buch, kapitel, vers, quelltext, _ in \
                stellen_mit_versen(text):
            neu = self.zaehlung.umrechnen(nummer, kapitel, vers, welche)
            if not neu:
                continue
            z_kap, z_vers = neu
            if (z_kap, z_vers) == (kapitel, vers):
                continue
            # Der Buchname in der Zielsprache. Fuer einen einzelnen
            # Psalm der Singular, nicht der Buchtitel.
            name = zaehlung.ZITATNAME.get(nummer, {}).get(sprache)
            if not name:
                treffer = [e for e in self.glossar.eintraege
                           if e.block == "A" and e.de == buch]
                name = (treffer[0].ziel.get(sprache, "").strip()
                        if treffer else "") or buch
            aus.append((quelltext, name, z_kap, z_vers))
        return aus

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
        # Bibelstellen: nur fuer Sprachen in config.STELLEN_TRENNER,
        # also es und pt -- dort schreibt das Modell von selbst ein
        # Komma, wo jede spanische und portugiesische Bibel einen
        # Doppelpunkt setzt.
        #
        # Der Doppelpunkt geht auch an Piper, kostet dort aber nichts:
        # ohne Leerzeichen behandelt espeak "53:5" wie "53 5". Das
        # Komma waere das teurere Zeichen. Messungen in config.py.
        trenner = config.STELLEN_TRENNER.get(sprache)
        if trenner:
            system += (f"\n- Bibelstellen werden mit „{trenner}“ zwischen "
                       f"Kapitel und Vers geschrieben, zum Beispiel "
                       f"Juan 3{trenner}16.")
        # Die Anrede. Ohne Vorgabe entscheidet das Modell sie in jedem
        # Abschnitt neu, und die Gemeinde wird im Wechsel geduzt und
        # gesiezt. Nur fuer Sprachen, fuer die sie belegt festgelegt
        # ist -- siehe config.ANREDE.
        anrede = getattr(config, "ANREDE", {}).get(sprache)
        if anrede:
            system += f"\n- {anrede}"
        # Thema und Bibelstellen auch fuer die Uebersetzung. Nur hinter
        # dem Schalter, und bewusst als EINORDNUNG, nicht als Auftrag:
        # das Modell soll wissen, worum es geht, und nicht anfangen,
        # den Abschnitt zum Thema passend zu machen.
        if self.thema_im_prompt:
            worum = []
            if self.kontext_stellen:
                worum.append(", ".join(self.kontext_stellen))
            if self.kontext_namen:
                worum.append(", ".join(self.kontext_namen[:20]))
            if worum:
                system += (f"\n- In diesem Gottesdienst geht es um: "
                           f"{' -- '.join(worum)}. Das dient NUR der "
                           f"Einordnung von Namen und Begriffen. "
                           f"Uebersetze trotzdem genau das Gegebene.")
        # Bibelstellen in die Zaehlung der Zielsprache. Vorgegeben wird
        # die FERTIGE Angabe, nicht die Regel -- ein Sprachmodell, das
        # rechnen soll, rechnet falsch.
        stellen_um = self.stellen_umrechnen(text, sprache)
        if stellen_um:
            system += zaehlung.hinweis_bauen(stellen_um, sprache,
                                             trenner or ",")
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
        t = self._modell_fragen(system, text)
        # Bekannte Fehlformen (config.FEHLFORMEN): einmal neu, mit
        # Hinweis; bleibt sie, geht es trotzdem hinaus -- ersetzt wird
        # nie. Ohne passenden Glossartreffer kostet das nichts.
        fehl = fehlformen_finden(treffer, t, sprache)
        if fehl:
            print(f"        Fehlform {sprache}: "
                  f"{', '.join(f['gefunden'] for f in fehl)} -- "
                  f"noch einmal mit Hinweis")
            # Je Glossarbegriff EIN Hinweis mit den gebeugten Formen,
            # dazu jede gefundene Fehlform mit ihrem Grund.
            hinweis = ""
            for gid in dict.fromkeys(f["glossar"] for f in fehl):
                zu = [f for f in fehl if f["glossar"] == gid]
                hinweis += (f"\n- WICHTIG: „{zu[0]['de']}“ heisst "
                            f"„{zu[0]['richtig']}“, passend gebeugt.")
                if zu[0].get("formen"):
                    hinweis += f" Die Formen: {zu[0]['formen']}"
                for f in zu:
                    hinweis += (f"\n  Nicht {f['falsch']} -- {f['grund']}.")
            t = self._modell_fragen(system + hinweis, text)
            for f in fehlformen_finden(treffer, t, sprache):
                print(warnung(f"Fehlform {sprache} blieb nach dem zweiten "
                              f"Versuch: {f['gefunden']} ({f['glossar']} "
                              f"{f['de']}). Gesendet wie sie ist."))
        if sprache in getattr(config, "SCHLEIFE_KAPPEN", ()):
            gekappt = schleife_kappen(t)
            if gekappt != t:
                print(f"        Schleife {sprache}: {len(t)} -> "
                      f"{len(gekappt)} Zeichen gekappt")
                t = gekappt
        # Nachsehen, ob die umgerechnete Angabe wirklich dasteht. Wenn
        # nicht, einsetzen -- aber nur, wo die alte Angabe woertlich im
        # Text steht. Sonst bleibt alles, wie es ist, und es geht ins
        # Journal: eine Uebersetzung kaputtzureparieren ist schlimmer
        # als eine Stelle in der falschen Zaehlung.
        if stellen_um:
            t, ersetzt = zaehlung.nachtragen(t, stellen_um, trenner or ",")
            for quell, ziel in ersetzt:
                print(f"        Zaehlung {sprache}: {quell} -> {ziel} "
                      f"(vom Modell nicht uebernommen)")
            offen = [q for q, n, k, v in stellen_um
                     if not zaehlung.steht_drin(t, n, k, v)]
            for q in offen:
                print(f"        Zaehlung {sprache}: {q} blieb, wie es war "
                      f"-- das Modell hat umformuliert.")
        return t

    def _modell_fragen(self, system, text):
        """Ein Aufruf des Uebersetzungsmodells, die Antwort bereinigt."""
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

    def _mit_kommapausen(self, text, sprache, datei, ms):
        """Spricht Teilsatz fuer Teilsatz und legt Stille dazwischen.

        Teile ohne Buchstaben werden uebersprungen -- sonst erzeugte
        ein Satz, der mit einem Komma beginnt, ein leeres Stueck, und
        Piper macht daraus eine Fehlermeldung statt einer Datei.

        Faellt hier etwas aus, wird der Satz am Stueck gesprochen:
        eine zu kurze Pause ist ein Schoenheitsfehler, ein
        ausgefallener Abschnitt nicht."""
        import re as _re
        teile = [t.strip() for t in text.split(",")]
        teile = [t for t in teile if _re.search(r"\w", t)]
        if len(teile) < 2:
            return self._am_stueck(text, sprache, datei)
        try:
            from piper import SynthesisConfig
            skala = 1.0 / self.tempo_fuer(sprache)
            stimme = self.stimmen[sprache]
            rahmen, kopf = [], None
            for i, teil in enumerate(teile):
                stueck = datei.with_name(f"{datei.stem}_{i}.wav")
                with wave.open(str(stueck), "wb") as ziel:
                    if self.synth_art == "syn_config":
                        stimme.synthesize_wav(
                            teil, ziel,
                            syn_config=SynthesisConfig(
                                length_scale=skala,
                                speaker_id=self.sprecher_fuer(sprache)))
                    elif self.synth_art == "length_scale":
                        stimme.synthesize_wav(teil, ziel, length_scale=skala)
                    else:
                        stimme.synthesize_wav(teil, ziel)
                with wave.open(str(stueck)) as w:
                    if kopf is None:
                        kopf = (w.getnchannels(), w.getsampwidth(),
                                w.getframerate())
                    rahmen.append(w.readframes(w.getnframes()))
                stueck.unlink(missing_ok=True)
            stille = b"\x00" * int(kopf[2] * kopf[1] * kopf[0] * ms / 1000)
            with wave.open(str(datei), "wb") as ziel:
                ziel.setnchannels(kopf[0])
                ziel.setsampwidth(kopf[1])
                ziel.setframerate(kopf[2])
                ziel.writeframes(stille.join(rahmen))
            with wave.open(str(datei)) as w:
                return datei, w.getnframes() / w.getframerate()
        except Exception as e:
            print(f"        Kommapausen gingen nicht ({str(e)[:60]}), "
                  f"der Satz wird am Stueck gesprochen.")
            return self._am_stueck(text, sprache, datei)

    def _am_stueck(self, text, sprache, datei):
        """Der gewoehnliche Weg: ein Aufruf, ein Stueck."""
        from piper import SynthesisConfig
        skala = 1.0 / self.tempo_fuer(sprache)
        stimme = self.stimmen[sprache]
        with wave.open(str(datei), "wb") as ziel:
            if self.synth_art == "syn_config":
                stimme.synthesize_wav(
                    text, ziel, syn_config=SynthesisConfig(
                        length_scale=skala,
                        speaker_id=self.sprecher_fuer(sprache)))
            elif self.synth_art == "length_scale":
                stimme.synthesize_wav(text, ziel, length_scale=skala)
            else:
                stimme.synthesize_wav(text, ziel)
        with wave.open(str(datei)) as w:
            return datei, w.getnframes() / w.getframerate()

    def sprechen(self, text, sprache, nummer):
        if self.nur_text or sprache not in self.stimmen:
            return None, 0.0
        if sprache == "fa":
            # Erst hier, nicht frueher: der Uebersetzungsprompt und die
            # Compliance-Messung arbeiten mit der unvokalisierten Form.
            text = vokalisieren(self.glossar, text)

        # Sprechform: nur fuer Piper, nicht fuer den Untertitel.
        # Geschrieben gehoert der volle Name, gesprochen nicht das
        # Initial -- Piper liest ein einzelnes "G." als Buchstaben.
        for muster, ersatz in config.SPRECHFORM.get(sprache, ()):
            text = re.sub(muster, ersatz, text)
        text = zeichen_angleichen(self.stimmennamen.get(sprache, ""), text)

        datei = self.tmp / f"{sprache}_{nummer:05d}.wav"

        # Laengere Pausen an Kommas -- nur fuer Stimmen, die in
        # config.PAUSE_KOMMA_MS stehen. Piper 1.7 kennt dafuer keine
        # Einstellung, also wird der Satz geteilt, jedes Stueck
        # gesprochen und dazwischen Stille eingelegt.
        #
        # Steht die Stimme nicht in der Tabelle -- und fuer de, en,
        # ru und fa steht dort nichts --, laeuft alles wie bisher:
        # ein Aufruf, ein Stueck. Der Zweig darunter wird gar nicht
        # betreten.
        ms = config.PAUSE_KOMMA_MS.get(self.stimmennamen.get(sprache, ""))
        if ms and self.piper == "modul" and "," in text:
            return self._mit_kommapausen(text, sprache, datei, ms)

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
                            length_scale=skala,
                            speaker_id=self.sprecher_fuer(sprache)))
                elif self.synth_art == "length_scale":
                    stimme.synthesize_wav(text, ziel, length_scale=skala)
                else:
                    stimme.synthesize_wav(text, ziel)
            with wave.open(str(datei)) as w:
                return datei, w.getnframes() / w.getframerate()

        from laengenfaktor import sprich
        dauer = sprich(self.piper, self.stimmen[sprache], text, datei,
                       self.tempo_fuer(sprache),
                       sprecher=self.sprecher_fuer(sprache))
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


# Die Aufnahme steckt in aufnahme.py: Einwilligung, Frist und Loeschung
# lassen sich dort ohne laufenden Server pruefen, und genau das war
# vorher nicht moeglich. Hier bleibt nur die Verdrahtung.

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
        # Die letzten Abschnitte JE SPRACHE, als Text, ohne Ton (0.5.0).
        # Wer nach einem Funkaussetzer wieder verbindet, bekommt daraus
        # nachgereicht, was er verpasst hat. self.letzte traegt nur den
        # erkannten Satz der Ausgangssprache, nicht die Uebersetzungen.
        # Gleiche Laenge wie dort: was der Server ohnehin vorhaelt.
        self.verpasst = defaultdict(lambda: deque(maxlen=30))
        # Kennung dieses Laufs. Die Abschnittsnummern beginnen nach einem
        # Neustart (oder "Zuruecksetzen") wieder bei 1; ein Handy, das
        # noch "zuletzt Nr. 212" kennt, wuerde sonst alles Neue fuer
        # Doppel halten. Mit der Kennung weiss es, dass neu gezaehlt wird.
        self.lauf_kennung = f"{time.time():.3f}"
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
        self.mitschnitt = aufnahme.Aufnahme(
            config.ERGEBNIS_ORDNER / "predigten", MIKRO_RATE,
            zustandsdatei.laden()[0].get("aufnahme_tage",
                                         aufnahme.TAGE_VORGABE))
        # Das Testprotokoll. Nur im Speicher, NICHT in zustand.json:
        # was den Predigttext mitschreibt, soll nicht aus Versehen
        # ueber einen Sonntag weiterlaufen. Ein Neustart schaltet es
        # ab, und das ist der Sinn.
        self.pruefprotokoll = pruefprotokoll.Protokoll(
            config.ERGEBNIS_ORDNER / "pruefprotokolle")
        # Die Sprachwache. Sie warnt nur, sie schaltet nichts um.
        # Die Warteschlange fuer Fehlerberichte, die im
        # Wartungsfenster von selbst hinausgehen.
        self.berichte = berichtpost.Warteschlange(
            config.ERGEBNIS_ORDNER / "berichte")
        # Was nur die Technik angeht. Steht getrennt, weil es unter
        # Einrichtung erscheint und nicht im Briefkasten.
        self.wartungsbefunde = []
        self.befunde = []
        self.sprachwache = sprachwache.Sprachwache(
            zustandsdatei.laden()[0].get("quelle", config.AUSGANGSSPRACHE))
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
    async def anmelden(self, ws, sprache, seit=None, lauf=None):
        """Ein Handy kommt dazu -- neu oder nach einem Abbruch wieder.

        Mit dem Zustand geht die FASSUNG mit (0.5.0): weicht sie von der
        Seite ab, die das Handy geladen hat, laedt die Seite sich einmal
        neu. Und die Laufkennung, damit das Handy weiss, ob seine
        Abschnittsnummern noch gelten.

        seit/lauf: was das Handy zuletzt bekommen hat. Stimmt der Lauf,
        gehen die Abschnitte danach als Text hinterher -- ohne Ton: der
        waere laengst vorbei und kaeme nur noch als Stau."""
        self.hoerer[sprache].add(ws)
        await self._senden(ws, {"typ": "zustand", "live": self.laeuft,
                                "gesendet": self.n,
                                **self.speicherlage(),
                                "fassung": config.VERSION,
                                "lauf": self.lauf_kennung})
        if seit is None or lauf != self.lauf_kennung:
            return
        for e in list(self.verpasst[sprache]):
            if e["id"] > seit:
                await self._senden(ws, dict(e, typ="segment",
                                            nachgereicht=True))

    def speicherlage(self):
        """Wird gerade etwas von der Predigt gespeichert? Fuer den
        Hinweis auf jedem Handy und am Pult (Nachtrag zu 0.5.0).

        aufnahme:   die Tonaufnahme.
        mitschrift: der Predigttext -- im Testprotokoll (Datei, mit
                    jeder Uebersetzung) oder als Mitschrift im
                    Protokoll (Journal). Bis zum Nachtrag stand nur die
                    Aufnahme auf den Handys, obwohl beide anderen
                    ebenfalls Predigttext festhalten."""
        return {"aufnahme": bool(self.mitschnitt.laeuft),
                "mitschrift": bool(PROTOKOLL_MITSCHRIFT
                                   or self.pruefprotokoll.laeuft)}

    async def speicherlage_melden(self):
        """Allen Handys sofort sagen, was gespeichert wird -- nicht erst
        beim naechsten Zustandswechsel."""
        await self._streuen_alle({"typ": "zustand", "live": self.laeuft,
                                  **self.speicherlage()})

    def nachholbar(self, sprache, nummer, text, dauer):
        """Merkt einen gesendeten Abschnitt fuer das Nachreichen vor."""
        self.verpasst[sprache].append({"id": nummer, "text": text,
                                       "absatz_ende": False,
                                       "dauer": dauer})

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
        if quelle and quelle in getattr(config, "NUR_ZIEL", set()):
            # Whisper kennt sie nicht -- siehe config.NUR_ZIEL. Die
            # bisherige Quelle bleibt, statt dass jeder Abschnitt an der
            # Erkennung scheitert.
            print(f"Sprachwahl: {quelle} kann keine Ausgangssprache sein, "
                  f"es bleibt {self.quelle}.")
            quelle = None
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
        await self.speicherlage_melden()

    async def anhalten(self):
        self.laeuft = False
        # Die Aufnahme geht mit. Wer die Uebersetzung anhaelt, hat den
        # Predigtteil hinter sich -- was danach kommt, ist Gebet oder
        # Abkuendigung, und genau davon sollte nichts mitlaufen. Das
        # ist der zweite Haken im Einwilligungsdialog, und er wird
        # hier eingeloest statt dem Techniker aufgebuerdet.
        if self.mitschnitt.laeuft:
            e = self.mitschnitt.beenden("uebersetzung_angehalten")
            print(f"Aufnahme beendet (Uebersetzung angehalten): "
                  f"{e['datei']}, {e['minuten']} min")
        await self.speicherlage_melden()

    async def zuruecksetzen(self):
        await self.anhalten()
        self.n = 0
        self.begonnen = None
        self.letzte.clear()
        self.verpasst.clear()
        # Die Nummern beginnen von vorn -- also ein neuer Lauf.
        self.lauf_kennung = f"{time.time():.3f}"
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

        # Die Sprachwache. Auch hier: ein einzelnes if, solange sie
        # aus ist, und alles darin gefangen. Sie warnt nur; umgestellt
        # wird die Ausgangssprache von einem Menschen am Pult.
        if self.sprachwache is not None:
            try:
                self.sprachwache.quelle_setzen(self.quelle)
                if self.sprachwache.dran(audiodauer):
                    erkannt, sicher = self.werk.sprache_raten(audio)
                    vorher = self.sprachwache.verdacht
                    if self.sprachwache.melden(erkannt, sicher) and not vorher:
                        print(warnung(self.sprachwache.satz()))
            except Exception as e:
                print(f"        Sprachwache: {str(e)[:70]}")

        # Das Testprotokoll. Ein einzelnes if, solange es aus ist --
        # und was drinnen schiefgeht, faengt segment() selbst ab. Was
        # hier haengt, haengt zwischen dem fertigen Satz und dem Ton,
        # der gleich im Saal ankommt; ein Protokoll, das den
        # Gottesdienst anhaelt, waere schlimmer als gar keins.
        if self.pruefprotokoll.laeuft:
            self.pruefprotokoll.segment(
                nummer, self.quelle, text, audiodauer, stt, gesamt,
                ergebnisse)
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
            self.nachholbar(e["sprache"], nummer, e["text"],
                            nachricht["dauer"])
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

_STIMM_JSON = {}


def _stimm_json(name):
    """Die .onnx.json einer Stimme, einmal gelesen und behalten; leer,
    wenn es sie nicht gibt."""
    if name not in _STIMM_JSON:
        try:
            pfad = config.BASIS / "voices" / f"{name}.onnx.json"
            _STIMM_JSON[name] = json.loads(pfad.read_text(encoding="utf-8"))
        except Exception:
            _STIMM_JSON[name] = {}
    return _STIMM_JSON[name]


def _sprecher_karte(name):
    """Name -> Nummer der Sprecher einer Stimme, aus ihrer .onnx.json."""
    return _stimm_json(name).get("speaker_id_map") or {}


def zeichen_angleichen(name, text):
    """Fuer Stimmen, die Zeichen statt Laute lesen (phoneme_type "text"):
    ein Buchstabe, den die Stimme nicht kennt, wohl aber klein
    geschrieben, wird klein geschrieben.

    Gefunden mit der Hoerprobe zum Nachtrag 0.5.0: uk_UA-ukrainian_tts
    kennt nur Kleinbuchstaben, und Piper laesst jedes unbekannte Zeichen
    stillschweigend weg -- aus "Наступної" wurde "аступної", aus "Ми"
    "и". Bis 0.4.6 sprach Devarenu so. Alle espeak-Stimmen und Twi
    (kennt Grossbuchstaben) bleiben unberuehrt."""
    d = _stimm_json(name)
    if d.get("phoneme_type") != "text":
        return text
    karte = d.get("phoneme_id_map") or {}
    return "".join(z if z in karte or z.lower() not in karte else z.lower()
                   for z in text)


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
        lauf.mitschnitt.schreiben(block, np)
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
        if werk.ERFUNDEN.fullmatch(werk.floskel_kuerzen(text) or text):
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

    # ------------------------------------------- Seiten und Zwischenspeicher
    # Bis 0.4.5 kam client.html ohne Cache-Control, aber mit
    # Last-Modified. Damit darf ein Browser HEURISTISCH speichern,
    # ueblich ist ein Zehntel des Dateialters: eine halbes Jahr
    # unveraenderte Seite gilt fast drei Wochen als frisch. Gesehen in
    # pruefstand/zwischenspeicher_test.py mit einem echten Firefox --
    # nach dem Update zeigte er weiter die alte Seite.
    #
    # "no-cache" heisst NICHT "nicht speichern", sondern "vor jeder
    # Verwendung nachfragen". Die Nachfrage traegt das ETag; ist die
    # Seite unveraendert, antwortet der Server mit 304 und ohne Inhalt.
    # Im Saal geht also bei jedem Aufruf eine kurze Frage ueber das
    # Netz und nicht 100 KB Seite -- spuerbar ist das nicht.
    #
    # Das ETag kommt aus dem INHALT, nicht aus Datum und Groesse wie bei
    # FileResponse. Eine Wiederherstellung mit cp -a oder tar setzt das
    # alte Datum wieder, und eine geaenderte Seite gleicher Laenge saehe
    # dann aus wie die alte.
    NACHFRAGEN = "no-cache"

    def _kennung(inhalt):
        return '"' + hashlib.sha256(inhalt).hexdigest()[:32] + '"'

    def _schon_da(request, kennung):
        frage = request.headers.get("if-none-match", "")
        if not frage:
            return False
        if frage.strip() == "*":
            return True
        return kennung in [t.strip().removeprefix("W/")
                           for t in frage.split(",")]

    def ausliefern(request, inhalt, media_type, kopf=None):
        """Eine Seite oder Datei, die sich mit einem Update aendern kann."""
        if isinstance(inhalt, str):
            inhalt = inhalt.encode("utf-8")
        kennung = _kennung(inhalt)
        h = {"Cache-Control": NACHFRAGEN, "ETag": kennung}
        h.update(kopf or {})
        if _schon_da(request, kennung):
            # Ohne Content-Disposition und ohne Inhalt; nur was der
            # Browser zum Wiederverwenden braucht.
            return Response(status_code=304,
                            headers={"Cache-Control": NACHFRAGEN,
                                     "ETag": kennung})
        return Response(content=inhalt, media_type=media_type, headers=h)

    def datei_ausliefern(request, datei, media_type, dateiname=None):
        kopf = {}
        if dateiname:
            kopf["Content-Disposition"] = f'attachment; filename="{dateiname}"'
        return ausliefern(request, Path(datei).read_bytes(), media_type, kopf)

    @asynccontextmanager
    def systemhinweis_legen(text, text_en=""):
        """Ein Systemhinweis in den Briefkasten, wie der Systemcheck.

        Dieselbe Form wie glossar_nachricht(): als Systemhinweis
        gekennzeichnet, bleibt stehen, bis jemand ihn geoeffnet hat."""
        lauf.nachrichten.append({
            "text": text, "text_en": text_en or text,
            "zeit": time.strftime("%H:%M"), "art": "system",
            "absender": "Devarenu", "gelesen": False})

    # ---------------------------------------------- Berichte von selbst
    # Eine Marke, die beim ordentlichen Herunterfahren verschwindet.
    # Liegt sie beim Start noch da, ist der Dienst vorher nicht sauber
    # gegangen -- abgestuerzt, hart neu gestartet oder der Strom weg.
    # Genau der Fall faellt niemandem auf, und genau er ist
    # interessant.
    LAEUFT_MARKE = config.BASIS / "update" / "dienst-laeuft"

    def bericht_ablegen(anlass):
        """Baut einen Bericht und reiht ihn ein. Faengt alles.

        Ein Bericht ueber einen Fehler darf nie selbst einer werden."""
        try:
            import fehlerbericht as fb
            # pruefen.sh dauert Minuten und gehoert nicht in einen
            # Lauf, der beim Hochfahren nebenher passiert.
            vorher = fb._pruefen_zusammen
            fb._pruefen_zusammen = lambda: ["(uebersprungen)"]
            try:
                text = fb.bauen()
            finally:
                fb._pruefen_zusammen = vorher
            pfad = lauf.berichte.einreihen(anlass, text)
            if pfad:
                print(f"Fehlerbericht vorgemerkt ({anlass}): {pfad.name}")
        except Exception as e:
            print(f"Fehlerbericht liess sich nicht ablegen: {str(e)[:70]}")

    def bericht_beim_start():
        """Zwei Anlaesse, beide beim Hochfahren zu erkennen."""
        try:
            unsauber = LAEUFT_MARKE.exists()
            LAEUFT_MARKE.parent.mkdir(parents=True, exist_ok=True)
            LAEUFT_MARKE.write_text(time.strftime("%Y-%m-%d %H:%M:%S"),
                                    encoding="utf-8")
            if unsauber:
                print(warnung("Der Dienst ist beim letzten Mal nicht "
                              "sauber beendet worden."))
                bericht_ablegen("neustart")
        except Exception:
            pass
        try:
            schwer = [b for b in systemcheck.pruefen()
                      if b.schwere == systemcheck.FEHLT]
            if schwer:
                bericht_ablegen("systemcheck")
        except Exception:
            pass

    def spendenkonto_pruefen():
        """Stimmt die Pruefziffer der IBAN aus config.py?

        Die IBAN steht fest in einer versionierten Datei und laesst
        sich am Pult nicht aendern -- das ist Absicht. Fest heisst
        aber nicht unfehlbar: ein Zahlendreher faellt sonst niemandem
        auf, der QR-Code sieht aus wie immer, und erst die
        Ueberweisung geht schief.

        Bei einem Fehler wird NICHTS geloescht und NICHTS
        abgeschaltet. Es steht am Pult und auf der QR-Seite, und wenn
        auf diesem Rechner ein Meldekanal eingerichtet ist, geht eine
        Nachricht hinaus. Ist keiner eingerichtet, geht keine -- es
        steht kein Meldeziel im Code."""
        global KONTO_GRUND
        ok, grund = spendenkonto.lage(getattr(config, "SPENDE", {}) or {})
        KONTO_GRUND = "" if ok else grund
        if ok:
            return
        print(warnung(f"Das Spendenkonto in config.py ist ungueltig: "
                      f"{grund}. Am Pult und auf der QR-Seite steht ein "
                      f"Hinweis. Es wird nichts abgeschaltet."))
        melder = config.BASIS / "meldung.sh"
        if not (config.BASIS / "meldung.json").exists() or not melder.exists():
            return
        try:
            subprocess.Popen(
                ["bash", str(melder),
                 f"Devarenu {config.VERSION}: Spendenkonto ungueltig",
                 f"Die IBAN in config.py wird beanstandet: {grund}.\n"
                 f"Angezeigt wird sie weiter; am Pult und auf der "
                 f"QR-Seite steht ein Hinweis."],
                cwd=str(config.BASIS),
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    def pruefprotokolle_aufraeumen():
        """Dieselbe Frist wie die Aufnahmen -- derselbe Inhalt.

        Kein Altbestandsschutz noetig: es gibt nichts aus der Zeit
        davor, dieses Protokoll ist neu in 0.3.3."""
        tage = zustandsdatei.laden()[0].get("aufnahme_tage",
                                            pruefprotokoll.TAGE_VORGABE)
        weg = pruefprotokoll.aufraeumen(lauf.pruefprotokoll.ordner, tage)
        if weg:
            print(f"{len(weg)} abgelaufene Testprotokolle geloescht.")

    def aufnahmen_aufraeumen(beim_start=False):
        """Loescht abgelaufene Aufnahmen. Gibt die Nachricht zurueck.

        Beim ERSTEN Start dieser Fassung wird nichts geloescht, was es
        schon vorher gab -- stattdessen beginnt die Frist. Eine
        Fassung, die beim Hochfahren ungefragt Tondateien wegraeumt,
        waere das Gegenteil dessen, wofuer die Einwilligung da ist."""
        stand = zustandsdatei.laden()[0]
        tage = stand.get("aufnahme_tage", aufnahme.TAGE_VORGABE)
        if tage <= 0:
            return None
        ab = stand.get("aufnahme_frist_ab") or 0
        nachricht = None

        if beim_start and not ab:
            alt_liste = aufnahme.altbestand(lauf.mitschnitt.ordner,
                                            time.time())
            ab = time.time()
            stand["aufnahme_frist_ab"] = ab
            zustandsdatei.speichern(stand)
            if alt_liste:
                wann = aufnahme.faellig_am(alt_liste[0], tage, ab)
                nachricht = (
                    f"Es liegen {len(alt_liste)} Aufnahmen aus der Zeit vor "
                    f"diesem Update. Sie werden NICHT sofort geloescht -- "
                    f"die Frist von {tage} Tagen laeuft ab heute, sie gehen "
                    f"also am {wann}. Wer eine davon behalten will, sichert "
                    f"sie vorher. Abrufen nur am Gemeinde-PC selbst.")
                print(warnung(nachricht))

        weg = aufnahme.aufraeumen(lauf.mitschnitt.ordner, tage, ab)
        if weg:
            print(f"Aufnahmen geloescht (aelter als {tage} Tage): "
                  + ", ".join(a["name"] for a in weg))
        return nachricht

    async def aufnahme_huetten():
        """Stuendlich nachsehen: abgelaufen? Platte voll?

        Ein Rechner, der von Freitag bis Sonntag laeuft, soll die
        Frist nicht erst beim naechsten Neustart bemerken."""
        while True:
            await asyncio.sleep(aufnahme.AUFRAEUMEN_ALLE)
            try:
                aufnahmen_aufraeumen()
                pruefprotokolle_aufraeumen()
                frei = lauf.mitschnitt.platz_pruefen()
                if frei is not None:
                    text = (f"Die Aufnahme wurde gestoppt: nur noch "
                            f"{frei / 1024**3:.1f} GB frei. Platz schaffen, "
                            f"bevor wieder aufgenommen wird.")
                    print(fehler(text))
                    systemhinweis_legen(
                        text,
                        f"Recording stopped: only {frei / 1024**3:.1f} GB "
                        f"left. Free up space before recording again.")
            except Exception as e:
                print(warnung(f"Aufnahmen aufraeumen misslang: "
                              f"{str(e)[:100]}"))

    async def lebenszyklus(app):
        aufgabe = asyncio.create_task(lauf.verarbeiten())
        # Eine laufende Aufnahme ueberlebt einen Neustart NICHT. Nach
        # einem Absturz gibt es keinen Menschen, der eingewilligt hat
        # -- also faengt nichts von selbst wieder an. Das ist hier
        # nichts zu tun, sondern etwas zu lassen: die Aufnahme ist
        # beim Start immer aus, und der Zettel daneben bleibt bei der
        # abgebrochenen Datei liegen.
        alt_nachricht = aufnahmen_aufraeumen(beim_start=True)
        pruefprotokolle_aufraeumen()
        if alt_nachricht:
            systemhinweis_legen(alt_nachricht)
        bericht_beim_start()
        spendenkonto_pruefen()
        huete = asyncio.create_task(aufnahme_huetten())
        yield
        huete.cancel()
        aufgabe.cancel()
        # Der Aufseher ist ein Daemon-Thread und wuerde auch so mit dem
        # Prozess enden. Ihm hier Bescheid zu sagen erspart beim Neustart
        # des Dienstes den halben Takt, in dem er noch einmal nachsieht.
        try:
            LAEUFT_MARKE.unlink(missing_ok=True)
        except OSError:
            pass
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

    # Eine Drossel je Schreibweg aus dem Saal. Getrennt, weil eine
    # gemeinsame bedeutete, dass eine Zuschrift die Sprachwahl bremst
    # -- zwei Dinge, die nichts miteinander zu tun haben.
    saaldrossel = drossel.Drossel()
    wahldrossel = drossel.Drossel(abstand=1.0, je_geraet=200)

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
            print(warnung("Pult: Anmeldung abgelehnt "
                          f"({geraetekennung(host)})."))
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
        fest = seg.modus == "fest" and seg.feste_schwelle is not None
        lauf.zustand["schwelle"] = {
            "wert": round(seg.feste_schwelle, 5) if fest else None,
            "gemessen": zustandsdatei.jetzt() if fest else None,
            "modus": seg.modus,
            "grundmodus": seg.grundmodus}
        zustandsdatei.speichern(lauf.zustand)

    @app.get("/")
    def wurzel(request: Request):
        if not client.exists():
            return HTMLResponse(f"<h1>client.html fehlt</h1><p>{client}</p>",
                                status_code=500)
        # Die Seite traegt ihre Fassung in sich (0.5.0). Meldet der Server
        # spaeter eine andere -- nach einem Update mit Neustart --, laedt
        # sie sich einmal selbst neu. Ersetzt wird hier und nicht in der
        # Datei: dann kann die Fassung nie neben VERSION herlaufen.
        seite = client.read_text(encoding="utf-8").replace(
            "<!--FASSUNG-->", config.VERSION, 1)
        return ausliefern(request, seite, "text/html; charset=utf-8")

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
    def favicon(request: Request):
        # Sonst steht in jeder Browserkonsole ein 404. Das Logo tut es.
        d = basis / "logo.png"
        if d.exists():
            return datei_ausliefern(request, d, "image/png")
        return Response(status_code=404)

    @app.get("/logo.png")
    def logo(request: Request):
        d = basis / "logo.png"
        if d.exists():
            return datei_ausliefern(request, d, "image/png")
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

    # Offene Stroeme je Adresse. Ein Handy braucht genau einen; beim
    # Sprachwechsel kurz zwei, weil der alte noch schliesst. Acht ist
    # das Vielfache davon und trifft niemanden -- ausser einem Skript,
    # das Verbindungen aufmacht, bis dem Dienst die Dateizeiger
    # ausgehen. Dann stuende der ganze Gottesdienst.
    STROEME_JE_GERAET = 8
    stroeme = {}

    @app.websocket("/strom")
    async def strom(ws: WebSocket):
        sprache = ws.query_params.get("sprache", "")
        if sprache not in lauf.sprachen:
            await ws.close(code=1008)
            return
        adresse = ws.client.host if ws.client else "?"
        if stroeme.get(adresse, 0) >= STROEME_JE_GERAET:
            # 1013 heisst "versuch es spaeter". Die Zuhoererseite
            # verbindet daraufhin mit wachsendem Abstand neu, statt
            # einen Fehler anzuzeigen.
            print(warnung(f"Zu viele Stroeme von "
                          f"{geraetekennung(adresse)}, abgewiesen."))
            await ws.close(code=1013)
            return
        stroeme[adresse] = stroeme.get(adresse, 0) + 1
        await ws.accept()
        if ws.client is not None:
            netzpruefung.beobachten(ws.client.host)
        # Nach einem Abbruch sagt das Handy, was es zuletzt hatte.
        try:
            seit = int(ws.query_params.get("seit", ""))
        except ValueError:
            seit = None
        await lauf.anmelden(ws, sprache, seit,
                            ws.query_params.get("lauf", "") or None)
        try:
            while True:
                await ws.receive_text()
        except (WebSocketDisconnect, Exception):
            pass
        finally:
            lauf.abmelden(ws, sprache)
            uebrig = stroeme.get(adresse, 1) - 1
            if uebrig > 0:
                stroeme[adresse] = uebrig
            else:
                # Nicht auf null stehen lassen: der Zaehler waere sonst
                # eine Adressliste, die nie kleiner wird.
                stroeme.pop(adresse, None)

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
                           or seg.modus == "fest"):
                # Nicht stur auf Automatik: wer ausdruecklich ohne
                # Schwelle faehrt, soll nach einem Mikrofonwechsel nicht
                # unversehens eine bekommen.
                zurueck = seg.grundmodus or "aus"
                seg.modus_setzen(zurueck)
                lauf.zustand["schwelle"] = {"wert": None, "gemessen": None,
                                            "modus": seg.modus,
                                            "grundmodus": seg.grundmodus}
                print(f"Schwelle verworfen: sie galt der alten Tonquelle. "
                      f"Zurueck auf \"{zurueck}\".")
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
            lauf.befunde = []
            lauf.wartungsbefunde = []
            return None
        # Die Marke ueber ALLE Befunde: aendert sich etwas an der
        # Wartungsseite, ist es eine neue Lage, auch wenn der
        # Briefkasten davon nichts zeigt. Sonst gaelte eine
        # Quittierung von vorletzter Woche weiter.
        marke = systemcheck.kennung(befunde)
        # Seit 0.4.2 stehen ALLE Befunde bereit, nicht nur die
        # Wartungspunkte: die Stoerungsansicht am Pult zeigt sie in
        # einfachen Worten, und was nur die Technik angeht, steht
        # darin unter "Fuer den Betreuer".
        def _befund(b):
            return {"kennung": b.kennung,
                    "schwer": b.schwere == systemcheck.FEHLT,
                    "wartung": bool(b.wartung),
                    "laie": bool(getattr(b, "laie", False)),
                    "was": b.was, "was_en": b.was_en,
                    "tun": b.tun, "tun_en": b.tun_en}
        lauf.befunde = [_befund(b) for b in befunde]
        lauf.wartungsbefunde = [_befund(b) for b in befunde if b.wartung]

        # DER BRIEFKASTEN IST NUR FUER DEN SAAL.
        #
        # Bis 0.4.1 legte der Systemcheck seine Befunde dort hinein --
        # "Dienst startet nicht von selbst", "keine automatische
        # Anmeldung". Beides geht den Techniker an, keines den Saal,
        # und beides stand zwischen den Zuschriften der Zuhoerer. Wer
        # drei Wochen lang dieselben zwei Punkte wegklickt, klickt die
        # vierte Woche auch die eine Zeile weg, auf die es ankommt.
        #
        # Seit 0.4.2 stehen die Befunde dort, wo man sie sucht: hinter
        # der Statuspille (Stoerungsansicht), unter Einrichtung ->
        # Fehlersuche, und im Fehlerbericht an den Betreuer. Der
        # Briefkasten traegt nur noch, was ein Mensch geschrieben hat.
        #
        # Der Fingerabdruck bleibt: er haengt an der Nachricht ueber
        # ungepruefte Sprachen, die weiter in den Briefkasten gehoert.
        _ = marke
        return None

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
            # Die Fassung des Servers. Die Seite vergleicht sie schon
            # beim Laden mit ihrer eigenen (G1, 0.5.0).
            "fassung": config.VERSION,
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
                # Taugt sie als Predigtsprache? Nicht, wenn Whisper sie
                # nicht kennt (config.NUR_ZIEL).
                "quelle": sp not in getattr(config, "NUR_ZIEL", set()),
            } for sp, name in sorted(config.SPRACHNAMEN.items(),
                                     key=lambda x: x[1])
                if versuch_erlaubt(sp)],
        }

    def versuch_erlaubt(sp):
        """Darf sp gewaehlt werden? Nein bei einer Versuchssprache
        (config.VERSUCHSSPRACHEN), solange der Schalter aus ist -- es
        sei denn, sie laeuft schon. Was eingeschaltet ist, bleibt
        eingeschaltet; der Systemcheck weist darauf hin."""
        if sp not in getattr(config, "VERSUCHSSPRACHEN", set()):
            return True
        return bool(lauf.zustand.get("versuchssprachen")) or sp in lauf.ziele

    @app.post("/api/sprachwahl")
    async def sprachwahl(daten: dict):
        """Stellt Quell- und Zielsprachen um.

        Alle Stimmen und Glossareintraege liegen auf der Platte; hier wird
        nur ausgewaehlt, was tatsaechlich mitlaeuft. Damit bleibt die
        Rechenzeit dort, wo eine Gemeinde sie braucht, und dasselbe Geraet
        bedient je nach Einstellung einen deutschen oder einen
        anderssprachigen Gottesdienst."""
        ziele = daten.get("ziele")
        if isinstance(ziele, list):
            # Eine Versuchssprache kommt nur bei eingeschaltetem
            # Schalter dazu, auch wenn jemand sie am Pult vorbei schickt.
            weg = [z for z in ziele if not versuch_erlaubt(z)]
            if weg:
                print(f"Sprachwahl: {', '.join(weg)} ist Versuchssprache, "
                      f"der Schalter ist aus.")
                ziele = [z for z in ziele if z not in weg]
        entfallen = lauf.sprachen_setzen(daten.get("quelle"), ziele)
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
    async def nachricht(daten: dict, request: Request):
        """Die Zuschrift aus dem Saal -- der einzige Schreibweg von dort.

        Deshalb gedrosselt. Ein normaler Zuhoerer merkt davon nichts:
        er meldet einmal, vielleicht zweimal. Die Grenzen und ihre
        Begruendung stehen in drossel.py.

        Abgelehnt wird mit einem Grund, nicht still. Wer eine Meldung
        schickt und nichts hoert, schickt sie noch einmal -- und das
        ist genau der Fall, den die Drossel verhindern soll."""
        adresse = request.client.host if request.client else "?"
        darf, grund = saaldrossel.fragen(adresse)
        if not darf:
            return JSONResponse({"grund": grund}, status_code=429)

        text, gekuerzt = drossel.kuerzen(daten.get("text"))
        if not text:
            return JSONResponse({"grund": "leer"}, status_code=400)
        if len(lauf.nachrichten) >= drossel.INSGESAMT:
            # Nicht die aelteste hinauswerfen: der Briefkasten ist
            # voll, weil niemand ihn geleert hat, und genau das
            # gehoert gesagt statt kaschiert.
            return JSONResponse({"grund": "briefkasten_voll"},
                                status_code=429)

        saaldrossel.vermerken(adresse)
        eintrag = {"text": text,
                   "sprache": (daten.get("sprache") or "")[:5],
                   "zeit": time.strftime("%H:%M"),
                   # Ausdruecklich, nicht durch Abwesenheit: das Pult
                   # unterscheidet danach, und "kein Feld" waere eine
                   # Annahme, die beim naechsten Umbau kippt.
                   "art": "saal"}
        lauf.nachrichten.append(eintrag)
        print(f"Nachricht aus dem Saal ({eintrag['sprache'] or '?'}): "
              f"{schutz(eintrag['text'], 200)}")
        return {"angekommen": True, "gekuerzt": gekuerzt}

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

    def befunde_mit_grafik():
        """lauf.befunde plus die aktuellen Hinweise der Grafikwacht.

        Billig: grafikwacht.hinweise() ruft hier nichts auf, sondern
        liest die letzte Messung. Was der Systemcheck beim Start schon
        gemeldet hat, steht nicht doppelt da."""
        try:
            schon = {b["kennung"] for b in lauf.befunde}
            dazu = [{"kennung": h["kennung"], "schwer": False,
                     "wartung": False, "laie": True, "was": h["was"],
                     "was_en": h["was_en"], "tun": h["tun"],
                     "tun_en": h["tun_en"]}
                    for h in grafikwacht.hinweise()
                    if h["kennung"] not in schon]
            return lauf.befunde + dazu
        except Exception:
            return lauf.befunde

    @app.get("/api/zustand")
    def zustand(request: Request):
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
                # Auch fuer die Zuhoererseite: wer mitgeschnitten
                # wird, soll es sehen, ohne das Pult zu kennen.
                "aufnahme": bool(lauf.mitschnitt.laeuft),
                # Predigttext im Testprotokoll oder in der Mitschrift --
                # steht wie die Aufnahme auf den Handys und am Pult.
                "mitschrift": lauf.speicherlage()["mitschrift"],
                "protokoll_mitschrift": PROTOKOLL_MITSCHRIFT,
                "pruefprotokoll": lauf.pruefprotokoll.lage(),
                # Hat jemand Thema und Bibelstellen uebernommen? Ohne sie
                # laeuft alles -- nur ohne den Prompt, der Whisper die
                # Eigennamen des Kapitels vorlegt, und das ist genau der
                # Unterschied zwischen "Sanballat" und "San Ballard".
                "kontext_fehlt": not lauf.werk.stt_prompt,
                "thema_im_prompt": bool(
                    getattr(lauf.werk, "thema_im_prompt", False)),
                "versuchssprachen": bool(
                    lauf.zustand.get("versuchssprachen")),
                # Der Knopf "Jetzt aus dem Netz": steht er zur
                # Verfuegung, und laeuft gerade einer?
                "online_lauf": online_lauf() or None,
                "online_vorgemerkt": (basis / "update" / "online-jetzt").exists(),
                # Ob dieses Pult ueberhaupt am Gemeinde-PC selbst
                # offen ist. Der Schalter wird sonst gar nicht
                # angezeigt -- ein Knopf, der immer "geht nicht"
                # sagt, ist schlechter als keiner.
                "am_rechner": pultschutz.vom_rechner_selbst(
                    request.client.host if request.client else ""),
                "wartung": lauf.wartungsbefunde,
                # Alles, was der Systemcheck gefunden hat -- fuer die
                # Stoerungsansicht hinter der Statuspille. Dazu die
                # Hinweise der Grafikwacht aus dem LAUFENDEN Betrieb:
                # der Systemcheck sieht nur den Start, eng wird es
                # aber mitten im Gottesdienst.
                "befunde": befunde_mit_grafik(),
                "gemeinde": lauf.zustand.get("gemeinde", ""),
                "kontakt": lauf.zustand.get("kontakt", ""),
                "nutzung_melden": bool(lauf.zustand.get("nutzung_melden")),
                "spendenkonto": KONTO_GRUND,
                "sprachverdacht": (lauf.sprachwache.satz()
                                   if lauf.sprachwache else ""),
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
                # Wie verstaendlich die Uebersetzung heute ankommt,
                # je Sprache. Zwei Zahlen, sonst nichts.
                "rueckmeldung": rueckmeldung.stand(),
                # Wie voll die Grafikkarte heute wurde. None, wenn es
                # keine gibt oder nvidia-smi fehlt.
                "grafik": grafikwacht.heute(),
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
                "fest": seg.modus == "fest",
                "modus": seg.modus,
                "grundmodus": seg.grundmodus,
                # Wann zuletzt eingemessen wurde. Eine Schwelle von heute
                # frueh ist etwas anderes als eine vom letzten Jahr.
                "gemessen": (lauf.zustand.get("schwelle") or {}).get("gemessen"),
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
        # Der ausdrueckliche Weg: {"modus": "aus"|"automatisch"|"fest"}.
        # "automatisch": true und ein nackter Wert bleiben erhalten --
        # ein Pult aus einer aelteren Fassung soll weiter bedienbar sein.
        modus = daten.get("modus")
        if modus is None:
            modus = "automatisch" if daten.get("automatisch") else "fest"
        wert = daten.get("wert")
        seg.modus_setzen(modus, wert if wert is not None else None)
        schwelle_sichern()
        return {"schwelle": round(seg.schwelle, 5),
                "fest": seg.modus == "fest",
                "modus": seg.modus,
                "grundmodus": seg.grundmodus}

    @app.post("/api/mitschnitt")
    async def mitschnitt(daten: dict):
        """Aufnahme starten oder beenden.

        Starten geht NUR mit beiden Haken. Die Pruefung steht in
        aufnahme.py und damit im Server, nicht in der Oberflaeche: das
        Pult haengt im Saalnetz, und eine Pflicht, die sich mit einem
        curl umgehen laesst, ist keine."""
        if daten.get("beenden"):
            e = lauf.mitschnitt.beenden("am Pult beendet")
            if e:
                print(f"Aufnahme beendet: {e['datei']}, {e['minuten']} min")
                await lauf.speicherlage_melden()
            return e or {"lief": False}

        datei, fehler = lauf.mitschnitt.starten(
            aufnahme.Einwilligung.aus_daten(daten.get("einwilligung")))
        if fehler == "einwilligung_fehlt":
            print(warnung("Aufnahme abgelehnt: Einwilligung nicht "
                          "vollstaendig bestaetigt."))
            return JSONResponse({"grund": "einwilligung_fehlt"},
                                status_code=400)
        if fehler == "platz_knapp":
            return JSONResponse({"grund": "platz_knapp"}, status_code=507)
        if fehler:
            return JSONResponse({"grund": fehler}, status_code=500)
        print(f"Aufnahme laeuft: {Path(datei).name} "
              f"(Einwilligung bestaetigt "
              f"{lauf.mitschnitt.einwilligung.zeit})")
        # Die Zuhoerer erfahren es sofort, nicht erst beim naechsten
        # Zustandswechsel. Wer mitgeschnitten wird, soll es sehen.
        await lauf.speicherlage_melden()
        return {"datei": Path(datei).name,
                "einwilligung": lauf.mitschnitt.einwilligung.zeit}

    def nur_am_rechner(request):
        """Aufnahmen gibt es nur am Gemeinde-PC selbst.

        Unabhaengig vom Pult-Passwort, und das ist Absicht: ein
        Passwort kann gesetzt sein oder nicht, kann weitergegeben
        werden oder im Browser gespeichert. Eine Tonaufnahme einer
        Predigt soll das Geraet gar nicht erst verlassen koennen, auf
        dem sie liegt."""
        host = request.client.host if request.client else ""
        return pultschutz.vom_rechner_selbst(host)

    @app.post("/api/gemeinde")
    async def gemeinde_setzen(daten: dict):
        """Name der Gemeinde und der Schalter fuer die Nutzungsmeldung.

        Beides am Pult, beides in zustand.json. Der Name erscheint auf
        der QR-Seite; der Schalter ist per Vorgabe AUS und laesst sich
        jederzeit wieder ausschalten."""
        stand = zustandsdatei.laden()[0]
        if "gemeinde" in daten:
            stand["gemeinde"] = " ".join(
                str(daten.get("gemeinde") or "").split())[:60]
        # Seit 0.5.0: der Kontakt fuer den Datenschutzhinweis.
        if "kontakt" in daten:
            stand["kontakt"] = " ".join(
                str(daten.get("kontakt") or "").split())[:120]
        if "melden" in daten:
            stand["nutzung_melden"] = bool(daten.get("melden"))
        if not zustandsdatei.speichern(stand):
            return JSONResponse({"grund": "nicht_schreibbar"},
                                status_code=500)
        lauf.zustand["gemeinde"] = stand["gemeinde"]
        lauf.zustand["kontakt"] = stand.get("kontakt", "")
        lauf.zustand["nutzung_melden"] = stand["nutzung_melden"]
        print(f"Gemeinde: {stand['gemeinde'] or '(ohne Namen)'}, "
              f"Nutzungsmeldung {'an' if stand['nutzung_melden'] else 'aus'}.")
        return {"gemeinde": stand["gemeinde"],
                "kontakt": stand.get("kontakt", ""),
                "melden": stand["nutzung_melden"]}

    @app.post("/api/pruefprotokoll")
    async def pruefprotokoll_schalten(daten: dict, request: Request):
        """Schaltet das Testprotokoll an oder aus.

        NUR AM RECHNER SELBST. Darin steht der Predigttext und jede
        Uebersetzung davon, Wort fuer Wort -- dieselbe Ueberlegung wie
        bei der Aufnahme: das soll das Geraet gar nicht erst verlassen
        koennen, auf dem es liegt.

        Die Einwilligung wird HIER geprueft und nicht nur im Browser.
        Anders als bei der Aufnahme genuegt EIN Haken: dass die
        sprechende Person gefragt wurde. Der zweite ("nur die
        Predigt") ergibt bei einem Test keinen Sinn."""
        if not nur_am_rechner(request):
            return JSONResponse({"grund": "nur_am_rechner"}, status_code=403)
        if not daten.get("an"):
            lage = lauf.pruefprotokoll.beenden()
            if lage:
                print(f"Testprotokoll beendet: {lage['zeilen']} Zeilen "
                      f"in {lage['minuten']} Minuten.")
            await lauf.speicherlage_melden()
            return {"an": False, "lage": None}

        datei, fehler = lauf.pruefprotokoll.starten(
            daten.get("einwilligung"))
        if fehler:
            return JSONResponse({"grund": fehler}, status_code=400)
        print(warnung(f"Testprotokoll laeuft: {datei.name}. Darin steht "
                      f"der gesprochene Text und jede Uebersetzung."))
        # Wie bei der Aufnahme: die Handys sehen es sofort.
        await lauf.speicherlage_melden()
        return {"an": True, "lage": lauf.pruefprotokoll.lage()}

    @app.get("/api/pruefprotokolle")
    def pruefprotokolle_liste(request: Request):
        if not nur_am_rechner(request):
            return JSONResponse({"grund": "nur_am_rechner"}, status_code=403)
        stand = zustandsdatei.laden()[0]
        tage = stand.get("aufnahme_tage", pruefprotokoll.TAGE_VORGABE)
        liste = pruefprotokoll.protokolle(lauf.pruefprotokoll.ordner)
        return {"tage": tage, "laeuft": lauf.pruefprotokoll.lage(),
                "dateien": [{"name": a["name"], "bytes": a["bytes"],
                             "tage": round(a["tage"], 1)} for a in liste]}

    @app.get("/pruefprotokoll/{name}")
    def pruefprotokoll_holen(name: str, request: Request):
        if not nur_am_rechner(request):
            return JSONResponse({"grund": "nur_am_rechner"}, status_code=403)
        # Kein Pfad aus dem Namen: nur ein Eintrag aus der eigenen
        # Liste zaehlt. Ein "../" darf hier nichts finden.
        for a in pruefprotokoll.protokolle(lauf.pruefprotokoll.ordner):
            if a["name"] == name:
                return FileResponse(str(a["pfad"]),
                                    media_type="application/x-ndjson",
                                    filename=name)
        return JSONResponse({"grund": "unbekannt"}, status_code=404)

    @app.post("/api/aufnahme/tage")
    async def aufnahme_tage(daten: dict, request: Request):
        if not nur_am_rechner(request):
            return JSONResponse({"grund": "nur_am_rechner"}, status_code=403)
        try:
            tage = int(daten.get("tage"))
        except (TypeError, ValueError):
            return JSONResponse({"grund": "keine_zahl"}, status_code=400)
        if tage < 0 or tage > 365:
            return JSONResponse({"grund": "ausserhalb"}, status_code=400)
        stand = zustandsdatei.laden()[0]
        stand["aufnahme_tage"] = tage
        if not zustandsdatei.speichern(stand):
            return JSONResponse({"grund": "nicht_schreibbar"},
                                status_code=500)
        lauf.mitschnitt.tage = tage
        print(f"Aufnahmen werden nach {tage} Tagen geloescht."
              if tage else warnung("Aufnahmen werden NICHT mehr "
                                   "geloescht."))
        aufnahmen_aufraeumen()
        return {"tage": tage}

    @app.get("/api/aufnahmen")
    def aufnahmen_liste(request: Request):
        """Was liegt, wie alt, wann faellig."""
        if not nur_am_rechner(request):
            return JSONResponse({"grund": "nur_am_rechner"}, status_code=403)
        stand = zustandsdatei.laden()[0]
        tage = stand.get("aufnahme_tage", aufnahme.TAGE_VORGABE)
        ab = stand.get("aufnahme_frist_ab") or 0
        liste = aufnahme.aufnahmen(lauf.mitschnitt.ordner)
        lage = lauf.mitschnitt.lage()
        laeuft = lage["datei"] if lage else ""
        return {"tage": tage,
                "liste": [{"name": a["name"],
                           "mb": round(a["bytes"] / 1024 / 1024, 1),
                           "tage": round(a["tage"], 1),
                           # Die laufende Aufnahme bekommt am Pult
                           # keinen Loeschknopf.
                           "laeuft": a["name"] == laeuft,
                           "faellig": aufnahme.faellig_am(a, tage, ab)}
                          for a in liste]}

    @app.post("/api/aufnahme/loeschen")
    async def aufnahme_loeschen(daten: dict, request: Request):
        """Eine Aufnahme von Hand loeschen. Nur am Gemeinderechner selbst.

        Dieselbe Schranke wie beim Herunterladen: wer im Saal sitzt,
        darf eine Predigtaufnahme nicht abrufen, und loeschen schon gar
        nicht. Ein Pult-Passwort wuerde das nicht ersetzen -- es ginge
        im Saalnetz unverschluesselt ueber HTTP.

        Die Rueckfrage steht am Pult, nicht hier: eine Schnittstelle,
        die zweimal gefragt werden will, ist keine Schnittstelle.
        Geloescht wird nur, was in der eigenen Liste steht."""
        if not nur_am_rechner(request):
            return JSONResponse({"grund": "nur_am_rechner"}, status_code=403)
        name = (daten.get("name") or "").strip()
        if not name:
            return JSONResponse({"grund": "kein_name"}, status_code=400)
        lage = lauf.mitschnitt.lage()
        laeuft = lage["datei"] if lage else ""
        gut, grund = aufnahme.loeschen(lauf.mitschnitt.ordner, name, laeuft)
        if not gut:
            # 409 und nicht 400: die Anfrage ist in Ordnung, der
            # Zustand erlaubt sie nur nicht.
            code = 409 if grund == "laeuft" else 404
            return JSONResponse({"grund": grund}, status_code=code)
        # Nur der Dateiname. Was darin gesprochen wurde, gehoert nicht
        # ins Journal -- und der Name steht ohnehin schon in der Liste.
        print(f"Aufnahme geloescht: {name}")
        return {"geloescht": name}

    @app.get("/mitschnitt/{name}")
    def mitschnitt_holen(name: str, request: Request):
        if not nur_am_rechner(request):
            # Kein 404: der Unterschied zwischen "gibt es nicht" und
            # "nicht fuer dich" gehoert gesagt, sonst sucht jemand im
            # Saal den Fehler bei sich.
            return JSONResponse({"grund": "nur_am_rechner"}, status_code=403)
        # Nur Dateinamen ohne Pfadanteile: sonst liesse sich ueber die
        # Adresse jede Datei des Rechners abrufen.
        datei = lauf.mitschnitt.ordner / Path(name).name
        if not datei.exists():
            return JSONResponse({"fehler": "nicht gefunden"}, status_code=404)
        # Seit 0.3.8 sind es MP3-Dateien; der Altbestand ist WAV. Der
        # falsche Typ laesst manche Abspieler stumm bleiben, statt zu
        # sagen, was sie nicht koennen.
        art = "audio/mpeg" if datei.suffix.lower() == ".mp3" else "audio/wav"
        return FileResponse(datei, media_type=art, filename=datei.name)

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
        lauf.werk.stt_kopf = erg["kopf"]
        lauf.werk.stt_namen = list(erg["namen"])
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
            lauf.werk.stt_kopf = neu["kopf"]
            lauf.werk.stt_namen = list(neu["namen"])
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
            "datenschutz": qr_texte.datenschutz(sp),
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
                    + f'<p class=dszeile dir="{richtung}">'
                      f'{html_escape(d["datenschutz"])}</p>'
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

        # "Devarenu . <Gemeinde>", oder nur "Devarenu". Der Name
        # steht in zustand.json und wird am Pult gesetzt.
        gemeinde = (lauf.zustand.get("gemeinde") or "").strip()
        marke_zeile = ("Devarenu · " + html_escape(gemeinde)
                       if gemeinde else "Devarenu")

        # Das Spendenkonto steht fest in config.py. Stimmt die
        # Pruefziffer nicht, sagt die Seite es -- abgeschaltet wird
        # nichts.
        kontohinweis = ""
        konto_ok, konto_grund = spendenkonto.lage(
            getattr(config, "SPENDE", {}) or {})
        if not konto_ok:
            kontohinweis = (
                '<p class=kontowarnung>Das angezeigte Spendenkonto ist '
                'ungültig. Bitte wende dich an den Betreuer.</p>')

        seite = QR_SEITE
        for marke, wert in (
                ("<!--LOGO-->", logo),
                ("<!--MARKE-->", marke_zeile),
                ("<!--KONTOHINWEIS-->", kontohinweis),
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
        # Die Seite am Beamer steht stundenlang offen; nach einem Update
        # soll ein Neuladen die neue bringen, nicht die gespeicherte.
        return ausliefern(request, seite, "text/html; charset=utf-8")

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
        # Denselben Bericht in die Warteschlange. Wer den Kaefer
        # drueckt, hat einen Grund -- und soll ihn nicht auch noch
        # abfotografieren und mailen muessen, damit er ankommt. Die
        # QR-Codes bleiben: sie funktionieren ohne Wartungsfenster.
        lauf.berichte.einreihen("hand", text)

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

    # ------------------------------------------------- Datenschutz (0.5.0)
    # Zwei Stufen, beide von diesem Rechner: das Saalnetz hat kein
    # Internet, ein Verweis nach draussen fuehrte ins Leere. Texte und
    # Begruendung in datenschutz.py. ENTWURF, vor Freigabe durch den
    # Datenschutzbeauftragten -- das steht auf beiden Stufen.
    @app.get("/api/datenschutz")
    def datenschutz_kurz(sprache: str = ""):
        """Stufe 1 fuer das Blatt auf dem Handy, in seiner Sprache."""
        return datenschutz.stufe1(sprache,
                                  lauf.zustand.get("gemeinde", ""),
                                  lauf.zustand.get("kontakt", ""))

    @app.get("/datenschutz")
    def datenschutz_lang(request: Request, sprache: str = "de"):
        """Stufe 2, die ausfuehrliche Fassung, als eigene Seite."""
        return ausliefern(request, datenschutz.stufe2_html(
            sprache, lauf.zustand.get("gemeinde", ""),
            lauf.zustand.get("kontakt", ""), config.VERSION),
            "text/html; charset=utf-8")

    @app.get("/anleitung.pdf")
    def anleitung(request: Request, teil: str = "alles", sprache: str = ""):
        """Die Bedienungsanleitung. Fertig gebaut, liegt im Repo.

        Gebaut wird sie auf dem Arbeitsrechner (bash anleitung_bauen.sh);
        hier wird nur ausgeliefert. Der Gemeinderechner bekommt dafuer
        kein zusaetzliches Paket -- und er hat im Betrieb ohnehin kein
        Netz, ueber das eines nachkommen koennte."""
        # Seit 0.5.0 zwei Druckvorlagen zum Datenschutz, beide Entwurf.
        einzeln = {"aushang": "Devarenu-Aushang-Datenschutz.pdf",
                   "gastprediger": "Devarenu-Gastprediger.pdf"}
        if teil in einzeln:
            name = einzeln[teil]
        elif teil != "zuhoerer":
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
        return datei_ausliefern(request, datei, "application/pdf", name)

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
        will die naechste Zeile sehen und nicht den naechsten Dienst.

        Einschalten nur mit derselben Einwilligung wie beim
        Testprotokoll: die sprechende Person wurde gefragt (Nachtrag zu
        0.5.0). Geprueft HIER, nicht nur im Browser -- eine Pflicht,
        die sich mit einem curl umgehen laesst, ist keine. Ausschalten
        geht immer."""
        global PROTOKOLL_MITSCHRIFT
        an = bool(daten.get("an"))
        if an:
            einwilligung = aufnahme.Einwilligung.aus_daten(
                daten.get("einwilligung"))
            if not einwilligung.person_gefragt:
                print("Mitschrift abgelehnt: Einwilligung nicht bestaetigt.")
                return JSONResponse({"grund": "einwilligung_fehlt"},
                                    status_code=400)
        PROTOKOLL_MITSCHRIFT = an
        lauf.zustand["protokoll_mitschrift"] = an
        zustandsdatei.speichern(lauf.zustand)
        # Der Zeitpunkt, kein Name -- wie beim Testprotokoll.
        print(warnung(f"Mitschrift im Protokoll EINGESCHALTET (Einwilligung "
                      f"bestaetigt {einwilligung.zeit}).") if an
              else "Mitschrift im Protokoll ausgeschaltet.")
        await lauf.speicherlage_melden()
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
        """Der juengere von zwei Staenden, hoechstens einmal je Sekunde.

        ZWEI DATEIEN, NICHT EINE. stand.json schreibt der Stick-Kern
        (stick_update.sh), stand-online.json schreibt aktualisierung.sh
        auf dem Netzweg. Das Pult las bis 0.3.7 nur die erste -- und
        zeigte darum auf einem Rechner, der seit Monaten ueber das Netz
        aktualisiert wird, unverdrossen den letzten Stick-Versuch:
        "Update 0.3.1 ist fehlgeschlagen", obwohl seitdem mehrere
        Fassungen sauber eingespielt wurden. pruefen.sh und der
        Fehlerbericht nehmen schon seit 0.3.5 die juengere; hier fehlte
        es.

        Ausgewaehlt wird in fehlerbericht.juengerer_stand() -- an EINER
        Stelle, damit das Pult und der Fehlerbericht nicht wieder
        auseinanderlaufen. Genau daran lag es: die Auswahl gab es
        schon, nur hier nicht.

        Das Pult fragt /api/zustand mehrmals je Minute ab; ohne den
        Zwischenspeicher laege bei jeder Abfrage ein Dateizugriff dahinter,
        nur damit meistens dasselbe herauskommt."""
        jetzt = time.time()
        if jetzt - stand_zwischen["zeit"] < 1.0:
            return stand_zwischen["wert"]
        import fehlerbericht as fb
        wert = fb.juengerer_stand(basis / "update")
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

    @app.post("/api/thema-im-prompt")
    async def thema_im_prompt(daten: dict):
        """Geht das Thema auch in den Uebersetzungsprompt?

        Vorgabe AUS. Eingeschaltet wird es je Gemeinde, nicht je
        Gottesdienst -- darum steht es in zustand.json."""
        an = bool(daten.get("an"))
        lauf.werk.thema_im_prompt = an
        lauf.zustand["thema_im_prompt"] = an
        zustandsdatei.speichern(lauf.zustand)
        return {"an": an}

    @app.post("/api/versuchssprachen")
    async def versuchssprachen_schalten(daten: dict):
        """Der Schalter "Versuchssprachen" (Nachtrag zu 0.5.0).

        Vorgabe AUS. Ausschalten nimmt eine laufende Versuchssprache
        NICHT heraus -- wer mitten im Gottesdienst den Schalter
        zuruecksetzt, soll keinen Zuhoerer verlieren. Sie verschwindet
        aus der Auswahl, sobald sie am Pult abgewaehlt ist."""
        an = bool(daten.get("an"))
        lauf.zustand["versuchssprachen"] = an
        zustandsdatei.speichern(lauf.zustand)
        print(f"Versuchssprachen: {'an' if an else 'aus'}.")
        return {"an": an}

    @app.post("/api/rueckmeldung")
    async def rueckmeldung_nehmen(daten: dict):
        """Eine Stimme von einem Handy: verstaendlich oder nicht.

        Gezaehlt wird nur, und zwar je Sprache. Keine Adresse, keine
        Kennung, kein Zeitpunkt je Stimme -- aus einer Liste von
        Zeitpunkten laesst sich herauslesen, wer gedrueckt hat, aus
        zwei Zaehlern nicht.

        Dass ein Geraet nur einmal zaehlt, merkt sich das Geraet. Es
        schickt seine alte Stimme mit, und der Zaehler geht zurueck."""
        rueckmeldung.zaehlen(daten.get("sprache", ""),
                             daten.get("wert", ""),
                             daten.get("vorher", ""))
        return {"ok": True}

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

    def online_lauf():
        """Was der Knopf gerade tut, oder {}.

        Geschrieben von wartungsfenster.sh --jetzt, hier nur gelesen --
        wie bei stand.json. Der Umweg ueber eine Datei ist Absicht: das
        Update startet den Dienst neu, und was sich der Server gemerkt
        haette, waere genau dann weg, wenn die Meldung gebraucht wird."""
        try:
            d = json.loads((basis / "update" / "online-lauf.json")
                           .read_text(encoding="utf-8"))
            return d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            return {}

    @app.post("/api/update/online")
    async def update_online(request: Request):
        """Stoesst ein Update ueber das Netz an. Nur am Gemeinderechner.

        DER SERVER BEKOMMT DAFUER KEIN RECHT. Er legt eine Datei in
        seinem eigenen Ordner an -- update/online-jetzt --, und
        devarenu-onlineupdate.timer sieht als root alle 30 Sekunden
        danach. Kein sudo, kein Parameter, den jemand unterschieben
        koennte. Derselbe Weg, den der Stick-Knopf seit 0.2.12 geht.

        Ausdruecklich NICHT per Pult-Passwort aus dem Saal: das
        Passwort ginge dort unverschluesselt ueber HTTP. Wer per
        RustDesk auf den Bildschirm des Rechners sieht, bedient einen
        Browser, der auf dem Rechner laeuft -- fuer den Server ist das
        Loopback, und damit gilt er als am Rechner."""
        if not nur_am_rechner(request):
            return JSONResponse({"grund": "nur_am_rechner"}, status_code=403)
        if lauf.laeuft:
            return JSONResponse({"grund": "uebersetzung"}, status_code=409)
        # Ein zweiter Klick waehrend eines Laufs startet nichts Neues.
        # Die Entscheidung gehoert hierher und nicht in die
        # Oberflaeche: wer zwei Pulte offen hat, sieht auf dem einen
        # noch den Stand von vorhin.
        marke = basis / "update" / "online-jetzt"
        if marke.exists() or online_lauf().get("lage") == "laeuft":
            return JSONResponse({"grund": "laeuft_schon"}, status_code=409)
        try:
            marke.parent.mkdir(parents=True, exist_ok=True)
            marke.write_text("", encoding="utf-8")
        except OSError as e:
            print(f"Update: Marke nicht schreibbar: {str(e)[:120]}")
            return JSONResponse({"grund": "nicht_schreibbar"}, status_code=500)
        print("Update: am Pult auf \"Jetzt aus dem Netz\" gedrueckt.")
        # Laeuft der Timer gar nicht, holt niemand die Marke ab. Das
        # gehoert gesagt, sonst wartet jemand vor einem Knopf, der
        # gedrueckt ist und nichts tut.
        timer = True
        try:
            r = subprocess.run(["systemctl", "is-enabled",
                                "devarenu-onlineupdate.timer"],
                               capture_output=True, text=True, timeout=5)
            timer = r.stdout.strip() == "enabled"
        except Exception:
            pass
        return {"angenommen": True, "timer": timer}

    @app.get("/pult")
    def pult(request: Request):
        return ausliefern(
            request,
            (basis / "pult.html").read_text(encoding="utf-8")
            if (basis / "pult.html").exists() else PULT,
            "text/html; charset=utf-8")

    # Einmal beim Start nachsehen, wie der Rechner eingestellt ist.
    # Die Befunde landen in lauf.befunde und stehen damit hinter der
    # Statuspille, bevor der erste Mensch das Pult oeffnet. In den
    # Briefkasten geht nichts davon -- der traegt nur, was aus dem
    # Saal kommt.
    #
    # Ein Fehler im Systemcheck darf den Server nicht aufhalten -- er
    # ist eine Auskunft, kein Betriebsteil.
    # Mitschreiben, wie voll die Grafikkarte wird -- aber nur,
    # solange uebersetzt wird. Zwischen zwei Gottesdiensten misst es
    # eine Karte im Leerlauf, und das sagt nichts.
    # Gezaehlt werden seit 0.4.6 nur die ZIELsprachen. Bis dahin stand
    # hier "+ 1" fuer die Ausgangssprache, und aus "4 Sprachen" in
    # der Grafikwacht las man vier Zielsprachen, wo es drei waren.
    grafikwacht.anwerfen(lambda: lauf.laeuft, lambda: len(lauf.ziele))

    try:
        systemnachricht()
        schwer = sum(1 for b in lauf.befunde if b["schwer"])
        if lauf.befunde:
            print(f"Systemcheck: {len(lauf.befunde)} Punkt(e), "
                  f"{schwer} davon halten den Betrieb auf.")
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
 .dszeile{margin:.6rem 0 0;font-size:.85rem;opacity:.75;text-align:center}
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
 /* "Devarenu . <Gemeinde>". Klein und unter dem Titel: wer im Saal
    sitzt, weiss, wo er ist -- die Zeile ist fuer den, der ein Foto
    der Wand sieht oder die Seite ausdruckt. Ohne Namen faellt sie
    ganz weg. */
 .marke{font:1rem system-ui,sans-serif;color:var(--grau);
   margin:.1rem 0 0}
 /* Ein ungueltiges Spendenkonto ist kein Grund, dem Zuhoerer etwas
    wegzunehmen -- aber es muss dastehen, bevor jemand ueberweist. */
 .kontowarnung{margin:.4rem 1.2rem;padding:.5rem .8rem;
   border:2px solid #9c2d22;border-radius:.4rem;background:#fdeceb;
   color:#9c2d22;font:1rem/1.35 system-ui,sans-serif}
 @media print{ .kontowarnung{border-width:1pt} }
</style>
<header>
  <img class=logo src="<!--LOGO-->" alt="" onerror="this.remove()">
  <h1>Übersetzung</h1>
  <p class=marke><!--MARKE--></p>
  <div class=streifen></div>
</header>
<!--KONTOHINWEIS-->

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
<p class=dszeile id=datenschutz></p>
 </section>
</main>

<p class=holen><!--HOLEN--></p>

<div class=drucksatz><!--DRUCKSATZ--></div>

<script>
// Die Sprachen, die am Pult eingeschaltet sind, dazu immer Englisch.
// Wer uebersetzt mithoert, liest kein Deutsch -- und Englisch ist die
// Sprache, in der am ehesten jemand mitkommt, dessen eigene fehlt.
const SPRACHEN = <!--SPRACHDATEN-->;
const FELDER = ["titel1","titel2","geduld","internet","hoeren","datenschutz"];
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
<meta name=viewport content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name=color-scheme content=light>
<title>Pult</title>
<style>
/* Das Pult. Vier Reiter, eine Startseite, Farbe nur mit Bedeutung.
   Zuerst fuers Handy gebaut -- so wird es bedient -- danach fuer den
   Laptop. Deshalb steht der Handyfall ohne Medienabfrage da und der
   Laptop in einem min-width-Block darunter.

   Farbregel, die ueberall gilt:
     dunkelblau  nur die EINE Hauptaktion und der aktive Reiter
     gruen/gelb/rot  nur Zustaende, nie Schmuck
     alles uebrige  weiss mit grauem Rand
   Wer sich nicht daran haelt, nimmt der Farbe die Aussage. */
:root{
  /* "light" allein: damit sagt die Seite, dass sie keinen Dunkelmodus
     hat. Chrome laesst seinen erzwungenen Dunkelmodus dann in Ruhe,
     statt die Zustandsfarben umzurechnen. */
  color-scheme:light;
  --navy:#141f52;
  --text:#1f2433;
  --grau:#5c6475;      /* 5,9:1 auf Weiss -- die hellste erlaubte Schrift */
  --hell:#9aa3b2;      /* nur Linien und Flaechen, nie Schrift */
  /* ZWEI GRAUS, UND SIE MEINEN VERSCHIEDENES.
     --linie trennt: Zeilen in einer Liste, der Strich unter einem
     Abschnitt. Dass man sie kaum sieht, ist der Zweck.
     --kante begrenzt ein BEDIENELEMENT: einen Knopf, ein Feld, eine
     Kachel. Ein weisser Knopf auf weissem Grund ist nur an seiner
     Kante als Knopf zu erkennen -- ist sie zu blass, sieht man ihn
     nicht. Bis 0.4.2 stand ueberall --linie, auch dort: 1,26:1 auf
     Weiss, also praktisch unsichtbar. WCAG 1.4.11 verlangt fuer
     solche Kanten 3:1; --kante hat 3,6:1 auf Weiss und 3,3:1 auf
     --fl. */
  --linie:#e3e5ea;
  --kante:#7f8796;
  --fl:#f5f6f8;
  --gruen:#146b38; --gruenbg:#e6f4ec;
  --gelb:#8a6208;  --gelbbg:#fdf4dc;
  --rot:#c0392b;   --rotbg:#fbe9e7;
  --link:#1c3a8f;
  --leiste:3.6rem;
  --schild:-apple-system,"Segoe UI",Roboto,system-ui,sans-serif;
  --display:Georgia,"Iowan Old Style","Times New Roman",serif;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--fl);color:var(--text);
     font:16px/1.55 var(--schild)}
[hidden]{display:none !important}
:focus-visible{outline:2px solid var(--navy);outline-offset:2px}
a{color:var(--link)}
/* Georgia traegt die Ueberschriften und die eine Hauptaktion. Alles
   andere laeuft in der Systemschrift: kleine Serifen auf einem
   Handybildschirm liest im Halbdunkel niemand. */
h1,h2,h3{font-family:var(--display);font-weight:400}

/* ---------------------------------------------- Handy ist der Normalfall */
.app{background:#fff;min-height:100dvh;
     padding-bottom:calc(var(--leiste) + env(safe-area-inset-bottom))}

/* Kopf. Am Handy stehen hier nur die Statuspille und die
   Oberflaechensprache -- fuer mehr ist die Zeile zu schmal, und was
   wegfaellt, steht unter Einrichtung. */
/* Umbrechen statt ueberlappen. Bei 150 Prozent Schriftgroesse schob
   sich die Pille bisher ueber "Devarenu" -- ein Kopf, in dem zwei
   Dinge uebereinanderliegen, sieht kaputt aus, ein Kopf in zwei
   Zeilen nur voll. */
.top{display:flex;align-items:center;gap:.4rem .6rem;flex-wrap:wrap;
     padding:.7rem 1rem;padding-top:calc(.7rem + env(safe-area-inset-top));
     background:#fff}
/* Die Unterkante traegt das Band der Urkunde, dieselben drei Farben
   wie der Startknopf. Der einzige Verlauf ausser ihm: Gruen, Gelb und
   Rot bleiben den Zustaenden vorbehalten. */
.app::after{content:none}
.top{border-bottom:3px solid transparent;
     border-image:linear-gradient(100deg,#3b1e73,#1c3a8f 52%,#1fa5d8) 1}
.top .logo{height:28px;width:auto;flex:0 0 auto}
.titel{display:flex;align-items:baseline;gap:.4rem;min-width:0;
       flex:0 1 auto}
.titel b{font:400 1.05rem/1.2 var(--display);letter-spacing:.05em;
         white-space:nowrap}
/* Das kleine "Pult" ist das erste, was weggeht, wenn es eng wird: der
   Name traegt, der Zusatz nicht. */
.titel span{font-size:.75rem;color:var(--grau);white-space:nowrap}
@media (max-width:460px){ .titel span{display:none} }
.meta{display:none;align-items:center;gap:.45rem}
.luecke{margin-inline-start:auto}
.laufzeit{font-size:.8rem;color:var(--grau);
          font-variant-numeric:tabular-nums;white-space:nowrap}
/* Die Pille sagt in einem Wort, was los ist. Sie steht in jedem Reiter
   im Kopf und verschwindet nie. */
/* Die Pille ist ein Knopf: ein Tipp darauf sagt, warum sie so
   aussieht. Ein Zustand, den man nur ansehen darf, hilft niemandem,
   der wissen will, was zu tun ist. */
.pille{flex:0 0 auto;min-height:32px;padding:.25rem .7rem;border:1px solid;
       font:600 .72rem var(--schild);letter-spacing:.08em;cursor:pointer;
       text-transform:uppercase;white-space:nowrap;border-radius:999px}
.pille.hinweis{background:var(--gelbbg);border-color:var(--gelb);
               color:var(--gelb)}
/* Das Zahnrad in der Kachel. Klein, grau, am Rand -- es ist ein Weg,
   keine Handlung. */
.kzahn{flex:0 0 auto;min-width:32px;min-height:32px;margin:-.3rem -.3rem 0 0;
       border:0;background:none;color:var(--grau);font-size:1rem;
       cursor:pointer;line-height:1}
.kzahn:hover{color:var(--text)}
/* Die Stoerungsansicht. Ein Punkt je Problem, darunter in einem Satz,
   was die Technik tun kann. Die Befehle stehen eine Ebene tiefer. */
.stoerpunkt{border:1px solid var(--kante);border-inline-start:4px solid;
  padding:.7rem .85rem;margin:0 0 .6rem;background:var(--fl)}
.stoerpunkt.schwer{border-inline-start-color:var(--rot)}
.stoerpunkt.leicht{border-inline-start-color:var(--gelb)}
.stoerpunkt .was{display:block;font-size:.95rem;line-height:1.45}
.stoerpunkt .tun{display:block;margin-top:.35rem;font:.85rem var(--schild);
  color:var(--grau)}
.stoerpunkt .tun b{color:var(--text)}
.pille.an{background:var(--gruenbg);border-color:var(--gruen);color:var(--gruen)}
.pille.aus{background:var(--fl);border-color:var(--kante);color:var(--grau)}
.pille.kaputt{background:var(--rotbg);border-color:var(--rot);color:var(--rot)}
/* Kopfknoepfe: weiss mit grauem Rand wie jeder Nebenknopf. Mit Wort,
   nicht nur mit Zeichen -- ein Kaefer allein sagt niemandem, dass man
   damit den Betreuer erreicht. */
.ikon{display:inline-flex;align-items:center;gap:.35rem;
      min-height:44px;padding:.35rem .6rem;
      border:1px solid var(--kante);background:#fff;color:var(--grau);
      font:.78rem var(--schild);letter-spacing:.04em;cursor:pointer}
.ikon:hover{border-color:var(--navy);color:var(--text)}
.ikon svg{display:block}

/* Reiterleiste. Am Handy fest unten, mit Zeichen und Wort; die
   Fusszone des Geraets (Home-Balken) ist eingerechnet. */
.reiter{position:fixed;inset-inline:0;bottom:0;z-index:5;
        display:flex;justify-content:space-around;background:#fff;
        border-top:1px solid var(--kante);
        padding-bottom:env(safe-area-inset-bottom)}
.reiter button{flex:1 1 0;min-width:0;min-height:44px;
               display:flex;flex-direction:column;align-items:center;gap:.1rem;
               padding:.45rem .2rem;background:none;border:0;
               border-top:2px solid transparent;cursor:pointer;
               position:relative;color:var(--grau);font:.7rem var(--schild)}
.reiter button[aria-selected=true]{color:var(--navy);font-weight:600;
                                   border-top-color:var(--navy)}
.reiter .sym{font-size:1.15rem;line-height:1}
/* Kein Ellipsenwort. "Gottesd…" ist schlechter als gar kein Wort:
   es sieht nach einem Fehler aus, und das Zeichen darueber sagt
   ohnehin schon, worum es geht. Passt das Wort nicht, traegt der
   Knopf nur noch das Zeichen -- und sein aria-label den Namen. */
.reiter .wort{max-width:100%;white-space:nowrap}
.reiter.nurzeichen .wort{display:none}
.reiter.nurzeichen button{min-height:48px}
.reiter.nurzeichen .sym{font-size:1.4rem}
/* Ein offener Punkt am Reiter. Gelb heisst: dort wartet etwas, das den
   Gottesdienst nicht aufhaelt. Rot steht nie hier, sondern als Banner
   in jedem Reiter. */
.punkt{position:absolute;top:.35rem;inset-inline-end:1.1rem;
       width:7px;height:7px;border-radius:50%;background:var(--gelb)}
.zahl{position:absolute;top:.2rem;inset-inline-end:.35rem;
      min-width:1.1rem;padding:0 .2rem;border-radius:999px;
      background:var(--rot);color:#fff;
      font:600 .62rem/1.1rem var(--schild);text-align:center}
/* Waehrend jemand tippt, ist die Leiste im Weg: die Tastatur schiebt
   das Feld nach oben, und eine feste Leiste legt sich darueber. */
body.tippt .reiter{display:none}
body.tippt .app{padding-bottom:1rem}

.inhalt{padding:1rem}

/* Rote Banner stehen in JEDEM Reiter unter dem Kopf. Gelbe nur im
   Gottesdienst; an den uebrigen Reitern genuegt der Punkt. */
.banner{display:flex;align-items:flex-start;gap:.5rem;flex-wrap:wrap;
        padding:.6rem .8rem;margin:0 0 .6rem;
        border:1px solid;border-inline-start-width:4px;
        font-size:.9rem;line-height:1.45}
.banner.rot{background:var(--rotbg);border-color:var(--rot);color:var(--rot)}
.banner.gelb{background:var(--gelbbg);border-color:var(--gelb);color:var(--gelb)}
.banner a,.banner button.link{color:inherit;font-weight:600}
.banner .wohin{margin-inline-start:auto}

h2{font:600 .72rem var(--schild);text-transform:uppercase;
   letter-spacing:.1em;color:var(--grau);margin:1.6rem 0 .5rem}
.inhalt section>h2:first-child{margin-top:0}

/* Knoepfe. Genau einer ist dunkelblau. */
.btn{display:inline-flex;align-items:center;justify-content:center;gap:.45rem;
     min-height:44px;padding:.6rem 1rem;
     border:1px solid var(--kante);background:#fff;color:var(--text);
     font:.95rem var(--schild);cursor:pointer}
.btn:hover{border-color:var(--navy)}
.btn:disabled{opacity:.45;cursor:default}
.btn.primaer{width:100%;min-height:3.4rem;
             background:var(--navy);border-color:var(--navy);color:#fff;
             font:1.05rem var(--display);letter-spacing:.06em}
.btn.primaer:hover{background:#1c2a6b;border-color:#1c2a6b}
/* "Uebersetzung starten" traegt das Band der Urkunde wie bis 0.4.0.
   Angehalten wird dunkelblau: dieselbe Handlung, aber keine, die
   eingeladen werden muss. */
.btn.primaer.start{background:linear-gradient(100deg,#3b1e73,#1c3a8f 52%,
                   #1fa5d8);border-color:#1c3a8f}
.btn.primaer.start:hover{background:linear-gradient(100deg,#331a64,
                         #17307a 52%,#1b96c6)}
.btn.gefahr{color:var(--rot);border-color:#eccac5}
.btn.gefahr:hover{border-color:var(--rot)}
.btn.an{border-color:var(--navy);box-shadow:inset 0 0 0 1px var(--navy);
        font-weight:600}
.reihe{display:flex;gap:.5rem;flex-wrap:wrap}
.haupt{display:grid;gap:.5rem;margin:0 0 1rem}
/* Die Aufnahme ist die Ausnahme, nicht der Normalfall: weiss, mit
   rotem Ring. Laeuft sie, fuellt sich der Ring. */
/* In Ruhe ist die Aufnahme ein Knopf wie jeder andere: grauer Rand,
   dunkle Schrift. Nur der leere rote Ring sagt, worum es geht. Rot
   gefuellt heisst, dass gerade aufgenommen wird -- und nur dann. */
.rec::before{content:"";width:.75rem;height:.75rem;border-radius:50%;
             border:2px solid var(--rot);flex:0 0 auto}
.rec[aria-pressed=true]{background:var(--rot);border-color:var(--rot);
                        color:#fff}
.rec[aria-pressed=true]::before{background:#fff;border-color:#fff}

/* Kacheln: ein Wort Zustand oben rechts, farbiger Rand an der
   Textanfangsseite -- logisch, damit Farsi nicht springt. */
.kacheln{display:grid;grid-template-columns:1fr;gap:.6rem;margin:0 0 .8rem}
.kachel{background:var(--fl);border:1px solid var(--kante);
        border-inline-start:4px solid var(--kante);padding:.7rem .85rem}
.kachel.ok{border-inline-start-color:var(--gruen)}
.kachel.warn{border-inline-start-color:var(--gelb)}
.kachel.schlecht{border-inline-start-color:var(--rot)}
.kkopf{display:flex;justify-content:space-between;align-items:baseline;
       gap:.5rem;font:600 .7rem var(--schild);text-transform:uppercase;
       letter-spacing:.09em;color:var(--grau)}
/* Der Zustand haengt rechts, neben dem Zahnrad -- nicht in der Mitte
   zwischen Wort und Zahnrad. space-between mit drei Kindern schiebt
   ihn sonst dorthin. */
.zustand{font-weight:600;font-size:.8rem;text-transform:none;letter-spacing:0;
         text-align:end;margin-inline-start:auto}
.kachel.ok .zustand{color:var(--gruen)}
.kachel.warn .zustand{color:var(--gelb)}
.kachel.schlecht .zustand{color:var(--rot)}
.gross{font:400 2rem/1.1 var(--display);margin:.3rem 0 .1rem}
.unterz{font-size:.8rem;color:var(--grau);margin:.3rem 0 0;line-height:1.4}
/* Pegelbalken in der Kachel: Ist-Pegel und die Schwellenmarke.
   Grau = nur Raum, rot = hoerbar aber unter der Schwelle (genau das
   wird weggeworfen), gruen = wird uebersetzt. */
.mini{position:relative;height:10px;background:#dde0e7;margin:.55rem 0 .3rem}
.mini .fuell{display:block;height:100%;width:0;background:var(--hell);
             transition:width .08s linear,background .2s ease}
.mini .fuell.knapp{background:var(--rot)}
.mini .fuell.ueber{background:var(--gruen)}
.mini .marke{position:absolute;top:-3px;bottom:-3px;width:2px;
             background:var(--text);inset-inline-start:0}
.sprachen{display:flex;flex-wrap:wrap;gap:.3rem .7rem;margin-top:.2rem;
          font-size:.82rem;color:var(--grau)}
.sprachen b{color:var(--text);font-variant-numeric:tabular-nums}
/* Die Stimmen der Zuhoerer, je Sprache. Klein und ohne Farbe: sie
   sind eine Auskunft, kein Zustand -- Gruen und Rot gehoeren denen. */
.sprachen s{text-decoration:none;color:var(--grau);font-size:.78rem;
            white-space:nowrap;font-variant-numeric:tabular-nums}

/* Hoechstens ein Satz Erklaerung steht offen da. Der Rest -- und das
   sind die heutigen Erklaertexte, Wort fuer Wort -- haengt hinter
   einem Fragezeichen. Geloescht wird nichts. */
details.hilfe{margin:.5rem 0 0}
details.hilfe>summary{display:flex;align-items:center;gap:.4rem;
  min-height:44px;cursor:pointer;list-style:none;
  font:.78rem var(--schild);color:var(--grau)}
details.hilfe>summary::-webkit-details-marker{display:none}
details.hilfe>summary::before{content:"?";flex:0 0 auto;
  width:1.35rem;height:1.35rem;border:1px solid var(--kante);
  border-radius:50%;display:grid;place-items:center;
  font:600 .75rem var(--schild)}
details.hilfe[open]>summary{color:var(--text)}
details.hilfe>div{border-inline-start:2px solid var(--linie);
  padding-inline-start:.7rem;margin-bottom:.4rem}

.hin{font:.8rem/1.5 var(--schild);color:var(--grau);margin:.6rem 0 0}
.hin.warnung{color:var(--gelb)}
.hin.gut{color:var(--gruen)}
label{display:block;font:.8rem var(--schild);color:var(--grau);
      margin:1rem 0 .3rem}
input[type=text],input[type=password],input[type=number],textarea,select{
  width:100%;font:.95rem var(--schild);padding:.6rem;min-height:44px;
  border:1px solid var(--kante);background:#fff;color:var(--text)}
textarea{min-height:5rem;resize:vertical;line-height:1.5}
input[type=range]{width:100%;min-height:44px}
.zeileein{display:flex;align-items:center;gap:.5rem;flex-wrap:wrap}
.zeileein input[type=number]{width:5.5rem;flex:0 0 auto}
.haken{display:flex;align-items:flex-start;gap:.5rem;
       font:.88rem/1.45 var(--schild);color:var(--text);margin:.8rem 0 0}
.haken input{margin-top:.25rem;flex:0 0 auto;min-height:0;width:auto}

/* Eine Zeile als Verweis, kein Knopf: sie fuehrt woandershin, sie tut
   nichts. */
.link{background:none;border:0;padding:0;margin:0;
      font:inherit;color:var(--link);text-decoration:underline;cursor:pointer}
.zuletzt{display:flex;align-items:center;gap:.5rem;width:100%;
         min-height:44px;padding:.5rem 0;background:none;border:0;
         border-top:1px solid var(--linie);text-align:start;
         font:.85rem var(--schild);color:var(--grau);cursor:pointer}
.zuletzt .satz{flex:1 1 auto;min-width:0;overflow:hidden;
               text-overflow:ellipsis;white-space:nowrap;color:var(--text)}
.zuletzt .sek{font-variant-numeric:tabular-nums;flex:0 0 auto}
.mit{font:.82rem/1.5 var(--schild);color:var(--grau);margin:0 0 .6rem;
     max-height:12rem;overflow:auto}
.mit div{display:flex;gap:.6rem;padding:.3rem 0;
         border-top:1px solid var(--linie)}
.mit .sek{flex:0 0 3rem;font-variant-numeric:tabular-nums;text-align:end}
.leise{margin:1.1rem 0 0;text-align:center}
.leise .btn{border-color:transparent;color:var(--grau);font-size:.8rem}
.leise .btn:hover{border-color:var(--kante)}

/* Was laeuft, muss man sehen, ohne danach zu suchen. */
.laeuftauf{display:flex;align-items:center;gap:.5rem;
  font:.9rem var(--schild);color:var(--rot);background:var(--rotbg);
  border:1px solid var(--rot);padding:.5rem .7rem;margin:.5rem 0}
.laeuftauf .dauer,.laeuftauf #pruefprotokollzeilen{
  margin-inline-start:auto;font-variant-numeric:tabular-nums}
.rotpunkt{width:.7rem;height:.7rem;border-radius:50%;background:var(--rot);
          flex:0 0 auto}
@media (prefers-reduced-motion: no-preference){
  .rotpunkt{animation:pulsen 1.6s ease-in-out infinite}
}
@keyframes pulsen{0%,100%{opacity:1}50%{opacity:.25}}

/* Sprachen als Chips. Gewaehlt wird mit einer Kontur in Dunkelblau und
   einem Haken, nicht mit dunkelblauer Flaeche: die gehoert der einen
   Hauptaktion. */
.chips{display:flex;flex-wrap:wrap;gap:.4rem;margin:.3rem 0}
.chips label{display:inline-flex;align-items:center;gap:.4rem;
  min-height:44px;margin:0;padding:.4rem .7rem;cursor:pointer;
  border:1px solid var(--kante);background:#fff;
  font:.88rem var(--schild);color:var(--text)}
.chips label.an{background:#eef1f8;border-color:var(--navy);font-weight:600}
.chips input{margin:0;width:auto;min-height:0}
.chips .nurtext{font-size:.72rem;color:var(--gelb);white-space:nowrap}
.chips .experiment{font-size:.7rem;color:var(--grau)}
/* Noch nicht geprueft: gestrichelt, unter eigener Ueberschrift. */
.chips.ungeprueft label{border-style:dashed}
.chips.ohneglossar label{border-style:dotted}
.untertitel{font:.75rem var(--schild);color:var(--grau);
            margin:.9rem 0 .2rem;text-transform:none;letter-spacing:0}

/* Einrichtung: links die Liste, rechts die Seite. Am Handy erst die
   Liste, dann die Seite mit Zurueck. */
.zwei{display:block}
.seitennav{display:flex;flex-direction:column;gap:.35rem}
.seitennav button{display:flex;align-items:center;justify-content:space-between;
  gap:.5rem;min-height:48px;padding:.6rem .8rem;text-align:start;
  border:1px solid var(--kante);background:#fff;cursor:pointer;
  font:.95rem var(--schild);color:var(--text)}
.seitennav button[aria-current=page]{background:#eef1f8;
  border-color:var(--navy);font-weight:600}
.seitennav .pfeil{color:var(--hell)}
.zurueck{margin-bottom:.8rem}
.unterseite h3{font:600 .95rem var(--schild);margin:0 0 .6rem;
               color:var(--text)}
/* Abgesetzt: Update und Fehlersuche gehoeren nicht zu dem, was man
   einmal je Gemeinde einstellt. */
.seitennav .trenner{height:1px;background:var(--linie);margin:.5rem 0}

/* Kanalliste der Tonquelle. Die Zeile ist der Knopf. */
.kanal{display:flex;align-items:center;gap:.6rem;width:100%;min-height:44px;
  padding:.5rem .6rem;margin-bottom:.25rem;border:1px solid var(--kante);
  background:#fff;cursor:pointer;text-align:start;flex-wrap:wrap;
  font:.85rem var(--schild);color:var(--text)}
.kanal:hover{border-color:var(--navy)}
.kanal.an{border-color:var(--navy);box-shadow:inset 0 0 0 1px var(--navy)}
.kanal.ruht{opacity:.6;cursor:default}
.kanal .kname{flex:1 1 9rem;min-width:0;overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap}
.kanal .kkanal{flex:0 0 auto;font-size:.76rem;color:var(--grau);
  font-variant-numeric:tabular-nums}
.kanal .mini{flex:1 1 5rem;height:12px;margin:0}
.kanal .kwort{flex:0 0 5rem;text-align:end;font-size:.75rem;color:var(--grau)}
.kanal .kurteil{flex:1 1 100%}
.kanal .ktext{display:block;font-size:.9rem;color:var(--text);line-height:1.35}
.kanal .kmarke{display:block;font-size:.72rem;color:var(--grau)}
.kanal.vermisst{display:block;background:var(--gelbbg);border-color:var(--gelb);
  color:var(--gelb);cursor:default}

/* Aufnahmen und Meldungen aus dem Saal: Listen mit einer Zeile je Stueck. */
.liste .zeile{display:flex;align-items:center;gap:.6rem;flex-wrap:wrap;
  padding:.6rem 0;border-top:1px solid var(--linie);font-size:.9rem}
.liste .zeile .was{flex:1 1 10rem;min-width:0}
.liste .zeile .btn{min-height:44px;padding:.4rem .7rem;font-size:.82rem}
.post{font:.9rem/1.5 var(--schild);margin:.2rem 0 .8rem}
.post div{padding:.5rem .7rem;margin-bottom:.35rem;background:var(--fl);
  border-inline-start:3px solid var(--kante);color:var(--text)}
.post .systempost{border-inline-start-color:var(--navy);background:#eef1f8}
.post .wann{color:var(--grau);font-size:.78rem;margin-inline-end:.4rem}
.post .systempost .wann{color:var(--navy);font-weight:600}
.wartungliste{list-style:none;padding:0;margin:.4rem 0}
.wartungliste li{padding:.45rem 0;border-top:1px solid var(--linie);
  font-size:.88rem;display:flex;flex-direction:column;gap:.2rem}
.wartungliste li.schwer{color:var(--rot)}
.wartungliste code{font-size:.82rem;color:var(--grau);word-break:break-all}
.werte{display:flex;justify-content:space-between;gap:.6rem;
  font:.76rem var(--schild);color:var(--grau);
  font-variant-numeric:tabular-nums;margin:.3rem 0}
.betreuer{margin:.5rem 0 1rem;font-size:1.05rem}
.betreuer code{font-size:.95rem;color:var(--link);word-break:break-all}
.qrpaar{display:flex;gap:1.2rem;flex-wrap:wrap;margin:.4rem 0 1rem}
.qrpaar img{border:1px solid var(--kante);background:#fff;
  width:min(100%,190px);height:auto}
.qrpaar>div{flex:1 1 12rem;max-width:14rem}
/* Der Knopf, der die Datei waehlt. Das nackte Browser-Feld sieht auf
   jedem Geraet anders aus und auf keinem wie ein Knopf. */
.dateiknopf input{position:absolute;width:1px;height:1px;opacity:0;
  overflow:hidden;clip:rect(0 0 0 0)}
dialog#einwilligung{max-width:26rem;width:calc(100vw - 2rem);
  border:1px solid var(--kante);padding:1.3rem;color:var(--text)}
dialog#einwilligung h2{font:400 1.1rem var(--display);color:var(--text);
  text-transform:none;letter-spacing:0;margin:0 0 .4rem}
dialog#einwilligung label{display:flex;gap:.5rem;align-items:flex-start;
  font:.92rem/1.45 var(--schild);color:var(--text);margin:.7rem 0 0}
dialog#einwilligung input[type=checkbox]{margin-top:.25rem;flex:0 0 auto;
  width:auto;min-height:0}
dialog::backdrop{background:rgba(20,31,82,.45)}

/* Der Wartungsblock klappt weiter auf und zu. Er ist kein Erklaertext,
   sondern eine Liste von Befunden -- ein "?" waere dafuer das falsche
   Zeichen. */
h2.klapp{display:flex;justify-content:space-between;align-items:center;
  min-height:44px;cursor:pointer;user-select:none}
.klapptext{display:inline-flex;align-items:center;gap:.35rem;
  font:.72rem var(--schild);text-transform:none;letter-spacing:0;
  color:var(--grau);font-weight:400}
.pfeil{font-size:.9rem;transition:transform .18s ease}
.pfeil.zu{transform:rotate(-90deg)}
/* Umschlag und Zahl im roten Briefkastenband. */
#briefkastenband .umschlag{font-size:1.1rem}
#postzahl{font-weight:700;font-variant-numeric:tabular-nums}
.unterseite h3{font:600 1rem var(--schild);margin:0 0 .7rem}

/* ---------------------------------------------------------- Laptop */
@media (min-width:701px){
  body{padding:0;background:var(--fl)}
  .app{max-width:66rem;margin:1.5rem auto;min-height:0;padding-bottom:0;
       border:1px solid var(--kante)}
  body.tippt .app{padding-bottom:0}
  .top{padding:.9rem 1.4rem}
  .meta{display:flex}
  .reiter{position:static;justify-content:flex-start;gap:.1rem;padding:0 1rem;
          border-top:0;border-bottom:1px solid var(--kante)}
  .reiter button{flex:0 0 auto;flex-direction:row;gap:.45rem;
                 min-height:48px;padding:.7rem 1rem;font-size:.92rem;
                 border-top:0;border-bottom:2px solid transparent}
  .reiter button[aria-selected=true]{border-bottom-color:var(--navy)}
  .reiter .sym{display:none}
  .reiter .punkt{position:static;margin-inline-start:.1rem}
  .reiter .zahl{position:static}
  .inhalt{padding:1.4rem}
  .kacheln{grid-template-columns:repeat(3,1fr)}
  .haupt{grid-template-columns:1fr auto;align-items:stretch}
  .haupt .rec{min-width:11rem}
  .zwei{display:grid;grid-template-columns:14rem 1fr;gap:1.6rem;
        align-items:start}
  .zurueck{display:none}
}
</style>
<div class=app>

<header class=top>
  <img class=logo src="/logo.png" alt="" onerror="this.remove()">
  <div class=titel><b>Devarenu</b><span data-t=pult>Pult</span></div>
  <span class=luecke></span>
  <div class=meta>
    <span class=laufzeit id=laufzeit></span>
    <button class=ikon id=qrknopf onclick=qrOeffnen() data-t=qr_titel
            title="QR-Seite für den Beamer">QR</button>
    <button class="ikon text" id=kaefer onclick=fehlerZeigen()>
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
           stroke="currentColor" stroke-width="2" aria-hidden="true">
        <path d="M8 6a4 4 0 0 1 8 0M5 11h14M12 6v12M6 9a6 6 0 0 0 12 0
                 M4 14h2M18 14h2M6 19l2-2M18 19l-2-2"/></svg>
      <span data-t=fehler_melden>Fehler melden</span></button>
  </div>
  <!-- KEIN data-t: uiZeichnen setzt jedes data-t neu, und die Pille
       haette damit bei jedem Sprachzeichnen wieder "Angehalten"
       gestanden -- gruen, rot, egal. Genau das war in den Bildern zu
       sehen. Ihren Text setzt lies(), und nur lies(). -->
  <button class="pille aus" id=pille onclick=stoerungZeigen()
          aria-haspopup=dialog>Angehalten</button>
  <button class=ikon id=sprachknopf onclick=uiSprache()>EN</button>
</header>

<!-- Vier Reiter. Am Handy feste Leiste unten mit Zeichen und Wort, am
     Laptop eine Zeile unter dem Kopf. Echte Knoepfe mit role=tab: eine
     Liste von Verweisen laesst sich nicht mit den Pfeiltasten bedienen,
     und am Pult steht nicht immer eine Maus. -->
<nav class=reiter role=tablist aria-label="Bereiche">
  <button role=tab id=rGottesdienst aria-selected=true
          aria-controls=gottesdienst onclick="reiterWaehlen('gottesdienst')"
          aria-label="Gottesdienst">
    <span class=sym aria-hidden=true>◉</span>
    <span class=wort data-t=r_gottesdienst>Gottesdienst</span></button>
  <button role=tab id=rVorbereiten aria-selected=false tabindex=-1
          aria-label="Vorbereiten"
          aria-controls=vorbereiten onclick="reiterWaehlen('vorbereiten')">
    <span class=sym aria-hidden=true>✎</span>
    <span class=wort data-t=r_vorbereiten>Vorbereiten</span>
    <span class=punkt id=punktVorbereiten hidden></span></button>
  <button role=tab id=rAufnahmen aria-selected=false tabindex=-1
          aria-label="Aufnahmen"
          aria-controls=aufnahmen onclick="reiterWaehlen('aufnahmen')">
    <span class=sym aria-hidden=true>♫</span>
    <span class=wort data-t=r_aufnahmen>Aufnahmen</span>
    <span class=zahl id=zahlAufnahmen hidden></span></button>
  <button role=tab id=rEinrichtung aria-selected=false tabindex=-1
          aria-label="Einrichtung"
          aria-controls=einrichtung onclick="reiterWaehlen('einrichtung')">
    <span class=sym aria-hidden=true>⚙</span>
    <span class=wort data-t=r_einrichtung>Einrichtung</span>
    <span class=punkt id=punktEinrichtung hidden></span></button>
</nav>

<div class=inhalt>

<!-- Rote Meldungen stehen in JEDEM Reiter. Wer in der Einrichtung
     steht, waehrend der Ton ausfaellt, soll es dort sehen und nicht
     erst, wenn er zufaellig zurueckwechselt. -->
<div id=bannerleiste>
<p class="banner rot" id=rechenwarnung hidden></p>
<p class="banner rot" id=tonhin hidden></p>
<p class="banner rot" id=zweiterdhcp hidden></p>
<p class="banner gelb" id=updatehin hidden></p>
<p class="banner rot" id=briefkastenband hidden>
  <span class=umschlag aria-hidden=true>✉</span>
  <span id=postzahl></span>
  <span data-t=post_neu>neue Meldungen aus dem Saal</span>
  <button class="link wohin" id=briefkasten onclick=postZeigen()
          data-t=post_lesen>Lesen</button></p>
<p class="banner gelb" id=sprachverdacht hidden>
  <span id=sprachverdachttext></span>
  <button class="link wohin" id=bSpracheUm onclick=spracheUmstellen()
          data-t=sprache_umstellen>Ausgangssprache umstellen</button></p>
<p class="banner gelb" id=warnung hidden></p>
</div>

<!-- ============================================= Gottesdienst -->
<section id=gottesdienst role=tabpanel aria-labelledby=rGottesdienst>
<div id=betrieb>
<div class=haupt>
  <button class="btn primaer" id=bStart onclick=umschalten()>Übersetzung starten</button>
  <button class="btn rec" id=bSchnitt onclick=aufnahmeUmschalten()
          aria-pressed="false" data-t=aufnahme>Aufnahme</button>
</div>
<p class=hin id=anhaltenHin data-t=anhalten_hin hidden>Anhalten trennt
niemanden — die Zuhörer bleiben verbunden.</p>
<p class=laeuftauf id=aufnahmelaeuft hidden>
  <span class=rotpunkt aria-hidden=true></span>
  <b data-t=aufnahme_laeuft>Aufnahme läuft</b>
  <span class=dauer id=aufnahmedauer>0:00</span></p>
<!-- Predigttext wird gespeichert (Nachtrag zu 0.5.0): Testprotokoll
     oder Mitschrift im Protokoll. Die Schalter stehen unter
     Fehlersuche; dass etwas laeuft, gehoert aber hierher, wo im
     Gottesdienst jemand hinsieht -- die Handys zeigen es ja auch. -->
<p class=laeuftauf id=mitschriftlaeuft hidden>
  <span class=rotpunkt aria-hidden=true></span>
  <b data-t=ms_laeuft>Predigttext wird gespeichert</b>
  <span id=mitschriftwas></span></p>
<div class=kacheln>
  <div class=kachel id=kTon>
    <div class=kkopf><span data-t=k_ton>Ton</span>
      <span class=zustand id=tonZustand>–</span>
      <!-- Der kurze Weg in die Feineinstellung. Kein Verweis aufs
           Einmessen -- das steht dort und nur dort. -->
      <!-- KEIN data-t: uiZeichnen setzt jedes data-t neu und haette
           das Zeichen durch das Wort "Feineinstellung" ersetzt. Den
           Namen bekommt der Knopf als aria-label und title, beides
           aus derselben Tabelle. -->
      <button class=kzahn id=tonzahn
              onclick="reiterWaehlen('vorbereiten','feineinstellung')"
              title="Feineinstellung"
              aria-label="Feineinstellung">⚙</button></div>
    <div class=mini><span class=fuell id=fuell></span>
      <span class=marke id=marke style="inset-inline-start:0"></span></div>
    <!-- Kein Weg zum Einmessen von hier aus. Gemessen verwirft eine
         eingemessene Schwelle auf einer ruhigen Aufnahme drei Fuenftel
         der Predigt; ein Verweis mitten im Gottesdienst laedt zu
         genau dem ein. Die Kachel sagt den Zustand, mehr nicht. -->
    <p class=unterz><span id=schwellestand></span></p>
    <details class=hilfe><summary data-t=hilfe_ton>Pegel und Schwelle</summary>
      <div>
        <div class=werte><span id=pegelwert>–</span><span id=schwellwert>–</span></div>
        <p class=hin data-t=ton_erklaert>Der Balken zeigt, was ankommt. Die
        Marke ist die Mindestlautstärke: was links davon bleibt, wird nicht
        übersetzt.</p>
      </div></details>
  </div>

  <div class=kachel id=kHoerer>
    <div class=kkopf><span data-t=k_hoerer>Zuhörer</span>
      <span class=zustand id=hoererZustand></span></div>
    <div class=gross id=hoererzahl>0</div>
    <div class=sprachen id=hoerersprachen></div>
    <details class=hilfe><summary data-t=hilfe_hoerer>Je Sprache</summary>
      <div><table><tbody id=zahlen></tbody></table></div></details>
  </div>

  <div class=kachel id=kThema>
    <div class=kkopf><span data-t=k_thema>Thema</span>
      <span class=zustand id=themaZustand></span></div>
    <p class=unterz id=themazeile></p>
    <button class=link id=themalink
            onclick="reiterWaehlen('vorbereiten','kontext')"
            data-t=eintragen>Eintragen</button>
    <details class=hilfe><summary data-t=hilfe_thema>Was erkannt wurde</summary>
      <div><p class=hin id=erkanntkachel></p>
      <p class=hin data-t=kontext_erklaert>Thema und Bibelstellen legen
      Whisper die Eigennamen des Kapitels vor. Das ist der Unterschied
      zwischen „Sanballat“ und „San Ballard“.</p></div></details>
  </div>
</div>

<button class=zuletzt id=zuletztzeile onclick=verlaufKlappen()
        aria-expanded=false aria-controls=mit>
  <span class=kopf data-t=zuletzt>Zuletzt erkannt</span>
  <span class=satz id=zuletzttext>–</span>
  <span class=sek id=zuletztsek></span></button>
<div class=mit id=mit hidden></div>

<p class=leise><button class=btn onclick=vonVorn()
   data-t=reset>Von vorn beginnen …</button></p>
</div>
</section>

<div id=post hidden>
  <button class="btn klein" onclick=postZeigen()
          data-t=zurueck>Zurück</button>
  <h2 data-t=post_ueber>Aus dem Saal</h2>
  <p class=hin data-t=post_hin>Antworten ist nicht vorgesehen. Wer etwas
  meldet, weiß das und erwartet keine Rückmeldung.</p>
  <div class=post id=postliste></div>
  <button class=btn onclick=postLeeren() data-t=post_weg>Erledigt</button>
</div>

<!-- ============================================== Vorbereiten -->
<section id=vorbereiten role=tabpanel aria-labelledby=rVorbereiten hidden>
<h2 data-t=kontext>Thema und Bibelstellen</h2>
<label for=kontext data-t=kontext_label>Worüber wird gepredigt?</label>
<textarea id=kontext placeholder="Predigt über Vergebung. Texte: Matthäus 18, Psalm 32. Namen: Petrus, Nathan."></textarea>
<button class=btn onclick=k() data-t=uebernehmen>Übernehmen</button>
<p class=hin id=erkannt></p>

<h2 data-t=manuskript>Predigtmanuskript</h2>
<p class=hin data-t=manuskript_kurz>Falls der Prediger eines hat.</p>
<label class=dateiknopf><span class=btn data-t=manuskript_waehlen>Manuskript hochladen …</span>
  <input type=file id=datei accept=".txt,.md,.docx" onchange=hochladen()></label>
<p class=hin id=skriptinfo></p>
<details class=hilfe><summary data-t=hilfe_manuskript>Was damit geschieht</summary>
  <div><p class=hin data-t=manuskript_hin>Es wird <b>nicht vorgelesen</b>,
  sondern nur nach Namen und Bibelstellen durchsucht. Daraus entsteht der
  Prompt, mit dem Whisper die Eigennamen trifft. Der Text selbst verlässt
  diesen Rechner nicht.</p></div></details>

<h2 data-t=ton_ueber>Ton</h2>
<details class=hilfe id=feineinstellung><summary data-t=feineinstellung>Feineinstellung</summary>
<div>
<p class=hin data-t=feiner_hin>Nur bei lauten Störgeräuschen. Kann bei
leisen Sprechern viel verwerfen.</p>
<p class=hin id=einmessstand></p>
<button class=btn id=bEinmessen onclick=einmessen()>Einmessen: Prediger sprechen lassen</button>
<div class=mini><span class=fuell id=tonfuell></span>
  <span class=marke id=marke2 style="inset-inline-start:0"></span></div>
<p class=hin id=feinwert></p>
<input type=range id=regler min=0 max=100 value=30 oninput=schieben()>
<div class=reihe>
  <button class="btn klein" id=bAus onclick="schwelleModus('aus')" data-t=m_aus>Aus</button>
  <button class="btn klein" id=bAuto onclick="schwelleModus('automatisch')" data-t=m_auto>Automatisch</button>
  <button class="btn klein" id=bFest onclick="schwelleModus('fest')" data-t=m_fest>Fest</button>
</div>
<p class=hin data-t=modus_hin>„Aus“ heißt: keine Mindestlautstärke,
geschnitten wird an Sprechpausen. „Automatisch“ folgt dem Raumpegel.
„Fest“ hält den Wert, den das Einmessen ergeben hat.</p>
<h3 data-t=tonquelle>Tonquelle</h3>
<div id=kanalliste></div>
<div class=reihe>
  <button class="btn klein" id=bSprache onclick=spracheKnopf()
          data-t=spr_pruefen>Sprache prüfen</button>
</div>
<p class=hin id=sprachstand></p>
<p class=hin id=geraetstand></p>
<details class=hilfe><summary data-t=hilfe_tonquelle>Wie man den Kanal findet</summary>
  <div><p class=hin data-t=tonquelle_hin>Jede Zeile ist ein Kanal.
  Hineinsprechen und zusehen, welche ausschlägt — gemessen wird reihum,
  eine Zeile nach der anderen. „Sprache prüfen“ hört bei jedem Kanal mit
  Pegel zweimal kurz hin und zeigt, was es verstanden hat.</p>
  <p class=hin data-t=spr_hin>Was hier steht, ist gehört, nicht bewiesen.
  Auf Musik erfindet die Erkennung ganze Sätze. Im Zweifel den Text lesen:
  steht dort, was gesprochen wurde, ist es der richtige Kanal.</p></div></details>
</div></details>
</section>

<!-- ================================================ Aufnahmen -->
<section id=aufnahmen role=tabpanel aria-labelledby=rAufnahmen hidden>
<h2 data-t=mitschnitt>Aufnahmen</h2>
<p class=hin id=schnittinfo></p>
<div class="liste" id=aufnahmeliste></div>
<p class=zeileein>
  <span data-t=aufnahme_tage_wort>Löschen nach</span>
  <input type=number id=aufnahmetage min=0 max=365 onchange=aufnahmeTageSetzen()>
  <span data-t=aufnahme_tage_einheit>Tagen</span>
</p>
<details class=hilfe><summary data-t=hilfe_aufnahmen>Was aufgenommen wird</summary>
  <div><p class=hin data-t=aufnahme_hin>Nimmt den Ton mit, der ohnehin
  durchläuft. Nur nach ausdrücklichem Druck und nur mit beiden Häkchen.</p>
  <p class=hin data-t=aufnahme_tage_hin>0 heißt: nicht löschen. Das ist
  eine Entscheidung, keine Vorgabe — dann sammelt sich an, woran niemand
  mehr denkt.</p></div></details>
</section>

<!-- ============================================== Einrichtung -->
<section id=einrichtung role=tabpanel aria-labelledby=rEinrichtung hidden>
<div class=zwei>
<nav class=seitennav id=seitennav aria-label="Einrichtung"></nav>
<div id=einrichtungseite>
<button class="btn klein zurueck" onclick=unterseiteZu()
        data-t=zurueck>Zurück</button>

<div class=unterseite id=eGemeinde hidden>
<h3 data-t=e_gemeinde>Gemeinde</h3>
<label for=gemeindefeld data-t=gemeinde_name>Name der Gemeinde</label>
<input type=text id=gemeindefeld maxlength=60 onchange=gemeindeSetzen()>
<p class="hin" data-t=gemeinde_hin>Erscheint auf der QR-Seite als
„Devarenu · &lt;Name&gt;“. Leer lassen heißt: keine Anzeige.</p>
<label for=kontaktfeld data-t=kontakt_name>Kontakt für Datenschutzfragen</label>
<input type=text id=kontaktfeld maxlength=120 onchange=gemeindeSetzen()>
<p class="hin" data-t=kontakt_hin>Steht mit dem Namen der Gemeinde im
Datenschutzhinweis auf jedem Handy (unter „Mehr“). Etwa eine Mailadresse
oder „Gemeindebüro, Tel. …“. Leer lassen heißt: die Zeile entfällt.</p>
<p class="hin"><a href="/anleitung.pdf?teil=aushang" target=_blank
  data-t=ds_aushang>Aushang Datenschutz (PDF)</a> ·
  <a href="/anleitung.pdf?teil=gastprediger" target=_blank
  data-t=ds_gast>Blatt für Gastprediger (PDF)</a> ·
  <a href="/datenschutz" target=_blank data-t=ds_lang>Ausführlicher
  Hinweis, wie ihn die Handys zeigen</a></p>
<label class=haken><input type=checkbox id=meldeschalter
  onchange=gemeindeSetzen()> <span data-t=melden_an>Nutzung an den
  Entwickler melden</span></label>
<details class=hilfe><summary data-t=hilfe_melden>Was gesendet wird</summary>
  <div><p class="hin" data-t=melden_hin>Gesendet werden <b>Name der
  Gemeinde, Fassung und Datum</b> — sonst nichts. Kein Predigttext, keine
  Zuschriften, keine Adressen. Der Versand läuft im Wartungsfenster über
  denselben Kanal wie die übrigen Meldungen und lässt sich jederzeit
  wieder abschalten.</p></div></details>
<p class="banner rot" id=kontowarnung hidden><span id=kontowarnungtext></span></p>
</div>

<div class=unterseite id=eSprachen hidden>
<h3 data-t=sprachen>Sprachen</h3>
<label for=quellwahl data-t=quelle>Gesprochene Sprache</label>
<select id=quellwahl onchange=sprachenSetzen()></select>
<label data-t=ziele>Übersetzt nach</label>
<div id=zielwahl></div>
<p class=hin data-t=sprachen_hin>Alle Sprachen liegen auf dem Rechner. Nur
die ausgewählten laufen mit, das spart Rechenzeit.</p>
<label class=haken><input type=checkbox id=themaschalter
  onchange=themaSetzen()> <span data-t=thema_an>Thema und Bibelstellen
  auch der Übersetzung mitgeben</span></label>
<p class=hin data-t=thema_hin>Aus. Das Thema geht dann nur an die
Spracherkennung. Eingeschaltet bekommt auch das Übersetzungsmodell
einen Satz dazu — das kann Namen treffsicherer machen und in
Einzelfällen den Abschnitt zum Thema hin verbiegen.</p>
</div>

<div class=unterseite id=eTonquelle hidden>
<h3 data-t=tonquelle>Tonquelle</h3>
<p class=hin data-t=tonquelle_wo>Kanalwahl, Pegel und „Sprache prüfen“
stehen unter Vorbereiten → Feineinstellung.</p>
<button class=btn onclick="reiterWaehlen('vorbereiten','feineinstellung')"
        data-t=ton_feiner>Feineinstellung</button>
</div>

<div class=unterseite id=eWlan hidden>
<h3 data-t=wlan>WLAN &amp; QR-Code</h3>
<p class=hin data-t=wlan_hin>Netzname und Passwort des Routers, an dem
dieser Rechner hängt. Sie wandern in den ersten QR-Code, damit sich die
Handys mit einem Scan verbinden, ohne ein Passwort abzutippen. Ohne
Eintrag zeigt die QR-Seite nur den zweiten Code.</p>
<div class=reihe>
  <input type=text id=ssid placeholder="Netzname" style="flex:1 1 9rem"
         onchange=wlanSetzen()>
  <input type=text id=wpw placeholder="Passwort" style="flex:1 1 9rem"
         onchange=wlanSetzen()>
</div>
<p class=hin id=wlanstand></p>
<p><a class=btn href="/qr" target="_blank" data-t=qr_oeffnen>QR-Seite für
den Beamer öffnen</a></p>
</div>

<div class=unterseite id=ePasswort hidden>
<h3 data-t=pw_ueber>Pult-Passwort (freiwillig)</h3>
<p class=hin data-t=pw_hin>Ohne Eintrag bleibt alles wie bisher: jeder im
Saal-WLAN kann dieses Pult bedienen. Mit Eintrag wird jedes Gerät im Saal
einmal danach gefragt und merkt sich die Anmeldung. Die Zuhörerseite
bleibt immer offen, und an diesem Rechner wird nie gefragt.</p>
<p class=hin id=pwstand></p>
<div class=reihe>
  <input type=password id=pwfeld placeholder="Passwort" style="flex:1 1 9rem"
    autocomplete="new-password">
  <button class=btn onclick=pultPasswortSetzen() data-t=pw_setzen>Übernehmen</button>
</div>
<p><button class="btn gefahr" id=bPwWeg onclick=pultPasswortLoeschen()
  data-t=pw_weg hidden>Passwort entfernen</button></p>
<details class=hilfe><summary data-t=hilfe_pw>Vergessen?</summary>
  <div><p class=hin data-t=pw_vergessen>Am Rechner selbst:
  <code>python werkzeuge/pult_passwort.py --loeschen</code></p></div></details>
</div>

<div class=unterseite id=eUpdate hidden>
<h3 data-t=e_update>Update</h3>
<p class=hin id=fassung></p>
<p class=hin id=updatestand hidden></p>
<button class=btn id=updateknopf onclick=updateJetzt() hidden
        data-t=upd_jetzt>Jetzt einspielen</button>
<!-- Der Weg ueber das Netz. Nur am Gemeinde-PC selbst sichtbar: ein
     Knopf, der aus dem Saal nur "geht nicht" sagt, ist schlechter als
     keiner -- und ein Pult-Passwort wuerde das nicht ersetzen, es ginge
     im Saalnetz unverschluesselt ueber HTTP. -->
<div id=onlinereihe hidden>
  <button class=btn id=onlineknopf onclick=onlineUpdate()
          data-t=on_jetzt>Jetzt aus dem Netz aktualisieren</button>
  <p class=hin id=onlinestand hidden></p>
  <details class=hilfe><summary data-t=hilfe_online>Was dabei geschieht</summary>
    <div><p class=hin data-t=on_hin>Holt die neueste geprüfte Fassung. Der
    Rechner verbindet sich dafür mit dem eingetragenen Wartungs-WLAN;
    steht keines zur Verfügung, wird die Verbindung benutzt, die gerade
    besteht — zum Beispiel ein Handy-Hotspot. Der Dienst startet dabei
    neu. Während einer laufenden Übersetzung geht es nicht.</p></div></details>
</div>
<p><a class=btn href="/anleitung.pdf" download
   data-t=anleitung_pult>Bedienungsanleitung als PDF</a></p>
</div>

<div class=unterseite id=eFehlersuche hidden>
<h3 data-t=e_fehlersuche>Fehlersuche</h3>
<button class=btn onclick=fehlerZeigen() data-t=fehler_melden>Fehler melden</button>
<h2 class=klapp id=wartungKopf onclick=wartungKlappen() hidden>
  <span data-t=wartung>Wartung</span>
  <span class=klapptext><span id=wartungZahl></span>
  <span class="pfeil zu" id=wartungPfeil>▾</span></span></h2>
<div id=wartungFeld hidden>
<ul id=wartungliste class=wartungliste></ul>
<p class=hin data-t=wartung_hin>Diese Punkte halten den Gottesdienst nicht
auf. Sie gehören der Technik und stehen deshalb nicht im Briefkasten.
Vollständig mit: bash pruefen.sh</p>
</div>
<label class=haken><input type=checkbox id=protokollschalter
  onchange=protokollSetzen()> <span data-t=protokoll_an>Mitschrift im
  Protokoll (nur zur Fehlersuche)</span></label>
<p class="hin" id=protokollhin data-t=protokoll_hin>Aus. Der gesprochene
Satz steht dann nicht im Protokoll -- nur seine Länge.</p>
<p class=hin id=pruefprotokollreihe hidden><label class=haken><input
  type=checkbox id=pruefprotokollschalter onchange=pruefprotokollSetzen()>
  <span data-t=pp_an>Testprotokoll schreiben (nur am Gemeinde-PC)</span></label></p>
<p class="hin" id=pruefprotokollhin data-t=pp_hin hidden>Schreibt je
Abschnitt den erkannten Satz, jede Übersetzung und die Dauer jedes
Schrittes in eine Datei. Nur zur Fehlersuche. Es hört von selbst auf,
wenn der Dienst neu startet, und wird nach sieben Tagen gelöscht.</p>
<p class=laeuftauf id=pruefprotokolllaeuft hidden>
  <span class=rotpunkt aria-hidden=true></span>
  <b data-t=pp_laeuft>Testprotokoll läuft</b>
  <span id=pruefprotokollzeilen></span></p>
<h3 id=grafikkopf data-t=grafik_ueber hidden>Grafikkarte</h3>
<p class=hin id=grafikheute hidden></p>
<details class=hilfe id=grafiktage hidden>
  <summary data-t=grafik_tage>Die letzten Tage</summary>
  <div><ul class=wartungliste id=grafikliste></ul></div></details>
<!-- Versuchssprachen (Nachtrag zu 0.5.0): absichtlich hier, zugeklappt
     und hinter der Fehlersuche. Wer Sprachen fuer den Gottesdienst
     sucht, sucht unter Sprachen und soll dort nur finden, was taugt. -->
<details class=hilfe id=erweitert>
  <summary data-t=erweitert>Erweitert</summary>
  <div>
  <label class=haken><input type=checkbox id=versuchsschalter
    onchange=versuchSetzen()> <span data-t=versuch_an>Versuchssprachen
    anbieten</span></label>
  <p class=hin data-t=versuch_hin>Aus. Versuchssprachen (heute Twi) liegen
  mit Stimme auf dem Rechner, aber das Übersetzungsmodell beherrscht sie
  nicht: es wiederholt Wörter, erfindet welche und verfehlt Bibelstellen.
  Für den Gottesdienst taugen sie deshalb nicht — nur zum Ausprobieren,
  zusammen mit jemandem, der die Sprache spricht.</p>
  </div></details>
</div>

</div>
</div>
</section>

<!-- Was gerade nicht stimmt, in einfachen Worten. Erreichbar aus
     JEDEM Reiter, weil die Statuspille in jedem Reiter steht. -->
<div id=stoerung hidden>
<button class="btn klein" onclick=stoerungZeigen() data-t=zurueck>Zurück</button>
<h2 id=stoerungkopf data-t=st_ueber>Was gerade nicht stimmt</h2>
<p class=hin id=stoerungleer data-t=st_nichts hidden>Es steht nichts an.
Der Rechner meldet keine Störung.</p>
<div id=stoerungliste></div>
<details class=hilfe id=stoerungtechnik hidden>
  <summary data-t=st_betreuer>Für den Betreuer</summary>
  <div><ul class=wartungliste id=stoerungtechnikliste></ul></div></details>
</div>

<!-- Keine eigene Reiterseite: der Weg zum Betreuer wird selten
     gebraucht und steht im Kopf und unter Fehlersuche. -->
<div id=fehler hidden>
<button class="btn klein" onclick=fehlerZeigen() data-t=zurueck>Zurück</button>
<h2 data-t=fehler_ueber>Fehler melden</h2>
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
<p><a class=btn id=berichtlink href="/fehlerbericht.txt" download
   data-t=fehler_laden>Fehlerbericht herunterladen</a></p>
<details class=hilfe><summary data-t=hilfe_bericht>Was im Bericht steht</summary>
  <div><p class="hin" data-t=fehler_inhalt>Der Bericht enthält nur
  technische Angaben: Fassung, Rechner, Systemcheck, Meldungen ab
  Warnstufe. Keine Mitschriften, keine Zuschriften aus dem Saal, kein
  WLAN-Passwort.</p>
  <p class="hin" data-t=fehler_offline>Die Mail geht raus, sobald das
  Handy wieder Internet hat. Im Saalnetz bleibt sie im Postausgang
  liegen.</p></div></details>
</div>

</div><!-- .inhalt -->
</div><!-- .app -->

<dialog id=einwilligung>
  <form method=dialog>
    <h2 data-t=ew_titel>Aufnahme starten?</h2>
    <p class=hin data-t=ew_hin>Es wird eine Tonaufnahme der Predigt
    angelegt. Beides muss zutreffen.</p>
    <p><label><input type=checkbox id=ewPerson>
      <span data-t=ew_person>Die predigende Person wurde gefragt und ist
      einverstanden.</span></label></p>
    <p><label><input type=checkbox id=ewNur>
      <span data-t=ew_nur>Ich nehme nur die Predigt auf und schalte vor
      Gebet und Abkündigungen aus.</span></label></p>
    <p class=hin data-t=ew_vermerk>Der Zeitpunkt der Bestätigung wird neben
    der Aufnahme vermerkt. Kein Name.</p>
    <p class="banner rot" id=ewfehler hidden></p>
    <div class=reihe>
      <button class="btn primaer" id=ewStart onclick=aufnahmeBestaetigen()
        data-t=ew_start>Aufnahme starten</button>
      <button class=btn id=ewAb data-t=abbrechen>Abbrechen</button>
    </div>
  </form>
</dialog>
<script>
// Beschriftungen. Nur Deutsch und Englisch, beide von Hand gepflegt: eine
// maschinell falsch uebersetzte Schaltflaeche ist aergerlicher als eine
// englische, die alle verstehen.
const TEXTE={
 de:{pult:"Pult",
   // --- Reiter, Kopf, Zustand (0.4.1) ---
   r_gottesdienst:"Gottesdienst", r_vorbereiten:"Vorbereiten",
   r_aufnahmen:"Aufnahmen", r_einrichtung:"Einrichtung",
   p_an:"Läuft", p_aus:"Angehalten", p_stoerung:"Störung",
   p_hinweis:"Hinweis",
   st_ueber:"Was gerade nicht stimmt",
   st_nichts:"Es steht nichts an. Der Rechner meldet keine Störung.",
   st_betreuer:"Für den Betreuer",
   st_warum:"Antippen: warum steht das hier?",
   st_tun_ton:"Mikrofon und Kabel prüfen, dann die Tonquelle unter "
     +"Vorbereiten → Feineinstellung.",
   st_tun_netz:"Den Zugangspunkt prüfen: er darf keine Adressen "
     +"verteilen.",
   st_tun_betreuer:"Betreuer anrufen. Über „Fehler melden“ geht "
     +"ein Bericht mit allen Angaben raus.",
   st_tun_spaeter:"Hält den Gottesdienst nicht auf. Beim nächsten "
     +"Besuch der Technik.",
   k_still:"still",
   fehler_melden:"Fehler melden", qr_titel:"QR",
   zurueck:"Zurück", eintragen:"Eintragen", uebernehmen:"Übernehmen",
   abbrechen:"Abbrechen",
   pp_hin:"Schreibt je Abschnitt den erkannten Satz, jede Übersetzung und "
     +"die Dauer jedes Schrittes in eine Datei. Nur zur Fehlersuche. Es "
     +"hört von selbst auf, wenn der Dienst neu startet, und wird nach "
     +"sieben Tagen gelöscht.",
   herunterladen:"Herunterladen", post_lesen:"Lesen",
   anzeigefehler:"Anzeigefehler:", achtung:"Achtung:",
   // --- Kacheln ---
   k_ton:"Ton", k_hoerer:"Zuhörer", k_thema:"Thema",
   k_gut:"gut", k_knapp:"knapp", k_kein_ton:"kein Ton",
   k_verzoegerung:"Verzögerung steigt",
   k_fehlt:"fehlt", k_gesetzt:"gesetzt",
   k_namen:"{n} Namen",
   u_titel:"Rückmeldungen: verständlich / schwer verständlich",
   zuletzt:"Zuletzt erkannt",
   hilfe_ton:"Pegel und Schwelle", hilfe_hoerer:"Je Sprache",
   hilfe_thema:"Was erkannt wurde", hilfe_manuskript:"Was damit geschieht",
   hilfe_tonquelle:"Wie man den Kanal findet",
   hilfe_aufnahmen:"Was aufgenommen wird", hilfe_melden:"Was gesendet wird",
   hilfe_pw:"Vergessen?", hilfe_online:"Was dabei geschieht",
   hilfe_bericht:"Was im Bericht steht",
   ton_erklaert:"Der Balken zeigt, was ankommt. Die Marke ist die "
     +"Mindestlautstärke: was links davon bleibt, wird nicht übersetzt.",
   kontext_erklaert:"Thema und Bibelstellen legen Whisper die Eigennamen "
     +"des Kapitels vor. Das ist der Unterschied zwischen „Sanballat“ "
     +"und „San Ballard“.",
   // --- Schwelle: drei Modi ---
   ton_feiner:"Feineinstellung", feineinstellung:"Feineinstellung",
   feiner_hin:"Nur bei lauten Störgeräuschen. Kann bei leisen Sprechern "
     +"viel verwerfen.",
   ton_ueber:"Ton",
   m_aus:"Aus", m_auto:"Automatisch", m_fest:"Fest",
   s_aus:"Schwelle: aus", s_auto:"Schwelle: automatisch",
   s_fest:"Schwelle: fest", s_fest_seit:"Schwelle: fest seit {z}",
   modus_hin:"„Aus“ heißt: keine Mindestlautstärke, geschnitten wird an "
     +"Sprechpausen. „Automatisch“ folgt dem Raumpegel. „Fest“ hält den "
     +"Wert, den das Einmessen ergeben hat.",
   schwelle_wort:"Schwelle", verworfen:"verworfen",
   knapp_darunter:"knapp darunter",
   spricht:"spricht", still:"still",
   eingemessen:"Eingemessen. Nochmal messen",
   messe:"Messe … noch {n} s, jetzt sprechen lassen",
   // --- Vorbereiten ---
   kontext_label:"Worüber wird gepredigt?",
   manuskript_waehlen:"Manuskript hochladen …",
   manuskript_kurz:"Falls der Prediger eines hat.",
   manuskript_hin:"Es wird nicht vorgelesen, sondern nur nach Namen und "
     +"Bibelstellen durchsucht. Daraus entsteht der Prompt, mit dem "
     +"Whisper die Eigennamen trifft. Der Text selbst verlässt diesen "
     +"Rechner nicht.",
   skript_liest:"wird gelesen …",
   skript_gelesen:"{w} Wörter gelesen.",
   skript_stellen:"Stellen:",
   skript_namen:"{b} bekannte und {n} weitere Namen.",
   skript_ging_nicht:"Hochladen fehlgeschlagen.",
   erkannt_keine:"Keine Bibelstelle erkannt. Schreibweise wie "
     +"„1. Samuel 15“ oder „Mt 18“.",
   erkannt_vor:"Erkannt:",
   erkannt_namen:"{n} von {g} Namen im Prompt:",
   // --- Einrichtung ---
   e_gemeinde:"Gemeinde", e_update:"Update", e_fehlersuche:"Fehlersuche",
   grafik_ueber:"Grafikkarte", grafik_tage:"Die letzten Tage",
   grafik_zeile:"Heute höchstens {belegt} von {gesamt} MB belegt "
     +"({voll} %), Auslastung {spitze} % Spitze / {mittel} % mittel, "
     +"{sprachen} Zielsprachen.",
   grafik_cpu:"ein Teil lag auf der CPU.",
   grafik_cpu_lang:"Das Sprachmodell liegt nicht ganz auf der "
     +"Grafikkarte. Die Übersetzung läuft weiter, aber deutlich "
     +"langsamer.",
   thema_an:"Thema und Bibelstellen auch der Übersetzung mitgeben",
   thema_hin:"Aus. Das Thema geht dann nur an die Spracherkennung. "
     +"Eingeschaltet bekommt auch das Übersetzungsmodell einen Satz "
     +"dazu — das kann Namen treffsicherer machen und in Einzelfällen "
     +"den Abschnitt zum Thema hin verbiegen.",
   erweitert:"Erweitert",
   versuch_an:"Versuchssprachen anbieten",
   versuch_hin:"Aus. Versuchssprachen (heute Twi) liegen mit Stimme auf "
     +"dem Rechner, aber das Übersetzungsmodell beherrscht sie nicht: es "
     +"wiederholt Wörter, erfindet welche und verfehlt Bibelstellen. Für "
     +"den Gottesdienst taugen sie deshalb nicht — nur zum Ausprobieren, "
     +"zusammen mit jemandem, der die Sprache spricht.",
   pw_kurz_ueber:"Pult-Passwort",
   tonquelle_wo:"Kanalwahl, Pegel und „Sprache prüfen“ stehen unter "
     +"Vorbereiten → Feineinstellung.",
   reset_frage:"Von vorn beginnen? Zähler, Verlauf sowie Thema und "
     +"Bibelstellen werden zurückgesetzt. Die Zuhörer bleiben verbunden.",
   sprachen:"Sprachen",quelle:"Gesprochene Sprache",
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
   mitschnitt:"Aufnahmen",wlan:"WLAN für die Zuhörer",
   aufnahme:"Aufnahme",
   aufnahme_laeuft:"Aufnahme läuft",
   aufnahme_hin:"Nimmt den Ton mit, der ohnehin durchläuft. Nur mit "
     +"Einwilligung der predigenden Person. Der Schalter steht oben neben "
     +"„Übersetzung starten“.",
   aufnahme_fertig:"{m} Minuten aufgenommen.",
   aufnahme_abgelehnt:"Abgelehnt: die Einwilligung war nicht vollständig "
     +"bestätigt.",
   aufnahme_platz:"Kein Platz mehr. Es wird nicht aufgenommen, bis welcher "
     +"frei ist.",
   aufnahme_keine:"Keine Aufnahmen vorhanden.",
   aufnahme_nur_pc:"Aufnahmen sind nur am Gemeinde-PC selbst abrufbar.",
   aufnahme_faellig:"wird gelöscht am {d}",
   aufnahme_tage_wort:"Löschen nach", aufnahme_tage_einheit:"Tagen",
   aufnahme_tage_hin:"0 heißt: nicht löschen. Das ist eine Entscheidung, "
     +"keine Vorgabe – dann sammelt sich an, woran niemand mehr denkt.",
   ew_titel:"Aufnahme starten?",
   ew_hin:"Es wird eine Tonaufnahme der Predigt angelegt. Beides muss "
     +"zutreffen.",
   ew_person:"Die predigende Person wurde gefragt und ist einverstanden.",
   ew_nur:"Ich nehme nur die Predigt auf und schalte vor Gebet und "
     +"Abkündigungen aus.",
   ew_vermerk:"Der Zeitpunkt der Bestätigung wird neben der Aufnahme "
     +"vermerkt. Kein Name.",
   ew_start:"Aufnahme starten",
   ew_beide:"Beide Punkte müssen bestätigt sein.",
   manuskript:"Predigtmanuskript",start:"Übersetzung starten",
   pause:"Übersetzung anhalten",reset:"Von vorn beginnen …",uebernehmen:"Übernehmen",
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
   anhalten_hin:"Anhalten trennt niemanden — die Zuhörer bleiben "
     +"verbunden.",
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
   sprache_umstellen:"Ausgangssprache umstellen",
   wartung:"Wartung",
   gemeinde_name:"Name der Gemeinde",
   gemeinde_hin:"Erscheint auf der QR-Seite als \u201eDevarenu \u00b7 "
     +"<Name>\u201c. Leer lassen hei\u00dft: keine Anzeige.",
   kontakt_name:"Kontakt f\u00fcr Datenschutzfragen",
   kontakt_hin:"Steht mit dem Namen der Gemeinde im Datenschutzhinweis "
     +"auf jedem Handy (unter \u201eMehr\u201c). Etwa eine Mailadresse oder "
     +"\u201eGemeindeb\u00fcro, Tel. \u2026\u201c. Leer lassen hei\u00dft: "
     +"die Zeile entf\u00e4llt.",
   ds_aushang:"Aushang Datenschutz (PDF)",
   ds_gast:"Blatt f\u00fcr Gastprediger (PDF)",
   ds_lang:"Ausf\u00fchrlicher Hinweis, wie ihn die Handys zeigen",
   melden_an:"Nutzung an den Entwickler melden",
   melden_hin:"Gesendet werden Name der Gemeinde, Fassung und Datum "
     +"\u2014 sonst nichts. Kein Predigttext, keine Zuschriften, keine "
     +"Adressen. Der Versand l\u00e4uft im Wartungsfenster \u00fcber "
     +"denselben Kanal wie die \u00fcbrigen Meldungen und l\u00e4sst "
     +"sich jederzeit wieder abschalten.",
   konto_kaputt:"Das angezeigte Spendenkonto ist ungültig. Bitte wende "
     +"dich an den Betreuer.",
   kontext_fehlt:"Thema und Bibelstellen fehlen. Prediger fragen.",
   on_jetzt:"Jetzt aus dem Netz aktualisieren",
   on_hin:"Holt die neueste geprüfte Fassung. Der Rechner verbindet "
     +"sich dafür mit dem eingetragenen Wartungs-WLAN; steht keines zur "
     +"Verfügung, wird die Verbindung benutzt, die gerade besteht — zum "
     +"Beispiel ein Handy-Hotspot. Der Dienst startet dabei neu. "
     +"Während einer laufenden Übersetzung geht es nicht.",
   on_frage:"Jetzt aus dem Netz aktualisieren? Der Dienst startet dabei "
     +"neu, die Zuhörer sind kurz getrennt.",
   on_vorgemerkt:"Vorgemerkt. Es beginnt in höchstens 30 Sekunden.",
   on_laeuft_netz:"Die Verbindung wird hergestellt …",
   on_laeuft_update:"Das Update läuft. Der Dienst startet dabei neu.",
   on_laeuft:"Das Update läuft …",
   on_laeuft_schon:"Es läuft schon eines. Bitte abwarten.",
   on_uebersetzung:"Erst die Übersetzung anhalten, dann aktualisieren.",
   on_nur_am_rechner:"Das geht nur am Gemeinde-PC selbst.",
   on_nicht_schreibbar:"Die Marke ließ sich nicht schreiben. Platte voll "
     +"oder Rechte verstellt.",
   on_kein_timer:"Angestoßen — aber der Timer dafür läuft nicht, also "
     +"holt es niemand ab. Nachsehen: systemctl status "
     +"devarenu-onlineupdate.timer",
   on_ging_nicht:"Das ging nicht. Mehr steht im Journal.",
   loeschen:"Löschen",
   loeschen_frage:"„{d}“ wirklich löschen? Das lässt sich nicht "
     +"zurücknehmen.",
   loeschen_laeuft:"Diese Aufnahme läuft gerade. Erst beenden.",
   loeschen_nicht_gefunden:"Diese Aufnahme gibt es nicht mehr.",
   loeschen_nur_am_rechner:"Löschen geht nur am Gemeinde-PC selbst.",
   loeschen_ging_nicht:"Das Löschen ging nicht. Mehr steht im Journal.",
   wartung_hin:"Diese Punkte halten den Gottesdienst nicht auf. Sie "
     +"gehören der Technik und stehen deshalb nicht im Briefkasten. "
     +"Vollständig mit: bash pruefen.sh",
   pp_an:"Testprotokoll schreiben (nur am Gemeinde-PC)",
   pp_laeuft:"Testprotokoll läuft",
   ms_laeuft:"Predigttext wird gespeichert",
   ms_pp:"Testprotokoll",
   ms_journal:"Mitschrift im Protokoll",
   ms_handys:"steht auch auf den Handys",
   pp_zeilen:"{n} Abschnitte",
   pp_frage:"Im Testprotokoll steht der gesprochene Text und jede "
     +"Übersetzung davon, Wort für Wort. Wurde die sprechende Person "
     +"gefragt und ist sie einverstanden?",
   pp_nur_rechner:"Nur am Gemeinde-PC selbst zu schalten.",
   pp_abgelehnt:"Ließ sich nicht einschalten.",
   protokoll_hin:"Aus. Der gesprochene Satz steht dann nicht im "
     +"Protokoll – nur seine Länge.",
   protokoll_warn:"EIN. Der gesprochene Satz steht jetzt im Protokoll. "
     +"Nach der Fehlersuche wieder ausschalten; spätestens ein Neustart "
     +"schaltet es ab.",
   ms_frage:"In der Mitschrift steht der Anfang jedes gesprochenen "
     +"Satzes im Protokoll des Rechners, rund vier Wochen lang. Wurde "
     +"die sprechende Person gefragt und ist sie einverstanden?",
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
 en:{pult:"Control desk",
   r_gottesdienst:"Service", r_vorbereiten:"Prepare",
   r_aufnahmen:"Recordings", r_einrichtung:"Setup",
   p_an:"Running", p_aus:"Paused", p_stoerung:"Fault",
   p_hinweis:"Notice",
   st_ueber:"What is not right",
   st_nichts:"Nothing pending. The computer reports no fault.",
   st_betreuer:"For the maintainer",
   st_warum:"Tap: why does this say that?",
   st_tun_ton:"Check microphone and cable, then the audio source under "
     +"Prepare \u2192 Fine tuning.",
   st_tun_netz:"Check the access point: it must not hand out addresses.",
   st_tun_betreuer:"Call the maintainer. \u201cReport a fault\u201d "
     +"sends a report with all the details.",
   st_tun_spaeter:"Does not hold up the service. At the next visit.",
   k_still:"silent",
   fehler_melden:"Report a fault", qr_titel:"QR",
   zurueck:"Back", eintragen:"Enter", uebernehmen:"Apply",
   abbrechen:"Cancel",
   pp_hin:"Writes the recognised sentence, every translation and the "
     +"duration of each step to a file, one line per section. For "
     +"diagnostics only. It stops by itself when the service restarts "
     +"and is deleted after seven days.",
   herunterladen:"Download", post_lesen:"Read",
   anzeigefehler:"Display error:", achtung:"Attention:",
   k_ton:"Audio", k_hoerer:"Listeners", k_thema:"Topic",
   k_gut:"good", k_knapp:"tight", k_kein_ton:"no audio",
   k_verzoegerung:"delay rising",
   k_fehlt:"missing", k_gesetzt:"set",
   k_namen:"{n} names",
   u_titel:"Feedback: clear / hard to follow",
   zuletzt:"Last recognised",
   hilfe_ton:"Level and threshold", hilfe_hoerer:"Per language",
   hilfe_thema:"What was recognised", hilfe_manuskript:"What happens to it",
   hilfe_tonquelle:"How to find the channel",
   hilfe_aufnahmen:"What gets recorded", hilfe_melden:"What is sent",
   hilfe_pw:"Forgotten?", hilfe_online:"What happens",
   hilfe_bericht:"What the report contains",
   ton_erklaert:"The bar shows what arrives. The mark is the minimum "
     +"volume: anything below it is not translated.",
   kontext_erklaert:"Topic and Bible references hand Whisper the proper "
     +"names of the chapter. That is the difference between "
     +"\u201cSanballat\u201d and \u201cSan Ballard\u201d.",
   ton_feiner:"Fine tuning", feineinstellung:"Fine tuning",
   feiner_hin:"Only for loud background noise. May discard a lot when "
     +"someone speaks quietly.",
   ton_ueber:"Audio",
   m_aus:"Off", m_auto:"Automatic", m_fest:"Fixed",
   s_aus:"Threshold: off", s_auto:"Threshold: automatic",
   s_fest:"Threshold: fixed", s_fest_seit:"Threshold: fixed since {z}",
   modus_hin:"\u201cOff\u201d means no minimum volume; cuts happen at "
     +"pauses. \u201cAutomatic\u201d follows the room level. "
     +"\u201cFixed\u201d keeps the calibrated value.",
   schwelle_wort:"Threshold", verworfen:"discarded",
   knapp_darunter:"just below",
   spricht:"speaking", still:"silent",
   eingemessen:"Calibrated. Measure again",
   messe:"Measuring … {n} s left, let them speak now",
   kontext_label:"What is the sermon about?",
   manuskript_waehlen:"Upload manuscript …",
   manuskript_kurz:"If the preacher has one.",
   manuskript_hin:"It is not read aloud, only searched for names and "
     +"Bible references. That is what builds the prompt Whisper uses to "
     +"get proper names right. The text itself never leaves this "
     +"computer.",
   skript_liest:"reading …",
   skript_gelesen:"{w} words read.",
   skript_stellen:"References:",
   skript_namen:"{b} known and {n} further names.",
   skript_ging_nicht:"Upload failed.",
   erkannt_keine:"No Bible reference recognised. Write it like "
     +"\u201c1 Samuel 15\u201d or \u201cMatt 18\u201d.",
   erkannt_vor:"Recognised:",
   erkannt_namen:"{n} of {g} names in the prompt:",
   e_gemeinde:"Congregation", e_update:"Update", e_fehlersuche:"Diagnostics",
   grafik_ueber:"Graphics card", grafik_tage:"The last few days",
   grafik_zeile:"Today at most {belegt} of {gesamt} MB used ({voll} %), "
     +"load {spitze} % peak / {mittel} % average, {sprachen} target languages.",
   grafik_cpu:"part of it was on the CPU.",
   grafik_cpu_lang:"The translation model is not entirely on the "
     +"graphics card. Translation continues, but much more slowly.",
   thema_an:"Give topic and Bible references to the translation too",
   thema_hin:"Off. The topic then only goes to speech recognition. "
     +"Switched on, the translation model gets a sentence about it as "
     +"well \u2014 that can make names more accurate and in rare cases "
     +"bend a passage towards the topic.",
   erweitert:"Advanced",
   versuch_an:"Offer experimental languages",
   versuch_hin:"Off. Experimental languages (currently Twi) are on this "
     +"computer with a voice, but the translation model does not master "
     +"them: it repeats words, invents some and misses Bible references. "
     +"They are therefore not fit for a church service — only for "
     +"trying out, together with someone who speaks the language.",
   pw_kurz_ueber:"Desk password",
   tonquelle_wo:"Channel, level and \u201ccheck language\u201d live under "
     +"Prepare \u2192 Fine tuning.",
   reset_frage:"Start over? Counters, history, topic and Bible references "
     +"are reset. Listeners stay connected.",
   sprachen:"Languages",quelle:"Spoken language",
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
   mitschnitt:"Recordings",wlan:"Wi-Fi for listeners",
   aufnahme:"Record",
   aufnahme_laeuft:"Recording",
   aufnahme_hin:"Records the sound that runs through anyway. Only with the "
     +"consent of the person preaching. The switch is at the top, next to "
     +"“Start translation”.",
   aufnahme_fertig:"{m} minutes recorded.",
   aufnahme_abgelehnt:"Refused: consent was not fully confirmed.",
   aufnahme_platz:"No space left. Nothing is recorded until some is freed.",
   aufnahme_keine:"No recordings.",
   aufnahme_nur_pc:"Recordings can only be retrieved on the church computer "
     +"itself.",
   aufnahme_faellig:"will be deleted on {d}",
   aufnahme_tage_wort:"Delete after", aufnahme_tage_einheit:"days",
   aufnahme_tage_hin:"0 means: do not delete. That is a decision, not a "
     +"default – things then pile up that nobody remembers.",
   ew_titel:"Start recording?",
   ew_hin:"A sound recording of the sermon will be made. Both must apply.",
   ew_person:"The person preaching has been asked and agrees.",
   ew_nur:"I will record the sermon only and switch off before prayer and "
     +"announcements.",
   ew_vermerk:"The time of confirmation is noted next to the recording. No "
     +"name.",
   ew_start:"Start recording",
   ew_beide:"Both points must be confirmed.",
   manuskript:"Sermon manuscript",start:"Start translation",
   pause:"Pause translation",reset:"Start over …",uebernehmen:"Apply",
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
   anhalten_hin:"Pausing disconnects nobody — listeners stay connected.",
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
   sprache_umstellen:"Change source language",
   wartung:"Maintenance",
   gemeinde_name:"Name of the church",
   gemeinde_hin:"Shown on the QR page as \u201cDevarenu \u00b7 "
     +"<name>\u201d. Leave empty for no display.",
   kontakt_name:"Contact for privacy questions",
   kontakt_hin:"Shown with the church name in the privacy notice on every "
     +"phone (under \u201cMore\u201d). For example an e-mail address or "
     +"\u201cChurch office, phone \u2026\u201d. Leave empty to omit the line.",
   ds_aushang:"Privacy poster (PDF, German)",
   ds_gast:"Sheet for guest preachers (PDF, German)",
   ds_lang:"Full notice as the phones show it",
   melden_an:"Report usage to the developer",
   melden_hin:"What is sent: name of the church, version and date "
     +"\u2014 nothing else. It goes out during the maintenance window "
     +"and can be switched off again at any time.",
   konto_kaputt:"The donation account shown is invalid. Please contact "
     +"the maintainer.",
   kontext_fehlt:"Topic and Bible passages are missing. Ask the preacher.",
   on_jetzt:"Update from the network now",
   on_hin:"Fetches the newest verified version. The computer connects to "
     +"the maintenance Wi-Fi for this; if none is available, it uses "
     +"whatever connection is up — a phone hotspot, for instance. The "
     +"service restarts in the process. Not while a translation is running.",
   on_frage:"Update from the network now? The service restarts, so "
     +"listeners are briefly disconnected.",
   on_vorgemerkt:"Queued. It starts within 30 seconds.",
   on_laeuft_netz:"Establishing the connection …",
   on_laeuft_update:"The update is running. The service restarts in the "
     +"process.",
   on_laeuft:"The update is running …",
   on_laeuft_schon:"One is already running. Please wait.",
   on_uebersetzung:"Pause the translation first, then update.",
   on_nur_am_rechner:"This only works on the church computer itself.",
   on_nicht_schreibbar:"The marker could not be written. Disk full or "
     +"permissions changed.",
   on_kein_timer:"Queued — but the timer for it is not running, so "
     +"nothing will pick it up. Check: systemctl status "
     +"devarenu-onlineupdate.timer",
   on_ging_nicht:"That did not work. Details are in the log.",
   loeschen:"Delete",
   loeschen_frage:"Really delete \u201c{d}\u201d? This cannot be undone.",
   loeschen_laeuft:"This recording is running. Stop it first.",
   loeschen_nicht_gefunden:"That recording is gone already.",
   loeschen_nur_am_rechner:"Deleting only works on the church computer "
     +"itself.",
   loeschen_ging_nicht:"Deleting failed. Details are in the log.",
   wartung_hin:"These items do not hold up the service. They belong "
     +"to the technician and are therefore not in the inbox. "
     +"Full list: bash pruefen.sh",
   pp_an:"Write a test log (only on the church PC)",
   pp_laeuft:"Test log is running",
   ms_laeuft:"Sermon text is being stored",
   ms_pp:"test log",
   ms_journal:"transcript in the log",
   ms_handys:"shown on the phones too",
   pp_zeilen:"{n} sections",
   pp_frage:"The test log contains the spoken text and every "
     +"translation of it, word for word. Has the speaker been asked "
     +"and agreed?",
   pp_nur_rechner:"Can only be switched on the church PC itself.",
   pp_abgelehnt:"Could not be switched on.",
   protokoll_hin:"Off. The spoken sentence does not go into the log – "
     +"only its length.",
   protokoll_warn:"ON. The spoken sentence now goes into the log. "
     +"Switch it off again after troubleshooting; a restart switches "
     +"it off at the latest.",
   ms_frage:"The transcript puts the beginning of every spoken sentence "
     +"into the computer's log, for about four weeks. Has the speaker "
     +"been asked and agreed?",
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

// ---------------------------------------------------------- Reiter
// Vier Reiter, eine Unteransicht (Briefkasten oder Fehler melden) kann
// sich davorlegen. Der gewaehlte Reiter steht im Anker der Adresse:
// wer das Pult auf dem Handy neu laedt -- und das passiert, sobald das
// WLAN kurz weg war -- landet dort, wo er war.
const REITER = ["gottesdienst", "vorbereiten", "aufnahmen", "einrichtung"];
const REITERKNOPF = {gottesdienst:"rGottesdienst", vorbereiten:"rVorbereiten",
                     aufnahmen:"rAufnahmen", einrichtung:"rEinrichtung"};
let reiterJetzt = "gottesdienst";
let unteransicht = null;    // "post" | "fehler" | "stoerung" | null

function ansichtZeichnen(){
  for(const n of REITER){
    const abschnitt = document.getElementById(n);
    const knopf = document.getElementById(REITERKNOPF[n]);
    const an = (n === reiterJetzt);
    abschnitt.hidden = !an || unteransicht !== null;
    knopf.setAttribute("aria-selected", String(an));
    // Nur der gewaehlte Reiter haengt in der Tabulatorfolge. Die
    // uebrigen erreicht man mit den Pfeiltasten, so wie es sich fuer
    // eine Reiterleiste gehoert.
    knopf.tabIndex = an ? 0 : -1;
  }
  post.hidden = unteransicht !== "post";
  fehler.hidden = unteransicht !== "fehler";
  stoerung.hidden = unteransicht !== "stoerung";
}

function reiterWaehlen(name, ziel){
  if(!REITER.includes(name)) name = "gottesdienst";
  reiterJetzt = name;
  unteransicht = null;
  // replaceState und nicht location.hash: ein Eintrag je Reiterwechsel
  // fuellt die Zurueck-Taste mit Dingen, die niemand zurueckwill.
  try{ history.replaceState(null, "", "#" + name); }catch(e){}
  ansichtZeichnen();
  // Was hinter dem Reiter liegt, wird erst beim Hinsehen geholt. Wer
  // waehrend des Betriebs ein Mikrofon einsteckt, soll es finden, ohne
  // die Seite neu zu laden.
  if(name === "einrichtung"){ sprachenLaden(); wlanLaden(); updateLaden(); }
  if(name === "aufnahmen") aufnahmenLaden();
  // Der Tonscan macht fremde Geraete auf. Er laeuft nur, solange die
  // Feineinstellung offen ist UND dieser Reiter vorne steht.
  scanSchalten(name === "vorbereiten" && feineinstellung.open);
  if(ziel === "kontext"){
    kontext.focus();
    kontext.scrollIntoView({behavior:"smooth", block:"center"});
  }
  if(ziel === "feineinstellung"){
    feineinstellung.open = true;
    scanSchalten(true);
    feineinstellung.scrollIntoView({behavior:"smooth", block:"start"});
  }
  if(name !== "einrichtung") unterseiteJetzt = unterseiteJetzt;
  uiZeichnen();
}

// Passen die Woerter in die Leiste? Das laesst sich nicht als
// Medienabfrage schreiben: es haengt nicht an der Breite allein,
// sondern auch daran, wie gross jemand seine Schrift gestellt hat.
// Bei 150 Prozent stand in den Pruefbildern "Gottesd…".
function reiterBreitePruefen(){
  const leiste = document.querySelector(".reiter");
  if(!leiste) return;
  leiste.classList.remove("nurzeichen");
  // Am Laptop stehen die Reiter nebeneinander und duerfen wachsen --
  // dort gibt es kein Gedraenge, nur am Handy.
  if(!SCHMAL()) return;
  for(const k of leiste.querySelectorAll("button")){
    const w = k.querySelector(".wort");
    if(w && w.scrollWidth > w.clientWidth + 1){
      leiste.classList.add("nurzeichen");
      return;
    }
  }
}
window.addEventListener("resize", reiterBreitePruefen);

// Pfeiltasten in der Reiterleiste, wie bei einer Reiterleiste ueblich.
document.querySelector(".reiter").addEventListener("keydown", e=>{
  const i = REITER.indexOf(reiterJetzt);
  let j = null;
  if(e.key === "ArrowRight") j = (i + 1) % REITER.length;
  if(e.key === "ArrowLeft")  j = (i - 1 + REITER.length) % REITER.length;
  if(e.key === "Home") j = 0;
  if(e.key === "End")  j = REITER.length - 1;
  if(j === null) return;
  e.preventDefault();
  reiterWaehlen(REITER[j]);
  document.getElementById(REITERKNOPF[REITER[j]]).focus();
});

// Solange ein Textfeld den Fokus hat, verdeckt die feste Leiste es
// nicht: die Tastatur schiebt das Feld nach oben, die Leiste bleibt am
// Rand des Fensters stehen und legt sich darueber.
const TIPPFELDER = "input[type=text],input[type=password],input[type=number],"
                 + "input[type=search],textarea";
document.addEventListener("focusin", e=>{
  if(e.target.matches && e.target.matches(TIPPFELDER))
    document.body.classList.add("tippt");
});
document.addEventListener("focusout", e=>{
  if(e.target.matches && e.target.matches(TIPPFELDER))
    document.body.classList.remove("tippt");
});

// ------------------------------------------- Unterseiten der Einrichtung
const UNTERSEITEN = [
  {id:"eGemeinde",    t:"e_gemeinde"},
  {id:"eSprachen",    t:"sprachen"},
  {id:"eTonquelle",   t:"tonquelle"},
  {id:"eWlan",        t:"wlan"},
  {id:"ePasswort",    t:"pw_kurz_ueber"},
  {id:"trenner"},
  {id:"eUpdate",      t:"e_update"},
  {id:"eFehlersuche", t:"e_fehlersuche"},
];
// Am Laptop steht links die Liste und rechts die Seite, beide immer.
// Am Handy ist erst die Liste da und dann die Seite -- nebeneinander
// bleibt auf 390 Pixeln von beidem zu wenig uebrig.
const SCHMAL = () => window.matchMedia("(max-width:700px)").matches;
let unterseiteJetzt = null;

function unterseitenZeichnen(){
  const t = TEXTE[UI];
  const nav = document.getElementById("seitennav");
  nav.innerHTML = UNTERSEITEN.map(u => u.id === "trenner"
    ? '<span class=trenner></span>'
    : `<button onclick="unterseiteWaehlen('${u.id}')"`
      + (u.id === unterseiteJetzt ? ' aria-current=page' : '')
      + `><span>${t[u.t] || u.t}</span><span class=pfeil>›</span></button>`
  ).join("");
  const schmal = SCHMAL();
  for(const u of UNTERSEITEN){
    if(u.id === "trenner") continue;
    document.getElementById(u.id).hidden = u.id !== unterseiteJetzt;
  }
  nav.hidden = schmal && unterseiteJetzt !== null;
  document.getElementById("einrichtungseite").hidden =
    schmal && unterseiteJetzt === null;
}

function unterseiteWaehlen(id){
  unterseiteJetzt = id;
  unterseitenZeichnen();
  if(id === "eSprachen") sprachenLaden();
  if(id === "eWlan") wlanLaden();
  if(id === "eUpdate") updateLaden();
}
function unterseiteZu(){
  unterseiteJetzt = SCHMAL() ? null : unterseiteJetzt;
  unterseitenZeichnen();
}
// Dreht jemand das Handy quer oder zieht das Fenster breit, aendert
// sich damit die Antwort auf die Frage, ob Liste und Seite nebeneinander
// passen.
window.matchMedia("(max-width:700px)").addEventListener("change", ()=>{
  if(!SCHMAL() && unterseiteJetzt === null) unterseiteJetzt = "eGemeinde";
  unterseitenZeichnen();
});

function uiZeichnen(){
  const t=TEXTE[UI];
  document.querySelectorAll("[data-t]").forEach(e=>{
    const k=e.dataset.t; if(t[k]) e.textContent=t[k];
  });
  // Ein Knopf statt zweier: er zeigt immer, was als naechstes passiert,
  // wenn man ihn drueckt. Zwei Knoepfe, von denen einer wirkungslos ist,
  // zwingen zum Nachdenken darueber, in welchem Zustand man gerade ist.
  bStart.textContent = zustandLive ? t.pause : t.start;
  // Starten traegt das Band, Anhalten das Dunkelblau. Dieselbe Regel
  // wie bis 0.4.0, nur dass der Knopf heute einer ist statt zweier.
  bStart.className = "btn primaer" + (zustandLive ? "" : " start");
  // Erklaert, was Anhalten bewirkt. Solange nichts laeuft, erklaert er
  // etwas, das gerade niemanden beschaeftigt.
  anhaltenHin.hidden = !zustandLive;
  if(!messlauf) bEinmessen.textContent=t.einmessen;
  // Der Schalter heisst immer gleich -- gedrueckt oder nicht sagt die
  // Farbe und aria-pressed, nicht der Text. Ein Knopf, dessen
  // Beschriftung springt, laesst im Gottesdienst offen, ob er den
  // Zustand nennt oder die Handlung.
  bSchnitt.textContent=t.aufnahme;
  // Die Reiterbeschriftung steht zweimal: sichtbar als Wort, und als
  // aria-label fuer den Fall, dass nur das Zeichen uebrigbleibt.
  for(const [k, n] of [[rGottesdienst,"r_gottesdienst"],
                       [rVorbereiten,"r_vorbereiten"],
                       [rAufnahmen,"r_aufnahmen"],
                       [rEinrichtung,"r_einrichtung"]])
    k.setAttribute("aria-label", t[n]);
  tonzahn.title = t.ton_feiner;
  tonzahn.setAttribute("aria-label", t.ton_feiner);
  reiterBreitePruefen();
  sprachknopf.textContent=UI==="de"?"EN":"DE";
  unterseitenZeichnen();
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
  // Rot heisst: der Ton geht gerade verloren. Gelb heisst: er koennte.
  warnung.classList.toggle("rot", !!schwer);
  warnung.classList.toggle("gelb", !schwer);
}

function postZeigen(){
  // Die Meldungen aus dem Saal legen sich vor den Reiter, statt einen
  // eigenen zu bekommen: sie kommen selten, und wer sie gelesen hat,
  // will zurueck dorthin, wo er war.
  const zeigen = unteransicht !== "post";
  // Beim Oeffnen gilt der Systemhinweis als gelesen. Danach bleibt an
  // der Sprache nur noch die kleine Zeile -- dieselbe Sprache fragt
  // nicht wieder nach.
  if(zeigen){
    fetch("/api/nachrichten/gelesen",{method:"POST"});
    reiterJetzt = "gottesdienst";
  }
  unteransicht = zeigen ? "post" : null;
  ansichtZeichnen();
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
  // Nur, was Whisper erkennen kann (Feld "quelle", config.NUR_ZIEL).
  quellwahl.innerHTML=d.moeglich.filter(x=>x.quelle!==false).map(x=>
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
    `<div class=chips>${geprueft.map(kachel).join("")}</div>`
    + (offen.length
       ? `<p class="hin untertitel">${t.glossar_offen_ueber}</p>`
         + `<div class="chips ungeprueft">${offen.map(kachel).join("")}</div>`
       : "")
    + (ohne.length
       ? `<p class="hin untertitel">${t.kein_glossar_ueber}</p>`
         + `<div class="chips ungeprueft ohneglossar">${ohne.map(kachel).join("")}</div>`
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
// Von vorn wirft Zaehler, Verlauf und Kontext weg. Bis 0.4.0 geschah
// das ohne Rueckfrage, und der Knopf stand unter dem Startknopf.
function vonVorn(){
  if(!confirm(TEXTE[UI].reset_frage)) return;
  s("reset");
}
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
  const t=TEXTE[UI];
  if(!d.stellen||!d.stellen.length){
    erkannt.textContent=kontext.value.trim() ? t.erkannt_keine : "";
    erkannt.classList.remove("gut");
    return;
  }
  erkannt.innerHTML=t.erkannt_vor+" <b>"+d.stellen.join(", ")+"</b><br>"
    +t.erkannt_namen.split("{n}").join(d.namen.length)
                    .split("{g}").join(d.gefunden)
    +" "+d.namen.join(", ");
  erkannt.classList.add("gut");
}
function schieben(){
  handBetrieb=true;
  marke.style.insetInlineStart=regler.value+"%";
  marke2.style.insetInlineStart=regler.value+"%";
  schwellwert.textContent=TEXTE[UI].schwelle_wort+" "+regler.value+" %";
  feinwert.textContent=schwellwert.textContent;
}
// Drei Modi, drei Knoepfe. Bis 0.4.0 waren es zwei, und "keine
// Schwelle" liess sich nur ausdruecken, indem man den Regler auf null
// zog -- was der Server als kleinste feste Schwelle speicherte und beim
// naechsten Einmessen verwarf.
let schwellenModus = "aus";
async function schwelleModus(modus){
  const koerper = (modus === "fest")
    ? {modus:"fest", wert:zuWert(+regler.value)} : {modus:modus};
  const a = await fetch("/api/schwelle",{method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify(koerper)});
  const d = await a.json().catch(()=>({}));
  if(d.modus) schwellenModus = d.modus;
  modusZeigen();
  handBetrieb=false;
}
function modusZeigen(){
  for(const [knopf, m] of [[bAus,"aus"], [bAuto,"automatisch"],
                           [bFest,"fest"]]){
    knopf.classList.toggle("an", schwellenModus === m);
    knopf.setAttribute("aria-pressed", String(schwellenModus === m));
  }
}
let schnittLaeuft=false;
/* ---------- Aufnahme ----------
   Der Schalter fragt nicht selbst, sondern oeffnet den Dialog. Die
   beiden Haken sind Pflicht, und zwar auch im Server -- hier werden
   sie nur erhoben. */
function aufnahmeUmschalten(){
  if(schnittLaeuft){ aufnahmeBeenden(); return; }
  ewPerson.checked = false;
  ewNur.checked = false;
  ewfehler.hidden = true;
  einwilligung.showModal();
}

async function aufnahmeBestaetigen(){
  const t = TEXTE[UI];
  if(!ewPerson.checked || !ewNur.checked){
    ewfehler.textContent = t.ew_beide;
    ewfehler.hidden = false;
    return false;                       // Dialog bleibt offen
  }
  einwilligung.close();
  const a = await fetch("/api/mitschnitt",{method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({einwilligung:{person_gefragt:true,
                                       nur_predigt:true}})});
  const d = await a.json().catch(()=>({}));
  if(!a.ok){
    schnittinfo.textContent = d.grund==="platz_knapp"
      ? t.aufnahme_platz : t.aufnahme_abgelehnt;
    return;
  }
  schnittinfo.textContent = "";
  aufnahmeAnzeigen(true, 0);
}

async function aufnahmeBeenden(){
  const a = await fetch("/api/mitschnitt",{method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({beenden:true})});
  const d = await a.json().catch(()=>({}));
  aufnahmeAnzeigen(false, 0);
  if(d.datei){
    schnittinfo.textContent =
      TEXTE[UI].aufnahme_fertig.split("{m}").join(d.minuten);
    aufnahmenLaden();
  }
}

function aufnahmeAnzeigen(an, sekunden){
  schnittLaeuft = an;
  bSchnitt.setAttribute("aria-pressed", String(an));
  aufnahmelaeuft.hidden = !an;
  if(an) aufnahmedauer.textContent =
    Math.floor(sekunden/60) + ":" + String(sekunden%60).padStart(2,"0");
}

async function aufnahmeTageSetzen(){
  const n = parseInt(aufnahmetage.value, 10);
  if(isNaN(n) || n < 0) return;
  await fetch("/api/aufnahme/tage",{method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({tage:n})});
  aufnahmenLaden();
}

async function aufnahmenLaden(){
  // Nur am Rechner selbst. Aus dem Saal kommt 403, und dann steht da,
  // warum -- nicht eine leere Liste, die nach "keine Aufnahmen"
  // aussieht.
  const a = await fetch("/api/aufnahmen");
  const t = TEXTE[UI];
  if(a.status === 403){
    aufnahmeliste.textContent = t.aufnahme_nur_pc;
    zahlAufnahmen.hidden = true;
    return;
  }
  const d = await a.json().catch(()=>({liste:[]}));
  if(d.tage !== undefined) aufnahmetage.value = d.tage;
  if(!d.liste.length){
    aufnahmeliste.textContent = t.aufnahme_keine;
    zahlAufnahmen.hidden = true;
    return;
  }
  // Der Loeschknopf nur, wo die Aufnahme nicht gerade laeuft. Ein
  // Knopf, der "geht nicht" sagt, waere schlechter als keiner -- und
  // die laufende Aufnahme hat ohnehin ihre eigene Zeile oben.
  aufnahmeliste.innerHTML = d.liste.map(a =>
    '<div class=zeile><span class=was>' + a.name + '<br><small>' + a.mb
    + " MB · " + t.aufnahme_faellig.split("{d}").join(a.faellig)
    + '</small></span>'
    + '<a class="btn klein" href="/mitschnitt/' + encodeURIComponent(a.name)
    + '" download>' + t.herunterladen + '</a>'
    + (a.laeuft ? ""
       : ' <button class="btn klein gefahr"'
         + ' onclick="aufnahmeLoeschen(this.dataset.n)"'
         + ' data-n="' + a.name.replace(/"/g, "&quot;") + '">'
         + t.loeschen + "</button>")
    + "</div>").join("");
  // Die Zahl am Reiter: wie viele Aufnahmen liegen hier.
  zahlAufnahmen.hidden = !d.liste.length;
  zahlAufnahmen.textContent = d.liste.length;
}

async function aufnahmeLoeschen(name){
  // Die Rueckfrage NENNT DEN NAMEN. "Wirklich loeschen?" neben einer
  // Liste von fuenf Predigten ist keine Rueckfrage, sondern ein
  // Glueckspiel -- und geloescht ist geloescht.
  const t = TEXTE[UI];
  if(!confirm(t.loeschen_frage.split("{d}").join(name))) return;
  const a = await fetch("/api/aufnahme/loeschen",{method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({name:name})});
  if(!a.ok){
    const d = await a.json().catch(()=>({}));
    alert(t["loeschen_"+(d.grund||"")] || t.loeschen_ging_nicht);
  }
  aufnahmenLaden();
}

// ------------------------------------------- Jetzt aus dem Netz
function onlineUpdateAnzeigen(d){
  // Nur am Gemeinde-PC. Dieselbe Schranke wie beim Testprotokoll.
  onlinereihe.hidden = !d.am_rechner;
  if(onlinereihe.hidden) return;
  const t = TEXTE[UI];
  const l = d.online_lauf;
  const laeuft = d.online_vorgemerkt || (l && l.lage === "laeuft");
  onlineknopf.disabled = !!(laeuft || d.live);
  onlineknopf.title = d.live ? t.on_uebersetzung : "";
  let satz = "";
  if(d.online_vorgemerkt && !(l && l.lage === "laeuft")) satz = t.on_vorgemerkt;
  else if(l && l.lage === "laeuft")
    satz = t["on_laeuft_" + (l.schritt||"")] || t.on_laeuft;
  // Ergebnis und Fehlschlag kommen als Satz aus dem Skript. Der ist
  // deutsch -- aber er nennt Fassungsnummern und Pfade, und die
  // uebersetzt niemand. Besser der Satz als gar keine Auskunft.
  else if(l && l.text) satz = l.text;
  onlinestand.hidden = !satz;
  if(satz) onlinestand.textContent = satz;
}

async function onlineUpdate(){
  const t = TEXTE[UI];
  if(!confirm(t.on_frage)) return;
  onlineknopf.disabled = true;
  const a = await fetch("/api/update/online",{method:"POST"});
  const d = await a.json().catch(()=>({}));
  onlinestand.hidden = false;
  if(a.ok){
    onlinestand.textContent = d.timer === false ? t.on_kein_timer
                                                : t.on_vorgemerkt;
  }else{
    onlinestand.textContent = t["on_"+(d.grund||"")] || t.on_ging_nicht;
    onlineknopf.disabled = false;
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
    ? TEXTE[UI].eingemessen : TEXTE[UI].einmessen;
  if(d.erfolg){ schwellenModus="fest"; modusZeigen(); }
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

function wartungKlappen(){
  const zu = wartungFeld.hidden = !wartungFeld.hidden;
  wartungPfeil.classList.toggle("zu", zu);
  try{ localStorage.setItem("wartungZu", zu ? "1" : ""); }catch(e){}
  wartungKopf.setAttribute("aria-expanded", String(!zu));
}

// Eingeklappt, solange niemand sie aufmacht -- und danach gemerkt.
// Wer sie einmal offen haben will, hat meistens einen Grund, der
// laenger dauert als ein Seitenaufruf.
function wartungAnzeigen(liste){
  const t = TEXTE[UI];
  liste = liste || [];
  wartungKopf.hidden = liste.length === 0;
  if(!liste.length){ wartungFeld.hidden = true; return; }
  wartungZahl.textContent = liste.length;
  // Beim ersten Zeichnen den gemerkten Zustand herstellen.
  // Vorgabe ist zu.
  if(wartungFeld.dataset.erst !== "nein"){
    wartungFeld.dataset.erst = "nein";
    let zu = true;
    try{ zu = localStorage.getItem("wartungZu") !== ""; }catch(e){}
    wartungFeld.hidden = zu;
    wartungPfeil.classList.toggle("zu", zu);
  }
  wartungliste.textContent = "";
  for(const b of liste){
    const li = document.createElement("li");
    if(b.schwer) li.className = "schwer";
    const was = document.createElement("span");
    was.textContent = (UI === "de" ? b.was : b.was_en);
    li.appendChild(was);
    const tun = (UI === "de" ? b.tun : b.tun_en);
    if(tun){
      const code = document.createElement("code");
      code.textContent = tun;
      li.appendChild(code);
    }
    wartungliste.appendChild(li);
  }
}

// Der Tonscan haengt am Auf- und Zuklappen der Feineinstellung: er
// macht fremde Geraete auf, und das darf nur laufen, solange jemand
// hinsieht.
feineinstellung.addEventListener("toggle", ()=>{
  scanSchalten(feineinstellung.open && reiterJetzt === "vorbereiten");
});

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
      +`<span class=mini><span class="${farbe}" `
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
// Nur diese drei Lagen schickt Tonquelle.lage(). Die Liste steht hier
// ausdruecklich, weil "ton_" + Lage sonst in dieselbe Tabelle greift,
// in der auch die Kanalwoerter stehen -- "still", "ruht", "offen". Eine
// unbekannte Lage haette damit ein rohes Zustandswort als rote Meldung
// an den Kopf geschrieben, und genau das stand in den Pruefbildern.
const TONLAGEN = ["kein_ton", "warte_auf_geraet", "neu_geoeffnet"];
function tonSatz(d){
  if(!d || !d.lage) return "";
  if(!TONLAGEN.includes(d.lage)){
    console.error("Unbekannte Tonlage:", d.lage);
    return "";
  }
  let s = TEXTE[UI]["ton_"+d.lage] || "";
  if(!s) return "";
  s = s.split("{name}").join(d.name || "?");
  // Die Einzelheit aus dem Treiber ist englisch, technisch und nichts
  // fuer ein Banner mitten im Gottesdienst. Sie steht in der
  // Stoerungsansicht unter "Fuer den Betreuer".
  tonLage.technik = d.einzelheit || "";
  return s;
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
  // Das Feld "stimmen" gab es bis 0.3.2. Gefuellt hat es zuletzt der
  // Kern von 0.2.11; seit 0.3.0 rief niemand mehr die Funktion auf,
  // die es fuellte, und der Hinweis erschien nie wieder. Seit 0.3.3
  // sagt ihn die Update-Logik selbst -- sie haengt ihn als MELDUNG an
  // den Text, und der steht ohnehin schon in "$d.text".
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

// ------------------------------------------------- Stoerungsansicht
// Was gerade nicht stimmt, in einfachen Worten -- erreichbar aus
// jedem Reiter, weil die Statuspille in jedem Reiter steht.
//
// Zwei Ebenen: oben der Satz, den jemand versteht, der den Ton fahren
// soll; darunter eingeklappt dasselbe fuer den Betreuer, mit den
// Befehlen. Bis 0.4.1 standen die Befehle mitten im Betrieb da, und
// dazwischen ging unter, was wirklich zu tun war.
let letzteBefunde = [];
let grafikCpu = false;
function stoerungZeigen(){
  unteransicht = unteransicht === "stoerung" ? null : "stoerung";
  ansichtZeichnen();
  if(unteransicht === "stoerung") stoerungZeichnen();
}

function stoerungZeichnen(){
  const t = TEXTE[UI];
  // Was den laufenden Gottesdienst betrifft, steht zuerst -- und
  // zwar unabhaengig davon, ob der Systemcheck es kennt.
  const sofort = [];
  if(tonLage.kein && tonhin.textContent)
    sofort.push({schwer:true, was:tonhin.textContent, tun:t.st_tun_ton,
                 technik:tonLage.technik});
  if(!rechenwarnung.hidden && rechenwarnung.textContent)
    sofort.push({schwer:true, was:rechenwarnung.textContent,
                 tun:t.st_tun_betreuer});
  if(!zweiterdhcp.hidden && zweiterdhcp.textContent)
    sofort.push({schwer:true, was:zweiterdhcp.textContent,
                 tun:t.st_tun_netz});
  // Ein Modell, das teils auf der CPU liegt, laeuft weiter -- nur
  // zehnmal langsamer, und niemand sieht warum.
  if(grafikCpu)
    sofort.push({schwer:false, was:t.grafik_cpu_lang,
                 tun:t.st_tun_betreuer,
                 technik:"ollama ps   |   nvidia-smi"});
  // Ein Befund "fuer Laien" (seit 0.4.6, etwa der Grafikspeicher)
  // traegt seinen eigenen Satz, was zu tun ist -- der steht dann
  // sichtbar da und nicht als Befehl unter "Fuer den Betreuer".
  const ausDemCheck = letzteBefunde.map(b => b.laie ? ({
    schwer: b.schwer,
    was: (UI === "de" ? b.was : b.was_en) || b.was,
    tun: (UI === "de" ? b.tun : b.tun_en) || b.tun,
    technik: "",
  }) : ({
    schwer: b.schwer,
    was: (UI === "de" ? b.was : b.was_en) || b.was,
    tun: b.schwer ? t.st_tun_betreuer : t.st_tun_spaeter,
    technik: (UI === "de" ? b.tun : b.tun_en) || b.tun,
  }));
  const alle = sofort.concat(ausDemCheck);
  stoerungleer.hidden = alle.length > 0;
  stoerungliste.innerHTML = alle.map(p =>
    `<div class="stoerpunkt ${p.schwer ? "schwer" : "leicht"}">`
    + `<span class=was>${entschaerfen(p.was)}</span>`
    + `<span class=tun>${entschaerfen(p.tun)}</span></div>`).join("");
  // Fuer den Betreuer: die Befehle, eingeklappt.
  const technik = alle.filter(p => p.technik);
  stoerungtechnik.hidden = technik.length === 0;
  stoerungtechnikliste.innerHTML = technik.map(p =>
    `<li><span>${entschaerfen(p.was)}</span>`
    + `<code>${entschaerfen(p.technik)}</code></li>`).join("");
}

async function fehlerZeigen(){
  // Wie der Briefkasten eine eigene Ansicht, kein aufspringendes
  // Fenster: am Pult darf im Gottesdienst nichts aufpoppen.
  const zeigen = unteransicht !== "fehler";
  unteransicht = zeigen ? "fehler" : null;
  ansichtZeichnen();
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
  // Ein Knopf, der nichts zu entfernen hat, stellt eine Frage, die
  // sich nicht stellt.
  bPwWeg.hidden = !gesetzt;
}

async function themaSetzen(){
  const a = await fetch("/api/thema-im-prompt",{method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({an: themaschalter.checked})});
  const d = await a.json().catch(()=>({}));
  if(d.an !== undefined) themaschalter.checked = !!d.an;
}

async function versuchSetzen(){
  const a = await fetch("/api/versuchssprachen",{method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({an: versuchsschalter.checked})});
  const d = await a.json().catch(()=>({}));
  if(d.an !== undefined) versuchsschalter.checked = !!d.an;
  // Die Auswahl unter Sprachen gleich neu aufbauen.
  sprachenLaden();
}

async function protokollSetzen(){
  // Seit dem Nachtrag zu 0.5.0 dieselbe Rueckfrage wie beim
  // Testprotokoll: die sprechende Person wurde gefragt. Der Server
  // prueft es auch.
  const t = TEXTE[UI];
  const an = protokollschalter.checked;
  if(an && !confirm(t.ms_frage)){
    protokollschalter.checked = false;
    return;
  }
  const a = await fetch("/api/protokoll",{method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify(an
      ? {an:true, einwilligung:{person_gefragt:true}}
      : {an:false})});
  protokollAnzeigen(a.ok ? an : false);
}
// --------------------------------------------------- Testprotokoll
// Eigener Dialog waere zu viel: es genuegt EIN Haken, und der steht
// in der Bestaetigung selbst. Anders als bei der Aufnahme -- dort
// sind es zwei, und der zweite ("nur die Predigt") ergibt bei einem
// Test keinen Sinn.
// ------------------------------------------------ Gemeinde
async function gemeindeSetzen(){
  const a = await fetch("/api/gemeinde",{method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({gemeinde:gemeindefeld.value,
                         kontakt:kontaktfeld.value,
                         melden:meldeschalter.checked})});
  const d = await a.json().catch(()=>({}));
  if(a.ok){
    gemeindefeld.value = d.gemeinde || "";
    kontaktfeld.value = d.kontakt || "";
    meldeschalter.checked = !!d.melden;
  }
}

async function pruefprotokollSetzen(){
  const t = TEXTE[UI];
  const an = pruefprotokollschalter.checked;
  if(an && !confirm(t.pp_frage)){
    pruefprotokollschalter.checked = false;
    return;
  }
  const a = await fetch("/api/pruefprotokoll",{method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify(an
      ? {an:true, einwilligung:{person_gefragt:true}}
      : {an:false})});
  const d = await a.json().catch(()=>({}));
  if(!a.ok){
    pruefprotokollschalter.checked = false;
    pruefprotokollhin.textContent = d.grund==="nur_am_rechner"
      ? t.pp_nur_rechner : t.pp_abgelehnt;
    pruefprotokollhin.hidden = false;
    return;
  }
  pruefprotokollAnzeigen(d.lage || null);
}

function pruefprotokollAnzeigen(lage){
  const t = TEXTE[UI];
  pruefprotokollschalter.checked = !!lage;
  pruefprotokolllaeuft.hidden = !lage;
  // Der Erklaertext nur, wenn es auch den Schalter gibt. Ist das Pult
  // nicht am Gemeinderechner offen, ist pruefprotokollreihe versteckt
  // -- und bis 0.3.7 stand der Text trotzdem da. Dann las jemand drei
  // Zeilen ueber einen Schalter, der nirgends zu sehen war, und suchte
  // den Fehler bei sich.
  pruefprotokollhin.hidden = !!lage || pruefprotokollreihe.hidden;
  if(lage){
    pruefprotokollzeilen.textContent =
      t.pp_zeilen.split("{n}").join(lage.zeilen);
  }
}

// --------------------------------------------------- Sprachwache
// Nur eine Vermutung, also nur ein Hinweis -- und ein Knopf, der
// daraus eine Entscheidung macht. Umgeschaltet wird NIE von selbst.
function sprachverdachtAnzeigen(satz){
  sprachverdacht.hidden = !satz;
  if(satz) sprachverdachttext.textContent = satz;
}

function spracheUmstellen(){
  // Die Sprachwahl steht ohnehin schon in der Einrichtung. Dorthin
  // fuehren, statt eine zweite Stelle zu bauen, an der dasselbe
  // eingestellt wird.
  reiterWaehlen("einrichtung");
  unterseiteWaehlen("eSprachen");
  quellwahl.scrollIntoView({behavior:"smooth", block:"center"});
  quellwahl.focus();
}

// Was den Predigttext speichert, ausser der Aufnahme. Dieselbe Lage,
// die jedes Handy bekommt (Feld "mitschrift").
function mitschriftAnzeigen(d){
  const t = TEXTE[UI];
  mitschriftlaeuft.hidden = !d.mitschrift;
  if(!d.mitschrift) return;
  const was = [];
  if(d.pruefprotokoll) was.push(t.ms_pp);
  if(d.protokoll_mitschrift) was.push(t.ms_journal);
  mitschriftwas.textContent = "(" + was.join(", ") + ") · " + t.ms_handys;
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
  const t=TEXTE[UI];
  skriptinfo.textContent=t.skript_liest;
  const daten=new FormData(); daten.append("datei",f);
  try{
    const a=await fetch("/api/skript",{method:"POST",body:daten});
    const d=await a.json();
    if(d.fehler){skriptinfo.textContent=t.skript_leer;return}
    skriptinfo.innerHTML=t.skript_gelesen.split("{w}").join(d.woerter)+" "
      +(d.stellen.length
        ? t.skript_stellen+" <b>"+d.stellen.join(", ")+"</b>. " : "")
      +t.skript_namen.split("{b}").join(d.bekannt).split("{n}").join(d.neu)
      +"<br>"+d.namen.join(", ");
    lies();
  }catch(e){skriptinfo.textContent=t.skript_ging_nicht}
}

async function pegel(){
  try{
    const d=await(await fetch("/api/pegel")).json();
    const pz=zuProzent(d.jetzt), sz=zuProzent(d.schwelle);
    fuell.style.width=pz+"%";
    const t=TEXTE[UI];
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
    if(!handBetrieb){
      marke.style.insetInlineStart=sz+"%";
      marke2.style.insetInlineStart=sz+"%";
      regler.value=Math.round(sz);
    }
    pegelwert.textContent=(d.spricht?t.spricht:t.still)+" · "+Math.round(pz)+" %";
    // "knapp darunter" ist der Fall, den man am Regler sofort beheben
    // kann: es wird gesprochen, nur zu leise fuer die Schwelle.
    schwellwert.textContent=t.schwelle_wort+" "+Math.round(sz)+" % · "
      +(t["m_"+({aus:"aus",automatisch:"auto",fest:"fest"}[d.modus]||"aus")])
      +(d.verworfen?" · "+d.verworfen+" "+t.verworfen:"")
      +(d.knapp>30?" · "+t.knapp_darunter:"");
    feinwert.textContent=pegelwert.textContent+" · "+schwellwert.textContent;
    if(d.modus && d.modus!==schwellenModus){ schwellenModus=d.modus; }
    modusZeigen();
    // Was die Ton-Kachel oben sagt, haengt an denselben Zahlen.
    tonKachel(d);
    // Nur zeigen, wenn es auch etwas zu sagen gibt: ein leerer gelber
    // Balken sieht nach Warnung aus und stumpft ab.
    warnungZeigen(d.lage_text && (d.lage==="alarm"||d.lage==="warnung")
      ? (d.lage==="alarm" ? t.achtung+" " : "") + d.lage_text : "",
      d.lage==="alarm");
    if(d.einmessen&&d.einmessen.laeuft){
      messlauf=true;
      bEinmessen.textContent=t.messe.split("{n}").join(d.einmessen.rest);
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
// ---------------------------------------------------------- Kacheln
// Jede Kachel sagt in EINEM Wort, wie es steht, und faerbt ihren Rand
// danach. Die Zahlen dahinter stehen eine Ebene tiefer, hinter dem
// Fragezeichen: im Gottesdienst zaehlt gut/knapp/kein Ton, nicht 42 %.
function kachelSetzen(kachel, stufe, wort){
  kachel.classList.remove("ok", "warn", "schlecht");
  if(stufe) kachel.classList.add(stufe);
  kachel.querySelector(".zustand").textContent = wort || "";
}

// Steigt die Verzoegerung ueber mehrere Abschnitte, staut sich etwas
// auf. Die Regel ist nicht erfunden, sondern die aus auswertung.py:
// Median des letzten Drittels gegen den des ersten, und "waechst" ab
// einer Sekunde Unterschied. Angewandt auf die acht Abschnitte, die der
// Server ohnehin schickt -- bei acht Werten ist ein Drittel zwei.
// Dazu die Bedingung, dass es ueberhaupt langsam ist: 2,0 s ist der
// gemessene Betriebswert aus LIESMICH.md. Ein Anstieg von 0,3 auf 1,4
// Sekunden ist kein Rueckstau, sondern ein laengerer Satz.
const RUECKSTAU_ANSTIEG = 1.0;
const RUECKSTAU_AB = 2.0;
function rueckstau(letzte){
  const w = (letzte||[]).map(x=>x.gesamt).filter(x=>typeof x === "number");
  if(w.length < 6) return false;
  const n = Math.max(1, Math.floor(w.length / 3));
  const mitte = a => {
    const b = a.slice().sort((x,y)=>x-y);
    return b.length % 2 ? b[(b.length-1)/2]
                        : (b[b.length/2-1] + b[b.length/2]) / 2;
  };
  const anfang = mitte(w.slice(0, n)), ende = mitte(w.slice(-n));
  return ende > anfang + RUECKSTAU_ANSTIEG && ende > RUECKSTAU_AB;
}
let stauJetzt = false;

// Die Ton-Kachel haengt an zwei Quellen: am Pegelabruf (zehnmal je
// Sekunde) und am Zustand (alle zwei Sekunden). Beide rufen hier an,
// und was sie nicht wissen, lassen sie stehen.
let tonLage = {kein: false, text: "", technik: ""};
function tonKachel(p){
  const t = TEXTE[UI];
  if(tonLage.kein){
    kachelSetzen(kTon, "schlecht", t.k_kein_ton);
  }else if(stauJetzt){
    kachelSetzen(kTon, "warn", t.k_verzoegerung);
  }else if(p && p.lage === "alarm"){
    kachelSetzen(kTon, "schlecht", t.k_kein_ton);
  }else if(p && (p.lage === "warnung" || p.knapp > 30)){
    kachelSetzen(kTon, "warn", t.k_knapp);
  }else if(p && (p.lage === "still" || !p.spricht) && p.jetzt <= p.grund * 2.5){
    // Stille ist kein gutes Zeichen, sondern gar keines. Gruen "gut"
    // behauptet, der Ton sei geprueft -- geprueft ist er erst, wenn
    // etwas durchkommt. Vor dem Gottesdienst steht hier deshalb grau.
    kachelSetzen(kTon, null, t.k_still);
  }else{
    kachelSetzen(kTon, "ok", t.k_gut);
  }
  if(!p) return;
  // Welcher Modus gilt -- und seit wann, wenn er eingemessen ist.
  const wann = (p.gemessen || "").slice(11, 16);
  schwellestand.textContent =
    p.modus === "fest"
      ? (wann ? t.s_fest_seit.split("{z}").join(wann) : t.s_fest)
      : (p.modus === "automatisch" ? t.s_auto : t.s_aus);
}

function verlaufKlappen(){
  const zu = mit.hidden = !mit.hidden;
  zuletztzeile.setAttribute("aria-expanded", String(!zu));
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
    pille.className = "pille kaputt";
    pille.textContent = TEXTE[UI].p_stoerung;
    warnungZeigen(TEXTE[UI].server_weg + " (" + e.message + ")", true);
    return;
  }
  try{
    const t=TEXTE[UI];
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
    // Die Statuspille steht in jedem Reiter im Kopf. Drei Zustaende,
    // und der dritte -- Stoerung -- schlaegt die beiden anderen: wer
    // keinen Ton hat, interessiert sich nicht dafuer, dass die
    // Uebersetzung formal laeuft.
    tonLage.kein = !!tSatz;
    letzteBefunde = d.befunde || [];
    // Vier Stufen. HINWEIS ist neu: der Betrieb laeuft, aber es steht
    // etwas offen, das niemand heute anfassen muss. Bis 0.4.1 stand
    // genau das jede Woche im Briefkasten und stumpfte ihn ab.
    const stoerung = !!(tSatz || d.stt_fehler || fremd.length
                        || letzteBefunde.some(b => b.schwer));
    const hinweis = !stoerung && letzteBefunde.length > 0;
    pille.className = "pille " + (stoerung ? "kaputt"
                                 : hinweis ? "hinweis"
                                 : (d.live ? "an" : "aus"));
    pille.textContent = stoerung ? t.p_stoerung
                        : hinweis ? t.p_hinweis
                        : (d.live ? t.p_an : t.p_aus);
    // Jede Stufe ausser LAEUFT und ANGEHALTEN sagt beim Antippen,
    // warum sie so aussieht.
    pille.title = (stoerung || hinweis) ? t.st_warum : "";
    if(unteransicht === "stoerung") stoerungZeichnen();
    // Laufzeit statt Segmentzahl: wie lange laeuft das hier schon.
    const sek = Math.max(0, Math.round(d.laeuft_seit || 0));
    laufzeit.textContent = d.live
      ? Math.floor(sek/3600 ? sek/3600 : 0)
        ? `${Math.floor(sek/3600)}:${String(Math.floor(sek%3600/60)).padStart(2,"0")}:${String(sek%60).padStart(2,"0")}`
        : `${Math.floor(sek/60)}:${String(sek%60).padStart(2,"0")}`
      : "";
    if(zustandLive!==d.live){ zustandLive=d.live; uiZeichnen(); }

    // --- Kachel Zuhoerer ---
    const hoerer = Object.entries(d.hoerer||{});
    hoererzahl.textContent = d.gesamt;
    // Je Sprache Kuerzel, Zahl -- und was die Zuhoerer gesagt haben.
    // Zwei Zahlen, sonst nichts: keine Adresse, keine Kennung, kein
    // Zeitpunkt. Siehe rueckmeldung.py.
    const urteil = d.rueckmeldung || {};
    hoerersprachen.innerHTML = hoerer
      .filter(([a,b])=>b>0)
      .map(([a,b])=>{
        const u = urteil[a];
        const stimmen = u && (u.gut || u.schwer)
          ? ` <s class=urteil title="${t.u_titel}">`
            + `${u.gut||0} 👍 ${u.schwer||0} 👎</s>`
          : "";
        return `<span>${a.toUpperCase()} <b>${b}</b>${stimmen}</span>`;
      }).join("");
    kachelSetzen(kHoerer, d.gesamt > 0 ? "ok" : null, "");
    zahlen.innerHTML=hoerer.map(([a,b])=>
      `<tr><td>${NAMEN[a]||a}</td><td>${b}</td></tr>`).join("");

    // --- Kachel Thema ---
    const stellen = d.stellen || [], namen = d.namen || [];
    if(d.kontext_fehlt){
      kachelSetzen(kThema, "warn", t.k_fehlt);
      themazeile.textContent = "";
      themalink.hidden = false;
    }else{
      kachelSetzen(kThema, "ok", t.k_gesetzt);
      themazeile.textContent = stellen.length
        ? stellen.join(", ") + " · "
          + t.k_namen.split("{n}").join(namen.length)
        : t.k_namen.split("{n}").join(namen.length);
      themalink.hidden = true;
    }
    erkanntkachel.textContent = namen.join(", ");
    // Die Wahrheit steht im Server, nicht im Browser: nach einem
    // Neuladen des Pults, nach einem Dienstneustart oder wenn die
    // Aufnahme von selbst endete (Uebersetzung angehalten, Platte
    // voll), muss der Schalter das zeigen.
    aufnahmeAnzeigen(!!d.mitschnitt, d.mitschnitt ? d.mitschnitt.sekunden : 0);
    if(d.protokoll_mitschrift!==undefined)
      protokollAnzeigen(d.protokoll_mitschrift);
    mitschriftAnzeigen(d);
    wartungAnzeigen(d.wartung);
    // Nur zeichnen, wenn niemand gerade tippt -- sonst springt das
    // Feld bei jedem Takt auf den gespeicherten Wert zurueck.
    if(document.activeElement !== gemeindefeld)
      gemeindefeld.value = d.gemeinde || "";
    if(document.activeElement !== kontaktfeld)
      kontaktfeld.value = d.kontakt || "";
    meldeschalter.checked = !!d.nutzung_melden;
    if(d.thema_im_prompt!==undefined)
      themaschalter.checked = !!d.thema_im_prompt;
    if(d.versuchssprachen!==undefined)
      versuchsschalter.checked = !!d.versuchssprachen;
    kontowarnung.hidden = !d.spendenkonto;
    onlineUpdateAnzeigen(d);
    if(d.spendenkonto) kontowarnungtext.textContent = TEXTE[UI].konto_kaputt;
    pruefprotokollreihe.hidden = !d.am_rechner;
    pruefprotokollAnzeigen(d.pruefprotokoll || null);
    sprachverdachtAnzeigen(d.sprachverdacht || "");
    if(d.pult_passwort!==undefined) pultPasswortAnzeigen(d.pult_passwort);
    const post_=(d.nachrichten||[]);
    briefkastenband.hidden = post_.length===0;
    postzahl.textContent = post_.length;
    // Steht ein Systemhinweis darin, heisst der Knopf anders: "neue
    // Meldungen aus dem Saal" waere schlicht falsch.
    const sys_ = post_.some(x=>x.art==="system");
    const knopftext = briefkastenband.querySelector("[data-t=post_neu]");
    if(knopftext) knopftext.textContent =
      sys_ ? TEXTE[UI].post_system : TEXTE[UI].post_neu;
    if(post_.length===0 && unteransicht === "post"){ postZeigen(); }
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
    // Die Zeile zeigt den letzten Abschnitt mit seiner Verzoegerung.
    // Ein Tipp darauf klappt die acht auf, die der Server mitschickt.
    const letzte = d.letzte || [];
    const neuste = letzte.length ? letzte[letzte.length-1] : null;
    zuletzttext.textContent = neuste ? neuste.deutsch : "–";
    zuletztsek.textContent = neuste ? neuste.gesamt + " s" : "";
    mit.innerHTML = letzte.slice().reverse().map(x=>
      `<div><span class=sek>${x.gesamt} s</span><span>${
        String(x.deutsch).replace(/[<>&]/g,
          c=>({"<":"&lt;",">":"&gt;","&":"&amp;"}[c]))}</span></div>`).join("");
    stauJetzt = rueckstau(letzte);
    tonKachel(null);

    // --- Punkte und Zahlen an den Reitern ---
    // Gelb am Reiter Vorbereiten, solange das Thema fehlt. Rote
    // Meldungen stehen als Banner in jedem Reiter, dafuer braucht es
    // keinen Punkt.
    // Grafikkarte. Ohne Karte oder ohne nvidia-smi steht hier
    // nichts -- eine leere Ueberschrift waere eine Frage, die sich
    // nicht stellt.
    const gk = d.grafik;
    grafikCpu = !!(gk && gk.cpu_anteil);
    grafikkopf.hidden = !gk;
    grafikheute.hidden = !gk;
    if(gk){
      const voll = Math.round(100 * gk.speicher_hoechst_mb
                              / Math.max(1, gk.speicher_gesamt_mb));
      grafikheute.textContent = t.grafik_zeile
        .split("{belegt}").join(gk.speicher_hoechst_mb)
        .split("{gesamt}").join(gk.speicher_gesamt_mb)
        .split("{voll}").join(voll)
        .split("{spitze}").join(gk.last_hoechst)
        .split("{mittel}").join(gk.last_mittel)
        .split("{sprachen}").join(gk.sprachen)
        + (gk.cpu_anteil ? " \u2014 " + t.grafik_cpu : "");
      // Auffaellig auch schon ab 90 Prozent, nicht erst, wenn ein
      // Teil auf der CPU liegt -- dieselbe Schwelle wie der Hinweis.
      grafikheute.classList.toggle("warnung", !!gk.cpu_anteil || voll >= 90);
    }
    punktVorbereiten.hidden = !d.kontext_fehlt;
    punktEinrichtung.hidden = !((d.wartung||[]).length || d.update);
    if(d.stellen&&d.stellen.length&&!erkannt.innerHTML)
      zeigeErkannt({stellen:d.stellen,namen:d.namen||[],
                    gefunden:(d.namen||[]).length});
  }catch(e){
    warnungZeigen(TEXTE[UI].anzeigefehler + " " + e.message, true);
    console.error(e);
  }
}
// Der Reiter aus der Adresse. Vorgabe ist Gottesdienst: wer das Pult
// aufmacht, will zuerst starten.
reiterJetzt = REITER.includes(location.hash.slice(1))
  ? location.hash.slice(1) : "gottesdienst";
unterseiteJetzt = SCHMAL() ? null : "eGemeinde";
ansichtZeichnen();
unterseitenZeichnen();
window.addEventListener("hashchange", ()=>{
  const n = location.hash.slice(1);
  if(REITER.includes(n) && n !== reiterJetzt) reiterWaehlen(n);
});
sprachenLaden().then(uiZeichnen);
aufnahmenLaden();
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
    # Die Mitschrift uebersteht seit dem Nachtrag zu 0.5.0 keinen
    # Neustart mehr: sie haengt an der Einwilligung der Person, die
    # gerade spricht -- wie das Testprotokoll, das ebenfalls mit dem
    # Dienst endet. Wer sie nach dem Neustart braucht, schaltet sie am
    # Pult wieder ein und fragt dafuer erneut.
    global PROTOKOLL_MITSCHRIFT
    PROTOKOLL_MITSCHRIFT = False
    if stand.get("protokoll_mitschrift"):
        stand["protokoll_mitschrift"] = False
        zustandsdatei.speichern(stand)
        print("Mitschrift im Protokoll war eingeschaltet. Nach dem "
              "Neustart ist sie aus -- sie gilt nur mit der Einwilligung "
              "der Person, die gerade spricht.")
    lauf.wlan = dict(stand["wlan"])
    lauf.werk.thema_im_prompt = bool(stand.get("thema_im_prompt"))
    # Der Modus uebersteht den Neustart, nicht nur der Wert. Bis 0.4.0
    # stand hier allein die Zahl, und ein Pult ohne Schwelle sah nach
    # einem Dienstneustart aus wie eines mit Automatik.
    _sch = stand.get("schwelle") or {}
    seg.grundmodus = _sch.get("grundmodus") or "aus"
    _modus = _sch.get("modus") or ("fest" if _sch.get("wert") is not None
                                   else "automatisch")
    if _modus == "fest" and _sch.get("wert") is not None:
        # Die eingemessene Schwelle gilt weiter. Im Dateibetrieb wird sie
        # gleich wieder ueberschrieben, das ist Absicht: eine Aufnahme hat
        # keinen wandernden Raumklang.
        seg.feste_schwelle = _sch["wert"]
        seg.modus = "fest"
    else:
        seg.modus_setzen(_modus if _modus in ("aus", "automatisch") else "aus")
    print(f"Schwelle: {seg.modus}" +
          (f" ({seg.feste_schwelle:.5f})" if seg.modus == "fest" else ""))
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
        seg.modus = "fest"
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
