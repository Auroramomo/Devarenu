#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fragt: wer verteilt auf dieser Leitung Adressen?

Gebraucht an zwei Stellen, und beide Male geht es um denselben Fehler:
am Zugangspunkt ist DHCP noch eingeschaltet. Dann vergeben zwei Server
Adressen, wer zuerst antwortet entscheidet der Zufall, und die Haelfte
der Handys findet diesen Rechner nicht.

  netz_einrichten.sh   antwortet hier schon jemand, haengt der Rechner
                       im Hausnetz und nicht am Zugangspunkt des Saals.
                       Dann ist der Umbau der falsche Schritt.
  pruefen.sh           antwortet ausser uns noch jemand, ist genau der
                       Fehler da, der sonntags die Haelfte kostet.

Wie: ein DHCPDISCOVER ins Netz, vier Sekunden zuhoeren, die Absender
der Angebote zaehlen. Kein REQUEST -- es wird nichts belegt, nur
gefragt. Als Hardware-Adresse dient die der Schnittstelle selbst und
keine erfundene: eine fremde MAC hinterliesse einen Phantomeintrag in
fremden Leasetabellen.

Dafuer braucht es Port 68 und damit Wurzelrechte. Der Server hat die
bewusst nicht; er erkennt denselben Fehler indirekt (netzpruefung.py,
Abschnitt "zweiter DHCP-Server"). Hier ist die direkte Messung, und sie
laeuft nur, wenn jemand sudo davorsetzt.

    sudo ./dhcp_umschau.py enp3s0

Nur Standardbibliothek: aufgerufen wird es als Wurzel, und das Python
der Wurzel kennt die venv des Dienstes nicht.
"""

import random
import socket
import struct
import sys
import time

COOKIE = b"\x63\x82\x53\x63"


def mac_lesen(schnittstelle: str) -> bytes:
    with open(f"/sys/class/net/{schnittstelle}/address") as f:
        return bytes(int(x, 16) for x in f.read().strip().split(":"))


def frage_bauen(mac: bytes, xid: int) -> bytes:
    """Ein DHCPDISCOVER, so knapp wie es sein darf."""
    p = struct.pack("!BBBBIHHIIII16s64s128s",
                    1,       # Anfrage
                    1,       # Ethernet
                    6,       # Laenge der Hardware-Adresse
                    0,       # Spruenge
                    xid,
                    0,       # Sekunden
                    0x8000,  # bitte per Rundruf antworten
                    0, 0, 0, 0,
                    mac + b"\0" * 10, b"", b"")
    p += COOKIE
    p += b"\x35\x01\x01"              # Nachrichtentyp: DISCOVER
    p += b"\x37\x03\x01\x03\x72"      # erbeten: Maske, Router, Option 114
    p += b"\xff"
    # Auf 300 Bytes auffuellen: aeltere BOOTP-Weiterleitungen verwerfen
    # kuerzere Pakete. dnsmasq nimmt sie, andere nicht -- und gesucht
    # wird hier gerade der andere.
    if len(p) < 300:
        p += b"\0" * (300 - len(p))
    return p


def angebot_lesen(daten: bytes, xid: int):
    """(Absender, Option 114) eines DHCPOFFER, sonst None."""
    if len(daten) < 240 or daten[236:240] != COOKIE:
        return None
    if struct.unpack("!I", daten[4:8])[0] != xid:
        return None            # Antwort auf die Frage eines anderen
    # siaddr nur als Rueckfall: Option 54 ist die verbindliche Angabe,
    # aber nicht jeder Server setzt sie.
    absender = socket.inet_ntoa(daten[20:24])
    option114 = ""
    typ = 0
    i = 240
    while i < len(daten):
        code = daten[i]
        if code == 255:
            break
        if code == 0:
            i += 1
            continue
        if i + 1 >= len(daten):
            break
        n = daten[i + 1]
        wert = daten[i + 2:i + 2 + n]
        if code == 53 and n == 1:
            typ = wert[0]
        elif code == 54 and n == 4:
            absender = socket.inet_ntoa(wert)
        elif code == 114:
            option114 = wert.decode("utf-8", "replace")
        i += 2 + n
    if typ != 2:               # 2 = OFFER. Alles andere geht uns nichts an.
        return None
    return absender, option114


def umschau(schnittstelle: str, sekunden: float = 4.0) -> dict:
    """{Absenderadresse: Option 114}. Leer heisst: niemand antwortet."""
    mac = mac_lesen(schnittstelle)
    xid = random.getrandbits(32)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    # An die Schnittstelle binden, nicht an eine Adresse: beim Umbau hat
    # sie oft noch gar keine.
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE,
                 schnittstelle.encode() + b"\0")
    s.bind(("", 68))
    gefunden = {}
    try:
        s.sendto(frage_bauen(mac, xid), ("255.255.255.255", 67))
        ende = time.time() + sekunden
        while True:
            rest = ende - time.time()
            if rest <= 0:
                break
            s.settimeout(rest)
            try:
                daten, _ = s.recvfrom(2048)
            except (socket.timeout, TimeoutError):
                break
            except OSError:
                break
            erg = angebot_lesen(daten, xid)
            if erg:
                # Mehrere Angebote desselben Servers sind eines.
                gefunden[erg[0]] = erg[1]
    finally:
        s.close()
    return gefunden


def main(argv):
    if len(argv) < 2:
        print("Aufruf: sudo ./dhcp_umschau.py <schnittstelle> [sekunden]")
        return 2
    schnittstelle = argv[1]
    sekunden = float(argv[2]) if len(argv) > 2 else 4.0
    try:
        gefunden = umschau(schnittstelle, sekunden)
    except PermissionError:
        # Absichtlich eigener Rueckgabewert: die Aufrufer unterscheiden
        # "niemand antwortet" von "durfte nicht nachsehen".
        print("KEINE_RECHTE|Port 68 braucht Wurzelrechte. Mit sudo aufrufen.")
        return 3
    except FileNotFoundError:
        print(f"FEHLER|Schnittstelle {schnittstelle} gibt es nicht.")
        return 4
    except OSError as e:
        print(f"FEHLER|{type(e).__name__}: {e}")
        return 4
    for adresse in sorted(gefunden):
        # Eine Zeile je Server, damit ein Shell-Aufrufer sie zaehlen kann.
        print(f"SERVER|{adresse}|{gefunden[adresse]}")
    print(f"ANZAHL|{len(gefunden)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
