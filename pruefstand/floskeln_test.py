#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Faellt die Abspannfloskel, und bleibt die Predigt stehen?

    python pruefstand/floskeln_test.py

Whisper antwortet auf Orgel, Gemeindegesang und auf jede laengere Stille
mit Saetzen aus seinem Trainingsmaterial: Untertitelhinweise,
Senderabspanne, "Vielen Dank fuers Zuhoeren". Der Filter in
server.py (Werk.ERFUNDEN) wirft sie weg.

Bis 0.4.0 stand im Muster "( fuer|für)?" -- das Leerzeichen nur im
ersten Zweig. "Vielen Dank fuers Zuhoeren." ging damit durch und lief in
vier Sprachen auf die Handys. Genau dieser Fall steht unten als erste
Zeile.

Drei Arten von Zeilen:
    FALLEN    besteht ganz aus einer Floskel -> leerer Text
    BLEIBEN   echte Rede, auch wenn "Dank", "Amen" oder
              "Aufmerksamkeit" darin vorkommt -> unveraendert
    KUERZEN   echte Rede mit angehaengtem Abspann -> nur der Abspann weg
"""
import re
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))

import server                                            # noqa: E402

W = server.Werk

# ---------------------------------------------------------------- Zeilen
# Muessen fallen: der Abschnitt besteht ganz aus der Floskel.
FALLEN = [
    "Vielen Dank fürs Zuhören.",
    "Vielen Dank für Ihre Aufmerksamkeit.",
    "Danke fürs Zuschauen!",
    "Vielen Dank für das Zuschauen.",
    "Vielen Dank für eure Aufmerksamkeit!",
    "Herzlichen Dank fürs Zusehen.",
    "Danke schön fürs Zuhören.",
    "Vielen Dank.",
    "Vielen Dank!",
    "Untertitel im Auftrag des ZDF, 2021",
    "Untertitelung des ZDF, 2020",
    "Untertitel von Stephanie Geiges",
    "Copyright WDR 2021",
    "Abonniert diesen Kanal!",
    "Bis zum nächsten Mal!",
    "Tschüss.",
    "Die Sendung wurde vom NDR live untertitelt.",
    "WDR mediagroup GmbH im Auftrag des WDR",
    "Im Auftrag des ZDF, 2019",
    "Mit freundlicher Unterstützung der Bundesregierung",
    "Untertitelung. BR 2018",
    "Amara.org community",
    # Fuehrende Zeichen und Leerraum duerfen den Filter nicht aushebeln.
    "  ... Vielen Dank fürs Zuhören.  ",
    "— Vielen Dank für Ihre Aufmerksamkeit —",
    # Russisch (0.5.2), wortgleich aus den Belegen in server.py:
    #   [G] Gist waveletdeboshir, whisper-large-v2 auf 13 h Rauschen
    #   [H] Datensatz sachaarbonel/whisper-hallucinations, phrases.csv
    # (arXiv 2609.32560 stand bis 28.10.2026 hier und ist gestrichen:
    # der Aufsatz nennt keine Einzelbeispiele.)
    "Спасибо за субтитры!",                                    # [G]
    "Субтитры добавил DimaTorzok",                             # [G]
    "Субтитры подогнал «Симон»!",                              # [G]
    "Редактор субтитров М.Лосева Корректор А.Егорова",         # [G]
    "Редактор субтитров А.Синецкая Корректор А.Егорова",       # [G]
    "Редактор субтитров Т.Горелова Корректор А.Егорова",       # [G]
    "Редактор субтитров Е.Жукова Корректор А.Егорова",         # [G]
    "Редактор субтитров А.Семкин Корректор А.Егорова",         # [G]
    "Редактор субтитров А.Захарова Корректор А.Егорова",       # [G]
    "Смотрите продолжение во второй части видео.",             # [G]
    "Смотрите продолжение в следующей части.",                 # [G]
    "Смотрите продолжение в следующей части видео.",           # [G]
    "Смотрите продолжение в 4 части видео.",                   # [G]
    "Смотрите продолжение в следующей серии...",               # [G]
    "Смотрите продолжение во второй части.",                   # [G]
    "Продолжение следует...",                                  # [G]
    "ПОДПИШИСЬ НА КАНАЛ",                                      # [G]
    "ПОДПИШИСЬ!",                                              # [G]
    "ПОДПИШИСЬ",                                               # [G]
    "спасибо за просмотр",                                     # [H]
    "подписывайтесь на мой канал",                             # [H]
]

# Muessen bleiben: echte Rede. Das Wort "Dank" allein ist im
# Gottesdienst kein Verdacht, sondern der Normalfall.
BLEIBEN = [
    "Amen.",
    "Danke.",
    "Danke schön.",
    "Wir danken Gott für seine Gnade.",
    "Danke für dein Wort, Herr.",
    "Vielen Dank, dass ihr heute gekommen seid.",
    "Dank sei Gott, der uns den Sieg gibt durch unseren Herrn Jesus Christus.",
    "Schenke uns Aufmerksamkeit für dein Wort.",
    "Ich bitte um eure Aufmerksamkeit für den Predigttext.",
    "Lasst uns Gott danken und ihn loben.",
    "Der Dank des Volkes stieg auf zum Himmel.",
    "Paulus beginnt fast jeden Brief mit einem Dank.",
    "Und das Volk sprach: Amen, Amen, und sie neigten sich.",
    "Danket dem Herrn, denn er ist freundlich.",
    "Herzlichen Dank an alle, die heute mitgeholfen haben.",
    "Bis zum nächsten Mal werden wir diesen Abschnitt zu Ende lesen.",
    # Russisch (0.5.2): Predigtsaetze, die an die Formeln anstreifen.
    "Аминь.",
    "Спасибо.",
    "Спасибо за ваши молитвы.",
    "Спасибо, Господь, за Твоё слово.",
    "Продолжение следует в следующей главе.",
    "Смотрите продолжение этой мысли в пятой главе.",
    "Подпишитесь под этими словами своим сердцем.",
    "Мы будем молиться за наших братьев и сестёр.",
]

# Muessen gekuerzt werden: echte Rede, Abspann hinten dran.
KUERZEN = [
    ("Gott segne euch. Vielen Dank fürs Zuhören.",
     "Gott segne euch."),
    ("Der Herr segne dich und behüte dich. Amen. "
     "Vielen Dank für Ihre Aufmerksamkeit.",
     "Der Herr segne dich und behüte dich. Amen."),
    ("Wir lesen heute aus dem Römerbrief. Untertitelung des ZDF, 2021",
     "Wir lesen heute aus dem Römerbrief."),
    ("Lasst uns beten. Danke fürs Zuschauen!",
     "Lasst uns beten."),
    ("Das war der erste Teil. Vielen Dank. Bis zum nächsten Mal!",
     "Das war der erste Teil."),
    # Russisch (0.5.2)
    ("Да благословит вас Господь. Продолжение следует...",
     "Да благословит вас Господь."),
    ("Помолимся. Спасибо за просмотр!",
     "Помолимся."),
    ("Аминь. Редактор субтитров А.Семкин Корректор А.Егорова",
     "Аминь."),
]

fehler = 0


def pruefe(was, bedingung, einzelheit=""):
    global fehler
    if bedingung:
        print(f"   ok    {was}")
    else:
        fehler += 1
        print(f"   FEHLER {was}" + (f"  -> {einzelheit}" if einzelheit else ""))


def ganz_floskel(text):
    return bool(W.ERFUNDEN.fullmatch(text.strip()))


print(f"\n{len(FALLEN)} Floskeln -- muessen fallen")
for t in FALLEN:
    pruefe(repr(t), ganz_floskel(t), "kam durch")

print(f"\n{len(BLEIBEN)} echte Saetze -- muessen bleiben")
for t in BLEIBEN:
    gekuerzt = W.floskel_kuerzen(t)
    pruefe(repr(t), not ganz_floskel(t) and gekuerzt == t.strip(),
           f"wurde zu {gekuerzt!r}")

print(f"\n{len(KUERZEN)} Saetze mit Abspann -- nur der Abspann faellt")
for roh, soll in KUERZEN:
    ist = W.floskel_kuerzen(roh)
    pruefe(repr(roh), not ganz_floskel(roh) and ist == soll, f"wurde {ist!r}")

print("\nDer alte Fehler, ausdruecklich")
pruefe('"( fuer|für)?" ohne Leerzeichen ist weg',
       "( fuer|für)?" not in W.ERFUNDEN.pattern)
pruefe("geprueft wird mit fullmatch, nicht mit match",
       W.ERFUNDEN.fullmatch("Vielen Dank fürs Zuhören.") is not None
       and W.ERFUNDEN.fullmatch(
           "Vielen Dank für das Wort, das heute zu uns gesprochen hat.")
       is None)

print("\nQuellen der russischen Formeln (28.10.2026 nachgesehen)")
# arXiv 2609.32560 nennt keine Einzelbeispiele und darf nicht mehr als
# Beleg stehen. Belegt sind die Formeln im Gist [G] und in phrases.csv
# des Datensatzes [H]; "Продолжение следует" steht nur im Gist.
quelltext = (WURZEL / "server.py").read_text(encoding="utf-8")
diese_datei = Path(__file__).read_text(encoding="utf-8")
pruefe("server.py nennt arXiv 2609.32560 nicht mehr als Beleg",
       "[A] arXiv 2609.32560" not in quelltext
       and not re.search(r"#\s*\[G\]\s*\[A\]", quelltext))
pruefe("der Pruefstand auch nicht",
       not re.search(r"#\s*(\[G\]\s*)?\[A\]\s*$", diese_datei, re.M))
zeile = next((z for z in quelltext.splitlines()
              if "продолжение\\s+следует" in z), "")
pruefe('"Продолжение следует" hat genau den Gist als Beleg',
       zeile.rstrip().endswith("# [G]"), zeile.strip())

gesamt = len(FALLEN) + len(BLEIBEN) + len(KUERZEN)
print(f"\n{gesamt} Zeilen geprueft.")
if fehler:
    print(f"{fehler} FEHLER")
    sys.exit(1)
print("Alles in Ordnung.")
