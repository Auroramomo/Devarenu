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
2. Warten. Eingespielt wird erst, wenn die Übersetzung angehalten ist.
3. Am Pult steht unter *Einrichtung*, was zuletzt passiert ist. Wartet
   ein Update, steht dort auch der Knopf **Jetzt einspielen** — damit
   muss man nicht bis zum nächsten Durchlauf warten.

Ein Update wird **nur** eingespielt, wenn die Signatur stimmt und die
Fassung neuer ist. Beides prüft der Rechner selbst.

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
