#!/usr/bin/env bash
# Stellt den Gemeinderechner so ein, dass er sonntags allein hochkommt.
#
#   bash rechner_einrichten.sh --trocken   nur zeigen, nichts aendern
#   sudo bash rechner_einrichten.sh        einrichten
#   bash rechner_einrichten.sh --help      diese Hilfe
#
# Scharf laeuft es NUR auf einem Rechner, dessen Name in netz.json
# steht -- derselbe Schutz wie bei netz_einrichten.sh. Die
# Einstellungen gelten fuer den ganzen Rechner, nicht nur fuer
# Devarenu: automatische Anmeldung ohne Passwort, keine
# Bildschirmsperre. Auf einem Arbeitsrechner waere das ein Griff ins
# Gesicht. --trocken laeuft ueberall.
#
# Was es setzt:
#   - automatische Anmeldung, Sitzung X11
#   - Netzschalter faehrt herunter, kein Standby von selbst
#   - Bildschirm bleibt an, keine Bildschirmsperre
#   - leere Sitzung beim Anmelden, keine Rueckfrage beim Abmelden
#
# Was es NICHT anfasst: das Netz. Dafuer gibt es netz_einrichten.sh,
# und das laeuft nur von Hand vor Ort.
#
# Mehrfach ausfuehrbar: was schon stimmt, bleibt stehen, und jede
# Aenderung wird genannt. Wer wissen will, was fehlt, ohne etwas zu
# aendern, nimmt bash pruefen.sh -- Abschnitt Rechner-Einstellungen.
#
# Geprueft auf CachyOS mit Plasma 6 und Plasma Login Manager. Auf
# einem anderen Anmeldemanager (SDDM) wird der passende Ordner
# gesucht; findet sich keiner, sagt es das, statt zu raten.

set -u
ORDNER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ORDNER"

TROCKEN=nein

blau() { printf '\n\033[1;34m== %s\033[0m\n' "$*"; }
gut()  { printf '   \033[32mok\033[0m    %s\n' "$*"; }
neu()  { printf '   \033[36mneu\033[0m   %s\n' "$*"; }
warn() { printf '   \033[33m!\033[0m     %s\n' "$*"; }
fehl() { printf '   \033[31mFEHLT\033[0m %s\n' "$*"; }
info() { printf '         %s\n' "$*"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --trocken)          TROCKEN=ja; shift ;;
    -h|--hilfe|--help|-\?)
                        sed -n '2,24p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)                  fehl "Unbekannt: $1"; exit 1 ;;
  esac
done

# Wem gehoert die Sitzung? Unter sudo ist das nicht die Wurzel.
BENUTZER="${SUDO_USER:-$(id -un)}"
HEIM="$(getent passwd "$BENUTZER" | cut -d: -f6)"
[ -n "$HEIM" ] || { fehl "Kein Heimatverzeichnis fuer $BENUTZER."; exit 1; }

printf '\033[1mDevarenu -- Rechner einrichten\033[0m   %s auf %s\n' \
  "$(date '+%d.%m.%Y %H:%M')" "$(hostname)"
info "Benutzer $BENUTZER, Heimat $HEIM"
[ "$TROCKEN" = ja ] && warn "Trockenlauf: es wird nichts geaendert."

# ------------------------------------------- Ist das der richtige Rechner?
# Dieselbe Sperre wie in netz_einrichten.sh, und aus demselben Grund:
# dasselbe Verzeichnis liegt auf dem Arbeitsrechner, auf dem Devarenu
# entsteht. Wer dort scharf laeuft, hat danach keine Bildschirmsperre
# mehr und meldet sich ohne Passwort an.
#
# --trocken darf ueberall laufen: es aendert nichts und beantwortet
# genau die Frage "was waere zu tun?".
if [ "$TROCKEN" != ja ]; then
  PY="$ORDNER/.venv/bin/python"
  [ -x "$PY" ] || PY="$(command -v python3)"
  RECHNER="$(hostname 2>/dev/null || cat /etc/hostname 2>/dev/null)"
  PASST="$("$PY" - "$RECHNER" 2>/dev/null <<'PYCODE'
import fnmatch, sys
sys.path.insert(0, ".")
try:
    import netzzustand
    muster = [str(m).strip().lower()
              for m in netzzustand.laden()[0]["rechner"] if str(m).strip()]
except Exception:
    muster = []
name = (sys.argv[1] or "").strip().lower()
if not muster:
    print("leer")
elif any(fnmatch.fnmatch(name, m) for m in muster):
    print("ja")
else:
    print("nein")
