#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Die Twi-Stimme: Coqui-Modell nach ONNX fuer Piper -- einmalig, am
Entwicklungsrechner.

    <coqui-venv>/bin/python werkzeuge/twi_stimme.py --umwandeln ORDNER
    .venv/bin/python        werkzeuge/twi_stimme.py --vergleichen ORDNER

Auf den Gemeinderechnern laeuft davon NICHTS. Dort liegt nur das
Ergebnis: tw_GH-openbible_asante-vits.onnx und .onnx.json, ueber Stick
oder Vorrat, gelistet in teile.json. Kein torch, kein Coqui.

DIE QUELLE

tts_models--tw_asante--openbible--vits aus dem Release v0.6.2_models von
coqui-ai/TTS. Lizenz laut Coqui CC BY-SA 4.0, Daten BibleTTS (Open.Bible,
Asante Twi von Biblica). Siehe LIZENZEN.md.

--umwandeln (braucht eine Umgebung mit Coqui -- Hinweise unten)

  1. Laedt das Archiv (rund 920 MB), falls es im ORDNER noch nicht liegt.
  2. Exportiert nach ONNX mit Vits.export_onnx -- mit dem ALTEN Exporter
     (dynamo=False) und mit einer Berichtigung, siehe unten.
  3. Schreibt die Piper-Beschreibung (.onnx.json) aus dem Tokenizer von
     Coqui selbst, nicht aus einer abgeschriebenen Liste.
  4. Spricht die Pruefsaetze mit Coqui, Rauschen 0, und legt IDs und Ton
     als Bezug ab.

--vergleichen (in der Devarenu-venv, mit Piper)

  Spricht dieselben Saetze ueber Piper mit der neuen Beschreibung und
  vergleicht: IDs gleich? Ton gleich lang, gleiche Abtastwerte?

DIE ZUORDNUNG ZEICHEN -> ID

Coqui (VitsCharacters, add_blank, ohne BOS/EOS) macht aus "ab":

    <BLNK> a <BLNK> b <BLNK>

Piper macht aus "ab":   ^ _ a _ b _ $

Also bekommt "_" die Nummer von <BLNK>, und ^ und $ bekommen eine LEERE
Liste -- dann fallen sie weg, und es kommt dieselbe Folge heraus.
Piper senkt nicht ab; damit Ɛ und Ɔ nicht verloren gehen, zeigen die
Grossbuchstaben auf die Nummer des Kleinbuchstabens. Die uebrige
Bereinigung von Coqui (; und : zu Komma usw.) macht config.SPRECHFORM.

DIE BERICHTIGUNG IM EXPORT

Coquis export_onnx schreibt scales[0] und scales[2] nach
self.noise_scale und self.noise_scale_dp -- inference() liest aber
inference_noise_scale und inference_noise_scale_dp. Unberichtigt landen
feste 0,333 im Graphen; der Eingang scales wirkt dann nur aufs Tempo,
und dieselbe Eingabe gibt bei jedem Aufruf eine andere Dauer. Zwei
Eigenschaften leiten die Zuweisung an die richtige Stelle. An den
Gewichten aendert das nichts.

DIE UMGEBUNG (nur hier, nur unter .tmp/)

    uv venv -p 3.12 .tmp/coqui-venv
    VIRTUAL_ENV=.tmp/coqui-venv uv pip install --index-strategy \
        unsafe-best-match --extra-index-url \
        https://download.pytorch.org/whl/cpu torch==2.8.0 torchaudio==2.8.0 \
        coqui-tts "transformers>=4.57,<5" onnx onnxruntime

