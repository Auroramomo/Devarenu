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

# Die AKTIVE Glossarfassung. v0.5 bis v0.8 sind Arbeitsstaende: dort
# wurden es, pt, hr, fr und pl aufgebaut, waehrend im Betrieb weiter
# v0.4 lief. In den Spalten, die v0.4 hat, sind alle fuenf Zeichen fuer
# Zeichen gleich -- en, ru und fa haben also nie von einem Arbeitsstand
# etwas abbekommen.
#
# v0.9 ist die erste, die aktiv wird: sie traegt die Rueckmeldungen der
# spanischen und portugiesischen Pruefer. Nachgewiesen vor dem
# Umschalten, mit werkzeuge/glossar_vergleich.py ueber 1444 Texte:
# en, ru, fa und der Whisper-Prompt kommen Zeichen fuer Zeichen gleich
# heraus.
#
# v1.2 (0.5.0) bringt Ukrainisch: die Pruefauswahl vom Muttersprachler,
# die Bibelbuecher aus Ohienko, der Rest maschinell -- Einzelheiten in
# werkzeuge/glossar_rueck_uk.py. Vergleichslauf gegen v1.1 ueber 1498
# Texte: en, ru, fa, es, pt, pl, fr, hr und der Whisper-Prompt
# unveraendert.
GLOSSAR_CSV = BASIS / "glossar_v1.2.csv"
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

# Was VOR dem Sprechen im Text ersetzt wird, je Sprache.
#
# Der Untertitel bleibt unberuehrt -- ersetzt wird nur, was an Piper
# geht. Beides auseinanderzuhalten ist der ganze Zweck: geschrieben
# gehoert "Elena G. de White", gesprochen gehoert das Initial nicht.
#
# Piper liest ein einzelnes "G." als Buchstaben vor, auf Spanisch
# also "ge". Mitten in einem Namen klingt das wie ein Versprecher,
# und der Pruefer hat es angemerkt. Weglassen ist die uebliche
# Sprechweise: im Spanischen heisst sie "Elena de White".
#
# HIER STEHEN NUR SPRACHEN, DIE ES BRAUCHEN. Fuer de, en, ru und fa
# steht nichts, und es aendert sich nichts.
# Zahl:Zahl -> Zahl,Zahl. Fuer Bibelstellen wie "Johannes 3:16".
#
# Der Doppelpunkt wird NICHT gesprochen -- der espeak-Phonemisierer
# macht daraus keine Woerter --, aber er ist ein Pausenzeichen. Ob
# das Zeit kostet oder spart, haengt an der Sprache UND an der
# Schreibweise, und das ist der ganze Witz dieser Messung.
#
# ERSTER ANLAUF, UND WARUM ER FALSCH WAR
#
# Gemessen wurde zuerst "53, 5" gegen "53: 5" -- beide MIT Leerzeichen
# nach dem Trennzeichen. Danach kostete der Doppelpunkt ueberall
# Zeit: ru +0,33 s, fa +0,18 s, en +0,06 s.
#
# Nur schreibt das Modell gar keine Leerzeichen. Es schreibt "53:5",
# und in dieser Form ist der Doppelpunkt etwas voellig anderes:
#
#   Исаия 53:5    1,68 s      Исаия 53 5    1,68 s
#   Исаия 53,5    2,12 s      Исаия 53: 5   2,68 s
#
# Ohne Leerzeichen behandelt espeak "53:5" wie "53 5" -- gar keine
# Pause. Das KOMMA macht dort eine. Der erste Anlauf hat also die
# Frage beantwortet, die niemand gestellt hatte.
#
# ZWEITER ANLAUF, AUF DEN ECHTEN MODELLAUSGABEN
#
# Dieselben Saetze, die in messungen/bibelstellen_trenner.json unter
# "vorher" stehen -- also das, was gemma4:12b wirklich schreibt --,
# einmal so und einmal mit Komma statt Doppelpunkt:
#
#   Sprache  Saetze  Median     Summe    Ergebnis
#   en          7    +0,00 s   -0,73 s   an der Schwelle
#   ru          5    +0,57 s   +3,08 s   das Komma KOSTET
#   fa          4    -0,47 s   -1,79 s   das Komma spart
#
# Also nur Persisch. Russisch waere eine Verschlechterung gewesen,
# und bei Englisch aendert sich in der Haelfte der Saetze gar nichts.
#
# Persische Ziffern (۵۳) und lateinische (53) verhalten sich gleich,
# ebenso das arabische Komma und das lateinische -- auf die
# Millisekunde, espeak normalisiert beides. Das Muster deckt trotzdem
# alle drei Ziffernreihen ab: darauf zu bauen, dass die
# Normalisierung so bleibt, waere eine Wette.
#
# WAS DAS MUSTER SONST NOCH TRIFFT: eine Uhrzeit, "18:30". Auch dort
# wird der Doppelpunkt nicht gesprochen, und es entstehen keine
# falschen Woerter -- nur eine andere Pause. Hingenommen. Ein
# Doppelpunkt nach einem Wort ("Er sagte: Kommt her") passt nicht
# auf Zahl:Zahl und bleibt unberuehrt.
#
# OHNE Leerzeichen ersetzt. Mit waere es langsamer als vorher.
_ZIFFER = r"[0-9\u0660-\u0669\u06F0-\u06F9]"
_STELLE_ZU_KOMMA = (rf"({_ZIFFER})\s*:\s*({_ZIFFER})", r"\1,\2")

