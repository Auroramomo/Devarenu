#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stimmen ohne brauchbare Lizenz werden nicht ausgeliefert.

    .venv/bin/python pruefstand/stimmlizenz_test.py

Mit 0.4.5 sind zwei herausgenommen:

  * ka_GE-natia-medium -- ausdruecklich nur fuer Privatpersonen,
    Organisationen untersagt. Eine Gemeinde ist eine Organisation.
  * ar_JO-kareem-medium -- gar keine Lizenzangabe.

"Nicht eingeschaltet" genuegte nicht: beide lagen trotzdem auf jedem
Stick, und ein Stick wird von Gemeinde zu Gemeinde weitergereicht.
Dieser Lauf haelt fest, dass sie aus allen Auslieferungswegen heraus
sind -- und dass Rostock davon unberuehrt bleibt.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402

BASIS = Path(__file__).resolve().parent.parent
OHNE_LIZENZ = {
    "ka_GE-natia-medium": "nur Privatpersonen, Organisationen untersagt",
    "ar_JO-kareem-medium": "keine Lizenzangabe",
}
# Die Sprachen, die in Rostock laufen. Sie duerfen von alledem nichts
# merken.
ROSTOCK = ("en", "ru", "fa")

fehler = 0


def pruefe(was, erwartet, ist):
    global fehler
    if erwartet == ist:
        print(f"   ok    {was}")
    else:
        fehler += 1
        print(f"   FEHLER {was}: erwartet {erwartet!r}, ist {ist!r}")


def titel(t):
    print(f"\n\033[1m== {t}\033[0m")


titel("1) Nicht mehr in config.STIMMEN")
for sprache in ("ka", "ar"):
    pruefe(f"{sprache} hat keine Stimme", "", config.STIMMEN.get(sprache, ""))
# Aber die Sprache selbst bleibt waehlbar -- Untertitel ohne Ton.
for sprache in ("ka", "ar"):
    pruefe(f"{sprache} bleibt eine Sprache", True,
           sprache in config.SPRACHNAMEN)
# Und kein anderer Eintrag nennt die beiden Dateien.
genannt = [sp for sp, pfad in config.STIMMEN.items()
           if pfad and any(n in pfad for n in OHNE_LIZENZ)]
pruefe("keine andere Sprache greift darauf", [], genannt)

titel("2) Nicht mehr in teile.json")
teile = json.loads((BASIS / "teile.json").read_text(encoding="utf-8"))
drin = [e["pfad"] for e in teile["teile"]
        if any(n in e["pfad"] for n in OHNE_LIZENZ)]
pruefe("kein Teil nennt sie", [], drin)
for sprache in ("ka", "ar"):
    pruefe(f"{sprache} steht nicht in der Stimmenliste", False,
           sprache in teile["stimmen"])
# Die Summe muss zu den Teilen passen, sonst meldet der Stick spaeter
# eine Abweichung, die keine ist.
pruefe("die Byte-Summe stimmt", sum(e["bytes"] for e in teile["teile"]),
       teile["bytes"])
# Jede Datei in teile.json muss sich einer Stimme zuordnen lassen --
# teile.py --aus-dem-netz meldet sonst "steht nicht in config.STIMMEN".
stimmnamen = {Path(p).name for p in config.STIMMEN.values() if p}
verwaist = [e["pfad"] for e in teile["teile"] if e["art"] == "stimmen"
            and e["pfad"].removesuffix(".json").removesuffix(".onnx")
            not in stimmnamen]
pruefe("keine verwaiste Stimmdatei", [], verwaist)
# Und umgekehrt: jede eingestellte Stimme ist auch erfasst.
erfasst = {e["pfad"].removesuffix(".json").removesuffix(".onnx")
           for e in teile["teile"] if e["art"] == "stimmen"}
pruefe("jede eingestellte Stimme ist erfasst", set(), stimmnamen - erfasst)

titel("3) Der Grund steht aufgeschrieben")
lizenzen = (BASIS / "LIZENZEN.md").read_text(encoding="utf-8")
for name, grund in OHNE_LIZENZ.items():
    pruefe(f"{name} steht in LIZENZEN.md", True, name in lizenzen)
pruefe("mit Fassung und Datum", True,
       "0.4.5 herausgenommen" in lizenzen and "04.10.2026" in lizenzen)
pruefe("und mit dem Hinweis, dass nichts geloescht wird", True,
       "geloescht" in lizenzen or "gelöscht" in lizenzen)

titel("4) Rostock merkt davon nichts")
for sprache in ROSTOCK:
    pfad = config.STIMMEN.get(sprache, "")
    pruefe(f"{sprache} hat weiterhin eine Stimme", True, bool(pfad))
    pruefe(f"{sprache} ist nicht eine der entfernten", False,
           any(n in pfad for n in OHNE_LIZENZ))
    pruefe(f"{sprache} ist in teile.json erfasst", True,
           sprache in teile["stimmen"])
pruefe("die Zielsprachen sind unveraendert", ["en", "fa", "ru"],
       sorted(config.ZIELSPRACHEN))

print("")
if fehler:
    print(f"{fehler} FEHLER")
    sys.exit(1)
print("\033[32mAlle Faelle wie erwartet.\033[0m")
