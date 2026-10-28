#!/usr/bin/env bash
# Devarenu-Update.zip bauen und an das GitHub-Release des Tags haengen
# (0.5.2). Laeuft zuhause, NACH dem Tag und dem Push.
#
#   bash release_zip.sh              bauen, pruefen, hochladen
#   bash release_zip.sh --trocken    bauen und pruefen, NICHT hochladen
#
# Danach zeigt
#   https://github.com/Auroramomo/Devarenu/releases/latest/download/Devarenu-Update.zip
# auf diese Fassung -- der Link, der am Pult unter Einrichtung -> Update
# steht. Das klappt, weil jede Fassung ihr ZIP unter DEMSELBEN Namen
# anhaengt.
#
# Was das Skript NICHT tut: taggen, pushen, signieren. Das Tag muss
# schon auf GitHub liegen (gh release create --verify-tag), sonst legte
# gh es selbst an -- unsigniert, auf dem Stand von main.
#
# Was im ZIP steht: das Bundle, die Wheels ohne NVIDIA-Pakete,
# upd-dev.txt, bootstrap.sh, schluessel.erlaubt. KEINE NVIDIA-Dateien
# (Weitergabe ungeklaert) -- geprueft, bevor irgendetwas hochgeht.
set -u
ORDNER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ORDNER"
blau() { printf '\n\033[1;34m== %s\033[0m\n' "$*"; }
gut()  { printf '   \033[32mok\033[0m   %s\n' "$*"; }
fehl() { printf '   \033[31mFEHLT\033[0m %s\n' "$*"; }

TROCKEN=nein
[ "${1:-}" = "--trocken" ] && TROCKEN=ja
REPO="Auroramomo/Devarenu"
NAME="Devarenu-Update.zip"
VERSION="$(tr -d '\r ' < VERSION | head -1)"
TAG="v$VERSION"
ABLAGE="${DEVARENU_RELEASE_ORDNER:-$HOME/Devarenu-Release/$TAG}"

blau "Vorher"
if [ "$TROCKEN" = nein ]; then
  command -v gh >/dev/null || { fehl "gh fehlt (github-cli)"; exit 1; }
  gh auth status >/dev/null 2>&1 || { fehl "gh ist nicht angemeldet: gh auth login"; exit 1; }
  if ! git ls-remote --exit-code --tags origin "refs/tags/$TAG" >/dev/null 2>&1; then
    fehl "$TAG liegt noch nicht auf GitHub. Erst: git push origin $TAG"
    exit 1
  fi
  gut "$TAG liegt auf GitHub"
fi

blau "Bauen"
# Ohne --mit-fremdteilen, ohne grosse Teile: das oeffentliche ZIP.
bash stick_bauen.sh --zip "$ABLAGE" || { fehl "stick_bauen.sh scheiterte"; exit 1; }
ZIP="$ABLAGE/$NAME"
[ -s "$ZIP" ] || { fehl "$ZIP fehlt"; exit 1; }

blau "Pruefen"
# Nichts Nicht-Oeffentliches darf hinaus. Nicht dem Bauskript glauben:
# in das fertige ZIP sehen. NVIDIA-Dateien, die Wheels, die
# pakete.sperre als "NICHT OEFFENTLICH" fuehrt (GPL-Binaerteile ohne
# Lizenztext oder Quellenangabe, siehe LIZENZEN.md), und grosse Teile
# (teile/: Modelle und Stimmen mit eigenen Bedingungen).
NICHT="$(python3 werkzeuge/sperre_pruefen.py --nicht-oeffentlich pakete.sperre \
         | paste -sd'|')"
FREMD="$(python3 -m zipfile -l "$ZIP" | awk '{print $1}' \
         | grep -iE "(^|/)(nvidia[-_]|cudart|libcu(blas|dart|dnn|fft|rand|solver|sparse))|^teile/|^wheels/(${NICHT:-NIE})-" || true)"
if [ -n "$FREMD" ]; then
  fehl "Im ZIP liegt, was nicht oeffentlich hinaus darf -- es geht NICHT hinaus:"
  printf '%s\n' "$FREMD" | sed 's/^/      /'
  exit 1
fi
gut "nichts Nicht-Oeffentliches im ZIP (NVIDIA, ${NICHT//|/, }, teile/)"
for f in LIZENZEN.md lizenzen/Apache-2.0.txt; do
  python3 -m zipfile -l "$ZIP" | awk '{print $1}' | grep -qx "$f" \
    || { fehl "$f fehlt im ZIP"; exit 1; }
done
gut "LIZENZEN.md und die Lizenztexte liegen bei"
python3 -m zipfile -l "$ZIP" | grep -q '^upd-dev.txt' \
  || { fehl "upd-dev.txt liegt nicht oben im ZIP"; exit 1; }
gut "upd-dev.txt oben ($(python3 -m zipfile -l "$ZIP" | grep '^upd-dev.txt' | head -1 | awk '{print $1}'))"
( cd "$ABLAGE" && sha256sum "$NAME" > "$NAME.sha256" )
gut "$(cat "$ABLAGE/$NAME.sha256")"

if [ "$TROCKEN" = ja ]; then
  blau "Trocken -- nichts hochgeladen"
  echo "   Hochladen waere:"
  echo "     gh release create $TAG $ZIP $ZIP.sha256 --repo $REPO \\"
  echo "        --verify-tag --title \"Devarenu $VERSION\" --notes-file <Abschnitt aus VERSIONEN.md>"
  exit 0
fi

blau "Hochladen"
NOTIZEN="$ABLAGE/notizen.md"
awk -v k="**$VERSION " 'index($0,k)==1{an=1;next} an&&/^\*\*[0-9]/{exit} an' \
  VERSIONEN.md > "$NOTIZEN"
printf '\nUpdate-Stick: %s unausgepackt oben auf einen USB-Stick kopieren\n(ab 0.5.2; aeltere Rechner: auspacken, Inhalt oben auf den Stick).\n' \
  "$NAME" >> "$NOTIZEN"
if gh release view "$TAG" --repo "$REPO" >/dev/null 2>&1; then
  gh release upload "$TAG" "$ZIP" "$ZIP.sha256" --repo "$REPO" --clobber \
    || { fehl "Hochladen scheiterte"; exit 1; }
else
  gh release create "$TAG" "$ZIP" "$ZIP.sha256" --repo "$REPO" --verify-tag \
     --title "Devarenu $VERSION" --notes-file "$NOTIZEN" \
    || { fehl "Release liess sich nicht anlegen"; exit 1; }
fi
gut "hochgeladen"
echo
echo "   https://github.com/$REPO/releases/latest/download/$NAME"
echo "   zeigt jetzt auf $TAG -- sofern $TAG das neueste Release ist."
