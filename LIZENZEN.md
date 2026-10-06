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
| Arabisch | ~~`ar_JO-kareem-medium`~~ | keine genannt (0.4.3 nachgesehen) | **keine Lizenz — seit 0.4.5 nicht mehr ausgeliefert** |
| Tschechisch | `cs_CZ-jirka-medium` | CC0 | |
| Deutsch | `de_DE-thorsten-medium` | CC0 | |
| Griechisch | `el_GR-rapunzelina-medium` | CC0 | |
| Englisch | `en_US-lessac-medium` | Blizzard 2013 (Lessac/Voice Factory) | **nur Forschung** |
| Spanisch | `es_MX-claude-high` | Apache-2.0 | |
| Persisch | `fa_IR-amir-medium` | CC0 | |
| Französisch | `fr_FR-siwis-medium` | CC-BY 4.0 | |
| Ungarisch | `hu_HU-anna-medium` | CC0 | |
| Italienisch | `it_IT-paola-medium` | CC0 1.0 (0.4.3 nachgesehen) | geklärt |
| Georgisch | ~~`ka_GE-natia-medium`~~ | nur Privatpersonen (0.4.3 nachgesehen) | **Organisationen untersagt — seit 0.4.5 nicht mehr ausgeliefert** |
| Niederländisch | `nl_NL-mls-medium` | CC-BY 4.0 | |
| Polnisch | `pl_PL-darkman-medium` | CC0 | |
| Portugiesisch | `pt_BR-jeff-medium` | CC0 | |
| Rumänisch | `ro_RO-mihai-medium` | CC0 | |
| **Russisch** | `ru_RU-irina-medium` | „Unknown" (RHVoice) | **keine Lizenz genannt** |
| Serbisch | `sr_RS-serbski_institut-medium` | CC-BY-NC-SA 4.0 | **nichtkommerziell** |
| Suaheli | `sw_CD-lanfrica-medium` | keine formale, „non-profit, educational, public benefit" (0.4.3) | eingeschränkt |
| Türkisch | `tr_TR-dfki-medium` | CC-BY-NC-SA 4.0 | **nichtkommerziell** |
| Ukrainisch | uk_UA-mykyta-high | Apache 2.0 | Trainingsweg laut Modellkarte nicht angegeben |
| Vietnamesisch | `vi_VN-vais1000-medium` | CC-BY 4.0 | |

Ukrainisch ist mit 0.5.0 von `uk_UA-ukrainian_tts-medium` (CC0) auf
`uk_UA-mykyta-high` umgestellt. Die Modellkarte nennt als Datensatz
<https://github.com/egorsmkv/ukrainian-tts-datasets> unter Apache 2.0
und verweist für das Training nur auf
<https://huggingface.co/RomanStasyshyn/uk_UA-mykyta-high>. Die alte
Stimme wird nicht mehr mitgeliefert; wo sie liegt, bleibt sie liegen
— Devarenu löscht keine Stimmen.

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

Die übrigen markierten Stimmen (Italienisch, Suaheli, Serbisch,
Türkisch) sind **nicht eingeschaltet** — sie laufen nur, wenn eine
Gemeinde sie am Pult wählt. Die zwei mit `NC` schließen eine
kommerzielle Nutzung aus; eine Gemeinde handelt nicht kommerziell, aber
Devarenu wird weitergegeben, und das ist der Punkt, an dem
„nichtkommerziell" unbestimmt wird.

### Zwei Stimmen sind mit 0.4.5 herausgenommen — 04.10.2026

**`ka_GE-natia-medium` (Georgisch)** und **`ar_JO-kareem-medium`
(Arabisch)** stehen seit dieser Fassung nicht mehr in
`config.STIMMEN`, nicht mehr in `teile.json`, nicht mehr auf dem Stick
und nicht mehr im Vorrat.

**Warum.** „Nicht eingeschaltet" war die falsche Antwort. Beide lagen
trotzdem auf jedem Stick und in jedem Vorrat, und ein Stick wird von
Gemeinde zu Gemeinde weitergereicht — das ist Weitergabe, unabhängig
davon, ob jemand die Sprache am Pult wählt.

