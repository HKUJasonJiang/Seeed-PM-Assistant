"""Map Seeed's English Wiki purchase buttons to exact overseas product pages."""
import argparse
from collections import defaultdict
import html
import json
import os
from pathlib import Path
import re
from urllib.parse import quote, unquote, urlsplit

from .storage import CATALOG_PREFIX, packed, write


GITHUB = "https://github.com/Seeed-Studio/wiki-documents"
STORE_HOSTS = {"www.seeedstudio.com", "seeedstudio.com"}
STOP_WORDS = set("a an the for and model with by to at of from grove seeed studio board module kit hardware sensor pi raspberry series base accessory expansion development getting started guide using quick easy introduction manual arduino official".split())
BUTTON = re.compile(r"get[ _-]*one[ _-]*now|buy[ _-]*now",re.I)
ANCHOR = re.compile(r"<a\b[^>]{0,2000}?href\s*=\s*[\"']([^\"'<>]+)[\"'][^>]*>(.{0,2000}?)</a>",re.I|re.S)
MD_BUTTON = re.compile(r"\[(?:!\[[^\]]*\]\(([^)]+)\)|([^\]\n]+))\]\((https?://[^)\s]+)\)",re.I)
SECTION = re.compile(r"(?im)^#{1,4}\s+(?:hardware (?:preparations?|requirements?|connections?)|what you need|materials required|prerequisites?|software|examples?|step\s+1|applications?|usage|documents?|resources?)\b")


def source_key(url):
    try:
        u=urlsplit(html.unescape(url))
        if u.scheme not in {"https","http"} or u.hostname not in STORE_HOSTS or u.username or u.password or u.port: return ""
        path=unquote(u.path).rstrip("/")
        return path.casefold() if re.search(r"-p-\d+\.html$",path,re.I) else ""
    except ValueError:
        return ""


def words(s):
    return set(re.findall(r"[a-z0-9]+",s.casefold()))-STOP_WORDS


PRODUCT_ROLES={
    "hat":r"\b(?:base[ _-]?)?hat\b","antenna":r"\bantenna\b","enclosure":r"\b(?:enclosure|case)\b",
    "cable":r"\b(?:cable|cord)\b","carrier":r"\bcarrier[ -]?board\b","shield":r"\bshield\b",
    "mount":r"\b(?:mounting[ -]?bracket|mount[ -]?kit)\b","heat sink":r"\bheat[ -]?sink\b",
}


def same_item_role(title,name):
    # A guide for a HAT may explicitly list the gateway module it accepts.
    # Keep a positive purchase/metadata result only for the primary item.
    role=lambda text:{key for key,pat in PRODUCT_ROLES.items() if re.search(pat,re.split(r"\s+for\s+|,",text,1,flags=re.I)[0],re.I)}
    return role(title)==role(name)


def markdown_meta(doc):
    meta=re.match(r"\A\ufeff?---\s*\r?\n(.+?)\r?\n---\s*(?:\r?\n|$)",doc,re.S)
    if not meta:return None
    values={}
    for key in ("slug","title"):
        item=re.search("^"+key+r":[ \t]*(.+?)\s*$",meta[1],re.M)
        if not item:return None
        values[key]=item[1].strip().strip("\"'")
    slug=values["slug"]
    if not slug.startswith("/") or "//" in slug or ".." in slug or re.search(r"[\s?#<>{}\\]",slug):return None
    return html.unescape(values["title"]),"https://wiki.seeedstudio.com/"+quote(slug.strip("/"),safe="/-_~.()")+"/",doc[meta.end():]


def primary_purchases(text):
    body=text[:16000]
    boundary=SECTION.search(body)
    if boundary:body=body[:boundary.start()]
    found=set()
    for match in ANCHOR.finditer(body):
        if BUTTON.search(match.group(0)):
            found.add(source_key(match[1]))
    for match in MD_BUTTON.finditer(body):
        if BUTTON.search(match[1] or match[2] or ""):
            found.add(source_key(match[3]))
    return found-{""}


def matches_model(title,product_name):
    if not same_item_role(title,product_name):return False
    a,b=words(title),words(product_name)
    shared=a&b
    if not a or not b or not shared:return False
    model_ids={w for w in a if re.search(r"\d",w) and re.search("[a-z]",w)}
    if model_ids and not model_ids<=b:return False
    return (len(shared)>=2 and (len(shared)/len(a)>=0.55 or len(shared)/len(b)>=0.85)) or bool(model_ids & shared)


def declared_skus(doc):
    front=re.match(r"\A\ufeff?---\s*\r?\n(.+?)\r?\n---\s*(?:\r?\n|$)",doc,re.S)
    if not front:return set(),None
    field=re.search(r"^(?:sku|skus):[ \t]*(.*)$",front[1],re.M|re.I)
    if not field:return set(),None
    value=field[1].partition("#")[0]
    if not value.strip():
        items=re.match(r"(?:\r?\n[ \t]*-[ \t]+[^\r\n]+)+",front[1][field.end():])
        value=items[0] if items else ""
    skus={item for item in re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]*",value) if any(c.isdigit() for c in item)}
    line=doc[:front.start(1)+field.start()].count("\n")+1
    return skus,line


def same_declared_product(title,name):
    if not same_item_role(title,name):return False
    if matches_model(title,name):return True
    normalize=lambda s:" ".join(re.findall(r"[a-z0-9]+",s.casefold()))
    a,b=normalize(title),normalize(name)
    if not a or not b or not (words(title)&words(name)):return False
    a=re.sub(r"^(?:getting started with|getting started|introduction to) ","",a)
    version=lambda s:re.search(r"\bv(?:er(?:sion)?)?\s*\d+(?:\s+\d+)?\b",s)
    title_version,name_version=version(a),version(b)
    if title_version and name_version and title_version[0]!=name_version[0]:return False
    if title_version and not name_version:a=(a[:title_version.start()]+a[title_version.end():]).strip()
    return len(a.split())>=2 and (" "+a+" " in " "+b+" " or len(b.split())>=2 and " "+b+" " in " "+a+" ")


