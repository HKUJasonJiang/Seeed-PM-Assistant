"""On-demand public Bazaar search, with conservative identity and resumable errors."""
from datetime import datetime, timezone
import re
import time
import unicodedata
from urllib.parse import quote, unquote, urlsplit

from .storage import Problem
from .storefront import OfficialStore, RateLimit, STORE

SEARCH_QUERY='query($q:String!,$page:Int!){products(search:$q,pageSize:20,currentPage:$page){total_count items{sku name url_key url_suffix}}}'
SKU_QUERY='query($sku:String!){products(filter:{sku:{eq:$sku}},pageSize:20,currentPage:1){total_count items{sku name url_key url_suffix}}}'
SEARCH_VERSION=2


def identity(value):
    value=unicodedata.normalize("NFKC",value).casefold()
    return re.sub(r"\s+"," ",re.sub("[‐‑‒–—−]","-",value)).strip()


def product_path(url):
    try:
        parsed=urlsplit(url)
        if parsed.scheme!="https" or parsed.hostname!="www.seeedstudio.com" or parsed.username or parsed.password:return ""
        if parsed.port not in (None,443) or not parsed.path.endswith(".html"):return ""
        return unquote(parsed.path)
    except ValueError:return ""


def candidate(item):
    sku=item.get("sku");name=item.get("name");key=item.get("url_key");suffix=item.get("url_suffix") or ".html"
    if not all(isinstance(v,str) and v for v in (sku,name,key)):return None
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,55}",sku) or suffix!=".html":return None
    if "/" in key or "\\" in key or key in {".",".."}:return None
    url=STORE+quote(key,safe="-_.~%")+".html"
    return {"sku":sku,"name":name,"url":url,"source":url}


def search_term(name):
    # Bazaar combines long descriptions broadly. Prefer a stated manufacturer model.
    head=re.split(r"\s+[—–]|\s+(?:for|used with)\s+",name,flags=re.I)[0].strip()
    if re.fullmatch(r"[A-Z]{2,}-(?:[A-Za-z]+-)?\d{3,}|MXKIT-[A-Za-z]+(?:-\d+)?",head):return head
    models=re.findall(r"(?<![a-z0-9])(?:[a-z]{2,}-)?[a-z]+\d[a-z0-9]*(?![a-z0-9])",identity(head))
    models=[m for m in models if len(m)>=5]
    if models:return max(models,key=len)
    for word in ("lightning","fiberglass","bracket","zigbee","flange","pole"):
        if word in identity(name):return word
    return name.strip()


def relevant(name, term, requested=""):
    compact=lambda value:re.sub(r"[^a-z0-9]","",identity(value))
    if re.fullmatch(r"(?:[a-z]{2,}-)?[a-z]+\d[a-z0-9]*",term):
        return compact(term) in compact(name)
    words=re.findall(r"[a-z0-9]+",identity(term))
    words=[w for w in words if w not in {"for","the","with","optional","inch","inches"}]
    title=compact(name)
    if term=="bracket" and "antenna" in identity(requested) and "antenna" not in title:return False
    if term=="lightning" and not any(word in title for word in ("protector","arrestor","arrester")):return False
    if term=="flange" and not any(word in title for word in ("bracket","plate")):return False
    tokens=re.findall(r"[a-z0-9]+",identity(name))
    return bool(words) and all(word in tokens or (word=="ble" and "bluetooth" in tokens) for word in words)


def refine_status(report):
    if report.get("status") in {"candidates","confirmed"} and not report.get("expectedSku"):
        report["candidates"]=[r for r in report.get("candidates",[]) if relevant(r["name"],report["searchTerm"],report["query"])]
    if report.get("status")=="candidates" and not report.get("candidates"):
        report["status"]="no_title_match"
    if report.get("status") in {"candidates","no_title_match"} and not report.get("expectedSku") and re.fullmatch(
            r"(?:power adapter(?: \(optional\))?|mini usb cable|microusb cable|solar panel|sim-card|3\.7v li-ion battery|dc/dc voltage regulator|usb to uart tool)",identity(report["query"])):
        report.update(status="needs_specification",candidates=[],error="ELECTRICAL_OR_MECHANICAL_VARIANT_REQUIRED")
    return report


