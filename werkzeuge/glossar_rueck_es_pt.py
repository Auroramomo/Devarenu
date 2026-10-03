#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Die Rücklaufe der spanischen und portugiesischen Prüfer eintragen.

    python werkzeuge/glossar_rueck_es_pt.py              (Trockenlauf)
    python werkzeuge/glossar_rueck_es_pt.py --scharf     schreibt glossar_v0.9.csv

WARUM EIN EIGENES SKRIPT UND NICHT sprachpaket.py --einlesen

`sprachpaket.py --einlesen` erwartet `begriffe_<sp>.docx` mit einer
Spalte **Kennung**, über die sich jede Zeile eindeutig einer
Glossarzeile zuordnen lässt. Die beiden Rückläufe, die hier vorliegen,
stammen aus einer früheren Fassung des Dokuments: sie heißen anders und
haben statt der Kennung nur eine laufende **Nr.** Dazu haben beide
Prüfer hinten eine freie Zusatzliste angehängt, die das allgemeine
Einlesen nicht kennt.

Beides einmalig. Darum steht es einmalig hier, mit jeder Entscheidung
als Tabelle im Quelltext -- und nicht als Sonderfall in dem Werkzeug,
das für die nächste Sprache wieder gebraucht wird.

DIE ZUORDNUNG Nr. -> KENNUNG

`pruefung/auswahl_es_pt.csv` enthält genau die 72 Begriffe in genau der
Reihenfolge, in der sie im Dokument stehen, mit Kennung. Geprüft wird
das: stimmt ein deutsches Wort nicht überein, bricht der Lauf ab.

WAS NICHT PASSIERT

  * Keine Spalte außer `es`, `pt`, `n_es`, `n_pt` wird angefasst. Die
    Spalten, die en, ru und fa benutzen, bleiben Zeichen für Zeichen
    so, wie sie in v0.8 stehen -- und v0.8 ist dort identisch mit der
    aktiven v0.4. Nachgewiesen wird das vom Vergleichslauf, nicht
    behauptet.
  * Neue Zeilen kommen HINTEN dazu und haben `stt=0`. Der
    Whisper-Prompt entsteht aus `stt=1`; nach hinten anzuhängen und
    `stt` auf 0 zu lassen heißt: die Spracherkennung sieht kein Wort
    mehr und kein Wort weniger als vorher.
  * Eine neue Zeile, deren deutsches Wort schon als Suchvariante einer
    bestehenden Zeile steht, wird NICHT angelegt. `glossar.finde()`
    sortiert die Varianten nach Länge und behält bei gleicher Länge die
    Reihenfolge der Datei -- die bestehende Zeile gewinnt also, und die
    neue wäre eine Zeile, die nie greift. Schlimmer: würde man sie
    gewinnen lassen, verlöre der englische Prompt den Begriff der alten
    Zeile. Solche Paare stehen im Bericht, nicht in der Datei.
