#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Das Pruefpaket fuer einen Muttersprachler bauen und wieder einlesen.

    python werkzeuge/sprachpaket.py --bauen pl
    python werkzeuge/sprachpaket.py --einlesen pruefung/rueck_pl/    (Trockenlauf)
    python werkzeuge/sprachpaket.py --einlesen pruefung/rueck_pl/ --scharf

Bis 0.3.0 gab es dieses Skript nicht. Die Pakete fuer Spanisch,
Portugiesisch und Franzoesisch sind von Hand entstanden; eingecheckt
wurden nur die Vorlage und die Auswahl-CSVs. Beim naechsten Mal haette
das wieder jemand nachbauen muessen -- und zwar aus dem Gedaechtnis.

WAS DER PRUEFER BEKOMMT

  1. Begriffsdokument (.docx)
     Die 93 Begriffe der Pruefauswahl, dazu die Texte der
     Zuhoererseite, der QR-Seite und der Anleitung. Spalten: Deutsch,
     Vorschlag, Korrektur. Zwei Vorfragen stehen vorn -- welche
     Bibeluebersetzung gilt, und wie die Gemeinde angeredet wird. Beide
     entscheiden ueber Dutzende Einzelfaelle und gehoeren deshalb VOR
     die Liste.

  2. Bewertungspaket (Ordner mit HTML und WAV)
     Zwanzig Saetze, maschinell uebersetzt und vorgelesen. Acht davon
     sind Fallstricke, die eigens fuer diese Sprache geschrieben
     wurden. Dazu drei Stimmproben zur Auswahl -- die Wahl trifft der
     Pruefer, nicht die Messung. Die Messung sagt nur, welche drei
     ueberhaupt zur Wahl stehen.

WAS ZURUECKKOMMT

  Das ausgefuellte .docx und die CSV-Datei, die der Knopf "Bewertung
  speichern" im Browser erzeugt. --einlesen traegt beides ein.
  IMMER erst als Trockenlauf: er zeigt jede Aenderung einzeln, und
  nichts wird angefasst, solange nicht --scharf dabeisteht.

WARUM NICHT IM REPO

  Die Pakete liegen unter pruefung/paket_<sprache>/ und sind
  gitignoriert. Ein Paket sind rund neun Megabyte Ton, und das Repo
  geht per "git bundle --all" auf jeden Update-Stick. Was einmal darin
  ist, traegt jede Gemeinde fuer immer mit.
