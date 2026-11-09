"""Checkpointed, serial audit of the public overseas catalogue; output is always staged."""
import argparse
from datetime import datetime,timezone
from collections import Counter,defaultdict
from contextlib import contextmanager
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.parse import quote,urlsplit,unquote
from xml.etree import ElementTree
from .storage import CATALOG_PREFIX,ROOT,Problem,packed,write
from .storefront import STORE,ITEM_FIELDS,DETAIL_FIELDS,PRODUCT_PAGE_BYTE_LIMIT,OfficialStore,RateLimit
from .extract import content_state


def stamp():return datetime.now(timezone.utc).isoformat(timespec="seconds")


def save(path,obj):
    raw=packed(obj)
    write(path,gzip.compress(raw,compresslevel=3) if path.suffix==".gz" else raw)


def load(path):
    raw=path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix==".gz" else raw)


class SerialStore(OfficialStore):
    def __init__(self):
        super().__init__()
        self.policy=None
        self.last=0

    def get(self,url,*args,**opts):
        if self.policy is not None and not self.policy.allows(url):raise Problem("ROBOTS_EXCLUDED")
        delay=self.policy.delay if self.policy is not None else 1
        time.sleep(max(0,self.last+delay-time.monotonic()))
        self.last=time.monotonic()
        return super().raw_get(url,*args,**opts)

    def redirect_allowed(self,url):
        return self.policy.allows(url) if self.policy is not None else super().redirect_allowed(url)


@contextmanager
def worker_lock(folder):
    import msvcrt
    with (folder/"network-worker.lock").open("a+b") as handle:
        if handle.tell()==0:handle.write(b"1");handle.flush()
        handle.seek(0)
        try:msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:raise SystemExit("A collector is already using this stage.") from None
        try:yield
        finally:
            handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)


def baseurl(row,previous):
    key=row.get("url_key")
    return STORE+quote(key,safe="/%()_-.")+(row.get("url_suffix") or "") if key else previous.get("url","")


def extract_sitemap(raw):
    doc=ElementTree.fromstring(raw)
    if not doc.tag.endswith("urlset"):raise Problem("SITEMAP_LAYOUT_CHANGED")
    return list(dict.fromkeys(n.text.strip() for n in doc.findall("{*}url/{*}loc") if n.text))


def inventory(remote,folder):
    listing='query($page:Int!){products(search:"",pageSize:80,currentPage:$page){total_count page_info{total_pages} items{'+ITEM_FIELDS+' stock_status related_products{sku} upsell_products{sku} crosssell_products{sku}}}}'
    rows={};page=1
    while True:
        path=folder/f"listing-{page:03d}.json.gz"
        if not path.exists():save(path,{"at":stamp(),"data":remote.public_query(listing,{"page":page})["products"]})
        result=load(path)["data"]
        for row in result["items"]:
            if row["sku"] in rows:raise Problem("STORE_CATALOG_CHANGED")
            rows[row["sku"]]=row
        if page>=result["page_info"]["total_pages"]:break
        if page%8==0:print("Catalogue inventory",page,"/",result["page_info"]["total_pages"],flush=True)
        page+=1
    if len(rows)!=result["total_count"]:raise Problem("STORE_CATALOG_CHANGED")
    return rows


def navigation(remote,folder):
    path=folder/"categories.json"
    if not path.exists():
        categories=remote.public_query("{categoryList{id name children{id name url_path}}}")["categoryList"][0]["children"]
        save(path,categories)
    categories=load(path)
    for c in categories:
        ident=c["id"];cache=folder/f"category-{ident}.json"
        if cache.exists():continue
        page=1; skus=[]
        while True:
            query="query($c:String!,$p:Int!){products(filter:{category_id:{eq:$c}},pageSize:250,currentPage:$p){total_count page_info{total_pages} items{sku}}}"
            p=remote.public_query(query,{"c":str(ident),"p":page})["products"]
            skus.extend(item["sku"] for item in p["items"])
            if page>=p["page_info"]["total_pages"]:break
            page+=1
        if len(set(skus))!=p["total_count"]:raise Problem("STORE_CATALOG_CHANGED")
        save(cache,{"at":stamp(),"members":skus})
    return categories


