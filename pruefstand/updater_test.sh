#!/usr/bin/env bash
# Prueft den Updater mit Attrappen statt mit acht Gigabyte.
#
#   bash pruefstand/updater_test.sh
#
# Braucht kein Wurzelrecht, kein systemd, kein Modell. systemctl,
# sudo und curl kommen aus pruefstand/attrappen/ und schreiben nur
# mit, statt etwas zu tun.
#
# Geprueft wird aktualisierung.sh mit Attrappen. Kein Wurzelrecht, kein echtes
# systemd, kein echtes Modell.
set -u
ECHT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Attrappen vor allem anderen: systemctl, sudo und curl werden
# nachgebildet, damit der Prueflauf ohne Wurzelrechte und ohne
# echten Dienst auskommt.
export PATH="$ECHT/pruefstand/attrappen:$PATH"
BASIS="$(mktemp -d)"
FEHLER=0

pruefe() { # $1 Beschreibung  $2 erwartet  $3 ist
  if [ "$2" = "$3" ]; then
    printf '   ok    %s\n' "$1"
  else
    printf '   FEHL  %s: erwartet %s, ist %s\n' "$1" "$2" "$3"
    FEHLER=$((FEHLER+1))
  fi
}

# --------------------------------------------- ein Uebungs-Repo bauen
bau_repo() { # $1 Ordner
  local o="$1"
  mkdir -p "$o"
  git -C "$o" init -q .
  git -C "$o" config user.email t@t; git -C "$o" config user.name t
  cp "$ECHT/aktualisierung.sh" "$ECHT/gesundheit.sh" "$o/"
  cp "$ECHT/systemcheck.py" "$ECHT/netzzustand.py" "$ECHT/config.py" "$o/" 2>/dev/null
  echo "0.2.12" > "$o/VERSION"
  echo "fastapi" > "$o/requirements.txt"
  echo "alt" > "$o/etwas.txt"
  git -C "$o" add -A >/dev/null; git -C "$o" commit -q -m "0.2.12"
  git -C "$o" tag v0.2.12
}

lauf() { # Umgebung setzen und aktualisierung.sh starten
  local o="$1" ref="$2" version="$3" altsha="$4" sicherung="$5"
  DEV_ORDNER="$o" DEV_BENUTZER="$(id -un)" DEV_ABLAGE="$BASIS/daten" \
  DEV_ALT_SHA="$altsha" DEV_REF="$ref" DEV_VERSION="$version" \
  DEV_HIER="0.2.12" DEV_SICHERUNG="$sicherung" \
  STUB_FASSUNG="$version" STUB_LOG="$BASIS/systemctl.log" \
    bash "$o/aktualisierung.sh" 2>&1
}

printf '\n\033[1m== 1) Sprung ueber mehrere Fassungen\033[0m\n'
R="$BASIS/r1"; bau_repo "$R"
ALT="$(git -C "$R" rev-parse HEAD)"
for v in 0.2.13 0.2.14; do
  echo "$v" > "$R/VERSION"; echo "stand $v" > "$R/etwas.txt"
  git -C "$R" add -A >/dev/null; git -C "$R" commit -q -m "$v"
  git -C "$R" tag "v$v"
done
git -C "$R" update-ref refs/stick/v0.2.14 "$(git -C "$R" rev-parse v0.2.14)"
git -C "$R" reset -q --hard "$ALT"
mkdir -p "$BASIS/daten" "$BASIS/s1"
AUS="$(lauf "$R" refs/stick/v0.2.14 0.2.14 "$ALT" "$BASIS/s1")"
pruefe "zwei Fassungen uebersprungen" "0.2.14" "$(cat "$R/VERSION")"
pruefe "Inhalt mitgekommen" "stand 0.2.14" "$(cat "$R/etwas.txt")"

printf '\n\033[1m== 2) Lokale Aenderung wird gesichert und ueberschrieben\033[0m\n'
R="$BASIS/r2"; bau_repo "$R"
ALT="$(git -C "$R" rev-parse HEAD)"
echo "0.2.13" > "$R/VERSION"; git -C "$R" add -A >/dev/null
git -C "$R" commit -q -m 0.2.13; git -C "$R" tag v0.2.13
git -C "$R" update-ref refs/stick/v0.2.13 "$(git -C "$R" rev-parse v0.2.13)"
git -C "$R" reset -q --hard "$ALT"
echo "von Hand geaendert" > "$R/etwas.txt"      # lokale Aenderung
mkdir -p "$BASIS/s2"
AUS="$(lauf "$R" refs/stick/v0.2.13 0.2.13 "$ALT" "$BASIS/s2")"
pruefe "eingespielt"  "0.2.13" "$(cat "$R/VERSION")"
pruefe "Patch gesichert" "1" "$(ls "$BASIS/daten"/lokal-*.patch 2>/dev/null | wc -l)"
pruefe "Patch nur fuer die Wurzel lesbar" "600" \
  "$(stat -c %a "$(ls "$BASIS/daten"/lokal-*.patch | head -1)")"
