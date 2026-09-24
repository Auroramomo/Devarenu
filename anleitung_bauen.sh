#!/usr/bin/env bash
# Baut die Bedienungsanleitung als PDF. NUR auf dem Arbeitsrechner.
#
#   bash anleitung_bauen.sh
#
# Das Ergebnis wird eingecheckt: auf dem Gemeinderechner soll kein
# zusaetzliches Paket stehen, nur um eine Anleitung zu drucken.
#
# Gebaut wird in einem EIGENEN venv (.bau-venv) mit einer eigenen
# Paketliste (requirements-bau.txt). Nichts davon gehoert in
# requirements.txt -- der Gemeinderechner braucht es nie.

set -eu
ORDNER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ORDNER"

BAU=.bau-venv

if [ ! -x "$BAU/bin/python" ]; then
  echo "== Bau-venv anlegen"
  python3 -m venv "$BAU"
  "$BAU/bin/pip" install --quiet --upgrade pip
  "$BAU/bin/pip" install --quiet -r requirements-bau.txt
fi

echo "== Anleitung bauen"
"$BAU/bin/python" anleitung/bauen.py

echo
echo "Fertig. Die PDF-Dateien gehoeren in den Commit:"
git status --short anleitung/*.pdf 2>/dev/null || true
