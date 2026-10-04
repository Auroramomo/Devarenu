#!/usr/bin/env bash
# Eine kurze Nachricht nach draussen -- fuer das, was unbeaufsichtigt
# passiert ist.
#
#   bash meldung.sh "Betreff" "Text"        senden (und merken)
#   bash meldung.sh --nachreichen           Liegengebliebenes senden
#   bash meldung.sh --berichte              Fehlerberichte abschicken
#   bash meldung.sh --zeigen                ist das eingerichtet?
#
# WOZU
#
# Seit 0.3.3 kann sich der Rechner im Wartungsfenster selbst
# aktualisieren. Wenn niemand dabei ist, muss er hinterher sagen, was
# geschehen ist -- sonst merkt man ein gescheitertes Update erst am
# Sabbat.
#
# WAS HINAUSGEHT UND WAS NICHT
#
# Fassung vorher und nachher, Ergebnis, Selbsttest, Dauer. SONST
# NICHTS. Kein Predigttext, kein WLAN-Name, kein Passwort, keine
# Adresse, kein Personenname. Wer den Kanal mitliest, erfaehrt, dass
# irgendwo ein Devarenu von 0.3.3 auf 0.3.4 gegangen ist -- mehr
# nicht. Der Aufrufer stellt den Text zusammen; diese Datei schickt
# ihn nur.
#
# WARUM ntfy UND NICHT TELEGRAM
#
# Beides waere ein curl-Aufruf. Der Unterschied liegt im Schaden
# eines Lecks: ein Telegram-Bot-Token ist ein Schluessel, mit dem
# jemand den Bot STEUERT. Ein ntfy-Thema ist eine Adresse, unter der
# jemand MITLIEST. Bei dem, was hier hinausgeht, ist Mitlesen
# hinnehmbar und Steuern nicht.
#
# DIE ZUGANGSDATEN
#
# In meldung.json neben dieser Datei, 600, in .gitignore. NICHT in
# netz.json: die wird mit 644 geschrieben und ist fuer jeden lesbar.
#
#   {"ntfy": "https://ntfy.sh/<thema>"}
#
# <thema> ist dabei wirklich zu ersetzen -- hier steht mit Absicht
# kein Beispiel, das wie eine echte Adresse aussieht:
# oeffentlich_pruefen.sh sucht nach genau solchen und wuerde diese
# Datei sonst bei jedem Durchlauf beanstanden.
#
# Das Thema ist das ganze Geheimnis -- es gibt kein Passwort. Also
# lang und zufaellig:
#
#   echo "devarenu-$(head -c 18 /dev/urandom | base32 | tr -d = | tr 'A-Z' 'a-z')"

set -u
ORDNER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ORDNER"

KONF="$ORDNER/meldung.json"
# Was noch nicht hinausging. Eine Meldung soll nicht verlorengehen,
# nur weil das WLAN im falschen Augenblick weg war -- der naechste
# Lauf nimmt sie mit.
OFFEN="$ORDNER/meldung-offen.txt"
CURL="${DEVARENU_CURL:-curl}"

ziel() {
  [ -f "$KONF" ] || return 1
  "$ORDNER/.venv/bin/python" - "$KONF" <<'PYCODE' 2>/dev/null
import json, sys
try:
    d = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception:
    raise SystemExit
url = str(d.get("ntfy") or "").strip()
if url.startswith("https://") or url.startswith("http://"):
    print(url)
PYCODE
}

senden() {  # $1 Betreff, $2 Text -- Rueckgabe 0, wenn es hinausging
  local url; url="$(ziel)" || return 1
  [ -n "$url" ] || return 1
  $CURL -fsS -m 20 \
    -H "Title: $1" \
    -H "Tags: devarenu" \
    -d "$2" \
    "$url" >/dev/null 2>&1
}

merken() {  # Liegengebliebenes, eine Zeile je Meldung
  printf '%s\t%s\t%s\n' "$(date '+%Y-%m-%d %H:%M')" "$1" \
    "$(printf '%s' "$2" | tr '\n' '~')" >> "$OFFEN"
  chmod 600 "$OFFEN" 2>/dev/null || true
}

nachreichen() {
  [ -s "$OFFEN" ] || return 0
  local rest="$OFFEN.rest"; : > "$rest"
  local zeit betreff text
  while IFS=$'\t' read -r zeit betreff text; do
    [ -n "${betreff:-}" ] || continue
    if senden "$betreff (nachgereicht)" \
              "$(printf '%s' "$text" | tr '~' '\n')
(vom $zeit)"; then
      continue
    fi
    printf '%s\t%s\t%s\n' "$zeit" "$betreff" "$text" >> "$rest"
  done < "$OFFEN"
  mv "$rest" "$OFFEN"
  [ -s "$OFFEN" ] || rm -f "$OFFEN"
}

