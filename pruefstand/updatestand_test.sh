#!/usr/bin/env bash
# Steht der Grund eines gescheiterten Updates am Pult? (0.5.2)
#
#   bash pruefstand/updatestand_test.sh
#
# Bis 0.5.1 schrieb aktualisieren.sh -- der Weg fuer Fenster,
# Online-Knopf und Hand -- bei einem Fehlschlag nichts auf. Unter
# Einrichtung -> Update stand weiter "Fassung X ist eingespielt" vom
# letzten Mal; den Grund kannte nur, wer das Protokoll las.
#
# Jetzt landet er in update/stand-online.json, der Datei, die das Pult
# ohnehin liest (fehlerbericht.juengerer_stand):
#   1) vor der Uebergabe (Signatur, lokale Aenderungen): "nichts
#      geaendert", ohne "vorher"
#   2) nach der Uebergabe mit Ruecksprung: der Grund aus den
#      MELDUNG-Zeilen, "vorher" ist die wiederhergestellte Fassung
#   3) Ruecksprung gescheitert: eigene Lage
#   4) von Hand: zusaetzlich eine Meldung (meldung.sh), aber nicht,
#      wenn das Fenster aufruft (das meldet selbst)
#   5) der Stick-Kern: sein stand.json nach einem Ruecksprung
# Und dass Signatur und Ruecksprung dabei bleiben, was sie waren.
#
# Wie online_test.sh: das "origin" ist ein Ordner daneben, sudo,
# systemctl und runuser sind die Attrappen aus pruefstand/attrappen.

set -u
ECHT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="$ECHT/pruefstand/attrappen:$PATH"
BASIS="$(mktemp -d)"
FEHLER=0
trap 'rm -rf "$BASIS"' EXIT

pruefe() {
  if [ "$2" = "$3" ]; then printf '   ok    %s\n' "$1"
  else printf '   \033[31mFEHL\033[0m  %s: erwartet %s, ist %s\n' "$1" "$2" "$3"
       FEHLER=$((FEHLER+1)); fi
}
titel() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
feld() {  # $1 Datei, $2 Feld
  "$ECHT/.venv/bin/python" -c 'import json,sys
try: print(json.load(open(sys.argv[1])).get(sys.argv[2], ""))
except Exception as e: print("UNLESBAR", type(e).__name__)' "$1" "$2"
}

# ------------------------------------------------------- Schluessel
ECHTER="$BASIS/echt"; FREMD="$BASIS/fremd"
ssh-keygen -q -t ed25519 -N "" -C echt  -f "$ECHTER"
ssh-keygen -q -t ed25519 -N "" -C fremd -f "$FREMD"

# ------------------------------------------------------- das "origin"
FERN="$BASIS/fern"
mkdir -p "$FERN"; git -C "$FERN" init -q -b main
git -C "$FERN" config user.email pruef@pruefstand
git -C "$FERN" config user.name Pruefstand
git -C "$FERN" config commit.gpgsign false
git -C "$FERN" config gpg.format ssh
git -C "$FERN" config user.signingkey "$ECHTER.pub"

# Die Update-Logik in Kurzform: vorspulen, und scheitern, wenn eine
# Marke im Ordner es verlangt -- mit der MELDUNG, die auch die echte
# schreibt.
echo "0.9.0" > "$FERN/VERSION"
cat > "$FERN/aktualisierung.sh" <<'LOGIK'
#!/usr/bin/env bash
set -u
cd "$DEV_ORDNER"
git merge --ff-only --quiet "$DEV_REF^{commit}" || exit 1
if [ -f "$DEV_ORDNER/scheitern" ]; then
  echo "   FEHLT Der Rechner ist nach dem Update nicht gesund."
  echo "MELDUNG|Update $DEV_VERSION ist fehlgeschlagen."
  exit 1
