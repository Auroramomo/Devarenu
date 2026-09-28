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

# Wohin die Units geschrieben werden. Die Vorgabe ist der echte Ort;
# gesetzt wird die Variable nur vom Pruefstand -- sonst liesse sich
# der Rueckweg gar nicht pruefen, und ausgerechnet er ist der Teil,
# der nur im Ernstfall laeuft. aktualisierung.sh kennt dieselbe
# Variable seit 0.2.14.
UNIT_ORDNER="${DEVARENU_UNIT_ORDNER:-/etc/systemd/system}"
blau() { printf '\n\033[1;34m== %s\033[0m\n' "$1"; }
gut()  { printf '   \033[32mok\033[0m   %s\n' "$1"; }
warn() { printf '   \033[33m!\033[0m    %s\n' "$1"; }
fehl() { printf '   \033[31mFEHLT\033[0m %s\n' "$1"; }

# Wem der Ordner gehoert -- unter diesem Benutzer laeuft der Dienst.
# Nicht $USER: dieses Skript wird auch mit sudo aufgerufen.
BENUTZER="$(stat -c %U "$ORDNER" 2>/dev/null || id -un)"

# ZWEI WEGE HINEIN, und sie brauchen verschiedene Rechte.
#
# Von Hand ruft der Besitzer dieses Skript auf; Privilegiertes holt es
# sich mit sudo. Seit 0.3.3 ruft es aber auch der Fenster-Timer auf,
# und der laeuft als WURZEL. Liefen die git-Befehle dann als root,
# stuenden root-eigene Objekte in .git, der Dienstbenutzer kaeme
# hinterher nicht mehr an sein eigenes Repo, und git meldete
# "dubious ownership".
#
# Also dasselbe Paar wie im Kern: alles mit git ueber als_benutzer,
# alles Privilegierte ueber als_wurzel. Beide sind ein no-op, wenn man
# ohnehin schon der Richtige ist.
als_benutzer() {
  if [ "$(id -u)" = "0" ] && [ "$BENUTZER" != "root" ]; then
    runuser -u "$BENUTZER" -- "$@"
  else
    "$@"
  fi
}
als_wurzel() {
  if [ "$(id -u)" = "0" ]; then
    "$@"
  else
    sudo "$@"
  fi
}

# Ein abgeloester HEAD haelt jedes Update an -- aber nicht immer
# muss er das. Zeigt ein lokaler Zweig auf GENAU den Commit, auf dem
# HEAD steht, ist nichts verloren: dann wird nur die Referenz
# umgehaengt, keine Datei angefasst, und es geht weiter.
#
# So stand der Gemeinderechner am 27.09.: HEAD auf tags/v0.2.11^0,
# main auf demselben Commit. Kein Weg im Repo hinterlaesst das --
# es muss von Hand entstanden sein --, und der Updater brach ab,
# obwohl nichts fehlte.
#
# Zeigt KEIN Zweig darauf, bleibt es beim Abbruch. Dann liegt dort
# Arbeit, die ein Anhaengen verlieren wuerde.
#
# Rueckgaengig mit:  git checkout --detach
wieder_anhaengen() {
  local zweige haupt
  zweige="$(als_benutzer git for-each-ref --format='%(refname:short)' \
            refs/heads --points-at HEAD 2>/dev/null)"
  [ -n "$zweige" ] || return 1
  if printf '%s\n' "$zweige" | grep -qx main; then
    haupt=main
  elif [ "$(printf '%s\n' "$zweige" | wc -l)" = 1 ]; then
    haupt="$zweige"
  else
    return 1
  fi
  als_benutzer git symbolic-ref HEAD "refs/heads/$haupt" || return 1
  return 0
}

# Welche Units gesichert und zurueckgeholt werden. Dieselbe Liste wie
# in stick_update.sh und aktualisierung.sh -- online_test.sh
# vergleicht sie, damit die drei nicht auseinanderlaufen.
UNITS_GESICHERT="devarenu.service devarenu-stick@.service \
devarenu-update.service devarenu-update.timer \
devarenu-fenster.service devarenu-fenster.timer \
devarenu-fenster-wecker.service"

