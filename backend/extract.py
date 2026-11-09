"""Extract normalized parts and evidence from public storefront HTML held in memory."""
import re
from urllib.parse import quote, urljoin, urlparse
from datetime import date
from collections import Counter
from lxml import html

PACK_TITLE = re.compile(r"^(?:part[s]?\s*list|packing\s*list|package\s*(?:includes?|contents?|list)|what.s in the box|kit contents?|packing contents?)\s*[:：]?$",re.I)
QUANTITY = re.compile(r"^(?:[x×*]\s*)?(\d+)\s*(?:pcs?|pieces?|sets?|units?)?\.?$",re.I)
ATTRIBUTE_NAMES={"product type","categories","sensors","series","ram","storage","operating system","network"}
SPEC_NAMES={"cpu","memory","os support","size","max. resolution","usb","ethernet","ingress protection","power consumption","operating temperature"}
QTY_HEADER={"qty","q'ty","quantity","amount","count","number","number of pieces"}
NAME_HEADER={"name","product","part","item","description","product name","part name","parts name","component name","item name","item name / description","contents","item description","part list"}
COLUMN_QUANTITY=re.compile(r"^(?:[x×✕*]\s*)?\d{1,5}\s*(?:[x×]|pcs?\.?|pieces?|sheets?|packs?|sets?|pairs?|units?)?$",re.I)
LABELLED_QTY=re.compile(r"^(.+?)\s+(?:[x×✕*]\s*(\d{1,5})(?:\s*(?:pcs?\.?|pieces?|units?))?|(\d{1,5})\s*(?:pcs?\.?|pieces?|units?))\s*$",re.I)
QTY_FIRST=re.compile(r"^(\d{1,5})\s*[x×✕*]\s*(.+)$",re.I)


def text_link(url, start, end=""):
    if not url:return ""
    def word(s):return quote(s,safe="").replace("-","%2D")
    return url.split("#",1)[0]+"#:~:text="+word(start)+(","+word(end) if end else "")


def excluded_item(name):
    # "Adapter (cord not included)" still includes the adapter itself.
    base=re.sub(r"\([^()]*\)","",name)
    return bool(re.search(r"\b(?:optional|sold separately|not included|not supplied|not provided|additional purchase)\b",base,re.I)
        or re.search(r"\(\s*(?:optional|sold separately|not (?:included|supplied|provided))\b",name,re.I))


def table_grid(table):
    carried={}
    for tr in table.xpath(".//tr"):
        occupied={i:value for i,(value,_) in carried.items()}
        carried={i:(value,rows-1) for i,(value,rows) in carried.items() if rows>1}
        col=0
        for cell in tr.xpath("./th|./td"):
            while col in occupied:col+=1
            def span(axis):
                value=cell.get(axis,"1")
                return min(60,int(value)) if value.isdigit() and len(value)<4 and int(value)>0 else 1
            size=span("colspan")
            for offset in range(size):
                value=txt(cell) if offset==0 else ""
                occupied[col+offset]=value
                if span("rowspan")>1:carried[col+offset]=(value,span("rowspan")-1)
            col+=size
        yield [occupied.get(i,"") for i in range(max(occupied,default=-1)+1)]


