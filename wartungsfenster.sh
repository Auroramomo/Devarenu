#!/usr/bin/env bash
# Das Wartungsfenster -- verbinden, trennen, wecken, ausschalten.
#
#   bash wartungsfenster.sh --zeigen       wie die Lage ist
#   bash wartungsfenster.sh --einschalten  Fenster einrichten
#   bash wartungsfenster.sh --ausschalten  Fenster abschalten
#   bash wartungsfenster.sh --autoupdate ja|nein
#   bash wartungsfenster.sh --pruefen      was jetzt zu tun ist (Timer)
#   bash wartungsfenster.sh --wecker       nur den BIOS-Wecker stellen
#
# Einschalten mit allen vier Angaben:
#
#   bash wartungsfenster.sh --einschalten "Gemeinde-WLAN" Do 18:00 22:00
#
# Die Werte werden geprueft, BEVOR etwas geschrieben wird, und zwar
# mit derselben Funktion, die sie spaeter auch liest. Was hier
# durchgeht, gilt auch fuer den Timer -- sonst stuende ein Fenster in
# netz.json, das er wortlos ignoriert.
#
# Gerechnet wird nicht hier, sondern in wartungsfenster.py. Diese
# Datei tut nur, was gesagt wurde -- getrennt, damit sich das Rechnen
# pruefen laesst, ohne dass ein Pruefstand einen Rechner ausschaltet.
#
# WAS HIER NIE PASSIERT
#
# Geleitet wird nichts. Zwischen dem WLAN und dem Saalnetz gibt es
# keinen Weg, im Fenster so wenig wie sonst -- das regelt firewall.sh,
# und pruefen.sh sieht nach. Und es wird nur das EINE Profil aus
# netz.json angefasst: ein Handy-Hotspot, den jemand vor Ort
# aufgemacht hat, bleibt unberuehrt. Wer davor sitzt, soll nicht
# mitten in der Arbeit ausgesperrt werden.

set -u
ORDNER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ORDNER"

PY="$ORDNER/.venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"
PORT="${DEVARENU_PORT:-8000}"

# Attrappen fuer den Pruefstand. Im Betrieb stehen hier die echten
# Befehle; der Pruefstand setzt sie auf ein Skript, das nur mitschreibt.
NMCLI="${DEVARENU_NMCLI:-nmcli}"
RTCWAKE="${DEVARENU_RTCWAKE:-rtcwake}"
AUSSCHALTEN="${DEVARENU_POWEROFF:-systemctl poweroff}"

blau() { printf '\n\033[1;34m== %s\033[0m\n' "$*"; }
gut()  { printf '   \033[32mok\033[0m   %s\n' "$*"; }
warn() { printf '   \033[33m!\033[0m    %s\n' "$*"; }
info() { printf '        %s\n' "$*"; }

LAGE="$("$PY" "$ORDNER/wartungsfenster.py" 2>/dev/null)" || {
  warn "wartungsfenster.py liess sich nicht ausfuehren. Nichts getan."
  exit 0; }
feld() { printf '%s\n' "$LAGE" | sed -n "s/^$1=//p"; }

AN="$(feld an)"; PROFIL="$(feld profil)"; IM_FENSTER="$(feld im_fenster)"
WECKER="$(feld wecker)"; WECKER_LESBAR="$(feld wecker_lesbar)"
AUTOUPDATE="$(feld autoupdate)"; NACH_UPDATE_AUS="$(feld nach_update_aus)"
BERICHTE="$(feld berichte_senden)"
FENSTERKENNUNG="$(feld fensterkennung)"
ABLAGE="${DEVARENU_DATEN:-/var/lib/devarenu/updates}"
BENUTZER="$(stat -c %U "$ORDNER" 2>/dev/null || id -un)"

