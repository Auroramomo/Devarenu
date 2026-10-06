#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Den Ruecklauf des ukrainischen Pruefers eintragen.

    python werkzeuge/glossar_rueck_uk.py --maschine     Vorschlaege holen (gemma)
    python werkzeuge/glossar_rueck_uk.py                Trockenlauf
    python werkzeuge/glossar_rueck_uk.py --scharf       schreibt glossar_v1.2.csv

Muster: werkzeuge/glossar_rueck_es_pt.py. Anders als dort kommt der
Ruecklauf hier nicht als .docx, sondern als CSV mit Kennung
(id;de;uk;n_uk) -- die Zuordnung zur Glossarzeile steht also schon
darin und muss nicht ueber eine laufende Nummer erschlossen werden.

DIE QUELLE

pruefung/rueck_uk/uk_geprueft.csv: die 93 Begriffe der Pruefauswahl,
von einem ukrainischen Muttersprachler durchgesehen. Eine Korrektur
(D016, знак звіра statt начерк звіра), ein Hinweis (C038, громада
wird gleichbedeutend mit церква gebraucht), alles andere bestaetigt.
Der Ordner liegt NICHT im Repo (.gitignore: pruefung/rueck_*/) --
das Ergebnis steht im Glossar, die Entscheidungen stehen hier.

DIE UEBRIGEN ZEILEN -- WIE BEI es UND pt

Bei es und pt wurde nur die Pruefauswahl von Menschen gesehen; alle
anderen Zeilen behielten den maschinellen Vorschlag, und die Sprache
gilt trotzdem als geprueft. Genauso hier:

  * die 93 geprueften Zeilen bekommen den Wert des Pruefers,
  * die uebrigen 54 Bibelbuecher bekommen den Namen aus der Ohienko-
    Ausgabe (BIBELBUCH unten) -- auch das wie bei es und pt,
  * die uebrigen Zeilen des alten Bestands (C, D bis D049) bekommen
    den maschinellen Vorschlag aus pruefung/glossar_maschine_uk.csv,
  * die 43 Zeilen aus der spanischen und portugiesischen Zusatzliste
    (D050 bis D092) bleiben fuer uk LEER -- wie fuer en, ru, fa, pl,
    fr und hr. Sie stehen nur da, weil zwei Pruefer sie beigetragen
    haben; ein ukrainischer Wert dort waere ein Wort ohne jeden Beleg
    in einer Sprache, die als geprueft angezeigt wird.

Die Vorschlaege entstehen mit --maschine ueber genau den Weg, den
sprachpaket.py fuer jede neue Sprache geht (glossar_ergaenzen, mit den
Ankerbeispielen aus ANKER["uk"]). Sie werden als CSV abgelegt und
eingecheckt, damit dieser Lauf ohne Sprachmodell wiederholbar ist und
dasselbe ergibt.

WAS NICHT PASSIERT

  * Keine Spalte ausser uk, k_uk, n_uk wird angefasst. Belegt wird das
    mit werkzeuge/glossar_vergleich.py, nicht behauptet.
  * Keine Zeile kommt dazu, keine faellt weg, die Reihenfolge bleibt.
  * stt bleibt, wie es ist: der Whisper-Prompt aendert sich nicht.
