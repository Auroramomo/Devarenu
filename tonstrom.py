#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ein durchgehender MP3-Strom je Sprache. Versuch C.

    python tonstrom.py --probe        zehn Sekunden Stille kodieren

WARUM UEBERHAUPT
----------------
Die Zuhoererseite spielt bis 0.4.3 Haeppchen ab: je Abschnitt eine
WAV-Datei in ein audio-Element. Sobald das Handy gesperrt wird, hoert
der Ton nach zehn bis fuenfzehn Sekunden auf.

Versuch B (0.4.3) liess das Element zwischen den Haeppchen Stille in
Schleife spielen, damit es nie pausiert. Gemessen auf einem Galaxy Z
Fold 7 mit Firefox: half nicht. Das Tonprotokoll zeigte dabei den
Grund -- staendig "ended", auch beim Stille-Fueller. Jedes Ende eines
Mediums ist dem Browser ein Anlass, die Tonsitzung abzuraeumen, und
davon gab es im Sekundentakt eines.

Also kein weiterer Versuch mit Einzelstuecken. EIN Medium, das nie
endet: ein MP3-Strom, der laeuft, solange jemand zuhoert, und in dem
Stille steht, wenn gerade niemand spricht.

WIE DIE ZEITACHSE ENTSTEHT
--------------------------
Der Koder bekommt PCM im Echtzeittakt, in Bloecken von 20 ms. Liegt
ein fertiger Abschnitt bereit, laeuft er hinein; sonst Stille. Das
ist der ganze Kern: die Uhr des Stroms ist die Wanduhr, nicht die
Summe der Abschnitte. Zwei Zuhoerer derselben Sprache hoeren deshalb
dasselbe zur selben Zeit, und wer spaeter dazukommt, steigt dort ein,
wo die anderen gerade sind -- nicht am Anfang.

Getaktet wird gegen eine absolute Zeitbasis, nicht mit sleep(0.02) in
einer Schleife: der Fehler von sleep summiert sich sonst ueber eine
Dreiviertelstunde auf Minuten. Dieselbe Begruendung wie bei
datei_thread in server.py.

WAS NICHT PASSIERT
------------------
Kein Koder, solange niemand zuhoert. Kein zweiter Koder fuer eine
Sprache, egal wie viele Handys daran haengen. Und kein Zuhoerer, der
andere bremst: jeder hat seine eigene Warteschlange, und wer sie
volllaufen laesst, wird getrennt. Der Client verbindet neu und steigt
wieder am Live-Punkt ein.