# TWI (0.5.0). Die Stimme ist ein Zeichenmodell aus Coqui, umgewandelt
# fuer Piper (werkzeuge/twi_stimme.py). Coqui hat den Text vor dem
# Training so bereinigt (multilingual_cleaners): ";" und ":" zu ",",
# "-" zu Leerzeichen, <>()[]" weg, Weissraum zusammengezogen. Genau das
# passiert hier, damit die Stimme bekommt, was sie kennt.
#
# Kleinbuchstaben braucht es hier NICHT: die .onnx.json bildet Ɛ auf
# dieselbe Nummer ab wie ɛ, Ɔ wie ɔ.
#
# Was die Stimme gar nicht kennt, faellt vorher weg -- vor allem
# Ziffern und typografische Anfuehrungszeichen. Piper wuerde sie
# ebenfalls weglassen, aber fuer JEDES Zeichen eine Warnung ins Journal
# schreiben. Ziffern spricht die Twi-Stimme also nicht: "Dwom 23:1" wird
# "Dwom ,". Im Untertitel steht die Zahl; gesprochen fehlt sie.
_TWI_KENNT = ("!',.?—…abcdefghijklmnoprstuvwxyz"
              "ABCDEFGHIJKLMNOPRSTUVWXYZ"
              "àáãèéìíòóõùúāăĩńŋũūƒƙǹɓɔɖɗɛɣʋṣẹẽọ"
              "ÀÁÃÈÉÌÍÒÓÕÙÚĀĂĨŃŊŨŪƑƘǸƁƆƉƊƐƔƲṢẸẼỌ"
              "̀́̃ ")
_TWI = [(r"[’ʼ‘]", "'"),
        (r"[;:]", ","),
        (r"-", " "),
        (r'[<>()\[\]"]', ""),
        (r"[^" + _TWI_KENNT + r"]", " "),
        (r"\s+", " "),
        (r"^ | $", "")]

SPRECHFORM = {
    "tw": _TWI,
    "fa": [_STELLE_ZU_KOMMA],
    "es": [(r"\bElena\s+G\.\s+de\s+White\b", "Elena de White"),
           (r"\bEllen\s+G\.\s+White\b", "Elena de White")],
    "pt": [(r"\bEllen\s+G\.\s+White\b", "Ellen White")],
}

# Zusaetzliche Pause an Kommas, in Millisekunden -- je Stimme.
#
# Der Pruefer zu pt_BR-jeff-medium: "Kommapausen zu kurz". Piper 1.7
# kennt dafuer keine Einstellung; SynthesisConfig hat nur
# length_scale, noise_scale, noise_w_scale und volume. Die Pause
# entsteht deshalb NACH der Synthese: der Satz wird an den Kommas
# geteilt, jedes Stueck einzeln gesprochen, und dazwischen kommt
# Stille.
#
# HIER STEHEN NUR STIMMEN, DIE ES BRAUCHEN. Fehlt eine, laeuft die
# Synthese genau wie bisher -- ein Stueck, ein Aufruf. Fuer die vier
# Sprachen in Rostock steht hier nichts, und es aendert sich nichts.
#
# Kosten: ein Piper-Aufruf je Teilsatz statt einem je Satz.
PAUSE_KOMMA_MS = {
    "pt_BR-jeff-medium": 180,
}

# Wer in einer Mehrsprecher-Stimme spricht, beim Namen aus der
# .onnx.json (speaker_id_map). Ohne Eintrag spricht Sprecher 0 -- so
# war es immer, und fuer jede ausgelieferte Stimme bleibt es so.
#
# uk_UA-ukrainian_tts-medium hat drei: lada (0), mykyta (1), tetiana
# (2). Bis 0.4.6 sprach dort lada, ohne dass es jemand gewaehlt hatte.
# Der Eintrag wirkt erst, wenn STIMMEN["uk"] auf diese Stimme zeigt
# (siehe dort) -- heute spricht uk_UA-mykyta-high, eine eigene Stimme.
STIMM_SPRECHER = {
    "uk_UA-ukrainian_tts-medium": "mykyta",
}

