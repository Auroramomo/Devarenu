# -*- coding: utf-8 -*-
"""Zentrale Konfiguration von Devarenu.

Diese Datei gilt fuer alle Gemeinden gleich und wird beim Aktualisieren
mit ueberschrieben. Was pro Gemeinde abweicht, wird am Pult eingestellt
und landet spaeter in zustand.json daneben, nicht hier.
"""

from pathlib import Path

# ---------------------------------------------------------------- Pfade
BASIS = Path(__file__).resolve().parent

# Fassung des Programms. Steht in einer eigenen Datei, damit
# aktualisieren.sh und der Blick von aussen dieselbe Quelle haben: was
# am Pult steht, ist dann auch das, was im Ordner liegt.
try:
    VERSION = (BASIS / "VERSION").read_text(encoding="utf-8").strip()
except OSError:
    VERSION = "unbekannt"

GLOSSAR_CSV = BASIS / "glossar_v0.4.csv"
TESTSAETZE_CSV = BASIS / "testsaetze_v0.3.csv"
ERGEBNIS_ORDNER = BASIS / "ergebnisse"

# Hier liegen die heruntergeladenen Whisper-Modelle. Bewusst im
# Projektordner und nicht im Benutzer-Cache: einrichten.sh laeuft unter
# dem angemeldeten Benutzer, der Systemdienst spaeter womoeglich unter
# einem anderen. Aus dessen Cache liest er nicht und wuerde die 1,6 GB
# beim ersten Gottesdienst nochmal ziehen. Nebeneffekt: der Ordner ist
# vollstaendig und laesst sich als Ganzes kopieren.
MODELL_ORDNER = BASIS / "models"

# Audiodatei fuer Test A.
AUDIO = str(BASIS / "predigt.mp3")

# Ausschnitt fuer Test A in Sekunden. AUDIO_DAUER = None nimmt alles.
# Die Datei ist rund 1934 Sekunden lang, also gut 32 Minuten.
# Fuer den Nachtlauf die ganze Datei. Zum spaeteren Iterieren am Prompt
# stattdessen AUDIO_START = 600 und AUDIO_DAUER = 600 setzen, sonst
# rechnet jeder Durchgang die komplette Predigt neu.
AUDIO_START = 0
AUDIO_DAUER = None

# ---------------------------------------------------------------- Whisper
WHISPER_MODELL = "large-v3-turbo"
WHISPER_DEVICE = "cuda"
WHISPER_COMPUTE = "float16"   # auf CPU stattdessen "int8"
WHISPER_SPRACHE = "de"
WHISPER_BEAM = 5
WHISPER_VAD = True

# Zeichenbudget fuer den initial_prompt. Whisper schneidet bei 224 Token
# hart ab. Deutsch braucht grob 2,5 bis 3 Zeichen je Token, 520 Zeichen
# liegen damit sicher darunter. Nicht ohne Messung hochsetzen.
PROMPT_MAX_ZEICHEN = 520

# Reihenfolge der Bloecke im Prompt. Was hinten steht, faellt beim
# Kuerzen zuerst weg. D = adventistische Spezifika, C = theologische
# Begriffe, A = Bibelbuchnamen.
PROMPT_BLOECKE = ("D", "C", "A")

# Satz, der dem Prompt vorangestellt wird. Whisper uebernimmt daraus auch
# Stil und Zeichensetzung, deshalb ein vollstaendiger deutscher Satz.
PROMPT_RAHMEN = ("Mitschrift einer Predigt im Gottesdienst der "
                 "Siebenten-Tags-Adventisten. Vorkommende Begriffe: {begriffe}.")

# Einleitung fuer den Livebetrieb. Hier ohne Platzhalter, weil der Prompt
# dort aus drei Teilen entsteht: Einleitung, Thema vom Pult, Namen aus den
# Bibelstellen.
PROMPT_EINLEITUNG = ("Mitschrift einer Predigt im Gottesdienst der "
                     "Siebenten-Tags-Adventisten.")

# ---------------------------------------------------------------- Uebersetzung
# Die Ausgangssprache. Sie wird nicht uebersetzt: der Text kommt direkt aus
# der Spracherkennung, der Ton ist die Originalaufnahme des Predigers. Das
# ist die einzige Ausgabe ohne Uebersetzungsfehler und zugleich die fuer
# Schwerhoerige, die den Untertitel mitlesen.
AUSGANGSSPRACHE = "de"

# Zielsprachen. Jede zusaetzliche kostet Rechenzeit; bei 31 Prozent
# Auslastung im Dauerlauf ist Luft fuer einige mehr. Die Grenze ist eher,
# ob sich jemand findet, der die Qualitaet beurteilen kann.
ZIELSPRACHEN = ["en", "ru", "fa"]

NLLB_CODES = {"de": "deu_Latn", "en": "eng_Latn",
              "ru": "rus_Cyrl", "fa": "pes_Arab"}

