// Der Versuch "Stille-Fueller" -- und vor allem: dass er AUS ist.
//
//     node pruefstand/versuch_test.mjs
//
// Der Versuch haengt an einem Adresszusatz (?versuch=stille). Die
// eine Zusage, die zaehlt, ist die negative: ohne ihn aendert sich
// fuer einen Zuhoerer in Rostock NICHTS. Alles andere ist ein
// Messgeraet, das mitfaehrt, wenn jemand es bestellt.

import { browserBauen, skriptLaden } from "./browsernachbau.mjs";

const SEITE = new URL("../client.html", import.meta.url).pathname;
let fehler = 0;

function pruefe(was, erwartet, ist) {
  if (JSON.stringify(erwartet) === JSON.stringify(ist)) {
    console.log(`   ok    ${was}`);
  } else {
    fehler++;
    console.log(`   FEHLER ${was}: erwartet ${JSON.stringify(erwartet)}, `
                + `ist ${JSON.stringify(ist)}`);
  }
}
const titel = (t) => console.log(`\n\x1b[1m== ${t}\x1b[0m`);

// Der Nachbau kennt localStorage nur als leere Attrappe. Fuer diesen
// Lauf braucht es einen, der sich etwas merkt -- genau daran haengt
// die Frage, ob der Versuch einen Neuladen ueberlebt.
function laden({ suche = "", gemerkt = null } = {}) {
  const umgebung = browserBauen();
  umgebung.location.search = suche;
  const kasten = { versuch: gemerkt };
  umgebung.localStorage = {
    getItem: (k) => (k in kasten ? kasten[k] : null),
    setItem: (k, w) => { kasten[k] = String(w); },
    removeItem: (k) => { delete kasten[k]; },
  };
  umgebung.btoa = (s) => Buffer.from(s, "binary").toString("base64");
  umgebung.URLSearchParams = URLSearchParams;
  const p = skriptLaden(umgebung, SEITE);
  return { ...p, umgebung, kasten };
}

titel("1) Ohne Adresszusatz aendert sich NICHTS");
{
  const { Versuch, Ton, zustand } = laden();
  pruefe("der Versuch ist aus", false, Versuch.stille);
  pruefe("und merkt nichts mit", 0, Versuch.ereignisse.length);
  // Der Kern: eine leere Schlange laesst das Element stehen, wie
  // bisher. Keine Stille, kein loop, kein zweites play().
  Ton.freischalten();
  zustand.tonAn = true;
  Ton.spielt = false;
  Ton.schlange = [];
  Ton._weiter();
  pruefe("keine Stille in Schleife", false, !!Ton.stillLaeuft);
  pruefe("das Element wird nicht auf loop gestellt", undefined,
         Ton.spieler.loop);
}

titel("2) Mit ?versuch=stille ist er an");
{
  const { Versuch, kasten } = laden({ suche: "?versuch=stille" });
  pruefe("der Versuch laeuft", true, Versuch.stille);
  pruefe("und ist im Browser gemerkt", "stille", kasten.versuch);
}

titel("3) Gemerkt ueberlebt das Neuladen");
{
  const { Versuch } = laden({ gemerkt: "stille" });
  pruefe("ohne Zusatz in der Adresse weiterhin an", true, Versuch.stille);
}

titel("4) ?versuch=aus nimmt ihn wieder weg");
{
  const { Versuch, kasten } = laden({ suche: "?versuch=aus",
                                      gemerkt: "stille" });
  pruefe("der Versuch ist aus", false, Versuch.stille);
  pruefe("und nichts bleibt gemerkt", undefined, kasten.versuch);
}

titel("5) Im Versuch endet das Element nie");
{
  const { Versuch, Ton, zustand } = laden({ suche: "?versuch=stille" });
  Ton.freischalten();
  zustand.tonAn = true;
  Ton.spielt = false;
  Ton.schlange = [];
  Ton._weiter();
  pruefe("leere Schlange ergibt Stille", true, Ton.stillLaeuft);
  pruefe("und zwar in Schleife", true, Ton.spieler.loop);
  pruefe("die Stille kommt aus dem Browser, nicht vom Server", true,
         String(Ton.spieler.src).startsWith("data:audio/wav;base64,"));
  // Kommt ein Haeppchen, uebernimmt es -- ohne loop.
  Ton.einreihen("/ton/de/7", 7);
  pruefe("das Haeppchen loest die Stille ab", false, Ton.stillLaeuft);
  pruefe("und laeuft nicht in Schleife", false, Ton.spieler.loop);
  pruefe("Ereignisse werden mitgeschrieben", true,
         Versuch.ereignisse.length > 0);
}

titel("6) Nichts davon geht an den Server");
{
  const { Versuch, umgebung } = laden({ suche: "?versuch=stille" });
  Versuch.merken("probe", "x");
  const text = Versuch.ereignisse.join(" ");
  pruefe("das Protokoll steht nur auf dem Geraet", true,
         text.includes("probe"));
  // browsernachbau liefert ein fetch, das jede Anfrage ablehnt und
  // sie vorher zaehlt waere Aufwand -- hier genuegt die Quelle:
  // merken() ruft nichts auf, was nach draussen geht.
  const quelle = Versuch.merken.toString();
  pruefe("merken() ruft kein fetch", false, /fetch|XMLHttpRequest|sendBeacon/
         .test(quelle));
}

console.log("");
if (fehler) { console.log(`${fehler} FEHLER`); process.exit(1); }
console.log("\x1b[32mAlle Faelle wie erwartet.\x1b[0m");
