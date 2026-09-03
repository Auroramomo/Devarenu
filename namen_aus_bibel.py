#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Baut Block B des Glossars: Eigen- und Ortsnamen aus einer Bibel-PDF.

Der Whisper-Prompt fasst nur 224 Token, und Whisper verhoert sich an
Eigennamen, nicht an Lehrbegriffen. Mit einem Namensindex laesst sich der
Prompt aus den Bibelstellen bauen, die der Techniker vor dem
Gottesdienst eintraegt.

Erzeugt wird ein Index aus Namen, Haeufigkeiten und Fundstellen, kein
Textauszug: der Bibeltext selbst wird nicht gespeichert.

Ablauf:
    python namen_aus_bibel.py --probe bibel.pdf       # was gibt das PDF her?
    python namen_aus_bibel.py bibel.pdf               # ganzer Durchlauf
"""

import argparse
import csv
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

# Buchnamen wie sie in Schlachter 2000 und Elberfelder vorkommen, samt
# gaengiger Abkuerzungen. Dient der Stellenerkennung, nicht dem Filtern.
BUECHER = {
    "1. Mose": ["1. Mose", "1Mo", "1. Mo"], "2. Mose": ["2. Mose", "2Mo", "2. Mo"],
    "3. Mose": ["3. Mose", "3Mo", "3. Mo"], "4. Mose": ["4. Mose", "4Mo", "4. Mo"],
    "5. Mose": ["5. Mose", "5Mo", "5. Mo"],
    "Josua": ["Josua", "Jos"], "Richter": ["Richter", "Ri"], "Ruth": ["Ruth", "Rut"],
    "1. Samuel": ["1. Samuel", "1Sam"], "2. Samuel": ["2. Samuel", "2Sam"],
    "1. Könige": ["1. Könige", "1Kön"], "2. Könige": ["2. Könige", "2Kön"],
    "1. Chronik": ["1. Chronik", "1Chr"], "2. Chronik": ["2. Chronik", "2Chr"],
    "Esra": ["Esra", "Esr"], "Nehemia": ["Nehemia", "Neh"],
    "Esther": ["Esther", "Ester", "Est"], "Hiob": ["Hiob", "Ijob"],
    "Psalmen": ["Psalm", "Psalmen", "Ps"], "Sprüche": ["Sprüche", "Spr"],
    "Prediger": ["Prediger", "Pred", "Kohelet"], "Hohelied": ["Hohelied", "Hld"],
    "Jesaja": ["Jesaja", "Jes"], "Jeremia": ["Jeremia", "Jer"],
    "Klagelieder": ["Klagelieder", "Klgl"], "Hesekiel": ["Hesekiel", "Ezechiel", "Hes"],
    "Daniel": ["Daniel", "Dan"], "Hosea": ["Hosea", "Hos"], "Joel": ["Joel"],
    "Amos": ["Amos"], "Obadja": ["Obadja", "Obd"], "Jona": ["Jona"],
    "Micha": ["Micha", "Mi"], "Nahum": ["Nahum", "Nah"], "Habakuk": ["Habakuk", "Hab"],
    "Zephanja": ["Zephanja", "Zefanja", "Zeph"], "Haggai": ["Haggai", "Hag"],
    "Sacharja": ["Sacharja", "Sach"], "Maleachi": ["Maleachi", "Mal"],
    "Matthäus": ["Matthäus", "Mt"], "Markus": ["Markus", "Mk"],
    "Lukas": ["Lukas", "Lk"], "Johannes": ["Johannes", "Joh"],
    "Apostelgeschichte": ["Apostelgeschichte", "Apg"], "Römer": ["Römer", "Röm"],
    "1. Korinther": ["1. Korinther", "1Kor"], "2. Korinther": ["2. Korinther", "2Kor"],
    "Galater": ["Galater", "Gal"], "Epheser": ["Epheser", "Eph"],
    "Philipper": ["Philipper", "Phil"], "Kolosser": ["Kolosser", "Kol"],
    "1. Thessalonicher": ["1. Thessalonicher", "1Thess"],
    "2. Thessalonicher": ["2. Thessalonicher", "2Thess"],
    "1. Timotheus": ["1. Timotheus", "1Tim"], "2. Timotheus": ["2. Timotheus", "2Tim"],
    "Titus": ["Titus", "Tit"], "Philemon": ["Philemon", "Phlm"],
    "Hebräer": ["Hebräer", "Hebr"], "Jakobus": ["Jakobus", "Jak"],
    "1. Petrus": ["1. Petrus", "1Petr"], "2. Petrus": ["2. Petrus", "2Petr"],
    "1. Johannes": ["1. Johannes", "1Joh"], "2. Johannes": ["2. Johannes", "2Joh"],
    "3. Johannes": ["3. Johannes", "3Joh"], "Judas": ["Judas", "Jud"],
    "Offenbarung": ["Offenbarung", "Offb"],
}

# Woerter, die praktisch nur grossgeschrieben vorkommen, aber keine Namen
# sind. Ohne diese Liste rutschen Gottesbezeichnungen und liturgische
# Formeln in die Namensliste.
KEINE_NAMEN = {
    "HERR", "HERRN", "HERRE", "GOTT", "Gott", "Gottes", "Herr", "Herrn",
    "Amen", "Halleluja", "Sela", "Kapitel", "Vers", "Buch", "Bibel",
    "Seite", "Anmerkung", "Studienbibel", "Übersetzung", "Auflage",
    "Vorwort", "Inhalt", "Register", "Anhang", "Einleitung",
}

# Pronomen, Konjunktionen und Adverbien. Sie stehen gross nur am
# Satzanfang, also genau dort, wo kein Begleiter davor sein kann, und
# rutschen deshalb durch die Begleiterpruefung.
FUNKTIONSWOERTER = {
    "Diese", "Dieser", "Dieses", "Diesen", "Diesem", "Jene", "Jener",
    "Wenn", "Wer", "Was", "Wie", "Wo", "Warum", "Wann", "Welche", "Welcher",
    "Aber", "Denn", "Doch", "Auch", "Nach", "Nachdem", "Nun", "Also",
    "Darum", "Deshalb", "Daher", "Dann", "Damit", "Dabei", "Davon", "Dazu",
    "Alle", "Allen", "Aller", "Alles", "Andere", "Anderen", "Einige",
    "Viele", "Vielen", "Jeder", "Jede", "Jedes", "Niemand", "Jemand",
    "Sein", "Seine", "Ihre", "Unser", "Unsere", "Euer", "Eure",
    "Erste", "Ersten", "Zweite", "Zweiten", "Dritte", "Letzte",
    "Siehe", "Sehet", "Wahrlich", "Fuerwahr", "Solche", "Solchen",
    "Gleichwie", "Sondern", "Obwohl", "Weil", "Damals", "Heute", "Morgen",
    "Allerdings", "Ausserdem", "Außerdem", "Trotzdem", "Jedoch", "Dennoch",
    "Ebenfalls", "Insbesondere", "Vermutlich", "Wahrscheinlich", "Moeglich",
    "Möglicherweise", "Offenbar", "Natuerlich", "Natürlich", "Schliesslich",
    "Schließlich", "Zunaechst", "Zunächst", "Danach", "Davor", "Somit",
    "Folglich", "Demnach", "Hingegen", "Zwar", "Etwa", "Beispielsweise",
    "Ungehorsam", "Gehorsam", "Glaubens", "Segen", "Fluch", "Bund",
    "Hier", "Dort", "Vorher", "Nachher", "Seitdem", "Ausdruck", "Beispiel",
    "Begegnung", "Gedanke", "Frage", "Antwort", "Geschichte", "Erfahrung",
    "Grossmutter", "Großmutter", "Grossvater", "Großvater", "Eltern",
    "Freund", "Freunde", "Nachbar", "Mitarbeiter", "Gemeinde", "Gemeinden",
    "Seid", "Sei", "Seien", "Spaeter", "Später", "Frueher",
    "Früher", "Zuerst", "Zuletzt", "Weiter", "Ferner", "Ebenso", "Zudem",
    "Gutes", "Boeses", "Böses", "Weise", "Grosse", "Große", "Ganze",
    "Kind", "Kinder", "Kindern", "Bruders", "Herz", "Herzen", "Schuld",
    "Scham", "Schmerz", "Schmerzen", "Strom", "Nebel", "Mond", "Sonne",
    "Stern", "Sterne", "Wasser", "Feuer", "Brot", "Wein", "Baum", "Baeume",
    "Bäume", "Tier", "Tiere", "Frucht", "Fruechte", "Früchte", "Same",
    "Samen", "Staub", "Garten", "Gewaechs", "Gewächs", "Gewuerm", "Gewürm",
    "Abend", "Nacht", "Tag", "Tage", "Tagen", "Jahre", "Jahren", "Jahr",
    "Zeit", "Zeiten", "Stunde", "Leben", "Wesen", "Wort", "Worte",
    "Sohn", "Soehne", "Söhne", "Tochter", "Toechter", "Töchter",
    "Vater", "Mutter", "Bruder", "Brueder", "Brüder", "Schwester",
    "Mensch", "Menschen", "Engel", "Volk", "Voelker", "Völker",
    "Himmel", "Erde", "Welt", "Land", "Meer", "Berg", "Stadt", "Haus",
    "Geist", "Seele", "Herz", "Hand", "Auge", "Augen", "Name", "Namen",
    "Gnade", "Liebe", "Glaube", "Glauben", "Wahrheit", "Sünde", "Suende",
    "Koenig", "König", "Priester", "Prophet", "Propheten", "Knecht",
    "Israel",   # kommt derart oft vor, dass Whisper es sicher kennt
}


def buch_abkuerzungen():
    """Die Querverweisspalte ist voller Kuerzel wie Hebr, Offb, Apg, 2Pt.
    Sie stehen nie mit Artikel und wuerden sonst als Eigennamen gelten.
    Neben den im Glossar gepflegten Formen kommen die in Studienbibeln
    ueblichen Kurzformen dazu."""
    raus = set()
    for buch, formen in BUECHER.items():
        for f in formen + [buch]:
            kern = re.sub(r"^\d+\.?\s*", "", f).strip()
            if kern:
                raus.add(kern)
                raus.add(kern.rstrip("."))
    raus |= {"Pt", "Petr", "Thess", "Kor", "Chr", "Kön", "Koen", "Sam",
             "Mo", "Rö", "Roem", "Phil", "Phlm", "Hebr", "Offb", "Apg",
             "Jak", "Jud", "Tit", "Tim", "Gal", "Eph", "Kol", "Hld",
             "Klgl", "Zeph", "Obd", "Hab", "Hag", "Sach", "Mal", "Nah",
             "Spr", "Pred", "Ps", "Hi", "Jes", "Jer", "Hes", "Dan",
             "Hos", "Joe", "Am", "Jon", "Mi", "Neh", "Esr", "Est", "Rut",
             "Jos", "Ri", "Mt", "Mk", "Lk", "Joh", "Röm", "Vgl", "Vers",
             "Kap", "Anm", "Hebraeisch", "Hebräisch", "Griechisch",
             "Aramaeisch", "Aramäisch", "Wtl", "Bzw", "Zit"}
    return raus


KEINE_NAMEN |= FUNKTIONSWOERTER | buch_abkuerzungen()

WORT = re.compile(r"\b([A-ZÄÖÜ][a-zäöüßA-ZÄÖÜ\-]{3,})\b")
STELLE = re.compile(r"(\d{1,3})[,:.](\d{1,3})")


def text_holen(pdf, von=None, bis=None):
    """Zieht den Text ueber pdftotext, seitenweise getrennt.

    pdftotext setzt zwischen die Seiten ein Seitenvorschubzeichen. Daran
    laesst sich der Text spaeter in Seiten zerlegen, und das ist wichtig:
    die Zuordnung zu Buch und Kapitel kommt aus dem Kolumnentitel, nicht
    aus dem Fliesstext.

    Bewusst OHNE -layout. Die Studienbibel ist dreispaltig gesetzt, mit
    einer schmalen Querverweisspalte in der Mitte. -layout wuerde diese
    Spalte zeilenweise in den Bibeltext einweben."""
    befehl = ["pdftotext", "-enc", "UTF-8"]
    if von:
        befehl += ["-f", str(von)]
    if bis:
        befehl += ["-l", str(bis)]
    befehl += [str(pdf), "-"]
    try:
        r = subprocess.run(befehl, capture_output=True, timeout=1800)
    except FileNotFoundError:
        sys.exit("pdftotext fehlt. Poppler installieren:\n"
                 "  winget install oschwartz10612.Poppler")
    if r.returncode != 0:
        sys.exit(f"pdftotext: {(r.stderr or b'').decode('utf-8','replace')[:300]}")
    return r.stdout.decode("utf-8", "replace")


# Kolumnentitel wie "1. MOSE 1,13" oder "Jesaja 40,5". Steht auf jeder
# Seite und nennt Buch und Kapitel. Verlaesslicher als Stellenangaben im
# Fliesstext, denn die Querverweisspalte ist voll davon und wuerde die
# Zuordnung staendig umspringen lassen.
KOPFZEILE = re.compile(
    r"^\s*(?:\d+\s+)?((?:[1-5]\.?\s*)?[A-ZÄÖÜ][A-ZÄÖÜa-zäöüß.]{2,}(?:\s+[A-ZÄÖÜa-zäöüß.]{2,})?)"
    r"\s+(\d{1,3})\s*,\s*\d{1,3}\s*$", re.MULTILINE)


def buch_normalisieren(roh):
    """Bringt eine Kopfzeilenangabe auf die Schreibweise des Glossars.
    Die Studienbibel setzt Kolumnentitel in Kapitaelchen, was als
    Grossschreibung ankommt: aus '1. MOSE' wird '1. Mose'."""
    text = re.sub(r"\s+", " ", roh.strip())
    text = re.sub(r"^([1-5])\.?\s*", r"\1. ", text)
    kern = text.split(" ", 1)[-1] if text[0].isdigit() else text
    kern = kern.capitalize() if kern.isupper() else kern
    vorn = text.split(" ", 1)[0] + " " if text[0].isdigit() else ""
    kandidat = (vorn + kern).strip()
    for buch, formen in BUECHER.items():
        for f in formen:
            if kandidat.lower() == f.lower() or kandidat.lower() == buch.lower():
                return buch
    return None


def seiten_mit_stelle(text, kopfzeilen=6):
    """Zerlegt den Text in Seiten und liest je Seite den Kolumnentitel.

    Gesucht wird NUR in den ersten Zeilen einer Seite. Der Kolumnentitel
    steht dort, und weiter unten stehen in der Querverweisspalte hunderte
    Angaben derselben Form. Sucht man auf der ganzen Seite, wird
    irgendeine davon zur Kopfzeile erklaert und die Zuordnung ist
    Zufall: so landete Gilboa in 1. Mose 8, obwohl es in 1. Samuel 28
    steht."""
    for seite in text.split("\f"):
        if not seite.strip():
            continue
        kopf = "\n".join(seite.lstrip("\n").splitlines()[:kopfzeilen])
        stelle = None
        treffer = KOPFZEILE.search(kopf)
        if treffer:
            buch = buch_normalisieren(treffer.group(1))
            if buch:
                stelle = f"{buch} {int(treffer.group(2))}"
        yield stelle, seite


# Was einem Gattungsnamen vorangehen kann, einem Eigennamen dagegen kaum.
# "das Volk" ist gewoehnlich, "der Elia" nicht.
BEGLEITER = (
    "der", "die", "das", "den", "dem", "des",
    "ein", "eine", "einen", "einem", "einer", "eines",
    "kein", "keine", "keinen", "keinem", "keiner",
    "mein", "meine", "meinen", "meinem", "sein", "seine", "seinen", "seinem",
    "ihr", "ihre", "ihren", "ihrem", "unser", "unsere", "unseren",
    "dieser", "diese", "dieses", "diesen", "diesem",
    "jeder", "jede", "jedes", "alle", "allen", "aller", "viele", "vielen",
    "im", "am", "vom", "zum", "zur", "beim", "ins", "ans",
    "andere", "anderen", "grosse", "grossen", "ganze", "ganzen",
)


# Deutsche Ableitungssilben. Ein Wort, das so endet, ist ein gebildetes
# Substantiv und kein Eigenname: Vereinigung, Beziehung, Trennung,
# Gerechtigkeit, Freundschaft. Das trifft genau die Kommentarsprache, die
# sich sonst nicht vom Bibeltext trennen laesst, weil beide auf derselben
# Seite stehen. Ausnahmen wie Offenbarung sind Buchnamen und stehen
# ohnehin schon in der Sperrliste.
ABLEITUNGEN = ("ung", "heit", "keit", "schaft", "nis", "tum", "sal",
               "ismus", "ation", "ierung", "lein", "chen")


ZAHLWOERTER = {"zwei", "drei", "vier", "fünf", "fuenf", "sechs", "sieben",
               "acht", "neun", "zehn", "elf", "zwölf", "zwoelf", "hundert",
               "tausend", "viele", "wenige", "einige", "etliche"}


def kandidaten(text, hoechste_begleiterquote=0.25):
    """Trennt Eigennamen von normalen Substantiven.

    Ueber Gross- und Kleinschreibung geht es nicht: im Deutschen sind ALLE
    Substantive gross. "Volk" kommt nirgends klein vor und rutschte durch.

    Das tragfaehige Kriterium ist der Begleiter. Gattungsnamen stehen
    ueberwiegend mit Artikel oder Possessivpronomen (das Volk, ein Altar),
    Eigennamen fast immer nackt (Elia sprach, nach Zarpat). Gemessen wird
    der Anteil der Vorkommen mit Begleiter; ueber einem Viertel ist es ein
    Gattungsname.

    Das ist eine Heuristik, keine Grammatik. Sie irrt bei festen Wendungen
    wie "der Herr Zebaoth" und bei Voelkernamen mit Artikel. Fuer einen
    Whisper-Prompt ist das verschmerzbar: ein Wort zu viel kostet nur
    Platz, ein Wort zu wenig kostet einen Verhoerer."""
    gross = Counter()          # alle Vorkommen
    bewertbar = Counter()      # Vorkommen, an denen sich der Begleiter zeigt
    mit_begleiter = Counter()

    # Zeilenumbrueche zuerst zu Leerzeichen. In PDF-Text steht mitten im
    # Satz staendig ein Umbruch, und wuerde man daran trennen, gaelte jedes
    # Wort am Zeilenanfang faelschlich als Satzanfang und fiele aus der
    # Zaehlung. Getrennt wird nur an echten Satzzeichen.
    text = re.sub(r"[ \t]*\n[ \t]*", " ", text)

    for satz in re.split(r"[.!?;:]", text):
        woerter = satz.split()
        for i, roh in enumerate(woerter):
            treffer = WORT.fullmatch(roh.strip(",;:()»«\"'"))
            if not treffer:
                continue
            wort = treffer.group(1)
            if wort in KEINE_NAMEN or wort.isupper():
                continue
            if wort.endswith(ABLEITUNGEN):
                continue
            # Flexionsformen gesperrter Woerter mitsperren: "Bruders" faellt
            # mit "Bruder", "Herzen" mit "Herz".
            if any(wort[:-n] in KEINE_NAMEN for n in (1, 2) if len(wort) > n + 2):
                continue
            gross[wort] += 1
            # Am Satzanfang steht kein Begleiter, weil dort nichts steht.
            # Das Vorkommen zaehlt trotzdem, liefert aber keine Evidenz.
            # Wuerde man es ganz ueberspringen, verloere man jeden Namen,
            # der nur einmal und dann satzeinleitend vorkommt.
            if i == 0:
                continue
            bewertbar[wort] += 1
            vorher = woerter[i - 1].strip(",;:()»«\"'").lower()
            # Eine Zahl davor spricht ebenso fuer einen Gattungsnamen:
            # "35 Jahre", "zwoelf Staemme". Eigennamen werden nicht gezaehlt.
            if vorher in BEGLEITER or vorher.rstrip(".").isdigit() \
                    or vorher in ZAHLWOERTER:
                mit_begleiter[wort] += 1

    treffer = {}
    for wort, n in gross.items():
        pruefbar = bewertbar[wort]
        if pruefbar and mit_begleiter[wort] / pruefbar > hoechste_begleiterquote:
            continue
        treffer[wort] = n

    # Genitivformen auf den Grundnamen ziehen: Adams zaehlt zu Adam,
    # Kains zu Kain. Zwei Eintraege fuer denselben Namen wuerden im
    # Prompt doppelt Platz kosten.
    for wort in sorted(treffer, key=len, reverse=True):
        if wort.endswith("s") and wort[:-1] in treffer:
            treffer[wort[:-1]] += treffer.pop(wort)
    return treffer


def stellen_index(text, namen):
    """Ordnet jedem Namen die Kapitel zu, in denen er vorkommt.

    Grundlage ist der Kolumnentitel je Seite. Eine Seite deckt in der
    Studienbibel meist ein bis zwei Kapitel ab, das genuegt: fuer den
    Whisper-Prompt reicht die Ebene Buch und Kapitel, Versgenauigkeit
    braucht es nicht.

    Seiten ohne erkennbaren Kolumnentitel werden uebersprungen. Das sind
    Vorwort, Einleitungen und Anhang, also genau der Teil, dessen Namen
    nicht ins Glossar sollen."""
    index = defaultdict(set)
    mit = ohne = 0
    for stelle, seite in seiten_mit_stelle(text):
        if not stelle:
            ohne += 1
            continue
        mit += 1
        for name in set(WORT.findall(seite)):
            if name in namen:
                index[name].add(stelle)
    return index, mit, ohne


def probe(pdf, von, bis):
    print(f"Probe: Seiten {von} bis {bis} aus {Path(pdf).name}\n")
    text = text_holen(pdf, von, bis)
    if len(text.strip()) < 200:
        print("Fast kein Text extrahierbar. Das PDF ist vermutlich ein Scan,")
        print("dann braucht es OCR und das ist ein eigener Arbeitsschritt.")
        return

    seiten = list(seiten_mit_stelle(text))
    erkannt = [s for s, _ in seiten if s]
    print(f"{len(seiten)} Seiten, davon {len(erkannt)} mit Kolumnentitel")
    if erkannt:
        print(f"  von {erkannt[0]} bis {erkannt[-1]}")
    else:
        print("  KEIN Kolumnentitel erkannt. Entweder liegt der Bereich vor")
        print("  dem Bibeltext, oder die Kopfzeile sieht anders aus als")
        print("  erwartet. Eine Zeile aus dem Seitenanfang zeigt es:")
        print("   ", "\n    ".join(text.strip().splitlines()[:3]))

    print("\n--- Textprobe ---")
    beispiel = next((t for st, t in seiten if st), text)
    print(beispiel[:700].strip())

    print("\n--- Namenskandidaten ---")
    nur_bibel = "\n".join(t for st, t in seiten if st) or text
    n = kandidaten(nur_bibel)
    print(f"{len(nur_bibel.split())} Woerter, {len(n)} Kandidaten")
    for wort, anzahl in Counter(n).most_common(30):
        print(f"  {anzahl:4}  {wort}")
    print("\nStehen dort ueberwiegend Namen, laeuft es. Viele normale")
    print("Substantive bedeuten, dass die Textextraktion die Spalten")
    print("durcheinanderbringt.")


def main():
    p = argparse.ArgumentParser(
        epilog="Seitenzahlen sind PDF-Seiten, nicht die gedruckten. In der "
               "MacArthur-Studienbibel beginnt der Bibeltext bei etwa "
               "PDF-Seite 44 und endet vor dem Anhang bei etwa 1951.")
    p.add_argument("pdf")
    p.add_argument("--probe", action="store_true")
    p.add_argument("--von", type=int, default=None,
                   help="erste PDF-Seite, Vorwort und Einleitungen auslassen")
    p.add_argument("--bis", type=int, default=None,
                   help="letzte PDF-Seite, Anhang und Register auslassen")
    p.add_argument("--max-streuung", type=float, default=0.75,
                   help="ab welcher Streuung ein Wort als Allgemeinwort gilt")
    p.add_argument("--min-haeufigkeit", type=int, default=2,
                   help="seltener genannte Namen weglassen")
    p.add_argument("--ziel", default="namen_block_b.csv")
    a = p.parse_args()

    if not Path(a.pdf).exists():
        sys.exit(f"Nicht gefunden: {a.pdf}")

    if a.probe:
        probe(a.pdf, a.von or 44, a.bis or (a.von or 44) + 8)
        return

    print("Text wird extrahiert, bei einer ganzen Studienbibel dauert das "
          "einige Minuten ...")
    text = text_holen(a.pdf, a.von, a.bis)

    # Nur Seiten mit Kolumnentitel. Damit fallen Vorwort, Buch-Einleitungen,
    # Themenindex und Anhang von selbst weg, ohne dass man Seitenzahlen
    # raten muss. Genau deren Namen sollen nicht ins Glossar.
    seiten = list(seiten_mit_stelle(text))
    bibel = "\n".join(t for st, t in seiten if st)
    ohne = sum(1 for st, _ in seiten if not st)
    print(f"{len(seiten)} Seiten, {len(seiten)-ohne} mit Bibeltext, "
          f"{ohne} ohne Kolumnentitel uebersprungen.")
    if not bibel.strip():
        sys.exit("Keine Bibelseiten erkannt. Erst mit --probe pruefen.")

    alle = kandidaten(bibel)
    namen = {w: n for w, n in alle.items() if n >= a.min_haeufigkeit}
    print(f"{len(alle)} Kandidaten, davon {len(namen)} ab "
          f"{a.min_haeufigkeit} Nennungen.")

    print("Stellenindex wird gebaut ...")
    index, mit, _ = stellen_index(text, set(namen))

    zeilen = []
    for wort, anzahl in sorted(namen.items(), key=lambda x: -x[1]):
        stellen = sorted(index.get(wort, []))
        # Streuung: in wie vielen verschiedenen Kapiteln steht das Wort,
        # gemessen an seiner Haeufigkeit. Ein Eigenname buendelt sich, weil
        # er zu einer Person oder einem Ort gehoert: Jethro steht in drei
        # Kapiteln, Jabes in zweien. Ein Allgemeinwort wie Geduld oder
        # Bedingungen verteilt sich ueber die ganze Bibel, kommt also fast
        # in so vielen Kapiteln vor wie es Nennungen hat. Das trennt die
        # letzten Kommentarwoerter, ohne ein Woerterbuch zu brauchen.
        streuung = len(stellen) / anzahl if anzahl else 0
        zeilen.append({
            "de": wort,
            "haeufigkeit": anzahl,
            "streuung": round(streuung, 2),
            "verdacht": "ja" if streuung > a.max_streuung else "",
            # Selten heisst: Whisper kennt es vermutlich nicht und verhoert
            # sich. Genau diese Namen gehoeren in den Prompt, nicht Jesus
            # oder Jerusalem.
            "prompt_rang": 1 if anzahl <= 20 else (2 if anzahl <= 200 else 3),
            "kapitel_anzahl": len(stellen),
            "kapitel": "|".join(stellen[:40]),
        })

    with open(a.ziel, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["de", "haeufigkeit", "streuung",
                                           "verdacht", "prompt_rang",
                                           "kapitel_anzahl", "kapitel"],
                           delimiter=";")
        w.writeheader()
        w.writerows(zeilen)

    leer = sum(1 for z in zeilen if not z["kapitel"])
    verdaechtig = sum(1 for z in zeilen if z["verdacht"])
    print(f"\n{len(zeilen)} Namen nach {a.ziel}")
    print(f"  mit Stellenzuordnung: {len(zeilen) - leer}")
    print(f"  als Allgemeinwort verdaechtig: {verdaechtig} "
          f"(Streuung ueber {a.max_streuung})")
    print(f"  brauchbar: {len(zeilen) - verdaechtig}")

    print("\nStichprobe echter Namen (niedrige Streuung):")
    gut = [x for x in zeilen if not x["verdacht"] and x["kapitel"]]
    for z in sorted(gut, key=lambda x: x["streuung"])[:12]:
        print(f"  {z['de']:20} {z['haeufigkeit']:3}x  Streuung "
              f"{z['streuung']:.2f}  {z['kapitel'][:44]}")

    print("\nAls Allgemeinwort aussortiert:")
    for z in sorted([x for x in zeilen if x["verdacht"]],
                    key=lambda x: -x["haeufigkeit"])[:10]:
        print(f"  {z['de']:20} {z['haeufigkeit']:3}x in "
              f"{z['kapitel_anzahl']} Kapiteln, Streuung {z['streuung']:.2f}")


if __name__ == "__main__":
    main()
