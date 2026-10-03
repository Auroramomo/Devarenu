# Was sich geändert hat

Die neueste Fassung steht oben. Ältere Einträge bleiben stehen — wer
einen Rechner vor sich hat, der seit einem Jahr läuft, soll nachlesen
können, was seither dazugekommen ist.

---

## 0.4.0 — Spanisch und Portugiesisch, und sechs Dinge, die niemand sah

*03.10.2026.*

### Für alle

**Spanisch und Portugiesisch sind freigegeben.** Je ein
Muttersprachler hat die 72 Fachbegriffe durchgesehen und rund 80
weitere beigetragen. Eine Gemeinde wählt sie am Pult unter *Übersetzt
nach*; **in Rostock ändert sich dadurch nichts**, die Zielsprachen
bleiben Englisch, Russisch und Persisch.

**Bibelstellen stehen in der Zählung der Zielsprache.** Die Schlachter
zählt wie der hebräische Text — aus „Joel 3,1" wird englisch „Joel
2:28", aus „Psalm 23" russisch „Псалом 22". Wer mitliest, findet die
Stelle in seiner eigenen Bibel.

**„Jetzt aus dem Netz aktualisieren"** als Knopf am Pult, unter
*Einrichtung*. Nur am Gemeinde-PC selbst, nie während einer laufenden
Übersetzung.

**Aufnahmen lassen sich von Hand löschen**, je Aufnahme, mit einer
Rückfrage, die den Dateinamen nennt.

**Fehlen Thema und Bibelstellen, erinnert das Pult daran** — eine gelbe
Zeile, die nichts aufhält.

**Acht Schreibweisen von Bibelstellen wurden nicht erkannt** und
trotzdem aus dem Thema gelöscht: „1. Kor 13", „1 Mose 1", „5 Mose 6"
und fünf weitere. Behoben.

### Für Techniker

**A — Spanisch und Portugiesisch.** Neuer Glossarstand
`glossar_v0.9.csv`, und er ist der erste, der aktiv wird: bis 0.3.8
zeigte `config.GLOSSAR_CSV` über vier Arbeitsstände hinweg auf `v0.4`.
`werkzeuge/glossar_rueck_es_pt.py` liest die beiden `.docx` mit der
Standardbibliothek und trägt ein: 3 Tabellenkorrekturen, 13
Nebenformen, 18 geänderte Zellen aus den Zusatzlisten, 43 neue Zeilen.
Jede Entscheidung steht als Tabelle im Quelltext.

*Die Falle dabei:* das Glossar wirkt über die **Suchvarianten**, nicht
über die Spalte. `glossar.finde()` sortiert nach Länge; eine neue Zeile
„28 Glaubensüberzeugungen" verdrängt D034 „Glaubensüberzeugungen", und
weil die neue Zeile für Englisch leer ist, fehlt der Begriff im
englischen Prompt. **Neun von 52 Kandidaten hätten das getan.** Sie
sind abgewiesen. `werkzeuge/glossar_vergleich.py` vergleicht nicht die
Datei, sondern das Ergebnis — `glossarzeilen()` über 1444 Texte, dazu
Whisper-Prompt und persische Vokalisierung. en, ru und fa kommen
Zeichen für Zeichen gleich heraus.

**Bibelbuchnamen brauchen keine Einstellung je Gemeinde.** Je zwei
unabhängige Übersetzungen verglichen (es: Reina Valera 1909 gegen
Sagradas Escrituras 1569; pt: Almeida Atualizada gegen Bíblia Livre):
**0 von 66** Namen verschieden. Dabei fielen fünf eigene Fehler auf
(`Nahú`, `Cânticos`, `Abdias`, `Miqueias`, `Filemão`) — berichtigt.
Dazu die **Anrede** als feste Vorgabe (`config.ANREDE`): ustedes/vocês
für die Gemeinde, tú/tu für Gott, wie in Reina-Valera und Almeida.

**I — Vorbereitung am Pult.** `bibelstellen.py` normalisierte beim
Nachschlagen nur die Leerzeichen, nicht die Punkte: in der Tabelle
stand `1.korinther` und `1kor`, gesucht wurde `1.kor`. Beide Seiten
normalisieren jetzt gleich (null Kollisionen über alle Formen aller
Sprachen). Neu erkannt: „Kapitel 3 Vers 16", die langen Buchtitel
(`Offenbarung des Johannes` ergab bis 0.3.8 *Johannes* 14), Umlaute als
ae/oe/ue. Nicht mehr erkannt: Abkürzungen, die gewöhnliche Wörter sind
— „Zum zweiten Mal 2 Lesungen" ergab Maleachi 2, „am 3. Oktober" hätte
Amos 3 ergeben.

**Grundregel: aus dem Thema-Text werden nur anerkannte Treffer
entfernt.** Was nicht erkannt wird, bleibt stehen.

**Der Whisper-Prompt** wurde als „die letzten 700 **Zeichen**" gebaut.
Whisper schneidet bei 223 **Token** ab. Gemessen am Beispiel „Nehemia
baut die Mauer. Nehemia 1-4": alt 258 Token **und der Kopf war weg**,
neu 210 Token mit Kopf. Jetzt gilt eine Rangfolge — Kopf bleibt, dann
weichen die Namen von hinten, der Verlauf zuerst —, gezählt mit dem
Tokenizer des eingesetzten Modells.

`namen_block_b.csv` ist **nicht** neu gebaut: die Bibel-PDF liegt nicht
im Repo und an keiner dokumentierten Stelle. Was fehlt, steht jetzt mit
Zahlen im Modulkommentar von `namen_aus_bibel.py` — 25 von 66 Büchern,
und die Lücke ist keine Absicht: `buch_abkuerzungen()` filtert gegen
die Querverweisspalte und nimmt dabei 76 ausgeschriebene Buchnamen mit,
also gerade Mose, Petrus, Johannes, Daniel und Nehemia.

**J — Löschen.** `aufnahme.loeschen()` behandelt den Namen **nicht als
Pfad**: gesucht wird in der Liste, die `aufnahmen()` ohnehin aufbaut,
auf Gleichheit des Dateinamens. `../../zustand.json` steht in keiner
Liste. Eine laufende Aufnahme ist nicht löschbar (409). Ins Journal
geht nur der Dateiname.

**B — Der Update-Knopf.** Der Server läuft als `devarenu`, das Update
braucht root. Statt einer `sudo`-Regel, die dauerhaft offenstünde, legt
der Server eine Datei in seinem eigenen Ordner an
(`update/online-jetzt`), und `devarenu-onlineupdate.timer` sieht als
root alle 30 Sekunden danach — **kein Parameter, den der Dienst
unterschieben könnte, und kein Befehl, den er wählen kann.** Derselbe
Weg, den der Stick-Knopf seit 0.2.12 geht. Gibt es kein
Wartungs-WLAN, wird die Verbindung benutzt, die gerade steht (ein
Handy-Hotspot); getrennt wird nur, was Devarenu selbst verbunden hat.
Stromausfall mitten im Update wird beim nächsten Start erkannt und als
*abgebrochen* vermerkt.

**K — Zählungen.** `werkzeuge/zaehlung_bauen.py` vergleicht die
Verszahlen je Kapitel aus drei gemeinfreien Übersetzungen und leitet
`zaehlung.json` ab: 4 kB, **nur Zahlen, keine Zeile Bibeltext**.
Umgerechnet wird nur, wo die Regel eindeutig folgt — Psalmenversatz für
die englische Zählung (62 von 150, Versatz ausschließlich 1 oder 2),
Psalmennummer für die Synodalzählung (132), Joel und Maleachi. **Nicht**
umgerechnet: 29 weitere Bücher mit abweichenden Verszahlen, Spannen,
Verse ohne Gegenstück, und Persisch. Live-Lauf mit `gemma4:12b`: 12 von
12 Sätzen richtig. Einen Fall hat erst der Lauf aufgedeckt — das Modell
schrieb „в Псалме 22" statt „Псалом 22", denselben Psalm im
Präpositiv; seitdem prüft `steht_drin()` den Stamm des Buchnamens.

**D — Sicherung.** `sichern.sh` und `zuruecksichern.sh`. Geheimnisse
(WLAN-Passwort, ntfy-Thema, RustDesk-Kennwort) nur verschlüsselt, mit
einer Passphrase, die abgefragt und nirgends gespeichert wird und auch
nicht in der Befehlszeile steht. **Ohne Passphrase sind die Geheimnisse
weg; alles andere lässt sich trotzdem wiederherstellen.** Die Aufnahmen
gehen ausdrücklich nicht mit. Neu: **ERSTINSTALLATION.md**, zehn
Abschnitte von der Kiste bis zur Abnahme, nach jedem eine Kontrolle.