# Wie eine Bibelstelle zwischen Kapitel und Vers getrennt wird.
#
# GEMESSEN, mit gemma4:12b, acht deutschen Saetzen mit Bibelstellen,
# temperature 0.1, seed 7, ohne jede Anweisung:
#
#   Sprache  was das Modell schreibt   ueblich
#   de       ,   (Ausgangssprache)     ,   Luther, Elberfelder: Joh 3,16
#   en       :   7 von 7               :   KJV, NIV: John 3:16
#   ru       :   5 von 7, sonst ,      :   Synodale: Иоанна 3:16
#   fa       :   4 von 4               :
#   es       ,   7 von 7   FALSCH      :   Reina-Valera: Juan 3:16
#   pt       ,   7 von 7   FALSCH      :   Almeida: Joao 3:16
#
# Die Anweisung fuer es und pt wirkt (7 von 7 auf Doppelpunkt), und
# der Vergleichslauf zeigte de, en, ru und fa Zeile fuer Zeile
# identisch. Belege in messungen/bibelstellen_trenner.json.
#
# IN 0.3.6 WAR SIE KURZ DRAUSSEN, AUS EINEM FALSCHEN GRUND.
#
# Gemessen worden war "53, 5" gegen "53: 5" -- beide MIT Leerzeichen
# nach dem Trennzeichen. Danach schien der Doppelpunkt bei Piper
# teurer zu sein, und die Anweisung wurde verworfen.
#
# Nur schreibt das Modell keine Leerzeichen. Es schreibt "53:5", und
# in dieser Form ist der Doppelpunkt etwas anderes: espeak behandelt
# ihn wie ein Leerzeichen, also gar keine Pause. Das KOMMA macht
# dort eine. Nachgemessen auf den echten Modellausgaben, mit den
# gewaehlten Stimmen, Doppelpunkt gegen Komma:
#
#   es  es_MX-claude-high   7 Saetze  Median +0,27 s  Summe +2,09 s
#   pt  pt_BR-jeff-medium   7 Saetze  Median +0,29 s  Summe +2,10 s
#
# Das Komma kostet also Zeit, nicht der Doppelpunkt. Die Entscheidung
# von 0.3.6 beruhte auf einer Messung, die eine Frage beantwortete,
# die niemand gestellt hatte -- und ist seit 0.3.7 zurueckgenommen.
#
# ENGLISCH UND RUSSISCH KAMEN MIT 0.4.2 DAZU.
#
# Sie standen bis dahin nicht hier, und das war aus zwei Gruenden
# halb richtig und halb falsch:
#
#   richtig  Das Modell schreibt in beiden Sprachen ohnehin meist
#            einen Doppelpunkt -- gemessen en 7 von 7, ru 5 von 7
#            (messungen/bibelstellen_trenner.json). Eine Anweisung
#            war dafuer nicht noetig.
#   falsch   Die Umrechnung aus 0.4.0 gab die fertige Zielangabe vor,
#            und ohne Eintrag hier galt dabei das deutsche Komma.
#            Im Prompt stand dann "Joel 2,28", waehrend das Modell
#            nebenan "Joel 2:28" schrieb. Zwei Schreibweisen in
#            demselben Prompt sind eine Einladung, die falsche zu
#            nehmen -- und bei den 2 von 7 russischen Faellen mit
#            Komma war genau das zu sehen.
#
# Englisch: "John 3:16" ist die Schreibweise jeder englischen Bibel.
# Russisch: die Synodaluebersetzung schreibt "Ин. 3:16", Doppelpunkt
# zwischen Kapitel und Vers -- so auf azbyka.ru, bible.by und in der
# Uebersicht der russischen Wikipedia zu den Buchabkuerzungen. Die
# Messung passt dazu.
#
# Die uebrigen Sprachen sind NICHT geprueft. Wer eine dazunimmt,
# misst erst und traegt dann ein.
#
# UKRAINISCH, gemessen mit 0.5.0 auf denselben acht Saetzen: gemma4:12b
# schreibt 7 von 7 Mal ein Komma ("Ісаї 53, 5"). Welche Schreibweise
# ukrainische Gemeinden erwarten, ist hier nicht belegt -- also keine
# Anweisung, und die umgerechnete Angabe (Joel 3,1 -> Йоїл 2,28) kommt
# mit Komma, wie das Modell es ohnehin schreibt. Ergebnis in
# messungen/bibelstellen_trenner.json unter "nachtrag_0_5_0".
#
# TWI, ebenfalls 0.5.0: Doppelpunkt 6 von 6 ("Yohanna 3:16"), ohne
# Anweisung -- wie Englisch, dessen Zaehlung Twi folgt. Eingetragen aus
# demselben Grund wie en und ru: sonst kaeme die umgerechnete Angabe
# ("Yoɛl 2:28") mit dem deutschen Komma in den Prompt.
STELLEN_TRENNER = {
    "en": ":",
    "es": ":",
    "pt": ":",
    "ru": ":",
    "tw": ":",
}

