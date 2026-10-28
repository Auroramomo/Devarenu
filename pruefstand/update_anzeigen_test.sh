#!/usr/bin/env bash
# Veraltete Update-Anzeigen (A4, 28.10.2026).
#
#   bash pruefstand/update_anzeigen_test.sh
#
# a) stick_update.sh --stand zeigte in Rostock weiter einen Fehlschlag
#    vom 27.09. (Rechtefehler im Updater 0.3.0, laengst behoben) --
#    obwohl danach Updates ueber das Netz gelungen waren. Es las nur
#    update/stand.json. Regel: nach einem gelungenen Update auf
#    beliebigem Weg gilt ein aelterer Fehlschlag als erledigt.
# b) Die Update-Seite am Pult: "Der Stick bringt Fassung 0.3.0, hier
#    laeuft schon ?." -- die laufende Fassung fehlte im Satz.
#
# Nur Kopien in einem Wegwerfordner; --stand liest nur.
set -u
ECHT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FEHLER=0
pruefe() {
  if [ "$2" = "$3" ]; then printf '   ok    %s\n' "$1"
  else printf '   \033[31mFEHL\033[0m  %s: erwartet %s, ist %s\n' "$1" "$2" "$3"
       FEHLER=$((FEHLER+1)); fi
}
titel() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
W="$(mktemp -d -p "$ECHT/.tmp" anzeige-XXXXXX)"
trap 'rm -rf "$W"' EXIT
cp "$ECHT/stick_update.sh" "$W/"
mkdir -p "$W/update"

FEHLSCHLAG='{
  "lage": "fehlgeschlagen",
  "version": "0.3.0",
  "vorher": "0.2.12",
  "text": "Update 0.3.0 ist fehlgeschlagen: Rechte.",
  "zeit": "2026-09-27 10:12:00"
}'
NETZ_GUT='{
  "lage": "eingespielt",
  "version": "0.5.1",
  "vorher": "0.5.0",
  "text": "Fassung 0.5.1 eingespielt (Netz).",
  "zeit": "2026-10-28 09:30:00"
}'

titel "a) Ein Fehlschlag, danach ein gelungenes Update ueber das Netz"
printf '%s\n' "$FEHLSCHLAG" > "$W/update/stand.json"
printf '%s\n' "$NETZ_GUT" > "$W/update/stand-online.json"
AUS="$(cd "$W" && bash stick_update.sh --stand 2>&1)"
printf '%s\n' "$AUS" | sed 's/^/      /'
pruefe "der juengere Stand steht da" "ja" \
  "$(printf '%s' "$AUS" | grep -q '0.5.1 eingespielt' && echo ja || echo nein)"
pruefe "der alte Fehlschlag gilt als erledigt" "ja" \
  "$(printf '%s' "$AUS" | grep -qi 'erledigt' && echo ja || echo nein)"
pruefe "und steht nicht mehr als aktueller Stand da" "nein" \
  "$(printf '%s' "$AUS" | grep -q '"lage": "fehlgeschlagen"' && echo ja || echo nein)"

titel "a2) Der Fehlschlag ist der juengste: er bleibt stehen"
printf '%s\n' "$NETZ_GUT" | sed 's/2026-10-28/2026-09-01/' > "$W/update/stand-online.json"
AUS="$(cd "$W" && bash stick_update.sh --stand 2>&1)"
pruefe "der Fehlschlag steht da" "ja" \
  "$(printf '%s' "$AUS" | grep -q 'fehlgeschlagen' && echo ja || echo nein)"
pruefe "ohne \"erledigt\"" "nein" \
  "$(printf '%s' "$AUS" | grep -q 'erledigt' && echo ja || echo nein)"

titel "a3) Ein gescheiterter Netzversuch erledigt nichts"
printf '%s\n' "$NETZ_GUT" | sed 's/"eingespielt"/"fehlgeschlagen"/' \
  > "$W/update/stand-online.json"
AUS="$(cd "$W" && bash stick_update.sh --stand 2>&1)"
pruefe "kein \"erledigt\" nach einem weiteren Fehlschlag" "nein" \
  "$(printf '%s' "$AUS" | grep -q 'erledigt' && echo ja || echo nein)"

titel "a4) Nichts da"
rm -f "$W/update/stand.json" "$W/update/stand-online.json"
pruefe "wie bisher" "Kein Update vorgemerkt." \
  "$(cd "$W" && bash stick_update.sh --stand 2>&1)"

titel "b) stick_update.sh schreibt bei \"nicht neuer\" die laufende Fassung mit"
# Der Satz am Pult (upd_nicht_neuer) setzt {alt} aus dem Feld "vorher"
# ein. Ohne das Feld stand dort "?" (update_satz_test.mjs prueft das
# Pult selbst, auch fuer alte stand.json ohne das Feld).
ZEILEN="$(grep -c 'stand_schreiben nicht_neuer' "$ECHT/stick_update.sh")"
MIT="$(grep -A1 'stand_schreiben nicht_neuer' "$ECHT/stick_update.sh" \
       | grep -c '"\$hier"$')"
pruefe "beide Stellen geben \$hier als vorher mit" "$ZEILEN" "$MIT"

printf '\n'
if [ "$FEHLER" = 0 ]; then printf '\033[32mAlle Faelle wie erwartet.\033[0m\n'
else printf '\033[31m%d Fehler.\033[0m\n' "$FEHLER"; fi
exit "$FEHLER"
