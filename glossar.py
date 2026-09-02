# -*- coding: utf-8 -*-
"""Laedt das Glossar und findet Begriffe in deutschem Text.

Matching-Regeln, die hier wichtig sind:

1. Longest-Match-First. "Heiliger Geist" muss vor "Geist" greifen,
   "Gnadenzeit" vor "Gnade", "1. Johannes" vor "Johannes".
2. Wortanfang auf Wortgrenze, am Ende nur eine geschlossene Liste deutscher
   Flexionsendungen. Ein offenes \\w* waere zu gierig: "Herz" wuerde dann in
   "herzlich willkommen" treffen und faelschlich die Terminologie fuer das
   biblische Herz erzwingen. Der Preis ist, dass Komposita wie "Sabbatgebot"
   nicht automatisch gefunden werden; solche Faelle gehoeren als eigene
   Suchvariante ins Glossar.
3. Ueberlappungsschutz. Ein Textabschnitt wird nur einmal belegt, damit
   ein bereits von "Heiliger Geist" belegter Bereich nicht nochmal von
   "Geist" beansprucht wird.
"""

import csv
import re
from dataclasses import dataclass, field

# Deutsche Flexionsendungen, die an eine Glossarvariante angehaengt sein
# duerfen. Bewusst geschlossen und nicht \w*, siehe Modulkommentar.
# Laengste zuerst, damit die Alternation gierig genug greift.
FLEXION = r"(?:ern|en|es|er|em|e|n|s)?"


def stamm(wort):
    """Kappt die Flexionsendung grob: das letzte Viertel entfaellt,
    mindestens vier Zeichen bleiben stehen.

    Grob, aber sprachunabhaengig. Fuer flektierende Sprachen ist das der
    Unterschied zwischen Treffer und Fehlschlag, und eine Endungsliste je
    Sprache waere nicht zu pflegen."""
    return wort[:max(4, int(len(wort) * 0.75))]


@dataclass
class Eintrag:
    id: str
    block: str
    typ: str          # "hart" oder "weich"
    stt: bool
    de: str
    varianten: list
    ziel: dict        # {"en": ..., "ru": ..., "fa": ...}
    konfidenz: dict   # {"en": 3, "ru": 3, "fa": 1}
    vokal: str = ""   # persische Form mit Vokalzeichen, nur fuer die Stimme
    anmerkung: str = ""


@dataclass
class Glossar:
    eintraege: list = field(default_factory=list)
    _muster: list = field(default_factory=list, repr=False)

    @classmethod
    def laden(cls, pfad):
        eintraege = []
        with open(pfad, encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh, delimiter=";"):
                eintraege.append(Eintrag(
                    id=r["id"], block=r["block"], typ=r["typ"],
                    stt=r["stt"] == "1", de=r["de"],
                    varianten=[v.strip() for v in r["suchvarianten"].split("|") if v.strip()],
                    ziel={k: r[k] for k in ("en", "ru", "fa")},
                    vokal=r.get("fa_vokal", ""),
                    konfidenz={k: int(r["k_" + k]) for k in ("en", "ru", "fa")},
                    anmerkung=r["anmerkung"]))

        g = cls(eintraege=eintraege)
        muster = []
        for e in eintraege:
            for v in e.varianten:
                muster.append((len(v),
                               re.compile(r"\b" + re.escape(v) + FLEXION + r"\b",
                                          re.IGNORECASE),
                               e))
        muster.sort(key=lambda x: -x[0])   # laengste Variante zuerst
        g._muster = muster
        return g

    def finde_in(self, text, quelle, nur_hart=False):
        """Sucht Glossarbegriffe in einem Text der angegebenen Quellsprache.

        Fuer Deutsch stehen gepflegte Suchvarianten bereit. Fuer andere
        Quellsprachen gibt es die nicht, und sie waeren auch kaum zu
        pflegen: Ukrainisch hat sieben Faelle, dazu Zahl und Geschlecht.
        Stattdessen wird der Zieleintrag der Quellsprache auf seinen Stamm
        gekuerzt und als Wortanfang gesucht. Das ist unschaerfer als die
        deutsche Variantenliste, aber es erfasst die Flexion, ohne sie
        aufzuzaehlen.

        Dasselbe Verfahren hat schon bei der Auswertung gefehlt: dort galt
        russisches "благодати" im Dativ nicht als Treffer fuer
        "благодать", und die Messung lag um 40 Punkte daneben."""
        if quelle == "de" or quelle is None:
            return self.finde(text, nur_hart)

        woerter = re.findall(r"\w+", text.lower(), re.UNICODE)
        treffer = []
        for e in self.eintraege:
            if nur_hart and e.typ != "hart":
                continue
            begriff = e.de if quelle == "de" else e.ziel.get(quelle, "").strip()
            if not begriff:
                continue
            teile = [t for t in re.findall(r"\w+", begriff.lower(), re.UNICODE)
                     if len(t) > 2]
            if not teile:
                continue
            if all(any(w.startswith(stamm(t)) for w in woerter) for t in teile):
                treffer.append(e)
        return treffer

    def finde(self, text, nur_hart=False):
        """Gibt die im Text vorkommenden Eintraege zurueck, ohne Dubletten,
        in der Reihenfolge ihres ersten Auftretens im Text."""
        belegt = []
        treffer = {}
        for _, pat, e in self._muster:
            if e.id in treffer:
                continue
            if nur_hart and e.typ != "hart":
                continue
            for m in pat.finditer(text):
                if any(not (m.end() <= a or m.start() >= b) for a, b in belegt):
                    continue
                belegt.append((m.start(), m.end()))
                treffer[e.id] = (m.start(), e)
                break
        return [e for _, e in sorted(treffer.values(), key=lambda x: x[0])]

    def stt_begriffe(self, bloecke=("D", "C", "A")):
        """Begriffe fuer den Whisper-initial_prompt: nur die, bei denen
        Verhoeren wahrscheinlich ist, in der Reihenfolge der uebergebenen
        Bloecke. Beim Kuerzen faellt hinten weg, deshalb steht das
        Wichtigste vorn."""
        rang = {b: i for i, b in enumerate(bloecke)}
        kandidaten = [e for e in self.eintraege if e.stt and e.block in rang]
        kandidaten.sort(key=lambda e: (rang[e.block], e.id))
        return [e.de for e in kandidaten]


