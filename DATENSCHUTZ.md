# Datenschutz

Zwei Teile: ein **Textbaustein**, den eine Gemeinde in ihre eigene
Datenschutzerklärung übernehmen kann, und darunter das **Verzeichnis
der Verarbeitungstätigkeiten** für die Technik.

> **Keine Rechtsberatung.** Hier steht, was das Programm tut — nicht,
> was daraus rechtlich folgt. Das muss die Gemeinde mit der Stelle
> klären, die für sie zuständig ist. Offene Fragen stehen unten
> ausdrücklich als offen.

---

## Teil 1 — Textbaustein für die Gemeinde

*Zum Übernehmen und Anpassen. Der Name in eckigen Klammern gehört
ersetzt.*

> **Live-Übersetzung im Gottesdienst**
>
> Für die Übersetzung des Gottesdienstes betreibt [Gemeinde] ein
> eigenes Gerät im Saal. Es stellt ein WLAN bereit, das **keine
> Verbindung ins Internet hat** und ausschließlich dazu dient, die
> Übersetzung auf Ihr Handy zu bringen.
>
> **Sie brauchen keine App, kein Konto und keine Anmeldung.** Es wird
> nichts auf Ihrem Gerät installiert.
>
> Damit Ihr Handy eine Netzwerkadresse bekommt, tauscht es technische
> Angaben mit dem Gerät aus (Geräteadresse, zugeteilte
> Netzwerkadresse). Diese Angaben liegen nur im Arbeitsspeicher und
> sind nach dem Ausschalten des Geräts verschwunden. Sie werden nicht
> ausgewertet und nicht weitergegeben.
>
> Der gesprochene Gottesdienst wird maschinell erkannt und übersetzt.
> Das geschieht **auf dem Gerät im Saal**; es wird dafür nichts ins
> Internet übertragen. Der Text wird nicht gespeichert.
>
> Wenn Sie über die Schaltfläche „Rückmeldung" eine Nachricht an die
> Technik schicken, wird diese bis zum Ende des Gottesdienstes am
> Technikpult angezeigt und danach verworfen. Bitte schreiben Sie
> dort **nichts Persönliches**.
>
> Wird ausnahmsweise eine **Tonaufnahme** der Predigt gemacht, wird
> die predigende Person vorher gefragt, und es ist während der
> Aufnahme auf Ihrem Bildschirm sichtbar.
>
> Fragen beantwortet [Ansprechpartner der Gemeinde].

---

## Teil 2 — Verzeichnis der Verarbeitungstätigkeiten

Beschrieben ist der Stand ab Fassung **0.3.6**. Wo ein Schalter
genannt ist, gilt die angegebene Vorgabe, solange ihn niemand
umstellt.

**Verantwortlich** ist die Gemeinde, die das Gerät betreibt — nicht
der Entwickler. Er hat ohne Wartungsfenster keinen Zugang, und mit
Wartungsfenster nur den, den die Gemeinde einschaltet.

### 1. Übersetzung des Gottesdienstes

| | |
|---|---|
| **Zweck** | Der Gottesdienst soll verstanden werden, ohne dass jemand Deutsch kann |
| **Daten** | Der gesprochene Ton aus dem Saalmikrofon; der daraus erkannte Text; die Übersetzungen |
| **Empfänger** | Niemand. Alles bleibt auf dem Gerät, es gibt keine Verbindung nach draußen |
| **Speicherdauer** | Nichts wird gespeichert. Ton und Text bestehen für Sekunden im Arbeitsspeicher; zuletzt gesendete Abschnitte liegen so lange, wie ein Handy verbunden ist |
| **Schalter** | Keiner — das ist der Zweck des Geräts |

### 2. Netzwerk für die Handys im Saal