# Sprachen, bei denen eine Wiederholungsschleife des Sprachmodells
# gekappt wird. gemma4:12b laeuft auf Twi in 7 von 20 Pruefsaetzen in
# eine Schleife ("honnim honnim honnim ..." bis zur Laengengrenze) --
# auf dem Handy eine Seite voll derselben Silbe, und die Stimme spricht
# sie eine Minute lang. Gekappt wird, wo sich ein Wort oder eine
# Gruppe von bis zu sechs Woertern mindestens viermal direkt
# wiederholt; stehen bleibt das erste Vorkommen.
#
# NUR fuer die hier genannten. In en, ru und fa ist das nie aufgetreten,
# und dort soll kein neuer Filter zwischen Modell und Zuhoerer stehen.
SCHLEIFE_KAPPEN = {"tw"}

# Bekannte Fehlformen (Nachtrag zu 0.5.0): Woerter, die in der
# Uebersetzung NICHT stehen duerfen, wenn im Abschnitt ein bestimmter
# Glossarbegriff vorkommt -- obwohl das Glossar die richtige Form
# vorgibt, nimmt das Modell manchmal die falsche.
#
# Trifft die Kontrolle, wird der Abschnitt EINMAL neu uebersetzt, mit
# einem ausdruecklichen Hinweis im Prompt. Trifft sie wieder, geht die
# Uebersetzung trotzdem hinaus und die Fehlform ins Journal (nur das
# Wort, nicht der Satz). Ersetzt wird NIE: ein eingesetztes Wort passt
# selten in Fall und Satzbau, und ein kaputter Satz ist schlimmer als
# ein falsches Wort.
#
# Kosten im Normalfall: nichts. Geprueft wird nur, wenn der
# Glossarbegriff im Abschnitt steht (die Glossarsuche laeuft ohnehin),
# und dann ein regulaerer Ausdruck ueber die Ausgabe.
#
# Je Sprache eine Liste:
#   glossar   Kennung im Glossar; die richtige Form steht dort
#   fehlform  regulaerer Ausdruck, ohne Gross-/Kleinschreibung,
#             auf den Wortanfang -- erfasst alle Beugungen
#   falsch    wie die Fehlform heisst, fuer Hinweis und Journal
#   grund     warum sie falsch ist, fuer den Hinweis an das Modell
#   formen    (frei) die richtige Form gebeugt, mit dem Fall benannt,
#             fuer den Hinweis. Ohne sie trifft das Modell beim zweiten
#             Versuch zwar das Wort, aber nicht die Endung (F04:
#             "Вечерєю Господнію"); mit Formen, aber ohne Fall, noch
#             immer nicht die Schreibung ("Вечерєю Господньою").
#             Mehrere Regeln zum selben Glossarbegriff nennen sie
#             im Hinweis nur einmal.
_ABENDMAHL_UK = (
    "Nominativ Вечеря Господня; Genitiv Вечері Господньої; Dativ Вечері "
    "Господній; Akkusativ Вечерю Господню; Instrumental Вечерею "
    "Господньою -- so nach „перед“, „з“, „над“, also zum Beispiel "
    "„Перед Вечерею Господньою“. Geschrieben mit е, nie mit є.")
FEHLFORMEN = {
    "uk": [
        # Belegt: pruefung/fallstricke_uk.csv F04, gemma4:12b schrieb
        # "Перед Вечернею ми відзначаємо обмивання ніг." Вечірня und
        # Вечерня (alle Faelle: -ня, -ні, -ню, -ньою, -нею) sind die
        # Vesper, ein Abendgottesdienst. Вечеря Господня trifft der
        # Ausdruck nicht: "вечер" + я/і/ю/ею, nie "вечерн".
        {"glossar": "C041",
         "fehlform": r"\bвеч[еі]рн",
         "falsch": "Вечірня/Вечерня",
         "grund": "das heisst Vesper, ein Abendgottesdienst, nicht "
                  "Abendmahl",
         "formen": _ABENDMAHL_UK},
        # Belegt: derselbe Satz im zweiten Versuch, "Перед Вечерєю
        # Господньою". Kein ukrainisches Wort -- nach р steht hier е.
        {"glossar": "C041",
         "fehlform": r"\bвечерє",
         "falsch": "Вечерє…",
         "grund": "das ist falsch geschrieben, es heisst Вечерею, "
                  "Вечері, Вечерю",
         "formen": _ABENDMAHL_UK},
    ],
}

