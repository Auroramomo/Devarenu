#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ein Bericht, den man dem Betreuer schicken kann.

    python fehlerbericht.py            auf die Standardausgabe
    python fehlerbericht.py > b.txt    zum Anhaengen an eine Mail

ERLAUBNISLISTE, KEIN FILTER
---------------------------
Aufgenommen wird nur, was hier ausdruecklich steht. Der Unterschied
ist wesentlich: ein Filter muss alles kennen, was nicht hinein darf,
und wird beim naechsten neuen Feld zur Luecke. Eine Erlaubnisliste
faengt mit nichts an, und jedes Feld muss einzeln dazu.

WAS NIE HINEINKOMMT
-------------------
Mitschriften, Uebersetzungen, Zuschriften aus dem Saal,
Glossarinhalte, Namen aus dem Predigtmanuskript, WLAN-Name,
WLAN-Passwort, zustand.json im Ganzen.

Nichts davon wird eingesammelt und dann entfernt -- es wird gar nicht
erst geholt. Dazu kommt ein zweiter Riegel am Ende: der fertige Text
wird gegen die Muster der Segmentzeilen geprueft. Schlaegt er an, wird
die Zeile verworfen und vermerkt, DASS etwas entfernt wurde. Der Riegel
ist fuer den Tag gedacht, an dem jemand eine Quelle ergaenzt und nicht
daran denkt.

DAS JOURNAL NUR AB WARNSTUFE
----------------------------
Und das ist kein Geschmack: systemd legt alles, was auf stdout und
stderr geht, auf Stufe 6 (info) -- gemessen. Damit der Unterschied
ueberhaupt entsteht, stellt server.py seinen Warnungen "<4>" und
seinen Fehlern "<3>" voran. Die Segmentzeilen bekommen das NICHT.
Mitschrift kann so nicht auf Warnstufe erscheinen.
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import config

# Der zweite Riegel: Zeilen, die Inhalt tragen KOENNTEN.
#
# Eine fuer jede Stelle, an der server.py je Text ins Protokoll
# geschrieben hat. Sie schreiben ihn heute nicht mehr -- schutz() haelt
# ihn zurueck --, aber der Riegel gilt dem Tag, an dem jemand eine
# Quelle ergaenzt und nicht daran denkt.
#
# Die Liste ist beim Bauen gewachsen: der Test hat die Zuschrift aus
# dem Saal durchgelassen, weil sie nicht wie ein Segment aussieht.
VERDAECHTIG = [
    # [  42] 3.4s Ton, STT 0.31s, gesamt 1.02s | Der Herr ist mein ...
    # [   .] 3.4s Ton, sammle | ...      [   !] Notbremse nach 4s | ...
    re.compile(r"\[\s*[0-9.!]+\]\s+.*\|"),
    # Nachricht aus dem Saal (de): ...
    re.compile(r"Nachricht aus dem Saal"),
    # Manuskript: ..., 12 Namen (Anna, Bert, ...), Stellen: ...
    re.compile(r"Manuskript:.*Namen\s*\("),
    # Eingemessen: ... -- enthaelt keinen Text, aber die Zeile hat
    # schon einmal einen Satz gefuehrt; lieber gefangen als vergessen.
    re.compile(r"Eingemessen:.*[A-Za-z]{20,}"),
]


def verdaechtig(zeile):
    return any(m.search(zeile) for m in VERDAECHTIG)


# Der alte Name, damit Tests und Aufrufer ihn weiter finden.
SEGMENTZEILE = VERDAECHTIG[0]


def _lauf(befehl, zeit=20):
    try:
        a = subprocess.run(befehl, capture_output=True, text=True,
                           timeout=zeit)
        return (a.stdout or "").strip()
    except Exception as e:
        return f"(nicht zu ermitteln: {type(e).__name__})"


def _abschnitt(titel, zeilen):
    if not zeilen:
        return ""
    return f"\n--- {titel} " + "-" * max(0, 58 - len(titel)) + "\n" \
        + "\n".join(zeilen) + "\n"


def _fassung():
    zeilen = [f"Fassung        {config.VERSION}"]
    stand = _lauf(["git", "-C", str(config.BASIS), "log", "-1",
                   "--format=%h %ad", "--date=short"])
    zeilen.append(f"Stand          {stand}")
    schmutzig = _lauf(["git", "-C", str(config.BASIS), "status",
                       "--porcelain", "--untracked-files=no"])
    zeilen.append("Ordner         "
                  + ("VERAENDERT" if schmutzig else "unveraendert"))
    return zeilen


