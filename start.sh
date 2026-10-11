#!/usr/bin/env bash
# Devarenu starten.
#
# Startet den Server in diesem Fenster und zeigt die Adressen, die man am
# Sonntag braucht. Strg+C beendet ihn.
#
#   bash start.sh              Mikrofon, Geraet aus zustand.json
#   bash start.sh --mikro 1    Aufnahmegeraet erzwingen, zur Fehlersuche
#   bash start.sh --datei predigt.mp3   Dauerlauf mit einer Aufnahme
#
# Ohne Argument wird nichts vorgegeben: server.py nimmt dann die Nummer
# aus zustand.json, und steht dort keine, das Vorgabegeraet des Systems.
# Ausgewaehlt wird das Geraet am Pult unter Einrichtung.
#
# Den Netzbetrieb (--netz, sender.py auf einem zweiten Rechner) gab es
# bis 0.2.12. Er stammte aus der Zeit mit dem Gemeindelaptop; der ist
# weg, der Ton kommt per Klinke direkt in den Rechner. Er legte
# ausserdem keine Tonquelle an, sodass die Auswahl am Pult leer blieb.
#
# Alles bleibt im eigenen Netz. Es gibt keine Verbindung nach aussen: kein
# Tunnel, kein Anbieter, keine Verarbeitung ausserhalb der Gemeinde. Fuer
# den Betrieb ist das nicht nur sicherer, sondern auch schneller, weil der
# Ton nicht durchs Internet und zurueck laeuft.
#
# UND DER DIENST (0.5.1)
#
# Dieses Skript liegt hinter den Schreibtischsymbolen. Bis 0.5.0
# beendete es per "fuser -k" alles, was Port 8000 hielt -- also auch den
# Dienst. systemd startete ihn zehn Sekunden spaeter neu, er fand den
# Port belegt, starb, und so fort, jedes Mal mit Whisper im
# Grafikspeicher. In Rostock klickt der Helfer nach jedem Einschalten
# auf das Symbol. Jetzt wird zuerst nachgesehen:
#
#   1. Kein Dienst, oder er laeuft nicht      -> starten wie bisher
#   2. Dienst laedt noch                      -> warten, dann 3 oder 4
#   3. Dienst laeuft und hat Ton              -> nichts starten, Adressen
#   4. Dienst laeuft ohne Ton, oder es ist    -> Dienst fuer diese Sitzung
#      nicht festzustellen                       anhalten (sudo), dann
#                                                starten wie bisher
#   5. Uebrig gebliebene Server aus einer frueheren Sitzung werden
#      beendet -- der Dienst nie.
#
# "Hat Ton" heisst: der Server meldet in /api/zustand einen Tonblock,
# der hoechstens TON_FRIST Sekunden alt ist (audio_quelle). Der Block
# kommt auch bei Stille, solange das Aufnahmegeraet offen ist und
# liefert -- Stille im Saal ist also kein "ohne Ton".
#
# Jeder Lauf schreibt eine Zeile nach start-protokoll.txt. Das Pult
# zeigt die letzten zehn unter Einrichtung -> Autostart.

set -u
ORDNER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ORDNER"
PY=.venv/bin/python
PORT=8000
QUELLE=()
NAME=devarenu
PROTOKOLL="$ORDNER/start-protokoll.txt"

# Naehte fuer den Pruefstand (pruefstand/startskript_test.sh). Im
# Betrieb gelten die Vorgaben.
SYSTEMCTL="${DEVARENU_SYSTEMCTL:-systemctl}"
# So lange wird auf einen Dienst gewartet, der noch laedt. Nach dem
# Einschalten braucht er fuer Whisper und Ollama gut eine Minute, auf
# einem kalten Rechner auch zwei.
LADE_FRIST="${DEVARENU_LADE_FRIST:-180}"
# So lange darf der Ton nach dem ersten Antworten noch ausbleiben: die
# Tonquelle geht kurz nach dem Port auf.
TON_WARTEN="${DEVARENU_TON_WARTEN:-15}"
# Ein Tonblock, der aelter ist, zaehlt nicht. Der Server selbst haelt
# einen Strom nach rund neun Sekunden ohne Block fuer tot.
TON_FRIST=10
# So lange darf das Anhalten dauern, bis Port und Grafikspeicher frei
# sind. systemd selbst wartet bis zu 90 Sekunden.
FREI_FRIST="${DEVARENU_FREI_FRIST:-100}"

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
             tonhelfer.py client.html; do
  [ -f "$datei" ] || FEHLEND="$FEHLEND $datei"
