#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bibelstellen in der Zählung der Zielsprache.

    python pruefstand/zaehlung_test.py

Die Schlachter 2000 zählt wie der hebräische Text, die Bibeln der
Zuhörer oft anders. Steht im Untertitel „Joel 3,1", sucht ein
englischsprachiger Zuhörer eine Stelle, die seine Bibel nicht hat —
dort heißt sie Joel 2:28.

Umgerechnet wird nur, wo die Regel aus nachgezählten Verszahlen
eindeutig folgt. Dieser Lauf prüft beides: dass die bekannten Fälle
stimmen UND dass alles andere unangetastet bleibt. Das Zweite ist das
Wichtigere — eine falsch umgerechnete Stelle ist schlechter als eine
nicht umgerechnete.
"""

import csv
import io
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))

import config                                  # noqa: E402
import zaehlung                                 # noqa: E402
import bibelstellen as b                        # noqa: E402
from namen_aus_bibel import BUECHER             # noqa: E402

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


T = zaehlung.Tabelle.laden()

titel("1) Die Tabelle ist da und sagt, woher sie kommt")

pruefe("zaehlung.json liegt im Repo", True, (WURZEL / "zaehlung.json").exists())
pruefe("sie ist geladen", True, T.vorhanden)
pruefe("sie nennt ihre Quelle", True, bool(T.daten.get("quelle")))
# Nur Zahlen. Kein Bibeltext -- der darf aus Urheberrechtsgruenden
# nicht ins Repo, und er wird hier auch nicht gebraucht.
roh = (WURZEL / "zaehlung.json").read_text(encoding="utf-8")
pruefe("sie enthält keinen Bibeltext", True, len(roh) < 20000)

titel("2) Die Buchnummern stimmen mit dem Glossar überein")

# zaehlung.json spricht in Buchnummern, bibelstellen.py rechnet sie
# aus der Reihenfolge von BUECHER. Laufen die auseinander, rechnet die
# Tabelle am falschen Buch.
g = [z for z in csv.DictReader(
    io.open(WURZEL / config.GLOSSAR_CSV.name, encoding="utf-8-sig",
            newline=""), delimiter=";") if z["block"] == "A"]
pruefe("66 Bibelbücher im Glossar", 66, len(g))
pruefe("dieselbe Reihenfolge wie BUECHER", [],
       [(i + 1, z["de"], buch) for i, (z, buch) in enumerate(zip(g, BUECHER))
        if z["de"] != buch])
pruefe("Psalmen ist Buch 19", 19, list(BUECHER).index("Psalmen") + 1)
pruefe("Joel ist Buch 29", 29, list(BUECHER).index("Joel") + 1)
pruefe("Maleachi ist Buch 39", 39, list(BUECHER).index("Maleachi") + 1)

titel("3) Die belegten Fälle")


def um(text, sprache):
    """Wie der Server es tut: Stelle finden, umrechnen, Namen holen."""
    aus = []
    welche = zaehlung.ZAEHLUNG_JE_SPRACHE.get(sprache)
    if not welche:
        return aus
    for nummer, buch, kap, vers, quell, _ in b.stellen_mit_versen(text):
        neu = T.umrechnen(nummer, kap, vers, welche)
        if not neu or neu == (kap, vers):
            continue
        name = zaehlung.ZITATNAME.get(nummer, {}).get(sprache)
        if not name:
            treffer = [z for z in g if z["de"] == buch]
            name = (treffer[0][sprache].strip() if treffer else "") or buch
        aus.append((quell, name, neu[0], neu[1]))
    return aus


pruefe("Joel 3,1 -> en Joel 2:28", [("Joel 3,1", "Joel", 2, 28)],
       um("Joel 3,1", "en"))
pruefe("Maleachi 3,23 -> en Malachi 4:5",
       [("Maleachi 3,23", "Malachi", 4, 5)], um("Maleachi 3,23", "en"))
pruefe("Psalm 51,12 -> en Psalm 51:10",
       [("Psalm 51,12", "Psalm", 51, 10)], um("Psalm 51,12", "en"))
pruefe("Psalm 23 -> ru Псалом 22",
       [("Psalm 23", "Псалом", 22, None)], um("Psalm 23", "ru"))
# Joel und Maleachi gelten auch fuer Russisch: die Synodalbibel hat
# dort dieselbe Kapiteleinteilung wie die KJV.
pruefe("Joel 3,1 -> ru Иоиль 2,28", [("Joel 3,1", "Иоиль", 2, 28)],
       um("Joel 3,1", "ru"))
# Und fuer Spanisch und Portugiesisch, die der englischen folgen.
pruefe("Maleachi 3,23 -> es Malaquías 4:5",
       [("Maleachi 3,23", "Malaquías", 4, 5)], um("Maleachi 3,23", "es"))
pruefe("Joel 4,5 -> pt Joel 3,5", [("Joel 4,5", "Joel", 3, 5)],
       um("Joel 4,5", "pt"))

titel("4) Was unangetastet bleibt -- der wichtigere Teil")

pruefe("Johannes 3,16 bleibt en", [], um("Johannes 3,16", "en"))
pruefe("Johannes 3,16 bleibt ru", [], um("Johannes 3,16", "ru"))
pruefe("Johannes 3,16 bleibt es", [], um("Johannes 3,16", "es"))
# Persisch ist nicht belegt. Keine Umrechnung, auch nicht bei Joel.
pruefe("fa bleibt unberührt, auch bei Joel", [], um("Joel 3,1", "fa"))
pruefe("fa steht in keiner Zuordnung", False,
       "fa" in zaehlung.ZAEHLUNG_JE_SPRACHE)
# Eine Spanne hat kein einzelnes Gegenstueck.
pruefe("eine Versspanne bleibt", [], um("Joel 3,1-5", "en"))
pruefe("eine Kapitelspanne bleibt", [], um("Joel 3-4", "en"))
# Der Vers IST die Ueberschrift: englisch gibt es ihn nicht.
pruefe("Psalm 51,1 hat kein Gegenstück", [], um("Psalm 51,1", "en"))
pruefe("Psalm 51,2 auch nicht", [], um("Psalm 51,2", "en"))
# Schlachter Maleachi 3 verteilt sich auf zwei Kapitel -- ohne Vers
# ist nicht zu sagen, auf welches.
pruefe("Maleachi 3 ohne Vers bleibt", [], um("Maleachi 3", "en"))
# Ein Psalm, bei dem die Verszahlen nicht zusammengehen, bleibt.
pruefe("Psalm 142 bleibt ru (Verszahlen gehen nicht zusammen)", [],
       um("Psalm 142,3", "ru"))
pruefe("Psalm 9 bleibt ru (zusammengelegt)", [], um("Psalm 9,1", "ru"))
pruefe("Psalm 23 bleibt en (keine Überschrift)", [], um("Psalm 23,1", "en"))
# Eine Sprache ohne Eintrag bekommt nichts.
pruefe("Ukrainisch bleibt unberührt", [], um("Joel 3,1", "uk"))

titel("5) Nur bei deutscher Ausgangssprache")

# Die Regel haengt an der Schlachter. Spricht jemand englisch, nennt
# er die Stelle schon in der englischen Zaehlung -- umzurechnen waere
# dann genau falsch. Geprueft wird die Zusicherung im Quelltext.
quelle = (WURZEL / "server.py").read_text(encoding="utf-8")
pruefe("der Server prüft die Quellsprache", True,
       'if self.quelle != "de"' in quelle)

titel("6) Die Ausgabe wird nachgesehen, nicht nachgebessert")

st = [("Joel 3,1", "Joel", 2, 28), ("Psalm 23", "Псалом", 22, None)]
t, e = zaehlung.nachtragen("We read Joel 3,1 today and Psalm 23.", st)
pruefe("nicht übernommene Angaben werden eingesetzt",
       "We read Joel 2,28 today and Псалом 22.", t)
pruefe("und es steht im Protokoll, welche", 2, len(e))

t, e = zaehlung.nachtragen("We read Joel 2:28 and Псалом 22.", st)
pruefe("der Doppelpunkt zählt genauso",
       "We read Joel 2:28 and Псалом 22.", t)
pruefe("und nichts wird angefasst", 0, len(e))

t, e = zaehlung.nachtragen("Heute ganz anders formuliert.", st)
pruefe("hat das Modell umformuliert, bleibt alles stehen",
       "Heute ganz anders formuliert.", t)
pruefe("und es wird nichts erfunden", 0, len(e))

pruefe("steht_drin erkennt den Punkt als Trenner", True,
       zaehlung.steht_drin("siehe Joel 2.28", "Joel", 2, 28))
pruefe("aber nicht eine andere Zahl", False,
       zaehlung.steht_drin("siehe Joel 2:29", "Joel", 2, 28))

titel("7) Der Hinweis an das Modell nennt die fertige Angabe")

h = zaehlung.hinweis_bauen(st, "en", ",")
pruefe("die Zielangabe steht drin", True, "Joel 2,28" in h)
pruefe("die Quellangabe auch, damit es zuzuordnen ist", True,
       "Joel 3,1" in h)
# Keine Rechenaufgabe. Ein Modell, das rechnen soll, rechnet falsch.
pruefe("keine Regel, keine Rechnung", False,
       "addier" in h.lower() or "ziehe" in h.lower())
pruefe("ohne Stellen kein Hinweis", "", zaehlung.hinweis_bauen([], "en"))

print()
if FEHLER:
    print(f"{ROT}{FEHLER} Fehler.{AUS}")
    sys.exit(1)
print(f"{GRUEN}Alle Faelle wie erwartet.{AUS}")
