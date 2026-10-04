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
import shutil
import subprocess
from pathlib import Path

import config

# Wie schwer ein Befund wiegt.
#   fehlt   der Betrieb ist gefaehrdet, das muss jemand anfassen
#   hinweis es laeuft, koennte aber besser stehen
FEHLT = "fehlt"
HINWEIS = "hinweis"


# Welche Befunde NUR die Technik angehen.
#
# Am Pult sitzt sonntags jemand, der den Ton fahren soll. Was dort
# steht, muss heute zu tun sein oder den Betrieb aufhalten. Alles
# andere -- ein Reparaturvorrat, der zu einer aelteren Fassung
# gehoert, eine Unit-Vorlage, die sich geaendert hat, ein offener
# Wartungszugang -- ist richtig und wichtig, aber nicht fuer diese
# Person und nicht in dieser Stunde. Es stand trotzdem da, jede
# Woche, und nach der dritten Woche liest man die Liste gar nicht
# mehr. Dann geht die eine Zeile unter, auf die es ankommt.
#
# Seit 0.3.3 also getrennt: hier die Wartung, der Rest bleibt am
# Pult. pruefen.sh zeigt weiterhin ALLES -- wer es aufruft, ist die
# Technik.
#
# Was hier NICHT hineingehoert: alles, was den Ton, das Saalnetz oder
# die Uebersetzung betrifft, und alles der Stufe FEHLT, das sich
# heute beheben laesst.
WARTUNG = {
    "wlan_verbunden",       # Wartungszugang offen
    "vorrat", "vorrat_alt", # Reparaturvorrat
    "sitzung", "sitzung_abweichend", "sitzung_anders_gewollt",
    "units_veraltet",
    "protokoll_mitschrift", # gehoert der Fehlersuche, nicht dem Sonntag
    "abmeldefrage", "netzschalter", "sperre", "standby", "bildschirm",
    "ordner_schmutzig",
    "wecker_fehlt", "fenster_timer", "fenster_profil",
    "onlineupdate_timer", "onlineupdate_abgebrochen",
    "testmodus", "testmodus_marke",
    "stick_timer",          # das Update per Stick, nicht der Sonntag
}


class Befund:
    """Ein einzelner Punkt. Kennung bleibt stabil, Text darf sich aendern."""

    def __init__(self, kennung, schwere, was, tun="", tun_en="", was_en=""):
        self.kennung = kennung
        self.schwere = schwere
        # Wartung heisst: nicht ans Pult, nur in die Einrichtung und
        # in pruefen.sh. Am Befund selbst, damit die Zuordnung an
        # einer Stelle steht und nicht in jeder Anzeige neu.
        self.wartung = kennung in WARTUNG
        self.was = was
        self.was_en = was_en or was
        self.tun = tun
        self.tun_en = tun_en or tun

    def __repr__(self):
        return f"<{self.kennung} {self.schwere}>"


def _lauf(befehl, zeit=5):
    """Ruft etwas auf und gibt die Ausgabe zurueck, oder None.

    MIT EINEM $HOME, auch wenn der Aufrufer keines hat. Ein root-Dienst
    bringt keines mit, und kreadconfig6 loest "$HOME/.config" dann zu
    "//.config" auf. Es beschwert sich darueber -- und zwar auf dem
    TERMINAL, nicht auf stderr, also hilft capture_output nicht:

        Configuration file "//.config/kreadconfig6rc" not writable.
        Please contact your system administrator

    Aufgefallen beim Bau des Einspielweg-Pruefstands, der den
    Gesundheitscheck absichtlich ohne HOME laufen laesst. Im Feld
    trifft es das Autoupdate im Fenster, das donnerstags als root
    laeuft -- jede Woche zwei Zeilen im Journal, die nichts sagen.

    Behoben wird die URSACHE und nicht das Symptom: wo kein HOME
    steht, wird das aus der Benutzerdatenbank eingesetzt. Dazu stdin
    auf /dev/null -- ein Programm, das im Dienst nach etwas fragt,
    wartet sonst bis zum Zeitablauf."""
    umgebung = dict(os.environ)
    if not umgebung.get("HOME"):
        try:
            umgebung["HOME"] = str(Path.home())
        except Exception:
            umgebung["HOME"] = "/root"
    try:
        a = subprocess.run(befehl, capture_output=True, text=True,
                           timeout=zeit, env=umgebung,
                           stdin=subprocess.DEVNULL)
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

