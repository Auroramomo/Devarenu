#!/usr/bin/env bash
# Was im Repo steht, steht oeffentlich. Dieses Skript sucht, was dort
# nicht hingehoert.
#
#   bash oeffentlich_pruefen.sh          alles pruefen
#   bash oeffentlich_pruefen.sh --liste  nur zeigen, wonach gesucht wird
#
# Geprueft wird der GANZE Baum, nicht nur was sich geaendert hat. Der
# Anlass: in sender/LIESMICH.md standen Ordnernamen vom Arbeitsrechner
# (~/Videos/..., /mnt/B/...). Gesehen wurde es erst nach dem Push. Die
# Geschichte laesst sich nicht umschreiben -- das naechste Mal soll es
# vorher auffallen.
#
# Kein Hook. Es gehoert in die Release-Checkliste, vor den Tag, und
# soll gelesen werden -- nicht im Hintergrund durchlaufen und
# uebersehen werden.
#
# Rueckgabe 0, wenn nichts uebrig bleibt.

set -u
ORDNER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ORDNER"

blau() { printf '\n\033[1;34m== %s\033[0m\n' "$*"; }
gut()  { printf '   \033[32mok\033[0m    %s\n' "$*"; }
fehl() { printf '   \033[31mFUND\033[0m  %s\n' "$*"; }
info() { printf '         %s\n' "$*"; }

# ------------------------------------------------------------ Ausnahmen
# Jede Zeile mit Begruendung. Eine Ausnahme ohne Begruendung ist eine
# Ausrede -- in einem halben Jahr weiss niemand mehr, warum sie dasteht.
#
# Geschrieben als <datei>:<muster>. Beides muss passen, damit die Zeile
# durchgeht; so deckt eine Ausnahme nicht versehentlich den ganzen Baum.
AUSNAHMEN=(
  # Der Urheberrechtsvermerk. Er MUSS den Namen nennen, sonst ist die
  # Lizenz nichts wert.
  "LICENSE:Maurice Wessel"

  # DIE eine Stelle fuer Name und Adresse des Betreuers. Alles andere
  # -- bootstrap.sh, die Batchdatei, der Fehler-Dialog, die
  # Glossar-Nachricht -- liest von dort. Steht der Name woanders im
  # Repo, schlaegt diese Pruefung an, und das ist richtig so.
  "betreuer.txt:Momo"
  "betreuer.txt:maurice.wessel@adventisten.de"

  # Der oeffentliche Teil des Signaturschluessels, mit der Adresse als
  # Kennung. Genau dafuer ist die Datei da: ohne sie wird kein Stick
  # angenommen. Ein oeffentlicher Schluessel ist zum Veroeffentlichen
  # gemacht.
  "schluessel.erlaubt:maurice.wessel@adventisten.de"

  # Kein Netz, sondern der uebliche Griff, die eigene Adresse zu
  # finden: ein UDP-Socket wird auf eine nicht erreichbare Adresse
  # gerichtet, ohne ein Paket zu senden. Danach steht die eigene
  # Adresse im Socket.
  "server.py:10.255.255.255"

  # Platzhalter in einer Aufrufzeile. "name" ist nicht der Name eines
  # Menschen, sondern die Stelle, an der einer stehen wird.
  "stick_bauen.sh:/run/media/name/STICK"
)

ausgenommen() {   # $1 = Datei, $2 = Fundtext
  local eintrag datei muster
  for eintrag in "${AUSNAHMEN[@]}"; do
    datei="${eintrag%%:*}"
    muster="${eintrag#*:}"
    [ "$1" = "$datei" ] || continue
    case "$2" in *"$muster"*) return 0 ;; esac
  done
  return 1
}

# Verfolgte UND noch nicht verfolgte Dateien. Was .gitignore abdeckt,
# bleibt aussen vor -- das wird nie veroeffentlicht.
#
# Die noch nicht verfolgten gehoeren ausdruecklich dazu: eine neue
# Datei, die noch nicht eingecheckt ist, faellt sonst durch die
# Pruefung und steht beim naechsten Commit im Repo. Genau das ist beim
# Bauen dieser Fassung passiert -- die Windows-Batchdatei war noch
# nicht verfolgt und wurde stillschweigend uebersprungen.
DATEIEN=$(git ls-files --cached --others --exclude-standard 2>/dev/null)
if [ -z "$DATEIEN" ]; then
  fehl "Kein git-Repo oder keine verfolgten Dateien."
  exit 1
fi

FUNDE=0