done

# Die aktive Glossardatei -- aus config.py gelesen, NICHT als fester
# Name hier. Welche Fassung gilt, aendert sich: v0.4 heute, v0.8
# morgen. Ein fester Name hier waere beim naechsten Wechsel falsch,
# ohne dass es jemand merkt -- und ein fehlendes Glossar faellt dann
# erst mitten im Gottesdienst auf, an einer Uebersetzung ohne
# Terminologie.
#
# Schlaegt das Auslesen fehl, wird NICHT geraten: dann ist config.py
# ohnehin kaputt, und das meldet der Server selbst deutlicher.
GLOSSAR="$("$PY" -c "import config,os; print(os.path.basename(config.GLOSSAR_CSV))" 2>/dev/null || true)"
if [ -n "$GLOSSAR" ] && [ ! -f "$GLOSSAR" ]; then
  FEHLEND="$FEHLEND $GLOSSAR"
fi
# Das Logo ist kein Grund abzubrechen, sein Fehlen faellt aber sofort auf.
[ -f logo.png ] || echo "Hinweis: logo.png fehlt, die Seiten laufen ohne Bildmarke."

if [ -n "$FEHLEND" ]; then
  echo
  echo "Diese Dateien fehlen im Ordner:$FEHLEND"
  echo "Ohne sie startet der Server nicht. Alle gehoeren nebeneinander in"
  echo "  $ORDNER"
  exit 1
fi

# ---------------------------------------------------------- Werkzeuge
D_LADE=keins D_AKTIV="" D_UNTER="" D_PID=0

# Was systemd ueber den Dienst sagt. Ohne systemctl gibt es keinen.
dienst_lesen() {
  D_LADE=keins D_AKTIV="" D_UNTER="" D_PID=0
  command -v "${SYSTEMCTL%% *}" >/dev/null 2>&1 || return 0
  local aus
  aus="$(timeout 5 $SYSTEMCTL show "$NAME" -p LoadState -p ActiveState \
           -p SubState -p MainPID 2>/dev/null)" || true
  D_LADE="$(printf '%s\n' "$aus" | sed -n 's/^LoadState=//p')"
  D_AKTIV="$(printf '%s\n' "$aus" | sed -n 's/^ActiveState=//p')"
  D_UNTER="$(printf '%s\n' "$aus" | sed -n 's/^SubState=//p')"
  D_PID="$(printf '%s\n' "$aus" | sed -n 's/^MainPID=//p')"
  [ -n "$D_LADE" ] || D_LADE=keins
  [ -n "$D_PID" ] || D_PID=0
}

dienst_beschreibung() {
  if [ "$D_LADE" != loaded ]; then echo "keiner"
  else echo "${D_AKTIV:-?}/${D_UNTER:-?}"; fi
}

dienst_da() {  # laeuft oder laedt
  [ "$D_LADE" = loaded ] || return 1
  case "$D_AKTIV" in active|activating|reloading) return 0 ;; esac
  return 1
}

protokoll() {  # Entscheidung
  printf '%s | Dienst %s | %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" \
    "$(dienst_beschreibung)" "$1" >> "$PROTOKOLL" 2>/dev/null || true
  # Nicht endlos wachsen lassen.
  if [ "$(wc -l < "$PROTOKOLL" 2>/dev/null || echo 0)" -gt 200 ]; then
    tail -100 "$PROTOKOLL" > "$PROTOKOLL.neu" 2>/dev/null \
      && mv "$PROTOKOLL.neu" "$PROTOKOLL"
  fi
}

antwortet() {
  "$PY" -c "
import socket,sys
s=socket.socket(); s.settimeout(0.4)
sys.exit(0 if s.connect_ex(('127.0.0.1',$PORT))==0 else 1)" 2>/dev/null
}