def laufende_sitzung():
    """Welcher Sitzungstyp laeuft gerade: "x11", "wayland" oder "".

    Aus loginctl und nicht aus XDG_SESSION_TYPE: der Dienst laeuft als
    System-Unit und erbt die Umgebung der grafischen Sitzung nicht.
    Gefragt wird nach der aktiven Sitzung der Klasse "user" -- daneben
    steht immer noch eine "manager"-Sitzung ohne Typ."""
    zeilen = _lauf(["loginctl", "list-sessions", "--no-legend"]) or ""
    for zeile in zeilen.splitlines():
        teile = zeile.split()
        if not teile:
            continue
        angaben = _lauf(["loginctl", "show-session", teile[0],
                         "-p", "Type", "-p", "Class", "-p", "Active"]) or ""
        werte = dict(z.split("=", 1) for z in angaben.splitlines()
                     if "=" in z)
        if werte.get("Class") != "user":
            continue
        typ = (werte.get("Type") or "").lower()
        if typ in ("x11", "wayland"):
            # Eine aktive Sitzung schlaegt eine inaktive; gibt es nur
            # eine inaktive, ist sie immer noch die Auskunft.
            if werte.get("Active") == "yes":
                return typ
            _merke = typ
    return locals().get("_merke", "")


def sitzungsdatei(name):
    """Der Pfad zur Sitzung <name>, oder "" wenn es sie nicht gibt.

    Session=plasmax11 ist keine Zusage, sondern ein Wunsch: der
    Anmeldemanager sucht plasmax11.desktop, und findet er sie nicht,
    nimmt er wortlos die einzige, die da ist. Auf einem Arch ohne
    plasma-x11-session ist das Wayland -- die Einstellung steht
    richtig da und bewirkt nichts."""
    for ordner in ("/usr/share/xsessions", "/usr/local/share/xsessions",
                   "/usr/share/wayland-sessions",
                   "/usr/local/share/wayland-sessions"):
        p = Path(ordner) / f"{name}.desktop"
        if p.is_file():
            return str(p)
    return ""


ANMELDE_ORDNER = ("/etc/plasmalogin.conf.d", "/etc/sddm.conf.d")


def _sitzung_gewuenscht():
    """Welche Sitzung netz.json fuer diesen Rechner vorsieht.

    Eigene Funktion und mit try: auf einem Rechner mit aelterem
    netzzustand.py gibt es das Feld nicht, und daran soll der
    Systemcheck nicht scheitern."""
    try:
        import netzzustand
        return netzzustand.laden()[0].get("sitzung",
                                          netzzustand.SITZUNG_VORGABE)
    except Exception:
        return ""


def sitzungsart(name):
    """Ist das eine X11- oder eine Wayland-Sitzung? "" heisst unbekannt.

    Am Namen ist es nicht zu erkennen: plasmax11 ist X11, plasma ist
    Wayland, und beide sagen es nicht. Entschieden wird am Ordner, in
    dem die .desktop-Datei liegt -- genau so entscheidet es der
    Anmeldemanager auch.

    Gibt es die Datei nicht, bleibt der Name als schwacher Hinweis.
    Nur wenn auch der nichts hergibt, wird "" zurueckgegeben: eine
    Vermutung ist keine Auskunft."""
    if not name:
        return ""
    pfad = sitzungsdatei(name)
    if pfad:
        return "wayland" if "wayland-sessions" in pfad else "x11"
    return "x11" if "x11" in name else ""


