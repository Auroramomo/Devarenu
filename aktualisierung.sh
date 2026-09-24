#!/usr/bin/env bash
# Was beim Einspielen eines Updates zu tun ist -- die VERSIONIERTE
# Haelfte des Updaters.
#
# NICHT von Hand aufrufen. stick_update.sh fuehrt dieses Skript aus,
# und zwar aus einem Auszug des GEPRUEFTEN Tags, nie aus Dateien vom
# Stick.
#
# WARUM ZWEIGETEILT
# -----------------
# Der Kern (stick_update.sh) trifft zwei Arten von Entscheidungen:
# Vertrauen (ist das Bundle echt, ist der Tag signiert, ist die Fassung
# neuer) und Rettung (wie kommt der Rechner zurueck, wenn es schiefgeht).
# Beides darf nicht von Code abhaengen, den ein Stick mitbringt, und
# beides soll sich praktisch nie aendern.
#
# Alles andere ist Verfahren: welche Dateien wohin, welche Pakete,
# welche Units, was "gesund" heisst. Das aendert sich mit jeder
# Fassung -- und weil es HIER steht, kommt es mit dem Update selbst.
# Ein Fehler darin laesst sich mit dem naechsten Update beheben. Stuende
# er im Kern, muesste jemand hinfahren.
#
# WAS DER KERN UEBERGIBT (als Umgebung)
#   DEV_ORDNER      der Projektordner
#   DEV_BENUTZER    der Benutzer, dem er gehoert
#   DEV_ABLAGE      /var/lib/devarenu/updates -- Sicherungen, Wheels,
#                   grosse Teile vom Stick
#   DEV_ALT_SHA     der Stand vor dem Update
#   DEV_REF         refs/stick/vX.Y.Z -- die GEPRUEFTE Objekt-SHA
#   DEV_VERSION     die neue Fassung
#   DEV_HIER        die bisherige Fassung
#   DEV_SICHERUNG   Unterordner mit allem, was zurueckgeholt werden kann
#
# RUECKGABE
#   0   eingespielt und gesund
#   1   gescheitert -- der Kern rollt zurueck
#   Eine Zeile "MELDUNG|<text>" auf der Standardausgabe wird vom Kern
#   ans Pult weitergereicht.

set -u
ORDNER="${DEV_ORDNER:?fehlt}"
BENUTZER="${DEV_BENUTZER:?fehlt}"
ABLAGE="${DEV_ABLAGE:?fehlt}"
ALT_SHA="${DEV_ALT_SHA:?fehlt}"
REF="${DEV_REF:?fehlt}"
VERSION="${DEV_VERSION:?fehlt}"
HIER="${DEV_HIER:-unbekannt}"
SICHERUNG="${DEV_SICHERUNG:?fehlt}"
NAME=devarenu

cd "$ORDNER"

blau() { printf '\n\033[1;34m== %s\033[0m\n' "$*"; }
gut()  { printf '   \033[32mok\033[0m    %s\n' "$*"; }
warn() { printf '   \033[33m!\033[0m     %s\n' "$*"; }
fehl() { printf '   \033[31mFEHLT\033[0m %s\n' "$*"; }
info() { printf '         %s\n' "$*"; }
melden() { printf 'MELDUNG|%s\n' "$*"; }

als_benutzer() { sudo -u "$BENUTZER" -H "$@"; }

PY_AKTIV="$ORDNER/.venv/bin/python"

# ------------------------------------------------- Lokale Aenderungen
# Der signierte Stand gewinnt. Was jemand vor Ort an einer versionierten
# Datei geaendert hat, wird gesichert und dann ueberschrieben -- nicht
# weil es wertlos waere, sondern weil sonst jedes Update an ihm haengen
# bleibt. Genau daran stand der Gemeinderechner vor 0.2.12 fest.
#
# Nicht versionierte Dateien bleiben unberuehrt. zustand.json, netz.json
# und die venvs gehoeren dazu.
blau "Lokale Aenderungen"
PATCH=""
if ! als_benutzer git diff --quiet HEAD 2>/dev/null; then
  PATCH="$ABLAGE/lokal-$(date +%Y%m%d-%H%M%S).patch"
  als_benutzer git diff HEAD > "$PATCH" 2>/dev/null
  chmod 600 "$PATCH" 2>/dev/null || true
  local_zeilen="$(wc -l < "$PATCH")"
  warn "$local_zeilen Zeilen lokale Aenderungen gesichert:"
  info "$PATCH"
  als_benutzer git checkout -- . 2>/dev/null || true
  gut "Arbeitsbaum zurueckgesetzt"
else
  gut "keine lokalen Aenderungen"
fi

