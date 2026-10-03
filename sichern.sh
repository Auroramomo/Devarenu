#!/usr/bin/env bash
# Sichert den Gemeinderechner auf eine tragbare Platte.
#
#   bash sichern.sh /run/media/<benutzer>/<PLATTE>
#   bash sichern.sh /pfad --ohne-grosse      ohne Modelle, Stimmen, Vorrat
#   bash sichern.sh /pfad --pruefen          nur sagen, was gesichert wuerde
#
# WAS HIER GESICHERT WIRD -- UND WARUM GETRENNT
#
# Zwei Teile, und die Trennung ist der Kern dieses Skripts:
#
#   geheim.tar.gz.gpg   zustand.json, netz.json, meldung.json,
#                       NetworkManager-Profile, RustDesk-Einstellungen.
#                       Darin stehen das WLAN-Passwort, das
#                       ntfy-Thema und das RustDesk-Kennwort. Diese
#                       Datei ist mit einer Passphrase verschluesselt.
#
#   offen/              Modelle, Stimmen, Reparaturvorrat, Fassung,
#                       Commit-SHA, Geraeteliste. Nichts davon ist
#                       geheim, alles davon ist gross.
#
# OHNE PASSPHRASE SIND DIE GEHEIMNISSE WEG und muessen neu eingetragen
# werden -- WLAN-Passwort am Pult, ntfy-Thema in meldung.json,
# RustDesk-Kennwort in RustDesk. Alles andere laesst sich trotzdem
# wiederherstellen: zuruecksichern.sh kommt ohne Passphrase bis zu dem
# Punkt und sagt dann, was fehlt.
#
# Die Passphrase wird hier abgefragt und NIRGENDS gespeichert. Sie
# steht auch nicht in der Befehlszeile -- dort koennte sie jeder
# mitlesen, der "ps" tippt -- sondern geht ueber eine Pipe an gpg.
#
# WARUM gpg UND NICHT openssl
#
# gpg bringt einen ordentlichen Schluesselableiter mit (S2K) und
# schuetzt die Datei gegen unbemerkte Veraenderung. openssl enc kann
# beides nicht von sich aus. Und gnupg ist auf einem Arch-System
# ohnehin da: pacman braucht es, um Paketsignaturen zu pruefen.

set -u
ORDNER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ORDNER"

ZIEL=""
GROSSE=ja
NUR_PRUEFEN=nein

# Attrappe fuer den Pruefstand, wie DEVARENU_NMCLI und
# DEVARENU_SYSTEMCTL in wartungsfenster.sh. Im Betrieb steht hier
# sudo; der Pruefstand setzt ein Skript ein, das nur mitschreibt --
# dann laeuft der ganze Weg durch, ohne eine einzige Datei ausserhalb
# des Wegwerfordners anzufassen.
SUDO="${DEVARENU_SUDO:-sudo}"

blau() { printf '\n\033[1;34m== %s\033[0m\n' "$*"; }
gut()  { printf '   \033[32mok\033[0m    %s\n' "$*"; }
warn() { printf '   \033[33m!\033[0m     %s\n' "$*"; }
fehl() { printf '   \033[31mFEHLT\033[0m %s\n' "$*"; }
info() { printf '         %s\n' "$*"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --ohne-grosse) GROSSE=nein; shift ;;
    --pruefen)     NUR_PRUEFEN=ja; shift ;;
    -h|--hilfe)
      sed -n '2,/^set -u/p' "$0" | sed 's/^# \{0,1\}//;/^set -u/d'
      exit 0 ;;
    -*) fehl "Unbekannt: $1"; exit 2 ;;
    *)  ZIEL="$1"; shift ;;
  esac
done

if [ -z "$ZIEL" ]; then
  echo "So wird es benutzt:"
  echo "  bash sichern.sh /run/media/<benutzer>/<PLATTE>"
  echo
  echo "Angesteckte Platten:"
  lsblk -o MOUNTPOINT,SIZE,LABEL 2>/dev/null \
    | awk 'NR>1 && $1 ~ /^\// && $1 != "/" {print "  " $0}'
  exit 2
fi

