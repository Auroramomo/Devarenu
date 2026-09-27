#!/usr/bin/env bash
# Devarenu auf den neuesten Stand bringen.
#
#     bash aktualisieren.sh
#
# Holt das naechste signierte Tag, spult darauf vor und uebergibt an
# dieselbe Update-Logik, die auch ein Stick benutzt.
#
# DIE REGELN SIND DIE DES STICKS
#
# Bis 0.3.1 stand hier "git pull --ff-only": es galt, worauf
# origin/main gerade zeigte, ohne Signatur, ohne Tag, ohne Pruefung.
# Wer den Server oder die Leitung beherrschte, bestimmte damit, was
# auf dem Gemeinderechner lief. Ueber den Stick war genau das seit
# 0.2.12 unmoeglich -- ueber das Netz blieb es offen.
#
# Jetzt gilt beides gleich:
#
#   * Es wird nur auf ein TAG vorgespult, nie auf main.
#   * Das Tag muss mit einem Schluessel aus schluessel.erlaubt
#     signiert sein -- der Liste, die HIER liegt, nie einer geholten.
#   * Vorgespult wird ueber die geprueufte Commit-SHA, nie ueber den
#     Tagnamen: ein gleichnamiges lokales Tag wuerde sonst etwas
#     Ungeprueftes unterschieben.
#   * Die Fassung muss neuer sein als die hiesige.
#
# UND DIE UNITS KOMMEN MIT
#
# Der alte Weg startete den Dienst neu und war fertig. Die Units
# schrieb er nie -- das tut nur dienst.sh bei der Ersteinrichtung.
# Nach dem Einspielen von 0.3.1 am 27.09. liefen deshalb alle Units in
# alter Fassung, bis jemand von Hand dienst.sh aufrief. Jetzt uebergibt
# dieses Skript an aktualisierung.sh, die versionierte Haelfte des
# Updaters, und die schreibt Units, grosse Teile und Pakete -- genau
# wie beim Stick. Eine Logik, zwei Wege.
#
# Was hier NICHT passiert: nichts wird ueberschrieben, was jemand vor Ort
# geaendert hat. Gibt es lokale Aenderungen oder waere die
# Zusammenfuehrung mehr als ein Vorspulen, bricht das Skript ab und sagt
# es. Ein Gemeinderechner ist kein Ort fuer automatische Konfliktloesung.
#
# zustand.json wird nicht angefasst. Sie steht in .gitignore, und zur
# Sicherheit wird vorher und nachher verglichen.

set -u
ORDNER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ORDNER"

NAME=devarenu
blau() { printf '\n\033[1;34m== %s\033[0m\n' "$1"; }
gut()  { printf '   \033[32mok\033[0m   %s\n' "$1"; }
warn() { printf '   \033[33m!\033[0m    %s\n' "$1"; }
fehl() { printf '   \033[31mFEHLT\033[0m %s\n' "$1"; }

# Wem der Ordner gehoert -- unter diesem Benutzer laeuft der Dienst.
# Nicht $USER: dieses Skript wird auch mit sudo aufgerufen.
BENUTZER="$(stat -c %U "$ORDNER" 2>/dev/null || id -un)"

# Fassungsvergleich wie in stick_update.sh: sort -V und nicht die
# Zeichenfolge. Lexikalisch kaeme 0.2.9 nach 0.2.13, und ein Update
# liefe rueckwaerts.
ist_neuer() {
  [ "$1" = "$2" ] && return 1
  [ "$(printf '%s\n%s\n' "$1" "$2" | sort -V | head -1)" = "$1" ]
}

pruefsumme() {
  [ -f zustand.json ] || { echo "keine"; return; }
  # Inhalt und Rechte, beides zaehlt: das WLAN-Passwort steht im Klartext
  # darin und soll 0600 bleiben.
  printf '%s %s' "$(sha256sum zustand.json | cut -d' ' -f1)" \
                 "$(stat -c %a zustand.json)"
}

VORHER="$(pruefsumme)"

# ---------------------------------------------------------------- pruefen
blau "Vorher nachsehen"
command -v git >/dev/null || { fehl "git fehlt. Nachholen und erneut."; exit 1; }
[ -d .git ] || { fehl "Kein git-Arbeitsverzeichnis. Dann gibt es nichts zu holen."
                 exit 1; }

