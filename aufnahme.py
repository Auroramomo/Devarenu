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
  * Der Name ist der, unter dem die Gemeinde sucht:
    Predigt_TT_MM_JJJJ.mp3, mit dem Datum des Aufnahmebeginns. Gibt
    es ihn schon, wird _2, _3 angehaengt -- nie ueberschrieben.

DAS FORMAT

Bis 0.3.7 war es WAV: 115 MB je Stunde, und sieben Tage Aufbewahrung
fuellten damit auch eine grosse Platte. Seit 0.3.8 ist es MP3 mit
48 kbit/s mono -- rund 22 MB je Stunde. Warum gerade 48, steht bei
BITRATE. Geschrieben wird weiter fortlaufend: der Ton geht in einen
Koder, der Koder schreibt Rahmen fuer Rahmen in die Datei, und faellt
der Strom aus, ist alles bis dahin da und abspielbar.

Kann dieser Rechner kein MP3 (kein ffmpeg mit libmp3lame, kein lame),
laeuft die Aufnahme als WAV weiter. Sie faellt NICHT aus. Der
Systemcheck sagt es, bevor jemand den Knopf drueckt.

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
import re
import shutil
import subprocess
import time
import wave
from pathlib import Path

# Vorgabe der Aufbewahrung. Sieben Tage: lang genug, um eine Predigt
# nachzuhoeren oder weiterzugeben, kurz genug, dass sich nichts
# ansammelt, was niemand mehr kennt.
TAGE_VORGABE = 7

# Unter dieser Grenze wird nicht mehr aufgenommen. Eine Stunde MP3
# belegt rund 22 MB (als WAV waren es 115); zwei Gigabyte sind damit
# weit mehr Vorlauf als eine Predigt je braucht und zugleich genug
# Rest, dass der Rechner nicht an anderer Stelle stehenbleibt. Die
# Grenze bleibt, wo sie war -- sie schuetzt nicht die Aufnahme,
# sondern alles andere: Protokoll, Update, zustand.json.
PLATZ_MINDESTENS = 2 * 1024 * 1024 * 1024

# WARUM 48 kbit/s MONO
#
# Der Ton kommt mit 16000 Hz vom Mikrofon (config: MIKRO_RATE). Mehr
# als 8 kHz Bandbreite ist darin nicht enthalten, und mehr braucht
# Sprache auch nicht -- es ist eine Predigt, kein Konzert.
#
# Bei 16 kHz arbeitet LAME im MPEG-2-Modus (MPEG-2 Layer III, "LSF"),
# und dort sind 8 bis 160 kbit/s erlaubt. Gemessen an dem, was diese
# Datei transportieren muss:
#
#   32 kbit/s  hoerbar: Zischlaute verschmieren, "s" und "f" werden
#              schwer unterscheidbar. Fuer eine Predigt, die jemand
#              nachhoert, zu wenig.
#   48 kbit/s  unauffaellig. Der gewaehlte Wert.
#   64 kbit/s  ein Drittel mehr Platz fuer nichts, was bei 8 kHz
#              Bandbreite noch ankaeme.
#
# Feste Bitrate, keine variable: die Groesse laesst sich dann aus der
# Dauer ausrechnen (und umgekehrt), was fuer die Platzpruefung und
# fuer eine abgeschnittene Datei zaehlt.
#
# 48 kbit/s sind 6 kB/s: eine Stunde rund 22 MB, gegenueber 115 MB als
# WAV. Das ist der eigentliche Gewinn -- sieben Tage Aufbewahrung mit
# mehreren Aufnahmen passen jetzt in einen Bruchteil des Platzes, und
# was per Hand weitergegeben wird, passt an eine Mail.
BITRATE = "48k"

# Der Name, den die Gemeinde erwartet: Predigt_03_10_2026.mp3, mit dem
# Datum des AUFNAHMEBEGINNS. Laeuft eine Aufnahme ueber Mitternacht,
# steht der Tag darauf, an dem sie anfing -- danach sucht man.
NAME_VORNE = "Predigt"
_NAME_MUSTER = re.compile(r"^predigt[_-]", re.IGNORECASE)
_ENDUNGEN = (".mp3", ".wav")

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


# ------------------------------------------------------- Der Koder
#
# MP3 SCHREIBT KEIN PYTHON-MODUL DER STANDARDBIBLIOTHEK.
#
# Gebraucht wird ein Koder von aussen. Der ist schon da: ffmpeg steht
# seit jeher in INSTALLIEREN.sh und in einrichten.sh, weil die
# Tonausgabe ihn ohnehin braucht. Ob dieses ffmpeg auch MP3 SCHREIBEN
# kann, ist eine zweite Frage -- das kann es nur mit libmp3lame, und
# das ist eine Uebersetzungsoption. Alle grossen Distributionen
# (Arch, Debian, Fedora, Ubuntu) liefern sie mit; eine selbstgebaute
# oder abgespeckte Fassung womoeglich nicht.
#
# Darum wird gefragt, nicht angenommen -- und zwar EINMAL beim Start
# und nicht erst, wenn jemand am Sonntag den Knopf drueckt.
#
# Drei Stufen, alle ohne Netz:
#   1. ffmpeg mit libmp3lame. Der Normalfall, nichts nachzuinstallieren.
#   2. lame als eigenes Programm. Winziges Paket, auf vielen Systemen
#      ohnehin da (es ist die Abhaengigkeit hinter libmp3lame).
#   3. Kein Koder: dann WAV wie bisher, mit deutlichem Hinweis. Eine
#      Aufnahme, die gar nicht erst anfaengt, weil ein Koder fehlt,
#      waere der schlechteste aller Ausgaenge -- der Prediger spricht
#      trotzdem.
#
# Nachzuruesten ist Stufe 2 offline vom selben Stick, der auch das
# Update bringt: "pacman -U lame-*.pkg.tar.zst". Das steht so in der
# Meldung, damit niemand erst suchen muss.
_koder_gemerkt = {}


