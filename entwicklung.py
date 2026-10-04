#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ist dies der Entwicklungsrechner?

    python entwicklung.py            sagt, ob er es ist, und warum
    python entwicklung.py --pruefen  Rueckgabe 0 = Entwicklungsrechner

WOFUER

Auf dem Rechner, an dem entwickelt wird, laeuft der Server dutzendfach
am Tag an -- und jedes Mal meldet der Systemcheck FEHLT fuer Dienst und
Autologin, weil es dort keinen Dienst und keine automatische Anmeldung
gibt. Jedes FEHLT merkt einen Fehlerbericht vor. An einem Tag in 0.4.5
lagen so neun Berichte in der Warteschlange, keiner davon ueber einen
echten Fehler.

Hinaus ging bisher keiner, weil dort keine meldung.json liegt. Aber das
ist ein Zufall, keine Regel: wer zum Ausprobieren von meldung.sh die
meldung.json einer Gemeinde hierher kopiert, schickt mit dem naechsten
Lauf alles in deren Kanal.

WARUM ZWEI BEDINGUNGEN

Beide muessen erfuellt sein, sonst verhaelt sich alles wie bisher:

  1. Die Datei ENTWICKLUNG liegt im Projektordner. Sie steht in
     .gitignore und kommt mit keinem Update und auf keinen Stick --
     der Stick traegt ein git-Buendel, also nur verfolgte Dateien.
  2. Der PRIVATE Signierschluessel liegt auf diesem Rechner.

Die zweite ist die eigentliche Sperre. Die erste allein waere eine
Datei, und Dateien wandern: jemand kopiert einen Ordner, spielt eine
Sicherung zurueck. Dann schwiege ein Gemeinderechner -- genau der, von
dem man die Berichte braucht. Den privaten Schluessel hat dagegen nur
der Rechner, der Fassungen signiert. Ein Gemeinderechner hat ihn nie
und darf ihn nie haben; laege er doch dort, waere das ein groesseres
Problem als ein fehlender Bericht.

Dasselbe Muster wie testmodus.py: eine Marke plus eine Eigenschaft
des Rechners, die sich nicht mitkopieren laesst.

WO DER SCHLUESSEL GESUCHT WIRD

Kein fester Pfad mit Benutzername. Zuerst dort, wohin git ihn ohnehin
schaut: user.signingkey aus der git-Konfiguration dieses Ordners
(repo-lokal oder global). Das ist der Schluessel, mit dem hier
tatsaechlich signiert wird -- wer ihn umzieht, zieht die Erkennung mit.
Steht dort der oeffentliche Teil (.pub), wird daneben nach dem privaten
gesehen. Steht dort gar kein Pfad (git erlaubt auch "key::ssh-ed25519
..."), dann der Ort, den AUFSTELLEN.md fuer ihn nennt:
~/.ssh/devarenu_freigabe.

Gelesen wird nur die erste Zeile, um zu sehen, ob es ein privater
Schluessel ist. Nichts davon wird ausgegeben oder gespeichert.
"""
import subprocess
import sys
from pathlib import Path

import config

MARKE = config.BASIS / "ENTWICKLUNG"
# Der Ort aus AUFSTELLEN.md, Abschnitt "Der Signierschluessel".
VORGABE = Path("~/.ssh/devarenu_freigabe")


def _aus_git():
    """Der Pfad aus user.signingkey, oder None."""
    try:
        r = subprocess.run(
            ["git", "-C", str(config.BASIS), "config", "--get",
             "user.signingkey"],
            capture_output=True, text=True, timeout=5)
    except Exception:
        return None
    wert = (r.stdout or "").strip()
    if r.returncode != 0 or not wert or wert.startswith("key::"):
        return None
    return Path(wert)


def kandidaten():
    """Wo ein privater Signierschluessel liegen koennte, in dieser Folge."""
    orte = []
    p = _aus_git()
    if p is not None:
        p = p.expanduser()
        orte.append(p.with_suffix("") if p.suffix == ".pub" else p)
    orte.append(VORGABE.expanduser())
    return orte


def _privat(pfad):
    try:
        with open(pfad, "r", encoding="ascii", errors="replace") as f:
            erste = f.readline()
    except OSError:
        return False
    return "PRIVATE KEY" in erste


def schluessel_da():
    return any(_privat(p) for p in kandidaten())


def marke_da():
    return MARKE.is_file()


def lage():
    """(ist_entwicklung, marke, schluessel)."""
    m = marke_da()
    s = schluessel_da()
    return m and s, m, s


def ist_entwicklungsrechner():
    """True nur, wenn BEIDE Bedingungen erfuellt sind. Faengt alles:
    eine Erkennung, die selbst scheitert, darf nichts verschweigen --
    im Zweifel ist es KEIN Entwicklungsrechner, und alles geht hinaus
    wie bisher."""
    try:
        return lage()[0]
    except Exception:
        return False


def main(argv):
    ja, m, s = lage()
    if "--pruefen" in argv:
        return 0 if ja else 1
    print(f"Marke {MARKE.name}: {'ja' if m else 'nein'}")
    print(f"Privater Signierschluessel: {'ja' if s else 'nein'}")
    print("Entwicklungsrechner: " + ("JA -- es werden keine Berichte "
          "vorgemerkt und keine Meldungen verschickt." if ja
          else "nein -- alles wie gewohnt."))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
