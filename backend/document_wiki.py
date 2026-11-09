"""Extract scoped factual sections from an already checked-out official English Wiki."""
import argparse
import html as htmlmod
import json
import os
from pathlib import Path
import re
from urllib.parse import quote, urlsplit
from lxml import html
from .document_enrichment import ACC, EXCLUSION, CUSTOM, add_rows, canonical, compact, github_file, html_rows, kind, point_type, load_catalog, publisher_source, set_catalog_skus
from .storage import write as atomic_write
from .document_compatibility import wiki_facts

def plain(text):
    text=re.sub(r"!\[([^\]]*)\]\([^)]*\)",r"\1",text)
    text=re.sub(r"\[([^\]]+)\]\([^)]*\)",r"\1",text)
    text=re.sub(r"\[\]\([^)]*\)|\[?\(to Wiki\)\]?", "",text,flags=re.I)
    text=re.sub("<[^>]+>"," ",text)
    return compact(htmlmod.unescape(text).replace("**","").replace("`",""))


def parse_markdown(raw,url,source,parents,title):
    lines=raw.splitlines();code=False;front=bool(lines and lines[0].strip()=="---")
    sections={};rows=[];statements=[];resources={};sheets={};section_data=[];current_title=title
    table=[];table_lines=[];html_table=[];html_line=0
    def cite(line):return source+"#L"+str(line)
    def append(cells,role,line,heading,header=(),table_line=None):
        cells=[plain(c).strip("[] ") for c in cells]
        start=len(rows);add_rows(rows,cells,role,cite(line),header,bool(re.fullmatch(r"(?:optional )?accessories(?: list)?",heading,re.I)))
        for new in rows[start:]:
            new["heading"]=heading
            if table_line is not None:new["tableLine"]=table_line
            if role=="accessory" and table_line is None:
                published={canonical(v) for v in re.findall(r"""https?://www\.seeedstudio\.com/[^\s)'"><|]*?-p-\d+\.html""",lines[line-1],re.I)}
                if len(published)==1:new["linkedStoreUrl"]=published.pop()
    def flush_table(role,heading):
        if len(table)>=3 and all(re.fullmatch(r":?[-\s]+:?",x) for x in table[1]):
            for i,cells in enumerate(table[2:],2):append(cells,role,table_lines[i],heading,table[0])
        table.clear();table_lines.clear()
    for idx,line in enumerate(lines,1):
        text=line.strip()
        if front:
            if idx>1 and text=="---":front=False
            continue
        if re.match(r"^(```|~~~)",text):
            code=not code
            continue
        if code:continue
        for dest in re.findall(r"""https?://[^\s)'"><]+?\.(?:pdf|xlsx)(?:\?[^\s)'"><]+)?""",line,re.I):
            u=canonical(dest)
            if u and kind(u) in ("pdf","spreadsheet") and (publisher_source(u) or github_file(u)):
                (sheets if kind(u)=="spreadsheet" else resources)[u]=""
        role_and_name=next(((point_type(h),h) for _,h in sorted(sections.items(),reverse=True) if point_type(h)),("",""))
        role,heading=role_and_name
        m=re.match(r"^(#{1,6})\s+(.+)",text)
        if m:
            flush_table(role,heading)
            level=len(m[1]);sections={k:v for k,v in sections.items() if k<level}
            h=plain(m[2]).strip("# ").strip();sections[level]=h
            if level==1 and not current_title:current_title=h
            if point_type(h):section_data.append({"line":idx,"title":h[:160]})
            continue
        if role and (text.startswith("|") or ("|" in text and bool(table))):
            cells=[plain(x) for x in text.strip("|").split("|")]
            table.append(cells);table_lines.append(idx)
        elif table:flush_table(role,heading)
        if role and (html_table or re.search(r"<table\b",text,re.I)):
            if not html_table:html_line=idx
            html_table.append(line)
            if re.search(r"</table>",text,re.I):
                try:
                    item=html.fromstring("\n".join(html_table))
                    data=html_rows(item,with_lines=True)
                    if data:
                        for cells,relative_line in data[1:]:
                            append(cells,role,html_line+relative_line-1,heading,data[0][0],html_line)
                except (ValueError,TypeError):pass
                html_table.clear()
        item_marker=re.match(r"^(?:[*+-]|\d{1,2}[.)])\s+(.+)",text) if role=="inbox" else None
        if item_marker:
            label=item_marker[1]
            if item_marker[0][0].isdigit() and re.match(r"(?:connect|insert|plug|make|press|install|assemble|follow|use|ensure|check|download|click|prepare|refer|remove)\b",plain(label),re.I):
                continue
            bold=re.match(r"^\*\*(.+?)\*\*\s+(.+)",label)
            if bold:
                suffix=re.split(r"\b(?:Provides?|Enables?|Ensures?|Supports?|For|A tool|All required hardware)\b",bold[2],maxsplit=1,flags=re.I)
                label=bold[1]+(" "+suffix[0].strip() if len(suffix)>1 and re.fullmatch(r"(?:header|adapter|board|cable|screw|clip)",suffix[0].strip(),re.I) else "")
            append([plain(label)],role,idx,heading)
        value=plain(text)
        if 10<=len(value)<=350 and re.search(r"not included|does not include|sold separately|purchased separately|available customization options|our hardware engineering services include",value,re.I):
            statements.append({"text":value,"kind":"customization" if CUSTOM.search(value) else "exclusion","source":cite(idx)})
    if table:flush_table(role,heading)
    return {"kind":"wiki","status":"parsed" if rows or statements else "empty","title":current_title,"sections":section_data,"rows":rows,
            "statements":statements[:22],"linkedPdfs":resources,"linkedSheets":sheets,"url":url,"markdownSource":source,"purchaseSkus":sorted(parents),
            **wiki_facts(url,raw,source),"parserVersion":4}


