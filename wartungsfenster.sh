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
# Die Unit, die den Wecker als root stellt. Der laengere Name ist
# Absicht, siehe devarenu-fenster-wecker.service.vorlage.
WECKER_UNIT_NAME="${DEVARENU_WECKER_UNIT:-devarenu-fenster-wecker.service}"
# Auch systemctl als Attrappe setzbar. Der Pruefstand soll den Weg
# "Knopf gedrueckt -> Update gelaufen" durchspielen koennen, ohne
# Dienste auf dem Rechner anzufassen, auf dem er laeuft.
SYSTEMCTL="${DEVARENU_SYSTEMCTL:-systemctl}"

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
  # DER WECKER SITZT IN /dev/rtc0, UND DAS GEHOERT root:clock 0660.
  #
  # Wer den Dienstbenutzer nimmt und "wartungsfenster.sh --einschalten"
  # von Hand aufruft, kommt dort nicht hinein. Bis 0.3.7 stand danach
  # "rtcwake hat den Wecker nicht angenommen" samt BIOS-Hinweis --
  # und wer dem folgte, schraubte am falschen Ende: das BIOS war in
  # Ordnung, es fehlten Rechte.
  #
  # Darum drei Wege, in dieser Reihenfolge:
  #   1. geradeaus. Als root (so laeuft die Wecker-Unit) und fuer
  #      jeden, der in der Gruppe clock steht, reicht das.
  #   2. sudo ohne Rueckfrage. Greift, wo eine Regel es erlaubt.
  #   3. die Wecker-Unit neu starten. Sie laeuft als root und ruft
  #      genau dieses Skript mit --wecker auf -- dort greift dann
  #      Weg 1. Das ist der saubere Weg, und er ist es auch dann,
  #      wenn niemand am Rechner sitzt.
  # Sitzt jemand davor, darf sudo am Ende noch nach dem Passwort
  # fragen. Ein Wecker, der schweigend ungestellt bleibt, ist
  # schlimmer als eine Frage.
  local aus="" rc=0 weg=""
  aus="$($RTCWAKE -m no -t "$WECKER" 2>&1)"; rc=$?
  if [ "$rc" = 0 ]; then
    weg=geradeaus
  elif [ "$(id -u)" != 0 ] && command -v sudo >/dev/null; then
    if aus="$(sudo -n $RTCWAKE -m no -t "$WECKER" 2>&1)"; then
      rc=0; weg="sudo"
    elif sudo -n systemctl restart "$WECKER_UNIT_NAME" >/dev/null 2>&1; then
      rc=0; weg="die Unit $WECKER_UNIT_NAME"
    elif [ -t 0 ] && [ "${DEVARENU_KEIN_SUDO:-}" != 1 ]; then
      info "Der Wecker braucht root. sudo fragt gleich nach dem Passwort."
      if aus="$(sudo $RTCWAKE -m no -t "$WECKER" 2>&1)"; then
        rc=0; weg="sudo"
      fi
    fi
  fi

  if [ "$rc" = 0 ]; then
    gut "Wecker steht auf $WECKER_LESBAR${weg:+ (ueber $weg)}"
    return 0
  fi

  # Fehlende Rechte oder ein widerspenstiges BIOS -- das sind zwei
  # verschiedene Befunde mit zwei verschiedenen Abhilfen, und sie
  # gehoeren auseinandergehalten.
  if printf '%s' "$aus" | grep -qiE \
       'permission|berechtigung|not permitted|nicht erlaubt|denied|EACCES|EPERM'; then
    warn "Der Wecker liess sich nicht stellen: fehlende Rechte, nicht das BIOS."
    info "Die Uhr /dev/rtc0 gehoert root:clock 0660. Einer von drei Wegen:"
    info "  sudo systemctl restart $WECKER_UNIT_NAME   (stellt ihn als root)"
    info "  sudo usermod -aG clock $(id -un)           (danach neu anmelden)"
    info "  sudo $RTCWAKE -m no -t $WECKER             (einmalig von Hand)"
  else
    warn "rtcwake hat den Wecker nicht angenommen."
    info "Im BIOS: ErP aus, 'Power On By RTC' aus -- der Wecker kommt"
    info "vom Betriebssystem, nicht vom BIOS."
  fi
  [ -n "$aus" ] && info "rtcwake sagte: $(printf '%s' "$aus" | head -1)"
  return 0
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

