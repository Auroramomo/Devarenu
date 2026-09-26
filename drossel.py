#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wie oft ein Geraet aus dem Saal schreiben darf.

Das Saalnetz ist offen -- das ist sein Zweck, jeder Zuhoerer ist
darin. Damit ist jeder Schreibweg von dort ein Weg, ueber den auch
Unsinn hereinkommt: absichtlich oder aus Versehen, durch ein Handy in
der Hosentasche.

DIE ZAHLEN UND WARUM SIE SO STEHEN

Gemessen wurde nichts -- es gibt keine Zuschriftenflut, an der man
messen koennte. Die Zahlen kommen aus der Frage: was tut ein NORMALER
Zuhoerer, und wo liegt das Zehnfache davon?

  Alle 5 Sekunden eine        Wer tippt, braucht laenger. Zwei
                              Meldungen in derselben Sekunde sind ein
                              Doppelklick oder ein Skript.
  200 Zeichen                 Das Feld ist fuer einen Satz gedacht:
                              "Der Ton ist zu leise." Wer mehr zu
                              sagen hat, sagt es nach dem
                              Gottesdienst. Abgeschnitten wird nicht
                              stillschweigend -- die Seite sagt es.
  20 je Geraet und Tag        Ein Zuhoerer, der zwanzigmal meldet,
                              meldet nicht mehr, sondern spielt.
  60 im Briefkasten           Darueber liest sie niemand mehr. Die
                              aeltesten fallen ohnehin heraus, aber
                              der Techniker soll nicht 300 Zeilen
                              wegklicken muessen.

WAS EIN NORMALER ZUHOERER MERKT

Nichts. Er meldet einmal, vielleicht zweimal. Erst wer schneller ist
als ein Mensch tippt, bekommt eine Antwort -- und zwar eine
freundliche, in seiner Sprache, nicht ein stilles Verschlucken.

WARUM IP UND NICHT GERAET

Weil es nichts Besseres gibt. Ein Keks liesse sich loeschen, ein
Fingerabdruck des Browsers waere eine Nachverfolgung, die hier nichts
zu suchen hat. Hinter einem Saalnetz teilen sich normalerweise keine
zwei Handys eine Adresse; tun sie es doch, ist die Grenze von zwanzig
je Tag immer noch reichlich.
"""

import time

ABSTAND = 5.0          # Sekunden zwischen zwei Meldungen
LAENGE = 200           # Zeichen je Meldung
JE_GERAET = 20         # Meldungen je Geraet und Tag
INSGESAMT = 60         # Meldungen im Briefkasten
TAG = 24 * 3600


class Drossel:
    """Zaehlt je Absender. Vergisst von selbst.

    Kein Aufraeumauftrag, kein Hintergrundlauf: was aelter als ein Tag
    ist, faellt beim naechsten Zugriff heraus. Ein Dienst, der
    monatelang laeuft, sammelt sonst eine Adressliste an, die niemand
    braucht."""

    def __init__(self, abstand=ABSTAND, je_geraet=JE_GERAET, tag=TAG):
        self.abstand = abstand
        self.je_geraet = je_geraet
        self.tag = tag
        self._zeiten = {}

    def _aufraeumen(self, jetzt):
        alt = jetzt - self.tag
        for adresse in [a for a, z in self._zeiten.items()
                        if not z or z[-1] < alt]:
            self._zeiten.pop(adresse, None)

    def fragen(self, adresse, jetzt=None):
        """(darf, grund). grund ist "" wenn erlaubt."""
        jetzt = jetzt if jetzt is not None else time.time()
        self._aufraeumen(jetzt)
        zeiten = [z for z in self._zeiten.get(adresse, ())
                  if z > jetzt - self.tag]
        if zeiten and jetzt - zeiten[-1] < self.abstand:
            return False, "zu_schnell"
        if len(zeiten) >= self.je_geraet:
            return False, "zu_viele"
        return True, ""

    def vermerken(self, adresse, jetzt=None):
        jetzt = jetzt if jetzt is not None else time.time()
        self._zeiten.setdefault(adresse, []).append(jetzt)

    def stand(self, adresse, jetzt=None):
        jetzt = jetzt if jetzt is not None else time.time()
        return len([z for z in self._zeiten.get(adresse, ())
                    if z > jetzt - self.tag])


def kuerzen(text, laenge=LAENGE):
    """(text, gekuerzt). Schneidet an einer Wortgrenze, wenn moeglich.

    Mitten im Wort abzuschneiden sieht nach einem Fehler aus; an der
    Wortgrenze sieht es nach einer Grenze aus -- und genau das ist
    es."""
    text = (text or "").strip()
    if len(text) <= laenge:
        return text, False
    schnitt = text[:laenge]
    luecke = schnitt.rfind(" ")
    if luecke > laenge * 0.6:
        schnitt = schnitt[:luecke]
    return schnitt.rstrip() + " …", True
