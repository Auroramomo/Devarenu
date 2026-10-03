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
# Der neue Dienst schreibt beim ersten Start in zustand.json. Was
# genau, sagt eine unversionierte Marke im Ordner -- sie ueberlebt
# das Vorspulen, weil git sie nicht kennt.
if [ -f "$DEV_ORDNER/zustand-tut" ]; then
  python3 - "$DEV_ORDNER" "$(cat "$DEV_ORDNER/zustand-tut")" <<'ZUS'
import json, sys, time
from pathlib import Path
d = Path(sys.argv[1]) / "zustand.json"
z = json.loads(d.read_text())
if sys.argv[2] == "wachsen":
    z["gemeinde"] = ""
    z["nutzung_melden"] = False
    z["aufnahme_frist_ab"] = time.time()
else:
    z["mikro"] = 7
d.write_text(json.dumps(z))
ZUS
fi
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
  # Eine Kurzfassung von gesundheit.sh. Die echte braucht ein venv
  # und einen laufenden Dienst; hier geht es um den Updater. Die
  # ECHTE laeuft in Fall 7 mit -- und genau dort ist aufgefallen,
  # dass ihr die Grundlinie fehlte.
  #
  # --vorher schreibt wirklich etwas: seit 0.3.5 bricht der Updater
  # ab, wenn die Grundlinie nicht entsteht, und das ist der Sinn.
  cat > "$ziel/gesundheit.sh" <<'GES'
#!/usr/bin/env bash
set -u
if [ "${1:-}" = "--vorher" ]; then
  mkdir -p "$(dirname "${DEV_SICHERUNG:-/tmp}/befunde-vorher")" || exit 1
  echo "keine" > "${DEV_SICHERUNG:-/tmp}/befunde-vorher" || exit 1
  exit 0
fi
exit 0
GES
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

titel "1b) zustand.json: Zuwachs ist kein Befund"
# Nach 0.3.4 -> 0.3.7 meldete der Updater "FEHLT zustand.json hat
# sich geaendert", weil der neue Dienst beim ersten Start "gemeinde"
# und "nutzung_melden" angelegt und "aufnahme_frist_ab" von 0 auf
# einen Zeitstempel gesetzt hatte. Genau dafuer ist das Feld da. Eine
# Warnung, die bei jedem Update falsch anschlaegt, liest niemand mehr
# -- und dann wird auch die richtige uebersehen.
R1B="$BASIS/r1b"; neuer_rechner "$R1B"
cat > "$R1B/zustand.json" <<'ZJ'
{"wlan": {"ssid": "x"}, "aufnahme_frist_ab": 0, "mikro": 1,
 "protokoll_mitschrift": false}
ZJ
chmod 600 "$R1B/zustand.json"
echo wachsen > "$R1B/zustand-tut"
AUS1B="$(lauf "$R1B")" || true
pruefe "kein FEHLT wegen zustand.json" "nein" \
  "$(printf '%s' "$AUS1B" | grep -q 'zustand.json hat sich geaendert' \
     && echo ja || echo nein)"
pruefe "der Zuwachs wird als solcher gemeldet" "ja" \
  "$(printf '%s' "$AUS1B" | grep -q 'nur Zuwachs' && echo ja || echo nein)"
pruefe "und die neuen Schluessel stehen namentlich da" "ja" \
  "$(printf '%s' "$AUS1B" | grep -q 'gemeinde, nutzung_melden' \
     && echo ja || echo nein)"
pruefe "aufnahme_frist_ab gilt als erstmals gefuellt" "ja" \
  "$(printf '%s' "$AUS1B" | grep -q 'erstmals gefuellt: *aufnahme_frist_ab' \
     && echo ja || echo nein)"

# Die Gegenprobe: ein GEAENDERTER Wert bleibt ein Befund. Ohne sie
# waere die Lockerung eine Abschaltung.
R1C="$BASIS/r1c"; neuer_rechner "$R1C"
cat > "$R1C/zustand.json" <<'ZJ'
{"wlan": {"ssid": "x"}, "mikro": 1}
ZJ
chmod 600 "$R1C/zustand.json"
echo aendern > "$R1C/zustand-tut"
AUS1C="$(lauf "$R1C")" || true
pruefe "ein geaenderter Wert bleibt ein Befund" "ja" \
  "$(printf '%s' "$AUS1C" | grep -q 'zustand.json hat sich geaendert' \
     && echo ja || echo nein)"
pruefe "und der Schluessel wird genannt" "ja" \
  "$(printf '%s' "$AUS1C" | grep -q 'geaenderte Werte: *mikro' \
     && echo ja || echo nein)"

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

