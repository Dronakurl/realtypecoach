#!/usr/bin/env python3
"""
Simple HTTP server to provide text for Monkeytype injection.

Run this server, then open https://monkeytype.com.
The Tampermonkey script will poll this server for text.
"""

import http.server
import json
import socketserver
import time
from pathlib import Path

PORT = 12543
RTC_FILE = Path.home() / ".rtc_monkeytype_inject.json"


class InjectionHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/inject":
            if RTC_FILE.exists():
                data = json.loads(RTC_FILE.read_text())
                age = time.time() * 1000 - data.get("timestamp", 0)

                if age < 30000:  # 30 seconds
                    self.send_response(200)
                    self.send_header("Content-type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(json.dumps(data).encode())
                    print(f"✅ Sent injection data: {data['text'][:50]}...")
                    # Delete after sending
                    RTC_FILE.unlink()
                    return

            # No data or too old
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'{"error": "no data"}')
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress logs


def start_server():
    with socketserver.TCPServer(("", PORT), InjectionHandler) as httpd:
        print(f"🚀 Injection server running on http://localhost:{PORT}")
        print("Press Ctrl+C to stop")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped")


if __name__ == "__main__":
    start_server()
