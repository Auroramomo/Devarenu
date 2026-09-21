#!/usr/bin/env bash
# Legt den Reparaturvorrat an.
#
#   sudo ./vorrat_bauen.sh              alles
#   sudo ./vorrat_bauen.sh --ziel /pfad an eine andere Stelle (zum Pruefen)
#   ./vorrat_bauen.sh --pruefen         nur nachsehen, nichts schreiben
#
# Warum das noetig ist: installiert wird beim Systemhaus mit Leitung,
# danach geht der Rechner in die Gemeinde, und dort gibt es kein Netz.
# Was hier nicht auf die Platte kommt, ist vor Ort nicht wiederzubekommen
# -- weder ein Paket noch eine Stimme noch das Uebersetzungsmodell.
#
# Rund 13 GB von einem Terabyte. Die Datenmenge ist egal, die Leitung
# steht beim Bauen. Was zaehlt, ist der Tag danach.
#
# Der Vorrat liegt bewusst NICHT im Projektordner: er muss ein git pull,
# ein Stick-Update und auch ein Neu-Klonen ueberleben. Unter dem
# Projektordner haenge er an .gitignore und waere bei einem
# "git clean -x" weg -- an genau dem Tag, an dem man ihn braucht.

set -u
ORDNER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ORDNER"

ZIEL=/opt/devarenu-vorrat
NUR_PRUEFEN=nein

blau() { printf '\n\033[1;34m== %s\033[0m\n' "$*"; }
gut()  { printf '   \033[32mok\033[0m    %s\n' "$*"; }
warn() { printf '   \033[33m!\033[0m     %s\n' "$*"; }
fehl() { printf '   \033[31mFEHLT\033[0m %s\n' "$*"; }
info() { printf '         %s\n' "$*"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --ziel)     ZIEL="${2:-}"; shift 2 ;;
    --pruefen)  NUR_PRUEFEN=ja; shift ;;
    -h|--hilfe) sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)          fehl "Unbekannt: $1"; exit 1 ;;
  esac
done

PY="$ORDNER/.venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"
[ -x "$PY" ] || { fehl "Kein Python gefunden."; exit 1; }

# Die Fassung des Interpreters, unter dem der Server spaeter LAEUFT.
# Nicht gesetzt, sondern abgelesen: beim Systemhaus ist es derselbe
# Rechner, und ein geratener Wert waere genau die Falle, die
# wiederherstellen.sh spaeter abfangen muss.
PY_FASSUNG="$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
VERSION="$(tr -d '\r' < VERSION | head -1 | tr -d ' ')"
MODELL="$("$PY" -c 'import config; print(config.LIVE_MODELL)' 2>/dev/null)"

blau "Reparaturvorrat"
info "Ziel      $ZIEL"
info "Fassung   $VERSION"
info "Python    $PY_FASSUNG  ($PY)"
info "Modell    ${MODELL:-unbekannt}"

if [ "$NUR_PRUEFEN" = "ja" ]; then
  if [ -f "$ZIEL/vorrat.json" ]; then
    gut "Vorrat vorhanden"
    "$PY" -c "
import json
d = json.load(open('$ZIEL/vorrat.json'))
for k in ('fassung', 'python', 'modell', 'gebaut'):
    print('         %-9s %s' % (k, d.get(k, '?')))
"
  else
    fehl "Unter $ZIEL liegt keiner."
  fi
  exit 0
fi

# Ab hier wird geschrieben.
if [ ! -w "$(dirname "$ZIEL")" ] && [ "$(id -u)" != "0" ]; then
  fehl "Keine Schreibrechte auf $(dirname "$ZIEL")."
  info "Mit sudo starten:  sudo ./vorrat_bauen.sh"
  exit 1
fi

mkdir -p "$ZIEL"/{wheels,wheels-torch,voices,modelle,ollama} || exit 1

