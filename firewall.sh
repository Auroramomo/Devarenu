#!/usr/bin/env bash
# Erkennt, ob eine Firewall den Port sperrt. Zum Einbinden gedacht:
#
#   . ./firewall.sh
#   firewall_lage 8000
#
# Danach stehen drei Variablen bereit:
#
#   FW_ART     leer = nichts zu tun (keine sperrende Firewall, oder die
#              Regel gibt es schon). Sonst "ufw" oder "firewalld".
#   FW_NETZ    das Teilnetz dieses Rechners, z.B. 10.0.0.0/24
#   FW_BEFEHL  der fertige Befehl zum Freigeben, mit genau diesem Netz
#
# Eine gemeinsame Datei und nicht zweimal derselbe Code in
# INSTALLIEREN.sh und pruefen.sh: zwei Fassungen derselben Erkennung
# laufen irgendwann auseinander, und dann sagt der Installer etwas
# anderes als die Durchsicht.
#
# Braucht kein sudo. Die UFW-Regeldateien liegen mit 644, und das
# Teilnetz steht in der Routentabelle.

# Das Teilnetz, in dem die Handys haengen. Bewusst aus diesem Rechner
# und nicht aus einer abgetippten Zeile: eine Regel fuer ein fremdes
# Teilnetz ist syntaktisch tadellos und passt auf niemanden. Der Fehler
# faellt dann erst im Gottesdienst auf.
firewall_netz() {
  local geraet netz
  # Bevorzugt die Karte mit der Standardroute. Ein geschlossenes
  # Gemeindenetz hat keine; dann die erste mit globaler Adresse.
  geraet="$(ip -4 route show default 2>/dev/null | awk 'NR==1{print $5}')"
  [ -n "${geraet:-}" ] || \
    geraet="$(ip -4 -o addr show scope global 2>/dev/null | awk 'NR==1{print $2}')"
  [ -n "${geraet:-}" ] || return 1
  netz="$(ip -4 route show scope link dev "$geraet" 2>/dev/null | awk 'NR==1{print $1}')"
  [ -n "${netz:-}" ] || return 1
  printf '%s' "$netz"
}

firewall_lage() {
  local port="${1:-8000}"
  FW_ART=""; FW_NETZ=""; FW_BEFEHL=""

  FW_NETZ="$(firewall_netz)" || return 0

  # ---- ufw ----
  if [ -r /etc/ufw/ufw.conf ] && grep -q '^ENABLED=yes' /etc/ufw/ufw.conf 2>/dev/null; then
    # Sperrt sie eingehend ueberhaupt? Steht die Richtlinie auf ACCEPT,
    # ist nichts zu tun.
    grep -qE '^DEFAULT_INPUT_POLICY="(DROP|REJECT)"' /etc/default/ufw 2>/dev/null || return 0
    # Gibt es die Regel schon? Das abschliessende Leerzeichen verhindert,
    # dass "--dport 8000" auch auf 80001 passt. Portbereiche (--dports
    # a:b) werden nicht ausgewertet; dass ein Bereich genau diesen Port
    # abdeckt, ist der seltenere Fall als gar keine Regel.
    grep -qs -- "--dport $port " /etc/ufw/user.rules /etc/ufw/user6.rules && return 0
    FW_ART="ufw"
    FW_BEFEHL="sudo ufw allow from $FW_NETZ to any port $port proto tcp comment \"Devarenu LAN\""
    return 0
  fi

  # ---- firewalld ----
  # Nur erkannt, nicht ausgefuehrt: hier war keins zum Ausprobieren, und
  # ungetestete Firewallbefehle gehoeren nicht auf einen fremden Rechner.
  if systemctl is-active --quiet firewalld 2>/dev/null; then
    FW_ART="firewalld"
    FW_BEFEHL="sudo firewall-cmd --permanent --add-rich-rule='rule family=ipv4 source address=$FW_NETZ port port=$port protocol=tcp accept' && sudo firewall-cmd --reload"
    return 0
  fi

  return 0
}

# ---------------------------------------------------------------- Regeln
# Direkt aufgerufen statt eingebunden: dann setzt dieses Skript die
# Regeln fuer den Saalbetrieb. Eingebunden (". firewall.sh") passiert
# hier nichts -- pruefen.sh und dienst.sh nutzen nur die Funktionen oben.
firewall_saal() {
  local netz="${1:-}"
  [ -n "$netz" ] || netz="$(firewall_netz)" || {
    echo "   Kein Teilnetz gefunden. Mit --netz 10.0.0.0/24 vorgeben." >&2
    return 1; }

  if ! command -v ufw >/dev/null; then
    echo "   ufw ist nicht installiert. Regeln von Hand setzen:" >&2
    echo "     53/tcp 53/udp 67/udp 80/tcp 8000/tcp 22/tcp aus $netz" >&2
    return 1
  fi

  echo "   Regeln fuer $netz"
  # DNS und DHCP kommen dazu, weil dieser Rechner sie jetzt selbst
  # anbietet. 80 fuer die Handys, 8000 wie bisher, 22 fuer die Technik.
  local regel
  for regel in "53 tcp" "53 udp" "67 udp" "80 tcp" "8000 tcp" "22 tcp"; do
    set -- $regel
    sudo ufw allow from "$netz" to any port "$1" proto "$2" \
         comment "Devarenu Saal" >/dev/null 2>&1 \
      && echo "      $1/$2" \
      || echo "      $1/$2 FEHLGESCHLAGEN" >&2
  done

  # Weiterleitung aus. Der Saal hat kein Internet und soll keines
  # bekommen -- weder durch NAT noch durch einen zweiten Weg.
  sudo ufw default deny routed >/dev/null 2>&1 \
    && echo "      Weiterleitung aus" \
    || echo "      Weiterleitung liess sich nicht abschalten" >&2
}

# Nur wenn direkt gestartet, nicht beim Einbinden.
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
  NETZ=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --netz) NETZ="${2:-}"; shift 2 ;;
      *) echo "Unbekannt: $1" >&2; exit 1 ;;
    esac
  done
  firewall_saal "$NETZ"
fi