* Georgisch ist **ausdrücklich** nur für Privatpersonen freigegeben,
  Organisationen sind untersagt. Eine Gemeinde ist eine Organisation.
  Das ist kein Graubereich, sondern ein geschriebenes Verbot.
* Arabisch nennt **gar keine** Lizenz. Ohne Lizenz gibt es keine
  Erlaubnis zur Weitergabe.

**Was sich dadurch ändert.** Georgisch und Arabisch laufen als reiner
Untertitel weiter — Text ja, Ton nein, genau wie jede andere Sprache
ohne Stimme. Am Pult bleiben sie wählbar.

**Was sich NICHT ändert.** Dateien, die schon auf einem Rechner liegen,
werden von keinem Update gelöscht. Devarenu löscht grundsätzlich keine
Stimmen; was dort liegt, gehört dem Rechner. Ein Update bringt sie nur
nicht mehr mit.

**Rostock** ist nicht betroffen: dort laufen `en`, `ru` und `fa`.

Die gemessenen Längenfaktoren beider Stimmen bleiben in
`config.TEMPO_STIMME` und `messungen/laengenfaktor_stimmen.json`
stehen. Sie sind Messwerte und kein Vertriebsweg; nachgeschlagen werden
sie nicht mehr.

### Die vier „See URL" — mit 0.4.3 nachgelesen

Vier Stimmen verwiesen auf eine Quelle, ohne die Lizenz zu nennen. Was
dort steht:

| Stimme | Quelle | Was dort steht |
|---|---|---|
| `ar_JO-kareem-medium` | [arabicttstrain][arjo] | **Nichts.** Das Repository führt keine Lizenzdatei und keine Lizenzangabe. Ohne Lizenz gibt es keine ausdrückliche Erlaubnis — dieselbe Lage wie bei Russisch. |
| `it_IT-paola-medium` | [Voice-Dataset-Italian][itit] | **CC0 1.0.** Damit ist dieser Fall erledigt. |
| `sw_CD-lanfrica-medium` | [Kiswahili TTS Dataset][swcd] | Keine formale Lizenz, aber ein Satz: „The authors permit use for non-profit, educational, and public benefit purposes." Eine Gemeinde fällt darunter. Weitergabe an andere Gemeinden ist davon gedeckt, der Verkauf nicht. |
| `ka_GE-natia-medium` | [RHVoice, `licenses/voices/natia`][kage] | **Ausdrücklich eingeschränkt:** „can be used free of charge **only by individuals for personal use**" und „It is **prohibited** to copy, modify, distribute, sell or use this voice **by Organizations**". Eine Gemeinde, die sie auf einem Stick weitergibt, ist eine Organisation. |

[arjo]: https://github.com/AliMokhammad/arabicttstrain/
[itit]: https://huggingface.co/datasets/paolapersico1/Voice-Dataset-Italian
[swcd]: https://lanfrica.com/record/kiswahili-tts-dataset
[kage]: https://github.com/Olga-Yakovleva/RHVoice/blob/master/licenses/voices/natia/license-eng.txt

### Die Kandidaten für Englisch und Russisch

Bestätigt am `MODEL_CARD` im Piper-Vorrat:

| Stimme | Datensatz | Lizenz des Datensatzes | Trainiert |
|---|---|---|---|
| `en_US-joe-medium` | [OHF-Voice/voice-datasets][ohf] | **CC0** | feinabgestimmt aus `lessac` |
| `en_US-ljspeech-medium` | [LJ Speech][ljs] | **public domain** | **von Grund auf** |
| `ru_RU-dmitri-medium` | [OHF-Voice/voice-datasets][ohf] | **CC0** | feinabgestimmt aus `lessac` |
| `ru_RU-denis-medium` | [OHF-Voice/voice-datasets][ohf] | **CC0** | feinabgestimmt aus `lessac` |

[ohf]: https://github.com/OHF-Voice/voice-datasets
[ljs]: https://keithito.com/LJ-Speech-Dataset/

