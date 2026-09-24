#!/usr/bin/env bash
# Devarenu durchsehen: was laeuft, was fehlt, was als naechstes zu tun ist.
#
#   bash pruefen.sh              alles durchgehen
#   bash pruefen.sh > bericht.txt   zum Verschicken
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

# Die kurze Fassung eigens: nach ihr richten sich die Wheels auf einem
# Update-Stick. Wer einen baut, braucht genau diese Zahl -- und rueckfragen
# kann er auf einem Rechner ohne Netz schlecht.
if [ -x "$PY" ]; then
  info "Stickziel $("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null) \
(fuer stick_bauen.sh --python)"
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

# Sperrt eine Firewall den Port? Von diesem Rechner aus faellt das nie
# auf: Loopback ist frei, und auch die eigene LAN-Adresse antwortet. Erst
# das Handy im Saal laeuft in die Wand -- und bis dahin steht hier alles
# auf gruen. Deshalb geprueft, obwohl nichts danach aussieht.
if [ -f "$ORDNER/firewall.sh" ]; then
  . "$ORDNER/firewall.sh"
  firewall_lage "$PORT"
  if [ -z "${FW_ART:-}" ]; then
    gut "keine Firewall sperrt Port $PORT"
  else
    fehl "Die Firewall ($FW_ART) sperrt Port $PORT."
    info "Von hier aus faellt das nicht auf, vom Handy im Saal schon."
    info "Freigeben mit:"
    info "  $FW_BEFEHL"
  fi

  # Ist dieser Rechner der Router, braucht der Saal mehr als 8000:
  # DNS und DHCP, damit ein Handy ueberhaupt eine Adresse und einen
  # Namen bekommt, und 80 fuer die Pruefadressen der Hersteller. Bis
  # 0.2.11 wurde nur 8000 geprueft -- und genau die anderen drei
  # fehlten auf dem Gemeinderechner.
  if [ "$("$PYJSON" -c "
import sys; sys.path.insert(0, '.')
import netzzustand; print('ja' if netzzustand.ist_router() else 'nein')
" 2>/dev/null)" = "ja" ] && command -v ufw >/dev/null; then
    KARTE="$("$PYJSON" -c "
import sys; sys.path.insert(0, '.')
import netzzustand; print(netzzustand.laden()[0]['schnittstelle'])
" 2>/dev/null)"
    UFWSTAND="$(sudo -n ufw status 2>/dev/null || ufw status 2>/dev/null)"
    if [ -z "$UFWSTAND" ]; then
      info "ufw-Regeln nicht einsehbar (braucht Wurzelrechte)."
      info "  sudo bash pruefen.sh"
    elif ! printf '%s' "$UFWSTAND" | grep -q "Status: active"; then
      gut "ufw ist aus -- nichts wird gesperrt"
    else
      for PP in "53" "67" "80" "8000"; do
        if printf '%s' "$UFWSTAND" | grep -qE "^$PP\b.*on ${KARTE}\b|^$PP/.*on ${KARTE}\b"; then
          gut "Port $PP ist auf $KARTE frei"
        else
          fehl "Port $PP ist auf $KARTE NICHT frei."
          info "Ohne 53 und 67 bekommt kein Handy eine Adresse,"
          info "ohne 80 meldet jedes \"kein Internet\"."
          info "  sudo bash firewall.sh --schnittstelle $KARTE"
        fi
      done
    fi
  fi
fi

# ----------------------------------------------------------- Saalnetz
# Nur wenn dieser Rechner der Router ist. Ohne den Umbau gibt es hier
# nichts zu pruefen, und eine Reihe roter Zeilen auf einem Rechner, der
# gar nicht umgebaut wurde, waere eine falsche Fehlersuche.
NETZROUTER="$("$PYJSON" -c "
import sys; sys.path.insert(0, '.')
import config; print('ja' if getattr(config, 'NETZ_ROUTER', False) else 'nein')
" 2>/dev/null)"

if [ "${NETZROUTER:-nein}" = "ja" ]; then
blau "Saalnetz"

