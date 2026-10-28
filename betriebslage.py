# -*- coding: utf-8 -*-
"""Was der Rechner ueber Dienst, Updates und Wecker preisgibt (0.5.1).

Fuer die Einrichtung am Pult und den Systemcheck. Anlass: in Rostock
startete Devarenu nach dem Einschalten nicht, das Autoupdate hatte nie
geklappt, und an den Rechner kommt man nur ueber Fotos vom Helfer. Was
dort passiert, muss also im Pult stehen.

DREI REGELN

  * Nur lesen, nie sudo. Was ohne Wurzelrechte nicht lesbar ist, heisst
    "unbekannt" -- und wird nicht aus Indizien geraten.
  * Jede Abfrage mit kurzer Frist. Fehlt systemctl, journalctl oder eine
    Datei, entfaellt die Angabe still. Nichts hier darf den Server
    aufhalten; gerufen wird es erst, wenn jemand die Seite oeffnet.
  * Was aus Protokollen kommt, geht durch schwaerzen(): keine
    WLAN-Passwoerter, keine ntfy-Themen, keine Namen und Mailadressen.

WAS DER UPDATER FESTHAELT (Stand 0.5.0)

  Stick          update/stand.json, jede Lage mit Grund (stick_update.sh)
  Netz, gelungen update/stand-online.json (aktualisierung.sh)
  Netz, gescheitert  NIRGENDS lesbar. aktualisieren.sh bricht vor der
                 Uebergabe ab ("git fetch fehlgeschlagen", Signatur ...)
                 und schreibt nur auf die Standardausgabe.
  Knopf am Pult  update/online-lauf.json, mit Grund (wartungsfenster.sh)
  Fenster        das Protokoll unter /var/lib/devarenu/updates (root,
                 600) und dieselben letzten Zeilen im Journal von
                 devarenu-fenster.service. Lesbar ist das Journal nur
                 fuer die Gruppen adm, wheel oder systemd-journal.

Darum wird der Grund eines Fensterlaufs aus dem Journal gelesen, wenn
es geht, und sonst steht dort "unbekannt".
"""

import json
import os
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

BASIS = Path(__file__).resolve().parent
NAME = "devarenu"
FENSTER_UNIT = "devarenu-fenster.service"
FENSTER_TIMER = "devarenu-fenster.timer"
ABLAGE = Path(os.environ.get("DEVARENU_DATEN", "/var/lib/devarenu/updates"))
# Geschrieben von start.sh, eine Zeile je Doppelklick (B4).
STARTPROTOKOLL = "start-protokoll.txt"
WECKER_DATEI = Path("/sys/class/rtc/rtc0/wakealarm")
JOURNAL_ORTE = (Path("/var/log/journal"), Path("/run/log/journal"))
FRIST = 3.0
# Ab so vielen selbsttaetigen Neustarts ist es kein Ausrutscher mehr.
NEUSTARTS_BEFUND = 3

_FARBE = re.compile(r"\x1b\[[0-9;]*m")
_URL = re.compile(r"\bhttps?://\S+")
_MAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_HEIM = re.compile(r"/home/[^/\s]+")
_GEHEIMFELD = re.compile(
    r"(?i)\b(passw\w*|kennwort|psk|secret|token|thema|topic)(\s*[:=]\s*)\S+")
_FASSUNG = r"(\d+\.\d+\.\d+)"


