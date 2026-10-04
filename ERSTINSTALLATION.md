# Devarenu aufsetzen — Schritt für Schritt

Diese Anleitung ist für jemanden geschrieben, der **das Projekt nicht
kennt**: ein Systemhaus, ein Bekannter mit Linux-Erfahrung, der
Nachfolger des heutigen Betreuers. Sie läuft von oben nach unten durch.
Nach jedem Abschnitt steht eine **Kontrolle** mit dem Befehl und dem,
was herauskommen muss.

**Jede Rückfrage, die beim Abarbeiten entsteht, ist eine Lücke in
diesem Dokument** und gehört hineingeschrieben, nicht beantwortet.

Alle Befehle sind für `fish` und stehen einzeln. Wer `bash` benutzt,
tippt sie genauso.

---

## Was vorher dasein muss

**Gerät**

- Ein Rechner mit NVIDIA-Grafikkarte (getestet: RTX 5080). Ohne GPU
  läuft die Übersetzung nicht in Echtzeit.
- **Zwei Netzwerkanschlüsse.** Einer für das Hausnetz oder nichts,
  einer für den Zugangspunkt im Saal. Eine USB-Netzwerkkarte genügt.
- Ein WLAN-Zugangspunkt, als **reiner Access Point** konfiguriert
  (kein DHCP, kein Router). Die Adressen verteilt Devarenu selbst.
- Mikrofon am Pult. Getestet mit einem Behringer UMC202HD am
  Mischpultausgang.
- Für die Einrichtung: eine Internetleitung — **oder** ein voller
  Stick, siehe unten. **Im Betrieb braucht der Rechner keine.**
- Ein USB-Stick und eine tragbare Platte für die Sicherung. Für den
  vollen Weg ohne Internet braucht der Stick **32 GB**; für den Weg
  mit Leitung genügen 8 GB.

**Angaben von der Gemeinde** — ohne die kommt man an zwei Stellen nicht
weiter:

| Was | Wofür | Wo eingetragen |
|---|---|---|
| Name und Passwort eines WLANs, das Internet hat | das Wartungsfenster, damit sich der Rechner selbst aktualisiert | am Pult unter *Einrichtung* |
| Name der Gemeinde | Anzeige auf der QR-Seite | am Pult unter *Einrichtung* |
| Sprachen der Zuhörer | welche Übersetzungen mitlaufen | am Pult unter *Übersetzt nach* |

Das WLAN kann auch der Hotspot eines Handys sein, das jemand einmal im
Monat mitbringt. Es muss nicht dauerhaft stehen.

---

## 1. Betriebssystem

CachyOS oder Arch Linux installieren, mit einem Benutzer. Der
Benutzername ist frei; in dieser Anleitung heißt er `devarenu`.

**Automatische Anmeldung einschalten** — der Rechner steht im
Gemeindesaal, und niemand soll am Sonntag ein Passwort tippen müssen.
Wie das geht, hängt von der Arbeitsumgebung ab (KDE: *Systemeinstellungen
→ Startvorgang → Automatische Anmeldung*). `pruefen.sh` sagt später, ob
es greift.

> **Kontrolle**
> ```fish
> uname -a; echo $USER
> ```
> Es muss ein Linux und der angelegte Benutzer dastehen.

---

## 2. Devarenu holen und einrichten

```fish
git clone https://github.com/Auroramomo/Devarenu.git ~/Devarenu
```
```fish
cd ~/Devarenu
```
```fish
bash INSTALLIEREN.sh
```

Das dauert; es lädt Python-Pakete, das Spracherkennungsmodell, die
Stimmen und das Übersetzungsmodell. Rund zehn Gigabyte.

### Ohne Internet: alles vom Stick

Hat der Raum keine Leitung, bringt ein **voller Stick** dieselben
Dateien mit. Gebaut wird er dort, wo eine Leitung liegt:

```fish
bash stick_bauen.sh /pfad/zum/stick --voll
```

Er trägt dann `teile/` mit allem, was `teile.json` nennt: jede Stimme
aus `config.STIMMEN`, die Spracherkennung und das Sprachmodell. Auf
dem neuen Rechner, nach `INSTALLIEREN.sh`:

```fish
.venv/bin/python teile.py --einspielen \
    --quelle /pfad/zum/stick/teile --sicherung /tmp/devarenu-teile
```

Eingespielt wird nur, was fehlt oder abweicht, und jedes Stück wird
gegen seine `sha256` geprüft, **bevor** etwas ersetzt wird. Stimmt
eine nicht, bleibt alles, wie es war.

> **Kontrolle: alle Stimmen da?**
> ```fish
> .venv/bin/python teile.py --pruefen
> ```
> Muss sagen: *… stimmen, 0 fehlen, 0 weichen ab*. Steht dort eine
> Zahl über null, nennt die Ausgabe, welche Datei es betrifft. Eine
> fehlende Stimme heißt: diese Sprache läuft am Sonntag als Untertitel,
> ohne Ton — und steht danach am Pult unter *Einrichtung →
> Fehlersuche*.

