#!/usr/bin/env bash
# Einen Update-Stick fuer die Gemeinderechner bauen. Laeuft zuhause.
#
#   ./stick_bauen.sh /run/media/name/STICK
#   ./stick_bauen.sh /run/media/name/STICK --python 3.12
#   ./stick_bauen.sh /run/media/name/STICK --ohne-wheels
#
# Legt auf den Stick:
#   upd-dev.txt        die Zeile, an der der Gemeinderechner das Update erkennt
#   devarenu.bundle    das Repo als eine Datei
#   wheels/            die Python-Pakete, falls gebraucht
#   bootstrap.sh       Erstinstallation fuer Rechner, die das Verfahren
#                      noch nicht kennen
#
# Gebaut wird immer aus einem TAG, nie aus dem Arbeitsverzeichnis. Ein
# Update ohne Signatur waere auf dem Gemeinderechner wertlos -- es wuerde
# dort abgelehnt, und der Weg dahin ist weit.
#
# Gepusht wird hier nichts. Das Tag setzt und veroeffentlicht ein Mensch.

set -u
ORDNER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ORDNER"

blau() { printf '\n\033[1;34m== %s\033[0m\n' "$1"; }
gut()  { printf '   \033[32mok\033[0m   %s\n' "$1"; }
warn() { printf '   \033[33m!\033[0m    %s\n' "$1"; }
fehl() { printf '   \033[31mFEHLT\033[0m %s\n' "$1"; }

# Die Gemeinderechner laufen auf Debian oder Ubuntu, dieser hier auf
# CachyOS -- mit einer anderen Python-Fassung. Wheels, die hier passen,
# passen dort nicht. Deshalb wird die Zielfassung gesetzt und nicht
# geraten.
ZIEL_PYTHON=3.13
# manylinux_2_28 deckt Debian 12 und neuer sowie Ubuntu 22.04 und neuer
# ab. manylinux2014 steht daneben, weil einige Pakete bis heute nur dafuer
# bauen; pip nimmt je Paket, was passt.
ZIEL_PLATTFORM=(--platform manylinux_2_28_x86_64 --platform manylinux2014_x86_64)
WHEELS=ja
STICK=""

while [ $# -gt 0 ]; do
  case "$1" in
    --python)       ZIEL_PYTHON="${2:-}"; shift 2 ;;
    --ohne-wheels)  WHEELS=nein; shift ;;
    -h|--hilfe)     sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*)             fehl "Unbekannt: $1"; exit 1 ;;
    *)              STICK="$1"; shift ;;
  esac
done

[ -n "$STICK" ] || { fehl "Aufruf: $0 /pfad/zum/stick [--python 3.13]"; exit 1; }

# ---------------------------------------------------------------- pruefen
blau "Vorher nachsehen"

[ -d .git ] || { fehl "Kein git-Arbeitsverzeichnis"; exit 1; }

# Aus einem schmutzigen Ordner gebaut waere das Bundle nicht das, was das
# Tag verspricht -- und niemand saehe den Unterschied, bis es auf dem
# Gemeinderechner liegt.
SCHMUTZ="$(git status --porcelain --untracked-files=no)"
if [ -n "$SCHMUTZ" ]; then
  fehl "Es gibt lokale Aenderungen. Erst einchecken, dann bauen."
  printf '%s\n' "$SCHMUTZ" | sed 's/^/     /'
  exit 1
fi
gut "Arbeitsverzeichnis sauber"

VERSION="$(tr -d '\r' < VERSION | head -1 | tr -d ' ')"
TAG="v$VERSION"

if ! git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
  fehl "Das Tag $TAG gibt es nicht."
  echo "   VERSION sagt $VERSION, also wird $TAG gesucht. Setzen mit:"
  echo "     git tag -s $TAG -m \"Devarenu $VERSION\""
  echo "   (signiert, sonst lehnt der Gemeinderechner es ab)"
  exit 1
fi
gut "Tag $TAG vorhanden"