def column_rows(fragment,url):
    """Interpret only the dedicated storefront Part List field; preserve text and uncertainty."""
    parts=[]; attrs=[]; unresolved=[]
    section_link=text_link(url,"Part List")
    result={"parts":parts,"attributes":attrs,"partSource":section_link,"attributeSource":section_link,
            "partStatus":"empty","attributeStatus":"empty","storePartStatus":"empty"}
    if fragment is None:return result
    if not isinstance(fragment,str):
        result.update(partStatus="unparsed",storePartStatus="unparsed",attributeStatus="unparsed")
        return result
    if not fragment.strip():return result
    root=tree(fragment)
    if not txt(root):
        if root.xpath(".//img|.//object|.//iframe"):result.update(partStatus="unparsed",storePartStatus="unparsed",attributeStatus="unparsed")
        return result
    def review(cells):
        cells=[norm(c) for c in cells]
        if any(cells) and cells not in unresolved:unresolved.append(cells)
    def add_part(name,qty):
        name=norm(name)
        if not name or len(name)>550:return False
        if excluded_item(name):return False
        if qty and COLUMN_QUANTITY.fullmatch(qty):
            count=re.search(r"\d+",qty)[0]
            name=re.sub(r"\s+[x×✕*]\s*"+count+r"$","",name,flags=re.I)
        if [name,qty] not in parts:parts.append([name,qty])
        return True
    def single(raw,allow_name=False):
        raw=norm(raw).strip("• ")
        if not raw or PACK_TITLE.fullmatch(raw) or raw.lower().strip(":") in {"item","qty","quantity","packing","in the box","note","notes"}:return True
        m=QTY_FIRST.fullmatch(raw)
        if m:return add_part(m[2],m[1])
        m=LABELLED_QTY.fullmatch(raw)
        if m:return add_part(m[1],m[2] or m[3])
        m=re.fullmatch(r"(.{2,300}?)\s*[×✕*]\s*(\d{1,4})",raw)
        if m:return add_part(m[1],m[2])
        return allow_name and len(raw)<=180 and not re.search(r"^(?:note\b|please\b|this \w+|we\b|additionally\b|purchased? (?:after|before))",raw,re.I) and add_part(raw,"")
    for tab in root.xpath(".//table[not(.//table)]"):
        heading=tab.xpath("preceding::*[self::h1 or self::h2 or self::h3 or self::h4][1]")
        contextual=tab.xpath("preceding::*[self::p or self::h1 or self::h2 or self::h3 or self::h4][not(ancestor::table) and normalize-space()][1]")
        qualifier=txt(contextual[0]) if contextual else ""
        if heading and re.search(r"\baccessories\b|\boptional\b",txt(heading[0]),re.I):qualifier=txt(heading[0])
        if re.search(r"purchased? (?:before|after)|\boptional\b|optional accessories",qualifier,re.I):
            for row in table_grid(tab):review([qualifier,*row])
            continue
        tr_nodes=tab.xpath(".//tr")
        rows=list(table_grid(tab))
        labels={cells[0].strip(":").casefold() for cells in rows if len(cells)==2}
        typed_attrs=len(labels & ATTRIBUTE_NAMES)>=2
        spec_table=len({c[0].casefold() for c in rows if c} & SPEC_NAMES)>=3
        name_col=qty_col=None
        spec_heading=""
        for tr,cells in zip(tr_nodes,rows):
            if not cells or not any(cells):continue
            tags=[cell.casefold().strip(". :") for cell in cells]
            if spec_table:
                values=[cell for cell in cells[1:] if cell]
                name=cells[0]
                if not values:
                    if spec_heading.casefold()=="certification" and "," in name:
                        values=[name];name=spec_heading
                    elif name.casefold() not in ATTRIBUTE_NAMES|SPEC_NAMES:
                        spec_heading=name
                        continue
                value=" / ".join(values)
                row={"name":name,"value":value,"source":text_link(url,name,value[:60])}
                if name and row not in attrs:attrs.append(row)
                continue
            if set(tags)&QTY_HEADER and (set(tags)&NAME_HEADER or len(cells)>1):
                qty_col=next(i for i,c in enumerate(tags) if c in QTY_HEADER)
                name_col=next((i for i,c in enumerate(tags) if c in NAME_HEADER),None)
                continue
            if len(cells)==2 and qty_col is None and (typed_attrs or (tags[0] in ATTRIBUTE_NAMES and not COLUMN_QUANTITY.fullmatch(cells[1]))) and cells[0] and len(cells[0])<130:
                if tags in (["attribute","value"],["parameter","value"],["item","value"]):continue
                row={"name":cells[0],"value":cells[1],"source":text_link(url,cells[0],cells[1][:60])}
                if row not in attrs:attrs.append(row)
                continue
            if name_col is not None and qty_col is not None and max(name_col,qty_col)<len(cells):
                if COLUMN_QUANTITY.fullmatch(cells[qty_col]) and add_part(cells[name_col],cells[qty_col]):continue
            if len(cells)==2:
                if COLUMN_QUANTITY.fullmatch(cells[1]) and add_part(cells[0],cells[1]):continue
                if COLUMN_QUANTITY.fullmatch(cells[0]) and add_part(cells[1],cells[0]):continue
                if cells[0] and not cells[1] and tr.xpath("./td[1][@class='name']") and add_part(cells[0],""):continue
            if len(cells)==3 and any(r.xpath("./td[1][@rowspan]") for r in tr_nodes) and COLUMN_QUANTITY.fullmatch(cells[-1]) and add_part(cells[1],cells[-1]):continue
            populated=[cell for cell in cells if cell]
            if len(populated)==1:
                lines=[txt(p) for p in tr.xpath("./td/p[normalize-space()]|./td/li[normalize-space()]")]
                if len(lines)>1:
                    for line in lines:
                        if not single(line):review([line])
                    continue
                if single(populated[0],allow_name=len(cells)==1 and len(rows)==1 and bool(qualifier and PACK_TITLE.fullmatch(qualifier))):continue
            review(cells)
    # Lists and paragraph-based contents occur in older pages. Do not traverse table cells again.
    for node in root.xpath(".//li[not(ancestor::table) and not(.//li)] | .//p[not(ancestor::table or ancestor::li or .//p)] | .//div[not(ancestor::table or ancestor::li) and not(div or p or table or ol or ul or h2 or h3)]"):
        if node.xpath("ancestor::*[contains(concat(' ',normalize-space(@class),' '),' tips ')]"):continue
        heading=node.xpath("preceding-sibling::*[self::h1 or self::h2 or self::h3 or self::h4][1]")
        if not single(txt(node),allow_name=node.tag=="li" or (node.tag=="p" and heading and PACK_TITLE.fullmatch(txt(heading[0])))):review([txt(node)])
    if not parts and not attrs and not unresolved:
        if not single(txt(root)):review([txt(root)])
    result["storePartStatus"]=result["partStatus"]="present" if parts else ("unparsed" if unresolved else "empty")
    result["attributeStatus"]="present" if attrs else ("unparsed" if unresolved else "empty")
    if unresolved:
        result.update(partUnparsedRows=len(unresolved),unclassifiedRows=unresolved,unclassifiedSource=section_link)
    return result


