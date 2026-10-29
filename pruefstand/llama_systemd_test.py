#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Welcher Sprachmodell-Server laeuft nach dem llama-Schritt -- mit
echtem systemd (29.10.2026).

    .venv/bin/python pruefstand/llama_systemd_test.py

WARUM DIESER LAUF EXISTIERT
---------------------------
devarenu.service hat Wants= auf ollama.service UND devarenu-llama.service,
devarenu-llama.service hat Conflicts=ollama.service. llama_einrichten.py
schaltet Ollama nach bestandener Probe nur ab (disable --now) und startet
devarenu neu. Ein Wants= kuemmert sich nicht um "disable": es zieht
Ollama bei jedem Start von devarenu wieder hoch -- und dann entscheidet
systemd, wer von beiden weichen muss. llama_einrichten_test.py sieht das
nicht, dort ist systemctl eine Attrappe ohne Abhaengigkeiten.

WAS HIER ECHT IST
-----------------
systemd, im Benutzerbereich (systemctl --user). Die Abhaengigkeiten von
devarenu.service stehen hier so, wie sie in devarenu.service.vorlage
stehen; devarenu-llama.service schreibt llama_einrichten.py selbst aus
seiner Vorlage (DEVARENU_LLAMA_BENUTZERUNIT). ollama.service ist gebaut
wie die Unit des Installierskripts von ollama.com: Restart=always,
WantedBy=default.target, als gewoehnliche Datei im obersten Unit-Ordner
(wie /etc/systemd/system) -- oder, zweite Lage, im untersten (wie
/usr/lib/systemd/system beim Arch-Paket).

Jeder Dienst ist ein "sleep infinity" (llama-server ein Skript, das
seine Fassung nennt und dann schlaeft). Die Probe geht an die
llama-Attrappe. Nichts davon beruehrt einen Dienst des Systems; am Ende
wird alles wieder abgebaut.

FAELLE, je Lage der Ollama-Unit
-------------------------------
1. Der llama-Schritt besteht, danach startet er devarenu neu.
2. Kalter Start wie beim Hochfahren: alles gestoppt, dann gestartet, was
   eingeschaltet ist (ein Ziel, das genau diese Units will) -- und
   devarenu allein.
3. Die Probe scheitert: danach und beim kalten Start muss Ollama laufen.
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
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "attrappen"))
import config  # noqa: E402
import ollama_attrappe as attrappe  # noqa: E402
from hilfe import arbeitskopie  # noqa: E402

FEHLER = 0
UNITS = ("devarenu", "devarenu-llama", "ollama")
OBEN = Path.home() / ".config/systemd/user"           # wie /etc
UNTEN = Path.home() / ".local/share/systemd/user"     # wie /usr/lib
ZIEL = "devarenu-pruef-hochfahren.target"


def pruefe(was, erwartet, ist):
    global FEHLER
    if erwartet == ist:
        print(f"   ok    {was}")
    else:
        FEHLER += 1
        print(f"   FEHL  {was}: erwartet {erwartet!r}, ist {ist!r}")


def titel(t):
    print(f"\n\033[1m== {t}\033[0m", flush=True)


def sc(*args):
    return subprocess.run(["systemctl", "--user", *args], capture_output=True,
                          text=True, timeout=60)


def lage():
    """{"devarenu": "active", ...}, kurz nachdem sich alles gesetzt hat."""
    time.sleep(1.5)
    return {u: sc("is-active", f"{u}.service").stdout.strip() for u in UNITS}


def wer_laeuft(l):
    if l["devarenu"] != "active":
        return "devarenu laeuft nicht"
    an = [u for u in ("devarenu-llama", "ollama") if l[u] == "active"]
    return " und ".join(an) or "keiner"


# --------------------------------------------------------- Vorbedingung
belegt = [u for u in UNITS
          if sc("cat", f"{u}.service").returncode == 0]
if belegt:
    print(f"   !     Benutzer-Units schon vorhanden: {belegt}. Abbruch.")
    sys.exit(1)
if sc("show-environment").returncode != 0:
    print("   !     Kein systemd --user. NICHT geprueft.")
    sys.exit(1)


