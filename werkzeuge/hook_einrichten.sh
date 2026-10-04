#!/usr/bin/env bash
# Legt den pre-push-Hook an: oeffentlich_pruefen.sh vor jedem Push.
#
#     bash werkzeuge/hook_einrichten.sh
#     bash werkzeuge/hook_einrichten.sh --entfernen
#
# WARUM
#
# Ein Fund, der schon gepusht ist, laesst sich nicht zurueckholen.
# Entfernen hilft fuer die Zukunft, nicht fuer die Vergangenheit; ein
# Zugangsdatum gilt dann als verbrannt. Die Liste in AUFSTELLEN.md
# sagt deshalb seit 0.2.13, dass oeffentlich_pruefen.sh vor dem Push
# zu laufen hat -- und genau daran denkt man an dem Abend nicht, an
# dem man es braucht.
#
# Der Hook liegt in .git/hooks und wird NICHT mitversioniert. Er muss
# darum auf jedem Rechner einmal eingerichtet werden; dieses Skript
# ist der eine Befehl dafuer.
#
# NOTAUSGANG
#
# git push --no-verify geht am Hook vorbei. Das ist Absicht: ein Hook,
# den man nicht umgehen kann, wird irgendwann geloescht statt
# verstanden. Wer ihn umgeht, soll es ausdruecklich tun.
set -u
ORDNER="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ORDNER"

GRUEN="\033[32m"; ROT="\033[31m"; GELB="\033[33m"; AUS="\033[0m"
gut()  { printf "   ${GRUEN}ok${AUS}    %s\n" "$*"; }
fehl() { printf "   ${ROT}FEHL${AUS}  %s\n" "$*"; }
info() { printf "   ${GELB}i${AUS}     %s\n" "$*"; }

HOOKS="$(git rev-parse --git-path hooks 2>/dev/null)"
if [ -z "$HOOKS" ]; then
  fehl "Das hier ist kein Git-Arbeitsverzeichnis."
  exit 1
fi
ZIEL="$HOOKS/pre-push"

if [ "${1:-}" = "--entfernen" ]; then
  if [ -f "$ZIEL" ] && grep -q 'devarenu-hook' "$ZIEL"; then
    rm -f "$ZIEL"
    gut "Hook entfernt: $ZIEL"
  else
    info "Kein Devarenu-Hook da, nichts zu tun."
  fi
  exit 0
fi

# Einen fremden Hook nicht ueberschreiben. Wer sich selbst einen
# gebaut hat, hat einen Grund dafuer.
if [ -f "$ZIEL" ] && ! grep -q 'devarenu-hook' "$ZIEL"; then
  fehl "In $ZIEL liegt schon ein anderer pre-push-Hook."
  info "Er wird NICHT ueberschrieben. Entweder von Hand ergaenzen um:"
  info "    bash oeffentlich_pruefen.sh || exit 1"
  info "oder ihn wegnehmen und dieses Skript noch einmal aufrufen."
  exit 1
fi

mkdir -p "$HOOKS"
cat > "$ZIEL" <<'HOOK'
#!/usr/bin/env bash
# devarenu-hook -- angelegt von werkzeuge/hook_einrichten.sh
#
# Prueft den Baum, bevor etwas das Repo verlaesst. Ein Fund, der
# schon gepusht ist, laesst sich nicht zurueckholen.
#
# Umgehen: git push --no-verify
set -u
ORDNER="$(git rev-parse --show-toplevel)"
if [ ! -f "$ORDNER/oeffentlich_pruefen.sh" ]; then
  echo "pre-push: oeffentlich_pruefen.sh fehlt -- Push geht durch."
  exit 0
fi
echo "pre-push: oeffentlich_pruefen.sh laeuft ..."
if bash "$ORDNER/oeffentlich_pruefen.sh"; then
  exit 0
fi
cat <<'ENDE'

  ================================================================
   PUSH ABGEBROCHEN
  ================================================================

  oeffentlich_pruefen.sh hat etwas gefunden. Jeden Fund einzeln
  ansehen. Gehoert einer wirklich ins Repo, kommt er oben in die
  Ausnahmeliste des Skripts -- mit einer Zeile, warum.

  Ein Fund, der schon gepusht ist, laesst sich nicht zurueckholen.

  Wenn es trotzdem raus soll:  git push --no-verify

ENDE
exit 1
HOOK
chmod +x "$ZIEL"
gut "Hook angelegt: $ZIEL"
info "Ein Push mit Fund bricht ab. Umgehen: git push --no-verify"
info "Wieder weg mit:  bash werkzeuge/hook_einrichten.sh --entfernen"
