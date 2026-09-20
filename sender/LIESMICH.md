# Sender-Laptop

Zwei Werkzeuge für den Fall, dass der Ton auf einem **anderen** Rechner
ankommt als dem, der übersetzt. Sie laufen nicht auf dem Gemeinde-PC,
sondern auf dem Rechner am Mischpult, und brauchen kein Whisper, kein
Ollama und keine Modelle.

    python -m pip install sounddevice websockets numpy

## Herkunft

Beide Dateien lagen am 20.09.2026 **nur noch im Papierkorb** und waren nie
in diesem Repo. Die Fassungen hier sind die vom 21.08.2026 — die einzigen
mit Kanalwahl. Ältere Kopien ohne `--kanal` liegen in
`~/Videos/ProjektRostockStadt/` und auf `/mnt/B/SettingsAI/`; die sind
überholt.

Unverändert übernommen. Wer sie anfasst, sollte vorher den Abschnitt
"Stand" unten lesen.

## pegel.py

Zeigt, auf welchem Kanal Ton ankommt. Ein Mischpult wie der SQ5 meldet
sich als vier Stereogeräte; welcher der acht Kanäle das Predigtmikrofon
führt, sieht man nicht am Namen.

    python pegel.py

Der Gemeinde-PC braucht das nicht mehr: seit 0.2.3 zeigt das Pult selbst
einen Pegel je Kanal und kann auf Knopfdruck prüfen, ob Sprache anliegt.
Für den Sender-Laptop bleibt `pegel.py` sinnvoll, weil dort kein Pult
läuft.

## sender.py

Nimmt auf und schickt 16 kHz Mono als 16-Bit-Ganzzahlen an den Server,
rund 256 kbit/s. Verbindet bei Abbruch selbst neu und wirft Aufgestautes
weg, statt den Ton zeitversetzt nachzuspielen.

    python sender.py --geraete
    python sender.py --ziel ws://<server-ip>:8000 --geraet <Nr> --kanal 2

Der Server muss dafür mit `--netz` laufen; ohne das legt er gar keine
Netz-Tonquelle an. Der Schlüssel (`--schluessel`, Vorgabe `gemeinde`) muss
zu dem des Servers passen.

## Zählweise der Kanäle

`--kanal` zählt **ab 1**: 1 ist links oder mono, 2 ist rechts. Innen wird
auf den Index ab 0 heruntergerechnet. `server.py` zählt seit 0.2.3 genauso
— auf dem SQ5 und auf jedem Kabel steht keine Null.

## Stand: läuft gegen 0.2.3 (geprüft 20.09.2026)

Das Protokoll hat sich seit dem 21.08. nicht geändert. Nachgemessen:

- `sender.py` verbindet sich auf `/audio?schluessel=…`, der Server nimmt
  an, und sein Pegel folgt dem, was der Sender anzeigt.
- Der Server meldet "Audioquelle verbunden" und zählt die Blöcke.
- Ein falscher Schlüssel wird mit Code 1008 abgewiesen.
- `websockets` 17.1 nimmt die Aufrufe unverändert entgegen.

Nicht geprüft: Windows, WDM-KS, und der Dauerlauf über eine Predigt.
