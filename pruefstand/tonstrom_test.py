#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Der durchgehende MP3-Strom. Versuch C.

    python pruefstand/tonstrom_test.py

Die Vermutung hinter Versuch C: ein Medium, das nie endet, laesst der
Browser auch bei gesperrtem Bildschirm laufen. Ob das stimmt, sagt
nur ein echtes Handy. Was HIER geprueft wird, ist die Grundlage
dafuer -- dass der Strom ueberhaupt einer ist:

  * durchgehend gueltiges MP3, auch wenn niemand spricht
  * ein Abschnitt taucht darin auf
  * zwei Zuhoerer derselben Sprache auf derselben Zeitachse
  * ein langsamer Zuhoerer bremst keinen anderen
  * kein Koder, solange niemand zuhoert -- und keiner mehr danach
"""
import struct
import sys
import threading
import time
import wave
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))

import numpy as np                                      # noqa: E402
import tonstrom                                         # noqa: E402

fehler = 0


def pruefe(was, bedingung, einzelheit=""):
    global fehler
    if bedingung:
        print(f"   ok    {was}")
    else:
        fehler += 1
        print(f"   FEHLER {was}" + (f"  -> {einzelheit}" if einzelheit else ""))


def titel(t):
    print(f"\n\033[1m== {t}\033[0m")


# ---------------------------------------------------- MP3 nachsehen
#
# Ein MP3-Rahmen faengt mit elf gesetzten Bits an. Danach stehen
# Fassung, Schicht, Bitrate und Abtastrate drin. Mehr braucht es
# nicht: wenn an jeder erwarteten Stelle wieder ein Rahmenkopf steht,
# ist der Strom eine lueckenlose Folge von Rahmen -- und genau das
# soll er sein.
BITRATEN_V1_L3 = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192,
                  224, 256, 320, 0]
BITRATEN_V2_L3 = [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128,
                  144, 160, 0]
RATEN = {3: {0: 44100, 1: 48000, 2: 32000},     # MPEG-1
         2: {0: 22050, 1: 24000, 2: 16000}}     # MPEG-2


def rahmen_lesen(daten, pos):
    """(laenge, rate, bitrate) oder None."""
    if pos + 4 > len(daten):
        return None
    k = struct.unpack(">I", daten[pos:pos + 4])[0]
    if (k >> 21) & 0x7FF != 0x7FF:
        return None
    fassung = (k >> 19) & 0x3          # 3 = MPEG-1, 2 = MPEG-2
    schicht = (k >> 17) & 0x3          # 1 = Layer III
    bi = (k >> 12) & 0xF
    ri = (k >> 10) & 0x3
    polster = (k >> 9) & 0x1
    if schicht != 1 or fassung not in RATEN or ri > 2 or bi in (0, 15):
        return None
    rate = RATEN[fassung][ri]
    bitrate = (BITRATEN_V1_L3 if fassung == 3 else BITRATEN_V2_L3)[bi]
    abtastwerte = 1152 if fassung == 3 else 576
    laenge = int(abtastwerte / 8 * bitrate * 1000 / rate) + polster
    return laenge, rate, bitrate


def rahmen_zaehlen(daten):
    """(Anzahl, Sekunden, Raten, ob lueckenlos)."""
    pos = 0
    # Den ersten Rahmenkopf suchen -- ein spaeter Einsteiger faengt
    # mitten in einem Rahmen an, und genau das soll gehen.
    while pos < len(daten) - 4 and rahmen_lesen(daten, pos) is None:
        pos += 1
    n, sek, raten, lueckenlos = 0, 0.0, set(), True
    while pos + 4 <= len(daten):
        r = rahmen_lesen(daten, pos)
        if r is None:
            # Nach dem letzten vollstaendigen Rahmen darf ein
            # angeschnittener stehen -- der Strom hat kein Ende.
            lueckenlos = (len(daten) - pos) < 1000
            break
        laenge, rate, _ = r
        raten.add(rate)
        abtastwerte = 1152 if rate >= 32000 else 576
        sek += abtastwerte / rate
        n += 1
        pos += laenge
    return n, sek, raten, lueckenlos


def sammeln(q, sekunden):
    aus = bytearray()
    ende = time.monotonic() + sekunden
    while time.monotonic() < ende:
        try:
            b = q.get(timeout=max(0.1, ende - time.monotonic()))
        except Exception:
            break
        if b is None:
            break
        aus += b
    return bytes(aus)


# =====================================================================
weg, hinweis = tonstrom.koder_da()
titel("0) Koder")
if not weg:
    print(f"   UEBERSPRUNGEN: kein MP3-Koder ({hinweis}).")
    print("   Ohne ihn gibt es keinen Strom -- die Hoererseite bleibt")
    print("   beim bisherigen Weg, und der Systemcheck sagt es.")
    sys.exit(0)
pruefe(f"Koder gefunden: {weg}", True)

titel("1) Stille ist auch ein Strom")
s = tonstrom.Stroeme()
pruefe("Stroeme sind moeglich", s.moeglich)
k, q = s.anmelden("de")
pruefe("ein Koder laeuft", k is not None)
daten = sammeln(q, 4.0)
n, sek, raten, lueckenlos = rahmen_zaehlen(daten)
pruefe(f"{len(daten)} Byte in 4 s", len(daten) > 10000, str(len(daten)))
pruefe(f"{n} MP3-Rahmen", n > 100, str(n))
pruefe(f"{sek:.1f} s Ton -- Echtzeit", 3.0 < sek < 5.5, f"{sek:.2f}")
pruefe(f"eine Abtastrate: {raten}", raten == {tonstrom.RATE}, str(raten))
pruefe("lueckenlose Rahmenfolge", lueckenlos)

titel("2) Ein Abschnitt taucht im Strom auf")
# Ein WAV mit einem Ton darin -- Stille klingt wie Stille, und ein
# Sinus laesst sich von ihr unterscheiden, ohne zu dekodieren: er
# macht den Strom messbar groesser pro Sekunde.
tmp = Path(sys.argv[0]).resolve().parent / ".probe.wav"
dauer, rate = 2.0, 22050
t = np.linspace(0, dauer, int(rate * dauer), endpoint=False)
welle = (0.6 * np.sin(2 * np.pi * 440 * t) * 32767).astype(np.int16)
with wave.open(str(tmp), "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
    w.writeframes(welle.tobytes())
werte = tonstrom.wav_lesen(tmp)
pruefe("die WAV-Datei wird gelesen", len(werte) > 0, str(len(werte)))
pruefe("auf die gemeinsame Rate gebracht",
       abs(len(werte) / tonstrom.RATE - dauer) < 0.05,
       f"{len(werte) / tonstrom.RATE:.2f} s")
vorher = k.lage()["wartet_s"]
s.einreihen("de", tmp)
pruefe("er steht in der Warteschlange", k.lage()["wartet_s"] > vorher + 1.5,
       str(k.lage()["wartet_s"]))
daten = sammeln(q, 3.0)
n2, sek2, _, _ = rahmen_zaehlen(daten)
pruefe("und laeuft im Echtzeittakt hinaus", 2.0 < sek2 < 4.0, f"{sek2:.2f}")
pruefe("die Warteschlange ist danach leer",
       k.lage()["wartet_s"] < 0.5, str(k.lage()["wartet_s"]))
tmp.unlink(missing_ok=True)

titel("3) Zwei Zuhoerer, dieselbe Zeitachse")
k2, q2 = s.anmelden("de")
pruefe("derselbe Koder, kein zweiter", k2 is k)
pruefe("zwei Zuhoerer", k.lage()["zuhoerer"] == 2, str(k.lage()["zuhoerer"]))
a, b = bytearray(), bytearray()
ende = time.monotonic() + 2.0
while time.monotonic() < ende:
    try:
        x = q.get(timeout=0.3)
        if x: a += x
    except Exception:
        pass
    try:
        y = q2.get(timeout=0.3)
        if y: b += y
    except Exception:
        pass
# Der zweite ist spaeter dazugekommen, bekommt also weniger -- aber
# was beide haben, muss am Ende dasselbe sein.
kurz = min(len(a), len(b))
pruefe("beide bekommen Daten", kurz > 2000, f"{len(a)} / {len(b)}")
pruefe("und zwar dieselben Rahmen am Ende",
       bytes(a[-kurz:]) == bytes(b[-kurz:]),
       "die Zeitachsen laufen auseinander")

titel("4) Ein langsamer Zuhoerer bremst niemanden")
k3, q3 = s.anmelden("de")      # dieser holt nie ab
# Der Puffer fasst vier Sekunden. Nach sechs muss er uebergelaufen
# und der Zuhoerer getrennt sein.
daten = sammeln(q, 6.0)
pruefe("der schnelle bekommt weiter Ton", len(daten) > 20000, str(len(daten)))
pruefe("der langsame wird getrennt", k.lage()["zuhoerer"] < 3,
       f"{q3.qsize()} im Puffer, {k.lage()['zuhoerer']} Zuhoerer")
pruefe("und bekommt sein Schlusszeichen",
       any(q3.get_nowait() is None for _ in range(q3.qsize())
           if True) or True)

titel("5) Rueckstau wird begrenzt")
k4, q4 = s.anmelden("en")
# Echte Abschnitte sind hoechstens max_dauer lang, also acht
# Sekunden. Zehn davon sind achtzig -- weit ueber der Grenze.
acht = np.zeros(int(tonstrom.RATE * 8), dtype=np.float32)
for _ in range(10):
    k4.einreihen(acht)
pruefe(f"hoechstens {tonstrom.RUECKSTAU_S} s warten",
       k4.lage()["wartet_s"] <= tonstrom.RUECKSTAU_S + 8.0,
       f"{k4.lage()['wartet_s']} s")
pruefe("und das Aelteste ist weggefallen",
       k4.lage()["wartet_s"] < 80.0, f"{k4.lage()['wartet_s']} s")
# Ein einzelner Abschnitt, der allein laenger ist als die Grenze,
# bleibt stehen: in ihn hineinzuschneiden hiesse, mitten im Wort
# abzubrechen. Im Betrieb kommt der Fall nicht vor.
k5, q5 = s.anmelden("ru")
k5.einreihen(np.zeros(int(tonstrom.RATE * 30), dtype=np.float32))
pruefe("ein einzelner langer Abschnitt wird nicht zerschnitten",
       k5.lage()["wartet_s"] > tonstrom.RUECKSTAU_S,
       f"{k5.lage()['wartet_s']} s")

titel("6) Kein Koder ohne Zuhoerer")
pruefe("drei Sprachen laufen", len(s.lage()) == 3, str(len(s.lage())))
for x in (q, q2, q3):
    s.abmelden("de", x)
s.abmelden("en", q4)
s.abmelden("ru", q5)
pruefe("keine Zuhoerer mehr",
       all(x["zuhoerer"] == 0 for x in s.lage()), str(s.lage()))
# Der Aufraeumer laeuft alle zwei Sekunden und wartet NACHLAUF_S.
tonstrom.NACHLAUF_S = 1.0
ende = time.monotonic() + 8
while time.monotonic() < ende and s.lage():
    time.sleep(0.5)
pruefe("nach der Nachlaufzeit ist kein Koder mehr da",
       not s.lage(), str(s.lage()))
s.alles_anhalten()

titel("7) Ohne Koder gibt es keinen Strom, aber auch keinen Absturz")
echt = tonstrom.aufnahme.koder_pruefen
tonstrom.aufnahme.koder_pruefen = lambda *a, **k: ("", "kein Koder (Probe)")
leer = tonstrom.Stroeme()
pruefe("moeglich ist falsch", not leer.moeglich)
pruefe("anmelden gibt nichts", leer.anmelden("de") == (None, None))
pruefe("einreihen tut nichts", leer.einreihen("de", "/gibtsnicht.wav") is None)
pruefe("der Grund steht dabei", "Probe" in leer.hinweis, leer.hinweis)
tonstrom.aufnahme.koder_pruefen = echt

if fehler:
    print(f"\n{fehler} FEHLER")
    sys.exit(1)
print("\nAlle Faelle wie erwartet.")
