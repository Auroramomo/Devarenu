#!/usr/bin/env bash
# Was beim Einspielen eines Updates zu tun ist -- die VERSIONIERTE
# Haelfte des Updaters.
#
# NICHT von Hand aufrufen. stick_update.sh fuehrt dieses Skript aus,
# und zwar aus einem Auszug des GEPRUEFTEN Tags, nie aus Dateien vom
# Stick.
#
# WARUM ZWEIGETEILT
# -----------------
# Der Kern (stick_update.sh) trifft zwei Arten von Entscheidungen:
# Vertrauen (ist das Bundle echt, ist der Tag signiert, ist die Fassung
# neuer) und Rettung (wie kommt der Rechner zurueck, wenn es schiefgeht).
# Beides darf nicht von Code abhaengen, den ein Stick mitbringt, und
# beides soll sich praktisch nie aendern.
#
# Alles andere ist Verfahren: welche Dateien wohin, welche Pakete,
# welche Units, was "gesund" heisst. Das aendert sich mit jeder
# Fassung -- und weil es HIER steht, kommt es mit dem Update selbst.
# Ein Fehler darin laesst sich mit dem naechsten Update beheben. Stuende
# er im Kern, muesste jemand hinfahren.
#
# WAS DER KERN UEBERGIBT (als Umgebung)
#   DEV_ORDNER      der Projektordner
#   DEV_BENUTZER    der Benutzer, dem er gehoert
#   DEV_ABLAGE      /var/lib/devarenu/updates -- Sicherungen, Wheels,
#                   grosse Teile vom Stick
#   DEV_ALT_SHA     der Stand vor dem Update
#   DEV_REF         refs/stick/vX.Y.Z -- die GEPRUEFTE Objekt-SHA
#   DEV_VERSION     die neue Fassung
#   DEV_HIER        die bisherige Fassung
#   DEV_SICHERUNG   Unterordner mit allem, was zurueckgeholt werden kann
#
# RUECKGABE
#   0   eingespielt und gesund
#   1   gescheitert -- der Kern rollt zurueck
#   Eine Zeile "MELDUNG|<text>" auf der Standardausgabe wird vom Kern
#   ans Pult weitergereicht.

set -u
ORDNER="${DEV_ORDNER:?fehlt}"
BENUTZER="${DEV_BENUTZER:?fehlt}"
ABLAGE="${DEV_ABLAGE:?fehlt}"
# Wo die Nutzlast vom Stick liegt -- Bundle, Wheels, grosse Teile.
#
# Seit 0.3.2 legt der Kern sie in einen eigenen Unterordner, der fuer
# den Dienstbenutzer lesbar ist; vorher lag alles direkt in $ABLAGE
# mit 700 root, und genau daran scheiterten pip und teile.py, sobald
# sie als $BENUTZER liefen. Beide Orte werden gesucht, denn der Kern
# auf dem Rechner ist der ALTE: eine 0.3.2-Logik kann durchaus von
# einem 0.3.1-Kern aufgerufen werden.
if [ -d "$ABLAGE/stick" ]; then
  NUTZLAST="$ABLAGE/stick"
else
  NUTZLAST="$ABLAGE"
fi
ALT_SHA="${DEV_ALT_SHA:?fehlt}"
REF="${DEV_REF:?fehlt}"
VERSION="${DEV_VERSION:?fehlt}"
HIER="${DEV_HIER:-unbekannt}"
# Die Sicherung: Units, zustand.json, netz.json, der alte venv-Name.
# Aus ihr holt der Aufrufer zurueck, wenn hier etwas schiefgeht.
#
# NICHT MEHR PFLICHT, und das ist kein Nachlassen. Der Kern uebergibt
# DEV_SICHERUNG seit 0.2.12; aktualisieren.sh tat es bis 0.3.2 NICHT,
# und weil hier ein ${...:?fehlt} stand, brach dieses Skript ab --
# vor dem Vorspulen, also ohne Schaden, aber auch ohne Update. Der
# ganze Online-Weg war damit tot, und der Pruefstand sah es nicht: er
# rief eine Attrappe statt dieser Datei auf.
#
# Repariert wird es HIER und nicht nur drueben, weil diese Datei mit
# dem neuen Tag kommt -- ein aktualisieren.sh aus 0.3.2 kann so ein
# 0.3.3 einspielen, ohne dass vorher jemand hinfaehrt.
SICHERUNG="${DEV_SICHERUNG:-$ABLAGE/vorher-$DEV_VERSION}"
SICHERUNG_SELBST=nein
[ -n "${DEV_SICHERUNG:-}" ] || SICHERUNG_SELBST=ja
NAME=devarenu

# Wohin die Units geschrieben werden. Fest verdrahtet war das bis 0.2.14
# und damit im Pruefstand nicht nachweisbar -- ausgerechnet der Teil, der
# jahrelang GAR NICHT lief. Die Vorgabe ist der echte Ort; gesetzt wird
# die Variable nur von den Tests.
UNIT_ORDNER="${DEVARENU_UNIT_ORDNER:-/etc/systemd/system}"