pruefe "Pult wird benachrichtigt" "1" \
  "$(printf '%s' "$AUS" | grep -c 'MELDUNG|Lokale Aenderungen')"

printf '\n\033[1m== 3) Gleichnamiger Tag darf nichts unterschieben\033[0m\n'
R="$BASIS/r3"; bau_repo "$R"
ALT="$(git -C "$R" rev-parse HEAD)"
echo "0.2.13" > "$R/VERSION"; echo "ECHT" > "$R/etwas.txt"
git -C "$R" add -A >/dev/null; git -C "$R" commit -q -m echt
ECHT_SHA="$(git -C "$R" rev-parse HEAD)"
git -C "$R" update-ref refs/stick/v0.2.13 "$ECHT_SHA"
echo "GEFAELSCHT" > "$R/etwas.txt"; git -C "$R" add -A >/dev/null
git -C "$R" commit -q -m gefaelscht
git -C "$R" tag -f v0.2.13 HEAD >/dev/null 2>&1
git -C "$R" reset -q --hard "$ALT"
mkdir -p "$BASIS/s3"
AUS="$(lauf "$R" refs/stick/v0.2.13 0.2.13 "$ALT" "$BASIS/s3")"
pruefe "der geprueufte Stand gewinnt" "ECHT" "$(cat "$R/etwas.txt")"

printf '\n\033[1m== 4) Gescheiterter Neustart meldet sich\033[0m\n'
R="$BASIS/r4"; bau_repo "$R"
ALT="$(git -C "$R" rev-parse HEAD)"
echo "0.2.13" > "$R/VERSION"; git -C "$R" add -A >/dev/null
git -C "$R" commit -q -m 0.2.13; git -C "$R" tag v0.2.13
git -C "$R" update-ref refs/stick/v0.2.13 "$(git -C "$R" rev-parse v0.2.13)"
git -C "$R" reset -q --hard "$ALT"
mkdir -p "$BASIS/s4"
STUB_RESTART_OK=nein AUS="$(STUB_RESTART_OK=nein lauf "$R" refs/stick/v0.2.13 0.2.13 "$ALT" "$BASIS/s4")"
RC=$?
pruefe "Rueckgabe ungleich 0" "1" "$([ "$RC" != 0 ] && echo 1 || echo 0)"
pruefe "Meldung fuers Pult" "1" \
  "$(printf '%s' "$AUS" | grep -c 'MELDUNG|Der Dienst liess sich')"

printf '\n\033[1m== 5) Alter Stick ohne teile.json\033[0m\n'
pruefe "keine teile.json noetig" "1" \
  "$(printf '%s' "$AUS" | grep -c 'keine grossen Teile' || echo 1)"

printf '\n\033[1m== 6) Altfall: .venv ist ein echtes Verzeichnis\033[0m\n'
# So steht der Gemeinderechner da: .venv ist ein Ordner, keine
# Verknuepfung. Beim ersten Tausch wird er zu .venv-a umbenannt und
# .venv zur Verknuepfung darauf.
#
# Umbenennen klingt riskant -- in einem venv stehen die Pfade in den
# Skripten. Es geht trotzdem, und zwar GENAU DESHALB, weil die
# Verknuepfung den alten Namen wiederherstellt: der eingebrannte Pfad
# .../.venv/bin/python loest danach weiter auf. Belegt unten mit
# sys.prefix.
R="$BASIS/r6"; bau_repo "$R"
ALT="$(git -C "$R" rev-parse HEAD)"
python3 -m venv "$R/.venv" >/dev/null 2>&1
"$R/.venv/bin/python" -c "pass" || { echo "   FEHL venv laeuft nicht"; FEHLER=$((FEHLER+1)); }
VOR="$("$R/.venv/bin/python" -c 'import sys; print(sys.prefix)')"
# Ein Paket hinein, damit man den Unterschied sieht.
echo "kennzeichen-alt" > "$R/.venv/kennzeichen"
# requirements.txt aendert sich -> venv wird getauscht
echo "0.2.13" > "$R/VERSION"
# Geaendert, aber ohne Paket: pip --no-index kommt damit auch ohne
# wheels/ durch. Sonst scheitert es, und der Test bestaende, weil der
# Tausch gar nicht erst stattfand.
printf '# nur ein Kommentar, aber eine Aenderung\n' > "$R/requirements.txt"
git -C "$R" add -A >/dev/null; git -C "$R" commit -q -m 0.2.13
git -C "$R" tag v0.2.13
git -C "$R" update-ref refs/stick/v0.2.13 "$(git -C "$R" rev-parse v0.2.13)"
git -C "$R" reset -q --hard "$ALT"
mkdir -p "$BASIS/daten/wheels" "$BASIS/s6"
AUS="$(lauf "$R" refs/stick/v0.2.13 0.2.13 "$ALT" "$BASIS/s6")"

