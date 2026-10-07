# Fahrplan zur 1.0

**Wann darf Devarenu an eine zweite Gemeinde?**

Heute läuft es in **einer** Gemeinde und wird dort erprobt. Die
Fassungen 0.3.x und 0.4.x sind diese Erprobung. Dieses Dokument sagt,
was erfüllt sein muss, bevor jemand anderes es aufstellt — und was
heute davon fehlt.

Die Antwort auf „ist es fertig?" lautet bis dahin: nein, und hier
steht warum.

*Stand: 0.5.0, 07.10.2026.*

---

## Wie dieses Dokument zu lesen ist

Drei Stufen, und die Einteilung ist der Kern:

| | |
|---|---|
| **Blocker** | Ohne das darf kein Gerät an eine zweite Gemeinde. Sechs Punkte. |
| **Sollte** | Gehört getan, hält aber nichts auf. Sechs Punkte. |
| **Nicht mehr auf der Liste** | Erledigt, entschieden oder als kein Hindernis erkannt. |

Die Nummern bleiben, wie sie waren: B4, B6 und S5 sind mit 0.5.0
entschieden und stehen jetzt unter *Nicht mehr auf der Liste*; B8 und
S7 sind neu. Eine Nummer, die wandert, findet niemand wieder.

Je Punkt drei Dinge: **Stand heute**, **was fehlt**, **wie man es
prüft**. Der dritte ist der wichtigste. Ein Punkt ohne Prüfweg ist
eine Meinung, kein Kriterium — und lässt sich nicht abhaken.

Was hier als erledigt gilt, muss **auf echter Hardware** erledigt
sein. Ein Prüfstand mit Attrappen belegt, dass der Code tut, was
gemeint war; er belegt nicht, dass es in einem Saal funktioniert.

**Die Blocker hängen zusammen, und zwar in dieser Reihenfolge:** erst
die Testumgebung (B2), dann ein Update-Weg, der sich darin und im Feld
bewährt (B1), und ganz zum Schluss **ein Monat Testphase** (B8) mit
genau der Fassung, die 1.0 werden soll. B3, B5 und B7 laufen daneben;
B7 kostet Zeit, die nicht technisch ist, und gehört darum früh
angestoßen.

### Was nur Menschen erledigen können

Kein Code bringt diese Punkte weiter. Sie stehen hier zusammen, damit
sie nicht zwischen den technischen untergehen:

| | Punkt |
|---|---|
| **Stick-Updates auf echter Hardware** — drei hintereinander, ohne Eingriff, dazu der Rückweg | B1 |
| **Erstinstallation durch Fremde** — jemand, der das Projekt nicht kennt | B5 |
| **Schlüssel sichern und eine zweite Person** | B3, S6 |
| **Kaltstart** — Stecker ziehen, Stecker rein, nichts anfassen | S3 |
| **iPhones** — Verbinden und Bildschirm anlassen | S4 |
| **Gespräch mit dem Datenschutzbeauftragten** — Freigabe des Entwurfs | B7 |

---

## Zwei Rechner, zwei Update-Wege

**Das ist die wichtigste Unterscheidung in diesem Dokument.**

| | Rostock, bis 1.0 | Rollout-Rechner |
|---|---|---|
| Internet | ja, über das Wartungs-WLAN | **nein** |
| Update | online, im Wartungsfenster oder per Knopf | **Stick rein, am Pult einspielen** |
| Wartungsfenster, Autoupdate, „Jetzt aus dem Netz" | **in Betrieb** | **gibt es dort nicht** |

Der **Online-Weg** — `aktualisieren.sh`, das Wartungsfenster, das
Autoupdate und der Knopf „Jetzt aus dem Netz aktualisieren" — gehört
zur **Erprobung in Rostock**. Er ist dort gebaut worden, weil ein
Rechner, an dem der Entwickler nicht sitzt, sich selbst auf Stand
halten muss, solange täglich etwas dazukommt.

**Ein Rechner im Rollout hat kein Internet.** Für ihn gilt der Weg,
den das Projekt von Anfang an hatte: **Stick einstecken, am Pult auf
„Jetzt einspielen" drücken.** Alles, was danach passiert — Signatur
prüfen, vorspulen, Units schreiben, Gesundheitscheck, bei einem
Fehler zurückrollen — ist für beide Wege dieselbe Logik
(`stick_update.sh` plus die versionierte `aktualisierung.sh`).

Was daraus folgt: **die Blocker-Liste prüft den Stick-Weg, nicht den
Online-Weg.** Der Online-Weg darf scheitern, ohne dass eine zweite
Gemeinde davon etwas merkt — er läuft dort nicht.

---

# Blocker

## B1. Der Stick-Weg mit Pult-Knopf, mehrfach und ohne Eingriff

**Das ist der Weg, den ein Rollout-Rechner geht**, und damit der
einzige, der hier zählt: Stick einstecken, am Pult unter *Einrichtung*
auf **„Jetzt einspielen"** drücken, fertig. Kein Terminal, kein
Internet, keine Tastatur.

**Stand:** Im Programm seit 0.2.13, im Prüfstand mit über 100
Zusicherungen belegt — darunter der echte alte Kern aus
`git show v0.2.11:stick_update.sh`, der sich beim Update selbst
überschreibt, und seit 0.4.0 der Weg auf die jeweils neue Fassung von
sieben Startfassungen aus, `v0.3.7` bis `v0.4.5`
(`pruefstand/einspielweg_test.sh`), jede mit ihrem eigenen alten
`aktualisieren.sh`. Alles
mit Attrappen für `systemctl`, `sudo`, `runuser`, `curl` und
`udevadm`.

Auf echter Hardware hat **kein einziges Stick-Update** stattgefunden.
Der Gemeinderechner ist bisher immer online aktualisiert worden.

**Was fehlt:**

- **Drei Fassungen hintereinander per Stick**, ohne dass jemand
  eingreift. Eingesteckt von jemandem, der nicht daneben steht und
  mitliest.
