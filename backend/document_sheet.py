"""Read small official procurement workbooks without extracting or following links."""
import hashlib
from io import BytesIO
import re
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile


GROVE_GAMMA = "https://files.seeedstudio.com/products/110020230/Part-List.xlsx"
GAMMA_DIGEST = "4edc7825471e1555f509b4b98b98afa0354386f5cf8027f9f836f0c02416f7e6"
STACKFORCE_BOM = "https://files.seeedstudio.com/wiki/robotics/projects/stackfoce/EN/BOM.xlsx"
STACKFORCE_DIGEST = "b9f8998bd96479ed4f7cb07c5ef3729e84dc6e660d3e382a83da26d48a9a1e66"
MICROBIT_GROVES = "Grove Modules for microbit v2.xlsx"
MICROBIT_URL = "https://github.com/SeeedDocument/Bazzar_Attachment/raw/master/110060762/Grove%20Modules%20for%20microbit%20v2.xlsx"
BLUE_URL = "https://github.com/SeeedDocument/Beaglebone_Blue/raw/master/res/Beaglebone%20Blue%20Grove%20Compatibility%20List.xlsx"
MATRICES = {
    BLUE_URL:("761e7bfe831caa46f83d16a103f12b0447f78daf118425bfa8ab1670bc56515a","102990827","BeagleBone® Blue",63),
    MICROBIT_URL:("e6b40221e056464bd93e09339ab972a372e2e59ee6ade7d236ca7b4fa6a77156","103100063","Grove Shield for micro:bit v2.0",50),
}
SHEET_NAME = re.compile(r"(?:parts?[\s._-]*list|pack(?:ing|age)[\s._-]*(?:list|contents)|accessor(?:ies|y)[\s._-]*(?:list|matrix)|compatibility[\s._-]*(?:list|matrix)|bill[\s._-]*of[\s._-]*materials|(?:^|[^a-z])bom(?:[^a-z]|$))",re.I)
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
RID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def targeted(url):
    name = unquote(urlsplit(url).path).rsplit("/",1)[-1]
    return name.lower().endswith(".xlsx") and (bool(SHEET_NAME.search(name)) or name==MICROBIT_GROVES)


def reviewed_assembly(url, record):
    sheets=record.get("worksheets",[])
    return bool(url==STACKFORCE_BOM and record.get("sha256")==STACKFORCE_DIGEST and sheets
                and sheets[0].get("header")==["Item Name","Quantity","Unit","Specifications","Notes/Standards"])


def xml(book, path):
    data = book.read(path)
    if b"\x00" in data[:128] or b"<!DOCTYPE" in data or b"<!ENTITY" in data:
        raise ValueError("unexpected_xml_declaration")
    return ET.fromstring(data)


def structured_sheet(name, rows):
    entries=[]; columns={}; populated=0; header=[]
    aliases={"sku":"sku","product name":"name","item name":"name","item":"name","grove modules":"name",
             "quantity":"quantity","qty":"quantity","i/o type":"interface","port":"interface",
             "working voltage":"voltage","makecode package developed":"makeCode"}
    for number,cells in rows:
        if any(cells.values()):populated+=1
        if not columns:
            fields={aliases[v.lower()]:k for k,v in cells.items() if v.lower() in aliases}
            if {"sku","name"}<=set(fields):columns=fields;header=list(cells.values())[:10]
            elif not header and any(k in fields for k in ("quantity","name")):header=list(cells.values())[:10]
            continue
        sku=cells.get(columns["sku"],""); label=cells.get(columns["name"],"")
        if not re.fullmatch(r"(?:[1-9]\d{8}|[A-Za-z][A-Za-z0-9_-]{4,28}\d)",sku) or not label:continue
        quantity=cells.get(columns.get("quantity",""),"")
        col=sorted(columns.values(),key=lambda s:(len(s),s))
        row={"publishedSku":sku,"name":label,"quantity":quantity if re.fullmatch(r"[1-9]\d{0,3}",quantity) else "",
             "sheet":name,"row":int(number),"cellRange":f"{col[0]}{number}:{col[-1]}{number}"}
        for field in ("interface","voltage","makeCode"):
            if field in columns and cells.get(columns[field]):row[field]=cells[columns[field]]
        entries.append(row)
    summary={"name":name,"rows":len(entries),"populatedRows":populated}
    if header:summary["header"]=header
    if entries:summary.update(firstRow=entries[0]["row"],lastRow=entries[-1]["row"])
    return summary,entries[:500]


