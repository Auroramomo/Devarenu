#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Zeigt an, auf welchem Kanal Ton ankommt.

Ein Mischpult wie der SQ5 meldet sich als mehrere Stereogeraete. Welcher
der acht Kanaele das Predigtmikrofon fuehrt, sieht man nicht am Namen,
sondern nur am Pegel. Dieses Werkzeug misst alle gleichzeitig und zeigt
Balken.

Aufruf:
    python pegel.py                 alle Geraete mit "SQ" im Namen
    python pegel.py --suche Realtek
    python pegel.py --geraet 1
"""

import argparse
import sys
import time

import numpy as np
import sounddevice as sd


def passende_geraete(suche, nur=None):
    """Nur MME-Eintraege: dieselbe Karte taucht unter mehreren
    Schnittstellen auf, und mehrfach gleichzeitig zu oeffnen scheitert.
    MME ist unter Windows die vertraeglichste."""
    apis = {i: a["name"] for i, a in enumerate(sd.query_hostapis())}
    treffer = []
    for i, g in enumerate(sd.query_devices()):
        if g["max_input_channels"] < 1:
            continue
        if nur is not None:
            if i == nur:
                treffer.append((i, g))
            continue
        if apis.get(g["hostapi"]) != "MME":
            continue
        if suche.lower() in g["name"].lower():
            treffer.append((i, g))
    return treffer


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--suche", default="SQ",
                   help="Namensteil der zu messenden Geraete")
    p.add_argument("--geraet", type=int, default=None,
                   help="nur dieses eine Geraet messen")
    p.add_argument("--sekunden", type=float, default=0,
                   help="nach dieser Zeit beenden, 0 = bis Strg+C")
    a = p.parse_args()

    geraete = passende_geraete(a.suche, a.geraet)
    if not geraete:
        print(f"Nichts gefunden zu \"{a.suche}\".")
        print("Alle Aufnahmegeraete: python sender.py --geraete")
        return

    spuren, stroeme = [], []
    for nummer, g in geraete:
        kanaele = min(2, g["max_input_channels"])
        rate = int(g["default_samplerate"])
        werte = [0.0] * kanaele
        spuren.append({"nr": nummer, "name": g["name"],
                       "kanaele": kanaele, "werte": werte, "spitze": [0.0] * kanaele})

        def macher(ziel):
            def rueckruf(daten, rahmen, zeit, status):
                for k in range(ziel["kanaele"]):
                    p = float(np.sqrt(np.mean(daten[:, k].astype(np.float64) ** 2)))
                    ziel["werte"][k] = p
                    ziel["spitze"][k] = max(p, ziel["spitze"][k] * 0.995)
            return rueckruf

        try:
            strom = sd.InputStream(device=nummer, channels=kanaele,
                                   samplerate=rate, blocksize=1024,
                                   dtype="float32",
                                   callback=macher(spuren[-1]))
            strom.start()
            stroeme.append(strom)
        except Exception as e:
            spuren[-1]["fehler"] = str(e)[:60]

    print(f"{len(spuren)} Geräte werden gemessen. Strg+C beendet.\n")
    print("Jetzt am Pult sprechen oder Musik einspielen. Wo ein Balken")
    print("ausschlägt, liegt das Signal.\n")

    beginn = time.time()
    zeilen = sum(s["kanaele"] for s in spuren) + 1
    try:
        erste = True
        while True:
            if not erste:
                # Zurueck an den Anfang der Ausgabe, damit die Balken an
                # Ort und Stelle bleiben statt durchzulaufen.
                sys.stdout.write(f"\033[{zeilen}A")
            erste = False
            for s in spuren:
                if "fehler" in s:
                    print(f"  {s['nr']:3} {s['name'][:26]:26} "
                          f"nicht nutzbar: {s['fehler']}")
                    continue
                for k in range(s["kanaele"]):
                    p, spitze = s["werte"][k], s["spitze"][k]
                    balken = "#" * min(34, int(p * 340))
                    marke = "  <-- HIER" if spitze > 0.01 else ""
                    print(f"  {s['nr']:3} {s['name'][:22]:22} K{k+1} "
                          f"[{balken:<34}] {p:.4f}{marke}   ")
            print(f"  {time.time()-beginn:.0f}s vergangen"
                  f"{' ':40}")
            if a.sekunden and time.time() - beginn > a.sekunden:
                break
            time.sleep(0.15)
    except KeyboardInterrupt:
        pass
    finally:
        for s in stroeme:
            s.stop(); s.close()

    print("\n\nErgebnis:")
    gefunden = False
    for s in spuren:
        if "fehler" in s:
            continue
        for k in range(s["kanaele"]):
            if s["spitze"][k] > 0.01:
                gefunden = True
                print(f"  Signal auf Gerät {s['nr']} ({s['name']}), "
                      f"Kanal {k+1}, Spitze {s['spitze'][k]:.3f}")
                print(f"    python sender.py --geraet {s['nr']} "
                      f"--kanal {k+1} --ziel wss://...")
    if not gefunden:
        print("  Auf keinem Kanal Signal.")
        print("  Dann liegt es am Pult: dort muss eingestellt werden, was")
        print("  auf die USB-Ausgänge geht. Sinnvoll wäre der Hauptmix oder")
        print("  ein eigener Aux-Weg mit nur dem Predigtmikrofon.")


if __name__ == "__main__":
    main()