**E — Signierschlüssel.** Dass `schluessel.erlaubt` mehrere Schlüssel
führen kann, stand seit 0.3.1 darin — geprüft wurde es nie. Jetzt
steht es im Prüfstand. *Dabei fiel ein Fehler in der eigenen
Dokumentation auf:* die Adresse vor dem Schlüssel ist ein **Etikett,
keine Bedingung**. `git verify-tag` nimmt ein Tag an, solange der
**Schlüssel** in der Datei steht — auch unter fremder Adresse. Wer
einen Schlüssel sperren will, löscht die **Zeile**.

**F — Lizenzen.** `werkzeuge/stimmlizenzen.py` liest die `MODEL_CARD`
aller 21 Stimmen. Zwei Befunde betreffen Sprachen, die in Rostock
laufen: **Englisch** hängt an den Blizzard-2013-Daten, deren Lizenz die
Nutzung „exclusively for Research Purposes only" gewährt, und
**Russisch** nennt gar keine Lizenz. Entfernt ist nichts; die Tabelle
in `LIZENZEN.md` ist die Grundlage für eine Entscheidung.

**C — Die Testumgebung.** `VM-TESTUMGEBUNG.md`,
`vm_pruefstand.sh`, `testmodus.py`. Der Testmodus greift nur, wenn die
Datei `TESTMODUS` daliegt **und** der Rechner keine NVIDIA-Karte hat.
Die zweite Bedingung ist die eigentliche Sperre: die erste allein wäre
eine Datei, und Dateien wandern — kopierte Ordner, zurückgespielte
Sicherungen, Sticks aus Testverzeichnissen. Dann lief am Sonntag ein
`tiny`-Modell, und am Pult sähe man es nicht: die Übersetzung käme ja,
nur als Unsinn. Fällt `nvidia-smi` aus, gilt „Karte da" — im Zweifel
Betrieb, nicht Test. Liegt die Marke doch auf einem Rechner mit Karte,
sagt der Systemcheck es trotzdem.

Die ehrliche Liste, **was die VM nicht prüft**, steht in
`VM-TESTUMGEBUNG.md` zuerst und nicht zuletzt: NVIDIA-Treiber,
Übersetzungsqualität, Ton, Wayland-Sitzung, BIOS-Wecker, Handys im
Saal, Hardware-Untergrenze. „Grün auf der VM" heißt nicht „grün im
Saal".

**G — Der Fahrplan.** `FAHRPLAN-1.0.md` ist neu geschnitten: **sieben
Blocker** (Update-Weg mehrfach ohne Eingriff, VM-Testumgebung,
Signierschlüssel gesichert plus zweiter, der Update-Knopf im Feld,
Erstinstallation von Fremden durchgespielt, Lizenzen der Bausteine
entschieden, Datenschutz abgenommen), **sechs Sollte** (freigegebene
Sprachen, Qualität im Betrieb, Kaltstart, Netz je Gemeinde, Stick-Weg,
Bus-Faktor) und ein Abschnitt *nicht mehr auf der Liste* — **RustDesk
unter Wayland ist kein Blocker mehr**, der Weg über
RustDesk-Terminal plus TCP-Tunnel trägt, und über ihn geht auch der
neue Update-Knopf.

### Was offen ist

- Der Prüfstand für den Einspielweg auf die jeweils neue Fassung ist
  angefangen und noch rot: der Gesundheitscheck fragt den laufenden
  Dienst über HTTP und trifft dabei den echten statt den der
  Sandbox. Es fehlt eine Attrappe dafür. **Der Weg auf 0.4.0 ist
  damit nicht geprüft.**
- Der Release-Text ist nicht geschrieben.
- `namen_block_b.csv` wartet auf die Bibel-PDF.
- Neun Glossarzeilen warten auf geprüfte Werte für en, ru, fa.
- Das pt-Tempo 1,15 ist im Betrieb nicht bestätigt.
- Zwei Stimmlizenzen sind offen (`en` nur Forschung, `ru` ungenannt).
- `ERSTINSTALLATION.md` hat noch niemand abgearbeitet, der das Projekt
  nicht kennt.

---

## 0.3.8 — die Predigt als MP3, und sechs Meldungen, die logen

*28.09.2026.*

### Für alle

**Die Predigtaufnahme ist jetzt eine MP3.** Sie heißt
`Predigt_03_10_2026.mp3` — mit dem Datum des Tages, an dem sie
angefangen hat. Gibt es den Namen schon, kommt `_2` dahinter, dann
`_3`; überschrieben wird nie. Eine Stunde belegt rund 22 MB statt
bisher 115, sie passt also an eine Mail. Einwilligung, die sieben
Tage und der Abruf nur am Gemeinde-PC bleiben, wie sie waren.

**Die Fehlerberichte lassen sich einschalten, ohne vorher das
Wartungsfenster einzuschalten.** Bisher brach der Befehl mit einer
Meldung über das Autoupdate ab — um das es gar nicht ging.

**Am Pult unter Einrichtung steht jetzt der neueste Update-Stand.**
Auf dem Gemeinderechner stand dort monatelang „Update 0.3.1 ist
fehlgeschlagen", obwohl seitdem mehrere Fassungen sauber eingespielt
worden waren.

**Der Erklärtext zum Testprotokoll erscheint nur noch da, wo es auch
den Schalter dazu gibt.**

### Für Techniker

**MP3: 48 kbit/s, mono, feste Bitrate.** Der Ton kommt mit 16 kHz vom
Mikrofon, mehr als 8 kHz Bandbreite steckt nicht darin. LAME arbeitet
dort im MPEG-2-Modus. 32 kbit/s verschmiert hörbar die Zischlaute,
64 kbit/s kostet ein Drittel mehr Platz für nichts, was bei dieser
Bandbreite noch ankäme. Feste Bitrate, damit sich Größe und Dauer
auseinander ausrechnen lassen.

Geschrieben wird weiter fortlaufend, in einen Koder-Prozess hinein.
Ohne Xing- und ohne ID3-Kopf: die Datei ist damit nichts als eine
Folge von MP3-Rahmen, an jeder Stelle abschneidbar und trotzdem
abspielbar. Fällt der Strom aus, ist alles bis dahin da — das galt
für WAV und gilt weiter.

**Geprüft wird, nicht angenommen.** `ffmpeg` ist seit jeher eine feste
Abhängigkeit, MP3 schreibt es aber nur mit `libmp3lame`, und das ist
eine Übersetzungsoption. `aufnahme.koder_pruefen()` fragt einmal beim
Start: ffmpeg mit libmp3lame, sonst das Programm `lame`, sonst WAV wie
bisher. Die Aufnahme fällt nie aus. Der Systemcheck meldet den dritten
Fall als Hinweis, samt Nachrüstweg ohne Netz
(`pacman -U lame-*.pkg.tar.zst` vom Stick).

Der Altbestand wird nicht umbenannt: `aufnahme.aufnahmen()` listet
`.mp3` und `.wav`, groß wie klein geschrieben, und die Frist läuft
für beide weiter. `/mitschnitt/<name>` liefert den passenden
Medientyp.

**`wartungsfenster.sh --berichte ja` bei ausgeschaltetem Fenster.**
Zwei Stellen waren schuld. Die Sperre in `wartungsfenster.py` fragte
`autoupdate or berichte_senden` ab und gab dazu die Autoupdate-Meldung
aus; sie fragt jetzt nur noch `autoupdate`. Und `einstellung()` setzte
`berichte_senden` bei ausgeschaltetem Fenster stumm auf `False`
zurück — wer den Schalter setzte, bekam ihn kommentarlos aberkannt.
Das gilt jetzt nur noch fürs Autoupdate. Gesendet wird ohnehin nur im
Fenster; der Schalter merkt vor, und die Ausgabe sagt das.

**`rtcwake` als Dienstbenutzer.** `/dev/rtc0` gehört `root:clock 0660`
— von Hand aufgerufen kam `wartungsfenster.sh --einschalten` dort
nicht hinein und zeigte trotzdem den BIOS-Hinweis. Wer dem folgte,
schraubte am falschen Ende. Jetzt drei Wege in dieser Reihenfolge:
geradeaus (als root und für jeden in der Gruppe `clock`), `sudo -n`,
und ein Neustart von `devarenu-fenster-wecker.service`, die als root
genau diesen Wecker stellt. Sitzt jemand am Rechner, darf `sudo` am
Ende nach dem Passwort fragen. Schlägt alles fehl, unterscheidet die
Meldung fehlende Rechte von einem widerspenstigen BIOS und nennt
jeweils die passende Abhilfe.

**`zustand.json`: Zuwachs ist kein Befund.** Der Updater verglich eine
sha256-Summe über die ganze Datei; nach 0.3.4 → 0.3.7 meldete er
darum `FEHLT zustand.json hat sich geändert`, obwohl nichts Schlimmes
passiert war. Verglichen wird jetzt Schlüssel für Schlüssel:

* **neue** Schlüssel sind in Ordnung — `gemeinde` und
  `nutzung_melden` gab es in 0.3.4 noch nicht;
* ein **erstes Füllen** ist in Ordnung — war der Wert `0`, leer oder
  `null` und steht jetzt etwas darin. Genau das ist
  `aufnahme_frist_ab`: `0` heißt „die Frist läuft noch nicht", und der
  erste Start einer Fassung mit Aufnahmefrist trägt den Zeitpunkt ein,
  damit der Altbestand nicht sofort gelöscht wird. **Gewollt**, und
  nur einmal;
* ein **geänderter** Wert, ein **weggefallener** Schlüssel und andere
  Rechte als 600 bleiben ein Befund, mit Namen.

`true`/`false` zählt ausdrücklich nicht als „leer": ein Schalter, der
von selbst umspringt, soll auffallen. Gemerkt wird nur ein Abdruck je
Schlüssel, nie der Wert — in `zustand.json` steht das WLAN-Passwort im
Klartext. **Die Sperre sitzt in `aktualisieren.sh`, der stabilen
Hälfte: sie greift erst beim Update *von* 0.3.8 aus, nicht bei diesem.**

**Der Update-Stand am Pult.** `stand.json` schreibt der Stick-Kern,
`stand-online.json` schreibt `aktualisierung.sh` auf dem Netzweg. Der
Fehlerbericht nahm seit 0.3.5 den jüngeren von beiden, das Pult las
nur den ersten. Die Auswahl steht jetzt einmal, in
`fehlerbericht.juengerer_stand()`, und beide benutzen sie.

**Der Erklärtext zum Testprotokoll** wurde in `pruefprotokollAnzeigen()`
unabhängig von `pruefprotokollreihe` ein- und ausgeblendet. Aus dem
Saal oder über den Tunnel las man drei Zeilen über einen Schalter, den
es auf dieser Seite nicht gab.

**`/run/devarenu/dnsmasq.leases` ist `0640`** statt `0644`. Darin
stehen MAC-Adressen und die Namen, die die Handys von sich aus melden.
`UMask=0137` im systemd-Zusatz; der Ordner bleibt `0755`, darin steht
nur ein Dateiname. `pruefen.sh` prüft die Rechte mit.

**Nebenbei gefunden.** `abschalten_faellig(..., stunden=None)` hieß
zugleich „nicht angegeben" und „Laufzeit unbekannt". Der Prüfstandfall
„Laufzeit unbekannt: keine Behauptung" prüfte dadurch in Wahrheit die
Betriebszeit des Rechners, auf dem er lief — auf einem eben
gestarteten ging er durch, nach einem Tag nicht mehr.

**Prüfstand.** Neue Fälle: Name, Endung, `_2`/`_3` und Größenordnung
der MP3 sowie die Kollision über Endungsgrenzen hinweg
(`aufnahme_test.py`); Berichte-Schalter bei ausgeschaltetem Fenster
und die Gegenprobe fürs Autoupdate, dazu `zustand.json`-Zuwachs gegen
geänderten Wert am echten `aktualisieren.sh` (`online_test.sh`); die
Auswahl des jüngeren Update-Standes (`bericht_test.py`); und eine
statische Prüfung, dass der Erklärtext am Schalter hängt
(`pruefprotokoll_test.py`).

---

## 0.3.7 — GPLv3, und eine Messung, die zweimal gemacht werden musste

*28.09.2026.*

### Für alle

**Devarenu steht jetzt unter GPLv3.** Bis 0.3.6 war es MIT. Der
Grund: Piper, das die Stimmen erzeugt, ist selbst GPL und läuft im
selben Prozess. Für eine Gemeinde ändert sich dadurch nichts — das
Programm bleibt kostenlos und darf weitergegeben werden.

**Persisch spricht Bibelstellen etwas flüssiger.** Der Doppelpunkt
in „۳:۱۶" machte dort eine unnötige Pause.

**Spanisch und Portugiesisch schreiben Bibelstellen wieder mit
Doppelpunkt** — so, wie es in spanischen und portugiesischen Bibeln
üblich ist. In 0.3.6 war das aus einem falschen Grund
zurückgenommen worden.

### Für Techniker

**Die Lizenz.** `COPYING` mit dem GPLv3-Text (Fassung von gnu.org;
inhaltlich dieselbe, die Piper mitliefert — Unterschied nur `http`
gegen `https`). Die MIT-Datei `LICENSE` ist entfernt, `LIESMICH.md`
und `LIZENZEN.md` sind angepasst. Im Quelltext standen keine
MIT-Kopfzeilen. Was bis 0.3.6 unter MIT veröffentlicht wurde, bleibt
unter MIT — das lässt sich nicht rückwirkend ändern, und es steht so
in `LIZENZEN.md`.

**Der Doppelpunkt bei Piper — und warum ich zweimal messen musste.**

Der erste Anlauf verglich `53, 5` gegen `53: 5`, beide **mit**
Leerzeichen, und fand den Doppelpunkt überall teurer: ru +0,33 s,
fa +0,18 s, en +0,06 s.

Nur schreibt das Modell keine Leerzeichen. Es schreibt `53:5`, und
in dieser Form ist der Doppelpunkt etwas ganz anderes:

```
Исаия 53:5   1,68 s        Исаия 53 5    1,68 s
Исаия 53,5   2,12 s        Исаия 53: 5   2,68 s
```

Ohne Leerzeichen behandelt espeak `53:5` wie `53 5` — **gar keine
Pause**. Das Komma macht dort eine. Der erste Anlauf hat also eine
Frage beantwortet, die niemand gestellt hatte.

Zweiter Anlauf, auf den **echten Modellausgaben** aus
`messungen/bibelstellen_trenner.json`:

| Sprache | Sätze | Median | Summe | |
|---|---|---|---|---|
| en | 7 | ±0,00 s | −0,73 s | an der Schwelle |
| ru | 5 | **+0,57 s** | +3,08 s | das Komma **kostet** |
| fa | 4 | **−0,47 s** | −1,79 s | das Komma spart |

Also **nur Persisch**. Bei Russisch wäre es eine Verschlechterung
gewesen — genau das Gegenteil dessen, was der erste Anlauf nahelegte.

Der `SPRECHFORM`-Eintrag ersetzt `Zahl:Zahl` durch `Zahl,Zahl`, ohne
Leerzeichen (mit wäre es langsamer als vorher), und deckt
lateinische, arabisch-indische und persische Ziffern ab. Persische
und lateinische Ziffern verhalten sich identisch, ebenso arabisches
und lateinisches Komma — espeak normalisiert beides, auf die
Millisekunde. Das Muster deckt sie trotzdem alle ab.

Mitgetroffen wird eine Uhrzeit (`18:30`). Auch dort wird der
Doppelpunkt nicht gesprochen, es entstehen keine falschen Wörter —
nur eine andere Pause. Hingenommen. Ein Doppelpunkt nach einem Wort
bleibt unberührt.

**Vergleichslauf** über die acht Sätze je Sprache:

| | Untertitel | Sprechdauer vorher | nachher | |
|---|---|---|---|---|
| de | 8/8 gleich | 29,42 s | 29,42 s | ±0 |
| en | 8/8 gleich | 24,33 s | 24,33 s | ±0 |
| ru | 8/8 gleich | 33,98 s | 33,98 s | ±0 |
| fa | 8/8 gleich | 33,79 s | **32,00 s** | −1,79 s |

Der Untertitel ist in allen vier Sprachen Zeile für Zeile
unverändert — `SPRECHFORM` greift ausschließlich vor Piper.

**Und dieselbe Fehlmessung hatte noch etwas gekostet.** Die
Entscheidung von 0.3.6, es und pt beim Komma zu lassen, beruhte auf
genau demselben Vergleich mit Leerzeichen. Nachgemessen auf den
echten Modellausgaben, mit den gewählten Stimmen:

| Sprache | Stimme | Sätze | Median | Summe |
|---|---|---|---|---|
| es | es_MX-claude-high | 7 | **+0,27 s** | +2,09 s |
| pt | pt_BR-jeff-medium | 7 | **+0,29 s** | +2,10 s |

Das **Komma** ist dort das teurere Zeichen, nicht der Doppelpunkt.
`STELLEN_TRENNER` steht für es und pt wieder auf `:` — die
Schreibweise, die Reina-Valera und Almeida ohnehin verwenden. Die
falsche Begründung ist in `config.py`, in der Messdatei und im
Eintrag zu 0.3.6 richtiggestellt; der alte Absatz bleibt stehen,
damit nachvollziehbar ist, was schiefging.

---

## 0.3.6 — weniger speichern, und aufschreiben, was bleibt

*28.09.2026.*

### Für alle

