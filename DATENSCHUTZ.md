# Datenschutz

> **Entwurf, vor Freigabe durch den Datenschutzbeauftragten.**
> Alles in diesem Dokument — das Verzeichnis, die beiden Abschnitte zum
> Rechtsrahmen, der Hinweis auf dem Handy, der Aushang und das Blatt für
> Gastprediger — ist ein Entwurf. Er wird erst gültig, wenn die
> zuständige Stelle ihn freigegeben hat.

> **Keine Rechtsberatung.** Hier steht, was das Programm tut, und
> welche Vorschriften dafür in Frage kommen. Was daraus folgt,
> entscheidet die zuständige Stelle.

Drei Teile:

1. **Das Verzeichnis der Verarbeitungstätigkeiten.** Neutral: es
   beschreibt, was das Gerät tut, und gilt für jeden Träger gleich.
2. **Der Rechtsrahmen**, je Träger ein Abschnitt — Adventgemeinden
   nach der Datenschutzverordnung der Freikirche, andere Träger nach
   der DSGVO.
3. **Die Information der Teilnehmenden**, in zwei Stufen, und was
   davon gedruckt wird.

Stand der Beschreibung: Fassung **0.5.0**. Wo ein Schalter genannt
ist, gilt die angegebene Vorgabe, solange ihn niemand umstellt.

---

## Teil 1 — Verzeichnis der Verarbeitungstätigkeiten

**Verantwortlich** ist der Träger, der das Gerät betreibt — die
Gemeinde, nicht der Entwickler. Der Entwickler hat ohne
Wartungsfenster keinen Zugang, und mit Wartungsfenster nur den, den die
Gemeinde einschaltet. Name und Kontakt werden am Pult eingetragen
(*Einrichtung → Gemeinde*) und erscheinen im Hinweis auf jedem Handy.

### 1. Übersetzung des Gottesdienstes

| | |
|---|---|
| **Zweck** | Der Gottesdienst soll verstanden werden, ohne dass jemand Deutsch kann |
| **Daten** | Der gesprochene Ton aus dem Saalmikrofon; der daraus erkannte Text; die Übersetzungen |
| **Empfänger** | Die Handys im Saal-WLAN. Sonst niemand: alles bleibt auf dem Gerät, es gibt keine Verbindung nach draußen |
| **Speicherdauer** | Nichts auf der Platte. Ton und Text bestehen für Sekunden im Arbeitsspeicher. Die letzten Abschnitte hält der Rechner bereit, damit ein Handy nach einem kurzen Abbruch nachlesen kann (seit 0.5.0); nach einem Neustart sind sie weg |
| **Schalter** | Keiner — das ist der Zweck des Geräts |

### 2. Rückmeldung „verständlich / schwer verständlich“

| | |
|---|---|
| **Zweck** | Die Gemeinde soll sagen können, ob die Übersetzung taugt, ohne jemanden ansprechen zu müssen |
| **Daten** | Zwei Zähler je Sprache und Tag. **Keine** Geräteadresse, **keine** Kennung, **kein** Zeitpunkt je Stimme |
| **Empfänger** | Niemand. Die Zahlen dürfen dem Fehlerbericht an den Betreuer und der Nutzungsmeldung beiliegen, wenn diese eingeschaltet sind |
| **Speicherdauer** | Eine Zeile je Tag und Sprache in `ergebnisse/rueckmeldung.csv`, bis jemand sie löscht |
| **Schalter** | Die Knöpfe unter *Mehr*. Eine Stimme je Gerät und Tag; gemerkt wird sie **im Browser**, nicht auf dem Gerät im Saal |

### 3. Messwerte der Grafikkarte

| | |
|---|---|
| **Zweck** | Die Frage beantworten, ob die Karte noch reicht |
| **Daten** | Je Tag eine Zeile: belegter und gesamter Grafikspeicher, Auslastung, Zahl der Zielsprachen. **Nichts über Menschen** |
| **Empfänger** | Niemand; dürfen Fehlerbericht und Nutzungsmeldung beiliegen, wenn eingeschaltet |
| **Speicherdauer** | Eine Zeile je Tag in `ergebnisse/grafik.csv`, bis jemand sie löscht |
| **Schalter** | Keiner. Fehlt `nvidia-smi`, wird nichts gemessen |

