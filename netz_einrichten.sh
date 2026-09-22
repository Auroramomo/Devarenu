#!/usr/bin/env bash
# Macht den Gemeinderechner zum Router fuer das Saalnetz.
#
#   sudo ./netz_einrichten.sh --trocken       nur zeigen, nichts schreiben
#   sudo ./netz_einrichten.sh                 einrichten
#   sudo ./netz_einrichten.sh --zuruecknehmen alles rueckgaengig
#   sudo ./netz_einrichten.sh --trotzdem      Pruefung des Rechners uebergehen
#
# NUR VON HAND, NUR VOR ORT, NUR AN DER TASTATUR DES RECHNERS.
#
# Dieses Skript wird von stick_update.sh und bootstrap.sh NICHT
# aufgerufen und darf es nie werden. Ein Update, das das Netz umbaut,
# kann den Rechner unerreichbar machen -- und dann hilft auch kein
# Stick mehr, weil niemand mehr hinkommt.
#
# Aus demselben Grund warnt es, wenn es ueber eine Fernsitzung
# aufgerufen wird: der Umbau kappt genau die Verbindung, ueber die man
# gerade zusieht.
#
# Und aus demselben Grund sieht es nach, ob es ueberhaupt auf einem
# Gemeinderechner steht. Dieses Verzeichnis liegt auch auf dem
# Arbeitsrechner, auf dem Devarenu entsteht; dort waere ein scharfer
# Lauf teuer. Der Rechnername muss darum in config.py unter
# NETZ_RECHNER stehen, und der Aufbau des Netzes muss passen. Beides
# laesst sich mit --trotzdem uebergehen, aber nur ausdruecklich.
#
# WAS ES TUT
#   - feste Adresse auf der LAN-Schnittstelle
#   - dnsmasq als DHCP- und DNS-Dienst
#   - die Pruefnamen der Hersteller auf diesen Rechner, alles andere
#     unaufloesbar
#   - DHCP-Option 114 auf die Captive-Portal-API des Servers
#   - NETZ_ROUTER in config.py einschalten
#
# WAS ES NICHT TUT
#   - kein NAT, kein Gateway, keine Weiterleitung. Der Saal hat kein
#     Internet und soll keines bekommen.

set -u
ORDNER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ORDNER"

TROCKEN=nein
ZURUECK=nein
TROTZDEM=nein
SCHNITTSTELLE=""

blau() { printf '\n\033[1;34m== %s\033[0m\n' "$*"; }
gut()  { printf '   \033[32mok\033[0m    %s\n' "$*"; }
warn() { printf '   \033[33m!\033[0m     %s\n' "$*"; }
fehl() { printf '   \033[31mFEHLT\033[0m %s\n' "$*"; }
info() { printf '         %s\n' "$*"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --trocken)        TROCKEN=ja; shift ;;
    --zuruecknehmen)  ZURUECK=ja; shift ;;
    --trotzdem)       TROTZDEM=ja; shift ;;
    --schnittstelle)  SCHNITTSTELLE="${2:-}"; shift 2 ;;
    -h|--hilfe)       sed -n '2,37p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)                fehl "Unbekannt: $1"; exit 1 ;;
  esac
done

PY="$ORDNER/.venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"
[ -x "$PY" ] || { fehl "Kein Python gefunden."; exit 1; }

lies_config() { "$PY" -c "import config; print(getattr(config, '$1', ''))"; }
ADRESSE="$(lies_config NETZ_ADRESSE)"
MASKE="$(lies_config NETZ_MASKE)"
VON="$("$PY" -c 'import config; print(config.NETZ_BEREICH[0])')"
BIS="$("$PY" -c 'import config; print(config.NETZ_BEREICH[1])')"
MIETE="$(lies_config NETZ_MIETE)"
NETZ="$("$PY" -c "
import ipaddress, config
print(ipaddress.ip_network(f'{config.NETZ_ADRESSE}/{config.NETZ_MASKE}',
                           strict=False))")"

CONF=/etc/dnsmasq.d/devarenu.conf
NMPROFIL=devarenu-lan