def staged_rows(folder):
    rows={};dates={}
    for path in sorted(folder.glob("listing-*.json.gz")):
        chunk=load(path)
        for row in chunk["data"]["items"]:
            rows[row["sku"]]=row
            dates[row["sku"]]=chunk["at"]
    return rows,dates


def references(folder,baseline):
    from .extract import tree,links,wiki_references
    previous={p["sku"]:p for p in baseline["products"]}
    result={sku:{"sku":sku,"name":p["name"],"productUrl":p["url"],"source":"previous",
            "docs":p.get("docs",[]),"wikiLinks":p.get("wikiLinks",[])} for sku,p in previous.items()}
    rows,_=staged_rows(folder)
    if (folder/"extras.json.gz").exists():rows.update(load(folder/"extras.json.gz")["products"])
    for sku,row in rows.items():
        p=result.get(sku,{})
        url=baseurl(row,previous.get(sku,{})) or row.get("verifiedUrl","");refs=links(tree((row.get("description") or {}).get("html")),url)
        p.update(sku=sku,name=row["name"],productUrl=url,source="listing")
        p["docs"]=list({d["url"]:d for d in p.get("docs",[])+[d for d in refs if re.search(r"\.pdf(?:$|[?#])",d["url"],re.I)]}.values())
        p["wikiLinks"]=wiki_references(p.get("wikiLinks",[])+refs)
        result[sku]=p
    seen=0
    batches=[load(path)["records"] for path in sorted(folder.glob("sections-*.json.gz"))]
    for path in (folder/"pages").glob("*.json.gz"):
        rec=load(path)
        if rec.get("status")=="ok":batches.append({rec["sku"]:rec.get("sections")})
    for batch in batches:
        for sku,section in batch.items():
            if not isinstance(section,dict):continue
            p=result[sku];url=p["productUrl"]
            docs = {r["url"]: r for r in p.get("docs", [])}
            wiki = list(p.get("wikiLinks", []))
            for key in DETAIL_FIELDS:
                value = section.get(key)
                if not isinstance(value, str) or "<a" not in value.lower():
                    continue
                refs = links(tree(value), url)
                for link in refs:
                    if key == "documents" or re.search(r"\.pdf(?:$|[?#])", link["url"], re.I):
                        docs[link["url"]] = link
                wiki.extend(refs)
            p["docs"] = list(docs.values())
            p["wikiLinks"] = wiki_references(wiki)
            if "documents" in section:
                p["source"] = "documents"
                seen += 1
    save(folder/"document-links.json",{"at":stamp(),"listingRead":len(rows),"sectionsRead":seen,
         "products":[p for p in result.values() if p["docs"] or p["wikiLinks"]]})
    print("Source references",len(rows),"inventory records,",seen,"documents fields",flush=True)


def path_key(url):
    u=urlsplit(url)
    return (u.hostname or "").lower()+unquote(u.path).rstrip("/").casefold()


def public_pid(url):
    m=re.search(r"-p-(\d+)\.html$",urlsplit(url).path,re.I)
    return int(m[1]) if m else None


