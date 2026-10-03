# Fahrplan zur 1.0

**Wann darf Devarenu an eine zweite Gemeinde?**

Heute läuft es in **einer** Gemeinde und wird dort erprobt. Die
Fassungen 0.3.x und 0.4.x sind diese Erprobung. Dieses Dokument sagt,
was erfüllt sein muss, bevor jemand anderes es aufstellt — und was
heute davon fehlt.

Die Antwort auf „ist es fertig?" lautet bis dahin: nein, und hier
steht warum.

*Stand: 0.4.0, 03.10.2026.*

---

## Wie dieses Dokument zu lesen ist

Drei Stufen, und die Einteilung ist der Kern:

| | |
|---|---|
| **Blocker** | Ohne das darf kein Gerät an eine zweite Gemeinde. Sieben Punkte. |
| **Sollte** | Gehört getan, hält aber nichts auf. Sechs Punkte. |
| **Nicht mehr auf der Liste** | Erledigt oder als kein Hindernis erkannt. |

Je Punkt drei Dinge: **Stand heute**, **was fehlt**, **wie man es
prüft**. Der dritte ist der wichtigste. Ein Punkt ohne Prüfweg ist
eine Meinung, kein Kriterium — und lässt sich nicht abhaken.

Was hier als erledigt gilt, muss **auf echter Hardware** erledigt
sein. Ein Prüfstand mit Attrappen belegt, dass der Code tut, was
gemeint war; er belegt nicht, dass es in einem Saal funktioniert.

**Die Blocker hängen zusammen, und zwar in dieser Reihenfolge:** erst
die Testumgebung (B2), dann ein Update-Weg, der sich darin und im Feld
bewährt (B1), dann der Knopf (B4), der ihn bedienbar macht. B3, B5,
B6 und B7 laufen daneben; B7 kostet Zeit, die nicht technisch ist, und
gehört darum früh angestoßen.

---

# Blocker

## B1. Der Update-Weg, mehrfach und ohne Eingriff

**Stand:** Der Online-Weg hat im Feld **mehrfach getragen**, aber
immer von Hand: 0.3.4 → 0.3.7 und 0.3.7 → 0.3.8, jeweils mit
`bash aktualisieren.sh` auf dem Gemeinderechner. Dreimal ist er
vorher gescheitert, und jedes Mal an einer Stelle, die im neuen Stand
längst behoben war — 0.3.1 (Units nie geschrieben), 0.3.3 (`[ -f … ]`
ohne `sudo` auf einem `root:root 700`-Ordner), 0.3.7 (falscher
Update-Stand am Pult).

Der **zweigeteilte Kern** (stabiler Kern plus versionierte Hälfte) ist
seit 0.2.13 im Programm und mit über 100 Zusicherungen belegt,
darunter der echte alte Kern aus `git show v0.2.11:stick_update.sh`,
der sich beim Update selbst überschreibt. Der **Rückweg** ist im
Prüfstand belegt: scheitert die versionierte Hälfte mittendrin, kommt
alles zurück.

**Was fehlt:**

- **Das Autoupdate im Fenster, im Feld.** Dass der Rechner sich
  donnerstags zwischen 18 und 22 Uhr von selbst holt, was da ist, ist
  im Prüfstand belegt und auf dem Gemeinderechner **nie beobachtet**.
  Dazu gehört der Wecker: `cat /sys/class/rtc/rtc0/wakealarm` nach
  einem echten Herunterfahren.
- **Der Rückweg im Feld.** Ein absichtlich scheiterndes Update, das
  den alten Stand zurückholt — bisher nur mit Attrappen.
- **Der Prüfstand für den Weg auf die jeweils neue Fassung.** Er ist
  angefangen (von `v0.3.7` und `v0.3.8` aus, über `git worktree`, mit
  dem *alten* `aktualisieren.sh` gegen den echten neuen Baum) und war
  bei 0.4.0 noch rot: der Gesundheitscheck fragt den laufenden Dienst
  über HTTP und trifft dabei den echten statt den der Sandbox. Es
  fehlt eine Attrappe dafür.

**Wie man es prüft:** Drei Fassungen hintereinander, ohne dass jemand
eingreift. Danach jeweils: läuft der Dienst, meldet das Pult die neue
Fassung, liegt die Sicherung unter `/var/lib/devarenu/updates/`, sind
die Units neu geschrieben, ist `zustand.json` unangetastet. Und der
Gegentest mit einem Update, das scheitern muss.

