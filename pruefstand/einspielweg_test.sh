#!/usr/bin/env bash
# Der Weg auf 0.4.0 -- von v0.3.7 und von v0.3.8 aus, mit den ECHTEN Dateien.
#
#   bash pruefstand/einspielweg_test.sh > /tmp/einspielweg.txt 2>&1
#
# AUSGABE UMLEITEN, UND ZWAR IMMER. Dieser Lauf startet absichtlich
# die ALTE systemcheck.py, und die fragt kreadconfig6 ohne $HOME. KDE
# beschwert sich darueber auf dem TERMINAL -- nicht auf stderr, nicht
# auf stdout:
#
#   Configuration file "//.config/kreadconfig6rc" not writable.
#
# Weder 2>/dev/null noch setsid halten das auf. In eine Datei
# geschrieben ist die Ausgabe sauber; auf dem Schirm steht die Zeile
# dazwischen. Behoben ist die Ursache seit 0.4.0 in systemcheck.py --
# aber 0.3.7 bleibt 0.3.7.
#
# WARUM DIESER LAUF EXISTIERT
#
# Auf dem Gemeinderechner laeuft immer das aktualisieren.sh der
# INSTALLIERTEN Fassung, nicht das der neuen. Ein Update kann darum an
# einer Stelle scheitern, die im neuen Stand laengst behoben ist --
# genau so ist 0.3.3 gescheitert (`[ -f ... ]` ohne sudo auf einem
# root:root-700-Ordner, repariert erst in 0.3.4, also im Stand, der
# nicht lief).
#
# Hier laeuft deshalb nicht die Attrappe und nicht der neue Kern,
# sondern das aktualisieren.sh aus v0.3.7 und aus v0.3.8 -- gegen ein
# Repo, dessen naechstes signiertes Tag den ECHTEN 0.4.0-Baum traegt,
# samt der echten aktualisierung.sh von 0.4.0.
#
# WIE DIE ALTEN DATEIEN HIERHERKOMMEN
#
# Ueber `git worktree add` auf die Tags. Kein Auschecken im
# Arbeitsverzeichnis, keine Veraenderung am Repo -- die Baeume liegen
# im Wegwerfordner und werden am Ende abgemeldet.
#
# WAS NACHGEBAUT IST UND WAS NICHT
#
# Nachgebaut: Dienstkontext ohne HOME (ein root-Dienst bringt keines
# mit), Aufruf als Dienstbenutzer, Rechte 600 auf zustand.json und 711
# auf der Ablage wie im Feld.
#
# NICHT nachgebaut: sudo, systemctl, pacman und udevadm -- dafuer
# stehen die Attrappen in pruefstand/attrappen, dieselben, die auch
# online_test.sh benutzt. Dieser Lauf prueft den WEG, nicht das
# Betriebssystem.

set -u
ECHT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASIS="$(mktemp -d)"
export PATH="$ECHT/pruefstand/attrappen:$PATH"

GRUEN="\033[32m"; ROT="\033[31m"; GELB="\033[33m"; AUS="\033[0m"
FEHLER=0
VON="v0.3.7 v0.3.8 v0.4.1 v0.4.2 v0.4.3 v0.4.4"

