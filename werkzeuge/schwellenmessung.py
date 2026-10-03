#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vergleicht die drei Schwellenmodi an derselben Aufnahme.

Der Befund aus Rostock war, dass der Helfer die Schwelle jeden
Gottesdienst auf null stellt, weil mit Automatik oder eingemessener
Schwelle MEHR Erkennungsfehler kommen als ohne. Das ist eine Aussage
ueber die Segmentierung, und sie laesst sich messen: dieselbe Predigt,
dreimal durch denselben Segmentierer und dasselbe Whisper, nur die
Schwelle anders.

Gemessen wird ausdruecklich NICHT die Uebersetzung. Zwischen den Modi
unterscheidet sich, WO geschnitten wird und was daraufhin erkannt wird --
alles dahinter haengt nur daran. Deshalb laeuft hier kein Ollama und kein
Piper, und der Lauf dauert Minuten statt Stunden.

Auch nicht in Echtzeit: die Bloecke gehen so schnell durch, wie der
Rechner kann. Fuer Latenz ist server.py --datei zustaendig, hier geht es
um Schnitte und Woerter.

Aufruf:
    python werkzeuge/schwellenmessung.py predigt2.mp3
    python werkzeuge/schwellenmessung.py predigt2.mp3 --rauschen rausch.wav
    python werkzeuge/schwellenmessung.py predigt2.mp3 --minuten 5