# ----------------------------------------------------------------- Anrede
#
# Spanisch und Portugiesisch muessen bei jedem "ihr" und jedem "du"
# entscheiden, welche Form gemeint ist -- und das Sprachmodell entscheidet
# es sonst in jedem Abschnitt neu. In einer Predigt faellt das auf: die
# Gemeinde wird in einem Satz geduzt, im naechsten gesiezt, und Gott
# wechselt mit.
#
# Festgelegt wird die Form, die die gebrauchten Bibeluebersetzungen
# verwenden:
#
#   es  Reina-Valera redet Gott mit "tú" an. Die Gemeinde als Mehrzahl
#       ist in Lateinamerika "ustedes"; "vosotros" ist dort ausgestorben
#       und klingt wie Kirchensprache aus dem 19. Jahrhundert.
#   pt  Almeida redet Gott mit "tu" an. Die Gemeinde als Mehrzahl ist im
#       brasilianischen Portugiesisch "voces".
#
# Dass die eine Form fuer Gott die vertrauliche ist und die andere fuer
# die Gemeinde die hoefliche, ist kein Widerspruch, sondern genau die
# Verteilung, die in beiden Uebersetzungen steht.
#
# Keine Sprache ohne Eintrag bekommt eine Vorgabe. Fuer Englisch,
# Russisch und Persisch wuerde sie nichts entscheiden (en) oder waere
# ungeprueft (ru, fa).
ANREDE = {
    "es": ("Die Gemeinde wird mit „ustedes“ angeredet, nie mit "
           "„vosotros“. Gott wird mit „tú“ angeredet, wie in der "
           "Reina-Valera."),
    "pt": ("Die Gemeinde wird mit „vocês“ angeredet. Gott wird mit "
           "„tu“ angeredet, wie in der Almeida."),
}

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
    # Seit 0.5.0. NUR Asante-Twi -- nicht Akuapem, nicht Fante. Der
    # Name geht so in den Uebersetzungsprompt ("nach Twi (Asante)"),
    # und die Stimme ist auf der Asante-Bibel trainiert.
    "tw": "Twi (Asante)",
}

# Sprachen, die Whisper nicht kennt. Sie sind Zielsprache, nie
# Ausgangssprache: als Predigtsprache gewaehlt, scheiterte die
# Erkennung an jedem Abschnitt ("'tw' is not a valid language code").
# Das Pult bietet sie darum nicht als Quelle an, und der Server nimmt
# sie dort nicht an.
NUR_ZIEL = {"tw"}

# Versuchssprachen (Nachtrag zu 0.5.0): Sprachen, die im Programm
# stehen, mit Stimme und Code, die das Uebersetzungsmodell aber nicht
# gut genug kann, um damit einen Gottesdienst zu bestreiten. gemma4:12b
# liefert in Twi Wiederholungsschleifen und erfundene Woerter (die Probe
# zu 0.5.0); gemma4:26b waere besser, passt aber neben Whisper nicht in
# 16 GB Grafikspeicher.
#
# Sie erscheinen weder am Pult in der Sprachauswahl noch auf der
# Hoererseite, solange der Schalter "Versuchssprachen" aus ist
# (zustand.json, Feld "versuchssprachen", Vorgabe aus). Der Schalter
# steht am Pult unter Einrichtung -> Fehlersuche -> Erweitert. Ist eine
# davon schon eingeschaltet, bleibt sie es; der Systemcheck sagt es.
VERSUCHSSPRACHEN = {"tw"}

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
    "tw": "Twi (Asante)",
}

# Sprachen, deren Fachwortverzeichnis ein Muttersprachler durchgesehen
# hat. Alle uebrigen laufen technisch genauso, aber ihre Terminologie ist
# maschinell erzeugt und ungeprueft. Bei Persisch hat die Pruefung acht
# von 54 Eintraegen korrigiert, darunter einen, der theologisch ins
# Gegenteil ging. Diesen Unterschied sollen die Zuhoerer sehen koennen.
#
# es und pt kamen mit 0.4.0 dazu. Je ein Muttersprachler hat die 72
# Begriffe durchgesehen und dazu rund 80 weitere beigetragen; die
# Entscheidungen stehen in werkzeuge/glossar_rueck_es_pt.py, jede mit
# Begruendung. Eingeschaltet wird dadurch nichts: ZIELSPRACHEN bleibt
# en, ru, fa, und eine Gemeinde waehlt am Pult.
#
# uk kam mit 0.5.0 dazu: die 93 Begriffe der Pruefauswahl, eine
# Korrektur, ein Hinweis. Siehe werkzeuge/glossar_rueck_uk.py.
GEPRUEFT = {"de", "en", "ru", "fa", "es", "pt", "uk"}

