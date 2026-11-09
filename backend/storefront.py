"""Read the English public storefront into small normalized records. Never save source pages."""
import gzip
import hashlib
import io
import json
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit, urljoin, unquote, parse_qsl
from urllib.request import Request, build_opener, HTTPRedirectHandler

from .storage import Problem, jpeg, write
from .store_policy import Policy

STORE = "https://www.seeedstudio.com/"
PRODUCT_PAGE_BYTE_LIMIT = 32_000_000
ITEM_FIELDS = """id sku name url_key url_suffix small_image{url}
categories{name url_path breadcrumbs{category_name}}
price_range{minimum_price{final_price{value currency}} maximum_price{final_price{value currency}}}
short_description{html} description{html}"""
SALES_FIELDS=ITEM_FIELDS+" stock_status related_products{sku} upsell_products{sku} crosssell_products{sku}"
DETAIL_FIELDS=("product_feature_description","specification","hardware_overview","product_application_description",
               "documents","certification_info","certification_info_tech","certification_info_part","certification_info_eccn","faq_list")


def is_official(url):
    try:
        p=urlsplit(url)
        return p.scheme=="https" and (p.hostname=="seeedstudio.com" or (p.hostname or "").endswith(".seeedstudio.com")) and not p.username and not p.password and p.port in (443,None)
    except ValueError: return False


class RateLimit(Exception):
    def __init__(self, until):
        super().__init__("STORE_RATE_LIMIT")
        self.until=until


class DetailIdentity(Problem):
    def __init__(self,reason,values=(),key="displayedSkus"):
        super().__init__("DETAIL_SKU_NOT_VERIFIED",502)
        self.observed={"reason":reason}
        valid=sorted(v for v in values if isinstance(v,str) and re.fullmatch(r"[\w.-]{1,55}",v))
        if valid:self.observed[key]=valid[:5]


class OfficialRedirect(HTTPRedirectHandler):
    def __init__(self,allowed=is_official):
        self.allowed=allowed

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not self.allowed(newurl): raise Problem("UNEXPECTED_STORE_REDIRECT",502)
        return super().redirect_request(req,fp,code,msg,headers,newurl)


