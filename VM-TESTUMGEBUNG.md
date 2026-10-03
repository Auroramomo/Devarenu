# Die virtuelle Testmaschine

**Jedes Update läuft zuerst hier und dann auf dem Gemeinderechner.**

Bis 0.3.8 war der Gemeinderechner die Testmaschine. Jeder Fehler fiel
damit am Donnerstagabend auf, zwei Tage vor dem Gottesdienst — dreimal
genau so passiert:

| Fassung | Was aufgefallen ist |
|---|---|
| 0.3.1 | Die Units wurden nie geschrieben; alles lief in alter Fassung weiter. |
| 0.3.3 | `[ -f … ]` ohne `sudo` auf einem `root:root 700`-Ordner — das Update brach ab, ohne etwas zu ändern. |
| 0.3.7 | Der Pult-Schalter für das Testprotokoll war unsichtbar, der Update-Stand falsch. |

Alle drei wären auf einer VM aufgefallen. Keiner davon brauchte eine
Grafikkarte, ein Mikrofon oder einen Saal — nur einen Rechner, der so
eingerichtet ist wie der echte.

---

## Was die VM NICHT prüft

**Diesen Abschnitt zuerst lesen.** „Grün auf der VM" heißt nicht „grün
im Saal".

| Nicht geprüft | Warum | Wo es dann auffällt |
|---|---|---|
| **NVIDIA-Treiber und CUDA** | Keine Karte durchgereicht. Whisper läuft im Testmodus als `tiny` auf der CPU. | `selbsttest.py` und die Startausgabe auf dem Gemeinderechner |
| **Die Übersetzungsqualität** | Ein `tiny`-Modell auf der CPU liefert Unsinn. Das ist in Ordnung: geprüft wird der Weg. | Testprotokoll am Pult, im Gottesdienst |
| **Der Ton** | Kein UMC202HD, kein Mischpult, keine Kanalnummern. | `tondiagnose.sh`, Einmessen am Pult |
| **Die Wayland-Sitzung** | In der VM läuft eine andere Arbeitsumgebung, und RustDesk/Portal verhalten sich dort anders. | `pruefen.sh`, Abschnitt Sitzung |
| **Der BIOS-Wecker** | `rtcwake` schreibt in eine virtuelle Uhr. Ob das echte BIOS den Rechner weckt, sagt nur das echte BIOS. | `cat /sys/class/rtc/rtc0/wakealarm` nach einem echten Herunterfahren |
| **Handys im Saal** | Kein WLAN, kein Zugangspunkt, keine iOS-Anmeldeerkennung. | Die Probe aus `ERSTINSTALLATION.md`, Abschnitt 6 |
| **Die Hardware-Untergrenze** | Die VM sagt nichts darüber, ob ein schwächerer Rechner reicht. | Eine Messung auf echter Hardware |

Was sie **sehr wohl** prüft: ob das Update durchläuft, ob die Units
geschrieben und scharf gemacht werden, ob der Dienst wieder hochkommt,
ob `zustand.json` unangetastet bleibt, ob der Rückweg greift, ob
`dnsmasq` startet und eine Adresse verteilt, ob das Wartungsfenster
zündet, ob das Pult kommt und jeder Schalter dort steht, wo er stehen
soll.

Das sind genau die Dinge, an denen 0.3.1, 0.3.3 und 0.3.7 gescheitert
sind.

---

## Einmal aufsetzen

```fish
bash vm_pruefstand.sh --vorbedingungen
```

Sagt, was fehlt, und nennt den Befehl dazu. **Es installiert nichts und
lädt nichts** — das ist Absicht: ein Skript, das von selbst Gigabyte
holt und Systemdienste anfasst, läuft einmal am falschen Rechner.

