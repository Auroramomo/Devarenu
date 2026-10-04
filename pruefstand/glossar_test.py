#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Das Glossar: ändert eine neue Fassung etwas an den alten Sprachen?

    python pruefstand/glossar_test.py

DER FALL, DER DIESEN LAUF NÖTIG MACHT

Mit 0.4.0 wird zum ersten Mal eine neue Glossarfassung aktiv: v0.9
statt v0.4, mit den Rückmeldungen der spanischen und portugiesischen
Prüfer. Gearbeitet wurde nur an `es` und `pt`. Englisch, Russisch und
Persisch dürfen davon nichts merken.

Das ist schwerer, als es klingt. Das Glossar wirkt nicht über die
Spalte, sondern über die **Suchvarianten**: `glossar.finde()` sortiert
alle Varianten nach Länge und lässt die erste, die eine Textstelle
beansprucht, gewinnen. Eine neue Zeile „28 Glaubensüberzeugungen"
ist länger als die Variante „Glaubensüberzeugungen" an D034 --
sie gewinnt, D034 fällt als Überlappung weg, und weil die neue Zeile
für Englisch leer ist, fehlt „fundamental beliefs" im englischen
Prompt. In der CSV sieht man davon nichts.

Genau das ist beim Bauen von v0.9 neun Mal passiert. Die neun Zeilen
sind draußen geblieben. Dieser Lauf hält den Zustand fest: er
vergleicht nicht die Dateien, sondern das ERGEBNIS -- den Text, den
glossarzeilen() dem Sprachmodell vorgibt.
"""

import csv
import io
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))
sys.path.insert(0, str(WURZEL / "werkzeuge"))

import config                                        # noqa: E402
from glossar import Glossar, glossarzeilen, sprachen_aus_kopf  # noqa: E402
from glossar_vergleich import vergleichen, vergleichen_ausser  # noqa: E402

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


def lies(pfad):
    with io.open(pfad, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


ALT = WURZEL / "glossar_v0.4.csv"
# Die aktive Fassung, nicht eine fest eingetragene. Bis 0.4.1 stand
# hier "glossar_v0.9.csv" -- und jede neue Fassung liess diesen
# Prüflauf fallen, obwohl an ihr nichts falsch war. Was zu prüfen ist,
# ist nicht die Nummer, sondern dass die aktive Datei wirklich daliegt
# und dass die Vorgängerin nicht verschwindet.
NEU = config.GLOSSAR_CSV

titel("1) Die aktive Fassung ist die, die geprüft wurde")

pruefe("config zeigt auf eine Glossardatei", True,
       config.GLOSSAR_CSV.name.startswith("glossar_v")
       and config.GLOSSAR_CSV.name.endswith(".csv"))
pruefe("die Datei liegt da", True, NEU.exists())
pruefe("die alte Fassung bleibt liegen", True, ALT.exists())
pruefe("die Vorgängerfassung liegt auch noch da", True,
       (WURZEL / "glossar_v0.9.csv").exists())

g = Glossar.laden(NEU)
pruefe("es ist eine Zielsprache", True, "es" in g.sprachen)
pruefe("pt ist eine Zielsprache", True, "pt" in g.sprachen)
# n_es sieht aus wie eine Sprache, ist aber eine Nebenformspalte. Ohne
# ein "k_n_es" daneben zaehlt sie nicht -- und ein solches gibt es
# nicht. Waere es anders, boete das Pult eine Sprache "n_es" an.
pruefe("n_es gilt NICHT als Sprache", False, "n_es" in g.sprachen)
pruefe("n_pt gilt NICHT als Sprache", False, "n_pt" in g.sprachen)

titel("2) en, ru und fa sind unverändert -- der Vergleichslauf")

# Derselbe Vergleich, den werkzeuge/glossar_vergleich.py von Hand
# macht. Er gehoert hierher, damit er bei JEDER kuenftigen Fassung
# wieder laeuft und nicht nur einmal lief.
# AUSDRUECKLICH ERLAUBT, mit Begruendung.
#
# Eine Suchvariante darf en, ru und fa aendern -- aber nur dort, wo
# genau sie greift, und nur so, dass der Begriff danach BESSER steht.
# Jede andere Abweichung bleibt ein Fehler.
#
#   "Geist der Weissagung" (0.4.2, an D009)
#       Vorher griff nur das kuerzere "Prophetie" und gab
#       "Prophetie = prophecy" vor. Jetzt steht der ganze Begriff da:
#       "Geist der Prophetie = Spirit of Prophecy". Das ist der Zweck
#       der Variante.
#   "Prediger" (0.4.2 Nachbesserung, A021 gegen D028)
#       "Prediger" heisst das Bibelbuch UND die Person. Bis dahin
#       gewann immer das Buch: "this Ecclesiastes wanted to preach".
#       A021 greift jetzt nur noch im Stellenzusammenhang, sonst
#       D028. Die Uebersetzungen beider Zeilen sind unberuehrt --
#       geprueft in pruefstand/prediger_test.py.
ERLAUBT = ["Geist der Weissagung", "Prediger", "Pred "]
abweichungen, fremd = vergleichen_ausser(ALT, NEU, ["en", "ru", "fa"],
                                         ERLAUBT)
pruefe("keine Sprache hat sich unerlaubt geändert", 0, fremd)
if abweichungen:
    print(f"        ({abweichungen} erlaubte Abweichung(en), "
          f"alle an: {', '.join(ERLAUBT)})")

titel("3) Die v0.4-Spalten sind Zeichen für Zeichen gleich")

alt_zeilen = {z["id"]: z for z in lies(ALT)}
neu_zeilen = {z["id"]: z for z in lies(NEU)}
spalten_alt = list(next(iter(alt_zeilen.values())).keys())
unterschiede = [
    (i, k) for i in alt_zeilen for k in spalten_alt
    if (alt_zeilen[i].get(k) or "") != (neu_zeilen.get(i, {}).get(k) or "")
]
# Suchvarianten duerfen wachsen -- das ist der Weg, eine Zeile besser
# zu treffen, ohne ihre Uebersetzungen anzufassen. Eine Uebersetzung
# zu aendern bleibt verboten: sie ist von einem Muttersprachler
# gegengelesen, und wer sie still ersetzt, nimmt dem Gegenlesen den
# Sinn.
gewachsen = [
    (i, k) for i, k in unterschiede
    if k == "suchvarianten"
    and set(filter(None, (alt_zeilen[i].get(k) or "").split("|")))
        <= set(filter(None, (neu_zeilen[i].get(k) or "").split("|")))
]
# Zwei Zeilen duerfen Suchvarianten auch VERLIEREN: A021 und D028
# teilen sich das Wort "Prediger", und die Kollision laesst sich nur
# aufloesen, indem eine der beiden die blosse Form abgibt. Was dabei
# NICHT angefasst werden darf, sind die Uebersetzungen -- und genau
# das steht unten.
UMGEHAENGT = {"A021", "D028"}
erlaubt_leer = [(i, k) for i, k in unterschiede
                if i in UMGEHAENGT and k in ("suchvarianten", "anmerkung")]
pruefe("keine alte Zelle angefasst ausser Suchvarianten",
       [], [x for x in unterschiede
            if x not in gewachsen and x not in erlaubt_leer])
if gewachsen:
    print("        (Suchvarianten ergaenzt: "
          + ", ".join(i for i, _ in gewachsen) + ")")
if erlaubt_leer:
    print("        (Prediger-Kollision umgehaengt: "
          + ", ".join(sorted({i for i, _ in erlaubt_leer})) + ")")
# Die Werte dieser beiden Zeilen muessen Zeichen fuer Zeichen stehen.
werte = [k for k in spalten_alt
         if k not in ("suchvarianten", "anmerkung")]
pruefe("und an A021/D028 keine Uebersetzung geaendert", [],
       [(i, k) for i in UMGEHAENGT for k in werte
        if (alt_zeilen[i].get(k) or "") != (neu_zeilen[i].get(k) or "")])
pruefe("keine alte Zeile verschwunden", [],
       [i for i in alt_zeilen if i not in neu_zeilen])

titel("4) Die neuen Zeilen halten sich an ihre Regeln")

neu_ids = [i for i in neu_zeilen if i not in alt_zeilen]
pruefe("es gibt überhaupt neue Zeilen", True, len(neu_ids) > 20)
pruefe("keine neue Zeile steht im Whisper-Prompt", [],
       [i for i in neu_ids if neu_zeilen[i]["stt"] == "1"])
pruefe("keine neue Zeile hat en, ru oder fa", [],
       [i for i in neu_ids
        if any(neu_zeilen[i].get(k, "").strip() for k in ("en", "ru", "fa"))])
pruefe("jede neue Zeile hat es oder pt", [],
       [i for i in neu_ids
        if not (neu_zeilen[i]["es"].strip() or neu_zeilen[i]["pt"].strip())])
# Ohne Suchvariante wird eine Zeile in deutschem Text NIE gefunden --
# glossar.finde() baut seine Muster allein aus den Varianten.
pruefe("jede neue Zeile hat eine Suchvariante", [],
       [i for i in neu_ids if not neu_zeilen[i]["suchvarianten"].strip()])

titel("5) Die festen Entscheidungen stehen drin")

nach_id = {e.id: e for e in g.eintraege}
pruefe("D021 es: Gran Chasco als Hauptform",
       "Gran Chasco", nach_id["D021"].ziel["es"])
pruefe("D021 es: Gran Decepción als Nebenform",
       ["Gran Decepción"], nach_id["D021"].neben["es"])
pruefe("D006 pt: juízo investigativo als Hauptform",
       "juízo investigativo", nach_id["D006"].ziel["pt"])
pruefe("D006 pt: julgamento investigativo als Nebenform",
       ["julgamento investigativo"], nach_id["D006"].neben["pt"])
# Der Auftrag nennt diese Schreibweise ausdrücklich.
pruefe("pt Morgenandacht mit Cedille", True,
       "Meditação Matinal" in nach_id["D045"].neben["pt"])
pruefe("und nirgends die Form ohne", False,
       "Meditacao" in NEU.read_text(encoding="utf-8"))

titel("6) Nebenformen erkennen, aber nicht vorgeben")

# Eine spanische Predigt, in der der Prediger die andere Form sagt:
# gefunden werden soll derselbe Eintrag.
for satz, erwartet in (("Hablamos del Gran Chasco de 1844.", True),
                       ("Hablamos de la Gran Decepción de 1844.", True)):
    treffer = [e.id for e in g.finde_in(satz, "es")]
    pruefe(f"es-Quelle findet D021 in {satz[:34]!r}", erwartet,
           "D021" in treffer)
# Ausgegeben wird trotzdem nur die Hauptform. Zwei Formen als Vorgabe
# waeren keine Vorgabe.
zeile = glossarzeilen([nach_id["D021"]], "es")
pruefe("die Vorgabe nennt nur die Hauptform", True,
       "Gran Chasco" in zeile and "Gran Decepción" not in zeile)
# Und der deutsche Weg bleibt der deutsche Weg.
pruefe("de-Quelle findet D021 weiterhin", True,
       "D021" in [e.id for e in g.finde("Die Große Enttäuschung von 1844")])

titel("7) Freigegeben heißt wählbar, nicht eingeschaltet")

pruefe("es ist geprüft", True, "es" in config.GEPRUEFT)
pruefe("pt ist geprüft", True, "pt" in config.GEPRUEFT)
# In Rostock darf sich nichts von selbst einschalten. Die Zielsprachen
# bleiben, was sie waren; gewaehlt wird am Pult.
pruefe("ZIELSPRACHEN unverändert", ["en", "ru", "fa"],
       list(config.ZIELSPRACHEN))
pruefe("Polnisch bleibt ungeprüft", False, "pl" in config.GEPRUEFT)

titel("8) Die Anrede steht fest, und nur wo sie belegt ist")

pruefe("es hat eine Anrede", True, bool(config.ANREDE.get("es")))
pruefe("pt hat eine Anrede", True, bool(config.ANREDE.get("pt")))
pruefe("es: ustedes", True, "ustedes" in config.ANREDE["es"])
pruefe("pt: vocês", True, "vocês" in config.ANREDE["pt"])
# Fuer die uebrigen Sprachen waere sie ungeprueft oder sinnlos.
pruefe("en, ru, fa bekommen keine", [],
       [s for s in ("en", "ru", "fa") if s in config.ANREDE])

print()
if FEHLER:
    print(f"{ROT}{FEHLER} Fehler.{AUS}")
    sys.exit(1)
print(f"{GRUEN}Alle Faelle wie erwartet.{AUS}")
