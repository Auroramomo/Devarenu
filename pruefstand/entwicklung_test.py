#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Erkennt Devarenu den Entwicklungsrechner -- und NUR ihn?

    .venv/bin/python pruefstand/entwicklung_test.py

Zwei Bedingungen, beide muessen erfuellt sein (entwicklung.py):

  1. die Marke ENTWICKLUNG im Projektordner,
  2. der private Signierschluessel auf dem Rechner.

Dann: berichtpost reiht nichts ein, meldung.sh sendet nichts und merkt
nichts vor, der Systemcheck meldet einen Hinweis statt FEHLT fuer
Dienst und Autologin. Ist nur eine erfuellt, ist alles wie bisher --
das ist der wichtigere Teil, denn ein Gemeinderechner, der faelschlich
schweigt, ist schlimmer als ein Entwicklungsrechner, der zu viel meldet.

Und: die Marke wandert nicht. Kein Stick, kein Update traegt sie.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
WURZEL = HIER.parent
sys.path.insert(0, str(WURZEL))
sys.path.insert(0, str(HIER))

import config  # noqa: E402
import entwicklung  # noqa: E402
import berichtpost  # noqa: E402
import systemcheck  # noqa: E402
from hilfe import arbeitskopie, wegwerfordner  # noqa: E402

GRUEN, ROT, AUS = "\033[32m", "\033[31m", "\033[0m"
FEHLER = 0
# Aus Teilen zusammengesetzt: die Kopfzeile woertlich im Quelltext
# hielte oeffentlich_pruefen.sh -- zu Recht -- fuer einen echten
# Schluessel. Mehr als die Kopfzeile prueft entwicklung.py nicht.
PRIVAT = "-----BEGIN OPENSSH " + "PRIVATE KEY-----\nnur eine Attrappe\n"
OEFFENTLICH = "ssh-ed25519 AAAAattrappe pruef@pruefstand\n"


def pruefe(was, erwartet, ist):
    global FEHLER
    if erwartet == ist:
        print(f"   ok    {was}")
    else:
        print(f"   {ROT}FEHL{AUS}  {was}: erwartet {erwartet!r}, ist {ist!r}")
        FEHLER += 1


def titel(t):
    print(f"\n\033[1m== {t}\033[0m")


ORD = wegwerfordner("devarenu-entw-")
MARKE = ORD / "ENTWICKLUNG"
SCHLUESSEL = ORD / "schluessel"


def stellen(marke, schluessel, schluessel_inhalt=PRIVAT):
    """Die Lage herstellen, ohne den echten Rechner anzufassen."""
    for p in (MARKE, SCHLUESSEL):
        if p.exists():
            p.unlink()
    if marke:
        MARKE.write_text("", encoding="utf-8")
    if schluessel:
        SCHLUESSEL.write_text(schluessel_inhalt, encoding="utf-8")
    entwicklung.MARKE = MARKE
    entwicklung.kandidaten = lambda: [SCHLUESSEL]


def befunde_mit_fehlt():
    """Eine Befundliste, wie sie ein Entwicklungsrechner liefert --
    dazu ein FEHLT, das mit der Entwicklung nichts zu tun hat."""
    B, F = systemcheck.Befund, systemcheck.FEHLT
    return [B("dienst_devarenu", F, "x"), B("dienst_ollama_tot", F, "x"),
            B("autologin", F, "x"), B("ollama_cpu", F, "x"),
            B("standby", systemcheck.HINWEIS, "x")]


