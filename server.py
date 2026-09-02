#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Devarenu v0.1 — der echte Server.

Bedient dieselbe Schnittstelle wie mock_server.py, rechnet aber wirklich:

    Mikrofon -> Segmentierung -> Whisper -> Uebersetzung -> Piper -> Zuhoerer

Damit bleibt client.html unveraendert.

Aufbau der Verarbeitung, und warum sie so ist:

  Die Segmente werden NACHEINANDER verarbeitet, die drei Zielsprachen eines
  Segments dagegen GLEICHZEITIG. Beides ist Absicht. Nacheinander, weil die
  Reihenfolge beim Zuhoerer stimmen muss; gleichzeitig, weil die Messung
  gezeigt hat, dass drei parallele Anfragen bei kleinen Modellen kaum mehr
  kosten als eine, und das ist der Faktor, der die Latenz traegt.

  Die Segmentgrenze wird live an Sprechpausen gezogen, nicht an Satzzeichen.
  Satzzeichen kennt man erst nach Whisper, also zu spaet.

Aufruf:
    python server.py --geraete            # welche Mikrofone gibt es?
    python server.py --geraet 3
    python server.py --geraet 3 --nur-text
"""

import argparse
import asyncio
import io
import json
import queue
import re
import sys
import threading
import time
import wave
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np

import config
from glossar import Glossar, glossarzeilen, vokalisieren

# Die Ausgangssprache wird nicht uebersetzt: der Text kommt aus der
# Spracherkennung, der Ton ist die Originalaufnahme des Predigers. Damit
# ist sie die einzige Ausgabe ohne Uebersetzungsfehler, und zugleich die
# fuer Schwerhoerige, die mitlesen wollen.
QUELLE = config.AUSGANGSSPRACHE
ZIELSPRACHEN = list(config.ZIELSPRACHEN)
SPRACHEN = [QUELLE] + [s for s in ZIELSPRACHEN if s != QUELLE]
MIKRO_RATE = 16000          # was Whisper erwartet
BLOCK = 512                 # Aufnahmeblock, gut 30 ms


# ================================================================
# Segmentierung
# ================================================================

class Segmentierer:
    """Erkennt Sprechpausen und schneidet daran.

    Bewusst energiebasiert und nicht ueber ein VAD-Modell: laeuft ohne
    zusaetzliche Abhaengigkeit, ohne GPU und ohne Latenz.

    Die Schwelle folgt normalerweise dem Grundpegel des Raums, laesst sich
    am Pult aber festnageln. Das ist der Unterschied zwischen Wohnzimmer
    und Gottesdienst: dort soll das Mikrofon uebersetzt werden, nicht das
    Kind in der ersten Reihe. Eine automatische Schwelle zieht bei einem
    ruhigen Prediger irgendwann so weit herunter, dass sie Nebengeraeusche
    mitnimmt."""

    def __init__(self, pause=0.45, min_dauer=1.6, max_dauer=8.0,
                 vorlauf=0.25, min_sprachdauer=0.9):
        self.pause = pause
        self.min_dauer = min_dauer
        self.max_dauer = max_dauer
        self.min_sprachdauer = min_sprachdauer
        self.grundpegel = 0.004
        self.feste_schwelle = None      # None = automatisch
        self.puffer = []
        self.vorpuffer = deque(maxlen=int(vorlauf * MIKRO_RATE / BLOCK) + 1)
        self.stille_bloecke = 0
        self.spricht = False
        # Beobachtungswerte fuer die Anzeige am Pult
        self.pegel_jetzt = 0.0
        self.pegel_spitze = 0.0
        self.verworfen = 0
        # Zeitpunkte statt reiner Zaehler: entscheidend ist nicht, wie oft
        # ueberhaupt verworfen wurde, sondern ob es GERADE passiert,
        # waehrend jemand spricht. Vor dem Gottesdienst ist ein voller
        # Zaehler belanglos, mitten in der Predigt ein Notfall.
        self.messung = None
        self.verworfen_zeiten = deque(maxlen=40)
        self.zu_leise = deque(maxlen=400)
        self.durchgelassen_zeiten = deque(maxlen=40)
        self.letzter_laut = 0.0

    def pegel(self, block):
        return float(np.sqrt(np.mean(block.astype(np.float64) ** 2)))

    @property
    def schwelle(self):
        if self.feste_schwelle is not None:
            return self.feste_schwelle
        return max(0.0025, self.grundpegel * 3.5)

    def schub(self, block):
        """Nimmt einen Audioblock, gibt ein fertiges Segment zurueck oder None.

        Die Pausenlaenge wird in Audioblöcken gezaehlt, nicht ueber die
        Wanduhr. Sonst wuerde ein kurzer Hänger des Rechners als Sprechpause
        gelten und mitten im Wort schneiden."""
        p = self.pegel(block)
        self.pegel_jetzt = p
        self.pegel_spitze = max(p, self.pegel_spitze * 0.995)

        messung = getattr(self, "messung", None)
        if messung and time.time() < messung["bis"]:
            messung["werte"].append(p)

        # Auch bei fester Schwelle weiterfuehren: er ist der Bezugspunkt,
        # an dem sich erkennen laesst, ob gerade zu leise gesprochen wird
        # oder ob tatsaechlich niemand spricht.
        if p < self.grundpegel:
            self.grundpegel = 0.9 * self.grundpegel + 0.1 * p
        else:
            self.grundpegel = 0.9995 * self.grundpegel + 0.0005 * p
        laut = p > self.schwelle
        if laut:
            self.letzter_laut = time.time()
        elif p > max(self.grundpegel * 2.5, 0.0015):
            # Hoerbar, aber unter der Schwelle: da spricht jemand zu leise,
            # etwa weil er vom Mikrofon weggetreten ist. Fuer die
            # Segmentierung ist das Stille, fuer den Techniker ein Problem.
            self.zu_leise.append(time.time())

        if not self.spricht:
            self.vorpuffer.append(block)
            if laut:
                self.spricht = True
                self.puffer = list(self.vorpuffer)
                self.vorpuffer.clear()
                self.stille_bloecke = 0
                self.laute_bloecke = 1
            return None

        self.puffer.append(block)
        if laut:
            self.laute_bloecke = getattr(self, "laute_bloecke", 0) + 1
        dauer = len(self.puffer) * BLOCK / MIKRO_RATE
        self.stille_bloecke = 0 if laut else self.stille_bloecke + 1
        stille_dauer = self.stille_bloecke * BLOCK / MIKRO_RATE

        fertig = (stille_dauer >= self.pause and dauer >= self.min_dauer) \
            or dauer >= self.max_dauer
        if not fertig:
            return None

        behalten = max(1, len(self.puffer) - max(0, self.stille_bloecke - 3))
        sprachdauer = getattr(self, "laute_bloecke", 0) * BLOCK / MIKRO_RATE
        audio = np.concatenate(self.puffer[:behalten])
        self.puffer = []
        self.spricht = False
        self.stille_bloecke = 0
        self.laute_bloecke = 0

        # Ein Segment mit weniger als knapp einer Sekunde echtem Schall ist
        # kein Sprechen, sondern ein Huster, eine zuschlagende Tuer oder ein
        # Stuhlruecken. Whisper erfindet daraus zuverlaessig einen
        # plausiblen Satz, deshalb gar nicht erst hinschicken.
        if sprachdauer < self.min_sprachdauer:
            self.verworfen += 1
            self.verworfen_zeiten.append(time.time())
            return None
        self.durchgelassen_zeiten.append(time.time())
        return audio

    def einmessen_starten(self, dauer=12.0):
        """Beginnt eine Messung, aus der sich die Schwelle ableiten laesst.

        Beim ersten Einsatz war die Mindestlautstaerke zu hoch eingestellt,
        und es fehlten Saetze. Das ist kein Bedienfehler, sondern eine
        Zumutung: niemand kann aus einem Balken ablesen, wo genau zwischen
        Raumgeraeusch und Prediger die Grenze liegen muss.

        Waehrend der Messung wird nur beobachtet. Die Schwelle wird erst
        danach gesetzt, aus dem, was tatsaechlich zu hoeren war."""
        self.messung = {"bis": time.time() + dauer, "werte": []}

    def einmessen_lage(self):
        if not getattr(self, "messung", None):
            return None
        rest = self.messung["bis"] - time.time()
        return {"laeuft": rest > 0, "rest": max(0.0, round(rest, 1)),
                "proben": len(self.messung["werte"])}

    def einmessen_auswerten(self, sicherheit=0.6):
        """Leitet aus der Messung eine Schwelle ab.

        Der Gedanke: waehrend der Messung spricht jemand, also gibt es
        laute und leise Abschnitte. Das untere Viertel der Messwerte ist
        der Raum, das obere Viertel die Stimme. Die Schwelle gehoert
        dazwischen, aber naeher am Raum als an der Stimme: eine zu hohe
        Schwelle verschluckt Saetze, eine zu niedrige laesst hoechstens
        ein Rascheln durch, das die Mindestsprechdauer ohnehin abfaengt.

        Deshalb sicherheit=0.6, also sechzig Prozent des Weges vom
        Raumgeraeusch zur Stimme, statt der Mitte."""
        messung = getattr(self, "messung", None)
        self.messung = None
        if not messung or len(messung["werte"]) < 40:
            return None
        werte = sorted(messung["werte"])
        ruhe = werte[len(werte) // 10]                 # unteres Zehntel
        stimme = werte[int(len(werte) * 0.85)]         # oberes Sechstel
        if stimme < ruhe * 2.0 or stimme < 0.004:
            # Kein deutlicher Unterschied: entweder hat niemand gesprochen
            # oder der Raum ist so laut wie die Stimme. Dann lieber nichts
            # setzen als etwas Falsches.
            return {"erfolg": False, "ruhe": round(ruhe, 5),
                    "stimme": round(stimme, 5),
                    "text": "Kein klarer Unterschied zwischen Raum und "
                            "Stimme. Beim Einmessen sprechen lassen und "
                            "den Abstand zum Mikrofon wie im Gottesdienst "
                            "halten."}
        schwelle = ruhe + (stimme - ruhe) * sicherheit
        self.feste_schwelle = max(0.0015, min(0.3, schwelle))
        return {"erfolg": True, "ruhe": round(ruhe, 5),
                "stimme": round(stimme, 5),
                "schwelle": round(self.feste_schwelle, 5),
                "text": f"Schwelle gesetzt. Raum {ruhe:.4f}, "
                        f"Stimme {stimme:.4f}."}

    def lage(self, fenster=90.0):
        """Beurteilt, ob die Einstellung gerade Schaden anrichtet.

        Drei Faelle, die im Betrieb verschieden zu bewerten sind:
        still, wenn seit einer Weile niemand spricht; gut, wenn Abschnitte
        durchkommen; und der Notfall, wenn zwar jemand spricht, aber nichts
        durchkommt oder das meiste verworfen wird."""
        jetzt = time.time()
        v = sum(1 for t in self.verworfen_zeiten if jetzt - t < fenster)
        d = sum(1 for t in self.durchgelassen_zeiten if jetzt - t < fenster)
        seit_laut = jetzt - self.letzter_laut if self.letzter_laut else 999

        # Zu leise: hoerbares Signal, das die Schwelle nicht erreicht.
        # Rund 30 Bloecke sind eine Sekunde; ab drei Sekunden solchen
        # Signals in einer halben Minute stimmt die Einstellung nicht mehr.
        leise = sum(1 for t in self.zu_leise if jetzt - t < 30)
        if leise > 90 and seit_laut > 8:
            return {"stufe": "alarm", "verworfen": v, "durch": d,
                    "text": "Es wird gesprochen, aber zu leise für die "
                            "eingestellte Schwelle. Steht der Prediger "
                            "weiter weg? Regler nach links oder neu "
                            "einmessen."}
        if leise > 30 and d == 0 and seit_laut > 8:
            return {"stufe": "warnung", "verworfen": v, "durch": d,
                    "text": "Leises Sprechen unterhalb der Schwelle. "
                            "Wenn Text fehlt, Regler etwas nach links."}

        if seit_laut > 25 and not v:
            return {"stufe": "still", "verworfen": v, "durch": d,
                    "text": "niemand spricht"}
        if v and v >= max(3, 2 * d):
            return {"stufe": "alarm", "verworfen": v, "durch": d,
                    "text": f"{v} Abschnitte verworfen, nur {d} übersetzt. "
                            f"Mindestlautstärke zu hoch?"}
        if seit_laut < 12 and d == 0 and self.spricht is False:
            return {"stufe": "alarm", "verworfen": v, "durch": d,
                    "text": "Ton kommt an, aber nichts wird übersetzt"}
        if v and v >= d:
            return {"stufe": "warnung", "verworfen": v, "durch": d,
                    "text": f"{v} verworfen gegenüber {d} übersetzt"}
        return {"stufe": "gut", "verworfen": v, "durch": d,
                "text": f"{d} Abschnitte übersetzt"}


# ================================================================
# Verarbeitung
# ================================================================

class Werk:
    """Whisper, Uebersetzung und Piper. Alles blockierend, deshalb laeuft es
    in Threads und nicht im Ereignisschleifen-Thread."""

    def __init__(self, nur_text=False):
        from faster_whisper import WhisperModel
        import requests
        self.requests = requests
        self.nur_text = nur_text

        print(f"Whisper {config.WHISPER_MODELL} laedt ...")
        self.whisper = WhisperModel(config.WHISPER_MODELL,
                                    device=config.WHISPER_DEVICE,
                                    compute_type=config.WHISPER_COMPUTE,
                                    download_root=str(config.MODELL_ORDNER))
        self.quelle = QUELLE
        self.glossar = Glossar.laden(config.GLOSSAR_CSV)
        from bibelstellen import Namensindex
        self.namen = Namensindex.laden(config.BASIS / "namen_block_b.csv")
        if self.namen.eintraege:
            print(f"Namensindex: {len(self.namen.eintraege)} Bibelnamen")
        else:
            print("Kein Namensindex (namen_block_b.csv fehlt). Der Prompt "
                  "nutzt dann nur den eingetippten Text.")
        self.stt_prompt = ""
        self.letzter_satz = ""
        self.kontext_stellen = []
        self.kontext_namen = []
        self.skript_namen = []
        self.skript_info = None
        self.verlauf = deque(maxlen=3)

        # Piper einmal laden und behalten. Vorher wurde es je Abschnitt
        # als eigenes Programm gestartet, und die Messung hat gezeigt, dass
        # darin fast die ganze Zeit steckt: 1,7 Sekunden bei nur 1,1- bis
        # 1,5-facher Echtzeit, waehrend Piper laut Herstellerangabe ein
        # Vielfaches schafft. Nicht die Rechenzeit war das Problem, sondern
        # Python-Start, ONNX-Laden und Modell-Einlesen bei jedem Haeppchen.
        # Genau deshalb brachte auch --cuda nichts.
        self.stimmen = {}
        self.piper = None
        self.synth_art = None
        if not nur_text:
            gefunden = stimmen_finden()
            try:
                from piper import PiperVoice
                for sp, datei in gefunden.items():
                    t0 = time.perf_counter()
                    self.stimmen[sp] = PiperVoice.load(str(datei))
                    print(f"Stimme {sp}: {datei.name} "
                          f"({time.perf_counter()-t0:.1f}s)")
                if self.stimmen:
                    self.synth_art = self._synthese_pruefen()
                    self.piper = "modul"
                    print(f"Piper laeuft als Modul ({self.synth_art}).")
            except Exception as e:
                print(f"Piper nicht als Modul nutzbar ({str(e)[:90]}), "
                      f"weiche auf Programmaufruf aus.")
                from laengenfaktor import piper_pfad
                self.piper = piper_pfad()
                self.stimmen = gefunden
            fehlt = [s for s in SPRACHEN if s not in self.stimmen]
            if fehlt:
                print(f"Ohne Stimme, nur Text: {', '.join(fehlt)}")
        self.tmp = config.ERGEBNIS_ORDNER / "live"
        self.tmp.mkdir(parents=True, exist_ok=True)

    def _synthese_pruefen(self):
        """Findet heraus, wie diese Piper-Fassung angesprochen werden will.

        Die Schnittstelle hat sich zwischen den Versionen mehrfach
        geaendert: mal nimmt synthesize_wav eine SynthesisConfig, mal
        einzelne Argumente, mal nur Text und Datei. Statt eine Variante zu
        raten und im Gottesdienst damit aufzulaufen, wird sie einmal beim
        Start ausprobiert."""
        import io
        stimme = next(iter(self.stimmen.values()))
        probe = "Test."
        skala = 1.0 / config.LIVE_TEMPO

        try:
            from piper import SynthesisConfig
            puffer = io.BytesIO()
            with wave.open(puffer, "wb") as w:
                stimme.synthesize_wav(probe, w,
                                      syn_config=SynthesisConfig(
                                          length_scale=skala))
            return "syn_config"
        except Exception:
            pass
        try:
            puffer = io.BytesIO()
            with wave.open(puffer, "wb") as w:
                stimme.synthesize_wav(probe, w, length_scale=skala)
            return "length_scale"
        except Exception:
            pass
        puffer = io.BytesIO()
        with wave.open(puffer, "wb") as w:
            stimme.synthesize_wav(probe, w)
        # Ohne Tempoeinstellung: der Laengenueberhang von Russisch und
        # Persisch muss dann anders aufgefangen werden.
        print("  Hinweis: diese Piper-Fassung nimmt kein Tempo entgegen, "
              "LIVE_TEMPO bleibt wirkungslos.")
        return "schlicht"

    # ---- Whisper ----
    # Bei leisen oder rauschigen Abschnitten erfindet Whisper zuverlaessig
    # Standardsaetze aus seinen Trainingsdaten: Abspaenne von
    # Untertitelungsdiensten, Dankesformeln, Kanalnamen. Die klingen
    # plausibel und wandern sonst ungeprueft in die Uebersetzung.
    ERFUNDEN = re.compile(
        r"^\W*(untertitel|untertitelung|amara\.org|copyright|abonniert|"
        r"vielen dank( fuer|für)? (das|ihre|eure)|"
        r"vielen dank\.?$|danke\.?$|tschüss\.?$|"
        r"bis zum n(ä|ae)chsten mal|"
        r"mit freundlicher unterst(ü|ue)tzung)", re.IGNORECASE)

    def hoeren(self, audio):
        kwargs = dict(language=self.quelle, beam_size=1,
                      vad_filter=False, condition_on_previous_text=False)
        teile = [t for t in [self.stt_prompt, " ".join(self.verlauf)] if t]
        if teile:
            kwargs["initial_prompt"] = " ".join(teile)[-700:]
        segmente, _ = self.whisper.transcribe(audio, **kwargs)
        text = " ".join(s.text.strip() for s in segmente).strip()

        if not text:
            return ""
        if self.ERFUNDEN.match(text):
            return ""
        # Ein Wort, das sich immer wiederholt, ist eine Schleife im Dekoder.
        woerter = text.lower().split()
        if len(woerter) >= 4 and len(set(woerter)) <= 2:
            return ""

        self.verlauf.append(text)
        return text

    # ---- Uebersetzung ----
    def uebersetzen(self, text, sprache, kontext=None):
        treffer = self.glossar.finde_in(text, self.quelle)
        gtext = glossarzeilen(treffer, sprache, quelle=self.quelle)
        von = config.SPRACHNAMEN.get(self.quelle, self.quelle)
        system = (f"Du bist Fachuebersetzer fuer christliche Predigttexte. "
                  f"Uebersetze den Abschnitt von {von} nach "
                  f"{config.SPRACHNAMEN[sprache]}.\n"
                  f"Regeln:\n"
                  f"- Gib ausschliesslich die Uebersetzung aus. Keine "
                  f"Erklaerung, keine Anfuehrungszeichen, kein Markdown.\n"
                  f"- Der Abschnitt stammt aus fortlaufender Rede. "
                  f"Uebersetze genau das Gegebene, ohne es zu "
                  f"vervollstaendigen.\n"
                  f"- Achte auf grammatisch korrekte Endungen und darauf, "
                  f"dass Adjektive und Substantive zusammenpassen.\n"
                  f"- Fuege nichts hinzu und lass nichts weg.")
        if kontext:
            system += (f"\n\nDavor wurde bereits gesprochen und uebersetzt:"
                       f"\n---\n{kontext}\n---\n"
                       f"Das dient NUR der Einordnung: es sagt dir, woran "
                       f"der neue Abschnitt anknuepft, welche Personen und "
                       f"Dinge gemeint sind und in welchem Fall und "
                       f"Geschlecht sie stehen. Uebersetze diesen Teil "
                       f"NICHT und gib ihn NICHT aus. Setze nur den neuen "
                       f"Abschnitt passend fort.")
        if gtext:
            system += ("\n\nWortwahlvorgaben fuer einzelne Fachbegriffe. Sie "
                       "sagen nichts ueber Satzbau oder Betonung.\n" + gtext)
        a = self.requests.post(
            f"{config.OLLAMA_URL}/api/chat",
            json={"model": config.LIVE_MODELL, "stream": False, "think": False,
                  "options": {"temperature": 0.1, "num_predict": 400},
                  "messages": [{"role": "system", "content": system},
                               {"role": "user", "content": text}]},
            timeout=30)
        a.raise_for_status()
        t = a.json()["message"]["content"]
        if "</think>" in t:
            t = t.split("</think>", 1)[1]
        return re.sub(r"[*`]+", "", t).strip().strip('"').strip()

    # ---- Piper ----
    def original_ablegen(self, audio, nummer):
        """Legt den aufgenommenen Abschnitt als Datei ab, unveraendert.

        Fuer die Ausgangssprache wird nichts synthetisiert. Wer mitliest,
        hoert den Prediger selbst, und Schwerhoerige bekommen seine Stimme
        direkt ins Ohr statt einer Nachbildung."""
        datei = self.tmp / f"{self.quelle}_{nummer:05d}.wav"
        with wave.open(str(datei), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(MIKRO_RATE)
            w.writeframes((np.clip(audio, -1.0, 1.0) * 32767)
                          .astype(np.int16).tobytes())
        return datei, len(audio) / MIKRO_RATE

    def sprechen(self, text, sprache, nummer):
        if self.nur_text or sprache not in self.stimmen:
            return None, 0.0
        if sprache == "fa":
            # Erst hier, nicht frueher: der Uebersetzungsprompt und die
            # Compliance-Messung arbeiten mit der unvokalisierten Form.
            text = vokalisieren(self.glossar, text)

        datei = self.tmp / f"{sprache}_{nummer:05d}.wav"
        if self.piper == "modul":
            # Piper rechnet umgekehrt: kleinere length_scale bedeutet
            # kuerzere Phoneme, also schnelleres Sprechen.
            skala = 1.0 / config.LIVE_TEMPO
            stimme = self.stimmen[sprache]
            with wave.open(str(datei), "wb") as ziel:
                if self.synth_art == "syn_config":
                    from piper import SynthesisConfig
                    stimme.synthesize_wav(
                        text, ziel, syn_config=SynthesisConfig(
                            length_scale=skala))
                elif self.synth_art == "length_scale":
                    stimme.synthesize_wav(text, ziel, length_scale=skala)
                else:
                    stimme.synthesize_wav(text, ziel)
            with wave.open(str(datei)) as w:
                return datei, w.getnframes() / w.getframerate()

        from laengenfaktor import sprich
        dauer = sprich(self.piper, self.stimmen[sprache], text, datei,
                       config.LIVE_TEMPO)
        return datei, dauer

    @staticmethod
    def lautstaerke_angleichen(datei, ziel=0.85):
        """Bringt eine erzeugte Datei auf einen einheitlichen Pegel.

        Die Piper-Stimmen stammen von verschiedenen Sprechern und sind
        unterschiedlich laut aufgenommen. Im Gottesdienst faellt das sofort
        auf: die persische Stimme war deutlich leiser als die anderen, und
        wer sie hoerte, verstand weniger. Statt eine Stimme einzeln
        hochzudrehen, wird jede Ausgabe auf dieselbe Spitze gebracht.

        Sehr leise Ausgaben werden hoechstens verachtfacht: sonst wuerde
        bei einem fast stillen Stueck nur das Rauschen verstaerkt."""
        try:
            with wave.open(str(datei)) as w:
                anzahl, rate, breite = (w.getnframes(), w.getframerate(),
                                        w.getsampwidth())
                roh = np.frombuffer(w.readframes(anzahl), dtype=np.int16)
            if not len(roh):
                return
            spitze = float(np.abs(roh).max()) / 32768.0
            if spitze < 0.001:
                return
            faktor = min(ziel / spitze, 8.0)
            if abs(faktor - 1.0) < 0.05:
                return
            neu = np.clip(roh.astype(np.float32) * faktor,
                          -32768, 32767).astype(np.int16)
            with wave.open(str(datei), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(breite)
                w.setframerate(rate)
                w.writeframes(neu.tobytes())
        except Exception:
            # Eine misslungene Anpassung darf die Ausgabe nicht verhindern.
            pass

    def eine_sprache(self, text, sprache, nummer, kontext=None, rohton=None):
        t0 = time.perf_counter()
        ziel = (text if sprache == self.quelle
                else self.uebersetzen(text, sprache, kontext))
        t1 = time.perf_counter()

        if sprache == self.quelle and rohton is not None:
            # Kein Piper: der echte Prediger klingt besser als jede
            # synthetische Stimme, und der Ton liegt ohnehin vor. Spart
            # nebenbei eine Synthese je Abschnitt.
            datei, dauer = self.original_ablegen(rohton, nummer)
        else:
            datei, dauer = self.sprechen(ziel, sprache, nummer)
        if datei and sprache != self.quelle:
            # Nur synthetische Stimmen angleichen. Am Originalton wird
            # nichts gedreht, sonst atmet die Lautstaerke von Abschnitt zu
            # Abschnitt und klingt unruhig.
            self.lautstaerke_angleichen(datei, config.LIVE_LAUTSTAERKE)
        return {"sprache": sprache, "text": ziel, "datei": datei,
                "dauer": dauer, "mt": t1 - t0,
                "tts": time.perf_counter() - t1}


# ================================================================
# Der Lauf
# ================================================================

SATZENDE = re.compile(r"[.!?…]\s*[\"»)]?\s*$")


class Satzsammler:
    """Fasst Sprechabschnitte zu ganzen Saetzen zusammen.

    Der Segmentierer schneidet an Sprechpausen, weil er live nichts anderes
    kann: Satzzeichen kennt man erst nach Whisper. Uebersetzt man diese
    Bruchstuecke einzeln, entstehen genau die Fehler, die eine russische
    Muttersprachlerin bemaengelt hat: falsche Wortendungen.

    Russisch hat sechs Faelle, und welcher richtig ist, ergibt sich aus der
    Rolle im Satz. Bekommt das Modell nur "die Rechtfertigung", kann es
    nicht wissen, ob das Subjekt oder Objekt ist, und raet. Bei Adjektiven
    ist es schlimmer: sie richten sich nach ihrem Substantiv, und wenn das
    im naechsten Bruchstueck steht, passt die Endung nicht.

    Deshalb wird gesammelt, bis Whisper ein Satzzeichen setzt. Damit die
    Ausgabe bei einem Redner ohne Punkt nicht stehenbleibt, greifen zwei
    Notbremsen: eine Hoechstzahl an Woertern und eine Hoechstwartezeit."""

    def __init__(self, max_woerter=40, max_warten=9.0):
        self.max_woerter = max_woerter
        self.max_warten = max_warten
        self.teile = []
        self.seit = None

    def anfang(self):
        """Der bisher gesammelte Satzanfang, ohne ihn abzuschliessen.

        Damit laesst sich ein Bruchstueck sofort uebersetzen und trotzdem
        einordnen: das Modell sieht, woran es anknuepft, und muss den Fall
        nicht raten. Kostet keine Wartezeit."""
        return " ".join(self.teile)

    def mitlesen(self, text):
        """Wie schub, aber ohne zurueckzuhalten: sammelt nur mit, damit
        anfang() weiss, wo im Satz man gerade ist."""
        if not text.strip():
            return
        if SATZENDE.search(text):
            self.teile = []
            self.seit = None
        else:
            self.teile.append(text.strip())
            if self.seit is None:
                self.seit = time.time()
            # Nicht unbegrenzt sammeln: bei einem Redner ohne Punkt wuerde
            # der Kontext sonst immer laenger und irgendwann unbrauchbar.
            if len(" ".join(self.teile).split()) > self.max_woerter:
                self.teile = self.teile[-2:]

    def schub(self, text):
        """Nimmt einen erkannten Abschnitt, gibt einen fertigen Satz
        zurueck oder None, wenn noch gewartet wird."""
        if not text.strip():
            return None
        self.teile.append(text.strip())
        if self.seit is None:
            self.seit = time.time()
        gesamt = " ".join(self.teile)

        fertig = bool(SATZENDE.search(gesamt)) \
            or len(gesamt.split()) >= self.max_woerter \
            or (time.time() - self.seit) >= self.max_warten
        if not fertig:
            return None
        self.teile = []
        self.seit = None
        return gesamt

    def rest(self):
        """Was am Ende noch im Puffer liegt, damit der letzte Satz einer
        Predigt nicht verlorengeht."""
        if not self.teile:
            return None
        gesamt = " ".join(self.teile)
        self.teile = []
        self.seit = None
        return gesamt


class Mitschnitt:
    """Schreibt den eingehenden Ton in eine Datei.

    Der Ton laeuft ohnehin durch, die Aufnahme kostet also nichts ausser
    Speicherplatz: eine Stunde belegt rund 115 MB. Sie ist zugleich der
    Ersatz fuer die Aufnahme auf USB-Stick, die am Mischpult nicht mehr
    moeglich ist, sobald der Rechner ueber USB angeschlossen ist. Beides
    zugleich unterstuetzt das Pult nicht.

    Geschrieben wird fortlaufend, nicht erst am Ende. Faellt der Strom aus
    oder stuerzt etwas ab, ist alles bis zu diesem Zeitpunkt erhalten."""

    def __init__(self, ordner):
        self.ordner = Path(ordner)
        self.datei = None
        self.griff = None
        self.rahmen = 0

    @property
    def laeuft(self):
        return self.griff is not None

    def starten(self):
        if self.griff:
            return self.datei
        self.ordner.mkdir(parents=True, exist_ok=True)
        self.datei = self.ordner / f"predigt_{time.strftime('%Y-%m-%d_%H-%M')}.wav"
        self.griff = wave.open(str(self.datei), "wb")
        self.griff.setnchannels(1)
        self.griff.setsampwidth(2)
        self.griff.setframerate(MIKRO_RATE)
        self.rahmen = 0
        print(f"Mitschnitt laeuft: {self.datei.name}")
        return self.datei

    def schreiben(self, block):
        if not self.griff:
            return
        try:
            self.griff.writeframes(
                (np.clip(block, -1.0, 1.0) * 32767).astype(np.int16).tobytes())
            self.rahmen += len(block)
        except Exception:
            pass

    def beenden(self):
        if not self.griff:
            return None
        try:
            self.griff.close()
        except Exception:
            pass
        self.griff = None
        dauer = self.rahmen / MIKRO_RATE
        print(f"Mitschnitt beendet: {self.datei.name}, {dauer/60:.1f} min")
        return {"datei": self.datei.name, "minuten": round(dauer / 60, 1)}

    def lage(self):
        if not self.griff:
            return None
        return {"datei": self.datei.name,
                "minuten": round(self.rahmen / MIKRO_RATE / 60, 1)}


class Lauf:
    def __init__(self, werk, segmentierer=None):
        self.werk = werk
        self.segmentierer = segmentierer
        self.laeuft = False
        self.n = 0
        self.begonnen = None
        self.hoerer = defaultdict(set)
        self.toene = {}                    # (sprache, nummer) -> Path
        self.warteschlange = queue.Queue()
        self.letzte = deque(maxlen=30)
        self.latenzen = []
        # Eigene Zeitbasis fuer den Dateimodus. self.begonnen zaehlt ab dem
        # Druck aufs Pult, die Datei startet aber erst nach dem Dekodieren,
        # und das dauert bei einer halben Stunde Ton mehrere Sekunden. Ohne
        # eigene Basis waere die gemessene Latenz um diesen Betrag zu hoch.
        self.datei_beginn = None
        self.datei_tempo = 1.0
        self.wlan = {"ssid": "", "passwort": ""}
        # Sprachen sind zur Laufzeit umschaltbar, nicht fest verdrahtet.
        # Eine Gemeinde braucht nie alle gleichzeitig, sondern zwei bis
        # vier, und die Rechenzeit haengt genau daran. Dasselbe Geraet
        # bedient damit den deutschen und den ukrainischen Gottesdienst,
        # nur mit anderer Einstellung.
        self.quelle = QUELLE
        self.ziele = list(ZIELSPRACHEN)
        self.sammler = Satzsammler()
        self._letzte_warnung = -1
        # "kontext" ist der Mittelweg: sofort uebersetzen wie bisher, aber
        # mit dem bisherigen Satzanfang als Einordnung. Keine zusaetzliche
        # Wartezeit, trotzdem weiss das Modell, woran es anknuepft.
        self.betrieb = "kontext"
        # Rueckkanal vom Saal ans Pult. Zuhoerer koennen etwas melden, was
        # sonst niemand erfaehrt: dass eine Sprache fehlt, der Ton zu leise
        # ist oder schlicht, dass es hilft. Bewusst nur in diese Richtung
        # und ohne Antwort: es ist eine Meldung, kein Gespraech.
        self.nachrichten = deque(maxlen=40)
        self.audio_schluessel = "gemeinde"
        self.audio_quelle = None
        self.mitschnitt = Mitschnitt(config.ERGEBNIS_ORDNER / "predigten")
        self.schleife = None
        self.pool = ThreadPoolExecutor(max_workers=len(SPRACHEN) + 1)

    # ---- Zuhoerer ----
    async def anmelden(self, ws, sprache):
        self.hoerer[sprache].add(ws)
        await self._senden(ws, {"typ": "zustand", "live": self.laeuft,
                                "gesendet": self.n})

    def abmelden(self, ws, sprache):
        self.hoerer[sprache].discard(ws)

    @property
    def sprachen(self):
        """Quellsprache zuerst, dann die Zielsprachen ohne Dubletten."""
        return [self.quelle] + [s for s in self.ziele if s != self.quelle]

    @property
    def anzahl(self):
        return {sp: len(self.hoerer.get(sp, ())) for sp in self.sprachen}

    def sprachen_setzen(self, quelle=None, ziele=None):
        """Stellt um, waehrend der Server laeuft.

        Zuhoerer einer abgewaehlten Sprache werden getrennt, sonst warten
        sie auf Abschnitte, die nie kommen. Das Whisper-Modell bleibt
        geladen: die Erkennungssprache ist ein Aufrufparameter, kein
        Bestandteil des Modells."""
        vorher = set(self.sprachen)
        if quelle:
            self.quelle = quelle
        if ziele is not None:
            self.ziele = [z for z in ziele if z in config.SPRACHNAMEN]
        self.werk.quelle = self.quelle
        self.sammler.teile = []
        self.werk.letzter_satz = ""
        entfallen = vorher - set(self.sprachen)
        return entfallen

    # ---- Steuerung ----
    async def starten(self):
        """Anlaufen und die Zuhoerer davon in Kenntnis setzen.

        Beim Anhalten wurde das immer gemeldet, beim Starten nicht: wer
        waehrend einer Pause wartete, sah nicht, dass es weitergeht."""
        if not self.laeuft:
            self.laeuft = True
            self.begonnen = self.begonnen or time.time()
        await self._streuen_alle({"typ": "zustand", "live": True})

    async def anhalten(self):
        self.laeuft = False
        await self._streuen_alle({"typ": "zustand", "live": False})

    async def zuruecksetzen(self):
        await self.anhalten()
        self.n = 0
        self.begonnen = None
        self.letzte.clear()
        self.werk.verlauf.clear()

    # ---- Verarbeitung ----
    async def verarbeiten(self):
        """Nimmt Segmente aus der Warteschlange und schiebt sie durch die
        Kette. Ein Segment nach dem anderen, damit die Reihenfolge stimmt."""
        eis = asyncio.get_running_loop()
        while True:
            try:
                audio, sprechende = self.warteschlange.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.05)
                continue
            if not self.laeuft:
                continue

            t0 = time.perf_counter()
            audiodauer = len(audio) / MIKRO_RATE
            try:
                text = await eis.run_in_executor(self.pool, self.werk.hoeren, audio)
            except Exception as e:
                print(f"  Whisper: {str(e)[:90]}")
                continue
            if not text or len(text) < 2:
                continue
            stt = time.perf_counter() - t0

            vorlauf = None
            if self.betrieb == "satz":
                gesammelt = self.sammler.schub(text)
                if gesammelt is None:
                    print(f"[   .] {audiodauer:4.1f}s Ton, sammle | {text[:56]}")
                    continue
                text = gesammelt
            elif self.betrieb == "kontext":
                vorlauf = self.sammler.anfang()
                self.sammler.mitlesen(text)

            nummer = self.n
            self.n += 1

            # Deutsch braucht keine Uebersetzung, nur Vertonung. Es laeuft
            # trotzdem im selben Rutsch, damit die Reihenfolge stimmt.
            # Der zuletzt uebersetzte Satz geht als Kontext mit. Er loest
            # Bezuege auf, an denen ein isolierter Satz scheitert: Pronomen,
            # Geschlecht, Zeitform. Fuer flektierende Sprachen wie Russisch
            # ist das der Unterschied zwischen passender und geratener
            # Endung.
            if self.betrieb == "kontext":
                # Der angefangene Satz zaehlt mehr als der letzte fertige:
                # er sagt, woran das Bruchstueck grammatisch anschliesst.
                kontext = vorlauf or self.werk.letzter_satz
            elif self.betrieb == "satz":
                kontext = self.werk.letzter_satz
            else:
                kontext = None
            auftraege = [eis.run_in_executor(self.pool, self.werk.eine_sprache,
                                             text, sp, nummer, kontext,
                                             audio if sp == self.quelle else None)
                         for sp in self.sprachen]
            ergebnisse = await asyncio.gather(*auftraege, return_exceptions=True)

            gesamt = time.perf_counter() - t0
            print(f"[{nummer:4}] {audiodauer:4.1f}s Ton, STT {stt:.2f}s, "
                  f"gesamt {gesamt:.2f}s | {text[:60]}")
            if self.segmentierer:
                lage = self.segmentierer.lage()
                if lage["stufe"] == "alarm" and nummer != self._letzte_warnung:
                    print(f"       ACHTUNG: {lage['text']}")
                    self._letzte_warnung = nummer

            for e in ergebnisse:
                if isinstance(e, Exception):
                    print(f"        Fehler: {str(e)[:80]}")
                    continue
                nachricht = {"typ": "segment", "id": nummer, "text": e["text"],
                             "absatz_ende": False, "dauer": round(e["dauer"], 2)}
                if e["datei"]:
                    self.toene[(e["sprache"], nummer)] = e["datei"]
                    nachricht["audio"] = f"/ton/{e['sprache']}/{nummer}"
                await self._streuen(e["sprache"], nachricht)

            self.werk.letzter_satz = text
            eintrag = {"id": nummer, "deutsch": text,
                       "stt": round(stt, 2), "gesamt": round(gesamt, 2)}
            if sprechende is not None and self.datei_beginn:
                # Echte Latenz: wie lange nach dem letzten gesprochenen Wort
                # steht die Uebersetzung bereit. Nur im Dateimodus messbar,
                # weil dort die Sprechposition bekannt ist.
                # Wanduhr seit Beginn der Wiedergabe, minus dem Zeitpunkt,
                # zu dem der Abschnitt zu Ende gesprochen war. Bei
                # beschleunigter Wiedergabe muss die Sprechposition
                # entsprechend umgerechnet werden.
                eintrag["latenz"] = round(
                    (time.perf_counter() - self.datei_beginn)
                    - sprechende / self.datei_tempo, 2)
                self.latenzen.append(eintrag["latenz"])
            self.letzte.append(eintrag)

    def bericht(self):
        """Fasst zusammen, was der Dauerlauf ergeben hat."""
        if not self.latenzen:
            print("Keine Latenzen gemessen.")
            return
        import statistics
        n = max(1, len(self.latenzen) // 10)
        anfang = statistics.median(self.latenzen[:n])
        ende = statistics.median(self.latenzen[-n:])
        print("\n" + "=" * 58)
        print(f"{len(self.latenzen)} Segmente")
        print(f"  Latenz Median   {statistics.median(self.latenzen):6.1f}s")
        print(f"  Latenz p90      {sorted(self.latenzen)[int(len(self.latenzen)*0.9)]:6.1f}s")
        print(f"  Latenz maximal  {max(self.latenzen):6.1f}s")
        print(f"  Anfang          {anfang:6.1f}s")
        print(f"  Ende            {ende:6.1f}s")
        print(f"  Drift           {ende-anfang:+6.1f}s")
        if abs(ende - anfang) > 60 or statistics.median(self.latenzen) < 0:
            print("\n  Werte unplausibel. Bei beschleunigter Wiedergabe "
                  "(--tempo) ist die\n  Latenzmessung nicht aussagekraeftig, "
                  "dafuer braucht es Echtzeit.")
        elif ende - anfang > 5:
            print("\n  Laeuft davon. Uebersetzung muss schneller werden, "
                  "oder feiner\n  geschnitten, oder die Wiedergabe staerker "
                  "beschleunigt.")
        elif ende - anfang > 2:
            print("\n  Leichter Anstieg. Ueber eine laengere Predigt "
                  "beobachten.")
        else:
            print("\n  Stabil.")
        print("=" * 58)

    # ---- Senden ----
    async def _senden(self, ws, daten):
        try:
            await ws.send_text(json.dumps(daten, ensure_ascii=False))
            return True
        except Exception:
            return False

    async def _streuen(self, sprache, daten):
        tot = []
        for ws in list(self.hoerer[sprache]):
            if not await self._senden(ws, daten):
                tot.append(ws)
        for ws in tot:
            self.hoerer[sprache].discard(ws)

    async def _streuen_alle(self, daten):
        for sp in SPRACHEN:
            await self._streuen(sp, daten)


# ================================================================
# Mikrofon
# ================================================================

def stimmen_finden():
    """Sucht im Ordner voices die Stimmen zu den eingestellten Sprachen.

    Anders als frueher nicht auf vier feste Sprachen begrenzt: welche
    gebraucht werden, steht in der Konfiguration. Wofuer keine Stimme da
    ist, laeuft als reiner Untertitel weiter, statt den Start zu
    verhindern."""
    ordner = config.BASIS / "voices"
    treffer = {}
    for sprache in SPRACHEN:
        if sprache == QUELLE:
            continue          # Originalton, keine Stimme noetig
        pfad = config.STIMMEN.get(sprache)
        if not pfad:
            continue
        name = pfad.split("/")[-1]
        if (ordner / f"{name}.onnx").exists() and \
                (ordner / f"{name}.onnx.json").exists():
            treffer[sprache] = ordner / f"{name}.onnx"
    return treffer


def auf_16k(block, rate):
    """Rechnet einen Audioblock auf 16000 Hz herunter.

    Zwei Schritte, beide noetig. Erst ein gleitender Mittelwert als Tiefpass,
    sonst wird alles oberhalb von 8 kHz zurueckgefaltet und landet als
    tieferes Rauschen im Signal. Dann die eigentliche Ratenaenderung: bei
    ganzzahligen Verhaeltnissen wie 48000 exakt, sonst linear interpoliert.
    44100 ist kein Vielfaches von 16000, deshalb reicht Dezimieren dort
    nicht."""
    if rate == MIKRO_RATE:
        return block
    faktor = rate / MIKRO_RATE
    ganz = int(faktor)
    if ganz > 1:
        rest = len(block) % ganz
        gefiltert = (block[:-rest] if rest else block).reshape(-1, ganz).mean(axis=1)
    else:
        gefiltert = block
    if abs(faktor - ganz) < 1e-9:
        return gefiltert
    ziel = int(round(len(block) / faktor))
    return np.interp(np.linspace(0, len(gefiltert) - 1, ziel),
                     np.arange(len(gefiltert)), gefiltert).astype(np.float32)


def mikrofon_thread(lauf, geraet, segmentierer, stoppen, rate, blockgroesse):
    import sounddevice as sd

    def rueckruf(daten, rahmen, zeit, status):
        if status:
            print(f"  Audio: {status}")
        # Erster Kanal genuegt; ein Grossmembranmikrofon liefert ohnehin mono.
        block = auf_16k(daten[:, 0].copy(), rate)
        lauf.mitschnitt.schreiben(block)
        segment = segmentierer.schub(block)
        if segment is not None and lauf.laeuft:
            lauf.warteschlange.put((segment, None))

    try:
        with sd.InputStream(device=geraet, channels=1, samplerate=rate,
                            blocksize=blockgroesse, dtype="float32",
                            callback=rueckruf):
            print(f"Mikrofon offen: {rate} Hz -> {MIKRO_RATE} Hz.")
            while not stoppen.is_set():
                time.sleep(0.2)
    except Exception as e:
        print("\n" + "=" * 62)
        print("MIKROFON LAESST SICH NICHT OEFFNEN")
        print(f"  {str(e)[:200]}")
        print()
        if "WDM-KS" in str(e) or "-9999" in str(e):
            print("  Das ist ein WDM-KS-Geraet. Diese Schnittstelle greift")
            print("  exklusiv auf den Treiber zu und scheitert haeufig, wenn")
            print("  Windows das Mikrofon noch belegt. Nimm stattdessen einen")
            print("  MME- oder WASAPI-Eintrag desselben Mikrofons.")
        print("  Verfuegbare Geraete mit Schnittstelle: server.py --geraete")
        print("=" * 62 + "\n")
        stoppen.set()


def datei_thread(lauf, pfad, segmentierer, stoppen, tempo=1.0):
    """Speist eine Aufnahme ein, als kaeme sie aus dem Mikrofon.

    Fuer den Dauerlauf ist das der ehrlichere Test als Vorlesen: dieselbe
    Predigt, reproduzierbar, ohne dass jemand eine halbe Stunde reden muss.
    Und weil die Sprechposition in der Datei bekannt ist, laesst sich die
    echte Latenz messen statt nur die Rechenzeit.

    Eingespeist wird im Echtzeittakt. Schneller einzuspeisen wuerde die
    Warteschlange fluten und genau den Drift verdecken, um den es geht.
    Die Taktung laeuft ueber eine absolute Zeitbasis, weil sich der Fehler
    von time.sleep sonst ueber eine halbe Stunde aufsummiert."""
    from faster_whisper.audio import decode_audio
    print(f"Lade {Path(pfad).name} ...")
    audio = np.asarray(decode_audio(str(pfad), sampling_rate=MIKRO_RATE),
                       dtype=np.float32)
    dauer = len(audio) / MIKRO_RATE
    print(f"{dauer/60:.1f} Minuten Ton, Wiedergabe {tempo}x. "
          f"Der Lauf dauert etwa {dauer/60/tempo:.0f} Minuten.")
    if tempo != 1.0:
        print("ACHTUNG: nicht in Echtzeit. Die Latenzwerte sind dann nicht "
              "auf den Livebetrieb uebertragbar.")

    beginn = time.perf_counter()
    lauf.datei_beginn = beginn
    lauf.datei_tempo = tempo
    i = 0
    while i + BLOCK <= len(audio) and not stoppen.is_set():
        block = audio[i:i + BLOCK]
        i += BLOCK
        segment = segmentierer.schub(block)
        if segment is not None and lauf.laeuft:
            lauf.warteschlange.put((segment, i / MIKRO_RATE))
        soll = beginn + (i / MIKRO_RATE) / tempo
        warte = soll - time.perf_counter()
        if warte > 0:
            time.sleep(warte)

    print(f"\nDatei zu Ende nach {(time.perf_counter()-beginn)/60:.1f} Minuten.")
    lauf.bericht()


def rate_waehlen(geraet, wunsch=None):
    """Sucht eine Aufnahmerate, die das Geraet wirklich kann.

    Kein handelsuebliches USB-Mikrofon laeuft nativ auf 16000 Hz. 48000 wird
    bevorzugt, weil es genau das Dreifache ist und sich exakt dezimieren
    laesst. 44100 geht auch, kostet aber eine Interpolation."""
    import sounddevice as sd
    kandidaten = [wunsch] if wunsch else [48000, 32000, 16000, 44100]
    for rate in kandidaten:
        try:
            sd.check_input_settings(device=geraet, channels=1,
                                    samplerate=rate, dtype="float32")
            return rate, int(round(BLOCK * rate / MIKRO_RATE))
        except Exception:
            continue
    raise SystemExit(
        "Keine der ueblichen Aufnahmeraten funktioniert mit diesem Geraet.\n"
        "Anderes Geraet waehlen (--geraete) oder Rate erzwingen (--rate).")


def geraete_zeigen():
    """Listet Eingabegeraete MIT Schnittstelle.

    Windows meldet dasselbe Mikrofon mehrfach, einmal je Schnittstelle. Die
    Unterschiede sind erheblich: WDM-KS greift exklusiv zu und scheitert oft,
    MME ist am vertraeglichsten, WASAPI hat die geringste Latenz. Ohne diese
    Spalte waehlt man blind."""
    import sounddevice as sd
    apis = {i: a["name"] for i, a in enumerate(sd.query_hostapis())}
    rang = {"MME": 0, "Windows WASAPI": 1, "Windows DirectSound": 2,
            "Windows WDM-KS": 9}
    zeilen = []
    for i, g in enumerate(sd.query_devices()):
        if g["max_input_channels"] > 0:
            api = apis.get(g["hostapi"], "?")
            zeilen.append((rang.get(api, 5), i, g["name"], api,
                           g["max_input_channels"],
                           int(g["default_samplerate"])))
    print("Eingabegeraete, empfohlene zuerst:\n")
    print(f"  {'Nr':>3}  {'Schnittstelle':20} {'Hz':>6}  Name")
    for r, i, name, api, kan, hz in sorted(zeilen):
        marke = "  " if r < 5 else " !"
        print(f"{marke}{i:3}  {api:20} {hz:6}  {name}")
    print("\n  ! = WDM-KS, greift exklusiv zu und scheitert haeufig.")
    print("  Starten mit: python server.py --geraet <Nummer>")


# ================================================================
# Web
# ================================================================

def app_bauen(lauf, basis, port=8000):
    a_port = [port]
    from fastapi import (FastAPI, File, Form, Request, UploadFile, WebSocket,
                         WebSocketDisconnect)
    from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                                   PlainTextResponse, Response)
    from html import escape as html_escape

    @asynccontextmanager
    async def lebenszyklus(app):
        aufgabe = asyncio.create_task(lauf.verarbeiten())
        yield
        aufgabe.cancel()

    app = FastAPI(title="Devarenu v0.1", lifespan=lebenszyklus)
    client = basis / "client.html"

    @app.get("/")
    def wurzel():
        if not client.exists():
            return HTMLResponse(f"<h1>client.html fehlt</h1><p>{client}</p>",
                                status_code=500)
        return FileResponse(client, media_type="text/html; charset=utf-8")

    @app.get("/spende.svg")
    def spende_qr():
        """Bank-QR nach europaeischer Norm, den jede Banking-App liest.

        Der Betrag ist Vorgabe und in der App aenderbar; ohne Betrag
        laesst die Norm keinen Datensatz zu."""
        spende = getattr(config, "SPENDE", {}) or {}
        if not spende.get("iban"):
            return Response(status_code=404)
        try:
            import segno
            # Der Datensatz von Hand, weil die Hilfsfunktion von segno
            # einen Betrag erzwingt. Die Norm laesst ihn frei, sodass hier
            # beides moeglich ist: mit Vorgabe, wenn ein Betrag in der
            # Konfiguration steht, sonst ohne.
            betrag = spende.get("betrag")
            zeilen = [
                "BCD", "002", "1", "SCT",
                (spende.get("bic") or "").replace(" ", ""),
                spende.get("name", "")[:70],
                spende["iban"].replace(" ", ""),
                f"EUR{float(betrag):.2f}" if betrag else "",
                "", "",                  # Zweckschluessel, Referenz
                spende.get("zweck", "")[:140],
            ]
            while zeilen and not zeilen[-1]:
                zeilen.pop()
            code = segno.make("\n".join(zeilen), error="m")
            puffer = io.BytesIO()
            code.save(puffer, kind="svg", scale=6, border=2,
                      dark="#141f52", light=None)
            return Response(puffer.getvalue(), media_type="image/svg+xml")
        except Exception as e:
            print(f"Spenden-QR nicht erzeugt: {str(e)[:100]}")
            return Response(status_code=404)

    @app.get("/favicon.ico")
    def favicon():
        # Sonst steht in jeder Browserkonsole ein 404. Das Logo tut es.
        d = basis / "logo.png"
        if d.exists():
            return FileResponse(d, media_type="image/png")
        return Response(status_code=404)

    @app.get("/logo.png")
    def logo():
        d = basis / "logo.png"
        if d.exists():
            return FileResponse(d, media_type="image/png")
        # Ohne Logo laeuft alles weiter; die Seiten blenden die Marke dann
        # selbst aus, statt ein kaputtes Bild zu zeigen.
        return Response(status_code=404)

    @app.get("/ton/{sprache}/{nummer}")
    def ton(sprache: str, nummer: int):
        datei = lauf.toene.get((sprache, nummer))
        if not datei or not Path(datei).exists():
            return JSONResponse({"fehler": "kein Ton"}, status_code=404)
        return FileResponse(datei, media_type="audio/wav",
                            headers={"Cache-Control": "no-store"})

    @app.websocket("/strom")
    async def strom(ws: WebSocket):
        sprache = ws.query_params.get("sprache", "")
        if sprache not in lauf.sprachen:
            await ws.close(code=1008)
            return
        await ws.accept()
        await lauf.anmelden(ws, sprache)
        try:
            while True:
                await ws.receive_text()
        except (WebSocketDisconnect, Exception):
            pass
        finally:
            lauf.abmelden(ws, sprache)

    @app.websocket("/audio")
    async def audio(ws: WebSocket):
        """Nimmt Ton von einem entfernten Rechner entgegen.

        Damit kann der Ton in der Gemeinde aufgenommen und hier verarbeitet
        werden. Erwartet 16 kHz Mono als 16-Bit-Ganzzahlen, umgerechnet
        wird schon auf der Gegenseite: ueber die Leitung soll nicht das
        Dreifache gehen.

        Der Schluessel ist kein ernsthafter Schutz, sondern verhindert,
        dass jemand mit der Tunneladresse versehentlich oder mutwillig Ton
        einspeist und die Karte auslastet."""
        if ws.query_params.get("schluessel") != lauf.audio_schluessel:
            await ws.close(code=1008)
            return
        await ws.accept()
        lauf.audio_quelle = time.time()
        print("Audioquelle verbunden.")
        empfangen = 0
        try:
            while True:
                roh = await ws.receive_bytes()
                lauf.audio_quelle = time.time()
                empfangen += 1
                block = (np.frombuffer(roh, dtype=np.int16)
                         .astype(np.float32) / 32768.0)
                lauf.mitschnitt.schreiben(block)
                segment = lauf.segmentierer.schub(block)
                if segment is not None and lauf.laeuft:
                    lauf.warteschlange.put((segment, None))
        except Exception:
            pass
        finally:
            lauf.audio_quelle = None
            print(f"Audioquelle getrennt nach {empfangen} Bloecken.")

    @app.get("/api/sprachen")
    def sprachen():
        """Welche Sprachen dieser Server anbietet.

        Der Client baut seine Auswahl daraus, statt eine feste Liste zu
        haben. Damit genuegt ein Eintrag in der Konfiguration, um eine
        Sprache zu ergaenzen, und niemand muss die Seite anfassen."""
        vorhanden = getattr(lauf.werk, "stimmen", {})
        spende = getattr(config, "SPENDE", {}) or {}
        return {
            "rueckmeldung": getattr(config, "RUECKMELDUNG_MAIL", ""),
            "spende": ({"name": spende.get("name", ""),
                        "iban": spende.get("iban", ""),
                        "bic": spende.get("bic", ""),
                        "bank": spende.get("bank", ""),
                        "zweck": spende.get("zweck", "")}
                       if spende.get("iban") else None),
            "quelle": lauf.quelle,
            "ziele": lauf.ziele,
            # Was gerade laeuft, fuer die Zuhoererseite.
            "liste": [{
                "code": sp,
                "name": config.SPRACHNAMEN.get(sp, sp),
                "original": sp == lauf.quelle,
                "ton": sp == lauf.quelle or sp in vorhanden,
                # Geprueft heisst: ein Muttersprachler hat das
                # Fachwortverzeichnis durchgesehen.
                "geprueft": sp in getattr(config, "GEPRUEFT", set()),
            } for sp in lauf.sprachen],
            # Was zur Auswahl steht, fuer das Pult. Sprachen ohne Stimme
            # sind nicht ausgeschlossen: sie laufen als reiner Untertitel.
            "moeglich": [{
                "code": sp,
                "name": name,
                "stimme": sp in vorhanden or sp == lauf.quelle,
                "geprueft": sp in getattr(config, "GEPRUEFT", set()),
            } for sp, name in sorted(config.SPRACHNAMEN.items(),
                                     key=lambda x: x[1])],
        }

    @app.post("/api/sprachwahl")
    async def sprachwahl(daten: dict):
        """Stellt Quell- und Zielsprachen um.

        Alle Stimmen und Glossareintraege liegen auf der Platte; hier wird
        nur ausgewaehlt, was tatsaechlich mitlaeuft. Damit bleibt die
        Rechenzeit dort, wo eine Gemeinde sie braucht, und dasselbe Geraet
        bedient je nach Einstellung einen deutschen oder einen
        anderssprachigen Gottesdienst."""
        entfallen = lauf.sprachen_setzen(daten.get("quelle"),
                                         daten.get("ziele"))
        for sp in entfallen:
            for ws in list(lauf.hoerer.get(sp, ())):
                try:
                    await ws.close(code=1000)
                except Exception:
                    pass
            lauf.hoerer.pop(sp, None)
        print(f"Sprachen: {lauf.quelle} -> {', '.join(lauf.ziele)}")
        return {"quelle": lauf.quelle, "ziele": lauf.ziele,
                "getrennt": sorted(entfallen)}

    @app.post("/api/nachricht")
    async def nachricht(daten: dict):
        text = (daten.get("text") or "").strip()
        if not text:
            return JSONResponse({"fehler": "leer"}, status_code=400)
        # Kurz halten: das Feld ist fuer einen Satz gedacht, nicht fuer
        # einen Brief, und alles landet ungefiltert vor dem Techniker.
        eintrag = {"text": text[:200],
                   "sprache": (daten.get("sprache") or "")[:5],
                   "zeit": time.strftime("%H:%M")}
        lauf.nachrichten.append(eintrag)
        print(f"Nachricht aus dem Saal ({eintrag['sprache'] or '?'}): "
              f"{eintrag['text']}")
        return {"angekommen": True}

    @app.post("/api/nachrichten/leeren")
    async def nachrichten_leeren():
        lauf.nachrichten.clear()
        return {"anzahl": 0}

    @app.get("/api/zustand")
    def zustand():
        return {"live": lauf.laeuft, "gesendet": lauf.n, "hoerer": lauf.anzahl,
                "gesamt": sum(lauf.anzahl.values()),
                "laeuft_seit": round(time.time() - lauf.begonnen, 1)
                if lauf.begonnen else 0,
                "prompt": lauf.werk.stt_prompt,
                "stellen": lauf.werk.kontext_stellen,
                "namen": lauf.werk.kontext_namen,
                "skript": lauf.werk.skript_info,
                "audio_quelle": (round(time.time() - lauf.audio_quelle, 1)
                                 if lauf.audio_quelle else None),
                "mitschnitt": lauf.mitschnitt.lage(),
                "nachrichten": list(lauf.nachrichten),
                "letzte": list(lauf.letzte)[-8:]}

    @app.post("/api/steuerung/{was}")
    async def steuerung(was: str):
        if was == "start":
            await lauf.starten()
        elif was == "pause":
            await lauf.anhalten()
        elif was == "reset":
            await lauf.zuruecksetzen()
        else:
            return JSONResponse({"fehler": "unbekannt"}, status_code=400)
        return {"live": lauf.laeuft, "gesendet": lauf.n}

    @app.get("/api/pegel")
    def pegel():
        """Wird vom Pult mehrmals je Sekunde abgefragt, deshalb bewusst
        schlank gehalten."""
        seg = lauf.segmentierer
        lage = seg.lage()
        return {"lage": lage["stufe"], "lage_text": lage["text"],
                "einmessen": seg.einmessen_lage(),
                "jetzt": round(seg.pegel_jetzt, 5),
                "spitze": round(seg.pegel_spitze, 5),
                "grund": round(seg.grundpegel, 5),
                "schwelle": round(seg.schwelle, 5),
                "fest": seg.feste_schwelle is not None,
                "knapp": sum(1 for t in seg.zu_leise
                             if time.time() - t < 30),
                "spricht": seg.spricht,
                "verworfen": seg.verworfen}

    @app.post("/api/einmessen")
    async def einmessen(daten: dict):
        """Startet oder beendet das Einmessen der Mindestlautstaerke."""
        seg = lauf.segmentierer
        if daten.get("beenden"):
            erg = seg.einmessen_auswerten()
            if erg:
                print(f"Eingemessen: {erg['text']}")
            return erg or {"erfolg": False,
                           "text": "Zu wenig gemessen. Länger sprechen lassen."}
        seg.einmessen_starten(float(daten.get("dauer", 12)))
        return {"gestartet": True, "dauer": float(daten.get("dauer", 12))}

    @app.post("/api/schwelle")
    async def schwelle(daten: dict):
        """Setzt die Mindestlautstaerke oder gibt sie wieder frei.

        Im Gottesdienst wird sie einmal vor Beginn festgenagelt: Prediger
        sprechen lassen, Wert knapp unter dessen Pegel setzen, fertig. Alles
        Leisere wird dann gar nicht erst zu einem Segment."""
        seg = lauf.segmentierer
        if daten.get("automatisch"):
            seg.feste_schwelle = None
        else:
            wert = float(daten.get("wert", 0))
            seg.feste_schwelle = max(0.0005, min(0.5, wert))
        return {"schwelle": round(seg.schwelle, 5),
                "fest": seg.feste_schwelle is not None}

    @app.post("/api/mitschnitt")
    async def mitschnitt(daten: dict):
        if daten.get("beenden"):
            return lauf.mitschnitt.beenden() or {"lief": False}
        datei = lauf.mitschnitt.starten()
        return {"datei": Path(datei).name}

    @app.get("/mitschnitt/{name}")
    def mitschnitt_holen(name: str):
        # Nur Dateinamen ohne Pfadanteile: sonst liesse sich ueber die
        # Adresse jede Datei des Rechners abrufen.
        datei = lauf.mitschnitt.ordner / Path(name).name
        if not datei.exists():
            return JSONResponse({"fehler": "nicht gefunden"}, status_code=404)
        return FileResponse(datei, media_type="audio/wav", filename=datei.name)

    @app.post("/api/kontext")
    async def kontext(daten: dict):
        """Nimmt Thema und Bibelstellen vom Pult und baut daraus den Prompt.

        Der Techniker fragt den Prediger vor dem Gottesdienst und tippt zwei
        Zeilen ein. Daraus werden die Kapitel gelesen und die Namen gezogen,
        die dort vorkommen, seltene zuerst. Der erste Nachtlauf hat gezeigt,
        warum das noetig ist: ein fester Prompt mit Lehrbegriffen brachte
        nichts, weil Whisper sich nicht an Begriffen verhoert, sondern an
        Eigennamen."""
        from bibelstellen import aus_pulttext
        text = (daten.get("text") or "").strip()
        erg = aus_pulttext(text, lauf.werk.namen, config.PROMPT_EINLEITUNG,
                           config.PROMPT_MAX_ZEICHEN,
                           zusatznamen=lauf.werk.skript_namen)
        lauf.werk.stt_prompt = erg["prompt"]
        lauf.werk.kontext_stellen = erg["stellen"]
        lauf.werk.kontext_namen = erg["namen"]
        print(f"Prompt gesetzt: {len(erg['stellen'])} Stellen, "
              f"{len(erg['namen'])} von {erg['namen_gefunden']} Namen")
        return {"prompt": erg["prompt"], "stellen": erg["stellen"],
                "namen": erg["namen"], "gefunden": erg["namen_gefunden"]}

    @app.post("/api/skript")
    async def skript(datei: UploadFile = File(None), text: str = Form("")):
        """Nimmt ein Predigtmanuskript und zieht die Namen daraus.

        Der Text wird ausdruecklich NICHT ausgeliefert. Prediger weichen ab,
        kuerzen, schweifen aus; wer das Manuskript vorliest, merkt das nicht
        und uebersetzt am Ende etwas, das nie gesagt wurde. Gesprochen wird,
        was gesprochen wird.

        Gezogen werden nur die Namen, und die sind das eigentliche Problem:
        ein Manuskript liefert genau die, die in keiner Bibelstelle stehen.
        Ein Ortsname aus einer Anekdote, ein zitierter Autor, ein
        hebraeischer Ausdruck."""
        from skript_lesen import auswerten, text_aus_datei
        if datei is not None and datei.filename:
            roh = await datei.read()
            inhalt = text_aus_datei(datei.filename, io.BytesIO(roh))
            quelle = datei.filename
        else:
            inhalt = text
            quelle = "eingefuegter Text"
        if not inhalt.strip():
            return JSONResponse({"fehler": "leer"}, status_code=400)

        erg = auswerten(inhalt, lauf.werk.namen)
        lauf.werk.skript_namen = erg["namen"]
        lauf.werk.skript_info = {
            "quelle": quelle, "woerter": erg["woerter"],
            "stellen": erg["stellen"], "namen": erg["namen"]}
        print(f"Manuskript: {quelle}, {erg['woerter']} Woerter, "
              f"{len(erg['namen'])} Namen, Stellen: "
              f"{', '.join(erg['stellen']) or 'keine'}")

        # Falls im Manuskript Stellen stehen und das Kontextfeld leer war,
        # gleich den Prompt setzen. Ein Handgriff weniger am Pult.
        if erg["stellen"] and not lauf.werk.kontext_stellen:
            from bibelstellen import aus_pulttext
            neu = aus_pulttext(" ".join(erg["stellen"]), lauf.werk.namen,
                               config.PROMPT_EINLEITUNG,
                               config.PROMPT_MAX_ZEICHEN,
                               zusatznamen=erg["namen"])
            lauf.werk.stt_prompt = neu["prompt"]
            lauf.werk.kontext_stellen = neu["stellen"]
            lauf.werk.kontext_namen = neu["namen"]
        return {"quelle": quelle, "woerter": erg["woerter"],
                "stellen": erg["stellen"], "namen": erg["namen"],
                "bekannt": erg["sicher"], "neu": erg["unsicher"],
                "prompt": lauf.werk.stt_prompt}

    @app.get("/qr")
    def qr(request: Request, ssid: str = "", passwort: str = "",
           adresse: str = ""):
        """Projektionsseite mit zwei QR-Codes.

        Zwei Schritte, weil sie zwei verschiedene Dinge tun: der erste
        verbindet das Handy mit dem WLAN, der zweite oeffnet die Seite.
        Beide Codes lassen sich mit der Kamera scannen, es muss nichts
        getippt werden.

        Ausgelegt fuer den Beamer: heller Grund, sehr grosse Codes,
        wenig Text. Aus fuenfzehn Metern muss der Code noch scharf genug
        sein, deshalb bekommt er den groessten Teil der Flaeche."""
        import segno
        ssid = ssid or lauf.wlan.get("ssid", "")
        passwort = passwort or lauf.wlan.get("passwort", "")

        # Die Adresse kommt aus dem Aufruf selbst, nicht aus der eigenen
        # Netzkonfiguration. Wer die Seite ueber den Tunnel oeffnet, bekommt
        # die Tunneladresse in den Code, wer sie lokal oeffnet, die lokale.
        # Das ist immer die Adresse, unter der der Aufrufer den Server
        # tatsaechlich erreicht hat, und damit die einzige, die auch fuer
        # die Handys im Raum funktioniert.
        if not adresse:
            weiter = request.headers.get("x-forwarded-host")
            gastgeber = weiter or request.headers.get("host") or \
                f"{lokale_ip()}:{a_port[0]}"
            schema = (request.headers.get("x-forwarded-proto")
                      or ("https" if weiter else request.url.scheme))
            adresse = f"{schema}://{gastgeber}/"
        elif not adresse.startswith("http"):
            adresse = "https://" + adresse
        if not adresse.endswith("/"):
            adresse += "/"

        def bild(inhalt, groesse=14):
            code = segno.make(inhalt, error="m")
            return code.svg_data_uri(scale=groesse, border=2,
                                     dark="#141f52", light="#ffffff")

        seiten_qr = bild(adresse)
        if ssid:
            # Das Format fuer WLAN-Zugangsdaten, das Android und iOS seit
            # Jahren verstehen. Semikolon und Doppelpunkt im Passwort
            # muessen maskiert werden, sonst bricht der Datensatz.
            def maskieren(t):
                for z in ("\\", ";", ",", ":", '"'):
                    t = t.replace(z, "\\" + z)
                return t
            wlan_qr = bild(f"WIFI:T:WPA;S:{maskieren(ssid)};"
                           f"P:{maskieren(passwort)};;")
        else:
            wlan_qr = None

        return HTMLResponse(QR_SEITE.format(
            wlan_block=(f'<div class=schritt><span class=nr>1</span>'
                        f'<p class=was>Mit dem WLAN verbinden</p>'
                        f'<img src="{wlan_qr}" alt="WLAN">'
                        f'<p class=klein>{html_escape(ssid)}<br>'
                        f'{html_escape(passwort)}</p></div>')
            if wlan_qr else "",
            nr_seite="2" if wlan_qr else "1",
            seiten_qr=seiten_qr, adresse=adresse))

    @app.get("/api/wlan")
    def wlan_lesen():
        return lauf.wlan

    @app.post("/api/wlan")
    async def wlan(daten: dict):
        lauf.wlan = {"ssid": (daten.get("ssid") or "").strip(),
                     "passwort": (daten.get("passwort") or "").strip()}
        return lauf.wlan

    @app.get("/pult")
    def pult():
        return HTMLResponse((basis / "pult.html").read_text(encoding="utf-8")
                            if (basis / "pult.html").exists() else PULT)

    return app


QR_SEITE = """<!doctype html><html lang=de><meta charset=utf-8>
<title>Übersetzung</title>
<style>
 /* Fuer den Beamer gebaut: heller Grund, kaum Text, die Codes bekommen
    fast die ganze Flaeche. Aus fuenfzehn Metern zaehlt nur die Groesse
    des Codes, alles andere ist Beiwerk. */
 *{{box-sizing:border-box;margin:0}}
 body{{font:16px/1.4 Georgia,serif;color:#141f52;background:#fff;
      height:100vh;display:flex;flex-direction:column;
      align-items:center;justify-content:center;padding:2vh 2vw;gap:2vh}}
 h1{{font-size:clamp(1.4rem,3.4vh,2.6rem);font-weight:400;
    letter-spacing:.1em;text-transform:uppercase}}
 .logo{{height:6vh;width:auto;opacity:.9}}
 .streifen{{height:.5vh;width:38vw;
   background:linear-gradient(90deg,#3b1e73,#1c3a8f 52%,#1fa5d8)}}
 .reihe{{display:flex;gap:5vw;align-items:flex-start;justify-content:center;
   flex:1;min-height:0}}
 .schritt{{display:flex;flex-direction:column;align-items:center;gap:1vh;
   min-height:0}}
 .nr{{display:grid;place-items:center;width:4.4vh;height:4.4vh;
   border-radius:50%;background:#141f52;color:#fff;
   font-size:2.2vh;font-family:system-ui,sans-serif}}
 .was{{font-size:clamp(.9rem,2.4vh,1.5rem)}}
 img{{height:min(58vh,42vw);width:auto;image-rendering:pixelated}}
 .klein{{font:1.9vh/1.5 ui-monospace,monospace;color:#6b7385;
   text-align:center;word-break:break-all;max-width:34vw}}
 .fuss{{font:1.9vh system-ui,sans-serif;color:#6b7385;text-align:center}}
</style>
<img class=logo src="/logo.png" alt="" onerror="this.remove()">
<h1>Übersetzung</h1>
<div class=streifen></div>
<div class=reihe>
{wlan_block}
<div class=schritt>
  <span class=nr>{nr_seite}</span>
  <p class=was>Seite öffnen</p>
  <img src="{seiten_qr}" alt="Seite">
  <p class=klein>{adresse}</p>
</div>
</div>
<p class=fuss>Mit der Kamera scannen · Sprache auswählen · Kopfhörer empfohlen</p>
</html>"""


PULT = """<!doctype html><html lang=de><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Pult</title>
<style>
 body{font:16px/1.6 Georgia,serif;margin:0;background:#f3f4f6;color:#141f52;
      display:grid;place-items:start center;min-height:100vh;padding:2rem 1rem}
 .k{background:#fff;border:1px solid #d9dce4;padding:1.8rem;width:min(92vw,34rem)}
 h1{font-size:1.3rem;font-weight:400;letter-spacing:.06em;margin:0 0 1.2rem}
 /* Faellt still weg, wenn kein Logo im Ordner liegt: eine kaputte
    Bildmarke sieht schlimmer aus als gar keine.
    Hiess frueher .marke wie die rote Schwellenmarke des Pegelbalkens.
    Das Logo bekam dadurch deren Aussehen und wurde zu einem roten
    Strich in der Ecke. */
 .logo{height:2.1rem;width:auto;display:block;margin:0 0 .7rem;opacity:.9}
 .lage{display:flex;align-items:center;gap:.6rem;margin:0 0 1.2rem;
       font:.85rem/1.4 system-ui,sans-serif;color:#6b7385}
 .punkt{width:9px;height:9px;border-radius:50%;background:#d9dce4}
 .punkt.an{background:#1fa5d8}
 button{font:1rem Georgia,serif;letter-spacing:.06em;padding:.9rem;border:0;
        cursor:pointer;color:#fff;width:100%;margin-bottom:.5rem}
 /* Meldungen aus dem Saal duerfen nicht untergehen: sie kommen selten,
    und wenn, dann meist waehrend etwas laeuft. Deshalb ueber dem
    Hauptknopf und mit einer kleinen Bewegung, die aufhoert, sobald man
    hinsieht. */
 .briefkasten{background:#1fa5d8;display:flex;align-items:center;
   justify-content:center;gap:.6rem;font-size:1rem}
 /* Ohne das gewinnt display:flex gegen das hidden-Attribut, und der
    Briefkasten stand mit einer Null darin da. */
 [hidden]{display:none !important}
 .briefkasten .umschlag{font-size:1.3rem;display:inline-block}
 /* Ein kleines Zeichen, das wackelt, sieht im Betrieb niemand. Auffallen
    muss die ganze Flaeche, sonst bleibt die Meldung liegen. */
 @media (prefers-reduced-motion: no-preference){
   .briefkasten{animation:pochen 1.8s ease-in-out infinite}
   .briefkasten .umschlag{animation:wackeln 1.8s ease-in-out infinite}
 }
 @keyframes pochen{0%,100%{background:#1fa5d8}
   50%{background:#0d7fab;box-shadow:0 0 0 3px rgba(31,165,216,.35)}}
 @keyframes wackeln{0%,70%,100%{transform:rotate(0)}
   78%{transform:rotate(-14deg)}86%{transform:rotate(12deg)}
   93%{transform:rotate(-6deg)}}
 #postzahl{background:#fff;color:#1c3a8f;border-radius:999px;
   min-width:1.4rem;padding:.05rem .35rem;font:600 .85rem system-ui,sans-serif}
 .start{background:linear-gradient(100deg,#3b1e73,#1c3a8f 52%,#1fa5d8)}
 .pause{background:#141f52}
 button:disabled{opacity:.4;cursor:default}
 /* Gleiche Groesse wie die anderen, aber zurueckgenommen: es ist eine
    Handlung wie die uebrigen, nur eine seltenere. Als blosser Text sah
    sie verloren aus. */
 .reset{background:none;color:#6b7385;border:1px solid #d9dce4}
 .reset:hover{border-color:#9aa3b2;color:#141f52}
 /* Zuklappbar, weil dieser Teil vor dem Gottesdienst gebraucht wird und
    waehrenddessen nur Platz kostet. */
 h2.klapp{display:flex;justify-content:space-between;align-items:center;
   cursor:pointer;user-select:none}
 h2.klapp:hover{color:#1c3a8f}
 /* Wort statt bloss eines Pfeils: ein Dreieck allein sagt nicht, was
    passiert, wenn man darauf drueckt. */
 .klapptext{display:inline-flex;align-items:center;gap:.35rem;
   font:.72rem system-ui,sans-serif;text-transform:none;letter-spacing:0;
   color:#8b93a3;font-weight:400}
 h2.klapp:hover .klapptext{color:#1c3a8f}
 .pfeil{font-size:.9rem;transition:transform .18s ease}
 .pfeil.zu{transform:rotate(-90deg)}
 h2{font:.8rem system-ui,sans-serif;text-transform:uppercase;
    letter-spacing:.1em;color:#6b7385;margin:1.8rem 0 .6rem;font-weight:600}
 /* Pegel: der Balken zeigt den Ist-Pegel, die Marke die Schwelle.
    Was links der Marke bleibt, wird nicht uebersetzt. */
 .balken{position:relative;height:26px;background:#eceef2;overflow:hidden}
 /* Drei Zustaende, die man ohne Zahlen unterscheiden kann:
    grau  = nur Raumgeraeusch, nichts geht verloren
    rot   = hoerbar, aber unter der Schwelle: genau das wird weggeworfen
    blau  = wird uebersetzt
    Der rote Bereich ist der einzige, bei dem der Techniker handeln muss,
    und er soll ihn sehen, ohne den Zahlenwert zu lesen. */
 .fuell{height:100%;width:0;background:#9aa3b2;
   transition:width .08s linear, background .2s ease}
 .fuell.knapp{background:linear-gradient(90deg,#a8737b,#c0392b)}
 .fuell.ueber{background:linear-gradient(90deg,#1c3a8f,#1fa5d8)}
 .marke{position:absolute;top:-3px;bottom:-3px;width:2px;background:#c0392b}
 .marke::after{content:"";position:absolute;top:-4px;left:-4px;
               border:5px solid transparent;border-top-color:#c0392b}
 /* Der Balken faellt nur auf, wenn etwas nicht stimmt. Im Normalbetrieb
    bleibt er unsichtbar, damit er nicht zur Tapete wird und im Ernstfall
    uebersehen wird. */
 /* Ueber das hidden-Attribut gesteuert, nicht ueber eine zweite Klasse:
    "warnung warnung" traf frueher versehentlich die Regel fuer die gelbe
    Stufe, und der Balken stand leer da. Was leer ist, wird versteckt. */
 .warnung{margin:1rem 0 0;padding:.7rem .9rem;
   font:.9rem/1.45 system-ui,sans-serif;border-left:4px solid;
   background:#fdf6e3;border-color:#c8991f;color:#7a5c12}
 .warnung.schwer{background:#fdeeec;border-color:#c0392b;color:#8c2f22}
 @keyframes puls{0%,100%{opacity:1}50%{opacity:.55}}
 @media (prefers-reduced-motion: no-preference){
   .warnung.alarm{animation:puls 1.6s ease-in-out infinite}
 }
 .werte{display:flex;justify-content:space-between;
        font:.75rem system-ui,sans-serif;color:#6b7385;margin:.35rem 0 .7rem;
        font-variant-numeric:tabular-nums}
 input[type=range]{width:100%;margin:.2rem 0 .5rem}
 select{width:100%;font:.9rem system-ui,sans-serif;padding:.5rem;
         border:1px solid #d9dce4;background:#fff;margin-bottom:.3rem}
 .zielliste{display:flex;flex-wrap:wrap;gap:.4rem;margin:.2rem 0 .3rem}
 .zielliste label{display:inline-flex;align-items:center;gap:.35rem;
   margin:0;padding:.35rem .6rem;border:1px solid #d9dce4;cursor:pointer;
   font:.85rem system-ui,sans-serif;color:#141f52}
 .zielliste label.an{background:#141f52;color:#fff;border-color:#141f52}
 .zielliste input{margin:0}
 .zielliste .ohneton{opacity:.75}
 /* Der ganze Block ist zurueckgenommen, nicht die einzelne Kachel: so
    sieht man auf einen Blick, wo die geprueften aufhoeren. */
 .zielliste.ungeprueft label{border-style:dashed;color:#6b7385}
 .zielliste.ungeprueft label.an{color:#fff;border-style:solid}
 .untertitel{margin:.5rem 0 .2rem;font-style:italic}
 /* Der Betrieb steht vorn, die Einrichtung dahinter. Was einmal je
    Gemeinde eingestellt wird, soll am Sonntag nicht im Weg stehen. */
 .kopfknoepfe{position:absolute;top:1.3rem;right:1.4rem;display:flex;gap:.4rem}
 .kopfknoepfe button{background:none;border:1px solid #d9dce4;color:#6b7385;
   width:auto;padding:.25rem .6rem;font:.75rem system-ui,sans-serif;
   letter-spacing:.06em;margin:0;line-height:1.4}
 #zahnrad{font-size:1rem;padding:.1rem .5rem}
 /* Der Weg zum Beamerbild soll nicht davon abhaengen, dass jemand eine
    Adresse im Kopf hat. Ein Knopf, ein neues Fenster, Vollbild. */
 #qrknopf{font-weight:600;letter-spacing:.1em}
 #zahnrad.an{background:#141f52;color:#fff;border-color:#141f52}
 #einrichtung>h2:first-of-type{margin-top:.6rem}
 .k{position:relative}
 input[type=text]{font:.9rem system-ui,sans-serif;padding:.5rem;
                  border:1px solid #d9dce4}
 a{color:#1c3a8f}
 input[type=file]{width:100%;font:.85rem system-ui,sans-serif;
                  padding:.5rem;border:1px dashed #d9dce4;background:#fbfcfd}
 .reihe{display:flex;gap:.5rem}
 .reihe button{margin:0}
 .klein{background:#141f52;font-size:.85rem;padding:.55rem}
 .aus{background:#eceef2;color:#6b7385}
 label{display:block;font:.85rem system-ui,sans-serif;color:#6b7385;
       margin:1.4rem 0 .3rem}
 textarea{width:100%;font:.9rem system-ui,sans-serif;padding:.6rem;
          border:1px solid #d9dce4;min-height:4.5rem;resize:vertical}
 table{width:100%;border-collapse:collapse;margin:1.2rem 0 0;
       font:.9rem system-ui,sans-serif}
 td{padding:.45rem 0;border-top:1px solid #d9dce4}
 td:last-child{text-align:right;font-variant-numeric:tabular-nums}
 /* Meldungen aus dem Saal stehen deutlicher da als der Verlauf: sie
    verlangen eine Entscheidung, der Verlauf nur einen Blick. */
 .post{font:.9rem/1.5 system-ui,sans-serif;margin:.2rem 0 .6rem}
 .post div{padding:.5rem .7rem;margin-bottom:.35rem;background:#eef4fb;
   border-left:3px solid #1fa5d8;color:#141f52}
 .post .wann{color:#6b7385;font-size:.78rem;margin-right:.4rem}
 .mit{font:.8rem/1.5 system-ui,sans-serif;color:#6b7385;margin:1rem 0 0;
      max-height:11rem;overflow:auto}
 .mit div{padding:.25rem 0;border-top:1px solid #eef0f4}
 .hin{font:.8rem/1.5 system-ui,sans-serif;color:#6b7385;margin:1.2rem 0 0}
</style>
<div class=k>
<div class=kopfknoepfe>
  <button id=qrknopf onclick=qrOeffnen() title="QR-Seite für den Beamer">
    QR</button>
  <button id=zahnrad onclick=einrichtungZeigen() title="Einrichtung">⚙</button>
  <button id=sprachknopf onclick=uiSprache()>EN</button>
</div>
<img class=logo src="/logo.png" alt="" onerror="this.remove()">
<h1 data-t=pult>Pult</h1>
<p class=lage><span class=punkt id=punkt></span><span id=lage>…</span></p>
<div id=betrieb>
<button class=briefkasten id=briefkasten onclick=postZeigen() hidden>
  <span class=umschlag>✉</span><span id=postzahl></span>
  <span data-t=post_neu>neue Meldungen aus dem Saal</span></button>
<button class=start id=bStart onclick=umschalten()>Übersetzung starten</button>
<p class=hin id=anhaltenHin data-t=anhalten_hin hidden>Anhalten stoppt die Auslieferung, ohne die
Zuhörer zu trennen. Sie bleiben verbunden und hören weiter, sobald es
weitergeht.</p>
<button class=reset onclick=s('reset')>Von vorn</button>
<p class=hin data-t=qr_hin>Mit <b>QR</b> oben rechts öffnet sich die Seite
für den Beamer. Dort scannen die Zuhörer sich selbst ein.</p>



<p class=warnung id=warnung hidden></p>
<h2 data-t=lautstaerke>Mindestlautstärke</h2>
<div class=balken>
  <div class=fuell id=fuell></div>
  <div class=marke id=marke style=left:0></div>
</div>
<div class=werte>
  <span id=pegelwert>–</span>
  <span id=schwellwert>–</span>
</div>
<input type=range id=regler min=0 max=100 value=30 oninput=schieben()>
<button class=klein id=bEinmessen onclick=einmessen()>Einmessen: Prediger
sprechen lassen</button>
<div class=reihe>
  <button class=klein id=bFest onclick=festnageln()>Regler festnageln</button>
  <button class="klein aus" id=bAuto onclick=automatisch()>Mitlaufend</button>
</div>
<p class=hin>Am einfachsten ist das Einmessen: draufdrücken, den Prediger
zwölf Sekunden normal sprechen lassen, fertig. Der Regler daneben ist für
Nachjustierung von Hand. Alles unterhalb der Marke wird gar nicht erst
übersetzt.</p>

<h2 class=klapp id=vorbereitungKopf onclick=vorbereitungKlappen()>
  <span data-t=vorbereitung>Vor dem Gottesdienst</span>
  <span class=klapptext><span id=vorbereitungWort>Zuklappen</span>
  <span class=pfeil id=vorbereitungPfeil>▾</span></span></h2>
<div id=vorbereitung>
<label for=kontext data-t=kontext>Thema und Bibelstellen</label>
<textarea id=kontext placeholder="Predigt über Vergebung. Texte: Matthäus 18, Psalm 32. Namen: Petrus, Nathan."></textarea>
<button class=klein onclick=k()>Übernehmen</button>
<p class=hin id=erkannt></p>

<label data-t=manuskript>Predigtmanuskript</label>
<p class=hin>Falls der Prediger eines hat. Es wird <b>nicht vorgelesen</b>,
sondern nur nach Namen durchsucht: Orte, Personen, Fremdwörter. Gesprochen
wird, was gesprochen wird.</p>
<input type=file id=datei accept=".txt,.md,.docx" onchange=hochladen()>
<p class=hin id=skriptinfo></p>



</div>

<h2 data-t=mitschnitt>Mitschnitt</h2>
<button class=klein id=bSchnitt onclick=schnitt()>Aufnahme starten</button>
<p class=hin id=schnittinfo>Nimmt den Ton mit, der ohnehin durchläuft. Ersetzt
die Aufnahme auf den USB-Stick, die am Mischpult nicht mehr geht, solange der
Rechner per USB angeschlossen ist.</p>



<h2 data-t=zuhoerer_ueber>Zuhörer je Sprache</h2>
<table><tbody id=zahlen></tbody></table>
<div class=mit id=mit></div>

</div>

<div id=post hidden>
<p class=hin data-t=post_hin>Antworten ist nicht vorgesehen. Wer etwas meldet, weiß das und erwartet keine Rückmeldung.</p>
  <h2 data-t=post_ueber>Aus dem Saal</h2>
  <div class=post id=postliste></div>
  <button class=klein onclick=postLeeren() data-t=post_weg>Erledigt</button>
</div>

<div id=einrichtung hidden>
<p class=hin data-t=einrichtung_hin>Einmal je Gemeinde einstellen, danach
bleibt es so.</p>
<h2 data-t=sprachen>Sprachen</h2>
<label for=quellwahl data-t=quelle>Gesprochene Sprache</label>
<select id=quellwahl onchange=sprachenSetzen()></select>
<label data-t=ziele>Übersetzt nach</label>
<div id=zielwahl></div>
<p class=hin data-t=sprachen_hin>Alle Sprachen liegen auf dem Rechner. Nur die
ausgewählten laufen mit, das spart Rechenzeit. Sprachen ohne Stimme
erscheinen als Untertitel.</p>

<h2 data-t=wlan>WLAN für die Zuhörer</h2>
<div class=reihe>
  <input type=text id=ssid placeholder="Netzname" style="flex:1"
         onchange=wlanSetzen()>
  <input type=text id=wpw placeholder="Passwort" style="flex:1"
         onchange=wlanSetzen()>
</div>
<p class=hin id=wlanstand></p>
<p class=hin data-t=wlan_hin>Netzname und Passwort des Routers, an dem
dieser Rechner hängt. Sie wandern in den ersten QR-Code, damit sich die
Handys mit einem Scan verbinden, ohne dass jemand ein Passwort abtippt.
Ohne Eintrag zeigt die QR-Seite nur den zweiten Code.</p>
<p class=hin><a href="/qr" target="_blank" data-t=qr_oeffnen>QR-Seite für den
Beamer öffnen</a></p>

</div>
</div>
<script>
// Beschriftungen. Nur Deutsch und Englisch, beide von Hand gepflegt: eine
// maschinell falsch uebersetzte Schaltflaeche ist aergerlicher als eine
// englische, die alle verstehen.
const TEXTE={
 de:{pult:"Pult",sprachen:"Sprachen",quelle:"Gesprochene Sprache",
   ziele:"Übersetzt nach",lautstaerke:"Mindestlautstärke",
   mitschnitt:"Mitschnitt",wlan:"WLAN für die Zuhörer",
   manuskript:"Predigtmanuskript",start:"Übersetzung starten",
   pause:"Übersetzung anhalten",reset:"Von vorn",uebernehmen:"Übernehmen",
   einmessen:"Einmessen: Prediger sprechen lassen",
   fest:"Regler festnageln",auto:"Mitlaufend",
   schnittstart:"Aufnahme starten",schnittstop:"Aufnahme beenden",
   laeuft:"läuft",pause_an:"angehalten",segmente:"Segmente",
   hoerer:"Zuhörer",tonda:"Ton kommt an",
   sprachen_hin:"Alle Sprachen liegen auf dem Rechner. Nur die ausgewählten "
     +"laufen mit, das spart Rechenzeit. Sprachen ohne Stimme erscheinen "
     +"als Untertitel.",
   ungeprueft_ueber:"Noch nicht von einem Muttersprachler geprüft. "
     +"Funktionieren, aber die Fachbegriffe stammen unbesehen aus der "
     +"Maschine.",
   einrichtung:"Einrichtung",
   einrichtung_hin:"Einmal je Gemeinde einstellen, danach bleibt es so.",
   wlan_hin:"Netzname und Passwort des Routers, an dem dieser Rechner hängt. "
     +"Sie wandern in den ersten QR-Code, damit sich die Handys mit einem "
     +"Scan verbinden, ohne dass jemand ein Passwort abtippt. Ohne Eintrag "
     +"zeigt die QR-Seite nur den zweiten Code.",
   qr_oeffnen:"QR-Seite für den Beamer öffnen",
   gespeichert:"Gespeichert.",
   qr_hin:"Mit QR oben rechts öffnet sich die Seite für den Beamer. "
     +"Dort scannen die Zuhörer sich selbst ein.",
   anhalten_hin:"Anhalten stoppt die Auslieferung, ohne die Zuhörer zu "
     +"trennen. Sie bleiben verbunden und hören weiter, sobald es "
     +"weitergeht.",
   zuhoerer_ueber:"Zuhörer je Sprache",
   vorbereitung:"Vor dem Gottesdienst",kontext:"Thema und Bibelstellen",
   zuklappen:"zuklappen",ausklappen:"ausklappen",
   post_ueber:"Aus dem Saal",post_weg:"Erledigt",
   post_neu:"neue Meldungen aus dem Saal",
   post_hin:"Antworten ist nicht vorgesehen. Wer etwas meldet, weiß das "
     +"und erwartet keine Rückmeldung."},
 en:{pult:"Control desk",sprachen:"Languages",quelle:"Spoken language",
   ziele:"Translated into",lautstaerke:"Minimum volume",
   mitschnitt:"Recording",wlan:"Wi-Fi for listeners",
   manuskript:"Sermon manuscript",start:"Start translation",
   pause:"Pause translation",reset:"Start over",uebernehmen:"Apply",
   einmessen:"Calibrate: let the preacher speak",
   fest:"Lock the slider",auto:"Follow the room",
   schnittstart:"Start recording",schnittstop:"Stop recording",
   laeuft:"running",pause_an:"paused",segmente:"segments",
   hoerer:"listeners",tonda:"audio arriving",
   sprachen_hin:"All languages are stored on the computer. Only the selected "
     +"ones run, which saves processing time. Languages without a voice "
     +"appear as subtitles.",
   ungeprueft_ueber:"Not yet reviewed by a native speaker. They work, but "
     +"their technical terms come straight from the machine.",
   einrichtung:"Setup",
   einrichtung_hin:"Set once per congregation, then leave it alone.",
   wlan_hin:"Network name and password of the router this computer is "
     +"connected to. They go into the first QR code so that phones can join "
     +"with one scan, without anyone typing a password. Without an entry the "
     +"QR page shows only the second code.",
   qr_oeffnen:"Open the QR page for the projector",
   gespeichert:"Saved.",
   qr_hin:"The QR button at the top right opens the page for the projector. "
     +"Listeners scan themselves in from there.",
   anhalten_hin:"Pausing stops delivery without disconnecting listeners. "
     +"They stay connected and continue as soon as it resumes.",
   zuhoerer_ueber:"Listeners per language",
   vorbereitung:"Before the service",kontext:"Topic and Bible passages",
   zuklappen:"collapse",ausklappen:"expand",
   post_ueber:"From the hall",post_weg:"Done",
   post_neu:"new messages from the hall",
   post_hin:"Replying is not provided for. Senders know this and expect "
     +"no answer."}};
let UI=localStorage.getItem("uiSprache")||"de";
let NAMEN={};

function uiZeichnen(){
  const t=TEXTE[UI];
  document.querySelectorAll("[data-t]").forEach(e=>{
    const k=e.dataset.t; if(t[k]) e.textContent=t[k];
  });
  // Die Ueberschrift richtet sich nach der Ansicht, nicht nach data-t.
  document.querySelector("h1").textContent =
    !einrichtung.hidden ? t.einrichtung
    : (!post.hidden ? t.post_ueber : t.pult);
  // Ein Knopf statt zweier: er zeigt immer, was als naechstes passiert,
  // wenn man ihn drueckt. Zwei Knoepfe, von denen einer wirkungslos ist,
  // zwingen zum Nachdenken darueber, in welchem Zustand man gerade ist.
  bStart.textContent = zustandLive ? t.pause : t.start;
  bStart.className = zustandLive ? "pause" : "start";
  // Erklaert, was Anhalten bewirkt. Solange nichts laeuft, erklaert er
  // etwas, das gerade niemanden beschaeftigt.
  anhaltenHin.hidden = !zustandLive;
  vorbereitungWort.textContent = vorbereitung.hidden ? t.ausklappen : t.zuklappen;
  document.querySelector(".reset").textContent=t.reset;
  bFest.textContent=t.fest; bAuto.textContent=t.auto;
  if(!messlauf) bEinmessen.textContent=t.einmessen;
  bSchnitt.textContent=schnittLaeuft?t.schnittstop:t.schnittstart;
  sprachknopf.textContent=UI==="de"?"EN":"DE";
  document.documentElement.lang=UI;
}
async function postLeeren(){
  await fetch("/api/nachrichten/leeren",{method:"POST"});
  lies();
}

function qrOeffnen(){
  // Neues Fenster, damit das Pult offen bleibt: der Techniker braucht
  // beides gleichzeitig, das eine auf dem Beamer, das andere vor sich.
  window.open("/qr", "_blank");
}

function warnungZeigen(text, schwer){
  // Eine Stelle, an der ueber den Balken entschieden wird. Vorher setzten
  // zwei Stellen Klassen, und eine davon schaltete ihn versehentlich ein.
  warnung.textContent = text || "";
  warnung.hidden = !text;
  warnung.classList.toggle("schwer", !!schwer);
}

function vorbereitungKlappen(){
  const zu = vorbereitung.hidden = !vorbereitung.hidden;
  vorbereitungPfeil.classList.toggle("zu", zu);
  vorbereitungWort.textContent = zu ? TEXTE[UI].ausklappen : TEXTE[UI].zuklappen;
  try{ localStorage.setItem("vorbereitungZu", zu ? "1" : ""); }catch(e){}
}

function postZeigen(){
  // Wie die Einrichtung eine eigene Ansicht: Meldungen wollen gelesen
  // werden, nicht zwischen Reglern stehen.
  const zeigen = post.hidden;
  post.hidden = !zeigen;
  betrieb.hidden = zeigen;
  einrichtung.hidden = true;
  zahnrad.classList.remove("an");
  document.querySelector("h1").textContent =
    zeigen ? TEXTE[UI].post_ueber : TEXTE[UI].pult;
}

function einrichtungZeigen(){
  // Zwei Ansichten statt eines aufklappenden Bereichs: was einmal je
  // Gemeinde eingestellt wird, soll am Sabbat gar nicht erst zwischen den
  // woechentlichen Handgriffen stehen. Nebeneinander wird beides
  // unuebersichtlich.
  const zeigen = einrichtung.hidden;
  einrichtung.hidden = !zeigen;
  post.hidden = true;
  betrieb.hidden = zeigen;
  zahnrad.classList.toggle("an", zeigen);
  document.querySelector("h1").textContent =
    zeigen ? TEXTE[UI].einrichtung : TEXTE[UI].pult;
  if(zeigen){ sprachenLaden(); wlanLaden(); }
}

function uiSprache(){
  UI=UI==="de"?"en":"de";
  localStorage.setItem("uiSprache",UI);
  uiZeichnen(); lies();
}

async function sprachenSetzen(){
  const ziele=[...document.querySelectorAll("#zielwahl input:checked")]
    .map(x=>x.value);
  await fetch("/api/sprachwahl",{method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({quelle:quellwahl.value,ziele:ziele})});
  await sprachenLaden(); lies();
}
async function sprachenLaden(){
  const d=await(await fetch("/api/sprachen")).json();
  NAMEN={}; d.liste.forEach(x=>NAMEN[x.code]=x.name);
  quellwahl.innerHTML=d.moeglich.map(x=>
    `<option value="${x.code}"${x.code===d.quelle?" selected":""}>`
    +`${x.name}</option>`).join("");
  // Geprüfte oben, ungeprüfte darunter mit eigener Überschrift. Eine
  // gestrichelte Kontur allein geht in einer Liste mit zwanzig Einträgen
  // unter, zumal die aktiven Sprachen gefüllt sind und den Rand verdecken.
  const kachel = (x) => {
    const an = d.ziele.includes(x.code);
    return `<label class="${an?"an":""}${x.stimme?"":" ohneton"}">`
      +`<input type=checkbox value="${x.code}"${an?" checked":""} `
      +`onchange="sprachenSetzen()">${x.name}${x.stimme?"":" (Text)"}</label>`;
  };
  const wahl = d.moeglich.filter(x=>x.code!==d.quelle);
  const geprueft = wahl.filter(x=>x.geprueft);
  const offen    = wahl.filter(x=>!x.geprueft);
  const t = TEXTE[UI];
  zielwahl.innerHTML =
    `<div class=zielliste>${geprueft.map(kachel).join("")}</div>`
    + (offen.length
       ? `<p class="hin untertitel">${t.ungeprueft_ueber}</p>`
         + `<div class="zielliste ungeprueft">${offen.map(kachel).join("")}</div>`
       : "");
}
// Pegel sind logarithmisch wahrnehmbar. Ein linearer Balken zeigt bei
// Sprache fast nichts, deshalb wird auf Dezibel umgerechnet.
const MIN_DB=-60;
const zuProzent=v=>{if(v<=0)return 0;
  const db=20*Math.log10(v);return Math.max(0,Math.min(100,(db-MIN_DB)/MIN_DB*-100))};
const zuWert=pz=>Math.pow(10,((pz/100)*-MIN_DB+MIN_DB)/20);

let handBetrieb=false;
async function s(w){await fetch("/api/steuerung/"+w,{method:"POST"});lies()}
async function umschalten(){
  // Zustand sofort umlegen, nicht erst beim naechsten Abruf: sonst bleibt
  // die Beschriftung bis zu zwei Sekunden lang falsch stehen.
  zustandLive = !zustandLive;
  uiZeichnen();
  await s(zustandLive ? "start" : "pause");
}
async function k(){
  const a=await fetch("/api/kontext",{method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({text:kontext.value})});
  zeigeErkannt(await a.json());
  lies();
}
function zeigeErkannt(d){
  if(!d) return;
  if(!d.stellen||!d.stellen.length){
    erkannt.textContent=kontext.value.trim()
      ? "Keine Bibelstelle erkannt. Schreibweise wie „1. Samuel 15“ oder „Mt 18“."
      : "";
    return;
  }
  erkannt.innerHTML="Erkannt: <b>"+d.stellen.join(", ")+"</b><br>"
    +d.namen.length+" von "+d.gefunden+" Namen im Prompt: "+d.namen.join(", ");
}
function schieben(){handBetrieb=true;marke.style.left=regler.value+"%";
  schwellwert.textContent="Schwelle "+regler.value+" %"}
async function festnageln(){
  await fetch("/api/schwelle",{method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({wert:zuWert(+regler.value)})});
  handBetrieb=false;
}
async function automatisch(){
  await fetch("/api/schwelle",{method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({automatisch:true})});
  handBetrieb=false;
}
let schnittLaeuft=false;
async function schnitt(){
  const a=await fetch("/api/mitschnitt",{method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify(schnittLaeuft?{beenden:true}:{})});
  const d=await a.json();
  if(schnittLaeuft&&d.datei){
    schnittinfo.innerHTML=d.minuten+" Minuten aufgenommen. "
      +'<a href="/mitschnitt/'+encodeURIComponent(d.datei)+'">'+d.datei+"</a>";
  }
}

let zustandLive=false;
let messlauf=false;
async function einmessen(){
  if(messlauf) return;
  messlauf=true;
  await fetch("/api/einmessen",{method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({dauer:12})});
}
async function messungBeenden(){
  const a=await fetch("/api/einmessen",{method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({beenden:true})});
  const d=await a.json();
  messlauf=false;
  bEinmessen.textContent=d.erfolg
    ? "Eingemessen. Nochmal messen"
    : "Einmessen: Prediger sprechen lassen";
  // Frueher stand hier className="warnung warnung", und genau das ist die
  // Regel fuer die gelbe Warnstufe: der Balken ging bei jedem Einmessen an
  // und blieb leer stehen.
  warnungZeigen(d.erfolg ? "" : (d.text || ""), false);
  handBetrieb=false;
}

async function wlanLaden(){
  // Was schon eingetragen ist, soll dastehen: sonst tippt jemand es
  // erneut ein, weil er die Felder leer sieht.
  try{
    const d=await(await fetch("/api/wlan")).json();
    if(!ssid.value) ssid.value=d.ssid||"";
    if(!wpw.value)  wpw.value=d.passwort||"";
    wlanstand.textContent = d.ssid ? TEXTE[UI].gespeichert : "";
  }catch(e){}
}

async function wlanSetzen(){
  // Sofort uebernehmen, so wie die Sprachauswahl daneben. Ein Knopf nur
  // fuer dieses eine Feld hatte zur Folge, dass man Sprachen aenderte und
  // beim Druecken ein leeres WLAN mit uebernahm.
  await fetch("/api/wlan",{method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({ssid:ssid.value,passwort:wpw.value})});
  wlanstand.textContent = ssid.value ? TEXTE[UI].gespeichert : "";
}

async function hochladen(){
  const f=datei.files[0]; if(!f) return;
  skriptinfo.textContent="wird gelesen …";
  const daten=new FormData(); daten.append("datei",f);
  try{
    const a=await fetch("/api/skript",{method:"POST",body:daten});
    const d=await a.json();
    if(d.fehler){skriptinfo.textContent="Datei ist leer oder unlesbar.";return}
    skriptinfo.innerHTML=d.woerter+" Wörter gelesen. "
      +(d.stellen.length?"Stellen: <b>"+d.stellen.join(", ")+"</b>. ":"")
      +d.bekannt+" bekannte und "+d.neu+" weitere Namen.<br>"
      +d.namen.join(", ");
    lies();
  }catch(e){skriptinfo.textContent="Hochladen fehlgeschlagen."}
}

async function pegel(){
  try{
    const d=await(await fetch("/api/pegel")).json();
    const pz=zuProzent(d.jetzt), sz=zuProzent(d.schwelle);
    fuell.style.width=pz+"%";
    // Dieselbe Grenze wie bei der Warnung: hoerbar heisst deutlich ueber
    // dem Raumgeraeusch, nicht bloss ueber null.
    const hoerbar = d.jetzt > Math.max(d.grund*2.5, 0.0015);
    fuell.className = "fuell" + (d.jetzt > d.schwelle ? " ueber"
                                 : (hoerbar ? " knapp" : ""));
    if(!handBetrieb){marke.style.left=sz+"%";regler.value=Math.round(sz)}
    pegelwert.textContent=(d.spricht?"spricht":"still")+" · "+Math.round(pz)+" %";
    // "knapp darunter" ist der Fall, den man am Regler sofort beheben
    // kann: es wird gesprochen, nur zu leise fuer die Schwelle.
    schwellwert.textContent="Schwelle "+Math.round(sz)+" % · "
      +(d.fest?"fest":"automatisch")
      +(d.verworfen?" · "+d.verworfen+" verworfen":"")
      +(d.knapp>30?" · knapp darunter":"");
    bFest.className="klein"+(d.fest?"":" aus");
    bAuto.className="klein"+(d.fest?" aus":"");
    // Nur zeigen, wenn es auch etwas zu sagen gibt: ein leerer gelber
    // Balken sieht nach Warnung aus und stumpft ab.
    warnungZeigen(d.lage_text && (d.lage==="alarm"||d.lage==="warnung")
      ? (d.lage==="alarm" ? "Achtung: " : "") + d.lage_text : "",
      d.lage==="alarm");
    if(d.einmessen&&d.einmessen.laeuft){
      messlauf=true;
      bEinmessen.textContent="Messe … noch "+d.einmessen.rest+" s, "
        +"jetzt sprechen lassen";
    }else if(messlauf){
      messungBeenden();
    }
  }catch(e){
    // Frueher stand hier ein leeres catch. Das hat einen Zugriffsfehler
    // still verschluckt, den es seit Wochen gab: die Knopf-IDs hatten
    // Bindestriche, und dafuer legt der Browser keine gleichnamige
    // Variable an. Ein Fehler, den niemand sieht, wird nicht behoben.
    console.error("Pegel:", e);
  }
}
async function lies(){
  // Abruf und Verarbeitung getrennt: vorher fing ein einziges catch beides
  // ab und meldete "Server nicht erreichbar", auch wenn der Server
  // einwandfrei antwortete und nur ein Fehler in der Anzeige steckte. Die
  // Fehlersuche lief damit in die falsche Richtung.
  let d;
  try{
    const a = await fetch("/api/zustand");
    if(!a.ok) throw new Error("HTTP " + a.status);
    d = await a.json();
  }catch(e){
    lage.textContent = "Server nicht erreichbar (" + e.message + ")";
    return;
  }
  try{
    const t=TEXTE[UI];
    punkt.className="punkt"+(d.live?" an":"");
    const quelle = (d.audio_quelle!==undefined && d.audio_quelle!==null)
      ? " · "+t.tonda : "";
    if(zustandLive!==d.live){ zustandLive=d.live; uiZeichnen(); }
    lage.textContent=(d.live?t.laeuft:t.pause_an)+" · "+d.gesendet
      +" "+t.segmente+" · "+d.gesamt+" "+t.hoerer+quelle;
    zahlen.innerHTML=Object.entries(d.hoerer||{}).map(([a,b])=>
      `<tr><td>${NAMEN[a]||a}</td><td>${b}</td></tr>`).join("");
    if(d.mitschnitt){
      schnittLaeuft=true;
      bSchnitt.textContent=t.schnittstop;
      schnittinfo.textContent=d.mitschnitt.minuten+" Minuten · "
        +d.mitschnitt.datei;
    }else if(schnittLaeuft){
      schnittLaeuft=false;
      bSchnitt.textContent=t.schnittstart;
    }
    const post_=(d.nachrichten||[]);
    briefkasten.hidden = post_.length===0;
    postzahl.textContent = post_.length;
    if(post_.length===0 && !post.hidden){ postZeigen(); }
    postliste.innerHTML = post_.slice().reverse().map(x=>
      `<div><span class=wann>${x.zeit}${x.sprache?" · "+x.sprache:""}</span>`
      +`${x.text.replace(/[<>&]/g, c=>({"<":"&lt;",">":"&gt;","&":"&amp;"}[c]))}`
      +`</div>`).join("");
    mit.innerHTML=(d.letzte||[]).slice().reverse().map(x=>
      `<div>${x.gesamt}s &nbsp; ${x.deutsch}</div>`).join("");
    if(d.stellen&&d.stellen.length&&!erkannt.innerHTML)
      zeigeErkannt({stellen:d.stellen,namen:d.namen||[],
                    gefunden:(d.namen||[]).length});
  }catch(e){
    lage.textContent = "Anzeigefehler: " + e.message;
    console.error(e);
  }
}
try{
  if(localStorage.getItem("vorbereitungZu")){
    vorbereitung.hidden = true;
    vorbereitungPfeil.classList.add("zu");
    vorbereitungWort.textContent = TEXTE[UI].ausklappen;
  }
}catch(e){}
sprachenLaden().then(uiZeichnen);
lies();setInterval(lies,2000);
pegel();setInterval(pegel,150);
</script></html>"""


# ================================================================

def lokale_ip():
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--geraete", action="store_true")
    p.add_argument("--geraet", type=int, default=None)
    p.add_argument("--netz", action="store_true",
                   help="Ton ueber das Netz entgegennehmen statt vom "
                        "Mikrofon (sender.py auf der Gegenseite)")
    p.add_argument("--schluessel", default="gemeinde",
                   help="muss zum Sender passen")
    p.add_argument("--datei", default=None,
                   help="statt Mikrofon eine Aufnahme einspeisen, fuer den "
                        "Dauerlauf")
    p.add_argument("--tempo", type=float, default=1.0,
                   help="Wiedergabetempo der Datei. Nur zum schnellen "
                        "Ausprobieren, verfaelscht die Latenzmessung.")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--nur-text", action="store_true",
                   help="ohne Sprachausgabe, nur Untertitel")
    p.add_argument("--pause", type=float, default=0.45)
    p.add_argument("--min-dauer", type=float, default=1.6)
    p.add_argument("--max-dauer", type=float, default=8.0)
    p.add_argument("--betrieb", default="kontext",
                   choices=["kontext", "satz", "roh"],
                   help="kontext: sofort uebersetzen, aber mit dem "
                        "bisherigen Satzanfang als Einordnung (schnell und "
                        "grammatisch brauchbar). satz: auf das Satzende "
                        "warten (beste Grammatik, mehrere Sekunden "
                        "langsamer). roh: wie frueher, ohne beides.")
    p.add_argument("--max-woerter", type=int, default=40,
                   help="Notbremse: ab so vielen Woertern wird auch ohne "
                        "Satzzeichen uebersetzt")
    p.add_argument("--max-warten", type=float, default=9.0,
                   help="Notbremse: nach so vielen Sekunden ebenso")
    p.add_argument("--min-sprachdauer", type=float, default=0.9,
                   help="Segmente verwerfen, die weniger echten Schall "
                        "enthalten (Sekunden)")
    p.add_argument("--rate", type=int, default=None,
                   help="Aufnahmerate erzwingen, sonst automatisch")
    p.add_argument("--sofort", action="store_true",
                   help="ohne Druck aufs Pult sofort loslegen")
    a = p.parse_args()

    if a.geraete:
        geraete_zeigen()
        return

    basis = Path(__file__).resolve().parent
    config.ERGEBNIS_ORDNER.mkdir(exist_ok=True)

    werk = Werk(nur_text=a.nur_text)
    seg = Segmentierer(pause=a.pause, min_dauer=a.min_dauer,
                       max_dauer=a.max_dauer,
                       min_sprachdauer=a.min_sprachdauer)
    lauf = Lauf(werk, seg)
    lauf.betrieb = a.betrieb
    lauf.sammler = Satzsammler(a.max_woerter, a.max_warten)
    stoppen = threading.Event()
    rate = MIKRO_RATE

    lauf.audio_schluessel = a.schluessel

    if a.netz:
        # Kein eigener Thread: der Ton kommt ueber den WebSocket herein und
        # wird dort direkt an denselben Segmentierer gegeben.
        #
        # Bewusst NICHT von selbst starten. Vorher lief die Uebersetzung ab
        # dem Serverstart, waehrend das Pult "Übersetzung starten" anzeigte:
        # zwei Wahrheiten gleichzeitig. Der Techniker drueckt jetzt bewusst
        # auf Start, so wie er es auch mit dem Mikrofon tun wuerde.
        if a.sofort:
            lauf.laeuft = True
            lauf.begonnen = time.time()
        rate = MIKRO_RATE
    elif a.datei:
        if not Path(a.datei).exists():
            sys.exit(f"Nicht gefunden: {a.datei}")
        # Eine Aufnahme hat keinen wandernden Raumklang, dem die Schwelle
        # folgen muesste. Fest eingestellt bleibt die Segmentierung ueber
        # die ganze Datei vergleichbar.
        seg.feste_schwelle = 0.006
        # Sofort loslegen, sonst laeuft die Aufnahme ins Leere, bis jemand
        # am Pult drueckt. Ohne Zuhoerer ist hier noch niemand zu
        # benachrichtigen, deshalb direkt statt ueber starten().
        lauf.laeuft = True
        lauf.begonnen = time.time()
        threading.Thread(target=datei_thread,
                         args=(lauf, a.datei, seg, stoppen, a.tempo),
                         daemon=True).start()
    else:
        rate, blockgroesse = rate_waehlen(a.geraet, a.rate)
        if a.sofort:
            lauf.laeuft = True
            lauf.begonnen = time.time()
        threading.Thread(target=mikrofon_thread,
                         args=(lauf, a.geraet, seg, stoppen, rate, blockgroesse),
                         daemon=True).start()

    import uvicorn
    ip = lokale_ip()
    print(f"\n  Zuhörer   http://{ip}:{a.port}/")
    print(f"  Pult      http://{ip}:{a.port}/pult")
    print(f"  QR-Codes  http://{ip}:{a.port}/qr")
    print(f"  Modell    {config.LIVE_MODELL}"
          f"{'  (nur Text)' if a.nur_text else ''}")
    print(f"  Schnitt   Pause {a.pause}s, {a.min_dauer} bis {a.max_dauer}s")
    beschriftung = {"kontext": "sofort, mit Satzanfang als Einordnung",
                    "satz": f"erst am Satzende, Notbremse bei "
                            f"{a.max_woerter} Wörtern oder {a.max_warten}s",
                    "roh": "sofort, ohne Einordnung"}
    print(f"  Übersetzt {beschriftung[a.betrieb]}")
    if a.netz:
        print(f"  Quelle    über das Netz, Schlüssel \"{a.schluessel}\"")
        print(f"  Sender    python sender.py --ziel ws://{ip}:{a.port} "
              f"--geraet <Nr>\n")
    elif a.datei:
        print(f"  Quelle    {Path(a.datei).name} (Dauerlauf)\n")
    else:
        print(f"  Aufnahme  {rate} Hz -> {MIKRO_RATE} Hz\n")

    try:
        uvicorn.run(app_bauen(lauf, basis, a.port), host="0.0.0.0", port=a.port,
                    log_level="warning")
    except OSError as e:
        if "10048" in str(e) or "address" in str(e).lower():
            print(f"\nPort {a.port} ist belegt. Laeuft noch ein anderer "
                  f"Server, etwa mock_server.py?")
            print(f"Anderen Port nehmen: server.py --geraet {a.geraet} "
                  f"--port {a.port + 1}")
        else:
            raise
    finally:
        stoppen.set()


if __name__ == "__main__":
    main()
