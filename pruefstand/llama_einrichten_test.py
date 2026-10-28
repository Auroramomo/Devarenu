#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Der Umstieg auf llama-server, mit Attrappen (0.5.2, 28.10.2026).

    python pruefstand/llama_einrichten_test.py

llama_einrichten.py auf einer Wegwerfkopie. Nichts davon beruehrt /opt,
/etc oder einen echten Dienst:

  Download    ein HTTP-Server hier, auf Wunsch reisst er nach der Haelfte ab
  Archive     kleine tar.gz mit einem llama-server, der nur seine Fassung
              und eine "CUDA0" meldet
  Modell      ein kleiner "Ollama-Blob" in einer Ollama-Ablage hier
  systemctl   eine Attrappe mit Zustand (aktiv, eingeschaltet) je Unit
  nvidia-smi  die Attrappe aus pruefstand/attrappen
  llama-server die Attrappe aus pruefstand/attrappen (oder eine, die denkt)

Faelle: Einrichtung gelingt; Download reisst ab und wird fortgesetzt;
Probe scheitert (Ollama bleibt an); zweiter Lauf; kein Internet und
keine Teile; und aktualisierung.sh ruft den Schritt am Ende auf, ohne
dass er das Update scheitern lassen kann.
"""
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "attrappen"))
import config  # noqa: E402
import ollama_attrappe as attrappe  # noqa: E402
from hilfe import arbeitskopie  # noqa: E402

FEHLER = 0


def pruefe(was, erwartet, ist):
    global FEHLER
    if erwartet == ist:
        print(f"   ok    {was}")
    else:
        FEHLER += 1
        print(f"   FEHL  {was}: erwartet {erwartet!r}, ist {ist!r}")


def titel(t):
    print(f"\n\033[1m== {t}\033[0m")


# ------------------------------------------------------------ Teile
def targz(ober, dateien):
    puffer = io.BytesIO()
    with tarfile.open(fileobj=puffer, mode="w:gz") as t:
        for name, (inhalt, modus) in dateien.items():
            info = tarfile.TarInfo(f"{ober}/{name}")
            info.size = len(inhalt)
            info.mode = modus
            t.addfile(info, io.BytesIO(inhalt))
    return puffer.getvalue()


BUILD = config.LLAMA_BUILD
LLAMA_EXE = (b"#!/bin/sh\ncase \"$1\" in\n"
             b"  --version) echo \"version: 0.8.0-dev (build "
             + BUILD.lstrip("b").encode() + b", commit attrappe)\" ;;\n"
             b"  --list-devices) echo \"Available devices:\"; "
             b"echo \"  CUDA0: Attrappe (16000 MiB)\" ;;\n"
             b"esac\n")
INHALT = {
    config.LLAMA_ARCHIV: targz(f"llama-{BUILD}", {
        "llama-server": (LLAMA_EXE, 0o755),
        "libllama.so": (b"\x7fELF attrappe", 0o644)}),
    config.LLAMA_CUDART: targz(
        config.LLAMA_CUDART.removesuffix(".tar.gz"),
        {"libcudart.so.12": (b"\x7fELF cudart", 0o644)}),
    config.LLAMA_GGUF_NAME: b"GGUF" + bytes(range(256)) * 400,
}
SHA = {n: hashlib.sha256(b).hexdigest() for n, b in INHALT.items()}


class Anfragen:
    liste = []
    abreissen = set()


class Quelle(BaseHTTPRequestHandler):
    def do_GET(self):
        name = self.path.strip("/")
        Anfragen.liste.append((name, self.headers.get("Range")))
        if name not in INHALT:
            self.send_response(404); self.end_headers(); return
        daten = INHALT[name]
        anfang = 0
        rng = self.headers.get("Range")
        if rng:
            anfang = int(rng.split("=")[1].split("-")[0])
            self.send_response(206)
        else:
            self.send_response(200)
        rest = daten[anfang:]
        self.send_header("Content-Length", str(len(rest)))
        self.end_headers()
        if name in Anfragen.abreissen and not rng:
            # Wie ein Gastzugang, der abreisst: die Haelfte, dann Schluss.
            Anfragen.abreissen.discard(name)
            self.wfile.write(rest[:len(rest) // 2])
            self.wfile.flush()
            self.connection.close()
            return
        self.wfile.write(rest)

    def do_HEAD(self):
        self.send_response(200); self.end_headers()

    def log_message(self, *a):
        pass


quelle = ThreadingHTTPServer(("127.0.0.1", 0), Quelle)
threading.Thread(target=quelle.serve_forever, daemon=True).start()
QUELLE = f"http://127.0.0.1:{quelle.server_address[1]}"


class Denkt(attrappe.LlamaAntwort):
    """Ein llama-server, der trotz abgeschaltetem Denken denkt."""
    def do_POST(self):
        laenge = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(laenge)
        self._json({"choices": [{"message": {
            "role": "assistant", "content": "And Jesus said ...",
            "reasoning_content": "Role: interpreter ..."}}],
            "usage": {"completion_tokens": 330}})


LLAMA = attrappe.starten("llama-server")
denkt = ThreadingHTTPServer(("127.0.0.1", 0), Denkt)
threading.Thread(target=denkt.serve_forever, daemon=True).start()
DENKT = f"http://127.0.0.1:{denkt.server_address[1]}"

SYSTEMCTL = """#!/usr/bin/env bash
# Attrappe mit Zustand: $STUB_STAND/<unit>.aktiv und <unit>.an
echo "systemctl $*" >> "$STUB_LOG"
befehl="$1"; shift
[ "$befehl" = "--user" ] && { befehl="$1"; shift; }
jetzt=""
for a in "$@"; do case "$a" in --now) jetzt=ja ;; --quiet|-p|--value) ;;
  MainPID) ;; *) u="${a%.service}" ;; esac; done
