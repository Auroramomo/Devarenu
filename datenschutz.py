# -*- coding: utf-8 -*-
"""Der Datenschutzhinweis fuer die Zuhoerer -- in zwei Stufen (0.5.0).

    Stufe 1  der Kurzhinweis: auf dem Handy unter "Mehr" -> "Datenschutz",
             auf dem Aushang am Eingang (anleitung/05_aushang.md)
    Stufe 2  die ausfuehrliche Fassung: /datenschutz, ausgeliefert von
             DIESEM Rechner -- das Saalnetz hat kein Internet, ein Link
             nach draussen fuehrte ins Leere.

ALLES HIER IST EIN ENTWURF, vor Freigabe durch den
Datenschutzbeauftragten. Das steht sichtbar auf jeder Fassung.

Verantwortlich und Kontakt kommen aus der Einrichtung am Pult
(zustand.json: "gemeinde", "kontakt"). Fehlt eine Angabe, faellt die
Zeile weg -- ein Platzhalter vor der Gemeinde waere schlimmer als nichts.

Stufe 1 gibt es auf de, en, ru und fa -- den Sprachen, in denen die
Hoererseite ihre Knoepfe beschriftet; sonst gilt Englisch wie ueberall
dort. ru und fa sind von hier geschrieben und NICHT gegengelesen.
Stufe 2 gibt es auf de und en.
"""

from html import escape

ENTWURF = {
    "de": "Entwurf, vor Freigabe durch den Datenschutzbeauftragten",
    "en": "Draft, pending approval by the data protection officer",
    "ru": "Проект, до утверждения уполномоченным по защите данных",
    "fa": "پیش‌نویس، پیش از تأیید مسئول حفاظت از داده‌ها",
}

STUFE1 = {
    "de": {
        "titel": "Datenschutz",
        "absaetze": [
            "Dieser Gottesdienst wird live übersetzt.",
            "Ein Rechner im Saal erkennt die Sprache am Mikrofon, übersetzt "
            "sie und schickt Text und Ton über das Saal-WLAN auf Ihr Handy.",
            "Alles bleibt auf diesem Rechner: keine Cloud, kein Konto, keine "
            "App.",
            "Gespeichert wird nichts – außer die Gemeinde schaltet eine "
            "Aufnahme, ein Protokoll oder eine Mitschrift der Predigt ein. "
            "Das ist dann auf Ihrem Handy sichtbar.",
            "Ihr Handy bekommt im Saal-WLAN eine Adresse. Sie verschwindet, "
            "wenn der Rechner ausgeschaltet wird.",
        ],
        "verantwortlich": "Verantwortlich: {}",
        "kontakt": "Kontakt: {}",
        "mehr": "Ausführliche Fassung",
        "mehr_hin": "Sie liegt auf diesem Rechner, denn das Saal-WLAN hat "
                    "kein Internet.",
    },
    "en": {
        "titel": "Privacy",
        "absaetze": [
            "This service is being translated live.",
            "A computer in the hall recognises the language at the "
            "microphone, translates it and sends text and sound to your "
            "phone over the hall wi-fi.",
            "Everything stays on this computer: no cloud, no account, no "
            "app.",
            "Nothing is stored – unless the church switches on a recording, "
            "a log or a transcript of the sermon. You will then see that on "
            "your phone.",
            "Your phone gets an address in the hall wi-fi. It disappears "
            "when the computer is switched off.",
        ],
        "verantwortlich": "Responsible: {}",
        "kontakt": "Contact: {}",
        "mehr": "Full version",
        "mehr_hin": "It is kept on this computer, because the hall wi-fi has "
                    "no internet.",
    },
    "ru": {
        "titel": "Защита данных",
        "absaetze": [
            "Это богослужение переводится в реальном времени.",
            "Компьютер в зале распознаёт речь с микрофона, переводит её и "
            "передаёт текст и звук на ваш телефон через Wi-Fi зала.",
            "Всё остаётся на этом компьютере: ни облака, ни учётной записи, "
            "ни приложения.",
            "Ничего не сохраняется – если только община не включит "
            "аудиозапись, протокол или стенограмму проповеди. Тогда это "
            "будет видно на вашем телефоне.",
            "Ваш телефон получает адрес в Wi-Fi зала. Он исчезает, когда "
            "компьютер выключают.",
        ],
        "verantwortlich": "Ответственный: {}",
        "kontakt": "Контакт: {}",
        "mehr": "Подробная версия",
        "mehr_hin": "Она хранится на этом компьютере, потому что у Wi-Fi "
                    "зала нет интернета.",
    },
    "fa": {
        "titel": "حریم خصوصی",
        "absaetze": [
            "این مراسم به‌صورت زنده ترجمه می‌شود.",
            "رایانه‌ای در سالن گفتار را از میکروفون تشخیص می‌دهد، آن را ترجمه "
            "می‌کند و متن و صدا را از طریق وای‌فای سالن به گوشی شما می‌فرستد.",
            "همه‌چیز روی همین رایانه می‌ماند: بدون فضای ابری، بدون حساب "
            "کاربری، بدون برنامه.",
            "چیزی ذخیره نمی‌شود – مگر اینکه کلیسا ضبط صدا، گزارش یا رونوشت "
            "موعظه را روشن کند. در آن صورت این روی گوشی شما دیده می‌شود.",
            "گوشی شما در وای‌فای سالن یک نشانی می‌گیرد. این نشانی با خاموش شدن "
            "رایانه از بین می‌رود.",
        ],
        "verantwortlich": "مسئول: {}",
        "kontakt": "تماس: {}",
        "mehr": "نسخهٔ کامل",
        "mehr_hin": "این نسخه روی همین رایانه است، چون وای‌فای سالن اینترنت "
                    "ندارد.",
    },
}

