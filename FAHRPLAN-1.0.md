# Fahrplan zur 1.0

**Wann darf Devarenu an eine zweite Gemeinde?**

Heute läuft es in **einer** Gemeinde und wird dort erprobt. Die
Fassungen 0.3.x sind diese Erprobung. Dieses Dokument sagt, was
erfüllt sein muss, bevor jemand anderes es aufstellt — und was heute
davon fehlt.

Die Antwort auf „ist es fertig?" lautet bis dahin: nein, und hier
steht warum.

---

## Wie dieses Dokument zu lesen ist

Je Punkt drei Dinge: **Stand heute**, **was fehlt**, **wie man es
prüft**. Der dritte ist der wichtigste. Ein Punkt ohne Prüfweg ist
eine Meinung, kein Kriterium — und lässt sich nicht abhaken.

Was hier als erledigt gilt, muss **auf echter Hardware** erledigt
sein. Ein Prüfstand mit Attrappen belegt, dass der Code tut, was
gemeint war; er belegt nicht, dass es in einem Saal funktioniert.

---

## 1. Der Stick-Weg auf echter Hardware

**Stand:** Nicht gelaufen. Der zweigeteilte Kern ist seit 0.2.13 im
Programm und im Prüfstand mit 73 Zusicherungen belegt — darunter der
echte alte Kern aus `git show v0.2.11:stick_update.sh`, der sich beim
Update selbst überschreibt. Alles mit Attrappen für `systemctl`,
`sudo`, `runuser`, `curl` und `udevadm`.

**Was fehlt:** Ein Update per Stick auf dem Gemeinderechner, von
jemandem eingesteckt, der nicht daneben steht und mitliest. Bisher hat
der Rechner **kein einziges** Stick-Update erlebt.

**Wie man es prüft:** `AUFSTELLEN.md`, Abschnitt „Von 0.2.11 direkt
auf 0.3.0". Danach: läuft der Dienst, meldet das Pult die neue
Fassung, liegt die Sicherung unter `/var/lib/devarenu/updates/`, sind
die Units neu geschrieben. Und der Gegentest: ein Update, das
absichtlich scheitert, muss den alten Stand zurückholen.

> **Das ist der Punkt, an dem alles andere hängt.** Ohne einen
> erprobten Weg, Fehler zu beheben, darf keine zweite Gemeinde ein
> Gerät bekommen. Wer dort etwas kaputtmacht, kann es nicht reparieren.

---

## 2. iPhone im Saalnetz

**Stand:** Bekannt und unbehoben. Neuere iPhones prüfen beim ersten
Verbinden auf ein Internet, das dieses WLAN nicht hat, und brauchen
dafür lange — die QR-Seite sagt deshalb „bis zu einer Minute warten,
nicht neu verbinden". Das ist eine Umschreibung des Problems, keine
Lösung.

**Was fehlt:** Eine Messung. Wie lange dauert es wirklich, auf welchen
iOS-Fassungen, und hilft ein Captive-Portal-Antwortverhalten? Der
Router beantwortet die Prüfadressen bereits (`netzpruefung.py`) —
ob das ausreicht, ist nicht gemessen.

**Wie man es prüft:** Drei iPhones verschiedener Baujahre, je fünf
Verbindungen, Zeit bis zur ersten hörbaren Übersetzung. Dazu dasselbe
mit abgeschalteten mobilen Daten. Ergebnis in eine Tabelle; darunter
die Entscheidung: gelöst, oder erklärt und dokumentiert.

---

## 3. Betrieb ohne Monitor

**Stand:** Teilweise. `rechner_einrichten.sh` setzt automatische
Anmeldung, kein Standby, keine Bildschirmsperre. Der Systemcheck
meldet, wenn eines davon fehlt. Ob der Rechner nach einem Stromausfall
ohne Tastatur und Bildschirm allein hochkommt und übersetzt, ist
**nicht geprüft**.

**Was fehlt:** Der Kaltstart-Versuch. Stecker ziehen, Stecker rein,
nichts anfassen.

**Wie man es prüft:** Dreimal hintereinander. Jedes Mal muss die
Zuhörerseite binnen zwei Minuten antworten und der Ton laufen. Ein
Durchlauf zusätzlich **ohne angeschlossenen Monitor** — manche
Grafiktreiber verhalten sich ohne erkanntes Display anders, und das
fällt sonst erst in der Gemeinde auf.

---

## 4. Erstinstallation durch ein Systemhaus

**Stand:** Es gibt `INSTALLIEREN.sh`, `einrichten.sh`, `dienst.sh`,
`netz_einrichten.sh`, `vorrat_bauen.sh` und `bootstrap.sh`. Es gibt
**keine** Anleitung, die ein fremder Techniker von oben nach unten
abarbeiten kann. `AUFSTELLEN.md` ist gewachsen und setzt voraus, dass
man die Geschichte kennt.

**Was fehlt:** Ein Dokument für jemanden, der Devarenu noch nie
gesehen hat: Hardware auspacken bis erster Gottesdienst. Mit
Abnahmeliste am Ende.

