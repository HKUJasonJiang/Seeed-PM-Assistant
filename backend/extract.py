"""Extract normalized parts and evidence from public storefront HTML held in memory."""
import re
from html import unescape
from copy import deepcopy
from urllib.parse import quote, urljoin, urlparse, urlsplit, urlunsplit, unquote
from datetime import date
from collections import Counter
from lxml import html

PACK_TITLE = re.compile(r"^(?:part[s]?\s*list|packing\s*list|package\s*(?:includes?|contents?|list)|what.s in the box|kit contents?|packing contents?)\s*[:：]?$",re.I)
QUANTITY = re.compile(r"^(?:[x×*]\s*)?(\d+)\s*(?:pcs?|pieces?|sets?|units?)?\.?$",re.I)
ATTRIBUTE_NAMES={"product type","categories","sensors","series","ram","storage","operating system","network"}
SPEC_NAMES={"cpu","memory","os support","size","max. resolution","usb","ethernet","ingress protection","power consumption","operating temperature"}
QTY_HEADER={"qty","q'ty","quantity","amount","count","number","number of pieces"}
NAME_HEADER={"name","product","part","item","items","module","description","product name","part name","parts name","component name","item name","item name / description","contents","item description","part list"}
COLUMN_QUANTITY=re.compile(r"^(?:[x×✕*＊]\s*)?\d{1,5}\s*(?:[x×✕*＊]|pcs?\.?|pieces?|sheets?|packs?|sets?|pairs?|units?)?$",re.I)
LABELLED_QTY=re.compile(r"^(.+?)\s+(?:[x×✕*]\s*(\d{1,5})(?:\s*(?:pcs?\.?|pieces?|units?))?|(\d{1,5})\s*(?:pcs?\.?|pieces?|units?))\s*$",re.I)
QTY_FIRST=re.compile(r"^(\d{1,5})\s*[x×✕*]\s*(.+)$",re.I)
PREFIX_COUNT=re.compile(r"^(?:[x×✕＊*]\s*|X\s+)(\d{1,5})\s+(.+)$")
EXCLUSION=re.compile(r"(?:not included|sold separately|(?:purchased|bought|ordered) separately|additional purchase|not (?:provided|supplied) with|(?:does not|doesn['‘’`]?t|do not|don['‘’`]?t) (?:come with|include))",re.I)


def text_link(url, start, end=""):
    if not url:return ""
    def word(s):return quote(s,safe="").replace("-","%2D")
    return url.split("#",1)[0]+"#:~:text="+word(start)+(","+word(end) if end else "")


def excluded_item(name):
    # "Adapter (cord not included)" still includes the adapter itself.
    base=re.sub(r"\([^()]*\)","",name)
    return bool(EXCLUSION.search(base) or re.search(r"\b(?:optional|not supplied|not provided)\b",base,re.I)
        or re.search(r"\(\s*(?:optional|sold separately|not (?:included|supplied|provided))\b",name,re.I))


def valid_part_name(value):
    return bool(norm(value)) and not re.fullmatch(r"(?:\d{1,2}|[\s./—–_-]+|n\s*/?\s*a|none|null|not applicable)",norm(value),re.I)