# ------------------------------------------------------------- Wecker
# Bei jedem Hochfahren und jedem Herunterfahren neu gestellt. "-m no"
# heisst: nur den Wecker setzen, nicht schlafen legen. Die Zeit kommt
# als Unix-Sekunde, damit die Umrechnung von Ortszeit auf die UTC der
# Hardware-Uhr an genau einer Stelle passiert -- in Python, wo die
# Sommerzeit bekannt ist.
wecker_stellen() {
  # AUSDRUECKLICH: der Wecker wird NICHT angefasst.
  #
  # Am 27.09. stand er nach einem dienst.sh --fenster auf 15:59:59
  # statt vorher 16:00:00 -- war also neu geschrieben worden. Aus
  # dieser Fassung kann das nicht kommen: rtcwake wird genau an drei
  # Stellen aufgerufen, und alle drei sind hier unerreichbar, solange
  # das Fenster aus ist (die beiden anderen stehen in --ausschalten
  # und in dienst.sh --entfernen). Die eine Sekunde ist die Signatur
  # einer RELATIVEN Weckzeit: wer "-s $(( ziel - jetzt ))" rechnet,
  # verliert beim Abschneiden der Sekundenbruchteile regelmaessig
  # eine. Hier wird absolut gerechnet, mit "-t <Unix-Sekunde>".
  #
  # Damit es beim naechsten Mal nachweisbar ist, steht es im Journal.
  if [ "$AN" != ja ]; then
    gut "Fenster ist aus -- der Wecker bleibt unangetastet"
    return 0
  fi
  [ -n "$WECKER" ] || { warn "Kein naechster Fensterbeginn zu berechnen."; return 0; }
  if ! command -v "${RTCWAKE%% *}" >/dev/null; then
    warn "rtcwake fehlt. Der Rechner wacht nicht von selbst auf."
    info "Nachholen:  sudo pacman -S util-linux"
    return 0
  fi
  if $RTCWAKE -m no -t "$WECKER" >/dev/null 2>&1; then
    gut "Wecker steht auf $WECKER_LESBAR"
  else
    warn "rtcwake hat den Wecker nicht angenommen."
    info "Im BIOS: ErP aus, 'Power On By RTC' aus -- der Wecker kommt"
    info "vom Betriebssystem, nicht vom BIOS."
  fi
}

# ------------------------------------------------------------- WLAN
verbinden() {
  if $NMCLI -t -f NAME connection show --active 2>/dev/null \
     | grep -qxF "$PROFIL"; then
    gut "$PROFIL ist schon verbunden"
    return 0
  fi
  if $NMCLI connection up "$PROFIL" >/dev/null 2>&1; then
    gut "$PROFIL verbunden"
  else
    warn "$PROFIL liess sich nicht verbinden."
    info "Gibt es das Profil?  nmcli connection show"
  fi
}

trennen() {
  if ! $NMCLI -t -f NAME connection show --active 2>/dev/null \
       | grep -qxF "$PROFIL"; then
    return 0
  fi
  if $NMCLI connection down "$PROFIL" >/dev/null 2>&1; then
    gut "$PROFIL getrennt"
  else
    warn "$PROFIL liess sich nicht trennen. Nachsehen, das WLAN ist offen."
  fi
}

