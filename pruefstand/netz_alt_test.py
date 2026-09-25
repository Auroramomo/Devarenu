#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wie meldet der Systemcheck ein Netz, das noch nach 0.2.11 aufgebaut ist?

    python pruefstand/netz_alt_test.py

Der Gemeinderechner steht mit dem Aufbau von 0.2.11 da: die
Konfiguration in /etc/dnsmasq.d/, die conf-dir-Zeile von Hand an
/etc/dnsmasq.conf gehaengt, der systemd-Zusatz von Hand geschrieben.
Das laeuft. Bis 0.2.14 meldete der Systemcheck dafuer trotzdem
FEHLT -- "Der Umbau ist halb" --, und am Pult sass jemand, der damit
nichts anfangen konnte.

Geprueft wird gegen Attrappen im Wegwerfordner. NICHTS unter /etc wird
angefasst oder auch nur gelesen.
"""
import sys
import tempfile
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))

import systemcheck
import netzzustand

FEHLER = 0


def pruefe(was, erwartet, ist):
    global FEHLER
    if erwartet == ist:
        print(f"   ok    {was}")
    else:
        print(f"   FEHL  {was}: erwartet {erwartet!r}, ist {ist!r}")
        FEHLER += 1


def lage(ordner, alt_da, neu_da, conf_dir_zeile, zusatz):
    """Baut eine Lage nach und gibt die Befunde zurueck."""
    o = Path(ordner)
    alt = o / "dnsmasq.d" / "devarenu.conf"
    neu = o / "devarenu" / "dnsmasq.conf"
    haupt = o / "dnsmasq.conf"
    zus = o / "dnsmasq.service.d" / "devarenu.conf"
    for p in (alt, neu, zus):
        p.parent.mkdir(parents=True, exist_ok=True)
    if alt_da:
        alt.write_text("interface=enp3s0\n", encoding="utf-8")
    if neu_da:
        neu.write_text("interface=enp3s0\n", encoding="utf-8")
    haupt.write_text(
        "# dnsmasq\n"
        + ("conf-dir=/etc/dnsmasq.d/,*.conf\n" if conf_dir_zeile else ""),
        encoding="utf-8")
    if zusatz:
        zus.write_text(zusatz, encoding="utf-8")

    # Die Pfade umbiegen, statt /etc anzufassen.
    sicher = (netzzustand.DNSMASQ_KONF, netzzustand.DNSMASQ_KONF_ALT,
              systemcheck.DNSMASQ_HAUPT, systemcheck.DNSMASQ_ZUSATZ)
    netzzustand.DNSMASQ_KONF = neu
    netzzustand.DNSMASQ_KONF_ALT = alt
    systemcheck.DNSMASQ_HAUPT = haupt
    systemcheck.DNSMASQ_ZUSATZ = zus
    try:
        netz = {"router": True, "adresse": "10.0.0.1", "maske": 24,
                "schnittstelle": "enp3s0", "rechner": [], "eingerichtet_am": ""}
        befunde = []
        alt_erkannt = systemcheck._netz_alt(befunde, netz)
        systemcheck._netzumbau(befunde, netz, alt=alt_erkannt)
        return alt_erkannt, befunde
    finally:
        (netzzustand.DNSMASQ_KONF, netzzustand.DNSMASQ_KONF_ALT,
         systemcheck.DNSMASQ_HAUPT, systemcheck.DNSMASQ_ZUSATZ) = sicher


ZUSATZ_ALT = ("[Unit]\nAfter=network-online.target\n"
              "[Service]\nExecStart=/usr/sbin/dnsmasq -k\n")
ZUSATZ_NEU = ("[Service]\nExecStart=\n"
              "ExecStart=/usr/sbin/dnsmasq -k --conf-file=/etc/devarenu/dnsmasq.conf\n")

with tempfile.TemporaryDirectory() as t:
    print("\n\033[1m== 1) Der Aufbau von 0.2.11, vollstaendig\033[0m")
    erkannt, befunde = lage(t + "/a", True, False, True, ZUSATZ_ALT)
    kennungen = [b.kennung for b in befunde]
    pruefe("die alte Lage wird erkannt", True, erkannt)
    pruefe("genau ein Befund", 1, len(befunde))
    pruefe("und der heisst netz_alt", ["netz_alt"], kennungen)
    pruefe("er ist ein Hinweis, kein Alarm", systemcheck.HINWEIS,
           befunde[0].schwere)
    pruefe("er sagt, dass es laeuft", True, "funktioniert" in befunde[0].was)
    pruefe("er verweist auf den Wartungsbesuch", True,
           "Wartungsbesuch" in befunde[0].was)
    pruefe("die conf-dir-Zeile ist benannt", True, "conf-dir" in befunde[0].was)
    pruefe("der Zusatz mit Zyklus ist benannt", True,
           "Ordnungszyklus" in befunde[0].was)
    pruefe("die alte Datei ist benannt", True,
           "dnsmasq.d" in befunde[0].was)
    pruefe("auf Englisch steht dasselbe", True,
           "0.2.11 layout" in befunde[0].was_en)
    pruefe("der alte Alarm bleibt weg", False, "dnsmasq_konf" in kennungen)
    pruefe("und der zweite auch", False, "dnsmasq_zusatz" in kennungen)

    print("\n\033[1m== 2) Nur die alte Datei, kein Zusatz\033[0m")
    erkannt, befunde = lage(t + "/b", True, False, False, "")
    pruefe("auch das ist die alte Lage", True, erkannt)
    pruefe("genau ein Befund", 1, len(befunde))
    pruefe("die conf-dir-Zeile wird NICHT behauptet", False,
           "conf-dir" in befunde[0].was)
    pruefe("der Zusatz wird NICHT behauptet", False,
           "systemd-Zusatz" in befunde[0].was)

    print("\n\033[1m== 3) Der neue Aufbau -- nichts zu melden\033[0m")
    erkannt, befunde = lage(t + "/c", False, True, False, ZUSATZ_NEU)
    pruefe("keine alte Lage", False, erkannt)
    pruefe("keine Befunde zur Konfiguration", [],
           [b.kennung for b in befunde
            if b.kennung.startswith(("netz_alt", "dnsmasq"))])

    print("\n\033[1m== 4) BEIDE Dateien -- halb umgezogen, das muss auffallen\033[0m")
    erkannt, befunde = lage(t + "/d", True, True, True, ZUSATZ_ALT)
    kennungen = [b.kennung for b in befunde]
    pruefe("das ist NICHT die ruhige alte Lage", False, erkannt)
    pruefe("kein beschwichtigender Hinweis", False, "netz_alt" in kennungen)
    pruefe("der Ordnungszyklus wird gemeldet", True, "dnsmasq_zyklus" in kennungen)

    print("\n\033[1m== 5) Kein Router -- der Systemcheck haelt sich heraus\033[0m")
    erkannt, befunde = lage(t + "/e", True, False, True, ZUSATZ_ALT)
    print("      (geprueft ueber router=False)")
    netz = {"router": False}
    b2 = []
    pruefe("nichts gemeldet", False, systemcheck._netz_alt(b2, netz))
    pruefe("und keine Befunde", 0, len(b2))

print()
if FEHLER:
    print(f"\033[31m{FEHLER} Fehler.\033[0m")
else:
    print("\033[32mAlle Faelle wie erwartet.\033[0m")
sys.exit(1 if FEHLER else 0)
