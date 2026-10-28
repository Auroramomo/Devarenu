#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Der Sprachmodell-Server: llama-server oder Ollama (0.5.2, 28.10.2026).

Bis hierher sprach Devarenu nur mit Ollama. Kuenftig laeuft die
Uebersetzung ueber llama-server (llama.cpp); Ollama soll weiter gehen,
solange ein Rechner es noch hat -- Rostock zum Beispiel. Ein Update
schaltet nichts um: es nimmt, was es vorfindet.

WER GEFRAGT WIRD
----------------
config.SPRACHMODELL_SERVER:

    "auto"          erst llama-server (LLAMA_URL), dann Ollama
                    (OLLAMA_URL). Die Vorgabe. Neue Rechner bekommen
                    llama-server, alte behalten Ollama.
    "llama-server"  nur llama-server
    "ollama"        nur Ollama

Fuer einen einzelnen Rechner ohne Eingriff in config.py (die im Repo
steht) gehen auch Umgebungsvariablen: DEVARENU_SPRACHMODELL,
DEVARENU_LLAMA_URL, DEVARENU_LLAMA_MODELL, DEVARENU_LLAMA_SCHLUESSEL_DATEI.

WIE GEFRAGT WIRD
----------------
llama-server: OpenAI-kompatibel, POST /v1/chat/completions, temperature
0.1, hoechstens 400 Token. Denken AUS ueber chat_template_kwargs
{"enable_thinking": false} -- gemessen am 28.10.2026 mit gemma4 12b
(Q4_K_M): ohne den Zusatz 327 Token Denken und 3,8 s je Satz, mit ihm
22 Token und 0,3 s, reasoning_content leer.