> **Daran hängt alles andere.** Ohne einen erprobten Weg, Fehler zu
> beheben, darf keine zweite Gemeinde ein Gerät bekommen. Wer dort
> etwas kaputtmacht, kann es nicht reparieren.

---

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

## B4. Der Knopf „Jetzt aktualisieren"

**Stand:** Seit 0.4.0 **gebaut und im Prüfstand**, auf dem
Gemeinderechner **nie gedrückt** — er kommt ja erst mit dieser
Fassung dorthin.

Am Pult unter *Einrichtung*, nur am Gemeinde-PC selbst
(`nur_am_rechner`), nie während einer laufenden Übersetzung, und ein
zweiter Klick startet nichts Neues. Der Weg zu root ist eng: der
Dienst legt eine Datei in seinem eigenen Ordner an
(`update/online-jetzt`), und `devarenu-onlineupdate.timer` sieht als
root alle 30 Sekunden danach — kein `sudo`, kein Parameter, den der
Dienst unterschieben könnte.

**Was fehlt:** Ein Druck im Feld, einmal mit dem eingetragenen
Wartungs-WLAN und einmal mit einem Handy-Hotspot. Dazu der Fall, den
nur echte Hardware hergibt: **Stromausfall mitten im Update**. Der
nächste Start muss das erkennen und als *abgebrochen* melden; im
Prüfstand tut er es.

**Wie man es prüft:** Nach dem Einspielen von 0.4.0 einmal
`sudo bash dienst.sh` (die Unit ist neu), dann

```fish
systemctl is-enabled devarenu-onlineupdate.timer
```

und danach am Pult drücken. Erledigt, wenn zwei Fassungen so
eingespielt wurden, ohne dass jemand ein Terminal geöffnet hat.

---

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

## B6. Die Lizenzen der Bausteine

**Stand:** Seit 0.4.0 **erhoben** — und damit ist aus einer offenen
Frage ein konkretes Problem geworden. `werkzeuge/stimmlizenzen.py`
liest die Modellkarte jeder der 21 ausgelieferten Piper-Stimmen; die
Tabelle steht in [LIZENZEN.md](LIZENZEN.md), dazu Whisper, Gemma,
Ollama und `piper-tts`.

**Zwei Befunde betreffen Sprachen, die in Rostock laufen:**

| Stimme | Lizenz | Lage |
|---|---|---|
| `en_US-lessac-medium` | Blizzard 2013 (Lessac / Voice Factory) | „exclusively for **Research Purposes** only", nicht übertragbar, ohne Unterlizenzierung |
| `ru_RU-irina-medium` | „Unknown" (RHVoice) | **keine Lizenz genannt**; das Repo führt keine Lizenzdatei |

Dazu fünf nicht eingeschaltete Stimmen mit „See URL" oder
`CC-BY-NC-SA`. Und **Gemma** ist keine freie Lizenz, sondern
Nutzungsbedingungen mit einer *Prohibited Use Policy* — Devarenu
liefert das Modell nicht mit, jede Gemeinde nimmt es über Ollama
selbst entgegen.

**Was fehlt:** Eine Entscheidung zu `en` und `ru`. Drei Wege, und
einer muss gewählt werden:

1. Die Beschränkung gilt nur für den Datensatz, nicht für die
   trainierten Gewichte — dann gehört die Begründung aufgeschrieben.
2. Eine andere Stimme auf freien Daten suchen und wechseln.
3. Beim Rechteinhaber fragen.

**Wie man es prüft:** In `LIZENZEN.md` steht zu jeder
ausgelieferten Stimme eine Lizenz **und** ein Satz, warum die
Weitergabe in Ordnung ist. Kein „unklar" mehr bei einer Sprache, die
irgendwo eingeschaltet ist.

> **Entfernt ist nichts.** Die Tabelle ist die Grundlage für eine
> Entscheidung, nicht die Entscheidung.

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

Das **Verzeichnis der Verarbeitungstätigkeiten** steht seit 0.3.6 in
[DATENSCHUTZ.md](DATENSCHUTZ.md) — elf Verarbeitungen, je mit Zweck,
Daten, Empfänger, Speicherdauer, Schalter und Vorgabe. Darüber ein
Textbaustein, den eine Gemeinde übernehmen kann.

**Was fehlt — und nichts davon ist technisch:**

- **Ob kirchliches Datenschutzrecht gilt** und welche Stelle zuständig
  ist. Das hängt an der Rechtsform.