> **Kontrolle**
> ```fish
> .venv/bin/python selbsttest.py
> ```
> Muss grün durchlaufen. Bleibt er bei *Ollama* oder dem
> *Sprachmodell* stehen, fehlt beides noch — er sagt, womit
> weiterzumachen ist.

---

## 3. Ton

Mikrofon anschließen. Dann den Server von Hand starten:

```fish
bash start.sh
```

Im Browser auf demselben Rechner `http://localhost:8000/pult` öffnen.
Unter **Tonquelle** das Gerät auswählen. Dann:

1. **Einmessen** drücken und den Prediger (oder sich selbst) zwölf
   Sekunden sprechen lassen. Das setzt die Mindestlautstärke.
2. **Sprache prüfen** drücken.

> **Kontrolle**
> Es muss der **gesprochene Satz** erscheinen, nicht nur ein Pegel.
> Kommt nichts, ist das falsche Gerät gewählt oder das Mischpult gibt
> nichts aus. Hilft `bash tondiagnose.sh`.

Danach den Server mit `Strg+C` beenden.

---

## 4. Als Dienst einrichten

Damit Devarenu nach einem Stromausfall von selbst wiederkommt.

```fish
sudo bash rechner_einrichten.sh
```
```fish
sudo bash dienst.sh
```

> **Kontrolle**
> ```fish
> systemctl is-active devarenu; systemctl is-enabled devarenu
> ```
> Muss `active` und `enabled` sagen.
> ```fish
> systemctl is-enabled devarenu-update.timer devarenu-onlineupdate.timer devarenu-fenster.timer
> ```
> Alle drei `enabled`. Der erste holt Updates vom USB-Stick, der zweite
> den Knopf am Pult, der dritte das Wartungsfenster.

---

## 5. Das Saalnetz

Kabel vom Zugangspunkt in die **zweite** Netzwerkkarte. Welche das ist:

```fish
ip -br link show
```

Dann erst trocken, dann scharf:

```fish
sudo bash netz_einrichten.sh --trocken
```
```fish
sudo bash netz_einrichten.sh
```
```fish
sudo bash firewall.sh --schnittstelle <karte>
```

`netz_einrichten.sh` verlangt beim ersten Lauf den Rechnernamen — das
ist die Sicherung dagegen, dass es versehentlich auf einem
Arbeitsrechner läuft und dort ein DHCP aufmacht.

> **Kontrolle**
> ```fish
> systemctl is-active dnsmasq
> ```
> Muss `active` sein. Sagt es `failed`, hält meist `systemd-resolved`
> den Port 53: `sudo systemctl disable --now systemd-resolved`.
> ```fish
> sysctl net.ipv4.ip_forward
> ```
> **Muss `0` sein.** Steht dort `1`, leitet der Rechner das Saalnetz
> ins Hausnetz weiter. Das darf nicht sein.
> ```fish
> stat -c '%a %n' /run/devarenu/dnsmasq.leases
> ```
> `640`. Darin stehen MAC-Adressen und Handynamen.

---

## 6. Probe mit einem Handy

QR-Seite am Beamer öffnen: `http://10.0.0.1/qr` (oder die Adresse, die
`netz_einrichten.sh` genannt hat).

Mit einem Handy **beide** Codes scannen: der erste verbindet das WLAN,
der zweite öffnet die Seite. Sprache wählen, zuhören.

> **Kontrolle**
> - Es muss Ton auf dem Handy kommen, über Kopfhörer.
> - **Mobile Daten am Handy ausschalten** und noch einmal probieren.
>   Das ist der Zustand, den die Zuhörer haben.
> - Fünf Minuten Bildschirm aus, bei laufender Wiedergabe: der Ton
>   muss weiterlaufen.
> - Am Pult nachsehen, ob dort eine Warnung über einen **zweiten
>   DHCP-Server** steht. Wenn ja, verteilt der Zugangspunkt noch
>   selbst Adressen — das gehört bei ihm abgeschaltet.

Die **Übersetzung gehört nie auf Lautsprecher im selben Raum wie das
Predigermikrofon.** Sonst hört das Mikrofon die eigene Ausgabe,
übersetzt sie erneut und schaukelt sich auf. Kopfhörer am Handy.

---

## 7. Reparaturvorrat

Solange noch eine Internetleitung da ist. Der Vorrat liegt auf der
Platte und erlaubt, Stimmen, Pakete und das Modell **ohne Netz**
wiederherzustellen.

```fish
sudo bash vorrat_bauen.sh
```

> **Kontrolle**
> ```fish
> bash vorrat_bauen.sh --pruefen
> ```
> Muss die Fassung nennen, zu der der Vorrat gebaut wurde — dieselbe,
> die in `VERSION` steht.

---

## 8. Wartungsfenster und der Update-Knopf

Damit sich der Rechner selbst auf Stand hält. Das WLAN-Profil muss
vorher in NetworkManager angelegt sein:

```fish
nmcli device wifi connect "<WLAN-Name>" password "<Passwort>"
```
```fish
bash wartungsfenster.sh --einschalten "<WLAN-Name>" Do 18:00 22:00
```
```fish
bash wartungsfenster.sh --autoupdate ja
```
```fish
bash wartungsfenster.sh --berichte ja
```

> **Kontrolle**
> ```fish
> bash wartungsfenster.sh --zeigen
> ```
> Fenster `an`, Autoupdate `ja`, Berichte `ja`, und eine plausible
> nächste Weckzeit.
> ```fish
> cat /sys/class/rtc/rtc0/wakealarm
> ```
> Eine Zahl, kein leerer Ausgabe. Leer heißt: der Wecker steht nicht,
> und dann kommt ein ausgeschalteter Rechner nicht von selbst wieder.
> Beim nächsten Herunterfahren stellt ihn die Unit
> `devarenu-fenster-wecker.service` von selbst.

Am Pult gibt es unter *Einrichtung* außerdem den Knopf **„Jetzt aus dem
Netz aktualisieren"**. Der geht nur am Gemeinde-PC selbst, nicht aus
dem Saal.

---

## 9. Sicherung anlegen

**Das ist der Abschnitt, den man nicht überspringt.** Ohne ihn beginnt
nach einem Plattenschaden alles wieder bei Abschnitt 1 — und das
WLAN-Passwort weiß dann niemand mehr.

Tragbare Platte anstecken, dann:

```fish
bash sichern.sh /run/media/$USER/<PLATTE>
```

Das Skript fragt nach einer **Passphrase**. Vier Wörter, die sich
jemand merkt. Sie verschlüsselt WLAN-Passwort, ntfy-Thema und das
RustDesk-Kennwort — alles andere (Modelle, Stimmen, Vorrat) liegt
unverschlüsselt daneben.

**Ohne die Passphrase sind die Geheimnisse weg und müssen neu
eingetragen werden. Alles andere lässt sich trotzdem
wiederherstellen.** Die Passphrase wird nirgends gespeichert; sie
gehört an zwei Stellen notiert, von denen nicht beide im Gemeindehaus
sind.

> **Kontrolle**
> ```fish
> bash zuruecksichern.sh /run/media/$USER/<PLATTE>/devarenu-sicherung-* --pruefen
> ```
> Muss Fassung, Commit und Rechnernamen nennen und sagen, dass die
> Prüfsummen stimmen.

Zurückspielen nach einer Neuinstallation: Abschnitte 1 bis 4 dieser
Anleitung, dann

```fish
bash zuruecksichern.sh /pfad/zur/devarenu-sicherung-...
```

---

## 10. Abnahme

```fish
bash pruefen.sh
```
```fish
.venv/bin/python selbsttest.py
```

> **Kontrolle**
> `pruefen.sh` darf keine roten Punkte mehr zeigen. Gelbe Hinweise sind
> in Ordnung, wenn man sie gelesen hat — sie stehen mit Begründung da.

**Dem Betreuer übergeben:**

- Wo die Sicherung liegt und wer die Passphrase hat.
- Dass Updates donnerstags zwischen 18 und 22 Uhr von selbst laufen
  und sich aufs Handy melden.
- `anleitung/Devarenu-Anleitung.pdf` ausdrucken und ans Pult legen.
- Diese drei Befehle, für den Fall, dass etwas ist:
  ```fish
  bash pruefen.sh
  ```
  ```fish
  systemctl status devarenu
  ```
  ```fish
  journalctl -u devarenu -n 50
  ```

---

## Wenn etwas nicht stimmt

| Erscheinung | Erster Griff |
|---|---|
| Kein Ton auf den Handys | `bash tondiagnose.sh`, dann am Pult die Tonquelle |
| Handys bekommen keine Adresse | `systemctl status dnsmasq`, dann `sudo bash netz_einrichten.sh --trocken` |
| „Kein Internet" am Handy, Seite geht nicht | Zugangspunkt verteilt noch selbst Adressen |
| Dienst läuft nicht | `journalctl -u devarenu -n 50` |
| Nach einem Update ist etwas kaputt | `bash wiederherstellen.sh --pruefen`, dann `--alles` |
| Etwas fehlt und es gibt kein Netz | `bash wiederherstellen.sh --alles` (aus dem Vorrat) |

Ausführlich — mit Begründungen, Messungen und der Geschichte jeder
Entscheidung — steht alles in [AUFSTELLEN.md](AUFSTELLEN.md). Dieses
Dokument hier ist der kurze Weg; jenes die Erklärung.

Wer diese Anleitung **üben** will, ohne einen Rechner zu plätten:
[VM-TESTUMGEBUNG.md](VM-TESTUMGEBUNG.md). Dort läuft dasselbe in einer
virtuellen Maschine — bis auf Ton, Grafikkarte und Saalnetz, und das
steht dort auch so.
