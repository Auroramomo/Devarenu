#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Grosse Teile und Stimmen nach dem Rostocker Update (A3, 28.10.2026).

    python pruefstand/teile_netz_test.py

Beim Update auf 0.5.1 in Rostock stand:

    6 Teile ausser Stimmen fehlen (Sprachmodell oder Spracherkennung)
    Der Piper-Vorrat ist nicht erreichbar (HTTPError)

obwohl pruefen.sh Whisper und gemma4:12b als vorhanden meldete, und
teile.py --pruefen nannte "16 fehlen", listete aber nur zehn.

Drei Fehler:
  a) --pruefen schnitt nach zehn Zeilen ab.
  b) Die sechs waren Manifest und Blobs von gemma4:12b in der
     Ollama-Ablage. "fehlen" hiess: teile.py fand die Ablage nicht
     (oder die Dateien darin nicht) -- Ollama selbst hatte das Modell.
     Die Meldung muss das sagen, statt "Sprachmodell oder
     Spracherkennung" zu raten.
  c) Die Erreichbarkeitsprobe fragte .../resolve/main OHNE Datei. Darauf
     antwortet Hugging Face 404, also HTTPError -- bei jedem Versuch,
     auch mit bestem Netz. Keine Stimme kam je ueber diesen Weg.

