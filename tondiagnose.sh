#!/usr/bin/env bash
# Warum bekommt der Dienst keinen Ton, die Sitzung aber schon?
#
#   bash tondiagnose.sh                      alles, was ohne Rechte geht
#   sudo bash tondiagnose.sh                 zusaetzlich der echte Dienstlauf
#   bash tondiagnose.sh --geraet UMC202HD    nach diesem Namen suchen
#   bash tondiagnose.sh > tonbericht.txt 2>&1   zum Verschicken
#
# Es AENDERT NICHTS: kein Dienst wird gestartet oder gestoppt, keine
# Einstellung gesetzt, nichts im Projektordner angefasst. Es liest,
# oeffnet die Tonquelle kurz und schliesst sie wieder. Einzige
# Schreibvorgaenge sind Zwischendateien unter /tmp, die sich selbst
# wieder aufraeumen.
#
# Die Frage, an der alles haengt: Bricht Pa_Initialize vollstaendig ab,
# wenn nur die PulseAudio-Schnittstelle scheitert, oder bleiben die
# ALSA-Geraete nutzbar? Davon haengt ab, ob der reine ALSA-Weg ueberhaupt
# gangbar ist. Lauf 6 unten beantwortet genau das: er setzt PULSE_SERVER
# mit Absicht auf etwas, das es nicht gibt.
#
# Auf dem Entwicklungsrechner laesst sich das nicht entscheiden -- dort
# ist PortAudio ohne PulseAudio-Schnittstelle gebaut. Deshalb dieses
# Skript, und deshalb muss es auf dem Gemeinderechner laufen.

set -u
ORDNER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ORDNER"

GERAET=""
while [ $# -gt 0 ]; do
  case "$1" in
    --geraet)   GERAET="${2:-}"; shift 2 ;;
    -h|--hilfe) sed -n '2,23p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)          echo "Unbekannt: $1"; exit 1 ;;
  esac
done

blau() { printf '\n\033[1;34m== %s\033[0m\n' "$*"; }
gut()  { printf '   \033[32mok\033[0m    %s\n' "$*"; }
warn() { printf '   \033[33m!\033[0m     %s\n' "$*"; }
fehl() { printf '   \033[31mNEIN\033[0m  %s\n' "$*"; }
info() { printf '         %s\n' "$*"; }

PY="$ORDNER/.venv/bin/python"
[ -x "$PY" ] || { fehl "Keine venv unter $ORDNER/.venv"; exit 1; }

printf '\033[1mDevarenu -- Tondiagnose\033[0m   %s auf %s\n' \
  "$(date '+%d.%m.%Y %H:%M')" "$(hostname)"

# ------------------------------------------------------------ Wer bin ich
blau "Sitzung und Benutzer"
info "angemeldet als   $(id -un) (uid $(id -u))"
info "Gruppen          $(id -Gn)"
case " $(id -Gn) " in
  *" audio "*) gut "in der Gruppe audio" ;;
  *)           warn "nicht in der Gruppe audio -- ohne Sitzung faellt die"
               info "uaccess-ACL weg, dann zaehlt nur noch die Gruppe." ;;
esac
if [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
  info "Das hier laeuft IN einer grafischen Sitzung. Der Dienst nicht."
else
  info "Keine grafische Sitzung in dieser Shell."
fi
info "XDG_RUNTIME_DIR  ${XDG_RUNTIME_DIR:-(nicht gesetzt)}"
info "PULSE_SERVER     ${PULSE_SERVER:-(nicht gesetzt)}"

# ------------------------------------------------------------ Der Dienst
blau "Der Dienst"
DBENUTZER=""
if command -v systemctl >/dev/null && systemctl cat devarenu >/dev/null 2>&1; then
  DBENUTZER="$(systemctl show devarenu -p User --value 2>/dev/null)"
  [ -z "$DBENUTZER" ] && DBENUTZER=root
  info "Zustand          $(systemctl is-active devarenu 2>/dev/null)"
  info "laeuft als       $DBENUTZER"
  UMG="$(systemctl show devarenu -p Environment --value 2>/dev/null)"
  info "Environment      ${UMG:-(leer)}"
  info "Gruppen extra    $(systemctl show devarenu -p SupplementaryGroups --value 2>/dev/null)"
  case "$UMG" in
    *XDG_RUNTIME_DIR*) gut "XDG_RUNTIME_DIR steht in der Unit" ;;
    *) warn "Die Unit setzt kein XDG_RUNTIME_DIR."
       info "Ohne das findet libpulse den Sockel nicht, auch wenn er da"
       info "ist -- der wahrscheinlichste Grund fuer den Befund." ;;
  esac
