"""Merge document audit metadata and unambiguous evidence into an in-memory catalogue."""
from __future__ import annotations

import collections
import hashlib
import json
from pathlib import Path
import re
import time
import unicodedata
from urllib.parse import quote, unquote, urlsplit
from .document_enrichment import EDGELOGIX_GUIDE, canonical, github_file, inventory, kind, load_catalog, point_type, publisher_source
from .storage import write as atomic_write
from . import document_product_tables as tables
from . import document_sheet
from . import document_variant_tables as variants
from .document_scope import reconcile, request_receipts
from . import document_compatibility as compatibility
from .document_reviewed import (BATTERY_BOM, REVIEWED_TABLES, SENSECAP_V13, FULL_KITS, CORD_EXCLUDED, S2100_PDF,
                               DSO_MANUAL, DSO_REPO_MANUAL, WIO_MANUAL, R1000_FLYER, J2032_PDF, J1020_DATASHEET, ZIMA_MANUAL,
                               BLIKVM_PCIE, ECOEYE, JETSON_BOX, other_visual_rows, reviewed_current,
                               reviewed_rows, is_reviewed_wiki_box, sensecap_common_box, exact_model_rows, checked_wiki_rows, checked_wiki_conflicts, supplementary_wiki_scope)


# These two tables use the ambiguous heading “Part(s) List”. Their published
# contents and the named standalone product or kit have been reviewed together.
VERIFIED_BOX = {
    "110060482":"https://wiki.seeedstudio.com/Grove_Starter_Kit_for_IoT_based_on_Raspberry_Pi/#part-list",
    "102110018":"https://wiki.seeedstudio.com/LinkIt_Smart_7688/#parts-list",
}
RF_LOOP_PDF = "https://statics3.seeedstudio.com/assets/file/bazaar/product/RFExplorerRFEAH_25datasheet.pdf"
EDGELOGIX_RAM={"102110779":"2GB","102991734":"4GB","102110773":"8GB"}
ROHS_REGISTER_DIGEST="bd53e2c6c280777873de316d2525c0c32bb7dfa7425918fc6bc4917096ec5662"


def edgelogix_facts(sku):
    source=EDGELOGIX_GUIDE+"#page=17"
    return [{"kind":"modelSpec","name":name,"value":value,"scope":"sku","source":source,"basis":"printed_sku_configuration"}
            for name,value in (("RAM",EDGELOGIX_RAM[sku]),("Storage","32GB eMMC"))]+[
        {"kind":"expansion","name":"4G/LTE module · 1 mini-PCIe socket with SIM","scope":"family","source":source,"basis":"EdgeLogix-RPI-1000"},
        {"kind":"expansion","name":"LoRaWAN module · 1 mini-PCIe socket","scope":"family","source":source,"basis":"EdgeLogix-RPI-1000"},
        {"kind":"exclusion","name":"4G and LoRaWAN modules","scope":"family","source":source,"basis":"EdgeLogix-RPI-1000"}]


def log_records(folder):
    path=Path(folder)/"document-checks.jsonl"
    result={}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                record=json.loads(line)
                old=result.get(record["url"],{})
                changed=old.get("sha256") and record.get("sha256") and old["sha256"]!=record["sha256"]
                if changed:
                    record["previousEdition"]={"sha256":old["sha256"],"status":old.get("status"),"checkedAt":old.get("checkedAt","")}
                if not changed and old.get("status") in {"parsed","empty"} and record.get("status") in {"failed","unread"}:
                    result[record["url"]]={**old,"lastAttempt":{"status":record["status"],"reason":record.get("reason",""),
                                                               "checkedAt":record.get("checkedAt","")}}
                else:result[record["url"]]=record
            except (ValueError,KeyError):
                continue
    offline=Path(folder)/"wiki-offline-checks.json"
    if offline.is_file():
        for url,md in json.loads(offline.read_text(encoding="utf-8")).items():
            prior=result.get(url,{})
            if md.get("linkOnly") and prior.get("status") in {"parsed","empty"}:
                result[url]={**prior,"markdownSource":md["markdownSource"],
                             "linkedPdfs":{**prior.get("linkedPdfs",{}),**md.get("linkedPdfs",{})},
                             "linkedSheets":{**prior.get("linkedSheets",{}),**md.get("linkedSheets",{})}}
                continue
            if md.get("serviceParagraphOnly") and prior.get("status") in {"parsed","empty"}:
                # Independently reading the service paragraph must not change a
                # live guide's product identity or replace its full article.
                result[url]={**prior,"status":"parsed","serviceEvidence":md["serviceEvidence"],
                             "serviceParagraphOnly":True,"markdownSource":md["markdownSource"]}
                continue
            base=dict(prior if prior.get("status") in ("parsed","empty") else md)
            if prior.get("status") in {"failed","unread"}:
                base["lastAttempt"]={"status":prior["status"],"reason":prior.get("reason",""),"checkedAt":prior.get("checkedAt","")}
            for key in ("rows","statements"):
                values=list(base.get(key,[]))
                seen={(r["kind"],r.get("sku") or r.get("publishedSku") or r.get("name") or r.get("text"),r.get("quantity")) for r in values}
                for row in md.get(key,[]):
                    identity=(row["kind"],row.get("sku") or row.get("publishedSku") or row.get("name") or row.get("text"),row.get("quantity"))
                    if identity not in seen:values.append(row);seen.add(identity)
                base[key]=values
            for section in md.get("sections",[]):
                if section not in base.setdefault("sections",[]):base["sections"].append(section)
            base.update(linkedPdfs={**prior.get("linkedPdfs",{}),**md.get("linkedPdfs",{})},purchaseSkus=md["purchaseSkus"],
                        linkedSheets={**prior.get("linkedSheets",{}),**md.get("linkedSheets",{})},
                        declaredSkus=md.get("declaredSkus",[]),declaresMultiple=md.get("declaresMultiple",False),
                        sourceScopes=md.get("sourceScopes",[]),markdownSource=md["markdownSource"])
            if md.get("serviceEvidence"):base["serviceEvidence"]=md["serviceEvidence"]
            for key in ("compatibilityRows","supportedStoreProducts"):
                if md.get(key):base[key]=md[key]
            if md.get("serviceParagraphOnly"):base["serviceParagraphOnly"]=True
            base["status"]="parsed" if base["rows"] or base["statements"] or base.get("serviceEvidence") else "empty"
            result[url]=base
    ocr_path=Path(folder)/"document-ocr.jsonl"
    if ocr_path.is_file():
        direct={};by_content={}
        for line in ocr_path.read_text(encoding="utf-8").splitlines():
            try:data=json.loads(line)
            except ValueError:continue
            direct[data["url"]]=data
            if data.get("sha256") and data["status"] in {"candidate_review","no_target_found","partial_or_unreadable"}:
                by_content[data["sha256"]]=data
        for url,r in result.items():
            if r.get("reason")!="no_text_layer":continue
            data=direct.get(url)
            if data and data.get("sha256") and r.get("sha256") and data["sha256"]!=r["sha256"]:data=None
            if not data:data=by_content.get(r.get("sha256"))
            if not data:continue
            if data["url"]!=url:r["ocrSameBytesAs"]=data["url"]
            if data.get("sha256") and not r.get("sha256") and data["url"]==url:
                r["sha256"]=data["sha256"]
            r["ocrStatus"]=data["status"];r["ocrPagesWithText"]=data.get("pagesWithText",0)
            if data.get("candidates"):r["ocrSections"]=[{"page":c["page"],"heading":c["heading"]} for c in data["candidates"] if c.get("page") and c.get("heading")][:24]
            if data.get("pages"):r["pages"]=data["pages"]
            # The signed 45-page declaration indexes products independently.
            # On physical page 12 the word "accessory" belongs to the name of
            # the Coral PCI-E product. It does not link that SKU to a host.
            if (data.get("sha256")==ROHS_REGISTER_DIGEST and data.get("pages")==45 and data.get("pagesWithText")==45
                    and data["status"]=="candidate_review" and {c.get("page") for c in data.get("candidates",[])}=={12}):
                r.update(status="empty",ocrStatus="no_target_found",ocrReview="compliance_product_register")
                r.pop("reason",None)
            elif data["status"]=="no_target_found":
                r.update(status="empty");r.pop("reason",None)
            elif data["status"]=="candidate_review":r.update(status="unread",reason="ocr_candidate_needs_review")
            elif data["status"]=="partial_or_unreadable":r["reason"]="ocr_partial"
    return result


