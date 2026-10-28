#!/usr/bin/env python3
"""Attrappe fuer Ollama. Antwortet, statt zu uebersetzen.

    python3 pruefstand/attrappen/ollama_attrappe.py     druckt "PORT <n>"

Der Server wartet beim Start bis zu 90 Sekunden auf Ollama
(ollama_abwarten, fragt /api/tags). Ohne laufendes Ollama brauchte
damit jeder Start eines Pruefstands so lange -- und die Pruefstaende
geben ihm genau 90 Sekunden. Sie scheiterten dann am Start, nicht an
dem, was sie pruefen.

Die Attrappe laeuft auf einem FREIEN Port, den das System vergibt, und
nicht auf 11434: dort darf das echte Ollama laufen, ohne dass sich
beide in die Quere kommen. Der Pruefstand lenkt die Wegwerfkopie
dorthin (hilfe.ollama_umlenken); am Server und an config.py im Repo
aendert sich nichts.

Uebersetzen kann sie nicht. /api/chat und /api/generate antworten mit
einem Text, der sich als Attrappe zu erkennen gibt -- ein Pruefstand,
der echte Uebersetzung braucht, faellt damit auf, statt still gruen zu
werden.

Als Modul: starten() gibt die Adresse zurueck und laeuft in einem
Faden mit, bis der Prozess endet.
"""

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODELLE = ["gemma4:12b", "qwen3:4b-instruct"]
ANTWORT = "[Ollama-Attrappe: keine Uebersetzung]"
# Seit dem 28.10.2026 auch als llama-server (starten("llama-server")):
# /health, /v1/models, /v1/chat/completions. Jede Anfrage an
# /v1/chat/completions landet in ANFRAGEN -- ein Pruefstand sieht so,
# ob das Denken abgeschaltet mitging.
LLAMA_MODELLE = ["gemma4-12b"]
LLAMA_ANTWORT = "[llama-Attrappe: keine Uebersetzung]"
ANFRAGEN = []


class LlamaAntwort(BaseHTTPRequestHandler):
    def _json(self, daten, status=200):
        roh = json.dumps(daten).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(roh)))
        self.end_headers()
        self.wfile.write(roh)

    def do_GET(self):
        if self.path == "/health":
            self._json({"status": "ok"})
        elif self.path == "/v1/models":
            self._json({"object": "list",
                        "data": [{"id": m, "object": "model"}
                                 for m in LLAMA_MODELLE]})
        else:
            self._json({"error": "nicht nachgebaut"}, 404)

    def do_POST(self):
        laenge = int(self.headers.get("Content-Length") or 0)
        roh = self.rfile.read(laenge)
        if self.path != "/v1/chat/completions":
            self._json({"error": "nicht nachgebaut"}, 404)
            return
        try:
            rumpf = json.loads(roh or b"{}")
        except ValueError:
            rumpf = {}
        ANFRAGEN.append(rumpf)
        aus = (rumpf.get("chat_template_kwargs") or {}).get(
            "enable_thinking") is False
        nachricht = {"role": "assistant", "content": LLAMA_ANTWORT}
        if not aus:
            # Wie gemma4 ohne den Zusatz: es denkt, und das kommt mit.
            nachricht["reasoning_content"] = "(gedacht)"
        self._json({"choices": [{"index": 0, "message": nachricht,
                                 "finish_reason": "stop"}],
                    "usage": {"completion_tokens": 9 if aus else 330}})

    def log_message(self, *a):
        pass


class Antwort(BaseHTTPRequestHandler):
    def _json(self, daten, status=200):
        roh = json.dumps(daten).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(roh)))
        self.end_headers()
        self.wfile.write(roh)

    def do_GET(self):
        if self.path == "/api/tags":
            self._json({"models": [{"name": m, "model": m} for m in MODELLE]})
        elif self.path == "/api/version":
            self._json({"version": "0.0.0-attrappe"})
        elif self.path == "/api/ps":
            self._json({"models": []})
        else:
            self._json({"error": "nicht nachgebaut"}, 404)

    def do_POST(self):
        laenge = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(laenge)
        if self.path == "/api/chat":
            self._json({"message": {"role": "assistant", "content": ANTWORT},
                        "done": True})
        elif self.path == "/api/generate":
            self._json({"response": ANTWORT, "done": True})
        else:
            self._json({"error": "nicht nachgebaut"}, 404)

    def log_message(self, *a):
        pass


def starten(art="ollama"):
    """Startet die Attrappe in einem Faden. Zurueck: "http://127.0.0.1:<n>"."""
    dienst = ThreadingHTTPServer(
        ("127.0.0.1", 0), LlamaAntwort if art == "llama-server" else Antwort)
    threading.Thread(target=dienst.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{dienst.server_address[1]}"


if __name__ == "__main__":
    dienst = ThreadingHTTPServer(("127.0.0.1", 0), Antwort)
    print(f"PORT {dienst.server_address[1]}", flush=True)
    try:
        dienst.serve_forever()
    except KeyboardInterrupt:
        sys.exit(0)
