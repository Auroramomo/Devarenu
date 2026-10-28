#!/usr/bin/env bash
# Fragt INSTALLIEREN.sh nach dem Dienst mit "Ja" als Vorgabe? (0.5.2)
#
#   bash pruefstand/installieren_dienst_test.sh
#
# Bis 0.5.1 stand dort [j/N]: wer auf der Gemeinde einfach Enter
# drueckte, bekam keinen Dienst, und Devarenu startete nach dem naechsten
# Einschalten nicht von selbst. Fuer den Rechner in der Gemeinde ist der
# Dienst der Normalfall.
#
# Laeuft wird nur der Abschnitt "Systemdienst" aus der ECHTEN Datei, in
# einem Wegwerfordner, mit einer dienst.sh-Attrappe, die mitschreibt.
# Die ganze INSTALLIEREN.sh laesst sich hier nicht fahren: sie
# installiert Pakete.

set -u
ECHT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASIS="$(mktemp -d)"
trap 'rm -rf "$BASIS"' EXIT
FEHLER=0
pruefe() {
  if [ "$2" = "$3" ]; then printf '   ok    %s\n' "$1"
  else printf '   \033[31mFEHL\033[0m  %s: erwartet %s, ist %s\n' "$1" "$2" "$3"
       FEHLER=$((FEHLER+1)); fi
}

if [ ! -d /run/systemd/system ]; then
  echo "   uebersprungen: kein systemd hier, der Abschnitt fragt dann nicht"
  exit 77
fi

# Der Abschnitt zwischen den beiden Ueberschriften, wortgleich.
ABSCHNITT="$BASIS/abschnitt.sh"
sed -n '/^# -* Dienst$/,/^# -* Reparaturvorrat$/p' "$ECHT/INSTALLIEREN.sh" \
  > "$ABSCHNITT"
pruefe "der Abschnitt Systemdienst ist gefunden" ja \
  "$(grep -q 'Als Systemdienst einrichten' "$ABSCHNITT" && echo ja || echo nein)"

antworten() {  # $1 = Eingabe; gibt aus, ob dienst.sh lief
  rm -f "$BASIS/lief"
  printf '#!/usr/bin/env bash\ntouch "%s/lief"\n' "$BASIS" > "$BASIS/dienst.sh"
  (cd "$BASIS" && printf '%s\n' "$1" | bash "$ABSCHNITT" >/dev/null 2>&1)
  [ -f "$BASIS/lief" ] && echo dienst || echo kein-dienst
}

printf '\n\033[1m== Die Frage nach dem Dienst\033[0m\n'
# read -p zeigt den Text nur an einem Terminal. Also aus der Datei.
pruefe "die Frage nennt Ja als Vorgabe: [J/n]" ja \
  "$(grep -q 'Als Systemdienst einrichten? \[J/n\]' "$ABSCHNITT" && echo ja || echo nein)"
pruefe "Enter: dienst.sh laeuft" dienst "$(antworten "")"
pruefe "j: dienst.sh laeuft" dienst "$(antworten "j")"
pruefe "ja: dienst.sh laeuft" dienst "$(antworten "ja")"
pruefe "n: kein Dienst" kein-dienst "$(antworten "n")"
pruefe "nein: kein Dienst" kein-dienst "$(antworten "nein")"

printf '\n'
[ "$FEHLER" = 0 ] || { printf '\033[31m%s Fehler.\033[0m\n' "$FEHLER"; exit 1; }
printf '\033[32mAlle Faelle wie erwartet.\033[0m\n'
