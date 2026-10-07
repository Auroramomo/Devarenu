# Devarenu

**דְּבָרֵנוּ** — hebräisch für „unsere Worte".

Live-Übersetzung im Gottesdienst. Der Prediger spricht, jeder Zuhörer hört
auf seinem Handy in seiner Sprache mit. Alles läuft auf einem Rechner in
der Gemeinde: ohne Internet, ohne Konto, ohne laufende Kosten.

Gemessen im Betrieb: 2,0 Sekunden Verzögerung, kein Nachlaufen über 32
Minuten.

**Fassung 0.5.0.** Was dazugekommen ist, steht in
[AENDERUNGEN.md](AENDERUNGEN.md). Devarenu läuft zur Zeit in **einer**
Gemeinde und wird dort erprobt; an weitere Gemeinden geht es erst mit
Version 1.0.

## Einrichten

```
git clone https://github.com/Auroramomo/Devarenu.git
cd devarenu
bash INSTALLIEREN.sh
```

Beim ersten Mal werden rund zehn Gigabyte geladen. Danach läuft alles
offline. Der Befehl ist gefahrlos mehrfach startbar und ergänzt nur, was
fehlt.

Zum Schluss prüft ein Selbsttest die Kette: Piper spricht einen Satz,
Whisper schreibt ihn wieder auf. Kommt er durch, funktioniert es.
Jederzeit wiederholbar mit `.venv/bin/python selbsttest.py`.

**Für einen Gemeinderechner von Grund auf**, mit Saalnetz, Dienst,
Wartungsfenster und Sicherung, gibt es
[ERSTINSTALLATION.md](ERSTINSTALLATION.md) — zehn Abschnitte, nach
jedem eine Kontrolle. Geschrieben für jemanden, der das Projekt nicht
kennt.

**Voraussetzung:** Linux und eine NVIDIA-Grafikkarte. Ohne Grafikkarte
läuft alles auf der CPU und ist für den Livebetrieb zu langsam.

## Starten

```
bash start.sh                        Voreinstellung
bash start.sh --datei predigt.mp3    Dauerlauf mit einer Aufnahme
bash start.sh --mikro 1              Aufnahmegerät erzwingen, zur Fehlersuche
```

Im Fenster stehen drei Adressen: für die Zuhörer, für die QR-Codes am
Beamer, und für das Pult.

## Einmal einrichten

Das Pult hat vier Reiter: **Gottesdienst**, **Vorbereiten**,
**Aufnahmen**, **Einrichtung**. Was einmal je Gemeinde eingestellt
wird, steht unter Einrichtung; die Tonquelle unter Vorbereiten →
Feineinstellung.

**Tonquelle.** Gerät auswählen, hineinsprechen, Ausschlag am Balken
prüfen. Lässt sich ein Gerät nicht öffnen, kommt das vorherige zurück und
der Grund steht daneben. Der Server läuft dabei weiter.

Alles davon steht anschließend in `zustand.json` neben dem Programm und
gilt nach dem Neustart weiter, der Schwellenmodus und die eingemessene
Mindestlautstärke eingeschlossen. Was in `config.py` steht, gilt für alle Gemeinden gleich
und wird beim Aktualisieren überschrieben; `zustand.json` bleibt davon
unberührt. Sie enthält das WLAN-Passwort im Klartext und ist deshalb nur
für den eigenen Benutzer lesbar.

## Vor dem Gottesdienst

Zwei Handgriffe am Pult, zusammen unter fünf Minuten.

**Einmessen.** Den Prediger zwölf Sekunden sprechen lassen, das setzt die
Mindestlautstärke. Bei jedem neuen Sprecher wiederholen. Der Wert bleibt
bis dahin erhalten, auch über einen Neustart hinweg.

**Die Übersetzung gehört nicht auf Lautsprecher im selben Raum wie das
Predigermikro.** Sie läuft über Kopfhörer am Handy. Sonst hört das
Mikrofon die eigene Ausgabe, übersetzt sie erneut und schaukelt sich auf.
Im Testbetrieb ist genau das passiert.

**Thema und Bibelstellen eintragen.** Daraus zieht das Programm die
Eigennamen der genannten Kapitel. Daran hängt, ob Bethsaida richtig
geschrieben wird. Fehlt die Angabe, erinnert das Pult mit einer gelben
Zeile daran — aufgehalten wird nichts.

