#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地预览服务器（双栈：127.0.0.1 + [::1]）
1) 双栈绑定：避免 localhost 被解析成 IPv6 后落到其它项目的服务器上。
2) 支持 HTTP Range（206）：音频「点读某一句」必须能 seek 到文件中段，
   Python 自带的 SimpleHTTPRequestHandler 不支持 Range，会导致 seek 失败、
   音频总是从 0 秒开始播。

用法:  python serve.py [端口]
默认端口 8791
"""
import io
import os
import re
import socket
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8791

RANGE_RE = re.compile(r"bytes\s*=\s*(\d*)\s*-\s*(\d*)\s*$", re.I)


class _Slice(io.RawIOBase):
    """只读文件的一个字节区间，供 shutil.copyfileobj 消费。"""

    def __init__(self, f, start, length):
        self._f = f
        self._left = length
        f.seek(start)

    def readable(self):
        return True

    def read(self, n=-1):
        if self._left <= 0:
            return b""
        if n is None or n < 0 or n > self._left:
            n = self._left
        data = self._f.read(n)
        self._left -= len(data)
        return data

    def close(self):
        try:
            self._f.close()
        finally:
            super().close()


class Handler(SimpleHTTPRequestHandler):
    """带正确 MIME + Range 支持 + 合理缓存策略的静态处理器。"""

    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".js": "application/javascript; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".mp3": "audio/mpeg",
        ".css": "text/css; charset=utf-8",
        ".html": "text/html; charset=utf-8",
    }

    def end_headers(self):
        self.send_header("Accept-Ranges", "bytes")
        p = self.path.split("?")[0].lower()
        if p.endswith(".mp3"):
            # 音频要可缓存，否则每次 seek 都重新拉流
            self.send_header("Cache-Control", "public, max-age=3600")
        else:
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.send_header("Pragma", "no-cache")
        super().end_headers()

    def send_head(self):
        rng = self.headers.get("Range")
        if not rng:
            return super().send_head()

        m = RANGE_RE.match(rng.strip())
        path = self.translate_path(self.path)
        if not m or os.path.isdir(path):
            return super().send_head()

        try:
            f = open(path, "rb")
        except OSError:
            self.send_error(404, "File not found")
            return None

        try:
            st = os.fstat(f.fileno())
            size = st.st_size
            g1, g2 = m.group(1), m.group(2)

            if g1 == "":                       # bytes=-N → 末尾 N 字节
                length = min(int(g2 or 0), size)
                start = size - length
                end = size - 1
            else:
                start = int(g1)
                end = min(int(g2), size - 1) if g2 else size - 1
                length = end - start + 1

            if start >= size or length <= 0:
                self.send_response(416)
                self.send_header("Content-Range", "bytes */%d" % size)
                self.send_header("Content-Length", "0")
                self.end_headers()
                f.close()
                return None

            self.send_response(206)
            self.send_header("Content-Type", self.guess_type(path))
            self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
            self.send_header("Content-Length", str(length))
            self.send_header("Last-Modified", self.date_time_string(st.st_mtime))
            self.end_headers()
            return _Slice(f, start, length)
        except Exception:
            f.close()
            raise

    def log_message(self, fmt, *args):  # 静音访问日志
        pass


class V4Server(ThreadingHTTPServer):
    address_family = socket.AF_INET
    daemon_threads = True
    allow_reuse_address = True


class V6Server(ThreadingHTTPServer):
    address_family = socket.AF_INET6
    daemon_threads = True
    allow_reuse_address = True


def main():
    handler = partial(Handler, directory=ROOT)
    servers = []

    try:
        s4 = V4Server(("127.0.0.1", PORT), handler)
        servers.append(("IPv4 127.0.0.1", s4))
    except OSError as e:
        print(f"[warn] IPv4 bind failed: {e}", flush=True)

    try:
        s6 = V6Server(("::1", PORT), handler)
        servers.append(("IPv6 [::1]", s6))
    except OSError as e:
        print(f"[warn] IPv6 bind failed: {e}", flush=True)

    if not servers:
        print(f"[fatal] port {PORT} unavailable on both stacks")
        sys.exit(1)

    for name, srv in servers:
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        print(f"[ok] serving {name}:{PORT}", flush=True)

    print(f"[ok] root = {ROOT}  (Range/206 enabled)", flush=True)
    print(f"[ok] open http://127.0.0.1:{PORT}/", flush=True)

    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        for _, srv in servers:
            srv.shutdown()


if __name__ == "__main__":
    main()