SPRACHNAMEN = {
    "de": "Deutsch", "en": "Englisch", "ru": "Russisch",
    "fa": "Persisch (Farsi)", "uk": "Ukrainisch", "pl": "Polnisch",
    "ro": "Rumänisch", "es": "Spanisch", "fr": "Französisch",
    "pt": "Portugiesisch", "it": "Italienisch", "tr": "Türkisch",
    "ar": "Arabisch", "sw": "Suaheli", "nl": "Niederländisch",
    "vi": "Vietnamesisch", "hu": "Ungarisch", "cs": "Tschechisch",
    "sr": "Serbisch", "el": "Griechisch", "ka": "Georgisch",
}

# Sprachen, deren Fachwortverzeichnis ein Muttersprachler durchgesehen
# hat. Alle uebrigen laufen technisch genauso, aber ihre Terminologie ist
# maschinell erzeugt und ungeprueft. Bei Persisch hat die Pruefung acht
# von 54 Eintraegen korrigiert, darunter einen, der theologisch ins
# Gegenteil ging. Diesen Unterschied sollen die Zuhoerer sehen koennen.
GEPRUEFT = {"de", "en", "ru", "fa"}

# Piper-Stimmen je Sprache, so wie sie im Repo rhasspy/piper-voices liegen.
# Was hier steht, kann einrichten.sh herunterladen; was fehlt, laeuft als
# reiner Untertitel weiter.
STIMMEN = {
    "de": "de/de_DE/thorsten/medium/de_DE-thorsten-medium",
    "en": "en/en_US/lessac/medium/en_US-lessac-medium",
    "ru": "ru/ru_RU/irina/medium/ru_RU-irina-medium",
    "fa": "fa/fa_IR/amir/medium/fa_IR-amir-medium",
    "uk": "uk/uk_UA/ukrainian_tts/medium/uk_UA-ukrainian_tts-medium",
    "pl": "pl/pl_PL/darkman/medium/pl_PL-darkman-medium",
    "ro": "ro/ro_RO/mihai/medium/ro_RO-mihai-medium",
    "es": "es/es_ES/davefx/medium/es_ES-davefx-medium",
    "fr": "fr/fr_FR/siwis/medium/fr_FR-siwis-medium",
    "pt": "pt/pt_BR/faber/medium/pt_BR-faber-medium",
    "it": "it/it_IT/paola/medium/it_IT-paola-medium",
    "tr": "tr/tr_TR/dfki/medium/tr_TR-dfki-medium",
    "ar": "ar/ar_JO/kareem/medium/ar_JO-kareem-medium",
    "sw": "sw/sw_CD/lanfrica/medium/sw_CD-lanfrica-medium",
    "nl": "nl/nl_NL/mls/medium/nl_NL-mls-medium",
    "vi": "vi/vi_VN/vais1000/medium/vi_VN-vais1000-medium",
    "hu": "hu/hu_HU/anna/medium/hu_HU-anna-medium",
    "cs": "cs/cs_CZ/jirka/medium/cs_CZ-jirka-medium",
    "sr": "sr/sr_RS/serbski_institut/medium/sr_RS-serbski_institut-medium",
    "el": "el/el_GR/rapunzelina/medium/el_GR-rapunzelina-medium",
    "ka": "ka/ka_GE/natia/medium/ka_GE-natia-medium",
}

# NLLB-Modelle. Auskommentieren, was nicht getestet werden soll.
# NLLB ist nach Lauf 1 raus: 61 bis 67 Prozent Compliance, und zwar
# dauerhaft, weil das Modell keine Terminologievorgabe entgegennehmen kann.
# Bei T36 lieferte es in allen drei Groessen eine falsche Bibelstelle.
# Zum Wiedereinschalten die Zeilen entkommentieren.
NLLB_MODELLE = [
    # "facebook/nllb-200-distilled-600M",
    # "facebook/nllb-200-distilled-1.3B",
    # "facebook/nllb-200-3.3B",
]

# Ollama-Modelle. Das Skript fragt /api/tags ab und ueberspringt still,
# was nicht installiert ist. Es reicht also, hier grosszuegig zu sein.
OLLAMA_URL = "http://localhost:11434"
# WICHTIG zur Interpretation: die 5080 hat 16 GB. Alles ab etwa 15 GB
# Modellgroesse lagert auf CPU aus. Seine gemessene Zeit ist dann KEINE
# Aussage ueber die Modellgeschwindigkeit auf passender Hardware, sondern
# ueber das Auslagern. Die Gruppierung unten haelt das auseinander.
#
# Kein aurora:latest: das ist ein Modelfile-Derivat von ministral-3:14b mit
# eigener Persona im SYSTEM-Block, die mit dem Uebersetzer-Prompt kollidiert.
# In einen Vergleichstest gehoert das Basismodell.
OLLAMA_MODELLE = [
    "qwen3:4b-instruct",     # 94 % mit Glossar bei 0,42 s. Schnellster Kandidat.
    "gemma4:12b",            # 95 % bei 7,6 GB. Bestes Verhaeltnis.
    "ministral-3:14b",
    "gemma4:26b",            # 98 %, Obergrenze des Feldes
    "mistral-small:24b",     # zweite Chance: ohne Glossar lateinische Umschrift
                             # bei Farsi (10 Faelle), mit Glossar nur noch 1
    "qwen3.6:35b-a3b",       # zweite Chance: uebersetzte ohne Glossar teils
                             # gar nicht nach Farsi (9 Faelle), mit Glossar 1
]

