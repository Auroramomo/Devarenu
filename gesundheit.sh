#!/usr/bin/env bash
# Laeuft der Rechner nach einem Update noch?
#
#   bash gesundheit.sh              pruefen, Rueckgabe 0 wenn gesund
#   bash gesundheit.sh --vorher     Befunde merken, ohne zu urteilen
#
# Gebraucht vom Updater. Absichtlich klein und schnell: es geht um die
# Frage "ist das hier kaputt", nicht um eine Durchsicht. Dafuer gibt es
# pruefen.sh.
#
# Gesund heisst:
#   - der Dienst laeuft
#   - /api/zustand antwortet binnen 120 Sekunden
#   - er meldet die erwartete Fassung, falls eine vorgegeben ist
#   - /pult kommt mit 200 und ist nicht die Fehlerseite (seit 0.5.2)
#   - der Systemcheck hat keinen NEUEN Fehler, den es vorher nicht gab
#
# Der letzte Punkt ist der Grund fuer --vorher: ein Rechner, bei dem
# schon vor dem Update etwas im Argen lag, soll nicht deshalb ein
# Update zurueckrollen.

set -u
ORDNER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ORDNER"

PORT="${DEVARENU_PORT:-8000}"
ERWARTET="${DEV_VERSION:-}"
MERKDATEI="${DEV_SICHERUNG:-/tmp}/befunde-vorher"
PY="$ORDNER/.venv/bin/python"

gut()  { printf '   \033[32mok\033[0m    %s\n' "$*"; }
fehl() { printf '   \033[31mFEHLT\033[0m %s\n' "$*"; }
info() { printf '         %s\n' "$*"; }

befunde_jetzt() {
  [ -x "$PY" ] || return 1
  "$PY" - <<'PYCODE' 2>/dev/null
import sys
sys.path.insert(0, ".")
try:
    import systemcheck
    for b in systemcheck.pruefen():
        if b.schwere == systemcheck.FEHLT:
            print(b.kennung)
except Exception:
    pass
PYCODE
}

if [ "${1:-}" = "--vorher" ]; then
  # "Gemerkt" wird nur gemeldet, wenn wirklich etwas dasteht.
  #
  # Vorher lief das durch, egal was passierte: mkdir und die
  # Umleitung scheiterten mit "Keine Berechtigung" -- die Ablage
  # gehoerte root und war nicht durchgehbar --, und die naechste
  # Zeile meldete trotzdem "Befunde vor dem Update gemerkt". Der
  # Aufrufer haengt ein "|| true" an, also fiel auch dort nichts auf.
  #
  # Es ist der schlimmere der beiden Fehler gewesen. Ohne Grundlinie
  # zaehlt hinterher JEDER vorhandene Befund als neu, und ein
  # tadelloses Update waere zurueckgerollt worden -- auf einem
  # Rechner, auf dem nichts kaputt war.
  ORDNER_MERK="$(dirname "$MERKDATEI")"
  if ! mkdir -p "$ORDNER_MERK" 2>/dev/null; then
    fehl "$ORDNER_MERK laesst sich nicht anlegen."
    info "Ohne Grundlinie gilt hinterher jeder Befund als neu."
    exit 1
  fi
  if ! befunde_jetzt | sort > "$MERKDATEI" 2>/dev/null; then
    fehl "$MERKDATEI laesst sich nicht schreiben."
    info "$(ls -ld "$ORDNER_MERK" 2>/dev/null)"
    info "Ohne Grundlinie gilt hinterher jeder Befund als neu."
    exit 1
  fi
  if [ ! -f "$MERKDATEI" ]; then
    fehl "$MERKDATEI ist nach dem Schreiben nicht da."
    exit 1
  fi
  info "$(wc -l < "$MERKDATEI") Befunde vor dem Update gemerkt"
  exit 0
fi