def reconcile(folder,baseline):
    rows,_=staged_rows(folder)
    if not (folder/"eligibility.json").exists():raise Problem("INVENTORY_NOT_COMPLETE")
    old={p["sku"]:p for p in baseline["products"]}
    by_url=defaultdict(list)
    for sku,row in rows.items():
        by_url[path_key(baseurl(row,old.get(sku,{})))].append(sku)
    remote=SerialStore()
    remote.policy=remote.policy_for(STORE)
    sitemap=load(folder/"sitemap.json.gz")["urls"]
    candidates=[s for s in sitemap if path_key(s) not in by_url and not re.search(r"-c-\d+\.html$",urlsplit(s).path,re.I)]
    all_routes={}
    for pos in range(0,len(candidates),15):
        cache=folder/f"routes-{pos:04d}.json"
        if cache.exists():all_routes.update(load(cache));continue
        chunk=candidates[pos:pos+15]
        answer={}
        batch={}
        for i,url in enumerate(chunk):
            if not remote.policy.allows(url):answer[url]={"state":"excluded"};continue
            if urlsplit(url).path=="/":answer[url]={"state":"homepage"};continue
            batch["r"+str(i)]=url
        if batch:
            query='query{'+" ".join(alias+':route(url:'+json.dumps(urlsplit(url).path.lstrip("/"))+'){__typename relative_url redirect_code type ... on ProductInterface {id sku name url_key url_suffix}}' for alias,url in batch.items())+'}'
            result=remote.public_query(query,allow_partial=True)
            for alias,url in batch.items():
                if alias not in result:answer[url]={"state":"source_error"};continue
                r=result.get(alias)
                if not isinstance(r,dict):answer[url]={"state":"no_route"};continue
                sku=r.get("sku")
                state=("resolved_product" if sku else ("redirect" if r.get("redirect_code") else "resolved_nonproduct"))
                answer[url]={"state":state,"sku":sku,"target":r.get("relative_url"),"type":r.get("type"),"redirectCode":r.get("redirect_code"),"storeId":r.get("id")}
        save(cache,answer);all_routes.update(answer)
    beyond={r["sku"] for r in all_routes.values() if r.get("sku") and r["sku"] not in rows}
    for c in load(folder/"categories.json"):
        beyond.update(set(load(folder/f'category-{c["id"]}.json')["members"])-rows.keys())
    extra={}
    for i in range(0,len(beyond),50):
        query='query($ids:[String]!){products(filter:{sku:{in:$ids}},pageSize:50){items{'+ITEM_FIELDS+' stock_status related_products{sku} upsell_products{sku} crosssell_products{sku}}}}'
        for row in remote.public_query(query,{"ids":sorted(beyond)[i:i+50]})["products"]["items"]:
            if row["sku"] in beyond:extra[row["sku"]]=row
    for sku in sorted(beyond-extra.keys()):
        source=next((url for url,r in all_routes.items() if r.get("sku")==sku),None)
        if not source:continue
        query='query($path:String!){route(url:$path){... on ProductInterface{'+ITEM_FIELDS+' stock_status related_products{sku} upsell_products{sku} crosssell_products{sku}}}}'
        result=remote.public_result(query,{"path":urlsplit(source).path.lstrip("/")})
        row=result["data"].get("route")
        if row and row.get("sku")==sku and row.get("id") and row.get("name"):
            row["sourceErrors"]=[e["path"][1:] for e in result.get("errors",[]) if e.get("path",[None])[0]=="route"]
            row["verifiedUrl"]=source
            extra[sku]=row
    save(folder/"extras.json.gz",{"at":stamp(),"products":extra})
    save(folder/"reconciliation.json",{"checkedAt":stamp(),"sources":all_routes,"additionalCandidates":sorted(beyond),"additionalVerified":sorted(extra)})
    print("Reconciled",len(all_routes),"unmatched sitemap URLs;",len(extra),"additional verified storefront SKUs",flush=True)


def collect(folder,baseline):
    status=folder/"progress.json"
    state=load(status) if status.exists() else {}
    if state.get("retryAfter",0)>time.time():raise RateLimit(state["retryAfter"])
    remote=SerialStore()
    remote.policy=remote.policy_for(STORE)
    robots=remote.policy.text
    if not remote.policy.allows(STORE+"graphql"):raise Problem("ROBOTS_EXCLUDED")
    save(folder/"policy.json",{"at":stamp(),"url":STORE+"robots.txt","text":robots})
    try:
        if not (folder/"sitemap.json.gz").exists():
            links=extract_sitemap(remote.get(STORE+"sitemap.xml",20_000_000))
            save(folder/"sitemap.json.gz",{"at":stamp(),"urls":links})
        rows=inventory(remote,folder)
        print("Verified inventory",len(rows),flush=True)
        categories=navigation(remote,folder)
        print("Verified category lists",len(categories),flush=True)
        old={p["sku"]:p for p in baseline["products"]}
        eligible=[];excluded={}
        for sku,row in rows.items():
            url=baseurl(row,old.get(sku,{}))
            if not url or not remote.policy.allows(url):excluded[sku]=url
            else:eligible.append(row)
        save(folder/"eligibility.json",{"eligible":[p["sku"] for p in eligible],"excluded":excluded})
        save(status,{"phase":"inventory_complete","eligible":len(eligible),"at":stamp()})
    except RateLimit as e:
        save(status,{**(load(status) if status.exists() else {}),"retryAfter":e.until,"at":stamp()})
        raise