def metric_fastener(name):
    return bool(re.search(r"\bM\d+(?:\.\d+)?$",name,re.I))


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
        if not valid_part_name(name) or len(name)>550:return False
        if excluded_item(name):return False
        if qty and COLUMN_QUANTITY.fullmatch(qty):
            count=re.search(r"\d+",qty)[0]
            name=re.sub(r"\s+[x×✕*]\s*"+count+r"$","",name,flags=re.I)
        if [name,qty] not in parts:parts.append([name,qty])
        return True
    def single(raw,allow_name=False):
        raw=norm(raw).strip("• ")
        if not raw or PACK_TITLE.fullmatch(raw) or raw.lower().strip(":") in {"item","qty","quantity","packing","in the box","note","notes"}:return True
        m=QTY_FIRST.fullmatch(raw) or PREFIX_COUNT.fullmatch(raw)
        if m:return add_part(m[2],m[1])
        if re.search(r"\(assembled\)$",raw,re.I):
            qualified=explicit_body_line(raw)
            if qualified:return add_part(*qualified)
        m=LABELLED_QTY.fullmatch(raw)
        if m and not metric_fastener(m[1]):return add_part(m[1],m[2] or m[3])
        m=re.fullmatch(r"(.{2,300}?)\s*[×✕*]\s*(\d{1,4})",raw)
        if m and not metric_fastener(m[1]):return add_part(m[1],m[2])
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
        variant_cols=[]
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
                variant_cols=[i for i,c in enumerate(tags) if i!=name_col and c in
                              {"specification","specifications","spec","model","model number","part number","description","specification / note"}]
                continue
            if len(cells)==2 and qty_col is None and (typed_attrs or (tags[0] in ATTRIBUTE_NAMES and not COLUMN_QUANTITY.fullmatch(cells[1]))) and cells[0] and len(cells[0])<130:
                if tags in (["attribute","value"],["parameter","value"],["item","value"]):continue
                row={"name":cells[0],"value":cells[1],"source":text_link(url,cells[0],cells[1][:60])}
                if row not in attrs:attrs.append(row)
                continue
            if name_col is not None and qty_col is not None and max(name_col,qty_col)<len(cells):
                if COLUMN_QUANTITY.fullmatch(cells[qty_col]):
                    values=[cells[i] for i in [name_col,*variant_cols] if i<len(cells) and valid_part_name(cells[i])]
                    if values and add_part(" · ".join(dict.fromkeys(values)),cells[qty_col]):continue
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
        for line in packing_lines(node):
            if not single(line,allow_name=node.tag=="li" or (node.tag=="p" and heading and PACK_TITLE.fullmatch(txt(heading[0])))):review([line])
    if not parts and not attrs and not unresolved:
        if not single(txt(root)):review([txt(root)])
    result["storePartStatus"]=result["partStatus"]="present" if parts else ("unparsed" if unresolved else "empty")
    result["attributeStatus"]="present" if attrs else ("unparsed" if unresolved else "empty")
    if unresolved:
        result.update(partUnparsedRows=len(unresolved),unclassifiedRows=unresolved,unclassifiedSource=section_link)
    return result


COLUMN_FIELDS=("parts","attributes","partStatus","storePartStatus","attributeStatus","partSource","attributeSource",
               "partSources","partScopes","partEvidenceScope","partQuantityConflicts","attributeChecked","unclassifiedRows","unclassifiedSource","partUnparsedRows")


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
    new_parts={name.casefold():(name,qty) for name,qty in parsed["parts"]}
    conflicts={}
    for name,qty in old:
        if not valid_part_name(name):continue
        link=sources.get(name) or record.get("partSource") or text_link(url,name[:60])
        independent=(scopes.get(name)=="family" or (link and link.split("#")[0]!=url.split("#")[0])
            or (sources.get(name) and link!=text_link(url,"Part List") and "#:~:text=" in link))
        same=new_parts.get(name.casefold())
        if same and independent and COLUMN_QUANTITY.fullmatch(str(qty)) and COLUMN_QUANTITY.fullmatch(str(same[1])):
            if re.findall(r"\d+",str(qty))!=re.findall(r"\d+",str(same[1])):
                conflicts[same[0]]=[{"quantity":same[1],"source":parsed["partSource"],"scope":"store_part_list"},
                                    {"quantity":qty,"source":link,"scope":scopes.get(name) or "description"}]
        if name.casefold() in new_names or (parsed["parts"] and not independent):continue
        if not independent and (name.casefold() in uncertain_items|attr_labels or excluded_item(name)):continue
        if not independent and record.get("storePartStatus")=="present" and (not sources.get(name) or link==record.get("attributeSource")):continue
        retained.append([name,qty])
        if link:sourced[name]=link
    for field in COLUMN_FIELDS:record.pop(field,None)
    record.update(parsed,attributeChecked=date.today().isoformat())
    record["parts"].extend(retained)
    if sourced:record["partSources"]=sourced
    if conflicts:record["partQuantityConflicts"]=conflicts
    if any(scopes.get(n) for n,_ in retained):record["partScopes"]={n:scopes[n] for n,_ in retained if n in scopes}
    if record["parts"]:record["partStatus"]="present"


