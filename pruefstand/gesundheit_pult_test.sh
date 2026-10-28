#!/usr/bin/env bash
# Prueft gesundheit.sh nach einem Update auch das Pult? (0.5.2)
#
#   bash pruefstand/gesundheit_pult_test.sh
#
# Seit 0.5.2 liegt das Pult in web/pult.html und wird bei jedem Aufruf
# gelesen. Fehlt die Datei, liefert /pult eine Fehlerseite -- und bis
# hierher sah der Gesundheitscheck das nicht: er fragte /api/zustand
# und den Systemcheck, nie das Pult. Ein Update ohne Pult waere als
# gesund durchgegangen, und am Sonntag kaeme niemand an die Bedienung.
#
# Die ECHTE gesundheit.sh in einem Wegwerfordner; systemctl ist die
# Attrappe aus pruefstand/attrappen, curl eine eigene, die je Weg
# antwortet, wie dieser Lauf es vorgibt.

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

ORDNER="$BASIS/devarenu"
mkdir -p "$ORDNER" "$BASIS/bin"
cp "$ECHT/gesundheit.sh" "$ORDNER/"
# Kein venv: befunde_jetzt liefert dann nichts, und "neue Befunde"
# spielt in diesem Lauf keine Rolle.

# curl: /api/zustand mit Fassung, /pult je nach PULT_ART. Versteht -w
# mit %{http_code} so, wie curl es tut: der Status hinter dem Inhalt.
cat > "$BASIS/bin/curl" <<'CURL'
#!/usr/bin/env bash
url="" code=""
for a in "$@"; do
  case "$a" in http://*) url="$a" ;; esac
done
case "$url" in
  */api/zustand) body='{"live": false, "fassung": "0.5.2", "gesamt": 0}'; code=200 ;;
  */pult)
    case "${PULT_ART:-gut}" in
      gut)         body='<!doctype html><html lang=de><title>Pult</title>'; code=200 ;;
      fehlt)       body="<h1>pult.html fehlt</h1><p>$ORDNER/web/pult.html</p>"; code=500 ;;
      fehlt_200)   body="<h1>pult.html fehlt</h1><p>x</p>"; code=200 ;;
      gesperrt)    body='<!doctype html><title>Pult</title><form>'; code=401 ;;
      still)       exit 7 ;;
    esac ;;
  *) exit 7 ;;
esac
printf '%s' "$body"
for a in "$@"; do
  case "$a" in *http_code*) printf '\n%s' "$code" ;; esac
done
CURL
chmod +x "$BASIS/bin/curl"

lauf() {  # $1 PULT_ART -> "rc|letzte Zeilen"
  local aus rc=0
  aus="$(PATH="$BASIS/bin:$ECHT/pruefstand/attrappen:$PATH" PULT_ART="$1" \
         ORDNER="$ORDNER" DEV_VERSION=0.5.2 DEV_SICHERUNG="$BASIS/sich" \
         bash "$ORDNER/gesundheit.sh" 2>&1)" || rc=$?
  printf '%s\n' "$aus" | sed 's/\x1b\[[0-9;]*m//g' > "$BASIS/aus-$1.txt"
  echo "$rc"
}

titel "1) Das Pult kommt"
pruefe "gesund (Rueckgabe 0)" 0 "$(lauf gut)"
pruefe "und es steht dabei" ja \
  "$(grep -q 'ok *Pult antwortet' "$BASIS/aus-gut.txt" && echo ja || echo nein)"

titel "2) Das Pult kommt nicht"
pruefe "web/pult.html fehlt (500): nicht gesund" 1 "$(lauf fehlt)"
pruefe "   und er sagt, was fehlt" ja \
  "$(grep -q 'FEHLT.*Pult' "$BASIS/aus-fehlt.txt" && echo ja || echo nein)"
pruefe "Fehlerseite mit 200: nicht gesund" 1 "$(lauf fehlt_200)"
pruefe "401 statt Pult: nicht gesund" 1 "$(lauf gesperrt)"
pruefe "keine Antwort auf /pult: nicht gesund" 1 "$(lauf still)"

titel "3) Umbenannte Befunde sind keine neuen (28.10.2026)"
# Die Grundlinie (--vorher) schreibt beim Sprung auf 0.5.2 noch die
# alte Fassung: "dienst_ollama_tot". Der neue Systemcheck nennt dasselbe
# "sprachmodell_dienst_tot". Hing Ollama schon vorher, darf das Update
# deshalb nicht zurueckrollen. Ein python, das feste Kennungen ausgibt,
# steht fuer den Systemcheck.
mkdir -p "$ORDNER/.venv/bin" "$BASIS/sich"
printf '#!/bin/sh\ncat >/dev/null\nprintf "%%b" "$BEFUNDE_JETZT"\n' \
  > "$ORDNER/.venv/bin/python"
chmod +x "$ORDNER/.venv/bin/python"
printf 'dienst_ollama_tot\n' > "$BASIS/sich/befunde-vorher"
pruefe "dienst_ollama_tot vorher, sprachmodell_dienst_tot nachher: gesund" 0 \
  "$(BEFUNDE_JETZT='sprachmodell_dienst_tot\n' lauf gut)"
printf 'dienst_ollama\n' > "$BASIS/sich/befunde-vorher"
pruefe "dienst_ollama vorher, sprachmodell_dienst nachher: gesund" 0 \
  "$(BEFUNDE_JETZT='sprachmodell_dienst\n' lauf gut)"
pruefe "ein wirklich neuer Befund bleibt neu" 1 \
  "$(BEFUNDE_JETZT='sprachmodell_dienst\nzwei_sprachmodelle\n' lauf gut)"
rm -rf "$ORDNER/.venv" "$BASIS/sich"

printf '\n'
[ "$FEHLER" = 0 ] || { printf '\033[31m%s Fehler.\033[0m\n' "$FEHLER"; exit 1; }
printf '\033[32mAlle Faelle wie erwartet.\033[0m\n'
