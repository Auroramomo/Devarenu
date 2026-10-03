# Lizenzen

Der Code von Devarenu steht unter **GPLv3 oder später**, siehe
`COPYING`. Bis einschließlich Fassung 0.3.6 stand er unter MIT; der
Grund für den Wechsel steht weiter unten. Was unter MIT
veröffentlicht wurde, bleibt unter MIT — eine Lizenz lässt sich
nicht rückwirkend zurücknehmen. Ab 0.3.7 gilt GPLv3.

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

## Warum GPLv3 — die Entscheidung und ihr Grund

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

> **Das ist keine Rechtsberatung.** Hier steht der Sachverhalt und
> was daraus entschieden wurde.

### Die drei Wege, die zur Wahl standen

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

### Entschieden: (a), seit Fassung 0.3.7

Der Nutzen von MIT war hier gering — das Programm richtet sich an
Gemeinden, nicht an Firmen, die es einbauen wollen. (b) hätte
dieselbe Frage gelöst, aber Rechenzeit an der einzigen Stelle
gekostet, an der der Gottesdienst sie merkt, und niemand hatte
gemessen, wie viel.

Umgesetzt ist: `COPYING` mit dem GPLv3-Text (die Fassung von
gnu.org, inhaltlich dieselbe, die Piper selbst mitliefert), die
MIT-Datei `LICENSE` ist entfernt, `LIESMICH.md` und dieser Abschnitt
sind angepasst. Im Quelltext standen keine MIT-Kopfzeilen, also war
dort nichts zu ändern.

Alle anderen Bausteine (MIT, BSD, Apache) sind mit GPLv3 verträglich
und bleiben, wie sie sind.

Die Bitte in `LIESMICH.md`, veränderte Fassungen nicht unter dem
Namen Devarenu weiterzugeben, wird davon **nicht** zur Bedingung.
Die GPL erlaubt das Weitergeben ausdrücklich, und daran soll sich
nichts ändern. Es bleibt eine Bitte, begründet mit dem Spendenkonto
und der Prüfung — und sie steht unter GPL auf demselben Grund wie
vorher unter MIT: auf keinem rechtlichen.

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
GPLv3 dieses Projekts. Gemeinden anderer Konfessionen ersetzen die
Datei durch ihr eigenes Zeichen.

## Die ausgelieferten Piper-Stimmen

Erhoben mit `werkzeuge/stimmlizenzen.py` aus der `MODEL_CARD` jeder
Stimme im Repo `rhasspy/piper-voices` — derselben Quelle, aus der
`einrichten.sh` sie holt. Stand 0.4.0.

Genannt ist die Lizenz des **Datensatzes**, auf dem die Stimme
trainiert wurde. Ob ein daraus trainiertes Modell dieselbe Beschränkung
erbt, ist eine Rechtsfrage, die dieses Projekt nicht entscheidet — es
legt sie offen.

| Sprache | Stimme | Lizenz des Datensatzes | Anmerkung |
|---|---|---|---|
| Arabisch | `ar_JO-kareem-medium` | „See URL" | **unklar** |
| Tschechisch | `cs_CZ-jirka-medium` | CC0 | |
| Deutsch | `de_DE-thorsten-medium` | CC0 | |
| Griechisch | `el_GR-rapunzelina-medium` | CC0 | |
| Englisch | `en_US-lessac-medium` | Blizzard 2013 (Lessac/Voice Factory) | **nur Forschung** |
| Spanisch | `es_MX-claude-high` | Apache-2.0 | |
| Persisch | `fa_IR-amir-medium` | CC0 | |
| Französisch | `fr_FR-siwis-medium` | CC-BY 4.0 | |
| Ungarisch | `hu_HU-anna-medium` | CC0 | |
| Italienisch | `it_IT-paola-medium` | „See URL" | **unklar** |
| Georgisch | `ka_GE-natia-medium` | „See LICENSE file" (RHVoice) | **unklar** |
| Niederländisch | `nl_NL-mls-medium` | CC-BY 4.0 | |
| Polnisch | `pl_PL-darkman-medium` | CC0 | |
| Portugiesisch | `pt_BR-jeff-medium` | CC0 | |
| Rumänisch | `ro_RO-mihai-medium` | CC0 | |
| **Russisch** | `ru_RU-irina-medium` | „Unknown" (RHVoice) | **keine Lizenz genannt** |
| Serbisch | `sr_RS-serbski_institut-medium` | CC-BY-NC-SA 4.0 | **nichtkommerziell** |
| Suaheli | `sw_CD-lanfrica-medium` | „See URL" | **unklar** |
| Türkisch | `tr_TR-dfki-medium` | CC-BY-NC-SA 4.0 | **nichtkommerziell** |
| Ukrainisch | `uk_UA-ukrainian_tts-medium` | CC0 | |
| Vietnamesisch | `vi_VN-vais1000-medium` | CC-BY 4.0 | |

### Zwei davon laufen in Rostock

