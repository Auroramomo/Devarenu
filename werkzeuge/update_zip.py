#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Devarenu-Update.zip vom Stick auspacken -- vorsichtig (0.5.2).

    python3 werkzeuge/update_zip.py ZIP ZIELORDNER

Aufgerufen von stick_update.sh (als root), wenn auf dem Stick kein
upd-dev.txt liegt, aber ein Devarenu-Update.zip. VERTRAUT wird dem
Inhalt dabei nicht: das Bundle prueft danach die Signatur, die Wheels
pakete.sperre, die grossen Teile teile.json -- wie bei einem
ausgepackten Stick. Hier geht es nur darum, dass das Auspacken selbst
nichts anrichten kann:

  * nur gewoehnliche Dateien und Ordner -- keine Verknuepfungen
  * kein Name mit "..", keiner mit absolutem Pfad
  * hoechstens 40 GB ausgepackt und nicht mehr, als frei ist (ein
    "ZIP-Bombe" fuellt sonst die Platte, auf der Devarenu laeuft)

Rueckgabe 0 und auf der letzten Zeile der Ordner, in dem upd-dev.txt
liegt. Sonst 1 und ein Satz, warum nicht.
"""
import shutil
import stat
import sys
import zipfile
from pathlib import Path, PurePosixPath

HOECHSTENS = 40 * 10**9


def main():
    zip_pfad, ziel = Path(sys.argv[1]), Path(sys.argv[2])
    try:
        z = zipfile.ZipFile(zip_pfad)
    except (OSError, zipfile.BadZipFile) as e:
        print(f"Das ZIP ist nicht lesbar ({type(e).__name__}).")
        return 1
    with z:
        eintraege = z.infolist()
        summe = 0
        for e in eintraege:
            name = PurePosixPath(e.filename)
            if name.is_absolute() or ".." in name.parts or "\\" in e.filename:
                print(f"Unzulaessiger Name im ZIP: {e.filename[:80]}")
                return 1
            art = (e.external_attr >> 16) & 0o170000
            if art and not (stat.S_ISREG(art) or stat.S_ISDIR(art)):
                print(f"Keine gewoehnliche Datei im ZIP: {e.filename[:80]}")
                return 1
            summe += e.file_size
        ziel.mkdir(parents=True, exist_ok=True)
        frei = shutil.disk_usage(ziel).free
        if summe > HOECHSTENS or summe > frei - 2 * 10**9:
            print(f"Das ZIP wuerde {summe / 1e9:.1f} GB auspacken; frei sind "
                  f"{frei / 1e9:.1f} GB.")
            return 1
        for e in eintraege:
            if e.is_dir():
                (ziel / e.filename).mkdir(parents=True, exist_ok=True)
                continue
            aus = ziel / e.filename
            aus.parent.mkdir(parents=True, exist_ok=True)
            with z.open(e) as quelle, open(aus, "wb") as datei:
                shutil.copyfileobj(quelle, datei, 1 << 20)
    treffer = sorted(p for p in ziel.rglob("*")
                     if p.name.lower() == "upd-dev.txt"
                     and len(p.relative_to(ziel).parts) <= 2)
    if len(treffer) != 1:
        print(f"Im ZIP liegen {len(treffer)} Dateien upd-dev.txt "
              f"(erwartet: genau eine).")
        return 1
    print(treffer[0].parent)
    return 0


if __name__ == "__main__":
    sys.exit(main())
