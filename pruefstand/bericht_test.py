#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Steht im Fehlerbericht wirklich nichts drin, was niemanden angeht?

    python pruefstand/bericht_test.py

Geprueft wird mit ERFUNDENEN Daten: ein Name, eine Diagnose, ein
WLAN-Passwort, eine Zuschrift aus dem Saal. Keines davon existiert.
Taucht eines im Bericht auf, ist die Erlaubnisliste undicht.
"""
import io
import json
import re
import sys
import tempfile
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))

# Erfundene Daten. Keine echten Personen, keine echten Zugangsdaten.
GEHEIM = {
    "Name aus dem Manuskript": "Hildegard Vossberg",
    "Diagnose aus der Predigt": "Bauchspeicheldruesenkrebs",
    "WLAN-Name": "Gemeindehaus-Gast",
    "WLAN-Passwort": "Sonnenblume1874",
    "Zuschrift aus dem Saal": "Der Ton ist zu leise, sagt Frau Vossberg",
    "Mitschrift": "Wir beten heute fuer Hildegard Vossberg",
    # Kein Passwort, aber auch nichts, was in eine Mail gehoert.
    "Hash des Pult-Passworts":
        "pbkdf2_sha256$240000$0123456789abcdef$deadbeefcafebabe",
}

fehler = 0


def pruefe(was, bedingung):
    global fehler
    if bedingung:
        print(f"   ok    {was}")
    else:
        print(f"   FEHL  {was}")
        fehler += 1


print("\n\033[1m== 1) schutz() haelt den Text zurueck\033[0m")
import server
server.PROTOKOLL_MITSCHRIFT = False
satz = GEHEIM["Mitschrift"]
aus = server.schutz(satz)
pruefe("aus: kein Wort aus dem Satz", not any(w in aus for w in satz.split()))
pruefe("aus: die Laenge steht da", "Z." in aus)
server.PROTOKOLL_MITSCHRIFT = True
pruefe("an: der Satz steht da", satz[:20] in server.schutz(satz))
server.PROTOKOLL_MITSCHRIFT = False

print("\n\033[1m== 2) Der Riegel erkennt Segmentzeilen\033[0m")
import fehlerbericht
proben = [
    ("[  42] 3.4s Ton, STT 0.31s, gesamt 1.02s | " + GEHEIM["Mitschrift"], True),
    ("[   .] 3.4s Ton, sammle | " + GEHEIM["Mitschrift"], True),
    ("[   !] Notbremse nach 4s | " + GEHEIM["Mitschrift"], True),
    ("Nachricht aus dem Saal (de): " + GEHEIM["Zuschrift aus dem Saal"], True),
    ("Manuskript: predigt.docx, 800 Woerter, 2 Namen (" 
     + GEHEIM["Name aus dem Manuskript"] + "), Stellen: Joh 3,16", True),
    ("Fassung        0.2.14", False),
    ("System         CachyOS", False),
]
for zeile, soll in proben:
    ist = fehlerbericht.verdaechtig(zeile)
    pruefe(f"{'faengt' if soll else 'laesst durch'}: {zeile[:34]}...",
           ist == soll)

print("\n\033[1m== 3) Der fertige Bericht\033[0m")
# zustand.json mit erfundenen Zugangsdaten unterschieben -- die echte
# wird NICHT angefasst.
ord_ = Path(tempfile.mkdtemp())
zdatei = ord_ / "zustand.json"
zdatei.write_text(json.dumps({
    "fassung": 3,
    "wlan": {"ssid": GEHEIM["WLAN-Name"],
             "passwort": GEHEIM["WLAN-Passwort"]},
    "quelle": "de", "ziele": ["en"],
}), encoding="utf-8")
import zustand as zustandsdatei
zustandsdatei.DATEI = zdatei

# pruefen.sh ueberspringen -- es dauert Minuten und bringt nur eine
# Zahlenzeile.
fehlerbericht._pruefen_zusammen = lambda: ["(im Test uebersprungen)"]
# Ein Journal voller Geheimnisse unterschieben.
fehlerbericht._journal = lambda: [
    "[devarenu]",
    "  Sep 24 10:00 devarenu[1]: [  42] 3.4s Ton, STT 0.3s, gesamt 1.0s | "
    + GEHEIM["Mitschrift"],
    "  Sep 24 10:01 devarenu[1]: Nachricht aus dem Saal (de): "
    + GEHEIM["Zuschrift aus dem Saal"],
]
bericht = fehlerbericht.bauen()
(ord_ / "bericht.txt").write_text(bericht, encoding="utf-8")

for was, wert in GEHEIM.items():
    drin = wert.lower() in bericht.lower()
    pruefe(f"{was} kommt NICHT vor", not drin)
    if drin:
        for z in bericht.split("\n"):
            if wert.lower() in z.lower():
                print(f"         gefunden in: {z[:100]}")

pruefe("der Riegel hat gemeldet, dass er etwas entfernt hat",
       "entfernt" in bericht)
pruefe("technische Angaben sind trotzdem da", "Fassung" in bericht)

print("\n\033[1m== 4) Der juengere von zwei Update-Staenden\033[0m")
# Am Gemeinderechner stand im Pult unter Einrichtung monatelang
# "Update 0.3.1 ist fehlgeschlagen", obwohl seitdem mehrere Fassungen
# ueber das Netz eingespielt worden waren: das Pult las nur
# stand.json (der Stick-Kern), nie stand-online.json. Die Auswahl gab
# es schon im Fehlerbericht -- sie stand nur an der falschen Stelle
# allein. Seit 0.3.8 nehmen beide dieselbe Funktion.
import json as _json
import tempfile as _tempfile

with _tempfile.TemporaryDirectory() as _t:
    _o = Path(_t)
    pruefe("gar kein Stand ist ein leerer Stand",
           fehlerbericht.juengerer_stand(_o) == {})
    (_o / "stand.json").write_text(_json.dumps(
        {"lage": "fehlgeschlagen", "version": "0.3.1",
         "zeit": "2026-05-01 10:00:00"}), encoding="utf-8")
    pruefe("nur der Stick: der Stick gilt",
           fehlerbericht.juengerer_stand(_o).get("version") == "0.3.1")
    (_o / "stand-online.json").write_text(_json.dumps(
        {"lage": "eingespielt", "version": "0.3.7",
         "zeit": "2026-09-27 12:00:00"}), encoding="utf-8")
    pruefe("der juengere Netzstand verdraengt den alten Stick-Versuch",
           fehlerbericht.juengerer_stand(_o).get("version") == "0.3.7")
    # Und andersherum -- ein Stick-Update nach dem Netzweg gilt auch.
    (_o / "stand.json").write_text(_json.dumps(
        {"lage": "eingespielt", "version": "0.3.9",
         "zeit": "2026-10-04 09:00:00"}), encoding="utf-8")
    pruefe("und umgekehrt genauso",
           fehlerbericht.juengerer_stand(_o).get("version") == "0.3.9")
    # Ohne Zeitstempel ist ein Stand nicht juenger, sondern aelter.
    (_o / "stand-online.json").write_text(_json.dumps(
        {"lage": "eingespielt", "version": "9.9.9"}), encoding="utf-8")
    pruefe("ein Stand ohne Zeit verdraengt keinen mit",
           fehlerbericht.juengerer_stand(_o).get("version") == "0.3.9")
    # Kaputte Datei: der andere Stand bleibt brauchbar.
    (_o / "stand-online.json").write_text("{kaputt", encoding="utf-8")
    pruefe("eine unlesbare Datei macht den anderen nicht ungueltig",
           fehlerbericht.juengerer_stand(_o).get("version") == "0.3.9")

print(f"\n   Bericht: {len(bericht)} Zeichen, "
      f"{len(bericht.splitlines())} Zeilen")
print()
if fehler:
    print(f"\033[31m{fehler} Fehler.\033[0m")
else:
    print("\033[32mAlle Faelle wie erwartet.\033[0m")
sys.exit(fehler)
