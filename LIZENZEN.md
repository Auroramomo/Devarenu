# Lizenzen

Der Code von Devarenu steht unter MIT, siehe `LICENSE`.

Die Modelle und Stimmen sind **nicht** Teil dieses Repos. `einrichten.sh`
lädt sie von den Anbietern, dort gelten deren Bedingungen.

## Bausteine

| Baustein | Wofür | Lizenz |
|---|---|---|
| Whisper-Modell (OpenAI) | Spracherkennung | MIT |
| faster-whisper | führt das Modell aus | MIT |
| Piper (`piper-tts`) | Sprachausgabe | **GPLv3 oder später** — siehe unten |
| Piper-Stimmen | je Sprache eine | unterschiedlich, siehe unten |
| Ollama | führt das Übersetzungsmodell aus | MIT |
| `gemma4:12b` | Übersetzung | Gemma Terms of Use |
| PyTorch | Rechenbibliothek | BSD 3-Clause |
| FastAPI | Webserver | MIT |
| uvicorn | führt FastAPI aus | BSD 3-Clause |
| transformers, sentencepiece | Modellwerkzeuge | Apache 2.0 |
| requests | HTTP-Aufrufe | Apache 2.0 |
| numpy | Zahlen | BSD 3-Clause |
| sounddevice | Toneingang | MIT |
| websockets | Verbindung zu den Zuhörern | BSD 3-Clause |
| segno | QR-Codes | siehe Projektseite |
| python-multipart | Datei-Uploads | siehe Projektseite |

Wo „siehe Projektseite" steht, habe ich die Lizenz nicht selbst geprüft.
Vor einer kommerziellen Nutzung nachsehen.

## Zwei Sonderfälle

**Gemma** steht nicht unter einer OSI-Lizenz, sondern unter den Gemma
Terms of Use. Weitergabe und Nutzung sind erlaubt, es gelten aber
Nutzungsbeschränkungen. Wer das Modell weitergibt, muss die Bedingungen
mitgeben.

**Aya Expanse ist CC-BY-NC**, also nicht kommerziell nutzbar. Es lief nur
im Test und ist in `config.py` auskommentiert. Es darf nicht in eine
Veröffentlichung geraten.

## Piper ist GPLv3 — und das ist ungeklärt

**Der Stand, nachgesehen im installierten Paket:**

```
piper-tts 1.7.0   GPL-3.0-or-later
.venv/…/piper_tts-1.7.0.dist-info/licenses/COPYING
  → GNU GENERAL PUBLIC LICENSE Version 3
```

In dieser Tabelle stand bis 0.3.5 „MIT". Das war einmal richtig: das
ursprüngliche `rhasspy/piper` stand unter MIT. Das Paket, das hier
läuft, ist der Nachfolger `OHF-voice/piper1-gpl` — der Name sagt es
schon. Der Eintrag ist mit dem Paket veraltet, nicht falsch
abgeschrieben worden.

**Wie Piper hier benutzt wird:** als Python-Modul im selben Prozess.

```python
from piper import PiperVoice
self.stimmen[sp] = PiperVoice.load(str(datei))
```

Das ist der Fall, den die GPL streng sieht. Ein Programm, das eine
GPL-Bibliothek importiert und mit ihr in einem Prozess läuft, gilt
nach Auffassung der Free Software Foundation als abgeleitetes Werk —
dann müsste das Ganze unter GPLv3 stehen, und „MIT" im Repo wäre
nicht haltbar. Ob Gerichte das genauso sehen, ist seit Jahren
umstritten und für Python-Importe nirgends entschieden.

> **Das ist keine Rechtsberatung, und es ist nicht entschieden.**
> Hier steht der Sachverhalt, damit jemand entscheiden kann.

### Die Wege, und was sie kosten

**(a) Das Repo auf GPLv3 umstellen.** Die ehrlichste Lesart, und die
einfachste: ein Satz in `LIESMICH.md`, eine Datei `COPYING`, fertig.
Kosten: wer Devarenu in etwas Geschlossenes einbauen will, kann es
dann nicht mehr. Für ein Programm, das Gemeinden kostenlos benutzen
sollen, ist das kein Verlust — eher das Gegenteil. Alle anderen
Bausteine (MIT, BSD, Apache) sind mit GPLv3 verträglich.

**(b) Piper als eigenen Prozess aufrufen.** Statt `import piper` ein
Aufruf der Kommandozeile, wie ihn `laengenfaktor.py` ohnehin schon
benutzt (`sprich()`). Zwei getrennte Programme, die über Dateien
reden — das ist die Konstellation, bei der auch die FSF keine
Ableitung sieht. Kosten: ein Prozessstart je Abschnitt statt eines
geladenen Modells. Gemessen ist das **nicht**; es wäre vor einer
Umstellung zu messen, und im Gottesdienst zählt jede Zehntelsekunde.
Dazu mehr bewegliche Teile an der Stelle, die heute verlässlich
läuft.

**(c) Bei MIT bleiben und nichts tun.** Ehrlich benannt: das hieße,
eine ungeklärte Frage offen stehen zu lassen und zu hoffen, dass sie
niemand stellt. Der Eintrag oben stimmt jetzt wenigstens.

### Empfehlung

**(a).** Der Nutzen von MIT ist hier gering — das Programm richtet
sich an Gemeinden, nicht an Firmen, die es einbauen wollen. Der
Aufwand ist eine Stunde. (b) löst dieselbe Frage, kostet aber
Rechenzeit an der einzigen Stelle, an der der Gottesdienst sie
merkt, und niemand hat gemessen, wie viel.

Die Bitte in `LIESMICH.md`, veränderte Fassungen nicht unter dem
Namen Devarenu weiterzugeben, ist davon **unberührt**. Sie ist keine
Lizenzbedingung und wird unter GPLv3 auch keine: die GPL erlaubt das
Weitergeben ausdrücklich. Es ist eine Bitte, begründet mit dem
Spendenkonto und der Prüfung, und sie steht unter MIT wie unter GPL
auf demselben Grund — nämlich auf keinem rechtlichen.

*Entschieden ist nichts. Solange hier nichts anderes steht, gilt für
den eigenen Code weiter MIT.*

## Piper-Stimmen

Die Stimmen haben je eigene Lizenzen, meist Creative Commons mit
Namensnennung. Welche für eine bestimmte Stimme gilt, steht in ihrer
Modellkarte:

<https://huggingface.co/rhasspy/piper-voices>

Wer Devarenu öffentlich einsetzt und die Sprachausgabe nutzt, sollte die
Nennung der verwendeten Stimmen bereithalten.

## Logo

`logo.png` ist das Signet der Siebenten-Tags-Adventisten und eine
eingetragene Marke der Generalkonferenz. Es fällt **nicht** unter die
MIT-Lizenz dieses Projekts. Gemeinden anderer Konfessionen ersetzen die
Datei durch ihr eigenes Zeichen.

## Bibelnamen

`namen_block_b.csv` enthält Eigennamen und Kapitelangaben, die mit
`namen_aus_bibel.py` aus einem Bibeltext extrahiert wurden. Namen und
Stellenangaben sind Fakten, kein Textauszug.
