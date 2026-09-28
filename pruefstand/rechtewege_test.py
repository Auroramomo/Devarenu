#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wird irgendwo root-700 angelegt und danach ohne Rechte gelesen?

    python pruefstand/rechtewege_test.py

DIE FEHLERART

Ein Skript legt einen Ordner an, der nur der Wurzel gehoert -- mit
gutem Grund, meistens weil darin gleich Code ausgefuehrt wird oder
ein Geheimnis liegt. Ein paar Zeilen weiter sieht dasselbe Skript
hinein, aber als Dienstbenutzer. Es findet nichts. Und weil "nichts
gefunden" und "darf nicht hineinsehen" gleich aussehen, meldet es
etwas Falsches.

Zweimal passiert, beide Male in aktualisieren.sh:

    als_wurzel mkdir -p "$AUSZUG"
    als_wurzel chmod 700 "$AUSZUG"
    ...
    if [ ! -f "$AUSZUG/aktualisierung.sh" ]; then
      fehl "v0.3.3 bringt keine aktualisierung.sh mit."

Die Datei lag da. Das Update brach ab, ohne etwas zu aendern, und die
Meldung zeigte in die falsche Richtung -- man sucht dann im Tag statt
in den Rechten.

Und bei der Sicherung: sie gehoerte der Wurzel, gesundheit.sh
--vorher laeuft als Dienstbenutzer und konnte seine Grundlinie nicht
hineinschreiben. Ohne Grundlinie galt hinterher JEDER vorhandene
Befund als neu -- ein tadelloses Update waere zurueckgerollt worden.

WARUM EIN LESENDER PRUEFSTAND

Der gewoehnliche Weg waere ein Lauf, der es nachstellt. Der geht hier
nur halb: ohne Wurzelrechte laesst sich kein root-eigener Ordner
anlegen, und mit den Attrappen des Pruefstands laeuft ohnehin alles
als derselbe Benutzer -- genau deshalb ist der Fehler zweimal durch
alle Laeufe gekommen. Also wird der Quelltext gelesen: wo ein Pfad
scharf gemacht wird, muss jeder spaetere Zugriff darauf durch
als_wurzel oder sudo gehen.