- **Der Rückweg auf echter Hardware.** Ein Update, das absichtlich
  scheitert, muss den alten Stand zurückholen. Bisher nur mit
  Attrappen.
- **Der Knopf am Pult**, einmal im Saal gedrückt. Er setzt nur eine
  Marke (`update/jetzt`); eingespielt wird von
  `devarenu-update.timer`, der als root läuft — der Dienst bekommt
  dafür kein Recht.

**Wie man es prüft:** `AUFSTELLEN.md`, Abschnitt „Von 0.2.11 direkt
auf 0.3.0". Danach jeweils: läuft der Dienst, meldet das Pult die
neue Fassung, liegt die Sicherung unter `/var/lib/devarenu/updates/`,
sind die Units neu geschrieben, ist `zustand.json` unangetastet. Und
der Gegentest mit einem Update, das scheitern muss.

> **Daran hängt alles andere.** Ohne einen erprobten Weg, Fehler zu
> beheben, darf keine zweite Gemeinde ein Gerät bekommen. Wer dort
> etwas kaputtmacht, kann es nicht reparieren — und niemand kann sich
> daraufsetzen, weil kein Internet da ist.

### Der Online-Weg gehört nicht hierher

`aktualisieren.sh`, das Wartungsfenster, das Autoupdate und der Knopf
„Jetzt aus dem Netz aktualisieren" sind **Werkzeuge der Erprobung in
Rostock**. Sie haben dort mehrfach getragen (0.3.4 → 0.3.7,
0.3.7 → 0.3.8, jeweils von Hand) und dreimal nicht — 0.3.1, 0.3.3,
0.3.7, jedes Mal an einer Stelle, die im neuen Stand längst behoben
war.

Für 1.0 ist das **kein Kriterium**: ein Rollout-Rechner hat kein
Internet und benutzt davon nichts. Was dort offen bleibt, bleibt
offen — es hält keine zweite Gemeinde auf.

## B2. Die virtuelle Testumgebung

**Stand:** Seit 0.4.0 **geschrieben, aber nicht aufgebaut.**
[VM-TESTUMGEBUNG.md](VM-TESTUMGEBUNG.md) beschreibt sie,
`vm_pruefstand.sh` legt sie an und testet ein Update darin,
`testmodus.py` lässt Devarenu ohne Grafikkarte laufen (Whisper als
`tiny` auf der CPU — und das kann auf einem Rechner mit NVIDIA-Karte
nicht greifen, das ist geprüft).

**Was fehlt:** Die VM selbst. `libvirt` ist auf dem
Entwicklungsrechner nicht installiert, und in dem Lauf, der das
Skript schrieb, durfte nichts installiert werden. Es gibt also eine
Anleitung und kein Gerät.

**Wie man es prüft:**

```fish
bash vm_pruefstand.sh --vorbedingungen
```
```fish
bash vm_pruefstand.sh --anlegen --iso ~/Downloads/cachyos-....iso
```
```fish
bash vm_pruefstand.sh --update v0.4.1
```

Erledigt ist der Punkt, wenn **ein Update dort gelaufen ist, bevor es
auf den Gemeinderechner kam** — und zwar nicht einmal, sondern als
Gewohnheit.

> **Dieser Punkt steht vor B1.** Die drei gescheiterten Updates von
> 0.3.x wären hier aufgefallen, und keines davon brauchte eine
> Grafikkarte, ein Mikrofon oder einen Saal.

---

## B3. Der Signierschlüssel: gesichert, und ein zweiter

**Stand:** Seit 0.4.0 **geprüft und dokumentiert, aber nicht getan.**
Dass `schluessel.erlaubt` mehrere Schlüssel führen kann, stand seit
0.3.1 darin — nachgewiesen ist es erst jetzt
(`pruefstand/online_test.sh`, Abschnitt *Zwei erlaubte Schlüssel*).
Dabei fiel ein Fehler in der eigenen Dokumentation auf: die Adresse
vor dem Schlüssel ist ein **Etikett, keine Bedingung**. Wer einen
Schlüssel sperren will, löscht die **Zeile**.

Es gibt **einen** Schlüssel, auf **einem** Rechner, **ohne** Sicherung.

**Was fehlt:**

- Eine verschlüsselte Kopie des vorhandenen privaten Schlüssels auf
  zwei getrennten Medien.
- Ein zweiter erlaubter Schlüssel, nach dem Ablauf in `AUFSTELLEN.md`
  (*Der Signierschlüssel*): ergänzen, mit dem **alten** signiert
  ausliefern, warten, bis jeder Rechner die Fassung hat, erst dann
  umschalten. Andersherum sperrt man sich aus.

**Wie man es prüft:** Der private Schlüssel wird auf dem
Entwicklungsrechner gelöscht und aus der Sicherung
zurückgeholt — danach verifiziert ein Gemeinderechner ein damit
signiertes Tag. Solange das nicht einmal durchgespielt wurde, ist die
Sicherung eine Behauptung.

> **Geht der Schlüssel verloren, kann niemand mehr ein Update
> signieren.** Dann bleibt nur, auf jedem Gerät vor Ort von Hand eine
> neue `schluessel.erlaubt` einzutragen.

---

## B4. Die Lizenz der englischen Stimme — entschieden mit 0.5.0

> **Entschieden: `en_US-lessac-medium` bleibt.** Das Risiko aus der
> Lizenz des Datensatzes („nur Forschung“) wird **bewusst getragen**.
> Damit ist B4 kein Blocker mehr; die Begründung, die der Prüfweg
> unten verlangt, ist diese Entscheidung. Was folgt, ist die
> Vorgeschichte und bleibt stehen, damit niemand die Frage ein zweites
> Mal von vorn aufrollt.

**Stand bis 0.4.6:** `en_US-lessac-medium` ist auf den Blizzard-2013-Daten von
Lessac Technologies / Voice Factory trainiert. Deren Lizenz gewährt
die Nutzung **„exclusively for Research Purposes only"**, nicht
übertragbar, ohne Recht zur Unterlizenzierung
([Lizenztext][bl13]). Ein Gottesdienst ist keine Forschung.

