#!/usr/bin/env bash
# Devarenu per USB-Stick aktualisieren. Laeuft auf dem Gemeinderechner.
#
#   bash stick_update.sh --lesen /dev/sdb1   Stick auswerten und ablegen
#   bash stick_update.sh --einspielen        Abgelegtes einspielen, wenn Ruhe ist
#   bash stick_update.sh --stand             nachsehen, was ansteht
#
# Von Hand ruft das normalerweise niemand auf. --lesen stoesst eine
# udev-Regel an, sobald ein Stick steckt; --einspielen ein Timer, jede
# Minute.
#
# Warum zweigeteilt: der Stick soll sofort wieder abziehbar sein, das
# Einspielen aber auf das Ende des Gottesdienstes warten. Wuerde ein
# einziger Lauf beides tun, muesste er stundenlang leben -- und waere beim
# naechsten Ausschalten weg, mit dem fertigen Paket ungenutzt auf der
# Platte. So ueberlebt der Auftrag jeden Neustart.
#
# Das Skript laeuft aus einer System-Unit, also als root. Alles, was den
# Projektordner oder die venv anfasst, wird auf den Besitzer des Ordners
# zurueckgestuft: sonst gehoeren Dateien danach root, der Dienst laeuft
# als ein anderer, und git meldet ab da "dubious ownership".
#
# ---------------------------------------------------------------------
# GRUNDSATZ: DIE SCHLUESSELLISTE KOMMT NIE VOM STICK.
#
# Auf dem Stick LIEGT eine schluessel.erlaubt. Sie ist ausschliesslich
# fuer bootstrap.sh da -- fuer einen Rechner, der das Verfahren noch gar
# nicht kennt und deshalb noch keine eigene Liste hat. bootstrap.sh
# zeigt den Fingerabdruck daraus am Bildschirm, und ein Mensch
# vergleicht ihn am Telefon mit dem, den der Betreuer ihm nennt. Dieser
# Anruf ist der Vertrauensanker, nicht die Datei.
#
# Dieses Skript hier liest sie NICHT. Es prueft ausschliesslich gegen
# "$ORDNER/schluessel.erlaubt", also gegen die installierte Liste. Vom
# Stick kommen nur devarenu.bundle, wheels/ und teile/.
#
# Der Grund ist einfach: wuerde der Kern die Liste vom Stick lesen,
# brauchte ein Angreifer nur einen Stick zu bespielen -- er braechte
# seine eigene Erlaubnis gleich mit, und die Signaturpruefung pruefte
# nichts mehr als sich selbst. Belegt in pruefstand/updater_test.sh,
# Fall 13: ein Tag von fremder Hand, dazu die passende Erlaubnis auf dem
# Stick, wird abgelehnt -- und derselbe Stick mit der echten Signatur
# geht durch.
# ---------------------------------------------------------------------

set -u
ORDNER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ORDNER"

NAME=devarenu
PORT="${DEVARENU_PORT:-8000}"
PY="$ORDNER/.venv/bin/python"

# Zwei Ablagen, und die Trennung hat einen Grund.
#
# ABLAGE ist die Verstaendigung mit dem Pult: was bereitliegt, was
# zuletzt passiert ist, der Knopf "Jetzt einspielen". Der Server liest
# das und laeuft als gewoehnlicher Benutzer -- also bleibt es im
# Projektordner und ihm lesbar.
#
# DATEN ist die Nutzlast: Bundle, Wheels, grosse Teile, gesicherte
# Patches und der Stand vor dem Update. Darin liegt unter anderem eine
# Kopie von zustand.json, und die enthaelt das WLAN-Passwort der
# Gemeinde. Deshalb ausserhalb des Projektordners und nur fuer die
# Wurzel lesbar: 700 auf dem Ordner, 600 auf den Dateien.
#
# Nicht im Reparaturvorrat: der ist eine geprueufte Offline-Kopie und
# soll nicht mit Halbfertigem aus laufenden Updates vermischt werden.
ABLAGE="$ORDNER/update"
# Die Vorgabe ist der echte Ort. Umgebogen wird sie nur vom Pruefstand
# -- sonst bliebe der ganze Leseweg ungeprueft: Signatur, Bundle, der
# Ordner auf dem Stick. Genau der Weg, den ein Ehrenamtlicher geht.
DATEN="${DEVARENU_DATEN:-/var/lib/devarenu/updates}"
STAND="$ABLAGE/stand.json"
BEREIT="$ABLAGE/bereit"
RUHIG="$ABLAGE/ruhig"
JETZT="$ABLAGE/jetzt"
SPERRE="$ABLAGE/sperre"

EINHAENGEPUNKT=/run/devarenu-stick

# Die Kopie der Schluesselliste, gegen die die Signatur geprueft wird.
# Sie bekommt BEWUSST keinen eigenen Schalter: eine Umgebungsvariable,
# die bestimmt, welche Schluessel gelten, waere der Hebel, mit dem sich
# ein fremdes Tag annehmen liesse. Sie haengt an der Ablage, und die ist
# ausserhalb des Pruefstands immer /var/lib/devarenu/updates.
if [ -n "${DEVARENU_DATEN:-}" ]; then
  SCHLUESSEL_KOPIE="$DATEN/schluessel.erlaubt"
  mkdir -p "$DATEN"
else
  SCHLUESSEL_KOPIE=/run/devarenu-schluessel.erlaubt
fi

