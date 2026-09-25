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

printf '\n'
if [ "$FEHLER" = 0 ]; then
  printf '\033[32mAlle Faelle wie erwartet.\033[0m\n'
else
  printf '\033[31m%d Fehler.\033[0m\n' "$FEHLER"
fi
rm -rf "$BASIS"
exit "$FEHLER"
