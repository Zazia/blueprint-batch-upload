import http.server
import os
import sys
from datetime import datetime
from urllib.parse import unquote, urlparse

OUT_DIR = r'c:\Users\Administrator\Documents\图审打包\page_export'
PORT = 8766

os.makedirs(OUT_DIR, exist_ok=True)


class Handler(http.server.BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/ping':
            self.send_response(200)
            self._cors()
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write('pong'.encode('utf-8'))
        else:
            self.send_response(404)
            self._cors()
            self.end_headers()

    def do_POST(self):
        length = int(self.headers.get('Content-Length') or 0)
        body = self.rfile.read(length)
        name = unquote(urlparse(self.path).path.strip('/').replace('/', '_')) or 'unnamed'
        ts = datetime.now().strftime('%H%M%S')
        path = os.path.join(OUT_DIR, f'{name}.json')
        with open(path, 'wb') as f:
            f.write(body)
        print(f'[{ts}] saved {len(body)} bytes -> {path}', flush=True)
        self.send_response(200)
        self._cors()
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def log_message(self, fmt, *args):
        pass


if __name__ == '__main__':
    server = http.server.ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
    print(f'receiver listening on http://127.0.0.1:{PORT}, out dir: {OUT_DIR}', flush=True)
    server.serve_forever()