# DER RUECKWEG.
#
# Bis 0.3.2 gab es ihn auf diesem Weg nicht: scheiterte
# aktualisierung.sh mittendrin, blieb der Rechner stehen, wo er
# gerade war -- halb neuer Code, womoeglich neue Units, und niemand
# vor Ort. Der Stick hatte seinen Rueckweg seit 0.2.12.
#
# Schritt fuer Schritt dasselbe wie zurueck() im Kern. Zwei Kopien,
# weil der Kern von keiner versionierten Datei abhaengen darf -- er
# ist der Rettungsweg, und ein Rettungsweg, der ein Update
# voraussetzt, ist keiner. Gegen das Auseinanderlaufen vergleicht
# online_test.sh beide Listen.
zurueck() {
  local sha="$1" sicherung="${2:-}"
  warn "zurueck auf $(printf '%.7s' "$sha")"
  als_benutzer git reset --hard --quiet "$sha" \
    || fehl "git reset fehlgeschlagen -- der Code ist NICHT zurueck."

  if [ -n "$sicherung" ] && [ -d "$sicherung" ]; then
    # venv: nur der Symlink. Ein venv laesst sich nicht verschieben,
    # in seinen Skripten stehen absolute Pfade.
    if [ -f "$sicherung/venv-vorher" ]; then
      local altes; altes="$(als_wurzel cat "$sicherung/venv-vorher")"
      if [ -n "$altes" ] && [ -d "$ORDNER/$altes" ]; then
        als_benutzer ln -sfn "$altes" "$ORDNER/.venv"
        warn "venv zurueck auf $altes"
      fi
    fi

    local u geaendert=nein
    for u in $UNITS_GESICHERT; do
      als_wurzel test -f "$sicherung/units/$u" || continue
      if ! als_wurzel cmp -s "$sicherung/units/$u" "$UNIT_ORDNER/$u"; then
        als_wurzel cp -a "$sicherung/units/$u" "$UNIT_ORDNER/$u"
        warn "$u zurueckgeholt"
        geaendert=ja
      fi
    done
    [ "$geaendert" = ja ] && als_wurzel systemctl daemon-reload 2>/dev/null

    # zustand.json und netz.json NUR, wenn sie sich geaendert haben.
    # Eine unveraenderte Datei anzufassen waere ein zweiter Eingriff
    # ohne Grund -- und sie gehoeren der Gemeinde, nicht dem Update.
    local d
    for d in zustand.json netz.json; do
      als_wurzel test -f "$sicherung/$d" || continue
      if ! als_wurzel cmp -s "$sicherung/$d" "$ORDNER/$d"; then
        als_wurzel cp -a "$sicherung/$d" "$ORDNER/$d"
        als_wurzel chown "$BENUTZER" "$ORDNER/$d" 2>/dev/null || true
        warn "$d zurueckgeholt (das Update hatte sie veraendert)"
      fi
    done
  fi

  als_wurzel systemctl restart "$NAME" \
    || fehl "Neustart nach dem Zurueckgehen fehlgeschlagen."

  # Ein Rueckweg, der selbst scheitert, ist die Lage, in der niemand
  # mehr etwas tun kann. Sie darf nicht als "zurueckgerollt"
  # durchgehen.
  if als_benutzer bash "$ORDNER/gesundheit.sh" >/dev/null 2>&1; then
    gut "zurueck auf $HIER, der Rechner ist gesund"
    RUECKWEG=gelungen
  else
    fehl "ZURUECK, ABER NICHT GESUND. Hier muss jemand nachsehen."
    echo "   journalctl -u $NAME -n 50"
    RUECKWEG=gescheitert
  fi
}
RUECKWEG=""

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

SCHMUTZ="$(als_benutzer git status --porcelain --untracked-files=no)"
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
# Abgeloester HEAD zuerst: sonst scheitert gleich @{u} und dieses
# Skript meldete "kein origin" -- eine Auskunft, die mit der Lage
# nichts zu tun hat.
if [ "$(als_benutzer git rev-parse --abbrev-ref HEAD)" = "HEAD" ]; then
  if wieder_anhaengen; then
    warn "HEAD war abgeloest und wurde wieder angehaengt."
    echo "   Keine Datei geaendert. Zurueck mit:  git checkout --detach"
  else
    fehl "HEAD ist abgeloest, und kein Zweig zeigt auf diesen Stand."
    echo "   Anhaengen wuerde Arbeit verlieren. Nachsehen:"
    echo "     git log --oneline -3   und   git branch -a"
    exit 1
  fi
fi