titel "7) Gegen die ECHTE aktualisierung.sh, ohne DEV_SICHERUNG"
# WARUM ES DIESEN FALL GIBT
#
# Die Faelle oben rufen eine Attrappe statt der echten Logik auf --
# und genau deshalb waren sie gruen, waehrend der Online-Weg in
# Wirklichkeit gar nicht lief: aktualisierung.sh verlangte
# DEV_SICHERUNG mit ${...:?fehlt}, aktualisieren.sh uebergab es bis
# 0.3.2 nicht, und das Skript brach in Zeile 61 ab. Vor dem
# Vorspulen, also ohne Schaden -- aber auch ohne Update.
#
# Hier laeuft die echte Datei, und zwar OHNE DEV_SICHERUNG: so ruft
# sie das aktualisieren.sh aus 0.3.2 auf, mit dem 0.3.3 eingespielt
# wird. Sie muss sich die Sicherung selbst anlegen und durchlaufen.
E7="$BASIS/e7"; mkdir -p "$E7"
git -C "$E7" init -q .
git -C "$E7" config user.email p@p; git -C "$E7" config user.name P
git -C "$E7" config commit.gpgsign false
cp "$ECHT/aktualisierung.sh" "$ECHT/gesundheit.sh" "$E7/"
cp "$ECHT/systemcheck.py" "$ECHT/netzzustand.py" "$ECHT/config.py" "$E7/" 2>/dev/null
mkdir -p "$E7/.venv/bin"; ln -sf "$(command -v python3)" "$E7/.venv/bin/python"
echo "0.9.0" > "$E7/VERSION"; echo fastapi > "$E7/requirements.txt"
printf '{"wlan": {"ssid": "x"}}' > "$E7/zustand.json"
git -C "$E7" add -A >/dev/null; git -C "$E7" commit -q -m 0.9.0
ALT7="$(git -C "$E7" rev-parse HEAD)"
echo "0.9.1" > "$E7/VERSION"; echo neu > "$E7/dazu.txt"
git -C "$E7" add -A >/dev/null; git -C "$E7" commit -q -m 0.9.1
git -C "$E7" tag v0.9.1
git -C "$E7" update-ref refs/online/v0.9.1 "$(git -C "$E7" rev-parse v0.9.1)"
git -C "$E7" reset -q --hard "$ALT7"

# Die Grundlinie fuer den Gesundheitscheck, wie sie jeder echte
# Aufrufer setzt (stick_update.sh seit 0.2.12, aktualisieren.sh seit
# 0.3.3). Ohne sie zaehlt JEDER vorhandene Befund als neu, und der
# Lauf rollt ein tadelloses Update zurueck. Genau diesen Fehler hatte
# der Online-Weg -- gefunden, weil dieser Fall gegen die echte Datei
# laeuft statt gegen eine Attrappe.
mkdir -p "$BASIS/d7/vorher-0.9.1"
(cd "$E7" && DEV_SICHERUNG="$BASIS/d7/vorher-0.9.1" \
   bash "$E7/gesundheit.sh" --vorher >/dev/null 2>&1) || true

AUS7="$(cd "$E7" && env -u DEV_SICHERUNG \
  DEV_ORDNER="$E7" DEV_BENUTZER="$(id -un)" DEV_ABLAGE="$BASIS/d7" \
  DEV_ALT_SHA="$ALT7" DEV_REF=refs/online/v0.9.1 DEV_VERSION=0.9.1 \
  DEV_HIER=0.9.0 DEVARENU_UNIT_ORDNER="$BASIS/u7" \
  DEVARENU_UDEV_REGEL="$BASIS/u7.rules" \
  STUB_FASSUNG=0.9.1 STUB_LOG="$BASIS/s7.log" \
  bash "$E7/aktualisierung.sh" 2>&1)"; RC7=$?

pruefe "sie bricht NICHT an DEV_SICHERUNG ab" "nein" \
  "$(printf '%s' "$AUS7" | grep -q 'DEV_SICHERUNG' && echo ja || echo nein)"
pruefe "sie legt die Sicherung selbst an" "ja" \
  "$(printf '%s' "$AUS7" | grep -q 'keine uebergeben' && echo ja || echo nein)"
pruefe "und sagt, wo sie liegt" "ja" \
  "$([ -d "$BASIS/d7/vorher-0.9.1" ] && echo ja || echo nein)"
pruefe "zustand.json liegt darin" "ja" \
  "$([ -f "$BASIS/d7/vorher-0.9.1/zustand.json" ] && echo ja || echo nein)"
pruefe "der Lauf geht durch" "0" "$RC7"
pruefe "und die Fassung steht auf 0.9.1" "0.9.1" "$(cat "$E7/VERSION")"

