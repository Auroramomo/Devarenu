#!/usr/bin/env bash
# Der Handlauf von v0.5.1 auf diese Fassung: kommen die neuen Units mit,
# und sagt das Ende, ob uebersetzt wird?
#
#   bash pruefstand/update_handlauf_test.sh > .tmp/handlauf.txt 2>&1
#
# WAS GEPRUEFT WIRD
#
# 1. Die Units. Auf einem Gemeinderechner stehen die Units von v0.5.1 in
#    /etc/systemd/system. Der Kern von v0.5.1 uebergibt an die
#    aktualisierung.sh DIESES Stands, und die muss sie durch die neuen
#    Vorlagen ersetzen -- sonst gelten die neuen Zeitgrenzen
#    (update_zeitgrenzen_test.sh) erst nach dem naechsten dienst.sh von
#    Hand, also nie.
# 2. Die Zeile "Übersetzung: ..." am Ende von aktualisierung.sh, je nach
#    Sprachmodell-Server: llama-server bereit, Ollama bereit, keiner.
# 3. Der Kern dieses Stands (fuer das naechste Update) wiederholt sie
#    direkt vor "Alles bereit".
#
# WAS ECHT IST UND WAS NICHT
#
# Echt: aktualisieren.sh aus v0.5.1 bzw. aus diesem Stand,
# aktualisierung.sh, gesundheit.sh, systemcheck.py, llama_einrichten.py,
# sprachmodell.py und der Sprachmodell-Teil des Selbsttests. sudo,
# systemctl, curl, nvidia-smi sind Attrappen wie in einspielweg_test.sh;
# Piper und Whisper im Selbsttest auch. Ollama und llama-server sind die
# Attrappen aus pruefstand/attrappen auf freien Ports -- das echte
# Ollama und der llama-server dieses Rechners werden nie gefragt.

set -u
ECHT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$ECHT/.tmp"
BASIS="$(mktemp -d "$ECHT/.tmp/handlauf-XXXXXX")"
export PATH="$ECHT/pruefstand/attrappen:$PATH"
START=v0.5.1
NIRGENDS="http://127.0.0.1:9"
NEU="$(tr -d '[:space:]' < "$ECHT/VERSION")"
DANACH="9.9.9"

GRUEN="\033[32m"; ROT="\033[31m"; AUS="\033[0m"
FEHLER=0
PIDS=""