OBEN="$(als_benutzer git rev-parse --abbrev-ref --symbolic-full-name @{u} 2>/dev/null || true)"
if [ -z "$OBEN" ]; then
  fehl "Kein Gegenstueck eingestellt (kein origin). Es gibt nichts zu holen."
  exit 1
fi
FERN="${OBEN%%/*}"

# Nur Tags, und nur die. --tags allein wuerde die Zweige mitholen, und
# dann laege origin/main hier -- ein Stand, auf den nie vorgespult
# wird, aber nach dem jemand greifen koennte.
if ! als_benutzer git fetch --quiet --tags --no-write-fetch-head "$FERN"; then
  fehl "git fetch fehlgeschlagen."
  echo "   Entweder kein Netz -- oder ein Tag zeigt drueben woanders hin"
  echo "   als hier. Das wird ABSICHTLICH nicht ueberschrieben: ein"
  echo "   umgebogenes Tag darf kein geprueuftes ersetzen. Nachsehen:"
  echo "     git fetch --tags --dry-run"
  exit 1
fi
gut "Tags von $FERN geholt"

HIER="$(tr -d '[:space:]' < VERSION 2>/dev/null || echo 0)"

# Das hoechste Tag, das NEUER ist als die hiesige Fassung. sort -V und
# nicht die Zeichenfolge: v0.2.9 kaeme sonst nach v0.2.13.
ZIEL=""
for T in $(als_benutzer git tag --list 'v[0-9]*' | sed 's/^v//' | sort -V); do
  ist_neuer "$HIER" "$T" && ZIEL="$T"
done
if [ -z "$ZIEL" ]; then
  gut "Hier laeuft $HIER. Es gibt kein neueres Tag."
  exit 0
fi
gut "$HIER -> $ZIEL, das ist neuer"

REF="refs/online/v$ZIEL"
als_benutzer git update-ref -d "$REF" 2>/dev/null || true
if ! als_benutzer git fetch --quiet "$FERN" "refs/tags/v$ZIEL:$REF"; then
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
  als_benutzer git update-ref -d "$REF" 2>/dev/null || true
  exit 1
fi
# 644 und nicht 600: gelesen wird die Kopie von als_benutzer, angelegt
# womoeglich von der Wurzel (aus dem Fenster-Timer). Eine Liste
# oeffentlicher Schluessel ist nichts Geheimes -- der Kern macht es
# genauso. Bei 600 root staende hier "Signatur ungueltig", obwohl sie
# stimmt: derselbe Fehler wie beim Bundle am 27.09.
KOPIE="$(mktemp)"; trap 'rm -f "$KOPIE"' EXIT INT TERM
install -m 644 "$ORDNER/schluessel.erlaubt" "$KOPIE"

# -c statt dauerhafter Einstellung: auf dem Gemeinderechner soll nach
# der Pruefung nichts in der git-Konfiguration zurueckbleiben.
if ! als_benutzer git -c "gpg.ssh.allowedSignersFile=$KOPIE" verify-tag "$REF" \
     >/dev/null 2>&1; then
  fehl "Die Signatur von v$ZIEL ist ungueltig. Es wird nichts eingespielt."
  echo "   Nachsehen:  git -c gpg.ssh.allowedSignersFile=schluessel.erlaubt \\"
  echo "                   verify-tag $REF"
  als_benutzer git update-ref -d "$REF" 2>/dev/null || true
  exit 1
fi
rm -f "$KOPIE"; trap - EXIT INT TERM
gut "Signatur von v$ZIEL ist gueltig"

# Die GEPRUEFTE Objekt-SHA. Ab hier wird nur noch mit ihr gearbeitet,
# nie mit dem Tagnamen: ein gleichnamiges lokales Tag wuerde sonst
# etwas Ungeprueftes unterschieben.
SHA="$(als_benutzer git rev-parse --verify "$REF^{commit}" 2>/dev/null)"
[ -n "$SHA" ] || { fehl "Die geprueufte Referenz laesst sich nicht aufloesen."; exit 1; }

if ! als_benutzer git merge-base --is-ancestor HEAD "$SHA"; then
  fehl "v$ZIEL baut nicht auf dem Stand dieses Rechners auf."
  echo "   Vorspulen geht nicht, und zusammenfuehren entscheidet dieses"
  echo "   Skript nicht. Nachsehen:  git log --oneline HEAD..$SHA"
  als_benutzer git update-ref -d "$REF" 2>/dev/null || true
  exit 1
fi

