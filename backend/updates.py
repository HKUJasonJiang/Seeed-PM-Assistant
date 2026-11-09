"""Checkpointed, explicitly triggered updates. The live base is replaced only at commit."""
from collections import Counter
from contextlib import closing
import copy
from datetime import datetime, timezone
import hashlib
import json
import math
import re
import sqlite3
import threading
import time
from .storage import Problem, packed, write, read_json, strings
from .storefront import OfficialStore, RateLimit, normalized, extract_detail, unique

CHECK_FIELDS=("name","url","price","maxPrice","currency","imageUrl","groups","paths","summary")
TERMINAL={"idle","done","ready","paused","error"}


def instant(timestamp=None):
    return datetime.fromtimestamp(timestamp or time.time(),timezone.utc).isoformat(timespec="seconds")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def refresh_facts(previous, current, addons, url_index):
    from .extract import COLUMN_FIELDS,column_defaults
    merged={**previous,**current}
    if current.get("storePartStatus","unread")=="unread":
        if previous.get("storePartStatus","unread")!="unread" or previous.get("parts"):
            for key in COLUMN_FIELDS:
                if key in previous:merged[key]=previous[key]
    else:
        for key in COLUMN_FIELDS:
            if key not in current:merged.pop(key,None)
        current_rows=list(merged.get("parts",[]))
        names={row[0].casefold() for row in current_rows}
        sources=previous.get("partSources",{})
        scopes=previous.get("partScopes",{})
        url=previous.get("url","").split("#")[0]
        for name,qty in previous.get("parts",[]):
            source=sources.get(name)
            if not source or name.casefold() in names or (source.split("#")[0]==url and scopes.get(name)!="family"):continue
            current_rows.append([name,qty])
            merged.setdefault("partSources",{})[name]=source
            if name in scopes:merged.setdefault("partScopes",{})[name]=scopes[name]
        if current_rows:merged.update(parts=current_rows,partStatus="present")
    column_defaults(merged)
    old_notes=previous.get("notes",[])
    if not current["details"]:
        merged["details"]=bool(previous.get("details"))
        for k in ("notes","docs","wikiLinks"):
            merged[k]=unique(previous.get(k,[])+current.get(k,[]),"text" if k=="notes" else "url")
        return merged
    # Successfully reading this SKU's page supersedes facts from that page. External manuals
    # and specifically verified Wiki facts keep their own provenance and page numbers.
    product_urls={previous.get("url","").split("#")[0],current["url"].split("#")[0]}
    independent=[n for n in old_notes if n.get("source","").split("#")[0] not in product_urls]
    merged["notes"]=unique(current.get("notes",[])+independent,"text")
    verified=[a for a in previous.get("accessories",[]) if a.get("type")!="商品页 Also Add 加购项"]
    for item in addons:
        target=url_index.get(item["url"].casefold())
        if target and not any(a.get("sku")==target for a in verified):
            verified.append({"sku":target,"name":item["name"],"type":"商品页 Also Add 加购项","source":current["url"]})
    if verified or "accessories" in previous:merged["accessories"]=verified
    if previous.get("missingSummary"):
        missing=[n["text"] for n in merged["notes"] if n.get("kind")=="另购说明"]
        if re.search(r"(?:w/o|without) power adapter",current["name"],re.I):
            missing.insert(0,"Power adapter not included")
        for name,_ in merged["parts"]:
            if re.search(r"not included|sold separately|需另购",name,re.I):missing.append(name)
        merged["missingSummary"]=list(dict.fromkeys(missing))[:4]
    return merged


