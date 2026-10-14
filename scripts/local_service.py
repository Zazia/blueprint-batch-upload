"""Authenticated loopback transport. Never inspects PACK members."""
import argparse
from functools import partial
import hmac
import hashlib
import http.server
import json
from pathlib import Path
import re
import secrets
from urllib.parse import parse_qs, unquote, urlsplit
import uuid


class Handler(http.server.BaseHTTPRequestHandler):
    def __init__(self, *args, root, origin, token, mode, allowed=None, max_bytes=8388608, **kwargs):
        self.root, self.origin, self.token = Path(root).resolve(), origin, token
        self.mode, self.allowed, self.max_bytes = mode, allowed, max_bytes
        super().__init__(*args, **kwargs)

    def log_message(self, *args):
        pass  # Do not log URLs containing per-run tokens.

    def end_headers(self):
        if self.headers.get('Origin') == self.origin:
            self.send_header('Access-Control-Allow-Origin', self.origin)
            self.send_header('Vary', 'Origin')
        self.send_header('Access-Control-Allow-Methods', 'GET, HEAD, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-Upload-Token')
        self.send_header('Access-Control-Expose-Headers', 'X-Content-SHA256')
        super().end_headers()

    def authorized(self):
        value = self.headers.get('X-Upload-Token') or parse_qs(urlsplit(self.path).query).get('token', [''])[0]
        if self.headers.get('Origin') not in (None, self.origin) or not hmac.compare_digest(value.encode('utf-8'), self.token.encode('utf-8')):
            self.send_error(403)
            return False
        return True

    def do_OPTIONS(self):
        if self.headers.get('Origin') != self.origin:
            self.send_error(403)
            return
        self.send_response(204)
        self.end_headers()

    def do_HEAD(self):
        self.do_GET(head=True)

    def do_GET(self, head=False):
        if not self.authorized():
            return
        raw = urlsplit(self.path).path
        if self.mode == 'receive':
            if raw != '/ping':
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Length', '4')
            self.end_headers()
            if not head:
                self.wfile.write(b'pong')
            return
        try:
            decoded = unquote(raw, errors='strict').lstrip('/')
            if '\\' in decoded or ':' in decoded or '..' in decoded.split('/') or '\x00' in decoded:
                raise ValueError('invalid path')
            file = (self.root / decoded).resolve(strict=True)
            if not file.is_relative_to(self.root) or not file.is_file():
                raise ValueError('outside base or directory listing')
            if self.allowed is not None and str(file) not in self.allowed:
                raise ValueError('not in allowlist')
            stream = file.open('rb')
        except (ValueError, OSError, UnicodeError):
            self.send_error(404)
            return
        with stream:
            checksum = hashlib.sha256()
            while chunk := stream.read(1048576):
                checksum.update(chunk)
            stream.seek(0)
            self.send_response(200)
            self.send_header('X-Content-SHA256', checksum.hexdigest())
            self.send_header('Content-Type', 'application/octet-stream')
            self.send_header('Content-Length', str(file.stat().st_size))
            self.end_headers()
            if not head:
                while chunk := stream.read(1048576):
                    self.wfile.write(chunk)

    def do_POST(self):
        if not self.authorized():
            return
        if self.mode != 'receive':
            self.send_error(405)
            return
        try:
            name = unquote(urlsplit(self.path).path, errors='strict').removeprefix('/')
            if not re.fullmatch(r'[\w-]{1,100}', name):
                raise ValueError('invalid event name')
            length = int(self.headers.get('Content-Length', '0'))
            if self.headers.get('Transfer-Encoding') or not 0 < length <= self.max_bytes:
                raise ValueError('invalid size')
            self.connection.settimeout(15)
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError('incomplete body')
            obj = json.loads(raw.decode('utf-8-sig'))
            if not isinstance(obj, (dict, list)):
                raise ValueError('object/array required')
            self.root.mkdir(parents=True, exist_ok=True)
            file = self.root / (name + '-' + uuid.uuid4().hex + '.json')
            with file.open('x', encoding='utf-8') as stream:
                json.dump(obj, stream, ensure_ascii=False, indent=2)
        except (ValueError, OSError, UnicodeError):
            self.send_error(400)
            return
        data = json.dumps({'ok': True, 'file': file.name}).encode()
        self.send_response(201)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def make_server(root, origin, token, mode, port=0, allowed=None, max_bytes=8388608):
    return http.server.ThreadingHTTPServer(('127.0.0.1', port), partial(
        Handler, root=root, origin=origin, token=token, mode=mode, allowed=allowed, max_bytes=max_bytes))


def main(mode):
    ap = argparse.ArgumentParser(description='本地文件服务' if mode == 'files' else 'JSON 证据接收服务')
    ap.add_argument('--base' if mode == 'files' else '--out', required=True, dest='root')
    ap.add_argument('--port', type=int, default=8765 if mode == 'files' else 8766)
    ap.add_argument('--origin', required=True)
    ap.add_argument('--token-file', required=True, help='不存在则生成；放在图纸根目录外，不提交 Git')
    ap.add_argument('--allow', help='文件服务允许访问的 JSON 绝对路径数组')
    args = ap.parse_args()
    origin = urlsplit(args.origin)
    if origin.scheme not in ('http', 'https') or not origin.netloc or origin.path or origin.query or origin.fragment:
        ap.error('origin 必须是无路径的站点源')
    root = Path(args.root).resolve()
    if mode == 'files' and not root.is_dir():
        ap.error('文件根目录不存在')
    token_file = Path(args.token_file).resolve()
    if mode == 'files' and token_file.is_relative_to(root):
        ap.error('令牌文件须在对外文件根目录之外')
    if token_file.exists():
        token = token_file.read_text(encoding='utf-8').strip()
        if len(token) < 24:
            ap.error('令牌至少 24 字符')
    else:
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token = secrets.token_urlsafe(32)
        with token_file.open('x', encoding='utf-8') as f:
            f.write(token)
    allowed = None
    if args.allow:
        allowed = {str(Path(p).resolve()) for p in json.loads(Path(args.allow).read_text(encoding='utf-8-sig'))}
    with make_server(root, args.origin, token, mode, args.port, allowed) as server:
        print(f'{mode}: http://127.0.0.1:{server.server_port}; root={root}; token-file={token_file}', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
