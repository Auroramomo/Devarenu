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

# Dieselben Sprachen auf Englisch. Gebraucht fuer die englischen
# Meldungen am Pult: "Rumänisch is switched on" ist kein englischer
# Satz, sondern ein halb uebersetzter. Wer am Pult auf Englisch
# umstellt, hat Gruende dafuer.
#
# Nur fuer Meldungen. Die Zuhoererseite nennt jede Sprache in ihrem
# EIGENEN Namen -- wer Vietnamesisch sucht, sucht "Tiếng Việt".
SPRACHNAMEN_EN = {
    "de": "German", "en": "English", "ru": "Russian",
    "fa": "Persian (Farsi)", "uk": "Ukrainian", "pl": "Polish",
    "ro": "Romanian", "es": "Spanish", "fr": "French",
    "pt": "Portuguese", "it": "Italian", "tr": "Turkish",
    "ar": "Arabic", "sw": "Swahili", "nl": "Dutch",
    "vi": "Vietnamese", "hu": "Hungarian", "cs": "Czech",
    "sr": "Serbian", "el": "Greek", "ka": "Georgian",
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

# --- Wiedergabetempo der Sprachausgabe --------------------------------
#
# Bis 0.2.10 stand hier eine einzige Zahl: LIVE_TEMPO = 1.24, ausgelegt
# auf Russisch und Persisch. Das war zu grob. Gemessen wurde je SPRACHE,
# aber mit genau EINER Stimme je Sprache -- der Sprachwert war in
# Wahrheit der Wert dieser einen Stimme. Sobald man mehrere vergleicht,
# faellt es auf:
#
#     Portugiesisch   0,97 / 1,35 / 1,34      Spannweite 0,38
#     Spanisch        0,96 / 1,22 / 1,20      Spannweite 0,26
#     zwischen den Sprachmitteln              Spannweite 0,01
#
# Die Streuung zwischen den Stimmen EINER Sprache ist groesser als die
# zwischen den Sprachen. Der Faktor gehoert also an die Stimme.
#
# Franzoesisch lag mit dem alten Globalwert um volle 24 Prozentpunkte
# zu hoch: gemessen 1,00, beschleunigt wurde auf 1,24. Das klang
# gehetzt, ohne irgendetwas zu gewinnen.
#
# Gemessen mit laengenfaktor.py --je-stimme, Einzelheiten und
# Bezugsgroesse in messungen/laengenfaktor_stimmen.json. Die Datei liegt
# im Repo, nicht unter ergebnisse/: sie ist der Beleg fuer jede Zahl
# hier, und in einem frischen Klon wuerde sie sonst fehlen. Bezug ist die
# deutsche Piper-Ausgabe desselben Satzes, NICHT die Sprechdauer des
# Predigers -- die beiden Reihen duerfen nicht gemischt werden.
TEMPO_STIMME = {
    "ar_JO-kareem-medium": 1.53,  # Arabisch
    "cs_CZ-jirka-medium": 1.46,  # Tschechisch
    "de_DE-thorsten-medium": 1.00,  # Deutsch
    "el_GR-rapunzelina-medium": 1.02,  # Griechisch
    "en_US-lessac-medium": 1.07,  # Englisch
    "es_ES-davefx-medium": 1.02,  # Spanisch
    "es_MX-ald-medium": 1.31,  # Spanisch, nicht ausgeliefert
    "es_MX-claude-high": 1.27,  # Spanisch, nicht ausgeliefert
    "fa_IR-amir-medium": 1.16,  # Persisch (Farsi)
    "fr_FR-siwis-medium": 1.04,  # Französisch
    "fr_FR-tom-medium": 1.24,  # Französisch, nicht ausgeliefert
    "hu_HU-anna-medium": 1.09,  # Ungarisch
    "it_IT-paola-medium": 1.05,  # Italienisch
    "ka_GE-natia-medium": 1.29,  # Georgisch
    "nl_NL-mls-medium": 1.63,  # Niederländisch
    "pl_PL-darkman-medium": 1.25,  # Polnisch
    "pt_BR-cadu-medium": 1.45,  # Portugiesisch, nicht ausgeliefert
    "pt_BR-faber-medium": 1.04,  # Portugiesisch
    "pt_BR-jeff-medium": 1.37,  # Portugiesisch, nicht ausgeliefert
    "ro_RO-mihai-medium": 1.23,  # Rumänisch
    "ru_RU-irina-medium": 1.22,  # Russisch
    "sr_RS-serbski_institut-medium": 1.67,  # Serbisch
    "sw_CD-lanfrica-medium": 1.09,  # Suaheli
    "tr_TR-dfki-medium": 1.13,  # Türkisch
    "uk_UA-ukrainian_tts-medium": 1.05,  # Ukrainisch
    "vi_VN-vais1000-medium": 0.99,  # Vietnamesisch
}

# Rueckfall je Sprache, falls eine andere Stimme eingesetzt wird als die
# gemessene. Grob, aber besser als die Vorgabe.
TEMPO_SPRACHE = {
    "ar": 1.53,   # Arabisch
    "cs": 1.46,   # Tschechisch
    "de": 1.00,   # Deutsch
    "el": 1.02,   # Griechisch
    "en": 1.07,   # Englisch
    "es": 1.02,   # Spanisch
    "fa": 1.16,   # Persisch (Farsi)
    "fr": 1.04,   # Französisch
    "hu": 1.09,   # Ungarisch
    "it": 1.05,   # Italienisch
    "ka": 1.29,   # Georgisch
    "nl": 1.63,   # Niederländisch
    "pl": 1.25,   # Polnisch
    "pt": 1.04,   # Portugiesisch
    "ro": 1.23,   # Rumänisch
    "ru": 1.22,   # Russisch
    "sr": 1.67,   # Serbisch
    "sw": 1.09,   # Suaheli
    "tr": 1.13,   # Türkisch
    "uk": 1.05,   # Ukrainisch
    "vi": 0.99,   # Vietnamesisch
}

# Rueckfall des Rueckfalls: eine Stimme, die niemand gemessen hat. Liegt
# unter dem alten Globalwert und ueber der Mehrheit der gemessenen --
# falsch also in beide Richtungen nur um wenige Prozentpunkte.
TEMPO_VORGABE = 1.15

# Puffer fuer schnelle Redner.
#
# Der Laengenfaktor misst eine Eigenschaft der STIMME an einem festen
# Text. Ein schnellerer Prediger aendert nicht diesen Faktor, sondern
# die verfuegbare Zeit -- dafuer ist der Aufschlag da.
#
# Sechs Prozent, und zwar begruendet: die Messreihe 0.2.5 legt den
# Kipppunkt der Verstaendlichkeit bei Sprechtempo rund 1,6. Die
# langsamste gemessene Stimme liegt bei 1,20; 1,20 x 1,06 = 1,27 und
# damit klar darunter. Zehn Prozent brachten sie auf 1,32 und
# bezahlten Verstaendlichkeit fuer Reserve, die die Messung nicht
# verlangt. Unter fuenf Prozent waere der Aufschlag kleiner als das
# Rauschen des Verfahrens und damit keine Reserve, sondern Zufall.
TEMPO_AUFSCHLAG = 1.06

# Der Notfallhebel: hebt oder senkt alles auf einmal. Vorgabe 1.0,
# also wirkungslos. Gedacht fuer den Sonntag, an dem die Uebersetzung
# durchgehend hinterherhaengt und niemand Zeit hat, einzelne Stimmen
# nachzumessen.
TEMPO_GLOBAL = 1.0

# Grenzen. Unter 1,0 zu bremsen bringt nichts: eine Stimme, die ohnehin
# kuerzer ist als das Original, hat keinen Rueckstand aufzuholen, und
# langsamer gesprochen klingt sie schlaff. Ueber 1,6 faellt die
# Verstaendlichkeit -- gemessen in 0.2.5.
TEMPO_MIN = 1.0
TEMPO_MAX = 1.6

# Zielspitze fuer die Sprachausgabe. Die Piper-Stimmen sind
# unterschiedlich laut aufgenommen; im Gottesdienst fiel die persische als
# deutlich zu leise auf. Jede Ausgabe wird auf diesen Wert gebracht, damit
# alle Sprachen gleich gut zu hoeren sind.
LIVE_LAUTSTAERKE = 0.85

# Notbremse der Betriebsart "satz".
#
# "satz" sammelt Abschnitte, bis ein Satzzeichen kommt. Dagegen stehen
# zwei Bremsen: eine Hoechstzahl an Woertern und MAX_WARTEN Sekunden.
# Die Wartezeit wurde aber nur geprueft, wenn ein NEUER Abschnitt
# eintraf -- und genau dann nicht, wenn der Prediger mitten im Satz
# schweigt. Gemessen am 21.09.2026: nach "Und er fuehrte ihn hinaus und
# sprach," lagen 17,9 Sekunden Stille, die Bremse sah nie auf die Uhr,
# und der Zuhoerer bekam 19,3 Sekunden nichts.
#
# Mit diesem Schalter laeuft die Frist unabhaengig davon ab, ob etwas
# ankommt: was dasteht, geht raus. Der Satz bleibt dann unvollstaendig
# -- aber er kommt, und das ist der Fall, fuer den die Bremse gedacht
# war.
#
# Wirkt nur in "satz". Die Vorgabe ist "kontext", dort sammelt niemand.
SATZ_NOTBREMSE = True

# Wie lange ein angefangener Satz hoechstens liegen darf, in Sekunden.
#
# Hier und nicht nur auf der Kommandozeile, weil es pro Gemeinde
# verschieden ist: es haengt daran, wie der Prediger spricht. Wer lange
# rhetorische Pausen macht, braucht eine kurze Frist -- sonst wartet der
# Zuhoerer sie mit aus, ohne zu wissen, worauf.
#
# Gemessen auf ausschnitt.mp3 am 21.09.2026, siehe LIESMICH. Kuerzer
# heisst: weniger Wartezeit, dafuer mehr Saetze, die doch in zwei
# Stuecken ankommen. Laenger heisst das Gegenteil.
#
# --max-warten auf der Kommandozeile schlaegt diesen Wert.
SATZ_MAX_WARTEN = 4.0

# --- Der Rechner als Router (aus, bis vor Ort umgebaut) ----------------
# Handys meiden ein WLAN ohne Internet. iOS prueft ueber HTTP, Android
# ueber HTTP und HTTPS. Wer die HTTP-Pruefung beantwortet, gilt bei iOS
# als online; bei Android bleibt das Ausrufezeichen, weil die
# HTTPS-Pruefung ohne Zertifikat nicht zu bestehen ist.
#
# Alles hier ist AUS. Ein Rechner ohne den Umbau verhaelt sich wie
# bisher: er sucht seine Adresse, laeuft auf Port 8000, und keine
# Pruefadresse wird beantwortet. Eingeschaltet wird das von Hand vor
# Ort, mit ./netz_einrichten.sh -- nie ueber ein Update.
# Ob dieser Rechner der Router ist, steht NICHT hier, sondern in
# netz.json -- einer Datei, die nicht im Repo liegt.
#
# Bis 0.2.11 schrieb netz_einrichten.sh "NETZ_ROUTER = True" in genau
# diese Datei. Damit galt der Ordner als veraendert, und jedes Update
# brach ab: stick_update.sh und aktualisieren.sh schreiben nicht ueber
# lokale Aenderungen hinweg. Der Gemeinderechner stand daran fest.
#
# Kein Skript schreibt mehr in eine versionierte Datei. config.py
# enthaelt Vorgaben; was diesen einen Rechner ausmacht, steht daneben:
#
#   netz.json     Router ja/nein, Adresse, Schnittstelle, Erlaubnisliste
#   zustand.json  was am Pult eingestellt wurde
#
# Gelesen wird beides ueber netzzustand.py beziehungsweise zustand.py.
# Fehlt netz.json, sieht netzzustand.py am System nach, ob der Umbau
# laeuft, und legt sie an.

# Die feste Adresse des Rechners im Gemeindenetz. Gilt nur, wenn
# NETZ_ROUTER an ist; sonst wird sie wie bisher gesucht.
NETZ_ADRESSE = "10.0.0.1"
NETZ_MASKE = 24
NETZ_BEREICH = ("10.0.0.50", "10.0.0.200")
NETZ_MIETE = "12h"

# Zusaetzlich auf Port 80 hoeren. Ein Handy tippt "10.0.0.1" ohne Port,
# und die Pruefadressen der Hersteller fragen ausschliesslich Port 80.
# Der Server bleibt dabei ein gewoehnlicher Benutzerprozess -- die Unit
# gibt ihm CAP_NET_BIND_SERVICE. Geht es nicht, laeuft er auf 8000
# weiter und sagt es.
NETZ_PORT_80 = True

# Welche Namen auf diesen Rechner zeigen. ALLES ANDERE bleibt
# unaufloesbar (NXDOMAIN).
#
# Bewusst eine Liste und kein Platzhalter fuer alle Namen: ein
# Platzhalter kapert den ganzen Namensraum fuer jedes Handy im Saal,
# auch fuer die, die gar nicht mithoeren. Mailprogramme und Messenger
# bekaemen dann einen Server, der nicht antwortet, und wiederholten
# ihre Anfragen, bis der Akku leer ist. NXDOMAIN ist die ehrliche
# Auskunft: hier gibt es kein Internet.
#
# www.google.com steht bewusst NICHT hier. Ueber diesen Namen redet ein
# Handy staendig im Hintergrund; er gehoert nicht auf unseren Server.
PRUEFDOMAENEN = [
    # Android
    "connectivitycheck.gstatic.com",
    "clients3.google.com",
    "connectivitycheck.android.com",
    "play.googleapis.com",
    # Apple. Die unteren fuenf sind die alten Namen, die iOS beim
    # ERSTEN Verbinden mit einem unbekannten Netz noch abfragt. Fehlen
    # sie, laeuft das iPhone dort in Zeitueberschreitungen -- und genau
    # das war im Saal als "das neue iPhone braucht ewig" zu sehen.
    "captive.apple.com",
    "www.apple.com",
    "www.appleiphonecell.com",
    "www.itools.info",
    "www.ibook.info",
    "www.airport.us",
    "www.thinkdifferent.us",
    # Windows
    "www.msftconnecttest.com",
    "www.msftncsi.com",
    "dns.msftncsi.com",
    # Firefox
    "detectportal.firefox.com",
]

# Captive Portal API, RFC 8910 (DHCP-Option 114) und RFC 8908 (die
# Antwort). Das Netz sagt den Geraeten damit ausdruecklich, dass keine
# Anmeldung noetig ist.
#
# Unsicher, ob es die Anzeige "Kein Internet" beeinflusst: der Standard
# regelt Anmeldepflicht, nicht Erreichbarkeit. Er widerspricht den
# Pruefadressen aber nicht, und iOS ab 14 fragt Option 114 an.
NETZ_CAPTIVE_API = True

# --- Messung (Fehlersuche, kein Betrieb) -------------------------------
# Alles hier ist AUS und muss aus bleiben. Auf dem Gemeinde-PC schreibt
# sonst jeder Gottesdienst Dateien, die niemand ansieht -- und der Rechner
# steht in einem Schrank, in dem niemand aufraeumt.
#
# Eingeschaltet wird fuer einen Messlauf von Hand, gemessen wird gegen
# eine Datei (--datei), nicht gegen den Saal. Danach wieder aus.

# Schreibt je Segment und Zielsprache eine Zeile nach
# ERGEBNIS_ORDNER/messung/<zeitstempel>/segmente.csv.
MESSUNG = False

# Nimmt zusaetzlich die Wiedergabe auf den Handys entgegen. Nur sinnvoll
# zusammen mit MESSUNG, und nur mit ?debug=1 auf der Zuhoererseite.
#
# Getrennt schaltbar, weil es das einzige Stueck ist, das im Livebetrieb
# neu schiefgehen kann: ein offener Endpunkt, den jeder ansprechen kann,
# der die Seite erreicht. Steht er auf False, gibt es ihn nicht -- der
# Server antwortet 404 und liest den Rumpf gar nicht erst.
MESSUNG_WIEDERGABE = False

# Obergrenze fuer den Rumpf einer Wiedergabe-Meldung, in Bytes. Ein Handy
# schickt je Buendel wenige Dutzend Zeilen; alles darueber ist keine
# Messung mehr. Wird verworfen, bevor irgendetwas geparst wird.
MESSUNG_RUMPF_MAX = 64 * 1024

# Adresse fuer Rueckmeldungen zum Programm selbst, nicht fuer Meldungen
# waehrend des Gottesdienstes: die gehen ans Pult. Hier landet, was
# jemandem an der Uebersetzung auffaellt und was der Technik vor Ort
# nicht hilft, etwa ein wiederkehrender Uebersetzungsfehler.
# Leer lassen, dann erscheint der Knopf nicht.
def _betreuer():
    """Name und Adresse des Betreuers, aus betreuer.txt.

    An EINER Stelle im Repo, damit sie nicht an fuenf Orten
    auseinanderlaufen -- und damit oeffentlich_pruefen.sh genau eine
    erlaubte Fundstelle hat."""
    werte = {"name": "", "mail": ""}
    try:
        for zeile in (BASIS / "betreuer.txt").read_text(
                encoding="utf-8").splitlines():
            zeile = zeile.strip()
            if not zeile or zeile.startswith("#") or "=" not in zeile:
                continue
            k, v = zeile.split("=", 1)
            if k.strip() in werte:
                werte[k.strip()] = v.strip()
    except OSError:
        pass
    return werte


BETREUER = _betreuer()
BETREUER_NAME = BETREUER["name"]

# Der alte Name bleibt: er wird an mehreren Stellen gelesen, und eine
# Umbenennung waere Arbeit ohne Gewinn.
RUECKMELDUNG_MAIL = BETREUER["mail"]

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