# Wie lange durchgehend Ruhe sein muss, bevor von allein eingespielt wird.
# Der Timer laeuft jede Minute, also sind das 20 Minuten. Eine Pause
# zwischen zwei Liedern ist kuerzer; ein Gottesdienst, der seit zwanzig
# Minuten angehalten ist und niemanden mehr zuhoeren hat, ist vorbei.
RUHE_LAEUFE=20

blau() { printf '\n\033[1;34m== %s\033[0m\n' "$1"; }
gut()  { printf '   \033[32mok\033[0m   %s\n' "$1"; }
warn() { printf '   \033[33m!\033[0m    %s\n' "$1"; }
fehl() { printf '   \033[31mFEHLT\033[0m %s\n' "$1"; }
# Fehlte bis 0.2.14. Die Aufrufe standen da, die Funktion nicht -- und
# "info" ist auf vielen Systemen der texinfo-Leser. Der Updater rief
# also im Unterordner-Fall ein fremdes Programm auf und schrieb dessen
# Fehlermeldung ins Journal. Ohne "set -e" lief er weiter, deshalb fiel
# es nie auf.
info() { printf '        %s\n' "$1"; }

BENUTZER="$(stat -c %U "$ORDNER" 2>/dev/null || id -un)"

# Alles, was Dateien im Projektordner anlegt, laeuft unter diesem
# Benutzer. Lesen darf root selbst, das hinterlaesst nichts.
als_benutzer() {
  if [ "$(id -u)" = "0" ] && [ "$BENUTZER" != "root" ]; then
    runuser -u "$BENUTZER" -- "$@"
  else
    "$@"
  fi
}

# ------------------------------------------------------------ Statusdatei
# Zwei Leser, zwei Formen. "lage" ist das Wort, aus dem das Pult seinen
# Satz baut -- auf Deutsch oder Englisch, je nachdem, was dort eingestellt
# ist. "text" ist derselbe Sachverhalt als deutscher Satz und geht ins
# Journal, in pruefen.sh und in --stand; dort liest ihn ein Mensch an
# einer Konsole, und die spricht Deutsch.
#
# Das Pult darf "text" also NICHT anzeigen, sonst steht unter englischer
# Oberflaeche ein deutscher Satz. Es nimmt "lage" und die Felder daneben.
#
# Anfuehrungszeichen und Backslashes kommen in den Texten nicht vor, damit
# das JSON ohne Maskierung auskommt. Wer neue Meldungen ergaenzt, haelt
# sich daran.
stand_schreiben() {
  local lage="$1" version="$2" text="$3" vorher="${4:-}" stimmen="${5:-}"
  mkdir -p "$ABLAGE"

  # Steht dasselbe schon drin, nicht noch einmal schreiben und vor allem
  # nichts melden. Ein Update, das auf das Ende des Gottesdienstes
  # wartet, durchlaeuft diese Stelle jede Minute -- ohne die Abkuerzung
  # stuenden im Journal stundenlang dieselben zwei Zeilen, und die eine,
  # auf die es ankommt, ginge darin unter.
  if [ -f "$STAND" ] && grep -q "\"text\": \"$text\"" "$STAND" 2>/dev/null; then
    return 0
  fi

  cat > "$STAND" <<ENDE
{
  "lage": "$lage",
  "version": "$version",
  "vorher": "$vorher",
  "stimmen": "$stimmen",
  "text": "$text",
  "zeit": "$(date '+%Y-%m-%d %H:%M:%S')"
}
ENDE
  chmod 644 "$STAND"
  printf '   Stand: %s -- %s\n' "$lage" "$text"
}

# Fragt den laufenden Server. Leere Antwort heisst: er antwortet nicht,
# nicht etwa "Feld ist leer" -- die Unterscheidung macht der Aufrufer.
zustand_holen() {
  curl -s -m 3 "http://127.0.0.1:$PORT/api/zustand" 2>/dev/null
}

feld() {
  printf '%s' "$1" | "$PY" -c \
    'import json,sys
try: print(json.load(sys.stdin).get(sys.argv[1], ""))
except Exception: pass' "$2" 2>/dev/null
}

# Vergleicht zwei Fassungen. Erfolg heisst: die zweite ist echt neuer.
# sort -V allein genuegt nicht -- bei gleichen Werten liefert es ebenfalls
# den zweiten, und gleich ist nicht neuer.
#
# Bekannte Grenze: sort -V haelt 0.3.0-rc1 fuer neuer als 0.3.0, nach
# Semver waere es aelter. Devarenu vergibt keine rc-Tags; wer damit
# anfaengt, muss hier nachbessern.
ist_neuer() {
  [ "$1" = "$2" ] && return 1
  [ "$(printf '%s\n%s\n' "$1" "$2" | sort -V | head -1)" = "$1" ]
}

# Leer, wenn die Datei fehlt oder Unsinn enthaelt. Leer sortiert vor jeder
# Zahl und gilt damit als aelter -- ein Rechner mit kaputter VERSION nimmt
# das Update also an, statt es abzulehnen. Andersherum haette er sich
# ausgesperrt, und zwar genau dann, wenn das Update die Datei repariert
# haette.
version_hier() {
  # Erst nachsehen, dann umleiten: bei fehlender Datei meldet die
  # Umleitung selbst, und zwar an der Fehlerausgabe vorbei ins Journal.
  [ -f VERSION ] || return 0
  tr -d '\r' < VERSION | head -1 | tr -d '[:space:]' \
    | grep -xE '[0-9][0-9A-Za-z.-]*' || true
}