Gebraucht werden `qemu-full`, `libvirt`, `virt-install`, ein lesbares
`/dev/kvm`, rund 50 GB Platz und eine **CachyOS-ISO** (von
[cachyos.org/download](https://cachyos.org/download/)).

```fish
bash vm_pruefstand.sh --anlegen --iso ~/Downloads/cachyos-....iso
```

Legt eine VM mit **zwei Netzwerkkarten** an:

- `default` — das NAT-Netz von libvirt. Darüber holt die VM Updates.
- `devarenu-saal` — ein **isoliertes** Netz ohne `<forward>` und ohne
  `<ip>`. libvirt stellt dort weder Router noch DHCP. Beides macht
  Devarenu selbst, und genau das soll geprüft werden.

Danach **in der VM**, von Hand:

1. CachyOS installieren. Benutzer `devarenu`, automatische Anmeldung.
2. [ERSTINSTALLATION.md](ERSTINSTALLATION.md) abarbeiten, Abschnitte 2
   bis 8. Abschnitt 3 (Ton) fällt aus, Abschnitt 6 (Handy) auch.
3. **Den Testmodus einschalten:**
   ```fish
   python testmodus.py --ein
   ```
   Ohne ihn lädt Whisper `large-v3-turbo` auf die CPU und braucht für
   fünf Sekunden Ton über eine Minute. Ein Prüflauf, der eine Stunde
   dauert, wird nicht gemacht.
4. **Einen Schnappschuss anlegen**, damit jeder Testlauf von derselben
   Stelle beginnt:
   ```fish
   virsh snapshot-create-as devarenu-test frisch
   ```

Ohne diesen Schnappschuss prüft der zweite Lauf einen Rechner, den der
erste verändert hat — und dann sagt „geht" wenig.

---

## Ein Update testen

```fish
bash vm_pruefstand.sh --update v0.4.0
```

Setzt die VM auf den Schnappschuss zurück, startet sie und nennt die
vier Befehle, die **in** der VM laufen:

```
bash aktualisieren.sh
bash pruefen.sh
.venv/bin/python selbsttest.py
cat VERSION
```

Danach muss stimmen:

- `VERSION` steht auf der neuen Fassung.
- `pruefen.sh` zeigt keine roten Punkte.
- `systemctl is-active devarenu` sagt `active`.
- Der Systemcheck meldet den **TESTMODUS**. Tut er das nicht, lief das
  große Modell — und der Lauf hat eine Stunde gedauert.

---

## Der Testmodus

`testmodus.py`. Zwei Bedingungen, und sie müssen **beide** erfüllt
sein:

1. Die Datei `TESTMODUS` liegt im Projektordner. Sie steht in
   `.gitignore` und kommt mit keinem Update mit.
2. Dieser Rechner hat **keine** NVIDIA-Karte (`nvidia-smi` findet
   keine).

**Die zweite Bedingung ist die eigentliche Sperre.** Die erste allein
wäre eine Datei, und Dateien wandern: jemand kopiert einen Ordner,
spielt eine Sicherung zurück, baut einen Stick aus einem
Testverzeichnis. Dann lief auf dem Gemeinderechner am Sonntag ein
`tiny`-Modell — und am Pult sähe man es nicht, die Übersetzung käme ja,
nur als Unsinn.

Der Gemeinderechner hat eine RTX 5080. Solange das so ist, kann der
Testmodus dort nicht greifen, auch wenn die Marke daliegt. Und liegt
sie dort, **sagt der Systemcheck es trotzdem** (Befund
`testmodus_marke`): sie tut nichts, aber sie ist versehentlich
hergekommen und hat dort nichts zu suchen.

Sichtbar ist der Testmodus in der Startausgabe, am Pult unter *Wartung*
und in `pruefen.sh`.

```fish
python testmodus.py
```
sagt jederzeit, ob er greift und warum.

---

## Aufräumen

```fish
bash vm_pruefstand.sh --zeigen
```
```fish
bash vm_pruefstand.sh --weg
```

Fragt nach, bevor es löscht. Das isolierte Netz bleibt stehen — es
kostet nichts, und die nächste Testmaschine braucht es wieder.