# ---------------------------------------------------------------- Pakete
blau "Pakete"
# Ohne --platform und ohne --python-version, anders als in
# stick_bauen.sh: der Stick zielt auf einen FREMDEN Rechner, dieser
# Vorrat auf genau diesen hier. Was pip fuer den laufenden Interpreter
# holt, passt deshalb per Bau.
#
# --only-binary=:all: trotzdem: eine Quelldistribution muesste vor Ort
# uebersetzt werden, und dafuer fehlt dort alles.
BEDINGUNG=""
[ -f constraints.txt ] && BEDINGUNG="-c constraints.txt"
rm -rf "$ZIEL/wheels"; mkdir -p "$ZIEL/wheels"
if "$PY" -m pip download -r requirements.txt $BEDINGUNG -d "$ZIEL/wheels" \
     --only-binary=:all: 2>&1 | sed 's/^/         /'; then
  gut "$(find "$ZIEL/wheels" -name '*.whl' | wc -l) Pakete, $(du -sh "$ZIEL/wheels" | cut -f1)"
else
  fehl "pip konnte nicht alle Pakete holen. Vorrat unvollstaendig."
  exit 1
fi

# ----------------------------------------------------------------- Torch
blau "Torch"
# Torch steht absichtlich nicht in requirements.txt: es kommt aus einem
# eigenen Index und in einer Fassung, die zur CUDA-Version passt. Genau
# deshalb faellt es hier leicht durchs Raster -- und waere die groesste
# Luecke im Vorrat, denn ohne Torch und die NVIDIA-Bibliotheken laesst
# sich die venv vor Ort nicht neu aufbauen.
#
# Die Adresse steht in einrichten.sh. Weicht sie ab, ist eine der beiden
# Dateien geaendert worden, ohne die andere nachzuziehen.
TORCH_INDEX=https://download.pytorch.org/whl/cu128
AUS_EINRICHTEN="$(sed -n 's#.*\(https://download\.pytorch\.org/whl/[a-z0-9]*\).*#\1#p' \
                  einrichten.sh | head -1)"
if [ -n "$AUS_EINRICHTEN" ] && [ "$AUS_EINRICHTEN" != "$TORCH_INDEX" ]; then
  warn "einrichten.sh nimmt $AUS_EINRICHTEN,"
  warn "hier steht $TORCH_INDEX. Ich nehme den aus einrichten.sh."
  TORCH_INDEX="$AUS_EINRICHTEN"
fi
info "Index     $TORCH_INDEX"

TORCH_FASSUNG="$("$PY" -c 'import torch; print(torch.__version__)' 2>/dev/null)"
if [ -z "$TORCH_FASSUNG" ]; then
  warn "torch ist hier nicht installiert. Es wird nichts gesichert."
  warn "Erst ./einrichten.sh laufen lassen, dann diesen Vorrat neu bauen."
else
  info "Fassung   $TORCH_FASSUNG"
  rm -rf "$ZIEL/wheels-torch"; mkdir -p "$ZIEL/wheels-torch"
  # Genau die Fassung, die hier laeuft -- nicht die neueste. Der Vorrat
  # soll diesen Rechner wiederherstellen, nicht einen anderen bauen.
  if "$PY" -m pip download "torch==${TORCH_FASSUNG}" \
       --index-url "$TORCH_INDEX" -d "$ZIEL/wheels-torch" \
       --only-binary=:all: 2>&1 | sed 's/^/         /'; then
    gut "$(find "$ZIEL/wheels-torch" -name '*.whl' | wc -l) Pakete, $(du -sh "$ZIEL/wheels-torch" | cut -f1)"
  else
    fehl "torch liess sich nicht holen. Der Vorrat waere unvollstaendig:"
    fehl "ohne ihn ist die venv vor Ort nicht neu aufzubauen."
    exit 1
  fi
fi

# --------------------------------------------------------------- Stimmen
blau "Stimmen"
if [ -d voices ] && [ -n "$(ls -A voices 2>/dev/null)" ]; then
  rm -rf "$ZIEL/voices"; mkdir -p "$ZIEL/voices"
  cp -a voices/. "$ZIEL/voices/"
  gut "$(find "$ZIEL/voices" -name '*.onnx' | wc -l) Stimmen, $(du -sh "$ZIEL/voices" | cut -f1)"
  ERWARTET="$("$PY" -c 'import config; print(len([p for p in config.STIMMEN.values() if p]))')"
  DA="$(find "$ZIEL/voices" -name '*.onnx' | wc -l)"
  if [ "$DA" -lt "$ERWARTET" ]; then
    warn "config.py nennt $ERWARTET Stimmen, gesichert sind $DA."
    warn "Erst ./einrichten.sh laufen lassen, dann diesen Vorrat neu bauen."
  fi