# ================================================================ LESEN
stick_lesen() {
  local geraet="$1"

  # Ein bereits eingehaengter Ordner statt eines Geraets. NUR fuer den
  # Pruefstand: Einhaengen braucht Wurzelrechte und ein echtes
  # Blockgeraet, und dann bliebe ausgerechnet das Suchen der Datei
  # ungeprueft -- der Teil, an dem sich entscheidet, ob ein Stick
  # ueberhaupt erkannt wird.
  local ohne_einhaengen="${DEVARENU_STICK_ORDNER:-}"

  if [ -z "$ohne_einhaengen" ]; then
    [ -b "$geraet" ] || { fehl "$geraet ist kein Blockgeraet"; exit 1; }
  fi

  mkdir -p "$ABLAGE"
  chown "$BENUTZER" "$ABLAGE" 2>/dev/null || true

  blau "Stick $geraet"

  # Der Stick wird nur gelesen, nie beschrieben, und haengt so kurz wie
  # moeglich: ro gegen Unfaelle, noexec/nosuid/nodev, weil ein fremder
  # Datentraeger nichts mitbringen soll, was sich ausfuehren laesst.
  if [ -n "$ohne_einhaengen" ]; then
    EINHAENGEPUNKT="$ohne_einhaengen"
    gut "Pruefstand: $EINHAENGEPUNKT gilt als eingehaengt"
  else

  mkdir -p "$EINHAENGEPUNKT"
  local eingehaengt=""
  # ntfs3 gibt es erst ab Kernel 5.15, aelteres Debian kennt nur das
  # ntfs-3g ueber FUSE. Deshalb der Reihe nach statt auf einem Typ zu
  # bestehen.
  for typ in auto vfat exfat ntfs3 ntfs-3g; do
    if mount -t "$typ" -o ro,noexec,nosuid,nodev \
             "$geraet" "$EINHAENGEPUNKT" 2>/dev/null; then
      eingehaengt="$typ"; break
    fi
  done
  if [ -z "$eingehaengt" ]; then
    warn "$geraet liess sich nicht einhaengen (weder vfat, exfat noch ntfs)."
    warn "Kein Grund zur Sorge, wenn das gar kein Update-Stick war."
    rmdir "$EINHAENGEPUNKT" 2>/dev/null
    exit 0
  fi
  gut "eingehaengt als $eingehaengt, nur lesend"

  # Ab hier haengt etwas. Egal wo es scheitert, es wird wieder
  # ausgehaengt -- auch beim Abbruch von aussen.
  trap 'umount "$EINHAENGEPUNKT" 2>/dev/null; rmdir "$EINHAENGEPUNKT" 2>/dev/null' \
       EXIT INT TERM
  fi

  # Gross- und Kleinschreibung offen lassen: auf vfat ist sie ohnehin
  # egal, und wer die Datei unter Windows anlegt, bekommt leicht
  # UPD-DEV.TXT.
  local ausloeser
  # maxdepth 2 statt 1, und das ist Absicht: der haeufigste Fehler beim
  # Kopieren wird sein, dass jemand den ganzen Ordner "Devarenu-Stick"
  # auf den Stick zieht, statt seinen Inhalt. Dann laegen die Dateien
  # eine Ebene tiefer -- und der Rechner haette schweigend gar nichts
  # gemerkt. Sonntagmorgen ist das die falsche Art von Raetsel.
  local treffer anzahl
  treffer="$(find "$EINHAENGEPUNKT" -maxdepth 2 -iname 'upd-dev.txt' \
             -type f 2>/dev/null | sort)"
  anzahl="$(printf '%s' "$treffer" | grep -c . || true)"

  # Mehr als eine: NICHT raten. Der wahrscheinliche Fall ist ein Stick,
  # auf dem noch ein alter Ordner von einem frueheren Update liegt --
  # und dann entscheidet die Reihenfolge von "find", welche Fassung
  # eingespielt wird. Eine Fassung, die vom Zufall abhaengt, ist
  # schlimmer als gar keine.
  if [ "$anzahl" -gt 1 ]; then
    fehl "Auf dem Stick liegen $anzahl Dateien upd-dev.txt."
    printf '%s\n' "$treffer" | sed "s|^$EINHAENGEPUNKT/||; s|^|     |"
    stand_schreiben mehrdeutig "" \
      "Auf dem Stick liegen $anzahl Update-Ordner. Es ist nicht zu erkennen, welcher gemeint ist. Den Stick an einem anderen Rechner leeren, nur den neuen Ordner daraufkopieren und noch einmal einstecken."
    exit 1
  fi

  ausloeser="$(printf '%s' "$treffer" | head -1)"
  if [ -z "$ausloeser" ]; then
    # Der Normalfall: irgendein Stick, kein Update. Nichts melden, nichts
    # in die Statusdatei schreiben -- sonst ueberschreibt der Fotostick
    # der Gemeinde die Meldung eines echten Updates.
    gut "kein upd-dev.txt, also kein Update-Stick. Nichts zu tun."
    exit 0
  fi

  # tr -d '\r': unter Windows geschrieben hat die Zeile ein CR am Ende,
  # und die Fassung hiesse dann "0.3.0<CR>" -- der Vergleich scheitert,
  # ohne dass man sieht warum.
  local version
  version="$(tr -d '\r' < "$ausloeser" \
             | sed -n 's/^[[:space:]]*version[[:space:]]*=[[:space:]]*v\{0,1\}\([0-9][0-9A-Za-z.-]*\).*/\1/p' \
             | head -1)"
  if [ -z "$version" ]; then
    fehl "upd-dev.txt enthaelt keine Zeile version=vX.Y.Z"
    stand_schreiben unlesbar "" \
      "Der Stick hat eine Datei upd-dev.txt, aber darin steht keine Version."
    exit 1
  fi
  gut "upd-dev.txt nennt Fassung $version"

  # Ab hier gilt der Ordner, in dem upd-dev.txt wirklich lag -- oben
  # oder eine Ebene tiefer. Alles andere wird relativ dazu gesucht.
  QUELLORDNER="$(dirname "$ausloeser")"
  if [ "$QUELLORDNER" != "$EINHAENGEPUNKT" ]; then
    info "Die Dateien liegen in $(basename "$QUELLORDNER")/ statt oben."
    info "Das geht auch, ist aber nicht noetig."
  fi

  local bundle="$QUELLORDNER/devarenu.bundle"
  if [ ! -f "$bundle" ]; then
    fehl "devarenu.bundle fehlt auf dem Stick"
    stand_schreiben unvollstaendig "$version" \
      "Auf dem Stick fehlt devarenu.bundle. Der Stick ist unvollstaendig."
    exit 1
  fi

  # Alles auf die Platte, dann sofort aushaengen. Der Rest der Pruefung
  # laeuft ohne Stick -- wer ihn nach dem Aufleuchten abzieht, soll nichts
  # kaputt machen koennen.
  blau "Kopieren"
  mkdir -p "$DATEN"
  chmod 700 "$DATEN"
  rm -rf "$DATEN/wheels" "$DATEN/devarenu.bundle" "$DATEN/teile"
  cp "$bundle" "$DATEN/devarenu.bundle" || {
    fehl "Kopieren fehlgeschlagen. Platte voll?"
    stand_schreiben fehlgeschlagen "$version" \
      "Das Bundle liess sich nicht auf die Platte kopieren. Platte voll?"
    exit 1; }
  gut "devarenu.bundle ($(du -h "$DATEN/devarenu.bundle" | cut -f1))"

  if [ -d "$QUELLORDNER/wheels" ]; then
    cp -r "$QUELLORDNER/wheels" "$DATEN/wheels" || {
      fehl "Wheels liessen sich nicht kopieren"
      stand_schreiben fehlgeschlagen "$version" \
        "Die Pakete vom Stick liessen sich nicht auf die Platte kopieren."
      exit 1; }
    gut "wheels/ ($(find "$DATEN/wheels" -name '*.whl' | wc -l) Pakete)"
  else
    gut "keine wheels/ dabei (nur noetig, wenn sich requirements.txt aendert)"
  fi

  # Grosse Teile, falls der Stick welche mitbringt. Ein Stick ohne sie
  # ist der Normalfall und bleibt es -- das Format von 0.2.12 muss
  # weiter funktionieren.
  if [ -d "$QUELLORDNER/teile" ]; then
    cp -r "$QUELLORDNER/teile" "$DATEN/teile" || {
      fehl "Grosse Teile liessen sich nicht kopieren"
      stand_schreiben fehlgeschlagen "$version" \
        "Die grossen Teile vom Stick liessen sich nicht kopieren. Platte voll?"
      exit 1; }
    gut "teile/ ($(du -sh "$DATEN/teile" | cut -f1))"
  else
    gut "keine teile/ dabei"
  fi

  # Nutzlast gehoert der Wurzel und niemandem sonst: in den Sicherungen
  # liegt spaeter eine Kopie von zustand.json samt WLAN-Passwort.
  chmod -R go-rwx "$DATEN" 2>/dev/null || true
  chown -R "$BENUTZER" "$ABLAGE" 2>/dev/null || true

  umount "$EINHAENGEPUNKT" 2>/dev/null
  rmdir "$EINHAENGEPUNKT" 2>/dev/null
  trap - EXIT INT TERM
  gut "Stick ausgehaengt, kann abgezogen werden"

  pruefen_und_vormerken "$version"
}

