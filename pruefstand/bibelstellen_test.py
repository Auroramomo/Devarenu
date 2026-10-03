#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Erkennt das Pult die Bibelstellen, die jemand wirklich tippt?

    python pruefstand/bibelstellen_test.py

WAS BIS 0.3.8 SCHIEFLIEF

Das Muster erlaubte Punkte und Leerzeichen an beliebiger Stelle, das
Nachschlagen danach nicht: in der Tabelle stand `1.korinther` und
`1kor`, gesucht wurde `1.kor`. Acht gängige Schreibweisen gingen so
verloren -- und weil das Muster trotzdem traf, wurde die Stelle aus dem
Thema-Text GELÖSCHT. Der Techniker tippte „1. Kor 13", und übrig blieb
ein Thema ohne Stelle, ohne Namen und ohne Hinweis darauf, dass etwas
fehlt.

Dazu zwei Fehler in der anderen Richtung: „Zum zweiten Mal 2 Lesungen"
ergab Maleachi 2, und „Offenbarung des Johannes 14" ergab Johannes 14 --
das falsche Buch.

Dieser Lauf hält jeden einzelnen Fall fest.
"""

import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))

import config                                   # noqa: E402
import bibelstellen as b                        # noqa: E402

GRUEN, ROT, AUS = "\033[32m", "\033[31m", "\033[0m"
FEHLER = 0


def pruefe(was, erwartet, ist):
    global FEHLER
    if erwartet == ist:
        print(f"   ok    {was}")
    else:
        print(f"   {ROT}FEHL{AUS}  {was}: erwartet {erwartet!r}, ist {ist!r}")
        FEHLER += 1


def titel(t):
    print(f"\n\033[1m== {t}\033[0m")


def stelle(text, erwartet):
    pruefe(f"{text!r}", erwartet, b.stellen_finden(text))


titel("1) Die Schreibweisen, die bis 0.3.8 verlorengingen")

# Alle acht aus der Fehlermeldung, Fall für Fall.
stelle("1. Kor 13", ["1. Korinther 13"])
stelle("1. Joh 4,8", ["1. Johannes 4"])
stelle("2. Tim 3,16", ["2. Timotheus 3"])
stelle("1. Sam 15", ["1. Samuel 15"])
stelle("1 Mose 1", ["1. Mose 1"])
stelle("1 Könige 18", ["1. Könige 18"])
stelle("1 Korinther 13", ["1. Korinther 13"])
stelle("5 Mose 6", ["5. Mose 6"])

titel("2) Was neu dazukommt")

stelle("Johannes Kapitel 3 Vers 16", ["Johannes 3"])
stelle("Römerbrief 8", ["Römer 8"])
stelle("Lukasevangelium 15", ["Lukas 15"])
stelle("Johannesevangelium 3", ["Johannes 3"])
# Umlaute als ae/oe/ue -- am Pult tippt nicht jeder Umlaute.
stelle("Roemer 8", ["Römer 8"])
stelle("Matthaeus 24", ["Matthäus 24"])
stelle("Hebraeer 4", ["Hebräer 4"])
# Das falsche Buch war hier der Fehler, nicht das fehlende.
stelle("Offenbarung des Johannes 14", ["Offenbarung 14"])

titel("3) Was NICHT als Stelle gelten darf")

# Kurze Abkürzungen, die gewöhnliche Wörter sind: nur mit Punkt oder
# mit Versangabe.
stelle("Zum zweiten Mal 2 Lesungen", [])
stelle("Wir treffen uns am 3. Oktober", [])
stelle("Mal. 2", ["Maleachi 2"])
stelle("Mal 2,3", ["Maleachi 2"])
stelle("Maleachi 3,23", ["Maleachi 3"])

titel("4) Und was vorher schon ging, geht weiter")

stelle("Matthäus 18", ["Matthäus 18"])
stelle("Psalm 23", ["Psalmen 23"])
stelle("1Chr 21", ["1. Chronik 21"])
stelle("Mt 5,3-12", ["Matthäus 5"])
stelle("Nehemia 1-4", ["Nehemia 1", "Nehemia 2", "Nehemia 3", "Nehemia 4"])
stelle("Dan 7", ["Daniel 7"])
stelle("Gal 5", ["Galater 5"])
# Englisch, für einen englischsprachigen Prediger.
stelle("1 Corinthians 13", ["1. Korinther 13"])

titel("5) Die Grundregel: was nicht erkannt wird, bleibt stehen")

index = b.Namensindex.laden(WURZEL / "namen_block_b.csv")


def thema(text):
    return b.aus_pulttext(text, index, config.PROMPT_EINLEITUNG,
                          config.PROMPT_MAX_ZEICHEN)


e = thema("Predigt über Vergebung. 1. Kor 13")
pruefe("erkannte Stelle wird aus dem Thema genommen", False,
       "1. Kor" in e["prompt"])
pruefe("und steht als Stelle da", ["1. Korinther 13"], e["stellen"])
pruefe("das Thema bleibt erhalten", True, "Vergebung" in e["prompt"])

# Hier ist der Kern des alten Fehlers: ein Buch, das es nicht gibt,
# darf nicht verschwinden. Sonst loescht das Pult etwas, was es nicht
# versteht -- und niemand sieht es.
e = thema("Thema: Treue. Buch Henoch 3")
pruefe("eine unbekannte Stelle bleibt im Thema stehen", True,
       "Henoch 3" in e["prompt"])
pruefe("und gilt nicht als Stelle", [], e["stellen"])

e = thema("Zum zweiten Mal 2 Lesungen")
pruefe("der Fehlalarm bleibt als Text stehen", True,
       "Lesungen" in e["prompt"])

titel("6) Der Prompt wird nach Token gekürzt, und der Kopf bleibt")

# Attrappe statt Modell: ein Token je Wort. Geprüft wird die Rangfolge,
# nicht der Tokenizer -- den prüft der Live-Lauf.
zaehlen = (lambda t: len(t.split()) if t else 0)
kopf = "Mitschrift einer Predigt. Nehemia baut die Mauer."
namen = ["Sanballat", "Tobija", "Geschem", "Hanani", "Mesullam"]
verlauf = ["erster Satz hier", "zweiter Satz hier", "dritter Satz hier"]

weit = b.stt_prompt_bauen(kopf, namen, verlauf, zaehlen, 100)
pruefe("mit Luft steht alles drin", True,
       all(n in weit for n in namen) and "dritter" in weit)

eng = b.stt_prompt_bauen(kopf, namen, verlauf, zaehlen, 14)
pruefe("der Kopf bleibt, wenn es eng wird", True, kopf in eng)
pruefe("der Verlauf weicht zuerst", False, "erster Satz" in eng)
pruefe("die Namen bleiben noch", True, "Sanballat" in eng)

sehr_eng = b.stt_prompt_bauen(kopf, namen, verlauf, zaehlen, 9)
pruefe("dann weichen die Namen von hinten", False, "Mesullam" in sehr_eng)
pruefe("und der Kopf steht immer noch", True, kopf in sehr_eng)

# Der Verlauf wird vom JÜNGSTEN her genommen: der sagt am meisten
# darüber, wie es weitergeht.
mittel = b.stt_prompt_bauen(kopf, [], verlauf, zaehlen, 13)
pruefe("der jüngste Satz kommt zuerst mit", True, "dritter" in mittel)

# Notfall: passt nicht einmal der Kopf, wird er gekürzt und nicht
# stillschweigend ein leerer Prompt gebaut.
notfall = b.stt_prompt_bauen(kopf, namen, verlauf, zaehlen, 3)
pruefe("auch im Notfall kommt Text heraus", True,
       0 < zaehlen(notfall) <= 3)

titel("7) Die alte Kürzung war messbar falsch")

# Der Beleg in Zahlen, mit dem Tokenizer des eingesetzten Modells --
# wenn er dasteht. Sonst übersprungen, nicht geraten.
import glob                                              # noqa: E402
treffer = glob.glob(str(config.MODELL_ORDNER / "**" / "tokenizer.json"),
                    recursive=True)
if not treffer:
    print("   übersprungen: kein tokenizer.json unter models/.")
else:
    import tokenizers                                    # noqa: E402
    T = tokenizers.Tokenizer.from_file(treffer[0])

    def echt(t):
        return len(T.encode(" " + t.strip()).ids) if t else 0

    e = thema("Nehemia baut die Mauer. Nehemia 1-4")
    lang = ["Und so lesen wir weiter, dass die Mauer gebaut wurde in "
            "zweiundfuenfzig Tagen und alle Voelker ringsum es sahen.",
            "Die Feinde spotteten und sagten, selbst ein Fuchs wuerde "
            "diese Mauer umstossen, so schwach sei sie gebaut.",
            "Aber Nehemia betete und stellte Wachen auf, Tag und Nacht."]
    alt = " ".join([e["prompt"], " ".join(lang)])[-700:]
    neu = b.stt_prompt_bauen(e["kopf"], e["namen"], lang, echt)
    print(f"   alt: {echt(alt)} Token, Kopf drin: {e['kopf'][:30] in alt}")
    print(f"   neu: {echt(neu)} Token, Kopf drin: {e['kopf'][:30] in neu}")
    pruefe("alt lag über der Grenze von 223 Token", True,
           echt(alt) > b.STT_TOKEN_GRENZE)
    pruefe("und hatte den Kopf verloren", False, e["kopf"][:30] in alt)
    pruefe("neu bleibt unter der Grenze", True,
           echt(neu) <= b.STT_TOKEN_GRENZE)
    pruefe("und behält den Kopf", True, e["kopf"][:30] in neu)

print()
if FEHLER:
    print(f"{ROT}{FEHLER} Fehler.{AUS}")
    sys.exit(1)
print(f"{GRUEN}Alle Faelle wie erwartet.{AUS}")
