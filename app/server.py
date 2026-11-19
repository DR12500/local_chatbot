"""Local chatbot web server.

Serves the chat UI and proxies requests to a *local* Ollama instance.
Standard library only (Python 3.8+), so there is nothing third-party to audit.

Privacy guarantees enforced here:
  * The server binds to 127.0.0.1 only (not reachable from your network).
  * The Ollama URL must be a loopback address (refuses to forward elsewhere).
  * Ollama "cloud" models (names containing "cloud"), which run on Ollama's
    servers instead of your GPU, are hidden and refused.
  * The UI loads no external scripts, fonts or CDNs.

Usage:
    python app/server.py [--port 8765] [--ollama http://127.0.0.1:11434]
"""
import argparse
import http.client
import ipaddress
import json
import mimetypes
import socket
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

STATIC_DIR = Path(__file__).resolve().parent / "static"
MAX_BODY = 20 * 1024 * 1024  # 20 MB request limit


def is_loopback(host):
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def is_cloud_model(name):
    return "cloud" in (name or "").lower()


class Handler(BaseHTTPRequestHandler):
    ollama_host = "127.0.0.1"
    ollama_port = 11434
    server_version = "LocalChatbot/1.0"

    # ---- helpers -------------------------------------------------------
    def log_message(self, fmt, *args):  # keep console quiet; never log prompts
        sys.stderr.write("[server] %s %s\n" % (self.command, self.path))

    def send_json(self, status, obj):
        data = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def ollama(self, method, path, body=None, timeout=600):
        conn = http.client.HTTPConnection(self.ollama_host, self.ollama_port, timeout=timeout)
        headers = {"Content-Type": "application/json"} if body is not None else {}
        conn.request(method, path, body=body, headers=headers)
        return conn, conn.getresponse()

    def read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise ValueError("request too large")
        return self.rfile.read(length)

    # ---- routes --------------------------------------------------------
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/models":
            return self.list_models()
        if path == "/api/health":
            return self.health()
        if path == "/":
            path = "/index.html"
        target = (STATIC_DIR / path.lstrip("/")).resolve()
        if STATIC_DIR not in target.parents or not target.is_file():
            return self.send_json(404, {"error": "not found"})
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(str(target))[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        # Browser-side lockdown: the page may only talk to this server.
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'",
        )
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if urlparse(self.path).path == "/api/chat":
            return self.chat()
        self.send_json(404, {"error": "not found"})

    def health(self):
        try:
            conn, resp = self.ollama("GET", "/api/version", timeout=3)
            version = json.loads(resp.read() or b"{}").get("version")
            conn.close()
            self.send_json(200, {"ollama": True, "version": version})
        except (OSError, socket.timeout):
            self.send_json(200, {"ollama": False})

    def list_models(self):
        try:
            conn, resp = self.ollama("GET", "/api/tags", timeout=10)
            data = json.loads(resp.read() or b"{}")
            conn.close()
        except (OSError, socket.timeout):
            return self.send_json(502, {"error": "Ollama is not running. Start it with scripts/start.ps1"})
        models = [
            {
                "name": m["name"],
                "size_gb": round(m.get("size", 0) / 1e9, 1),
                "params": (m.get("details") or {}).get("parameter_size"),
                "quant": (m.get("details") or {}).get("quantization_level"),
            }
            for m in data.get("models", [])
            if not is_cloud_model(m.get("name"))
        ]
        models.sort(key=lambda m: m["size_gb"])
        self.send_json(200, {"models": models})

    def chat(self):
        try:
            req = json.loads(self.read_body() or b"{}")
        except ValueError as e:
            return self.send_json(400, {"error": "bad request: %s" % e})
        model = req.get("model")
        if not model or is_cloud_model(model):
            return self.send_json(400, {"error": "a local model is required (cloud models are blocked)"})

        payload = {
            "model": model,
            "messages": req.get("messages", []),
            "stream": True,
            "options": req.get("options", {}),
        }
        try:
            conn, resp = self.ollama("POST", "/api/chat", body=json.dumps(payload).encode("utf-8"))
        except (OSError, socket.timeout):
            return self.send_json(502, {"error": "Ollama is not running. Start it with scripts/start.ps1"})

        if resp.status != 200:
            detail = resp.read().decode("utf-8", "replace")
            conn.close()
            return self.send_json(resp.status, {"error": detail})

        # Stream NDJSON chunks straight through to the browser.
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        try:
            while True:
                line = resp.readline()
                if not line:
                    break
                self.wfile.write(line)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass  # user pressed "Stop"; closing the upstream connection aborts generation
        finally:
            conn.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--ollama", default="http://127.0.0.1:11434")
    args = ap.parse_args()

    url = urlparse(args.ollama)
    if not is_loopback(url.hostname or ""):
        sys.exit("Refusing to use non-local Ollama host %r: data must stay on this machine." % url.hostname)
    Handler.ollama_host = url.hostname
    Handler.ollama_port = url.port or 11434

    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print("Local chatbot running at http://127.0.0.1:%d  (Ctrl+C to stop)" % args.port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