fi
echo "MELDUNG|nichts"
LOGIK
git -C "$FERN" add -A >/dev/null
git -C "$FERN" commit -q -m 0.9.0
git -C "$FERN" tag -s v0.9.0 -m "Devarenu 0.9.0"
echo "0.9.1" > "$FERN/VERSION"
git -C "$FERN" add -A >/dev/null; git -C "$FERN" commit -q -m 0.9.1
git -C "$FERN" tag -s v0.9.1 -m "Devarenu 0.9.1"

neuer_rechner() {  # $1 Ordner
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
  # gesundheit.sh in Kurzform; GESUND=nein laesst den Check nach dem
  # Ruecksprung scheitern.
  cat > "$ziel/gesundheit.sh" <<'GES'
#!/usr/bin/env bash
set -u
if [ "${1:-}" = "--vorher" ]; then
  mkdir -p "$(dirname "${DEV_SICHERUNG:-/tmp}/befunde-vorher")" || exit 1
  echo "keine" > "${DEV_SICHERUNG:-/tmp}/befunde-vorher" || exit 1
  exit 0
fi
[ "${GESUND:-ja}" = ja ]
GES
  # meldung.sh als Attrappe: schreibt mit, was hinausginge.
  printf '#!/usr/bin/env bash\nprintf "%%s\\n---\\n" "$@" >> "%s/meldungen.log"\n' \
    "$ziel" > "$ziel/meldung.sh"
  printf '{"ntfy": "attrappe"}' > "$ziel/meldung.json"
  chmod 600 "$ziel/meldung.json"
  printf '{"wlan": {"ssid": "x"}}' > "$ziel/zustand.json"
  chmod 600 "$ziel/zustand.json"
  # Die Statusdateien liegen in update/, wie auf dem Gemeinderechner.
  mkdir -p "$ziel/update"
}

lauf() {  # $1 Ordner, Rest: zusaetzliche Umgebung
  local r="$1"; shift
  (cd "$r" && env DEVARENU_DATEN="$BASIS/daten" STUB_LOG="$BASIS/sysctl.log" \
     "$@" bash ./aktualisieren.sh 2>&1)
}
STAND() { echo "$1/update/stand-online.json"; }

# =====================================================================
titel "1) Vor der Uebergabe: Signatur fremd"
# Dasselbe Tag, aber vom fremden Schluessel unterschrieben -- VOR dem
# Klonen, sonst laege das echte schon hier, und fetch scheiterte am
# Ueberschreiben statt an der Signatur.
git -C "$FERN" tag -d v0.9.1 >/dev/null
git -C "$FERN" -c user.signingkey="$FREMD.pub" tag -s v0.9.1 -m "fremd" >/dev/null
R="$BASIS/r1"; neuer_rechner "$R"
AUS="$(lauf "$R")"; RC=$?
pruefe "Rueckgabe wie bisher 1" 1 "$RC"
pruefe "die Signatur wird wie bisher abgelehnt" ja \
  "$(printf '%s' "$AUS" | grep -q 'Die Signatur von v0.9.1 ist ungueltig' && echo ja || echo nein)"
pruefe "die Fassung blieb" 0.9.0 "$(cat "$R/VERSION")"
pruefe "der Stand steht da: fehlgeschlagen" fehlgeschlagen "$(feld "$(STAND "$R")" lage)"
pruefe "   fuer v0.9.1" 0.9.1 "$(feld "$(STAND "$R")" version)"
pruefe "   ohne vorher (nichts wurde angefasst)" "" "$(feld "$(STAND "$R")" vorher)"
pruefe "   mit dem Grund" ja \
  "$(feld "$(STAND "$R")" text | grep -q 'Signatur von v0.9.1 ist ungueltig' && echo ja || echo nein)"
pruefe "   und dem Satz, dass nichts geaendert wurde" ja \
  "$(feld "$(STAND "$R")" text | grep -q 'nichts geaendert' && echo ja || echo nein)"
pruefe "von Hand: eine Meldung ging hinaus" ja \
  "$(grep -q 'GESCHEITERT (von Hand)' "$R/meldungen.log" 2>/dev/null && echo ja || echo nein)"
