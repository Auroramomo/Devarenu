#!/usr/bin/env bash
# Devarenu als Systemdienst einrichten.
#
#   bash dienst.sh              installieren und starten
#   bash dienst.sh --entfernen  wieder abschalten
#   bash dienst.sh --status     nachsehen, was er macht
#   bash dienst.sh --stick      nur das Update per USB-Stick einrichten
#
# Gedacht fuer den Rechner in der Gemeinde: headless, niemand meldet sich
# an, nach dem Einschalten muss der Server von allein hochkommen. Wer
# entwickelt, braucht das nicht und startet weiter mit bash start.sh.

set -u
ORDNER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ORDNER"

NAME=devarenu
ZIEL=/etc/systemd/system/$NAME.service
PORT="${DEVARENU_PORT:-8000}"

# Das Update per USB-Stick. Drei Units und eine udev-Regel: die Regel
# merkt, dass ein Stick steckt, die Instanz-Unit wertet ihn aus, der
# Timer spielt spaeter ein. Warum getrennt, steht in stick_update.sh.
STICK_UNIT=/etc/systemd/system/$NAME-stick@.service
UPDATE_UNIT=/etc/systemd/system/$NAME-update.service
UPDATE_TIMER=/etc/systemd/system/$NAME-update.timer
UDEV_REGEL=/etc/udev/rules.d/99-$NAME-stick.rules

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

# ------------------------------------------------------------------ Stick
# Richtet ein, was einen eingesteckten USB-Stick zu einem Update macht.
# Eigene Funktion, weil zwei Wege hierher fuehren: die gewoehnliche
# Einrichtung weiter unten und bootstrap.sh vom Stick, auf Rechnern, die
# das Verfahren noch nicht kennen.
stick_einrichten() {
  blau "Update per USB-Stick"

  local fehlt=""
  for datei in stick_update.sh stick.udev.vorlage \
               devarenu-stick@.service.vorlage \
               devarenu-update.service.vorlage devarenu-update.timer.vorlage; do
    [ -f "$ORDNER/$datei" ] || fehlt="$fehlt $datei"
  done
  if [ -n "$fehlt" ]; then
    warn "Es fehlt:$fehlt"
    warn "Das Update per Stick wird uebersprungen. Der Dienst laeuft davon"
    warn "unberuehrt weiter."
    return 1
  fi

  # KEIN chmod mehr: stick_update.sh ist versioniert, und ein
  # geaendertes Ausfuehrungsrecht laesst git den Ordner als veraendert
  # sehen -- woran dann das naechste Update abbricht. Die Unit ruft das
  # Skript ueber /bin/bash auf, das Recht wird also nicht gebraucht.

  # Ohne Schluesselliste wird nie ein Stick angenommen. Einrichten laesst
  # sich das Verfahren trotzdem -- besser eine Unit, die wartet, als eine
  # Fehlermeldung mitten in der Ersteinrichtung.
  if [ ! -s "$ORDNER/schluessel.erlaubt" ] \
     || ! grep -qE '^[^#[:space:]]+[[:space:]]+(ssh|sk-)' "$ORDNER/schluessel.erlaubt"; then
    warn "schluessel.erlaubt enthaelt keinen Schluessel. Sticks werden"
    warn "abgelehnt, bis einer eingetragen ist."
  fi

  sed "s|@ORDNER@|$ORDNER|g" "$ORDNER/devarenu-stick@.service.vorlage" \
    | sudo tee "$STICK_UNIT" >/dev/null || { fehl "$STICK_UNIT"; return 1; }
  sed "s|@ORDNER@|$ORDNER|g" "$ORDNER/devarenu-update.service.vorlage" \
    | sudo tee "$UPDATE_UNIT" >/dev/null || { fehl "$UPDATE_UNIT"; return 1; }
  sudo cp "$ORDNER/devarenu-update.timer.vorlage" "$UPDATE_TIMER" \
    || { fehl "$UPDATE_TIMER"; return 1; }
  gut "Units geschrieben"

  # Die Kommentarzeilen der Vorlage gehoeren mit in die Regel: wer in
  # /etc/udev/rules.d stoebert, soll dort lesen koennen, warum sie da ist.
  sudo cp "$ORDNER/stick.udev.vorlage" "$UDEV_REGEL" \
    || { fehl "$UDEV_REGEL"; return 1; }
  if sudo udevadm control --reload 2>/dev/null; then
    gut "udev-Regel $UDEV_REGEL"
  else
    # Kein Abbruchgrund: udev liest seine Regeln beim naechsten Start
    # ohnehin neu ein. Nur wirkt sie bis dahin nicht.
    warn "udev-Regel liegt, aber udevadm liess sich nicht ansprechen."
    warn "Sie greift spaetestens nach dem naechsten Neustart."
  fi

  sudo systemctl daemon-reload
  if sudo systemctl enable --now "$NAME-update.timer" 2>/dev/null; then
    gut "Timer laeuft, sieht jede Minute nach"
  else
    fehl "Timer liess sich nicht starten"
    return 1
  fi

  gut "Ein eingesteckter Stick wird ab jetzt von allein geprueft"
  return 0
}