# ------------------------------------------------------------ Ziel pruefen
blau "Ziel"
if [ ! -d "$ZIEL" ]; then
  fehl "$ZIEL ist kein Ordner."
  info "Ist die Platte eingehaengt? Nachsehen mit  lsblk"
  exit 1
fi
if [ ! -w "$ZIEL" ]; then
  fehl "In $ZIEL darf nicht geschrieben werden."
  exit 1
fi
gut "$ZIEL ist beschreibbar"

# Als Wurzel brauchen wir nur das Lesen der NetworkManager-Profile.
# Alles andere gehoert dem Dienstbenutzer. Darum NICHT das ganze
# Skript als root: eine Sicherung, die root-eigene Dateien auf eine
# FAT-Platte legt, ist eine Sicherung, die niemand zurueckspielen kann.
if [ "$(id -u)" = 0 ]; then
  fehl "Nicht als root. Dieses Skript fragt selbst nach sudo, wo es"
  info "noetig ist -- und legt die Sicherung dem an, der sie macht."
  exit 1
fi

NAME="devarenu-sicherung-$(hostname)-$(date +%Y%m%d-%H%M%S)"
STAND="$ZIEL/$NAME"
FASSUNG="$(tr -d '[:space:]' < VERSION 2>/dev/null || echo unbekannt)"

# ------------------------------------------------------- Was ist da?
blau "Was gesichert wird"

GEHEIM_DATEIEN=""
for d in zustand.json netz.json meldung.json; do
  if [ -f "$d" ]; then
    GEHEIM_DATEIEN="$GEHEIM_DATEIEN $d"
    gut "$d ($(stat -c %s "$d") Bytes, Rechte $(stat -c %a "$d"))"
  else
    warn "$d gibt es nicht -- wird uebersprungen"
  fi
done

NM_ORDNER=/etc/NetworkManager/system-connections
NM_ANZAHL=0
# Der Ordner gehoert root und ist 700 -- ohne sudo sieht man ihn nicht
# einmal. Darum wird hier gefragt, und zwar einmal und sichtbar.
if $SUDO test -d "$NM_ORDNER" 2>/dev/null; then
  NM_ANZAHL="$($SUDO ls -1 "$NM_ORDNER" 2>/dev/null | wc -l)"
  gut "NetworkManager-Profile: $NM_ANZAHL (ueber sudo gelesen)"
else
  warn "Keine NetworkManager-Profile gefunden (oder kein sudo)."
fi

RUSTDESK="$HOME/.config/rustdesk"
if [ -d "$RUSTDESK" ]; then
  gut "RustDesk-Einstellungen ($RUSTDESK)"
else
  warn "Keine RustDesk-Einstellungen unter $RUSTDESK."
fi

OFFEN_LISTE=""
if [ "$GROSSE" = ja ]; then
  for o in models voices; do
    if [ -d "$o" ]; then
      OFFEN_LISTE="$OFFEN_LISTE $o"
      gut "$o ($(du -sh "$o" 2>/dev/null | cut -f1))"
    fi
  done
  if [ -d /opt/devarenu-vorrat ]; then
    gut "Reparaturvorrat ($(du -sh /opt/devarenu-vorrat 2>/dev/null | cut -f1))"
  fi
else
  info "Modelle, Stimmen und Vorrat bleiben draussen (--ohne-grosse)."
  info "Sie lassen sich mit einrichten.sh und vorrat_bauen.sh neu holen"
  info "-- dafuer braucht es dann ein Netz."
fi

if [ "$NUR_PRUEFEN" = ja ]; then
  blau "Trockenlauf"
  info "Geschrieben wuerde nach: $STAND"
  exit 0
fi

# ------------------------------------------------------- Passphrase
blau "Passphrase fuer die Geheimnisse"
if ! command -v gpg >/dev/null; then
  fehl "gpg fehlt. Ohne gpg werden die Geheimnisse nicht gesichert."
  info "Nachholen:  sudo pacman -S gnupg"
  info "Oder mit --ohne-geheim nur den offenen Teil sichern."
  exit 1
