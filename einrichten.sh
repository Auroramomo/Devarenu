#!/usr/bin/env bash
# Devarenu einrichten, Linux.
#
# Prueft der Reihe nach, was da ist, und ergaenzt nur das Fehlende. Laesst
# sich also gefahrlos mehrfach starten, etwa wenn ein Schritt schiefging.
#
#   chmod +x einrichten.sh
#   bash einrichten.sh

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
  # dnsmasq ist hier dabei, obwohl es nur der Gemeinderechner braucht:
  # vor Ort gibt es kein Netz zum Nachinstallieren. Es wird gleich
  # wieder stillgelegt, siehe unten -- eingeschaltet wird es allein von
  # netz_einrichten.sh.
  for paket in python3-venv python3-pip ffmpeg libportaudio2 git dnsmasq; do
    if dpkg -s "$paket" >/dev/null 2>&1; then gut "$paket"; else
      fehlt "$paket"; NACHINSTALLIEREN="${NACHINSTALLIEREN:-} $paket"; fi
  done
  if [ -n "${NACHINSTALLIEREN:-}" ]; then
    echo "   Installiere:$NACHINSTALLIEREN"
    FRISCHES_DNSMASQ=nein
    case " $NACHINSTALLIEREN " in *" dnsmasq "*) FRISCHES_DNSMASQ=ja ;; esac
    sudo apt-get update -qq && sudo apt-get install -y $NACHINSTALLIEREN
    # Debian startet dnsmasq beim Installieren sofort. Auf einem Rechner
    # mit systemd-resolved belegt dann jemand anderes Port 53, und die
    # Namensaufloesung dieses Rechners ist hinueber -- auf einem
    # Arbeitsrechner ein boeses Erwachen, und auf dem Gemeinderechner
    # eines zum falschen Zeitpunkt. Also: da, aber aus.
    if [ "$FRISCHES_DNSMASQ" = ja ]; then
      sudo systemctl disable --now dnsmasq >/dev/null 2>&1
      gut "dnsmasq liegt bereit, ist aber aus"
      echo "        Eingeschaltet wird es nur von bash netz_einrichten.sh,"
      echo "        von Hand und vor Ort."
    fi
  fi
else
  for befehl in python3 ffmpeg git; do
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
# Welche Pakete und in welcher Fassung, steht in requirements.txt. Frueher
# stand die Liste hier im Skript -- dann kannte der USB-Stick sie nicht,
# und ein Rechner ohne Netz bekam andere Versionen als einer mit.
if [ ! -f requirements.txt ]; then
  warn "requirements.txt fehlt. Ohne sie ist nicht zu sagen, welche"
  warn "Pakete gebraucht werden. Datei aus dem Repo nachlegen."
else
  # constraints.txt nagelt zusaetzlich fest, was die zwoelf Pakete
  # mitziehen. Damit installiert dieser Rechner dieselben Fassungen wie
  # der, fuer den der USB-Stick gebaut wurde. Fehlt die Datei, geht es
  # auch ohne -- dann eben nur mit den zwoelf.
  BEDINGUNG=""
  [ -f constraints.txt ] && BEDINGUNG="-c constraints.txt"
  $PY -m pip install -q $BEDINGUNG -r requirements.txt \
    && gut "alle Pakete da ($(grep -cE '^[a-zA-Z]' requirements.txt) angefordert)" \
    || warn "pip hat etwas beanstandet. Oben nachlesen."
fi

# ---------------------------------------------------------------- Ollama
blau "Ollama"
if command -v ollama >/dev/null; then
  gut "installiert"