def column_defaults(record):
    record.setdefault("partStatus","present" if record.get("parts") else "unread")
    record.setdefault("storePartStatus","unread")
    record.setdefault("attributeStatus","unread")
    record.setdefault("attributes",[])
    return record

def merge_part_purposes(record,fresh_body=False):
    """Fold a second description of the same, equally counted item into its named line."""
    rows=record.get("parts",[])
    names={norm(name).casefold():(name,qty) for name,qty in rows}
    refs=record.get("partSources",{})
    url=record.get("url","").split("#",1)[0]
    descriptions={name:entry for name,entry in record.get("partDescriptions",{}).items() if name.casefold() in names
                  and (entry.get("kind") in {"alias","configuration"} or not fresh_body or (entry.get("source") or "").split("#",1)[0]!=url)}
    remove=set()
    for name,qty in rows:
        match=re.fullmatch(r"(.+?)\s+to\s+(?:recognize|recognise|record|play|detect|emit|use|make|measure|monitor|control)\b.{2,}",name,re.I)
        if not match:continue
        shorter=names.get(norm(match[1]).casefold())
        if not shorter:continue
        qty=norm(str(qty or ""));old_qty=norm(str(shorter[1] or ""))
        if qty!=old_qty and not (COLUMN_QUANTITY.fullmatch(qty) and COLUMN_QUANTITY.fullmatch(old_qty)
                                  and re.findall(r"\d+",qty)==re.findall(r"\d+",old_qty)):continue
        source=refs.get(name) or record.get("partSource") or url
        if not source:continue
        descriptions[shorter[0]]={"text":name,"source":source}
        remove.add(name)
    if remove:
        record["parts"]=[row for row in rows if row[0] not in remove]
        for field in ("partSources","partScopes"):
            if field in record:record[field]={n:v for n,v in record[field].items() if n not in remove}
    if descriptions:record["partDescriptions"]=descriptions
    else:record.pop("partDescriptions",None)


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

def content_state(value):
    if value is None:return "empty"
    if isinstance(value,(list,dict)):return "present" if value else "empty"
    if not isinstance(value,str):return "source_error"
    node=tree(value)
    for hidden in node.xpath(".//style|.//script|.//template"):hidden.drop_tree()
    return "present" if txt(node) or node.xpath(".//img[@src]|.//a[@href]|.//iframe[@src]") else "empty"

def safe_url(url, base):
    try:
        url=urljoin(base,(url or "").strip())
        return (wiki_url(url) or url) if urlparse(url).scheme in ("http","https") else ""
    except (AttributeError,ValueError):return ""

def wiki_url(url):
    try:
        parsed=urlsplit(url or "")
        if (parsed.scheme not in {"http","https"} or parsed.hostname!="wiki.seeedstudio.com" or parsed.username is not None
                or parsed.password is not None or parsed.port not in {None,443 if parsed.scheme=="https" else 80}):return ""
    except ValueError:return ""
    return urlunsplit(("https","wiki.seeedstudio.com",parsed.path or "/",parsed.query,parsed.fragment))

def link_title(url):
    parsed=urlsplit(url)
    name=unquote(parsed.path.rstrip("/").rsplit("/",1)[-1]).replace("_"," ").strip()
    return name or parsed.hostname or url

