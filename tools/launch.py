"""Manage only the loopback service belonging to this specific project and data folder."""
import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import threading
import time
from urllib.error import HTTPError
from urllib.parse import parse_qs,urlsplit
from urllib.request import ProxyHandler,Request,build_opener
import webbrowser

ROOT=Path(__file__).resolve().parents[1]
HTTP=build_opener(ProxyHandler({}))
DEFAULT_PORT=8765


def arguments():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port",type=int,help="Request this exact port (defaults to 8765, with automatic fallback)")
    parser.add_argument("--data-dir",type=Path,default=ROOT/".local-workbench")
    parser.add_argument("--no-browser",action="store_true")
    parser.add_argument("--stop",action="store_true")
    parser.add_argument("--serve",action="store_true",help=argparse.SUPPRESS)
    args=parser.parse_args()
    if args.port is not None and not 1<=args.port<=65535:parser.error("port must be 1 to 65535")
    args.data_dir=args.data_dir.resolve()
    return args


def address(port):return "http://127.0.0.1:"+str(port)


def identity(data_dir):
    return hashlib.sha256((os.path.normcase(str(ROOT))+"\n"+os.path.normcase(str(data_dir))).encode()).hexdigest()


def marker(data_dir):return data_dir/"launcher-instance.json"


def read_record(data_dir):
    try:
        value=json.loads(marker(data_dir).read_bytes())
        if (isinstance(value,dict) and value.get("folder")==identity(data_dir) and type(value.get("port")) is int
                and 0<value["port"]<65536 and isinstance(value.get("secret"),str) and len(value["secret"])==64):
            return value
    except (ValueError,OSError):pass
    return None


def proof(secret,purpose,nonce):
    return hmac.new(secret.encode(),(purpose+":"+nonce).encode(),hashlib.sha256).hexdigest()


def current(data_dir):
    rec=read_record(data_dir)
    if not rec:return None
    nonce=secrets.token_hex(16)
    try:
        url=address(rec["port"])+"/api/launcher?challenge="+nonce
        with HTTP.open(url,timeout=1.2) as res:data=json.loads(res.read(1024))
        if hmac.compare_digest(data["proof"],proof(rec["secret"],"identify",nonce)):return rec
    except (OSError,ValueError,KeyError,TypeError):pass
    return None


def open_existing(args):
    rec=current(args.data_dir)
    if not rec:return None
    if args.port is not None and args.port!=rec["port"]:
        print("This folder already runs on "+address(rec["port"])+". Run Stop Assistant before changing the port.",file=sys.stderr)
        return 1
    url=address(rec["port"])+"/"
    print(url,flush=True)
    if not args.no_browser:webbrowser.open(url)
    return 0


def locked(data_dir):
    if not (data_dir/"service.lock").exists():return False
    import msvcrt
    try:
        with (data_dir/"service.lock").open("r+b") as f:
            msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
            f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
        return False
    except OSError:return True


def stop(args):
    rec=current(args.data_dir)
    if not rec:
        if locked(args.data_dir):
            print("This folder is busy in an older workbench or is still starting. Finish its work before closing the old service or restarting Windows.",file=sys.stderr)
            return 2
        print("This workbench is already stopped.")
        return 0
    if args.port is not None and args.port!=rec["port"]:
        print("The specified port does not belong to this folder.",file=sys.stderr)
        return 1
    nonce=secrets.token_hex(16)
    base=address(rec["port"])
    req=Request(base+"/api/launcher/stop",data=b"",method="POST",headers={"Origin":base,"X-Launcher-Challenge":nonce,
                            "X-Launcher-Proof":proof(rec["secret"],"stop",nonce)})
    try:
        with HTTP.open(req,timeout=4) as res:res.read(512)
    except HTTPError as e:
        if e.code==409:print("An update, AI reply or save is in progress. Let it finish, then run Stop Assistant again.",file=sys.stderr)
        else:print("This service could not verify the stop request.",file=sys.stderr)
        return 2
    except OSError:
        print("Could not contact this workbench. Try Stop Assistant again.",file=sys.stderr)
        return 1
    until=time.monotonic()+10
    while locked(args.data_dir) and time.monotonic()<until:time.sleep(.1)
    if locked(args.data_dir):
        print("Shutdown is still finishing. Wait before copying or replacing this folder.",file=sys.stderr)
        return 2
    print("Stopped. You can now back up this folder or install an update.")
    return 0