# Hat der laufende Server Ton? Gibt "ja", "nein" oder "unbekannt" aus,
# dazu in der zweiten Zeile die Adresse, die er kennt.
ton_fragen() {
  "$PY" - "$PORT" "$TON_FRIST" <<'PYCODE' 2>/dev/null || printf 'unbekannt\n\n'
import json, sys, urllib.request
port, frist = sys.argv[1], float(sys.argv[2])
try:
    with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/zustand", timeout=5) as a:
        d = json.load(a)
except Exception:
    print("unbekannt"); print(""); sys.exit(0)
alter = d.get("audio_quelle")
print("ja" if isinstance(alter, (int, float)) and alter <= frist else "nein")
print(d.get("adresse") or "")
PYCODE
}

# Gehoert dieser Prozess zum Dienst? Hauptprozess oder seine cgroup.
ist_dienst() {
  [ "$1" = "$D_PID" ] && [ "$D_PID" != 0 ] && return 0
  grep -q "/$NAME.service" "/proc/$1/cgroup" 2>/dev/null
}

# Wer haelt den Port? Nur Prozesse dieses Benutzers sind zu sehen.
port_halter() {
  command -v fuser >/dev/null 2>&1 || return 0
  fuser -n tcp "$PORT" 2>/dev/null | tr -s ' ' '\n' | grep -E '^[0-9]+$' || true
}

# Zweig 5: uebrig gebliebene Server aus einer frueheren Sitzung beenden.
# Den Dienst NIE: dessen Prozesse werden uebersprungen.
reste_beenden() {
  local pid reste=""
  for pid in $(port_halter); do
    ist_dienst "$pid" && continue
    reste="$reste $pid"
  done
  [ -n "$reste" ] || return 0
  echo "Ein altes Devarenu-Fenster lief noch. Es wird beendet ..."
  # shellcheck disable=SC2086
  kill $reste 2>/dev/null
  for _ in 1 2 3 4 5; do
    sleep 1
    local noch=""
    for pid in $reste; do kill -0 "$pid" 2>/dev/null && noch="$noch $pid"; done
    [ -n "$noch" ] || return 0
  done
  # shellcheck disable=SC2086
  kill -9 $noch 2>/dev/null
  sleep 1
}

# Sind Port und Grafikspeicher frei, nachdem der Dienst angehalten ist?
frei() {  # alte Haupt-PID
  antwortet && return 1
  [ "$1" != 0 ] && kill -0 "$1" 2>/dev/null && return 1
  if [ "$1" != 0 ] && command -v nvidia-smi >/dev/null 2>&1; then
    timeout 5 nvidia-smi --query-compute-apps=pid --format=csv,noheader \
      2>/dev/null | tr -d ' ' | grep -qx "$1" && return 1
  fi
  return 0
}

# ------------------------------------------------------------ Entscheiden
dienst_lesen
reste_beenden

if dienst_da && ! antwortet; then
  # Zweig 2. Nach dem Einschalten klickt der Helfer oft, bevor der
  # Dienst fertig geladen hat. Dann nicht dazwischenfahren.
  echo
  echo "Devarenu startet gerade von selbst. Bitte warten,"
  echo "das kann bis zu $(( LADE_FRIST / 60 )) Minuten dauern ..."
  gewartet=0
  while [ "$gewartet" -lt "$LADE_FRIST" ]; do
    sleep 2; gewartet=$(( gewartet + 2 ))
    dienst_lesen
    dienst_da || break
    antwortet && break
    [ $(( gewartet % 20 )) = 0 ] && echo "  ... noch $(( LADE_FRIST - gewartet )) Sekunden"
  done
  dienst_lesen
fi

