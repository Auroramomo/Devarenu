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

> **Seit 0.3.2: `no-ping`.** dnsmasq schickte vor jeder Vergabe erst
> ein ICMP-Echo an die Adresse und wartete auf Antwort. Gemessen an
> einem neuen Handy im Saal: drei DHCP-Anfragen, alle Antworten erst
> nach gut drei Sekunden — die Sekunden, in denen der Zuhörer auf eine
> leere Seite sieht und noch einmal tippt. In diesem Netz vergibt außer
> dnsmasq niemand Adressen, die Probe kann also nichts finden.
>
> **Das wirkt erst nach einem erneuten `sudo bash netz_einrichten.sh`.**
> Ein Update schreibt `/etc/devarenu/dnsmasq.conf` nicht neu.

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

### Merkposten: `fr_FR-upmc` mit `--speaker` neu messen

Eine Stimme steht in `messungen/laengenfaktor_stimmen.json`, aber
**nicht** in der Tempotabelle von `config.py`: `fr_FR-upmc-medium`,
gemessen mit 0,447. Alle anderen Stimmen liegen zwischen 0,99 und 1,67,
und Französisch ist gegenüber Deutsch eher länger als kürzer — halb so
lang ist die Übersetzung sicher nicht. Der Wert ist nicht plausibel,
und ein unplausibler Wert in der Tabelle wäre schlimmer als gar keiner:
er gälte als gemessen. Bis das geklärt ist, bekommt die Stimme den
Sprachrückfall 1,04.

Die wahrscheinliche Ursache steht in `voices.json`: die Stimme hat
**zwei Sprecher**. Piper nimmt ohne `--speaker` den ersten, und was
gemessen wurde, ist dann nicht das, was man meinte.

Nachgemessen ist das **nicht**, und es geht im Moment auch nicht ohne
Vorarbeit: `laengenfaktor.py` reicht gar kein `--speaker` an Piper
weiter (`argumente` in `sprechen()` kennt nur `--length-scale` und
`--noise-w-scale`). Wer das aufgreift, braucht drei Schritte:

1. In `sprechen()` ein `--speaker` durchreichen, und in `--je-stimme`
   je Sprecher einmal messen statt einmal je Stimme.
2. Die Stimme laden und den Lauf wiederholen — mit `--noise-w-scale 0`,
   sonst würfelt Piper die Längen um bis zu 10 %:

   ```
   python laengenfaktor.py --stimmen-laden --ziel-ordner ergebnisse/stimmprobe/voices
   python laengenfaktor.py --je-stimme --nur fr
   ```

   `--nur fr` misst nur Französisch nach; die übrigen Messungen in der
   Datei bleiben stehen.
3. Kommt ein Wert im Bereich der anderen französischen Stimmen heraus
   (siwis 1,04, tom 1,24), die Stimme in `config.py` eintragen. Kommt
   wieder etwas um 0,45 heraus, liegt es nicht am Sprecher — dann
   bleibt sie draußen, und der Kommentar in `config.py` wird um den
   Befund ergänzt.

## Bei einem Test sehen, wo die Kette kippt

Zwei Schalter, für zwei verschiedene Fragen.

### „Mitschrift im Protokoll" — der kleine

Gibt es seit 0.2.14. **Pult → Einrichtung → „Mitschrift im Protokoll
(nur zur Fehlersuche)".** Der Schalter steht in `zustand.json` unter
`protokoll_mitschrift`, **nicht** in `config.py`: eine Änderung an
einer versionierten Datei ließe jedes Update abbrechen. Er wirkt
sofort ohne Neustart und **überlebt einen Neustart** — er bleibt an,
bis ihn jemand ausschaltet. `pruefen.sh` meldet das, solange er läuft.

Wirkung: statt „42 Z." steht der erkannte Satz im Journal, gekürzt auf
etwa 60 Zeichen. Von Hand:

```fish
curl -s -X POST localhost:8000/api/protokoll -H 'Content-Type: application/json' -d '{"an": true}'
```

### „Testprotokoll" — der große

Neu in 0.3.3. Schreibt **je Abschnitt eine Zeile in eine Datei**, nicht
ins Journal: Zeitstempel, eingestellte Ausgangssprache, erkannter Satz,
jede Übersetzung, und die Dauer jedes Schrittes — Whisper, Übersetzung
je Sprache, Piper. Damit sieht man, wo es kippt: hat Whisper schon
falsch gehört, oder erst das Modell falsch übersetzt?

**Pult → Einrichtung → „Testprotokoll schreiben".** Der Schalter
erscheint **nur, wenn das Pult am Gemeinde-PC selbst geöffnet ist** —
aus dem Saal gibt es ihn nicht.

Es gelten die Regeln der Aufnahme, denn es ist derselbe Inhalt:

