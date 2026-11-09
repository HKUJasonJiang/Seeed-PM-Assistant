"""Verify family-wide commercial services against an official English guide and its named SKUs."""
import re
from urllib.parse import quote
from .document_enrichment import canonical


# A guide may also declare third-party bundles, development accessories and
# unrelated add-ons. Its service paragraph applies only to the named primary
# product family. Applications and the general Fusion service page are excluded.
GUIDES={
    "recomputer_industrial_getting_started":("reComputer Industrial Jetson",r"^reComputer Industrial J[234]0[01][012]\b"),
    "recomputer_j30_40_with_jetson_getting_start":("reComputer Classic J30/J40",r"^reComputer J[34]01[012]\b"),
    "recomputer_j401b_getting_start":("reComputer J401B",r"^reComputer J[34]01[012]B\b"),
    "recomputer_jetson_mini_getting_started":("reComputer Mini",r"^reComputer Mini J[34]01[012]\b"),
    "recomputer_jetson_super_getting_started":("reComputer Super",r"^reComputer Super J[34]01[012]\b"),
    "reserver_industrial_getting_started":("reServer Industrial",r"^reServer Industrial J[34]01[012]\b"),
    "recomputer_industrial_r20xx_getting_start":("reComputer Industrial R20xx",r"^reComputer Industrial R20\d{2}-\d{2}\b"),
    "recomputer_industrial_r21xx_getting_start":("reComputer Industrial R21xx",r"^reComputer Industrial R21\d{2}-\d{2}\b"),
    "recomputer_industrial_r22xx_getting_start":("reComputer Industrial R22xx",r"^reComputer Industrial R22\d{2}-\d{2}\b"),
    "recomputer_r":("reComputer R1000",r"^reComputer R10\d{2}-\d{2}\b"),
    "recomputer_r1100_intro":("reComputer R1100",r"^reComputer R11\d{2}-\d{2}\b"),
    "reterminal-dm":("reTerminal DM",r"^reTerminal DM\s*[-–|]"),
    "sensecap_t1000_tracker/introduction":("SenseCAP T1000-A/B",r"^SenseCAP T1000-[AB] LoRaWAN Tracker\b"),
    "t1000e_for_lorawan_introduction":("SenseCAP T1000-E for LoRaWAN",r"^SenseCAP .*?T1000-E\b"),
}
COMMITMENT="Available customization options: logo branding, packaging, and firmware flashing."
SERVICE="https://www.seeedstudio.com/fusion_branding_firmware.html"
FILENAME_HINTS={"recomputer_industrial_getting_started","recomputer_j30_40_with_jetson_getting_start",
    "recomputer_j401b_getting_start","recomputer_mini_getting_started","recomputer_super_getting_started",
    "reserver_industrial_getting_started","recomputer_industrial_r20xx_getting_start","recomputer_industrial_r21xx_getting_start",
    "recomputer_industrial_r22xx_getting_start","recomputer_r","recomputer_r1100","reterminal-dm","introduction","sensecap_t1000_tracker_introduction"}


def explicit_service(raw,root_source,products):
    lines=raw.splitlines()
    if not lines or lines[0].strip()!="---":return None
    try:end=next(i for i in range(1,min(len(lines),100)) if lines[i].strip()=="---")
    except StopIteration:return None
    header={}
    for line_number,line in enumerate(lines[1:end],2):
        key,separator,value=line.partition(":")
        if separator and key in {"sku","slug","title"}:header[key]=(line_number,value.strip())
    slug=header.get("slug",(0,""))[1].strip("/")
    guide=GUIDES.get(slug.casefold())
    if not guide or "sku" not in header or not header.get("title",(0,""))[1]:return None
    if not root_source.startswith("https://github.com/Seeed-Studio/wiki-documents/blob/"):return None
    pages=[i for i,l in enumerate(lines[:110]) if l.strip()==COMMITMENT]
    if len(pages)!=1 or not any(SERVICE in l and "customize now" in l.casefold() for l in lines[pages[0]+1:pages[0]+10]):return None
    declared=set(re.findall(r"(?<![\w-])(?:[1-9]\d{8}|[A-Z]\d{5,})(?![\w-])",header["sku"][1],re.I))
    family,pattern=guide
    members=sorted(s for s in declared if s in products and re.search(pattern,products[s].get("name",""),re.I))
    if not members:return None
    return {"url":canonical("https://wiki.seeedstudio.com/"+slug+"/"),"title":header["title"][1],"family":family,"skus":members,
            "source":root_source+"#L"+str(pages[0]+1),"modelSource":root_source+"#L"+str(header["sku"][0]),"serviceUrl":SERVICE}


def annotate(checkout,repository,revision,products,records):
    if repository.rstrip("/")!="https://github.com/Seeed-Studio/wiki-documents" or not re.fullmatch(r"[a-f0-9]{40}",revision):return
    base=checkout/"sites/en/docs"
    for path in base.rglob("*.md"):
        if path.stem.casefold() not in FILENAME_HINTS:continue
        source=repository+"/blob/"+revision+"/"+quote(path.relative_to(checkout).as_posix(),safe="/")
        service=explicit_service(path.read_text(encoding="utf-8-sig"),source,products)
        if not service:continue
        article=records.setdefault(service["url"],{"kind":"wiki","url":service["url"],"title":service["title"],
            "status":"parsed","sections":[],"rows":[],"statements":[],"linkedPdfs":{},"markdownSource":source,"purchaseSkus":[],
            "declaredSkus":[],"declaresMultiple":True,"sourceScopes":["multi_sku"],"parserVersion":3,"serviceParagraphOnly":True})
        article["serviceEvidence"]=service
