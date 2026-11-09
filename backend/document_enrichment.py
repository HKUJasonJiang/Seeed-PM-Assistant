"""Audit official documents explicitly linked from the overseas catalogue.

Maintainer tool. Each response is processed in memory. Output contains identifiers,
section links, short factual table rows and statuses, never the source document.
The storefront's published robots rules are checked again for each new run.
Use the customer's local temp directory for --output. The catalogue service
does not require the optional pypdf / pypdfium2 or Poppler maintenance tools.
Run this module with --links and --discovered for newly linked documents.
Previously completed records are reused and a host's rate-limit reset is
preserved across runs. The optional --extended-text and --retry-redirects
passes can be run separately, followed by backend.document_merge.
"""
from __future__ import annotations

import argparse
import collections
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import io
import hashlib
import json
import logging
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, unquote_plus, urldefrag, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from lxml import html
from .storage import write as atomic_write
from . import document_sheet

AGENT = "SeeedPMDocumentation"
PDF_TEXT_TOOL = None
PDFIUM_RECOVERY = False
HEADERS = {"User-Agent": AGENT + "/1.0 (public product document review)", "Accept-Encoding": "identity"}
HOSTS = {"wiki.seeedstudio.com", "files.seeedstudio.com", "statics3.seeedstudio.com", "www.seeedstudio.com",
         "sensecap-docs.seeed.cc", "file.seeedstudio.com", "garden.seeedstudio.com"}
SEEED_BUCKET_HOST="s3-us-west-2.amazonaws.com"
SEEED_BUCKET_PREFIX="/files.seeedstudio.com/"


def bucket_key(url):
    u=urlsplit(url)
    if u.scheme!="https" or u.netloc!=SEEED_BUCKET_HOST or u.query or not u.path.startswith(SEEED_BUCKET_PREFIX):return ""
    key=u.path[len(SEEED_BUCKET_PREFIX):]
    segments=unquote(key).split("/")
    if any(s in {"",".",".."} for s in segments):return ""
    return key if re.fullmatch(r"products/[A-Za-z0-9_-]+/.+\.pdf",key,re.I) else ""


def publisher_source(url):
    return urlsplit(url).hostname in HOSTS or bool(bucket_key(url))

PART = re.compile(r"\b(?:pack(?:age|ing)?\s*(?:contents?|list)|what(?:'s| is) (?:included|in the box)|in the box|box contents|parts? list|kit contents)\b|装箱清单|包装清单|包装内容|随箱清单", re.I)
ACC = re.compile(r"\b(?:accessor(?:y|ies)(?: list)?|supported (?:accessories|modules)|optional (?:accessories|modules)|compatible (?:accessories|modules))\b|配件列表|可选配件|选配附件", re.I)
EXCLUSION = re.compile(r"\b(?:not included|sold separately|purchased separately|purchase separately|does not come with)\b", re.I)
CUSTOM = re.compile(r"\b(?:customization services?|customi[sz]ation options|logo branding|logo customi[sz]ation|our hardware engineering services)\b", re.I)
SKU = re.compile(r"(?<![A-Za-z\d])([1-9]\d{8})(?![A-Za-z\d])")
KNOWN_NON_NUMERIC=frozenset()
LABELLED_NON_NUMERIC=None


def set_catalog_skus(skus):
    """Nonstandard identifiers require an explicit SKU field and an exact local match."""
    global KNOWN_NON_NUMERIC,LABELLED_NON_NUMERIC
    KNOWN_NON_NUMERIC=frozenset(str(value) for value in skus if value and not SKU.fullmatch(str(value)))
    choices="|".join(re.escape(value) for value in sorted(KNOWN_NON_NUMERIC,key=len,reverse=True))
    LABELLED_NON_NUMERIC=re.compile(r"\b(?i:SKU(?:\s+(?:no\.?|number|code))?)\s*[:：#]?\s*("+choices+r")(?![\w-])") if choices else None


def sku_cell(value):
    exact=compact(value)
    if exact in KNOWN_NON_NUMERIC:return [exact]
    return SKU.findall(exact)


def labelled_skus(text):
    return LABELLED_NON_NUMERIC.findall(text) if LABELLED_NON_NUMERIC else []
QTY = re.compile(r"(?:[x×]\s*(\d{1,3})\s*$|^\s*(\d{1,3})\s*[x×](?:\s+|(?=[A-Za-z]))|^\s*(\d{1,3})\s*(?:pcs?\.?|pieces?)?\s*$)", re.I)
PDF_HEADING = re.compile(r"^\s*(?:(?:(?:chapter|section|table|appendix)\s+)?[A-Z]?\d+(?:\.\d+)*[.)]?\s*)?"
                         r"((?:optional\s+)?accessories(?:\s+(?:list|information))?|packing\s*list|package\s*contents|parts?\s*list|"
                         r"in\s*the\s*box|装箱清单|包装清单|包装内容|随箱清单|配件列表|可选配件|选配附件)\s*[:：.]?\s*$",re.I)
GLOBAL_CATALOG_URL="https://files.seeedstudio.com/wiki/wiki-platform/2026_Seeed_Studio_Catalog.pdf"
EDGELOGIX_GUIDE="https://files.seeedstudio.com/wiki/raspberry-pi/seeed-studio-raspberry-pi-series-catalog-v1.1.pdf"


class Redirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


OPENER = build_opener(Redirects())


def compact(s):
    return " ".join(str(s or "").replace("\u200b", "").split())


def canonical(url):
    try:
        u = urlsplit(urldefrag(str(url).strip())[0])
        if u.scheme.lower() not in {"http", "https"} or not u.hostname or u.username or u.password or u.port not in (None, 80, 443):
            return ""
        # Decode only RFC-unreserved bytes, so a published %2F never silently
        # becomes a different path or matches a different robots rule.
        def normalize(match):
            char=chr(int(match[1],16))
            return char if re.fullmatch(r"[A-Za-z0-9._~-]",char) else "%"+match[1].upper()
        path = quote(re.sub(r"%([0-9A-Fa-f]{2})",normalize,u.path) or "/",safe="/!$&'()*+,;=:@-._~%")
        scheme = "https" if u.hostname in HOSTS else u.scheme.lower()
        pieces=[]
        for term in u.query.split("&"):
            key=unquote_plus(term.partition("=")[0]).casefold()
            if key in {"_gl","gclid","fbclid","from_wecom"} or key.startswith("utm_"):continue
            if key in {"api_key","access_token","x-amz-credential","x-amz-signature"}:return ""
            if term:pieces.append(term)
        return urlunsplit((scheme, u.hostname.lower(), path, "&".join(pieces), ""))
    except (ValueError, UnicodeError):
        return ""


