# Für die Technik

## Einschalten

Netzschalter drücken. Der Rechner meldet sich von selbst an, startet den
Dienst, richtet das Saalnetz ein und ist nach ein bis zwei Minuten
bereit. Es ist **kein Handgriff nötig** — keine Anmeldung, kein
Programmstart.

Prüfen lässt sich das am Pult: **http://10.0.0.1/pult**

## Ausschalten

Netzschalter kurz drücken. Der Rechner fährt herunter. Nicht den Strom
ziehen — dabei kann die Einstellungsdatei Schaden nehmen.

## Wenn kein Handy eine Adresse bekommt

Das ist fast immer einer von drei Fällen.

**Der Zugangspunkt ist aus, oder das Kabel ist ab.** Der einfachste Fall
und der häufigste. Sitzt das Kabel zwischen Rechner und Zugangspunkt
fest? Leuchtet am Zugangspunkt eine Lampe? Ohne ihn gibt es gar kein
WLAN, in das sich ein Handy einbuchen könnte.

**Am Zugangspunkt ist DHCP noch eingeschaltet.** Dann vergeben zwei
Geräte Adressen, und welches zuerst antwortet, entscheidet der Zufall.
Die Handys aus dem falschen Topf finden diesen Rechner nicht. Am Pult
steht dann eine Warnung. Abhilfe: am Zugangspunkt DHCP ausschalten.

**dnsmasq läuft nicht.** Am Rechner:

    sudo systemctl status dnsmasq
    sudo systemctl restart dnsmasq

## Wenn etwas nicht stimmt

    bash pruefen.sh

Das geht alles durch: Rechner, Grafikkarte, Netz, Saalnetz, Dienste,
Sprechtempo, Ton, Reparaturvorrat, Rechner-Einstellungen. Jede Meldung
sagt, was zu tun ist.

Zum Verschicken:

    bash pruefen.sh > bericht.txt 2>&1

## Update per USB-Stick

1. Stick einstecken. Der Rechner erkennt ihn selbst.
2. Warten. Eingespielt wird erst, wenn die Übersetzung angehalten ist
   und zwanzig Minuten niemand mehr zugehört hat.
3. Am Pult steht unter *Einrichtung*, was zuletzt passiert ist. Wartet
   ein Update, steht dort auch der Knopf **Jetzt einspielen** — damit
   muss man nicht bis zum nächsten Durchlauf warten.
4. Stick wieder abziehen.

Ein Update wird **nur** eingespielt, wenn die Signatur stimmt und die
Fassung neuer ist. Beides prüft der Rechner selbst, und zwar mit der
Schlüsselliste, die auf **ihm** liegt — nicht mit einer vom Stick.

### Wenn etwas schiefgeht

Der Rechner stellt den vorigen Stand selbst wieder her: Code, Dienste,
und die Einstellungen, falls das Update sie angefasst hat. Danach steht
am Pult, was passiert ist und welche Fassung wieder läuft. Es ist kein
Handgriff nötig.

### Wenn der Rechner den Stick nicht bemerkt

Am Pult steht unter *Einrichtung*, was zuletzt mit einem Stick passiert
ist. Steht dort gar nichts, hat er ihn nicht gelesen. Fast immer liegen
die Dateien dann zu tief: sie gehören **ganz oben** auf den Stick, nicht
in einen Unterordner. Einen Ordner tief findet er sie auch noch, zwei
nicht mehr.

### Lokale Änderungen

Hat jemand am Rechner eine Datei des Projekts geändert, gewinnt beim
Update der signierte Stand. Die Änderung geht aber nicht verloren — sie
wird vorher als Patch gesichert, und das Pult nennt den Ablageort.

## Den Fehlerbericht schicken

Am Pult, hinter dem Käfer oben rechts. Der Bericht entsteht beim
Abruf — er beschreibt den Rechner in diesem Moment, eine alte Kopie
wäre schlimmer als keine.

Zwei Wege, je nachdem, wo man steht:

- **Am Rechner:** Knopf *Fehlerbericht herunterladen*, dann an die Mail
  hängen.
- **Mit dem Handy:** den zweiten QR-Code scannen. Das Handy lädt den
  Bericht über das Saalnetz und kann ihn später anhängen, wenn es
  wieder Internet hat.

## Die Mitschrift im Protokoll

Normalerweise steht der gesprochene Satz **nicht** im Protokoll — nur
seine Länge. Das ist Absicht: über Wochen ergäbe sich sonst eine
Sammlung von Predigtinhalten, die niemand angelegt hat und niemand
löscht.

Zur Fehlersuche lässt sich das am Pult unter *Einrichtung*
einschalten: **Mitschrift im Protokoll**. Solange es an ist, steht ein
Hinweis am Pult. **Danach wieder ausschalten.**

## Was die Technik nicht anfassen muss

Das Saalnetz. Es ist einmal eingerichtet und bleibt so.

Wer es doch ändern muss, tut das **vor Ort, an Tastatur und Bildschirm
des Rechners**. Nicht weil es technisch unmöglich wäre — der Umbau
betrifft nur die Kabelkarte zum Zugangspunkt —, sondern weil dabei
Schritte nötig sind, die man sehen muss: Steckt das Kabel? Leuchtet der
Zugangspunkt? Hat ein Handy eine Adresse bekommen? Das beantwortet
niemand aus der Ferne.

Für Wartungsarbeiten kann jemand vor Ort einen Handy-Hotspot
einschalten; der Rechner verbindet sich dann per WLAN, und die
Fernwartung wird möglich. Das ist die Ausnahme. Danach wird der Hotspot
wieder getrennt — im Gottesdienst braucht der Rechner kein Netz nach
draußen.
