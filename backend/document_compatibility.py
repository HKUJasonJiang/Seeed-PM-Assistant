"""Model-scoped manufacturer compatibility tables and supported-store-product links."""
import re
from lxml import html
from .document_enrichment import canonical, html_rows

BLUE="https://wiki.seeedstudio.com/BeagleBone_Blue/"
WIFI="https://wiki.seeedstudio.com/rtl8822ce_wireless_module_for_jetson/"
NIC="https://www.seeedstudio.com/RTL8822CE-WIFI-Module-p-6313.html"


def wiki_facts(url,raw,source):
    lines=raw.splitlines()
    if url==BLUE and re.search(r"^sku:\s*102990827\s*$",raw,re.M):
        intro=next((i for i,s in enumerate(lines) if s.strip()=="## Grove Compatibility List"),None)
        if intro is None:return {}
        boundary=next((i for i in range(intro+1,len(lines)) if lines[i].startswith("## ")),len(lines))
        if not any("the Grove modules that work well with BeagleBone® Blue" in s for s in lines[intro:boundary]):return {}
        start=next((i for i in range(intro,boundary) if "<table " in lines[i]),None)
        end=next((i for i in range(start+1,boundary) if "</table>" in lines[i]),None) if start is not None else None
        if end is None:return {}
        rows=html_rows(html.fromstring("\n".join(lines[start:end+1])),with_lines=True)
        if not rows or rows[0][0]!=["SKU","Item","I/O type","Working Voltage"]:return {}
        grouped={}
        for cells,relative in rows[1:]:
            if len(cells)!=4 or not re.fullmatch(r"[1-9]\d{8}",cells[0]) or not cells[1].startswith("Grove"):continue
            sku,name,interface,voltage=cells
            if interface not in {"Analog","Digital","I2C","UART"} or voltage not in {"3.3V","Can work on 1.8V"}:continue
            cite=source+"#L"+str(start+relative)
            fact=grouped.setdefault(sku,{"kind":"accessory","sku":sku,"publishedSku":sku,"name":name,"scope":"sku",
                                         "basis":"published_board_compatibility_matrix","source":cite,"compatibilityDetails":[]})
            detail={"interface":interface,"voltage":voltage,"source":cite}
            if name==fact["name"] and detail not in fact["compatibilityDetails"]:fact["compatibilityDetails"].append(detail)
        return {"compatibilityRows":list(grouped.values())}
    if url==WIFI and re.search(r"^sku:\s*114993556\s*,\s*E24121001\s*$",raw,re.M) and NIC in raw:
        section=False;links=[]
        for n,line in enumerate(lines,1):
            if line.startswith("## "):
                section=line.strip()=="## Supported Devices"
                continue
            if section:
                m=re.fullmatch(r"- \[(reComputer J\d{4})\]\((https://www\.seeedstudio\.com/[^)]+-p-\d+\.html)\)",line.strip())
                if m:links.append({"name":m[1],"storeUrl":m[2],"source":source+"#L"+str(n)})
        return {"supportedStoreProducts":links}
    return {}


def card_hosts(record,by_sku):
    card=by_sku.get("114993556",{})
    if canonical(card.get("url",""))!=NIC or "rtl8822ce wireless nic" not in card.get("name","").lower():return {}
    targets={}
    for item in record.get("supportedStoreProducts",[]):
        named=[p for p in by_sku.values() if p.get("url")==item["storeUrl"] and p.get("name","").startswith(item["name"]+" (w/o power adapter)")]
        if len(named)==1:
            targets[named[0]["sku"]]=[{"kind":"accessory","sku":"114993556","name":"RTL8822CE Wireless NIC","scope":"sku",
                                       "basis":"published_card_supported_host_store_url","source":item["source"],"storeProductSource":NIC}]
    return targets


def legacy_wiki_rows(product,record):
    """The shop and its officially redirected Wiki each identify these items."""
    final=record.get("finalUrl","")
    if (final=="https://wiki.seeedstudio.com/Small_e-Paper_Shield/" and product.get("sku")=="104030012"
            and product.get("name","").lower()=="small e-paper shield" and re.search(r"-p-1597\.html$",product.get("url",""))):
        statement=next((s for s in record.get("statements",[]) if "e-paper is not included in this product" in s.get("text","")
                        and "2.0 inch and 2.7 inch" in s["text"]),None)
        if not statement:return []
        source=final+"#:~:text=e-paper%20is%20not%20included%20in%20this%20product"
        return [{"kind":"exclusion","name":"E-paper display panel","basis":"reviewed_shield_exclusion","scope":"sku","source":source}]+[
            {"kind":"accessory","name":size+" e-paper display panel","namedAccessory":True,"basis":"published_shield_panel_sizes",
             "scope":"sku","source":source,"notIncludedSource":source} for size in ("2.0-inch","2.7-inch")]
    if (final=="https://wiki.seeedstudio.com/Mini_Soldering_Iron/" and product.get("sku")=="110060222"
            and product.get("name")=="Mini Soldering Iron Deluxe Kit (Europe Standard)"):
        # Only match the eight items found independently in the European
        # retail list and the Wiki shared with the US kit.
        aliases={"mini soldering iron (main part)":"Mini Soldering Iron Operating Part","pcb soldering kit":"PCB soldering kit",
                 "soldering iron tip type-bc2":"Soldering Iron Tip Type-BC2","soldering iron tip type-b2":"Soldering Tron Tip Type-B2",
                 "soldering iron holder":"Soldering Iron Stand","dc5525 power adapter":"DC5525 Power Adapter",
                 "earth clamps":"Earth Clamps","manual":"User Manual"}
        present={row[0] for row in product.get("parts",[]) if len(row)>1 and str(row[1]).strip("x× ")=="1"}
        return [{"kind":"inbox","name":aliases[r["name"].lower()],"documentItem":r["name"],"quantity":"1","basis":"retail_item_and_shared_wiki",
                 "scope":"sku","source":r["source"],"storeProductSource":product.get("partSource") or product.get("url","")}
                for r in record.get("rows",[]) if r.get("kind")=="inbox" and r.get("quantity")=="1" and
                aliases.get(r.get("name","").lower()) in present and r.get("source")==final+"#parts-list"]
    return []
