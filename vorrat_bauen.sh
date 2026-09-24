#!/usr/bin/env bash
# Legt den Reparaturvorrat an.
#
#   sudo bash vorrat_bauen.sh              alles
#   sudo bash vorrat_bauen.sh --ziel /pfad an eine andere Stelle (zum Pruefen)
#   bash vorrat_bauen.sh --pruefen         nur nachsehen, nichts schreiben
#   sudo bash vorrat_bauen.sh --nur-systempakete
#                                          nur die Systempakete ergaenzen
#   sudo bash vorrat_bauen.sh --nur-etikett
#                                          nur die Fassung nachziehen
#
# --nur-systempakete ist fuer den Fall, dass ein Vorrat schon daliegt
# und bloss dnsmasq fehlt. Es laedt ein paar Megabyte statt vierzehn
# Gigabyte -- wichtig, wenn die Leitung ein Handy-Hotspot ist.
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
NUR_SYSTEM=nein
NUR_ETIKETT=nein

blau() { printf '\n\033[1;34m== %s\033[0m\n' "$*"; }
gut()  { printf '   \033[32mok\033[0m    %s\n' "$*"; }
warn() { printf '   \033[33m!\033[0m     %s\n' "$*"; }
fehl() { printf '   \033[31mFEHLT\033[0m %s\n' "$*"; }
info() { printf '         %s\n' "$*"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --ziel)     ZIEL="${2:-}"; shift 2 ;;
    --pruefen)  NUR_PRUEFEN=ja; shift ;;
    --nur-systempakete) NUR_SYSTEM=ja; shift ;;
    --nur-etikett)      NUR_ETIKETT=ja; shift ;;
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
    # Bis 0.2.11 war hier Schluss: "Vorrat vorhanden" stand da, ohne
    # dass eine einzige Datei angefasst wurde. Ein Vorrat, von dem die
    # Haelfte verdorben ist, sah genauso aus wie ein guter -- und
    # auffallen wuerde es an dem Tag, an dem man ihn braucht.
    if [ -f "$ZIEL/pruefsummen.sha256" ]; then
      ANZ="$(wc -l < "$ZIEL/pruefsummen.sha256")"
      info "Rechne $ANZ Pruefsummen nach, das dauert einen Moment ..."
      SCHLECHT="$( cd "$ZIEL" && sha256sum -c pruefsummen.sha256 2>/dev/null \
                   | grep -v ': OK$' || true )"
      if [ -z "$SCHLECHT" ]; then
        gut "$ANZ Dateien unveraendert"
      else
        fehl "$(printf '%s\n' "$SCHLECHT" | wc -l) Dateien stimmen nicht:"
        printf '%s\n' "$SCHLECHT" | head -10 | sed 's/^/         /'
        info "Neu bauen geht nur mit Netz:  sudo bash vorrat_bauen.sh"
        exit 1
      fi
    else
      fehl "pruefsummen.sha256 fehlt. Der Vorrat ist unvollstaendig."
      exit 1
    fi
  else
    fehl "Unter $ZIEL liegt keiner."
  fi
  exit 0
fi

# --nur-etikett: nach einem Update steht im Vorrat noch die alte
# Fassung. Am Inhalt aendert das nichts -- Stimmen und Modelle sind
# dieselben -- aber die Nummer soll stimmen, sonst meldet pruefen.sh
# einen veralteten Vorrat, der gar keiner ist. Der Updater ruft das.
if [ "$NUR_ETIKETT" = ja ]; then
  if [ ! -f "$ZIEL/vorrat.json" ]; then
    fehl "Unter $ZIEL liegt kein Vorrat."
    exit 1
  fi
  "$PY" - "$ZIEL" "$VERSION" <<'PYCODE'