### 4. Netzwerk für die Handys im Saal

| | |
|---|---|
| **Zweck** | Das Handy muss eine Adresse bekommen, sonst erreicht es die Seite nicht |
| **Daten** | Geräteadresse (MAC), zugeteilte Netzwerkadresse, der Name, den das Handy sich selbst gibt |
| **Empfänger** | Niemand. Die Mietliste ist `0640` und damit nur für `root` lesbar |
| **Speicherdauer** | Die Mietliste liegt unter `/run` **im Arbeitsspeicher** und ist nach dem Ausschalten weg. Ins Journal geht sie **nicht** (`quiet-dhcp`) |
| **Schalter** | Keiner. Wer kein WLAN stellt, braucht das Gerät nicht |

### 5. Nachricht an die Technik („Melden“)

| | |
|---|---|
| **Zweck** | Ein Zuhörer soll der Technik sagen können, dass etwas nicht geht |
| **Daten** | Der eingetippte Text (höchstens 200 Zeichen), die gewählte Sprache, die Uhrzeit. **Keine Adresse, kein Gerätebezug** |
| **Empfänger** | Das Pult im selben Saal. Nie nach draußen — die Erlaubnisliste des Fehlerberichts schließt den Text aus |
| **Speicherdauer** | Arbeitsspeicher, höchstens 40 Nachrichten, beim Neustart weg |
| **Schalter** | Keiner |

### 6. Rückmeldung an den Betreuer („Rückmeldung“)

| | |
|---|---|
| **Zweck** | Wer zum Programm selbst etwas sagen will, soll den Betreuer erreichen |
| **Daten** | Was der Zuhörer schreibt — mit **seinem eigenen** Mailprogramm. Das Gerät sieht davon nichts |
| **Empfänger** | Der Betreuer (`betreuer.txt`) |
| **Speicherdauer** | Beim Mailanbieter und beim Betreuer |
| **Schalter** | Ohne eingetragene Adresse erscheint der Knopf nicht |

### 7. Fehler melden am Pult („Käfer“)

| | |
|---|---|
| **Zweck** | Ein Bedienender soll ein Problem melden können, ohne Technikkenntnis |
| **Daten** | Fassung, Rechnerdaten, Systemcheck, letztes Update, Journalzeilen **ab Warnstufe** |
| **Empfänger** | Der Betreuer — per E-Mail, die der Bedienende selbst abschickt, oder über das Wartungsfenster (Punkt 11) |
| **Speicherdauer** | Höchstens 50 Berichte unter `ergebnisse/berichte/` |
| **Schalter** | Der Knopf. Das Versenden im Fenster hat einen eigenen (Vorgabe **aus**) |

Erlaubnisliste statt Filter: aufgenommen wird nur, was ausdrücklich
genannt ist. Dazu ein zweiter Riegel, der den fertigen Text noch
einmal gegen die Muster der Segmentzeilen prüft.

### 8. Tonaufnahme der Predigt

| | |
|---|---|
| **Zweck** | Eine Predigt nachhören oder weitergeben |
| **Daten** | Der Ton der Predigt als MP3. Daneben ein Vermerk mit dem Zeitpunkt der Einwilligung — **ohne Namen** |
| **Empfänger** | Niemand. Abrufbar nur am Gerät selbst, nicht aus dem Saalnetz |
| **Speicherdauer** | Sieben Tage, einstellbar; stündlicher Aufräumlauf; von Hand löschbar am Pult |
| **Schalter** | Zwei Häkchen am Pult, beide Pflicht: die predigende Person wurde gefragt, und es läuft nur die Predigt mit. Vorgabe **aus**. Solange sie läuft, steht es auf jedem Handy |

### 9. Testprotokoll

| | |
|---|---|
| **Zweck** | Bei einem Test sehen, wo die Übersetzungskette kippt |
| **Daten** | Je Abschnitt: erkannter Text, jede Übersetzung, Dauer der Schritte — **der Predigttext im Wortlaut**, nichts über Zuhörer |
| **Empfänger** | Niemand. Abrufbar nur am Gerät selbst |
| **Speicherdauer** | Sieben Tage |
| **Schalter** | Am Pult, nur am Gerät selbst, mit Einwilligung der sprechenden Person. Vorgabe **aus**, endet beim Neustart. Solange es läuft, steht es auf jedem Handy und am Pult unter *Gottesdienst* |