# $1 Ueberschrift  $2 Muster  $3 was daran falsch ist
suchen() {
  local titel="$1" muster="$2" warum="$3" nicht="${4:-}"
  local treffer datei text n=0
  # -I laesst Binaerdateien aus, -n gibt die Zeile.
  while IFS= read -r treffer; do
    [ -n "$treffer" ] || continue
    datei="${treffer%%:*}"
    text="${treffer#*:}"
    text="${text#*:}"
    if ausgenommen "$datei" "$text"; then
      continue
    fi
    # Gegenmuster, falls angegeben. Hier und nicht im Suchmuster:
    # git grep -E ist POSIX und kennt keinen Blick nach vorn. Ein
    # (?!...) findet dort GAR NICHTS -- und eine Pruefung, die still
    # nichts tut, ist schlimmer als keine. Genau das ist passiert.
    if [ -n "$nicht" ] && printf '%s' "$text" | grep -qE "$nicht"; then
      continue
    fi
    [ "$n" = 0 ] && fehl "$titel"
    n=$((n + 1))
    printf '           %s\n' "${treffer:0:150}"
  # Diese Datei selbst bleibt aussen vor. Ihre Ausnahmeliste nennt
  # zwangslaeufig genau das, wonach gesucht wird -- sie faende sich
  # sonst in jedem Durchlauf selbst.
  #
  # Das ist ein blinder Fleck, und er wird unten benannt: wer hier
  # etwas versteckt, dem sieht dieses Skript nicht zu. Gelesen werden
  # muss es trotzdem von Hand.
  done < <(git grep -InE --untracked --exclude-standard "$muster" \
             -- . ':!*.pdf' ':!oeffentlich_pruefen.sh' 2>/dev/null)
  if [ "$n" = 0 ]; then
    gut "$titel"
  else
    info "$warum"
    FUNDE=$((FUNDE + n))
  fi
}

printf '\033[1mDevarenu -- ist das oeffentlich zumutbar?\033[0m   %s\n' \
  "$(date '+%d.%m.%Y %H:%M')"
info "$(printf '%s\n' "$DATEIEN" | wc -l) verfolgte Dateien"

if [ "${1:-}" = "--liste" ]; then
  blau "Wonach gesucht wird"
  info "Benutzerverzeichnisse, fremde Rechnernamen, private Adressen,"
  info "Personennamen, Zugangsdaten, private Schluessel, Tokens."
  blau "Ausnahmen"
  for e in "${AUSNAHMEN[@]}"; do info "$e"; done
  exit 0
fi

blau "Pfade und Rechner"
# /home/<name>/ trifft jeden Benutzernamen, auch kuenftige. Der
# Gemeinderechner heisst devarenu -- der darf dastehen.
suchen "keine fremden Benutzerverzeichnisse" \
  '/home/(devarenu)@|/home/[a-z][a-z0-9_-]+' \
  "Ein Pfad aus dem Arbeitsrechner sagt, wer daran arbeitet und wie es
         dort aussieht. Ersetzen durch ~ oder einen Platzhalter."

# Laufwerke, die es nur auf einem bestimmten Rechner gibt.
suchen "keine fremden Laufwerkspfade" \
  '/(mnt|media|run/media)/[A-Za-z0-9_-]+/' \
  "Ein Einhaengepunkt beschreibt einen einzelnen Rechner."

blau "Netzadressen"
# 10.0.0.x ist das Saalnetz und gehoert hierher. Alles andere private
# gehoert geprueft.
suchen "keine fremden privaten Adressen" \
  '(^|[^0-9.])(192\.168\.[0-9]|172\.(1[6-9]|2[0-9]|3[01])\.|10\.(([1-9][0-9]*)|0\.[1-9])\.)' \
  "Private Adressen verraten den Aufbau eines fremden Netzes.
         10.0.0.x ist das Saalnetz und ausgenommen."

blau "Zugangsdaten"
suchen "keine privaten Schluessel" \
  'BEGIN (RSA |OPENSSH |EC |DSA )?PRIVATE KEY' \
  "Ein privater Schluessel im Repo ist sofort verbrannt."

suchen "keine Passwoerter im Klartext" \
  '(passwor[dt]|passwd|secret|token|api[_-]?key)[[:space:]]*[:=][[:space:]]*["'"'"'][^"'"'"']{4,}' \
  "Sieht nach einem hinterlegten Zugang aus."

blau "Namen"
suchen "keine Personennamen ausser den erlaubten" \
  '\b(Gerrit|Gerd|Momo|Wessel)\b' \
  "Das Repo ist oeffentlich. Wer hier steht, steht dort fuer immer."

# systemd-Vorlagen heissen "devarenu-stick@.service" und sehen aus wie
# eine Adresse. Sie werden als Gegenmuster aussortiert.
suchen "keine Mailadressen ausser der Rueckmeldeadresse" \
  '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}' \
  "Eine Mailadresse im Repo wird von Sammlern gefunden." \
  '@[A-Za-z0-9.-]*\.(service|vorlage|timer|socket)'

blau "Ergebnis"
info "Nicht geprueft: diese Datei selbst. Ihre Ausnahmeliste nennt"
info "dieselben Muster, nach denen sie sucht -- sie faende sich sonst"
info "in jedem Durchlauf. Wer sie aendert, liest sie von Hand."
if [ "$FUNDE" = 0 ]; then
  gut "Sonst nichts gefunden. Das Repo ist so zumutbar."
  exit 0
fi
fehl "$FUNDE Fund(e)."
info "Jeden einzeln ansehen. Gehoert einer wirklich dorthin, kommt er"
info "oben in AUSNAHMEN -- mit einer Zeile, warum."
info ""
info "ACHTUNG: Ein Fund, der schon gepusht ist, laesst sich nicht"
info "zurueckholen. Entfernen hilft fuer die Zukunft, nicht fuer die"
info "Vergangenheit. Ein Zugangsdatum gilt dann als verbrannt."
exit 1