def candidate_section_links(url,record):
    """A heading gives reviewers a place to look without asserting anything is supplied."""
    result=[];seen=set()
    for section in [*record.get("sections",[]),*record.get("ocrSections",[])]:
        if isinstance(section,str):
            heading=unquote(section).replace("-"," ").replace("_"," ")
            role=point_type(heading)
            entry={"kind":role,"heading":heading,"url":(record.get("finalUrl") or url)+"#"+quote(section)}
        elif isinstance(section,dict):
            heading=str(section.get("heading") or section.get("title") or "")[:120]
            role=section.get("kind") or point_type(heading)
            page=section.get("page")
            if isinstance(page,int) and 1<=page<=record.get("pages",0):
                entry={"kind":role,"page":page,"url":(record.get("finalUrl") or url)+"#page="+str(page)}
                if heading:entry["heading"]=heading
            elif isinstance(section.get("line"),int) and section["line"]>0 and record.get("markdownSource"):
                entry={"kind":role,"heading":heading,"url":record["markdownSource"]+"#L"+str(section["line"])}
            else:continue
        else:continue
        if role not in ("inbox","accessory") or entry["url"] in seen:continue
        result.append(entry);seen.add(entry["url"])
        if len(result)>=8:break
    return result


def aggregate_links(catalog, records, additional=None):
    sources=inventory(catalog)
    if additional:
        for url,b in inventory(additional).items():
            a=sources.setdefault(url,b)
            a["skus"].update(b["skus"]);a["labels"].update(b["labels"])
            for relation in ("explicitStore","purchases","declared"):
                a.setdefault(relation,set()).update(b.get(relation,set()))
    for source in sources.values():
        source["direct"]=set(source.get("explicitStore",set()))
        source["via"]=set()
    for url,r in records.items():
        if not r.get("purchaseSkus") and not r.get("declaredSkus"):continue
        group=sources.setdefault(url,{"kind":"wiki","labels":set(),"skus":set(),"direct":set(),"via":set()})
        group.setdefault("purchases",set()).update(r.get("purchaseSkus",[]))
        group.setdefault("declared",set()).update(r.get("declaredSkus",[]))
        group["skus"].update(group["purchases"]|group["declared"])
    for url,record in records.items():
        if url not in sources or record.get("kind")!="wiki":continue
        sku_set=sources[url]["skus"]
        for target,label in {**record.get("linkedPdfs",{}),**record.get("linkedSheets",{})}.items():
            item=sources.setdefault(target,{"kind":kind(target),"labels":set(),"skus":set(),"direct":set(),"via":set()})
            item["skus"].update(sku_set)
            item["via"].add(url)
            if label:item["labels"].add(label)
    # A family services statement does not establish ownership of PDFs linked
    # from other sections of the same multi-product page.
    for url,record in records.items():
        service=record.get("serviceEvidence")
        if service:
            item=sources.setdefault(url,{"kind":"wiki","labels":set(),"skus":set(),"direct":set(),"via":set()})
            item.setdefault("serviceSkus",set()).update(service["skus"])
            item["skus"].update(service["skus"])
    return sources


def words(s):
    return " ".join(re.findall(r"[a-z0-9]+",str(s).lower()))


def identity(p,url,record,link):
    title=words(record.get("title",""))
    stem=unquote(urlsplit(url).path).lower()
    if re.search(r"/(?:seeed_certificate|documents_certificate)/",stem):return None
    if {"application","multi_sku","component_guide","link_only"}.intersection(record.get("sourceScopes",[])):return None
    scopes={str(e.get("scope","")).lower() for e in p.get("wikiEvidence",[])}
    if "r1000" in scopes and (
        stem.strip("/") in {"recomputer_r","recomputer_r1000_assembly_guide"}
        or stem in {"/wiki/recomputer-r1000/recomputerr_usermanual_version01.pdf","/wiki/recomputer-r1000/recomputer_r1000_uermanual.pdf"}):
        return "family","R1000"
    if "r1100" in scopes and (
        stem.strip("/")=="recomputer_r1100_intro" or stem=="/r11/recomputer r1100 user manual-v1.0.pdf"):
        return "family","R1100"
    own_purchase=record.get("purchaseSkus")==[p["sku"]]
    declared=record.get("declaredSkus",[])
    owns_declaration=declared==[p["sku"]] and not record.get("declaresMultiple")
    if declared and (len(declared)>1 or record.get("declaresMultiple")):return None
    if p["sku"] not in link["direct"] and not own_purchase and not owns_declaration:return None
    if (p["sku"]=="110060762" and words(p.get("name",""))=="grove inventor kit for micro bit"
        and url=="https://wiki.seeedstudio.com/Grove_Inventor_Kit_for_microbit/" and title.replace(" ","")==words(p["name"]).replace(" ","")):
        return "sku","reviewed_store_model_and_wiki_kit_table"
    if p["sku"]=="114990711" and url==RF_LOOP_PDF and "rfeah 25" in title and "rfean25" in words(p.get("name","")):
        # This store listing spells the model RFEAN25 in its title. The official
        # product description names RFEAH-25 and links this particular datasheet.
        return "sku","linked_datasheet_and_store_model"
    cover_ids=set(record.get("identitySkus",[]))
    if cover_ids:return ("sku","document_sku") if cover_ids=={p["sku"]} else None
    if not title or re.search(r"\b(?:series|comparison|selection|kit series|course|examples?)\b",title):return None
    short=words(re.sub(r"^(?:(?:getting started (?:with )?|introduction to |quick start for )+)", "",title))
    short=re.sub(r"\s+(?:getting started|user manual|user guide|datasheet|wiki)$","",short)
    if (own_purchase or owns_declaration) and not re.search(r"\b(tutorial|project|demo|example|application|how to|expanding|connecting|installing|benchmark|compared)\b",short):
        return "sku","declared_product_sku_and_title" if owns_declaration else "verified_product_purchase_and_title"
    name=p.get("name","")
    precise={words(name),words(name.split("|",1)[0])}
    short_name=re.split(r"\s+[-–—]\s+|,\s*",name,maxsplit=1)[0]
    if len(words(short_name).split())>=3 and len(words(short_name))>12:precise.add(words(short_name))
    if len(short.split())<2 or len(short)<9 or short not in precise:return None
    # A shared guide can cover many versions; an exact personal buy link can disambiguate.
    store_id=p.get("storeId")
    buys=record.get("purchaseUrls",[])
    same_buy=canonical(p.get("url","")) in buys or any(store_id and re.search(r"-p-"+re.escape(str(store_id))+r"\.html$",a,re.I) for a in buys)
    if len(link["direct"])>1 and not same_buy:return None
    return "sku","linked_title_and_product_url" if same_buy else "unique_link_and_product_title"


