#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ob dieser Rechner der Router fuer das Saalnetz ist -- und welcher er ist.

WARUM NICHT IN config.py
------------------------
Bis 0.2.11 schrieb netz_einrichten.sh "NETZ_ROUTER = True" in config.py.
Damit galt der Ordner als veraendert, und jedes Update brach ab:
stick_update.sh und aktualisieren.sh weigern sich, ueber lokale
Aenderungen hinwegzuschreiben. Genau daran stand der Gemeinderechner
fest. Kein Skript schreibt mehr in eine versionierte Datei.

WARUM NICHT IN zustand.json
---------------------------
Das ist die Bedienoberflaeche der Gemeinde: Sprachwahl, Tonquelle,
WLAN-Zugangsdaten. Sie gehoert dem Benutzer, unter dem der Dienst
laeuft. netz_einrichten.sh laeuft als Wurzel; schriebe es dort hinein,
gehoerte die Datei danach der Wurzel, und der Dienst koennte seine
eigenen Einstellungen nicht mehr speichern. Zwei Zustaendigkeiten,
zwei Dateien.

WAS DIE PLATTE SAGT, GILT
-------------------------
netz.json kann fehlen -- nach einem frischen Klon, nach einem Update von
0.2.11, oder weil jemand sie geloescht hat. Dann wird am System
nachgesehen: liegt unsere dnsmasq-Konfiguration da, gibt es das
NM-Profil? Ist der Umbau danach eindeutig aktiv, wird netz.json
angelegt. So uebernimmt 0.2.12 einen Rechner, der schon umgebaut ist,
ohne dass jemand etwas von Hand eintraegt.