def documented_component(doc,title,name):
    """A single declared SKU and explicit model/role in the editor's description."""
    meta=re.match(r"\A\ufeff?---\s*\r?\n(.+?)\r?\n---",doc,re.S)
    line=re.search(r"^description:[ \t]+([^\r\n]+)",meta[1],re.M) if meta else None
    if not line:return False
    lead=re.split(r"[.!?](?:\s|$)",html.unescape(line[1]),1)[0]
    head=re.split(r"\s+for\s+|,",name,1,flags=re.I)[0]
    models={w for w in words(head)&words(title)&words(lead) if len(w)>=4 and re.search(r"\d",w) and re.search("[a-z]",w)}
    return bool(models) and any(re.search(pattern,head,re.I) and re.search(pattern,lead,re.I) for pattern in PRODUCT_ROLES.values()) and same_item_role(lead,head)


def application_guide(relative,title):
    return bool(re.search(r"/(?:applications?|tutorials?|projects?|examples?)/",relative,re.I)
                or re.match(r"how to\b|(?:resolve|implement|build|deploy|run|integrate|flash)\b",title,re.I)
                or re.search(r"\b(?:training guide|tutorial|teleoperation|teleop)\b",title,re.I))


def scan(catalog,checkout,revision):
    if not re.fullmatch(r"[a-f\d]{40}",revision):
        raise ValueError("A full official Git revision is required")
    paths=defaultdict(list)
    by_sku={p["sku"]:p for p in catalog["products"]}
    for product in catalog["products"]:
        key=source_key(product.get("url") or "")
        if key:paths[key].append(product)
    checkout=Path(checkout).resolve()
    if os.name=="nt" and not str(checkout).startswith("\\\\?\\"):
        checkout=Path("\\\\?\\"+str(checkout))
    docs=checkout/"sites/en/docs"
    files=sorted([*docs.rglob("*.md"),*docs.rglob("*.mdx")])
    refs=defaultdict(dict); index={}; unread=[]; slug_counts=defaultdict(int); source_rows=[]
    declared_pages=0
    for file in files:
        relative=file.relative_to(checkout).as_posix()
        try:text=file.read_text(encoding="utf-8-sig")
        except (OSError,UnicodeError):
            unread.append(relative);continue
        meta=markdown_meta(text)
        if not meta:continue
        title,wiki,body=meta
        slug_counts[wiki]+=1
        related={}
        button_keys=primary_purchases(body)
        for key in button_keys:
            targets=paths[key]
            if len(targets)!=1 or not matches_model(title,targets[0]["name"]):continue
            product=targets[0]
            related[product["sku"]]={"relation":"purchase_link","purchaseLink":True}
        declared,line=declared_skus(text)
        declared_pages+=bool(declared)
        for sku in sorted(declared&by_sku.keys()):
            matched=same_declared_product(title,by_sku[sku]["name"])
            component=not matched and len(declared)==1 and documented_component(text,title,by_sku[sku]["name"])
            if matched or component:
                relation=related.setdefault(sku,{})
                relation.update(relation="declared_sku",declaredSku=True,metadataLine=line)
                if component:relation["sourceScope"]="component_guide"
        application=application_guide(relative,title)
        multiple=len(declared)>1 or len(button_keys)>1
        for sku,relation in related.items():
            relation.setdefault("sourceScope","application" if application else "multi_sku" if multiple else "product")
            relation["declaredSkuCount"]=len(declared)
            source_rows.append((wiki,relative,sku,title,relation))
    for wiki,relative,sku,title,relation in source_rows:
        if slug_counts[wiki]!=1:continue
        source=GITHUB+"/blob/"+revision+"/"+quote(relative,safe="/-_.~")
        refs[sku][wiki]={"title":title,"url":wiki,**relation,"source":source}
        index[wiki]=relative
    items=[(sku,w) for sku,group in refs.items() for w in group.values()]
    return {"revision":revision,"repository":GITHUB,"files":len(files),"read":len(files)-len(unread),"unread":unread,
        "pages":len(index),"matchedSkus":len(refs),"sourcePaths":index,"declaredPages":declared_pages,
        "purchasePages":len({w["url"] for _,w in items if w.get("purchaseLink")}),"purchaseSkus":len({sku for sku,w in items if w.get("purchaseLink")}),
        "verifiedDeclaredPages":len({w["url"] for _,w in items if w.get("declaredSku")}),"verifiedDeclaredSkus":len({sku for sku,w in items if w.get("declaredSku")}),
        "products":[{"sku":s,"wikiLinks":list(links.values())} for s,links in sorted(refs.items())]}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--catalog",type=Path,required=True);ap.add_argument("--checkout",type=Path,required=True)
    ap.add_argument("--revision",required=True);ap.add_argument("--output",required=True,type=Path)
    args=ap.parse_args()
    data=json.loads(args.catalog.read_text(encoding="utf-8-sig").strip()[len(CATALOG_PREFIX):].rstrip(";"))
    result=scan(data,args.checkout,args.revision)
    write(args.output,packed(result))
    print("English source files",result["files"],"read",result["read"],"matched Wiki pages",result["pages"],"matched SKUs",result["matchedSkus"])


if __name__=="__main__":main()