# Zuerst: ist der Tausch ueberhaupt gelaufen? Ohne diese Zeile
# bestuende der Test auch dann, wenn aktualisierung.sh vorher
# abgebrochen waere.
pruefe "der Tausch ist gelaufen (venv-vorher geschrieben)" "ja" \
  "$([ -s "$BASIS/s6/venv-vorher" ] && echo ja || echo nein)"
pruefe "jetzt ist .venv-b aktiv" ".venv-b" "$(readlink "$R/.venv")"
pruefe ".venv ist jetzt eine Verknuepfung" "ja" \
  "$([ -L "$R/.venv" ] && echo ja || echo nein)"
pruefe "das alte venv heisst .venv-a" "ja" \
  "$([ -f "$R/.venv-a/kennzeichen" ] && echo ja || echo nein)"
pruefe "der eingebrannte Pfad gilt weiter" "$VOR" \
  "$("$R/.venv/bin/python" -c 'import sys; print(sys.prefix)' 2>/dev/null)"
pruefe "das alte venv ist noch da (Rueckweg)" "ja" \
  "$([ -d "$R/.venv-a" ] && echo ja || echo nein)"

printf '\n\033[1m== 7) Rueckfall auf das alte echte Verzeichnis\033[0m\n'
# Nachgebaut, was zurueck() im Kern tut: die Verknuepfung zurueck.
ALTES="$(cat "$BASIS/s6/venv-vorher" 2>/dev/null)"
pruefe "gemerkt wurde .venv-a" ".venv-a" "$ALTES"
ln -sfn "$ALTES" "$R/.venv"
pruefe "Verknuepfung zeigt wieder auf .venv-a" ".venv-a" "$(readlink "$R/.venv")"
pruefe "das Kennzeichen von vorher ist da" "kennzeichen-alt" \
  "$(cat "$R/.venv/kennzeichen" 2>/dev/null)"
pruefe "und es laeuft" "$VOR" \
  "$("$R/.venv/bin/python" -c 'import sys; print(sys.prefix)' 2>/dev/null)"

printf '\n\033[1m== 8) Der echte Sprung 0.2.13 -> 0.2.14\033[0m\n'
# Genau der Sprung, der vor Ort gemacht wird: kein Modellwechsel, keine
# neuen Pakete, nur Code. Mit dem NEUEN Kern, also ueber
# aktualisierung.sh -- so, wie es ab 0.2.13 laeuft.
R="$BASIS/r8"; bau_repo "$R"
echo "0.2.13" > "$R/VERSION"
git -C "$R" add -A >/dev/null; git -C "$R" commit -q -m 0.2.13
git -C "$R" tag v0.2.13
ALT="$(git -C "$R" rev-parse HEAD)"

# 0.2.14: eine Zeile mehr, sonst nichts. requirements.txt bleibt.
echo "0.2.14" > "$R/VERSION"
echo "Fehler melden am Pult" >> "$R/etwas.txt"
git -C "$R" add -A >/dev/null; git -C "$R" commit -q -m 0.2.14
git -C "$R" tag v0.2.14
git -C "$R" update-ref refs/stick/v0.2.14 "$(git -C "$R" rev-parse v0.2.14)"
git -C "$R" reset -q --hard "$ALT"
mkdir -p "$BASIS/s8"
AUS="$(lauf "$R" refs/stick/v0.2.14 0.2.14 "$ALT" "$BASIS/s8")"

pruefe "0.2.14 ist eingespielt" "0.2.14" "$(cat "$R/VERSION")"
pruefe "die neue Zeile ist da" "1" \
  "$(grep -c 'Fehler melden am Pult' "$R/etwas.txt")"
pruefe "kein venv getauscht (requirements unveraendert)" "nein" \
  "$([ -f "$BASIS/s8/venv-vorher" ] && echo ja || echo nein)"
pruefe "keine grossen Teile noetig" "1" \
  "$(printf '%s' "$AUS" | grep -c 'keine grossen Teile')"
pruefe "der Gesundheitscheck lief" "1" \
  "$(printf '%s' "$AUS" | grep -c 'Gesundheitscheck')"