titel "8) Scheitert die Logik mittendrin, kommt alles zurueck"
# Der Fall, ohne den es kein Autoupdate geben darf: die Logik hat
# schon vorgespult, aendert eine Unit und zustand.json -- und
# scheitert dann. Ohne Rueckweg bliebe der Rechner halb neu stehen,
# und niemand ist vor Ort.
#
# EIGENES Gegenstueck. Das obige hat inzwischen ein neu gesetztes Tag,
# und ein Klon davon weigert sich beim Holen, sein vorhandenes Tag zu
# ueberschreiben -- zu Recht, aber dann prueft dieser Fall den
# falschen Fehler.
FERN8="$BASIS/fern8"; mkdir -p "$FERN8"
git -C "$FERN8" init -q -b main
git -C "$FERN8" config user.email p@p; git -C "$FERN8" config user.name P
git -C "$FERN8" config commit.gpgsign false
git -C "$FERN8" config gpg.format ssh
git -C "$FERN8" config user.signingkey "$ECHTER.pub"
echo "0.9.0" > "$FERN8/VERSION"
echo ': # Platzhalter' > "$FERN8/aktualisierung.sh"
git -C "$FERN8" add -A >/dev/null; git -C "$FERN8" commit -q -m 0.9.0
git -C "$FERN8" tag -s v0.9.0 -m "Devarenu 0.9.0"

echo "0.9.1" > "$FERN8/VERSION"
# Eine Logik, die alles anfasst und dann scheitert.
cat > "$FERN8/aktualisierung.sh" <<'KAPUTT'
#!/usr/bin/env bash
set -u
cd "$DEV_ORDNER"
git merge --ff-only --quiet "$DEV_REF^{commit}" || exit 1
echo "NEUE UNIT"   > "$DEVARENU_UNIT_ORDNER/devarenu.service"
echo "NEUER TIMER" > "$DEVARENU_UNIT_ORDNER/devarenu-fenster.timer"
printf '{"kaputt": true}' > "$DEV_ORDNER/zustand.json"
echo "SIE-LIEF" >> "$DEV_ORDNER/kaputt.log"
echo "MELDUNG|mittendrin gescheitert"
exit 7
KAPUTT
git -C "$FERN8" add -A >/dev/null; git -C "$FERN8" commit -q -m 0.9.1
git -C "$FERN8" tag -s v0.9.1 -m "Devarenu 0.9.1"

R8="$BASIS/r8"
git clone -q "$FERN8" "$R8"
git -C "$R8" config user.email p@p; git -C "$R8" config user.name P
git -C "$R8" config commit.gpgsign false
git -C "$R8" -c advice.detachedHead=false checkout -q v0.9.0
git -C "$R8" branch -f main v0.9.0 >/dev/null
git -C "$R8" checkout -q main
git -C "$R8" branch --set-upstream-to=origin/main main >/dev/null 2>&1
echo "pruef@pruefstand $(cat "$ECHTER.pub")" > "$R8/schluessel.erlaubt"
cp "$ECHT/aktualisieren.sh" "$ECHT/gesundheit.sh" "$R8/"
printf '{"wlan": {"ssid": "x"}}' > "$R8/zustand.json"
chmod 600 "$R8/zustand.json"

U8="$BASIS/u8"; mkdir -p "$U8"
echo "ALTE UNIT"           > "$U8/devarenu.service"
echo "ALTER FENSTER-TIMER" > "$U8/devarenu-fenster.timer"
VOR8="$(git -C "$R8" rev-parse HEAD)"
ZUSTAND_VOR="$(md5sum < "$R8/zustand.json")"

AUS8="$(cd "$R8" && DEVARENU_DATEN="$BASIS/d8" \
        DEVARENU_UNIT_ORDNER="$U8" STUB_LOG="$BASIS/s8.log" \
        bash ./aktualisieren.sh 2>&1)" || true

# ZUERST: ist die kaputte Logik ueberhaupt gelaufen? Ohne diese Zeile
# gingen alle folgenden Pruefungen auch dann durch, wenn das Update
# gar nicht erst angefangen haette -- der Endzustand saehe gleich aus.
pruefe "die kaputte Logik lief wirklich" "ja" \
  "$([ -f "$R8/kaputt.log" ] && echo ja || echo nein)"
pruefe "das Scheitern wird gemeldet" "ja" \
  "$(printf '%s' "$AUS8" | grep -q 'gescheitert' && echo ja || echo nein)"
pruefe "der Code ist zurueck auf dem alten Stand" "$VOR8" \
  "$(git -C "$R8" rev-parse HEAD)"
pruefe "die Fassung ist wieder 0.9.0" "0.9.0" "$(cat "$R8/VERSION")"
pruefe "die Unit ist zurueckgeholt" "ALTE UNIT" "$(cat "$U8/devarenu.service")"
pruefe "auch die des Wartungsfensters" "ALTER FENSTER-TIMER" \
  "$(cat "$U8/devarenu-fenster.timer")"
pruefe "zustand.json ist zurueckgeholt" "$ZUSTAND_VOR" \
  "$(md5sum < "$R8/zustand.json")"
