#!/usr/bin/env bash
# Devarenu, komplette Ersteinrichtung.
#
# Nur diese eine Datei starten:
#
#     bash INSTALLIEREN.sh
#
# Mit "bash" davor, dann braucht die Datei kein Ausfuehrungsrecht und muss
# nach dem Entpacken oder Klonen nicht erst freigeschaltet werden.

set -u
ORDNER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ORDNER"

# Der Reparaturvorrat ist der Normalfall: installiert wird beim
# Systemhaus mit Leitung, der Rechner geht danach in eine Gemeinde ohne
# Netz. Abschaltbar fuer den Entwicklungsrechner, wo die 17 GB bei jeder
# Einrichtung nur im Weg liegen.
VORRAT=ja
while [ $# -gt 0 ]; do
  case "$1" in
    --ohne-vorrat) VORRAT=nein; shift ;;
    -h|--hilfe)    sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)             printf '   Unbekannt: %s\n' "$1"; exit 1 ;;
  esac
done

printf '\n\033[1;34m'
cat <<'ENDE'
    ____  _______    _____    ____  _______   ____  __
   / __ \/ ____/ |  / /   |  / __ \/ ____/ | / / / / /
  / / / / __/  | | / / /| | / /_/ / __/ /  |/ / / / /
 / /_/ / /___  | |/ / ___ |/ _, _/ /___/ /|  / /_/ /
/_____/_____/  |___/_/  |_/_/ |_/_____/_/ |_/\____/
ENDE
printf '\033[0m\n  Devarenu — hebräisch für "unsere Worte"\n'
printf '  Live-Übersetzung im Gottesdienst\n\n'
printf '  Ersteinrichtung. Das dauert beim ersten Mal eine Weile, weil\n'
printf '  rund zehn Gigabyte geladen werden: Rechenbibliothek, Spracherkennung,\n'
printf '  Übersetzungsmodell und die Stimmen.\n\n'

# ---------------------------------------------------------------- Rechte
# Nicht als root. Sonst gehoeren venv, Modelle und Stimmen hinterher
# root, und der Dienst -- der unter einem gewoehnlichen Benutzer laeuft
# -- kommt nicht an sie heran. Der Fehler faellt erst beim ersten Start
# auf, und dann sieht er aus wie ein Problem mit den Modellen.
#
# Fuer den Reparaturvorrat wird spaeter von selbst nach dem Passwort
# gefragt; dafuer braucht es kein sudo vor diesem Aufruf.
if [ "$(id -u)" = "0" ]; then
  printf '\n   \033[31mBitte ohne sudo starten:\033[0m  bash INSTALLIEREN.sh\n\n'
  printf '   Als root gehoeren Programm, Modelle und Stimmen hinterher\n'
  printf '   root, und der Dienst kommt nicht an sie heran.\n'
  printf '   Nach dem Passwort wird spaeter von allein gefragt.\n\n'
  exit 1
fi

