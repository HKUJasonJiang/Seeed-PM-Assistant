"""Explicit, limited public-name verification. Writes only the requested report."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.bazaar_lookup import check_accessory, ready_to_retry, refine_status
from backend.storage import CATALOG_PREFIX, packed, write
from backend.storefront import OfficialStore


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog",type=Path,default=ROOT/"data"/"catalog.js")
    parser.add_argument("--sku",action="append",help="Host product SKU; repeat for more hosts")
    parser.add_argument("--manifest",type=Path,help="Explicit public catalogue accessory keys to check")
    parser.add_argument("--limit",type=int,default=10,help="At most 100 distinct names in one explicitly requested run")
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--include-linked",action="store_true",help="Also recheck published SKUs")
    parser.add_argument("--refresh",action="store_true",help="Recheck completed entries explicitly")
    args=parser.parse_args()
    if not 1<=args.limit<=100:parser.error("limit must be 1 to 100")
    output=args.output.resolve()
    if output==args.catalog.resolve() or output.name in {"catalog.js","workbench.json","chat-history.json","credentials.json"} or any(part.startswith(".local-workbench") for part in output.parts):
        parser.error("Choose a separate public verification report, outside the user data directory")
    text=args.catalog.read_text("utf-8")
    if not text.startswith(CATALOG_PREFIX):parser.error("The input must be a public catalogue")
    catalog=json.loads(text[len(CATALOG_PREFIX):].strip().rstrip(";"))
    if not args.sku and not args.manifest:parser.error("Select public host SKUs or a catalogue accessory manifest")
    selected=set(args.sku or [])
    manifest=set(json.loads(args.manifest.read_text("utf-8"))) if args.manifest else None
    if manifest is not None:selected={p["sku"] for p in catalog["products"]}
    products=[p for p in catalog["products"] if p["sku"] in selected]
    if len(products)!=len(selected):parser.error("A requested host SKU was not found in the public catalogue")
    prefix="window.SEEED_ACCESSORY_LOOKUP="
    if output.exists():
        saved=output.read_text("utf-8")
        if saved.startswith(prefix):saved=saved[len(prefix):].strip().rstrip(";")
        report=json.loads(saved)
    else:report={"version":1,"source":"https://www.seeedstudio.com/graphql","rows":{}}
    def save():
        content=packed(report)
        if output.suffix==".js":content=prefix.encode()+content+b";\n"
        write(output,content)
    for item in report["rows"].values():refine_status(item)
    remote=OfficialStore();count=0;cache={}
    for host in products:
        for accessory in host.get("accessories",[]):
            sku=accessory.get("sku") or accessory.get("publishedSku") or ""
            name=accessory.get("name","")
            key=json.dumps([name,sku],ensure_ascii=False,separators=(",",":"))
            if manifest is not None:
                if key not in manifest:continue
            elif sku and not args.include_linked:continue
            prior=report["rows"].get(key)
            if prior and not args.refresh and not ready_to_retry(prior):
                prior["hostSkus"]=sorted(set(prior.get("hostSkus",[])+[host["sku"]]))
                continue
            if count>=args.limit:break
            result=check_accessory(name,remote,sku,accessory.get("productUrl",""),cache)
            result["hostSkus"]=sorted(set((prior or {}).get("hostSkus",[])+[host["sku"]]))
            result["accessorySource"]=accessory.get("source","")
            report["rows"][key]=result;count+=1
            policy=remote.policies.get("www.seeedstudio.com")
            if policy:report["policy"]={"source":"https://www.seeedstudio.com/robots.txt","minimumDelaySeconds":policy.delay,"graphqlAllowed":policy.allows("https://www.seeedstudio.com/graphql")}
            save()
            print(host["sku"],result["status"],len(result["candidates"]),flush=True)
            if result["status"] in {"rate_limited","source_error","excluded"}:
                print("Stopped safely. Rerun after the source error or Retry-After has cleared.",flush=True)
                return 2
    save()
    print(json.dumps(dict(Counter(row["status"] for row in report["rows"].values())),ensure_ascii=False))
    return 0


if __name__=="__main__":raise SystemExit(main())
