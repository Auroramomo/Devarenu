# Aufstellen auf dem Gemeinderechner

Was sich nur dort prüfen lässt. Entwickelt und getestet wurde auf
CachyOS mit angemeldeter Sitzung; der Zielrechner ist Ubuntu Server mit
nachinstalliertem KDE, X11, headless im Betrieb, ohne angemeldeten
Benutzer.

Abhaken, was durchgelaufen ist.

**Zuerst `./pruefen.sh`.** Das geht die maschinell prüfbaren Punkte von
allein durch und sagt bei jedem, was zu tun ist. Es läuft auch, wenn der
Dienst gar nicht steht — dann zeigt es zusätzlich, woran er scheitert.
Die damit abgedeckten Punkte sind unten mit (pruefen.sh) gekennzeichnet.

```
./pruefen.sh                    ansehen
./pruefen.sh > bericht.txt 2>&1 zum Verschicken
```

## Einrichten

- [ ] `git clone` und `bash INSTALLIEREN.sh` einmal komplett durchlaufen
      lassen. Der apt-Zweig in `einrichten.sh` ist hier nie gelaufen:
      `python3-venv python3-pip ffmpeg libportaudio2 git`. Stimmen die
      Namen auf dieser Ubuntu-Fassung, wird alles gefunden?
- [ ] Python-Version prüfen (pruefen.sh). Hier lief 3.14, Ubuntu 24.04
      bringt 3.12. Laufen faster-whisper, piper und sounddevice damit?
- [ ] NVIDIA-Treiber (pruefen.sh). `nvidia-smi` muss die Karte zeigen.
      Fehlt er, meldet `INSTALLIEREN.sh` das jetzt auch auf Ubuntu.
- [ ] `ollama.service` (pruefen.sh) — heißt sie dort genauso, ist sie
      `enabled`, und ist das Modell da?

## Reparaturvorrat

**Der Rechner braucht beim Installieren eine Internetleitung, und
einmal wird nach dem Passwort gefragt.** In der Gemeinde gibt es danach
kein Netz mehr; was jetzt nicht auf die Platte kommt, ist dort nicht
wiederzubekommen.

```
bash INSTALLIEREN.sh
```

**Nicht mit `sudo` davor** — sonst gehören Programm, Modelle und Stimmen
hinterher `root`, und der Dienst kommt nicht an sie heran. Das Skript
fragt von sich aus nach dem Passwort, wenn es so weit ist, und legt dann
rund 13 GB unter `/opt/devarenu-vorrat` ab: die Python-Pakete, Torch,
alle Piper-Stimmen, die Spracherkennung und das Übersetzungsmodell.

Wer das Passwort nicht hat, kann trotzdem installieren — die Einrichtung
läuft durch, nur der Vorrat fehlt. Das Skript sagt es und nennt den
Befehl zum Nachholen.

- [ ] Nach der Einrichtung `./pruefen.sh` laufen lassen. Unter
      **Reparaturvorrat** muss stehen: *Vorrat vorhanden* und
      *Prüfsummen stimmen*. Steht dort *Kein Vorrat*, fehlt er — dann
      nachholen, **solange die Leitung noch steht**:

      ```
      sudo ./vorrat_bauen.sh
      ```

- [ ] Der Rechner darf erst ausgeliefert werden, wenn diese beiden
      Zeilen grün sind. Danach ist der Vorrat nicht mehr zu beschaffen.

## Selbsttest

- [ ] `.venv/bin/python selbsttest.py` — 0 Fehler.
- [ ] Die Zeile "Whisper rechnet auf cuda (float16)" muss dastehen.
      Steht dort `cpu`, ist etwas mit den CUDA-Bibliotheken; der Test
      meldet das jetzt rot, wenn eine Karte vorhanden ist.

## Dienst

- [ ] `./dienst.sh` — läuft durch, meldet "rechnet auf der Grafikkarte".
      Danach sagt `./pruefen.sh` dasselbe noch einmal, samt Adresse.
- [ ] **Neustart des Rechners.** Kommt der Dienst ohne Anmeldung von
      allein hoch? `systemctl status devarenu`, `journalctl -u devarenu -b`
