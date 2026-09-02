# Lizenzen

Der Code von Devarenu steht unter MIT, siehe `LICENSE`.

Die Modelle und Stimmen sind **nicht** Teil dieses Repos. `einrichten.sh`
lädt sie von den Anbietern, dort gelten deren Bedingungen.

## Bausteine

| Baustein | Wofür | Lizenz |
|---|---|---|
| Whisper-Modell (OpenAI) | Spracherkennung | MIT |
| faster-whisper | führt das Modell aus | MIT |
| Piper (`piper-tts`) | Sprachausgabe | MIT |
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
