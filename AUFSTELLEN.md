# Aufstellen auf dem Gemeinderechner

Was sich nur dort prüfen lässt. Entwickelt und getestet wurde auf
CachyOS mit angemeldeter Sitzung; der Zielrechner ist Ubuntu Server mit
nachinstalliertem KDE, X11, headless im Betrieb, ohne angemeldeten
Benutzer.

Abhaken, was durchgelaufen ist.

## Einrichten

- [ ] `git clone` und `bash INSTALLIEREN.sh` einmal komplett durchlaufen
      lassen. Der apt-Zweig in `einrichten.sh` ist hier nie gelaufen:
      `python3-venv python3-pip ffmpeg libportaudio2 git`. Stimmen die
      Namen auf dieser Ubuntu-Fassung, wird alles gefunden?
- [ ] Python-Version prüfen. Hier lief 3.14, Ubuntu 24.04 bringt 3.12.
      Laufen faster-whisper, piper und sounddevice damit?
- [ ] NVIDIA-Treiber. `nvidia-smi` muss die Karte zeigen. Fehlt er,
      meldet `INSTALLIEREN.sh` das jetzt auch auf Ubuntu.
- [ ] `ollama.service` — heißt sie dort genauso, ist sie `enabled`?

## Selbsttest

- [ ] `.venv/bin/python selbsttest.py` — 0 Fehler.
- [ ] Die Zeile "Whisper rechnet auf cuda (float16)" muss dastehen.
      Steht dort `cpu`, ist etwas mit den CUDA-Bibliotheken; der Test
      meldet das jetzt rot, wenn eine Karte vorhanden ist.

## Dienst

- [ ] `./dienst.sh` — läuft durch, meldet "rechnet auf der Grafikkarte".
- [ ] **Neustart des Rechners.** Kommt der Dienst ohne Anmeldung von
      allein hoch? `systemctl status devarenu`, `journalctl -u devarenu -b`
- [ ] Nach dem Kaltstart: `curl -s localhost:8000/api/zustand` — das Feld
      `rechenwerk` muss `cuda (float16)` sein, nicht `cpu`. Das ist der
      Punkt, an dem sich zeigt, ob das Vorladen der CUDA-Bibliotheken
      ohne Sitzung greift.
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
- [ ] Rechner neu starten. Steht danach dasselbe Gerät da? In
      `zustand.json` stehen Nummer **und** Name; gesucht wird zuerst nach
      Namen. Ohne Sitzung zählt ALSA weniger Geräte auf als mit einer,
      hier waren es 13 statt 16.
- [ ] USB-Mikro einmal umstecken und neu starten: wird es über den Namen
      wiedergefunden?

## Im Gottesdienst

- [ ] Einmessen mit dem echten Prediger am echten Mikrofon.
- [ ] Übersetzung **nicht** über Lautsprecher im selben Raum. Kopfhörer
      am Handy. Sonst hört das Mikrofon die eigene Ausgabe und übersetzt
      sie erneut.
- [ ] WLAN-Name und Passwort am Pult eintragen, QR-Seite am Beamer
      prüfen.
- [ ] Ein Handy durchspielen: QR scannen, Sprache wählen, hören.

## Aktualisieren

- [ ] `./aktualisieren.sh` einmal ausführen. `zustand.json` muss danach
      unverändert sein — das Skript prüft und meldet es selbst.