aufraeumen() {
  [ -n "$PIDS" ] && kill $PIDS 2>/dev/null
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
farblos() { sed 's/\x1b\[[0-9;]*m//g' "$@"; }

attrappe() {  # $1 ollama|llama-server -> Adresse auf der Standardausgabe
  local aus="$BASIS/attrappe-$1.txt"
  python3 -c '
import sys, time
sys.path.insert(0, sys.argv[1])
import ollama_attrappe as a
print("ADRESSE", a.starten(sys.argv[2]), flush=True)
time.sleep(86400)' "$ECHT/pruefstand/attrappen" "$1" > "$aus" &
  PIDS="$PIDS $!"
  for _ in $(seq 1 50); do
    grep -q '^ADRESSE ' "$aus" 2>/dev/null && break
    sleep 0.1
  done
  awk '/^ADRESSE /{print $2}' "$aus"
}

titel "0) Vorbedingungen"
git -C "$ECHT" rev-parse -q --verify "refs/tags/$START" >/dev/null \
  || { printf "   ${ROT}!${AUS}     das Tag %s fehlt\n" "$START"; exit 1; }
git -C "$ECHT" worktree add -q --detach "$BASIS/baum-$START" "$START" 2>/dev/null \
  || { printf "   ${ROT}FEHL${AUS}  worktree fuer %s ging nicht\n" "$START"; exit 1; }
OLLAMA="$(attrappe ollama)"
LLAMA="$(attrappe llama-server)"
pruefe "die Attrappen laufen" "ja" \
  "$([ -n "$OLLAMA" ] && [ -n "$LLAMA" ] && echo ja || echo nein)"

SCHLUESSEL="$BASIS/freigabe"
ssh-keygen -q -t ed25519 -N "" -C pruefstand -f "$SCHLUESSEL"

fern_anlegen() {  # $1 Ordner
  mkdir -p "$1"
  git -C "$1" init -q -b main
  git -C "$1" config user.email pruef@pruefstand
  git -C "$1" config user.name Pruefstand
  git -C "$1" config gpg.format ssh
  git -C "$1" config user.signingkey "$SCHLUESSEL.pub"
  git -C "$1" config commit.gpgsign false
}

baum_hinein() {  # $1 Fernrepo, $2 Quellordner, $3 Fassung, $4 Tag
  local fern="$1"
  find "$fern" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
  ( cd "$2" && git ls-files -z | tar --null -cf - -T - ) | tar -xf - -C "$fern"
  echo "pruef@pruefstand $(cat "$SCHLUESSEL.pub")" > "$fern/schluessel.erlaubt"
  printf '%s\n' "$3" > "$fern/VERSION"
  # Ollama erreicht dieser Stand ueber die Attrappe; ob sie antwortet,
  # entscheidet der Fall. llama-server lenkt DEVARENU_LLAMA_URL.
  sed -i -e "s|^OLLAMA_URL = .*|OLLAMA_URL = \"$OLLAMA\"|" \
         -e "s|^LLAMA_URL = .*|LLAMA_URL = \"$NIRGENDS\"|" "$fern/config.py"
  if [ -f "$fern/selbsttest.py" ]; then
    mv "$fern/selbsttest.py" "$fern/selbsttest_echt.py"
    printf '%s\n' \
      '#!/usr/bin/env python3' \
      'import sys' \
      'sys.path.insert(0, ".")' \
      'import selbsttest_echt as s' \
      's.pruefe_piper = lambda ziel: (s.ok("Piper (Attrappe)"), False)[1]' \
      's.pruefe_whisper = lambda quelle: s.ok("Whisper (Attrappe)")' \
      'sys.exit(s.main())' > "$fern/selbsttest.py"
  fi
  git -C "$fern" add -A >/dev/null 2>&1
  git -C "$fern" commit -q -m "$3" >/dev/null 2>&1
  git -C "$fern" tag -s "$4" -m "Devarenu $3" >/dev/null 2>&1
}

# Die Units, wie dienst.sh sie aus den Vorlagen eines Stands schreibt.
UNITS="devarenu.service devarenu-stick@.service devarenu-update.service \
devarenu-update.timer devarenu-fenster.service devarenu-fenster.timer \
devarenu-fenster-wecker.service devarenu-onlineupdate.service \
devarenu-onlineupdate.timer"
units_schreiben() {  # $1 Vorlagenordner, $2 Unit-Ordner, $3 Projektordner
  mkdir -p "$2"
  local u
  for u in $UNITS; do
    sed -e "s|@ORDNER@|$3|g" -e "s|@BENUTZER@|$(id -un)|g" \
        -e "s|@PORT@|8000|g" "$1/$u.vorlage" > "$2/$u"
  done
}

FERN="$BASIS/fern"
fern_anlegen "$FERN"
baum_hinein "$FERN" "$BASIS/baum-$START" "${START#v}" "$START"
baum_hinein "$FERN" "$ECHT" "$NEU" "v$NEU"
FERN_NEU="$BASIS/fern-neu"
fern_anlegen "$FERN_NEU"
baum_hinein "$FERN_NEU" "$ECHT" "$NEU" "v$NEU"
baum_hinein "$FERN_NEU" "$ECHT" "$DANACH" "v$DANACH"

# $1 Fall, $2 Fernrepo, $3 Start-Tag, $4 erwartete Fassung,
# $5 llama-server an (ja|nein)
durchlauf() {
  local fall="$1" fern="$2" start="$3" ziel="$BASIS/rechner-$1" d="$BASIS/daten-$1"
  git clone -q "$fern" "$ziel"
  git -C "$ziel" config user.email pruef@pruefstand
  git -C "$ziel" config user.name Pruefstand
  git -C "$ziel" -c advice.detachedHead=false checkout -q "$start"
  git -C "$ziel" branch -f main "$start" >/dev/null
  git -C "$ziel" checkout -q main
  git -C "$ziel" branch --set-upstream-to=origin/main main >/dev/null
  printf '{"fassung": 3, "quelle": "de", "ziele": ["en", "ru", "fa"]}\n' \
    > "$ziel/zustand.json"
  chmod 600 "$ziel/zustand.json"
  printf '{"router": false}\n' > "$ziel/netz.json"
  mkdir -p "$ziel/.venv/bin"
  ln -sf "$(command -v python3)" "$ziel/.venv/bin/python"
  mkdir -p "$d" "$BASIS/home-$fall/.config"; chmod 711 "$d"
  # Die Units des Startstands, wie auf dem Gemeinderechner.
  units_schreiben "$ziel" "$BASIS/units-$fall" "$(cd "$ziel" && pwd)"
  # Ollama "aus" steckt im Fernrepo (config.py des Tags, FERN_OHNE),
  # llama-server "an" in der Umgebung, die die sudo-Attrappe durchreicht.
  local llama_url="$NIRGENDS"
  [ "$5" = ja ] && llama_url="$LLAMA"
  ( cd "$ziel" && setsid env HOME="$BASIS/home-$fall" \
      XDG_CONFIG_HOME="$BASIS/home-$fall/.config" \
      DEVARENU_DATEN="$d" \
      DEVARENU_UNIT_ORDNER="$BASIS/units-$fall" \
      DEVARENU_UDEV_REGEL="$BASIS/udev-$fall.rules" \
      STUB_LOG="$BASIS/stub-$fall.log" \
      STUB_FASSUNG="$4" \
      DEVARENU_KEIN_NETZ=1 \
      DEVARENU_LLAMA_OHNE_ROOT=1 \
      DEVARENU_LLAMA_OPT="$BASIS/opt-$fall" \
      DEVARENU_LLAMA_URL="$llama_url" \
      bash ./aktualisieren.sh 2>&1 ) > "$BASIS/lauf-$fall.txt"
  farblos "$BASIS/lauf-$fall.txt" > "$BASIS/lauf-$fall.klar"
}

zeile() {  # $1 Fall -> die letzte "Übersetzung: "-Zeile, ohne Einzug
  grep -a 'Übersetzung: ' "$BASIS/lauf-$1.klar" | tail -1 | sed 's/^ *//'
}

# Ollama "aus" geht nur ueber config.py des neuen Stands -- die Adresse
# steht dort fest. Also ein zweites Tag ohne Ollama.
FERN_OHNE="$BASIS/fern-ohne-ollama"
fern_anlegen "$FERN_OHNE"
OLLAMA_MERK="$OLLAMA"
baum_hinein "$FERN_OHNE" "$BASIS/baum-$START" "${START#v}" "$START"
OLLAMA="$NIRGENDS"
baum_hinein "$FERN_OHNE" "$ECHT" "$NEU" "v$NEU"
OLLAMA="$OLLAMA_MERK"

titel "1) $START -> $NEU, Ollama laeuft: die Units kommen mit"
durchlauf ollama "$FERN" "$START" "$NEU" nein
ZIEL="$BASIS/rechner-ollama"
pruefe "die Fassung steht auf $NEU" "$NEU" "$(tr -d '[:space:]' < "$ZIEL/VERSION")"
for u in devarenu-fenster.service devarenu-onlineupdate.service \
         devarenu-update.service devarenu-stick@.service; do
  pruefe "$u: aus der neuen Vorlage geschrieben" "infinity" \
    "$(sed -n 's/^TimeoutStartSec=//p' "$BASIS/units-ollama/$u" | tail -1)"
done
pruefe "alle Units gleich der neuen Vorlage" "" \
  "$(for u in $UNITS; do
       sed -e "s|@ORDNER@|$(cd "$ZIEL" && pwd)|g" -e "s|@BENUTZER@|$(id -un)|g" \
           -e "s|@PORT@|8000|g" "$ZIEL/$u.vorlage" \
         | cmp -s - "$BASIS/units-ollama/$u" || printf '%s ' "$u"
     done)"