- [ ] Nach dem Kaltstart: `./pruefen.sh` — `rechenwerk` muss
      `cuda (float16)` sein, nicht `cpu`. Das ist der Punkt, an dem sich
      zeigt, ob das Vorladen der CUDA-Bibliotheken ohne Sitzung greift.
- [ ] **Die Adresse in der Startausgabe.** `journalctl -u devarenu -b`
      nach dem Kaltstart: dort muss die LAN-Adresse stehen, nicht
      `127.0.0.1`. Kam sie erst verspätet, steht ein Nachtrag
      "Netz da nach Ns" im Journal — das ist der Normalfall auf einem
      Rechner, dessen Netz beim Start noch nicht fertig ist, und keine
      Störung. Steht dort "Nach 120s keine Netzwerkadresse gefunden",
      kommt der Rechner gar nicht ins Netz.
- [ ] Absturz-Neustart: `sudo systemctl kill -s KILL devarenu`, danach
      muss er nach etwa zehn Sekunden von allein wieder laufen.
- [ ] Kommt der Dienst ohne `SupplementaryGroups=audio` an `/dev/snd`?
      Auf Ubuntu vermutlich nicht, weil der Benutzer dort nicht in der
      Gruppe `audio` ist und die uaccess-ACL ohne Sitzung fehlt. Die Unit
      umgeht es; interessant ist es trotzdem.
- [ ] Stromausfall nachstellen: Stecker ziehen, wieder einschalten,
      nichts tippen. Läuft die Übersetzung?

## Tonquelle ohne Sitzung

**Der häufigste Grund, warum der Dienst keinen Ton bekommt.**

Der Rechner soll headless laufen, also ohne dass sich jemand anmeldet.
Genau dann gibt es keinen PulseAudio-Server. PortAudio ist auf Ubuntu
26.04 mit Pulse-Backend gebaut und versucht das als Erstes; schlägt es
fehl, kommt der Import von `sounddevice` gar nicht bis ALSA:

```
PulseAudio_Initialize: Can't connect to server
```

Bis 0.2.8 hat der Dienst daran abgebrochen und ist in eine
Neustartschleife gelaufen — auf einem Gemeinderechner 42 Mal. **Seit
0.2.9 läuft der Server weiter**, meldet die fehlende Tonquelle am Pult
und nimmt nichts auf. Das ist besser, aber immer noch kein Ton.

- [ ] Nach dem Einrichten `./pruefen.sh` laufen lassen. Unter **Ton**
      muss stehen: *PortAudio lädt*. Steht dort *PortAudio lädt nicht*,
      ist es dieser Fall.

- [ ] Dann in `/etc/systemd/system/devarenu.service` die vorbereitete
      Zeile einkommentieren und neu starten:

      ```
      Environment=PULSE_SERVER=
      ```
      ```
      sudo systemctl daemon-reload && sudo systemctl restart devarenu
      ./pruefen.sh
      ```

      Damit überspringt PortAudio das Pulse-Backend und nimmt ALSA.

- [ ] Hilft das nicht, ist der zweite Weg eine Nutzer-Unit mit
      `loginctl enable-linger <benutzer>`. Dann existiert eine Sitzung
      ohne Anmeldung, und PulseAudio läuft. Das ist aufwendiger und
      ordnet nicht gegen `ollama.service` — deshalb erst der Weg oben.

**Ungeprüft:** ob `PULSE_SERVER=` bei diesem PortAudio-Build genügt.
Auf dem Entwicklungsrechner läuft eine Sitzung, dort tritt der Fall
nicht auf. Wer das misst, trägt das Ergebnis hier ein.

## Tonquelle

- [ ] Am Pult unter Einrichtung: ist das Predigermikro in der Liste?
- [ ] Auswählen, hineinsprechen, schlägt der Balken aus?
- [ ] Rechner neu starten. Steht danach dasselbe Gerät da? `./pruefen.sh`
      zeigt unter Ton, was der Dienst tatsächlich offen hat, und ob das
      dem hinterlegten Namen entspricht. Weicht die Nummer ab, steht sie
      neben der hinterlegten — dann hat sich die Nummer verschoben und
      der Name hat es aufgefangen, genau dafür steht er drin.