def wiki_references(refs):
    result={}
    for ref in refs:
        url=wiki_url(ref.get("url"))
        if url:result[url]={"title":ref.get("name") or ref.get("title") or link_title(url),"url":url}
    return list(result.values())

def explicit_body_line(raw):
    text=unescape(norm(raw)).lstrip("•-– ")
    match=re.fullmatch(r"(\d{1,5})\s*[x×✕＊*]\s*(.+)",text,re.I) or PREFIX_COUNT.fullmatch(text)
    if match:return [norm(match[2]),match[1]]
    installed = re.fullmatch(r"(.+?)\s+[x×✕＊*]\s*(\d{1,5})\s*(\(assembled\))", text, re.I)
    if installed:
        return [norm(installed[1])+" "+installed[3], installed[2]]
    match=re.fullmatch(r"(.+?)(?:\s+[xX]|\s*[×✕＊*])\s*(\d{1,5})(?:\s*(?:pcs?|pieces?))?\.?",text)
    if match and not metric_fastener(norm(match[1])):return [norm(match[1]),match[2]]
    match=re.fullmatch(r".+?\s+[x×]\s+(\d{1,4})\s+(?:with|including)\s+.+",text,re.I)
    if match:return [text,match[1]]
    return None


def packing_lines(node):
    # A <br> in a wrapped product name is not a new item. Accept a hard break
    # only when each resulting line already contains a complete item and count.
    if not node.xpath(".//br"):
        return [txt(node)]
    lines, words = [], []
    for token in node.xpath(".//text() | .//br"):
        if isinstance(token, str):
            words.append(token)
        else:
            lines.append(norm(" ".join(words)))
            words = []
    lines.append(norm(" ".join(words)))
    lines = [line for line in lines if line]
    return lines if len(lines)>1 and all(explicit_body_line(line) for line in lines) else [txt(node)]

def body_table_pairs(table, product_name=""):
    rows=list(table_grid(table))
    # One packing block can contain a second, explicitly optional accessory table.
    for i,cells in enumerate(rows):
        titles=[cell for cell in cells if cell]
        if len(titles)==1 and len(titles[0])<110 and re.search(r"\b(?:optional|sold separately|not included)\b",titles[0],re.I):
            if i==0:return []
            table=deepcopy(table)
            for row in table.xpath(".//tr")[i:]:row.getparent().remove(row)
            rows=rows[:i]
            break
    # Some kits group their contents by version. A product title must identify that group.
    def version(cells):
        text=[c for c in cells if c]
        if len(text)==1 and 3<=len(text[0])<=90 and re.search(r"\bversion\b",text[0],re.I):return text[0].casefold()
        return ""
    versions={tag for row in rows if (tag:=version(row))}
    chosen=[tag for tag in versions if tag in product_name.casefold()]
    if versions and len(chosen)!=1:return []
    if not versions:
        for cells in rows:
            tags={label.strip(". :").casefold() for label in cells}
            if tags&NAME_HEADER and tags&QTY_HEADER:
                return column_rows(html.tostring(table,encoding="unicode"),"")["parts"]
    active=not versions
    pairs=[]
    for cells in rows:
        marker=version(cells)
        if marker:
            active=marker in chosen
            continue
        if not active:continue
        cells=[cell for cell in cells if cell]
        if len(cells)<1:continue
        if len(cells)==2 and COLUMN_QUANTITY.fullmatch(cells[1]):pairs.append([cells[0],cells[1]]);continue
        numbered_qty=COLUMN_QUANTITY.fullmatch(cells[-1]) or (len(cells)>=3 and "/" in cells[1] and re.fullmatch(r"[x×*]?\s*\d{1,3}\s*/\s*[x×*]?\s*\d{1,3}",cells[-1],re.I))
        if len(cells)>=3 and cells[0].isdigit() and numbered_qty:
            pairs.append([cells[1],cells[-1]]);continue
        if len(cells)>=2 and COLUMN_QUANTITY.fullmatch(cells[0]):
            # A quantity preceding several parallel items must be explicitly marked '1x'.
            if len(cells)==2 or re.search(r"[x×✕＊*]",cells[0],re.I):pairs.extend([n,cells[0]] for n in cells[1:])
            continue
        if len(cells)>=2 and COLUMN_QUANTITY.fullmatch(cells[1]) and re.search(r"[x×✕＊*]",cells[1],re.I):
            pairs.append([cells[0],cells[1]]);continue
        marked=[explicit_body_line(cell) for cell in cells]
        if marked and all(marked):pairs.extend(marked)
    return pairs