def _system():
    zeilen = []
    try:
        for z in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
            if z.startswith("PRETTY_NAME="):
                zeilen.append("System         " + z.split("=", 1)[1].strip('"'))
    except OSError:
        pass
    zeilen.append("Kern           " + _lauf(["uname", "-r"]))
    zeilen.append("Python         " + sys.version.split()[0])
    karte = _lauf(["nvidia-smi", "--query-gpu=name,driver_version",
                   "--format=csv,noheader"])
    zeilen.append("Grafik         " + (karte.split("\n")[0] if karte
                                       else "keine NVIDIA erkannt"))
    return zeilen


def _systemcheck():
    try:
        import systemcheck
        befunde = systemcheck.pruefen()
    except Exception as e:
        return [f"(Systemcheck fehlgeschlagen: {type(e).__name__})"]
    if not befunde:
        return ["ohne Befund"]
    # Nur Kennung, Schwere und der feste Text -- keine gesammelten
    # Inhalte. Die Texte stehen in systemcheck.py und sind bekannt.
    return [f"{b.schwere:8} {b.kennung:22} {b.was}" for b in befunde]


def _pruefen_zusammen():
    """Nur die Zusammenzaehlung von pruefen.sh, nicht seine Ausgabe.

    Die ganze Ausgabe waere lang und enthielte Geraetenamen und
    Netzadressen. Die drei Zahlen sagen, ob es sich lohnt
    nachzusehen."""
    pfad = config.BASIS / "pruefen.sh"
    if not pfad.exists():
        return []
    aus = _lauf(["bash", str(pfad)], zeit=240)
    for z in aus.split("\n"):
        nackt = re.sub(r"\x1b\[[0-9;]*m", "", z).strip()
        if "in Ordnung" in nackt:
            return [nackt]
    return ["(pruefen.sh lieferte keine Zusammenzaehlung)"]


def _update():
    stand = config.BASIS / "update" / "stand.json"
    if not stand.exists():
        return ["noch kein Update ueber Stick gelaufen"]
    try:
        d = json.loads(stand.read_text(encoding="utf-8"))
    except Exception:
        return ["(stand.json unlesbar)"]
    # Ausdruecklich diese vier Felder, nicht die ganze Datei.
    return [f"{k:14} {d.get(k, '-')}"
            for k in ("was", "version", "vorher", "zeit") if k in d]


def _journal():
    """Nur ab Warnstufe, nur diese drei Dienste, nur heute und gestern."""
    zeilen = []
    for dienst in ("devarenu", "dnsmasq", "devarenu-update"):
        aus = _lauf(["journalctl", "-u", dienst, "-p", "warning",
                     "--since", "-2 days", "--no-pager", "-n", "40"], zeit=30)
        if not aus or "No entries" in aus or "-- Keine" in aus:
            continue
        zeilen.append(f"[{dienst}]")
        zeilen += ["  " + z for z in aus.split("\n")[-40:]]
    return zeilen or ["keine Warnungen oder Fehler in den letzten zwei Tagen"]


def bauen():
    jetzt = datetime.now().strftime("%d.%m.%Y %H:%M")
    kopf = [
        "Devarenu -- Fehlerbericht",
        "=" * 62,
        f"Erstellt       {jetzt}",
        "",
        "Dieser Bericht enthaelt nur technische Angaben. Keine",
        "Mitschriften, keine Uebersetzungen, keine Zuschriften aus dem",
        "Saal, keine Namen aus dem Manuskript, kein WLAN-Passwort.",
    ]
    teile = [
        _abschnitt("Fassung", _fassung()),
        _abschnitt("Rechner", _system()),
        _abschnitt("Systemcheck", _systemcheck()),
        _abschnitt("Durchsicht (pruefen.sh)", _pruefen_zusammen()),
        _abschnitt("Letztes Update", _update()),
        _abschnitt("Meldungen ab Warnstufe", _journal()),
    ]
    text = "\n".join(kopf) + "\n" + "".join(teile)

    # Der zweite Riegel. Er soll nie anschlagen -- wenn doch, ist eine
    # Quelle dazugekommen, die jemand nicht bedacht hat.
    behalten, entfernt = [], 0
    for z in text.split("\n"):
        if verdaechtig(z):
            entfernt += 1
            continue
        behalten.append(z)
    if entfernt:
        behalten.append("")
        behalten.append(f"HINWEIS: {entfernt} Zeile(n) wurden entfernt, "
                        f"weil sie wie Mitschrift aussahen.")
    return "\n".join(behalten) + "\n"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--schnell", action="store_true",
                   help="ohne pruefen.sh, das dauert am laengsten")
    a = p.parse_args()
    if a.schnell:
        global _pruefen_zusammen
        _pruefen_zusammen = lambda: ["(uebersprungen)"]
    sys.stdout.write(bauen())
    return 0


if __name__ == "__main__":
    sys.exit(main())