def check_accessory(name, remote=None, expected_sku="", product_url="", cache=None):
    """Call only after an explicit user action, with names from the public catalogue.

    An exact published SKU confirms that listing. Name searches confirm only unique
    complete names. Approximate names remain candidates for a person to inspect.
    """
    if not isinstance(name,str) or not 1<=len(name.strip())<=300:raise Problem("INVALID_ACCESSORY_NAME")
    if not isinstance(expected_sku,str) or (expected_sku and not re.fullmatch(r"[A-Za-z0-9_.-]{1,55}",expected_sku)):raise Problem("INVALID_SKU")
    if product_url and not product_path(product_url):raise Problem("INVALID_STORE_URL")
    remote=remote or OfficialStore()
    report={"query":name.strip(),"checkedAt":datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source":STORE+"graphql","status":"source_error","method":"published_sku" if expected_sku else "name",
            "candidates":[],"total":None,"searchVersion":SEARCH_VERSION,"pagesRead":0}
    if expected_sku:report["expectedSku"]=expected_sku
    try:
        term=search_term(name)
        report["searchTerm"]=expected_sku or term
        query,variables=(SKU_QUERY,{"sku":expected_sku}) if expected_sku else (SEARCH_QUERY,{"q":term,"page":1})
        # The caller may share a cache only for one explicit batch, never across updates.
        if cache is None:cache={}
        cache_key=(expected_sku,term if not expected_sku else "")
        if cache_key not in cache:cache[cache_key]=(remote.public_query(query,variables).get("products"),report["checkedAt"])
        result,report["checkedAt"]=cache[cache_key]
        if not isinstance(result,dict) or not isinstance(result.get("items"),list):raise Problem("STORE_API_CHANGED")
        report["pagesRead"]=1
        items=list(result["items"])
        total=result.get("total_count")
        if not expected_sku and isinstance(total,int):
            # A finite, explicit lookup. Large broad searches remain incomplete.
            for page in range(2,min(5,(total+19)//20)+1):
                page_result=remote.public_query(SEARCH_QUERY,{"q":term,"page":page}).get("products",{})
                if not isinstance(page_result.get("items"),list):raise Problem("STORE_API_CHANGED")
                items.extend(page_result["items"]);report["pagesRead"]+=1
        candidates=[row for item in items if isinstance(item,dict) and (row:=candidate(item)) and
                    (row["sku"]==expected_sku if expected_sku else relevant(row["name"],term,name))]
        report["candidates"]=list({(r["sku"],r["url"]):r for r in candidates}.values())
        report["total"]=total
        report["truncated"]=isinstance(total,int) and total>len(items)
        exact=[r for r in report["candidates"] if (r["sku"]==expected_sku if expected_sku else identity(r["name"])==identity(name))]
        if product_url:exact=[r for r in exact if product_path(r["url"])==product_path(product_url)]
        if len(exact)==1:
            report["status"]="confirmed";report["match"]=exact[0]
        elif report["candidates"]:report["status"]="candidates"
        elif result.get("total_count")==0:report["status"]="not_found"
        else:report.update(status="no_title_match",error="NO_PRECISE_TITLE_IN_RETURNED_RESULTS")
        if len(report["candidates"])>8:
            report["candidateCount"]=len(report["candidates"]);report["candidates"]=report["candidates"][:8]
    except RateLimit as exc:
        report.update(status="rate_limited",retryAfter=exc.until,error="STORE_RATE_LIMIT")
    except Problem as exc:
        report.update(status="excluded" if exc.code=="ROBOTS_EXCLUDED" else "source_error",error=exc.code)
    return refine_status(report)


def ready_to_retry(report):
    return report.get("searchVersion")!=SEARCH_VERSION or (not report.get("expectedSku") and report.get("searchTerm")!=search_term(report["query"])) or (
        report.get("status") in {"source_error","rate_limited"} and report.get("retryAfter",0)<=time.time())