- [ ] USB-Mikro einmal umstecken und neu starten: wird es über den Namen
      wiedergefunden? `./pruefen.sh` zeigt beide Nummern nebeneinander.
- [ ] **Keine Gerätenummer irgendwohin abtippen.** Die Zählungen des
      Dienstes und einer angemeldeten Sitzung sind verschiedene Welten,
      und zwar in beide Richtungen. Am selben Rechner zur selben Sekunde
      gemessen:

      | | Dienst, ohne Sitzung | Terminal, mit Sitzung |
      |---|---|---|
      | Nr. 0 | Auna Mic CM900 (hw:0,0) | USB Audio: - (hw:1,0) |
      | Anzahl | 13 | 7 |
      | Plugins | sysdefault, spdif, lavrate | pipewire, pulse, default |

      Zwei Ursachen überlagern sich: der Dienst hält das benutzte Mikrofon
      exklusiv offen, es fehlt der anderen Aufzählung deshalb ganz; und
      ohne Sitzung zeigt ALSA einen anderen Satz Plugin-Einträge. Ob dabei
      mehr oder weniger Geräte herauskommen, hängt davon ab, was gerade
      läuft — verlässlich ist nur, dass die Nummern **nicht** dieselben
      sind. Deshalb am Pult auswählen; dabei wird der Name mitgeschrieben,
      und der gilt in beiden Zählungen.

## Der Rechner als Router für das Saalnetz

**Nur von Hand, nur vor Ort, nur an der Tastatur des Rechners.** Nie über
`stick_update.sh`, nie über `bootstrap.sh`, nie über eine Fernsitzung:
Der Umbau stellt die Netzwerkkarte um und kappt damit genau die
Verbindung, über die man zusieht.

### Warum überhaupt

Ein WLAN ohne Internet wird von Handys gemieden. Android zeigt ein
Ausrufezeichen und wechselt nach ein paar Minuten von selbst zurück auf
die mobilen Daten — mitten im Gottesdienst, mitten im Satz. iOS öffnet
den kleinen Anmeldebrowser, und der schließt sich, sobald jemand die App
wechselt.

Dagegen hilft nur eines: Der Rechner beantwortet die Prüfadressen, mit
denen die Handys nach Internet fragen. Dafür muss er selbst DHCP und DNS
stellen — und damit ist er der Router.

**Kein NAT, kein Gateway, kein Weg nach draußen.** Der Saal bekommt kein
Internet und soll keines bekommen. Auch der Rechner selbst hat danach
keines mehr; Updates kommen über den Stick.

### Was vorher beim Systemhaus passiert

- [ ] Ein **Zugangspunkt** (Access Point), der am LAN hängt und nur WLAN
      macht. Kein Router, kein DHCP.
- [ ] **DHCP am Zugangspunkt ausschalten.** Der häufigste Fehler und der
      teuerste: Vergeben zwei Server Adressen, entscheidet der Zufall,
      welcher zuerst antwortet. Die Handys aus dem falschen Topf finden
      diesen Rechner nicht. `./pruefen.sh` meldet es, und am Pult steht
      es auch.
- [ ] Das **Mainboard-WLAN bleibt aus.** Die Intel AX201 macht als
      Zugangspunkt nur 2,4 GHz und ist bei acht bis zwölf Geräten am
      Ende. Ein Saal mit dreißig Zuhörern braucht einen richtigen
      Zugangspunkt.
- [ ] **Keine Router Advertisements** am Zugangspunkt. Sonst holen sich
      die Handys über IPv6 einen anderen DNS und fragen an diesem
      Rechner vorbei.
- [ ] `NETZ_RECHNER` in `config.py` auf den Namen dieses Rechners
      setzen. Leer heißt: Der Umbau läuft nirgends. Das ist Absicht —
      dasselbe Verzeichnis liegt auch auf dem Arbeitsrechner, auf dem
      Devarenu entsteht.