printf '\n\033[1m== 9) Der echte Weg des Helfers: 0.2.11 -> 0.2.15 mit dem ALTEN Kern\033[0m\n'
# Genau das, was vor Ort passiert. Der Gemeinderechner steht auf 0.2.11,
# und eingespielt wird mit SEINEM Updater -- der neue Kern kommt erst
# mit und greift beim naechsten Mal.
#
# Der alte Kern ueberschreibt sich dabei selbst (git merge auf eine
# Fassung, in der stick_update.sh anders aussieht). Dass das gutgeht,
# haengt daran, dass git eine neue Datei anlegt statt die alte zu
# ueberschreiben -- die laufende Shell liest ueber ihren offenen
# Deskriptor weiter. Dieser Fall prueft es am echten Skript.
R="$BASIS/r9"
mkdir -p "$R"
git -C "$R" init -q .
git -C "$R" config user.email t@t; git -C "$R" config user.name t
# Der Stand von 0.2.11, mit dem Kern von damals.
git -C "$ECHT" show v0.2.11:stick_update.sh > "$R/stick_update.sh"
chmod 755 "$R/stick_update.sh"
echo "0.2.11" > "$R/VERSION"
echo "fastapi" > "$R/requirements.txt"
echo "alt" > "$R/etwas.txt"
# Der Kern liest Antworten des Dienstes mit der venv-Python. Fehlt sie,
# bleibt jedes Feld leer, der Gesundheitscheck laeuft 60 mal ins Leere
# und der Fall scheitert nach zwei Minuten aus dem falschen Grund.
mkdir -p "$R/.venv/bin"
ln -sf "$(command -v python3)" "$R/.venv/bin/python"
git -C "$R" add -A >/dev/null; git -C "$R" commit -q -m 0.2.11
ALT="$(git -C "$R" rev-parse HEAD)"

# 0.2.15: neuer Kern, neue Logik, neue Fassung.
cp "$ECHT/stick_update.sh" "$ECHT/aktualisierung.sh" "$ECHT/gesundheit.sh" "$R/"
cp "$ECHT/stick.udev.vorlage" "$R/"
echo "0.2.15" > "$R/VERSION"
echo "neu" > "$R/etwas.txt"
git -C "$R" add -A >/dev/null; git -C "$R" commit -q -m 0.2.15
git -C "$R" tag v0.2.15
git -C "$R" update-ref refs/stick/v0.2.15 "$(git -C "$R" rev-parse v0.2.15)"
git -C "$R" reset -q --hard "$ALT"

# Was der --lesen-Lauf hinterlassen haette: vorgemerkt und am Pult
# gedrueckt. Ohne "jetzt" zaehlte der alte Kern erst zwanzig Minuten.
mkdir -p "$R/update"
echo "0.2.15" > "$R/update/bereit"
: > "$R/update/jetzt"

AUS9="$(STUB_FASSUNG=0.2.15 STUB_LOG="$BASIS/s9.log" \
        bash "$R/stick_update.sh" --einspielen 2>&1)" || true

pruefe "0.2.15 ist eingespielt" "0.2.15" "$(cat "$R/VERSION")"
pruefe "der Inhalt kam mit" "neu" "$(cat "$R/etwas.txt")"
pruefe "der alte Kern lief zu Ende (Dienst neu gestartet)" "1" \
  "$(grep -c 'systemctl restart devarenu' "$BASIS/s9.log" 2>/dev/null || echo 0)"
pruefe "der neue Kern liegt jetzt im Ordner" "ja" \
  "$(grep -q 'aktualisierung.sh' "$R/stick_update.sh" && echo ja || echo nein)"
pruefe "die Vormerkung ist weg" "nein" \
  "$([ -f "$R/update/bereit" ] && echo ja || echo nein)"

printf '\n\033[1m== 10) Der neue Kern, aufgerufen aus den ALTEN Units von 0.2.11\033[0m\n'
# Nach Fall 9 liegt der neue Kern im Ordner, die Units stammen aber noch
# von 0.2.11. Sie rufen das Skript OHNE /bin/bash auf. Vertraegt der
# neue Kern dieselben Argumente?
ALTE_EIN="$(git -C "$ECHT" show v0.2.11:devarenu-update.service.vorlage \
            | sed -n 's/^ExecStart=//p')"
ALTE_LESEN="$(git -C "$ECHT" show v0.2.11:devarenu-stick@.service.vorlage \
              | sed -n 's/^ExecStart=//p')"
pruefe "die alte Unit ruft ohne /bin/bash auf" "1" \
  "$(printf '%s' "$ALTE_EIN" | grep -c '^@ORDNER@/stick_update.sh')"