"""

import csv
import io
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

WURZEL = Path(__file__).resolve().parent.parent
QUELLE = WURZEL / "glossar_v0.8.csv"
ZIEL = WURZEL / "glossar_v0.9.csv"
AUSWAHL = WURZEL / "pruefung" / "auswahl_es_pt.csv"
RUECK = {
    "es": WURZEL / "pruefung" / "rueck_es" / "Spanische_Fachbegriffe_pruefen.docx",
    "pt": WURZEL / "pruefung" / "rueck_pt" / "Portugiesische_Fachbegriffe_pruefen.docx",
}

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

GRUEN, ROT, GELB, BLAU, AUS = (
    "\033[32m", "\033[31m", "\033[33m", "\033[1;34m", "\033[0m")


def blau(t):
    print(f"\n{BLAU}== {t}{AUS}")


def gut(t):
    print(f"   {GRUEN}ok{AUS}   {t}")


def warn(t):
    print(f"   {GELB}!{AUS}    {t}")


def fehl(t):
    print(f"   {ROT}FEHLT{AUS} {t}")


# ------------------------------------------------- Feste Entscheidungen
#
# Jede Zeile hier ist eine Entscheidung, die NICHT aus dem Rücklauf
# folgt, sondern daneben getroffen wurde -- mit Grund. Sie schlägt den
# Rücklauf.
FEST = {
    # (Kennung, Sprache): (Hauptform, Nebenformen, Grund)
    ("D006", "pt"): (
        "juízo investigativo", ["julgamento investigativo"],
        "CPB und Revista Adventista schreiben juízo investigativo. "
        "Die Zusatzliste des Prüfers sagt dasselbe."),
    ("D021", "es"): (
        "Gran Chasco", ["Gran Decepción"],
        "Kirchliche Standardform. Der Prüfer nennt sie in der Spalte "
        "\"Auch gehört als\" und in seiner Zusatzliste."),
}

# ------------------------------- Konflikte zwischen Zusatzliste und Tabelle
#
# Regel: widerspricht die freie Zusatzliste der eigenen Tabelle des
# Prüfers (oder dem Maschinenvorschlag, den er in der Tabelle
# stehengelassen hat), gilt die Zusatzliste. Hier steht, was daraus
# folgt -- und bei jedem Eintrag, warum.
#
# "/" in der Zusatzliste heißt zwei Formen: die erste ist die
# Hauptform, der Rest wird Nebenform.
ZUSATZ_GILT = {
    ("C041", "es"): ("Santa Cena", [], "Zusatzliste gegen Maschinenvorschlag"),
    ("C041", "pt"): ("Santa Ceia", [], "Zusatzliste, zweimal genannt (Tabelle und frei)"),
    ("C042", "es"): ("rito de humildad", ["lavamiento de pies"], "Zusatzliste"),
    ("D022", "es"): ("diezmo", [], "Zusatzliste, ohne Artikel"),
    ("D015", "es"): ("remanente", [], "Zusatzliste, ohne Artikel"),
    ("D015", "pt"): ("remanescente", [], "Zusatzliste, ohne Artikel"),
    ("C110", "es"): ("creación", [], "Zusatzliste, klein"),
    ("C110", "pt"): ("criação", [], "Zusatzliste, klein"),
    ("C055", "es"): ("segunda venida", ["regreso de Jesús"], "Zusatzliste"),
    ("C055", "pt"): ("volta de Jesus", [], "Zusatzliste"),
    ("D030", "es"): ("Asociación", ["Misión"], "Zusatzliste nennt beide"),
    ("D030", "pt"): ("Associação", ["Missão"], "Zusatzliste nennt beide"),
    ("D042", "es"): ("grupo pequeño", ["grupo en casa"], "Zusatzliste nennt beide"),
    ("D045", "es"): ("devocional", ["meditación", "devocional matutino"],
                     "Zusatzliste: Andacht und Morgenandacht"),
    ("D045", "pt"): ("devocional", ["Meditação Matinal"],
                     "Zusatzliste; Diakritika berichtigt (Meditacao -> Meditação)"),
    ("D049", "es"): ("informe misionero", ["relato misionero"], "Zusatzliste"),
    ("D049", "pt"): ("informativo missionário", ["relato missionário"], "Zusatzliste"),
    ("D021", "pt"): ("Grande Desapontamento", ["O grande desapontamento"],
                     "Zusatzliste schlägt die eigene Tabellenkorrektur; "
                     "die Tabellenform wird Nebenform"),
}

# ------------------------------------- Zusatzpaare, die NICHT eingehen
#
# Warum nicht, steht dabei. Diese Liste gehört in den Bericht.
NICHT_UEBERNEHMEN = {
    ("Erlösung", "es"): "Zusatz sagt salvación -- das ist C009 Heil. "
                        "Erlösung ist redención. Zwei Begriffe, nicht einer.",
    ("Erlösung", "pt"): "Zusatz sagt salvação -- das ist C009 Heil. "
                        "Erlösung ist redenção.",
    ("Offenbarung", "es"): "Zusatz sagt Apocalipsis. Das ist das BUCH "
                           "(A066, steht schon so da), nicht der Sachbegriff "
                           "C030 revelación.",
    ("Offenbarung", "pt"): "Zusatz sagt Apocalipse. Das ist A066, nicht C030.",
    ("Jüngerschaft", "es"): "Steht als Suchvariante an C037 Jünger. Eine eigene "
                            "Zeile würde dort nie greifen; C037 auf discipulado "
                            "zu setzen wäre falsch (Jünger = discípulo).",
    ("Jüngerschaft", "pt"): "wie es: Suchvariante an C037.",
    ("Diakonin", "es"): "Steht als Suchvariante an D027 Diakon. diaconisa "
                        "bekäme keine eigene Zeile, die greift; D027 auf "
                        "diaconisa zu setzen wäre für Diakon falsch.",
}

# ------------------------------- Groß/klein: die bestehende Form bleibt
#
# "28 Creencias Fundamentales" ist der Titel des Glaubensbekenntnisses
# und wird groß geschrieben; dass der Prüfer ihn mitten in einer Liste
# klein notiert, ist kein Widerspruch in der Sache.
SCHREIBUNG_BLEIBT = {("D034", "es"), ("D034", "pt")}

# ---------------------------------------- Schreibweisen in der Zusatzliste
#
# Nur fehlende Diakritika, nichts sonst. "Assembléia" bleibt stehen:
# das ist eine Rechtschreibreform-Frage und keine fehlende Tilde, und
# darüber entscheidet nicht dieses Skript.
SCHREIBWEISE = {
    "Meditacao Matinal": "Meditação Matinal",
}

# ----------------------------------------------- Bibelbuchnamen
#
# Nicht aus dem Rücklauf -- aus dem Abgleich mit den Übersetzungen
# selbst (Punkt A.5 des Auftrags). Verglichen wurden je Sprache zwei
# unabhängige Übersetzungen über api.getbible.net:
#
#   es   Reina Valera (1909) gegen Sagradas Escrituras (1569)
#        -> 0 von 66 Buchnamen verschieden
#   pt   Almeida Atualizada gegen Bíblia Livre
#        -> 0 von 66 Buchnamen verschieden
#
# Die Namen stehen also fest, und eine Einstellung je Gemeinde wäre ein
# Schalter ohne Gegenstand. Beim Abgleich fielen dafür fünf Zellen auf,
# in denen UNSER Glossar von beiden Übersetzungen abweicht. Die werden
# hier berichtigt. Keine davon ist eine Streitfrage zwischen
# Übersetzungen -- es sind Tippfehler und eine abgeschnittene Form.
BIBELBUCH = {
    ("A034", "es"): ("Nahúm", "Beide spanischen Übersetzungen: Nahúm. "
                              "\"Nahú\" ist abgeschnitten."),
    ("A022", "pt"): ("Cântico dos Cânticos",
                     "Almeida und Bíblia Livre schreiben den vollen Titel."),
    ("A031", "pt"): ("Obadias", "Almeida: Obadias. \"Abdias\" ist die "
                                "Form aus der Vulgata-Tradition."),
    # A033 bleibt "Miqueias" -- OHNE Akzent. Die Almeida Atualizada
    # von 1959 schreibt "Miquéias"; NAA und NVI folgen dem Acordo
    # Ortográfico und schreiben "Miqueias". Die Gemeinden, um die es
    # geht, lesen NAA oder NVI. Mit 0.4.0 war der Akzent einmal drin
    # und ist zurueckgenommen.
    ("A057", "pt"): ("Filemom", "Almeida: Filemom."),
}

# ------------------------------------------- Tippfehler im Rücklauf
DEUTSCH_BERICHTIGT = {
    "Bezirks pastor": "Bezirkspastor",
}

# Block und Typ für die neuen Zeilen. Alles, was aus der Zusatzliste
# kommt, ist Gemeinde- oder Organisationswortschatz -- Block D, wie die
# 49 Zeilen, die dort schon stehen. "hart" ist dort die Regel (47 von
# 49); die Ausnahmen sind deutsche Wörter mit zweiter Bedeutung.
NEU_BLOCK = "D"
NEU_WEICH = {
    # Deutsche Wörter, die auch außerhalb der Gemeinde vorkommen. Als
    # Vorgabe erzwungen würden sie dem Modell eine kirchliche Lesart
    # aufdrängen, wo keine gemeint ist.
    "Präsident", "Sekretär", "Delegierter", "Division", "Bezirk",
    "Kollekte", "Kirchenleitung", "Abteilungsleiter", "Vollversammlung",
    "Endzeit",
}


# ------------------------------------------------------------- docx lesen

def _text(el):
    teile = []
    for n in el.iter():
        if n.tag == W + "t":
            teile.append(n.text or "")
        elif n.tag in (W + "tab", W + "br", W + "cr"):
            teile.append(" ")
    return re.sub(r"\s+", " ", "".join(teile)).strip()


def _zellen(zeile):
    return [" ".join(_text(p) for p in c.findall(W + "p")).strip()
            for c in zeile.findall(W + "tc")]


def rueck_lesen(pfad):
    """(Begriffe, Zusatzpaare) aus einem Rücklauf.

    Ohne python-docx: ein .docx ist eine ZIP mit word/document.xml, und
    was hier gebraucht wird -- Tabellenzellen -- steht dort als
    w:tbl/w:tr/w:tc. python-docx gehört in das BAU-venv und nicht auf
    den Gemeinderechner; für einen Lesevorgang lohnt der Umweg nicht.
    """
    with zipfile.ZipFile(pfad) as z:
        wurzel = ET.fromstring(z.read("word/document.xml"))
    koerper = wurzel.find(W + "body")
    begriffe, zusatz = [], []
    for tbl in koerper.findall(W + "tbl"):
        zeilen = tbl.findall(W + "tr")
        if not zeilen:
            continue
        if "Korrektur (bitte hier)" in " ".join(_zellen(zeilen[0])):
            for z in zeilen[1:]:
                werte = (_zellen(z) + [""] * 6)[:6]
                nr, de, en, vor, korr, auch = werte
                if not nr.strip():
                    continue          # Erläuterungszeile unter dem Begriff
                begriffe.append({"nr": nr.strip(), "de": de,
                                 "vorschlag": vor, "korrektur": korr,
                                 "auch": auch})
            continue
        # Die Zusatzliste: zweispaltig ohne Kopf, beim spanischen
        # Rücklauf in eine Tabelle in der Tabelle gesetzt, beim
        # portugiesischen teils als freie Zeile "Deutsch - Ziel".
        for z in zeilen:
            innen = [t for c in z.findall(W + "tc") for t in c.findall(W + "tbl")]
            if innen:
                for it in innen:
                    for iz in it.findall(W + "tr"):
                        w = _zellen(iz)
                        if len(w) >= 2 and w[0] and w[1]:
                            zusatz.append((w[0], w[1]))
                continue
            w = _zellen(z)
            if len(w) >= 2 and w[0] and w[1]:
                zusatz.append((w[0], w[1]))
            elif len(w) == 1 and w[0]:
                for trenner in ("–", "—", " - "):
                    if trenner in w[0]:
                        a, b = w[0].split(trenner, 1)
                        zusatz.append((a.strip(), b.strip()))
                        break
    return begriffe, zusatz


def paare_aufteilen(paare):
    """Deutsche "/"-Paare aufspalten, wenn die Zielseite genauso viele hat.

    "Übrige / Gemeinde der Übrigen" gegen "remanescente / igreja
    remanescente" sind zwei Paare. Stehen die Zahlen nicht zusammen,
    bleibt es ein Paar und das "/" gehört zur Zielform."""
    aus = []
    for de, ziel in paare:
        dt = [x.strip() for x in de.split("/")]
        zt = [x.strip() for x in ziel.split("/")]
        if len(dt) > 1 and len(dt) == len(zt):
            aus.extend(zip(dt, zt))
        else:
            aus.append((de.strip(), ziel.strip()))
    return aus


def schreibweise(wort):
    for falsch, richtig in SCHREIBWEISE.items():
        wort = wort.replace(falsch, richtig)
    return wort


def verdraengt(bestand, kandidat, kopf):
    """Welche bestehende Zeile würde diese neue Zeile verdrängen?

    Gebaut werden zwei Glossare -- ohne und mit der neuen Zeile -- und
    für die deutschen Formen der neuen Zeile verglichen, was
    glossarzeilen() für en, ru und fa ausgibt. Unterschied heißt:
    verdrängt. Gibt den Namen der verdrängten Zeile zurück oder "".
    """
    import tempfile
    sys.path.insert(0, str(WURZEL))
    from glossar import Glossar, glossarzeilen

    def laden(satzliste):
        with tempfile.NamedTemporaryFile(
                "w", suffix=".csv", delete=False, encoding="utf-8-sig",
                newline="") as f:
            s = csv.DictWriter(f, fieldnames=kopf, delimiter=";")
            s.writeheader()
            s.writerows(satzliste)
            name = f.name
        try:
            return Glossar.laden(name)
        finally:
            Path(name).unlink(missing_ok=True)

    ohne = laden(bestand)
    mit = laden(bestand + [kandidat])
    texte = [kandidat["de"],
             f"Wir sprechen über {kandidat['de']} in der Gemeinde."]
    for text in texte:
        for sp in ("en", "ru", "fa"):
            a = glossarzeilen(ohne.finde(text), sp)
            b = glossarzeilen(mit.finde(text), sp)
            if a != b:
                # Welcher Eintrag ist weggefallen?
                vorher = {e.id for e in ohne.finde(text)}
                nachher = {e.id for e in mit.finde(text)}
                weg = sorted(vorher - nachher)
                namen = [f"{i} {e.de}" for i in weg
                         for e in ohne.eintraege if e.id == i]
                return ", ".join(namen) or f"den {sp}-Prompt"
    return ""


# ----------------------------------------------------------------- Lauf

def main():
    scharf = "--scharf" in sys.argv

    with io.open(QUELLE, encoding="utf-8-sig", newline="") as f:
        kopf = next(csv.reader(f, delimiter=";"))
    with io.open(QUELLE, encoding="utf-8-sig", newline="") as f:
        zeilen = list(csv.DictReader(f, delimiter=";"))
    nach_id = {z["id"]: z for z in zeilen}

    # Jedes deutsche Wort, das das Glossar schon kennt -- als Hauptwort
    # oder als Suchvariante.
    bekannt = {}
    for z in zeilen:
        for v in [z["de"]] + [x.strip() for x in z["suchvarianten"].split("|")]:
            if v.strip():
                bekannt.setdefault(v.strip().lower(), z)

    auswahl = list(csv.DictReader(
        io.open(AUSWAHL, encoding="utf-8-sig", newline=""), delimiter=";"))

    # Nebenformen: zwei neue Spalten. Sie sehen aus wie eine Sprache,
    # sind aber keine -- glossar.sprachen_aus_kopf() zählt nur, was ein
    # "k_" neben sich hat, und ein "k_n_es" gibt es nicht.
    for spalte in ("n_es", "n_pt"):
        if spalte not in kopf:
            kopf.append(spalte)
    for z in zeilen:
        for spalte in ("n_es", "n_pt"):
            z.setdefault(spalte, "")

    aenderungen, nebenformen, offen, uebersprungen = [], [], [], []

    def setzen(kennung, sp, haupt, neben, grund):
        z = nach_id[kennung]
        alt = z[sp]
        if alt != haupt:
            z[sp] = haupt
            aenderungen.append((kennung, sp, z["de"], alt, haupt, grund))
        if neben:
            vorher = [x for x in z["n_" + sp].split("|") if x.strip()]
            for n in neben:
                if n not in vorher and n != haupt:
                    vorher.append(n)
            z["n_" + sp] = "|".join(vorher)
            nebenformen.append((kennung, sp, z["de"], z["n_" + sp], grund))

    # ---- 1) Die Tabelle, Begriff für Begriff
    blau("Die 72 Begriffe aus der Tabelle")
    for sp, pfad in RUECK.items():
        if not pfad.exists():
            fehl(f"{pfad} fehlt.")
            return 1
        begriffe, _ = rueck_lesen(pfad)
        if len(begriffe) != len(auswahl):
            fehl(f"{sp}: {len(begriffe)} Zeilen im Dokument, "
                 f"{len(auswahl)} in {AUSWAHL.name}.")
            return 1
        for i, (b, a) in enumerate(zip(begriffe, auswahl), 1):
            if b["nr"] != str(i) or b["de"] != a["de"]:
                fehl(f"{sp} Nr.{b['nr']}: {b['de']!r} gegen {a['de']!r} "
                     f"in {AUSWAHL.name}. Die Zuordnung stimmt nicht.")
                return 1
            kennung = a["id"]
            if (kennung, sp) in FEST:
                continue                      # unten, mit Begründung
            if b["korrektur"]:
                setzen(kennung, sp, schreibweise(b["korrektur"]), [],
                       "Korrektur des Prüfers")
            if b["auch"]:
                setzen(kennung, sp, nach_id[kennung][sp],
                       [schreibweise(b["auch"])], "\"Auch gehört als\"")
        gut(f"{sp}: 72 Begriffe gelesen, Zuordnung geprüft")

    # ---- 2) Die festen Entscheidungen
    blau("Feste Entscheidungen")
    for (kennung, sp), (haupt, neben, grund) in FEST.items():
        setzen(kennung, sp, haupt, neben, grund)
        gut(f"{kennung} {sp}: {haupt}" + (f"  (auch: {', '.join(neben)})"
                                          if neben else ""))
        print(f"           {grund}")

    # ---- 2b) Bibelbuchnamen aus dem Abgleich mit den Übersetzungen
    blau("Bibelbuchnamen")
    for (kennung, sp), (name, grund) in BIBELBUCH.items():
        setzen(kennung, sp, name, [], grund)
        gut(f"{kennung} {sp}: {name}  -- {grund}")

    # ---- 3) Die Zusatzlisten
    blau("Die Zusatzlisten")
    neue = {}
    for sp, pfad in RUECK.items():
        _, zusatz = rueck_lesen(pfad)
        zusatz = paare_aufteilen(zusatz)
        gleich = 0
        for de, ziel in zusatz:
            de = DEUTSCH_BERICHTIGT.get(de, de)
            ziel = schreibweise(ziel)
            if (de, sp) in NICHT_UEBERNEHMEN:
                uebersprungen.append((sp, de, ziel, NICHT_UEBERNEHMEN[(de, sp)]))
                continue
            z = bekannt.get(de.lower())
            if z is not None:
                kennung = z["id"]
                if (kennung, sp) in ZUSATZ_GILT:
                    continue              # unten, mit Begründung
                if z[sp].strip() == ziel.split("/")[0].strip():
                    gleich += 1
                    continue
                if (kennung, sp) in SCHREIBUNG_BLEIBT:
                    gleich += 1
                    continue
                # Bekannt, kein Eintrag in ZUSATZ_GILT, und doch anders:
                # das ist nichts, was ein Skript entscheiden darf.
                offen.append((sp, de, kennung, z["de"], z[sp], ziel))
                continue
            haupt, *neben = [x.strip() for x in ziel.split("/")]
            e = neue.setdefault(de, {"es": "", "pt": "",
                                     "n_es": "", "n_pt": ""})
            e[sp] = haupt
            if neben:
                e["n_" + sp] = "|".join(neben)
        gut(f"{sp}: {gleich} Paare bestätigen, was schon dasteht")

    for (kennung, sp), (haupt, neben, grund) in ZUSATZ_GILT.items():
        setzen(kennung, sp, haupt, neben, grund)

    # ---- 4) Neue Zeilen -- aber nur die, die niemandem im Weg stehen
    #
    # DIE FALLE: glossar.finde() sortiert alle Suchvarianten nach Länge.
    # Eine neue Zeile "28 Glaubensüberzeugungen" ist LÄNGER als die
    # Variante "Glaubensüberzeugungen" an D034 -- sie beansprucht die
    # Textstelle zuerst, D034 wird als Überlappung verworfen, und weil
    # die neue Zeile für Englisch leer ist, verliert der englische
    # Prompt den Begriff. In der CSV sieht man davon nichts.
    #
    # Geprüft wird darum nicht die Datei, sondern das Ergebnis: verdrängt
    # eine neue Zeile für en, ru oder fa etwas, kommt sie nicht hinein.
    # Die Prüfung steht in werkzeuge/glossar_vergleich.py und ist
    # dieselbe, die hinterher den Vergleichslauf macht.
    blau(f"{len(neue)} Kandidaten für neue Zeilen")
    bestand = list(zeilen)
    nummer = max(int(z["id"][1:]) for z in zeilen if z["block"] == NEU_BLOCK)
    abgewiesen = []
    for de in sorted(neue):
        e = neue[de]
        typ = "weich" if de in NEU_WEICH else "hart"
        satz = {k: "" for k in kopf}
        satz.update({
            "id": "vorlaeufig", "block": NEU_BLOCK, "typ": typ,
            # stt=0: der Whisper-Prompt bleibt Wort für Wort der von v0.4.
            "stt": "0", "de": de, "suchvarianten": de,
            "es": e["es"], "pt": e["pt"],
            "n_es": e["n_es"], "n_pt": e["n_pt"],
            "k_es": "3" if e["es"] else "", "k_pt": "3" if e["pt"] else "",
            "anmerkung": "Aus der Zusatzliste des Prüfers (0.4.0). "
                         "en/ru/fa absichtlich leer.",
        })
        stoert = verdraengt(bestand, satz, kopf)
        if stoert:
            abgewiesen.append((de, e, stoert))
            continue
        nummer += 1
        satz["id"] = f"{NEU_BLOCK}{nummer:03d}"
        bestand.append(satz)
        print(f"   {satz['id']} {typ:5} {de:32} es={e['es'][:26]:26} pt={e['pt']}")
    zeilen = bestand
    if abgewiesen:
        blau(f"{len(abgewiesen)} Zeilen abgewiesen: sie würden en/ru/fa ändern")
        for de, e, stoert in abgewiesen:
            warn(f"{de} (es={e['es']!r}, pt={e['pt']!r})")
            print(f"      verdrängt: {stoert}")
            uebersprungen.append(
                ("es/pt", de, e["es"] or e["pt"],
                 f"würde {stoert} verdrängen und damit den Prompt für "
                 f"en/ru/fa ändern"))

    # ---- Bericht
    blau(f"{len(aenderungen)} geänderte Zellen")
    for kennung, sp, de, alt, neu, grund in aenderungen:
        print(f"   {kennung} {sp} {de[:24]:24} {ROT}{alt[:26]:26}{AUS} -> "
              f"{GRUEN}{neu}{AUS}")
        print(f"            {grund}")
    blau(f"{len(nebenformen)} Nebenformen")
    for kennung, sp, de, formen, grund in nebenformen:
        print(f"   {kennung} n_{sp} {de[:24]:24} {formen}")
    if uebersprungen:
        blau(f"{len(uebersprungen)} Paare NICHT übernommen")
        for sp, de, ziel, grund in uebersprungen:
            print(f"   {sp} {de:26} ({ziel})")
            print(f"      {grund}")
    if offen:
        blau(f"{len(offen)} Paare ungeklärt -- bitte von Hand ansehen")
        for sp, de, kennung, gde, alt, ziel in offen:
            warn(f"{sp} {de} -> {kennung} {gde}: {alt!r} gegen {ziel!r}")

    if not scharf:
        print()
        warn("TROCKENLAUF. Nichts geschrieben.")
        warn(f"Schreiben mit  --scharf   (nach {ZIEL.name})")
        return 0

    with io.open(ZIEL, "w", encoding="utf-8-sig", newline="") as f:
        s = csv.DictWriter(f, fieldnames=kopf, delimiter=";")
        s.writeheader()
        s.writerows(zeilen)
    print()
    gut(f"{ZIEL.name} geschrieben: {len(zeilen)} Zeilen, {len(kopf)} Spalten")
    warn("Aktiv wird sie erst, wenn config.GLOSSAR_CSV darauf zeigt --")
    warn("und erst nach dem Vergleichslauf fuer en, ru und fa.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