def accepted(record, scope, basis, sku):
    candidates=[]
    for raw in record.get("rows",[]):
        if raw.get("kind")=="inbox":
            if (sku=="105990001" and raw["name"].lower()=="mini usb cable" and raw["source"].endswith("AVR_USB_Programmer.md#L40")
                and record.get("url")=="https://wiki.seeedstudio.com/AVR_USB_Programmer/"):
                candidates.append({"kind":"accessory","name":"Mini USB cable","namedAccessory":True,"scope":scope,"basis":"optional_in_guide","source":raw["source"]})
                continue
            anchor=raw["source"].split("#",1)[-1]
            if "page=" in anchor:
                if not any(section.get("page")==int(anchor.split("=")[1]) and section.get("explicitBox")
                           and not re.search(r"\bparts?[\s_-]*list\b",section.get("heading",""),re.I)
                           for section in record.get("sections",[]) if isinstance(section,dict)):continue
            elif raw["source"]!=VERIFIED_BOX.get(sku) and not is_reviewed_wiki_box(sku,record,raw) and not re.search(r"package[-_ ]?contents|in[-_ ]the[-_ ]box|packing[-_ ]list|what.s[-_ ]included|box[-_ ]contents|kit[-_ ]contents|装箱清单|包装清单|包装内容|随箱清单",unquote(raw.get("heading") or anchor),re.I):
                continue
            if re.search(r'get one now|buy now',raw["name"],re.I):continue
            if sku=="103020030" and "no knob included" in raw["name"].lower():
                candidates.append({"kind":"exclusion","name":"Encoder knob","scope":scope,"basis":basis,"source":raw["source"]})
                raw={**raw,"name":re.sub(r"\s*\(no knob included\)","",raw["name"],flags=re.I).strip()}
        elif not raw.get("sku") and not (raw.get("namedAccessory") and (scope=="sku" or raw.get("publishedSku"))):continue
        candidates.append({**raw,"scope":scope,"basis":basis})
    for s in record.get("statements",[]):
        text=s["text"]
        if s["kind"]=="customization" and re.search(r"(?:available customization options|our hardware engineering services include)",text,re.I):
            options=[name for name,rex in [("logo branding",r"logo"),("packaging",r"packag"),("labeling",r"label"),
                ("firmware flashing",r"firmware flash"),("imaging",r"imaging")] if re.search(rex,text,re.I)]
            if options:candidates.append({"kind":"customization","name":", ".join(options),"source":s["source"],"scope":scope,"basis":basis})
        elif s["kind"]=="exclusion":
            text_lower=text.lower()
            name=""
            scoped_phrases={
                "114110168":("support gps (modules not included)",("GPS module",)),
                "110061403":("qc25-eux 4g module is used with the following setup guide and the module does not included",("4G module used in the setup guide",)),
                "113050002":("uartsbee device and the xbeeshield are sold separately",("UartSBee","XbeeShield")),
                "109990013":("you need a micro sd card to do this (not included)",("MicroSD card",)),
                "103030356":("this product does not include seeed studio xiao and battery",("Seeed Studio XIAO board","Battery")),
                "102010070":("uartsbee v4, mini usb cable and 6pin cable are not included",("UartSBee V4","Mini USB cable","6-pin cable")),
                "102110057":("battery is not included in the package",("Battery",)),
                "110060010":("compatible arduino board not included",("Compatible Arduino board",)),
                "104030019":("e-paper is not included in this product",("ePaper display",)),
            }
            check=scoped_phrases.get(sku)
            if check and check[0] in text_lower:
                candidates.extend({"kind":"exclusion","name":n,"source":s["source"],"scope":scope,"basis":basis} for n in check[1])
                if sku=="103030356" and "does not support the xiao nrf54l15 and xiao mg24" in text_lower:
                    candidates.append({"kind":"modelSpec","name":"XIAO board compatibility","value":"XIAO nRF54L15 and XIAO MG24 are unsupported (SWD pin mapping)",
                                       "source":s["source"],"scope":scope,"basis":basis})
                continue
            if re.search(r"(?:wall|vertical) mount",text_lower) and "bracket" in text_lower:name="Wall-mount brackets"
            elif "4g" in text_lower and "lora" in text_lower and "module" in text_lower:name="4G and LoRa modules"
            elif sku=="110060482" and "does not include the raspberry pi board" in text_lower:name="Raspberry Pi board"
            elif re.search(r"(?:micro\s*sd\s*\(?card|micro\s*sd card)\s*\(?(?:is )?not included",text_lower):name="MicroSD card"
            elif re.search(r"\bsd card is not included in this grove",text_lower):name="SD card"
            elif re.search(r"(?:kit|product) does not include (?:a |the )?battery",text_lower):name="Battery"
            elif re.search(r"(?:board|product) does not include an? (?:eink|epaper) display",text_lower):name="ePaper display"
            elif re.search(r"does not include (?:a seeed studio xiao board|the xiao module)",text_lower):name="Seeed Studio XIAO board"
            elif re.search(r"charge cable\s*\(adapter not included\)",text_lower):name="Charging adapter"
            elif re.search(r"gmsl\s*2 (?:adaptor board|camera connector.*adaptor board) need to be purchased separately",text_lower):name="GMSL2 adapter board"
            elif "gps module is not included in the standard product" in text_lower:name="GPS module"
            elif "nvme ssd is not included in the standard product" in text_lower:name="NVMe SSD"
            elif re.search(r"standard version .*?(?:does not come with a 4g module|does not include a built-in 4g module)",text_lower):name="4G module (standard version)"
            elif "4g/5g module is not included in reserver" in text_lower:name="4G/5G module"
            elif sku=="110061403" and "lorawan® module does not include." in text_lower:name="LoRaWAN module"
            elif re.fullmatch(r"(?:\*|note: )?(?:the )?(?:power (?:adapter|supply)|usb cable|sd card|micro[- ]?sd card|battery|batteries) (?:is |are )?(?:not included|sold separately)[.!]?",text_lower):
                name=re.split(r"\s+(?:is |are )?(?:not included|sold separately)",text,flags=re.I)[0].strip("* ")
            if name:candidates.append({"kind":"exclusion","name":name,"source":s["source"],"scope":scope,"basis":basis})
    return candidates


def preverified_pdf_rows(product, url, record, docs):
    """An established SKU-level relation is retained only when its exact cited page still shows the accessory SKU."""
    result=[]
    for existing in product.get("accessories",[]):
        doc=existing.get("doc")
        page=existing.get("page") if doc in docs and canonical(docs[doc]["url"])==url else None
        if not page and canonical(existing.get("source",""))==url:
            fragment=re.fullmatch(r"page=(\d+)",urlsplit(existing["source"]).fragment)
            if fragment:page=int(fragment[1])
        sku=existing.get("sku")
        if not page or not sku or sku not in record.get("pageSkus",{}).get(str(page),[]):continue
        scope="family" if doc in ("r10","r11") or existing.get("scope","").casefold() in {"r1000","r1100","family"} else "sku"
        result.append({"kind":"accessory","sku":sku,"name":existing.get("storeName") or existing["name"],
                       "source":url+"#page="+str(page),"scope":scope,"basis":"reviewed_manual_row_and_page_sku"})
    return result


