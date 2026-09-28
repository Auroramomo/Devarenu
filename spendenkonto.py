#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prueft die IBAN des Spendenkontos -- beim Start, nicht erst beim Geben.

WOZU

Die IBAN steht fest in config.py und laesst sich am Pult NICHT
aendern. Das ist Absicht: wer das Programm weitergibt, soll das
Spendenkonto nicht nebenbei austauschen koennen.

Fest heisst aber nicht unfehlbar. Ein Zahlendreher beim Eintragen
faellt sonst niemandem auf -- der QR-Code sieht aus wie immer, die
Banking-App oeffnet sich, und erst die Ueberweisung scheitert oder
landet woanders. Deshalb wird die Pruefziffer beim Start gerechnet.

WAS BEI EINEM FEHLER PASSIERT

Ein Hinweis am Pult und auf der QR-Seite, mehr nicht. Es wird nichts
geloescht und nichts abgeschaltet: eine falsche IBAN ist ein Grund
nachzusehen, kein Grund, dem Zuhoerer etwas wegzunehmen.

Dazu eine Meldung ueber meldung.sh -- aber nur, wenn auf diesem
Rechner ueberhaupt ein Kanal eingerichtet ist. Es steht KEIN
Meldeziel im Code. Wer keinen Kanal hat, meldet nichts.
"""

import re

# mod 97 nach ISO 13616. Das faengt Zahlendreher und vertauschte
# Ziffern -- nicht, ob es das Konto gibt.
def pruefen(iban):
    """(gueltig, grund). grund ist "" wenn alles stimmt.

    Keine Laendertabelle: die Laengen unterscheiden sich je Land, und
    eine Tabelle im Repo waere eine Liste, die veraltet. Geprueft
    wird, was sich ohne Tabelle pruefen laesst -- und das ist genau
    das, was ein Tippfehler verletzt."""
    roh = re.sub(r"\s+", "", str(iban or "")).upper()
    if not roh:
        return False, "keine IBAN eingetragen"
    if not re.fullmatch(r"[A-Z]{2}[0-9]{2}[A-Z0-9]{10,30}", roh):
        return False, "sieht nicht wie eine IBAN aus"

    # Die ersten vier Zeichen ans Ende, Buchstaben zu Zahlen
    # (A=10 ... Z=35), dann Rest bei Division durch 97. Stimmt die
    # Pruefziffer, ist der Rest 1.
    umgestellt = roh[4:] + roh[:4]
    zahl = "".join(str(int(z, 36)) for z in umgestellt)
    if int(zahl) % 97 != 1:
        return False, "die Pruefziffer stimmt nicht"
    return True, ""


def lage(spende):
    """(gueltig, grund) fuer den SPENDE-Block aus config.py.

    Ohne IBAN ist nichts ungueltig -- dann gibt es den Abschnitt
    einfach nicht, und das ist ein erlaubter Zustand."""
    iban = (spende or {}).get("iban", "")
    if not str(iban).strip():
        return True, ""
    return pruefen(iban)