import json, sys
from datetime import datetime
from pathlib import Path
ziel, version = Path(sys.argv[1]), sys.argv[2]
datei = ziel / "vorrat.json"
d = json.loads(datei.read_text(encoding="utf-8"))
alt = d.get("fassung")
d["fassung"] = version
d["etikett_nachgezogen"] = datetime.now().isoformat(timespec="seconds")
# Ausdruecklich vermerkt: der INHALT stammt weiter vom Bau. Wer das
# verwechselt, haelt einen alten Vorrat fuer einen frischen.
d.setdefault("inhalt_von", alt)
datei.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n",
                 encoding="utf-8")
print("   ok    vorrat.json: %s -> %s (Inhalt weiter von %s)"
      % (alt, version, d["inhalt_von"]))
PYCODE
  ( cd "$ZIEL" && find . -type f ! -name pruefsummen.sha256 -print0 \
      | sort -z | xargs -0 sha256sum > pruefsummen.sha256 )
  gut "Pruefsummen nachgezogen"
  exit 0
fi

# --nur-systempakete: der Kurzweg. Geprueft wird VOR dem ersten
# Ladevorgang -- sonst haengen schon 175 MB Wheels an der Leitung, ehe
# auffaellt, dass es gar keinen Vorrat zu ergaenzen gibt. Genau das ist
# beim ersten Versuch passiert.
if [ "$NUR_SYSTEM" = ja ]; then
  if [ ! -f "$ZIEL/vorrat.json" ]; then
    fehl "Unter $ZIEL liegt kein Vorrat, der sich ergaenzen liesse."
    info "Einen ganzen bauen:  sudo bash vorrat_bauen.sh"
    exit 1
  fi
  gut "Vorhandener Vorrat wird nur ergaenzt"
  info "Stimmen, Modelle und Wheels bleiben, wie sie sind."
fi

# Ab hier wird geschrieben.
if [ ! -w "$(dirname "$ZIEL")" ] && [ "$(id -u)" != "0" ]; then
  fehl "Keine Schreibrechte auf $(dirname "$ZIEL")."
  info "Mit sudo starten:  sudo bash vorrat_bauen.sh"
  exit 1
fi

mkdir -p "$ZIEL"/{wheels,wheels-torch,voices,modelle,ollama,systempakete} \
  || exit 1

# ---------------------------------------------------------------- Pakete
if [ "$NUR_SYSTEM" != ja ]; then
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

fi   # Ende von --nur-systempakete uebersprungen

