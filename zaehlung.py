#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bibelstellen in die Zaehlung der Zielsprache bringen.

Die Schlachter 2000 zaehlt wie der hebraeische Text. Die Bibeln der
Zuhoerer zaehlen oft anders -- und dann steht im Untertitel eine
Stelle, die es in der Bibel auf dem Schoss des Zuhoerers nicht gibt:

    Schlachter Joel 3,1       heisst englisch Joel 2:28
    Schlachter Maleachi 3,23  heisst englisch Malachi 4:5
    Schlachter Psalm 51,12    heisst englisch Psalm 51:10
    Schlachter Psalm 23       heisst russisch Псалом 22

WAS DIESES MODUL TUT UND WAS NICHT

Es rechnet KAPITEL- UND VERSANGABEN um, nie Text. Es rechnet nur
dort, wo die Regel aus nachgezaehlten Verszahlen eindeutig folgt --
gebaut und begruendet in werkzeuge/zaehlung_bauen.py. Ist eine Angabe
nicht eindeutig umzurechnen, bleibt sie unveraendert. Lieber die
Angabe der Schlachter als eine falsche.

Nur fuer die Ausgangssprache DEUTSCH. Spricht jemand englisch, kommt
die Stelle schon in der englischen Zaehlung aus seinem Mund.

ZIELE

    en, es, pt   englische Zaehlung (KJV, Reina-Valera, Almeida)
    tw           englische Zaehlung (Biblica, Asante Twi) -- seit 0.5.0
    ru           Synodalzaehlung (Septuaginta bei den Psalmen)
    uk           Ohienko: Psalmen hebraeisch wie die Schlachter, Joel
                 und Maleachi wie die englischen Bibeln -- seit 0.5.0
    fa           NICHT. Welche Zaehlung die persischen Bibeln benutzen,
                 ist nicht belegt. Eine Umrechnung auf Verdacht waere
                 schlimmer als keine.
    alles andere unveraendert.
