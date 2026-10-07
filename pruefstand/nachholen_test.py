#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verpasster Text nach einem Verbindungsabbruch -- die Serverseite (G2).

    .venv/bin/python pruefstand/nachholen_test.py

Beim Wiederverbinden nennt das Handy, was es zuletzt hatte (seit,
lauf). Der Server schickt den Zustand -- mit Fassung und Laufkennung --
und danach die Abschnitte, die seitdem gesendet wurden: als Text, OHNE
Ton, ohne Doppel, nur fuer die eigene Sprache. Passt der Lauf nicht
(Serverneustart, Zuruecksetzen), wird nichts nachgereicht: die Nummern
meinten dann andere Abschnitte.

Geprueft an server.Lauf selbst, mit einem nachgebauten WebSocket --
ohne Whisper, ohne Stimmen, ohne Netz. Die Seite des Handys steht in
pruefstand/fassung_test.mjs.
"""
import asyncio
import json
import sys
from collections import defaultdict, deque
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))
import config  # noqa: E402
import server  # noqa: E402

ROT, GRUEN, AUS = "\033[31m", "\033[32m", "\033[0m"
FEHLER = 0


def pruefe(was, erwartet, ist):
    global FEHLER
    if erwartet == ist:
        print(f"   ok    {was}")
    else:
        print(f"   {ROT}FEHL{AUS}  {was}: erwartet {erwartet!r}, ist {ist!r}")
        FEHLER += 1


class Draht:
    def __init__(self):
        self.bekommen = []

    async def send_text(self, t):
        self.bekommen.append(json.loads(t))


class Mitschnitt:
    laeuft = False


def lauf_bauen():
    """Ein Lauf nur mit dem, was anmelden() und nachholbar() brauchen."""
    L = server.Lauf.__new__(server.Lauf)
    L.hoerer = defaultdict(set)
    L.laeuft = True
    L.n = 0
    L.mitschnitt = Mitschnitt()
    # Seit dem Nachtrag zu 0.5.0 meldet anmelden() auch das
    # Testprotokoll (Feld "mitschrift").
    L.pruefprotokoll = Mitschnitt()
    L.verpasst = defaultdict(lambda: deque(maxlen=30))
    L.lauf_kennung = "L1"
    return L


def anmelden(L, sprache, seit=None, lauf=None):
    d = Draht()
    asyncio.run(L.anmelden(d, sprache, seit, lauf))
    return d.bekommen


L = lauf_bauen()
for n in range(1, 6):
    L.n = n
    L.nachholbar("ru", n, f"Абзац {n}.", 2.0)
    L.nachholbar("fa", n, f"بند {n}.", 2.0)

print("\n\033[1m== 1) Der Zustand traegt Fassung und Lauf\033[0m")
z = anmelden(L, "ru")[0]
pruefe("typ zustand", "zustand", z["typ"])
pruefe("mit der Fassung des Servers", config.VERSION, z["fassung"])
pruefe("mit der Laufkennung", "L1", z["lauf"])

print("\n\033[1m== 2) Ohne seit: nichts nachgereicht\033[0m")
pruefe("nur der Zustand", 1, len(anmelden(L, "ru")))

print("\n\033[1m== 3) Mit seit: genau das Verpasste, als Text\033[0m")
b = anmelden(L, "ru", 2, "L1")
segs = [x for x in b if x["typ"] == "segment"]
pruefe("der Zustand zuerst", "zustand", b[0]["typ"])
pruefe("die Abschnitte 3, 4, 5 -- nicht 1 und 2", [3, 4, 5],
       [x["id"] for x in segs])
pruefe("in der eigenen Sprache", ["Абзац 3.", "Абзац 4.", "Абзац 5."],
       [x["text"] for x in segs])
pruefe("als nachgereicht gekennzeichnet", [True] * 3,
       [x.get("nachgereicht") for x in segs])
pruefe("ohne Ton", [False] * 3, ["audio" in x for x in segs])
pruefe("keine Doppel", len(segs), len({x["id"] for x in segs}))

print("\n\033[1m== 4) Nichts zu holen, falscher Lauf\033[0m")
pruefe("seit 5: nichts dazu", 1, len(anmelden(L, "ru", 5, "L1")))
pruefe("anderer Lauf: nichts dazu", 1, len(anmelden(L, "ru", 2, "L0")))
pruefe("ohne Lauf: nichts dazu", 1, len(anmelden(L, "ru", 2, None)))

print("\n\033[1m== 5) Vorgehalten wird nur, was der Server ohnehin haelt\033[0m")
for n in range(6, 60):
    L.nachholbar("ru", n, f"Абзац {n}.", 2.0)
pruefe("hoechstens 30 Abschnitte je Sprache", 30, len(L.verpasst["ru"]))
segs = [x for x in anmelden(L, "ru", 0, "L1") if x["typ"] == "segment"]
pruefe("nach langem Abbruch: die letzten 30", (30, 59),
       (len(segs), segs[-1]["id"]))

print("\n\033[1m== 6) Zuruecksetzen ist ein neuer Lauf\033[0m")
quelle = (WURZEL / "server.py").read_text(encoding="utf-8")
block = quelle.split("async def zuruecksetzen")[1].split("# ---- Verarbeitung")[0]
pruefe("leert die Vorhaltung", True, "self.verpasst.clear()" in block)
pruefe("und vergibt eine neue Laufkennung", True, "self.lauf_kennung =" in block)
pruefe("jeder gesendete Abschnitt wird vorgemerkt", True,
       "self.nachholbar(e[\"sprache\"], nummer" in quelle)

print()
if FEHLER:
    print(f"{ROT}{FEHLER} Fehler.{AUS}")
    sys.exit(1)
print(f"{GRUEN}Alle Faelle wie erwartet.{AUS}")