Ollama: weiter POST /api/chat mit "think": false. Ollamas /v1 nimmt kein
chat_template_kwargs; "think" gibt es nur an /api/chat, und genau dort
ist es in Rostock gemessen (0.40.12 denkt ohne es rund 500 Token).
Beide Wege laufen durch dieselbe Bereinigung, der </think>-Schutz bleibt.
"""

import os
import re
from pathlib import Path

import config

LLAMA = "llama-server"
OLLAMA = "ollama"
ARTEN = (LLAMA, OLLAMA)

# Wie lange eine Erkennung je Server warten darf. Ein Server, der
# laeuft, antwortet in Millisekunden; ein toter Port weist sofort ab.
FRIST_ERKENNEN = 2.0


def _env(name, vorgabe):
    w = os.environ.get(name, "").strip()
    return w if w else vorgabe


def wahl():
    """"auto", "llama-server" oder "ollama"."""
    w = _env("DEVARENU_SPRACHMODELL",
             getattr(config, "SPRACHMODELL_SERVER", "auto")).lower()
    return w if w in ARTEN + ("auto",) else "auto"


def llama_url():
    return _env("DEVARENU_LLAMA_URL",
                getattr(config, "LLAMA_URL", "http://127.0.0.1:8091")).rstrip("/")


def llama_modell():
    return _env("DEVARENU_LLAMA_MODELL",
                getattr(config, "LLAMA_MODELL", "gemma4-12b"))


def _llama_schluessel():
    """Ein API-Schluessel, falls der llama-server einen verlangt (etwa ein
    gemeinsam genutzter Router). Auf dem Gemeinde-PC leer: dort lauscht
    llama-server nur auf 127.0.0.1."""
    datei = _env("DEVARENU_LLAMA_SCHLUESSEL_DATEI",
                 getattr(config, "LLAMA_SCHLUESSEL_DATEI", ""))
    if not datei:
        return ""
    try:
        for zeile in Path(datei).read_text(encoding="utf-8").splitlines():
            if zeile.strip() and not zeile.startswith("#"):
                return zeile.strip()
    except OSError:
        pass
    return ""


def _kopf():
    s = _llama_schluessel()
    return {"Authorization": f"Bearer {s}"} if s else {}


def name_des_modells(art):
    return llama_modell() if art == LLAMA else config.LIVE_MODELL


def adresse(art):
    return llama_url() if art == LLAMA else config.OLLAMA_URL.rstrip("/")


# ------------------------------------------------------------ Erkennen

def _llama_lage(requests):
    """None, wenn dort kein llama-server antwortet. Sonst ein dict."""
    url = llama_url()
    try:
        a = requests.get(f"{url}/health", timeout=FRIST_ERKENNEN,
                         headers=_kopf())
    except Exception:
        return None
    if a.status_code == 503:
        # llama-server antwortet waehrend des Ladens mit 503.
        return {"art": LLAMA, "adresse": url, "bereit": False,
                "modell_da": None, "grund": "laedt"}
    if a.status_code == 401:
        return {"art": LLAMA, "adresse": url, "bereit": False,
                "modell_da": None, "grund": "schluessel"}
    if a.status_code != 200:
        return None
    modelle = []
    try:
        m = requests.get(f"{url}/v1/models", timeout=FRIST_ERKENNEN,
                         headers=_kopf())
        if m.ok:
            modelle = [str(x.get("id", "")) for x in m.json().get("data", [])]
    except Exception:
        pass
    gesucht = llama_modell()
    # Ein einzelner llama-server traegt genau ein Modell und nimmt
    # jeden Namen an; erst ein Router mit mehreren muss den richtigen
    # haben.
    da = (gesucht in modelle) or len(modelle) == 1
    return {"art": LLAMA, "adresse": url, "bereit": True,
            "modell_da": da, "modelle": modelle,
            "grund": "" if da else "modell_fehlt"}


def _ollama_lage(requests):
    url = config.OLLAMA_URL.rstrip("/")
    try:
        a = requests.get(f"{url}/api/tags", timeout=FRIST_ERKENNEN)
    except Exception:
        return None
    if not a.ok:
        return None
    try:
        namen = [m.get("name", "") for m in a.json().get("models", [])]
    except Exception:
        namen = []
    gesucht = config.LIVE_MODELL
    da = any(n == gesucht or n == f"{gesucht}:latest" for n in namen)
    return {"art": OLLAMA, "adresse": url, "bereit": True,
            "modell_da": da, "modelle": namen,
            "grund": "" if da else "modell_fehlt"}


def erkennen(requests=None):
    """Welcher Sprachmodell-Server antwortet? Immer ein dict:

    {"art": "llama-server"|"ollama"|"", "adresse", "bereit",
     "modell_da", "modell", "grund"}

    grund: ""             alles da
           "keiner"       weder llama-server noch Ollama antwortet
           "laedt"        llama-server laedt noch das Modell
           "schluessel"   llama-server verlangt einen API-Schluessel
           "modell_fehlt" der Server antwortet, das Modell fehlt
    """
    if requests is None:
        import requests
    w = wahl()
    reihe = {"auto": (LLAMA, OLLAMA), LLAMA: (LLAMA,),
             OLLAMA: (OLLAMA,)}[w]
    for art in reihe:
        lage = (_llama_lage if art == LLAMA else _ollama_lage)(requests)
        if lage is not None:
            lage["modell"] = name_des_modells(art)
            lage["wahl"] = w
            return lage
    return {"art": "", "adresse": " / ".join(adresse(a) for a in reihe),
            "bereit": False, "modell_da": None, "modell": "",
            "grund": "keiner", "wahl": w}


def beschreiben(lage):
    """Ein Satz fuer Startausgabe und Journal."""
    art, grund = lage.get("art"), lage.get("grund")
    if grund == "keiner":
        return (f"Kein Sprachmodell-Server antwortet ({lage['adresse']}). "
                f"Der Server laeuft weiter, aber ohne Uebersetzung.")
    if grund == "laedt":
        return f"{art} auf {lage['adresse']} laedt noch das Modell."
    if grund == "schluessel":
        return (f"{art} auf {lage['adresse']} verlangt einen API-Schluessel "
                f"(DEVARENU_LLAMA_SCHLUESSEL_DATEI).")
    if grund == "modell_fehlt":
        return (f"{art} auf {lage['adresse']} antwortet, aber das Modell "
                f"{lage['modell']} fehlt dort.")
    return f"{art} auf {lage['adresse']}, Modell {lage['modell']}"


# ------------------------------------------------------------- Fragen

def bereinigen(t):
    """Wie seit jeher: ein Denkblock, der doch durchrutscht, faellt weg;
    Markdown-Sternchen und Anfuehrungszeichen aussen herum auch."""
    t = t or ""
    if "</think>" in t:
        t = t.split("</think>", 1)[1]
    return re.sub(r"[*`]+", "", t).strip().strip('"').strip()


def anfrage(art, system, text):
    """(adresse, json, kopf) fuer einen Uebersetzungsaufruf."""
    nachrichten = [{"role": "system", "content": system},
                   {"role": "user", "content": text}]
    if art == LLAMA:
        return (f"{llama_url()}/v1/chat/completions",
                {"model": llama_modell(), "stream": False,
                 "temperature": 0.1, "max_tokens": 400,
                 "chat_template_kwargs": {"enable_thinking": False},
                 "messages": nachrichten},
                _kopf())
    return (f"{config.OLLAMA_URL.rstrip('/')}/api/chat",
            {"model": config.LIVE_MODELL, "stream": False, "think": False,
             "options": {"temperature": 0.1, "num_predict": 400},
             "messages": nachrichten},
            {})


def antwort_lesen(art, daten):
    if art == LLAMA:
        return daten["choices"][0]["message"].get("content") or ""
    return daten["message"]["content"]


def fragen(art, system, text, requests, timeout=30):
    """Ein Uebersetzungsaufruf. Die Antwort bereinigt."""
    url, rumpf, kopf = anfrage(art, system, text)
    a = requests.post(url, json=rumpf, headers=kopf, timeout=timeout)
    a.raise_for_status()
    return bereinigen(antwort_lesen(art, a.json()))


# ---------------------------------------------------- Grafikspeicher

def auf_der_karte(nvidia_smi="nvidia-smi"):
    """Welche Sprachmodell-Server gerade Grafikspeicher halten.

    [(art, pid, MiB), ...] aus nvidia-smi. Leer, wenn es keine Karte
    oder kein nvidia-smi gibt.

    Erkannt am VOLLEN Pfad, nicht am Programmnamen: Ollama rechnet in
    einem eigenen Prozess, und der heisst seit einigen Fassungen selbst
    "llama-server" (gemessen 28.10.2026, Ollama 0.32.15:
    /usr/local/lib/ollama/llama-server). Steht "ollama" irgendwo im
    Pfad, gehoert er zu Ollama; sonst ist ein "llama-server" ein
    eigener."""
    import subprocess
    try:
        a = subprocess.run(
            [nvidia_smi, "--query-compute-apps=pid,process_name,used_memory",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
            stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return []
    funde = []
    for zeile in a.stdout.splitlines():
        teile = [t.strip() for t in zeile.split(",")]
        if len(teile) < 3:
            continue
        pid, pfad, mib = teile[0], teile[1], teile[2]
        art = (OLLAMA if "ollama" in pfad.lower() else
               LLAMA if Path(pfad).name.startswith("llama-server") else "")
        if art:
            try:
                funde.append((art, int(pid), int(float(mib))))
            except ValueError:
                funde.append((art, 0, 0))
    return funde
