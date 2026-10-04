# -*- coding: utf-8 -*-
"""teile.py mit Attrappen, nicht mit acht Gigabyte."""
import json, os, shutil, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import teile
from hilfe import wegwerfordner

ord_ = wegwerfordner("devarenu-teile-")
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
# Seit 0.4.2 sammelt erfassen() nicht mehr auf, sondern zaehlt auf:
# was in config.STIMMEN steht, das Whisper-Modell und das eine
# Sprachmodell. Hier steht die Aufzaehlung von Hand -- der Prueflauf
# soll die Mechanik pruefen, nicht die Stimmenliste dieser Fassung.
teile.sollteile = lambda: [
    ("whisper", "modell.bin"),
    ("stimmen", "de.onnx"),
    ("ollama", "blobs/sha256-aaa"),
    ("ollama", "manifests/gemma"),
]
teile.DATEI = ord_ / "teile.json"
teile.PUFFER = ord_ / ".puffer.json"

print("=== 1) erfassen")
assert teile.erfassen() == 0
d = json.loads(teile.DATEI.read_text())
print("   Eintraege:", len(d["teile"]))
assert len(d["teile"]) == 4

print("=== 1b) erfassen schreibt NICHTS, wenn etwas fehlt")
# Eine teile.json mit einer Luecke verspricht einer Gemeinde eine
# Sprache, die auf ihrem Rechner stumm bleibt.
vorher = teile.DATEI.read_text()
teile.sollteile = lambda: [
    ("whisper", "modell.bin"), ("stimmen", "de.onnx"),
    ("ollama", "blobs/sha256-aaa"), ("ollama", "manifests/gemma"),
    ("stimmen", "gibtsnicht.onnx"),
]
assert teile.erfassen() == 1
assert teile.DATEI.read_text() == vorher
print("   abgebrochen, die alte Datei steht unveraendert")
teile.sollteile = lambda: [
    ("whisper", "modell.bin"), ("stimmen", "de.onnx"),
    ("ollama", "blobs/sha256-aaa"), ("ollama", "manifests/gemma"),
]

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

# ================================================ A8 zu 0.4.2
print("=== 7) Stick ohne Netz bringt eine fehlende Stimme mit")
# Der Fall, um den es geht: ein Rechner, der Farsi eingeschaltet hat,
# aber die Stimme nicht auf der Platte. Der Stick traegt sie, und ein
# Update spielt sie ein -- ohne dass irgendwo eine Leitung liegt.
d["teile"] = [e for e in d["teile"] if e["pfad"] != "fr.onnx"]
d["teile"].append({"art": "stimmen", "pfad": "fa.onnx", "bytes": 9,
                   "sha256": sha("stimme-fa")})
teile.DATEI.write_text(json.dumps(d), encoding="utf-8")
f, ab, da = teile.lage()
assert any(e["pfad"] == "fa.onnx" for e in f), "fa.onnx muesste fehlen"
print("   vorher fehlt fa.onnx")
schreib(stick / "stimmen" / "fa.onnx", "stimme-fa")
rc = teile.einspielen(stick, sicherung)
print("   Rueckgabe:", rc)
assert rc == 0
assert (platte / "stimmen" / "fa.onnx").read_text() == "stimme-fa"
print("   die Stimme liegt jetzt auf der Platte")

print("=== 8) falsche Pruefsumme wird abgelehnt, nichts ersetzt")
# Eine Stimme, die anders klingt als die gemessene, ist keine
# Verbesserung, sondern eine Ueberraschung.
d["teile"] = [e for e in d["teile"] if e["pfad"] != "de.onnx"]
d["teile"].append({"art": "stimmen", "pfad": "de.onnx",
                   "bytes": len("stimme-de-NEU"),
                   "sha256": sha("stimme-de-NEU")})
teile.DATEI.write_text(json.dumps(d), encoding="utf-8")
# Der Stick traegt etwas mit der richtigen LAENGE, aber falschem Inhalt.
schreib(stick / "stimmen" / "de.onnx", "stimme-de-XXX")
assert len("stimme-de-XXX") == len("stimme-de-NEU")
rc = teile.einspielen(stick, sicherung)
print("   Rueckgabe:", rc, "(erwartet 1 -- nachgerechnet stimmt es nicht)")
assert rc == 1
f, ab, da = teile.lage()
assert any(e["pfad"] == "de.onnx" for e in ab), \
    "de.onnx muesste als abweichend dastehen"
print("   de.onnx gilt weiter als abweichend, es wurde nichts bestaetigt")
print("   das alte liegt in der Sicherung:",
      (sicherung / "stimmen" / "de.onnx").read_text())
assert (sicherung / "stimmen" / "de.onnx").read_text() == "stimme-de"

