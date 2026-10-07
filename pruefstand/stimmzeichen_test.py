#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kommen die Sonderzeichen einer Sprache unversehrt bei der Stimme an?

    .venv/bin/python pruefstand/stimmzeichen_test.py

Ukrainisch (seit 0.5.0 uk_UA-mykyta-high): і, ї, є und ґ muessen
anders klingen als и, і, е und г -- sonst sagt die Stimme ein anderes
Wort. Der Apostroph trennt ("м'ясо" ist [mj], nicht [mʲ]); ihn gibt es
in drei Schreibungen (' U+0027, ʼ U+02BC, ’ U+2019), und das
Sprachmodell nimmt mal die eine, mal die andere. Alle drei muessen
dasselbe ergeben.

Geprueft wird an den Phonemen, die Piper aus dem Text macht -- also
genau an der Stelle, an der ein Zeichen lautlos verloren ginge. Piper
meldet ein unbekanntes Zeichen nur als Warnung im Log und laesst es
weg; darum zaehlt hier auch jede Warnung als Fehler.

Liegt die Stimme nicht auf der Platte (frischer Klon), wird der Teil
uebersprungen und das gesagt -- nicht still bestanden.
"""
import logging
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))
import config  # noqa: E402

fehler = 0
uebersprungen = []
warnungen = []


class _Fang(logging.Handler):
    def emit(self, r):
        warnungen.append(r.getMessage())


logging.getLogger().addHandler(_Fang())


def pruefe(was, erwartet, ist):
    global fehler
    if erwartet == ist:
        print(f"   ok    {was}")
    else:
        fehler += 1
        print(f"   FEHLER {was}: erwartet {erwartet!r}, ist {ist!r}")


def titel(t):
    print(f"\n\033[1m== {t}\033[0m")


def stimme(sprache):
    pfad = config.STIMMEN.get(sprache, "")
    if not pfad:
        return None
    datei = WURZEL / "voices" / (Path(pfad).name + ".onnx")
    if not (datei.exists() and Path(str(datei) + ".json").exists()):
        uebersprungen.append(f"{sprache}: {datei.name} liegt nicht da")
        return None
    from piper import PiperVoice
    return PiperVoice.load(str(datei))


def phoneme(v, text):
    return "".join("".join(s) for s in v.phonemize(text))


titel("1) Ukrainisch: і ї є ґ und der Apostroph")
pruefe("uk spricht mykyta", "uk_UA-mykyta-high",
       Path(config.STIMMEN["uk"]).name)
v = stimme("uk")
if v is not None:
    for mit, ohne, was in (("кіт", "кит", "і ist nicht и"),
                           ("їжак", "іжак", "ї ist [ji], nicht [i]"),
                           ("Європа", "Европа", "є ist [jɛ], nicht [ɛ]"),
                           ("ґанок", "ганок", "ґ ist [ɡ], nicht [h]")):
        pruefe(f"{was}: {mit} / {ohne}", True,
               phoneme(v, mit) != phoneme(v, ohne))
    pruefe("ґ wird [ɡ]", True, "ɡ" in phoneme(v, "ґанок"))
    gerade = phoneme(v, "м'ясо")
    pruefe("Apostroph ' trennt: м'ясо hat [mj]", True, "mj" in gerade)
    pruefe("Apostroph ʼ (U+02BC) gleich wie '", gerade, phoneme(v, "мʼясо"))
    pruefe("Apostroph ’ (U+2019) gleich wie '", gerade, phoneme(v, "м’ясо"))
    pruefe("auch im Wortinnern: сім'ї", True, "mj" in phoneme(v, "сім'ї"))
    # Ein Satz mit allem auf einmal, so wie er aus der Uebersetzung kommt.
    satz = ("Їжак з'їв ґрунт біля сім'ї, і Європа знає про це. "
            "Ми дякуємо Богові за Його благодать.")
    pruefe("ein ganzer Satz ergibt Phoneme", True, len(phoneme(v, satz)) > 60)
    pruefe("Piper hat kein Zeichen verworfen", [], list(warnungen))

titel("2) Twi: ɛ ɔ Ɛ Ɔ -- von der Uebersetzung bis zur Stimme")
import re  # noqa: E402

# Ein Satz, wie ihn das Sprachmodell liefert: Grossbuchstaben am
# Satzanfang, typografische Anfuehrungszeichen, eine Bibelstelle.
satz = "Ɛnnɛ yɛkenkan Dwom 23:1 sɛ: “Awurade ne me hwɛfo.” Ɔdɔ nni awiei."


def sprechform(text, sprache):
    for muster, ersatz in config.SPRECHFORM.get(sprache, ()):
        text = re.sub(muster, ersatz, text)
    return text


gesprochen = sprechform(satz, "tw")
for zeichen in "ɛɔƐƆ":
    pruefe(f"Sprechform laesst {zeichen} stehen",
           satz.count(zeichen), gesprochen.count(zeichen))
pruefe("Sprechform nimmt Ziffern und “” heraus", False,
       bool(re.search(r"[0-9“”]", gesprochen)))
pruefe("Sprechform hinterlaesst keinen doppelten Leerraum", False,
       "  " in gesprochen or gesprochen != gesprochen.strip())
# Der Untertitel bekommt den Text unveraendert -- die Sprechform wirkt
# nur vor Piper (server.Werk.sprechen).
import json  # noqa: E402
pruefe("ɛ und ɔ ueberstehen den Weg als JSON zum Handy", satz,
       json.loads(json.dumps({"t": satz}, ensure_ascii=False))["t"])
v = stimme("tw")
if v is not None:
    warnungen.clear()

    def ids(text):
        return v.phonemes_to_ids(v.phonemize(text)[0])

    pruefe("Ɛ hat dieselbe Nummer wie ɛ", ids("ɛ"), ids("Ɛ"))
    pruefe("Ɔ hat dieselbe Nummer wie ɔ", ids("ɔ"), ids("Ɔ"))
    pruefe("ɛ ist nicht e", True, ids("ɛ") != ids("e"))
    pruefe("ɔ ist nicht o", True, ids("ɔ") != ids("o"))
    pruefe("nach der Sprechform verwirft Piper kein Zeichen", [],
           (ids(gesprochen), list(warnungen))[1])
    pruefe("und keine Nummer fehlt: so viele Zeichen wie IDs", 2 * len(
        __import__("unicodedata").normalize("NFD", gesprochen)) + 1,
        len(ids(gesprochen)))

print()
for u in uebersprungen:
    print(f"   UEBERSPRUNGEN  {u}")
if fehler:
    print(f"\033[31m{fehler} Fehler.\033[0m")
    sys.exit(1)
print("\033[32mAlle Faelle wie erwartet.\033[0m")
