# Aufstellen auf dem Gemeinderechner

Was sich nur dort prüfen lässt. Entwickelt und getestet wurde auf
CachyOS mit angemeldeter Sitzung; der Zielrechner ist Ubuntu Server mit
nachinstalliertem KDE, X11, headless im Betrieb, ohne angemeldeten
Benutzer.

Abhaken, was durchgelaufen ist.

**Zuerst `bash pruefen.sh`.** Das geht die maschinell prüfbaren Punkte von
allein durch und sagt bei jedem, was zu tun ist. Es läuft auch, wenn der
Dienst gar nicht steht — dann zeigt es zusätzlich, woran er scheitert.
Die damit abgedeckten Punkte sind unten mit (pruefen.sh) gekennzeichnet.

```
bash pruefen.sh                    ansehen
bash pruefen.sh > bericht.txt 2>&1 zum Verschicken
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

- [ ] Nach der Einrichtung `bash pruefen.sh` laufen lassen. Unter
      **Reparaturvorrat** muss stehen: *Vorrat vorhanden* und
      *Prüfsummen stimmen*. Steht dort *Kein Vorrat*, fehlt er — dann
      nachholen, **solange die Leitung noch steht**:

      ```
      sudo bash vorrat_bauen.sh
      ```

- [ ] Der Rechner darf erst ausgeliefert werden, wenn diese beiden
      Zeilen grün sind. Danach ist der Vorrat nicht mehr zu beschaffen.

## Selbsttest

- [ ] `.venv/bin/python selbsttest.py` — 0 Fehler.
- [ ] Die Zeile "Whisper rechnet auf cuda (float16)" muss dastehen.
      Steht dort `cpu`, ist etwas mit den CUDA-Bibliotheken; der Test
      meldet das jetzt rot, wenn eine Karte vorhanden ist.

## Dienst

- [ ] `bash dienst.sh` — läuft durch, meldet "rechnet auf der Grafikkarte".
      Danach sagt `bash pruefen.sh` dasselbe noch einmal, samt Adresse.
- [ ] **Neustart des Rechners.** Kommt der Dienst ohne Anmeldung von
      allein hoch? `systemctl status devarenu`, `journalctl -u devarenu -b`
- [ ] Nach dem Kaltstart: `bash pruefen.sh` — `rechenwerk` muss
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

- [ ] Nach dem Einrichten `bash pruefen.sh` laufen lassen. Unter **Ton**
      muss stehen: *PortAudio lädt*. Steht dort *PortAudio lädt nicht*,
      ist es dieser Fall.

- [ ] Dann in `/etc/systemd/system/devarenu.service` die vorbereitete
      Zeile einkommentieren und neu starten:

      ```
      Environment=PULSE_SERVER=
      ```
      ```
      sudo systemctl daemon-reload && sudo systemctl restart devarenu
      bash pruefen.sh
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
- [ ] Rechner neu starten. Steht danach dasselbe Gerät da? `bash pruefen.sh`
      zeigt unter Ton, was der Dienst tatsächlich offen hat, und ob das
      dem hinterlegten Namen entspricht. Weicht die Nummer ab, steht sie
      neben der hinterlegten — dann hat sich die Nummer verschoben und
      der Name hat es aufgefangen, genau dafür steht er drin.