def as_pairs(el,product_name=""):
    pairs=[]
    tables=el.xpath("self::table | .//table[not(.//table)]")
    for table in tables:pairs.extend(body_table_pairs(table,product_name))
    if not tables:
        lines=el.xpath(".//li") or el.xpath(".//p[not(.//p)]")
        if not lines and el.tag in {"p","div"}:lines=[el]
        for e in lines:
            for line in packing_lines(e):
                if not line or len(line)>180 or PACK_TITLE.fullmatch(line):continue
                marked=explicit_body_line(line)
                if marked:pairs.append(marked)
                elif e.tag=="li":pairs.append([line,""])
    return [list(x) for x in dict.fromkeys(tuple(x) for x in pairs) if valid_part_name(x[0]) and not excluded_item(x[0]) and x[0].casefold() not in ATTRIBUTE_NAMES]


def cross_listed_parts(doc, parts, url):
    """Preserve duplicate category entries for the same item in a single packing table."""
    if not parts or not url:
        return {}
    accepted = {name.casefold(): name for name, _ in parts}
    cross_listed = {}
    for table in doc.xpath(".//table[not(.//table)]"):
        preceding = table.getprevious()
        if preceding is None or not PACK_TITLE.fullmatch(txt(preceding)):
            continue
        rows = iter(table_grid(table))
        headers = [label.strip(" :").casefold() for label in next(rows, [])]
        groups = [i for i, v in enumerate(headers) if v in {"category", "group"}]
        names = [i for i, v in enumerate(headers) if v in NAME_HEADER]
        quantities = [i for i, v in enumerate(headers) if v in QTY_HEADER]
        if not (len(groups) == len(names) == len(quantities) == 1):
            continue
        group_i, name_i, qty_i = groups[0], names[0], quantities[0]
        occurrences = {}
        for cells in rows:
            if len(cells) <= max(group_i, name_i, qty_i):
                continue
            name = accepted.get(cells[name_i].casefold())
            group, qty = cells[group_i], cells[qty_i]
            if not name or not group or not COLUMN_QUANTITY.fullmatch(qty):
                continue
            entry = {"group": group, "quantity": qty}
            entries = occurrences.setdefault(name, [])
            if entry not in entries:
                entries.append(entry)
        for name, entries in occurrences.items():
            if len({entry["group"].casefold() for entry in entries}) < 2:
                continue
            cross_listed[name] = {
                "kind": "crossListed", "source": text_link(url, "Part List", name),
                "text": " / ".join(" · ".join([entry["group"], name, entry["quantity"]]) for entry in entries),
                "groups": entries,
            }
    return cross_listed


