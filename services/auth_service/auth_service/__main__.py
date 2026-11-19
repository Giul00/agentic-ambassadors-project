"""Servidor local para probar auth-service sin AWS (solo biblioteca estándar).

Uso (desde services/auth_service):  python -m auth_service [--port 8080]
Prueba:  curl -X POST http://127.0.0.1:8080/authorize -d '{"merchant_id":"m1","amount":100,"currency":"ARS","card_token":"tok_demo01"}'
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .handler import MAX_BODY_BYTES, lambda_handler


class _Handler(BaseHTTPRequestHandler):
    def _send(self, result: dict) -> None:
        body = result["body"].encode("utf-8")
        self.send_response(result["statusCode"])
        for key, value in result["headers"].items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != "/authorize":
            self._send({"statusCode": 404, "headers": {"Content-Type": "application/json"},
                        "body": json.dumps({"error": "ruta no encontrada"})})
            return
        length = min(int(self.headers.get("Content-Length") or 0), MAX_BODY_BYTES + 1)
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        self._send(lambda_handler({"httpMethod": "POST", "body": raw}))

    def do_GET(self) -> None:  # noqa: N802
        self._send(lambda_handler({"httpMethod": "GET"}))


def main() -> None:
    parser = argparse.ArgumentParser(description="auth-service local")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), _Handler)
    print(f"auth-service escuchando en http://127.0.0.1:{args.port}/authorize")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
