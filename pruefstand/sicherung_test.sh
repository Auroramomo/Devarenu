#!/usr/bin/env bash
# Sichern und Zuruecksichern -- im Wegwerfordner, ohne sudo.
#
#   bash pruefstand/sicherung_test.sh
#
# WAS HIER BEWIESEN WERDEN SOLL
#
# Die Sicherung nimmt Geheimnisse mit: das WLAN-Passwort aus
# zustand.json, das ntfy-Thema aus meldung.json, das RustDesk-Kennwort.
# Sie landet auf einer tragbaren Platte, und tragbare Platten liegen
# im Auto, im Schrank, bei jemandem zu Hause.
#
# Drei Zusicherungen, und alle drei werden hier nachgesehen:
#
#   1. Auf der Platte steht KEIN Geheimnis im Klartext.
#   2. Ohne Passphrase kommt niemand an die Geheimnisse -- aber
#      sehr wohl an alles andere.
#   3. Zurueckgespielt stehen die Rechte wieder, wie sie waren
#      (600 auf zustand.json und meldung.json).
#
# sudo wird NICHT aufgerufen: DEVARENU_SUDO zeigt auf eine Attrappe,
# die nur mitschreibt. Dieselbe Naht wie DEVARENU_NMCLI in
# wartungsfenster.sh.

set -u
ECHT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASIS="$(mktemp -d)"
trap 'rm -rf "$BASIS"' EXIT INT TERM

GRUEN="\033[32m"; ROT="\033[31m"; AUS="\033[0m"
FEHLER=0
PASS="vier Woerter sind besser"

pruefe() {  # was erwartet ist
  if [ "$2" = "$3" ]; then
    printf "   ${GRUEN}ok${AUS}    %s\n" "$1"
  else
    printf "   ${ROT}FEHL${AUS}  %s: erwartet %s, ist %s\n" "$1" "$2" "$3"
    FEHLER=$((FEHLER + 1))
  fi
}
titel() { printf "\n\033[1m== %s\033[0m\n" "$*"; }

if ! command -v gpg >/dev/null; then
  printf "   ${ROT}!${AUS}     UEBERSPRUNGEN: gpg fehlt. Damit ist NICHT "
  printf "geprueft,\n         ob die Geheimnisse verschluesselt werden.\n"
  exit 1
fi

# ------------------------------------------------------------ Aufbau
cat > "$BASIS/sudo" <<'SU'
#!/bin/sh
echo "SUDO $*" >> "$(dirname "$0")/sudo.log"
case "$1" in test) exit 1 ;; esac
exit 0
SU
chmod +x "$BASIS/sudo"

Q="$BASIS/rechner"; mkdir -p "$Q/models" "$Q/voices" "$Q/heim/.config/rustdesk"
cp "$ECHT/sichern.sh" "$ECHT/zuruecksichern.sh" "$Q/"
echo "0.9.9" > "$Q/VERSION"
printf '{"wlan":{"ssid":"Gemeinde","passwort":"PASSWORT-IM-TEST"}}' > "$Q/zustand.json"
chmod 600 "$Q/zustand.json"
printf '{"router":true,"adresse":"10.0.0.1"}' > "$Q/netz.json"
printf '{"ntfy":"THEMA-IM-TEST"}' > "$Q/meldung.json"
chmod 600 "$Q/meldung.json"
printf 'KENNWORT-IM-TEST' > "$Q/heim/.config/rustdesk/RustDesk.toml"
echo "modell" > "$Q/models/modell.bin"
echo "stimme" > "$Q/voices/stimme.onnx"
P="$BASIS/platte"; mkdir -p "$P"

lauf() { (cd "$Q" && DEVARENU_SUDO="$BASIS/sudo" HOME="$Q/heim" bash "$@"); }

titel "1) Sichern"
AUS1="$(printf '%s\n%s\n' "$PASS" "$PASS" | lauf sichern.sh "$P" 2>&1)"
STAND="$(ls -d "$P"/devarenu-sicherung-* 2>/dev/null | head -1)"
pruefe "ein Sicherungsordner ist entstanden" "ja" \
  "$([ -n "$STAND" ] && [ -d "$STAND" ] && echo ja || echo nein)"
