// Laedt sich das Pult nach einem Update selbst neu? (0.5.2)
//
//     node pruefstand/pult_fassung_test.mjs
//
// Die Hoererseite tut das seit 0.5.0 (fassung_test.mjs). Das Pult
// nicht: wer es am Samstag geoeffnet hatte, arbeitete nach dem Update
// mit der alten Seite gegen einen Server, dessen Antworten sie nicht
// mehr kennt -- 0.5.2 aendert /api/sprachen. Jetzt derselbe Weg und
// derselbe Schutz gegen eine Schleife: "fassung=<neu>" in der Adresse.
//
// Gefahren wird das echte Skript aus web/pult.html im Nachbau, mit der
// Fassung eingesetzt, wie der Server es beim Ausliefern tut. Dazu der
// Server selbst: setzt /pult die Fassung ein?

import { readFileSync } from "node:fs";
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
const titel = (t) => console.log(`\n\x1b[1m== ${t}\x1b[0m`);
const ruhe = () => new Promise((f) => setTimeout(f, 0));

async function pult({ seite, server, suche = "", hash = "" }) {
  const p = pultBauen({ zustand: { fassung: server },
                        extra: { fassung: seite, suche, hash,
                                 antworten: { "/api/sprachen": {
                                   fassung: server, liste: [], moeglich: [],
                                   quelle: "de", ziele: [] } } } });
  for (let i = 0; i < 5; i++) await ruhe();
  await p.fenster.lies();
  return p;
}

titel("1) Gleiche Fassung: nichts passiert");
{
  const p = await pult({ seite: "0.5.2", server: "0.5.2" });
  pruefe("kein Neuladen", [], p.neuGeladen);
}

titel("2) Der Server meldet eine neue Fassung");
{
  const p = await pult({ seite: "0.5.2", server: "0.5.3", hash: "#einrichtung" });
  pruefe("das Pult laedt sich neu, mit fassung=0.5.3, der Reiter bleibt",
         true, p.neuGeladen.includes("/pult?fassung=0.5.3#einrichtung"));
  // Im Browser verlaesst die Seite mit dem ersten replace(); der Nachbau
  // bleibt stehen, und jede weitere Abfrage stoesst es noch einmal an.
  // Es muss nur immer dasselbe Ziel sein.
  pruefe("jeder Anstoss hat dasselbe Ziel", ["/pult?fassung=0.5.3#einrichtung"],
         [...new Set(p.neuGeladen)]);
}

titel("3) Schon einmal neu geladen, passt trotzdem nicht: keine Schleife");
{
  const p = await pult({ seite: "0.5.2", server: "0.5.3",
                         suche: "?fassung=0.5.3" });
  pruefe("kein zweites Neuladen", [], p.neuGeladen);
}

titel("4) Angekommen: der Marker verschwindet aus der Adresse");
{
  const p = await pult({ seite: "0.5.3", server: "0.5.3",
                         suche: "?fassung=0.5.3", hash: "#einrichtung" });
  pruefe("kein Neuladen", [], p.neuGeladen);
  pruefe("die Adresse ist wieder sauber", true,
         p.adresseErsetzt.includes("/pult#einrichtung"));
}

titel("5) Ohne eingesetzte Fassung (Datei, Pruefstand): nichts");
{
  const p = await pult({ seite: undefined, server: "0.5.3" });
  pruefe("kein Neuladen", [], p.neuGeladen);
}

titel("6) Der Server setzt die Fassung ein");
{
  const server = readFileSync(new URL("../server.py", import.meta.url), "utf8");
  const pultweg = server.slice(server.indexOf('@app.get("/pult")'),
                               server.indexOf('@app.get("/pult")') + 900);
  pruefe("/pult ersetzt <!--FASSUNG--> durch config.VERSION", true,
         pultweg.includes('replace("<!--FASSUNG-->", config.VERSION, 1)'));
  const seite = readFileSync(new URL("../web/pult.html", import.meta.url), "utf8");
  pruefe("web/pult.html traegt die Marke genau einmal", 1,
         seite.split("<!--FASSUNG-->").length - 1);
}

console.log();
if (fehler) { console.log(`${fehler} FEHLER`); process.exit(1); }
console.log("Alle Faelle wie erwartet.");
