"""Capture the public Specification section without assigning a shared variant table to a SKU."""
import re
from copy import deepcopy
import json

from lxml import html

from .extract import norm, text_link, tree, txt


def install_specification(product, fragment):
    for key in ("specTables","specText","specRowsOmitted","specSource","specLocation"):
        product.pop(key,None)
    product["specStatus"]="empty"
    if not fragment:return
    if not isinstance(fragment,str):
        product["specStatus"]="unparsed"
        return
    root=tree(fragment)
    for hidden in root.xpath(".//script|.//style|.//noscript"):
        hidden.drop_tree()
    if not txt(root) and not root.xpath(".//img|.//object|.//iframe"):return
    product["specSource"]=text_link(product.get("url",""),"Specification")
    tables=[]
    omitted=0
    for element in root.xpath(".//table[not(.//table)]"):
        rows=[]
        for tr in element.xpath(".//tr"):
            cells=tr.xpath("./th|./td")
            values=[txt(cell) for cell in cells]
            if not any(values):continue
            if len(cells)>60 or any(len(value)>1500 for value in values):
                omitted+=1
                continue
            row=[]
            for cell,value in zip(cells,values):
                record={}
                for attr in ("rowspan","colspan"):
                    span=(cell.get(attr) or "1").strip()
                    if span.isdecimal() and len(span)<4 and 1<int(span)<=200:record[attr]=int(span)
                if cell.tag=="th":record["header"]=True
                row.append({"text":value,**record} if record else value)
            rows.append(row)
        if rows:
            captions=element.xpath("./caption")
            caption=txt(captions[0]) if captions else ""
            table={"rows":rows}
            if caption:table["title"]=caption[:180]
            if table not in tables:tables.append(table)
    if tables:product["specTables"]=tables
    notes=[]
    candidates=root.xpath(".//li[not(ancestor::table or .//li)]|.//p[not(ancestor::table or ancestor::li or .//p or .//table)]")
    if not candidates and not tables and not root.xpath(".//table"):
        candidates=[root]
    for block in candidates:
        text=norm(txt(block))
        if not text or re.fullmatch(r"specifications?[:\s]*",text,re.I):continue
        if len(text)>420:
            omitted+=1
            continue
        if text not in notes:notes.append(text)
    if notes:product["specText"]=notes
    if omitted:product["specRowsOmitted"]=omitted
    if tables or notes:product["specStatus"]="partial" if omitted else "present"
    else:product["specStatus"]="image" if not txt(root) else "unparsed"


BODY_HEADING = re.compile(r"(?:(?:technical|product|hardware) )?specifications?|technical (?:details|data)|tech specs", re.I)
STOP_HEADING = re.compile(r"(?:part|pack(?:ing|age)) list|package contents|hardware overview|features?|applications?|documents?|resources?|overview|accessories|note|tip", re.I)


