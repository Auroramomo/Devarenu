# Für das Pult

Das Pult ist die Bedienoberfläche während des Gottesdienstes. Es läuft
im Browser: **http://10.0.0.1/pult**

Ohne den Netzumbau — also auf einem Rechner, der noch nicht Router ist —
gehört die Portnummer dazu: **http://10.0.0.1:8000/pult**. Welche
Adresse gilt, steht beim Start in der Ausgabe des Dienstes und in
`bash pruefen.sh`.

## Die vier Reiter

Seit 0.4.1 hat das Pult vier Reiter. Am Handy stehen sie als feste
Leiste unten, am Laptop als Zeile unter dem Kopf.

| Reiter | Wofür |
|---|---|
| **Gottesdienst** | Starten, Anhalten, Aufnahme. Drei Kacheln: Ton, Zuhörer, Thema. Das ist die Startseite, und sie passt auf einen Handybildschirm. |
| **Vorbereiten** | Thema und Bibelstellen, Manuskript, Ton einmessen — und dahinter die Feineinstellung mit Tonquelle und Schwelle. |
| **Aufnahmen** | Was aufgenommen wurde: herunterladen, löschen, Löschfrist. |
| **Einrichtung** | Was einmal je Gemeinde eingestellt wird. |

Ein **gelber Punkt** am Reiter heißt: dort wartet etwas, das den
Gottesdienst nicht aufhält. **Rote Meldungen** stehen dagegen in
*jedem* Reiter als Band unter dem Kopf — wer in der Einrichtung steht,
während der Ton ausfällt, sieht es dort.

Oben rechts sagt die **Statuspille** in einem Wort, wie es steht:
*Läuft* (grün), *Angehalten* (grau), *Störung* (rot). Sie ist immer zu
sehen.

Jedes „?" klappt die ausführliche Erklärung auf. Nichts davon ist
verschwunden, es steht nur nicht mehr dauerhaft offen.

## Vor dem Gottesdienst

1. **Tonquelle prüfen.** Unter *Vorbereiten* → *Feineinstellung* ist
   jede Zeile ein Kanal. Hineinsprechen, der Balken muss ausschlagen.
   Immer **auswählen**, nie eine Nummer abtippen: die Nummern
   verschieben sich beim Umstecken.
2. **Thema und Bibelstellen eintragen.** Unter *Vorbereiten*. Solange
   es fehlt, ist die Kachel *Thema* gelb und der Reiter trägt einen
   Punkt. Es ist der Unterschied zwischen „Sanballat" und
   „San Ballard".
3. **Sprachen wählen.** *Einrichtung* → *Sprachen*. Nur einschalten,
   was wirklich gebraucht wird — jede zusätzliche Sprache kostet
   Rechenzeit.
4. **WLAN-Name und Passwort eintragen.** *Einrichtung* → *WLAN &
   QR-Code*. Sie werden nur für den QR-Code gebraucht. Stimmen sie hier
   nicht mit dem Zugangspunkt überein, enthält der QR-Code ein falsches
   Passwort und niemand kommt ins Netz.
5. **QR-Seite am Beamer prüfen.** Am Laptop oben rechts auf *QR*, am
   Handy unter *Einrichtung* → *WLAN & QR-Code*.

## Die Mindestlautstärke: drei Modi

Unter *Vorbereiten* → *Feineinstellung*. **Nur bei lauten
Störgeräuschen. Kann bei leisen Sprechern viel verwerfen.** Im
Normalfall ist hier nichts zu tun.

| Modus | Was er tut |
|---|---|
| **Aus** | Keine Mindestlautstärke. Geschnitten wird an Sprechpausen und an der Höchstdauer. **Vorgabe.** |
| **Automatisch** | Die Schwelle folgt dem Raumpegel. |
| **Fest** | Der Wert bleibt stehen, den das Einmessen ergeben hat. |

Der Modus bleibt über Neustarts stehen und wird in der Ton-Kachel
genannt — die Kachel sagt nur, was gilt, und führt nicht hierher.

**Einmessen** steht ebenfalls nur hier und setzt den Modus auf *Fest*:
den Prediger am echten Mikrofon sprechen lassen und drücken, es dauert
**12 Sekunden**, in denen durchgehend gesprochen werden muss.

> Gemessen an einer Predigt von 21 Minuten lieferte *Aus* die meisten
> Wörter (2743), *Automatisch* 2576, *Fest* mit der eingemessenen
> Schwelle nur 1091 — sie verwarf drei Fünftel. Der Grund: das
> Einmessen legt die Schwelle sechzig Prozent des Weges von der Ruhe
> zur lautesten Stelle. Bei einer sauberen Leitung ist die Ruhe fast
> Stille, und sechzig Prozent landen mitten im normalen Sprechen. Wer
> nicht sicher ist, lässt *Aus* stehen.

Ein Wechsel des Tongeräts verwirft eine feste Schwelle: sie galt dem
alten Mikrofon. Es gilt dann wieder der Modus, der vorher gewählt war.

## Die QR-Seite für den Beamer

Sie ist für 16:9 gebaut und für zwölf Meter Abstand.

**Links die zwei Schritte.** Oben der Code fürs WLAN, darunter Netzname
und Passwort in großer Schrift — der Code ist der bequeme Weg, nicht der
einzige. Ältere Handys und Laptops tippen mit. Unten der Code für die
Seite, darunter die Adresse zum Abtippen.

**Rechts drei Kästen** in verschiedenen Farben, jeder mit einem Symbol:

