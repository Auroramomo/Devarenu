# Was sich geändert hat

Die neueste Fassung steht oben. Ältere Einträge bleiben stehen — wer
einen Rechner vor sich hat, der seit einem Jahr läuft, soll nachlesen
können, was seither dazugekommen ist.

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
