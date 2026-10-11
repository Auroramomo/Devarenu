#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dienst, letztes Wartungsfenster und Wecker, wie das Pult sie liest (0.5.1).

    .venv/bin/python pruefstand/betriebslage_test.py

Alles gegen nachgebaute Systemausgaben: systemctl und journalctl aus
pruefstand/attrappen, dazu eine Ablage, eine cgroup-Datei und eine
Weckerdatei im Wegwerfordner. Der Rechner, auf dem das laeuft, wird
nicht gefragt -- auf dem Entwicklungsrechner gibt es keinen Dienst und
keinen Wecker, und genau die Faelle, auf die es ankommt, liessen sich
dort gar nicht herstellen.

  A1  eingerichtet / eingeschaltet / aktiv / Neustarts, Dienst oder
      Sitzung, das Startprotokoll ohne Geheimnisse, die Befunde im
      Systemcheck ("Autostart ist aus", "startet immer wieder neu")
  A2  das letzte Fenster: aufgewacht oder nicht, Internet, Ziel,
      Ergebnis, Grund vollstaendig -- und "unbekannt", wo ohne Root
      nichts zu sehen ist
  A3  der Wecker: gestellt, keiner, nicht lesbar
"""
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER))
from hilfe import WURZEL, wegwerfordner  # noqa: E402

sys.path.insert(0, str(WURZEL))
import betriebslage as bl  # noqa: E402
import systemcheck  # noqa: E402
import wartungsfenster as wf  # noqa: E402

ROT, GRUEN, AUS = "\033[31m", "\033[32m", "\033[0m"
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


ORDNER = Path(wegwerfordner("devarenu-betriebslage-"))
SHOW = ORDNER / "show"
JOURNAL = ORDNER / "journal"
ABLAGE = ORDNER / "ablage"
for d in (SHOW, JOURNAL, ABLAGE):
    d.mkdir(parents=True, exist_ok=True)
os.environ["PATH"] = f"{HIER / 'attrappen'}:{os.environ['PATH']}"
os.environ["STUB_SHOW"] = str(SHOW)


def show(unit, **felder):
    (SHOW / unit).write_text(
        "".join(f"{k}={v}\n" for k, v in felder.items()), encoding="utf-8")


# Geheimes, wie es auf einem Gemeinderechner stuende. Zur Laufzeit
# zusammengesetzt: oeffentlich_pruefen.sh soll im Repo keine Adresse
# finden, die wie ein echter Kanal oder eine echte Mailadresse aussieht.
PASSWORT = "saalnetz-kennwort-4711"
THEMA = "devarenu-" + "qwertzuiopasdfgh"
KANAL = "https://" + "ntfy.example/" + THEMA
MAIL = "kuester" + chr(64) + "gemeinde.example"
BASIS = ORDNER / "devarenu"
BASIS.mkdir()
(BASIS / "zustand.json").write_text(json.dumps(
    {"wlan": {"ssid": "Gemeindesaal", "passwort": PASSWORT},
     "kontakt": "Buero Gemeindehaus"}), encoding="utf-8")
(BASIS / "meldung.json").write_text(json.dumps({"ntfy": KANAL}),
                                    encoding="utf-8")


# =================================================================== A1
titel("A1 Der Dienst")
show("devarenu", LoadState="loaded", UnitFileState="enabled",
     ActiveState="active", SubState="running", NRestarts="0",
     MainPID="4242", ActiveEnterTimestamp="Thu 2026-10-08 18:00:05 CEST")
d = bl.dienst()
pruefe("eingerichtet, eingeschaltet, aktiv",
       (True, "enabled", "active", 0, 4242),
       (d["vorhanden"], d["eingeschaltet"], d["aktiv"], d["neustarts"], d["pid"]))
pruefe("Autostart an", True, bl.autostart_an(d))

show("devarenu", LoadState="loaded", UnitFileState="disabled",
     ActiveState="inactive", SubState="dead", NRestarts="0", MainPID="0")
d = bl.dienst()
pruefe("ausgeschaltet: Autostart aus", False, bl.autostart_an(d))

show("devarenu", LoadState="not-found", UnitFileState="",
     ActiveState="inactive", SubState="dead", NRestarts="0", MainPID="0")
pruefe("nicht eingerichtet", False, bl.dienst()["vorhanden"])

alt_pfad = os.environ["PATH"]
os.environ["PATH"] = str(ORDNER / "leer")
pruefe("ohne systemctl: keine Angabe (die Zeile entfaellt)", None, bl.dienst())
os.environ["PATH"] = alt_pfad

cg = ORDNER / "cgroup"
cg.write_text("0::/system.slice/devarenu.service\n")
pruefe("Prozess im Dienst", "dienst", bl.laufart(cg))
cg.write_text("0::/user.slice/user-1000.slice/user@1000.service/app.slice/"
              "app-gnome-Devarenu-1234.scope\n")
pruefe("Prozess vom Schreibtischsymbol", "sitzung", bl.laufart(cg))
pruefe("cgroup nicht lesbar: unbekannt", "unbekannt",
       bl.laufart(ORDNER / "gibtsnicht"))

titel("A1 Das Startprotokoll -- ohne Geheimnisse")
(BASIS / "start-protokoll.txt").write_text("\n".join(
    [f"2026-10-0{i} 08:0{i}:00 | Dienst active/running | laeuft mit Ton "
     f"-- nichts gestartet" for i in range(1, 10)]
    + ["2026-10-11 08:00:00 | Dienst inactive/dead | kein laufender Dienst",
       f"2026-10-11 08:01:00 | passwort={PASSWORT} {KANAL} {MAIL}",
       # Zur Laufzeit zusammengesetzt, aus demselben Grund wie oben.
       "2026-10-11 08:02:00 | Pfad /" + "home/vorname/Devarenu"]) + "\n",
    encoding="utf-8")
zeilen = bl.startprotokoll(BASIS)
pruefe("die letzten zehn", 10, len(zeilen))
pruefe("juengste zuletzt", True, "/Devarenu" in zeilen[-1])
alles = "\n".join(zeilen)
for was, wert in (("WLAN-Passwort", PASSWORT), ("ntfy-Thema", THEMA),
                  ("Mailadresse", MAIL), ("Name im Heimatordner", "vorname")):
    pruefe(f"kein {was}", False, wert in alles)
pruefe("ohne Datei: leer", [], bl.startprotokoll(ORDNER))

titel("A1 Der Systemcheck")
echt_dienst, echt_art = bl.dienst, bl.laufart


def befunde_mit(dienst, art="dienst"):
    bl.dienst = lambda name=bl.NAME: dienst
    bl.laufart = lambda cgroup=None: art
    b = []
    systemcheck._devarenu(b)
    bl.dienst, bl.laufart = echt_dienst, echt_art
    return b


b = befunde_mit({"vorhanden": True, "eingeschaltet": "disabled",
                 "aktiv": "active", "neustarts": 0})
pruefe("Autostart aus: ein Befund, FEHLT",
       [("dienst_devarenu", systemcheck.FEHLT)],
       [(x.kennung, x.schwere) for x in b])
pruefe("er sagt \"Autostart ist aus\"", True, b[0].was.startswith("Autostart ist aus"))
pruefe("und schaltet nichts ein, er nennt nur den Befehl",
       "sudo systemctl enable devarenu", b[0].tun)
b = befunde_mit({"vorhanden": True, "eingeschaltet": "enabled",
                 "aktiv": "active", "neustarts": 7})
pruefe("startet immer wieder neu: Befund", ["dienst_neustarts"],
       [x.kennung for x in b])
pruefe("mit der Zahl", True, "7-mal" in b[0].was)
b = befunde_mit({"vorhanden": True, "eingeschaltet": "enabled",
                 "aktiv": "active", "neustarts": 2})
pruefe("zwei Neustarts: noch kein Befund", [], b)
b = befunde_mit({"vorhanden": False})
pruefe("nicht eingerichtet: bash dienst.sh", "bash dienst.sh", b[0].tun)
b = befunde_mit({"vorhanden": True, "eingeschaltet": "enabled",
                 "aktiv": "inactive", "neustarts": 0}, art="sitzung")
pruefe("eingeschaltet, aber angehalten, und wir laufen in der Sitzung",
       True, "Schreibtischsymbol" in b[0].was)
pruefe("die neuen Befunde gehoeren nicht in die Wartung (Pult sieht sie)",
       False, systemcheck.Befund("dienst_neustarts", "hinweis", "").wartung)


# =================================================================== A2
titel("A2 Das letzte Wartungsfenster")
FENSTER = dict(wf.VORGABE, an=True, profil="Gemeindesaal",
               wochentag="Do", von="18:00", bis="22:00", autoupdate=True)
wf.einstellung = lambda netz=None: dict(FENSTER)
JETZT = datetime(2026, 10, 11, 9, 0)            # Sonntag
BEGINN = datetime(2026, 10, 8, 18, 0)           # Donnerstag davor
KENNUNG = "2026-10-08T18:00"
os.environ["STUB_JOURNAL"] = str(JOURNAL)
show("devarenu-fenster.timer", LastTriggerUSec="")


def boots(*paare):
    (JOURNAL / "boots.json").write_text(json.dumps(
        [{"index": -i, "boot_id": "x", "first_entry": int(a.timestamp() * 1e6),
          "last_entry": int(b.timestamp() * 1e6)}
         for i, (a, b) in enumerate(paare)]), encoding="utf-8")


def protokoll(text):
    (JOURNAL / "fenster.txt").write_text(text, encoding="utf-8")


GESCHEITERT = f"""
== Autoupdate
   ok   Gemeindesaal verbunden

   == Vorher nachsehen
      ok   keine lokalen Aenderungen

   == Aenderungen holen
      FEHLT git fetch fehlgeschlagen.
      Entweder kein Netz -- oder ein Tag zeigt drueben woanders hin
      als hier. Das wird ABSICHTLICH nicht ueberschrieben: ein
      umgebogenes Tag darf kein geprueuftes ersetzen. Nachsehen:
        git fetch --tags --dry-run
   !    Autoupdate ist gescheitert (Rueckgabe 1).
   !    Die Rueckmeldung ging nicht hinaus, sie liegt vorgemerkt.
   !    Der Rechner bleibt bis Fensterende an, damit jemand nachsehen kann.
        /var/lib/devarenu/updates/autoupdate-{KENNUNG}.log
        Kanal {KANAL} passwort={PASSWORT}