def prompt_bauen(glossar, rahmen, max_zeichen, bloecke=("D", "C", "A")):
    """Fuellt den Prompt bis zum Zeichenbudget auf.

    Whisper schneidet den initial_prompt bei 224 Token hart ab. Deutsch
    tokenisiert ungefuenstig (Umlaute, Komposita), grob 2,5 bis 3 Zeichen
    je Token. Ueber die Anzahl der Begriffe zu begrenzen greift deshalb
    daneben, sobald lange Begriffe wie "Vorabschliessendes Gericht"
    dabei sind. Darum wird nach Zeichen begrenzt."""
    alle = glossar.stt_begriffe(bloecke)
    genommen = []
    for b in alle:
        kandidat = rahmen.format(begriffe=", ".join(genommen + [b]))
        if len(kandidat) > max_zeichen:
            break
        genommen.append(b)
    return rahmen.format(begriffe=", ".join(genommen)), len(genommen), len(alle)


def glossarzeilen(eintraege, sprache, quelle="de"):
    """Formatiert gefundene Eintraege als Terminologievorgabe fuer ein LLM.
    Harte Eintraege werden als Vorgabe formuliert, weiche als Hinweis."""
    def wort(eintrag, sp):
        # Deutsch steht in der Grundspalte, nicht in den Zielspalten. Ohne
        # diese Unterscheidung liefert die Vorgabe nichts, sobald Deutsch
        # die Zielsprache ist, also genau im Fall einer fremdsprachigen
        # Predigt mit deutscher Uebersetzung.
        return eintrag.de if sp == "de" else eintrag.ziel.get(sp, "").strip()

    hart, weich = [], []
    for e in eintraege:
        ziel = wort(e, sprache)
        if not ziel:
            continue
        # Als Ausgangsbegriff das Wort der Quellsprache nennen, nicht das
        # deutsche: bei einer ukrainischen Predigt hilft dem Modell
        # "Rechtfertigung" nichts, es sieht ja das ukrainische Wort.
        von = wort(e, quelle) or e.de
        (hart if e.typ == "hart" else weich).append(f"{von} = {ziel}")
    teile = []
    if hart:
        teile.append("Verbindliche Terminologie: " + "; ".join(hart))
    if weich:
        teile.append("Im theologischen Sinn zu verstehen: " + "; ".join(weich))
    return "\n".join(teile)


def vokalisieren(glossar, text):
    """Setzt in einem persischen Text die Vokalzeichen der Glossarbegriffe.

    Warum ueberhaupt: Persisch schreibt kurze Vokale nicht. Piper muss die
    Aussprache also raten und liegt bei mehrdeutigen Woertern daneben. In
    einem Test wurde koshti (Ringen) als kashti (Schiff) gesprochen, weil
    beides كشتی geschrieben wird. Mit Vokalzeichen ist der Fall eindeutig.

    Warum nur die Glossarbegriffe: eine vollstaendige automatische
    Diakritisierung waere ein eigener Verarbeitungsschritt mit eigener
    Fehlerquelle und eigener Latenz. Die Fachbegriffe sind genau die Stellen,
    an denen ein Fehler weh tut, und fuer sie liegen gepruefte Formen vor.

    Ersetzt wird laengster Treffer zuerst, damit bei mehrwortigen Begriffen
    nicht ein Bestandteil einzeln erwischt wird."""
    if not text:
        return text
    paare = sorted(
        ((e.ziel.get("fa", "").strip(), e.vokal.strip())
         for e in glossar.eintraege if e.vokal.strip()),
        key=lambda p: -len(p[0]))
    for ohne, mit in paare:
        if ohne and ohne in text:
            text = text.replace(ohne, mit)
    return text
