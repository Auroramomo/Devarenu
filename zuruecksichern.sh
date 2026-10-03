#!/usr/bin/env bash
# Spielt eine Sicherung zurueck, die sichern.sh angelegt hat.
#
#   bash zuruecksichern.sh /run/media/<benutzer>/<PLATTE>/devarenu-sicherung-...
#   bash zuruecksichern.sh /pfad --pruefen        nur sagen, was passieren wuerde
#   bash zuruecksichern.sh /pfad --ohne-geheim    ohne Passphrase, nur der
#                                                 offene Teil
#
# GEDACHT FUER DEN FALL "Rechner geplaettet und neu aufgesetzt".
# Erst die Erstinstallation nach AUFSTELLEN.md, dann dieses Skript.
#
# WAS ES ANFASST UND WAS NICHT
#
# Es schreibt zustand.json, netz.json und meldung.json in diesen
# Ordner, die NetworkManager-Profile nach /etc, die
# RustDesk-Einstellungen nach ~/.config -- und legt Modelle, Stimmen
# und den Reparaturvorrat zurueck, wenn sie in der Sicherung liegen.
#
# Es fasst NICHT an: den Quelltext (der kommt aus git), die Units (die
# schreibt dienst.sh), das venv (das baut einrichten.sh). Eine
# Sicherung ist fuer die Einstellungen einer Gemeinde da, nicht fuer
# ein Abbild der Platte.
#
# OHNE PASSPHRASE kommt es bis zum offenen Teil und sagt dann genau,
# was neu eingetragen werden muss.

set -u
ORDNER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ORDNER"

QUELLE=""
NUR_PRUEFEN=nein
GEHEIM=ja

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
    --pruefen)      NUR_PRUEFEN=ja; shift ;;
    --ohne-geheim)  GEHEIM=nein; shift ;;
    -h|--hilfe)
      sed -n '2,/^set -u/p' "$0" | sed 's/^# \{0,1\}//;/^set -u/d'
      exit 0 ;;
    -*) fehl "Unbekannt: $1"; exit 2 ;;
    *)  QUELLE="$1"; shift ;;
  esac
done

if [ -z "$QUELLE" ]; then
  echo "So wird es benutzt:"
  echo "  bash zuruecksichern.sh /pfad/zu/devarenu-sicherung-..."
  exit 2
fi
if [ "$(id -u)" = 0 ]; then
  fehl "Nicht als root. Dieses Skript fragt selbst nach sudo."
  exit 1
fi

blau "Die Sicherung"
if [ ! -d "$QUELLE" ]; then
  fehl "$QUELLE ist kein Ordner."
  exit 1
fi
if [ -f "$QUELLE/offen/stand.txt" ]; then
  sed 's/^/         /' "$QUELLE/offen/stand.txt"
else
  warn "Kein offen/stand.txt. Ist das eine Sicherung von sichern.sh?"
fi

# Pruefsummen zuerst. Eine Sicherung von einer Platte, die im Auto
# lag, ist nicht immer die, die geschrieben wurde.
if [ -f "$QUELLE/pruefsummen.txt" ]; then
  if ( cd "$QUELLE" && sha256sum --quiet -c pruefsummen.txt 2>/dev/null ); then
    gut "Pruefsummen stimmen"
  else
    warn "Pruefsummen stimmen NICHT ueberall."
    info "Nachsehen:  cd \"$QUELLE\" && sha256sum -c pruefsummen.txt"
    info "Weitermachen kann richtig sein -- aber wissen sollte man es."
  fi
else
  warn "Keine Pruefsummen in der Sicherung."
fi

HAT_GEHEIM=nein
[ -f "$QUELLE/geheim.tar.gz.gpg" ] && HAT_GEHEIM=ja
if [ "$HAT_GEHEIM" = ja ]; then
  gut "geheim.tar.gz.gpg liegt vor"
else
  warn "Kein geheimer Teil in dieser Sicherung."
  GEHEIM=nein
fi

if [ "$NUR_PRUEFEN" = ja ]; then
  blau "Trockenlauf"
  info "Zurueckgespielt wuerde nach $ORDNER (und /etc, ~/.config)."
  [ -d "$QUELLE/offen/models" ] && info "models/  ($(du -sh "$QUELLE/offen/models" | cut -f1))"
  [ -d "$QUELLE/offen/voices" ] && info "voices/  ($(du -sh "$QUELLE/offen/voices" | cut -f1))"
  [ -d "$QUELLE/offen/devarenu-vorrat" ] && info "Reparaturvorrat"
  exit 0
fi

# ------------------------------------------------------- Der geheime Teil
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"; unset PASS' EXIT INT TERM
OFFEN_GEBLIEBEN=""