RTL = {"fa", "ar"}


def stufe1(sprache, gemeinde="", kontakt=""):
    """Der Kurzhinweis als Daten -- fuer das Blatt auf dem Handy.

    Ohne Gemeinde und ohne Kontakt fallen die Zeilen weg."""
    sp = sprache if sprache in STUFE1 else "en"
    t = STUFE1[sp]
    zeilen = []
    if (gemeinde or "").strip():
        zeilen.append(t["verantwortlich"].format(gemeinde.strip()))
    if (kontakt or "").strip():
        zeilen.append(t["kontakt"].format(kontakt.strip()))
    return {"sprache": sp, "rtl": sp in RTL, "titel": t["titel"],
            "entwurf": ENTWURF[sp], "absaetze": list(t["absaetze"]),
            "angaben": zeilen, "mehr": t["mehr"], "mehr_hin": t["mehr_hin"],
            "link": f"/datenschutz?sprache={'de' if sp == 'de' else 'en'}"}


# ---------------------------------------------------------------- Stufe 2

STUFE2 = {
    "de": {
        "titel": "Datenschutz bei der Live-Übersetzung",
        "teile": [
            ("Worum es geht",
             ["Für die Übersetzung des Gottesdienstes steht im Saal ein "
              "Rechner mit dem Programm Devarenu. Er stellt ein WLAN bereit, "
              "das keine Verbindung ins Internet hat. Über dieses WLAN kommen "
              "Text und Ton der Übersetzung auf Ihr Handy. Sie brauchen keine "
              "App, kein Konto und keine Anmeldung."]),
            ("Wer verantwortlich ist", ["{verantwortlich}"]),
            ("Was verarbeitet wird", [
                "**Ton und Text des Gottesdienstes.** Der Ton vom Mikrofon "
                "wird auf dem Rechner erkannt und übersetzt. Ton und Text "
                "liegen nur im Arbeitsspeicher. Die letzten Abschnitte hält "
                "der Rechner bereit, damit ein Handy nach einem kurzen "
                "Abbruch nachlesen kann, was es verpasst hat; nach einem "
                "Neustart sind sie weg.",
                "**Ihr Handy im Saal-WLAN.** Damit es die Seite erreicht, "
                "bekommt es eine Adresse. Dafür sieht der Rechner die "
                "Geräteadresse (MAC), die zugeteilte Adresse und den Namen, "
                "den sich das Handy selbst gibt. Das liegt nur im "
                "Arbeitsspeicher, ist nur für den Verwalter des Rechners "
                "lesbar, geht nicht ins Protokoll und ist mit dem Ausschalten "
                "weg.",
                "**Die Knöpfe „verständlich“ und „schwer verständlich“.** "
                "Gezählt wird je Sprache und Tag – nicht, von welchem Gerät "
                "und nicht, wann.",
                "**„Melden“.** Eine Nachricht an die Technik steht bis zum "
                "Ende des Gottesdienstes am Pult, ohne Absender und ohne "
                "Gerät, und geht nie nach draußen. Bitte schreiben Sie dort "
                "nichts Persönliches.",
                "**„Rückmeldung“.** Sie schreiben mit Ihrem eigenen "
                "Mailprogramm an den Betreuer des Programms. Dafür gelten "
                "die Bedingungen Ihres Mailanbieters.",
                "**Tonaufnahme der Predigt.** Nur wenn die Gemeinde sie "
                "einschaltet und die predigende Person zugestimmt hat. Solange "
                "sie läuft, steht es auf jedem Handy. Sie bleibt auf dem "
                "Rechner (voreingestellt sieben Tage) und ist aus dem "
                "Saal-WLAN nicht abrufbar.",
                "**Testprotokoll und Mitschrift.** Zur Fehlersuche kann die "
                "Technik den Predigttext speichern lassen: das Testprotokoll "
                "schreibt ihn mit allen Übersetzungen in eine Datei (nur mit "
                "Zustimmung der sprechenden Person, nur am Rechner selbst, "
                "voreingestellt nach sieben Tagen gelöscht); die Mitschrift "
                "schreibt den Anfang jedes erkannten Satzes ins "
                "Systemprotokoll des Rechners (dort rund vier Wochen). Darin "
                "steht der Text, nichts über Zuhörer. "
                "Solange eines davon läuft, steht es auf jedem Handy."]),
            ("Was auf Ihrem Handy bleibt",
             ["Ihr Browser merkt sich ein paar Einstellungen – etwa ob der "
              "Bildschirm anbleiben soll, wie dunkel die Seite ist und Ihre "
              "Stimme bei „verständlich“. Das liegt nur auf Ihrem Handy; "
              "löschen Sie die Websitedaten, ist es weg."]),
            ("Was nicht geschieht",
             ["Keine Cloud, keine Werbung, keine Weitergabe. Der Rechner "
              "kann – nur wenn die Gemeinde es eingeschaltet hat – über ein "
              "anderes Netz Aktualisierungen holen und technische Meldungen "
              "an den Betreuer schicken. Daten über Zuhörer sind nicht "
              "darunter."]),
            ("Rechtsgrundlage",
             ["**Gemeinden der Freikirche der Siebenten-Tags-Adventisten:** "
              "Datenschutzverordnung der Freikirche (DSVO 2018), § 53 "
              "„Gottesdienste und kirchliche Veranstaltungen“. Die "
              "Verarbeitung ist zulässig, wenn die Teilnehmenden über Art "
              "und Umfang informiert werden – das geschieht mit diesem "
              "Hinweis und dem Aushang am Eingang.",
              "**Andere Träger:** Datenschutz-Grundverordnung, Art. 6 "
              "Abs. 1 lit. f (berechtigtes Interesse an einer verständlichen "
              "Übertragung des Gottesdienstes). *Noch zu bestätigen.*"]),
            ("Ihre Rechte",
             ["Sie können Auskunft verlangen, Berichtigung, Löschung und "
              "Einschränkung, und Sie können widersprechen. Weil über Sie "
              "nichts gespeichert wird, gibt es in aller Regel nichts "
              "herauszugeben. Fragen richten Sie an die Verantwortlichen "
              "oben; beschweren können Sie sich bei der zuständigen "
              "Aufsicht."]),
        ],
        "ohne_angaben": "Die Gemeinde, die diesen Rechner betreibt. "
                        "(Name und Kontakt sind am Pult nicht eingetragen.)",
        "zurueck": "Zurück zur Übersetzung",
    },
    "en": {
        "titel": "Privacy for the live translation",
        "teile": [
            ("What this is about",
             ["To translate the service, a computer running the program "
              "Devarenu stands in the hall. It provides a wi-fi that has no "
              "connection to the internet. Text and sound of the translation "
              "reach your phone through this wi-fi. You need no app, no "
              "account and no login."]),
            ("Who is responsible", ["{verantwortlich}"]),
            ("What is processed", [
                "**Sound and text of the service.** The sound from the "
                "microphone is recognised and translated on the computer. "
                "Sound and text are held in memory only. The computer keeps "
                "the latest sections so that a phone can catch up after a "
                "short drop-out; after a restart they are gone.",
                "**Your phone in the hall wi-fi.** To reach the page it gets "
                "an address. For that the computer sees the device address "
                "(MAC), the assigned address and the name the phone gives "
                "itself. This is held in memory only, readable only by the "
                "administrator of the computer, not logged, and gone when "
                "the computer is switched off.",
                "**The buttons “clear” and “hard to follow”.** They are "
                "counted per language and day – not by device and not by "
                "time.",
                "**“Message”.** A message to the sound desk stays at the "
                "desk until the end of the service, without sender or device, "
                "and never leaves the hall. Please write nothing personal.",
                "**“Feedback”.** You write with your own mail program to the "
                "maintainer of the program. Your mail provider's terms apply.",
                "**Recording of the sermon.** Only if the church switches it "
                "on and the preacher has agreed. While it runs, every phone "
                "shows it. It stays on the computer (seven days by default) "
                "and cannot be fetched over the hall wi-fi.",
                "**Test log and transcript.** For troubleshooting the "
                "technician can have the sermon text stored: the test log "
                "writes it with all translations to a file (only with the "
                "speaker's consent, only at the computer itself, deleted "
                "after seven days by default); the transcript writes the "
                "beginning of each recognised sentence to the computer's "
                "system log (kept there for about four weeks). They "
                "contain the text, nothing about listeners. While either "
                "runs, every phone shows it."]),
            ("What stays on your phone",
             ["Your browser remembers a few settings – for example whether "
              "the screen stays on, how dark the page is, and your vote on "
              "“clear”. This stays on your phone only; clearing the site "
              "data removes it."]),
            ("What does not happen",
             ["No cloud, no advertising, no sharing. Only if the church has "
              "switched it on, the computer can fetch updates over another "
              "network and send technical reports to the maintainer. No data "
              "about listeners is part of that."]),
            ("Legal basis",
             ["**Churches of the Seventh-day Adventist Church in Germany:** "
              "the church's data protection regulation (DSVO 2018), § 53 "
              "“services and church events”. The processing is permitted if "
              "participants are informed about its nature and extent – this "
              "notice and the poster at the entrance do that.",
              "**Other operators:** General Data Protection Regulation, "
              "Art. 6(1)(f) (legitimate interest in an understandable "
              "transmission of the service). *To be confirmed.*"]),
            ("Your rights",
             ["You can ask for access, correction, erasure and restriction, "
              "and you can object. As nothing about you is stored, there is "
              "usually nothing to hand over. Please address questions to the "
              "people responsible above; you can complain to the competent "
              "supervisory authority."]),
        ],
        "ohne_angaben": "The church that runs this computer. (Name and "
                        "contact have not been entered at the desk.)",
        "zurueck": "Back to the translation",
    },
}


