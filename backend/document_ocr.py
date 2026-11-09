"""Read short image-only product documents with installed Windows OCR and Poppler."""
import argparse
import collections
import hashlib
import io
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
from urllib.parse import unquote, urlsplit
from .document_enrichment import ACC, PART, SKU, Rules, compact, github_file

COMPLETED={"candidate_review","no_target_found","partial_or_unreadable"}
DRAWING=re.compile(r"schematic|(?:^|[-_. ])sch(?:[-_. ]|$)|pinout|footprint|mechanical|circuit.diagram|pcba",re.I)


def eligible_scan_name(url):
    return not DRAWING.search(unquote(urlsplit(url).path.rsplit("/",1)[-1]))


def inline_checker(output,renderer,max_pages):
    """Use the PDF already in memory; OCR each distinct accessible file once."""
    import threading
    dest=output/"document-ocr.jsonl"
    complete=set();attempted=set();guard=threading.Lock()
    if dest.is_file():
        for line in dest.read_text(encoding="utf-8").splitlines():
            try:event=json.loads(line)
            except ValueError:continue
            if event.get("sha256") and event.get("status") in COMPLETED:complete.add(event["sha256"])
    def check(url,pdf,record):
        if record.get("reason")!="no_text_layer" or not eligible_scan_name(url):return
        if record.get("pages",0)>max_pages:return
        digest=record["sha256"]
        with guard:
            if digest in complete or digest in attempted:return
            attempted.add(digest)
            language="zh-Hans-CN" if re.search(r"[_-](?:zh|cn)[._-]|chinese",url,re.I) else "en-US"
            try:result=inspect(pdf,renderer,language,max_pages)
            except Exception:result={"status":"ocr_engine_error"}
            if result["status"] in COMPLETED:complete.add(digest)
            result.update(url=url,sha256=digest,checkedAt=datetime.now(timezone.utc).isoformat(timespec="seconds"))
            with dest.open("a",encoding="utf-8") as f:f.write(json.dumps(result,ensure_ascii=False)+"\n")
    return check


