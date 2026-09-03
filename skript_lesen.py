#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wertet ein Predigtmanuskript aus, ohne es vorzulesen.

Der Unterschied ist wichtig: das Manuskript wird NICHT als Textquelle
benutzt. Gesprochen wird, was gesprochen wird, und Prediger weichen ab,
kuerzen, schweifen aus. Wer das Manuskript ausliefert, merkt Abweichungen
nicht und uebersetzt am Ende etwas, das nie gesagt wurde.

Gezogen werden nur die Namen. An denen scheitert Whisper, und ein
Manuskript liefert genau die, die in keiner Bibelstelle stehen: Ortsnamen
aus einer Anekdote, ein zitierter Autor, ein hebraeischer Ausdruck.

Drei Quellen werden zusammengefuehrt:
  1. Bibelstellen im Text, daraus die Namen des Kapitels
  2. Woerter, die im Bibelnamensindex stehen (sicher Namen)
  3. Woerter, die nach der Begleiterpruefung Eigennamen sind (Rest)

Aufruf zum Ausprobieren:
    python skript_lesen.py predigt.docx
"""

import re
import sys
import zipfile
from pathlib import Path

from namen_aus_bibel import ABLEITUNGEN, KEINE_NAMEN, WORT, kandidaten


def text_aus_datei(pfad, rohdaten=None):
    """Liest txt, md oder docx.

    docx wird ohne Zusatzbibliothek gelesen: die Datei ist ein ZIP-Archiv
    mit XML darin. Eine Abhaengigkeit weniger, die bei einem
    Versionswechsel brechen kann."""
    pfad = Path(pfad)
    endung = pfad.suffix.lower()

    if endung == ".docx":
        quelle = rohdaten if rohdaten is not None else pfad
        with zipfile.ZipFile(quelle) as z:
            xml = z.read("word/document.xml").decode("utf-8", "replace")
        # Absatzenden zu Zeilenumbruechen, dann alle Auszeichnungen weg.
        xml = re.sub(r"</w:p>", "\n", xml)
        text = re.sub(r"<[^>]+>", "", xml)
        return re.sub(r"\n{3,}", "\n\n", text)

    if rohdaten is not None:
        roh = rohdaten.read() if hasattr(rohdaten, "read") else rohdaten
        for kodierung in ("utf-8", "cp1252", "latin-1"):
            try:
                return roh.decode(kodierung)
            except UnicodeDecodeError:
                continue
        return roh.decode("utf-8", "replace")

    for kodierung in ("utf-8", "cp1252", "latin-1"):
        try:
            return pfad.read_text(encoding=kodierung)
        except UnicodeDecodeError:
            continue
    return pfad.read_text(encoding="utf-8", errors="replace")


def auswerten(text, bibelindex=None, hoechstens=45):
    """Findet Bibelstellen und Namen im Manuskript.

    Ein Wort, das auch im Bibelnamensindex steht, ist sicher ein Name und
    kommt zuerst. Der Rest stammt aus der Begleiterpruefung, die bei einem
    kurzen Text ungenauer ist als bei einer ganzen Bibel: dort stuetzt sich
    die Quote auf hunderte Vorkommen, hier oft auf eines. Deshalb sind
    diese Namen nachrangig."""
    from bibelstellen import stellen_finden

    stellen = stellen_finden(text)

    bekannt = {e["de"] for e in bibelindex.eintraege} if bibelindex else set()

    # Erst alles, was im Bibelnamensindex steht, und zwar ohne die
    # Begleiterpruefung. Sonst faellt "auf dem Karmel" durch, weil ein
    # Artikel davorsteht: bei Ortsnamen mit Artikel ist die Heuristik
    # falsch, und hier ist sie auch unnoetig, weil das Wort bereits als
    # Name belegt ist.
    aus_text = set(WORT.findall(text))
    sicher = [w for w in aus_text if w in bekannt]

    # Danach die uebrigen, dort entscheidet die Begleiterpruefung.
    roh = kandidaten(text)
    unsicher = [w for w, _ in sorted(roh.items(), key=lambda x: -x[1])
                if w not in bekannt and len(w) >= 4
                and not w.lower().endswith(ABLEITUNGEN)]

    # Aus dem Manuskript stammende Namen stehen vorn: sie kommen garantiert
    # vor, waehrend die Namen aus einem Bibelkapitel nur vorkommen koennten.
    namen = []
    for wort in sicher + unsicher:
        if wort not in namen:
            namen.append(wort)

    return {"stellen": stellen, "namen": namen[:hoechstens],
            "sicher": len(sicher), "unsicher": len(unsicher),
            "woerter": len(text.split())}


def main():
    if len(sys.argv) < 2:
        sys.exit("Aufruf: python skript_lesen.py predigt.docx")
    import config
    from bibelstellen import Namensindex

    pfad = Path(sys.argv[1])
    if not pfad.exists():
        sys.exit(f"Nicht gefunden: {pfad}")

    text = text_aus_datei(pfad)
    index = Namensindex.laden(config.BASIS / "namen_block_b.csv")
    erg = auswerten(text, index)

    print(f"{pfad.name}: {erg['woerter']} Wörter")
    print(f"Bibelstellen: {', '.join(erg['stellen']) or 'keine'}")
    print(f"Namen: {erg['sicher']} aus dem Bibelindex, "
          f"{erg['unsicher']} weitere")
    print(f"\n{', '.join(erg['namen'])}")


if __name__ == "__main__":
    main()
