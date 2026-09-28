#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Merkt, wenn jemand in einer anderen Sprache spricht als eingestellt.

DAS PROBLEM

Steht die Ausgangssprache auf Deutsch und es spricht jemand Englisch,
bekommt Whisper die Sprache VORGEGEBEN (language=de). Es erfindet dann
deutsche Woerter aus englischen Lauten -- und weil der Text danach
plausibel aussieht, uebersetzt das Modell ihn brav weiter. Jede
Zielsprache bekommt Unsinn, und am Pult sieht alles normal aus.

WAS HIER NICHT PASSIERT

Umgeschaltet wird NICHTS. Diese Datei stellt eine Vermutung an, mehr
nicht. Welche Sprache gilt, entscheidet ein Mensch am Pult -- eine
Automatik, die mitten in der Predigt die Ausgangssprache wechselt,
waere schlimmer als das Problem.

WARUM NICHT BEI JEDEM SEGMENT

Gemessen mit large-v3-turbo, float16, auf einer RTX 5080:

    detect_language   76 ms   (unabhaengig von der Tondauer --
                               Whisper fuellt ohnehin auf 30 s auf)
    transcribe 5 s    85 ms

Bei jedem Segment zu pruefen wuerde den Whisper-Anteil also fast
verdoppeln. Auf der 5060 Ti der Gemeinde ist beides langsamer, das
Verhaeltnis bleibt. Deshalb nur jedes vierte taugliche Segment: der
Aufschlag liegt dann bei rund einem Viertel eines Durchlaufs, und bis
eine Warnung erscheint, vergehen etwa ein bis zwei Minuten
durchgehend fremder Rede. Genau so soll es sein.

GEGEN FEHLALARME

Drei Bedingungen, alle noetig:

  * Nur Segmente ab drei Sekunden. Kurze Stuecke sind die
    unzuverlaessigsten, und ein einzelner Eigenname kippt sie.
  * Die Wahrscheinlichkeit muss deutlich sein (0,8). Whisper gibt sie
    mit aus.
  * DIESELBE fremde Sprache muss dreimal hintereinander gewinnen.

Damit ueberstehen die Faelle, die es im Gottesdienst wirklich gibt,
die Pruefung ohne Warnung: ein Bibelvers mit hebraeischen
Eigennamen, ein englisches Lied zwischendurch, ein Name wie
"Thessalonicher". Sie kommen nicht dreimal hintereinander.

Und ein einziges Segment in der eingestellten Sprache loescht alles
wieder -- die Warnung verschwindet von selbst, sobald wieder Deutsch
gesprochen wird.

EINE SCHWAECHE, DIE BLEIBT

Weil nur jedes vierte Segment geprueft wird, kann eine regelmaessige
Abfolge mit dem Takt zusammenfallen. Wechseln zwei fremde Sprachen
streng ab und kommt gar kein Deutsch dazwischen, trifft jede Probe
dieselbe von beiden, und es wird gewarnt -- obwohl keine dreimal
wirklich hintereinander kam.

Das ist hingenommen und nicht wegprogrammiert: ein Dutzend langer
Segmente ohne ein einziges sicheres Deutsch ist auch dann ein Grund
hinzusehen, wenn der genannte Name geraten ist. Ein engerer Takt
wuerde nur mit anderen Perioden zusammenfallen und kostete Rechenzeit.
"""

# Nur jedes N-te taugliche Segment wird geprueft. Siehe Modulkopf.
JEDES = 4
# Kuerzere Segmente sind zu unzuverlaessig.
MIN_DAUER = 3.0
# Darunter gilt die Erkennung als unsicher und zaehlt gar nicht.
SCHWELLE = 0.8
# So oft dieselbe fremde Sprache, bevor etwas gesagt wird.
NOETIG = 3

# Nur fuers Pult. Eine unbekannte Kennung wird so ausgegeben, wie sie
# kam -- lieber "nn" als eine erfundene Sprache.
NAMEN = {
    "de": "Deutsch", "en": "Englisch", "ru": "Russisch", "fa": "Persisch",
    "uk": "Ukrainisch", "pl": "Polnisch", "ro": "Rumänisch",
    "es": "Spanisch", "fr": "Französisch", "pt": "Portugiesisch",
    "it": "Italienisch", "tr": "Türkisch", "ar": "Arabisch",
    "nl": "Niederländisch", "cs": "Tschechisch", "hu": "Ungarisch",
    "el": "Griechisch", "sr": "Serbisch", "hr": "Kroatisch",
    "sw": "Suaheli", "vi": "Vietnamesisch", "ka": "Georgisch",
}


def name(kennung):
    return NAMEN.get(kennung, kennung)


class Sprachwache:
    """Zaehlt, wie oft hintereinander eine fremde Sprache gewonnen hat."""

    def __init__(self, quelle, jedes=JEDES, min_dauer=MIN_DAUER,
                 schwelle=SCHWELLE, noetig=NOETIG):
        self.quelle = quelle
        self.jedes = max(1, int(jedes))
        self.min_dauer = min_dauer
        self.schwelle = schwelle
        self.noetig = max(1, int(noetig))
        self._tauglich = 0
        self._letzte = ""
        self._zaehler = 0
        self.verdacht = ""

    def quelle_setzen(self, quelle):
        """Nach einem Sprachwechsel faengt alles von vorn an."""
        if quelle != self.quelle:
            self.quelle = quelle
            self.zuruecksetzen()

    def zuruecksetzen(self):
        self._letzte = ""
        self._zaehler = 0
        self.verdacht = ""

    def dran(self, audiodauer):
        """Soll dieses Segment geprueft werden?

        Zaehlt nur TAUGLICHE Segmente mit. Wuerde jedes vierte Segment
        genommen, auch die kurzen, praegten die unzuverlaessigsten den
        Takt -- und in einer Predigt mit vielen kurzen Einwuerfen
        pruefte man fast nur die."""
        if audiodauer < self.min_dauer:
            return False
        self._tauglich += 1
        return self._tauglich % self.jedes == 0

    def melden(self, sprache, wahrscheinlichkeit):
        """Ein Erkennungsergebnis. Gibt den Verdacht zurueck, oder "".

        Unsicheres zaehlt GAR NICHT -- weder fuer noch gegen. Eine
        Erkennung unter der Schwelle sagt nichts, und sie soll weder
        eine Warnung ausloesen noch eine bestehende loeschen."""
        if not sprache or wahrscheinlichkeit is None:
            return self.verdacht
        if wahrscheinlichkeit < self.schwelle:
            return self.verdacht

        if sprache == self.quelle:
            # Ein einziges sicheres Segment in der eingestellten
            # Sprache raeumt auf. Die Warnung verschwindet von selbst.
            self.zuruecksetzen()
            return ""

        if sprache == self._letzte:
            self._zaehler += 1
        else:
            self._letzte = sprache
            self._zaehler = 1

        if self._zaehler >= self.noetig:
            self.verdacht = sprache
        return self.verdacht

    def satz(self):
        """Der Satz fuers Pult, oder "" wenn es nichts zu sagen gibt."""
        if not self.verdacht:
            return ""
        return (f"Gesprochen wird vermutlich {name(self.verdacht)}, "
                f"eingestellt ist {name(self.quelle)}. Solange das so "
                f"steht, ist jede Übersetzung falsch.")
