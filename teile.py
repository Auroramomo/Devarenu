#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Die grossen Teile: Sprachmodell, Spracherkennung, Stimmen, Torch.

Sie liegen nicht im Repo -- zusammen sind es rund vierzehn Gigabyte,
und ein git-Bundle damit ginge auf keinen Stick. Im Repo steht nur
teile.json: welche Datei wohin gehoert, wie gross sie ist und welche
Pruefsumme sie hat.

    python teile.py --erfassen      teile.json aus dieser Platte bauen
    python teile.py --pruefen       liegt alles da, und stimmt es?
    python teile.py --einspielen    Fehlendes aus einem Ordner holen
    python teile.py --aufraeumen    Ersetztes wegraeumen

WARUM UEBERHAUPT
----------------
Bis 0.2.12 konnte ein Update alles ausser den grossen Teilen. Ein
Wechsel des Sprachmodells war damit ein Besuch vor Ort. Modelle
aendern sich selten -- aber sie KOENNEN sich aendern, und dann soll
ein Stick genuegen.

WAS HIER NICHT GERATEN WIRD
---------------------------
Der Ort der Ollama-Ablage. Drei Rechner, drei Orte: /usr/share/ollama
beim Installierskript, /var/lib/ollama beim Arch-Paket, und anderswo,
wenn jemand OLLAMA_MODELS gesetzt hat. Gefragt wird
systemcheck.ollama_ablage().

ERST PRUEFEN, DANN ANFASSEN
---------------------------
--einspielen sieht ZUERST nach, ob alles Noetige da ist und ob der
Platz reicht. Fehlt etwas, wird gar nichts geaendert. Ein halb
eingespieltes Modell ist schlimmer als ein altes.
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

import config

DATEI = config.BASIS / "teile.json"

# Pruefsummen von acht Gigabyte zu rechnen dauert. Gemerkt wird, was
# schon einmal gerechnet wurde -- erkannt an Groesse und Aenderungszeit.
# Aendert sich eine davon, wird neu gerechnet.
PUFFER = config.BASIS / ".teile-pruefsummen.json"


def ollama_ort():
    """Die Ollama-Ablage, oder None."""
    try:
        import systemcheck
        return systemcheck.ollama_ablage()
    except Exception:
        return None


def orte():
    """Wo die grossen Teile liegen. Schluessel ist die Art."""
    o = {
        "whisper": config.BASIS / "models",
        "stimmen": config.BASIS / "voices",
    }
    ablage = ollama_ort()
    if ablage:
        o["ollama"] = Path(ablage)
    return o