COLUMN_FIELDS=("parts","attributes","partStatus","storePartStatus","attributeStatus","partSource","attributeSource",
               "partSources","partScopes","partEvidenceScope","attributeChecked","unclassifiedRows","unclassifiedSource","partUnparsedRows")


def install_column(record, fragment):
    """Install a successfully read storefront field, preserving independently sourced packing."""
    url=record.get("url","")
    parsed=column_rows(fragment,url)
    sources=record.get("partSources",{})
    scopes=record.get("partScopes",{})
    old=record.get("parts") or []
    uncertain_items={norm(cell).casefold() for row in parsed.get("unclassifiedRows",[]) for cell in row}
    attr_labels={x["name"].casefold() for x in parsed["attributes"]}
    sourced={}
    retained=[]
    new_names={row[0].casefold() for row in parsed["parts"]}
    for name,qty in old:
        link=sources.get(name) or record.get("partSource") or text_link(url,name[:60])
        independent=(scopes.get(name)=="family" or (link and link.split("#")[0]!=url.split("#")[0])
            or (sources.get(name) and link!=text_link(url,"Part List") and "#:~:text=" in link))
        if name.casefold() in new_names or (parsed["parts"] and not independent):continue
        if not independent and (name.casefold() in uncertain_items|attr_labels or excluded_item(name)):continue
        if not independent and record.get("storePartStatus")=="present" and (not sources.get(name) or link==record.get("attributeSource")):continue
        retained.append([name,qty])
        if link:sourced[name]=link
    for field in COLUMN_FIELDS:record.pop(field,None)
    record.update(parsed,attributeChecked=date.today().isoformat())
    record["parts"].extend(retained)
    if sourced:record["partSources"]=sourced
    if any(scopes.get(n) for n,_ in retained):record["partScopes"]={n:scopes[n] for n,_ in retained if n in scopes}
    if record["parts"]:record["partStatus"]="present"


def column_defaults(record):
    record.setdefault("partStatus","present" if record.get("parts") else "unread")
    record.setdefault("storePartStatus","unread")
    record.setdefault("attributeStatus","unread")
    record.setdefault("attributes",[])
    return record


def section_counts(catalog):
    products=catalog["products"]
    stats=catalog["stats"]
    for key,field in (("parts","parts"),("attributes","attributes"),("unclassifiedProducts","unclassifiedRows")):
        stats[key]=sum(bool(p.get(field)) for p in products)
    for key,field in (("partRows","parts"),("attributeRows","attributes"),("unclassifiedRows","unclassifiedRows")):
        stats[key]=sum(len(p.get(field) or []) for p in products)
    for key in ("storePartStatus","attributeStatus"):
        stats[key+"Counts"]=dict(Counter(p.get(key,"unread") for p in products))
    stats["partChecked"]=len(products)-stats["storePartStatusCounts"].get("unread",0)
    stats["wikiFacts"]=sum(bool(p.get("wikiEvidence")) for p in products)
    stats["wikiLinked"]=sum(bool(p.get("wikiEvidence") or p.get("wikiLinks")) for p in products)
    stats["documents"]=sum(bool(p.get("docs")) for p in products)
    for category in catalog["categories"]:
        members=[p for p in products if category["name"] in p.get("groups",[])]
        category["parts"]=sum(bool(p.get("parts")) for p in members)
        category["attributes"]=sum(bool(p.get("attributes")) for p in members)