def kind(url):
    u = urlsplit(url)
    if unquote(u.path).lower().endswith(".pdf"):
        return "pdf"
    if document_sheet.targeted(url):return "spreadsheet"
    wiki_page=u.hostname=="wiki.seeedstudio.com" or (u.hostname=="www.seeedstudio.com" and u.path.startswith("/wiki/") and "/images/" not in u.path)
    if wiki_page and not re.search(r"\.(?:zip|stp|stl|dxf|rar|ino|js|dwg|xlsx?|docx?|png|jpe?g|svg)$", u.path, re.I):
        return "wiki"
    return "reference"


def document_limit(url,mode):
    if mode!="pdf":return 6_000_000
    path=unquote(urlsplit(url).path)
    large_product_docs=r"recomputer|reterminal|sensecap[ _-]?watcher|user[ _-]?manual|instruction[ _-]?manual|grove[ _-]?(?:beginner|creator)[ _-]?kit|xiao[ _-]?reference[ _-]?design"
    if re.search(r"/products/[A-Za-z0-9-]+/[^?#]*brochure",path,re.I):return 64_000_000
    return 160_000_000 if re.search(large_product_docs,path,re.I) else 36_000_000


def github_file(url):
    """Original Seeed public repository and revision from the published document link."""
    u=urlsplit(url)
    pieces=unquote(u.path).strip("/").split("/")
    if u.hostname=="github.com" and len(pieces)>=5 and pieces[2] in ("blob","raw","tree"):
        owner,repo,_,ref,*parts=pieces
    elif u.hostname=="raw.githubusercontent.com" and len(pieces)>=4:
        owner,repo,ref,*parts=pieces
    else:return None
    if owner.lower() not in {"seeed-studio","seeeddocument"}:return None
    if not all(re.fullmatch(r"[A-Za-z0-9_.-]+",n) and n not in (".","..") for n in [owner,repo,ref]):return None
    if any(n in ("",".","..") for n in parts):return None
    if not parts[-1].lower().endswith(".pdf") and not document_sheet.targeted(url):return None
    path="/".join(quote(v,safe="") for v in parts)
    endpoint=f"https://api.github.com/repos/{owner}/{repo}/contents/{path}?"+urlencode({"ref":ref})
    raw=f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}"
    return endpoint,raw


def load_catalog(path):
    raw = path.read_text(encoding="utf-8-sig")
    return json.loads(raw[raw.index("{"):raw.rindex("}")+1])


def add_source(sources, url, sku, title, mode=None):
    url = canonical(url)
    if not url or not sku:
        return
    entry = sources.setdefault(url, {"kind": mode or kind(url), "skus": set(), "labels": set()})
    entry["skus"].add(sku)
    if title:
        entry["labels"].add(compact(title)[:160])


def inventory(doc):
    result = {}
    for p in doc["products"]:
        if p["sku"] in {"102110779","102991734","102110773"} and "edgelogix" in p.get("name","").casefold().replace(" ",""):
            add_source(result,EDGELOGIX_GUIDE,p["sku"],"Seeed Studio Raspberry Pi Series Catalog v1.1","pdf")
        for field in ["docs", "wikiLinks", "wikiEvidence"]:
            for ref in p.get(field, []):
                if not isinstance(ref, dict):
                    continue
                url=canonical(ref.get("url") or "")
                add_source(result, url, p["sku"], ref.get("name") or ref.get("title") or "")
                if url and p["sku"]:
                    entry=result[url]
                    rel=ref.get("relation")
                    if rel=="declared_sku":entry.setdefault("declared",set()).add(p["sku"])
                    if rel=="purchase_link" or ref.get("purchaseLink"):entry.setdefault("purchases",set()).add(p["sku"])
                    if rel not in ("declared_sku","purchase_link"):entry.setdefault("explicitStore",set()).add(p["sku"])
        # Verified manuals in legacy records are indexed indirectly.
        for option in p.get("accessories", []):
            if option.get("doc") in doc.get("docs", {}):
                u=canonical(doc["docs"][option["doc"]]["url"])
                add_source(result,u,p["sku"],option["doc"])
                if u:result[u].setdefault("explicitStore",set()).add(p["sku"])
    return result


