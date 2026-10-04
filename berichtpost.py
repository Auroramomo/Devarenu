#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Eine Warteschlange fuer Fehlerberichte, die von selbst hinausgehen.

WOZU

Bis 0.3.2 musste jemand am Pult den Kaefer druecken, zwei QR-Codes
abfotografieren und eine E-Mail abschicken. Das setzt voraus, dass es
jemandem auffaellt und dass er es tut. Ein Dienst, der nachts
abstuerzt und von selbst wieder hochkommt, faellt niemandem auf --
und genau der waere interessant.

Seit 0.3.3 sammeln sich Berichte hier, und im Wartungsfenster gehen
sie ueber denselben Kanal hinaus wie die Update-Rueckmeldung.

WAS HINEINKOMMT

Nur das, was fehlerbericht.bauen() liefert -- also nur, was auf der
dortigen ERLAUBNISLISTE steht. Nichts wird hier zusaetzlich
eingesammelt. Kein eingetippter Freitext, kein Predigttext, keine
Uebersetzung, keine Namen, keine Adressen, kein WLAN-Name. Der zweite
Riegel aus fehlerbericht.py laeuft ohnehin mit.

WARUM TEXT UND KEIN ANHANG

Nachgesehen in der ntfy-Dokumentation:

  * Nachrichten ueber 4096 Bytes macht der Server VON SELBST zu einem
    Anhang.
  * Anhaenge verfallen nach DREI STUNDEN.

Ein Bericht, der donnerstags um 18 Uhr hinausgeht und freitags
gelesen wird, waere als Anhang weg. Also bleibt jeder Bericht unter
der Grenze -- gekuerzt, wenn es sein muss, mit deutlichem Vermerk.
Vollstaendig liegt er weiter auf dem Rechner.
"""

import json
import os
import time
from pathlib import Path

# Unter 4096, mit Luft fuer die Kopfzeilen, die meldung.sh anhaengt.
# Lieber ein gekuerzter Bericht, der ankommt und bleibt, als ein
# vollstaendiger, der nach drei Stunden verschwunden ist.
HOECHSTENS = 3500

# So viele Berichte liegen hoechstens herum. Was aelter ist, faellt
# weg: ein Rechner, der jede Stunde denselben Fehler meldet, soll die
# Platte nicht vollschreiben, und die AELTESTEN sind dann ohnehin die
# uninteressantesten.
HOECHSTENS_STUECK = 50

ANLAESSE = {
    "hand": "am Pult gemeldet",
    "neustart": "Dienst neu gestartet",
    "systemcheck": "Systemcheck meldet FEHLT",
    "update": "Update fehlgeschlagen",
}


def _sichern(pfad, rechte):
    try:
        os.chmod(pfad, rechte)
    except OSError:
        pass


def kuerzen(text, hoechstens=HOECHSTENS):
    """Auf die Nachrichtenlaenge bringen -- und sagen, dass gekuerzt wurde.

    Geschnitten wird an einer Zeilengrenze: ein Bericht, der mitten im
    Wort aufhoert, sieht aus wie ein Uebertragungsfehler."""
    if len(text.encode("utf-8")) <= hoechstens:
        return text, False
    zeilen = text.split("\n")
    behalten, laenge = [], 0
    vermerk = "\n[gekuerzt -- vollstaendig auf dem Rechner]\n"
    grenze = hoechstens - len(vermerk.encode("utf-8"))
    for z in zeilen:
        n = len(z.encode("utf-8")) + 1
        if laenge + n > grenze:
            break
        behalten.append(z)
        laenge += n
    return "\n".join(behalten) + vermerk, True


class Warteschlange:
    """Berichte, die noch hinausgehen sollen."""

    def __init__(self, ordner):
        self.ordner = Path(ordner)

    def einreihen(self, anlass, text):
        """Legt einen Bericht ab. Gibt den Pfad zurueck, oder None.

        Auf dem Entwicklungsrechner (entwicklung.py: Marke UND privater
        Signierschluessel) wird nichts eingereiht. Dort meldet jeder
        Serverstart FEHLT fuer Dienst und Autologin, und keiner dieser
        Berichte handelt von einem echten Fehler. Schon liegende
        Berichte bleiben liegen; sie werden hier nicht angefasst."""
        try:
            import entwicklung
            if entwicklung.ist_entwicklungsrechner():
                return None
        except Exception:
            pass
        try:
            self.ordner.mkdir(parents=True, exist_ok=True)
            _sichern(self.ordner, 0o700)
            stempel = time.strftime("%Y-%m-%d_%H-%M-%S")
            pfad = self.ordner / f"{stempel}_{anlass}.txt"
            gekuerzt, wurde = kuerzen(text)
            kopf = (f"Devarenu {config_fassung()} -- "
                    f"{ANLAESSE.get(anlass, anlass)}\n"
                    f"{time.strftime('%d.%m.%Y %H:%M')}\n"
                    f"{'-' * 50}\n")
            pfad.write_text(kopf + gekuerzt, encoding="utf-8")
            _sichern(pfad, 0o600)
            self._aufraeumen()
            return pfad
        except Exception:
            # Ein Bericht, der sich nicht ablegen laesst, darf nichts
            # aufhalten. Er ist der Hinweis auf ein Problem, nicht das
            # Problem.
            return None

    def _aufraeumen(self):
        alle = sorted(self.ordner.glob("*.txt"))
        for p in alle[:-HOECHSTENS_STUECK] if len(alle) > HOECHSTENS_STUECK \
                else []:
            try:
                p.unlink()
                p.with_suffix(".gesendet").unlink(missing_ok=True)
            except OSError:
                pass

    def offene(self):
        """Was noch nicht bestaetigt hinausgegangen ist, aelteste zuerst."""
        if not self.ordner.exists():
            return []
        return [p for p in sorted(self.ordner.glob("*.txt"))
                if not p.with_suffix(".gesendet").exists()]

    def als_gesendet(self, pfad):
        """Erst NACH der Bestaetigung. Sonst geht ein Bericht verloren,
        weil das WLAN im falschen Augenblick weg war."""
        try:
            marke = Path(pfad).with_suffix(".gesendet")
            marke.write_text(time.strftime("%Y-%m-%d %H:%M:%S"),
                             encoding="utf-8")
            _sichern(marke, 0o600)
            return True
        except OSError:
            return False

    def stand(self):
        alle = list(self.ordner.glob("*.txt")) if self.ordner.exists() else []
        return {"gesamt": len(alle), "offen": len(self.offene())}


def config_fassung():
    try:
        import config
        return config.VERSION
    except Exception:
        return "?"
