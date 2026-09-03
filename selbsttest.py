#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prueft nach dem Einrichten, ob die Kette wirklich laeuft.

Warum ueberhaupt: einrichten.sh prueft nur, ob Dateien und Pakete da
sind. Das ist etwas anderes als "es funktioniert". Ein Modell kann
heruntergeladen und trotzdem nicht ladbar sein, eine Stimme kann fehlen,
Ollama kann laufen ohne das gebrauchte Modell zu haben, und die
Piper-Schnittstelle hat sich zwischen den Versionen mehrfach geaendert.
Solche Sachen sollen hier auffallen und nicht am Sabbatmorgen.

Der letzte Schritt ist der eigentliche Test: Piper spricht einen Satz,
Whisper hoert ihn sich an und schreibt ihn auf. Kommt der Satz durch,
funktionieren Sprachausgabe und Spracherkennung nachweislich zusammen.

    python selbsttest.py           alles
    python selbsttest.py --schnell ohne Whisper (spart das Modell-Laden)
"""

import io
import sys
import time
import wave
from pathlib import Path

# Der Satz fuer die Durchlaufprobe. Kurz, deutsch, und die Woerter darin
# sind haeufig genug, dass keine Spracherkennung daran scheitern darf.
PROBESATZ = "Der Herr ist mein Hirte, mir wird nichts mangeln."
PRUEFWOERTER = ("herr", "hirte", "mangeln")

GRUEN, GELB, ROT, AUS = "\033[32m", "\033[33m", "\033[31m", "\033[0m"
_stand = {"ok": 0, "warnung": 0, "fehler": 0}


def ok(text):
    _stand["ok"] += 1
    print(f"   {GRUEN}ok{AUS}   {text}")


def warnung(text):
    _stand["warnung"] += 1
    print(f"   {GELB}!{AUS}    {text}")


def fehler(text):
    _stand["fehler"] += 1
    print(f"   {ROT}FEHLT{AUS} {text}")


def abschnitt(text):
    print(f"\n\033[1;34m== {text}{AUS}")


def kurz(e, n=110):
    """Ausnahmen als eine Zeile. Ein voller Traceback hilft hier nicht,
    die Meldung schon."""
    return str(e).replace("\n", " ")[:n]


# ---------------------------------------------------------------- Dateien
def pruefe_dateien():
    abschnitt("Dateien")
    import config

    for datei in ("server.py", "glossar.py", "bibelstellen.py",
                  "skript_lesen.py", "namen_aus_bibel.py",
                  "laengenfaktor.py", "client.html"):
        if (config.BASIS / datei).exists():
            ok(datei)
        else:
            fehler(f"{datei} fehlt, der Server startet ohne sie nicht")

    if config.GLOSSAR_CSV.exists():
        try:
            from glossar import Glossar
            g = Glossar.laden(config.GLOSSAR_CSV)
            ok(f"Glossar: {len(g.eintraege)} Fachbegriffe")
        except Exception as e:
            fehler(f"Glossar nicht ladbar: {kurz(e)}")
    else:
        fehler(f"{config.GLOSSAR_CSV.name} fehlt, Fachbegriffe werden "
               f"deutlich schlechter uebersetzt")

    namen = config.BASIS / "namen_block_b.csv"
    if namen.exists():
        try:
            from bibelstellen import Namensindex
            idx = Namensindex.laden(namen)
            ok(f"Namensindex: {len(idx.eintraege)} Bibelnamen")
        except Exception as e:
            warnung(f"Namensindex nicht ladbar: {kurz(e)}")
    else:
        warnung("namen_block_b.csv fehlt. Laeuft, aber das Kontextfeld am "
                "Pult findet keine Bibelnamen.")

    if (config.BASIS / "logo.png").exists():
        ok("logo.png")
    else:
        warnung("logo.png fehlt, die Seiten laufen ohne Bildmarke")


# ---------------------------------------------------------------- Ollama
def pruefe_ollama():
    abschnitt("Uebersetzung (Ollama)")
    import config
    try:
        import requests
    except ImportError:
        fehler("Paket requests fehlt")
        return

    try:
        antwort = requests.get(config.OLLAMA_URL + "/api/tags", timeout=10)
        antwort.raise_for_status()
        vorhanden = [m["name"] for m in antwort.json().get("models", [])]
    except requests.exceptions.ConnectionError:
        # Der volle Python-Fehler ist hier drei Zeilen lang und sagt nichts,
        # was nicht auch in einem Satz steht.
        fehler(f"Keine Verbindung zu Ollama auf {config.OLLAMA_URL}")
        print("        Laeuft der Dienst?  ollama serve")
        return
    except Exception as e:
        fehler(f"Ollama antwortet unerwartet: {kurz(e)}")
        return
    ok(f"Ollama laeuft, {len(vorhanden)} Modelle installiert")

    # Ollama haengt manchen Namen ein :latest an, manchen nicht.
    stamm = config.LIVE_MODELL.split(":")[0]
    if not any(m == config.LIVE_MODELL or m.startswith(stamm + ":")
               for m in vorhanden):
        fehler(f"{config.LIVE_MODELL} fehlt. Holen mit: "
               f"ollama pull {config.LIVE_MODELL}")
        return
    ok(config.LIVE_MODELL)

    t0 = time.perf_counter()
    try:
        antwort = requests.post(
            config.OLLAMA_URL + "/api/generate",
            json={"model": config.LIVE_MODELL,
                  "prompt": "Uebersetze ins Englische, "
                            "antworte nur mit der Uebersetzung: "
                            "Der Herr ist mein Hirte.",
                  "stream": False,
                  # Dieselben Optionen wie im Livebetrieb, nicht knapper.
                  # Reasoning-Modelle verbrauchen einen Teil des Budgets im
                  # Denkblock; ist num_predict zu klein, bleibt davon nichts
                  # fuer die eigentliche Antwort uebrig und die Probe
                  # scheitert, obwohl das Modell einwandfrei laeuft.
                  # config.py erklaert es an der Definition.
                  "options": config.OLLAMA_OPTIONEN},
            timeout=config.OLLAMA_TIMEOUT)
        antwort.raise_for_status()
        daten = antwort.json()
    except Exception as e:
        fehler(f"Uebersetzung fehlgeschlagen: {kurz(e)}")
        return

    text = (daten.get("response") or "").strip()
    denkblock = (daten.get("thinking") or "").strip()
    grund = daten.get("done_reason") or "kein Grund gemeldet"

    if text:
        ok(f"Probe nach {time.perf_counter()-t0:.1f}s: {text[:60]}")
    elif denkblock:
        # Der Fall, der sich von selbst nicht erklaert: das Modell hat
        # gearbeitet, aber alles im Denkblock verbraucht. "Antwortet leer"
        # haette hier in die falsche Richtung geschickt.
        fehler(f"Modell denkt, antwortet aber nicht (Abbruch: {grund}). "
               f"num_predict in config.OLLAMA_OPTIONEN ist vermutlich "
               f"zu klein.")
        print(f"        Denkblock: {denkblock[:80]}")
    else:
        fehler(f"Modell antwortet leer (Abbruch: {grund})")


# ---------------------------------------------------------------- Piper
def sprich_probe(stimme, ziel, tempo):
    """Spricht den Probesatz in eine WAV-Datei.

    Die Piper-Schnittstelle hat sich zwischen den Versionen mehrfach
    geaendert. Genau wie im Server werden die Varianten der Reihe nach
    ausprobiert, statt eine zu raten."""
    skala = 1.0 / tempo
    versuche = []

    try:
        from piper import SynthesisConfig
        versuche.append(("syn_config", lambda w: stimme.synthesize_wav(
            PROBESATZ, w, syn_config=SynthesisConfig(length_scale=skala))))
    except ImportError:
        pass
    versuche.append(("length_scale", lambda w: stimme.synthesize_wav(
        PROBESATZ, w, length_scale=skala)))
    versuche.append(("schlicht",
                     lambda w: stimme.synthesize_wav(PROBESATZ, w)))

    letzter = None
    for art, aufruf in versuche:
        try:
            puffer = io.BytesIO()
            with wave.open(puffer, "wb") as w:
                aufruf(w)
            daten = puffer.getvalue()
            if len(daten) < 1000:            # nur Kopfdaten, kein Ton
                raise RuntimeError("leere Audioausgabe")
            Path(ziel).write_bytes(daten)
            return art
        except Exception as e:
            letzter = e
    raise RuntimeError(f"keine Aufrufart funktionierte ({kurz(letzter)})")


def pruefe_piper(ziel):
    abschnitt("Sprachausgabe (Piper)")
    import config

    gebraucht = [config.AUSGANGSSPRACHE] + list(config.ZIELSPRACHEN)
    ordner = config.BASIS / "voices"
    fehlend = []
    for sp in dict.fromkeys(gebraucht):
        pfad = config.STIMMEN.get(sp)
        name = pfad.split("/")[-1] if pfad else None
        if name and (ordner / f"{name}.onnx").exists():
            ok(f"{config.SPRACHNAMEN.get(sp, sp)}: {name}")
        else:
            fehlend.append(sp)
    for sp in fehlend:
        # Die Ausgangssprache wird gleich als Fehler gemeldet, weil ohne
        # sie die Durchlaufprobe entfaellt. Nicht doppelt melden.
        if sp == config.AUSGANGSSPRACHE:
            continue
        warnung(f"{config.SPRACHNAMEN.get(sp, sp)} ohne Stimme, "
                f"laeuft als reiner Untertitel")

    quelle = config.STIMMEN.get(config.AUSGANGSSPRACHE, "").split("/")[-1]
    datei = ordner / f"{quelle}.onnx"
    if not datei.exists():
        fehler("Stimme der Ausgangssprache fehlt, Durchlaufprobe entfaellt")
        return False

    try:
        from piper import PiperVoice
    except ImportError as e:
        fehler(f"Paket piper-tts fehlt: {kurz(e)}")
        return False

    t0 = time.perf_counter()
    try:
        stimme = PiperVoice.load(str(datei))
        art = sprich_probe(stimme, ziel, config.LIVE_TEMPO)
    except Exception as e:
        fehler(f"Sprachausgabe fehlgeschlagen: {kurz(e)}")
        return False

    ok(f"Probesatz gesprochen ({art}, {time.perf_counter()-t0:.1f}s)")
    return True


# ---------------------------------------------------------------- Whisper
def pruefe_whisper(quelle):
    abschnitt("Spracherkennung (Whisper)")
    import config

    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        fehler(f"Paket faster-whisper fehlt: {kurz(e)}")
        return

    geraet, rechenart = config.WHISPER_DEVICE, config.WHISPER_COMPUTE
    try:
        import torch
        if geraet == "cuda" and not torch.cuda.is_available():
            warnung("Keine GPU sichtbar, pruefe auf der CPU. Fuer den "
                    "Livebetrieb ist die CPU zu langsam.")
            geraet, rechenart = "cpu", "int8"
    except ImportError:
        pass

    t0 = time.perf_counter()
    try:
        modell = WhisperModel(config.WHISPER_MODELL, device=geraet,
                              compute_type=rechenart,
                              download_root=str(config.MODELL_ORDNER))
    except Exception as e:
        fehler(f"Modell nicht ladbar: {kurz(e)}")
        return
    ok(f"{config.WHISPER_MODELL} geladen ({geraet}, "
       f"{time.perf_counter()-t0:.1f}s)")

    if not quelle or not Path(quelle).exists():
        warnung("Keine Tondatei aus der Sprachausgabe, "
                "Durchlaufprobe entfaellt")
        return

    t0 = time.perf_counter()
    try:
        abschnitte, _ = modell.transcribe(str(quelle),
                                          language=config.WHISPER_SPRACHE,
                                          beam_size=config.WHISPER_BEAM)
        gehoert = " ".join(a.text for a in abschnitte).strip()
    except Exception as e:
        fehler(f"Spracherkennung fehlgeschlagen: {kurz(e)}")
        return

    dauer = time.perf_counter() - t0
    klein = gehoert.lower()
    getroffen = [w for w in PRUEFWOERTER if w in klein]

    print(f"        gesprochen: {PROBESATZ}")
    print(f"        verstanden: {gehoert or '(nichts)'}")
    if len(getroffen) == len(PRUEFWOERTER):
        ok(f"Durchlaufprobe bestanden ({dauer:.1f}s)")
    elif getroffen:
        warnung(f"Nur teilweise verstanden ({len(getroffen)} von "
                f"{len(PRUEFWOERTER)} Woertern). Laeuft, aber unsauber.")
    else:
        fehler("Der gesprochene Satz kam nicht zurueck")


# ---------------------------------------------------------------- Ablauf
def main():
    schnell = "--schnell" in sys.argv
    print(f"\n\033[1;34m== Devarenu, Selbsttest{AUS}")
    print("   Prueft die Kette einmal komplett durch.")

    try:
        import config
    except Exception as e:
        print(f"\n   {ROT}config.py nicht ladbar: {kurz(e)}{AUS}")
        return 2

    config.ERGEBNIS_ORDNER.mkdir(parents=True, exist_ok=True)
    probe = config.ERGEBNIS_ORDNER / "selbsttest.wav"

    pruefe_dateien()
    pruefe_ollama()
    gesprochen = pruefe_piper(probe)
    if schnell:
        abschnitt("Spracherkennung (Whisper)")
        warnung("uebersprungen (--schnell)")
    else:
        pruefe_whisper(probe if gesprochen else None)

    probe.unlink(missing_ok=True)

    abschnitt("Ergebnis")
    print(f"   {_stand['ok']} in Ordnung, {_stand['warnung']} Hinweise, "
          f"{_stand['fehler']} Fehler")
    if _stand["fehler"]:
        print(f"\n   {ROT}Nicht einsatzbereit.{AUS} Das Rote oben zuerst "
              f"beheben, dann erneut:\n     .venv/bin/python selbsttest.py\n")
        return 1
    if _stand["warnung"]:
        print(f"\n   {GELB}Einsatzbereit mit Einschraenkungen.{AUS} "
              f"Die Hinweise oben lesen.\n")
        return 0
    print(f"\n   {GRUEN}Alles bereit.{AUS} Starten mit ./start.sh\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