# Wortwoertlich das, was systemd daraus macht: Platzhalter ersetzt,
# Instanzname sdb1 wie bei %k.
set -- $(printf '%s' "$ALTE_EIN" | sed "s|@ORDNER@|$R|")
AUS10="$("$@" 2>&1)"; RC10=$?
pruefe "--einspielen aus der alten Unit laeuft durch" "0" "$RC10"
pruefe "und meldet nichts, weil nichts vorgemerkt ist" "" "$AUS10"

set -- $(printf '%s' "$ALTE_LESEN" | sed "s|@ORDNER@|$R|; s|%i|sdb1|")
AUS10B="$("$@" 2>&1)" || true
pruefe "--lesen /dev/sdb1 wird verstanden (kein Aufruffehler)" "0" \
  "$(printf '%s' "$AUS10B" | grep -c 'Aufruf:')"
pruefe "und scheitert sauber am fehlenden Geraet" "ja" \
  "$(printf '%s' "$AUS10B" | grep -qi 'sdb1' && echo ja || echo nein)"

# Schreibt er Units und udev-Regel neu? Das tut die Logik, also ueber
# den gewohnten Weg -- aber mit umgebogenen Zielen, damit nichts unter
# /etc angefasst wird.
R="$BASIS/r10"; bau_repo "$R"
cp "$ECHT"/devarenu*.vorlage "$ECHT/stick.udev.vorlage" "$R/"
git -C "$R" add -A >/dev/null; git -C "$R" commit -q -m vorlagen
ALT="$(git -C "$R" rev-parse HEAD)"
echo "0.2.15" > "$R/VERSION"
git -C "$R" add -A >/dev/null; git -C "$R" commit -q -m 0.2.15
git -C "$R" tag v0.2.15
git -C "$R" update-ref refs/stick/v0.2.15 "$(git -C "$R" rev-parse v0.2.15)"
git -C "$R" reset -q --hard "$ALT"

UO="$BASIS/units10"; mkdir -p "$UO" "$BASIS/s10"
# Die installierten Units, wie sie auf dem Rechner von 0.2.11 liegen.
for u in devarenu.service devarenu-stick@.service devarenu-update.service \
         devarenu-update.timer; do
  git -C "$ECHT" show "v0.2.11:$u.vorlage" \
    | sed "s|@ORDNER@|$R|g; s|@BENUTZER@|$(id -un)|g; s|@PORT@|8000|g" > "$UO/$u"
done
UR="$BASIS/99-devarenu-stick.rules"
echo '# veraltete Regel von Hand' > "$UR"

AUS="$(DEVARENU_UNIT_ORDNER="$UO" DEVARENU_UDEV_REGEL="$UR" \
       lauf "$R" refs/stick/v0.2.15 0.2.15 "$ALT" "$BASIS/s10")"

pruefe "die drei veralteten Units wurden neu geschrieben" "3" \
  "$(printf '%s' "$AUS" | grep -cE '(service|timer) neu geschrieben' || true)"
pruefe "devarenu-update.service laeuft jetzt ueber /bin/bash" "1" \
  "$(grep -c '^ExecStart=/bin/bash' "$UO/devarenu-update.service")"
pruefe "der Timer blieb unangetastet (er hat sich nie geaendert)" "0" \
  "$(printf '%s' "$AUS" | grep -c 'devarenu-update.timer neu geschrieben' || true)"
pruefe "systemd wurde neu geladen" "1" \
  "$(grep -c 'daemon-reload' "$BASIS/systemctl.log" || true)"
pruefe "die udev-Regel wurde nachgezogen" "0" \
  "$(cmp -s "$ECHT/stick.udev.vorlage" "$UR" && echo 0 || echo 1)"
pruefe "und udev wurde angestossen" "1" \
  "$(grep -c 'udevadm control' "$BASIS/systemctl.log" || true)"

printf '\n\033[1m== 11) Was auf dem Stick liegt: eine Ebene tief, zweimal, zu tief\033[0m\n'
# Der Weg des Helfers geht ueber ein ZIP. Windows entpackt es in einen
# Ordner, und der wandert als Ganzes auf den Stick -- die Dateien liegen
# dann eine Ebene tiefer als sonst. Dass der Rechner sie dort findet,
# entscheidet ueber den ganzen Sonntag.
R="$BASIS/r11"; bau_repo "$R"
mkdir -p "$R/update"
# Der Kern leitet seinen Projektordner aus dem EIGENEN Pfad ab. Wird er
# aus dem echten Repo heraus aufgerufen, legt er seine Statusdatei dort
# ab statt im Uebungsordner -- der Prueflauf schriebe in die
# Arbeitskopie. Also die Kopie im Uebungsordner starten.
cp "$ECHT/stick_update.sh" "$R/"