### 10. Mitschrift im Journal

| | |
|---|---|
| **Zweck** | Fehlersuche im laufenden Betrieb |
| **Daten** | Der erkannte Satz, auf etwa 60 Zeichen gekürzt |
| **Empfänger** | Niemand; Zeilen unter der Warnstufe gehen nicht in den Fehlerbericht |
| **Speicherdauer** | Solange das Journal hält (rund vier Wochen) |
| **Schalter** | Am Pult, mit Einwilligung der sprechenden Person — dieselbe Abfrage wie beim Testprotokoll, vom Server geprüft. Vorgabe **aus**, endet beim Neustart. Solange er an ist, meldet der Systemcheck ihn, und es steht auf jedem Handy und am Pult unter *Gottesdienst* |

### 11. Meldungen über das Wartungsfenster

Rückmeldung nach einem Autoupdate, Fehlerberichte, Nutzungsmeldung
(Name der Gemeinde, Fassung, Datum) und der Hinweis auf eine falsche
Spenden-IBAN. Gemeinsam ist ihnen:

| | |
|---|---|
| **Empfänger** | Der Kanal, der in `meldung.json` **auf diesem Gerät** eingetragen ist (ntfy). Im Programmcode steht kein Ziel |
| **Daten über Zuhörer** | **Keine** |
| **Schalter** | Wartungsfenster und jede Meldungsart einzeln, alle Vorgabe **aus** |

### 12. Einstellungen im Browser des Handys

| | |
|---|---|
| **Zweck** | Die Seite soll sich merken, was der Zuhörer eingestellt hat |
| **Daten** | Bildschirm anlassen ja/nein, Dunkelstufe, die eigene Stimme bei „verständlich“ |
| **Empfänger** | Niemand. Es liegt im Browser (`localStorage`) und geht nicht an das Gerät |
| **Speicherdauer** | Bis der Zuhörer die Websitedaten löscht |
| **Schalter** | Keiner |

### Datenschutzfreundliche Voreinstellungen

Alles, was mehr erfasst als den laufenden Gottesdienst, ist ab Werk
**aus** und wird am Pult eingeschaltet: Tonaufnahme, Testprotokoll,
Mitschrift im Journal, Wartungsfenster, Fehlerberichte über das
Fenster, Nutzungsmeldung. Die Ausnahme ist das **Pult**: es ist ab
Werk ohne Passwort erreichbar — siehe „Was offen ist“.

---

## Teil 2 — Der Rechtsrahmen

Welches Recht gilt, hängt am **Träger**, nicht am Programm. Darum
zwei Abschnitte; das Verzeichnis oben gilt für beide.

### A. Adventgemeinden — Datenschutzverordnung der Freikirche (DSVO 2018)

*Entwurf, vor Freigabe durch den Datenschutzbeauftragten.*

Für Gemeinden der Freikirche der Siebenten-Tags-Adventisten gilt die
Datenschutzverordnung der Freikirche in der Fassung von 2018.

* **Rechtsgrundlage — § 53 „Gottesdienste und kirchliche
  Veranstaltungen“.** Die Verarbeitung im Rahmen des Gottesdienstes ist
  zulässig, wenn die Teilnehmenden über **Art und Umfang** informiert
  werden. Diese Information leisten der Aushang am Eingang und der
  Hinweis auf dem Handy (Teil 3).
* **Verzeichnis — § 31.** Teil 1 dieses Dokuments ist als Grundlage
  dafür geschrieben; die Gemeinde trägt ihre Angaben (Verantwortliche,
  Kontakt, Aufbewahrung der Aufnahmen) ein.
* **Datenschutzfreundliche Voreinstellungen — § 28.** Siehe oben: was
  über den laufenden Gottesdienst hinausgeht, ist ab Werk aus.
* **Ansprechpartner** für die Freigabe ist der Datenschutzbeauftragte
  der Freikirche.

Einzelfälle, die über § 53 hinausgehen, brauchen eine eigene Grundlage:
die **Tonaufnahme** (Einwilligung der predigenden Person, am Pult
bestätigt), das **Testprotokoll** und die **Mitschrift im Journal**
(beide Einwilligung der sprechenden Person, am Pult bestätigt).