# Welche Units gesichert und im Rueckweg zurueckgeholt werden. Bis
# 0.3.2 fehlten hier die drei des Wartungsfensters -- ein Rueckfall
# haette ein halb zurueckgerolltes Fenster hinterlassen. Dieselbe
# Liste steht in stick_update.sh; online_test.sh vergleicht die
# beiden, damit sie nicht auseinanderlaufen.
UNITS_GESICHERT="devarenu.service devarenu-stick@.service \
devarenu-update.service devarenu-update.timer \
devarenu-fenster.service devarenu-fenster.timer \
devarenu-fenster-wecker.service \
devarenu-onlineupdate.service devarenu-onlineupdate.timer"
UDEV_REGEL="${DEVARENU_UDEV_REGEL:-/etc/udev/rules.d/99-$NAME-stick.rules}"

cd "$ORDNER"

blau() { printf '\n\033[1;34m== %s\033[0m\n' "$*"; }
gut()  { printf '   \033[32mok\033[0m    %s\n' "$*"; }
warn() { printf '   \033[33m!\033[0m     %s\n' "$*"; }
fehl() { printf '   \033[31mFEHLT\033[0m %s\n' "$*"; }
info() { printf '         %s\n' "$*"; }
melden() { printf 'MELDUNG|%s\n' "$*"; }

als_benutzer() { sudo -u "$BENUTZER" -H "$@"; }

PY_AKTIV="$ORDNER/.venv/bin/python"

# ----------------------------------------------------- Die Sicherung
# Angelegt, bevor irgendetwas angefasst wird. Hat der Aufrufer schon
# eine mitgebracht (der Kern tut das), wird sie nur ergaenzt: er hat
# die Units bereits abgelegt, der venv-Name kommt spaeter dazu.
# Die Ablage durchgehbar, die Sicherung darin zu. 711 und nicht 710
# -- siehe stick_update.sh, ablage_rechte().
mkdir -p "$ABLAGE" "$SICHERUNG/units"
chmod 711 "$ABLAGE" 2>/dev/null || true
chmod 700 "$SICHERUNG"
if [ "$SICHERUNG_SELBST" = ja ]; then
  blau "Sicherung"
  warn "Der Aufrufer hat keine uebergeben -- eine aeltere Fassung von"
  warn "aktualisieren.sh. Sie wird hier angelegt:"
  info "$SICHERUNG"
  for u in $UNITS_GESICHERT; do
    [ -f "$UNIT_ORDNER/$u" ] && cp -a "$UNIT_ORDNER/$u" "$SICHERUNG/units/$u"
  done
  for d in zustand.json netz.json; do
    [ -f "$ORDNER/$d" ] && cp -a "$ORDNER/$d" "$SICHERUNG/$d"
  done
  chmod -R go-rwx "$SICHERUNG" 2>/dev/null || true
  # Dem Dienstbenutzer: gesundheit.sh laeuft als er und liest hier
  # seine Grundlinie. Siehe stick_update.sh.
  chown -R "$BENUTZER" "$SICHERUNG" 2>/dev/null || true
  gut "Units, zustand.json und netz.json gesichert"
  info "Ein Rueckweg von Hand findet dort alles, was er braucht."
fi

# Die Sicherung gehoert dem Dienstbenutzer -- IMMER, auch wenn der
# Aufrufer sie mitgebracht hat.
#
# Ein Aufrufer aus 0.3.4 oder aelter legt sie als root mit 700 an.
# gesundheit.sh laeuft als $BENUTZER und kommt dann weder an seine
# Grundlinie heran noch kann er sie schreiben. Diese Datei kommt aus
# dem NEUEN Tag und laeuft auch dann, wenn der Aufrufer alt ist --
# also wird es hier geradegezogen.
chown -R "$BENUTZER" "$SICHERUNG" 2>/dev/null || true

# Und die Grundlinie, falls sie fehlt.
#
# Sie gehoert VOR das Vorspulen: hier gilt noch der alte Code, und
# genau dessen Befunde sind der Vergleichsmassstab. Hinterher prueft
# gesundheit.sh gegen diese Liste; fehlt sie, zaehlt JEDER Befund als
# neu und ein tadelloses Update rollt zurueck.
#
# Ein alter Aufrufer hat es versucht und ist an den Rechten
# gescheitert -- still, denn er haengt ein "|| true" an.
if [ ! -s "$SICHERUNG/befunde-vorher" ]; then
  if als_benutzer env DEV_SICHERUNG="$SICHERUNG" \
       "$ORDNER/gesundheit.sh" --vorher >/dev/null 2>&1; then
    gut "Grundlinie fuer den Gesundheitscheck nachgetragen"
  else
    warn "Die Grundlinie liess sich nicht anlegen."
    info "Der Gesundheitscheck zaehlt dann jeden vorhandenen Befund"
    info "als neu. Steht keiner an, macht es nichts."
  fi
fi

# ------------------------------------------------- Lokale Aenderungen
# Der signierte Stand gewinnt. Was jemand vor Ort an einer versionierten
# Datei geaendert hat, wird gesichert und dann ueberschrieben -- nicht
# weil es wertlos waere, sondern weil sonst jedes Update an ihm haengen
# bleibt. Genau daran stand der Gemeinderechner vor 0.2.12 fest.
#
# Nicht versionierte Dateien bleiben unberuehrt. zustand.json, netz.json
# und die venvs gehoeren dazu.
blau "Lokale Aenderungen"
PATCH=""
if ! als_benutzer git diff --quiet HEAD 2>/dev/null; then
  PATCH="$ABLAGE/lokal-$(date +%Y%m%d-%H%M%S).patch"
  als_benutzer git diff HEAD > "$PATCH" 2>/dev/null
  chmod 600 "$PATCH" 2>/dev/null || true
  local_zeilen="$(wc -l < "$PATCH")"
  warn "$local_zeilen Zeilen lokale Aenderungen gesichert:"
  info "$PATCH"
  als_benutzer git checkout -- . 2>/dev/null || true
  gut "Arbeitsbaum zurueckgesetzt"
