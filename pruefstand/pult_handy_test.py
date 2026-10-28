#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Geht vom Handy, was bisher nur am Gemeinde-PC ging? (A1, 28.10.2026)

    python pruefstand/pult_handy_test.py

Der Gemeinde-PC laeuft ohne Bildschirm. Bis hierher verlangten acht
Wege den Rechner selbst (nur_am_rechner): Aufnahmen auflisten, abrufen,
loeschen, ihre Frist setzen, das Testprotokoll schalten, auflisten und
abrufen, und der Knopf "Jetzt aus dem Netz aktualisieren". Jetzt gilt
allein das Pult-Passwort:

  * keines gesetzt  -> alles offen, auch aus dem Saal
  * eines gesetzt   -> aus dem Saal nur mit Anmeldung (401 ohne)
  * am Rechner selbst (Loopback) wird wie bisher nie gefragt

Und immer: Das Passwort des Wartungs-WLANs und der ntfy-Kanal gehen
NIE an den Browser. Das Pult sagt "gesetzt" oder "nicht gesetzt".
Geprueft gegen einen echten Server auf einer Wegwerfkopie, mit einer
nmcli-Attrappe, die das WLAN-Passwort nur auf ausdrueckliche Frage
herausgibt, und einer meldung.json mit einem erfundenen Kanal.
"""

import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pultschutz  # noqa: E402
from hilfe import (arbeitskopie, eigene_adresse, rufen,  # noqa: E402
                   server_starten, server_stoppen)

ROT, AUS = "\033[31m", "\033[0m"
FEHLER = 0
PORT = 8143
KANAL = "devarenu-pruefstand-kanal-q7x2"
WLAN_GEHEIM = "WartungsGeheim-4711"


def pruefe(was, erwartet, ist):
    global FEHLER
    if erwartet == ist:
        print(f"   ok    {was}")
    else:
        print(f"   {ROT}FEHL{AUS}  {was}: erwartet {erwartet!r}, ist {ist!r}")
        FEHLER += 1


def titel(t):
    print(f"\n\033[1m== {t}\033[0m")


# Die Wege, die bis zum 28.10.2026 nur am Rechner gingen, mit dem, was
# ein offenes Pult darauf antwortet. (weg, daten, status_offen)
# daten=None ist ein GET.
WEGE = [
    ("/api/aufnahmen", None, 200),
    ("/api/aufnahme/tage", {"tage": 30}, 200),
    ("/mitschnitt/Predigt_01_01_2026.mp3", None, 200),
    ("/api/aufnahme/loeschen", {"name": "Predigt_01_01_2026.mp3"}, 200),
    ("/api/pruefprotokolle", None, 200),
    ("/pruefprotokoll/pruefprotokoll_2026-01-01_10-00.jsonl", None, 200),
    ("/api/pruefprotokoll", {"an": False}, 200),
    ("/api/protokoll", {"an": False}, 200),
    ("/api/update/online", {}, 200),
]


def aufnahme_hinlegen(arbeit):
    """Eine Aufnahme und ein Testprotokoll, wie sie der Betrieb ablegt."""
    o = arbeit / "ergebnisse" / "predigten"
    o.mkdir(parents=True, exist_ok=True)
    (o / "Predigt_01_01_2026.mp3").write_bytes(b"ID3" + b"\0" * 64)
    p = arbeit / "ergebnisse" / "pruefprotokolle"
    p.mkdir(parents=True, exist_ok=True)
    (p / "pruefprotokoll_2026-01-01_10-00.jsonl").write_text(
        '{"satz": "Pruefstand"}\n', encoding="utf-8")
    marke = arbeit / "update" / "online-jetzt"
    if marke.exists():
        marke.unlink()


titel("0) Das Pult blendet nichts mehr nach dem Ort aus")
pult = (WURZEL / "web" / "pult.html").read_text(encoding="utf-8")
# Nur was auf dem Bildschirm steht: Kommentare duerfen die Geschichte
# erzaehlen.
pult_sichtbar = re.sub(r"<!--.*?-->", "", pult, flags=re.S)
pult_sichtbar = re.sub(r"(?m)^\s*//.*$", "", pult_sichtbar)
pruefe("der Online-Knopf haengt nicht an am_rechner", False,
       bool(re.search(r"onlinereihe\.hidden\s*=\s*!d\.am_rechner", pult)))
pruefe("das Testprotokoll auch nicht", False,
       bool(re.search(r"pruefprotokollreihe\.hidden\s*=\s*!d\.am_rechner",
                      pult)))
pruefe("kein Text sagt mehr \"nur am Gemeinde-PC\"", [],
       sorted(set(re.findall(r"(nur am Gemeinde-PC[^\"<]*|only on the church"
                             r" (?:PC|computer)[^\"<]*)", pult_sichtbar))))
quelle = (WURZEL / "server.py").read_text(encoding="utf-8")
pruefe("server.py fragt nirgends mehr nach nur_am_rechner", 0,
       len(re.findall(r"if not nur_am_rechner\(", quelle)))

saal = eigene_adresse()
if not saal:
    print(f"   {ROT}!{AUS}     keine Adresse ausser Loopback -- der Saal "
          f"laesst sich nicht nachstellen.")
    sys.exit(1)

ARBEIT = Path(tempfile.mkdtemp(prefix="devarenu-handy-",
                               dir=WURZEL / ".tmp"))
NMCLI_PROTOKOLL = ARBEIT / "nmcli-aufrufe.txt"
os.environ["DEVARENU_NMCLI"] = str(WURZEL / "pruefstand/attrappen/nmcli")
os.environ["NMCLI_PROTOKOLL"] = str(NMCLI_PROTOKOLL)
os.environ["NMCLI_GEHEIM"] = WLAN_GEHEIM
lauf = None
try:
    arbeitskopie(ARBEIT, {"pult_passwort": ""})
    (ARBEIT / "meldung.json").write_text(
        json.dumps({"ntfy": f"https://ntfy.sh/{KANAL}"}), encoding="utf-8")
    os.chmod(ARBEIT / "meldung.json", 0o600)
    (ARBEIT / "netz.json").write_text(json.dumps({
        "router": False,
        "wartungsfenster": {"an": True, "profil": "Gastzugang-Pruefstand",
                            "wochentag": "Do", "von": "18:00",
                            "bis": "22:00"}}), encoding="utf-8")
    lauf = server_starten(ARBEIT, PORT)
    if rufen(PORT, "/api/sprachen")[0] != 200:
        print(f"   {ROT}FEHL{AUS}  der Server kam nicht hoch")
        sys.exit(1)

    # ------------------------------------------------ ohne Passwort
    titel(f"1) Ohne Pult-Passwort, vom Handy ({saal})")
    for weg, daten, soll in WEGE:
        aufnahme_hinlegen(ARBEIT)
        pruefe(f"{'POST' if daten is not None else 'GET '} {weg}", soll,
               rufen(PORT, weg, daten, gastgeber=saal)[0])
    aufnahme_hinlegen(ARBEIT)
    rufen(PORT, "/api/update/online", {}, gastgeber=saal)
    pruefe("der Online-Knopf legt die Marke an", True,
           (ARBEIT / "update" / "online-jetzt").exists())
    status, roh = rufen(PORT, "/mitschnitt/Predigt_01_01_2026.mp3",
                        gastgeber=saal)
    pruefe("die Aufnahme kommt als Datei", (200, True),
           (status, roh.startswith("ID3")))

    # ------------------------------------------------- mit Passwort
    titel("2) Mit Pult-Passwort")
    pruefe("Passwort setzen", 200,
           rufen(PORT, "/api/pult-passwort", {"passwort": "Saal2026"})[0])
    z = json.loads((ARBEIT / "zustand.json").read_text(encoding="utf-8"))
    ausweis = pultschutz.ausweis(z["pult_passwort"])
    for weg, daten, soll in WEGE:
        aufnahme_hinlegen(ARBEIT)
        pruefe(f"ohne Anmeldung: {weg} -> 401", 401,
               rufen(PORT, weg, daten, gastgeber=saal)[0])
    pruefe("ohne Anmeldung keine Marke", False,
           (ARBEIT / "update" / "online-jetzt").exists())
    for weg, daten, soll in WEGE:
        aufnahme_hinlegen(ARBEIT)
        pruefe(f"angemeldet: {weg}", soll,
               rufen(PORT, weg, daten, keks=ausweis, gastgeber=saal)[0])
    aufnahme_hinlegen(ARBEIT)
    pruefe("am Rechner selbst ohne Anmeldung, wie bisher", 200,
           rufen(PORT, "/api/aufnahmen")[0])

    # Allein das Passwort schuetzt -- dann darf es auch nicht von selbst
    # verschwinden. Bis zum 28.10.2026 schrieb jeder Schalter den
    # Zustand vom Serverstart zurueck, samt pult_passwort "".
    titel("2b) Das Passwort bleibt, was immer am Pult geschaltet wird")
    for weg, daten in (("/api/protokoll", {"an": False}),
                       ("/api/thema-im-prompt", {"an": True}),
                       ("/api/versuchssprachen", {"an": False}),
                       ("/api/wlan", {"ssid": "Saal", "passwort": "x1y2z3"})):
        rufen(PORT, weg, daten, keks=ausweis, gastgeber=saal)
        jetzt = json.loads((ARBEIT / "zustand.json").read_text(
            encoding="utf-8")).get("pult_passwort")
        pruefe(f"nach {weg} steht der Hash noch da", z["pult_passwort"], jetzt)
    pruefe("und das Handy ohne Anmeldung bleibt draussen", 401,
           rufen(PORT, "/api/aufnahmen", gastgeber=saal)[0])
    # Umgekehrt: am Rechner geloescht (werkzeuge/pult_passwort.py),
    # darf ein Schalter es nicht zurueckbringen.
    pultschutz.zuruecksetzen(ARBEIT / "zustand.json")
    rufen(PORT, "/api/thema-im-prompt", {"an": False})
    pruefe("am Rechner geloescht bleibt geloescht", "",
           json.loads((ARBEIT / "zustand.json").read_text(
               encoding="utf-8")).get("pult_passwort"))
    pruefe("Passwort wieder setzen", 200,
           rufen(PORT, "/api/pult-passwort", {"passwort": "Saal2026"})[0])
    z = json.loads((ARBEIT / "zustand.json").read_text(encoding="utf-8"))
    ausweis = pultschutz.ausweis(z["pult_passwort"])

    # ---------------------------------------- Geheimnisse bleiben
    titel("3) Wartungs-WLAN und ntfy-Kanal: nur \"gesetzt\"")
    status, roh = rufen(PORT, "/api/betriebslage", keks=ausweis,
                        gastgeber=saal)
    lage = json.loads(roh) if status == 200 else {}
    pruefe("die Einrichtung kennt den Meldekanal als gesetzt", True,
           (lage.get("meldekanal") or {}).get("gesetzt"))
    pruefe("das Wartungs-WLAN hat ein Passwort", "gesetzt",
           (lage.get("wartungs_wlan") or {}).get("passwort"))
    pruefe("es ist eingetragen", True,
           (lage.get("wartungs_wlan") or {}).get("eingetragen"))
    # Der Profilname gehoert wie das Thema zu dem, was _geheime_werte
    # aus jeder Anzeige nimmt.
    pruefe("sein Name steht nicht in der Antwort", False,
           "Gastzugang-Pruefstand" in roh)

    # Zusammengesetzt und nicht woertlich: oeffentlich_pruefen.sh sucht
    # nach ntfy-Adressen im Klartext, und zu Recht.
    NEU = f"https://ntfy.sh/{KANAL}-neu"
    status, roh = rufen(PORT, "/api/meldekanal", {"ntfy": NEU},
                        keks=ausweis, gastgeber=saal)
    pruefe("den Kanal aendern geht vom Handy", 200, status)
    pruefe("die Antwort nennt ihn nicht", False, KANAL in roh)
    pruefe("er steht in meldung.json", NEU,
           json.loads((ARBEIT / "meldung.json").read_text())["ntfy"])
    pruefe("die Datei bleibt 0600", "600",
           oct((ARBEIT / "meldung.json").stat().st_mode)[-3:])
    pruefe("ohne Anmeldung nicht", 401,
           rufen(PORT, "/api/meldekanal", {"ntfy": "https://ntfy.sh/x-y-z"},
                 gastgeber=saal)[0])
    for falsch in ("ftp://ntfy.sh/abc", "https://ntfy.sh/a b",
                   "https://ntfy.sh/abc\"; rm -rf /", "https://ntfy.sh/",
                   "https://ntfy.sh/abc?x=$(id)"):
        pruefe(f"abgelehnt: {falsch!r}", 400,
               rufen(PORT, "/api/meldekanal", {"ntfy": falsch},
                     keks=ausweis, gastgeber=saal)[0])
    # Zurueck auf den ersten Kanal, damit die Suche unten ihn findet,
    # falls er irgendwo durchsickert.
    (ARBEIT / "meldung.json").write_text(
        json.dumps({"ntfy": f"https://ntfy.sh/{KANAL}"}), encoding="utf-8")

    print("\n   -- alles, was ein Browser abrufen kann --")
    gets = sorted(set(re.findall(r'@app\.get\("([^"{]+)"\)', quelle)))
    gets += ["/fehlerbericht.txt?schnell=1", "/qr?druck=1"]
    durchsucht = 0
    for weg in gets:
        for keks in (None, ausweis):
            status, roh = rufen(PORT, weg, keks=keks, gastgeber=saal)
            durchsucht += 1
            for geheim, name in ((KANAL, "ntfy-Kanal"),
                                 (WLAN_GEHEIM, "WLAN-Passwort")):
                if geheim in roh:
                    pruefe(f"{name} in {weg}", False, True)
    pruefe(f"{durchsucht} Antworten durchsucht, kein Geheimnis darin",
           True, durchsucht > 20)
    pruefe("das Pult gibt keine Felder mit dem Kanal oder WLAN-Passwort",
           False, KANAL in rufen(PORT, "/pult", keks=ausweis,
                                 gastgeber=saal)[1])
    aufrufe = (NMCLI_PROTOKOLL.read_text(encoding="utf-8")
               if NMCLI_PROTOKOLL.exists() else "")
    pruefe("nmcli wurde gefragt", True, "key-mgmt" in aufrufe)
    pruefe("aber nie nach dem Passwort selbst", False,
           bool(re.search(r"(^| )(-s|--show-secrets)( |$)|\.psk", aufrufe,
                          re.M)))
finally:
    server_stoppen(lauf)
    shutil.rmtree(ARBEIT, ignore_errors=True)

print()
if FEHLER:
    print(f"{FEHLER} FEHLER")
    sys.exit(1)
print("Alles in Ordnung.")