"""

import argparse
import csv
import io
import json
import re
import subprocess
import sys
import wave
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))

import config                                        # noqa: E402

PRUEFUNG = WURZEL / "pruefung"
VORLAGE = PRUEFUNG / "vorlagen" / "vorlage_bewertung.html"

GRUEN, GELB, ROT, AUS = "\033[32m", "\033[33m", "\033[31m", "\033[0m"

# Eine Farbe je Sprache, damit zwei offene Pakete nicht verwechselt
# werden. Die drei ersten sind vergeben.
FARBEN = {
    "es": "#a8551f", "pt": "#1f6f4a", "fr": "#3a5ca8",
    "pl": "#8a2f4a", "uk": "#1f6f8a", "ro": "#7a3f8a",
    "it": "#8a6a1f", "nl": "#2f6a5a", "cs": "#6a2f2f",
}
FARBE_VORGABE = "#a86a1f"

# Ankerbeispiele je Sprache: die Faelle, in denen die allgemein
# kirchliche Uebersetzung etwas ANDERES heisst als die adventistische.
#
# Ohne sie lieferte das Modell "Gottesdienst = Usługa kultu",
# "Abendmahl = Wiecień Pański" (kein polnisches Wort) und "Kościół
# Kościoła Adwentystów". Mit ihnen, an denselben acht Begriffen
# gemessen: nabożeństwo, Wieczerza Pańska, Adwentysta Dnia Siódmego.
#
# Kein Ersatz fuer den Muttersprachler. Der Unterschied zwischen einer
# Liste, die er korrigiert, und einer, die er wegwirft. Die Paare
# stehen in fallstricke_<sprache>.csv in Prosa -- hier maschinenlesbar.
ANKER = {
    "pl": [("Gottesdienst", "nabożeństwo", "msza"),
           ("Gemeinde", "zbór", "parafia"),
           ("Abendmahl", "Wieczerza Pańska", "komunia"),
           ("Sabbat", "sabat", "sobota, das ist der Wochentag"),
           ("Ältester", "starszy zboru", "starzec")],
}


def blau(t):
    print(f"\n\033[1;34m== {t}\033[0m")


def gut(t):
    print(f"   {GRUEN}ok{AUS}    {t}")


def warn(t):
    print(f"   {GELB}!{AUS}     {t}")


def fehl(t):
    print(f"   {ROT}FEHLT{AUS} {t}")


# ------------------------------------------------------------ Quellen

def lies_csv(pfad):
    with io.open(pfad, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


def auswahl_datei(sprache):
    """Die 93 Begriffe. Erst eine sprachenreine Datei, sonst die
    gemeinsame -- die Auswahl ist fuer alle Sprachen dieselbe."""
    eigen = PRUEFUNG / f"auswahl_{sprache}.csv"
    if eigen.exists():
        return eigen
    for name in ("auswahl_es_pt_fr.csv", "auswahl_es_pt.csv"):
        if (PRUEFUNG / name).exists():
            return PRUEFUNG / name
    return None


def saetze_datei(sprache):
    eigen = PRUEFUNG / f"saetze_auswahl_{sprache}.csv"
    return eigen if eigen.exists() else PRUEFUNG / "saetze_auswahl.csv"


def glossar_datei():
    """Die juengste Glossarfassung, nicht die aktive.

    Eine neue Sprache wird in der juengsten gepflegt; aktiv geschaltet
    wird sie erst, wenn jemand das ausdruecklich entscheidet."""
    fassungen = sorted(WURZEL.glob("glossar_v*.csv"))
    return fassungen[-1] if fassungen else None


# ------------------------------------------------------- Uebersetzen

def uebersetzen(text, sprache, modell, glossar=None):
    """Dieselbe Kette wie im Betrieb: Glossar plus Sprachmodell.

    Das Glossar wird uebergeben und NICHT aus config.GLOSSAR_CSV
    genommen. Die aktive Datei kennt eine neue Sprache ja gerade noch
    nicht -- sie wird erst aktiv, wenn jemand das entscheidet. Ohne
    diesen Umweg wurden die zwanzig Saetze ohne Fachwortverzeichnis
    uebersetzt, und der Pruefer haette genau die Fehler bewertet, die
    das neue Glossar schon behebt: "Eucharystia" statt "Wieczerza
    Panska", und das im Satz, der diesen Fall pruefen soll.

    Aufgefallen ist es nur, weil glossar.py beim Uebersetzen eine
    Warnung ausgibt -- im Protokoll des Bauens, vier Zeilen vor den
    Ergebnissen."""
    import requests
    from glossar import Glossar, glossarzeilen
    quelle = Path(glossar) if glossar else Path(config.GLOSSAR_CSV)
    if getattr(uebersetzen, "quelle", None) != quelle:
        uebersetzen.g = Glossar.laden(quelle)
        uebersetzen.quelle = quelle
    gtext = glossarzeilen(uebersetzen.g.finde(text), sprache)
    system = (f"Du bist Fachuebersetzer fuer christliche Predigttexte. "
              f"Uebersetze den deutschen Satz nach "
              f"{config.SPRACHNAMEN[sprache]}. Gib ausschliesslich die "
              f"Uebersetzung aus, ohne Erklaerung, ohne "
              f"Anfuehrungszeichen, ohne Formatierung.")
    if gtext:
        system += "\n" + gtext
    a = requests.post(f"{config.OLLAMA_URL}/api/chat",
                      json={"model": modell, "stream": False, "think": False,
                            "options": config.OLLAMA_OPTIONEN,
                            "messages": [{"role": "system", "content": system},
                                         {"role": "user", "content": text}]},
                      timeout=config.OLLAMA_TIMEOUT)
    a.raise_for_status()
    t = a.json()["message"]["content"]
    if "</think>" in t:
        t = t.split("</think>", 1)[1]
    return re.sub(r"\*+", "", t).strip().strip('"')


# ------------------------------------------------------------- Piper

def piper_pfad():
    for k in ([sys.executable, "-m", "piper"], ["piper"]):
        try:
            r = subprocess.run(k + ["--help"], capture_output=True,
                               timeout=30, text=True)
            if r.returncode == 0 or "usage" in (r.stdout + r.stderr).lower():
                return k
        except Exception:
            continue
    return None


def stimme_suchen(name):
    for ordner in (WURZEL / "voices",
                   config.ERGEBNIS_ORDNER / "stimmprobe" / "voices"):
        p = ordner / f"{name}.onnx"
        if p.exists():
            return p
    return None


def sprich(befehl, modell, text, ziel, tempo=1.0):
    """Spricht und gibt die Dauer zurueck.

    Der Text geht ueber eine Datei und -i, nicht ueber stdin: bei stdin
    liest Piper unter Windows in der Konsolen-Codepage, und aus einem
    polnischen "ł" wird Unsinn. Im Pruefpaket faellt das besonders auf
    -- es geht ja gerade um die Sprache."""
    tmp = ziel.with_suffix(".txt")
    tmp.write_text(text, encoding="utf-8")
    r = subprocess.run(befehl + ["-m", str(modell), "-i", str(tmp),
                                 "-f", str(ziel),
                                 "--length-scale", f"{1.0 / tempo:.4f}"],
                       capture_output=True, text=True, timeout=300)
    tmp.unlink(missing_ok=True)
    if r.returncode != 0 or not ziel.exists():
        raise RuntimeError((r.stderr or "piper ohne Ausgabe")[:200])
    with wave.open(str(ziel)) as w:
        return w.getnframes() / w.getframerate()


# ------------------------------------------------- Bewertungspaket

def drei_stimmen(sprache):
    """Die drei Kandidaten mit dem niedrigsten Laengenfaktor.

    Die MESSUNG waehlt nicht aus, sie stellt nur zur Wahl: welche
    Stimme ueber eine dreiviertel Stunde ertraeglich ist, hoert ein
    Mensch und rechnet kein Skript. Die Reihenfolge A, B, C ist die
    der Messung, sagt dem Pruefer aber nichts -- er soll hoeren, nicht
    Rangfolgen lesen."""
    datei = WURZEL / "messungen" / "laengenfaktor_stimmen.json"
    if not datei.exists():
        return []
    d = json.loads(datei.read_text(encoding="utf-8"))
    # Die Messwerte liegen unter "stimmen"; daneben steht, wogegen
    # gemessen wurde. Ohne den Griff dorthin fand diese Funktion
    # lautlos nichts -- und das Paket waere ohne Stimmprobe gebaut
    # worden, ohne dass es jemandem aufgefallen waere.
    st = d.get("stimmen", d)
    kandidaten = [(name, w) for name, w in st.items()
                  if isinstance(w, dict) and w.get("sprache") == sprache]
    kandidaten.sort(key=lambda p: (p[1].get("gegen_deutsch", 9),
                                   p[1].get("streuung", 9)))
    return kandidaten[:3]


def paket_bauen(sprache, modell, tempo=None, glossar=None):
    name = config.SPRACHNAMEN.get(sprache, sprache)
    ziel = PRUEFUNG / f"paket_{sprache}"
    ziel.mkdir(parents=True, exist_ok=True)

    befehl = piper_pfad()
    if not befehl:
        sys.exit("Piper nicht gefunden. pip install piper-tts")

    saetze = lies_csv(saetze_datei(sprache))
    if len(saetze) != 20:
        warn(f"{len(saetze)} Saetze statt 20 -- die Vorlage rechnet mit 20.")

    stimmen = drei_stimmen(sprache)
    if not stimmen:
        sys.exit(f"Keine gemessene Stimme fuer {sprache}. Erst:\n"
                 f"  python laengenfaktor.py --je-stimme --nur {sprache}")
    blau("Stimmen")
    for buchstabe, (stimme, wert) in zip("ABC", stimmen):
        gut(f"{buchstabe}: {stimme}  "
            f"Faktor {wert['gegen_deutsch']}  Streuung {wert['streuung']}")

    # Gesprochen wird mit der ERSTEN, also der gemessen kuerzesten.
    # Sie ist noch nicht gewaehlt -- aber eine muss die zwanzig Saetze
    # sprechen, und die kuerzeste verzerrt am wenigsten.
    haupt = stimme_suchen(stimmen[0][0])
    if not haupt:
        sys.exit(f"{stimmen[0][0]}.onnx liegt nirgends.")
    faktor = tempo or config.TEMPO_STIMME.get(
        stimmen[0][0], config.TEMPO_SPRACHE.get(sprache, config.TEMPO_VORGABE))

    blau("Stimmproben")
    probe = (PRUEFUNG / "predigtteil.txt").read_text(encoding="utf-8").strip()
    for buchstabe, (stimme, _) in zip("ABC", stimmen):
        pfad = stimme_suchen(stimme)
        if not pfad:
            warn(f"{stimme} fehlt, Probe {buchstabe} entfaellt")
            continue
        dauer = sprich(befehl, pfad, probe, ziel / f"stimme_{buchstabe}.wav",
                       faktor)
        gut(f"stimme_{buchstabe}.wav  {dauer:.1f}s  ({stimme})")

    blau(f"Zwanzig Saetze nach {name}")
    zeilen = []
    for r in saetze:
        nr = r["nummer"]
        satz = r["satz"]
        ziel_text = uebersetzen(satz, sprache, modell,
                                glossar or glossar_datei())
        wav = ziel / f"{nr}_{sprache}.wav"
        dauer = sprich(befehl, haupt, ziel_text, wav, faktor)
        # Die deutsche Sprechdauer derselben Referenzstimme -- damit der
        # Pruefer sieht, ob die Uebersetzung laenger geworden ist.
        de_stimme = stimme_suchen(
            config.STIMMEN["de"].split("/")[-1])
        de_dauer = 0.0
        if de_stimme:
            de_wav = ziel / f"_de_{nr}.wav"
            de_dauer = sprich(befehl, de_stimme, satz, de_wav, 1.0)
            de_wav.unlink(missing_ok=True)
        zeilen.append({"nummer": nr, "de": satz, "ziel": ziel_text,
                       "dauer": dauer, "de_dauer": de_dauer,
                       "fokus": r.get("prueffokus", "")})
        print(f"   {nr}  {de_dauer:4.1f}s -> {dauer:4.1f}s  "
              f"{ziel_text[:54]}")

    html_schreiben(sprache, name, zeilen, bool(stimmen), ziel)
    gut(f"bewertung_{sprache}.html")
    return ziel, zeilen


def html_schreiben(sprache, name, zeilen, mit_stimmproben, ziel):
    """Fuellt vorlagen/vorlage_bewertung.html.

    Die Vorlage traegt zwei Beispielsaetze. Sie werden durch die echten
    ersetzt -- nicht ergaenzt: sonst stuenden BEISPIEL-Zeilen im Paket,
    und der Pruefer bewertet eine Zeile, die es nicht gibt."""
    roh = VORLAGE.read_text(encoding="utf-8")
    farbe = FARBEN.get(sprache, FARBE_VORGABE)

    def satzblock(z):
        return f'''    <article class="satz" id="satz{int(z["nummer"])}">
      <header>
        <span class="nummer">{int(z["nummer"])}</span>
        <p class="original" lang="de">{schuetzen(z["de"])}</p>
        <span class="laenge">{z["de_dauer"]:.1f}s gesprochen</span>
      </header>
      <div class="spuren">
      <div class="spur" data-satz="{int(z["nummer"])}" data-sprache="{sprache}"
           style="--ton:{farbe}">
        <div class="kopf">
          <span class="sprache">{schuetzen(name)}</span>
          <span class="dauer">{z["dauer"]:.1f}s</span>
        </div>
        <audio preload="none" src="{z["nummer"]}_{sprache}.wav"></audio>
        <button class="spielen" type="button">Abspielen</button>
        <p class="ziel" dir="auto" lang="{sprache}">{schuetzen(z["ziel"])}</p>
        <div class="noten" role="group" aria-label="Bewertung">
          <button type="button" data-note="1">gut</button>
          <button type="button" data-note="2">brauchbar</button>
          <button type="button" data-note="3">unbrauchbar</button>
        </div>
        <input class="notiz" type="text" placeholder="Anmerkung, optional">
      </div></div>
    </article>'''

    # Der Bauhinweis der Vorlage gehoert nicht ins fertige Paket. Er
    # nennt die Platzhalter, und die werden weiter unten ersetzt --
    # danach stand dort "pl -> es | pt", was den Pruefer nur verwirrt.
    if roh.lstrip().startswith("<!doctype") and "\n<!--" in roh[:200]:
        a = roh.index("\n<!--")
        e = roh.index("-->", a) + len("-->")
        roh = roh[:a] + roh[e:]

    # Die beiden Beispielbloecke der Vorlage herausschneiden.
    a = roh.index('    <article class="satz" id="satz1">')
    b = roh.index("</main>", a)
    roh = roh[:a] + "\n\n".join(satzblock(z) for z in zeilen) + "\n\n" + roh[b:]

    if not mit_stimmproben:
        s = roh.index('  <!-- Stimmprobe')
        e = roh.index("</section>", s) + len("</section>")
        roh = roh[:s] + roh[e:]

    roh = roh.replace("SPRACHKUERZEL", sprache).replace("SPRACHNAME", name)
    roh = roh.replace("--ton:#a86a1f", f"--ton:{farbe}")
    (ziel / f"bewertung_{sprache}.html").write_text(roh, encoding="utf-8")


def schuetzen(t):
    return (str(t).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


# ---------------------------------------------------------- Glossar

def glossar_ergaenzen(sprache, modell, quelle=None, ziel=None):
    """Traegt eine neue Sprachspalte in die juengste Glossarfassung.

    Geschrieben wird eine NEUE Fassung, nie die bestehende: die aktive
    Datei steht in config.GLOSSAR_CSV, und welche das ist, entscheidet
    ein Mensch nach einem Testlauf -- nicht dieses Skript.

    Zwei Spalten, <sp> und k_<sp>. Ohne die zweite erkennt glossar.py
    die Sprache gar nicht; das ist Absicht und steht dort erklaert. Die
    Konfidenz wird von der englischen Spalte uebernommen: sie
    beschreibt, wie eindeutig der BEGRIFF ist, nicht wie gut die
    Uebersetzung -- und das ist fuer jede Zielsprache dasselbe."""
    quelle = Path(quelle) if quelle else glossar_datei()
    zeilen = lies_csv(quelle)
    with io.open(quelle, encoding="utf-8-sig", newline="") as f:
        kopf = next(csv.reader(f, delimiter=";"))
    if sprache in kopf:
        warn(f"{quelle.name} hat schon eine Spalte {sprache}.")
        return quelle

    if ziel is None:
        # v0.7 -> v0.8
        m = re.search(r"v(\d+)\.(\d+)", quelle.name)
        neu_nr = f"v{m.group(1)}.{int(m.group(2)) + 1}" if m else "v0.8"
        ziel = quelle.with_name(re.sub(r"v\d+\.\d+", neu_nr, quelle.name))
    ziel = Path(ziel)

    name = config.SPRACHNAMEN.get(sprache, sprache)
    blau(f"Glossar: {len(zeilen)} Begriffe nach {name}")
    system = (
        f"Du uebersetzt theologische Fachbegriffe der Siebenten-Tags-"
        f"Adventisten aus dem Deutschen nach {name}.\n"
        f"Nimm die Form, die eine adventistische Gemeinde amtlich "
        f"benutzt -- NICHT die roemisch-katholische.")
    anker = ANKER.get(sprache)
    if anker:
        system += "\nBeispiele:  " + "  ".join(
            f"{a} = {b} (nicht {c})" for a, b, c in anker)
    else:
        warn(f"Keine Ankerbeispiele fuer {sprache} in ANKER -- die "
             f"Vorschlaege werden dadurch deutlich schlechter.")
    system += ("\nGib NUR den uebersetzten Begriff aus. Keine "
               "Erklaerung, keine Alternativen, kein Satz, keine "
               "Anfuehrungszeichen.")

    import requests
    for i, r in enumerate(zeilen, 1):
        hinweis = (r.get("anmerkung") or "").strip()
        englisch = (r.get("en") or "").strip()
        frage = r["de"]
        if englisch:
            frage += f"   (englisch: {englisch})"
        if hinweis:
            frage += f"   (Hinweis: {hinweis})"
        a = requests.post(
            f"{config.OLLAMA_URL}/api/chat",
            json={"model": modell, "stream": False, "think": False,
                  "options": config.OLLAMA_OPTIONEN,
                  "messages": [{"role": "system", "content": system},
                               {"role": "user", "content": frage}]},
            timeout=config.OLLAMA_TIMEOUT)
        a.raise_for_status()
        t = a.json()["message"]["content"]
        if "</think>" in t:
            t = t.split("</think>", 1)[1]
        t = re.sub(r"\*+", "", t).strip().strip('"').split("\n")[0].strip()
        r[sprache] = t
        r["k_" + sprache] = r.get("k_en", "")
        if i % 25 == 0 or i == len(zeilen):
            print(f"   {i}/{len(zeilen)}  {r['de']} -> {t}")

    spalten = kopf + [sprache, "k_" + sprache]
    with io.open(ziel, "w", encoding="utf-8-sig", newline="") as f:
        s = csv.DictWriter(f, fieldnames=spalten, delimiter=";")
        s.writeheader()
        s.writerows(zeilen)
    gut(f"{ziel.name} geschrieben ({len(zeilen)} Begriffe, "
        f"Spalten {sprache} und k_{sprache})")
    warn("NICHT aktiv geschaltet. config.GLOSSAR_CSV bleibt, "
         "wo es stand.")
    return ziel


# ----------------------------------------------- Oberflaechentexte

def vorschlag_datei(sprache):
    return PRUEFUNG / f"vorschlag_{sprache}.json"


def texte_uebersetzen(sprache, modell):
    """Maschinenvorschlaege fuer Oberflaeche, QR-Seite und Anleitung.

    Ohne sie stuende im Dokument neben jedem deutschen Satz eine leere
    Zelle, und der Pruefer muesste 62 Texte SELBST uebersetzen statt
    sie durchzusehen. Das ist ein anderer Auftrag und dauert ein
    Vielfaches.

    Gespeichert als JSON unter pruefung/, nicht im Programm: es sind
    Vorschlaege, keine Texte. Ins Programm kommen sie erst ueber
    --einlesen, nachdem ein Mensch sie gesehen hat."""
    name = config.SPRACHNAMEN.get(sprache, sprache)
    ui, qr, an = ui_texte(), qr_texte_de(), anleitung_absaetze()
    blau(f"Oberflaechentexte nach {name} "
         f"({len(ui)} + {len(qr)} + {len(an)})")

    kurz = ("Du uebersetzt die Oberflaeche einer App fuer eine "
            f"adventistische Gemeinde aus dem Deutschen nach {name}. "
            "Es sind Knoepfe und kurze Hinweise auf einem Handy -- "
            "halte dich KURZ, so kurz wie das Deutsche. Gib nur die "
            "Uebersetzung aus.")
    lang = ("Du uebersetzt eine Anleitung fuer Gottesdienstbesucher "
            f"aus dem Deutschen nach {name}. Behalte Markdown-Zeichen "
            "(#, **, -) unveraendert bei. Gib nur die Uebersetzung aus.")

    import requests

    def durch(text, system):
        a = requests.post(
            f"{config.OLLAMA_URL}/api/chat",
            json={"model": modell, "stream": False, "think": False,
                  "options": config.OLLAMA_OPTIONEN,
                  "messages": [{"role": "system", "content": system},
                               {"role": "user", "content": text}]},
            timeout=config.OLLAMA_TIMEOUT)
        a.raise_for_status()
        t = a.json()["message"]["content"]
        if "</think>" in t:
            t = t.split("</think>", 1)[1]
        return t.strip().strip('"')

    d = {"ui": {}, "qr": {}, "an": []}
    for k, v in ui.items():
        d["ui"][k] = durch(v, kurz)
    gut(f"Zuhoererseite: {len(d['ui'])}")
    for k, v in qr.items():
        d["qr"][k] = durch(v, kurz)
    gut(f"QR-Seite: {len(d['qr'])}")
    for a in an:
        d["an"].append(durch(a, lang))
    gut(f"Anleitung: {len(d['an'])}")

    ziel = vorschlag_datei(sprache)
    ziel.write_text(json.dumps(d, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    gut(f"{ziel.name}")
    return d


# ------------------------------------------------ Begriffsdokument

def ui_texte():
    """Die Texte der Zuhoererseite, deutsch, in Reihenfolge."""
    h = (WURZEL / "client.html").read_text(encoding="utf-8")
    m = re.search(r"const TEXTE = \{(.*?)\n\};", h, re.S)
    if not m:
        return {}
    block = m.group(1)
    teil = re.split(r"\n  [a-z]{2}:\{", block)
    if len(teil) < 2:
        return {}
    # Nur der deutsche Abschnitt, und daraus Schluessel + Text.
    roh = teil[1]
    paare = {}
    for k, v in re.findall(
            r'(?:^|[{,]\s*|\n\s*)([a-zA-Z][a-zA-Z_]*)\s*:\s*"((?:[^"\\]|\\.)*)"',
            roh):
        paare.setdefault(k, v.replace('\\"', '"'))
    return paare


def qr_texte_de():
    sys.path.insert(0, str(WURZEL))
    import qr_texte
    return dict(qr_texte.TEXTE["de"])


def anleitung_absaetze():
    """Teil A der Anleitung, Absatz fuer Absatz."""
    quelle = WURZEL / "anleitung" / "01_zuhoerer.md"
    if not quelle.exists():
        return []
    roh = quelle.read_text(encoding="utf-8")
    teile, puffer = [], []
    for zeile in roh.split("\n"):
        if zeile.strip():
            puffer.append(zeile.strip())
        elif puffer:
            teile.append(" ".join(puffer))
            puffer = []
    if puffer:
        teile.append(" ".join(puffer))
    return teile


def docx_bauen(sprache, ziel=None, glossar=None):
    try:
        from docx import Document
    except ImportError:
        sys.exit(
            "python-docx fehlt.\n"
            "  Es liegt im BAU-venv, nicht im Laufzeit-venv -- der\n"
            "  Gemeinderechner soll kein Paket bekommen, das er nie\n"
            "  braucht. Also:\n"
            "    .bau-venv/bin/python werkzeuge/sprachpaket.py --dokument "
            + sprache)
    from docx.shared import Pt, Cm, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    name = config.SPRACHNAMEN.get(sprache, sprache)
    ziel = Path(ziel) if ziel else PRUEFUNG / f"begriffe_{sprache}.docx"
    auswahl = lies_csv(auswahl_datei(sprache))
    vd = vorschlag_datei(sprache)
    vorschlag = json.loads(vd.read_text(encoding="utf-8")) if vd.exists() else {}
    if not vorschlag:
        warn(f"{vd.name} fehlt -- die Spalte Vorschlag bleibt bei "
             f"Oberflaeche und Anleitung leer.")
    vorschlaege = {}
    if glossar and Path(glossar).exists():
        for r in lies_csv(glossar):
            vorschlaege[r["id"]] = (r.get(sprache) or "").strip()

    d = Document()
    for abschnitt in d.sections:
        # python-docx liefert ab Werk Letter. Ein Prueffer in Polen
        # oder Deutschland druckt auf A4, und eine Tabelle, die rechts
        # ueber den Rand laeuft, ist genau in der Spalte abgeschnitten,
        # die er ausfuellen soll.
        abschnitt.page_width, abschnitt.page_height = Cm(21), Cm(29.7)
        abschnitt.left_margin = abschnitt.right_margin = Cm(1.6)
        abschnitt.top_margin = abschnitt.bottom_margin = Cm(1.8)
    normal = d.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(11)

    d.add_heading(f"Devarenu – Fachbegriffe auf {name}", level=0)
    p = d.add_paragraph()
    p.add_run(
        "Vielen Dank, dass Sie sich die Zeit nehmen. Devarenu übersetzt "
        "den Gottesdienst live auf das Handy der Zuhörer. Die Begriffe "
        "unten hat bisher nur ein Computer übersetzt. Sie entscheiden, "
        "was eine adventistische Gemeinde wirklich sagt.")
    p = d.add_paragraph()
    r = p.add_run("So geht es: Bitte nur die Spalte „Korrektur“ ausfüllen. "
                  "Was Sie leer lassen, gilt als richtig.")
    r.bold = True

    # ---- Die zwei Vorfragen
    d.add_heading("Zuerst zwei Fragen", level=1)
    p = d.add_paragraph()
    p.add_run("1. Welche Bibelübersetzung gilt?").bold = True
    d.add_paragraph(
        "Die Namen der biblischen Bücher und die Schreibweise der "
        "Stellenangaben richten sich danach. Bitte nennen Sie die "
        "Übersetzung, die in Ihren Gemeinden gelesen wird.")
    d.add_paragraph("Antwort: ______________________________________________")

    p = d.add_paragraph()
    p.add_run("2. Wie wird die Gemeinde angeredet?").bold = True
    d.add_paragraph(
        "Im Deutschen heißt es „Liebe Geschwister“ und „Sie“. Wie "
        "spricht ein Prediger die versammelte Gemeinde an – förmlich "
        "oder vertraut, und mit welchem Wort?")
    d.add_paragraph("Antwort: ______________________________________________")

    d.add_paragraph(
        "Beide Antworten entscheiden über Dutzende Einzelfälle weiter "
        "unten. Deshalb stehen sie vorn.")

    def tabelle(zeilen, mit_kontext=False):
        spalten = ["Kennung", "Deutsch", "Vorschlag", "Korrektur"]
        if mit_kontext:
            spalten.insert(2, "Zusammenhang")
        t = d.add_table(rows=1, cols=len(spalten))
        t.style = "Table Grid"
        for i, s in enumerate(spalten):
            zelle = t.rows[0].cells[i]
            zelle.text = ""
            lauf = zelle.paragraphs[0].add_run(s)
            lauf.bold = True
            lauf.font.size = Pt(9)
        for z in zeilen:
            r = t.add_row().cells
            werte = [z["kennung"], z["de"], z["vorschlag"], ""]
            if mit_kontext:
                werte.insert(2, z.get("kontext", ""))
            for i, w in enumerate(werte):
                r[i].text = ""
                lauf = r[i].paragraphs[0].add_run(str(w))
                lauf.font.size = Pt(10)
                if i == 0:
                    # Die Kennung geht den Pruefer nichts an -- sie ist
                    # der Rueckweg. Ausgegraut, damit sie nicht
                    # mitgelesen wird.
                    lauf.font.size = Pt(7)
                    lauf.font.color.rgb = RGBColor(0x99, 0x99, 0x99)
        # Spaltenbreiten. Die KORREKTUR ist die breiteste -- in sie
        # wird geschrieben, und zwar von Hand. Die Kennung bekommt so
        # wenig wie moeglich.
        #
        # Word beachtet die Breite nur, wenn sie an JEDER Zelle steht;
        # am Tabellenobjekt allein bleibt sie wirkungslos. Das ist
        # keine Eigenheit von python-docx, sondern von Word.
        breiten = ([Cm(1.3), Cm(4.2), Cm(4.2), Cm(3.6), Cm(4.5)]
                   if mit_kontext else [Cm(1.3), Cm(6.4), Cm(5.0), Cm(5.1)])
        t.autofit = False
        for reihe in t.rows:
            for zelle, breite in zip(reihe.cells, breiten):
                zelle.width = breite
        return t

    # ---- 1) Die Begriffe
    d.add_page_break()
    d.add_heading(f"Fachbegriffe ({len(auswahl)})", level=1)
    d.add_paragraph(
        "Die Spalte „Zusammenhang“ sagt, in welchem Sinn das Wort im "
        "Gottesdienst vorkommt. Achten Sie besonders darauf, wo eine "
        "allgemein kirchliche Übersetzung etwas anderes bedeutet als "
        "die adventistische.")
    blockname = {"A": "Bibelbücher", "C": "Theologie",
                 "D": "Adventistisch"}
    for block in ("D", "C", "A"):
        teil = [r for r in auswahl if r["block"] == block]
        if not teil:
            continue
        d.add_heading(f"{blockname.get(block, block)} ({len(teil)})", level=2)
        tabelle([{"kennung": r["id"], "de": r["de"],
                  "kontext": (r.get("anmerkung") or "").strip()
                             or f"englisch: {r.get('en', '')}",
                  "vorschlag": vorschlaege.get(r["id"], "")}
                 for r in teil], mit_kontext=True)

    # ---- 2) Zuhoererseite
    d.add_page_break()
    d.add_heading("Texte der Zuhörerseite", level=1)
    d.add_paragraph(
        "Das sieht der Zuhörer auf dem Handy: Knöpfe, Hinweise, "
        "Fehlermeldungen. Kurz halten – auf einem Telefon ist wenig "
        "Platz.")
    ui = ui_texte()
    tabelle([{"kennung": f"UI.{k}", "de": v,
              "vorschlag": vorschlag.get("ui", {}).get(k, "")}
             for k, v in ui.items()])

    # ---- 3) QR-Seite
    d.add_heading("Texte der QR-Seite (Beamer)", level=1)
    d.add_paragraph(
        "Diese Sätze stehen während des Gottesdienstes an der Wand und "
        "wechseln alle acht Sekunden die Sprache. Sie müssen aus zwölf "
        "Metern lesbar sein – je kürzer, desto besser.")
    qr = qr_texte_de()
    tabelle([{"kennung": f"QR.{k}", "de": v,
              "vorschlag": vorschlag.get("qr", {}).get(k, "")}
             for k, v in qr.items()])

    # ---- 4) Anleitung
    d.add_page_break()
    d.add_heading("Anleitung für die Zuhörer", level=1)
    d.add_paragraph(
        "Ein Blatt zum Ausdrucken und Auslegen. Hier darf es ganze "
        "Sätze sein.")
    vorab = vorschlag.get("an", [])
    tabelle([{"kennung": f"AN.{i:02d}", "de": a,
              "vorschlag": vorab[i - 1] if i <= len(vorab) else ""}
             for i, a in enumerate(anleitung_absaetze(), 1)])

    d.add_page_break()
    p = d.add_paragraph()
    p.add_run("Fertig? Dann bitte die Datei zurückschicken an "
              f"{config.RUECKMELDUNG_MAIL}. ").bold = True
    d.add_paragraph(
        "Und wenn etwas grundsätzlich falsch wirkt – nicht nur ein "
        "Wort, sondern der ganze Ton –, schreiben Sie es bitte dazu. "
        "Das ist wertvoller als jede Einzelkorrektur.")

    ziel.parent.mkdir(parents=True, exist_ok=True)
    d.save(str(ziel))
    return ziel


# ------------------------------------------------------- Rueckweg

def einlesen(ordner, scharf=False):
    """Traegt ein, was zurueckkam. Ohne --scharf wird nichts angefasst.

    Erwartet in einem Ordner:
      begriffe_<sp>.docx    das ausgefuellte Dokument
      bewertung_<sp>.csv    was der Knopf im Browser gespeichert hat

    Der Trockenlauf ist die Vorgabe und nicht eine Option. Was hier
    eingetragen wird, sind die Worte, die im Gottesdienst gesprochen
    werden -- das sieht man sich vorher an."""
    from docx import Document
    ordner = Path(ordner)
    docxe = sorted(ordner.glob("begriffe_*.docx"))
    if not docxe:
        sys.exit(f"Kein begriffe_*.docx in {ordner}")
    quelle = docxe[0]
    sprache = quelle.stem.split("_", 1)[1]
    name = config.SPRACHNAMEN.get(sprache, sprache)
    blau(f"{quelle.name}  ({name})")

    d = Document(str(quelle))
    korrekturen, vorfragen = {}, []
    for t in d.tables:
        kopf = [z.text.strip() for z in t.rows[0].cells]
        if "Korrektur" not in kopf:
            continue
        i_k, i_de = kopf.index("Korrektur"), kopf.index("Deutsch")
        i_id = kopf.index("Kennung")
        i_v = kopf.index("Vorschlag")
        for r in t.rows[1:]:
            neu = r.cells[i_k].text.strip()
            if not neu:
                continue
            korrekturen[r.cells[i_id].text.strip()] = {
                "de": r.cells[i_de].text.strip(),
                "alt": r.cells[i_v].text.strip(), "neu": neu}
    for p in d.paragraphs:
        if p.text.startswith("Antwort:"):
            antwort = p.text[len("Antwort:"):].strip(" _")
            if antwort:
                vorfragen.append(antwort)

    if vorfragen:
        blau("Vorfragen")
        for a in vorfragen:
            gut(a)

    blau(f"{len(korrekturen)} Korrekturen")
    nach_bereich = {}
    for kennung, w in korrekturen.items():
        bereich = kennung.split(".")[0] if "." in kennung else "GLOSSAR"
        nach_bereich.setdefault(bereich, []).append((kennung, w))
    for bereich, liste in sorted(nach_bereich.items()):
        print(f"\n   \033[1m{bereich}\033[0m  ({len(liste)})")
        for kennung, w in liste:
            print(f"     {kennung:14} {w['de'][:34]:34}")
            print(f"     {'':14} {ROT}{w['alt'][:60]}{AUS}")
            print(f"     {'':14} {GRUEN}{w['neu'][:60]}{AUS}")

    bewertung = sorted(ordner.glob("bewertung_*.csv"))
    gewaehlte_stimme = ""
    if bewertung:
        blau(bewertung[0].name)
        zeilen = [z for z in io.open(bewertung[0], encoding="utf-8-sig")
                  if z.strip()]
        noten = {}
        for z in zeilen:
            teile = z.rstrip("\n").split(";")
            if teile and teile[0] == "stimme" and len(teile) > 2:
                gewaehlte_stimme = teile[2]
            elif len(teile) >= 3 and teile[2].isdigit():
                noten[teile[2]] = noten.get(teile[2], 0) + 1
        for note, anzahl in sorted(noten.items()):
            wort = {"1": "gut", "2": "brauchbar", "3": "unbrauchbar"}
            gut(f"{wort.get(note, note)}: {anzahl}")
        if gewaehlte_stimme:
            gut(f"gewaehlte Stimme: {gewaehlte_stimme}")

    if not scharf:
        print()
        warn("TROCKENLAUF. Nichts geaendert.")
        warn("Uebernehmen mit  --scharf")
        return

    blau("Eintragen")
    geaendert = schreiben(sprache, korrekturen, gewaehlte_stimme)
    for zeile in geaendert:
        gut(zeile)
    print()
    warn("pl gilt jetzt als geprueft. Vor dem Commit einmal "
         "ansehen, was sich geaendert hat:  git diff")


def schreiben(sprache, korrekturen, stimme=""):
    """Traegt die Korrekturen an ihre Stellen. Gibt zurueck, was geschah."""
    getan = []

    # ---- Glossar: Kennungen ohne Punkt (A001, C012, D033)
    begriffe = {k: w for k, w in korrekturen.items() if "." not in k}
    if begriffe:
        datei = glossar_datei()
        zeilen = lies_csv(datei)
        with io.open(datei, encoding="utf-8-sig", newline="") as f:
            kopf = next(csv.reader(f, delimiter=";"))
        treffer = 0
        for r in zeilen:
            if r["id"] in begriffe:
                r[sprache] = begriffe[r["id"]]["neu"]
                treffer += 1
        with io.open(datei, "w", encoding="utf-8-sig", newline="") as f:
            s = csv.DictWriter(f, fieldnames=kopf, delimiter=";")
            s.writeheader()
            s.writerows(zeilen)
        getan.append(f"{datei.name}: {treffer} Begriffe")

    # ---- Oberflaeche, QR-Seite, Anleitung
    #
    # Der Pruefer korrigiert nur, was ihm auffaellt. Alles andere
    # bleibt beim Maschinenvorschlag -- der steht in vorschlag_<sp>.json
    # und wird hier zusammengefuehrt. Ohne ihn fehlten alle Texte, die
    # in Ordnung waren, und das waere das Gegenteil von "leer lassen
    # heisst passt".
    vd = vorschlag_datei(sprache)
    vorschlag = json.loads(vd.read_text(encoding="utf-8")) if vd.exists() else {}

    def zusammen(praefix, vorgabe):
        fertig = dict(vorgabe)
        for k, w in korrekturen.items():
            if k.startswith(praefix + "."):
                fertig[k.split(".", 1)[1]] = w["neu"]
        return fertig

    ui = zusammen("UI", vorschlag.get("ui", {}))
    if ui:
        n = client_html_schreiben(sprache, ui)
        getan.append(f"client.html: {n} Texte")

    qr = zusammen("QR", vorschlag.get("qr", {}))
    if qr:
        n = qr_texte_schreiben(sprache, qr)
        getan.append(f"qr_texte.py: {n} Texte")

    absaetze = list(vorschlag.get("an", []))
    for k, w in korrekturen.items():
        if k.startswith("AN."):
            i = int(k.split(".", 1)[1]) - 1
            while len(absaetze) <= i:
                absaetze.append("")
            absaetze[i] = w["neu"]
    if any(a.strip() for a in absaetze):
        ziel = WURZEL / "anleitung" / f"01_zuhoerer.{sprache}.md"
        ziel.write_text("\n\n".join(absaetze).rstrip() + "\n",
                        encoding="utf-8")
        getan.append(f"{ziel.name}: {len(absaetze)} Absaetze "
                     f"(PDF neu bauen: bash anleitung_bauen.sh)")

    # ---- Stimme
    if stimme:
        getan.append(f"gewaehlte Stimme {stimme} -- config.STIMMEN "
                     f"von Hand setzen")

    # ---- als geprueft markieren
    p = WURZEL / "config.py"
    s = p.read_text(encoding="utf-8")
    m = re.search(r"GEPRUEFT = \{([^}]*)\}", s)
    if m and f'"{sprache}"' not in m.group(1):
        neu = m.group(0).replace("}", f', "{sprache}"}}')
        p.write_text(s.replace(m.group(0), neu), encoding="utf-8")
        getan.append(f"config.GEPRUEFT um {sprache} ergaenzt")
    return getan


def _js(t):
    """Eine Zeichenkette fuer client.html."""
    return (str(t).replace("\\", "\\\\").replace('"', '\\"')
            .replace("\n", " ").strip())


def client_html_schreiben(sprache, texte):
    """Traegt einen Sprachblock in TEXTE ein.

    NUR innerhalb von "const TEXTE = {...}". Der erste Anlauf suchte
    "\\n  pl:{" in der ganzen Datei -- und fand den Eintrag in
    EIGENNAME, der weiter oben steht. Der Sprachblock ueberschrieb
    dort Name, Kuerzel und Schreibrichtung, und die Texte landeten in
    der falschen Tabelle. Aufgefallen beim Probelauf des Rueckwegs,
    nicht beim Lesen.

    Vorhandene Sprachen bleiben unangetastet: gesucht wird der eigene
    Block, und nur der wird ersetzt. Gibt es ihn noch nicht, kommt er
    ans Ende -- vor die schliessende Klammer, nicht dahinter."""
    p = WURZEL / "client.html"
    s = p.read_text(encoding="utf-8")
    block = f"  {sprache}:{{" + ",\n      ".join(
        f'{k}:"{_js(v)}"' for k, v in texte.items()) + "},\n"

    rahmen = re.search(r"const TEXTE = \{.*?\n\};", s, re.S)
    if not rahmen:
        raise RuntimeError("const TEXTE = { ... } nicht gefunden")
    innen = rahmen.group(0)

    m = re.search(rf"\n  {sprache}:\{{.*?\n(?=  [a-z]{{2}}:\{{|\}};)", innen,
                  re.S)
    if m:
        neu = innen[:m.start()] + "\n" + block + innen[m.end():]
    else:
        schluss = innen.rindex("\n};")
        neu = innen[:schluss] + "\n" + block + innen[schluss:]
    s = s[:rahmen.start()] + neu + s[rahmen.end():]
    p.write_text(s, encoding="utf-8")
    return len(texte)


def qr_texte_schreiben(sprache, texte):
    """Traegt einen Sprachblock in qr_texte.TEXTE ein."""
    p = WURZEL / "qr_texte.py"
    s = p.read_text(encoding="utf-8")

    def py(t):
        return str(t).replace("\\", "\\\\").replace('"', '\\"')

    block = (f'    "{sprache}": {{\n' + "".join(
        f'        "{k}": "{py(v)}",\n' for k, v in texte.items()) + "    },\n")
    m = re.search(rf'\n    "{sprache}": \{{.*?\n    \}},\n', s, re.S)
    if m:
        s = s[:m.start()] + "\n" + block + s[m.end():]
    else:
        # Vor die schliessende Klammer von TEXTE.
        i = s.index("\nTEXTE = {")
        j = s.index("\n}\n", i)
        s = s[:j + 1] + block + s[j + 1:]
    p.write_text(s, encoding="utf-8")
    return len(texte)


# ----------------------------------------------------------- Aufruf

def main():
    p = argparse.ArgumentParser(
        description="Pruefpaket bauen und wieder einlesen.")
    p.add_argument("--bauen", metavar="SPRACHE",
                   help="Glossarspalte, Uebersetzungen und Bewertungspaket "
                        "(Laufzeit-venv: braucht Ollama und Piper)")
    p.add_argument("--dokument", metavar="SPRACHE",
                   help="nur das Begriffsdokument .docx "
                        "(BAU-venv: braucht python-docx)")
    p.add_argument("--glossar", metavar="SPRACHE",
                   help="nur die Glossarspalte ergaenzen")
    p.add_argument("--einlesen", metavar="ORDNER",
                   help="ausgefuelltes Paket einlesen (Trockenlauf)")
    p.add_argument("--scharf", action="store_true",
                   help="beim Einlesen wirklich schreiben")
    p.add_argument("--modell", default="gemma4:12b")
    p.add_argument("--ohne-ton", action="store_true",
                   help="nur das Dokument, keine Sprachausgabe")
    a = p.parse_args()

    if a.einlesen:
        einlesen(a.einlesen, a.scharf)
        return
    if a.glossar:
        glossar_ergaenzen(a.glossar, a.modell)
        return
    if a.dokument:
        blau("Begriffsdokument")
        doc = docx_bauen(a.dokument, glossar=glossar_datei())
        gut(f"{doc.relative_to(WURZEL)}  ({doc.stat().st_size // 1024} KB)")
        return
    if not a.bauen:
        p.print_help()
        return

    sprache = a.bauen
    if sprache not in config.SPRACHNAMEN:
        sys.exit(f"{sprache} kennt config.SPRACHNAMEN nicht.")

    g = glossar_datei()
    with io.open(g, encoding="utf-8-sig", newline="") as f:
        kopf = next(csv.reader(f, delimiter=";"))
    if sprache not in kopf:
        g = glossar_ergaenzen(sprache, a.modell)

    if not vorschlag_datei(sprache).exists():
        texte_uebersetzen(sprache, a.modell)

    if a.ohne_ton:
        warn("--ohne-ton: kein Bewertungspaket gebaut.")
        return
    ordner, _ = paket_bauen(sprache, a.modell, glossar=g)
    blau("Fertig")
    gut(f"Paket: {ordner.relative_to(WURZEL)}/")
    print()
    warn("Das Begriffsdokument braucht das Bau-venv:")
    warn(f"  .bau-venv/bin/python werkzeuge/sprachpaket.py "
         f"--dokument {sprache}")


if __name__ == "__main__":
    main()
