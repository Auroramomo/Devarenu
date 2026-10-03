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

### Was beim Kaltstart passieren soll

Der Reihe nach, und jede Zeile ist eine Stelle, an der es hängen
bleiben kann:

1. BIOS startet. **ErP aus**, sonst versorgt es die Uhr im Standby
   nicht — dann weckt der Wartungswecker nicht.
2. Der Anmeldemanager meldet den Dienstbenutzer ohne Passwort an.
   Ohne angemeldete Sitzung gibt es keinen PulseAudio-Server und
   damit **keinen Ton**. Genau daran hing der Rollout monatelang.
3. `devarenu.service` startet, lädt Whisper und die Stimmen. Das
   dauert; der Dienst antwortet erst danach.
4. `dnsmasq` gibt Adressen aus. Mit `bind-dynamic` wartet es auf die
   Netzwerkkarte, statt abzubrechen.
5. `devarenu-update.timer` sieht nach, ob ein Stick-Update vorliegt.
6. `devarenu-fenster.timer` und der Wecker, falls ein Fenster
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

**Nicht geprüft** ist der Fall, um den es geht: Stecker ziehen,
warten, wieder einstecken, und niemand fasst das Gerät an. Dazu
gehört ein Stromausfall mitten im Gottesdienst, mit Handys, die noch
verbunden sind.

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

**Seit 0.4.0 steht sie als eigenes Dokument:**
[ERSTINSTALLATION.md](ERSTINSTALLATION.md) — zehn Abschnitte, nach
jedem eine Kontrolle mit Befehl und erwarteter Ausgabe, dazu eine
Tabelle "was die Gemeinde vorher sagen muss" und eine Störungstabelle
am Ende. Die Liste unten ist die Kurzfassung davon.

Was fehlt, ist der Durchlauf: **niemand hat sie abgearbeitet, der das
Projekt nicht kennt.** Bis dahin ist sie eine Behauptung.

**Wie man es prüft:** Jemand, der nicht am Projekt beteiligt ist,
arbeitet sie ab — ohne Rückfragen. Jede Rückfrage ist eine Lücke im
Dokument und gehört hineingeschrieben, nicht beantwortet.

### Von der Kiste bis zum ersten Gottesdienst

Vorausgesetzt: CachyOS oder Arch ist installiert, ein Benutzer
angelegt, das Gerät hängt für die Einrichtung an einer Leitung.
Alles in `fish`, einzeln, mit Kontrolle darunter.

**1. Holen und einrichten**

```fish
git clone https://github.com/Auroramomo/Devarenu.git ~/Devarenu
cd ~/Devarenu
```
```fish
bash INSTALLIEREN.sh
```
```fish
.venv/bin/python selbsttest.py
```
Der Selbsttest muss grün durchlaufen. Bleibt er bei Ollama oder dem
Sprachmodell stehen, fehlt beides noch — er sagt, womit.

**2. Ton**

Mikrofon anschließen, dann am Pult (`bash start.sh`, dann
`http://localhost:8000/pult`) unter *Tonquelle* das Gerät auswählen
und einmal *Sprache prüfen* drücken. Es muss der gesprochene Satz
erscheinen, nicht nur ein Pegel.

```fish
bash pruefen.sh
```

**3. Als Dienst**

```fish
sudo bash rechner_einrichten.sh
```
```fish
sudo bash dienst.sh
```
```fish
systemctl is-active devarenu; systemctl is-enabled devarenu
```
Beides muss `active` und `enabled` sagen.

**4. Das Saalnetz**

Kabel vom Zugangspunkt in die zweite Netzwerkkarte. Dann den eigenen
Rechnernamen in `netz.json` eintragen lassen — `netz_einrichten.sh`
verlangt das, damit es nicht versehentlich auf einem Arbeitsrechner
läuft:

```fish
sudo bash netz_einrichten.sh --trocken
```
```fish
sudo bash netz_einrichten.sh
```
```fish
systemctl is-active dnsmasq; ip -br addr show
```
```fish
sudo bash firewall.sh --schnittstelle <karte>
```

**5. Probe mit einem Handy**

