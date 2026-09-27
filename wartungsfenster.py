#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wann der Rechner ins WLAN darf -- und wann er von selbst ausgeht.

Im Betrieb hat der Gemeinderechner kein Netz nach draussen. Fuer die
Wartung hing bisher jemand vor Ort einen Handy-Hotspot daran. Das
setzt voraus, dass jemand hinfaehrt.

Das Fenster ist die Alternative: an einem festen Wochentag, in einer
festen Stunde, verbindet sich der Rechner mit dem Gemeinde-WLAN, und
danach trennt er sich wieder. Dazwischen ist er so unerreichbar wie
zuvor.

DREI REGELN, DIE NICHT VERHANDELBAR SIND

  * Ausfall heisst ZU. Faellt der Timer aus, bleibt das WLAN getrennt
    -- das Profil steht auf autoconnect no, und nur dieses Modul
    schaltet es ein. Ein vergessenes offenes WLAN ist der Schaden,
    den es zu vermeiden gilt; eine verpasste Wartung ist eine Woche
    Wartezeit.
  * Unklar heisst ZU. Ein unbrauchbarer Wert in netz.json schaltet
    das Fenster ab, nicht auf.
  * Geleitet wird nie. Zwischen WLAN und Saalnetz gibt es keinen Weg,
    im Fenster so wenig wie sonst. Das regelt firewall.sh, und
    pruefen.sh sieht nach.

WAS HIER NICHT PASSIERT

