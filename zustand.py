#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Was pro Gemeinde abweicht, ueber den Neustart hinweg.

config.py gilt fuer alle Gemeinden gleich und wird beim Aktualisieren
ueberschrieben. Hier steht, was diesem Rechner gehoert: Aufnahmegeraet,
Sprachen, WLAN und die eingemessene Mindestlautstaerke. Die Trennung ist
der ganze Zweck der Datei -- sonst kostet jedes Update dem Techniker
seine Einstellungen.

Geschrieben wird bei jeder Aenderung sofort, nicht erst beim Beenden.
Ein Rechner im Gemeindesaal wird selten sauber heruntergefahren, und was
beim Ausschalten verloren geht, muss am naechsten Sabbat neu eingetragen
werden.

Die Datei enthaelt das WLAN-Passwort im Klartext und bekommt deshalb
0600. In .gitignore steht sie ohnehin.
"""

import json
import os
import threading
import time
from pathlib import Path

import config

DATEI = config.BASIS / "zustand.json"

# Steht mit in der Datei, damit ein spaeteres Format erkennbar ist, ohne
# raten zu muessen, was die Schluessel bedeuten.
#
# 2 hat geraet_kanal und geraet_kanaele dazubekommen. Eine Datei nach
# Fassung 1 hat sie nicht, und das ist kein Fehlerfall: die Vorgaben 0
# und 1 beschreiben genau, was vorher galt -- erster Kanal, mono.
#
# 3 hat glossar_quittiert. Das kam schon mit 0.2.11, ohne die Fassung
# hochzusetzen -- ein Versehen, das hier nachgeholt wird.
FASSUNG = 3

# Bis 0.2.11 wurde die Fassung GESCHRIEBEN, aber nie gelesen. Es gab
# keine Umzugsschritte, keine Sicherung, und _uebernehmen kopierte Feld
# fuer Feld in die Vorgabe -- ein Schluessel, den diese Fassung nicht
# kennt, war nach dem naechsten Speichern weg. Gemessen an einer Datei
# mit einem zusaetzlichen Schluessel: nach dem Laden nicht mehr da,
# nach dem Speichern aus der Datei verschwunden.
#
# Das ist der Grund, warum Einstellungen ein Update ueberleben muessen,
# ohne dass jemand daran denkt. Was hier steht, laeuft beim Start
# einmal der Reihe nach durch.


def _von_1_nach_2(daten):
    """geraet_kanal und geraet_kanaele kamen mit Fassung 2 dazu.

    Inhaltlich ist nichts umzuschreiben: die Vorgaben 0 und 1
    beschreiben genau, was vorher galt -- erster Kanal, mono. Der
    Schritt steht trotzdem hier, und zwar ausdruecklich. Ohne ihn
    bliebe die Kette bei 1 stehen, und eine Datei ohne Fassungsnummer
    wuerde als Fassung 1 zurueckgeschrieben, obwohl sie laengst den
    Inhalt von 3 hat. Ein leerer Schritt ist kein ueberfluessiger."""
    daten.setdefault("geraet_kanal", 0)
    daten.setdefault("geraet_kanaele", 1)
    return ""


def _von_2_nach_3(daten):
    """glossar_quittiert kam mit 0.2.11 dazu, ohne Fassungswechsel.

    Eine Datei aus 0.2.10 oder frueher hat den Schluessel nicht. Die
    leere Liste ist dabei die richtige Auskunft: es wurde noch nichts
    quittiert, also erscheint der Hinweis zu einer ungeprueften Sprache
    beim naechsten Einschalten einmal. Lieber einmal zu viel als ein
    Techniker, der nie erfaehrt, dass eine Sprache ungeprueft ist."""
    daten.setdefault("glossar_quittiert", [])
    return "glossar_quittiert ergaenzt"


# Von welcher Fassung nach der naechsten. Der Schluessel ist die
# Fassung, die IN DER DATEI steht.
UMZUEGE = {
    1: _von_1_nach_2,
    2: _von_2_nach_3,
}

# Geschrieben wird aus den Request-Threads des Servers, also aus mehreren
# gleichzeitig. Ohne Schloss koennten sich zwei Schreibvorgaenge
# ueberholen und die Datei mit dem aelteren Stand ueberschreiben.
_schloss = threading.Lock()


def jetzt():
    """Zeitstempel fuer die letzte Messung. Ortszeit, weil ihn ein Mensch
    liest und nicht ein Programm."""
    return time.strftime("%Y-%m-%d %H:%M:%S")


def vorgabe():
    """Was gilt, solange nichts eingestellt wurde: die Werte aus config.py.

    geraet=None heisst Vorgabegeraet des Systems, schwelle.wert=None
    heisst mitlaufende Schwelle statt festgenagelter.

    geraet_name steht neben der Nummer, weil die Nummer allein nicht
    traegt: Dienst und angemeldete Sitzung zaehlen verschieden. Ohne
    Sitzung zeigt ALSA einen anderen Satz Plugin-Eintraege, und der
    Dienst haelt das benutzte Mikrofon exklusiv offen, es fehlt einer
    zweiten Aufzaehlung deshalb ganz. Gemessen wurden 13 Geraete beim
    Dienst gegen 7 im Terminal, mit verschiedener Nummer 0 -- die
    Richtung steht nicht fest, nur dass die Nummern abweichen. Beim
    Umstecken eines USB-Mikrofons verschieben sie sich zusaetzlich."""
    return {
        "fassung": FASSUNG,
        "geraet": None,
        "geraet_name": "",
        "geraet_kanal": 0,
        "geraet_kanaele": 1,
        "quelle": config.AUSGANGSSPRACHE,
        "ziele": list(config.ZIELSPRACHEN),
        "wlan": {"ssid": "", "passwort": ""},
        "schwelle": {"wert": None, "gemessen": None},
        # Welche ungeprueften Sprachen der Techniker schon einmal
        # gelesen hat. Steht hier und nicht nur im Speicher, weil es
        # sonst nach jedem Neustart wieder im Briefkasten laege -- und
        # was zum dritten Mal kommt, wird ungelesen weggeklickt.
        "glossar_quittiert": [],
        # Fingerabdruck der zuletzt gelesenen Systemcheck-Befunde.
        # Aendert sich die Lage, aendert sich der Abdruck, und die
        # Nachricht kommt wieder.
        "systemcheck_quittiert": "",
        # Darf der gesprochene Satz ins Protokoll?
        #
        # Vorgabe AUS. Bis 0.2.13 stand bei jedem Abschnitt Predigttext
        # im Journal, dazu Zuschriften aus dem Saal und die
        # Personennamen aus dem Manuskript. Ueber Monate ergibt das eine
        # Sammlung, die niemand angelegt hat und niemand loescht.
        #
        # Hier und nicht in config.py: ein geaenderter Wert in einer
        # versionierten Datei laesst jedes Update abbrechen.
        "protokoll_mitschrift": False,
        # Das freiwillige Pult-Passwort, als Hash. Leer heisst: keines,
        # und das ist die Vorgabe -- das Pult bleibt offen wie bisher.
        #
        # Nur der Hash, nie das Passwort. Wer die Datei in die Hand
        # bekommt, hat damit noch keinen Zugang; und der Fehlerbericht,
        # der technische Angaben aus dieser Datei zieht, kann ihn
        # konstruktiv nicht ausplaudern.
        "pult_passwort": "",
    }


def kanalname(kanal, kanaele):
    """Wie ein Kanal am Pult heisst.

    Bei zwei Kanaelen L und R -- so steht es auf jedem Mischpult und auf
    jedem Kabel, und danach sucht der Techniker. Bei mehr als zweien
    gibt es keine eingebuergerten Buchstaben mehr, dann wird gezaehlt,
    und zwar ab 1: Kanal 0 steht auf keinem Geraet."""
    if kanaele <= 1:
        return "Mono"
    if kanaele == 2:
        return "L" if kanal == 0 else "R"
    return f"Kanal {kanal + 1}"


def _sprache_pruefen(wert, ersatz):
    return wert if isinstance(wert, str) and wert in config.SPRACHNAMEN \
        else ersatz


def _uebernehmen(roh, daten):
    """Traegt ein, was in der Datei brauchbar ist, und laesst den Rest auf
    der Vorgabe stehen.

    Feld fuer Feld statt dict.update: eine von Hand verpfuschte Zeile soll
    nur ihren eigenen Wert kosten, nicht die ganze Datei. Wer im Editor
    eine Sprache falsch schreibt, soll nicht sein WLAN verlieren."""
    fehlerhaft = []

    if isinstance(roh.get("geraet"), bool):
        # bool ist in Python ein int, waere hier aber Unsinn.
        fehlerhaft.append("geraet")
    elif isinstance(roh.get("geraet"), int):
        daten["geraet"] = roh["geraet"]
    elif roh.get("geraet") is not None:
        fehlerhaft.append("geraet")

    if "geraet_name" in roh:
        if isinstance(roh["geraet_name"], str):
            daten["geraet_name"] = roh["geraet_name"]
        else:
            fehlerhaft.append("geraet_name")

    # Beide Kanalfelder zusammen, weil sie dieselbe Pruefung brauchen:
    # eine Zahl, nicht negativ, kein bool. Ein unbrauchbarer Wert kostet
    # nur ihn selbst und faellt auf die Vorgabe zurueck -- also auf den
    # ersten Kanal, und damit auf das Verhalten vor Fassung 2.
    for feld, kleinst in (("geraet_kanal", 0), ("geraet_kanaele", 1)):
        if feld not in roh:
            continue
        wert = roh[feld]
        if isinstance(wert, int) and not isinstance(wert, bool) \
                and wert >= kleinst:
            daten[feld] = wert
        else:
            fehlerhaft.append(feld)

    # Ein Kanal, den das gespeicherte Geraet gar nicht hat, ist keine
    # Auswahl, sondern ein Tippfehler von Hand. Lieber der erste Kanal
    # als ein Griff ins Leere.
    if daten["geraet_kanal"] >= daten["geraet_kanaele"]:
        if "geraet_kanal" in roh and "geraet_kanal" not in fehlerhaft:
            fehlerhaft.append("geraet_kanal")
        daten["geraet_kanal"] = 0

    if "quelle" in roh:
        gueltig = _sprache_pruefen(roh["quelle"], None)
        if gueltig:
            daten["quelle"] = gueltig
        else:
            fehlerhaft.append("quelle")

    if "ziele" in roh:
        if isinstance(roh["ziele"], list):
            daten["ziele"] = [s for s in roh["ziele"]
                              if _sprache_pruefen(s, None)]
        else:
            fehlerhaft.append("ziele")

    # Welche ungeprueften Sprachen der Techniker schon gelesen hat.
    # Geprueft wird wie bei "ziele": nur bekannte Sprachcodes, alles
    # andere faellt still weg. Ein Tippfehler von Hand soll hoechstens
    # dazu fuehren, dass ein Hinweis noch einmal kommt.
    if isinstance(roh.get("systemcheck_quittiert"), str):
        daten["systemcheck_quittiert"] = roh["systemcheck_quittiert"]

    if isinstance(roh.get("protokoll_mitschrift"), bool):
        daten["protokoll_mitschrift"] = roh["protokoll_mitschrift"]
    elif roh.get("protokoll_mitschrift") is not None:
        fehlerhaft.append("protokoll_mitschrift")

    # Eine Zeichenkette oder gar nichts. Steht dort Unsinn, faellt sie
    # auf leer zurueck -- also auf ein offenes Pult. Andersherum waere
    # es schlimmer: ein unlesbarer Wert, der als "irgendein Passwort"
    # gilt, sperrt die Gemeinde aus ihrem eigenen Pult aus.
    if isinstance(roh.get("pult_passwort"), str):
        daten["pult_passwort"] = roh["pult_passwort"]
    elif roh.get("pult_passwort") is not None:
        fehlerhaft.append("pult_passwort")

    quittiert = roh.get("glossar_quittiert")
    if isinstance(quittiert, list):
        daten["glossar_quittiert"] = [s for s in quittiert
                                      if _sprache_pruefen(s, None)]
    elif quittiert is not None:
        fehlerhaft.append("glossar_quittiert")

    wlan = roh.get("wlan")
    if isinstance(wlan, dict):
        daten["wlan"] = {"ssid": str(wlan.get("ssid") or ""),
                         "passwort": str(wlan.get("passwort") or "")}
    elif wlan is not None:
        fehlerhaft.append("wlan")

    schwelle = roh.get("schwelle")
    if isinstance(schwelle, dict):
        wert = schwelle.get("wert")
        if isinstance(wert, (int, float)) and not isinstance(wert, bool):
            # Dieselben Grenzen wie am Pult. Ein von Hand eingetragener
            # Unsinnswert soll den Ton nicht dauerhaft abwuergen.
            daten["schwelle"] = {
                "wert": max(0.0005, min(0.5, float(wert))),
                "gemessen": schwelle.get("gemessen") or None}
        elif wert is not None:
            fehlerhaft.append("schwelle")
    elif schwelle is not None:
        fehlerhaft.append("schwelle")

    return fehlerhaft


def laden():
    """Liest zustand.json. Gibt (daten, herkunft) zurueck.

    Fehlt die Datei oder ist sie kaputt, kommen die Vorgaben aus config.py
    und der Grund steht in herkunft. Kein Abbruch: eine unlesbare
    Einstellungsdatei darf den Gottesdienst nicht verhindern."""
    daten = vorgabe()
    if not DATEI.exists():
        return daten, f"Vorgaben aus config.py ({DATEI.name} gibt es noch nicht)"

    try:
        roh = json.loads(DATEI.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"{DATEI.name} ist unlesbar ({str(e)[:90]}). Es gelten die "
              f"Vorgaben aus config.py. Die Datei bleibt unangetastet, bis "
              f"am Pult etwas geaendert wird.")
        return daten, f"Vorgaben aus config.py ({DATEI.name} unlesbar)"

    if not isinstance(roh, dict):
        print(f"{DATEI.name} enthaelt kein Objekt. Es gelten die Vorgaben "
              f"aus config.py.")
        return daten, f"Vorgaben aus config.py ({DATEI.name} unbrauchbar)"

    fehlerhaft = _uebernehmen(roh, daten)

    # Was diese Fassung nicht kennt, bleibt trotzdem stehen. Sonst
    # verliert ein Rueckfall auf die aeltere Fassung genau die
    # Einstellungen, die die neuere angelegt hat -- still, und erst im
    # Gottesdienst zu merken.
    for schluessel, wert in roh.items():
        if schluessel not in daten:
            daten[schluessel] = wert

    hinweis = _umziehen(roh, daten)

    if fehlerhaft:
        print(f"{DATEI.name}: unbrauchbare Eintraege "
              f"({', '.join(fehlerhaft)}), dafuer gilt config.py.")
        return daten, f"{DATEI.name}, teilweise (siehe oben)"
    if hinweis:
        return daten, f"{DATEI.name}, {hinweis}"
    return daten, DATEI.name


# Eine Datei aus einer neueren Fassung wird gelesen, aber nicht
# zurueckgeschrieben. Der Fall tritt nach einem misslungenen Update auf:
# die neue Fassung hat schon geschrieben, dann faellt der Rechner auf
# die alte zurueck. Wuerde die alte darueberschreiben, waeren die
# Einstellungen der neuen endgueltig weg.
NUR_LESEN = False
NUR_LESEN_GRUND = ""


def _umziehen(roh, daten):
    """Fuehrt die Umzugsschritte aus. Gibt einen Hinweis zurueck oder ''."""
    global NUR_LESEN, NUR_LESEN_GRUND
    NUR_LESEN = False
    NUR_LESEN_GRUND = ""

    war = roh.get("fassung")
    if not isinstance(war, int) or isinstance(war, bool):
        # Keine oder eine unbrauchbare Angabe: dann ist es eine Datei
        # aus der Zeit vor der Fassungsnummer. Die aelteste, die es
        # gibt, ist 1.
        war = 1

    if war > FASSUNG:
        NUR_LESEN = True
        NUR_LESEN_GRUND = (
            f"{DATEI.name} ist in Fassung {war} geschrieben, dieses "
            f"Programm kennt {FASSUNG}. Die Datei wird gelesen, aber "
            f"NICHT ueberschrieben -- sonst waeren die Einstellungen "
            f"der neueren Fassung weg. Wahrscheinlich ist ein Update "
            f"zurueckgefallen.")
        print(NUR_LESEN_GRUND)
        return f"Fassung {war}, nur gelesen"

    if war == FASSUNG:
        return ""

    # Vor dem ersten Schritt eine Sicherung. Sie enthaelt das
    # WLAN-Passwort, gehoert also niemandem ausser dem Dienstbenutzer
    # und nie ins Repo (.gitignore deckt zustand.json* ab).
    sicherung = DATEI.with_name(f"{DATEI.name}.vor-{war}")
    try:
        if not sicherung.exists():
            sicherung.write_text(DATEI.read_text(encoding="utf-8"),
                                 encoding="utf-8")
            os.chmod(sicherung, 0o600)
    except Exception as e:
        print(f"Sicherung {sicherung.name} misslang ({str(e)[:70]}). "
              f"Der Umzug laeuft trotzdem -- die Datei im Speicher ist "
              f"vollstaendig.")

    schritte = []
    stand = war
    while stand < FASSUNG:
        schritt = UMZUEGE.get(stand)
        if schritt is None:
            print(f"Kein Umzugsschritt von Fassung {stand} nach "
                  f"{stand + 1}. Es bleibt bei dem, was gelesen wurde.")
            break
        try:
            was = schritt(daten)
        except Exception as e:
            print(f"Umzug {stand} -> {stand + 1} misslang "
                  f"({str(e)[:70]}). Die Sicherung liegt als "
                  f"{sicherung.name} daneben.")
            break
        schritte.append(f"{stand}->{stand + 1}" + (f" ({was})" if was else ""))
        stand += 1

    daten["fassung"] = stand
    if schritte:
        print(f"{DATEI.name} umgezogen: {', '.join(schritte)}")
        print(f"  Vorher liegt als {sicherung.name} daneben.")
        return "umgezogen von Fassung %d" % war
    return ""


def speichern(daten):
    """Schreibt zustand.json. Gibt zurueck, ob es geklappt hat.

    Erst vollstaendig danebenschreiben, dann umbenennen: os.replace ist
    unteilbar, damit gibt es nie eine halb geschriebene Datei, auch wenn
    mitten im Schreiben der Strom ausfaellt. Die Rechte werden vor dem
    Umbenennen gesetzt, sonst laege das WLAN-Passwort einen Moment lang
    lesbar fuer alle da.

    Wirft nicht: aufgerufen wird das aus Request-Handlern, und eine
    volle Platte soll die Einstellung am Pult nicht mit einem Fehler
    quittieren, wenn sie im laufenden Betrieb doch greift."""
    if NUR_LESEN:
        # Nicht schreiben und auch nicht so tun, als waere geschrieben
        # worden: der Aufrufer soll es am Rueckgabewert merken.
        print(f"{DATEI.name} wird nicht ueberschrieben: {NUR_LESEN_GRUND}")
        return False
    daten["fassung"] = FASSUNG
    neben = DATEI.with_name(DATEI.name + ".neu")
    try:
        with _schloss:
            neben.write_text(
                json.dumps(daten, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8")
            os.chmod(neben, 0o600)
            os.replace(neben, DATEI)
        return True
    except Exception as e:
        print(f"{DATEI.name} liess sich nicht schreiben ({str(e)[:90]}). "
              f"Die Einstellung gilt fuer diesen Lauf, ueberlebt aber den "
              f"Neustart nicht.")
        try:
            neben.unlink(missing_ok=True)
        except Exception:
            pass
        return False


def kurzfassung(daten):
    """Eine Zeile fuer die Startausgabe des Servers."""
    if daten["geraet"] is None and not daten["geraet_name"]:
        geraet = "Vorgabegeraet"
    else:
        geraet = daten["geraet_name"] or f"Geraet {daten['geraet']}"
    if daten["geraet_kanaele"] > 1:
        geraet += f" ({kanalname(daten['geraet_kanal'], daten['geraet_kanaele'])})"
    schwelle = daten["schwelle"]["wert"]
    return (f"{geraet}, {daten['quelle']} -> "
            f"{', '.join(daten['ziele']) or 'nichts'}, "
            f"Schwelle {'mitlaufend' if schwelle is None else f'{schwelle:.4f}'}"
            f"{', WLAN gesetzt' if daten['wlan']['ssid'] else ''}")


if __name__ == "__main__":
    # Zum Nachsehen von Hand: python zustand.py
    d, woher = laden()
    print(f"Herkunft: {woher}")
    print(json.dumps(d, indent=2, ensure_ascii=False))