Gegen einen Server auf 127.0.0.1, der sich wie Hugging Face verhaelt:
die Wurzel 404, voices.json und die Stimmdateien 200.
"""
import contextlib
import hashlib
import io
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
import teile  # noqa: E402
from hilfe import wegwerfordner  # noqa: E402

FEHLER = 0


def pruefe(was, erwartet, ist):
    global FEHLER
    if erwartet == ist:
        print(f"   ok    {was}")
    else:
        FEHLER += 1
        print(f"   FEHLER {was}: erwartet {erwartet!r}, ist {ist!r}")


def titel(t):
    print(f"\n\033[1m== {t}\033[0m")


ord_ = wegwerfordner("devarenu-teilenetz-")
platte = ord_ / "platte"
(platte / "stimmen").mkdir(parents=True)
(platte / "whisper").mkdir(parents=True)

# Die fuenf Stimmen, die in Rostock fehlten (je .onnx und .onnx.json),
# als kleine Attrappen. Twi gibt es nirgends zum Herunterladen.
STIMMEN = {
    "uk": "uk/uk_UA/mykyta/high/uk_UA-mykyta-high",
    "es": "es/es_MX/claude/high/es_MX-claude-high",
    "pt": "pt/pt_BR/jeff/medium/pt_BR-jeff-medium",
    "tw": "tw/tw_GH-openbible_asante-vits",
}
INHALT = {}
for pfad in STIMMEN.values():
    for endung in (".onnx", ".onnx.json"):
        INHALT[pfad + endung] = f"stimme {pfad}{endung}".encode()


class HuggingFace(BaseHTTPRequestHandler):
    def do_GET(self):
        weg = self.path.split("/resolve/main/", 1)
        if self.path.endswith("/resolve/main") or len(weg) < 2:
            # Wie das Original: die nackte Revision ist keine Datei.
            self.send_response(404)
            self.end_headers()
            return
        rel = weg[1]
        if rel == "voices.json":
            daten = b"{}"
        elif rel in INHALT:
            daten = INHALT[rel]
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(daten)))
        self.end_headers()
        self.wfile.write(daten)

    do_HEAD = do_GET

    def log_message(self, *a):
        pass


dienst = ThreadingHTTPServer(("127.0.0.1", 0), HuggingFace)
threading.Thread(target=dienst.serve_forever, daemon=True).start()
teile.PIPER_BASIS = (f"http://127.0.0.1:{dienst.server_address[1]}"
                     f"/rhasspy/piper-voices/resolve/main")

config.STIMMEN = dict(STIMMEN)
teile.STIMMEN_REPO = ord_ / "stimmen-repo"
teile.STIMMEN_REPO.mkdir()
(teile.STIMMEN_REPO / "tw_GH-openbible_asante-vits.onnx.json").write_bytes(
    INHALT["tw/tw_GH-openbible_asante-vits.onnx.json"])

eintraege = []
for pfad in STIMMEN.values():
    for endung in (".onnx", ".onnx.json"):
        b = INHALT[pfad + endung]
        eintraege.append({"art": "stimmen", "pfad": Path(pfad).name + endung,
                          "bytes": len(b),
                          "sha256": hashlib.sha256(b).hexdigest()})
# Die sechs Teile von gemma4:12b, wie in teile.json.
OLLAMA = ["manifests/registry.ollama.ai/library/gemma4/12b"] + [
    f"blobs/sha256-{i}" * 1 for i in "abcde"]
for p in OLLAMA:
    eintraege.append({"art": "ollama", "pfad": p, "bytes": 1,
                      "sha256": "0" * 64})
# Und zwei zum Auffuellen, damit es wie in Rostock mehr als zehn sind.
for i in range(2):
    eintraege.append({"art": "stimmen", "pfad": f"xx_XX-fehlt{i}.onnx",
                      "bytes": 1, "sha256": "0" * 64})
teile.DATEI = ord_ / "teile.json"
teile.PUFFER = ord_ / ".puffer.json"
teile.DATEI.write_text(json.dumps({"teile": eintraege}), encoding="utf-8")
GESAMT = len(eintraege)

# Rostock: die Ollama-Ablage fuer diesen Benutzer nicht gefunden.
teile.orte = lambda: {"whisper": platte / "whisper",
                      "stimmen": platte / "stimmen"}


def mitschreiben(f, *a):
    puffer = io.StringIO()
    with contextlib.redirect_stdout(puffer):
        rc = f(*a)
    return rc, puffer.getvalue()


titel("a) --pruefen nennt ALLE fehlenden Teile")
sys.argv = ["teile.py", "--pruefen"]
rc, aus = mitschreiben(teile.main)
genannt = [z.strip() for z in aus.splitlines()
           if z.strip().startswith(("stimmen/", "ollama/", "whisper/"))]
print("      " + "\n      ".join(aus.strip().splitlines()[:3]) + " ...")
pruefe(f"alle {GESAMT} stehen da", GESAMT, len(genannt))
pruefe("Rueckgabe 1", 1, rc)

titel("b) Was die sechs Nicht-Stimmen sind, steht in der Meldung")
rc, aus = mitschreiben(teile.aus_dem_netz)
print("      " + "\n      ".join(aus.strip().splitlines()[:4]))
pruefe("nicht mehr geraten (\"Sprachmodell oder Spracherkennung\")", False,
       "Sprachmodell oder Spracherkennung" in aus)
pruefe("die Zahl stimmt und das Modell ist genannt", True,
       "6 Dateien des Sprachmodells gemma4:12b" in aus
       or f"6 Dateien des Sprachmodells {config.LIVE_MODELL}" in aus)
pruefe("und der Grund: die Ablage ist nicht auffindbar", True,
       "Ablage" in aus and "nicht auffindbar" in aus)

titel("c) Stimmen kommen, obwohl die Wurzel 404 antwortet")
pruefe("keine Meldung \"nicht erreichbar (HTTPError)\"", False,
       "nicht erreichbar (HTTPError)" in aus)
for sp in ("uk", "es", "pt"):
    n = Path(STIMMEN[sp]).name
    pruefe(f"{sp}: {n}.onnx liegt da", True,
           (platte / "stimmen" / f"{n}.onnx").is_file())
    pruefe(f"{sp}: und die Beschreibung", True,
           (platte / "stimmen" / f"{n}.onnx.json").is_file())
pruefe("Twi kommt nur ueber Stick, und das steht da", True,
       "tw_GH-openbible_asante-vits.onnx (kommt nur ueber Stick" in aus)
pruefe("Ukrainisch ist danach bei --pruefen vollstaendig", True,
       not any("uk_UA" in z for z in mitschreiben(teile.main)[1].splitlines()
               if z.strip().startswith("stimmen/")))

titel("c2) Ohne Netz bleibt es bei einer klaren Meldung")
teile.PIPER_BASIS = "http://127.0.0.1:9/rhasspy/piper-voices/resolve/main"
for e in list((platte / "stimmen").iterdir()):
    e.unlink()
rc, aus = mitschreiben(teile.aus_dem_netz)
pruefe("Rueckgabe 1", 1, rc)
pruefe("\"nicht erreichbar\" mit dem echten Grund", True,
       "nicht erreichbar" in aus and "HTTPError" not in aus)

dienst.shutdown()
print()
if FEHLER:
    print(f"{FEHLER} FEHLER")
    sys.exit(1)
print("Alles in Ordnung.")