def _autologin(befunde, ordner_liste=ANMELDE_ORDNER):
    """Meldet sich der Rechner nach dem Einschalten von selbst an?

    Ohne das steht er am Anmeldebildschirm, und ohne angemeldete
    Sitzung gibt es keinen PulseAudio-Server -- also keinen Ton. Genau
    daran hing der Rollout monatelang.

    ordner_liste ist nur fuer den Pruefstand da: die Faelle, um die es
    geht, lassen sich auf einem laufenden Rechner nicht herstellen."""
    gefunden = {}
    for ordner in (Path(o) for o in ordner_liste):
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
    gewollt = sitzungsart(sitzung)
    laeuft = laufende_sitzung()

    # Zwei verschiedene Auskuenfte: was EINGESTELLT ist, und was
    # LAEUFT. Bis 0.3.1 wurde nur die erste gelesen, und gemeldet
    # wurde, solange nicht "wayland" im Namen stand. Auf dem
    # Gemeinderechner stand plasmax11 -- und es lief Wayland, weil es
    # eine Sitzung dieses Namens dort gar nicht gibt.
    #
    # Am Namen ist es ohnehin nicht abzulesen: plasmax11 ist X11,
    # plasma ist Wayland, und keiner der beiden sagt es. Entschieden
    # wird am Ordner, in dem die .desktop-Datei liegt -- genau so
    # entscheidet es der Anmeldemanager auch.
    #
    # SEIT 0.3.2 IST WAYLAND DER NORMALFALL, seit 0.3.6 steht die
    # Wahl je Rechner in netz.json. Der Tonweg ist unter Wayland
    # gemessen; x11 ist die Ausnahme fuer Rechner, auf denen die
    # Fernwartung den Bildschirm braucht.
    #
    # Gemeldet wird, wenn Eingestelltes und Laufendes
    # auseinandergehen -- nicht, weil das schlimm waere, sondern weil
    # dann niemand weiss, was nach dem naechsten Neustart gilt. Und
    # wenn beides zwar zusammenpasst, aber nicht zu dem, was in
    # netz.json steht: dann hat jemand die Anmeldung von Hand
    # geaendert, oder netz.json ist neu und rechner_einrichten.sh
    # lief seither nicht.
    gewuenscht = _sitzung_gewuenscht()
    if gewuenscht and laeuft and gewuenscht != laeuft \
            and gewollt == laeuft:
        befunde.append(Befund(
            "sitzung_anders_gewollt", HINWEIS,
            f"In netz.json steht {gewuenscht}, es laeuft aber "
            f"{laeuft} -- und die Anmeldung ist auch auf {laeuft} "
            f"eingestellt. Entweder wurde sie von Hand geaendert, "
            f"oder netz.json ist neu und die Einrichtung lief "
            f"seither nicht.",
            "sudo bash rechner_einrichten.sh  -- danach neu starten. "
            "Umgestellt wird nur VOR ORT.",
            was_en=f"netz.json says {gewuenscht}, but {laeuft} is "
                   f"running and configured.",
            tun_en="sudo bash rechner_einrichten.sh, then reboot. "
                   "Only do this on site."))

    if gewollt and laeuft and gewollt != laeuft:
        fehlt_datei = not sitzungsdatei(sitzung)
        grund = (f" Eine Sitzung {gefunden['session']} gibt es auf "
                 "diesem Rechner naemlich nicht -- der Anmeldemanager "
                 "nimmt dann die, die er hat." if fehlt_datei else "")
        befunde.append(Befund(
            "sitzung_abweichend", HINWEIS,
            f"Eingestellt ist {gefunden['session']} ({gewollt}), es "
            f"laeuft aber {laeuft}: die Einstellung hat nicht "
            f"gegriffen.{grund} Devarenu laeuft unter beidem -- aber "
            f"solange beides auseinandergeht, weiss niemand, was nach "
            f"dem naechsten Neustart gilt.",
            "ls /usr/share/wayland-sessions /usr/share/xsessions  -- "
            "und in /etc/plasmalogin.conf.d/ eine Sitzung eintragen, "
            "die es dort wirklich gibt.",
            was_en=f"Configured is {gefunden['session']} ({gewollt}), "
                   f"but {laeuft} is running: the setting did not take "
                   f"effect.",
            tun_en="List the available sessions and configure one that "
                   "exists."))


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


