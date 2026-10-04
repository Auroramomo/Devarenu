#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Die Grafikwacht -- und vor allem: dass sie nichts aufhaelt.

    python pruefstand/grafikwacht_test.py

Eine Messung ist eine Auskunft, kein Betriebsteil. Fehlt nvidia-smi,
schlaegt es fehl, haengt es oder liefert Unsinn, darf davon nichts
weiter gehen als eine fehlende Zeile.
"""
import sys
import tempfile
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))
sys.path.insert(0, str(WURZEL / "pruefstand"))

import grafikwacht                                      # noqa: E402
from hilfe import wegwerfordner                         # noqa: E402

fehler = 0


def pruefe(was, erwartet, ist):
    global fehler
    if erwartet == ist:
        print(f"   ok    {was}")
    else:
        fehler += 1
        print(f"   FEHLER {was}: erwartet {erwartet!r}, ist {ist!r}")


grafikwacht.DATEI = wegwerfordner("devarenu-gpu-") / "g.csv"
grafikwacht._tage.clear()
echt = grafikwacht._lauf


def stellen(smi=None, ps=None):
    def _lauf(befehl, frist=8):
        if befehl[0] == "nvidia-smi":
            return smi
        if befehl[0] == "ollama":
            return ps
        return None
    grafikwacht._lauf = _lauf


print("\n1. Ohne nvidia-smi passiert nichts")
stellen(smi=None)
pruefe("karte() gibt None", None, grafikwacht.karte())
pruefe("einmal() gibt None", None, grafikwacht.einmal(4))
pruefe("und schreibt keine Datei", False, grafikwacht.DATEI.exists())
pruefe("anwerfen() startet keinen Faden", None,
       grafikwacht.anwerfen(lambda: True, lambda: 4))

print("\n2. Unsinn aus nvidia-smi wird nicht geglaubt")
for unsinn in ("", "kaputt\n", "a, b, c\n", "1,2\n"):
    stellen(smi=unsinn)
    pruefe(f"{unsinn!r} ergibt None", None, grafikwacht.karte())

print("\n3. Eine saubere Messung")
stellen(smi="10504, 16303, 7\n", ps="NAME ID SIZE PROCESSOR\n"
                                    "gemma4:12b x 8.1 GB 100% GPU\n")
m = grafikwacht.einmal(4)
pruefe("belegt", 10504, m["belegt"])
pruefe("gesamt", 16303, m["gesamt"])
pruefe("Last", 7, m["last"])
pruefe("ganz auf der Karte", False, m["cpu"])
h = grafikwacht.heute()
pruefe("Hoechstwert gemerkt", 10504, h["speicher_hoechst_mb"])
pruefe("Sprachen gemerkt", 4, h["sprachen"])
pruefe("kein CPU-Anteil", False, h["cpu_anteil"])

print("\n4. Hoechstwert bleibt der Hoechstwert")
stellen(smi="9000, 16303, 3\n", ps="gemma4:12b x 8.1 GB 100% GPU\n")
grafikwacht.einmal(4)
pruefe("niedrigere Messung senkt ihn nicht", 10504,
       grafikwacht.heute()["speicher_hoechst_mb"])
pruefe("der Mittelwert wandert mit", 5, grafikwacht.heute()["last_mittel"])

print("\n5. Teils auf der CPU wird erkannt")
for zeile, erwartet in (
        ("gemma4:12b x 8.1 GB 100% GPU\n", False),
        ("gemma4:12b x 8.1 GB 48%/52% CPU/GPU\n", True),
        ("gemma4:12b x 8.1 GB 100% CPU\n", True)):
    stellen(smi="1, 2, 3\n", ps="NAME\n" + zeile)
    pruefe(f"{zeile.strip()[-16:]!r}", erwartet, grafikwacht.modell_auf_cpu())
stellen(smi="1, 2, 3\n", ps="NAME ID SIZE PROCESSOR\n")
pruefe("Modell gar nicht geladen ergibt None -- kein Befund", None,
       grafikwacht.modell_auf_cpu())
stellen(smi="1, 2, 3\n", ps=None)
pruefe("ohne ollama ebenfalls None", None, grafikwacht.modell_auf_cpu())

print("\n6. Einmal CPU-Anteil bleibt stehen")
stellen(smi="12000, 16303, 90\n",
        ps="NAME\ngemma4:12b x 8.1 GB 48%/52% CPU/GPU\n")
grafikwacht.einmal(4)
pruefe("der Tag ist markiert", True, grafikwacht.heute()["cpu_anteil"])
stellen(smi="100, 16303, 1\n", ps="NAME\ngemma4:12b x 8.1 GB 100% GPU\n")
grafikwacht.einmal(4)
pruefe("und bleibt es", True, grafikwacht.heute()["cpu_anteil"])

print("\n7. In der Datei steht nichts ueber Menschen")
inhalt = grafikwacht.DATEI.read_text(encoding="utf-8")
print("   " + inhalt.replace("\n", "\n   ").rstrip())
pruefe("die Spalten sind, was sie sein sollen",
       ";".join(grafikwacht.SPALTEN), inhalt.splitlines()[0])
for verboten in ("10.0.0", "@", "uhr", "name"):
    pruefe(f"kein {verboten!r}", True, verboten not in inhalt.lower())

print("\n8. Neu geladen stehen dieselben Zahlen da")
grafikwacht._tage.clear()
pruefe("Hoechstwert zurueckgelesen", 12000,
       grafikwacht.heute()["speicher_hoechst_mb"])
pruefe("CPU-Anteil zurueckgelesen", True, grafikwacht.heute()["cpu_anteil"])

print("\n9. Eine unlesbare Datei haelt nichts auf")
grafikwacht.DATEI.write_text("kaputt\x00", encoding="utf-8")
grafikwacht._tage.clear()
pruefe("faengt bei nichts an", None, grafikwacht.heute())
stellen(smi="500, 16303, 2\n", ps="NAME\ngemma4:12b x 8.1 GB 100% GPU\n")
grafikwacht.einmal(2)
pruefe("und misst weiter", 500, grafikwacht.heute()["speicher_hoechst_mb"])

print("\n10. Die Spalte \"sprachen\" zaehlt seit 0.4.6 nur Zielsprachen")
from datetime import date, timedelta  # noqa: E402
heute_s = date.today().isoformat()
gestern = (date.today() - timedelta(days=1)).isoformat()
# Eine Datei, wie 0.4.5 sie schrieb: ohne Spalte "zaehlt", gestern und
# heute frueh je eine Zeile mit der alten Zaehlung (Ziele + Ausgang).
alt_kopf = ("datum;speicher_hoechst_mb;speicher_gesamt_mb;last_hoechst;"
            "last_mittel;sprachen;cpu_anteil;messungen\n")
grafikwacht.DATEI.write_text(
    alt_kopf + f"{gestern};15037;16303;96;12;4;nein;269\n"
               f"{heute_s};9000;16303;5;5;4;nein;3\n", encoding="utf-8")
grafikwacht._tage.clear()
pruefe("alte Zeile: Zaehlung leer", "", grafikwacht._tage.get(gestern, {})
       .get("zaehlt", "?") if grafikwacht.heute() else "?")
stellen(smi="9100, 16303, 5\n", ps="NAME\ngemma4:12b x 8.1 GB 100% GPU\n")
grafikwacht.einmal(3)
h = grafikwacht.heute()
pruefe("heute gilt die neue Zaehlung", "ziele", h["zaehlt"])
pruefe("und die Sprachzahl faengt neu an: 3 Ziele, nicht max(4, 3)", 3,
       h["sprachen"])
zeilen_ = grafikwacht.DATEI.read_text(encoding="utf-8").splitlines()
pruefe("der Kopf traegt die neue Spalte", True,
       zeilen_[0].endswith(";zaehlt"))
pruefe("die alte Zeile steht unveraendert da (4 Sprachen, leer)",
       f"{gestern};15037;16303;96;12;4;nein;269;", zeilen_[1])
pruefe("die neue traegt \"ziele\"", True, zeilen_[2].endswith(";ziele"))
text = "\n".join(grafikwacht.zeilen())
pruefe("die alte Zeile sagt es dazu", True,
       "4 Sprachen mit Ausgangssprache" in text)
pruefe("die neue sagt Zielsprachen", True, "3 Zielsprachen" in text)
# Und der Server zaehlt ohne "+ 1".
server_quelle = (WURZEL / "server.py").read_text(encoding="utf-8")
pruefe("server.py zaehlt len(lauf.ziele), ohne + 1", True,
       "lambda: len(lauf.ziele))" in server_quelle
       and "len(lauf.ziele) + 1" not in server_quelle)

print("\n11. Hinweis ab 90 Prozent Tagesspitze")
for belegt, erwartet in ((14000, False), (14672, False), (14673, True),
                         (16000, True)):
    grafikwacht._tage.clear()
    grafikwacht.DATEI.unlink()
    stellen(smi=f"{belegt}, 16303, 5\n",
            ps="NAME\ngemma4:12b x 8.1 GB 100% GPU\n")
    grafikwacht.einmal(3)
    voll = [h for h in grafikwacht.hinweise() if h["kennung"] == "grafik_voll"]
    pruefe(f"{belegt} von 16303 ({100 * belegt / 16303:.1f} %): "
           f"Hinweis {'ja' if erwartet else 'nein'}", erwartet, bool(voll))
h = voll[0]
pruefe("sagt die Prozentzahl", True, "98 Prozent" in h["was"])
pruefe("sagt, was zu tun ist", True, "keine weiteren Programme" in h["tun"])
pruefe("und hat eine englische Fassung", True,
       bool(h["was_en"]) and bool(h["tun_en"]))

print("\n12. Hinweis bei mehr als einem geladenen Modell")
zwei = ("NAME ID SIZE PROCESSOR\n"
        "gemma4:12b x 8.1 GB 100% GPU\n"
        "qwen3:4b y 3.2 GB 100% GPU\n")
grafikwacht._tage.clear()
grafikwacht.DATEI.unlink()
stellen(smi="11000, 16303, 5\n", ps=zwei)
pruefe("zwei Zeilen in ollama ps: zwei Modelle", 2,
       grafikwacht.geladene_modelle())
grafikwacht.einmal(3)
m = [h for h in grafikwacht.hinweise() if h["kennung"] == "grafik_modelle"]
pruefe("aus der laufenden Messung: Hinweis", True, bool(m))
pruefe("nennt die Zahl", True, "2 Sprachmodelle" in m[0]["was"])
pruefe("und was zu tun ist", True, "neu starten" in m[0]["tun"])
stellen(smi="11000, 16303, 5\n", ps="NAME\ngemma4:12b x 8.1 GB 100% GPU\n")
pruefe("frisch gefragt, nur eines: kein Hinweis", [],
       [h for h in grafikwacht.hinweise(frisch=True)
        if h["kennung"] == "grafik_modelle"])
stellen(smi="11000, 16303, 5\n", ps="NAME ID SIZE PROCESSOR\n")
pruefe("keines geladen: kein Hinweis", [],
       [h for h in grafikwacht.hinweise(frisch=True)
        if h["kennung"] == "grafik_modelle"])
stellen(smi="11000, 16303, 5\n", ps=None)
pruefe("ohne ollama: kein Hinweis", [],
       [h for h in grafikwacht.hinweise(frisch=True)
        if h["kennung"] == "grafik_modelle"])

print("\n13. Im Systemcheck: Hinweis, keine Stoerung, fuer Laien")
import systemcheck  # noqa: E402
grafikwacht._tage.clear()
grafikwacht.DATEI.unlink()
stellen(smi="15500, 16303, 5\n", ps=zwei)
grafikwacht.einmal(3)
b = []
systemcheck._grafikspeicher(b)
pruefe("beide Hinweise", ["grafik_modelle", "grafik_voll"],
       sorted(x.kennung for x in b))
pruefe("als HINWEIS, nicht als FEHLT", [systemcheck.HINWEIS] * 2,
       [x.schwere for x in b])
pruefe("am Pult, nicht unter Wartung", [False, False],
       [x.wartung for x in b])
pruefe("mit einem Satz fuer Laien", [True, True], [x.laie for x in b])
pruefe("der Systemcheck ruft ihn auf", True,
       "_grafikspeicher(befunde)" in
       (WURZEL / "systemcheck.py").read_text(encoding="utf-8"))
# Im laufenden Betrieb mischt der Server sie in die Stoerungsansicht.
pruefe("der Server mischt sie in /api/zustand", True,
       '"befunde": befunde_mit_grafik()' in server_quelle)
pruefe("die Stoerungsansicht zeigt den Laien-Satz", True,
       "b.laie ?" in server_quelle)

grafikwacht._lauf = echt
if fehler:
    print(f"\n{fehler} FEHLER")
    sys.exit(1)
print("\nAlle Faelle wie erwartet.")