"""

import argparse
import statistics
import sys
import time
from pathlib import Path

import numpy as np

BASIS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASIS))

import config                                            # noqa: E402
import server                                            # noqa: E402


def laden(pfad, rate):
    from faster_whisper.audio import decode_audio
    return np.asarray(decode_audio(str(pfad), sampling_rate=rate),
                      dtype=np.float32)


def rauschen_unterlegen(audio, rausch, anteil):
    """Legt eine Rauschdatei unter den Ton, in Schleife, auf Pegelanteil.

    Der Anteil gilt dem Effektivwert: 0.3 heisst, das Rauschen hat
    dreissig Prozent des Effektivwerts der Predigt. Lauter waere kein
    Raumrauschen mehr, sondern ein zweiter Sprecher."""
    if len(rausch) == 0:
        return audio
    wdh = int(np.ceil(len(audio) / len(rausch)))
    lang = np.tile(rausch, wdh)[:len(audio)]
    p_audio = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
    p_rausch = float(np.sqrt(np.mean(lang.astype(np.float64) ** 2))) or 1e-9
    return np.clip(audio + lang * (p_audio * anteil / p_rausch), -1.0, 1.0)


def lauf(audio, werk, modus, fester_wert, args):
    """Ein Durchgang. Gibt die Zahlen zurueck, die den Modus beschreiben."""
    seg = server.Segmentierer(pause=args.pause, min_dauer=args.min_dauer,
                              max_dauer=args.max_dauer,
                              min_sprachdauer=args.min_sprachdauer)
    seg.modus = modus
    seg.feste_schwelle = fester_wert if modus == "fest" else None

    laengen, texte = [], []
    erfunden = 0
    leer = 0
    blocks = server.BLOCK
    rate = server.MIKRO_RATE
    t0 = time.perf_counter()
    i = 0
    while i + blocks <= len(audio):
        stueck = seg.schub(audio[i:i + blocks])
        i += blocks
        if stueck is None:
            continue
        laengen.append(len(stueck) / rate)
        vorher = werk.erfunden_zahl
        text = werk.hoeren(stueck)
        if werk.erfunden_zahl > vorher:
            erfunden += 1
        if not text:
            leer += 1
        else:
            texte.append(text)
    dauer = time.perf_counter() - t0

    woerter = sum(len(t.split()) for t in texte)
    # "An der Hoechstdauer geschnitten" heisst: der Abschnitt lief voll,
    # es gab keine Pause, an der sich schneiden liess. Ein kleiner
    # Spielraum, weil der letzte Block nicht genau aufgeht.
    grenze = args.max_dauer - (blocks / rate) - 0.01
    amrand = sum(1 for d in laengen if d >= grenze)
    return {
        "modus": modus,
        "schwelle": (f"{fester_wert:.5f}" if modus == "fest"
                     else ("0.00050" if modus == "aus" else "Grundpegel x 3,5")),
        "abschnitte": len(laengen),
        "laenge_median": statistics.median(laengen) if laengen else 0.0,
        "laenge_p10": (sorted(laengen)[int(len(laengen) * 0.10)]
                       if laengen else 0.0),
        "laenge_p90": (sorted(laengen)[int(len(laengen) * 0.90)]
                       if laengen else 0.0),
        "laenge_min": min(laengen) if laengen else 0.0,
        "laenge_max": max(laengen) if laengen else 0.0,
        "amrand": amrand,
        "amrand_anteil": (amrand / len(laengen) * 100) if laengen else 0.0,
        "erfunden": erfunden,
        "leer": leer,
        "verworfen": seg.verworfen,
        "woerter": woerter,
        "rechenzeit": dauer,
    }


def einmessen_auf(audio, args):
    """Was das Einmessen auf DIESER Datei ergeben wuerde.

    Dieselbe Auswertung wie am Pult, nur ueber die ganze Datei statt
    ueber zwoelf Sekunden. Ein Einmessen auf zwoelf zufaellig gewaehlten
    Sekunden waere nicht reproduzierbar und damit keine Messung."""
    seg = server.Segmentierer()
    seg.messung = {"bis": time.time() + 1e9, "werte": []}
    blocks = server.BLOCK
    i = 0
    while i + blocks <= len(audio):
        seg.messung["werte"].append(seg.pegel(audio[i:i + blocks]))
        i += blocks
    erg = seg.einmessen_auswerten()
    return erg


def zeile(e):
    return (f"| {e['modus']:<12} | {e['schwelle']:>16} | {e['abschnitte']:>5} "
            f"| {e['laenge_median']:>5.2f} | {e['laenge_p10']:>5.2f} "
            f"| {e['laenge_p90']:>5.2f} | {e['laenge_max']:>5.2f} "
            f"| {e['amrand']:>4} ({e['amrand_anteil']:>4.1f}%) "
            f"| {e['erfunden']:>4} | {e['leer']:>4} | {e['verworfen']:>4} "
            f"| {e['woerter']:>6} |")


def tabelle(ergebnisse, titel):
    print(f"\n{titel}")
    print("| Modus        |          Schwelle | Absch "
          "| Med. | p10  | p90  | max  | an Hoechstdauer "
          "| ERF. | leer | verw | Woerter |")
    print("|--------------|-------------------|-------"
          "|------|------|------|------|-----------------"
          "|------|------|------|---------|")
    for e in ergebnisse:
        print(zeile(e))


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("datei")
    p.add_argument("--rauschen", default=None,
                   help="Rauschdatei, die unter den Ton gelegt wird")
    p.add_argument("--rauschanteil", type=float, default=0.3)
    p.add_argument("--minuten", type=float, default=0.0,
                   help="nur die ersten N Minuten, zum Ausprobieren")
    p.add_argument("--pause", type=float, default=0.45)
    p.add_argument("--min-dauer", type=float, default=1.6)
    p.add_argument("--max-dauer", type=float, default=8.0)
    p.add_argument("--min-sprachdauer", type=float, default=0.9)
    args = p.parse_args()

    pfad = Path(args.datei)
    if not pfad.exists():
        sys.exit(f"Nicht gefunden: {pfad}")

    rate = server.MIKRO_RATE
    print(f"Lade {pfad.name} ...")
    audio = laden(pfad, rate)
    if args.minuten:
        audio = audio[:int(args.minuten * 60 * rate)]
    print(f"{len(audio)/rate/60:.1f} Minuten Ton.")

    print("Whisper laedt ...")
    # nur_text: Piper wird nicht gebraucht. Gemessen wird, WO
    # geschnitten wird und was daraufhin erkannt wird.
    werk = server.Werk(nur_text=True)
    print(f"Rechenwerk: {werk.rechenwerk}")

    gemessen = einmessen_auf(audio, args)
    if gemessen and gemessen.get("erfolg"):
        fest = gemessen["schwelle"]
        print(f"Einmessen auf dieser Datei: {fest:.5f}  ({gemessen['text']})")
    else:
        fest = 0.0060
        print(f"Einmessen ergab nichts Brauchbares, ersatzweise {fest:.5f}")

    laeufe = [("aus", None), ("automatisch", None), ("fest", fest)]

    ergebnisse = []
    for modus, wert in laeufe:
        print(f"\n--- {modus} ---")
        werk.erfunden_zahl = 0
        werk.verlauf.clear()
        e = lauf(audio, werk, modus, wert, args)
        print(f"    {e['abschnitte']} Abschnitte, {e['woerter']} Woerter, "
              f"{e['rechenzeit']:.0f}s Rechenzeit")
        ergebnisse.append(e)
    tabelle(ergebnisse, "OHNE zusaetzliches Rauschen")

    if args.rauschen:
        rp = Path(args.rauschen)
        if not rp.exists():
            print(f"\nRauschdatei nicht gefunden: {rp} -- weggelassen.")
        else:
            laut = rauschen_unterlegen(audio, laden(rp, rate),
                                       args.rauschanteil)
            mit = []
            for modus, wert in laeufe:
                print(f"\n--- {modus} + Rauschen ---")
                werk.erfunden_zahl = 0
                werk.verlauf.clear()
                mit.append(lauf(laut, werk, modus, wert, args))
            tabelle(mit, f"MIT Rauschen ({args.rauschanteil:.0%} des "
                         f"Effektivwerts)")
    else:
        print("\nKein Rauschen unterlegt (keine Rauschdatei angegeben).")


if __name__ == "__main__":
    main()