# wieder richtig signieren
git -C "$FERN" tag -d v0.9.1 >/dev/null
git -C "$FERN" tag -s v0.9.1 -m "Devarenu 0.9.1" >/dev/null

titel "2) Vor der Uebergabe: lokale Aenderungen, aus dem Fenster"
R="$BASIS/r2"; neuer_rechner "$R"
echo "von Hand" >> "$R/VERSION"
AUS="$(lauf "$R" DEVARENU_UEBER_FENSTER=1)"; RC=$?
pruefe "Rueckgabe 1" 1 "$RC"
pruefe "der Stand nennt den Grund" ja \
  "$(feld "$(STAND "$R")" text | grep -q 'lokale Aenderungen' && echo ja || echo nein)"
pruefe "aus dem Fenster: keine zweite Meldung von hier" nein \
  "$([ -s "$R/meldungen.log" ] && echo ja || echo nein)"

titel "3) Nach der Uebergabe, mit Ruecksprung"
R="$BASIS/r3"; neuer_rechner "$R"
: > "$R/scheitern"
AUS="$(lauf "$R")"; RC=$?
pruefe "Rueckgabe 1" 1 "$RC"
pruefe "der Ruecksprung lief wie bisher" ja \
  "$(printf '%s' "$AUS" | grep -q 'zurueck auf 0.9.0, der Rechner ist gesund' && echo ja || echo nein)"
pruefe "die Fassung ist wieder 0.9.0" 0.9.0 "$(cat "$R/VERSION")"
pruefe "der Stand: fehlgeschlagen" fehlgeschlagen "$(feld "$(STAND "$R")" lage)"
pruefe "   vorher ist die wiederhergestellte Fassung" 0.9.0 "$(feld "$(STAND "$R")" vorher)"
pruefe "   der Grund aus der Update-Logik (MELDUNG)" ja \
  "$(feld "$(STAND "$R")" text | grep -q 'Update 0.9.1 ist fehlgeschlagen' && echo ja || echo nein)"
pruefe "   und dass die alte Fassung laeuft" ja \
  "$(feld "$(STAND "$R")" text | grep -q 'Fassung 0.9.0 wurde wiederhergestellt' && echo ja || echo nein)"
pruefe "das Pult liest genau diesen Stand" fehlgeschlagen \
  "$("$ECHT/.venv/bin/python" -c 'import sys; sys.path.insert(0, sys.argv[1])
import fehlerbericht; print(fehlerbericht.juengerer_stand(sys.argv[2]).get("lage"))' \
     "$ECHT" "$R/update")"

titel "4) Der Ruecksprung scheitert auch"
R="$BASIS/r4"; neuer_rechner "$R"
: > "$R/scheitern"
AUS="$(lauf "$R" GESUND=nein)"; RC=$?
pruefe "Rueckgabe 1" 1 "$RC"
pruefe "die Lage sagt es" rueckweg_gescheitert "$(feld "$(STAND "$R")" lage)"
pruefe "   und der Text" ja \
  "$(feld "$(STAND "$R")" text | grep -q 'Ruecksprung auf 0.9.0 ist ebenfalls gescheitert' && echo ja || echo nein)"

titel "5) Gelungen, von Hand: Meldung, kein Fehlerstand"
R="$BASIS/r5"; neuer_rechner "$R"
AUS="$(lauf "$R")"; RC=$?
pruefe "Rueckgabe 0" 0 "$RC"
pruefe "Fassung 0.9.1" 0.9.1 "$(cat "$R/VERSION")"
pruefe "kein Fehlerstand von hier" nein \
  "$([ -f "$(STAND "$R")" ] && echo ja || echo nein)"
pruefe "eine Meldung 'eingespielt' ging hinaus" ja \
  "$(grep -q 'eingespielt (von Hand)' "$R/meldungen.log" 2>/dev/null && echo ja || echo nein)"