# Das Tag muss auf einen Stand zeigen, dessen VERSION-Datei dieselbe
# Fassung nennt. Sonst meldet der Gemeinderechner nach dem Einspielen
# eine andere Zahl als die, die eingespielt wurde -- und die
# Gesundheitspruefung schlaegt fehl, obwohl alles lief.
TAG_VERSION="$(git show "$TAG:VERSION" 2>/dev/null | tr -d '\r' | head -1 | tr -d ' ')"
if [ "$TAG_VERSION" != "$VERSION" ]; then
  fehl "$TAG zeigt auf VERSION=$TAG_VERSION, hier steht $VERSION."
  echo "   Beide muessen gleich sein. Entweder das Tag neu setzen oder"
  echo "   VERSION anpassen und neu einchecken."
  exit 1
fi
gut "$TAG traegt VERSION=$VERSION"

# ---------------------------------------------------------------- Signatur
blau "Signatur"

if [ ! -s schluessel.erlaubt ] || ! grep -qE '^[^#[:space:]]+[[:space:]]+(ssh|sk-)' schluessel.erlaubt; then
  fehl "schluessel.erlaubt enthaelt keinen Schluessel."
  echo "   Ohne sie laesst sich nicht pruefen, ob das Tag von der"
  echo "   richtigen Hand kommt -- und der Gemeinderechner lehnt ab."
  echo "   Schluessel erzeugen:"
  echo "     ssh-keygen -t ed25519 -C \"devarenu-freigabe\" -f ~/.ssh/devarenu_freigabe"
  echo "   Dann den Inhalt von ~/.ssh/devarenu_freigabe.pub eintragen, mit"
  echo "   \"$(git config user.email)\" davor."
  exit 1
fi

# Genau so prueft es spaeter der Gemeinderechner. Scheitert es hier,
# scheitert es dort auch -- nur merkt man es hier noch rechtzeitig.
if ! git -c "gpg.ssh.allowedSignersFile=$ORDNER/schluessel.erlaubt" \
     verify-tag "$TAG" 2>/dev/null; then
  fehl "$TAG ist nicht signiert oder die Signatur passt nicht zu schluessel.erlaubt."
  echo
  echo "   Haeufigste Ursache: die E-Mail. git verify-tag sucht die Zeile"
  echo "   zur Adresse aus dem Tagger-Feld, nicht zu irgendeinem Namen."
  echo "     Tagger:            $(git for-each-ref --format='%(taggeremail)' "refs/tags/$TAG")"
  echo "     schluessel.erlaubt: $(awk '!/^#/ && NF {print $1}' schluessel.erlaubt | tr '\n' ' ')"
  exit 1
fi
gut "$TAG ist gueltig signiert"

# Der Fingerabdruck geht mit auf den Stick und wird bei der
# Erstinstallation am Bildschirm angezeigt. Wer ihn dort bestaetigt, muss
# ihn von hier kennen -- ueber einen anderen Weg als den Stick selbst,
# sonst bestaetigt sich der Stick selbst.
blau "Fingerabdruck"
awk '!/^#/ && NF {$1=""; print substr($0,2)}' schluessel.erlaubt > /tmp/devarenu-schluessel.$$
while read -r zeile; do
  [ -z "$zeile" ] && continue
  printf '%s\n' "$zeile" > /tmp/devarenu-einzeln.$$
  printf '   %s\n' "$(ssh-keygen -lf /tmp/devarenu-einzeln.$$ 2>/dev/null || echo '(nicht lesbar)')"
done < /tmp/devarenu-schluessel.$$
rm -f /tmp/devarenu-schluessel.$$ /tmp/devarenu-einzeln.$$
echo
echo "   Diesen Fingerabdruck braucht der Techniker bei der"
echo "   Erstinstallation. Nicht ueber den Stick uebermitteln -- anrufen."

# ---------------------------------------------------------------- Stick
blau "Stick"

[ -d "$STICK" ] || { fehl "$STICK gibt es nicht oder es ist kein Ordner"; exit 1; }
[ -w "$STICK" ] || { fehl "$STICK ist nicht beschreibbar"; exit 1; }
gut "$STICK"

# Das Dateisystem interessiert hier nur fuer die Warnung: der
# Gemeinderechner nimmt vfat, exfat und ntfs gleichermassen. Auf vfat
# passt keine Datei ueber 4 GB -- mit wheels/ kommt man dem naeher, als
# einem lieb ist.
DATEISYSTEM="$(findmnt -n -o FSTYPE --target "$STICK" 2>/dev/null || echo unbekannt)"
gut "Dateisystem $DATEISYSTEM"