titel("1) Vier Lagen")
for marke, schluessel, erwartet in [(False, False, False),
                                    (True, False, False),
                                    (False, True, False),
                                    (True, True, True)]:
    wie = (f"Marke {'ja' if marke else 'nein'}, "
           f"Schluessel {'ja' if schluessel else 'nein'}")
    stellen(marke, schluessel)
    pruefe(f"{wie}: Entwicklungsrechner {erwartet}", erwartet,
           entwicklung.ist_entwicklungsrechner())

    # berichtpost
    w = berichtpost.Warteschlange(ORD / "berichte")
    vorher = sorted(p.name for p in (ORD / "berichte").glob("*.txt")) \
        if (ORD / "berichte").exists() else []
    p = w.einreihen("systemcheck", "Fassung x\nautologin fehlt\n")
    pruefe(f"{wie}: Bericht {'NICHT ' if erwartet else ''}eingereiht",
           not erwartet, p is not None)
    if erwartet:
        nachher = sorted(q.name for q in (ORD / "berichte").glob("*.txt"))
        pruefe(f"{wie}: liegende Berichte unangetastet", vorher, nachher)

    # Systemcheck
    b = systemcheck._entwicklungsrechner(befunde_mit_fehlt())
    kennungen = sorted(x.kennung for x in b)
    if erwartet:
        pruefe(f"{wie}: kein FEHLT mehr fuer Dienst und Autologin", [],
               [x.kennung for x in b if x.schwere == systemcheck.FEHLT
                and x.kennung.startswith(("dienst_", "autologin"))])
        pruefe(f"{wie}: stattdessen ein Hinweis", True,
               any(x.kennung == "entwicklungsrechner"
                   and x.schwere == systemcheck.HINWEIS for x in b))
        pruefe(f"{wie}: anderes FEHLT bleibt stehen", True,
               "ollama_cpu" in kennungen)
        h = [x for x in b if x.kennung == "entwicklungsrechner"][0]
        pruefe(f"{wie}: der Hinweis steht am Pult, nicht unter Wartung",
               False, h.wartung)
    else:
        pruefe(f"{wie}: Befunde unveraendert",
               sorted(x.kennung for x in befunde_mit_fehlt()), kennungen)

titel("2) Ein oeffentlicher Schluessel ist kein privater")
stellen(True, True, OEFFENTLICH)
pruefe("Marke plus .pub-Inhalt: KEIN Entwicklungsrechner", False,
       entwicklung.ist_entwicklungsrechner())

titel("3) Wo der Schluessel gesucht wird")
# Echte Logik, nicht gestellt: ein eigenes git-Repo mit user.signingkey.
import importlib  # noqa: E402
entwicklung = importlib.reload(entwicklung)
repo = ORD / "repo"
repo.mkdir()
subprocess.run(["git", "init", "-q", str(repo)], check=True)
subprocess.run(["git", "-C", str(repo), "config", "user.signingkey",
                str(ORD / "freigabe.pub")], check=True)
alt_basis = config.BASIS
config.BASIS = repo
try:
    k = entwicklung.kandidaten()
    pruefe("aus user.signingkey, .pub abgeschnitten", ORD / "freigabe", k[0])
    pruefe("dahinter der Ort aus AUFSTELLEN.md", True,
           k[-1] == Path("~/.ssh/devarenu_freigabe").expanduser())
    subprocess.run(["git", "-C", str(repo), "config", "user.signingkey",
                    "key::ssh-ed25519 AAAAattrappe"], check=True)
    k = entwicklung.kandidaten()
    pruefe("key:: ist kein Pfad: nur der Ort aus AUFSTELLEN.md", 1, len(k))
finally:
    config.BASIS = alt_basis
# Kein Benutzername im Quelltext.
quelle = (WURZEL / "entwicklung.py").read_text(encoding="utf-8")
pruefe("kein /home/ im Quelltext", False, "/home/" in quelle)

titel("4) meldung.sh sendet nichts und merkt nichts vor")
# Eine Arbeitskopie mit eigenem HOME: dort liegt (oder liegt nicht) der
# Schluessel unter ~/.ssh/devarenu_freigabe. Kein git-Repo, also greift
# der Ort aus AUFSTELLEN.md.
kopie = arbeitskopie(ORD / "kopie")
shutil.copy2(WURZEL / "meldung.sh", kopie / "meldung.sh")
heim = ORD / "heim"
(heim / ".ssh").mkdir(parents=True)
(kopie / "meldung.json").write_text(
    '{"ntfy": "https://ntfy.invalid/pruefstand"}', encoding="utf-8")
os.chmod(kopie / "meldung.json", 0o600)
spur = ORD / "curl.log"
curl = ORD / "curl"
curl.write_text(f'#!/bin/sh\necho "$@" >> "{spur}"\nexit 0\n',
                encoding="utf-8")
curl.chmod(0o755)
umgebung = dict(os.environ, HOME=str(heim), DEVARENU_CURL=str(curl),
                XDG_CONFIG_HOME=str(heim / ".config"),
                GIT_CONFIG_NOSYSTEM="1")