# ------------------------------------------------------------- Code
blau "Code"
# ^{commit} an der GEPRUEFTEN Referenz, nicht am Tagnamen: ein
# gleichnamiger lokaler Tag wuerde sonst etwas Ungeprueftes
# unterschieben. Nachgewiesen -- mit einem lokal ueberschriebenen Tag
# nimmt "git archive v9.9.9" das Gefaelschte, "git archive
# refs/stick/v9.9.9" das Echte.
if ! als_benutzer git merge --ff-only --quiet "$REF^{commit}" 2>/dev/null; then
  fehl "Der neue Stand laesst sich nicht vorspulen."
  melden "Update $VERSION passt nicht auf den hiesigen Stand."
  exit 1
fi
gut "auf $(als_benutzer git rev-parse --short HEAD) vorgespult"

# --------------------------------------------------------- Grosse Teile
# teile.json nennt, was an Modellen, Stimmen und Paketen dazugehoert --
# mit Groesse und Pruefsumme. Fehlt die Datei, ist es ein Update ohne
# grosse Teile, und das ist der Normalfall.
if [ -f "$ORDNER/teile.json" ]; then
  blau "Grosse Teile"
  if ! als_benutzer "$PY_AKTIV" "$ORDNER/teile.py" --einspielen \
       --quelle "$ABLAGE/teile" --sicherung "$SICHERUNG/teile"; then
    fehl "Grosse Teile liessen sich nicht einspielen."
    melden "Update $VERSION braucht Dateien, die der Stick nicht mitbrachte."
    exit 1
  fi
  gut "grosse Teile vollstaendig"
else
  gut "keine grossen Teile in dieser Fassung"
fi

# ------------------------------------------------------------- Pakete
# venv wird getauscht, nicht ueberschrieben: pip schreibt in vorhandene
# Pakete hinein, ein Rueckfall waere dort kein Loeschen. Also ein
# zweites venv daneben und ein Symlink, der umgelegt wird.
#
# venvs sind NICHT verschiebbar -- die Pfade stehen in den Skripten der
# Umgebung. Deshalb liegen beide im Projektordner und heissen .venv-a
# und .venv-b; verschoben wird nie etwas.
blau "Pakete"
VENV_GEWECHSELT=nein
if ! als_benutzer git diff --quiet "$ALT_SHA" HEAD -- requirements.txt; then
  if [ ! -d "$ABLAGE/wheels" ]; then
    fehl "requirements.txt hat sich geaendert, der Stick brachte keine wheels/"
    melden "Das Update braucht neue Pakete, der Stick brachte keine mit."
    exit 1
  fi
  # Welches ist gerade aktiv? Der Symlink sagt es; ist .venv noch ein
  # echter Ordner (Stand vor 0.2.13), wird er zu .venv-a gemacht.
  if [ -L "$ORDNER/.venv" ]; then
    AKTIV="$(readlink "$ORDNER/.venv")"
  else
    info ".venv ist noch ein Ordner -- wird zu .venv-a"
    als_benutzer mv "$ORDNER/.venv" "$ORDNER/.venv-a" || {
      fehl "Umbenennen nach .venv-a fehlgeschlagen"; exit 1; }
    als_benutzer ln -s .venv-a "$ORDNER/.venv"
    AKTIV=".venv-a"
  fi
  case "$AKTIV" in *a) NEU=".venv-b" ;; *) NEU=".venv-a" ;; esac
  info "$AKTIV ist aktiv, gebaut wird $NEU"

  als_benutzer rm -rf "$ORDNER/$NEU"
  if ! als_benutzer python3 -m venv "$ORDNER/$NEU"; then
    fehl "$NEU liess sich nicht anlegen"
    melden "Das Update konnte keine neue Paketumgebung bauen."
    exit 1
  fi
  # --no-index: kein Wort nach draussen. Was nicht auf dem Stick liegt,
  # gibt es nicht, und das soll hier scheitern statt in einer
  # Zeitueberschreitung zu haengen.
  if ! als_benutzer "$ORDNER/$NEU/bin/python" -m pip install --quiet \
       --no-index --find-links "$ABLAGE/wheels" -r "$ORDNER/requirements.txt"; then
    fehl "pip konnte nicht alles aus wheels/ installieren"
    als_benutzer rm -rf "$ORDNER/$NEU"
    melden "Die Pakete auf dem Stick reichen nicht aus."
    exit 1
  fi
  # Umschalten: erst jetzt, wenn das neue venv vollstaendig ist.
  als_benutzer ln -sfn "$NEU" "$ORDNER/.venv"
  printf '%s\n' "$AKTIV" > "$SICHERUNG/venv-vorher"
  VENV_GEWECHSELT=ja
  gut "$NEU gebaut und aktiv, $AKTIV bleibt als Rueckfall liegen"
