#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Baut die Umrechnungstabelle fuer Bibelstellen-Zaehlungen.

    python werkzeuge/zaehlung_bauen.py                 (Trockenlauf, holt)
    python werkzeuge/zaehlung_bauen.py --scharf        schreibt zaehlung.json
    python werkzeuge/zaehlung_bauen.py --aus /tmp/b    aus einem Zwischenlager

WORUM ES GEHT

Die Schlachter 2000 zaehlt wie der hebraeische Text. Die Bibeln der
Zuhoerer zaehlen oft anders, und dann steht im Untertitel eine Stelle,
die es in der Bibel auf dem Schoss des Zuhoerers nicht gibt.

  Schlachter Joel 3,1       heisst englisch Joel 2:28
  Schlachter Maleachi 3,23  heisst englisch Malachi 4:5
  Schlachter Psalm 51,12    heisst englisch Psalm 51:10
  Schlachter Psalm 23       heisst russisch Psalom 22

DIE DATENGRUNDLAGE -- UND WARUM SIE AUS ZAEHLUNGEN KOMMT

Gezaehlt wird, nicht geraten. Verglichen werden die VERSZAHLEN je
Kapitel aus drei Uebersetzungen, die ueber api.getbible.net frei
abrufbar sind:

    schlachter   Schlachter (1951)           -- die hebraeische Zaehlung
    kjv          King James Version          -- die englische
    synodal      Synodal-Uebersetzung (1876) -- die russische