# ------------------------------------------------------- Autoupdate
# Laeuft nur im Fenster, nur mit Schalter, nur einmal je Fenster und
# nie waehrend einer Uebersetzung. Die Pruefung der Signatur macht
# aktualisieren.sh -- hier wird nichts gelockert, was dort gilt.
autoupdate_laufen() {
  [ "$AUTOUPDATE" = ja ] || return 1
  [ "$IM_FENSTER" = ja ] || return 1

  # Einmal je Fenster. Ohne diese Marke liefe der Updater alle fuenf
  # Minuten neu -- und nach einem Fehlschlag jedes Mal wieder in
  # denselben Fehlschlag.
  local marke="$ABLAGE/autoupdate-$FENSTERKENNUNG"
  if [ -f "$marke" ]; then
    return 1
  fi

  if [ "$(uebersetzung_laeuft)" = ja ]; then
    info "Es wird uebersetzt -- das Autoupdate wartet."
    return 1
  fi

  blau "Autoupdate"
  mkdir -p "$ABLAGE"
  : > "$marke"

  local vorher; vorher="$(tr -d '[:space:]' < "$ORDNER/VERSION" 2>/dev/null)"
  local protokoll="$ABLAGE/autoupdate-$FENSTERKENNUNG.log"
  local t0; t0="$(date +%s)"
  local rc=0

  # Als BENUTZER, nicht als Wurzel: dem gehoert das Repo. Liefen die
  # git-Befehle als root, blieben root-eigene Objekte in .git zurueck
  # und der Dienst kaeme an sein eigenes Repo nicht mehr heran.
  # aktualisieren.sh holt sich Privilegiertes selbst.
  if [ "$(id -u)" = 0 ] && [ "$BENUTZER" != root ]; then
    runuser -u "$BENUTZER" -- bash "$ORDNER/aktualisieren.sh" \
      > "$protokoll" 2>&1 || rc=$?
  else
    bash "$ORDNER/aktualisieren.sh" > "$protokoll" 2>&1 || rc=$?
  fi
  chmod 600 "$protokoll" 2>/dev/null || true

  local nachher; nachher="$(tr -d '[:space:]' < "$ORDNER/VERSION" 2>/dev/null)"
  local dauer=$(( $(date +%s) - t0 ))
  sed 's/\x1b\[[0-9;]*m//g' "$protokoll" | tail -20 | sed 's/^/   /'

  # Die Rueckmeldung, SOLANGE DAS WLAN NOCH STEHT. Nach dem
  # Herunterfahren ginge nichts mehr hinaus, und dann wuesste niemand,
  # dass etwas schiefging.
  local ergebnis
  if [ "$rc" = 0 ] && [ "$vorher" != "$nachher" ]; then
    ergebnis="eingespielt"
    gut "$vorher -> $nachher in ${dauer}s"
  elif [ "$rc" = 0 ]; then
    ergebnis="nichts zu tun"
    gut "kein neueres Tag, Fassung bleibt $nachher"
  else
    ergebnis="GESCHEITERT"
    warn "Das Autoupdate ist gescheitert (Rueckgabe $rc)."
  fi

  # Den Reparaturvorrat gleich mitziehen.
  #
  # Er traegt die Fassung, zu der er gebaut wurde; nach jedem Update
  # meldet der Systemcheck sonst "Der Vorrat gehoert zu Fassung X".
  # Das ist richtig und stand bisher jede Woche da -- und eine
  # Meldung, die nach jedem Update erscheint und nie etwas aufhaelt,
  # bringt einem bei, die Liste zu ueberblaettern.
  #
  # Nur nach einem gelungenen Update, nur solange das WLAN steht, und
  # ein Fehlschlag steht bloss in der Rueckmeldung: der Vorrat ist
  # eine Vorsichtsmassnahme, kein Betriebsmittel. Dass er eine
  # Fassung hinterherhinkt, hat noch nie einen Gottesdienst
  # aufgehalten.
  local vorrat_satz=""
  if [ "$ergebnis" = "eingespielt" ] && [ -f "$ORDNER/vorrat_bauen.sh" ]; then
    info "Reparaturvorrat wird nachgezogen ..."
    if bash "$ORDNER/vorrat_bauen.sh" >> "$protokoll" 2>&1; then
      gut "Vorrat auf $nachher nachgezogen"
      vorrat_satz="Vorrat nachgezogen."
    else
      warn "Der Vorrat liess sich nicht nachziehen."
      info "Kein Grund zur Eile -- er ist eine Vorsichtsmassnahme."
      vorrat_satz="Vorrat NICHT nachgezogen (siehe Protokoll)."
    fi
  fi

  # Die Rueckmeldung ZULETZT, damit der Vorrat darin vorkommt --
  # und solange das WLAN noch steht.
  if [ -f "$ORDNER/meldung.sh" ]; then
    bash "$ORDNER/meldung.sh" "Devarenu $(hostname): $ergebnis" \
"Fassung vorher:  ${vorher:-unbekannt}
Fassung nachher: ${nachher:-unbekannt}
Ergebnis:        $ergebnis
Dauer:           ${dauer}s
${vorrat_satz:+Vorrat:          $vorrat_satz}

$(sed 's/\x1b\[[0-9;]*m//g' "$protokoll" | tail -25)" >/dev/null 2>&1 \
      || warn "Die Rueckmeldung ging nicht hinaus, sie liegt vorgemerkt."
  fi

  # Erfolg oder nichts zu tun -> aus, wenn so eingestellt.
  # Fehlgeschlagen -> an bleiben. Der Rechner ist zurueckgerollt und
  # laeuft; bis zum Fensterende kann jemand nachsehen, was war.
  if [ "$ergebnis" = "GESCHEITERT" ]; then
    warn "Der Rechner bleibt bis Fensterende an, damit jemand nachsehen kann."
    info "$protokoll"
    return 0
  fi
  if [ "$NACH_UPDATE_AUS" = ja ]; then
    info "Nach dem Lauf wird heruntergefahren (nach_update_aus)."
    wecker_stellen
    $AUSSCHALTEN
  fi
  return 0
}