else
  gut "keine lokalen Aenderungen"
fi

# ------------------------------------------------------------- Code
blau "Code"
# ^{commit} an der GEPRUEFTEN Referenz, nicht am Tagnamen: ein
# gleichnamiger lokaler Tag wuerde sonst etwas Ungeprueftes
# unterschieben. Nachgewiesen -- mit einem lokal ueberschriebenen Tag
# nimmt "git archive v9.9.9" das Gefaelschte, "git archive
# refs/stick/v9.9.9" das Echte.
if ! als_benutzer git merge --ff-only --quiet "$REF^{commit}" 2>/dev/null; then
  fehl "Der neue Stand laesst sich nicht vorspulen."
  melden "Update $VERSION passt nicht auf den hiesigen Stand."
  exit 1
fi
gut "auf $(als_benutzer git rev-parse --short HEAD) vorgespult"

# --------------------------------------------------------- Grosse Teile
# teile.json nennt, was an Modellen, Stimmen und Paketen dazugehoert --
# mit Groesse und Pruefsumme.
#
# Seit 0.4.2 steht sie IMMER im Repo. Bis dahin hiess "Datei da" so
# viel wie "dieses Update bringt grosse Teile mit"; jetzt heisst es
# nur noch "so soll dieser Rechner aussehen". Entschieden wird darum
# am Stick, nicht an der Datei:
#
#   Stick mit teile/   -> einspielen wie bisher, Fehler ist Abbruch.
#   Ohne teile/        -> das ist ein Update ueber das Netz oder ein
#                         Code-Stick. Fehlende STIMMEN werden aus dem
#                         Piper-Vorrat nachgeholt, gegen die sha256
#                         geprueft. Geht das nicht, ist es KEIN
#                         Abbruch: der Code ist richtig eingespielt,
#                         und die fehlende Stimme steht danach als
#                         Befund am Pult (systemcheck: stimme_fehlt).
#                         Ein Update abzubrechen, weil eine Stimme
#                         fehlt, waere der schlechtere Tausch.
if [ -f "$ORDNER/teile.json" ] && [ -d "$NUTZLAST/teile" ]; then
  blau "Grosse Teile"
  if ! als_benutzer "$PY_AKTIV" "$ORDNER/teile.py" --einspielen \
       --quelle "$NUTZLAST/teile" --sicherung "$SICHERUNG/teile"; then
    fehl "Grosse Teile liessen sich nicht einspielen."
    melden "Update $VERSION braucht Dateien, die der Stick nicht mitbrachte."
    exit 1
  fi
  gut "grosse Teile vollstaendig"
elif [ -f "$ORDNER/teile.json" ]; then
  blau "Grosse Teile"
  if als_benutzer "$PY_AKTIV" "$ORDNER/teile.py" --pruefen >/dev/null 2>&1; then
    gut "grosse Teile vollstaendig"
  else
    info "Es fehlen grosse Teile. Stimmen werden aus dem Netz geholt."
    if als_benutzer "$PY_AKTIV" "$ORDNER/teile.py" --aus-dem-netz; then
      gut "grosse Teile vollstaendig"
    else
      warn "Nicht alle grossen Teile sind da. Das Update laeuft trotzdem"
      warn "durch -- was fehlt, steht danach am Pult unter Fehlersuche."
      melden "Nach dem Update fehlen grosse Teile (Stimmen oder Modell)."
    fi
  fi
else
  gut "keine grossen Teile in dieser Fassung"
fi

