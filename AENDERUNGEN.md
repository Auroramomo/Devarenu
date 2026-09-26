# Was sich geändert hat

Die neueste Fassung steht oben. Ältere Einträge bleiben stehen — wer
einen Rechner vor sich hat, der seit einem Jahr läuft, soll nachlesen
können, was seither dazugekommen ist.

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