pruefe "der Dienst wurde neu gestartet" "1" \
  "$(grep -c 'restart devarenu' "$BASIS/s8.log" 2>/dev/null || echo 0)"

titel "8b) Abgeloester HEAD -- drei Lagen"
# Am 27.09. stand der Gemeinderechner auf tags/v0.2.11^0, main zeigte
# auf denselben Commit, und der Updater brach ab, obwohl nichts
# fehlte. Kein Weg im Repo hinterlaesst das; entstanden ist es von
# Hand. Angehaengt wird nur, wenn dabei nichts verlorengeht.
kopf_lage() { # $1 Ordner -> "main", "HEAD" oder der Zweigname
  git -C "$1" rev-parse --abbrev-ref HEAD
}

# (1) main zeigt auf denselben Commit -> anhaengen und weitermachen
R9A="$BASIS/r9a"; neuer_rechner "$R9A"
BAUM_VOR="$(cd "$R9A" && find . -path ./.git -prune -o -type f -print | sort | xargs md5sum 2>/dev/null | md5sum)"
git -C "$R9A" -c advice.detachedHead=false checkout -q --detach HEAD
AUS9A="$(lauf "$R9A")" || true
pruefe "(1) HEAD wird wieder angehaengt" "main" "$(kopf_lage "$R9A")"
pruefe "(1) und es wird gesagt" "ja" \
  "$(printf '%s' "$AUS9A" | grep -q 'wieder angehaengt' && echo ja || echo nein)"
pruefe "(1) das Update laeuft danach durch" "0.9.1" "$(cat "$R9A/VERSION")"

# (2) ein anders benannter Zweig zeigt darauf -> ebenfalls anhaengen
R9B="$BASIS/r9b"; neuer_rechner "$R9B"
# Erst abloesen, DANN main entfernen -- git weigert sich, den Zweig
# zu loeschen, auf dem HEAD gerade steht.
git -C "$R9B" -c advice.detachedHead=false checkout -q --detach HEAD
git -C "$R9B" branch vor-ort >/dev/null
git -C "$R9B" branch -D main >/dev/null 2>&1
lauf "$R9B" >/dev/null 2>&1 || true
pruefe "(2) der einzige Zweig wird genommen" "vor-ort" "$(kopf_lage "$R9B")"

# (3) kein Zweig zeigt darauf -> Abbruch, nichts angefasst
R9C="$BASIS/r9c"; neuer_rechner "$R9C"
git -C "$R9C" -c advice.detachedHead=false checkout -q --detach HEAD
echo "nur hier" > "$R9C/nur-abgeloest.txt"
git -C "$R9C" add -A >/dev/null
git -C "$R9C" -c user.email=p@p -c user.name=P commit -q -m "nur abgeloest"
SHA9C="$(git -C "$R9C" rev-parse HEAD)"
AUS9C="$(lauf "$R9C")" || true
pruefe "(3) kein Zweig darauf -> HEAD bleibt abgeloest" "HEAD" "$(kopf_lage "$R9C")"
pruefe "(3) der Stand bleibt unangetastet" "$SHA9C" "$(git -C "$R9C" rev-parse HEAD)"
pruefe "(3) die Arbeit ist noch da" "ja" \
  "$([ -f "$R9C/nur-abgeloest.txt" ] && echo ja || echo nein)"
pruefe "(3) und es wird erklaert" "ja" \
  "$(printf '%s' "$AUS9C" | grep -q 'kein Zweig zeigt' && echo ja || echo nein)"

titel "8c) Der Auszug gehoert root -- und wird trotzdem gefunden"
# Der Fehler vom 28.09.: aktualisieren.sh legt $AUSZUG als root mit
# 700 an und prueft gleich darauf mit einem blanken [ -f ], ob
# aktualisierung.sh darin liegt. Als Dienstbenutzer sieht es nichts
# und meldet "v0.3.3 bringt keine aktualisierung.sh mit" -- ueber ein
# Tag, in dem sie sehr wohl lag. Das Update brach ab, ohne etwas zu
# aendern.
#
# Nachgestellt mit einer sudo-Attrappe, die Rechte wirklich
# simuliert: was durch sie laeuft, darf in den Ordner sehen, was
# daran vorbeigeht, nicht. Ohne Wurzelrechte geht es anders nicht --
# und genau deshalb ist der Fehler durch alle bisherigen Laeufe
# gekommen.
R8C="$BASIS/r8c"; neuer_rechner "$R8C"
D8C="$BASIS/d8c"
STUBS8C="$BASIS/stubs8c"; mkdir -p "$STUBS8C"
cat > "$STUBS8C/sudo" <<STUB
#!/bin/sh
# Simuliert Wurzelrechte fuer genau einen Ordner: aufmachen,
# ausfuehren, wieder zumachen.
A="$D8C/logik-0.9.1"
[ -d "\$A" ] && chmod 700 "\$A"
"\$@"; rc=\$?
[ -d "\$A" ] && chmod 000 "\$A"
exit \$rc
STUB
# Die id-Attrappe muss hier WEG. Sie meldet "id -u" als 0, und
# damit nimmt als_wurzel seinen Wurzel-Zweig und ruft sudo nie auf --
# der Ordner gehoerte dann dem Pruefbenutzer und waere lesbar. Genau
# so ist der Fehler durch alle bisherigen Laeufe gekommen.
cat > "$STUBS8C/id" <<'STUBID'
#!/bin/sh
exec /usr/bin/id "$@"
STUBID
chmod +x "$STUBS8C/sudo" "$STUBS8C/id"