OLLAMA_TIMEOUT = 300
# num_predict grosszuegig: Reasoning-Modelle verbrauchen einen Teil des
# Budgets fuer den Denkblock. Ist es zu knapp, wird der Denkblock
# abgeschnitten und es kommt gar keine Uebersetzung mehr heraus.
OLLAMA_OPTIONEN = {"temperature": 0.1, "num_predict": 900}

# --- Variantenmatrix ---------------------------------------------------
# Lauf 1 hat gezeigt: mit Glossar 88 bis 98 Prozent, ohne 47 bis 81, ohne
# jede Ueberschneidung. Die Ohne-Glossar-Laeufe sind damit weitgehend
# beantwortet; einer bleibt als Basislinie sinnvoll, mehr nicht.
TESTE_OHNE_GLOSSAR = False   # auf True setzen fuer eine neue Basislinie
TESTE_MIT_GLOSSAR = True
TESTE_MIT_KONTEXT = True     # zusaetzlicher Lauf mit vorangehenden Saetzen

# --- Parallelitaet ------------------------------------------------------
# Die drei Zielsprachen gleichzeitig statt nacheinander. Faktor drei auf
# die Wandzeit, ohne Qualitaetsverlust.
#
# WICHTIG: Ollama muss serverseitig parallele Anfragen erlauben, sonst
# stellt es sie intern in eine Warteschlange und der Gewinn verpufft.
# Einmalig setzen und Ollama neu starten:
#     setx OLLAMA_NUM_PARALLEL 3
PARALLEL = True


# --- Livebetrieb (server.py) -------------------------------------------
# Uebersetzungsmodell fuer die Live-Pipeline. gemma4:12b hat im Test die
# wenigsten Auffaelligkeiten bei 85 Prozent Compliance und schafft drei
# Sprachen gleichzeitig in etwa einer Sekunde. Auf schwaecherer Hardware
# ist qwen3:4b-instruct die Alternative: eine Sekunde schneller, dafuer
# ein Prozentpunkt weniger Compliance und mehr Auffaelligkeiten.
LIVE_MODELL = "gemma4:12b"

# Wiedergabetempo der Sprachausgabe. Gemessener Laengenfaktor ist 1,24:
# Russisch und Persisch brauchen gesprochen 24 Prozent laenger als das
# deutsche Original. Ohne diesen Ausgleich waechst der Rueckstand ueber
# die Predigt hinweg, unabhaengig davon wie schnell die Karte ist.
LIVE_TEMPO = 1.24

# Zielspitze fuer die Sprachausgabe. Die Piper-Stimmen sind
# unterschiedlich laut aufgenommen; im Gottesdienst fiel die persische als
# deutlich zu leise auf. Jede Ausgabe wird auf diesen Wert gebracht, damit
# alle Sprachen gleich gut zu hoeren sind.
LIVE_LAUTSTAERKE = 0.85

# Adresse fuer Rueckmeldungen zum Programm selbst, nicht fuer Meldungen
# waehrend des Gottesdienstes: die gehen ans Pult. Hier landet, was
# jemandem an der Uebersetzung auffaellt und was der Technik vor Ort
# nicht hilft, etwa ein wiederkehrender Uebersetzungsfehler.
# Leer lassen, dann erscheint der Knopf nicht.
RUECKMELDUNG_MAIL = "maurice.wessel@adventisten.de"

# Freiwillige Unterstuetzung. Sie geht an die Freikirche, nicht an eine
# Person: der Pastor wird ueber den Zehnten getragen, das Programm selbst
# kostet nichts. Ohne IBAN erscheint der Abschnitt gar nicht.
#
# Der Betrag ist eine Vorgabe fuer den QR-Code und laesst sich in jeder
# Banking-App vor dem Absenden aendern. Anders als bei der Gabensammlung
# im Gottesdienst ist hier eine Zahl sinnvoll: wer den Knopf drueckt,
# will etwas geben und nicht erst ueberlegen, wie viel angemessen waere.
SPENDE = {
    "name": "Freikirche der Siebenten-Tags-Adventisten",
    "iban": "DE19 2005 0550 1330 1104 44",
    "bic": "HASPDEHHXXX",
    "bank": "Hamburger Sparkasse",
    "zweck": "Spende Übersetzungsprogramm",
    "betrag": 10,
}