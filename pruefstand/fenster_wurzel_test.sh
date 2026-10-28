#!/usr/bin/env bash
# Spielt das Fenster (und der Knopf am Pult) ein Update ein, ohne sudo?
# (28.10.2026)
#
#   bash pruefstand/fenster_wurzel_test.sh
#
# wartungsfenster.sh laeuft als root. Bis zum 28.10.2026 rief update_kern
# aktualisieren.sh per runuser als DIENSTBENUTZER auf. aktualisieren.sh
# holt sich Privilegiertes dann mit sudo -- und sudo braucht ohne
# Terminal ein Passwort, das niemand eingibt. Das Update scheiterte.
# aktualisieren.sh ist seit 0.3.3 dafuer gebaut, als root zu laufen:
# git ueber als_benutzer beim Dienstbenutzer, alles andere als_wurzel.
#
# Nachgestellt mit echten Skripten und einem echt signierten Tag:
#   id -u      meldet 0 -- ausser nach runuser, das herabstuft
#   runuser    stuft wirklich herab (danach meldet id -u nicht mehr 0)
#   sudo       scheitert wie ohne Terminal und schreibt jeden Aufruf mit
#   chown      tut nichts (der Pruefbenutzer ist nicht root)
# Gefordert: die neue Fassung steht da, und sudo wurde nie gerufen.
set -u
ECHT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASIS="$(mktemp -d -p "$ECHT/.tmp" wurzel-XXXXXX)"
trap 'rm -rf "$BASIS"' EXIT
FEHLER=0
pruefe() {
  if [ "$2" = "$3" ]; then printf '   ok    %s\n' "$1"
  else printf '   \033[31mFEHL\033[0m  %s: erwartet %s, ist %s\n' "$1" "$2" "$3"
       FEHLER=$((FEHLER+1)); fi
}
titel() { printf '\n\033[1m== %s\033[0m\n' "$*"; }

# ------------------------------------------------------------ Attrappen
S="$BASIS/stubs"; mkdir -p "$S"
cat > "$S/id" <<'X'
#!/usr/bin/env bash
if [ "${1:-}" = "-u" ] && [ $# -eq 1 ]; then
  [ -n "${STUB_HERABGESTUFT:-}" ] && { /usr/bin/id -u; exit 0; }
  echo 0; exit 0
fi
exec /usr/bin/id "$@"
X
cat > "$S/runuser" <<'X'
#!/usr/bin/env bash
while [ $# -gt 0 ]; do
  case "$1" in -u) shift 2 ;; --) shift; break ;; *) break ;; esac
done
export STUB_HERABGESTUFT=1
exec "$@"
X
cat > "$S/sudo" <<'X'
#!/usr/bin/env bash
echo "sudo $*" >> "$SUDO_LOG"
echo "sudo: a terminal is required to read the password" >&2
exit 1
X
printf '#!/bin/sh\nexit 0\n' > "$S/chown"
printf '#!/bin/sh\necho "systemctl $*" >> "${STUB_LOG:-/dev/null}"\ncase "$1" in is-active) exit 0;; esac\nexit 0\n' > "$S/systemctl"
cat > "$S/nmcli" <<'X'
#!/bin/sh
case "$*" in
  *"STATE general"*) echo connected ;;
  *"CONNECTIVITY general"*) echo full ;;
  *"connection show --active"*) echo "P" ;;