def section_parts(doc,product_name=""):
    # Only accept the first content block after a literal packing-list heading.
    for h in doc.xpath(".//h1|.//h2|.//h3|.//h4|.//h5|.//p|.//strong|.//b"):
        if not PACK_TITLE.fullmatch(txt(h)): continue
        enclosing=h.xpath("ancestor::table[1]")
        if enclosing:
            grid=table_grid(enclosing[0]);first=[name for name in next(grid,[]) if name]
            if len(first)==1 and PACK_TITLE.fullmatch(first[0]):
                rows=as_pairs(enclosing[0],product_name)
                if rows:return rows
            row=h.xpath("ancestor::tr[1]")
            cells=row[0].xpath("./td|./th") if row else []
            if len(cells)>2:
                # Compare model columns only when a specific model in the SKU title
                # matches a complete, unambiguous header and the heading labels this row.
                head=enclosing[0].xpath(".//tr[1]")[0].xpath("./th|./td")
                headers=[txt(cell) for cell in head]
                if cells and txt(cells[0])==txt(h) and len(headers)==len(cells):
                    match=[]
                    for i,label in enumerate(headers[1:],1):
                        if not re.fullmatch(r"[\w-]{3,45}",label) or not re.search(r"\d",label):continue
                        if any(other.casefold().startswith(label.casefold()+"-") for other in headers):continue
                        if re.search(r"(?<![\w-])"+re.escape(label)+r"(?![\w-])",product_name,re.I):match.append(i)
                    if len(match)==1:
                        specific=as_pairs(cells[match[0]])
                        if specific:return specific
                continue
        at=h
        while at.getparent() is not None and at.getnext() is None:
            at=at.getparent()
        sibling=at.getnext()
        while sibling is not None and (sibling.tag in {"style","script"} or not txt(sibling)):sibling=sibling.getnext()
        if sibling is None or sibling.tag in ("h1","h2","h3","h4","h5"):continue
        groups=[]
        while sibling is not None and sibling.tag=="p" and re.fullmatch(r"[\w -]{0,45}(?:Modules|Components|Cables|Parts|Sensors|Tools):",txt(sibling),re.I):
            if excluded_item(txt(sibling)):break
            contents=sibling.getnext()
            if contents is None or contents.tag not in {"ul","ol"}:break
            used=as_pairs(contents)
            if not used or any(not qty for _,qty in used):break
            groups.extend(used)
            sibling=contents.getnext()
        if groups:return groups
        if sibling.tag in {"p","div"} and not sibling.xpath(".//table|.//ul|.//ol|.//h1|.//h2|.//h3|.//div|.//p"):
            rows=[]
            tag=sibling.tag
            while sibling is not None and sibling.tag==tag:
                found=as_pairs(sibling,product_name)
                if not found:
                    following=sibling.getnext()
                    if rows and following is not None and following.tag==tag and re.match(r"^[-•]\s*\d+\s*[x×]",txt(following),re.I):
                        sibling=following;continue
                    break
                rows.extend(found);sibling=sibling.getnext()
            if rows:return rows
        else:
            # Store editors occasionally use H2 for large text inside a table cell.
            headings=sibling.xpath(".//*[self::h1 or self::h2 or self::h3][not(ancestor::td or ancestor::th)]")
            if headings:
                block=next(iter(sibling),None)
                if block is None or block.tag not in {"ul","ol","table"}:continue
                sibling=block
            rows=as_pairs(sibling,product_name)
            if rows:return rows
    return []

def links(doc,base):
    out={}
    for a in doc.xpath(".//a[@href]"):
        href=safe_url(a.get("href"),base)
        if href and href!=base:
            label=txt(a) or next((norm(v) for v in a.xpath(".//img/@alt") if norm(v)),"") or link_title(href)
            out[href]={"name":label[:180],"url":href}
    return list(out.values())