class Rules:
    def __init__(self):
        self.hosts = {}
        self.pause = {}
        self.last = {}
        self.unavailable_publisher_keys=set()
        self.allow_published_redirects=False
        self.request_counter=threading.local()
        self.github_cli=None

    def cooldown(self,host,headers):
        until=time.time()+120
        if headers.get("X-RateLimit-Remaining")=="0" and headers.get("X-RateLimit-Reset","").isdigit():
            until=max(until,int(headers["X-RateLimit-Reset"]))
        value=headers.get("Retry-After","")
        if value.isdigit():until=max(until,time.time()+int(value))
        elif value:
            try:until=max(until,parsedate_to_datetime(value).timestamp())
            except (ValueError,TypeError):pass
        self.pause[host]=int(until+1)
        return self.pause[host]

    def github_document(self, urls, hops=0):
        host="api.github.com"
        if self.pause.get(host,0)>time.time():return {"status":"unread","reason":"github_rate_limit","retryAt":self.pause[host]},None
        delay=.9-(time.monotonic()-self.last.get(host,0))
        if delay>0:time.sleep(delay)
        self.last[host]=time.monotonic()
        api,source=urls
        try:
            self.request_counter.count=getattr(self.request_counter,"count",0)+1
            with OPENER.open(Request(api,headers={**HEADERS,"Accept":"application/vnd.github.raw+json","X-GitHub-Api-Version":"2022-11-28"}),timeout=20) as resp:
                if resp.headers.get("X-RateLimit-Remaining")=="0":self.cooldown(host,resp.headers)
                limit=6_000_000 if document_sheet.targeted(source) else 36_000_000
                body=resp.read(limit+1)
                if len(body)>limit:return {"status":"unread","reason":"limit_bytes"},None
                return {"finalUrl":source,"bytes":len(body)},body
        except HTTPError as err:
            if err.code in (403,429) and (err.headers.get("Retry-After") or err.headers.get("X-RateLimit-Remaining")=="0"):
                self.cooldown(host,err.headers)
                return {"status":"unread","reason":"github_rate_limit","retryAt":self.pause[host]},None
            if err.code in (301,302,307,308) and err.headers.get("Location") and hops<3:
                new=canonical(urljoin(api,err.headers["Location"]));u=urlsplit(new)
                if u.scheme=="https" and u.hostname==host and re.match(r"^/(?:repositories/\d+|repos/[^/]+/[^/]+)/contents/",u.path):
                    if err.headers.get("X-RateLimit-Remaining")=="0":self.cooldown(host,err.headers)
                    return self.github_document((new,source),hops+1)
            return {"status":"failed","reason":"http_"+str(err.code)},None
        except OSError:return {"status":"failed","reason":"network"},None

    def policy(self, host):
        if host in self.hosts:
            return self.hosts[host]
        rules, delay = [], 0
        try:
            with OPENER.open(Request("https://"+host+"/robots.txt",headers=HEADERS),timeout=15) as r:
                data = r.read(512001)
                if len(data)>512000 or b"<html" in data[:200].lower():
                    raise ValueError("unreadable robots")
                groups, agents, group, started = [], [], [], False
                for line in data.decode("utf-8","replace").splitlines():
                    key,sep,value=line.partition("#")[0].partition(":")
                    if not sep:
                        continue
                    key,value=key.strip().lower(),value.strip()
                    if key=="user-agent":
                        if started:
                            groups.append((agents,group))
                            agents,group,started=[],[],False
                        agents.append(value.lower())
                    elif agents and key in ("allow","disallow","crawl-delay"):
                        started=True
                        if value:
                            group.append((key,value))
                groups.append((agents,group))
                specific=[g for a,g in groups if any(x!="*" and x and x in AGENT.lower() for x in a)]
                relevant=specific or [g for a,g in groups if "*" in a]
                for g in relevant:
                    for key,val in g:
                        if key=="crawl-delay":
                            try:delay=max(delay,float(val))
                            except ValueError:pass
                        else:rules.append((key,val))
                status="published"
        except HTTPError as exc:
            if exc.code not in (401,403,404,410):
                self.hosts[host]=("unverified",[],1);return self.hosts[host]
            # RFC 9309 section 2.3.1.3: 4xx on robots is an unavailable rules file.
            # A separate 401 or 403 on an actual document is always respected.
            status="robots_http_"+str(exc.code)
        except (OSError, ValueError):
            self.hosts[host]=("unverified",[],1);return self.hosts[host]
        self.hosts[host]=(status,rules,max(0.65,delay))
        return self.hosts[host]

    def blocked_path(self,policy_host,path):
        status,rules,delay=self.policy(policy_host)
        if status=="unverified":
            return "robots_unverified"
        matches=[]
        for action,rule in rules:
            anchor=rule.endswith("$")
            pattern=rule[:-1] if anchor else rule
            regex=re.escape(pattern).replace(r"\*",".*")+("$" if anchor else "")
            if re.match(regex,path):
                matches.append((len(pattern.replace("*","")),int(action=="allow")))
        return "excluded_robots" if matches and max(matches)[1]==0 else ""

    def allowed(self,url):
        u=urlsplit(url)
        reason=self.blocked_path(u.hostname,u.path+("?"+u.query if u.query else ""))
        key=bucket_key(url)
        if reason or not key:return reason
        return self.blocked_path(SEEED_BUCKET_HOST+"/files.seeedstudio.com","/"+key) or self.blocked_path("files.seeedstudio.com","/"+key)

    def fetch(self,url,mode):
        github=github_file(url) if mode in {"pdf","spreadsheet"} and self.github_cli else None
        if github:
            receipt,body=self.github_cli.fetch(github)
            receipt["githubBudget"]="account"
            return receipt,body
        self.request_counter.count=0
        record,body=self._fetch(url,mode)
        record["requestAttempted"]=self.request_counter.count>0
        return record,body

    def _fetch(self,url,mode):
        github=github_file(url) if mode in {"pdf","spreadsheet"} else None
        if github:return self.github_document(github)
        current=url; origin=urlsplit(url).hostname
        for _ in range(5):
            host=urlsplit(current).hostname
            if not publisher_source(current) or (host!=origin and not self.allow_published_redirects):
                return {"status":"unread","reason":"redirect_other_host","redirect":current},None
            key=bucket_key(current)
            if key and key in self.unavailable_publisher_keys:
                return {"status":"unread","reason":"publisher_source_unavailable"},None
            if key and self.pause.get("files.seeedstudio.com",0)>time.time():
                return {"status":"unread","reason":"host_cooldown","retryAt":self.pause["files.seeedstudio.com"]},None
            if self.pause.get(host,0)>time.time():
                return {"status":"unread","reason":"host_cooldown","retryAt":self.pause[host]},None
            exclude=self.allowed(current)
            if exclude:
                return {"status":"unread","reason":exclude},None
            interval=self.policy(host)[2]
            if bucket_key(current):interval=max(interval,self.policy(SEEED_BUCKET_HOST+"/files.seeedstudio.com")[2],self.policy("files.seeedstudio.com")[2])
            wait=interval-(time.monotonic()-self.last.get(host,0))
            if wait>0:time.sleep(wait)
            self.last[host]=time.monotonic()
            try:
                request=Request(current,headers=HEADERS)
                self.request_counter.count+=1
                with OPENER.open(request,timeout=22) as response:
                    limit=document_limit(current,mode)
                    length=response.headers.get("Content-Length")
                    if length and int(length)>limit:
                        return {"status":"unread","reason":"limit_bytes","bytes":int(length)},None
                    body=response.read(limit+1)
                    if len(body)>limit:return {"status":"unread","reason":"limit_bytes"},None
                    return {"finalUrl":current,"bytes":len(body)},body
            except HTTPError as exc:
                if exc.code in (301,302,303,307,308) and exc.headers.get("Location"):
                    nxt=canonical(urljoin(current,exc.headers["Location"]))
                    if not nxt:return {"status":"unread","reason":"invalid_redirect"},None
                    current=nxt;continue
                if exc.code==429 or exc.code==503:
                    return {"status":"unread","reason":"host_cooldown","retryAt":self.cooldown(host,exc.headers)},None
                return {"status":"failed","reason":"http_"+str(exc.code)},None
            except (OSError,ValueError):
                return {"status":"failed","reason":"network"},None
        return {"status":"failed","reason":"redirect_limit"},None


def html_rows(table,with_lines=False):
    result=[];spans={}
    for tr in table.xpath('.//tr'):
        if tr.xpath("ancestor::table[1]")[0] is not table:continue
        cells={col:value for col,(remaining,value) in spans.items()}
        spans={col:(remaining-1,value) for col,(remaining,value) in spans.items() if remaining>1}
        col=0
        for td in tr.xpath("./td|./th"):
            while col in cells:col+=1
            try:
                width=max(1,min(32,int(td.get("colspan","1"))))
                height=max(1,min(500,int(td.get("rowspan","1"))))
            except ValueError:width,height=1,1
            value=compact(" ".join(td.itertext()))
            for j in range(width):
                cells[col+j]=value if not j else ""
                if height>1:spans[col+j]=(height-1,cells[col+j])
            col+=width
        cells=[cells.get(i,"") for i in range(max(cells,default=-1)+1)]
        if any(cells):result.append((cells,tr.sourceline or 1) if with_lines else cells)
    return result


def point_type(title):
    if PART.search(title):return "inbox"
    if ACC.search(title):return "accessory"
    return ""


