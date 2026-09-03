# Devarenu

**דְּבָרֵנוּ** — hebräisch für „unsere Worte".

Live-Übersetzung im Gottesdienst. Der Prediger spricht, jeder Zuhörer hört
auf seinem Handy in seiner Sprache mit. Alles läuft auf einem Rechner in
der Gemeinde: ohne Internet, ohne Konto, ohne laufende Kosten.

Gemessen im Betrieb: 2,0 Sekunden Verzögerung, kein Nachlaufen über 32
Minuten.

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

**Voraussetzung:** Linux und eine NVIDIA-Grafikkarte. Ohne Grafikkarte
läuft alles auf der CPU und ist für den Livebetrieb zu langsam.

## Starten

```
./start.sh                        Voreinstellung
./start.sh --datei predigt.mp3    Dauerlauf mit einer Aufnahme
./start.sh --mikro 1              Aufnahmegerät erzwingen, zur Fehlersuche
```

Im Fenster stehen drei Adressen: für die Zuhörer, für die QR-Codes am
Beamer, und für das Pult.

## Einmal einrichten

Am Pult öffnet das Zahnrad die Einrichtung: Tonquelle, Sprachen, WLAN.

**Tonquelle.** Gerät auswählen, hineinsprechen, Ausschlag am Balken
prüfen. Lässt sich ein Gerät nicht öffnen, kommt das vorherige zurück und
der Grund steht daneben. Der Server läuft dabei weiter.

Alles davon steht anschließend in `zustand.json` neben dem Programm und
gilt nach dem Neustart weiter, die eingemessene Mindestlautstärke
eingeschlossen. Was in `config.py` steht, gilt für alle Gemeinden gleich
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
geschrieben wird.

## Sprachen ändern

In `config.py`:

```python
AUSGANGSSPRACHE = "de"
ZIELSPRACHEN = ["en", "ru", "fa"]
```

Danach einmal `./einrichten.sh`, das lädt die fehlenden Stimmen. Umschalten
geht auch am Pult; das bleibt dann so, bis es jemand wieder ändert.
Sprachen ohne Stimme laufen als reiner Untertitel.

Bei Deutsch, Englisch, Russisch und Persisch hat ein Muttersprachler das
Fachwortverzeichnis durchgesehen. Die übrigen Sprachen laufen technisch
genauso, ihre Terminologie ist aber maschinell erzeugt und ungeprüft.

## Warum es so gebaut ist

**Das Glossar ist der Hebel.** Trefferquote bei Fachbegriffen 88 bis 98
Prozent mit, 47 bis 81 ohne. „Fürbitte" wurde ohne Vorgabe mit dem
orthodoxen Wort für Heiligenanrufung übersetzt.

**Der Whisper-Prompt besteht aus Eigennamen, nicht aus Lehrbegriffen.**
Der erste Versuch brachte nichts, weil Sabbatschule und
Untersuchungsgericht darin standen, die Predigt aber Bilha und Kapernaum
brauchte.

**Es gibt keinen Rückfall.** Fällt eine Komponente aus, steht die
Übersetzung still. Eine erfundene Übersetzung wäre schlimmer als keine.

## Dauerbetrieb

Auf dem Rechner in der Gemeinde meldet sich niemand an. Dafür gibt es
einen Systemdienst, der mit dem Rechner startet und sich nach einem
Absturz selbst wieder fängt:

```
./dienst.sh              einrichten und starten
./dienst.sh --status     nachsehen
./dienst.sh --entfernen  wieder abschalten
```

`INSTALLIEREN.sh` fragt am Ende danach. Wer nur entwickelt, sagt nein und
startet weiter mit `./start.sh`.

Die Tonquelle steht bewusst **nicht** im Dienst, sondern in
`zustand.json`, und wird am Pult gewählt. Neben der Gerätenummer steht
dort auch der Gerätename, und gesucht wird zuerst nach dem Namen: die
Nummern verschieben sich, sobald jemand ein USB-Gerät umsteckt oder der
Rechner ohne angemeldete Sitzung hochfährt.

Nachsehen, ob alles steht:

```
./pruefen.sh
```

Das geht Grafikkarte, Ollama, Modelle, Dienst, Netz, Tonquelle und
Zustand durch und sagt bei jedem Fund, was zu tun ist. Es läuft auch,
wenn der Dienst gar nicht steht — dann zeigt es zusätzlich die letzten
Zeilen aus dem Journal. Gedacht für den Fall, dass jemand anderes vor dem
Rechner steht: `./pruefen.sh > bericht.txt 2>&1` und verschicken.

Aktualisieren:

```
./aktualisieren.sh
```

Das holt den neuen Stand, ergänzt fehlende Abhängigkeiten, startet den
Dienst neu und lässt den Selbsttest laufen. Lokale Änderungen werden
nicht überschrieben: gibt es welche, bricht es ab und zeigt sie.
`zustand.json` bleibt unangetastet.

## Lizenz

Der Code steht unter MIT. Modelle, Stimmen und das Logo haben eigene
Bedingungen, siehe [LIZENZEN.md](LIZENZEN.md).

Das Programm kostet nichts. Wer etwas zurückgeben möchte, findet in der
Zuhörer-Oberfläche einen Spendenknopf.