if [ "${1:-}" = "--stick" ]; then
  stick_einrichten
  exit $?
fi

# ---------------------------------------------------------------- entfernen
if [ "${1:-}" = "--entfernen" ]; then
  blau "Dienst entfernen"
  sudo systemctl disable --now $NAME 2>/dev/null
  sudo rm -f "$ZIEL"

  # Das Update per Stick geht mit. Bliebe der Timer stehen, wuerde er
  # weiter jede Minute einen Dienst neu starten wollen, den es nicht mehr
  # gibt.
  sudo systemctl disable --now "$NAME-update.timer" 2>/dev/null
  sudo rm -f "$STICK_UNIT" "$UPDATE_UNIT" "$UPDATE_TIMER" "$UDEV_REGEL"
  sudo udevadm control --reload 2>/dev/null

  sudo systemctl daemon-reload
  gut "entfernt, samt Update per Stick"
  gut "Starten wieder von Hand mit bash start.sh"
  # Was auf der Platte liegt, bleibt liegen: ein vorgemerktes Update ist
  # Arbeit, die jemand hineingesteckt hat, und wegzuwerfen ist es hier
  # nicht.
  [ -s "$ORDNER/update/bereit" ] && \
    warn "In update/ liegt noch ein vorgemerktes Update. Es passiert nichts"
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

# Gleich mit: dann braucht ein neu aufgesetzter Rechner bootstrap.sh nie.
stick_einrichten || warn "Ohne Stick-Update. Nachholen mit: bash dienst.sh --stick"

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

feld() {
  printf '%s' "$ANTWORT" | "$ORDNER/.venv/bin/python" -c \
    "import json,sys; print(json.load(sys.stdin).get('$1',''))" 2>/dev/null
}
RECHENWERK="$(feld rechenwerk)"
gut "antwortet auf Port $PORT"
case "$RECHENWERK" in
  cuda*) gut "rechnet auf der Grafikkarte: $RECHENWERK" ;;
  "")    warn "Konnte nicht feststellen, worauf gerechnet wird" ;;
  *)     warn "rechnet auf: $RECHENWERK"
         warn "Fuer den Livebetrieb ist die CPU zu langsam. Nachsehen mit:"
         warn "  .venv/bin/python selbsttest.py" ;;
esac

# Aus derselben Antwort wie oben. Frueher stand hier ein eigener
# Python-Aufruf, der server.py importierte, nur um die Adresse zu
# ermitteln -- das zieht Torch und faster-whisper hinterher und riet danach
# genauso einmal wie der Server selbst. Der laufende Dienst weiss es
# besser: er sucht weiter, bis eine Adresse da ist.
IP="$(feld adresse)"

blau "Fertig"
cat <<ENDE
   Der Dienst startet ab jetzt mit dem Rechner und laeuft nach einem
   Absturz von allein wieder an.
ENDE

if [ -n "$IP" ]; then
  cat <<ENDE

     Zuhoerer   http://$IP:$PORT/
     Pult       http://$IP:$PORT/pult
ENDE
else
  cat <<ENDE

     Noch keine Netzwerkadresse. Der Dienst laeuft und antwortet auf
     Port $PORT; sobald der Rechner im Netz ist, steht die Adresse im
     Journal und unter bash pruefen.sh.
ENDE
fi

cat <<ENDE

   Nachsehen     systemctl status $NAME
   Mitlesen      journalctl -u $NAME -f
   Neu starten   sudo systemctl restart $NAME
   Abschalten    bash dienst.sh --entfernen

   Die Tonquelle steht nicht in der Unit, sondern in zustand.json und
   wird am Pult unter Einrichtung gewaehlt.
ENDE
