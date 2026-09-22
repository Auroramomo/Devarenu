#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Die Adressen, mit denen ein Handy fragt, ob es Internet hat.

Warum es das gibt: ein WLAN ohne Internet wird von Handys gemieden. iOS
prueft ueber HTTP bei captive.apple.com; antwortet dort jemand mit der
Apple-Erfolgsseite, gilt das Netz als online. Android prueft HTTP und
HTTPS gleichzeitig -- die HTTPS-Pruefung ist ohne Zertifikat nicht zu
bestehen, dort bleibt es bei "eingeschraenkter Verbindung". Windows und
Firefox haben eigene Adressen.

Die Rumpftexte sind am 22.09.2026 von den echten Adressen abgerufen und
byte-genau uebernommen, nicht aus dem Gedaechtnis geschrieben. Zwei
Einzelheiten, die man leicht falsch macht:

  captive.apple.com/hotspot-detect.html   endet auf \\n   (69 Bytes)
  www.apple.com/library/test/success.html endet NICHT    (68 Bytes)

Dieselbe Seite, ein Byte Unterschied. Beide werden so ausgeliefert, wie
sie wirklich kommen.

NIEMALS EINE UMLEITUNG
----------------------
Keine dieser Adressen darf mit 302 antworten. iOS haelt das Netz dann
fuer ein Anmeldeportal und oeffnet den kleinen Anmeldebrowser. Der
schliesst sich, sobald jemand die App wechselt -- und nimmt die
WLAN-Verbindung mit. Genau das soll hier nicht passieren.