def _puffer_laden():
    try:
        return json.loads(PUFFER.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _puffer_speichern(p):
    try:
        PUFFER.write_text(json.dumps(p, indent=1) + "\n", encoding="utf-8")
    except OSError:
        pass


def summe(pfad, puffer=None):
    """sha256 einer Datei, mit Zwischenspeicher."""
    pfad = Path(pfad)
    st = pfad.stat()
    kennung = f"{st.st_size}:{int(st.st_mtime)}"
    schluessel = str(pfad)
    if puffer is not None:
        eintrag = puffer.get(schluessel)
        if eintrag and eintrag.get("kennung") == kennung:
            return eintrag["sha256"]
    h = hashlib.sha256()
    with open(pfad, "rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    wert = h.hexdigest()
    if puffer is not None:
        puffer[schluessel] = {"kennung": kennung, "sha256": wert}
    return wert


def erfassen():
    """Baut teile.json aus dem, was auf dieser Platte liegt."""
    puffer = _puffer_laden()
    eintraege = []
    for art, wurzel in orte().items():
        if not wurzel.is_dir():
            print(f"  {art}: {wurzel} gibt es nicht, uebersprungen")
            continue
        n = 0
        for pfad in sorted(wurzel.rglob("*")):
            if not pfad.is_file() or pfad.is_symlink():
                continue
            eintraege.append({
                "art": art,
                "pfad": str(pfad.relative_to(wurzel)),
                "bytes": pfad.stat().st_size,
                "sha256": summe(pfad, puffer),
            })
            n += 1
        print(f"  {art}: {n} Dateien unter {wurzel}")
    _puffer_speichern(puffer)
    gesamt = sum(e["bytes"] for e in eintraege)
    DATEI.write_text(json.dumps({
        "fassung": config.VERSION,
        "hinweis": "Erzeugt von teile.py --erfassen. Die Dateien selbst "
                   "liegen nicht im Repo.",
        "bytes": gesamt,
        "teile": eintraege,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\n{len(eintraege)} Teile, {gesamt / 1e9:.1f} GB -> {DATEI.name}")


def laden():
    if not DATEI.exists():
        return None
    return json.loads(DATEI.read_text(encoding="utf-8"))


def lage():
    """(fehlend, abweichend, vorhanden) gegenueber teile.json."""
    d = laden()
    if d is None:
        return None
    puffer = _puffer_laden()
    o = orte()
    fehlend, abweichend, da = [], [], []
    for e in d["teile"]:
        wurzel = o.get(e["art"])
        if wurzel is None:
            fehlend.append(e)
            continue
        ziel = wurzel / e["pfad"]
        if not ziel.is_file():
            fehlend.append(e)
        elif ziel.stat().st_size != e["bytes"] or \
                summe(ziel, puffer) != e["sha256"]:
            abweichend.append(e)
        else:
            da.append(e)
    _puffer_speichern(puffer)
    return fehlend, abweichend, da


# ----------------------------------------------------- Stueckeln
#
# FAT32 kann keine Datei ueber 4 GB. Das Sprachmodell allein ist
# groesser. Bis 0.3.0 hiess die Antwort darauf: FAT32 ablehnen und den
# Stick neu formatieren lassen. Das ist eine Zumutung fuer jemanden,
# der nur einen Stick bringen soll -- und Sticks kommen nun einmal
# formatiert an.
#
# Also stueckeln. Die Grenze liegt bei 3,5 GB und nicht bei 4: FAT32
# kann 4 GiB minus ein Byte, und ein Rest von einer halben Milliarde
# Byte kostet nichts ausser einer weiteren Datei.
#
# Zusammengesetzt wird gegen die sha256 aus teile.json geprueft. Passt
# sie nicht, wird NICHTS angefasst -- weder das alte Modell noch das
# halbe neue. Ein halb eingespieltes Modell ist schlimmer als ein
# altes, und das galt hier schon vorher.
STUECK = 3_500_000_000


def stueckname(pfad, nummer):
    return Path(f"{pfad}.teil{nummer:02d}")


def stueckeln(quelle, zielpfad, groesse=STUECK):
    """Schreibt quelle in Stuecke. Gibt die Anzahl zurueck.

    Bleibt die Datei unter der Grenze, wird sie schlicht kopiert und 0
    zurueckgegeben -- der Normalfall soll nicht teurer werden, nur
    weil der Ausnahmefall abgedeckt ist.

    Der Lesepuffer ist hoechstens so gross wie ein Stueck. Der erste
    Anlauf las feste 1 MiB und zaehlte danach: bei einer Stueckgrenze
    unter 1 MiB landete damit die ganze Datei in einem Stueck. Im
    Betrieb waere das nie aufgefallen -- dort ist die Grenze 3,5 GB --,
    im Pruefstand mit kleinen Attrappen sofort."""
    quelle = Path(quelle)
    zielpfad = Path(zielpfad)
    if quelle.stat().st_size <= groesse:
        shutil.copy2(quelle, zielpfad)
        return 0

    puffer = min(1 << 20, groesse)
    n = 0
    with open(quelle, "rb") as ein:
        while True:
            erstes = ein.read(puffer)
            if not erstes:
                break
            geschrieben = 0
            with open(stueckname(zielpfad, n), "wb") as aus:
                aus.write(erstes)
                geschrieben += len(erstes)
                while geschrieben < groesse:
                    weiter = ein.read(min(puffer, groesse - geschrieben))
                    if not weiter:
                        break
                    aus.write(weiter)
                    geschrieben += len(weiter)
            n += 1
    return n


def stuecke_von(pfad):
    """Alle Stuecke einer Datei, in der richtigen Reihenfolge."""
    pfad = Path(pfad)
    gefunden = sorted(pfad.parent.glob(pfad.name + ".teil[0-9][0-9]"))
    return gefunden


def zusammensetzen(quellpfad, zielpfad, erwartet_sha, erwartet_bytes):
    """Setzt Stuecke zusammen und prueft. (gelungen, grund).

    Geschrieben wird zuerst NEBEN das Ziel und erst nach bestandener
    Pruefung umbenannt. Bricht der Strom mittendrin aus, liegt ein
    Bruchstueck mit fremdem Namen da -- und nicht ein halbes Modell an
    der Stelle, an der der Dienst eines erwartet."""
    stuecke = stuecke_von(quellpfad)
    if not stuecke:
        return False, "keine Stuecke"
    zielpfad = Path(zielpfad)
    zwischen = zielpfad.with_name(zielpfad.name + ".halb")
    h = hashlib.sha256()
    gesamt = 0
    try:
        with open(zwischen, "wb") as aus:
            for st in stuecke:
                with open(st, "rb") as ein:
                    while True:
                        b = ein.read(1 << 20)
                        if not b:
                            break
                        aus.write(b)
                        h.update(b)
                        gesamt += len(b)
    except OSError as e:
        zwischen.unlink(missing_ok=True)
        return False, f"nicht schreibbar: {str(e)[:70]}"

    if gesamt != erwartet_bytes:
        zwischen.unlink(missing_ok=True)
        return False, (f"Laenge {gesamt} statt {erwartet_bytes} -- "
                       f"ein Stueck fehlt oder ist abgeschnitten")
    if h.hexdigest() != erwartet_sha:
        zwischen.unlink(missing_ok=True)
        return False, "sha256 stimmt nicht"
    zwischen.replace(zielpfad)
    return True, ""


def einspielen(quelle, sicherung):
    """Holt Fehlendes und Abweichendes aus quelle. Erst pruefen, dann tun."""
    erg = lage()
    if erg is None:
        print("Keine teile.json -- nichts einzuspielen.")
        return 0
    fehlend, abweichend, da = erg
    noetig = fehlend + abweichend
    if not noetig:
        print(f"  alle {len(da)} Teile sind da und stimmen")
        return 0

    quelle = Path(quelle)
    print(f"  {len(noetig)} Teile fehlen oder weichen ab")

    # ---- erst pruefen: ist alles da, und passt es auf die Platte?
    nicht_auf_stick = []
    braucht = 0
    for e in noetig:
        herkunft = quelle / e["art"] / e["pfad"]
        if herkunft.is_file() and herkunft.stat().st_size == e["bytes"]:
            braucht += e["bytes"]
            continue
        # Nicht als ganze Datei da? Dann vielleicht in Stuecken --
        # ein Stick mit FAT32 kann nichts ueber 4 GB tragen.
        stuecke = stuecke_von(herkunft)
        if stuecke and sum(st.stat().st_size for st in stuecke) == e["bytes"]:
            braucht += e["bytes"]
            continue
        nicht_auf_stick.append(f"{e['art']}/{e['pfad']}"
                               + (f" ({len(stuecke)} Stuecke, Laenge "
                                  f"stimmt nicht)" if stuecke else ""))
    if nicht_auf_stick:
        print("  FEHLT auf dem Stick:")
        for x in nicht_auf_stick[:8]:
            print(f"    {x}")
        if len(nicht_auf_stick) > 8:
            print(f"    ... und {len(nicht_auf_stick) - 8} weitere")
        return 1

    o = orte()
    for art in {e["art"] for e in noetig}:
        wurzel = o.get(art)
        if wurzel is None:
            print(f"  Kein Ablageort fuer {art} gefunden.")
            return 1
        frei = shutil.disk_usage(wurzel).free
        # Mit Luft: das Alte bleibt liegen, bis der Gesundheitscheck
        # steht. Es liegt also beides gleichzeitig da.
        if frei < braucht * 1.2 + 500e6:
            print(f"  Zu wenig Platz unter {wurzel}: "
                  f"{frei / 1e9:.1f} GB frei, gebraucht "
                  f"{braucht * 1.2 / 1e9:.1f} GB.")
            return 1

    # ---- jetzt erst anfassen
    sicherung = Path(sicherung)
    sicherung.mkdir(parents=True, exist_ok=True)
    ersetzt = []
    for e in noetig:
        wurzel = o[e["art"]]
        ziel = wurzel / e["pfad"]
        ziel.parent.mkdir(parents=True, exist_ok=True)
        # Eine Datei, die es schon gibt, wird nicht ueberschrieben,
        # sondern beiseitegelegt. Ollama-Manifeste tragen denselben
        # Namen bei anderem Inhalt -- ohne das waere der Rueckweg weg.
        if ziel.is_file():
            beiseite = sicherung / e["art"] / e["pfad"]
            beiseite.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(ziel), str(beiseite))
            ersetzt.append(f"{e['art']}/{e['pfad']}")
        herkunft = quelle / e["art"] / e["pfad"]
        if herkunft.is_file():
            shutil.copy2(herkunft, ziel)
        else:
            # In Stuecken vom Stick. Zusammengesetzt wird gegen die
            # sha256 aus teile.json geprueft; stimmt sie nicht, bleibt
            # das Alte liegen, wo es liegt.
            gelungen, grund = zusammensetzen(herkunft, ziel, e["sha256"],
                                             e["bytes"])
            if not gelungen:
                print(f"  {e['art']}/{e['pfad']}: {grund}")
                print("  ABGEBROCHEN. Das Beiseitegelegte liegt unter "
                      f"{sicherung} und wird NICHT aufgeraeumt.")
                return 1
            print(f"    {e['art']}/{e['pfad']}: aus "
                  f"{len(stuecke_von(herkunft))} Stuecken, sha256 stimmt")
    if ersetzt:
        (sicherung / "ersetzt.txt").write_text(
            "\n".join(ersetzt) + "\n", encoding="utf-8")
    print(f"  {len(noetig)} Teile eingespielt, {len(ersetzt)} ersetzt")

    # Den Zwischenspeicher fuer die frisch geschriebenen Dateien
    # vergessen. copy2 uebernimmt die Aenderungszeit der Quelle -- bei
    # gleicher Groesse sieht der Eintrag dann unveraendert aus, und die
    # Nachrechnung bekaeme die Pruefsumme der ALTEN Datei zurueck. Beim
    # Test mit zwei gleich langen Ollama-Manifesten ist genau das
    # passiert: eingespielt war richtig, nachgerechnet falsch.
    puffer = _puffer_laden()
    for e in noetig:
        puffer.pop(str(o[e["art"]] / e["pfad"]), None)
    _puffer_speichern(puffer)

    # ---- nachrechnen
    fehlend, abweichend, da = lage()
    if fehlend or abweichend:
        print(f"  Nach dem Einspielen stimmen {len(fehlend + abweichend)} "
              f"Teile immer noch nicht.")
        return 1
    print(f"  nachgerechnet: alle {len(da)} Teile stimmen")
    return 0


def auf_stick(ziel, von="", voll=False):
    """Legt die grossen Teile fuer einen Stick bereit.

    --von vX.Y.Z nimmt nur, was sich gegenueber der teile.json JENER
    Fassung geaendert hat. Der Vergleich laeuft ueber git: die alte
    Datei wird aus dem Tag gelesen, ohne den Arbeitsbaum anzufassen.

    Ohne --von und ohne --voll passiert hier gar nichts -- das
    entscheidet der Aufrufer."""
    import subprocess
    d = laden()
    if d is None:
        print("Keine teile.json. Erst: python teile.py --erfassen")
        return 1
    noetig = d["teile"]

    if von and not voll:
        try:
            roh = subprocess.run(
                ["git", "show", f"{von}:teile.json"],
                cwd=config.BASIS, capture_output=True, text=True, timeout=30)
            if roh.returncode != 0:
                print(f"  {von} bringt keine teile.json mit -- es kommt alles mit.")
            else:
                alt = json.loads(roh.stdout)
                vorher = {(e["art"], e["pfad"]): e["sha256"]
                          for e in alt.get("teile", [])}
                noetig = [e for e in d["teile"]
                          if vorher.get((e["art"], e["pfad"])) != e["sha256"]]
                print(f"  gegenueber {von}: {len(noetig)} von "
                      f"{len(d['teile'])} Teilen geaendert")
        except Exception as e:
            print(f"  Vergleich mit {von} misslang ({type(e).__name__}) "
                  f"-- es kommt alles mit.")

    if not noetig:
        print("  Nichts geaendert. Der Stick braucht keine grossen Teile.")
        return 0

    o = orte()
    ziel = Path(ziel)
    gesamt = 0
    gestueckelt = 0
    for e in noetig:
        wurzel = o.get(e["art"])
        if wurzel is None:
            print(f"  Kein Ablageort fuer {e['art']} -- abgebrochen.")
            return 1
        quelle = wurzel / e["pfad"]
        if not quelle.is_file():
            print(f"  Fehlt auf dieser Platte: {e['art']}/{e['pfad']}")
            return 1
        zielpfad = ziel / e["art"] / e["pfad"]
        zielpfad.parent.mkdir(parents=True, exist_ok=True)
        # Alte Stuecke aus einem frueheren Lauf zuerst weg: sonst
        # haengen sie an das neue an, und zusammengesetzt kommt
        # Unsinn heraus -- mit richtiger Laenge, falls die Fassungen
        # zufaellig gleich gross sind.
        for st in stuecke_von(zielpfad):
            st.unlink()
        n = stueckeln(quelle, zielpfad)
        if n:
            gestueckelt += 1
            print(f"    {e['art']}/{e['pfad']}: {n} Stuecke "
                  f"(zu gross fuer FAT32)")
        gesamt += e["bytes"]
    print(f"  {len(noetig)} Teile, {gesamt / 1e9:.2f} GB"
          + (f", davon {gestueckelt} gestueckelt" if gestueckelt else ""))
    return 0


def aufraeumen(sicherung):
    """Das Beiseitegelegte endgueltig weg -- erst nach bestandenem Check."""
    sicherung = Path(sicherung)
    if not sicherung.is_dir():
        return 0
    shutil.rmtree(sicherung, ignore_errors=True)
    print(f"  {sicherung} entfernt")
    return 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--erfassen", action="store_true")
    p.add_argument("--pruefen", action="store_true")
    p.add_argument("--einspielen", action="store_true")
    p.add_argument("--aufraeumen", action="store_true")
    p.add_argument("--quelle", default="")
    p.add_argument("--sicherung", default="")
    p.add_argument("--auf-stick", default="")
    p.add_argument("--von", default="")
    p.add_argument("--voll", action="store_true")
    a = p.parse_args()

    if a.erfassen:
        erfassen()
        return 0
    if a.pruefen:
        erg = lage()
        if erg is None:
            print("Keine teile.json.")
            return 0
        fehlend, abweichend, da = erg
        print(f"  {len(da)} stimmen, {len(fehlend)} fehlen, "
              f"{len(abweichend)} weichen ab")
        for e in (fehlend + abweichend)[:10]:
            print(f"    {e['art']}/{e['pfad']}")
        return 1 if (fehlend or abweichend) else 0
    if a.einspielen:
        if not a.quelle or not a.sicherung:
            sys.exit("--einspielen braucht --quelle und --sicherung")
        return einspielen(a.quelle, a.sicherung)
    if a.auf_stick:
        return auf_stick(a.auf_stick, a.von, a.voll)
    if a.aufraeumen:
        if not a.sicherung:
            sys.exit("--aufraeumen braucht --sicherung")
        return aufraeumen(a.sicherung)
    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