SCHMUTZ="$(git status --porcelain --untracked-files=no)"
if [ -n "$SCHMUTZ" ]; then
  fehl "Es gibt lokale Aenderungen. Abgebrochen, nichts angefasst."
  echo
  printf '%s\n' "$SCHMUTZ" | sed 's/^/     /'
  echo
  echo "   Entweder sichern und zuruecknehmen:"
  echo "     git diff > ~/devarenu-aenderungen.patch && git checkout -- ."
  echo "   Oder ansehen, was da steht, und dann entscheiden."
  exit 1
fi
gut "keine lokalen Aenderungen"

# ---------------------------------------------------------------- holen
blau "Aenderungen holen"
OBEN="$(git rev-parse --abbrev-ref --symbolic-full-name @{u} 2>/dev/null || true)"
if [ -z "$OBEN" ]; then
  fehl "Kein Gegenstueck eingestellt (kein origin). Es gibt nichts zu holen."
  exit 1
fi
FERN="${OBEN%%/*}"

# Nur Tags, und nur die. --tags allein wuerde die Zweige mitholen, und
# dann laege origin/main hier -- ein Stand, auf den nie vorgespult
# wird, aber nach dem jemand greifen koennte.
git fetch --quiet --tags --no-write-fetch-head "$FERN" \
  || { fehl "git fetch fehlgeschlagen. Netz?"; exit 1; }
gut "Tags von $FERN geholt"

HIER="$(tr -d '[:space:]' < VERSION 2>/dev/null || echo 0)"

# Das hoechste Tag, das NEUER ist als die hiesige Fassung. sort -V und
# nicht die Zeichenfolge: v0.2.9 kaeme sonst nach v0.2.13.
ZIEL=""
for T in $(git tag --list 'v[0-9]*' | sed 's/^v//' | sort -V); do
  ist_neuer "$HIER" "$T" && ZIEL="$T"
done
if [ -z "$ZIEL" ]; then
  gut "Hier laeuft $HIER. Es gibt kein neueres Tag."
  exit 0
fi
gut "$HIER -> $ZIEL, das ist neuer"

REF="refs/online/v$ZIEL"
git update-ref -d "$REF" 2>/dev/null || true
if ! git fetch --quiet "$FERN" "refs/tags/v$ZIEL:$REF"; then
  fehl "Das Tag v$ZIEL liess sich nicht holen."
  exit 1
fi

# ------------------------------------------------------------ Signatur
blau "Signatur"
# Geprueft wird gegen die Schluesselliste, die HIER liegt -- nie gegen
# eine mitgelieferte. Sonst brauchte ein Angreifer nur ein Repo, das
# seinen eigenen Schluessel mitbringt, und die Signatur pruefte sich
# selbst. Dieselbe Regel und derselbe Satz wie in stick_update.sh.
if [ ! -s "$ORDNER/schluessel.erlaubt" ]; then
  fehl "schluessel.erlaubt fehlt oder ist leer."
  echo "   Ohne die Liste der erlaubten Schluessel wird nichts eingespielt."
  git update-ref -d "$REF" 2>/dev/null || true
  exit 1
fi
KOPIE="$(mktemp)"; trap 'rm -f "$KOPIE"' EXIT INT TERM
install -m 600 "$ORDNER/schluessel.erlaubt" "$KOPIE"

# -c statt dauerhafter Einstellung: auf dem Gemeinderechner soll nach
# der Pruefung nichts in der git-Konfiguration zurueckbleiben.
if ! git -c "gpg.ssh.allowedSignersFile=$KOPIE" verify-tag "$REF" \
     >/dev/null 2>&1; then
  fehl "Die Signatur von v$ZIEL ist ungueltig. Es wird nichts eingespielt."
  echo "   Nachsehen:  git -c gpg.ssh.allowedSignersFile=schluessel.erlaubt \\"
  echo "                   verify-tag $REF"
  git update-ref -d "$REF" 2>/dev/null || true
  exit 1
fi
rm -f "$KOPIE"; trap - EXIT INT TERM
gut "Signatur von v$ZIEL ist gueltig"

# Die GEPRUEFTE Objekt-SHA. Ab hier wird nur noch mit ihr gearbeitet,
# nie mit dem Tagnamen: ein gleichnamiges lokales Tag wuerde sonst
# etwas Ungeprueftes unterschieben.
SHA="$(git rev-parse --verify "$REF^{commit}" 2>/dev/null)"
[ -n "$SHA" ] || { fehl "Die geprueufte Referenz laesst sich nicht aufloesen."; exit 1; }