fi
info "Sie wird nirgends gespeichert. Ohne sie sind WLAN-Passwort,"
info "ntfy-Thema und RustDesk-Kennwort aus dieser Sicherung nicht mehr"
info "zu holen -- alles andere schon."
printf '         Passphrase: '
IFS= read -rs PASS1; echo
printf '         noch einmal: '
IFS= read -rs PASS2; echo
if [ -z "$PASS1" ]; then
  fehl "Leere Passphrase. Abgebrochen."
  exit 1
fi
if [ "$PASS1" != "$PASS2" ]; then
  fehl "Die beiden Eingaben sind verschieden. Abgebrochen."
  exit 1
fi
unset PASS2
# Mindestens zwoelf Zeichen. Keine Regeln ueber Sonderzeichen: eine
# Passphrase, die man sich nicht merkt, steht am Monitor.
if [ "${#PASS1}" -lt 12 ]; then
  warn "Nur ${#PASS1} Zeichen. Vier Woerter sind besser als acht Zeichen."
  printf '         Trotzdem weiter? [j/N] '
  read -r a
  case "$a" in j|J|ja|Ja) ;; *) echo "         Abgebrochen."; exit 1 ;; esac
fi

# ------------------------------------------------------------ Sichern
blau "Sichern nach $STAND"
mkdir -p "$STAND/offen" || { fehl "Ordner liess sich nicht anlegen."; exit 1; }
chmod 700 "$STAND"

# ---- der geheime Teil
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"; unset PASS1' EXIT INT TERM
mkdir -p "$TMP/geheim/devarenu" "$TMP/geheim/nm" "$TMP/geheim/rustdesk"
for d in $GEHEIM_DATEIEN; do
  cp -p "$d" "$TMP/geheim/devarenu/$d"
done
if [ "$NM_ANZAHL" != 0 ]; then
  # Als Wurzel lesen, dem Benutzer uebergeben: die Profile sind
  # root:root 600, und auf der Platte soll nichts liegen, was der
  # Benutzer nicht wieder anfassen kann.
  $SUDO tar -cf - -C "$NM_ORDNER" . 2>/dev/null \
    | tar -xf - -C "$TMP/geheim/nm" 2>/dev/null \
    && $SUDO chown -R "$(id -un)" "$TMP/geheim/nm" \
    && gut "NetworkManager-Profile gelesen" \
    || warn "Die NetworkManager-Profile liessen sich nicht lesen."
fi
if [ -d "$RUSTDESK" ]; then
  cp -a "$RUSTDESK/." "$TMP/geheim/rustdesk/" 2>/dev/null \
    && gut "RustDesk-Einstellungen gelesen" \
    || warn "RustDesk-Einstellungen liessen sich nicht lesen."
fi

# Die Passphrase geht ueber den Deskriptor 3 an gpg, nicht ueber die
# Befehlszeile. printf ist in bash eingebaut -- der Wert erscheint also
# in keiner Prozessliste.
# Ein eigenes gpg-Heim im Wegwerfordner: fuer eine symmetrische
# Verschluesselung braucht gpg keinen Schluesselbund, und der des
# Benutzers hat damit nichts zu schaffen. Nebenbei laeuft es so auch
# dort, wo ~/.gnupg nicht anzulegen ist.
mkdir -p "$TMP/gpg"; chmod 700 "$TMP/gpg"
if tar -czf - -C "$TMP" geheim \
     | gpg --batch --quiet --yes --symmetric --homedir "$TMP/gpg" \
           --cipher-algo AES256 --digest-algo SHA512 \
           --s2k-mode 3 --s2k-count 65011712 --s2k-digest-algo SHA512 \
           --passphrase-fd 3 --output "$STAND/geheim.tar.gz.gpg" \
           3< <(printf '%s' "$PASS1"); then
  chmod 600 "$STAND/geheim.tar.gz.gpg"
  gut "geheim.tar.gz.gpg ($(stat -c %s "$STAND/geheim.tar.gz.gpg") Bytes)"
else
  fehl "Das Verschluesseln ging nicht. Es liegt NICHTS Geheimes auf der Platte."
  exit 1
fi
unset PASS1