else
  fehl "voices/ ist leer. Erst ./einrichten.sh laufen lassen."
  exit 1
fi

# -------------------------------------------------------- Whisper-Modell
blau "Spracherkennung"
# Eine eigene Kopie, obwohl models/ danebenliegt: models/ ist die
# Arbeitskopie. Ein Vorrat, der auf die Arbeitskopie zeigt, ist keiner.
if [ -d models ] && [ -n "$(ls -A models 2>/dev/null)" ]; then
  rm -rf "$ZIEL/modelle/whisper"; mkdir -p "$ZIEL/modelle/whisper"
  cp -a models/. "$ZIEL/modelle/whisper/"
  gut "Whisper gesichert, $(du -sh "$ZIEL/modelle/whisper" | cut -f1)"
else
  fehl "models/ ist leer. Erst ./einrichten.sh laufen lassen."
  exit 1
fi

# -------------------------------------------------------- Ollama-Modell
blau "Uebersetzungsmodell"
# Wo Ollama seine Modelle ablegt: erst die Umgebung, dann die Unit, dann
# die ueblichen Orte. Geraten wird nicht -- wer hier danebengreift,
# sichert nichts und merkt es erst vor Ort.
OLLAMA_ORT="${OLLAMA_MODELS:-}"
if [ -z "$OLLAMA_ORT" ]; then
  OLLAMA_ORT="$(systemctl cat ollama 2>/dev/null \
                | sed -n 's/.*OLLAMA_MODELS=\([^"]*\).*/\1/p' | head -1)"
fi
for k in /usr/share/ollama/.ollama/models "$HOME/.ollama/models" \
         /var/lib/ollama/.ollama/models; do
  [ -n "$OLLAMA_ORT" ] && break
  [ -d "$k/blobs" ] && OLLAMA_ORT="$k"
done

if [ -z "$OLLAMA_ORT" ] || [ ! -d "$OLLAMA_ORT/blobs" ]; then
  fehl "Ollamas Modellablage nicht gefunden."
  info "Mit OLLAMA_MODELS=/pfad davor nochmal starten."
  exit 1
fi
info "Ablage    $OLLAMA_ORT"

# Nur die Blobs, die das Manifest dieses einen Modells nennt. Ein
# cp -r der ganzen Ablage braechte auf einem Rechner mit mehreren
# Modellen dreissig Gigabyte Fremdmodelle mit.
rm -rf "$ZIEL/ollama"; mkdir -p "$ZIEL/ollama"
if "$PY" - "$OLLAMA_ORT" "$MODELL" "$ZIEL/ollama" <<'PYCODE'
import json, shutil, sys
from pathlib import Path
ablage, modell, ziel = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
name, _, tag = modell.partition(":")
tag = tag or "latest"
manifest = (ablage / "manifests" / "registry.ollama.ai" / "library"
            / name / tag)
if not manifest.exists():
    sys.exit(f"Manifest fehlt: {manifest}")
daten = json.loads(manifest.read_text())
teile = [daten["config"]] + list(daten.get("layers", []))
(ziel / "manifests").mkdir(parents=True, exist_ok=True)
(ziel / "blobs").mkdir(parents=True, exist_ok=True)
shutil.copy2(manifest, ziel / "manifests" / f"{name}--{tag}")
summe = 0
for t in teile:
    blob = ablage / "blobs" / t["digest"].replace(":", "-")
    if not blob.exists():
        sys.exit(f"Blob fehlt: {blob}")
    shutil.copy2(blob, ziel / "blobs" / blob.name)
    summe += blob.stat().st_size
(ziel / "modell.json").write_text(json.dumps(
    {"modell": modell, "name": name, "tag": tag,
     "blobs": [t["digest"] for t in teile]}, indent=2) + "\n")