esac
exit 0
X
chmod +x "$S"/*
export PATH="$S:$PATH" SUDO_LOG="$BASIS/sudo.log" STUB_LOG="$BASIS/systemctl.log"

# ------------------------------------------------------------ "origin"
ssh-keygen -q -t ed25519 -N "" -C echt -f "$BASIS/echt"
FERN="$BASIS/fern"; mkdir -p "$FERN"; git -C "$FERN" init -q -b main
git -C "$FERN" config user.email pruef@pruefstand
git -C "$FERN" config user.name Pruefstand
git -C "$FERN" config commit.gpgsign false
git -C "$FERN" config gpg.format ssh
git -C "$FERN" config user.signingkey "$BASIS/echt.pub"
echo "0.9.0" > "$FERN/VERSION"
cat > "$FERN/aktualisierung.sh" <<'LOGIK'
#!/usr/bin/env bash
set -u
cd "$DEV_ORDNER"
git merge --ff-only --quiet "$DEV_REF^{commit}" || exit 1
echo "LOGIK-LIEF $DEV_VERSION als $(id -u)" >> "$DEV_ORDNER/logik.log"
echo "MELDUNG|nichts"
LOGIK
git -C "$FERN" add -A >/dev/null; git -C "$FERN" commit -q -m 0.9.0
git -C "$FERN" tag -s v0.9.0 -m "Devarenu 0.9.0"
echo "0.9.1" > "$FERN/VERSION"
git -C "$FERN" add -A >/dev/null; git -C "$FERN" commit -q -m 0.9.1
git -C "$FERN" tag -s v0.9.1 -m "Devarenu 0.9.1"

rechner() {  # $1 Ordner -- ein Gemeinderechner auf 0.9.0 mit Fenster
  local r="$1"
  git clone -q "$FERN" "$r"
  git -C "$r" config user.email pruef@pruefstand
  git -C "$r" config user.name Pruefstand
  git -C "$r" -c advice.detachedHead=false checkout -q v0.9.0
  git -C "$r" branch -f main v0.9.0 >/dev/null; git -C "$r" checkout -q main
  git -C "$r" branch --set-upstream-to=origin/main main >/dev/null 2>&1
  echo "pruef@pruefstand $(cat "$BASIS/echt.pub")" > "$r/schluessel.erlaubt"
  cp "$ECHT/aktualisieren.sh" "$ECHT/wartungsfenster.sh" \
     "$ECHT/wartungsfenster.py" "$ECHT/netzzustand.py" "$ECHT/config.py" "$r/"
  mkdir -p "$r/.venv/bin" "$r/update"
  ln -s "$ECHT/.venv/bin/python" "$r/.venv/bin/python"
  cat > "$r/gesundheit.sh" <<'GES'
#!/usr/bin/env bash
if [ "${1:-}" = "--vorher" ]; then
  mkdir -p "$(dirname "${DEV_SICHERUNG:-/tmp}/befunde-vorher")" || exit 1
  echo keine > "${DEV_SICHERUNG:-/tmp}/befunde-vorher" || exit 1
fi
exit 0
GES
  printf '{"wlan": {"ssid": "x"}}' > "$r/zustand.json"; chmod 600 "$r/zustand.json"
  # Ein Fenster, das jetzt offen ist, mit Autoupdate.
  local tage=(So Mo Di Mi Do Fr Sa) tag
  tag="${tage[$(date +%w)]}"
  cat > "$r/netz.json" <<NJ
{"wartungsfenster": {"an": true, "profil": "P", "wochentag": "$tag",
 "von": "00:00", "bis": "23:59", "autoupdate": true,
 "nach_update_aus": false}}
NJ
}

fenster() {  # $1 Ordner, $2 Aufruf
  (cd "$1" && DEVARENU_NMCLI=nmcli DEVARENU_SYSTEMCTL=systemctl \
     DEVARENU_RTCWAKE=/bin/true DEVARENU_POWEROFF=/bin/true \
     DEVARENU_DATEN="$BASIS/daten-$(basename "$1")" DEVARENU_PORT=1 \
     DEVARENU_UEBERSETZT_TEST=nein bash wartungsfenster.sh "$2" 2>&1)
}

titel "1) Der Knopf am Pult (--jetzt)"
R="$BASIS/knopf"; rechner "$R"
: > "$R/update/online-jetzt"; : > "$SUDO_LOG"
AUS="$(fenster "$R" --jetzt)"
printf '%s\n' "$AUS" | grep -E "sudo|terminal|scheiter|->" | sed 's/^/      /' | head -6
pruefe "die Fassung steht auf 0.9.1" "0.9.1" "$(cat "$R/VERSION")"
pruefe "sudo wurde nie gerufen" 0 "$(wc -l < "$SUDO_LOG")"
pruefe "die Update-Logik lief als root" "LOGIK-LIEF 0.9.1 als 0" \
  "$(cat "$R/logik.log" 2>/dev/null)"

titel "2) Das Wartungsfenster (Autoupdate)"
R="$BASIS/fenster"; rechner "$R"
: > "$SUDO_LOG"
AUS="$(fenster "$R" --pruefen)"
printf '%s\n' "$AUS" | grep -E "sudo|terminal|scheiter|->" | sed 's/^/      /' | head -6
pruefe "die Fassung steht auf 0.9.1" "0.9.1" "$(cat "$R/VERSION")"
pruefe "sudo wurde nie gerufen" 0 "$(wc -l < "$SUDO_LOG")"

titel "3) git bleibt beim Dienstbenutzer"
# als_benutzer in aktualisieren.sh stuft fuer git herab. Im Pruefstand
# gibt es keinen zweiten Benutzer; die Attrappe merkt sich das
# Herabstufen. Kein Objekt in .git darf root gehoeren -- hier heisst
# das: alles gehoert dem Pruefbenutzer.
pruefe "keine fremden Eigentuemer in .git" 0 \
  "$(find "$R/.git" ! -user "$(/usr/bin/id -un)" | wc -l)"
pruefe "update_kern ruft aktualisieren.sh nicht mehr per runuser" nein \
  "$(sed -n '/^update_kern() {/,/^}/p' "$ECHT/wartungsfenster.sh" \
     | grep -v '^\s*#' | grep -q 'runuser' && echo ja || echo nein)"

printf '\n'
if [ "$FEHLER" = 0 ]; then printf '\033[32mAlle Faelle wie erwartet.\033[0m\n'
else printf '\033[31m%d Fehler.\033[0m\n' "$FEHLER"; fi
exit "$FEHLER"