# Laeuft dnsmasq? Ohne ihn bekommt kein Handy eine Adresse -- das Netz
# ist da, aber leer.
if [ "$SYSTEMD" = ja ] && systemctl is-active --quiet dnsmasq; then
  gut "dnsmasq laeuft"
elif pgrep -x dnsmasq >/dev/null 2>&1; then
  gut "dnsmasq laeuft (ohne systemd)"
else
  fehl "dnsmasq laeuft nicht."
  info "Ohne ihn bekommt kein Handy eine Adresse und keines findet"
  info "diesen Rechner. Starten mit:"
  info "  sudo systemctl start dnsmasq"
  info "Sagt er nichts, verraet der Grund sich mit:"
  info "  sudo dnsmasq --test"
fi

# Traegt die Karte die feste Adresse wirklich? Das Profil kann angelegt
# und trotzdem nicht aktiv sein.
ADR="$("$PYJSON" -c "
import sys; sys.path.insert(0, '.')
import config; print(config.NETZ_ADRESSE)" 2>/dev/null)"
if ip -4 addr 2>/dev/null | grep -q "inet $ADR/"; then
  gut "Adresse $ADR liegt auf einer Karte"
else
  fehl "Adresse $ADR liegt auf keiner Karte."
  info "Das Profil ist angelegt, aber nicht aktiv. Nachsehen mit:"
  info "  nmcli device status ; ip -4 addr"
fi

# Weiterleitung muss aus sein. Steht sie an, haengt der Saal am
# Hausnetz -- und das ist genau das, was nicht sein soll.
WEITER="$(cat /proc/sys/net/ipv4/ip_forward 2>/dev/null)"
if [ "${WEITER:-0}" = "0" ]; then
  gut "keine Weiterleitung (ip_forward=0)"
else
  fehl "ip_forward=$WEITER -- der Rechner leitet weiter."
  info "Der Saal soll kein Internet haben und keinen Weg ins Hausnetz."
  info "  sudo sysctl -w net.ipv4.ip_forward=0"
fi

# Steht die Option 114 in der erzeugten Konfiguration?
CONF=/etc/dnsmasq.d/devarenu.conf
if [ ! -f "$CONF" ]; then
  fehl "$CONF fehlt."
  info "Der Umbau ist nicht gelaufen oder wurde zurueckgenommen:"
  info "  sudo bash netz_einrichten.sh"
elif grep -q '^dhcp-option=114,' "$CONF"; then
  gut "DHCP-Option 114 gesetzt ($(grep -m1 '^dhcp-option=114,' "$CONF" | cut -d, -f2-))"
else
  warn "Keine DHCP-Option 114 in $CONF."
  info "Ohne sie fragt kein Geraet die Captive-Portal-API ab. Kein"
  info "Ausfall -- die Pruefadressen wirken auch ohne. Einschalten mit"
  info "NETZ_CAPTIVE_API in config.py und erneutem Umbau."
fi

# Antwortet der DNS so, wie er soll? Zwei Fragen, und beide muessen
# stimmen: die Pruefnamen der Hersteller auf uns, alles andere
# unaufloesbar. Ein Platzhalter fuer alles waere hier gruen und im Saal
# ein leerer Akku.
mit_python '
import random, socket, struct, sys
sys.path.insert(0, ".")
import config

def frage(name, server, timeout=3.0):
    """(rcode, [A-Adressen]) oder None bei Zeitueberschreitung."""
    xid = random.getrandbits(16)
    p = struct.pack("!HHHHHH", xid, 0x0100, 1, 0, 0, 0)
    for teil in name.split("."):
        b = teil.encode("idna") if teil else b""
        p += bytes([len(b)]) + b
    p += b"\0" + struct.pack("!HH", 1, 1)          # A, IN
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    try:
        s.sendto(p, (server, 53))
        while True:
            daten, _ = s.recvfrom(4096)
            if len(daten) >= 12 and struct.unpack("!H", daten[:2])[0] == xid:
                break
    except (socket.timeout, TimeoutError, OSError):
        return None
    finally:
        s.close()
    flags, qd, an = struct.unpack("!HHH", daten[2:8])
    i = 12
    for _ in range(qd):                            # Frageteil ueberspringen
        while i < len(daten) and daten[i]:
            if daten[i] & 0xC0:
                i += 1
                break
            i += daten[i] + 1
        i += 5
    adressen = []
    for _ in range(an):
        while i < len(daten):
            if daten[i] & 0xC0:
                i += 2
                break
            if daten[i] == 0:
                i += 1
                break
            i += daten[i] + 1
        if i + 10 > len(daten):
            break
        typ, _kl, _ttl, laenge = struct.unpack("!HHIH", daten[i:i + 10])
        i += 10
        if typ == 1 and laenge == 4:
            adressen.append(socket.inet_ntoa(daten[i:i + 4]))
        i += laenge
    return flags & 0x0F, adressen