# Wo die Handarbeit von 0.2.11 ihre Spuren hinterlassen hat. Alle drei
# raeumt netz_einrichten.sh weg; hier werden sie nur benannt.
DNSMASQ_HAUPT = Path("/etc/dnsmasq.conf")
DNSMASQ_ZUSATZ = Path("/etc/systemd/system/dnsmasq.service.d/devarenu.conf")
CONF_DIR_ZEILE = re.compile(
    r"^\s*conf-dir=/etc/dnsmasq\.d/?,\*\.conf\s*$", re.M)


def _netz_alt(befunde, netz):
    """Laeuft das Netz noch nach dem Aufbau von 0.2.11?

    Bis 0.2.11 lag die Konfiguration in /etc/dnsmasq.d/, die conf-dir-Zeile
    wurde von Hand an /etc/dnsmasq.conf gehaengt und der systemd-Zusatz
    von Hand geschrieben. Das laeuft -- es ist nur nicht mehr der Aufbau,
    den netz_einrichten.sh herstellt.

    Ohne diese Pruefung meldete der Systemcheck dafuer drei FEHLT-Befunde,
    allen voran "Der Umbau ist halb". Das ist ein roter Alarm fuer einen
    Rechner, an dem nichts fehlt, und er landet am Pult vor jemandem, der
    ihn nicht einordnen kann. Ein Ehrenamtlicher, der sonntags einen
    roten Punkt sieht, ruft an -- zu Recht, und umsonst.

    Rueckgabe: True, wenn die alte Lage erkannt wurde. Der Aufrufer
    ueberspringt dann die Befunde, die nur daher ruehren.
    """
    import netzzustand
    if not netz["router"]:
        return False
    # Die alte Lage ist: alte Datei da, neue nicht. Sind BEIDE da, ist
    # etwas halb umgezogen -- das soll sehr wohl auffallen.
    if not netzzustand.DNSMASQ_KONF_ALT.exists():
        return False
    if netzzustand.DNSMASQ_KONF.exists():
        return False

    # Die beiden anderen Spuren einzeln benennen. Wer vor Ort steht,
    # soll wissen, was ihn erwartet, statt es zu suchen.
    spuren = [str(netzzustand.DNSMASQ_KONF_ALT)]
    try:
        if CONF_DIR_ZEILE.search(
                DNSMASQ_HAUPT.read_text(encoding="utf-8", errors="replace")):
            spuren.append("die von Hand angehaengte conf-dir-Zeile in "
                          "/etc/dnsmasq.conf")
    except OSError:
        pass
    if DNSMASQ_ZUSATZ.exists():
        try:
            text = DNSMASQ_ZUSATZ.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        if re.search(r"^\s*After\s*=.*network-online", text, re.M):
            spuren.append("der von Hand angelegte systemd-Zusatz mit "
                          "Ordnungszyklus")
        else:
            spuren.append("der von Hand angelegte systemd-Zusatz")

    befunde.append(Befund(
        "netz_alt", HINWEIS,
        "Das Netz laeuft noch nach dem Aufbau von 0.2.11. Es funktioniert; "
        "nichts ist kaputt. Beim naechsten Wartungsbesuch neu einrichten. "
        "Betroffen: " + ", ".join(spuren) + ".",
        "Beim naechsten Besuch:  sudo bash netz_einrichten.sh",
        was_en="The network still uses the 0.2.11 layout. It works, "
               "nothing is broken. Set it up again at the next "
               "maintenance visit. Affected: " + ", ".join(spuren) + ".",
        tun_en="At the next visit:  sudo bash netz_einrichten.sh"))
    return True