# --------------------------------------------------- Nutzungsmeldung
# Dem Entwickler sagen, dass es hier laeuft. Gemeindename, Fassung,
# Datum -- SONST NICHTS.
#
# Der Schalter steht in zustand.json und wird am Pult gesetzt, wo
# auch steht, was gesendet wird. Vorgabe aus. Hoechstens einmal je
# Fenster, sonst ginge sie alle fuenf Minuten hinaus.
#
# Das Ziel ist derselbe Kanal wie alles andere: meldung.json auf
# diesem Rechner. Es steht kein Meldeziel im Code.
nutzung_melden() {
  [ -f "$ORDNER/meldung.sh" ] || return 0
  [ -f "$ORDNER/meldung.json" ] || return 0

  local an gemeinde
  an="$("$PY" - <<'PYCODE' 2>/dev/null
import sys
sys.path.insert(0, ".")
import zustand
z = zustand.laden()[0]
print("ja" if z.get("nutzung_melden") else "nein")
print(z.get("gemeinde") or "")
PYCODE
)"
  gemeinde="$(printf '%s\n' "$an" | sed -n 2p)"
  an="$(printf '%s\n' "$an" | sed -n 1p)"
  [ "$an" = ja ] || return 0

  local marke="$ABLAGE/nutzung-$FENSTERKENNUNG"
  [ -f "$marke" ] && return 0
  mkdir -p "$ABLAGE"; chmod 711 "$ABLAGE" 2>/dev/null || true
  : > "$marke"

  local fassung; fassung="$(tr -d '[:space:]' < "$ORDNER/VERSION" 2>/dev/null)"
  if bash "$ORDNER/meldung.sh" "Devarenu: Nutzung" \
"Gemeinde: ${gemeinde:-(ohne Namen)}
Fassung:  ${fassung:-unbekannt}
Datum:    $(date '+%Y-%m-%d')" >/dev/null 2>&1; then
    gut "Nutzungsmeldung abgeschickt"
  else
    warn "Die Nutzungsmeldung ging nicht hinaus, sie liegt vorgemerkt."
  fi
}

# ------------------------------------------------------- Autoupdate
# Laeuft nur im Fenster, nur mit Schalter, nur einmal je Fenster und
# nie waehrend einer Uebersetzung. Die Pruefung der Signatur macht
# aktualisieren.sh -- hier wird nichts gelockert, was dort gilt.
# --------------------------------------------- Der Kern eines Updates
#
# Dieselben Schritte fuer beide Wege: das Autoupdate im Fenster und den
# Knopf "Jetzt aktualisieren" am Pult. Was sich unterscheidet, ist die
# Vorbedingung drumherum -- nicht das Einspielen selbst. Zwei Kopien
# davon waeren zwei Baustellen.
#
# Rueckgabe ueber Globale, weil bash keine Verbuende kennt.
KERN_VORHER="" KERN_NACHHER="" KERN_DAUER="" KERN_ERGEBNIS="" KERN_VORRAT=""