chmod +x ./*.sh 2>/dev/null

# ---------------------------------------------------------------- Pakete
# einrichten.sh kennt nur Debian und Ubuntu. Auf Arch und CachyOS heisst
# der Paketmanager anders, deshalb hier vorweg.
if command -v pacman >/dev/null && ! command -v apt-get >/dev/null; then
  printf '\033[1;34m== Systempakete (Arch)\033[0m\n'
  FEHLT=""
  # dnsmasq nur, weil es dieselbe Liste sein soll wie auf dem
  # Gemeinderechner. pacman startet nichts von selbst, es liegt also
  # bloss da. Eingeschaltet wird es allein von netz_einrichten.sh --
  # und das laeuft auf einem Arbeitsrechner ohnehin nicht (NETZ_RECHNER
  # in config.py).
  for paket in python ffmpeg portaudio dnsmasq; do
    pacman -Q "$paket" >/dev/null 2>&1 || FEHLT="$FEHLT $paket"
  done
  if [ -n "$FEHLT" ]; then
    echo "   Installiere:$FEHLT"
    echo "   (das Passwort ist für sudo, nicht für uns)"
    sudo pacman -S --needed --noconfirm $FEHLT || {
      echo "   Fehlgeschlagen. Bitte von Hand:"
      echo "     sudo pacman -S --needed$FEHLT"; exit 1; }
  else
    printf '   \033[32mok\033[0m   alles vorhanden\n'
  fi

fi

# ---------------------------------------------------------------- Treiber
# Stand frueher im pacman-Zweig und lief damit auf Ubuntu nie -- also
# ausgerechnet auf dem Rechner, der in der Gemeinde steht. Eine fehlende
# Grafikkarte waere dort erst im Selbsttest aufgefallen.
if ! command -v nvidia-smi >/dev/null; then
  printf '\n\033[1;34m== Grafikkarte\033[0m\n'
  printf '   \033[31m!\033[0m    Kein NVIDIA-Treiber gefunden.\n'
  printf '        Ohne Grafikkarte läuft alles auf der CPU und ist für\n'
  printf '        den Livebetrieb zu langsam.\n'
  if command -v pacman >/dev/null; then
    printf '        Nachholen mit: sudo pacman -S nvidia-open, dann neu starten\n'
  elif command -v apt-get >/dev/null; then
    printf '        Nachholen mit: sudo ubuntu-drivers install, dann neu starten\n'
  fi
fi

# ---------------------------------------------------------------- Rest
# einrichten.sh gibt den Rueckgabewert des Selbsttests weiter. Ein
# fehlgeschlagener Test ist kein Grund, die Einrichtung als gescheitert zu
# melden: alles ist installiert, es hakt nur irgendwo. Deshalb wird hier
# unterschieden.
# Sagt einrichten.sh, dass es aus einem groesseren Lauf kommt: sonst
# steht sein Abschluss direkt ueber dem hiesigen, zweimal "Fertig".
DEVARENU_SAMMELLAUF=1 bash ./einrichten.sh
ERGEBNIS=$?
if [ "$ERGEBNIS" -gt 1 ]; then
  echo; echo "Einrichtung abgebrochen."; exit 1
fi

# ---------------------------------------------------------------- Symbol
# Nur wo es einen Desktop gibt. Laeuft der Rechner headless, waere eine
# Verknuepfung sinnlos und die Meldung darueber nur verwirrend.
SCHREIBTISCH="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
# Ohne installiertes xdg-user-dirs liefert der Aufruf das Heimatverzeichnis
# zurueck. Ungeprueft laege die Verknuepfung dann mitten in $HOME.
if [ -n "${SCHREIBTISCH:-}" ] && [ "$SCHREIBTISCH" != "$HOME" ] \
   && [ -d "$SCHREIBTISCH" ]; then
  printf '\n\033[1;34m== Verknüpfung\033[0m\n'
  bash ./verknuepfung.sh
  SYMBOL=1
else
  SYMBOL=0
fi

# ------------------------------------------------------------ Netzfreigabe
# Vor der Dienst-Frage, damit der Port schon offen ist, wenn dienst.sh
# gleich darauf die Adressen ausgibt.
#
# Gefragt wird nur, wenn es etwas zu tun gibt. Ist keine Firewall aktiv --
# auf Ubuntu Server der Normalfall -- oder gibt es die Regel schon,
# passiert hier gar nichts und es steht auch nichts da.
#
# Und gefragt wird ueberhaupt: eine Firewall ungefragt zu oeffnen ist
# nichts, was ein Installationsskript still entscheiden sollte. Ein
# Tastendruck genuegt, aber man hat gesehen, was passiert.
if [ -f firewall.sh ]; then
  . ./firewall.sh
  firewall_lage "${DEVARENU_PORT:-8000}"
  if [ -n "${FW_ART:-}" ]; then
    printf '\n\033[1;34m== Netzfreigabe\033[0m\n'
    printf '   Die Firewall (%s) sperrt eingehende Verbindungen. Ohne\n' "$FW_ART"
    printf '   Freigabe erreicht kein Handy im Saal den Server.\n\n'
    if [ "$FW_ART" = "ufw" ]; then
      read -rp "   Port ${DEVARENU_PORT:-8000} für $FW_NETZ freigeben? [J/n] " fwantwort
      case "${fwantwort:-j}" in
        [nN]*) printf '   Gut. Nachholen mit:\n     %s\n' "$FW_BEFEHL" ;;
        *)     if eval "$FW_BEFEHL" >/dev/null 2>&1; then
                 printf '   Freigegeben für %s.\n' "$FW_NETZ"
               else
                 printf '   \033[33mHat nicht geklappt.\033[0m Von Hand:\n     %s\n' \
                        "$FW_BEFEHL"
               fi ;;
      esac
    else
      # firewalld wird erkannt, aber nicht angefasst: hier war keins zum
      # Ausprobieren, und ungetestete Firewallbefehle gehoeren nicht auf
      # einen fremden Rechner.
      printf '   Freigeben mit:\n     %s\n' "$FW_BEFEHL"
    fi
  fi
fi

# ---------------------------------------------------------------- Dienst
# Nur auf Nachfrage und mit "nein" als Vorgabe: wer entwickelt, will
# keinen Dienst, der beim naechsten Einschalten den Port belegt. Fuer den
# Rechner in der Gemeinde ist es dagegen der Normalfall -- dort meldet
# sich niemand an und tippt ./start.sh.
DIENST=0
if [ -d /run/systemd/system ] && [ -f dienst.sh ]; then
  printf '\n\033[1;34m== Systemdienst\033[0m\n'
  printf '   Soll Devarenu beim Einschalten des Rechners von allein\n'
  printf '   starten und sich nach einem Absturz selbst wieder fangen?\n'
  printf '   Fuer den Rechner in der Gemeinde: ja. Zum Entwickeln: nein.\n\n'
  read -rp "   Als Systemdienst einrichten? [j/N] " dienstantwort
  case "${dienstantwort:-n}" in
    [jJyY]*) bash ./dienst.sh && DIENST=1 ;;
    *)       printf '   Gut. Nachholen jederzeit mit: ./dienst.sh\n' ;;
  esac
fi

# ------------------------------------------------------- Reparaturvorrat
# Ganz zuletzt: er kopiert, was die Schritte davor geladen haben. Vorher
# gebaut waere er leer.
if [ "$VORRAT" = "ja" ] && [ -f vorrat_bauen.sh ]; then
  printf '\n\033[1;34m== Reparaturvorrat\033[0m\n'
  printf '   Eine Kopie von allem, was gerade geladen wurde: Pakete,\n'
  printf '   Stimmen, Spracherkennung, Uebersetzungsmodell. Rund 17 GB.\n'
  printf '   In der Gemeinde gibt es kein Netz -- ohne diese Kopie laesst\n'
  printf '   sich dort nichts wiederherstellen.\n\n'
  if sudo -n true 2>/dev/null || sudo -v; then
    # Scheitert er, ist die Einrichtung trotzdem gelungen. Der Vorrat
    # ist Vorsorge, kein Bestandteil des Betriebs.
    if sudo bash ./vorrat_bauen.sh; then
      VORRAT_OK=1
    else
      VORRAT_OK=0
      printf '\n   \033[33mDer Vorrat wurde nicht vollstaendig angelegt.\033[0m\n'
      printf '   Nachholen, solange noch Netz da ist:\n'
      printf '     sudo ./vorrat_bauen.sh\n'
    fi
  else
    VORRAT_OK=0
    printf '   Ohne sudo geht das nicht. Nachholen mit:\n'
    printf '     sudo ./vorrat_bauen.sh\n'
  fi
else
  VORRAT_OK=-1
fi

printf '\n\033[1;34m== Fertig\033[0m\n'
if [ "$SYMBOL" = "1" ]; then
  printf '   Auf dem Schreibtisch liegt jetzt "Devarenu starten".\n'
  printf '   Doppelklick genügt, dieses Fenster wird nicht mehr gebraucht.\n\n'
  printf '   Beim ersten Doppelklick fragt das System einmal nach, ob die\n'
  printf '   Verknüpfung ausgeführt werden darf.\n\n'
else
  printf '   Kein Desktop gefunden, also keine Verknüpfung.\n'
  printf '   Starten mit:  ./start.sh\n\n'
fi

if [ "${VORRAT_OK:--1}" = "1" ]; then
  printf '   Der Reparaturvorrat liegt unter /opt/devarenu-vorrat.\n'
  printf '   Damit laesst sich in der Gemeinde ohne Netz wiederherstellen:\n'
  printf '     ./wiederherstellen.sh --pruefen\n\n'
fi

if [ "$ERGEBNIS" != "0" ]; then
  printf '   \033[33mDer Selbsttest hat etwas beanstandet.\033[0m Nachlesen oben,\n'
  printf '   Test wiederholen mit:  .venv/bin/python selbsttest.py\n\n'
fi

# Laeuft der Dienst, laeuft der Server schon. Ein zweiter Start wuerde
# nur am belegten Port scheitern.
if [ "$DIENST" = "1" ]; then
  printf '   Der Dienst läuft bereits. Adressen stehen oben.\n\n'
  exit 0
fi

read -rp "   Jetzt gleich starten? [J/n] " antwort
case "${antwort:-j}" in
  [nN]*) echo "   Gut. Später mit ./start.sh" ;;
  *)     echo; exec bash ./start.sh ;;
esac
