#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Holt die Lizenz jeder ausgelieferten Piper-Stimme aus ihrer Modellkarte.

    python werkzeuge/stimmlizenzen.py                 Tabelle auf den Schirm
    python werkzeuge/stimmlizenzen.py --json datei    dazu als JSON

WARUM DAS SEIN MUSS

Devarenu liefert 21 Piper-Stimmen mit. Jede ist auf einem anderen
Datensatz trainiert, und jeder Datensatz hat seine eigene Lizenz --
von CC0 (nichts zu beachten) bis zu Bedingungen, die eine Weitergabe
oder eine nichtkommerzielle Beschraenkung mitbringen. Solange niemand
nachgesehen hat, liefert das Projekt Dateien aus, deren Rechtsstand
es nicht kennt.

Gelesen wird die MODEL_CARD aus rhasspy/piper-voices -- dieselbe
Quelle, aus der einrichten.sh die Stimmen holt. Der Pfad steht in
config.STIMMEN; die Karte liegt im selben Ordner.

Dieses Werkzeug ENTFERNT nichts und entscheidet nichts. Es traegt
zusammen, was die Modellkarten sagen. Was daraus folgt, steht in
LIZENZEN.md.
"""

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))

import config                                   # noqa: E402

BASIS_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main"

GRUEN, ROT, GELB, BLAU, AUS = (
    "\033[32m", "\033[31m", "\033[33m", "\033[1;34m", "\033[0m")

# Lizenzen, bei denen eine Weitergabe oder die Nutzung in einer
# Gemeinde Fragen aufwerfen KANN. Nicht "verboten" -- "nachsehen".
#
#   NC / non-commercial  Eine Gemeinde handelt nicht kommerziell, aber
#                        "nichtkommerziell" ist ein unbestimmter
#                        Begriff, und Devarenu wird weitergegeben.
#   ND / no-derivatives  Ein feinabgestimmtes Modell IST eine
#                        Bearbeitung.
#   research only        Schliesst den Betrieb aus.
#   unknown / keine      Ohne Lizenz gibt es keine Erlaubnis.
HEIKEL = (
    (r"\bnc\b|non-?commercial|nicht-?kommerziell", "nichtkommerziell"),
    (r"\bnd\b|no-?deriv", "keine Bearbeitung"),
    (r"research|wissenschaft", "nur Forschung"),
    (r"^$|unknown|unbekannt|see |siehe ", "unklar"),
)


def karte_holen(pfad):
    """Der Text der MODEL_CARD, oder ""."""
    ordner = pfad.rsplit("/", 1)[0]
    url = f"{BASIS_URL}/{ordner}/MODEL_CARD"
    try:
        with urllib.request.urlopen(url, timeout=45) as a:
            return a.read().decode("utf-8", "replace")
    except Exception as e:
        print(f"   {ROT}!{AUS} {ordner}: {str(e)[:60]}", file=sys.stderr)
        return ""


def auslesen(text):
    """(Lizenz, Datensatz-URL, Trainingshinweis) aus einer Modellkarte.

    Die Karten sind von Hand geschrieben und nicht ganz einheitlich:
    manche nennen "License:", manche "license", manche setzen die
    Lizenz in eine eigene Zeile. Gesucht wird darum zeilenweise und
    nicht mit einem Muster ueber das ganze Dokument."""
    lizenz, url, training = "", "", ""
    abschnitt = ""
    for zeile in text.splitlines():
        z = zeile.strip()
        if z.startswith("##"):
            abschnitt = z.lstrip("# ").lower()
            continue
        m = re.match(r"^[*\-]?\s*(?:URL|Url|url)\s*:\s*(\S+)", z)
        if m and not url:
            url = m.group(1)
        m = re.match(r"^[*\-]?\s*(?:License|Licence|license)\s*:\s*(.+)$", z)
        if m and not lizenz:
            lizenz = m.group(1).strip().rstrip(".")
        if abschnitt.startswith("training") and z and not z.startswith(("*", "-")):
            training = (training + " " + z).strip()
    return lizenz, url, training


def einstufen(lizenz):
    """"" wenn unbedenklich, sonst der Grund zum Nachsehen."""
    kleine = (lizenz or "").strip().lower()
    for muster, grund in HEIKEL:
        if re.search(muster, kleine):
            return grund
    return ""


def main():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--json", help="Ergebnis zusaetzlich als JSON ablegen")
    a = p.parse_args()

    print(f"{BLAU}== {len(config.STIMMEN)} ausgelieferte Stimmen{AUS}")
    zeilen = []
    for sprache, pfad in sorted(config.STIMMEN.items()):
        name = pfad.rsplit("/", 1)[1]
        text = karte_holen(pfad)
        lizenz, url, training = auslesen(text)
        heikel = einstufen(lizenz)
        zeilen.append({
            "sprache": sprache,
            "name": config.SPRACHNAMEN.get(sprache, sprache),
            "stimme": name,
            "lizenz": lizenz or "(nicht genannt)",
            "datensatz": url,
            "training": training[:120],
            "heikel": heikel,
            "geprueft": sprache in getattr(config, "GEPRUEFT", set()),
        })
        marke = (GELB + "!" + AUS) if heikel else (GRUEN + "ok" + AUS)
        print(f"   {marke:12} {sprache:3} {name:30} {lizenz or '(keine)'}"
              + (f"   <- {heikel}" if heikel else ""))

    print(f"\n{BLAU}== Als Tabelle fuer LIZENZEN.md{AUS}\n")
    print("| Sprache | Stimme | Lizenz des Datensatzes | Anmerkung |")
    print("|---|---|---|---|")
    for z in zeilen:
        anm = f"**{z['heikel']}**" if z["heikel"] else ""
        print(f"| {z['name']} | `{z['stimme']}` | {z['lizenz']} | {anm} |")

    offen = [z for z in zeilen if z["heikel"]]
    print()
    if offen:
        print(f"{GELB}{len(offen)} Stimmen brauchen einen Blick:{AUS}")
        for z in offen:
            print(f"   {z['sprache']:3} {z['stimme']:30} {z['lizenz']}")
            if z["datensatz"]:
                print(f"       {z['datensatz']}")
    else:
        print(f"{GRUEN}Keine Stimme mit einer Lizenz, die Fragen aufwirft.{AUS}")

    if a.json:
        Path(a.json).write_text(
            json.dumps(zeilen, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")
        print(f"\n   {GRUEN}ok{AUS}   {a.json} geschrieben")
    return 0


if __name__ == "__main__":
    sys.exit(main())