# ---------------------------------------------------- Die Wegwerfkopie
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
# Nennt Fassung und Karte wie llama-server, und schlaeft sonst -- so
# bleibt die Unit aktiv wie die echte.
LLAMA_EXE = (b"#!/bin/sh\ncase \"$1\" in\n"
             b"  --version) echo \"version: 0.8.0-dev (build "
             + BUILD.lstrip("b").encode() + b", commit attrappe)\" ;;\n"
             b"  --list-devices) echo \"  CUDA0: Attrappe (16000 MiB)\" ;;\n"
             b"  *) exec sleep infinity ;;\n"
             b"esac\n")
INHALT = {
    config.LLAMA_ARCHIV: targz(f"llama-{BUILD}", {
        "llama-server": (LLAMA_EXE, 0o755)}),
    config.LLAMA_CUDART: targz(
        config.LLAMA_CUDART.removesuffix(".tar.gz"),
        {"libcudart.so.12": (b"\x7fELF cudart", 0o644)}),
    config.LLAMA_GGUF_NAME: b"GGUF" + bytes(range(256)) * 40,
}
SHA = {n: hashlib.sha256(b).hexdigest() for n, b in INHALT.items()}

GUT = attrappe.starten("llama-server")


class Denkt(attrappe.LlamaAntwort):
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self._json({"choices": [{"message": {
            "role": "assistant", "content": "And Jesus said ...",
            "reasoning_content": "(gedacht)"}}],
            "usage": {"completion_tokens": 330}})


denkt = ThreadingHTTPServer(("127.0.0.1", 0), Denkt)
threading.Thread(target=denkt.serve_forever, daemon=True).start()
DENKT = f"http://127.0.0.1:{denkt.server_address[1]}"

ORT = Path(tempfile.mkdtemp(prefix="llama-systemd-", dir=WURZEL / ".tmp"))
GESCHRIEBEN = []


def abbauen():
    for u in UNITS:
        sc("disable", "--now", f"{u}.service")
    sc("stop", ZIEL)
    for p in GESCHRIEBEN + [OBEN / "devarenu-llama.service"]:
        try:
            p.unlink()
        except OSError:
            pass
    sc("daemon-reload")
    for u in UNITS:
        sc("reset-failed", f"{u}.service")


def schreiben(pfad, text):
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(text, encoding="utf-8")
    GESCHRIEBEN.append(pfad)


def devarenu_unit():
    """Die Abhaengigkeiten aus devarenu.service.vorlage, unveraendert."""
    vorlage = (WURZEL / "devarenu.service.vorlage").read_text(encoding="utf-8")
    unit = vorlage.split("[Service]")[0].split("[Unit]", 1)[1]
    zeilen = [z for z in unit.splitlines()
              if z.split("=", 1)[0] in ("After", "Wants", "Requires",
                                         "Before", "Conflicts", "BindsTo")]
    return ("[Unit]\nDescription=Pruefstand: devarenu\n" + "\n".join(zeilen)
            + "\n\n[Service]\nExecStart=/bin/sleep infinity\n\n"
              "[Install]\nWantedBy=default.target\n")


OLLAMA_UNIT = ("[Unit]\nDescription=Pruefstand: ollama (wie ollama.com)\n"
               "After=network-online.target\n\n[Service]\n"
               "ExecStart=/bin/sleep infinity\nRestart=always\nRestartSec=1\n\n"
               "[Install]\nWantedBy=default.target\n")


def rechner(name, ollama_ort):
    """Eine Wegwerfkopie, die Units, Ollama an und laufend, devarenu an."""
    abbauen()
    GESCHRIEBEN.clear()
    kopie = ORT / name
    if kopie.exists():
        shutil.rmtree(kopie)
    arbeitskopie(kopie)
    shutil.copy2(WURZEL / "devarenu-llama.service.vorlage", kopie)
    (kopie / "teile.json").write_text(json.dumps({"teile": [
        {"art": "llama", "pfad": n, "bytes": len(b), "sha256": SHA[n]}
        for n, b in INHALT.items()]}))
    # Alles "vom Stick": kein Download, um den geht es hier nicht.
    (kopie / "sprachmodell").mkdir()
    for n, b in INHALT.items():
        (kopie / "sprachmodell" / n).write_bytes(b)
    schreiben(OBEN / "devarenu.service", devarenu_unit())
    schreiben(ollama_ort / "ollama.service", OLLAMA_UNIT)
    sc("daemon-reload")
    sc("enable", "--now", "ollama.service")
    sc("enable", "devarenu.service")
    sc("start", "devarenu.service")
    return kopie


