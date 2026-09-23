#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Liest einen Messlauf aus und sagt, wo die Zeit bleibt.

    python auswertung.py ergebnisse/messung/20260920_213000
    python auswertung.py                 # nimmt den juengsten Lauf

Vier Fragen, in dieser Reihenfolge:

  1. Wie lange dauert jede Stufe?           Median und p90 je Stufe
  2. Waechst der Rueckstau?                 Schlangentiefe ueber den Lauf
  3. Ist er ueberhaupt vermeidbar?          Realtime-Faktor je Sprache
  4. Was hoert der Zuhoerer davon?          Luecken und Verwuerfe

Frage 3 ist die wichtigste. Der Realtime-Faktor ist

    erzeugte Piper-Audiodauer / Laenge des aufgenommenen Abschnitts

kumuliert ueber den Lauf. Liegt er ueber 1,0, erzeugt der Server mehr Ton
als in derselben Zeit gesprochen wurde. Dann ist Rueckstau strukturell und
keine Puffergroesse hilft, sie verschiebt ihn nur nach hinten. Dieselbe
Groesse misst laengenfaktor.py offline gegen woerter.json; hier kommt sie
aus dem Livelauf.

Nur Standardbibliothek.
"""

import argparse
import csv
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import config


def p90(werte):
    if not werte:
        return None
    geordnet = sorted(werte)
    # Ohne numpy: der Rang, unter dem 90 Prozent liegen. Bei wenigen
    # Werten ist das der vorletzte -- ehrlicher als eine Interpolation,
    # die Genauigkeit vortaeuscht, die die Stichprobe nicht hergibt.
    i = min(len(geordnet) - 1, int(round(0.9 * (len(geordnet) - 1))))
    return geordnet[i]


def zahl(wert):
    try:
        return float(wert)
    except (TypeError, ValueError):
        return None


def spanne(zeile, von, bis):
    a, b = zahl(zeile.get(von)), zahl(zeile.get(bis))
    return None if a is None or b is None else b - a


def block(titel):
    print()
    print(titel)
    print("-" * len(titel))


def lauf_waehlen(pfad):
    if pfad:
        return Path(pfad)
    basis = config.ERGEBNIS_ORDNER / "messung"
    laeufe = sorted(p for p in basis.glob("*") if (p / "segmente.csv").exists())
    if not laeufe:
        sys.exit(f"Keine Messung unter {basis}. "
                 f"Lief der Server mit config.MESSUNG = True?")
    return laeufe[-1]


# ------------------------------------------------------------ Stufen

def stufen(zeilen):
    block("1. Wie lange dauert jede Stufe?")
    messungen = [
        ("Whisper      ", "whisper_start", "whisper_ende"),
        ("Uebersetzung ", "llm_start", "llm_ende"),
        ("Piper        ", "piper_start", "piper_ende"),
        ("Warten davor ", "audio_ende", "whisper_start"),
        ("Kette gesamt ", "audio_ende", "ws_send"),
    ]
    print(f"{'Stufe':14} {'n':>5} {'Median':>9} {'p90':>9} {'max':>9}")
    for name, von, bis in messungen:
        werte = [w for w in (spanne(z, von, bis) for z in zeilen)
                 if w is not None]
        if not werte:
            print(f"{name} {'--':>5}")
            continue
        print(f"{name} {len(werte):5d} {statistics.median(werte):8.2f}s "
              f"{p90(werte):8.2f}s {max(werte):8.2f}s")
    print()
    print("  \"Warten davor\" ist die Zeit in der Schlange, bevor die Arbeit")
    print("  anfaengt. Sie steht in KEINER Zahl am Pult -- die dortige Zahl")
    print("  beginnt erst beim Herausnehmen des Segments.")


# ------------------------------------------------------------ Rueckstau

def rueckstau(zeilen):
    block("2. Waechst der Rueckstau?")
    # Je Segment nur einmal: die Schlangentiefe gilt dem Segment, nicht
    # jeder einzelnen Sprache.
    je_segment = {}
    for z in zeilen:
        nr = zahl(z.get("segment"))
        if nr is None:
            continue
        je_segment.setdefault(int(nr), (zahl(z.get("schlange_ein")),
                                        zahl(z.get("schlange_aus"))))
    if not je_segment:
        print("  Keine Segmente.")
        return
    folge = [je_segment[k][0] for k in sorted(je_segment)
             if je_segment[k][0] is not None]
    if not folge:
        print("  Keine Schlangentiefen aufgezeichnet.")
        return

    drittel = max(1, len(folge) // 3)
    anfang = statistics.median(folge[:drittel])
    ende = statistics.median(folge[-drittel:])
    print(f"  Segmente: {len(folge)}")
    print(f"  Tiefe erstes Drittel (Median): {anfang:.1f}")
    print(f"  Tiefe letztes Drittel (Median): {ende:.1f}")
    print(f"  Hoechststand: {max(folge):.0f}")

    # Verlauf in zehn Stufen, damit man das Wachsen sieht statt es zu
    # erschliessen.
    schritt = max(1, len(folge) // 10)
    punkte = [folge[i] for i in range(0, len(folge), schritt)][:10]
    print("  Verlauf: " + " ".join(f"{w:.0f}" for w in punkte))

    if ende > anfang + 1:
        print("  => Die Tiefe WAECHST. Rueckstau ist da.")
    elif max(folge) <= 1:
        print("  => Kein Rueckstau. Die Schlange bleibt leer.")
    else:
        print("  => Die Tiefe schwankt, waechst aber nicht. Kein Dauerrueckstau.")


# ------------------------------------------------------- Realtime-Faktor

def realtime(zeilen, kopf):
    block("3. Realtime-Faktor je Sprache (die entscheidende Zahl)")
    ton = defaultdict(float)
    original = defaultdict(float)
    quelle = defaultdict(bool)
    verlauf = defaultdict(list)
    for z in zeilen:
        sp = z.get("sprache")
        t, o = zahl(z.get("ton_audio_s")), zahl(z.get("segment_audio_s"))
        if not sp or t is None or o is None or o <= 0:
            continue
        ton[sp] += t
        original[sp] += o
        quelle[sp] = quelle[sp] or z.get("ist_quelle") == "1"
        verlauf[sp].append(ton[sp] / original[sp])

    if not ton:
        print("  Keine Tondauern aufgezeichnet.")
        return

    # Bis 0.2.10 stand hier eine einzige Zahl. Aeltere Messungen
    # tragen sie noch, neuere eine Tabelle -- beide muessen lesbar
    # bleiben, sonst sind die alten Laeufe stumm.
    tempo = (kopf or {}).get("live_tempo")
    if tempo:
        print(f"  LIVE_TEMPO = {tempo} ist bereits eingerechnet: Piper")
        print(f"  spricht um diesen Faktor schneller. (Messung vor 0.2.11)")
    tabelle = (kopf or {}).get("tempo")
    if tabelle:
        print(f"  Tempo je Stimme, Aufschlag {tabelle.get('aufschlag')}, "
              f"global {tabelle.get('global')}.")
        je = tabelle.get("je_stimme") or {}
        if je:
            # Nur die Stimmen, um die es in diesem Lauf ging. Die ganze
            # Tabelle waeren sechsundzwanzig Eintraege auf einer Zeile,
            # und davon liest niemand mehr etwas.
            gefragt = {k: v for k, v in sorted(je.items())
                       if k.split("_")[0].lower() in ton}
            if gefragt:
                print("  Eingerechnet:")
                for k, v in gefragt.items():
                    print(f"    {k:32} {v}")
            print(f"  ({len(je)} Stimmen in der Tabelle insgesamt)")
    print()
    print(f"{'Sprache':9} {'Ton':>9} {'Original':>10} {'RTF':>7}   Urteil")
    for sp in sorted(ton):
        f = ton[sp] / original[sp]
        if quelle[sp]:
            urteil = "Quellsprache, per Bau 1,00"
        elif f > 1.0:
            urteil = "UEBER 1,0 -- Rueckstau unvermeidbar"
        elif f > 0.9:
            urteil = "knapp, kein Puffer"
        else:
            urteil = "haelt mit"
        print(f"{sp:9} {ton[sp]:8.1f}s {original[sp]:9.1f}s "
              f"{f:7.2f}   {urteil}")

    print()
    print("  Kumulierter Verlauf (Anfang -> Ende des Laufs):")
    for sp in sorted(verlauf):
        reihe = verlauf[sp]
        schritt = max(1, len(reihe) // 8)
        punkte = [reihe[i] for i in range(0, len(reihe), schritt)][:8]
        print(f"    {sp:4} " + " ".join(f"{w:.2f}" for w in punkte)
              + f"  (letzter {reihe[-1]:.2f})")


# ------------------------------------------------------------ Wiedergabe

def wiedergabe(pfad):
    block("4. Was hoert der Zuhoerer?")
    datei = pfad / "wiedergabe.csv"
    if not datei.exists():
        print("  Keine wiedergabe.csv.")
        return
    zeilen = list(csv.DictReader(datei.open(encoding="utf-8")))
    if not zeilen:
        print("  Keine Zeilen. Lief ein Handy mit ?debug=1 und stand")
        print("  config.MESSUNG_WIEDERGABE auf True?")
        return

    nach_art = defaultdict(int)
    for z in zeilen:
        nach_art[z.get("ereignis", "?")] += 1
    geraete = {z.get("hoerer") for z in zeilen}
    print(f"  {len(geraete)} Geraet(e), {len(zeilen)} Zeilen")
    for art in sorted(nach_art):
        print(f"    {art:12} {nach_art[art]}")

    luecken = [zahl(z.get("luecke_s")) for z in zeilen
               if z.get("ereignis") == "start"]
    luecken = [w for w in luecken if w is not None]
    if luecken:
        print()
        print(f"  Luecken zwischen den Haeppchen (n={len(luecken)}):")
        print(f"    Median {statistics.median(luecken):.2f}s   "
              f"p90 {p90(luecken):.2f}s   max {max(luecken):.2f}s")
        # Eine Lucke unter 0,15 s hoert niemand -- das ist die Zeit, die
        # das Audio-Element ohnehin zum Umschalten braucht.
        hoerbar = [w for w in luecken if w >= 0.15]
        print(f"    davon hoerbar (>= 0,15 s): {len(hoerbar)} "
              f"({100.0 * len(hoerbar) / len(luecken):.0f} %)")

    verworfen = [z for z in zeilen if z.get("ereignis") == "verworfen"]
    if verworfen:
        print()
        print(f"  VERWORFEN: {len(verworfen)} Haeppchen, weil die Schlange")
        print(f"  auf dem Handy voll war (Ton.hoechstens = 6).")
        zeitpunkte = sorted(w for w in (zahl(z.get("t")) for z in verworfen)
                            if w is not None)
        if zeitpunkte:
            print(f"    erster bei {zeitpunkte[0]:.1f}s, "
                  f"letzter bei {zeitpunkte[-1]:.1f}s")
            nummern = sorted(int(n) for n in
                             (zahl(z.get("segment")) for z in verworfen)
                             if n is not None)
            if nummern:
                print(f"    Segmente: "
                      + ", ".join(str(n) for n in nummern[:20])
                      + (" ..." if len(nummern) > 20 else ""))
        print("    Jedes davon ist eine Luecke mitten im Satz.")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("ordner", nargs="?", help="Messordner. Ohne Angabe der juengste.")
    a = p.parse_args()

    pfad = lauf_waehlen(a.ordner)
    seg = pfad / "segmente.csv"
    if not seg.exists():
        sys.exit(f"{seg} gibt es nicht.")
    zeilen = list(csv.DictReader(seg.open(encoding="utf-8")))

    kopf = None
    kopfdatei = pfad / "lauf.json"
    if kopfdatei.exists():
        try:
            kopf = json.loads(kopfdatei.read_text(encoding="utf-8"))
        except Exception:
            kopf = None

    print(f"Messlauf: {pfad}")
    if kopf:
        print(f"  Fassung {kopf.get('fassung')}, Modell {kopf.get('modell')}, "
              f"Betrieb {kopf.get('betrieb')}")
        print(f"  Sprachen {kopf.get('sprachen')}, "
              f"Pool {kopf.get('pool_groesse')} fuer "
              f"{kopf.get('sprachzahl')} Sprache(n)")
        if (kopf.get("pool_groesse") is not None
                and kopf.get("sprachzahl") is not None
                and kopf["pool_groesse"] < kopf["sprachzahl"] + 1):
            print("  ACHTUNG: Der Pool ist kleiner als die Sprachzahl + 1.")
            print("  Er wird beim Start dimensioniert und bei einer Umstellung")
            print("  am Pult nicht nachgezogen. Die Sprachen liefen dann NICHT")
            print("  vollstaendig gleichzeitig.")
    print(f"  {len(zeilen)} Zeilen")

    if not zeilen:
        sys.exit("Keine Segmentzeilen.")

    stufen(zeilen)
    rueckstau(zeilen)
    realtime(zeilen, kopf)
    wiedergabe(pfad)
    print()


if __name__ == "__main__":
    main()