QR-Seite am Beamer (`http://<adresse>/qr`), mit einem Handy beide
Codes scannen, Sprache wählen, zuhören. Es muss Ton kommen.

```fish
sysctl net.ipv4.ip_forward
```
Muss `0` sein. Ist es `1`, leitet der Rechner ins Hausnetz weiter —
das darf nicht sein.

**6. Der Reparaturvorrat**

Solange noch eine Leitung da ist:

```fish
sudo bash vorrat_bauen.sh
```
```fish
bash vorrat_bauen.sh --pruefen
```

**7. Abnahme**

```fish
bash pruefen.sh
```
```fish
.venv/bin/python selbsttest.py
```
```fish
bash wartungsfenster.sh --zeigen
```

Kein **FEHLT** darf stehenbleiben. Hinweise dürfen — sie stehen
unter Einrichtung → Wartung und halten den Gottesdienst nicht auf.

Zuletzt: Leitung abziehen, Rechner neu starten, und Schritt 5 noch
einmal. **Ohne Internet muss alles genauso laufen.**

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

Seit 0.3.6 steht das **Verzeichnis der Verarbeitungstätigkeiten** in
[DATENSCHUTZ.md](DATENSCHUTZ.md) — elf Verarbeitungen, je mit Zweck,
Daten, Empfänger, Speicherdauer, Schalter und Vorgabe. Darüber ein
Textbaustein, den eine Gemeinde übernehmen kann.

Ebenfalls seit 0.3.6 **speichert das Gerät weniger**: die
DHCP-Mietliste liegt im Arbeitsspeicher statt auf der Platte, die
Aushandlungen gehen nicht mehr ins Journal (`quiet-dhcp`), und wo im
Journal eine Zuhöreradresse stand, steht jetzt eine gesalzene
Kennung.

**Was fehlt:**

- Die Fragen unter „Was offen ist" in DATENSCHUTZ.md — allen voran,
  **ob kirchliches Datenschutzrecht gilt** und welche Stelle
  zuständig ist. Das hängt an der Rechtsform, nicht am Programm, und
  lässt sich hier nicht beantworten.
- Das Verzeichnis ist geschrieben, aber **von keiner Gemeindeleitung
  abgenommen**.
- Das Pult ist per Vorgabe **offen im Saalnetz**. Für eine fremde
  Gemeinde ist das eine bewusste Entscheidung, die jemand treffen
  muss — nicht eine, die sie erbt.
- Die **Aufbewahrung der Aufnahmen** ist eingestellt, aber nicht
  vereinbart. Sieben Tage sind eine Vorgabe, kein Beschluss.

**Wie man es prüft:** Das Verzeichnis ist von der Gemeindeleitung
abgenommen. Kein Punkt daraus lässt sich im laufenden System
widerlegen — nachzusehen mit

```fish
sudo ls -l /run/devarenu/
journalctl -u dnsmasq --since today | grep -ci dhcp
```

Die Mietliste liegt unter `/run`, und das `grep` findet nichts.

---

## 8. Hardware

**Stand:** Ein Rechner, CachyOS, RTX 5080. Es gibt **keine**
Empfehlung, was eine andere Gemeinde kaufen soll.

### Was gemessen ist

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

### Was unbekannt ist

- **Auf welcher Karte diese Läufe entstanden sind**, steht in keiner
  `lauf.json`. Alle stammen von Entwicklungsrechnern, vermutlich
  derselben Klasse. Das ist eine Lücke in der Messung selbst.
- **Ob der Rückstand über eine dreiviertel Stunde wächst.** Die Läufe
  hier sind fünf Minuten lang und liefen im Dateibetrieb, also
  schneller als Echtzeit. Fünf Minuten ohne Drift sagen nichts über
  fünfundvierzig.
- **Wo die Untergrenze liegt.** Eine kleinere Karte wurde nie
  gemessen. Die 5060 Ti in Rostock läuft, aber es liegt keine
  Messung von ihr vor — nur die Beobachtung, dass es geht.
- **Ohne CUDA** läuft es gar nicht; das sagt der Selbsttest deutlich.

**Was fehlt:** Eine Untergrenze, die auf einer Messung beruht und
nicht auf dem, was zufällig danebenstand.

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