- [ ] `sudo ./vorrat_bauen.sh` **nach** dem Einrichten: Der Vorrat nimmt
      seit 0.2.10 auch `dnsmasq` als `.deb` mit. Vor Ort gibt es keine
      Leitung, über die es nachkommen könnte.

### Zwei Wege, die nur hier zu prüfen sind

Beides ließ sich auf dem Entwicklungsrechner **nicht** ausführen: dort
gibt es kein `apt`, und kein `sudo` ohne Passwortabfrage. Geprüft sind
jeweils nur die Fehlerwege — dass die Sache funktioniert, wenn sie
funktionieren soll, zeigt sich erst hier. Also beim Systemhaus, solange
noch eine Leitung steht und jemand danebensteht.

- [ ] **DHCP-Rundruf mit Wurzelrechten.**

      ```
      sudo ./dhcp_umschau.py <schnittstelle> 4
      ```

      Erwartet: eine Zeile `SERVER|<adresse>|<option114>` je antwortendem
      DHCP-Server, danach `ANZAHL|n`. Am Hausanschluss des Systemhauses
      muss genau einer auftauchen, nämlich dessen Router. Kommt
      `ANZAHL|0`, sendet oder empfängt der Rundruf nicht — dann meldet
      auch `netz_einrichten.sh` fälschlich „niemand verteilt Adressen"
      und `pruefen.sh` findet einen zweiten Server nie.

      Geprüft ist bisher: das Zerlegen einer Antwort, der Abgleich der
      Vorgangsnummer, OFFER gegen ACK, abgeschnittene Pakete, fehlende
      Rechte, unbekannte Schnittstelle. **Nicht geprüft: das Senden
      selbst.**

      Der Rundruf belegt nichts — es geht nur ein DISCOVER hinaus, nie
      ein REQUEST. Als Hardware-Adresse dient die der Schnittstelle
      selbst, damit keine Phantomeinträge in fremden Leasetabellen
      entstehen.

- [ ] **Systempakete in den Vorrat und zurück.**

      ```
      sudo ./vorrat_bauen.sh
      ls /opt/devarenu-vorrat/systempakete/*.deb
      sudo ./wiederherstellen.sh --systempakete
      systemctl is-enabled dnsmasq        # muss "disabled" sagen
      ```

      Erwartet: `dnsmasq` und `dnsmasq-base` liegen als `.deb` im
      Vorrat, `dpkg -i` spielt sie ein, und der Dienst ist danach
      **aus**. Läuft er, nimmt er auf einem Rechner ohne Umbau den Port
      53 weg — und damit dessen Namensauflösung.

      Geprüft ist bisher: kein `apt-get` vorhanden, keine `.deb` im
      Vorrat, kein `dpkg` vorhanden, fehlende Wurzelrechte. **Nicht
      geprüft: der Weg, auf dem es klappt.**

      Schlägt `apt-get --download-only` fehl, bricht `vorrat_bauen.sh`
      ab, statt einen unvollständigen Vorrat als fertig auszugeben.

### Der Umbau

```
sudo ./netz_einrichten.sh --trocken       nur zeigen, nichts schreiben
sudo ./netz_einrichten.sh                 einrichten
sudo ./netz_einrichten.sh --zuruecknehmen alles rückgängig
```

Vorher sieht das Skript nach, ob es überhaupt auf dem richtigen Rechner
steht: Name in `NETZ_RECHNER`, genau eine Leitung mit Stecker, kein WLAN
verbunden, keine virtuellen Brücken, NetworkManager führt die Karte, und
— mit `sudo` — ob hier schon jemand anders Adressen verteilt. Stimmt
etwas nicht, ändert es nichts und sagt, was. Mit `--trotzdem` lässt sich
das übergehen; dann aber ausdrücklich und auf eigene Gefahr.

Danach:

- Feste Adresse `10.0.0.1/24` auf der Karte am Zugangspunkt
- `dnsmasq` verteilt `10.0.0.50` bis `10.0.0.200`, Mietdauer 12 h
- Kein Gateway (Option 3 leer), DNS zeigt auf `10.0.0.1`
- DHCP-Option 114 auf `http://10.0.0.1/captive-api` (RFC 8910)
- Die Prüfadressen der Hersteller zeigen auf diesen Rechner, **alles
  andere bleibt unauflösbar**
