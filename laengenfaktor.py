#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Misst, wie viel laenger die gesprochene Uebersetzung dauert als das Original.

Gemessen wird gegen die ECHTE Sprechdauer aus woerter.json, nicht gegen
eine synthetische deutsche Referenz. Genau dieses Verhaeltnis braucht die
Simulation: der Prediger spricht, Piper muss hinterherkommen.

Deutsches Piper wird mitgemessen, um zwei Effekte zu trennen: spricht
Piper generell anders schnell als der Prediger, und ist Russisch
beziehungsweise Persisch darueber hinaus laenger.

Ablauf:
    python laengenfaktor.py --pruefen         # was fehlt?
    python laengenfaktor.py --stimmen-laden   # Stimmen holen
    python laengenfaktor.py                   # messen
    python laengenfaktor.py --je-stimme       # je Stimme statt je Sprache

JE STIMME, NICHT JE SPRACHE
---------------------------
Der obere Weg misst eine Sprache mit genau EINER Stimme -- der aus
config.STIMMEN. Der Sprachwert ist damit in Wahrheit der Wert dieser
einen Stimme, und das faellt erst auf, wenn man mehrere vergleicht:

    es   1.18 / 1.19 / 1.00      Spannweite 0.19
    pt   1.19 / 0.92 / 1.22      Spannweite 0.30
    zwischen den Sprachmitteln   Spannweite 0.01

Gemessen in ergebnisse/stimmprobe/laengen.txt. Die Streuung zwischen
den Stimmen EINER Sprache ist groesser als die zwischen den Sprachen.
Der Faktor gehoert also an die Stimme; die Sprache ist nur der
Rueckfall fuer Stimmen, die niemand gemessen hat.

--je-stimme misst jede Stimme, die auf der Platte liegt, und schreibt
das Ergebnis nach messungen/laengenfaktor_stimmen.json -- verfolgt,
weil es der Beleg fuer die Tempotabelle in config.py ist. Die
Uebersetzungen selbst bleiben unter ergebnisse/: sie enthalten
Predigttext, und das Repo ist oeffentlich.

ZWEI BEZUGSGROESSEN, DIE MAN NICHT MISCHEN DARF
-----------------------------------------------
    gegen_deutsch    Zieldauer geteilt durch die Dauer der DEUTSCHEN
                     PIPER-Ausgabe desselben Satzes. Misst allein den
                     Unterschied zwischen den Stimmen.
    gegen_original   Zieldauer geteilt durch die ECHTE Sprechdauer des
                     Predigers. Misst zusaetzlich, ob Piper generell
                     anders schnell spricht als ein Mensch.

