#!/usr/bin/env bash
# Devarenu durchsehen: was laeuft, was fehlt, was als naechstes zu tun ist.
#
#   ./pruefen.sh              alles durchgehen
#   ./pruefen.sh > bericht.txt   zum Verschicken
#
# Gedacht fuer den Rechner in der Gemeinde und fuer den Menschen, der
# davor steht -- nicht unbedingt den, der das hier gebaut hat. Jede
# Meldung sagt deshalb, was zu tun ist, nicht nur was nicht stimmt.
#
# Bewusst OHNE set -e: eine fehlende Datei, ein fehlendes Werkzeug oder
# ein nicht laufender Dienst sind Befunde, keine Abbruchgruende. Gerade
# wenn nichts geht, wird diese Ausgabe gebraucht.
#
# Braucht kein sudo. Wo etwas ohne Rechte nicht zu sehen ist, steht das
# dabei, statt dass die Pruefung scheitert.

set -u
ORDNER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ORDNER"

NAME=devarenu
PORT="${DEVARENU_PORT:-8000}"
# Fuer die Python-Schnipsel, die den laufenden Server fragen.
export PRUEF_PORT="$PORT"
PY="$ORDNER/.venv/bin/python"

# Zum Lesen der Serverantwort genuegt irgendein Python: es geht nur um
# JSON. Ohne diese Unterscheidung lieferte jedes Feld eine leere
# Zeichenkette, sobald die venv fehlte -- und das Skript meldete dann
# "kennt keine Adresse" ueber einen Server, den es gar nicht gefragt hat.
if [ -x "$PY" ]; then PYJSON="$PY"
elif command -v python3 >/dev/null 2>&1; then PYJSON=python3
else PYJSON=""; fi

N_OK=0; N_WARN=0; N_FEHL=0

blau() { printf '\n\033[1;34m== %s\033[0m\n' "$1"; }
gut()  { N_OK=$((N_OK+1));     printf '   \033[32mok\033[0m    %s\n' "$1"; }
warn() { N_WARN=$((N_WARN+1)); printf '   \033[33m!\033[0m     %s\n' "$1"; }
fehl() { N_FEHL=$((N_FEHL+1)); printf '   \033[31mFEHLT\033[0m %s\n' "$1"; }
info() {                       printf '         %s\n' "$1"; }

# Python-Schnipsel geben Zeilen der Form "OK|Text" aus; hier werden sie
# gezeichnet und gezaehlt. So steht die Zaehlung an einer Stelle, und die
# Schnipsel muessen nichts ueber Farben wissen.
zeilen() {
  while IFS='|' read -r art text; do
    case "$art" in
      OK)   gut  "$text" ;;
      WARN) warn "$text" ;;
      FEHL) fehl "$text" ;;
      # Leere Zeile bleibt leer, statt eingerueckte Leerzeichen zu
      # hinterlassen -- die sieht man erst in der abgetippten Datei.
      *)    [ -n "$text" ] && info "$text" || echo ;;
    esac
  done
}

# Laeuft nur, wenn es die venv gibt. Sonst eine Meldung statt eines
# Absturzes -- ohne venv laeuft ohnehin nichts, und das steht weiter oben
# schon.
mit_python() {
  if [ -x "$PY" ]; then "$PY" -c "$1" 2>&1 | zeilen
  else warn "Ohne venv nicht pruefbar. Erst: bash INSTALLIEREN.sh"; fi
}

printf '\033[1mDevarenu -- Durchsicht\033[0m   %s auf %s\n' \
  "$(date '+%d.%m.%Y %H:%M')" "$(hostname)"

# ------------------------------------------------------------- Rechner
blau "Rechner"

# In einer Subshell: /etc/os-release setzt NAME, VERSION und ID. Direkt
# eingelesen ueberschreibt das hier NAME=devarenu, und die Dienstpruefung
# suchte danach nach /etc/systemd/system/CachyOS.service -- also nach
# nichts. Sie meldete "nicht eingerichtet", waehrend der Dienst lief.
if [ -r /etc/os-release ]; then
  info "System    $( . /etc/os-release 2>/dev/null; echo "${PRETTY_NAME:-unbekannt}" )"