**Bibelstellen werden in die Zählung der Zielsprache gebracht.** Die
Schlachter 2000 zählt wie der hebräische Text; englische, spanische,
portugiesische und die Twi-Bibel zählen anders, russische bei den
Psalmen ebenfalls, die ukrainische (Ohienko) bei Joel und Maleachi.
Aus „Joel 3,1" wird darum englisch „Joel 2:28" und aus „Psalm 23"
russisch „Псалом 22". Umgerechnet wird nur, wo die Zuordnung eindeutig
belegt ist — bei Spannen über Kapitelgrenzen, bei Versen ohne
Gegenstück und für Persisch bleibt die Angabe unverändert stehen.

## Sprachen ändern

In `config.py`:

```python
AUSGANGSSPRACHE = "de"
ZIELSPRACHEN = ["en", "ru", "fa"]
```

Danach einmal `bash einrichten.sh`, das lädt die fehlenden Stimmen. Umschalten
geht auch am Pult; das bleibt dann so, bis es jemand wieder ändert.
Sprachen ohne Stimme laufen als reiner Untertitel.

Bei Deutsch, Englisch, Russisch, Persisch, Spanisch, Portugiesisch und
Ukrainisch hat ein Muttersprachler das Fachwortverzeichnis durchgesehen.
Die übrigen Sprachen laufen technisch genauso, ihre Terminologie ist
aber maschinell erzeugt und ungeprüft — Twi hat gar keine. Twi (Asante)
gibt es nur als Zielsprache: die Spracherkennung kennt es nicht. Und
es ist *Versuchssprache*: das Übersetzungsmodell schreibt es nicht gut
genug für den Gottesdienst, darum erscheint es erst, wenn unter
*Einrichtung → Fehlersuche → Erweitert* der Schalter
„Versuchssprachen“ an ist.

## Warum es so gebaut ist

**Das Glossar ist der Hebel.** Trefferquote bei Fachbegriffen 88 bis 98
Prozent mit, 47 bis 81 ohne. „Fürbitte" wurde ohne Vorgabe mit dem
orthodoxen Wort für Heiligenanrufung übersetzt.

**Der Whisper-Prompt besteht aus Eigennamen, nicht aus Lehrbegriffen.**
Der erste Versuch brachte nichts, weil Sabbatschule und
Untersuchungsgericht darin standen, die Predigt aber Bilha und Kapernaum
brauchte. Von 24 Begriffen im festen Prompt kamen fünf in der Predigt
überhaupt vor.

Er hilft auch bei Namen, die gar nicht in der Liste stehen. Whisper hat
einen Sprachmodellanteil im Dekoder: steht im Prompt ein Namensraum,
bewertet es unbekannte Lautfolgen anders und schreibt eher einen
Eigennamen als ein zerlegtes Alltagswort. Der Prompt fasst nur 224 Token,
deshalb wird er aus den eingetragenen Bibelstellen gebaut statt fest
vorgegeben.

**Das Predigtmanuskript wird ausgewertet, nicht ausgeliefert.** Prediger
weichen ab, kürzen, schweifen aus. Wer das Manuskript vorliest, merkt die
Abweichung nicht und überträgt am Ende etwas, das nie gesagt wurde.
Gezogen werden nur die Namen — und zwar die, die in keiner Bibelstelle
stehen: Ortsnamen aus einer Anekdote, ein zitierter Autor, ein
hebräischer Ausdruck.

**Es gibt keinen Rückfall.** Fällt eine Komponente aus, steht die
Übersetzung still. Eine erfundene Übersetzung wäre schlimmer als keine.

**Ton bei gesperrtem Handy: der Hinweis bleibt, zwei Versuche sind
gescheitert.** Die Hörerseite sagt „Bildschirm anlassen, sonst stoppt
die Wiedergabe". Das ist kein ungelöster Rest, sondern der Stand nach
zwei Versuchen auf echten Geräten.