def body_options(doc,url):
    """Options explicitly listed by this SKU's description; no compatibility inference."""
    results={}
    if not url:return []
    def optional(text):
        return len(text)<=150 and re.search(r"\boptional\b.{0,65}\b(?:accessories|antenna[s]?|sensors?|modules?|add[ -]?ons?|parts?)\b",text,re.I)
    def named_option(heading):
        # The table's directly preceding caption can identify a named product
        # family separately from the preceding sentence which makes it optional.
        label = re.fullmatch(r"(?:the )?following table (?:shows|lists) (?:the )?details (?:of|for) (?:the )?(.{4,85}?)s?\s*:\s*",
                             txt(heading), re.I)
        if not label:
            return None
        family = norm(re.sub(r"[®™]", "", label[1])).casefold().rstrip("s")
        family_model = re.search(r"\b[a-z]+\d+[a-z\d]*\b", family)
        if not family_model or not re.search(r"\b(?:sensor|module|antenna|board|adapter)$", family):
            return None
        sibling = heading.getprevious()
        for _ in range(5):
            if sibling is None or sibling.tag in {"table","h1","h2","h3","h4","h5","h6"}:
                break
            for sentence in re.split(r"(?<=[.!?;])\s+", txt(sibling)):
                if len(sentence)>450 or not re.match(r"\s*Optionally\b", sentence, re.I) or re.search(r"\b(?:required|mandatory|except)\b",sentence,re.I):
                    continue
                plain = norm(re.sub(r"[®™]", "", sentence)).casefold()
                if re.search(r"\b"+re.escape(family)+r"s?\b", plain):
                    model = family_model.group()
                    match_model = re.escape(model[:-1])+r"\d" if model.endswith("x") else re.escape(model)
                    return sentence, re.compile(r"\b"+match_model+r"\b", re.I)
            sibling = sibling.getprevious()
        return None
    for table in doc.xpath(".//table[not(.//table)]"):
        rows=list(table_grid(table))
        if not rows:continue
        start=0
        basis=None
        titles=[cell for cell in rows[0] if cell]
        if len(titles)==1 and optional(titles[0]):start=1
        else:
            at=table
            before=at.getprevious()
            while before is None and at.getparent() is not None and len(at.getparent().xpath(".//table"))==1:
                at=at.getparent();before=at.getprevious()
            if before is None:continue
            if not optional(txt(before)):
                basis=named_option(before)
                if not basis:continue
        sku_col=name_col=None
        trs=table.xpath(".//tr")
        for tr,cells in zip(trs[start:],rows[start:]):
            labels=[cell.strip(" .:").casefold() for cell in cells]
            if "sku" in labels and set(labels)&NAME_HEADER:
                sku_col=labels.index("sku");name_col=next(i for i,label in enumerate(labels) if label in NAME_HEADER)
                continue
            sku="";name=""
            if name_col is not None and max(name_col,sku_col)<len(cells):
                sku=cells[sku_col]
                if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{2,40}",sku):name=cells[name_col]
            elif len(cells)==3 and cells[0].isdigit() and COLUMN_QUANTITY.fullmatch(cells[2]):name=cells[1]
            elif len(cells)==2 and COLUMN_QUANTITY.fullmatch(cells[-1]):name=cells[0]
            if not valid_part_name(name) or len(name)>240:continue
            if basis and not basis[1].search(name):continue
            targets=[r["url"] for r in links(tr,url) if urlsplit(r["url"]).hostname=="www.seeedstudio.com" and urlsplit(r["url"]).path.lower().endswith(".html")]
            row={"name":name,"source":text_link(url,sku,name[:60]) if sku else text_link(url,name[:60]),"scope":"product","type":"商品页标明选配"}
            if basis:
                phrase = basis[0]
                row.update(basisText=phrase,basisSource=text_link(url," ".join(phrase.split()[:6])," ".join(phrase.split()[-6:])))
            if sku:row["sku"]=sku
            if len(targets)==1:row["productUrl"]=targets[0]
            results.setdefault((sku,name),row)
    return list(results.values())