"""
boots((datetime(2026, 9, 1), datetime(2026, 9, 2)),
      (datetime(2026, 10, 8, 17, 55), datetime(2026, 10, 8, 22, 1)))
protokoll(GESCHEITERT)
f = bl.fenster(JETZT, ABLAGE, journal=True, geheim=bl._geheime_werte(BASIS))
pruefe("zuletzt begonnen", "2026-10-08 18:00", f["beginn"])
pruefe("aufgewacht, laut Systemprotokoll", ("ja", "journal"), (f["wach"], f["beleg"]))
pruefe("WLAN verbunden, Internet nein", ("ja", "nein"), (f["wlan"], f["internet"]))
pruefe("Ergebnis gescheitert", "gescheitert", f["ergebnis"])
pruefe("der Grund beginnt mit dem Fehler", True,
       f["grund"].startswith("git fetch fehlgeschlagen."))
pruefe("und ist VOLLSTAENDIG, mit Zeilenumbruch", True,
       "git fetch --tags --dry-run" in f["grund"] and "\n" in f["grund"]
       and "Fensterende an" in f["grund"])
pruefe("kein ntfy-Thema im Grund", False, THEMA in f["grund"])
pruefe("kein Passwort im Grund", False, PASSWORT in f["grund"])

boots((datetime(2026, 9, 1), datetime(2026, 9, 2)),
      (datetime(2026, 10, 10, 8, 0), datetime(2026, 10, 11, 9, 0)))
protokoll("")
f = bl.fenster(JETZT, ABLAGE, journal=True)
pruefe("kein Start in der Fensterzeit, Journal reicht weiter zurueck: "
       "nicht aufgewacht", "nein", f["wach"])

boots((datetime(2026, 10, 10, 8, 0), datetime(2026, 10, 11, 9, 0)))
f = bl.fenster(JETZT, ABLAGE, journal=True)
pruefe("Journal beginnt erst nach dem Fenster: unbekannt, nicht geraten",
       "unbekannt", f["wach"])

f = bl.fenster(JETZT, ABLAGE, journal=False)
pruefe("Journal nicht lesbar, keine Marke: alles unbekannt",
       ("unbekannt", "unbekannt", "unbekannt", "unbekannt"),
       (f["wach"], f["versucht"], f["internet"], f["ergebnis"]))
pruefe("und es sagt, warum", False, f["journal"])

(ABLAGE / f"autoupdate-{KENNUNG}").write_text("")
log = ABLAGE / f"autoupdate-{KENNUNG}.log"
log.write_text("nur fuer root")
ende_lauf = datetime(2026, 10, 8, 18, 9).timestamp()
os.utime(log, (ende_lauf, ende_lauf))
f = bl.fenster(JETZT, ABLAGE, journal=False)
pruefe("mit Marke, ohne Journal: wach und versucht, Ergebnis unbekannt",
       ("ja", "marke", "ja", "unbekannt"),
       (f["wach"], f["beleg"], f["versucht"], f["ergebnis"]))
pruefe("und wann der Lauf endete", "2026-10-08 18:09", f["ende_lauf"])
for p in ABLAGE.iterdir():
    p.unlink()

show("devarenu-fenster.timer",
     LastTriggerUSec="Thu 2026-10-08 18:05:01 CEST")
f = bl.fenster(JETZT, ABLAGE, journal=False)
pruefe("Fenster-Timer lief in der Fensterzeit: wach", ("ja", "timer"),
       (f["wach"], f["beleg"]))
show("devarenu-fenster.timer", LastTriggerUSec="")

protokoll("""== Autoupdate
   ok   Gemeindesaal ist schon verbunden
      ok   Tags von origin geholt
      ok   0.5.0 -> 0.5.1, das ist neuer
      ok   Signatur von v0.5.1 ist gueltig
   ok   0.5.0 -> 0.5.1 in 184s
