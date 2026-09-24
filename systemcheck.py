#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ist dieser Rechner so eingestellt, dass er sonntags allein hochkommt?

Geprueft wird beim Start des Servers und in pruefen.sh -- dieselbe
Logik, an einer Stelle. Der Server AENDERT NICHTS. Er sieht nach und
legt Abweichungen als Nachricht ins Pult; geaendert wird von Hand oder
mit rechner_einrichten.sh.

Warum ueberhaupt: der Gemeinderechner steht ohne Tastatur und ohne
Bildschirm im Saal. Was ihn aufhaelt, faellt nicht auf -- es faellt
sonntags auf. Eine Bildschirmsperre, die nach zehn Minuten zuschnappt,
eine Abmeldung, die nachfragt, ein Netzschalter, der in den Standby
geht statt herunterzufahren: alles harmlos am Schreibtisch, alles ein
ausgefallener Gottesdienst im Saal.

Jeder Befund nennt in Klartext, was zu tun ist. Wer davorsteht, soll
nicht raten muessen, und wer es liest, hat meistens wenig Zeit.
"""

import os
import re
import subprocess
from pathlib import Path

import config

# Wie schwer ein Befund wiegt.
#   fehlt   der Betrieb ist gefaehrdet, das muss jemand anfassen
#   hinweis es laeuft, koennte aber besser stehen
FEHLT = "fehlt"
HINWEIS = "hinweis"


class Befund:
    """Ein einzelner Punkt. Kennung bleibt stabil, Text darf sich aendern."""

    def __init__(self, kennung, schwere, was, tun="", tun_en="", was_en=""):
        self.kennung = kennung
        self.schwere = schwere
        self.was = was
        self.was_en = was_en or was
        self.tun = tun
        self.tun_en = tun_en or tun

    def __repr__(self):
        return f"<{self.kennung} {self.schwere}>"


def _lauf(befehl, zeit=5):
    """Ruft etwas auf und gibt die Ausgabe zurueck, oder None."""
    try:
        a = subprocess.run(befehl, capture_output=True, text=True,
                           timeout=zeit)
        return a.stdout
    except Exception:
        return None


def _kconfig(datei, gruppen, schluessel):
    """Liest einen Plasma-Wert. gruppen ist eine Liste, auch bei einer.

    Verschachtelte Gruppen brauchen MEHRFACHES --group. powerdevilrc
    schreibt [AC][SuspendAndShutdown]; mit einem einzigen
    --group "AC][SuspendAndShutdown" kommt eine leere Antwort zurueck,
    und die saehe aus wie "nicht gesetzt". Geprueft:

        kreadconfig6 --file powerdevilrc --group AC \
            --group SuspendAndShutdown --key PowerButtonAction
        -> 8

    Der Umweg ueber das Programm ist der genauere: Plasma legt
    Einstellungen in mehreren Ebenen ab (/etc/xdg, ~/.config), und wer
    nur die Benutzerdatei liest, uebersieht eine Systemvorgabe."""
    if isinstance(gruppen, str):
        gruppen = [gruppen]
    befehl = ["kreadconfig6", "--file", datei]
    for g in gruppen:
        befehl += ["--group", g]
    befehl += ["--key", schluessel]
    aus = _lauf(befehl)
    if aus is not None:
        aus = aus.strip()
        return aus if aus else None

    # Kein kreadconfig6: dann von Hand, und zwar auf die verschachtelte
    # Schreibweise, wie sie in der Datei steht.
    pfad = Path.home() / ".config" / datei
    if not pfad.exists():
        return None
    kopf = "[" + "][".join(gruppen) + "]"
    in_gruppe = False
    for zeile in pfad.read_text(encoding="utf-8",
                                errors="replace").splitlines():
        zeile = zeile.strip()
        if zeile.startswith("["):
            in_gruppe = zeile == kopf
        elif in_gruppe and zeile.startswith(schluessel + "="):
            return zeile.split("=", 1)[1].strip() or None
    return None


def _dienst_an(name):
    """(laeuft, eingeschaltet) -- beides, weil beides schiefgehen kann."""
    aktiv = (_lauf(["systemctl", "is-active", name]) or "").strip()
    an = (_lauf(["systemctl", "is-enabled", name]) or "").strip()
    return aktiv == "active", an in ("enabled", "enabled-runtime", "static")


# ------------------------------------------------------ Die Pruefungen

def _autologin(befunde):
    """Meldet sich der Rechner nach dem Einschalten von selbst an?

    Ohne das steht er am Anmeldebildschirm, und ohne angemeldete
    Sitzung gibt es keinen PulseAudio-Server -- also keinen Ton. Genau
    daran hing der Rollout monatelang."""
    gefunden = {}
    for ordner in (Path("/etc/plasmalogin.conf.d"),
                   Path("/etc/sddm.conf.d")):
        if not ordner.is_dir():
            continue
        for datei in sorted(ordner.glob("*.conf")):
            try:
                inhalt = datei.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            gruppe = ""
            for zeile in inhalt.splitlines():
                zeile = zeile.strip()
                if zeile.startswith("["):
                    gruppe = zeile.strip("[]").lower()
                elif "=" in zeile and gruppe == "autologin":
                    k, v = zeile.split("=", 1)
                    gefunden[k.strip().lower()] = v.strip()
    if not gefunden.get("user"):
        befunde.append(Befund(
            "autologin", FEHLT,
            "Der Rechner meldet sich nach dem Einschalten nicht von "
            "selbst an. Ohne angemeldete Sitzung gibt es keinen Ton.",
            "bash rechner_einrichten.sh",
            was_en="The computer does not log in automatically after "
                   "power-on. Without a session there is no sound.",
            tun_en="bash rechner_einrichten.sh"))
        return
    sitzung = (gefunden.get("session") or "").lower()
    if sitzung and "wayland" in sitzung:
        befunde.append(Befund(
            "autologin_wayland", HINWEIS,
            f"Die automatische Anmeldung waehlt {gefunden['session']}. "
            f"Geprueft ist X11 (plasmax11); unter Wayland ist der "
            f"Tonweg nicht gemessen.",
            "In /etc/plasmalogin.conf.d/ Session=plasmax11 setzen.",
            was_en=f"Autologin uses {gefunden['session']}. Only X11 "
                   f"(plasmax11) has been tested.",
            tun_en="Set Session=plasmax11 in /etc/plasmalogin.conf.d/."))


def _energie(befunde):
    """Standby, Netzschalter, Bildschirm, Sperre."""
    # Netzschalter. 8 = Herunterfahren, 0 = nichts tun; belegt durch
    # Abgleich mit der Energieverwaltung von Plasma.
    # 8 = Herunterfahren, 0 = nichts tun. Belegt durch Abgleich mit der
    # Energieverwaltung von Plasma: dort steht bei Wert 8
    # "Herunterfahren".
    schalter = _kconfig("powerdevilrc", ["AC", "SuspendAndShutdown"],
                        "PowerButtonAction")
    if schalter not in (None, "", "8"):
        befunde.append(Befund(
            "netzschalter", HINWEIS,
            f"Der Netzschalter tut nicht 'Herunterfahren' (Wert "
            f"{schalter}). Wer den Rechner damit ausschaltet, legt ihn "
            f"vielleicht nur schlafen.",
            "bash rechner_einrichten.sh",
            was_en=f"The power button is not set to shut down (value "
                   f"{schalter}).",
            tun_en="bash rechner_einrichten.sh"))

    standby = _kconfig("powerdevilrc", ["AC", "SuspendAndShutdown"],
                       "AutoSuspendAction")
    if standby not in (None, "", "0"):
        befunde.append(Befund(
            "standby", FEHLT,
            f"Der Rechner geht von selbst in den Standby (Wert "
            f"{standby}). Mitten im Gottesdienst ist dann Schluss.",
            "bash rechner_einrichten.sh",
            was_en=f"The computer suspends on its own (value {standby}).",
            tun_en="bash rechner_einrichten.sh"))

    aus = _kconfig("powerdevilrc", ["AC", "Display"],
                   "TurnOffDisplayWhenIdle")
    if aus is not None and aus.lower() == "true":
        befunde.append(Befund(
            "bildschirm", HINWEIS,
            "Der Bildschirm schaltet sich ab. Am Pult ist das laestig, "
            "gefaehrlich ist es nicht.",
            "bash rechner_einrichten.sh",
            was_en="The screen turns itself off.",
            tun_en="bash rechner_einrichten.sh"))

    sperre = _kconfig("kscreenlockerrc", "Daemon", "Autolock")
    if sperre is not None and sperre.lower() != "false":
        befunde.append(Befund(
            "sperre", FEHLT,
            "Die Bildschirmsperre ist an. Wer sonntags davorsteht, "
            "braucht dann ein Passwort -- und kennt es meistens nicht.",
            "bash rechner_einrichten.sh",
            was_en="The screen lock is enabled. Whoever stands in front "
                   "of it on Sunday needs a password.",
            tun_en="bash rechner_einrichten.sh"))


def _sitzung(befunde):
    """Leere Sitzung beim Anmelden, keine Rueckfrage beim Abmelden."""
    modus = _kconfig("ksmserverrc", "General", "loginMode")
    if modus is not None and modus != "emptySession":
        befunde.append(Befund(
            "sitzung", HINWEIS,
            f"Beim Anmelden wird die letzte Sitzung wiederhergestellt "
            f"({modus}). Dann gehen alte Fenster wieder auf, und "
            f"irgendwann steht ein Dutzend davon uebereinander.",
            "bash rechner_einrichten.sh",
            was_en=f"The previous session is restored on login ({modus}).",
            tun_en="bash rechner_einrichten.sh"))
    frage = _kconfig("ksmserverrc", "General", "confirmLogout")
    if frage is not None and frage.lower() != "false":
        befunde.append(Befund(
            "abmeldefrage", HINWEIS,
            "Beim Abmelden und Herunterfahren kommt eine Rueckfrage. "
            "Am Netzschalter wartet sie auf eine Antwort, die niemand "
            "gibt.",
            "bash rechner_einrichten.sh",
            was_en="Logout and shutdown ask for confirmation.",
            tun_en="bash rechner_einrichten.sh"))


def _dienste(befunde, netz):
    """Laufen und starten die Dienste, auf die es ankommt?"""
    for name, warum, warum_en in (
            ("devarenu", "Ohne ihn gibt es keine Uebersetzung.",
             "Without it there is no translation."),
            ("ollama", "Ohne ihn scheitert jede Uebersetzung.",
             "Without it every translation fails.")):
        laeuft, an = _dienst_an(name)
        if not an:
            befunde.append(Befund(
                f"dienst_{name}", FEHLT,
                f"Der Dienst {name} startet nicht von selbst. {warum}",
                f"sudo systemctl enable --now {name}",
                was_en=f"Service {name} does not start automatically. "
                       f"{warum_en}",
                tun_en=f"sudo systemctl enable --now {name}"))
        elif not laeuft:
            befunde.append(Befund(
                f"dienst_{name}_tot", FEHLT,
                f"Der Dienst {name} ist eingeschaltet, laeuft aber "
                f"nicht. {warum}",
                f"systemctl status {name}",
                was_en=f"Service {name} is enabled but not running.",
                tun_en=f"systemctl status {name}"))

    if netz["router"]:
        laeuft, an = _dienst_an("dnsmasq")
        if not (laeuft and an):
            befunde.append(Befund(
                "dienst_dnsmasq", FEHLT,
                "dnsmasq laeuft nicht oder startet nicht von selbst. "
                "Dann bekommt kein Handy im Saal eine Adresse.",
                "sudo systemctl enable --now dnsmasq",
                was_en="dnsmasq is not running or not enabled. No phone "
                       "in the hall gets an address.",
                tun_en="sudo systemctl enable --now dnsmasq"))


def _netzumbau(befunde, netz):
    """Greift die eigene Konfiguration, steht der Start-Zusatz, ist die
    Weiterleitung aus?"""
    if not netz["router"]:
        return
    import netzzustand
    if not netzzustand.DNSMASQ_KONF.exists():
        befunde.append(Befund(
            "dnsmasq_konf", FEHLT,
            f"netz.json sagt Router, aber {netzzustand.DNSMASQ_KONF} "
            f"fehlt. Der Umbau ist halb.",
            "sudo bash netz_einrichten.sh",
            was_en="netz.json says router, but the dnsmasq configuration "
                   "is missing.",
            tun_en="sudo bash netz_einrichten.sh"))
    zusatz = Path("/etc/systemd/system/dnsmasq.service.d/devarenu.conf")
    if not zusatz.exists():
        befunde.append(Befund(
            "dnsmasq_zusatz", FEHLT,
            "Der systemd-Zusatz fuer dnsmasq fehlt. Ohne ihn liest "
            "dnsmasq unsere Konfiguration gar nicht -- unter Arch sind "
            "die conf-dir-Zeilen ab Werk auskommentiert.",
            "sudo bash netz_einrichten.sh",
            was_en="The systemd drop-in for dnsmasq is missing. Without "
                   "it dnsmasq never reads our configuration.",
            tun_en="sudo bash netz_einrichten.sh"))
    else:
        text = zusatz.read_text(encoding="utf-8", errors="replace")
        if "--conf-file" not in text:
            befunde.append(Befund(
                "dnsmasq_conffile", FEHLT,
                "Der systemd-Zusatz nennt kein --conf-file. dnsmasq "
                "liest dann /etc/dnsmasq.conf und findet uns nie.",
                "sudo bash netz_einrichten.sh",
                was_en="The drop-in has no --conf-file.",
                tun_en="sudo bash netz_einrichten.sh"))
        if re.search(r"^\s*After\s*=.*network-online", text, re.M):
            befunde.append(Befund(
                "dnsmasq_zyklus", HINWEIS,
                "Der systemd-Zusatz ordnet dnsmasq nach "
                "network-online.target. Der Unit des Pakets sagt "
                "Before= -- das ist ein Ordnungszyklus, den systemd "
                "willkuerlich aufloest.",
                "sudo bash netz_einrichten.sh",
                was_en="The drop-in orders dnsmasq after "
                       "network-online.target, which conflicts with the "
                       "packaged unit and creates an ordering cycle.",
                tun_en="sudo bash netz_einrichten.sh"))

    try:
        weiter = Path("/proc/sys/net/ipv4/ip_forward").read_text().strip()
    except OSError:
        weiter = "0"
    if weiter != "0":
        befunde.append(Befund(
            "ip_forward", FEHLT,
            "Die Weiterleitung ist an. Der Saal haette damit einen Weg "
            "ins Gemeindenetz -- und den soll er nicht haben.",
            "sudo sysctl -w net.ipv4.ip_forward=0",
            was_en="IP forwarding is on. The hall would have a route "
                   "into the church network.",
            tun_en="sudo sysctl -w net.ipv4.ip_forward=0"))

    # Firewall: haengt die Freigabe an der richtigen Karte?
    karte = netz.get("schnittstelle") or ""
    aus = _lauf(["ufw", "status"])
    if aus is None:
        aus = _lauf(["sudo", "-n", "ufw", "status"]) or ""
    if "Status: active" in aus and karte:
        if f"on {karte}" not in aus:
            befunde.append(Befund(
                "firewall_karte", FEHLT,
                f"ufw ist an, aber keine Regel haengt an {karte}. Die "
                f"Handys im Saal kommen dann nicht durch -- vom Rechner "
                f"selbst faellt das nie auf.",
                "sudo bash firewall.sh --schnittstelle " + karte,
                was_en=f"ufw is active but no rule is bound to {karte}. "
                       f"Phones in the hall cannot get through.",
                tun_en="sudo bash firewall.sh --schnittstelle " + karte))


def _wlan(befunde):
    """Haengt der Rechner dauerhaft in einem WLAN?

    Im BETRIEB hat der Gemeinderechner kein Netz nach draussen, und
    nichts in Devarenu setzt eines voraus. Fuer die WARTUNG schaltet
    jemand vor Ort einen Handy-Hotspot ein; dann geht RustDesk, und
    Updates lassen sich abkuerzen.

    Also kein Fehler, sondern eine Lagemeldung: der Wartungszugang ist
    gerade offen. Wer das nach der Wartung liest, weiss, dass der
    Hotspot noch laeuft."""
    aus = _lauf(["nmcli", "-t", "-f", "TYPE,STATE,CONNECTION", "device"])
    if not aus:
        return
    for zeile in aus.split("\n"):
        teile = zeile.split(":")
        if len(teile) >= 3 and teile[0] == "wifi" and teile[1] == "connected":
            befunde.append(Befund(
                "wlan_verbunden", HINWEIS,
                f"Wartungszugang aktiv: der Rechner haengt im WLAN "
                f"({teile[2]}). Im Gottesdienst braucht er das nicht. "
                f"Nach der Wartung trennen.",
                "nmcli con down \"" + teile[2] + "\"",
                was_en=f"Maintenance access is on: connected to wifi "
                       f"({teile[2]}). Not needed during a service.",
                tun_en="nmcli con down \"" + teile[2] + "\""))
            return


def ollama_ablage():
    """Wo Ollama seine Modelle wirklich hinlegt. None, wenn unauffindbar.

    Eine EINZIGE Stelle, weil drei Programme dieselbe Antwort brauchen:
    vorrat_bauen.sh, wiederherstellen.sh und der Systemcheck. Zwei
    Ermittlungen, die auseinanderlaufen, sind schlimmer als eine, die
    manchmal nichts findet.

    Geraten wird nicht, und das ist keine Vorsicht ohne Anlass: auf
    einem der Entwicklungsrechner zeigt OLLAMA_MODELS auf ein eigenes
    Laufwerk, weit ausserhalb jeder ueblichen Liste. Auf dem
    Gemeinderechner liegt es unter /usr/share/ollama (Installierskript
    von ollama.com), das Arch-Paket nimmt /var/lib/ollama. Drei
    Rechner, drei Orte. Deshalb zuerst fragen, dann suchen."""
    import os
    # 1. Was in dieser Umgebung gesetzt ist.
    ort = os.environ.get("OLLAMA_MODELS", "").strip()
    if ort and Path(ort, "blobs").is_dir():
        return Path(ort)

    # 2. Was der DIENST mitbekommt. systemctl show loest Zusaetze mit
    #    auf, systemctl cat zeigt nur die Dateien.
    aus = _lauf(["systemctl", "show", "ollama", "-p", "Environment"]) or ""
    m = re.search(r"OLLAMA_MODELS=(\S+)", aus)
    if m and Path(m.group(1), "blobs").is_dir():
        return Path(m.group(1))

    # 3. Erst zuletzt die ueblichen Orte.
    for k in ("/usr/share/ollama/.ollama/models",
              "/var/lib/ollama/.ollama/models",
              str(Path.home() / ".ollama" / "models"),
              "/usr/local/share/ollama/.ollama/models"):
        if Path(k, "blobs").is_dir():
            return Path(k)
    return None


def _ollama_gpu(befunde):
    """Rechnet das Sprachmodell auf der Grafikkarte oder auf der CPU?

    Auf der CPU laeuft es -- nur eben zu langsam fuer den Livebetrieb.
    Und es faellt nicht auf: es gibt keine Fehlermeldung, die
    Uebersetzung kommt bloss zu spaet. Unter Arch ist das der
    Normalfall nach einer Installation ohne ollama-cuda, denn das Paket
    'ollama' haengt nur an libgcc, libstdc++ und glibc."""
    aus = _lauf(["ollama", "ps"], zeit=10)
    if not aus:
        return
    zeilen = [z for z in aus.strip().split("\n") if z.strip()]
    if len(zeilen) < 2:
        # Kein Modell geladen. Ollama laedt erst bei der ersten
        # Anfrage; das ist kein Befund, sondern der Normalzustand
        # zwischen den Gottesdiensten.
        return
    # NICHT nach Leerzeichen trennen: die Spalte SIZE enthaelt selbst
    # eines ("8.1 GB"), und dann zeigt der Feldindex auf etwas anderes.
    # "ollama ps" richtet die Spalten aus, also wird nach der
    # Zeichenposition der Ueberschrift gelesen -- und der Wert selbst
    # per Muster geholt, weil bei geteilter Last "48%/52% CPU/GPU"
    # dasteht.
    if "PROCESSOR" not in zeilen[0]:
        return
    von = zeilen[0].index("PROCESSOR")
    danach = [zeilen[0].index(x) for x in ("CONTEXT", "UNTIL")
              if x in zeilen[0] and zeilen[0].index(x) > von]
    bis = min(danach) if danach else len(zeilen[0]) + 40
    for zeile in zeilen[1:]:
        wo = zeile[von:bis].strip().lower()
        if not wo:
            continue
        if "gpu" not in wo:
            befunde.append(Befund(
                "ollama_cpu", FEHLT,
                f"Das Sprachmodell rechnet auf der CPU ({wo.strip()}), "
                f"nicht auf der Grafikkarte. Es laeuft -- nur zu "
                f"langsam fuer den Livebetrieb, und zwar ohne jede "
                f"Fehlermeldung.",
                "Unter Arch fehlt dann das passende Paket: "
                "sudo pacman -S ollama-cuda   (NVIDIA)  bzw. "
                "ollama-rocm (AMD), danach: sudo systemctl restart ollama",
                was_en=f"The language model runs on the CPU ({wo.strip()}), "
                       f"not on the graphics card. Too slow for live use.",
                tun_en="On Arch install ollama-cuda (NVIDIA) or "
                       "ollama-rocm (AMD), then restart ollama."))
            return


def _vorrat(befunde):
    """Liegt der Reparaturvorrat da, und passt er zu dieser Fassung?"""
    import json
    ziel = Path("/opt/devarenu-vorrat")
    datei = ziel / "vorrat.json"
    if not datei.exists():
        befunde.append(Befund(
            "vorrat", HINWEIS,
            "Es gibt keinen Reparaturvorrat. Geht vor Ort etwas kaputt, "
            "laesst es sich ohne Netz nicht wiederherstellen.",
            "sudo bash vorrat_bauen.sh   (braucht eine Leitung)",
            was_en="There is no repair stock. Nothing can be restored "
                   "on site without a connection.",
            tun_en="sudo bash vorrat_bauen.sh   (needs a connection)"))
        return
    try:
        d = json.loads(datei.read_text(encoding="utf-8"))
    except Exception:
        return
    if d.get("fassung") and d["fassung"] != config.VERSION:
        befunde.append(Befund(
            "vorrat_alt", HINWEIS,
            f"Der Vorrat gehoert zu Fassung {d['fassung']}, hier laeuft "
            f"{config.VERSION}. Stimmen und Modell passen trotzdem; bei "
            f"den Paketen kann requirements.txt sich geaendert haben.",
            "Beim naechsten Besuch mit Netz:  sudo bash vorrat_bauen.sh",
            was_en=f"The stock belongs to version {d['fassung']}, this "
                   f"is {config.VERSION}.",
            tun_en="Next visit with a connection: sudo bash vorrat_bauen.sh"))


def _units_veraltet(befunde):
    """Stimmen die installierten Units noch mit den Vorlagen ueberein?

    Der Haken: KEIN Update schreibt sie neu. stick_update.sh und
    aktualisieren.sh fassen sie nicht an, und einrichten.sh auch nicht
    -- geschrieben werden sie allein von dienst.sh, und das laeuft nur
    bei der Ersteinrichtung.

    Eine Aenderung an einer Vorlage erreicht den Rechner also nie von
    selbst. Sie liegt im Ordner und wirkt nicht, und niemand sieht es.
    Deshalb wird hier verglichen."""
    ordner = Path(config.BASIS)
    paare = [
        ("devarenu-stick@.service", "devarenu-stick@.service.vorlage"),
        ("devarenu-update.service", "devarenu-update.service.vorlage"),
        ("devarenu.service", "devarenu.service.vorlage"),
    ]
    veraltet = []
    for unit, vorlage in paare:
        ziel = Path("/etc/systemd/system") / unit
        quelle = ordner / vorlage
        if not ziel.exists() or not quelle.exists():
            continue
        # Verglichen werden die ExecStart-Zeilen, nicht die ganze
        # Datei: dienst.sh setzt Platzhalter ein, ein wortwoertlicher
        # Vergleich schluege deshalb immer fehl.
        def befehle(text):
            return [z.split("=", 1)[1].strip()
                    for z in text.splitlines()
                    if z.strip().startswith(("ExecStart=", "ExecStartPre="))
                    and "=" in z]
        soll = befehle(quelle.read_text(encoding="utf-8", errors="replace"))
        ist = befehle(ziel.read_text(encoding="utf-8", errors="replace"))
        # Die Platzhalter aus der Vorgabe wegdenken.
        soll = [x.replace("@ORDNER@", str(ordner)) for x in soll]
        if soll and ist and soll != ist:
            veraltet.append(unit)
    if veraltet:
        befunde.append(Befund(
            "units_veraltet", HINWEIS,
            "Diese Dienste laufen mit einer aelteren Fassung ihrer "
            "Vorlage: " + ", ".join(veraltet) + ". Kein Update schreibt "
            "sie neu -- das tut nur dienst.sh.",
            "sudo bash dienst.sh",
            was_en="These services still run an older version of their "
                   "template: " + ", ".join(veraltet) + ". No update "
                   "rewrites them.",
            tun_en="sudo bash dienst.sh"))


def _stick(befunde):
    """Ist das Update per Stick scharf?"""
    laeuft, an = _dienst_an("devarenu-update.timer")
    if not an:
        befunde.append(Befund(
            "stick_timer", HINWEIS,
            "Der Timer fuer das Update per Stick ist aus. Ein "
            "eingesteckter Stick wird dann nicht bemerkt.",
            "sudo systemctl enable --now devarenu-update.timer",
            was_en="The timer for USB stick updates is off.",
            tun_en="sudo systemctl enable --now devarenu-update.timer"))


def _ordner(befunde):
    """Weicht eine versionierte Datei ab? Dann bricht das naechste
    Update ab -- und zwar bevor es etwas tut."""
    aus = _lauf(["git", "-C", str(config.BASIS), "status", "--porcelain",
                 "--untracked-files=no"])
    if not aus:
        return
    # Nicht aus.strip(): das frisst das fuehrende Leerzeichen der
    # ersten Zeile, und aus " M .gitignore" wird dann "gitignore".
    dateien = [z[3:] for z in aus.split("\n") if len(z) > 3]
    if dateien:
        befunde.append(Befund(
            "ordner_schmutzig", FEHLT,
            "Versionierte Dateien weichen ab: " + ", ".join(dateien[:6])
            + ("" if len(dateien) <= 6 else f" (und {len(dateien)-6} weitere)")
            + ". Jedes Update bricht daran ab.",
            "git diff ansehen, dann: git checkout -- <datei>",
            was_en="Tracked files differ: " + ", ".join(dateien[:6])
                   + ". Every update will refuse to run.",
            tun_en="Inspect with git diff, then: git checkout -- <file>"))


def pruefen():
    """Alle Befunde, schwerste zuerst. Leere Liste heisst: alles gut."""
    import netzzustand
    netz = netzzustand.laden()[0]
    befunde = []
    _ordner(befunde)
    _dienste(befunde, netz)
    _netzumbau(befunde, netz)
    _autologin(befunde)
    _energie(befunde)
    _sitzung(befunde)
    _wlan(befunde)
    _ollama_gpu(befunde)
    _vorrat(befunde)
    _units_veraltet(befunde)
    _stick(befunde)
    befunde.sort(key=lambda b: 0 if b.schwere == FEHLT else 1)
    return befunde


def kennung(befunde):
    """Ein kurzer Fingerabdruck der Befundmenge.

    Damit merkt das Pult, ob sich etwas GEAENDERT hat: eine quittierte
    Nachricht bleibt quittiert, solange dieselben Punkte offen sind,
    und kommt wieder, sobald einer dazukommt oder wegfaellt."""
    import hashlib
    roh = "|".join(sorted(b.kennung for b in befunde))
    return hashlib.sha256(roh.encode("utf-8")).hexdigest()[:16]