| | |
|---|---|
| **Zweck** | Das Handy muss eine Adresse bekommen, sonst erreicht es die Seite nicht |
| **Daten** | Geräteadresse (MAC), zugeteilte Netzwerkadresse, der Name, den das Handy sich selbst gibt |
| **Empfänger** | Niemand. Die Mietliste ist `0640` und damit nur für `root` lesbar, nicht für jeden angemeldeten Benutzer |
| **Speicherdauer** | Die Mietliste liegt unter `/run` **im Arbeitsspeicher** und ist nach dem Ausschalten weg. Ins Journal geht sie **nicht** (`quiet-dhcp`) |
| **Schalter** | Keiner. Wer kein WLAN stellt, braucht das Gerät nicht |

*Bis 0.3.5 stand die Mietliste auf der Platte und jede Aushandlung im
Journal — mit Geräteadresse und Handynamen, vier Wochen lang. Bis
0.3.7 lag sie zwar im Arbeitsspeicher, aber mit `0644`: jeder, der
am Rechner angemeldet war, konnte nachlesen, wessen Handy im Saal
war.*

### 3. Rückmeldung aus dem Saal („Melden")

| | |
|---|---|
| **Zweck** | Ein Zuhörer soll der Technik sagen können, dass etwas nicht geht |
| **Daten** | Der eingetippte Text (höchstens 200 Zeichen), die gewählte Sprache, die Uhrzeit. **Keine Adresse, kein Gerätebezug** |
| **Empfänger** | Das Technikpult im selben Saal |
| **Speicherdauer** | Arbeitsspeicher, höchstens 40 Nachrichten, beim Neustart weg. Nichts auf der Platte |
| **Schalter** | Keiner |

Der Text geht **nie** nach draußen: die Erlaubnisliste des
Fehlerberichts schließt ihn aus.

### 4. Fehler melden am Pult („Käfer")

| | |
|---|---|
| **Zweck** | Ein Bedienender soll ein Problem melden können, ohne Technikkenntnis |
| **Daten** | Fassung, Rechnerdaten, Systemcheck, letztes Update, Journalzeilen **ab Warnstufe** |
| **Empfänger** | Der Betreuer — per E-Mail, die der Bedienende selbst abschickt, oder über das Wartungsfenster (Punkt 8) |
| **Speicherdauer** | Höchstens 50 Berichte unter `ergebnisse/berichte/`, danach fallen die ältesten weg |
| **Schalter** | Der Knopf. Das Versenden im Fenster hat einen eigenen (Vorgabe **aus**) |

Erlaubnisliste statt Filter: aufgenommen wird nur, was ausdrücklich
genannt ist. Dazu ein zweiter Riegel, der den fertigen Text noch
einmal gegen die Muster der Segmentzeilen prüft.

### 5. Tonaufnahme der Predigt

| | |
|---|---|
| **Zweck** | Eine Predigt nachhören oder weitergeben |
| **Daten** | Der Ton der Predigt, als MP3 (`Predigt_TT_MM_JJJJ.mp3`). Daneben ein Vermerk mit dem Zeitpunkt der Einwilligung — **ohne Namen** |
| **Empfänger** | Niemand. Abrufbar nur am Gerät selbst, nicht aus dem Saalnetz |
| **Speicherdauer** | Sieben Tage, einstellbar. Der Aufräumlauf läuft stündlich |
| **Schalter** | Zwei Häkchen am Pult, beide Pflicht: die predigende Person wurde gefragt, und es läuft nur die Predigt mit. Vorgabe **aus** |

Sichtbar, solange sie läuft — am Pult und auf jedem Handy im Saal.

### 6. Testprotokoll

| | |
|---|---|
| **Zweck** | Bei einem Test sehen, wo die Übersetzungskette kippt |
| **Daten** | Je Abschnitt: erkannter Text, jede Übersetzung, Dauer der Schritte. Also **der Predigttext im Wortlaut** |
| **Empfänger** | Niemand. Abrufbar nur am Gerät selbst |
| **Speicherdauer** | Sieben Tage |
| **Schalter** | Am Pult, nur am Gerät selbst sichtbar, mit Einwilligung der sprechenden Person. Vorgabe **aus**, hört beim Neustart von selbst auf |

### 7. Mitschrift im Journal