"""

import csv
import io
import sys
import tempfile
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))
sys.path.insert(0, str(WURZEL / "werkzeuge"))

QUELLE = WURZEL / "glossar_v1.1.csv"
ZIEL = WURZEL / "glossar_v1.2.csv"
RUECK = WURZEL / "pruefung" / "rueck_uk" / "uk_geprueft.csv"
MASCHINE = WURZEL / "pruefung" / "glossar_maschine_uk.csv"
MODELL = "gemma4:12b"

# Die Zeilen aus den Zusatzlisten von es und pt. Ab hier bleibt uk leer.
ERSTE_ZUSATZZEILE = 50

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
# Was im Ruecklauf in der Spalte n_uk steht, ist zweierlei: eine echte
# Nebenform (C038) und ein Vermerk zur Korrektur (D016). Nur die
# Nebenform geht in n_uk -- dort sucht glossar.finde_in() nach ihr.
# Der Vermerk bleibt HIER und geht nicht ins Glossar: in n_uk suchte
# der Rechner sonst nach dem Satz "korrigiert vom Pruefer", und die
# Spalte anmerkung ist eine alte Zelle, die pruefstand/glossar_test.py
# zu Recht nicht angefasst sehen will.
NEBENFORM = {
    "C038": (["громада"],
             "Pruefer: громада wird gleichbedeutend gebraucht. Ausgegeben "
             "wird церква; громада dient nur dem Erkennen."),
}
VERMERK = {
    "D016": "uk vom Pruefer korrigiert (0.5.0): знак звіра statt "
            "начерк звіра.",
}


# ----------------------------------------------- Bibelbuchnamen
#
# Nicht aus dem Ruecklauf und nicht vom Sprachmodell -- aus der
# Uebersetzung selbst, wie bei es und pt (BIBELBUCH in
# glossar_rueck_es_pt.py). Grundlage ist Ohienko in der Ausgabe der
# Ukrainischen Bibelgesellschaft (UBIO, ueber bolls.life/get-books),
# dieselbe, nach der zaehlung.json fuer uk gebaut ist.
#
# Warum nicht die Vorschlaege des Modells: sie waren hier oft falsch,
# und zwar sachlich -- 3. Mose als "Числа" (das ist 4. Mose), Micha als
# "Міхаїл" (ein Personenname), "1 Тимому 1", "Руффа". Ein Buchname ist
# keine Ermessensfrage; er steht in der Bibel.
#
# Die Ordinalform "1-а", "1-е" ist die der Ohienko-Ausgabe und
# entspricht der russischen Spalte ("1-я Царств", "1-е Коринфянам"),
# die ein Muttersprachler bestaetigt hat.
#
# Die zwoelf Buecher, die der Pruefer gesehen hat, behalten SEINE Form
# ("Суддів" statt "Книга Суддів", "Дії апостолів" statt "Дії").
BIBELBUCH = {
    "A001": "Буття",  # 1. Mose
    "A002": "Вихід",  # 2. Mose
    "A003": "Левит",  # 3. Mose
    "A004": "Числа",  # 4. Mose
    "A006": "Ісус Навин",  # Josua
    "A008": "Рут",  # Ruth
    "A009": "1-а Самуїлова",  # 1. Samuel
    "A010": "2-а Самуїлова",  # 2. Samuel
    "A011": "1-а царів",  # 1. Könige
    "A012": "2-а царів",  # 2. Könige
    "A013": "1-а хроніки",  # 1. Chronik
    "A014": "2-а хроніки",  # 2. Chronik
    "A015": "Ездра",  # Esra
    "A016": "Неемія",  # Nehemia
    "A017": "Естер",  # Esther
    "A018": "Йов",  # Hiob
    "A019": "Псалми",  # Psalmen
    "A023": "Ісая",  # Jesaja
    "A024": "Єремія",  # Jeremia
    "A026": "Єзекіїль",  # Hesekiel
    "A027": "Даниїл",  # Daniel
    "A028": "Осія",  # Hosea
    "A029": "Йоїл",  # Joel
    "A030": "Амос",  # Amos
    "A031": "Овдій",  # Obadja
    "A032": "Йона",  # Jona
    "A033": "Михей",  # Micha
    "A034": "Наум",  # Nahum
    "A036": "Софонія",  # Zephanja
    "A038": "Захарія",  # Sacharja
    "A039": "Малахії",  # Maleachi
    # Die Evangelien OHNE "Від". Ohienko titelt "Від Матвія"; als
    # Vorgabe im Satz wurde daraus "читаємо з Від Матвія 18, 21" --
    # gemessen mit gemma4:12b. Die russische Spalte laesst "От"
    # ebenso weg ("Матфея"), und der Pruefer schreibt "Якова".
    "A040": "Матвія",  # Matthäus
    "A041": "Марка",  # Markus
    "A042": "Луки",  # Lukas
    "A043": "Івана",  # Johannes
    "A045": "До римлян",  # Römer
    "A046": "1-е до коринтян",  # 1. Korinther
    "A047": "2-е до коринтян",  # 2. Korinther
    "A048": "До галатів",  # Galater
    "A049": "До ефесян",  # Epheser
    "A050": "До филип'ян",  # Philipper
    "A051": "До колоссян",  # Kolosser
    "A052": "1-е до солунян",  # 1. Thessalonicher
    "A053": "2-е до солунян",  # 2. Thessalonicher
    "A054": "1-е Тимофію",  # 1. Timotheus
    "A055": "2-е Тимофію",  # 2. Timotheus
    "A056": "До Тита",  # Titus
    "A057": "До Филимона",  # Philemon
    "A060": "1-е Петра",  # 1. Petrus
    "A061": "2-е Петра",  # 2. Petrus
    "A062": "1-е Івана",  # 1. Johannes
    "A063": "2-е Івана",  # 2. Johannes
    "A064": "3-е Івана",  # 3. Johannes
    "A065": "Юда",  # Judas
}


# ------------------------------- Maschinenvorschlaege, die NICHT bleiben
#
# Hier weicht dieser Lauf von es und pt ab, und zwar mit Absicht.
#
# Die Vorschlaege des Modells waren bei rund einem Sechstel der
# uebrigen Zeilen nicht schief, sondern falsch: Kreuzigung als
# "Хрещення" (das ist die TAUFE), Hohepriester als "Верховний Йаєць"
# (kein Wort), Daemon als "бес" (russisch). Die meisten dieser Zeilen
# sind "hart" -- das Modell bekommt das Wort als verbindliche Vorgabe,
# in einer Sprache, die am Pult als geprueft erscheint. Ein falsches
# hartes Wort ist schlechter als gar keins.
#
# Darum zwei Tabellen. Jede Ersatzform ist im Ohienko-Text belegt
# (gezaehlt in der Ausgabe UBIO) oder als Lemma im ukrainischen
# Woerterbuch (uk.wiktionary) -- KEIN Wort kommt aus dem Gedaechtnis
# dieses Skripts. Wo sich nichts belegen liess, bleibt die Zelle leer:
# dann uebersetzt das Modell den Begriff ohne Vorgabe, wie in jeder
# Sprache ohne Glossar.
#
# Beides gehoert vor den naechsten Pruefer. Bis dahin ist es eine
# Entscheidung dieses Laufs, keine Pruefung.
KORREKTUR = {
    # Kennung: (Ersatz, maschinell, Beleg)
    "C018": ("примирення", "помирення", "Ohienko 2 Kor 5,18 u. a., 5x"),
    "C022": ("первосвященик", "Верховний Йаєць", "Ohienko, 132x"),
    "C027": ("розп'яття", "Хрещення (= Taufe)", "Ohienko, 3x"),
    "C037": ("учень", "ученьник (kein Wort)", "Ohienko, 18x"),
    "C045": ("хвала", "славослів (abgebrochen)", "Ohienko, 14x"),
    "C048": ("Трійця", "Триєдинство", "Woerterbuch; ru: Троица"),
    "C049": ("провидіння", "Провиденство (falsch geschrieben)", "Woerterbuch"),
    "C061": ("пекло", "пекельний вогонь (Hoellenfeuer)", "Ohienko, 2x"),
    "C066": ("демон", "бес (russisch)", "Ohienko, 73x"),
    "C070": ("скинія", "Намет (Zelt)", "Ohienko, 233x"),
    "C071": ("прообраз", "тип і антитип", "Ohienko, 1x; ru: прообраз"),
    "C075": ("послух", "покора (= Demut, C084)", "Ohienko"),
    "C076": ("діла", "твори (Kunstwerke)", "Ohienko, 121x"),
    "C085": ("лагідність", "покірність (Unterwuerfigkeit)", "Ohienko, 5x"),
    "C086": ("довготерпіння", "терпимість (Toleranz)", "Ohienko, 10x"),
    "C103": ("Агнець Божий", "Ягнятко Боже (Verkleinerung)", "Ohienko Joh 1,29"),
    "C112": ("рай", "райський сад", "Ohienko"),
    "C117": ("страх Божий", "боязнь Божа", "Ohienko, 2x"),
    "C123": ("книжники", "писцірі (kein Wort)", "Ohienko, 65x"),
    "C125": ("козел відпущення", "козлище", "Woerterbuch"),
    "C126": ("Пасха", "Паска (Паска Господня)", "Ohienko, 66x"),
    "C127": ("свято Кучок", "Свято наменосів (kein Wort)", "Ohienko, 9x"),
    "C128": ("День очищення", "День викуплення", "Ohienko 3 Mo 23,27, 4x"),
    "C131": ("синедріон", "Вища Рада", "Ohienko, 19x"),
    "C135": ("виноградина", "виноградник (Weinberg)", "Ohienko Joh 15,1"),
    "C139": ("Осанна", "Госанна", "Ohienko, 6x"),
    "C141": ("Еммануїл", "Іммануїл", "Ohienko Jes 7,14, 3x"),
    "C144": ("блудний син", "Загублений син", "Woerterbuch"),
    "C148": ("безбожність", "безодарність (Talentlosigkeit)", "Ohienko, 10x"),
    "C156": ("первісток", "первісторія (kein Wort)", "Ohienko, 6x"),
}
LEER = {
    # Kennung: (maschinell, warum leer)
    "C020": ("посередництво",
             "heisst Vermittlung. Das naheliegende заступництво ist genau "
             "die Falle, die in der Anmerkung fuer ru steht "
             "(Heiligenanrufung). Das entscheidet ein Pruefer."),
    "C031": ("надихнення",
             "allgemeine Eingebung, nicht Schriftinspiration (ru: "
             "богодухновенность). Die Fachform liess sich nicht belegen."),
    "C145": ("говорення мовами",
             "falsch geschrieben; die richtige Form liess sich nicht "
             "belegen."),
}


def zusatzzeile(kennung):
    """D050 und folgende stammen aus den Zusatzlisten von es und pt."""
    return kennung.startswith("D") and int(kennung[1:]) >= ERSTE_ZUSATZZEILE


def lies(pfad):
    with io.open(pfad, encoding="utf-8-sig", newline="") as f:
        kopf = next(csv.reader(f, delimiter=";"))
    with io.open(pfad, encoding="utf-8-sig", newline="") as f:
        return kopf, list(csv.DictReader(f, delimiter=";"))


def maschine(zeilen, kopf, rueck):
    """Holt die Vorschlaege fuer die nicht geprueften Zeilen.

    Ueber sprachpaket.glossar_ergaenzen -- derselbe Prompt, dieselben
    Ankerbeispiele wie bei jeder anderen neuen Sprache. Gefragt wird
    nur nach den Zeilen, die einen Vorschlag brauchen."""
    import sprachpaket
    noetig = [z for z in zeilen
              if z["id"] not in rueck and not zusatzzeile(z["id"])]
    with tempfile.TemporaryDirectory() as tmp:
        ein = Path(tmp) / "glossar_v9.0.csv"
        aus = Path(tmp) / "glossar_v9.1.csv"
        with io.open(ein, "w", encoding="utf-8-sig", newline="") as f:
            s = csv.DictWriter(f, fieldnames=kopf, delimiter=";")
            s.writeheader()
            s.writerows(noetig)
        sprachpaket.glossar_ergaenzen("uk", MODELL, quelle=ein, ziel=aus)
        _k, erg = lies(aus)
    with io.open(MASCHINE, "w", encoding="utf-8", newline="") as f:
        s = csv.writer(f, delimiter=";")
        s.writerow(["id", "de", "uk"])
        for z in erg:
            s.writerow([z["id"], z["de"], z["uk"]])
    gut(f"{MASCHINE.relative_to(WURZEL)}: {len(erg)} Vorschlaege")


def main():
    scharf = "--scharf" in sys.argv
    kopf, zeilen = lies(QUELLE)
    if "uk" in kopf:
        fehl(f"{QUELLE.name} hat schon eine Spalte uk.")
        return 1
    if not RUECK.exists():
        fehl(f"{RUECK} fehlt.")
        return 1
    _rk, rueck_zeilen = lies(RUECK)
    rueck = {r["id"]: r for r in rueck_zeilen}
    nach_id = {z["id"]: z for z in zeilen}

    blau(f"Ruecklauf: {len(rueck)} Begriffe")
    for kennung, r in rueck.items():
        if kennung not in nach_id:
            fehl(f"{kennung} gibt es im Glossar nicht.")
            return 1
        if nach_id[kennung]["de"] != r["de"]:
            fehl(f"{kennung}: {r['de']!r} gegen {nach_id[kennung]['de']!r}")
            return 1
        if not r["uk"].strip():
            fehl(f"{kennung}: kein Wert")
            return 1
        notiz = r.get("n_uk", "").strip()
        if notiz and kennung not in NEBENFORM and kennung not in VERMERK:
            fehl(f"{kennung}: Notiz {notiz!r} ohne Entscheidung hier.")
            return 1
    gut(f"{len(rueck)} Kennungen gefunden, deutsches Wort stimmt jeweils")

    if "--maschine" in sys.argv:
        blau("Maschinelle Vorschlaege fuer die uebrigen Zeilen")
        maschine(zeilen, kopf, rueck)
        return 0

    if not MASCHINE.exists():
        fehl(f"{MASCHINE.name} fehlt. Erst: --maschine")
        return 1
    _mk, mzeilen = lies(MASCHINE)
    vorschlag = {m["id"]: m["uk"] for m in mzeilen}

    for spalte in ("uk", "k_uk", "n_uk"):
        kopf.append(spalte)

    geprueft = maschinell = leer = bibel = korrigiert = geleert = 0
    for z in zeilen:
        kennung = z["id"]
        z["n_uk"] = ""
        if kennung in rueck:
            z["uk"] = rueck[kennung]["uk"].strip()
            geprueft += 1
            if kennung in BIBELBUCH:
                fehl(f"{kennung} steht im Ruecklauf UND in BIBELBUCH.")
                return 1
        elif kennung in BIBELBUCH:
            z["uk"] = BIBELBUCH[kennung]
            bibel += 1
        elif zusatzzeile(kennung):
            z["uk"] = ""
            leer += 1
        else:
            if kennung not in vorschlag:
                fehl(f"{kennung}: kein maschineller Vorschlag")
                return 1
            if vorschlag[kennung] and z["de"] != next(
                    m["de"] for m in mzeilen if m["id"] == kennung):
                fehl(f"{kennung}: Vorschlag gehoert zu einem anderen Wort")
                return 1
            z["uk"] = vorschlag[kennung].strip()
            if kennung in KORREKTUR:
                ersatz, masch, _beleg = KORREKTUR[kennung]
                if not masch.startswith(z["uk"]):
                    fehl(f"{kennung}: Vorschlag ist {z['uk']!r}, KORREKTUR "
                         f"erwartet {masch!r}. Erst nachsehen.")
                    return 1
                z["uk"] = ersatz
                korrigiert += 1
            elif kennung in LEER:
                if LEER[kennung][0] != z["uk"]:
                    fehl(f"{kennung}: Vorschlag ist {z['uk']!r}, LEER "
                         f"erwartet {LEER[kennung][0]!r}.")
                    return 1
                z["uk"] = ""
                geleert += 1
            else:
                maschinell += 1
        # Konfidenz wie in sprachpaket.glossar_ergaenzen: sie beschreibt
        # den BEGRIFF, nicht die Uebersetzung.
        z["k_uk"] = (z.get("k_en") or z.get("k_es") or "") if z["uk"] else ""
        if kennung in NEBENFORM:
            z["n_uk"] = "|".join(NEBENFORM[kennung][0])

    blau("Ergebnis")
    gut(f"{geprueft} Zeilen vom Pruefer")
    gut(f"{bibel} Bibelbuchnamen aus Ohienko (UBIO)")
    gut(f"{maschinell} Zeilen maschinell, wie bei es und pt")
    warn(f"{korrigiert} maschinelle Vorschlaege ersetzt (KORREKTUR), "
         f"{geleert} geleert (LEER) -- vor den naechsten Pruefer")
    for kennung, (ersatz, masch, beleg) in KORREKTUR.items():
        print(f"   {kennung} {masch[:30]:30} -> {ersatz:18} {beleg}")
    for kennung, (masch, grund) in LEER.items():
        print(f"   {kennung} {masch[:30]:30} -> leer   {grund[:60]}")
    gut(f"{leer} Zeilen der Zusatzlisten fuer uk leer, wie fuer en/ru/fa")
    for kennung, (formen, grund) in NEBENFORM.items():
        print(f"   {kennung} n_uk = {'|'.join(formen)}  -- {grund}")
    for kennung, vermerk in VERMERK.items():
        print(f"   {kennung} {vermerk}")

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
    warn("und erst nach dem Vergleichslauf (werkzeuge/glossar_vergleich.py).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
