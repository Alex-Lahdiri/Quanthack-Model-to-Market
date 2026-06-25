"""
Cloud 'mission control' web service (for Northflank) — serves the live dashboard and the
AI trading-desk decision over HTTP. Advisory only; the MT5 feed + bridge stay on the
Windows box. Stdlib only (no web framework) for a tiny, robust container.

Endpoints:
  GET /            -> the dashboard.html page
  GET /health      -> {"status":"ok"}  (Northflank health check)
  GET /api/desk    -> runs the AI desk on the latest book.json, returns the decision JSON
  GET /api/status  -> the most recent desk_decision.json

Run:  PORT=8080 python live/server.py
"""
from __future__ import annotations
import http.server, socketserver, json, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = int(os.environ.get("PORT", "8080"))


class Handler(http.server.BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/dashboard", "/index.html"):
            f = os.path.join(ROOT, "dashboard.html")
            if os.path.exists(f):
                self._send(200, open(f, "rb").read(), "text/html; charset=utf-8")
            else:
                self._send(404, "dashboard.html not found")
        elif path == "/health":
            self._send(200, json.dumps({"status": "ok"}))
        elif path == "/api/desk":
            book = os.path.join(ROOT, "book.json")
            if not os.path.exists(book):
                self._send(404, json.dumps({"error": "no book.json yet"})); return
            try:
                subprocess.run([sys.executable, os.path.join(ROOT, "live", "desk.py"),
                                "--book", book, "--headlines", os.path.join(ROOT, "live", "headlines.txt"),
                                "--emit", os.path.join(ROOT, "desk_decision.json")],
                               cwd=ROOT, timeout=70, capture_output=True)
            except Exception as e:
                self._send(500, json.dumps({"error": str(e)})); return
            d = os.path.join(ROOT, "desk_decision.json")
            self._send(200, open(d).read() if os.path.exists(d) else json.dumps({"error": "no decision produced"}))
        elif path == "/api/status":
            d = os.path.join(ROOT, "desk_decision.json")
            self._send(200, open(d).read() if os.path.exists(d) else json.dumps({"status": "no decision yet"}))
        else:
            self._send(404, json.dumps({"error": "not found"}))

    def log_message(self, *a):  # quiet
        pass


if __name__ == "__main__":
    print(f"mission-control on :{PORT}  routes: / /health /api/desk /api/status", flush=True)
    socketserver.TCPServer.allow_reuse_address = True
    socketserver.TCPServer(("0.0.0.0", PORT), Handler).serve_forever()