OHNE KODER
----------
Fehlt ffmpeg mit libmp3lame und fehlt lame, gibt es keinen Strom. Die
Hoererseite bleibt dann beim bisherigen Weg; der Systemcheck sagt,
woran es liegt. Dieselben zwei Wege wie bei der Predigtaufnahme --
eine dritte Abhaengigkeit waere eine zu viel.
"""

import queue
import subprocess
import threading
import time
import wave
from pathlib import Path

import numpy as np

import aufnahme

# Eine gemeinsame Abtastrate fuer alles, was in den Strom laeuft.
# 22050 ist die Rate der Piper-Stimmen: der haeufigste Fall kostet
# damit gar keine Umrechnung, und nur der Originalton (16000) muss
# umgerechnet werden.
RATE = 22050

# Dieselbe Bitrate wie die Predigtaufnahme. Sie ist dort an echter
# Sprache gemessen und reicht dafuer; eine zweite Zahl waere eine
# zweite Stelle, an der jemand sie pflegen muesste. 48 kbit/s mono
# sind ausserdem 6 KB je Sekunde -- im Saal-WLAN nichts, und auf
# einem Handy ohne Datenverbindung genauso wenig.
BITRATE = aufnahme.BITRATE

# 20 ms je Block. Kuerzer bringt nichts: ein MP3-Rahmen bei 22050 Hz
# fasst 1152 Abtastwerte, also rund 52 ms. Laenger kostet Verzoegerung.
BLOCK_MS = 20
BLOCK = int(RATE * BLOCK_MS / 1000)

# Wie viel fertiger Ton hoechstens warten darf. Der Client hielt bis
# 0.4.3 sechs Haeppchen zurueck, bei einer gemessenen Abschnittslaenge
# von rund drei bis vier Sekunden also gut zwanzig Sekunden. Mehr
# heisst: der Zuhoerer hoert etwas, das mit dem, was vorn gerade
# gesagt wird, nichts mehr zu tun hat. Dann lieber eine Luecke.
RUECKSTAU_S = 20.0

# Was ein Zuhoerer hoechstens ungelesen liegen lassen darf, bevor er
# getrennt wird. Wer es nicht abholt, hat keine Verbindung mehr, und
# seinen Puffer wachsen zu lassen hiesse, den Speicher des Rechners
# an ein Handy zu haengen, das nicht mehr da ist.
#
# GERECHNET, NICHT GERATEN. Der Lesefaden gibt Stuecke zu 1024 Byte
# weiter, und bei 48 kbit/s sind das 6000 Byte je Sekunde -- also
# knapp sechs Stuecke. Die erste Fassung stand auf 200 mit dem
# Kommentar "vier Sekunden"; in Wahrheit waren es vierunddreissig.
# Der Pruefstand hat es gefunden.
BROCKEN = 1024
_JE_S = int(float(str(BITRATE).rstrip("k")) * 1000 / 8 / BROCKEN)
ZUHOERER_PUFFER = max(8, _JE_S * 4)        # vier Sekunden

# Wie lange ein Koder nach dem letzten Zuhoerer noch laeuft. Ein
# Handy, das kurz das Netz verliert, soll nicht jedes Mal einen neuen
# Koder anwerfen -- das kostet mehr als zehn Sekunden Stille.
NACHLAUF_S = 10.0


def koder_da():
    """(weg, hinweis) -- derselbe Weg wie bei der Predigtaufnahme."""
    return aufnahme.koder_pruefen()


def _befehl(weg):
    """Der Koderaufruf. Schreibt nach stdout, nicht in eine Datei."""
    if weg == "ffmpeg":
        return ["ffmpeg", "-hide_banner", "-loglevel", "error",
                "-f", "s16le", "-ar", str(RATE), "-ac", "1", "-i", "pipe:0",
                "-c:a", "libmp3lame", "-b:a", BITRATE, "-ac", "1",
                # Kein Xing-Kopf, kein ID3: der Strom ist nichts als
                # eine Folge von Rahmen. Wer mittendrin einsteigt,
                # findet den naechsten Rahmen und spielt los.
                # Dieselbe Begruendung wie in aufnahme.py.
                "-write_xing", "0", "-id3v2_version", "0",
                # Ohne Bitreservoir ist jeder Rahmen fuer sich
                # dekodierbar. Das kostet ein wenig Qualitaet bei
                # gleicher Bitrate und spart genau das, worum es hier
                # geht: ein Rahmen muss nicht auf den naechsten
                # warten, und ein spaeter Einsteiger hoert sofort.
                "-reservoir", "0",
                "-flush_packets", "1",
                "-f", "mp3", "pipe:1"]
    return ["lame", "--quiet", "-r", "-s", str(RATE / 1000.0),
            "--bitwidth", "16", "--signed", "--little-endian",
            "-m", "m", "-b", str(int(str(BITRATE).rstrip("k"))),
            "--nores", "-", "-"]


# Wie viel fertiger Strom vorgehalten wird, damit ein neuer Zuhoerer
# sofort einen Puffer hat. Mehr als die groesste erlaubte
# Zielvorgabe, mit etwas Luft.
VORRAT_S = 15.0

# ---------------------------------------------------- MP3-Rahmen
#
# WARUM DER STROM IN RAHMEN ZERLEGT WIRD
#
# Befund vom Galaxy Z Fold 7: der Ton blieb abgehackt, und das
# Tonprotokoll zeigte durchgehend "abstand 0.0". Nachgemessen mit
# curl: sechzig Sekunden Abruf ergeben 59,9 Sekunden Ton -- der
# Server liefert also exakt Echtzeit. Firefox Android faengt ohne
# Vorpuffer an, und bei Lieferung in Echtzeit kann danach nie einer
# entstehen. Jedes Zoegern des WLAN wird damit zu einer Luecke, und
# Aufholen ueber das Tempo baut nur Abstand AB, nie auf.
#
# Also wie Icecast: ein neuer Zuhoerer bekommt zuerst die letzten
# Sekunden auf einen Schlag und danach Echtzeit. Dafuer muessen es
# ganze Rahmen sein -- ein halber Rahmen am Anfang ist fuer jeden
# Abspieler Mull, und mit -reservoir 0 ist jeder fuer sich
# dekodierbar.
_BITRATEN = {3: [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192,
                 224, 256, 320, 0],
             2: [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128,
                 144, 160, 0]}
_RATEN = {3: {0: 44100, 1: 48000, 2: 32000},
          2: {0: 22050, 1: 24000, 2: 16000}}


def rahmen_kopf(daten, pos):
    """(Laenge, Sekunden) eines MP3-Rahmens an pos, oder None."""
    if pos + 4 > len(daten):
        return None
    k = (daten[pos] << 24) | (daten[pos + 1] << 16) \
        | (daten[pos + 2] << 8) | daten[pos + 3]
    if (k >> 21) & 0x7FF != 0x7FF:
        return None
    fassung = (k >> 19) & 0x3
    schicht = (k >> 17) & 0x3
    bi = (k >> 12) & 0xF
    ri = (k >> 10) & 0x3
    polster = (k >> 9) & 0x1
    if schicht != 1 or fassung not in _RATEN or ri > 2 or bi in (0, 15):
        return None
    rate = _RATEN[fassung][ri]
    bitrate = _BITRATEN[fassung][bi]
    werte = 1152 if fassung == 3 else 576
    laenge = int(werte / 8 * bitrate * 1000 / rate) + polster
    if laenge < 8:
        return None
    return laenge, werte / rate


def umrechnen(werte, von, nach=RATE):
    """Abtastrate aendern, mit numpy. Mono, float32 in [-1, 1].

    Lineare Interpolation. Fuer Sprache bei diesen Raten genuegt das:
    der Unterschied zu einem ordentlichen Filter liegt weit unter
    dem, was 48 kbit/s MP3 ohnehin wegwirft. Ein zweites Paket dafuer
    waere eine Abhaengigkeit fuer nichts."""
    if von == nach or len(werte) == 0:
        return werte
    n = int(round(len(werte) * nach / von))
    if n <= 0:
        return np.zeros(0, dtype=np.float32)
    alt = np.arange(len(werte), dtype=np.float64)
    neu = np.linspace(0, len(werte) - 1, n)
    return np.interp(neu, alt, werte).astype(np.float32)


def wav_lesen(pfad):
    """Eine WAV-Datei als float32 mono auf RATE. Leer bei Fehler."""
    try:
        with wave.open(str(pfad), "rb") as w:
            kanaele = w.getnchannels()
            breite = w.getsampwidth()
            rate = w.getframerate()
            roh = w.readframes(w.getnframes())
    except Exception:
        return np.zeros(0, dtype=np.float32)
    if breite != 2:
        return np.zeros(0, dtype=np.float32)
    werte = np.frombuffer(roh, dtype=np.int16).astype(np.float32) / 32768.0
    if kanaele > 1:
        werte = werte.reshape(-1, kanaele).mean(axis=1)
    return umrechnen(werte, rate)


class Koder:
    """Ein Strom fuer eine Sprache."""

    def __init__(self, sprache, weg):
        self.sprache = sprache
        self.weg = weg
        self.zuhoerer = set()          # queue.Queue je Zuhoerer
        self._schloss = threading.Lock()
        self._warteschlange = []       # fertige Abschnitte, float32
        self._wartet_s = 0.0
        self._aus = threading.Event()
        self._leer_seit = None
        self._prozess = None
        self._bytes = 0
        self._seit = time.monotonic()
        # Die letzten Sekunden als ganze Rahmen, fuer den Vorrat
        # beim Verbinden. (bytes, Sekunden) je Rahmen.
        self._vorrat = []
        self._vorrat_s = 0.0
        self._rest = b""

    # ---- hineingeben -------------------------------------------
    def einreihen(self, werte):
        """Einen fertigen Abschnitt anhaengen. Schon auf RATE."""
        if len(werte) == 0:
            return
        with self._schloss:
            self._warteschlange.append(werte)
            self._wartet_s += len(werte) / RATE
            # Rueckstau begrenzen: das AELTESTE faellt weg. Es ist
            # das, was am wenigsten mit dem zu tun hat, was vorn
            # gerade gesagt wird.
            #
            # Das letzte Stueck bleibt immer stehen, auch wenn es
            # allein schon laenger ist als die Grenze. In einen
            # Abschnitt hineinzuschneiden hiesse, mitten im Wort
            # abzubrechen -- schlechter als ein paar Sekunden zu
            # spaet. Im Betrieb kommt der Fall nicht vor: ein
            # Abschnitt ist hoechstens max_dauer lang, also acht
            # Sekunden.
            while self._wartet_s > RUECKSTAU_S and len(self._warteschlange) > 1:
                weg = self._warteschlange.pop(0)
                self._wartet_s -= len(weg) / RATE

    def _naechster_block(self):
        """Ein Block PCM. Stille, wenn nichts wartet."""
        with self._schloss:
            aus = np.zeros(BLOCK, dtype=np.float32)
            gefuellt = 0
            while gefuellt < BLOCK and self._warteschlange:
                stueck = self._warteschlange[0]
                nimm = min(BLOCK - gefuellt, len(stueck))
                aus[gefuellt:gefuellt + nimm] = stueck[:nimm]
                gefuellt += nimm
                if nimm >= len(stueck):
                    self._warteschlange.pop(0)
                else:
                    self._warteschlange[0] = stueck[nimm:]
                self._wartet_s = max(0.0, self._wartet_s - nimm / RATE)
            return aus

    # ---- zuhoeren ----------------------------------------------
    def vorrat(self, sekunden):
        """Die letzten N Sekunden als ganze Rahmen, am Stueck.

        Von hinten gesammelt: der Zuhoerer soll die juengsten
        Sekunden bekommen, nicht die aeltesten."""
        if sekunden <= 0:
            return b""
        with self._schloss:
            teile, summe = [], 0.0
            for roh, dauer in reversed(self._vorrat):
                teile.append(roh)
                summe += dauer
                if summe >= sekunden:
                    break
            return b"".join(reversed(teile))

    def anmelden(self, ziel=0.0):
        q = queue.Queue(maxsize=ZUHOERER_PUFFER)
        # DER VORRAT ZUERST, und zwar als EIN Stueck: als hundert
        # einzelne Rahmen liefe die Warteschlange ueber, bevor der
        # Zuhoerer das erste abgeholt hat.
        anfang = self.vorrat(ziel)
        if anfang:
            try:
                q.put_nowait(anfang)
            except queue.Full:
                pass
        with self._schloss:
            self.zuhoerer.add(q)
            self._leer_seit = None
        return q

    def abmelden(self, q):
        with self._schloss:
            self.zuhoerer.discard(q)
            if not self.zuhoerer:
                self._leer_seit = time.monotonic()

    def _streuen(self, brocken):
        with self._schloss:
            tot = []
            for q in self.zuhoerer:
                try:
                    q.put_nowait(brocken)
                except queue.Full:
                    tot.append(q)
            for q in tot:
                self.zuhoerer.discard(q)
                try:
                    q.put_nowait(None)      # Schlusszeichen
                except queue.Full:
                    pass

    # ---- Faeden ------------------------------------------------
    def starten(self):
        self._prozess = subprocess.Popen(
            _befehl(self.weg), stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        threading.Thread(target=self._fuettern, daemon=True).start()
        threading.Thread(target=self._lesen, daemon=True).start()

    def _fuettern(self):
        """Schiebt PCM im Echtzeittakt in den Koder."""
        beginn = time.monotonic()
        n = 0
        ein = self._prozess.stdin
        while not self._aus.is_set():
            block = self._naechster_block()
            roh = (np.clip(block, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
            try:
                ein.write(roh)
                ein.flush()
            except Exception:
                break
            n += 1
            # Absolute Zeitbasis: der Fehler von sleep summiert sich
            # sonst ueber eine Dreiviertelstunde auf Minuten.
            soll = beginn + n * BLOCK / RATE
            warte = soll - time.monotonic()
            if warte > 0:
                time.sleep(warte)
        try:
            ein.close()
        except Exception:
            pass

    def _lesen(self):
        """Liest den Koder, zerlegt in ganze Rahmen und verteilt.

        Frueher gingen rohe 1024-Byte-Stuecke hinaus. Das genuegte,
        solange jeder von Anfang an zuhoerte. Fuer den Vorrat beim
        Verbinden muessen es ganze Rahmen sein: ein halber Rahmen am
        Anfang ist fuer jeden Abspieler Mull.

        Weitergegeben wird weiter in Stuecken von rund 1024 Byte --
        nur eben an Rahmengrenzen. Ein Stueck je Rahmen waere das
        Sechsfache an Warteschlangeneintraegen fuer dieselbe Menge
        Ton."""
        aus = self._prozess.stdout
        puffer = b""
        paket, paket_bytes = [], 0
        while not self._aus.is_set():
            roh = aus.read(BROCKEN)
            if not roh:
                break
            self._bytes += len(roh)
            puffer += roh
            # Auf den naechsten Rahmenkopf aufsetzen.
            pos = 0
            while True:
                kopf = rahmen_kopf(puffer, pos)
                if kopf is None:
                    # Kein Kopf hier: ein Byte weiter suchen, aber
                    # nur solange noch etwas da ist.
                    if pos + 4 <= len(puffer):
                        pos += 1
                        continue
                    break
                laenge, dauer = kopf
                if pos + laenge > len(puffer):
                    break
                rahmen = puffer[pos:pos + laenge]
                pos += laenge
                with self._schloss:
                    self._vorrat.append((rahmen, dauer))
                    self._vorrat_s += dauer
                    while self._vorrat_s > VORRAT_S and self._vorrat:
                        _, d = self._vorrat.pop(0)
                        self._vorrat_s -= d
                paket.append(rahmen)
                paket_bytes += laenge
                if paket_bytes >= BROCKEN:
                    self._streuen(b"".join(paket))
                    paket, paket_bytes = [], 0
            puffer = puffer[pos:]
        if paket:
            self._streuen(b"".join(paket))
        self._streuen(None)

    def anhalten(self):
        self._aus.set()
        p = self._prozess
        if p is None:
            return
        try:
            if p.stdin:
                p.stdin.close()
        except Exception:
            pass
        try:
            p.terminate()
            p.wait(timeout=3)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass

    def leer_seit(self):
        with self._schloss:
            return self._leer_seit

    def lage(self):
        with self._schloss:
            return {"sprache": self.sprache, "zuhoerer": len(self.zuhoerer),
                    "wartet_s": round(self._wartet_s, 2),
                    "bytes": self._bytes,
                    "vorrat_s": round(self._vorrat_s, 2),
                    "laeuft_s": round(time.monotonic() - self._seit, 1)}


class Stroeme:
    """Alle Koder. Einer je Sprache, nur solange jemand zuhoert."""

    def __init__(self):
        self.koder = {}
        self._schloss = threading.Lock()
        self._weg, self._hinweis = koder_da()
        self._aufraeumer = None
        self._aus = threading.Event()

    @property
    def moeglich(self):
        return bool(self._weg)

    @property
    def hinweis(self):
        return self._hinweis

    def _aufraeumen(self):
        while not self._aus.wait(2.0):
            jetzt = time.monotonic()
            with self._schloss:
                weg = [sp for sp, k in self.koder.items()
                       if k.leer_seit() and jetzt - k.leer_seit() > NACHLAUF_S]
                fertig = [self.koder.pop(sp) for sp in weg]
            for k in fertig:
                k.anhalten()

    def anmelden(self, sprache, ziel=0.0):
        """Gibt (koder, warteschlange) oder (None, None).

        ziel ist der Vorrat in Sekunden, den dieser eine Zuhoerer
        beim Verbinden auf einen Schlag bekommt. Zwei Zuhoerer
        derselben Sprache duerfen verschiedene Ziele haben -- der
        Koder ist derselbe, nur ihr Anfang ist verschieden."""
        if not self._weg:
            return None, None
        with self._schloss:
            k = self.koder.get(sprache)
            neu_angelegt = k is None
            if neu_angelegt:
                k = Koder(sprache, self._weg)
                self.koder[sprache] = k
                k.starten()
            if self._aufraeumer is None:
                self._aus.clear()
                self._aufraeumer = threading.Thread(target=self._aufraeumen,
                                                    daemon=True)
                self._aufraeumer.start()
        return k, k.anmelden(0.0 if neu_angelegt else ziel)

    def abmelden(self, sprache, q):
        with self._schloss:
            k = self.koder.get(sprache)
        if k is not None:
            k.abmelden(q)

    def einreihen(self, sprache, pfad):
        """Einen fertigen Abschnitt in den Strom legen, falls er laeuft.

        Laeuft kein Koder, passiert nichts -- dann hoert niemand ueber
        den Strom zu, und die Datei zu lesen waere Arbeit fuer
        niemanden."""
        with self._schloss:
            k = self.koder.get(sprache)
        if k is None:
            return
        werte = wav_lesen(pfad)
        if len(werte):
            k.einreihen(werte)

    def lage(self):
        with self._schloss:
            return [k.lage() for k in self.koder.values()]

    def alles_anhalten(self):
        self._aus.set()
        with self._schloss:
            alle = list(self.koder.values())
            self.koder.clear()
        for k in alle:
            k.anhalten()


if __name__ == "__main__":
    import sys
    weg, hinweis = koder_da()
    print("Koder:", weg or f"keiner ({hinweis})")
    if "--probe" in sys.argv and weg:
        s = Stroeme()
        k, q = s.anmelden("de")
        gesamt, t0 = 0, time.monotonic()
        while time.monotonic() - t0 < 10:
            b = q.get()
            if b is None:
                break
            gesamt += len(b)
        print(f"{gesamt} Byte in 10 s "
              f"= {gesamt * 8 / 10 / 1000:.0f} kbit/s")
        print("Lage:", k.lage())
        s.alles_anhalten()