# ------------------------------------------------- Fehlerberichte
# Die Warteschlange aus berichtpost.py. Jeder Bericht geht als
# EIGENE Nachricht hinaus und wird erst danach als gesendet
# vermerkt -- sonst ginge einer verloren, weil das WLAN im falschen
# Augenblick weg war.
#
# Inhalt: nur, was fehlerbericht.bauen() liefert, also nur die
# dortige Erlaubnisliste. Hier wird nichts hinzugefuegt.
berichte_senden() {
  local ordner="$ORDNER/ergebnisse/berichte"
  [ -d "$ordner" ] || return 0
  local offen=0 raus=0 datei
  for datei in "$ordner"/*.txt; do
    [ -f "$datei" ] || continue
    [ -f "${datei%.txt}.gesendet" ] && continue
    offen=$((offen + 1))
    if senden "Devarenu $(hostname): Fehlerbericht" \
              "$(cat "$datei")"; then
      date '+%Y-%m-%d %H:%M:%S' > "${datei%.txt}.gesendet"
      chmod 600 "${datei%.txt}.gesendet" 2>/dev/null || true
      raus=$((raus + 1))
    else
      # Beim ersten Fehlschlag aufhoeren. Steht der Kanal nicht,
      # stehen die naechsten auch nicht -- und jeder Versuch kostet
      # zwanzig Sekunden Zeitueberschreitung.
      break
    fi
  done
  [ "$offen" = 0 ] && return 0
  echo "$raus von $offen Bericht(en) abgeschickt."
  [ "$raus" = "$offen" ]
}

# AUF DEM ENTWICKLUNGSRECHNER GEHT NICHTS HINAUS.
#
# Erkannt an zwei Dingen, beide zusammen: der Marke ENTWICKLUNG im
# Ordner und dem privaten Signierschluessel auf dem Rechner (Begruendung
# in entwicklung.py). Dann wird weder gesendet noch fuer spaeter
# vorgemerkt -- sonst kaeme das Liegengebliebene beim ersten Lauf auf
# einem anderen Weg doch hinaus. Die Marke allein entscheidet nichts;
# sie ist nur der schnelle Weg, Python gar nicht erst zu starten.
entwicklungsrechner() {
  [ -f "$ORDNER/ENTWICKLUNG" ] || return 1
  "$ORDNER/.venv/bin/python" "$ORDNER/entwicklung.py" --pruefen \
    >/dev/null 2>&1
}

if [ "${1:---zeigen}" != "--zeigen" ] && entwicklungsrechner; then
  echo "Entwicklungsrechner (Marke ENTWICKLUNG und privater" \
       "Signierschluessel): es wird nichts gesendet und nichts" \
       "vorgemerkt." >&2
  exit 3
fi

case "${1:---zeigen}" in
  --berichte)
    berichte_senden ;;

  --zeigen)
    if entwicklungsrechner; then
      echo "Entwicklungsrechner: von hier wird nichts gesendet."
    fi
    if [ ! -f "$KONF" ]; then
      echo "Keine Rueckmeldung eingerichtet ($KONF fehlt)."
      echo "Das ist in Ordnung -- dann meldet der Rechner nichts."
      exit 0
    fi
    U="$(ziel || true)"
    if [ -z "$U" ]; then
      echo "$KONF steht da, enthaelt aber kein brauchbares \"ntfy\"."
      exit 1
    fi
    # NICHT die volle Adresse ausgeben: sie ist das ganze Geheimnis,
    # und diese Ausgabe landet in Berichten und Journalen.
    echo "Rueckmeldung eingerichtet: ${U%%/*}//…/${U##*/devarenu-} verkuerzt"
    echo "Liegengeblieben: $([ -s "$OFFEN" ] && wc -l < "$OFFEN" || echo 0)"
    ;;

  --nachreichen)
    nachreichen ;;

  --pruefen)
    senden "Devarenu: Probe" "Nur eine Probe. Wenn das ankommt, stimmt der Kanal." \
      && echo "abgeschickt" || { echo "ging nicht hinaus"; exit 1; } ;;

  *)
    BETREFF="${1:-Devarenu}"; TEXT="${2:-}"
    nachreichen
    if senden "$BETREFF" "$TEXT"; then
      exit 0
    else
      merken "$BETREFF" "$TEXT"
      exit 1
    fi ;;
esac