# --------------------------------------------------------------- pruefen
pruefen_und_vormerken() {
  local version="$1"

  blau "Pruefen"

  command -v git >/dev/null || { fehl "git fehlt"; exit 1; }
  [ -d .git ] || { fehl "Kein git-Arbeitsverzeichnis"; exit 1; }

  if ! als_benutzer git bundle verify "$DATEN/devarenu.bundle" >/dev/null 2>&1; then
    fehl "git bundle verify schlaegt fehl"
    stand_schreiben fehlgeschlagen "$version" \
      "Das Bundle auf dem Stick ist beschaedigt oder passt nicht zu diesem Rechner."
    exit 1
  fi
  gut "Bundle ist unversehrt"

  # Bewusst nach refs/stick/ und nicht nach refs/tags/: ein Stick koennte
  # ein Tag mitbringen, das es hier schon gibt, und dann stuende die
  # Pruefung vor zwei Bedeutungen desselben Namens. Unter eigenem Dach
  # kann er nichts ueberschreiben.
  local ref="refs/stick/v$version"
  als_benutzer git update-ref -d "$ref" 2>/dev/null
  if ! als_benutzer git fetch --quiet "$DATEN/devarenu.bundle" \
       "refs/tags/v$version:$ref" 2>/dev/null; then
    fehl "Im Bundle steckt kein Tag v$version"
    stand_schreiben unvollstaendig "$version" \
      "Im Bundle auf dem Stick fehlt das Tag v$version. Der Stick ist unvollstaendig."
    exit 1
  fi
  gut "Tag v$version aus dem Bundle geholt"

  # Der wichtigste Schritt. Geprueft wird gegen die Schluesselliste, die
  # HIER liegt -- nie gegen die im Bundle. Sonst brauchte ein Angreifer
  # nur einen Stick, der seinen eigenen Schluessel mitbringt, und die
  # Signatur pruefte sich selbst.
  #
  # Die Kopie nach /run stellt sicher, dass spaeter kein Auschecken die
  # Datei unter der Pruefung wegzieht.
  if [ ! -s "$ORDNER/schluessel.erlaubt" ]; then
    fehl "schluessel.erlaubt fehlt oder ist leer"
    stand_schreiben fehlgeschlagen "$version" \
      "Auf diesem Rechner fehlt die Liste der erlaubten Schluessel. Ohne sie wird nichts eingespielt."
    als_benutzer git update-ref -d "$ref"
    exit 1
  fi
  install -m 644 "$ORDNER/schluessel.erlaubt" "$SCHLUESSEL_KOPIE"

  # -c statt dauerhafter Einstellung: auf dem Gemeinderechner soll nach
  # der Pruefung nichts in der git-Konfiguration zurueckbleiben.
  if ! als_benutzer git -c "gpg.ssh.allowedSignersFile=$SCHLUESSEL_KOPIE" \
       verify-tag "$ref" >/dev/null 2>&1; then
    fehl "Signatur von v$version ist ungueltig"
    stand_schreiben signatur "$version" \
      "Die Signatur des Updates v$version stimmt nicht. Es wird nicht eingespielt."
    als_benutzer git update-ref -d "$ref"
    rm -f "$SCHLUESSEL_KOPIE"
    exit 1
  fi
  rm -f "$SCHLUESSEL_KOPIE"
  gut "Signatur von v$version ist gueltig"

  local hier; hier="$(version_hier)"
  if ! ist_neuer "$hier" "$version"; then
    gut "Hier laeuft $hier. Das Update ist nicht neuer, es passiert nichts."
    stand_schreiben nicht_neuer "$version" \
      "Der Stick bringt Fassung $version, hier laeuft schon $hier. Nichts zu tun."
    als_benutzer git update-ref -d "$ref"
    exit 0
  fi
  gut "$hier -> $version, das ist neuer"

  # Dieselbe Haltung wie aktualisieren.sh: was jemand vor Ort geaendert
  # hat, wird nicht ueberschrieben. Ein Gemeinderechner ist kein Ort fuer
  # automatische Konfliktloesung.
  local schmutz
  schmutz="$(als_benutzer git status --porcelain --untracked-files=no)"
  if [ -n "$schmutz" ]; then
    fehl "Es gibt lokale Aenderungen. Abgebrochen, nichts angefasst."
    printf '%s\n' "$schmutz" | sed 's/^/     /'
    stand_schreiben schmutzig "$version" \
      "Im Ordner liegen lokale Aenderungen. Das Update wartet, bis sie geklaert sind."
    als_benutzer git update-ref -d "$ref"
    exit 1
  fi
  gut "keine lokalen Aenderungen"

  printf '%s\n' "$version" > "$BEREIT"
  chmod 644 "$BEREIT"
  rm -f "$RUHIG"
  stand_schreiben bereit "$version" \
    "Update $version liegt geprueft bereit. Es wird eingespielt, wenn 20 Minuten nichts laeuft und niemand verbunden ist, oder sofort unter Einrichtung -> Jetzt einspielen."
  blau "Bereit"
  echo "   Der Stick kann abgezogen werden. Eingespielt wird nach dem Anhalten."
}

