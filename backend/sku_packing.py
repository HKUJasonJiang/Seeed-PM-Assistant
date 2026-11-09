"""Packing names and model options confirmed against SKU-indexed Seeed manuals."""
import re

from .extract import text_link


COMPUTER_GUIDE="https://files.seeedstudio.com/products/NVIDIA/reComputer-Industrial-Reference-Guide.pdf#page=1"
SERVER_GUIDE="https://files.seeedstudio.com/wiki/reServer-Industrial/reServer-Industrial-Reference-Guide.pdf#page=1"
COMPUTERS={"110110188":"J2011","110110189":"J2012","110110190":"J4011","110110191":"J4012","110110192":"J3010","110110193":"J3011"}
SERVERS={"114110247":"J4012","114110248":"J4011","114110249":"J3011","114110250":"J3010"}
SUPER_GUIDE="https://files.seeedstudio.com/products/NVIDIA-Jetson/reComputer_super_user_manual.pdf"
SUPER_MODULES={"114110311":("J3010","Nano","4"),"114110312":("J3011","Nano","8"),
               "114110313":("J4011","NX","8"),"114110314":("J4012","NX","16")}


def super_module(record):
    model,chip,gb=SUPER_MODULES[record["sku"]]
    title=record.get("name","")
    if not re.search(r"\breComputer Super\s+"+model+r"\b",title,re.I) or not re.search(r"\b"+chip+r"\s+"+gb+r"\s*GB\b",title,re.I):return
    rows=list(record.get("parts",[]))
    for index,(raw,quantity) in enumerate(rows):
        if not re.search(r"^Jetson Orin[^/]{0,12}\b(?:NX|Nano)\b",raw,re.I) or not re.search(r"\bmodule\s*$",raw,re.I):continue
        if not re.fullmatch(r"\s*[x×*]?\s*1\s*[x×*]?\s*",str(quantity),re.I):continue
        options={(label.casefold(),size) for label,size in re.findall(r"\b(NX|Nano)\s+(\d+)\s*GB\b",raw,re.I)}
        if (chip.casefold(),gb) not in options:continue
        display=f"Jetson Orin™ {chip} {gb}GB module"
        if len(options)>1:
            sources=dict(record.get("partSources") or {})
            source=sources.pop(raw,None) or record.get("partSource") or record.get("url")
            record.setdefault("partDescriptions",{})[display]={"kind":"configuration","text":raw,"source":source,"crosscheck":SUPER_GUIDE+"#page=2"}
            if any(n==display and re.fullmatch(r"\s*[x×*]?\s*1\s*[x×*]?\s*",str(q),re.I) for n,q in rows):rows.pop(index)
            else:rows[index]=[display,quantity]
            record["parts"]=rows
            if raw in record.get("partScopes",{}):record["partScopes"]={n:v for n,v in record["partScopes"].items() if n!=raw}
            sources[display]=SUPER_GUIDE+"#page=7"
            record["partSources"]=sources
            return


def verified_aliases(record):
    sku=record.get("sku")
    if sku in SUPER_MODULES:return super_module(record)
    if sku in COMPUTERS:family,model,guide="reComputer Industrial",COMPUTERS[sku],COMPUTER_GUIDE
    elif sku in SERVERS:family,model,guide="reServer Industrial",SERVERS[sku],SERVER_GUIDE
    else:return
    if not record.get("url") or family.casefold() not in record.get("name","").casefold() or model not in record["name"].upper():return
    def compact(s):return re.sub(r"[^a-z0-9]","",s.casefold())
    def count(q):
        m=re.fullmatch(r"\s*[x×*]?\s*(\d+)\s*[x×*]?\s*",str(q),re.I)
        return int(m[1]) if m else None
    aliases=[(compact(family+model+"system installed"),compact(family),1)]
    if sku in SERVERS:aliases.append(("bracketbolt","bracketscrew",10))
    rows=record.get("parts",[])
    for preferred,short,quantity in aliases:
        long_name=next((n for n,q in rows if compact(n)==preferred and count(q)==quantity),None)
        other=next((n for n,q in rows if compact(n)==short and count(q)==quantity),None)
        if not long_name or not other:continue
        source=(record.get("partSources") or {}).get(other) or text_link(record["url"],other)
        record.setdefault("partDescriptions",{})[long_name]={"kind":"alias","text":other,"source":source,"crosscheck":guide}
        record["parts"]=[row for row in record["parts"] if row[0]!=other]
        for field in ("partSources","partScopes"):
            if other in record.get(field,{}):record[field]={n:v for n,v in record[field].items() if n!=other}
    factory_count=4 if sku in COMPUTERS else 10
    for name,qty in record.get("parts",[]):
        if compact(name) not in {"bracketscrew","bracketbolt"} or count(qty) in {None,factory_count}:continue
        source=record.get("partSources",{}).get(name) or record.get("partSource") or record["url"]
        conflicts=dict(record.get("partQuantityConflicts") or {})
        conflict=list(conflicts.get(name,[{"quantity":qty,"source":source,"scope":"store_part_list"}]))
        if not any(entry.get("source")==guide for entry in conflict):conflict.append({"quantity":str(factory_count),"source":guide,"scope":"family"})
        conflicts[name]=conflict;record["partQuantityConflicts"]=conflicts