Versucht wurde, das `audio`-Element nie leer werden zu lassen — erst
mit einer Sekunde Stille in Schleife (0.4.2), dann mit einem
durchgehenden MP3-Strom je Sprache vom Server (0.4.4). Die Stille half
nicht: jedes Ende eines Mediums räumt dem Browser die Tonsitzung ab,
und davon gab es im Sekundentakt eines. Der Strom lief serverseitig
einwandfrei und scheiterte am Puffer im Browser. Gefordert sind
höchstens 0,5 Sekunden Abstand zum Live-Punkt; gemessen auf einem
Galaxy Z Fold 7 nahm sich Chrome von selbst 2 bis 3 Sekunden und lief
bei 0,4 Sekunden regelmäßig leer, Firefox nahm sich 6 Sekunden Vorrat
und blieb bei 3 bis 6.

**Mit einem gewöhnlichen `audio`-Element steuert der Browser den
Puffer, nicht wir.** Eine Quelle angeben und das Tempo verstellen ist
alles, was geht; wie viel vorgehalten wird und wann von selbst
aufgepuffert wird, entscheidet der Browser. Deshalb ist beides
ausgebaut. Die Zahlen stehen in `messungen/tonstrom_verzoegerung.json`,
die Begründung in `AENDERUNGEN.md` unter 0.4.4, der offene Weg nach
1.0 in `FAHRPLAN-1.0.md`.

Was ein Zuhörer stattdessen hat: der Bildschirm muss anbleiben, darf
aber dunkel sein — ein Knopf unten dimmt die Seite in zwei Stufen.

## Dauerbetrieb

Auf dem Rechner in der Gemeinde meldet sich niemand an. Dafür gibt es
einen Systemdienst, der mit dem Rechner startet und sich nach einem
Absturz selbst wieder fängt:

```
bash dienst.sh              einrichten und starten
bash dienst.sh --status     nachsehen
bash dienst.sh --entfernen  wieder abschalten
```

`INSTALLIEREN.sh` fragt am Ende danach. Wer nur entwickelt, sagt nein und
startet weiter mit `bash start.sh`.

Die Tonquelle steht bewusst **nicht** im Dienst, sondern in
`zustand.json`, und wird am Pult gewählt. Neben der Gerätenummer steht
dort auch der Gerätename, und gesucht wird zuerst nach dem Namen.

**Gerätenummern nicht abtippen.** Sie verschieben sich nicht nur beim
Umstecken eines USB-Geräts — der Dienst und ein Terminal zählen von
vornherein verschieden. Der Dienst hält das benutzte Mikrofon exklusiv
offen, es fehlt einer zweiten Aufzählung deshalb ganz, und ohne
angemeldete Sitzung zeigt ALSA andere Plugin-Einträge. Am selben Rechner
zur selben Sekunde gemessen: 13 Geräte beim Dienst, 7 im Terminal, mit
verschiedener Nummer 0. Was `server.py --geraete` oder `bash einrichten.sh`
auflisten, gilt nur für einen Start aus demselben Terminal. Am Pult
auswählen schreibt den Namen mit, und der gilt überall.

Nachsehen, ob alles steht:

```
bash pruefen.sh
```

Das geht Grafikkarte, Ollama, Modelle, Dienst, Netz, Tonquelle und
Zustand durch und sagt bei jedem Fund, was zu tun ist. Es läuft auch,
wenn der Dienst gar nicht steht — dann zeigt es zusätzlich die letzten
Zeilen aus dem Journal. Gedacht für den Fall, dass jemand anderes vor dem
Rechner steht: `bash pruefen.sh > bericht.txt 2>&1` und verschicken.

Aktualisieren:

```
bash aktualisieren.sh
```

Das holt den neuen Stand, ergänzt fehlende Abhängigkeiten, startet den
Dienst neu und lässt den Selbsttest laufen. Lokale Änderungen werden
nicht überschrieben: gibt es welche, bricht es ab und zeigt sie.
`zustand.json` bleibt unangetastet.

## Datenschutz

Was das Programm über Zuhörer speichert — und was nicht — steht in
[DATENSCHUTZ.md](DATENSCHUTZ.md): ein Verzeichnis der
Verarbeitungstätigkeiten, der Rechtsrahmen für Adventgemeinden (DSVO)
und für andere Träger (DSGVO), und die Information der Teilnehmenden in
zwei Stufen — auf jedem Handy unter *Mehr* → *Datenschutz*, als Aushang
für den Eingang und als Blatt für Gastprediger. **Alles davon ist ein
Entwurf, vor Freigabe durch den Datenschutzbeauftragten.**

## Spenden und offizielle Fassung