def audit(catalog,folder,additional=None):
    records=log_records(folder);sources=aggregate_links(catalog,records,additional)
    by_sku={p["sku"]:p for p in catalog["products"]}
    by_store_id=collections.defaultdict(set)
    for p in catalog["products"]:
        store_id=p.get("storeId")
        if not store_id:
            match=re.search(r"-p-(\d+)\.html$",urlsplit(p.get("url") or "").path,re.I)
            if match:store_id=match[1]
        if store_id:by_store_id[str(store_id)].add(p["sku"])
    if additional:
        for new in additional.get("products",[]):
            if new["sku"] not in by_sku:by_sku[new["sku"]]={**new,"url":new.get("productUrl") or new.get("url","")}
    per=collections.defaultdict(lambda:{"sources":[],"rows":[]})
    totals=collections.defaultdict(collections.Counter);reasons=collections.Counter()
    if S2100_PDF in sources and "114992872" in by_sku and by_sku["114992872"].get("name","").lower().startswith("sensecap s2100"):
        # Several RS485 probes refer readers to this separate data logger's guide.
        # Its title and the exact S2100 store product identify the guide's owner.
        sources[S2100_PDF]["skus"].add("114992872")
    if WIO_MANUAL in sources and "102991299" in by_sku and by_sku["102991299"].get("name","").lower().startswith("wio terminal: atsamd51"):
        sources[WIO_MANUAL]["skus"].add("102991299")
    card_hosts=compatibility.card_hosts(records.get(compatibility.WIFI,{}),by_sku)
    if compatibility.WIFI in sources:sources[compatibility.WIFI]["skus"].update(card_hosts)
    if tables.ODYSSEY_BLUE in sources and tables.reviewed_edition(tables.ODYSSEY_BLUE,records.get(tables.ODYSSEY_BLUE,{})):
        sources[tables.ODYSSEY_BLUE]["skus"].update(code for code in ("110991564","110991565") if code in by_sku and tables.original_odyssey_blue(by_sku[code]))
    for publication in (tables.WEATHER,tables.WEATHER17):
        weather_record=records.get(publication,{})
        if publication in sources and tables.reviewed_edition(publication,weather_record):
            sources[publication]["skus"].update(s for s in tables.WEATHER_MODELS if s in by_sku and tables.printed_weather_matches(by_sku[s],weather_record))
    edge={sku for sku in EDGELOGIX_RAM if sku in by_sku and "edgelogix" in words(by_sku[sku].get("name","")).replace(" ","")}
    if edge:
        src=sources.setdefault(EDGELOGIX_GUIDE,{"kind":"pdf","skus":set(),"labels":set(),"direct":set(),"via":set()})
        src["skus"].update(edge)
        records[EDGELOGIX_GUIDE]={**records.get(EDGELOGIX_GUIDE,{}),"status":"parsed","kind":"pdf","title":"Seeed Studio Raspberry Pi Series Catalog v1.1"}
    official_catalog=Path(folder)/"global-catalog-evidence.json"
    catalog_pages=collections.defaultdict(list)
    if official_catalog.is_file():
        guide=json.loads(official_catalog.read_text(encoding="utf-8"))
        for page in guide["mentions"]:
            for sku in page["skus"]:
                if sku=="604182009" and page["page"]==119:continue
                if sku in by_sku:catalog_pages[sku].append(page["page"])
        if catalog_pages:
            u=canonical(guide["url"])
            sources[u]={"kind":"catalogue","labels":{"Seeed Studio Catalog 2026"},"skus":set(catalog_pages),"direct":set(),"via":set()}
            records[u]={"status":"parsed","kind":"catalogue","title":"Seeed Studio Catalog 2026","pages":guide["pages"]}
    for url,link in sources.items():
        record=records.get(url,{})
        status=record.get("status","unread")
        prior={}
        visual={}
        text_review={}
        focused={}
        variant_conflicts={}
        outside={}
        if url in variants.EDITIONS:
            for sku in link["skus"]:
                if sku not in by_sku:continue
                rows,conf=variants.reviewed(url,by_sku[sku],record)
                if rows:focused[sku]=rows
                if conf:variant_conflicts[sku]=conf
                scope=variants.figure_scope(url,by_sku[sku],record)
                if scope:outside[sku]=scope
            if focused:status="parsed"
            elif outside and outside.keys()==link["skus"]:status="empty"
        if link["kind"]=="spreadsheet" and record.get("worksheets"):
            focused={s:document_sheet.verified_rows(url,by_sku[s],record,by_sku) for s in link["direct"] if s in by_sku}
            if any(focused.values()):status="parsed"
            elif document_sheet.reviewed_assembly(url,record):status="empty"
        if tables.reviewed_edition(url,record):
            focused={s:tables.source_rows(url,by_sku[s],record,by_sku) for s in link["skus"] if s in by_sku}
            outside={s:scope for s in link["skus"] if s in by_sku and (scope:=tables.sections_outside_product_box(url,record,by_sku[s]))}
            if any(focused.values()):status="parsed"
            elif outside and outside.keys()==link["skus"]:status="empty"
        if link["kind"]=="wiki" and record.get("markdownSource"):
            focused={s:checked_wiki_rows(url,by_sku[s],record,by_sku) for s in link["skus"] if s in by_sku}
            if url==compatibility.BLUE and by_sku.get("102990827",{}).get("name")=="BeagleBone® Blue" and record.get("compatibilityRows"):
                focused["102990827"]=record["compatibilityRows"]
            if url==compatibility.WIFI:focused.update(card_hosts)
            if any(focused.values()):status="parsed"
        if link["kind"]=="wiki" and (record.get("markdownSource") or record.get("publishedRedirect")):
            outside={s:scope for s in link["skus"] if s in by_sku and (scope:=supplementary_wiki_scope(url,by_sku[s],record))}
            if outside and outside.keys()==link["skus"] and not any(focused.values()):status="empty"
        if link["kind"]=="wiki" and record.get("publishedRedirect") and record.get("status")=="parsed":
            for s in link["direct"]:
                if s in by_sku:
                    extra_rows=compatibility.legacy_wiki_rows(by_sku[s],record)
                    if extra_rows:focused.setdefault(s,[]).extend(extra_rows)
        if url==SENSECAP_V13 and status in ("empty","parsed"):
            text_review={s:sensecap_common_box(by_sku[s],record) for s in link["direct"] if s in by_sku}
            if any(text_review.values()):status="parsed"
        if (url in FULL_KITS or url in CORD_EXCLUDED) and status in ("empty","parsed"):
            text_review={s:exact_model_rows(url,by_sku[s],record,by_sku) for s in link["skus"] if s in by_sku}
            if any(text_review.values()):status="parsed"
        if url in REVIEWED_TABLES:
            visual={s:reviewed_rows(url,by_sku[s],record) for s in link["skus"] if s in by_sku}
            if any(visual.values()):status="parsed"
        if url in {WIO_MANUAL,R1000_FLYER,ZIMA_MANUAL,J1020_DATASHEET,BLIKVM_PCIE,ECOEYE} or url in JETSON_BOX:
            visual={s:other_visual_rows(url,by_sku[s],record) for s in link["skus"] if s in by_sku}
            if any(visual.values()):status="parsed"
        reviewed_empty=url in {DSO_MANUAL,DSO_REPO_MANUAL,BATTERY_BOM} and reviewed_current(url,record) and record.get("ocrStatus")=="candidate_review"
        if reviewed_empty:status="empty"
        if link["kind"]=="pdf" and status in ("empty","parsed"):
            prior={s:preverified_pdf_rows(by_sku[s],url,record,catalog.get("docs",{})) for s in link["skus"] if s in by_sku}
            if any(prior.values()):status="parsed"
        reason=record.get("reason","") if status not in ("parsed","empty") else ""
        if status=="empty" and record.get("sections") and not reviewed_empty and not outside:
            # A recognisable heading may lead to an illustration, a contents
            # entry or a table whose text cell boundaries were lost.
            status,reason="unread","section_needs_review"
        if not record:
            if urlsplit(url).hostname=="datasheets.raspberrypi.com":reason="publisher_terms"
            elif not publisher_source(url) and not github_file(url):reason="external_not_checked"
            else:reason="other_resource_type" if link["kind"]=="reference" else "not_yet_checked"
        qscout=url==tables.QSCOUT and "110090181" in by_sku and tables.document_conflicts(url,by_sku["110090181"],record,by_sku)
        if qscout:status,reason="unread","document_model_conflict"
        totals[link["kind"]][status]+=1
        if reason:reasons[reason]+=1
        basic={"url":url,"kind":link["kind"],"status":status}
        if qscout:
            basic["sourceScope"]="model_conflict"
            basic["sectionLinks"]=[{"page":n,"heading":heading,"url":url+"#page="+str(n)} for n,heading in
                                   [(1,"Parts 1–11"),(2,"Parts 12–22"),(3,"Parts 23–34"),(4,"Parts 35–45")]]
        if record.get("worksheets"):basic["worksheets"]=record["worksheets"]
        if record.get("sheetReview"):basic["sheetReview"]=record["sheetReview"]
        if document_sheet.reviewed_assembly(url,record):basic["sheetReview"]="assembly_bom"
        if reason:basic["reason"]=reason
        if status=="unread" and reason in ("section_needs_review","ocr_candidate_needs_review"):
            sections=candidate_section_links(url,record)
            if sections:basic["sectionLinks"]=sections
        if record.get("lastAttempt"):basic["lastAttempt"]=record["lastAttempt"]
        if record.get("previousEdition"):basic["previousEdition"]=record["previousEdition"]
        for sku in link["skus"]:
            if sku not in by_sku:continue
            info=per[sku]
            item={**basic,"relation":"direct" if sku in link["direct"] else "viaWiki"}
            if sku in link.get("purchases",set()) and sku not in link["direct"]:item["relation"]="purchaseLink"
            if sku in link.get("declared",set()):item["relation"]="declaredSku"
            if sku in link.get("serviceSkus",set()) and sku not in link["direct"] and sku not in link.get("declared",set()):
                item["relation"]="familyService"
            if url==S2100_PDF and sku=="114992872" and sku not in link["direct"]:item["relation"]="modelMatch"
            if url==WIO_MANUAL and sku=="102991299" and sku not in link["direct"]:item["relation"]="modelMatch"
            if url==compatibility.WIFI and sku in card_hosts:
                item["relation"]="modelMatch";item["modelSource"]=card_hosts[sku][0]["source"]
            if url==tables.ODYSSEY_BLUE and focused.get(sku) and sku not in link["direct"]:
                item.update(relation="modelMatch",modelSource=by_sku[sku].get("partSource") or by_sku[sku].get("url",""))
            if url in (tables.WEATHER,tables.WEATHER17) and focused.get(sku) and sku not in link["direct"]:
                item.update(relation="printedSku",modelSource=url+"#page=9")
            if link["kind"]=="wiki":
                scope=next((v for v in ("application","component_guide","multi_sku","product") if v in record.get("sourceScopes",[])),None)
                if scope:item["sourceScope"]=scope
            if record.get("title"):item["title"]=record["title"]
            if record.get("ocrStatus"):item["ocrStatus"]=record["ocrStatus"]
            if record.get("ocrReview"):item["ocrReview"]=record["ocrReview"]
            if record.get("ocrSameBytesAs"):item["ocrSameBytesAs"]=record["ocrSameBytesAs"]
            if sku in outside:
                scope,sections=outside[sku]
                item["sourceScope"]=scope
                item["sectionLinks"]=[]
                for number,purpose,label,*permalink in sections:
                    entry={"kind":purpose,"heading":label}
                    if permalink:entry["url"]=permalink[0]
                    else:entry.update(page=number,url=url+"#page="+str(number))
                    item["sectionLinks"].append(entry)
                if record.get("ocrStatus"):item["ocrStatus"]="no_target_found"
            if url==tables.DEMO_KITS and focused.get(sku):
                pages=[(1,"Package 1 · S700/S800/S1000, 4G hub and PV-12W"),(2,"Package 1 · installation tools and fittings")] if sku=="E23010807" else [
                    (11,"Package 2 · S200/S500/S700/S800/S1000, S2100, junction box and M2 gateway"),(12,"Package 2 · gateway purchase and setup")]
                item["sourceScope"]="configuration"
                item["sectionLinks"]=[{"kind":"example_configuration","heading":title,"page":page,"url":url+"#page="+str(page)} for page,title in pages]
            if visual.get(sku) or (url in (tables.LINKIT_BOX,tables.ODYSSEY_BLUE) and focused.get(sku)):item["ocrStatus"]="table_visually_verified"
            if url==BATTERY_BOM and reviewed_empty:item["ocrStatus"]="internal_component_bom"
            if url in {DSO_MANUAL,DSO_REPO_MANUAL} and reviewed_empty:item["ocrStatus"]="no_named_accessories"
            if link["kind"]=="catalogue":
                item.update(relation="printedSku",pages=sorted(set(catalog_pages[sku])),scope="sku")
                item["url"]=item["url"]+"#page="+str(item["pages"][0])
            matched=identity(by_sku[sku],url,record,link) if status=="parsed" and link["kind"]!="spreadsheet" else None
            if sku in outside:matched=None
            qualified=[*prior.get(sku,[]),*visual.get(sku,[]),*text_review.get(sku,[]),*focused.get(sku,[])]
            if sku in link.get("serviceSkus",set()):
                service=record["serviceEvidence"]
                qualified.append({"kind":"customization","name":"logo branding, packaging, firmware flashing","scope":"family",
                                  "basis":"reviewed_wiki_series_service","family":service["family"],"source":service["source"],
                                  "modelSource":service["modelSource"],"serviceUrl":service["serviceUrl"]})
            if url==tables.SUPER and focused.get(sku):
                qualified=list(focused[sku]);matched=None
            if url in variants.EDITIONS and focused.get(sku):
                qualified=list(focused[sku]);matched=None
                if url==variants.ACRYLIC:item["ocrStatus"]="table_visually_verified"
                if url in variants.ODYS:
                    item.update(ocrStatus="table_visually_verified",sourceScope="multi_sku",pages=[2,15])
            if url in {BLIKVM_PCIE,ECOEYE} or url in JETSON_BOX:
                qualified=list(visual.get(sku,[]));matched=None
                if url==BLIKVM_PCIE and qualified:
                    p=by_sku[sku]
                    module=next((row[0] for row in p.get("parts",[]) if row and "CM4 102000" in row[0]),None)
                    if module:
                        info.setdefault("conflicts",[]).append({"publishedSku":"","field":"moduleModel","name":"CM4 002000 (plug-n-play column)",
                            "catalogName":module,"catalogUrl":p.get("partSources",{}).get(module) or p.get("partSource") or p.get("url",""),
                            "source":url+"#page=5"})
            if url==ZIMA_MANUAL:
                # Its four side-by-side labels collapse into one line in the
                # PDF text layer. Only the checked illustration is usable.
                qualified=list(visual.get(sku,[]));matched=None
                if qualified:
                    item.update(sourceScope="multi_sku",pages=[1,3])
                    p=by_sku[sku]
                    store_supply=next((row[0] for row in p.get("parts",[]) if row and "power adapter" in row[0].lower()),None)
                    if store_supply:
                        info.setdefault("conflicts",[]).append({"publishedSku":"","field":"guidePackageScope",
                            "name":"Shared packing illustration lists the board, SATA cable, manual and two stickers",
                            "catalogName":store_supply,"catalogUrl":p.get("partSources",{}).get(store_supply) or p.get("partSource") or p.get("url",""),
                            "source":url+"#page=3"})
            if focused.get(sku) or sku in outside or (qscout and sku=="110090181"):
                conflicts=tables.document_conflicts(url,by_sku[sku],record,by_sku)+checked_wiki_conflicts(url,by_sku[sku],record)+variant_conflicts.get(sku,[])
                for conflict in conflicts:
                    items=info.setdefault("conflicts",[])
                    previous=next((old for old in items if all(old.get(k)==conflict.get(k) for k in ("publishedSku","field","name","catalogName"))),None)
                    if not previous:items.append(conflict)
                    elif previous["source"]!=conflict["source"] and conflict["source"] not in previous.setdefault("otherSources",[]):
                        previous["otherSources"].append(conflict["source"])
            if url==EDGELOGIX_GUIDE and sku in edge:
                item.update(relation="printedSku",pages=[17],scope="sku",url=EDGELOGIX_GUIDE+"#page=17")
                qualified.extend(edgelogix_facts(sku))
            if matched:
                qualified.extend(accepted(record,*matched,sku))
            if qualified:
                if record.get("sha256"):item["fileSha256"]=record["sha256"]
                if record.get("checkedAt"):item["checkedAt"]=record["checkedAt"]
                known={(x["kind"],x["source"],x.get("sku") or x.get("publishedSku") or x["name"]) for x in info["rows"]}
                added=0
                for fact in qualified:
                    if fact["kind"]=="accessory" and fact.get("sku") and fact["sku"] not in by_sku:
                        fact={**fact,"publishedSku":fact["sku"]}
                    if fact["kind"]=="accessory" and fact.get("namedAccessory") and not fact.get("sku") and fact.get("linkedStoreUrl"):
                        original_link=fact["linkedStoreUrl"]
                        fact={key:value for key,value in fact.items() if key!="linkedStoreUrl"}
                        match=re.search(r"-p-(\d+)\.html$",urlsplit(original_link).path,re.I)
                        matches=by_store_id.get(match[1],set()) if match else set()
                        if len(matches)==1 and sku not in matches:
                            target=next(iter(matches))
                            label=words(fact["name"])
                            target_title=words(by_sku[target].get("name",""))
                            if len(label)>6 and len(label.split())>=2 and re.search(r"\b"+re.escape(label)+r"\b",target_title):
                                fact={**fact,"sku":target,"storeProductSource":by_sku[target].get("url",""),"basis":"wiki_accessory_row_store_id_and_title"}
                    key=fact["kind"],fact["source"],fact.get("sku") or fact.get("publishedSku") or fact["name"]
                    if key not in known:
                        info["rows"].append({**fact,"documentUrl":url});known.add(key);added+=1
                item["verifiedRows"]=added
            info["sources"].append(item)
    return per,totals,reasons