AUS8C="$(cd "$R8C" && PATH="$STUBS8C:$PATH" DEVARENU_DATEN="$D8C" \
         STUB_LOG="$BASIS/s8c.log" bash ./aktualisieren.sh 2>&1)" || true
chmod -R u+rwX "$D8C" 2>/dev/null || true

pruefe "die Logik wird im root-Ordner gefunden" "nein" \
  "$(printf '%s' "$AUS8C" | grep -q 'bringt keine aktualisierung.sh mit' \
     && echo ja || echo nein)"
pruefe "und das Update laeuft durch" "0.9.1" "$(cat "$R8C/VERSION")"

titel "9) Die drei Unit-Listen laufen nicht auseinander"
# Kern, versionierte Logik und Online-Weg fuehren dieselbe Liste
# dreimal -- der Kern darf von keiner versionierten Datei abhaengen.
# Drei Kopien laufen auseinander, wenn niemand hinsieht.
liste() {
  # Erst den Variablennamen weg, DANN zerlegen -- sonst nimmt das
  # grep die erste Unit mit, die auf derselben Zeile steht.
  sed -n '/^UNITS_GESICHERT="/,/"$/p' "$1" \
    | sed 's/^UNITS_GESICHERT="//' \
    | tr -d '\\"' | tr ' ' '\n' | grep -v '^$' | sort
}
pruefe "Kern und versionierte Logik" "$(liste "$ECHT/stick_update.sh")" \
  "$(liste "$ECHT/aktualisierung.sh")"
pruefe "Kern und Online-Weg" "$(liste "$ECHT/stick_update.sh")" \
  "$(liste "$ECHT/aktualisieren.sh")"
# Neun seit 0.4.0: devarenu-onlineupdate.service und .timer sind
# dazugekommen, der Weg hinter dem Knopf "Jetzt aktualisieren".
pruefe "und es sind die neun, die es gibt" "9" \
  "$(liste "$ECHT/stick_update.sh" | wc -l)"

titel "10) Autoupdate im Fenster: wann es laeuft und wann nicht"
# Der Schalter darf nur unter allen vier Bedingungen zuenden: Fenster
# an, Autoupdate an, im Fenster, keine Uebersetzung. Und genau einmal
# je Fenster -- der Timer tickt alle fuenf Minuten.
W="$BASIS/w10"; mkdir -p "$W/.venv/bin"
cp "$ECHT/wartungsfenster.sh" "$ECHT/wartungsfenster.py" \
   "$ECHT/netzzustand.py" "$ECHT/config.py" "$ECHT/meldung.sh" "$W/"
ln -sf "$ECHT/.venv/bin/python" "$W/.venv/bin/python"
echo "0.9.0" > "$W/VERSION"

# Attrappen: nmcli tut nichts, aktualisieren.sh schreibt nur mit,
# poweroff auch. Der Server wird ueber eine Datei nachgebildet.
cat > "$W/nmcli" <<'NM'
#!/bin/sh
exit 0
NM
cat > "$W/aktualisieren.sh" <<'UPD'
#!/usr/bin/env bash
echo "LIEF" >> "$(dirname "$0")/updater.log"
echo "0.9.1" > "$(dirname "$0")/VERSION"
exit 0
UPD
cat > "$W/poweroff" <<'PO'
#!/bin/sh
echo "AUS" >> "$(dirname "$0")/poweroff.log"
PO
chmod +x "$W/nmcli" "$W/poweroff"

# Das Fenster auf JETZT stellen, damit im_fenster=ja gilt.
HEUTE="$(LC_ALL=C date +%a | sed 's/Mon/Mo/;s/Tue/Di/;s/Wed/Mi/;s/Thu/Do/;s/Fri/Fr/;s/Sat/Sa/;s/Sun/So/')"
fenster_setzen() { # $1 autoupdate ja/nein
  cat > "$W/netz.json" <<ENDE
{"wartungsfenster": {"an": true, "profil": "P", "wochentag": "$HEUTE",
 "von": "00:00", "bis": "23:59", "autoupdate": $([ "$1" = ja ] && echo true || echo false),
 "nach_update_aus": true}}
ENDE
}
w_lauf() { # $1 uebersetzung ja/nein
  (cd "$W" && DEVARENU_NMCLI="$W/nmcli" DEVARENU_RTCWAKE=/bin/true \
     DEVARENU_POWEROFF="$W/poweroff" DEVARENU_DATEN="$W/abl" \
     DEVARENU_PORT=1 DEVARENU_UEBERSETZT_TEST="$1" \
     bash wartungsfenster.sh --pruefen 2>&1)
}