- [ ] USB-Mikro einmal umstecken und neu starten: wird es über den Namen
      wiedergefunden? `bash pruefen.sh` zeigt beide Nummern nebeneinander.
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
      diesen Rechner nicht. `bash pruefen.sh` meldet es, und am Pult steht
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
- [ ] `sudo bash vorrat_bauen.sh` **nach** dem Einrichten: Der Vorrat nimmt
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
      sudo bash vorrat_bauen.sh
      ls /opt/devarenu-vorrat/systempakete/*.deb
      sudo bash wiederherstellen.sh --systempakete
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
sudo bash netz_einrichten.sh --trocken       nur zeigen, nichts schreiben
sudo bash netz_einrichten.sh                 einrichten
sudo bash netz_einrichten.sh --zuruecknehmen alles rückgängig
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
bash pruefen.sh              Abschnitt „Saalnetz"
sudo bash pruefen.sh         zusätzlich der DHCP-Rundruf
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

- [ ] `sudo bash pruefen.sh`, Abschnitt „Saalnetz": alles grün, besonders
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
sudo bash wiederherstellen.sh --systempakete
```

Holt es aus dem Reparaturvorrat. Danach liegt es bereit, ist aber aus —
eingeschaltet wird es allein von `netz_einrichten.sh`.

## Sprechtempo je Stimme

### Warum die Übersetzung schneller spricht als der Prediger

Eine Übersetzung braucht gesprochen fast immer länger als das Original.
Ohne Ausgleich wächst der Rückstand über die Predigt hinweg — unabhängig
davon, wie schnell die Grafikkarte ist. Piper spricht deshalb schneller.

Bis 0.2.10 stand dafür **eine** Zahl in `config.py`, ausgelegt auf
Russisch und Persisch. Das war zu grob: gemessen wurde je Sprache, aber
mit genau einer Stimme je Sprache — der Sprachwert war in Wahrheit der
Wert dieser Stimme. Bei mehreren Stimmen fällt es auf:

| Sprache | Stimme A | Stimme B | Stimme C | Spannweite |
|---|---|---|---|---|
| Portugiesisch | 1,04 | 1,45 | 1,37 | **0,41** |
| Spanisch | 1,02 | 1,31 | 1,27 | **0,29** |
| zwischen den Sprachmitteln | | | | **0,01** |

Seit 0.2.11 hängt das Tempo deshalb an der **Stimme**. Französisch
wurde vorher um volle 24 Prozentpunkte zu stark beschleunigt und klang
gehetzt, ohne dass etwas gewonnen war.

### Was am Pult davon zu sehen ist

Nichts — und das ist Absicht. Das Tempo stellt sich selbst ein.
`bash pruefen.sh` zeigt im Abschnitt **Sprechtempo**, welcher Wert je
eingeschalteter Sprache tatsächlich gilt und woher er kommt: gemessene
Stimme, Sprache als Rückfall, oder Vorgabe.

### Drei Sprachen stoßen an die Obergrenze

Arabisch, Niederländisch und Serbisch bräuchten mehr als Faktor 1,6, um
den Rückstand vollständig aufzuholen. Über 1,6 fällt die
Verständlichkeit — gemessen in der Reihe 0.2.5 — deshalb wird dort
gedeckelt. Diese drei Sprachen hinken im Gottesdienst hinterher. Das ist
kein Fehler, sondern die bewusste Wahl: lieber etwas später und
verständlich als pünktlich und unverständlich.

Wer es trotzdem probieren will, hebt `TEMPO_MAX` in `config.py` — und
hört sich das Ergebnis vorher an.

### Wenn alles hinterherhängt

```
TEMPO_GLOBAL = 1.05    in config.py
```

Der Notfallhebel. Er hebt oder senkt alle Sprachen auf einmal, Vorgabe
1.0. Gedacht für den Sonntag, an dem keine Zeit ist, einzelne Stimmen
nachzumessen. `bash pruefen.sh` meldet, wenn er nicht auf 1,00 steht —
denn als Dauerzustand ist er der falsche Weg.

### Nachmessen

```
python laengenfaktor.py --stimmen-laden --ziel-ordner ergebnisse/stimmprobe/voices
python laengenfaktor.py --je-stimme
```

Der erste Befehl holt die Stimmen — **nicht** nach `voices/`: dort steht
nur, was ausgeliefert wird, und was dort liegt, bietet das Pult an. Der
zweite misst und schreibt nach `messungen/laengenfaktor_stimmen.json` —
die Datei liegt im Repo, denn sie ist der Beleg für jede Zahl in der
Tempotabelle. Die Übersetzungen selbst bleiben unter `ergebnisse/`:
sie enthalten Predigttext, und das Repo ist öffentlich.

Zwei Dinge, die man dabei falsch machen kann:

- **Bezugsgröße.** Die Datei nennt sie ausdrücklich: `gegen_deutsch`,
  also die Dauer der deutschen Piper-Ausgabe desselben Satzes. Daneben
  steht `gegen_original`, die echte Sprechdauer des Predigers. Die
  beiden Reihen dürfen nicht gemischt werden.
- **Piper würfelt.** Der Dauervorhersager von VITS ist stochastisch:
  derselbe Satz, dieselbe Stimme, zweimal gesprochen, ergibt bis zu
  10 % verschiedene Längen. Gemessen wird deshalb mit
  `--noise-w-scale 0`. Ohne das kam die deutsche Stimme gegen sich
  selbst auf 1,017 statt 1,000 — ein Versatz, der sonst in jedem
  abgeleiteten Wert steckt. Im Betrieb bleibt der Zufall an; er ist
  einer der Gründe für den Aufschlag von sechs Prozent.

## Sprachen ohne geprüftes Fachwortverzeichnis

Eine Sprache hat drei Zustände, und sie sehen am Pult verschieden aus:

| Zustand | Am Pult | Beim Zuhörer |
|---|---|---|
| geprüft | normal | normal |
| Glossar da, ungeprüft | gestrichelt | gestrichelt, Punkt |
| gar kein Glossar | gepunktet | gepunktet, Kreis |

Von 21 Sprachen haben vier ein Fachwortverzeichnis. Wer Rumänisch
dazuschaltet, bekommt eine Übersetzung ohne jede Terminologie: Sabbat,
Gemeinde und Vereinigung werden wörtlich übertragen.

**Beim Einschalten legt der Server einen Hinweis in den Briefkasten des
Pults** — mit ⚙ und Absender „Devarenu", damit er nicht wie eine
Zuschrift aus dem Saal aussieht. Kein Fenster springt auf: am Pult darf
im Gottesdienst nichts aufpoppen.

Der Hinweis bleibt stehen, bis er einmal geöffnet wurde. Danach fragt
dieselbe Sprache nicht wieder — auch nach einem Neustart nicht, die
Quittierung steht in `zustand.json`. An der Sprache selbst bleibt die
Zeile „experimentell, mehr dazu in der Nachricht".

In der Nachricht steht die Bitte um Kontakt. Gesucht wird jemand, der
die Sprache als Muttersprache spricht und Deutsch oder Englisch
versteht, rund eine Stunde Zeit für eine Liste mit 93 Begriffen. Das
ist der einzige Weg, wie aus einer experimentellen Sprache eine
geprüfte wird.

## Was nicht im Protokoll steht

Der gesprochene Satz geht **nicht** ins Journal — nur seine Länge:

```
[  42]  3.2s Ton, STT 0.12s, gesamt 3.44s | 67 Z.
```

Dasselbe gilt für Zuschriften aus dem Saal und für die Personennamen
aus dem Predigtmanuskript. Bis 0.2.13 stand das alles im Klartext da.

Zur Fehlersuche lässt es sich am Pult unter *Einrichtung* einschalten
(*Mitschrift im Protokoll*). Der Schalter steht in `zustand.json`,
nicht in `config.py` — eine Änderung an einer versionierten Datei ließe
jedes Update abbrechen. Solange er an ist, meldet ihn der Systemcheck.

Damit der Fehlerbericht überhaupt etwas Brauchbares zeigen kann, setzt
der Server seinen Warnungen `<4>` und seinen Fehlern `<3>` voran —
systemd liest das als Stufe. Nötig ist das, weil systemd sonst
**alles** auf Stufe 6 legt, stdout wie stderr; gemessen. Die
Segmentzeilen bekommen die Marke **nicht**, und darum kann Mitschrift
nie auf Warnstufe erscheinen. Genau ab dort sammelt der Bericht.

## Im Betrieb kein Internet, für die Wartung ein Hotspot

Im Gottesdienst hat der Rechner **kein Netz nach draußen**, und nichts
in Devarenu setzt eines voraus:

- Updates gehen **immer** per USB-Stick. Online ist eine Abkürzung,
  keine Voraussetzung.
- Kaputtes wird aus dem Reparaturvorrat wiederhergestellt.
- Die Bedienungsanleitung liegt fertig gebaut im Ordner.

Für die **Wartung** schaltet jemand vor Ort einen Handy-Hotspot ein.
Der Rechner verbindet sich per WLAN, dann geht RustDesk, und ein Update
lässt sich abkürzen. Das ist die Ausnahme, nicht der Normalfall — nach
der Wartung wird der Hotspot getrennt.

`bash pruefen.sh` meldet ein verbundenes WLAN als **Wartungszugang
aktiv**. Kein Fehler, nur eine Lagemeldung: wer sie sonntags liest,
weiß, dass der Hotspot noch läuft.

**Auf dem WLAN wird nichts freigegeben** — weder das Pult noch sonst
etwas. RustDesk baut seine Verbindung selbst nach draußen auf und
braucht keinen offenen Port.

Zwischen WLAN und Saalnetz wird nie geleitet: `ip_forward` bleibt aus,
und alle Freigaben hängen an der Kabelkarte zum Zugangspunkt.

## Von 0.2.11 auf 0.2.12 — die Schritte am Gemeinderechner

> **Überholt.** Der Rechner geht in einem Zug auf 0.3.0, siehe
> [Von 0.2.11 direkt auf 0.3.0](#von-0211-direkt-auf-030--der-weg-des-helfers).
> Dieser Abschnitt bleibt stehen, weil er erklärt, **warum** der Ordner
> verändert ist und was `dienst.sh` tut — beides braucht man, wenn
> unterwegs etwas klemmt.

Der Rechner steht mit einer geänderten `config.py` da: `netz_einrichten.sh`
hatte dort bis 0.2.11 `NETZ_ROUTER = True` eingetragen. Deshalb bricht
jedes Update ab. Das muss von Hand aufgelöst werden — **einmal**, danach
nie wieder, weil 0.2.12 nicht mehr in versionierte Dateien schreibt.

Außerhalb eines Gottesdienstes, an Tastatur und Bildschirm. Die Shell
ist `fish`.

**1. Nachsehen, was abweicht**

```fish
cd ~/Devarenu
git status --short
git diff --stat
```

Erwartet werden `config.py` und `firewall.sh`. Etwas anderes? Dann erst
ansehen, bevor es verworfen wird.

**2. Verwerfen**

```fish
git checkout -- config.py firewall.sh
git status
```

`git status` muss jetzt schweigen. Ab hier bis Schritt 4 beantwortet der
Server die Prüfadressen nicht — die Handys würden „kein Internet"
melden. Deshalb nicht vor einem Gottesdienst anfangen.

**3. Einspielen — zwei Wege**

`requirements.txt` ist gegenüber 0.2.11 **unverändert**. Der Stick
braucht also keine neuen Wheels; ein Bundle genügt.

*(a) Ohne Internet — der Normalfall.* Stick einstecken:

```fish
sudo systemctl start devarenu-stick@dev.service
journalctl -u 'devarenu-stick@*' -n 40 --no-pager
```

*(b) Mit Wartungs-Hotspot.* Jemand vor Ort schaltet den Hotspot ein,
der Rechner verbindet sich, dann geht RustDesk. Die Schritte 1 und 2
lassen sich darüber erledigen, und statt des Sticks genügt:

```fish
bash aktualisieren.sh
```

Der Stick geht auch dann. Nach der Wartung den Hotspot trennen:

```fish
nmcli con down "<name des hotspots>"
```

**4. Die Dienste neu schreiben**

**Das wird leicht übersehen:** Kein Update schreibt die systemd-Units
neu. Weder `stick_update.sh` noch `aktualisieren.sh` noch
`einrichten.sh` fassen sie an — das tut allein `dienst.sh`, und das
läuft sonst nur bei der Ersteinrichtung. Eine geänderte Vorlage liegt
also im Ordner und wirkt nicht.

0.2.12 ändert zwei davon (`ExecStart` läuft jetzt über `/bin/bash`,
damit es nicht am Ausführungsrecht hängt). Also einmal:

```fish
sudo bash dienst.sh
```

`bash pruefen.sh` meldet es künftig von selbst, wenn eine installierte
Unit von ihrer Vorlage abweicht.

**5. Neu starten und nachsehen**

```fish
sudo systemctl restart devarenu
bash pruefen.sh
```

0.2.12 erkennt beim ersten Start am System, dass der Umbau läuft, und
legt `netz.json` selbst an. `NETZ_ROUTER` muss niemand nachtragen.

**6. Das Netz neu einrichten — einmalig**

Der Umbau von 0.2.11 liegt noch an den alten Stellen. `netz_einrichten.sh`
räumt sie auf: die alte `/etc/dnsmasq.d/devarenu.conf`, die von Hand
angehängte `conf-dir`-Zeile in `/etc/dnsmasq.conf` (eine Sicherung bleibt
als `.devarenu-vorher` liegen) und den von Hand angelegten systemd-Zusatz.

```fish
sudo bash netz_einrichten.sh --trocken
sudo env DEVARENU_TROTZDEM=ja bash netz_einrichten.sh
```

Den Namen des Rechners vorher eintragen, falls noch nicht geschehen:

```fish
bash netz_einrichten.sh --rechner-eintragen
```

**7. Prüfen, dass kein Ordnungszyklus mehr da ist**

```fish
journalctl -b | grep -i "ordering cycle"
systemd-analyze verify dnsmasq.service
```

Beide sollen nichts ausgeben. Der alte Zusatz ordnete dnsmasq *nach*
`network-online.target`, während der Unit des Pakets *davor* sagt — ein
Zyklus, den systemd willkürlich auflöst. Der neue Zusatz verzichtet auf
die Ordnung ganz; `bind-dynamic` holt sich die Karte selbst.

**8. Firewall**

```fish
sudo ufw status numbered
```

Stehen sollen nur noch Regeln `on enp5s0` für 53, 67, 80 und 8000.
Fremde Regeln (KDE Connect) bleiben unangetastet; alte Devarenu-Regeln
räumt der Umbau selbst ab. Auf dem WLAN steht nichts.

**9. dnsmasq in den Vorrat — ein paar Megabyte, nicht vierzehn Gigabyte**

Der vorhandene Vorrat kennt `dnsmasq` noch nicht: auf Ubuntu gebaut,
und dort meldete das Skript „kein apt-get". Ergänzen lässt sich das,
ohne alles neu zu laden — wichtig, wenn die Leitung ein Handy-Hotspot
ist:

```fish
sudo bash vorrat_bauen.sh --nur-systempakete
bash vorrat_bauen.sh --pruefen
```

Stimmen, Modelle und Wheels bleiben unangetastet; Prüfsummen und
Etikett werden nachgezogen. Die Fassung im Etikett bleibt bewusst auf
dem alten Stand — geladen wurden nur Systempakete, die Wheels gehören
weiter zur alten Fassung.

**10. Ollama auf der Grafikkarte**

Das Arch-Paket `ollama` ist **CPU-only** — es hängt nur an libgcc,
libstdc++ und glibc. Die Beschleunigung ist ein Zusatzpaket:

```fish
sudo pacman -S ollama-cuda
sudo systemctl restart ollama
```

Auf dem Gemeinderechner kam Ollama vermutlich über das Installierskript
von ollama.com (`/usr/local/bin/ollama`, Modelle unter
`/usr/share/ollama`). Dann ist nichts zu tun — das Skript bringt CUDA
selbst mit. `bash pruefen.sh` meldet es, wenn das Modell doch auf der
CPU rechnet: es läuft dann, nur zu langsam, und ohne jede
Fehlermeldung.

Den Modellpfad nimmt keines der Skripte mehr an. Ermittelt wird er in
`systemcheck.ollama_ablage()` — erst `OLLAMA_MODELS`, dann die
Umgebung des Dienstes, erst zuletzt die üblichen Orte.

## Der Updater, zweigeteilt

Seit 0.2.13 besteht das Update aus zwei Hälften.

**Der Kern** (`stick_update.sh`) trifft nur zwei Arten von
Entscheidungen: **Vertrauen** — ist das Bundle heil, ist der Tag mit
einem Schlüssel aus dem *installierten* `schluessel.erlaubt` signiert,
ist die Fassung neuer — und **Rettung**, also wie der Rechner
zurückkommt, wenn etwas schiefgeht. Beides darf nicht von Code
abhängen, den ein Stick mitbringt. Der Kern soll sich praktisch nie
ändern.

**Die Logik** (`aktualisierung.sh`) macht alles andere: vorspulen,
große Teile, Pakete, Dienste, Gesundheitscheck, Aufräumen. Sie liegt im
Repo und wird **aus dem geprüften Tag** ausgeführt — nie aus Dateien
vom Stick. Ein Fehler darin lässt sich mit dem nächsten Update beheben.
Stünde er im Kern, müsste jemand hinfahren.

Ausgepackt wird über die geprüfte Objekt-SHA aus `refs/stick/vX`,
**nie über den Tagnamen**. Ein gleichnamiger lokaler Tag würde sonst
etwas Ungeprüftes unterschieben — nachgewiesen:

```
refs/stick/v9.9.9 -> aa3876ef   (geprüft)
Tag v9.9.9        -> 7d0a1fbe   (lokal überschrieben)

git archive v9.9.9            nimmt: 7d0a1fbe   ← das Gefälschte
git archive refs/stick/v9.9.9 nimmt: aa3876ef   ← das Geprüfte
```

### Was der Rückfall zurückholt

| | wie |
|---|---|
| Code | `git reset --hard` auf den alten Stand |
| venv | Symlink zurück aufs alte (`.venv-a` / `.venv-b`) |
| Dienste | aus der Sicherung, dann `daemon-reload` |
| `zustand.json`, `netz.json` | aus der Sicherung, **nur wenn geändert** |
| große Teile | das Beiseitegelegte zurück |

**venvs werden nie verschoben.** In einem venv stehen die Pfade in den
Skripten; ein verschobenes startet nicht. Deshalb liegen beide im
Projektordner als `.venv-a` und `.venv-b`, und `.venv` ist nur der
Verweis aufs aktive. Das alte fällt erst weg, wenn der Gesundheitscheck
steht.

### Zwei Ablagen

```
<projekt>/update/              was das Pult liest: bereit, stand, jetzt
/var/lib/devarenu/updates/     Nutzlast und Sicherungen, 700 / 600
```

Die zweite gehört der Wurzel allein: darin liegt eine Kopie von
`zustand.json`, und die enthält das WLAN-Passwort der Gemeinde.

### Große Teile

`teile.json` nennt für jede Datei Pfad, Größe und Prüfsumme —
Sprachmodell, Spracherkennung, Stimmen. Die Dateien selbst liegen nicht
im Repo; zusammen sind es rund vierzehn Gigabyte.

```
python teile.py --erfassen     teile.json aus dieser Platte bauen
python teile.py --pruefen      liegt alles da, und stimmt es?
```

Vor dem Einspielen wird geprüft, ob alles Nötige auf dem Stick liegt
und ob der Platz reicht. Fehlt etwas, wird **gar nichts** geändert.
Alte Teile bleiben liegen, bis der Gesundheitscheck steht.

Der Ollama-Ort wird nicht angenommen, sondern über
`systemcheck.ollama_ablage()` erfragt.

### Einen Stick bauen

```
bash stick_bauen.sh /run/media/<name>/STICK               nur Code
bash stick_bauen.sh /run/media/<name>/STICK --von v0.2.12  was sich änderte
bash stick_bauen.sh /run/media/<name>/STICK --voll         alles
```

Ohne `--von` oder `--voll` sind **keine** großen Teile dabei. Das ist
der Normalfall — die meisten Updates ändern nur Code.

**FAT32 und große Teile gehen nicht zusammen.** Auf FAT32 passt keine
Datei über 4 GB; das Sprachmodell allein ist größer. Mit `--von` oder
`--voll` bricht der Bau auf einem FAT32-Stick ab und sagt, was zu tun
ist. Ohne große Teile ist FAT32 unproblematisch.

> **Noch nicht gebaut, für später vorgemerkt.** Statt FAT32 abzulehnen,
> große Dateien immer in Stücke unter 4 GB teilen, sie auf dem
> Zielrechner wieder zusammensetzen und gegen die `sha256` aus der
> Teileliste prüfen. Dann ist das Dateisystem des Sticks egal, und ein
> halb kopierter Stick fällt beim Prüfen auf statt vor Ort. Solange das
> nicht da ist, gilt der Abbruch oben.

### Einen Stick als ZIP verschicken

Wenn niemand vor Ort einen Stick bespielen kann — oder der Stick erst
beim Helfer ankommt:

```
bash stick_bauen.sh --zip ~/Devarenu-Stick-v0.3.0.zip
```

Kein echter Stick nötig. Die Dateien liegen im ZIP **ganz oben**, nicht
in einem Unterordner. Das ist Absicht: Windows entpackt in einen Ordner,
der wie das ZIP heißt, und genau dieser eine Ordner darf unverändert auf
den Stick. Der Rechner sucht `upd-dev.txt` eine Ebene tief und findet
ihn dort. Läge im ZIP schon ein Unterordner, wären es zwei Ebenen — und
der Rechner meldete „kein Update-Stick".

**Auf dem Stick darf nur ein Update-Ordner liegen.** Sind es zwei — ein
alter vom letzten Mal —, entschiede die Reihenfolge des Dateisystems,
welche Fassung gilt. Deshalb bricht der Rechner ab und schreibt ans
Pult, was zu tun ist. Keine Fassung, die vom Zufall abhängt.

### Prüfen, ohne acht Gigabyte anzufassen

```
bash pruefstand/updater_test.sh
python pruefstand/teile_test.py
python pruefstand/bericht_test.py
python pruefstand/netz_alt_test.py
```

Alles läuft mit Attrappen, ohne Wurzelrechte, ohne systemd, ohne
Modell. `systemctl`, `sudo`, `curl`, `runuser`, `id` und `udevadm`
kommen aus `pruefstand/attrappen/` und schreiben nur mit.

Vier Umgebungsvariablen biegen Pfade um, **nur** für den Prüfstand. Ihre
Vorgabe ist immer der echte Ort:

| | statt |
|---|---|
| `DEVARENU_UNIT_ORDNER` | `/etc/systemd/system` |
| `DEVARENU_UDEV_REGEL` | `/etc/udev/rules.d/99-devarenu-stick.rules` |
| `DEVARENU_DATEN` | `/var/lib/devarenu/updates` |
| `DEVARENU_STICK_ORDNER` | ein eingehängter Datenträger |

Die Liste der erlaubten Schlüssel hat **bewusst keinen** eigenen
Schalter — eine Variable, die bestimmt, welche Signatur gilt, wäre der
Hebel, mit dem sich ein fremdes Tag annehmen ließe. Sie hängt an
`DEVARENU_DATEN`.

### Die Schlüsselliste kommt nie vom Stick

Auf dem Stick **liegt** eine `schluessel.erlaubt`. Sie ist
ausschließlich für `bootstrap.sh` da — für einen Rechner, der das
Verfahren noch nicht kennt und deshalb noch keine eigene Liste hat.
`bootstrap.sh` zeigt den Fingerabdruck daraus am Bildschirm, und ein
Mensch vergleicht ihn **am Telefon** mit dem, den der Betreuer ihm
nennt. Dieser Anruf ist der Vertrauensanker, nicht die Datei.

**`stick_update.sh` liest sie nicht.** Der Kern prüft ausschließlich
gegen `~/Devarenu/schluessel.erlaubt`, also gegen die installierte
Liste. Vom Stick kommen nur `devarenu.bundle`, `wheels/` und `teile/`.

Würde er die Liste vom Stick lesen, bräuchte ein Angreifer nur einen
Stick zu bespielen: er brächte seine eigene Erlaubnis mit, und die
Signaturprüfung prüfte nichts mehr als sich selbst.

Belegt als **Fall 13** im Prüfstand — ein Tag von fremder Hand, dieselbe
Absenderadresse, dazu die passende Erlaubnis auf dem Stick:

```
ok    die Signatur wird als ungueltig erkannt
ok    das Pult sagt: Signatur
ok    die Fassung blieb unangetastet
ok    der fremde Schluessel steht in keiner Erlaubnisliste
ok    mit dem echten Schluessel geht derselbe Stick durch
```

Die letzte Zeile gehört dazu: ohne sie bewiese der Fall nur, dass
irgendetwas scheitert.

### Von 0.2.12 auf 0.2.13

**Nur Stick einstecken.** Eingespielt wird mit der *alten* Logik aus
0.2.12 — der neue Kern greift erst ab dem Update danach. Deshalb bringt
0.2.13 keine großen Teile mit und lässt `requirements.txt` unangetastet.

### Von 0.2.11 direkt auf 0.2.13

> **Nicht mehr der geplante Weg** — es geht direkt auf 0.3.0. Das
> Folgende gilt unverändert weiter, nur mit der höheren Zahl.

Geht genauso, mit **denselben** Übergangsschritten. Geprüft:

- `requirements.txt` ist seit `v0.2.11` unverändert — der Stick braucht
  keine Wheels.
- 0.2.11 schrieb dieselben zwei Werte in `config.py`
  (`NETZ_ROUTER`, `NETZ_RECHNER`), also derselbe
  `git checkout -- config.py firewall.sh`.
- `zustand.json` steht dort in Fassung 2; die Umzugskette bringt sie
  beim ersten Start auf 3.
- Die dnsmasq-Konfiguration von 0.2.11 liegt noch unter
  `/etc/dnsmasq.d/devarenu.conf`. `netzzustand` kennt diesen alten Ort
  und übernimmt den Zustand daraus.

0.2.12 wird dabei übersprungen. Das ist ohne Folgen — sie bringt keine
Datenänderung mit, die 0.2.13 nicht selbst nachholt.

## Von 0.2.11 direkt auf 0.3.0 — der Weg des Helfers

Der Gemeinderechner steht auf 0.2.11. Vor Ort ist kein Techniker,
sondern ein Ehrenamtlicher **ohne Admin-Passwort**. Er soll so wenig wie
möglich tun: **ein Stick, eine Runde, eine getippte Zeile.**

Gedruckt bekommt er dafür `anleitung/Devarenu-Umstellung.pdf` — eine
Seite, ohne Fachbegriffe. Alles Folgende steht dort in seiner Sprache.

### Warum das ohne sudo geht

Er braucht kein Wurzelrecht, weil an keiner Stelle er selbst eines
braucht:

| Schritt | wer mit Rechten läuft |
|---|---|
| die eine Zeile | niemand, es ist sein eigener Ordner |
| Stick einstecken | udev → `devarenu-stick@.service`, von systemd |
| „Jetzt einspielen" | das Pult schreibt nur eine Marke, als normaler Benutzer |
| einspielen | `devarenu-update.timer`, von systemd, binnen einer Minute |

Der Server startet **nichts** selbst neu. Er legt `update/jetzt` an, und
der Timer, der ohnehin jede Minute nachsieht, überspringt daraufhin die
Wartezeit. Genau dafür gibt es keine dauerhaft offene sudo-Regel.

### Die eine Zeile

```fish
cd ~/Devarenu; git checkout HEAD -- .
```

Bis 0.2.11 schrieb `netz_einrichten.sh` in `config.py`, und `firewall.sh`
bekam ein Ausführungsrecht. Beides macht den Ordner „verändert", und
jedes Update bricht dann ab.

`git checkout HEAD -- .` statt zweier Dateinamen: der Helfer soll nicht
entscheiden müssen, was abweicht. **Geprüft, dass das ungefährlich ist** —
unversionierte Dateien bleiben unberührt, also `zustand.json` mit dem
WLAN-Passwort, `netz.json`, `update/`, `models/`, `voices/`, `.venv/`.
Wiederhergestellt wird nur, was im Repo steht, samt Rechtebits.

`HEAD --` und nicht nur `--`: ohne `HEAD` holt git aus dem *Index*. Wäre
je etwas vorgemerkt worden, bliebe der Ordner verändert und das Update
bräche weiter ab — ohne dass jemand sähe, warum.

### Was mitkommt und was nicht

0.3.0 wird mit dem **alten** Updater von 0.2.11 eingespielt. Der neue
Kern kommt mit und greift erst beim Update danach. Also bewusst klein:
`requirements.txt` seit v0.2.11 unverändert, keine großen Teile.

Der alte Kern überschreibt sich dabei selbst — er führt ein
`git merge --ff-only` auf eine Fassung aus, in der `stick_update.sh`
anders aussieht. **Das geht gut**, und es ist nicht Glück: git legt beim
Auschecken eine neue Datei an und benennt sie um, statt die alte zu
überschreiben. Die laufende Shell liest über ihren offenen Deskriptor
die alte Fassung zu Ende. Im Prüfstand ist das Fall 9, mit dem echten
Kern aus `git show v0.2.11:stick_update.sh`.

**Die Units bleiben die von 0.2.11.** Sie rufen das Skript ohne
`/bin/bash` auf, was am Ausführungsrecht hängt — das führt git mit
(`100755`). Fall 10 belegt, dass der neue Kern dieselben Argumente
verträgt. Neu geschrieben werden sie erst beim nächsten Update.

### Was danach noch offen ist

Nichts davon kann ein Update erledigen, alles braucht jemanden vor Ort:

| | warum nicht im Update |
|---|---|
| **Netz** `netz_einrichten.sh` | stellt die Netzkarte um; geht es schief, ist der Rechner ohne Netz |
| **Firewall** `firewall.sh --schnittstelle` | hängt an der Karte, die erst das Netz festlegt |
| **Rechner** `rechner_einrichten.sh` | Autologin, kein Standby — gilt für den ganzen Rechner |
| **Vorrat** `vorrat_bauen.sh` | braucht eine Leitung, rund 13 GB |
| **Journal** `--rotate`, `--vacuum-time=1s` | löscht das ganze Systemprotokoll |

Das Pult meldet Vorrat, veraltete Units und das alte Netz von selbst.

### Das alte Netz meldet sich ruhig

Bis 0.2.14 meldete der Systemcheck für den Aufbau von 0.2.11 **drei
FEHLT-Befunde**, allen voran „Der Umbau ist halb". Das ist ein roter
Alarm für einen Rechner, an dem nichts kaputt ist — und er stand am
Pult vor jemandem, der ihn nicht einordnen konnte.

Ab 0.3.0 steht dort **ein Hinweis**:

> Das Netz läuft noch nach dem Aufbau von 0.2.11. Es funktioniert;
> nichts ist kaputt. Beim nächsten Wartungsbesuch neu einrichten.
> Betroffen: /etc/dnsmasq.d/devarenu.conf, die von Hand angehängte
> conf-dir-Zeile in /etc/dnsmasq.conf, der von Hand angelegte
> systemd-Zusatz mit Ordnungszyklus.

Liegen **beide** Konfigurationen da, ist etwas halb umgezogen — dann
bleibt es beim Alarm. Geprüft in `pruefstand/netz_alt_test.py`.

## Neuen Kern vor Ort prüfen — mit 0.2.14

Der neue Kern greift erst beim Update **nach** 0.2.13. **0.2.14 ist
dieses Update** — die erste Fassung, die er selbst einspielt. Deshalb
einmal danebenstehen.

0.2.14 ist dafür geeignet: keine großen Teile, `requirements.txt`
unverändert. Im Prüfstand ist genau dieser Sprung als Fall 8
durchgespielt.

### Einspielen und zusehen

Stick einstecken, dann mitlesen:

```fish
journalctl -f -u 'devarenu-stick@*' -u devarenu-update.service
```

### Woran du erkennst, dass der neue Kern gearbeitet hat

Diese Zeilen gibt es **nur** im neuen Kern:

```
ok    Stand gesichert: Units, zustand.json, netz.json
ok    Logik aus <7 Zeichen> ausgepackt
== Einspielen
ok    requirements.txt unveraendert, keine Pakete noetig
ok    keine grossen Teile in dieser Fassung
```

Die zweite ist die wichtigste: sie nennt die **Objekt-SHA**, aus der
die Update-Logik kam — nicht den Tagnamen. Vergleichen lässt sie sich
mit:

```fish
git rev-parse --short v0.2.14^{commit}
```

**Am Pult**, unter *Einrichtung*: „Update auf Fassung 0.2.14 ist
eingespielt und läuft."

**Auf der Platte:**

```fish
sudo ls -la /var/lib/devarenu/updates/
sudo ls -la /var/lib/devarenu/updates/vorher-0.2.14/
```

Erwartet: `vorher-0.2.14/` mit `units/`, `zustand.json`, `netz.json`,
`befunde-vorher`, und der Ordner mit Rechten `700`. Das
Auspackverzeichnis `logik-0.2.14/` ist danach wieder weg.

### Woran du erkennst, dass der Rückfall greifen würde

Ohne etwas kaputtzumachen: **die Sicherung ist der Beweis.** Steht sie
da und ist vollständig, kann der Kern zurück.

Wer es wirklich auslösen will, baut eine 0.3.1, deren
`aktualisierung.sh` am Ende `exit 1` hat. Dann muss dastehen:

```
FEHLT Die Update-Logik ist gescheitert (Rueckgabe 1).
!     zurueck auf <7 Zeichen>
```

und am Pult: „Fassung 0.2.14 wurde wiederhergestellt und läuft."
Danach muss `bash pruefen.sh` wieder still sein. **Nicht an einem
Sonntag.**

### Woran du erkennst, dass der Gesundheitscheck greift

```
== Gesundheitscheck
ok    Dienst laeuft
ok    antwortet
ok    meldet Fassung 0.2.14
ok    keine neuen Fehler
```

„Keine neuen" heißt: neu gegenüber dem Stand vor dem Update. Was vorher
schon im Argen lag, rollt kein Update zurück. Der Vergleichsstand liegt
in `vorher-0.2.14/befunde-vorher`.

Ändern sich venv oder große Teile, läuft zusätzlich der Selbsttest —
bei 0.2.14 also **nicht**.

### Danach: einmalig das alte Journal aufräumen

**Das gehört zu diesem Update dazu.** Bis 0.2.13 schrieb der Server bei
jedem Abschnitt bis zu sechzig Zeichen des gesprochenen Satzes ins
Journal, dazu die Zuschriften aus dem Saal im Wortlaut und die
Personennamen aus dem Predigtmanuskript. Im Journal dieses Rechners
stehen damit Predigtsätze aus früheren Gottesdiensten — Wochen davon.

Ab 0.2.14 passiert das nicht mehr. Das Alte verschwindet dadurch aber
nicht von allein.

#### Warum `--vacuum-time=2d` allein nichts nützt

Zwei Eigenschaften von `journalctl`, die zusammen eine Falle bilden:

1. **Vacuum fasst nur archivierte Dateien an.** In der man-Page steht
   es wörtlich: „removes the oldest **archived** journal files" und
   „the vacuuming operation only operates on archived journal files."
   Die gerade beschriebene, *aktive* Datei bleibt unangetastet.
2. **Gelöscht wird dateiweise, nicht zeilenweise.** Eine Journaldatei
   umfasst viele Stunden. Sie fliegt nur raus, wenn sie als Ganzes
   älter ist als die Grenze.

Daraus folgt: `sudo journalctl --vacuum-time=2d` lässt genau die Datei
stehen, auf die es ankommt. Frisch rotiert enthält sie die alten
Predigtsätze **und** die Einträge von eben — damit ist sie nicht zwei
Tage alt und bleibt liegen. Ohne `--rotate` ist sie nicht einmal
archiviert und kommt gar nicht erst in Frage.

#### Der Ablauf

**a) Erst den Kerntest zu Ende machen.** Das Aufräumen kommt danach,
sonst löschst du die Meldungen, an denen du den Test abliest.

**b) Die Meldungen des Kerntests wegsichern**, bevor sie verschwinden.
`<beginn>` ist der Zeitpunkt, zu dem du den Stick eingesteckt hast, im
Format `"2026-09-27 14:00"`:

```fish
journalctl -u 'devarenu-stick@*' -u devarenu-update.service \
  --since "<beginn>" --no-pager > ~/kerntest-0.2.14.txt
wc -l ~/kerntest-0.2.14.txt
```

Die Datei liegt im Home und übersteht das Aufräumen. Sieh kurz hinein —
nach dem nächsten Schritt gibt es sie nur noch dort.

**c) Alles Bisherige archivieren:**

```fish
sudo journalctl --rotate
```

Das schließt die aktiven Dateien ab und legt leere neue an. Die man-Page:
„all currently active journal files are marked as archived and renamed,
so that they are never written to in future."

**d) Die archivierten Dateien wegwerfen:**

```fish
sudo journalctl --vacuum-time=1s
```

Alles, was älter als eine Sekunde ist — also alles aus Schritt c.

> Die beiden Befehle lassen sich laut man-Page auch zu einem
> zusammenfassen. **Hier nicht.** Bei `1s` kann die eben rotierte Datei
> dann jünger als die Grenze sein und stehenbleiben. Getrennt getippt
> liegt mehr als eine Sekunde dazwischen.

**e) Kontrolle:**

```fish
journalctl -u devarenu --since -90days | grep -c "Ton, STT"
journalctl --disk-usage
```

Erwartet: **0** Treffer und eine deutlich kleinere Zahl bei der
Plattennutzung. Kommt etwas anderes heraus, ist Schritt c oder d nicht
durchgelaufen — nicht weitermachen, sondern nachsehen.

Zeilen, die ab jetzt neu dazukommen, tragen keinen Text mehr, sondern
nur noch die Länge (`| 67 Z.`).

#### Was dabei verloren geht

**Das gesamte Systemprotokoll bis zu diesem Moment — nicht nur
Devarenu.** Also auch Startmeldungen, Netzwerk- und Treibermeldungen,
Fehler anderer Dienste, die ganze Vorgeschichte des Rechners.
`journalctl` kann nicht nach einzelnen Diensten löschen; die Journale
sind nach Zeit organisiert, nicht nach Herkunft.

Das ist hier hinnehmbar, weil der Rechner nichts protokolliert, was
über den Tag hinaus gebraucht wird — und weil das, was tatsächlich
gebraucht wird, in Schritt b im Home liegt. Auf einem anderen Rechner
wäre diese Abwägung eine andere.

Gebraucht wird danach nichts mehr aus dem Journal: der Fehlerbericht am
Pult liest ohnehin nur die letzten zwei Tage und nur ab Stufe
*warning*.

## Release-Checkliste

Bei jeder Fassung:

- [ ] `VERSION` setzen. **Jede Stelle mitziehen, die die Zahl nennt** —
      das Blatt für den Helfer nennt sie zweimal (was bereitliegt, was
      am Ende dastehen muss), die Beispiele in `stick_bauen.sh` und in
      dieser Datei ebenso. Gegenprobe:
      ```
      grep -rn "0\.2\.14" --include='*.sh' --include='*.py' --include='*.md' .
      ```
- [ ] **In `AENDERUNGEN.md` einen Abschnitt anlegen** — erst für
      Nicht-Techniker, darunter kurz für Techniker, und am Ende, was
      offen ist. Solange der Stick-Weg auf dem Gemeinderechner nicht
      gelaufen ist, gehört der Vorbehalt ganz nach oben.
- [ ] **Bei jeder größeren Fassung:** die Anleitung überarbeiten
      (`anleitung/*.md`), dann neu bauen:
      ```
      bash anleitung_bauen.sh
      ```
      Das braucht `.bau-venv` und `requirements-bau.txt` — beides nur
      auf dem Arbeitsrechner. Die fertigen PDF-Dateien gehören in den
      Commit.

      **Voraussetzung: zwei Schriften aus dem System.** Sie liegen
      nicht im Repo — es sind Systempakete, und mitgeliefert wären sie
      ein Lizenzanhang ohne Gewinn.

      | Schrift | Arch / CachyOS | Debian / Ubuntu |
      |---|---|---|
      | DejaVu Sans (Latein, Kyrillisch) | `ttf-dejavu` | `fonts-dejavu-core` |
      | Noto Naskh Arabic (Farsi) | `noto-fonts` | `fonts-noto-core` |

      Fehlt die arabische Schrift, bricht der Bau mit einer Meldung ab,
      statt ein PDF ohne Text zu schreiben.

      Zwei Bauläufe hintereinander müssen **byte-gleich** sein. Datum
      und Erstellzeitpunkt kommen aus `anleitung/DATUM`, nicht aus der
      Uhr — sonst wäre jeder Neubau eine Änderung im Repo. Also bei
      einer neuen Fassung auch `anleitung/DATUM` setzen.

      Gebaut werden sechs PDF-Dateien:

      | Datei | für wen |
      |---|---|
      | `Devarenu-Anleitung.pdf` | die ganze Anleitung, Teil A bis C |
      | `Devarenu-Zuhoerer{,-en,-ru,-fa}.pdf` | Teil A einzeln, vier Sprachen |
      | `Devarenu-Umstellung.pdf` | **eine Seite** für den Helfer vor Ort |

      Das Blatt für den Helfer hat keine Titelseite und muss auf **eine**
      Seite passen. Wird es länger, bricht der Bau ab statt still zwei
      Seiten zu liefern — ein zweiseitiges „Blatt" geht am Zweck vorbei.
      Es nennt die Fassung im Fußbereich, damit ein Ausdruck von vor
      einem Jahr erkennbar ist.
- [ ] `bash pruefen.sh` und `python selbsttest.py` müssen grün sein.
- [ ] **Den Prüfstand laufen lassen:**
      ```
      bash pruefstand/updater_test.sh
      python pruefstand/teile_test.py
      python pruefstand/bericht_test.py
      python pruefstand/netz_alt_test.py
      ```
      Der dritte prüft mit **erfundenen** Daten, dass im Fehlerbericht
      weder Mitschrift noch Namen noch Zugangsdaten stehen. Der vierte,
      dass ein Netz nach altem Aufbau einen ruhigen Hinweis bekommt und
      keinen Alarm.
- [ ] **Ist das öffentlich zumutbar?**
      ```
      bash oeffentlich_pruefen.sh
      ```
      Prüft den ganzen Baum auf Benutzernamen, fremde Rechnernamen und
      Pfade, private Netzadressen, Personennamen und Zugangsdaten.
      Was dort auftaucht und trotzdem hingehört, kommt mit einer
      Begründung in die Ausnahmeliste im Skript.

      **Ein Fund, der schon gepusht ist, lässt sich nicht zurückholen.**
      Entfernen hilft für die Zukunft, nicht für die Vergangenheit.
- [ ] Ändern sich große Teile (Modell, Stimmen, Spracherkennung):
      ```
      python teile.py --erfassen
      ```
      und `teile.json` mit einchecken. Sonst **nicht** — eine
      `teile.json` im Tag bedeutet für die Windows-Batch-Datei, dass
      der Stick auf diesem Weg nicht vollständig gebaut werden kann.
      Sie bricht dann ab und verweist auf einen fertigen Stick.
- [ ] `git status` muss schweigen, bevor getaggt wird.
- [ ] Signierter Tag, dann Stick bauen:
      ```
      bash stick_bauen.sh /run/media/<name>/STICK
      ```
      Ohne `--python` gilt 3.14 — die Fassung auf dem Gemeinderechner.

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
      durch. `bash pruefen.sh` sagt es vorher, `INSTALLIEREN.sh` fragt beim
      Einrichten danach. Auf Ubuntu Server ist `ufw` ab Werk aus; wer ihn
      einschaltet, muss Port 8000 fürs lokale Netz freigeben.

## Aktualisieren

- [ ] `bash aktualisieren.sh` einmal ausführen. `zustand.json` muss danach
      unverändert sein — das Skript prüft und meldet es selbst.

## Aktualisieren ohne Netz, per USB-Stick

Die meisten Gemeinderechner haben kein Internet. `bash aktualisieren.sh`
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

Neu aufgesetzte Rechner brauchen das nicht, `bash dienst.sh` richtet alles
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

    bash pruefen.sh                     Abschnitt „Fassung"
    bash stick_update.sh --stand        nur die Statusdatei
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