def merge_document_evidence(catalog, folder):
    """Overlay only documented relationships. Updates base data in memory, returns totals."""
    path=Path(folder)
    for attempt in range(5):
        summary=json.loads((path/"document-summary.json").read_bytes())
        payload=(path/"sku-document-audit.json").read_bytes()
        fingerprint=summary.get("auditSha256")
        if not fingerprint or hashlib.sha256(payload).hexdigest()==fingerprint:break
        if attempt==4:raise ValueError("The document summary and evidence bundle belong to different revisions.")
        time.sleep(.1)
    bundle=json.loads(payload)
    by_sku={p["sku"]:p for p in catalog["products"]}
    for p in catalog["products"]:
        result=bundle.get(p["sku"])
        if result:
            p["documentAudit"]=result["audit"]
            p["documentChecks"]=result["sources"]
            p["verifiedDocumentRows"]=result["rows"]
            if result.get("conflicts"):p["documentConflicts"]=result["conflicts"]
            if p["sku"] in tables.SUPER_MODELS and any(r["kind"]=="inbox" and r.get("sku")=="112990226" and r.get("documentUrl")==tables.SUPER for r in result["rows"]):
                # Old pilot rows transcribed an entire options table, including
                # the installed disk and the two cameras with conflicting FOV.
                unsafe={r["publishedSku"] for r in result.get("conflicts",[]) if r.get("field")=="fieldOfView"}|{"112990226"}
                p["accessories"]=[a for a in p.get("accessories",[]) if not (a.get("sku") in unsafe and
                                  (a.get("doc")=="super" or canonical(a.get("source",""))==tables.SUPER))]
            merge_rows(p,result["rows"],by_sku)
    return summary