- `ip_forward=0`, `ufw` lässt 53, 67, 80, 8000 und 22 im lokalen Netz
- `NETZ_ROUTER = True` in `config.py`

Der Dienst muss danach neu starten:

```
sudo systemctl restart devarenu
```

### Port 80

Die Prüfadressen der Hersteller fragen ausschließlich Port 80, und wer
`10.0.0.1` ins Handy tippt, meint auch Port 80. Der Server bleibt
trotzdem ein gewöhnlicher Benutzerprozess: Die Unit gibt ihm
`AmbientCapabilities=CAP_NET_BIND_SERVICE`, also genau das Recht, eine
Portnummer unter 1024 zu belegen, und sonst keines. Port 8000 bleibt
daneben bestehen.

Fehlt die Zeile, läuft der Server auf 8000 weiter und sagt es beim
Start. Ein Ausfall ist das nicht — aber die Handys melden dann „kein
Internet".

### Was die Handys zu sehen bekommen

| Gerät | Prüfung | Ergebnis |
|---|---|---|
| iOS | nur HTTP | gilt als online |
| Android | HTTP **und** HTTPS | Ausrufezeichen bleibt |
| Windows | HTTP | gilt als online |

Androids HTTPS-Prüfung ist ohne Zertifikat nicht zu bestehen. Das
Ausrufezeichen bleibt also, aber das Handy verlässt das Netz nicht mehr
von selbst. **Die mobilen Daten müssen trotzdem aus** — das steht auf
der Beamer-Seite und auf der Zuhörerseite, deutsch und englisch.

### Prüfen

```
./pruefen.sh              Abschnitt „Saalnetz"
sudo ./pruefen.sh         zusätzlich der DHCP-Rundruf
```

Geprüft werden: läuft `dnsmasq`, liegt die Adresse auf der Karte, ist
`ip_forward` aus, steht Option 114 in der Konfiguration, antwortet der
DNS richtig (Prüfnamen auf uns, alles andere NXDOMAIN), antworten die
Prüfadressen byte-genau, und — mit `sudo` — verteilt außer uns noch
jemand Adressen.

Ohne `sudo` bleibt der DHCP-Rundruf aus; stattdessen meldet der
laufende Server, ob schon ein Gerät mit einer fremden Adresse
angekommen ist. Das ist ein Hinweis, kein Beweis: Wer eine fremde
Adresse hat und uns deshalb gar nicht erreicht, fällt dabei nicht auf.

### Abnahme vor Ort, mit echten Handys

Vom Rechner aus sieht alles gut aus, auch wenn nichts geht. Diese Liste
wird **mit zwei Handys in der Hand** abgearbeitet, im Saal, nicht am
Schreibtisch. Ein Android (möglichst Samsung — die eigene
WLAN-Verwaltung ist dort am strengsten) und ein iPhone.

- [ ] `sudo ./pruefen.sh`, Abschnitt „Saalnetz": alles grün, besonders
      „nur dieser Rechner verteilt Adressen".
- [ ] **Android, mobile Daten AN.** QR scannen, verbinden. Erwartet:
      verbindet, Ausrufezeichen am WLAN-Zeichen bleibt. Seite öffnen,
      Sprache wählen, hören.
- [ ] **Android, mobile Daten AUS.** Dasselbe noch einmal. Das ist der
      Zustand, den die Zuhörer haben sollen.
- [ ] **iPhone, mobile Daten AN und AUS.** Erwartet: kein
      Anmeldebrowser. Öffnet sich doch einer, antwortet irgendwo eine
      Umleitung — das gehört gemeldet, nicht weggeklickt.
- [ ] **Fünf Minuten Bildschirm aus**, bei beiden Handys, mit
      laufender Wiedergabe. Erwartet: Ton läuft weiter, Verbindung
      bleibt. Das ist die Prüfung, an der ein WLAN ohne Internet sonst
      scheitert.
- [ ] Danach am Pult nachsehen: steht dort eine Warnung über einen
      zweiten DHCP-Server?