def koder_pruefen(neu_fragen=False):
    """(weg, hinweis). weg ist "ffmpeg", "lame" oder "".

    Das Ergebnis wird gemerkt: die Frage kostet einen Unterprozess,
    und die Antwort aendert sich zwischen zwei Neustarts nicht."""
    if _koder_gemerkt and not neu_fragen:
        return _koder_gemerkt["weg"], _koder_gemerkt["hinweis"]

    weg, hinweis = "", ""
    if shutil.which("ffmpeg"):
        try:
            aus = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"],
                                 capture_output=True, text=True, timeout=10)
            if "libmp3lame" in aus.stdout:
                weg = "ffmpeg"
            else:
                hinweis = ("Das ffmpeg auf diesem Rechner kann kein MP3 "
                           "schreiben (libmp3lame fehlt).")
        except Exception as e:
            hinweis = f"ffmpeg liess sich nicht befragen: {str(e)[:60]}"
    else:
        hinweis = "ffmpeg fehlt."

    if not weg and shutil.which("lame"):
        weg, hinweis = "lame", ""

    # hinweis ist NUR der Grund, nicht die Folge und nicht die
    # Abhilfe. Wer ihn anzeigt, weiss selbst, in welchen Satz er
    # gehoert -- der Systemcheck baut daraus einen, das Pult einen
    # anderen. Zweimal dieselbe Erklaerung hintereinander liest sich
    # wie ein Fehler.
    if not weg and not hinweis:
        hinweis = "Kein MP3-Koder gefunden."

    _koder_gemerkt.update(weg=weg, hinweis=hinweis)
    return weg, hinweis


def _befehl(weg, pfad, rate):
    if weg == "ffmpeg":
        return ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "s16le", "-ar", str(rate), "-ac", "1", "-i", "pipe:0",
                "-c:a", "libmp3lame", "-b:a", BITRATE, "-ac", "1",
                # Kein Xing-Kopf: den schreibt ffmpeg erst am Ende und
                # muss dafuer an den Dateianfang zurueckspringen. Faellt
                # der Strom aus, ist das nie passiert -- und mit einem
                # halb geschriebenen Kopf tun sich manche Abspieler
                # schwerer als mit gar keinem. Ohne ihn ist die Datei
                # eine reine Folge von Rahmen: an jeder Stelle
                # abschneidbar und trotzdem abspielbar.
                "-write_xing", "0",
                # Und kein ID3-Kopf. Zusammen mit -write_xing 0 ist die
                # Datei damit nichts als eine Folge von MP3-Rahmen:
                # kein Kopf, der nachtraeglich gefuellt werden muss,
                # nichts, was beim Abschneiden halb dasteht. Nebenbei
                # steht dann auch nicht "Lavf62.x" als Erzeuger darin.
                "-id3v2_version", "0",
                # Jeden Rahmen sofort hinausschreiben, nicht sammeln.
                "-flush_packets", "1",
                str(pfad)]
    return ["lame", "--quiet", "-r", "-s", str(rate / 1000.0),
            "--bitwidth", "16", "--signed", "--little-endian",
            "-m", "m", "-b", str(int(BITRATE.rstrip("k"))),
            "-", str(pfad)]


