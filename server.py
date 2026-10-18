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
            fehlt = ohne_stimme(SPRACHEN, QUELLE, self.stimmen)
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
        # Die Quelle von JETZT (sprachen_setzen setzt sie vorher), nicht
        # die globale vom Start: mit None ueberspraenge stimmen_finden die
        # Startquelle -- nach dem Wechsel de -> ru liefe de dann ohne
        # Stimme, obwohl thorsten daliegt (bis 0.5.1).
        gefunden = stimmen_finden([sprache], quelle=self.quelle)
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
        Bestandteil des Modells.

        Wechselt die Quelle, bleibt die bisherige als Ziel angewaehlt
        (0.5.1): wer eben noch zuhoerte, hoert jetzt die Uebersetzung,
        statt getrennt zu werden. Das gilt fuer jeden Aufruf, auch am
        Pult vorbei und von einer Pult-Seite, die noch von 0.5.0 offen
        ist. Abwaehlen laesst sie sich danach wie jede andere."""
        vorher = set(self.sprachen)
        alt = self.quelle
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
        if self.quelle != alt and alt not in self.ziele:
            self.ziele.append(alt)
            print(f"Sprachwahl: {alt} bleibt als Uebersetzung angewaehlt.")
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
                    # Was uebersetzt wird, nicht was angehakt ist: die
                    # Quelle kann in lauf.ziele stehen (0.5.1).
                    quelle=self.quelle, ziele=list(self.sprachen[1:]),
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


def ohne_stimme(sprachen, quelle, stimmen):
    """Welche Zielsprachen laufen ohne Stimme, nur als Text?

    Ohne die Quelle: sie ist Originalton und braucht keine Stimme
    (stimmen_finden laesst sie aus). Bis 0.5.1 stand sie in der
    Startzeile "Ohne Stimme, nur Text" immer mit da."""
    return [s for s in dict.fromkeys(sprachen)
            if s != quelle and s not in stimmen]


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


class PortBelegt(OSError):
    """Der Hauptport ist schon vergeben -- meist laeuft der Dienst.

    Eine eigene Art, damit main() sie erkennt. Bis 0.5.0 suchte main()
    in der Meldung nach "address" oder "10048" (Windows), fand in
    "Port 8000 ist belegt" keines von beiden und warf einen Traceback
    statt des Hinweises auf den laufenden Dienst."""


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
        raise PortBelegt(f"Port {port} ist belegt")
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

    # Pult, Anmeldung und QR-Seite liegen seit 0.5.2 in web/, vorher
    # standen sie als Zeichenketten in dieser Datei. Gelesen bei jedem
    # Aufruf, wie client.html. Fehlt eine, sagt die Antwort das -- kein
    # stiller Rueckfall auf eine alte Fassung, auch nicht auf eine
    # pult.html im Hauptordner, wie sie bis 0.5.1 Vorrang hatte.
    web = basis / "web"

    def web_lesen(name):
        """Der Text aus web/<name>, oder None, wenn die Datei fehlt."""
        datei = web / name
        if not datei.exists():
            return None
        return datei.read_text(encoding="utf-8")

    def fehlende_datei_seite(name):
        return HTMLResponse(f"<h1>{name} fehlt</h1><p>{web / name}</p>",
                            status_code=500)

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
        anmeldung = web_lesen("anmeldung.html")
        if anmeldung is None:
            return fehlende_datei_seite("anmeldung.html")
        return HTMLResponse(
            anmeldung.format(ziel=html_escape(request.url.path), fehler=""),
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
            anmeldung = web_lesen("anmeldung.html")
            if anmeldung is None:
                return fehlende_datei_seite("anmeldung.html")
            return HTMLResponse(
                anmeldung.format(ziel=html_escape(ziel),
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
        print(f"Sprachen: {lauf.quelle} -> {', '.join(lauf.sprachen[1:])}")

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

        seite = web_lesen("qr.html")
        if seite is None:
            return fehlende_datei_seite("qr.html")
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

    # Dienst, letztes Wartungsfenster, Wecker, Schreibtischsymbol (0.5.1).
    # Nur fuer die Einrichtung und erst, wenn jemand die Seite oeffnet:
    # dahinter stehen systemctl- und journalctl-Aufrufe mit kurzer
    # Frist, und die gehoeren nicht in den Takt von /api/zustand. Kein
    # async: die Aufrufe blockieren, und so laufen sie im Threadpool
    # statt in der Ereignisschleife, an der die Zuhoerer haengen.
    betrieb_zwischen = {"zeit": 0.0, "wert": None}

    @app.get("/api/betriebslage")
    def betriebslage_lesen():
        jetzt = time.time()
        if (betrieb_zwischen["wert"] is None
                or jetzt - betrieb_zwischen["zeit"] > 10.0):
            import betriebslage
            betrieb_zwischen.update(zeit=jetzt, wert=betriebslage.lage(basis))
        return betrieb_zwischen["wert"]

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
        seite = web_lesen("pult.html")
        if seite is None:
            return fehlende_datei_seite("pult.html")
        return ausliefern(request, seite, "text/html; charset=utf-8")

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
    # Und gezaehlt wird, was als Uebersetzung LAEUFT: seit 0.5.1 bleibt
    # die Quelle in lauf.ziele stehen, wenn sie dort angehakt war.
    grafikwacht.anwerfen(lambda: lauf.laeuft,
                         lambda: len(lauf.sprachen) - 1)

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
# nicht ausgewiesen hat, steht in web/anmeldung.html. Bewusst karg: sie
# ist kein Teil der Bedienung, sondern eine Tuer. Und sie sagt, wo das
# Passwort herkommt -- sonst steht sonntags jemand davor und weiss
# nicht, wen er fragen soll. Eingesetzt wird mit format(): {ziel} und
# {fehler}, darum stehen geschweifte Klammern im CSS dort doppelt.
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

    belegt = False
    try:
        starten_auf(app_bauen(lauf, basis, a.port, tonquelle, kanalscan),
                    a.port)
    except PortBelegt:
        belegt = True
    except OSError as e:
        if "10048" in str(e) or "address" in str(e).lower():
            belegt = True
        else:
            raise
    finally:
        stoppen.set()
        if tonquelle is not None:
            tonquelle.anhalten()
    if belegt:
        # Mit Rueckgabe 1 statt 0: start.sh und systemd sollen sehen,
        # dass dieser Start nichts geworden ist.
        print(f"\nPort {a.port} ist belegt. Laeuft der Dienst schon?")
        print("  systemctl status devarenu")
        print(f"Anderen Port nehmen: server.py --port {a.port + 1}")
        sys.exit(1)


if __name__ == "__main__":
    main()
