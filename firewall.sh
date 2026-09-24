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
  # An die SCHNITTSTELLE, nicht an ein Teilnetz. Der Unterschied hat
  # den Gemeinderechner eine Installation gekostet:
  #
  # Bis 0.2.11 hiess es "ufw allow from <teilnetz>", und das Teilnetz
  # ermittelte firewall_netz aus der Adresse, die der Rechner GERADE
  # hatte. Bei der Installation hing er an einem WLAN-Hotspot, also
  # wurde Port 8000 fuer das WLAN geoeffnet. Nach dem Umbau lagen die
  # Handys im Saal in einem ganz anderen Netz und waren ausgesperrt.
  # Auf Ubuntu fiel das nie auf, weil ufw dort ab Werk aus ist; auf
  # CachyOS ist er an.
  #
  # Auf einem WLAN wird ueberhaupt nichts geoeffnet -- auch nicht das
  # Pult. Der Rechner hat im Betrieb kein Netz nach draussen, und was
  # dort offen stuende, koennte nur jemand erreichen, der nicht im Saal
  # sitzt.
  #
  # "allow in on <karte>" bindet die Freigabe an das Kabel zum
  # Zugangspunkt. Aendert sich die Adresse, bleibt die Regel richtig.
  local karte="${1:-}"
  if [ -z "$karte" ]; then
    echo "   Keine Schnittstelle angegeben. Aufruf:" >&2
    echo "     bash firewall.sh --schnittstelle enp5s0" >&2
    return 1
  fi

  if ! command -v ufw >/dev/null; then
    echo "   ufw ist nicht installiert. Regeln von Hand setzen:" >&2
    echo "     53/tcp 53/udp 67/udp 80/tcp 8000/tcp -- nur auf $karte" >&2
    return 1
  fi

  echo "   Regeln auf $karte"
  # DNS und DHCP kommen dazu, weil dieser Rechner sie jetzt selbst
  # anbietet. 80 fuer die Handys, 8000 wie bisher.
  #
  # 22/tcp ist NICHT dabei, anders als bis 0.2.11. Es stand fuer jedes
  # Handy im Saal offen -- eine Einladung, die niemand brauchte. Die
  # Wartung passiert an der Tastatur des Rechners.
  local regel
  for regel in "53 tcp" "53 udp" "67 udp" "80 tcp" "8000 tcp"; do
    set -- $regel
    sudo ufw allow in on "$karte" to any port "$1" proto "$2" \
         comment "Devarenu Saal" >/dev/null 2>&1 \
      && echo "      $1/$2" \
      || echo "      $1/$2 FEHLGESCHLAGEN" >&2
  done

  # Alte Regeln abraeumen: die netzgebundene aus der Installation und
  # alles, was von Hand dazukam. Sonst steht neben der richtigen Regel
  # weiter die falsche, und niemand sieht, welche gerade wirkt.
  #
  # Angefasst wird NUR, was den Kommentar von Devarenu traegt. Fremde
  # Regeln -- KDE Connect und dergleichen -- bleiben unberuehrt.
  local nummer
  while :; do
    nummer="$(sudo ufw status numbered 2>/dev/null \
              | grep -iE "Devarenu" \
              | grep -v "on $karte" \
              | grep -oE '^\[[ ]*[0-9]+\]' | tr -d '[] ' | head -1)"
    [ -n "$nummer" ] || break
    sudo ufw --force delete "$nummer" >/dev/null 2>&1 \
      && echo "      alte Regel $nummer entfernt" || break
  done

  # Weiterleitung aus. Der Saal hat kein Internet und soll keines
  # bekommen -- weder durch NAT noch durch einen zweiten Weg.
  sudo ufw default deny routed >/dev/null 2>&1 \
    && echo "      Weiterleitung aus" \
    || echo "      Weiterleitung liess sich nicht abschalten" >&2
}

# Nur wenn direkt gestartet, nicht beim Einbinden.
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
  KARTE=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --schnittstelle) KARTE="${2:-}"; shift 2 ;;
      # --netz gab es bis 0.2.11. Es wird angenommen und abgelehnt,
      # statt still etwas anderes zu tun: wer es aufruft, meint die
      # alte Bedeutung, und die war falsch.
      --netz) echo "   --netz gibt es nicht mehr. Die Regeln haengen" >&2
              echo "   jetzt an der Schnittstelle:" >&2
              echo "     bash firewall.sh --schnittstelle enp5s0" >&2
              exit 1 ;;
      *) echo "Unbekannt: $1" >&2; exit 1 ;;
    esac
  done
  firewall_saal "$KARTE"
fi
