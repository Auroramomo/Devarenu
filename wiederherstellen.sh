#!/usr/bin/env bash
# Stellt aus dem Reparaturvorrat wieder her. Ohne Netz.
#
#   ./wiederherstellen.sh --pruefen     nur nachsehen, nichts anfassen
#   ./wiederherstellen.sh --stimmen     Piper-Stimmen zurueckholen
#   ./wiederherstellen.sh --pakete      Python-Pakete und Torch neu
#   ./wiederherstellen.sh --modell      Uebersetzungsmodell zurueckspielen
#   ./wiederherstellen.sh --alles       alles drei
#
#   --vorrat /pfad                      anderer Ort als /opt/devarenu-vorrat
#
# Gedacht fuer den Sonntagmorgen in der Gemeinde, an dem etwas fehlt und
# niemand ein Netz hat. Jede Meldung sagt, was zu tun ist.
#
# Was hier NICHT angefasst wird: zustand.json. Die Einstellungen der
# Gemeinde gehoeren ihr, nicht dem Vorrat -- dieselbe Regel wie beim
# Update per Stick.

set -u
ORDNER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ORDNER"

VORRAT=/opt/devarenu-vorrat
TUN=""

blau() { printf '\n\033[1;34m== %s\033[0m\n' "$*"; }
gut()  { printf '   \033[32mok\033[0m    %s\n' "$*"; }
warn() { printf '   \033[33m!\033[0m     %s\n' "$*"; }
fehl() { printf '   \033[31mFEHLT\033[0m %s\n' "$*"; }
info() { printf '         %s\n' "$*"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --vorrat)   VORRAT="${2:-}"; shift 2 ;;
    --pruefen)  TUN="$TUN pruefen"; shift ;;
    --stimmen)  TUN="$TUN stimmen"; shift ;;
    --pakete)   TUN="$TUN pakete";  shift ;;
    --modell)   TUN="$TUN modell";  shift ;;
    --alles)    TUN="$TUN stimmen pakete modell"; shift ;;
    -h|--hilfe) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)          fehl "Unbekannt: $1"; exit 1 ;;
  esac
done
[ -z "$TUN" ] && { sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0; }

hat() { case " $TUN " in *" $1 "*) return 0 ;; *) return 1 ;; esac; }

# ------------------------------------------------------------ Vorhanden?
blau "Vorrat"
if [ ! -f "$VORRAT/vorrat.json" ]; then
  fehl "Unter $VORRAT liegt kein Vorrat."
  info "Dieser Rechner wurde ohne einen aufgesetzt, oder er ist geloescht."
  info "Neu bauen geht nur mit Netz:  sudo ./vorrat_bauen.sh"
  exit 1
fi

PY="$ORDNER/.venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"
[ -x "$PY" ] || { fehl "Kein Python gefunden."; exit 1; }

V_FASSUNG="$("$PY" -c "import json;print(json.load(open('$VORRAT/vorrat.json')).get('fassung','?'))")"
V_PYTHON="$("$PY" -c "import json;print(json.load(open('$VORRAT/vorrat.json')).get('python','?'))")"
V_MODELL="$("$PY" -c "import json;print(json.load(open('$VORRAT/vorrat.json')).get('modell','?'))")"
V_TORCH="$("$PY" -c "import json;print(json.load(open('$VORRAT/vorrat.json')).get('torch') or '')")"
V_GEBAUT="$("$PY" -c "import json;print(json.load(open('$VORRAT/vorrat.json')).get('gebaut','?'))")"
HIER_FASSUNG="$(tr -d '\r' < VERSION | head -1 | tr -d ' ')"
HIER_PYTHON="$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"

gut "Vorrat gefunden, gebaut $V_GEBAUT"
info "gehoert zu Fassung $V_FASSUNG, hier laeuft $HIER_FASSUNG"
info "Pakete fuer Python $V_PYTHON, hier laeuft $HIER_PYTHON"
info "Modell $V_MODELL"
[ -n "$V_TORCH" ] && info "Torch $V_TORCH"