**Englisch** ist der schwerere Fall. Die Blizzard-2013-Lizenz von
Lessac Technologies / Voice Factory gewährt die Nutzung „**exclusively
for Research Purposes only**", nicht übertragbar, ohne Recht zur
Unterlizenzierung ([Lizenztext][bl13]). Ein Gottesdienst ist keine
Forschung. Das betrifft den Datensatz; `rhasspy/piper-voices` gibt die
daraus trainierten Gewichte trotzdem weiter, und ob die Beschränkung
mitwandert, ist offen. **Nicht entfernt**, aber hiermit festgehalten:
wer das klären will, hat hier den Link. Ein Ausweg wäre eine englische
Stimme auf CC0-Daten.

**Russisch** nennt gar keine Lizenz: die `MODEL_CARD` sagt „Unknown",
und das RHVoice-Repository `irina-rus` führt keine Lizenzdatei (die
RHVoice-*Software* ist GPL-2.0, die Stimmdaten sind davon getrennt).
Ohne Lizenz gibt es keine ausdrückliche Erlaubnis.

Die übrigen fünf markierten Stimmen (Arabisch, Italienisch, Georgisch,
Suaheli, Serbisch, Türkisch) sind **nicht eingeschaltet** — sie liegen
im Repo und laufen nur, wenn eine Gemeinde sie am Pult wählt. Die zwei
mit `NC` schließen eine kommerzielle Nutzung aus; eine Gemeinde handelt
nicht kommerziell, aber Devarenu wird weitergegeben, und das ist der
Punkt, an dem „nichtkommerziell" unbestimmt wird.

**Es ist nichts entfernt worden.** Diese Tabelle ist die Grundlage für
eine Entscheidung, nicht die Entscheidung.

[bl13]: https://www.cstr.ed.ac.uk/projects/blizzard/2013/lessac_blizzard2013/license.html

## Spracherkennung und Sprachmodell

| Baustein | Was | Lizenz |
|---|---|---|
| `faster-whisper` | Laufzeit der Spracherkennung | MIT |
| `CTranslate2` | Rechenkern darunter | MIT |
| Whisper `large-v3-turbo` | das Modell selbst, von OpenAI | MIT |
| Gemma (`gemma4`) | das Übersetzungsmodell, über Ollama | **Gemma Terms of Use** — keine Open-Source-Lizenz, mit Nutzungsbeschränkungen (*Prohibited Use Policy*) |
| Ollama | Laufzeit des Sprachmodells | MIT |
| `piper-tts` | Sprachausgabe, in-process importiert | **GPL-3.0-or-later** — der Grund, warum Devarenu selbst GPLv3 ist |

Die **Gemma-Bedingungen** sind keine freie Lizenz. Sie erlauben
Weitergabe und Betrieb, binden den Empfänger aber an dieselben
Bedingungen und verbieten bestimmte Verwendungen. Devarenu liefert das
Modell nicht mit — `einrichten.sh` holt es über Ollama, und damit
nimmt es jede Gemeinde selbst entgegen. Das ist der Unterschied
zwischen Mitliefern und Verweisen, und er ist Absicht.

## Bibelnamen

`namen_block_b.csv` enthält Eigennamen und Kapitelangaben, die mit
`namen_aus_bibel.py` aus einem Bibeltext extrahiert wurden. Namen und
Stellenangaben sind Fakten, kein Textauszug.

Seit 0.4.0 ist die Quelle die **Schlachter (1951)**, kapitelweise über
[api.getbible.net](https://api.getbible.net) — dieselbe Übersetzung,
aus der auch `zaehlung.json` stammt, und ihrem Alter nach gemeinfrei.
Der Text wird geholt, ausgezählt und **weggeworfen**: in der Datei
stehen 2538 Zeilen mit Name, Häufigkeit, Streuung und Kapitelliste.
Keine Zeile Bibeltext.

## Bibelstellen-Zählungen

`zaehlung.json` enthält, um wie viel sich eine Kapitel- oder
Versangabe zwischen zwei Zählungen verschiebt. Gebaut von
`werkzeuge/zaehlung_bauen.py` aus den **Verszahlen** dreier
Übersetzungen, abgerufen über [api.getbible.net](https://api.getbible.net):

| Kürzel | Übersetzung | Zählung | Rechtsstand |
|---|---|---|---|
| `schlachter` | Schlachter (1951) | hebräisch/masoretisch | gemeinfrei |
| `kjv` | King James Version (1611/1769) | englisch | gemeinfrei |
| `synodal` | Synodal-Übersetzung (1876) | Septuaginta (Psalmen) | gemeinfrei |

**Gespeichert werden ausschließlich Zahlen** — Kapitel, Vers, Versatz.
Keine Zeile Bibeltext, in keiner Sprache. Zahlen sind Fakten und kein
Werk; dasselbe Argument gilt schon für `namen_block_b.csv`. Alle drei
Übersetzungen sind ihrem Alter nach ohnehin gemeinfrei. Die Datei ist
unter 5 kB groß — wer sie öffnet, sieht, dass darin nichts anderes
steht.

Dass die Schlachter **2000** dieselbe Zählung hat wie die 1951, ist an
vier Stellen geprüft (`pruefstand/zaehlung_test.py`); beide folgen dem
masoretischen Text.