pruefe "der geheime Teil liegt verschluesselt da" "ja" \
  "$([ -f "$STAND/geheim.tar.gz.gpg" ] && echo ja || echo nein)"
pruefe "und zwar mit Rechten 600" "600" \
  "$(stat -c %a "$STAND/geheim.tar.gz.gpg" 2>/dev/null)"
pruefe "der Ordner selbst ist 700" "700" "$(stat -c %a "$STAND")"
pruefe "RustDesk ist mitgekommen" "ja" \
  "$(printf '%s' "$AUS1" | grep -q 'RustDesk-Einstellungen gelesen' \
     && echo ja || echo nein)"
pruefe "Modelle und Stimmen liegen offen da" "ja" \
  "$([ -f "$STAND/offen/models/modell.bin" ] \
    && [ -f "$STAND/offen/voices/stimme.onnx" ] && echo ja || echo nein)"
pruefe "stand.txt nennt die Fassung" "ja" \
  "$(grep -q 'fassung=0.9.9' "$STAND/offen/stand.txt" && echo ja || echo nein)"
pruefe "Pruefsummen liegen dabei" "ja" \
  "$([ -f "$STAND/pruefsummen.txt" ] && echo ja || echo nein)"
pruefe "und sie stimmen" "ja" \
  "$( (cd "$STAND" && sha256sum --quiet -c pruefsummen.txt >/dev/null 2>&1) \
     && echo ja || echo nein)"

titel "2) Kein Geheimnis im Klartext auf der Platte"
for wort in PASSWORT-IM-TEST THEMA-IM-TEST KENNWORT-IM-TEST "$PASS"; do
  pruefe "\"$wort\" steht nirgends" "nein" \
    "$(grep -rqF "$wort" "$STAND" 2>/dev/null && echo ja || echo nein)"
done
# Die Aufnahmen gehoeren ausdruecklich NICHT in die Sicherung: sie
# werden nach sieben Tagen geloescht, und eine Sicherung, die sie
# mitnimmt, hebelt diese Zusage aus.
pruefe "keine Aufnahmen in der Sicherung" "nein" \
  "$(find "$STAND" -name 'Predigt_*' -o -name 'predigt_*' 2>/dev/null \
     | grep -q . && echo ja || echo nein)"

titel "3) Zuruecksichern mit Passphrase"
Z="$BASIS/neu"; mkdir -p "$Z/heim"
cp "$ECHT/zuruecksichern.sh" "$Z/"
printf '%s\n' "$PASS" \
  | (cd "$Z" && DEVARENU_SUDO="$BASIS/sudo" HOME="$Z/heim" \
       bash zuruecksichern.sh "$STAND" >/dev/null 2>&1)
pruefe "zustand.json ist zurueck" "ja" \
  "$(grep -qF 'PASSWORT-IM-TEST' "$Z/zustand.json" 2>/dev/null \
     && echo ja || echo nein)"
pruefe "mit Rechten 600" "600" "$(stat -c %a "$Z/zustand.json" 2>/dev/null)"
pruefe "meldung.json ist zurueck" "ja" \
  "$(grep -qF 'THEMA-IM-TEST' "$Z/meldung.json" 2>/dev/null \
     && echo ja || echo nein)"
pruefe "auch mit 600" "600" "$(stat -c %a "$Z/meldung.json" 2>/dev/null)"
pruefe "netz.json ist zurueck und 644" "644" \
  "$(stat -c %a "$Z/netz.json" 2>/dev/null)"
pruefe "RustDesk ist zurueck" "ja" \
  "$(grep -qF 'KENNWORT-IM-TEST' "$Z/heim/.config/rustdesk/RustDesk.toml" \
       2>/dev/null && echo ja || echo nein)"
pruefe "Modelle sind zurueck" "ja" \
  "$([ -f "$Z/models/modell.bin" ] && echo ja || echo nein)"

