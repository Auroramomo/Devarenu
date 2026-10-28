#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""llama-server einrichten -- der Umstieg von Ollama (0.5.2, 28.10.2026).

    sudo .venv/bin/python llama_einrichten.py [--frist SEKUNDEN]

Aufgerufen von aktualisierung.sh am Ende jedes Updates (Netz, Stick,
Fenster, von Hand) und von  sudo bash dienst.sh --llama.

WAS GESCHIEHT
-------------
1. Schon fertig? Unit da und unveraendert, llama-server laeuft und
   uebersetzt, Ollama aus -- dann nichts.
2. Archiv und CUDA-Laufzeit (ggml-org, Build config.LLAMA_BUILD) liegen
   unter sprachmodell/ oder werden geladen; sha256 gegen teile.json.
   Ausgepackt nach /opt/devarenu-llama/<build>.
3. Das Modell (gemma4 12b Q4_K_M) liegt unter sprachmodell/ -- vom
   Stick, sonst aus der Ollama-Ablage (Blob nach sha256 gepruft, per
   cp --reflink=auto, auf btrfs ohne Platz), sonst geladen.
4. Unit devarenu-llama aus der Vorlage, nur 127.0.0.1.
5. PROBE: Ollama vorueber anhalten (sein Modell gibt den Grafikspeicher
   frei), llama-server starten, ein echter Uebersetzungsaufruf mit
   abgeschaltetem Denken, Grafikspeicher mit Whisper unter 16 GB.
6. Besteht die Probe: llama-server einschalten, Ollama abschalten (nicht
   deinstallieren), Devarenu neu starten. Besteht sie nicht:
   llama-server aus, Ollama wieder an, wie es war -- und der Grund steht
   in update/llama-lage.json, im Protokoll, am Pult und in der Meldung.

NIE TOEDLICH
------------
Rueckgabe 0: eingerichtet (oder war es schon). 1: nicht eingerichtet,
Grund in der letzten Zeile. 2: uebersprungen (kein Netz, Teile fehlen).
aktualisierung.sh wertet KEINE davon als Fehlschlag des Updates.

Die letzte Zeile beginnt immer mit "ERGEBNIS|" und ist ein Satz fuer
Menschen: eingerichtet ja/nein, Grund, welcher Server jetzt uebersetzt,
Tempo der Probe.

ZEITGRENZEN
-----------
--frist (Vorgabe 2700 s) fuer alles zusammen. Jeder Download liest mit
einer Frist von 60 s je Block -- ein Gastzugang, der abreisst, haengt
nicht, sondern wird nach 10 s mit Range fortgesetzt, bis die Frist um
ist.