stick_lesen() { # $1 Stickordner -> Ausgabe
  DEVARENU_STICK_ORDNER="$1" STUB_LOG="$BASIS/s11.log" \
    bash "$R/stick_update.sh" --lesen /dev/attrappe 2>&1 || true
}
lage() { sed -n 's/.*"lage"[: ]*"\([a-z_]*\)".*/\1/p' "$R/update/stand.json" 2>/dev/null; }

# a) eine Ebene tief -- der Normalfall nach dem ZIP
S="$BASIS/stick_a"; mkdir -p "$S/Devarenu-Stick-v0.2.15"
echo "version=v0.2.15" > "$S/Devarenu-Stick-v0.2.15/upd-dev.txt"
A="$(cd "$R" && stick_lesen "$S")"
pruefe "eine Ebene tief wird gefunden" "ja" \
  "$(printf '%s' "$A" | grep -q 'upd-dev.txt nennt Fassung 0.2.15' && echo ja || echo nein)"
pruefe "und es wird gesagt, dass sie tiefer liegen" "ja" \
  "$(printf '%s' "$A" | grep -q 'statt oben' && echo ja || echo nein)"
pruefe "danach faellt das fehlende Bundle auf" "unvollstaendig" "$(cd "$R" && lage)"

# b) zwei Ordner -- ein alter vom letzten Mal ist liegengeblieben
S="$BASIS/stick_b"; mkdir -p "$S/alt-0.2.13" "$S/Devarenu-Stick-v0.2.15"
echo "version=v0.2.13" > "$S/alt-0.2.13/upd-dev.txt"
echo "version=v0.2.15" > "$S/Devarenu-Stick-v0.2.15/upd-dev.txt"
B="$(cd "$R" && stick_lesen "$S")"
pruefe "zwei Update-Ordner: es wird nicht geraten" "ja" \
  "$(printf '%s' "$B" | grep -q '2 Dateien upd-dev.txt' && echo ja || echo nein)"
pruefe "beide werden benannt" "2" \
  "$(printf '%s' "$B" | grep -c 'upd-dev.txt$' || true)"
pruefe "das Pult bekommt die Lage" "mehrdeutig" "$(cd "$R" && lage)"
pruefe "und keine Fassung wurde uebernommen" "0.2.12" "$(cat "$R/VERSION")"

# c) zwei Ebenen tief -- Windows-Ordner samt Unterordner kopiert
S="$BASIS/stick_c"; mkdir -p "$S/Devarenu-Stick-v0.2.15/Devarenu-Stick"
echo "version=v0.2.15" > "$S/Devarenu-Stick-v0.2.15/Devarenu-Stick/upd-dev.txt"
C="$(cd "$R" && stick_lesen "$S")"
pruefe "zwei Ebenen tief wird NICHT gefunden" "ja" \
  "$(printf '%s' "$C" | grep -q 'kein upd-dev.txt' && echo ja || echo nein)"

printf '\n\033[1m== 12) Der ganze Weg des Helfers: ZIP -> Windows -> Stick -> gelesen\033[0m\n'
# Von der gebauten ZIP-Datei bis zur Vormerkung am Pult, mit echter
# Signaturpruefung. Der Weg, den vor Ort niemand ueben kann.
R="$BASIS/r12"; bau_repo "$R"
mkdir -p "$R/.venv/bin"
ln -sf "$(command -v python3)" "$R/.venv/bin/python"
cp "$ECHT/stick_update.sh" "$ECHT/stick_bauen.sh" "$ECHT/bootstrap.sh" "$R/"

# Ein eigener Freigabeschluessel, nur fuer diesen Lauf.
SCHL="$BASIS/pruefschluessel"
ssh-keygen -q -t ed25519 -N "" -C pruefstand -f "$SCHL"
echo "pruef@pruefstand $(cat "$SCHL.pub")" > "$R/schluessel.erlaubt"
git -C "$R" config user.email pruef@pruefstand
git -C "$R" config user.name Pruefstand
git -C "$R" config gpg.format ssh
git -C "$R" config user.signingkey "$SCHL.pub"
git -C "$R" add -A >/dev/null; git -C "$R" commit -q -m "Stand mit Schluessel"
VOR="$(git -C "$R" rev-parse HEAD)"

echo "0.2.15" > "$R/VERSION"; echo "neu" > "$R/etwas.txt"
git -C "$R" add -A >/dev/null; git -C "$R" commit -q -m 0.2.15
git -C "$R" tag -s v0.2.15 -m "Devarenu 0.2.15"

