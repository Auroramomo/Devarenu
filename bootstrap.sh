#!/usr/bin/env bash
# Erstinstallation des Update-Verfahrens. Laeuft vom USB-Stick.
#
#     sudo bash /pfad/zum/stick/bootstrap.sh
#
# Gedacht fuer Gemeinderechner, die noch eine Fassung vor 0.2.1 haben und
# deshalb von einem eingesteckten Stick nichts wissen. Einmal aufrufen,
# danach genuegt das Einstecken.
#
# Neu aufgesetzte Rechner brauchen das nicht: INSTALLIEREN.sh und
# dienst.sh richten das Verfahren gleich mit ein.
#
# Warum das von Hand laufen muss: die Signaturpruefung der Sticks stuetzt
# sich auf eine Schluesselliste, die auf dem RECHNER liegt. Vor der
# Erstinstallation gibt es die dort nicht. Also muss das Vertrauen einmal
# auf einem anderen Weg entstehen als ueber den Stick -- durch einen
# Menschen, der den Fingerabdruck am Telefon vergleicht. Genau einmal.

set -u
STICK="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

blau() { printf '\n\033[1;34m== %s\033[0m\n' "$1"; }
gut()  { printf '   \033[32mok\033[0m   %s\n' "$1"; }
warn() { printf '   \033[33m!\033[0m    %s\n' "$1"; }
fehl() { printf '   \033[31mFEHLT\033[0m %s\n' "$1"; }

printf '\n\033[1;34m'
printf '  Devarenu -- Update-Verfahren einrichten\n'
printf '\033[0m'

[ "$(id -u)" = "0" ] || {
  fehl "Das hier braucht root."
  echo "   Noch einmal mit:  sudo bash $0"
  exit 1; }

# ---------------------------------------------------------------- Ordner
blau "Devarenu finden"

ORDNER="${1:-}"
if [ -z "$ORDNER" ] && [ -f /etc/systemd/system/devarenu.service ]; then
  # Der eingerichtete Dienst weiss es am besten -- besser als jedes Raten
  # ueber /home.
  ORDNER="$(sed -n 's/^WorkingDirectory=//p' \
            /etc/systemd/system/devarenu.service | head -1)"
  [ -n "$ORDNER" ] && gut "aus der Unit: $ORDNER"
fi
if [ -z "$ORDNER" ]; then
  for k in /home/*/Devarenu /root/Devarenu /opt/Devarenu; do
    [ -d "$k/.git" ] && { ORDNER="$k"; gut "gefunden: $ORDNER"; break; }
  done
fi
if [ -z "$ORDNER" ] || [ ! -d "$ORDNER/.git" ]; then
  fehl "Devarenu nicht gefunden."
  echo "   Ordner angeben:  sudo bash $0 /pfad/zu/Devarenu"
  exit 1
fi
cd "$ORDNER"

BENUTZER="$(stat -c %U "$ORDNER")"
gut "gehoert $BENUTZER"
als_benutzer() {
  if [ "$BENUTZER" != "root" ]; then runuser -u "$BENUTZER" -- "$@"
  else "$@"; fi
}

# ---------------------------------------------------------------- Stick
blau "Stick nachsehen"

for datei in upd-dev.txt devarenu.bundle schluessel.erlaubt; do
  [ -f "$STICK/$datei" ] || { fehl "$datei fehlt auf dem Stick"; exit 1; }
done
gut "upd-dev.txt, devarenu.bundle, schluessel.erlaubt"

VERSION="$(tr -d '\r' < "$STICK/upd-dev.txt" \
  | sed -n 's/^[[:space:]]*version[[:space:]]*=[[:space:]]*v\{0,1\}\([0-9][0-9A-Za-z.-]*\).*/\1/p' \
  | head -1)"
[ -n "$VERSION" ] || { fehl "upd-dev.txt nennt keine Fassung"; exit 1; }
HIER="$(tr -d '\r' < VERSION 2>/dev/null | head -1 | tr -d ' ')"
gut "Stick bringt $VERSION, hier laeuft ${HIER:-unbekannt}"

SCHMUTZ="$(als_benutzer git status --porcelain --untracked-files=no)"
if [ -n "$SCHMUTZ" ]; then
  fehl "Im Ordner liegen lokale Aenderungen. Abgebrochen, nichts angefasst."
  printf '%s\n' "$SCHMUTZ" | sed 's/^/     /'
  echo "   Erst klaeren, dann noch einmal."
  exit 1
fi
gut "keine lokalen Aenderungen"

# ------------------------------------------------------------ Vertrauen
blau "Schluessel bestaetigen"

cat <<'ENDE'
   Auf dem Stick liegt eine Schluesselliste. Ab jetzt wird jedes weitere
   Update gegen sie geprueft -- deshalb muss genau hier einmal jemand
   hinsehen.

   Der Fingerabdruck unten muss mit dem uebereinstimmen, den Sie von
   Maurice bekommen haben. NICHT ueber den Stick vergleichen und nicht
   ueber eine Datei darauf: fragen Sie nach, am Telefon oder persoenlich.
   Stimmt er nicht, brechen Sie ab.

ENDE

awk '!/^#/ && NF {$1=""; print substr($0,2)}' "$STICK/schluessel.erlaubt" \
  > /run/devarenu-bootstrap-keys
ANZAHL=0
while read -r zeile; do
  [ -z "$zeile" ] && continue
  printf '%s\n' "$zeile" > /run/devarenu-bootstrap-einzeln
  printf '     %s\n' "$(ssh-keygen -lf /run/devarenu-bootstrap-einzeln 2>/dev/null \
                        || echo '(nicht lesbar)')"
  ANZAHL=$((ANZAHL + 1))