def clear_item_label(value):
    return bool(1<len(value)<125 and re.search(r"[A-Za-z\u3400-\u9fff]",value)
                and not re.search(r"[.!?]\s|[:;!?]$|\b(?:you|we|this kit contains|please|note that|example|download|purchase|assembly steps)\b",value,re.I)
                and not re.fullmatch(r"(?:part|item|product|component|name|description|quantity|picture|image|link)(?: name)?",value,re.I))


def add_rows(out,cells,role,source,header=(),allow_named=False):
    if role=="inbox" and re.search(r"\b(?:optional|not included|sold separately|customer supplied)\b|需另购|不包含|选配|不随附"," ".join(cells),re.I):return
    if role=="accessory" and re.search(r"\b(?:incompatible|not compatible|unsupported|not supported)\b"," ".join(cells),re.I):return
    sku_index=next((i for i,h in enumerate(header) if re.search(r"\bsku\b|part number",h,re.I)),None)
    qty_index=next((i for i,h in enumerate(header) if re.fullmatch(r"qty\.?|quantity|count|pcs|数量",h,re.I)),None)
    if sku_index is not None and sku_index<len(cells):
        ids=sku_cell(cells[sku_index]) if re.search(r"\bsku\b",header[sku_index],re.I) else SKU.findall(cells[sku_index])
    else:ids=SKU.findall(" ".join(cells))
    explicit_name=next((i for i,h in enumerate(header) if re.fullmatch(r"name|part name|product name|accessor(?:y|ies)|module name|产品名称|配件名称|物品名称|名称",h,re.I)),None)
    named=allow_named and explicit_name is not None and len(header)<=4
    published=""
    if not ids and sku_index is not None and sku_index<len(cells) and re.fullmatch(r"SKU",header[sku_index],re.I) and explicit_name is not None:
        column=compact(cells[sku_index])
        if re.fullmatch(r"(?=.*\d)[A-Za-z][A-Za-z0-9._-]{2,24}",column):published=column
    if role=="accessory" and len(set(ids))!=1 and not (not ids and (named or published)):return
    if len(set(ids))>1:return
    name_idx=explicit_name if explicit_name is not None else next((i for i,h in enumerate(header) if re.fullmatch(r"component|item(?: name)?|parts name",h,re.I)),None)
    if name_idx is None:name_idx=next((i for i,h in enumerate(header) if h.lower()=="description"),None)
    eligible=[v for i,v in reversed(list(enumerate(cells))) if i not in {sku_index,qty_index}
              and 1<len(v)<220 and re.search(r"[A-Za-z\u3400-\u9fff]",v) and not QTY.fullmatch(v)
              and not re.search(r"https?://|get (?:one|it) now|buy now|^link$|purchase link|^see more$|^click",v,re.I)]
    preferred=cells[name_idx] if name_idx is not None and name_idx<len(cells) else ""
    title=preferred if preferred in eligible else next(iter(eligible),"")
    if not title:return
    qty=""
    if qty_index is not None and qty_index<len(cells):
        quantity=re.sub(r"(?<=\d)\s*(?:件|个|条|根|颗|枚|份)\s*$","",cells[qty_index])
        m=QTY.search(quantity);qty=next((x for x in m.groups() if x),"") if m else ""
    elif role=="inbox":
        m=QTY.search(title) or next((m for c in cells if (m:=QTY.fullmatch(c))),None)
        if m:qty=next(x for x in m.groups() if x)
        if not qty and len(cells)==1:
            asterisk=re.search(r"^\s*(\d{1,3})\s*\*\s*(?=[A-Za-z])|\s+\*\s*(\d{1,3})\s*$",title)
            if asterisk:
                qty=next(x for x in asterisk.groups() if x)
                title=(title[:asterisk.start()]+title[asterisk.end():]).strip()
    if role=="inbox" and not qty and not clear_item_label(title):return
    name=SKU.sub("",title).strip(" |-:;")
    if ids:name=re.sub(r"\s*\bSKU\s*[:#]?\s*$","",name,flags=re.I).strip()
    if role=="inbox":name=re.sub(r"^\s*\d{1,3}\s*[x×](?:\s+|(?=[A-Za-z]))|\s*[x×]\s*\d{1,3}\s*$","",name,flags=re.I).strip()
    if role=="inbox" and name_idx is not None:
        spec=next((cells[i] for i,h in enumerate(header) if h.lower()=="specification" and i<len(cells)),"")
        if spec and spec.lower() not in name.lower() and len(spec)<=65:name+=" ("+spec+")"
    if not name or not re.search(r"[A-Za-z\u3400-\u9fff]",name):return
    row={"kind":role,"name":name,"source":source}
    if ids:row["sku"]=ids[0]
    elif role=="accessory" and published and preferred in eligible:row.update(publishedSku=published,namedAccessory=True)
    elif role=="accessory" and named and preferred in eligible:row["namedAccessory"]=True
    elif role=="accessory":return
    if qty:row["quantity"]=qty
    if row not in out:out.append(row)


def parse_wiki(body,url):
    tree=html.fromstring(body,parser=html.HTMLParser(encoding="utf-8"))
    main=tree.xpath("//article")
    if not main:return {"status":"failed","reason":"no_wiki_article"}
    article=main[0]
    title=compact(" ".join(article.xpath("(.//h1)[1]//text()")))[:180]
    if not title or re.search("Page Not Found",title,re.I):return {"status":"failed","reason":"missing_article"}
    items,sections,statements,linked,sheets,products=[],[],[],{},{},set()
    heading=[]; levels={}; ancestry=None
    for node in article.iter():
        if not isinstance(node.tag,str):continue
        tag=node.tag.lower()
        if re.fullmatch("h[1-6]",tag):
            level=int(tag[-1])
            for k in list(levels):
                if k>=level:del levels[k]
            name=compact(" ".join(node.itertext())).strip("# ​")[:180]
            levels[level]=(name,node.get("id") or "")
            heading=list(levels.values())
            ancestry=next(((point_type(t),i) for t,i in reversed(heading) if point_type(t)),None)
            if ancestry and ancestry[1] and ancestry[1] not in sections:sections.append(ancestry[1])
        source=url+("#"+quote(heading[-1][1]) if heading and heading[-1][1] else "")
        if tag=="a":
            dest=canonical(urljoin(url,node.get("href") or ""))
            text=compact(" ".join(node.itertext()))
            if dest and kind(dest) in {"pdf","spreadsheet"} and (publisher_source(dest) or github_file(dest)):
                (sheets if kind(dest)=="spreadsheet" else linked)[dest]=text[:120]
            if dest and urlsplit(dest).hostname=="www.seeedstudio.com" and re.search(r"get.*now|buy.*now|purchase",text,re.I):
                products.add(dest)
        if tag=="table" and ancestry:
            table=html_rows(node)
            if len(table)>1:
                allow_named=any(re.fullmatch(r"(?:optional )?accessories(?: list)?",title,re.I) for title,_ in heading)
                for cells in table[1:]:add_rows(items,cells,ancestry[0],source,table[0],allow_named)
        elif tag=="li" and ancestry and ancestry[0]=="inbox" and not node.xpath(".//li"):
            add_rows(items,[compact(" ".join(node.itertext()))],ancestry[0],source)
        if tag in ("p","li") and not node.xpath(".//p|.//li"):
            text=compact(" ".join(node.itertext()))
            if len(text)>350 or len(text)<10:continue
            if EXCLUSION.search(text) or CUSTOM.search(text):
                statements.append({"kind":"exclusion" if EXCLUSION.search(text) else "customization","text":text,"source":source})
    return {"status":"parsed" if items or statements else "empty","title":title,"sections":sections[:35],
            "rows":items[:220],"statements":statements[:22],"linkedPdfs":linked,"linkedSheets":sheets,"purchaseUrls":sorted(products)}


