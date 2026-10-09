"""本地 CORS 文件服务：让浏览器页面 JS 能 fetch 本地文件。

用途：配合 JGTGL 图纸系统"上传新版"注入上传（见 SKILL.md）。
绑定 127.0.0.1，仅本机可访问。

用法：
    uv run cors_server.py --base "C:\\path\\to\\图纸目录" --port 8765

验证：
    curl -I "http://127.0.0.1:8765/<子目录>/<URL编码文件名>"
"""

import argparse
import http.server
import os
import socketserver
import urllib.parse

class CORSHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, base_dir=None, **kwargs):
        if base_dir:
            super().__init__(*args, directory=base_dir, **kwargs)
        else:
            super().__init__(*args, **kwargs)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def translate_path(self, path):
        return super().translate_path(urllib.parse.unquote(path))

    def log_message(self, fmt, *args):
        print("[serve] %s" % (fmt % args), flush=True)


def main():
    ap = argparse.ArgumentParser(description="本地 CORS 文件服务")
    ap.add_argument("--base", required=True, help="对外提供的根目录（绝对路径）")
    ap.add_argument("--port", type=int, default=8765, help="监听端口，默认 8765")
    args = ap.parse_args()

    base = os.path.abspath(args.base)
    if not os.path.isdir(base):
        raise SystemExit(f"目录不存在: {base}")

    os.chdir(base)

    class Server(socketserver.ThreadingTCPServer):
        allow_reuse_address = True

    with Server(("127.0.0.1", args.port), CORSHandler) as httpd:
        print(f"CORS server serving {base} on http://127.0.0.1:{args.port}", flush=True)
        print("注意：中文/特殊字符文件名需 URL 编码后访问", flush=True)
        httpd.serve_forever()


if __name__ == "__main__":
    main()
