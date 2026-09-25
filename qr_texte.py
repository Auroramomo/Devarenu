#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Die Texte der QR-Seite, in allen Sprachen, die Devarenu anbietet.

Die Seite haengt am Beamer und wechselt alle acht Sekunden die Sprache.
Wer uebersetzt mithoert, liest kein Deutsch -- eine Projektionsseite
nur auf Deutsch waere fuer genau die Leute unlesbar, fuer die sie
gedacht ist.

ACHTUNG, UNGEPRUEFT
-------------------
Diese Uebersetzungen sind maschinell entstanden und von KEINEM
Muttersprachler gegengelesen. Auf der Seite selbst steht das
ABSICHTLICH NICHT: sie haengt vor der Gemeinde, und ein Hinweis
"maschinell uebersetzt" an der Wand hilft dort niemandem. Geprueft
wird hier, in dieser Datei.

Wer eine Sprache gegenliest, streicht sie unten in GEPRUEFT ein. So
steht an einer Stelle, worauf man sich verlassen kann.

Der Ton ist bewusst knapp und in der Befehlsform: aus zwoelf Metern
liest niemand einen Nebensatz. Die drei Kaesten sagen genau das, was
sonst als Rueckfrage kommt.

Fehlt eine Sprache, gilt Englisch.
"""

# Welche Sprachen ein Muttersprachler gelesen hat. Bis hier etwas
# steht, ist alles ausser Deutsch unbesehen.
GEPRUEFT = ("de",)

# Eigenname und Schreibrichtung. Der Eigenname steht auf der Seite --
# "Русский" und nicht "Russisch": wer die Sprache sucht, sucht ihr
# eigenes Wort.
SPRACHEN = {
    "de": ("Deutsch",    False),
    "en": ("English",    False),
    "ru": ("Русский",    False),
    "fa": ("فارسی",      True),
    "uk": ("Українська", False),
    "pl": ("Polski",     False),
    "ro": ("Română",     False),
    "es": ("Español",    False),
    "fr": ("Français",   False),
    "pt": ("Português",  False),
    "it": ("Italiano",   False),
    "tr": ("Türkçe",     False),
    "ar": ("العربية",    True),
    "sw": ("Kiswahili",  False),
    "nl": ("Nederlands", False),
    "vi": ("Tiếng Việt", False),
    "hu": ("Magyar",     False),
    "cs": ("Čeština",    False),
    "sr": ("Српски",     False),
    "el": ("Ελληνικά",   False),
    "ka": ("ქართული",    False),
}

# schritt1  ueber dem WLAN-Code
# schritt2  ueber dem Seiten-Code
# geduld    gelber Kasten: warten, nicht neu verbinden
# internet  blauer Kasten: "Kein Internet" ist richtig
# hoeren    lila Kasten: Kopfhoerer, Bildschirm an
TEXTE = {
    "de": {
        "schritt1": "Mit dem WLAN verbinden",
        "schritt2": "Seite öffnen",
        "geduld": "Bis zu einer Minute warten. Beim ersten Mal braucht "
                  "das Handy Zeit. Nicht neu verbinden.",
        "internet": "„Kein Internet“ ist richtig. Dieses WLAN bringt nur "
                    "die Übersetzung. Oben kann 5G stehen. Verbunden bleiben.",
        "hoeren": "Kopfhörer benutzen. Bildschirm anlassen, sonst stoppt "
                  "der Ton.",
    },
    "en": {
        "schritt1": "Connect to the wi-fi",
        "schritt2": "Open the page",
        "geduld": "Wait up to a minute. The first time, your phone needs "
                  "a while. Do not reconnect.",
        "internet": "“No internet” is correct. This wi-fi only carries the "
                    "translation. 5G may still show at the top. Stay connected.",
        "hoeren": "Use headphones. Keep the screen on, or the sound stops.",
    },
    "ru": {
        "schritt1": "Подключитесь к Wi-Fi",
        "schritt2": "Откройте страницу",
        "geduld": "Подождите до минуты. В первый раз телефону нужно время. "
                  "Не переподключайтесь.",
        "internet": "«Без интернета» — это правильно. Этот Wi-Fi передаёт "
                    "только перевод. Сверху может быть 5G. Оставайтесь "
                    "подключёнными.",
        "hoeren": "Используйте наушники. Не гасите экран, иначе звук "
                  "прервётся.",
    },
    "fa": {
        "schritt1": "به وای‌فای وصل شوید",
        "schritt2": "صفحه را باز کنید",
        "geduld": "تا یک دقیقه صبر کنید. بار اول گوشی زمان لازم دارد. "
                  "دوباره وصل نشوید.",
        "internet": "«بدون اینترنت» درست است. این وای‌فای فقط ترجمه را "
                    "می‌رساند. ممکن است بالا 5G نشان دهد. متصل بمانید.",
        "hoeren": "از هدفون استفاده کنید. صفحه را روشن نگه دارید، وگرنه "
                  "صدا قطع می‌شود.",
    },
    "uk": {
        "schritt1": "Підключіться до Wi-Fi",
        "schritt2": "Відкрийте сторінку",
        "geduld": "Зачекайте до хвилини. Уперше телефону потрібен час. "
                  "Не перепідключайтеся.",
        "internet": "«Без інтернету» — це правильно. Цей Wi-Fi передає лише "
                    "переклад. Угорі може бути 5G. Залишайтеся підключеними.",
        "hoeren": "Користуйтеся навушниками. Не вимикайте екран, інакше звук "
                  "зупиниться.",
    },
    "pl": {
        "schritt1": "Połącz się z Wi-Fi",
        "schritt2": "Otwórz stronę",
        "geduld": "Poczekaj do minuty. Za pierwszym razem telefon potrzebuje "
                  "czasu. Nie łącz się ponownie.",
        "internet": "„Brak internetu” jest w porządku. To Wi-Fi przekazuje "
                    "tylko tłumaczenie. U góry może być 5G. Pozostań "
                    "połączony.",
        "hoeren": "Używaj słuchawek. Nie wygaszaj ekranu, bo dźwięk się "
                  "zatrzyma.",
    },
    "ro": {
        "schritt1": "Conectați-vă la Wi-Fi",
        "schritt2": "Deschideți pagina",
        "geduld": "Așteptați până la un minut. Prima dată telefonul are "
                  "nevoie de timp. Nu vă reconectați.",
        "internet": "„Fără internet” este corect. Acest Wi-Fi transmite doar "
                    "traducerea. Sus poate apărea 5G. Rămâneți conectat.",
        "hoeren": "Folosiți căști. Lăsați ecranul aprins, altfel sunetul se "
                  "oprește.",
    },
    "es": {
        "schritt1": "Conéctese al wifi",
        "schritt2": "Abra la página",
        "geduld": "Espere hasta un minuto. La primera vez el teléfono "
                  "necesita tiempo. No vuelva a conectarse.",
        "internet": "«Sin internet» es correcto. Este wifi solo trae la "
                    "traducción. Arriba puede aparecer 5G. Siga conectado.",
        "hoeren": "Use auriculares. Deje la pantalla encendida o el sonido "
                  "se detiene.",
    },
    "fr": {
        "schritt1": "Connectez-vous au wifi",
        "schritt2": "Ouvrez la page",
        "geduld": "Attendez jusqu’à une minute. La première fois, le "
                  "téléphone a besoin de temps. Ne vous reconnectez pas.",
        "internet": "« Pas d’internet » est normal. Ce wifi ne transporte "
                    "que la traduction. La 5G peut rester affichée en haut. "
                    "Restez connecté.",
        "hoeren": "Utilisez des écouteurs. Laissez l’écran allumé, sinon le "
                  "son s’arrête.",
    },
    "pt": {
        "schritt1": "Ligue-se ao wi-fi",
        "schritt2": "Abra a página",
        "geduld": "Espere até um minuto. Da primeira vez o telemóvel precisa "
                  "de tempo. Não volte a ligar.",
        "internet": "“Sem internet” está certo. Este wi-fi traz apenas a "
                    "tradução. Em cima pode aparecer 5G. Continue ligado.",
        "hoeren": "Use auscultadores. Deixe o ecrã ligado, senão o som para.",
    },
    "it": {
        "schritt1": "Collegatevi al wi-fi",
        "schritt2": "Aprite la pagina",
        "geduld": "Aspettate fino a un minuto. La prima volta il telefono ha "
                  "bisogno di tempo. Non riconnettetevi.",
        "internet": "«Nessuna connessione» è corretto. Questo wi-fi porta "
                    "solo la traduzione. In alto può restare 5G. Rimanete "
                    "collegati.",
        "hoeren": "Usate le cuffie. Lasciate lo schermo acceso, altrimenti "
                  "l’audio si ferma.",
    },
    "tr": {
        "schritt1": "Wi-Fi’ye bağlanın",
        "schritt2": "Sayfayı açın",
        "geduld": "Bir dakikaya kadar bekleyin. İlk seferde telefonun zamana "
                  "ihtiyacı var. Yeniden bağlanmayın.",
        "internet": "„İnternet yok“ doğrudur. Bu Wi-Fi yalnızca çeviriyi "
                    "taşır. Üstte 5G yazabilir. Bağlı kalın.",
        "hoeren": "Kulaklık kullanın. Ekranı açık bırakın, yoksa ses durur.",
    },
    "ar": {
        "schritt1": "اتصل بشبكة الواي فاي",
        "schritt2": "افتح الصفحة",
        "geduld": "انتظر حتى دقيقة واحدة. في المرة الأولى يحتاج الهاتف إلى "
                  "وقت. لا تُعد الاتصال.",
        "internet": "«لا يوجد إنترنت» صحيح. هذه الشبكة تنقل الترجمة فقط. قد "
                    "يظهر 5G في الأعلى. ابقَ متصلاً.",
        "hoeren": "استخدم سماعات الرأس. أبقِ الشاشة مضاءة، وإلا توقف الصوت.",
    },
    "sw": {
        "schritt1": "Unganisha na Wi-Fi",
        "schritt2": "Fungua ukurasa",
        "geduld": "Subiri hadi dakika moja. Mara ya kwanza simu inahitaji "
                  "muda. Usiunganishe upya.",
        "internet": "“Hakuna intaneti” ni sawa. Wi-Fi hii inaleta tafsiri "
                    "tu. Juu inaweza kuonyesha 5G. Endelea kuwa "
                    "umeunganishwa.",
        "hoeren": "Tumia vipokea sauti. Acha skrini iwe wazi, la sivyo sauti "
                  "itasimama.",
    },
    "nl": {
        "schritt1": "Verbind met de wifi",
        "schritt2": "Open de pagina",
        "geduld": "Wacht tot een minuut. De eerste keer heeft de telefoon "
                  "tijd nodig. Niet opnieuw verbinden.",
        "internet": "„Geen internet” klopt. Deze wifi brengt alleen de "
                    "vertaling. Bovenin kan 5G staan. Blijf verbonden.",
        "hoeren": "Gebruik een koptelefoon. Laat het scherm aan, anders stopt "
                  "het geluid.",
    },
    "vi": {
        "schritt1": "Kết nối Wi-Fi",
        "schritt2": "Mở trang",
        "geduld": "Chờ tối đa một phút. Lần đầu điện thoại cần thời gian. "
                  "Đừng kết nối lại.",
        "internet": "“Không có internet” là đúng. Wi-Fi này chỉ truyền bản "
                    "dịch. Phía trên có thể hiện 5G. Hãy giữ kết nối.",
        "hoeren": "Dùng tai nghe. Để màn hình sáng, nếu không âm thanh sẽ "
                  "dừng.",
    },
    "hu": {
        "schritt1": "Csatlakozzon a wifihez",
        "schritt2": "Nyissa meg az oldalt",
        "geduld": "Várjon akár egy percet. Első alkalommal a telefonnak idő "
                  "kell. Ne csatlakozzon újra.",
        "internet": "A „Nincs internet” rendben van. Ez a wifi csak a "
                    "fordítást hozza. Fent maradhat az 5G. Maradjon "
                    "csatlakozva.",
        "hoeren": "Használjon fülhallgatót. Hagyja bekapcsolva a képernyőt, "
                  "különben leáll a hang.",
    },
    "cs": {
        "schritt1": "Připojte se k Wi-Fi",
        "schritt2": "Otevřete stránku",
        "geduld": "Počkejte až minutu. Poprvé potřebuje telefon čas. "
                  "Nepřipojujte se znovu.",
        "internet": "„Bez internetu“ je správně. Tato Wi-Fi přináší jen "
                    "překlad. Nahoře může být 5G. Zůstaňte připojeni.",
        "hoeren": "Použijte sluchátka. Nechte obrazovku zapnutou, jinak se "
                  "zvuk zastaví.",
    },
    "sr": {
        "schritt1": "Повежите се на Wi-Fi",
        "schritt2": "Отворите страницу",
        "geduld": "Сачекајте до један минут. Први пут телефону треба времена. "
                  "Немојте се поново повезивати.",
        "internet": "„Нема интернета“ је у реду. Овај Wi-Fi доноси само "
                    "превод. Горе може писати 5G. Останите повезани.",
        "hoeren": "Користите слушалице. Оставите екран упаљен, иначе се звук "
                  "зауставља.",
    },
    "el": {
        "schritt1": "Συνδεθείτε στο Wi-Fi",
        "schritt2": "Ανοίξτε τη σελίδα",
        "geduld": "Περιμένετε έως ένα λεπτό. Την πρώτη φορά το κινητό "
                  "χρειάζεται χρόνο. Μην επανασυνδεθείτε.",
        "internet": "Το «Χωρίς σύνδεση» είναι σωστό. Αυτό το Wi-Fi φέρνει "
                    "μόνο τη μετάφραση. Επάνω μπορεί να γράφει 5G. Μείνετε "
                    "συνδεδεμένοι.",
        "hoeren": "Χρησιμοποιήστε ακουστικά. Αφήστε την οθόνη αναμμένη, "
                  "αλλιώς ο ήχος σταματά.",
    },
    "ka": {
        "schritt1": "დაუკავშირდით Wi-Fi-ს",
        "schritt2": "გახსენით გვერდი",
        "geduld": "დაელოდეთ ერთ წუთამდე. პირველად ტელეფონს დრო სჭირდება. "
                  "ხელახლა ნუ დაუკავშირდებით.",
        "internet": "„ინტერნეტი არ არის“ სწორია. ეს Wi-Fi მხოლოდ თარგმანს "
                    "გადმოსცემს. ზემოთ შეიძლება ეწეროს 5G. დარჩით "
                    "დაკავშირებული.",
        "hoeren": "გამოიყენეთ ყურსასმენები. ეკრანი ჩართული დატოვეთ, თორემ "
                  "ხმა შეწყდება.",
    },
}


def fuer(code):
    """Die Texte einer Sprache -- oder Englisch, wenn es sie nicht gibt."""
    return TEXTE.get(code) or TEXTE["en"]


def name(code):
    return SPRACHEN.get(code, (code.upper(), False))[0]


def rtl(code):
    return SPRACHEN.get(code, (code, False))[1]