def norm(s):
    return " ".join((s or "").split())

def tree(fragment):
    return html.fragment_fromstring(fragment or "<div></div>",create_parent=True)

def txt(e):
    return norm(" ".join(e.itertext()))

def safe_url(url, base):
    url=urljoin(base,(url or "").strip())
    return url if urlparse(url).scheme in ("http","https") else ""

def as_pairs(el):
    pairs=[]
    for tr in el.xpath(".//tr"):
        cells=[txt(x) for x in tr.xpath("./td | ./th")]
        if len(cells)>=2 and cells[0] and len(cells[0])<300:
            if QUANTITY.fullmatch(cells[-1]):
                pairs.append([re.sub(r"\s+[x×]\s*\d+$","",cells[0],flags=re.I),cells[-1]])
            elif len(cells)==2 and QUANTITY.fullmatch(cells[0]) and cells[1]:
                pairs.append([cells[1],cells[0]])
    if not pairs:
        lines=el.xpath(".//li") or el.xpath(".//p[not(.//p)]")
        for e in lines:
            line=txt(e)
            if not line or len(line)>180 or PACK_TITLE.fullmatch(line):continue
            end=re.match(r"^(.+?)\s*[x×*]\s*(\d+)\s*(?:pcs?)?\.?$",line,re.I)
            start=re.match(r"^(\d+)\s*[x×*]\s*(.+)$",line,re.I)
            if end:pairs.append([norm(end[1]),end[2]])
            elif start:pairs.append([norm(start[2]),start[1]])
            elif e.tag=="li":pairs.append([line,""])
    return [list(x) for x in dict.fromkeys(tuple(x) for x in pairs) if not excluded_item(x[0]) and x[0].casefold() not in ATTRIBUTE_NAMES]

def section_parts(doc):
    # Only accept the first content block after a literal packing-list heading.
    for h in doc.xpath(".//h1|.//h2|.//h3|.//h4|.//h5|.//p|.//strong|.//b"):
        if not PACK_TITLE.fullmatch(txt(h)): continue
        at=h
        while at.getparent() is not None and at.getnext() is None:
            at=at.getparent()
        sibling=at.getnext()
        while sibling is not None and not txt(sibling):sibling=sibling.getnext()
        if sibling is None or sibling.tag in ("h1","h2","h3","h4","h5"):continue
        if sibling.tag=="p":
            rows=[]
            while sibling is not None and sibling.tag=="p":
                wrap=tree(html.tostring(sibling,encoding="unicode"))
                found=as_pairs(wrap)
                if not found:break
                rows.extend(found);sibling=sibling.getnext()
            if rows:return rows
        else:
            if sibling.xpath(".//h1|.//h2|.//h3"):continue
            rows=as_pairs(sibling)
            if rows:return rows
    return []

def links(doc,base):
    out={}
    for a in doc.xpath(".//a[@href]"):
        href=safe_url(a.get("href"),base)
        if href and href!=base:
            label=txt(a) or href.rsplit("/",1)[-1]
            out[href]={"name":label[:180],"url":href}
    return list(out.values())

def facts(fragment, source):
    notes=[]
    for el in fragment.xpath(".//li|.//p[not(ancestor::li or ancestor::tr)]|.//tr"):
        text=txt(el)
        if not text or len(text)>450:continue
        if re.search(r"(?:not included|sold separately|purchased separately|additional purchase|not (?:provided|supplied) with)",text,re.I):
            notes.append({"kind":"另购说明","text":text,"source":source})
        elif re.search(r"(?:customi[sz]ation (?:service|options?)|(?:logo|firmware|packag\w*) customi[sz]ation|customi[sz](?:e|able) (?:the logo|your own logo))",text,re.I):
            notes.append({"kind":"定制说明","text":text,"source":source})
    return list({n["text"]:n for n in notes}.values())