if [ "$V_FASSUNG" != "$HIER_FASSUNG" ]; then
  warn "Der Vorrat ist nicht fuer die Fassung, die hier laeuft."
  warn "Stimmen und Modell passen trotzdem -- die haengen nicht an der"
  warn "Fassung. Bei den Paketen kann requirements.txt sich geaendert"
  warn "haben. Beim naechsten Besuch mit Netz neu bauen."
fi

# ------------------------------------------------------------ Pruefsummen
blau "Pruefsummen"
if [ ! -f "$VORRAT/pruefsummen.sha256" ]; then
  fehl "pruefsummen.sha256 fehlt. Der Vorrat ist unvollstaendig."
  exit 1
fi
# Vor jedem Einspielen, nicht danach: was verdorben ist, soll gar nicht
# erst auf die Platte kommen.
if ( cd "$VORRAT" && sha256sum --quiet -c pruefsummen.sha256 >/dev/null 2>&1 ); then
  gut "$(wc -l < "$VORRAT/pruefsummen.sha256") Dateien unveraendert"
else
  fehl "Mindestens eine Datei stimmt nicht mit ihrer Pruefsumme ueberein."
  ( cd "$VORRAT" && sha256sum -c pruefsummen.sha256 2>/dev/null \
      | grep -v ': OK$' | head -10 | sed 's/^/         /' )
  info "Es wird nichts eingespielt. Der Vorrat muss neu gebaut werden."
  exit 1
fi

if hat pruefen; then
  blau "Nur nachgesehen"
  info "Es wurde nichts veraendert."
  info "Einspielen mit --stimmen, --pakete, --modell oder --alles."
  exit 0
fi