update_kern() {  # $1 Anlass (fuer die Meldungen), $2 Protokolldatei
  local anlass="$1" protokoll="$2" rc=0 t0
  KERN_VORHER="$(tr -d '[:space:]' < "$ORDNER/VERSION" 2>/dev/null)"
  t0="$(date +%s)"

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

  KERN_NACHHER="$(tr -d '[:space:]' < "$ORDNER/VERSION" 2>/dev/null)"
  KERN_DAUER=$(( $(date +%s) - t0 ))
  sed 's/\x1b\[[0-9;]*m//g' "$protokoll" | tail -20 | sed 's/^/   /'

  if [ "$rc" = 0 ] && [ "$KERN_VORHER" != "$KERN_NACHHER" ]; then
    KERN_ERGEBNIS="eingespielt"
    gut "$KERN_VORHER -> $KERN_NACHHER in ${KERN_DAUER}s"
  elif [ "$rc" = 0 ]; then
    KERN_ERGEBNIS="nichts zu tun"
    gut "kein neueres Tag, Fassung bleibt $KERN_NACHHER"
  else
    KERN_ERGEBNIS="GESCHEITERT"
    warn "$anlass ist gescheitert (Rueckgabe $rc)."
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
  # eine Vorsichtsmassnahme, kein Betriebsmittel.
  KERN_VORRAT=""
  if [ "$KERN_ERGEBNIS" = "eingespielt" ] && [ -f "$ORDNER/vorrat_bauen.sh" ]; then
    info "Reparaturvorrat wird nachgezogen ..."
    if bash "$ORDNER/vorrat_bauen.sh" >> "$protokoll" 2>&1; then
      gut "Vorrat auf $KERN_NACHHER nachgezogen"
      KERN_VORRAT="Vorrat nachgezogen."
    else
      warn "Der Vorrat liess sich nicht nachziehen."
      info "Kein Grund zur Eile -- er ist eine Vorsichtsmassnahme."
      KERN_VORRAT="Vorrat NICHT nachgezogen (siehe Protokoll)."
    fi
  fi
  return 0
}

# Die Rueckmeldung, SOLANGE DAS WLAN NOCH STEHT. Nach dem
# Herunterfahren ginge nichts mehr hinaus, und dann wuesste niemand,
# dass etwas schiefging.
update_melden() {  # protokoll vorher nachher ergebnis dauer vorrat
  [ -f "$ORDNER/meldung.sh" ] || return 0
  bash "$ORDNER/meldung.sh" "Devarenu $(hostname): $4" \
"Fassung vorher:  ${2:-unbekannt}
Fassung nachher: ${3:-unbekannt}
Ergebnis:        $4
Dauer:           ${5}s
${6:+Vorrat:          $6}

$(sed 's/\x1b\[[0-9;]*m//g' "$1" | tail -25)" >/dev/null 2>&1 \
    || warn "Die Rueckmeldung ging nicht hinaus, sie liegt vorgemerkt."
}

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
  chmod 711 "$ABLAGE" 2>/dev/null || true
  : > "$marke"

  local protokoll="$ABLAGE/autoupdate-$FENSTERKENNUNG.log"
  update_kern "Autoupdate" "$protokoll"
  local vorher="$KERN_VORHER" nachher="$KERN_NACHHER"
  local dauer="$KERN_DAUER" ergebnis="$KERN_ERGEBNIS"

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
  local vorrat_satz="$KERN_VORRAT"
  update_melden "$protokoll" "$vorher" "$nachher" "$ergebnis" \
                "$dauer" "$vorrat_satz"

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

# -------------------------------------- Der Knopf "Jetzt aktualisieren"
#
# WARUM EIN MARKER UND KEIN sudo
#
# Der Server laeuft als devarenu, das Update braucht root. Statt einer
# sudo-Regel, die dauerhaft offenstuende, legt der Server eine Datei an
# -- update/online-jetzt -- und ein Timer, der als root laeuft, sieht
# alle 30 Sekunden danach. Derselbe Weg, den der Stick-Knopf seit
# 0.2.12 geht, und derselbe Grund: der Dienst bekommt kein einziges
# Recht mehr, als er ohnehin hat. Er kann eine Datei in seinem eigenen
# Ordner anlegen. Mehr nicht.
#
# Der Preis sind bis zu 30 Sekunden Wartezeit. Die stehen am Pult, denn
# sonst drueckt jemand ein zweites Mal.
LAUF_DATEI="$ORDNER/update/online-lauf.json"
MARKE_JETZT="$ORDNER/update/online-jetzt"
# Laenger als das hier darf ein Lauf nicht "laeuft" melden. Danach ist
# etwas dazwischengekommen -- Strom weg, Dienst erschlagen -- und die
# Datei luegt. 20 Minuten: aktualisieren.sh samt Selbsttest und Vorrat
# braucht im schlechtesten Fall ein paar Minuten.
LAUF_FRIST=1200