# Explicit equivalences across two official editions. Preserve the storefront's
# spelling/quantities, and retain the handbook description as separate evidence.
PACK_ALIASES={
    ("110060482","109990056"):"Flat HDMI Male to Male Cable (1M)",
    ("110060482","321010007"):"Micro USB Cable (1200px)",
    ("114990711","rfeah 25 h loop near field antenna"):"RF Explorer H-Loop Near Field Antenna (RFEAN25)",
}


def part_key(value):
    phrase=unicodedata.normalize("NFKC",value.replace("™","").replace("®","").replace("+"," plus ")).casefold()
    phrase=re.sub(r"\b(?:tm|the)\b","",phrase)
    return "".join(ch for ch in phrase if ch.isalnum())


def numeric_qty(value):
    matched=re.fullmatch(r"\s*(?:[x×]\s*)?(\d+)\s*(?:pcs?\.?|pieces?)?\s*",str(value or ""),re.I)
    return int(matched[1]) if matched else None


def exclusion_key(value):
    phrase=words(value)
    if "壁挂" in value or ("wall" in phrase and "bracket" in phrase):return "wall bracket"
    if "4g" in phrase and ("lorawan" in phrase or "lora" in phrase):return "4g lora modules"
    if "raspberry pi" in phrase and "board" in phrase:return "raspberry pi board"
    return phrase or value.strip()


def use_complete_assembly_table(product,facts):
    """One physical parts list for these kits. The storefront can count an assembly as a single item."""
    tables={url:(sku,page,title,[(name,qty) for _,name,qty in rows]) for url,(sku,page,title,rows) in REVIEWED_TABLES.items()}
    tables.update(FULL_KITS)
    for url,(sku,page,title,rows) in tables.items():
        if product["sku"]!=sku or not product.get("name","").casefold().startswith(title.casefold()):continue
        source=url+"#page="+str(page)
        verified=[f for f in facts if f["kind"]=="inbox" and f["source"]==source and f.get("basis") in {"visually_verified_packing_table","reviewed_model_packing_table"}]
        if {(f["name"],str(f.get("quantity",""))) for f in verified}!={(name,str(qty)) for name,qty in rows}:continue
        if product.get("partSource")!=source:
            sources=product.get("partSources",{})
            original=[list(x) for x in product.get("parts",[]) if x and sources.get(x[0],"")!=source]
            if original:
                quantities={part_key(n):numeric_qty(qty) for n,qty in rows}
                for item in original:
                    current=numeric_qty(item[1] if len(item)>1 else "")
                    published=quantities.get(part_key(item[0]))
                    if current is not None and published is not None and current!=published:
                        conflict={"name":item[0],"existingQuantity":str(current),"documentQuantity":str(published),"documentSource":source,
                                  "existingSource":sources.get(item[0]) or product.get("partSource") or product.get("url","")}
                        conflicts=product.setdefault("partConflicts",[])
                        if conflict not in conflicts:conflicts.append(conflict)
                kind="assembly_components" if url==J2032_PDF else "storefront"
                alternate={"source":product.get("partSource") or product.get("url",""),"kind":kind,"parts":original}
                alternatives=product.setdefault("alternatePackingLists",[])
                if alternate not in alternatives:alternatives.append(alternate)
        product["parts"]=[[name,str(qty)] for name,qty in rows]
        product["partSources"]={name:source for name,_ in rows}
        product["partScopes"]={name:"sku" for name,_ in rows}
        product["partSource"]=source
        product["partStatus"]="present"


def independent_packing_tables(product,facts):
    """Do not sum assembly/variant nomenclature from independent published lists."""
    groups=collections.defaultdict(list)
    for row in facts:
        if row["kind"]=="inbox" and row.get("documentUrl"):
            groups[row["documentUrl"]].append(row)
    alternate_rows=set()
    existing={part_key(row[0]) for row in product.get("parts",[]) if row}
    for doc,items in groups.items():
        primary=product.get("partSource","")
        if not existing:
            product["partSource"]=items[0]["source"]
            existing.update(part_key(row["name"]) for row in items)
            continue
        if primary.split("#",1)[0] in {doc,items[0]["source"].split("#",1)[0]}:continue
        # Identical names are safe to compare for quantity discrepancies.
        if all(part_key(row["name"]) in existing for row in items):continue
        per_item={row["name"]:row["source"] for row in items}
        entries=[]
        for row in items:
            cells=[row["name"],row.get("quantity","")]
            if cells not in entries:entries.append(cells)
        extra={"kind":"document","source":items[0]["source"],"documentUrl":doc,"parts":entries,
               "partSources":per_item,"scope":items[0]["scope"]}
        others=product.setdefault("alternatePackingLists",[])
        same=next((option for option in others if option.get("kind")=="document" and option.get("documentUrl")!=doc
                   and option.get("scope")==extra["scope"] and option.get("parts")==entries),None)
        if same:
            citation={"documentUrl":doc,"source":extra["source"],"partSources":per_item}
            references=same.setdefault("otherSources",[])
            if citation not in references:references.append(citation)
            alternate_rows.update(id(row) for row in items if part_key(row["name"]) not in existing)
            continue
        other_index=next((i for i,option in enumerate(others) if option.get("kind")=="document" and option.get("documentUrl")==doc),None)
        if other_index is None:others.append(extra)
        else:
            if others[other_index].get("otherSources"):extra["otherSources"]=others[other_index]["otherSources"]
            others[other_index]=extra
        alternate_rows.update(id(row) for row in items if part_key(row["name"]) not in existing)
    return alternate_rows