ALT_SHA="$(als_benutzer git rev-parse HEAD)"
als_benutzer git update-ref refs/devarenu/vorher "$ALT_SHA"

# ------------------------------------------------------------ Logik
# Ausgepackt und von dort ausgefuehrt, genau wie beim Stick: zwischen
# Pruefen und Ausfuehren soll niemand die Dateien tauschen koennen.
# Unter $ABLAGE und nicht unter /tmp -- dort darf jeder Benutzer
# Dateien anlegen.
blau "Einspielen"
ABLAGE="${DEVARENU_DATEN:-/var/lib/devarenu/updates}"
AUSZUG="$ABLAGE/logik-$ZIEL"
als_wurzel rm -rf "$AUSZUG"
als_wurzel mkdir -p "$AUSZUG"
als_wurzel chown root:root "$AUSZUG"
als_wurzel chmod 700 "$AUSZUG"
if ! als_benutzer git archive "$SHA" | als_wurzel tar -x -C "$AUSZUG"; then
  fehl "Der geprueufte Stand liess sich nicht auspacken. Nichts geaendert."
  als_wurzel rm -rf "$AUSZUG"
  exit 1
fi
if [ ! -f "$AUSZUG/aktualisierung.sh" ]; then
  fehl "v$ZIEL bringt keine aktualisierung.sh mit."
  echo "   Diese Fassung laesst sich mit diesem Weg nicht einspielen."
  als_wurzel rm -rf "$AUSZUG"
  exit 1
fi
gut "Logik aus $(printf '%.7s' "$SHA") ausgepackt"

# ------------------------------------------------------- Sicherung
# Bevor irgendetwas angefasst wird. Genau das, was zurueckgeholt
# werden koennen muss -- dieselben Dateien wie beim Stick.
SICHERUNG="$ABLAGE/vorher-$ZIEL"
als_wurzel rm -rf "$SICHERUNG"
als_wurzel mkdir -p "$SICHERUNG/units"
als_wurzel chmod 700 "$SICHERUNG"
for u in $UNITS_GESICHERT; do
  [ -f "$UNIT_ORDNER/$u" ] \
    && als_wurzel cp -a "$UNIT_ORDNER/$u" "$SICHERUNG/units/$u"
done
for d in zustand.json netz.json; do
  [ -f "$ORDNER/$d" ] && als_wurzel cp -a "$ORDNER/$d" "$SICHERUNG/$d"
done
als_wurzel chmod -R go-rwx "$SICHERUNG" 2>/dev/null || true
gut "Stand gesichert: Units, zustand.json, netz.json"

# Welche Fehler gab es SCHON? Ohne diese Grundlinie zaehlt der
# Gesundheitscheck nach dem Update JEDEN vorhandenen Befund als neu
# -- und rollt ein tadelloses Update zurueck, weil der Autologin
# schon vorher nicht eingerichtet war. Der Kern tut das seit 0.2.12
# (stick_update.sh, "Welche Fehler gab es SCHON?"); hier fehlte es.
#
# Aufgefallen erst, als der Pruefstand gegen die ECHTE
# aktualisierung.sh lief statt gegen eine Attrappe.
DEV_SICHERUNG="$SICHERUNG" als_benutzer bash "$ORDNER/gesundheit.sh" --vorher \
  >/dev/null 2>&1 || true

# Von hier an tut aktualisierung.sh die Arbeit: vorspulen, grosse
# Teile, Pakete, UNITS, Neustart, Gesundheitscheck. Dieselbe Datei,
# die auch ein Stick ausfuehrt.
RC=0
als_wurzel env DEV_ORDNER="$ORDNER" DEV_BENUTZER="$BENUTZER" \
     DEV_ABLAGE="$ABLAGE" DEV_ALT_SHA="$ALT_SHA" DEV_REF="$REF" \
     DEV_VERSION="$ZIEL" DEV_HIER="$HIER" DEV_SICHERUNG="$SICHERUNG" \
     bash "$AUSZUG/aktualisierung.sh" 2>&1 | grep -v '^MELDUNG|' | sed 's/^/   /'
RC=${PIPESTATUS[0]}
als_wurzel rm -rf "$AUSZUG"
als_benutzer git update-ref -d "$REF" 2>/dev/null || true

if [ "$RC" != 0 ]; then
  fehl "Das Update ist gescheitert (Rueckgabe $RC)."
  zurueck "$ALT_SHA" "$SICHERUNG"
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