Die Datei ist nicht versioniert (.gitignore). Sie beschreibt diesen
einen Rechner, nicht das Projekt.
"""

import json
import os
from pathlib import Path

import config

DATEI = config.BASIS / "netz.json"

# Woran der Umbau am System zu erkennen ist. Beide Spuren legt
# netz_einrichten.sh an; eine davon genuegt nicht, denn eine
# vergessene Datei ohne Profil waere kein laufender Umbau.
DNSMASQ_KONF = Path("/etc/devarenu/dnsmasq.conf")
DNSMASQ_KONF_ALT = Path("/etc/dnsmasq.d/devarenu.conf")   # bis 0.2.11
NM_PROFIL = "devarenu-lan"


def vorgabe():
    """Was gilt, solange nichts eingerichtet wurde."""
    return {
        "router": False,
        "adresse": "",
        "maske": 0,
        "schnittstelle": "",
        # Auf welchen Rechnern netz_einrichten.sh scharf laufen darf.
        # LEER HEISST NIRGENDWO, und das ist Absicht: dasselbe
        # Verzeichnis liegt auch auf dem Arbeitsrechner, auf dem
        # Devarenu entsteht.
        "rechner": [],
        "eingerichtet_am": "",
    }


def _system_spuren():
    """(konfiguration_da, profil_da) -- was am System zu sehen ist."""
    konf = DNSMASQ_KONF.exists() or DNSMASQ_KONF_ALT.exists()
    profil = False
    try:
        import subprocess
        a = subprocess.run(["nmcli", "-t", "-f", "NAME", "con", "show"],
                           capture_output=True, text=True, timeout=5)
        profil = NM_PROFIL in a.stdout.split("\n")
    except Exception:
        # Kein NetworkManager, kein nmcli, keine Rechte: dann bleibt es
        # bei der Datei. Eine fehlende Auskunft ist kein Nein.
        profil = False
    return konf, profil


def _aus_system_lesen():
    """Liest Adresse und Schnittstelle aus der erzeugten Konfiguration."""
    daten = vorgabe()
    quelle = DNSMASQ_KONF if DNSMASQ_KONF.exists() else DNSMASQ_KONF_ALT
    try:
        text = quelle.read_text(encoding="utf-8")
    except Exception:
        return daten
    for zeile in text.splitlines():
        zeile = zeile.strip()
        if zeile.startswith("interface="):
            daten["schnittstelle"] = zeile.split("=", 1)[1].strip()
        elif zeile.startswith("dhcp-option=6,"):
            daten["adresse"] = zeile.split(",", 1)[1].strip()
        elif zeile.startswith("host-record=") or zeile.startswith("address=/"):
            # Rueckfall: die Adresse steht auch hinter jedem Pruefnamen.
            if not daten["adresse"]:
                daten["adresse"] = zeile.rsplit("/", 1)[-1].rsplit(",", 1)[-1]
    daten["router"] = True
    daten["maske"] = getattr(config, "NETZ_MASKE", 24)
    return daten


def laden():
    """(daten, herkunft). Faellt auf die Vorgabe zurueck, nie auf einen Fehler."""
    daten = vorgabe()
    if DATEI.exists():
        try:
            roh = json.loads(DATEI.read_text(encoding="utf-8"))
            if isinstance(roh, dict):
                _uebernehmen(roh, daten)
                return daten, DATEI.name
        except Exception as e:
            print(f"{DATEI.name} ist unlesbar ({str(e)[:80]}). Es wird am "
                  f"System nachgesehen.")

    konf, profil = _system_spuren()
    if konf and profil:
        daten = _aus_system_lesen()
        return daten, "am System erkannt"
    if konf or profil:
        # Nur eine Spur: das ist ein halber Umbau, und darueber muss
        # jemand Bescheid wissen. Nicht stillschweigend als "Router"
        # gelten lassen -- der Saal bekaeme dann Port 80 ohne DHCP.
        return daten, ("halber Umbau: "
                       + ("dnsmasq-Konfiguration ohne NM-Profil" if konf
                          else "NM-Profil ohne dnsmasq-Konfiguration"))
    return daten, "kein Umbau"


def _uebernehmen(roh, daten):
    """Feld fuer Feld, wie in zustand.py: ein verpfuschter Wert kostet
    nur sich selbst."""
    if isinstance(roh.get("router"), bool):
        daten["router"] = roh["router"]
    for feld in ("adresse", "schnittstelle", "eingerichtet_am"):
        if isinstance(roh.get(feld), str):
            daten[feld] = roh[feld]
    if isinstance(roh.get("maske"), int) and not isinstance(roh.get("maske"), bool):
        daten["maske"] = roh["maske"]
    if isinstance(roh.get("rechner"), list):
        daten["rechner"] = [str(x) for x in roh["rechner"] if str(x).strip()]


def speichern(daten):
    """Schreibt netz.json. Nur netz_einrichten.sh tut das."""
    DATEI.write_text(json.dumps(daten, ensure_ascii=False, indent=2) + "\n",
                     encoding="utf-8")
    # Lesbar fuer den Dienst, auch wenn die Wurzel sie angelegt hat.
    try:
        os.chmod(DATEI, 0o644)
    except OSError:
        pass


def uebernehmen_falls_noetig():
    """Legt netz.json an, wenn der Umbau laeuft, die Datei aber fehlt.

    Der Fall nach dem Update von 0.2.11: der Rechner ist umgebaut, der
    Zustand stand bisher in config.py, und die wird beim Update
    zurueckgesetzt. Ohne das hier stuende der Saal nach dem Update ohne
    Port 80 und ohne Pruefadressen da -- also mit lauter Handys, die
    "kein Internet" melden."""
    if DATEI.exists():
        return None
    daten, herkunft = laden()
    if not daten["router"]:
        return None
    try:
        speichern(daten)
    except OSError as e:
        print(f"netz.json liess sich nicht anlegen ({str(e)[:70]}).")
        print("  Der Umbau ist am System erkannt und gilt fuer diesen Lauf.")
        return herkunft
    print(f"netz.json angelegt ({herkunft}): Router auf "
          f"{daten['adresse'] or '?'}, Schnittstelle "
          f"{daten['schnittstelle'] or '?'}")
    return herkunft


def ist_router():
    """Kurzform. Liest jedes Mal neu -- die Datei aendert sich selten,
    und ein zwischengespeichertes Ja waere nach --zuruecknehmen falsch."""
    return laden()[0]["router"]