def merge_rows(product,facts,by_sku):
    use_complete_assembly_table(product,facts)
    alternate_rows=independent_packing_tables(product,facts)
    packing_targets=collections.defaultdict(set)
    for fact in facts:
        name=fact["name"];sku=fact.get("sku","");source=fact["source"]
        if fact["kind"]=="inbox":
            if id(fact) in alternate_rows:continue
            parts=product.setdefault("parts",[])
            original=PACK_ALIASES.get((product["sku"],sku or words(name)),"")
            aliases={part_key(t) for t in (name,original,by_sku.get(sku,{}).get("name","")) if t}
            existing=next((row for row in parts if row and part_key(row[0]) in aliases),None)
            code=sku or fact.get("publishedSku")
            if code:packing_targets[existing[0] if existing else name].add(code)
            part_name=existing[0] if existing else name
            if fact.get("sheet") and fact.get("row") and fact.get("cellRange"):
                product.setdefault("partSourceLocations",{})[part_name]={k:fact[k] for k in ("sheet","row","cellRange")}
                product["partSourceLocations"][part_name]["source"]=source
            if fact.get("publishedSku"):product.setdefault("partPublishedSkus",{})[part_name]=fact["publishedSku"]
            if existing:
                primary=product.get("partSources",{}).get(existing[0]) or product.get("partSource") or product.get("url")
                if source and source!=primary:
                    extra=product.setdefault("partOtherSources",{}).setdefault(existing[0],[])
                    if source not in extra:extra.append(source)
                old_qty=numeric_qty(existing[1] if len(existing)>1 else "")
                new_qty=numeric_qty(fact.get("quantity"))
                if fact.get("scope")=="sku" and new_qty is not None and not str(existing[1] if len(existing)>1 else "").strip():
                    if len(existing)>1:existing[1]=str(new_qty)
                    else:existing.append(str(new_qty))
                    product.setdefault("partQuantitySources",{})[existing[0]]=fact.get("quantitySource") or source
                if old_qty is not None and new_qty is not None and new_qty!=old_qty:
                    conflict={"name":existing[0],"existingQuantity":str(old_qty),"documentQuantity":str(new_qty),"documentSource":source,
                              "existingSource":product.get("partSources",{}).get(existing[0]) or product.get("partSource") or product.get("url","")}
                    conflicts=product.setdefault("partConflicts",[])
                    if conflict not in conflicts:conflicts.append(conflict)
                continue
            parts.append([name,fact.get("quantity","")])
            product.setdefault("partSources",{})[name]=source
            product.setdefault("partScopes",{})[name]=fact["scope"]
            product["partStatus"]="present"
        elif fact["kind"]=="expansion":
            accessories=product.setdefault("accessories",[])
            if not any(a.get("name")==name and a.get("source")==source for a in accessories):
                accessories.append({"name":name,"sku":"","type":"Expansion interface","scope":fact["basis"],"source":source})
        elif fact["kind"]=="modelSpec":
            specs=product.setdefault("modelSpecs",[])
            if not any(s.get("name")==name for s in specs):specs.append({"name":name,"value":fact["value"],"source":source})
        elif fact["kind"]=="accessory":
            accessories=product.setdefault("accessories",[])
            if fact.get("storeLabel"):
                match=next((a for a in accessories if a.get("name")==fact["storeLabel"] and a.get("type")=="商品页标明选配"),None)
                if match:
                    first=match.setdefault("documentedAsAccessorySource",source)
                    match.setdefault("documentedAsAccessoryName",name)
                    if first!=source and source not in match.setdefault("documentedAsAccessorySources",[first]):
                        match["documentedAsAccessorySources"].append(source)
                    if fact.get("notIncludedSource"):match["notIncludedSource"]=fact["notIncludedSource"]
                    continue
            if fact.get("compatibilityDetails"):
                match=next((a for a in accessories if sku and a.get("sku")==sku),None)
                if match:
                    details=match.setdefault("compatibilityDetails",[])
                    for detail in fact["compatibilityDetails"]:
                        if detail not in details:details.append(detail)
            if sku and fact.get("documentUrl") and kind(fact["documentUrl"]) in {"pdf","wiki"} and fact["scope"] in {"sku","family"}:
                offered=next((a for a in accessories if a.get("sku","").casefold()==sku.casefold() and a.get("type")=="商品页 Also Add 加购项"),None)
                if offered:
                    first=offered.setdefault("documentedAsAccessorySource",source)
                    offered.setdefault("documentedAsAccessoryScope",fact.get("family") or fact["scope"])
                    offered.setdefault("documentedAsAccessoryName",name)
                    if first!=source and source not in offered.setdefault("documentedAsAccessorySources",[first]):
                        offered["documentedAsAccessorySources"].append(source)
            if sku and fact.get("soldSeparately"):
                same=next((a for a in accessories if a.get("sku")==sku),None)
                if same:same["soldSeparatelySource"]=source
            if fact.get("notIncludedSource"):
                same=next((a for a in accessories if (sku and a.get("sku")==sku) or part_key(a.get("name",""))==part_key(name)),None)
                if same:same["notIncludedSource"]=fact["notIncludedSource"]
            if sku and sku not in by_sku and fact.get("publishedSku"):
                published_match=next((a for a in accessories if a.get("sku")==sku),None)
                if published_match:published_match["publishedSku"]=fact["publishedSku"]
            if not sku:
                if not fact.get("namedAccessory"):continue
                published=fact.get("publishedSku","")
                if published:
                    if any(published in (a.get("sku"),a.get("publishedSku")) for a in accessories):continue
                    unnamed=next((a for a in accessories if not a.get("sku") and not a.get("publishedSku") and a.get("source")==source and part_key(a.get("name",""))==part_key(name)),None)
                    if unnamed:
                        unnamed["publishedSku"]=published
                        continue
                elif any(part_key(a.get("name",""))==part_key(name) for a in accessories):continue
            elif sku==product["sku"] or any(a.get("sku","").casefold()==sku.casefold() for a in accessories):continue
            item={"sku":sku,"name":name,"type":"Official accessory list","source":source}
            if fact.get("compatibilityDetails"):
                item["compatibilityDetails"]=list(fact["compatibilityDetails"])
                item["type"]="Official module list" if fact.get("basis")=="published_host_module_workbook" else "Official compatibility list"
            if fact.get("soldSeparately"):item["soldSeparatelySource"]=source
            if fact.get("notIncludedSource"):item["notIncludedSource"]=fact["notIncludedSource"]
            if fact.get("publishedSku"):item["publishedSku"]=fact["publishedSku"]
            if sku in by_sku:item["storeName"]=by_sku[sku]["name"]
            if fact["scope"]=="family":item["scope"]=fact.get("family") or fact["basis"]
            accessories.append(item)
        elif fact["kind"] in ("exclusion","customization"):
            category="另购说明" if fact["kind"]=="exclusion" else "定制说明"
            notes=product.setdefault("notes",[])
            if fact["kind"]=="customization" and product.get("custom"):continue
            present=any(note.get("kind")==category and (exclusion_key(note.get("text",""))==exclusion_key(name)
                       or (note.get("source")==source and words(name) in words(note.get("text","")))) for note in notes)
            if not present:notes.append({"kind":category,"text":name,"source":source,"scope":fact["scope"]})
            if fact["kind"]=="customization":
                if fact.get("basis")!="reviewed_wiki_series_service" or not (product.get("custom") and product.get("customUrl")):
                    product["custom"]=name
                    product["customUrl"]=fact.get("documentUrl",source) if source.startswith("https://github.com/") else source
            else:
                missing=product.setdefault("missingSummary",[])
                if not any(exclusion_key(n)==exclusion_key(name) for n in missing):missing.append(name)
    for name,codes in packing_targets.items():
        if len(codes)==1:
            code=next(iter(codes))
            if code in by_sku and code!=product["sku"]:
                product.setdefault("partProductSkus",{})[name]=code
                continue
        if "partProductSkus" in product:product["partProductSkus"].pop(name,None)