> **Das ist der Haken, und er war vorher nicht gesehen.** Drei der
> vier Kandidaten sind aus `en_US-lessac-medium` feinabgestimmt — also
> aus genau der Stimme, deren Lizenz „nur Forschung" sagt und derer
> man sich entledigen wollte. Ob eine Beschränkung auf die daraus
> weitertrainierten Gewichte durchschlägt, ist dieselbe offene Frage
> wie oben bei Englisch, nur eine Stufe später. Fast jede Piper-Stimme
> ist so entstanden; auch Arabisch, Italienisch, Suaheli und Georgisch
> tragen den Satz „Finetuned from U.S. English lessac voice".
>
> **`en_US-ljspeech-medium` ist die einzige in dieser Liste, die von
> Grund auf trainiert wurde** — sie ist damit die einzige, bei der
> sich die Frage gar nicht stellt. Für Russisch gibt es in dieser
> Auswahl keine solche Stimme.
>
> Das ist eine Feststellung, keine Empfehlung: `ljspeech` ist mit
> Längenfaktor 1,28 die langsamste der drei englischen Kandidaten,
> und wie sie klingt, entscheidet die Hörprobe (`AUFSTELLEN.md`).

**Es ist nichts entfernt worden.** Diese Tabelle ist die Grundlage für
eine Entscheidung, nicht die Entscheidung.

### Lizenzfreie Stimmen, die es stattdessen gibt

Erhoben aus denselben Modellkarten, über alle englischen und
russischen Stimmen in `rhasspy/piper-voices`. Für **beide** Problemfälle
gibt es Ersatz, und für Russisch sogar zwei Stimmen unter CC0:

Die Spalte *Tempo* ist der gemessene Längenfaktor gegen die deutsche
Stimme (`laengenfaktor.py --je-stimme`, 20 Sätze aus `ausschnitt.mp3`).
**Kleiner ist besser:** die Übersetzung braucht dann weniger Zeit als
das Original, und der Rückstand wächst nicht.

| Sprache | Stimme | Lizenz des Datensatzes | Tempo | Datensatz |
|---|---|---|---|---|
| **ru** | `ru_RU-dmitri-medium` | **CC0** | **0,92** | OHF-Voice/voice-datasets |
| **ru** | `ru_RU-denis-medium` | **CC0** | 1,14 | OHF-Voice/voice-datasets |
| ru | `ru_RU-ruslan-medium` | CC BY-NC-SA | — | ruslan-corpus |
| ru | `ru_RU-irina-medium` *(heute aktiv)* | **„Unknown"** | 1,22 | RHVoice |
| **en** | `en_US-joe-medium` | **CC0** | 1,15 | OHF-Voice/voice-datasets |
| **en** | `en_US-ljspeech-medium` | **public domain** | 1,28 | LJ Speech |
| en | `en_US-john-medium`, `-kristin-`, `-norman-`, `-bryce-` | public domain | — | LibriVox |
| en | `en_US-libritts_r-medium`, `-libritts-high` | CC BY 4.0 | — | openslr 141 / 60 |
| en | `en_US-sam-medium` | Apache-2.0 | — | Sam-Accenture |
| en | `en_US-kathleen-low` | CC0 | — | rhasspy |
| en | `en_US-ryan-*` | CC BY-NC-SA 4.0 | — | Kaggle |
| en | `en_US-lessac-*` *(heute aktiv)* | **nur Forschung** | 1,07 | Blizzard 2013 |

**Russisch wäre ein Gewinn in beide Richtungen.** `dmitri` ist
lizenzfrei **und** mit 0,92 schneller als die heutige `irina` (1,22) —
dreißig Prozent weniger Sprechzeit je Abschnitt. `denis` liegt bei
1,14 und ist damit auch noch besser.

**Englisch kostet etwas.** Die saubere Wahl `joe` (CC0) braucht 1,15
statt 1,07 — gut sieben Prozent mehr Sprechzeit. Das ist der Preis,
und er ist bezahlbar.

Damit ist der offene Punkt keine Rechtsfrage mehr, sondern eine
**Wahl**: welche Stimme soll die Gemeinde hören. Das entscheidet
niemand am Schreibtisch — das Projekt wählt Stimmen, indem ein
Muttersprachler drei Kandidaten anhört
(`werkzeuge/sprachpaket.py --bauen <sp>`), so wie es bei Spanisch und
Portugiesisch gelaufen ist.