titel "4) Ohne Passphrase: der offene Teil geht trotzdem"
Z2="$BASIS/neu2"; mkdir -p "$Z2/heim"
cp "$ECHT/zuruecksichern.sh" "$Z2/"
AUS2="$( (cd "$Z2" && DEVARENU_SUDO="$BASIS/sudo" HOME="$Z2/heim" \
  bash zuruecksichern.sh "$STAND" --ohne-geheim 2>&1) )"
pruefe "Modelle und Stimmen kommen zurueck" "ja" \
  "$([ -f "$Z2/models/modell.bin" ] && [ -f "$Z2/voices/stimme.onnx" ] \
    && echo ja || echo nein)"
pruefe "zustand.json aber nicht" "nein" \
  "$([ -f "$Z2/zustand.json" ] && echo ja || echo nein)"
pruefe "und es steht da, was neu eingetragen werden muss" "ja" \
  "$(printf '%s' "$AUS2" | grep -q 'Neu eintragen muss jemand' \
     && echo ja || echo nein)"
pruefe "namentlich das WLAN-Passwort" "ja" \
  "$(printf '%s' "$AUS2" | grep -q 'WLAN-Name und -Passwort' \
     && echo ja || echo nein)"

titel "5) Falsche Passphrase: nichts halb Zurueckgespieltes"
Z3="$BASIS/neu3"; mkdir -p "$Z3/heim"
cp "$ECHT/zuruecksichern.sh" "$Z3/"
AUS3="$(printf 'falschfalschfalsch\n' \
  | (cd "$Z3" && DEVARENU_SUDO="$BASIS/sudo" HOME="$Z3/heim" \
      bash zuruecksichern.sh "$STAND" 2>&1) )"
pruefe "es bricht ab" "ja" \
  "$(printf '%s' "$AUS3" | grep -q 'Das Entschluesseln ging nicht' \
     && echo ja || echo nein)"
pruefe "zustand.json wurde nicht angelegt" "nein" \
  "$([ -f "$Z3/zustand.json" ] && echo ja || echo nein)"
pruefe "und es nennt den Weg ohne Passphrase" "ja" \
  "$(printf '%s' "$AUS3" | grep -q -- '--ohne-geheim' && echo ja || echo nein)"

titel "6) Vorhandenes wird nicht stillschweigend ueberschrieben"
printf '{"wlan":{"ssid":"VORGABE","passwort":""}}' > "$Z/zustand.json"
printf '%s\n' "$PASS" \
  | (cd "$Z" && DEVARENU_SUDO="$BASIS/sudo" HOME="$Z/heim" \
      bash zuruecksichern.sh "$STAND" >/dev/null 2>&1)
pruefe "die Vorgabe liegt beiseite" "ja" \
  "$(grep -rqF 'VORGABE' "$Z"/.vorher-* 2>/dev/null && echo ja || echo nein)"
pruefe "und die Sicherung steht wieder da" "ja" \
  "$(grep -qF 'PASSWORT-IM-TEST' "$Z/zustand.json" && echo ja || echo nein)"

titel "7) sudo wurde nie wirklich gebraucht"
# Die Attrappe schreibt mit. Gerufen werden darf sie -- aber nur fuer
# die drei Dinge, die ohne root nicht gehen.
if [ -f "$BASIS/sudo.log" ]; then
  FREMD="$(grep -cvE 'test -d /etc/NetworkManager|ls -1 /etc/NetworkManager|tar -cf - -C /etc/NetworkManager|cp -a .* /etc/NetworkManager|chown -R root:root /etc/NetworkManager|chmod 600 /etc/NetworkManager|nmcli connection reload|mkdir -p /opt|cp -a .* /opt' \
    "$BASIS/sudo.log" || true)"
  pruefe "sudo nur fuer /etc/NetworkManager und /opt" "0" "$FREMD"
else
  printf "   ${GRUEN}ok${AUS}    sudo wurde gar nicht gerufen\n"
fi

printf '\n'
if [ "$FEHLER" = 0 ]; then
  printf "${GRUEN}Alle Faelle wie erwartet.${AUS}\n"
else
  printf "${ROT}%d Fehler.${AUS}\n" "$FEHLER"
fi
exit "$FEHLER"