print(f"{len(teile)} Blobs, {summe/1e9:.1f} GB")
PYCODE
then
  gut "Modell $MODELL gesichert"
else
  fehl "Modell liess sich nicht sichern."
  exit 1
fi

# ------------------------------------------------------------ Beschriftung
blau "Beschriftung"
"$PY" - "$ZIEL" "$VERSION" "$PY_FASSUNG" "$MODELL" \
      "${TORCH_FASSUNG:-}" "${TORCH_INDEX:-}" <<'PYCODE'
import json, sys, subprocess
from datetime import datetime
from pathlib import Path
(ziel, version, pyfassung, modell, torch_fassung, torch_index) = (
    Path(sys.argv[1]), *sys.argv[2:7])
groesse = subprocess.run(["du", "-sb", str(ziel)], capture_output=True,
                         text=True).stdout.split()[0]
(ziel / "vorrat.json").write_text(json.dumps({
    "fassung": version,
    "python": pyfassung,
    "modell": modell,
    "torch": torch_fassung,
    "torch_index": torch_index,
    "gebaut": datetime.now().isoformat(timespec="seconds"),
    "bytes": int(groesse),
}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
PYCODE
gut "vorrat.json"

cat > "$ZIEL/LIESMICH.txt" <<ENDE
Reparaturvorrat für Devarenu $VERSION
=====================================

Dieser Ordner ist die Kopie von allem, was dieser Rechner aus dem
Internet geladen hat. Er liegt hier, weil in der Gemeinde kein Netz ist:
ohne ihn lässt sich vor Ort weder ein Paket noch eine Stimme noch das
Übersetzungsmodell wiederherstellen.

Nichts hiervon wird im Betrieb gelesen. Der Vorrat liegt herum, bis
etwas kaputt ist.

  wheels/            Python-Pakete für Python $PY_FASSUNG
  wheels-torch/      Torch $TORCH_FASSUNG und die NVIDIA-Bibliotheken
  voices/            die Piper-Stimmen
  modelle/whisper/   die Spracherkennung
  ollama/            das Übersetzungsmodell $MODELL
  vorrat.json        wozu dieser Vorrat gehört
  pruefsummen.sha256 damit man merkt, wenn etwas verdorben ist

Wiederherstellen, ohne Netz, im Projektordner:

    ./wiederherstellen.sh --pruefen     nur nachsehen
    ./wiederherstellen.sh --stimmen
    ./wiederherstellen.sh --pakete
    ./wiederherstellen.sh --modell
    ./wiederherstellen.sh --alles

Die Wheels passen NUR zu Python $PY_FASSUNG. wiederherstellen.sh bricht
ab, wenn vor Ort eine andere Fassung läuft -- sonst installiert man
Pakete für den falschen Interpreter und sucht den Fehler danach
stundenlang an der falschen Stelle.

Der Vorrat gehört zur Fassung $VERSION. Ändert sich requirements.txt
durch ein Update, passen die Wheels nicht mehr. Dann gilt: beim nächsten
Besuch der Technik neu bauen. pruefen.sh meldet es.
ENDE
gut "LIESMICH.txt"

# ------------------------------------------------------------ Pruefsummen
blau "Pruefsummen"
# Zuletzt, damit sie alles erfassen, was vorher entstanden ist.
( cd "$ZIEL" && find . -type f ! -name pruefsummen.sha256 -print0 \
    | sort -z | xargs -0 sha256sum > pruefsummen.sha256 )
gut "$(wc -l < "$ZIEL/pruefsummen.sha256") Dateien"

if [ "$(id -u)" = "0" ]; then
  # Lesbar fuer alle, schreibbar nur fuer root: der Dienst laeuft unter
  # einem anderen Benutzer und soll den Vorrat nicht beschaedigen
  # koennen.
  chown -R root:root "$ZIEL"
  find "$ZIEL" -type d -exec chmod 755 {} +
  find "$ZIEL" -type f -exec chmod 644 {} +
  gut "root:root, Ordner 755, Dateien 644"
fi

blau "Fertig"
info "$ZIEL  --  $(du -sh "$ZIEL" | cut -f1)"
info "Nachsehen mit:  ./vorrat_bauen.sh --pruefen"