else
  warn "Kein Dienst devarenu eingerichtet."
  # Nicht "id -un": unter sudo ist das root, und dann pruefte dieses
  # Skript /run/user/0 -- einen Ordner, den es meist gar nicht gibt, und
  # der mit dem Ton dieses Rechners nichts zu tun hat. Gesucht ist der
  # Mensch, der das Skript aufgerufen hat, nicht die Rolle, in der es
  # gerade laeuft.
  DBENUTZER="${SUDO_USER:-$(id -un)}"
  info "Geprueft wird stattdessen der Benutzer $DBENUTZER."
  if [ -n "${SUDO_USER:-}" ]; then
    info "(Nicht root: unter sudo waere das der falsche Ordner.)"
  fi
fi

DUID="$(id -u "$DBENUTZER" 2>/dev/null)"
if [ -z "$DUID" ]; then
  fehl "Benutzer $DBENUTZER gibt es nicht."
else
  info "uid des Dienstbenutzers  $DUID"
fi

# --------------------------------------------------- Der Laufzeitordner
blau "/run/user/$DUID"
LAUF="/run/user/${DUID:-0}"
if [ -d "$LAUF" ]; then
  gut "$LAUF existiert  ($(stat -c '%U:%G %a' "$LAUF" 2>/dev/null))"
  if [ -S "$LAUF/pulse/native" ]; then
    gut "$LAUF/pulse/native ist da"
    info "$(stat -c '%U:%G %a' "$LAUF/pulse/native" 2>/dev/null)"
    [ -r "$LAUF/pulse/native" ] && gut "von hier aus lesbar" \
      || warn "von hier aus NICHT lesbar (anderer Benutzer?)"
  else
    fehl "$LAUF/pulse/native fehlt."
    info "Ohne diesen Sockel gibt es keinen PulseAudio-Zugang, egal was"
    info "in der Umgebung steht."
  fi
else
  fehl "$LAUF existiert nicht."
  info "Der Ordner entsteht beim Anmelden und verschwindet beim Abmelden."
  info "Damit er beim Hochfahren ohne Anmeldung da ist:"
  info "  sudo loginctl enable-linger $DBENUTZER"
fi
if command -v loginctl >/dev/null; then
  info "Linger           $(loginctl show-user "$DBENUTZER" -p Linger --value 2>/dev/null || echo '?')"
  info "Sitzungen        $(loginctl show-user "$DBENUTZER" -p Sessions --value 2>/dev/null || echo '?')"
fi

# ------------------------------------------------------- Was laeuft da
blau "Tonserver und Karten"
for d in pipewire pipewire-pulse wireplumber pulseaudio jackd; do
  if pgrep -x "$d" >/dev/null 2>&1; then
    info "laeuft: $d  (als $(ps -o user= -C "$d" 2>/dev/null | sort -u | tr '\n' ' '))"
  fi
done
pgrep -x pipewire >/dev/null 2>&1 || pgrep -x pulseaudio >/dev/null 2>&1 \
  || warn "Kein Tonserver laeuft in diesem Moment."
if [ -r /proc/asound/cards ]; then
  info "ALSA-Karten:"
  sed 's/^/           /' /proc/asound/cards
else
  fehl "/proc/asound/cards fehlt -- kein ALSA im Kern?"
fi
if command -v arecord >/dev/null; then
  info "Aufnahmegeraete (arecord -l):"
  arecord -l 2>/dev/null | sed 's/^/           /'
fi

# ---------------------------------------------------------------- Laeufe
# Die eigentliche Messung. Jeder Lauf ist ein eigener Prozess: PortAudio
# laesst sich je Prozess nur einmal starten, und es geht gerade um die
# Umgebung, in der das geschieht.
PROBE='
import os, sys, tempfile

gesucht = sys.argv[1] if len(sys.argv) > 1 else ""

# ALSA schreibt ueber die C-Schicht direkt auf Deskriptor 2, hunderte
# Zeilen. Weggehalten, aber gezaehlt -- und die ersten Zeilen zeigen wir,
# weil dort manchmal der eigentliche Grund steht. Zugehalten wird der
# ganze Lauf, nicht nur der Import: auch das Oeffnen redet dort hinein.
sys.stderr.flush()
alt = os.dup(2)
puffer = tempfile.TemporaryFile()
os.dup2(puffer.fileno(), 2)

