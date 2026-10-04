#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Blindes Hoerprobenpaket fuer die Stimmenwahl.

    python werkzeuge/hoerprobe.py --bauen en
    python werkzeuge/hoerprobe.py --bauen ru
    python werkzeuge/hoerprobe.py --auswerten pruefung/rueck_hoerprobe_en.txt

WOFUER

Englisch und Russisch laufen heute mit Stimmen, deren Lizenz fraglich
ist (LIZENZEN.md): en_US-lessac-medium gilt "nur fuer Forschung",
ru_RU-irina-medium nennt gar keine Lizenz. Lizenzfreie Kandidaten
sind gemessen (messungen/laengenfaktor_stimmen.json) -- aber welche
Stimme eine dreiviertel Stunde lang ertraeglich ist, hoert ein Mensch
und rechnet kein Skript. Dasselbe Verfahren wie bei den Pruefpaketen
fuer es und pt, nur auf die Stimme verengt.

BLIND, UND ZWAR RICHTIG

Die Stimmen heissen im Paket nur A, B und C, und die Zuordnung ist JE
SATZ eine andere. Waere sie durchgehend dieselbe, genuegte ein Satz,
um sie zu durchschauen -- und ab da hoerte niemand mehr die Stimme,
sondern seine eigene Vermutung. Die Aufloesung steht in einer
getrennten Schluesseldatei, die NICHT im Paket liegt.

TEMPO

Jede Stimme spricht mit ihrem eigenen Faktor, so wie sie es im
Betrieb taete: TEMPO_STIMME, und wo dort nichts steht, der gemessene
Laengenfaktor. Eine Stimme mit fremdem Tempo zu beurteilen hiesse,
etwas zu hoeren, das es so nie gibt.

NICHT IM REPO

