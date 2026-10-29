#!/usr/bin/env bash
# Der Sprung von v0.5.1 auf diese Fassung, wenn Ollama kaputt oder weg ist.
#
#   bash pruefstand/update_ohne_ollama_test.sh > .tmp/update_ohne_ollama.txt 2>&1
#
# WARUM DIESER LAUF EXISTIERT
#
# In Rostock war der Zustand von Ollama vor dem Update auf 0.5.2 unklar:
# gehoben, abgebrochen zurueckgesprungen, neu installiert. Gerade dort
# soll das Update llama-server einrichten (llama_einrichten.py, am ENDE
# von aktualisierung.sh) -- das Modell liegt ja noch in der Ablage.
#
# Davor laeuft aber der Selbsttest, und zwar bei diesem Sprung immer:
# teile.json hat sich gegenueber v0.5.1 geaendert. Bis zum 29.10.2026
# zaehlte dort "kein Sprachmodell-Server antwortet" als Fehler. Das
# Update rollte damit zurueck, BEVOR der llama-Schritt kam: am Ende
# uebersetzte weder Ollama noch llama-server, obwohl llama-server haette
# laufen koennen. einspielweg_test.sh sah das nicht, dort ist der ganze
# Selbsttest eine Attrappe, die immer 0 zurueckgibt.
#
# WAS HIER ECHT IST UND WAS NICHT
#
# Echt: aktualisieren.sh aus v0.5.1 (der Kern in Rostock), die
# aktualisierung.sh, gesundheit.sh, systemcheck.py und llama_einrichten.py
# dieses Stands, und der Teil des Selbsttests, der das Sprachmodell
# prueft. Piper und Whisper sind Attrappen (gruen): sie brauchten zehn
# Gigabyte und die Grafikkarte, und um sie geht es hier nicht. sudo,
# systemctl, curl, nvidia-smi wie in einspielweg_test.sh.
#
# Ollama ist entweder die Attrappe aus pruefstand/attrappen auf einem
# freien Port, oder es antwortet gar nichts. Das echte Ollama dieses
# Rechners wird nie gefragt: config.py im Fernrepo zeigt woanders hin.

set -u
ECHT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$ECHT/.tmp"
BASIS="$(mktemp -d "$ECHT/.tmp/update-ohne-ollama-XXXXXX")"
export PATH="$ECHT/pruefstand/attrappen:$PATH"
START=v0.5.1
NIRGENDS="http://127.0.0.1:9"

GRUEN="\033[32m"; ROT="\033[31m"; AUS="\033[0m"
FEHLER=0
ATTRAPPE_PID=""

aufraeumen() {
  [ -n "$ATTRAPPE_PID" ] && kill "$ATTRAPPE_PID" 2>/dev/null
  git -C "$ECHT" worktree remove --force "$BASIS/baum-$START" 2>/dev/null || true
  git -C "$ECHT" worktree prune 2>/dev/null || true
  rm -rf "$BASIS"
}
trap aufraeumen EXIT INT TERM

pruefe() {  # was erwartet ist
  if [ "$2" = "$3" ]; then
    printf "   ${GRUEN}ok${AUS}    %s\n" "$1"
  else
    printf "   ${ROT}FEHL${AUS}  %s: erwartet %s, ist %s\n" "$1" "$2" "$3"
    FEHLER=$((FEHLER + 1))
  fi
}
titel() { printf "\n\033[1m== %s\033[0m\n" "$*"; }

titel "0) Vorbedingungen"
git -C "$ECHT" rev-parse -q --verify "refs/tags/$START" >/dev/null \
  || { printf "   ${ROT}!${AUS}     das Tag %s fehlt\n" "$START"; exit 1; }
NEU="$(tr -d '[:space:]' < "$ECHT/VERSION")"
pruefe "teile.json hat sich seit $START geaendert (dann laeuft der Selbsttest)" \
  "ja" "$(git -C "$ECHT" diff --quiet "$START" HEAD -- teile.json \
          && echo nein || echo ja)"
