#!/usr/bin/env bash
# Nennen start.sh, einrichten.sh und selbsttest.py die Seiten unter web/?
# (0.5.2)
#
#   bash pruefstand/web_dateilisten_test.sh
#
# Seit 0.5.2 liegen Pult, Anmeldung und QR-Seite in web/. Die drei
# Skripte pruefen vor dem Start, ob alles da ist, was der Server
# braucht -- client.html stand dort, die Seiten unter web/ nicht. Fehlte
# eine, startete der Server, und erst am Pult stand "pult.html fehlt".
#
# Gefahren wird jeweils der ECHTE Pruefblock in einem Wegwerfordner,
# in dem genau eine Datei fehlt.

set -u
ECHT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASIS="$(mktemp -d)"
trap 'rm -rf "$BASIS"' EXIT
FEHLER=0
pruefe() {
  if [ "$2" = "$3" ]; then printf '   ok    %s\n' "$1"
  else printf '   \033[31mFEHL\033[0m  %s: erwartet %s, ist %s\n' "$1" "$2" "$3"
       FEHLER=$((FEHLER+1)); fi
}
titel() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
WEB="web/pult.html web/anmeldung.html web/qr.html"

# Ein Ordner mit allen Dateien, die die Listen kennen -- leer, aber da.
ordner_bauen() {  # $1 Ordner, $2 die Datei, die fehlen soll
  rm -rf "$1"; mkdir -p "$1/web"
  for f in server.py config.py zustand.py grafikkarte.py glossar.py \
           bibelstellen.py skript_lesen.py namen_aus_bibel.py \
           laengenfaktor.py tonhelfer.py selbsttest.py client.html $WEB; do
    : > "$1/$f"
  done
  rm -f "$1/$2"
}

# Der Block "FEHLEND=..." bis zum ersten "done" danach, wortgleich.
titel "1) start.sh"
sed -n '/^FEHLEND=""$/,/^done$/p' "$ECHT/start.sh" > "$BASIS/start_block.sh"
pruefe "der Pruefblock ist gefunden" ja \
  "$(grep -q 'client.html' "$BASIS/start_block.sh" && echo ja || echo nein)"
for w in $WEB; do
  ordner_bauen "$BASIS/o" "$w"
  pruefe "fehlt $w: start.sh nennt sie" " $w" \
    "$(cd "$BASIS/o" && bash -c "source '$BASIS/start_block.sh'; printf '%s' \"\$FEHLEND\"")"
done
ordner_bauen "$BASIS/o" "nichts"
pruefe "alles da: start.sh vermisst nichts" "" \
  "$(cd "$BASIS/o" && bash -c "source '$BASIS/start_block.sh'; printf '%s' \"\$FEHLEND\"")"

titel "2) einrichten.sh"
# Dort meldet der Block mit warn und setzt MANGEL.
sed -n '/^MANGEL=0$/,/^done$/p' "$ECHT/einrichten.sh" > "$BASIS/einr_block.sh"
pruefe "der Pruefblock ist gefunden" ja \
  "$(grep -q 'client.html' "$BASIS/einr_block.sh" && echo ja || echo nein)"
for w in $WEB; do
  ordner_bauen "$BASIS/o" "$w"
  pruefe "fehlt $w: einrichten.sh nennt sie" "$w FEHLT|1" \
    "$(cd "$BASIS/o" && bash -c "gut(){ :; }; warn(){ echo \"\$*\"; }; \
       source '$BASIS/einr_block.sh'; printf '|%s' \"\$MANGEL\"" | tr -d '\n')"
done

titel "3) selbsttest.py"
for w in $WEB; do
  ordner_bauen "$BASIS/o" "$w"
  pruefe "fehlt $w: der Selbsttest meldet sie" ja \
    "$("$ECHT/.venv/bin/python" "$ECHT/pruefstand/web_dateilisten_hilfe.py" \
         "$BASIS/o" | grep -q "FEHLT.*$w fehlt" && echo ja || echo nein)"
done

printf '\n'
[ "$FEHLER" = 0 ] || { printf '\033[31m%s Fehler.\033[0m\n' "$FEHLER"; exit 1; }
printf '\033[32mAlle Faelle wie erwartet.\033[0m\n'