def write_bundle(catalog,folder,additional=None):
    folder=Path(folder);per,totals,reasons=audit(catalog,folder,additional)
    bundle={}
    for sku,r in sorted(per.items()):
        c=collections.Counter(s["status"] for s in r["sources"])
        summary={s:c.get(s,0) for s in ("parsed","empty","unread","failed")}
        summary.update(linked=len(r["sources"]),checked=c["parsed"]+c["empty"],verifiedRows=len(r["rows"]))
        bundle[sku]={"audit":summary,"sources":sorted(r["sources"],key=lambda e:(e["kind"],e["url"])),"rows":r["rows"]}
        if r.get("conflicts"):bundle[sku]["conflicts"]=r["conflicts"]
    all_status=collections.Counter()
    for values in totals.values():all_status.update(values)
    result={"uniqueLinked":sum(all_status.values()),"uniqueChecked":all_status["parsed"]+all_status["empty"],
            "uniqueByStatus":dict(all_status),"byKind":{k:dict(v) for k,v in totals.items()},
            "unreadAndFailureReasons":dict(reasons),"linkedSkus":len(bundle),
            "checkedSkus":sum(bool(x["audit"]["checked"]) for x in bundle.values()),
            "verifiedSkus":sum(bool(x["rows"]) for x in bundle.values()),"verifiedRows":sum(len(x["rows"]) for x in bundle.values())}
    pairs={(sku,row["sku"]) for sku,item in bundle.items() for row in item["rows"] if row["kind"]=="accessory" and row.get("sku")}
    result["distinctAccessorySkuPairs"]=len(pairs)
    result["distinctAccessorySkus"]=len({target for _,target in pairs})
    result["skusWithDocumentPackingRows"]=sum(any(r["kind"]=="inbox" for r in v["rows"]) for v in bundle.values())
    result["sourcesWithSkuFacts"]=len({r["documentUrl"] for v in bundle.values() for r in v["rows"] if r.get("documentUrl")})
    unique_checks={canonical(s["url"]):s for row in bundle.values() for s in row["sources"]}
    result["sheetSourcesChecked"]=sum(s["kind"]=="spreadsheet" and bool(s.get("worksheets")) for s in unique_checks.values())
    sheet_rows={(r["documentUrl"],r["sheet"],r["row"]) for v in bundle.values() for r in v["rows"] if r.get("sheet") and r.get("row")}
    sheet_rows.update((item["source"],item["sheet"],item["row"]) for v in bundle.values() for row in v["rows"] for item in row.get("compatibilityDetails",[]) if item.get("sheet") and item.get("row"))
    result["sheetRowsWithProductEvidence"]=len(sheet_rows)
    origins=collections.defaultdict(collections.Counter)
    pending_official=collections.Counter()
    github_contents=collections.defaultdict(list)
    for url,source in unique_checks.items():
        remote=github_file(url) if source["kind"] in ("pdf","spreadsheet") else None
        origin=("otherAttachment" if source["kind"]=="reference" else "seeed" if publisher_source(url) else "officialGitHub" if remote else "external")
        outcome=source.get("reason") or source["status"]
        origins[origin][outcome]+=1
        if origin=="seeed" and outcome=="not_yet_checked":
            pending_official["certificateDirectory" if re.search(r"/(?:Seeed_Certificate|documents_certificate)/",url,re.I) else source["kind"]]+=1
        if remote:github_contents[remote[0]].append(outcome)
    result["sourceOutcomesByPublisher"]={k:dict(v) for k,v in origins.items()}
    result["firstPartyPendingReads"]=dict(pending_official)
    result["githubPendingFiles"]=sum(all(r in {"not_yet_checked","github_rate_limit","github_secondary_limit","github_cli_unavailable","host_cooldown","network"} for r in statuses)
                                      for statuses in github_contents.values())
    certificate_counts=collections.Counter(s["status"] for u,s in unique_checks.items() if s["kind"]=="pdf" and
                                          re.search(r"/(?:Seeed_Certificate|documents_certificate)/",u,re.I))
    result["certificateDirectoryPdfs"]={"linked":sum(certificate_counts.values()),**dict(certificate_counts)}
    records=log_records(folder)
    result["officialScopeSummary"]=reconcile(unique_checks,records,request_receipts(folder))
    public_cli={url:r for url,r in records.items() if url in unique_checks and r.get("githubBudget")=="account"}
    if public_cli:
        verified={u:r["gitBlobSha"] for u,r in public_cli.items() if r.get("gitBlobSha")}
        result["githubPublicCli"]={"linkedUrls":len(public_cli),"integrityVerified":len(verified),"distinctGitBlobs":len(set(verified.values())),
                                   "screened":sum(unique_checks[u]["status"] in ("parsed","empty") for u in verified),
                                   "unavailableByReason":dict(collections.Counter(r.get("reason","unknown") for u,r in public_cli.items() if u not in verified))}
    linked_urls={canonical(source["url"]) for x in bundle.values() for source in x["sources"]}
    pdfs={}
    for url,r in records.items():
        if url not in linked_urls or r.get("kind")!="pdf":continue
        key=r.get("sha256") or url
        prior=pdfs.get(key)
        if not prior or (r.get("status") in {"parsed","empty"} and prior.get("status") not in {"parsed","empty"}):pdfs[key]=r
    pdf=list(pdfs.values())
    result["pdfDeclaredPages"]=sum(r.get("pages",0) for r in pdf)
    result["pdfPagesInCompletedTextPasses"]=sum(r.get("pages",0) for r in pdf if r.get("status") in {"parsed","empty"} and not r.get("ocrStatus"))
    result["pdfSparsePagesInCompletedTextPasses"]=sum(r.get("sparsePages",0) for r in pdf if r.get("status") in {"parsed","empty"} and not r.get("ocrStatus"))
    ocr_completed={"no_target_found","partial_or_unreadable","candidate_review"}
    result["pdfOcrAttempts"]=sum(bool(r.get("ocrStatus")) for r in pdf)
    result["pdfOcrSharedLinks"]=sum(bool(r.get("ocrSameBytesAs")) for u,r in records.items() if u in linked_urls)
    result["pdfOcrDocuments"]=sum(r.get("ocrStatus") in ocr_completed for r in pdf)
    result["pdfOcrPagesWithText"]=sum(r.get("ocrPagesWithText",0) for r in pdf)
    digital=[r for r in pdf if r.get("status") in {"parsed","empty"} and not r.get("ocrStatus")]
    result["pdfTextFilesWithoutDigest"]=sum(not r.get("sha256") for r in digital)
    result["pdfTextPagesWithoutDigest"]=sum(r.get("pages",0) for r in digital if not r.get("sha256"))
    result["pdfTextPages"]=sum(r.get("pages",0) for r in digital if r.get("sha256"))
    result["pdfTextSparsePagesByDigest"]=sum(r.get("sparsePages",0) for r in digital if r.get("sha256"))
    result["pdfOcrPages"]=sum(r.get("pages",0) for r in pdf if r.get("ocrStatus") in ocr_completed)
    offline_articles=[r["markdownSource"] for u,r in records.items() if u in linked_urls and r.get("markdownSource") and not r.get("serviceParagraphOnly")]
    result["offlineWikiArticleUrls"]=len(offline_articles)
    result["offlineWikiArticles"]=len(set(offline_articles))
    result["targetedWikiServiceGuides"]=sum(bool(r.get("serviceEvidence")) for u,r in records.items() if u in linked_urls)
    result["wikiSeriesServiceSkus"]=len({sku for sku,entry in bundle.items() if any(f.get("basis")=="reviewed_wiki_series_service" for f in entry["rows"])})
    official_catalogue=folder/"global-catalog-evidence.json"
    if official_catalogue.is_file():
        general=json.loads(official_catalogue.read_text(encoding="utf-8"))
        result["globalCataloguePages"]=general.get("pages",0)
        result["globalCatalogueSkuMatches"]=sum(any(s["kind"]=="catalogue" for s in x["sources"]) for x in bundle.values())
        verified_unmatched={"114993124":{29,30},"100060802":{56},"100090853":{56},"100060965":{57},"102110839":{57},"316000001":{57,67}}
        indexed={p["sku"] for p in catalog.get("products",[])}
        result["publishedUnmatchedSkus"]=[
            {"sku":sku,"pages":pages,"source":general["url"]+"#page="+str(pages[0]),
             "pageUrls":[general["url"]+"#page="+str(n) for n in pages]}
            for sku,scoped_pages in verified_unmatched.items() if sku not in indexed and
            (pages:=sorted(entry["page"] for entry in general.get("mentions",[]) if entry["page"] in scoped_pages and sku in entry["skus"]))]
        if additional and isinstance(additional.get("paperSkuLookup"),dict):
            lookup=additional["paperSkuLookup"]
            if lookup.get("source")=="https://www.seeedstudio.com/graphql" and lookup.get("totalCount")==0 and lookup.get("matches")==[] and lookup.get("checkedAt"):
                for mention in result["publishedUnmatchedSkus"]:
                    if mention["sku"] in lookup.get("requested",[]):
                        mention["storeLookup"]={"source":lookup["source"],"checkedAt":lookup["checkedAt"],"matches":0}
    result["method"]="Counts report targeted extraction of accessible text, published tables or checked OCR. A checked document can have no SKU-specific relationship ready to use."
    payload=json.dumps(bundle,ensure_ascii=False,separators=(",",":")).encode("utf-8")
    result["auditSha256"]=hashlib.sha256(payload).hexdigest()
    atomic_write(folder/"sku-document-audit.json",payload)
    atomic_write(folder/"document-summary.json",json.dumps(result,indent=2).encode("utf-8"))
    return result


if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog",type=Path,default=Path("data/catalog.js"))
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--links",type=Path)
    args=parser.parse_args()
    extra=json.loads(args.links.read_text(encoding="utf-8-sig")) if args.links else None
    if extra is not None and (args.links.parent/"paper-sku-lookup.json").is_file():
        extra["paperSkuLookup"]=json.loads((args.links.parent/"paper-sku-lookup.json").read_bytes())
    print(json.dumps(write_bundle(load_catalog(args.catalog),args.output,extra),indent=2))
