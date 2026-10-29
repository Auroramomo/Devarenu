#!/usr/bin/env bash
# Beendet systemd ein Update, weil es laenger dauert als die Zeitgrenze
# seiner Unit?
#
#   bash pruefstand/update_zeitgrenzen_test.sh > .tmp/zeitgrenzen.txt 2>&1
#   DEVARENU_VORLAGEN=ORDNER bash pruefstand/update_zeitgrenzen_test.sh
#                                   (die Vorlagen eines anderen Stands)
#
# Dauert gut 15 Minuten: die vier Proben laufen gleichzeitig, die
# laengste so lange wie die alte Grenze von devarenu-update (900 s) plus
# fuenf Sekunden.
#
# WARUM DIESER LAUF EXISTIERT
#
# Bis zum 29.10.2026 hatten die Units, die ein Update ausfuehren, feste
# Grenzen: das Wartungsfenster 120 s, der Knopf "Jetzt aus dem Netz" und
# das Stick-Update je 900 s, das Lesen des Sticks 300 s. Seit 0.5.2 laeuft
# das Update in Fenster und Knopf als root und kommt bis zum llama-Schritt
# (bis 50 min). systemd haette es mittendrin beendet, ohne Ruecksprung.
#
# WAS HIER ECHT IST
#
# systemd. Je Vorlage startet eine Benutzer-Unit (systemd-run --user) mit
# GENAU der Zeitgrenze aus der Vorlage und einem "sleep", der fuenf
# Sekunden laenger dauert als die alte Grenze dieser Unit. Steht in der
# Vorlage noch die alte Grenze, beendet systemd den sleep -- rot. Nichts
# davon braucht root oder fasst einen Dienst an.

set -u
ECHT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VORLAGEN="${DEVARENU_VORLAGEN:-$ECHT}"

GRUEN="\033[32m"; ROT="\033[31m"; AUS="\033[0m"
FEHLER=0
pruefe() {  # was erwartet ist
  if [ "$2" = "$3" ]; then
    printf "   ${GRUEN}ok${AUS}    %s\n" "$1"
  else
    printf "   ${ROT}FEHL${AUS}  %s: erwartet %s, ist %s\n" "$1" "$2" "$3"
    FEHLER=$((FEHLER + 1))
  fi
}
titel() { printf "\n\033[1m== %s\033[0m\n" "$*"; }

# Unit-Vorlage und ihre Grenze bis zum 29.10.2026.
UNITS="devarenu-fenster.service:120 devarenu-onlineupdate.service:900 \
devarenu-update.service:900 devarenu-stick@.service:300"

wert() {  # $1 Vorlage, $2 Schluessel -> der letzte Wert, oder leer
  sed -n "s/^$2=//p" "$1" | tail -1
}

titel "1) Die Vorlagen ($VORLAGEN)"
for paar in $UNITS; do
  unit="${paar%%:*}"
  datei="$VORLAGEN/$unit.vorlage"
  pruefe "$unit: TimeoutStartSec" "infinity" "$(wert "$datei" TimeoutStartSec)"
  pruefe "$unit: kein TimeoutSec, kein RuntimeMaxSec" "" \
    "$(wert "$datei" TimeoutSec)$(wert "$datei" RuntimeMaxSec)"
done

titel "2) systemd: ein Lauf, laenger als die alte Grenze"
if ! systemctl --user show-environment >/dev/null 2>&1; then
  printf "   ${ROT}!${AUS}     Kein systemd --user. NICHT geprueft.\n"
  exit 1
fi
LAUF=$$
mkdir -p "$ECHT/.tmp"
ERG="$(mktemp -d "$ECHT/.tmp/zeitgrenzen-XXXXXX")"
trap 'rm -rf "$ERG"' EXIT INT TERM
for paar in $UNITS; do
  unit="${paar%%:*}"; alt="${paar#*:}"
  grenze="$(wert "$VORLAGEN/$unit.vorlage" TimeoutStartSec)"
  name="devarenu-pruef-${unit%%[@.]*}-$LAUF"
  printf "         %s: Grenze %s, Lauf %s s\n" "$unit" "${grenze:-Vorgabe}" "$((alt + 5))"
  ( systemd-run --user --wait --quiet --collect --unit="$name" \
      -p Type=oneshot ${grenze:+-p TimeoutStartSec=$grenze} \
      /bin/sleep "$((alt + 5))"
    echo "$?" > "$ERG/$name.rc" ) &
done
wait
for paar in $UNITS; do
  unit="${paar%%:*}"; alt="${paar#*:}"
  name="devarenu-pruef-${unit%%[@.]*}-$LAUF"
  pruefe "$unit: $((alt + 5)) s laufen durch" "0" \
    "$(cat "$ERG/$name.rc" 2>/dev/null || echo keine)"
done

printf '\n'
if [ "$FEHLER" = 0 ]; then
  printf "${GRUEN}Alle Faelle wie erwartet.${AUS}\n"
else
  printf "${ROT}%d Fehler.${AUS}\n" "$FEHLER"
fi
exit "$FEHLER"