Dieses Modul rechnet nur. Es faehrt nichts herunter, verbindet nichts
und stellt keinen Wecker -- das tut wartungsfenster.sh. Getrennt,
damit sich die Rechnerei pruefen laesst, ohne dass ein Pruefstand
einen Rechner ausschaltet.
"""

import json
import sys
from datetime import datetime, timedelta

import netzzustand

# Wie viel frueher der Wecker zuendet. Der Rechner soll zu Beginn des
# Fensters schon oben sein und nicht erst booten: BIOS, Anmeldung und
# Dienststart brauchen zusammen gut zwei Minuten.
WECKER_VORLAUF_MIN = 5

# Kurz oder ausgeschrieben, Gross- und Kleinschreibung egal -- aber
# nichts darueber hinaus. Der Anfang zu vergleichen waere bequemer und
# liesse "Donnerstag Abend" als Donnerstag durchgehen; wer das
# schreibt, meint aber eine Uhrzeit und nicht einen Tag, und das
# Fenster ginge dann zu einer Zeit auf, die niemand gewollt hat.
TAGE = {"mo": 0, "di": 1, "mi": 2, "do": 3, "fr": 4, "sa": 5, "so": 6,
        "montag": 0, "dienstag": 1, "mittwoch": 2, "donnerstag": 3,
        "freitag": 4, "samstag": 5, "sonnabend": 5, "sonntag": 6}


def _tag(text):
    """Die Wochentagsnummer, oder None."""
    return TAGE.get(str(text).strip().lower())

VORGABE = {
    "an": False,
    "profil": "",
    "wochentag": "Do",
    "von": "18:00",
    "bis": "22:00",
    # Nach so vielen Stunden Laufzeit geht der Rechner aus. Er steht
    # im Gemeindesaal und soll nicht wochenlang durchlaufen, nur weil
    # ihn nach einem Gottesdienst niemand ausgeschaltet hat.
    "hoechstlaufzeit_h": 24,
    # Laeuft dabei eine Uebersetzung, wartet das Auto-Aus -- aber nicht
    # unbegrenzt. Ein Gottesdienst, der zwoelf Stunden "live" meldet,
    # ist keine Predigt, sondern ein Tonstrom, den niemand abgestellt
    # hat. Bis hierher wird gewartet, danach nicht mehr.
    "hoechstlaufzeit_hart_h": 36,
}


def _uhrzeit(text):
    """"18:00" -> (18, 0). None, wenn daraus nichts zu machen ist."""
    try:
        stunde, minute = str(text).split(":")
        stunde, minute = int(stunde), int(minute)
    except Exception:
        return None
    if 0 <= stunde <= 23 and 0 <= minute <= 59:
        return stunde, minute
    return None


def einstellung(netz=None):
    """Der Fensterblock aus netz.json, geprueft. Unklar heisst aus.

    Feld fuer Feld wie in zustand.py: ein verpfuschter Wert kostet nur
    sich selbst -- mit einer Ausnahme. Ist die Zeitangabe unbrauchbar
    oder fehlt das Profil, gilt das GANZE Fenster als aus. Ein Fenster
    mit halben Angaben waere ein WLAN zu einer Zeit, die niemand
    gewollt hat."""
    daten = dict(VORGABE)
    if netz is None:
        netz, _ = netzzustand.laden()
    roh = netz.get("wartungsfenster")
    if not isinstance(roh, dict):
        return daten

    if isinstance(roh.get("an"), bool):
        daten["an"] = roh["an"]
    for feld in ("profil", "wochentag", "von", "bis"):
        if isinstance(roh.get(feld), str):
            daten[feld] = roh[feld]
    for feld in ("hoechstlaufzeit_h", "hoechstlaufzeit_hart_h"):
        wert = roh.get(feld)
        if isinstance(wert, int) and not isinstance(wert, bool) and wert >= 0:
            daten[feld] = wert

    if not daten["profil"].strip():
        daten["an"] = False
    if _tag(daten["wochentag"]) is None:
        daten["an"] = False
    von, bis = _uhrzeit(daten["von"]), _uhrzeit(daten["bis"])
    if von is None or bis is None or von >= bis:
        # Ein Fenster ueber Mitternacht gibt es bewusst nicht: es waere
        # die Sorte Sonderfall, die man einmal schreibt und danach bei
        # jeder Aenderung uebersieht.
        daten["an"] = False
    # Die harte Grenze kann nicht vor der weichen liegen.
    if daten["hoechstlaufzeit_hart_h"] < daten["hoechstlaufzeit_h"]:
        daten["hoechstlaufzeit_hart_h"] = daten["hoechstlaufzeit_h"]
    return daten


def _an_tag(jetzt, e, versatz_tage):
    """(Beginn, Ende) des Fensters an dem Tag, der versatz_tage entfernt ist."""
    tag = (jetzt + timedelta(days=versatz_tage)).date()
    vs, vm = _uhrzeit(e["von"])
    bs, bm = _uhrzeit(e["bis"])
    return (datetime(tag.year, tag.month, tag.day, vs, vm),
            datetime(tag.year, tag.month, tag.day, bs, bm))


def im_fenster(jetzt=None, e=None):
    """Ist gerade Fenster? Aus heisst immer nein."""
    e = e if e is not None else einstellung()
    if not e["an"]:
        return False
    jetzt = jetzt or datetime.now()
    if jetzt.weekday() != _tag(e["wochentag"]):
        return False
    beginn, ende = _an_tag(jetzt, e, 0)
    return beginn <= jetzt < ende


def naechster_beginn(jetzt=None, e=None):
    """Wann das Fenster das naechste Mal aufgeht. None, wenn es aus ist.

    Steht der Rechner mitten im Fenster, ist der naechste Beginn der
    der KOMMENDEN Woche -- der heutige liegt hinter uns. Sonst stellte
    sich der Wecker beim Herunterfahren um 22 Uhr auf 18 Uhr desselben
    Tages, also in die Vergangenheit, und rtcwake wiese ihn ab."""
    e = e if e is not None else einstellung()
    if not e["an"]:
        return None
    jetzt = jetzt or datetime.now()
    ziel = _tag(e["wochentag"])
    for versatz in range(0, 8):
        beginn, _ = _an_tag(jetzt, e, versatz)
        if beginn.weekday() == ziel and beginn > jetzt:
            return beginn
    return None


def wecker_zeit(jetzt=None, e=None):
    """Wann der BIOS-Wecker zuenden soll: kurz VOR dem Fensterbeginn."""
    beginn = naechster_beginn(jetzt, e)
    if beginn is None:
        return None
    return beginn - timedelta(minutes=WECKER_VORLAUF_MIN)


def laufzeit_stunden():
    """Wie lange dieser Rechner schon laeuft. None, wenn unbekannt."""
    try:
        with open("/proc/uptime", encoding="utf-8") as f:
            return float(f.read().split()[0]) / 3600.0
    except Exception:
        return None


def abschalten_faellig(uebersetzung_laeuft, jetzt=None, e=None,
                       stunden=None):
    """("", Grund) -- soll der Rechner jetzt ausgehen, und warum?

    Gibt ("", "") zurueck, wenn nicht. Sonst eine der drei Lagen:

      fensterende   das Fenster ist eben zugegangen
      laufzeit      die weiche Grenze, und es laeuft keine Uebersetzung
      laufzeit_hart die harte Grenze, Uebersetzung hin oder her

    Die Uebersetzung schiebt das Auto-Aus auf, aber nicht auf ewig.
    Ein Rechner, der seit anderthalb Tagen "live" meldet, hat keinen
    Gottesdienst, sondern einen Tonstrom, den niemand abgestellt hat
    -- und der haelt ihn sonst fuer immer wach."""
    e = e if e is not None else einstellung()
    if not e["an"]:
        return "", ""
    stunden = stunden if stunden is not None else laufzeit_stunden()

    if stunden is not None and e["hoechstlaufzeit_hart_h"] \
            and stunden >= e["hoechstlaufzeit_hart_h"]:
        return "laufzeit_hart", (
            f"laeuft seit {stunden:.0f} Stunden -- die harte Grenze von "
            f"{e['hoechstlaufzeit_hart_h']} Stunden ist erreicht")

    if uebersetzung_laeuft:
        return "", ""

    jetzt = jetzt or datetime.now()
    if jetzt.weekday() == _tag(e["wochentag"]):
        _, ende = _an_tag(jetzt, e, 0)
        # Nur im Nachlauf des Fensters, nicht den ganzen Abend. Sonst
        # faehrt ein Rechner, den jemand um 23 Uhr absichtlich
        # einschaltet, sofort wieder herunter.
        if ende <= jetzt < ende + timedelta(minutes=15):
            return "fensterende", "das Wartungsfenster ist zu Ende"

    if stunden is not None and e["hoechstlaufzeit_h"] \
            and stunden >= e["hoechstlaufzeit_h"]:
        return "laufzeit", (
            f"laeuft seit {stunden:.0f} Stunden, laenger als die "
            f"eingestellten {e['hoechstlaufzeit_h']} Stunden")
    return "", ""


def schreiben(werte):
    """Traegt das Fenster in netz.json ein. Gibt Fehler als Liste zurueck.

    Geprueft wird VOR dem Schreiben, und zwar mit derselben Funktion,
    die es spaeter auch liest: einstellung() sagt "an": False, sobald
    irgendetwas nicht stimmt. Was hier durchgeht, geht auch dort
    durch -- sonst schriebe ein --einschalten ein Fenster, das der
    Timer danach wortlos ignoriert, und niemand wuesste warum."""
    fehler = []
    tag = _tag(werte.get("wochentag", ""))
    if tag is None:
        fehler.append(f"Wochentag \"{werte.get('wochentag')}\" kenne ich "
                      f"nicht. Mo Di Mi Do Fr Sa So, oder ausgeschrieben.")
    for feld in ("von", "bis"):
        if _uhrzeit(werte.get(feld)) is None:
            fehler.append(f"{feld}=\"{werte.get(feld)}\" ist keine "
                          f"Uhrzeit. Gemeint ist HH:MM, etwa 18:00.")
    if not str(werte.get("profil", "")).strip():
        fehler.append("Ohne Profil kein Fenster.")
    von, bis = _uhrzeit(werte.get("von")), _uhrzeit(werte.get("bis"))
    if von and bis and von >= bis:
        fehler.append(f"{werte['von']} liegt nicht vor {werte['bis']}. "
                      f"Ein Fenster ueber Mitternacht gibt es nicht.")
    if fehler:
        return fehler

    netz, _ = netzzustand.laden()
    # Was schon dasteht, bleibt stehen: wer nur die Uhrzeit aendert,
    # soll die Laufzeitgrenzen nicht verlieren.
    block = dict(VORGABE)
    block.update(netz.get("wartungsfenster") or {})
    block.update(werte)
    block["an"] = True
    netz["wartungsfenster"] = block
    netzzustand.speichern(netz)
    return []


def abschalten():
    """Schaltet das Fenster aus. Die Werte bleiben stehen.

    Geloescht wird nichts: wer es naechste Woche wieder einschaltet,
    soll Profil und Uhrzeit nicht neu eintippen muessen."""
    netz, _ = netzzustand.laden()
    block = dict(VORGABE)
    block.update(netz.get("wartungsfenster") or {})
    block["an"] = False
    netz["wartungsfenster"] = block
    netzzustand.speichern(netz)


def _ausgeben(e, jetzt):
    """Maschinenlesbar, eine Zeile je Auskunft -- fuer die Shell."""
    beginn = naechster_beginn(jetzt, e)
    wecker = wecker_zeit(jetzt, e)
    print(f"an={'ja' if e['an'] else 'nein'}")
    print(f"profil={e['profil']}")
    print(f"im_fenster={'ja' if im_fenster(jetzt, e) else 'nein'}")
    print(f"beginn={beginn.strftime('%Y-%m-%d %H:%M') if beginn else ''}")
    # Als Unix-Sekunde: rtcwake bekommt sie so, und die Umrechnung von
    # Ortszeit auf die UTC der Hardware-Uhr passiert an genau EINER
    # Stelle. Sommerzeit inbegriffen -- timestamp() kennt sie.
    print(f"wecker={int(wecker.timestamp()) if wecker else ''}")
    print(f"wecker_lesbar={wecker.strftime('%Y-%m-%d %H:%M') if wecker else ''}")
    print(f"hoechstlaufzeit_h={e['hoechstlaufzeit_h']}")
    print(f"hoechstlaufzeit_hart_h={e['hoechstlaufzeit_hart_h']}")
    stunden = laufzeit_stunden()
    print(f"laufzeit_h={stunden:.2f}" if stunden is not None else "laufzeit_h=")


if __name__ == "__main__":
    # --setzen profil=... wochentag=... von=... bis=...
    # Aufgerufen von wartungsfenster.sh --einschalten; von Hand geht es
    # auch, aber das Skript stellt zusaetzlich autoconnect no.
    if "--setzen" in sys.argv:
        werte = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
        probleme = schreiben(werte)
        for satz in probleme:
            print(satz, file=sys.stderr)
        sys.exit(1 if probleme else 0)
    if "--aus" in sys.argv:
        abschalten()
        sys.exit(0)
    e = einstellung()
    jetzt = datetime.now()
    if "--json" in sys.argv:
        print(json.dumps(e, indent=2, ensure_ascii=False))
    else:
        _ausgeben(e, jetzt)