fenster_setzen nein
rm -f "$W/updater.log"; rm -rf "$W/abl"
w_lauf nein >/dev/null 2>&1 || true
pruefe "Autoupdate aus: der Updater laeuft nicht" "nein" \
  "$([ -f "$W/updater.log" ] && echo ja || echo nein)"

fenster_setzen ja
rm -f "$W/updater.log" "$W/poweroff.log"; rm -rf "$W/abl"
AUS10="$(w_lauf nein)" || true
pruefe "Autoupdate an: der Updater laeuft" "ja" \
  "$([ -f "$W/updater.log" ] && echo ja || echo nein)"
pruefe "die neue Fassung wird genannt" "ja" \
  "$(printf '%s' "$AUS10" | grep -q '0.9.0 -> 0.9.1' && echo ja || echo nein)"
pruefe "danach wird heruntergefahren" "ja" \
  "$([ -f "$W/poweroff.log" ] && echo ja || echo nein)"

# Zweiter Tick im selben Fenster: nichts mehr.
rm -f "$W/updater.log"
w_lauf nein >/dev/null 2>&1 || true
pruefe "der zweite Tick im selben Fenster laeuft nicht noch einmal" "nein" \
  "$([ -f "$W/updater.log" ] && echo ja || echo nein)"

# Waehrend einer Uebersetzung wird nicht aktualisiert. Das ist die
# Bedingung, an der der Gottesdienst haengt: ein Dienstneustart
# mitten in der Predigt waere der eine Fehler, den niemand erklaeren
# kann.
fenster_setzen ja
rm -f "$W/updater.log" "$W/poweroff.log"; rm -rf "$W/abl"
AUS10B="$(w_lauf ja)" || true
pruefe "waehrend einer Uebersetzung laeuft nichts" "nein" \
  "$([ -f "$W/updater.log" ] && echo ja || echo nein)"
pruefe "und es wird gesagt, warum" "ja" \
  "$(printf '%s' "$AUS10B" | grep -q 'Es wird uebersetzt' && echo ja || echo nein)"
pruefe "und der Rechner bleibt an" "nein" \
  "$([ -f "$W/poweroff.log" ] && echo ja || echo nein)"
# Und die Marke darf dabei NICHT gesetzt worden sein -- sonst liefe
# nach dem Gottesdienst in diesem Fenster gar nichts mehr.
pruefe "die Marke bleibt frei fuer den naechsten Tick" "nein" \
  "$(ls "$W/abl"/autoupdate-* >/dev/null 2>&1 && echo ja || echo nein)"

# Fenster ganz aus -- der Schalter faellt mit.
cat > "$W/netz.json" <<'ENDE'
{"wartungsfenster": {"an": false, "profil": "P", "autoupdate": true}}
ENDE
rm -f "$W/updater.log"; rm -rf "$W/abl"
w_lauf nein >/dev/null 2>&1 || true
pruefe "kein Fenster, kein Autoupdate" "nein" \
  "$([ -f "$W/updater.log" ] && echo ja || echo nein)"
pruefe "und es steht auch nicht mehr als an da" "False" \
  "$(cd "$W" && "$ECHT/.venv/bin/python" -c \
     'import sys; sys.path.insert(0,"."); import wartungsfenster as w; print(w.einstellung()["autoupdate"])')"

# ------------------------------------------------ Schalter und Fenster
#
# Bis 0.3.7 brach "wartungsfenster.sh --berichte ja" bei
# ausgeschaltetem Fenster ab -- mit der Meldung "Ohne eingeschaltetes
# Fenster kein Autoupdate". Die falsche Sache in der Meldung, und eine
# Reihenfolge, die nichts schuetzt: gesendet wird ohnehin nur im
# Fenster. Beide Faelle stehen hier, damit sie nicht wieder
# zusammenwachsen.
titel_f() { printf '\n   -- %s --\n' "$*"; }
titel_f "Schalter bei ausgeschaltetem Fenster"

cat > "$W/netz.json" <<'ENDE'
{"wartungsfenster": {"an": false, "profil": "P"}}
ENDE
SCHALT() { (cd "$W" && bash wartungsfenster.sh "$@" 2>&1); }