# ------------------------------------------------------------- Pakete
# venv wird getauscht, nicht ueberschrieben: pip schreibt in vorhandene
# Pakete hinein, ein Rueckfall waere dort kein Loeschen. Also ein
# zweites venv daneben und ein Symlink, der umgelegt wird.
#
# venvs sind NICHT verschiebbar -- die Pfade stehen in den Skripten der
# Umgebung. Deshalb liegen beide im Projektordner und heissen .venv-a
# und .venv-b; verschoben wird nie etwas.
blau "Pakete"
VENV_GEWECHSELT=nein
SPERRE="$ORDNER/pakete.sperre"
# Ist PyPI zu erreichen? Nur dann darf pip dort holen, was auf dem Stick
# fehlt -- und auch dann nur gegen die sha256 aus pakete.sperre.
pypi_erreichbar() {
  [ -z "${DEVARENU_KEIN_NETZ:-}" ] || return 1
  curl -fsS -m 15 -o /dev/null https://pypi.org/simple/pip/ 2>/dev/null
}
if ! als_benutzer git diff --quiet "$ALT_SHA" HEAD -- requirements.txt; then
  if [ ! -d "$NUTZLAST/wheels" ] && { [ ! -f "$SPERRE" ] || ! pypi_erreichbar; }; then
    fehl "requirements.txt hat sich geaendert, der Stick brachte keine wheels/"
    [ -f "$SPERRE" ] && info "und PyPI ist nicht erreichbar."
    melden "Das Update braucht neue Pakete, der Stick brachte keine mit."
    exit 1
  fi
  # Welches ist gerade aktiv? Der Symlink sagt es; ist .venv noch ein
  # echter Ordner (Stand vor 0.2.13), wird er zu .venv-a gemacht.
  if [ -L "$ORDNER/.venv" ]; then
    AKTIV="$(readlink "$ORDNER/.venv")"
  else
    info ".venv ist noch ein Ordner -- wird zu .venv-a"
    als_benutzer mv "$ORDNER/.venv" "$ORDNER/.venv-a" || {
      fehl "Umbenennen nach .venv-a fehlgeschlagen"; exit 1; }
    als_benutzer ln -s .venv-a "$ORDNER/.venv"
    AKTIV=".venv-a"
  fi
  case "$AKTIV" in *a) NEU=".venv-b" ;; *) NEU=".venv-a" ;; esac
  info "$AKTIV ist aktiv, gebaut wird $NEU"

  als_benutzer rm -rf "$ORDNER/$NEU"
  if ! als_benutzer python3 -m venv "$ORDNER/$NEU"; then
    fehl "$NEU liess sich nicht anlegen"
    melden "Das Update konnte keine neue Paketumgebung bauen."
    exit 1
  fi
  # SEIT 0.5.2 MIT SHA256 (pakete.sperre, im signierten Baum).
  # --require-hashes: jedes Wheel muss genau die Pruefsumme aus der Liste
  # haben, gleich woher es kommt. Bis 0.5.1 genuegte der passende Name,
  # und ein manipuliertes wheels/ auf einem Stick oder in einem ZIP waere
  # an Signatur und Pruefung vorbei installiert worden.
  #
  # Erst nur vom Stick (--no-index: kein Wort nach draussen). Fehlt dort
  # etwas -- im oeffentlichen ZIP fehlen die NVIDIA-Pakete mit Absicht --,
  # holt pip es von PyPI, sobald Internet da ist, wieder gegen die
  # Pruefsumme. Ohne Internet steht da, was fehlt.
  VON_STICK=()
  [ -d "$NUTZLAST/wheels" ] && VON_STICK=(--find-links "$NUTZLAST/wheels")
  pip_sicher() {
    als_benutzer "$ORDNER/$NEU/bin/python" -m pip install --quiet \
      --require-hashes --no-deps "$@" -r "$SPERRE"
  }
  if [ -f "$SPERRE" ]; then
    if [ ${#VON_STICK[@]} -gt 0 ] && pip_sicher --no-index "${VON_STICK[@]}"; then
      gut "alle Pakete vom Stick, sha256 gegen pakete.sperre geprueft"
    elif pypi_erreichbar && pip_sicher "${VON_STICK[@]}"; then
      gut "fehlende Pakete von PyPI geholt, sha256 gegen pakete.sperre geprueft"
    else
      FEHLT_PAKETE="$(als_benutzer "$PY_AKTIV" "$ORDNER/werkzeuge/sperre_pruefen.py" \
                      "$SPERRE" "$NUTZLAST/wheels" 2>/dev/null)"
      fehl "pip konnte die Pakete nicht gegen pakete.sperre installieren"
      [ -n "$FEHLT_PAKETE" ] && info "Fehlt auf dem Stick: $FEHLT_PAKETE"
      als_benutzer rm -rf "$ORDNER/$NEU"
      melden "Es fehlen Pakete${FEHLT_PAKETE:+ ($FEHLT_PAKETE)}, und PyPI war nicht erreichbar. Einige Pakete liegen mit Absicht nicht im oeffentlichen Update-ZIP (NVIDIA, GPL-Binaerteile, siehe LIZENZEN.md); mit Internet holt das Update sie selbst, ohne Internet braucht es einen Stick mit allem. Fassung $HIER bleibt."
      exit 1
    fi
  elif ! als_benutzer "$ORDNER/$NEU/bin/python" -m pip install --quiet \
       --no-index --find-links "$NUTZLAST/wheels" -r "$ORDNER/requirements.txt"; then
    fehl "pip konnte nicht alles aus wheels/ installieren"
    als_benutzer rm -rf "$ORDNER/$NEU"
    melden "Die Pakete auf dem Stick reichen nicht aus."
    exit 1
  fi
  # Umschalten: erst jetzt, wenn das neue venv vollstaendig ist.
  als_benutzer ln -sfn "$NEU" "$ORDNER/.venv"
  printf '%s\n' "$AKTIV" > "$SICHERUNG/venv-vorher"
  VENV_GEWECHSELT=ja
  gut "$NEU gebaut und aktiv, $AKTIV bleibt als Rueckfall liegen"
else
  gut "requirements.txt unveraendert, keine Pakete noetig"
fi

# -------------------------------------------------------------- Units
# Bis 0.2.12 schrieb KEIN Update die Units neu -- das tat allein
# dienst.sh bei der Ersteinrichtung. Eine geaenderte Vorlage lag im
# Ordner und wirkte nicht, und niemand sah es.
blau "Dienste"
UNITS_GEAENDERT=nein
NEUE_UNITS=""
for paar in "devarenu.service:devarenu.service.vorlage" \
            "devarenu-stick@.service:devarenu-stick@.service.vorlage" \
            "devarenu-update.service:devarenu-update.service.vorlage" \
            "devarenu-update.timer:devarenu-update.timer.vorlage"; do
  unit="${paar%%:*}"; vorlage="${paar#*:}"
  ziel="$UNIT_ORDNER/$unit"
  [ -f "$ziel" ] || continue          # nicht eingerichtet, nichts zu tun
  [ -f "$ORDNER/$vorlage" ] || continue
  neu="$(sed -e "s|@ORDNER@|$ORDNER|g" -e "s|@BENUTZER@|$BENUTZER|g" \
             -e "s|@PORT@|${DEVARENU_PORT:-8000}|g" "$ORDNER/$vorlage")"
  if [ "$neu" != "$(cat "$ziel")" ]; then
    printf '%s\n' "$neu" > "$ziel"
    chmod 644 "$ziel"
    gut "$unit neu geschrieben"
    UNITS_GEAENDERT=ja
  fi
done
# Units, die es in dieser Fassung NEU gibt. Die Schleife oben legt
# nichts an -- sie ueberspringt, was nicht schon dasteht, und das ist
# richtig: ein Update soll nicht entscheiden, welche Dienste ein
# Rechner ueberhaupt haben will.
#
# Fuer neue Units gilt das nicht. Kaeme das Wartungsfenster erst mit
# dem naechsten dienst.sh von Hand, waere es genau an dem Donnerstag
# nicht da, an dem es gebraucht wird -- und niemand kaeme heran, um es
# nachzuinstallieren.
#
# Angelegt wird nur, wenn dieser Rechner ueberhaupt als Dienst laeuft
# (devarenu.service ist da). Auf einem Arbeitsrechner passiert nichts.
if [ -f "$UNIT_ORDNER/devarenu.service" ]; then
  for paar in "devarenu-fenster.service:devarenu-fenster.service.vorlage" \
              "devarenu-fenster.timer:devarenu-fenster.timer.vorlage" \
              "devarenu-fenster-wecker.service:devarenu-fenster-wecker.service.vorlage" \
              "devarenu-onlineupdate.service:devarenu-onlineupdate.service.vorlage" \
              "devarenu-onlineupdate.timer:devarenu-onlineupdate.timer.vorlage"; do
    unit="${paar%%:*}"; vorlage="${paar#*:}"
    ziel="$UNIT_ORDNER/$unit"
    [ -f "$ORDNER/$vorlage" ] || continue
    neu="$(sed -e "s|@ORDNER@|$ORDNER|g" -e "s|@BENUTZER@|$BENUTZER|g" \
               -e "s|@PORT@|${DEVARENU_PORT:-8000}|g" "$ORDNER/$vorlage")"
    # Ob sie NEU ist, wird vor dem Schreiben festgehalten: nur neue
    # Units werden gleich scharf gemacht. Wer eine bestehende
    # absichtlich abgeschaltet hat, soll sie nicht bei jedem Update
    # zurueckbekommen.
    frisch=nein; [ -f "$ziel" ] || frisch=ja
    if [ "$frisch" = ja ] || [ "$neu" != "$(cat "$ziel")" ]; then
      printf '%s\n' "$neu" > "$ziel"
      chmod 644 "$ziel"
      gut "$unit geschrieben"
      UNITS_GEAENDERT=ja
      [ "$frisch" = ja ] && NEUE_UNITS="$NEUE_UNITS $unit"
    fi
  done
fi

if [ "$UNITS_GEAENDERT" = ja ]; then
  systemctl daemon-reload && gut "systemd neu geladen"
else
  gut "Units unveraendert"
fi

# Scharf machen, was gerade erst entstanden ist. Das Fenster selbst
# bleibt trotzdem AUS: in netz.json steht per Vorgabe "an": false, und
# ohne das tut der Lauf nichts und sagt nichts. Ein Update, das von
# sich aus ein WLAN aufmachte, waere das Gegenteil dessen, wofuer
# dieser Rechner gebaut ist.
for unit in $NEUE_UNITS; do
  case "$unit" in
    *.timer|devarenu-fenster-wecker.service)
      if systemctl enable --now "$unit" >/dev/null 2>&1; then
        gut "$unit scharf gemacht"
      else
        warn "$unit liess sich nicht scharf machen."
      fi ;;
  esac
done

# Die udev-Regel ging bis 0.2.14 leer aus. Sie sah nur deshalb richtig
# aus, weil sie sich seit 0.2.11 nicht geaendert hat -- eine Luecke, die
# erst bei der naechsten Aenderung aufgefallen waere, und dann als
# "der Stick wird nicht mehr erkannt". Ohne Erkennung gibt es auch kein
# Update mehr, das sie nachtraeglich reparieren koennte.
if [ -f "$UDEV_REGEL" ] && [ -f "$ORDNER/stick.udev.vorlage" ]; then
  if ! cmp -s "$ORDNER/stick.udev.vorlage" "$UDEV_REGEL"; then
    cp "$ORDNER/stick.udev.vorlage" "$UDEV_REGEL"
    chmod 644 "$UDEV_REGEL"
    gut "udev-Regel neu geschrieben"
    # Kein Abbruchgrund: udev liest seine Regeln spaetestens beim
    # naechsten Start neu ein, und der kommt sonntags ohnehin.
    if udevadm control --reload 2>/dev/null; then
      gut "udev neu geladen"
    else
      warn "udev-Regel liegt, udevadm liess sich nicht ansprechen."
      warn "Sie gilt ab dem naechsten Neustart."
    fi
  else
    gut "udev-Regel unveraendert"
  fi
fi

# --------------------------------------------------- Das Sprachmodell
# models/ steht in .gitignore, das Bundle kennt es also nicht. Traegt
# das neue config.py ein anderes Sprachmodell ein, fehlt es hier, und
# ohne Netz laedt nichts nach. Der Dienst startet dann, antwortet auf
# /api/zustand -- und uebersetzt nicht. Das faellt sonst erst am
# Sabbat auf.
#
# Hier und nicht im Kern: gefragt wird das NEUE config.py, und das
# gibt es erst nach dem Vorspulen weiter oben. Im Kern stand eine
# vorpruefung(), die seit 0.3.0 von niemandem mehr aufgerufen wurde --
# die Warnung war also ersatzlos weg, ohne dass es auffiel.
#
# GEFRAGT WIRD UEBER HTTP, NICHT UEBER DIE KOMMANDOZEILE.
# "ollama list" braucht $HOME. Ein root-Dienst ohne User= bekommt von
# systemd keines, und der Befehl bricht dann mit
#   panic: $HOME is not defined
# ab, bevor er den Ollama-Dienst ueberhaupt fragt. Weil die alte
# Fassung stderr wegwarf und nur nach einem Treffer in der Ausgabe
# suchte, wurde daraus "das Sprachmodell liegt hier nicht" -- auf
# einem Rechner, auf dem es lag. Nachgestellt mit
#   sudo env -i /usr/local/bin/ollama list
# Die HTTP-Schnittstelle braucht kein HOME, keinen PATH und keinen
# Benutzerkontext; selbsttest.py fragt sie seit jeher so.
#
# Seit 0.5.2 (28.10.2026) ueber sprachmodell.erkennen: llama-server
# ODER Ollama. Bis dahin fragte dieser Abschnitt nur Ollama.
blau "Sprachmodell"
MODELL_LAGE="$(als_benutzer "$PY_AKTIV" - <<'PYCODE' 2>/dev/null
import sys, time
sys.path.insert(0, ".")
try:
    import requests
    import sprachmodell
except ImportError as e:
    print("unklar|%s" % e)
    raise SystemExit

# Dreimal im Abstand von zehn Sekunden. Ein Update laeuft oft kurz
# nach dem Hochfahren, und der Sprachmodell-Server laedt dabei noch.
# Einmal fragen und aufgeben hiesse, den haeufigsten Fall fuer den
# schlimmsten zu halten.
lage = {}
for versuch in range(3):
    if versuch:
        time.sleep(10)
    lage = sprachmodell.erkennen(requests)
    if lage.get("art") and lage.get("grund") != "laedt":
        break
if not lage.get("art"):
    print("unklar|%s" % sprachmodell.beschreiben(lage))
elif lage.get("grund"):
    print("fehlt|%s" % sprachmodell.beschreiben(lage))
else:
    print("da|%s" % sprachmodell.beschreiben(lage))
PYCODE
)"
case "${MODELL_LAGE%%|*}" in
  da)
    gut "Sprachmodell: ${MODELL_LAGE#*|}" ;;
  fehlt)
    # KEIN Abbruch. Ein fehlendes Modell ist ein Ausfall der
    # Uebersetzung, kein Schaden am Rechner -- und ein Update
    # zurueckzurollen macht das Modell auch nicht wieder da. Gesagt
    # werden muss es aber deutlich, sonst sucht am Sabbat jemand den
    # Fehler beim Ton.
    fehl "${MODELL_LAGE#*|}"
    info "Die Uebersetzung bleibt stumm, bis es da ist."
    melden "Achtung: ${MODELL_LAGE#*|} Bis es behoben ist, laeuft keine Uebersetzung." ;;
  *)
    warn "Der Sprachmodell-Server war dreimal nicht zu erreichen."
    info "${MODELL_LAGE#*|}"
    info "Ob das Sprachmodell da ist, ist damit UNBEKANNT."
    melden "Beim Update antwortete kein Sprachmodell-Server; ob das Modell da ist, wurde nicht geprueft." ;;
