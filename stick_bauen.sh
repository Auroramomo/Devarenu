#!/usr/bin/env bash
# Einen Update-Stick fuer die Gemeinderechner bauen. Laeuft zuhause.
#
#   bash stick_bauen.sh /run/media/name/STICK
#   bash stick_bauen.sh /run/media/name/STICK --python 3.12
#
# Ohne --python gilt 3.14 -- die Fassung auf dem Gemeinderechner.
#   bash stick_bauen.sh /run/media/name/STICK --ohne-wheels
#
# OHNE STICK, als ZIP zum Verschicken:
#   bash stick_bauen.sh --zip ~/Devarenu-Stick-v0.3.0.zip
# Die Dateien liegen im ZIP GANZ OBEN, nicht in einem Unterordner.
# Windows entpackt es dadurch in einen Ordner, der nach dem ZIP heisst,
# und dieser eine Ordner darf unveraendert auf den Stick. Mit einem
# Unterordner im ZIP waeren es zwei Ebenen, und der Rechner sucht nur
# eine tief.
#   bash stick_bauen.sh --nur-constraints          nach jeder Aenderung an
#                                               requirements.txt
#
# GROSSE TEILE (Sprachmodell, Spracherkennung, Stimmen)
#   --von v0.2.12   nur das, was sich seit v0.2.12 geaendert hat
#   --voll          alles, rund vierzehn Gigabyte
#   ohne Angabe     gar keine. Das ist der Normalfall: die meisten
#                   Updates aendern nur Code.
#
# Legt auf den Stick:
#   upd-dev.txt        die Zeile, an der der Gemeinderechner das Update erkennt
#   devarenu.bundle    das Repo als eine Datei
#   wheels/            die Python-Pakete, falls gebraucht
#   teile/             grosse Teile, nur mit --von oder --voll
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
# Siehe stick_update.sh: dieselbe fehlende Funktion. Hier traf es den
# NORMALFALL -- jeder Bau ohne --von/--voll rief dreimal den
# texinfo-Leser auf.
info() { printf '        %s\n' "$1"; }

# Die Gemeinderechner laufen auf Debian oder Ubuntu, dieser hier auf
# CachyOS -- mit einer anderen Python-Fassung. Wheels, die hier passen,
# passen dort nicht. Deshalb wird die Zielfassung gesetzt und nicht
# geraten.
# Die Fassung des Ziel-Rechners, nicht die dieses hier. Der
# Gemeinderechner laeuft seit dem 23.09.2026 auf CachyOS mit Python
# 3.14; Wheels fuer 3.13 passen dort nicht.
ZIEL_PYTHON=3.14
# manylinux_2_28 deckt Debian 12 und neuer sowie Ubuntu 22.04 und neuer
# ab. manylinux2014 steht daneben, weil einige Pakete bis heute nur dafuer
# bauen; pip nimmt je Paket, was passt.
ZIEL_PLATTFORM=(--platform manylinux_2_28_x86_64 --platform manylinux2014_x86_64)
WHEELS=ja
STICK=""

NUR_BEDINGUNGEN=nein
VON=""
VOLL=nein
ZIEL_ZIP=""
ZIP_MODUS=nein

while [ $# -gt 0 ]; do
  case "$1" in
    --python)           ZIEL_PYTHON="${2:-}"; shift 2 ;;
    --ohne-wheels)      WHEELS=nein; shift ;;
    --nur-constraints)  NUR_BEDINGUNGEN=ja; shift ;;
    --zip)              ZIEL_ZIP="${2:-}"; shift 2 ;;
    --von)              VON="${2:-}"; shift 2 ;;
    --voll)             VOLL=ja; shift ;;
    -h|--hilfe|--help|-\?)
                    sed -n '2,37p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*)             fehl "Unbekannt: $1"; exit 1 ;;
    *)              STICK="$1"; shift ;;
  esac
done