def index_long_pdf(body,reader):
    """Read the text of all physical pages, retrieving column layout near relevant headings."""
    try:import pypdfium2 as pdfium
    except ImportError:return None
    if len(reader.pages)>2500:return None
    pages=[]
    with pdfium.PdfDocument(body) as pdf:
        if len(pdf)!=len(reader.pages):return None
        for i in range(len(pdf)):
            page=pdf[i]
            try:
                text=page.get_textpage()
                try:pages.append(text.get_text_bounded().replace("\r\n","\n"))
                finally:text.close()
            finally:page.close()
    target=set()
    for i,text in enumerate(pages):
        if any(len(compact(line))<110 and PDF_HEADING.match(compact(line)) for line in text.splitlines()):
            target.update(range(i,min(i+4,len(pages))))
    for i in sorted(target):
        try:layout=reader.pages[i].extract_text(extraction_mode="layout")
        except (ValueError,KeyError,IndexError,NotImplementedError):continue
        if layout:pages[i]=layout
    return pages


def parse_pdf(body,url):
    if not body.startswith(b"%PDF-"):return {"status":"failed","reason":"not_pdf"}
    binary=PDF_TEXT_TOOL or shutil.which("pdftotext")
    if PDFIUM_RECOVERY:
        import pypdfium2 as pdfium
        import pypdfium2.raw as api
        from pypdf.constants import UserAccessPermissions
        try:
            with pdfium.PdfDocument(body) as document:
                if api.FPDF_GetSecurityHandlerRevision(document)>=0 and not api.FPDF_GetDocUserPermissions(document)&int(UserAccessPermissions.EXTRACT):
                    return {"status":"unread","reason":"protected_pdf"}
                if len(document)>2500:return {"status":"unread","reason":"long_pdf","pages":len(document)}
                pages=[]
                for i in range(len(document)):
                    page=document[i]
                    try:
                        text=page.get_textpage()
                        try:pages.append(text.get_text_bounded().replace("\r\n","\n"))
                        finally:text.close()
                    finally:page.close()
        except Exception as exc:
            if "password" in str(exc).lower():return {"status":"unread","reason":"protected_pdf"}
            return {"status":"failed","reason":"pdf_text_"+type(exc).__name__}
    elif binary:
        if re.search(rb"/Encrypt\b",body):
            try:
                from pypdf import PdfReader
                from pypdf.constants import UserAccessPermissions
                reader=PdfReader(io.BytesIO(body),strict=False)
                if reader.is_encrypted and not (reader.user_access_permissions and reader.user_access_permissions & UserAccessPermissions.EXTRACT):
                    return {"status":"unread","reason":"protected_pdf"}
            except Exception:return {"status":"unread","reason":"protected_pdf"}
        try:
            run=subprocess.run([binary,"-layout","-enc","UTF-8","-","-"],input=body,capture_output=True,timeout=70)
        except (OSError,subprocess.TimeoutExpired):return {"status":"failed","reason":"pdf_text_timeout"}
        if run.returncode:return {"status":"failed","reason":"pdf_text_failed"}
        pages=run.stdout.decode("utf-8","replace").split("\f")
        if pages and not pages[-1].strip():pages.pop()
    else:
        try:
            from pypdf import PdfReader
            from pypdf.constants import UserAccessPermissions
            reader=PdfReader(io.BytesIO(body),strict=False)
            if reader.is_encrypted:
                # Open only documents the standard reader already exposes without a
                # password and whose PDF permissions explicitly allow text copying.
                # Never call decrypt() or supply, test or guess a password.
                try:
                    permits=reader.user_access_permissions
                    if not permits or not permits & UserAccessPermissions.EXTRACT or not len(reader.pages):
                        return {"status":"unread","reason":"protected_pdf"}
                except Exception:return {"status":"unread","reason":"protected_pdf"}
            if len(reader.pages)>180:
                pages=index_long_pdf(body,reader)
                if pages is None:return {"status":"unread","reason":"long_pdf","pages":len(reader.pages)}
            else:
                try:pages=[p.extract_text(extraction_mode="layout") or "" for p in reader.pages]
                except (ValueError,RuntimeError,KeyError,IndexError,NotImplementedError):
                    pages=index_long_pdf(body,reader)
                    if pages is None:raise
        except (ImportError,ValueError,RuntimeError,KeyError,IndexError,OSError,NotImplementedError) as exc:
            return {"status":"failed","reason":"pdf_text_"+type(exc).__name__}
    if not pages or sum(len(compact(p)) for p in pages)<60:return {"status":"unread","reason":"no_text_layer","pages":len(pages)}
    rows,sections=[],[];continued=0
    title=next((compact(line)[:180] for line in pages[0].splitlines() if re.search(r"[A-Za-z]{4}",line)), "")
    for idx,page in enumerate(pages,1):
        lines=page.splitlines();matches=[(i,PDF_HEADING.match(compact(line))) for i,line in enumerate(lines) if len(compact(line))<110]
        matches=[(i,m) for i,m in matches if m]
        if not matches and not continued:continue
        start=matches[-1][0] if matches else 0
        label=matches[-1][1][1] if matches else ""
        role="accessory" if not matches or ACC.search(label) else "inbox"
        if not role:continue
        source=url+"#page="+str(idx)
        headers=any(re.search(r"\bSKU\b",line,re.I) for line in lines[start:start+9])
        named_pdf_column=any(re.search(r"(?:\b(?:product|module|part) name|产品名称|配件名称)\s+SKU\s*$",compact(line),re.I) for line in lines[start:start+9])
        qty_header=any(re.search(r"\b(?:qty|quantity|pieces|pcs)\b|数量",line,re.I) for line in lines[start:start+9])
        if matches:sections.append({"page":idx,"kind":role,"heading":label,"explicitBox":role=="inbox" and not re.search(r"parts?[\s_-]*list",matches[-1][1][1],re.I)})
        if role=="accessory" and not headers and not continued:continue
        hits=0
        for line in lines[start+1:]:
            cells=[compact(x) for x in re.split(r"\s{2,}",line.strip()) if compact(x)]
            if role=="inbox":
                trimmed=compact(line)
                if re.fullmatch(r"(?:[A-Z]?\d+(?:\.\d+)*[.)]?\s+)?(?:installation(?: instructions)?|assembly(?: instructions| steps)?|getting started|specifications?|technical data|hardware overview|preparation|working principle|安装说明|产品规格)[:：.]?",trimmed,re.I):break
                if cells and qty_header:cells[-1]=re.sub(r"(?<=\d)\s*(?:件|个|条|根|颗|枚|份)\s*$","",cells[-1])
                if re.search(r"\b(?:page\s+\d|of\s+\d+|copyright|product details|sku\s*[:#])\b",trimmed,re.I):continue
                if re.match(r"^(?:[•*–\uf0b7-]\s*)?\d+\s*[x×]\s+\S",trimmed,re.I):
                    cells=[re.sub(r"^[•*–\uf0b7-]\s*","",trimmed)]
                elif matches and role=="inbox" and sections[-1]["explicitBox"] and re.match(r"^[•*–\uf0b7-]\s+\S",trimmed):
                    cells=[re.sub(r"^[•*–\uf0b7-]\s+","",trimmed)]
                elif matches and sections[-1]["explicitBox"] and not qty_header:
                    numbered=re.match(r"^(?:\d{1,2}[.)、]|[（(]\d{1,2}[)）])\s+(.+)$",trimmed)
                    if not numbered or not clear_item_label(numbered[1]) or re.match(r"(?:connect|install|plug|read|prepare|refer|remove|use|please)\b",numbered[1],re.I):continue
                    cells=[numbered[1]]
                elif not qty_header or len(cells)<2 or not QTY.fullmatch(cells[-1]):continue
            elif len(cells)<2:continue
            if role=="accessory":
                codes=sku_cell(cells[-1])
                printed_only=named_pdf_column and re.fullmatch(r"(?=.*\d)[A-Za-z][A-Za-z0-9._-]{2,24}",cells[-1])
                if not printed_only and (len(codes)!=1 or len(set(SKU.findall(line))|set(codes))!=1):continue
            header=[""]*(len(cells)-1)+["SKU"] if role=="accessory" else ()
            if role=="accessory" and named_pdf_column:header[-2]="Product Name"
            n=len(rows);add_rows(rows,cells,role,source,header)
            hits+=(n<len(rows))
        continued=1 if role=="accessory" and hits>=3 else 0
    cover=pages[0]
    ids=re.findall(r"\bSKU\s*[:：#]\s*([1-9]\d{8})\b",cover,re.I)+labelled_skus(cover)
    for line in cover.splitlines():
        listed=re.search(r"\bSKUs?\s*[:：#]\s*(.+)",line,re.I)
        if listed:
            cells=re.split(r"\s*[,;/|]\s*|\s{2,}",listed[1].strip())
            for cell in cells:
                if SKU.fullmatch(cell) or cell in KNOWN_NON_NUMERIC:ids.append(cell)
    page_codes={str(i):sorted(values) for i,page in enumerate(pages,1) if (values:=set(SKU.findall(page))|set(labelled_skus(page)))}
    for row in rows:
        if row.get("sku") in KNOWN_NON_NUMERIC:
            key=row["source"].rsplit("=",1)[-1]
            page_codes[key]=sorted(set(page_codes.get(key,[]))|{row["sku"]})
    return {"status":"parsed" if rows else "empty","title":title,"identitySkus":sorted(set(ids)),"pageSkus":page_codes,
            "pages":len(pages),"sparsePages":sum(len(compact(p))<40 for p in pages),
            "sections":sections[:60],"rows":rows[:260]}


