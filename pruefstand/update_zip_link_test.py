#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Der dauerhafte Link auf Devarenu-Update.zip (0.5.2, 28.10.2026).

    python pruefstand/update_zip_link_test.py

  1. Am Pult unter Einrichtung -> Update: der Link als Text, ein QR-Code,
     ein Satz fuer Helfer (de und en).
  2. Der QR-Code kommt vom Server und traegt genau config.UPDATE_ZIP_LINK.
  3. stick_bauen.sh schreibt immer Devarenu-Update.zip; release_zip.sh
     prueft das fertige ZIP auf NVIDIA-Dateien und legt kein Tag selbst an.
"""
import shutil
import sys
import tempfile
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
from hilfe import arbeitskopie, rufen, server_starten, server_stoppen  # noqa: E402

FEHLER = 0
PORT = 8153
LINK = ("https://github.com/Auroramomo/Devarenu/releases/latest/download/"
        "Devarenu-Update.zip")


def pruefe(was, erwartet, ist):
    global FEHLER
    if erwartet == ist:
        print(f"   ok    {was}")
    else:
        FEHLER += 1
        print(f"   FEHL  {was}: erwartet {erwartet!r}, ist {ist!r}")


print("\n== 1) Das Pult")
pult = (WURZEL / "web" / "pult.html").read_text(encoding="utf-8")
pruefe("config.UPDATE_ZIP_LINK ist der feste Link", LINK,
       getattr(config, "UPDATE_ZIP_LINK", None))
pruefe("der Link steht als Text im Pult", True, f">{LINK}</code>" in pult)
pruefe("mit QR-Code", True, 'src="/update-zip-qr.png"' in pult)
pruefe("und einem Satz fuer Helfer, deutsch und englisch", 2,
       pult.count("uz_hin:"))
pruefe("der Satz sagt: nicht auspacken", True, "(nicht auspacken)" in pult)

print("\n== 2) Der QR-Code vom Server")
ort = Path(tempfile.mkdtemp(prefix="updatezip-", dir=WURZEL / ".tmp"))
lauf = None
try:
    arbeitskopie(ort)
    lauf = server_starten(ort, PORT)
    status, roh = rufen(PORT, "/update-zip-qr.png")
    pruefe("/update-zip-qr.png kommt als PNG", (200, True),
           (status, "PNG" in roh[:8]))
finally:
    server_stoppen(lauf)
    shutil.rmtree(ort, ignore_errors=True)
quelle = (WURZEL / "server.py").read_text(encoding="utf-8")
pruefe("er traegt config.UPDATE_ZIP_LINK", True,
       "segno.make(config.UPDATE_ZIP_LINK" in quelle)

print("\n== 3) Bauen und Hochladen")
bau = (WURZEL / "stick_bauen.sh").read_text(encoding="utf-8")
pruefe("stick_bauen.sh: fester Name", True,
       'ZIP_NAME="Devarenu-Update.zip"' in bau
       and 'ZIEL_ZIP="$(cd "$ZIEL_ZIP" && pwd)/$ZIP_NAME"' in bau)
pruefe("und --mit-fremdteilen fuer einen privaten Stick", True,
       "--mit-fremdteilen)  MIT_FREMDTEILEN=ja" in bau)
rel = WURZEL / "release_zip.sh"
text = rel.read_text(encoding="utf-8") if rel.exists() else ""
pruefe("release_zip.sh gibt es", True, rel.exists())
pruefe("es sieht ins fertige ZIP nach NVIDIA-Dateien", True,
       "nvidia[-_]" in text and "cudart" in text)
pruefe("es legt kein Tag selbst an (--verify-tag, Tag muss auf GitHub sein)",
       True, "--verify-tag" in text and "git ls-remote" in text)
pruefe("es baut ohne --mit-fremdteilen", False,
       "--mit-fremdteilen" in "\n".join(z for z in text.splitlines()
                                        if not z.lstrip().startswith("#")))

print()
if FEHLER:
    print(f"{FEHLER} FEHLER")
    sys.exit(1)
print("Alles in Ordnung.")