**Der Rechner merkt sich weniger von den Zuhörern.** Die Liste, wer
wann welche Netzwerkadresse bekommen hat, lag auf der Platte und
jede Aushandlung im Journal — mit Geräteadresse und dem Namen, den
das Handy sich gibt, oft ein Vorname. Jetzt liegt die Liste im
Arbeitsspeicher und ist nach dem Ausschalten weg, und ins Journal
kommt davon nichts mehr.

**Neu: `DATENSCHUTZ.md`** — ein Textbaustein, den eine Gemeinde in
ihre eigene Datenschutzerklärung übernehmen kann, und darunter das
Verzeichnis aller elf Verarbeitungen. Auf der Zuhörerseite und am
Pult steht dazu bewusst nichts.

**Spanisch und Portugiesisch** haben ihre Stimme bekommen. Beide
Sprachen bleiben aus. *(Bibelstellen dort seit 0.3.7 mit
Doppelpunkt.)*

### Für Techniker

**Datensparsamkeit** (`netz_einrichten.sh`): `quiet-dhcp`,
`quiet-dhcp6`, `quiet-ra`, und die Mietliste unter
`/run/devarenu/dnsmasq.leases` statt auf der Platte — `systemd` legt
den Ordner über `RuntimeDirectory` an. **Wirkt erst nach einem
erneuten `sudo bash netz_einrichten.sh`.**

Im Server gehen zwei Zeilen, die eine Zuhöreradresse nannten, jetzt
über `geraetekennung()`: `Geraet a3f1` statt `10.0.0.57`, mit einem
Salz, das mit dem Prozess entsteht und mit ihm verschwindet. Was die
Technik braucht — ein Gerät zwanzigmal oder zwanzig Geräte — steht
weiter da. Die Zugriffsprotokolle von uvicorn waren schon aus
(`log_level="warning"`).

**Piper ist GPLv3, nicht MIT.** In `LIZENZEN.md` stand „MIT"; das war
einmal richtig (`rhasspy/piper`), das installierte Paket ist der
Nachfolger `OHF-voice/piper1-gpl` und trägt die GPL im eigenen
`COPYING`. Benutzt wird es als Python-Modul im selben Prozess — der
Fall, den die GPL streng sieht. Der Sachverhalt, drei Wege und eine
Empfehlung stehen jetzt dort. **An der Lizenz ist nichts geändert.**

**Die Sitzung steht je Rechner in `netz.json`** (`wayland` oder
`x11`, Vorgabe `wayland`). `rechner_einrichten.sh` schreibt danach
die passende Zeile, und der Systemcheck vergleicht gegen diesen Wert
statt gegen eine feste Erwartung — er meldet jetzt auch den Fall,
dass Anmeldung und Lauf zwar zusammenpassen, aber nicht zu dem, was
eingetragen ist. Umgestellt wird nur vor Ort.

**Bibelstellen-Trennzeichen: geprüft und verworfen** — *und in 0.3.7
zurückgenommen, weil die Messung unten falsch war. Der Absatz bleibt
stehen, damit nachvollziehbar ist, was entschieden wurde und warum es
nicht trug.* Gemessen mit
`gemma4:12b`, acht Sätzen, `temperature 0.1`, `seed 7`, ohne jede
Anweisung: en `:` (7/7), fa `:` (4/4), ru gemischt (5× `:`, 2× `,`),
es und pt durchweg `,` — obwohl Reina-Valera und Almeida den
Doppelpunkt setzen.

Die Anweisung für es und pt war gebaut und geprüft: sie wirkt (7/7),
und der Vergleichslauf zeigte **de, en, ru und fa Zeile für Zeile
identisch** (8/8), Trennzeichen unverändert.

Sie ist trotzdem wieder draußen. Der Doppelpunkt geht auch an Piper,
und dort ist er ein **Pausenzeichen**: gemessen **+0,27 bis +0,49 s
je Bibelstelle**. Gesprochen wird er nicht — der Phonemisierer macht
daraus keine Wörter (`…tɾˈes: θˈinko` gegen `…ðˈos pˈuntos`) —, aber
die Pause kostet Zeit, und Zeit ist das, woran die Übersetzung im
Gottesdienst knapp ist. Der Preis: im Untertitel steht ein Komma, wo
eine spanische Bibel einen Doppelpunkt setzt.

Beide Messungen stehen in `messungen/bibelstellen_trenner.json`.

> **Diese Begründung trägt nicht.** Gemessen wurde `53, 5` gegen
> `53: 5`, beide **mit** Leerzeichen — das Modell schreibt aber
> `53:5`, und ohne Leerzeichen kostet der Doppelpunkt gar nichts.
> Nachgemessen in 0.3.7: das *Komma* ist dort das teurere Zeichen.
> Die Anweisung ist seit 0.3.7 wieder da.

**`laengenfaktor.py` reicht `--speaker` durch** und misst jeden
Sprecher einzeln. Damit ist `fr_FR-upmc-medium` geklärt: der alte
Wert 0,447 war Sprecher 0, und dieser Sprecher spricht mit **46
Zeichen je Sekunde** — rund doppelt so schnell wie jede andere Stimme
(siwis 20,7, Sprecher 1 21,3). Das ist keine Rede mehr. Sprecher 1
läge bei 1,091 und wäre brauchbar, lässt sich aber nicht eintragen:
die Tempotabelle kennt nur Stimmnamen, und der Server wählt beim
Sprechen keinen Sprecher. Die Stimme bleibt draußen — jetzt aus
einem gemessenen Grund statt aus einer Vermutung.

**es und pt:** Stimme B aus den Prüfpaketen ist
`es_MX-claude-high` und `pt_BR-jeff-medium` (A/B/C sind die drei
gemessenen Stimmen, nach Faktor sortiert). Für `pt_BR-jeff-medium`
steht das Tempo jetzt auf **1,15 statt der gemessenen 1,366** — der
Prüfer sagt zu schnell, Wörter verschluckt. Wenn Stoppuhr und Ohr
auseinandergehen, gewinnt das Ohr; die Zahl ist eine Entscheidung
und keine Messung und gehört beim nächsten Rücklauf bestätigt.

Dazu **Kommapausen**: Piper 1.7 kennt dafür keine Einstellung —
`SynthesisConfig` hat nur `length_scale`, `noise_*` und `volume`.
Der Satz wird deshalb an den Kommas geteilt, stückweise gesprochen
und mit Stille verbunden, 180 ms für diese eine Stimme. Steht eine
Stimme nicht in `PAUSE_KOMMA_MS`, läuft alles wie bisher.

**Ellen G. White** heißt auf Spanisch „Elena G. de White" (Glossar
D010, nur diese eine Zeile geändert). Gesprochen wird das Initial
nicht: Piper liest ein einzelnes „G." als Buchstaben vor. Dafür gibt
es `SPRECHFORM` — Ersetzungen, die **nur** vor Piper greifen, nicht
im Untertitel. Die vier Glossarbegriffe, die auf den Prüfer warten,
sind unberührt.

**`FAHRPLAN-1.0.md`** hat drei neue Abschnitte: die
Erstinstallation Schritt für Schritt (Punkt 4), was beim Kaltstart
passieren soll und was davon geprüft wird (Punkt 3), und die
Hardware-Untergrenze aus den 26 Messläufen im Repo (Punkt 8) —
Median 1,1 bis 1,4 s Verzögerung, kein Drift, Warteschlange
durchgehend 0. Was unbekannt ist, steht als unbekannt da: auf
welcher Karte die Läufe entstanden, ob der Rückstand über eine
dreiviertel Stunde wächst, wo die Untergrenze liegt.

### Was offen ist

- Russisch schreibt Bibelstellen uneinheitlich (5× Doppelpunkt,
  2× Komma). Das zu vereinheitlichen wäre eine Verbesserung — aber
  eine Änderung am laufenden Betrieb, die niemand verlangt hat.
- Die Lizenzfrage ist dargestellt, nicht entschieden.
- Die Erstinstallation hat noch niemand abgearbeitet, der das
  Projekt nicht kennt.

---

## 0.3.5 — die Ablage war zu, und das Programm sagt jetzt, was es sendet

*28.09.2026.*

### Für alle

**Der Name der Gemeinde steht auf der QR-Seite.** Unter dem Titel als
„Devarenu · <Name>", einzutragen am Pult unter Einrichtung. Leer
lassen heißt: keine Anzeige.

**Ein Schalter „Nutzung an den Entwickler melden".** Gesendet werden
Name der Gemeinde, Fassung und Datum — sonst nichts. Das steht auch am
Pult neben dem Schalter. Vorgabe aus, jederzeit wieder abschaltbar.

**`AUFSTELLEN.md` listet jetzt vollständig auf, was dieser Rechner
nach draußen sendet** — alle vier Wege, mit Inhalt und Schalter. Ohne
Wartungsfenster und ohne `meldung.json` ist die Liste leer. Es gibt
keine verdeckten Übermittlungen.