Fuer die Tempotabelle gilt gegen_deutsch: gesucht ist, wie viel
laenger diese Stimme fuer denselben Inhalt braucht. Welche Groesse
gilt, steht in der JSON-Datei mit dabei -- sonst steht in einem halben
Jahr wieder jemand davor.
"""

import argparse
import json
import re
import statistics
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import config

STIMMEN_ORDNER = config.BASIS / "voices"

# Welche Stimme zu welcher Sprache gehoert, steht in config.py -- an
# einer Stelle, wie ueberall sonst im Projekt. Frueher stand hier eine
# eigene Liste mit vier Sprachen; sie wich von config.STIMMEN ab, ohne
# dass es auffiel, und --stimmen-laden konnte die uebrigen siebzehn
# Sprachen deshalb gar nicht holen.
#
# Ausweichpfade bleiben hier: nicht jede Stimme existiert in jeder
# Qualitaetsstufe, und was config.py nennt, ist die erste Wahl.
AUSWEICHE = {
    "de": ["de/de_DE/karlsson/low/de_DE-karlsson-low"],
    "en": ["en/en_US/ryan/medium/en_US-ryan-medium"],
    "ru": ["ru/ru_RU/dmitri/medium/ru_RU-dmitri-medium"],
    "fa": ["fa/fa_IR/gyro/medium/fa_IR-gyro-medium",
           "fa/fa_IR/ganji/medium/fa_IR-ganji-medium"],
    # Polnisch: vier Kandidaten fuer die Wahl durch den Pruefer.
    # mls_6892 faellt raus -- Qualitaetsstufe "low", und die anderen
    # Sprachen laufen alle auf medium oder besser.
    "pl": ["pl/pl_PL/gosia/medium/pl_PL-gosia-medium",
           "pl/pl_PL/mc_speech/medium/pl_PL-mc_speech-medium",
           "pl/pl_PL/bass/high/pl_PL-bass-high"],
}

STIMMEN = {sp: [pfad] + AUSWEICHE.get(sp, [])
           for sp, pfad in config.STIMMEN.items() if pfad}

BASIS_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/"


# ---------------------------------------------------------------- Piper

def piper_pfad():
    """Sucht ein lauffaehiges Piper. Erst das Python-Modul, dann ein
    Binary im PATH, dann die uebliche venv-Ablage unter Windows."""
    kandidaten = [
        [sys.executable, "-m", "piper"],
        ["piper"],
        [str(Path(sys.executable).parent / "piper.exe")],
    ]
    for k in kandidaten:
        try:
            r = subprocess.run(k + ["--help"], capture_output=True,
                               timeout=30, text=True)
            if r.returncode == 0 or "usage" in (r.stdout + r.stderr).lower():
                return k
        except Exception:
            continue
    return None


def sprich(befehl, modell, text, ziel, tempo=1.0, fest=False):
    """Synthetisiert und gibt die Audiodauer in Sekunden zurueck.

    Der Text geht ueber eine UTF-8-Datei und den Schalter -i, NICHT ueber
    stdin. Das ist der entscheidende Punkt: bei stdin interpretiert Piper
    unter Windows die Bytes in der Konsolen-Codepage. Aus einem "ä" werden
    dann zwei Zeichen, die einzeln vorgelesen werden, und aus "ã" wird der
    Unicode-Name "atilde". Genau das ist im ersten Anlauf passiert und hat
    saemtliche Messwerte unbrauchbar gemacht, bei Farsi bis Faktor 5,5.

    tempo steuert --length-scale. Piper rechnet dabei umgekehrt: kleinere
    Werte bedeuten kuerzere Phoneme, also schnelleres Sprechen. Ein
    gewuenschtes Tempo von 1,2 entspricht length-scale 1/1,2.

    fest=True schaltet den Zufall in der Dauervorhersage ab. Piper baut
    auf VITS, und dessen Dauervorhersager ist stochastisch: derselbe
    Satz, dieselbe Stimme, zweimal gesprochen, ergibt verschiedene
    Laengen. Gemessen an einem deutschen Satz, sechs Durchgaenge:

        Vorgabe             4.49  4.68  4.64  4.97  4.67  4.71
                            Spanne 10,1 %, Streuung 3,0 %
        --noise-w-scale 0   4.377 sechsmal, Spanne 0,0 %

    Fuer eine Messung ist das entscheidend. Ohne den Schalter kam die
    deutsche Stimme gegen sich selbst auf 1,017 statt 1,000 -- ein
    Versatz, der sonst in jedem abgeleiteten Wert gesteckt haette.

    Im Betrieb bleibt der Zufall an: er macht die Stimme lebendiger,
    und die Schwankung ist zufaellig, nicht systematisch. Sie ist einer
    der Gruende, warum auf den gemessenen Wert ein Aufschlag kommt."""
    ziel = Path(ziel)
    ziel.unlink(missing_ok=True)
    eingabe = ziel.with_suffix(".txt")
    eingabe.write_text(text.strip() + "\n", encoding="utf-8")

    argumente = befehl + ["-m", str(modell), "-i", str(eingabe), "-f", str(ziel)]
    if abs(tempo - 1.0) > 1e-6:
        argumente += ["--length-scale", f"{1.0/tempo:.4f}"]
    if fest:
        argumente += ["--noise-w-scale", "0"]

    try:
        r = subprocess.run(argumente, capture_output=True, timeout=180)
        fehlertext = (r.stderr or b"").decode("utf-8", "replace").strip()

        if not ziel.exists():
            raise RuntimeError(f"keine Datei erzeugt. {letzte_zeile(fehlertext)}")
        if ziel.stat().st_size < 100:
            raise RuntimeError(f"Datei ist leer ({ziel.stat().st_size} Byte). "
                               f"{letzte_zeile(fehlertext)}")
        try:
            with wave.open(str(ziel)) as w:
                rahmen, rate = w.getnframes(), w.getframerate()
        except Exception as e:
            raise RuntimeError(f"WAV unlesbar: {e}. {letzte_zeile(fehlertext)}")
        if rahmen == 0:
            raise RuntimeError(f"WAV ohne Audiodaten. {letzte_zeile(fehlertext)}")
        return rahmen / rate
    finally:
        eingabe.unlink(missing_ok=True)


def letzte_zeile(text, n=200):
    """Aus einem Traceback die eigentliche Fehlermeldung ziehen. Ein auf
    70 Zeichen gekuerzter Traceback zeigt nur Pfeile und Zeilennummern und
    ist damit wertlos, genau das war der Fehler im ersten Anlauf."""
    if not text:
        return "(keine Fehlerausgabe)"
    zeilen = [z.strip() for z in text.splitlines() if z.strip()]
    inhalt = [z for z in zeilen
              if not z.startswith(("File ", "^", "~", "|"))
              and not z.lstrip().startswith(("File ", "^", "~"))]
    return (inhalt[-1] if inhalt else zeilen[-1])[:n]


def stimmen_testen(befehl, stimmen):
    """Faehrt jede Stimme einmal mit einem kurzen Satz an, bevor die
    eigentliche Messung startet. Zwanzig Saetze durchzurechnen und dann
    festzustellen, dass eine Sprache gar nicht funktioniert, ist
    verschwendete Zeit."""
    proben = {
        "de": "Der Sabbat ist ein Geschenk und keine Last.",
        "en": "The Sabbath is a gift and not a burden.",
        "ru": "Суббота это дар, а не бремя.",
        "fa": "سبت یک هدیه است، نه یک بار.",
    }
    tmp = Path(tempfile.mkdtemp())
    brauchbar = {}
    print("Stimmentest:")
    for sp, modell in stimmen.items():
        try:
            d = sprich(befehl, modell, proben[sp], tmp / f"test_{sp}.wav")
            woerter = len(proben[sp].split())
            # Normales Lesetempo liegt bei 0,3 bis 0,6 s je Wort. Alles ueber
            # 1,2 s bedeutet, dass Piper nicht Woerter liest, sondern Zeichen
            # oder Zeichennamen buchstabiert.
            je_wort = d / woerter
            if je_wort < 0.15 or je_wort > 1.2:
                print(f"  {sp}: {d:.1f}s fuer {woerter} Woerter "
                      f"= {je_wort:.2f}s je Wort -> unplausibel. "
                      f"Piper buchstabiert vermutlich statt zu lesen.")
            else:
                print(f"  {sp}: {d:.1f}s  ok")
                brauchbar[sp] = modell
        except Exception as e:
            print(f"  {sp}: {e}")
    print()
    return brauchbar


# ---------------------------------------------------------------- Setup

def gefundene_stimmen():
    treffer = {}
    for sp, liste in STIMMEN.items():
        for pfad in liste:
            name = pfad.split("/")[-1]
            datei = STIMMEN_ORDNER / f"{name}.onnx"
            if datei.exists() and (STIMMEN_ORDNER / f"{name}.onnx.json").exists():
                treffer[sp] = datei
                break
    return treffer


def pruefen():
    print("Piper:", end=" ")
    b = piper_pfad()
    print(" ".join(b) if b else "NICHT GEFUNDEN  ->  pip install piper-tts")

    print(f"\nStimmenordner: {STIMMEN_ORDNER}")
    da = gefundene_stimmen()
    for sp in sorted(STIMMEN):
        z = da.get(sp)
        print(f"  {sp}: {z.name if z else 'fehlt'}")

    fehlend = [s for s in STIMMEN if s not in da]
    if fehlend:
        print(f"\nFehlen ({len(fehlend)} von {len(STIMMEN)}): "
              f"{', '.join(sorted(fehlend))}")
        print("Diese Sprachen sind am Pult waehlbar und liefern dort nur")
        print("Text. Das Pult sagt es dazu, aber Ton gibt es keinen.")
        print("Holen mit: python laengenfaktor.py --stimmen-laden")
    else:
        print("\nAlles da. Messen mit: python laengenfaktor.py")

    quelle = config.ERGEBNIS_ORDNER / "woerter.json"
    print(f"\nwoerter.json: {'vorhanden' if quelle.exists() else 'FEHLT'}")


def stimmen_laden(ordner=None):
    """Holt die Stimmen aus config.STIMMEN.

    Der Zielordner ist wichtig und nicht bloss Geschmack: in voices/
    steht, was ausgeliefert wird -- was dort liegt, bietet das Pult an.
    Stimmen, die nur gemessen werden sollen, gehoeren deshalb nach
    ergebnisse/stimmprobe/voices/. Sonst waechst die Auswahl im
    Gottesdienst um Stimmen, die niemand gehoert hat."""
    import urllib.request
    global STIMMEN_ORDNER
    if ordner is not None:
        STIMMEN_ORDNER = Path(ordner)
    STIMMEN_ORDNER.mkdir(parents=True, exist_ok=True)
    da = gefundene_stimmen()

    for sp, liste in STIMMEN.items():
        if sp in da:
            print(f"{sp}: schon da ({da[sp].name})")
            continue
        geschafft = False
        for pfad in liste:
            name = pfad.split("/")[-1]
            print(f"{sp}: versuche {name} ...", end=" ", flush=True)
            try:
                for endung in (".onnx", ".onnx.json"):
                    urllib.request.urlretrieve(BASIS_URL + pfad + endung,
                                               STIMMEN_ORDNER / (name + endung))
                mb = (STIMMEN_ORDNER / (name + ".onnx")).stat().st_size / 1e6
                print(f"ok ({mb:.0f} MB)")
                geschafft = True
                break
            except Exception as e:
                print(f"nein ({type(e).__name__})")
                for endung in (".onnx", ".onnx.json"):
                    (STIMMEN_ORDNER / (name + endung)).unlink(missing_ok=True)
        if not geschafft:
            print(f"  {sp}: keine der hinterlegten Stimmen verfuegbar.")
            print(f"  Manuell suchen unter "
                  f"https://huggingface.co/rhasspy/piper-voices/tree/main/{sp}")
            print(f"  und beide Dateien (.onnx und .onnx.json) nach "
                  f"{STIMMEN_ORDNER} legen.")


# ---------------------------------------------------------------- Messung

def saetze_holen(anzahl):
    """Zieht Saetze mit ihrer echten Sprechdauer aus woerter.json.
    Nur mittellange Saetze, weil sehr kurze durch den Ein- und Ausklang
    von Piper verzerrt werden."""
    quelle = config.ERGEBNIS_ORDNER / "woerter.json"
    if not quelle.exists():
        sys.exit(f"Nicht gefunden: {quelle}\n"
                 f"Erst: python latenz_simulation.py --transkribieren")
    woerter = json.loads(quelle.read_text(encoding="utf-8"))["woerter"]

    saetze, puffer = [], []
    for w in woerter:
        puffer.append(w)
        if re.search(r"[.!?]$", w["wort"]):
            if 8 <= len(puffer) <= 30:
                saetze.append({
                    "text": " ".join(x["wort"] for x in puffer),
                    "dauer": puffer[-1]["ende"] - puffer[0]["start"],
                    "woerter": len(puffer)})
            puffer = []
    if not saetze:
        sys.exit("Keine geeigneten Saetze gefunden.")

    schritt = max(1, len(saetze) // anzahl)
    return saetze[::schritt][:anzahl]


def uebersetzen(text, sprache, modell):
    import requests
    from glossar import Glossar, glossarzeilen
    if not hasattr(uebersetzen, "g"):
        uebersetzen.g = Glossar.laden(config.GLOSSAR_CSV)
    gtext = glossarzeilen(uebersetzen.g.finde(text), sprache)
    system = (f"Du bist Fachuebersetzer fuer christliche Predigttexte. "
              f"Uebersetze den deutschen Satz nach {config.SPRACHNAMEN[sprache]}. "
              f"Gib ausschliesslich die Uebersetzung aus, ohne Erklaerung, "
              f"ohne Anfuehrungszeichen, ohne Formatierung.")
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


def messen(anzahl, modell, behalten=False):
    befehl = piper_pfad()
    if not befehl:
        sys.exit("Piper nicht gefunden. pip install piper-tts")

    stimmen = stimmen_testen(befehl, gefundene_stimmen())
    if "de" not in stimmen:
        sys.exit("Ohne funktionierende deutsche Stimme gibt es keine "
                 "Vergleichsbasis. Abbruch.")
    # Bewusst nur die geprueften Sprachen: die Messung vergleicht gegen
    # eine deutsche Referenz, und fuer ungepruefte Sprachen gibt es
    # keine Uebersetzung, der man die Laenge glauben koennte.
    ziele = [sp for sp in sorted(config.GEPRUEFT)
             if sp != "de" and sp in stimmen]
    if not ziele:
        sys.exit("Keine Zielsprache lauffaehig. Abbruch.")

    saetze = saetze_holen(anzahl)
    print(f"{len(saetze)} Saetze aus der Predigt, "
          f"{sum(s['dauer'] for s in saetze):.0f}s Original\n")

    ordner = (config.ERGEBNIS_ORDNER / "tts") if behalten else Path(tempfile.mkdtemp())
    ordner.mkdir(parents=True, exist_ok=True)

    gegen_original = {sp: [] for sp in stimmen}   # Piper gegen echte Sprechdauer
    gegen_deutsch = {sp: [] for sp in ziele}      # Piper gegen Piper-Deutsch
    zeilen = []
    ollama_tot = 0

    for i, s in enumerate(saetze, 1):
        print(f"[{i}/{len(saetze)}] {s['woerter']} Wörter, "
              f"{s['dauer']:.1f}s: {s['text'][:56]}")
        zeile = {"text": s["text"], "original": round(s["dauer"], 2)}
        deutsch_dauer = None

        for sp in ["de"] + ziele:
            try:
                if sp == "de":
                    text = s["text"]
                else:
                    text = uebersetzen(s["text"], sp, modell)
                dauer = sprich(befehl, stimmen[sp], text, ordner / f"{i:02d}_{sp}.wav")
                if sp == "de":
                    deutsch_dauer = dauer

                f_orig = dauer / s["dauer"]
                gegen_original[sp].append(f_orig)
                zeile[sp] = {"text": text, "dauer": round(dauer, 2),
                             "gegen_original": round(f_orig, 3)}
                anzeige = f"      {sp}: {dauer:5.1f}s  vs Original {f_orig:.2f}"
                if sp != "de" and deutsch_dauer:
                    f_de = dauer / deutsch_dauer
                    gegen_deutsch[sp].append(f_de)
                    zeile[sp]["gegen_deutsch"] = round(f_de, 3)
                    anzeige += f"  vs Piper-DE {f_de:.2f}"
                print(anzeige)

            except Exception as e:
                meldung = str(e)[:110]
                print(f"      {sp}: FEHLER {meldung}")
                if "HTTPConnectionPool" in meldung or "Max retries" in meldung:
                    ollama_tot += 1
                    if ollama_tot >= 3:
                        print("\nOllama antwortet dreimal nicht mehr. Abbruch, "
                              "statt weitere Saetze ins Leere zu rechnen.")
                        print("Pruefen mit: ollama ps    "
                              "Danach Ollama neu starten und erneut messen.")
                        return
                    break
        zeilen.append(zeile)

    # ------------------------------------------------------------ Auswertung
    print("\n" + "=" * 66)
    print("SPRACHVERGLEICH  (Piper gegen Piper-Deutsch)")
    print("Das ist die saubere Zahl: beide Seiten lesen gleichmaessig ab.")
    print("-" * 66)
    print(f"{'Sprache':18} {'Median':>8} {'Mittel':>8} {'Streuung':>10} {'n':>4}")
    for sp in ziele:
        w = gegen_deutsch.get(sp)
        if not w:
            continue
        streu = statistics.pstdev(w) if len(w) > 1 else 0
        print(f"{config.SPRACHNAMEN[sp]:18} {statistics.median(w):7.2f}x "
              f"{statistics.mean(w):7.2f}x {streu:9.2f} {len(w):4}")

    print("\n" + "=" * 66)
    print("SIMULATIONSWERT  (Piper gegen die echte Sprechdauer des Predigers)")
    print("Streut stark, weil Denkpausen des Predigers mitzaehlen. Der Median")
    print("ueber viele Saetze ist trotzdem der Wert, mit dem die Simulation")
    print("rechnet, denn genau dieses Verhaeltnis muss die Pipeline schaffen.")
    print("-" * 66)
    print(f"{'Sprache':18} {'Median':>8} {'Mittel':>8} {'Streuung':>10} {'n':>4}")
    for sp in ["de"] + ziele:
        w = gegen_original.get(sp)
        if not w:
            continue
        streu = statistics.pstdev(w) if len(w) > 1 else 0
        name = "Deutsch (Sockel)" if sp == "de" else config.SPRACHNAMEN[sp]
        print(f"{name:18} {statistics.median(w):7.2f}x "
              f"{statistics.mean(w):7.2f}x {streu:9.2f} {len(w):4}")

    # Plausibilitaetsgrenze. Kein Sprachenpaar der Welt ist doppelt so lang.
    # Wird sie gerissen, ist die Stimme oder die Textuebergabe defekt, und ein
    # daraus abgeleiteter Simulationswert waere Unsinn. Im ersten Anlauf kam
    # so ein Vorschlag von 6,57 heraus, den ich haette abfangen muessen.
    GRENZE = 2.0
    massgeblich, defekt = [], []
    for sp in ziele:
        w = gegen_original.get(sp)
        if not w:
            continue
        m = statistics.median(w)
        (defekt if m > GRENZE else massgeblich).append((sp, m))

    if defekt:
        print("\nUNPLAUSIBEL, nicht fuer die Simulation verwenden:")
        for sp, m in defekt:
            print(f"  {config.SPRACHNAMEN[sp]}: {m:.2f}x. Keine Sprache ist "
                  f"doppelt so lang wie Deutsch. Stimme oder Textuebergabe "
                  f"pruefen, Datei in {ordner} anhoeren.")

    if massgeblich:
        sp, hoch = max(massgeblich, key=lambda x: x[1])
        print(f"\nLangsamste brauchbare Sprache: {config.SPRACHNAMEN[sp]} "
              f"mit {hoch:.2f}x")
        print(f"  latenz_simulation.py --laengenfaktor {hoch:.2f}"
              + (f" --speedup {hoch:.2f}" if hoch > 1.0 else ""))
        if hoch <= 1.0:
            print("  Unter 1.0: die Ausgabe ist kuerzer als das Original, "
                  "ein Speedup ist nicht noetig.")
    else:
        print("\nKeine brauchbare Zielsprache. Kein Simulationswert ableitbar.")

    if behalten:
        print(f"\nAudiodateien zum Anhoeren in {ordner}")

    ziel = config.ERGEBNIS_ORDNER / "laengenfaktor.json"
    ziel.write_text(json.dumps(
        {"modell": modell, "saetze": len(zeilen),
         "gegen_deutsch": {sp: round(statistics.median(w), 3)
                           for sp, w in gegen_deutsch.items() if w},
         "gegen_original": {sp: round(statistics.median(w), 3)
                            for sp, w in gegen_original.items() if w},
         "einzeln": zeilen}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Einzelheiten in {ziel.name}")


# ------------------------------------------------------- Je Stimme

def saetze_aus_ton(datei, anzahl):
    """Deutsche Saetze samt ECHTER Sprechdauer, aus einer Tonaufnahme.

    Frueher kam das aus ergebnisse/woerter.json, geschrieben von
    latenz_simulation.py. Beides gibt es nicht mehr; der Aufruf lief
    deshalb sofort in einen Abbruch. Hier wird stattdessen direkt
    transkribiert -- dieselbe Quelle, ein Schritt weniger, und die
    Wortzeiten kommen aus derselben Erkennung wie im Betrieb.
    """
    # Vor faster_whisper: ctranslate2 darunter oeffnet libcublas erst
    # beim ersten transcribe. Liegt sie nur in der venv, findet der
    # Lader sie nicht, und es scheitert mit
    # "Library libcublas.so.12 is not found". grafikkarte.vorladen()
    # haengt sie vorher ein -- genau wie server.py es tut.
    import grafikkarte
    geladen = grafikkarte.vorladen()
    if geladen:
        print(f"CUDA-Bibliotheken vorgeladen: {', '.join(geladen)}")
    from faster_whisper import WhisperModel
    print(f"Transkribiere {Path(datei).name} ...", flush=True)
    modell = WhisperModel(config.WHISPER_MODELL,
                          device=config.WHISPER_DEVICE,
                          compute_type=config.WHISPER_COMPUTE)
    segmente, _ = modell.transcribe(str(datei),
                                    language=config.WHISPER_SPRACHE,
                                    beam_size=config.WHISPER_BEAM,
                                    vad_filter=config.WHISPER_VAD,
                                    word_timestamps=True)
    saetze = []
    for seg in segmente:
        text = seg.text.strip()
        # Sehr kurze Segmente verzerren: Piper haengt an jede Ausgabe
        # Ein- und Ausklang an, und bei zwei Woertern faellt das ins
        # Gewicht. Sehr lange sind meist zwei Saetze ohne Punkt.
        if not (8 <= len(text.split()) <= 30):
            continue
        dauer = seg.end - seg.start
        if dauer < 1.5:
            continue
        saetze.append({"text": text, "dauer": dauer,
                       "woerter": len(text.split())})
    if not saetze:
        sys.exit(f"Aus {datei} liessen sich keine brauchbaren Saetze "
                 f"gewinnen.")
    schritt = max(1, len(saetze) // anzahl)
    return saetze[::schritt][:anzahl]


def stimmen_auf_platte():
    """Alle Stimmen, die hier liegen, nach Sprache sortiert.

    Zwei Orte, und der Unterschied ist Absicht: in voices/ steht, was
    ausgeliefert wird; in ergebnisse/stimmprobe/voices/ liegen die
    Kandidaten, die nur zum Vergleich geholt wurden. Gemessen werden
    beide, aber welche ausgeliefert wird, steht mit im Ergebnis --
    denn nur deren Wert kommt spaeter in config.py.
    """
    orte = [(STIMMEN_ORDNER, True),
            (config.ERGEBNIS_ORDNER / "stimmprobe" / "voices", False)]
    ausgeliefert = {pfad.split("/")[-1] for pfad in config.STIMMEN.values()}
    gefunden = {}
    for ordner, _ in orte:
        if not ordner.exists():
            continue
        for onnx in sorted(ordner.glob("*.onnx")):
            name = onnx.stem
            # Der Sprachcode steckt vorn im Dateinamen: es_ES-davefx-medium
            sp = name.split("_")[0].lower()
            if sp not in config.SPRACHNAMEN:
                continue
            # Derselbe Name an zwei Orten: der erste gewinnt, und das ist
            # voices/ -- also die ausgelieferte Datei.
            if any(st["name"] == name for st in gefunden.get(sp, [])):
                continue
            gefunden.setdefault(sp, []).append(
                {"name": name, "pfad": str(onnx)[:-5],
                 "ausgeliefert": name in ausgeliefert})
    return gefunden


def je_stimme(anzahl, modell, tondatei, nur=None):
    """Misst jede Stimme einzeln gegen dieselbe deutsche Referenz."""
    befehl = piper_pfad()
    if not befehl:
        sys.exit("Piper nicht gefunden. pip install piper-tts")

    alle = stimmen_auf_platte()
    if "de" not in alle:
        sys.exit("Ohne deutsche Stimme gibt es keine Vergleichsbasis. "
                 "Abbruch.")
    if nur:
        alle = {sp: st for sp, st in alle.items() if sp in nur or sp == "de"}

    # Die deutsche Referenz ist die ausgelieferte Stimme, nicht
    # irgendeine: alle Zielwerte haengen daran, und sie muss dieselbe
    # sein wie im Betrieb.
    deutsch = next((st for st in alle["de"] if st["ausgeliefert"]),
                   alle["de"][0])
    print(f"Deutsche Referenz: {deutsch['name']}")

    saetze = saetze_aus_ton(tondatei, anzahl)
    print(f"{len(saetze)} Saetze, "
          f"{sum(s['dauer'] for s in saetze):.0f}s Original\n")

    ordner = Path(tempfile.mkdtemp())
    # Je Sprache einmal uebersetzen, dann mit jeder Stimme dieser
    # Sprache sprechen. Die Uebersetzung ist der teure Teil und haengt
    # nicht an der Stimme.
    #
    # Aufgehoben wird sie auch: eine zweite Messreihe mit anderen
    # Piper-Schaltern soll nicht noch einmal das Sprachmodell bemuehen,
    # und sie soll auf DENSELBEN Texten laufen -- sonst vergliche man
    # zwei Dinge auf einmal.
    puffer_datei = config.ERGEBNIS_ORDNER / "laengenfaktor_texte.json"
    kennung = f"{Path(tondatei).name}|{anzahl}|{modell}"
    puffer = {}
    if puffer_datei.exists():
        try:
            gespeichert = json.loads(puffer_datei.read_text(encoding="utf-8"))
            if gespeichert.get("kennung") == kennung:
                puffer = gespeichert.get("texte", {})
                print(f"Uebersetzungen aus {puffer_datei.name} uebernommen.")
        except Exception:
            puffer = {}

    texte = {"de": [s["text"] for s in saetze]}
    ziele = [sp for sp in sorted(alle) if sp != "de"]
    for sp in ziele:
        if len(puffer.get(sp, [])) == len(saetze):
            texte[sp] = puffer[sp]
            continue
        print(f"  uebersetze nach {config.SPRACHNAMEN.get(sp, sp)} ...",
              flush=True)
        texte[sp] = [uebersetzen(s["text"], sp, modell) for s in saetze]
    puffer_datei.write_text(json.dumps(
        {"kennung": kennung, "texte": texte}, ensure_ascii=False, indent=2),
        encoding="utf-8")

    # Zuerst Deutsch: ohne diese Dauern gibt es keinen Bezug.
    deutsch_dauer = []
    for i, text in enumerate(texte["de"]):
        deutsch_dauer.append(
            sprich(befehl, deutsch["pfad"], text, ordner / f"de_{i}.wav",
                   fest=True))

    ergebnis = {}
    for sp in [s for s in sorted(alle)]:
        for st in alle[sp]:
            gd, go = [], []
            for i, text in enumerate(texte[sp]):
                try:
                    dauer = sprich(befehl, st["pfad"], text,
                                   ordner / f"{st['name']}_{i}.wav",
                                   fest=True)
                except Exception as e:
                    print(f"    {st['name']}: {type(e).__name__}")
                    break
                if deutsch_dauer[i] > 0:
                    gd.append(dauer / deutsch_dauer[i])
                if saetze[i]["dauer"] > 0:
                    go.append(dauer / saetze[i]["dauer"])
            if not gd:
                continue
            ergebnis[st["name"]] = {
                "sprache": sp,
                "ausgeliefert": st["ausgeliefert"],
                "gegen_deutsch": round(statistics.median(gd), 3),
                "gegen_original": round(statistics.median(go), 3) if go else None,
                "streuung": round(statistics.pstdev(gd), 3) if len(gd) > 1 else 0.0,
                "saetze": len(gd),
            }
            marke = " <- ausgeliefert" if st["ausgeliefert"] else ""
            print(f"  {st['name']:34} {ergebnis[st['name']]['gegen_deutsch']:5.2f}x"
                  f"  (Streuung {ergebnis[st['name']]['streuung']:.2f}){marke}")

    print("\nJe Sprache, nur die ausgelieferte Stimme:")
    for sp in sorted(alle):
        aus = [(n, w) for n, w in ergebnis.items()
               if w["sprache"] == sp and w["ausgeliefert"]]
        for n, w in aus:
            print(f"  {config.SPRACHNAMEN.get(sp, sp):22} "
                  f"{w['gegen_deutsch']:5.2f}x   {n}")

    # Verfolgt und nicht unter ergebnisse/: diese Datei ist der Beleg
    # fuer die Tempotabelle in config.py. Der Textpuffer daneben bleibt
    # draussen -- er enthaelt Predigtsaetze, und das Repo ist oeffentlich.
    ziel = config.BASIS / "messungen" / "laengenfaktor_stimmen.json"
    ziel.parent.mkdir(exist_ok=True)
    ziel.write_text(json.dumps({
        "bezugsgroesse": "gegen_deutsch",
        # Ohne diesen Schalter waere jede Zahl hier um wenige Prozent
        # verwuerfelt: Piper sagt die Dauer stochastisch voraus.
        "noise_w_scale": 0,
        "bezugsgroesse_erklaerung":
            "Zieldauer geteilt durch die Dauer der deutschen "
            "Piper-Ausgabe desselben Satzes. Fuer die Tempotabelle in "
            "config.py gilt genau diese Groesse. gegen_original steht "
            "daneben und bezieht sich auf die echte Sprechdauer des "
            "Predigers -- die beiden Reihen duerfen NICHT gemischt "
            "werden.",
        "deutsche_referenz": deutsch["name"],
        "tondatei": Path(tondatei).name,
        "modell": modell,
        "saetze": len(saetze),
        "stimmen": ergebnis,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nGeschrieben: {ziel}")
    return ergebnis


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--pruefen", action="store_true")
    p.add_argument("--stimmen-laden", action="store_true")
    p.add_argument("--anzahl", type=int, default=20)
    p.add_argument("--modell", default="gemma4:12b")
    p.add_argument("--behalten", action="store_true",
                   help="WAV-Dateien in ergebnisse/tts ablegen statt ins "
                        "Temp-Verzeichnis. Zum Anhoeren, besonders Farsi.")
    p.add_argument("--je-stimme", action="store_true",
                   help="Jede Stimme einzeln messen statt eine je Sprache.")
    p.add_argument("--ton", default="ausschnitt.mp3",
                   help="Aufnahme, aus der die deutschen Saetze kommen.")
    p.add_argument("--nur", default="",
                   help="Nur diese Sprachen, mit Komma getrennt.")
    p.add_argument("--ziel-ordner", default="",
                   help="Wohin --stimmen-laden legt. Vorgabe voices/. "
                        "Zum Messen: ergebnisse/stimmprobe/voices")
    a = p.parse_args()

    config.ERGEBNIS_ORDNER.mkdir(exist_ok=True)
    if a.pruefen:
        pruefen()
    elif getattr(a, "stimmen_laden", False):
        stimmen_laden(getattr(a, "ziel_ordner", "") or None)
    elif getattr(a, "je_stimme", False):
        nur = [x.strip() for x in a.nur.split(",") if x.strip()]
        je_stimme(a.anzahl, a.modell, config.BASIS / a.ton, nur or None)
    else:
        messen(a.anzahl, a.modell, a.behalten)


if __name__ == "__main__":
    main()
