#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""llama-server und Ollama, Erkennen und Fragen (B1, B2, B5, A6; 28.10.2026).

    python pruefstand/sprachmodell_test.py

Ohne Grafikkarte und ohne echtes Sprachmodell: zwei Attrappen, eine als
llama-server, eine als Ollama (pruefstand/attrappen/ollama_attrappe.py).

1) sprachmodell.py fuer sich
   - auto: erst llama-server, dann Ollama; keiner -> "keiner"
   - llama-server bekommt /v1/chat/completions mit temperature 0.1,
     max_tokens 400 und chat_template_kwargs enable_thinking=false
   - Ollama bekommt weiter /api/chat mit "think": false
   - der </think>-Schutz bleibt
2) Der Server startet OHNE Sprachmodell-Server und mit FALSCHEM Modell
   (A6) -- er kommt hoch, und das Pult sagt, was fehlt.
3) Der Server mit llama-server: /api/zustand nennt ihn.
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "attrappen"))
import requests  # noqa: E402

import config  # noqa: E402
import ollama_attrappe as attrappe  # noqa: E402
import sprachmodell  # noqa: E402
from hilfe import (arbeitskopie, llama_umlenken, rufen,  # noqa: E402
                   server_starten, server_stoppen, NIRGENDS)

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


LLAMA = attrappe.starten("llama-server")
OLLAMA = attrappe.starten("ollama")
for v in ("DEVARENU_SPRACHMODELL", "DEVARENU_LLAMA_URL",
          "DEVARENU_LLAMA_MODELL", "DEVARENU_LLAMA_SCHLUESSEL_DATEI"):
    os.environ.pop(v, None)

titel("1) sprachmodell.py fuer sich")
config.LLAMA_URL, config.OLLAMA_URL = LLAMA, OLLAMA
lage = sprachmodell.erkennen(requests)
pruefe("auto findet zuerst llama-server", ("llama-server", ""),
       (lage["art"], lage["grund"]))
t = sprachmodell.fragen(lage["art"], "System", "Text", requests)
pruefe("die Antwort kommt an", attrappe.LLAMA_ANTWORT.strip("[]"), t.strip("[]"))
anfrage = attrappe.ANFRAGEN[-1]
pruefe("Denken ist aus (chat_template_kwargs)", {"enable_thinking": False},
       anfrage.get("chat_template_kwargs"))
pruefe("temperature 0.1, max_tokens 400", (0.1, 400),
       (anfrage.get("temperature"), anfrage.get("max_tokens")))
pruefe("dieselbe Systemanweisung, als system-Nachricht",
       [{"role": "system", "content": "System"},
        {"role": "user", "content": "Text"}], anfrage.get("messages"))
pruefe("der </think>-Schutz bleibt", "Hello",
       sprachmodell.bereinigen("<think>hmm</think> **Hello**"))

config.LLAMA_URL = NIRGENDS
lage = sprachmodell.erkennen(requests)
pruefe("ohne llama-server: Ollama", ("ollama", ""), (lage["art"], lage["grund"]))
url, rumpf, _ = sprachmodell.anfrage("ollama", "S", "T")
pruefe("Ollama ueber /api/chat", True, url.endswith("/api/chat"))
pruefe("mit think: false", False, rumpf.get("think"))
pruefe("und Antwort", attrappe.ANTWORT,
       sprachmodell.fragen("ollama", "S", "T", requests))

os.environ["DEVARENU_SPRACHMODELL"] = "ollama"
config.LLAMA_URL = LLAMA
pruefe("DEVARENU_SPRACHMODELL=ollama erzwingt Ollama", "ollama",
       sprachmodell.erkennen(requests)["art"])
os.environ.pop("DEVARENU_SPRACHMODELL")

config.LLAMA_URL, config.OLLAMA_URL = NIRGENDS, NIRGENDS
lage = sprachmodell.erkennen(requests)
pruefe("keiner antwortet: grund keiner", ("", "keiner"),
       (lage["art"], lage["grund"]))
config.OLLAMA_URL = OLLAMA
alt = config.LIVE_MODELL
config.LIVE_MODELL = "gibt-es-nicht:1b"
pruefe("Ollama ohne das Modell: modell_fehlt", "modell_fehlt",
       sprachmodell.erkennen(requests)["grund"])
config.LIVE_MODELL = alt

titel("2) Der Server kommt ohne Sprachmodell hoch und sagt es (A6)")
os.environ["DEVARENU_SPRACHMODELL_FRIST"] = "3"
PORT = 8151


def _ersetzen(ordner, alt, neu):
    datei = Path(ordner) / "config.py"
    text = datei.read_text(encoding="utf-8")
    assert text.count(alt) == 1, alt
    datei.write_text(text.replace(alt, neu), encoding="utf-8")


