#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pult, Anmeldung und QR-Seite aus web/ -- wie vorher aus server.py?

    .venv/bin/python pruefstand/webseiten_test.py

Bis 0.5.1 standen die drei Seiten als Zeichenketten in server.py
(PULT, ANMELDUNG, QR_SEITE). Seit 0.5.2 liegen sie in web/ und werden
bei jedem Aufruf gelesen. Der Umbau sollte am Verhalten nichts
aendern; dieser Pruefstand haelt das fest.

  1) Inhalt: web/*.html, wie der Umbau sie angelegt hat, sind
     zeichengleich mit den Zeichenketten aus 00cfaec (= v0.5.1) --
     so, wie Python sie auswertet, also wie der Browser sie bekam.
     Ist der Umbau committet, gilt der Vergleich fuer DIESEN Commit;
     spaetere Aenderungen am Pult machen ihn nicht rot.
  2) Huelle: der Server aus 00cfaec und der neue laufen nacheinander
     auf demselben Port, der neue mit den Seiten von 0.5.1 in web/.
     Verglichen wird, was
     ein Browser bekommt: Status, Content-Type, Cache-Control, ETag,
     Content-Disposition und jedes Byte. Fuer /pult, /qr, die
     QR-Seite zum Herunterladen, die Anmeldung von aussen und die
     Anmeldung mit falschem Passwort.
  3) Der echte Stand: /pult, /qr und die Anmeldung aus dem heutigen
     web/; was 200 ist, kommt mit no-cache und ETag und antwortet auf
     If-None-Match mit 304. Jede Datei unter web/ muss hier einen
     Weg haben -- eine neue ohne Pruefung macht den Lauf rot.
  4) Fehlt web/pult.html, kommt eine Fehlerseite, und eine pult.html
     im Hauptordner wird NICHT genommen (bis 0.5.1 hatte sie Vorrang).
     Fehlt web/anmeldung.html, kommt von aussen trotzdem niemand ans
     Pult.

Die Ausgabe beider Server liest hilfe.mithoeren mit: ein Traceback
oder "Systemcheck fehlgeschlagen" macht den Lauf rot.
"""

import ast
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hilfe import (VERKNUEPFT, WURZEL, arbeitskopie,  # noqa: E402
                   eigene_adresse, ollama_umlenken, server_starten,
                   server_stoppen, wegwerfordner)

sys.path.insert(0, str(WURZEL))
import pultschutz  # noqa: E402

ROT, GRUEN, GELB, AUS = "\033[31m", "\033[32m", "\033[33m", "\033[0m"
FEHLER = 0
PORT = 8201

# Der Stand vor dem Umbau. Als Commit und nicht als Tag: ein Tag laesst
# sich verschieben, ein Commit nicht.
VORHER = "00cfaec"
SEITEN = {"PULT": "pult.html", "ANMELDUNG": "anmeldung.html",
          "QR_SEITE": "qr.html"}
PASSWORT = "Pruefstand2026"
ZUSTAND = {
    "gemeinde": "Prüfgemeinde Süd",
    "wlan": {"ssid": "Pruefnetz", "passwort": "geheim-123"},
    "pult_passwort": pultschutz.hashen(PASSWORT),
}
KOEPFE = ("content-type", "cache-control", "etag", "content-disposition")


def pruefe(was, erwartet, ist):
    global FEHLER
    if erwartet == ist:
        print(f"   ok    {was}")
    else:
        e, i = repr(erwartet), repr(ist)
        if len(e) + len(i) > 300:
            e, i = e[:140] + " ...", i[:140] + " ..."
        print(f"   {ROT}FEHL{AUS}  {was}: erwartet {e}, ist {i}")
        FEHLER += 1


def merke(t):
    print(f"   {GELB}i{AUS}     {t}")


def titel(t):
    print(f"\n\033[1m== {t}\033[0m")


def holen(port, weg, kopf=None, gastgeber="127.0.0.1", formular=None):
    """(status, {kopf: wert}, bytes). Keine Ausnahme bei 4xx und 5xx."""
    b = urllib.request.Request(f"http://{gastgeber}:{port}{weg}")
    for k, v in (kopf or {}).items():
        b.add_header(k, v)
    if formular is not None:
        b.data = urllib.parse.urlencode(formular).encode("utf-8")
        b.add_header("Content-Type", "application/x-www-form-urlencoded")

    class OhneUmleitung(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None

    oeffner = urllib.request.build_opener(OhneUmleitung)
    try:
        with oeffner.open(b, timeout=30) as a:
            return a.status, {k.lower(): v for k, v in a.headers.items()}, \
                a.read()
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in e.headers.items()}, e.read()
    except Exception as e:
        return 0, {}, str(e).encode()


def seiten_aus(server_py):
    """Die drei Zeichenketten aus einer server.py, ausgewertet."""
    werte = {}
    for k in ast.parse(server_py).body:
        if (isinstance(k, ast.Assign) and len(k.targets) == 1
                and isinstance(k.targets[0], ast.Name)
                and k.targets[0].id in SEITEN):
            werte[SEITEN[k.targets[0].id]] = k.value.value
    return werte


def git(*args):
    return subprocess.run(["git", "-C", str(WURZEL), *args],
                          capture_output=True, check=True).stdout


def alte_kopie(ziel):
    """Der Baum aus VORHER, lauffaehig wie hilfe.arbeitskopie."""
    ziel.mkdir(parents=True, exist_ok=True)
    subprocess.run(["tar", "-x", "-C", str(ziel)],
                   input=git("archive", VORHER), check=True)
    for v in VERKNUEPFT:
        if (WURZEL / v).exists() and not (ziel / v).exists():
            (ziel / v).symlink_to(WURZEL / v)
    z = {"fassung": 3, "quelle": "de", "ziele": ["en"]}
    z.update(ZUSTAND)
    (ziel / "zustand.json").write_text(json.dumps(z), encoding="utf-8")
    os.chmod(ziel / "zustand.json", 0o600)
    ollama_umlenken(ziel)
    return ziel


def web_fuellen(ordner, seiten):
    for name, text in seiten.items():
        with open(ordner / "web" / name, "w", encoding="utf-8",
                  newline="") as f:
            f.write(text)


# =====================================================================
titel(f"1) Inhalt: web/ gegen die Zeichenketten aus {VORHER}")
vorher = seiten_aus(git("show", f"{VORHER}:server.py").decode("utf-8"))
pruefe(f"{VORHER} hat PULT, ANMELDUNG und QR_SEITE",
       sorted(SEITEN.values()), sorted(vorher))
pruefe("in server.py stehen sie nicht mehr", {},
       seiten_aus((WURZEL / "server.py").read_text(encoding="utf-8")))

# Welcher Stand von web/ ist "der Umbau"? Ist er committet, der Commit,
# der web/pult.html angelegt hat -- dann bleibt dieser Fall gruen, auch
# wenn das Pult spaeter waechst. Sonst das Arbeitsverzeichnis.
umbau = git("log", "--diff-filter=A", "--format=%h", "--",
            "web/pult.html").decode().split()
umbau = umbau[-1] if umbau else ""
merke(f"Umbau: {'Commit ' + umbau if umbau else 'Arbeitsverzeichnis'}")
for name in sorted(SEITEN.values()):
    if umbau:
        ist = git("show", f"{umbau}:web/{name}").decode("utf-8")
    else:
        ist = (WURZEL / "web" / name).read_bytes().decode("utf-8")
    pruefe(f"web/{name} zeichengleich ({len(vorher.get(name, ''))} Zeichen)",
           True, ist == vorher.get(name))

# =====================================================================
titel(f"2) Huelle: neuer Server gegen {VORHER}, mit denselben Seiten")
neu = arbeitskopie(wegwerfordner("devarenu-web-neu-"), ZUSTAND)
web_fuellen(neu, vorher)
alt = alte_kopie(wegwerfordner("devarenu-web-alt-"))
pruefe("die alte Kopie hat kein web/", False, (alt / "web").exists())
pruefe("und keine pult.html im Hauptordner", False,
       (alt / "pult.html").exists())

aussen = eigene_adresse()
faelle = [
    ("/pult", {}, "127.0.0.1", None),
    ("/qr", {}, "127.0.0.1", None),
    ("/qr?herunterladen=1", {}, "127.0.0.1", None),
    ("/pult-anmeldung (falsches Passwort)", {}, "127.0.0.1",
     {"passwort": "falsch", "ziel": "/pult"}),
]
if aussen:
    faelle.append(("/pult von aussen (Anmeldung)", {}, aussen, None))
else:
    merke("keine Adresse ausser Loopback -- die Anmeldung von aussen")
    merke("ist NICHT verglichen, nur die mit falschem Passwort.")


def alles_holen():
    antworten = {}
    for weg, kopf, gastgeber, formular in faelle:
        antworten[weg] = holen(PORT, weg.split(" ")[0], kopf, gastgeber,
                               formular)
    etag = antworten["/pult"][1].get("etag", "")
    antworten["304"] = holen(PORT, "/pult", {"If-None-Match": etag})
    return antworten


# NACHEINANDER auf demselben Port, nicht nebeneinander: die QR-Seite
# traegt die Adresse samt Port in ihren Codes, auf zwei Ports saehe sie
# verschieden aus, ohne dass sich etwas geaendert haette. 300 Sekunden:
# mit Whisper brauchte ein Server auf Aurora unter Last ueber 90, die
# Vorgabe von server_starten.
p_alt = server_starten(alt, PORT, warten=300)
try:
    pruefe(f"der Server aus {VORHER} antwortet", 200,
           holen(PORT, "/api/sprachen")[0])
    vorher_antworten = alles_holen()
finally:
    server_stoppen(p_alt)

p_neu = server_starten(neu, PORT, warten=300)
try:
    pruefe("der neue Server antwortet", 200, holen(PORT, "/api/sprachen")[0])
    jetzt_antworten = alles_holen()
    for weg, *_ in faelle:
        a, n = vorher_antworten[weg], jetzt_antworten[weg]
        pruefe(f"{weg}: Status wie vorher ({a[0]})", a[0], n[0])
        pruefe(f"{weg}: Koepfe wie vorher",
               {k: a[1].get(k) for k in KOEPFE},
               {k: n[1].get(k) for k in KOEPFE})
        pruefe(f"{weg}: jedes Byte wie vorher ({len(a[2])} Bytes)",
               True, a[2] == n[2])
    pruefe("/pult: es ist PULT aus server.py von vorher", True,
           jetzt_antworten["/pult"][2] == vorher["pult.html"].encode("utf-8"))
    pruefe("/pult: mit ETag nachgefragt -> 304 wie vorher",
           vorher_antworten["304"][0], jetzt_antworten["304"][0])
except BaseException:
    server_stoppen(p_neu)
    raise

# =====================================================================
titel("3) Der echte Stand aus web/")
web_fuellen(neu, {d.name: d.read_text(encoding="utf-8")
                  for d in (WURZEL / "web").iterdir() if d.is_file()})
geprueft = set()
try:
    for weg, datei in (("/pult", "pult.html"), ("/qr", "qr.html")):
        s, k, inhalt = holen(PORT,weg)
        geprueft.add(datei)
        pruefe(f"{weg}: 200", 200, s)
        pruefe(f"{weg}: Cache-Control no-cache", "no-cache",
               k.get("cache-control"))
        pruefe(f"{weg}: mit ETag", True, bool(k.get("etag")))
        pruefe(f"{weg}: nachgefragt -> 304", 304,
               holen(PORT,weg, {"If-None-Match": k.get("etag", "")})[0])
        pruefe(f"{weg}: anderes ETag -> 200", 200,
               holen(PORT,weg, {"If-None-Match": '"anders"'})[0])
        if datei == "pult.html":
            # Seit 0.5.2 setzt der Server die Fassung ein (Selbst-
            # Neuladen, pult_fassung_test.mjs) -- sonst Byte fuer Byte.
            fassung = (WURZEL / "VERSION").read_text(encoding="utf-8").strip()
            pruefe("/pult ist web/pult.html, nur mit eingesetzter Fassung",
                   True, inhalt == (WURZEL / "web" / "pult.html").read_text(
                       encoding="utf-8").replace("<!--FASSUNG-->", fassung, 1)
                   .encode("utf-8"))
            pruefe("   und die Fassung steht darin", True,
                   f'const SEITENFASSUNG = "{fassung}";'.encode() in inhalt)

    # Die Anmeldung kam schon in 0.5.1 mit 401 und ohne ETag: sie ist
    # eine Antwort auf "du darfst nicht", keine Seite zum Aufheben, und
    # ein Browser speichert 401 nicht. Das bleibt so -- geprueft wird,
    # dass sie aus web/anmeldung.html kommt.
    geprueft.add("anmeldung.html")
    s, k, inhalt = holen(PORT,"/pult-anmeldung", formular={
        "passwort": "falsch", "ziel": "/pult"})
    vorlage = (WURZEL / "web" / "anmeldung.html").read_text(encoding="utf-8")
    pruefe("Anmeldung: 401 wie bisher", 401, s)
    pruefe("Anmeldung: aus web/anmeldung.html, eingesetzt per format()",
           True, inhalt.decode("utf-8") == vorlage.format(
               ziel="/pult",
               fehler="<p class=fehler>Das war nicht das richtige "
                      "Passwort.</p>"))
    if aussen:
        s, k, inhalt = holen(PORT,"/pult", gastgeber=aussen)
        pruefe("von aussen ohne Ausweis: 401 mit der Anmeldung", True,
               s == 401 and b'name=passwort' in inhalt)
        s, k, inhalt = holen(PORT,"/pult-anmeldung", gastgeber=aussen,
                             formular={"passwort": PASSWORT, "ziel": "/pult"})
        keks = (k.get("set-cookie") or "").split(";")[0]
        pruefe("mit Passwort: 303 und ein Ausweis", True,
               s == 303 and keks.startswith(pultschutz.KEKS + "="))
        s, k, inhalt = holen(PORT,"/pult", {"Cookie": keks},
                             gastgeber=aussen)
        pruefe("mit Ausweis von aussen: das Pult, no-cache, ETag", True,
               s == 200 and k.get("cache-control") == "no-cache"
               and bool(k.get("etag")) and inhalt.startswith(b"<!doctype"))

    unter_web = {d.name for d in (WURZEL / "web").iterdir()}
    pruefe("jede Datei unter web/ hat hier einen Weg", [],
           sorted(unter_web - geprueft))
    # Nur ueber ihre Wege, nicht als Ordner: sonst laege das Pult unter
    # /web/pult.html an der Wache vorbei, die nur Wege kennt.
    for name in sorted(unter_web):
        pruefe(f"/web/{name} gibt es nicht (404)", 404,
               holen(PORT, f"/web/{name}")[0])

    # =================================================================
    titel("4) Wenn eine Datei fehlt")
    (neu / "pult.html").write_text("<!doctype html>ALTES PULT IM HAUPTORDNER",
                                   encoding="utf-8")
    (neu / "web" / "pult.html").unlink()
    s, k, inhalt = holen(PORT,"/pult")
    pruefe("ohne web/pult.html: 500", 500, s)
    pruefe("mit einer klaren Fehlerseite", True,
           b"<h1>pult.html fehlt</h1>" in inhalt
           and str(neu / "web" / "pult.html").encode() in inhalt)
    pruefe("die pult.html im Hauptordner wird nicht genommen", False,
           b"ALTES PULT" in inhalt)
    pruefe("kein Rueckfall auf ein eingebautes Pult", False,
           b"<script>" in inhalt)

    (neu / "web" / "anmeldung.html").unlink()
    if aussen:
        for weg in ("/pult", "/qr", "/api/zustand"):
            s, k, inhalt = holen(PORT,weg, gastgeber=aussen)
            pruefe(f"ohne web/anmeldung.html: {weg} von aussen -> 500",
                   500, s)
            pruefe("   mit Fehlerseite, nichts vom Pult kommt durch", True,
                   b"<h1>anmeldung.html fehlt</h1>" in inhalt)
        pruefe("ein offener Weg bleibt offen (/api/sprachen)", 200,
               holen(PORT,"/api/sprachen", gastgeber=aussen)[0])
    else:
        merke("ohne Adresse ausser Loopback nicht pruefbar: was passiert,")
        merke("wenn web/anmeldung.html fehlt und jemand von aussen kommt.")
finally:
    server_stoppen(p_neu)

print()
if FEHLER:
    print(f"{ROT}{FEHLER} Fehler.{AUS}")
    sys.exit(1)
print(f"{GRUEN}Alle Faelle wie erwartet.{AUS}")