# Bauen wie zuhause: aus dem Tag, als ZIP, ohne echten Stick.
ZIP="$BASIS/Devarenu-Stick-v0.2.15.zip"
BAU="$(cd "$R" && bash stick_bauen.sh --zip "$ZIP" --ohne-wheels 2>&1)" || true
pruefe "das ZIP wurde gebaut" "ja" "$([ -s "$ZIP" ] && echo ja || echo nein)"
pruefe "die Dateien liegen im ZIP ganz oben" "ja" \
  "$(python3 -m zipfile -l "$ZIP" | grep -q '^upd-dev.txt' && echo ja || echo nein)"

# Windows: entpackt in einen Ordner, der wie das ZIP heisst.
STK="$BASIS/stick12"; mkdir -p "$STK/Devarenu-Stick-v0.2.15"
python3 -m zipfile -e "$ZIP" "$STK/Devarenu-Stick-v0.2.15"

# Der Rechner steht wieder auf 0.2.12 und liest den Stick.
git -C "$R" reset -q --hard "$VOR"
LES="$(cd "$R" && DEVARENU_STICK_ORDNER="$STK" DEVARENU_DATEN="$BASIS/daten12" \
       STUB_FASSUNG=0.2.12 STUB_LOG="$BASIS/s12.log" \
       bash "$R/stick_update.sh" --lesen /dev/attrappe 2>&1)" || true

pruefe "der Ordner vom Stick wird gefunden" "ja" \
  "$(printf '%s' "$LES" | grep -q 'nennt Fassung 0.2.15' && echo ja || echo nein)"
# Nicht auf das Wort "Signatur" pruefen -- das steht auch in der
# Absage. Auf das Gegenteil.
pruefe "die Signatur wird angenommen" "nein" \
  "$(printf '%s' "$LES" | grep -q 'ungueltig' && echo ja || echo nein)"
pruefe "das Update liegt bereit" "bereit" \
  "$(sed -n 's/.*"lage"[: ]*"\([a-z_]*\)".*/\1/p' "$R/update/stand.json")"
pruefe "und das Pult nennt die Fassung" "ja" \
  "$(grep -q '0.2.15' "$R/update/stand.json" && echo ja || echo nein)"
pruefe "die Nutzlast liegt ausserhalb des Projektordners" "ja" \
  "$([ -d "$BASIS/daten12" ] && echo ja || echo nein)"
pruefe "im Projektordner selbst kein Bundle" "nein" \
  "$([ -f "$R/update/devarenu.bundle" ] && echo ja || echo nein)"

printf '\n\033[1m== 13) Ein Stick, der seine eigenen Schluessel mitbringt\033[0m\n'
# Der Angriff, der am naechstliegenden ist: ein Stick traegt ohnehin eine
# schluessel.erlaubt -- bootstrap.sh braucht sie. Wuerde der Kern sie
# lesen, koennte jeder, der einen Stick bespielen kann, jede beliebige
# Fassung einspielen. Er wuerde seine eigene Erlaubnis mitbringen.
#
# Der Kern prueft NUR gegen die installierte Liste im Projektordner.
# Dieser Fall baut den Angriff nach, so gut es geht: dieselbe
# Absenderadresse, ein anderer Schluessel, und eine passende Erlaubnis
# auf dem Stick.
R="$BASIS/r13"; bau_repo "$R"
mkdir -p "$R/.venv/bin"
ln -sf "$(command -v python3)" "$R/.venv/bin/python"
cp "$ECHT/stick_update.sh" "$R/"

ECHTER="$BASIS/schluessel_echt"
FREMD="$BASIS/schluessel_fremd"
ssh-keygen -q -t ed25519 -N "" -C echt   -f "$ECHTER"
ssh-keygen -q -t ed25519 -N "" -C fremd  -f "$FREMD"

# Installiert ist NUR der echte Schluessel.
echo "pruef@pruefstand $(cat "$ECHTER.pub")" > "$R/schluessel.erlaubt"
git -C "$R" config user.email pruef@pruefstand
git -C "$R" config user.name Pruefstand
git -C "$R" add -A >/dev/null; git -C "$R" commit -q -m "Stand mit echtem Schluessel"
VOR="$(git -C "$R" rev-parse HEAD)"
LISTE_VORHER="$(md5sum < "$R/schluessel.erlaubt")"