pruefe "systemd wurde neu geladen" "ja" \
  "$(grep -q 'daemon-reload' "$BASIS/stub-ollama.log" && echo ja || echo nein)"
pruefe "die Zeile sagt Ollama" "Übersetzung: bereit über Ollama" "$(zeile ollama)"

titel "2) $START -> $NEU, llama-server laeuft"
durchlauf llama "$FERN" "$START" "$NEU" ja
pruefe "die Zeile sagt llama-server" "Übersetzung: bereit über llama-server" \
  "$(zeile llama)"

titel "3) $START -> $NEU, kein Sprachmodell-Server"
durchlauf keiner "$FERN_OHNE" "$START" "$NEU" nein
pruefe "die Fassung steht auf $NEU" "$NEU" \
  "$(tr -d '[:space:]' < "$BASIS/rechner-keiner/VERSION")"
pruefe "die Zeile sagt NICHT bereit und warum" "ja" \
  "$(zeile keiner | grep -q '^Übersetzung: NICHT bereit – Kein Sprachmodell-Server antwortet' \
     && echo ja || echo nein)"
pruefe "  und warum llama-server nicht kam" "ja" \
  "$(zeile keiner | grep -q 'llama-server: kein Internet' && echo ja || echo nein)"
pruefe "  rot" "ja" \
  "$(grep -a 'Übersetzung: ' "$BASIS/lauf-keiner.txt" | tail -1 \
     | grep -q $'\033\[31m' && echo ja || echo nein)"
pruefe "  ohne den Schluss 'Es uebersetzt weiter'" "nein" \
  "$(zeile keiner | grep -q 'Es uebersetzt weiter' && echo ja || echo nein)"

titel "4) $NEU -> $DANACH: der Kern dieses Stands"
durchlauf kern "$FERN_NEU" "v$NEU" "$DANACH" nein
pruefe "die Fassung steht auf $DANACH" "$DANACH" \
  "$(tr -d '[:space:]' < "$BASIS/rechner-kern/VERSION")"
pruefe "direkt vor 'Alles bereit' steht die Zeile" \
  "Übersetzung: bereit über Ollama" \
  "$(grep -a -B1 'Alles bereit' "$BASIS/lauf-kern.klar" | head -1 | sed 's/^ *//')"

if [ "$FEHLER" != 0 ]; then
  for f in ollama llama keiner kern; do
    [ -f "$BASIS/lauf-$f.klar" ] || continue
    printf '\n--- Lauf "%s", letzte Zeilen:\n' "$f"
    tail -n 15 "$BASIS/lauf-$f.klar"
  done
fi

printf '\n'
if [ "$FEHLER" = 0 ]; then
  printf "${GRUEN}Alle Faelle wie erwartet.${AUS}\n"
else
  printf "${ROT}%d Fehler.${AUS}\n" "$FEHLER"
fi
exit "$FEHLER"
