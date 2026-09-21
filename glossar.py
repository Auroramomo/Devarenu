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


def sprachen_aus_kopf(spalten):
    """Welche Spalten des Glossars sind Zielsprachen?

    Die, zu denen es eine Konfidenzspalte gibt: "en" ist eine Sprache,
    weil "k_en" danebensteht. "de" nicht -- Deutsch steht in der
    Grundspalte und hat keine Konfidenz. "fa_vokal" nicht -- es gibt
    kein "k_fa_vokal", es ist eine Schreibweise, keine Sprache.

    Aus dem Kopf gelesen und nicht fest verdrahtet: eine neue Sprache
    soll durch zwei Spalten in der CSV entstehen, nicht durch eine
    Aenderung hier. Frueher standen ("en", "ru", "fa") im Code, und wer
    eine Spalte ergaenzte, bekam sie lautlos nicht zu sehen.

    Die Reihenfolge ist die des Kopfes, damit die Ausgabe stabil bleibt.
    """
    if not spalten:
        return ()
    vorhanden = {s for s in spalten if s}
    return tuple(s for s in spalten
                 if s and not s.startswith("k_") and "k_" + s in vorhanden)


def _zahl(wert):
    """Konfidenz als Zahl. Fehlt sie oder steht Unsinn darin, gilt 0.

    Vorher stand hier int() ohne Netz. Fuer die gepflegten Spalten war
    das folgenlos -- alle Zellen sind gefuellt --, beim Anlegen einer
    neuen Sprache waeren leere Zellen aber der Normalfall, und das
    Glossar liesse sich dann gar nicht mehr laden."""
    try:
        return int(str(wert).strip())
    except (TypeError, ValueError):
        return 0


# Die Zielsprachen der zuletzt geladenen Datei, und welche fehlenden
# schon gemeldet wurden. Modulweit, weil es das Glossar im Prozess genau
# einmal gibt: server.py laedt es beim Start und haelt es danach.
_SPRACHEN = ()
_QUELLE = ""
_GEMELDET = set()


@dataclass
class Glossar:
    eintraege: list = field(default_factory=list)
    # Die Zielsprachen laut CSV-Kopf, in dessen Reihenfolge.
    sprachen: tuple = ()
    _muster: list = field(default_factory=list, repr=False)

    @classmethod
    def laden(cls, pfad):
        global _SPRACHEN, _QUELLE, _GEMELDET
        eintraege = []
        with open(pfad, encoding="utf-8-sig", newline="") as fh:
            leser = csv.DictReader(fh, delimiter=";")
            sprachen = sprachen_aus_kopf(leser.fieldnames)
            for r in leser:
                eintraege.append(Eintrag(
                    id=r["id"], block=r["block"], typ=r["typ"],
                    stt=r["stt"] == "1", de=r["de"],
                    varianten=[v.strip() for v in r["suchvarianten"].split("|") if v.strip()],
                    ziel={k: r[k] for k in sprachen},
                    vokal=r.get("fa_vokal", ""),
                    konfidenz={k: _zahl(r.get("k_" + k)) for k in sprachen},
                    anmerkung=r["anmerkung"]))

        _SPRACHEN = sprachen
        _QUELLE = str(pfad)
        # Nach einem Neuladen darf erneut gemeldet werden: die Spalten
        # koennen andere sein als vorher.
        _GEMELDET = set()
        g = cls(eintraege=eintraege, sprachen=sprachen)
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
        Quellsprachen waeren sie kaum zu pflegen -- Ukrainisch hat sieben
        Faelle, dazu Zahl und Geschlecht. Stattdessen wird der Zieleintrag
        auf seinen Stamm gekuerzt und als Wortanfang gesucht: unschaerfer,
        erfasst die Flexion aber, ohne sie aufzuzaehlen.

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


def _fehlende_spalte_melden(sprache, quelle):
    """Sagt einmal je Lauf Bescheid, wenn eine Zielsprache keine Spalte hat.

    Ohne das laeuft sie lautlos ohne Terminologie mit: glossarzeilen
    liefert dann eine leere Zeichenkette, der Prompt bekommt keinen
    Wortwahlblock, und niemand sieht es -- weder am Pult noch im Log.
    Gemessen an einem Predigtteil mit 17 Glossarbegriffen: fuer Englisch
    428 Zeichen Vorgabe, fuer eine Sprache ohne Spalte nichts.

    Geprueft wird gegen den CSV-Kopf und NICHT gegen die gefundenen
    Eintraege. Ein Abschnitt ohne Glossartreffer wuerde sonst schweigen,
    obwohl die Spalte genauso fehlt.

    Deutsch und die Quellsprache sind ausgenommen: Deutsch steht in der
    Grundspalte, und die Quellsprache ist die Seite, von der uebersetzt
    wird, nicht die, fuer die ein Begriff nachzuschlagen waere.

    Einmal je Lauf und nicht je Abschnitt: im Gottesdienst kaemen sonst
    tausend gleiche Zeilen, und was sich endlos wiederholt, liest
    niemand mehr."""
    if not _SPRACHEN or sprache in _SPRACHEN:
        return
    if sprache == "de" or sprache == quelle or sprache in _GEMELDET:
        return
    _GEMELDET.add(sprache)
    print(f"GLOSSAR: Fuer '{sprache}' gibt es keine Spalte in "
          f"{_QUELLE or 'der Glossardatei'}.")
    print(f"  Diese Sprache wird OHNE Fachwortverzeichnis uebersetzt. "
          f"Vorhanden: {', '.join(_SPRACHEN)}.")
    print(f"  Zum Ergaenzen: zwei Spalten anlegen, '{sprache}' und "
          f"'k_{sprache}'.")


def glossarzeilen(eintraege, sprache, quelle="de"):
    """Formatiert gefundene Eintraege als Terminologievorgabe fuer ein LLM.
    Harte Eintraege werden als Vorgabe formuliert, weiche als Hinweis."""
    _fehlende_spalte_melden(sprache, quelle)

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

    Persisch schreibt kurze Vokale nicht, Piper muss die Aussprache also
    raten. Im Test wurde koshti (Ringen) als kashti (Schiff) gesprochen,
    weil beides كشتی geschrieben wird; mit Vokalzeichen ist es eindeutig.

    Nur die Glossarbegriffe, weil eine vollstaendige Diakritisierung ein
    eigener Verarbeitungsschritt mit eigener Fehlerquelle und Latenz
    waere. Bei den Fachbegriffen tut ein Fehler weh, und fuer sie liegen
    gepruefte Formen vor.

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