class OfficialStore:
    def __init__(self):
        self.policies={}
        self.requested={}
        self.opener=build_opener(OfficialRedirect(self.redirect_allowed))

    def redirect_allowed(self,url):
        p=urlsplit(url)
        return is_official(url) and ((p.path=="/robots.txt" and not p.query) or
                                    (p.hostname in self.policies and self.policies[p.hostname].allows(url)))

    def policy_for(self,url):
        if not is_official(url):raise Problem("INVALID_STORE_URL")
        host=urlsplit(url).hostname
        if host not in self.policies:
            try:raw=self.raw_get("https://"+host+"/robots.txt",200_000)
            except Problem as e:
                if e.code not in {"STORE_HTTP_404","STORE_HTTP_410"}:raise
                raw=""
            self.policies[host]=Policy(raw,host=host)
        return self.policies[host]

    def get(self,url,limit=10_000_000,post=None):
        policy=self.policy_for(url);host=urlsplit(url).hostname
        if not policy.allows(url):raise Problem("ROBOTS_EXCLUDED")
        time.sleep(max(0,self.requested.get(host,0)+policy.delay-time.monotonic()))
        self.requested[host]=time.monotonic()
        return self.raw_get(url,limit,post)

    def raw_get(self,url,limit=10_000_000,post=None):
        if not is_official(url):raise Problem("INVALID_STORE_URL")
        headers={"User-Agent":"SeeedCatalogLocal/2.0","Accept-Encoding":"gzip"}
        if post is not None:headers["Content-Type"]="application/json"
        request=Request(url,data=post,headers=headers)
        try:
            with self.opener.open(request,timeout=35) as res:
                self.response_url=res.geturl()
                source=gzip.GzipFile(fileobj=res) if res.headers.get("Content-Encoding")=="gzip" else res
                body=source.read(limit+1)
            if len(body)>limit:raise Problem("STORE_RESPONSE_TOO_LARGE",502)
            return body
        except HTTPError as exc:
            header=exc.headers.get("Retry-After")
            if exc.code==429 or (exc.code==503 and header):
                try:until=time.time()+max(1,int(header))
                except (TypeError,ValueError):
                    try:until=max(time.time()+1,parsedate_to_datetime(header).timestamp())
                    except (TypeError,AttributeError,ValueError):until=time.time()+120
                raise RateLimit(until) from None
            raise Problem("STORE_HTTP_"+str(exc.code),502) from None
        except (URLError,OSError,TimeoutError):raise Problem("STORE_UNREACHABLE",502) from None

    def graphql(self,query,variables=None):
        params=urlencode({"query":query,"variables":json.dumps(variables or {},separators=(",",":"))})
        try:result=json.loads(self.get(STORE+"graphql?"+params,24_000_000))
        except (ValueError,UnicodeError):raise Problem("STORE_API_CHANGED",502) from None
        if not result.get("data") or result.get("errors"):raise Problem("STORE_API_CHANGED",502)
        return result["data"]

    def public_result(self,query,variables=None):
        body=json.dumps({"query":query,"variables":variables or {}},separators=(",",":")).encode()
        raw=self.get(STORE+"graphql",24_000_000,post=body)
        try:result=json.loads(raw)
        except ValueError:raise Problem("STORE_API_CHANGED",502) from None
        if not isinstance(result.get("data"),dict):raise Problem("STORE_API_CHANGED",502)
        return result

    def public_query(self,query,variables=None,allow_partial=False):
        result=self.public_result(query,variables)
        if result.get("errors"):
            if not allow_partial:raise Problem("STORE_API_CHANGED",502)
            for error in result["errors"]:
                path=error.get("path") or []
                if not path:raise Problem("STORE_API_CHANGED",502)
                result["data"].pop(path[0],None)
        return result["data"]

    def section_batch(self,ids):
        # Same public field and POST method as the storefront's queryProductGraghql.
        ids=[int(i) for i in ids]
        if not ids or len(ids)>40 or any(i<=0 for i in ids):raise Problem("INVALID_LIST")
        query="query{"+ " ".join(f'p{i}:customProductAttributes(id:{i},attributeCodes:["certification_info_part"])' for i in ids)+"}"
        data=self.public_query(query)
        rows={}
        for i in ids:
            payload=data.get("p"+str(i))
            if not isinstance(payload,str):continue
            try:obj=json.loads(payload)
            except ValueError:continue
            if isinstance(obj,dict) and "certification_info_part" in obj:
                rows[i]=obj["certification_info_part"]
        return rows

    def categories(self):
        tree=self.graphql("{categoryList{id name children{id name url_path}}}")["categoryList"]
        return [{"name":c["name"],"id":str(c["id"]),"url":STORE+c["url_path"]+".html"} for c in tree[0]["children"]]

    def category_page(self, category_id, page):
        query="""query($id:String!,$page:Int!){products(filter:{category_id:{eq:$id}},pageSize:100,currentPage:$page){total_count page_info{total_pages} items{sku}}}"""
        data=self.graphql(query,{"id":category_id,"page":page})["products"]
        return [p["sku"] for p in data["items"]],data["total_count"],data["page_info"]["total_pages"]

    def listing(self, page, skus=None):
        args="search:\"\"" if skus is None else "filter:{sku:{in:$skus}}"
        variables={"page":page}
        more=""
        if skus is not None:
            more=",$skus:[String]!"
            variables["skus"]=skus
        query="query($page:Int!"+more+"){products("+args+",pageSize:100,currentPage:$page){total_count page_info{total_pages} items{"+SALES_FIELDS+"}}}"
        data=self.public_query(query,variables)["products"]
        return data["items"],data["total_count"],data["page_info"]["total_pages"]

    def route_product(self,url,sku):
        if not self.policy_for(url).allows(url):raise Problem("ROBOTS_EXCLUDED")
        query='query($path:String!){route(url:$path){... on ProductInterface{'+SALES_FIELDS+'}}}'
        result=self.public_result(query,{"path":urlsplit(url).path.lstrip("/")})
        row=result["data"].get("route")
        if not row or row.get("sku")!=sku or not row.get("name"):raise Problem("DETAIL_SKU_NOT_VERIFIED")
        row["sourceErrors"]=[e["path"][1:] for e in result.get("errors",[]) if (e.get("path") or [None])[0]=="route"]
        return row

    def detail(self, url, sku):
        body=self.get(url, PRODUCT_PAGE_BYTE_LIMIT)
        resolved=getattr(self,"response_url",url)
        try:record=self.detail_payload(body,sku)
        except DetailIdentity as e:
            if resolved!=url and is_official(resolved):e.observed["resolvedUrl"]=resolved.split("?",1)[0].split("#",1)[0]
            raise
        return record

    @staticmethod
    def detail_payload(content,sku):
        from .extract import html
        from lxml.etree import ParserError
        try:
            root=html.fromstring(content,parser=html.HTMLParser(encoding="utf-8"))
        except (ParserError,ValueError):
            raise Problem("DETAIL_LAYOUT_UNKNOWN",502) from None
        title=" ".join(root.xpath("string(//title)").split()).strip(".… ").casefold()
        if title in {"access denied","attention required! | cloudflare","just a moment"}:
            challenge=root.xpath('//script[contains(@src,"/cdn-cgi/challenge-platform/") or contains(text(),"cf_chl_opt")]|//*[@id="challenge-form"]')
            if challenge or title=="access denied":
                raise Problem("STORE_ACCESS_CHALLENGE",403)
        main='//*[contains(concat(" ",normalize-space(@class)," ")," sku-section ")]//*[@itemprop="sku"]'
        nodes=root.xpath(main) or root.xpath('//*[@itemprop="sku"]')
        payload=root.xpath('//input[starts-with(@id,"PRODUCT_DETAIL_")]/@value')
        if not payload and root.xpath('//script[contains(text(),"self.__next_f.push(")]'):
            from .served_product import embedded_sections
            return embedded_sections(root,sku)
        hints={str(n.get("content") or "".join(n.itertext())).strip() for n in nodes}
        if {v.casefold() for v in hints}!={sku.casefold()}:
            raise DetailIdentity("different_displayed_sku" if hints else "no_displayed_sku",hints)
        if not payload:raise Problem("DETAIL_LAYOUT_UNKNOWN")
        try: sections=json.loads(payload[0])
        except ValueError:raise Problem("DETAIL_LAYOUT_UNKNOWN") from None
        if not isinstance(sections,dict):raise Problem("DETAIL_LAYOUT_UNKNOWN")
        ids=set(root.xpath('//form[@id="product_addtocart_form"]//input[@name="product"]/@value'))
        if len(ids)>1:raise DetailIdentity("multiple_product_ids",ids,"displayedStoreIds")
        if ids:sections["_verifiedStoreId"]=ids.pop()
        sections["addons"]=[{"name":" ".join(a.itertext()).strip(),"url":a.get("href")} for a in root.xpath('//form[@id="mageplaza-fbt-form"]//li//a[@href]')]
        return sections

    @staticmethod
    def verify_entity_id(sections,expected):
        if expected and sections.get("_verifiedStoreId") and str(expected)!=str(sections["_verifiedStoreId"]):
            raise DetailIdentity("different_product_id",[str(sections["_verifiedStoreId"])],"displayedStoreIds")

    def main_image(self, url, root):
        data=jpeg(self.get(url,8_000_000),(600,450))
        name=hashlib.sha256(data).hexdigest()+".jpg"
        image="data/jpg/"+name
        if not (root/image).exists():write(root/image,data)
        return image


