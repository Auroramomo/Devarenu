# Für das Pult

Das Pult ist die Bedienoberfläche während des Gottesdienstes. Es läuft
im Browser: **http://10.0.0.1/pult**

Ohne den Netzumbau — also auf einem Rechner, der noch nicht Router ist —
gehört die Portnummer dazu: **http://10.0.0.1:8000/pult**. Welche
Adresse gilt, steht beim Start in der Ausgabe des Dienstes und in
`bash pruefen.sh`.

## Vor dem Gottesdienst

1. **Tonquelle prüfen.** Unter *Einrichtung* → *Tonquelle* ist jede
   Zeile ein Kanal. Hineinsprechen, der Balken muss ausschlagen. Immer
   **auswählen**, nie eine Nummer abtippen: die Nummern verschieben sich
   beim Umstecken.
2. **Einmessen.** Den Prediger am echten Mikrofon sprechen lassen und
   auf *Einmessen* drücken. Es dauert **12 Sekunden** — in dieser Zeit
   muss durchgehend gesprochen werden. Danach weiß der Rechner, was in
   diesem Saal leise und was laut ist.
3. **Sprachen wählen.** Nur einschalten, was wirklich gebraucht wird —
   jede zusätzliche Sprache kostet Rechenzeit.
4. **WLAN-Name und Passwort eintragen.** Sie werden nur für den QR-Code
   gebraucht; der Zugangspunkt kennt sie selbst. Stimmen sie hier nicht
   mit dem Zugangspunkt überein, enthält der QR-Code ein falsches
   Passwort und niemand kommt ins Netz.
5. **QR-Seite am Beamer prüfen.** Oben rechts auf *QR*.

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
- **Der Briefkasten** oben zeigt Meldungen. Zwei Sorten: Zuschriften aus
  dem Saal, und Hinweise von Devarenu selbst (mit ⚙). Die zweiten
  bleiben stehen, bis sie einmal geöffnet wurden.
- **Rote Zeilen** stehen für Dinge, die den Betrieb aufhalten: keine
  Tonquelle, ein zweiter DHCP-Server im Netz, ein Rechner, der falsch
  eingestellt ist. Sie nennen jeweils, was zu tun ist.

## Sprachen

Drei Zustände, und sie sehen verschieden aus:

- **normal** — die Fachbegriffe hat ein Muttersprachler durchgesehen.
- **gestrichelt** — es gibt ein Fachwortverzeichnis, aber ungeprüft.
- **gepunktet** — es gibt keines. Begriffe wie Sabbat, Gemeinde oder
  Vereinigung werden wörtlich übersetzt.

Wird eine ungeprüfte Sprache eingeschaltet, legt Devarenu einen Hinweis
in den Briefkasten — einmal je Sprache.

## Etwas funktioniert nicht

Oben rechts, neben dem Zahnrad, sitzt ein **Käfer**. Dahinter steht,
wie man es meldet:

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