def einrichten(kopie, llama):
    env = dict(os.environ,
               DEVARENU_LLAMA_OHNE_ROOT="1",
               DEVARENU_LLAMA_BENUTZERUNIT="1",
               DEVARENU_SYSTEMCTL="systemctl --user",
               DEVARENU_UNIT_ORDNER=str(OBEN),
               DEVARENU_LLAMA_OPT=str(kopie / "opt"),
               DEVARENU_NVIDIA_SMI=str(WURZEL / "pruefstand/attrappen/nvidia-smi"),
               NVSMI_AUSGABE="",
               DEVARENU_LLAMA_URL=llama,
               DEVARENU_LLAMA_PAUSE="1",
               DEVARENU_KEIN_NETZ="1",
               DEVARENU_PORT="9")
    a = subprocess.run([str(kopie / ".venv/bin/python"), "llama_einrichten.py",
                        "--frist", "120"], cwd=kopie, env=env,
                       capture_output=True, text=True, timeout=300)
    satz = next((z[9:] for z in a.stdout.splitlines()
                 if z.startswith("ERGEBNIS|")), "")
    print(f"      Rueckgabe {a.returncode}: {satz}")
    return a.returncode


def hochfahren():
    """Alles gestoppt, dann ein Ziel, das will, was eingeschaltet ist --
    so wie multi-user.target beim Hochfahren."""
    for u in UNITS:
        sc("stop", f"{u}.service")
    an = [f"{u}.service" for u in UNITS
          if sc("is-enabled", f"{u}.service").stdout.strip() == "enabled"]
    schreiben(OBEN / ZIEL, "[Unit]\nDescription=Pruefstand: Hochfahren\n"
              f"Wants={' '.join(an)}\n")
    sc("daemon-reload")
    sc("start", ZIEL)
    return an


def nur_devarenu():
    for u in UNITS:
        sc("stop", f"{u}.service")
    sc("start", "devarenu.service")


try:
    for ort_name, ort in (("oben, wie /etc (ollama.com)", OBEN),
                          ("unten, wie /usr/lib (Arch-Paket)", UNTEN)):
        titel(f"Ollama-Unit {ort_name}: Probe besteht")
        kopie = rechner("gut", ort)
        pruefe("vorher: devarenu und Ollama laufen", "ollama",
               wer_laeuft(lage()))
        pruefe("der llama-Schritt richtet ein", 0, einrichten(kopie, GUT))
        l = lage()
        print(f"      danach: {l}")
        pruefe("1) nach dem Neustart von devarenu laeuft llama-server",
               "devarenu-llama", wer_laeuft(l))
        an = hochfahren()
        l = lage()
        print(f"      eingeschaltet: {an}; nach dem Hochfahren: {l}")
        pruefe("2) nach dem Hochfahren laeuft llama-server",
               "devarenu-llama", wer_laeuft(l))
        nur_devarenu()
        l = lage()
        print(f"      nur devarenu gestartet: {l}")
        pruefe("2) devarenu allein gestartet: llama-server",
               "devarenu-llama", wer_laeuft(l))

        titel(f"Ollama-Unit {ort_name}: Probe scheitert")
        kopie = rechner("schlecht", ort)
        pruefe("der llama-Schritt richtet nicht ein", 1,
               einrichten(kopie, DENKT))
        l = lage()
        print(f"      danach: {l}")
        pruefe("3) danach laeuft Ollama", "ollama", wer_laeuft(l))
        an = hochfahren()
        l = lage()
        print(f"      eingeschaltet: {an}; nach dem Hochfahren: {l}")
        pruefe("3) nach dem Hochfahren laeuft Ollama", "ollama", wer_laeuft(l))
finally:
    abbauen()
    denkt.shutdown()
    shutil.rmtree(ORT, ignore_errors=True)

pruefe("abgebaut: keine Pruefstand-Unit mehr da", [],
       [u for u in UNITS if sc("cat", f"{u}.service").returncode == 0])
print()
if FEHLER:
    print(f"{FEHLER} FEHLER")
    sys.exit(1)
print("Alles in Ordnung.")