ENTSCHEIDUNG=""
if dienst_da; then
  TON=unbekannt; ADRESSE=""
  if antwortet; then
    gewartet=0
    while :; do
      ANTWORT="$(ton_fragen)"
      TON="$(printf '%s\n' "$ANTWORT" | sed -n 1p)"
      ADRESSE="$(printf '%s\n' "$ANTWORT" | sed -n 2p)"
      [ "$TON" = ja ] && break
      [ "$gewartet" -ge "$TON_WARTEN" ] && break
      sleep 3; gewartet=$(( gewartet + 3 ))
    done
  fi

  if [ "$TON" = ja ]; then
    # Zweig 3.
    protokoll "laeuft mit Ton -- nichts gestartet"
    echo
    echo "Devarenu läuft schon, mit Ton. Es muss nichts gestartet werden."
    echo
    echo "  Für die Zuhörer:  http://${ADRESSE:-<Adresse des Rechners>}:$PORT/"
    echo "  Pult:             http://${ADRESSE:-<Adresse des Rechners>}:$PORT/pult"
    echo "  Pult hier am Rechner:  http://127.0.0.1:$PORT/pult"
    echo
    echo "Dieses Fenster kann geschlossen werden. Devarenu läuft weiter."
    exit 0
  fi

  # Zweig 4.
  echo
  if [ "$TON" = nein ]; then
    echo "Devarenu läuft schon, bekommt aber keinen Ton vom Mischpult."
  else
    echo "Devarenu läuft schon, antwortet aber nicht richtig."
  fi
  echo "Es wird jetzt angehalten und hier in diesem Fenster neu gestartet."
  echo "Gleich wird nach dem Passwort dieses Rechners gefragt."
  echo
  ALT_PID="$D_PID"
  if ! sudo $SYSTEMCTL stop "$NAME"; then
    protokoll "ohne Ton ($TON) -- Anhalten gescheitert, nichts gestartet"
    echo
    echo "Das Anhalten hat nicht geklappt (oder das Passwort wurde nicht"
    echo "eingegeben). Es wird deshalb NICHTS gestartet -- zwei Devarenu"
    echo "nebeneinander gehen nicht."
    echo "Bitte den Rechner einmal neu starten. Hilft das nicht: den"
    echo "Betreuer anrufen und sagen, was hier steht."
    exit 1
  fi
  gewartet=0
  until frei "$ALT_PID"; do
    if [ "$gewartet" -ge "$FREI_FRIST" ]; then
      protokoll "ohne Ton ($TON) -- angehalten, aber nicht frei geworden, nichts gestartet"
      echo
      echo "Devarenu wurde angehalten, gibt den Platz aber nicht frei."
      echo "Es wird deshalb NICHTS gestartet. Bitte den Rechner neu starten."
      exit 1
    fi
    sleep 2; gewartet=$(( gewartet + 2 ))
  done
  dienst_lesen
  ENTSCHEIDUNG="ohne Ton ($TON) -- Dienst angehalten, hier gestartet"
  echo "Angehalten. Devarenu startet jetzt hier."
else
  # Zweig 1.
  ENTSCHEIDUNG="kein laufender Dienst -- hier gestartet"
fi

# Haelt den Port noch jemand, der nicht der Dienst ist, ist es ein Rest
# (Zweig 5). Fuer den Dienst kommt hier niemand mehr an.
reste_beenden
protokoll "$ENTSCHEIDUNG"

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
# -u, weil die Ausgabe hier nicht ins Terminal geht, sondern in eine
# Pipe: Python puffert dann blockweise, und beim Beenden ist der Puffer
# verloren. Genau die Meldungen, die zaehlen -- kein Ton, keine
# Erkennung auf der Grafikkarte -- kamen so nie an. Fuer den spaeteren
# Systemdienst gilt dasselbe, dort ist das Journal die Pipe.
$PY -u server.py ${QUELLE[@]+"${QUELLE[@]}"} --port "$PORT" &
SERVER_PID=$!

for _ in $(seq 1 90); do
  antwortet && break
  kill -0 "$SERVER_PID" 2>/dev/null || { echo "Server abgebrochen."; exit 1; }
  sleep 1
done

# Der Server gibt die Adressen selbst aus, und zwar mit der IP, die er
# tatsaechlich ermittelt hat. Hier nochmal zu raten fuehrte zu einem zweiten
# Block, in dem die IP fehlte, weil hostname -I nicht ueberall etwas liefert.

wait "$SERVER_PID"
