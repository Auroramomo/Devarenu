#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Uebersetzt dieselben Abschnitte mit und ohne Thema im Prompt.

Thema und Bibelstellen gehen bis 0.4.1 nur an Whisper. Ob es der
UEBERSETZUNG hilft, laesst sich nicht erraten: ein Hinweis mehr im
Prompt kann Namen treffsicherer machen -- und er kann einen Abschnitt
zum Thema hin verbiegen, der gar nicht davon handelt.

Darum derselbe Abschnitt zweimal, nebeneinander:

    python werkzeuge/themavergleich.py predigt2.mp3 \\
        --thema "Predigt ueber Vergebung. Texte: Matthaeus 18, Psalm 32." \\
        --abschnitte 20 --sprachen en,ru

Gemessen wird nicht "besser", das kann keine Maschine sagen. Gemessen
wird, WIE OFT und WIE WEIT sich etwas aendert -- und die Faelle stehen
zum Nachlesen daneben.
"""

import argparse
import difflib
import sys
import time
from pathlib import Path

import numpy as np

BASIS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASIS))

import config                                            # noqa: E402
import server                                            # noqa: E402


def abschnitte_holen(audio, werk, anzahl, args):
    """Die ersten N Abschnitte mit erkanntem Text."""
    seg = server.Segmentierer(pause=args.pause, min_dauer=args.min_dauer,
                              max_dauer=args.max_dauer)
    seg.modus = "aus"
    blocks, rate = server.BLOCK, server.MIKRO_RATE
    aus, i = [], 0
    while i + blocks <= len(audio) and len(aus) < anzahl:
        stueck = seg.schub(audio[i:i + blocks])
        i += blocks
        if stueck is None:
            continue
        text = werk.hoeren(stueck)
        if text and len(text.split()) >= 4:
            aus.append(text)
    return aus


def aehnlich(a, b):
    return difflib.SequenceMatcher(None, a, b).ratio()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("datei")
    p.add_argument("--thema", required=True)
    p.add_argument("--abschnitte", type=int, default=20)
    p.add_argument("--sprachen", default="en,ru")
    p.add_argument("--pause", type=float, default=0.45)
    p.add_argument("--min-dauer", type=float, default=1.6)
    p.add_argument("--max-dauer", type=float, default=8.0)
    a = p.parse_args()
    sprachen = [x.strip() for x in a.sprachen.split(",") if x.strip()]

    from faster_whisper.audio import decode_audio
    print(f"Lade {Path(a.datei).name} ...")
    audio = np.asarray(decode_audio(a.datei, sampling_rate=server.MIKRO_RATE),
                       dtype=np.float32)

    print("Whisper laedt ...")
    werk = server.Werk(nur_text=True)

    # Das Thema setzen -- derselbe Weg wie am Pult.
    from bibelstellen import aus_pulttext
    erg = aus_pulttext(a.thema, werk.namen, config.PROMPT_EINLEITUNG,
                       config.PROMPT_MAX_ZEICHEN)
    werk.stt_prompt = erg["prompt"]
    werk.stt_kopf = erg["kopf"]
    werk.stt_namen = list(erg["namen"])
    werk.kontext_stellen = erg["stellen"]
    werk.kontext_namen = erg["namen"]
    print(f"Thema: {len(werk.kontext_stellen)} Stellen, "
          f"{len(werk.kontext_namen)} Namen")

    print(f"Hole {a.abschnitte} Abschnitte ...")
    t0 = time.perf_counter()
    texte = abschnitte_holen(audio, werk, a.abschnitte, a)
    print(f"  {len(texte)} Abschnitte in {time.perf_counter()-t0:.0f}s")

    for sprache in sprachen:
        print(f"\n{'='*70}\n{sprache.upper()}\n{'='*70}")
        gleich, anders = 0, 0
        zeilen = []
        for n, text in enumerate(texte, 1):
            werk.thema_im_prompt = False
            ohne = werk.uebersetzen(text, sprache)
            werk.thema_im_prompt = True
            mit = werk.uebersetzen(text, sprache)
            werk.thema_im_prompt = False
            if ohne.strip() == mit.strip():
                gleich += 1
            else:
                anders += 1
                zeilen.append((n, text, ohne, mit, aehnlich(ohne, mit)))
        print(f"\n{gleich} von {len(texte)} Abschnitten Zeichen fuer "
              f"Zeichen gleich, {anders} anders.\n")
        for n, text, ohne, mit, q in zeilen:
            print(f"--- {n} (Aehnlichkeit {q:.2f})")
            print(f"    quelle: {text[:150]}")
            print(f"    ohne:   {ohne[:150]}")
            print(f"    mit:    {mit[:150]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