fi
info "Kern      $(uname -r)"

if [ -x "$PY" ]; then
  gut "venv vorhanden, Python $("$PY" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])' 2>/dev/null)"
else
  fehl "Keine venv in $ORDNER. Einrichten mit: bash INSTALLIEREN.sh"
fi

# Einmal feststellen, ob systemd zu fragen ist -- danach dreimal benutzt.
# Ohne diese Unterscheidung meldet ein blosses "systemctl is-active" bei
# fehlendem Zugriff auf den Systembus dasselbe wie ein wirklich
# gestoppter Dienst, und das Skript behauptete "laeuft nicht" ueber einen
# laufenden Dienst. Lieber keine Auskunft als eine falsche.
SYSTEMD=ja
if [ ! -d /run/systemd/system ]; then
  SYSTEMD=nein
elif ! systemctl show --property=Version >/dev/null 2>&1; then
  SYSTEMD=unerreichbar
fi
[ "$SYSTEMD" = unerreichbar ] && \
  warn "systemd laeuft, ist von hier aus aber nicht abfragbar. Alles zu" && \
  warn "Diensten wird deshalb uebersprungen."

# Unter welchem Benutzer laeuft der DIENST? Nicht unbedingt der, der
# gerade tippt: wer vor Ort per ssh oder mit sudo hereinkommt, ist ein
# anderer. Dann sagt "ich bin in der Gruppe audio" nichts darueber, ob
# der Dienst an das Mikrofon kommt, und "Rechte 600" nichts darueber, ob
# er zustand.json lesen darf. Beide Pruefungen weiter unten nehmen
# deshalb diesen Benutzer.
BENUTZER="$(id -un)"
WESSEN="Sie selbst"
if [ -f "/etc/systemd/system/$NAME.service" ]; then
  AUS_UNIT="$(sed -n 's/^User=//p' "/etc/systemd/system/$NAME.service" | head -1)"
  if [ -n "${AUS_UNIT:-}" ]; then
    BENUTZER="$AUS_UNIT"
    WESSEN="der Dienst"
  fi
fi

# ------------------------------------------------------- Grafikkarte
blau "Grafikkarte"

if command -v nvidia-smi >/dev/null 2>&1; then
  KARTE="$(nvidia-smi --query-gpu=name,driver_version,memory.total \
           --format=csv,noheader 2>/dev/null | head -1)"
  if [ -n "$KARTE" ]; then
    gut "$KARTE"
  else
    fehl "nvidia-smi ist da, meldet aber keine Karte. Treiber pruefen:"
    info "  nvidia-smi"
  fi
else
  fehl "Kein nvidia-smi. Ohne Grafikkarte rechnet alles auf der CPU"
  info "und ist fuer den Livebetrieb zu langsam."
fi

# --------------------------------------------------------------- Netz
blau "Netz"

# Dieselbe Ermittlung wie im Server, damit hier nicht etwas anderes
# herauskommt als in der Startausgabe.
mit_python '
import json, os, sys, urllib.request
sys.path.insert(0, ".")
import server

ip = server.lokale_ip()

# Laeuft ein Server, ist SEINE Adresse die, die die Zuhoerer bekommen --
# er hat sie in der Startausgabe genannt und im QR-Code. Die eigene
# Ermittlung ist nur der Ersatz, solange keiner antwortet.
vom_server = None
try:
    with urllib.request.urlopen(
            "http://127.0.0.1:%s/api/zustand" % os.environ.get("PRUEF_PORT", "8000"),
            timeout=5) as a:
        vom_server = json.load(a).get("adresse") or None
except Exception:
    pass

if vom_server:
    print("OK|Adresse %s (so nennt der Server sie selbst)" % vom_server)
    print("INFO|Die Handys im Saal erreichen ihn unter dieser Adresse.")
    if ip and ip != vom_server:
        print("WARN|Von hier aus ermittelt: %s -- also eine andere." % ip)
        print("WARN|Bei mehreren Netzwerkkarten kann das vorkommen. Es gilt")
        print("WARN|die des Servers; die andere kennen die Handys nicht.")
