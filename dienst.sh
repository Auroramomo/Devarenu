#!/usr/bin/env bash
# Devarenu als Systemdienst einrichten.
#
#   ./dienst.sh              installieren und starten
#   ./dienst.sh --entfernen  wieder abschalten
#   ./dienst.sh --status     nachsehen, was er macht
#
# Gedacht fuer den Rechner in der Gemeinde: headless, niemand meldet sich
# an, nach dem Einschalten muss der Server von allein hochkommen. Wer
# entwickelt, braucht das nicht und startet weiter mit ./start.sh.

set -u
ORDNER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ORDNER"

NAME=devarenu
ZIEL=/etc/systemd/system/$NAME.service
PORT="${DEVARENU_PORT:-8000}"

blau() { printf '\n\033[1;34m== %s\033[0m\n' "$1"; }
gut()  { printf '   \033[32mok\033[0m   %s\n' "$1"; }
warn() { printf '   \033[33m!\033[0m    %s\n' "$1"; }
fehl() { printf '   \033[31mFEHLT\033[0m %s\n' "$1"; }

# Wer den Dienst spaeter besitzt. Bei einem Aufruf mit sudo ist das nicht
# root, sondern der Mensch davor: ihm gehoert der Projektordner, und sein
# Zugriff aufs Aufnahmegeraet zaehlt.
BENUTZER="${SUDO_USER:-$(id -un)}"

if [ ! -d /run/systemd/system ]; then
  fehl "Dieses System benutzt kein systemd. Dann gibt es hier nichts zu tun."
  exit 1
fi

# ---------------------------------------------------------------- entfernen
if [ "${1:-}" = "--entfernen" ]; then
  blau "Dienst entfernen"
  sudo systemctl disable --now $NAME 2>/dev/null
  sudo rm -f "$ZIEL"
  sudo systemctl daemon-reload
  gut "entfernt. Starten wieder von Hand mit ./start.sh"
  exit 0
fi

if [ "${1:-}" = "--status" ]; then
  systemctl status $NAME --no-pager
  exit $?
fi

# ---------------------------------------------------------------- pruefen
blau "Voraussetzungen"

[ -x "$ORDNER/.venv/bin/python" ] || {
  fehl "Keine venv in $ORDNER. Erst einrichten: bash INSTALLIEREN.sh"; exit 1; }
gut "venv vorhanden"

[ -f "$ORDNER/devarenu.service.vorlage" ] || {
  fehl "devarenu.service.vorlage fehlt"; exit 1; }

# Ohne angemeldete Sitzung gibt es keine uaccess-ACL auf /dev/snd. Die
# Unit setzt SupplementaryGroups=audio, damit es trotzdem geht; hier steht
# es nur zur Kenntnis, weil es beim Suchen hilft.
if id -nG "$BENUTZER" | tr ' ' '\n' | grep -qx audio; then
  gut "$BENUTZER ist in der Gruppe audio"
else
  warn "$BENUTZER ist nicht in der Gruppe audio. Die Unit gleicht das mit"
  warn "SupplementaryGroups=audio aus. Dauerhaft sauberer waere:"
  warn "  sudo usermod -aG audio $BENUTZER"
fi

if systemctl list-unit-files 2>/dev/null | grep -q '^ollama\.service'; then
  gut "ollama.service ist bekannt"
else
  warn "Kein ollama.service gefunden. Ohne Ollama gibt es keine"
  warn "Uebersetzung, nur Untertitel in der Ausgangssprache."
fi

command -v nvidia-smi >/dev/null && gut "NVIDIA-Treiber vorhanden" \
  || warn "Kein NVIDIA-Treiber. Alles laeuft auf der CPU und ist fuer den
        Livebetrieb zu langsam."

# ---------------------------------------------------------------- schreiben
blau "Unit schreiben"
UNIT="$(sed -e "s|@BENUTZER@|$BENUTZER|g" \
            -e "s|@ORDNER@|$ORDNER|g" \
            -e "s|@PORT@|$PORT|g" devarenu.service.vorlage)"
printf '%s\n' "$UNIT" | sudo tee "$ZIEL" >/dev/null || {
  fehl "Konnte $ZIEL nicht schreiben"; exit 1; }
gut "$ZIEL"
gut "Benutzer $BENUTZER, Ordner $ORDNER, Port $PORT"

sudo systemctl daemon-reload
sudo systemctl enable --now $NAME || { fehl "Start fehlgeschlagen"; exit 1; }

# ---------------------------------------------------------------- nachsehen
blau "Laeuft er?"
# Der Server laedt beim Start das Whisper-Modell; bis er antwortet,
# vergehen ein paar Sekunden.
for _ in $(seq 1 60); do
  ANTWORT="$(curl -s -m 2 "http://127.0.0.1:$PORT/api/zustand" 2>/dev/null)"
  [ -n "$ANTWORT" ] && break
  systemctl is-active --quiet $NAME || { fehl "Dienst ist abgebrochen."
    echo; journalctl -u $NAME -n 20 --no-pager; exit 1; }
  sleep 2
done

if [ -z "${ANTWORT:-}" ]; then
  warn "Der Dienst laeuft, antwortet aber noch nicht auf Port $PORT."
  warn "Nachsehen mit: journalctl -u $NAME -f"
  exit 1
fi

RECHENWERK="$(printf '%s' "$ANTWORT" | "$ORDNER/.venv/bin/python" -c \
  'import json,sys; print(json.load(sys.stdin).get("rechenwerk",""))' 2>/dev/null)"
gut "antwortet auf Port $PORT"
case "$RECHENWERK" in
  cuda*) gut "rechnet auf der Grafikkarte: $RECHENWERK" ;;
  "")    warn "Konnte nicht feststellen, worauf gerechnet wird" ;;
  *)     warn "rechnet auf: $RECHENWERK"
         warn "Fuer den Livebetrieb ist die CPU zu langsam. Nachsehen mit:"
         warn "  .venv/bin/python selbsttest.py" ;;
esac

IP="$("$ORDNER/.venv/bin/python" -c \
  'import sys; sys.path.insert(0,"'"$ORDNER"'"); import server; print(server.lokale_ip())' \
  2>/dev/null || echo 127.0.0.1)"

blau "Fertig"
cat <<ENDE
   Der Dienst startet ab jetzt mit dem Rechner und laeuft nach einem
   Absturz von allein wieder an.

     Zuhoerer   http://$IP:$PORT/
     Pult       http://$IP:$PORT/pult

   Nachsehen     systemctl status $NAME
   Mitlesen      journalctl -u $NAME -f
   Neu starten   sudo systemctl restart $NAME
   Abschalten    ./dienst.sh --entfernen

   Die Tonquelle steht nicht in der Unit, sondern in zustand.json und
   wird am Pult unter Einrichtung gewaehlt.
ENDE