# =========================================================== EINSPIELEN
einspielen() {
  [ -s "$BEREIT" ] || exit 0          # nichts vorgemerkt, still zurueck

  # Gleich zu Beginn und nicht erst vor dem Einspielen: liefe ein zweiter
  # Aufruf gleichzeitig los, zaehlten beide an derselben Ruhezeit mit und
  # kaemen doppelt so schnell ans Ziel. systemd startet eine oneshot-Unit
  # zwar nicht zweimal nebeneinander, aber darauf muss sich das Skript
  # nicht verlassen.
  exec 9>"$SPERRE"
  flock -n 9 || exit 0

  local version; version="$(tr -d '\r \n' < "$BEREIT")"
  local ref="refs/stick/v$version"

  # Zwischendurch koennte von Hand aktualisiert worden sein.
  local hier; hier="$(version_hier)"
  if ! ist_neuer "$hier" "$version"; then
    rm -f "$BEREIT" "$RUHIG" "$JETZT"
    stand_schreiben nicht_neuer "$version" \
      "Hier laeuft inzwischen $hier. Das vorgemerkte Update $version ist nicht mehr noetig."
    exit 0
  fi

  # ------------------------------------------------------------ warten
  local antwort; antwort="$(zustand_holen)"
  local live gesamt
  if [ -z "$antwort" ]; then
    # Der Dienst antwortet nicht. Das kann ein Neustart sein oder ein
    # Absturz -- in beiden Faellen ist jetzt nicht der Moment, Dateien
    # auszutauschen. Beim naechsten Lauf noch einmal.
    exit 0
  fi
  live="$(feld "$antwort" live)"
  gesamt="$(feld "$antwort" gesamt)"

  local sofort=""
  [ -f "$JETZT" ] && sofort=ja       # am Pult gedrueckt

  if [ "$live" = "True" ] || [ "$live" = "true" ]; then
    printf '0\n' > "$RUHIG"
    stand_schreiben wartet "$version" \
      "Update $version liegt bereit. Es wird eingespielt, wenn 20 Minuten nichts laeuft und niemand verbunden ist, oder sofort unter Einrichtung -> Jetzt einspielen."
    exit 0
  fi

  if [ -z "$sofort" ]; then
    # Angehalten allein genuegt nicht: zwischen Lied und Predigt ist auch
    # angehalten, und ein Neustart kostet dort eine Minute Modellladen.
    # Erst wenn lange nichts mehr passiert und niemand mehr zuhoert, ist
    # der Gottesdienst wirklich vorbei.
    local n=0
    [ -f "$RUHIG" ] && n="$(tr -d '\r \n' < "$RUHIG")"
    case "$n" in ''|*[!0-9]*) n=0 ;; esac
    # Hoert noch jemand zu, faengt die Ruhezeit von vorn an. Ein leeres
    # Feld zaehlt als niemand: dann hat der Server nichts dazu gesagt,
    # und die Uebersetzung ist ohnehin angehalten.
    if [ -n "${gesamt:-}" ] && [ "$gesamt" != "0" ]; then
      n=0
    else
      n=$((n + 1))
    fi
    printf '%s\n' "$n" > "$RUHIG"
    if [ "$n" -lt "$RUHE_LAEUFE" ]; then
      stand_schreiben wartet "$version" \
        "Update $version liegt bereit. Es wird eingespielt, wenn 20 Minuten nichts laeuft und niemand verbunden ist, oder sofort unter Einrichtung -> Jetzt einspielen."
      exit 0
    fi
  fi

  # ------------------------------------------------------- einspielen
  blau "Update $hier -> $version einspielen"
  rm -f "$JETZT"

  local vorher_summe; vorher_summe="$(zustand_pruefsumme)"
  local alt_sha; alt_sha="$(als_benutzer git rev-parse HEAD)"
  als_benutzer git update-ref refs/devarenu/vorher "$alt_sha"
  gut "Rueckweg gemerkt: $hier ($(printf '%.7s' "$alt_sha"))"

  # ------------------------------------------------- Stand sichern
  # Alles, was das Update anfassen koennte und was sich nicht aus git
  # zurueckholen laesst. Ohne diese Sicherung ist "zurueck" nur ein
  # halber Rueckweg.
  local sicherung="$DATEN/vorher-$version"
  rm -rf "$sicherung"; mkdir -p "$sicherung/units"
  chmod 700 "$sicherung"
  for u in devarenu.service devarenu-stick@.service \
           devarenu-update.service devarenu-update.timer; do
    [ -f "/etc/systemd/system/$u" ] \
      && cp -a "/etc/systemd/system/$u" "$sicherung/units/$u"
  done
  for d in zustand.json netz.json; do
    [ -f "$ORDNER/$d" ] && cp -a "$ORDNER/$d" "$sicherung/$d"
  done
  chmod -R go-rwx "$sicherung" 2>/dev/null || true
  gut "Stand gesichert: Units, zustand.json, netz.json"

  # Welche Fehler gab es SCHON? Ein Rechner, bei dem vorher etwas im
  # Argen lag, soll deshalb kein Update zurueckrollen.
  DEV_SICHERUNG="$sicherung" als_benutzer bash "$ORDNER/gesundheit.sh" --vorher \
    >/dev/null 2>&1 || true

  # Vorspulen statt Auschecken -- aber nicht hier. Ein ausgecheckter Tag
  # laesst HEAD abgeloest zurueck, und aktualisieren.sh findet danach
  # kein Gegenstueck mehr. Das Vorspulen macht die neue Logik.
  local zweig; zweig="$(als_benutzer git rev-parse --abbrev-ref HEAD)"
  if [ "$zweig" = "HEAD" ]; then
    fehl "HEAD ist abgeloest. Erst wieder auf einen Zweig stellen."
    stand_schreiben fehlgeschlagen "$version" \
      "Der Ordner steht nicht auf einem Zweig. Das Update wurde nicht eingespielt."
    exit 1
  fi

  # ------------------------------------------- die neue Logik holen
  # Ausgepackt wird ueber die GEPRUEFTE Objekt-SHA aus refs/stick/vX,
  # niemals ueber den Tagnamen. Ein gleichnamiger lokaler Tag wuerde
  # sonst etwas Ungeprueftes unterschieben -- nachgewiesen: mit einem
  # ueberschriebenen Tag nimmt "git archive vX" das Gefaelschte,
  # "git archive refs/stick/vX" das Echte.
  local geprueft_sha
  geprueft_sha="$(als_benutzer git rev-parse --verify "$ref^{commit}" 2>/dev/null)"
  if [ -z "$geprueft_sha" ]; then
    fehl "Die geprueufte Referenz $ref ist nicht aufzuloesen."
    stand_schreiben fehlgeschlagen "$version" \
      "Der geprueufte Stand liess sich nicht finden. Nichts geaendert."
    exit 1
  fi

  # Ausgepackt wird unter /var/lib/devarenu/updates -- NICHT unter
  # /tmp. Dort darf jeder Benutzer Dateien anlegen, und zwischen
  # Auspacken und Ausfuehren laege ein Fenster, in dem jemand die
  # Skriptdatei austauschen koennte. Hier gehoert alles der Wurzel und
  # ist fuer sonst niemanden zugaenglich.
  local auszug="$DATEN/logik-$version"
  rm -rf "$auszug"
  mkdir -p "$auszug"
  chown root:root "$DATEN" "$auszug" 2>/dev/null || true
  chmod 700 "$DATEN" "$auszug"

  # Nachsehen statt hoffen: waere hier etwas fuer Gruppe oder andere
  # beschreibbar, duerfte darin nichts ausgefuehrt werden.
  local rechte; rechte="$(stat -c %a "$auszug" 2>/dev/null)"
  if [ "$rechte" != "700" ]; then
    fehl "$auszug hat Rechte $rechte statt 700. Es wird nichts ausgefuehrt."
    rm -rf "$auszug"
    stand_schreiben fehlgeschlagen "$version" \
      "Das Auspackverzeichnis liess sich nicht absichern. Nichts geaendert."
    exit 1
  fi

  # git archive laeuft als der Benutzer (ihm gehoert das Repo), tar als
  # Wurzel -- die ausgepackten Dateien gehoeren damit der Wurzel.
  if ! als_benutzer git archive "$geprueft_sha" | tar -x -C "$auszug"; then
    fehl "Der geprueufte Stand liess sich nicht auspacken."
    rm -rf "$auszug"
    stand_schreiben fehlgeschlagen "$version" \
      "Der geprueufte Stand liess sich nicht auspacken. Nichts geaendert."
    exit 1
  fi
  gut "Logik aus $(printf '%.7s' "$geprueft_sha") ausgepackt"

  # Faellt sie aus, gilt der alte Weg. So laeuft ein Update von einer
  # Fassung ohne aktualisierung.sh weiter -- und der Kern muss nicht
  # wissen, ab wann es sie gibt.
  if [ ! -x "$auszug/aktualisierung.sh" ] && [ ! -f "$auszug/aktualisierung.sh" ]; then
    fehl "Die neue Fassung bringt keine aktualisierung.sh mit."
    rm -rf "$auszug"
    stand_schreiben fehlgeschlagen "$version" \
      "Dieses Update laesst sich mit dem hiesigen Updater nicht einspielen."
    exit 1
  fi

  # ------------------------------------------------------ uebergeben
  blau "Einspielen"
  local ausgabe rc=0
  ausgabe="$(DEV_ORDNER="$ORDNER" DEV_BENUTZER="$BENUTZER" \
             DEV_ABLAGE="$DATEN" DEV_ALT_SHA="$alt_sha" DEV_REF="$ref" \
             DEV_VERSION="$version" DEV_HIER="$hier" \
             DEV_SICHERUNG="$sicherung" \
             bash "$auszug/aktualisierung.sh" 2>&1)" || rc=$?
  printf '%s\n' "$ausgabe" | grep -v '^MELDUNG|' | sed 's/^/   /'
  local meldung
  meldung="$(printf '%s\n' "$ausgabe" | sed -n 's/^MELDUNG|//p' | tail -3 \
             | tr '\n' ' ')"
  rm -rf "$auszug"

  if [ "$rc" != 0 ]; then
    fehl "Die Update-Logik ist gescheitert (Rueckgabe $rc)."
    zurueck "$alt_sha" ja "$sicherung"
    stand_schreiben fehlgeschlagen "$version" \
      "${meldung:-Update $version ist fehlgeschlagen.} Fassung $hier wurde wiederhergestellt und laeuft." \
      "$hier"
    exit 1
  fi

  # ---------------------------------------------------------- Zustand
  # Ein Update darf die Einstellungen der Gemeinde nicht anfassen.
  local nachher_summe; nachher_summe="$(zustand_pruefsumme)"
  if [ "$vorher_summe" = "$nachher_summe" ]; then
    gut "zustand.json unveraendert"
  else
    warn "zustand.json hat sich geaendert. Das darf ein Update nicht."
    warn "  vorher:  $vorher_summe"
    warn "  nachher: $nachher_summe"
  fi

  rm -f "$BEREIT" "$RUHIG" "$JETZT"
  als_benutzer git update-ref -d "$ref" 2>/dev/null
  local satz="Update auf Fassung $version ist eingespielt und laeuft."
  [ -n "$meldung" ] && satz="$satz $meldung"
  stand_schreiben eingespielt "$version" "$satz" "$hier"
  blau "Fertig"
}