def unique(values, key):
    return list({value[key]:value for value in values if value.get(key)}.values())


def product_link_key(url,base=STORE):
    try:parsed=urlsplit(urljoin(base,url or ""))
    except (TypeError,ValueError):return ""
    if parsed.scheme not in {"http","https"} or parsed.netloc.casefold()!="www.seeedstudio.com":return ""
    if any(not k.startswith("utm_") for k,_ in parse_qsl(parsed.query,keep_blank_values=True)):return ""
    return unquote(parsed.path).rstrip("/").casefold()


def product_link_index(rows):
    index={}
    for sku,url in rows:
        if not url:continue
        key=product_link_key(url)
        if key:index[key]=sku if key not in index or index[key]==sku else None
    return index


def normalized(row, old):
    from .extract import tree,txt,section_parts,facts,links,norm,text_link,column_defaults,content_state,wiki_references,body_options,cross_listed_parts
    sku=row["sku"]
    key=(row.get("url_key") or "").strip()
    url=STORE+quote(key,safe="/%()_-.")+(row.get("url_suffix") or "") if key else old.get("url","")
    doc=tree((row.get("description") or {}).get("html"))
    short_doc=tree((row.get("short_description") or {}).get("html"))
    notes=facts(doc,url,row["name"]) if url else []
    for note in facts(short_doc,url,row["name"]) if url else []:
        note["location"]="short_description"
        if note["kind"]=="另购说明":
            words=note["text"].split()
            note["source"]=text_link(url," ".join(words[:6])," ".join(words[-5:])) if len(words)>12 else text_link(url,note["text"])
        if not any(entry["text"]==note["text"] for entry in notes):
            notes.append(note)
    primary=(row.get("small_image") or {}).get("url") or ""
    if not is_official(primary) or "placeholder" in primary.lower():primary=""
    prices=row.get("price_range") or {}
    low=(prices.get("minimum_price") or {}).get("final_price") or {}
    high=(prices.get("maximum_price") or {}).get("final_price") or {}
    refs=links(doc,url or STORE)
    part_rows=section_parts(doc,row["name"])
    cross_listed = cross_listed_parts(doc, part_rows, url)
    if cross_listed:
        adjusted = [(name, "" if name in cross_listed else qty) for name, qty in part_rows]
        part_rows = [list(row) for row in dict.fromkeys(adjusted)]
    part_sources={}
    for name,qty in part_rows:
        if not url:
            break
        label=name.split(" · ")[1] if " · " in name else name
        installed=re.fullmatch(r"(.+?)\s+(\(assembled\))", name, re.I)
        if installed and str(qty).isdigit():
            raw=re.search(re.escape(installed[1])+r"\s+[x×✕＊*]\s*"+str(qty)+r"\s*"+re.escape(installed[2]),txt(doc),re.I)
            if raw:
                label=raw[0]
        part_sources[name]=text_link(url,label[:60])
    record=column_defaults({"sku":sku,"storeId":int(row["id"]) if str(row.get("id","")).isdigit() else None,"name":norm(row["name"]),"url":url,"price":low.get("value"),"maxPrice":high.get("value"),
            "currency":low.get("currency"),"imageUrl":primary,
            "paths":[[b["category_name"] for b in c.get("breadcrumbs") or []]+[c["name"]] for c in (row.get("categories") or []) if c and c.get("name")],
            "summary":txt(short_doc)[:550],
            "parts":part_rows,"partSources":part_sources,
            "docs":[d for d in refs if re.search(r"\.pdf(?:$|[?#])",d["url"],re.I)],
            "notes":notes,
            "wikiLinks":wiki_references(refs),
            "details":False,"updated":datetime.now(timezone.utc).date().isoformat()})
    from .product_specs import install_description_specs
    install_description_specs(record,doc)
    record["bodyStatus"]=content_state((row.get("description") or {}).get("html")) if "description" in row else "unread"
    if record["bodyStatus"] in {"empty","present"}:record["_bodyOptions"]=body_options(doc,url)
    if cross_listed:record["_bodyCrossListed"]=cross_listed
    if "stock_status" in row:record["stockStatus"]=row["stock_status"]
    relation_keys=(("related_products","related"),("upsell_products","upsell"),("crosssell_products","crosssell"))
    if any(key in row for key,_ in relation_keys):
        record["storeRelations"]=[{"sku":r["sku"],"kind":kind,"source":url} for key,kind in relation_keys
                                  for r in row.get(key) or [] if r and r.get("sku") and r["sku"]!=sku]
    if "sourceErrors" in row:record["catalogFieldErrors"]=row["sourceErrors"]
    return record