def read_public_detail(remote, url, sku):
    try:
        return remote.detail(url, sku)
    except Problem as error:
        if error.code != "STORE_UNREACHABLE":
            raise
    # One transport retry. Server denials, challenges, rate limits, and HTTP
    # errors retain their own handling and never pass through this path.
    print("Connection interrupted; waiting one minute before retrying SKU", sku, flush=True)
    time.sleep(60)
    return remote.detail(url, sku)


def public_pages(folder,baseline,report=None):
    """Read the normal public product page, respecting the host's limits across runs."""
    previous={p["sku"]:p for p in baseline["products"]}
    rows,_=staged_rows(folder)
    available=load(folder/"eligibility.json")
    if (folder/"extras.json.gz").exists():
        extras=load(folder/"extras.json.gz")["products"]
        rows.update(extras)
        available["eligible"].extend(s for s in extras if s not in available["eligible"])
    state_path=folder/"page-progress.json"
    state=load(state_path) if state_path.exists() else {}
    if state.get("forbidden"):
        print("Normal product page access was denied. Further page reads are stopped:",state.get("error","STORE_HTTP_403"))
        return
    if state.get("retryAfter",0)>time.time():raise RateLimit(state["retryAfter"])
    remote=SerialStore()
    remote.policy=remote.policy_for(STORE)
    rate_limits = state.get("rateLimitCount", int(bool(state.get("retryAfter"))))
    # After the required cooldown, reduce request frequency for the remainder
    # of this stage even if the host no longer returns a Retry-After header.
    remote.policy.delay=max(5, min(60, 8 * rate_limits), state.get("minInterval", 0), remote.policy.delay)
    dest=folder/"pages";dest.mkdir(exist_ok=True)
    existing={item["sku"]:(item.get("error"),item.get("identitySchema",0),item.get("pageByteLimit",10_000_000))
              for path in dest.glob("*.json.gz") if (item:=load(path))}
    recheck={s for s,(error,version,byte_limit) in existing.items() if (error=="DETAIL_SKU_NOT_VERIFIED" and version<2)
             or (error=="STORE_RESPONSE_TOO_LARGE" and byte_limit<PRODUCT_PAGE_BYTE_LIMIT)}
    priority={"100025879","110110145","110110184","114110314","113991334"}
    menu=load(folder/"categories.json");group_rank={}
    for index,cat in enumerate(menu):
        for sku in load(folder/f'category-{cat["id"]}.json')["members"]:group_rank.setdefault(sku,index)
    targets=sorted(available["eligible"],key=lambda sku:(sku not in recheck,sku not in priority,sku in previous,group_rank.get(sku,len(menu)),
                   previous.get(sku,{}).get("details",False),int(rows[sku]["id"])))
    n=len(existing);remaining_rechecks=len(recheck)
    resuming=bool(state.get("phase")=="interrupted" or state.get("retryAfter"))
    if recheck:print("Rechecking earlier pages after a public-layout or local reader-limit change:",len(recheck),flush=True)
    for sku in targets:
        if (folder/"pause.request").exists():
            print("Paused at a saved product boundary.",flush=True)
            return
        row=rows[sku];path=dest/(str(row["id"])+".json.gz")
        if sku in existing and sku not in recheck:continue
        url=baseurl(row,previous.get(sku,{}))
        item={"sku":sku,"source":"product_page","url":url,"at":stamp(),"status":"ok","identitySchema":2}
        if not remote.policy.allows(url):item["status"]="excluded"
        else:
            try:
                sections=read_public_detail(remote,url,sku)
                remote.verify_entity_id(sections,row["id"])
                item["sections"]=sections
            except RateLimit as e:
                save(state_path,{"completed":n,"eligible":len(targets),"retryAfter":e.until,"failedSku":sku,
                                 "rateLimitCount":state.get("rateLimitCount",int(bool(state.get("retryAfter"))))+1,"at":stamp()})
                if report:report()
                raise
            except Problem as e:
                item.update(status="source_error",error=e.code)
                if e.code=="STORE_RESPONSE_TOO_LARGE":item["pageByteLimit"]=PRODUCT_PAGE_BYTE_LIMIT
                if getattr(e,"observed",None):item["identity"]=e.observed
                if e.code in {"STORE_HTTP_401","STORE_HTTP_403","STORE_ACCESS_CHALLENGE"}:
                    save(path,item);save(state_path,{"completed":n+int(sku not in existing),"eligible":len(targets),"forbidden":True,"error":e.code,"failedSku":sku,"at":stamp()})
                    print("Normal public page access denied:",e.code,sku,flush=True)
                    if report:report()
                    return
                if e.code in ("STORE_UNREACHABLE","STORE_HTTP_500","STORE_HTTP_502","STORE_HTTP_503","STORE_HTTP_504"):
                    save(state_path,{"phase":"interrupted","completed":n,"eligible":len(targets),"at":stamp(),
                                     "error":e.code,"failedSku":sku,"minInterval":remote.policy.delay,
                                     "rateLimitCount":state.get("rateLimitCount",0)})
                    if report:report()
                    raise
        save(path,item)
        if sku in recheck:
            remaining_rechecks-=1
            if not remaining_rechecks:
                print("Previously unread pages rechecked:",len(recheck),flush=True)
                if report and n<len(targets):report()
            continue
        n+=1
        if resuming or n%25==0:
            save(state_path,{"completed":n,"eligible":len(targets),"at":stamp(),"minInterval":remote.policy.delay,
                             "rateLimitCount":state.get("rateLimitCount",int(bool(state.get("retryAfter"))))})
            print("Verified public pages",n,"/",len(targets),flush=True)
            resuming=False
        if report and n%500==0 and n<len(targets):report()
    save(state_path,{"completed":n,"eligible":len(targets),"at":stamp(),"phase":"complete",
                     "minInterval":remote.policy.delay,"rateLimitCount":state.get("rateLimitCount",0)})
    if report:report()