- **Gelb:** Bis zu einer Minute warten, nicht neu verbinden.
- **Blau:** „Kein Internet" ist richtig. Oben kann 5G stehen.
- **Lila:** Kopfhörer benutzen, Bildschirm anlassen.

**Die Texte wechseln alle acht Sekunden die Sprache** — durch die
Sprachen, die unter *Sprachen* eingeschaltet sind, dazu Englisch. Die
Sprache, in der gepredigt wird, kommt **nicht** vor: wer direkt zuhört,
braucht keine Anleitung zum Mithören. Oben rechts stehen Punkte für die
Stelle im Durchlauf.

Bei Farsi und Arabisch läuft **nur der Text** von rechts nach links.
Kästen, Farben und Symbole bleiben, wo sie sind — wer vorn sagt „der
gelbe Kasten oben", hat in jeder Sprache recht.

Eine einzelne Sprache ansehen, ohne zu warten: `/qr#fa` statt `/qr`.

**Als Datei herunterladen** liefert die ganze Seite als *eine* Datei,
mit allem darin. Sie läuft auf jedem Laptop im Browser, auch ohne Netz —
für einen Beamer-Rechner, der nicht im Saalnetz hängt. Gedruckt gibt sie
eine Seite je Sprache, zum Auslegen am Eingang.

> Die Datei enthält das WLAN-Passwort im Code. Sie wird bei jedem Abruf
> neu erzeugt und gehört nicht weitergegeben.

## Während des Gottesdienstes

- **Starten** und **Anhalten** mit dem großen Knopf. Anhalten stoppt die
  Auslieferung, ohne die Zuhörer zu trennen — sie bleiben verbunden und
  hören weiter, sobald es weitergeht.
- **Die drei Kacheln** sagen jede in einem Wort, wie es steht, und
  färben ihren linken Rand danach:
  - **Ton** — *gut*, *knapp* oder *kein Ton*. Darunter der Pegelbalken
    mit der Schwellenmarke und der Modus.
  - **Zuhörer** — die Gesamtzahl groß, darunter je Sprache Kürzel und
    Zahl.
  - **Thema** — *fehlt* (gelb, mit einem Weg zum Eintragen) oder
    *gesetzt* (grün, mit den erkannten Stellen).
- **„Zuletzt erkannt"** zeigt den letzten Abschnitt und wie lange er
  gebraucht hat. Ein Tipp darauf klappt die letzten acht auf. Steigt
  die Verzögerung über mehrere Abschnitte, wird die Ton-Kachel gelb und
  sagt *Verzögerung steigt* — dann staut sich etwas auf.
- **Der Briefkasten** erscheint als rotes Band unter dem Kopf. Zwei
  Sorten: Zuschriften aus dem Saal, und Hinweise von Devarenu selbst
  (mit ⚙). Die zweiten bleiben stehen, bis sie einmal geöffnet wurden.
- **Rote Bänder** stehen für Dinge, die den Betrieb aufhalten: keine
  Tonquelle, ein zweiter DHCP-Server im Netz, ein Rechner, der falsch
  eingestellt ist. Sie stehen in jedem Reiter und nennen jeweils, was
  zu tun ist.
- **Von vorn beginnen** steht ganz unten, klein und grau, und fragt
  nach.

## Sprachen

Drei Zustände, und sie sehen verschieden aus:

- **normal** — die Fachbegriffe hat ein Muttersprachler durchgesehen.
- **gestrichelt** — es gibt ein Fachwortverzeichnis, aber ungeprüft.
- **gepunktet** — es gibt keines. Begriffe wie Sabbat, Gemeinde oder
  Vereinigung werden wörtlich übersetzt.

Die ungeprüften stehen unter einer eigenen Überschrift *Noch nicht
geprüft*. Wird eine eingeschaltet, legt Devarenu einen Hinweis in den
Briefkasten — einmal je Sprache.

## Etwas funktioniert nicht

Am Laptop steht oben rechts **Fehler melden**, am Handy unter
*Einrichtung* → *Fehlersuche*. Dahinter steht, wie man es meldet:

- **Name und Adresse** des Betreuers zum Abschreiben.
- **Ein QR-Code**, der auf dem Handy eine fertige Mail öffnet — Betreff
  und die wichtigsten Angaben stehen schon drin, zu schreiben bleibt
  „Was ist passiert?".
- **Ein zweiter QR-Code**, der den Fehlerbericht aufs Handy lädt. Der
  ist nötig, weil das Pult meist am Rechner selbst bedient wird: ein
  Download dort kommt nie in die Mail.
- **Ein Knopf** für denselben Bericht, wenn man am Rechner sitzt.

Die Mail geht erst raus, wenn das Handy wieder Internet hat. Im
Saalnetz bleibt sie im Postausgang liegen — das ist richtig so und kein
Fehler.

**Was im Bericht steht:** Fassung, Rechner, Grafikkarte, Systemcheck,
die Zusammenzählung von `pruefen.sh`, das letzte Update und Meldungen
ab Warnstufe. **Was nicht darin steht:** Mitschriften, Übersetzungen,
Zuschriften aus dem Saal, Namen aus dem Manuskript, das WLAN-Passwort.
Nichts davon wird gesammelt und dann entfernt — es wird gar nicht erst
geholt.

## Nach dem Gottesdienst

Nichts weiter zu tun. Der Rechner darf am Netzschalter ausgeschaltet
werden; er fährt dann ordentlich herunter.