Dazu kommt unten ein Lauf, der den Fall mit einer Attrappe
nachstellt, die Rechte wirklich simuliert.
"""

import re
import subprocess
import sys
import tempfile
import os
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent

GRUEN, ROT, GELB, AUS = "\033[32m", "\033[31m", "\033[33m", "\033[0m"
FEHLER = 0

# Die Skripte, die mit Wurzelrechten hantieren.
SKRIPTE = ["aktualisieren.sh", "aktualisierung.sh", "stick_update.sh",
           "bootstrap.sh", "dienst.sh", "wartungsfenster.sh"]


def laeuft_unprivilegiert(text):
    """Laeuft dieses Skript selbst als Dienstbenutzer?

    Die Skripte sagen es selbst, an ihren Hilfsfunktionen:

      als_wurzel  -- das Skript MUSS nach Rechten fragen, es hat also
                     keine. stick_update.sh braucht so etwas nie.
      als_benutzer -- das Skript IST die Wurzel und steigt fuer
                     einzelne Schritte herab.

    Nur im ersten Fall ist ein blanker Zugriff auf einen root-700-Pfad
    ein Fehler. In stick_update.sh liest dieselbe Zeile als Wurzel,
    und dann ist sie richtig.

    aktualisieren.sh hat beides: es laeuft als Besitzer und holt sich
    Privilegiertes einzeln. Es zaehlt als unprivilegiert -- richtig,
    genau dort lag der Fehler."""
    if re.search(r'^als_wurzel\(\)', text, re.M):
        return True             # muss fragen -- hat also keine Rechte
    if re.search(r'^als_benutzer\(\)', text, re.M):
        return False            # steigt herab -- ist also die Wurzel
    if re.search(r'^\s*sudo \S', text, re.M):
        return True             # fragt ohne Hilfsfunktion
    return True                 # im Zweifel streng

# Womit ein Pfad scharf gemacht wird.
SCHARF = re.compile(
    r'(?:als_wurzel |sudo )?(?:chmod\s+(?:0?700|0?600)|chown\s+root:root)\s+'
    r'"?\$(?:\{)?([A-Za-z_][A-Za-z0-9_]*)')

# Ein Zugriff OHNE Rechte: test/[/cat/ls/source und Umleitungen, die
# den Pfad unmittelbar anfassen.
OHNE_RECHTE = re.compile(
    r'(?<!als_wurzel )(?<!sudo )'
    r'(?:\[\s+!?\s*-(?![nz]\b)[a-z]\s+|\btest\s+!?\s*-(?![nz]\b)[a-z]\s+'
    r'|\bcat\s+|\bsource\s+|\b\.\s+)'
    r'"?\$(?:\{)?([A-Za-z_][A-Za-z0-9_]*)')


def pruefe(was, erwartet, ist):
    global FEHLER
    if erwartet == ist:
        print(f"   ok    {was}")
    else:
        print(f"   {ROT}FEHL{AUS}  {was}: erwartet {erwartet!r}, ist {ist!r}")
        FEHLER += 1


def titel(t):
    print(f"\n\033[1m== {t}\033[0m")


def fundstellen(text):
    """[(zeilennummer, variable, zeile)] -- Zugriffe ohne Rechte auf
    Pfade, die vorher scharf gemacht wurden."""
    scharfe = set()
    treffer = []
    for nr, zeile in enumerate(text.split("\n"), 1):
        blank = zeile.split("#", 1)[0]
        if not blank.strip():
            continue
        for m in SCHARF.finditer(blank):
            scharfe.add(m.group(1))
        for m in OHNE_RECHTE.finditer(blank):
            if m.group(1) in scharfe:
                treffer.append((nr, m.group(1), zeile.strip()))
    return treffer


titel("1) Der Wächter selbst erkennt den Fehler wieder")

# Ohne diesen Fall prueft der Rest nur, dass nichts gefunden wird --
# und das taete er auch, wenn der Ausdruck kaputt waere.
BEISPIEL = '''
als_wurzel mkdir -p "$AUSZUG"
als_wurzel chmod 700 "$AUSZUG"
if [ ! -f "$AUSZUG/aktualisierung.sh" ]; then
  fehl "bringt keine mit"
fi
'''
gefunden = fundstellen(BEISPIEL)
pruefe("der Fehler vom 28.09. wird gefunden", 1, len(gefunden))
pruefe("und die Variable benannt", "AUSZUG",
       gefunden[0][1] if gefunden else "")

BEHOBEN = BEISPIEL.replace('if [ ! -f "$AUSZUG/aktualisierung.sh" ]',
                           'if ! als_wurzel test -f "$AUSZUG/aktualisierung.sh"')
pruefe("die behobene Fassung ist sauber", 0, len(fundstellen(BEHOBEN)))

# Ein Pfad, der nie scharf gemacht wurde, geht niemanden etwas an.
pruefe("ein gewoehnlicher Pfad schlaegt nicht an", 0,
       len(fundstellen('if [ -f "$ORDNER/VERSION" ]; then :; fi\n')))

titel("2) Die Skripte")

for name in SKRIPTE:
    pfad = WURZEL / name
    if not pfad.exists():
        print(f"   {GELB}fehlt{AUS} {name}")
        continue
    text = pfad.read_text(encoding="utf-8")
    if not laeuft_unprivilegiert(text):
        print(f"   ok    {name} (laeuft selbst als Wurzel)")
        continue
    treffer = sorted(set(fundstellen(text)))
    if treffer:
        for nr, var, zeile in treffer:
            print(f"   {ROT}FEHL{AUS}  {name}:{nr} liest ${var} ohne Rechte")
            print(f"           {zeile[:70]}")
            FEHLER += 1
    else:
        print(f"   ok    {name}")

titel("3) Nachgestellt, mit einer Attrappe, die Rechte simuliert")

# Ohne Wurzelrechte laesst sich kein root-eigener Ordner anlegen. Was
# sich nachstellen laesst, ist die WIRKUNG: was durch die
# sudo-Attrappe laeuft, darf hineinsehen; was daran vorbeigeht, nicht.
with tempfile.TemporaryDirectory() as o:
    ordner = Path(o)
    (ordner / "scharf").mkdir()
    (ordner / "scharf" / "aktualisierung.sh").write_text("#!/bin/sh\n")
    stubs = ordner / "stubs"
    stubs.mkdir()
    (stubs / "sudo").write_text(
        '#!/bin/sh\n'
        '# Simuliert Wurzelrechte: macht den Ordner auf, fuehrt aus,\n'
        '# macht ihn wieder zu. Ohne diesen Umweg kommt niemand hinein.\n'
        f'chmod 700 "{ordner}/scharf"\n'
        '"$@"; rc=$?\n'
        f'chmod 000 "{ordner}/scharf"\n'
        'exit $rc\n', encoding="utf-8")
    (stubs / "sudo").chmod(0o755)
    (ordner / "scharf").chmod(0o000)

    def lauf(zeile):
        skript = (f'als_wurzel() {{ sudo "$@"; }}\n'
                  f'AUSZUG="{ordner}/scharf"\n'
                  f'if {zeile}; then echo GEFUNDEN; else echo NICHTS; fi\n')
        r = subprocess.run(["bash", "-c", skript], capture_output=True,
                           text=True, env={**os.environ,
                                           "PATH": f"{stubs}:{os.environ['PATH']}"})
        return r.stdout.strip()

    pruefe("ohne Rechte findet [ -f ] nichts -- der alte Fehler",
           "NICHTS", lauf('[ -f "$AUSZUG/aktualisierung.sh" ]'))
    pruefe("mit als_wurzel test wird sie gefunden -- die Behebung",
           "GEFUNDEN", lauf('als_wurzel test -f "$AUSZUG/aktualisierung.sh"'))
    (ordner / "scharf").chmod(0o700)

titel("4) Der Elternordner, durch den niemand hindurchkommt")

# Der Fehler vom 28.09., zweiter Teil. Die Rechte der Datei selbst
# waren richtig -- sie gehoerte dem Dienstbenutzer mit 600. Nur lag
# sie unter /var/lib/devarenu/updates, und das war root mit 710.
#
# 710 sieht aus, als duerfte jemand hindurch. Es gibt das Durchgehen
# aber der GRUPPE, und der Ordner gehoert root:root -- der
# Dienstbenutzer ist dort "andere" und bekommt nichts. Fuer ihn war
# der Ordner so zu wie mit 700.
#
# Es genuegt also nicht, die Rechte einer Datei zu pruefen. Jeder
# Ordner auf dem Weg dorthin muss durchgehbar sein.
with tempfile.TemporaryDirectory() as o:
    ablage = Path(o) / "updates"
    (ablage / "vorher-9.9.9").mkdir(parents=True)
    ziel = ablage / "vorher-9.9.9" / "befunde-vorher"
    ziel.write_text("autologin\n", encoding="utf-8")
    ziel.chmod(0o600)

    def erreichbar():
        """Kommt man an die Datei heran? Wie ein fremder Benutzer --
        ohne Leserecht auf dem Weg dorthin geht es nicht."""
        try:
            return ziel.read_text(encoding="utf-8") != ""
        except OSError:
            return False

    # 700 auf der Ablage: der Besitzer kommt durch, ein anderer nicht.
    # Nachgestellt wird es ueber den Modus, den ein anderer Benutzer
    # saehe -- 0 Rechte fuer "andere".
    ablage.chmod(0o700)
    pruefe("700 gibt anderen kein Durchgehen", 0, ablage.stat().st_mode & 0o007)
    ablage.chmod(0o710)
    pruefe("710 auch nicht -- das war der Fehler", 0,
           ablage.stat().st_mode & 0o007)
    ablage.chmod(0o711)
    pruefe("711 gibt das Durchgehen", 0o001, ablage.stat().st_mode & 0o007)
    pruefe("aber kein Auflisten", 0, ablage.stat().st_mode & 0o004)
    pruefe("und die Datei bleibt fuer andere zu", 0,
           ziel.stat().st_mode & 0o007)
    pruefe("der Besitzer kommt heran", True, erreichbar())

    # Und der eigentliche Fall: ein zugesperrter Elternordner macht
    # eine tadellose Datei unerreichbar.
    ablage.chmod(0o000)
    pruefe("zugesperrter Elternordner sperrt die Datei aus", False,
           erreichbar())
    ablage.chmod(0o711)
    pruefe("wieder geoeffnet, wieder da", True, erreichbar())

# Und dass die Skripte es richtig machen: nirgends darf $DATEN oder
# $ABLAGE auf 700 oder 710 gesetzt werden.
titel("5) Keine Ablage auf 700 oder 710")

ENG = re.compile(r'chmod\s+(?:0?700|0?710)\s+"?\$(?:\{)?'
                 r'(DATEN|ABLAGE)\b')
for name in SKRIPTE:
    pfad = WURZEL / name
    if not pfad.exists():
        continue
    schlecht = []
    for nr, zeile in enumerate(pfad.read_text(encoding="utf-8").split("\n"), 1):
        blank = zeile.split("#", 1)[0]
        if ENG.search(blank):
            schlecht.append((nr, zeile.strip()))
    if schlecht:
        for nr, zeile in schlecht:
            print(f"   {ROT}FEHL{AUS}  {name}:{nr} sperrt die Ablage zu")
            print(f"           {zeile[:70]}")
            FEHLER += 1
    else:
        print(f"   ok    {name}")

print()
if FEHLER:
    print(f"{ROT}{FEHLER} Fehler.{AUS}")
    sys.exit(1)
print(f"{GRUEN}Alle Faelle wie erwartet.{AUS}")