Das betrifft den Datensatz; `rhasspy/piper-voices` gibt die daraus
trainierten Gewichte trotzdem weiter, und ob die Beschränkung
mitwandert, ist offen. Für **ein** Gerät in Erprobung ist das
hinnehmbar. Für Geräte, die an fremde Gemeinden gehen, nicht — dann
verteilt das Projekt die Stimme weiter.

Englisch ist keine Nebensache: es ist nach Deutsch die Sprache, die
eine aufnehmende Gemeinde am ehesten einschaltet.

**Was fehlt:** Eine Entscheidung. Gemessene Kandidaten (siehe
[LIZENZEN.md](LIZENZEN.md)):

| Stimme | Lizenz des Datensatzes | trainiert | Tempo |
|---|---|---|---|
| `en_US-joe-medium` | **CC0** | **feinabgestimmt aus `lessac`** | 1,15 |
| `en_US-ljspeech-medium` | public domain | **von Grund auf** | 1,28 |
| `en_US-lessac-medium` *(heute)* | nur Forschung | — | 1,07 |

dazu `john`, `kristin`, `norman`, `bryce` (public domain),
`libritts_r` (CC BY 4.0), `sam` (Apache-2.0).

**Richtiggestellt mit 0.4.6:** Bis hierher stand hier, lizenzfreier
Ersatz liege bereit. Das stimmt so nicht. `joe` ist aus genau der
`lessac`-Stimme feinabgestimmt, deren Datensatz „nur Forschung" sagt —
ob diese Beschränkung auf weitertrainierte Gewichte durchschlägt, ist
dieselbe offene Frage, nur eine Stufe später. **Von den gemessenen
Kandidaten ist allein `ljspeech` von Grund auf trainiert**, und damit
der einzige, bei dem sich die Frage nicht stellt. Dasselbe betrifft
**Russisch** (S5): beide lizenzfreien Kandidaten dort sind ebenfalls
aus `lessac` feinabgestimmt. Festgestellt in `LIZENZEN.md` seit 0.4.3;
der Fahrplan war nicht nachgezogen. Eine Entscheidung ist das nicht.

**Entschieden wird nach einer Hörprobe, nicht nach der Tabelle.** Das
Projekt wählt Stimmen so: `werkzeuge/sprachpaket.py --bauen en` baut
ein Paket mit drei Kandidaten, ein englischsprachiger Hörer wählt.
Genau so sind Spanisch und Portugiesisch gewählt worden.

**In 0.4.0 wird keine Stimme getauscht.** Ein Stimmwechsel ändert,
was die Zuhörer hören, und gehört nicht in eine Lizenzaufräumung.

**Wie man es prüft:** In `LIZENZEN.md` steht zur ausgelieferten
englischen Stimme eine Lizenz, die eine Weitergabe trägt — oder eine
aufgeschriebene Begründung, warum die Beschränkung des Datensatzes
die Gewichte nicht erfasst.

[bl13]: https://www.cstr.ed.ac.uk/projects/blizzard/2013/lessac_blizzard2013/license.html

## B5. Die Erstinstallation, von Fremden durchgespielt

**Stand:** Seit 0.4.0 gibt es
[ERSTINSTALLATION.md](ERSTINSTALLATION.md) — zehn Abschnitte von der
Kiste bis zur Abnahme, nach jedem eine **Kontrolle** mit Befehl und
erwarteter Ausgabe, dazu eine Tabelle *was die Gemeinde vorher sagen
muss* und eine Störungstabelle am Ende.

**Was fehlt:** Der Durchlauf. **Niemand hat sie abgearbeitet, der das
Projekt nicht kennt.** Bis dahin ist sie eine Behauptung.

Dazu gehört die **Sicherung** (Abschnitt 9). `sichern.sh` und
`zuruecksichern.sh` sind seit 0.4.0 da und im Prüfstand belegt — aber
es liegt **keine Sicherung des Gemeinderechners** vor.

**Wie man es prüft:** Jemand, der nicht am Projekt beteiligt ist,
arbeitet sie ab — ohne Rückfragen. **Jede Rückfrage ist eine Lücke im
Dokument und gehört hineingeschrieben, nicht beantwortet.** Am Ende
muss ein Handy im Saal Ton bekommen.

Der günstige Weg dorthin ist B2: die Anleitung lässt sich in einer VM
abarbeiten, ohne einen Rechner zu plätten.

---

## B6. Die übrigen Lizenzen der Bausteine — entschieden mit 0.5.0

> **Entschieden:** `ru_RU-irina-medium` (keine Lizenz genannt) bleibt,
> das Risiko wird **bewusst getragen** — wie bei Englisch (B4).
> **Serbisch, Türkisch und Suaheli bleiben** unverändert. Damit hat
> jede ausgelieferte Stimme in `LIZENZEN.md` eine Lizenz oder eine
> getroffene Entscheidung, und B6 ist kein Blocker mehr.
>
> **Neu mit 0.5.0**, alle drei mit Lizenz:
>
> | Sprache | Stimme | Lizenz |
> |---|---|---|
> | Ukrainisch | `uk_UA-mykyta-high` | Apache 2.0 (Datensatz); Trainingsweg laut Modellkarte nicht angegeben |
> | Twi (Asante) | `tw_GH-openbible_asante-vits` | CC BY-SA 4.0 — Umwandlung eines Coqui-Modells, ebenfalls CC BY-SA 4.0 |
> | Arabisch | `ar_miro_espeak_V2` | CC BY-NC-ND 4.0 — nichtkommerziell, unverändert ausgeliefert |
>
> Was bleibt, steht unten unter *Von Hand in Rostock*.