server = config.NETZ_ADRESSE
pruef = (config.PRUEFDOMAENEN or ["captive.apple.com"])[0]

a = frage(pruef, server)
if a is None:
    print("FEHL|DNS auf %s antwortet nicht." % server)
    print("INFO|Kein Handy kommt damit durch die Internetpruefung.")
    print("INFO|Laeuft dnsmasq, und hoert er auf dieser Adresse?")
elif a[1] == [config.NETZ_ADRESSE]:
    print("OK|DNS: %s -> %s" % (pruef, config.NETZ_ADRESSE))
else:
    print("FEHL|DNS: %s -> %s, erwartet %s"
          % (pruef, a[1] or ("rcode %d" % a[0]), config.NETZ_ADRESSE))
    print("INFO|Die Pruefadresse zeigt nicht auf diesen Rechner.")

# Ein Name, den es nirgends gibt. Er MUSS unaufloesbar bleiben.
b = frage("kein-name-devarenu-pruefung.invalid", server)
if b is None:
    print("FEHL|DNS antwortet auf unbekannte Namen gar nicht.")
elif b[0] == 3 and not b[1]:
    print("OK|Unbekannte Namen bleiben unaufloesbar (NXDOMAIN)")
else:
    print("FEHL|Ein unbekannter Name wird beantwortet: %s"
          % (b[1] or ("rcode %d" % b[0])))
    print("INFO|Hier steht ein Platzhalter fuer alle Namen. Dann laufen")
    print("INFO|die Hintergrunddienste JEDES Handys im Saal auf diesen")
    print("INFO|Rechner -- auch die der Leute, die gar nicht mithoeren.")
    print("INFO|Sie wiederholen ihre Anfragen bis zum leeren Akku.")
'

# Die Pruefadressen selbst, ueber Port 80. Dass der Server antwortet,
# sagt noch nicht, dass er das Richtige antwortet: bei iOS entscheidet
# ein einzelnes Byte.
mit_python '
import sys, urllib.request
sys.path.insert(0, ".")
import config
import netzpruefung as n

basis = "http://127.0.0.1:80"
faelle = [
    ("/generate_204",        204, b"",                   "Android"),
    ("/hotspot-detect.html", 200, n.APPLE_MIT_UMBRUCH,   "Apple"),
    ("/library/test/success.html", 200, n.APPLE_OHNE_UMBRUCH, "Apple"),
    ("/connecttest.txt",     200, n.WINDOWS_CONNECTTEST, "Windows"),
    ("/ncsi.txt",            200, n.WINDOWS_NCSI,        "Windows"),
    ("/success.txt",         200, n.FIREFOX_SUCCESS,     "Firefox"),
]
schlecht = 0
erreichbar = True
for pfad, kode, rumpf, wer in faelle:
    try:
        with urllib.request.urlopen(basis + pfad, timeout=5) as a:
            ist = a.read()
            if a.status != kode or ist != rumpf:
                schlecht += 1
                print("FEHL|%s (%s): %d, %d Bytes -- erwartet %d, %d Bytes"
                      % (pfad, wer, a.status, len(ist), kode, len(rumpf)))
    except urllib.error.HTTPError as e:
        schlecht += 1
        print("FEHL|%s (%s): HTTP %d" % (pfad, wer, e.code))
    except Exception as e:
        erreichbar = False
        print("FEHL|Port 80 antwortet nicht: %s" % type(e).__name__)
        print("INFO|Die Pruefadressen der Hersteller fragen NUR Port 80.")
        print("INFO|Ohne ihn meldet jedes Handy \"kein Internet\" und")
        print("INFO|verlaesst das WLAN wieder. Sieht der Dienst")
        print("INFO|AmbientCapabilities=CAP_NET_BIND_SERVICE vor?")
        print("INFO|  systemctl cat devarenu | grep Ambient")
        break
