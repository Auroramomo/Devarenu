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