**Es gibt genau ein Spendenkonto.** Es steht fest in `config.py` unter
`SPENDE` und lässt sich am Pult nicht ändern. Die Spenden gehen an die
Freikirche, nicht an eine Person: der Pastor wird über den Zehnten
getragen, das Programm selbst kostet nichts.

Welches Konto das richtige ist, steht auf der Seite des Betreuers.
*(Adresse folgt.)* Wer eine Fassung von Devarenu mit einem anderen
Spendenkonto findet, sollte dort nachsehen, bevor er überweist. Das
Programm rechnet beim Start die Prüfziffer der eingetragenen IBAN nach
und sagt es am Pult und auf der QR-Seite, wenn sie nicht stimmt.

**Offizielle Fassungen sind signiert.** Jedes veröffentlichte Tag
trägt eine SSH-Signatur mit dem Schlüssel

```
SHA256:EklvDQh9QDDh7a5z9PhdUKXTcH0N+4aNcycsFYQnu+Q
```

Derselbe Schlüssel steht in `schluessel.erlaubt`; der Updater spielt
nur Tags ein, die damit signiert sind — über USB-Stick wie über das
Netz. Prüfen lässt sich das jederzeit selbst:

```
git -c gpg.ssh.allowedSignersFile=schluessel.erlaubt verify-tag v0.3.7
```

**Wer etwas ändert, gibt es nicht unter dem Namen Devarenu weiter.**
Bis 0.4.6 war das eine Bitte; seit 0.5.0 ist es eine Bedingung der
Lizenz (unten, *Zusätzliche Bedingung*). Nicht aus Besitzanspruch —
den Code darf jeder ändern und weitergeben. Aber in den Gemeinden steht
der Name für etwas, das geprüft wurde und dessen Spendenkonto bekannt
ist. Eine veränderte Fassung unter demselben Namen macht beides
wertlos. Nimm einen eigenen Namen, und der Code gehört dir.

## Lizenz

Der Code steht unter **GPLv3 oder später**, siehe `COPYING`. Bis
einschließlich 0.3.6 war es MIT; gewechselt wurde, weil Piper als
GPL-Bibliothek im selben Prozess läuft. Was unter MIT veröffentlicht
wurde, bleibt unter MIT.

### Zusätzliche Bedingung nach § 7 GPLv3 (seit 0.5.0)

Für dieses Programm gilt neben der GPLv3 die folgende zusätzliche
Bedingung, die § 7 Abs. 2 Buchst. c und e der Lizenz zulassen. Sie
steht auch neben dem Lizenztext, in `COPYING.ZUSATZ`:

1. **Der Name „Devarenu“** (auch in hebräischer Schrift, „דְּבָרֵנוּ“)
   ist nicht Gegenstand der Lizenz. Für **veränderte Fassungen** werden
   keine Rechte an diesem Namen eingeräumt (§ 7 Buchst. e).
2. Wer eine **veränderte Fassung** weitergibt, gibt sie unter einem
   **anderen Namen** weiter und darf sie nicht als Devarenu ausgeben;
   sie muss als von der ursprünglichen verschieden erkennbar sein
   (§ 7 Buchst. c). Ein sachlicher Hinweis wie „beruht auf Devarenu“
   ist erlaubt; Urheber- und Lizenzvermerke bleiben ohnehin stehen.
3. **Unveränderte** Fassungen — die veröffentlichten, signierten Tags —
   dürfen unter dem Namen Devarenu weitergegeben werden.

Alle übrigen Rechte aus der GPLv3 bleiben unberührt: ändern, weitergeben,
verkaufen, unter eigenem Namen.

*Additional term under section 7 of the GNU GPL v3 (since 0.5.0):
(1) The name “Devarenu” (also in Hebrew script) is not licensed under
the GPL; no rights to it are granted for modified versions (section
7(e)). (2) Whoever conveys a modified version must convey it under a
different name and must not present it as Devarenu; it must be marked
as different from the original version (section 7(c)). Stating that it
is based on Devarenu is permitted. (3) Unmodified versions — the
published, signed tags — may be conveyed under the name Devarenu. All
other rights under the GPL v3 remain unaffected.*

Modelle, Stimmen und das Logo haben eigene Bedingungen, siehe
[LIZENZEN.md](LIZENZEN.md).

Das Programm kostet nichts. Wer etwas zurückgeben möchte, findet in der
Zuhörer-Oberfläche einen Spendenknopf.
