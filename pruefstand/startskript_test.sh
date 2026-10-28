#!/usr/bin/env bash
# Das Schreibtischsymbol und der Dienst (B4, 0.5.1).
#
#   bash pruefstand/startskript_test.sh
#
# start.sh beendete bis 0.5.0 per "fuser -k" alles auf Port 8000, auch
# den Dienst -- und systemd startete ihn danach alle zehn Sekunden neu.
# Hier laufen alle fuenf Zweige gegen nachgebaute Teile:
#
#   systemctl  liest und schreibt eine Zustandsdatei (show, stop)
#   sudo       reicht durch -- oder bricht ab wie ein abgebrochenes Passwort
#   nvidia-smi nennt die Prozesse, die noch Grafikspeicher halten
#   Server     ein kleiner HTTP-Server mit /api/zustand, einmal als
#              "Dienst" vom Pruefstand gestartet, einmal als Sitzung von
#              start.sh selbst (ueber eine nachgebaute .venv/bin/python)
#
# Nichts davon fasst den Rechner an: kein echter Dienst, kein sudo, ein
# freier Port statt 8000. Gebraucht wird fuser (psmisc) -- ohne ihn
# entfallen die beiden Faelle mit Resten.

set -u
ECHT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASIS="$(mktemp -d)"
GRUEN="\033[32m"; ROT="\033[31m"; AUS="\033[0m"
FEHLER=0
PIDS=""

aufraeumen() {
  for p in $PIDS; do kill "$p" 2>/dev/null; done
  pkill -f "$BASIS/attrappe_server.py" 2>/dev/null
  rm -rf "$BASIS"
}
trap aufraeumen EXIT

pruefe() {  # was erwartet ist
  if [ "$2" = "$3" ]; then printf '   ok    %s\n' "$1"
  else printf "   ${ROT}FEHL${AUS}  %s: erwartet %s, ist %s\n" "$1" "$2" "$3"
       FEHLER=$((FEHLER+1)); fi
}
titel() { printf '\n\033[1m== %s\033[0m\n' "$1"; }

PORT="$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1])')"

# ------------------------------------------------------ Der Nachbau
ORDNER="$BASIS/devarenu"
mkdir -p "$ORDNER/.venv/bin" "$BASIS/bin"
# Gegenprobe mit einer anderen Fassung: DEVARENU_START_SH=<pfad>
cp "${DEVARENU_START_SH:-$ECHT/start.sh}" "$ORDNER/start.sh"
for f in server.py zustand.py grafikkarte.py glossar.py bibelstellen.py \
         skript_lesen.py namen_aus_bibel.py laengenfaktor.py tonhelfer.py \
         client.html logo.png glossar.csv; do : > "$ORDNER/$f"; done
# Seit 0.5.2 fragt start.sh auch nach den Seiten unter web/.
mkdir -p "$ORDNER/web"
for f in pult.html anmeldung.html qr.html; do : > "$ORDNER/web/$f"; done
echo 'GLOSSAR_CSV = "glossar.csv"' > "$ORDNER/config.py"

cat > "$BASIS/attrappe_server.py" <<'PY'
# Ein Devarenu-Server zum Schein: /api/zustand, sonst nichts.
import json, os, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
rolle = sys.argv[1]
port = int(sys.argv[sys.argv.index("--port") + 1])
ton = os.environ.get("ATTR_TON", "0.5")
marke = os.environ.get("ATTR_MARKE", "")
if marke:
    with open(marke, "a") as f:
        f.write(f"{rolle} {os.getpid()} {' '.join(sys.argv[2:])}\n")
time.sleep(float(os.environ.get("ATTR_VERZUG", "0")))
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        d = {"audio_quelle": None if ton == "none" else float(ton),
             "adresse": "10.0.0.1"}
        b = json.dumps(d).encode()
        self.send_response(200); self.end_headers(); self.wfile.write(b)
    def log_message(self, *a): pass
s = ThreadingHTTPServer(("0.0.0.0", port), H)
s.timeout = 0.2
ende = time.time() + float(os.environ.get("ATTR_LAUFZEIT", "600"))
while time.time() < ende:
    s.handle_request()