**Wie man es prüft:** Jemand, der nicht am Projekt beteiligt ist,
arbeitet es ab — ohne Rückfragen. Jede Rückfrage ist eine Lücke im
Dokument und gehört hineingeschrieben, nicht beantwortet.

---

## 5. Die Anleitung

**Stand:** Sechs PDF-Dateien, reproduzierbar gebaut: die ganze
Anleitung (Teile A bis C), Teil A einzeln in vier Sprachen, und ein
Blatt für die Umstellung. Sie tragen „Vorversion".

**Was fehlt:** Teil C (Technik) ist mit der Zeit gewachsen und
erklärt Dinge in der Reihenfolge, in der sie entstanden sind, nicht in
der, in der man sie braucht. Und die Zuhörerseite gibt es in vier von
einundzwanzig Sprachen.

**Wie man es prüft:** Teil A einem Zuhörer geben, der Devarenu nicht
kennt, und zusehen. Teil C dem Systemhaus aus Punkt 4.

---

## 6. Geprüfte Sprachen

**Stand:** Vier von einundzwanzig sind von Muttersprachlern
gegengelesen: Deutsch, Englisch, Russisch, Persisch. Polnisch ist
vorbereitet und beim Prüfer. Alles andere läuft maschinell und ist am
Pult als *experimentell* gekennzeichnet.

**Was fehlt:** Kein fester Zielwert — eine Gemeinde braucht die
Sprachen, die sie braucht. Für 1.0 gilt: **jede Sprache, die eine
aufnehmende Gemeinde einschaltet, muss geprüft sein**, oder der
Hinweis am Pult muss stehen bleiben.

Offen ist außerdem, dass eine geprüfte Sprache ihr Glossar auch
**aktiv** bekommt (`GLOSSAR_CSV`) — siehe den Merkposten in
`AUFSTELLEN.md`. Bis dahin läuft sie geprüft, aber ohne
Fachwortverzeichnis, und das ist der schlechteste Zustand.

**Wie man es prüft:** `werkzeuge/sprachpaket.py --bauen <sp>`, Paket
an einen Muttersprachler, `--einlesen`. Der Vergleichslauf über die
Testsätze der schon aktiven Sprachen gehört dazu.

---

## 7. Datenschutz

**Stand:** Deutlich besser als in 0.2.

| | |
|---|---|
| Mitschrift im Protokoll | aus, Schalter am Pult, Systemcheck meldet ihn |
| Aufnahme | nur mit zwei bestätigten Häkchen, sichtbar, Frist sieben Tage, nur am Rechner abrufbar |
| Fehlerbericht | Erlaubnisliste plus Riegel, mit erfundenen Daten geprüft |
| Pult | freiwilliges Passwort, Vorgabe offen |

**Was fehlt:**

- Ein **Verzeichnis der Verarbeitungstätigkeiten** und eine kurze
  Auskunft für die Gemeinde: was entsteht, wo liegt es, wie lange.
  Ohne das kann eine Gemeindeleitung nicht zustimmen.
- Das Pult ist per Vorgabe **offen im Saalnetz**. Für eine fremde
  Gemeinde ist das eine bewusste Entscheidung, die jemand treffen
  muss — nicht eine, die sie erbt.
- Die **Aufbewahrung der Aufnahmen** ist eingestellt, aber nicht
  vereinbart. Sieben Tage sind eine Vorgabe, kein Beschluss.

**Wie man es prüft:** Das Verzeichnis existiert und ist von der
Gemeindeleitung abgenommen. Kein Punkt daraus lässt sich im laufenden
System widerlegen.

---

## 8. Hardware

**Stand:** Ein Rechner, CachyOS, RTX 5080. Gemessen: 2,0 Sekunden
Verzögerung, kein Nachlaufen über 32 Minuten. Es gibt **keine**
Empfehlung, was eine andere Gemeinde kaufen soll.

**Was fehlt:** Eine Untergrenze. Läuft es auf einer kleineren Karte?
Auf einer ohne CUDA gar nicht — der Selbsttest sagt das bereits
deutlich, aber niemand weiß, wo die Grenze liegt.

**Wie man es prüft:** Dieselbe Predigt auf zwei, drei Karten
verschiedener Klasse. Gemessen wird nicht die Geschwindigkeit, sondern
ob der Rückstand über eine dreiviertel Stunde **wächst**. Wächst er,
ist die Karte zu klein — auch wenn die ersten fünf Minuten gut
aussehen.

---

## Was NICHT drinsteht

Keine Funktionswünsche. 1.0 heißt nicht „kann mehr", sondern
**„lässt sich jemand anderem in die Hand geben"**. Alles, was diese
Liste verlängert, ohne einen der acht Punkte zu schließen, gehört in
eine spätere Fassung.

---

## Reihenfolge

1 vor allem anderen. Dann 3 und 4 — sie hängen zusammen, denn wer
installiert, muss auch den Kaltstart sehen. Dann 2. Dann 7, weil es
eine Entscheidung der Gemeinde braucht und Zeit kostet, die nicht
technisch ist. 5, 6 und 8 laufen nebenher.