# ---------------------------------------------------------- Systempakete
blau "Systempakete"
# Bis 0.2.9 nahm dieser Vorrat nur Python-Pakete mit. Das genuegte,
# solange alles Noetige schon auf dem Rechner lag. Mit dem Netzumbau
# genuegt es nicht mehr: dnsmasq ist ein Systempaket, und vor Ort gibt
# es keine Leitung, ueber die es nachkommen koennte. Ein Rechner, auf
# dem der Umbau an einem fehlenden dnsmasq scheitert, hat kein WLAN --
# und niemanden, der ihm eines besorgen kann.
#
# apt legt die .deb-Dateien in sein Archivverzeichnis; mit
# -o Dir::Cache::archives zeigt es hierher. --reinstall, weil sonst
# nichts geholt wird, was schon installiert ist -- und genau das ist
# hier der Normalfall.
# Zwei Paketverwaltungen, weil es zwei Systeme gibt. Der
# Gemeinderechner lief bis zum 23.09.2026 auf Ubuntu und laeuft seither
# auf CachyOS -- und in der Zwischenzeit stand im Vorrat "Kein apt-get,
# Systempakete werden uebersprungen". Damit fehlte dnsmasq, also genau
# das Paket, ohne das sich das Saalnetz vor Ort nicht einrichten laesst.
SYSTEMPAKETE_APT="dnsmasq dnsmasq-base"
SYSTEMPAKETE_PACMAN="dnsmasq"
if command -v pacman >/dev/null && ! command -v apt-get >/dev/null; then
  # pacman -Sw laedt in einen Zwischenspeicher, ohne zu installieren.
  # --cachedir zeigt in den Vorrat; ohne das landet es unter
  # /var/cache/pacman/pkg und waere beim naechsten Aufraeumen weg.
  rm -rf "$ZIEL/systempakete"
  mkdir -p "$ZIEL/systempakete"
  # Ohne PIPESTATUS gilt der Rueckgabewert von sed, nicht der von
  # pacman -- und dann meldet das Skript "Erfolg, aber keine Datei da",
  # wo in Wahrheit "Sie benoetigen Root-Rechte" stand.
  pacman -Sw --noconfirm --cachedir "$ZIEL/systempakete" \
    $SYSTEMPAKETE_PACMAN 2>&1 | sed 's/^/         /'
  if [ "${PIPESTATUS[0]}" = "0" ]; then
    ANZ="$(find "$ZIEL/systempakete" -maxdepth 1 -name '*.pkg.tar.*' \
           ! -name '*.sig' | wc -l)"
    if [ "$ANZ" -gt 0 ]; then
      gut "$ANZ Pakete, $(du -sh "$ZIEL/systempakete" | cut -f1)"
      # Die Signaturen kommen mit und bleiben liegen: pacman -U prueft
      # sie, und ohne sie muesste man vor Ort --nosignature nehmen.
      info "Signaturen liegen daneben, pacman -U prueft sie."
    else
      fehl "pacman meldete Erfolg, aber es liegt kein Paket da."
      exit 1
    fi
  else
    fehl "pacman konnte die Systempakete nicht holen."
    info "Erst die Paketlisten auffrischen:  sudo pacman -Sy"
    exit 1
  fi
elif ! command -v apt-get >/dev/null; then
  warn "Weder pacman noch apt-get -- Systempakete werden uebersprungen."
  info "Der Vorrat ist auf diesem Rechner unvollstaendig."
else
  SYSTEMPAKETE="$SYSTEMPAKETE_APT"
  # apt braucht partial/, sonst bricht es mit einer Meldung ab, die
  # nach einem Rechtefehler aussieht.
  rm -rf "$ZIEL/systempakete"
  mkdir -p "$ZIEL/systempakete/partial"
  if apt-get install --reinstall --download-only -y \
       -o Dir::Cache::archives="$ZIEL/systempakete" \
       $SYSTEMPAKETE 2>&1 | sed 's/^/         /'; then
    ANZ="$(find "$ZIEL/systempakete" -maxdepth 1 -name '*.deb' | wc -l)"
    if [ "$ANZ" -gt 0 ]; then
      gut "$ANZ .deb, $(du -sh "$ZIEL/systempakete" | cut -f1)"
    else
      fehl "apt meldete Erfolg, aber es liegt keine .deb-Datei da."
      info "Ohne dnsmasq scheitert der Netzumbau vor Ort. Nachsehen:"
      info "  apt-get install --reinstall --download-only -o \\"
      info "    Dir::Cache::archives=$ZIEL/systempakete $SYSTEMPAKETE"
      exit 1
    fi
  else
    fehl "apt konnte die Systempakete nicht holen."
    info "Ohne dnsmasq laesst sich das Saalnetz vor Ort nicht"
    info "einrichten. Erst die Paketquellen pruefen:"
    info "  sudo apt-get update"
    exit 1
  fi
fi

if [ "$NUR_SYSTEM" = ja ]; then
  # Pruefsummen und Etikett muessen mit, sonst meldet --pruefen
  # hinterher die neuen Dateien als unbekannt und den Vorrat als
  # verdorben.
  blau "Pruefsummen"
  ( cd "$ZIEL" && find . -type f ! -name pruefsummen.sha256 -print0 \
      | sort -z | xargs -0 sha256sum > pruefsummen.sha256 )
  gut "$(wc -l < "$ZIEL/pruefsummen.sha256") Dateien"

  blau "Beschriftung"
  "$PY" - "$ZIEL" "$VERSION" <<'PYCODE'