- **Ohne Einwilligung fängt nichts an.** Ein Haken, nicht zwei: dass
  die sprechende Person gefragt wurde. Der zweite Haken der Aufnahme
  („nur die Predigt") ergibt bei einem Test keinen Sinn. Geprüft wird
  im Server, nicht im Browser.
- Daneben liegt ein **Vermerk mit dem Zeitpunkt, ohne Namen**.
- **Es hört beim Neustart von selbst auf.** Der Schalter steht
  bewusst *nicht* in `zustand.json` — was den Predigttext mitschreibt,
  soll nicht aus Versehen über einen Sonntag weiterlaufen.
- `700` auf dem Ordner, `600` auf den Dateien, **nach sieben Tagen
  gelöscht** (dieselbe Frist wie die Aufnahme, `aufnahme_tage`).
- Abrufbar nur am Rechner selbst.

Die Dateien liegen unter `ergebnisse/pruefprotokolle/` und heißen
`pruefprotokoll_<datum>_<zeit>.jsonl` — eine Zeile JSON je Abschnitt.
Ansehen zum Beispiel so:

```fish
jq -r '"\(.nummer)  \(.text)"' ergebnisse/pruefprotokolle/pruefprotokoll_*.jsonl
```

```fish
jq -r '.ziele[] | "\(.sprache)  \(.mt_s)s  \(.text)"' ergebnisse/pruefprotokolle/pruefprotokoll_*.jsonl
```

## Wenn jemand in einer anderen Sprache spricht

Steht die Ausgangssprache auf Deutsch und es spricht jemand Englisch,
bekommt Whisper die Sprache **vorgegeben**. Es erfindet dann deutsche
Wörter aus englischen Lauten, der Text sieht plausibel aus, und das
Modell übersetzt ihn brav weiter — jede Zielsprache bekommt Unsinn,
und am Pult sieht alles normal aus.

Seit 0.3.3 fällt das auf. Am Pult erscheint eine gelbe Zeile
„Gesprochen wird vermutlich Englisch, eingestellt ist Deutsch" mit
einem Knopf, der zur Sprachwahl führt. **Umgeschaltet wird nichts von
selbst** — eine Automatik, die mitten in der Predigt die
Ausgangssprache wechselt, wäre schlimmer als das Problem.

Damit keine Fehlalarme entstehen, müssen drei Dinge zusammenkommen:
das Segment ist mindestens drei Sekunden lang, die Erkennung ist
mindestens zu 80 % sicher, und **dieselbe** fremde Sprache gewinnt
dreimal hintereinander. Ein Bibelvers mit hebräischen Namen, ein
englisches Lied, ein Eigenname — nichts davon kommt dreimal
hintereinander. Ein einziges sicheres deutsches Segment löscht die
Warnung wieder.

Geprüft wird nur **jedes vierte** taugliche Segment. Gemessen mit
`large-v3-turbo`, float16, auf einer RTX 5080:

| | |
|---|---|
| `detect_language` | 76 ms (unabhängig von der Tondauer) |
| `transcribe`, 5 s | 85 ms |

Bei jedem Segment zu prüfen würde den Whisper-Anteil also fast
verdoppeln. So liegt der Aufschlag bei rund einem Viertel eines
Durchlaufs, und bis eine Warnung erscheint, vergehen ein bis zwei
Minuten durchgehend fremder Rede.

## Sprachen ohne geprüftes Fachwortverzeichnis

Eine Sprache hat drei Zustände, und sie sehen am Pult verschieden aus:

| Zustand | Am Pult | Beim Zuhörer |
|---|---|---|
| geprüft | normal | normal |
| Glossar da, ungeprüft | gestrichelt | gestrichelt, Punkt |
| gar kein Glossar | gepunktet | gepunktet, Kreis |

Von 21 Sprachen haben **sechs** ein geprüftes Fachwortverzeichnis: de,
en, ru, fa und seit 0.4.0 es und pt. Wer Rumänisch dazuschaltet,
bekommt eine Übersetzung ohne jede Terminologie: Sabbat, Gemeinde und
Vereinigung werden wörtlich übertragen.

### Spanisch und Portugiesisch

Freigegeben mit 0.4.0, **nicht eingeschaltet**: `ZIELSPRACHEN` bleibt
en, ru, fa. Eine Gemeinde wählt sie am Pult unter *Übersetzt nach*; in
Rostock ändert sich dadurch nichts.

Je ein Muttersprachler hat die 72 Begriffe durchgesehen und rund 80
weitere beigetragen. Festgelegt ist dabei auch die **Anrede**
(`config.ANREDE`): die Gemeinde mit „ustedes" bzw. „vocês", Gott mit
„tú" bzw. „tu" — so wie es in Reina-Valera und Almeida steht. Ohne
diese Vorgabe entscheidet das Sprachmodell es in jedem Abschnitt neu,
und die Gemeinde wird im Wechsel geduzt und gesiezt.

**Bibelbuchnamen brauchen keine Einstellung je Gemeinde.** Geprüft
wurde das, nicht vermutet: je zwei unabhängige Übersetzungen über
`api.getbible.net` — für Spanisch Reina Valera (1909) gegen Sagradas
Escrituras (1569), für Portugiesisch Almeida Atualizada gegen Bíblia
Livre. Ergebnis **0 von 66** Buchnamen verschieden, in beiden Sprachen.
Die Namen stehen also fest; ein Schalter dafür hätte keinen Gegenstand.
Beim Abgleich fielen dagegen fünf Zellen auf, in denen unser Glossar
von beiden Übersetzungen abwich (`Nahú` → `Nahúm`, `Cânticos` →
`Cântico dos Cânticos`, `Abdias` → `Obadias`, `Miqueias` → `Miquéias`,
`Filemão` → `Filemom`). Sie sind berichtigt.

**Nach dem ersten Gottesdienst mit spanisch- oder
portugiesischsprachigen Zuhörern: deren Rückmeldung einholen.** Ein
geprüftes Glossar sagt, dass die Begriffe stimmen — nicht, dass die
Übersetzung im Saal verständlich ankommt. Zu fragen ist nach dem
Sprechtempo (für `pt_BR-jeff-medium` steht `TEMPO_STIMME` auf 1,15 und
ist noch nicht im Betrieb bestätigt), nach der Anrede und danach, ob
Bibelstellen beim Mitlesen wiederzufinden sind.

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

## Datenschutz

Das Verzeichnis der Verarbeitungstätigkeiten und ein Textbaustein für
die Gemeinde stehen in [DATENSCHUTZ.md](DATENSCHUTZ.md).

**Auf der Zuhörerseite und am Pult steht dazu bewusst nichts.** Ein
Hinweis dort wäre ein Text des Entwicklers über eine Verarbeitung,
für die die Gemeinde verantwortlich ist — und ein Link ins Leere,
solange niemand ihn pflegt. Die Gemeinde übernimmt den Baustein in
ihre eigene Erklärung, dorthin, wo ihre Leute ohnehin nachsehen.

Seit 0.3.6 speichert der Rechner weniger:

| | vorher | jetzt |
|---|---|---|
| DHCP-Mietliste | auf der Platte, dauerhaft | `/run`, weg beim Ausschalten |
| DHCP im Journal | jede Aushandlung mit MAC und Handyname | nichts (`quiet-dhcp`) |
| Zuhöreradressen im Journal | `10.0.0.57` | `Geraet a3f1`, gesalzen |

**Die ersten beiden wirken erst nach einem erneuten
`sudo bash netz_einrichten.sh`** — ein Update schreibt
`/etc/devarenu/dnsmasq.conf` nicht neu.

## Was dieser Rechner nach draußen sendet

**Vollständig, und es gibt nichts daneben.** Ohne Wartungsfenster und
ohne `meldung.json` verlässt gar nichts den Rechner — dann ist diese
Liste leer. Jeder Punkt hat einen eigenen Schalter, alle sind per
Vorgabe **aus**, und gesendet wird nur über den Kanal, der in
`meldung.json` auf **diesem** Rechner steht. **Im Code steht kein
Meldeziel.**

| Was | Wann | Inhalt |
|---|---|---|
| **Update-Rückmeldung** | nach einem Autoupdate | Fassung vorher/nachher, Ergebnis, Dauer, die letzten Zeilen des Laufs |
| **Fehlerberichte** | im Fenster, wenn welche vorliegen | nur die Erlaubnisliste aus `fehlerbericht.py`: Fassung, Rechnerdaten, Systemcheck, letztes Update, Journalzeilen ab Warnstufe |
| **Nutzungsmeldung** | einmal je Fenster | Name der Gemeinde, Fassung, Datum |
| **Spendenkonto-Hinweis** | beim Start, wenn die IBAN nicht stimmt | die Beanstandung, sonst nichts |

**Was nie hinausgeht**, auf keinem dieser Wege: Predigttext,
Übersetzungen, Mitschriften, Testprotokolle, Zuschriften aus dem Saal,
eingetippter Freitext, Namen von Personen, IP- oder MAC-Adressen,
WLAN-Name, WLAN-Passwort, `zustand.json`.

Der Name der Gemeinde ist die einzige Angabe, die diesen Rechner
benennt — und er steht nur dann darin, wenn du ihn einträgst und die
Nutzungsmeldung einschaltest. Am Pult steht neben dem Schalter, was
gesendet wird.

Nachsehen, was eingerichtet ist:

```fish
bash meldung.sh --zeigen
```
```fish
bash wartungsfenster.sh --zeigen
```

## Das Spendenkonto

Die IBAN steht fest in `config.py` unter `SPENDE` und lässt sich **am
Pult nicht ändern**. Wer das Programm weitergibt, soll das
Spendenkonto nicht nebenbei austauschen können.

Fest heißt nicht unfehlbar. Beim Start wird die **Prüfziffer nach
mod 97** gerechnet. Stimmt sie nicht, steht am Pult und auf der
QR-Seite:

> Das angezeigte Spendenkonto ist ungültig. Bitte wende dich an den
> Betreuer.

**Es wird nichts gelöscht und nichts abgeschaltet** — eine falsche
IBAN ist ein Grund nachzusehen, kein Grund, dem Zuhörer etwas
wegzunehmen. Ist auf dem Rechner ein Meldekanal eingerichtet, geht
zusätzlich eine Nachricht hinaus; ist keiner eingerichtet, geht keine.

## Der Name der Gemeinde

**Pult → Einrichtung → „Name der Gemeinde".** Er erscheint auf der
QR-Seite unter dem Titel als „Devarenu · <Name>". Leer lassen heißt:
keine Anzeige. Er steht in `zustand.json`, nicht im Repo.

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

## Wer im Saalnetz was erreicht

Jeder Zuhörer ist im Saal-WLAN — das ist sein Zweck. Damit ist das Netz
**nicht vertrauenswürdig**, und die Frage ist nicht theoretisch: die
Adresse steht an der Wand.

**Vorgabe ist ein offenes Pult, wie bisher.** In einer kleinen Gemeinde
ist das die richtige Abwägung; ein Passwort, das sonntags getippt werden
muss, landet als Zettel am Bildschirm.

Gemessen an einer Wegwerf-Kopie, ohne Passwort:

```
GET  /pult               200   die vollständige Bedienoberfläche
GET  /api/wlan           200   Netzname und Passwort im Klartext
POST /api/protokoll      200   die Mitschrift lässt sich EINSCHALTEN
POST /api/steuerung/…    200   die Übersetzung lässt sich anhalten
GET  /mitschnitt/<name>  200   eine laufende Aufnahme lässt sich holen
```

Das WLAN-Passwort ist dabei der kleinste Verlust — wer es abruft, ist
schon drin. Schwerer wiegen die anderen drei. Ein Angreifer ist dafür
nicht nötig; es genügt jemand, der die Adresse von der Wand abliest und
neugierig ist.

### Das Pult-Passwort (freiwillig)

Am Pult unter *Einrichtung*, ganz unten. Leer heißt: alles bleibt, wie
es war.

Ist eines gesetzt:

| | |
|---|---|
| Geräte im Saal | werden **einmal** gefragt, danach ein Jahr lang nicht |
| Die Zuhörerseite | bleibt offen — `/`, `/strom`, `/ton/…`, `/api/sprachen`, `/api/nachricht` |
| Dieser Rechner | wird **nie** gefragt (jede Loopback-Adresse) |
| Der Fehlerbericht aufs Handy | geht weiter: der QR trägt einen Schlüssel, 15 Minuten und drei Abrufe |

Die Liste der offenen Wege ist eine **Erlaubnisliste**, keine Sperrliste.
Kommt später ein Pult-Weg dazu, ist er geschützt, ohne dass jemand daran
denkt. Eine vergessene Sperre fiele niemandem auf.

Gespeichert wird ein PBKDF2-Hash mit 240 000 Runden und eigenem Salz,
nie das Passwort. Der Keks im Browser ist daraus abgeleitet — deshalb
braucht der Server keine Liste offener Sitzungen, die Anmeldung
übersteht jeden Neustart, und ein geändertes Passwort macht alle alten
Kekse mit einem Schlag ungültig.

### Vergessen — der Fall, der eintritt

```fish
cd ~/Devarenu
python werkzeuge/pult_passwort.py --stand
python werkzeuge/pult_passwort.py --loeschen
```

**Kein Neustart nötig.** Der Dienst sieht sich die Datei bei jedem
Aufruf kurz an und merkt die Änderung von selbst — wer gerade ausgesperrt
ist, denkt nicht an `systemctl`.

Setzen geht dort absichtlich nicht: ein Passwort in der Kommandozeile
landet in der Verlaufsdatei der Shell.

Geprüft in `pruefstand/pultschutz_test.py` — und zwar **aus dem Saal**,
über eine Adresse, die nicht Loopback ist. Über 127.0.0.1 gilt jeder
Aufruf als „am Rechner selbst"; ein Prüflauf, der nur darüber spricht,
belegt die Sperre nie. Findet er keine solche Adresse, meldet er das als
Fehler statt still durchzulaufen.

### Die Aufnahmen

Aufnahmen (`/mitschnitt/…`) entstehen nur nach ausdrücklichem Druck am
Pult und nur mit zwei Häkchen — im normalen Betrieb entsteht nichts.
Seit 0.3.0 werden sie nach **sieben Tagen gelöscht** (`aufnahme_tage`,
am Pult einstellbar), der Aufräumlauf geht stündlich. Abrufbar sind
sie nur am Gemeinde-PC selbst, nie aus dem Saalnetz.

**Löschen von Hand** gibt es seit 0.4.0: ein Knopf je Aufnahme, mit
einer Rückfrage, die den Dateinamen nennt. Nur am Gemeinde-PC selbst,
wie das Herunterladen — ein Pult-Passwort würde das nicht ersetzen, es
ginge im Saalnetz unverschlüsselt über HTTP. Eine laufende Aufnahme ist
nicht löschbar. Ins Journal geht nur der Dateiname.

Seit 0.3.8 ist das Format **MP3**, 48 kbit/s mono, rund 22 MB je
Stunde. Die Datei heißt `Predigt_TT_MM_JJJJ.mp3` nach dem Tag des
Aufnahmebeginns; gibt es den Namen schon, kommt `_2`, `_3` dahinter.
Kann der Rechner kein MP3 schreiben (kein `ffmpeg` mit `libmp3lame`,
kein `lame`), läuft die Aufnahme als WAV weiter und der Systemcheck
sagt es.

*Bis 0.2.15 wurden Aufnahmen nie gelöscht: kein Höchstalter, keine
Höchstzahl, kein Hinweis. Wer die Aufnahme ein Jahr lang jeden Sabbat
benutzte, hatte rund fünfzig Predigten als Rohton auf der Platte.*

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

### Die Sitzung je Rechner wählen

Seit 0.3.6 steht sie in `netz.json`, Vorgabe `wayland`:

```json
"sitzung": "x11"
```

`rechner_einrichten.sh` schreibt danach `Session=plasmax11` statt
`plasma`, und der Systemcheck vergleicht gegen diesen Wert. Das Paket
`plasma-x11-session` liegt im Reparaturvorrat.

> **Umgestellt wird nur VOR ORT.** Kommt der Rechner in der neuen
> Sitzung nicht hoch, hilft bis zur nächsten Fahrt nichts — und dann
> nützt auch das Wartungsfenster nichts, denn es setzt einen
> laufenden Rechner voraus. Wer es aus der Ferne versucht, hat im
> schlechtesten Fall bis zum nächsten Besuch gar nichts.

Nach der Umstellung: `sudo bash rechner_einrichten.sh`, neu starten,
und `loginctl show-session $XDG_SESSION_ID -p Type` muss das Neue
sagen. Meldet der Systemcheck weiter eine Abweichung, hat die
Einstellung nicht gegriffen — dann steht die Sitzung nicht zur
Verfügung, und man schaltet besser zurück.

### Fernwartung unter Wayland: Terminal und Tunnel

**Der Bildschirm ist nach einem Neustart nicht verlässlich
erreichbar.** Unter Wayland darf kein Programm einfach mitlesen;
RustDesk geht über xdg-desktop-portal, und KDE fragt bei jeder neuen
Portal-Sitzung wieder, welcher Bildschirm freigegeben wird. Der
gespeicherte `wayland-restore-token` überbrückt das nicht — KDE bindet
ihn an die Sitzung, und die ist nach einem Neustart weg. Das ist kein
Fehler von RustDesk und mit keiner Einstellung dort zu beheben.

**Der Weg ist deshalb: RustDesk-Terminal und ein TCP-Tunnel auf Port
8000.** Das Terminal hängt an keiner grafischen Sitzung, der Tunnel
bringt das Pult in den eigenen Browser. Damit ist alles erreichbar,
was man aus der Ferne braucht — ohne die Portal-Frage überhaupt zu
stellen.

Der Umstieg auf X11 bliebe die Alternative, und `plasma-x11-session`
liegt seit 0.3.3 im Reparaturvorrat bereit. **Aus der Ferne wird er
nicht gemacht:** kommt der Rechner in der neuen Sitzung nicht hoch,
hilft bis zur nächsten Fahrt nichts, und dann nützt auch das
Wartungsfenster nichts.

Eine KDE-Vorabfreigabe über den Berechtigungsspeicher wurde verworfen.
Sie hinge an einer Stelle, die KDE nicht als Einstellung vorsieht —
sie hielte vermutlich ein Jahr und dann an einem Sonntag nicht mehr.

Seit 0.3.2 gibt es dafür auch den Weg ohne jemanden vor Ort, siehe
[Das Wartungsfenster](#das-wartungsfenster). Innerhalb des Fensters
ist das verbundene WLAN erwartet und wird nicht gemeldet.

**Auf dem WLAN wird nichts freigegeben** — weder das Pult noch sonst
etwas. RustDesk baut seine Verbindung selbst nach draußen auf und
braucht keinen offenen Port.

Zwischen WLAN und Saalnetz wird nie geleitet: `ip_forward` bleibt aus,
und alle Freigaben hängen an der Kabelkarte zum Zugangspunkt.

## Das Wartungsfenster

Seit 0.3.2 gibt es einen zweiten Weg zur Fernwartung, der **niemanden
vor Ort braucht**: an einem festen Wochentag, in einer festen Stunde,
verbindet sich der Rechner mit dem Gemeinde-WLAN und trennt sich
danach wieder. Dazwischen ist er so unerreichbar wie zuvor.

**Per Vorgabe ist das Fenster aus.** Es gilt vorerst nur für Rostock.

### Einschalten

Ein Befehl, keine Handbearbeitung von `netz.json`:

```fish
bash wartungsfenster.sh --einschalten "Gemeinde-WLAN" Do 18:00 22:00
```

Ohne Angaben zeigt er die vorhandenen WLAN-Profile und sagt, wie es
geht. Was er tut:

1. **Prüft die Werte, bevor er schreibt** — mit derselben Funktion,
   die sie später auch liest. Was hier durchgeht, gilt auch für den
   Timer; sonst stünde ein Fenster in `netz.json`, das er wortlos
   ignoriert, und niemand wüsste warum. Schlägt die Prüfung fehl,
   bleibt `netz.json` unangetastet.
2. Trägt den Block in `netz.json` ein (nicht im Repo, gehört diesem
   einen Rechner). Vorhandene Werte bleiben stehen: wer nur die
   Uhrzeit ändert, verliert die Laufzeitgrenzen nicht.
3. Stellt das Profil auf **`autoconnect no`**. Ohne das verbände sich
   der Rechner auch außerhalb des Fensters, und das Fenster wäre eine
   Verabredung ohne Wirkung.
4. Stellt den Wecker und gibt `--zeigen` aus.

Der Wochentag geht kurz oder ausgeschrieben (`Do`, `Donnerstag`,
Groß- und Kleinschreibung egal), aber nichts darüber hinaus:
„Donnerstagabend" wird abgewiesen. Wer das schreibt, meint eine
Uhrzeit und keinen Tag.

Wieder ausschalten:

```fish
bash wartungsfenster.sh --ausschalten
```

Das löscht den BIOS-Wecker mit, trennt das WLAN, wenn gerade Fenster
war, und lässt Profil und Uhrzeit stehen — wer nächste Woche wieder
einschaltet, tippt sie nicht neu.

Die Laufzeitgrenzen (`hoechstlaufzeit_h`, `hoechstlaufzeit_hart_h`)
stehen weiter nur in `netz.json`. Sie ändert man selten, und ein
Befehl mit sechs Stellen wäre einer, den man falsch bedient.

### Was der Rechner dann tut

| Zeitpunkt | Was passiert |
|---|---|
| alle 5 Minuten | Im Fenster verbinden, außerhalb trennen |
| Fensterbeginn | war er aus, hat der BIOS-Wecker ihn 5 Minuten vorher geweckt |
| Fensterende | herunterfahren |
| nach 24 h Laufzeit | herunterfahren |
| nach 36 h Laufzeit | herunterfahren, **auch wenn übersetzt wird** |
| bei jedem Start und Stopp | Wecker auf den nächsten Fensterbeginn stellen |

**Ausfall heißt zu.** Fällt der Timer aus, bleibt das WLAN getrennt —
das Profil verbindet sich nicht von selbst. Ein unbrauchbarer Wert in
`netz.json` schaltet das Fenster ab, nicht auf. Eine verpasste Wartung
kostet eine Woche; ein vergessenes offenes WLAN ist der Schaden.

**Ein verpasster Termin wird nicht nachgeholt.** Der Timer trägt kein
`Persistent=true`: sonst verbände sich der Rechner am Samstag, weil
der Donnerstag ausgefallen ist.

**Nur das eine Profil wird angefasst.** Ein Handy-Hotspot, den jemand
vor Ort aufgemacht hat, bleibt unberührt — wer davor sitzt, soll nicht
mitten in der Arbeit ausgesperrt werden.

**Zwischen WLAN und Saalnetz wird auch im Fenster nie geleitet.**
`ip_forward` bleibt aus, und `pruefen.sh` sieht nach.

### Das Auto-Aus und der Gottesdienst

Läuft eine Übersetzung, **wartet** das Auto-Aus — der Rechner fragt
`/api/zustand` und sieht `live`. Aber nicht unbegrenzt: bei
`hoechstlaufzeit_hart_h` (36) geht er aus, Übersetzung hin oder her.
Ein Rechner, der seit anderthalb Tagen „live" meldet, hat keinen
Gottesdienst, sondern einen Tonstrom, den niemand abgestellt hat — und
der hielte ihn sonst für immer wach.

Wer den Rechner absichtlich außerhalb des Fensters hochfährt, wird
nicht sofort wieder ausgesperrt: das Fensterende schaltet nur in den
15 Minuten danach ab, nicht den ganzen Abend.

### BIOS

Am ASUS PRIME B760M-A WIFI D4 vor Ort geprüft:

| Einstellung | Wert | Warum |
|---|---|---|
| **ErP Ready** | **aus** | Mit ErP wird die RTC im Standby nicht mehr versorgt, und der Wecker zündet nicht |
| **Power On By RTC** | **aus** | Der Wecker kommt vom Betriebssystem (`rtcwake`), nicht vom BIOS. Beides zugleich ergibt zwei Weckzeiten |
| **Restore AC Power Loss** | egal | Der Wecker reicht |

Die Hardware-Uhr läuft in **UTC**. Die Umrechnung von Ortszeit passiert
an genau einer Stelle — in `wartungsfenster.py`, wo die Sommerzeit
bekannt ist. Über die Zeitumstellung hinweg bleiben es 18:00 Ortszeit;
der Prüfstand rechnet die 169 echten Stunden zwischen zwei
Donnerstagen nach.

### Strom

**Der Schalter hinten am Netzteil bleibt an**, und der Stecker bleibt
drin. Der Rechner wird normal heruntergefahren, über das Menü. Ohne
Strom am Netzteil kann die RTC nicht wecken — dann kommt bis zum
nächsten Besuch niemand mehr heran. Das steht auch auf dem Helferblatt.

### Autoupdate im Fenster

Seit 0.3.3 kann sich der Rechner im Fenster selbst aktualisieren.
**Vorgabe ist aus.**

```fish
bash wartungsfenster.sh --autoupdate ja
```

Es gelten dieselben Regeln wie von Hand — nur signierte Tags, nur über
die geprüfte SHA — und drei weitere:

- **Nie während einer Übersetzung.** Der Rechner fragt `/api/zustand`;
  meldet der Dienst `live`, wartet das Update bis zum nächsten Tick.
- **Einmal je Fenster.** Sonst liefe der Updater alle fünf Minuten neu
  und nach einem Fehlschlag jedes Mal wieder in denselben.
- **Scheitert es, geht es von selbst zurück** — Code, Units,
  `zustand.json`, `netz.json`. Ohne diesen Rückweg gäbe es den
  Schalter nicht.

Danach: bei Erfolg oder „kein neueres Tag" fährt der Rechner herunter
(`nach_update_aus`, Vorgabe an). Bei einem Fehlschlag bleibt er bis
Fensterende an, damit jemand nachsehen kann; das Protokoll des Laufs
liegt unter `/var/lib/devarenu/updates/autoupdate-*.log`.

Nach einem gelungenen Update wird auch der **Reparaturvorrat**
nachgezogen, solange das WLAN steht. Scheitert das, steht es nur in der
Rückmeldung — der Vorrat ist eine Vorsichtsmaßnahme und hat noch nie
einen Gottesdienst aufgehalten.

Willst du an einem Donnerstag selbst hinein, ohne dass der Rechner
vorher weggeht:

```fish
bash wartungsfenster.py --schalter nach_update_aus=nein
```

### Die Rückmeldung

Ohne sie merkt man ein gescheitertes Update erst am Sabbat. Der Kanal
ist **ntfy**; die Zugangsdaten stehen in `meldung.json` neben dem
Projekt, mit `600` und in `.gitignore` — **nicht** in `netz.json`, die
wird mit `644` geschrieben.

Ein Thema erzeugen und eintragen:

```fish
echo "devarenu-"(head -c 18 /dev/urandom | base32 | tr -d = | tr 'A-Z' 'a-z')
```

```fish
set thema "devarenu-"(head -c 18 /dev/urandom | base32 | tr -d = | tr 'A-Z' 'a-z')
echo "{\"ntfy\": \"https://ntfy.sh/$thema\"}" > meldung.json
chmod 600 meldung.json
bash meldung.sh --pruefen
```

Das Thema hier nicht ausschreiben: `oeffentlich_pruefen.sh` sucht nach
fertigen ntfy-Adressen in verfolgten Dateien und schlägt sonst an —
zu Recht.

Auf dem Handy die ntfy-App installieren und dasselbe Thema abonnieren.

**Das Thema ist das ganze Geheimnis** — es gibt kein Passwort daneben.
Wer es kennt, liest mit. Deshalb geht nur hinaus, was niemandem
schadet: Fassung vorher und nachher, Ergebnis, Selbsttest, Dauer.
Kein Predigttext, kein WLAN-Name, keine Adresse.

Telegram wäre derselbe Aufwand gewesen. Dagegen sprach das Schadensmaß:
ein Bot-Token ist ein Schlüssel, mit dem jemand den Bot **steuert** —
ein ntfy-Thema ist eine Adresse, unter der jemand **mitliest**.

Geht eine Meldung nicht hinaus, bleibt sie in `meldung-offen.txt`
liegen, und der nächste Lauf nimmt sie mit.

### Fehlerberichte, die von selbst kommen

Bis 0.3.2 musste jemand am Pult den Käfer drücken, zwei QR-Codes
abfotografieren und eine E-Mail abschicken. Ein Dienst, der nachts
abstürzt und von selbst wieder hochkommt, fällt dabei niemandem auf —
und genau der wäre interessant.

```fish
bash wartungsfenster.sh --berichte ja
```

Gesammelt wird bei vier Anlässen:

| Anlass | wann |
|---|---|
| `hand` | jemand hat am Pult den Käfer gedrückt |
| `neustart` | der Dienst ist beim letzten Mal nicht sauber beendet worden |
| `systemcheck` | beim Start steht ein **FEHLT** an |
| `update` | ein Autoupdate ist fehlgeschlagen |

Die Berichte liegen unter `ergebnisse/berichte/` (`700`/`600`, nicht
im Repo) und gehen im Fenster über denselben Kanal hinaus wie die
Update-Rückmeldung. **Erst nach der Bestätigung** wird einer als
gesendet vermerkt; was nicht durchkam, geht im nächsten Fenster noch
einmal. Höchstens 50 liegen herum, die ältesten fallen weg.

**Inhalt: nur, was `fehlerbericht.bauen()` liefert** — also nur die
dortige Erlaubnisliste, plus deren zweiten Riegel. Kein eingetippter
Freitext von Zuhörern oder Bedienern, kein Predigt- oder
Übersetzungstext, keine Namen, keine IP- oder MAC-Adressen, kein
WLAN-Name. Hier wird nichts hinzugefügt.

**Warum Text und kein Anhang.** In der ntfy-Dokumentation nachgesehen:
Nachrichten über **4096 Bytes** macht der Server von selbst zu einem
Anhang, und **Anhänge verfallen nach drei Stunden**. Ein Bericht von
Donnerstagabend, den du freitags liest, wäre weg. Jeder Bericht bleibt
deshalb unter 3500 Bytes — gekürzt an einer Zeilengrenze, mit
Vermerk; vollständig liegt er weiter auf dem Rechner.

Von Hand abschicken, ohne auf das Fenster zu warten:

```fish
bash meldung.sh --berichte
```

### Nachsehen

```fish
bash wartungsfenster.sh --zeigen
systemctl list-timers devarenu-fenster.timer
sudo rtcwake -m show
journalctl -u devarenu-fenster.service -n 20
```

> **Die Wecker-Unit heißt `devarenu-fenster-wecker.service`**, nicht
> `devarenu-wecker.service`. Der längere Name ist Absicht: auf dem
> Gemeinderechner liegt seit dem 27.09. eine von Hand gebaute
> Übergangslösung unter dem kurzen Namen. Hießen beide gleich,
> überschriebe das erste Update die alte — und wer sie danach
> abschaltet, träfe die neue. So liegen sie nebeneinander, bis die
> alte von Hand abgeschaltet ist.

`pruefen.sh` meldet ein fehlendes `rtcwake`, einen ausgeschalteten
Fenster-Timer und ein Profil, das es gar nicht gibt. **Im Fenster**
gilt das verbundene WLAN als erwartet und wird nicht mehr als
„Wartungszugang aktiv" gemeldet — außerhalb schon.

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

**FAT32 und große Teile gehen jetzt zusammen.** Auf FAT32 passt keine
Datei über 4 GB; das Sprachmodell allein ist größer. Seit 0.3.1 wird
gestückelt: `teile.py` schreibt alles über 3,5 GB in mehrere Dateien
(`…​.teil00`, `.teil01`, …), und der Gemeinderechner setzt sie beim
Einspielen zusammen.

**Geprüft wird gegen die `sha256` aus `teile.json`** — und zwar bevor
etwas ersetzt wird. Stimmt sie nicht, bleibt das alte Modell liegen,
wo es liegt, und das Beiseitegelegte wird nicht aufgeräumt. Ein halb
eingespieltes Modell ist schlimmer als ein altes.

Erkannt werden zwei Fälle getrennt: ein **fehlendes** Stück an der
Länge, ein **verfälschtes** an der Prüfsumme. Die Unterscheidung
spart beim Suchen — das eine ist ein abgebrochener Kopiervorgang, das
andere ein defekter Stick.

Der Bau sagt es, wenn er stückelt. Wer die Wahl hat, nimmt trotzdem
exFAT: ein Stück weniger ist ein Fehler weniger.

### Einen Stick als ZIP verschicken

Wenn niemand vor Ort einen Stick bespielen kann — oder der Stick erst
beim Helfer ankommt:

```
bash stick_bauen.sh --zip ~/Devarenu-Stick-v0.3.0.zip
```

Kein echter Stick nötig. Die Dateien liegen im ZIP **ganz oben**, nicht
in einem Unterordner.

**Auf den Stick gehören die vier Dateien, nicht der Ordner.** Windows
entpackt in einen Ordner, der wie das ZIP heißt; dieser Ordner wird
geöffnet, und sein Inhalt wandert direkt oben auf den Stick.

> **Kerne vor 0.2.13 suchen `upd-dev.txt` NUR ganz oben** (`maxdepth 1`).
> Der Gemeinderechner läuft noch auf 0.2.11 — liegen die Dateien in
> einem Ordner, findet er sie nicht und tut gar nichts, ohne Meldung.
> **Genau daran ist ein Versuch schon gescheitert.**
>
> Ab 0.2.13 sucht der Kern eine Ebene tief, ein Ordner ginge dort also
> auch. Oben geht **immer** — deshalb nennt das Helferblatt nur diesen
> einen Weg und erwähnt die Ausnahme nicht. Wer zwei Wege liest,
> wählt den falschen.

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

## Laptop ans Saalnetz, ohne sein Internet zu verlieren

Der Techniker sitzt oft an einem Laptop, der im Gemeinde-WLAN hängt
und dort Internet hat. Das Pult liegt aber im Saalnetz, hinter dem
Zugangspunkt. Beides gleichzeitig geht — über ein **Kabel**.

Ein LAN-Kabel vom Laptop in eine freie LAN-Buchse der Fritzbox (nicht
WAN). Der Laptop bekommt dort eine **feste Adresse** außerhalb des
DHCP-Bereichs, den Devarenu vergibt (`10.0.0.50` bis `10.0.0.200`):

| | |
|---|---|
| Adresse | `10.0.0.20` |
| Maske | `255.255.255.0` |
| Gateway | **leer lassen** |
| DNS | **leer lassen** |

> Gateway und DNS sind der ganze Trick. Trägt man sie ein, schickt
> der Laptop seinen gesamten Verkehr ins Saalnetz — und das hat kein
> Internet. Bleiben beide leer, geht über das Kabel nur, was nach
> `10.0.0.x` adressiert ist; alles andere läuft weiter über das WLAN.

Das Pult steht dann unter **http://10.0.0.1/pult**.

### Windows

1. **Einstellungen → Netzwerk und Internet → Ethernet**
2. Bei *IP-Zuweisung* auf **Bearbeiten**
3. Von *Automatisch (DHCP)* auf **Manuell** stellen, **IPv4** einschalten
4. IP-Adresse `10.0.0.20`, Subnetzmaske `255.255.255.0`
5. **Gateway und DNS leer lassen**, speichern

### macOS

1. **Systemeinstellungen → Netzwerk → Ethernet**
2. **Details…**, dann Reiter **TCP/IP**
3. *IPv4 konfigurieren* auf **Manuell**
4. IP-Adresse `10.0.0.20`, Teilnetzmaske `255.255.255.0`
5. **Router-Feld leer lassen**; im Reiter **DNS** nichts eintragen
6. **OK**, dann **Anwenden**

### Zwei Dinge, die dabei zu wissen sind

**Ein Laptop im Saalnetz zählt nicht als „am Rechner".** Devarenu
unterscheidet, ob das Pult am Gemeinde-PC selbst offen ist oder
irgendwo im Netz — davon hängen die Aufnahmen, das Testprotokoll und
„Jetzt aus dem Netz aktualisieren" ab. Über das Kabel ist der Laptop
im Netz, nicht am Rechner. Das ist richtig so: wer vom Laptop aus
alles dürfte, dürfte es auch vom Handy eines Besuchers aus.

**Alternative ohne Kabel:** ein zweiter WLAN-Stick am Laptop, mit dem
er sich ins Saal-WLAN hängt — dieselben Einstellungen, dieselbe feste
Adresse, auch dort Gateway und DNS leer. Das eingebaute WLAN bleibt
im Gemeindenetz.

## Reicht die Grafikkarte?

Die Frage stellt sich erst, wenn eine Gemeinde eine vierte Sprache
einschaltet oder ein größeres Modell kommt — und dann steht jemand im
Gottesdienst davor. Seit 0.4.3 wird sie vorher beantwortet, aus dem
laufenden Betrieb.

Solange übersetzt wird, misst `grafikwacht.py` alle 30 Sekunden:
belegter und gesamter Grafikspeicher und Auslastung über `nvidia-smi`,
und über `ollama ps`, ob das Sprachmodell **ganz** auf der Karte
liegt. Das zweite ist das wichtigere: fällt ein Teil auf die CPU,
läuft alles weiter — nur zehnmal langsamer, und niemand sieht warum.

Zu sehen am Pult unter *Einrichtung → Fehlersuche*, je Tag eine Zeile.
Lag etwas auf der CPU, steht es zusätzlich in der Störungsansicht. Im
Terminal:

```
python grafikwacht.py --jetzt     einmal nachsehen
python grafikwacht.py             die letzten Tage
```

Fehlt `nvidia-smi` oder schlägt es fehl, wird **still** nichts
gemessen. Eine Messung ist eine Auskunft, kein Betriebsteil.

## Hörprobe: welche Stimme für Englisch und Russisch?

Beide laufen heute mit einer Stimme, deren Lizenz fraglich ist
(`LIZENZEN.md`): `en_US-lessac-medium` gilt „nur für Forschung",
`ru_RU-irina-medium` nennt gar keine. Lizenzfreie Kandidaten sind
gemessen — aber welche Stimme eine dreiviertel Stunde lang erträglich
ist, hört ein Mensch und rechnet kein Skript.

```
python werkzeuge/hoerprobe.py --bauen en
python werkzeuge/hoerprobe.py --bauen ru
```

Das baut je eine Seite unter `pruefung/paket_hoerprobe_<sprache>/`:
zehn Sätze aus `pruefung/saetze_auswahl.csv`, jeder von allen drei
Stimmen gesprochen, jede mit ihrem eigenen Tempo wie im Betrieb. Die
Seite läuft offline im Browser, auch vom Stick.

**Blind, und zwar richtig.** Die Stimmen heißen A, B und C, und die
Zuordnung ist **je Satz eine andere** — wäre sie durchgehend dieselbe,
genügte ein Satz, um sie zu durchschauen, und ab da hörte niemand
mehr die Stimme, sondern seine eigene Vermutung. Am Ende steht dafür
ein fester Block: dreimal derselbe längere Abschnitt als X, Y und Z,
und diese drei bleiben, was sie sind. Die Frage „welche insgesamt?"
bezieht sich darauf.

Die Auflösung steht in `pruefung/schluessel_hoerprobe_<sprache>.json`
— **nicht im Paket** und nicht im Repo (`.gitignore`).

Zurück kommt der Text, den der Knopf „Antworten anzeigen" erzeugt:

```
python werkzeuge/hoerprobe.py --auswerten pruefung/rueck_hoerprobe_en.txt
```

Er löst die Buchstaben auf und zählt je Stimme.

## Am eigenen Gerät testen

Zwei Versuche, den Ton bei gesperrtem Handy weiterlaufen zu lassen,
standen hier bis 0.4.4 mit Testanleitung. Beide sind verworfen; woran
sie gescheitert sind und welche Zahlen gemessen wurden, steht in
`AENDERUNGEN.md` unter 0.4.4 und in `LIESMICH.md` unter „Ton bei
gesperrtem Handy". Die Hörerseite sagt deshalb weiterhin **„Bildschirm
anlassen"** — und dabei bleibt es, solange nichts Besseres gemessen
ist. Der nächste Versuch steht gleich darunter: er greift nicht den Ton
an, sondern den Bildschirm.

### Versuch: bleibt der Bildschirm an? (`?versuch=wach`)

Wake Lock gibt es im Saal nicht — die Seite kommt unter
`http://10.0.0.1`, und das ist kein sicherer Kontext. Handys sperren
nach 30 Sekunden bis 2 Minuten ohne Berührung, und dann endet der Ton.
Der Versuch hält stattdessen ein winziges Video in Schleife: solange
ein Video läuft, lassen viele Browser den Bildschirm an.

| | |
|---|---|
| `?versuch=wach` | einschalten, im Browser gemerkt |
| `?versuch=aus` | wieder weg |

**Ohne den Zusatz ändert sich nichts** — ohne ihn steht nicht einmal
ein `video` im Dokument. Geprüft in `pruefstand/wachvideo_test.mjs`.

#### Woran der erste Anlauf scheiterte

Das Video hatte **keine Tonspur** und war **16×16 Bildpunkte groß**.
Damit bekommt es in keinem Zielbrowser eine Sperre. Auf einem Galaxy
Z Fold 7 ging der Bildschirm nach 30 Sekunden aus — mit und ohne
Adresszusatz.

**Firefox**, `dom/html/HTMLVideoElement.cpp`:

```cpp
// Only request wake lock for video with audio or video from media
// stream, because non-stream video without audio is often used as a
// background image.
return HasVideo() && (mSrcStream || HasAudio());
```

**Chromium** (Chrome, Samsung Internet),
`third_party/blink/renderer/core/html/media/video_wake_lock.cc`:

```cpp
constexpr float kStrictVisibilityThreshold = 0.75f;
constexpr float kSizeThreshold = 0.2f;   // kFractionOfRoot
...
bool has_volume = VideoElement().EffectiveMediaVolume() > 0;
bool has_audio = VideoElement().HasAudio() && has_volume;
bool visibility_requirements_met =
    VideoElement().HasVideo() &&
    (in_picture_in_picture ||
     (page_visible && ((is_visible_ && is_big_enough) || has_audio)));
```

Also drei Änderungen, alle seit 0.4.5-F:

* **Tonspur aus reiner Stille** — AAC im MP4, Opus im WebM. Sie ist
  der eigentliche Schlüssel: sie genügt in *beiden* Browsern für
  sich allein.
* **Nicht stumm, Lautstärke 0,01.** `muted` oder `volume: 0` machen
  `EffectiveMediaVolume()` zu null, und damit `has_audio` zu falsch.
* **Bildschirmfüllend**, fest positioniert, hinter dem Inhalt, ohne
  Berührungen. Das ist der zweite Weg für Chromium, falls die
  Lautstärke doch einmal auf null landet: 20 Prozent des Sichtfelds
  und 75 Prozent Sichtbarkeit sind damit erfüllt. Deckkraft und ein
  Element davor stören dabei nicht — beide Schwellen kommen aus
  einem IntersectionObserver ohne `trackVisibility`, und der rechnet
  rein geometrisch.

Das Medium ist **vier Sekunden** lang, bewusst unter fünf:
`media/base/media_content_type.cc` stuft alles darüber als
`kPersistent` ein, darunter als `kTransient`.

#### So wird getestet

Je Browser ein Durchgang: **Firefox, Chrome, Samsung Internet**, und
wenn ein iPhone zur Hand ist, **Safari**.

**Der Durchgang zählt nur mit laufender Übersetzung.** Ohne sie sagt
er nichts darüber, ob Ton und Video sich vertragen — und genau das
ist die offene Frage. Am Arbeitsrechner geht das ohne Prediger:

```
.venv/bin/python server.py --datei predigt.mp3 --sofort
```

`--datei` speist eine Aufnahme ein, statt das Mikrofon zu öffnen,
`--sofort` fängt ohne Druck aufs Pult an. Die Datei darf alles sein,
was ffmpeg lesen kann; eine halbe Stunde Predigt reicht für mehrere
Durchgänge. (`--tempo 2` geht auch, verfälscht aber jede
Zeitmessung — für diesen Versuch ist es egal.)

1. Am Handy den **Bildschirm-Timeout auf 30 Sekunden** stellen
   (Android: Einstellungen → Display → Bildschirm-Timeout).
2. Am Rechner den Server wie oben starten und warten, bis am Pult
   Abschnitte durchlaufen.
3. `http://<Adresse>:8000/?versuch=wach` öffnen, Sprache wählen,
   **Zuhören** drücken. Es muss Text erscheinen und Ton kommen.
4. In der Leiste unten **zweimal auf „Dunkler"** tippen. Nach dem
   zweiten Mal steht dort **„Heller"** — das ist die dunkelste der
   zwei Stufen, und so würde ein Zuhörer im Gottesdienst sitzen.
5. Das Handy **hinlegen und fünf Minuten nicht berühren.** Nicht
   wischen, nicht tippen, nicht aufheben.
6. Nach fünf Minuten notieren, je Browser:
   * Ist der **Bildschirm** noch an?
   * Läuft der **Ton** noch, und ohne Lücken?
   * Ist er **leiser** geworden?
   * Hängt eine **Medien-Benachrichtigung** in der Leiste, die vorher
     nicht da war?

Die letzten beiden Fragen gehören dazu, weil das Video jetzt eine
Tonspur hat. Es soll den Übersetzungston weder ducken noch eine
eigene Benachrichtigung erzeugen; die vier Sekunden Laufzeit sollen
das verhindern, **aber belegt ist das nur im Quelltext, nicht am
Gerät.**

Bleibt der Bildschirm an und der Ton hört trotzdem auf, dann liegt es
nicht am Bildschirm. Bleibt der Bildschirm aus, steht im Protokoll,
woran: unter der Textspalte aufklappen, **Versuch: Protokoll**. Dort
stehen der Start des Videos, abgelehnte `play()`-Aufrufe und jeder
Wechsel der Sichtbarkeit. Nichts davon geht an den Server.

#### Was der Versuch kostet

**Korrigiert gegenüber der ersten Fassung dieses Abschnitts.** Dort
stand, das Video sei „die kleinste Last, die ein Videodekoder
überhaupt annehmen kann". Für das Dekodieren stimmt das weiterhin —
es sind nach wie vor 16×16 Bildpunkte bei zwei Bildern je Sekunde,
und daran hat die Tonspur nichts geändert: vier Sekunden digitale
Stille sind für einen Audiodekoder nichts.

Was sich geändert hat, ist das **Zusammensetzen**. Das Element ist
jetzt bildschirmfüllend, also mischt der Compositor bei jedem Bild
eine sichtfeldgroße Ebene über den Hintergrund statt eines Quadrats
von zwei Pixeln. Das ist mehr als vorher, aber es ist dieselbe Arbeit,
die jede Seite mit einem Hintergrundbild macht, und sie läuft auf der
Grafikeinheit.

**Der Bildschirm bleibt der Verbrauch, nicht das Video.** Genau
deshalb gehört das Abdunkeln auf die dunkelste Stufe in den
Durchgang: auf einem OLED-Bildschirm ist eine dunkle Fläche auch die
sparsame. Gemessen ist das alles nicht — wer es wissen will, liest
den Akkustand vor und nach den fünf Minuten ab und notiert ihn
daneben.

### Damit das Handy den Rechner erreicht

Der Server hört auf **allen** Adressen (`0.0.0.0`), Port **8000**.
Port 80 kommt nur dazu, wenn der Rechner selbst das Saalnetz stellt —
beim Testen im Heimnetz also nicht. Die Portnummer gehört darum in die
Adresse.

Zwei Dinge können im Weg stehen:

**Die Adresse.** Welche der Rechner im Heimnetz hat:
```
ip -4 -o addr show scope global | awk '{print $2, $4}'
```

**Die Firewall.** Läuft eine, ist Port 8000 von außen zu:
```
sudo ufw status verbose
```
Öffnen — nur für das eigene Netz, nicht für alle. `<NETZ>` ist das
Netz aus der Ausgabe des `ip`-Befehls oben, mit `.0/24` am Ende: aus
`192.0.2.17/24` wird also `192.0.2.0/24`.
```
sudo ufw allow from <NETZ> to any port 8000 proto tcp comment "Devarenu Test"
```
Und hinterher wieder zu:
```
sudo ufw delete allow from <NETZ> to any port 8000 proto tcp
```

> Eine Regel ohne `from` öffnet den Port für jeden, der den Rechner
> erreicht. Zum Testen ist das nicht nötig, und offen bleibt sie
> erfahrungsgemäß länger als geplant.

### Das Pult

```
node pruefstand/pult_test.mjs
node pruefstand/pult_test.mjs --bilder     # braucht firefox
```

Das Pult hat seit 0.4.1 vier Reiter. Damit kann etwas verschwinden,
ohne dass es auffällt: ein Knopf, den niemand mehr erreicht, sieht aus
wie ein aufgeräumtes Pult. Deshalb trägt `pult_test.mjs` die
**Bestandsaufnahme** mit — eine Zeile je Bedienelement mit dem Ort, an
dem es liegen soll — und prüft für jedes, dass es existiert, dass es
dort liegt, und dass man von der Startseite aus hinkommt. Was eine
Ebene tiefer steht (hinter einem „?" oder in der Feineinstellung), ist
als solches vermerkt und wird auch so geprüft.

Dazu: die acht Zustände (bereit, läuft, kein Ton, Thema fehlt, Aufnahme
läuft, Update wartet, Meldung aus dem Saal, aus dem Saal geöffnet), die
Reiterbedienung mit Tastatur, die roten Bänder in jedem Reiter, die
Rückstau-Regel, die drei Schwellenmodi, die Vollständigkeit beider
Sprachtabellen, die Farbregel, die Fingergröße, die logischen Ränder
für Farsi und der Kontrast jedes Farbpaars.

Gerechnet wird gegen einen nachgebauten Browser (`pultnachbau.mjs`) mit
einem kleinen HTML-Parser: das Pult greift Elemente über ihre Kennung
als globale Namen an, und ein Nachbau, der jede Anfrage mit einem
frischen leeren Element beantwortet, bestätigt jede Behauptung.

`--bilder` rendert das Pult mit Attrappendaten in acht Gerätegrößen
(320×568 bis 1366×768, einmal quer, einmal mit 150 % Schriftgröße) und
legt die Bilder unter **`/tmp/devarenu_pult/`** ab — **nie im Repo**.
Es braucht `firefox`.

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

## Eine Sprache prüfen lassen

Devarenu übersetzt in einundzwanzig Sprachen. Geprüft hat die
Fachbegriffe bisher niemand außer für Deutsch, Englisch, Russisch und
Persisch — alles andere ist maschinell und läuft am Pult als
*experimentell*, mit gestricheltem Rand.

Was eine Sprache aus diesem Zustand holt, ist **ein Mensch aus der
Gemeinde**, der sie als Muttersprache spricht. Nicht ein besseres
Modell.

### Was der Prüfer bekommt

Zwei Dinge, beide ohne Technik zu bearbeiten:

| | |
|---|---|
| `pruefung/begriffe_<sp>.docx` | 93 Fachbegriffe, dazu die Texte der Zuhörerseite, der QR-Seite und der Anleitung |
| `pruefung/paket_<sp>/` | 20 gesprochene Sätze im Browser, dazu drei Stimmproben |

Im Dokument füllt er **nur die Spalte Korrektur** aus. Was er leer
lässt, gilt als richtig — das steht oben auf jeder Seite. Die Spalte
*Kennung* ist ausgegraut: sie geht ihn nichts an, sie ist der Rückweg.

Vorn stehen **zwei Fragen**, die über Dutzende Einzelfälle entscheiden
und deshalb nicht hinten stehen dürfen: welche Bibelübersetzung gilt,
und wie die Gemeinde angeredet wird.

Im Bewertungspaket hört er zuerst **drei Stimmen** denselben Text
sprechen und wählt. Die Messung wählt nicht aus, sie stellt nur zur
Wahl: welche Stimme über eine dreiviertel Stunde erträglich ist, hört
ein Mensch und rechnet kein Skript.

### Bauen

```fish
# 1. Stimmen: alle Kandidaten messen
python laengenfaktor.py --je-stimme --nur <sp>

# 2. Glossarspalte, Übersetzungen, Bewertungspaket
python werkzeuge/sprachpaket.py --bauen <sp>

# 3. Das Dokument -- im BAU-venv, es braucht python-docx
.bau-venv/bin/python werkzeuge/sprachpaket.py --dokument <sp>
```

Zwei venvs, und das ist Absicht: `python-docx` gehört nicht auf den
Gemeinderechner. Das Skript sagt es, wenn es im falschen läuft.

**Vorher anlegen**, sonst wird das Paket schwächer:

- `pruefung/fallstricke_<sp>.csv` — acht Sätze, die genau dort
  hinlangen, wo die allgemein kirchliche Übersetzung etwas anderes
  heißt als die adventistische. Für Polnisch: `msza`, `komunia`,
  `spowiedź`, `parafia`, `sakrament`.
- `ANKER` in `werkzeuge/sprachpaket.py` — dieselben Fälle als
  Wortpaare. **Ohne sie sind die Maschinenvorschläge unbrauchbar.**
  Gemessen an acht Begriffen: ohne Anker kam *„Abendmahl = Wiecień
  Pański"* (kein polnisches Wort) und *„Kościół Kościoła
  Adwentystów"*; mit Ankern *Wieczerza Pańska* und *Kościół
  Adwentystów Dnia Siódmego*. Das ist der Unterschied zwischen einer
  Liste, die jemand korrigiert, und einer, die er wegwirft.

Die neue Glossarspalte landet in einer **neuen** Fassung
(`glossar_v0.8.csv`) und wird **nicht** aktiv geschaltet. Welche Datei
`config.GLOSSAR_CSV` nennt, entscheidet ein Mensch nach einem Testlauf.

### Zurück

```fish
python werkzeuge/sprachpaket.py --einlesen pruefung/rueck_<sp>/
python werkzeuge/sprachpaket.py --einlesen pruefung/rueck_<sp>/ --scharf
```

In den Ordner gehören das ausgefüllte `begriffe_<sp>.docx` und die
`bewertung_<sp>.csv`, die der Knopf *Bewertung speichern* im Browser
erzeugt.

**Der Trockenlauf ist die Vorgabe, nicht eine Option.** Er zeigt jede
Änderung einzeln — alt in Rot, neu in Grün — und fasst nichts an. Was
hier eingetragen wird, sind die Worte, die im Gottesdienst gesprochen
werden; das sieht man sich vorher an.

Mit `--scharf` werden eingetragen:

| Kennung | wohin |
|---|---|
| `A001`, `C012`, `D033` | die Sprachspalte im Glossar |
| `UI.*` | `client.html`, als eigener Sprachblock in `TEXTE` |
| `QR.*` | `qr_texte.py` |
| `AN.*` | `anleitung/01_zuhoerer.<sp>.md` |

Danach steht die Sprache in `config.GEPRUEFT`, und das Pult zeigt sie
ohne gestrichelten Rand.

**Was der Rückweg nicht tut:** die Stimme umstellen. Er nennt die
gewählte; `config.STIMMEN` setzt ein Mensch. Eine Stimme zu wechseln
heißt, dass jeder Zuhörer ab dem nächsten Sabbat eine andere hört.

Danach noch von Hand:

```fish
bash anleitung_bauen.sh      # das Zuhörer-PDF in der neuen Sprache
```

### Die virtuelle Testmaschine

**Jedes Update läuft zuerst dort und dann auf dem Gemeinderechner.**
Anleitung, Skript und — wichtiger — die ehrliche Liste, *was die VM
nicht prüft*: [VM-TESTUMGEBUNG.md](VM-TESTUMGEBUNG.md).

Der Grund steht in der Geschichte: 0.3.1 schrieb die Units nie, 0.3.3
brach an einem `[ -f … ]` ohne `sudo` ab, 0.3.7 versteckte einen
Pult-Schalter. Alle drei wären auf einer VM aufgefallen, und keiner
davon brauchte eine Grafikkarte, ein Mikrofon oder einen Saal.

Dazu gehört der **Testmodus** (`testmodus.py`): Whisper als `tiny` auf
der CPU, damit ein Prüflauf Minuten dauert und nicht eine Stunde. Er
greift nur, wenn die Datei `TESTMODUS` daliegt **und** der Rechner
keine NVIDIA-Karte hat — die zweite Bedingung ist die eigentliche
Sperre, denn Dateien wandern. Liegt die Marke doch einmal auf dem
Gemeinderechner, sagt der Systemcheck es (`testmodus_marke`), obwohl
sie dort nichts tut.

### Der Signierschlüssel

`schluessel.erlaubt` ist der Vertrauensanker. Ein Update — über Stick
oder über das Netz — wird nur eingespielt, wenn sein Tag mit einem
Schlüssel aus dieser Datei signiert ist. Geprüft wird immer gegen die
Datei, die auf dem Rechner **liegt**, nie gegen die im Bundle.

**Mehrere Schlüssel gehen.** Eine Zeile je Schlüssel; Kommentare und
Leerzeilen dazwischen stören nicht. Nachgewiesen in
`pruefstand/online_test.sh`, Abschnitt *Zwei erlaubte Schlüssel*: ein
Tag, das mit dem zweiten Schlüssel signiert ist, läuft durch, und ein
dritter, nicht eingetragener wird abgewiesen.

**Die Adresse vor dem Schlüssel ist ein Etikett, keine Bedingung.** Bis
0.3.8 behauptete der Kommentar in der Datei das Gegenteil. Gemessen
(git 2.55.0, OpenSSH 10.5): `git verify-tag` nimmt ein Tag an, solange
der **Schlüssel** in der Datei steht — auch wenn davor eine andere
Adresse steht als im Tagger-Feld. git schreibt dann die Adresse *aus
der Datei* in seine Meldung. Wer einen Schlüssel sperren will, löscht
die **Zeile**; eine Adresse zu ändern bewirkt nichts.

#### Einen zweiten Schlüssel dazunehmen

Die Reihenfolge ist der ganze Punkt. Andersherum sperrt man sich aus:
ein Rechner, der den neuen Schlüssel noch nicht kennt, nimmt kein
Update mehr an — auch nicht das, das ihn mitbringen würde.

```fish
ssh-keygen -t ed25519 -C "devarenu-freigabe-2" -f ~/.ssh/devarenu_freigabe2
```

1. Zeile in `schluessel.erlaubt` ergänzen, **den alten Schlüssel stehen
   lassen**.
2. Diese Fassung mit dem **alten** Schlüssel signieren und ausliefern:
   ```fish
   git config user.signingkey ~/.ssh/devarenu_freigabe.pub
   ```
   ```fish
   git tag -s v0.4.1 -m "Devarenu 0.4.1"
   ```
3. Warten, bis **jeder** Rechner diese Fassung hat. Nachsehen über die
   Nutzungsmeldung oder durch Nachfragen.
4. Erst danach mit dem neuen Schlüssel signieren.
5. Den alten erst im **übernächsten** Update entfernen.

Zwischen Schritt 1 und 5 sind beide Schlüssel gültig. Das ist Absicht:
in diesem Fenster lässt sich der Wechsel noch zurücknehmen.

#### Den vorhandenen Schlüssel sichern

Der private Schlüssel liegt in `~/.ssh/devarenu_freigabe` auf dem
Entwicklungsrechner. **Geht er verloren, kann niemand mehr ein Update
signieren** — die Gemeinderechner nehmen dann keine neue Fassung an,
und es bleibt nur, auf jedem Rechner von Hand eine neue
`schluessel.erlaubt` einzutragen. Vor Ort, an jedem Gerät.

Darum zwei Kopien, und nicht beide am selben Ort:

```fish
ssh-keygen -y -f ~/.ssh/devarenu_freigabe
```
Zeigt den öffentlichen Teil — damit lässt sich prüfen, ob eine Kopie
die richtige ist.

Die private Datei gehört **verschlüsselt** auf zwei getrennte Medien.
Wer mag, legt sie mit einer Passphrase an (`ssh-keygen -p -f …`) — dann
ist eine Kopie auf einem Stick vertretbar, und die Passphrase gehört
dann dorthin, wo sonst nichts liegt.

Ein Schlüssel ohne Passphrase, der in einer Dateisicherung mitläuft,
ist kein Schlüssel mehr. Das ist derselbe Gedanke wie bei
`sichern.sh`: Geheimnisse nur verschlüsselt, und die Passphrase
getrennt.

### Sicherung auf eine tragbare Platte

`sichern.sh` und `zuruecksichern.sh`, seit 0.4.0. Gedacht für den Fall
„Platte hin, Rechner neu aufsetzen".

**Zwei Teile, und die Trennung ist der Kern.**

| Teil | Inhalt | Zustand |
|---|---|---|
| `geheim.tar.gz.gpg` | `zustand.json`, `netz.json`, `meldung.json`, NetworkManager-Profile, RustDesk-Einstellungen | mit Passphrase verschlüsselt, `600` |
| `offen/` | Modelle, Stimmen, Reparaturvorrat, Fassung, Commit-SHA, Tongeräteliste | unverschlüsselt |

Im geheimen Teil stehen das WLAN-Passwort, das ntfy-Thema und das
RustDesk-Kennwort. Der offene Teil ist nicht geheim, aber groß.

**Die Passphrase wird beim Sichern abgefragt und nirgends
gespeichert.** Sie steht auch nicht in der Befehlszeile — dort könnte
sie jeder mitlesen, der `ps` tippt — sondern geht über einen
Dateideskriptor an `gpg`.

**Ohne Passphrase sind die Geheimnisse weg** und müssen neu eingetragen
werden: WLAN am Pult, ntfy-Thema in `meldung.json`, RustDesk in
RustDesk. **Alles andere lässt sich trotzdem wiederherstellen** —
`zuruecksichern.sh --ohne-geheim` macht genau das und sagt beim
Durchlauf, was offen bleibt.

**Warum `gpg` und nicht `openssl enc`.** `gpg` bringt einen
ordentlichen Schlüsselableiter mit (S2K, hier mit dem höchsten
Zählwert) und schützt die Datei gegen unbemerkte Veränderung.
`openssl enc` kann beides nicht von sich aus. Und `gnupg` ist auf einem
Arch-System ohnehin da: `pacman` braucht es für die Paketsignaturen.
`gpg` läuft dabei mit einem eigenen Verzeichnis im Wegwerfordner — der
Schlüsselbund des Benutzers wird nicht angefasst.

**Was ausdrücklich nicht in die Sicherung geht: die Aufnahmen.** Sie
werden nach sieben Tagen gelöscht, und eine Sicherung, die sie
mitnimmt, hebelt diese Zusage aus. `pruefstand/sicherung_test.sh`
prüft das mit.

### Der Knopf „Jetzt aus dem Netz aktualisieren"

Am Pult unter *Einrichtung*, seit 0.4.0. Er spart den Weg ins Terminal
— niemand muss `bash aktualisieren.sh` tippen.

**Nur am Gemeinde-PC selbst.** Dieselbe Schranke wie bei Aufnahmen und
Testprotokoll (`nur_am_rechner`). Ein Pult-Passwort würde das nicht
ersetzen: es ginge im Saalnetz unverschlüsselt über HTTP, und ein
Update, das sich von dort anstoßen lässt, ist ein Update, das jeder
anstoßen kann, der im WLAN ist. **Über RustDesk geht es**, denn dort
läuft der Browser auf dem Rechner selbst — für den Server ist das
Loopback.

**Warum ein Marker und kein `sudo`.** Der Server läuft als `devarenu`,
das Update braucht root. Eine `sudo`-Regel für den Dienstbenutzer stünde
dauerhaft offen, und wer den Server übernimmt, übernimmt sie mit.
Stattdessen legt der Server eine Datei in seinem eigenen Ordner an —
`update/online-jetzt` —, und `devarenu-onlineupdate.timer` sieht als
root alle 30 Sekunden danach. Der Dienst bekommt **kein einziges Recht
mehr**, als er ohnehin hat: es gibt keinen Parameter, den er
unterschieben könnte, und keinen Befehl, den er wählen kann. Derselbe
Weg, den der Stick-Knopf seit 0.2.12 geht.

Der Preis sind bis zu 30 Sekunden, bis etwas passiert. Das steht am
Pult, sonst drückt jemand ein zweites Mal.

**Der Ablauf** (`wartungsfenster.sh --jetzt`, als root):

1. Läuft eine Übersetzung? Dann nichts, mit Begründung am Pult.
2. Fenster-Timer anhalten — sonst stolpert er mitten im Update über
   ein Repo, das gerade vorgespult wird.
3. Das eingetragene Wartungs-WLAN verbinden. Gibt es keines oder lässt
   es sich nicht verbinden, wird die Verbindung benutzt, **die gerade
   besteht** — etwa ein Handy-Hotspot, den der Helfer per Klick
   verbunden hat. Getrennt wird am Ende nur, was Devarenu selbst
   verbunden hat.
4. `aktualisieren.sh`, als Dienstbenutzer (ihm gehört das Repo).
5. Rückmeldung über `meldung.sh`, **solange das WLAN noch steht**.
6. Trennen, Timer wieder an.

Fortschritt und Ergebnis stehen in `update/online-lauf.json` und damit
am Pult. **Ein zweiter Klick während eines Laufs startet nichts Neues**
— die Entscheidung sitzt im Server, nicht in der Oberfläche: wer zwei
Pulte offen hat, sieht auf dem einen noch den Stand von vorhin.

**Stromausfall mitten im Update.** Dann steht in
`online-lauf.json` weiter „läuft", und niemand hat es beendet. Beim
nächsten Hochfahren berichtigt `--jetzt-aufraeumen` das auf
„abgebrochen" mit dem Hinweis auf `pruefen.sh`; der Systemcheck meldet
es ebenfalls. Zurückgerollt hat sich `aktualisieren.sh` selbst, falls
es bis dahin kam — und ein Repo mit halbem Stand lässt es beim nächsten
Lauf nicht an sich heran, sondern bricht ab und sagt es.

### Das Glossar aktiv schalten

Seit 0.4.0 ist `config.GLOSSAR_CSV` = `glossar_v0.9.csv`. Davor zeigte
es über vier Arbeitsstände hinweg auf `v0.4` — die geprüften Sprachen
standen in der neueren Datei, liefen live aber ohne
Fachwortverzeichnis. Das war der schlechteste der drei Zustände, weil
er nach dem besten aussah.

Zum Umschalten gehört dreierlei, und alles drei ist getan:

1. **`config.GLOSSAR_CSV`** zeigt auf die neue Fassung.

2. **`start.sh`** prüft die Glossardatei beim Namen aus
   `config.GLOSSAR_CSV`, nicht als feste Zeichenkette. Fehlt sie nach
   einem Update, fällt es beim Start auf und nicht mitten im
   Gottesdienst. Dasselbe gilt für den Prüfstand (`pruefstand/hilfe.py`,
   `BEIWERK`).

3. **Der Vergleichslauf** ist ein Werkzeug und ein Prüfstandfall:

   ```fish
   python werkzeuge/glossar_vergleich.py glossar_v0.4.csv glossar_v0.9.csv
   ```

   Verglichen wird nicht die Datei, sondern das Ergebnis: der Text, den
   `glossarzeilen()` dem Sprachmodell vorgibt, über 1444 Texte (die 40
   Testsätze samt Kontext plus jede deutsche Form beider Fassungen,
   allein und in einem Satz). Dazu der Whisper-Prompt und die
   persische Vokalisierung. Rückgabe 0 heißt: Zeichen für Zeichen
   dasselbe.

**Warum das mehr ist als eine Formalie.** Das Glossar wirkt nicht über
die Spalte, sondern über die **Suchvarianten**. `glossar.finde()`
sortiert sie nach Länge und lässt die erste, die eine Textstelle
beansprucht, gewinnen. Eine neue Zeile „28 Glaubensüberzeugungen" ist
länger als die Variante „Glaubensüberzeugungen" an D034 — sie gewinnt,
D034 fällt als Überlappung weg, und weil die neue Zeile für Englisch
leer ist, fehlt „fundamental beliefs" plötzlich im englischen Prompt.
In der CSV sieht man davon nichts.

Beim Bauen von `v0.9` ist das **neun Mal** passiert.
`werkzeuge/glossar_rueck_es_pt.py` prüft jede neue Zeile vorher und
weist sie ab; die neun stehen im Bericht zu 0.4.0 und warten auf
geprüfte Werte für en, ru und fa.

### Warum die Pakete nicht ins Repo gehören

`pruefung/paket_*` ist gitignoriert. Ein Paket sind rund neun Megabyte
Ton, und das Repo geht per `git bundle --all` auf **jeden**
Update-Stick. Was einmal darin ist, trägt jede Gemeinde für immer mit.

Die Quellen dagegen gehören hinein: `fallstricke_<sp>.csv`,
`saetze_auswahl_<sp>.csv`, `vorschlag_<sp>.json` und das Glossar. Aus
ihnen ist ein Paket in Minuten wieder gebaut.

## Bei jeder Fassung mitzupflegen

- [ ] `VERSION` hochsetzen.
- [ ] `AENDERUNGEN.md` — ausführlich, mit Begründungen. Das ist das
      Gedächtnis des Projekts.
- [ ] **`VERSIONEN.md`** — die kurze Übersicht, neueste oben. Eine
      Zeile mit Nummer und Datum, darunter ein bis acht kurze Zeilen
      in einfacher Sprache: was sich für Gemeinde und Bediener
      ändert. Keine Begründungen, keine Dateinamen, keine
      Zeilennummern — dafür ist `AENDERUNGEN.md` da.
      **Die ganze Datei passt auf eine A4-Seite.** Reicht sie nicht,
      werden ältere Fassungen zusammengefasst (`0.2.1 bis 0.2.9`),
      nicht eine zweite Seite angefangen. Gebaut wird sie als PDF von
      `anleitung_bauen.sh` mit; der Bau bricht ab, wenn sie länger
      wird.
- [ ] `anleitung/DATUM` und die PDFs neu bauen.

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
      python pruefstand/pultschutz_test.py
      python pruefstand/qrseite_test.py
      node  pruefstand/sprachwechsel_test.mjs
      ```
      Der letzte braucht **node**, und zwar nur auf dem Arbeitsrechner.
      Er fährt das echte Skript aus `client.html` gegen einen
      nachgebauten Browser. Auf den Gemeinderechner kommt node nicht,
      und in `requirements.txt` hat es nichts verloren.
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

      Damit niemand daran denken muss, legt
      ```
      bash werkzeuge/hook_einrichten.sh
      ```
      einen `pre-push`-Hook an: ein Push mit Fund bricht ab. Der Hook
      liegt in `.git/hooks` und wird nicht mitversioniert — er muss
      auf jedem Rechner einmal eingerichtet werden. Umgehen geht mit
      `git push --no-verify`, und das ist Absicht: ein Hook, den man
      nicht umgehen kann, wird irgendwann gelöscht statt verstanden.
- [ ] Ändern sich große Teile (Modell, Stimmen, Spracherkennung):
      ```
      python teile.py --erfassen
      ```
      und `teile.json` mit einchecken.

      **Seit 0.4.2 steht `teile.json` immer im Repo** — ein Rechner
      ohne Internet soll bei jedem Update sehen können, was
      dazugehört. Sie wird aus `config.STIMMEN`, `WHISPER_MODELL` und
      `LIVE_MODELL` aufgezählt, nicht aus dem aufgesammelt, was gerade
      unter `voices/` liegt: auf einem Entwicklungsrechner liegen dort
      auch Stimmen, die niemand eingestellt hat.

      Die Windows-Batch-Datei fragt deshalb nicht mehr, **ob** es die
      Datei gibt, sondern ob sie sich gegenüber der Vorgängerfassung
      **geändert** hat. Nur dann reicht ihr Weg nicht und sie verweist
      auf `stick_bauen.sh --voll`.
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

Seit 0.3.2 gelten dabei **dieselben Regeln wie beim Stick**:

- Vorgespult wird nur auf ein **Tag**, nie auf `main`.
- Das Tag muss mit einem Schlüssel aus `schluessel.erlaubt` signiert
  sein — der Liste, die **hier** liegt, nie einer geholten.
- Vorgespult wird über die geprüfte **Commit-SHA**, nie über den
  Tagnamen: ein gleichnamiges lokales Tag würde sonst etwas
  Ungeprüftes unterschieben.
- Die Fassung muss neuer sein. Verglichen wird mit `sort -V`, nicht
  als Zeichenfolge — sonst käme 0.2.9 nach 0.2.13.

Bis 0.3.1 stand hier `git pull --ff-only`: es galt, worauf
`origin/main` gerade zeigte, ohne Signatur und ohne Tag. Über den
Stick war genau das seit 0.2.12 unmöglich — über das Netz blieb es
offen.

**Und die Units kommen mit.** Der alte Weg startete nur den Dienst neu;
geschrieben wurden die Units allein von `dienst.sh` bei der
Ersteinrichtung. Nach dem Einspielen von 0.3.1 am 27.09. liefen sie
deshalb in alter Fassung, bis jemand `dienst.sh` von Hand aufrief.
Jetzt übergibt `aktualisieren.sh` an `aktualisierung.sh`, die
versionierte Hälfte des Updaters — dieselbe Datei, die auch ein Stick
ausführt. Eine Logik, zwei Wege.

`bash pruefstand/online_test.sh` prüft die vier Fälle, die zusammen
die Regel ergeben: gültig signiert geht durch, fremd signiert nicht,
nachträglich umgebogen nicht, und ein `main`, das weiter ist als das
letzte Tag, zählt nicht.

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