def add_published_links(root,repository,revision,product_links,records):
    """Read an exact published English slug without inferring the article's product identity."""
    from .wiki_purchases import markdown_meta
    wanted={}
    for product in product_links:
        for entry in [*product.get("wikiLinks",[]),*product.get("docs",[])]:
            url=canonical(entry.get("url",""))
            if url and urlsplit(url).hostname=="wiki.seeedstudio.com" and kind(url)=="wiki" and url not in records:
                wanted.setdefault(url.rstrip("/"),set()).add(url)
    if not wanted:return
    matches={}
    for path in (root/"sites"/"en"/"docs").rglob("*.md"):
        if not path.resolve().is_relative_to(root):continue
        try:
            local=Path("\\\\?\\"+str(path)) if os.name=="nt" and not str(path).startswith("\\\\?\\") else path
            meta=markdown_meta(local.read_text(encoding="utf-8-sig"))
        except (UnicodeError,OSError):
            continue
        if meta and meta[1].rstrip("/") in wanted:
            matches.setdefault(meta[1].rstrip("/"),[]).append((local,path.relative_to(root),meta[0]))
    known={r["markdownSource"]:r for r in records.values() if r.get("markdownSource") and not r.get("serviceParagraphOnly")}
    for slug,items in matches.items():
        if len(items)!=1:continue
        local,relative,title=items[0]
        source=repository+"/blob/"+revision+"/"+quote(relative.as_posix(),safe="/")
        original=local.read_text(encoding="utf-8-sig")
        for url in wanted[slug]:
            same_article=known.get(source)
            if same_article and same_article.get("url","").rstrip("/")==slug:
                records[url]={**same_article,"publishedAlias":url}
                continue
            article=parse_markdown(original,url,source,[],title)
            article.update(linkOnly=True,sourceScopes=["link_only"])
            records[url]=article


def read_checkout(mapping,checkout,products=None,product_links=None):
    data=json.loads(mapping.read_text(encoding="utf-8-sig")); by_url={}
    for p in data["products"]:
        for w in p["wikiLinks"]:
            u=canonical(w["url"])
            info=by_url.setdefault(u,{"purchases":set(),"declared":set(),"title":w.get("title",""),"scopes":set(),"declaredCount":0})
            if w.get("relation")=="declared_sku":info["declared"].add(p["sku"])
            if w.get("relation") in (None,"purchase_link") or w.get("purchaseLink"):info["purchases"].add(p["sku"])
            if w.get("sourceScope"):info["scopes"].add(w["sourceScope"])
            info["declaredCount"]=max(info["declaredCount"],w.get("declaredSkuCount") or 0)
    records={};root=checkout.resolve();rev=data["revision"]
    for url,path in data["sourcePaths"].items():
        u=canonical(url);p=(root/path).resolve()
        if not p.is_relative_to(root) or u not in by_url:continue
        if os.name=="nt" and not str(p).startswith("\\\\?\\"):p=Path("\\\\?\\"+str(p))
        if not p.is_file():continue
        parent=by_url[u]
        source=data["repository"]+"/blob/"+rev+"/"+quote(Path(path).as_posix(),safe="/")
        raw=p.read_text(encoding="utf-8-sig")
        article=parse_markdown(raw,u,source,parent["purchases"],parent["title"])
        article["declaredSkus"]=sorted(parent["declared"])
        article["sourceScopes"]=sorted(parent["scopes"])
        # Parent mapping only contains known, model-matched SKU. An unindexed
        # variant in the actual front matter still makes this a shared page.
        header=raw.split("---",2)[1] if raw.startswith("---") and raw.count("---")>=2 else ""
        field=re.search(r"^sku[ \t]*:[ \t]*([^\r\n]*(?:\r?\n[ \t]+-[^\r\n]+)*)",header,re.I|re.M)
        if field:
            values=re.findall(r"(?<![A-Z0-9])(?:[1-9]\d{8}|[A-Z]\d{5,})(?![A-Z0-9])",field[1],re.I)
            article["declaresMultiple"]=max(len(set(values)),parent["declaredCount"])>1
        records[u]=article
    if products:
        from .document_family_services import annotate
        annotate(root,data["repository"],rev,products,records)
    if product_links:add_published_links(root,data["repository"],rev,product_links,records)
    return records


if __name__=="__main__":
    args=argparse.ArgumentParser(description=__doc__)
    args.add_argument("--mapping",type=Path,required=True);args.add_argument("--checkout",type=Path,required=True);args.add_argument("--output",type=Path,required=True)
    args.add_argument("--catalog",type=Path,default=Path("data/catalog.js"))
    args.add_argument("--product-links",type=Path,help="Optional exact product-page links; an article link alone never confers product identity.")
    a=args.parse_args()
    products={p["sku"]:p for p in load_catalog(a.catalog)["products"]}
    set_catalog_skus(products)
    links=json.loads(a.product_links.read_bytes())["products"] if a.product_links else []
    records=read_checkout(a.mapping,a.checkout,products,links)
    a.output.mkdir(parents=True,exist_ok=True)
    atomic_write(a.output/"wiki-offline-checks.json",json.dumps(records,ensure_ascii=False).encode("utf-8"))
    print("English articles",len(records),"with target candidates",sum(r["status"]=="parsed" for r in records.values()))
