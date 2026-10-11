#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Der Start, wie er auf Aurora aussah -- Nachtrag zu 0.5.1.

    .venv/bin/python pruefstand/systemcheck_start_test.py

Gemeldet aus dem Start von start.sh, zwei Laeufe hintereinander:

    Systemcheck fehlgeschlagen (too many values to unpack (expected 3)).
    Ohne Stimme, nur Text: de
    Schwelle: aus
      Zustand   zustand.json
                Auna Mic CM900: ..., de -> en, ru, fa, de, Schwelle mitlaufend

Mit einer zustand.json wie dort: Quelle de, Ziele en, ru, fa, de (de
blieb nach einem Wechsel auf ru und zurueck angehakt), Schwelle aus,
ein Mikrofon, das es nicht gibt, und kein devarenu-Dienst (eine
systemctl-Attrappe meldet ihn als nicht eingerichtet).

  1) Der echte Server, Kopie, --nur-text: der Systemcheck laeuft durch
     und meldet den fehlenden Dienst; die Zustandszeile nennt de nicht
     als Ziel und die Schwelle so, wie sie laeuft.
  2) "Ohne Stimme, nur Text" laesst die Quelle aus.
  3) Wird de nach dem Wechsel auf ru zum Ziel, laedt der Server die
     Stimme thorsten nach -- vorher blieb de stumm.

Warum das vorher keiner fand: kein Pruefstand rief systemcheck.pruefen()
im Ganzen auf. Die Teile wurden einzeln geprueft (_devarenu in
betriebslage_test.py), und die Pruefstaende, die den Server starten,
schicken seine Ausgabe nach /dev/null -- dort stand der Fehler.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hilfe import (WURZEL, arbeitskopie, rufen, server_stoppen,  # noqa: E402
                   wegwerfordner)

sys.path.insert(0, str(WURZEL))
import config  # noqa: E402
import zustand as zustandsdatei  # noqa: E402

ROT, GRUEN, AUS = "\033[31m", "\033[32m", "\033[0m"
FEHLER = 0
PORT = 8195


def pruefe(was, erwartet, ist):
    global FEHLER
    if erwartet == ist:
        print(f"   ok    {was}")
    else:
        print(f"   {ROT}FEHL{AUS}  {was}: erwartet {erwartet!r}, ist {ist!r}")
        FEHLER += 1


def titel(t):
    print(f"\n\033[1m== {t}\033[0m")


ZUSTAND = {
    "fassung": zustandsdatei.FASSUNG,
    "quelle": "de",
    "ziele": ["en", "ru", "fa", "de"],
    "geraet": None,
    "geraet_name": "Pruefstand-Mikrofon: USB Audio (hw:9,0)",
    "schwelle": {"wert": None, "gemessen": None,
                 "modus": "aus", "grundmodus": "aus"},
    "wlan": {"ssid": "Pruefstand", "passwort": ""},
}

# =====================================================================
titel("1) Der echte Server mit dieser zustand.json")
ordner = arbeitskopie(wegwerfordner("devarenu-scstart-"), ZUSTAND)
# Kein Dienst: nur systemctl wird ersetzt, alles andere bleibt echt.
stubs = ordner / "stubs"
stubs.mkdir()
(stubs / "systemctl").symlink_to(WURZEL / "pruefstand/attrappen/systemctl")
show = ordner / "show"
show.mkdir()
for unit in ("devarenu", "devarenu.service"):
    (show / unit).write_text("LoadState=not-found\nUnitFileState=\n"
                             "ActiveState=inactive\nSubState=dead\n"
                             "NRestarts=\nMainPID=0\n"
                             "ActiveEnterTimestamp=\n", encoding="utf-8")
umgebung = dict(os.environ, PATH=f"{stubs}:{os.environ.get('PATH', '')}",
                STUB_SHOW=str(show), PYTHONUNBUFFERED="1")
ausgabe = ordner / "ausgabe.txt"
with open(ausgabe, "w", encoding="utf-8") as aus:
    p = subprocess.Popen(
        [str(ordner / ".venv/bin/python"), "server.py",
         "--port", str(PORT), "--nur-text"],
        cwd=str(ordner), stdout=aus, stderr=subprocess.STDOUT, env=umgebung)