PY

# Die venv: "server.py" wird zur Attrappe, alles andere zu python3.
cat > "$ORDNER/.venv/bin/python" <<SH
#!/usr/bin/env bash
if [ "\${1:-}" = -u ] && [ "\${2:-}" = server.py ]; then
  shift 2
  ATTR_LAUFZEIT=2 ATTR_TON=0.5 exec python3 "$BASIS/attrappe_server.py" sitzung "\$@"
fi
exec python3 "\$@"
SH

cat > "$BASIS/bin/systemctl" <<SH
#!/usr/bin/env bash
echo "systemctl \$*" >> "$BASIS/systemctl.log"
z="$BASIS/dienst.zustand"
case "\$1" in
  show) cat "\$z" 2>/dev/null; exit 0 ;;
  stop)
    [ -f "$BASIS/stop_scheitert" ] && exit 1
    pid="\$(sed -n 's/^MainPID=//p' "\$z")"
    [ "\${pid:-0}" != 0 ] && kill "\$pid" 2>/dev/null
    printf 'LoadState=loaded\nActiveState=inactive\nSubState=dead\nMainPID=0\n' > "\$z"
    # Der Grafikspeicher wird erst etwas spaeter frei.
    ( sleep 2; : > "$BASIS/gpu.pids" ) &
    exit 0 ;;
esac
exit 0
SH

cat > "$BASIS/bin/sudo" <<SH
#!/usr/bin/env bash
echo "sudo \$*" >> "$BASIS/systemctl.log"
if [ -f "$BASIS/sudo_abbruch" ]; then
  echo "sudo: 1 falsche Kennworteingabe" >&2; exit 1
fi
exec "\$@"
SH

cat > "$BASIS/bin/nvidia-smi" <<SH
#!/usr/bin/env bash
if [ -s "$BASIS/gpu.pids" ]; then echo "nvidia-smi belegt" >> "$BASIS/systemctl.log"
else echo "nvidia-smi frei" >> "$BASIS/systemctl.log"; fi
cat "$BASIS/gpu.pids" 2>/dev/null; exit 0
SH
chmod +x "$ORDNER/.venv/bin/python" "$BASIS/bin/"*
export PATH="$BASIS/bin:$PATH"
export ATTR_MARKE="$BASIS/gestartet"

# ------------------------------------------------------ Hilfen
zustand() {  # Load Active Sub Pid
  printf 'LoadState=%s\nActiveState=%s\nSubState=%s\nMainPID=%s\n' \
    "$1" "$2" "$3" "$4" > "$BASIS/dienst.zustand"
}
dienst_starten() {  # ton verzug
  ATTR_TON="$1" ATTR_VERZUG="${2:-0}" \
    python3 "$BASIS/attrappe_server.py" dienst --port "$PORT" &
  DIENST=$!
  PIDS="$PIDS $DIENST"
  echo "$DIENST" > "$BASIS/gpu.pids"
  zustand loaded active running "$DIENST"
  # Bis er antwortet, ausser er soll noch laden.
  if [ "${2:-0}" = 0 ]; then
    for _ in $(seq 1 50); do
      python3 -c "import socket,sys; s=socket.socket(); sys.exit(s.connect_ex(('127.0.0.1',$PORT)))" && break
      sleep 0.1
    done
  fi
}
rest_starten() {
  ATTR_TON=0.5 ATTR_LAUFZEIT=600 \
    python3 "$BASIS/attrappe_server.py" rest --port "$PORT" &
  REST=$!
  PIDS="$PIDS $REST"
  for _ in $(seq 1 50); do
    python3 -c "import socket,sys; s=socket.socket(); sys.exit(s.connect_ex(('127.0.0.1',$PORT)))" && break
    sleep 0.1
  done
}
neu() {
  rm -f "$BASIS/gestartet" "$BASIS/systemctl.log" "$BASIS/sudo_abbruch" \
        "$BASIS/stop_scheitert" "$ORDNER/start-protokoll.txt"
  : > "$BASIS/gpu.pids"
  for p in $PIDS; do kill "$p" 2>/dev/null; done
  PIDS=""
  sleep 0.5
}
starten() {  # Argumente fuer start.sh
  AUSGABE="$(DEVARENU_LADE_FRIST="${LADE:-20}" DEVARENU_TON_WARTEN=3 \
             DEVARENU_FREI_FRIST=20 \
             timeout 90 bash "$ORDNER/start.sh" --port "$PORT" "$@" 2>&1)"
  RC=$?
}
sitzung_lief() { grep -q '^sitzung ' "$BASIS/gestartet" 2>/dev/null && echo ja || echo nein; }
lebt() { kill -0 "$1" 2>/dev/null && echo ja || echo nein; }
letzte() { tail -1 "$ORDNER/start-protokoll.txt" 2>/dev/null; }
enthaelt() { printf '%s' "$1" | grep -qF -- "$2" && echo ja || echo nein; }