# --------------------------------------------------------- Auto-Aus
# Laeuft gerade eine Uebersetzung? Der Server weiss es; antwortet er
# nicht, gilt "nein". Ein Dienst, der nicht antwortet, uebersetzt auch
# nicht -- und ein Rechner, der ewig anbleibt, weil eine Abfrage
# fehlschlaegt, waere der falsche Ausgang.
uebersetzung_laeuft() {
  # Naht fuer den Pruefstand: eine laufende Uebersetzung laesst sich
  # ohne echten Dienst nicht herstellen, und ausgerechnet sie ist die
  # Bedingung, die den Gottesdienst schuetzt.
  if [ -n "${DEVARENU_UEBERSETZT_TEST:-}" ]; then
    echo "$DEVARENU_UEBERSETZT_TEST"; return 0
  fi
  "$PY" - <<PYCODE 2>/dev/null
import json, urllib.request
try:
    with urllib.request.urlopen(
            "http://127.0.0.1:$PORT/api/zustand", timeout=5) as a:
        print("ja" if json.load(a).get("live") else "nein")
except Exception:
    print("nein")
PYCODE
}

abschalten_pruefen() {
  local laeuft grund
  laeuft="$(uebersetzung_laeuft)"
  grund="$("$PY" - "$laeuft" <<'PYCODE' 2>/dev/null
import sys
sys.path.insert(0, ".")
import wartungsfenster as wf
lage, grund = wf.abschalten_faellig(sys.argv[1] == "ja")
print(f"{lage}|{grund}")
PYCODE
)"
  case "${grund%%|*}" in
    "") [ "$laeuft" = ja ] && info "Es wird uebersetzt -- das Auto-Aus wartet."
        return 0 ;;
    laufzeit_hart)
      warn "Abschaltung: ${grund#*|}"
      info "Auch eine laufende Uebersetzung haelt hier nicht mehr auf." ;;
    *)
      warn "Abschaltung: ${grund#*|}" ;;
  esac
  # Der Wecker ZUERST. Geht der Rechner aus, ohne dass er steht, kommt
  # er nicht von selbst wieder -- und dann hilft nur eine Fahrt.
  wecker_stellen
  info "Der Rechner faehrt jetzt herunter."
  $AUSSCHALTEN
}

# ------------------------------------------------------- Ein und Aus
einschalten() {
  local profil="${1:-}" tag="${2:-}" von="${3:-}" bis="${4:-}"
  if [ -z "$profil" ] || [ -z "$tag" ] || [ -z "$von" ] || [ -z "$bis" ]; then
    echo "So wird es benutzt:"
    echo "  bash wartungsfenster.sh --einschalten \"Gemeinde-WLAN\" Do 18:00 22:00"
    echo
    echo "Vorhandene WLAN-Profile:"
    $NMCLI -t -f NAME,TYPE connection show 2>/dev/null \
      | awk -F: '$2 ~ /wireless/ {print "  " $1}'
    return 2
  fi

  blau "Wartungsfenster einschalten"
  if ! "$PY" "$ORDNER/wartungsfenster.py" --setzen \
       "profil=$profil" "wochentag=$tag" "von=$von" "bis=$bis"; then
    warn "Nichts geaendert."
    return 1
  fi
  gut "netz.json: $tag $von-$bis ueber \"$profil\""

  # autoconnect no gehoert dazu, sonst ist das Fenster eine
  # Verabredung ohne Wirkung: NetworkManager verbaende sich auch
  # ausserhalb, und der Rechner haenge die ganze Woche im WLAN.
  if $NMCLI -t -f NAME connection show 2>/dev/null | grep -qxF "$profil"; then
    if $NMCLI connection modify "$profil" connection.autoconnect no \
       >/dev/null 2>&1; then
      gut "\"$profil\" steht auf autoconnect no"
    else
      warn "autoconnect liess sich nicht umstellen -- von Hand:"
      info "nmcli connection modify \"$profil\" connection.autoconnect no"
    fi
  else
    warn "Ein Profil \"$profil\" gibt es hier nicht."
    info "Das Fenster steht trotzdem in netz.json und geht nie auf."
    info "Nachsehen:  nmcli connection show"
  fi

  # Frisch einlesen: LAGE stammt vom Skriptanfang, also von vorher.
  LAGE="$("$PY" "$ORDNER/wartungsfenster.py" 2>/dev/null)"
  AN="$(feld an)"; PROFIL="$(feld profil)"; IM_FENSTER="$(feld im_fenster)"
  WECKER="$(feld wecker)"; WECKER_LESBAR="$(feld wecker_lesbar)"
  wecker_stellen
  zeigen
}

