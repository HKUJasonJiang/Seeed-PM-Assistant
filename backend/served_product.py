"""Read only the public data already embedded in a rendered storefront product page."""
import json
import re

from .storage import Problem


def flight_rows(scripts):
    fragments = []
    for script in scripts:
        text = (script.text or "").strip()
        match = re.fullmatch(r"self\.__next_f\.push\((\[.*\])\);?", text, re.S)
        if not match:
            continue
        try:
            entry = json.loads(match[1])
        except ValueError:
            continue
        if len(entry) == 2 and entry[0] == 1 and isinstance(entry[1], str):
            fragments.append(entry[1])
    stream = "".join(fragments).encode("utf8")
    documents, texts = [], {}
    start = 0
    header = re.compile(rb"([0-9a-f]+):")
    text_header = re.compile(rb"T([0-9a-f]+),")
    while start < len(stream):
        if stream[start:start+1] in (b"\n", b"\r"):
            start += 1
            continue
        if stream[start:start+1] == b":":
            end = stream.find(b"\n", start)
            if end < 0:
                break
            start = end + 1
            continue
        match = header.match(stream, start)
        if not match:
            break
        row = match[1].decode()
        start = match.end()
        payload = text_header.match(stream, start)
        if payload:
            # The publisher counts bytes, including multibyte text and line breaks.
            end = payload.end() + int(payload[1], 16)
            if end > len(stream):
                break
            try:
                texts[row] = stream[payload.end():end].decode("utf8")
            except UnicodeError:
                break
            start = end
            continue
        end = stream.find(b"\n", start)
        if end < 0:
            end = len(stream)
        value = stream[start:end]
        if value.startswith((b"[", b"{")):
            try:
                documents.append(json.loads(value))
            except (ValueError, UnicodeError):
                pass
        start = end + 1
    return documents, texts


def product_props(node):
    if isinstance(node, dict):
        product = node.get("product")
        if "deviceType" in node and isinstance(product, dict) and product.get("id") and product.get("sku") and product.get("name"):
            yield product
            return
        children = node.values()
    elif isinstance(node, list):
        children = node
    else:
        return
    for child in children:
        yield from product_props(child)


def embedded_sections(root, sku):
    from .storefront import DETAIL_FIELDS, DetailIdentity
    published = set()
    for script in root.xpath('//script[@type="application/ld+json"]'):
        try:
            data = json.loads(script.text or "")
        except ValueError:
            continue
        if isinstance(data, dict) and data.get("@type") == "Product" and isinstance(data.get("sku"), str):
            published.add(data["sku"].strip())
    if not published:
        for el in root.xpath('//*[text()[normalize-space()="SKU"]]'):
            label = " ".join(" ".join(el.itertext()).split())
            match = re.fullmatch(r"SKU\s*:?\s+([\w.-]{1,55})", label, re.I)
            if match:
                published.add(match[1])
    if {v.casefold() for v in published} != {sku.casefold()}:
        raise DetailIdentity("different_displayed_sku" if published else "no_displayed_sku", published)
    blocks, texts = flight_rows(root.xpath("//script[not(@src)]"))
    records = [p for block in blocks for p in product_props(block)]
    if not records:
        raise Problem("DETAIL_LAYOUT_UNKNOWN", 502)
    if {str(p["sku"]).casefold() for p in records} != {sku.casefold()}:
        raise DetailIdentity("different_displayed_sku", [p["sku"] for p in records])
    ids = {str(p["id"]) for p in records}
    if len(ids) != 1:
        raise DetailIdentity("multiple_product_ids", ids, "displayedStoreIds")
    product = records[0]
    section = {"_verifiedStoreId": str(product["id"]), "_pageTemplate": "storefront_app"}

    def decoded(value):
        if isinstance(value, str):
            if value.startswith("$$"):
                return value[1:]
            marker = re.fullmatch(r"\$([0-9a-f]+)", value)
            if marker:
                return texts[marker[1]]
            if value.startswith("$"):
                raise KeyError("unresolved reference")
        if isinstance(value, list):
            return [decoded(v) for v in value]
        if isinstance(value, dict):
            return {k: decoded(v) for k, v in value.items()}
        return value

    for key in DETAIL_FIELDS:
        if key in product:
            try:
                section[key] = decoded(product[key])
            except KeyError:
                pass  # An unresolved section remains unread.
    stage = product.get("product_stage")
    if isinstance(stage, str) and re.fullmatch(r"[\w -]{1,40}", stage):
        section["_storeLifecycle"] = stage.strip()
    elif "product_stage" in product and stage in (None, ""):
        section["_storeLifecycle"] = ""
    return section