def _netzumbau(befunde, netz, alt=False):
    """Greift die eigene Konfiguration, steht der Start-Zusatz, ist die
    Weiterleitung aus?

    alt=True: die Lage von 0.2.11 wurde erkannt und ist bereits gemeldet.
    Dann bleiben die drei Befunde weg, die nur besagen, dass der neue
    Aufbau noch nicht da ist -- das weiss der Leser schon. Weiterleitung
    und Firewall werden trotzdem geprueft: die gehen den alten Aufbau
    genauso an."""
    if not netz["router"]:
        return
    import netzzustand
    if not alt and not netzzustand.DNSMASQ_KONF.exists():
        befunde.append(Befund(
            "dnsmasq_konf", FEHLT,
            f"netz.json sagt Router, aber {netzzustand.DNSMASQ_KONF} "
            f"fehlt. Der Umbau ist halb.",
            "sudo bash netz_einrichten.sh",
            was_en="netz.json says router, but the dnsmasq configuration "
                   "is missing.",
            tun_en="sudo bash netz_einrichten.sh"))
    zusatz = DNSMASQ_ZUSATZ
    if alt:
        # Der Zusatz gehoert hier zur alten Lage und ist dort schon
        # benannt. Ein zweites Mal daraufhinzuweisen macht die Liste am
        # Pult laenger, nicht klarer.
        pass
    elif not zusatz.exists():
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


def _fensterlage():
    """(Einstellung, ob gerade Fenster ist). Faellt auf "aus" zurueck.

    Eigene Funktion, weil zwei Pruefungen sie brauchen und keine von
    beiden daran scheitern soll, dass es das Modul nicht gibt -- etwa
    auf einem Rechner, der noch eine aeltere Fassung hat."""
    try:
        import wartungsfenster
        e = wartungsfenster.einstellung()
        return e, wartungsfenster.im_fenster(e=e)
    except Exception:
        return {}, False


def _wartungsfenster(befunde):
    """Ist das Fenster brauchbar eingestellt -- und kann es wecken?

    Gemeldet wird nur, wenn jemand das Fenster eingeschaltet hat. Auf
    allen anderen Rechnern gibt es hier nichts zu sagen."""
    fenster, _ = _fensterlage()
    if not fenster.get("an"):
        return

    if not shutil.which("rtcwake"):
        befunde.append(Befund(
            "wecker_fehlt", FEHLT,
            "Das Wartungsfenster ist an, aber rtcwake fehlt. Der "
            "Rechner faehrt am Fensterende herunter und wacht nicht "
            "wieder auf -- danach kommt niemand mehr aus der Ferne "
            "heran.",
            "sudo pacman -S util-linux",
            was_en="The maintenance window is on, but rtcwake is "
                   "missing: the computer will shut down and never "
                   "wake up again.",
            tun_en="Install util-linux (it provides rtcwake)."))

    _, an = _dienst_an("devarenu-fenster.timer")
    if not an:
        befunde.append(Befund(
            "fenster_timer", FEHLT,
            "Das Wartungsfenster ist eingestellt, aber sein Timer ist "
            "aus. Es geht damit nie auf.",
            "sudo systemctl enable --now devarenu-fenster.timer",
            was_en="The maintenance window is configured but its "
                   "timer is off, so it never opens.",
            tun_en="sudo systemctl enable --now devarenu-fenster.timer"))

    # Gibt es das Profil ueberhaupt? Ein Tippfehler im Namen faellt
    # sonst erst an dem Donnerstag auf, an dem niemand hereinkommt.
    profile = _lauf(["nmcli", "-t", "-f", "NAME", "connection", "show"])
    if profile is not None and fenster["profil"] not in profile.split("\n"):
        befunde.append(Befund(
            "fenster_profil", FEHLT,
            f"Das Wartungsfenster soll \"{fenster['profil']}\" "
            f"verbinden, aber ein Profil dieses Namens gibt es nicht.",
            "nmcli connection show  -- und den Namen danach in "
            "netz.json richtigstellen",
            was_en=f"The maintenance window wants to connect "
                   f"\"{fenster['profil']}\", but no such profile exists.",
            tun_en="nmcli connection show, then fix the name in netz.json."))


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
    fenster, im_fenster = _fensterlage()
    for zeile in aus.split("\n"):
        teile = zeile.split(":")
        if len(teile) >= 3 and teile[0] == "wifi" and teile[1] == "connected":
            # Im Fenster ist das WLAN kein Befund, sondern der Plan.
            # Sonst stuende an jedem Donnerstagabend eine Warnung da,
            # die niemanden etwas angeht -- und eine Warnung, die
            # regelmaessig zu Unrecht kommt, liest bald niemand mehr.
            if im_fenster and teile[2] == fenster.get("profil"):
                return
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


