"""Structured catalogue, local overrides and account-bound credential storage."""
import base64
import binascii
import copy
import ctypes
from ctypes import wintypes
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import secrets
import threading
from urllib.parse import urlsplit
import uuid

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PREFIX = "window.SEEED_CATALOG="
PROVIDERS = {
    "deepseek": ("https://api.deepseek.com/chat/completions", "deepseek-flash"),
    "doubao": ("https://ark.cn-beijing.volces.com/api/v3/chat/completions", "doubao-seed-2-0-mini-260428"),
}


class Problem(Exception):
    def __init__(self, code, status=400):
        super().__init__(code)
        self.code = code
        self.status = status


def packed(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()


def write(path, body):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with tmp.open("xb") as dst:
            dst.write(body)
            dst.flush()
            os.fsync(dst.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def read_json(path, default):
    return json.loads(path.read_bytes()) if path.is_file() else copy.deepcopy(default)


def field(value, limit, required=False):
    if not isinstance(value, str) or len(value) > limit:
        raise Problem("INVALID_FIELD")
    result = value.strip()
    if required and not result:
        raise Problem("REQUIRED_FIELD")
    return result


def strings(values, limit=100):
    if not isinstance(values, list) or len(values) > limit:
        raise Problem("INVALID_LIST")
    return list(dict.fromkeys(field(s, 160, required=True) for s in values))


def https_url(value):
    value = field(value, 2048)
    if not value:
        return ""
    try:
        u = urlsplit(value)
        valid = u.scheme == "https" and u.hostname and not u.username and not u.password and u.port in (None, 443)
    except ValueError:
        valid = False
    if not valid or re.search(r"[\s\\<>]", value):
        raise Problem("INVALID_URL")
    return value


class Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("pointer", ctypes.POINTER(ctypes.c_ubyte))]


def protect(raw, decrypt=False):
    if os.name != "nt":
        raise Problem("CREDENTIAL_VAULT_UNAVAILABLE", 503)
    block = (ctypes.c_ubyte * len(raw))(*raw)
    src = Blob(len(raw), block)
    dst = Blob()
    function = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    ok = function(ctypes.byref(src), None, None, None, None, 1, ctypes.byref(dst))
    if not ok:
        raise Problem("CREDENTIAL_VAULT_UNAVAILABLE", 503)
    try:
        return ctypes.string_at(dst.pointer, dst.size)
    finally:
        ctypes.windll.kernel32.LocalFree(ctypes.cast(dst.pointer, ctypes.c_void_p))


def jpeg(raw, size=(900, 700)):
    try:
        from PIL import Image, ImageOps
    except ImportError:
        raise Problem("IMAGE_RUNTIME_REQUIRED", 503)
    if len(raw) > 8_000_000:
        raise Problem("IMAGE_TOO_LARGE", 413)
    try:
        with Image.open(io.BytesIO(raw)) as im:
            if im.width * im.height > 30_000_000:
                raise Problem("IMAGE_TOO_LARGE", 413)
            im = ImageOps.exif_transpose(im)
            im.thumbnail(size, Image.Resampling.LANCZOS)
            rgba = im.convert("RGBA")
            flat = Image.new("RGB", rgba.size, "white")
            flat.paste(rgba, mask=rgba.getchannel("A"))
            buf = io.BytesIO()
            flat.save(buf, "JPEG", quality=83, optimize=True)
            return buf.getvalue()
    except (OSError, ValueError, Image.DecompressionBombError):
        raise Problem("INVALID_IMAGE")


def default_state():
    return {"language":"zh", "provider":"deepseek",
            "models":{k:v[1] for k,v in PROVIDERS.items()}, "vault":{},
            "favorites":[], "projects":[], "overrides":{}}


def customization_info(product):
    url=product.get("url","")
    custom_url=product.get("customUrl") or ""
    if product.get("custom") and urlsplit(custom_url).hostname in {"www.seeedstudio.com","wiki.seeedstudio.com","files.seeedstudio.com"}:
        return {"kind":"series","text":product["custom"],"url":custom_url}
    if urlsplit(url).hostname!="www.seeedstudio.com":return None
    name=re.sub(r"[^a-z0-9]+"," ",product.get("name","").casefold()).strip()
    for note in product.get("notes",[]):
        if note.get("source")!=url or note.get("kind") not in ("定制说明","customization"):continue
        text=note.get("text","").casefold()
        if re.search(r"\bfuture\b|\bplanned\b|not (?:available|supported)|cannot|can't offer",text):continue
        evidence={"kind":"product","text":note["text"],"url":url}
        if "white-label version" in text and "logo customization" in text and "minimum order" in text:return evidence
        target=re.search(r"tailor-make the (\w+)",text)
        if target and target[1] in name.split() and "seeed provides" in text and "manufacturing services" in text:return evidence
        if not re.search(r"\b(?:we|seeed)\b.{0,100}\b(?:provid\w*|offer\w*|assure|promise|can customize)\b", text):continue
        for match in re.finditer(r"customi[sz]ation services? for (?:the )?([^.,;!?()]{2,65})",text):
            label=re.sub(r"[^a-z0-9]+"," ",match[1]).strip()
            if label in {"this product","this device","this board","this module","this sku"}:return evidence
            if len(label)>=5 and re.search(r"\b"+re.escape(label)+r"\b",name):return evidence
    return None


class Store:
    def __init__(self, data_dir, root=ROOT):
        self.root = Path(root).resolve()
        self.local = Path(data_dir).resolve()
        self.local.mkdir(parents=True, exist_ok=True)
        self.state_file = self.local / "workbench.json"
        self.catalog_file = self.root / "data/catalog.js"
        self.lock = threading.RLock()
        self.csrf = secrets.token_urlsafe(32)
        self.state = read_json(self.state_file, default_state())
        source = self.catalog_file.read_text(encoding="utf-8-sig").strip()
        if not source.startswith(CATALOG_PREFIX):
            raise ValueError("Invalid Seeed catalogue")
        self.catalog = json.loads(source[len(CATALOG_PREFIX):].rstrip(";"))
        from .internal_knowledge import InternalKnowledge
        self.internal = InternalKnowledge(self.local)
        self.internal.load()
        self.reindex()

    def reindex(self):
        self.by_sku = {p["sku"].casefold():p for p in self.catalog["products"]}
        self.custom_evidence={p["sku"]:info for p in self.catalog["products"] if (info:=customization_info(p))}
        self.official_custom_skus=set(self.custom_evidence)
        self.internal.apply(self.catalog)

    def effective(self, sku):
        if not isinstance(sku, str):
            raise Problem("INVALID_SKU")
        original = self.by_sku.get(sku.casefold(), {})
        internal = next((p for code,p in self.internal.products.items() if code.casefold()==sku.casefold()), None)
        if not original and internal:
            original = {"sku": internal["sku"], "name": internal["name"], "url": "", "image": "",
                        "groups": [], "paths": [], "summary": "", "parts": [], "accessories": [],
                        "notes": [], "docs": [], "wikiLinks": [], "internalOnly": True}
        canonical = original.get("sku") or next((k for k in self.state["overrides"] if k.casefold()==sku.casefold()), sku)
        override = self.state["overrides"].get(canonical, {})
        if not original and not override:
            raise Problem("UNKNOWN_SKU", 404)
        return {**original, **override, **({"internal": internal} if internal else {})}

    def public(self):
        with self.lock:
            self.internal.load()
            self.internal.apply(self.catalog)
            s = self.state
            return {"csrf":self.csrf, "language":s["language"], "provider":s["provider"],
                    "internalProducts":self.internal.products, "internalSummary":self.internal.summary(),
                    "customizableSkus":sorted(self.official_custom_skus|{sku for sku,p in s["overrides"].items() if p.get("customConfirmed") is True}),
                    "customEvidence":copy.deepcopy(self.custom_evidence),
                    "providers":{k:{"model":s["models"][k], "hasKey":bool(s["vault"].get(k))} for k in PROVIDERS},
                    **{k:copy.deepcopy(s[k]) for k in ("favorites","projects","overrides")}}

    def api_key(self, provider):
        with self.lock:
            secret = self.state["vault"].get(provider)
            if not secret:
                raise Problem("API_KEY_REQUIRED", 409)
            return protect(base64.b64decode(secret), decrypt=True).decode()

    def apply(self, route, body):
        with self.lock:
            updated = copy.deepcopy(self.state)
            if route == "settings":
                self.settings(updated, body)
            elif route == "favorite":
                sku = self.effective(body.get("sku"))["sku"]
                if not isinstance(body.get("active"), bool): raise Problem("INVALID_FIELD")
                updated["favorites"] = [s for s in updated["favorites"] if s != sku]
                if body["active"]: updated["favorites"].append(sku)
            elif route == "project":
                self.project(updated, body)
            elif route == "product":
                self.product(updated, body)
            else:
                raise Problem("UNKNOWN_ROUTE", 404)
            write(self.state_file, packed(updated))
            self.state = updated
            if route == "product": self.clean_user_images()
            return self.public()

    def settings(self, state, body):
        provider = body.get("provider", state["provider"])
        if provider not in PROVIDERS: raise Problem("UNKNOWN_PROVIDER")
        if "language" in body:
            if body["language"] not in ("en","zh","zh-CN"): raise Problem("INVALID_LANGUAGE")
            state["language"] = "en" if body["language"]=="en" else "zh"
        state["provider"] = provider
        if "model" in body:
            model = field(body["model"], 160, required=True)
            if not re.fullmatch(r"[A-Za-z0-9._:-]+", model): raise Problem("INVALID_MODEL")
            state["models"][provider] = model
        if body.get("clearKey") is True:
            state["vault"].pop(provider, None)
        elif body.get("apiKey"):
            secret = field(body["apiKey"], 2048, required=True)
            if not re.fullmatch(r"[!-~]+", secret): raise Problem("INVALID_KEY")
            state["vault"][provider] = base64.b64encode(protect(secret.encode())).decode()

    def eligible(self, p):
        return p.get("customConfirmed") is True or p["sku"] in self.official_custom_skus

    def project(self, state, body):
        requested = body.get("id")
        current = next((p for p in state["projects"] if p["id"]==requested), None)
        if requested and not current: raise Problem("UNKNOWN_PROJECT", 404)
        if body.get("delete") is True:
            if not current: raise Problem("UNKNOWN_PROJECT", 404)
            state["projects"].remove(current)
            return
        members = [self.effective(s) for s in strings(body.get("skus", []))]
        if not members: raise Problem("PROJECT_REQUIRES_SKU")
        for product in members:
            if not self.eligible(product) and product["sku"] not in (current or {}).get("skus",[]):
                raise Problem("CUSTOMIZATION_UNCONFIRMED")
        item = {"id":requested or uuid.uuid4().hex, "title":field(body.get("title"),200,True),
                "description":field(body.get("description",""),12000), "labels":strings(body.get("labels",[]),30),
                "skus":list(dict.fromkeys(p["sku"] for p in members))}
        materials = body.get("materials",(current or {}).get("materials",[]))
        if not isinstance(materials,list) or len(materials)>50:raise Problem("INVALID_MATERIALS")
        item["materials"] = []
        for material in materials:
            if not isinstance(material,dict):raise Problem("INVALID_MATERIALS")
            material_sku = self.effective(material.get("sku"))["sku"]
            host = material.get("hostSku")
            action = material.get("action")
            count = material.get("quantity",1)
            if host not in item["skus"] or action not in {"replace","add"} or type(count) is not int or not 1<=count<=999:
                raise Problem("INVALID_MATERIALS")
            entry = {"sku":material_sku,"hostSku":host,"action":action,"quantity":count}
            previous = next((m for m in (current or {}).get("materials",[])
                             if all(m.get(k)==entry[k] for k in ("sku","hostSku","action"))),None)
            evidence = (previous or {}).get("evidence")
            if evidence is None:
                material_record = self.internal.products.get(material_sku,{})
                evidence = [{k:r[k] for k in ("sourceId","location","version","text")}
                            for r in material_record.get("records",[]) if r["kind"]=="identity"][:3]
            if evidence:entry["evidence"]=evidence
            if entry not in item["materials"]:item["materials"].append(entry)
        if current: state["projects"][state["projects"].index(current)] = item
        else: state["projects"].append(item)

    def product(self, state, body):
        sku = field(body.get("sku"),100,True)
        try: original = self.effective(sku)
        except Problem:
            if not body.get("create"): raise
            original = {}
        if body.get("create") and original: raise Problem("DUPLICATE_SKU",409)
        if not original and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}",sku): raise Problem("INVALID_SKU")
        if not original and not body.get("name"): raise Problem("REQUIRED_FIELD")
        sku = original.get("sku", sku)
        record = state["overrides"].setdefault(sku, {"sku":sku})
        for k,limit in (("name",600),("summary",12000),("custom",2000)):
            if k in body: record[k] = field(body[k],limit,required=k=="name")
        if "url" in body: record["url"]=https_url(body["url"])
        if "currency" in body:
            curr = field(body["currency"],3).upper()
            if curr and not re.fullmatch("[A-Z]{3}",curr): raise Problem("INVALID_CURRENCY")
            record["currency"]=curr
        if "price" in body:
            price=body["price"]
            if price is not None and (type(price) not in (int,float) or not math.isfinite(price) or price<0):
                raise Problem("INVALID_PRICE")
            record["price"]=record["maxPrice"]=price
        if "customConfirmed" in body:
            if not isinstance(body["customConfirmed"],bool): raise Problem("INVALID_FIELD")
            record["customConfirmed"]=body["customConfirmed"]
        if "image" in body:
            image=body["image"]
            if not isinstance(image,str): raise Problem("INVALID_IMAGE")
            record["image"]=self.store_image(image)

    def store_image(self, image):
        if not image: return ""
        if re.fullmatch(r"data/jpg/[0-9a-f]{20,64}\.jpg",image) and (self.root/image).is_file(): return image
        if re.fullmatch(r"/user-images/[0-9a-f]{64}\.jpg",image) and (self.local/image[1:]).is_file():return image
        if image.startswith("https://"): return https_url(image)
        prefix = "data:image/jpeg;base64,"
        if not image.startswith(prefix): raise Problem("INVALID_IMAGE")
        try: raw=base64.b64decode(image[len(prefix):],validate=True)
        except (binascii.Error,ValueError): raise Problem("INVALID_IMAGE")
        if not raw.startswith(b"\xff\xd8\xff"): raise Problem("INVALID_IMAGE")
        body=jpeg(raw)
        name=hashlib.sha256(body).hexdigest()+".jpg"
        target=self.local/"user-images"/name
        if not target.is_file(): write(target,body)
        return "/user-images/"+name

    def clean_user_images(self):
        references={r.get("image","") for r in self.state["overrides"].values()}
        for p in (self.local/"user-images").glob("*.jpg"):
            if re.fullmatch("[0-9a-f]{64}\\.jpg",p.name) and "/user-images/"+p.name not in references: p.unlink(missing_ok=True)

    def commit_catalog(self, catalog):
        with self.lock:
            write(self.catalog_file, CATALOG_PREFIX.encode()+packed(catalog)+b";\n")
            self.catalog=catalog
            self.reindex()