def _fett(text):
    """**fett** und *kursiv* -- mehr Markdown braucht diese Seite nicht."""
    import re
    t = escape(text)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    return re.sub(r"\*(.+?)\*", r"<i>\1</i>", t)


def stufe2_html(sprache, gemeinde="", kontakt="", fassung=""):
    """Die ausfuehrliche Fassung als ganze Seite."""
    sp = "de" if sprache == "de" else "en"
    t = STUFE2[sp]
    s1 = STUFE1[sp]
    angaben = []
    if (gemeinde or "").strip():
        angaben.append(escape(s1["verantwortlich"].format(gemeinde.strip())))
    if (kontakt or "").strip():
        angaben.append(escape(s1["kontakt"].format(kontakt.strip())))
    verantwortlich = "<br>".join(angaben) or escape(t["ohne_angaben"])
    teile = []
    for kopf, absaetze in t["teile"]:
        inhalt = []
        for a in absaetze:
            if a == "{verantwortlich}":
                inhalt.append(f"<p>{verantwortlich}</p>")
            else:
                inhalt.append(f"<p>{_fett(a)}</p>")
        teile.append(f"<h2>{escape(kopf)}</h2>\n" + "\n".join(inhalt))
    andere = "en" if sp == "de" else "de"
    return f"""<!doctype html>
<html lang="{sp}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(t['titel'])}</title>
<style>
:root{{--grund:#fbfaf7;--tinte:#141f52;--leise:#5d6475;--warn:#8a4b0f}}
@media (prefers-color-scheme:dark){{:root{{--grund:#111522;--tinte:#e8eaf2;--leise:#a3a9b8;--warn:#f0b36b}}}}
body{{margin:0;background:var(--grund);color:var(--tinte);
  font:1rem/1.55 Georgia,"Iowan Old Style","Times New Roman",serif}}
main{{max-width:40rem;margin:0 auto;padding:1.2rem 1rem 3rem}}
h1{{font-weight:400;font-size:1.45rem;margin:.4rem 0 .8rem}}
h2{{font-size:1.05rem;margin:1.6rem 0 .4rem}}
p{{margin:0 0 .8rem}}
.entwurf{{border:2px solid var(--warn);color:var(--warn);padding:.5rem .7rem;
  font:600 .9rem/1.4 system-ui,sans-serif}}
nav,footer{{font:.85rem/1.4 system-ui,sans-serif;color:var(--leise)}}
a{{color:inherit}}
</style></head>
<body><main>
<nav><a href="/">{escape(t['zurueck'])}</a> · <a href="/datenschutz?sprache={andere}">{'English' if andere == 'en' else 'Deutsch'}</a></nav>
<p class="entwurf">{escape(ENTWURF[sp])}</p>
<h1>{escape(t['titel'])}</h1>
{chr(10).join(teile)}
<footer><p>Devarenu {escape(fassung)} · {escape(ENTWURF[sp])}</p></footer>
</main></body></html>
"""