# ----------------------------------------------------------- Handgriffe
zustand_pruefsumme() {
  [ -f zustand.json ] || { echo "keine"; return; }
  printf '%s %s' "$(sha256sum zustand.json | cut -d' ' -f1)" \
                 "$(stat -c %a zustand.json)"
}

# Laeuft mit dem NEUEN config.py, deshalb erst nach dem Vorspulen. Gibt
# den Mangel als Satz zurueck oder nichts, wenn alles da ist.
vorpruefung() {
  local modell
  modell="$(als_benutzer "$PY" -c \
    'import config; print(config.LIVE_MODELL)' 2>/dev/null)"
  if [ -n "$modell" ] && command -v ollama >/dev/null; then
    if ! ollama list 2>/dev/null | grep -q "^${modell%%:*}"; then
      echo "Das Update braucht das Sprachmodell $modell, das hier nicht liegt und ohne Netz nicht nachzuladen ist."
      return
    fi
  fi
}

# Fehlende Stimmen fuer die eingestellten Sprachen, als Aufzaehlung.
#
# Anders als das Sprachmodell ist das KEIN Abbruchgrund: eine Sprache
# ohne Stimme laeuft als reiner Untertitel weiter, das ist ein Mangel und
# kein Ausfall. Gesagt werden muss es trotzdem, sonst sucht am Sabbat
# jemand den Fehler beim Ton.
stimmen_fehlen() {
  als_benutzer "$PY" - <<'PYCODE' 2>/dev/null
import config, zustand
z = zustand.laden()
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
}

