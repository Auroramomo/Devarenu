# Was sich geändert hat

Die neueste Fassung steht oben. Ältere Einträge bleiben stehen — wer
einen Rechner vor sich hat, der seit einem Jahr läuft, soll nachlesen
können, was seither dazugekommen ist.

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