print("=== 9) zusammengesetzte Stuecke mit falscher Summe ersetzen nichts")
gut_inhalt = "stimme-ru" * 20
d["teile"] = [e for e in d["teile"] if e["pfad"] != "de.onnx"]
d["teile"].append({"art": "stimmen", "pfad": "ru.onnx",
                   "bytes": len(gut_inhalt), "sha256": sha(gut_inhalt)})
teile.DATEI.write_text(json.dumps(d), encoding="utf-8")
schreib(platte / "stimmen" / "ru.onnx", "ru-ALT")
boese = ("x" * len(gut_inhalt))
ziel = stick / "stimmen" / "ru.onnx"
ziel.parent.mkdir(parents=True, exist_ok=True)
for st in teile.stuecke_von(ziel):
    st.unlink()
teile.stueckeln_quelle = None
(ziel.parent / "ru.onnx.teil00").write_text(boese[:100], encoding="utf-8")
(ziel.parent / "ru.onnx.teil01").write_text(boese[100:], encoding="utf-8")
ziel.unlink(missing_ok=True)
rc = teile.einspielen(stick, sicherung)
print("   Rueckgabe:", rc, "(erwartet 1)")
assert rc == 1
print("   das alte ru.onnx wurde nicht durch Unsinn ersetzt:",
      not (platte / "stimmen" / "ru.onnx").exists()
      or (platte / "stimmen" / "ru.onnx").read_text() == "ru-ALT")

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


# ---------------------------------------------------------------------
# Der Stick nimmt, was in teile.json STEHT -- nicht, was auf der
# Platte liegt.
#
# Die Frage dahinter ist keine Kleinigkeit: liefe es andersherum,
# wuerde eine Stimme, die aus config.STIMMEN herausgenommen wurde,
# von jedem bestehenden Rechner weiterverteilt -- ihre Datei liegt
# dort ja noch. Genau das waere bei ka_GE-natia-medium und
# ar_JO-kareem-medium (0.4.5, Lizenz) der Fehler gewesen.
#
# Bis 0.4.1 war es auch so: erfassen() sammelte alles unter voices/
# ein. Seit 0.4.2 zaehlt es auf. Dieser Abschnitt haelt fest, dass es
# dabei bleibt.
def stick_nimmt_nur_erfasstes():
    fehler = 0

    def pr(was, erwartet, ist):
        nonlocal fehler
        if erwartet == ist:
            print(f"   ok    {was}")
        else:
            fehler += 1
            print(f"   FEHLER {was}: erwartet {erwartet!r}, ist {ist!r}")

    print("\n=== 9) Der Stick nimmt nur, was erfasst ist")
    # Sauber aufsetzen: die Abschnitte davor haben teile.json von Hand
    # um Eintraege erweitert, die auf dieser Platte gar nicht liegen.
    assert teile.erfassen() == 0

    # Eine Stimme, die auf der Platte liegt und NICHT in teile.json
    # steht -- so sieht ein Rechner aus, auf dem eine herausgenommene
    # Stimme noch herumliegt.
    schreib(platte / "stimmen" / "verboten.onnx", "stimme-ohne-lizenz")
    schreib(platte / "stimmen" / "verboten.onnx.json", "{}")
    pr("sie liegt wirklich auf der Platte", True,
       (platte / "stimmen" / "verboten.onnx").exists())
    d = json.loads(teile.DATEI.read_text())
    pr("und steht nicht in teile.json", [],
       [e["pfad"] for e in d["teile"] if "verboten" in e["pfad"]])

    stick2 = ord_ / "stick-nur-erfasstes"
    pr("auf_stick geht durch", 0, teile.auf_stick(str(stick2), voll=True))
    gelandet = sorted(p.name for p in (stick2 / "stimmen").glob("*"))
    pr("auf dem Stick liegt nur die erfasste Stimme", ["de.onnx"], gelandet)
    pr("die unerfasste ist NICHT mitgekommen", False,
       (stick2 / "stimmen" / "verboten.onnx").exists())

    # Und erfassen() holt sie auch nicht nachtraeglich herein: es
    # zaehlt auf, was eingestellt ist, statt den Ordner zu lesen.
    assert teile.erfassen() == 0
    d2 = json.loads(teile.DATEI.read_text())
    pr("erfassen() nimmt sie auch nicht auf", [],
       [e["pfad"] for e in d2["teile"] if "verboten" in e["pfad"]])

    (platte / "stimmen" / "verboten.onnx").unlink()
    (platte / "stimmen" / "verboten.onnx.json").unlink()
    return fehler


_stick_fehler = stick_nimmt_nur_erfasstes()
print()
if _stick_fehler:
    print(f"\033[31m{_stick_fehler} Fehler beim Stick.\033[0m")
    sys.exit(1)
print("\033[32mStick: alle Faelle wie erwartet.\033[0m")
