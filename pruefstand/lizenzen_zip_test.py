#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Steht alles, was ins oeffentliche Update-ZIP geht, mit Lizenz in
LIZENZEN.md -- und bleibt draussen, was nicht hinaus soll? (28.10.2026)

    python pruefstand/lizenzen_zip_test.py

1. Jedes Paket aus pakete.sperre steht in LIZENZEN.md, mit Fassung,
   Lizenz und "ja"/"nein" fuer das oeffentliche ZIP.
2. Die "nein" in LIZENZEN.md sind genau die "# NICHT OEFFENTLICH" in
   pakete.sperre (NVIDIA, av, ctranslate2, piper-tts) -- und
   werkzeuge/sperre_pruefen.py --nicht-oeffentlich nennt genau sie.
3. Kein "siehe Projektseite" mehr.
4. Der Apache-Text liegt bei; stick_bauen.sh legt LIZENZEN.md und
   lizenzen/ ins ZIP; release_zip.sh sieht nach allem Nicht-Oeffentlichen.
"""
import re
import subprocess
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
FEHLER = 0


def pruefe(was, erwartet, ist):
    global FEHLER
    if erwartet == ist:
        print(f"   ok    {was}")
    else:
        FEHLER += 1
        print(f"   FEHL  {was}: erwartet {erwartet!r}, ist {ist!r}")


lizenzen = (WURZEL / "LIZENZEN.md").read_text(encoding="utf-8")
sperre = (WURZEL / "pakete.sperre").read_text(encoding="utf-8")
pakete = re.findall(r"^([a-z0-9._-]+)==(\S+)", sperre, re.M)
nicht = {m.group(1) for m in re.finditer(
    r"^# NICHT OEFFENTLICH: .*\n([a-z0-9._-]+)==", sperre, re.M)}

print("\n== 1) Jedes Paket mit Lizenz in LIZENZEN.md")
zeilen = {}
for z in lizenzen.splitlines():
    m = re.match(r"^\| ([a-z0-9._-]+)(?: \([^)]*\))? \| (\S+) \| (.+) \| "
                 r"(ja|\*\*nein\*\*) \|$", z)
    if m:
        zeilen[m.group(1)] = (m.group(2), m.group(3), m.group(4))
fehlt = [f"{n} {v}" for n, v in pakete if n not in zeilen]
pruefe(f"alle {len(pakete)} Pakete stehen in der Tabelle", [], fehlt)
falsch = [n for n, v in pakete if n in zeilen and zeilen[n][0] != v]
pruefe("mit der Fassung aus pakete.sperre", [], falsch)
ohne = [n for n, (_v, liz, _j) in zeilen.items() if len(liz.strip()) < 3]
pruefe("und jeweils einer Lizenz", [], ohne)

print("\n== 2) Was nicht ins oeffentliche ZIP darf")
nein = {n for n, (_v, _l, j) in zeilen.items() if j != "ja"}
pruefe("die nein-Zeilen sind genau die NICHT OEFFENTLICH der Sperre",
       sorted(nicht), sorted(nein))
pruefe("darunter NVIDIA und die drei mit GPL-Binaerteilen",
       ["av", "ctranslate2", "nvidia-cublas-cu12", "piper-tts"], sorted(nicht))
r = subprocess.run([sys.executable, str(WURZEL / "werkzeuge/sperre_pruefen.py"),
                    "--nicht-oeffentlich", str(WURZEL / "pakete.sperre")],
                   capture_output=True, text=True)
pruefe("sperre_pruefen --nicht-oeffentlich nennt sie (Wheel-Schreibweise)",
       sorted(re.sub(r"[-.]+", "_", n) for n in nicht), sorted(r.stdout.split()))

print("\n== 3) Nichts mehr ungeprueft")
pruefe("kein 'siehe Projektseite'", False, "siehe Projektseite" in lizenzen)

print("\n== 4) Lizenztexte im ZIP, Pruefung vor dem Hochladen")
apache = WURZEL / "lizenzen" / "Apache-2.0.txt"
pruefe("lizenzen/Apache-2.0.txt liegt da", True,
       apache.exists() and "Apache License" in apache.read_text()[:200])
bau = (WURZEL / "stick_bauen.sh").read_text(encoding="utf-8")
pruefe("stick_bauen.sh legt LIZENZEN.md und lizenzen/ ins ZIP", True,
       'git show "$TAG:LIZENZEN.md" > "$STICK/LIZENZEN.md.neu"' in bau
       and 'git ls-tree --name-only "$TAG" lizenzen/' in bau)
pruefe("und nimmt die nicht oeffentlichen Wheels heraus", True,
       "sperre_pruefen.py\" \\\n                     --nicht-oeffentlich" in bau)
rel = (WURZEL / "release_zip.sh").read_text(encoding="utf-8")
pruefe("release_zip.sh prueft das fertige ZIP auf alle nicht oeffentlichen "
       "Wheels und teile/", True,
       "--nicht-oeffentlich pakete.sperre" in rel and "^teile/" in rel)
pruefe("und dass die Lizenztexte darin liegen", True,
       "LIZENZEN.md lizenzen/Apache-2.0.txt" in rel)

print()
if FEHLER:
    print(f"{FEHLER} FEHLER")
    sys.exit(1)
print("Alles in Ordnung.")
