# -*- coding: utf-8 -*-
"""teile.py mit Attrappen, nicht mit acht Gigabyte."""
import json, os, shutil, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import teile

ord_ = Path(tempfile.mkdtemp())
platte = ord_ / "platte"
stick = ord_ / "stick"
sicherung = ord_ / "sicherung"
for p in (platte / "whisper", platte / "stimmen", platte / "ollama"):
    p.mkdir(parents=True)

def schreib(p, text):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")

schreib(platte / "whisper" / "modell.bin", "whisper-alt")
schreib(platte / "stimmen" / "de.onnx", "stimme-de")
schreib(platte / "ollama" / "blobs" / "sha256-aaa", "blob-alt")
schreib(platte / "ollama" / "manifests" / "gemma", "manifest-alt")

teile.orte = lambda: {"whisper": platte / "whisper",
                      "stimmen": platte / "stimmen",
                      "ollama": platte / "ollama"}
teile.DATEI = ord_ / "teile.json"
teile.PUFFER = ord_ / ".puffer.json"

print("=== 1) erfassen")
teile.erfassen()
d = json.loads(teile.DATEI.read_text())
print("   Eintraege:", len(d["teile"]))
assert len(d["teile"]) == 4

print("=== 2) pruefen: alles da")
f, ab, da = teile.lage()
print(f"   {len(da)} stimmen, {len(f)} fehlen, {len(ab)} weichen ab")
assert not f and not ab

print("=== 3) Modellwechsel: Manifest anders, neuer Blob")
schreib(stick / "ollama" / "manifests" / "gemma", "manifest-NEU")
schreib(stick / "ollama" / "blobs" / "sha256-bbb", "blob-NEU")
# teile.json der neuen Fassung
d["teile"] = [e for e in d["teile"] if e["pfad"] != "manifests/gemma"]
import hashlib
def sha(t): return hashlib.sha256(t.encode()).hexdigest()
d["teile"] += [
    {"art": "ollama", "pfad": "manifests/gemma", "bytes": len("manifest-NEU"),
     "sha256": sha("manifest-NEU")},
    {"art": "ollama", "pfad": "blobs/sha256-bbb", "bytes": len("blob-NEU"),
     "sha256": sha("blob-NEU")},
]
teile.DATEI.write_text(json.dumps(d), encoding="utf-8")
f, ab, da = teile.lage()
print(f"   {len(f)} fehlen, {len(ab)} weichen ab (erwartet 1 und 1)")
assert len(f) == 1 and len(ab) == 1

print("=== 4) einspielen")
rc = teile.einspielen(stick, sicherung)
print("   Rueckgabe:", rc)
assert rc == 0
print("   Manifest jetzt:", (platte / "ollama" / "manifests" / "gemma").read_text())
assert (platte / "ollama" / "manifests" / "gemma").read_text() == "manifest-NEU"
print("   altes Manifest beiseite:",
      (sicherung / "ollama" / "manifests" / "gemma").read_text())
assert (sicherung / "ollama" / "manifests" / "gemma").read_text() == "manifest-alt"
print("   alter Blob liegt noch da:", (platte / "ollama" / "blobs" / "sha256-aaa").exists())

print("=== 5) fehlender Teil auf dem Stick")
d["teile"].append({"art": "stimmen", "pfad": "fr.onnx", "bytes": 9,
                   "sha256": sha("stimme-fr")})
teile.DATEI.write_text(json.dumps(d), encoding="utf-8")
rc = teile.einspielen(stick, sicherung)
print("   Rueckgabe:", rc, "(erwartet 1)")
assert rc == 1
print("   nichts angefasst:", not (platte / "stimmen" / "fr.onnx").exists())

print("=== 6) aufraeumen")
teile.aufraeumen(sicherung)
print("   Sicherung weg:", not sicherung.exists())
print("\nalle Faelle wie erwartet.")
