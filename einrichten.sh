#!/usr/bin/env bash
# Devarenu einrichten, Linux.
#
# Prueft der Reihe nach, was da ist, und ergaenzt nur das Fehlende. Laesst
# sich also gefahrlos mehrfach starten, etwa wenn ein Schritt schiefging.
#
#   chmod +x einrichten.sh
#   ./einrichten.sh

set -u
ORDNER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ORDNER"

blau()  { printf '\n\033[1;34m== %s\033[0m\n' "$*"; }
gut()   { printf '   \033[32mok\033[0m   %s\n' "$*"; }
fehlt() { printf '   \033[33mfehlt\033[0m %s\n' "$*"; }
warn()  { printf '   \033[31m!\033[0m    %s\n' "$*"; }

# ---------------------------------------------------------------- System
PY_SYS="$(command -v python3 || echo python)"

blau "System"
. /etc/os-release 2>/dev/null
echo "   ${PRETTY_NAME:-unbekannt}"

if command -v nvidia-smi >/dev/null; then
  gut "$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader | head -1)"
else
  warn "Kein NVIDIA-Treiber. Ohne GPU laeuft Whisper auf der CPU und ist"
  warn "fuer den Livebetrieb zu langsam."
  echo "        Ubuntu: sudo ubuntu-drivers autoinstall && sudo reboot"
fi

# Nur auf Debian und Ubuntu pruefen. Auf Arch heisst alles anders, und
# dpkg gibt es dort nicht: ohne diese Abfrage meldet jede Pruefung "fehlt"
# und der Versuch zu installieren laeuft ins Leere, samt nutzloser
# Passwortabfrage. Die Arch-Pakete erledigt INSTALLIEREN.sh.
if command -v dpkg >/dev/null && command -v apt-get >/dev/null; then
  for paket in python3-venv python3-pip ffmpeg libportaudio2; do
    if dpkg -s "$paket" >/dev/null 2>&1; then gut "$paket"; else
      fehlt "$paket"; NACHINSTALLIEREN="${NACHINSTALLIEREN:-} $paket"; fi
  done
  if [ -n "${NACHINSTALLIEREN:-}" ]; then
    echo "   Installiere:$NACHINSTALLIEREN"
    sudo apt-get update -qq && sudo apt-get install -y $NACHINSTALLIEREN
  fi
else
  for befehl in python3 ffmpeg; do
    if command -v "$befehl" >/dev/null; then gut "$befehl"; else
      warn "$befehl fehlt"; fi
  done
  $PY_SYS -c "import venv" 2>/dev/null && gut "venv" || warn "python venv fehlt"
fi

# ---------------------------------------------------------------- Python
blau "Python-Umgebung"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv || exit 1
  gut "venv angelegt"
else
  gut "venv vorhanden"
fi
PY=.venv/bin/python
$PY -m pip install --upgrade pip -q

if $PY -c "import torch" 2>/dev/null; then
  echo "   torch $($PY -c 'import torch;print(torch.__version__)')"
  if $PY -c "import torch;exit(0 if torch.cuda.is_available() else 1)"; then
    gut "CUDA nutzbar: $($PY -c 'import torch;print(torch.cuda.get_device_name(0))')"
  else
    warn "torch sieht keine GPU. Vermutlich die CPU-Fassung installiert."
    warn "Neu holen: .venv/bin/pip install --force-reinstall torch \\"
    warn "  --index-url https://download.pytorch.org/whl/cu128"
  fi
else
  fehlt "torch, wird geladen (mehrere GB)"
  $PY -m pip install torch --index-url https://download.pytorch.org/whl/cu128
fi

blau "Python-Pakete"
$PY -m pip install -q \
  faster-whisper transformers sentencepiece requests \
  fastapi uvicorn websockets python-multipart \
  sounddevice numpy segno piper-tts \
  && gut "alle Pakete da"

# ---------------------------------------------------------------- Ollama
blau "Ollama"
if command -v ollama >/dev/null; then
  gut "installiert"
else
  fehlt "Ollama, wird installiert"
  curl -fsSL https://ollama.com/install.sh | sh
fi

MODELL=$(grep -oP 'LIVE_MODELL\s*=\s*"\K[^"]+' config.py 2>/dev/null || echo "gemma4:12b")
if ollama list 2>/dev/null | grep -q "^${MODELL%%:*}"; then
  gut "$MODELL"
else
  fehlt "$MODELL, wird geladen (mehrere GB)"
  ollama pull "$MODELL"
fi

# ---------------------------------------------------------------- Whisper
# Ohne diesen Schritt laedt faster-whisper das Modell erst beim ersten
# Serverstart. Die Einrichtung meldet dann "fertig", und die 1,6 GB kommen
# am Sonntagmorgen. Also jetzt.
blau "Whisper-Modell"
$PY - <<'PYCODE'
import sys
import config
try:
    from faster_whisper import WhisperModel
except ImportError as e:
    sys.exit(f"faster-whisper fehlt: {e}")

ordner = config.MODELL_ORDNER
ordner.mkdir(parents=True, exist_ok=True)
print(f"   {config.WHISPER_MODELL} nach {ordner.name}/ ...")
try:
    # Zum reinen Herunterladen genuegt die CPU-Variante. So laeuft der
    # Schritt auch auf einem Rechner ohne Grafikkarte durch; der Server
    # nimmt spaeter dieselben Dateien mit CUDA.
    WhisperModel(config.WHISPER_MODELL, device="cpu", compute_type="int8",
                 download_root=str(ordner))
except Exception as e:
    sys.exit(f"fehlgeschlagen: {str(e)[:120]}")