def melden(*args):
    if spur.exists():
        spur.unlink()
    offen = kopie / "meldung-offen.txt"
    if offen.exists():
        offen.unlink()
    r = subprocess.run(["bash", str(kopie / "meldung.sh"), *args],
                       capture_output=True, text=True, env=umgebung,
                       timeout=60)
    return r.returncode, spur.exists(), offen.exists(), r.stderr


for marke, schluessel, dev in [(False, False, False), (True, False, False),
                               (False, True, False), (True, True, True)]:
    wie = (f"Marke {'ja' if marke else 'nein'}, "
           f"Schluessel {'ja' if schluessel else 'nein'}")
    m = kopie / "ENTWICKLUNG"
    s = heim / ".ssh" / "devarenu_freigabe"
    for p in (m, s):
        if p.exists():
            p.unlink()
    if marke:
        m.write_text("", encoding="utf-8")
    if schluessel:
        s.write_text(PRIVAT, encoding="utf-8")
    rc, gesendet, vorgemerkt, fehler = melden("Devarenu: Probe", "Text")
    if dev:
        pruefe(f"{wie}: verweigert (Rueckgabe 3)", 3, rc)
        pruefe(f"{wie}: curl nicht gerufen", False, gesendet)
        pruefe(f"{wie}: nichts vorgemerkt", False, vorgemerkt)
        pruefe(f"{wie}: sagt, warum", True, "Entwicklungsrechner" in fehler)
        rc, gesendet, _, _ = melden("--berichte")
        pruefe(f"{wie}: --berichte verweigert", (3, False), (rc, gesendet))
        rc, gesendet, _, _ = melden("--nachreichen")
        pruefe(f"{wie}: --nachreichen verweigert", (3, False), (rc, gesendet))
    else:
        pruefe(f"{wie}: geht hinaus wie bisher", (0, True), (rc, gesendet))

titel("5) Die Marke wandert nicht")
r = subprocess.run(["git", "-C", str(WURZEL), "check-ignore", "-q",
                    "ENTWICKLUNG"])
pruefe("ENTWICKLUNG steht in .gitignore", 0, r.returncode)
# Der Stick traegt ein git-Buendel. Ein Klon mit Marke, daraus ein
# Buendel, daraus ein neuer Klon: die Marke darf darin nicht stehen.
quelle_repo = ORD / "quelle"
subprocess.run(["git", "clone", "-q", "--no-hardlinks", str(WURZEL),
                str(quelle_repo)], check=True)
# Die .gitignore der Arbeitskopie, nicht die des letzten Commits: geprueft
# wird der Stand, der ausgeliefert wird, auch vor seinem Commit.
shutil.copy2(WURZEL / ".gitignore", quelle_repo / ".gitignore")
(quelle_repo / "ENTWICKLUNG").write_text("", encoding="utf-8")
subprocess.run(["git", "-C", str(quelle_repo), "add", "-A"], check=True)
st = subprocess.run(["git", "-C", str(quelle_repo), "status", "--porcelain"],
                    capture_output=True, text=True).stdout
pruefe("git add -A nimmt sie nicht auf", False, "ENTWICKLUNG" in st)
subprocess.run(["git", "-C", str(quelle_repo), "bundle", "create",
                str(ORD / "stick.bundle"), "--all"],
               check=True, capture_output=True)
ziel_repo = ORD / "gemeinde"
subprocess.run(["git", "clone", "-q", str(ORD / "stick.bundle"),
                str(ziel_repo)], check=True)
pruefe("im Klon aus dem Buendel liegt keine Marke", False,
       (ziel_repo / "ENTWICKLUNG").exists())
sb = (WURZEL / "stick_bauen.sh").read_text(encoding="utf-8")
pruefe("stick_bauen.sh packt das Repo als Buendel", True,
       "git bundle create" in sb)
pruefe("und nennt die Marke nirgends", False, "ENTWICKLUNG" in sb)

print()
if FEHLER:
    print(f"{ROT}{FEHLER} Fehler.{AUS}")
    sys.exit(1)
print(f"{GRUEN}Alle Faelle wie erwartet.{AUS}")