elif ip:
    print("OK|Adresse %s" % ip)
    print("INFO|Die Handys im Saal erreichen den Server unter dieser Adresse.")
else:
    print("FEHL|Keine brauchbare Netzwerkadresse.")
    print("INFO|Nachsehen mit: ip -4 addr")
    print("INFO|127.* und 169.254.* zaehlen nicht: die erste ist der Rechner")
    print("INFO|selbst, die zweite gibt er sich, wenn kein DHCP antwortet.")
'

# Der Punkt, an dem die Adresse beim Kaltstart fehlte: network-online.target
# wird erreicht, sagt aber nur "NetworkManager hat nichts mehr vor". Der
# Server faengt das inzwischen selbst ab; hier steht, was dieser Rechner
# tut, weil es beim Suchen hilft.
WARTER=""
if [ "$SYSTEMD" = ja ]; then
  for D in NetworkManager-wait-online.service systemd-networkd-wait-online.service; do
    if systemctl is-enabled "$D" >/dev/null 2>&1; then WARTER="$WARTER $D"; fi
  done
fi
if [ "$SYSTEMD" != ja ]; then
  :
elif [ -n "$WARTER" ]; then
  info "Wartet beim Start auf:$WARTER"
else
  info "Kein wait-online-Dienst eingerichtet. network-online.target ist"
  info "dann sofort erreicht und ordnet nichts. Fuer Devarenu ist das"
  info "unerheblich -- der Server sucht die Adresse selbst weiter."
fi

# ------------------------------------------------------------- Ollama
blau "Ollama"

if [ "$SYSTEMD" != ja ]; then
  :
elif systemctl list-unit-files ollama.service >/dev/null 2>&1 && \
   systemctl cat ollama.service >/dev/null 2>&1; then
  if systemctl is-active --quiet ollama.service; then
    gut "Dienst ollama laeuft"
  else
    fehl "Dienst ollama laeuft nicht. Starten mit:"
    info "  sudo systemctl enable --now ollama"
  fi
else
  warn "Keine ollama.service gefunden. Laeuft Ollama anders, ist das in"
  warn "Ordnung -- die naechste Zeile entscheidet."
fi

mit_python '
import sys; sys.path.insert(0, ".")
import config, json, urllib.request
try:
    with urllib.request.urlopen(config.OLLAMA_URL + "/api/tags", timeout=5) as a:
        modelle = [m["name"] for m in json.load(a).get("models", [])]
except Exception as e:
    print("FEHL|Ollama antwortet nicht auf %s (%s)" % (config.OLLAMA_URL, str(e)[:60]))
    print("INFO|Ohne Ollama gibt es keine Uebersetzung. Nachsehen mit:")
    print("INFO|  systemctl status ollama")
    raise SystemExit
print("OK|Ollama antwortet auf %s" % config.OLLAMA_URL)
gesucht = config.LIVE_MODELL
if any(m == gesucht or m.split(":")[0] == gesucht.split(":")[0] for m in modelle):
    print("OK|Modell %s ist da" % gesucht)
else:
    print("FEHL|Modell %s fehlt. Holen mit:" % gesucht)
    print("INFO|  ollama pull %s" % gesucht)
    print("INFO|Vorhanden waeren: %s" % (", ".join(modelle) or "keins"))
'

# --------------------------------------------- Modelle und Stimmen
blau "Modelle und Stimmen"

mit_python '
import sys; sys.path.insert(0, ".")
import config
mo = config.MODELL_ORDNER
treffer = list(mo.glob("**/*%s*" % config.WHISPER_MODELL.replace("large-v3-turbo", "large-v3-turbo"))) if mo.is_dir() else []
if treffer:
    print("OK|Whisper %s liegt in %s" % (config.WHISPER_MODELL, mo.name))
else:
    print("FEHL|Whisper %s nicht in %s. Holen mit: ./einrichten.sh"
          % (config.WHISPER_MODELL, mo))

