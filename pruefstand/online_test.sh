#!/usr/bin/env bash
# Spielt aktualisieren.sh nur signierte Tags ein -- und nichts anderes?
#
#   bash pruefstand/online_test.sh
#
# Bis 0.3.1 stand in aktualisieren.sh "git pull --ff-only": es galt,
# worauf origin/main gerade zeigte. Keine Signatur, kein Tag, keine
# Pruefung. Wer den Server oder die Leitung beherrschte, bestimmte
# damit, was auf dem Gemeinderechner lief -- ueber den Stick war genau
# das seit 0.2.12 unmoeglich.
#
# Dieser Lauf prueft die vier Faelle, die zusammen die Regel ergeben:
# ein gueltiges Tag geht durch, ein fremd signiertes nicht, ein
# nachtraeglich umgebogenes nicht, und ein main, das weiter ist als
# das letzte Tag, zaehlt nicht.
#
# Kein Netz noetig: das "origin" ist ein Ordner daneben.

set -u
ECHT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="$ECHT/pruefstand/attrappen:$PATH"
BASIS="$(mktemp -d)"
FEHLER=0
trap 'rm -rf "$BASIS"' EXIT

pruefe() {
  if [ "$2" = "$3" ]; then
    printf '   ok    %s\n' "$1"
  else
    printf '   \033[31mFEHL\033[0m  %s: erwartet %s, ist %s\n' "$1" "$2" "$3"
    FEHLER=$((FEHLER+1))
  fi
}
titel() { printf '\n\033[1m== %s\033[0m\n' "$*"; }

# ------------------------------------------------------- Schluessel
ECHTER="$BASIS/echt"; FREMD="$BASIS/fremd"
ssh-keygen -q -t ed25519 -N "" -C echt  -f "$ECHTER"
ssh-keygen -q -t ed25519 -N "" -C fremd -f "$FREMD"

# ------------------------------------------------------- das "origin"
# Ein gewoehnliches Repo, kein bare: es muss Tags signieren koennen.
FERN="$BASIS/fern"
mkdir -p "$FERN"; git -C "$FERN" init -q -b main
git -C "$FERN" config user.email pruef@pruefstand
git -C "$FERN" config user.name Pruefstand
git -C "$FERN" config commit.gpgsign false
git -C "$FERN" config gpg.format ssh
git -C "$FERN" config user.signingkey "$ECHTER.pub"

# Eine Fassung, die nur so viel kann, wie dieser Lauf braucht. Die
# echte aktualisierung.sh laesst sich hier nicht gebrauchen -- sie
# baut venvs und startet Dienste.
echo "0.9.0" > "$FERN/VERSION"
cat > "$FERN/aktualisierung.sh" <<'LOGIK'
#!/usr/bin/env bash
# Kurzfassung fuer den Pruefstand: vorspulen und mitschreiben, dass
# man ueberhaupt aufgerufen wurde -- samt der Fassung.
set -u
cd "$DEV_ORDNER"
git merge --ff-only --quiet "$DEV_REF^{commit}" || exit 1
echo "LOGIK-LIEF $DEV_VERSION" >> "$DEV_ORDNER/logik.log"
echo "MELDUNG|nichts"
LOGIK
git -C "$FERN" add -A >/dev/null
git -C "$FERN" commit -q -m 0.9.0
git -C "$FERN" tag -s v0.9.0 -m "Devarenu 0.9.0"

echo "0.9.1" > "$FERN/VERSION"; echo neu > "$FERN/dazu.txt"
git -C "$FERN" add -A >/dev/null; git -C "$FERN" commit -q -m 0.9.1
git -C "$FERN" tag -s v0.9.1 -m "Devarenu 0.9.1"
V091="$(git -C "$FERN" rev-parse v0.9.1^{commit})"

