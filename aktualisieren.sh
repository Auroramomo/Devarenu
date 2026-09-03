#!/usr/bin/env bash
# Devarenu auf den neuesten Stand bringen.
#
#     ./aktualisieren.sh
#
# Holt die Aenderungen, ergaenzt fehlende Abhaengigkeiten, startet den
# Dienst neu und prueft am Ende mit dem Selbsttest, ob die Kette noch
# laeuft.
#
# Was hier NICHT passiert: nichts wird ueberschrieben, was jemand vor Ort
# geaendert hat. Gibt es lokale Aenderungen oder waere die
# Zusammenfuehrung mehr als ein Vorspulen, bricht das Skript ab und sagt
# es. Ein Gemeinderechner ist kein Ort fuer automatische Konfliktloesung.
#
# zustand.json wird nicht angefasst. Sie steht in .gitignore, und zur
# Sicherheit wird vorher und nachher verglichen.

set -u
ORDNER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ORDNER"

NAME=devarenu
blau() { printf '\n\033[1;34m== %s\033[0m\n' "$1"; }
gut()  { printf '   \033[32mok\033[0m   %s\n' "$1"; }
warn() { printf '   \033[33m!\033[0m    %s\n' "$1"; }
fehl() { printf '   \033[31mFEHLT\033[0m %s\n' "$1"; }

pruefsumme() {
  [ -f zustand.json ] || { echo "keine"; return; }
  # Inhalt und Rechte, beides zaehlt: das WLAN-Passwort steht im Klartext
  # darin und soll 0600 bleiben.
  printf '%s %s' "$(sha256sum zustand.json | cut -d' ' -f1)" \
                 "$(stat -c %a zustand.json)"
}

VORHER="$(pruefsumme)"
ALT="$(cat VERSION 2>/dev/null || echo unbekannt)"

# ---------------------------------------------------------------- pruefen
blau "Vorher nachsehen"
command -v git >/dev/null || { fehl "git fehlt. Nachholen und erneut."; exit 1; }
[ -d .git ] || { fehl "Kein git-Arbeitsverzeichnis. Dann gibt es nichts zu holen."
                 exit 1; }

SCHMUTZ="$(git status --porcelain --untracked-files=no)"
if [ -n "$SCHMUTZ" ]; then
  fehl "Es gibt lokale Aenderungen. Abgebrochen, nichts angefasst."
  echo
  printf '%s\n' "$SCHMUTZ" | sed 's/^/     /'
  echo
  echo "   Entweder sichern und zuruecknehmen:"
  echo "     git diff > ~/devarenu-aenderungen.patch && git checkout -- ."
  echo "   Oder ansehen, was da steht, und dann entscheiden."
  exit 1
fi
gut "keine lokalen Aenderungen"

# ---------------------------------------------------------------- holen
blau "Aenderungen holen"
git fetch --quiet || { fehl "git fetch fehlgeschlagen. Netz?"; exit 1; }

OBEN="$(git rev-parse --abbrev-ref --symbolic-full-name @{u} 2>/dev/null || true)"
if [ -z "$OBEN" ]; then
  warn "Kein Gegenstueck eingestellt (kein origin). Es gibt nichts zu holen."
elif [ "$(git rev-parse HEAD)" = "$(git rev-parse @{u})" ]; then
  gut "schon auf dem neuesten Stand ($OBEN)"
elif git merge-base --is-ancestor HEAD @{u}; then
  git pull --ff-only --quiet || { fehl "git pull fehlgeschlagen"; exit 1; }
  gut "geholt von $OBEN"
elif git merge-base --is-ancestor @{u} HEAD; then
  # Hier liegt mehr als auf dem Server. Kein Fehler, aber auch nichts zu
  # tun -- und schon gar nichts zu ueberschreiben.
  warn "Der Stand hier ist neuer als $OBEN. Nichts zu holen."
  warn "Ungesendetes:  git log --oneline $OBEN..HEAD"
else
  fehl "Der Stand hier ist nicht bloss aelter, er ist auseinandergelaufen."
  echo "   Vorspulen geht nicht, und zusammenfuehren entscheidet dieses"
  echo "   Skript nicht. Nachsehen mit:  git log --oneline HEAD..$OBEN"
  exit 1
fi

NEU="$(cat VERSION 2>/dev/null || echo unbekannt)"
if [ "$ALT" = "$NEU" ]; then gut "Fassung $NEU (unveraendert)"
else gut "Fassung $ALT -> $NEU"; fi

# ---------------------------------------------------------------- Pakete
blau "Abhaengigkeiten"
echo "   einrichten.sh ergaenzt nur, was fehlt."
bash ./einrichten.sh
EINRICHTEN=$?

# ---------------------------------------------------------------- Dienst
blau "Dienst"
if systemctl list-unit-files 2>/dev/null | grep -q "^$NAME\.service"; then
  if sudo systemctl restart $NAME; then
    gut "$NAME neu gestartet"
  else
    fehl "Neustart fehlgeschlagen. Nachsehen: journalctl -u $NAME -n 30"
  fi
else
  warn "Kein Dienst installiert. Von Hand starten mit ./start.sh"
  warn "Einrichten mit: ./dienst.sh"
fi

# ---------------------------------------------------------------- Zustand
blau "Einstellungen"
NACHHER="$(pruefsumme)"
if [ "$VORHER" = "$NACHHER" ]; then
  gut "zustand.json unveraendert"
else
  fehl "zustand.json hat sich geaendert. Das darf ein Update nicht."
  echo "     vorher:  $VORHER"
  echo "     nachher: $NACHHER"
fi

blau "Ergebnis"
if [ "$EINRICHTEN" = "0" ]; then
  printf '   \033[32mAlles bereit.\033[0m Fassung %s\n\n' "$NEU"
else
  printf '   \033[33mDer Selbsttest hat etwas beanstandet.\033[0m Oben nachlesen.\n'
  printf '   Wiederholen mit:  .venv/bin/python selbsttest.py\n\n'
fi
exit $EINRICHTEN