import zustand as zd
stand, _ = zd.laden()
sprachen = [stand["quelle"]] + [s for s in stand["ziele"] if s != stand["quelle"]]
fehlend, stumm = [], []
for s in sprachen:
    pfad = config.STIMMEN.get(s)
    if not pfad:
        stumm.append(s); continue
    datei = config.BASIS / "voices" / (pfad.rsplit("/", 1)[1] + ".onnx")
    if not datei.exists():
        fehlend.append(s)
if not fehlend and not stumm:
    print("OK|Fuer alle %d Sprachen ist eine Stimme da (%s)"
          % (len(sprachen), ", ".join(sprachen)))
if stumm:
    print("WARN|Ohne vorgesehene Stimme, laeuft als reiner Untertitel: %s"
          % ", ".join(stumm))
if fehlend:
    print("FEHL|Stimme fehlt fuer: %s. Holen mit: ./einrichten.sh"
          % ", ".join(fehlend))
ungeprueft = [s for s in sprachen if s not in config.GEPRUEFT]
if ungeprueft:
    print("INFO|Terminologie maschinell erzeugt und ungeprueft: %s"
          % ", ".join(ungeprueft))
'

# ------------------------------------------------------------ Dienst
blau "Dienst"

DIENST_LAEUFT=nein
if [ "$SYSTEMD" = nein ]; then
  warn "Kein systemd. Dann wird von Hand gestartet: ./start.sh"
elif [ "$SYSTEMD" = unerreichbar ]; then
  warn "Nicht abfragbar, siehe oben. Von Hand nachsehen mit:"
  warn "  systemctl status $NAME"
elif [ -f "/etc/systemd/system/$NAME.service" ]; then
  gut "Unit ist installiert"

  if systemctl is-enabled --quiet $NAME 2>/dev/null; then
    gut "startet mit dem Rechner"
  else
    fehl "startet NICHT mit dem Rechner. Nach einem Stromausfall bliebe"
    info "es still. Einschalten mit: sudo systemctl enable $NAME"
  fi

  if systemctl is-active --quiet $NAME; then
    DIENST_LAEUFT=ja
    SEIT="$(systemctl show $NAME -p ActiveEnterTimestamp --value 2>/dev/null)"
    gut "laeuft${SEIT:+, seit $SEIT}"
    NEUSTARTS="$(systemctl show $NAME -p NRestarts --value 2>/dev/null)"
    if [ -n "${NEUSTARTS:-}" ] && [ "${NEUSTARTS:-0}" -gt 0 ] 2>/dev/null; then
      warn "$NEUSTARTS Neustarts seit dem Einschalten. Ein einzelner ist"
      warn "harmlos, viele deuten auf einen wiederkehrenden Fehler:"
      warn "  journalctl -u $NAME -b"
    fi
  else
    fehl "laeuft nicht. Die letzten Zeilen aus dem Journal:"
    echo
    journalctl -u $NAME -n 20 --no-pager 2>/dev/null | sed 's/^/         /' \
      || info "(Journal nicht lesbar)"
    echo
    info "Starten mit: sudo systemctl start $NAME"
  fi
else
  warn "Nicht als Dienst eingerichtet. Nach dem Einschalten kommt der"
  warn "Server dann nicht von allein hoch. Einrichten mit: ./dienst.sh"
  warn "Wer nur entwickelt, braucht das nicht und nimmt ./start.sh"
fi

# ------------------------------------------------------------ Server
blau "Server"

ANTWORT="$(curl -s -m 5 "http://127.0.0.1:$PORT/api/zustand" 2>/dev/null)"
if [ -z "$ANTWORT" ]; then
  if [ "$DIENST_LAEUFT" = ja ]; then
    fehl "Antwortet nicht auf Port $PORT, obwohl der Dienst laeuft."
    info "Beim Start laedt er das Whisper-Modell, das dauert einige"
    info "Sekunden. Bleibt es dabei:  journalctl -u $NAME -f"
  else
    warn "Antwortet nicht auf Port $PORT -- er laeuft ja auch nicht."
    info "Das Uebrige ist trotzdem geprueft."
  fi