FAELLE = [
    ("kein Server antwortet", "sprachmodell_keiner",
     lambda o: _ersetzen(o, 'OLLAMA_URL = "http://127.0.0.1:',
                         f'OLLAMA_URL = "{NIRGENDS}"  # war 127.0.0.1:')),
    ("Ollama ohne das Modell", "sprachmodell_modell_fehlt",
     lambda o: _ersetzen(o, 'LIVE_MODELL = "gemma4:12b"',
                         'LIVE_MODELL = "gibt-es-nicht:1b"')),
]
for name, kennung, umbau in FAELLE:
    arbeit = Path(tempfile.mkdtemp(prefix="devarenu-modell-",
                                   dir=WURZEL / ".tmp"))
    lauf = None
    try:
        arbeitskopie(arbeit)
        umbau(arbeit)
        lauf = server_starten(arbeit, PORT, warten=60)
        status, roh = rufen(PORT, "/api/zustand")
        pruefe(f"{name}: der Server ist oben", 200, status)
        d = json.loads(roh) if status == 200 else {}
        b = [x for x in d.get("befunde", []) if x["kennung"] == kennung]
        pruefe(f"{name}: das Pult nennt es ({kennung})", 1, len(b))
        pruefe(f"{name}: als schwer", True, bool(b and b[0]["schwer"]))
        pruefe(f"{name}: das Pult selbst kommt", 200, rufen(PORT, "/pult")[0])
    finally:
        server_stoppen(lauf)
        shutil.rmtree(arbeit, ignore_errors=True)

titel("3) Der Server mit llama-server")
arbeit = Path(tempfile.mkdtemp(prefix="devarenu-modell-", dir=WURZEL / ".tmp"))
lauf = None
try:
    arbeitskopie(arbeit)
    llama_umlenken(arbeit, LLAMA)
    lauf = server_starten(arbeit, PORT, warten=60)
    status, roh = rufen(PORT, "/api/zustand")
    d = json.loads(roh) if status == 200 else {}
    pruefe("/api/zustand nennt llama-server",
           {"art": "llama-server", "modell": "gemma4-12b", "grund": ""},
           d.get("sprachmodell"))
    # Nur die Lage zur Laufzeit; ob ein Dienst eingeschaltet ist
    # (sprachmodell_dienst*), haengt am Rechner und steht in Teil 4.
    pruefe("kein Befund zur Lage des Sprachmodells", [],
           [x["kennung"] for x in d.get("befunde", [])
            if x["kennung"].startswith("sprachmodell_")
            and not x["kennung"].startswith("sprachmodell_dienst")])
finally:
    server_stoppen(lauf)
    shutil.rmtree(arbeit, ignore_errors=True)

titel("4) Systemcheck: Dienst und Grafikspeicher (B5)")
import systemcheck  # noqa: E402

NVSMI = str(WURZEL / "pruefstand/attrappen/nvidia-smi")
os.environ["DEVARENU_NVIDIA_SMI"] = NVSMI
# Ollama 0.32 rechnet in einem Prozess, der selbst "llama-server" heisst.
OLLAMA_LAEUFER = "5100, /usr/local/lib/ollama/llama-server, 10762\\n"
EIGENER = "5200, /usr/bin/llama-server, 9628\\n"
for name, ausgabe, erwartet in (
        ("nur Ollama (Laeufer heisst llama-server)", OLLAMA_LAEUFER,
         [("ollama", 5100, 10762)]),
        ("nur llama-server", EIGENER, [("llama-server", 5200, 9628)]),
        ("beide", OLLAMA_LAEUFER + EIGENER,
         [("ollama", 5100, 10762), ("llama-server", 5200, 9628)])):
    os.environ["NVSMI_AUSGABE"] = ausgabe
    pruefe(f"{name}: richtig zugeordnet", erwartet,
           sprachmodell.auf_der_karte(NVSMI))
    befunde = []
    systemcheck._zwei_sprachmodelle(befunde)
    pruefe(f"{name}: Befund zwei_sprachmodelle", name == "beide",
           any(b.kennung == "zwei_sprachmodelle" for b in befunde))

alt_dienst = systemcheck._dienst_an
for name, lagen, erwartet in (
        ("llama-server laeuft, Ollama aus",
         {"devarenu-llama": (True, True), "ollama": (False, False)}, []),
        ("Ollama laeuft (Rostock)",
         {"devarenu-llama": (False, False), "ollama": (True, True)}, []),
        ("keiner eingeschaltet",
         {"devarenu-llama": (False, False), "ollama": (False, False)},
         ["sprachmodell_dienst"]),
        ("eingeschaltet, aber tot",
         {"devarenu-llama": (False, True), "ollama": (False, False)},
         ["sprachmodell_dienst_tot"])):
    systemcheck._dienst_an = lambda n, _l=lagen: _l.get(n, (False, False))
    befunde = []
    systemcheck._sprachmodell_dienst(befunde)
    pruefe(f"Dienst: {name}", erwartet, [b.kennung for b in befunde])
systemcheck._dienst_an = alt_dienst

print()
if FEHLER:
    print(f"{FEHLER} FEHLER")
    sys.exit(1)
print("Alles in Ordnung.")