import json, sys
from datetime import datetime
from pathlib import Path
ziel, version = Path(sys.argv[1]), sys.argv[2]
datei = ziel / "vorrat.json"
d = json.loads(datei.read_text(encoding="utf-8"))
# Die Fassung NICHT hochsetzen: geladen wurden nur Systempakete, die
# Wheels gehoeren weiter zur alten. Wer das verwechselt, haelt einen
# halben Vorrat fuer einen ganzen.
d["systempakete_ergaenzt"] = datetime.now().isoformat(timespec="seconds")
d["systempakete_fassung"] = version
datei.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n",
                 encoding="utf-8")
print("   ok    vorrat.json ergaenzt (Fassung bleibt %s)"
      % d.get("fassung", "?"))
PYCODE

  blau "Fertig"
  info "Nur die Systempakete wurden ergaenzt. Der uebrige Vorrat"
  info "gehoert weiter zu Fassung $("$PY" -c "
import json; print(json.load(open('$ZIEL/vorrat.json')).get('fassung','?'))")."
  info "Nachsehen:  bash vorrat_bauen.sh --pruefen"
  exit 0
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
  warn "Erst bash einrichten.sh laufen lassen, dann diesen Vorrat neu bauen."
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
    warn "Erst bash einrichten.sh laufen lassen, dann diesen Vorrat neu bauen."
  fi
else
  fehl "voices/ ist leer. Erst bash einrichten.sh laufen lassen."
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
  fehl "models/ ist leer. Erst bash einrichten.sh laufen lassen."
  exit 1
fi

# -------------------------------------------------------- Ollama-Modell
blau "Uebersetzungsmodell"
# Wo Ollama seine Modelle ablegt: erst die Umgebung, dann die Unit, dann
# die ueblichen Orte. Geraten wird nicht -- wer hier danebengreift,
# sichert nichts und merkt es erst vor Ort.
# Wo Ollama seine Modelle wirklich hinlegt -- gefragt, nicht geraten.
# Ermittelt wird das an EINER Stelle, in systemcheck.ollama_ablage():
# vorrat_bauen.sh, wiederherstellen.sh und der Systemcheck brauchen
# dieselbe Antwort, und zwei Ermittlungen laufen frueher oder spaeter
# auseinander.
#
# Dass Raten nicht genuegt: auf einem Entwicklungsrechner zeigt
# OLLAMA_MODELS auf ein eigenes Laufwerk, auf dem Gemeinderechner liegt
# es unter /usr/share/ollama (Installierskript von ollama.com), und das
# Arch-Paket nimmt /var/lib/ollama. Drei Rechner, drei Orte.
OLLAMA_ORT="$("$PY" -c "
import sys; sys.path.insert(0, '$ORDNER')
import systemcheck; print(systemcheck.ollama_ablage() or '')" 2>/dev/null)"

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

  systempakete/      dnsmasq als .deb, für den Netzumbau vor Ort
  wheels/            Python-Pakete für Python $PY_FASSUNG
  wheels-torch/      Torch $TORCH_FASSUNG und die NVIDIA-Bibliotheken
  voices/            die Piper-Stimmen
  modelle/whisper/   die Spracherkennung
  ollama/            das Übersetzungsmodell $MODELL
  vorrat.json        wozu dieser Vorrat gehört
  pruefsummen.sha256 damit man merkt, wenn etwas verdorben ist

Wiederherstellen, ohne Netz, im Projektordner:

    bash wiederherstellen.sh --pruefen     nur nachsehen
    bash wiederherstellen.sh --stimmen
    bash wiederherstellen.sh --pakete
    bash wiederherstellen.sh --modell
    bash wiederherstellen.sh --systempakete
    bash wiederherstellen.sh --alles

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
info "Nachsehen mit:  bash vorrat_bauen.sh --pruefen"
