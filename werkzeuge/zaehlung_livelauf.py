#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Live-Lauf: Bibelstellen in der Zaehlung der Zielsprache.

    python werkzeuge/zaehlung_livelauf.py

Braucht ein laufendes Ollama mit config.LIVE_MODELL. Der Pruefstand
(pruefstand/zaehlung_test.py) prueft die Umrechnung selbst; dieser Lauf
prueft, was das MODELL daraus macht -- ob es die vorgegebene Angabe
uebernimmt und wo die Nachpruefung eingreifen muss.

Nachgebaut ist dieselbe Prompt-Bildung wie in
server.Werk.uebersetzen(). Laeuft die auseinander, sagt dieser Lauf
nichts mehr ueber den Betrieb; darum stehen die Regeln hier Zeile fuer
Zeile so wie dort.

Ergebnis von 0.4.0, gemma4:12b: 12 von 12 Saetzen richtig. Einen Fall
hat erst der Lauf aufgedeckt -- das Modell schrieb "в Псалме 22"
statt "Псалом 22", also denselben Psalm im Praepositiv. Seitdem prueft
zaehlung.steht_drin() den Stamm des Buchnamens und nicht die Nennform.
"""
import sys, json, re, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config, zaehlung
import bibelstellen as b
from glossar import Glossar, glossarzeilen
import csv, io

G = Glossar.laden(config.GLOSSAR_CSV)
T = zaehlung.Tabelle.laden()
A = [z for z in csv.DictReader(io.open(config.GLOSSAR_CSV, encoding="utf-8-sig",
     newline=""), delimiter=";") if z["block"] == "A"]

SAETZE = [
    "Lesen wir Joel 3,1: Und danach will ich meinen Geist ausgiessen ueber alles Fleisch.",
    "In Maleachi 3,23 steht die Verheissung vom Propheten Elia.",
    "Psalm 51,12 bittet: Schaffe mir, Gott, ein reines Herz.",
    "Der gute Hirte in Psalm 23 ist das bekannteste Gebet der Bibel.",
    "Johannes 3,16 kennt fast jeder in der Gemeinde.",
    "Joel 4,5 spricht vom Tag des Herrn.",
]

def stellen_um(text, sprache):
    welche = zaehlung.ZAEHLUNG_JE_SPRACHE.get(sprache)
    if not welche:
        return []
    aus = []
    for nr, buch, kap, vers, quell, _ in b.stellen_mit_versen(text):
        neu = T.umrechnen(nr, kap, vers, welche)
        if not neu or neu == (kap, vers):
            continue
        name = zaehlung.ZITATNAME.get(nr, {}).get(sprache)
        if not name:
            tr = [z for z in A if z["de"] == buch]
            name = (tr[0][sprache].strip() if tr else "") or buch
        aus.append((quell, name, neu[0], neu[1]))
    return aus

def uebersetzen(text, sprache):
    treffer = G.finde_in(text, "de")
    gtext = glossarzeilen(treffer, sprache, quelle="de")
    von = config.SPRACHNAMEN["de"]
    system = (f"Du bist Fachuebersetzer fuer christliche Predigttexte. "
              f"Uebersetze den Abschnitt von {von} nach "
              f"{config.SPRACHNAMEN[sprache]}.\n"
              f"Regeln:\n"
              f"- Gib ausschliesslich die Uebersetzung aus. Keine "
              f"Erklaerung, keine Anfuehrungszeichen, kein Markdown.\n"
              f"- Der Abschnitt stammt aus fortlaufender Rede. "
              f"Uebersetze genau das Gegebene, ohne es zu "
              f"vervollstaendigen.\n"
              f"- Achte auf grammatisch korrekte Endungen und darauf, "
              f"dass Adjektive und Substantive zusammenpassen.\n"
              f"- Fuege nichts hinzu und lass nichts weg.")
    trenner = config.STELLEN_TRENNER.get(sprache)
    if trenner:
        system += (f"\n- Bibelstellen werden mit „{trenner}“ zwischen "
                   f"Kapitel und Vers geschrieben, zum Beispiel Juan 3{trenner}16.")
    anrede = getattr(config, "ANREDE", {}).get(sprache)
    if anrede:
        system += f"\n- {anrede}"
    um = stellen_um(text, sprache)
    if um:
        system += zaehlung.hinweis_bauen(um, sprache, trenner or ",")
    if gtext:
        system += ("\n\nWortwahlvorgaben fuer einzelne Fachbegriffe. Sie "
                   "sagen nichts ueber Satzbau oder Betonung.\n" + gtext)
    daten = json.dumps({"model": config.LIVE_MODELL, "stream": False,
        "think": False, "options": {"temperature": 0.1, "num_predict": 400},
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": text}]}).encode()
    r = urllib.request.Request(f"{config.OLLAMA_URL}/api/chat", data=daten,
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=120) as a:
        t = json.loads(a.read())["message"]["content"]
    if "</think>" in t:
        t = t.split("</think>", 1)[1]
    t = re.sub(r"[*`]+", "", t).strip().strip('"').strip()
    roh = t
    t, ersetzt = zaehlung.nachtragen(t, um, trenner or ",")
    return um, roh, t, ersetzt

print(f"Modell: {config.LIVE_MODELL}\n")
for sprache in ("en", "ru"):
    print(f"######## {sprache}")
    for satz in SAETZE:
        um, roh, fertig, ersetzt = uebersetzen(satz, sprache)
        soll = "; ".join(zaehlung.stelle_schreiben(n, k, v) for _, n, k, v in um) or "-"
        drin_roh = all(zaehlung.steht_drin(roh, n, k, v) for _, n, k, v in um) if um else True
        drin = all(zaehlung.steht_drin(fertig, n, k, v) for _, n, k, v in um) if um else True
        print(json.dumps({"satz": satz, "sprache": sprache, "soll": soll,
                          "modell_direkt": drin_roh, "nach_pruefung": drin,
                          "ersetzt": [e[1] for e in ersetzt],
                          "ausgabe": fertig}, ensure_ascii=False))