lauf_schreiben() {  # lage schritt [text]
  mkdir -p "$ORDNER/update" 2>/dev/null || true
  cat > "$LAUF_DATEI" <<ENDE
{
  "lage": "$1",
  "schritt": "$2",
  "text": "${3:-}",
  "seit": ${LAUF_SEIT:-$(date +%s)},
  "zeit": "$(date '+%Y-%m-%d %H:%M:%S')"
}
ENDE
  chmod 644 "$LAUF_DATEI" 2>/dev/null || true
  chown "$BENUTZER" "$LAUF_DATEI" 2>/dev/null || true
}

# Steht schon eine Verbindung? Dann ist das der Hotspot, den der
# Helfer eben per Klick verbunden hat -- und der soll benutzt werden,
# nicht getrennt. "connected" ist die Antwort von NetworkManager,
# wenn irgendeine Verbindung traegt.
netz_steht() {
  [ "$($NMCLI -t -f STATE general 2>/dev/null | head -1)" = connected ]
}

jetzt_laufen() {
  LAUF_SEIT="$(date +%s)"
  blau "Jetzt aktualisieren (vom Pult angestossen)"

  if [ "$(id -u)" != 0 ]; then
    warn "Dieser Weg laeuft als root, ueber devarenu-onlineupdate.service."
    info "Von Hand geht es einfacher:  bash aktualisieren.sh"
    return 1
  fi

  # Die Marke ZUERST weg. Geht unten etwas schief, soll der Timer es
  # nicht in dreissig Sekunden erneut versuchen -- und nach einem
  # Fehlschlag jedes Mal wieder in denselben Fehlschlag.
  rm -f "$MARKE_JETZT"

  if [ "$(uebersetzung_laeuft)" = ja ]; then
    warn "Es wird uebersetzt. Das Update wartet."
    lauf_schreiben gescheitert uebersetzung \
      "Es wird uebersetzt. Erst die Uebersetzung anhalten."
    return 1
  fi

  # Der Fenster-Timer aus, solange der Lauf geht. Sonst stolpert er
  # mitten im Update ueber ein Repo, das gerade vorgespult wird.
  local timer_war_an=nein
  if $SYSTEMCTL is-active --quiet devarenu-fenster.timer 2>/dev/null; then
    timer_war_an=ja
    $SYSTEMCTL stop devarenu-fenster.timer >/dev/null 2>&1 \
      && gut "Fenster-Timer angehalten"
  fi

  # Das WLAN. Erst das eingetragene Profil; gibt es keines oder laesst
  # es sich nicht verbinden, wird genommen, was steht -- ein
  # Handy-Hotspot zum Beispiel, den der Helfer eben verbunden hat.
  # Getrennt wird am Ende nur, was WIR verbunden haben.
  local wir_verbanden=nein
  lauf_schreiben laeuft netz "Verbindung wird hergestellt"
  if [ -n "$PROFIL" ] \
     && ! $NMCLI -t -f NAME connection show --active 2>/dev/null \
          | grep -qxF "$PROFIL"; then
    if $NMCLI connection up "$PROFIL" >/dev/null 2>&1; then
      gut "$PROFIL verbunden"
      wir_verbanden=ja
    else
      warn "$PROFIL liess sich nicht verbinden."
    fi
  fi
  if ! netz_steht; then
    warn "Kein Netz. Es gibt nichts zu holen."
    lauf_schreiben gescheitert netz \
      "Kein Netz. Entweder das Wartungs-WLAN in Reichweite bringen oder am Rechner ein Handy-WLAN verbinden."
    [ "$timer_war_an" = ja ] && $SYSTEMCTL start devarenu-fenster.timer >/dev/null 2>&1
    return 1
  fi
  if [ "$wir_verbanden" = nein ]; then
    info "Die bestehende Verbindung wird benutzt und bleibt stehen."
  fi

  mkdir -p "$ABLAGE"; chmod 711 "$ABLAGE" 2>/dev/null || true
  local protokoll="$ABLAGE/jetzt-$(date +%Y%m%d-%H%M%S).log"
  lauf_schreiben laeuft update "Das Update laeuft. Der Dienst startet dabei neu."
  update_kern "Das Update" "$protokoll"

  update_melden "$protokoll" "$KERN_VORHER" "$KERN_NACHHER" \
                "$KERN_ERGEBNIS" "$KERN_DAUER" "$KERN_VORRAT"

  if [ "$wir_verbanden" = ja ]; then
    trennen
  fi
  [ "$timer_war_an" = ja ] \
    && $SYSTEMCTL start devarenu-fenster.timer >/dev/null 2>&1 \
    && gut "Fenster-Timer wieder an"

  if [ "$KERN_ERGEBNIS" = "GESCHEITERT" ]; then
    lauf_schreiben gescheitert fertig \
      "Das Update ist gescheitert. Die alte Fassung ${KERN_NACHHER:-?} laeuft weiter. Einzelheiten: $protokoll"
    return 1
  fi
  lauf_schreiben fertig fertig \
    "${KERN_ERGEBNIS}. Fassung ${KERN_VORHER:-?} -> ${KERN_NACHHER:-?} in ${KERN_DAUER}s.${KERN_VORRAT:+ $KERN_VORRAT}"
  return 0
}