R="$BASIS/r5b"; neuer_rechner "$R"
AUS="$(lauf "$R" DEVARENU_UEBER_FENSTER=1)"
pruefe "aus dem Fenster gelungen: keine Meldung von hier" nein \
  "$([ -s "$R/meldungen.log" ] && echo ja || echo nein)"
R="$BASIS/r5c"; neuer_rechner "$R"; rm -f "$R/meldung.sh"
AUS="$(lauf "$R")"; RC=$?
pruefe "ohne meldung.sh: laeuft trotzdem durch" 0 "$RC"

titel "6) Das Fenster ruft mit DEVARENU_UEBER_FENSTER auf"
# Seit dem 28.10.2026 gibt es in update_kern nur noch EINEN Aufruf
# (als root; der runuser-Zweig ist weg, fenster_wurzel_test.sh). Gefragt
# wird darum: jeder Aufruf von aktualisieren.sh in update_kern traegt
# die Variable.
KERN="$(sed -n '/^update_kern() {/,/^}/p' "$ECHT/wartungsfenster.sh" | grep -v '^\s*#')"
pruefe "jeder Aufruf von aktualisieren.sh in update_kern setzt die Variable" \
  "$(printf '%s\n' "$KERN" | grep -c 'aktualisieren.sh')" \
  "$(printf '%s\n' "$KERN" | grep -c 'DEVARENU_UEBER_FENSTER=1')"

# =====================================================================
titel "7) Der Stick-Kern: Ruecksprung steht in stand.json"
# Der echte Kern, die echte Logik, ein Neustart, der scheitert -- wie
# updater_test.sh Fall 4, aber ueber den ganzen Kern.
R="$BASIS/r7"; mkdir -p "$R"
git -C "$R" init -q .
git -C "$R" config user.email t@t; git -C "$R" config user.name t
cp "$ECHT/stick_update.sh" "$ECHT/aktualisierung.sh" "$ECHT/gesundheit.sh" \
   "$ECHT/stick.udev.vorlage" "$R/"
echo "0.4.0" > "$R/VERSION"; echo "fastapi" > "$R/requirements.txt"
mkdir -p "$R/.venv/bin"; ln -sf "$(command -v python3)" "$R/.venv/bin/python"
git -C "$R" add -A >/dev/null; git -C "$R" commit -q -m 0.4.0
ALT="$(git -C "$R" rev-parse HEAD)"
echo "0.4.1" > "$R/VERSION"
git -C "$R" add -A >/dev/null; git -C "$R" commit -q -m 0.4.1
git -C "$R" tag v0.4.1
git -C "$R" update-ref refs/stick/v0.4.1 "$(git -C "$R" rev-parse v0.4.1)"
git -C "$R" reset -q --hard "$ALT"
mkdir -p "$R/update"; echo "0.4.1" > "$R/update/bereit"; : > "$R/update/jetzt"
AUS7="$(cd "$R" && STUB_FASSUNG=0.4.0 STUB_RESTART_OK=nein STUB_LOG="$BASIS/s7.log" \
        DEVARENU_DATEN="$BASIS/daten7" DEVARENU_UNIT_ORDNER="$BASIS/units7" \
        DEVARENU_UDEV_REGEL="$BASIS/udev7.rules" \
        bash "$R/stick_update.sh" --einspielen 2>&1)" || true
pruefe "die Fassung ist wieder 0.4.0" 0.4.0 "$(cat "$R/VERSION")"
pruefe "stand.json: fehlgeschlagen" fehlgeschlagen "$(feld "$R/update/stand.json" lage)"
pruefe "   vorher 0.4.0" 0.4.0 "$(feld "$R/update/stand.json" vorher)"
pruefe "   mit dem Grund aus der Logik" ja \
  "$(feld "$R/update/stand.json" text | grep -q 'Dienst liess sich' && echo ja || echo nein)"

printf '\n'
[ "$FEHLER" = 0 ] || { printf '\033[31m%s Fehler.\033[0m\n' "$FEHLER"; exit 1; }
printf '\033[32mAlle Faelle wie erwartet.\033[0m\n'
