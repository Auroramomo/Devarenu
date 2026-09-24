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
  mkdir -p "$(dirname "$MERKDATEI")"
  befunde_jetzt | sort > "$MERKDATEI"
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

# -------------------------------------------------------- Neue Befunde
# Nur NEUE zaehlen. Ein Rechner ohne Reparaturvorrat war vorher schon
# ohne Reparaturvorrat -- das ist kein Grund, ein Update zurueckzurollen.
if [ -s "$MERKDATEI" ]; then
  NEU="$(befunde_jetzt | sort | comm -13 "$MERKDATEI" - 2>/dev/null)"
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