NAEHTE FUER PRUEFSTAENDE (Umgebung)
-----------------------------------
DEVARENU_LLAMA_OPT, DEVARENU_LLAMA_ORDNER, DEVARENU_UNIT_ORDNER,
DEVARENU_LLAMA_UNIT, DEVARENU_SYSTEMCTL, DEVARENU_NVIDIA_SMI,
DEVARENU_LLAMA_QUELLEN (JSON-Datei name -> Adresse),
DEVARENU_LLAMA_OHNE_ROOT=1, DEVARENU_LLAMA_BENUTZERUNIT=1 (Unit fuer
systemctl --user: ohne User= und SupplementaryGroups=).
"""

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path

BASIS = Path(__file__).resolve().parent
sys.path.insert(0, str(BASIS))

import config  # noqa: E402
import sprachmodell  # noqa: E402

BLOCK = 1 << 20
LESE_FRIST = 60          # Sekunden ohne ein Byte -> abgerissen
PAUSE_NACH_ABRISS = int(os.environ.get("DEVARENU_LLAMA_PAUSE") or 10)
GESUNDHEIT_FRIST = 180   # bis llama-server das Modell geladen hat
VRAM_GRENZE_MIB = 16 * 1024
# Whisper large-v3-turbo float16, gemessen am 28.10.2026: 2356 MiB.
# Gilt, wenn Devarenu gerade nicht auf der Karte steht.
WHISPER_MIB_SCHAETZUNG = 2400

PROBE_SYSTEM = ("Du bist Fachuebersetzer fuer christliche Predigttexte. "
                "Uebersetze den Abschnitt von Deutsch nach Englisch.\n"
                "Regeln:\n- Gib ausschliesslich die Uebersetzung aus. "
                "Keine Erklaerung, keine Anfuehrungszeichen, kein Markdown.")
PROBE_TEXT = ("Und Jesus sprach zu ihnen: Ich bin das Brot des Lebens. Wer "
              "zu mir kommt, den wird nicht hungern.")


def _env(name, vorgabe):
    w = os.environ.get(name, "").strip()
    return w if w else vorgabe


OPT = Path(_env("DEVARENU_LLAMA_OPT", config.LLAMA_OPT))
ORDNER = Path(_env("DEVARENU_LLAMA_ORDNER", str(config.LLAMA_ORDNER)))
UNIT_ORDNER = Path(_env("DEVARENU_UNIT_ORDNER", "/etc/systemd/system"))
UNIT = _env("DEVARENU_LLAMA_UNIT", "devarenu-llama")
SYSTEMCTL = _env("DEVARENU_SYSTEMCTL", "systemctl").split()
NVIDIA_SMI = _env("DEVARENU_NVIDIA_SMI", "nvidia-smi")
BENUTZERUNIT = os.environ.get("DEVARENU_LLAMA_BENUTZERUNIT") == "1"
LAGE = BASIS / "update" / "llama-lage.json"


class Abbruch(Exception):
    """Ein Grund, nicht einzurichten. str() ist der Satz fuer Menschen."""


class Uebersprungen(Abbruch):
    pass


def sag(text):
    print(f"   {text}", flush=True)


# --------------------------------------------------------- Hilfsmittel

def benutzer():
    """Wem der Projektordner gehoert: dem gehoert auch sprachmodell/."""
    st = BASIS.stat()
    return st.st_uid, st.st_gid


def uebergeben(pfad):
    """Was als root unter dem Projektordner entsteht, gehoert danach dem
    Dienstbenutzer -- sonst kann llama-server das Modell nicht lesen."""
    if os.geteuid() != 0:
        return
    uid, gid = benutzer()
    try:
        os.chown(pfad, uid, gid)
    except OSError:
        pass


def quellen():
    datei = os.environ.get("DEVARENU_LLAMA_QUELLEN")
    if datei:
        return json.loads(Path(datei).read_text(encoding="utf-8"))
    return dict(config.LLAMA_QUELLEN)


def teil(name):
    """Groesse und sha256 aus teile.json (Art "llama")."""
    d = json.loads((BASIS / "teile.json").read_text(encoding="utf-8"))
    for e in d.get("teile", []):
        if e.get("art") == "llama" and e.get("pfad") == name:
            return e
    raise Abbruch(f"{name} steht nicht in teile.json")


def sha256(pfad, frist_ende=None):
    h = hashlib.sha256()
    with open(pfad, "rb") as f:
        for b in iter(lambda: f.read(BLOCK * 8), b""):
            h.update(b)
            if frist_ende and time.time() > frist_ende:
                raise Abbruch("Zeitgrenze beim Pruefen der sha256 erreicht")
    return h.hexdigest()


_STEMPEL = None


def _stempel_datei():
    return ORDNER / ".pruefsummen.json"


def stimmt(pfad, e, frist_ende=None):
    """Liegt die Datei da, mit Groesse und sha256 aus teile.json?
    Einmal gerechnet wird gemerkt (Groesse + Aenderungszeit): ein zweiter
    Lauf rechnet 7 GB nicht noch einmal."""
    global _STEMPEL
    p = Path(pfad)
    if not p.is_file() or p.stat().st_size != e["bytes"]:
        return False
    if _STEMPEL is None:
        try:
            _STEMPEL = json.loads(_stempel_datei().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _STEMPEL = {}
    st = p.stat()
    kennung = f"{st.st_size}:{st.st_mtime_ns}"
    if _STEMPEL.get(str(p)) == [kennung, e["sha256"]]:
        return True
    if sha256(p, frist_ende) != e["sha256"]:
        return False
    stempel_setzen(p, e)
    return True


def stempel_setzen(p, e):
    """Merkt sich: diese Datei (Groesse, Aenderungszeit) hat diese sha256."""
    global _STEMPEL
    if _STEMPEL is None:
        try:
            _STEMPEL = json.loads(_stempel_datei().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _STEMPEL = {}
    st = Path(p).stat()
    _STEMPEL[str(p)] = [f"{st.st_size}:{st.st_mtime_ns}", e["sha256"]]
    try:
        ORDNER.mkdir(parents=True, exist_ok=True)
        _stempel_datei().write_text(json.dumps(_STEMPEL), encoding="utf-8")
        uebergeben(_stempel_datei())
    except OSError:
        pass


def systemctl(*args, pruefen=False):
    a = subprocess.run(SYSTEMCTL + list(args), capture_output=True,
                       text=True, timeout=180, stdin=subprocess.DEVNULL)
    if pruefen and a.returncode != 0:
        raise Abbruch(f"systemctl {' '.join(args)} scheiterte: "
                      f"{(a.stderr or a.stdout).strip()[:120]}")
    return a


def aktiv(unit):
    return systemctl("is-active", "--quiet", unit).returncode == 0


def eingeschaltet(unit):
    return systemctl("is-enabled", "--quiet", unit).returncode == 0


# ------------------------------------------------------------ Laden

def internet_da(url):
    import urllib.request
    import urllib.error
    # Wie in teile.py: der Pruefstand sagt ausdruecklich "kein Netz" --
    # er soll den Weg ohne Netz pruefen und nicht 8 GB laden.
    if os.environ.get("DEVARENU_KEIN_NETZ"):
        return False
    try:
        urllib.request.urlopen(urllib.request.Request(url, method="HEAD"),
                               timeout=15).close()
        return True
    except urllib.error.HTTPError:
        return True
    except Exception:
        return False


def holen(name, e, frist_ende):
    """Laedt name nach sprachmodell/, setzt nach Abriss mit Range fort."""
    import urllib.request
    import urllib.error
    url = quellen().get(name)
    if not url:
        raise Abbruch(f"keine Quelle fuer {name}")
    ziel = ORDNER / name
    halb = ORDNER / (name + ".halb")
    ORDNER.mkdir(parents=True, exist_ok=True)
    uebergeben(ORDNER)
    versuch = 0
    while True:
        versuch += 1
        if time.time() > frist_ende:
            raise Abbruch(f"Zeitgrenze erreicht beim Laden von {name} "
                          f"({halb.stat().st_size // 10**6 if halb.exists() else 0}"
                          f" von {e['bytes'] // 10**6} MB)")
        schon = halb.stat().st_size if halb.exists() else 0
        if schon > e["bytes"]:
            halb.unlink()
            schon = 0
        if schon == e["bytes"]:
            break
        bitte = urllib.request.Request(url)
        if schon:
            bitte.add_header("Range", f"bytes={schon}-")
        try:
            with urllib.request.urlopen(bitte, timeout=LESE_FRIST) as a:
                if schon and a.status != 206:
                    # Der Server setzt nicht fort: von vorn.
                    schon = 0
                with open(halb, "ab" if schon else "wb") as f:
                    while True:
                        b = a.read(BLOCK)
                        if not b:
                            break
                        f.write(b)
                        if time.time() > frist_ende:
                            break
            if halb.stat().st_size >= e["bytes"]:
                break
            raise OSError("Verbindung endete vor dem Ende der Datei")
        except urllib.error.HTTPError as f:
            if f.code == 416 and halb.exists() and \
                    halb.stat().st_size == e["bytes"]:
                break
            if f.code in (404, 403, 401):
                raise Abbruch(f"{name}: die Quelle antwortet {f.code}")
            grund = f"HTTP {f.code}"
        except Exception as f:          # noqa: BLE001 -- jeder Abriss
            grund = f"{type(f).__name__}: {str(f)[:80]}"
        jetzt = halb.stat().st_size if halb.exists() else 0
        sag(f"{name}: abgerissen bei {jetzt // 10**6} von "
            f"{e['bytes'] // 10**6} MB ({grund}), Versuch {versuch}; "
            f"weiter in {PAUSE_NACH_ABRISS} s")
        time.sleep(PAUSE_NACH_ABRISS)
    if sha256(halb, frist_ende) != e["sha256"]:
        halb.unlink(missing_ok=True)
        raise Abbruch(f"{name}: geladen, aber die sha256 stimmt nicht")
    os.replace(halb, ziel)
    uebergeben(ziel)
    sag(f"{name}: geladen, sha256 stimmt")


def bereitstellen(name, frist_ende, ollama_blob=None):
    """Sorgt dafuer, dass sprachmodell/<name> stimmt. Zurueck: woher."""
    e = teil(name)
    ziel = ORDNER / name
    if stimmt(ziel, e, frist_ende):
        return "lag schon da"
    if ollama_blob and Path(ollama_blob).is_file() and \
            Path(ollama_blob).stat().st_size == e["bytes"]:
        sag(f"{name}: aus der Ollama-Ablage, sha256 wird geprueft ...")
        if sha256(ollama_blob, frist_ende) != e["sha256"]:
            sag(f"{name}: der Ollama-Blob hat eine andere sha256 -- "
                f"nicht genommen")
        else:
            ORDNER.mkdir(parents=True, exist_ok=True)
            uebergeben(ORDNER)
            halb = ORDNER / (name + ".halb")
            frei = shutil.disk_usage(ORDNER).free
            r = subprocess.run(["cp", "--reflink=always", str(ollama_blob),
                                str(halb)], capture_output=True)
            if r.returncode != 0:
                # Kein reflink (anderes Dateisystem): eine echte Kopie.
                if frei < e["bytes"] * 1.05 + 500e6:
                    raise Abbruch(
                        f"zu wenig Platz fuer eine Kopie des Modells "
                        f"({frei / 1e9:.1f} GB frei, gebraucht "
                        f"{e['bytes'] / 1e9:.1f} GB)")
                rest = max(60, frist_ende - time.time())
                try:
                    subprocess.run(["cp", str(ollama_blob), str(halb)],
                                   check=True, timeout=rest)
                except (subprocess.SubprocessError, OSError) as f:
                    halb.unlink(missing_ok=True)
                    raise Abbruch(f"Kopie aus der Ollama-Ablage scheiterte "
                                  f"({type(f).__name__})")
                wie = "kopiert"
            else:
                wie = "per reflink, ohne Platz"
            os.chmod(halb, 0o644)
            if halb.stat().st_size != e["bytes"]:
                halb.unlink(missing_ok=True)
                raise Abbruch(f"{name}: die Kopie hat die falsche Groesse")
            os.replace(halb, ziel)
            uebergeben(ziel)
            # Die Quelle ist gerade gegen teile.json geprueft, cp hat
            # Byte fuer Byte kopiert: nicht noch einmal 7 GB rechnen.
            stempel_setzen(ziel, e)
            return f"aus der Ollama-Ablage ({wie})"
    url = quellen().get(name, "")
    if not internet_da(url):
        nvidia = (" -- die CUDA-Laufzeit von NVIDIA liegt mit Absicht "
                  "nicht im oeffentlichen Update-ZIP"
                  if name == config.LLAMA_CUDART else "")
        raise Uebersprungen(
            f"kein Internet, und {name} liegt weder hier noch auf einem "
            f"Stick{nvidia}")
    holen(name, e, frist_ende)
    return "geladen"


def ollama_blob(name):
    """Der Blob mit derselben sha256 in der Ollama-Ablage, oder None."""
    try:
        e = teil(name)
        import systemcheck
        ablage = systemcheck.ollama_ablage()
    except Exception:
        return None
    if not ablage:
        return None
    p = Path(ablage) / "blobs" / f"sha256-{e['sha256']}"
    return p if p.is_file() else None


# ------------------------------------------------------ Installieren

def zielordner():
    return OPT / config.LLAMA_BUILD


def installiert():
    z = zielordner()
    try:
        stempel = json.loads((z / ".devarenu-quelle.json").read_text())
    except (OSError, ValueError):
        return False
    soll = {n: teil(n)["sha256"] for n in (config.LLAMA_ARCHIV,
                                            config.LLAMA_CUDART)}
    return stempel == soll and (z / "llama-server").is_file()


def installieren():
    """Packt Archiv und CUDA-Laufzeit in EINEN Ordner aus: llama-server
    sucht seine Bibliotheken neben sich (RUNPATH $ORIGIN)."""
    z = zielordner()
    neu = OPT / (config.LLAMA_BUILD + ".neu")
    shutil.rmtree(neu, ignore_errors=True)
    neu.mkdir(parents=True)
    for name in (config.LLAMA_ARCHIV, config.LLAMA_CUDART):
        with tarfile.open(ORDNER / name) as t:
            t.extractall(neu / "auspack", filter="data")
        # Je Archiv ein Oberordner; sein Inhalt kommt nach oben.
        for ober in (neu / "auspack").iterdir():
            quelle = ober if ober.is_dir() else (neu / "auspack")
            for x in quelle.iterdir():
                shutil.move(str(x), str(neu / x.name))
            if ober.is_dir():
                ober.rmdir()
        shutil.rmtree(neu / "auspack", ignore_errors=True)
    (neu / ".devarenu-quelle.json").write_text(json.dumps(
        {n: teil(n)["sha256"] for n in (config.LLAMA_ARCHIV,
                                         config.LLAMA_CUDART)}))
    for p in [neu] + list(neu.rglob("*")):
        os.chmod(p, 0o755 if p.is_dir() or os.access(p, os.X_OK) else 0o644)
    if z.exists():
        shutil.rmtree(z)
    os.replace(neu, z)
    verweis = OPT / "aktuell"
    tmp = OPT / "aktuell.neu"
    tmp.unlink(missing_ok=True)
    tmp.symlink_to(z.name)
    os.replace(tmp, verweis)


def programm_pruefen():
    exe = OPT / "aktuell" / "llama-server"
    try:
        v = subprocess.run([str(exe), "--version"], capture_output=True,
                           text=True, timeout=60)
        g = subprocess.run([str(exe), "--list-devices"], capture_output=True,
                           text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as f:
        raise Abbruch(f"llama-server laesst sich nicht starten "
                      f"({type(f).__name__})")
    text = v.stdout + v.stderr
    if f"build {config.LLAMA_BUILD.lstrip('b')}" not in text:
        raise Abbruch(f"llama-server meldet nicht Build {config.LLAMA_BUILD}: "
                      f"{text.strip()[:100]}")
    if "CUDA" not in (g.stdout + g.stderr):
        raise Abbruch("llama-server sieht keine NVIDIA-Grafikkarte "
                      "(Treiber? libcuda?)")


# --------------------------------------------------------------- Unit

def unit_text():
    vorlage = (BASIS / "devarenu-llama.service.vorlage").read_text(
        encoding="utf-8")
    url = sprachmodell.llama_url()
    port = url.rsplit(":", 1)[1].split("/")[0]
    import pwd
    name = pwd.getpwuid(benutzer()[0]).pw_name
    text = (vorlage.replace("@BENUTZER@", name)
            .replace("@LLAMA_SERVER@", str(OPT / "aktuell" / "llama-server"))
            .replace("@GGUF@", str(ORDNER / config.LLAMA_GGUF_NAME))
            .replace("@LLAMA_PORT@", port))
    if BENUTZERUNIT:
        zeilen = [z for z in text.splitlines()
                  if not z.startswith(("User=", "SupplementaryGroups="))]
        text = "\n".join(zeilen).replace("WantedBy=multi-user.target",
                                         "WantedBy=default.target") + "\n"
    return text


def unit_schreiben():
    datei = UNIT_ORDNER / f"{UNIT}.service"
    text = unit_text()
    try:
        alt = datei.read_text(encoding="utf-8")
    except OSError:
        alt = None
    if alt == text:
        return False
    UNIT_ORDNER.mkdir(parents=True, exist_ok=True)
    datei.write_text(text, encoding="utf-8")
    os.chmod(datei, 0o644)
    systemctl("daemon-reload")
    return True


# -------------------------------------------------------------- Probe

def karte():
    """[(pid, pfad, MiB)], belegt MiB, gesamt MiB -- oder None ohne Karte."""
    try:
        a = subprocess.run(
            [NVIDIA_SMI, "--query-compute-apps=pid,process_name,used_memory",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10)
        g = subprocess.run(
            [NVIDIA_SMI, "--query-gpu=memory.used,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    prozesse = []
    for z in a.stdout.splitlines():
        t = [x.strip() for x in z.split(",")]
        if len(t) >= 3:
            try:
                prozesse.append((int(t[0]), t[1], int(float(t[2]))))
            except ValueError:
                pass
    try:
        belegt, gesamt = (int(float(x)) for x in
                          g.stdout.strip().splitlines()[0].split(","))
    except (ValueError, IndexError):
        belegt = gesamt = 0
    return prozesse, belegt, gesamt


def hauptpid(unit):
    a = systemctl("show", "-p", "MainPID", "--value", unit)
    try:
        return int(a.stdout.strip() or 0)
    except ValueError:
        return 0


def probe(frist_ende):
    """Der echte Aufruf. Zurueck ein dict; "ok" sagt, ob er besteht."""
    import requests
    url = sprachmodell.llama_url()
    ende = min(frist_ende, time.time() + GESUNDHEIT_FRIST)
    while True:
        try:
            if requests.get(f"{url}/health", timeout=5).status_code == 200:
                break
        except Exception:
            pass
        if time.time() > ende:
            return {"ok": False, "grund": "llama-server kam nicht hoch "
                    f"(kein /health in {GESUNDHEIT_FRIST} s)"}
        time.sleep(2)
    adresse, rumpf, kopf = sprachmodell.anfrage(
        sprachmodell.LLAMA, PROBE_SYSTEM, PROBE_TEXT)
    t0 = time.perf_counter()
    try:
        a = requests.post(adresse, json=rumpf, headers=kopf, timeout=120)
        a.raise_for_status()
        d = a.json()
    except Exception as f:
        return {"ok": False, "grund": f"Uebersetzungsaufruf scheiterte "
                f"({type(f).__name__}: {str(f)[:80]})"}
    dauer = time.perf_counter() - t0
    m = (d.get("choices") or [{}])[0].get("message") or {}
    text = sprachmodell.bereinigen(m.get("content") or "")
    gedacht = (m.get("reasoning_content") or "").strip()
    token = (d.get("usage") or {}).get("completion_tokens")
    tempo = (d.get("timings") or {}).get("predicted_per_second")
    erg = {"text": text, "s": round(dauer, 2), "token": token,
           "token_s": round(tempo, 1) if tempo else None}
    if not text:
        return dict(erg, ok=False, grund="die Probe kam leer zurueck")
    if gedacht or "</think>" in (m.get("content") or ""):
        return dict(erg, ok=False, grund="das Modell denkt trotz "
                    "abgeschaltetem Denken")
    if token and token > 120:
        return dict(erg, ok=False, grund=f"zu lange Antwort ({token} Token) "
                    f"-- nicht nur die Uebersetzung")
    # Grafikspeicher: llama-server plus Whisper (Devarenu).
    k = karte()
    if k is not None:
        prozesse, belegt, gesamt = k
        # Ueber die Haupt-PID der Unit: auf einem Rechner kann daneben ein
        # anderer llama-server laufen (Ollamas Laeufer heisst auch so).
        eigen = hauptpid(f"{UNIT}.service")
        llama = sum(m for p, pfad, m in prozesse if p == eigen) if eigen \
            else sum(m for p, pfad, m in prozesse
                     if Path(pfad).name.startswith("llama-server")
                     and "ollama" not in pfad.lower())
        dev = hauptpid("devarenu")
        whisper = next((m for p, _pf, m in prozesse if p == dev and dev), None)
        geschaetzt = whisper is None
        summe = llama + (WHISPER_MIB_SCHAETZUNG if geschaetzt else whisper)
        erg.update(llama_mib=llama, whisper_mib=whisper,
                   summe_mib=summe, whisper_geschaetzt=geschaetzt,
                   karte_belegt=belegt, karte_gesamt=gesamt)
        if summe >= VRAM_GRENZE_MIB or (gesamt and belegt > gesamt):
            return dict(erg, ok=False, grund=f"Grafikspeicher zu knapp: "
                        f"llama-server {llama} MB + Whisper "
                        f"{summe - llama} MB = {summe} MB")
    return dict(erg, ok=True, grund="")


def uebersetzt_gerade():
    port = os.environ.get("DEVARENU_PORT", "8000")
    try:
        import requests
        return bool(requests.get(f"http://127.0.0.1:{port}/api/zustand",
                                 timeout=5).json().get("live"))
    except Exception:
        return False


# ---------------------------------------------------------- Ablauf

def schon_fertig(frist_ende):
    datei = UNIT_ORDNER / f"{UNIT}.service"
    try:
        if datei.read_text(encoding="utf-8") != unit_text():
            return None
    except OSError:
        return None
    if not installiert() or not aktiv(UNIT) or aktiv("ollama"):
        return None
    p = probe(frist_ende)
    return p if p.get("ok") else None


def satz_tempo(p):
    teile = [f"{p['s']} s"]
    if p.get("token_s"):
        teile.append(f"{p['token_s']} Token/s")
    if p.get("summe_mib"):
        teile.append(f"Grafikspeicher mit Whisper {p['summe_mib'] / 1024:.1f}"
                     f" GB{' (Whisper geschaetzt)' if p.get('whisper_geschaetzt') else ''}")
    return ", ".join(teile)


def einrichten(frist_ende):
    """Zurueck (rueckgabe, satz, lage-dict)."""
    p = schon_fertig(frist_ende)
    if p:
        return 0, (f"llama-server war schon eingerichtet und uebersetzt "
                   f"(Probe: {satz_tempo(p)})."), {"schon": True, "probe": p}

    sag("Programm (ggml-org, Build " + config.LLAMA_BUILD + ")")
    for name in (config.LLAMA_ARCHIV, config.LLAMA_CUDART):
        sag(f"{name}: {bereitstellen(name, frist_ende)}")
    if not installiert():
        installieren()
        sag(f"ausgepackt nach {zielordner()}")
    programm_pruefen()
    sag("llama-server startet und sieht die Grafikkarte")

    name = config.LLAMA_GGUF_NAME
    sag(f"Modell {name}: {bereitstellen(name, frist_ende, ollama_blob(name))}")

    if unit_schreiben():
        sag(f"Unit {UNIT}.service geschrieben (nur 127.0.0.1)")

    ollama_war = aktiv("ollama")
    if ollama_war:
        sag("Ollama wird fuer die Probe angehalten (nicht abgeschaltet)")
        systemctl("stop", "ollama")
    try:
        systemctl("restart", f"{UNIT}.service", pruefen=True)
        p = probe(frist_ende)
    except Abbruch as f:
        p = {"ok": False, "grund": str(f)}
    if not p.get("ok"):
        systemctl("stop", f"{UNIT}.service")
        systemctl("disable", f"{UNIT}.service")
        if ollama_war:
            systemctl("start", "ollama")
        raise Abbruch(f"Probe nicht bestanden: {p.get('grund')}")

    systemctl("enable", f"{UNIT}.service", pruefen=True)
    ollama_aus = ""
    if ollama_war or eingeschaltet("ollama"):
        systemctl("disable", "--now", "ollama")
        ollama_aus = " Ollama ist abgeschaltet, nicht deinstalliert."
    if aktiv("devarenu") and not uebersetzt_gerade():
        systemctl("restart", "devarenu")
    return 0, (f"llama-server eingerichtet und uebersetzt jetzt (Build "
               f"{config.LLAMA_BUILD}, gemma4 12b). Probe: {satz_tempo(p)}."
               f"{ollama_aus}"), {"schon": False, "probe": p}


def jetzt_uebersetzt():
    """Welcher Sprachmodell-Server jetzt uebersetzt -- fuer den Satz.
    Zuerst nach den Diensten: die sind eben gestellt worden. Erst ohne
    beide wird gefragt, wer antwortet (ein von Hand gestarteter)."""
    try:
        if aktiv(f"{UNIT}.service"):
            return "llama-server"
        if aktiv("ollama"):
            return "Ollama"
        lage = sprachmodell.erkennen()
        return lage.get("art") or "keiner"
    except Exception:
        return "unbekannt"


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--frist", type=int, default=2700)
    args = a.parse_args(argv)
    frist_ende = time.time() + args.frist
    t0 = time.time()

    if os.geteuid() != 0 and os.environ.get("DEVARENU_LLAMA_OHNE_ROOT") != "1":
        print("ERGEBNIS|llama-server NICHT eingerichtet: das braucht root "
              "(sudo bash dienst.sh --llama).")
        return 1
    # Auf dem Entwicklungsrechner nie: dort laeuft womoeglich ein eigener
    # llama-server oder Ollama fuer anderes, und /opt und /etc gehoeren
    # nicht Devarenu (entwicklung.py: Marke ENTWICKLUNG und Schluessel).
    try:
        import entwicklung
        if entwicklung.ist_entwicklungsrechner():
            print("ERGEBNIS|llama-server NICHT eingerichtet: dies ist der "
                  "Entwicklungsrechner.")
            return 2
    except Exception:
        pass
    ORDNER.mkdir(parents=True, exist_ok=True)
    uebergeben(ORDNER)
    sperre = open(ORDNER / ".einrichten.sperre", "w")
    try:
        fcntl.flock(sperre, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("ERGEBNIS|llama-server: es laeuft schon eine Einrichtung.")
        return 2

    lage = {"zeit": time.strftime("%Y-%m-%d %H:%M:%S"),
            "build": config.LLAMA_BUILD}
    if uebersetzt_gerade():
        rc, satz = 2, ("llama-server NICHT eingerichtet: es wird gerade "
                       "uebersetzt. Beim naechsten Update wieder.")
    else:
        try:
            rc, satz, mehr = einrichten(frist_ende)
            lage.update(mehr)
        except Uebersprungen as f:
            rc, satz = 2, f"llama-server NICHT eingerichtet: {f}."
        except Abbruch as f:
            rc, satz = 1, f"llama-server NICHT eingerichtet: {f}."
        except Exception as f:          # noqa: BLE001 -- nie toedlich
            rc, satz = 1, (f"llama-server NICHT eingerichtet: unerwarteter "
                           f"Fehler ({type(f).__name__}: {str(f)[:100]}).")
    server = jetzt_uebersetzt()
    if rc != 0:
        satz += f" Es uebersetzt weiter: {server}."
    # Der Satz wandert unmaskiert in JSON (stand.json des Sticks,
    # stand-online.json) und in eine Zeile: keine Anfuehrungszeichen,
    # keine Backslashes, kein Zeilenumbruch.
    satz = " ".join(satz.replace('"', "'").replace("\\", "/").split())
    lage.update(eingerichtet=(rc == 0), rueckgabe=rc, satz=satz,
                server=server, dauer_s=round(time.time() - t0))
    try:
        LAGE.parent.mkdir(parents=True, exist_ok=True)
        LAGE.write_text(json.dumps(lage, ensure_ascii=False, indent=1),
                        encoding="utf-8")
        uebergeben(LAGE)
    except OSError:
        pass
    print(f"   Dauer: {round(time.time() - t0)} s")
    print(f"ERGEBNIS|{satz}", flush=True)
    return rc


if __name__ == "__main__":
    sys.exit(main())