def fetch_one(url,detail,rules,scan=None):
    mode=detail["kind"];meta,body=rules.fetch(url,mode)
    if body is None:return meta
    try:
        if mode=="pdf":out=parse_pdf(body,meta["finalUrl"])
        elif mode=="spreadsheet":out=document_sheet.parse(body,meta["finalUrl"])
        else:out=parse_wiki(body,meta["finalUrl"])
    except Exception as exc:
        # PDF codecs and layout engines can raise format-specific errors. Record the
        # failure for this published file without losing the rest of the host queue.
        out={"status":"failed","reason":"unreadable_"+type(exc).__name__}
    out.update(meta)
    if mode=="pdf":
        out["sha256"]=hashlib.sha256(body).hexdigest()
        if scan:scan(url,body,out)
    return out


def global_catalog_index(out,rules):
    from pypdf import PdfReader
    meta,body=rules.fetch(GLOBAL_CATALOG_URL,"pdf")
    if body is None:return meta
    reader=PdfReader(io.BytesIO(body),strict=False)
    mentions=[]
    for idx,page in enumerate(reader.pages,1):
        content=page.extract_text(extraction_mode="layout") or ""
        # A course link on page 119 contains ?sku=604182009. Query values are
        # not catalogue item labels; keep printed product codes separately.
        print_text=re.sub(r"[?&][A-Za-z][\w.-]*=[^\s]+","",content)
        skus=sorted(set(SKU.findall(print_text))|set(labelled_skus(print_text)))
        models=sorted(set(re.findall(r"\b(?:reComputer\s+(?:(?:Industrial|Super|Mini|Robotics|Rugged)\s+)?[JR]\d{3,4}(?:-\d{2})?|XIAO\s+(?:ESP32[A-Z0-9-]+|nRF\d+|RP\d+|SAMD\d+))\b",content,re.I)))
        if skus or models:mentions.append({"page":idx,"skus":skus,"models":models})
    result={"url":GLOBAL_CATALOG_URL,"pages":len(reader.pages),"mentions":mentions}
    atomic_write(out/"global-catalog-evidence.json",json.dumps(result).encode("utf-8"))
    return result