else
  feld() {
    [ -n "$PYJSON" ] || return 0
    printf '%s' "$ANTWORT" | "$PYJSON" -c \
      "import json,sys; print(json.load(sys.stdin).get('$1',''))" 2>/dev/null
  }
  gut "antwortet auf Port $PORT"
  info "Fassung   $(feld fassung)"

  RECHENWERK="$(feld rechenwerk)"
  case "$RECHENWERK" in
    cuda*) gut "rechnet auf der Grafikkarte: $RECHENWERK" ;;
    "")    warn "Konnte nicht feststellen, worauf gerechnet wird" ;;
    *)     fehl "rechnet auf: $RECHENWERK"
           info "Fuer den Livebetrieb ist die CPU zu langsam. Meist fehlen"
           info "die CUDA-Bibliotheken. Nachsehen mit:"
           info "  .venv/bin/python selbsttest.py" ;;
  esac

  # Zwischen "Feld leer" und "Feld gibt es nicht" liegt ein Unterschied:
  # das zweite heisst, dass eine aeltere Fassung laeuft als die im Ordner.
  # Nach einem git pull ohne Dienstneustart ist genau das der Fall.
  HAT_FELD="$([ -n "$PYJSON" ] && printf '%s' "$ANTWORT" | "$PYJSON" -c \
    "import json,sys; print('ja' if 'adresse' in json.load(sys.stdin) else 'nein')" \
    2>/dev/null)"
  ADRESSE="$(feld adresse)"
  if [ -z "$PYJSON" ]; then
    warn "Der Server antwortet, aber ohne Python laesst sich die Antwort"
    warn "hier nicht lesen. Von Hand:  curl localhost:$PORT/api/zustand"
  elif [ "${HAT_FELD:-ja}" = nein ]; then
    warn "Der laufende Server kennt die Adressauskunft noch nicht -- er"
    warn "laeuft mit einer aelteren Fassung als der Ordner. Neu starten:"
    warn "  sudo systemctl restart $NAME"
  elif [ -n "$ADRESSE" ]; then
    gut "erreichbar unter http://$ADRESSE:$PORT/"
    info "Pult      http://$ADRESSE:$PORT/pult"
    info "QR-Codes  http://$ADRESSE:$PORT/qr"
  else
    fehl "kennt noch keine Netzwerkadresse. Ohne die erreicht ihn kein"
    info "Handy im Saal. Siehe Abschnitt Netz weiter oben."
  fi
fi

# --------------------------------------------------------------- Ton
blau "Ton"

if [ -d /dev/snd ]; then
  gut "/dev/snd ist da"
else
  fehl "/dev/snd fehlt. Ohne Tongeraete gibt es nichts aufzunehmen."
fi

if id -nG "$BENUTZER" 2>/dev/null | tr ' ' '\n' | grep -qx audio; then
  gut "$BENUTZER ist in der Gruppe audio ($WESSEN)"
else
  info "$BENUTZER ist nicht in der Gruppe audio. Die Unit gleicht das mit"
  info "SupplementaryGroups=audio aus, der Dienst kommt also trotzdem an"
  info "den Ton. Von Hand gestartet fehlt er womoeglich:"
  info "  sudo usermod -aG audio $BENUTZER"
fi

# Der wichtigste Punkt der ganzen Durchsicht -- und der, an dem dieses
# Skript zuerst falsch lag.
#
# Eine Geraeteliste aus DIESEM Prozess ist mit den Nummern des Dienstes
# nicht vergleichbar. Gemessen auf demselben Rechner, zur selben Sekunde:
#
#   Dienst (ohne Sitzung)   13 Geraete, Nr. 0 = Auna Mic CM900 (hw:0,0)
#   hier (mit Sitzung)       7 Geraete, Nr. 0 = USB Audio: - (hw:1,0)
#
# Zwei Ursachen ueberlagern sich: das benutzte Mikrofon haelt der Server
# exklusiv offen und faellt hier aus der Aufzaehlung, und ohne Sitzung
# zeigt ALSA einen anderen Satz Plugin-Eintraege (sysdefault, spdif,
# lavrate statt pipewire, pulse, default). Alles dahinter verschiebt sich.
#
# Frueher verglich dieses Skript die hinterlegte Auswahl gegen die eigene
# Aufzaehlung. Das schlug im Normalbetrieb rot aus -- nicht zufaellig,
# sondern immer, sobald der Dienst laeuft. Wer davor steht, haelt ein
# funktionierendes System fuer kaputt.
#
# Deshalb: nimmt der Server auf, ist seine Antwort die Wahrheit. Die
# eigene Aufzaehlung gilt nur, wenn keiner laeuft oder keiner aufnimmt.
mit_python '
import json, os, sys, urllib.request
sys.path.insert(0, ".")
import zustand as zd, server

