"""Attach verified R1000 family evidence without copying another SKU's packing list."""
import re
from urllib.parse import urlsplit


ASSEMBLY = "https://wiki.seeedstudio.com/recomputer_r1000_assembly_guide/"
INTRO = "https://wiki.seeedstudio.com/recomputer_r/"
MANUAL = "https://files.seeedstudio.com/wiki/reComputer-R1000/reComputerR_UserManual_version01.pdf"
EARLIER_MANUAL = "https://files.seeedstudio.com/wiki/reComputer-R1000/reComputer_R1000_uermanual.pdf"
CLIP_SOURCE = ASSEMBLY + "#din-rail-mounting-guide"
WALL_SOURCE = ASSEMBLY + "#wall-mounting-guide"
ACCESSORY_SOURCE = ASSEMBLY + "#accessories-list"
MODELS = {
    "113991295": "R1013-10", "100025879": "R1014-10",
    "113991294": "R1024-10", "113991274": "R1025-10", "100016292": "R1026-10",
    "113991314": "R1035-10", "100011197": "R1036-10",
}

# Product identifiers from the family assembly guide. Procurement names come from the
# local catalogue by exact SKU; the abbreviated descriptions work when a SKU is unlisted.
WIKI_OPTIONS = (
    ("114992969", "LoRa", "WM1302 · SPI · US915"),
    ("114993268", "LoRa", "WM1302 · SPI · EU868"),
    ("114992991", "LoRa", "WM1302 · USB · US915"),
    ("114992628", "LoRa", "WM1302 · USB · EU868"),
    ("110061501", "LoRa antenna", "868–915 MHz antenna"),
    ("114992364", "Wi-Fi / BLE antenna", "CM4 antenna kit"),
    ("113991134", "LTE Cat 4", "EC25-AFXGA · North America"),
    ("113991135", "LTE Cat 4", "EC25-EUXGR · EMEA / Thailand"),
    ("113991174", "LTE Cat 4", "EC25-AUXGR · Australia"),
    ("113991214", "LTE Cat 4", "EC25-EFA · Thailand"),
    ("113991234", "LTE Cat 4", "EC25-EMGA · Malaysia"),
    ("113991296", "LTE Cat 4", "EC25-JFA"),
    ("110061502", "4G antenna", "LTE antenna kit"),
    ("110061521", "GNSS antenna", "EC25 GPS antenna"),
    ("110992004", "UPS", "LTC3350 supercapacitor module"),
    ("114993114", "TPM 2.0", "Infineon SLB9670"),
    ("112990267", "NVMe storage", "M.2 2280 · 1 TB"),
    ("112990247", "NVMe storage", "M.2 2280 · 512 GB"),
    ("112990246", "NVMe storage", "M.2 2280 · 256 GB"),
    ("112990226", "NVMe storage", "M.2 2280 · 128 GB"),
    ("110991925", "PoE", "MQ7813T120 PoE module"),
    ("110061505", "Power adapter", "12 V adapter · US plug"),
    ("110061506", "Power adapter", "12 V adapter · EU plug"),
)
MANUAL_OPTIONS = (
    ("110992005", "Zigbee", "Mini-PCIe USB Zigbee module"),
    ("110061641", "Zigbee antenna", "External antenna for reComputer R"),
)
WIKI_FACTS = (
    (INTRO + "#rich-interfaces", "R1000 系列有三路隔离 RS485。",
     "R1000 provides three isolated RS485 interfaces."),
    (INTRO + "#rich-wireless-capabilities",
     "USB LoRa 可用 Mini-PCIe 1 或 2，SPI LoRa 使用插槽 2。",
     "USB LoRa fits either Mini-PCIe slot; SPI LoRa uses slot 2."),
    (CLIP_SOURCE, "导轨卡扣与安装螺丝随箱提供；该章节未给出数量。",
     "The mounting clip and screws for DIN rail installation are supplied; this section gives no piece count."),
    (WALL_SOURCE, "壁挂安装需另外采购支架。", "Order wall-mount brackets separately for wall installation."),
    (ASSEMBLY, "R1000 系列提供 Logo、包装、标签、固件烧录及镜像写入服务。",
     "Branding, packaging, labeling, firmware flashing and imaging are available at family level."),
)


def _applies(product):
    title = product.get("name", "")
    model = re.match(r"^reComputer\s+(R10\d\d-10)\b", title, re.I)
    if not model or re.search(r"\b(kit|bundle|accessory|accessories|enclosure only)\b", title, re.I):
        return False
    identified = model[1].upper()
    sku = product.get("sku", "")
    if sku in MODELS:
        return MODELS[sku] == identified
    # A future standalone R10xx-10 unit also needs the official R1000 manual explicitly
    # linked from its own shop page before accepting these family-level facts.
    url = product.get("url") or ""
    links_manual = any(d.get("url", "").split("#")[0] in {MANUAL, EARLIER_MANUAL}
                       for d in product.get("docs", []))
    return urlsplit(url).hostname == "www.seeedstudio.com" and links_manual


