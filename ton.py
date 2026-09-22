#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Der eine Ort, an dem sounddevice geladen wird.

Warum ueberhaupt: "import sounddevice" ruft Pa_Initialize(). Auf einem
Rechner ohne angemeldete Sitzung gibt es keinen PulseAudio-Server, und
ein PortAudio, das mit Pulse-Backend gebaut ist, bricht dort schon beim
Laden ab:

    PortAudioError: Error querying device -1
    PulseAudio_Initialize: Can't connect to server

Gemessen auf Ubuntu 26.04, headless. Der Fehler flog bisher durch
rate_waehlen, _starten und main() aus dem Prozess. systemd startete neu,
mit Restart=always und ohne StartLimit -- eine Schleife, die auf dem
Gemeinderechner den Zaehler 42 erreicht hat.

Ein fehlendes PortAudio ist aber kein Grund, den Server zu beenden. Ohne
Ton bleibt alles andere sinnvoll: das Pult ist erreichbar, es sagt, was
fehlt, und pruefen.sh kann es melden. Genau dafuer gibt es den Zustand
"wartet auf Tonquelle" schon.

Deshalb hier: genau einmal laden, Fehler behalten statt werfen, und
jedem Aufrufer die Wahl lassen. Wer sd braucht, fragt holen(); kommt
None zurueck, gibt es auf diesem Rechner keinen Ton, und grund() sagt
warum.
"""

import os
import sys
import threading
from contextlib import contextmanager

_schloss = threading.Lock()
_sd = None
_grund = ""
_versucht = False


@contextmanager
def stumm():
    """Haelt stderr zu, solange PortAudio hineinredet.

    ALSA schreibt ueber die C-Schicht direkt auf Dateideskriptor 2:

        Expression 'ret' failed in src/hostapi/alsa/pa_linux_alsa.c

    Hunderte Zeilen je Aufzaehlung, auf einem Rechner mit vielen
    ALSA-Pseudogeraeten. Ein logging-Filter erreicht das nicht -- es geht
    an Python vorbei. Also wird der Deskriptor selbst umgelenkt und
    danach zurueckgelegt.

    Eng geklammert und nicht global: was der Server selbst auf stderr
    schreibt, soll im Journal stehen bleiben. Zugehalten wird nur
    waehrend Pa_Initialize und der Geraeteaufzaehlung.
    """
    sys.stderr.flush()
    try:
        alt = os.dup(2)
    except OSError:
        # Kein Deskriptor 2 -- dann gibt es auch nichts zuzuhalten.
        yield
        return
    leer = None
    try:
        leer = os.open(os.devnull, os.O_WRONLY)
        os.dup2(leer, 2)
        yield
    finally:
        try:
            sys.stderr.flush()
        except Exception:
            pass
        os.dup2(alt, 2)
        os.close(alt)
        if leer is not None:
            os.close(leer)


def holen():
    """Gibt das sounddevice-Modul zurueck, oder None.

    Nur der erste Aufruf laedt wirklich. Danach steht das Ergebnis fest:
    ein zweiter Versuch waere entweder ueberfluessig oder wuerde denselben
    Fehler noch einmal ins Journal schreiben."""
    global _sd, _grund, _versucht
    with _schloss:
        if _versucht:
            return _sd
        _versucht = True
        try:
            with stumm():
                import sounddevice as sd
            _sd = sd
        except Exception as e:
            _sd = None
            _grund = f"{type(e).__name__}: {str(e).strip()[:200]}"
            print("TON: sounddevice liess sich nicht laden.")
            print(f"  {_grund}")
            print("  Ohne PortAudio gibt es auf diesem Rechner keine "
                  "Aufnahme.")
            print("  Der Server laeuft weiter; das Pult ist erreichbar und")
            print("  meldet, dass keine Tonquelle da ist. Haeufigste "
                  "Ursache:")
            print("  kein PulseAudio, weil niemand angemeldet ist. Siehe")
            print("  AUFSTELLEN.md, Abschnitt Tonquelle ohne Sitzung.")
        return _sd


def da():
    """Kurzform fuer 'laesst sich hier ueberhaupt aufnehmen'."""
    return holen() is not None


def grund():
    """Warum nicht, als eine Zeile. Leer, solange es geht."""
    holen()
    return _grund