done < /run/devarenu-bootstrap-keys
rm -f /run/devarenu-bootstrap-keys /run/devarenu-bootstrap-einzeln
[ "$ANZAHL" -gt 0 ] || { fehl "Die Schluesselliste auf dem Stick ist leer"; exit 1; }

echo
read -rp "   Stimmt der Fingerabdruck? [j/N] " antwort
case "${antwort:-n}" in
  [jJyY]*) gut "bestaetigt" ;;
  *) echo; warn "Abgebrochen. Nichts wurde geaendert."
     echo "   Das ist die richtige Entscheidung, wenn etwas nicht stimmt."
     exit 1 ;;
esac

# ------------------------------------------------------------ Signatur
blau "Update pruefen"

command -v git >/dev/null || { fehl "git fehlt"; exit 1; }

als_benutzer git bundle verify "$STICK/devarenu.bundle" >/dev/null 2>&1 \
  || { fehl "Das Bundle auf dem Stick ist beschaedigt"; exit 1; }
gut "Bundle ist unversehrt"

REF="refs/stick/v$VERSION"
als_benutzer git update-ref -d "$REF" 2>/dev/null
als_benutzer git fetch --quiet "$STICK/devarenu.bundle" \
  "refs/tags/v$VERSION:$REF" 2>/dev/null \
  || { fehl "Im Bundle steckt kein Tag v$VERSION"; exit 1; }
gut "Tag v$VERSION geholt"

# Hier ausnahmsweise gegen die Liste VOM STICK -- auf dem Rechner gibt es
# noch keine. Genau deshalb stand die Bestaetigung oben davor. Ab dem
# naechsten Stick wird gegen die Liste im Ordner geprueft, und die
# Ausnahme ist vorbei.
install -m 644 "$STICK/schluessel.erlaubt" /run/devarenu-bootstrap.erlaubt
if ! als_benutzer git -c gpg.ssh.allowedSignersFile=/run/devarenu-bootstrap.erlaubt \
     verify-tag "$REF" >/dev/null 2>&1; then
  fehl "Die Signatur von v$VERSION stimmt nicht."
  echo "   Der Stick wird nicht eingespielt. Bitte bei Maurice melden."
  rm -f /run/devarenu-bootstrap.erlaubt
  als_benutzer git update-ref -d "$REF"
  exit 1
fi
rm -f /run/devarenu-bootstrap.erlaubt
gut "Signatur von v$VERSION ist gueltig"

# ---------------------------------------------------------------- Dienst
blau "Einspielen"

# Vorspulen und nicht auschecken, damit der Zweig samt Gegenstueck heil
# bleibt. Naeheres in stick_update.sh.
ZWEIG="$(als_benutzer git rev-parse --abbrev-ref HEAD)"
[ "$ZWEIG" != "HEAD" ] || { fehl "HEAD ist abgeloest. Erst auf einen Zweig stellen."; exit 1; }
ALT="$(als_benutzer git rev-parse HEAD)"
als_benutzer git update-ref refs/devarenu/vorher "$ALT"

# ^{commit} und nicht das Tag: sonst prueft git die Signatur ein zweites
# Mal, findet die Liste nicht und meldet einen Fehler, obwohl es gelingt.
# Naeheres in stick_update.sh.
if ! als_benutzer git merge --ff-only --quiet "$REF^{commit}" 2>/dev/null; then
  fehl "Das Update baut nicht auf dem Stand dieses Rechners auf."
  echo "   Vorspulen geht nicht. Nachsehen mit:"
  echo "     git log --oneline HEAD..$REF"
  exit 1
fi
gut "auf v$VERSION vorgespult"

if [ -d "$STICK/wheels" ] \
   && ! als_benutzer git diff --quiet "$ALT" HEAD -- requirements.txt; then
  echo "   requirements.txt hat sich geaendert, Pakete vom Stick..."
  als_benutzer "$ORDNER/.venv/bin/python" -m pip install --quiet --no-index \
    --find-links "$STICK/wheels" -r requirements.txt \
    && gut "Pakete installiert" \
    || warn "pip hat etwas beanstandet. Nachsehen, bevor der Sabbat kommt."
fi

# Ab hier liegt dienst.sh in der neuen Fassung vor und kennt --stick.
blau "Verfahren einrichten"
if bash ./dienst.sh --stick; then
  gut "udev-Regel, Units und Timer stehen"
else
  fehl "Einrichten fehlgeschlagen. Der Code ist eingespielt, aber ein"
  fehl "Stick loest noch nichts aus. Nachholen mit: sudo ./dienst.sh --stick"
fi

blau "Dienst neu starten"
if systemctl list-unit-files 2>/dev/null | grep -q '^devarenu\.service'; then
  systemctl restart devarenu && gut "devarenu neu gestartet" \
    || fehl "Neustart fehlgeschlagen. Nachsehen: journalctl -u devarenu -n 30"
else
  warn "Kein Dienst eingerichtet. Von Hand starten mit ./start.sh"
fi

blau "Fertig"
cat <<ENDE
   Devarenu laeuft jetzt in Fassung $VERSION.

   Ab sofort genuegt es, einen Update-Stick einzusteckt. Der Rechner
   prueft ihn von allein und spielt das Update ein, sobald die
   Uebersetzung angehalten ist. Am Pult steht unter Einrichtung, was
   gerade ansteht.

   Der Stick kann jetzt abgezogen werden.
ENDE