case "$befehl" in
  is-active)  [ -f "$STUB_STAND/$u.aktiv" ] ;;
  is-enabled) [ -f "$STUB_STAND/$u.an" ] ;;
  start|restart) touch "$STUB_STAND/$u.aktiv" ;;
  stop) rm -f "$STUB_STAND/$u.aktiv" ;;
  enable) touch "$STUB_STAND/$u.an"; [ -n "$jetzt" ] && touch "$STUB_STAND/$u.aktiv"; true ;;
  disable) rm -f "$STUB_STAND/$u.an"; [ -n "$jetzt" ] && rm -f "$STUB_STAND/$u.aktiv"; true ;;
  show) echo 0 ;;
  *) true ;;
esac
"""


class Lauf:
    """Ein Rechner: Wegwerfkopie, Ollama-Ablage, Zustand der Dienste."""

    def __init__(self, name, blob=True, ollama_an=True):
        self.ort = Path(tempfile.mkdtemp(prefix=f"llama-{name}-",
                                         dir=WURZEL / ".tmp"))
        self.kopie = self.ort / "devarenu"
        arbeitskopie(self.kopie)
        shutil.copy2(WURZEL / "devarenu-llama.service.vorlage", self.kopie)
        teile = {"teile": [{"art": "llama", "pfad": n, "bytes": len(b),
                            "sha256": SHA[n]} for n, b in INHALT.items()]}
        (self.kopie / "teile.json").write_text(json.dumps(teile))
        self.stand = self.ort / "stand"
        self.stand.mkdir()
        if ollama_an:
            for e in ("aktiv", "an"):
                (self.stand / f"ollama.{e}").touch()
        self.ablage = self.ort / "ollama"
        (self.ablage / "blobs").mkdir(parents=True)
        if blob:
            n = config.LLAMA_GGUF_NAME
            (self.ablage / "blobs" / f"sha256-{SHA[n]}").write_bytes(INHALT[n])
        (self.ort / "systemctl").write_text(SYSTEMCTL)
        os.chmod(self.ort / "systemctl", 0o755)
        self.quellen = self.ort / "quellen.json"
        self.quellen_setzen(QUELLE)

    def quellen_setzen(self, wurzel):
        self.quellen.write_text(json.dumps(
            {n: f"{wurzel}/{n}" for n in INHALT}))

    def starten(self, llama=LLAMA):
        self.log = self.ort / "systemctl.log"
        self.log.write_text("")
        env = dict(os.environ,
                   DEVARENU_LLAMA_OHNE_ROOT="1",
                   DEVARENU_LLAMA_OPT=str(self.ort / "opt"),
                   DEVARENU_UNIT_ORDNER=str(self.ort / "units"),
                   DEVARENU_SYSTEMCTL=str(self.ort / "systemctl"),
                   DEVARENU_NVIDIA_SMI=str(WURZEL / "pruefstand/attrappen/nvidia-smi"),
                   NVSMI_AUSGABE="5200, /opt/x/llama-server, 9628\\n",
                   DEVARENU_LLAMA_QUELLEN=str(self.quellen),
                   DEVARENU_LLAMA_URL=llama,
                   DEVARENU_LLAMA_PAUSE="1",
                   DEVARENU_PORT="9",
                   OLLAMA_MODELS=str(self.ablage),
                   STUB_STAND=str(self.stand), STUB_LOG=str(self.log))
        a = subprocess.run([str(self.kopie / ".venv/bin/python"),
                            "llama_einrichten.py", "--frist", "120"],
                           cwd=self.kopie, env=env, capture_output=True,
                           text=True, timeout=300)
        self.aus = a.stdout + a.stderr
        self.rc = a.returncode
        try:
            self.lage = json.loads((self.kopie / "update/llama-lage.json")
                                   .read_text())
        except (OSError, ValueError):
            self.lage = {}
        return self

    def systemctl(self):
        return self.log.read_text()

    def aktiv(self, unit):
        return (self.stand / f"{unit}.aktiv").exists()

    def an(self, unit):
        return (self.stand / f"{unit}.an").exists()

    def ergebnis(self):
        return next((z[9:] for z in self.aus.splitlines()
                     if z.startswith("ERGEBNIS|")), "")

    def weg(self):
        shutil.rmtree(self.ort, ignore_errors=True)


titel("1) Einrichtung gelingt (Rostock: Ollama an, Blob in der Ablage)")
r = Lauf("gut")
Anfragen.liste.clear()
r.starten()
print("      " + r.ergebnis())
pruefe("Rueckgabe 0", 0, r.rc)
pruefe("eingerichtet laut llama-lage.json", True, r.lage.get("eingerichtet"))
pruefe("das Modell kam aus der Ollama-Ablage, nicht aus dem Netz", True,
       "aus der Ollama-Ablage" in r.aus
       and not any(n == config.LLAMA_GGUF_NAME for n, _ in Anfragen.liste))
pruefe("Archiv und cudart wurden geladen", True,
       {config.LLAMA_ARCHIV, config.LLAMA_CUDART}
       <= {n for n, _ in Anfragen.liste})
z = r.ort / "opt" / BUILD
pruefe("ausgepackt nach opt/<build>, cudart daneben", (True, True),
       ((z / "llama-server").is_file(), (z / "libcudart.so.12").is_file()))
pruefe("opt/aktuell zeigt darauf", BUILD,
       os.readlink(r.ort / "opt" / "aktuell"))
unit = (r.ort / "units" / "devarenu-llama.service").read_text()
pruefe("Unit nur auf 127.0.0.1, Port aus der Adresse", True,
       f"--host 127.0.0.1 --port {LLAMA.rsplit(':', 1)[1]} " in unit)
pruefe("Unit nimmt opt/aktuell/llama-server und das Modell", True,
       f"{r.ort}/opt/aktuell/llama-server -m " in unit
       and f"sprachmodell/{config.LLAMA_GGUF_NAME}" in unit)
log = r.systemctl()
pruefe("Ollama erst angehalten (fuer die Probe)", True, "stop ollama" in log)
pruefe("llama-server eingeschaltet", (True, True),
       (r.aktiv("devarenu-llama"), r.an("devarenu-llama")))
pruefe("Ollama danach abgeschaltet", (False, False),
       (r.aktiv("ollama"), r.an("ollama")))
pruefe("die Reihenfolge: Probe vor dem Abschalten", True,
       log.index("restart devarenu-llama") < log.index("disable --now ollama"))
pruefe("der Satz nennt das Tempo", True, "Probe:" in r.ergebnis())

titel("2) Zweiter Lauf erkennt den fertigen Zustand")
Anfragen.liste.clear()
r.starten()
print("      " + r.ergebnis())
pruefe("Rueckgabe 0", 0, r.rc)
pruefe("schon eingerichtet", True, "schon eingerichtet" in r.ergebnis())
pruefe("nichts geladen", [], Anfragen.liste)
pruefe("nichts neu gestartet oder umgeschaltet", False,
       any(w in r.systemctl() for w in ("restart", "enable", "disable",
                                        "daemon-reload", "stop")))
r.weg()

titel("3) Der Download reisst ab und wird fortgesetzt")
r = Lauf("abriss")
Anfragen.liste.clear()
Anfragen.abreissen = {config.LLAMA_CUDART}
r.starten()
pruefe("Rueckgabe 0", 0, r.rc)
pruefe("der Abriss steht im Protokoll", True, "abgerissen" in r.aus)
pruefe("fortgesetzt mit Range", True,
       any(n == config.LLAMA_CUDART and rng for n, rng in Anfragen.liste))
pruefe("und die Datei stimmt", SHA[config.LLAMA_CUDART], hashlib.sha256(
    (r.kopie / "sprachmodell" / config.LLAMA_CUDART).read_bytes()).hexdigest())
r.weg()

titel("4) Die Probe scheitert: Ollama bleibt, wie es war")
r = Lauf("probe")
r.starten(llama=DENKT)
print("      " + r.ergebnis())
pruefe("Rueckgabe 1 (nicht eingerichtet)", 1, r.rc)
pruefe("der Grund steht im Satz", True,
       "Probe nicht bestanden" in r.ergebnis() and "denkt" in r.ergebnis())
pruefe("Ollama laeuft wieder und ist eingeschaltet", (True, True),
       (r.aktiv("ollama"), r.an("ollama")))
pruefe("Ollama wurde nie abgeschaltet", False,
       "disable --now ollama" in r.systemctl())
pruefe("llama-server ist aus", (False, False),
       (r.aktiv("devarenu-llama"), r.an("devarenu-llama")))
pruefe("llama-lage.json sagt nein", False, r.lage.get("eingerichtet"))
pruefe("und der Satz nennt, wer jetzt uebersetzt", True,
       r.ergebnis().endswith("Es uebersetzt weiter: Ollama."))
r.weg()

titel("5) Kein Internet, keine Teile: uebersprungen und gemeldet")
r = Lauf("offline", blob=False)
r.quellen_setzen("http://127.0.0.1:9")
r.starten()
print("      " + r.ergebnis())
pruefe("Rueckgabe 2 (uebersprungen)", 2, r.rc)
pruefe("der Satz sagt es", True, "kein Internet" in r.ergebnis())
pruefe("nichts gestoppt, gestartet oder umgeschaltet", False,
       any(w in r.systemctl() for w in ("stop", "start", "enable",
                                        "disable", "daemon-reload")))
pruefe("Ollama laeuft weiter", True, r.aktiv("ollama"))
r.weg()

titel("6) Ein Stick brachte die Teile: kein Download")
r = Lauf("stick", blob=False)
(r.kopie / "sprachmodell").mkdir()
for n, b in INHALT.items():
    (r.kopie / "sprachmodell" / n).write_bytes(b)
r.quellen_setzen("http://127.0.0.1:9")
Anfragen.liste.clear()
r.starten()
pruefe("eingerichtet, ohne Netz", (0, []), (r.rc, Anfragen.liste))
r.weg()

titel("7) aktualisierung.sh: am Ende, nie toedlich")
text = (WURZEL / "aktualisierung.sh").read_text(encoding="utf-8")
block = text.split("# ------------------------------------------------- llama-server (0.5.2)")
pruefe("der Schritt steht in aktualisierung.sh", 2, len(block))
if len(block) == 2:
    davor, danach = block
    schritt = danach.split("# ------------------------------------------------------- Der Stand")[0]
    pruefe("nach dem Gesundheitscheck", True, 'blau "Gesundheitscheck"' in davor)
    pruefe("ohne exit -- er kann das Update nicht scheitern lassen", False,
           "exit" in "".join(z for z in schritt.splitlines(True)
                             if not z.lstrip().startswith("#")))
    pruefe("mit Zeitgrenze", True, "timeout " in schritt and "--frist" in schritt)
    pruefe("der Satz geht als MELDUNG ans Pult und in die Rueckmeldung", True,
           'melden "$LLAMA_SATZ"' in schritt)

quelle.shutdown()
denkt.shutdown()
print()
if FEHLER:
    print(f"{FEHLER} FEHLER")
    sys.exit(1)
print("Alles in Ordnung.")