def freier_name(ordner, jetzt=None, endung=".mp3"):
    """Predigt_TT_MM_JJJJ.mp3 -- und bei Kollision _2, _3, ...

    NIE UEBERSCHREIBEN. Zwei Gottesdienste an einem Tag sind der
    Normalfall (Predigt und Nachmittagsstunde), und die zweite darf
    die erste nicht loeschen.

    Belegt gilt ein Name schon dann, wenn es ihn mit IRGENDEINER
    Endung gibt: liegt Predigt_03_10_2026.wav da, weil damals kein
    Koder vorhanden war, faengt die naechste bei _2 an. Sonst stuenden
    zwei verschiedene Aufnahmen unter demselben Namen nebeneinander
    und nur die Endung unterschiede sie."""
    ordner = Path(ordner)
    tag = time.strftime("%d_%m_%Y", time.localtime(jetzt or time.time()))
    nummer = 1
    while True:
        stamm = f"{NAME_VORNE}_{tag}" if nummer == 1 \
            else f"{NAME_VORNE}_{tag}_{nummer}"
        if not any(ordner.glob(stamm + ".*")):
            return ordner / (stamm + endung)
        nummer += 1


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
        self.prozess = None
        self.weg = ""
        self.koder_hinweis = ""
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
        self.weg, self.koder_hinweis = koder_pruefen()
        self.datei = freier_name(self.ordner,
                                 endung=".mp3" if self.weg else ".wav")
        # Die Datei zuerst anlegen und auf 600 setzen, DANN fuellen.
        # Sonst stuende sie einen Augenblick lang mit den Rechten da,
        # die die umask hergibt -- und in dem Augenblick ist schon Ton
        # darin.
        try:
            self.datei.touch(mode=0o600, exist_ok=False)
        except OSError as e:
            self.datei = None
            return None, f"nicht_schreibbar: {str(e)[:80]}"
        _datei_sichern(self.datei)
        try:
            if self.weg:
                self.prozess = subprocess.Popen(
                    _befehl(self.weg, self.datei, self.rate),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE)
                self.griff = self.prozess.stdin
            else:
                self.griff = wave.open(str(self.datei), "wb")
                self.griff.setnchannels(1)
                self.griff.setsampwidth(2)
                self.griff.setframerate(self.rate)
        except (OSError, ValueError) as e:
            self.griff = None
            self.prozess = None
            self.datei.unlink(missing_ok=True)
            self.datei = None
            return None, f"nicht_schreibbar: {str(e)[:80]}"

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
        roh = (np_modul.clip(block, -1.0, 1.0) * 32767).astype("int16").tobytes()
        try:
            if self.prozess:
                self.griff.write(roh)
            else:
                self.griff.writeframes(roh)
            self.rahmen += len(block)
        except Exception:
            # Bricht der Koder weg, bricht nicht der Gottesdienst ab.
            # Was bis dahin geschrieben ist, bleibt abspielbar -- eine
            # MP3-Datei ist eine Folge von Rahmen ohne Abschluss.
            pass

    def beenden(self, grund=""):
        if not self.griff:
            return None
        try:
            self.griff.close()
        except Exception:
            pass
        self.griff = None
        if self.prozess:
            # Dem Koder Zeit lassen, den Rest auszuschreiben -- aber
            # nicht beliebig viel. Haengt er, ist die Datei bis dahin
            # trotzdem vollstaendig genug, und das Pult darf nicht
            # stehenbleiben.
            try:
                self.prozess.wait(timeout=20)
            except Exception:
                try:
                    self.prozess.kill()
                except Exception:
                    pass
            self.prozess = None
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
                "koder": self.weg,
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
    # Gross und klein, mp3 und wav. Bis 0.3.7 hiessen die Dateien
    # predigt_2026-01-10_09-30.wav; ab 0.3.8 Predigt_10_01_2026.mp3.
    # Wer diese Fassung einspielt, hat womoeglich beides liegen -- und
    # der Altbestand muss weiter aufgelistet werden UND weiter
    # ablaufen. Eine Umbenennung waere der falsche Weg: sie aenderte
    # Dateien, die unter der alten Zusage entstanden sind.
    for p in sorted(x for x in o.iterdir()
                    if x.is_file() and x.suffix.lower() in _ENDUNGEN
                    and _NAME_MUSTER.match(x.name)):
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


def loeschen(ordner, name, laeuft=""):
    """Loescht EINE Aufnahme aus der eigenen Liste. (gut, grund).

    DER NAME WIRD NICHT ALS PFAD BEHANDELT. Gesucht wird in der Liste,
    die aufnahmen() ohnehin aufbaut, und zwar auf Gleichheit des
    Dateinamens. Damit ist jeder Weg nach draussen von selbst
    verschlossen: "../../etc/passwd" steht in keiner Liste. Ein
    Path(name).name haette dasselbe Ziel, aber nur solange niemand die
    Zeile umbaut -- hier gibt es gar keinen Pfad, den man umbauen
    koennte.

    laeuft ist der Dateiname der gerade laufenden Aufnahme, falls eine
    laeuft. Die ist nicht loeschbar: der Koder schreibt noch hinein,
    und was dabei herauskaeme, waere eine halbe Datei und ein Pult, das
    "geloescht" sagt und daneben weiter "Aufnahme laeuft"."""
    if laeuft and name == laeuft:
        return False, "laeuft"
    gefunden = next((a for a in aufnahmen(ordner) if a["name"] == name), None)
    if gefunden is None:
        return False, "nicht_gefunden"
    for pfad in (gefunden["pfad"],
                 gefunden["pfad"].with_suffix(".einwilligung.txt")):
        try:
            pfad.unlink(missing_ok=True)
        except OSError as e:
            return False, f"nicht_loeschbar: {str(e)[:60]}"
    return True, ""


def faellig_am(a, tage, ab=None):
    """Wann diese Aufnahme geloescht wird, als Text."""
    beginn = max(a["stand"], ab) if ab else a["stand"]
    return time.strftime("%d.%m.%Y", time.localtime(beginn + tage * 86400))