zeilen = []
def sag(t):
    zeilen.append(t)

try:
    fehler = None
    try:
        import sounddevice as sd
    except Exception as e:
        fehler = "%s: %s" % (type(e).__name__, str(e).strip()[:300])

    if fehler:
        sag("   IMPORT FEHLGESCHLAGEN")
        sag("     " + fehler)
    else:
        sag("   Import ok, PortAudio %s" % sd.get_portaudio_version()[1])
        apis = sd.query_hostapis()
        sag("   Schnittstellen: " + (", ".join(
            "%s (%d Geraete)" % (h["name"], len(h["devices"])) for h in apis)
            or "keine"))
        namen = {i: h["name"] for i, h in enumerate(apis)}
        alle = sd.query_devices()
        eingang = [(i, g) for i, g in enumerate(alle)
                   if g["max_input_channels"] > 0]
        sag("   Eingaenge: %d" % len(eingang))
        for i, g in eingang:
            treffer = gesucht and gesucht.lower() in g["name"].lower()
            sag("    %s %2d  %-40s %-8s %dch %.0f Hz"
                % ("*" if treffer else " ", i, g["name"][:40],
                   namen.get(g["hostapi"], "?"),
                   g["max_input_channels"], g["default_samplerate"]))
        if gesucht and not any(gesucht.lower() in g["name"].lower()
                               for _, g in eingang):
            sag("   Kein Eingang mit %r in diesem Lauf." % gesucht)

        # Auflisten ist nicht oeffnen. Erst der Versuch zeigt, ob das
        # Geraet wirklich zu haben ist -- es kann belegt sein, etwa vom
        # laufenden Dienst selbst.
        ziele = [i for i, g in eingang
                 if gesucht and gesucht.lower() in g["name"].lower()]
        if not ziele:
            # Ohne Vorgabe die hw:-Geraete, nicht "default": es geht um
            # die Frage, ob ALSA direkt zu haben ist.
            ziele = [i for i, g in eingang if "(hw:" in g["name"]][:3]
        for i in ziele:
            g = alle[i]
            geschafft = False
            for rate in (16000, int(g["default_samplerate"])):
                try:
                    with sd.InputStream(device=i, channels=1,
                                        samplerate=rate, blocksize=1024):
                        pass
                    sag("   OEFFNEN ok: %d %s bei %d Hz"
                        % (i, g["name"][:30], rate))
                    geschafft = True
                    break
                except Exception as e:
                    letzt = "%s: %s" % (type(e).__name__,
                                        str(e).strip()[:160])
            if not geschafft:
                sag("   OEFFNEN fehlgeschlagen: %d %s -- %s"
                    % (i, g["name"][:30], letzt))
finally:
    sys.stderr.flush()
    os.dup2(alt, 2)
    os.close(alt)
    puffer.seek(0)
    laut = puffer.read().decode("utf-8", "replace").splitlines()
    puffer.close()

for t in zeilen:
    print(t)
if laut:
    print("   (%d Zeilen ALSA-Ausgabe unterdrueckt)" % len(laut))
    for z in laut[:4]:
        print("     " + z[:160])

'

lauf() {
  # $1 = Ueberschrift, Rest = Umgebung als VAR=WERT
  printf '\n   \033[1m%s\033[0m\n' "$1"; shift
  for v in "$@"; do info "  $v"; done
  env "$@" "$PY" -c "$PROBE" "$GERAET" 2>&1 | sed 's/^/   /'
}

blau "Laeufe"
info "Jeder Lauf ist ein eigener Prozess. Verglichen wird die Umgebung."

lauf "1) wie diese Sitzung (unveraendert)"

# Ein Systemdienst bekommt von systemd fast nichts mit: HOME, LOGNAME,
# USER, PATH -- und sonst nur, was Environment= setzt. env -i baut genau
# das nach, ohne den Dienst anzufassen.
lauf "2) wie der Dienst heute (leere Umgebung)" \
  HOME="$HOME" USER="$(id -un)" LOGNAME="$(id -un)" PATH=/usr/bin:/bin

lauf "3) Dienstumgebung plus XDG_RUNTIME_DIR" \
  HOME="$HOME" USER="$(id -un)" LOGNAME="$(id -un)" PATH=/usr/bin:/bin \
  XDG_RUNTIME_DIR="$LAUF"

lauf "4) Dienstumgebung plus XDG_RUNTIME_DIR und PULSE_SERVER" \
  HOME="$HOME" USER="$(id -un)" LOGNAME="$(id -un)" PATH=/usr/bin:/bin \
  XDG_RUNTIME_DIR="$LAUF" PULSE_SERVER="unix:$LAUF/pulse/native"