esac

# ------------------------------------------------------- Die Stimmen
# Eine eingestellte Sprache ohne Stimme laeuft als reiner Untertitel
# weiter. Das ist ein Mangel und kein Ausfall -- also KEIN
# Abbruchgrund. Gesagt werden muss es trotzdem, sonst sucht am Sabbat
# jemand den Fehler beim Ton.
#
# Bis 0.2.11 tat das der Kern; seit 0.3.0 rief die Funktion niemand
# mehr auf, und der Hinweis war ersatzlos weg. Jetzt steht sie hier,
# wo das NEUE config.py schon gilt -- denselben Weg wie die
# Modellpruefung.
#
# UEBER melden UND NICHT UEBER EIN FELD. Das Pult-Feld "stimmen"
# schreibt der Kern, und der Kern auf dem Rechner ist beim Update
# immer der ALTE. Eine Meldung von hier erreicht das Pult dagegen
# sofort -- auch mit einem Kern aus 0.3.2.
#
# stderr wird verworfen, stdout NICHT: laden() aus zustand.py druckt
# seine Hinweise seit 0.3.2 nach stderr, und genau deshalb steht hier
# nur noch die Aufzaehlung. Vorher landete "zustand.json umgezogen:
# 2->3" mitten im Satz "Ohne Stimme, laufen als Untertitel: ...".
blau "Stimmen"
OHNE_STIMME="$(als_benutzer "$PY_AKTIV" - <<'PYCODE' 2>/dev/null
import sys
sys.path.insert(0, ".")
import config, zustand
z = zustand.laden()[0] if isinstance(zustand.laden(), tuple) else zustand.laden()
sprachen = [z.get("quelle", config.AUSGANGSSPRACHE)] + list(
    z.get("ziele", config.ZIELSPRACHEN))