**Das Spendenkonto wird beim Start geprüft.** Stimmt die Prüfziffer
nicht, steht am Pult und auf der QR-Seite ein Hinweis. Es wird nichts
gelöscht und nichts abgeschaltet.

### Für Techniker

**Die Ablage war zu.** `/var/lib/devarenu/updates` stand auf `710` —
das gibt das Durchgehen der **Gruppe**, und der Ordner gehört
`root:root`. Der Dienstbenutzer ist dort „andere" und bekam nichts;
für ihn war der Ordner so zu wie mit `700`. Er kam damit nicht an
seine eigene Sicherung. Jetzt `711`: hindurchgehen ja, hineinsehen
nein. Gesetzt an einer Stelle (`ablage_rechte()` im Kern), und der
Prüfstand verbietet `700` und `710` auf `$DATEN`/`$ABLAGE`.

Mein Kommentar von 0.3.2 sagte das Richtige („der Dienstbenutzer muss
hindurchgehen können"), die Zahl war falsch.

**`gesundheit.sh --vorher` meldete Erfolg, wenn nichts geschrieben
wurde.** `mkdir` und die Umleitung scheiterten mit „Keine
Berechtigung", die nächste Zeile sagte trotzdem „Befunde vor dem
Update gemerkt", und die Aufrufer hängten ein `|| true` an. Beides ist
weg: ein Schreibfehler ist jetzt ein Fehler, und das Update wird
angehalten. Ohne Grundlinie gilt hinterher jeder vorhandene Befund als
neu — dann rollt ein tadelloses Update zurück.

Dabei fiel eine dritte Stelle derselben Machart auf: `if ! cmd | sed`
prüft den Rückgabewert von **sed**, und sed gelingt immer. Jetzt wird
erst aufgefangen, dann ausgegeben.

**Der Rechtewege-Prüfstand kennt den Elternordner.** Es genügt nicht,
die Rechte einer Datei zu prüfen — jeder Ordner auf dem Weg dorthin
muss durchgehbar sein. Genau daran lag es.

**„Letztes Update" zeigte die Stick-Meldung vom 27.09.**, obwohl
danach zweimal über das Netz eingespielt worden war. `aktualisierung.sh`
schreibt den Stand jetzt selbst nach `update/stand-online.json` — sie
läuft auf beiden Wegen, auch bei einer Überbrückung von Hand. In eine
eigene Datei, weil `update/stand.json` zugleich die Verständigung
zwischen Stick-Kern und Pult ist. `pruefen.sh` und der Fehlerbericht
zeigen den jüngeren der beiden.

**`spendenkonto.py`**: mod 97 nach ISO 13616, ohne Ländertabelle —
eine Tabelle im Repo wäre eine Liste, die veraltet. Bei einem Fehler
geht eine Meldung hinaus, **aber nur, wenn auf diesem Rechner ein
Kanal eingerichtet ist**. Es steht kein Meldeziel im Code; der
Prüfstand sieht nach.

**`LIESMICH.md`** hat einen Abschnitt „Spenden und offizielle
Fassung": ein Spendenkonto, der Fingerabdruck des Signierschlüssels
(`SHA256:EklvDQh9QDDh7a5z9PhdUKXTcH0N+4aNcycsFYQnu+Q`, derselbe wie in
`schluessel.erlaubt`), und die Bitte, veränderte Fassungen nicht unter
dem Namen Devarenu weiterzugeben.

---

## 0.3.4 — der Auszug gehört root, und das Update sah nicht hinein

*28.09.2026. Eine Fassung für genau einen Fehler — und für die
Fehlerart dahinter.*

### Für alle

0.3.3 ließ sich nicht einspielen. Das Update brach ab mit „v0.3.3
bringt keine aktualisierung.sh mit" und änderte **nichts** — der
Rechner blieb heil auf 0.3.2. Die Datei lag sehr wohl im Tag; das
Update durfte nur nicht hinsehen.

### Für Techniker

`aktualisieren.sh` legt den Auszug als `root` mit `700` an — mit
gutem Grund: darin liegt Code, der gleich ausgeführt wird, und
zwischen Prüfen und Ausführen soll ihn niemand tauschen können.
Zwei Zeilen weiter prüfte ein blankes `[ -f "$AUSZUG/…" ]`, ob die
Logik darin liegt. Das lief als Dienstbenutzer und fand nichts.

**„Nichts gefunden" und „darf nicht hineinsehen" sehen gleich aus.**
Deshalb zeigte die Meldung in die falsche Richtung — man sucht im
Tag statt in den Rechten. Jetzt `als_wurzel test -f`.

**Dieselbe Fehlerart ein zweites Mal, an anderer Stelle.** Die
Sicherung gehörte ebenfalls `root` mit `700`, und `gesundheit.sh
--vorher` schreibt seine Grundlinie hinein — als Dienstbenutzer. Der
Schreibversuch scheiterte still (der Aufrufer hängt `|| true` an).
Ohne Grundlinie zählt hinterher **jeder** vorhandene Befund als neu,
und ein tadelloses Update wäre zurückgerollt worden. Das betraf auch
den Stick-Weg, seit es die Sicherung gibt.

Die Sicherung gehört jetzt dem Dienstbenutzer. Sie enthält eine Kopie
von `zustand.json` samt WLAN-Passwort — aber das Original gehört ihm
ohnehin, mit denselben `600`. Der Wurzel zu geben schützte nichts und
kostete die Grundlinie. Der Auszug bleibt `root`-`700`: dort liegt
ausführbarer Code, das ist etwas anderes.

**Die Fehlerart steht jetzt im Prüfstand**, nicht nur die zwei Fälle.
`pruefstand/rechtewege_test.py` liest die Skripte: wo ein Pfad auf
`700` oder `root:root` gesetzt wird, muss jeder spätere Zugriff
darauf durch `als_wurzel` oder `sudo` gehen. Ob ein Skript selbst
Wurzelrechte hat, sagt es an seinen Hilfsfunktionen — wer
`als_wurzel` definiert, muss fragen und hat also keine; wer
`als_benutzer` definiert, ist die Wurzel und steigt herab.

Dazu ein Laufzeitfall in `online_test.sh` mit einer `sudo`-Attrappe,
die Rechte wirklich simuliert: was durch sie läuft, darf in den
Ordner sehen, was daran vorbeigeht, nicht. **Und die `id`-Attrappe
musste dafür weg** — sie meldet `id -u` als `0`, `als_wurzel` nimmt
dann den Wurzel-Zweig, ruft `sudo` nie auf, und der Ordner gehört dem
Prüfbenutzer. Genau so ist der Fehler durch alle bisherigen Läufe
gekommen. Beide Fälle wurden gegen den alten Code geprüft: rot.

---

## 0.3.3 — der Rechner hält sich selbst auf Stand

*28.09.2026.*

### Für alle

**Der Rechner kann sich donnerstags von selbst aktualisieren.** Im
Wartungsfenster, ohne dass jemand dabei ist — und er meldet danach
aufs Handy, was er getan hat. **Vorgabe ist aus.**

Geht dabei etwas schief, **holt er den alten Stand selbst zurück**:
Code, Dienste, Einstellungen. Ohne diesen Rückweg gäbe es den
Schalter nicht.

**Am Pult steht nur noch, was heute jemanden angeht.** Wer sonntags
den Ton fährt, bekommt keine Meldungen mehr über Reparaturvorräte und
Dienstvorlagen. Die liegen jetzt unter Einrichtung im eingeklappten
Abschnitt „Wartung" — und vollständig in `bash pruefen.sh`.

**Spricht jemand in einer anderen Sprache als eingestellt, fällt das
auf.** Am Pult erscheint eine gelbe Zeile. Umgeschaltet wird nichts
von selbst.

**„Mobile Daten ausschalten" ist aus der Anleitung verschwunden** — in
allen vier Sprachen. Mit neuem und älterem iPhone und einem Samsung
geprüft: kein Anmeldefenster, die Seite lädt, der Ton läuft durch.

### Für Techniker

**Der Online-Weg lief in 0.3.2 gar nicht.** `aktualisierung.sh`
verlangte `DEV_SICHERUNG` mit `${...:?fehlt}`, `aktualisieren.sh`
übergab es nicht — das Skript brach ab, bevor es vorspulte. Ohne
Schaden, aber auch ohne Update. Der Prüfstand sah es nicht: er rief
eine **Attrappe** statt der echten Datei auf. Jetzt läuft mindestens
ein Fall gegen die echte, und die Sicherung ist keine Pflicht mehr —
fehlt sie, legt `aktualisierung.sh` sie selbst an. Nur deshalb lässt
sich 0.3.3 mit dem Skript aus 0.3.2 überhaupt einspielen.

Zwei weitere Fehler fielen im selben Zug auf, beide nur sichtbar, weil
gegen die echte Datei geprüft wurde:

- `aktualisieren.sh` setzte **keine Gesundheits-Grundlinie**
  (`gesundheit.sh --vorher`). Jeder vorhandene Befund galt danach als
  neu, und ein tadelloses Update wäre zurückgerollt worden.
- `aktualisierung.sh` reichte `DEV_SICHERUNG` und `DEV_VERSION` nicht
  an `gesundheit.sh` weiter. `sudo -H` räumt die Umgebung ab; die
  Grundlinie wurde unter `/tmp` gesucht und nie gefunden. Das betraf
  auch den Stick-Weg.

**Rückweg auf dem Online-Weg**, Schritt für Schritt wie im Kern: Code
auf die alte SHA, venv-Symlink, Units aus der Sicherung,
`zustand.json` und `netz.json` nur, wenn das Update sie verändert hat.
Danach ein Gesundheitscheck — ein Rückweg, der selbst scheitert, darf
nicht als „zurückgerollt" durchgehen.

**Die Unit-Listen kannten das Wartungsfenster nicht.** Gesichert und
zurückgeholt wurden vier Units, seit 0.3.2 gibt es sieben. Ein
Rückfall hätte ein halb zurückgerolltes Fenster hinterlassen. Jetzt
führen Kern, versionierte Logik und Online-Weg dieselbe Liste, und der
Prüfstand vergleicht alle drei.

**`aktualisieren.sh` kennt jetzt `als_benutzer` und `als_wurzel`.** Es
lief bisher als Besitzer und holte sich Privilegiertes mit `sudo`; der
Fenster-Timer ruft es aber als Wurzel auf, und dann lägen root-eigene
Objekte in `.git`.

**Ein abgelöster HEAD hält nicht mehr grundlos an.** Zeigt ein lokaler
Zweig auf genau denselben Commit, wird wieder angehängt — `main`
bevorzugt, keine Datei angefasst, rückgängig mit `git checkout
--detach`. Zeigt keiner darauf, bleibt es beim Abbruch: dort läge
Arbeit, die ein Anhängen verlöre. Gilt in `stick_update.sh`,
`bootstrap.sh` und `aktualisieren.sh`.

**„Ohne Stimme, laufen als Untertitel" gibt es wieder.** Der Hinweis
fehlte seit 0.3.0, weil niemand mehr `stimmen_fehlen()` aufrief. Er
kommt jetzt aus der versionierten Logik über `melden` — damit erreicht
er das Pult auch mit einem älteren Kern. Das tote Feld `stimmen` und
`upd_stimmen` sind entfernt.

**Testprotokoll** (`pruefprotokoll.py`). Je Abschnitt eine Zeile JSON:
Zeitstempel, Ausgangssprache, erkannter Satz, jede Übersetzung, und
die Dauer jedes Schrittes. Gemessen wurde das alles längst — es fehlte
nur jemand, der es aufschreibt. Regeln wie bei der Aufnahme, aber
**ein** Haken statt zwei; der Schalter steht nur im Arbeitsspeicher
und hört beim Neustart von selbst auf.

**Sprachwache** (`sprachwache.py`). `detect_language` auf jedem
vierten tauglichen Segment. Gemessen mit `large-v3-turbo`, float16,
RTX 5080: 76 ms, unabhängig von der Tondauer — gegen 85 ms für ein
`transcribe` über fünf Sekunden. Bei jedem Segment zu prüfen würde den
Whisper-Anteil fast verdoppeln. Drei Bedingungen gegen Fehlalarme:
mindestens drei Sekunden, mindestens 0,8 Wahrscheinlichkeit, dieselbe
fremde Sprache dreimal hintereinander.

Beide hängen in der Segmentschleife und sind bei ausgeschaltetem
Schalter je ein einzelnes `if`. Was darin schiefgeht, wird gefangen —
ein Protokoll, das den Gottesdienst anhält, wäre schlimmer als keins.

**Nach einem gelungenen Autoupdate wird der Reparaturvorrat
nachgezogen**, solange das WLAN steht. Sonst meldete der Systemcheck
nach jedem Update „Der Vorrat gehört zu Fassung X". Scheitert es,
steht das nur in der Rückmeldung.

**Fehlerberichte gehen von selbst hinaus** (`berichtpost.py`). Vier
Anlässe: der Käfer am Pult, ein Dienst, der nicht sauber beendet
wurde, ein FEHLT beim Start, ein fehlgeschlagenes Update. Sie sammeln
sich lokal (`700`/`600`) und gehen im Fenster über denselben Kanal
hinaus; als gesendet gilt einer erst nach der Bestätigung. Inhalt nur
nach der Erlaubnisliste aus `fehlerbericht.py` — hier kommt nichts
dazu. Eigener Schalter, Vorgabe aus.

Text und kein Anhang, nachgesehen in der ntfy-Dokumentation: über 4096
Bytes macht der Server selbst einen Anhang daraus, und Anhänge
verfallen nach drei Stunden. Ein Bericht vom Donnerstagabend wäre
freitags weg.

**Rückmeldung über ntfy** (`meldung.sh`). Das Thema steht in
`meldung.json` mit `600`, in `.gitignore`, und
`oeffentlich_pruefen.sh` sucht nach solchen Adressen in verfolgten
Dateien. Telegram wäre derselbe Aufwand gewesen; dagegen sprach das
Schadensmaß — ein Bot-Token ist ein Schlüssel, ein ntfy-Thema eine
Adresse zum Mitlesen.

**Echte exFAT- und vfat-Sticks im Prüfstand.** Ohne Wurzelrechte wird
der Abschnitt übersprungen und sagt es. Geprüft wird auf `$EUID` und
nicht auf `id -u`: in `pruefstand/attrappen/` liegt eine `id`-Attrappe,
die eine Wurzel vorspielt — sie hätte den Abschnitt auf einem
Arbeitsrechner losgehen lassen.

`plasma-x11-session` liegt im Reparaturvorrat. Benutzt wird es nicht;
es liegt da, falls der Rechner einmal auf X11 muss, und vor Ort gibt
es keine Leitung, über die es nachkäme.

Neu: **`VERSIONEN.md`**, eine Seite, neueste Fassung oben. Sie wird ab
jetzt mitgepflegt; `AUFSTELLEN.md` führt sie in der Liste „Bei jeder
Fassung mitzupflegen".

### Was offen ist

- Der erste echte Autoupdate-Lauf ist 0.3.3 nach 0.3.4. Die
  Änderungen an `aktualisieren.sh` wirken erst dann.
- Der Bildschirm ist nach einem Neustart unter Wayland nicht
  verlässlich erreichbar. Der Weg ist RustDesk-Terminal und ein
  Tunnel auf Port 8000.

---

## 0.3.2 — Fernwartung ohne jemanden vor Ort

*27.09.2026. Nach dem ersten Einspielen auf dem Gemeinderechner — die
meisten Punkte hier sind Befunde von diesem Tag.*

### Für alle

**Der Rechner ist donnerstags erreichbar.** An einem festen Wochentag,
in einer festen Stunde, verbindet er sich mit dem Gemeinde-WLAN und
trennt sich danach wieder. Er weckt sich dafür selbst und fährt am
Ende von selbst herunter. Dazwischen ist er so offline wie zuvor.
**Per Vorgabe ist das aus** — es gilt vorerst nur für Rostock.

**Wichtig am Rechner:** normal herunterfahren, und **den Schalter
hinten am Netzteil anlassen**. Ohne Strom kann die Uhr ihn nicht
wecken.

Eingeschaltet wird das Fenster mit einem Befehl, nicht von Hand in
einer Datei: `bash wartungsfenster.sh --einschalten "<WLAN-Profil>" Do
18:00 22:00`. Er prüft die Werte, bevor er schreibt, stellt das Profil
auf `autoconnect no` und sagt danach, wie die Lage ist.

**Läuft gerade eine Übersetzung, wartet das Abschalten.** Höchstens
bis 36 Stunden Laufzeit — danach geht er aus, denn ein Rechner, der
seit anderthalb Tagen „live" meldet, hat keinen Gottesdienst, sondern
einen Tonstrom, den niemand abgestellt hat.

**Ein neues Handy ist drei Sekunden schneller im Netz.**

### Für Techniker

**`aktualisieren.sh` prüft jetzt Signaturen.** Bis 0.3.1 stand dort
`git pull --ff-only`: es galt, worauf `origin/main` gerade zeigte —
ohne Signatur, ohne Tag, ohne Prüfung. Über den Stick war das seit
0.2.12 unmöglich, über das Netz blieb es offen. Jetzt gelten dieselben
vier Regeln: nur Tags, nur mit einem Schlüssel aus der **hier**
liegenden `schluessel.erlaubt`, nur über die geprüfte Commit-SHA, nur
aufwärts.

**Und die Units kommen mit.** Der Online-Weg lief nie durch
`aktualisierung.sh`, deshalb liefen nach dem 27.09. alle Units in
alter Fassung, bis jemand `dienst.sh` von Hand aufrief. Jetzt
übergeben beide Wege an dieselbe versionierte Hälfte.

**Die Vorprüfung des Sprachmodells gab es seit 0.3.0 nicht mehr.**
`vorpruefung()` stand noch im Kern, aber niemand rief sie auf — die
Warnung war ersatzlos weg, ohne dass es auffiel. Sie steht jetzt in
`aktualisierung.sh`, wo das **neue** `config.py` schon gilt, und fragt
Ollama über HTTP statt über die Kommandozeile.

Das war der zweite Fehler: `ollama list` braucht `$HOME`. Ein
root-Dienst ohne `User=` bekommt von systemd keines, der Befehl bricht
mit `panic: $HOME is not defined` ab — und weil stderr verworfen wurde,
stand am Pult „das Sprachmodell liegt hier nicht", auf einem Rechner,
auf dem es lag. Dreimal wird jetzt im Abstand von zehn Sekunden
gefragt; ist Ollama dann immer noch stumm, heißt das **unbekannt** und
nicht „fehlt", und das Update läuft weiter.

**Das Bundle vom Stick war für den Dienstbenutzer nicht lesbar.** Der
Kern legte die ganze Nutzlast auf `700 root` — mit der Begründung, in
den Sicherungen stehe das WLAN-Passwort. Das stimmt, nur steht es
nicht im Bundle. `git bundle verify` läuft als Dienstbenutzer und
scheiterte; gemeldet wurde „beschädigt oder passt nicht zu diesem
Rechner". Bundle, Wheels und große Teile liegen jetzt in
`updates/stick/` mit `640`, die Sicherungen bleiben `700`. Unlesbar,
beschädigt und „passt nicht" sind drei verschiedene Meldungen, und
`stderr` von git geht ins Journal.

**Der Prüfstand war bei all dem grün** — er konnte nicht anders: er
lief als ein einziger Benutzer, `als_benutzer` wechselte nie wirklich,
und die Umgebung blieb stehen. Jetzt bildet er den Dienstkontext ab
(`runuser` mit `env -i`) und prüft die Rechte der Nutzlast.

**Fehlalarme, die auf einen gesunden Rechner zeigten:**

- „Diese Dienste laufen mit einer älteren Fassung ihrer Vorlage" —
  dauerhaft, auch nach zweimal `dienst.sh`. Verglichen wurden die
  `ExecStart`-Zeilen, aber nur `@ORDNER@` wurde ersetzt; in
  `devarenu.service.vorlage` steht `--port @PORT@`, in der Unit
  `--port 8000`. Die restlichen Platzhalter gelten jetzt als „hier
  steht irgendetwas" — ein anderer Port ist keine veraltete Vorlage.
- „Der Server nimmt etwas anderes auf als eingestellt" — nach dem
  Anstecken eines zweiten Mikrofons rutschte die UMC von `hw:0,0` auf
  `hw:1,0`. Der Server nahm weiter das richtige Gerät, er kennt
  `_namenskern()`; `pruefen.sh` verglich wortwörtlich. Es benutzt
  jetzt dieselbe Regel aus dem Server statt einer zweiten Kopie.
- `vorrat_bauen.sh --nur-systempakete` schrieb erst die Prüfsummen und
  danach `vorrat.json` — worauf `--pruefen` genau diese Datei
  beanstandete. Der volle Bau macht es richtig und sagt sogar, warum.

**Wayland ist jetzt der Normalfall.** `rechner_einrichten.sh` schrieb
`Session=plasmax11`; eine Sitzung dieses Namens gibt es auf dem
Gemeinderechner gar nicht, der Anmeldemanager nahm wortlos Wayland,
und die Konfiguration behauptete das Gegenteil. Ton, Übersetzung und
RustDesk sind dort unter Wayland gemessen. Gemeldet wird nur noch,
wenn Eingestelltes und Laufendes auseinandergehen.

**Hinweise von `zustand.py` gehen nach stderr.** Eine
Kommandosubstitution fing sie sonst mit ein, und am Pult stand „Ohne
Stimme, laufen als Untertitel: zustand.json umgezogen: 2->3". Die
Meldung war richtig, sie stand nur in der falschen Zeile.

**`no-ping` in der dnsmasq-Konfiguration.** Wirkt erst nach einem
erneuten `sudo bash netz_einrichten.sh` — ein Update schreibt
`/etc/devarenu/dnsmasq.conf` nicht neu.

### Was offen ist

- Ein abgelöster HEAD hält den Updater weiterhin an. Kein Weg im Repo
  hinterlässt ihn so; auf dem Gemeinderechner stand der Ordner
  trotzdem auf `tags/v0.2.11^0`. Das automatische Wiederanhängen kommt
  in 0.3.3.
- Der Hinweis „Ohne Stimme, laufen als Untertitel" fehlt seit 0.3.0
  am Pult. `stimmen_fehlen()` steht noch im Kern, ruft aber niemand
  auf. Kommt in 0.3.3 denselben Weg wie die Modellprüfung.
- Der Rat „mobile Daten ausschalten" ist überholt — mit neuem und
  älterem iPhone und einem Samsung geprüft, kein Anmeldefenster, Ton
  läuft durch. Steht noch in der Anleitung, kommt in 0.3.3 heraus.
- Echte exFAT- und vfat-Sticks im Prüfstand: braucht Wurzelrechte,
  kommt in 0.3.3 als Abschnitt, der sich ohne `sudo` überspringt.

---

## 0.3.1 — Aufnahme nur mit Einwilligung

*26.09.2026.*

### Für alle

**Eine Aufnahme wird jetzt gefragt, nicht vorausgesetzt.** Der
Schalter steht neben „Übersetzung starten". Wer ihn drückt, bekommt
zwei Häkchen: die predigende Person wurde gefragt, und es wird nur
die Predigt aufgenommen. **Beide sind Pflicht** — auch für ein
Programm, das den Server direkt anspricht.

**Was läuft, sieht man.** Roter Punkt, „Aufnahme läuft", die Dauer —
am Pult und auf jedem Handy im Saal.

**Sie hört von selbst auf.** Wenn die Übersetzung angehalten wird
(dann kommen Gebet und Abkündigungen), und bei jedem Neustart. Von
selbst wieder an geht sie nie.

**Sie verschwindet von selbst.** Nach sieben Tagen, einstellbar.
Aufnahmen, die es vor diesem Update schon gab, werden **nicht**
sofort gelöscht: die Frist läuft ab dem Update, und das Pult sagt,
wie viele es sind und wann sie gehen.

**Sie bleibt auf dem Rechner.** Liste und Download gehen nur am
Gemeinde-PC selbst — unabhängig davon, ob ein Pult-Passwort gesetzt
ist. Aus dem Saal steht dort: „Nur am Gemeinde-PC abrufbar."

**Die Meldefunktion ist gegen Unfug gesichert.** Höchstens eine
Meldung alle fünf Sekunden je Gerät, 200 Zeichen, zwanzig am Tag. Ein
normaler Zuhörer merkt davon nichts. Wer abgewiesen wird, bekommt
einen freundlichen Satz in seiner Sprache statt stiller Ablehnung.

**Reißt die Verbindung ab, bleibt die Seite ruhig.** Statt „keine
Verbindung" steht dort jetzt „Warte auf das Devarenu-WLAN … die
Übersetzung geht gleich weiter" — und sie holt sie sich selbst
zurück, ohne dass jemand neu lädt.

### Für Techniker

**Aufnahme.** `aufnahme.py` — Einwilligung, Frist, Rechte (700/600),
Platzgrenze. Neben jeder Aufnahme liegt ein Vermerk mit dem Zeitpunkt
der Bestätigung, **ohne Namen**: er belegt, dass gefragt wurde, nicht
wer geantwortet hat. Stündlicher Aufräumlauf, Stopp bei unter 2 GB
freiem Platz mit Meldung ins Pult.

**Drossel.** `drossel.py`, je Schreibweg aus dem Saal eine eigene.
Dazu höchstens acht offene Datenströme je Gerät — ein Skript, das
Verbindungen aufmacht, bis die Dateizeiger ausgehen, legte sonst den
ganzen Gottesdienst still.

**Kein Service Worker.** Geprüft und verworfen: Browser erlauben ihn
nur in einem *secure context*, und `http://10.0.0.1` ist keiner. Das
Wiederverbinden läuft im normalen Skript, mit wachsendem Abstand und
einem Zufallsanteil — ohne den klopfen vierzig Handys gleichzeitig an,
sobald der Zugangspunkt zurückkommt.

**Selbsttest.** Er wurde in fünf von acht Läufen gelb. Nachgemessen
lag es **nicht** am Prüfsatz, sondern an der Sprachausgabe: gesprochen
wurde mit dem Tempo-Rückfall 1,15 statt dem gemessenen 1,00 dieser
Stimme, und Pipers Dauervorhersage ist stochastisch. Beides behoben,
acht Läufe hintereinander grün.

**`start.sh`** prüft jetzt die Glossardatei aus `config.GLOSSAR_CSV`
statt eines festen Namens — ein fehlendes Glossar fällt damit beim
Start auf und nicht mitten im Gottesdienst.

**FAT32 geht jetzt auch mit großen Teilen.** `teile.py` stückelt alles
über 3,5 GB, der Zielrechner setzt zusammen und prüft gegen die
`sha256` aus `teile.json` — **bevor** etwas ersetzt wird. Fehlendes
Stück und verfälschtes Stück werden getrennt gemeldet: das eine ist
ein abgebrochener Kopiervorgang, das andere ein defekter Stick.

**Das Helferblatt sagt nur noch einen Weg:** die vier Dateien direkt
oben auf den Stick, in keinen Ordner. Kerne vor 0.2.13 suchen
`upd-dev.txt` nur ganz oben, und der Gemeinderechner läuft auf 0.2.11
— liegen die Dateien in einem Ordner, tut er gar nichts, ohne Meldung.
Genau daran ist ein Versuch schon gescheitert.

**Der Systemcheck sieht nach, welche Sitzung wirklich läuft.** Bisher
las er nur, was in der automatischen Anmeldung *eingestellt* ist. Auf
dem Gemeinderechner stand dort `plasmax11` und es lief trotzdem
Wayland — gemeldet wurde nichts. Jetzt fragt er `loginctl`, und wenn
beides auseinandergeht, sagt er es und nennt die wahrscheinliche
Ursache: eine Sitzung `plasmax11` gibt es auf dem Rechner gar nicht,
also nimmt der Anmeldemanager wortlos die, die er hat. Am
Anmeldeverfahren ändert sich **nichts** — es wird nur geprüft und
gemeldet.

### Was offen ist

- Der Stick-Weg auf dem echten Gemeinde-PC. **Das ist der Grund für
  0.3.x** — siehe `FAHRPLAN-1.0.md`, wo alles steht, was vor einer
  zweiten Gemeinde erfüllt sein muss.
- Das Glossar mit Polnisch ist nicht aktiv geschaltet.
- `fr_FR-upmc-medium` ist ohne gemessenes Tempo. Der Wert 0,447 ist
  nicht plausibel; die Stimme hat zwei Sprecher, und
  `laengenfaktor.py` kennt `--speaker` noch nicht. Die Schritte zum
  Nachmessen stehen in `AUFSTELLEN.md`.
- Das Pult ist per Vorgabe offen im Saalnetz. Das Passwort ist
  freiwillig und bleibt es.

---

## 0.3.0 — der erste Meilenstein

*25.09.2026. Fasst alles zusammen, was seit 0.2.0 entstanden ist.*

> Das Tag **v0.2.15** steht im Repo und ist derselbe Stand, nur eine
> Zahl davor. Es bleibt stehen, weil ein veroeffentlichtes Tag nicht
> zurueckgenommen wird — wer es schon geholt hat, behielte sonst etwas,
> das es angeblich nie gab. **Gueltig ist 0.3.0.**

> **Noch nicht erprobt.** Der Weg über den USB-Stick ist auf dem
> Gemeinde-PC **noch nicht gelaufen** — geprüft ist er nur am
> Prüfstand, mit Attrappen. Die Fassungen 0.3.x sind die Erprobung in
> **einer** Gemeinde. **An weitere Gemeinden erst mit Version 1.0.**

### Für alle

**Der Rechner sagt, wenn ihm etwas fehlt.** Früher musste man wissen,
wonach man sucht. Jetzt steht am Pult, was nicht stimmt — und daneben,
was dagegen zu tun ist. Auf Deutsch und auf Englisch.

**Fehler melden geht mit dem Handy.** Oben rechts am Pult sitzt ein
kleiner Käfer. Ein Tippen darauf, zwei Quadratmuster erscheinen: das
eine öffnet eine fertige E-Mail, das andere lädt einen Bericht aufs
Handy, der sich anhängen lässt. Im Gemeindehaus gibt es kein Internet;
die Mail bleibt im Postausgang und geht von selbst raus, sobald das
Handy wieder Empfang hat.

**Der Bericht verrät nichts.** Er enthält nur technische Angaben —
Fassung, Rechner, was der Selbsttest sagt. Keine Predigtsätze, keine
Übersetzungen, keine Zuschriften aus dem Saal, keine Namen, kein
WLAN-Passwort. Das ist keine Absichtserklärung, sondern geprüft: ein
Testlauf füttert das Programm mit erfundenen Daten und sucht sie im
Bericht.

**Was gesprochen wird, bleibt nicht liegen.** Bis 0.2.13 schrieb der
Rechner bei jedem Abschnitt ein Stück des gesprochenen Satzes in sein
Protokoll. Über Monate sammelten sich dort Predigtinhalte. Das ist
abgestellt; im Protokoll steht nur noch, wie lang ein Satz war.

**Jede Stimme hat ihr eigenes Tempo.** Vorher liefen alle Sprachen
gleich schnell — mal hetzte die Übersetzung, mal schleppte sie.

**Updates kommen per USB-Stick.** Stick einstecken, am Pult auf „Jetzt
einspielen" tippen, fertig. Kein Passwort, kein Fachwissen. Geht dabei
etwas schief, holt der Rechner sich selbst auf den alten Stand zurück
und läuft weiter.

**Eine Anleitung zum Ausdrucken.** Für die Zuhörer in vier Sprachen
(Deutsch, Englisch, Russisch, Farsi), für das Pult, für die Technik.
Und ein **einzelnes Blatt** für den, der die Umstellung vor Ort macht:
ohne Fachbegriffe, eine Seite.

### Für Techniker

**Netz.** Der Rechner ist Router im Saalnetz: dnsmasq unter
`/etc/devarenu/dnsmasq.conf` mit eigenem systemd-Zusatz statt
`/etc/dnsmasq.d/` — unter Arch sind dort alle `conf-dir`-Zeilen ab Werk
auskommentiert, eine Datei darin wird schlicht nie gelesen.
`local=/#/` und `host-record=` statt `address=/…/`, sonst antwortet
dnsmasq mit REFUSED. Die Freigaben hängen an der Kabelkarte;
`ip_forward` bleibt aus, zwischen WLAN und Saal wird nie geleitet.

**Updater, zweigeteilt.** Ein Kern, der auf dem Rechner bleibt (Trust
und Rückweg), und die Update-Logik, die aus dem geprüften Tag kommt.
Ausgepackt wird über `git archive` auf die **Objekt-SHA**, nicht über
den Tagnamen — ein Tag lässt sich überschatten. Die Signatur wird gegen
die **installierte** Schlüsselliste geprüft, nie gegen eine vom Stick.
Ab 0.3.0 zieht ein Update auch die Units und die udev-Regel nach.

**venv.** Zwei Umgebungen, `.venv-a` und `.venv-b`, umgeschaltet über
eine Verknüpfung. venvs sind nicht verschiebbar — die Pfade stehen
eingebrannt darin —, deshalb bleibt der alte Name als Verknüpfung
stehen.

**Einstellungen überleben jede Fassung.** `zustand.json` trägt eine
Formatnummer und wird beim Start hochgezogen. Vor jedem Umzug eine
Sicherung; eine Datei aus der Zukunft wird nur gelesen, nie
überschrieben. Unbekannte Schlüssel bleiben erhalten.

**Protokollstufen.** systemd legt stdout *und* stderr auf Stufe 6 —
`journalctl -p warning` lieferte von diesem Dienst also gar nichts.
Warnungen tragen jetzt `<4>`, Fehler `<3>`, aber nur, wenn die Ausgabe
wirklich ins Journal geht: `JOURNAL_STREAM` wird vererbt, ein Terminal
unter systemd trägt es mit.

**Prüfstand.** 73 Zusicherungen ohne Wurzelrechte, ohne systemd, ohne
Modell. Darunter der echte Kern von 0.2.11, der sich beim Update selbst
überschreibt; ein Stick, der seine eigenen Schlüssel mitbringt und
abgelehnt wird; und der ganze Weg vom ZIP über Windows bis zur
Vormerkung am Pult.

### Was offen ist

- Der Stick-Weg auf dem echten Gemeinde-PC. **Das ist der Grund für
  0.3.x.**
- Das Netz steht dort noch nach dem alten Aufbau. Es läuft; die
  Umstellung bleibt Handarbeit beim nächsten Wartungsbesuch.
- Der Selbsttest hört seinen eigenen Prüfsatz nicht zuverlässig
  („mangeln" wird zu „manneln") und wird deshalb ohne Grund gelb. Der
  Satz gehört ersetzt.