**Gewechselt ist nichts.** Ein Stimmwechsel ändert, was die Zuhörer
hören, und gehört nicht in eine Lizenzaufräumung.

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
aus der auch `zaehlung.json` stammt. Sie ist **nicht gemeinfrei**
(© 1951 Genfer Bibelgesellschaft, „free non-commercial
distribution"); Devarenu gibt sie aber auch nicht weiter. Der Text
wird geholt, ausgezählt und **weggeworfen**: in der Datei stehen 2538
Zeilen mit Name, Häufigkeit, Streuung und Kapitelliste. Keine Zeile
Bibeltext. Näheres oben unter *Bibelstellen-Zählungen*.

## Bibelstellen-Zählungen

`zaehlung.json` enthält, um wie viel sich eine Kapitel- oder
Versangabe zwischen zwei Zählungen verschiebt. Gebaut von
`werkzeuge/zaehlung_bauen.py` aus den **Verszahlen** dreier
Übersetzungen, abgerufen über [api.getbible.net](https://api.getbible.net):

| Kürzel | Übersetzung | Zählung | Rechtsstand laut Quelle |
|---|---|---|---|
| `schlachter` | Schlachter (1951) | hebräisch/masoretisch | **© 1951 Genfer Bibelgesellschaft — „Copyrighted; Free non-commercial distribution"** |
| `kjv` | King James Version (1611/1769) | englisch | GPL |
| `synodal` | Synodal-Übersetzung (1876) | Septuaginta (Psalmen) | Public Domain |

Dieselbe Quelle liefert auch die Texte, gegen die die Buchnamen
geprüft wurden: `valera` (Reina Valera 1909, *Copyrighted, Weitergabe
an CrossWire erlaubt*), `sse` (Sagradas Escrituras 1569, Public
Domain), `almeida` (Almeida Atualizada, GPL), `livre` (Bíblia Livre,
CC BY 3.0 BR).

> **Berichtigung zu 0.4.0.** Dort stand, die Schlachter 1951 sei
> „ihrem Alter nach gemeinfrei". **Das ist falsch.** Die
> Lizenzangabe der Quelle lautet *Copyrighted; Free non-commercial
> distribution*, Rechteinhaber ist die Genfer Bibelgesellschaft.

**Darauf kommt es trotzdem nicht an, denn Devarenu gibt den Text
nicht weiter.** Er wird geholt, ausgezählt und weggeworfen. Im Repo
liegt keine Zeile Bibeltext und keine Bibel-PDF — nachzusehen mit

```fish
git ls-files | grep -iE '\.pdf$|bibel|schlachter'
```

Das findet sieben eigene Anleitungs-PDFs und vier Quelltextdateien,
sonst nichts.

Was bleibt, sind **Fakten über den Text**, nicht der Text:

| Datei | Inhalt | Größe |
|---|---|---|
| `zaehlung.json` | Kapitel, Vers, Versatz | unter 5 kB |
| `namen_block_b.csv` | Name, Häufigkeit, Streuung, Kapitelliste | 2538 Zeilen |

Wie viele Verse ein Kapitel hat und welcher Eigenname in welchem
Kapitel vorkommt, ist eine Tatsache über ein Werk und keine
Vervielfältigung davon. Dasselbe Argument trug schon `namen_block_b.csv`
in 0.3.x, als die Quelle eine gedruckte Studienbibel war.

**Wo der Volltext während des Laufs liegt:** in einem Wegwerfordner
unter `/tmp` (bei der Erstellung von 0.4.0:
`…/scratchpad/bibel/schlachter/*.json`, 8,3 MB, 66 Dateien). Er ist
nach der Sitzung weg und wird bei Bedarf neu geholt —
`werkzeuge/zaehlung_bauen.py` und `namen_aus_bibel.py --aus-bibeltext`
können beides.

Dass die Schlachter **2000** dieselbe Zählung hat wie die 1951, ist an
vier Stellen geprüft (`pruefstand/zaehlung_test.py`); beide folgen dem
masoretischen Text. **Für die Namensschreibung gilt das nicht
automatisch** — siehe die Annahme im Bericht zu dieser Nachbesserung.