def inspect(pdf,render,language,max_pages=25):
    from pypdf import PdfReader
    from pypdf.constants import UserAccessPermissions
    document=PdfReader(io.BytesIO(pdf),strict=False)
    if document.is_encrypted:
        try:
            permitted=document.user_access_permissions
            if not permitted or not permitted & UserAccessPermissions.EXTRACT:return {"status":"source_unavailable","reason":"protected_pdf"}
        except Exception:return {"status":"source_unavailable","reason":"protected_pdf"}
    expected=len(document.pages)
    if not 1<=expected<=max_pages:return {"status":"outside_ocr_range","pages":expected}
    win=Path(os.environ["SystemRoot"])/"System32/WindowsPowerShell/v1.0/powershell.exe"
    script=Path(__file__).with_suffix(".ps1").resolve()
    # Only transient rendered pages are written. The downloaded PDF stays in RAM.
    hits=[]; counts=[]
    for first in range(1,expected+1,18):
        last=min(expected,first+17)
        with tempfile.TemporaryDirectory(prefix="seeed-doc-ocr-") as temp:
            target=Path(temp)/"page"
            result=subprocess.run([str(render),"-f",str(first),"-l",str(last),"-scale-to","1450","-jpeg","-",str(target)],
                                  input=pdf,capture_output=True,timeout=70)
            if result.returncode or len(list(Path(temp).glob("*.jpg")))!=last-first+1:return {"status":"render_failed"}
            output=subprocess.run([str(win),"-NoProfile","-NonInteractive","-File",str(script),"-ImageFolder",temp,"-Language",language],
                                  capture_output=True,timeout=120)
            if output.returncode:return {"status":"ocr_engine_error"}
            pages=json.loads(output.stdout.decode("utf-8-sig"))
        if not isinstance(pages,list) or len(pages)!=last-first+1:return {"status":"ocr_engine_error"}
        for i,text in enumerate(pages,first):
            counts.append(len(compact(text)))
            section=next((s for s in (compact(t) for t in text.splitlines()) if 3<=len(s)<80 and (PART.search(s) or ACC.search(s))),None)
            if section:hits.append({"page":i,"heading":section[:75],"possibleSkus":sorted(set(SKU.findall(text)))[:40]})
    return {"status":"candidate_review" if hits else ("no_target_found" if all(c>=35 for c in counts) else "partial_or_unreadable"),
            "pages":expected,"pagesWithText":sum(c>=35 for c in counts),"candidates":hits}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True);parser.add_argument("--pdftoppm",type=Path,required=True)
    parser.add_argument("--limit",type=int)
    parser.add_argument("--min-pages",type=int,default=0)
    parser.add_argument("--max-pages",type=int,default=25,help="OCR at most this many physical pages per file, in temporary groups of 18")
    parser.add_argument("--shared-only",action="store_true",help="Read one representative of each previously fetched identical PDF body")
    parser.add_argument("--host",action="append",default=[],help="Only process URLs from the selected official hosts")
    parser.add_argument("--product-documents",action="store_true",help="Prioritise product manuals before dedicated certificate directories")
    args=parser.parse_args()
    if not 0<=args.min_pages<=args.max_pages<=512 or args.max_pages<1:parser.error("choose a page range within 0–512")
    rules=Rules()
    records={}
    for line in (args.output/"document-checks.jsonl").read_text(encoding="utf8").splitlines():
        try:r=json.loads(line)
        except ValueError:continue
        records[r["url"]]=r
        retry=r.get("retryAt",0)
        if isinstance(retry,(float,int)) and retry>time.time():
            host="api.github.com" if github_file(r["url"]) else urlsplit(r["url"]).hostname
            rules.pause[host]=max(rules.pause.get(host,0),retry)
    dest=args.output/"document-ocr.jsonl"
    done={}
    if dest.is_file():
        for line in dest.read_text(encoding="utf8").splitlines():
            r=json.loads(line);done[r["url"]]=r
    handled={v["sha256"] for v in done.values() if v.get("sha256") and v["status"] in COMPLETED}
    frequencies=collections.Counter(v["sha256"] for v in records.values() if v.get("sha256") and v.get("reason")=="no_text_layer")
    def eligible(item):
        url,r=item
        if args.host and urlsplit(url).hostname not in args.host:return False
        if args.product_documents and re.search(r"/(?:Seeed_Certificate|documents_certificate)/",url,re.I):return False
        host="api.github.com" if github_file(url) else urlsplit(url).hostname
        if rules.pause.get(host,0)>time.time():return False
        if r.get("reason")!="no_text_layer" or not args.min_pages<=r.get("pages",0)<=args.max_pages:return False
        if args.shared_only and frequencies[r.get("sha256","")]<2:return False
        if url in done and not (r.get("sha256") and done[url].get("sha256") and r["sha256"]!=done[url]["sha256"]):
            expanded=done[url].get("status")=="outside_ocr_range" and done[url].get("pages",513)<=args.max_pages
            if not expanded and done[url].get("reason") not in {"host_cooldown","github_rate_limit","network","robots_unverified"}:return False
        return eligible_scan_name(url)
    pending=[x for x in records.items() if eligible(x)]
    pending.sort(key=lambda pair:(-frequencies[pair[1].get("sha256","")] if args.shared_only else 0,
                                  not bool(re.search("manual|guide|catalog|kit|accessor",pair[0],re.I)),pair[1]["pages"],pair[0]))
    print("Short image-only publications selected:",len(pending),flush=True)
    attempted=0
    for url,r in pending:
        if r.get("sha256") in handled:continue
        if args.limit is not None and attempted>=args.limit:break
        attempted+=1
        meta,body=rules.fetch(url,"pdf")
        if body is None:result={"status":"source_unavailable","reason":meta.get("reason")}
        else:
            try:result=inspect(body,args.pdftoppm,"zh-Hans-CN" if re.search(r"[_-](?:cn|zh)[._-]|chinese",url,re.I) else "en-US",args.max_pages)
            except (OSError,ValueError,subprocess.TimeoutExpired):result={"status":"ocr_engine_error"}
            result["sha256"]=hashlib.sha256(body).hexdigest()
            if result["status"] in COMPLETED:handled.add(result["sha256"])
        result["checkedAt"]=datetime.now(timezone.utc).isoformat(timespec="seconds")
        result["url"]=url
        with dest.open("a",encoding="utf8") as f:f.write(json.dumps(result,ensure_ascii=False)+"\n")
        print(result["status"], result.get("pages",0),flush=True)
        if result["status"]=="ocr_engine_error":break


if __name__=="__main__":main()