# Zweites Argument gesetzt heisst: auch wieder starten. Ohne wurde noch
# nicht neu gestartet, dann laeuft der alte Dienst unberuehrt weiter.
# Der Rueckweg gehoert in den Kern, nicht in die Update-Logik: wenn die
# gescheitert ist, kann man ihr nichts mehr anvertrauen.
#
# Zurueckgeholt wird alles, was das Update angefasst haben koennte und
# was git nicht selbst wiederherstellt:
#
#   Code            git reset --hard auf den alten Stand
#   venv            der Symlink zurueck auf das alte (das neue bleibt
#                   liegen; loeschen kann man spaeter, beim naechsten
#                   Versuch wird es ohnehin neu gebaut)
#   Units           aus der Sicherung, dann daemon-reload
#   zustand.json    aus der Sicherung, ABER nur wenn sie sich geaendert
#   netz.json       hat -- eine unveraenderte Datei anzufassen waere ein
#                   zweiter Eingriff ohne Grund
zurueck() {
  local sha="$1" starten="${2:-}" sicherung="${3:-}"
  warn "zurueck auf $(printf '%.7s' "$sha")"
  als_benutzer git reset --hard --quiet "$sha" || fehl "git reset fehlgeschlagen"

  if [ -n "$sicherung" ] && [ -d "$sicherung" ]; then
    # venv: der Symlink zurueck. Verschoben wird nichts -- in einem venv
    # stehen die Pfade in den Skripten, ein verschobenes startet nicht.
    if [ -f "$sicherung/venv-vorher" ]; then
      local altes; altes="$(cat "$sicherung/venv-vorher")"
      if [ -n "$altes" ] && [ -d "$ORDNER/$altes" ]; then
        als_benutzer ln -sfn "$altes" "$ORDNER/.venv"
        warn "venv zurueck auf $altes"
      fi
    fi

    local u geaendert=nein
    for u in devarenu.service devarenu-stick@.service \
             devarenu-update.service devarenu-update.timer; do
      [ -f "$sicherung/units/$u" ] || continue
      if ! cmp -s "$sicherung/units/$u" "/etc/systemd/system/$u"; then
        cp -a "$sicherung/units/$u" "/etc/systemd/system/$u"
        warn "$u zurueckgeholt"
        geaendert=ja
      fi
    done
    [ "$geaendert" = ja ] && systemctl daemon-reload 2>/dev/null

    local d
    for d in zustand.json netz.json; do
      [ -f "$sicherung/$d" ] || continue
      if ! cmp -s "$sicherung/$d" "$ORDNER/$d"; then
        cp -a "$sicherung/$d" "$ORDNER/$d"
        chown "$BENUTZER" "$ORDNER/$d" 2>/dev/null || true
        warn "$d zurueckgeholt (das Update hatte sie veraendert)"
      fi
    done
  fi

  if [ -n "$starten" ]; then
    systemctl restart "$NAME" || fehl "Neustart nach dem Zurueckgehen fehlgeschlagen"
  fi
}