def serve(args):
    sys.path.insert(0,str(ROOT))
    from backend.server import Handler,create
    from backend.storage import Problem,packed,write
    try:
        try:server=create(args.port or DEFAULT_PORT,args.data_dir,ROOT)
        except OSError:
            if args.port is not None:raise
            server=create(0,args.data_dir,ROOT)
    except Problem as e:
        return 3 if e.code=="ALREADY_RUNNING" else 1
    except OSError:return 4
    rec={"folder":identity(args.data_dir),"port":server.server_port,"secret":secrets.token_hex(32)}
    gate=threading.Lock()
    active=0
    closing=False

    class ManagedHandler(Handler):
        def process(self,mutation=False):
            nonlocal active,closing
            path=urlsplit(self.path)
            if path.path in {"/api/launcher","/api/launcher/stop"}:
                try:
                    self.check_origin()
                    if not mutation and path.path=="/api/launcher":
                        nonce=parse_qs(path.query).get("challenge",[""])[0]
                        if not re.fullmatch("[0-9a-f]{32}",nonce):raise Problem("INVALID_REQUEST",400)
                        self.reply({"proof":proof(rec["secret"],"identify",nonce)})
                    elif mutation and path.path=="/api/launcher/stop":
                        nonce=self.headers.get("X-Launcher-Challenge","")
                        signature=self.headers.get("X-Launcher-Proof","")
                        if (self.headers.get("Origin")!=address(rec["port"]) or not re.fullmatch("[0-9a-f]{32}",nonce) or
                            not re.fullmatch("[0-9a-f]{64}",signature) or not hmac.compare_digest(signature,proof(rec["secret"],"stop",nonce))):
                            raise Problem("STOP_DENIED",403)
                        with gate:
                            if active or server.ai_lock.locked() or server.updates.state["status"]=="running" or (server.updates.thread and server.updates.thread.is_alive()):
                                raise Problem("WORK_IN_PROGRESS",409)
                            closing=True
                        threading.Thread(target=server.shutdown,daemon=True).start()
                        self.reply({"stopping":True})
                    else:raise Problem("NOT_FOUND",404)
                except Problem as e:self.reply({"error":e.code},e.status)
                return
            if not mutation:return super().process(False)
            with gate:
                if closing:return self.reply({"error":"SERVICE_STOPPING"},503)
                active+=1
            try:super().process(True)
            finally:
                with gate:active-=1

    try:
        server.RequestHandlerClass=ManagedHandler
        write(marker(args.data_dir),packed(rec))
        server.serve_forever(poll_interval=.15)
    finally:
        server.server_close()
        if read_record(args.data_dir)==rec:marker(args.data_dir).unlink(missing_ok=True)
        server.instance.close()
    return 0


def launch():
    args=arguments()
    if args.serve:return serve(args)
    if args.stop:return stop(args)
    existing=open_existing(args)
    if existing is not None:return existing
    command=[sys.executable,"-I","-B",str(Path(__file__).resolve()),"--serve","--data-dir",str(args.data_dir)]
    if args.port is not None:command.extend(["--port",str(args.port)])
    child=subprocess.Popen(command,cwd=ROOT,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                           creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
    until=time.monotonic()+28
    while time.monotonic()<until:
        existing=open_existing(args)
        if existing is not None:return existing
        code=child.poll()
        if code is not None and code!=3:break
        if code==3 and not read_record(args.data_dir):
            # Concurrent launch can briefly hold the instance lock before its marker is written.
            if time.monotonic()>until-24:break
        time.sleep(.2)
    if child.poll()==4:print("This port is unavailable. Close the other application or start without --port to choose an available port.",file=sys.stderr)
    elif child.poll()==3:print("Another service already uses this data folder. Finish its work, then stop the previous service before starting this version.",file=sys.stderr)
    else:print("Could not start the workbench. Check folder access and that data/catalog.js was extracted with the application.",file=sys.stderr)
    return 1


if __name__=="__main__":raise SystemExit(launch())
