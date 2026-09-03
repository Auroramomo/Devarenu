#!/usr/bin/env bash
# Devarenu starten.
#
# Startet Server und Tunnel zusammen und zeigt am Ende die drei Adressen,
# die man am Sonntag braucht. Strg+C beendet beides.
#
#   ./start.sh              Mikrofon, Geraet aus zustand.json
#   ./start.sh --mikro 1    Aufnahmegeraet erzwingen, zur Fehlersuche
#   ./start.sh --datei predigt.mp3   Dauerlauf mit einer Aufnahme
#   ./start.sh --netz       Ton ueber das Netz von einem zweiten Rechner
#
# Ohne Argument wird nichts vorgegeben: server.py nimmt dann die Nummer
# aus zustand.json, und steht dort keine, das Vorgabegeraet des Systems.
# Ausgewaehlt wird das Geraet am Pult unter Einrichtung.
#
# Frueher stand hier --netz als Voreinstellung, aus der Zeit mit dem
# Gemeindelaptop. Der ist weg, der Ton kommt per Klinke direkt in den
# Rechner -- und im Netzbetrieb legt server.py keine Tonquelle an, sodass
# die Auswahl am Pult leer blieb.
#
# Alles bleibt im eigenen Netz. Es gibt keine Verbindung nach aussen: kein
# Tunnel, kein Anbieter, keine Verarbeitung ausserhalb der Gemeinde. Fuer
# den Betrieb ist das nicht nur sicherer, sondern auch schneller, weil der
# Ton nicht durchs Internet und zurueck laeuft.

set -u
ORDNER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ORDNER"
PY=.venv/bin/python
PORT=8000
QUELLE=()

while [ $# -gt 0 ]; do
  case "$1" in
    --mikro)  QUELLE=(--geraet "$2"); shift 2 ;;
    --datei)  QUELLE=(--datei "$2"); shift 2 ;;
    --port)   PORT="$2"; shift 2 ;;
    *)        QUELLE+=("$1"); shift ;;
  esac
done

[ -x "$PY" ] || { echo "Keine venv. Erst einrichten: bash INSTALLIEREN.sh"; exit 1; }

# Fehlende Dateien vorher melden. Sonst bricht der Server mitten im Start
# mit einem Traceback ab, aus dem nicht hervorgeht, dass schlicht eine
# Datei im Ordner fehlt.
FEHLEND=""
for datei in server.py config.py zustand.py grafikkarte.py glossar.py \
             bibelstellen.py \
             skript_lesen.py namen_aus_bibel.py laengenfaktor.py \
             client.html; do
  [ -f "$datei" ] || FEHLEND="$FEHLEND $datei"
done
# Das Logo ist kein Grund abzubrechen, sein Fehlen faellt aber sofort auf.
[ -f logo.png ] || echo "Hinweis: logo.png fehlt, die Seiten laufen ohne Bildmarke."

if [ -n "$FEHLEND" ]; then
  echo
  echo "Diese Dateien fehlen im Ordner:$FEHLEND"
  echo "Ohne sie startet der Server nicht. Alle gehoeren nebeneinander in"
  echo "  $ORDNER"
  exit 1
fi

# Alten Server auf dem Port beenden, sonst scheitert der Start mit einer
# wenig aussagekraeftigen Meldung.
if command -v fuser >/dev/null && fuser "$PORT/tcp" >/dev/null 2>&1; then
  echo "Port $PORT belegt, beende den alten Server ..."
  fuser -k "$PORT/tcp" >/dev/null 2>&1
  sleep 1
fi

aufraeumen() {
  echo
  [ -n "${SERVER_PID:-}" ] && kill "$SERVER_PID" 2>/dev/null
  wait 2>/dev/null
  echo "Beendet."
}
trap aufraeumen INT TERM EXIT

echo "Server startet ..."
# Die Ersatzform, weil ein leeres Array unter set -u in bash vor 4.4
# als ungesetzte Variable gilt. Ohne Argument ist der Normalfall.
$PY server.py ${QUELLE[@]+"${QUELLE[@]}"} --port "$PORT" &
SERVER_PID=$!

for _ in $(seq 1 90); do
  if $PY -c "
import socket,sys
s=socket.socket(); s.settimeout(0.4)
sys.exit(0 if s.connect_ex(('127.0.0.1',$PORT))==0 else 1)" 2>/dev/null; then
    break
  fi
  kill -0 "$SERVER_PID" 2>/dev/null || { echo "Server abgebrochen."; exit 1; }
  sleep 1
done

# Der Server gibt die Adressen selbst aus, und zwar mit der IP, die er
# tatsaechlich ermittelt hat. Hier nochmal zu raten fuehrte zu einem zweiten
# Block, in dem die IP fehlte, weil hostname -I nicht ueberall etwas liefert.

wait "$SERVER_PID"
