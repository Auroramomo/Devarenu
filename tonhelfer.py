#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Macht EIN Aufnahmegeraet auf, misst, gibt zurueck, endet.

Warum ein eigener Prozess, obwohl der Scan urspruenglich ausdruecklich
im Server laufen sollte: weil ein Treiber den Prozess mitnehmen kann,
der ihn aufmacht. Gemessen auf dem Entwicklungsrechner --

    libasound_module_pcm_upmix.so -> snd_pcm_area_copy -> Segfault

reproduzierbar beim ersten Block. Ein Segfault laesst sich nicht
abfangen: kein try, kein except, kein Signalhandler, der das
zuverlaessig ueberlebt. Im Serverprozess haette das den Gottesdienst
beendet, ausgeloest davon, dass jemand am Pult die Geraeteliste
aufgeklappt hat. Hier stirbt nur der Helfer, die Zeile im Pult sagt
"nicht lesbar", und der Scan geht zum naechsten Kanal.

Absichtlich duenn: numpy und sounddevice, sonst nichts. Der Helfer
wird je Messung neu gestartet, und jeder Import kostet diese Zeit
wieder. Gemessen sind rund 220 ms Start gegen 800 ms Messfenster.

Er rechnet NICHT auf 16 kHz herunter. Das tut der Aufrufer mit
auf_16k aus server.py -- dieselbe Funktion, die auch die Livepipeline
benutzt. Zwei Umrechnungen nebeneinander liefen sonst auseinander,
und die Sprachpruefung hoerte etwas anderes als der Server nachher.

Aufruf (nicht fuer die Hand gedacht, server.py ruft das):

    tonhelfer.py <geraet> <kanal> <kanaele> <dauer> <raten>

Ausgabe auf stdout: eine JSON-Zeile, danach die Rohdaten des
gewaehlten Kanals als float32. Die JSON-Zeile sagt, wie viele.
"""

import json
import sys


def scheitern(grund):
    """Sauber scheitern heisst: sagen warum, und mit 0 enden.

    Ein Rueckgabewert ungleich 0 ist dem Aufrufer vorbehalten, um
    einen Absturz von einem abgelehnten Geraet zu unterscheiden. Ein
    belegtes Mikrofon ist kein Absturz."""
    sys.stdout.write(json.dumps({"ok": False, "fehler": str(grund)[:200]}) + "\n")
    sys.stdout.flush()
    raise SystemExit(0)


def main():
    if len(sys.argv) != 6:
        scheitern("Aufruf: tonhelfer.py <geraet> <kanal> <kanaele> "
                  "<dauer> <raten>")
    try:
        geraet = int(sys.argv[1])
        kanal = int(sys.argv[2])
        kanaele = int(sys.argv[3])
        dauer = float(sys.argv[4])
        raten = [int(r) for r in sys.argv[5].split(",") if r.strip()]
    except ValueError as e:
        scheitern(f"unbrauchbare Angabe: {e}")

    import numpy as np
    import sounddevice as sd

    # Genau wie mikrofon_thread: Kanal 0 wird einkanalig aufgemacht und
    # aus Spalte 0 gelesen. Mehrkanalig nur fuer einen hinteren Kanal.
    # Ein Geraet, das 128 Kanaele meldet, wuerde sonst mit 128 geoeffnet,
    # um einen zu lesen.
    mehrkanal = kanal > 0
    offen_kanaele = kanaele if mehrkanal else 1
    spalte = kanal if mehrkanal else 0

    rate = blockgroesse = None
    for r in raten:
        try:
            sd.check_input_settings(device=geraet, channels=offen_kanaele,
                                    samplerate=r, dtype="float32")
            rate = r
            # Dieselbe Blockgroesse wie die Livepipeline: 512 Proben bei
            # 16000 Hz, hochgerechnet auf die Geraeterate.
            blockgroesse = int(round(512 * r / 16000))
            break
        except Exception:
            continue
    if rate is None:
        scheitern("keine brauchbare Aufnahmerate")

    stuecke = []
    spitze = [0.0]

    def rueckruf(daten, rahmen, zeit, status):
        spur = daten[:, spalte].copy()
        stuecke.append(spur)
        # Der Spitzenwert im Fenster, nicht der Mittelwert: gesucht ist,
        # ob ueberhaupt etwas anliegt, und ein einzelner Satz in 800 ms
        # verschwindet im Mittel.
        w = float(np.sqrt(np.mean(spur.astype(np.float64) ** 2)))
        if w > spitze[0]:
            spitze[0] = w

    try:
        import threading
        with sd.InputStream(device=geraet, channels=offen_kanaele,
                            samplerate=rate, blocksize=blockgroesse,
                            dtype="float32", callback=rueckruf):
            threading.Event().wait(dauer)
    except Exception as e:
        scheitern(str(e).replace("\n", " "))

    if not stuecke:
        scheitern("kein Block angekommen")

    roh = np.concatenate(stuecke).astype(np.float32)
    sys.stdout.write(json.dumps({
        "ok": True, "pegel": spitze[0], "rate": rate,
        "proben": int(len(roh)),
    }) + "\n")
    sys.stdout.flush()
    # Rohdaten hinterher, damit der Aufrufer sie mit derselben Funktion
    # herunterrechnet wie die Livepipeline.
    sys.stdout.buffer.write(roh.tobytes())
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