# ------------------------------------------------------- Fernsitzung?
# Ueber sudo allein reicht SSH_CONNECTION nicht: sudo raeumt die
# Umgebung auf, und dann saehe der Aufruf aus wie einer an der
# Tastatur. Deshalb mehrere Wege, und einer genuegt.
fernsitzung() {
  [ -n "${SSH_CONNECTION:-}${SSH_CLIENT:-}${SSH_TTY:-}" ] && return 0
  [ -n "${SUDO_USER:-}" ] && [ -n "$(who am i 2>/dev/null | grep -oE '\([^)]+\)')" ] \
    && return 0
  who am i 2>/dev/null | grep -qE '\(([0-9]{1,3}\.){3}[0-9]{1,3}\)' && return 0
  # Der Elternbaum: sudo haengt unter dem Login-Prozess der Sitzung.
  local pid=$PPID n=0
  while [ "$pid" -gt 1 ] && [ $n -lt 12 ]; do
    case "$(ps -o comm= -p "$pid" 2>/dev/null)" in
      sshd|sshd-session|mosh-server) return 0 ;;
    esac
    pid="$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' ')"
    [ -n "${pid:-}" ] || break
    n=$((n+1))
  done
  return 1
}

blau "Netzumbau"
if fernsitzung; then
  printf '\n   \033[31mDu sitzt an einer Fernverbindung.\033[0m\n\n'
  info "Dieser Umbau stellt die Netzwerkschnittstelle um. Er kappt damit"
  info "genau die Verbindung, ueber die du gerade zusiehst -- und der"
  info "Rechner ist danach unter der alten Adresse nicht mehr da."
  info ""
  info "Geh an die Tastatur des Rechners. Wenn du sicher bist, dass du"
  info "trotzdem weitermachen willst:"
  info "  DEVARENU_TROTZDEM=ja sudo ./netz_einrichten.sh"
  if [ "${DEVARENU_TROTZDEM:-}" != "ja" ]; then
    exit 1
  fi
  warn "DEVARENU_TROTZDEM=ja gesetzt. Auf eigene Gefahr."
fi