# Der Dienst gilt als gesund, wenn er die ERWARTETE Fassung meldet.
# "Antwortet" allein genuegt nicht: systemctl restart kehrt sofort
# zurueck, und in den ersten Sekunden antwortet womoeglich noch der alte
# Prozess -- der wuerde ein Update bestaetigen, das gleich stirbt.
#
# 60 Durchlaeufe zu 2 Sekunden, wie in dienst.sh. Der Server laedt beim
# Start das Whisper-Modell; bei kaltem Zwischenspeicher dauert das.
gesund() {
  local erwartet="$1" i antwort
  for i in $(seq 1 60); do
    antwort="$(zustand_holen)"
    if [ -n "$antwort" ] && [ "$(feld "$antwort" fassung)" = "$erwartet" ]; then
      return 0
    fi
    systemctl is-active --quiet "$NAME" || return 1
    sleep 2
  done
  return 1
}

stand_zeigen() {
  if [ -s "$STAND" ]; then cat "$STAND"; else echo "Kein Update vorgemerkt."; fi
}

# ================================================================ Aufruf
case "${1:---stand}" in
  --lesen)
    [ $# -ge 2 ] || { fehl "Aufruf: $0 --lesen /dev/sdb1"; exit 1; }
    [ "$(id -u)" = "0" ] || { fehl "--lesen braucht root (haengt ein)"; exit 1; }
    stick_lesen "$2" ;;
  --einspielen)
    [ "$(id -u)" = "0" ] || { fehl "--einspielen braucht root (startet den Dienst neu)"; exit 1; }
    einspielen ;;
  --stand)
    stand_zeigen ;;
  *)
    echo "Aufruf: $0 [--lesen /dev/sdb1 | --einspielen | --stand]"
    exit 1 ;;
esac