def measurement_exclusion_only(text):
    """A weight, size or tested operating range may explicitly exclude an item."""
    matched = False
    for sentence in re.split(r"(?<=[.!?;])\s+|\n+", text):
        exclusion = EXCLUSION.search(sentence)
        if not exclusion:
            continue
        matched = True
        if re.search(r"\b(?:sold|purchase[ds]?|bought|ordered|order)\s+separately\b|\b(?:box|kit|delivery|shipment)\b.{0,35}\b(?:does not include|not included)\b|\bnot included\s+(?:with|in)\s+(?:the\s+)?(?:box|kit|delivery|package)\b", sentence, re.I):
            return False
        before = sentence[:exclusion.start()]
        metric = re.search(r"\b(?:dimensions?|weight|weighs?|height|length|width|depth|thickness|operating temperature|measurement range|test conditions)\b", before, re.I)
        unit = re.search(r"\d\s*(?:mm|cm|(?:k?g|grams?)|inch(?:es)?|°\s*[CF])\b", sentence, re.I)
        measurement_subject = re.search(r"\b(?:height|weight|width|length|depth|thickness|dimension)\s*$", before, re.I)
        if not metric or not (unit or measurement_subject):
            return False
    return matched


def non_product_exclusion_only(text):
    """Exclude a price, sample program or measurement qualifier from packing claims."""
    matched = False
    charge = r"(?:shipping(?:\s+and\s+handling)?|handling|delivery|import|customs?|dut(?:y|ies)|(?:sales\s+)?tax(?:es)?|vat|fees?|charges?|costs?)"
    for sentence in re.split(r"(?<=[.!?;])\s+|\n+", text):
        exclusion = EXCLUSION.search(sentence)
        if not exclusion:
            continue
        matched = True
        if measurement_exclusion_only(sentence):
            continue
        before, after = sentence[:exclusion.start()], sentence[exclusion.end():]
        if re.search(r"\b(?:this|the|our)\s+(?:(?:code|software|programming|basic)\s+)?(?:example|demonstration|sample code)\s*$", before, re.I):
            continue
        # Inspect only the excluded items. An adapter listed alongside a tax
        # still matters to a PM and must not disappear under this rule.
        items = after if re.search(r"\binclude\b", exclusion.group(), re.I) else before
        if re.search(r"\b"+charge+r"\b", items, re.I):
            stripped = re.sub(r"\b(?:"+charge+r"|all|the|any|applicable|local|international|value.added|and|or|are|is|note|prices?)\b|[\s,.:()&/-]+", "", items, flags=re.I)
            if not stripped:
                continue
        return False
    return matched


def foreign_customization(text, product_name):
    if not product_name:
        return False
    family = re.search(r"\bcustomi[sz]ation services? (?:based on|for) (?:the )?([\w][\w ®™-]{1,55}?) (?:series|family)\b",text,re.I)
    if not family:
        return False
    def words(name):
        return " ".join(re.findall(r"[a-z0-9]+",name.casefold()))
    label = words(family[1])
    return bool(label) and not re.search(r"\b"+re.escape(label)+r"\b", words(product_name))


def facts(fragment, source, product_name=""):
    notes=[]
    blocks=fragment.xpath(".//li|.//p[not(ancestor::li or ancestor::tr)]|.//tr") or [fragment]
    lines=[]
    for el in blocks:
        paragraph=txt(el)
        lines.extend(re.split(r"(?<=[.!?])\s+(?=[A-Z])",paragraph) if len(paragraph)>450 else [paragraph])
    for text in lines:
        if not text or len(text)>450:continue
        if EXCLUSION.search(text) and not non_product_exclusion_only(text):
            notes.append({"kind":"另购说明","text":text,"source":source})
        elif (re.search(r"\bSeeed(?: Studio)?(?: Agile)? ODM Services?\b",text,re.I)
                and re.search(r"\b(?:customi[sz]able|customi[sz]ation) services?\b",text,re.I)):
            notes.append({"kind":"定制说明","scope":"service","text":text,
                          "source":text_link(source," ".join(text.split()[:6])," ".join(text.split()[-4:]))})
        elif not foreign_customization(text, product_name) and re.search(r"(?:customi[sz]ation (?:service|options?)|(?:logo|firmware|packag\w*) customi[sz]ation|customi[sz](?:e|able) (?:the logo|your own logo))",text,re.I):
            notes.append({"kind":"定制说明","text":text,"source":source})
    return list({n["text"]:n for n in notes}.values())