**Stand bis 0.4.6:** Seit 0.4.0 erhoben. `werkzeuge/stimmlizenzen.py` liest die
Modellkarte jeder ausgelieferten Piper-Stimme — seit 0.4.5 sind es
19, vorher 21; die Tabelle
steht in [LIZENZEN.md](LIZENZEN.md), dazu Whisper, Gemma, Ollama und
`piper-tts`.

| Baustein | Lage |
|---|---|
| **Gemma** (`gemma4:12b`) | keine freie Lizenz, sondern Nutzungsbedingungen mit *Prohibited Use Policy*. Devarenu liefert das Modell **nicht mit** — `einrichten.sh` holt es über Ollama, jede Gemeinde nimmt die Bedingungen selbst entgegen. |
| `sr_RS-serbski_institut`, `tr_TR-dfki` | CC BY-NC-SA — **nicht eingeschaltet** |
| `it_IT-paola`, `sw_CD-lanfrica` | mit 0.4.3 nachgelesen: CC0 1.0 bzw. „non-profit, educational" — **nicht eingeschaltet** |
| ~~`ar_JO-kareem`~~, ~~`ka_GE-natia`~~ | keine Lizenz bzw. Organisationen untersagt — mit **0.4.5 ganz herausgenommen**, siehe LIZENZEN.md |
| Whisper `large-v3-turbo`, `faster-whisper`, `CTranslate2`, Ollama | MIT |
| `piper-tts` | GPL-3.0-or-later — der Grund, warum Devarenu selbst GPLv3 ist |

**Was fehlt:** Eine Entscheidung, was mit den noch markierten, nicht
eingeschalteten Stimmen geschieht. Drei Wege: nachsehen und
begründen, austauschen, oder **nicht mitliefern** und erst auf
Anforderung holen — `einrichten.sh` lädt sie ohnehin einzeln.

Für zwei ist sie mit 0.4.5 gefallen, und zwar auf den dritten Weg:
`ka_GE-natia` (Organisationen ausdrücklich untersagt) und
`ar_JO-kareem` (gar keine Lizenz) werden nicht mehr mitgeliefert.
„Nicht eingeschaltet" genügte nicht — sie lagen trotzdem auf jedem
Stick, und ein Stick wird weitergereicht. Bleiben Italienisch (CC0,
geklärt), Suaheli, Serbisch und Türkisch.

**Von Hand in Rostock:** Auf dem Rostocker Rechner liegen die beiden
herausgenommenen Stimmdateien noch — kein Update löscht Stimmen. Sie
werden **von Hand gelöscht, sobald 0.4.6 dort läuft**: je `.onnx` und
`.onnx.json` von `ar_JO-kareem-medium` und `ka_GE-natia-medium` unter
`voices/`, zusammen rund 126 MB. Erst nach 0.4.6, weil ein Rückfall
auf eine ältere Fassung sie sonst vermisste.

**Versuch: eine arabische Stimme mit Lizenz — mit 0.5.0 erledigt.**
OpenVoiceOS *Miro V2* ist eingebaut. Piper lädt die Datei
**unverändert**; gebraucht wird nur eine Beschreibung im Piper-Format.
Text ohne Vokalzeichen setzt Pipers eingebaute Diakritisierung um —
mit Whisper als Hörer an zwölf Sätzen im Mittel 0,98 Übereinstimmung
(die alte `kareem` 0,975). Ob sie **gut** klingt, sagt weiterhin nur
jemand, der Arabisch spricht; Arabisch bleibt ungeprüft.

Dazu ein Satz zu Gemma in der Übergabe an eine Gemeinde: sie nimmt
die Bedingungen entgegen, nicht das Projekt.

**Wie man es prüft:** In `LIZENZEN.md` steht zu jeder **ausgelieferten**
Stimme eine Lizenz **und** ein Satz, warum die Weitergabe in Ordnung
ist. Kein „unklar" mehr bei etwas, das mit dem Gerät das Haus
verlässt.

---

## B7. Datenschutz, von der Freikirche abgenickt

**Stand:** Technisch deutlich besser als in 0.2.

| | |
|---|---|
| Mitschrift im Protokoll | aus, Schalter am Pult, Systemcheck meldet ihn |
| Aufnahme | zwei bestätigte Häkchen, sichtbar, Frist sieben Tage, nur am Rechner abrufbar, seit 0.4.0 von Hand löschbar |
| DHCP-Mietliste | im Arbeitsspeicher, nicht im Journal, seit 0.3.8 mit Rechten `0640` |
| Fehlerbericht | Erlaubnisliste plus Riegel, mit erfundenen Daten geprüft |
| Pult | freiwilliges Passwort, Vorgabe offen |

**Seit 0.5.0 liegt alles als Entwurf vor**, sichtbar so gekennzeichnet
(„Entwurf, vor Freigabe durch den Datenschutzbeauftragten“):

- [DATENSCHUTZ.md](DATENSCHUTZ.md): ein **neutrales Verzeichnis** der
  Verarbeitungstätigkeiten (zwölf Punkte), dazu je ein Abschnitt zum
  **Rechtsrahmen** — Adventgemeinden nach der DSVO 2018 (§ 53 als
  Rechtsgrundlage, § 31 Verzeichnis, § 28 Voreinstellungen), andere
  Träger nach DSGVO (Art. 6 Abs. 1 lit. f, noch zu bestätigen). Die
  Frage „welches Recht gilt“ ist damit durch die Aufteilung beantwortet.
- Die **Information der Teilnehmenden** in zwei Stufen: kurz auf jedem
  Handy unter *Mehr* → *Datenschutz* und auf dem **Aushang** am
  Eingang, ausführlich unter `/datenschutz` vom Gerät selbst.
- Ein **Blatt für Gastprediger**.

**Was fehlt — und nichts davon ist technisch:**

- **Das Gespräch mit dem Datenschutzbeauftragten** und seine Freigabe.
- Das Verzeichnis ist geschrieben, aber **von keiner Gemeindeleitung
  abgenommen**.