fehlt = []
for sp in dict.fromkeys(sprachen):
    pfad = config.STIMMEN.get(sp)
    if not pfad:
        continue
    name = pfad.rsplit("/", 1)[-1]
    if not (config.BASIS / "voices" / f"{name}.onnx").exists():
        fehlt.append(sp)
print(" ".join(fehlt))
PYCODE
)"
OHNE_STIMME="$(printf '%s' "$OHNE_STIMME" | tr -s '[:space:]' ' ' \
               | sed 's/^ //; s/ $//')"
if [ -n "$OHNE_STIMME" ]; then
  warn "Ohne Stimme, laufen als Untertitel: $OHNE_STIMME"
  melden "Ohne Stimme, laufen als Untertitel: $OHNE_STIMME."
else
  gut "alle eingestellten Sprachen haben eine Stimme"
fi

# ------------------------------------------------------------- Dienst
blau "Neustart"
systemctl restart "$NAME" || {
  fehl "Neustart fehlgeschlagen"
  melden "Der Dienst liess sich mit $VERSION nicht starten."
  exit 1; }

# ------------------------------------------------------ Gesundheit
blau "Gesundheitscheck"
# DEV_SICHERUNG und DEV_VERSION ausdruecklich mitgeben, nicht vererben.
#
# als_benutzer ist hier "sudo -u ... -H", und sudo raeumt mit
# env_reset die Umgebung ab. gesundheit.sh suchte seine Grundlinie
# deshalb unter /tmp/befunde-vorher statt in der Sicherung -- fand
# sie nie und zaehlte JEDEN vorhandenen Befund als neu. Ein Rechner,
# auf dem der Autologin schon vorher fehlte, rollte damit jedes
# tadellose Update zurueck. Dasselbe galt fuer die erwartete Fassung.
#
# Im Pruefstand fiel das nie auf: die sudo-Attrappe reicht alles
# durch. Gefunden, als der Online-Weg gegen die echte Datei lief.
if ! als_benutzer env DEV_SICHERUNG="$SICHERUNG" DEV_VERSION="$VERSION" \
     "$ORDNER/gesundheit.sh"; then
  fehl "Der Rechner ist nach dem Update nicht gesund."
  melden "Update $VERSION ist fehlgeschlagen."
  exit 1