# ---- der offene Teil
{
  echo "fassung=$FASSUNG"
  echo "commit=$(git rev-parse HEAD 2>/dev/null || echo unbekannt)"
  echo "rechner=$(hostname)"
  echo "datum=$(date '+%Y-%m-%d %H:%M:%S')"
  echo "benutzer=$(id -un)"
  echo "ordner=$ORDNER"
} > "$STAND/offen/stand.txt"
gut "stand.txt (Fassung, Commit, Rechner)"

# Die Geraeteliste: ohne sie raet man nach einer Neuinstallation, auf
# welcher Nummer das Mikrofon sitzt. Nur Namen und Nummern, keine
# Einstellungen -- die stehen in zustand.json.
if [ -x .venv/bin/python ]; then
  .venv/bin/python -c '
import sounddevice as sd
for i, g in enumerate(sd.query_devices()):
    if g["max_input_channels"]:
        print(f"{i}  {g[\"name\"]}  ({g[\"max_input_channels\"]} Kanaele)")
' > "$STAND/offen/tongeraete.txt" 2>/dev/null \
    && gut "tongeraete.txt" || warn "Die Geraeteliste ging nicht."
fi

for o in $OFFEN_LISTE; do
  info "$o wird kopiert, das dauert ..."
  if command -v rsync >/dev/null; then
    rsync -a --info=progress2 "$o/" "$STAND/offen/$o/" \
      && gut "$o kopiert" || warn "$o nicht vollstaendig kopiert."
  else
    cp -a "$o" "$STAND/offen/" && gut "$o kopiert" \
      || warn "$o nicht vollstaendig kopiert."
  fi
done
if [ "$GROSSE" = ja ] && [ -d /opt/devarenu-vorrat ]; then
  info "Reparaturvorrat wird kopiert ..."
  $SUDO tar -cf - -C /opt devarenu-vorrat 2>/dev/null \
    | tar -xf - -C "$STAND/offen" 2>/dev/null \
    && gut "Reparaturvorrat kopiert" \
    || warn "Der Vorrat liess sich nicht kopieren."
fi

# ---- Pruefsummen und eine Liesmich
( cd "$STAND" && find . -type f ! -name pruefsummen.txt \
    -exec sha256sum {} + > pruefsummen.txt ) 2>/dev/null \
  && gut "pruefsummen.txt" || warn "Pruefsummen gingen nicht."

cat > "$STAND/LIESMICH.txt" <<ENDE
Sicherung eines Devarenu-Gemeinderechners
=========================================

Rechner:  $(hostname)
Fassung:  $FASSUNG
Datum:    $(date '+%d.%m.%Y %H:%M')

ZURUECKSPIELEN

  1. Rechner nach AUFSTELLEN.md neu aufsetzen (Abschnitt
     "Erstinstallation Schritt fuer Schritt").
  2. bash zuruecksichern.sh "$NAME"
     Dabei wird nach der Passphrase gefragt.

OHNE PASSPHRASE

  Dann bleiben die Geheimnisse in geheim.tar.gz.gpg unlesbar:
  WLAN-Passwort, ntfy-Thema, RustDesk-Kennwort. Sie muessen neu
  eingetragen werden -- WLAN am Pult unter Einrichtung, ntfy-Thema in
  meldung.json, RustDesk in RustDesk selbst.

  ALLES ANDERE laesst sich trotzdem zurueckspielen: Modelle, Stimmen,
  Reparaturvorrat, Fassung und die Geraeteliste liegen im Ordner
  "offen" unverschluesselt. zuruecksichern.sh --ohne-geheim macht
  genau das.

WAS HIER NICHT DRIN IST

  Die Aufnahmen. Die werden nach sieben Tagen geloescht, und eine
  Sicherung, die sie mitnimmt, hebelt diese Zusage aus.
ENDE
gut "LIESMICH.txt"

blau "Fertig"
printf '   \033[32m%s\033[0m\n' "$(du -sh "$STAND" | cut -f1) in $STAND"
info "Die Passphrase ist nirgends gespeichert. Wer sie verliert,"
info "verliert die Geheimnisse -- nicht die Sicherung."
info "Jetzt noch die Platte sauber aushaengen."
exit 0