- Das **Testprotokoll** ist auf den Handys nicht sichtbar, die
  Aufnahme schon — zu entscheiden, ob es das sein muss (siehe „Was
  offen ist“ in DATENSCHUTZ.md).
- Das Pult ist per Vorgabe **offen im Saalnetz**. Für eine fremde
  Gemeinde ist das eine bewusste Entscheidung, die jemand treffen
  muss — nicht eine, die sie erbt.
- Die **Aufbewahrung der Aufnahmen** ist eingestellt, nicht
  vereinbart. Sieben Tage sind eine Vorgabe, kein Beschluss.

**Wie man es prüft:** Das Verzeichnis ist von der Gemeindeleitung
abgenommen, und kein Punkt daraus lässt sich im laufenden System
widerlegen:

```fish
sudo ls -l /run/devarenu/
```
```fish
journalctl -u dnsmasq --since today | grep -ci dhcp
```

Die Mietliste liegt unter `/run` mit `0640`, und das `grep` findet
nichts.

> **Früh anstoßen.** Dieser Punkt kostet Wochen, in denen niemand
> etwas programmiert.

---

## B8. Ein Monat Testphase vor 1.0 — neu mit 0.5.0

**Stand:** Noch nicht begonnen.

**Was fehlt:** Bevor eine Fassung 1.0 heißt, läuft **genau diese
Fassung** einen Monat lang im Gemeindebetrieb, ohne dass dazwischen
etwas eingespielt wird außer Fehlerbehebungen. Ein Monat heißt
mindestens vier Gottesdienste.

**Wie man es prüft:** Am Ende des Monats liegen vor: die Zahl der
Gottesdienste, die Fehlerberichte des Monats (`ergebnisse/berichte/`),
die Rückmeldungen „verständlich / schwer verständlich“ je Sprache und
ein Satz der Technik vor Ort. Jede Fehlerbehebung in dieser Zeit
startet den Monat **nicht** neu, steht aber in der Liste — eine, die
etwas am Ablauf ändert, schon.

---

# Sollte

Gehört getan, hält aber kein Gerät auf.

## S1. Freigegebene Sprachen

**Stand:** **Sieben** von zweiundzwanzig sind von Muttersprachlern
gegengelesen: Deutsch, Englisch, Russisch, Persisch, seit 0.4.0
Spanisch und Portugiesisch, und seit 0.5.0 **Ukrainisch** — fest
aufgenommen, mit der Stimme `mykyta` und der Bibelzählung von Ohienko.
Polnisch liegt vorbereitet. Alles andere läuft maschinell und ist am
Pult als *experimentell* gekennzeichnet; der Hinweis auf dem Handy steht
seit 0.5.0 in der Sprache selbst und bittet um Mithilfe.

**Twi (Asante) und Arabisch** laufen seit 0.5.0 **ungeprüft mit
Stimme**. Bei Twi ist das mehr als ein Etikett: gemma4:12b schreibt
Twi gemessen schlecht (Wiederholungsschleifen, falsche Begriffe), und
Twi hat kein Fachwortverzeichnis. Einschalten erst nach einer Hörprobe
mit jemandem, der Twi spricht.

**Bei Ukrainisch zu bestätigen:** 30 maschinelle Glossarbegriffe sind
aus Ohienko berichtigt, nicht vom Prüfer gesehen
(`werkzeuge/glossar_rueck_uk.py`), und `mykyta` braucht mit
Längenfaktor 1,51 fast das zulässige Höchsttempo. Beides gehört vor
den nächsten Rücklauf.

Seit 0.4.0 ist das Glossar auch **aktiv** (`glossar_v0.9.csv`) — bis
0.3.8 zeigte `config.GLOSSAR_CSV` über vier Arbeitsstände hinweg auf
`v0.4`, und eine geprüfte Sprache lief ohne Fachwortverzeichnis. Das
war der schlechteste Zustand, weil er nach dem besten aussah.

**Was fehlt:** Kein fester Zielwert — eine Gemeinde braucht die
Sprachen, die sie braucht. Für 1.0 gilt: **jede Sprache, die eine
aufnehmende Gemeinde einschaltet, muss geprüft sein**, oder der
Hinweis am Pult bleibt stehen.

Offen sind außerdem neun Glossarzeilen aus dem spanischen und
portugiesischen Rücklauf, die geprüfte Werte für en, ru und fa
brauchen — siehe den Bericht zu 0.4.0.

**Wie man es prüft:** `werkzeuge/sprachpaket.py --bauen <sp>`, Paket
an einen Muttersprachler, einlesen,
`werkzeuge/glossar_vergleich.py` über die schon aktiven Sprachen.
Erwartet wird: keine Änderung.

---

## S2. Qualität im Betrieb

**Stand:** Es gibt keine Messung aus einem echten Gottesdienst. Das
**Testprotokoll** (seit 0.3.3, am Pult nur am Gemeinde-PC) schreibt je
Abschnitt den erkannten Satz, jede Übersetzung und die Dauer jedes
Schrittes — das Werkzeug ist da, benutzt wurde es nicht.

**Was fehlt:** Ein Protokoll über eine **ganze Predigt**, und zwar
für **Russisch** — die Sprache, die in Rostock tatsächlich gehört
wird. Jemand, der sie spricht, liest es durch und sagt, wo es kippt.

Dazu für Spanisch und Portugiesisch: nach dem ersten Gottesdienst mit
solchen Zuhörern deren Rückmeldung einholen. Das Sprechtempo für
`pt_BR-jeff-medium` steht auf 1,15 und ist im Betrieb **nicht
bestätigt**.

**Wie man es prüft:** Ein Testprotokoll, von einem Muttersprachler
durchgesehen, mit einer Zahl darunter: wie viele Abschnitte waren
brauchbar. Ohne diese Zahl ist „die Qualität ist gut" eine Vermutung.

---

## S3. Der Kaltstart

