#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kommt ein manipuliertes Wheel durch? (0.5.2, 28.10.2026)

    python pruefstand/wheels_sperre_test.py

Bis 0.5.1 installierte das Update mit
    pip install --no-index --find-links wheels -r requirements.txt
-- der passende Dateiname genuegte. Die Signatur deckt nur das Bundle,
nicht wheels/. Ein manipuliertes ZIP haette eigenen Code einschleusen
koennen. Seit 0.5.2 steht jedes Wheel mit sha256 in pakete.sperre (im
signierten Baum), und installiert wird mit --require-hashes.

Mit echtem pip und zwei kleinen, selbst gebauten Wheels:
  1. die Sperre aus werkzeuge/sperre_schreiben.py, Installation gelingt
  2. dasselbe Wheel, Inhalt veraendert: abgelehnt
  3. das NVIDIA-Wheel fehlt (oeffentliches ZIP): sperre_pruefen nennt es
  4. aktualisierung.sh und stick_bauen.sh benutzen das so, und
     pakete.sperre deckt requirements.txt und constraints.txt ab
"""
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
PY = WURZEL / ".venv" / "bin" / "python"
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


def wheel(ordner, name, fassung, code):
    norm = name.replace("-", "_")
    datei = ordner / f"{norm}-{fassung}-py3-none-any.whl"
    info = f"{norm}-{fassung}.dist-info"
    with zipfile.ZipFile(datei, "w") as z:
        z.writestr(f"{norm}_modul.py", code)
        z.writestr(f"{info}/METADATA",
                   f"Metadata-Version: 2.1\nName: {name}\nVersion: {fassung}\n")
        z.writestr(f"{info}/WHEEL", "Wheel-Version: 1.0\nGenerator: pruefstand\n"
                   "Root-Is-Purelib: true\nTag: py3-none-any\n")
        z.writestr(f"{info}/RECORD", "")
    return datei


def pip(*args):
    return subprocess.run([str(PY), "-m", "pip", "install", "--quiet",
                           "--disable-pip-version-check", *args],
                          capture_output=True, text=True)


ort = Path(tempfile.mkdtemp(prefix="sperre-", dir=WURZEL / ".tmp"))
try:
    w = ort / "wheels"
    w.mkdir()
    wheel(w, "devarenu-probe", "1.0", "WERT = 'echt'\n")
    nv = wheel(w, "nvidia-probe-cu12", "1.0", "WERT = 'nvidia'\n")
    sperre = ort / "pakete.sperre"
    r = subprocess.run([sys.executable, str(WURZEL / "werkzeuge/sperre_schreiben.py"),
                        str(w), str(sperre)], capture_output=True, text=True)
    titel("1) Sperre schreiben, installieren")
    pruefe("sperre_schreiben.py laeuft", 0, r.returncode)
    text = sperre.read_text()
    pruefe("jede Zeile mit sha256", 2, len(re.findall(r"--hash=sha256:", text)))
    pruefe("das NVIDIA-Paket ist als nicht oeffentlich gekennzeichnet", True,
           "# NICHT OEFFENTLICH: NVIDIA, Weitergabe ungeklaert\n"
           "nvidia-probe-cu12==1.0" in text)
    a = pip("--target", str(ort / "ziel1"), "--require-hashes", "--no-deps",
            "--no-index", "--find-links", str(w), "-r", str(sperre))
    pruefe("Installation gegen die Sperre gelingt", 0, a.returncode)

    titel("2) Ein Wheel mit gleichem Namen, anderem Inhalt")
    boese = ort / "boese"
    boese.mkdir()
    wheel(boese, "devarenu-probe", "1.0", "import os  # eingeschleust\n")
    shutil.copy2(nv, boese)
    a = pip("--target", str(ort / "ziel2"), "--require-hashes", "--no-deps",
            "--no-index", "--find-links", str(boese), "-r", str(sperre))
    pruefe("abgelehnt", True, a.returncode != 0)
    pruefe("wegen der Pruefsumme", True, "hash" in (a.stderr + a.stdout).lower())
    pruefe("nichts installiert", False,
           (ort / "ziel2" / "devarenu_probe_modul.py").exists())
    # Gegenprobe: der alte Befehl (bis 0.5.1) haette es genommen.
    alt = ort / "alt-req.txt"
    alt.write_text("devarenu-probe==1.0\n")
    a = pip("--target", str(ort / "ziel3"), "--no-index", "--find-links",
            str(boese), "-r", str(alt))
    pruefe("(der alte Befehl haette es installiert)", True,
           "eingeschleust" in (ort / "ziel3" / "devarenu_probe_modul.py")
           .read_text() if a.returncode == 0 else False)

    titel("3) Oeffentliches ZIP ohne NVIDIA-Wheel")
    nv.unlink()
    r = subprocess.run([sys.executable, str(WURZEL / "werkzeuge/sperre_pruefen.py"),
                        str(sperre), str(w)], capture_output=True, text=True)
    pruefe("sperre_pruefen nennt, was fehlt",
           "nvidia-probe-cu12 1.0 (nicht oeffentlich)", r.stdout.strip())
    a = pip("--target", str(ort / "ziel4"), "--require-hashes", "--no-deps",
            "--no-index", "--find-links", str(w), "-r", str(sperre))
    pruefe("ohne Netz scheitert die Installation, statt halb zu laufen", True,
           a.returncode != 0)
finally:
    shutil.rmtree(ort, ignore_errors=True)

titel("4) So benutzt es das Update")
akt = (WURZEL / "aktualisierung.sh").read_text(encoding="utf-8")
pruefe("aktualisierung.sh installiert mit --require-hashes aus pakete.sperre",
       True, "--require-hashes" in akt and 'SPERRE="$ORDNER/pakete.sperre"' in akt)
pruefe("fehlende Pakete nur von PyPI und nur mit Hash", True,
       "pypi_erreichbar && pip_sicher" in akt)
bau = (WURZEL / "stick_bauen.sh").read_text(encoding="utf-8")
pruefe("stick_bauen.sh laedt nach der Sperre", True,
       "-r pakete.sperre --require-hashes" in bau)
pruefe("und laesst NVIDIA ohne --mit-fremdteilen draussen", True,
       '-name "$NVIDIA_MUSTER" -delete' in bau
       and "cudart-*' -delete" in bau)
gesperrt = {m.group(1): m.group(2) for m in re.finditer(
    r"^([a-z0-9._-]+)==(\S+)", (WURZEL / "pakete.sperre").read_text(), re.M)}
noetig = {}
for datei in ("requirements.txt", "constraints.txt"):
    for z in (WURZEL / datei).read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([A-Za-z0-9._-]+)==([^\s#]+)", z.strip())
        if m:
            noetig[m.group(1).lower().replace("_", "-")] = m.group(2)
pruefe("pakete.sperre deckt requirements.txt und constraints.txt ab", {},
       {n: v for n, v in noetig.items() if gesperrt.get(n) != v})
pruefe("und bringt nvidia-cublas-cu12 fuer Whisper mit", True,
       "nvidia-cublas-cu12" in gesperrt)

print()
if FEHLER:
    print(f"{FEHLER} FEHLER")
    sys.exit(1)
print("Alles in Ordnung.")