elif command -v pacman >/dev/null; then
  # Unter Arch aus dem Paketspeicher, NICHT ueber das Installierskript
  # von ollama.com. Das legt nach /usr/local, richtet eine eigene Unit
  # ein und weiss nichts von pacman -- beim naechsten Systemwechsel
  # steht dann zweimal Ollama auf dem Rechner, und welches laeuft,
  # entscheidet der PATH.
  fehlt "Ollama, wird ueber pacman installiert"
  info_ollama() { printf '        %s\n' "$*"; }

  # Das Paket "ollama" ist CPU-ONLY. Geprueft am Paketspeicher:
  #
  #   ollama        haengt ab von: libgcc libstdc++ glibc
  #   ollama-cuda   haengt ab von: libgcc libstdc++ glibc ollama cuda
  #   ollama-rocm   dasselbe mit rocm
  #
  # Die Beschleunigung ist also ein ZUSATZPAKET, kein Ersatz -- beide
  # werden gebraucht. Ohne das zweite laeuft die Uebersetzung auf der
  # CPU: sie laeuft, aber zu langsam fuer den Livebetrieb, und es gibt
  # keine Fehlermeldung. Der Systemcheck meldet es spaeter am Pult.
  OLLAMA_PAKETE="ollama"
  if command -v nvidia-smi >/dev/null 2>&1 \
     || lspci 2>/dev/null | grep -qi "vga.*nvidia"; then
    OLLAMA_PAKETE="ollama ollama-cuda"
    info_ollama "NVIDIA erkannt -- mit ollama-cuda"
  elif lspci 2>/dev/null | grep -qiE "vga.*(amd|ati|radeon)"; then
    OLLAMA_PAKETE="ollama ollama-rocm"
    info_ollama "AMD erkannt -- mit ollama-rocm"
  else
    warn "Keine Grafikkarte erkannt. Ollama laeuft dann auf der CPU."
    info_ollama "Fuer den Livebetrieb ist das zu langsam."
  fi

  if sudo pacman -S --needed --noconfirm $OLLAMA_PAKETE; then
    gut "$OLLAMA_PAKETE aus dem Paketspeicher"
    # Das Paket richtet den Dienst ein, schaltet ihn aber nicht an.
    sudo systemctl enable --now ollama 2>/dev/null \
      && gut "Dienst ollama eingeschaltet" \
      || warn "Dienst ollama liess sich nicht starten"
  else
    warn "pacman konnte Ollama nicht installieren."
    info_ollama "Von Hand:  sudo pacman -S $OLLAMA_PAKETE"
  fi
else
  fehlt "Ollama, wird installiert"
  curl -fsSL https://ollama.com/install.sh | sh
fi

# Der Dienst muss ANTWORTEN, nicht nur laufen: ollama pull faellt sonst
# in einen Verbindungsfehler, und die Einrichtung meldet trotzdem
# weiter. Genau so fehlte auf dem neu aufgesetzten Gemeinderechner das
# Sprachmodell, ohne dass irgendwo ein Fehler stand.
for _versuch in 1 2 3 4 5 6 7 8 9 10; do
  ollama list >/dev/null 2>&1 && break
  sleep 2
done
if ! ollama list >/dev/null 2>&1; then
  warn "Ollama antwortet nicht. Das Sprachmodell wird NICHT geladen."
  warn "Ohne es gibt es keine Uebersetzung."
  echo "        Nachsehen:  systemctl status ollama"
  echo "        Danach:     bash einrichten.sh erneut"
fi

MODELL=$(grep -oP 'LIVE_MODELL\s*=\s*"\K[^"]+' config.py 2>/dev/null || echo "gemma4:12b")
if ollama list 2>/dev/null | grep -q "^${MODELL%%:*}"; then
  gut "$MODELL"
else
  fehlt "$MODELL, wird geladen (mehrere GB)"
  if ollama pull "$MODELL"; then
    gut "$MODELL geladen"
  else
    # Bis 0.2.11 lief es hier stillschweigend weiter. Auf dem frisch
    # aufgesetzten Gemeinderechner fehlte danach gemma4:12b, und
    # gemerkt wurde es erst durch pruefen.sh.
    warn "$MODELL liess sich NICHT laden."
    warn "Ohne Sprachmodell gibt es keine Uebersetzung."
    echo "        Von Hand nachholen:  ollama pull $MODELL"
  fi
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
# ALLE Stimmen aus config.py, nicht nur die heute eingestellten.
#
# Die Sprachen sind am Pult zur Laufzeit umschaltbar. Wer nur die
# eingestellten laedt, baut eine Falle: die Gemeinde waehlt spaeter
# Ukrainisch, bekommt stumme Untertitel und niemand weiss warum -- am
# wenigsten beim Rollout, wo keiner danebensteht.
#
# Einundzwanzig Stimmen sind rund 1,3 GB. Einmalig, bei der Einrichtung,
# wo ohnehin Internet gebraucht wird. Der Gemeinderechner hat danach
# keins mehr.
$PY - <<'PYCODE' > /tmp/stimmenliste 2>/dev/null || echo "" > /tmp/stimmenliste
import config
for sp, pfad in config.STIMMEN.items():
    if pfad:
        print(sp, pfad)