# --------------------------------------------------- der Gemeinderechner
neuer_rechner() {
  local ziel="$1"
  rm -rf "$ziel"
  git clone -q "$FERN" "$ziel"
  git -C "$ziel" config user.email pruef@pruefstand
  git -C "$ziel" config user.name Pruefstand
  git -C "$ziel" config commit.gpgsign false
  git -C "$ziel" -c advice.detachedHead=false checkout -q v0.9.0
  git -C "$ziel" branch -f main v0.9.0 >/dev/null
  git -C "$ziel" checkout -q main
  git -C "$ziel" branch --set-upstream-to=origin/main main >/dev/null 2>&1
  echo "pruef@pruefstand $(cat "$ECHTER.pub")" > "$ziel/schluessel.erlaubt"
  cp "$ECHT/aktualisieren.sh" "$ziel/"
  printf '{"wlan": {"ssid": "x"}}' > "$ziel/zustand.json"
  chmod 600 "$ziel/zustand.json"
}

lauf() {
  (cd "$1" && DEVARENU_DATEN="$BASIS/daten" STUB_LOG="$BASIS/sysctl.log" \
     bash ./aktualisieren.sh 2>&1)
}

titel "1) Ein richtig signiertes Tag geht durch"
R="$BASIS/r1"; neuer_rechner "$R"
AUS="$(lauf "$R")" || true
pruefe "Signatur wird angenommen" "ja" \
  "$(printf '%s' "$AUS" | grep -q 'Signatur von v0.9.1 ist gueltig' && echo ja || echo nein)"
pruefe "die Fassung steht auf 0.9.1" "0.9.1" "$(cat "$R/VERSION")"
pruefe "die versionierte Logik lief" "LOGIK-LIEF 0.9.1" \
  "$(cat "$R/logik.log" 2>/dev/null)"
pruefe "der Zweig ist nicht abgeloest" "main" \
  "$(git -C "$R" rev-parse --abbrev-ref HEAD)"
pruefe "die Hilfsreferenz ist wieder weg" "" \
  "$(git -C "$R" rev-parse -q --verify refs/online/v0.9.1 2>/dev/null || true)"
pruefe "der Auszug liegt nicht mehr herum" "nein" \
  "$([ -d "$BASIS/daten/logik-0.9.1" ] && echo ja || echo nein)"

titel "2) Ein fremd signiertes Tag nicht"
# Dasselbe Repo, dasselbe Tag -- nur mit einem Schluessel signiert,
# der nicht in schluessel.erlaubt steht.
git -C "$FERN" tag -d v0.9.1 >/dev/null
git -C "$FERN" config user.signingkey "$FREMD.pub"
git -C "$FERN" tag -s v0.9.1 -m "Devarenu 0.9.1"
R2="$BASIS/r2"; neuer_rechner "$R2"
VOR2="$(git -C "$R2" rev-parse HEAD)"
AUS2="$(lauf "$R2")" || true
pruefe "die Signatur wird abgelehnt" "ja" \
  "$(printf '%s' "$AUS2" | grep -q 'Signatur von v0.9.1 ist ungueltig' && echo ja || echo nein)"
pruefe "die Fassung blieb auf 0.9.0" "0.9.0" "$(cat "$R2/VERSION")"
pruefe "der Stand blieb unangetastet" "$VOR2" "$(git -C "$R2" rev-parse HEAD)"
pruefe "die Logik lief gar nicht" "nein" \
  "$([ -f "$R2/logik.log" ] && echo ja || echo nein)"
# Der wichtigste Satz dieses Falles: die eigene Liste bleibt die eigene.
pruefe "die Schluesselliste ist unveraendert" "ja" \
  "$(grep -q "$(awk '{print $2}' "$ECHTER.pub")" "$R2/schluessel.erlaubt" \
     && echo ja || echo nein)"
pruefe "der fremde Schluessel steht nicht darin" "nein" \
  "$(grep -q "$(awk '{print $2}' "$FREMD.pub")" "$R2/schluessel.erlaubt" \
     && echo ja || echo nein)"