| | |
|---|---|
| **Zweck** | Fehlersuche im laufenden Betrieb |
| **Daten** | Der erkannte Satz, auf etwa 60 Zeichen gekürzt, im Systemjournal |
| **Empfänger** | Niemand. Journalzeilen unterhalb der Warnstufe gehen auch nicht in den Fehlerbericht |
| **Speicherdauer** | Solange das Journal hält (voreingestellt rund vier Wochen) |
| **Schalter** | Am Pult. Vorgabe **aus**. Solange er an ist, meldet der Systemcheck ihn |

### 8. Rückmeldung nach einem Autoupdate

| | |
|---|---|
| **Zweck** | Wenn sich das Gerät unbeaufsichtigt aktualisiert, muss jemand erfahren, ob es geklappt hat |
| **Daten** | Fassung vorher und nachher, Ergebnis, Dauer, die letzten Zeilen des Laufs |
| **Empfänger** | Der Kanal, der in `meldung.json` **auf diesem Gerät** eingetragen ist (ntfy). Im Programmcode steht kein Ziel |
| **Speicherdauer** | Beim Empfänger nach dessen Regeln; lokal bleibt das Laufprotokoll in der Ablage |
| **Schalter** | Wartungsfenster und Autoupdate, beide Vorgabe **aus** |

### 9. Fehlerberichte über das Wartungsfenster

| | |
|---|---|
| **Zweck** | Ein Gerät, das nachts abstürzt und von selbst hochkommt, fällt sonst niemandem auf |
| **Daten** | Wie Punkt 4 |
| **Empfänger** | Wie Punkt 8 |
| **Speicherdauer** | Wie Punkt 4 |
| **Schalter** | Eigener Schalter, Vorgabe **aus** |

### 10. Nutzungsmeldung an den Entwickler

| | |
|---|---|
| **Zweck** | Der Entwickler möchte wissen, wo das Programm läuft |
| **Daten** | Name der Gemeinde, Fassung, Datum. **Sonst nichts** |
| **Empfänger** | Wie Punkt 8 |
| **Speicherdauer** | Beim Empfänger |
| **Schalter** | Am Pult, mit der Angabe daneben, was gesendet wird. Vorgabe **aus** |

Der Gemeindename ist die einzige Angabe, die das Gerät benennt — und
nur, wenn ihn jemand einträgt.

### 11. Hinweis zum Spendenkonto

| | |
|---|---|
| **Zweck** | Eine falsche IBAN soll auffallen, bevor jemand überweist |
| **Daten** | Die Beanstandung der Prüfziffer. Keine personenbezogenen Daten |
| **Empfänger** | Wie Punkt 8 — und nur, wenn ein Kanal eingerichtet ist |
| **Speicherdauer** | Beim Empfänger |
| **Schalter** | Keiner. Es wird dabei nichts abgeschaltet und nichts gelöscht |

---

## Was offen ist

Diese Punkte sind **nicht geklärt** und gehören vor einer zweiten
Gemeinde geklärt:

- **Welches Datenschutzrecht gilt.** Für kirchliche Einrichtungen
  kann anstelle der DSGVO ein eigenes kirchliches Datenschutzgesetz
  gelten. Ob das hier zutrifft und welche Stelle zuständig ist, muss
  die Gemeinde klären — es hängt an der Rechtsform und an der
  Gliedkirche, nicht am Programm.
- **Ob eine Einwilligung der Zuhörer nötig ist** oder ob der Betrieb
  des Saalnetzes anders zu begründen ist.
- **Die Aufbewahrung der Aufnahmen** ist eingestellt (sieben Tage),
  aber nicht beschlossen. Eine Vorgabe ist kein Beschluss der
  Gemeindeleitung.
- **Das Pult ist per Vorgabe offen im Saalnetz.** Wer im Saal sitzt,
  kann es bedienen. Das Passwort ist freiwillig.
- **Ob die Nutzungsmeldung** (Punkt 10) eine Übermittlung ist, die
  die Gemeinde ihrerseits nennen muss.

Nichts davon lässt sich aus dem Code beantworten, und dieses
Dokument versucht es auch nicht.