- Das Verzeichnis ist geschrieben, aber **von keiner Gemeindeleitung
  abgenommen**.
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

# Sollte

Gehört getan, hält aber kein Gerät auf.

## S1. Freigegebene Sprachen

**Stand:** **Sechs** von einundzwanzig sind von Muttersprachlern
gegengelesen: Deutsch, Englisch, Russisch, Persisch und seit 0.4.0
Spanisch und Portugiesisch. Polnisch liegt vorbereitet. Alles andere
läuft maschinell und ist am Pult als *experimentell* gekennzeichnet.

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
- **Ein zweiter Aufbau.** Jede Gemeinde hat ein anderes Hausnetz,
  einen anderen Zugangspunkt, andere Kabel. Dass es zweimal
  funktioniert, ist nicht gezeigt.

**Wie man es prüft:** Drei iPhones verschiedener Baujahre, je fünf
Verbindungen, Zeit bis zur ersten hörbaren Übersetzung, dasselbe mit
abgeschalteten mobilen Daten. Ergebnis in eine Tabelle; darunter die
Entscheidung: gelöst, oder erklärt und dokumentiert.

---

## S5. Gemeinden ohne Internet-WLAN — der Stick-Weg

**Stand:** Im Programm seit 0.2.13, im Prüfstand mit Attrappen für
`systemctl`, `sudo`, `runuser`, `curl` und `udevadm` belegt. Auf dem
Gemeinderechner hat **kein einziges** Stick-Update stattgefunden: dort
lief immer der Online-Weg.

**Warum es trotzdem auf die Liste gehört:** Eine Gemeinde ohne
nutzbares WLAN gibt es, und für die ist der Stick der einzige Weg. Es
ist aber kein Blocker, solange eine aufnehmende Gemeinde ein WLAN
stellen kann — und das lässt sich vorher fragen.

**Was fehlt:** Ein Update per Stick auf echter Hardware, von jemandem
eingesteckt, der nicht daneben steht und mitliest.

**Wie man es prüft:** `AUFSTELLEN.md`, Abschnitt „Von 0.2.11 direkt
auf 0.3.0". Danach: läuft der Dienst, meldet das Pult die neue
Fassung, liegt die Sicherung da, sind die Units neu geschrieben. Und
der Gegentest mit einem Update, das scheitern muss.

---

## S6. Der Bus-Faktor

**Stand:** **Eins.** Eine Person kennt das Projekt, hält den
Signierschlüssel, pflegt das Glossar, baut die Anleitung und betreut
den einen Gemeinderechner.

Dagegen steht einiges: alles ist aufgeschrieben und begründet
(`AUFSTELLEN.md`, 2000 Zeilen mit der Geschichte jeder Entscheidung),
23 Prüfstände halten die Zusicherungen fest, das Repo ist öffentlich
und unter GPLv3, und seit 0.4.0 gibt es eine Erstinstallation für
Fremde.

**Was fehlt:**

- **Eine zweite Person**, die ein Update signieren und einspielen
  kann — das ist dasselbe wie B3, von der anderen Seite.
- **Jemand, der das Glossar pflegen kann.** Die Entscheidungen zu
  Spanisch und Portugiesisch stehen mit Begründung im Quelltext
  (`werkzeuge/glossar_rueck_es_pt.py`); ob das reicht, hat niemand
  ausprobiert.
- Die **Betreuer-Stelle** ist eine Adresse, keine Vertretung.

**Wie man es prüft:** Eine zweite Person spielt eine Fassung ein, die
sie selbst signiert hat, auf einem Rechner, an dem sie vorher nicht
war. Erst dann ist der Faktor zwei.

---

# Nicht mehr auf der Liste

**RustDesk unter Wayland** — **kein Blocker mehr.** Das
Bildschirmteilen über `xdg-desktop-portal` fragt unter KDE bei jeder
neuen Sitzung nach und ist damit für einen unbeaufsichtigten Rechner
unbrauchbar; das ist ein Fehler von RustDesk und mit keiner
Einstellung dort zu beheben. Der Weg ist deshalb **RustDesk-Terminal
plus ein TCP-Tunnel auf Port 8000** — darüber ist das Pult erreichbar,
und RustDesk zählt für den Server als „am Rechner" (Loopback), also
geht auch der Update-Knopf. Steht ausführlich in `AUFSTELLEN.md`.

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
Liste verlängert, ohne einen der sieben Blocker zu schließen, gehört
in eine spätere Fassung.

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