""")
boots((datetime(2026, 10, 8, 17, 55), datetime(2026, 10, 8, 22, 1)))
f = bl.fenster(JETZT, ABLAGE, journal=True)
pruefe("gelungen: Internet, Ziel, eingespielt",
       ("ja", "0.5.1", "eingespielt", ""),
       (f["internet"], f["ziel"], f["ergebnis"], f["grund"]))

protokoll("""== Autoupdate
      ok   Tags von origin geholt
      ok   Hier laeuft 0.5.1. Es gibt kein neueres Tag.
   ok   kein neueres Tag, Fassung bleibt 0.5.1
""")
f = bl.fenster(JETZT, ABLAGE, journal=True)
pruefe("nichts zu tun", ("ja", "nichts_zu_tun"), (f["internet"], f["ergebnis"]))

protokoll("   ok   Gemeindesaal verbunden\n"
          "        Es wird uebersetzt -- das Autoupdate wartet.\n")
f = bl.fenster(JETZT, ABLAGE, journal=True)
pruefe("aufgewacht, aber kein Update versucht", ("kein_versuch", "nein"),
       (f["ergebnis"], f["versucht"]))

FENSTER["an"] = False
pruefe("Fenster aus: nur das", {"an": False}, bl.fenster(JETZT, ABLAGE))
FENSTER["an"] = True


# =================================================================== A3
titel("A3 Der Wecker")
weckdatei = ORDNER / "wakealarm"
geplant = wf.wecker_zeit(JETZT)
weckdatei.write_text(f"{int(geplant.timestamp())}\n")
w = bl.wecker(weckdatei, JETZT)
pruefe("gestellt und wie geplant", (True, "2026-10-15 17:55", "2026-10-15 17:55"),
       (w["lesbar"], w["gestellt"], w["geplant"]))
weckdatei.write_text("\n")
w = bl.wecker(weckdatei, JETZT)
pruefe("leere Datei: keiner gestellt", (True, ""), (w["lesbar"], w["gestellt"]))
w = bl.wecker(ORDNER / "kein_rtc", JETZT)
pruefe("nicht lesbar: unbekannt, nicht geraten", (False, ""),
       (w["lesbar"], w["gestellt"]))
weckdatei.write_text(f"{int(datetime(2026, 10, 8, 17, 55).timestamp())}\n")
pruefe("ein Wecker in der Vergangenheit", True,
       bl.wecker(weckdatei, JETZT)["vorbei"])


# ============================================================== Frist
titel("Kurze Fristen, keine Ausnahme")
langsam = ORDNER / "langsam"
langsam.mkdir()
(langsam / "systemctl").write_text("#!/bin/sh\nsleep 30\n")
(langsam / "systemctl").chmod(0o755)
os.environ["PATH"] = f"{langsam}:{alt_pfad}"
t0 = time.monotonic()
pruefe("ein haengendes systemctl: keine Angabe", None, bl.dienst())
pruefe("nach hoechstens der Frist", True, time.monotonic() - t0 < bl.FRIST + 1.5)
os.environ["PATH"] = alt_pfad
lage = bl.lage(BASIS)
pruefe("lage() liefert alle Teile", sorted(
    ["dienst", "laufart", "startprotokoll", "fenster", "wecker"]),
    sorted(lage))

print()
if FEHLER:
    print(f"{ROT}{FEHLER} Fehler.{AUS}")
    sys.exit(1)
print(f"{GRUEN}Alle Faelle wie erwartet.{AUS}")
