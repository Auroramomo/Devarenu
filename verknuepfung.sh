#!/usr/bin/env bash
# Legt eine Verknuepfung auf dem Schreibtisch an.
#
# Doppelklick startet Server und Tunnel in einem Terminalfenster. Das
# Fenster bleibt offen, denn dort stehen die Adressen und der fertige
# Befehl fuer den Gemeindelaptop.
#
#   ./verknuepfung.sh

set -u
ORDNER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Der Schreibtisch heisst je nach Spracheinstellung anders.
SCHREIBTISCH="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
[ -d "${SCHREIBTISCH:-}" ] || SCHREIBTISCH="$HOME/Schreibtisch"
[ -d "$SCHREIBTISCH" ] || SCHREIBTISCH="$HOME/Desktop"
[ -d "$SCHREIBTISCH" ] || { echo "Kein Schreibtischordner gefunden."; exit 1; }

SYMBOL="$ORDNER/logo.png"
[ -f "$SYMBOL" ] || SYMBOL="utilities-terminal"

anlegen() {  # Dateiname, Anzeigename, Aufruf, Beschreibung
  local ziel="$SCHREIBTISCH/$1"
  cat > "$ziel" <<ENDE
[Desktop Entry]
Type=Application
Name=$2
Comment=$4
Exec=bash -c 'cd "$ORDNER" && $3; echo; echo "Fenster kann geschlossen werden."; read -n1'
Path=$ORDNER
Icon=$SYMBOL
Terminal=true
Categories=AudioVideo;
ENDE
  chmod +x "$ziel"
  # GNOME startet Verknuepfungen erst, wenn sie als vertrauenswuerdig
  # markiert sind. Ohne das erscheint nur ein Warnhinweis.
  gio set "$ziel" metadata::trusted true 2>/dev/null || true
  echo "  angelegt: $2"
}

anlegen "Devarenu starten.desktop" "Devarenu starten" \
        "./start.sh" \
        "Server starten und die Adressen anzeigen"

anlegen "Devarenu Mikrofon.desktop" "Devarenu am Mikrofon" \
        "./start.sh --mikro 1" \
        "Ton vom Aufnahmegerät Nummer 1"

echo
echo "Auf dem Schreibtisch liegen jetzt zwei Verknuepfungen."
echo "Beim ersten Doppelklick fragt GNOME einmal nach, ob sie ausgefuehrt"
echo "werden duerfen. Danach nicht mehr."