PYCODE
)"
  case "${PASST:-leer}" in
    ja) gut "Rechnername $RECHNER steht in netz.json" ;;
    leer)
      fehl "In netz.json steht kein erlaubter Rechnername."
      info "Diese Einstellungen gelten fuer den GANZEN Rechner:"
      info "Anmeldung ohne Passwort, keine Bildschirmsperre. Deshalb"
      info "laeuft es nur dort scharf, wo es hingehoert."
      info ""
      info "Sehen, was fehlt (aendert nichts):"
      info "  bash rechner_einrichten.sh --trocken"
      info "Diesen Rechner freigeben:"
      info "  bash netz_einrichten.sh --rechner-eintragen"
      exit 1 ;;
    *)
      fehl "Rechnername $RECHNER steht nicht in netz.json."
      info "Ist das hier wirklich der Gemeinderechner?"
      info "Sehen, was fehlt (aendert nichts):"
      info "  bash rechner_einrichten.sh --trocken"
      exit 1 ;;
  esac
fi

AENDERUNGEN=0

# Setzt einen Plasma-Wert, aber nur wenn er abweicht.
# $1 Datei  $2.. Gruppen  --key $k $wert
setze() {
  local datei="$1"; shift
  local gruppen=() schluessel="" wert=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --key)  schluessel="$2"; shift 2 ;;
      --wert) wert="$2"; shift 2 ;;
      *)      gruppen+=("$1"); shift ;;
    esac
  done
  local lesen=(kreadconfig6 --file "$datei")
  local schreiben=(kwriteconfig6 --file "$datei")
  local g
  for g in "${gruppen[@]}"; do
    lesen+=(--group "$g"); schreiben+=(--group "$g")
  done
  lesen+=(--key "$schluessel")
  schreiben+=(--key "$schluessel" "$wert")

  local ist
  ist="$(sudo -u "$BENUTZER" "${lesen[@]}" 2>/dev/null)"
  if [ "$ist" = "$wert" ]; then
    gut "$datei ${gruppen[*]} $schluessel = $wert"
    return 0
  fi
  if [ "$TROCKEN" = ja ]; then
    neu "$datei ${gruppen[*]} $schluessel: ${ist:-(nicht gesetzt)} -> $wert"
    AENDERUNGEN=$((AENDERUNGEN+1))
    return 0
  fi
  if sudo -u "$BENUTZER" "${schreiben[@]}" 2>/dev/null; then
    neu "$datei ${gruppen[*]} $schluessel: ${ist:-(nicht gesetzt)} -> $wert"
    AENDERUNGEN=$((AENDERUNGEN+1))
  else
    fehl "$datei $schluessel liess sich nicht setzen."
  fi
}

# ------------------------------------------------- Automatische Anmeldung
blau "Automatische Anmeldung"
# Ohne sie steht der Rechner am Anmeldebildschirm. Und ohne angemeldete
# Sitzung gibt es keinen PulseAudio-Server, also keinen Ton -- daran
# hing der Rollout monatelang.
ANMELDE_ORDNER=""
for kandidat in /etc/plasmalogin.conf.d /etc/sddm.conf.d; do
  if [ -d "$kandidat" ] || [ -d "$(dirname "$kandidat")" ]; then
    ANMELDE_ORDNER="$kandidat"; break
  fi
done
if [ -z "$ANMELDE_ORDNER" ]; then
  fehl "Kein Ordner fuer den Anmeldemanager gefunden."
  info "Geprueft: /etc/plasmalogin.conf.d und /etc/sddm.conf.d"
  info "Von Hand einrichten, siehe AUFSTELLEN.md."
else
  ANMELDE_DATEI="$ANMELDE_ORDNER/zzz-devarenu-autologin.conf"
  # zzz- im Namen, damit die Datei zuletzt gelesen wird: der
  # Anmeldemanager liest den Ordner alphabetisch, und was spaeter
  # kommt, gewinnt.
  SOLL="[Autologin]