stand, woher = zd.laden()
nummer, name = stand["geraet"], stand["geraet_name"]
port = os.environ.get("PRUEF_PORT", "8000")


def hinterlegt():
    print("INFO|Hinterlegt in %s:" % woher)
    print("INFO|  Nummer %s, Name %s"
          % (nummer if nummer is not None else "-",
             ("\"%s\"" % name) if name else "-"))


def liste_zeigen(liste, quelle):
    print("INFO|%d Aufnahmegeraete (%s):" % (len(liste), quelle))
    for g in liste[:12]:
        print("INFO|  %s%3d  %-18s %s"
              % ("  " if g.get("empfohlen", True) else " !", g["nummer"],
                 g["schnittstelle"], g["name"][:44]))
    if len(liste) > 12:
        print("INFO|  ... und %d weitere" % (len(liste) - 12))


def eigene_nummern_warnen():
    """Der wichtigste Satz dieser Ausgabe.

    Wer eine Nummer von hier am Pult eintraegt, trifft womoeglich ein
    anderes Geraet -- und merkt es erst im Gottesdienst."""
    print("WARN|ACHTUNG: Diese Nummern stammen aus dieser Sitzung.")
    print("WARN|Der Dienst zaehlt anders. Auf diesem Rechner gemessen:")
    print("WARN|13 Geraete beim Dienst gegen 7 hier, mit unterschiedlichen")
    print("WARN|Plugin-Eintraegen -- also auch andere Nummern.")
    print("WARN|Wer eine Nummer von hier am Pult eintraegt, trifft")
    print("WARN|womoeglich ein anderes Geraet.")
    print("WARN|Am Pult AUSWAEHLEN, keine Nummern abtippen.")


# ---- Was sagt der laufende Server? --------------------------------
antwort = None
try:
    with urllib.request.urlopen(
            "http://127.0.0.1:%s/api/geraete" % port, timeout=5) as a:
        antwort = json.load(a)
except Exception:
    antwort = None

if antwort and antwort.get("fehler"):
    print("WARN|Server meldet: %s" % str(antwort["fehler"])[:100])

nimmt_auf = bool(antwort and antwort.get("aktiv") and antwort.get("laeuft"))

# ---- Fall A: der Server nimmt auf, seine Antwort gilt --------------
if nimmt_auf:
    offen_nr = antwort.get("aktuell")
    offen_name = antwort.get("name") or ""
    liste = antwort.get("liste") or []
    if liste:
        liste_zeigen(liste, "wie der Dienst sie zaehlt -- das sind die "
                            "Nummern, die am Pult gelten")
        print("INFO|")
    hinterlegt()

    print("INFO|Server nimmt auf: \"%s\" (Nr. %s), %s Hz"
          % (offen_name or "?", offen_nr, antwort.get("rate")))

    if not name and nummer is None:
        print("WARN|Nichts festgelegt -- es gilt das Vorgabegeraet, und das")
        print("WARN|ist gerade \"%s\". Am Pult einmal auswaehlen, dann steht"
              % (offen_name or "?"))
        print("WARN|der Name in zustand.json und ueberlebt das Umstecken.")
    elif not name:
        print("WARN|Nur eine Nummer hinterlegt, kein Name. Am Pult einmal")
        print("WARN|auswaehlen, dann wird der Name mitgeschrieben -- die")
        print("WARN|Nummer allein bezeichnet nach einem Neustart womoeglich")
        print("WARN|ein anderes Geraet.")
    elif name == offen_name:
        print("OK|Hinterlegt ist dasselbe Geraet. Passt.")
        if nummer != offen_nr:
            print("INFO|Gefunden unter Nummer %s, hinterlegt war %s: die"
                  % (offen_nr, nummer))
            print("INFO|Nummer hat sich verschoben, der Name hat es")
            print("INFO|aufgefangen. Genau dafuer steht er in zustand.json.")
    else:
        print("FEHL|Der Server nimmt etwas anderes auf als eingestellt.")
        print("INFO|Hinterlegt: \"%s\"" % name)
        print("INFO|Offen:      \"%s\"" % offen_name)
        print("INFO|Der hinterlegte Name war beim Start nicht da, er ist auf")
        print("INFO|ein anderes Geraet ausgewichen. Mikrofon angeschlossen?")
        print("INFO|Sonst am Pult neu auswaehlen.")
    raise SystemExit

