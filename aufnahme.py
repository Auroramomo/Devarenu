#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Die Aufnahme der Predigt -- Einwilligung, Frist, Loeschung.

Bis 0.3.0 war die Aufnahme ein Knopf. Ein Druck, und der Ton lief in
eine Datei: ohne Rueckfrage, ohne sichtbaren Hinweis, ohne Loeschung,
und aus dem Saalnetz abrufbar. Wer die Aufnahme ein Jahr lang jeden
Sabbat benutzte, hatte rund fuenfzig Predigten als Rohton auf der
Platte -- und niemand erinnerte daran.

Eine Predigt ist kein Betriebsprotokoll. Es spricht ein Mensch, oft
ueber das, was ihn selbst umtreibt, manchmal ueber Menschen in der
Gemeinde. Dass davon eine Tonaufnahme entsteht, gehoert gefragt und
nicht vorausgesetzt.

WAS DIESES MODUL SICHERSTELLT

  * Ohne bestaetigte Einwilligung faengt nichts an. Auch nicht ueber
    die Schnittstelle: die Pflicht steht hier, nicht in der
    Oberflaeche. Eine Pflicht, die nur im Browser gilt, ist keine.
  * Was laeuft, ist sichtbar -- am Pult und auf jedem Handy.
  * Nach der eingestellten Frist wird geloescht, ohne dass jemand
    daran denkt. Vorgabe sieben Tage.
  * Rechte 700 auf dem Ordner, 600 auf den Dateien. Der Ton gehoert
    dem Dienstbenutzer und sonst niemandem.

DER ALTBESTAND