# ------------------------------------------------------------ Bedingungen
# constraints.txt neu aufloesen. Braucht weder Stick noch Tag: es geht
# nur darum, welche Fassungen pip fuer die Zielversion zusammenstellt.
# Nach jeder Aenderung an requirements.txt faellig.
if [ "$NUR_BEDINGUNGEN" = "ja" ]; then
  blau "constraints.txt fuer Python $ZIEL_PYTHON"
  ZWISCHEN="$(mktemp -d)"
  # trap und nicht rm am Ende: bei Abbruch bleibt sonst ein Ordner mit
  # ein paar hundert Megabyte im temporaeren Verzeichnis liegen.
  trap 'rm -rf "$ZWISCHEN"' EXIT INT TERM
  # Bewusst OHNE -c: hier entsteht die Aufloesung ja gerade erst. Mit der
  # alten Datei als Bedingung koennte sie sich nie aendern.
  pip download -r requirements.txt -d "$ZWISCHEN" \
    --only-binary=:all: --python-version "$ZIEL_PYTHON" \
    "${ZIEL_PLATTFORM[@]}" 2>&1 | tail -3 | sed 's/^/   /'
  ls "$ZWISCHEN"/*.whl >/dev/null 2>&1 || {
    fehl "pip hat nichts geholt. Oben nachlesen."; exit 1; }

  ZIEL_PYTHON="$ZIEL_PYTHON" python3 - "$ZWISCHEN" <<'PYCODE'
import pathlib, re, sys, os
quelle = pathlib.Path(sys.argv[1])
paare = {}
for w in sorted(quelle.glob("*.whl")):
    teile = w.name[:-4].split("-")
    paare[teile[0].replace("_", "-").lower()] = teile[1]
direkt = {m.group(1).replace("_", "-").lower()
          for m in (re.match(r"^([A-Za-z][A-Za-z0-9._-]*)==", z.strip())
                    for z in open("requirements.txt", encoding="utf-8")) if m}
kopf = pathlib.Path("constraints.txt").read_text(encoding="utf-8") \
    .split("\n\n", 1)[0] + "\n\n" if pathlib.Path("constraints.txt").exists() else ""
zeilen = [f"{n}=={paare[n]}" + ("" if n in direkt else "    # mitgezogen")
          for n in sorted(paare)]
pathlib.Path("constraints.txt").write_text(kopf + "\n".join(zeilen) + "\n",
                                           encoding="utf-8")
print(f"   {len(paare)} Pakete, davon {len(direkt & set(paare))} direkt angefordert")
PYCODE
  gut "constraints.txt neu geschrieben"
  warn "Der Kommentarkopf der Datei bleibt stehen. Nachsehen, ob er noch stimmt."
  exit 0
fi

# ------------------------------------------------------------- Ziel
if [ -n "$ZIEL_ZIP" ]; then
  [ -z "$STICK" ] || { fehl "Entweder ein Stick ODER --zip, nicht beides."; exit 1; }
  case "$ZIEL_ZIP" in *.zip) ;; *) ZIEL_ZIP="$ZIEL_ZIP.zip" ;; esac
  ZIP_MODUS=ja
  # Gebaut wird in einen Wegwerfordner; ins ZIP kommt sein INHALT.
  ZIP_BAU="$(mktemp -d)"
  trap 'rm -rf "$ZIP_BAU"' EXIT INT TERM
  STICK="$ZIP_BAU"
fi

[ -n "$STICK" ] || {
  fehl "Aufruf: $0 /pfad/zum/stick [--python 3.14]"
  echo "   oder ohne Stick:  $0 --zip ~/Devarenu-Stick.zip"
  exit 1; }

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
if [ "$ZIP_MODUS" = ja ]; then
  blau "ZIP statt Stick"
  gut "gebaut wird nach $ZIEL_ZIP"
else
  blau "Stick"
fi

[ -d "$STICK" ] || { fehl "$STICK gibt es nicht oder es ist kein Ordner"; exit 1; }
[ -w "$STICK" ] || { fehl "$STICK ist nicht beschreibbar"; exit 1; }
[ "$ZIP_MODUS" = ja ] || gut "$STICK"

# Das Dateisystem interessiert hier nur fuer die Warnung: der
# Gemeinderechner nimmt vfat, exfat und ntfs gleichermassen. Auf vfat
# passt keine Datei ueber 4 GB -- mit wheels/ kommt man dem naeher, als
# einem lieb ist.
if [ "$ZIP_MODUS" = ja ]; then
  DATEISYSTEM=zip
else
  DATEISYSTEM="$(findmnt -n -o FSTYPE --target "$STICK" 2>/dev/null || echo unbekannt)"
  gut "Dateisystem $DATEISYSTEM"
fi

# FAT32 kann keine Datei ueber 4 GB. Das Sprachmodell allein ist
# groesser. Bis 0.3.0 wurde deshalb abgebrochen und ein anderes
# Dateisystem verlangt -- eine Zumutung fuer jemanden, der nur einen
# Stick bringen soll, und Sticks kommen nun einmal formatiert an.
#
# Seit 0.3.1 wird gestueckelt: teile.py schreibt Dateien ueber 3,5 GB
# in mehrere, und der Gemeinderechner setzt sie zusammen und prueft
# gegen die sha256 aus teile.json. Stimmt sie nicht, bleibt das Alte
# liegen.
#
# Gesagt wird es trotzdem: wer die Wahl hat, nimmt exFAT. Ein Stueck
# weniger ist ein Fehler weniger.
if [ "$VOLL" = ja ] || [ -n "$VON" ]; then
  case "$DATEISYSTEM" in
    vfat|msdos|fat|fat32)
      warn "Dieser Stick ist mit $DATEISYSTEM formatiert (FAT32)."
      warn "Dateien ueber 4 GB werden gestueckelt und auf dem"
      warn "Gemeinderechner wieder zusammengesetzt, gegen sha256"
      warn "geprueft. Das geht -- exFAT waere trotzdem einfacher."
      ;;
  esac
fi

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
  # -c constraints.txt: sonst haengt es vom Tag ab, welche Fassung der
  # vierzig mitgezogenen Pakete auf dem Stick landet.
  BEDINGUNG=""
  [ -f constraints.txt ] && BEDINGUNG="-c constraints.txt"
  if pip download -r requirements.txt $BEDINGUNG -d "$STICK/wheels" \
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

# ------------------------------------------------------- grosse Teile
# Nur auf Verlangen. Vierzehn Gigabyte gehoeren nicht auf jeden Stick,
# und die meisten Updates aendern ohnehin nur Code.
if [ "$VOLL" = ja ] || [ -n "$VON" ]; then
  blau "Grosse Teile"
  if [ ! -f "$ORDNER/teile.json" ]; then
    fehl "teile.json fehlt. Erst erfassen:"
    info "  python teile.py --erfassen"
    exit 1
  fi
  rm -rf "$STICK/teile"
  # Die venv des Projekts, weil teile.py config importiert.
  TPY="$ORDNER/.venv/bin/python"
  [ -x "$TPY" ] || TPY="$(command -v python3)"
  if ! "$TPY" "$ORDNER/teile.py" --auf-stick "$STICK/teile" \
       ${VON:+--von "$VON"} ${VOLL:+--voll}; then
    fehl "Die grossen Teile liessen sich nicht zusammenstellen."
    exit 1
  fi
  gut "teile/ ($(du -sh "$STICK/teile" 2>/dev/null | cut -f1))"
else
  info "Ohne --von oder --voll sind KEINE grossen Teile dabei."
  info "Braucht die neue Fassung ein anderes Sprachmodell oder neue"
  info "Stimmen, reicht dieser Stick nicht."
fi

sync

# ---------------------------------------------------------------- packen
if [ "$ZIP_MODUS" = ja ]; then
  blau "Packen"
  rm -f "$ZIEL_ZIP"
  # Ueber Python und nicht ueber "zip": das Paket ist auf einem
  # frischen Arbeitsrechner nicht immer da, das Modul zipfile dagegen
  # immer. Gepackt wird der INHALT des Bauordners, ohne Wrapper --
  # siehe Kopf dieser Datei.
  python3 - "$ZIP_BAU" "$ZIEL_ZIP" <<'PYCODE'
import os, sys, zipfile
quelle, ziel = sys.argv[1], sys.argv[2]
n = 0
with zipfile.ZipFile(ziel, "w", zipfile.ZIP_DEFLATED) as z:
    for wurzel, ordner, dateien in os.walk(quelle):
        ordner.sort(); dateien.sort()
        for d in dateien:
            voll = os.path.join(wurzel, d)
            z.write(voll, os.path.relpath(voll, quelle))
            n += 1
print(f"   {n} Dateien")
PYCODE
  [ -s "$ZIEL_ZIP" ] || { fehl "Das ZIP wurde nicht geschrieben."; exit 1; }
  gut "$ZIEL_ZIP ($(du -h "$ZIEL_ZIP" | cut -f1))"

  blau "Fertig"
  cat <<ENDE
   Im ZIP liegt Devarenu $VERSION ($TAG).

   So kommt es auf den Stick:
     1. ZIP auf den Windows-Rechner kopieren.
     2. Rechtsklick -> "Alle extrahieren".
     3. Den entstandenen Ordner OEFFNEN und die vier Dateien darin
        DIREKT OBEN auf den Stick ziehen -- nicht den Ordner selbst.

   Warum nicht der Ordner: Kerne vor 0.2.13 suchen upd-dev.txt NUR
   ganz oben. Der Gemeinderechner laeuft noch auf 0.2.11, findet die
   Dateien in einem Ordner also nicht und tut gar nichts. Genau daran
   ist ein Versuch schon gescheitert.

   Ab 0.2.13 ginge ein Ordner auch. Oben geht IMMER -- deshalb steht
   im Helferblatt nur dieser eine Weg.
ENDE
  exit 0
fi

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