# Die vorbereitete, auskommentierte Zeile aus der Unit. Die Absicht war,
# PortAudio damit an PulseAudio vorbeizuleiten. Ob ein leerer Wert das
# tut oder nur einen anderen Fehlschlag erzeugt, steht hier.
lauf "5) PULSE_SERVER leer (die vorbereitete Zeile)" \
  HOME="$HOME" USER="$(id -un)" LOGNAME="$(id -un)" PATH=/usr/bin:/bin \
  PULSE_SERVER=

# DER ENTSCHEIDENDE LAUF. PulseAudio ist hier garantiert nicht zu
# erreichen. Kommen trotzdem ALSA-Geraete heraus, ueberlebt
# Pa_Initialize eine gescheiterte Schnittstelle -- dann ist der reine
# ALSA-Weg gangbar. Bricht der Import ab, ist er es nicht, und alles
# haengt daran, dass PulseAudio erreichbar ist.
lauf "6) PulseAudio mit Absicht kaputt -- die entscheidende Frage" \
  HOME="$HOME" USER="$(id -un)" LOGNAME="$(id -un)" PATH=/usr/bin:/bin \
  XDG_RUNTIME_DIR=/gibt/es/nicht \
  PULSE_SERVER="unix:/gibt/es/nicht/pulse/native"

# ------------------------------------------------- Der echte Dienstlauf
blau "Als Dienstbenutzer, ohne Sitzung"
if [ "$(id -u)" != "0" ]; then
  info "Ohne Wurzelrechte nicht moeglich. Der Lauf oben ist nachgebaut,"
  info "dieser hier waere der echte. Mit:"
  info "  sudo bash tondiagnose.sh${GERAET:+ --geraet $GERAET}"
elif ! command -v systemd-run >/dev/null; then
  warn "systemd-run fehlt."
else
  info "systemd-run startet den Lauf so, wie systemd den Dienst startet:"
  info "als $DBENUTZER, mit leerer Umgebung, ohne Sitzung."
  for zusatz in "" "XDG_RUNTIME_DIR=$LAUF" ; do
    printf '\n   \033[1mDienstlauf%s\033[0m\n' \
      "${zusatz:+ mit $zusatz}"
    # shellcheck disable=SC2086
    systemd-run --quiet --wait --pipe --collect \
      --uid="$DBENUTZER" \
      ${zusatz:+--setenv="$zusatz"} \
      --setenv="HOME=$(getent passwd "$DBENUTZER" | cut -d: -f6)" \
      "$PY" -c "$PROBE" "$GERAET" 2>&1 | sed 's/^/   /'
  done
fi

# ----------------------------------------------------------- Zusammen
blau "Was daraus folgt"
# Ohne PulseAudio-Schnittstelle in PortAudio ist Lauf 6 gegenstandslos:
# dann kann dort gar nichts scheitern. Genau so steht es auf dem
# Entwicklungsrechner, und dort darf niemand ein gruenes Ergebnis fuer
# eine Antwort halten.
HATPULSE="$("$PY" -c "
import sounddevice as sd
print('ja' if any('pulse' in h['name'].lower()
                  for h in sd.query_hostapis()) else 'nein')" 2>/dev/null)"
if [ "${HATPULSE:-}" != "ja" ]; then
  warn "Dieses PortAudio hat gar keine PulseAudio-Schnittstelle."
  info "Dann kann in Lauf 6 auch nichts daran scheitern -- er beantwortet"
  info "die Frage auf DIESEM Rechner nicht. Gebraucht wird die Ausgabe vom"
  info "Gemeinderechner, wo der Absturz aufgetreten ist."
  info ""
fi
info "Lauf 6 ist der Schluessel:"
info "  Import ok, ALSA-Geraete da  -> der reine ALSA-Weg ist gangbar."
info "  Import bricht ab            -> PulseAudio MUSS erreichbar sein,"
info "                                 also XDG_RUNTIME_DIR und linger."
info ""
info "Lauf 2 gegen Lauf 3: kommt allein mit XDG_RUNTIME_DIR Ton zustande,"
info "ist die Ursache gefunden und die Loesung eine Zeile in der Unit."
info ""
info "Diese Ausgabe bitte vollstaendig schicken:"
info "  bash tondiagnose.sh${GERAET:+ --geraet $GERAET} > tonbericht.txt 2>&1"