def _protokoll(befunde):
    """Steht die Mitschrift im Protokoll?

    Ein Schalter fuer die Fehlersuche, der vergessen wird, sammelt ueber
    Monate Predigtinhalte im Journal. Solange er an ist, steht es am
    Pult -- nicht als Fehler, aber sichtbar."""
    try:
        import zustand as zustandsdatei
        an = bool(zustandsdatei.laden()[0].get("protokoll_mitschrift"))
    except Exception:
        return
    if not an:
        return
    befunde.append(Befund(
        "protokoll_mitschrift", HINWEIS,
        "Die Mitschrift steht im Protokoll. Der gesprochene Satz landet "
        "damit bei jedem Abschnitt im Journal -- ueber Wochen ergibt "
        "das eine Sammlung von Predigtinhalten, die niemand angelegt "
        "hat.",
        "Am Pult unter Einrichtung wieder ausschalten.",
        was_en="Transcripts are being written to the log. The spoken "
               "sentence ends up in the journal for every segment.",
        tun_en="Switch it off again under Setup on the control desk."))


def _testmodus(befunde):
    """Laeuft dieser Rechner im Testmodus?

    Dann ist die Uebersetzung unbrauchbar, und das gehoert gesagt --
    nicht als Fehler (auf der Testmaschine ist es gewollt), aber
    deutlich. Die eigentliche Sperre steckt in testmodus.py: ohne
    NVIDIA-Karte greift er, mit einer nicht.

    Und der Gegenfall gehoert auch gesagt: liegt die Marke auf einem
    Rechner MIT Karte, ist sie dort versehentlich hingekommen -- ueber
    eine Sicherung, einen kopierten Ordner, einen Stick aus einem
    Testverzeichnis. Dann tut sie nichts, aber sie hat dort nichts zu
    suchen."""
    try:
        import testmodus
        an, grund = testmodus.lage()
    except Exception:
        return
    if an:
        befunde.append(Befund(
            "testmodus", HINWEIS,
            "Dieser Rechner laeuft im TESTMODUS: Whisper rechnet als "
            f"\"{testmodus.MODELL}\" auf der CPU. Die Uebersetzung ist "
            "damit unbrauchbar -- geprueft wird der Weg, nicht das "
            "Ergebnis. Auf einem Gemeinderechner darf das nie stehen.",
            "Ausschalten:  python testmodus.py --aus",
            was_en="This computer runs in TEST MODE: Whisper uses a tiny "
                   "model on the CPU, so translations are unusable.",
            tun_en="Switch it off:  python testmodus.py --aus"))
        return
    if testmodus.MARKE.exists():
        befunde.append(Befund(
            "testmodus_marke", HINWEIS,
            "Die Datei TESTMODUS liegt im Projektordner. Sie greift hier "
            "nicht -- dieser Rechner hat eine Grafikkarte --, aber sie ist "
            "versehentlich hergekommen: ueber eine Sicherung, einen "
            "kopierten Ordner oder einen Stick aus einem Testverzeichnis.",
            "Wegnehmen:  python testmodus.py --aus",
            was_en="A TESTMODUS marker file is present. It has no effect "
                   "here, but it does not belong on this computer.",
            tun_en="Remove it:  python testmodus.py --aus"))