titel "3) Ein Tag, das auf etwas anderes umgebogen wurde"
# Das Tag ist echt signiert -- aber es zeigt inzwischen auf einen
# Commit, der nie unterschrieben wurde. git verify-tag prueft das
# Tag-Objekt; zeigt dieses woandershin, ist es ein anderes Tag und
# die Signatur passt nicht mehr.
git -C "$FERN" config user.signingkey "$ECHTER.pub"
git -C "$FERN" tag -d v0.9.1 >/dev/null
git -C "$FERN" tag -s v0.9.1 -m "Devarenu 0.9.1"
echo "geschmuggelt" > "$FERN/schmuggel.txt"
git -C "$FERN" add -A >/dev/null; git -C "$FERN" commit -q -m schmuggel
SCHMUGGEL="$(git -C "$FERN" rev-parse HEAD)"
# Das signierte Tag-Objekt bleibt, aber die Referenz zeigt daneben.
git -C "$FERN" update-ref refs/tags/v0.9.1 "$SCHMUGGEL"
R3="$BASIS/r3"; neuer_rechner "$R3"
AUS3="$(lauf "$R3")" || true
pruefe "nichts Ungeprueftes kommt durch" "nein" \
  "$([ -f "$R3/schmuggel.txt" ] && echo ja || echo nein)"
pruefe "die Fassung blieb auf 0.9.0" "0.9.0" "$(cat "$R3/VERSION")"

titel "4) main ist weiter als das letzte Tag"
# Der Fall, den der alte Weg falsch machte: git pull --ff-only haette
# den Rechner auf main gezogen, Tag hin oder her.
# Erst wieder ein echtes, signiertes Tag-Objekt auf 0.9.1 -- der Fall
# oben hat die Referenz auf einen blossen Commit gebogen, und ohne
# diese Zeile pruefte der naechste Fall nur noch denselben Schaden.
git -C "$FERN" tag -d v0.9.1 >/dev/null
git -C "$FERN" tag -s v0.9.1 -m "Devarenu 0.9.1" "$V091"
echo "ungetaggt" > "$FERN/spaeter.txt"
git -C "$FERN" add -A >/dev/null; git -C "$FERN" commit -q -m spaeter
R4="$BASIS/r4"; neuer_rechner "$R4"
AUS4="$(lauf "$R4")" || true
pruefe "auf 0.9.1 wird vorgespult" "0.9.1" "$(cat "$R4/VERSION")"
pruefe "aber nicht auf das, was hinter dem Tag liegt" "nein" \
  "$([ -f "$R4/spaeter.txt" ] && echo ja || echo nein)"

titel "5) Was sich nicht vorspulen laesst"
R5="$BASIS/r5"; neuer_rechner "$R5"
# Eine lokale Aenderung an einer versionierten Datei.
echo "vor Ort geaendert" >> "$R5/VERSION"
AUS5="$(lauf "$R5")" || true
pruefe "lokale Aenderungen halten das Update an" "ja" \
  "$(printf '%s' "$AUS5" | grep -q 'lokale Aenderungen' && echo ja || echo nein)"
pruefe "und die Aenderung steht noch da" "ja" \
  "$(grep -q 'vor Ort geaendert' "$R5/VERSION" && echo ja || echo nein)"

titel "6) Nichts Neues da"
R6="$BASIS/r6"; neuer_rechner "$R6"
lauf "$R6" >/dev/null 2>&1 || true      # auf 0.9.1 bringen
AUS6="$(lauf "$R6")" || true
pruefe "der zweite Lauf sagt es und tut nichts" "ja" \
  "$(printf '%s' "$AUS6" | grep -q 'kein neueres Tag' && echo ja || echo nein)"
pruefe "die Logik lief nur einmal" "1" \
  "$(grep -c LOGIK-LIEF "$R6/logik.log" 2>/dev/null || echo 0)"

printf '\n'
if [ "$FEHLER" = 0 ]; then
  printf '\033[32mAlle Faelle wie erwartet.\033[0m\n'
else
  printf '\033[31m%d Fehler.\033[0m\n' "$FEHLER"
fi
exit "$FEHLER"
