#!/usr/bin/env bash
# Die virtuelle Testmaschine: anlegen, pruefen, wegwerfen.
#
#   bash vm_pruefstand.sh --vorbedingungen   was fehlt noch? (ohne sudo)
#   bash vm_pruefstand.sh --anlegen          VM aus einer CachyOS-ISO
#   bash vm_pruefstand.sh --update <tag>     Update dort einspielen und pruefen
#   bash vm_pruefstand.sh --zeigen           Zustand der VM
#   bash vm_pruefstand.sh --weg              VM und Platte loeschen
#
#   --name devarenu-test   anderer VM-Name
#   --iso /pfad/zur.iso    andere Installationsquelle
#
# WOFUER
#
# Jedes Update soll zuerst hier laufen und dann auf dem
# Gemeinderechner. Bis 0.3.8 war der Gemeinderechner die Testmaschine
# -- und jeder Fehler fiel am Donnerstagabend auf, zwei Tage vor dem
# Gottesdienst. Dreimal ist genau das passiert (0.3.1, 0.3.3, 0.3.7).
#
# WAS DIE VM NICHT PRUEFT
#
# Das steht ausfuehrlich in VM-TESTUMGEBUNG.md und gehoert gelesen,
# bevor jemand "gruen auf der VM" fuer "gruen im Saal" nimmt. Kurz:
# NVIDIA-Treiber, Ton (UMC202HD), die Wayland-Sitzung und der
# BIOS-Wecker lassen sich hier nicht pruefen. Die VM prueft den WEG,
# nicht das Geraet.
#
# WAS DIESES SKRIPT NICHT TUT
#
# Es laedt keine ISO herunter und installiert nichts ohne
# Nachfrage. --vorbedingungen sagt, was fehlt, und nennt den Befehl.
# Das ist Absicht: ein Skript, das von selbst Gigabyte holt und
# Systemdienste anfasst, laeuft einmal am falschen Rechner.

set -u
ORDNER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

NAME="devarenu-test"
ISO=""
PLATTE_GB=40
RAM_MB=8192
KERNE=4
# Ein eigenes Netz, damit das dnsmasq der VM niemandem in die Quere
# kommt. Das Netz "default" von libvirt bringt ein eigenes dnsmasq auf
# einem eigenen Adressbereich mit; die Testmaschine bekommt ihr
# Saalnetz darum auf einer zweiten, ISOLIERTEN Schnittstelle.
NETZ_SAAL="devarenu-saal"

TUN=""
SUDO="${DEVARENU_SUDO:-sudo}"
VIRSH="${DEVARENU_VIRSH:-virsh}"
VIRTINSTALL="${DEVARENU_VIRTINSTALL:-virt-install}"

blau() { printf '\n\033[1;34m== %s\033[0m\n' "$*"; }
gut()  { printf '   \033[32mok\033[0m    %s\n' "$*"; }
warn() { printf '   \033[33m!\033[0m     %s\n' "$*"; }
fehl() { printf '   \033[31mFEHLT\033[0m %s\n' "$*"; }
info() { printf '         %s\n' "$*"; }

TAG=""
while [ $# -gt 0 ]; do
  case "$1" in
    --vorbedingungen) TUN=vorbedingungen; shift ;;
    --anlegen)        TUN=anlegen; shift ;;
    --update)         TUN=update; TAG="${2:-}"; shift 2 ;;
    --zeigen)         TUN=zeigen; shift ;;
    --weg)            TUN=weg; shift ;;
    --name)           NAME="${2:-}"; shift 2 ;;
    --iso)            ISO="${2:-}"; shift 2 ;;
    -h|--hilfe)
      sed -n '2,/^set -u/p' "$0" | sed 's/^# \{0,1\}//;/^set -u/d'
      exit 0 ;;
    *) fehl "Unbekannt: $1"; exit 2 ;;
  esac
done
[ -n "$TUN" ] || { sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }

# ------------------------------------------------------ Vorbedingungen
vorbedingungen() {
  blau "Was die Testmaschine braucht"
  local mangel=0

  for befehl in qemu-system-x86_64 virsh virt-install; do
    if command -v "$befehl" >/dev/null; then
      gut "$befehl"
    else
      fehl "$befehl"
      mangel=1
    fi
  done
  if [ "$mangel" = 1 ]; then
    info "Nachholen:  sudo pacman -S --needed qemu-full libvirt virt-install"
    info "Danach:     sudo systemctl enable --now libvirtd"
    info "Und einmal: sudo usermod -aG libvirt \$USER   (dann neu anmelden)"
  fi

  if [ -r /dev/kvm ]; then
    gut "/dev/kvm ist lesbar -- die VM laeuft mit Beschleunigung"
  else
    fehl "/dev/kvm nicht lesbar."
    info "Entweder fehlt die Gruppe kvm oder die Virtualisierung ist im"
    info "BIOS aus. Ohne KVM laeuft die VM, aber zu langsam zum Arbeiten."
    mangel=1
  fi

  if id -nG 2>/dev/null | grep -qw libvirt; then
    gut "dieser Benutzer ist in der Gruppe libvirt"
  else
    warn "Dieser Benutzer ist nicht in der Gruppe libvirt."
    info "Dann braucht jeder virsh-Aufruf sudo. Geht, ist nur unbequem."
  fi

  if command -v "$VIRSH" >/dev/null \
     && $VIRSH net-info default >/dev/null 2>&1; then
    gut "libvirt-Netz \"default\" ist da"
  else
    warn "Das libvirt-Netz \"default\" antwortet nicht."
    info "  sudo virsh net-start default"
    info "  sudo virsh net-autostart default"
  fi

  local platz
  platz="$(df --output=avail -BG "$HOME" 2>/dev/null | tail -1 | tr -dc '0-9')"
  if [ -n "$platz" ] && [ "$platz" -ge "$((PLATTE_GB + 10))" ]; then
    gut "${platz} GB frei (gebraucht: $PLATTE_GB fuer die Platte, dazu die ISO)"
  else
    warn "Nur ${platz:-?} GB frei. Gebraucht werden gut $((PLATTE_GB + 10))."
    mangel=1
  fi

  if [ -n "$ISO" ] && [ -f "$ISO" ]; then
    gut "ISO: $ISO ($(du -h "$ISO" | cut -f1))"
  else
    local gefunden
    gefunden="$(ls -1 "$HOME"/Downloads/cachyos*.iso \
                      "$HOME"/Downloads/CachyOS*.iso 2>/dev/null | head -1)"
    if [ -n "$gefunden" ]; then
      gut "ISO gefunden: $gefunden"
      info "Mit --iso \"$gefunden\" uebergeben."
    else
      warn "Keine CachyOS-ISO gefunden."
      info "Von https://cachyos.org/download/ holen und mit --iso uebergeben."
      info "Dieses Skript laedt sie NICHT herunter."
      mangel=1
    fi
  fi

  blau "Ergebnis"
  if [ "$mangel" = 0 ]; then
    gut "Alles da. Weiter mit:  bash vm_pruefstand.sh --anlegen --iso ..."
    return 0
  fi
  warn "Es fehlt etwas (siehe oben). Nichts angefasst."
  return 1
}

# ------------------------------------------------------------ Anlegen
anlegen() {
  blau "Testmaschine $NAME anlegen"
  vorbedingungen >/dev/null || { fehl "Vorbedingungen nicht erfuellt."
    info "Nachsehen:  bash vm_pruefstand.sh --vorbedingungen"; return 1; }
  [ -n "$ISO" ] && [ -f "$ISO" ] || { fehl "--iso fehlt."; return 1; }

  if $VIRSH dominfo "$NAME" >/dev/null 2>&1; then
    fehl "Eine VM \"$NAME\" gibt es schon."
    info "Erst weg:  bash vm_pruefstand.sh --weg --name $NAME"
    return 1
  fi

  # Das isolierte Saalnetz. "isolated" heisst: die VM kommt darueber
  # nirgendwohin, und niemand kommt hinein. Genau das ist der Saal.
  if ! $VIRSH net-info "$NETZ_SAAL" >/dev/null 2>&1; then
    local xml; xml="$(mktemp)"
    cat > "$xml" <<ENDE
<network>
  <name>$NETZ_SAAL</name>
  <bridge name='virbr-devsaal' stp='on' delay='0'/>
</network>
ENDE
    if $VIRSH net-define "$xml" >/dev/null 2>&1 \
       && $VIRSH net-start "$NETZ_SAAL" >/dev/null 2>&1; then
      gut "isoliertes Netz \"$NETZ_SAAL\" angelegt"
      info "Kein <forward>, kein <ip>: libvirt stellt dort weder einen"
      info "Router noch ein DHCP. Beides macht Devarenu selbst -- genau"
      info "das soll geprueft werden."
    else
      warn "Das Netz \"$NETZ_SAAL\" liess sich nicht anlegen."
    fi
    rm -f "$xml"
  else
    gut "Netz \"$NETZ_SAAL\" ist schon da"
  fi

  info "virt-install laeuft an. Die Installation von CachyOS geschieht"
  info "im Fenster, von Hand -- genau wie beim Gemeinderechner."
  info "Benutzer dabei: devarenu. Alles andere nach ERSTINSTALLATION.md."
  $VIRTINSTALL \
    --name "$NAME" \
    --memory "$RAM_MB" --vcpus "$KERNE" \
    --disk "size=$PLATTE_GB,format=qcow2" \
    --cdrom "$ISO" \
    --os-variant archlinux \
    --network network=default \
    --network "network=$NETZ_SAAL" \
    --graphics spice \
    --noautoconsole \
    || { fehl "virt-install ist gescheitert."; return 1; }

  gut "VM $NAME angelegt: zwei Netzwerkkarten, $RAM_MB MB, $KERNE Kerne"
  blau "Danach, IN der VM"
  info "1. CachyOS installieren, Benutzer devarenu, automatische Anmeldung."
  info "2. ERSTINSTALLATION.md abarbeiten -- Abschnitte 2 bis 8."
  info "3. Den Testmodus einschalten (sonst rechnet Whisper auf der CPU"
  info "   mit dem grossen Modell und braucht Minuten je Satz):"
  info "      python testmodus.py --ein"
  info "4. Einen Schnappschuss anlegen, damit jeder Testlauf von"
  info "   derselben Stelle beginnt:"
  info "      virsh snapshot-create-as $NAME frisch"
  return 0
}

