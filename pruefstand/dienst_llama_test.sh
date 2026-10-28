#!/usr/bin/env bash
# Wer llama-server einrichtet -- und wer nicht (0.5.2, 28.10.2026).
#
#   bash pruefstand/dienst_llama_test.sh
#
# Seit dem Nachtrag vom 28.10.2026 gibt es EINEN Weg: llama_einrichten.py.
# 1) Die Unit-Vorlage traegt die gemessenen Werte (B3) und lauscht nur
#    auf 127.0.0.1; Conflicts=ollama.service.
# 2) dienst.sh --llama ruft llama_einrichten.py auf und schreibt keine
#    Unit mehr selbst.
# 3) Von den Update-Wegen ruft NUR aktualisierung.sh den Schritt auf
#    (sie laeuft auf jedem Weg, als root). Kern, Fenster und Stick-Kern
#    tun es nicht noch einmal daneben; niemand installiert llama.cpp
#    ueber einen Paketmanager, und niemand schaltet Ollama an
#    llama_einrichten.py vorbei ab.
set -u
ECHT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FEHLER=0
pruefe() {
  if [ "$2" = "$3" ]; then printf '   ok    %s\n' "$1"
  else printf '   \033[31mFEHL\033[0m  %s: erwartet %s, ist %s\n' "$1" "$2" "$3"
       FEHLER=$((FEHLER+1)); fi
}
titel() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
ohne_kommentar() { grep -v '^\s*#' "$1"; }

titel "1) Die Vorlage"
V="$ECHT/devarenu-llama.service.vorlage"
pruefe "es gibt sie" ja "$([ -f "$V" ] && echo ja || echo nein)"
pruefe "nur 127.0.0.1" ja "$(grep -q -- '--host 127.0.0.1 ' "$V" && echo ja || echo nein)"
pruefe "Werte aus B3: -c 16384 -np 4" ja \
  "$(grep -q -- '-c 16384 -np 4' "$V" && echo ja || echo nein)"
pruefe "Name wie config.LLAMA_MODELL" ja \
  "$(grep -q -- '--alias gemma4-12b' "$V" && echo ja || echo nein)"
pruefe "Conflicts=ollama.service" ja \
  "$(grep -q '^Conflicts=ollama.service' "$V" && echo ja || echo nein)"

titel "2) dienst.sh --llama"
pruefe "ruft llama_einrichten.py auf" ja \
  "$(sed -n '/= "--llama" \]/,/^fi/p' "$ECHT/dienst.sh" \
     | grep -q 'llama_einrichten.py' && echo ja || echo nein)"
pruefe "schreibt keine Unit mehr selbst" nein \
  "$(ohne_kommentar "$ECHT/dienst.sh" | grep -q 'devarenu-llama.service.vorlage' \
     && echo ja || echo nein)"

titel "3) Die Update-Wege"
pruefe "aktualisierung.sh ruft llama_einrichten.py" ja \
  "$(ohne_kommentar "$ECHT/aktualisierung.sh" | grep -q 'llama_einrichten.py' \
     && echo ja || echo nein)"
for f in aktualisieren.sh stick_update.sh wartungsfenster.sh; do
  pruefe "$f ruft es nicht noch einmal daneben" nein \
    "$(ohne_kommentar "$ECHT/$f" | grep -q -E 'llama_einrichten|dienst\.sh --llama' \
       && echo ja || echo nein)"
done
for f in aktualisieren.sh aktualisierung.sh stick_update.sh wartungsfenster.sh; do
  T="$(ohne_kommentar "$ECHT/$f")"
  pruefe "$f schaltet Ollama nicht selbst ab" nein \
    "$(printf '%s' "$T" | grep -q -E '(disable|stop|mask)[^|;]*ollama' && echo ja || echo nein)"
  pruefe "$f installiert kein llama.cpp ueber einen Paketmanager" nein \
    "$(printf '%s' "$T" | grep -q -E '(pacman|apt(-get)?|dnf|snap)[^|;]*llama' && echo ja || echo nein)"
done

printf '\n'
if [ "$FEHLER" = 0 ]; then printf '\033[32mAlle Faelle wie erwartet.\033[0m\n'
else printf '\033[31m%d Fehler.\033[0m\n' "$FEHLER"; fi
exit "$FEHLER"