# Piper-Stimmen je Sprache, so wie sie im Repo rhasspy/piper-voices liegen.
# Was hier steht, kann einrichten.sh herunterladen; was fehlt, laeuft als
# reiner Untertitel weiter.
STIMMEN = {
    "de": "de/de_DE/thorsten/medium/de_DE-thorsten-medium",
    "en": "en/en_US/lessac/medium/en_US-lessac-medium",
    "ru": "ru/ru_RU/irina/medium/ru_RU-irina-medium",
    "fa": "fa/fa_IR/amir/medium/fa_IR-amir-medium",
    # Seit 0.5.0 mykyta (high) statt ukrainian_tts (medium). Die alte
    # Datei bleibt auf Rechnern, die sie haben -- Devarenu loescht keine
    # Stimmen. Lizenz und Messung: LIZENZEN.md, TEMPO_STIMME unten.
    #
    # Zurueck auf die alte Stimme, aber mit dem Sprecher mykyta
    # (Hoerprobe c, Nachtrag zu 0.5.0) -- EINE Aenderung, diese Zeile:
    #   "uk": "uk/uk_UA/ukrainian_tts/medium/uk_UA-ukrainian_tts-medium",
    # Sprecher und Tempo stehen schon bereit (STIMM_SPRECHER und
    # TEMPO_STIMME). Siehe LIZENZEN.md zur Lizenz dieser Stimme.
    "uk": "uk/uk_UA/mykyta/high/uk_UA-mykyta-high",
    "pl": "pl/pl_PL/darkman/medium/pl_PL-darkman-medium",
    "ro": "ro/ro_RO/mihai/medium/ro_RO-mihai-medium",
    # Vom Pruefer gewaehlt: Stimme B aus pruefung/paket_es.
    # A war es_ES-davefx-medium (1.025), B es_MX-claude-high (1.268),
    # C es_MX-ald-medium (1.306) -- sortiert nach gemessenem Faktor,
    # so baut werkzeuge/sprachpaket.py die Buchstaben.
    "es": "es/es_MX/claude/high/es_MX-claude-high",
    "fr": "fr/fr_FR/siwis/medium/fr_FR-siwis-medium",
    # Vom Pruefer gewaehlt: Stimme B aus pruefung/paket_pt.
    # A war pt_BR-faber-medium (1.039), B pt_BR-jeff-medium (1.366),
    # C pt_BR-cadu-medium (1.454).
    "pt": "pt/pt_BR/jeff/medium/pt_BR-jeff-medium",
    "it": "it/it_IT/paola/medium/it_IT-paola-medium",
    "tr": "tr/tr_TR/dfki/medium/tr_TR-dfki-medium",
    # Von 0.4.5 bis 0.4.6 leer: ar_JO-kareem-medium hat KEINE
    # Lizenzangabe und wird nicht mehr ausgeliefert. Seit 0.5.0 Miro V2
    # von OpenVoiceOS, CC BY-NC-ND 4.0 -- die Datei ist unveraendert,
    # nur umbenannt; siehe STIMM_QUELLE und LIZENZEN.md. Arabisch bleibt
    # ungeprueft.
    "ar": "ar/ar_miro_espeak_V2",
    "sw": "sw/sw_CD/lanfrica/medium/sw_CD-lanfrica-medium",
    "nl": "nl/nl_NL/mls/medium/nl_NL-mls-medium",
    "vi": "vi/vi_VN/vais1000/medium/vi_VN-vais1000-medium",
    "hu": "hu/hu_HU/anna/medium/hu_HU-anna-medium",
    "cs": "cs/cs_CZ/jirka/medium/cs_CZ-jirka-medium",
    "sr": "sr/sr_RS/serbski_institut/medium/sr_RS-serbski_institut-medium",
    "el": "el/el_GR/rapunzelina/medium/el_GR-rapunzelina-medium",
    # Seit 0.4.5 leer: ka_GE-natia-medium ist ausdruecklich nur fuer
    # Privatpersonen freigegeben, Organisationen sind untersagt. Eine
    # Gemeinde ist eine Organisation. Einzelheiten in LIZENZEN.md.
    # Georgisch laeuft damit als reiner Untertitel.
    "ka": "",
    # Seit 0.5.0. Nicht aus dem Piper-Vorrat: umgewandelt aus einem
    # Coqui-Modell, siehe STIMM_QUELLE unten und werkzeuge/twi_stimme.py.
    "tw": "tw/tw_GH-openbible_asante-vits",
}