PYCODE
if [ $? -eq 0 ]; then
  gut "Whisper-Modell liegt bereit"
else
  warn "Whisper-Modell nicht geladen. Der Server holt es beim ersten Start"
  warn "nach, das dauert dann mehrere Minuten."
fi

# ---------------------------------------------------------------- Stimmen
blau "Piper-Stimmen"
mkdir -p voices
# Welche Stimmen gebraucht werden, steht in config.py. So genuegt dort ein
# Eintrag, um eine Sprache zu ergaenzen, ohne dieses Skript anzufassen.
$PY - <<'PYCODE' > /tmp/stimmenliste 2>/dev/null || echo "" > /tmp/stimmenliste
import config
gebraucht = [config.AUSGANGSSPRACHE] + list(config.ZIELSPRACHEN)
for sp in dict.fromkeys(gebraucht):
    pfad = config.STIMMEN.get(sp)
    if pfad:
        print(sp, pfad)
PYCODE

BASIS="https://huggingface.co/rhasspy/piper-voices/resolve/main"
while read -r sprache pfad; do
  [ -z "${pfad:-}" ] && continue
  name="${pfad##*/}"
  if [ -f "voices/$name.onnx" ] && [ -f "voices/$name.onnx.json" ]; then
    gut "$sprache: $name"
    continue
  fi
  fehlt "$sprache: $name wird geladen"
  if curl -fsSL -o "voices/$name.onnx"      "$BASIS/$pfad.onnx" &&
     curl -fsSL -o "voices/$name.onnx.json" "$BASIS/$pfad.onnx.json"; then
    gut "$sprache geladen"
  else
    warn "$sprache fehlgeschlagen. Laeuft dann als reiner Untertitel."
    warn "  Pfad pruefen: huggingface.co/rhasspy/piper-voices/tree/main/$sprache"
    rm -f "voices/$name.onnx" "voices/$name.onnx.json"
  fi
done < /tmp/stimmenliste
rm -f /tmp/stimmenliste

# ---------------------------------------------------------------- Daten
blau "Projektdateien"
MANGEL=0
for datei in server.py config.py zustand.py grafikkarte.py glossar.py \
             bibelstellen.py \
             skript_lesen.py namen_aus_bibel.py laengenfaktor.py \
             selbsttest.py client.html; do
  if [ -f "$datei" ]; then gut "$datei"; else
    warn "$datei FEHLT"; MANGEL=1; fi
done
if [ "$MANGEL" = "1" ]; then
  warn ""
  warn "Ohne diese Dateien startet der Server nicht. Sie gehoeren alle in"
  warn "denselben Ordner wie dieses Skript."
fi

if [ -f glossar_v0.4.csv ]; then
  gut "glossar_v0.4.csv ($(($(wc -l < glossar_v0.4.csv) - 1)) Eintraege)"
elif [ -f build_glossar.py ]; then
  fehlt "glossar_v0.4.csv, wird erzeugt"
  $PY build_glossar.py
else
  warn "glossar_v0.4.csv fehlt und laesst sich ohne build_glossar.py"
  warn "nicht erzeugen. Ohne Glossar laeuft der Server, uebersetzt aber"
  warn "Fachbegriffe deutlich schlechter."
fi

if [ -f namen_block_b.csv ]; then
  gut "namen_block_b.csv ($(($(wc -l < namen_block_b.csv) - 1)) Namen)"
else
  warn "namen_block_b.csv fehlt. Der Server laeuft, aber das Kontextfeld"
  warn "am Pult findet keine Bibelnamen. Neu erzeugen mit:"
  warn "  .venv/bin/python namen_aus_bibel.py --von 44 --bis 1951 bibel.pdf"
fi

[ -f logo.png ] && gut "logo.png" || fehlt "logo.png (nur Optik)"

# ---------------------------------------------------------------- Tunnel
# ---------------------------------------------------------------- Audio
blau "Aufnahmegeraete"
$PY - <<'PYCODE' 2>/dev/null || echo "   sounddevice meldet nichts. Fuer den"
import sounddevice as sd
apis = {i: a["name"] for i, a in enumerate(sd.query_hostapis())}
n = 0
for i, g in enumerate(sd.query_devices()):
    if g["max_input_channels"] > 0:
        print(f"   {i:3}  {apis.get(g['hostapi'],'?'):12} "
              f"{int(g['default_samplerate']):6}  {g['name']}")
        n += 1
if not n:
    print("   Keine Aufnahmegeraete. Fuer den Netzbetrieb (--netz) egal.")
PYCODE

# ---------------------------------------------------------------- Probe
# Bis hierher wurde nur geprueft, ob Dateien und Pakete da sind. Das ist
# etwas anderes als "es funktioniert". Der Selbsttest laesst Piper einen
# Satz sprechen und Whisper ihn wieder aufschreiben; kommt er durch, ist
# die Kette nachweislich in Ordnung.
if [ -f selbsttest.py ]; then
  $PY selbsttest.py
  ERGEBNIS=$?
else
  warn "selbsttest.py fehlt, die Durchlaufprobe entfaellt"
  ERGEBNIS=0
fi

blau "Fertig"
cat <<'ENDE'
   Starten:
     ./start.sh                 Ton vom Mikrofoneingang
     ./start.sh --mikro 1       bestimmtes Aufnahmegeraet
     ./start.sh --datei x.mp3   Dauerlauf mit einer Aufnahme

   Selbsttest jederzeit erneut:
     .venv/bin/python selbsttest.py

   Alles bleibt im eigenen Netz. Keine Verbindung nach aussen.
ENDE
exit $ERGEBNIS