def _lauf(befehl, zeit=FRIST):
    """stdout eines Befehls, oder None, wenn es ihn nicht gibt oder er
    nicht in der Frist fertig wird. Nie eine Ausnahme."""
    try:
        a = subprocess.run(befehl, capture_output=True, text=True,
                           timeout=zeit, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return a.stdout


# ------------------------------------------------------------ Schwaerzen

def _geheime_werte(basis):
    """Was in keiner Anzeige stehen darf, aus den Dateien dieses Rechners.

    Nur Werte mit mindestens vier Zeichen: kuerzere wuerden mitten in
    gewoehnlichen Woertern ersetzt."""
    werte = set()

    def sammeln(d, schluessel=""):
        if isinstance(d, dict):
            for k, v in d.items():
                sammeln(v, str(k).lower())
        elif isinstance(d, list):
            for v in d:
                sammeln(v, schluessel)
        elif isinstance(d, str) and re.search(
                r"pass|psk|kennwort|ntfy|thema|topic|ssid|profil|kontakt",
                schluessel):
            werte.add(d.strip())

    for name in ("zustand.json", "netz.json", "meldung.json"):
        try:
            sammeln(json.loads((basis / name).read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    # Das ntfy-Thema allein, ohne die Adresse davor.
    for w in list(werte):
        if w.startswith("http"):
            werte.add(w.rstrip("/").rsplit("/", 1)[-1])
    try:
        import config
        werte.add(str(config.BETREUER.get("name", "")).strip())
        werte.add(str(config.BETREUER.get("mail", "")).strip())
    except Exception:
        pass
    return sorted((w for w in werte if len(w) >= 4), key=len, reverse=True)


def schwaerzen(text, geheim=()):
    """Nimmt Geheimes und Persoenliches aus einer Protokollzeile.

    Bekannte Werte (Passwort, Thema, Name) zuerst und woertlich, danach
    die Muster: jede Adresse mit http, denn darin steckt das ntfy-Thema;
    Mailadressen; Heimatordner, deren Name oft ein Vorname ist."""
    text = _FARBE.sub("", str(text))
    for w in geheim:
        text = text.replace(w, "[…]")
    text = _URL.sub("[Adresse]", text)
    text = _MAIL.sub("[Mail]", text)
    text = _HEIM.sub("~", text)
    text = _GEHEIMFELD.sub(lambda m: m.group(1) + m.group(2) + "[…]", text)
    return text


# ----------------------------------------------------------------- Dienst

_FELDER = ("LoadState", "UnitFileState", "ActiveState", "SubState",
           "NRestarts", "MainPID", "ActiveEnterTimestamp")


def dienst(name=NAME):
    """Was systemd ueber den Dienst sagt, oder None ohne systemctl.

    Eine Abfrage statt drei: is-enabled, is-active und NRestarts kommen
    aus demselben "systemctl show". Das braucht keine Wurzelrechte."""
    befehl = ["systemctl", "show", name]
    for f in _FELDER:
        befehl += ["-p", f]
    aus = _lauf(befehl)
    if not aus:
        return None
    w = dict(z.split("=", 1) for z in aus.splitlines() if "=" in z)
    if "LoadState" not in w:
        return None
    try:
        neu = int(w.get("NRestarts", ""))
    except ValueError:
        neu = None
    try:
        pid = int(w.get("MainPID", "0") or 0)
    except ValueError:
        pid = 0
    return {"vorhanden": w.get("LoadState") == "loaded",
            "eingeschaltet": w.get("UnitFileState", ""),
            "aktiv": w.get("ActiveState", ""),
            "unter": w.get("SubState", ""),
            "neustarts": neu,
            "pid": pid,
            "seit": w.get("ActiveEnterTimestamp", "")}


def dienst_befehl(basis=BASIS, heim=None):
    """Der Befehl, der den Dienst einrichtet und einschaltet (0.5.2).

    Mit dem Ordner, in dem DIESES Devarenu liegt -- nicht mit einem
    festen ~/Devarenu: auf einem Rechner, auf dem es woanders liegt,
    waere der Befehl sonst falsch, und wer ihn abtippt, steht vor
    "Datei nicht gefunden". Liegt der Ordner unter dem Heimordner,
    mit ~ und damit kuerzer zum Abtippen; sonst der ganze Pfad.
    Leerzeichen und Sonderzeichen werden fuer die Shell geschuetzt."""
    import shlex
    pfad = Path(basis).resolve() / "dienst.sh"
    try:
        heim = Path(heim or Path.home()).resolve()
        rest = pfad.relative_to(heim)
    except (ValueError, RuntimeError, OSError):
        return f"bash {shlex.quote(str(pfad))}"
    return f"bash ~/{shlex.quote(str(rest))}"


def autostart_an(d):
    return bool(d) and d.get("eingeschaltet") in (
        "enabled", "enabled-runtime", "static", "alias")


def laufart(cgroup="/proc/self/cgroup"):
    """Laeuft DIESER Prozess als Dienst oder aus einer Sitzung?

    An der cgroup, nicht an der Umgebung: systemd legt jeden Dienst in
    seine eigene, und ein Server vom Schreibtischsymbol steckt in der
    der Anmeldung (user@1000.service/app.slice/...)."""
    try:
        text = Path(cgroup).read_text(encoding="utf-8")
    except OSError:
        return "unbekannt"
    return "dienst" if f"/{NAME}.service" in text else "sitzung"


def startprotokoll(basis=BASIS, anzahl=10, geheim=None):
    """Die letzten Zeilen, die start.sh geschrieben hat, juengste zuletzt."""
    try:
        zeilen = (basis / STARTPROTOKOLL).read_text(
            encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    geheim = _geheime_werte(basis) if geheim is None else geheim
    return [schwaerzen(z, geheim) for z in zeilen if z.strip()][-anzahl:]


# ------------------------------------------------------------- Journal

def journal_lesbar(orte=JOURNAL_ORTE, maschine=None):
    """Darf dieser Benutzer das SYSTEM-Journal lesen?

    Ohne die Gruppe adm, wheel oder systemd-journal sieht journalctl nur
    das eigene Benutzerjournal -- und meldet dann keine Fehler, sondern
    einfach nichts. Darum vorher fragen, statt aus Leere "nicht
    aufgewacht" zu schliessen. os.access beachtet die ACL, ueber die
    Ubuntu der Gruppe adm das Lesen erlaubt."""
    if maschine is None:
        try:
            maschine = Path("/etc/machine-id").read_text().strip()
        except OSError:
            return False
    for ort in orte:
        datei = Path(ort) / maschine / "system.journal"
        if datei.exists():
            return os.access(datei, os.R_OK)
    return False


def boots():
    """[(erster, letzter Eintrag)] als Unix-Sekunden, oder None."""
    aus = _lauf(["journalctl", "--list-boots", "-o", "json", "--no-pager"],
                zeit=5)
    try:
        liste = json.loads(aus or "")
        return [(b["first_entry"] / 1e6, b["last_entry"] / 1e6)
                for b in liste]
    except (ValueError, TypeError, KeyError):
        return None


def fenster_journal(beginn, ende):
    """Was devarenu-fenster.service in diesem Fenster geschrieben hat."""
    aus = _lauf(["journalctl", "-u", FENSTER_UNIT,
                 "--since", beginn.strftime("%Y-%m-%d %H:%M:%S"),
                 "--until", ende.strftime("%Y-%m-%d %H:%M:%S"),
                 "-o", "cat", "--no-pager", "-q"], zeit=5)
    if aus is None:
        return None
    return [_FARBE.sub("", z).rstrip() for z in aus.splitlines()]


# -------------------------------------------------------- Das Fenster

def letztes_fenster(e, jetzt):
    """(Beginn, Ende) des letzten Fensters, das schon begonnen hat."""
    import wartungsfenster as wf
    if not e.get("an"):
        return None
    ziel = wf._tag(e["wochentag"])
    for versatz in range(0, -8, -1):
        beginn, ende = wf._an_tag(jetzt, e, versatz)
        if beginn.weekday() == ziel and beginn <= jetzt:
            return beginn, ende
    return None


def auswerten(zeilen):
    """Liest aus den Zeilen eines Fensterlaufs, was geschah.

    Gesucht wird nach den Saetzen, die wartungsfenster.sh und
    aktualisieren.sh selbst schreiben -- nicht nach Vermutungen. Steht
    keiner davon da, bleibt es "unbekannt". Das Journal traegt vom
    Updateprotokoll nur die letzten zwanzig Zeilen; was davor stand,
    kann fehlen."""
    text = "\n".join(zeilen)
    lage = {"wlan": "unbekannt", "internet": "unbekannt", "ziel": "",
            "ergebnis": "unbekannt", "grund": ""}
    if re.search(r"(ist schon verbunden|\bverbunden)$", text, re.M) and \
            "liess sich nicht verbinden" not in text:
        lage["wlan"] = "ja"
    elif "liess sich nicht verbinden" in text:
        lage["wlan"] = "nein"

    if re.search(r"Tags von \S+ geholt|kein neueres Tag|Es gibt kein "
                 r"neueres Tag|das ist neuer|Signatur von v", text):
        lage["internet"] = "ja"
    elif "git fetch fehlgeschlagen" in text:
        lage["internet"] = "nein"

    m = (re.search(r"-> " + _FASSUNG + r", das ist neuer", text)
         or re.search(r"\bv" + _FASSUNG + r"\b", text)
         or re.search(_FASSUNG + r" -> " + _FASSUNG + r" in \d+s", text))
    if m:
        lage["ziel"] = m.group(m.lastindex)

    if "== Autoupdate" not in text:
        lage["ergebnis"] = "kein_versuch"
    if re.search(_FASSUNG + r" -> " + _FASSUNG + r" in \d+s", text):
        lage["ergebnis"] = "eingespielt"
    elif "kein neueres Tag" in text or "Es gibt kein neueres Tag" in text:
        lage["ergebnis"] = "nichts_zu_tun"
    elif "ist gescheitert" in text:
        lage["ergebnis"] = "gescheitert"
        # Der Grund VOLLSTAENDIG: jede Zeile, die das Skript selbst als
        # Fehler oder Warnung markiert hat, dazu die erklaerenden
        # Folgezeilen. Abgeschnitten wird hier nichts.
        grund, dabei = [], False
        for z in zeilen:
            s = z.strip()
            if re.match(r"^(FEHLT|!)\s", s):
                grund.append(re.sub(r"^(FEHLT|!)\s+", "", s))
                dabei = True
            elif (dabei and s and z[:1] == " "
                  and not re.match(r"^(ok|==)\s", s)):
                grund.append(s)
            else:
                dabei = False
        lage["grund"] = "\n".join(grund)
    return lage


def _zeitpunkt(text):
    m = re.search(r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)", text or "")
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def fenster(jetzt=None, ablage=ABLAGE, journal=None, geheim=()):
    """Das letzte Wartungsfenster: wach, versucht, Ergebnis, Grund.

    journal=None heisst: selbst nachsehen, ob es lesbar ist. Der
    Pruefstand gibt True oder False vor."""
    try:
        import wartungsfenster as wf
        e = wf.einstellung()
    except Exception:
        return None
    if not e.get("an"):
        return {"an": False}
    jetzt = jetzt or datetime.now()
    zeit = letztes_fenster(e, jetzt)
    aus = {"an": True, "tag": e["wochentag"], "von": e["von"],
           "bis": e["bis"], "autoupdate": bool(e.get("autoupdate")),
           "beginn": "", "wach": "unbekannt", "beleg": "",
           "versucht": "unbekannt", "ende_lauf": "",
           "journal": False, "wlan": "unbekannt", "internet": "unbekannt",
           "ziel": "", "ergebnis": "unbekannt", "grund": ""}
    if zeit is None:
        return aus
    beginn, ende = zeit
    aus["beginn"] = beginn.strftime("%Y-%m-%d %H:%M")
    kennung = beginn.strftime("%Y-%m-%dT%H:%M")
    if ende > jetzt:
        aus["laeuft"] = True

    # 1. Belege ohne Journal. Die Ablage ist 711: hineinsehen darf
    #    niemand, nach einem bekannten Namen fragen jeder.
    try:
        marke = Path(ablage) / f"autoupdate-{kennung}"
        if marke.exists():
            aus["versucht"] = "ja"
            aus["wach"], aus["beleg"] = "ja", "marke"
            log = Path(ablage) / f"autoupdate-{kennung}.log"
            if log.exists():
                aus["ende_lauf"] = datetime.fromtimestamp(
                    log.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        elif not e.get("autoupdate"):
            aus["versucht"] = "nein"
    except OSError:
        pass
    timer = _lauf(["systemctl", "show", FENSTER_TIMER,
                   "-p", "LastTriggerUSec"])
    t = _zeitpunkt(timer)
    if t and beginn <= t <= ende and aus["wach"] != "ja":
        aus["wach"], aus["beleg"] = "ja", "timer"

    # 2. Das Journal, wenn es lesbar ist.
    lesbar = journal_lesbar() if journal is None else journal
    aus["journal"] = bool(lesbar)
    if not lesbar:
        return aus
    liste = boots()
    if liste:
        b0, e0 = beginn.timestamp(), ende.timestamp()
        if any(erst <= e0 and letzt >= b0 for erst, letzt in liste):
            aus["wach"], aus["beleg"] = "ja", aus["beleg"] or "journal"
        elif (min(erst for erst, _ in liste) <= b0
              and aus["wach"] != "ja"):
            # Das Journal reicht weiter zurueck als das Fenster, und
            # kein Start faellt hinein: der Rechner war aus.
            aus["wach"], aus["beleg"] = "nein", "journal"
    zeilen = fenster_journal(beginn, ende + timedelta(minutes=15))
    if zeilen:
        lage = auswerten(zeilen)
        if lage["ergebnis"] != "kein_versuch":
            aus["versucht"] = "ja"
        elif aus["versucht"] == "unbekannt":
            aus["versucht"] = "nein"
        lage["grund"] = schwaerzen(lage["grund"], geheim)
        aus.update(lage)
        if aus["wach"] == "unbekannt":
            aus["wach"], aus["beleg"] = "ja", "journal"
    return aus


# ----------------------------------------------------------------- Wecker

def wecker(datei=WECKER_DATEI, jetzt=None):
    """Der gestellte Wecker der Hardware-Uhr und der geplante.

    /sys/class/rtc/rtc0/wakealarm ist fuer alle lesbar: Unix-Sekunden,
    leer, wenn keiner gestellt ist. Geplant ist, was wartungsfenster.py
    aus der Einstellung rechnet -- gestellt wird es nur als root."""
    jetzt = jetzt or datetime.now()
    aus = {"lesbar": False, "gestellt": "", "vorbei": False, "geplant": ""}
    try:
        roh = Path(datei).read_text(encoding="utf-8").strip()
        aus["lesbar"] = True
        if roh:
            t = datetime.fromtimestamp(int(roh))
            aus["gestellt"] = t.strftime("%Y-%m-%d %H:%M")
            aus["vorbei"] = t < jetzt
    except (OSError, ValueError):
        aus["lesbar"] = False
    try:
        import wartungsfenster as wf
        g = wf.wecker_zeit(jetzt)
        aus["geplant"] = g.strftime("%Y-%m-%d %H:%M") if g else ""
    except Exception:
        pass
    return aus


# ----------------------------------------------------------- Alles

# ------------------------------------------- Meldekanal und Wartungs-WLAN
# Beide sind Geheimnisse, und beide gehen NIE an den Browser (28.10.2026).
# Das Pult erfaehrt nur, ob etwas eingetragen ist.

def meldekanal(basis=BASIS):
    """{"gesetzt": bool}. Ob meldung.json einen brauchbaren Kanal hat --
    dieselbe Pruefung wie meldung.sh, ohne den Kanal herauszugeben."""
    try:
        d = json.loads((basis / "meldung.json").read_text(encoding="utf-8"))
        url = str(d.get("ntfy") or "").strip()
    except (OSError, ValueError, AttributeError):
        url = ""
    return {"gesetzt": url.startswith(("https://", "http://"))}


def wartungs_wlan(netz=None):
    """{"eingetragen": bool, "passwort": "gesetzt"|"nicht_gesetzt"|
    "unbekannt"}.

    Das Passwort selbst fragt hier niemand ab: nmcli bekommt weder -s
    noch ein psk-Feld, nur die Art der Absicherung. "wpa-psk" oder "sae"
    heisst, im Profil steht ein Passwort. Der Profilname bleibt auch
    draussen -- _geheime_werte zaehlt ihn zu dem, was in keine Anzeige
    gehoert."""
    import wartungsfenster
    profil = wartungsfenster.einstellung(netz)["profil"].strip()
    if not profil:
        return {"eingetragen": False, "passwort": "unbekannt"}
    nmcli = os.environ.get("DEVARENU_NMCLI", "nmcli")
    try:
        a = subprocess.run([nmcli, "-g", "802-11-wireless-security.key-mgmt",
                            "connection", "show", profil],
                           capture_output=True, text=True, timeout=FRIST,
                           stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError, ValueError):
        return {"eingetragen": True, "passwort": "unbekannt"}
    if a.returncode != 0:
        # Profil fehlt oder nmcli verweigert -- nichts raten.
        return {"eingetragen": True, "passwort": "unbekannt"}
    art = a.stdout.strip()
    if art in ("wpa-psk", "sae"):
        return {"eingetragen": True, "passwort": "gesetzt"}
    if art in ("", "none", "owe"):
        # Offenes WLAN (owe ist verschluesselt, aber ohne Passwort).
        return {"eingetragen": True, "passwort": "nicht_gesetzt"}
    return {"eingetragen": True, "passwort": "unbekannt"}


def lage(basis=BASIS):
    """Alles fuer die Einrichtung am Pult. Jeder Teil fuer sich: faellt
    einer aus, stehen die anderen trotzdem da."""
    geheim = _geheime_werte(basis)
    aus = {}
    for schluessel, holen in (
            ("dienst", dienst),
            ("laufart", laufart),
            ("startprotokoll", lambda: startprotokoll(basis, geheim=geheim)),
            ("fenster", lambda: fenster(geheim=geheim)),
            ("wecker", wecker),
            ("meldekanal", lambda: meldekanal(basis)),
            ("wartungs_wlan", wartungs_wlan)):
        try:
            aus[schluessel] = holen()
        except Exception as e:
            print(f"Betriebslage: {schluessel} -- {type(e).__name__}")
            aus[schluessel] = None
    # Der Befehl zum Einrichten gehoert zum Dienst und steht darum dort,
    # nicht als eigener Teil (0.5.2). Das Pult zeigt ihn, wenn der
    # Autostart aus ist oder der Dienst fehlt.
    if isinstance(aus.get("dienst"), dict):
        aus["dienst"]["befehl"] = dienst_befehl(basis)
    return aus