# ------------------------------------------------------------ Dienst
if ! systemctl is-active --quiet devarenu; then
  fehl "Der Dienst laeuft nicht."
  exit 1
fi
gut "Dienst laeuft"

# --------------------------------------------------------- Antwortet er?
# 120 Sekunden: Whisper und die Stimmen brauchen beim ersten Start
# Zeit. Weniger waere eine Fehlmeldung, mehr eine Geduldsprobe.
ANTWORT=""
for _ in $(seq 1 60); do
  ANTWORT="$(curl -s -m 3 "http://127.0.0.1:$PORT/api/zustand" 2>/dev/null)"
  [ -n "$ANTWORT" ] && break
  sleep 2
done
if [ -z "$ANTWORT" ]; then
  fehl "Der Dienst antwortet nach zwei Minuten nicht."
  exit 1
fi
gut "antwortet"

if [ -n "$ERWARTET" ]; then
  GEMELDET="$(printf '%s' "$ANTWORT" \
    | sed -n 's/.*"fassung"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
  if [ "$GEMELDET" != "$ERWARTET" ]; then
    fehl "Er meldet Fassung ${GEMELDET:-nichts}, erwartet war $ERWARTET."
    exit 1
  fi
  gut "meldet Fassung $ERWARTET"
fi

# ------------------------------------------------------------- Das Pult
# Seit 0.5.2 liegt es in web/pult.html und wird bei jedem Aufruf
# gelesen. Fehlt die Datei, antwortet der Dienst trotzdem auf
# /api/zustand -- nur das Pult ist eine Fehlerseite, und niemand kommt
# an die Bedienung. Gefragt wird ueber 127.0.0.1: von dort gilt der
# Aufruf als "am Rechner", ein Pult-Passwort steht nicht im Weg.
#
# 200 UND nicht die Fehlerseite. Die kommt heute mit 500, aber darauf
# allein soll sich dieser Check nicht verlassen.
PULT_ANTWORT="$(curl -s -m 10 -w '\n%{http_code}' \
                "http://127.0.0.1:$PORT/pult" 2>/dev/null)"
PULT_STATUS="$(printf '%s' "$PULT_ANTWORT" | tail -n 1)"
if [ "$PULT_STATUS" != 200 ]; then
  fehl "Das Pult kommt nicht (HTTP ${PULT_STATUS:-keine Antwort})."
  exit 1
fi
if printf '%s' "$PULT_ANTWORT" | grep -q 'pult.html fehlt'; then
  fehl "Das Pult kommt nicht: web/pult.html fehlt."
  exit 1
fi
gut "Pult antwortet"

# -------------------------------------------------------- Neue Befunde
# Nur NEUE zaehlen. Ein Rechner ohne Reparaturvorrat war vorher schon
# ohne Reparaturvorrat -- das ist kein Grund, ein Update zurueckzurollen.
#
# Umbenannte Befunde zaehlen als dieselben (0.5.2, 28.10.2026): der
# Systemcheck sagt "sprachmodell_dienst" statt "dienst_ollama". Die
# Grundlinie schreibt beim Sprung auf 0.5.2 noch die ALTE Fassung --
# ohne diese Abbildung haette ein Rechner, auf dem Ollama schon vorher
# hing, das Update zurueckgerollt.
if [ -s "$MERKDATEI" ]; then
  NEU="$(befunde_jetzt | sort | comm -13 <(sed \
           -e 's/^dienst_ollama_tot$/sprachmodell_dienst_tot/' \
           -e 's/^dienst_ollama$/sprachmodell_dienst/' "$MERKDATEI" | sort) \
         - 2>/dev/null)"
else
  NEU="$(befunde_jetzt | sort)"
fi
if [ -n "$NEU" ]; then
  fehl "Neue Fehler seit dem Update:"
  printf '%s\n' "$NEU" | sed 's/^/           /'
  exit 1
fi
gut "keine neuen Fehler"
exit 0