def extract_detail(record, section):
    from .extract import tree,txt,links,facts,install_column,text_link,wiki_references
    from .product_specs import REFERENCE_HEADINGS,install_reference_sections
    if "_storeLifecycle" in section:
        record.update(storeLifecycle=section["_storeLifecycle"],lifecycleSource=record["url"] if section["_storeLifecycle"] else "")
    read=[key for key in REFERENCE_HEADINGS if key in section]
    if read:
        install_reference_sections(record,section)
        record["_readReferenceSections"]=list(dict.fromkeys([*record.get("_readReferenceSections",[]),*read]))
    if "certification_info_part" in section:install_column(record,section["certification_info_part"])
    if "specification" in section:
        from .product_specs import install_specification
        fallback={k:v for k,v in record.items() if k.startswith("spec")} if record.get("specLocation")=="description" else {}
        install_specification(record,section["specification"])
        if fallback and not (record.get("specTables") or record.get("specText")):record.update(fallback)
    for key in DETAIL_FIELDS:
        value=section.get(key)
        if key=="faq_list" or not isinstance(value,str) or not value.strip():continue
        node=tree(value);refs=links(node,record["url"])
        record["docs"].extend(r for r in refs if key=="documents" or re.search(r"\.pdf(?:$|[?#])",r["url"],re.I))
        record["wikiLinks"].extend(wiki_references(refs))
        record["notes"].extend(facts(node,record["url"],record.get("name","")))
        target={"product_feature_description":("storeFeatures",6),"product_application_description":("storeApplications",4)}.get(key)
        if target:
            items=node.xpath(".//li[not(.//li)]") or node.xpath(".//p[not(.//p or .//table)]")
            snippets=[txt(el) for el in items]
            record[target[0]]=list(dict.fromkeys(s for s in snippets if 4<=len(s)<=420))[:target[1]]
    for key,attr in (("product_feature_description","storeFeatures"),("product_application_description","storeApplications")):
        if key in section:record.setdefault(attr,[])
    record["docs"]=unique(record["docs"],"url")
    record["wikiLinks"]=unique(record["wikiLinks"],"url")
    record["notes"]=unique(record["notes"],"text")
    record["details"]=True