torch 2.8, weil ab 2.9 Coqui torchcodec verlangt und der neue Exporter
Vorgabe ist; transformers unter 5, weil Coqui sonst beim Import scheitert.
"""

import argparse
import json
import sys
import urllib.request
import wave
import zipfile
from pathlib import Path

NAME = "tw_GH-openbible_asante-vits"
ARCHIV = ("https://github.com/coqui-ai/TTS/releases/download/v0.6.2_models/"
          "tts_models--tw_asante--openbible--vits.zip")

# Pruefsaetze: mit ɛ, ɔ, Ɛ und Ɔ, klein und gross. Der erste ist Psalm
# 23,1 aus der Asante-Twi-Bibel von Biblica.
SAETZE = [
    "Awurade ne me hwɛfo, hwee renhia me.",
    "Ɔdɔ nni awiei. Ɛnnɛ yɛda Onyankopɔn ase.",
    "Yɛn asafo panyin bɛbɔ mpaeɛ ama ayarefoɔ no seesei.",
]


def _coqui(ordner):
    from TTS.tts.configs.vits_config import VitsConfig
    from TTS.tts.models.vits import Vits
    quelle = ordner / "asante-twi"
    if not (quelle / "model_file.pth").exists():
        zipdatei = ordner / "tw.zip"
        if not zipdatei.exists():
            print(f"lade {ARCHIV} ...")
            urllib.request.urlretrieve(ARCHIV, zipdatei)
        with zipfile.ZipFile(zipdatei) as z:
            z.extractall(ordner)
    cfg = VitsConfig()
    cfg.load_json(str(quelle / "config.json"))
    m = Vits.init_from_config(cfg)
    m.load_checkpoint(cfg, str(quelle / "model_file.pth"), eval=True)
    return cfg, m


def _berichtigen(m):
    """Siehe Modulkommentar: DIE BERICHTIGUNG IM EXPORT."""
    class Berichtigt(type(m)):
        @property
        def noise_scale(self):
            return self.inference_noise_scale

        @noise_scale.setter
        def noise_scale(self, wert):
            self.__dict__["inference_noise_scale"] = wert

        @property
        def noise_scale_dp(self):
            return self.inference_noise_scale_dp

        @noise_scale_dp.setter
        def noise_scale_dp(self, wert):
            self.__dict__["inference_noise_scale_dp"] = wert

    m.__dict__.pop("noise_scale", None)
    m.__dict__.pop("noise_scale_dp", None)
    m.__class__ = Berichtigt


def beschreibung(m, cfg):
    tok = m.tokenizer
    c2i = dict(tok.characters._char_to_id)
    if tok.use_eos_bos or not tok.add_blank:
        sys.exit("Unerwarteter Tokenizer (BOS/EOS oder ohne BLNK) -- die "
                 "Zuordnung unten passt dann nicht.")
    karte = {z: [i] for z, i in c2i.items()
             if z not in ("<PAD>", "<BLNK>", "<BOS>", "<EOS>")}
    karte["_"] = [tok.characters.blank_id]
    karte["^"] = []
    karte["$"] = []
    for z, i in c2i.items():
        if len(z) == 1 and len(z.upper()) == 1 and z.upper() != z:
            karte.setdefault(z.upper(), [i])
    return {
        "audio": {"sample_rate": cfg.audio.sample_rate, "quality": "medium"},
        "espeak": {"voice": "tw"},
        "language": {"code": "tw_GH", "family": "tw", "region": "GH",
                     "name_native": "Twi (Asante)",
                     "name_english": "Twi (Asante)",
                     "country_english": "Ghana"},
        "inference": {"noise_scale": float(m.inference_noise_scale),
                      "length_scale": float(m.length_scale),
                      "noise_w": float(m.inference_noise_scale_dp)},
        "phoneme_type": "text",
        "phoneme_map": {},
        "phoneme_id_map": karte,
        "num_symbols": cfg.model_args.num_chars,
        "num_speakers": 1,
        "speaker_id_map": {},
        "piper_version": "1.0.0",
        "dataset": "openbible_asante-twi",
        "herkunft": ("Umgewandelt aus tts_models--tw_asante--openbible--vits "
                     "(coqui-ai/TTS, Release v0.6.2_models), Daten BibleTTS "
                     "(Open.Bible), CC BY-SA 4.0. Die ONNX-Datei ist eine "
                     "Umwandlung und steht ebenfalls unter CC BY-SA 4.0. "
                     "Werkzeug: werkzeuge/twi_stimme.py im Devarenu-Repo."),
    }


def umwandeln(ordner):
    import numpy as np
    import torch
    ordner.mkdir(parents=True, exist_ok=True)
    cfg, m = _coqui(ordner)
    beschr = beschreibung(m, cfg)

    # Der Bezug fuer --vergleichen: Coqui selbst, Rauschen 0.
    bezug = []
    for satz in SAETZE:
        ids = m.tokenizer.text_to_ids(satz)
        m.inference_noise_scale = 0.0
        m.inference_noise_scale_dp = 0.0
        with torch.no_grad():
            aus = m.inference(torch.LongTensor(ids).unsqueeze(0),
                              aux_input={"x_lengths": torch.LongTensor([len(ids)])})
        ton = aus["model_outputs"].squeeze().numpy().astype(np.float32)
        bezug.append({"satz": satz, "ids": ids, "werte": len(ton)})
        np.save(ordner / f"bezug_{len(bezug)}.npy", ton)
    m.inference_noise_scale = beschr["inference"]["noise_scale"]
    m.inference_noise_scale_dp = beschr["inference"]["noise_w"]
    (ordner / "bezug.json").write_text(
        json.dumps(bezug, ensure_ascii=False, indent=1), encoding="utf-8")

    echt = torch.onnx.export

    def alter_exporter(*a, **k):
        k["dynamo"] = False
        return echt(*a, **k)

    torch.onnx.export = alter_exporter
    _berichtigen(m)
    ziel = ordner / f"{NAME}.onnx"
    m.export_onnx(output_path=str(ziel), verbose=False)
    (ordner / f"{NAME}.onnx.json").write_text(
        json.dumps(beschr, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(f"geschrieben: {ziel} ({ziel.stat().st_size / 1e6:.0f} MB) "
          f"und {ziel.name}.json")


def vergleichen(ordner):
    import time
    import numpy as np
    import onnxruntime
    from piper import PiperVoice, SynthesisConfig
    v = PiperVoice.load(str(ordner / f"{NAME}.onnx"))
    bezug = json.loads((ordner / "bezug.json").read_text(encoding="utf-8"))
    schief = 0
    for i, b in enumerate(bezug, 1):
        ids = v.phonemes_to_ids(v.phonemize(b["satz"])[0])
        ton = v.phoneme_ids_to_audio(
            ids, SynthesisConfig(noise_scale=0.0, noise_w_scale=0.0,
                                 length_scale=1.0))
        coqui = np.load(ordner / f"bezug_{i}.npy")
        gleich_ids = ids == b["ids"]
        gleich_lang = len(ton) == len(coqui)
        abw = (float(np.max(np.abs(ton - coqui))) if gleich_lang
               else float("nan"))
        ok = gleich_ids and gleich_lang and abw < 1e-3
        schief += not ok
        print(f"  {'ok  ' if ok else 'FEHL'} {b['satz'][:44]:44} "
              f"IDs {len(ids)}={'gleich' if gleich_ids else 'ANDERS'}  "
              f"Werte {len(ton)}/{len(coqui)}  max. Abweichung {abw:.6f}")
    # Rechenzeit auf zwei Kernen -- so viel hat ein kleiner
    # Gemeinderechner neben Whisper und dem Sprachmodell frei.
    opt = onnxruntime.SessionOptions()
    opt.intra_op_num_threads = 2
    opt.inter_op_num_threads = 1
    v.session = onnxruntime.InferenceSession(
        str(ordner / f"{NAME}.onnx"), sess_options=opt,
        providers=["CPUExecutionProvider"])
    ids = v.phonemes_to_ids(v.phonemize(bezug[0]["satz"])[0])
    v.phoneme_ids_to_audio(ids)
    t0 = time.perf_counter()
    ton = v.phoneme_ids_to_audio(ids)
    print(f"  zwei Kerne: {time.perf_counter() - t0:.2f} s Rechenzeit fuer "
          f"{len(ton) / v.config.sample_rate:.2f} s Ton")
    return 1 if schief else 0


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--umwandeln", metavar="ORDNER")
    p.add_argument("--vergleichen", metavar="ORDNER")
    a = p.parse_args()
    if a.umwandeln:
        umwandeln(Path(a.umwandeln))
        return 0
    if a.vergleichen:
        return vergleichen(Path(a.vergleichen))
    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