if [ "$GEHEIM" = ja ]; then
  blau "Geheimnisse"
  if ! command -v gpg >/dev/null; then
    fehl "gpg fehlt. Nachholen:  sudo pacman -S gnupg"
    exit 1
  fi
  printf '         Passphrase: '
  IFS= read -rs PASS; echo
  # Eigenes gpg-Heim, siehe sichern.sh.
  mkdir -p "$TMP/gpg"; chmod 700 "$TMP/gpg"
  if gpg --batch --quiet --decrypt --homedir "$TMP/gpg" --passphrase-fd 3 \
         "$QUELLE/geheim.tar.gz.gpg" 3< <(printf '%s' "$PASS") \
       | tar -xzf - -C "$TMP" 2>/dev/null; then
    gut "entschluesselt"
    unset PASS
  else
    unset PASS
    fehl "Das Entschluesseln ging nicht -- falsche Passphrase oder die"
    info "Datei ist beschaedigt."
    info "Der offene Teil laesst sich trotzdem zurueckspielen:"
    info "  bash zuruecksichern.sh \"$QUELLE\" --ohne-geheim"
    exit 1
  fi

  # Was schon dasteht, wird beiseitegelegt und nicht ueberschrieben.
  # Nach einer Neuinstallation steht dort die Vorgabe; die ist nichts
  # wert, aber sie wegzuwerfen, ohne sie gesehen zu haben, waere eine
  # Gewohnheit, die beim naechsten Mal wehtut.
  ALT="$ORDNER/.vorher-$(date +%Y%m%d-%H%M%S)"
  for d in zustand.json netz.json meldung.json; do
    q="$TMP/geheim/devarenu/$d"
    [ -f "$q" ] || continue
    if [ -f "$d" ]; then
      mkdir -p "$ALT"; cp -p "$d" "$ALT/$d"
    fi
    cp -p "$q" "$d" && gut "$d zurueckgespielt"
  done
  [ -d "$ALT" ] && info "Was vorher dastand, liegt in $(basename "$ALT")."
  # Rechte wieder herstellen: in zustand.json steht das WLAN-Passwort
  # im Klartext, in meldung.json das ntfy-Thema.
  chmod 600 zustand.json meldung.json 2>/dev/null || true
  chmod 644 netz.json 2>/dev/null || true
  gut "Rechte gesetzt (600 auf zustand.json und meldung.json)"

  if [ -n "$(ls -A "$TMP/geheim/nm" 2>/dev/null)" ]; then
    if $SUDO cp -a "$TMP/geheim/nm/." /etc/NetworkManager/system-connections/ \
       && $SUDO chown -R root:root /etc/NetworkManager/system-connections \
       && $SUDO chmod 600 /etc/NetworkManager/system-connections/* ; then
      gut "NetworkManager-Profile zurueckgespielt"
      $SUDO nmcli connection reload 2>/dev/null \
        && gut "NetworkManager hat sie neu gelesen"
    else
      warn "Die NetworkManager-Profile liessen sich nicht zurueckspielen."
      OFFEN_GEBLIEBEN="$OFFEN_GEBLIEBEN WLAN-Profile"
    fi
  fi

  if [ -n "$(ls -A "$TMP/geheim/rustdesk" 2>/dev/null)" ]; then
    mkdir -p "$HOME/.config/rustdesk"
    cp -a "$TMP/geheim/rustdesk/." "$HOME/.config/rustdesk/" \
      && gut "RustDesk-Einstellungen zurueckgespielt" \
      || { warn "RustDesk-Einstellungen gingen nicht."
           OFFEN_GEBLIEBEN="$OFFEN_GEBLIEBEN RustDesk"; }
  fi
else
  blau "Ohne Geheimnisse"
  info "Neu eintragen muss jemand:"
  info "  WLAN-Name und -Passwort   am Pult unter Einrichtung"
  info "  ntfy-Thema                in meldung.json (600!)"
  info "  RustDesk-Kennwort         in RustDesk selbst"
  info "  Wartungsfenster-Profil    bash wartungsfenster.sh --einschalten ..."
fi

# --------------------------------------------------------- Der offene Teil
blau "Modelle, Stimmen, Vorrat"
for o in models voices; do
  q="$QUELLE/offen/$o"
  [ -d "$q" ] || { warn "$o liegt nicht in der Sicherung."; continue; }
  info "$o wird kopiert, das dauert ..."
  if command -v rsync >/dev/null; then
    rsync -a "$q/" "$ORDNER/$o/" && gut "$o zurueckgespielt" \
      || warn "$o nicht vollstaendig."
  else
    cp -a "$q" "$ORDNER/" && gut "$o zurueckgespielt" \
      || warn "$o nicht vollstaendig."
  fi
done
if [ -d "$QUELLE/offen/devarenu-vorrat" ]; then
  info "Reparaturvorrat wird kopiert ..."
  $SUDO mkdir -p /opt \
    && $SUDO cp -a "$QUELLE/offen/devarenu-vorrat" /opt/ \
    && gut "Reparaturvorrat zurueckgespielt" \
    || warn "Der Vorrat liess sich nicht zurueckspielen."
fi
if [ -f "$QUELLE/offen/tongeraete.txt" ]; then
  gut "Die Tongeraeteliste von damals:"
  sed 's/^/           /' "$QUELLE/offen/tongeraete.txt"
  info "Stimmt die Nummer nicht mehr, am Pult die Tonquelle neu waehlen."
fi

blau "Danach"
info "1. bash pruefen.sh          -- sagt, was noch fehlt"
info "2. bash start.sh            -- oder der Dienst, falls eingerichtet"
info "3. Am Pult einmessen        -- die Mindestlautstaerke gehoert zum Raum,"
info "                               nicht zur Sicherung."
if [ -n "$OFFEN_GEBLIEBEN" ]; then
  warn "Offen geblieben:$OFFEN_GEBLIEBEN"
fi
exit 0