HAT_FUSER=ja
command -v fuser >/dev/null || HAT_FUSER=nein

# ======================================================== Zweig 1
titel "1) Kein Dienst: starten wie bisher"
neu; zustand not-found inactive dead 0
starten
pruefe "ein Server startet in der Sitzung" ja "$(sitzung_lief)"
pruefe "kein sudo, kein Anhalten" nein \
  "$(grep -q 'stop' "$BASIS/systemctl.log" 2>/dev/null && echo ja || echo nein)"
pruefe "Protokoll: kein laufender Dienst" ja \
  "$(enthaelt "$(letzte)" "kein laufender Dienst -- hier gestartet")"
pruefe "Protokoll nennt den Dienstzustand" ja "$(enthaelt "$(letzte)" "Dienst keiner")"

neu; zustand loaded failed failed 0
starten
pruefe "Dienst gescheitert (failed): ebenso" ja "$(sitzung_lief)"
pruefe "und das Protokoll nennt ihn" ja "$(enthaelt "$(letzte)" "Dienst failed/failed")"

# ======================================================== Zweig 5
titel "5) Reste aus einer frueheren Sitzung -- der Dienst nie"
if [ "$HAT_FUSER" = ja ]; then
  neu; zustand loaded inactive dead 0
  rest_starten
  starten
  pruefe "der alte Sitzungsserver ist beendet" nein "$(lebt "$REST")"
  pruefe "und ein neuer laeuft" ja "$(sitzung_lief)"
  pruefe "das Fenster sagt es" ja "$(enthaelt "$AUSGABE" "altes Devarenu-Fenster")"
else
  echo "   --    fuser fehlt, Fall entfaellt"
fi

# ======================================================== Zweig 3
titel "3) Dienst laeuft mit Ton: nichts starten"
for symbol in "" "--mikro 1"; do
  neu; dienst_starten 0.5
  # shellcheck disable=SC2086
  starten $symbol
  wie="${symbol:-ohne --mikro}"
  pruefe "[$wie] es startet nichts" nein "$(sitzung_lief)"
  pruefe "[$wie] der Dienst lebt (fuser hat ihn nicht getroffen)" ja "$(lebt "$DIENST")"
  pruefe "[$wie] kein Anhalten" nein \
    "$(grep -q 'stop' "$BASIS/systemctl.log" 2>/dev/null && echo ja || echo nein)"
  pruefe "[$wie] das Fenster sagt: laeuft schon, mit Ton" ja \
    "$(enthaelt "$AUSGABE" "Devarenu läuft schon, mit Ton")"
  pruefe "[$wie] mit Zuhoereradresse" ja "$(enthaelt "$AUSGABE" "http://10.0.0.1:$PORT/")"
  pruefe "[$wie] und Pultadresse" ja "$(enthaelt "$AUSGABE" "http://10.0.0.1:$PORT/pult")"
  pruefe "[$wie] Rueckgabe 0" 0 "$RC"
  pruefe "[$wie] Protokoll: mit Ton, nichts gestartet" ja \
    "$(enthaelt "$(letzte)" "Dienst active/running | laeuft mit Ton -- nichts gestartet")"
done

# Stille im Raum: der Tonblock ist frisch, nur leise. Das ist Ton.
neu; dienst_starten 0.0
starten
pruefe "Stille (frischer, leiser Block) zaehlt als Ton" nein "$(sitzung_lief)"