def parse(body, url):
    digest = hashlib.sha256(body).hexdigest()
    result = {"status":"unread","reason":"section_needs_review","sha256":digest,"worksheets":[],"sheetRows":[]}
    try:
        with ZipFile(BytesIO(body)) as book:
            entries = book.infolist()
            if len(entries)>180 or len({e.filename for e in entries})!=len(entries) or sum(e.file_size for e in entries)>12_000_000 or any(e.file_size>4_000_000 for e in entries):
                return {**result,"status":"unread","reason":"limit_bytes"}
            names = set(book.namelist())
            shared = []
            if "xl/sharedStrings.xml" in names:
                shared = ["".join(t.text or "" for t in s.iter(NS+"t")) for s in xml(book,"xl/sharedStrings.xml").findall(NS+"si")]
            paths = {}
            for rel in xml(book,"xl/_rels/workbook.xml.rels"):
                target=rel.get("Target","")
                if rel.get("TargetMode")=="External":continue
                path=target.lstrip("/") if target.startswith("/") else "xl/"+target
                if re.fullmatch(r"xl/worksheets/sheet[1-9]\d*\.xml",path) and path in names:paths[rel.get("Id")]=path
            for sheet in xml(book,"xl/workbook.xml").iter(NS+"sheet"):
                path=paths.get(sheet.get(RID)); name=sheet.get("name","")
                if not path or sheet.get("state","visible")!="visible" or not name:continue
                cells_by_row=[]
                for row in xml(book,path).iter(NS+"row"):
                    number=row.get("r","")
                    if not number.isdigit() or row.get("hidden")=="1":continue
                    cells={}
                    for cell in row.findall(NS+"c"):
                        address=re.fullmatch(r"([A-Z]{1,3})(\d+)",cell.get("r",""))
                        if not address or address[2]!=number or cell.find(NS+"f") is not None:continue
                        val=cell.findtext(NS+"v",""); typ=cell.get("t")
                        if typ=="s":
                            if not val.isdigit() or int(val)>=len(shared):continue
                            val=shared[int(val)]
                        elif typ=="inlineStr":val="".join(t.text or "" for t in cell.iter(NS+"t"))
                        elif typ not in (None,"n","str"):continue
                        cells[address[1]]=" ".join(val.split())[:400]
                    cells_by_row.append((number,cells))
                summary,entries=structured_sheet(name,cells_by_row)
                result["worksheets"].append(summary)
                result["sheetRows"].extend(entries)
    except (ET.ParseError,BadZipFile,OSError,ValueError,KeyError,RuntimeError):
        return {"sha256":digest,"status":"failed","reason":"unreadable_workbook"}
    if reviewed_assembly(url,result):
        # The assembly Wiki presents this engineering BOM separately from the
        # store's ready-made robot and controller. No kit quantities transfer.
        result.update(status="empty",sheetReview="assembly_bom")
        result.pop("reason",None)
    return result


def verified_rows(url, product, record, by_sku):
    """Promote a reviewed edition only for its independently identified host."""
    rows=record.get("sheetRows",[])
    title=product.get("name","").lower()
    if url in MATRICES:
        digest,host,title,count=MATRICES[url]
        if (record.get("sha256")!=digest or product.get("sku")!=host or product.get("name")!=title or len(rows)!=count
                or [r["row"] for r in rows]!=list(range(2,count+2)) or any(r["sheet"]!="Sheet1" for r in rows)):
            return []
        results={}
        for row in rows:
            code=row["publishedSku"]
            detail={k:row[k] for k in ("interface","voltage","makeCode","sheet","row","cellRange") if row.get(k)}
            detail["source"]=url
            relation="published_host_module_workbook" if url==MICROBIT_URL else "reviewed_host_compatibility_workbook"
            fact={**row,"kind":"accessory","scope":"sku","basis":relation,"namedAccessory":True,
                  "source":url,"compatibilityDetails":[detail],"storeProductSource":product.get("url") or product.get("productUrl","")}
            if code in by_sku:fact["sku"]=code
            if code in results:results[code]["compatibilityDetails"].append(detail)
            else:results[code]=fact
        return list(results.values())
    if (url!=GROVE_GAMMA or record.get("sha256")!=GAMMA_DIGEST or product.get("sku")!="110020230"
            or "grove creator kit" not in title or not re.search(r"(?:γ|gamma)\s*/\s*40 grove functional modules in one box",title)
            or len(rows)!=40 or len({r["publishedSku"] for r in rows})!=40 or [r["row"] for r in rows]!=list(range(2,42))
            or any(r["sheet"]!="Sheet1" or r["quantity"] for r in rows)):
        return []
    result=[]
    for row in rows:
        code=row["publishedSku"]
        fact={**row,"kind":"inbox","scope":"sku","basis":"reviewed_kit_workbook_and_product_title",
              "source":url,"storeProductSource":product.get("url") or product.get("productUrl","")}
        if code in by_sku:fact["sku"]=code
        result.append(fact)
    return result