AUSB="$(SCHALT --berichte ja)"; RCB=$?
pruefe "Berichte lassen sich bei aus einschalten" "0" "$RCB"
pruefe "und der Schalter steht danach auch so da" "True" \
  "$(cd "$W" && "$ECHT/.venv/bin/python" -c \
     'import sys; sys.path.insert(0,"."); import wartungsfenster as w; print(w.einstellung()["berichte_senden"])')"
pruefe "es wird aber gesagt, dass noch nichts hinausgeht" "ja" \
  "$(printf '%s' "$AUSB" | grep -q 'Fenster ist aus' && echo ja || echo nein)"

AUSA="$(SCHALT --autoupdate ja)"; RCA=$?
pruefe "das Autoupdate braucht weiter ein Fenster" "1" "$RCA"
pruefe "und die Meldung nennt das Autoupdate, nicht die Berichte" "ja" \
  "$(printf '%s' "$AUSA" | grep -q 'Autoupdate braucht ein eingeschaltetes Fenster' \
     && echo ja || echo nein)"
pruefe "der Schalter bleibt dabei aus" "False" \
  "$(cd "$W" && "$ECHT/.venv/bin/python" -c \
     'import sys; sys.path.insert(0,"."); import wartungsfenster as w; print(w.einstellung()["autoupdate"])')"

# ------------------------------------ Der Knopf "Jetzt aktualisieren"
#
# Angestossen wird er ueber eine Marke, abgeholt von einem root-Timer.
# Hier laeuft dieselbe Kette mit Attrappen: nmcli sagt, ob Netz steht,
# systemctl schreibt nur mit, aktualisieren.sh auch.
titel_f "Jetzt aktualisieren (Knopf am Pult)"

J="$BASIS/wj"; rm -rf "$J"; mkdir -p "$J/.venv/bin" "$J/update"
cp "$ECHT/wartungsfenster.sh" "$ECHT/wartungsfenster.py" \
   "$ECHT/netzzustand.py" "$ECHT/config.py" "$J/"
ln -sf "$ECHT/.venv/bin/python" "$J/.venv/bin/python"
echo "0.9.0" > "$J/VERSION"
cat > "$J/netz.json" <<ENDE
{"wartungsfenster": {"an": true, "profil": "P", "wochendtag": "Do",
 "von": "00:00", "bis": "23:59"}}
ENDE
# nmcli: "connected" oder nicht, je nach Datei. connection up gelingt.
cat > "$J/nmcli" <<'NM'
#!/bin/sh
case "$*" in
  *"STATE general"*) [ -f "$(dirname "$0")/netz_da" ] && echo connected                        || echo disconnected ;;
  *"connection show --active"*) echo "" ;;
  *) : ;;
esac
exit 0
NM
cat > "$J/systemctl" <<'SC'
#!/bin/sh
echo "systemctl $*" >> "$(dirname "$0")/systemctl.log"
case "$1" in is-active) exit 0 ;; esac
exit 0
SC
cat > "$J/meldung.sh" <<'ME'
#!/usr/bin/env bash
echo "MELDUNG: $1" >> "$(dirname "$0")/meldung.log"
exit 0
ME
chmod +x "$J/nmcli" "$J/systemctl" "$J/meldung.sh"

j_lauf() {  # $1 uebersetzung ja/nein
  (cd "$J" && DEVARENU_NMCLI="$J/nmcli" DEVARENU_SYSTEMCTL="$J/systemctl" \
     DEVARENU_RTCWAKE=/bin/true DEVARENU_POWEROFF=/bin/true \
     DEVARENU_DATEN="$J/abl" DEVARENU_PORT=1 \
     DEVARENU_UEBERSETZT_TEST="${1:-nein}" \
     bash wartungsfenster.sh --jetzt 2>&1)
}
lage() { sed -n 's/.*"lage": *"\([a-z]*\)".*/\1/p' "$J/update/online-lauf.json" 2>/dev/null | head -1; }

# 1) Ohne Marke passiert nichts -- der Timer tickt alle 30 Sekunden.
cat > "$J/aktualisieren.sh" <<'UPD'
#!/usr/bin/env bash
echo "LIEF" >> "$(dirname "$0")/updater.log"
echo "0.9.1" > "$(dirname "$0")/VERSION"
exit 0
UPD
AUSJ="$(j_lauf nein)" || true
pruefe "ohne Marke laeuft nichts" "nein" \
  "$([ -f "$J/updater.log" ] && echo ja || echo nein)"

# 2) Waehrend einer Uebersetzung nicht.
: > "$J/update/online-jetzt"; touch "$J/netz_da"
AUSJ="$(j_lauf ja)" || true
pruefe "waehrend der Uebersetzung laeuft nichts" "nein" \
  "$([ -f "$J/updater.log" ] && echo ja || echo nein)"
pruefe "und es steht als Grund da" "gescheitert" "$(lage)"
pruefe "die Marke ist weg, der Timer versucht es nicht alle 30s neu" "nein" \
  "$([ -f "$J/update/online-jetzt" ] && echo ja || echo nein)"