# ------------------------------------------------- Update dort pruefen
update() {
  blau "Update auf der Testmaschine pruefen"
  [ -n "$TAG" ] || { fehl "Kein Tag genannt."
    info "So:  bash vm_pruefstand.sh --update v0.4.0"; return 1; }
  if ! $VIRSH dominfo "$NAME" >/dev/null 2>&1; then
    fehl "Keine VM \"$NAME\"."
    info "Anlegen:  bash vm_pruefstand.sh --anlegen --iso ..."
    return 1
  fi

  # Vom Schnappschuss aus, damit jeder Lauf gleich anfaengt. Ohne das
  # prueft der zweite Lauf einen Rechner, den der erste veraendert hat.
  if $VIRSH snapshot-info "$NAME" frisch >/dev/null 2>&1; then
    info "Zuruecksetzen auf den Schnappschuss \"frisch\" ..."
    $VIRSH snapshot-revert "$NAME" frisch >/dev/null 2>&1 \
      && gut "zurueckgesetzt" || warn "Zuruecksetzen ging nicht."
  else
    warn "Kein Schnappschuss \"frisch\". Der Lauf beginnt da, wo der"
    info "letzte endete -- das prueft weniger, als es aussieht."
    info "Anlegen:  virsh snapshot-create-as $NAME frisch"
  fi

  $VIRSH start "$NAME" >/dev/null 2>&1 || true
  info "Die VM laeuft. Jetzt IN der VM:"
  echo
  echo "      bash aktualisieren.sh"
  echo "      bash pruefen.sh"
  echo "      .venv/bin/python selbsttest.py"
  echo "      cat VERSION"
  echo
  info "Oder in einem Zug, falls ein SSH-Zugang eingerichtet ist:"
  echo
  echo "      ssh devarenu@<vm-adresse> \\"
  echo "        'cd ~/Devarenu && bash aktualisieren.sh && bash pruefen.sh'"
  echo
  blau "Was danach stimmen muss"
  info "VERSION steht auf ${TAG#v}"
  info "pruefen.sh zeigt keine roten Punkte"
  info "systemctl is-active devarenu  sagt active"
  info "der Systemcheck meldet den TESTMODUS -- sonst lief das grosse"
  info "Modell, und der Lauf hat eine Stunde gedauert"
  echo
  warn "UND WAS DIE VM NICHT GEPRUEFT HAT: NVIDIA-Treiber, Ton,"
  warn "Wayland-Sitzung, BIOS-Wecker. Siehe VM-TESTUMGEBUNG.md."
  return 0
}

zeigen() {
  blau "Testmaschine $NAME"
  if ! $VIRSH dominfo "$NAME" 2>/dev/null | sed 's/^/         /'; then
    warn "Keine VM \"$NAME\"."
    return 0
  fi
  blau "Schnappschuesse"
  $VIRSH snapshot-list "$NAME" 2>/dev/null | sed 's/^/         /' \
    || warn "keine"
  blau "Netze"
  $VIRSH net-list --all 2>/dev/null | sed 's/^/         /'
  return 0
}

weg() {
  blau "Testmaschine $NAME loeschen"
  if ! $VIRSH dominfo "$NAME" >/dev/null 2>&1; then
    warn "Keine VM \"$NAME\". Nichts zu tun."
    return 0
  fi
  printf '         Wirklich loeschen, samt Platte? [j/N] '
  read -r a
  case "$a" in j|J|ja|Ja) ;; *) echo "         Abgebrochen."; return 0 ;; esac
  $VIRSH destroy "$NAME" >/dev/null 2>&1 || true
  $VIRSH undefine "$NAME" --remove-all-storage --snapshots-metadata \
    >/dev/null 2>&1 && gut "VM und Platte weg" \
    || fehl "Das Loeschen ging nicht."
  info "Das Netz \"$NETZ_SAAL\" bleibt stehen -- es kostet nichts und"
  info "die naechste Testmaschine braucht es wieder."
  return 0
}

case "$TUN" in
  vorbedingungen) vorbedingungen ;;
  anlegen)        anlegen ;;
  update)         update ;;
  zeigen)         zeigen ;;
  weg)            weg ;;
esac
exit $?