Gespeichert werden ausschliesslich ZAHLEN: Kapitel, Vers, Versatz. Kein
Bibeltext. Zahlen sind Fakten und kein Werk; dasselbe gilt schon fuer
namen_block_b.csv, siehe LIZENZEN.md. Die Rechtsstaende sind verschieden -- Synodal 1876 ist Public Domain,
die KJV steht unter GPL, die SCHLACHTER 1951 ist NICHT gemeinfrei
(Copyright Genfer Bibelgesellschaft, "free non-commercial
distribution"). Darauf kommt es hier nicht an: das Projekt uebernimmt
von keiner eine Zeile. Siehe LIZENZEN.md.

Dass die Zaehlung der Schlachter **2000** mit der von 1951 uebereinstimmt,
ist an den vier Beispielen oben geprueft; beide folgen dem
masoretischen Text.

WAS UMGERECHNET WIRD -- UND WAS AUSDRUECKLICH NICHT

Umgerechnet wird nur, wo die Regel aus den Zahlen EINDEUTIG folgt:

  1. PSALMENVERSATZ (englische Zaehlung). Die hebraeische Zaehlung
     zaehlt die Ueberschrift als Vers, die englische nicht. Der
     Versatz gilt dann fuer den ganzen Psalm. Nachgezaehlt: 62 von 150
     Psalmen haben einen Versatz, und zwar ausschliesslich 1 oder 2 --
     genau die Laenge einer Ueberschrift. Nichts anderes kommt vor,
     und nichts anderes wird uebernommen.
  2. PSALMENNUMMER (russische Zaehlung). Die Synodalbibel folgt der
     Septuaginta. Die Abbildung ist dokumentiert und wird hier an den
     Verszahlen nachgeprueft: Hebraeisch 9+10 wird Synodal 9 (21+18=39
     Verse, und Synodal 9 hat 39), Hebraeisch 114+115 wird Synodal 113
     (26 gegen 26). Uebernommen werden nur die 1:1-Verschiebungen, bei
     denen die Verszahl UEBEREINSTIMMT.
  3. JOEL und MALEACHI. Dort weicht die Kapitelzahl ab, nicht nur die
     Verszahl: Schlachter hat Joel 1-4 und Maleachi 1-3, KJV und
     Synodal haben Joel 1-3 und Maleachi 1-4. Die Grenzen folgen aus
     den Verszahlen (Joel: 27+5 = 32; Maleachi: 18+6 = 24).

NICHT umgerechnet wird alles andere. In 29 weiteren Buechern weichen
einzelne Verszahlen ab -- aber eine abweichende Verszahl heisst nicht,
dass die Zaehlung verschoben ist. Oft ist mitten im Kapitel ein Vers
geteilt oder zusammengezogen, und dann gilt der Versatz nur fuer einen
Teil des Kapitels. Welchen, sagt die Verszahl nicht. Darum bleiben
diese Stellen, wie sie sind: lieber die Angabe der Schlachter als eine
falsche.

Ebenso bleibt Persisch unangetastet: welche Zaehlung die persischen
Bibeln benutzen, ist hier nicht belegt.
"""

import argparse
import json
import sys
import urllib.request
from datetime import date
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))

ZIEL = WURZEL / "zaehlung.json"
API = "https://api.getbible.net/v2"
QUELLEN = {"de": "schlachter", "en": "kjv", "ru": "synodal"}

GRUEN, ROT, GELB, BLAU, AUS = (
    "\033[32m", "\033[31m", "\033[33m", "\033[1;34m", "\033[0m")

PSALMEN = 19
JOEL = 29
MALEACHI = 39


def blau(t):
    print(f"\n{BLAU}== {t}{AUS}")


def gut(t):
    print(f"   {GRUEN}ok{AUS}   {t}")


def warn(t):
    print(f"   {GELB}!{AUS}    {t}")


def verszahlen(kuerzel, lager=None):
    """{Buchnummer: [Verse je Kapitel]} -- nur Zahlen, kein Text."""
    aus = {}
    for n in range(1, 67):
        if lager:
            d = json.loads((Path(lager) / kuerzel / f"{n}.json")
                           .read_text(encoding="utf-8"))
        else:
            with urllib.request.urlopen(f"{API}/{kuerzel}/{n}.json",
                                        timeout=60) as a:
                d = json.loads(a.read().decode("utf-8"))
        aus[n] = [len(c["verses"]) for c in d["chapters"]]
    return aus


def psalmen_versatz(de, en):
    """{Psalm: Versatz} fuer die englische Zaehlung.

    Nur 1 und 2 werden uebernommen. Ein anderer Wert waere kein
    Ueberschriftsversatz, sondern etwas, das diese Zahlen nicht
    erklaeren -- und dann wird nicht umgerechnet."""
    regeln, verworfen = {}, []
    for i, (a, b) in enumerate(zip(de[PSALMEN], en[PSALMEN]), 1):
        v = a - b
        if v == 0:
            continue
        if v in (1, 2):
            regeln[i] = v
        else:
            verworfen.append((i, v))
    return regeln, verworfen


def psalmen_nummer(de, ru):
    """{Hebraeischer Psalm: Synodal-Psalm} -- nur die eindeutigen.

    Die Abbildung ist dokumentiert (Septuaginta-Zaehlung). Hier wird
    sie an den Verszahlen nachgeprueft und nur dort uebernommen, wo
    ein Psalm GANZ auf einen anderen fuehrt und die Verszahl stimmt.
    Zusammengelegte und geteilte Psalmen (9+10, 114+115, 116, 147)
    bleiben draussen: dort verschiebt sich auch der Vers, und zwar
    nicht um einen festen Wert."""
    plan = {}
    for h in range(1, 9):
        plan[h] = h
    for h in range(11, 114):
        plan[h] = h - 1
    for h in range(117, 147):
        plan[h] = h - 1
    for h in range(148, 151):
        plan[h] = h
    regeln, verworfen = {}, []
    for h, sy in sorted(plan.items()):
        if h == sy:
            continue                      # nichts umzurechnen
        if de[PSALMEN][h - 1] == ru[PSALMEN][sy - 1]:
            regeln[h] = sy
        else:
            verworfen.append((h, sy, de[PSALMEN][h - 1], ru[PSALMEN][sy - 1]))
    return regeln, verworfen


def buch_regeln(de, ziel, buch):
    """Joel und Maleachi: die Kapitelgrenze aus den Verszahlen.

    Nur wenn die Zahlen zusammengehen, entsteht eine Regel. Gehen sie
    nicht zusammen, entsteht keine -- und die Stelle bleibt, wie sie
    ist."""
    d, z = de[buch], ziel[buch]
    regeln = []
    if buch == JOEL and len(d) == 4 and len(z) == 3 \
            and d[1] + d[2] == z[1] and d[3] == z[2]:
        # Schlachter 3,v gehoert hinten an das zweite Kapitel.
        regeln.append({"kap": 3, "vers_von": 1, "vers_bis": d[2],
                       "ziel_kap": 2, "vers_plus": d[1]})
        regeln.append({"kap": 4, "vers_von": 1, "vers_bis": d[3],
                       "ziel_kap": 3, "vers_plus": 0})
    if buch == MALEACHI and len(d) == 3 and len(z) == 4 \
            and z[2] + z[3] == d[2]:
        regeln.append({"kap": 3, "vers_von": 1, "vers_bis": z[2],
                       "ziel_kap": 3, "vers_plus": 0})
        regeln.append({"kap": 3, "vers_von": z[2] + 1, "vers_bis": d[2],
                       "ziel_kap": 4, "vers_plus": -z[2]})
    return regeln


def main():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--scharf", action="store_true")
    p.add_argument("--aus", help="Ordner mit <kuerzel>/<nr>.json")
    a = p.parse_args()

    blau("Verszahlen holen")
    zahlen = {}
    for sprache, kuerzel in QUELLEN.items():
        zahlen[sprache] = verszahlen(kuerzel, a.aus)
        gut(f"{kuerzel}: 66 Buecher, "
            f"{sum(len(v) for v in zahlen[sprache].values())} Kapitel")
    de = zahlen["de"]

    daten = {
        "gebaut_am": date.today().isoformat(),
        "quelle": {
            "dienst": API,
            "de": "schlachter (Schlachter 1951) -- hebraeische Zaehlung",
            "en": "kjv (King James Version) -- englische Zaehlung",
            "ru": "synodal (Synodal 1876) -- Septuaginta-Zaehlung",
        },
        "hinweis": "Nur Zahlen, kein Bibeltext. Gebaut von "
                   "werkzeuge/zaehlung_bauen.py; die Begruendung jeder "
                   "Regel steht dort im Modulkommentar.",
        "zaehlungen": {},
    }

    for ziel_name, sprache in (("en", "en"), ("ru", "ru")):
        blau(f"Zaehlung {ziel_name}")
        ziel = zahlen[sprache]
        z = {"psalm_versatz": {}, "psalm_nummer": {}, "buecher": {}}

        if ziel_name == "en":
            versatz, verworfen = psalmen_versatz(de, ziel)
            z["psalm_versatz"] = {str(k): v for k, v in versatz.items()}
            gut(f"{len(versatz)} Psalmen mit Ueberschriftsversatz "
                f"(1 oder 2)")
            if verworfen:
                warn(f"{len(verworfen)} Psalmen verworfen: {verworfen}")
        else:
            nummern, verworfen = psalmen_nummer(de, ziel)
            z["psalm_nummer"] = {str(k): v for k, v in nummern.items()}
            gut(f"{len(nummern)} Psalmen mit anderer Nummer")
            if verworfen:
                warn(f"{len(verworfen)} nicht eindeutig, bleiben: "
                     f"{[v[0] for v in verworfen]}")

        for buch in (JOEL, MALEACHI):
            regeln = buch_regeln(de, ziel, buch)
            if regeln:
                z["buecher"][str(buch)] = regeln
                gut(f"Buch {buch}: {len(regeln)} Regeln")
            else:
                warn(f"Buch {buch}: keine Regel -- die Zahlen gehen "
                     f"nicht zusammen, es bleibt, wie es ist.")
        daten["zaehlungen"][ziel_name] = z

    blau("Probe")
    import zaehlung
    tab = zaehlung.Tabelle(daten)
    faelle = [(JOEL, 3, 1, "en", (2, 28)),
              (MALEACHI, 3, 23, "en", (4, 5)),
              (PSALMEN, 51, 12, "en", (51, 10)),
              (PSALMEN, 23, None, "ru", (22, None)),
              (43, 3, 16, "en", None),
              (43, 3, 16, "ru", None)]
    schief = 0
    for buch, kap, vers, ziel_name, soll in faelle:
        ist = tab.umrechnen(buch, kap, vers, ziel_name)
        marke = GRUEN + "ok  " + AUS if ist == soll else ROT + "FEHL" + AUS
        if ist != soll:
            schief += 1
        print(f"   {marke} Buch {buch} {kap},{vers} -> {ziel_name}: "
              f"{ist} (erwartet {soll})")
    if schief:
        print(f"\n{ROT}{schief} Proben schief. Nichts geschrieben.{AUS}")
        return 1

    if not a.scharf:
        print()
        warn("TROCKENLAUF. Nichts geschrieben.")
        warn(f"Schreiben mit  --scharf   (nach {ZIEL.name})")
        return 0
    ZIEL.write_text(json.dumps(daten, ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8")
    print()
    gut(f"{ZIEL.name} geschrieben")
    return 0


if __name__ == "__main__":
    sys.exit(main())
