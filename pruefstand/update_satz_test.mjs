// "Der Stick bringt Fassung 0.3.0, hier laeuft schon ?." (A4b, 28.10.2026)
//
//     node pruefstand/update_satz_test.mjs
//
// So stand es in Rostock unter Einrichtung -> Update, nachdem ein alter
// 0.3.0-Stick steckte. stick_update.sh schrieb bei "nicht neuer" das
// Feld "vorher" nicht, und das Pult setzte fuer die laufende Fassung
// "?" ein. Jetzt schreibt der Stick sie mit -- und das Pult kennt die
// Fassung, mit der es ausgeliefert wurde, und nimmt die, wenn eine
// alte stand.json das Feld nicht hat.

import { pultBauen } from "./pultnachbau.mjs";

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

const p = pultBauen({ extra: { fassung: "0.5.2" } });
const satz = (d) => p.fenster.updateSatz(d);

const alt = satz({ lage: "nicht_neuer", version: "0.3.0", vorher: "" });
console.log(`      ohne "vorher": ${alt}`);
pruefe("ohne vorher: die Fassung dieses Pults statt \"?\"", true,
       alt.includes("hier läuft schon 0.5.2"));
pruefe("kein Fragezeichen", false, alt.includes("?"));

const neu = satz({ lage: "nicht_neuer", version: "0.3.0", vorher: "0.5.1" });
console.log(`      mit "vorher":  ${neu}`);
pruefe("mit vorher: genau die", true, neu.includes("hier läuft schon 0.5.1"));

// Andere Lagen nehmen "vorher" in seiner eigenen Bedeutung (die Fassung
// VOR dem Versuch) -- dort darf das Pult nichts einsetzen.
const f = satz({ lage: "fehlgeschlagen", version: "0.5.2", vorher: "0.5.1" });
pruefe("fehlgeschlagen bleibt, wie es war", true, f.includes("0.5.1"));

console.log();
if (fehler) { console.log(`${fehler} FEHLER`); process.exit(1); }
console.log("Alle Faelle wie erwartet.");