Unterschieden wird nach Host-Kopfzeile, damit die eigenen Routen des
Servers unberuehrt bleiben: /pult, /qr und die Zuhoererseite laufen
weiter wie bisher.
"""

import ipaddress
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response

import config

# Byte-genau abgerufen am 22.09.2026.
APPLE_MIT_UMBRUCH = (
    b"<HTML><HEAD><TITLE>Success</TITLE></HEAD><BODY>Success</BODY></HTML>\n")
APPLE_OHNE_UMBRUCH = APPLE_MIT_UMBRUCH[:-1]
WINDOWS_CONNECTTEST = b"Microsoft Connect Test"
WINDOWS_NCSI = b"Microsoft NCSI"
FIREFOX_CANONICAL = (
    b'<meta http-equiv="refresh" content="0;url=https://support.mozilla.org'
    b'/kb/captive-portal"/>')
FIREFOX_SUCCESS = b"success\n"

# Welcher Hersteller fragt unter welchem Namen. Nur zum Mitzaehlen --
# beantwortet wird nach Pfad, weil ein Handy den Host-Kopf auch mal
# anders setzt als erwartet.
HERSTELLER = {
    "connectivitycheck.gstatic.com": "Android",
    "clients3.google.com": "Android",
    "connectivitycheck.android.com": "Android",
    "play.googleapis.com": "Android",
    "captive.apple.com": "Apple",
    "www.apple.com": "Apple",
    "www.msftconnecttest.com": "Windows",
    "www.msftncsi.com": "Windows",
    "dns.msftncsi.com": "Windows",
    "detectportal.firefox.com": "Firefox",
}

router = APIRouter()

# Wer wie oft gefragt hat. Das Pult zeigt es, und im Testplan ist es der
# Beleg, dass ein Handy die Pruefung wirklich bei uns gemacht hat.
zaehler = {}


def _zaehlen(request: Request, was: str):
    host = (request.headers.get("host") or "").split(":")[0].lower()
    wer = HERSTELLER.get(host, "unbekannt")
    zaehler[wer] = zaehler.get(wer, 0) + 1
    zaehler["_letzter"] = f"{wer} {was}"
    if request.client is not None:
        beobachten(request.client.host)


# ------------------------------------------------- zweiter DHCP-Server
#
# Woran man ihn merkt: am Zugangspunkt ist DHCP noch eingeschaltet. Dann
# vergeben zwei Server Adressen, und welcher zuerst antwortet, entscheidet
# der Zufall. Handys aus dem falschen Topf finden diesen Rechner nicht.
#
# Direkt messen liesse sich das nur mit einem eigenen DHCP-Ruf auf Port
# 68 -- dafuer braucht es Wurzelrechte, die der Server bewusst nicht hat.
# Also wird es indirekt erkannt, und zwar am einzigen Ort, an dem es sich
# ohne Rechte zeigt: an der Absenderadresse derer, die ankommen. Wer uns
# erreicht und dabei eine Adresse ausserhalb unseres Netzes traegt, hat
# sie von woanders. Das ist kein Beweis fuer einen zweiten Server, aber
# es ist derselbe Befund, den der Techniker sonst erst sonntags merkt.
#
# Die Umkehrung gilt nicht: wer eine fremde Adresse hat und uns deshalb
# gar nicht erreicht, taucht hier nie auf. pruefen.sh macht deshalb
# zusaetzlich den echten Ruf, mit sudo.
fremde = {}


def _eigenes_netz():
    """Unser Netz als Objekt, oder None, wenn wir nicht Router sind."""
    if not getattr(config, "NETZ_ROUTER", False):
        # In einem fremden Netz sagt eine fremde Adresse gar nichts --
        # dort vergibt ohnehin ein anderer die Adressen.
        return None
    try:
        return ipaddress.ip_network(
            f"{config.NETZ_ADRESSE}/{config.NETZ_MASKE}", strict=False)
    except ValueError:
        return None


def beobachten(ip: str):
    """Merkt sich eine Absenderadresse, die nicht von uns stammt."""
    netz = _eigenes_netz()
    if netz is None:
        return
    try:
        adr = ipaddress.ip_address(ip)
    except ValueError:
        return
    # Der Rechner selbst und alles Ortsgebundene zaehlt nicht: das Pult
    # ruft ueber 127.0.0.1 an, und das ist keine fremde Vergabe.
    if adr.is_loopback or adr.is_link_local or adr.version != 4:
        return
    if adr in netz:
        return
    eintrag = fremde.get(ip)
    fremde[ip] = (eintrag[0] + 1 if eintrag else 1, time.time())
    # Nicht unbegrenzt wachsen lassen: es ist eine Warnlampe, keine
    # Liste. Die aelteste Adresse faellt heraus.
    if len(fremde) > 20:
        aeltest = min(fremde, key=lambda k: fremde[k][1])
        del fremde[aeltest]


def _ohne_zwischenspeicher(r: Response) -> Response:
    # Ein zwischengespeichertes "online" waere schlimmer als keines: das
    # Handy prueft dann gar nicht mehr und merkt einen echten Ausfall
    # nicht.
    r.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    r.headers["Pragma"] = "no-cache"
    return r


# ---------------------------------------------------------------- Android
@router.get("/generate_204")
@router.get("/gen_204")
def android_204(request: Request):
    """Leer, Status 204. Genau das erwartet Android."""
    _zaehlen(request, "generate_204")
    return _ohne_zwischenspeicher(Response(status_code=204))


# ------------------------------------------------------------------ Apple
@router.get("/hotspot-detect.html")
def apple_hotspot(request: Request):
    _zaehlen(request, "hotspot-detect")
    return _ohne_zwischenspeicher(
        Response(content=APPLE_MIT_UMBRUCH, media_type="text/html"))


@router.get("/library/test/success.html")
def apple_success(request: Request):
    # Ein Byte kuerzer als die andere -- so kommt sie vom Original.
    _zaehlen(request, "library/test/success")
    return _ohne_zwischenspeicher(
        Response(content=APPLE_OHNE_UMBRUCH, media_type="text/html"))


# ---------------------------------------------------------------- Windows
@router.get("/connecttest.txt")
def windows_connecttest(request: Request):
    _zaehlen(request, "connecttest")
    return _ohne_zwischenspeicher(
        Response(content=WINDOWS_CONNECTTEST, media_type="text/plain"))


@router.get("/ncsi.txt")
def windows_ncsi(request: Request):
    _zaehlen(request, "ncsi")
    return _ohne_zwischenspeicher(
        Response(content=WINDOWS_NCSI, media_type="text/plain"))


# ---------------------------------------------------------------- Firefox
@router.get("/canonical.html")
def firefox_canonical(request: Request):
    _zaehlen(request, "canonical")
    return _ohne_zwischenspeicher(
        Response(content=FIREFOX_CANONICAL, media_type="text/html"))


@router.get("/success.txt")
def firefox_success(request: Request):
    _zaehlen(request, "success.txt")
    return _ohne_zwischenspeicher(
        Response(content=FIREFOX_SUCCESS, media_type="text/plain"))


# ------------------------------------------------- Captive Portal API
@router.get("/captive-api")
def captive_api(request: Request):
    """RFC 8908. Sagt ausdruecklich: hier ist keine Anmeldung noetig.

    DHCP-Option 114 (RFC 8910) zeigt auf diese Adresse. Geliefert wird
    sie nur, wenn das Geraet sie anfragt -- iOS ab 14 tut das, Android
    ab 11 teilweise. Wer nicht fragt, bekommt sie nicht; das ist der
    Standard und kein Fehler.

    "captive": false heisst: kein Anmeldeportal. Ob das die Anzeige
    "Kein Internet" beeinflusst, ist offen -- der Standard regelt
    Anmeldepflicht, nicht Erreichbarkeit."""
    _zaehlen(request, "captive-api")
    adresse = getattr(config, "NETZ_ADRESSE", "10.0.0.1")
    antwort = JSONResponse({
        "captive": False,
        "venue-info-url": f"http://{adresse}/",
    })
    # Der Standard schreibt diesen Typ vor. Mit application/json
    # erkennen manche Geraete die Antwort nicht als Captive-API.
    antwort.media_type = "application/captive+json"
    antwort.headers["content-type"] = "application/captive+json"
    return _ohne_zwischenspeicher(antwort)


def lage():
    """Was das Pult ueber die Pruefungen anzeigt."""
    d = {k: v for k, v in zaehler.items() if not k.startswith("_")}
    if fremde:
        d["fremde_adressen"] = sorted(fremde)[:5]
    return d