try:
    bereit = False
    for _ in range(90):
        if rufen(PORT, "/api/sprachen")[0] == 200:
            bereit = True
            break
        time.sleep(1)
    pruefe("der Server antwortet", True, bereit)
    text = ausgabe.read_text(encoding="utf-8", errors="replace")
    pruefe("kein \"Systemcheck fehlgeschlagen\"", False,
           "Systemcheck fehlgeschlagen" in text)
    pruefe("keine Dienstabfrage gescheitert", False,
           "Systemcheck: Dienstabfrage" in text)
    code, roh = rufen(PORT, "/api/zustand")
    d = json.loads(roh) if code == 200 else {}
    kennungen = [b.get("kennung") for b in d.get("befunde") or []]
    pruefe("der Systemcheck meldet: devarenu nicht eingerichtet",
           True, "dienst_devarenu" in kennungen)
    zeile = next((z.strip() for z in text.splitlines()
                  if "Pruefstand-Mikrofon" in z and " -> " in z), "")
    pruefe("Zustandszeile: de -> en, ru, fa (de nicht als Ziel)", True,
           ", de -> en, ru, fa, Schwelle" in zeile)
    pruefe("Zustandszeile: Schwelle aus, wie sie laeuft", True,
           "Schwelle aus" in zeile)
    pruefe("und daneben dieselbe Schwelle", True, "Schwelle: aus" in text)
    d = json.loads(rufen(PORT, "/api/sprachen")[1])
    pruefe("es laeuft de -> en, ru, fa",
           ["de", "en", "ru", "fa"], [x["code"] for x in d["liste"]])
finally:
    server_stoppen(p)
    if FEHLER:
        print("\n   Ausgabe des Servers:")
        for z in ausgabe.read_text(encoding="utf-8",
                                   errors="replace").splitlines()[:60]:
            print("     | " + z)

# =====================================================================
titel("2) Die Zustandszeile fuer sich")
basis = zustandsdatei.vorgabe()


def zeile_mit(**felder):
    d = json.loads(json.dumps(basis))
    d.update(felder)
    return zustandsdatei.kurzfassung(d)


pruefe("Quelle unter den Zielen: nicht genannt", True,
       "de -> en, ru, fa, Schwelle" in zeile_mit(quelle="de",
                                       ziele=["en", "ru", "fa", "de"]))
pruefe("nur die Quelle als Ziel: nichts", True,
       "de -> nichts," in zeile_mit(quelle="de", ziele=["de"]))
for modus, wert, erwartet in (("aus", None, "Schwelle aus"),
                              ("automatisch", None, "Schwelle automatisch"),
                              ("fest", 0.0123, "Schwelle fest 0.0123"),
                              ("fest", None, "Schwelle aus")):
    s = {"wert": wert, "gemessen": None, "modus": modus, "grundmodus": "aus"}
    pruefe(f"Modus {modus}, Wert {wert}: {erwartet}", True,
           erwartet in zeile_mit(schwelle=s))

# =====================================================================
titel("3) Stimmen: die Quelle braucht keine, die fruehere Quelle schon")
import server  # noqa: E402

ohne_stimme = getattr(server, "ohne_stimme", None)
pruefe("es gibt server.ohne_stimme", True, ohne_stimme is not None)
if ohne_stimme:
    pruefe("Ohne Stimme: die Quelle nicht, auch nicht unter den Zielen", [],
           ohne_stimme(["de", "en", "ru", "fa"], "de",
                       {"en": 1, "ru": 1, "fa": 1}))
    pruefe("eine Zielsprache ohne Stimme schon", ["fa"],
           ohne_stimme(["de", "en", "fa"], "de", {"en": 1}))

thorsten = config.STIMMEN["de"].rsplit("/", 1)[-1]
da = (config.BASIS / "voices" / f"{thorsten}.onnx").is_file() and \
     (config.BASIS / "voices" / f"{thorsten}.onnx.json").is_file()
if not da:
    print(f"   --    {thorsten} liegt hier nicht, Fall 3b uebersprungen")
else:
    # Ein Werk ohne Whisper und ohne Piper-Modul: nur, was
    # stimme_nachladen() anfasst. Der Server lief mit Quelle de an
    # (server.QUELLE), dann wurde am Pult auf ru gestellt.
    werk = server.Werk.__new__(server.Werk)
    werk.nur_text = False
    werk.piper = "programm"
    werk.stimmen = {"en": "x", "fa": "x"}
    werk.stimmennamen = {}
    werk.quelle = "ru"
    server.QUELLE = "de"
    pruefe("nach dem Wechsel auf ru: thorsten wird nachgeladen", True,
           werk.stimme_nachladen("de"))
    pruefe("und de laeuft mit Stimme", thorsten,
           Path(str(werk.stimmen.get("de", ""))).stem)
    pruefe("ru als Quelle bekommt keine", False, werk.stimme_nachladen("ru"))

print()
if FEHLER:
    print(f"{ROT}{FEHLER} Fehler.{AUS}")
    sys.exit(1)
print(f"{GRUEN}Alle Faelle wie erwartet.{AUS}")