**Stand:** Teilweise. `rechner_einrichten.sh` setzt automatische
Anmeldung, kein Standby, keine Bildschirmsperre; der Systemcheck
meldet, wenn eines fehlt. Ob der Rechner nach einem Stromausfall ohne
Tastatur und Bildschirm allein hochkommt und übersetzt, ist **nicht
geprüft**.

### Was dabei der Reihe nach passieren soll

Jede Zeile ist eine Stelle, an der es hängen bleiben kann:

1. BIOS startet. **ErP aus**, sonst versorgt es die Uhr im Standby
   nicht — dann weckt der Wartungswecker nicht.
2. Der Anmeldemanager meldet den Dienstbenutzer ohne Passwort an.
   Ohne angemeldete Sitzung gibt es keinen PulseAudio-Server und
   damit **keinen Ton**. Daran hing der Rollout monatelang.
3. `devarenu.service` startet, lädt Whisper und die Stimmen. Das
   dauert; der Dienst antwortet erst danach.
4. `dnsmasq` gibt Adressen aus. Mit `bind-dynamic` wartet es auf die
   Netzwerkkarte, statt abzubrechen.
5. `devarenu-update.timer` sieht nach einem Stick-Update.
6. `devarenu-onlineupdate.timer` sieht nach einem Druck am Pult.
7. `devarenu-fenster.timer` und der Wecker, falls ein Fenster
   eingeschaltet ist.

**Was geprüft wird — ohne Tastatur, ohne Bildschirm:**

```fish
systemctl is-active devarenu dnsmasq
```
```fish
loginctl list-sessions --no-legend
```
```fish
curl -s -m 5 localhost:8000/api/zustand | head -c 60
```
```fish
bash gesundheit.sh
```

Und die eigentliche Probe: ein Handy verbindet sich und hört. Alles
andere sagt nur, dass Dienste laufen — nicht, dass Ton ankommt.

**Was fehlt:** Der Versuch. Stecker ziehen, Stecker rein, nichts
anfassen. Dazu der Fall, um den es geht: Stromausfall **mitten im
Gottesdienst**, mit Handys, die noch verbunden sind.

**Wie man es prüft:** Dreimal hintereinander. Jedes Mal muss die
Zuhörerseite binnen zwei Minuten antworten und der Ton laufen. Ein
Durchlauf zusätzlich **ohne angeschlossenen Monitor** — manche
Grafiktreiber verhalten sich ohne erkanntes Display anders, und das
fällt sonst erst in der Gemeinde auf.

---

## S4. Das Netz je Gemeinde

**Stand:** Ein Aufbau, einmal eingerichtet: der Rechner ist Router im
Saalnetz (`10.0.0.1`), `dnsmasq` verteilt Adressen, keine
Weiterleitung ins Hausnetz, Captive-Portal-Prüfadressen werden
beantwortet (`netzpruefung.py`).

**Was fehlt:**

- **Der iPhone-Fall.** Neuere iPhones prüfen beim ersten Verbinden auf
  ein Internet, das dieses WLAN nicht hat, und brauchen dafür lange.
  Die QR-Seite sagt „bis zu einer Minute warten, nicht neu
  verbinden" — das ist eine Umschreibung des Problems, keine Lösung.
  Ob die beantworteten Prüfadressen reichen, ist **nicht gemessen**.
- **„Bildschirm anlassen" auf dem iPhone.** Seit 0.4.6 hält die
  Hörerseite den Bildschirm selbst an — Wake Lock, sonst ein Video mit
  stiller Tonspur. Belegt ist das im Quelltext von Firefox und
  Chromium und am Galaxy Z Fold 7: mit 0.4.5-F und mit 0.4.6, in
  Chrome, Samsung Internet und Firefox, jeweils mit laufender
  Übersetzung und 30 Sekunden Bildschirm-Timeout — der Bildschirm blieb
  an, der Ton lief weiter. **Auf einem iPhone ist es ungetestet.** Wer dort Probleme hat, schaltet es unter *Mehr* aus.
  Zu prüfen in demselben Durchgang wie oben: bleibt der Bildschirm
  fünf Minuten ohne Berührung an, läuft der Ton, wird er leiser?
- **Ein zweiter Aufbau.** Jede Gemeinde hat ein anderes Hausnetz,
  einen anderen Zugangspunkt, andere Kabel. Dass es zweimal
  funktioniert, ist nicht gezeigt.

**Wie man es prüft:** Drei iPhones verschiedener Baujahre, je fünf
Verbindungen, Zeit bis zur ersten hörbaren Übersetzung, dasselbe mit
abgeschalteten mobilen Daten. Ergebnis in eine Tabelle; darunter die
Entscheidung: gelöst, oder erklärt und dokumentiert.

---

## S5. Die russische Stimme — entschieden mit 0.5.0

> **Entschieden: `ru_RU-irina-medium` bleibt**, das Lizenzrisiko wird
> bewusst getragen — wie bei Englisch (B4). Eine Hörprobe mit den
> Kandidaten unten kann trotzdem jederzeit stattfinden; sie wäre dann
> eine Frage des Klangs und des Tempos, nicht mehr der Lizenz.

**Stand bis 0.4.6:** `ru_RU-irina-medium` nennt **gar keine Lizenz** — die
Modellkarte sagt „Unknown", und das RHVoice-Repository `irina-rus`
führt keine Lizenzdatei. Ohne Lizenz gibt es keine ausdrückliche
Erlaubnis.

**Warum trotzdem nur *Sollte*:** Russisch ist die Sprache, für die
Rostock Devarenu gebaut hat. Eine aufnehmende Gemeinde schaltet sie
nur ein, wenn sie russische Zuhörer hat — und dann ist es ihre
Entscheidung, nicht eine, die sie erbt. Englisch (**B4**) steht
anders da: das schaltet fast jeder ein.

**Gemessene Kandidaten:**

| Stimme | Lizenz des Datensatzes | trainiert | Tempo |
|---|---|---|---|
| `ru_RU-dmitri-medium` | **CC0** | **feinabgestimmt aus `lessac`** | **0,92** |
| `ru_RU-denis-medium` | **CC0** | **feinabgestimmt aus `lessac`** | 1,14 |
| `ru_RU-irina-medium` *(heute)* | „Unknown" | — | 1,22 |