fi

# Haben sich venv oder grosse Teile geaendert, kommt der Selbsttest
# dazu. Er dauert Minuten -- das ist hier egal: eingespielt wird nur,
# wenn niemand zuhoert.
#
# Bis 0.4.1 hiess die Bedingung "[ -f teile.json ]", also "dieses
# Update bringt grosse Teile mit". Seit 0.4.2 steht die Datei IMMER
# im Repo, und damit lief der Selbsttest nach jedem Update -- und
# jedes Update scheiterte, wenn er aus einem beliebigen anderen
# Grund nicht durchkam. Gefragt wird jetzt dasselbe wie damals
# gemeint: hat sich an den grossen Teilen etwas GEAENDERT?
TEILE_NEU=nein
if ! als_benutzer git diff --quiet "$ALT_SHA" HEAD -- teile.json 2>/dev/null
then
  TEILE_NEU=ja
fi
#
# --sprachmodell-nur-melden (29.10.2026): ein fehlendes Sprachmodell ist
# hier kein Abbruchgrund, genau wie im Abschnitt "Sprachmodell" oben.
# Bis dahin rollte der Selbsttest das Update deswegen zurueck -- vor dem
# llama-Schritt, der es haette beheben koennen. Beim Sprung von 0.5.1
# laeuft er immer (teile.json ist neu), und ein Rechner mit kaputtem
# Ollama blieb damit ohne jede Uebersetzung.
# (pruefstand/update_ohne_ollama_test.sh)
if [ "$VENV_GEWECHSELT" = ja ] || [ "$TEILE_NEU" = ja ]; then
  info "venv oder grosse Teile geaendert -- Selbsttest laeuft mit."
  if ! als_benutzer "$PY_AKTIV" "$ORDNER/selbsttest.py" \
       --sprachmodell-nur-melden >/dev/null 2>&1; then
    fehl "Der Selbsttest schlaegt fehl."
    melden "Update $VERSION besteht den Selbsttest nicht."
    exit 1
  fi
  gut "Selbsttest bestanden"
fi

# ------------------------------------------------------- Aufraeumen
# ERST JETZT. Bis hierher musste alles zurueckholbar bleiben.
blau "Aufraeumen"
if [ "$VENV_GEWECHSELT" = ja ]; then
  ALT_VENV="$(cat "$SICHERUNG/venv-vorher" 2>/dev/null)"
  if [ -n "$ALT_VENV" ] && [ -d "$ORDNER/$ALT_VENV" ]; then
    als_benutzer rm -rf "$ORDNER/$ALT_VENV"
    gut "$ALT_VENV entfernt"
  fi
