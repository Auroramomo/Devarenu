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


# ==================================================== Stueckeln
# Grosse Dateien passen nicht auf FAT32. Geprueft wird mit einer
# winzigen Stueckgrenze statt mit acht Gigabyte: die Logik ist
# dieselbe, der Prueflauf dauert Millisekunden statt Minuten.

def stueckel_pruefung():
    import hashlib
    import tempfile
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import teile

    fehler = 0

    def pr(was, erwartet, ist):
        nonlocal fehler
        if erwartet == ist:
            print(f"   ok    {was}")
        else:
            print(f"   FEHL  {was}: erwartet {erwartet!r}, ist {ist!r}")
            fehler += 1

    print("\n\033[1m== Stueckeln fuer FAT32\033[0m")
    with tempfile.TemporaryDirectory() as t:
        o = Path(t)
        gross = o / "modell.bin"
        inhalt = bytes(range(256)) * 400          # 102 400 Byte
        gross.write_bytes(inhalt)
        sha = hashlib.sha256(inhalt).hexdigest()

        # Unter der Grenze: schlicht kopieren.
        klein = o / "klein.bin"
        klein.write_bytes(b"kurz")
        n = teile.stueckeln(klein, o / "stick_klein.bin", groesse=1000)
        pr("kleine Datei wird nicht gestueckelt", 0, n)
        pr("und liegt als eine da", b"kurz",
           (o / "stick_klein.bin").read_bytes())

        # Darueber: in Stuecke.
        ziel = o / "stick" / "modell.bin"
        ziel.parent.mkdir()
        n = teile.stueckeln(gross, ziel, groesse=30_000)
        pr("grosse Datei wird gestueckelt", 4, n)
        pr("die ganze Datei liegt NICHT daneben", False, ziel.exists())
        stuecke = teile.stuecke_von(ziel)
        pr("die Stuecke sind gefunden und sortiert", 4, len(stuecke))
        pr("keines ueberschreitet die Grenze", True,
           all(s.stat().st_size <= 30_000 for s in stuecke))
        pr("zusammen ergeben sie die Laenge", len(inhalt),
           sum(s.stat().st_size for s in stuecke))

        # Zusammensetzen
        zurueck = o / "zurueck.bin"
        gelungen, grund = teile.zusammensetzen(ziel, zurueck, sha, len(inhalt))
        pr("zusammengesetzt", True, gelungen)
        pr("ohne Grund zur Klage", "", grund)
        pr("und byte-gleich mit dem Original", inhalt, zurueck.read_bytes())

        # Ein beschaedigtes Stueck: NICHTS anfassen.
        zurueck.unlink()
        kaputt = stuecke[1].read_bytes()
        stuecke[1].write_bytes(b"\x00" * len(kaputt))
        gelungen, grund = teile.zusammensetzen(ziel, zurueck, sha, len(inhalt))
        pr("ein verfaelschtes Stueck wird erkannt", False, gelungen)
        pr("und zwar an der Pruefsumme", "sha256 stimmt nicht", grund)
        pr("das Ziel entsteht gar nicht erst", False, zurueck.exists())
        pr("und kein Bruchstueck bleibt liegen", False,
           (o / "zurueck.bin.halb").exists())
        stuecke[1].write_bytes(kaputt)

        # Ein fehlendes Stueck: an der Laenge erkannt, nicht erst am Hash.
        weg = stuecke[2].read_bytes()
        stuecke[2].unlink()
        gelungen, grund = teile.zusammensetzen(ziel, zurueck, sha, len(inhalt))
        pr("ein fehlendes Stueck wird erkannt", False, gelungen)
        pr("und als Laengenfehler benannt", True, "Laenge" in grund)
        pr("auch hier bleibt nichts liegen", False,
           (o / "zurueck.bin.halb").exists())
        stuecke[2].write_bytes(weg)

        # Nach der Reparatur geht es wieder.
        gelungen, _ = teile.zusammensetzen(ziel, zurueck, sha, len(inhalt))
        pr("repariert laesst es sich wieder zusammensetzen", True, gelungen)

    return fehler


_stueckel_fehler = stueckel_pruefung()
print()
if _stueckel_fehler:
    print(f"\033[31m{_stueckel_fehler} Fehler beim Stueckeln.\033[0m")
    sys.exit(1)
print("\033[32mStueckeln: alle Faelle wie erwartet.\033[0m")