def run():
    global PDF_TEXT_TOOL,PDFIUM_RECOVERY
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog",type=Path,default=Path("data/catalog.js"))
    parser.add_argument("--output",required=True,type=Path)
    parser.add_argument("--links",type=Path,help="Additional official SKU-to-document mappings from a catalogue refresh")
    parser.add_argument("--pdftotext",type=Path,help="Poppler pdftotext executable")
    parser.add_argument("--discovered",action="store_true",help="Also inspect first-party PDF links published in the linked Wiki articles")
    parser.add_argument("--only",action="append",default=[],help="Recheck an exact document URL already present in the official link inventory")
    parser.add_argument("--host",action="append",default=[],help="Limit to selected source hosts (use api.github.com for approved Seeed repository files)")
    parser.add_argument("--github-cli",action="store_true",help="Maintainer only: read verified public Seeed repositories with the existing GitHub CLI account, on api.github.com.")
    parser.add_argument("--per-host-limit",type=int,help="Maximum source URLs per host in this run; subsequent batches reuse completed records")
    parser.add_argument("--product-documents",action="store_true",help="Prioritise manuals and product documents before the dedicated certificate collections")
    parser.add_argument("--global-catalog",action="store_true",help="Index explicit SKU mentions by page in the official 2026 global catalogue")
    parser.add_argument("--retry-redirects",action="store_true",help="Follow published redirects to supported first-party hosts, checking each host's rules in one serial queue")
    parser.add_argument("--extended-text",action="store_true",help="Reread long text manuals with PDFium and previously detected package tables with the quantity-optional parser")
    parser.add_argument("--recover-format",action="store_true",help="Retry local text-decoding failures with Poppler or native PDFium; source access and copy restrictions still apply")
    parser.add_argument("--verify-digests",action="store_true",help="Recheck older successfully read documents that lack a full file fingerprint")
    parser.add_argument("--ocr-scans",type=Path,help="Poppler pdftoppm executable for OCR of image-only publications during this download")
    parser.add_argument("--ocr-pending",action="store_true",help="Revisit previously retrieved image-only publications which still have no OCR result")
    parser.add_argument("--ocr-max-pages",type=int,default=50,help="Maximum physical pages per document for inline OCR (1–512)")
    options=parser.parse_args()
    if options.github_cli and options.host!=["api.github.com"]:
        parser.error("--github-cli requires exactly --host api.github.com")
    if not 1<=options.ocr_max_pages<=512:parser.error("choose an OCR page limit within 1–512")
    if options.ocr_scans and not options.ocr_scans.is_file():parser.error("the OCR renderer file does not exist")
    if options.pdftotext and not options.pdftotext.is_file():parser.error("the specified PDF text reader does not exist")
    if options.ocr_pending and not options.ocr_scans:parser.error("--ocr-pending requires --ocr-scans")
    if options.per_host_limit is not None and options.per_host_limit<1:parser.error("--per-host-limit must be positive")
    PDF_TEXT_TOOL=str(options.pdftotext.resolve()) if options.pdftotext else shutil.which("pdftotext")
    if not PDF_TEXT_TOOL or not Path(PDF_TEXT_TOOL).is_file():
        PDF_TEXT_TOOL=None
        if options.recover_format:
            try:import pypdfium2
            except ImportError:parser.error("--recover-format requires Poppler pdftotext or pypdfium2")
    PDFIUM_RECOVERY=bool(options.recover_format and not PDF_TEXT_TOOL)
    recovery_parser="pdfium" if PDFIUM_RECOVERY else "poppler"
    if not PDF_TEXT_TOOL:
        try:from pypdf import PdfReader
        except ImportError:parser.error("Install pypdf or specify a working pdftotext executable")
    doc=load_catalog(options.catalog);set_catalog_skus(p["sku"] for p in doc["products"]);sources=inventory(doc)
    if options.links:
        other=inventory(json.loads(options.links.read_text(encoding="utf-8-sig")))
        for url,entry in other.items():
            current=sources.setdefault(url,entry)
            current["skus"].update(entry["skus"])
            current["labels"].update(entry["labels"])
    out=options.output;out.mkdir(parents=True,exist_ok=True)
    scan=None;ocr_urls=set();ocr_digests=set()
    if options.ocr_scans:
        from .document_ocr import COMPLETED, eligible_scan_name, inline_checker
        scan=inline_checker(out,options.ocr_scans,options.ocr_max_pages)
        prior_ocr=out/"document-ocr.jsonl"
        if options.ocr_pending and prior_ocr.exists():
            for line in prior_ocr.read_text(encoding="utf-8").splitlines():
                item=json.loads(line)
                if item.get("status") in COMPLETED:
                    ocr_urls.add(item["url"])
                    if item.get("sha256"):ocr_digests.add(item["sha256"])
    log=out/"document-checks.jsonl";rules=Rules();done={}
    if options.github_cli:
        from .document_github import PublicGitHubCLI
        rules.github_cli=PublicGitHubCLI()
    rules.allow_published_redirects=options.retry_redirects
    if options.global_catalog:global_catalog_index(out,rules)
    only={canonical(x) for x in options.only}
    if log.exists():
        for ln in log.read_text(encoding="utf-8").splitlines():
            try:
                obj=json.loads(ln);done[obj["url"]]=obj
                retry=obj.get("retryAt",0)
                if isinstance(retry,(int,float)) and retry>time.time():
                    host="api.github.com" if github_file(obj["url"]) else urlsplit(obj["url"]).hostname
                    if (options.github_cli and host=="api.github.com" and obj.get("githubBudget")!="account"
                            and obj.get("reason")=="github_rate_limit" and obj.get("requestAttempted") is False):continue
                    rules.pause[host]=max(rules.pause.get(host,0),retry)
            except (ValueError,KeyError):pass
    offline_path=out/"wiki-offline-checks.json"
    rules.unavailable_publisher_keys={urlsplit(u).path.lstrip("/") for u,v in done.items()
        if urlsplit(u).hostname=="files.seeedstudio.com" and v.get("reason") in {"http_401","http_403","excluded_robots","protected_pdf"}}
    offline=json.loads(offline_path.read_text(encoding="utf-8")) if offline_path.exists() else {}
    for url,item in offline.items():
        for sku in set(item.get("purchaseSkus",[]))|set(item.get("declaredSkus",[])):add_source(sources,url,sku,item.get("title",""))
    lock=threading.Lock();attempted=set();host_counts=collections.Counter()
    def pass_once():
        queue=collections.defaultdict(list)
        for url,info in sources.items():
            if url in attempted:continue
            host=urlsplit(url).hostname
            request_host="api.github.com" if github_file(url) else host
            if options.host and request_host not in options.host:continue
            if options.product_documents and re.search(r"/(?:Seeed_Certificate|documents_certificate)/",url,re.I):continue
            if info["kind"]=="wiki" and url in offline and not only:continue
            old=done.get(url,{})
            revised=old.get("status")=="parsed" and not old.get("parserVersion")
            if options.ocr_pending:
                if (info["kind"]!="pdf" or old.get("reason")!="no_text_layer" or url in ocr_urls
                    or old.get("sha256") in ocr_digests or old.get("pages",0)>options.ocr_max_pages
                    or not eligible_scan_name(url)):continue
                revised=True
            if options.verify_digests:
                if info["kind"]!="pdf" or old.get("sha256") or old.get("status") not in {"empty","parsed"}:continue
                revised=True
            if options.extended_text:
                target=any((isinstance(s,dict) and s.get("explicitBox")) or
                           (isinstance(s,str) and re.search(r"package[-_ ]contents|in[-_ ]the[-_ ]box|packing[-_ ]list",s,re.I))
                           for s in old.get("sections",[]))
                table=any(isinstance(s,dict) and s.get("kind")=="accessory" for s in old.get("sections",[]))
                cn=re.search(r"[\u3400-\u9fff]|[_ -]cn[_ .-]|Chinese",unquote(urlsplit(url).path),re.I)
                version=old.get("parserVersion",0)
                dense_table=(version<9 and info["kind"]=="pdf" and old.get("status") in {"empty","parsed"}
                             and not re.search(r"/(?:seeed_certificate|documents_certificate)/",url,re.I)
                             and re.search(r"manual|guide|datasheet|kit|recomputer|reserver|sensecap|grove|station|gateway|module",unquote(url),re.I)
                             and any(len(values)>=3 for values in old.get("pageSkus",{}).values()))
                if not (dense_table or (target and version<8) or (version<6 and (old.get("reason")=="long_pdf" or table or (cn and old.get("status") in {"empty","parsed"})))):continue
                revised=True
            if old.get("reason")=="github_rate_limit" and isinstance(old.get("retryAt"),(int,float)) and old["retryAt"]<time.time():revised=True
            if options.github_cli and old.get("reason")=="github_rate_limit" and old.get("githubBudget")!="account" and old.get("requestAttempted") is False:revised=True
            if options.github_cli and old.get("reason") in {"github_cli_unavailable","github_secondary_limit"} and old.get("retryAt",0)<=time.time():revised=True
            if (options.github_cli and old.get("githubBudget")=="account" and old.get("bytes")
                    and not old.get("gitBlobSha") and old.get("reason","").startswith(("unreadable_","not_pdf"))):revised=True
            if github_file(url) and old.get("reason") in {"http_301","http_302"} and old.get("parserVersion",0)<9:revised=True
            if options.recover_format:
                reason=old.get("reason","")
                previous=set(old.get("formatRecoveries",[]))|{old.get("formatRecovery")}
                if not (reason=="long_pdf" or reason.startswith(("unreadable_","pdf_text_"))) or recovery_parser in previous:continue
                revised=True
            if options.retry_redirects:
                if old.get("reason")!="redirect_other_host" or not publisher_source(old.get("redirect","")):continue
                revised=True
            if old.get("reason")=="limit_bytes" and 0<old.get("bytes",0)<document_limit(url,info["kind"]):revised=True
            if old.get("reason")=="pdf_text_KeyError" and old.get("parserVersion",0)<7:revised=True
            if only and url not in only:continue
            if not only and old and not revised and old.get("reason") not in {"host_cooldown","robots_unverified","network","pdf_text_tool_missing","encrypted_pdf"}:continue
            if publisher_source(url) and info["kind"] in ("wiki","pdf","spreadsheet"):queue[host].append((url,info))
            elif github_file(url):queue["api.github.com"].append((url,info))
        def worker(entries):
            if options.github_cli and entries:
                if rules.github_cli.stop_reason or rules.github_cli.next_request>time.time():return
                if rules.pause.get("api.github.com",0)>time.time():
                    print("The previous GitHub access pause is still active; the document queue was preserved.",flush=True)
                    return
                targets=[github_file(url)[0] for url,_ in entries]
                try:rules.github_cli.prepare(targets)
                except (RuntimeError,OSError,ValueError,TypeError):
                    print("Public repository or account verification is unavailable; the queue was preserved.",flush=True)
                    return
            entries.sort(key=lambda pair:(pair[1]["kind"]!="wiki",
                         bool(re.search(r"/(?:Seeed_Certificate|documents_certificate)/",pair[0],re.I)),
                         bool(options.ocr_pending and done.get(pair[0],{}).get("sha256")),
                         not bool(re.search(r"parts?[\s_-]*list|accessor|pack(?:ing|age)[\s_-]*(?:list|contents)|in[\s_-]*the[\s_-]*box",
                                            unquote(urlsplit(pair[0]).path.rsplit("/",1)[-1]),re.I)),
                         not bool(re.search(r"recomputer|manual|guide|package|packing",unquote(pair[0]),re.I)),pair[0]))
            for url,info in entries:
                host="api.github.com" if github_file(url) else urlsplit(url).hostname
                if options.per_host_limit is not None and host_counts[host]>=options.per_host_limit:break
                requested=url
                if options.retry_redirects:
                    published=done.get(url,{}).get("redirect","")
                    if publisher_source(published):requested=published
                result=fetch_one(requested,info,rules,scan)
                if requested!=url:result["publishedRedirect"]=requested
                result.update(url=url,kind=info["kind"],parserVersion=9,checkedAt=datetime.now(timezone.utc).isoformat(timespec="seconds"))
                if options.recover_format and result.get("reason") not in {"github_rate_limit","host_cooldown","network"}:
                    old=done.get(url,{})
                    result["formatRecovery"]=recovery_parser
                    result["formatRecoveries"]=sorted({p for p in [*old.get("formatRecoveries",[]),old.get("formatRecovery"),recovery_parser] if p})
                with lock:
                    attempted.add(url);host_counts[host]+=1
                    done[url]=result
                    with log.open("a",encoding="utf-8") as f:f.write(json.dumps(result,ensure_ascii=False)+"\n")
                    if len(done)%30==0:print("Unique documents processed:",len(done),flush=True)
                if options.github_cli and (rules.github_cli.stop_reason or rules.github_cli.next_request>time.time()):break
        with ThreadPoolExecutor(max_workers=1 if options.retry_redirects else 4) as pool:
            for future in [pool.submit(worker,entries) for entries in queue.values()]:future.result()
    def discover_known_attachments():
        for url,record in list(done.items())+list(offline.items()):
            if url not in sources or record.get("kind")!="wiki":continue
            for target,label in {**record.get("linkedPdfs",{}),**record.get("linkedSheets",{})}.items():
                for sku in set(sources[url]["skus"]):
                    add_source(sources,target,sku,label)
    if options.discovered:
        # Known manual links should compete for the same quota in the first
        # priority queue, alongside direct store PDFs and before certificates.
        discover_known_attachments()
    pass_once()
    if options.discovered:
        discover_known_attachments()
        pass_once()
    index={url:{"kind":e["kind"],"skus":sorted(e["skus"]),"labels":sorted(e["labels"])} for url,e in sources.items()}
    if not (only or options.host or options.retry_redirects or options.extended_text or options.product_documents or options.recover_format or options.verify_digests or options.per_host_limit):
        atomic_write(out/"document-links.json",json.dumps(index,ensure_ascii=False).encode("utf-8"))
    counts=collections.Counter()
    for url,entry in sources.items():
        status=done.get(url,{}).get("status","unread")
        counts[(entry["kind"],status)]+=1
    print("Final counts",sorted(counts.items()),flush=True)


if __name__=="__main__":
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    run()