fi
# Nur, wenn tatsaechlich etwas beiseitegelegt wurde. Dieselbe
# Verwechslung wie oben: "teile.json da" heisst nicht mehr "es wurde
# eingespielt".
if [ -d "$SICHERUNG/teile" ]; then
  als_benutzer "$PY_AKTIV" "$ORDNER/teile.py" --aufraeumen \
    --sicherung "$SICHERUNG/teile" 2>/dev/null \
    && gut "alte grosse Teile entfernt"
fi

# Der Reparaturvorrat muss nachziehen, sonst stellt eine spaetere
# Reparatur das alte Modell wieder her.
if [ -f /opt/devarenu-vorrat/vorrat.json ]; then
  info "Reparaturvorrat wird auf $VERSION nachgezogen."
  if bash "$ORDNER/vorrat_bauen.sh" --nur-etikett >/dev/null 2>&1; then
    gut "Vorrat nachgezogen"
  else
    warn "Vorrat liess sich nicht nachziehen -- beim naechsten Besuch"
    warn "mit Leitung:  sudo bash vorrat_bauen.sh"
  fi
fi

[ -n "$PATCH" ] && melden "Lokale Aenderungen wurden ueberschrieben. Gesichert als $PATCH."

# ------------------------------------------------- llama-server (0.5.2)
# Der Umstieg von Ollama auf llama-server (llama_einrichten.py). Er
# steht HIER, am Ende, nach Gesundheitscheck und Aufraeumen: das Update
# ist zu diesem Zeitpunkt eingespielt und gesund, und nichts, was jetzt
# geschieht, kann noch einen Ruecksprung ausloesen. Scheitert der
# Schritt, bleibt das Update bestehen und Ollama an; der Grund steht im
# Protokoll, am Pult (MELDUNG) und in der Rueckmeldung.
#
# Gilt fuer JEDEN Weg ins Update -- Netz, Stick, Fenster, von Hand --,
# weil diese Datei auf jedem laeuft, und zwar als root. Er ersetzt die
# Regel von 0.5.2 (B7), dass ein Update llama-server nie selbst
# einrichtet.
#
# Zeitgrenze 45 Minuten fuer alles; timeout darum herum als zweiter
# Riegel, falls Python selbst haengt.
LLAMA_SATZ=""
if [ -f "$ORDNER/llama_einrichten.py" ] && [ -x "$PY_AKTIV" ]; then
  blau "Sprachmodell-Server (llama-server)"
  LLAMA_AUS="$(cd "$ORDNER" && timeout 3000 "$PY_AKTIV" \
                 "$ORDNER/llama_einrichten.py" --frist 2700 2>&1)"
  LLAMA_RC=$?
  printf '%s\n' "$LLAMA_AUS" | grep -v '^ERGEBNIS|' | sed 's/^/   /'
  LLAMA_SATZ="$(printf '%s\n' "$LLAMA_AUS" | sed -n 's/^ERGEBNIS|//p' | tail -1)"
  if [ -z "$LLAMA_SATZ" ]; then
    LLAMA_SATZ="llama-server NICHT eingerichtet: die Einrichtung brach ohne Ergebnis ab (Rueckgabe $LLAMA_RC). Es uebersetzt weiter der bisherige Sprachmodell-Server."
  fi
  if [ "$LLAMA_RC" = 0 ]; then gut "$LLAMA_SATZ"; else warn "$LLAMA_SATZ"; fi
  melden "$LLAMA_SATZ"
fi

# ------------------------------------------------------- Der Stand
# Was zuletzt eingespielt wurde -- fuer pruefen.sh und den
# Fehlerbericht.
#
# Bis 0.3.4 schrieb das nur der Stick-Kern. Nach einem Update ueber
# das Netz stand unter "Letztes Update" weiter die Stick-Meldung vom
# 27.09., obwohl danach zweimal online eingespielt worden war. Wer
# das liest, haelt den Rechner fuer aelter, als er ist.
#
# Hier und nicht in aktualisieren.sh: diese Datei laeuft auf BEIDEN
# Wegen -- ueber das Netz und bei einer Ueberbrueckung von Hand.
#
# In eine EIGENE Datei. update/stand.json ist zugleich die
# Verstaendigung zwischen Stick-Kern und Pult (bereit, jetzt); sie
# von hier aus zu ueberschreiben koennte ein vorgemerktes
# Stick-Update verwirren. Wer beide liest, nimmt die juengere.
#
# Nicht auf dem Stick-Weg: dort schreibt der Kern gleich danach
# seinen eigenen, ausfuehrlicheren Stand.
case "$REF" in
  refs/stick/*) ;;
  *)
    mkdir -p "$ORDNER/update"
    cat > "$ORDNER/update/stand-online.json" <<ENDE
{
  "lage": "eingespielt",
  "version": "$VERSION",
  "vorher": "$HIER",
  "text": "Fassung $VERSION ist ueber das Netz eingespielt und laeuft.${LLAMA_SATZ:+ $LLAMA_SATZ}",
  "zeit": "$(date '+%Y-%m-%d %H:%M:%S')"
}
ENDE
    chmod 644 "$ORDNER/update/stand-online.json" 2>/dev/null || true
    chown "$BENUTZER" "$ORDNER/update/stand-online.json" 2>/dev/null || true
    ;;
esac

blau "Fertig"
exit 0
