#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Der Datenschutzhinweis in zwei Stufen (0.5.0) -- alles als Entwurf.

    .venv/bin/python pruefstand/datenschutz_test.py

  * Stufe 1 (/api/datenschutz) in der Sprache des Zuhoerers, sonst
    Englisch; mit Gemeinde und Kontakt aus der Einrichtung, und ohne
    die Zeile, wenn eine Angabe fehlt.
  * Stufe 2 (/datenschutz) kommt von diesem Rechner, mit no-cache.
  * Beide tragen sichtbar "Entwurf, vor Freigabe durch den
    Datenschutzbeauftragten".
  * Beide Wege sind fuer Zuhoerer offen, auch mit Pult-Passwort.
  * Die Hoererseite hat den kleinen Link unter "Mehr".
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hilfe import (WURZEL, arbeitskopie, rufen, server_starten,  # noqa: E402
                   server_stoppen, wegwerfordner)

sys.path.insert(0, str(WURZEL))
import datenschutz  # noqa: E402
import pultschutz  # noqa: E402

ROT, GRUEN, AUS = "\033[31m", "\033[32m", "\033[0m"
FEHLER = 0
PORT = 8177
ENTWURF = "Entwurf, vor Freigabe durch den Datenschutzbeauftragten"


def pruefe(was, erwartet, ist):
    global FEHLER
    if erwartet == ist:
        print(f"   ok    {was}")
    else:
        print(f"   {ROT}FEHL{AUS}  {was}: erwartet {erwartet!r}, ist {ist!r}")
        FEHLER += 1


def titel(t):
    print(f"\n\033[1m== {t}\033[0m")


titel("1) Die Texte")
pruefe("der Entwurfsvermerk steht woertlich da", ENTWURF, datenschutz.ENTWURF["de"])
for sp in ("de", "en", "ru", "fa"):
    s = datenschutz.stufe1(sp)
    pruefe(f"Stufe 1 {sp}: fuenf Absaetze, Entwurf, Link", (5, True, True),
           (len(s["absaetze"]), bool(s["entwurf"]), s["link"].startswith("/datenschutz")))
pruefe("eine Sprache ohne Text faellt auf Englisch", "en",
       datenschutz.stufe1("pl")["sprache"])
pruefe("ohne Gemeinde und Kontakt: keine Zeile", [], datenschutz.stufe1("de")["angaben"])
pruefe("nur mit Kontakt: nur die Kontaktzeile", ["Kontakt: buero@x.invalid"],
       datenschutz.stufe1("de", "", "buero@x.invalid")["angaben"])
de = " ".join(datenschutz.STUFE1["de"]["absaetze"])
for wort in ("live übersetzt", "keine Cloud", "kein Konto", "keine App",
             "Aufnahme der Predigt", "sichtbar", "ausgeschaltet"):
    pruefe(f"Stufe 1 sagt: {wort}", True, wort in de)
seite = datenschutz.stufe2_html("de", "Adventgemeinde <Test>", "", "0.5.0")
pruefe("Stufe 2 nennt § 53 DSVO", True, "§ 53" in seite)
pruefe("Stufe 2 nennt Art. 6 Abs. 1 lit. f, als noch zu bestaetigen", True,
       "Art. 6" in seite and "Noch zu bestätigen" in seite)
pruefe("Stufe 2 nennt das Testprotokoll", True, "Testprotokoll" in seite)
pruefe("Stufe 2 schuetzt HTML in der Gemeindeangabe", True,
       "&lt;Test&gt;" in seite and "<Test>" not in seite)
pruefe("Stufe 2 hat den Entwurfsvermerk", True, ENTWURF in seite)

titel("2) Fuer Zuhoerer offen, auch mit Pult-Passwort")
for weg in ("/datenschutz", "/api/datenschutz"):
    pruefe(f"{weg} ist oeffentlich", True, pultschutz.oeffentlich(weg))

