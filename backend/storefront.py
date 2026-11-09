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
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

from .storage import Problem, jpeg, write

STORE = "https://www.seeedstudio.com/"
ITEM_FIELDS = """id sku name url_key url_suffix small_image{url}
categories{name url_path breadcrumbs{category_name}}
price_range{minimum_price{final_price{value currency}} maximum_price{final_price{value currency}}}
short_description{html} description{html}"""


def is_official(url):
    try:
        p=urlsplit(url)
        return p.scheme=="https" and (p.hostname=="seeedstudio.com" or (p.hostname or "").endswith(".seeedstudio.com")) and not p.username and not p.password and p.port in (443,None)
    except ValueError: return False


class RateLimit(Exception):
    def __init__(self, until):
        super().__init__("STORE_RATE_LIMIT")
        self.until=until


class OfficialRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not is_official(newurl): raise Problem("UNEXPECTED_STORE_REDIRECT",502)
        return super().redirect_request(req,fp,code,msg,headers,newurl)


class OfficialStore:
    def __init__(self):
        self.opener=build_opener(OfficialRedirect())

    def get(self,url,limit=10_000_000,post=None):
        if not is_official(url):raise Problem("INVALID_STORE_URL")
        headers={"User-Agent":"SeeedCatalogLocal/2.0","Accept-Encoding":"gzip"}
        if post is not None:headers["Content-Type"]="application/json"
        request=Request(url,data=post,headers=headers)
        try:
            with self.opener.open(request,timeout=35) as res:
                source=gzip.GzipFile(fileobj=res) if res.headers.get("Content-Encoding")=="gzip" else res
                body=source.read(limit+1)
            if len(body)>limit:raise Problem("STORE_RESPONSE_TOO_LARGE",502)
            return body
        except HTTPError as exc:
            if exc.code==429:
                header=exc.headers.get("Retry-After")
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

    def public_query(self,query,variables=None):
        body=json.dumps({"query":query,"variables":variables or {}},separators=(",",":")).encode()
        raw=self.get(STORE+"graphql",24_000_000,post=body)
        try:result=json.loads(raw)
        except ValueError:raise Problem("STORE_API_CHANGED",502) from None
        if result.get("errors") or not isinstance(result.get("data"),dict):raise Problem("STORE_API_CHANGED",502)
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
        query="query($page:Int!"+more+"){products("+args+",pageSize:100,currentPage:$page){total_count page_info{total_pages} items{"+ITEM_FIELDS+"}}}"
        data=self.graphql(query,variables)["products"]
        return data["items"],data["total_count"],data["page_info"]["total_pages"]

    def detail(self, url, sku):
        return self.detail_payload(self.get(url),sku)

    @staticmethod
    def detail_payload(content,sku):
        from .extract import html
        root=html.fromstring(content,parser=html.HTMLParser(encoding="utf-8"))
        hints=[s.strip().casefold() for s in root.xpath('//*[@itemprop="sku"]/@content|//*[@itemprop="sku"]/text()')]
        if sku.casefold() not in hints:raise Problem("DETAIL_SKU_NOT_VERIFIED")
        payload=root.xpath('//input[starts-with(@id,"PRODUCT_DETAIL_")]/@value')
        if not payload:raise Problem("DETAIL_LAYOUT_UNKNOWN")
        try: sections=json.loads(payload[0])
        except ValueError:raise Problem("DETAIL_LAYOUT_UNKNOWN") from None
        if not isinstance(sections,dict):raise Problem("DETAIL_LAYOUT_UNKNOWN")
        sections["addons"]=[{"name":" ".join(a.itertext()).strip(),"url":a.get("href")} for a in root.xpath('//form[@id="mageplaza-fbt-form"]//li//a[@href]')]
        return sections

    def main_image(self, url, root):
        data=jpeg(self.get(url,8_000_000),(600,450))
        name=hashlib.sha256(data).hexdigest()+".jpg"
        image="data/jpg/"+name
        if not (root/image).exists():write(root/image,data)
        return image


def unique(values, key):
    return list({value[key]:value for value in values if value.get(key)}.values())


def normalized(row, old):
    from .extract import tree,txt,section_parts,facts,links,norm,text_link,column_defaults
    sku=row["sku"]
    key=(row.get("url_key") or "").strip()
    url=STORE+quote(key,safe="/%()_-.")+(row.get("url_suffix") or "") if key else old.get("url","")
    doc=tree((row.get("description") or {}).get("html"))
    primary=(row.get("small_image") or {}).get("url") or ""
    if not is_official(primary) or "placeholder" in primary.lower():primary=""
    prices=row.get("price_range") or {}
    low=(prices.get("minimum_price") or {}).get("final_price") or {}
    high=(prices.get("maximum_price") or {}).get("final_price") or {}
    refs=links(doc,url or STORE)
    part_rows=section_parts(doc)
    return column_defaults({"sku":sku,"storeId":int(row["id"]) if str(row.get("id","")).isdigit() else None,"name":norm(row["name"]),"url":url,"price":low.get("value"),"maxPrice":high.get("value"),
            "currency":low.get("currency"),"imageUrl":primary,
            "paths":[[b["category_name"] for b in c.get("breadcrumbs") or []]+[c["name"]] for c in row.get("categories",[])],
            "summary":txt(tree((row.get("short_description") or {}).get("html")))[:550],
            "parts":part_rows,"partSources":{name:text_link(url,name[:60]) for name,_ in part_rows if url},
            "docs":[d for d in refs if re.search(r"\.pdf(?:$|[?#])",d["url"],re.I)],
            "notes":facts(doc,url) if url else [],
            "wikiLinks":[{"title":r["name"],"url":r["url"]} for r in refs if r["url"].startswith("https://wiki.seeedstudio.com/")],
            "details":False,"updated":datetime.now(timezone.utc).date().isoformat()})


def extract_detail(record, section):
    from .extract import tree,txt,links,facts,install_column,text_link
    if "certification_info_part" in section:install_column(record,section["certification_info_part"])
    if "specification" in section:
        record["specSource"]=text_link(record["url"],"Specification") if txt(tree(section["specification"])) else ""
    doc_links=links(tree(section.get("documents")),record["url"])
    record["docs"]=unique(record["docs"]+doc_links,"url")
    record["wikiLinks"]=unique(record["wikiLinks"]+[{"title":r["name"],"url":r["url"]} for r in doc_links if r["url"].startswith("https://wiki.seeedstudio.com/")],"url")
    for k in ("product_feature_description","specification"):
        record["notes"]+=facts(tree(section.get(k)),record["url"])
    record["notes"]=unique(record["notes"],"text")
    record["details"]=True