PYCODE
anzahl=$(wc -l < /tmp/stimmenliste)
printf '        %s\n' "$anzahl Stimmen laut config.py, rund $((anzahl * 63)) MB"

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
    echo "$sprache" >> /tmp/stimmen_fehlen
  fi
done < /tmp/stimmenliste
rm -f /tmp/stimmenliste
if [ -s /tmp/stimmen_fehlen ]; then
  warn "Ohne Stimme: $(tr '\n' ' ' < /tmp/stimmen_fehlen)"
  warn "Diese Sprachen sind am Pult waehlbar und liefern dann nur Text."
  warn "Das Pult zeigt es bei der Sprachwahl an."
fi
rm -f /tmp/stimmen_fehlen

# ---------------------------------------------------------------- Daten
blau "Projektdateien"
MANGEL=0
for datei in server.py config.py zustand.py grafikkarte.py glossar.py \
             bibelstellen.py \
             skript_lesen.py namen_aus_bibel.py laengenfaktor.py \
             tonhelfer.py selbsttest.py client.html; do
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
  # Nicht wc -l: die Datei hat mehr Zeilen als nutzbare Namen. Was der
  # Streuungsfilter als Allgemeinwort markiert hat, faellt beim Laden
  # weg. Frueher stand hier 2237, wo der Server 1212 sieht -- zwei
  # Zahlen fuer dieselbe Sache, und die falsche war die groessere.
  ANZAHL="$($PY -c 'from bibelstellen import Namensindex
from pathlib import Path
print(len(Namensindex.laden(Path("namen_block_b.csv")).eintraege))' 2>/dev/null)"
  gut "namen_block_b.csv (${ANZAHL:-?} nutzbare Namen)"
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
    print("   Keine Aufnahmegeraete. Ohne Mikrofon gibt es keinen Ton.")
else:
    # Ohne diesen Hinweis wandert eine Nummer von hier in die Einstellung
    # und trifft dort ein anderes Geraet: der Systemdienst haelt das
    # benutzte Mikrofon exklusiv offen und zaehlt ohne angemeldete
    # Sitzung andere Plugin-Eintraege mit.
    print()
    print("   ACHTUNG: Diese Nummern gelten fuer diese Sitzung. Der")
    print("   Systemdienst zaehlt anders -- auf einem Rechner gemessen")
    print("   13 Geraete gegen 7 hier. Eine Nummer von hier trifft dort")
    print("   womoeglich ein anderes Geraet.")
    print("   Deshalb am Pult unter Einrichtung AUSWAEHLEN, keine Nummern")
    print("   abtippen. Dabei wird der Name mitgeschrieben, und nach dem")
    print("   wird gesucht -- der gilt in beiden Zaehlungen.")
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

# Beim Aufruf aus INSTALLIEREN.sh stand hier ein zweites "Fertig", direkt
# ueber dem der Ersteinrichtung. Wer einrichten.sh einzeln aufruft,
# braucht den Abschluss dagegen.
if [ -z "${DEVARENU_SAMMELLAUF:-}" ]; then
  blau "Fertig"
  cat <<'ENDE'
   Starten:
     bash start.sh                 Mikrofon, Geraet aus zustand.json
     bash start.sh --mikro 1       Aufnahmegeraet erzwingen
     bash start.sh --datei x.mp3   Dauerlauf mit einer Aufnahme

   Selbsttest jederzeit erneut:
     .venv/bin/python selbsttest.py

   Alles bleibt im eigenen Netz. Keine Verbindung nach aussen.
ENDE
fi
exit $ERGEBNIS
