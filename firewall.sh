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
#   FW_NETZ    das Teilnetz dieses Rechners, z.B. 192.168.178.0/24
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