zeigen() {
  blau "Wartungsfenster"
  if [ "$AN" != ja ]; then
    info "aus. Einschalten mit:"
    info "  bash wartungsfenster.sh --einschalten \"<Profil>\" Do 18:00 22:00"
    return 0
  fi
  gut "an, Profil $PROFIL"
  info "gerade im Fenster: $IM_FENSTER"
  info "naechster Beginn:  $(feld beginn)"
  info "Wecker:            $WECKER_LESBAR"
  info "Laufzeit:          $(feld laufzeit_h) h von $(feld hoechstlaufzeit_h) h"
  info "                   (hart: $(feld hoechstlaufzeit_hart_h) h)"
  info "Autoupdate:        $AUTOUPDATE (danach aus: $NACH_UPDATE_AUS)"
  info "Fehlerberichte:    $BERICHTE"
  [ "$AUTOUPDATE" = ja ] && bash "$ORDNER/meldung.sh" --zeigen | sed 's/^/        /'
  return 0
}

# --------------------------------------------------------------- Lauf
case "${1:---zeigen}" in
  --einschalten)
    shift; einschalten "$@"; exit $? ;;

  --ausschalten)
    blau "Wartungsfenster ausschalten"
    "$PY" "$ORDNER/wartungsfenster.py" --aus || {
      warn "netz.json liess sich nicht schreiben."; exit 1; }
    gut "aus. Profil und Uhrzeit bleiben stehen."
    # Den gestellten Wecker zuruecknehmen, sonst schaltet er den
    # Rechner noch einmal grundlos ein.
    if command -v "${RTCWAKE%% *}" >/dev/null; then
      $RTCWAKE -m disable >/dev/null 2>&1 && gut "Wecker geloescht"
    fi
    # Und das WLAN trennen, falls gerade Fenster war. Ein
    # ausgeschaltetes Fenster, das die Verbindung stehen laesst, waere
    # genau die Lage, die es zu vermeiden gilt.
    [ "$IM_FENSTER" = ja ] && [ -n "$PROFIL" ] && trennen
    exit 0 ;;

  --berichte)
    blau "Fehlerberichte"
    if ! "$PY" "$ORDNER/wartungsfenster.py" --schalter \
         "berichte_senden=${2:-}"; then
      exit 1
    fi
    gut "${2:-} -- im Fenster gehen vorgemerkte Berichte hinaus"
    exit 0 ;;

  --autoupdate)
    blau "Autoupdate"
    if ! "$PY" "$ORDNER/wartungsfenster.py" --schalter \
         "autoupdate=${2:-}"; then
      exit 1
    fi
    if [ "${2:-}" = ja ]; then
      gut "an -- im Fenster wird von selbst aktualisiert"
      info "Nur signierte Tags, nie waehrend einer Uebersetzung,"
      info "und bei einem Fehlschlag geht es von selbst zurueck."
      bash "$ORDNER/meldung.sh" --zeigen | sed 's/^/        /'
    else
      gut "aus"
    fi
    exit 0 ;;

  --wecker)
    wecker_stellen ;;

  --pruefen)
    if [ "$AN" != ja ]; then
      # Kein Wort, kein Eingriff. Diese Fassung laeuft auch auf
      # Rechnern, auf denen es gar kein Fenster gibt, und der Timer
      # tickt dort alle fuenf Minuten.
      exit 0
    fi
    if [ "$IM_FENSTER" = ja ]; then
      verbinden
      # Erst verbinden, dann aktualisieren: ohne Netz gaebe es nichts
      # zu holen, und die Rueckmeldung ginge auch nicht hinaus.
      #
      # Die Fehlerberichte ZUERST. Geht das Update schief und der
      # Rechner faehrt herunter, waeren sie sonst eine Woche liegen
      # geblieben -- und gerade dann will man sie lesen.
      if [ "$BERICHTE" = ja ] && [ -f "$ORDNER/meldung.sh" ]; then
        bash "$ORDNER/meldung.sh" --berichte | sed 's/^/   /'
      fi
      autoupdate_laufen || true
    else
      trennen
    fi
    abschalten_pruefen ;;

  --zeigen)
    zeigen ;;

  *)
    echo "Unbekannt: $1"
    echo "  --zeigen | --einschalten | --ausschalten"
    echo "  --autoupdate ja|nein | --berichte ja|nein"
    echo "  --pruefen | --wecker"
    exit 2 ;;
esac