def install_description_specs(product, fragment):
    """Read an explicitly titled data block in the public description, with its own source."""
    if product.get("specTables") or product.get("specText") or fragment is None or isinstance(fragment,str) and not fragment.strip():
        return
    root = tree(fragment) if isinstance(fragment,str) else fragment
    candidates = root.xpath(".//*[self::h1 or self::h2 or self::h3 or self::h4 or self::h5 or self::p or self::b or self::strong or self::div][not(ancestor::table or .//table or .//ul or .//ol)]")
    for heading in candidates:
        title = txt(heading).rstrip(":").strip()
        if not BODY_HEADING.fullmatch(title):
            continue
        # Editors wrap some headings in two or three elements. Take the outermost
        # wrapper with exactly that text so a following table remains a sibling.
        anchor = heading
        while anchor.getparent() is not None and txt(anchor.getparent()) == txt(anchor):
            anchor = anchor.getparent()
        blocks = []
        group = ""
        level = int(heading.tag[1]) if re.fullmatch("h[1-5]",heading.tag) else 2
        for sibling in anchor.itersiblings():
            if not isinstance(sibling.tag,str) or sibling.tag in {"script","style"}:
                continue
            label = txt(sibling)
            if not label:
                continue
            actual = sibling.tag in {"table","ul","ol"}
            first = sibling.xpath("(.//*[not(ancestor::table or ancestor::ul or ancestor::ol) and (self::h1 or self::h2 or self::h3 or self::h4 or self::strong or self::b)])[1]") if not actual else []
            if STOP_HEADING.fullmatch(label.rstrip(":").strip()) or first and STOP_HEADING.fullmatch(txt(first[0]).rstrip(":").strip()):
                break
            if re.fullmatch("h[1-5]",sibling.tag) and int(sibling.tag[1])<=level:
                if BODY_HEADING.fullmatch(label.rstrip(":").strip()):continue
                break
            contents = sibling.xpath("self::table|self::ul|self::ol|.//table[not(ancestor::table)]|.//ul[not(ancestor::ul or ancestor::table)]|.//ol[not(ancestor::ol or ancestor::table)]")
            if contents:
                node=deepcopy(contents[0])
                if group and node.tag=="table" and not node.xpath("./caption"):
                    caption=html.Element("caption");caption.text=group;node.insert(0,caption)
                elif group and node.tag in {"ol","ul"}:
                    for item in node.xpath("./li"):
                        item.text=group+" — "+(item.text or "")
                blocks.append(node)
                group=""
                if not actual:break
                continue
            if sibling.tag in {"p","div"} and len(label)<=420 and re.match(r"^[^:]{1,65}:\s*\S",label):
                blocks.append(sibling)
                continue
            if BODY_HEADING.fullmatch(label.rstrip(":").strip()):
                continue
            if sibling.tag in {"p","div","h3","h4","h5"} and len(label)<=150 and not sibling.xpath(".//img|.//a"):
                group=label
                continue
            if not blocks and sibling.tag=="p" and len(label)<=360:
                continue
            break
        if blocks:
            wrapper = html.Element("div")
            for block in blocks:
                wrapper.append(deepcopy(block))
            derived = {}
            derived["url"] = product.get("url","")
            install_specification(derived,html.tostring(wrapper,encoding="unicode"))
            if derived.get("specTables") or derived.get("specText"):
                product.update({key:value for key,value in derived.items() if key!="url"})
                product["specLocation"]="description"
                product["specSource"]=text_link(product.get("url",""),title)
                return


REFERENCE_HEADINGS={
    "certification_info_tech":"Technical details",
    "hardware_overview":"Hardware Overview",
    "certification_info":"Certification",
    "certification_info_eccn":"ECCN",
    "faq_list":"FAQ",
}


def install_reference_sections(product,sections):
    result=dict(product.get("referenceSections") or {})
    for key,title in REFERENCE_HEADINGS.items():
        if key not in sections:continue
        result.pop(key,None)
        raw=sections[key]
        if not raw:continue
        doc={"url":product.get("url","")}
        if key=="faq_list":
            if isinstance(raw,str) and raw.lstrip().startswith(("[","{")):
                try:raw=json.loads(raw)
                except json.JSONDecodeError:pass
            if isinstance(raw,list):
                questions=[txt(tree(q["question"])) for q in raw if isinstance(q,dict) and isinstance(q.get("question"),str)]
                notes=[q for q in questions if 0<len(q)<=420]
                if notes:result[key]={"text":notes,"source":text_link(doc["url"],title)}
                continue
        install_specification(doc,raw)
        details={}
        if doc.get("specTables"):details["tables"]=doc["specTables"]
        if doc.get("specText"):details["text"]=doc["specText"]
        if doc.get("specRowsOmitted"):details["omitted"]=doc["specRowsOmitted"]
        if doc.get("specStatus")=="image":details["mediaOnly"]=True
        if not details:continue
        locator=title
        for tab in details.get("tables",[]):
            for row in tab["rows"]:
                values=[c if isinstance(c,str) else c["text"] for c in row]
                if len(values)<2:continue
                if locator==title and key=="certification_info_eccn":locator=values[0] or title
                if values[0].casefold()=="dimensions" and re.fullmatch(r"\s*0+(?:\.0+)?\s*(?:mm|cm)?(?:\s*[x×*]\s*0+(?:\.0+)?\s*(?:mm|cm)?){1,3}\s*",values[1],re.I):
                    row[1]={"text":values[1],"unconfirmed":True}
        details["source"]=text_link(doc["url"],locator)
        result[key]=details
    if result:product["referenceSections"]=result
    else:product.pop("referenceSections",None)