# Stimmen, die NICHT im Piper-Vorrat (rhasspy/piper-voices) liegen.
# Schluessel ist der Dateiname ohne Endung, wie in voices/.
#
#   onnx    Woher das Modell kommt -- eine Adresse, oder None: dann gibt
#           es die Datei nirgends zum Herunterladen, und sie kommt nur
#           ueber Stick und Vorrat (teile.json).
#   lizenz  Was werkzeuge/stimmlizenzen.py statt einer Modellkarte nennt.
#
# Die Piper-Beschreibung (.onnx.json) dieser Stimmen liegt im Repo unter
# stimmen/ -- sie stammt von hier, nicht vom Anbieter. Woher, steht in
# LIZENZEN.md.
STIMM_QUELLE = {
    "tw_GH-openbible_asante-vits": {
        "onnx": None,
        "lizenz": "CC BY-SA 4.0 (Coqui, Daten BibleTTS/Open.Bible); "
                  "Umwandlung nach ONNX ebenfalls CC BY-SA 4.0",
    },
    # Miro V2. Die Adresse nennt die REVISION, nicht "main": aendert der
    # Anbieter die Datei, passt sie nicht mehr zur sha256 in teile.json,
    # und eine andere Stimme als die gemessene waere eine Ueberraschung.
    # Gespeichert wird sie unter anderem Namen, Inhalt Byte fuer Byte
    # gleich -- die Lizenz (ND) erlaubt keine Bearbeitung.
    "ar_miro_espeak_V2": {
        "onnx": "https://huggingface.co/OpenVoiceOS/"
                "phoonnx_ar_miro_espeak_V2/resolve/"
                "8c5783a11d450ffad2ed99fc7c6dc8d6c8f86ccb/miro_ar.onnx",
        "lizenz": "CC BY-NC-ND 4.0 (TigreGotico Lda / OpenVoiceOS), "
                  "nichtkommerziell, unveraendert",
    },
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
    # Gemessen, bevor die Stimme wegen fehlender Lizenz aus STIMMEN
    # genommen wurde (0.4.5). Die Zahl bleibt als Messwert stehen; sie
    # wird nicht mehr nachgeschlagen.
    "ar_JO-kareem-medium": 1.53,  # Arabisch, nicht mehr ausgeliefert
    # Seit 0.5.0, im selben Lauf wie kareem (1.535) gemessen: 0.996.
    "ar_miro_espeak_V2": 1.00,  # Arabisch
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
    # fr_FR-upmc-medium steht hier ABSICHTLICH nicht -- und seit
    # 0.3.6 wissen wir auch genau, warum.
    #
    # NACHGEMESSEN, mit --speaker, sechs Satzpaaren, noise-w-scale 0:
    #
    #   fr_FR-siwis-medium          1.066   20.7 Zeichen/s
    #   fr_FR-upmc-medium  Sprecher 0   0.473   46.0 Zeichen/s
    #   fr_FR-upmc-medium  Sprecher 1   1.091   21.3 Zeichen/s
    #
    # Der alte Wert 0.447 war Sprecher 0. Die Vermutung von 0.3.1 --
    # "ohne --speaker misst man nicht das, was man meint" -- stimmte
    # nur halb: Piper nimmt ohne Angabe Sprecher 0, und DIESER
    # Sprecher ist wirklich so. 46 Zeichen je Sekunde sind rund das
    # Doppelte jeder anderen Stimme; das ist keine Rede mehr,
    # sondern unbrauchbar.
    #
    # Sprecher 1 (pierre) waere brauchbar und liegt genau dort, wo
    # man Franzoesisch erwartet. Eintragen laesst er sich trotzdem
    # nicht: die Tempotabelle kennt nur Stimmnamen, und der Server
    # waehlt beim Sprechen keinen Sprecher aus -- er bekaeme also
    # wieder Sprecher 0. Wer die Stimme will, muss zuerst den
    # Sprecher durch den Server reichen.
    #
    # Belege: messungen/laengenfaktor_stimmen.json unter
    # "nachgemessen".
    "hu_HU-anna-medium": 1.09,  # Ungarisch
    "it_IT-paola-medium": 1.05,  # Italienisch
    # Wie oben: gemessen, seit 0.4.5 nicht mehr ausgeliefert.
    "ka_GE-natia-medium": 1.29,  # Georgisch
    "nl_NL-mls-medium": 1.63,  # Niederländisch
    # KORRIGIERT nach der Rueckmeldung des Pruefers, nicht gemessen.
    #
    # Gemessen wurden 1.366 -- das ist der Faktor, der die
    # portugiesische Ausgabe auf die Laenge des deutschen Originals
    # bringt. Der Pruefer sagt dazu: zu schnell, Woerter werden
    # verschluckt. Wenn Stoppuhr und Ohr auseinandergehen, gewinnt
    # das Ohr: eine Uebersetzung, die mitlaeuft und die niemand
    # versteht, ist keine.
    #
    # 1.15 statt 1.366. Die Zahl ist eine Entscheidung, keine
    # Messung, und sie kostet Gleichlauf -- bei einer halben Stunde
    # Predigt laeuft Portugiesisch damit sichtbar hinterher. Beim
    # naechsten Ruecklauf gehoert sie bestaetigt oder korrigiert.
    #
    # pt ist nicht ausgeliefert; im Betrieb in Rostock aendert das
    # nichts.
    "pl_PL-bass-high": 1.36,  # Polnisch, nicht ausgeliefert
    "pl_PL-darkman-medium": 1.25,  # Polnisch
    "pl_PL-gosia-medium": 1.25,  # Polnisch, nicht ausgeliefert
    "pl_PL-mc_speech-medium": 1.01,  # Polnisch, nicht ausgeliefert
    "pt_BR-cadu-medium": 1.45,  # Portugiesisch, nicht ausgeliefert
    "pt_BR-jeff-medium": 1.15,  # Portugiesisch, AUSGELIEFERT, siehe oben
    "pt_BR-faber-medium": 1.04,  # Portugiesisch
    "ro_RO-mihai-medium": 1.23,  # Rumänisch
    "ru_RU-irina-medium": 1.22,  # Russisch
    "sr_RS-serbski_institut-medium": 1.67,  # Serbisch
    "sw_CD-lanfrica-medium": 1.09,  # Suaheli
    "tr_TR-dfki-medium": 1.13,  # Türkisch
    # Ukrainisch seit 0.5.0. Gemessen auf denselben 20 Saetzen, beide
    # Stimmen im selben Lauf:
    #
    #   uk_UA-mykyta-high           1.506   ausgeliefert
    #   uk_UA-ukrainian_tts-medium  1.028   (bis 0.4.6; vorher 1.05)
    #
    # mykyta spricht also rund die Haelfte langsamer. Mit dem Aufschlag
    # (1,06) ergibt das 1,596 -- knapp unter TEMPO_MAX 1,6, also an der
    # Grenze, ab der die Verstaendlichkeit faellt (Messreihe 0.2.5).
    # Die Stimmwahl stand fest; dass sie so viel Tempo kostet, ist der
    # Preis. Bestaetigen muss es ein Hoerer -- wie bei pt.
    "uk_UA-mykyta-high": 1.51,  # Ukrainisch
    # ukrainian_tts: die 1,028 oben galt Sprecher 0 (lada), gemessen
    # mit verschluckten Grossbuchstaben (siehe server.zeichen_angleichen).
    # Seit dem Nachtrag zu 0.5.0 spricht hier mykyta (STIMM_SPRECHER),
    # und der ist so langsam wie mykyta-high: 1,499 gegen lada 1,136,
    # gemessen auf den acht Satzpaaren aus pruefung/fallstricke_uk.csv,
    # geeicht an mykyta-high (dort 1,626 -> 1,506). Eine Schaetzung auf
    # wenigen Saetzen; gilt erst, wenn STIMMEN["uk"] umgestellt wird.
    "uk_UA-ukrainian_tts-medium": 1.50,  # Ukrainisch, Sprecher mykyta, nicht ausgeliefert
    "vi_VN-vais1000-medium": 0.99,  # Vietnamesisch
    # Twi, seit 0.5.0. Gemessen 1.664 -- die langsamste Stimme hier. Mit
    # Aufschlag 1,76, gestutzt auf TEMPO_MAX 1,6. Ueber eine lange
    # Predigt laeuft Twi darum hinterher. Hoeher als 1,6 wird es nicht
    # gestellt: dort faellt die Verstaendlichkeit (0.2.5).
    "tw_GH-openbible_asante-vits": 1.66,  # Twi (Asante)
}

# Rueckfall je Sprache, falls eine andere Stimme eingesetzt wird als die
# gemessene. Grob, aber besser als die Vorgabe.
TEMPO_SPRACHE = {
    "ar": 1.00,   # Arabisch (miro, seit 0.5.0)
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
    "uk": 1.51,   # Ukrainisch (mykyta, seit 0.5.0)
    "vi": 0.99,   # Vietnamesisch
    "tw": 1.66,   # Twi (Asante)
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