def read_sections(folder):
    result={}
    for path in sorted(folder.glob("sections-*.json.gz")):
        chunk=load(path)
        for sku,sec in chunk["records"].items():
            result[sku]={"source":"native_sections","at":chunk["at"],"sections":sec,"status":"ok" if isinstance(sec,dict) else "source_error"}
    for path in sorted((folder/"pages").glob("*.json.gz")):
        item=load(path)
        result[item["sku"]]=item
    return result


def body_sections(fragment):
    """Only consume content that follows a named heading in the SKU's actual public description."""
    from lxml import etree
    from .extract import tree,txt
    node=tree(fragment)
    labels={
        "specification":"specification","specifications":"specification","technical specifications":"specification",
        "features":"product_feature_description","key features":"product_feature_description","feature":"product_feature_description",
        "application":"product_application_description","applications":"product_application_description",
        "documents":"documents","resources":"documents","resource":"documents","documentation":"documents"}
    result={}
    for heading in node.xpath(".//h1|.//h2|.//h3|.//h4|.//h5"):
        key=labels.get(txt(heading).strip(":").strip().casefold())
        if not key:continue
        chunks=[]
        for sib in heading.itersiblings():
            if sib.tag in ("h1","h2","h3","h4","h5") or sib.xpath(".//h1|.//h2|.//h3|.//h4|.//h5"):break
            chunks.append(etree.tostring(sib,encoding="unicode",method="html",with_tail=False))
        if chunks:result[key]="".join(chunks)
    return result


def reconcile_summary(folder,rows,old):
    live_urls=defaultdict(list);live_ids=defaultdict(list)
    for sku,row in rows.items():
        u=baseurl(row,old.get(sku,{}))
        live_urls[path_key(u)].append(sku)
        if public_pid(u) is not None:live_ids[public_pid(u)].append(sku)
    sitemap=load(folder/"sitemap.json.gz")
    urls=sitemap["urls"]
    path=folder/"reconciliation.json"
    audited=load(path) if path.exists() else {}
    inspected=audited.get("sources",{})
    if not inspected:
        for item in sorted(folder.glob("routes-*.json")):inspected.update(load(item))
    product_urls=[url for url in urls if public_pid(url) is not None]
    remaining=[]
    for url in urls:
        if path_key(url) in live_urls or re.search(r"-c-\d+\.html$",urlsplit(url).path,re.I):continue
        check=inspected.get(url,{"state":"unread"})
        entry={"url":url,"id":public_pid(url),**check}
        if entry["id"] in live_ids:entry["sameUrlIdCandidates"]=live_ids[entry["id"]]
        remaining.append(entry)
    legacy_candidates=[r for r in remaining if r["id"] is not None and r["id"] not in live_ids]
    previous_ids={public_pid(p.get("url","")) for p in old.values()}
    original=[{"url":url,"id":public_pid(url),**inspected.get(url,{"state":"unread"})}
              for url in product_urls if public_pid(url) not in previous_ids]
    return {"at":sitemap["at"],"urls":len(urls),"productUrls":len(product_urls),"productIds":len(set(map(public_pid,product_urls))),
            "matched":sum(path_key(url) in live_urls for url in product_urls),"exactCatalogUrlMatches":sum(path_key(url) in live_urls for url in urls),
            "unmatched":sum(path_key(url) not in live_urls for url in product_urls),
            "unmatchedProductIdCount":len({r["id"] for r in legacy_candidates}),
            "unmatchedCandidates":remaining,"legacyProductCandidates":legacy_candidates,
            "priorUnmatchedProductIdCount":len({r["id"] for r in original}),"priorUnmatchedProductCandidates":original,
            "secondaryCheckedAt":audited.get("checkedAt")}


