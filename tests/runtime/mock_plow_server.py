from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

IDENTITY = {
    "line": {"uid": "line-runtime-smoke"},
    "chats": [
        {
            "uid": "chat-runtime-smoke",
            "status": "active",
            "participants": [
                {
                    "type": "agent",
                    "relationship": "self",
                    "line": {"uid": "line-runtime-smoke"},
                },
                {
                    "type": "member",
                    "uid": "owner-runtime-smoke",
                    "role": "owner",
                    "display_name": "Runtime Smoke Owner",
                    "provider_key": None,
                },
            ],
        }
    ],
    "mcp_url": None,
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/v1/agents/cloud/me":
            body = json.dumps(IDENTITY).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def do_POST(self) -> None:
        self.send_error(404)

    def log_message(self, format: str, *args: object) -> None:
        return


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 18080
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