titel("3) Der Server")
ordner = arbeitskopie(wegwerfordner("devarenu-datenschutz-"),
                      {"gemeinde": "Adventgemeinde Musterstadt",
                       "kontakt": "datenschutz@beispiel.invalid"})
# Die Arbeitskopie bringt anleitung/ nicht mit; die zwei Blaetter schon.
(ordner / "anleitung").mkdir(exist_ok=True)
for name in ("Devarenu-Aushang-Datenschutz.pdf", "Devarenu-Gastprediger.pdf"):
    if (WURZEL / "anleitung" / name).exists():
        (ordner / "anleitung" / name).write_bytes(
            (WURZEL / "anleitung" / name).read_bytes())
p = server_starten(ordner, PORT)
try:
    code, text = rufen(PORT, "/api/datenschutz?sprache=ru")
    pruefe("Stufe 1 antwortet", 200, code)
    d = json.loads(text) if code == 200 else {}
    pruefe("auf Russisch", "ru", d.get("sprache"))
    pruefe("mit Gemeinde und Kontakt",
           ["Ответственный: Adventgemeinde Musterstadt",
            "Контакт: datenschutz@beispiel.invalid"], d.get("angaben"))
    d = json.loads(rufen(PORT, "/api/datenschutz?sprache=fa")[1])
    pruefe("Farsi von rechts nach links", True, d.get("rtl"))
    code, text = rufen(PORT, "/datenschutz")
    pruefe("Stufe 2 antwortet", 200, code)
    pruefe("mit Gemeinde", True, "Adventgemeinde Musterstadt" in text)
    pruefe("mit Entwurfsvermerk", True, ENTWURF in text)
    code, text = rufen(PORT, "/datenschutz?sprache=en")
    pruefe("auch auf Englisch", True,
           "Draft, pending approval by the data protection officer" in text)
    # Der Kontakt laesst sich am Pult setzen und steht danach im Hinweis.
    code, _ = rufen(PORT, "/api/gemeinde", {"kontakt": "  neu@x.invalid \n"})
    pruefe("das Pult setzt den Kontakt", 200, code)
    d = json.loads(rufen(PORT, "/api/datenschutz?sprache=de")[1])
    pruefe("einzeilig und getrimmt im Hinweis", "Kontakt: neu@x.invalid",
           d["angaben"][-1])
    stand = json.loads((ordner / "zustand.json").read_text(encoding="utf-8"))
    pruefe("und in zustand.json", "neu@x.invalid", stand.get("kontakt"))
    # Die Druckvorlagen (E4) liegen gebaut im Repo und sind abrufbar.
    for teil, name in (("aushang", "Devarenu-Aushang-Datenschutz.pdf"),
                       ("gastprediger", "Devarenu-Gastprediger.pdf")):
        pruefe(f"{name} liegt im Repo", True,
               (WURZEL / "anleitung" / name).exists())
        code, inhalt = rufen(PORT, f"/anleitung.pdf?teil={teil}")
        pruefe(f"/anleitung.pdf?teil={teil} liefert ein PDF", (200, True),
               (code, inhalt.startswith("%PDF")))
finally:
    server_stoppen(p)

titel("4) Die Hoererseite")
client = (WURZEL / "client.html").read_text(encoding="utf-8")
mehr = client.split('<dialog id="mehrblatt">')[1].split("</dialog>")[0]
pruefe("der Link steht unter Mehr, neben Schliessen", True,
       mehr.index('id="ds-link"') < mehr.index('id="mehr-zu"')
       and 'class="mehr-fuss"' in mehr)
pruefe("er fuehrt auch ohne Skript zur ausfuehrlichen Fassung", True,
       'href="/datenschutz"' in mehr)

print()
if FEHLER:
    print(f"{ROT}{FEHLER} Fehler.{AUS}")
    sys.exit(1)
print(f"{GRUEN}Alle Faelle wie erwartet.{AUS}")