**Richtiggestellt mit 0.4.6:** Bis hierher stand hier, der Ersatz sei
lizenzfrei und „ein Gewinn in beide Richtungen". Lizenzfrei ist der
**Datensatz** — aber beide Stimmen sind aus der englischen
`lessac`-Stimme feinabgestimmt, deren Datensatz „nur Forschung" sagt.
Ob das auf die Gewichte durchschlägt, ist dieselbe offene Frage wie
bei Englisch (**B4**). **Damit ist auch Russisch davon betroffen**, und
anders als bei Englisch gibt es in dieser Auswahl keine von Grund auf
trainierte russische Stimme. Schneller als `irina` ist `dmitri`
weiterhin, um knapp dreißig Prozent.

**Was fehlt:** Eine Hörprobe — das Paket liegt seit 0.4.3 unter
`pruefung/` bereit. **Das entscheiden die russischen Zuhörer in
Rostock**, nicht eine Tabelle und nicht der Entwickler. Dazu, getrennt
davon, eine Entscheidung zur Lizenzfrage oben.

**Wie man es prüft:** `werkzeuge/sprachpaket.py --bauen ru` baut ein
Paket mit drei Kandidaten; wer Russisch spricht, hört sie an und
wählt. Danach `config.STIMMEN["ru"]` und `TEMPO_STIMME` setzen.

---

## S6. Der Bus-Faktor

**Stand:** **Eins.** Eine Person kennt das Projekt, hält den
Signierschlüssel, pflegt das Glossar, baut die Anleitung und betreut
den einen Gemeinderechner.

Dagegen steht einiges: alles ist aufgeschrieben und begründet
(`AUFSTELLEN.md`, 2000 Zeilen mit der Geschichte jeder Entscheidung),
39 Prüfstände halten die Zusicherungen fest (Stand 0.4.6: 35 in
Python und JavaScript, vier als Shell-Skript), das Repo ist öffentlich
und unter GPLv3, und seit 0.4.0 gibt es eine Erstinstallation für
Fremde.

**Was fehlt:**

- **Eine zweite Person**, die ein Update signieren und einspielen
  kann — das ist dasselbe wie B3, von der anderen Seite.
- **Jemand, der das Glossar pflegen kann.** Die Entscheidungen zu
  Spanisch, Portugiesisch und Ukrainisch stehen mit Begründung im
  Quelltext (`werkzeuge/glossar_rueck_es_pt.py`,
  `werkzeuge/glossar_rueck_uk.py`); ob das reicht, hat niemand
  ausprobiert.
- Die **Betreuer-Stelle** ist eine Adresse, keine Vertretung.

**Wie man es prüft:** Eine zweite Person spielt eine Fassung ein, die
sie selbst signiert hat, auf einem Rechner, an dem sie vorher nicht
war. Erst dann ist der Faktor zwei.

---

## S7. Die Lizenz des Codes: AGPL vorbereitet — neu mit 0.5.0

**Stand:** Der Code steht unter **GPLv3**. Seit 0.5.0 gilt dazu eine
**zusätzliche Bedingung nach § 7**: veränderte Fassungen dürfen nicht
unter dem Namen Devarenu weitergegeben werden (`COPYING.ZUSATZ`). Bis
0.4.6 war das nur eine Bitte.

Der Wechsel auf die **AGPL-3.0** ist **vorbereitet, aber nicht
aktiviert**: Lizenztext, fertiger Patch, Verträglichkeitsprüfung aller
Abhängigkeiten und eine Anleitung liegen am Entwicklungsrechner, nicht
im Repo. Er wartet auf die **Antwort des Justitiars**.

**Was fehlt:** Die Antwort. Danach entweder der Wechsel mit einem
Befehl, oder die Unterlagen werden verworfen.

**Wie man es prüft:** Entweder steht in `COPYING` die AGPL und auf der
Hörerseite ein Weg zum Quelltext (§ 13 AGPL), oder in diesem Abschnitt
steht, warum es bei der GPL bleibt.

---

# Nicht mehr auf der Liste

**B4, B6 und S5 — die Lizenzen der Stimmen** — mit 0.5.0 entschieden:
`lessac` (Englisch) und `irina` (Russisch) bleiben, das Risiko ist
bewusst getragen; Serbisch, Türkisch und Suaheli bleiben unverändert;
Ukrainisch, Twi und Arabisch sind mit Lizenz dazugekommen. Die
Abschnitte stehen oben weiter, mit der Entscheidung obenan und der
Vorgeschichte darunter.

**Ukrainisch als geprüfte Sprache** — seit 0.5.0 (S1).

**Welches Datenschutzrecht gilt** — durch die Aufteilung in
DATENSCHUTZ.md beantwortet: Adventgemeinden nach DSVO, andere Träger
nach DSGVO. Offen bleibt die Freigabe (B7).

**RustDesk unter Wayland** — **kein Blocker mehr.** Das
Bildschirmteilen über `xdg-desktop-portal` fragt unter KDE bei jeder
neuen Sitzung nach und ist damit für einen unbeaufsichtigten Rechner
unbrauchbar; das ist ein Fehler von RustDesk und mit keiner
Einstellung dort zu beheben. Der Weg ist deshalb **RustDesk-Terminal
plus ein TCP-Tunnel auf Port 8000** — darüber ist das Pult erreichbar,
und RustDesk zählt für den Server als „am Rechner" (Loopback), also
geht auch der Update-Knopf. Steht ausführlich in `AUFSTELLEN.md`.

**Der Online-Update-Weg als Kriterium** — `aktualisieren.sh`, das
Wartungsfenster, das Autoupdate und der Knopf „Jetzt aus dem Netz"
sind Werkzeuge der Erprobung in Rostock. Ein Rollout-Rechner hat kein
Internet und benutzt davon nichts. Was dort offen bleibt, hält keine
zweite Gemeinde auf. Geprüft wird stattdessen der Stick-Weg (**B1**).