def _onlineupdate(befunde):
    """Der Weg hinter dem Knopf "Jetzt aus dem Netz".

    Zwei Dinge koennen schieflaufen, und beide sind von aussen nicht
    zu sehen: der Timer, der die Marke abholt, laeuft nicht -- dann ist
    der Knopf ein Knopf ohne Wirkung. Oder ein Lauf steht noch auf
    "laeuft", obwohl ihn niemand beendet hat; das heisst in der Regel,
    dass der Strom weg war."""
    import json
    from pathlib import Path as P
    # Nur auf einem Rechner, der ueberhaupt als Dienst laeuft.
    if not P("/etc/systemd/system/devarenu.service").exists():
        return
    _, an = _dienst_an("devarenu-onlineupdate.timer")
    if not an:
        befunde.append(Befund(
            "onlineupdate_timer", HINWEIS,
            "Der Timer fuer den Knopf \"Jetzt aus dem Netz aktualisieren\" "
            "laeuft nicht. Der Knopf am Pult legt dann eine Marke an, die "
            "niemand abholt -- es sieht aus, als waere nichts passiert.",
            "sudo systemctl enable --now devarenu-onlineupdate.timer",
            was_en="The timer behind the control desk's \"update from the "
                   "network\" button is not running, so nothing picks the "
                   "request up.",
            tun_en="sudo systemctl enable --now devarenu-onlineupdate.timer"))
    try:
        d = json.loads((Path(__file__).resolve().parent / "update"
                        / "online-lauf.json").read_text(encoding="utf-8"))
    except Exception:
        return
    if d.get("lage") == "abgebrochen":
        befunde.append(Befund(
            "onlineupdate_abgebrochen", HINWEIS,
            "Ein Update ueber das Netz wurde angefangen und nie beendet. "
            "Vermutlich war der Strom weg. Welche Fassung jetzt laeuft, "
            "sagt pruefen.sh -- zurueckgerollt hat sich der Updater "
            "selbst, falls er bis dahin kam.",
            "bash pruefen.sh   (danach den Knopf noch einmal druecken)",
            was_en="A network update was started and never finished, most "
                   "likely a power cut.",
            tun_en="bash pruefen.sh, then press the button again"))


def _mp3(befunde):
    """Kann dieser Rechner die Predigt als MP3 schreiben?

    Gefragt wird VORHER, nicht am Sonntag. ffmpeg ist eine feste
    Abhaengigkeit, aber MP3 schreibt es nur mit libmp3lame, und das
    ist eine Uebersetzungsoption. Fehlt sie und fehlt auch lame, laeuft
    die Aufnahme als WAV weiter -- sie faellt nicht aus, sie wird nur
    rund fuenfmal so gross. Das gehoert gesagt, bevor jemand sich
    ueber eine 700-MB-Datei wundert."""
    try:
        import aufnahme
        weg, hinweis = aufnahme.koder_pruefen()
    except Exception:
        return
    if weg:
        return
    befunde.append(Befund(
        "mp3_koder", HINWEIS,
        hinweis + " Die Predigt wird darum als WAV aufgenommen: rund "
        "115 MB je Stunde statt 22, und die Frist von sieben Tagen "
        "fuellt damit die Platte deutlich schneller.",
        "Vom Stick nachruesten, ohne Netz:  "
        "sudo pacman -U lame-*.pkg.tar.zst",
        was_en="This computer cannot write MP3. Sermons are recorded as "
               "WAV instead: about 115 MB per hour instead of 22.",
        tun_en="Install offline from the stick:  "
               "sudo pacman -U lame-*.pkg.tar.zst"))


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


def _gleiche_befehle(soll, ist, ordner):
    """Sind das dieselben ExecStart-Zeilen, Platzhalter weggedacht?

    dienst.sh setzt DREI Platzhalter ein -- @ORDNER@, @BENUTZER@ und
    @PORT@ -- hier wurde bis 0.3.1 nur der erste ersetzt. In
    devarenu.service.vorlage steht "--port @PORT@", in der
    installierten Unit "--port 8000", und damit galt eine gerade
    geschriebene Unit als veraltet. Dauerhaft: zweimal dienst.sh,
    daemon-reload und Neustart aenderten daran nichts, weil sich
    nichts aendern konnte.

    Die uebrigen Platzhalter werden nicht nachgebaut, sondern als
    "hier steht irgendetwas" gelesen. Ihre Werte sind Sache dieses
    Rechners -- ein anderer Port ist keine veraltete Vorlage. Was
    auffallen soll, ist der Befehl selbst: ein anderer Pfad, ein
    hinzugekommener Schalter."""
    if len(soll) != len(ist):
        return False
    for erwartet, wirklich in zip(soll, ist):
        muster = re.escape(erwartet.replace("@ORDNER@", str(ordner)))
        # Nach re.escape heissen die Platzhalter immer noch @NAME@:
        # @ und Grossbuchstaben sind nichts, was escaped wuerde.
        muster = re.sub(r"@[A-Z]+@", ".+", muster)
        if not re.fullmatch(muster, wirklich):
            return False
    return True


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
        ("devarenu-fenster.service", "devarenu-fenster.service.vorlage"),
        ("devarenu-fenster-wecker.service", "devarenu-fenster-wecker.service.vorlage"),
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
        if soll and ist and not _gleiche_befehle(soll, ist, ordner):
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