# ------------------------------------------------- Schnittstelle finden
# Nie ein fester Name. USB-Ethernet heisst je nach Anschluss anders, und
# ein fest verdrahtetes "eth0" trifft dann die falsche Karte oder keine.
# Gesucht wird die kabelgebundene Schnittstelle mit Verbindung.
if [ -z "$SCHNITTSTELLE" ]; then
  for k in /sys/class/net/*; do
    name="$(basename "$k")"
    [ "$name" = "lo" ] && continue
    [ -d "$k/wireless" ] && continue          # WLAN nicht, siehe AUFSTELLEN.md
    [ -e "$k/device" ] || continue            # keine virtuellen
    if [ "$(cat "$k/carrier" 2>/dev/null)" = "1" ]; then
      SCHNITTSTELLE="$name"; break
    fi
    [ -z "$SCHNITTSTELLE" ] && SCHNITTSTELLE="$name"
  done
fi
if [ -z "$SCHNITTSTELLE" ]; then
  fehl "Keine kabelgebundene Schnittstelle gefunden."
  info "Haengt das LAN-Kabel zum Zugangspunkt?"
  info "Mit --schnittstelle <name> laesst sie sich vorgeben."
  exit 1
fi
gut "Schnittstelle $SCHNITTSTELLE"
info "Verbindung: $([ "$(cat /sys/class/net/$SCHNITTSTELLE/carrier 2>/dev/null)" = 1 ] \
     && echo "Kabel steckt" || echo "KEIN KABEL -- der Zugangspunkt haengt nicht dran")"

# ------------------------------------------- Gehoert der Rechner hierher?
# Zwei Fragen: heisst dieser Rechner so, wie ein Gemeinderechner heissen
# soll, und sieht das Netz so aus, wie es vor dem Umbau aussehen muss?
# Jeder Befund wird genannt, auch wenn schon einer davor steht -- wer
# einmal hinsieht, soll alles auf einmal sehen.
ABWEICHUNG=0
passt_nicht() { ABWEICHUNG=$((ABWEICHUNG+1)); fehl "$1"; }

blau "Gehoert dieser Rechner hierher?"

RECHNER="$(hostname 2>/dev/null || cat /etc/hostname 2>/dev/null)"
NAMEPASST="$("$PY" - "$RECHNER" <<'PYCODE'
import fnmatch, sys
import config
name = (sys.argv[1] or "").strip().lower()
muster = [str(m).strip().lower()
          for m in getattr(config, "NETZ_RECHNER", []) if str(m).strip()]
if not muster:
    print("leer")
elif any(fnmatch.fnmatch(name, m) for m in muster):
    print("ja")
else:
    print("nein")
PYCODE
)"
case "$NAMEPASST" in
  ja)
    gut "Rechnername $RECHNER steht in NETZ_RECHNER" ;;
  leer)
    passt_nicht "NETZ_RECHNER in config.py ist leer."
    info "Leer heisst absichtlich: nirgendwo. Der Umbau stellt die"
    info "Netzwerkkarte um; welcher Rechner das sein darf, muss dastehen."
    info "Auf DIESEM Rechner waere das:"
    info "  NETZ_RECHNER = [\"$RECHNER\"]" ;;
  *)
    passt_nicht "Rechnername $RECHNER steht nicht in NETZ_RECHNER."
    info "In config.py stehen: $("$PY" -c 'import config; print(", ".join(config.NETZ_RECHNER) or "--")')"
    info "Ist das hier wirklich der Gemeinderechner?" ;;
esac

# Mehr als eine Leitung mit Stecker: dann ist nicht zu entscheiden,
# welche die zum Zugangspunkt ist, und die falsche umzustellen kostet
# den Rechner sein Netz.
MIT_KABEL=""
for k in /sys/class/net/*; do
  n="$(basename "$k")"
  [ "$n" = "lo" ] && continue
  [ -d "$k/wireless" ] && continue
  [ -e "$k/device" ] || continue
  [ "$(cat "$k/carrier" 2>/dev/null)" = "1" ] && MIT_KABEL="$MIT_KABEL $n"
done
ANZ_KABEL="$(set -- $MIT_KABEL; echo $#)"
if [ "$ANZ_KABEL" = "1" ]; then
  gut "genau eine Leitung mit Stecker:$MIT_KABEL"
elif [ "$ANZ_KABEL" = "0" ]; then
  passt_nicht "Keine Leitung mit Stecker."
  info "Das Kabel zum Zugangspunkt steckt nicht. Vor dem Umbau"
  info "einstecken -- sonst richtet sich hier etwas ein, das niemand"
  info "erreicht."
else
  passt_nicht "Mehrere Leitungen mit Stecker:$MIT_KABEL"
  info "Welche zum Zugangspunkt fuehrt, ist von hier nicht zu sehen."
  info "Die falsche umzustellen nimmt dem Rechner sein Netz."
  info "Mit --schnittstelle <name> vorgeben."
fi

# WLAN verbunden: der Gemeinderechner haengt am Kabel. Das Mainboard-WLAN
# wird bewusst nicht benutzt (2,4 GHz, acht bis zwoelf Geraete). Ein
# verbundenes WLAN ist deshalb das Kennzeichen eines anderen Rechners.
WLANDRAN="$(nmcli -t -f TYPE,STATE device 2>/dev/null \
            | awk -F: '$1=="wifi" && $2=="connected"' | wc -l)"
if [ "${WLANDRAN:-0}" -gt 0 ]; then
  passt_nicht "Dieser Rechner haengt im WLAN."
  info "Der Gemeinderechner haengt am Kabel; sein eigenes WLAN bleibt"
  info "aus. Siehe AUFSTELLEN.md."
else
  gut "kein WLAN verbunden"
fi

# Virtuelle Bruecken: docker0, virbr0, br-*. Ein Gemeinderechner hat
# keine. Ein Arbeitsrechner schon -- und genau den soll das hier nicht
# umbauen.
BRUECKEN=""
for k in /sys/class/net/*; do
  n="$(basename "$k")"
  case "$n" in
    docker0|virbr*|br-*|vmnet*) BRUECKEN="$BRUECKEN $n" ;;
  esac
done
if [ -n "$BRUECKEN" ]; then
  passt_nicht "Virtuelle Netzwerkbruecken vorhanden:$BRUECKEN"
  info "Das sieht nach einem Arbeitsrechner aus, nicht nach dem"
  info "Rechner in der Gemeinde."
else
  gut "keine virtuellen Bruecken"
fi

# NetworkManager muss die Schnittstelle fuehren, sonst laeuft das
# angelegte Profil ins Leere und der Umbau meldet Erfolg ohne Wirkung.
NMZUSTAND="$(nmcli -t -f DEVICE,STATE device 2>/dev/null \
             | awk -F: -v d="$SCHNITTSTELLE" '$1==d {print $2}')"
case "${NMZUSTAND:-}" in
  "")            passt_nicht "NetworkManager kennt $SCHNITTSTELLE nicht."
                 info "Ohne ihn hat das angelegte Profil keine Wirkung."
                 info "Nachsehen mit: nmcli device status" ;;
  unmanaged)     passt_nicht "NetworkManager fuehrt $SCHNITTSTELLE nicht (unmanaged)."
                 info "Das angelegte Profil wuerde nichts bewirken." ;;
  *)             gut "NetworkManager fuehrt $SCHNITTSTELLE ($NMZUSTAND)" ;;
esac

# Verteilt hier schon jemand Adressen? Dann haengt der Rechner im
# Hausnetz und nicht am Zugangspunkt des Saals -- und der Umbau waere
# der falsche Schritt an der falschen Dose.
if [ "$(id -u)" = "0" ]; then
  UMSCHAU="$("$PY" "$ORDNER/dhcp_umschau.py" "$SCHNITTSTELLE" 4 2>/dev/null)"
  FREMDE="$(printf '%s\n' "$UMSCHAU" | awk -F'|' '$1=="SERVER"{print $2}' \
            | grep -v "^$ADRESSE$")"
  if [ -n "$FREMDE" ]; then
    passt_nicht "Auf $SCHNITTSTELLE verteilt schon jemand Adressen: $(echo $FREMDE)"
    info "Entweder steckt das Kabel im Hausnetz statt am Zugangspunkt,"
    info "oder am Zugangspunkt ist DHCP noch eingeschaltet. Beides muss"
    info "vor dem Umbau geklaert sein: zwei DHCP-Server im selben Netz"
    info "sind genau der Fehler, den dieser Umbau beheben soll."
  else
    gut "niemand sonst verteilt Adressen auf $SCHNITTSTELLE"
  fi
else
  info "Ohne Wurzelrechte nicht zu sehen, ob hier schon jemand Adressen"
  info "verteilt. Mit sudo aufgerufen wird auch das geprueft."
fi

# Kein Abbruchgrund, aber es muss dastehen: der Rechner verliert sein
# Internet. Genau das ist beabsichtigt -- ueberraschen darf es nicht.
if ip -4 route show default 2>/dev/null | grep -q "dev $SCHNITTSTELLE"; then
  warn "Ueber $SCHNITTSTELLE laeuft zurzeit der Weg ins Internet."
  info "Nach dem Umbau ist er weg: kein Gateway, kein NAT, kein Draussen."
  info "Updates brauchen danach den Stick. So ist es gewollt."
fi

if [ "$ABWEICHUNG" -gt 0 ]; then
  echo
  if [ "$TROCKEN" = "ja" ]; then
    warn "$ABWEICHUNG Abweichung(en). Scharf wuerde hier abgebrochen."
  elif [ "$TROTZDEM" = "ja" ]; then
    warn "$ABWEICHUNG Abweichung(en), uebergangen mit --trotzdem."
    warn "Auf eigene Gefahr."
  else
    fehl "$ABWEICHUNG Abweichung(en). Es wird nichts geaendert."
    info "Dieser Rechner sieht nicht aus wie der, fuer den das gedacht"
    info "ist. Erst nachsehen, dann entscheiden. Wenn es wirklich der"
    info "richtige ist:"
    info "  sudo ./netz_einrichten.sh --trotzdem"
    exit 1
  fi
fi

# --------------------------------------------------------- Zuruecknehmen
if [ "$ZURUECK" = "ja" ]; then
  blau "Zuruecknehmen"
  [ "$TROCKEN" = "ja" ] && { info "Wuerde $CONF loeschen, das NM-Profil"
                             info "$NMPROFIL entfernen und NETZ_ROUTER"
                             info "ausschalten."; exit 0; }
  rm -f "$CONF" && gut "$CONF geloescht"
  systemctl restart dnsmasq 2>/dev/null || systemctl stop dnsmasq 2>/dev/null
  nmcli con delete "$NMPROFIL" >/dev/null 2>&1 && gut "NM-Profil entfernt"
  "$PY" - <<'PYCODE'
import io, re
p = "config.py"
s = io.open(p, encoding="utf-8").read()
s = re.sub(r"^NETZ_ROUTER = True$", "NETZ_ROUTER = False", s, flags=re.M)
io.open(p, "w", encoding="utf-8").write(s)
print("   ok    NETZ_ROUTER = False")
PYCODE
  info "Der Dienst muss neu starten:  sudo systemctl restart devarenu"
  exit 0
fi

# ------------------------------------------------------------ dnsmasq da?
if ! command -v dnsmasq >/dev/null; then
  fehl "dnsmasq ist nicht installiert."
  info "Vor Ort gibt es kein Netz zum Nachinstallieren. Entweder aus dem"
  info "Reparaturvorrat:"
  info "  sudo dpkg -i /opt/devarenu-vorrat/pakete/*.deb"
  info "oder beim Systemhaus mit Leitung:  sudo apt-get install dnsmasq"
  exit 1
fi
gut "dnsmasq $(dnsmasq --version 2>/dev/null | head -1 | awk '{print $3}')"

# --------------------------------------------------------- Konfiguration
ENTWURF="$(mktemp)"
trap 'rm -f "$ENTWURF"' EXIT
{
  echo "# Von netz_einrichten.sh erzeugt. Nicht von Hand aendern --"
  echo "# was hier steht, kommt aus config.py."
  echo "#"
  echo "# Der Rechner ist Router fuer das Saalnetz: DHCP und DNS. Kein"
  echo "# NAT, kein Gateway, kein Weg nach draussen."
  echo
  echo "interface=$SCHNITTSTELLE"
  echo "bind-interfaces"
  echo "except-interface=lo"
  echo
  echo "# DHCP. Ohne Gateway (Option 3 leer) und ohne fremden DNS:"
  echo "# ein Gateway, das nirgendwohin fuehrt, laesst Handys in"
  echo "# Zeitueberschreitungen laufen."
  echo "dhcp-range=$VON,$BIS,$MIETE"
  echo "dhcp-option=3"
  echo "dhcp-option=6,$ADRESSE"
  echo
  echo "# Captive Portal API, RFC 8910. Wird nur geliefert, wenn das"
  echo "# Geraet Option 114 anfragt -- iOS ab 14, Android ab 11"
  echo "# teilweise. Wer nicht fragt, bekommt sie nicht."
  "$PY" -c "import config; print('' if config.NETZ_CAPTIVE_API else '#', end='')"
  echo "dhcp-option=114,http://$ADRESSE/captive-api"
  echo
  echo "# Kein Weiterleiten nach draussen: es gibt kein Draussen."
  echo "no-resolv"
  echo "no-poll"
  echo
  echo "# Die Pruefnamen der Hersteller zeigen auf uns. ALLES ANDERE"
  echo "# bleibt unaufloesbar. Ein Platzhalter fuer alle Namen wuerde"
  echo "# jedes Handy im Saal betreffen, auch die, die gar nicht"
  echo "# mithoeren: ihre Hintergrunddienste bekaemen einen Server, der"
  echo "# nicht antwortet, und wiederholten ihre Anfragen bis zum"
  echo "# leeren Akku. NXDOMAIN ist die ehrliche Auskunft."
  "$PY" -c "
import config
for d in config.PRUEFDOMAENEN:
    print(f'address=/{d}/{config.NETZ_ADRESSE}')"
  echo
  echo "# Der eigene Name, damit 'devarenu' im Browser reicht."
  echo "address=/devarenu/$ADRESSE"
  echo "address=/devarenu.lan/$ADRESSE"
} > "$ENTWURF"

blau "dnsmasq-Konfiguration"
sed 's/^/   /' "$ENTWURF"

if ! dnsmasq --test --conf-file="$ENTWURF" 2>&1 | sed 's/^/   /'; then
  fehl "dnsmasq lehnt die Konfiguration ab. Es wird nichts geschrieben."
  exit 1
fi

blau "Netzwerk"
info "Schnittstelle $SCHNITTSTELLE bekommt $ADRESSE/$MASKE"
info "Netz          $NETZ, DHCP $VON bis $BIS"
info "Weiterleitung bleibt aus (kein NAT, kein Gateway)"

if [ "$TROCKEN" = "ja" ]; then
  blau "Trockenlauf"
  info "Es wurde NICHTS geschrieben und nichts umgestellt."
  info "Ohne --trocken wuerde jetzt:"
  info "  $CONF angelegt"
  info "  NM-Profil \"$NMPROFIL\" auf $SCHNITTSTELLE gesetzt"
  info "  dnsmasq neu gestartet"
  info "  NETZ_ROUTER = True in config.py"
  info "  ./firewall.sh aufgerufen"
  exit 0
fi

# --------------------------------------------------------------- Schreiben
printf '\n   Jetzt wirklich umbauen? Die Verbindung dieses Rechners aendert sich. [j/N] '
read -r antwort
case "${antwort:-n}" in [jJyY]*) ;; *) info "Abgebrochen."; exit 0 ;; esac

mkdir -p /etc/dnsmasq.d
install -m 644 "$ENTWURF" "$CONF" && gut "$CONF geschrieben"

# Feste Adresse ueber NetworkManager, ohne shared-Modus: der schaltet
# NAT und ip_forward ein, und beides wollen wir ausdruecklich nicht.
if command -v nmcli >/dev/null; then
  nmcli con delete "$NMPROFIL" >/dev/null 2>&1 || true
  if nmcli con add type ethernet ifname "$SCHNITTSTELLE" con-name "$NMPROFIL" \
       ipv4.method manual ipv4.addresses "$ADRESSE/$MASKE" \
       ipv4.never-default yes ipv6.method disabled \
       connection.autoconnect yes >/dev/null 2>&1; then
    nmcli con up "$NMPROFIL" >/dev/null 2>&1
    gut "NM-Profil \"$NMPROFIL\" auf $SCHNITTSTELLE"
    info "ipv6.method=disabled: ohne Router im Netz gibt es keine Router"
    info "Advertisements, und damit auch kein IPv6-DNS, das uns umgeht."
  else
    warn "nmcli hat das Profil nicht angelegt. Adresse von Hand setzen:"
    warn "  sudo ip addr add $ADRESSE/$MASKE dev $SCHNITTSTELLE"
  fi
else
  warn "Kein nmcli. Adresse von Hand setzen:"
  warn "  sudo ip addr add $ADRESSE/$MASKE dev $SCHNITTSTELLE"
fi

# Weiterleitung ausdruecklich aus.
sysctl -w net.ipv4.ip_forward=0 >/dev/null 2>&1 && gut "ip_forward = 0"

systemctl enable --now dnsmasq >/dev/null 2>&1
if systemctl restart dnsmasq 2>/dev/null; then
  gut "dnsmasq laeuft"
else
  fehl "dnsmasq startet nicht. Nachsehen:  journalctl -u dnsmasq -n 30"
  info "Haeufigste Ursache: systemd-resolved haelt Port 53."
  info "  sudo systemctl disable --now systemd-resolved"
fi

"$PY" - <<'PYCODE'
import io, re
p = "config.py"
s = io.open(p, encoding="utf-8").read()
neu = re.sub(r"^NETZ_ROUTER = False$", "NETZ_ROUTER = True", s, flags=re.M)
if neu == s and "NETZ_ROUTER = True" not in s:
    raise SystemExit("   FEHLT NETZ_ROUTER nicht gefunden")
io.open(p, "w", encoding="utf-8").write(neu)
print("   ok    NETZ_ROUTER = True")
PYCODE

[ -f firewall.sh ] && bash ./firewall.sh --netz "$NETZ" 2>/dev/null

blau "Fertig"
info "Der Dienst muss neu starten:"
info "  sudo systemctl restart devarenu"
info "Danach nachsehen:"
info "  ./pruefen.sh          Abschnitt Netz"
info "  http://$ADRESSE/pult"
