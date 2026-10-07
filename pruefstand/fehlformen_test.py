#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Nachkontrolle fuer bekannte Fehlformen (Nachtrag zu 0.5.0).

    .venv/bin/python pruefstand/fehlformen_test.py

Erster Eintrag, Ukrainisch: steht "Abendmahl" im deutschen Abschnitt,
darf in der Uebersetzung keine Form von Вечірня/Вечерня stehen -- das
ist die Vesper. Richtig ist Вечеря Господня (Glossar C041).

  * Trifft die Kontrolle, wird EINMAL neu uebersetzt, mit Hinweis.
  * Trifft sie wieder, geht die Uebersetzung trotzdem hinaus,
    unveraendert, und die Fehlform ins Journal. Ersetzt wird nie.
  * Ohne den Glossarbegriff im Abschnitt: kein zweiter Aufruf, egal
    was in der Uebersetzung steht.

Ohne Ollama: das Modell ist ein Nachbau, der vorgegebene Antworten
liefert -- die erste davon ist die echte Ausgabe von gemma4:12b zu
F04 aus pruefung/fallstricke_uk.csv.
"""
import contextlib
import io
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))
import config  # noqa: E402
import server  # noqa: E402
import zaehlung  # noqa: E402
from glossar import Glossar  # noqa: E402

ROT, GRUEN, AUS = "\033[31m", "\033[32m", "\033[0m"
FEHLER = 0

F04 = "Vor dem Abendmahl feiern wir die Fußwaschung."
F04_GEMMA = "Перед Вечернею ми відзначаємо обмивання ніг."
F04_RICHTIG = "Перед Вечерею Господньою ми звершуємо обряд обмивання ніг."


def pruefe(was, erwartet, ist):
    global FEHLER
    if erwartet == ist:
        print(f"   ok    {was}")
    else:
        print(f"   {ROT}FEHL{AUS}  {was}: erwartet {erwartet!r}, ist {ist!r}")
        FEHLER += 1


def titel(t):
    print(f"\n\033[1m== {t}\033[0m")


class Modell:
    """Liefert der Reihe nach die vorgegebenen Antworten und merkt sich
    jeden Systemprompt."""
    def __init__(self, *antworten):
        self.antworten = list(antworten)
        self.prompts = []

    def post(self, url, json=None, timeout=None):
        self.prompts.append(json["messages"][0]["content"])
        inhalt = self.antworten.pop(0)

        class Antwort:
            def raise_for_status(self):
                pass

            def json(self):
                return {"message": {"content": inhalt}}
        return Antwort()


GLOSSAR = Glossar.laden(config.GLOSSAR_CSV)


def uebersetzen(satz, sprache, *antworten):
    w = server.Werk.__new__(server.Werk)
    w.requests = Modell(*antworten)
    w.quelle = "de"
    w.glossar = GLOSSAR
    w.zaehlung = zaehlung.Tabelle.laden()
    w.thema_im_prompt = False
    w.kontext_stellen = []
    w.kontext_namen = []
    journal = io.StringIO()
    with contextlib.redirect_stdout(journal):
        t = server.Werk.uebersetzen(w, satz, sprache)
    return t, w.requests.prompts, journal.getvalue()


titel("1) Die Regel")
regel = config.FEHLFORMEN["uk"][0]
eintrag = next(e for e in GLOSSAR.eintraege if e.id == regel["glossar"])
pruefe("sie haengt am Glossarbegriff Abendmahl", "Abendmahl", eintrag.de)
pruefe("die richtige Form kommt aus dem Glossar", "Вечеря Господня",
       eintrag.ziel.get("uk"))
pruefe("nur fuer Ukrainisch", ["uk"], sorted(config.FEHLFORMEN))
treffer = GLOSSAR.finde_in(F04, "de")
pruefe("zwei Regeln, beide an C041", ["C041", "C041"],
       [r["glossar"] for r in config.FEHLFORMEN["uk"]])
for form in ("Вечірня", "Вечірні", "Вечірню", "Вечірньою", "Вечерня",
             "Вечерні", "Вечерню", "Вечернею", "вечірня", "ВЕЧЕРНІ",
             # Die zweite Regel: falsch geschrieben, gemma4:12b im
             # zweiten Versuch zu F04.
             "Вечерєю", "Вечерєй", "вечерє"):
    pruefe(f"Fehlform erkannt: {form}", 1,
           len(server.fehlformen_finden(treffer, f"Перед {form} ми", "uk")))
for form in ("Вечеря Господня", "Вечері Господньої", "Вечерю Господню",
             "Вечерею Господньою", "ввечері", "вечора", "вечір",
             "вечірній", "Вечір"):
    # "вечірній" (Adjektiv, abendlich) beginnt mit "вечірн" und wird
    # deshalb erkannt -- aber nur, wenn im Deutschen "Abendmahl" steht.
    # Dann ist ein zweiter Versuch harmlos.
    erwartet = 1 if form == "вечірній" else 0
    pruefe(f"{'erkannt (siehe Kommentar)' if erwartet else 'keine Fehlform'}: "
           f"{form}", erwartet,
           len(server.fehlformen_finden(treffer, f"Перед {form} ми", "uk")))
pruefe("ohne Glossartreffer: nichts gesucht", [],
       server.fehlformen_finden([], F04_GEMMA, "uk"))

titel("2) F04: die echte Ausgabe, dann eine richtige")
t, prompts, journal = uebersetzen(F04, "uk", F04_GEMMA, F04_RICHTIG)
pruefe("zwei Aufrufe", 2, len(prompts))
pruefe("die zweite Antwort geht hinaus", F04_RICHTIG, t)
pruefe("der erste Prompt hat keinen Hinweis", False, "WICHTIG" in prompts[0])
pruefe("der zweite nennt die richtige Form", True,
       "„Abendmahl“ heisst „Вечеря Господня“" in prompts[1])
pruefe("mit den Beugungsformen", True, "Вечерею Господньою" in prompts[1])
pruefe("der Instrumental ausdruecklich", True,
       "Instrumental Вечерею Господньою" in prompts[1]
       and "„Перед Вечерею Господньою“" in prompts[1])
pruefe("und die Schreibung mit е", True, "nie mit є" in prompts[1])
pruefe("und warum die Fehlform falsch ist", True, "Vesper" in prompts[1])
pruefe("der Rest des Prompts ist derselbe", True,
       prompts[1].startswith(prompts[0]))
pruefe("das Journal nennt nur das Wort", True,
       "Fehlform uk: Вечернею -- noch einmal mit Hinweis" in journal
       and "обмивання" not in journal)

titel("3) Zweimal falsch: trotzdem senden, nichts ersetzen")
zweite = "Перед Вечірньою ми святкуємо обмивання ніг."
t, prompts, journal = uebersetzen(F04, "uk", F04_GEMMA, zweite)
pruefe("zwei Aufrufe, nicht mehr", 2, len(prompts))
pruefe("gesendet wird die zweite Antwort, unveraendert", zweite, t)
pruefe("ins Journal, als Warnung", True,
       "Fehlform uk blieb nach dem zweiten Versuch: Вечірньою" in journal)
pruefe("auch dort ohne den Satz", False, "святкуємо" in journal)

titel("3b) Beide Fehlformen zugleich: die Formen nur einmal")
beide = "Перед Вечернею, тобто Вечерєю, ми звершуємо обмивання ніг."
t, prompts, journal = uebersetzen(F04, "uk", beide, F04_RICHTIG)
pruefe("zwei Aufrufe", 2, len(prompts))
pruefe("beide Fehlformen im Hinweis", True,
       "Nicht Вечірня/Вечерня" in prompts[1] and "Nicht Вечерє…" in prompts[1])
pruefe("die Formen stehen einmal da", 1,
       prompts[1].count("Instrumental Вечерею Господньою"))
t, prompts, journal = uebersetzen(F04, "uk", F04_GEMMA,
                                  "Перед Вечерєю Господньою ми звершуємо "
                                  "обмивання ніг.")
pruefe("der zweite Versuch mit є: gesendet und ins Journal", True,
       "Fehlform uk blieb nach dem zweiten Versuch: Вечерєю" in journal)

titel("4) Kein zweiter Aufruf, wo es nichts zu pruefen gibt")
t, prompts, _ = uebersetzen(F04, "uk", F04_RICHTIG)
pruefe("Abendmahl, gleich richtig: ein Aufruf", (1, F04_RICHTIG),
       (len(prompts), t))
t, prompts, _ = uebersetzen("Am Abend feiern wir die Vesper.", "uk",
                            "Увечері ми звершуємо вечірню.")
pruefe("ohne Abendmahl im Deutschen: ein Aufruf, auch mit вечірню",
       1, len(prompts))
t, prompts, _ = uebersetzen(F04, "ru", "Перед Вечерней мы совершаем омовение ног.")
pruefe("andere Sprache ohne Regel: ein Aufruf", 1, len(prompts))

print()
if FEHLER:
    print(f"{ROT}{FEHLER} Fehler.{AUS}")
    sys.exit(1)
print(f"{GRUEN}Alle Faelle wie erwartet.{AUS}")