**Der Stick-Weg als eigener Punkt** — er war bis 0.4.0 „Sollte"
(S5, *Gemeinden ohne Internet-WLAN*) und ist jetzt **B1**, also der
Normalfall statt der Ausnahme.

**Die Erstinstallation als Liste** — sie existiert
([ERSTINSTALLATION.md](ERSTINSTALLATION.md)). Was fehlt, ist nur noch
der Durchlauf, und der steht als B5.

**Das Glossar aktiv schalten** — seit 0.4.0 getan, mit einem
Vergleichslauf über 1444 Texte, der belegt, dass en, ru und fa
Zeichen für Zeichen dasselbe bekommen.

---

## Was NICHT drinsteht

Keine Funktionswünsche. 1.0 heißt nicht „kann mehr", sondern
**„lässt sich jemand anderem in die Hand geben"**. Alles, was diese
Liste verlängert, ohne einen der sechs Blocker zu schließen, gehört
in eine spätere Fassung.

---

## Nach 1.0

Kein Teil von 1.0 und kein Blocker. Hier stehen Wege, die **erprobt und
verworfen** wurden, damit niemand sie ein zweites Mal geht — und was an
ihnen noch offen ist.

### Ton bei gesperrtem Handy: ein eigener Abspieler

**Stand:** Seit 0.4.6 hält die Hörerseite den Bildschirm selbst an
(siehe S4) — das hilft, solange niemand das Handy bewusst sperrt.
Gegen das bewusste Sperren hilft es nicht. Zwei Versuche,
das zu beheben, sind auf echten Geräten gescheitert — der Stille-Füller
(0.4.2) und der durchgehende MP3-Strom (0.4.4). Beides ist ausgebaut.
Die Messwerte stehen in `messungen/tonstrom_verzoegerung.json`, die
Begründung in `AENDERUNGEN.md` unter 0.4.4.

**Warum es scheiterte:** Mit einem gewöhnlichen `audio`-Element
steuert der Browser den Puffer, nicht wir. Gefordert sind höchstens
0,5 Sekunden Abstand zum Live-Punkt; auf einem Galaxy Z Fold 7 nahm
sich Chrome von selbst 2 bis 3 Sekunden, Firefox 3 bis 6.

**Was noch möglich wäre:** ein eigener Abspieler mit **Media Source
Extensions**. Dann liegt die Pufferführung bei uns: Häppchen werden in
einen `SourceBuffer` geschoben, und wie weit der Ton hinter dem
Live-Punkt läuft, ist eine Zahl in unserem Code statt eine Entscheidung
des Browsers. Serverseitig ist die Arbeit getan — der Koder war
gemessen und kostete nichts.

**Offen daran, beides nicht beantwortet:**

* Ob MSE mit gesperrtem Bildschirm überhaupt weiterspielt. Das ist
  genau die Frage, an der die beiden Versuche gescheitert sind, und sie
  ist nur auf echten Geräten zu beantworten — nicht am Schreibtisch.
* iOS kennt `ManagedMediaSource` erst ab 17.1. Älteres iPhone heißt
  kein MSE, also in jedem Fall zwei Wege nebeneinander: den neuen und
  die heutigen Häppchen.

Erst wenn der erste Punkt auf einem Android- **und** einem
iOS-Gerät gemessen ist, lohnt der zweite.

---

## Anhang: was an der Hardware gemessen ist

Gehört zu keinem Punkt und wird überall gebraucht.

**Stand:** Ein Rechner, CachyOS, RTX 5080. Es gibt **keine**
Empfehlung, was eine andere Gemeinde kaufen soll.

Aus `ergebnisse/messung/` — 26 Läufe, der längste 280 Segmente über
knapp fünf Minuten, vier bis fünf Sprachen gleichzeitig:

| | |
|---|---|
| Verzögerung Ton → Auslieferung | Median **1,1 bis 1,4 s** |
| davon Whisper | Median **0,09 s** |
| 95. Perzentil | **2,1 s** |
| schlechtester Wert | 2,3 s (in einem Lauf ein Ausreißer von 6,2 s) |
| Warteschlange | durchgehend **0** — nichts staute sich |
| Drift innerhalb eines Laufs | keiner: erstes Viertel 1,11 s, letztes 1,15 s |

Dazu der Speicherbedarf, nicht gemessen sondern abgelesen:
`gemma4:12b` belegt **7,6 GB** auf der Platte und entsprechend im
Grafikspeicher; `large-v3-turbo` in float16 kommt dazu. Unter **12 GB
VRAM** wird es eng, unter 8 GB passt beides nicht gleichzeitig.

**Was unbekannt ist:**

- **Auf welcher Karte diese Läufe entstanden sind**, steht in keiner
  `lauf.json`. Alle stammen von Entwicklungsrechnern, vermutlich
  derselben Klasse. Das ist eine Lücke in der Messung selbst.
- **Ob der Rückstand über eine dreiviertel Stunde wächst.** Die Läufe
  sind fünf Minuten lang und liefen im Dateibetrieb, also schneller
  als Echtzeit. Fünf Minuten ohne Drift sagen nichts über
  fünfundvierzig.
- **Wo die Untergrenze liegt.** Eine kleinere Karte wurde nie
  gemessen. Die 5060 Ti in Rostock läuft, aber es liegt keine Messung
  von ihr vor — nur die Beobachtung, dass es geht.
- **Ohne CUDA** läuft es gar nicht; das sagt der Selbsttest deutlich.

**Wie man es prüft:** Dieselbe Predigt auf zwei, drei Karten
verschiedener Klasse. Gemessen wird nicht die Geschwindigkeit, sondern
ob der Rückstand über eine dreiviertel Stunde **wächst**. Wächst er,
ist die Karte zu klein — auch wenn die ersten fünf Minuten gut
aussehen.