def _stimmen(befunde):
    """Liegt zu jeder eingeschalteten Sprache auch ihre Stimme da?

    Bis 0.4.1 stand das nur im Journal. Eine Gemeinde schaltet Farsi
    ein, am Pult steht Farsi, und am Sonntag kommt Text ohne Ton --
    gemerkt hat es niemand, weil niemand das Journal liest.

    Gewaehlt heisst eingeschaltet, nicht moeglich: dass fuer Georgisch
    keine Stimme daliegt, geht eine Gemeinde nichts an, die Georgisch
    nicht anbietet."""
    import zustand as zustandsdatei
    try:
        stand = zustandsdatei.laden()[0]
    except Exception:
        return
    gewaehlt = [stand.get("quelle") or config.AUSGANGSSPRACHE]
    gewaehlt += list(stand.get("ziele") or [])
    ordner = config.BASIS / "voices"
    fehlend = []
    for sprache in dict.fromkeys(gewaehlt):
        pfad = config.STIMMEN.get(sprache)
        if not pfad:
            continue            # Sprache ohne Stimme laeuft als Untertitel
        name = Path(pfad).name
        if not (ordner / f"{name}.onnx").is_file() \
                or not (ordner / f"{name}.onnx.json").is_file():
            fehlend.append(sprache)
    if not fehlend:
        return
    liste = ", ".join(sorted(fehlend))
    # HINWEIS, nicht FEHLT -- und das ist eine Entscheidung mit
    # Narben. Mit FEHLT rollte der Gesundheitscheck nach JEDEM Update
    # zurueck: er wertet einen neuen FEHLT-Befund als "der Rechner
    # ist nach dem Update nicht gesund". Eine Gemeinde, der eine
    # Stimme fehlt, haette damit nie wieder ein Update bekommen --
    # und ausgerechnet das Update haette die Stimme mitgebracht.
    #
    # Es passt auch zur Einteilung dieser Datei: FEHLT heisst "der
    # Betrieb ist gefaehrdet". Ohne Stimme laeuft die Sprache als
    # Untertitel weiter. Das ist schlechter, aber es laeuft.
    befunde.append(Befund(
        "stimme_fehlt", HINWEIS,
        f"Zu {liste} ist die Stimme nicht da. Diese Sprache laeuft am "
        f"Sonntag als Untertitel, ohne Ton.",
        "Vom Stick:  python teile.py --einspielen --quelle <Stick>/teile "
        "--sicherung /tmp/devarenu-teile    oder mit Netz: bash einrichten.sh",
        was_en=f"The voice for {liste} is missing. That language will "
               f"run as subtitles only, without sound.",
        tun_en="From the stick: python teile.py --einspielen ... "
               "or with a connection: bash einrichten.sh"))


def pruefen():
    """Alle Befunde, schwerste zuerst. Leere Liste heisst: alles gut."""
    import netzzustand
    netz = netzzustand.laden()[0]
    befunde = []
    _ordner(befunde)
    _dienste(befunde, netz)
    _netzumbau(befunde, netz, alt=_netz_alt(befunde, netz))
    _autologin(befunde)
    _energie(befunde)
    _sitzung(befunde)
    _wlan(befunde)
    _ollama_gpu(befunde)
    _wartungsfenster(befunde)
    _protokoll(befunde)
    _mp3(befunde)
    _onlineupdate(befunde)
    _testmodus(befunde)
    _vorrat(befunde)
    _stimmen(befunde)
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
