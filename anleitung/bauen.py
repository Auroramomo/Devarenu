#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Baut die Bedienungsanleitung als PDF.

Laeuft NUR auf dem Arbeitsrechner, im eigenen Bau-venv (.bau-venv).
Auf dem Gemeinderechner wird nichts gebaut -- dort liegt das fertige
PDF, und es kommt kein zusaetzliches Paket dazu.

Warum fpdf2 und nicht pandoc oder ein Browser: auf dem Arbeitsrechner
war weder pandoc noch Chromium installiert, und beides waere ein
Systempaket. fpdf2 ist reines Python, braucht keine Systembibliothek
und laesst sich in einem venv festnageln.

    bash anleitung_bauen.sh
"""

import hashlib
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from fpdf import FPDF

HIER = Path(__file__).resolve().parent
WURZEL = HIER.parent

# Dieselben Farben wie am Pult und auf der Beamer-Seite.
TINTE = (20, 31, 82)
GRAU = (107, 115, 133)
STREIFEN = (28, 58, 143)

# Die Sprachen, die die Zuhoererseite anbietet. Wer uebersetzt mithoert,
# spricht ja gerade kein Deutsch -- eine Anleitung nur auf Deutsch waere
# fuer genau die Leute unlesbar, fuer die sie gedacht ist.
#
# rtl: von rechts nach links. Farsi braucht dafuer Textformung
# (uharfbuzz) und eine Schrift mit arabischen Zeichen -- DejaVu hat
# keine. Geprueft wurde das an einer Probeseite: Buchstaben verbinden
# sich, Zeilen laufen richtig um, Anfuehrungszeichen sitzen.
SPRACHEN = {
    "de": {"name": "Deutsch", "rtl": False,
           "titel": "Mithören im Gottesdienst",
           "teil": "Für die Zuhörer", "datei": "Devarenu-Zuhoerer.pdf"},
    "en": {"name": "English", "rtl": False,
           "titel": "Listening along in the service",
           "teil": "For the listeners", "datei": "Devarenu-Zuhoerer-en.pdf"},
    "ru": {"name": "Русский", "rtl": False,
           "titel": "Слушать перевод на богослужении",
           "teil": "Для слушателей", "datei": "Devarenu-Zuhoerer-ru.pdf"},
    "fa": {"name": "فارسی", "rtl": True,
           "titel": "شنیدن ترجمه در مراسم",
           "teil": "برای شنوندگان", "datei": "Devarenu-Zuhoerer-fa.pdf"},
}

# Uebersetzt, aber von niemandem gegengelesen -- dieselbe Auskunft wie
# bei den Glossaren. Wer sie liest, soll wissen, woran er ist.
# Die Worte der Titelseite je Sprache. "Devarenu" bleibt ueberall
# lateinisch -- es ist ein Name.
TITELWORTE = {
    "de": ("Vorversion", "Wird mit jeder größeren Fassung überarbeitet.",
           "Fassung"),
    "en": ("Preview", "Revised with every major version.", "Version"),
    "ru": ("Предварительная версия",
           "Перерабатывается с каждой крупной версией.", "Версия"),
    "fa": ("نسخهٔ آزمایشی", "با هر نسخهٔ بزرگ بازنویسی می‌شود.", "نسخه"),
}

MASCHINELL = {
    "en": "Machine-translated, not yet reviewed by a native speaker.",
    "ru": "Машинный перевод, ещё не проверен носителем языка.",
    "fa": "ترجمهٔ ماشینی، هنوز بازبینی‌نشده.",
}


def fassung():
    try:
        return (WURZEL / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "unbekannt"


def _zeitpunkt():
    """Der Erstellzeitpunkt im PDF -- aus DATUM, nicht aus der Uhr."""
    roh = stand()
    try:
        tag, monat, jahr = (int(x) for x in roh.split("."))
        return datetime(jahr, monat, tag, 12, 0, 0, tzinfo=timezone.utc)
    except Exception:
        # Ohne brauchbares Datum ein fester Punkt. Irgendein Wert ist
        # besser als die Uhr: er aendert sich wenigstens nicht.
        return datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def stand():
    """Das Datum auf dem Titel -- aus DATUM, nicht aus der Uhr.

    Zwei Baulaeufe hintereinander muessen dieselbe Datei ergeben. Steht
    dort das heutige Datum, ist jeder Neubau eine Aenderung im Repo,
    auch wenn sich am Inhalt nichts getan hat. Dann sieht man vor lauter
    Rauschen nicht mehr, was sich wirklich geaendert hat.

    Das Datum wird von Hand gepflegt, zusammen mit der Fassung."""
    try:
        return (HIER / "DATUM").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


class Anleitung(FPDF):
    def __init__(self, titel, rtl=False):
        super().__init__(format="A4", unit="mm")
        self.titel = titel
        self.rtl = rtl
        # Der Buchstabe des Teils, oben rechts auf jeder Seite. Wer die
        # Anleitung aufgeschlagen in der Hand haelt, soll auf einen
        # Blick wissen, in welchem Teil er ist.
        self.teilbuchstabe = ""
        # Ein einzelnes Blatt: keine Titelseite, keine Teile, und die
        # Fusszeile schon auf Seite 1 -- sonst traegt das Blatt weder
        # Fassung noch Datum, und gedruckt weiss in einem halben Jahr
        # niemand mehr, welches er in der Hand haelt.
        self.einblatt = False
        self.set_auto_page_break(True, margin=20)
        # DejaVu ist in fpdf2 nicht dabei, aber auf jedem Linux da.
        # Ohne eine Unicode-Schrift gaebe es keine Umlaute -- die
        # eingebauten Schriften koennen nur Latin-1, und "ä" faellt
        # dann still weg.
        gefunden = self._schrift_suchen()
        if gefunden is None:
            # Abbrechen statt ein PDF ohne Text zu schreiben: eine
            # leere Seite faellt erst auf, wenn sie jemand aufschlaegt.
            if rtl:
                sys.exit(
                    "Keine arabische Schrift gefunden (Noto Naskh "
                    "Arabic).\n"
                    "  Arch/CachyOS:   sudo pacman -S noto-fonts\n"
                    "  Debian/Ubuntu:  sudo apt install fonts-noto-core")
            sys.exit(
                "Keine DejaVu-Schrift gefunden. Ohne sie gibt es keine "
                "Umlaute im PDF.\n"
                "  Arch/CachyOS:   sudo pacman -S ttf-dejavu\n"
                "  Debian/Ubuntu:  sudo apt install fonts-dejavu-core")
        normal, fett = gefunden
        self.add_font("s", "", str(normal))
        self.add_font("s", "B", str(fett))
        self.set_font("s", "", 11)

        # Eine zweite Schrift fuer lateinische Zeichen. NotoNaskhArabic
        # hat kein "A" -- geprueft an der Zeichentabelle -- und der
        # Teilbuchstabe waere in der arabischen Fassung schlicht
        # unsichtbar. Genau das war er beim ersten Bauen.
        latn = sorted(Path("/usr/share/fonts").rglob("DejaVuSans.ttf"))
        latb = sorted(Path("/usr/share/fonts").rglob("DejaVuSans-Bold.ttf"))
        self.hat_latein = bool(latn and latb)
        if self.hat_latein:
            self.add_font("lat", "", str(latn[0]))
            self.add_font("lat", "B", str(latb[0]))

        if rtl:
            # Ohne Textformung stehen die Buchstaben einzeln und in der
            # falschen Reihenfolge -- lesbar ist das nicht.
            self.set_text_shaping(True)

    def _schrift_suchen(self):
        """(normal, fett). DejaVu fuer Latein und Kyrillisch, Noto Naskh
        fuer die arabische Schrift -- DejaVu deckt sie nicht ab."""
        wurzel = Path("/usr/share/fonts")
        if getattr(self, "rtl", False):
            paare = [("NotoNaskhArabic-Regular.ttf",
                      "NotoNaskhArabic-Bold.ttf"),
                     ("NotoSansArabic-Regular.ttf",
                      "NotoSansArabic-Bold.ttf")]
        else:
            paare = [("DejaVuSans.ttf", "DejaVuSans-Bold.ttf")]
        for nname, fname in paare:
            n = sorted(wurzel.rglob(nname))
            f = sorted(wurzel.rglob(fname))
            if n and f:
                return n[0], f[0]
            if n:
                # Ohne fette Schnittstelle lieber dieselbe zweimal als
                # gar kein PDF. Ueberschriften sind dann nicht fett,
                # aber lesbar.
                return n[0], n[0]
        return None

    def header(self):
        if self.page_no() == 1 or not self.teilbuchstabe:
            return
        # Gross und aussen: so findet man den Teil im Blaettern.
        self.set_font("lat" if self.hat_latein else "s", "B", 22)
        self.set_text_color(200, 206, 220)
        breite = self.w - self.l_margin - self.r_margin
        self.set_xy(self.l_margin, 8)
        # Bei rechts-nach-links nach LINKS: rechts steht dort die
        # Ueberschrift, und der Buchstabe verschwaende dahinter.
        self.cell(breite, 10, self.teilbuchstabe,
                  align="L" if self.rtl else "R")
        self.set_xy(self.l_margin, self.t_margin)

    def footer(self):
        if self.einblatt:
            self.set_y(-15)
            self.set_text_color(*GRAU)
            self.set_font("s", "", 8)
            self.cell(0, 5, f"Devarenu {fassung()}  ·  {stand()}", align="C")
            return
        if self.page_no() == 1:
            return
        self.set_y(-15)
        self.set_text_color(*GRAU)
        if self.rtl:
            # Lateinischer Titel neben arabischem Text wird von der
            # Bidi-Umordnung auseinandergerissen -- beim ersten Bauen
            # stand dort "مه در مراسم ... شنیدن ترج1". Also nur die
            # Seitenzahl, und die in lateinischer Schrift.
            self.set_font("lat" if self.hat_latein else "s", "B", 8)
            self.cell(0, 5, str(self.page_no() - 1), align="C")
        else:
            self.set_font("s", "", 8)
            self.cell(0, 5, f"{self.titel}  ·  {self.page_no() - 1}",
                      align="C")

    def titelseite(self, untertitel, teile, maschinell="", worte=None):
        self.add_page()
        self.ln(60)
        # "Devarenu" ist ein Name und bleibt lateinisch -- die
        # arabische Schrift hat die Buchstaben gar nicht, und beim
        # ersten Bauen stand dort deshalb nichts.
        self.set_font("lat" if self.hat_latein else "s", "B", 30)
        self.set_text_color(*TINTE)
        self.cell(0, 14, "Devarenu", align="C", new_x="LMARGIN",
                  new_y="NEXT")
        self.ln(2)
        self.set_draw_color(*STREIFEN)
        self.set_line_width(1.2)
        mitte = self.w / 2
        self.line(mitte - 35, self.get_y(), mitte + 35, self.get_y())
        self.ln(8)
        self.set_font("s", "", 14)
        self.cell(0, 8, untertitel, align="C", new_x="LMARGIN",
                  new_y="NEXT")
        self.ln(20)
        self.set_font("s", "", 10)
        self.set_text_color(*GRAU)
        for zeile in teile:
            self.cell(0, 6, zeile, align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(25)
        vor, satz, fassungswort = worte or TITELWORTE["de"]
        self.set_font("s", "B", 11)
        self.set_text_color(180, 90, 20)
        self.cell(0, 7, vor, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("s", "", 9)
        self.set_text_color(*GRAU)
        self.cell(0, 5, satz, align="C", new_x="LMARGIN", new_y="NEXT")
        if maschinell:
            self.ln(4)
            self.set_font("s", "", 9)
            self.set_text_color(150, 90, 30)
            self.multi_cell(0, 5, maschinell, align="C")
        self.ln(6)
        self.set_font("s", "", 9)
        self.set_text_color(*GRAU)
        datum = stand()
        # Das Wort in der jeweiligen Sprache, Nummer und Datum
        # lateinisch -- Ziffern gibt es in beiden Schriften, aber die
        # Reihenfolge waere sonst der Bidi-Umordnung ausgeliefert.
        self.cell(0, 5, fassungswort, align="C", new_x="LMARGIN",
                  new_y="NEXT")
        self.set_font("lat" if self.hat_latein else "s", "", 9)
        self.cell(0, 5, fassung() + (f"  ·  {datum}" if datum else ""),
                  align="C", new_x="LMARGIN", new_y="NEXT")

    def lateinisch_pruefen(self, text, woher):
        """Warnt vor lateinischen Buchstaben in einer RTL-Fassung.

        NotoNaskhArabic hat KEINE lateinischen Buchstaben. Sie fallen
        beim Setzen spurlos weg -- aus "5G oder LTE" wurde "5" und zwei
        Leerstellen, und die Seite sah auf den ersten Blick heil aus.

        Eine Ersatzschrift waere der naheliegende Ausweg und geht
        NICHT: mit set_fallback_fonts zerfaellt in fpdf2 2.8.8 die
        arabische Verbindungsschrift, aus "صفحه" wird "صف حه". An einer
        gerenderten Seite gesehen, beides.

        Also: nicht heimlich reparieren, sondern melden. Der Text
        gehoert umgeschrieben, ohne lateinische Buchstaben."""
        if not self.rtl:
            return
        import unicodedata
        schlimm = sorted({z for z in text
                          if "LATIN" in unicodedata.name(z, "")})
        if schlimm:
            print(f"  ! {woher}: lateinische Buchstaben in einer "
                  f"Fassung von rechts nach links -- sie fallen im PDF "
                  f"WEG: {''.join(schlimm)}")

    def markdown(self, text):
        """Der kleine Teil von Markdown, den diese Anleitung benutzt."""
        aus = "R" if self.rtl else "L"
        for art, inhalt in self._absaetze(text):
            self.set_x(self.l_margin)
            if art == "h1":
                self.add_page()
                self.set_font("s", "B", 19)
                self.set_text_color(*TINTE)
                self.multi_cell(0, 9, inhalt, align=aus)
                self.set_draw_color(*STREIFEN)
                self.set_line_width(0.8)
                self.line(self.l_margin, self.get_y() + 1,
                          self.w - self.r_margin, self.get_y() + 1)
                self.ln(6)
            elif art == "h2":
                if self.get_y() > self.h - 50:
                    self.add_page()
                self.ln(3)
                self.set_font("s", "B", 13)
                self.set_text_color(*TINTE)
                self.multi_cell(0, 7, inhalt, align=aus)
                self.ln(1)
            elif art == "code":
                self.set_font("s", "", 10)
                self.set_text_color(60, 60, 60)
                self.set_fill_color(244, 246, 250)
                self.multi_cell(0, 6, "  " + inhalt, fill=True, align="L")
            elif art == "leer":
                self.ln(3)
            elif art == "liste":
                marke, rest = inhalt
                self._absatz(rest, marke=marke)
            else:
                self._absatz(inhalt)

    @staticmethod
    def _absaetze(text):
        """Zeilen zu Bloecken verbinden, jeder mit seiner Art.

        Der Knackpunkt sind die FOLGEZEILEN einer Aufzaehlung. Im
        Quelltext stehen sie eingerueckt unter ihrem Punkt:

            1. **Einmessen.** Den Prediger sprechen lassen und
               auf "Einmessen" druecken.

        Bis eben wurden sie als eigener Absatz gesetzt -- und standen
        dann am linken Rand, unter dem Aufzaehlungszeichen statt neben
        ihm. Die Liste sah aus wie Fliesstext mit Punkten dazwischen.
        Jetzt gehoeren sie zu ihrem Punkt und ruecken mit ein.

        Vier Leerzeichen sind etwas anderes: das ist ein Befehl zum
        Abtippen und bleibt Zeile fuer Zeile stehen."""
        bloecke = []
        puffer = []
        art = "text"
        marke = ""

        def leeren():
            nonlocal puffer, art, marke
            if puffer:
                text_ = " ".join(puffer)
                if art == "liste":
                    bloecke.append(("liste", (marke, text_)))
                else:
                    bloecke.append((art, text_))
                puffer = []
            art, marke = "text", ""

        im_zaun = False
        for roh in text.split("\n"):
            zeile = roh.rstrip()
            nackt = zeile.strip()
            eingerueckt = zeile[:1] == " " and not zeile.startswith("    ")

            # Ein Zaun aus ``` -- die Schreibweise, die jeder aus
            # Markdown kennt. Der Bauer kannte bis 0.2.14 nur die
            # Einrueckung, und ein Zaun wurde still zu Fliesstext: die
            # Backticks standen im PDF, und die Anfuehrungszeichen im
            # Befehl wurden zu deutschen. Genau so ist es beim Blatt
            # fuer den Helfer passiert.
            # Ein Blockzitat. Der Bauer kannte es nicht, und das ">"
            # stand danach mitten im Satz -- dieselbe Falle wie bei
            # den ```-Zaeunen. Der Text wird als eigener Absatz
            # gesetzt, die Marke faellt weg.
            if nackt.startswith(">"):
                leeren()
                bloecke.append(("text", nackt.lstrip("> ").strip()))
                continue
            if nackt.startswith("```"):
                leeren()
                im_zaun = not im_zaun
                continue
            if im_zaun:
                leeren()
                bloecke.append(("code", nackt))
            elif not nackt:
                leeren()
                bloecke.append(("leer", ""))
            elif zeile.startswith("    "):
                leeren()
                bloecke.append(("code", nackt))
            elif nackt.startswith("## "):
                leeren()
                bloecke.append(("h2", nackt[3:]))
            elif nackt.startswith("# "):
                leeren()
                bloecke.append(("h1", nackt[2:]))
            elif re.match(r"^\d+\. ", nackt) and not eingerueckt:
                leeren()
                nr, rest = nackt.split(". ", 1)
                art, marke = "liste", nr + "."
                puffer.append(rest)
            elif nackt.startswith("- ") and not eingerueckt:
                leeren()
                art, marke = "liste", "\u2022"
                puffer.append(nackt[2:])
            else:
                # Folgezeile: gehoert zum laufenden Block, egal ob das
                # ein Absatz oder ein Aufzaehlungspunkt ist.
                puffer.append(nackt)
        leeren()
        return bloecke

    def _absatz(self, zeile, marke=""):
        """Setzt einen Absatz und wertet dabei **fett** aus.

        marke ist das Aufzaehlungszeichen. Es steht AUSSERHALB des
        Textblocks, und die Folgezeilen ruecken darunter ein --
        haengender Einzug. Ohne das beginnt die zweite Zeile einer
        Aufzaehlung ganz links und laeuft unter das Zeichen; dann sieht
        die Liste aus wie Fliesstext mit Punkten dazwischen."""
        self.set_font("s", "", 11)
        self.set_text_color(30, 30, 40)
        rand = self.l_margin
        einzug = 7 if marke else 0

        if marke:
            if self.rtl:
                # Rechtsbuendig: das Zeichen steht rechts vom Text.
                self.set_xy(self.w - self.r_margin - einzug, self.get_y())
                self.cell(einzug, 6, marke, align="R")
                self.set_x(rand)
                self.set_right_margin(self.r_margin + einzug)
            else:
                self.set_xy(rand, self.get_y())
                self.cell(einzug, 6, marke)
                self.set_left_margin(rand + einzug)
                self.set_x(rand + einzug)

        zeile = self._auszeichnen(zeile)
        teile = re.split(r"\*\*(.+?)\*\*", zeile)
        if self.rtl:
            # write() setzt von links; fuer rechts-nach-links braucht es
            # multi_cell mit align="R". Fettungen gehen dabei verloren,
            # deshalb werden die Sternchen vorher entfernt -- ein
            # Sternchen mitten im Satz waere schlimmer als fehlende
            # Fettung.
            self.multi_cell(0, 6.5, "".join(teile), align="R",
                            new_x="LMARGIN", new_y="NEXT")
        else:
            # multi_cell mit markdown=True statt write() je Stueck.
            #
            # Vorher wurde abwechselnd normal und fett geschrieben,
            # jedes Stueck mit write(). Das bricht die Zeile aber
            # innerhalb eines Stuecks -- und wenn ein fettes Wort nicht
            # mehr in den Rest der Zeile passt, mitten im Wort. Auf dem
            # Helferblatt stand "Konsol e".
            #
            # markdown=True kennt **fett** selbst und umbricht ueber
            # die Auszeichnung hinweg richtig.
            self.set_font("s", "", 11)
            self.multi_cell(0, 6, zeile, markdown=True, align="L",
                            new_x="LMARGIN", new_y="NEXT")

        if marke:
            if self.rtl:
                self.set_right_margin(self.r_margin - einzug)
            else:
                self.set_left_margin(rand)
            self.set_x(self.l_margin)

    @staticmethod
    def _auszeichnen(zeile):
        """Kursiv gibt es in DejaVu nicht als eigene Datei. Statt das
        Sternchen stehen zu lassen -- wo es jeder fuer einen Tippfehler
        haelt -- kommt der Text in Anfuehrungszeichen. Deutsche, denn
        die Quelle ist deutsch; die uebersetzten Fassungen bringen ihre
        eigenen schon im Text mit."""
        zeile = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", "\u201e\\1\u201c",
                       zeile)
        # Rueckwaertsakzente sind eine Auszeichnung des Quelltexts, kein
        # Zeichen, das jemand lesen soll.
        return re.sub(r"`([^`]+)`", "\u201e\\1\u201c", zeile)


def bauen(quellen, ziel, untertitel, teile, rtl=False, maschinell="",
          buchstaben=None, einblatt=False):
    """quellen: Liste von (Pfad, Teilbuchstabe).

    einblatt=True laesst die Titelseite weg. Gedacht fuer das eine
    Blatt, das jemand ausdruckt und in die Hand nimmt -- dort waere
    eine Titelseite die Haelfte des Papiers fuer nichts."""
    pdf = Anleitung("Devarenu " + untertitel, rtl=rtl)
    pdf.einblatt = einblatt
    if not einblatt:
        pdf.titelseite(untertitel, teile, maschinell, worte=buchstaben)
    for quelle, buchstabe in quellen:
        pdf.teilbuchstabe = buchstabe
        roh = quelle.read_text(encoding="utf-8")
        pdf.lateinisch_pruefen(roh, quelle.name)
        pdf.markdown(roh)

    # Reproduzierbar: ohne feste Kennung und festes Datum traegt jedes
    # PDF eine neue Erstellungszeit und eine zufaellige Datei-Kennung --
    # zwei Baulaeufe ohne inhaltliche Aenderung waeren dann zwei
    # verschiedene Dateien, und jeder Neubau ein Rauschen im Repo.
    # Fester Zeitpunkt statt "jetzt". Abgeleitet aus dem Datum in
    # anleitung/DATUM, damit er sich mit dem Inhalt aendert und sonst
    # nie.
    pdf.set_creation_date(_zeitpunkt())
    # file_id ist in fpdf2 eine METHODE, keine Eigenschaft -- sie wird
    # beim Schreiben aufgerufen. Sie liefert ab Werk eine zufaellige
    # Kennung; hier wird sie aus Fassung, Datum und Dateiname
    # abgeleitet und ist damit bei gleichem Inhalt gleich.
    marke = hashlib.sha256(
        (fassung() + stand() + ziel.name).encode("utf-8")
    ).hexdigest()[:32].upper()
    pdf.file_id = lambda m=marke: f"<{m}><{m}>"
    pdf.output(str(ziel))
    print(f"  {ziel.relative_to(WURZEL)}  "
          f"({ziel.stat().st_size // 1024} KB, {pdf.page_no()} Seite"
          f"{'n' if pdf.page_no() != 1 else ''})")
    if einblatt and pdf.page_no() != 1:
        sys.exit(f"  {ziel.name} soll EIN Blatt sein, hat aber "
                 f"{pdf.page_no()} Seiten. Text kuerzen.")


def main():
    hier = HIER
    titel = hier / "00_titel.md"
    pult = hier / "02_pult.md"
    technik = hier / "03_technik.md"
    for d in (titel, pult, technik):
        if not d.exists():
            sys.exit(f"Fehlt: {d}")

    print("Baue:")
    # Die ganze Anleitung -- fuers Pult, auf Deutsch.
    bauen([(titel, ""), (hier / "01_zuhoerer.md", "A"),
           (pult, "B"), (technik, "C")],
          hier / "Devarenu-Anleitung.pdf",
          "Live-Übersetzung im Gottesdienst",
          ["Teil A  Für die Zuhörer",
           "Teil B  Für das Pult",
           "Teil C  Für die Technik"])

    # Das eine Blatt fuer den Helfer. Ein Ehrenamtlicher, der einmal im
    # Jahr einen Stick einsteckt, liest keine dreissigseitige Anleitung
    # -- und soll es auch nicht muessen.
    helfer = hier / "04_helfer.md"
    if helfer.exists():
        bauen([(helfer, "")], hier / "Devarenu-Umstellung.pdf",
              "Umstellung", [], einblatt=True)

    # Teil A einzeln, in jeder Sprache, die die Zuhoererseite anbietet.
    # Wer uebersetzt mithoert, spricht ja gerade kein Deutsch.
    for code, spr in SPRACHEN.items():
        quelle = hier / ("01_zuhoerer.md" if code == "de"
                         else f"01_zuhoerer.{code}.md")
        if not quelle.exists():
            print(f"  {code}: {quelle.name} fehlt, uebersprungen")
            continue
        bauen([(quelle, "A")], hier / spr["datei"], spr["titel"],
              [spr["teil"]], rtl=spr["rtl"],
              maschinell=MASCHINELL.get(code, ""),
              buchstaben=TITELWORTE.get(code))


if __name__ == "__main__":
    main()