# 3) Ohne Netz: deutlich, und der Timer kommt zurueck.
rm -f "$J/netz_da" "$J/systemctl.log"
: > "$J/update/online-jetzt"
AUSJ="$(j_lauf nein)" || true
pruefe "ohne Netz laeuft der Updater nicht" "nein" \
  "$([ -f "$J/updater.log" ] && echo ja || echo nein)"
pruefe "und es steht deutlich da" "ja" \
  "$(printf '%s' "$AUSJ" | grep -q 'Kein Netz' && echo ja || echo nein)"
pruefe "der Fenster-Timer wird wieder gestartet" "ja" \
  "$(grep -q 'start devarenu-fenster.timer' "$J/systemctl.log" \
     && echo ja || echo nein)"

# 4) Der gute Fall.
touch "$J/netz_da"; rm -f "$J/systemctl.log"
: > "$J/update/online-jetzt"
AUSJ="$(j_lauf nein)" || true
pruefe "der Updater lief" "ja" \
  "$([ -f "$J/updater.log" ] && echo ja || echo nein)"
pruefe "die Fassung steht auf 0.9.1" "0.9.1" "$(cat "$J/VERSION")"
pruefe "der Lauf ist fertig" "fertig" "$(lage)"
pruefe "der Fenster-Timer wurde angehalten" "ja" \
  "$(grep -q 'stop devarenu-fenster.timer' "$J/systemctl.log" \
     && echo ja || echo nein)"
pruefe "und wieder gestartet" "ja" \
  "$(grep -q 'start devarenu-fenster.timer' "$J/systemctl.log" \
     && echo ja || echo nein)"
pruefe "die Rueckmeldung ging hinaus" "ja" \
  "$([ -f "$J/meldung.log" ] && echo ja || echo nein)"

# 5) Abbruch mittendrin: der Updater gibt nicht Null zurueck. Er hat
#    seinen eigenen Rueckweg (Fall 5 oben); hier zaehlt, dass das Pult
#    es deutlich erfaehrt und die alte Fassung stehenbleibt.
cat > "$J/aktualisieren.sh" <<'UPD'
#!/usr/bin/env bash
echo "ABBRUCH" >> "$(dirname "$0")/updater.log"
exit 3
UPD
rm -f "$J/updater.log"
: > "$J/update/online-jetzt"
AUSJ="$(j_lauf nein)" || true
pruefe "ein Fehlschlag wird als solcher vermerkt" "gescheitert" "$(lage)"
pruefe "die Fassung bleibt, was sie war" "0.9.1" "$(cat "$J/VERSION")"
pruefe "und der Satz nennt die laufende Fassung" "ja" \
  "$(grep -q '0.9.1 laeuft weiter' "$J/update/online-lauf.json" \
     && echo ja || echo nein)"

# 6) Stromausfall mitten im Update: in online-lauf.json steht "laeuft",
#    und niemand hat es beendet. Beim naechsten Start muss das
#    berichtigt werden -- sonst wartet am Pult jemand auf etwas, das
#    nie fertig wird.
cat > "$J/update/online-lauf.json" <<ENDE
{
  "lage": "laeuft",
  "schritt": "update",
  "text": "",
  "seit": $(( $(date +%s) - 4000 )),
  "zeit": "2026-01-01 00:00:00"
}
ENDE
AUSJ="$(cd "$J" && DEVARENU_NMCLI="$J/nmcli" DEVARENU_SYSTEMCTL="$J/systemctl" \
  DEVARENU_DATEN="$J/abl" DEVARENU_PORT=1 \
  bash wartungsfenster.sh --jetzt-aufraeumen 2>&1)" || true
pruefe "ein abgebrochener Lauf wird erkannt" "abgebrochen" "$(lage)"
pruefe "und gesagt, was zu tun ist" "ja" \
  "$(grep -q 'pruefen.sh' "$J/update/online-lauf.json" && echo ja || echo nein)"

# Ein Lauf, der noch in der Frist liegt, bleibt unangetastet.
cat > "$J/update/online-lauf.json" <<ENDE
{"lage": "laeuft", "schritt": "update", "text": "", "seit": $(date +%s),
 "zeit": "2026-01-01 00:00:00"}
ENDE
(cd "$J" && DEVARENU_SYSTEMCTL="$J/systemctl" DEVARENU_PORT=1 \
  bash wartungsfenster.sh --jetzt-aufraeumen >/dev/null 2>&1) || true
pruefe "ein frischer Lauf bleibt laufend" "laeuft" "$(lage)"

printf '\n'
if [ "$FEHLER" = 0 ]; then
  printf '\033[32mAlle Faelle wie erwartet.\033[0m\n'
else
  printf '\033[31m%d Fehler.\033[0m\n' "$FEHLER"
fi
exit "$FEHLER"
