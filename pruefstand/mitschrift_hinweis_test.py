#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gespeicherter Predigttext wird angezeigt (Nachtrag zu 0.5.0).

    .venv/bin/python pruefstand/mitschrift_hinweis_test.py

Bis zum Nachtrag stand auf den Handys nur die Tonaufnahme. Aber auch
das Testprotokoll und die Mitschrift im Protokoll halten Predigttext
fest. Jetzt:

  * Der Zustand an die Handys traegt "mitschrift" -- wahr, solange
    Testprotokoll ODER Mitschrift laeuft --, und zwar sofort beim
    Umschalten, nicht erst beim naechsten Zustandswechsel.
  * /api/zustand traegt dasselbe, und das Pult zeigt es unter
    Gottesdienst an, neben "Aufnahme laeuft".
  * Der Kurzhinweis (Stufe 1) nennt Aufnahme, Protokoll und Mitschrift,
    in allen vier Sprachen.

Die Anzeige auf der Hoererseite selbst prueft hinweisbalken_test.mjs.
"""
import asyncio
import json
import sys
import threading
from collections import defaultdict, deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hilfe import (WURZEL, arbeitskopie, rufen, server_starten,  # noqa: E402
                   server_stoppen, wegwerfordner)

sys.path.insert(0, str(WURZEL))
import datenschutz  # noqa: E402
import server  # noqa: E402

ROT, GRUEN, AUS = "\033[31m", "\033[32m", "\033[0m"
FEHLER = 0
PORT = 8187


def pruefe(was, erwartet, ist):
    global FEHLER
    if erwartet == ist:
        print(f"   ok    {was}")
    else:
        print(f"   {ROT}FEHL{AUS}  {was}: erwartet {erwartet!r}, ist {ist!r}")
        FEHLER += 1


def titel(t):
    print(f"\n\033[1m== {t}\033[0m")


class Draht:
    def __init__(self):
        self.bekommen = []

    async def send_text(self, t):
        self.bekommen.append(json.loads(t))


class Schalter:
    def __init__(self, laeuft=False):
        self.laeuft = laeuft


def lauf_bauen(aufnahme=False, pruefprotokoll=False):
    L = server.Lauf.__new__(server.Lauf)
    L.hoerer = defaultdict(set)
    L.laeuft = True
    L.n = 0
    L.mitschnitt = Schalter(aufnahme)
    L.pruefprotokoll = Schalter(pruefprotokoll)
    L.verpasst = defaultdict(lambda: deque(maxlen=30))
    L.lauf_kennung = "L1"
    return L


def erste_meldung(L):
    d = Draht()
    asyncio.run(L.anmelden(d, "ru"))
    z = d.bekommen[0]
    return z.get("aufnahme"), z.get("mitschrift")


titel("1) Was ein Handy beim Anmelden erfaehrt")
server.PROTOKOLL_MITSCHRIFT = False
pruefe("nichts laeuft: nichts", (False, False), erste_meldung(lauf_bauen()))
pruefe("Aufnahme: nur die Aufnahme", (True, False),
       erste_meldung(lauf_bauen(aufnahme=True)))
pruefe("Testprotokoll: Mitschrift", (False, True),
       erste_meldung(lauf_bauen(pruefprotokoll=True)))
server.PROTOKOLL_MITSCHRIFT = True
pruefe("Mitschrift im Protokoll: Mitschrift", (False, True),
       erste_meldung(lauf_bauen()))
pruefe("alles zugleich: beides", (True, True),
       erste_meldung(lauf_bauen(aufnahme=True, pruefprotokoll=True)))
server.PROTOKOLL_MITSCHRIFT = False

titel("2) Der Kurzhinweis nennt alle drei")
for sp, worte in (("de", "eine Aufnahme, ein Protokoll oder eine Mitschrift "
                         "der Predigt"),
                  ("en", "a recording, a log or a transcript of the sermon"),
                  ("ru", "аудиозапись, протокол или стенограмму проповеди"),
                  ("fa", "ضبط صدا، گزارش یا رونوشت موعظه")):
    absaetze = " ".join(datenschutz.stufe1(sp)["absaetze"])
    pruefe(f"Stufe 1 {sp}", True, worte in absaetze)
for sp, wort in (("de", "Solange eines davon läuft, steht es auf jedem Handy"),
                 ("en", "While either runs, every phone shows it")):
    seite = datenschutz.stufe2_html(sp)
    pruefe(f"Stufe 2 {sp}: Testprotokoll und Mitschrift sind sichtbar",
           True, wort in seite)
    pruefe(f"Stufe 2 {sp}: der alte Satz ist weg", False,
           "nicht angezeigt" in seite or "do not show it" in seite)

titel("3) Das Pult")
quelle = (WURZEL / "server.py").read_text(encoding="utf-8")
gd = quelle.split("<section id=gottesdienst")[1].split("</section>")[0]
pruefe("die Zeile steht unter Gottesdienst", True,
       "id=mitschriftlaeuft hidden" in gd)
pruefe("gleich nach 'Aufnahme laeuft'", True,
       gd.index("id=aufnahmelaeuft") < gd.index("id=mitschriftlaeuft")
       < gd.index("<div class=kacheln>"))
for s in ("ms_laeuft:", "ms_pp:", "ms_journal:", "ms_handys:"):
    pruefe(f"{s} auf Deutsch und Englisch", 2, quelle.count(f"   {s}"))
pruefe("der Zustandstakt zeichnet sie", True,
       "mitschriftAnzeigen(d);" in quelle)

titel("4) Am laufenden Server: sofort auf dem Handy")
import websockets  # noqa: E402

ordner = arbeitskopie(wegwerfordner("devarenu-mitschrift-"))
p = server_starten(ordner, PORT)


def nebenher(weg, daten):
    """Ein Pult-Aufruf, waehrend der Strom offen ist."""
    t = threading.Thread(target=rufen, args=(PORT, weg, daten))
    t.start()
    return t


async def strom_probe():
    ergebnisse = []
    async with websockets.connect(
            f"ws://127.0.0.1:{PORT}/strom?sprache=de") as ws:

        async def naechster_zustand():
            while True:
                m = json.loads(await asyncio.wait_for(ws.recv(), 20))
                if m.get("typ") == "zustand":
                    return m

        z = await naechster_zustand()
        ergebnisse.append(("beim Anmelden", z.get("mitschrift")))
        for weg, daten, name in (
                ("/api/protokoll",
                 {"an": True, "einwilligung": {"person_gefragt": True}},
                 "Mitschrift an"),
                ("/api/protokoll", {"an": False}, "Mitschrift aus"),
                ("/api/pruefprotokoll",
                 {"an": True, "einwilligung": {"person_gefragt": True}},
                 "Testprotokoll an"),
                ("/api/pruefprotokoll", {"an": False}, "Testprotokoll aus")):
            t = nebenher(weg, daten)
            z = await naechster_zustand()
            await asyncio.to_thread(t.join)
            ergebnisse.append((name, z.get("mitschrift")))
            stand = json.loads(rufen(PORT, "/api/zustand")[1])
            ergebnisse.append((name + " (Pult)", stand.get("mitschrift")))
    return ergebnisse


try:
    erwartet = {"beim Anmelden": False,
                "Mitschrift an": True, "Mitschrift an (Pult)": True,
                "Mitschrift aus": False, "Mitschrift aus (Pult)": False,
                "Testprotokoll an": True, "Testprotokoll an (Pult)": True,
                "Testprotokoll aus": False, "Testprotokoll aus (Pult)": False}
    try:
        ist = dict(asyncio.run(strom_probe()))
    except Exception as e:
        ist = {"fehler": repr(e)}
    for name, wert in erwartet.items():
        pruefe(name, wert, ist.get(name, ist.get("fehler")))
finally:
    server_stoppen(p)

print()
if FEHLER:
    print(f"{ROT}{FEHLER} Fehler.{AUS}")
    sys.exit(1)
print(f"{GRUEN}Alle Faelle wie erwartet.{AUS}")