# ---- Fall B: Server antwortet, hat aber kein Geraet offen ----------
if antwort and antwort.get("aktiv"):
    print("FEHL|Der Server hat kein Geraet offen, es kommt kein Ton.")
    print("INFO|Am Pult unter Einrichtung eines auswaehlen.")
elif antwort is not None:
    print("INFO|Der Ton kommt nicht vom Mikrofon dieses Rechners")
    print("INFO|(--netz oder --datei).")
    raise SystemExit

# ---- Fall B und C: jetzt ist die eigene Aufzaehlung die beste Quelle
try:
    liste = server.geraete_liste()
except Exception as e:
    print("FEHL|Geraeteliste nicht lesbar: %s" % str(e)[:100])
    raise SystemExit

if not liste:
    print("FEHL|Kein einziges Aufnahmegeraet gefunden.")
    raise SystemExit

liste_zeigen(liste, "aus dieser Sitzung")
eigene_nummern_warnen()
print("INFO|")
hinterlegt()

nach_name = [g for g in liste if g["name"] == name] if name else []
in_liste  = [g for g in liste if g["nummer"] == nummer]

if not name and nummer is None:
    print("WARN|Kein Geraet festgelegt, es gilt das Vorgabegeraet des Systems.")
    print("INFO|Am Pult unter Einrichtung eines auswaehlen -- dann steht der")
    print("INFO|Name dabei und ueberlebt das Umstecken.")
elif not name:
    print("WARN|Nur eine Nummer hinterlegt, kein Name. Genau das war der")
    print("WARN|Grund fuer die Umstellung: Nummer %s zeigt hier auf" % nummer)
    print("WARN|  %s" % (in_liste[0]["name"] if in_liste else "gar kein Geraet"))
    print("INFO|Am Pult einmal auswaehlen, dann wird der Name mitgeschrieben.")
elif nach_name:
    jetzt = nach_name[0]["nummer"]
    if jetzt == nummer:
        print("OK|Name gefunden unter Nummer %d -- wie hinterlegt." % jetzt)
    else:
        print("OK|Name gefunden unter Nummer %d, hinterlegt war %s."
              % (jetzt, nummer))
        print("INFO|Die Nummer hat sich verschoben, der Name greift. Genau")
        print("INFO|dafuer steht er in zustand.json.")
elif in_liste:
    print("FEHL|Geraet \"%s\" ist in dieser Sitzung nicht da." % name)
    print("INFO|Nummer %s gibt es zwar, das ist hier aber ein anderes" % nummer)
    print("INFO|Geraet: %s" % in_liste[0]["name"][:50])
    print("INFO|Mikrofon angeschlossen? Sonst am Pult neu auswaehlen.")
else:
    print("FEHL|Weder \"%s\" noch Nummer %s ist in dieser Sitzung da."
          % (name, nummer))
    print("INFO|Es gilt das Vorgabegeraet. Mikrofon anschliessen und am")
    print("INFO|Pult unter Einrichtung auswaehlen.")
'

# ------------------------------------------------------------ Zustand
blau "Zustand"