else
  gut "requirements.txt unveraendert, keine Pakete noetig"
fi

# -------------------------------------------------------------- Units
# Bis 0.2.12 schrieb KEIN Update die Units neu -- das tat allein
# dienst.sh bei der Ersteinrichtung. Eine geaenderte Vorlage lag im
# Ordner und wirkte nicht, und niemand sah es.
blau "Dienste"
UNITS_GEAENDERT=nein
for paar in "devarenu.service:devarenu.service.vorlage" \
            "devarenu-stick@.service:devarenu-stick@.service.vorlage" \
            "devarenu-update.service:devarenu-update.service.vorlage" \
            "devarenu-update.timer:devarenu-update.timer.vorlage"; do
  unit="${paar%%:*}"; vorlage="${paar#*:}"
  ziel="/etc/systemd/system/$unit"
  [ -f "$ziel" ] || continue          # nicht eingerichtet, nichts zu tun
  [ -f "$ORDNER/$vorlage" ] || continue
  neu="$(sed -e "s|@ORDNER@|$ORDNER|g" -e "s|@BENUTZER@|$BENUTZER|g" \
             -e "s|@PORT@|${DEVARENU_PORT:-8000}|g" "$ORDNER/$vorlage")"
  if [ "$neu" != "$(cat "$ziel")" ]; then
    printf '%s\n' "$neu" > "$ziel"
    chmod 644 "$ziel"
    gut "$unit neu geschrieben"
    UNITS_GEAENDERT=ja
  fi
done
if [ "$UNITS_GEAENDERT" = ja ]; then
  systemctl daemon-reload && gut "systemd neu geladen"
else
  gut "Units unveraendert"
fi

# ------------------------------------------------------------- Dienst
blau "Neustart"
systemctl restart "$NAME" || {
  fehl "Neustart fehlgeschlagen"
  melden "Der Dienst liess sich mit $VERSION nicht starten."
  exit 1; }

# ------------------------------------------------------ Gesundheit
blau "Gesundheitscheck"
if ! als_benutzer "$ORDNER/gesundheit.sh"; then
  fehl "Der Rechner ist nach dem Update nicht gesund."
  melden "Update $VERSION ist fehlgeschlagen."
  exit 1
fi

# Haben sich venv oder grosse Teile geaendert, kommt der Selbsttest
# dazu. Er dauert Minuten -- das ist hier egal: eingespielt wird nur,
# wenn niemand zuhoert.
if [ "$VENV_GEWECHSELT" = ja ] || [ -f "$ORDNER/teile.json" ]; then
  info "venv oder grosse Teile geaendert -- Selbsttest laeuft mit."
  if ! als_benutzer "$PY_AKTIV" "$ORDNER/selbsttest.py" >/dev/null 2>&1; then
    fehl "Der Selbsttest schlaegt fehl."
    melden "Update $VERSION besteht den Selbsttest nicht."
    exit 1
  fi
  gut "Selbsttest bestanden"
fi

# ------------------------------------------------------- Aufraeumen
# ERST JETZT. Bis hierher musste alles zurueckholbar bleiben.
blau "Aufraeumen"
if [ "$VENV_GEWECHSELT" = ja ]; then
  ALT_VENV="$(cat "$SICHERUNG/venv-vorher" 2>/dev/null)"
  if [ -n "$ALT_VENV" ] && [ -d "$ORDNER/$ALT_VENV" ]; then
    als_benutzer rm -rf "$ORDNER/$ALT_VENV"
    gut "$ALT_VENV entfernt"
  fi
fi
if [ -f "$ORDNER/teile.json" ]; then
  als_benutzer "$PY_AKTIV" "$ORDNER/teile.py" --aufraeumen \
    --sicherung "$SICHERUNG/teile" 2>/dev/null \
    && gut "alte grosse Teile entfernt"
fi

# Der Reparaturvorrat muss nachziehen, sonst stellt eine spaetere
# Reparatur das alte Modell wieder her.
if [ -f /opt/devarenu-vorrat/vorrat.json ]; then
  info "Reparaturvorrat wird auf $VERSION nachgezogen."
  if bash "$ORDNER/vorrat_bauen.sh" --nur-etikett >/dev/null 2>&1; then
    gut "Vorrat nachgezogen"
  else
    warn "Vorrat liess sich nicht nachziehen -- beim naechsten Besuch"
    warn "mit Leitung:  sudo bash vorrat_bauen.sh"
  fi
fi

[ -n "$PATCH" ] && melden "Lokale Aenderungen wurden ueberschrieben. Gesichert als $PATCH."
blau "Fertig"
exit 0