"""

import json
import re
from pathlib import Path

BASIS = Path(__file__).resolve().parent

# Welche Zielsprache welche Zaehlung benutzt. Wer hier nicht steht,
# bekommt keine Umrechnung.
ZAEHLUNG_JE_SPRACHE = {
    "en": "en",
    # Reina-Valera und Almeida folgen beide der englischen Zaehlung --
    # Joel hat dort drei Kapitel, Maleachi vier.
    "es": "en",
    "pt": "en",
    "ru": "ru",
    # Ohienko in der Ausgabe der Ukrainischen Bibelgesellschaft. Belegt
    # in werkzeuge/zaehlung_bauen.py -- dort auch, warum NICHT die
    # Ohienko-Datei von getbible.
    "uk": "uk",
    # Die Asante-Twi-Bibel von Biblica zaehlt in Psalmen, Joel und
    # Maleachi genau wie die KJV; zaehlung_bauen.py prueft das bei jedem
    # Lauf nach.
    "tw": "en",
}

# Der Name, mit dem eine EINZELNE Stelle genannt wird. Das Glossar
# fuehrt den Buchtitel ("Psalms", "Псалтирь"); zitiert wird aber der
# einzelne Psalm, und der heisst im Singular.
#
# Twi hat KEIN Glossar, also auch keine Buchnamen. Hier stehen genau
# die drei Buecher, deren Angabe sich in der englischen Zaehlung
# aendert -- nur fuer sie wird je ein Name gebraucht. Die Namen sind
# die der Biblica-Ausgabe (\toc2 bzw. \cl in den USFM-Dateien).
ZITATNAME = {
    19: {"en": "Psalm", "es": "Salmo", "pt": "Salmo", "ru": "Псалом",
         "uk": "Псалом", "tw": "Dwom"},
    29: {"tw": "Yoɛl"},
    39: {"tw": "Malaki"},
}


class Tabelle:
    """Die Umrechnungsregeln. Fehlt die Datei, wird nichts umgerechnet."""

    def __init__(self, daten=None):
        self.daten = daten or {}
        self.zaehlungen = self.daten.get("zaehlungen", {})

    @classmethod
    def laden(cls, pfad=None):
        pfad = Path(pfad) if pfad else BASIS / "zaehlung.json"
        try:
            return cls(json.loads(pfad.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            # Keine Tabelle heisst: nichts umrechnen. Das ist der
            # richtige Ausfall -- die Stelle der Schlachter stimmt ja.
            return cls({})

    @property
    def vorhanden(self):
        return bool(self.zaehlungen)

    def umrechnen(self, buch, kapitel, vers, zaehlung):
        """(Kapitel, Vers) in der Zielzaehlung, oder None.

        None heisst ausdruecklich "nicht umzurechnen" -- entweder weil
        es nichts zu rechnen gibt oder weil es nicht eindeutig ist.
        Beides fuehrt zum selben Verhalten: die Angabe bleibt stehen.

        vers=None ist eine Angabe ohne Vers ("Psalm 23"). Dann wird nur
        die Kapitelnummer umgerechnet, und nur wenn das Kapitel als
        GANZES auf ein anderes fuehrt."""
        z = self.zaehlungen.get(zaehlung)
        if not z:
            return None

        # ---- Joel und Maleachi: die Kapitelgrenze liegt anders
        for regel in z.get("buecher", {}).get(str(buch), []):
            if regel["kap"] != kapitel:
                continue
            if vers is None:
                # Ohne Vers nur, wenn das ganze Kapitel auf eines
                # fuehrt. Schlachter Maleachi 3 verteilt sich auf zwei
                # Kapitel -- "Maleachi 3" ist dann nicht umzurechnen.
                passend = [r for r in z["buecher"][str(buch)]
                           if r["kap"] == kapitel]
                ziele = {r["ziel_kap"] for r in passend}
                if len(ziele) == 1 and len(passend) == 1:
                    return (passend[0]["ziel_kap"], None)
                return None
            if regel["vers_von"] <= vers <= regel["vers_bis"]:
                return (regel["ziel_kap"], vers + regel["vers_plus"])

        # ---- Psalmen, englische Zaehlung: Ueberschrift zaehlt nicht mit
        versatz = z.get("psalm_versatz", {}).get(str(kapitel))
        if buch == 19 and versatz:
            if vers is None:
                return None               # die Nummer bleibt dieselbe
            neu = vers - versatz
            if neu < 1:
                # Der Vers IST die Ueberschrift. Englisch hat sie
                # nicht, es gibt also kein Gegenstueck.
                return None
            return (kapitel, neu)

        # ---- Psalmen, Synodalzaehlung: andere Nummer, gleicher Vers
        nummer = z.get("psalm_nummer", {}).get(str(kapitel))
        if buch == 19 and nummer:
            return (nummer, vers)

        return None


_ZIFFER_TRENNER = {"es": ":", "pt": ":"}


def stelle_schreiben(name, kapitel, vers, trenner=","):
    """"Joel 2:28" oder "Псалом 22"."""
    if vers is None:
        return f"{name} {kapitel}"
    return f"{name} {kapitel}{trenner}{vers}"


def hinweis_bauen(stellen, sprache, trenner=","):
    """Die Zeile fuer den Systemprompt, oder "".

    stellen ist eine Liste von (quelltext, zielname, kapitel, vers).
    Vorgegeben wird die fertige Zielangabe -- nicht die Regel. Ein
    Sprachmodell, das rechnen soll, rechnet falsch."""
    if not stellen:
        return ""
    teile = [f"„{quell}“ heisst dort {stelle_schreiben(name, k, v, trenner)}"
             for quell, name, k, v in stellen]
    return ("\n- Die Bibelstellen werden in der Zaehlung der Zielsprache "
            "angegeben: " + "; ".join(teile) + ".")


def _muster(text):
    return re.escape(text).replace(r"\ ", r"\s+")


def steht_drin(ausgabe, name, kapitel, vers):
    """Steht die Zielangabe im Text -- mit IRGENDEINEM Trennzeichen?

    DAS IST DER PUNKT. config.STELLEN_TRENNER ist nur fuer Spanisch und
    Portugiesisch gemessen; fuer Englisch und Russisch steht dort
    nichts, und dann gilt das deutsche Komma. Ein englisches Modell
    schreibt aber "Joel 2:28", weil das die englische Schreibweise ist
    -- und das ist richtig.

    Wer hier auf das Komma bestuende, machte aus einer richtigen
    Uebersetzung eine schlechtere. Geprueft werden darum Name, Kapitel
    und Vers; welches Zeichen dazwischen steht, bleibt dem Modell.
    """
    kopf = _beugbar(name)
    if vers is None:
        return re.search(kopf + r"\s*" + str(kapitel) + r"\b",
                         ausgabe) is not None
    return re.search(kopf + r"\s*" + str(kapitel)
                     + r"\s*[,:.]\s*" + str(vers) + r"\b",
                     ausgabe) is not None


def _beugbar(name):
    """Das Muster fuer einen Buchnamen, der gebeugt sein darf.

    IM LIVE-LAUF AUFGEFALLEN: vorgegeben war „Псалом 22", das Modell
    schrieb „в Псалме 22" -- derselbe Psalm, nur im Praepositiv.
    Russisch beugt Buchnamen, Deutsch und Englisch tun es auch
    gelegentlich ("im Johannesevangelium"). Wer hier auf der
    Nennform bestuende, haette eine richtige Uebersetzung als falsch
    gemeldet und womoeglich darin herumkorrigiert.

    Geprueft wird darum der STAMM des letzten Wortes -- dasselbe
    Verfahren, mit dem glossar.finde_in() fremdsprachige Flexion
    erfasst -- und danach beliebige Wortzeichen. Die ZAHLEN muessen
    exakt stimmen; darauf kommt es an."""
    from glossar import stamm
    worte = name.split()
    if not worte:
        return r"(?!)"
    vorn = [re.escape(w) for w in worte[:-1]]
    return r"\s+".join(vorn + [re.escape(stamm(worte[-1])) + r"\w*"])


def nachtragen(ausgabe, stellen, trenner=","):
    """Setzt die Zielangabe ein, wo das Modell sie nicht genommen hat.

    Rueckgabe (text, ersetzt). Ersetzt wird nur, was sicher ist: die
    alte Angabe muss im Text WOERTLICH stehen (bis auf den Weissraum
    und das Trennzeichen). Steht sie nicht da, hat das Modell
    umformuliert, und dann wird nichts angefasst -- ein
    Suchen-und-Ersetzen auf Verdacht macht aus einer richtigen
    Uebersetzung eine kaputte."""
    ersetzt = []
    for quell, name, k, v in stellen:
        if steht_drin(ausgabe, name, k, v):
            continue                       # das Modell hat es genommen
        ziel = stelle_schreiben(name, k, v, trenner)
        # Die alte Angabe auch mit anderem Trennzeichen finden: das
        # Modell schreibt die QUELLSTELLE womoeglich schon in seiner
        # eigenen Schreibweise ab ("Joel 3:1" statt "Joel 3,1").
        # Jedes Komma, jeden Doppelpunkt und jeden Punkt im Muster
        # gegen "eines von dreien" tauschen. re.escape laesst das
        # Komma unberuehrt und schreibt den Punkt als \. -- beides
        # muss hier getroffen werden.
        locker = re.sub(r"\\?[,:.]", "[,:.]", _muster(quell))
        pat = re.compile(locker, re.IGNORECASE)
        neu, anzahl = pat.subn(ziel, ausgabe)
        if anzahl:
            ausgabe = neu
            ersetzt.append((quell, ziel))
    return ausgabe, ersetzt