if [ -f zustand.json ]; then
  RECHTE="$(stat -c %a zustand.json 2>/dev/null)"
  EIGNER="$(stat -c %U zustand.json 2>/dev/null)"
  if [ "${RECHTE:-}" != "600" ]; then
    warn "zustand.json hat Rechte ${RECHTE:-?}, erwartet 600. Darin steht"
    warn "das WLAN-Passwort im Klartext. Richten mit:"
    warn "  chmod 600 zustand.json"
  elif [ -n "${EIGNER:-}" ] && [ "$EIGNER" != "$BENUTZER" ]; then
    # Rechte 600 heisst: nur der Eigentuemer liest sie. Ist das ein
    # anderer als der Dienstbenutzer, liest der Dienst sie NICHT und
    # faellt still auf die Vorgaben aus config.py zurueck -- Tonquelle,
    # Sprachen und Einmessung waeren weg, ohne dass es jemand merkt.
    fehl "zustand.json gehoert $EIGNER, der Dienst laeuft als $BENUTZER."
    info "Bei Rechten 600 liest er sie nicht und nimmt die Vorgaben aus"
    info "config.py: Tonquelle, Sprachen und Einmessung waeren weg."
    info "Richten mit:  sudo chown $BENUTZER zustand.json"
  else
    gut "zustand.json, Rechte $RECHTE, gehoert $EIGNER"
  fi
else
  warn "Keine zustand.json. Es gelten die Vorgaben aus config.py; sie"
  warn "entsteht beim ersten Speichern am Pult."
fi

mit_python '
import sys; sys.path.insert(0, ".")
import zustand as zd
stand, woher = zd.laden()
print("INFO|%s" % zd.kurzfassung(stand))
s = stand["schwelle"]
if s.get("wert") is None:
    print("WARN|Noch nicht eingemessen. Vor dem Gottesdienst den Prediger")
    print("WARN|zwoelf Sekunden sprechen lassen, am Pult unter Einrichtung.")
else:
    print("OK|Eingemessen am %s (Schwelle %.4f)"
          % (s.get("gemessen") or "unbekannt", s["wert"]))
if not stand["wlan"].get("ssid"):
    print("WARN|Kein WLAN eingetragen. Die QR-Seite am Beamer zeigt dann")
    print("WARN|keinen Zugang. Am Pult unter Einrichtung nachtragen.")
else:
    print("OK|WLAN \"%s\" eingetragen" % stand["wlan"]["ssid"])
'

# ------------------------------------------------------------ Fassung
blau "Fassung"

if [ -f VERSION ]; then
  info "VERSION   $(cat VERSION)"
else
  warn "Keine VERSION-Datei. Am Pult steht dann \"unbekannt\"."
fi

if command -v git >/dev/null 2>&1 && [ -d .git ]; then
  info "Stand     $(git log -1 --format='%h %ad %s' --date=short 2>/dev/null | cut -c1-70)"
  if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
    warn "Lokale Aenderungen im Ordner. ./aktualisieren.sh bricht deshalb"
    warn "ab, statt sie zu ueberschreiben. Ansehen mit: git status"
  else
    gut "keine lokalen Aenderungen, ./aktualisieren.sh laeuft durch"
  fi
else
  warn "Kein Git-Ordner. ./aktualisieren.sh braucht einen."
fi

# ----------------------------------------------------------- Schluss
blau "Zusammen"

printf '   %d in Ordnung' "$N_OK"
[ $N_WARN -gt 0 ] && printf ', %d zu beachten' "$N_WARN"
[ $N_FEHL -gt 0 ] && printf ', \033[31m%d fehlt\033[0m' "$N_FEHL"
printf '\n\n'

if [ $N_FEHL -gt 0 ]; then
  echo "   Die mit FEHLT stehen dem Betrieb im Weg. Bei jedem steht,"
  echo "   was zu tun ist."
elif [ $N_WARN -gt 0 ]; then
  echo "   Nichts steht dem Betrieb im Weg. Die mit ! sind Hinweise."
else
  echo "   Alles in Ordnung."
fi

cat <<'ENDE'

   Diese Ausgabe laesst sich abfotografieren oder festhalten mit:
     ./pruefen.sh > bericht.txt 2>&1

ENDE

[ $N_FEHL -gt 0 ] && exit 1
exit 0