if erreichbar and not schlecht:
    print("OK|Alle %d Pruefadressen antworten byte-genau" % len(faelle))

if erreichbar and getattr(config, "NETZ_CAPTIVE_API", False):
    try:
        with urllib.request.urlopen(basis + "/captive-api", timeout=5) as a:
            typ = a.headers.get("content-type", "")
            if typ.startswith("application/captive+json"):
                print("OK|Captive-Portal-API antwortet (%s)" % typ)
            else:
                print("FEHL|Captive-Portal-API sendet %s" % (typ or "nichts"))
                print("INFO|RFC 8908 verlangt application/captive+json.")
                print("INFO|Mit application/json erkennen manche Geraete")
                print("INFO|die Antwort nicht als solche.")
    except Exception as e:
        print("FEHL|Captive-Portal-API: %s" % type(e).__name__)
'

# Ein zweiter DHCP-Server. Der Fehler, der sonntags die Haelfte der
# Handys kostet und von dem man am Rechner nichts merkt.
if [ "$(id -u)" = "0" ]; then
  KARTE="$(ip -o -4 addr show 2>/dev/null | awk -v a="$ADR" '$4 ~ "^"a"/" {print $2; exit}')"
  if [ -z "$KARTE" ]; then
    warn "Ohne die Karte zu $ADR kein DHCP-Rundruf moeglich."
  else
    AUSGABE="$("$PYJSON" "$ORDNER/dhcp_umschau.py" "$KARTE" 4 2>&1)"
    ALLE="$(printf '%s\n' "$AUSGABE" | awk -F'|' '$1=="SERVER"{print $2}')"
    ANDERE="$(printf '%s\n' "$ALLE" | grep -v "^$ADR$" | grep -v '^$')"
    if [ -n "$ANDERE" ]; then
      fehl "Ein zweiter DHCP-Server antwortet: $(echo $ANDERE)"
      info "Am Zugangspunkt ist DHCP noch eingeschaltet. Dann vergeben"
      info "zwei Server Adressen, und welcher zuerst antwortet,"
      info "entscheidet der Zufall. Die Handys aus dem falschen Topf"
      info "finden diesen Rechner nicht."
      info "Am Zugangspunkt DHCP ausschalten. Siehe AUFSTELLEN.md."
    elif echo "$ALLE" | grep -q "^$ADR$"; then
      gut "nur dieser Rechner verteilt Adressen"
    else
      fehl "Auf $KARTE verteilt niemand Adressen, auch wir nicht."
      info "Kein Handy bekommt eine Adresse. Laeuft dnsmasq, und steht"
      info "in $CONF die richtige Schnittstelle?"
    fi
  fi
else
  info "Ein zweiter DHCP-Server ist ohne Wurzelrechte nicht direkt zu"
  info "sehen -- der Rundruf braucht Port 68. Mit sudo geprueft:"
  info "  sudo bash pruefen.sh"
  # Der laufende Server merkt denselben Fehler indirekt: an Handys, die
  # mit einer Adresse ankommen, die nicht aus unserem Netz stammt.
  mit_python '
import json, os, sys, urllib.request
sys.path.insert(0, ".")
try:
    with urllib.request.urlopen(
            "http://127.0.0.1:%s/api/zustand" % os.environ.get("PRUEF_PORT", "8000"),
            timeout=5) as a:
        netz = (json.load(a).get("netz") or {})
except Exception:
    netz = None
if netz is None:
    pass
elif netz.get("fremde_adressen"):
    print("FEHL|Geraete mit fremden Adressen waren schon da: %s"
          % ", ".join(netz["fremde_adressen"]))
    print("INFO|Sie haben ihre Adresse nicht von uns. Am Zugangspunkt")
    print("INFO|ist DHCP noch eingeschaltet.")