def _title_specs(product):
    """The seven audited titles identify their fixed SKU configuration after the pipe."""
    model = MODELS[product["sku"]]
    heading, _, capacity = product.get("name", "").rpartition("|")
    url = product.get("url") or ""
    page = urlsplit(url)
    if page.scheme != "https" or page.hostname != "www.seeedstudio.com":
        return []
    if not re.fullmatch(rf"/reComputer-{model}-p-\d+\.html", page.path, re.I):
        return []
    if re.findall(r"\bR\d{4}-\d{2}\b", heading.upper()) != [model]:
        return []
    if re.search(r"\b(?:up to|max(?:imum)?|optional|options?|variants?|configurations?|choose|select)\b|\d\s*(?:GB|TB)\b", heading, re.I):
        return []
    pair = re.fullmatch(r"\s*([1-9]\d*)\s*GB\s+RAM\s*,\s*([1-9]\d*)\s*GB\s+eMMC\s*", capacity, re.I)
    if not pair:
        return []
    return [{"name": "RAM", "value": f"{pair[1]}GB", "source": url},
            {"name": "Storage", "value": f"{pair[2]}GB eMMC", "source": url}]


def _add_box_contents(product, resistor_source):
    rows = product.setdefault("parts", [])
    sources = product.setdefault("partSources", {})
    scopes = product.setdefault("partScopes", {})
    product.setdefault("storePartStatus", product.get("partStatus") or ("present" if rows else "unread"))
    additions = (
        ("DIN-rail clip", "", CLIP_SOURCE, r"din[-\s]*rail.*(?:clip|clamp|bracket)"),
        ("DIN-rail installation screws", "", CLIP_SOURCE, r"screw\s*pack|(?:mounting|installation).*screw"),
        ("120 Ω RS485 termination resistor", "5", resistor_source, r"120\s*(?:Ω|ohm).*resistor|resistor.*120"),
    )
    for name, quantity, url, equivalent in additions:
        if any(re.search(equivalent, str(row[0]), re.I) for row in rows if row):
            continue
        rows.append([name, quantity])
        sources[name] = url
        scopes[name] = "family"
    family_count = sum(scopes.get(row[0]) == "family" for row in rows)
    if family_count:
        product["partEvidenceScope"] = "family" if family_count == len(rows) else "mixed"
    product["partStatus"] = "present"


def enrich_r1000(product, by_sku=None):
    """Merge only facts supported by R1000 sources; keep SKU-specific contents and quantities."""
    applies = _applies(product)
    if product.get("sku") in MODELS:
        if applies:
            product["modelSpecs"] = _title_specs(product)
        elif "modelSpecs" in product:
            product["modelSpecs"] = []
    if not applies:
        return product
    current_manual = any(d.get("url", "").split("#")[0] == MANUAL for d in product.get("docs", []))
    manual = MANUAL if current_manual else EARLIER_MANUAL
    # Physical page 18 addresses the five resistors in both editions. The Zigbee table
    # starts on physical page 48 (printed 44) in version01 and 44 (printed 40) earlier.
    _add_box_contents(product, manual + "#page=18")
    manual_page = 48 if current_manual else 44
    options = product.setdefault("accessories", [])
    existing = {a.get("sku"): a for a in options}
    desktop_catalog = by_sku or {}
    for entries, url in ((WIKI_OPTIONS, ACCESSORY_SOURCE),
                         (MANUAL_OPTIONS, manual + "#page=" + str(manual_page))):
        for sku, category, description in entries:
            item = existing.get(sku)
            if item and item.get("scope") != "R1000" and "Also Add" not in item.get("type", ""):
                continue
            if not item:
                item = {}
                options.append(item)
            item.update(sku=sku, type=category, name=description, source=url, scope="R1000")
            target = desktop_catalog.get(sku)
            if isinstance(target, dict) and target.get("name"):
                item["storeName"] = target["name"]
            existing[sku] = item
    if not product.get("custom"):
        product["custom"] = "Logo、包装、标签、固件烧录（R 系列）"
        product["customUrl"] = ASSEMBLY
    notes = product.setdefault("notes", [])
    for text, url in (("壁挂支架需另购。", WALL_SOURCE),
                      ("4G and LoRa modules are sold separately.", INTRO + "#safety-and-reliability")):
        if not any(n.get("source") == url and n.get("text") == text for n in notes):
            notes.append({"kind": "另购说明", "text": text, "source": url, "scope": "R1000"})
    previous = product.get("missingSummary", [])
    product["missingSummary"] = list(dict.fromkeys([*previous, "壁挂支架", "4G / LoRa modules"]))
    facts = product.setdefault("wikiEvidence", [])
    known = {f.get("url") for f in facts}
    for url, zh, en in WIKI_FACTS:
        if url not in known:
            facts.append({"url": url, "title": "reComputer R1000", "scope": "R1000",
                          "zh": zh, "en": en, "checked": "2026-11-08"})
    documents = product.setdefault("docs", [])
    if not any(d.get("url") == manual for d in documents):
        documents.append({"name": "reComputer R1000 User Manual", "url": manual})
    return product