# Der Angreifer baut auf demselben Stand auf -- sonst scheiterte es schon
# am Vorspulen und der Fall bewiese nichts ueber die Signatur.
A="$BASIS/angriff13"
git clone -q "$R" "$A"
git -C "$A" config user.email pruef@pruefstand      # dieselbe Adresse
git -C "$A" config user.name Pruefstand
git -C "$A" config gpg.format ssh
git -C "$A" config user.signingkey "$FREMD.pub"     # anderer Schluessel
echo "0.2.15" > "$A/VERSION"
echo "hier stand mal etwas anderes" > "$A/etwas.txt"
git -C "$A" add -A >/dev/null; git -C "$A" commit -q -m 0.2.15
git -C "$A" tag -s v0.2.15 -m "Devarenu 0.2.15"

STK="$BASIS/stick13"; mkdir -p "$STK"
echo "version=v0.2.15" > "$STK/upd-dev.txt"
git -C "$A" bundle create "$STK/devarenu.bundle" --all >/dev/null 2>&1
# Und die Erlaubnis gleich mit: genau dieser fremde Schluessel.
echo "pruef@pruefstand $(cat "$FREMD.pub")" > "$STK/schluessel.erlaubt"

LES="$(cd "$R" && DEVARENU_STICK_ORDNER="$STK" DEVARENU_DATEN="$BASIS/daten13" \
       STUB_FASSUNG=0.2.12 STUB_LOG="$BASIS/s13.log" \
       bash "$R/stick_update.sh" --lesen /dev/attrappe 2>&1)" || true

pruefe "die Signatur wird als ungueltig erkannt" "ja" \
  "$(printf '%s' "$LES" | grep -q 'Signatur von v0.2.15 ist ungueltig' && echo ja || echo nein)"
pruefe "das Pult sagt: Signatur" "signatur" \
  "$(sed -n 's/.*"lage"[: ]*"\([a-z_]*\)".*/\1/p' "$R/update/stand.json")"
pruefe "nichts liegt bereit" "nein" \
  "$([ -f "$R/update/bereit" ] && echo ja || echo nein)"
pruefe "die Fassung blieb unangetastet" "0.2.12" "$(cat "$R/VERSION")"
pruefe "der Stand blieb unangetastet" "$VOR" "$(git -C "$R" rev-parse HEAD)"
pruefe "die Marke des Sticks wurde wieder entfernt" "" \
  "$(git -C "$R" rev-parse -q --verify refs/stick/v0.2.15 2>/dev/null || true)"
# Der Kern darf die Liste des Sticks weder lesen noch uebernehmen.
pruefe "die installierte Schluesselliste ist unveraendert" "$LISTE_VORHER" \
  "$(md5sum < "$R/schluessel.erlaubt")"
# Das Schluesselmaterial selbst steckt zwangslaeufig im Bundle -- eine
# SSH-Signatur fuehrt ihren Schluessel mit. Entscheidend ist daher
# nicht, ob er irgendwo vorkommt, sondern ob er je als ERLAUBNIS gilt.
FREMD_MATERIAL="$(awk '{print $2}' "$FREMD.pub")"
pruefe "der fremde Schluessel steht in keiner Erlaubnisliste" "nein" \
  "$(grep -q "$FREMD_MATERIAL" "$R/schluessel.erlaubt" && echo ja || echo nein)"
pruefe "und in der Ablage liegt gar keine Liste mehr" "nein" \
  "$([ -f "$BASIS/daten13/schluessel.erlaubt" ] && echo ja || echo nein)"

# Gegenprobe: derselbe Aufbau, aber mit dem ECHTEN Schluessel signiert.
# Ohne sie bewiese der Fall nur, dass irgendetwas scheitert.
git -C "$A" tag -d v0.2.15 >/dev/null
git -C "$A" config user.signingkey "$ECHTER.pub"
git -C "$A" tag -s v0.2.15 -m "Devarenu 0.2.15"
rm -f "$STK/devarenu.bundle"
git -C "$A" bundle create "$STK/devarenu.bundle" --all >/dev/null 2>&1
LES2="$(cd "$R" && DEVARENU_STICK_ORDNER="$STK" DEVARENU_DATEN="$BASIS/daten13b" \
        STUB_FASSUNG=0.2.12 STUB_LOG="$BASIS/s13.log" \
        bash "$R/stick_update.sh" --lesen /dev/attrappe 2>&1)" || true
pruefe "mit dem echten Schluessel geht derselbe Stick durch" "bereit" \
  "$(sed -n 's/.*"lage"[: ]*"\([a-z_]*\)".*/\1/p' "$R/update/stand.json")"

printf '\n'
if [ "$FEHLER" = 0 ]; then
  printf '\033[32mAlle Faelle wie erwartet.\033[0m\n'
else
  printf '\033[31m%d Fehler.\033[0m\n' "$FEHLER"
fi
rm -rf "$BASIS"
exit "$FEHLER"
