"""Start the local-only Seeed workbench: python -m backend.server --port 8765."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import socket
import sys
import threading
from urllib.parse import urlsplit

from .assistant import answer
from .chats import Chats
from .preview_migration import recover_preview
from .storage import Problem, ROOT, Store, packed
from .updates import Updates

ASSETS={"index.html","app.css","app.js","search.js","product-ui.js","workbench.js","workbench.css","chat.js","chat.css","locale.js","internal-ui.js","internal-ui.css","data/catalog.js","data/accessory-lookup.js"}


class Instance:
    def __init__(self,directory):
        directory.mkdir(parents=True,exist_ok=True)
        self.stream=(directory/"service.lock").open("a+b")
        self.stream.seek(0)
        if not self.stream.read(1):
            self.stream.write(b"1")
            self.stream.flush()
        self.stream.seek(0)
        try:
            if os.name=="nt":
                import msvcrt
                msvcrt.locking(self.stream.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            self.stream.close()
            raise Problem("ALREADY_RUNNING",409)

    def close(self):
        self.stream.close()


class LocalServer(ThreadingHTTPServer):
    allow_reuse_address=False
    daemon_threads=True
    def server_bind(self):
        if not ipaddress.ip_address(self.server_address[0]).is_loopback:
            raise ValueError("Loopback address required")
        if os.name=="nt": self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
        super().server_bind()


class Handler(BaseHTTPRequestHandler):
    server_version="SeeedWorkbench"
    sys_version=""
    def log_message(self,*args):
        pass

    def check_origin(self,mutation=False):
        port=self.server.server_address[1]
        allowed={f"127.0.0.1:{port}",f"localhost:{port}"}
        host=self.headers.get("Host","").lower()
        if host not in allowed:raise Problem("INVALID_HOST",403)
        top_level_entry=(self.command=="GET" and urlsplit(self.path).path in ("/","/index.html")
                         and self.headers.get("Sec-Fetch-Mode")=="navigate"
                         and self.headers.get("Sec-Fetch-Dest")=="document")
        if top_level_entry:
            return
        origin=self.headers.get("Origin")
        if (origin or mutation) and origin!="http://"+host:raise Problem("ORIGIN_REQUIRED",403)
        if self.headers.get("Sec-Fetch-Site")=="cross-site":raise Problem("ORIGIN_REQUIRED",403)
        if mutation and not secrets.compare_digest(self.headers.get("X-CSRF-Token",""),self.server.store.csrf):
            raise Problem("INVALID_CSRF",403)

    def headers_for(self,status,mime,length):
        self.send_response(status)
        self.send_header("Content-Type",mime)
        self.send_header("Content-Length",str(length))
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Referrer-Policy","no-referrer")
        self.send_header("Cross-Origin-Resource-Policy","same-origin")
        self.send_header("Content-Security-Policy","default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        self.end_headers()

    def reply(self,obj,status=200):
        raw=packed(obj)
        self.headers_for(status,"application/json; charset=utf-8",len(raw))
        if self.command!="HEAD":self.wfile.write(raw)

    def process(self,mutation=False):
        try:
            self.check_origin(mutation)
            path=urlsplit(self.path).path
            chat=re.fullmatch(r"/api/chats/([0-9a-f]{32})(?:/(send|delete))?",path)
            if mutation:
                if self.headers.get_content_type()!="application/json":raise Problem("JSON_REQUIRED",415)
                size=int(self.headers.get("Content-Length","-1"))
                if size<0 or size>(40_000 if chat or path=="/api/chats" else 11_000_000):raise Problem("REQUEST_TOO_LARGE",413)
                try:body=json.loads(self.rfile.read(size))
                except (ValueError,UnicodeError):raise Problem("INVALID_JSON") from None
                if not isinstance(body,dict):raise Problem("INVALID_JSON")
                if path=="/api/ai":
                    if not self.server.ai_lock.acquire(blocking=False):raise Problem("AI_REQUEST_RUNNING",409)
                    try:result=answer(self.server.store,body)
                    finally:self.server.ai_lock.release()
                elif path=="/api/chats":result=self.server.chats.create(body)
                elif chat and chat[2]=="send":result=self.server.chats.send(chat[1],body)
                elif chat and chat[2]=="delete":result=self.server.chats.delete(chat[1])
                elif path=="/api/update": result=self.server.updates.start(body)
                elif path=="/api/internal":
                    if body.get("action")!="import":raise Problem("INVALID_INTERNAL_ACTION")
                    from .storage import field
                    with self.server.store.lock:
                        self.server.store.internal.load(field(body.get("path"),2048,True))
                        self.server.store.internal.apply(self.server.store.catalog)
                        result=self.server.store.internal.public()
                elif path=="/api/internal/assess":
                    from .storage import field, strings
                    with self.server.store.lock:
                        self.server.store.internal.load()
                        self.server.store.internal.apply(self.server.store.catalog)
                        result={"assessments":self.server.store.internal.assess(
                            strings(body.get("skus",[]),30),field(body.get("description",""),12000),body.get("language"),
                            body.get("materials",[]) if isinstance(body.get("materials",[]),list) else [])}
                elif path in {"/api/settings","/api/product","/api/project","/api/favorite"}:
                    result=self.server.store.apply(path.split("/")[-1],body)
                else:raise Problem("UNKNOWN_ROUTE",404)
                self.reply(result)
            elif path=="/api/health": self.reply({"app":"seeed-workbench","version":2})
            elif path=="/api/state": self.reply(self.server.store.public())
            elif path=="/api/internal":
                with self.server.store.lock:
                    self.server.store.internal.load()
                    self.server.store.internal.apply(self.server.store.catalog)
                    self.reply(self.server.store.internal.public())
            elif re.fullmatch(r"/api/internal/source/[a-f0-9]{24}",path):
                self.reply(self.server.store.internal.source(path.rsplit("/",1)[1]))
            elif path=="/api/chats":self.reply(self.server.chats.list())
            elif chat and not chat[2]:self.reply(self.server.chats.read(chat[1]))
            elif path=="/api/update": self.reply(self.server.updates.status())
            else:
                name=path[1:] if path.startswith("/") else path
                name=name or "index.html"
                if name in ASSETS or re.fullmatch(r"data/jpg/[0-9a-f]{20,64}\.jpg",name):
                    root=self.server.store.root
                elif re.fullmatch(r"user-images/[0-9a-f]{64}\.jpg",name): root=self.server.store.local
                else:raise Problem("NOT_FOUND",404)
                f=(root/name).resolve()
                if not f.is_relative_to(root) or not f.is_file():raise Problem("NOT_FOUND",404)
                mime=mimetypes.guess_type(f.name)[0] or "application/octet-stream"
                if f.suffix==".js":mime="application/javascript; charset=utf-8"
                body=f.read_bytes()
                self.headers_for(200,mime,len(body))
                if self.command!="HEAD":self.wfile.write(body)
        except Problem as error:self.reply({"error":error.code},error.status)
        except (BrokenPipeError,ConnectionResetError):pass
        except (ValueError,TypeError):self.reply({"error":"INVALID_FIELD"},400)
        except Exception:self.reply({"error":"LOCAL_SERVICE_ERROR"},500)

    def do_GET(self):self.process()
    def do_HEAD(self):self.process()
    def do_POST(self):self.process(True)
    def do_OPTIONS(self):self.reply({"error":"ORIGIN_REQUIRED"},403)


def create(port,data_dir,root=ROOT):
    server=LocalServer(("127.0.0.1",port),Handler)
    try:
        server.instance=Instance(Path(data_dir))
        recover_preview(Path(root)/"data"/"catalog.js",Path(data_dir))
        server.store=Store(data_dir,root)
        server.updates=Updates(server.store)
        server.ai_lock=threading.Lock()
        server.chats=Chats(server.store,server.ai_lock)
        return server
    except BaseException:
        server.server_close()
        if hasattr(server,"instance"):server.instance.close()
        raise


def main():
    parser=argparse.ArgumentParser(description="Seeed local product workbench")
    parser.add_argument("--port",type=int,default=8765)
    parser.add_argument("--data-dir",type=Path,default=None)
    parser.add_argument("--root",type=Path,default=ROOT,help="catalogue root (for isolated test installations)")
    args=parser.parse_args()
    try:server=create(args.port,args.data_dir or args.root/".local-workbench",args.root)
    except (OSError,Problem) as exc:
        print(str(exc),file=sys.stderr)
        return 1
    try:
        print("Seeed Workbench: http://127.0.0.1:"+str(server.server_address[1]),flush=True)
        server.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        server.server_close()
        server.instance.close()
    return 0


if __name__=="__main__":raise SystemExit(main())