User=$BENUTZER
Session=plasmax11
Relogin=false"
  if [ -f "$ANMELDE_DATEI" ] && [ "$(cat "$ANMELDE_DATEI")" = "$SOLL" ]; then
    gut "$ANMELDE_DATEI steht richtig"
  elif [ "$TROCKEN" = ja ]; then
    neu "$ANMELDE_DATEI wuerde geschrieben:"
    printf '%s\n' "$SOLL" | sed 's/^/           /'
    AENDERUNGEN=$((AENDERUNGEN+1))
  elif [ "$(id -u)" != "0" ]; then
    fehl "$ANMELDE_DATEI braucht Wurzelrechte."
    info "  sudo bash rechner_einrichten.sh"
  else
    mkdir -p "$ANMELDE_ORDNER"
    printf '%s\n' "$SOLL" > "$ANMELDE_DATEI"
    chmod 644 "$ANMELDE_DATEI"
    neu "$ANMELDE_DATEI geschrieben"
    AENDERUNGEN=$((AENDERUNGEN+1))
  fi
  # Eine von Hand angelegte Datei mit demselben Zweck waere eine
  # zweite Wahrheit. Gemeldet, nicht geloescht: sie koennte von
  # jemandem stammen, der wusste, was er tat.
  for andere in "$ANMELDE_ORDNER"/*.conf; do
    [ -f "$andere" ] || continue
    [ "$andere" = "$ANMELDE_DATEI" ] && continue
    if grep -qi "^\[Autologin\]" "$andere" 2>/dev/null; then
      warn "$andere regelt die automatische Anmeldung ebenfalls."
      info "Welche gewinnt, entscheidet die alphabetische Reihenfolge."
    fi
  done

  # Session=plasmax11 hinzuschreiben ist das eine, sie zu bekommen das
  # andere. Der Anmeldemanager sucht plasmax11.desktop; findet er die
  # Datei nicht, nimmt er wortlos die einzige Sitzung, die da ist --
  # auf einem Arch ohne plasma-x11-session ist das Wayland. Die
  # Einstellung stand dann richtig da, gruen gemeldet, und der Rechner
  # lief trotzdem unter Wayland. Genau so stand der Gemeinderechner.
  #
  # Hier wird nur nachgesehen und gesagt, was ist. Am Anmeldeverfahren
  # aendert diese Fassung nichts: welche Sitzung laufen soll, ist eine
  # Entscheidung und kein Versehen.
  X11_DA=nein
  for ordner in /usr/share/xsessions /usr/local/share/xsessions; do
    [ -f "$ordner/plasmax11.desktop" ] && X11_DA=ja
  done
  if [ "$X11_DA" = nein ]; then
    warn "Eine Sitzung plasmax11 gibt es auf diesem Rechner nicht."
    info "Die Einstellung oben zeigt damit ins Leere -- der"
    info "Anmeldemanager nimmt die Sitzung, die er hat (Wayland)."
    info "Fehlt das Paket (Arch: plasma-x11-session), nachinstallieren"
    info "-- oder bei Wayland bleiben und den Ton nachmessen."
    info "Diese Einrichtung aendert daran nichts."
  fi

  # Und was laeuft gerade? Aus loginctl, nicht aus XDG_SESSION_TYPE:
  # unter sudo ist die Umgebung nicht mehr die der Sitzung.
  LAEUFT=""
  if command -v loginctl >/dev/null; then
    for kennung in $(loginctl list-sessions --no-legend 2>/dev/null \
                     | awk '{print $1}'); do
      typ=$(loginctl show-session "$kennung" -p Type --value 2>/dev/null)
      klasse=$(loginctl show-session "$kennung" -p Class --value 2>/dev/null)
      [ "$klasse" = user ] || continue
      case "$typ" in x11|wayland) LAEUFT="$typ"; break;; esac
    done
  fi
  if [ -n "$LAEUFT" ]; then
    if [ "$LAEUFT" = x11 ]; then
      gut "Es laeuft gerade eine X11-Sitzung"
    else
      warn "Es laeuft gerade eine $LAEUFT-Sitzung, geprueft ist X11."
      info "Der Tonweg ist unter Wayland nicht gemessen -- er kann"
      info "laufen, nur weiss es niemand. Selbsttest gibt Auskunft:"
      info "  python3 selbsttest.py"
    fi
  fi
fi

# --------------------------------------------------------------- Energie
blau "Energie und Bildschirm"
if ! command -v kwriteconfig6 >/dev/null; then
  fehl "kwriteconfig6 fehlt -- ist das ueberhaupt Plasma 6?"
  info "Ohne das Programm laesst sich hier nichts setzen."
else
  # 8 = Herunterfahren, 0 = nichts tun. Belegt: bei PowerButtonAction=8
  # zeigt die Energieverwaltung von Plasma "Herunterfahren" an.
  setze powerdevilrc AC SuspendAndShutdown --key PowerButtonAction --wert 8
  setze powerdevilrc AC SuspendAndShutdown --key AutoSuspendAction --wert 0
  setze powerdevilrc AC Display --key TurnOffDisplayWhenIdle --wert false
  setze powerdevilrc AC Display --key TurnOffDisplayIdleTimeoutSec --wert -1

  # Bildschirmsperre. Beides aus: Autolock schnappt nach einer Weile
  # zu, LockOnResume nach dem Aufwachen.
  setze kscreenlockerrc Daemon --key Autolock --wert false
  setze kscreenlockerrc Daemon --key LockOnResume --wert false

  # Sitzung: leer anfangen, nicht nachfragen.
  setze ksmserverrc General --key loginMode --wert emptySession
  setze ksmserverrc General --key confirmLogout --wert false
fi

# ---------------------------------------------------------------- Fertig
blau "Fertig"
if [ "$TROCKEN" = ja ]; then
  if [ "$AENDERUNGEN" -eq 0 ]; then
    gut "Es gibt nichts zu tun."
  else
    info "$AENDERUNGEN Aenderung(en) waeren noetig. Scharf:"
    info "  sudo bash rechner_einrichten.sh"
  fi
else
  if [ "$AENDERUNGEN" -eq 0 ]; then
    gut "Alles stand schon richtig."
  else
    info "$AENDERUNGEN Aenderung(en)."
    info "Die Plasma-Werte gelten ab der naechsten Anmeldung."
    info "Die automatische Anmeldung ab dem naechsten Start."
  fi
fi
info "Nachsehen:  bash pruefen.sh   Abschnitt Rechner-Einstellungen"