- [ ] `10.0.0.1/pult` **ohne** `http://` in die Adresszeile tippen.
      Erwartet: die Seite kommt. Kommt stattdessen eine Suchmaschine
      oder „Seite nicht gefunden", hat das Handy den Eintrag als
      Suchbegriff genommen — dann gilt das als Befund und kommt in die
      Anleitung fürs Pult.
- [ ] Beamer-Seite `http://10.0.0.1/qr` am Beamer: sind beide Codes aus
      der letzten Reihe noch scharf, steht „Mobile Daten ausschalten"
      lesbar da?
- [ ] Das WLAN-Passwort am Pult mit dem am Zugangspunkt vergleichen.
      Stimmen sie nicht überein, trägt der QR-Code ein falsches
      Passwort und niemand kommt ins Netz.

Offen und **nicht** vorher zu beantworten: ob die Captive-Portal-API
(Option 114) die Anzeige „kein Internet" überhaupt verändert. Der
Standard regelt Anmeldepflicht, nicht Erreichbarkeit. Was die Geräte
tatsächlich anzeigen, zeigt erst dieser Termin — in beiden Fällen
bleiben die Prüfadressen wirksam.

### Wenn dnsmasq fehlt

```
sudo ./wiederherstellen.sh --systempakete
```

Holt es aus dem Reparaturvorrat. Danach liegt es bereit, ist aber aus —
eingeschaltet wird es allein von `netz_einrichten.sh`.

## Im Gottesdienst

- [ ] Einmessen mit dem echten Prediger am echten Mikrofon.
- [ ] Übersetzung **nicht** über Lautsprecher im selben Raum. Kopfhörer
      am Handy. Sonst hört das Mikrofon die eigene Ausgabe und übersetzt
      sie erneut.
- [ ] WLAN-Name und Passwort am Pult eintragen, QR-Seite am Beamer
      prüfen.
- [ ] Ein Handy durchspielen: QR scannen, Sprache wählen, hören.
      **Mit einem echten Handy, nicht vom Rechner aus.** Sperrt eine
      Firewall den Port, antwortet der Server auf sich selbst und auf
      seine eigene LAN-Adresse einwandfrei — nur das Handy kommt nicht
      durch. `./pruefen.sh` sagt es vorher, `INSTALLIEREN.sh` fragt beim
      Einrichten danach. Auf Ubuntu Server ist `ufw` ab Werk aus; wer ihn
      einschaltet, muss Port 8000 fürs lokale Netz freigeben.

## Aktualisieren

- [ ] `./aktualisieren.sh` einmal ausführen. `zustand.json` muss danach
      unverändert sein — das Skript prüft und meldet es selbst.

## Aktualisieren ohne Netz, per USB-Stick

Die meisten Gemeinderechner haben kein Internet. `./aktualisieren.sh`
braucht aber `git fetch` und ruft `einrichten.sh` auf, das pip, Ollama
und Hugging Face erwartet — beides geht offline nicht. Dafür gibt es den
Stick.

### Am Rechner in der Gemeinde

- [ ] Stick einstecken. Sonst nichts.
- [ ] Am Pult unter **Einrichtung** steht, was passiert ist: geprüft und
      vorgemerkt, eingespielt, oder warum nicht.
- [ ] Der Stick kann sofort wieder abgezogen werden. Er wird nur gelesen,
      nie beschrieben, und ist nach ein paar Sekunden ausgehängt.
- [ ] Eingespielt wird **nicht sofort**, sondern wenn die Übersetzung
      angehalten ist und zwanzig Minuten lang niemand mehr zugehört hat.
      Mitten im Gottesdienst passiert nichts. Wer es eilig hat, drückt
      unter Einrichtung auf **Jetzt einspielen**; das dauert dann bis zu
      eine Minute.
- [ ] Geht etwas schief, kommt der alte Stand von allein zurück und der
      Dienst läuft weiter. Am Pult steht dann, welche Fassung wieder
      läuft.

Ein Stick ohne `upd-dev.txt` löst gar nichts aus — der Fotostick der
Gemeinde darf also bedenkenlos in denselben Rechner.

### Beim ersten Mal