if ! git merge-base --is-ancestor HEAD "$SHA"; then
  fehl "v$ZIEL baut nicht auf dem Stand dieses Rechners auf."
  echo "   Vorspulen geht nicht, und zusammenfuehren entscheidet dieses"
  echo "   Skript nicht. Nachsehen:  git log --oneline HEAD..$SHA"
  git update-ref -d "$REF" 2>/dev/null || true
  exit 1
fi

ALT_SHA="$(git rev-parse HEAD)"
git update-ref refs/devarenu/vorher "$ALT_SHA"

# ------------------------------------------------------------ Logik
# Ausgepackt und von dort ausgefuehrt, genau wie beim Stick: zwischen
# Pruefen und Ausfuehren soll niemand die Dateien tauschen koennen.
# Unter $ABLAGE und nicht unter /tmp -- dort darf jeder Benutzer
# Dateien anlegen.
blau "Einspielen"
ABLAGE="${DEVARENU_DATEN:-/var/lib/devarenu/updates}"
AUSZUG="$ABLAGE/logik-$ZIEL"
sudo rm -rf "$AUSZUG"
sudo mkdir -p "$AUSZUG"
sudo chown root:root "$AUSZUG"
sudo chmod 700 "$AUSZUG"
if ! git archive "$SHA" | sudo tar -x -C "$AUSZUG"; then
  fehl "Der geprueufte Stand liess sich nicht auspacken. Nichts geaendert."
  sudo rm -rf "$AUSZUG"
  exit 1
fi
if [ ! -f "$AUSZUG/aktualisierung.sh" ]; then
  fehl "v$ZIEL bringt keine aktualisierung.sh mit."
  echo "   Diese Fassung laesst sich mit diesem Weg nicht einspielen."
  sudo rm -rf "$AUSZUG"
  exit 1
fi
gut "Logik aus $(printf '%.7s' "$SHA") ausgepackt"

# Von hier an tut aktualisierung.sh die Arbeit: vorspulen, grosse
# Teile, Pakete, UNITS, Neustart, Gesundheitscheck. Dieselbe Datei,
# die auch ein Stick ausfuehrt.
RC=0
sudo env DEV_ORDNER="$ORDNER" DEV_BENUTZER="$BENUTZER" \
     DEV_ABLAGE="$ABLAGE" DEV_ALT_SHA="$ALT_SHA" DEV_REF="$REF" \
     DEV_VERSION="$ZIEL" DEV_HIER="$HIER" \
     bash "$AUSZUG/aktualisierung.sh" 2>&1 | grep -v '^MELDUNG|' | sed 's/^/   /'
RC=${PIPESTATUS[0]}
sudo rm -rf "$AUSZUG"
git update-ref -d "$REF" 2>/dev/null || true

if [ "$RC" != 0 ]; then
  fehl "Das Update ist gescheitert (Rueckgabe $RC)."
  echo "   Der Stand vor dem Versuch steht in refs/devarenu/vorher."
  echo "   Nachsehen:  journalctl -n 50   und   git log --oneline -3"
  exit 1
fi

NEU="$(tr -d '[:space:]' < VERSION 2>/dev/null || echo unbekannt)"
gut "Fassung $HIER -> $NEU"

# ---------------------------------------------------------------- Zustand
blau "Einstellungen"
NACHHER="$(pruefsumme)"
if [ "$VORHER" = "$NACHHER" ]; then
  gut "zustand.json unveraendert"
else
  fehl "zustand.json hat sich geaendert. Das darf ein Update nicht."
  echo "     vorher:  $VORHER"
  echo "     nachher: $NACHHER"
fi

blau "Ergebnis"
printf '   \033[32mAlles bereit.\033[0m Fassung %s\n' "$NEU"
# Gesundheitscheck und -- wenn sich venv oder grosse Teile geaendert
# haben -- der Selbsttest sind in aktualisierung.sh schon gelaufen.
# Waeren sie fehlgeschlagen, stuende dieses Skript hier nicht mehr.
printf '   Geprueft: Signatur, Units, Gesundheit. Nachsehen:\n'
printf '     bash pruefen.sh\n\n'
exit 0
