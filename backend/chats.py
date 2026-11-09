"""Local conversations. One successful send commits its turn and retry receipt together."""
from contextlib import closing
from datetime import datetime,timezone
import hashlib
import json
import re
import sqlite3
import uuid
from .chat_context import redact,respond
from .storage import Problem,field,packed


MAX_CHATS=200
MAX_TURNS=150


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class Chats:
    def __init__(self,store,send_lock,completion=None):
        self.store=store
        self.send_lock=send_lock
        self.completion=completion
        self.file=store.local/"chats.sqlite3"
        with closing(self.connect()) as db,db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS chats(id TEXT PRIMARY KEY,title TEXT,auto_title INTEGER,created TEXT,updated TEXT);
                CREATE TABLE IF NOT EXISTS turns(chat TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
                    request TEXT NOT NULL, fingerprint TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(chat,request));
            """)

    def connect(self):
        db=sqlite3.connect(self.file,timeout=5)
        db.execute("PRAGMA foreign_keys=ON")
        return db

    @staticmethod
    def snapshot(db,ident,full):
        row=db.execute("SELECT id,title,created,updated FROM chats WHERE id=?",(ident,)).fetchone()
        if not row:raise Problem("UNKNOWN_CHAT",404)
        count=db.execute("SELECT COUNT(*) FROM turns WHERE chat=?",(ident,)).fetchone()[0]
        latest=db.execute("SELECT payload FROM turns WHERE chat=? ORDER BY rowid DESC LIMIT 1",(ident,)).fetchone()
        data=dict(zip(("id","title","createdAt","updatedAt"),row))
        data.update(turnCount=count,lastSku=json.loads(latest[0])["sku"] if latest else "")
        if full:
            data["turns"]=[json.loads(raw) for raw, in db.execute("SELECT payload FROM turns WHERE chat=? ORDER BY rowid",(ident,))]
        return data

    def list(self):
        with closing(self.connect()) as db:
            return {"chats":[self.snapshot(db,ident,False) for ident, in db.execute("SELECT id FROM chats ORDER BY updated DESC,rowid DESC")]}

    def create(self,body):
        title=redact(field(body.get("title",""),150))
        stamp=now()
        ident=uuid.uuid4().hex
        default_title="New chat" if body.get("lang")=="en" else "新对话"
        with closing(self.connect()) as db,db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT COUNT(*) FROM chats").fetchone()[0]>=MAX_CHATS:raise Problem("CHAT_LIMIT_REACHED",409)
            db.execute("INSERT INTO chats VALUES (?,?,?,?,?)",(ident,title or default_title,int(not title),stamp,stamp))
            return {"chat":self.snapshot(db,ident,True)}

    def read(self,ident):
        with closing(self.connect()) as db:return {"chat":self.snapshot(db,ident,True)}

    def delete(self,ident):
        if not self.send_lock.acquire(blocking=False):raise Problem("AI_REQUEST_RUNNING",409)
        try:
            with closing(self.connect()) as db,db:
                if not db.execute("DELETE FROM chats WHERE id=?",(ident,)).rowcount:raise Problem("UNKNOWN_CHAT",404)
            return {"ok":True}
        finally:self.send_lock.release()

    def send(self,ident,body):
        request=field(body.get("requestId"),100,True)
        if not re.fullmatch(r"[A-Za-z0-9_-]{8,100}",request):raise Problem("INVALID_CHAT_REQUEST")
        field(body.get("query"),4000,True)
        # A retry may come after navigation; it always replays the original snapshot and never pays twice.
        fingerprint=hashlib.sha256(packed({"query":body["query"],"sku":body.get("sku") or ""})).hexdigest()
        if not self.send_lock.acquire(blocking=False):raise Problem("AI_REQUEST_RUNNING",409)
        try:
            with closing(self.connect()) as db:
                prior=db.execute("SELECT fingerprint FROM turns WHERE chat=? AND request=?",(ident,request)).fetchone()
                if prior:
                    if prior[0]!=fingerprint:raise Problem("CHAT_REQUEST_CONFLICT",409)
                    return {"chat":self.snapshot(db,ident,True)}
                chat=self.snapshot(db,ident,True)
                if chat["turnCount"]>=MAX_TURNS:raise Problem("CHAT_TURN_LIMIT",409)
                turn=respond(self.store,body,chat["turns"][-6:],**({"complete":self.completion} if self.completion else {}))
                turn.update(id=request,createdAt=now())
                with db:
                    db.execute("INSERT INTO turns VALUES (?,?,?,?)",(ident,request,fingerprint,packed(turn).decode()))
                    db.execute("UPDATE chats SET title=CASE WHEN auto_title=1 THEN ? ELSE title END,auto_title=0,updated=? WHERE id=?",
                               (turn["query"][:64],turn["createdAt"],ident))
                return {"chat":self.snapshot(db,ident,True)}
        finally:self.send_lock.release()