Das Paket liegt unter pruefung/paket_hoerprobe_<sprache>/ und ist
gitignoriert (pruefung/paket_*). Es sind rund sechzig WAV-Dateien;
das Repo geht per "git bundle --all" auf jeden Update-Stick, und was
einmal darin ist, traegt jede Gemeinde fuer immer mit.
"""

import argparse
import csv
import io
import json
import random
import subprocess
import sys
import wave
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))

import config                                            # noqa: E402

PRUEFUNG = WURZEL / "pruefung"
MESSUNG = WURZEL / "messungen" / "laengenfaktor_stimmen.json"

KANDIDATEN = {
    "en": ["en_US-lessac-medium",      # heute im Betrieb
           "en_US-joe-medium",
           "en_US-ljspeech-medium"],
    "ru": ["ru_RU-irina-medium",       # heute im Betrieb
           "ru_RU-dmitri-medium",
           "ru_RU-denis-medium"],
}

BLAU = "\033[1;34m"; GRUEN = "\033[32m"; GELB = "\033[33m"; AUS = "\033[0m"
blau = lambda t: print(f"\n{BLAU}== {t}{AUS}")          # noqa: E731
gut = lambda t: print(f"   {GRUEN}ok{AUS}    {t}")       # noqa: E731
warn = lambda t: print(f"   {GELB}!{AUS}     {t}")       # noqa: E731


# --------------------------------------------------------- Werkzeuge

def piper_pfad():
    """Derselbe Weg wie in werkzeuge/sprachpaket.py."""
    for k in ([sys.executable, "-m", "piper"], ["piper"]):
        try:
            r = subprocess.run(k + ["--help"], capture_output=True,
                               timeout=30, text=True)
            if r.returncode == 0 or "usage" in (r.stdout + r.stderr).lower():
                return k
        except Exception:
            continue
    return None


def stimme_suchen(name):
    p = WURZEL / "voices" / f"{name}.onnx"
    return p if p.exists() else None


def sprich(befehl, modell, text, ziel, tempo=1.0):
    """Spricht und gibt die Dauer zurueck.

    Der Text geht ueber eine Datei und -i, nicht ueber stdin -- unter
    Windows liest Piper stdin in der Konsolen-Codepage. Begruendet in
    werkzeuge/sprachpaket.py, hier derselbe Weg."""
    tmp = ziel.with_suffix(".txt")
    tmp.write_text(text, encoding="utf-8")
    try:
        r = subprocess.run(befehl + ["-m", str(modell), "-i", str(tmp),
                                     "-f", str(ziel),
                                     "--length-scale", f"{1.0 / tempo:.4f}"],
                           capture_output=True, text=True, timeout=300)
    finally:
        tmp.unlink(missing_ok=True)
    if r.returncode != 0 or not ziel.exists():
        raise RuntimeError((r.stderr or "piper ohne Ausgabe")[:200])
    with wave.open(str(ziel)) as w:
        return w.getnframes() / w.getframerate()


def tempo_fuer(stimme, sprache):
    """TEMPO_STIMME, sonst der gemessene Faktor, sonst die Vorgabe."""
    t = config.TEMPO_STIMME.get(stimme)
    if t:
        return t, "TEMPO_STIMME"
    try:
        d = json.loads(MESSUNG.read_text(encoding="utf-8"))
        w = d.get("stimmen", d).get(stimme) or {}
        if w.get("gegen_deutsch"):
            return float(w["gegen_deutsch"]), "gemessen"
    except Exception:
        pass
    return (config.TEMPO_SPRACHE.get(sprache, config.TEMPO_VORGABE),
            "Vorgabe")


def saetze_holen(anzahl=10):
    """Zehn typische Predigtsaetze AUS DEM BESTAND.

    pruefung/saetze_auswahl.csv ist die Auswahl, die fuer die
    Pruefpakete zusammengestellt wurde -- Fallstricke und echte
    Predigtsaetze gemischt. Neue zu erfinden hiesse, die Stimmen an
    Saetzen zu beurteilen, die so nie fallen."""
    pfad = PRUEFUNG / "saetze_auswahl.csv"
    with io.open(pfad, encoding="utf-8-sig", newline="") as f:
        alle = list(csv.DictReader(f, delimiter=";"))
    # Gleichmaessig ueber die Liste, nicht die ersten zehn: vorn
    # stehen die Fallstricke, und eine Stimme soll nicht nur an
    # Sonderfaellen gemessen werden.
    schritt = max(1, len(alle) // anzahl)
    aus = [alle[i] for i in range(0, len(alle), schritt)][:anzahl]
    return aus


def uebersetzen(text, sprache, modell):
    """Wie im Betrieb: ueber das Werk, mit Glossar und Anrede."""
    import server
    if not hasattr(uebersetzen, "_werk"):
        uebersetzen._werk = server.Werk(nur_text=True)
    return uebersetzen._werk.uebersetzen(text, sprache)


# ------------------------------------------------------------- Bauen

def bauen(sprache, modell, seed=0):
    stimmen = KANDIDATEN.get(sprache)
    if not stimmen:
        sys.exit(f"Keine Kandidaten fuer {sprache}. "
                 f"Bekannt: {', '.join(KANDIDATEN)}")
    befehl = piper_pfad()
    if not befehl:
        sys.exit("Piper nicht gefunden. pip install piper-tts")

    ziel = PRUEFUNG / f"paket_hoerprobe_{sprache}"
    ziel.mkdir(parents=True, exist_ok=True)

    blau("Stimmen")
    pfade, tempi = {}, {}
    for st in stimmen:
        p = stimme_suchen(st)
        if not p:
            sys.exit(f"{st}.onnx liegt nicht unter voices/.")
        pfade[st] = p
        tempi[st], woher = tempo_fuer(st, sprache)
        gut(f"{st}  Tempo {tempi[st]:.2f}  ({woher})")

    blau("Saetze")
    saetze = saetze_holen()
    gut(f"{len(saetze)} aus pruefung/saetze_auswahl.csv")

    blau(f"Uebersetzen nach {config.SPRACHNAMEN.get(sprache, sprache)}")
    uebersetzt = []
    for r in saetze:
        z = uebersetzen(r["satz"], sprache, modell)
        uebersetzt.append(z)
        print(f"   {r['nummer']}  {z[:62]}")

    blau("Sprechen")
    # JE SATZ eine andere Reihenfolge. Der Zufall ist festgenagelt,
    # damit sich ein Paket nachbauen laesst -- die Schluesseldatei
    # nennt den Startwert.
    wuerfel = random.Random(seed or 20260404)
    schluessel = []
    zeilen = []
    for n, (r, z) in enumerate(zip(saetze, uebersetzt), 1):
        reihe = stimmen[:]
        wuerfel.shuffle(reihe)
        dateien = {}
        for buchstabe, st in zip("ABC", reihe):
            wav = ziel / f"s{n:02d}_{buchstabe}.wav"
            dauer = sprich(befehl, pfade[st], z, wav, tempi[st])
            dateien[buchstabe] = (wav.name, dauer)
        schluessel.append({"satz": n, "A": reihe[0], "B": reihe[1],
                           "C": reihe[2]})
        zeilen.append({"nr": n, "de": r["satz"], "ziel": z,
                       "dateien": dateien})
        print(f"   {n:2d}  " + "  ".join(
            f"{b}={dateien[b][1]:.1f}s" for b in "ABC"))

    # EIN FESTER SCHLUSSBLOCK.
    #
    # "Welche insgesamt?" laesst sich mit A, B und C nicht
    # beantworten, wenn die Zuordnung je Satz wechselt -- der
    # Buchstabe meint dann bei jedem Satz eine andere Stimme. Darum
    # am Ende dreimal DERSELBE laengere Abschnitt, als X, Y und Z,
    # und diese Zuordnung bleibt. Blind bleibt es trotzdem.
    blau("Schlussblock")
    lang = max(uebersetzt, key=len)
    fest = stimmen[:]
    wuerfel.shuffle(fest)
    probe = {}
    for buchstabe, st in zip("XYZ", fest):
        wav = ziel / f"probe_{buchstabe}.wav"
        dauer = sprich(befehl, pfade[st], lang, wav, tempi[st])
        probe[buchstabe] = (wav.name, dauer)
        print(f"   {buchstabe}  {dauer:.1f}s")

    html_schreiben(sprache, zeilen, ziel, lang, probe)
    gut(f"{ziel}/hoerprobe_{sprache}.html")

    # Die Aufloesung liegt NICHT im Paket.
    s_datei = PRUEFUNG / f"schluessel_hoerprobe_{sprache}.json"
    s_datei.write_text(json.dumps({
        "sprache": sprache,
        "startwert": seed or 20260404,
        "tempo": {st: tempi[st] for st in stimmen},
        "zuordnung": schluessel,
        "schlussblock": {"X": fest[0], "Y": fest[1], "Z": fest[2]},
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    gut(f"{s_datei}  (NICHT ins Paket legen)")
    return ziel


def schuetzen(t):
    return (str(t).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def html_schreiben(sprache, zeilen, ziel, probetext, probe):
    """Eine Seite, offline, gross genug fuers Handy.

    Kein Server, kein Netz: die Antworten stehen im Browser und
    erscheinen am Ende als Text zum Kopieren oder Ausdrucken. Wer
    sie abschickt, entscheidet selbst, wie."""
    name = config.SPRACHNAMEN.get(sprache, sprache)
    probeknoepfe = "".join(
        f'<button class=hoer data-d="{schuetzen(probe[b][0])}">'
        f'<span class=gross>{b}</span>'
        f'<span class=sek>{probe[b][1]:.1f}s</span></button>'
        for b in "XYZ")
    bloecke = []
    for z in zeilen:
        knoepfe = "".join(
            f'<button class=hoer data-d="{schuetzen(z["dateien"][b][0])}">'
            f'<span class=gross>{b}</span>'
            f'<span class=sek>{z["dateien"][b][1]:.1f}s</span></button>'
            for b in "ABC")
        wahl = "".join(
            f'<label><input type=radio name="w{z["nr"]}" value="{b}"> {b}'
            f'</label>' for b in "ABC")
        bloecke.append(f'''
<section class=satz>
  <h2>Satz {z["nr"]} von {len(zeilen)}</h2>
  <p class=de>{schuetzen(z["de"])}</p>
  <p class=ziel lang="{sprache}">{schuetzen(z["ziel"])}</p>
  <div class=knoepfe>{knoepfe}</div>
  <p class=frage>Welche klingt am besten?</p>
  <div class=wahl>{wahl}</div>
</section>''')

    seite = f'''<!doctype html><html lang=de><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Hörprobe {name}</title>
<style>
:root{{color-scheme:light;
 --tinte:#141f52;--grau:#5c6475;--linie:#9aa3b2;--fl:#f5f6f8;
 --schild:-apple-system,"Segoe UI",Roboto,system-ui,sans-serif}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--fl);color:var(--tinte);
 font:17px/1.55 var(--schild);padding:0 0 4rem}}
header{{background:#fff;border-bottom:3px solid var(--tinte);
 padding:1rem}}
h1{{font:400 1.3rem Georgia,serif;margin:0}}
.hin{{font-size:.9rem;color:var(--grau);margin:.5rem 0 0}}
.satz{{background:#fff;border:1px solid var(--linie);margin:1rem;
 padding:1rem}}
.satz h2{{font:600 .78rem var(--schild);text-transform:uppercase;
 letter-spacing:.09em;color:var(--grau);margin:0 0 .6rem}}
.de{{color:var(--grau);font-size:.92rem;margin:0 0 .4rem}}
.ziel{{font-size:1.05rem;margin:0 0 .9rem}}
.knoepfe{{display:flex;gap:.6rem}}
.hoer{{flex:1;min-height:64px;display:flex;flex-direction:column;
 align-items:center;justify-content:center;gap:.1rem;cursor:pointer;
 background:#fff;border:2px solid var(--tinte);color:var(--tinte);
 font:inherit}}
.hoer.laeuft{{background:var(--tinte);color:#fff}}
.hoer .gross{{font:600 1.3rem var(--schild)}}
.hoer .sek{{font-size:.72rem;opacity:.75}}
.frage{{margin:.9rem 0 .4rem;font-size:.9rem;color:var(--grau)}}
.wahl{{display:flex;gap:.5rem}}
.wahl label{{flex:1;display:flex;align-items:center;justify-content:center;
 gap:.4rem;min-height:52px;border:2px solid var(--linie);background:#fff;
 cursor:pointer;font-weight:600}}
.wahl input{{width:1.2rem;height:1.2rem}}
.ende{{background:#fff;border:1px solid var(--linie);margin:1rem;
 padding:1rem}}
.ende h2{{font:400 1.1rem Georgia,serif;margin:0 0 .6rem}}
select,textarea{{width:100%;font:inherit;padding:.6rem;
 border:2px solid var(--linie);background:#fff;min-height:52px}}
textarea{{min-height:6rem}}
button.fertig{{width:100%;min-height:56px;margin-top:1rem;cursor:pointer;
 background:var(--tinte);color:#fff;border:0;font:1.05rem Georgia,serif}}
pre{{white-space:pre-wrap;background:var(--fl);border:1px solid var(--linie);
 padding:.8rem;font-size:.85rem}}
@media print{{.hoer,.fertig{{display:none}}}}
</style>
<header>
  <h1>Hörprobe {name}</h1>
  <p class=hin>Drei Stimmen, A B C. Welche heißt wie, steht hier
  nicht — und sie wechseln von Satz zu Satz. Bitte mit Kopfhörern
  hören und bei jedem Satz ankreuzen, welche am besten klingt.</p>
</header>
{"".join(bloecke)}
<div class=ende>
  <h2>Zum Schluss</h2>
  <p class=hin>Bis hierher hießen die Stimmen bei jedem Satz anders.
  Jetzt dreimal derselbe Abschnitt — und <b>diese</b> drei bleiben,
  was sie sind.</p>
  <p class=ziel lang="{sprache}">{schuetzen(probetext)}</p>
  <div class=knoepfe>{probeknoepfe}</div>
  <p class=frage>Welche Stimme würden Sie insgesamt nehmen?</p>
  <select id=gesamt>
    <option value="">— bitte wählen —</option>
    <option value="X">X</option><option value="Y">Y</option>
    <option value="Z">Z</option>
    <option value="egal">kein Unterschied</option>
  </select>
  <p class=frage>Was ist Ihnen aufgefallen?</p>
  <textarea id=frei placeholder="Zum Beispiel: zu schnell, zu leiernd, Namen falsch betont …"></textarea>
  <button class=fertig id=fertig>Antworten anzeigen</button>
  <pre id=ergebnis hidden></pre>
</div>
<script>
const SPRACHE = "{sprache}";
const ANZAHL = {len(zeilen)};
let spieler = null, aktiv = null;
document.querySelectorAll(".hoer").forEach(k => {{
  k.addEventListener("click", () => {{
    if(spieler){{ spieler.pause(); }}
    if(aktiv){{ aktiv.classList.remove("laeuft"); }}
    if(aktiv === k){{ aktiv = null; return; }}
    spieler = new Audio(k.dataset.d);
    spieler.play().catch(() => {{}});
    spieler.addEventListener("ended", () => k.classList.remove("laeuft"));
    k.classList.add("laeuft");
    aktiv = k;
  }});
}});
document.getElementById("fertig").addEventListener("click", () => {{
  const zeilen = ["Hoerprobe " + SPRACHE];
  for(let i = 1; i <= ANZAHL; i++){{
    const g = document.querySelector('input[name="w' + i + '"]:checked');
    zeilen.push("Satz " + i + ": " + (g ? g.value : "-"));
  }}
  zeilen.push("Insgesamt: "
    + (document.getElementById("gesamt").value || "-"));
  const frei = document.getElementById("frei").value.trim();
  if(frei) zeilen.push("Anmerkung: " + frei.replace(/\\n/g, " "));
  const feld = document.getElementById("ergebnis");
  feld.textContent = zeilen.join("\\n");
  feld.hidden = false;
  feld.scrollIntoView({{behavior: "smooth"}});
}});
</script>
</html>'''
    (ziel / f"hoerprobe_{sprache}.html").write_text(seite, encoding="utf-8")


# -------------------------------------------------------- Auswerten

def auswerten(pfad):
    """Liest die Antworten und loest die Buchstaben auf."""
    text = Path(pfad).read_text(encoding="utf-8")
    sprache = ""
    for zeile in text.splitlines():
        if zeile.lower().startswith("hoerprobe"):
            sprache = zeile.split()[-1].strip()
    if not sprache:
        sys.exit("In der Datei steht nicht, welche Sprache es war.")
    s_datei = PRUEFUNG / f"schluessel_hoerprobe_{sprache}.json"
    if not s_datei.exists():
        sys.exit(f"Schluesseldatei fehlt: {s_datei}")
    schluessel = json.loads(s_datei.read_text(encoding="utf-8"))
    zuordnung = {z["satz"]: z for z in schluessel["zuordnung"]}

    punkte, gesamt = {}, None
    blau(f"Hoerprobe {sprache}")
    for zeile in text.splitlines():
        zeile = zeile.strip()
        if zeile.lower().startswith("satz "):
            try:
                nr = int(zeile.split()[1].rstrip(":"))
                wahl = zeile.split(":")[1].strip()
            except Exception:
                continue
            if wahl not in "ABC" or nr not in zuordnung:
                continue
            st = zuordnung[nr][wahl]
            punkte[st] = punkte.get(st, 0) + 1
            print(f"   Satz {nr:2d}: {wahl} = {st}")
        elif zeile.lower().startswith("insgesamt:"):
            gesamt = zeile.split(":", 1)[1].strip()

    blau("Zusammen")
    for st, n in sorted(punkte.items(), key=lambda p: -p[1]):
        gut(f"{n:2d} von {len(zuordnung)}  {st}")
    fest = schluessel.get("schlussblock") or {}
    if gesamt in fest:
        gut(f"Gesamtwahl: {gesamt} = {fest[gesamt]}")
    elif gesamt == "egal":
        gut("Gesamtwahl: kein Unterschied gehoert")
    elif gesamt in "ABC" and gesamt:
        warn(f"Gesamtwahl steht als {gesamt} da. Die Buchstaben A, B und C "
             f"wechseln je Satz -- das laesst sich nicht aufloesen. "
             f"Massgeblich ist die Zaehlung oben.")
    elif gesamt:
        gut(f"Gesamtwahl: {gesamt}")
    return punkte


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--bauen", metavar="SPRACHE")
    p.add_argument("--auswerten", metavar="DATEI")
    p.add_argument("--modell", default=config.LIVE_MODELL)
    p.add_argument("--startwert", type=int, default=0)
    a = p.parse_args()
    if a.bauen:
        bauen(a.bauen, a.modell, a.startwert)
        return 0
    if a.auswerten:
        auswerten(a.auswerten)
        return 0
    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