Rechner mit einer Fassung vor 0.2.1 kennen das Verfahren noch nicht. Bei
ihnen einmal von Hand:

    sudo bash /pfad/zum/stick/bootstrap.sh

Dabei wird ein Fingerabdruck angezeigt. Er muss mit dem übereinstimmen,
den Sie **auf einem anderen Weg als über den Stick** bekommen haben —
fragen Sie nach, am Telefon oder persönlich. Stimmt er nicht: abbrechen.
Das ist der einzige Moment, in dem ein Mensch das Vertrauen herstellt;
danach prüft der Rechner selbst.

Neu aufgesetzte Rechner brauchen das nicht, `./dienst.sh` richtet alles
gleich mit ein.

### Was der Rechner prüft, bevor er etwas anfasst

Der Reihe nach, und beim ersten Nein ist Schluss:

1. Ist das Bundle unversehrt?
2. Ist das Tag mit einem Schlüssel aus `schluessel.erlaubt` signiert?
   Geprüft wird gegen die Liste **auf dem Rechner**, nie gegen die auf
   dem Stick — sonst brächte ein Stick einfach seinen eigenen Schlüssel
   mit.
3. Ist die Fassung überhaupt neuer als die laufende?
4. Liegen lokale Änderungen im Ordner? Dann nichts anfassen.
5. Ist die Übersetzung angehalten und ruhig?
6. Liegen Sprachmodell und Stimmen da? Das Bundle bringt sie nicht mit,
   und ohne Netz lädt nichts nach.
7. Braucht das Update neue Pakete, und sind sie auf dem Stick?

Erst danach wird der Dienst neu gestartet. Meldet er sich nicht binnen
zwei Minuten mit der neuen Fassung, geht alles zurück.

### Nachsehen

    ./pruefen.sh                     Abschnitt „Fassung"
    ./stick_update.sh --stand        nur die Statusdatei
    journalctl -u devarenu-update    was der Timer gemacht hat
    journalctl -u 'devarenu-stick@*' was beim Einstecken passierte

## Wenn am Pult „Warte auf …" steht

Der Server öffnet **nur** das Mikrofon, das unter Einrichtung ausgewählt
wurde — erkannt am Namen, nicht an der Nummer. Ist es beim Einschalten
noch nicht da, wartet er darauf und nimmt bewusst kein anderes.

Das ist Absicht. Vorher griff er in diesem Fall auf die alte Nummer
zurück, und die zeigte dann auf den Onboard-Eingang: der Rechner nahm
scheinbar auf, meldete keinen Fehler, und es kam nie Ton. Das fiel erst
im Gottesdienst auf.

- [ ] **Steht die Meldung nur kurz nach dem Einschalten?** Dann ist alles
      in Ordnung. USB braucht länger als der Dienst; sobald das Mikrofon
      aufgezählt ist, greift er von allein zu, meist in ein paar Sekunden.
- [ ] **Bleibt sie stehen?** Dann ist das Gerät wirklich nicht da. Kabel
      prüfen. Ist dauerhaft ein anderes Mikrofon im Einsatz, unter
      Einrichtung auswählen — damit ist das Warten beendet.

Der Kartenindex im Namen (`… (hw:4,0)`) darf sich verschieben, danach
wird ebenfalls gesucht. Zwei baugleiche Mikrofone am selben Rechner sind
so allerdings nicht zu unterscheiden.

### „Der Tonstrom war tot und wurde neu geöffnet."

Der Server überwacht, ob noch Tonblöcke ankommen. Bleiben sie aus, öffnet
er den Strom von allein neu; die Übersetzung läuft weiter, es fehlt
weniger als eine Sekunde.

**Stille löst das nicht aus.** Auch bei völliger Ruhe kommen Blöcke an,
nur leise. Gebet, Lieder und Pausen sind davon nicht betroffen.

Die Meldung verschwindet nach einer Minute von selbst — sie sagt, dass
etwas war, nicht dass etwas ist. Nachlesen im Journal:

    journalctl -u devarenu | grep -i tonstrom

Häuft sie sich, liegt es meist am USB-Kabel oder an einem Hub ohne
eigene Stromversorgung.