### B. Andere Träger — DSGVO

*Entwurf, vor Freigabe durch den Datenschutzbeauftragten.*

Für Träger, die nicht unter ein kirchliches Datenschutzrecht fallen,
gilt die Datenschutz-Grundverordnung.

* **Rechtsgrundlage — Art. 6 Abs. 1 lit. f DSGVO** (berechtigtes
  Interesse an einer verständlichen Übertragung des Gottesdienstes für
  Teilnehmende, die die Sprache nicht verstehen). **Noch zu
  bestätigen.**
* Für die Tonaufnahme, das Testprotokoll und die Mitschrift gilt wie
  unter A die Einwilligung der sprechenden Person.
* Die Information der Teilnehmenden (Teil 3) und das Verzeichnis
  (Teil 1) sind dieselben.

---

## Teil 3 — Die Information der Teilnehmenden

Zwei Stufen, beide **Entwurf**, beide in `datenschutz.py` — eine
Quelle für Handy, Gerät und Papier:

| | Wo | Sprachen |
|---|---|---|
| **Stufe 1** — Kurzhinweis | Auf dem Handy unter *Mehr* → *Datenschutz* (kleiner Textlink neben „Schließen“); auf dem **Aushang** am Eingang | de, en, ru, fa; sonst Englisch |
| **Stufe 2** — ausführlich | `/datenschutz` — ausgeliefert **von diesem Gerät**, weil das Saal-WLAN kein Internet hat | de, en |

Stufe 1 sagt: der Gottesdienst wird live übersetzt; ein Rechner im
Saal erkennt die Sprache am Mikrofon, übersetzt und schickt Text und
Ton über das Saal-WLAN aufs Handy; alles bleibt auf diesem Rechner,
keine Cloud, kein Konto, keine App; gespeichert wird nichts, außer die
Gemeinde schaltet eine Aufnahme, ein Protokoll oder eine Mitschrift der
Predigt ein — das ist dann auf dem Handy sichtbar (Punkte 8 bis 10:
Tonaufnahme, Testprotokoll, Mitschrift im Journal; seit dem Nachtrag
zu 0.5.0 zeigen die Handys alle drei an, nicht nur die Aufnahme); das
Handy bekommt eine Adresse, die beim Ausschalten
verschwindet. Darunter **Verantwortlich** und **Kontakt** aus der
Einrichtung; fehlt eine Angabe, entfällt die Zeile.

**Gedruckt** (`anleitung/`, gebaut mit `bash anleitung_bauen.sh`, am
Pult unter *Einrichtung → Gemeinde* verlinkt):

* `Devarenu-Aushang-Datenschutz.pdf` — für den Eingang, Stufe 1 auf
  Deutsch, Verantwortlich und Kontakt zum Ausfüllen.
* `Devarenu-Gastprediger.pdf` — was mit der Predigt passiert und was
  nicht; Aufnahme nur mit Zustimmung.
* Auf der **QR-Seite** am Beamer steht unter den Kästen eine Zeile in
  der jeweiligen Sprache: alles bleibt im Saal, Datenschutz unter
  *Mehr*. Eine gedruckte QR-Karte gibt es nicht; die QR-Seite lässt
  sich drucken und trägt die Zeile dann mit.

---

## Was offen ist

Nicht technisch, und vor einer zweiten Gemeinde zu klären:

- **Die Freigabe** dieses Entwurfs durch den Datenschutzbeauftragten —
  für Adventgemeinden die Bestätigung, dass § 53 DSVO mit der
  Information aus Teil 3 trägt; für andere Träger die Prüfung von
  Art. 6 Abs. 1 lit. f.
- **Die Aufbewahrung der Aufnahmen** ist eingestellt (sieben Tage),
  nicht beschlossen.
- **Das Pult ist per Vorgabe offen im Saalnetz.** Das Passwort ist
  freiwillig. Das passt nicht zu den datenschutzfreundlichen
  Voreinstellungen und gehört entschieden.
- **Ob die Nutzungsmeldung** eine Übermittlung ist, die die Gemeinde
  ihrerseits nennen muss.
- **Stufe 1 auf Russisch und Farsi** und **Stufe 2 auf Englisch** sind
  nicht gegengelesen.