# ======================================================== Zweig 2
titel "2) Dienst laedt noch: warten, dann entscheiden"
neu; dienst_starten 0.5 4
starten
pruefe "nach dem Warten: laeuft mit Ton, nichts gestartet" nein "$(sitzung_lief)"
pruefe "der Dienst lebt" ja "$(lebt "$DIENST")"
pruefe "das Fenster bat um Geduld" ja "$(enthaelt "$AUSGABE" "startet gerade von selbst")"

neu; zustand loaded activating auto-restart 0
( sleep 3; zustand loaded inactive dead 0 ) &
starten
pruefe "Dienst gibt waehrend des Wartens auf: Zweig 1" ja "$(sitzung_lief)"

neu; dienst_starten 0.5 600
LADE=6 starten
pruefe "Dienst antwortet nie: nach der Frist angehalten" ja \
  "$(grep -q 'sudo systemctl stop devarenu' "$BASIS/systemctl.log" && echo ja || echo nein)"
pruefe "und hier gestartet" ja "$(sitzung_lief)"
pruefe "Protokoll: Ton nicht festzustellen" ja "$(enthaelt "$(letzte)" "ohne Ton (unbekannt)")"

# ======================================================== Zweig 4
titel "4) Dienst laeuft ohne Ton: anhalten, dann hier starten"
for symbol in "" "--mikro 1"; do
  neu; dienst_starten none
  # shellcheck disable=SC2086
  starten $symbol
  wie="${symbol:-ohne --mikro}"
  pruefe "[$wie] mit sudo angehalten" ja \
    "$(grep -q 'sudo systemctl stop devarenu' "$BASIS/systemctl.log" && echo ja || echo nein)"
  pruefe "[$wie] der Dienst ist weg" nein "$(lebt "$DIENST")"
  pruefe "[$wie] hier gestartet" ja "$(sitzung_lief)"
  # Der nachgebaute Grafikspeicher wird erst zwei Sekunden nach dem
  # Anhalten frei. Gestartet werden darf erst danach.
  pruefe "[$wie] hat auf den Grafikspeicher gewartet" ja \
    "$(grep -q 'nvidia-smi belegt' "$BASIS/systemctl.log" \
       && grep 'nvidia-smi' "$BASIS/systemctl.log" | tail -1 | grep -q 'frei' \
       && echo ja || echo nein)"
  pruefe "[$wie] das Fenster sagt warum" ja "$(enthaelt "$AUSGABE" "bekommt aber keinen Ton")"
  pruefe "[$wie] Protokoll: angehalten, hier gestartet" ja \
    "$(enthaelt "$(letzte)" "ohne Ton (nein) -- Dienst angehalten, hier gestartet")"
done
pruefe "--mikro 1 kommt beim Server an" ja \
  "$(grep '^sitzung ' "$BASIS/gestartet" | grep -q -- '--geraet 1' && echo ja || echo nein)"

neu; dienst_starten 60
starten
pruefe "ein alter Tonblock (60 s) zaehlt nicht als Ton" ja "$(sitzung_lief)"

neu; dienst_starten none; : > "$BASIS/sudo_abbruch"
starten
pruefe "Passwort abgebrochen: nichts gestartet" nein "$(sitzung_lief)"
pruefe "der Dienst lebt weiter" ja "$(lebt "$DIENST")"
pruefe "Rueckgabe nicht 0" 1 "$RC"
pruefe "das Fenster sagt es" ja "$(enthaelt "$AUSGABE" "Es wird deshalb NICHTS gestartet")"
pruefe "Protokoll: Anhalten gescheitert" ja \
  "$(enthaelt "$(letzte)" "Anhalten gescheitert, nichts gestartet")"

neu; dienst_starten none; : > "$BASIS/stop_scheitert"
starten
pruefe "systemctl stop scheitert: nichts gestartet" nein "$(sitzung_lief)"

printf '\n'
if [ "$FEHLER" -gt 0 ]; then
  printf "${ROT}%s Fehler.${AUS}\n" "$FEHLER"; exit 1
fi
printf "${GRUEN}Alle Faelle wie erwartet.${AUS}\n"