def assemble(folder,baseline):
    from .storefront import normalized,extract_detail,unique,product_link_index
    from .extract import section_counts,column_defaults
    from .r1000_evidence import enrich_r1000
    from .updates import refresh_facts
    old={p["sku"]:p for p in baseline["products"]}
    rows,dates=staged_rows(folder);live_list=set(rows)
    extra=load(folder/"extras.json.gz") if (folder/"extras.json.gz").exists() else {}
    rows.update(extra.get("products",{}));dates.update({sku:extra["at"] for sku in extra.get("products",{})})
    eligible=load(folder/"eligibility.json");excluded=set(eligible["excluded"])
    members=defaultdict(list);cats=[]
    for c in load(folder/"categories.json"):
        cc=load(folder/f'category-{c["id"]}.json')
        cats.append({"name":c["name"],"id":c["id"],"url":STORE+c["url_path"]+".html","count":len(cc["members"]),"checkedAt":cc["at"]})
        for sku in cc["members"]:members[sku].append(c["name"])
    current_sections=read_sections(folder)
    url_index=product_link_index((sku,baseurl(r,old.get(sku,{}))) for sku,r in rows.items())
    by_sku={};statuses=Counter();field_counts=defaultdict(Counter);description_counts=Counter();body_count=Counter()
    status_skus=defaultdict(list)
    for sku in dict.fromkeys([*old,*rows]):
        prev=old.get(sku,{})
        if sku not in rows:
            by_sku[sku]={**prev,"catalogStatus":"retained_previous","detailAudit":{"state":"unread","fields":{k:"unread" for k in DETAIL_FIELDS}}}
            continue
        row=rows[sku];cur=normalized(row,prev);url=cur["url"]
        if not url and row.get("verifiedUrl"):cur["url"]=url=row["verifiedUrl"]
        cur.update(catalogStatus="live" if sku in live_list else "live_secondary",groups=members.get(sku,[]),
                   stockStatus=row.get("stock_status"),image=prev.get("image","") if cur["imageUrl"]==prev.get("imageUrl") else "",
                   storeRelations=[{"sku":a["sku"],"kind":kind,"source":url} for key,kind in
                      (("related_products","related"),("upsell_products","upsell"),("crosssell_products","crosssell"))
                      for a in (row.get(key) or []) if isinstance(a,dict) and a.get("sku") and a["sku"]!=sku])
        fragment=(row.get("description") or {}).get("html") or ""
        description=content_state(fragment);description_counts[description]+=1
        body=body_sections(fragment) if fragment else {}
        if body:
            extract_detail(cur,{k:v for k,v in body.items() if k!="specification"})
            cur["details"]=False
            for k in body:body_count[k]+=1
        item=current_sections.get(sku,{})
        sec=item.get("sections") if isinstance(item.get("sections"),dict) else {}
        fields={k:content_state(sec[k]) if k in sec else "unread" for k in DETAIL_FIELDS}
        add_status="previous_html" if prev.get("details") else "unread"
        addons=None
        if sku in excluded or item.get("status")=="excluded":status="excluded"
        elif item.get("status")=="source_error":status="source_error"
        elif item.get("status")=="ok":
            status="source_error" if any(v in ("unread","source_error") for v in fields.values()) else ("nonempty" if "present" in fields.values() else "empty")
            extract_detail(cur,{k:v for k,v in sec.items() if k not in DETAIL_FIELDS or fields[k]!="source_error"})
            if status=="source_error":cur["details"]=False
            if "addons" in sec:
                addons=sec["addons"];add_status="present" if addons else "empty"
        else:status="unread"
        if status in {"source_error","excluded"}:
            fields={k:status if v=="unread" else v for k,v in fields.items()}
        # Reading the description is separate from checking each dedicated product-page field.
        found=refresh_facts(prev,cur,addons,url_index)
        from .product_specs import install_description_specs
        install_description_specs(found,fragment)
        for key in ("storeFeatures","storeApplications"):
            if body and cur.get(key) and not found.get(key):found[key]=cur[key]
        found["detailAudit"]={"state":status,"fields":fields,"checkedAt":item.get("at"),"source":item.get("source"),
              "body":description,"bodySections":list(body),"bodyCheckedAt":dates.get(sku),"alsoAdd":add_status,
              "previousDetail":bool(prev.get("details"))}
        if row.get("sourceErrors"):found["catalogFieldErrors"]=row["sourceErrors"]
        if item.get("error"):found["detailAudit"]["error"]=item["error"]
        if sec:found["detailAudit"]["template"]=sec.get("_pageTemplate","magento")
        if item.get("identity"):found["detailAudit"]["identity"]=item["identity"]
        found["storePageStatus"]=("not_found" if item.get("error")=="STORE_HTTP_404" else
                 "verified" if item.get("status")=="ok" else status if status in {"excluded","source_error"} else "unread")
        statuses[status]+=1;status_skus[status].append(sku)
        for field,state in fields.items():field_counts[field][state]+=1
        by_sku[sku]=column_defaults(found)
    for product in by_sku.values():enrich_r1000(product,by_sku)
    urls=Counter(p.get("url") for p in by_sku.values() if p.get("url"))
    for p in by_sku.values():
        if urls[p.get("url")]>1:p["sharedUrl"]=True
        else:p.pop("sharedUrl",None)
    baseline["products"]=list(by_sku.values());baseline["categories"]=cats
    section_counts(baseline)
    for c in cats:
        records=[by_sku[sku] for sku in members if c["name"] in members[sku] and sku in by_sku]
        c["sections"]=sum(bool(p.get("details")) for p in records)
        counts=Counter(p["detailAudit"]["state"] for p in records)
        c["thisRunPages"]={key:counts[key] for key in ("nonempty","empty","source_error","excluded","unread")}
        c["thisRunPages"].update(checked=counts["nonempty"]+counts["empty"],eligible=len(records)-counts["excluded"])
    stats=baseline["stats"];products=baseline["products"]
    stats.update(total=len(products),menu=sum(bool(p.get("groups")) for p in products),prices=sum((p.get("price") or 0)>0 for p in products))
    for label,key in (("sections","details"),("images","image"),("officialImages","imageUrl"),("urls","url")):stats[label]=sum(bool(p.get(key)) for p in products)
    sm=reconcile_summary(folder,rows,old);stats["sitemap"]=sm["urls"]
    detail={key:statuses[key] for key in ("nonempty","empty","source_error","excluded","unread")}
    detail.update(checked=detail["nonempty"]+detail["empty"],eligible=len(rows)-detail["excluded"],all=len(rows))
    audit={"checkedAt":stamp(),"startedAt":load(folder/"run.json")["startedAt"],
           "sources":{"listing":STORE+"graphql","categories":STORE+"graphql","sitemap":STORE+"sitemap.xml","robots":STORE+"robots.txt"},
           "directory":{"previousSkuCount":len(old),"liveSkuCount":len(rows),"publicSearchSkuCount":len(live_list),
             "retainedPrevious":len(set(old)-set(rows)),"addedSkuCount":len(set(rows)-set(old)),"menuSkus":len(members),
             "menuOnly":sorted(set(members)-live_list),"body":dict(description_counts),"bodySections":dict(body_count),
             "secondaryPageStates":dict(Counter(by_sku[s].get("storePageStatus","unread") for s in set(rows)-live_list)),
             "storeLifecycle":dict(Counter(p["storeLifecycle"] for p in products if p.get("storeLifecycle")))},
           "detail":detail,"fields":{k:dict(v) for k,v in field_counts.items()},"sitemap":sm,"categories":cats}
    page_records = [entry for entry in current_sections.values() if entry.get("source") == "product_page"]
    page_times = sorted(entry["at"] for entry in page_records if entry.get("at"))
    listing_times = sorted(t for sku,t in dates.items() if sku in live_list and t)
    audit["sourceWindows"] = {
        "searchInventory": {"first": listing_times[0], "last": listing_times[-1]} if listing_times else None,
        "productPages": {"first": page_times[0], "last": page_times[-1]} if page_times else None,
        "sitemap": sm.get("at"),
    }
    audit["pageOutcomes"] = {
        "templates": dict(Counter(entry["sections"].get("_pageTemplate","magento") for entry in page_records if entry.get("status")=="ok")),
        "errors": dict(Counter(entry["error"] for entry in page_records if entry.get("error"))),
        "identityReasons": dict(Counter(entry["identity"]["reason"] for entry in page_records if entry.get("identity",{}).get("reason"))),
    }
    paper_lookup = folder / "paper-sku-lookup.json"
    if paper_lookup.is_file():
        audit["supplementarySkuLookup"] = load(paper_lookup)
    baseline["audit"]=audit
    save(folder/"audit.json",{**audit,"statusSkus":status_skus,"addedSkus":sorted(set(rows)-set(old)),"retainedSkus":sorted(set(old)-set(rows))})
    write(folder/"catalog.js",CATALOG_PREFIX.encode()+packed(baseline)+b";\n")
    print("Candidate",folder/"catalog.js",detail,audit["directory"],flush=True)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stage",type=Path,required=True)
    ap.add_argument("--assemble",action="store_true")
    ap.add_argument("--references",action="store_true")
    ap.add_argument("--reconcile",action="store_true")
    ap.add_argument("--pages",action="store_true")
    args=ap.parse_args()
    folder=args.stage.resolve()
    if folder.is_relative_to(ROOT):ap.error("Use a separate temporary stage outside the live project.")
    folder.mkdir(parents=True,exist_ok=True)
    source=(ROOT/"data/catalog.js").read_bytes()
    baseline=json.loads(source.decode("utf-8-sig").strip()[len(CATALOG_PREFIX):].rstrip(";"))
    digest=hashlib.sha256(source).hexdigest()
    run=folder/"run.json"
    if not run.exists():save(run,{"startedAt":stamp(),"baseDigest":digest})
    saved=folder/"initial-catalog.js.gz"
    if load(run)["baseDigest"]!=digest:
        if not saved.exists():ap.error("The catalogue changed and no verified stage baseline exists.")
        source=gzip.decompress(saved.read_bytes())
        if hashlib.sha256(source).hexdigest()!=load(run)["baseDigest"]:ap.error("Staged baseline digest mismatch.")
        baseline=json.loads(source.decode("utf-8-sig").strip()[len(CATALOG_PREFIX):].rstrip(";"))
    elif not saved.exists():write(saved,gzip.compress(source,compresslevel=3))
    if args.references:references(folder,baseline)
    elif args.pages:
        def update_stage():
            # Reopen the immutable source checkpoint for each publication. A long scan
            # can then pick up fixes to the offline parser without repeating any requests.
            for action in ("--references","--assemble"):
                subprocess.run([sys.executable,"-B","-m","backend.bulk_catalog","--stage",str(folder),action],cwd=ROOT,check=True)
        try:
            with worker_lock(folder):public_pages(folder,baseline,update_stage)
        except RateLimit as e:raise SystemExit("Public pages rate limited; resume after "+time.ctime(e.until)) from None
    elif args.reconcile:
        pause_file=folder/"route-retry.json"
        if pause_file.exists() and load(pause_file)["until"]>time.time():ap.error("Sitemap reconciliation is cooling down after rate limiting.")
        try:
            with worker_lock(folder):reconcile(folder,baseline)
        except RateLimit as e:
            save(pause_file,{"until":e.until})
            raise SystemExit("Retry after "+time.ctime(e.until)) from None
    elif args.assemble:assemble(folder,baseline)
    else:
        try:
            with worker_lock(folder):collect(folder,baseline)
        except RateLimit as e:raise SystemExit("Store rate limited. Resume after "+time.ctime(e.until)) from None


if __name__=="__main__":main()