# --------------------------------------------------------------- Stimmen
if hat stimmen; then
  blau "Stimmen"
  if [ ! -d "$VORRAT/voices" ]; then
    fehl "Im Vorrat liegen keine Stimmen."
  else
    mkdir -p voices
    # Kein rm davor: was da ist und stimmt, bleibt. Wer eine einzelne
    # kaputte Stimme hat, soll nicht alle 21 neu kopieren muessen.
    NEU=0
    for f in "$VORRAT"/voices/*; do
      [ -e "$f" ] || continue
      z="voices/$(basename "$f")"
      if [ ! -f "$z" ] || ! cmp -s "$f" "$z"; then
        cp -a "$f" "$z" && NEU=$((NEU+1))
      fi
    done
    gut "$NEU Dateien zurueckgeholt, $(find voices -name '*.onnx' 2>/dev/null | wc -l) Stimmen vorhanden"
    [ "$NEU" -gt 0 ] && info "Der Dienst muss neu starten, damit er sie sieht:"
    [ "$NEU" -gt 0 ] && info "  sudo systemctl restart devarenu"
  fi
fi

# ---------------------------------------------------------------- Pakete
if hat pakete; then
  blau "Pakete"
  # Die Sperre. Wheels sind an die Python-Fassung gebunden; eine Fassung
  # daneben und pip installiert entweder nichts oder das Falsche, und
  # gesucht wird danach am Server.
  if [ "$V_PYTHON" != "$HIER_PYTHON" ]; then
    fehl "Der Vorrat hat Pakete fuer Python $V_PYTHON,"
    fehl "hier laeuft aber Python $HIER_PYTHON."
    info "Diese Wheels passen nicht. Es wird nichts installiert."
    info "Entweder die venv mit Python $V_PYTHON neu anlegen, oder den"
    info "Vorrat beim naechsten Besuch mit Netz neu bauen."
    exit 1
  fi
  if [ ! -d "$VORRAT/wheels" ]; then
    fehl "Im Vorrat liegen keine Pakete."
  else
    ANZAHL="$(find "$VORRAT/wheels" -name '*.whl' | wc -l)"
    info "$ANZAHL Wheels fuer Python $V_PYTHON"
    BEDINGUNG=""
    [ -f constraints.txt ] && BEDINGUNG="-c constraints.txt"
    # --no-index: kein Griff ins Netz, auch nicht versehentlich. Hier
    # gibt es keins, und ein Versuch endete in einem langen Timeout
    # statt in einer klaren Meldung.
    if "$PY" -m pip install --no-index --find-links "$VORRAT/wheels" \
         -r requirements.txt $BEDINGUNG 2>&1 | sed 's/^/         /'; then
      gut "Pakete installiert"
    else
      fehl "pip ist gescheitert. Die Ausgabe oben sagt, woran."
      exit 1
    fi

    # Torch getrennt, weil es getrennt gesichert wurde: eigener Index,
    # eigene Fassung, und es steht nicht in requirements.txt.
    if [ -d "$VORRAT/wheels-torch" ] \
       && [ -n "$(ls -A "$VORRAT/wheels-torch" 2>/dev/null)" ]; then
      info "$(find "$VORRAT/wheels-torch" -name '*.whl' | wc -l) Wheels fuer Torch $V_TORCH"
      if "$PY" -m pip install --no-index \
           --find-links "$VORRAT/wheels-torch" \
           "torch==$V_TORCH" 2>&1 | sed 's/^/         /'; then
        gut "Torch $V_TORCH installiert"
      else
        fehl "Torch liess sich nicht installieren."
        exit 1
      fi
    else
      warn "Im Vorrat liegt kein Torch. Ohne es erkennt Whisper nichts."
      warn "Nachholen geht nur mit Netz."
    fi
    info "Danach einmal:  ./pruefen.sh"
  fi
fi

# ---------------------------------------------------------------- Modell
if hat modell; then
  blau "Uebersetzungsmodell"
  if [ ! -f "$VORRAT/ollama/modell.json" ]; then
    fehl "Im Vorrat liegt kein Modell."
  elif ! command -v ollama >/dev/null; then
    fehl "ollama ist nicht installiert. Ohne das Programm nuetzt das"
    fehl "Modell nichts."
  else
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
    if [ -z "$OLLAMA_ORT" ]; then
      fehl "Ollamas Modellablage nicht gefunden."
      info "Mit OLLAMA_MODELS=/pfad davor nochmal starten."
      exit 1
    fi
    info "Ablage $OLLAMA_ORT"
    SUDO=""
    [ -w "$OLLAMA_ORT" ] || SUDO="sudo"
    [ -n "$SUDO" ] && info "Schreiben braucht sudo."
    if "$PY" - "$VORRAT/ollama" "$OLLAMA_ORT" "$SUDO" <<'PYCODE'
import json, subprocess, sys
from pathlib import Path
quelle, ziel, sudo = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
d = json.loads((quelle / "modell.json").read_text())
name, tag = d["name"], d["tag"]

def lauf(*teile):
    befehl = ([sudo] if sudo else []) + list(teile)
    return subprocess.run(befehl).returncode == 0

zielmanifest = ziel / "manifests" / "registry.ollama.ai" / "library" / name
if not lauf("mkdir", "-p", str(zielmanifest), str(ziel / "blobs")):
    sys.exit("mkdir fehlgeschlagen")
for blob in sorted((quelle / "blobs").iterdir()):
    if not lauf("cp", "-n", str(blob), str(ziel / "blobs" / blob.name)):
        sys.exit(f"Blob {blob.name} liess sich nicht kopieren")
if not lauf("cp", str(quelle / "manifests" / f"{name}--{tag}"),
            str(zielmanifest / tag)):
    sys.exit("Manifest liess sich nicht kopieren")
print(f"{len(list((quelle/'blobs').iterdir()))} Blobs und das Manifest fuer {name}:{tag}")
PYCODE
    then
      gut "Modell zurueckgespielt"
      info "Nachsehen mit:  ollama list"
      info "Ollama muss danach neu starten:  sudo systemctl restart ollama"
    else
      fehl "Das Modell liess sich nicht zurueckspielen."
      exit 1
    fi
  fi
fi

blau "Fertig"
info "zustand.json wurde nicht angefasst."
