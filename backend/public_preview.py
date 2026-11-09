"""Serve a read-only public snapshot on this computer without opening a workspace profile."""
import argparse
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import re
from urllib.parse import urlsplit

from .storage import ROOT


ASSETS={"index.html","app.css","app.js","search.js","product-ui.js","workbench.css","chat.css","locale.js"}
TYPES={".js":"text/javascript; charset=utf-8",".html":"text/html; charset=utf-8",".css":"text/css; charset=utf-8",".jpg":"image/jpeg"}


class PublicPage(BaseHTTPRequestHandler):
    def log_message(self,*args):
        pass

    def do_GET(self):
        port=self.server.server_port
        if self.headers.get("Host") not in {f"127.0.0.1:{port}",f"localhost:{port}"}:
            self.send_error(403);return
        path=urlsplit(self.path).path
        if path in {"/","/index.html"}:
            file=ROOT/"index.html"
        elif re.fullmatch(r"/data/jpg/[a-f0-9]{64}\.jpg",path):
            file=ROOT/path[1:]
            if not file.is_file():file=self.server.candidate.parent/"jpg"/file.name
        elif path=="/data/catalog.js":
            file=self.server.candidate
        elif path[1:] in ASSETS:
            file=ROOT/path[1:]
        else:
            self.send_error(404);return
        try:raw=file.read_bytes()
        except OSError:self.send_error(404);return
        if file.name=="index.html":
            raw=raw.replace(b"<head>",b'<head><meta name="seeed-public-preview" content="1">')
            for script in (b"workbench.js",b"chat.js"):
                raw=raw.replace(b'<script src="'+script+b'"></script>',b"")
        self.send_response(200)
        self.send_header("Content-Type",TYPES[file.suffix])
        self.send_header("Cache-Control","no-store" if file.suffix!=".jpg" else "public, max-age=86400")
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Content-Security-Policy","default-src 'self'; img-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'none'; object-src 'none'; frame-ancestors 'none'")
        self.send_header("Content-Length",str(len(raw)));self.end_headers();self.wfile.write(raw)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--catalog",required=True,type=Path)
    p.add_argument("--port",default=8770,type=int)
    args=p.parse_args()
    with ThreadingHTTPServer(("127.0.0.1",args.port),PublicPage) as server:
        server.candidate=args.catalog.resolve(strict=True)
        server.serve_forever()