git -C "$ECHT" worktree add -q --detach "$BASIS/baum-$START" "$START" 2>/dev/null \
  || { printf "   ${ROT}FEHL${AUS}  worktree fuer %s ging nicht\n" "$START"; exit 1; }

# Die Ollama-Attrappe auf einem freien Port.
python3 "$ECHT/pruefstand/attrappen/ollama_attrappe.py" > "$BASIS/attrappe.txt" &
ATTRAPPE_PID=$!
for _ in $(seq 1 50); do
  grep -q '^PORT ' "$BASIS/attrappe.txt" 2>/dev/null && break
  sleep 0.1
done
OLLAMA_ATTRAPPE="http://127.0.0.1:$(awk '/^PORT /{print $2}' "$BASIS/attrappe.txt")"
pruefe "die Ollama-Attrappe antwortet" "ja" \
  "$(python3 -c "import urllib.request,sys; urllib.request.urlopen(sys.argv[1]+'/api/tags',timeout=3)" \
     "$OLLAMA_ATTRAPPE" 2>/dev/null && echo ja || echo nein)"

titel "1) Ein Fernrepo: $START und $NEU"
SCHLUESSEL="$BASIS/freigabe"
ssh-keygen -q -t ed25519 -N "" -C pruefstand -f "$SCHLUESSEL"
FERN="$BASIS/fern"
mkdir -p "$FERN"
git -C "$FERN" init -q -b main
git -C "$FERN" config user.email pruef@pruefstand
git -C "$FERN" config user.name Pruefstand
git -C "$FERN" config gpg.format ssh
git -C "$FERN" config user.signingkey "$SCHLUESSEL.pub"
git -C "$FERN" config commit.gpgsign false

baum_hinein() {  # $1 Quellordner, $2 Fassung, $3 Tag
  find "$FERN" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
  ( cd "$1" && git ls-files -z | tar --null -cf - -T - ) | tar -xf - -C "$FERN"
  echo "pruef@pruefstand $(cat "$SCHLUESSEL.pub")" > "$FERN/schluessel.erlaubt"
  # Ollama und llama-server dieses Rechners nie fragen.
  sed -i -e "s|^OLLAMA_URL = .*|OLLAMA_URL = \"$OLLAMA_ATTRAPPE\"|" \
         -e "s|^LLAMA_URL = .*|LLAMA_URL = \"$NIRGENDS\"|" "$FERN/config.py"
  # Der Selbsttest: echt bis auf Piper und Whisper.
  if [ -f "$FERN/selbsttest.py" ]; then
    mv "$FERN/selbsttest.py" "$FERN/selbsttest_echt.py"
    printf '%s\n' \
      '#!/usr/bin/env python3' \
      'import sys' \
      'sys.path.insert(0, ".")' \
      'import selbsttest_echt as s' \
      's.pruefe_piper = lambda ziel: (s.ok("Piper (Attrappe)"), False)[1]' \
      's.pruefe_whisper = lambda quelle: s.ok("Whisper (Attrappe)")' \
      'sys.exit(s.main())' > "$FERN/selbsttest.py"
  fi
  git -C "$FERN" add -A >/dev/null 2>&1
  git -C "$FERN" commit -q -m "$2" >/dev/null 2>&1
  git -C "$FERN" tag -s "$3" -m "Devarenu $2" >/dev/null 2>&1
}
baum_hinein "$BASIS/baum-$START" "${START#v}" "$START"
baum_hinein "$ECHT" "$NEU" "v$NEU"
pruefe "beide Tags liegen im Fernrepo" "2" \
  "$(git -C "$FERN" tag --list | wc -l | tr -d ' ')"

