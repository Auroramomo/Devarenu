#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Baut aus Bibelstellen den Whisper-Prompt.

Ein fester Prompt bringt nichts: Whisper verhoert sich an Eigennamen,
nicht an Lehrbegriffen. Der Ausweg ist der Ablauf, den die Technik am
Pult ohnehin leisten kann -- vor dem Gottesdienst Thema und Bibelstellen
erfragen, zwei Zeilen eintippen. Dieses Modul macht daraus eine
Namensliste. Ausfuehrlich begruendet in LIESMICH.md unter "Warum es so
gebaut ist".

Aufruf zum Ausprobieren:
    python bibelstellen.py "Predigt über Vergebung. 1. Samuel 15, Matthäus 18"
"""

import csv
import re
import sys
from pathlib import Path

from namen_aus_bibel import BUECHER

# Buchnamen in weiteren Quellsprachen. Ein englischer Prediger sagt
# "1 Kings", ein ukrainischer etwas anderes; erkannt werden soll beides,
# und zwar auf denselben Glossarnamen abgebildet.
WEITERE = {
    "en": {
        "1. Mose": ["Genesis", "Gen"], "2. Mose": ["Exodus", "Ex"],
        "3. Mose": ["Leviticus", "Lev"], "4. Mose": ["Numbers", "Num"],
        "5. Mose": ["Deuteronomy", "Deut", "Dt"],
        "Josua": ["Joshua", "Josh"], "Richter": ["Judges", "Judg"],
        "Ruth": ["Ruth"], "1. Samuel": ["1 Samuel", "1Sam", "1 Sam"],
        "2. Samuel": ["2 Samuel", "2Sam", "2 Sam"],
        "1. Könige": ["1 Kings", "1Kgs", "1 Kgs"],
        "2. Könige": ["2 Kings", "2Kgs", "2 Kgs"],
        "1. Chronik": ["1 Chronicles", "1Chr"],
        "2. Chronik": ["2 Chronicles", "2Chr"],
        "Esra": ["Ezra"], "Nehemia": ["Nehemiah", "Neh"],
        "Esther": ["Esther", "Esth"], "Hiob": ["Job"],
        "Psalmen": ["Psalm", "Psalms", "Ps"],
        "Sprüche": ["Proverbs", "Prov"],
        "Prediger": ["Ecclesiastes", "Eccl"],
        "Hohelied": ["Song of Songs", "Song of Solomon"],
        "Jesaja": ["Isaiah", "Isa"], "Jeremia": ["Jeremiah", "Jer"],
        "Klagelieder": ["Lamentations", "Lam"],
        "Hesekiel": ["Ezekiel", "Ezek"], "Daniel": ["Daniel", "Dan"],
        "Hosea": ["Hosea", "Hos"], "Joel": ["Joel"], "Amos": ["Amos"],
        "Obadja": ["Obadiah", "Obad"], "Jona": ["Jonah"],
        "Micha": ["Micah", "Mic"], "Nahum": ["Nahum", "Nah"],
        "Habakuk": ["Habakkuk", "Hab"],
        "Zephanja": ["Zephaniah", "Zeph"], "Haggai": ["Haggai", "Hag"],
        "Sacharja": ["Zechariah", "Zech"], "Maleachi": ["Malachi", "Mal"],
        "Matthäus": ["Matthew", "Matt", "Mt"], "Markus": ["Mark", "Mk"],
        "Lukas": ["Luke", "Lk"], "Johannes": ["John", "Jn"],
        "Apostelgeschichte": ["Acts"], "Römer": ["Romans", "Rom"],
        "1. Korinther": ["1 Corinthians", "1Cor"],
        "2. Korinther": ["2 Corinthians", "2Cor"],
        "Galater": ["Galatians", "Gal"], "Epheser": ["Ephesians", "Eph"],
        "Philipper": ["Philippians", "Phil"],
        "Kolosser": ["Colossians", "Col"],
        "1. Thessalonicher": ["1 Thessalonians", "1Thess"],
        "2. Thessalonicher": ["2 Thessalonians", "2Thess"],
        "1. Timotheus": ["1 Timothy", "1Tim"],
        "2. Timotheus": ["2 Timothy", "2Tim"],
        "Titus": ["Titus"], "Philemon": ["Philemon", "Phlm"],
        "Hebräer": ["Hebrews", "Heb"], "Jakobus": ["James", "Jas"],
        "1. Petrus": ["1 Peter", "1Pet"], "2. Petrus": ["2 Peter", "2Pet"],
        "1. Johannes": ["1 John", "1Jn"], "2. Johannes": ["2 John", "2Jn"],
        "3. Johannes": ["3 John", "3Jn"], "Judas": ["Jude"],
        "Offenbarung": ["Revelation", "Rev"],
    },
    "uk": {
        "1. Mose": ["Буття"], "2. Mose": ["Вихід"], "3. Mose": ["Левит"],
        "4. Mose": ["Числа"], "5. Mose": ["Повторення Закону"],
        "Josua": ["Ісус Навин"], "Richter": ["Книга Суддів", "Суддів"],
        "Ruth": ["Рут"], "1. Samuel": ["1 Самуїлова"],
        "2. Samuel": ["2 Самуїлова"], "1. Könige": ["1 Царів"],
        "2. Könige": ["2 Царів"], "1. Chronik": ["1 Хронік"],
        "2. Chronik": ["2 Хронік"], "Esra": ["Ездри"],
        "Nehemia": ["Неемії"], "Esther": ["Естер"], "Hiob": ["Йова"],
        "Psalmen": ["Псалом", "Псалми"], "Sprüche": ["Приповісті"],
        "Prediger": ["Екклезіяст"], "Hohelied": ["Пісня над піснями"],
        "Jesaja": ["Ісаї"], "Jeremia": ["Єремії"],
        "Klagelieder": ["Плач Єремії"], "Hesekiel": ["Єзекіїля"],
        "Daniel": ["Даниїла"], "Hosea": ["Осії"], "Joel": ["Йоіла"],
        "Amos": ["Амоса"], "Obadja": ["Овдія"], "Jona": ["Йони"],
        "Micha": ["Михея"], "Nahum": ["Наума"], "Habakuk": ["Авакума"],
        "Zephanja": ["Софонії"], "Haggai": ["Огія"],
        "Sacharja": ["Захарія"], "Maleachi": ["Малахії"],
        "Matthäus": ["Матвія"], "Markus": ["Марка"], "Lukas": ["Луки"],
        "Johannes": ["Івана"], "Apostelgeschichte": ["Дії"],
        "Römer": ["Римлян"], "1. Korinther": ["1 Коринтян"],
        "2. Korinther": ["2 Коринтян"], "Galater": ["Галатів"],
        "Epheser": ["Ефесян"], "Philipper": ["Филип'ян"],
        "Kolosser": ["Колосян"], "1. Thessalonicher": ["1 Солунян"],
        "2. Thessalonicher": ["2 Солунян"], "1. Timotheus": ["1 Тимофія"],
        "2. Timotheus": ["2 Тимофія"], "Titus": ["Тита"],
        "Philemon": ["Филимона"], "Hebräer": ["Євреїв"],
        "Jakobus": ["Якова"], "1. Petrus": ["1 Петра"],
        "2. Petrus": ["2 Петра"], "1. Johannes": ["1 Івана"],
        "2. Johannes": ["2 Івана"], "3. Johannes": ["3 Івана"],
        "Judas": ["Юди"], "Offenbarung": ["Об'явлення"],
    },
}

# Zusaetzliche deutsche Schreibweisen -- die, die am Pult wirklich
# getippt werden und die es bis 0.3.8 nicht gab.
#
# Die ausgeschriebenen Buchtitel: wer "Lukasevangelium 15" tippt, meint
# Lukas 15, und "Offenbarung des Johannes 14" meint Offenbarung 14 --
# bis 0.3.8 wurde daraus Johannes 14, also das falsche Buch.
_LANGFORMEN = {
    "Matthäus": ["Matthäusevangelium", "Evangelium nach Matthäus"],
    "Markus": ["Markusevangelium", "Evangelium nach Markus"],
    "Lukas": ["Lukasevangelium", "Evangelium nach Lukas"],
    "Johannes": ["Johannesevangelium", "Evangelium nach Johannes"],
    "Offenbarung": ["Offenbarung des Johannes"],
    "Apostelgeschichte": ["Apostelgeschichte des Lukas"],
    "Römer": ["Römerbrief", "Brief an die Römer"],
    "Galater": ["Galaterbrief", "Brief an die Galater"],
    "Epheser": ["Epheserbrief", "Brief an die Epheser"],
    "Philipper": ["Philipperbrief", "Brief an die Philipper"],
    "Kolosser": ["Kolosserbrief", "Brief an die Kolosser"],
    "Hebräer": ["Hebräerbrief", "Brief an die Hebräer"],
    "Jakobus": ["Jakobusbrief", "Brief des Jakobus"],
    "Judas": ["Judasbrief", "Brief des Judas"],
    "Titus": ["Titusbrief"], "Philemon": ["Philemonbrief"],
    "1. Korinther": ["1. Korintherbrief", "erster Korintherbrief"],
    "2. Korinther": ["2. Korintherbrief", "zweiter Korintherbrief"],
    "1. Thessalonicher": ["1. Thessalonicherbrief"],
    "2. Thessalonicher": ["2. Thessalonicherbrief"],
    "1. Timotheus": ["1. Timotheusbrief"],
    "2. Timotheus": ["2. Timotheusbrief"],
    "1. Petrus": ["1. Petrusbrief"], "2. Petrus": ["2. Petrusbrief"],
    "1. Johannes": ["1. Johannesbrief"],
    "2. Johannes": ["2. Johannesbrief"],
    "3. Johannes": ["3. Johannesbrief"],
    "Psalmen": ["Psalter"],
    "Hohelied": ["Hoheslied", "Lied der Lieder"],
    "Sprüche": ["Sprichwörter", "Buch der Sprüche"],
    "Prediger": ["Buch Prediger"],
}


def _ohne_umlaut(wort):
    """Roemer fuer Römer, Matthaeus fuer Matthäus.

    Am Pult wird auf einer Tastatur getippt, die Umlaute hat -- aber
    nicht jeder tippt sie. "Roemer 8" ist keine Nachlaessigkeit,
    sondern die Schreibweise, die ohne Umlaut auskommt, und sie stand
    bis 0.3.8 nicht in der Liste."""
    for mit, ohne in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"),
                      ("Ä", "Ae"), ("Ö", "Oe"), ("Ü", "Ue"), ("ß", "ss")):
        wort = wort.replace(mit, ohne)
    return wort


def _norm(form):
    """Die Vergleichsform: klein, ohne Leerzeichen UND OHNE PUNKTE.

    DAS WAR DER FEHLER BIS 0.3.8. Das Muster erlaubte Punkte und
    Leerzeichen an beliebiger Stelle -- "1. Kor", "1 Mose", "5 Mose"
    wurden also alle gefunden. Nachgeschlagen wurde dann aber in einer
    Tabelle, deren Schluessel nur die Leerzeichen entfernt hatte:
    darin stand "1.korinther" und "1kor", gesucht wurde "1.kor" und
    "1mose". Acht gaengige Schreibweisen gingen so verloren -- und
    weil die Stelle am Muster trotzdem traf, wurde sie aus dem
    Thema-Text GELOESCHT. Der Techniker tippte "1. Kor 13", und uebrig
    blieb ein Thema ohne Stelle und ohne Namen.

    Jetzt normalisieren beide Seiten gleich. Dass das keine zwei
    Buecher zusammenwirft, ist geprueft: ueber alle Formen aller
    Sprachen gibt es null Kollisionen."""
    return re.sub(r"[\s.]+", "", form).lower()


# Alle Schreibweisen auf den Glossarnamen abbilden, laengste zuerst, damit
# "1. Samuel" vor "Samuel" greift und "1Kor" nicht als "Kor" endet.
_FORMEN = {}
for _buch, _liste in BUECHER.items():
    for _f in _liste + [_buch]:
        _FORMEN[_norm(_f)] = _buch
        _FORMEN.setdefault(_norm(_ohne_umlaut(_f)), _buch)
for _buch, _liste in _LANGFORMEN.items():
    for _f in _liste:
        _FORMEN.setdefault(_norm(_f), _buch)
        _FORMEN.setdefault(_norm(_ohne_umlaut(_f)), _buch)
for _sprache, _tabelle in WEITERE.items():
    for _buch, _liste in _tabelle.items():
        for _f in _liste:
            _FORMEN.setdefault(_norm(_f), _buch)

# Abkuerzungen, die zugleich gewoehnliche Woerter sind. Sie gelten nur
# mit Punkt ("Mal. 2") oder mit Versangabe ("Mal 2,3").
#
# "Zum zweiten Mal 2 Lesungen" ergab bis 0.3.8 Maleachi 2, und "wir
# treffen uns am 3. Maerz" haette Amos 3 ergeben. Eine Stelle, die der
# Prompt nennt, aber niemand predigt, kostet nicht nur Platz: Whisper
# bekommt dann die Namen eines fremden Kapitels vorgelegt.
#
# Zurueckhaltend aufgezaehlt und nicht nach Laenge geraten: "Dan 7" und
# "Gal 5" sind gaengige Zitate, und "Dan" wie "Gal" sind keine
# deutschen Woerter.
_HEIKEL = {"mal", "mi", "am", "hi", "ri", "jude"}

def _fragment(form):
    """Macht aus einer Schreibweise ein Regex-Stueck, das alle ueblichen
    Varianten abdeckt: '1. Samuel' trifft auch '1.Samuel' und '1 Samuel',
    '1Sam' auch '1. Sam'.

    Mehrwortige Formen ("Offenbarung des Johannes") duerfen zwischen den
    Woertern beliebig viel Weissraum haben -- getippt wird am Pult, nicht
    gesetzt."""
    treffer = re.match(r"^([1-5])\.?\s*(.+)$", form)
    if treffer:
        return (re.escape(treffer.group(1)) + r"\s*\.?\s*"
                + _wortfolge(treffer.group(2)) + r"\.?")
    return _wortfolge(form) + r"\.?"


def _wortfolge(form):
    return r"\s+".join(re.escape(w) for w in form.split())


# Das Muster wird aus den bekannten Buchnamen gebaut, nicht aus einem
# allgemeinen Wortmuster. Sonst frisst ein beliebiges Wort die Ziffer der
# folgenden Angabe auf: aus "sowie 1Chr 21" wurde "sowie 1" plus ein
# uebrig gebliebenes "Chr", und die Stelle war verloren.
_ALLE_FORMEN = ({f for liste in BUECHER.values() for f in liste}
                | set(BUECHER)
                | {f for liste in _LANGFORMEN.values() for f in liste}
                | {f for t in WEITERE.values() for liste in t.values()
                   for f in liste})
_ALLE_FORMEN |= {_ohne_umlaut(f) for f in _ALLE_FORMEN}
_ALTERNATIVEN = "|".join(
    _fragment(f) for f in sorted(_ALLE_FORMEN, key=len, reverse=True))

# "Kapitel" und "Vers" ausgeschrieben: wer am Pult diktiert bekommt
# ("Johannes Kapitel 3 Vers 16"), tippt es auch so. Beides optional.
_MUSTER = re.compile(
    r"\b(" + _ALTERNATIVEN + r")"                                # 1 Buch
    r"\s*(?:kapitel\s*)?"                                       # "Kapitel"
    r"(\d{1,3})"                                                # 2 Kapitel
    r"(?:\s*(?:bis|[-–])\s*(\d{1,3}))?"                         # 3 bis Kapitel
    r"(\s*(?:[,:]|\s+vers)\s*\d{1,3}"                          # 4 Verse
    r"(?:\s*(?:[-–]|\s*bis)\s*\d{1,3})?)?",
    re.IGNORECASE)


def stellen_mit_bereichen(text):
    """[(stelle, ...), ...] und die Textbereiche, die dazu gehoeren.

    Nur ANERKANNTE Treffer liefern einen Bereich. Das ist der
    Unterschied, auf den es ankommt: bis 0.3.8 wurde jeder Mustertreffer
    aus dem Thema-Text geloescht, auch wenn das Nachschlagen danach
    scheiterte. "1. Kor 13" verschwand also spurlos -- weder als Stelle
    erkannt noch im Thema stehengeblieben. Jetzt gilt: was nicht erkannt
    wird, bleibt stehen."""
    gefunden, bereiche = [], []
    for treffer in _MUSTER.finditer(text):
        roh = _norm(treffer.group(1))
        buch = _FORMEN.get(roh)
        if not buch:
            continue
        # Abkuerzungen, die gewoehnliche Woerter sind, zaehlen nur mit
        # Punkt oder Versangabe.
        if roh in _HEIKEL and not (treffer.group(1).rstrip().endswith(".")
                                   or treffer.group(4)):
            continue
        von = int(treffer.group(2))
        bis = int(treffer.group(3)) if treffer.group(3) else von
        if bis < von or bis - von > 30:
            bis = von
        for k in range(von, bis + 1):
            stelle = f"{buch} {k}"
            if stelle not in gefunden:
                gefunden.append(stelle)
        bereiche.append(treffer.span())
    return gefunden, bereiche


def stellen_finden(text):
    """Zieht Buch- und Kapitelangaben aus freiem Text.

    Verse werden erkannt, aber weggeworfen: der Namensindex arbeitet auf
    Kapitelebene, und wer Matthaeus 18,21-35 predigt, streift ohnehin das
    ganze Kapitel."""
    return stellen_mit_bereichen(text)[0]


class Namensindex:
    """Die aus der Bibel extrahierte Namensliste, nach Kapiteln durchsuchbar."""

    def __init__(self, eintraege):
        self.eintraege = eintraege

    # Endungen, die kein Eigenname hat. Der Namensextrakt aus der
    # Studienbibel enthaelt zwangslaeufig Kommentarsprache, weil Bibeltext
    # und Kommentar auf derselben Seite stehen. Hier faellt der Rest weg,
    # den die Streuung nicht erwischt: Adverbien wie "ironischerweise",
    # Genitive wie "Handelns" und Partizipien wie "Bedeutet".
    # Bewusst zurueckhaltend: "ses" waere naheliegend fuer "Wuchses",
    # traefe aber auch Moses und Ramses. Den Grossteil raeumt ohnehin der
    # Streuungsfilter ab.
    NICHT_NAME = ("weise", "lich", "isch", "sam", "haft", "bar", "los",
                  "ens", "els", "ums", "erns", "ends", "ungs", "ungen",
                  "tet", "elns", "iche", "icher", "keiten")

    @classmethod
    def laden(cls, pfad, mit_verdaechtigen=False):
        pfad = Path(pfad)
        if not pfad.exists():
            return cls([])
        eintraege = []
        with open(pfad, encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh, delimiter=";"):
                # Was der Streuungsfilter als Allgemeinwort markiert hat,
                # bleibt draussen. Im Prompt zaehlt jeder der rund
                # 25 Plaetze, und ein Wort wie "Bedingungen" nimmt einem
                # Namen wie "Gibea" den Platz weg.
                if r.get("verdacht") and not mit_verdaechtigen:
                    continue
                if r["de"].lower().endswith(cls.NICHT_NAME):
                    continue
                eintraege.append({
                    "de": r["de"],
                    "haeufigkeit": int(r["haeufigkeit"]),
                    "rang": int(r["prompt_rang"]),
                    "kapitel": set(k for k in r["kapitel"].split("|") if k),
                })
        return cls(eintraege)

    def fuer_stellen(self, stellen, hoechstens=60):
        """Namen, die in den genannten Kapiteln vorkommen.

        Sortiert nach Prompt-Rang, also seltene zuerst. Das ist der Punkt:
        Jesus und Jerusalem trifft Whisper ohnehin, sie wuerden nur Platz
        kosten. Zarpat und Barsillai nicht. Innerhalb eines Rangs kommen
        die haeufigeren zuerst, weil sie im Kapitel wahrscheinlicher
        mehrfach fallen."""
        if not stellen:
            return []
        gesucht = set(stellen)
        treffer = [e for e in self.eintraege if e["kapitel"] & gesucht]
        treffer.sort(key=lambda e: (e["rang"], -e["haeufigkeit"]))
        return [e["de"] for e in treffer[:hoechstens]]


# Was nach dem Entfernen der Stellenangaben als Rest stehenbleibt und
# nichts mehr traegt: "Vergebung. und." liest sich schlechter als
# "Vergebung." und kostet Platz im knappen Budget.
_RESTE = re.compile(r"\b(und|sowie|bis|aus|in|zu|ueber|über|texte?|"
                    r"lesung|predigt(?:text)?|kapitel|vers)\b\s*$",
                    re.IGNORECASE)


def _freitext_saeubern(text):
    text = re.sub(r"\s{2,}", " ", text)
    text = text.strip(" ,.;:-–")
    for _ in range(3):
        neu = _RESTE.sub("", text).strip(" ,.;:-–")
        if neu == text:
            break
        text = neu
    return text


def prompt_bauen(freitext, namen, einleitung, max_zeichen):
    """Fuellt den Prompt bis zum Zeichenbudget.

    Whisper schneidet den initial_prompt bei 224 Token hart ab. Deutsch
    braucht grob 2,5 bis 3 Zeichen je Token. Der Freitext des Technikers
    steht vorn, weil er das Thema traegt; die Namen fuellen den Rest auf
    und werden hinten gekappt."""
    kopf = einleitung.strip()
    if freitext.strip():
        kopf += " " + freitext.strip().rstrip(".") + "."

    genommen = []
    for n in namen:
        versuch = kopf + " Namen: " + ", ".join(genommen + [n]) + "."
        if len(versuch) > max_zeichen:
            break
        genommen.append(n)

    if not genommen:
        return kopf[:max_zeichen], []
    return kopf + " Namen: " + ", ".join(genommen) + ".", genommen


# Whisper nimmt vom uebergebenen Prompt nur die letzten
# max_length // 2 - 1 Token, und max_length ist 448. Das sind 223.
# Nachgelesen in faster_whisper.transcribe.WhisperModel.get_prompt.
STT_TOKEN_GRENZE = 223


def stt_prompt_bauen(kopf, namen, verlauf, zaehlen, grenze=STT_TOKEN_GRENZE):
    """Der Prompt fuer EINEN Abschnitt, auf das Token-Budget gebracht.

    DER FEHLER BIS 0.3.8: der Prompt wurde als
    `" ".join([stt_prompt, verlauf])[-700:]` gebaut -- die letzten 700
    ZEICHEN. Waechst der Verlauf, faellt damit der Anfang weg, und der
    Anfang ist genau das Wertvolle: die Einleitung und das Thema, das
    der Techniker vor dem Gottesdienst erfragt hat. Bei einem
    namensreichen Kapitel ("Nehemia baut die Mauer. Nehemia 1-4") war
    nach wenigen Abschnitten nur noch Verlauf uebrig.
    Dazu kam, dass Whisper ohnehin bei 223 TOKEN abschneidet, nicht bei
    700 Zeichen -- gekuerzt wurde also an der falschen Stelle und nach
    dem falschen Mass.

    Jetzt gilt eine Rangfolge:

      1. DER KOPF BLEIBT. Einleitung und Thema stehen immer drin.
      2. Dann die Namen, von hinten gekuerzt. Sie sind nach Seltenheit
         sortiert -- hinten stehen die, die Whisper ohnehin trifft.
      3. Dann der Verlauf, von vorn gekuerzt: der juengste Satz sagt am
         meisten darueber, wie es weitergeht.

    Gemessen wird mit dem Tokenizer des eingesetzten Modells, nicht in
    Zeichen. `zaehlen` ist eine Funktion Text -> Tokenzahl.

    Passt nicht einmal der Kopf, wird er wortweise gekuerzt. Das ist
    der Notfall und sollte nie eintreten: PROMPT_MAX_ZEICHEN ist so
    gewaehlt, dass Kopf und Namen zusammen hineinpassen."""
    kopf = (kopf or "").strip()
    namen = list(namen or [])
    verlauf = [v for v in (verlauf or []) if v and v.strip()]

    if zaehlen(kopf) > grenze:
        worte = kopf.split()
        while worte and zaehlen(" ".join(worte)) > grenze:
            worte.pop()
        return " ".join(worte)

    def zusammen(n, v):
        teile = [kopf]
        if n:
            teile.append("Namen: " + ", ".join(n) + ".")
        teile.extend(v)
        return " ".join(teile)

    # Erst die Namen von hinten, bis Kopf plus Namen passen.
    while namen and zaehlen(zusammen(namen, [])) > grenze:
        namen.pop()
    # Dann den Verlauf von vorn auffuellen, juengster Satz zuerst.
    genommen = []
    for satz in reversed(verlauf):
        versuch = [satz] + genommen
        if zaehlen(zusammen(namen, versuch)) > grenze:
            break
        genommen = versuch
    return zusammen(namen, genommen)


def aus_pulttext(text, index, einleitung, max_zeichen, zusatznamen=None):
    """Ein Aufruf fuer den Server: Text vom Pult rein, Prompt raus.

    zusatznamen stammen aus einem hochgeladenen Manuskript. Sie stehen
    vorn, weil sie garantiert vorkommen, waehrend die Namen aus einem
    Bibelkapitel nur vorkommen koennten."""
    stellen, bereiche = stellen_mit_bereichen(text)
    namen = list(zusatznamen or [])
    for n in index.fuer_stellen(stellen):
        if n not in namen:
            namen.append(n)
    # Die ERKANNTEN Stellenangaben aus dem Freitext nehmen: die Buchnamen
    # stehen gleich als Namen im Prompt und wuerden sonst doppelt Platz
    # kosten. Was NICHT erkannt wurde, bleibt stehen -- sonst
    # verschwindet es aus dem Thema, ohne dafuer irgendwo aufzutauchen.
    rest, ende = [], 0
    for a, b in bereiche:
        rest.append(text[ende:a])
        ende = b
    rest.append(text[ende:])
    freitext = _freitext_saeubern(" ".join(rest))
    prompt, drin = prompt_bauen(freitext, namen, einleitung, max_zeichen)
    # Der Kopf getrennt, damit hoeren() ihn beim Kuerzen schuetzen kann.
    kopf = einleitung.strip()
    if freitext.strip():
        kopf += " " + freitext.strip().rstrip(".") + "."
    return {"prompt": prompt, "kopf": kopf, "stellen": stellen,
            "namen": drin, "namen_gefunden": len(namen)}


def main():
    if len(sys.argv) < 2:
        sys.exit('Aufruf: python bibelstellen.py "1. Samuel 15, Matthäus 18"')
    import config
    text = " ".join(sys.argv[1:])
    index = Namensindex.laden(config.BASIS / "namen_block_b.csv")
    if not index.eintraege:
        print("namen_block_b.csv fehlt. Erst namen_aus_bibel.py laufen lassen.\n")

    erg = aus_pulttext(text, index, config.PROMPT_EINLEITUNG,
                       config.PROMPT_MAX_ZEICHEN)
    print(f"Eingabe:  {text}")
    print(f"Stellen:  {', '.join(erg['stellen']) or 'keine erkannt'}")
    print(f"Namen:    {erg['namen_gefunden']} gefunden, "
          f"{len(erg['namen'])} passen in den Prompt")
    print(f"\nPrompt ({len(erg['prompt'])} Zeichen, "
          f"ca. {len(erg['prompt'])//3}-{len(erg['prompt'])//2} Token):\n")
    print(erg["prompt"])


if __name__ == "__main__":
    main()