# Ein Lauf, der "laeuft" meldet und dessen Frist abgelaufen ist, hat
# sie nicht selbst beendet -- da war der Strom weg oder der Dienst
# erschlagen. Das gehoert gesagt und nicht als "laeuft" stehengelassen,
# sonst wartet am Pult jemand auf etwas, das nie fertig wird.
lauf_aufraeumen() {
  [ -f "$LAUF_DATEI" ] || return 0
  grep -q '"lage": *"laeuft"' "$LAUF_DATEI" || return 0
  local seit jetzt
  seit="$(sed -n 's/.*"seit": *\([0-9]*\).*/\1/p' "$LAUF_DATEI" | head -1)"
  jetzt="$(date +%s)"
  [ -n "$seit" ] || return 0
  [ $(( jetzt - seit )) -gt "$LAUF_FRIST" ] || return 0
  LAUF_SEIT="$seit"
  lauf_schreiben abgebrochen fertig \
    "Der Lauf hat sich nicht gemeldet. Vermutlich war der Strom weg. Mit  bash pruefen.sh  nachsehen, welche Fassung laeuft."
  warn "Ein alter Update-Lauf stand auf \"laeuft\" und ist jetzt als abgebrochen vermerkt."
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
    # Der Schalter laesst sich auch bei ausgeschaltetem Fenster setzen.
    # Dann ist er vorgemerkt und greift, sobald es ein Fenster gibt --
    # aber das gehoert gesagt, sonst wartet jemand auf Post.
    [ "${2:-}" = ja ] && [ "$AN" != ja ] && \
      info "Das Fenster ist aus -- vorgemerkt, gesendet wird ab dem ersten Fenster."
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

  --jetzt)
    # Wird von devarenu-onlineupdate.service aufgerufen, nicht von Hand.
    lauf_aufraeumen
    [ -f "$MARKE_JETZT" ] || exit 0
    jetzt_laufen; exit $? ;;

  --jetzt-aufraeumen)
    # Beim Hochfahren: einen Lauf, der nie fertig wurde, als solchen
    # vermerken.
    lauf_aufraeumen; exit 0 ;;

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
      nutzung_melden
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
    echo "  --jetzt                 (vom Pult angestossen, braucht root)"
    echo "  --pruefen | --wecker"
    exit 2 ;;
esac
