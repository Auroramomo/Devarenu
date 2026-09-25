#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Das freiwillige Pult-Passwort.

Das Pult haengt im Saalnetz, und im Saalnetz ist jeder Zuhoerer. Ohne
Passwort kann dort jeder das Pult bedienen: die Uebersetzung anhalten,
Aufnahmen abrufen, die Mitschrift ins Protokoll einschalten. Das war
schon immer so und bleibt die Vorgabe -- in einer kleinen Gemeinde ist
ein Passwort mehr Last als Gewinn, und wer sonntags eines tippen muss,
schreibt es an den Bildschirm.

Wer es anders will, traegt am Pult eines ein. Dann gilt:

  * Die ZUHOERERSEITE bleibt offen. Sie ist der Zweck des Netzes.
  * Vom Gemeinderechner selbst (localhost) wird NIE gefragt. Sonst
    sperrt sich aus, wer das Passwort vergisst -- und genau das
    passiert nach einem halben Jahr.
  * Alles andere verlangt einmal je Geraet das Passwort. Danach merkt
    es der Browser ein Jahr lang.

Gespeichert wird nur ein Hash, nie das Passwort. Auch der
Fehlerbericht bekommt ihn nicht zu sehen.
"""

import hashlib
import hmac
import ipaddress
import json
import os
import secrets
import time
from pathlib import Path

# PBKDF2 mit SHA-256. Kein Argon2, kein bcrypt: beides waere ein
# zusaetzliches Paket auf einem Rechner ohne Netz. PBKDF2 steckt in der
# Standardbibliothek und ist fuer ein Passwort, das nur im Saalnetz
# etwas nuetzt, mehr als genug.
RUNDEN = 240_000
VERFAHREN = "pbkdf2_sha256"

# Wie lange sich ein Geraet gemerkt wird. Ein Jahr, damit niemand im
# Gottesdienst vor einer Passwortabfrage sitzt, weil der Techniker
# gewechselt hat.
KEKS = "devarenu_pult"
KEKS_DAUER = 365 * 24 * 3600

# Wege, die IMMER offen bleiben -- die Zuhoererseite und was sie laedt.
# Bewusst eine Erlaubnisliste und keine Sperrliste: kommt spaeter ein
# Pult-Weg dazu, ist er geschuetzt, ohne dass jemand daran denkt. Eine
# vergessene Sperre faellt niemandem auf, ein zu viel geschuetzter Weg
# schon beim ersten Versuch.
OFFEN_GENAU = {
    "/",                        # die Zuhoererseite
    "/strom",                   # ihr Datenstrom
    "/api/sprachen",            # welche Sprachen es gibt
    "/api/nachricht",           # Zuschrift aus dem Saal
    "/api/messung/wiedergabe",  # ihre eigene Messung
    "/logo.png",
    "/favicon.ico",
    "/spende.svg",
    "/anleitung.pdf",
    "/pult-anmeldung",          # sonst kaeme niemand hinein
}
OFFEN_ANFANG = ("/ton/",)       # die Tonhaeppchen je Sprache


def hashen(passwort, salz=None):
    """Aus einem Passwort die Zeile, die in zustand.json landet."""
    salz = salz or secrets.token_bytes(16)
    roh = hashlib.pbkdf2_hmac("sha256", passwort.encode("utf-8"),
                              salz, RUNDEN)
    return f"{VERFAHREN}${RUNDEN}${salz.hex()}${roh.hex()}"


def stimmt(passwort, gespeichert):
    """Passt das Passwort zur gespeicherten Zeile?"""
    if not gespeichert or not passwort:
        return False
    try:
        art, runden, salz, roh = gespeichert.split("$")
        if art != VERFAHREN:
            return False
        neu = hashlib.pbkdf2_hmac("sha256", passwort.encode("utf-8"),
                                  bytes.fromhex(salz), int(runden))
    except (ValueError, TypeError):
        return False
    # compare_digest und nicht ==: ein Vergleich, der beim ersten
    # falschen Zeichen abbricht, verraet ueber die Zeit, wie weit man
    # gekommen ist.
    return hmac.compare_digest(neu.hex(), roh)


def ausweis(gespeichert):
    """Der Wert, der im Keks steht.

    Abgeleitet aus dem gespeicherten Hash, nicht zufaellig: dann
    braucht der Server keine Liste offener Sitzungen, die Anmeldung
    ueberlebt jeden Neustart, und ein geaendertes Passwort macht alle
    alten Kekse mit einem Schlag ungueltig."""
    return hmac.new(gespeichert.encode("utf-8"), b"pult-ausweis",
                    hashlib.sha256).hexdigest()


def ausweis_gilt(wert, gespeichert):
    return bool(wert) and hmac.compare_digest(wert, ausweis(gespeichert))


def oeffentlich(pfad):
    """Gehoert der Weg der Zuhoererseite?"""
    return pfad in OFFEN_GENAU or pfad.startswith(OFFEN_ANFANG)


def vom_rechner_selbst(host):
    """Sitzt der Aufrufer am Gemeinderechner?

    Wer hier sitzt, hat ohnehin Tastatur und Bildschirm -- ein Passwort
    schuetzte davor nichts und sperrte nur den aus, der es vergessen
    hat.

    Geprueft wird die ganze Loopback-Familie, nicht nur 127.0.0.1:
    127.0.0.2 und alles darunter ist derselbe Rechner, und ::1 ebenso.
    Eine Liste aus drei Zeichenketten haette irgendwann einen Fall
    uebersehen -- und dann stuende jemand vor seinem eigenen Pult."""
    if host in ("localhost", ""):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class Einmalschluessel:
    """Kurzlebige Schluessel fuer den Fehlerbericht aufs Handy.

    Der QR-Code am Pult zeigt auf /fehlerbericht.txt. Mit gesetztem
    Passwort kaeme das Handy dort nicht hinein -- es ist im Saalnetz und
    hat keinen Keks. Ein Schluessel im Link loest das, ohne das Passwort
    aufs Handy zu bringen: er wird am Pult erzeugt, gilt kurz und nur
    fuer diesen einen Weg.

    Im Speicher und nicht auf der Platte: nach einem Neustart soll ein
    alter Zettel an der Wand nichts mehr oeffnen."""

    # Lang genug zum Scannen und Laden, kurz genug, dass ein
    # abfotografierter Bildschirm nach dem Gottesdienst nichts mehr
    # nuetzt.
    DAUER = 15 * 60
    # Ein Handy laedt gern zweimal -- Vorschau und Download. Drei Griffe
    # sind Nachsicht, dreissig waeren ein Dauerzugang.
    GRIFFE = 3

    def __init__(self):
        self._schluessel = {}

    def neu(self):
        s = secrets.token_urlsafe(16)
        self._schluessel[s] = {"bis": time.time() + self.DAUER,
                               "uebrig": self.GRIFFE}
        self._aufraeumen()
        return s

    def einloesen(self, s):
        eintrag = self._schluessel.get(s or "")
        if not eintrag:
            return False
        if time.time() > eintrag["bis"]:
            self._schluessel.pop(s, None)
            return False
        eintrag["uebrig"] -= 1
        if eintrag["uebrig"] <= 0:
            self._schluessel.pop(s, None)
        return True

    def _aufraeumen(self):
        jetzt = time.time()
        for s in [k for k, v in self._schluessel.items() if v["bis"] < jetzt]:
            self._schluessel.pop(s, None)


class Wache:
    """Liest den gespeicherten Hash und sagt, ob ein Aufruf durchdarf.

    Die Datei wird nur neu gelesen, wenn sie sich geaendert hat. Das
    kostet einen stat je Aufruf und erspart einen Neustart, wenn jemand
    das Passwort am Rechner zuruecksetzt -- der haeufigste Fall, und
    zugleich der, in dem niemand an systemctl denkt."""

    def __init__(self, datei):
        self.datei = Path(datei)
        self._hash = ""
        self._stand = None
        self.schluessel = Einmalschluessel()

    def _frisch(self):
        try:
            stand = self.datei.stat().st_mtime_ns
        except OSError:
            self._hash = ""
            self._stand = None
            return
        if stand == self._stand:
            return
        self._stand = stand
        try:
            roh = json.loads(self.datei.read_text(encoding="utf-8"))
            wert = roh.get("pult_passwort")
            self._hash = wert if isinstance(wert, str) else ""
        except (OSError, ValueError):
            # Eine unlesbare Datei darf das Pult nicht aussperren.
            self._hash = ""

    @property
    def gesetzt(self):
        self._frisch()
        return bool(self._hash)

    @property
    def hash(self):
        self._frisch()
        return self._hash

    def darf(self, pfad, host, keks, schluessel=None):
        """(ja, grund). grund nur fuer das Protokoll."""
        if not self.gesetzt:
            return True, "kein_passwort"
        if oeffentlich(pfad):
            return True, "oeffentlich"
        if vom_rechner_selbst(host):
            return True, "am_rechner"
        if ausweis_gilt(keks, self._hash):
            return True, "angemeldet"
        if schluessel and self.schluessel.einloesen(schluessel):
            return True, "einmalschluessel"
        return False, "gesperrt"


def zuruecksetzen(datei):
    """Loescht das Passwort. Fuer den Befehl am Rechner."""
    p = Path(datei)
    roh = json.loads(p.read_text(encoding="utf-8"))
    hatte = bool(roh.get("pult_passwort"))
    roh["pult_passwort"] = ""
    zwischen = p.with_suffix(p.suffix + ".neu")
    zwischen.write_text(json.dumps(roh, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    os.chmod(zwischen, 0o600)
    os.replace(zwischen, p)
    return hatte
