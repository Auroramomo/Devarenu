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

print(f"\n   Bericht: {len(bericht)} Zeichen, "
      f"{len(bericht.splitlines())} Zeilen")
print()
if fehler:
    print(f"\033[31m{fehler} Fehler.\033[0m")
else:
    print("\033[32mAlle Faelle wie erwartet.\033[0m")
sys.exit(fehler)