Wer diese Fassung einspielt, hat vielleicht schon Aufnahmen liegen --
entstanden unter Regeln, die es nicht gab. Die werden NICHT sofort
geloescht: eine Fassung, die beim ersten Start ungefragt Dateien
wegraeumt, ist genau das Gegenteil dessen, was hier gemeint ist. Die
Frist laeuft ab dem Update, und das Pult sagt, wie viele es sind und
wann sie gehen.
"""

import json
import os
import shutil
import time
import wave
from pathlib import Path

# Vorgabe der Aufbewahrung. Sieben Tage: lang genug, um eine Predigt
# nachzuhoeren oder weiterzugeben, kurz genug, dass sich nichts
# ansammelt, was niemand mehr kennt.
TAGE_VORGABE = 7

# Unter dieser Grenze wird nicht mehr aufgenommen. Eine Stunde belegt
# rund 115 MB; zwei Gigabyte sind gut siebzehn Stunden Vorlauf und
# zugleich genug Rest, dass der Rechner nicht an anderer Stelle
# stehenbleibt.
PLATZ_MINDESTENS = 2 * 1024 * 1024 * 1024

# Wie oft nachgesehen wird, ob etwas abgelaufen ist. Beim Start und
# dann stuendlich -- ein Rechner, der von Freitag bis Sonntag laeuft,
# soll die Frist nicht erst beim naechsten Neustart bemerken.
AUFRAEUMEN_ALLE = 3600


def _ordner_sichern(ordner):
    """700 auf dem Ordner. Fehlschlag ist kein Abbruchgrund."""
    try:
        os.chmod(ordner, 0o700)
    except OSError:
        pass


def _datei_sichern(pfad):
    try:
        os.chmod(pfad, 0o600)
    except OSError:
        pass


class Einwilligung:
    """Was bestaetigt wurde, und wann.

    Zwei Haken, beide Pflicht. Der erste ist die Einwilligung der
    predigenden Person, der zweite die Zusage dessen, der aufnimmt --
    dass nur die Predigt mitlaeuft und vor Gebet und Abkuendigungen
    abgeschaltet wird.

    Vermerkt wird der Zeitpunkt, KEIN Name. Wer bestaetigt hat, steht
    nirgends: der Vermerk soll belegen, dass gefragt wurde, und nicht
    eine Person nachweisbar machen."""

    FELDER = ("person_gefragt", "nur_predigt")

    def __init__(self, person_gefragt=False, nur_predigt=False, zeit=""):
        self.person_gefragt = bool(person_gefragt)
        self.nur_predigt = bool(nur_predigt)
        self.zeit = zeit or time.strftime("%Y-%m-%d %H:%M")

    @property
    def vollstaendig(self):
        return self.person_gefragt and self.nur_predigt

    @property
    def fehlend(self):
        return [f for f in self.FELDER if not getattr(self, f)]

    def als_text(self):
        return (
            "Einwilligung zur Tonaufnahme\n"
            f"Bestaetigt am {self.zeit}\n"
            "\n"
            "[x] Die predigende Person wurde gefragt und ist einverstanden.\n"
            "[x] Es wird nur die Predigt aufgenommen; vor Gebet und\n"
            "    Abkuendigungen wird abgeschaltet.\n"
            "\n"
            "Kein Name vermerkt. Dieser Zettel belegt, dass gefragt\n"
            "wurde -- nicht, wer geantwortet hat.\n")

    @classmethod
    def aus_daten(cls, daten):
        d = daten if isinstance(daten, dict) else {}
        return cls(d.get("person_gefragt"), d.get("nur_predigt"))


class Aufnahme:
    """Schreibt den eingehenden Ton in eine Datei -- nach Einwilligung.

    Geschrieben wird fortlaufend, nicht erst am Ende: faellt der Strom
    aus, ist alles bis dahin erhalten. Das war schon so und bleibt."""

    def __init__(self, ordner, rate, tage=TAGE_VORGABE):
        self.ordner = Path(ordner)
        self.rate = rate
        self.tage = tage
        self.datei = None
        self.griff = None
        self.rahmen = 0
        self.seit = 0.0
        self.einwilligung = None
        self.grund_aus = ""

    @property
    def laeuft(self):
        return self.griff is not None

    # ------------------------------------------------------- starten

    def starten(self, einwilligung):
        """(datei, fehler). Ohne vollstaendige Einwilligung: (None, Grund).

        Die Pruefung steht HIER und nicht nur im Browser. Eine Pflicht,
        die sich mit einem curl umgehen laesst, ist keine Pflicht --
        und das Pult haengt im Saalnetz."""
        if self.griff:
            return self.datei, ""
        if not isinstance(einwilligung, Einwilligung):
            einwilligung = Einwilligung.aus_daten(einwilligung)
        if not einwilligung.vollstaendig:
            return None, "einwilligung_fehlt"

        frei = self.platz_frei()
        if frei is not None and frei < PLATZ_MINDESTENS:
            return None, "platz_knapp"

        self.ordner.mkdir(parents=True, exist_ok=True)
        _ordner_sichern(self.ordner)
        stempel = time.strftime("%Y-%m-%d_%H-%M")
        self.datei = self.ordner / f"predigt_{stempel}.wav"
        try:
            self.griff = wave.open(str(self.datei), "wb")
            self.griff.setnchannels(1)
            self.griff.setsampwidth(2)
            self.griff.setframerate(self.rate)
        except OSError as e:
            self.griff = None
            return None, f"nicht_schreibbar: {str(e)[:80]}"
        _datei_sichern(self.datei)

        # Der Vermerk liegt NEBEN der Aufnahme und heisst wie sie. Wer
        # die Datei weitergibt, gibt den Beleg mit; wer sie loescht,
        # loescht ihn mit.
        zettel = self.datei.with_suffix(".einwilligung.txt")
        zettel.write_text(einwilligung.als_text(), encoding="utf-8")
        _datei_sichern(zettel)

        self.einwilligung = einwilligung
        self.rahmen = 0
        self.seit = time.time()
        self.grund_aus = ""
        return self.datei, ""

    def schreiben(self, block, np_modul):
        if not self.griff:
            return
        try:
            self.griff.writeframes(
                (np_modul.clip(block, -1.0, 1.0) * 32767)
                .astype("int16").tobytes())
            self.rahmen += len(block)
        except Exception:
            pass

    def beenden(self, grund=""):
        if not self.griff:
            return None
        try:
            self.griff.close()
        except Exception:
            pass
        self.griff = None
        self.grund_aus = grund
        dauer = self.rahmen / self.rate
        if self.datei and self.datei.exists():
            _datei_sichern(self.datei)
        return {"datei": self.datei.name if self.datei else "",
                "minuten": round(dauer / 60, 1), "grund": grund}

    def lage(self):
        if not self.griff:
            return None
        return {"datei": self.datei.name,
                "minuten": round(self.rahmen / self.rate / 60, 1),
                "sekunden": int(self.rahmen / self.rate),
                "seit": self.seit,
                "einwilligung": self.einwilligung.zeit
                if self.einwilligung else ""}

    # --------------------------------------------------------- Platz

    def platz_frei(self):
        ziel = self.ordner if self.ordner.exists() else self.ordner.parent
        try:
            return shutil.disk_usage(ziel).free
        except OSError:
            return None

    def platz_pruefen(self):
        """Stoppt die laufende Aufnahme, wenn der Platz knapp wird.

        Gibt die freien Bytes zurueck, wenn gestoppt wurde, sonst None.
        Eine volle Platte trifft nicht nur die Aufnahme: der Dienst
        schreibt Protokoll, das Update braucht Platz, und zustand.json
        will gespeichert werden."""
        if not self.laeuft:
            return None
        frei = self.platz_frei()
        if frei is not None and frei < PLATZ_MINDESTENS:
            self.beenden("platz_knapp")
            return frei
        return None


# ------------------------------------------------------- Aufraeumen

def aufnahmen(ordner):
    """Alle Aufnahmen mit Alter, juengste zuerst."""
    o = Path(ordner)
    if not o.exists():
        return []
    jetzt = time.time()
    liste = []
    for p in sorted(o.glob("predigt_*.wav")):
        try:
            st = p.stat()
        except OSError:
            continue
        liste.append({"name": p.name, "pfad": p,
                      "bytes": st.st_size,
                      "stand": st.st_mtime,
                      "tage": (jetzt - st.st_mtime) / 86400})
    liste.sort(key=lambda a: a["stand"], reverse=True)
    return liste


def altbestand(ordner, ab):
    """Aufnahmen, die es vor dem Update schon gab.

    ab ist der Zeitpunkt, an dem diese Fassung zum ersten Mal lief.
    Alles Aeltere ist unter Regeln entstanden, die es damals nicht
    gab."""
    return [a for a in aufnahmen(ordner) if a["stand"] < ab]


def aufraeumen(ordner, tage=TAGE_VORGABE, ab=None, jetzt=None,
               trocken=False):
    """Loescht, was zu alt ist. Gibt zurueck, was geloescht wurde.

    ab schuetzt den Altbestand: fuer Dateien, die vor dem Update
    entstanden, laeuft die Frist erst ab diesem Zeitpunkt. Sonst waere
    beim ersten Start dieser Fassung alles weg, was aelter als eine
    Woche ist -- ungefragt, und genau das soll nicht passieren.

    tage=0 heisst: NICHT loeschen. Ohne diese Zeile rechnete die
    Grenze auf null Sekunden, und damit war jede Datei ueberfaellig --
    aus "nicht loeschen" wurde "alles sofort loeschen", also genau das
    Gegenteil. Gefunden im Pruefstand, nicht im Betrieb.

    trocken=True sagt nur, was geschehen wuerde."""
    if tage <= 0:
        return []
    jetzt = jetzt if jetzt is not None else time.time()
    grenze = tage * 86400
    weg = []
    for a in aufnahmen(ordner):
        # Der Bezugspunkt ist der spaetere von beiden: das Alter der
        # Datei oder der Beginn der Frist.
        beginn = max(a["stand"], ab) if ab else a["stand"]
        if jetzt - beginn < grenze:
            continue
        weg.append(a)
        if trocken:
            continue
        for p in (a["pfad"],
                  a["pfad"].with_suffix(".einwilligung.txt")):
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass
    return weg


def faellig_am(a, tage, ab=None):
    """Wann diese Aufnahme geloescht wird, als Text."""
    beginn = max(a["stand"], ab) if ab else a["stand"]
    return time.strftime("%d.%m.%Y", time.localtime(beginn + tage * 86400))