# $1 Name des Falls. Ein "Gemeinderechner" auf $START, eingespielt mit
# dessen aktualisieren.sh.
durchlauf() {
  local fall="$1" ziel="$BASIS/rechner-$1" d="$BASIS/daten-$1"
  git clone -q "$FERN" "$ziel"
  git -C "$ziel" config user.email pruef@pruefstand
  git -C "$ziel" config user.name Pruefstand
  git -C "$ziel" -c advice.detachedHead=false checkout -q "$START"
  git -C "$ziel" branch -f main "$START" >/dev/null
  git -C "$ziel" checkout -q main
  git -C "$ziel" branch --set-upstream-to=origin/main main >/dev/null
  printf '{"fassung": 3, "quelle": "de", "ziele": ["en", "ru", "fa"]}\n' \
    > "$ziel/zustand.json"
  chmod 600 "$ziel/zustand.json"
  printf '{"router": false}\n' > "$ziel/netz.json"
  mkdir -p "$ziel/.venv/bin"
  ln -sf "$(command -v python3)" "$ziel/.venv/bin/python"
  mkdir -p "$d" "$BASIS/home-$fall/.config"; chmod 711 "$d"
  ( cd "$ziel" && setsid env HOME="$BASIS/home-$fall" \
      XDG_CONFIG_HOME="$BASIS/home-$fall/.config" \
      DEVARENU_DATEN="$d" \
      DEVARENU_UNIT_ORDNER="$BASIS/units-$fall" \
      DEVARENU_UDEV_REGEL="$BASIS/udev-$fall.rules" \
      STUB_LOG="$BASIS/stub-$fall.log" \
      STUB_FASSUNG="$NEU" \
      DEVARENU_KEIN_NETZ=1 \
      DEVARENU_LLAMA_OHNE_ROOT=1 \
      DEVARENU_LLAMA_OPT="$BASIS/opt-$fall" \
      DEVARENU_LLAMA_URL="$NIRGENDS" \
      bash ./aktualisieren.sh 2>&1 ) | sed 's/\x1b\[[0-9;]*m//g' \
      > "$BASIS/lauf-$fall.txt"
}

bewerten() {  # $1 Fall
  local lauf="$BASIS/lauf-$1.txt" ziel="$BASIS/rechner-$1"
  pruefe "die Fassung steht auf $NEU" "$NEU" \
    "$(tr -d '[:space:]' < "$ziel/VERSION" 2>/dev/null)"
  pruefe "kein Ruecksprung" "nein" \
    "$(grep -q 'Das Update ist gescheitert' "$lauf" && echo ja || echo nein)"
  pruefe "der Selbsttest lief und bestand" "ja" \
    "$(grep -q 'Selbsttest bestanden' "$lauf" && echo ja || echo nein)"
  pruefe "der llama-Schritt lief (er richtet llama-server ein)" "ja" \
    "$(grep -q 'Sprachmodell-Server (llama-server)' "$lauf" \
       && echo ja || echo nein)"
}

titel "2) Ollama laeuft (Attrappe)"
durchlauf ollama_laeuft
bewerten ollama_laeuft

titel "3) Ollama ist weg: kein Sprachmodell-Server antwortet"
kill "$ATTRAPPE_PID" 2>/dev/null; wait "$ATTRAPPE_PID" 2>/dev/null
ATTRAPPE_PID=""
durchlauf ollama_weg
bewerten ollama_weg
pruefe "  und es steht da, dass kein Sprachmodell da ist" "ja" \
  "$(grep -qE 'Kein Sprachmodell-Server antwortet|dreimal nicht zu erreichen' \
     "$BASIS/lauf-ollama_weg.txt" && echo ja || echo nein)"

if [ "$FEHLER" != 0 ]; then
  printf '\n--- Lauf "ollama_weg", letzte Zeilen:\n'
  tail -n 25 "$BASIS/lauf-ollama_weg.txt"
fi

printf '\n'
if [ "$FEHLER" = 0 ]; then
  printf "${GRUEN}Alle Faelle wie erwartet.${AUS}\n"
else
  printf "${ROT}%d Fehler.${AUS}\n" "$FEHLER"
fi
exit "$FEHLER"