class Updates:
    def __init__(self,store,remote=None):
        self.store=store
        self.remote=remote or OfficialStore()
        self.file=store.local/"update-state.json"
        self.dbfile=store.local/"update-work.sqlite"
        self.lock=threading.RLock()
        self.thread=None
        self.state=read_json(self.file,{"status":"idle","action":"","phase":"idle","done":0,"total":0,
             "updatedAt":"","retryAt":"","error":"","warnings":[],"warningCount":0,"remaining":0})
        initial=max((p.get("updated") or "" for p in store.catalog["products"]),default="")
        self.state.setdefault("lastCheckedAt",initial)
        self.state.setdefault("lastAppliedAt",initial)
        if self.state["status"]=="running":
            self.set(status="paused",error="INTERRUPTED")
        # Preview rows are disposable. Keep a paused user's work for up to a week.
        if self.dbfile.exists() and self.state["status"]=="done":
            self.dbfile.unlink()
        if self.dbfile.exists() and time.time()-self.dbfile.stat().st_mtime>7*86400:
            self.dbfile.unlink()
            self.set(status="idle",phase="idle",action="",remaining=0,error="",done=0,total=0)

    def connect(self):
        db=sqlite3.connect(self.dbfile,timeout=10)
        db.execute("CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY,v TEXT)")
        db.execute("CREATE TABLE IF NOT EXISTS pending (sku TEXT PRIMARY KEY,p TEXT,done INTEGER DEFAULT 0)")
        db.execute("CREATE TABLE IF NOT EXISTS members (category TEXT,sku TEXT,PRIMARY KEY(category,sku))")
        db.execute("CREATE TABLE IF NOT EXISTS changes (sku TEXT PRIMARY KEY,d TEXT)")
        return db

    @staticmethod
    def get(db,k,default=None):
        row=db.execute("SELECT v FROM kv WHERE k=?",(k,)).fetchone()
        return json.loads(row[0]) if row else default

    @staticmethod
    def put(db,k,v):
        db.execute("INSERT OR REPLACE INTO kv VALUES (?,?)",(k,json.dumps(v,ensure_ascii=False)))

    def set(self,**changes):
        with self.lock:
            self.state.update(changes)
            self.state["remaining"]=max(0,self.state.get("total",0)-self.state.get("done",0))
            write(self.file,packed(self.state))

    def status(self):
        with self.lock:
            data=copy.deepcopy(self.state)
            data["changes"]=[]
            if self.dbfile.exists() and data["status"]=="ready":
                with closing(self.connect()) as db:
                    data["changes"]=[json.loads(v) for (v,) in db.execute("SELECT d FROM changes ORDER BY sku")]
            return data

    def start(self,request):
        action=request.get("action")
        if action not in {"preview","apply","refresh","resume"}:raise Problem("INVALID_UPDATE_ACTION")
        with self.lock:
            if self.state["status"]=="running":raise Problem("UPDATE_RUNNING",409)
            retry=self.state.get("retryAt")
            if retry and datetime.fromisoformat(retry).timestamp()>time.time():raise Problem("STORE_RATE_LIMIT",429)
            skus=strings(request.get("skus",[]),20000)
            cats=strings(request.get("categories",[]),500)
            if action=="resume":
                if self.state["status"] not in {"paused","error"} or not self.dbfile.is_file():raise Problem("NO_UPDATE_TO_RESUME",409)
            elif action=="apply":
                if self.state["status"]!="ready" or not (skus or cats):raise Problem("SELECT_PREVIEW_CHANGES",409)
                with closing(self.connect()) as db:
                    chosen=[]
                    for sku,d in db.execute("SELECT sku,d FROM changes"):
                        change=json.loads(d)
                        if sku in skus or set(cats).intersection(change["groups"]):
                            if change["kind"]!="missing":chosen.append(sku)
                    if not chosen:raise Problem("NO_APPLICABLE_CHANGES",409)
                    with db:
                        db.execute("CREATE TEMP TABLE chosen(sku TEXT PRIMARY KEY)")
                        db.executemany("INSERT INTO chosen VALUES (?)",[(s,) for s in chosen])
                        db.execute("DELETE FROM pending WHERE sku NOT IN (SELECT sku FROM chosen)")
                        self.put(db,"phase","details")
                self.state.update(action=action,phase="details",done=0,total=len(chosen))
            else:
                if self.dbfile.exists(): self.dbfile.unlink()
                with closing(self.connect()) as db,db:
                    self.put(db,"baseDigest",digest(self.store.catalog_file))
                    self.put(db,"scope",{"skus":skus,"categories":cats})
                    self.put(db,"phase","categories")
                    self.put(db,"full",action=="preview" or not (skus or cats))
                self.state.update(action=action,phase="categories",done=0,total=0)
                self.state.update(warnings=[],warningCount=0)
            self.set(status="running",error="",retryAt="")
            self.thread=threading.Thread(target=self.run,daemon=True)
            self.thread.start()
            return self.status()

    def warn(self,sku,code):
        with self.lock:
            self.state["warningCount"]+=1
            if len(self.state["warnings"])<50:self.state["warnings"].append({"sku":sku,"code":code})

    def checkpoints(self,db,phase):
        self.put(db,"phase",phase)
        db.commit()

    def group_stage(self,db):
        scope=self.get(db,"scope")
        full=self.get(db,"full")
        cats=self.get(db,"cats")
        if cats is None:
            cats=self.remote.categories() if full or scope["categories"] else []
            if not full:
                cats=[c for c in cats if c["name"] in scope["categories"]]
                if set(scope["categories"])-{c["name"] for c in cats}:raise Problem("UNKNOWN_CATEGORY")
            self.put(db,"cats",cats)
            db.commit()
        current=self.get(db,"categoryIndex",0)
        self.set(phase="categories",done=current,total=len(cats))
        for i in range(current,len(cats)):
            c=cats[i]
            page=self.get(db,"categoryPage",1)
            while True:
                items,total,last=self.remote.category_page(c["id"],page)
                with db:
                    db.executemany("INSERT OR IGNORE INTO members VALUES (?,?)",[(c["name"],s) for s in items])
                    if page>=last:
                        count=db.execute("SELECT COUNT(*) FROM members WHERE category=?",(c["name"],)).fetchone()[0]
                        if count!=total:raise Problem("STORE_CATALOG_CHANGED",409)
                        self.put(db,"categoryIndex",i+1)
                        self.put(db,"categoryPage",1)
                        break
                    page+=1
                    self.put(db,"categoryPage",page)
            self.set(done=i+1)
        self.checkpoints(db,"inventory")

    def inventory_stage(self,db):
        full=self.get(db,"full")
        scope=self.get(db,"scope")
        old=self.store.by_sku
        cats={c["name"] for c in self.get(db,"cats",[])}
        wanted=sorted(set(scope["skus"])|{s for s, in db.execute("SELECT DISTINCT sku FROM members")}) if not full else []
        page=self.get(db,"listPage",1)
        if not full and not wanted:raise Problem("NO_MATCHING_PRODUCTS")
        while True:
            only=None if full else wanted[(page-1)*50:page*50]
            result,total,last=self.remote.listing(page if full else 1,only)
            logical_last=last if full else (len(wanted)+49)//50
            self.set(phase="inventory",done=page-1,total=logical_last)
            with db:
                for r in result:
                    sku=r["sku"]
                    previous=old.get(sku.casefold(),{})
                    p=normalized(r,previous)
                    memberships=[c for c, in db.execute("SELECT category FROM members WHERE sku=?",(sku,))]
                    p["groups"]=sorted(set(memberships) | (set(previous.get("groups",[]))-cats if not full else set()))
                    db.execute("INSERT OR REPLACE INTO pending(sku,p) VALUES (?,?)",(sku,packed(p)))
                if page>=logical_last:
                    count=db.execute("SELECT COUNT(*) FROM pending").fetchone()[0]
                    if full and (count!=total or total==0):raise Problem("STORE_CATALOG_CHANGED",409)
                    if not full:
                        got={s for s, in db.execute("SELECT sku FROM pending")}
                        for s in set(wanted)-got:self.warn(s,"NOT_IN_CURRENT_STORE")
                    break
                page+=1
                self.put(db,"listPage",page)
        self.checkpoints(db,"diff" if self.state["action"]=="preview" else "details")

    def make_diff(self,db):
        found=set()
        old=self.store.by_sku
        db.execute("DELETE FROM changes")
        def add(change):
            db.execute("INSERT INTO changes VALUES (?,?)",(change["sku"],packed(change)))
        for sku,raw in db.execute("SELECT sku,p FROM pending"):
            new=json.loads(raw)
            prev=old.get(sku.casefold(),{})
            found.add(sku.casefold())
            def value(obj,k):
                v=obj.get(k)
                return sorted(v or []) if k in ("groups","paths") else v
            fields=[k for k in CHECK_FIELDS if value(new,k)!=value(prev,k)]
            if not prev or fields:
                add({"sku":sku,"name":new["name"],"groups":new["groups"],"kind":"changed" if prev else "new",
                     "fields":fields,"diff":{k:{"before":prev.get(k),"after":new.get(k)} for k in fields}})
        for key,p in old.items():
            if key not in found:add({"sku":p["sku"],"name":p["name"],"groups":p.get("groups",[]),"kind":"missing","fields":[],"diff":{}})
        db.execute("DELETE FROM pending WHERE sku NOT IN (SELECT sku FROM changes)")
        self.checkpoints(db,"preview")
        self.set(status="ready",phase="preview",done=len(found),total=len(found),updatedAt=instant(),lastCheckedAt=instant())

    def details(self,db):
        old=self.store.by_sku
        total=db.execute("SELECT COUNT(*) FROM pending").fetchone()[0]
        completed=db.execute("SELECT COUNT(*) FROM pending WHERE done=1").fetchone()[0]
        self.set(phase="details",done=completed,total=total)
        url_index={p.get("url","").casefold():p["sku"] for p in old.values() if p.get("url") and not p.get("sharedUrl")}
        image_map={} if self.state["action"]=="refresh" else {p.get("imageUrl"):p["image"] for p in old.values() if p.get("image") and p.get("imageUrl") and (self.store.root/p["image"]).is_file()}
        for (raw,) in db.execute("SELECT p FROM pending WHERE done=1"):
            staged=json.loads(raw)
            if staged.get("image") and staged.get("imageUrl"):image_map[staged["imageUrl"]]=staged["image"]
        skus=[s for s, in db.execute("SELECT sku FROM pending WHERE done=0 ORDER BY sku")]
        for sku in skus:
            p=json.loads(db.execute("SELECT p FROM pending WHERE sku=?",(sku,)).fetchone()[0])
            previous=old.get(sku.casefold(),{})
            addons=[]
            if p["url"]:
                try:
                    sections=self.remote.detail(p["url"],sku)
                    extract_detail(p,sections)
                    addons=sections.get("addons",[])
                except Problem as e:
                    if e.code in {"STORE_UNREACHABLE","STORE_HTTP_500","STORE_HTTP_502","STORE_HTTP_503","STORE_HTTP_504"}:raise
                    self.warn(sku,e.code)
            else:self.warn(sku,"NO_PRODUCT_URL")
            if p.get("storePartStatus","unread")=="unread" and p.get("storeId"):
                from .extract import install_column
                try:
                    ident=p["storeId"]
                    fields=self.remote.section_batch([ident])
                    if ident in fields:install_column(p,fields[ident])
                except Problem as e:self.warn(sku,e.code)
            merged=refresh_facts(previous,p,addons,url_index)
            from .r1000_evidence import enrich_r1000
            enrich_r1000(merged,old)
            merged["image"]=""
            if p["imageUrl"]:
                try:
                    image=image_map.get(p["imageUrl"]) or self.remote.main_image(p["imageUrl"],self.store.root)
                    image_map[p["imageUrl"]]=image
                    merged["image"]=image
                except Problem as e:
                    self.warn(sku,e.code)
                    merged["image"]=previous.get("image","")
                    if merged["image"]:merged["imageUrl"]=previous.get("imageUrl","")
            with db: db.execute("UPDATE pending SET done=1,p=? WHERE sku=?",(packed(merged),sku))
            completed+=1
            self.set(done=completed)
        self.checkpoints(db,"commit")

    def commit(self,db):
        if self.get(db,"baseDigest")!=digest(self.store.catalog_file):
            if self.get(db,"newDigest")==digest(self.store.catalog_file):
                self.clean_images()
                return
            raise Problem("LOCAL_CATALOG_CHANGED",409)
        base=copy.deepcopy(self.store.catalog)
        by_sku={p["sku"].casefold():p for p in base["products"]}
        by_sku.update({sku.casefold():json.loads(raw) for sku,raw in db.execute("SELECT sku,p FROM pending WHERE done=1")})
        products=list(by_sku.values())
        base["products"]=products
        urls=Counter(p.get("url") for p in products if p.get("url"))
        for p in products:
            if urls.get(p.get("url"),0)>1:p["sharedUrl"]=True
            else:p.pop("sharedUrl",None)
        cats={c["name"]:c for c in base["categories"]}
        for c in self.get(db,"cats",[]):cats.setdefault(c["name"],{"name":c["name"],"url":c["url"]})
        for key,c in cats.items():
            members=[p for p in products if key in p.get("groups",[])]
            c.update(count=len(members),sections=sum(bool(p.get("details")) for p in members),parts=sum(bool(p.get("parts")) for p in members))
        base["categories"]=list(cats.values())
        stats=base["stats"]
        stats.update(total=len(products),menu=sum(bool(p.get("groups")) for p in products),
                     prices=sum((p.get("price") or 0)>0 for p in products),
                     wikiFacts=sum(bool(p.get("wikiEvidence")) for p in products),
                     wikiLinked=sum(bool(p.get("wikiEvidence") or p.get("wikiLinks")) for p in products))
        for name,k in (("sections","details"),("images","image"),("officialImages","imageUrl"),("parts","parts"),("urls","url"),("documents","docs")):
            stats[name]=sum(bool(p.get(k)) for p in products)
        from .extract import section_counts
        section_counts(base)
        from .storage import CATALOG_PREFIX
        self.put(db,"newDigest",hashlib.sha256(CATALOG_PREFIX.encode()+packed(base)+b";\n").hexdigest())
        db.commit()
        self.store.commit_catalog(base)
        self.clean_images()

    def clean_images(self):
        # Only generated image names may be removed. User uploads live separately.
        with self.store.lock:
            refs={p.get("image") for p in self.store.catalog["products"]}
            refs.update(p.get("image") for p in self.store.state["overrides"].values())
            for jpg in (self.store.root/"data/jpg").glob("*.jpg"):
                if re.fullmatch(r"[a-f0-9]{20,64}\.jpg",jpg.name) and "data/jpg/"+jpg.name not in refs:jpg.unlink(missing_ok=True)

    def run(self):
        try:
            with closing(self.connect()) as db:
                phase=self.get(db,"phase")
                if phase=="categories": self.group_stage(db);phase=self.get(db,"phase")
                if phase=="inventory": self.inventory_stage(db);phase=self.get(db,"phase")
                if phase=="diff": self.make_diff(db);return
                if phase=="preview":
                    self.set(status="ready",phase="preview",error="",lastCheckedAt=instant(),updatedAt=instant())
                    return
                if phase=="details": self.details(db);phase=self.get(db,"phase")
                if phase=="commit": self.commit(db)
            with self.lock:
                stamp=instant()
                self.set(status="done",phase="complete",updatedAt=stamp,lastAppliedAt=stamp,
                         lastCheckedAt=stamp if self.state["action"]=="refresh" else self.state["lastCheckedAt"],error="")
                self.dbfile.unlink(missing_ok=True)
        except RateLimit as e:
            self.set(status="paused",error="STORE_RATE_LIMIT",retryAt=instant(math.ceil(e.until)))
        except (ImportError,ModuleNotFoundError):
            self.set(status="error",error="UPDATE_RUNTIME_REQUIRED")
        except Problem as e:
            self.set(status="error",error=e.code)
        except (ValueError,KeyError,TypeError,IndexError):
            self.set(status="error",error="STORE_API_CHANGED")
        except Exception:
            self.set(status="error",error="UPDATE_FAILED")