else:
    print("OK|Der Server hat bisher kein Geraet mit fremder Adresse gesehen")
    print("INFO|Das ist ein Hinweis, kein Beweis: wer eine fremde Adresse")
    print("INFO|hat und uns deshalb gar nicht erreicht, faellt hier nicht")
    print("INFO|auf. Der sichere Weg ist sudo bash pruefen.sh.")
'
fi

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
    print("FEHL|Whisper %s nicht in %s. Holen mit: bash einrichten.sh"
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
    print("FEHL|Stimme fehlt fuer: %s. Holen mit: bash einrichten.sh"
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
  warn "Kein systemd. Dann wird von Hand gestartet: bash start.sh"
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
  warn "Server dann nicht von allein hoch. Einrichten mit: bash dienst.sh"
  warn "Wer nur entwickelt, braucht das nicht und nimmt bash start.sh"
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

# Laesst sich PortAudio ueberhaupt laden? Vor dieser Frage ist jede
# Geraeteliste sinnlos. Auf einem Rechner ohne angemeldete Sitzung gibt
# es keinen PulseAudio-Server, und ein PortAudio mit Pulse-Backend
# scheitert dann schon beim Import.
if [ -n "$PYJSON" ] && [ -f ton.py ]; then
  TONGRUND="$("$PYJSON" -c "
import sys; sys.path.insert(0, '.')
import ton
print('' if ton.da() else ton.grund())
" 2>/dev/null | tail -1)"
  if [ -z "${TONGRUND:-}" ]; then
    gut "PortAudio laedt"
  else
    fehl "PortAudio laedt nicht: ${TONGRUND}"
    info "Der Server laeuft trotzdem weiter, nimmt aber nichts auf."
    info "Haeufigste Ursache auf einem Rechner ohne Anmeldung: es gibt"
    info "keinen PulseAudio-Server. Siehe AUFSTELLEN.md, Abschnitt"
    info "\"Tonquelle ohne Sitzung\"."
  fi
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
    print("WARN|Der Dienst zaehlt womoeglich anders.")
    # Bis 0.2.11 stand hier "13 Geraete beim Dienst gegen 7 hier" --
    # ein Messwert vom alten Ubuntu, fest eingeschrieben. Auf CachyOS
    # waren es 13 gegen 13, und dann sagte die Zeile etwas Falsches
    # ueber genau den Rechner, vor dem jemand steht. Gemessen wird
    # jetzt, wenn ein Server laeuft; sonst wird gar keine Zahl genannt.
    if eigene is not None and vom_dienst is not None:
        if eigene == vom_dienst:
            print("INFO|Hier und beim Dienst je %d Geraete -- auf diesem"
                  % eigene)
            print("INFO|Rechner also gleich viele. Dass die NUMMERN"
                  " dieselben sind,")
            print("INFO|folgt daraus nicht: die Reihenfolge haengt an der"
                  " Aufzaehlung.")
        else:
            print("WARN|%d Geraete beim Dienst gegen %d hier -- also auch"
                  % (vom_dienst, eigene))
            print("WARN|andere Nummern.")
    else:
        print("INFO|Zum Vergleichen muss der Dienst laufen. Ohne ihn"
              " steht hier")
        print("INFO|nur die Zaehlung dieser Sitzung.")
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

# Der Server schickt seit 0.2.1 ein Wort statt eines fertigen Satzes:
# das Pult baut seine Meldung selbst, auf Deutsch oder Englisch. Hier
# liest ein Mensch an einer deutschen Konsole, also steht der deutsche
# Satz in dieser Datei.
TON_LAGE = {
    "nicht_lokal": "Der Ton kommt nicht vom Mikrofon dieses Rechners "
                   "(--datei).",
    "liste_unlesbar": "Die Geraeteliste ist nicht lesbar.",
    "kein_ton": "Das Geraet laeuft nicht, es kommt gerade kein Ton.",
    "warte_auf_geraet": "Wartet auf \"%s\". Es wird bewusst kein anderes "
                        "Geraet genommen. Ist das Mikrofon dauerhaft ein "
                        "anderes, am Pult unter Einrichtung auswaehlen.",
    "neu_geoeffnet": "Der Tonstrom war tot und wurde gerade neu geoeffnet.",
}
if antwort and antwort.get("lage"):
    satz = TON_LAGE.get(antwort["lage"], antwort["lage"])
    if "%s" in satz:
        satz = satz % (antwort.get("name") or "?")
    if antwort.get("einzelheit"):
        satz += " (%s)" % str(antwort["einzelheit"])[:80]
    print("WARN|Server meldet: %s" % satz[:200])

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
    print("INFO|(--datei).")
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
# Gezaehlt wird beides: was dieser Lauf sieht und was der Dienst sieht.
# Ohne laufenden Dienst bleibt vom_dienst None, und dann wird gar keine
# Zahl behauptet.
eigene = len(liste) if liste else None
vom_dienst = None
if antwort and isinstance(antwort.get("liste"), list):
    vom_dienst = len(antwort["liste"])
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
# ------------------------------------------------------- Systemcheck
# Dieselbe Pruefung, die der Server beim Start macht und als Nachricht
# ins Pult legt. Eine Stelle, zwei Anzeigen -- sonst laufen die beiden
# Listen frueher oder spaeter auseinander, und dann glaubt man der
# falschen.
blau "Rechner-Einstellungen"
mit_python '
import sys
sys.path.insert(0, ".")
import systemcheck

try:
    befunde = systemcheck.pruefen()
except Exception as e:
    print("WARN|Systemcheck fehlgeschlagen: %s" % str(e)[:90])
    befunde = None

if befunde is not None:
    if not befunde:
        print("OK|Alles eingestellt, wie es sein soll")
    for b in befunde:
        art = "FEHL" if b.schwere == systemcheck.FEHLT else "WARN"
        print("%s|%s" % (art, b.was))
        if b.tun:
            print("INFO|  %s" % b.tun)
'

blau "Sprechtempo"
# Seit 0.2.11 haengt das Tempo an der Stimme, nicht mehr an einer
# einzelnen Zahl. Bleibt der alte Name in einer von Hand gepflegten
# config.py stehen, wirkt er nicht mehr -- und das faellt im
# Gottesdienst nicht auf, weil nichts abstuerzt. Es klingt nur falsch.
mit_python '
import sys
sys.path.insert(0, ".")
import config

if hasattr(config, "LIVE_TEMPO"):
    print("FEHL|In config.py steht noch LIVE_TEMPO = %s." % config.LIVE_TEMPO)
    print("INFO|Der Wert wirkt seit 0.2.11 NICHT mehr. Das Tempo steht in")
    print("INFO|TEMPO_STIMME, TEMPO_SPRACHE und TEMPO_VORGABE -- je Stimme,")
    print("INFO|weil zwei Stimmen derselben Sprache bis zu 0,38 auseinander")
    print("INFO|liegen. Die Zeile kann weg.")
else:
    print("OK|Tempo je Stimme (LIVE_TEMPO ist abgeloest)")

je_stimme = getattr(config, "TEMPO_STIMME", {})
je_sprache = getattr(config, "TEMPO_SPRACHE", {})
if je_stimme:
    print("OK|%d Stimmen gemessen, %d Sprachen als Rueckfall"
          % (len(je_stimme), len(je_sprache)))
else:
    print("WARN|Keine gemessenen Stimmen eingetragen.")
    print("INFO|Alles laeuft auf TEMPO_VORGABE = %s. Das ist eine Schaetzung"
          % getattr(config, "TEMPO_VORGABE", "?"))
    print("INFO|und kein Messwert. Nachmessen mit:")
    print("INFO|  python laengenfaktor.py --je-stimme")

auf = getattr(config, "TEMPO_AUFSCHLAG", 1.0)
glob = getattr(config, "TEMPO_GLOBAL", 1.0)
print("INFO|Aufschlag %.2f, global %.2f, Grenzen %.2f bis %.2f"
      % (auf, glob, getattr(config, "TEMPO_MIN", 1.0),
         getattr(config, "TEMPO_MAX", 1.6)))
if abs(glob - 1.0) > 1e-6:
    print("WARN|Der globale Hebel steht nicht auf 1,00. Er hebt oder senkt")
    print("INFO|ALLE Sprachen auf einmal -- gedacht als Notbehelf, nicht als")
    print("INFO|Dauerzustand.")

# Was tatsaechlich herauskommt, je eingeschalteter Sprache. Eine Tabelle
# voller Zahlen sagt weniger als das Ergebnis.
hoch = [s for s in getattr(config, "ZIELSPRACHEN", [])]
for sp in hoch:
    name = config.STIMMEN.get(sp, "").split("/")[-1]
    wert = (je_stimme.get(name) or je_sprache.get(sp)
            or getattr(config, "TEMPO_VORGABE", 1.15))
    fertig = max(getattr(config, "TEMPO_MIN", 1.0),
                 min(getattr(config, "TEMPO_MAX", 1.6), wert * auf * glob))
    woher = ("Stimme" if name in je_stimme
             else "Sprache" if sp in je_sprache else "Vorgabe")
    print("INFO|  %-4s %-30s %.2f  (%s)" % (sp, name[:30], fertig, woher))
'

blau "Fassung"

if [ -f VERSION ]; then
  info "VERSION   $(cat VERSION)"
else
  warn "Keine VERSION-Datei. Am Pult steht dann \"unbekannt\"."
fi

if command -v git >/dev/null 2>&1 && [ -d .git ]; then
  info "Stand     $(git log -1 --format='%h %ad %s' --date=short 2>/dev/null | cut -c1-70)"
  if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
    warn "Lokale Aenderungen im Ordner. bash aktualisieren.sh bricht deshalb"
    warn "ab, statt sie zu ueberschreiben. Ansehen mit: git status"
  else
    gut "keine lokalen Aenderungen, bash aktualisieren.sh laeuft durch"
  fi
else
  warn "Kein Git-Ordner. bash aktualisieren.sh braucht einen."
fi

# ------------------------------------------------------- Update per Stick
# Auf einem Rechner ohne Netz ist das der einzige Weg, der noch geht.
# Deshalb gehoert in die Durchsicht, ob er ueberhaupt offensteht.
if [ -s schluessel.erlaubt ] \
   && grep -qE '^[^#[:space:]]+[[:space:]]+(ssh|sk-)' schluessel.erlaubt; then
  gut "schluessel.erlaubt: $(grep -cE '^[^#[:space:]]+[[:space:]]+(ssh|sk-)' schluessel.erlaubt) Schluessel eingetragen"
else
  warn "schluessel.erlaubt hat keinen Schluessel. Ein Update-Stick wird"
  warn "abgelehnt, egal was darauf liegt."
fi

if [ "$SYSTEMD" = ja ]; then
  if systemctl list-unit-files 2>/dev/null | grep -q "^$NAME-update\.timer"; then
    if systemctl is-active --quiet "$NAME-update.timer"; then
      gut "Update per Stick ist scharf (Timer laeuft)"
    else
      warn "Der Timer fuer Updates ist eingerichtet, laeuft aber nicht."
      warn "Anwerfen mit: sudo systemctl enable --now $NAME-update.timer"
    fi
  else
    warn "Update per Stick nicht eingerichtet. Ein eingesteckter Stick"
    warn "loest nichts aus. Nachholen mit: sudo bash dienst.sh --stick"
  fi
fi

if [ -s update/stand.json ]; then
  # [^"]* und nicht .*: mit .* frisst der Ausdruck bis zum letzten
  # Anfuehrungszeichen der Zeile und nimmt den Zeitstempel mit.
  info "Letztes Update:"
  sed -n 's/.*"text"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/   \1/p' \
      update/stand.json | head -1
fi
if [ -s update/bereit ]; then
  warn "Vorgemerkt: Fassung $(tr -d '\r\n ' < update/bereit). Wird"
  warn "eingespielt, wenn 20 Minuten nichts laeuft und niemand verbunden"
  warn "ist, oder sofort am Pult unter Einrichtung."
fi

# ------------------------------------------------------ Reparaturvorrat
# Ein Vorrat, den niemand ansieht, ist an dem Tag kaputt, an dem er
# gebraucht wird. Deshalb gehoert er in jede Durchsicht -- und nicht
# nur die Frage, ob er daliegt, sondern ob er noch zu dem passt, was
# hier laeuft.
blau "Reparaturvorrat"
VORRAT="${DEVARENU_VORRAT:-/opt/devarenu-vorrat}"
if [ -z "$PYJSON" ]; then
  warn "Ohne Python laesst sich vorrat.json nicht lesen."
elif [ ! -f "$VORRAT/vorrat.json" ]; then
  warn "Kein Vorrat unter $VORRAT."
  warn "Ohne ihn laesst sich hier nichts wiederherstellen -- dieser"
  warn "Rechner hat kein Netz. Beim naechsten Besuch mit Leitung:"
  warn "  sudo bash vorrat_bauen.sh"
else
  V_FASSUNG="$("$PYJSON" -c "import json;print(json.load(open('$VORRAT/vorrat.json')).get('fassung','?'))" 2>/dev/null)"
  V_PYTHON="$("$PYJSON" -c "import json;print(json.load(open('$VORRAT/vorrat.json')).get('python','?'))" 2>/dev/null)"
  V_GEBAUT="$("$PYJSON" -c "import json;print(json.load(open('$VORRAT/vorrat.json')).get('gebaut','?'))" 2>/dev/null)"
  gut "Vorrat vorhanden, $(du -sh "$VORRAT" 2>/dev/null | cut -f1), gebaut $V_GEBAUT"

  # Passt er noch zur installierten Fassung?
  HIER_FASSUNG="$(tr -d '\r' < VERSION 2>/dev/null | head -1 | tr -d ' ')"
  if [ "$V_FASSUNG" = "$HIER_FASSUNG" ]; then
    info "gehoert zu Fassung $V_FASSUNG, wie installiert"
  else
    warn "Der Vorrat gehoert zu Fassung $V_FASSUNG, installiert ist"
    warn "$HIER_FASSUNG. Die Pakete darin koennen veraltet sein."
    warn "Beim naechsten Besuch mit Netz neu bauen."
  fi

  # Passt er noch zum Python der venv? Nur die zaehlt -- dorthin
  # werden die Wheels installiert. Fehlt die venv, gibt es nichts zu
  # vergleichen, und ihr Fehlen steht schon weiter oben.
  if [ -x "$PY" ]; then
    HIER_PYTHON="$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null)"
    if [ -n "$V_PYTHON" ] && [ "$V_PYTHON" != "$HIER_PYTHON" ]; then
      warn "Pakete im Vorrat sind fuer Python $V_PYTHON, die venv laeuft"
      warn "auf $HIER_PYTHON. wiederherstellen.sh --pakete bricht ab."
    fi
  fi

  # Und ist er heil? Das ist die eigentliche Frage.
  if [ -f "$VORRAT/pruefsummen.sha256" ]; then
    if ( cd "$VORRAT" && sha256sum --quiet -c pruefsummen.sha256 >/dev/null 2>&1 ); then
      gut "Pruefsummen stimmen ($(wc -l < "$VORRAT/pruefsummen.sha256") Dateien)"
    else
      KAPUTT="$( cd "$VORRAT" && sha256sum -c pruefsummen.sha256 2>/dev/null \
                 | grep -cv ': OK$' )"
      fehl "$KAPUTT Datei(en) im Vorrat stimmen nicht mit ihrer Pruefsumme"
      fehl "ueberein. Wiederherstellen wuerde abbrechen."
      info "Nachsehen:  cd $VORRAT && sha256sum -c pruefsummen.sha256 | grep -v OK"
    fi
  else
    warn "pruefsummen.sha256 fehlt. Ob der Vorrat heil ist, laesst sich"
    warn "nicht sagen."
  fi
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
     bash pruefen.sh > bericht.txt 2>&1

ENDE

[ $N_FEHL -gt 0 ] && exit 1
exit 0