aufraeumen() {
  for t in $VON; do
    git -C "$ECHT" worktree remove --force "$BASIS/baum-$t" 2>/dev/null || true
  done
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
merke() { printf "   ${GELB}i${AUS}     %s\n" "$*"; }
titel() { printf "\n\033[1m== %s\033[0m\n" "$*"; }

# ---------------------------------------------------------- Vorbedingungen
titel "0) Vorbedingungen"
for t in $VON; do
  if ! git -C "$ECHT" rev-parse -q --verify "refs/tags/$t" >/dev/null; then
    printf "   ${ROT}!${AUS}     UEBERSPRUNGEN: das Tag %s gibt es nicht.\n" "$t"
    printf "         Damit ist NICHT geprueft, ob ein Rechner mit %s\n" "$t"
    printf "         diese Fassung einspielen kann.\n"
    exit 1
  fi
done
NEU="$(tr -d '[:space:]' < "$ECHT/VERSION")"
pruefe "VERSION ist gesetzt" "ja" "$([ -n "$NEU" ] && echo ja || echo nein)"
merke "Ziel ist $NEU, Start sind $VON"

# Die alten Baeume. Ueber worktree, damit das Arbeitsverzeichnis
# unangetastet bleibt.
for t in $VON; do
  git -C "$ECHT" worktree add -q --detach "$BASIS/baum-$t" "$t" 2>/dev/null \
    || { printf "   ${ROT}FEHL${AUS}  worktree fuer %s ging nicht\n" "$t"
         exit 1; }
done
fehlt=""
for t in $VON; do
  [ -f "$BASIS/baum-$t/aktualisieren.sh" ] || fehlt="$fehlt $t"
done
pruefe "alle alten Baeume liegen da" "" "$fehlt"
# Der Beweis, dass es wirklich die ALTEN Dateien sind: 0.3.7 kennt den
# schluesselweisen Vergleich von zustand.json noch nicht.
pruefe "v0.3.7 hat noch die alte zustand-Pruefung" "nein" \
  "$(grep -q 'abdruck()' "$BASIS/baum-v0.3.7/aktualisieren.sh" \
     && echo ja || echo nein)"
pruefe "v0.3.8 hat sie schon" "ja" \
  "$(grep -q 'abdruck()' "$BASIS/baum-v0.3.8/aktualisieren.sh" \
     && echo ja || echo nein)"

# ------------------------------------------------- Das Fernrepo bauen
titel "1) Ein Fernrepo mit sechs echten Baeumen"
SCHLUESSEL="$BASIS/freigabe"
ssh-keygen -q -t ed25519 -N "" -C einspielweg -f "$SCHLUESSEL"
FERN="$BASIS/fern"
mkdir -p "$FERN"
# -b main, nicht die Vorgabe: aktualisieren.sh fragt nach dem
# Gegenstueck des Zweigs (@{u}), und das gibt es nur, wenn drueben
# derselbe Zweigname liegt. Ohne das meldete der Lauf "kein origin" --
# eine Auskunft, die mit der Lage nichts zu tun hat.
git -C "$FERN" init -q -b main
git -C "$FERN" config user.email pruef@pruefstand
git -C "$FERN" config user.name Pruefstand
git -C "$FERN" config gpg.format ssh
git -C "$FERN" config user.signingkey "$SCHLUESSEL.pub"
git -C "$FERN" config commit.gpgsign false

baum_hinein() {  # $1 Quellordner, $2 Fassung, $3 Tag
  # Nur verfolgte Dateien, also kein models/, kein voices/, kein venv.
  ( cd "$1" && git ls-files -z 2>/dev/null \
      | tar --null -cf - -T - ) 2>/dev/null \
    | tar -xf - -C "$FERN" 2>/dev/null \
    || { cd "$1" && cp -a . "$FERN/" 2>/dev/null; }
  # DER VERTRAUENSANKER GEHOERT IN DEN COMMIT.
  #
  # schluessel.erlaubt ist eine verfolgte Datei. Sie nachtraeglich im
  # Arbeitsverzeichnis zu ersetzen hiesse "lokale Aenderung", und
  # aktualisieren.sh bricht dann ab -- zu Recht. Also steht der
  # Testschluessel schon im Commit, genau wie der echte auf dem
  # Gemeinderechner im Commit steht.
  echo "pruef@pruefstand $(cat "$SCHLUESSEL.pub")" \
    > "$FERN/schluessel.erlaubt"
  # DER SELBSTTEST IST EINE ATTRAPPE, wie sudo und systemctl.
  #
  # Er laedt Whisper, Piper und das Sprachmodell -- zusammen zehn
  # Gigabyte, von denen in diesem Wegwerfordner nichts liegt. Seit
  # 0.4.2 laeuft er bei jedem Update, das teile.json aendert, und das
  # tut der Weg hierher. Ohne Attrappe scheiterte jeder Lauf an
  # etwas, das dieser Pruefstand gar nicht prueft.
  #
  # Geprueft wird dafuer, DASS die Kette ihn aufruft: unten steht
  # "der Selbsttest lief mit".
  printf '#!/usr/bin/env python3\nimport sys\nprint("Attrappe")\nsys.exit(0)\n' \
    > "$FERN/selbsttest.py"
  git -C "$FERN" add -A >/dev/null 2>&1
  git -C "$FERN" commit -q -m "$2" >/dev/null 2>&1
  git -C "$FERN" tag -s "$3" -m "Devarenu $2" >/dev/null 2>&1
}

# Der Reihe nach, aus $VON -- NICHT aufgezaehlt. Eine zweite Liste
# neben $VON war schon einmal der Fehler: v0.4.4 kam oben dazu und
# hier nicht, und der Lauf scheiterte an einem Tag, das es im
# Fernrepo gar nicht gab.
#
# Was an einzelnen Fassungen besonders ist:
#   v0.4.1  die letzte Fassung OHNE teile.json im Repo. Der Weg von
#           dort aus ist der, den eine Gemeinde als naechstes geht.
#   v0.4.2  die erste Fassung MIT teile.json. Von dort aus steht die
#           Datei auf beiden Seiten.
for t in $VON; do
  baum_hinein "$BASIS/baum-$t" "${t#v}" "$t"
done
# Der neue Stand: das Arbeitsverzeichnis, so wie es jetzt ist.
baum_hinein "$ECHT" "$NEU" "v$NEU"

# Nicht "git tag -v": das prueft die Signatur und braucht dafuer eine
# allowedSignersFile. Hier geht es nur darum, DASS eine Signatur im
# Tag-Objekt steht -- geprueft wird sie unten von aktualisieren.sh,
# und das ist der Punkt des Laufs.
for t in $VON "v$NEU"; do
  pruefe "$t traegt eine Signatur" "ja" \
    "$(git -C "$FERN" cat-file -p "$t" 2>/dev/null \
       | grep -q 'BEGIN SSH SIGNATURE' && echo ja || echo nein)"
done
pruefe "der neue Baum traegt die neue Fassung" "$NEU" \
  "$(git -C "$FERN" show "v$NEU:VERSION" | tr -d '[:space:]')"
pruefe "und die neue aktualisierung.sh" "ja" \
  "$(git -C "$FERN" show "v$NEU:aktualisierung.sh" \
     | grep -q 'devarenu-onlineupdate' && echo ja || echo nein)"

# ------------------------------------------------------- Ein Durchlauf
# $1 = Start-Tag. Legt einen "Gemeinderechner" an, der auf dieser
# Fassung steht, und spielt mit DESSEN aktualisieren.sh ein.
durchlauf() {
  local start="$1" ziel="$BASIS/rechner-$start" d="$BASIS/daten-$start"
  rm -rf "$ziel" "$d"
  git clone -q "$FERN" "$ziel"
  git -C "$ziel" config user.email pruef@pruefstand
  git -C "$ziel" config user.name Pruefstand
  git -C "$ziel" config commit.gpgsign false
  git -C "$ziel" -c advice.detachedHead=false checkout -q "$start"
  git -C "$ziel" branch -f main "$start" >/dev/null
  git -C "$ziel" checkout -q main
  git -C "$ziel" branch --set-upstream-to=origin/main main >/dev/null \
    || { printf "   ${ROT}FEHL${AUS}  kein origin/main im Klon\n"
         FEHLER=$((FEHLER + 1)); }

  # schluessel.erlaubt steht schon im Commit (siehe baum_hinein).
  # Hier wird nur nachgesehen, dass das auch stimmt -- sonst liefe der
  # Lauf gegen eine Signatur, die niemand prueft.
  grep -qF "$(awk '{print $2 " " $3}' "$SCHLUESSEL.pub")" \
    "$ziel/schluessel.erlaubt" \
    || { printf "   ${ROT}FEHL${AUS}  der Testschluessel steht nicht im Commit\n"
         FEHLER=$((FEHLER + 1)); }

  # Einstellungen wie im Feld: 600, mit einem WLAN-Passwort darin.
  printf '{"fassung": 3, "quelle": "de", "ziele": ["en", "ru", "fa"],\n' \
    > "$ziel/zustand.json"
  printf ' "wlan": {"ssid": "TEST-WLAN", "passwort": "TEST-PASSWORT"},\n' \
    >> "$ziel/zustand.json"
  printf ' "aufnahme_tage": 7, "aufnahme_frist_ab": 0}\n' >> "$ziel/zustand.json"
  chmod 600 "$ziel/zustand.json"
  printf '{"router": false}\n' > "$ziel/netz.json"
  chmod 644 "$ziel/netz.json"

  # Ein venv, das es gibt. Die echte aktualisierung.sh baut nur dann
  # ein neues, wenn sich requirements.txt geaendert hat.
  mkdir -p "$ziel/.venv/bin"
  ln -sf "$(command -v python3)" "$ziel/.venv/bin/python"

  # Die Ablage wie im Feld: durchgehbar, aber nicht auflistbar.
  mkdir -p "$d"; chmod 711 "$d"

  # MIT HOME, seit 0.4.2 -- und das ist keine Nachlaessigkeit,
  # sondern die Lage im Feld.
  #
  # Bis hierher lief dieser Fall mit "env -u HOME": ein root-Dienst
  # bringt keines mit, und git braucht es. Genau daran hing
  # devarenu-update.service bis 0.2.12. Seit 0.4.0 steht in JEDER
  # Unit-Vorlage "Environment=HOME=/root" -- der Dienst hat also
  # eines, und ein Lauf ohne HOME prueft eine Welt, die das Projekt
  # nicht mehr ausliefert.
  #
  # Es kostete ausserdem jedes Mal dasselbe: die ALTEN systemcheck.py
  # aus v0.3.7 und v0.3.8 fragen kreadconfig6 nach den
  # Energieeinstellungen, und ohne HOME loest "$HOME/.config" zu
  # "//.config" auf. kreadconfig6 beschwert sich darueber auf dem
  # TERMINAL -- weder "2>/dev/null" noch capture_output noch setsid
  # halten das auf, weil die Meldung nicht durch die umgeleiteten
  # Kanaele geht. Wer den Prueflauf fuhr, bekam sie quer ueber den
  # Schirm, jedes Mal.
  #
  # Zwei Riegel, beide im Wegwerfordner und beide ohne eine Zeile an
  # den alten Baeumen zu aendern:
  #   HOME             git findet seine Einstellungen, wie im Feld
  #   XDG_CONFIG_HOME  kreadconfig6 findet einen schreibbaren Ort
  #                    und hat nichts mehr zu melden
  mkdir -p "$BASIS/home-$start/.config"
  #
  # STUB_FASSUNG ist nicht Schmuck: der Gesundheitscheck fragt den
  # laufenden Dienst ueber HTTP nach seiner Fassung. Ohne die Attrappe
  # antwortet der ECHTE Devarenu dieses Rechners, meldet eine andere
  # Fassung, und der Lauf haelt ein tadelloses Update fuer kaputt und
  # rollt zurueck. Genau das ist beim Bauen dieses Falles passiert.
  # OHNE EIGENES TERMINAL (setsid).
  #
  ( cd "$ziel" && setsid env HOME="$BASIS/home-$start" \
      XDG_CONFIG_HOME="$BASIS/home-$start/.config" \
      DEVARENU_DATEN="$d" \
      DEVARENU_UNIT_ORDNER="$BASIS/units-$start" \
      DEVARENU_UDEV_REGEL="$BASIS/udev-$start.rules" \
      STUB_LOG="$BASIS/stub-$start.log" \
      STUB_FASSUNG="$NEU" \
      DEVARENU_KEIN_NETZ=1 \
      bash ./aktualisieren.sh 2>&1 )
}

for start in $VON; do
  titel "2) Von $start aus -- mit dem aktualisieren.sh von $start"
  ZIEL="$BASIS/rechner-$start"
  AUSG="$(durchlauf "$start")"; RC=$?
  printf '%s\n' "$AUSG" | sed 's/\x1b\[[0-9;]*m//g' \
    > "$BASIS/lauf-$start.txt"

  pruefe "der Lauf geht durch" "0" "$RC"
  # SEIT 0.4.2 STEHT teile.json IMMER IM REPO.
  #
  # Bis dahin hiess "Datei da" so viel wie "dieses Update bringt
  # grosse Teile mit", und aktualisierung.sh brach ab, wenn der Stick
  # sie nicht mitbrachte. Dieser Lauf hier ist der ONLINE-Weg: es gibt
  # gar keinen Stick. Er darf daran nicht scheitern -- und tut es
  # auch nicht, wenn kein Netz da ist, um Fehlendes nachzuholen.
  pruefe "teile.json liegt im neuen Stand" "ja" \
    "$([ -f "$ZIEL/teile.json" ] && echo ja || echo nein)"
  pruefe "das Update ohne Stick scheitert nicht daran" "nein" \
    "$(grep -q 'Grosse Teile liessen sich nicht einspielen' \
       "$BASIS/lauf-$start.txt" && echo ja || echo nein)"
  pruefe "und sagt, dass etwas fehlt, statt es zu verschweigen" "ja" \
    "$(grep -qE 'grosse Teile|Stimmen werden aus dem Netz' \
       "$BASIS/lauf-$start.txt" && echo ja || echo nein)"
  # Der Selbsttest gehoert dazu, wenn sich die grossen Teile geaendert
  # haben -- und das steht in teile.json.
  #
  # NICHT an Fassungsnummern festgemacht. Hier stand einmal "von
  # v0.4.2 und v0.4.3 aus kein Selbsttest", und das stimmte genau so
  # lange, bis teile.json sich wieder aenderte (0.4.5, zwei Stimmen
  # heraus). Dann meldete der Lauf einen Fehler, wo keiner war.
  # Gefragt wird jetzt das, worauf es ankommt.
  if git -C "$ECHT" diff --quiet "$start" HEAD -- teile.json 2>/dev/null
  then
    pruefe "ohne Aenderung an teile.json kein Selbsttest" "nein" \
      "$(grep -q 'Selbsttest' "$BASIS/lauf-$start.txt" \
         && echo ja || echo nein)"
  else
    pruefe "der Selbsttest lief mit" "ja" \
      "$(grep -q 'Selbsttest bestanden' "$BASIS/lauf-$start.txt" \
         && echo ja || echo nein)"
  fi
  pruefe "die Fassung steht auf $NEU" "$NEU" \
    "$(tr -d '[:space:]' < "$ZIEL/VERSION" 2>/dev/null)"
  pruefe "die Signatur wurde geprueft" "ja" \
    "$(grep -q "Signatur von v$NEU ist gueltig" "$BASIS/lauf-$start.txt" \
       && echo ja || echo nein)"
  pruefe "die versionierte Haelfte lief" "ja" \
    "$(grep -qi 'vorgespult\|Pakete\|Units' "$BASIS/lauf-$start.txt" \
       && echo ja || echo nein)"
  pruefe "der Zweig ist nicht abgeloest" "main" \
    "$(git -C "$ZIEL" rev-parse --abbrev-ref HEAD)"

  # Die Einstellungen der Gemeinde: unangetastet, und 600 geblieben.
  pruefe "zustand.json hat noch das Passwort" "ja" \
    "$(grep -q 'TEST-PASSWORT' "$ZIEL/zustand.json" && echo ja || echo nein)"
  pruefe "und noch die Rechte 600" "600" \
    "$(stat -c %a "$ZIEL/zustand.json")"
  pruefe "netz.json ist noch 644" "644" "$(stat -c %a "$ZIEL/netz.json")"

  # Die neuen Units von 0.4.0 muessen im Baum liegen -- geschrieben
  # werden sie nur auf einem Rechner, der als Dienst laeuft.
  pruefe "die neuen Unit-Vorlagen sind da" "ja" \
    "$([ -f "$ZIEL/devarenu-onlineupdate.service.vorlage" ] \
      && [ -f "$ZIEL/devarenu-onlineupdate.timer.vorlage" ] \
      && echo ja || echo nein)"
  pruefe "und die neuen Dateien von 0.4.0" "ja" \
    "$([ -f "$ZIEL/zaehlung.json" ] && [ -f "$ZIEL/testmodus.py" ] \
      && [ -f "$ZIEL/sichern.sh" ] && echo ja || echo nein)"
  pruefe "das aktive Glossar liegt dabei" "ja" \
    "$([ -f "$ZIEL/glossar_v0.9.csv" ] && echo ja || echo nein)"

  # Die Hilfsreferenz gehoert aufgeraeumt.
  pruefe "die Hilfsreferenz ist wieder weg" "" \
    "$(git -C "$ZIEL" rev-parse -q --verify "refs/online/v$NEU" 2>/dev/null || true)"

  # Und der Unterschied, auf den es ankommt: 0.3.7 kennt den
  # schluesselweisen Vergleich noch nicht und meldet darum FEHLT,
  # sobald der neue Dienst zustand.json ergaenzt. Das ist KEIN Fehler
  # des Updates -- aber es gehoert gewusst, bevor jemand am Donnerstag
  # davor steht.
  if grep -q 'zustand.json hat sich geaendert' "$BASIS/lauf-$start.txt"; then
    merke "$start meldet \"zustand.json hat sich geaendert\" -- erwartet"
    merke "   bei 0.3.7 (Ganzdatei-Pruefsumme), nicht bei 0.3.8."
    pruefe "nur v0.3.7 meldet das" "v0.3.7" "$start"
  else
    merke "$start meldet keinen zustand-Befund"
  fi
done

# ------------------------------------------------ Was NICHT geprueft ist
titel "3) Was dieser Lauf NICHT prueft"
cat <<'ENDE'
         sudo, systemctl, pacman, udevadm und der SELBSTTEST laufen
         als Attrappe. Also: dass die Units wirklich scharf werden,
         dass pacman die Pakete findet, dass der Dienst wieder
         hochkommt und dass Whisper, Piper und das Sprachmodell
         danach wirklich rechnen, sagt dieser Lauf NICHT.

         Dafuer ist die virtuelle Testmaschine da -- VM-TESTUMGEBUNG.md.
         Dort laeuft dasselbe gegen ein echtes systemd.
ENDE

printf '\n'
if [ "$FEHLER" = 0 ]; then
  printf "${GRUEN}Alle Faelle wie erwartet.${AUS}\n"
else
  printf "${ROT}%d Fehler.${AUS}\n" "$FEHLER"
fi
exit "$FEHLER"
