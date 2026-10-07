#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ukrainisch auf ukrainian_tts mit Sprecher mykyta -- vorbereitet, nicht
umgestellt (Nachtrag zu 0.5.0).

    .venv/bin/python pruefstand/sprecherwahl_test.py

  * Fuer jede ausgelieferte Stimme aendert sich nichts: kein Sprecher
    gewaehlt (Piper nimmt 0 wie bisher), kein Zeichen umgeschrieben.
  * ukrainian_tts kennt nur Kleinbuchstaben; Piper liess jeden
    Grossbuchstaben still weg. zeichen_angleichen schreibt ihn klein --
    nur fuer Stimmen, die Zeichen statt Laute lesen und den Buchstaben
    sonst nicht haetten.
  * Die Umstellung ist EINE Zeile in config.py: danach spricht
    ukrainian_tts mit Sprecher mykyta und dem Tempo, das fuer ihn
    gemessen ist.

Liegt eine Stimme nicht auf der Platte, wird der Teil uebersprungen
und das gesagt.
"""
import logging
import re
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))
import config  # noqa: E402
import server  # noqa: E402

ROT, GRUEN, AUS = "\033[31m", "\033[32m", "\033[0m"
FEHLER = 0
uebersprungen = []
warnungen = []
ALT = "uk_UA-ukrainian_tts-medium"
SAETZE = [
    "Перед Вечерею Господньою ми звершуємо обряд обмивання ніг.",
    "Наступної суботи троє молодих людей приймуть хрещення через занурення.",
    "Ми дякуємо Богові за Його благодать і за всіх, хто сьогодні прийшов.",
]


class _Fang(logging.Handler):
    def emit(self, r):
        warnungen.append(r.getMessage())


logging.getLogger().addHandler(_Fang())


def pruefe(was, erwartet, ist):
    global FEHLER
    if erwartet == ist:
        print(f"   ok    {was}")
    else:
        print(f"   {ROT}FEHL{AUS}  {was}: erwartet {erwartet!r}, ist {ist!r}")
        FEHLER += 1


def titel(t):
    print(f"\n\033[1m== {t}\033[0m")


def werk(sprache, name):
    w = server.Werk.__new__(server.Werk)
    w.stimmennamen = {sprache: name}
    return w


def liegt(name):
    return (WURZEL / "voices" / f"{name}.onnx").exists()


titel("1) Ausgelieferte Stimmen: alles wie bisher")
probe = "Ɛyɛ Ɔdɔ Наступної Ми Богові The Lord Der Herr G. Ñ É"
for sp, pfad in sorted(config.STIMMEN.items()):
    if not pfad:
        continue
    name = pfad.split("/")[-1]
    pruefe(f"{sp}: kein Sprecher gewaehlt ({name})", None,
           werk(sp, name).sprecher_fuer(sp))
    if liegt(name):
        pruefe(f"{sp}: kein Zeichen umgeschrieben", probe,
               server.zeichen_angleichen(name, probe))
    else:
        uebersprungen.append(name)
pruefe("STIMM_SPRECHER nennt nur die alte ukrainische Stimme", [ALT],
       list(config.STIMM_SPRECHER))
pruefe("und die ist heute nicht eingestellt", False,
       config.STIMMEN["uk"].endswith(ALT))

titel("2) Die alte Stimme: Sprecher mykyta, Kleinbuchstaben")
if liegt(ALT):
    w = werk("uk", ALT)
    pruefe("Sprecher mykyta ist Nummer 1", 1, w.sprecher_fuer("uk"))
    pruefe("Grossbuchstaben werden klein",
           "наступної суботи. ми дякуємо богові.",
           server.zeichen_angleichen(ALT, "Наступної суботи. Ми дякуємо Богові."))
    pruefe("Satzzeichen bleiben", "«так», — ні!",
           server.zeichen_angleichen(ALT, "«Так», — ні!"))
    from piper import PiperVoice, SynthesisConfig
    import io
    import wave
    stimme = PiperVoice.load(str(WURZEL / "voices" / f"{ALT}.onnx"))
    for satz in SAETZE:
        warnungen.clear()
        with wave.open(io.BytesIO(), "wb") as ziel:
            stimme.synthesize_wav(server.zeichen_angleichen(ALT, satz), ziel,
                                  syn_config=SynthesisConfig(speaker_id=1))
        pruefe(f"nichts verschluckt: {satz[:30]}…", [],
               [m for m in warnungen if "Missing phoneme" in m])
    # Gegenprobe: ohne Angleichung fehlt etwas -- sonst prueft der Fall
    # nichts.
    warnungen.clear()
    with wave.open(io.BytesIO(), "wb") as ziel:
        stimme.synthesize_wav(SAETZE[1], ziel,
                              syn_config=SynthesisConfig(speaker_id=1))
    pruefe("Gegenprobe: ohne Angleichung fehlt das Н", True,
           any("Н" in m for m in warnungen))
else:
    uebersprungen.append(ALT)

titel("3) Die Umstellung ist eine Zeile")
quelle = (WURZEL / "config.py").read_text(encoding="utf-8")
neu = '"uk": "uk/uk_UA/ukrainian_tts/medium/uk_UA-ukrainian_tts-medium",'
pruefe("die Zeile steht als Kommentar bereit", True, f"#   {neu}" in quelle)
pruefe("die geltende Zeile gibt es genau einmal", 1,
       len(re.findall(r'^\s*"uk": "uk/uk_UA/mykyta/high/uk_UA-mykyta-high",$',
                      quelle, re.M)))
vorher = dict(config.STIMMEN)
try:
    config.STIMMEN["uk"] = "uk/uk_UA/ukrainian_tts/medium/" + ALT
    w = werk("uk", ALT)
    pruefe("danach: Sprecher mykyta", 1 if liegt(ALT) else None,
           w.sprecher_fuer("uk"))
    pruefe("danach: das Tempo fuer mykyta, nicht das fuer lada",
           round(min(config.TEMPO_MAX,
                     1.50 * config.TEMPO_AUFSCHLAG * config.TEMPO_GLOBAL), 3),
           round(w.tempo_fuer("uk"), 3))
    if liegt(ALT):
        pruefe("danach findet der Server die Datei", True,
               "uk" in server.stimmen_finden(["uk"], quelle="de"))
finally:
    config.STIMMEN.clear()
    config.STIMMEN.update(vorher)

print()
if uebersprungen:
    print(f"Uebersprungen (Stimme fehlt): {', '.join(uebersprungen)}")
if FEHLER:
    print(f"{ROT}{FEHLER} Fehler.{AUS}")
    sys.exit(1)
print(f"{GRUEN}Alle Faelle wie erwartet.{AUS}")
