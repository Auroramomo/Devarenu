#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Merkt der Systemcheck, dass Wayland laeuft, obwohl X11 dasteht?

    python pruefstand/sitzung_test.py

Der Fall kam vom Gemeinderechner: in der Anmeldung stand
Session=plasmax11, der Systemcheck meldete gruen, und Plasma lief
unter Wayland. Geprueft wurde bis 0.3.1 nur, was EINGESTELLT ist --
nicht, was laeuft. Eine Auskunft, die nur die eigene Konfiguration
liest, bestaetigt den Wunsch und nicht den Zustand.

Alles hier laeuft gegen Wegwerfordner. Die Faelle, um die es geht,
lassen sich auf einem laufenden Rechner nicht herstellen -- und was
unter /etc steht, geht einen Pruefstand nichts an.
"""

import sys
import tempfile
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))

import systemcheck  # noqa: E402

GRUEN, ROT, AUS = "\033[32m", "\033[31m", "\033[0m"
FEHLER = 0


def pruefe(was, erwartet, ist):
    global FEHLER
    if erwartet == ist:
        print(f"   ok    {was}")
    else:
        print(f"   {ROT}FEHL{AUS}  {was}: erwartet {erwartet!r}, ist {ist!r}")
        FEHLER += 1


def titel(t):
    print(f"\n\033[1m== {t}\033[0m")


def befunde_fuer(inhalt, laeuft, x11_da=False):
    """Fuehrt _autologin gegen einen erfundenen Rechner aus.

    Zurueck kommen nur die Kennungen -- der Wortlaut der Meldung darf
    sich aendern, ohne dass hier etwas rot wird."""
    with tempfile.TemporaryDirectory() as ordner:
        (Path(ordner) / "zzz-devarenu-autologin.conf").write_text(
            inhalt, encoding="utf-8")
        alt_lauf = systemcheck.laufende_sitzung
        alt_datei = systemcheck.sitzungsdatei
        systemcheck.laufende_sitzung = lambda: laeuft
        systemcheck.sitzungsdatei = (
            lambda name: "/usr/share/xsessions/plasmax11.desktop"
            if (x11_da and name == "plasmax11") else "")
        try:
            gesammelt = []
            systemcheck._autologin(gesammelt, [ordner])
            return [b.kennung for b in gesammelt]
        finally:
            systemcheck.laufende_sitzung = alt_lauf
            systemcheck.sitzungsdatei = alt_datei


X11 = "[Autologin]\nUser=gemeinde\nSession=plasmax11\nRelogin=false\n"
WAY = "[Autologin]\nUser=gemeinde\nSession=plasma\nRelogin=false\n"
OHNE = "[Autologin]\nUser=gemeinde\nRelogin=false\n"

titel("1) Der Fall vom Gemeinderechner")

# Das ist der Grund fuer diesen Pruefstand: eingestellt X11, es laeuft
# Wayland. Vor 0.3.1 kam hier eine leere Liste zurueck -- gruen.
pruefe("eingestellt X11, es laeuft Wayland -> gemeldet",
       ["sitzung_abweichend"], befunde_fuer(X11, "wayland"))

pruefe("eingestellt X11, es laeuft X11 -> still",
       [], befunde_fuer(X11, "x11", x11_da=True))

titel("2) Die anderen Lagen")

pruefe("eingestellt Wayland (heisst \"plasma\") -> gemeldet",
       ["autologin_wayland"], befunde_fuer(WAY, "wayland"))

pruefe("keine Sitzung eingetragen, Wayland laeuft",
       ["autologin_wayland"], befunde_fuer(OHNE, "wayland"))

pruefe("keine Sitzung eingetragen, X11 laeuft -> still",
       [], befunde_fuer(OHNE, "x11"))

# Kein loginctl, ein Rechner ohne systemd, ein Dienst ohne Auskunft:
# dann ist die laufende Sitzung unbekannt. Unbekannt ist kein Befund.
pruefe("laufende Sitzung unbekannt -> keine Behauptung",
       [], befunde_fuer(X11, ""))

pruefe("gar keine Anmeldung eingerichtet",
       ["autologin"], befunde_fuer("[Autologin]\nRelogin=false\n", "x11"))

titel("3) Die Ursache steht in der Meldung")

# Fehlt plasmax11.desktop, zeigt die Einstellung ins Leere. Das ist
# die eigentliche Auskunft -- ohne sie sucht jemand eine Stunde in
# einer Konfiguration, die richtig dasteht.
with tempfile.TemporaryDirectory() as o:
    (Path(o) / "a.conf").write_text(X11, encoding="utf-8")
    alt_lauf, alt_datei = (systemcheck.laufende_sitzung,
                           systemcheck.sitzungsdatei)
    systemcheck.laufende_sitzung = lambda: "wayland"
    systemcheck.sitzungsdatei = lambda name: ""
    try:
        gesammelt = []
        systemcheck._autologin(gesammelt, [o])
        text = gesammelt[0].was + " " + gesammelt[0].tun
    finally:
        systemcheck.laufende_sitzung = alt_lauf
        systemcheck.sitzungsdatei = alt_datei
pruefe("fehlende Sitzungsdatei wird benannt", True, "gibt es" in text)
pruefe("das Paket wird genannt", True, "plasma-x11-session" in text)

titel("4) Die laufende Sitzung lesen")

# loginctl listet neben der grafischen Sitzung eine "manager"-Sitzung
# ohne Typ. Wer die erste Zeile nimmt, bekommt "" und meldet nichts.
ANTWORTEN = {
    ("loginctl", "list-sessions", "--no-legend"): "1 1000 gemeinde -\n"
                                                  "2 1000 gemeinde seat0\n",
    ("loginctl", "show-session", "1", "-p", "Type", "-p", "Class",
     "-p", "Active"): "Type=unspecified\nClass=manager\nActive=yes\n",
    ("loginctl", "show-session", "2", "-p", "Type", "-p", "Class",
     "-p", "Active"): "Type=wayland\nClass=user\nActive=yes\n",
}
alt = systemcheck._lauf
systemcheck._lauf = lambda b, **k: ANTWORTEN.get(tuple(b))
try:
    pruefe("die Manager-Sitzung wird uebergangen",
           "wayland", systemcheck.laufende_sitzung())
    systemcheck._lauf = lambda b, **k: None
    pruefe("ohne loginctl: keine Auskunft, keine Erfindung",
           "", systemcheck.laufende_sitzung())
finally:
    systemcheck._lauf = alt

print()
if FEHLER:
    print(f"{ROT}{FEHLER} Fehler.{AUS}")
    sys.exit(1)
print(f"{GRUEN}Alle Faelle wie erwartet.{AUS}")