blau "Bundle"
# --all statt eines Ausschnitts ab dem letzten Tag: dann passt der Stick
# auf jeden Rechner, egal wie alt sein Stand ist. Bei diesem Repo kostet
# das nichts, .git ist gut ein Megabyte.
rm -f "$STICK/devarenu.bundle"
git bundle create "$STICK/devarenu.bundle" --all 2>&1 | sed 's/^/   /'
[ -s "$STICK/devarenu.bundle" ] || { fehl "Bundle wurde nicht erzeugt"; exit 1; }
gut "devarenu.bundle ($(du -h "$STICK/devarenu.bundle" | cut -f1))"

# ---------------------------------------------------------------- Wheels
if [ "$WHEELS" = "ja" ]; then
  blau "Pakete fuer Python $ZIEL_PYTHON"
  echo "   Die Gemeinderechner haben kein Netz. Was hier nicht mitkommt,"
  echo "   koennen sie nicht nachladen."
  rm -rf "$STICK/wheels"
  mkdir -p "$STICK/wheels"
  # --only-binary=:all: ist bei --platform Pflicht und hier ohnehin
  # richtig: eine Quelldistribution muesste auf dem Gemeinderechner
  # uebersetzt werden, und dafuer fehlt dort alles.
  if pip download -r requirements.txt -d "$STICK/wheels" \
       --only-binary=:all: \
       --python-version "$ZIEL_PYTHON" \
       "${ZIEL_PLATTFORM[@]}" 2>&1 | sed 's/^/   /'; then
    gut "$(find "$STICK/wheels" -name '*.whl' | wc -l) Pakete, $(du -sh "$STICK/wheels" | cut -f1)"
  else
    fehl "pip konnte nicht alle Pakete fuer Python $ZIEL_PYTHON holen."
    echo "   Steht oben ein Paketname: fuer diese Zielfassung gibt es kein"
    echo "   fertiges Wheel. Entweder die Version in requirements.txt"
    echo "   zuruecknehmen oder eine andere --python waehlen."
    exit 1
  fi
else
  warn "Ohne Wheels gebaut."
  warn "Aendert sich requirements.txt, bricht das Update auf dem"
  warn "Gemeinderechner ab -- vor dem Neustart, es bleibt also heil."
  rm -rf "$STICK/wheels"
fi

# ---------------------------------------------------------------- Beiwerk
blau "Ausloeser und Erstinstallation"

# Ohne diese Datei passiert auf dem Gemeinderechner gar nichts. Sie ist
# der ganze Unterschied zwischen einem Update-Stick und dem Fotostick der
# Gemeinde.
printf 'version=%s\n' "$TAG" > "$STICK/upd-dev.txt"
gut "upd-dev.txt  ($(cat "$STICK/upd-dev.txt"))"

if [ -f bootstrap.sh ]; then
  cp bootstrap.sh "$STICK/bootstrap.sh"
  cp schluessel.erlaubt "$STICK/schluessel.erlaubt"
  gut "bootstrap.sh und schluessel.erlaubt (nur fuer Rechner ohne das Verfahren)"
else
  warn "bootstrap.sh fehlt im Repo. Bestandsrechner koennen den Stick dann"
  warn "nicht selbst einrichten."
fi

sync

# ---------------------------------------------------------------- fertig
blau "Fertig"
cat <<ENDE
   Auf dem Stick liegt Devarenu $VERSION ($TAG).

   Rechner, die das Verfahren schon kennen (ab 0.2.1):
     Stick einstecken. Sonst nichts. Eingespielt wird nach dem
     Gottesdienst, das Pult zeigt es unter Einrichtung an.

   Rechner, die es noch nicht kennen:
     Stick einstecken, ein Fenster oeffnen und einmal aufrufen:
       sudo bash /pfad/zum/stick/bootstrap.sh
     Der Fingerabdruck von oben wird dabei abgefragt.

   Vor dem Weggeben nachsehen, ob der Stick wirklich geschrieben ist:
     ls -la $STICK
ENDE
