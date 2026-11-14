"""Import private local reference material as attributed records, separate from the public catalogue."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import threading
import zipfile
import xml.etree.ElementTree as ET

from .storage import Problem, packed, read_json, write

SKU = re.compile(r"(?<![A-Za-z0-9])(?:\d{9}|[Ee]\d{8})(?![A-Za-z0-9])")
EOL = re.compile(r"(?<![A-Za-z])EOL(?![A-Za-z])|End of Life", re.I)
WORD = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
XL = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
SUPPORTED = {".md", ".docx", ".xlsx", ".zip"}


def instant():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def unescape(text):
    return re.sub(r"\\([.\-+|_()#])", r"\1", text).strip()


def identifiers(text):
    return list(dict.fromkeys(x.upper() for x in SKU.findall(text)))


def classify(title, text):
    if "SSD" in title.upper() or re.search(r"存储|系统盘|数据盘", title):
        return "ssd"
    if re.search(r"无线|天线|Wi.?Fi|Bluetooth", title, re.I):
        return "wireless"
    if re.search(r"Logo|标识", title, re.I):
        return "logo"
    if re.search(r"规则|定制|审查", title):
        return "customization"
    return "reference"


def record(source, location, title, text, skus=(), kind=None, scope="sku", **extra):
    text = unescape(text)
    identity = "|".join([source["id"], location, title, text])
    return {"id": hashlib.sha256(identity.encode()).hexdigest()[:24],
            "sourceId": source["id"], "version": source["version"], "location": location,
            "title": unescape(title), "text": text, "skus": list(dict.fromkeys(skus)),
            "kind": kind or classify(title, text), "scope": scope, **extra}


def markdown(source, text):
    lines = text.splitlines()
    records = []
    headings = []
    declared = list(dict.fromkeys(re.findall(r"销售\s*SKU\s*[：:]\s*(\d{9})", text, re.I)))
    document_scope = declared if len(declared) == 1 else []
    inherited = document_scope[:]
    chunk = []
    start = 1
    table_header = []

    def flush(end):
        nonlocal chunk
        value = "\n".join(chunk).strip()
        if value:
            title = " / ".join(h[1] for h in headings) or source["title"]
            targets = inherited[:]
            records.append(record(source, f"L{start}–L{end}", title, value, targets,
                                  scope="sku" if targets else "general"))
        chunk = []

    for number, raw in enumerate(lines, 1):
        line = unescape(raw)
        heading = re.match(r"^(#{1,6})\s+(.+)", line)
        if heading:
            flush(number - 1)
            level, label = len(heading[1]), heading[2]
            headings = [h for h in headings if h[0] < level] + [(level, label)]
            inherited = next((identifiers(h[1]) for h in reversed(headings) if identifiers(h[1])), document_scope[:])
            start = number + 1
            table_header = []
            continue
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            following = unescape(lines[number]) if number < len(lines) else ""
            if following.startswith("|") and re.fullmatch(r"[|:\-\s]+",following):
                table_header = cells
        # Tables identify the host in their SKU cell. Scoped product sections retain the host.
        if line.startswith("|") and identifiers(line):
            flush(number - 1)
            cells = [c.strip() for c in line.strip("|").split("|")]
            title = " / ".join(h[1] for h in headings) or source["title"]
            targets = inherited or identifiers(line)
            combination = bool(re.search(r"组合项", title) or re.search(r"\d{9}\s*\+\s*\d{9}", line))
            named = next((c for c in cells[:2] if re.search(r"[A-Za-z\u4e00-\u9fff]", c)
                          and not re.fullmatch(r"[Ee]\d{8}", c)), "")
            if inherited:
                named = ""
            records.append(record(source, f"L{number}", title, line, targets,
                                  scope="combination" if combination else "sku",
                                  fields=[{"name":key,"value":value} for key,value in zip(table_header,cells)] if len(table_header)==len(cells) else [],
                                  materialCodes=[code for code in identifiers(line) if code not in targets],
                                  productName=named))
            start = number + 1
            continue
        chunk.append(raw)
        if not line and len("\n".join(chunk)) > 900:
            flush(number)
            start = number + 1
    flush(len(lines))
    return records, "\n".join(f"{i}: {line}" for i, line in enumerate(lines, 1))


def docx(source, raw):
    with zipfile.ZipFile(raw) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    alltext = "\n".join("".join(n.text or "" for n in p.findall(".//w:t", WORD))
                        for p in root.findall(".//w:p", WORD))
    rows = []
    for ti, table in enumerate(root.findall(".//w:tbl", WORD), 1):
        for ri, row in enumerate(table.findall("w:tr", WORD), 1):
            cells = ["".join(t.text or "" for t in c.findall(".//w:t", WORD))
                     for c in row.findall("w:tc", WORD)]
            rows.append((f"Table {ti}, row {ri}", cells))
    change = re.search(r"CHANGE DESCRIPTION\s*(.*?)(?:REASONS FOR CHANGE|CUSTOMER ACTION REQUIRED|$)",alltext,re.I|re.S)
    description = change[1] if change else ""
    confirmed = re.search(r"(?im)^\s*(?:EOL|End of Life)(?:\s*[.:：-]|\s*$)",description)
    selected = re.search(r"[☒☑✓✔]\s*(?:EOL|End of Life)\b",description,re.I)
    is_eol = bool(confirmed or selected)
    action = re.search(r"CUSTOMER ACTION REQUIRED\s*([^\n]+)", alltext, re.I)
    action_text = action[1].strip() if action else ""
    date = re.search(r"PCN(\d{4})(\d{2})(\d{2})", source["title"])
    issue_date = "-".join(date.groups()) if date else ""
    sell_until = bool(re.search(r"sold until out of stock|while supplies last|售完", alltext, re.I))
    records, seen = [], set()
    for location, cells in rows:
        if not cells:
            continue
        code = cells[0].strip()
        if not SKU.fullmatch(code) or code in seen:
            continue
        seen.add(code)
        name = cells[1].strip() if len(cells) > 1 else ""
        text = " | ".join([code, name, "EOL" if is_eol else "", issue_date,
                           "Sold until out of stock" if sell_until else "", action_text])
        records.append(record(source, location, source["title"], text, [code],
                              kind="eol" if is_eol else "reference", date=issue_date,
                              productName=name, sellUntilOutOfStock=sell_until, action=action_text))
    if not records:
        records.append(record(source, "Document", source["title"], alltext, scope="general"))
    return records, alltext


def column(ref):
    number = 0
    for letter in re.match("[A-Z]+", ref)[0]:
        number = number * 26 + ord(letter) - 64
    return number


def cell_ref(col, row):
    result = ""
    while col:
        col, mod = divmod(col - 1, 26)
        result = chr(65 + mod) + result
    return result + str(row)


def workbook(source, path):
    # Only identifiers, names, bounded category labels and explicit lifecycle markers are imported.
    # Cost, profit and price values never enter the saved dataset or the browser.
    records, evidence = [], []
    with zipfile.ZipFile(path) as archive:
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            strings = ["".join(t.text or "" for t in item.findall(".//m:t", XL)) for item in root]
        relations = {e.attrib["Id"]: e.attrib["Target"]
                     for e in ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))}
        book = ET.fromstring(archive.read("xl/workbook.xml"))
        for sheet in book.find("m:sheets", XL):
            name = sheet.attrib["name"]
            target = relations[sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]]
            target = target.lstrip("/") if target.startswith("/") else "xl/" + target
            root = ET.fromstring(archive.read(target))
            cells = {}
            for c in root.findall(".//m:sheetData/m:row/m:c", XL):
                v = c.find("m:v", XL)
                value = v.text or "" if v is not None else ""
                if c.attrib.get("t") == "s":
                    value = strings[int(value)]
                elif c.attrib.get("t") == "inlineStr":
                    value = "".join(t.text or "" for t in c.findall(".//m:t", XL))
                cells[c.attrib["r"]] = value
            merges = []
            for entry in root.findall(".//m:mergeCell", XL):
                left, right = entry.attrib["ref"].split(":")
                merges.append((column(left), int(re.search(r"\d+", left)[0]),
                               column(right), int(re.search(r"\d+", right)[0]), left))
            def value_at(col, row):
                key = cell_ref(col, row)
                if cells.get(key):
                    return cells[key], key
                for c1, r1, c2, r2, anchor in merges:
                    if c1 <= col <= c2 and r1 <= row <= r2:
                        return cells.get(anchor, ""), anchor
                return "", key
            headers = [(column(ref), int(re.search(r"\d+", ref)[0])) for ref, value in cells.items()
                       if value.strip().upper() in {"SKU", "销售SKU", "SKU编号"}]
            for col, header_row in headers:
                next_header = min([r for c, r in headers if c == col and r > header_row] or [100000])
                right_bound = min([c for c, r in headers if r == header_row and c > col] or [col + 7])
                rows = sorted({int(re.search(r"\d+", ref)[0]) for ref in cells})
                for row in rows:
                    if not header_row < row < next_header:
                        continue
                    code, sku_ref = value_at(col, row)
                    if not SKU.fullmatch(code.strip()):
                        continue
                    code = code.strip().upper()
                    product, product_ref = value_at(col + 1, row)
                    if not product or not re.search(r"[A-Za-z\u4e00-\u9fff]", product):
                        continue
                    category, category_ref = value_at(col - 1, row) if col > 1 else ("", "")
                    # Repeated independent SKU groups must never inherit a distant left-hand category.
                    if col > min(c for c, r in headers if r == header_row):
                        category, category_ref = "", ""
                    marks = [(product_ref, product), (category_ref, category)]
                    marks += [(cell_ref(c, row), cells.get(cell_ref(c, row), ""))
                              for c in range(col + 2, min(right_bound, col + 7))]
                    eol_cells = [(ref, value) for ref, value in marks if EOL.search(value)]
                    location = name + "!" + sku_ref + "/" + product_ref
                    date = re.search(r"(20\d{6})", name)
                    issue_date = date[1][:4] + "-" + date[1][4:6] + "-" + date[1][6:] if date else ""
                    text = " | ".join([code, product, category]).strip(" |")
                    records.append(record(source, location, name, text, [code], kind="identity",
                                          date=issue_date, productName=product,
                                          fields=[{"name":"SKU","value":code},{"name":"产品名称","value":product}]+([{"name":"分类","value":category}] if category else [])))
                    evidence.append(location + " | " + text)
                    if eol_cells:
                        status = "; ".join(ref + " " + value for ref, value in eol_cells)
                        records.append(record(source, name + "!" + ",".join(ref for ref, _ in eol_cells),
                                              name, code + " | " + product + " | " + status,
                                              [code], kind="eol", date=issue_date, productName=product))
                        evidence.append(name + " | " + status)
    return records, "\n".join(evidence)


def scan_paths(root):
    if not root.is_dir():
        raise Problem("INTERNAL_DIRECTORY_NOT_FOUND")
    paths = []
    for file in sorted(root.rglob("*")):
        if file.is_file() and file.suffix.lower() in SUPPORTED:
            if not file.resolve().is_relative_to(root):
                raise Problem("INTERNAL_PATH_OUTSIDE_ROOT")
            paths.append(file)
    if len(paths) > 200:
        raise Problem("INTERNAL_TOO_MANY_FILES")
    return paths


def fingerprint(root):
    return [[str(p.relative_to(root)), p.stat().st_size, p.stat().st_mtime_ns] for p in scan_paths(root)]


def import_directory(root):
    root = Path(root).expanduser().resolve()
    manifest = fingerprint(root)
    if not manifest:
        raise Problem("INTERNAL_NO_SUPPORTED_FILES")
    documents, records, errors = [], [], []
    for relative, size, stamp in manifest:
        path = root / relative
        if size > 40_000_000:
            errors.append({"file": relative, "error": "FILE_TOO_LARGE"})
            continue
        raw = path.read_bytes()
        version = hashlib.sha256(raw).hexdigest()
        source = {"id": hashlib.sha256(relative.encode()).hexdigest()[:24], "title": relative,
                  "version": version, "modifiedAt": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")}
        try:
            if path.suffix.lower() == ".md":
                found, body = markdown(source, raw.decode("utf-8-sig"))
            elif path.suffix.lower() == ".docx":
                found, body = docx(source, path)
            elif path.suffix.lower() == ".xlsx":
                found, body = workbook(source, path)
            else:
                found, bodies = [], []
                with zipfile.ZipFile(path) as archive:
                    members = [member for member in archive.infolist() if member.filename.lower().endswith(".md")]
                    if not members:
                        raise ValueError("No Markdown in archive")
                    for member in members:
                        if member.file_size > 5_000_000:
                            raise ValueError("Markdown too large")
                        text = archive.read(member).decode("utf-8-sig")
                        child = {**source, "title": relative + " / " + member.filename}
                        child_records, child_body = markdown(child, text)
                        for item in child_records:
                            item["location"] = member.filename + " · " + item["location"]
                        found.extend(child_records)
                        bodies.append(member.filename + "\n" + child_body)
                body = "\n\n".join(bodies)
            documents.append({**source, "text": body})
            records.extend(found)
        except (ValueError, OSError, KeyError, IndexError, zipfile.BadZipFile, ET.ParseError, UnicodeError):
            errors.append({"file": relative, "error": "PARSE_FAILED"})
    return {"format": 2, "root": str(root), "importedAt": instant(), "manifest": manifest,
            "documents": documents, "records": records, "errors": errors,
            "version": hashlib.sha256(packed([[d["id"], d["version"]] for d in documents])).hexdigest()[:16]}


class InternalKnowledge:
    def __init__(self, directory):
        self.path = Path(directory) / "internal-knowledge.json"
        self.lock = threading.RLock()
        self.data = read_json(self.path, {"documents": [], "records": [], "errors": []})
        self.error = ""
        self.products = {}
        self.catalog_key = None

    def load(self, root=None):
        with self.lock:
            old = self.data
            root = root or old.get("root")
            if not root:
                return
            try:
                root_path = Path(root).expanduser().resolve()
                manifest = fingerprint(root_path)
                if old.get("format")==2 and str(root_path) == old.get("root") and manifest == old.get("manifest"):
                    self.error = ""
                    return
                data = import_directory(root_path)
                if data["errors"]:
                    # Keep the last good version of each failed source.
                    failed = {e["file"] for e in data["errors"]}
                    prior = [d for d in old["documents"] if d["title"] in failed]
                    ids = {d["id"] for d in prior}
                    data["documents"].extend(prior)
                    data["records"].extend(r for r in old["records"] if r["sourceId"] in ids)
                write(self.path, packed(data))
                self.data = data
                self.catalog_key = None
                self.error = ""
            except (Problem, OSError, ValueError):
                self.error = "INTERNAL_REFRESH_FAILED"
                if not old.get("root"):
                    raise Problem("INTERNAL_IMPORT_FAILED")

    def apply(self, catalog):
        with self.lock:
            if self.catalog_key is catalog:
                return
            original = {p["sku"]: p for p in catalog["products"]}
            self.public_by_sku = original
            products = {}
            sources = {d["id"]: d for d in self.data["documents"]}
            for row in self.data["records"]:
                if row["scope"] == "combination":
                    continue
                for sku in row["skus"]:
                    item = products.setdefault(sku, {"sku": sku, "name": original.get(sku, {}).get("name", ""),
                        "records": [], "eol": False, "internalOnly": sku not in original, "names": []})
                    item["records"].append({**row, "sourceTitle": sources[row["sourceId"]]["title"]})
                    name = row.get("productName")
                    if name and name not in item["names"]:
                        item["names"].append(name)
                    if row["kind"] == "eol":
                        item["eol"] = True
                    if item["internalOnly"] and not item["name"] and name:
                        item["name"] = name
            for item in products.values():
                if not item["name"]:
                    item["name"] = item["sku"]
                item["version"] = self.data.get("version", "")
                item["importedAt"] = self.data.get("importedAt", "")
            self.products = products
            self.catalog_key = catalog

    def summary(self):
        matched = sum(not p["internalOnly"] for p in self.products.values())
        return {"importedAt": self.data.get("importedAt", ""), "version": self.data.get("version", ""),
                "documents": len(self.data["documents"]), "records": len(self.data["records"]),
                "matched": matched, "unmatched": len(self.products) - matched,
                "eol": sum(p["eol"] for p in self.products.values()),
                "sourceRoot": self.data.get("root", ""), "errors": self.data["errors"],
                "error": self.error}

    def public(self):
        return {"summary": self.summary(), "documents": [{k: v for k, v in d.items() if k != "text"} for d in self.data["documents"]],
                "records": self.data["records"]}

    def source(self, ident):
        value = next((d for d in self.data["documents"] if d["id"] == ident), None)
        if value is None:
            raise Problem("INTERNAL_SOURCE_NOT_FOUND", 404)
        return value

    def assess(self, skus, description, language="zh", materials=()):
        en = language == "en"
        materials = [m for m in materials[:50] if isinstance(m,dict)
                     and isinstance(m.get("sku"),str) and isinstance(m.get("hostSku"),str)]
        if not re.search(r"SSD|NVMe|SATA|固态|系统盘|数据盘|存储|storage|system drive|data drive|盘[12一二]|drive\s*[12]", description, re.I):
            return []
        def say(zh, english):
            return english if en else zh
        capacity_pattern = r"(\d+(?:\.\d+)?\s*(?:GB|TB))"
        def capacity(text):
            found = re.search(capacity_pattern, text, re.I)
            return re.sub(r"\s+", "", found[1]).upper() if found else ""
        intent = re.sub(r"(?:不|无需|不要)(?:增加|加装|保留|额外)|(?:do not|without) (?:add|retain|keep)", "", description, flags=re.I)
        added = bool(re.search(r"增加|新增|加装|额外|数据盘|additional|add ", intent, re.I))
        retained = bool(re.search(r"保留|retain|keep ", intent, re.I))
        upgrade = bool(re.search(r"升级|替换|更换|换|upgrade|replace", intent, re.I))
        results = []
        for sku in skus:
            product = self.products.get(sku)
            if not product:
                continue
            rows = [r for r in product["records"] if r["kind"] == "ssd"]
            content = "\n".join(r["title"] + "\n" + r["text"] for r in rows)
            dimensions = list(dict.fromkeys(re.findall(r"(?<!\d)(2242|2280)(?!\d)", content)))
            actions, confirm = [], []
            uncertain = not rows or len(dimensions) != 1 or "公开资料暂时无法确认" in content
            dual = bool(re.search(r"双\s*SSD|2\s*个\s*M\.?2", content, re.I))
            original_match = re.search(r"(?:标配|标品包含|standard)\s*" + capacity_pattern, content, re.I)
            original = capacity(original_match[0]) if original_match else ""
            selected = [m for m in materials if m.get("hostSku") == sku]
            selected_text = " ".join(self.products.get(m.get("sku"), {}).get("name", "") for m in selected)
            specified_codes = identifiers(description)
            selected_text += " " + " ".join(self.products.get(code, {}).get("name", "") for code in specified_codes)
            target_match = re.search(r"(?:升级(?:为|到)?|替换(?:为|成)?|更换(?:为|成)?|换|加装|新增|增加|upgrade|replace)\s*(?:SSD\s*)?" + capacity_pattern, description, re.I)
            target = capacity(target_match[0]) if target_match else capacity(description) or capacity(selected_text)
            explicit_grade = bool(re.search(r"商规|商业级|工规|工业级|industrial|commercial", description+" "+selected_text, re.I))
            required_grade = "industrial" if re.search(r"工规|工业级|industrial",description,re.I) else "commercial" if re.search(r"商规|商业级|commercial",description,re.I) else ""
            relation = "add" if added else "replace" if upgrade else ""
            if selected and not relation:
                relation = selected[0].get("action", "")
            slots = {}
            for match in re.finditer(r"(?:盘|drive\s*|slot\s*)([12一二])\s*([^，,；;\n]+)", description, re.I):
                number = {"一":"1","二":"2"}.get(match[1],match[1])
                text = match[2]
                action = "keep" if re.search(r"保留|keep|retain",text,re.I) else "replace" if re.search(r"换|replace",text,re.I) else "add" if re.search(r"新增|增加|加装|add",text,re.I) else ""
                slots[number] = {"action":action,"capacity":capacity(text),"text":text}
            if uncertain:
                confirm.append(say("此 SKU 的 SSD 盘位与尺寸待核，请查内部 BOM 或准确产品资料。","SSD slot and dimensions need verification for this exact SKU."))
            else:
                actions.append(say("本型号已核 SSD 尺寸 · ","Verified SSD size · ") + dimensions[0])
                if dual:
                    for number in ("1","2"):
                        slot = slots.get(number)
                        if not slot:
                            confirm.append(say("请明确盘"+number+"的目标容量、替换/新增或保留安排。","Specify drive "+number+" capacity and whether to replace, add or retain it."))
                        else:
                            if slot["action"] and slot["capacity"]:
                                actions.append(say("盘"+number+" · ","Drive "+number+" · ")+slot["text"])
                            if not slot["action"]:
                                confirm.append(say("请明确盘"+number+"是替换、新增还是保留。","Specify whether drive "+number+" is replaced, added or retained."))
                            if not slot["capacity"]:
                                confirm.append(say("请明确盘"+number+"的最终容量。","Specify the final capacity of drive "+number+"."))
                    if slots and all(s["action"]=="keep" for s in slots.values()):
                        explicit_grade = True
                elif added or retained:
                    if added:
                        actions.append(say("按新增 SSD 处理，原系统盘保留。","Treat this request as an additional SSD, keeping the system drive."))
                    if not re.search(r"SATA|NVMe|M\.?2|盘[12一二]|slot",description,re.I):
                        confirm.append(say("请明确新增/保留配置的目标盘位或接口。","Specify the target slot or interface for this storage combination."))
                    if not target:
                        confirm.append(say("请明确新增盘的容量。","Specify the added drive capacity."))
                elif upgrade and original and re.search(r"默认.*替换|默认表示.*替换",content):
                    if target:
                        actions.append(say("用 "+target+" M.2 NVMe 替换标配 "+original+" 系统盘。","Replace the standard "+original+" M.2 NVMe system drive with "+target+"."))
                    else:
                        confirm.append(say("请明确升级后的系统盘容量。","Specify the upgraded system-drive capacity."))
                    if "SATA" in content:
                        actions.append(say("可选 SATA 数据盘位单独处理。","Optional SATA data-drive bays are handled separately."))
                else:
                    if not relation:
                        confirm.append(say("请明确本次 SSD 是替换还是新增。","Specify whether this SSD replaces a drive or is added."))
                    if not target:
                        confirm.append(say("请明确目标容量。","Specify the target capacity."))
                if not explicit_grade:
                    confirm.append(say("请明确商业级或工业级；已给物料但未注明等级时仍需核对。","Confirm commercial or industrial grade; an item code alone may not specify it."))
            candidates = []
            if target and not uncertain and not (added and re.search(r"SATA",description,re.I)):
                for candidate in self.products.values():
                    if candidate["eol"] or candidate["sku"] == sku:
                        continue
                    names = candidate["names"] or [candidate["name"]]
                    identity = [r for r in candidate["records"] if r["kind"]=="identity"]
                    for row in identity:
                        name = row.get("productName","")
                        if not (re.search(r"SSD|固态",name,re.I) and re.search(r"NVMe",name,re.I)):
                            continue
                        if dimensions[0] not in re.findall(r"(?<!\d)(2242|2280)(?!\d)",name) or capacity(name) != target:
                            continue
                        grade = "industrial" if re.search(r"工规|工业级|industrial",name,re.I) else "commercial" if re.search(r"商规|商业级|commercial",name,re.I) else "unconfirmed"
                        if required_grade and grade not in {required_grade,"unconfirmed"}:
                            continue
                        official = getattr(self,"public_by_sku",{}).get(candidate["sku"],{})
                        candidates.append({"sku":candidate["sku"],"name":name,"url":official.get("url",""),
                                           "capacity":target,"size":dimensions[0],"grade":grade,
                                           "gradeStatus":"unconfirmed" if grade=="unconfirmed" else "meets" if required_grade==grade else "specified",
                                           "sourceId":row["sourceId"],"location":row["location"],"version":row["version"]})
                        break
            unknown_grade = [c["sku"] for c in candidates if c["grade"]=="unconfirmed"]
            if required_grade and unknown_grade:
                label = say("工业级","industrial grade") if required_grade=="industrial" else say("商业级","commercial grade")
                confirm.append(say("候选 "+", ".join(unknown_grade)+" 的"+label+"资格尚待核实。","The requested "+label+" is unconfirmed for candidates "+", ".join(unknown_grade)+"."))
            if product["eol"]:
                confirm.append(say("此产品有内部 EOL 通知，请确认库存及本次项目的使用安排。","This product has an internal EOL notice. Confirm stock and intended use."))
            results.append({"sku":sku,"name":product["name"],"actions":actions,"confirmations":confirm,
                            "candidates":candidates[:12],"action":relation or "replace",
                            "replacementSku":selected[0]["sku"] if len(selected)==1 else "",
                            "replacementNote":say("规格候选需由项目经理确认后加入需求，接口相同不足以证明兼容。","Specification candidates require selection and compatibility confirmation."),
                            "records":rows,"version":self.data.get("version","")})
        return results
