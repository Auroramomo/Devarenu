#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Nimmt Ton auf und schickt ihn an den GemeindeKI-Server.

Laeuft auf einem beliebigen Rechner in der Gemeinde und braucht nichts
ausser sounddevice, websockets und numpy. Kein Whisper, kein Ollama, keine
Modelle: die Arbeit macht der Server.

Gesendet wird 16 kHz Mono als 16-Bit-Ganzzahlen, also rund 256 kbit/s.
Das traegt jeder Anschluss. Umgerechnet wird schon hier, damit ueber die
Leitung nicht das Dreifache geht.

Aufruf:
    python sender.py --geraete
    python sender.py --ziel wss://name.trycloudflare.com --geraet 11
    python sender.py --ziel ws://10.0.0.1:8000 --geraet 11
"""

import argparse
import asyncio
import sys
import time

import numpy as np
import sounddevice as sd
import websockets

RATE = 16000          # was der Server erwartet
BLOCK = 512           # gut 30 ms, dieselbe Groesse wie im Server


def auf_16k(block, rate):
    """Rechnet einen Audioblock auf 16000 Hz herunter.

    Erst ein gleitender Mittelwert als Tiefpass, sonst wird alles oberhalb
    von 8 kHz zurueckgefaltet und landet als tieferes Rauschen im Signal.
    Dann die Ratenaenderung, bei 48000 exakt, bei 44100 interpoliert."""
    if rate == RATE:
        return block
    faktor = rate / RATE
    ganz = int(faktor)
    if ganz > 1:
        rest = len(block) % ganz
        gefiltert = (block[:-rest] if rest else block).reshape(-1, ganz).mean(axis=1)
    else:
        gefiltert = block
    if abs(faktor - ganz) < 1e-9:
        return gefiltert
    ziel = int(round(len(block) / faktor))
    return np.interp(np.linspace(0, len(gefiltert) - 1, ziel),
                     np.arange(len(gefiltert)), gefiltert).astype(np.float32)


def geraete_zeigen():
    apis = {i: a["name"] for i, a in enumerate(sd.query_hostapis())}
    rang = {"MME": 0, "Windows WASAPI": 1, "Windows DirectSound": 2,
            "Windows WDM-KS": 9}
    zeilen = []
    for i, g in enumerate(sd.query_devices()):
        if g["max_input_channels"] > 0:
            api = apis.get(g["hostapi"], "?")
            zeilen.append((rang.get(api, 5), i, g["name"], api,
                           int(g["default_samplerate"])))
    print("Aufnahmegeraete, empfohlene zuerst:\n")
    print(f"  {'Nr':>3}  {'Schnittstelle':20} {'Hz':>6}  Name")
    for r, i, name, api, hz in sorted(zeilen):
        marke = "  " if r < 5 else " !"
        print(f"{marke}{i:3}  {api:20} {hz:6}  {name}")
    print("\n  ! = WDM-KS, greift exklusiv zu und scheitert haeufig.")
    print("\n  Stereomix nimmt auf, was der Rechner ausgibt. Gut zum Testen:")
    print("  eine Aufnahme abspielen und schauen, ob sie ankommt.")


def rate_waehlen(geraet, wunsch=None, kanaele=1):
    for rate in ([wunsch] if wunsch else [48000, 44100, 96000, 32000, 16000]):
        try:
            sd.check_input_settings(device=geraet, channels=kanaele,
                                    samplerate=rate, dtype="float32")
            return rate
        except Exception:
            continue
    raise SystemExit("Keine der ueblichen Aufnahmeraten funktioniert. "
                     "Anderes Geraet waehlen oder --rate erzwingen.")


async def senden(a):
    kanaele = max(a.kanal,
                  1 if a.kanal <= 1 else 2)
    rate = rate_waehlen(a.geraet, a.rate, kanaele)
    ziel = a.ziel.rstrip("/") + f"/audio?schluessel={a.schluessel}"
    print(f"Aufnahme  {rate} Hz -> {RATE} Hz, Kanal {a.kanal}")
    print(f"Ziel      {ziel.split('?')[0]}")

    schlange = asyncio.Queue(maxsize=200)
    schleife = asyncio.get_running_loop()
    zustand = {"pegel": 0.0, "gesendet": 0, "verloren": 0}

    def rueckruf(daten, rahmen, zeit, status):
        # Ein Mischpult liefert mehrere Kanaele gleichzeitig. Welcher das
        # Predigtmikrofon fuehrt, haengt vom Routing am Pult ab und laesst
        # sich nur messen, nicht raten. Siehe pegel.py.
        spur = min(a.kanal - 1, daten.shape[1] - 1)
        block = auf_16k(daten[:, spur].copy(), rate)
        zustand["pegel"] = float(np.sqrt(np.mean(block.astype(np.float64) ** 2)))
        # In 16 Bit umrechnen: halbiert die Datenmenge, und feiner braucht
        # es Whisper nicht.
        roh = (np.clip(block, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
        try:
            schleife.call_soon_threadsafe(schlange.put_nowait, roh)
        except Exception:
            # Schlange voll: lieber einen Block verwerfen als Rueckstau
            # aufbauen, der die Latenz dauerhaft erhoeht.
            zustand["verloren"] += 1

    strom = sd.InputStream(device=a.geraet, channels=kanaele, samplerate=rate,
                           blocksize=int(BLOCK * rate / RATE),
                           dtype="float32", callback=rueckruf)

    async def anzeige():
        while True:
            await asyncio.sleep(1.0)
            p = zustand["pegel"]
            balken = "#" * min(30, int(p * 300))
            hinweis = "  Ton kommt an" if p > 0.004 else "  still"
            verlust = (f"  {zustand['verloren']} verworfen"
                       if zustand["verloren"] else "")
            print(f"\r  [{balken:<30}] {p:.4f}{hinweis}{verlust}   ",
                  end="", flush=True)

    with strom:
        print("Mikrofon offen.\n")
        anzeiger = asyncio.create_task(anzeige())
        try:
            while True:
                try:
                    async with websockets.connect(ziel, max_queue=64,
                                                  ping_interval=20) as draht:
                        print("\nVerbunden.\n")
                        while True:
                            block = await schlange.get()
                            await draht.send(block)
                            zustand["gesendet"] += 1
                except (OSError, websockets.WebSocketException) as e:
                    print(f"\nVerbindung weg ({str(e)[:70]}), neuer Versuch "
                          f"in 3 s ...")
                    # Aufgestaute Bloecke wegwerfen: sie sind beim
                    # Wiederverbinden veraltet und wuerden den Ton
                    # zeitversetzt einspielen.
                    while not schlange.empty():
                        schlange.get_nowait()
                    await asyncio.sleep(3)
        finally:
            anzeiger.cancel()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--geraete", action="store_true")
    p.add_argument("--geraet", type=int, default=None)
    # Keine Vorgabe mehr. Frueher stand hier eine Adresse von zu Hause;
    # wer --ziel vergass, suchte ein Netz, das es vor Ort nicht gibt,
    # und bekam nur "verbindet nicht" ohne zu erfahren wohin.
    p.add_argument("--ziel", required=True,
                   help="wss://... fuer den Tunnel, ws://... im selben Netz")
    p.add_argument("--schluessel", default="gemeinde",
                   help="muss zum Server passen")
    p.add_argument("--kanal", type=int, default=1,
                   help="welcher Kanal des Geraets, 1 oder 2. "
                        "Herausfinden mit pegel.py")
    p.add_argument("--rate", type=int, default=None)
    a = p.parse_args()

    if a.geraete:
        geraete_zeigen()
        return
    if a.geraet is None:
        sys.exit("Kein Geraet gewaehlt. Erst: python sender.py --geraete")

    try:
        asyncio.run(senden(a))
    except KeyboardInterrupt:
        print("\nBeendet.")


if __name__ == "__main__":
    main()
