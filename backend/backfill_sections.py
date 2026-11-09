"""Repair public Part List metadata without downloading thousands of individual pages."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import time

from .storage import CATALOG_PREFIX, ROOT, Problem, packed, write
from .storefront import OfficialStore, RateLimit
from .extract import column_defaults, install_column, section_counts, text_link, tree,txt
from .r1000_evidence import enrich_r1000


def fetch(remote,folder,skus):
    index=folder/"index.json"
    if not index.exists():
        page=1; rows={}; targets={}
        query="""query($page:Int!){products(search:"",pageSize:300,currentPage:$page){total_count page_info{total_pages} items{id sku url_key url_suffix}}}"""
        while True:
            result=remote.public_query(query,{"page":page})["products"]
            for row in result["items"]:
                rows[row["sku"]]=row
                if row["sku"] in skus:targets[row["sku"]]=row
            if page>=result["page_info"]["total_pages"]:break
            page+=1
        if len(rows)!=result["total_count"]:raise Problem("STORE_CATALOG_CHANGED")
        write(index,packed(targets))
    targets=json.loads(index.read_bytes())
    selected=sorted(targets.values(),key=lambda r:(r["sku"]!="100025879",r["id"]))
    print("Verified public identity mappings:",len(selected),flush=True)
    for i in range(0,len(selected),30):
        batch=selected[i:i+30]
        dest=folder/("rows-%04d.json.gz"%i)
        if dest.is_file():continue
        data=remote.section_batch([r["id"] for r in batch])
        items={r["sku"]:data[r["id"]] for r in batch if r["id"] in data}
        write(dest,gzip.compress(packed(items)))
        if i%300==0:print("Public fields read:",min(i+30,len(selected)),"/",len(selected),flush=True)
        time.sleep(0.12)
    return targets


def stage(db,folder,output,detail_files):
    public_index=json.loads((folder/"index.json").read_bytes())
    by_sku={p["sku"]:p for p in db["products"]}
    processed=set()
    for chunk in sorted(folder.glob("rows-*.json.gz")):
        with gzip.open(chunk) as source:fields=json.load(source)
        for sku,fragment in fields.items():
            record=by_sku.get(sku)
            identity=public_index.get(sku) or {}
            if not record or identity.get("sku")!=sku or sku in processed:raise ValueError("Inconsistent public SKU mapping")
            record["storeId"]=int(identity["id"])
            install_column(record,fragment)
            processed.add(sku)
    for specification in detail_files:
        sku,sep,path=specification.partition("=")
        if not sep or sku not in by_sku:raise ValueError("Expected SKU=verified-product-page.html")
        section=OfficialStore.detail_payload(Path(path).read_bytes(),sku)
        if txt(tree(section.get("specification"))):by_sku[sku]["specSource"]=text_link(by_sku[sku]["url"],"Specification")
    for p in by_sku.values():
        column_defaults(p)
        enrich_r1000(p,by_sku)
    section_counts(db)
    write(output,CATALOG_PREFIX.encode()+packed(db)+b";\n")
    print("Exact public SKU fields:",len(processed),"of",len(by_sku))
    print(json.dumps(db["stats"],sort_keys=True))
    print("Staged",output,"SHA256",hashlib.sha256(output.read_bytes()).hexdigest())


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root",type=Path,default=ROOT)
    ap.add_argument("--cache",type=Path,help="temporary staging directory; only keep it to inspect or resume")
    ap.add_argument("--fetch-only",action="store_true")
    ap.add_argument("--apply-only",action="store_true")
    ap.add_argument("--output",type=Path,help="separate staged catalog.js; never replaces the live base")
    ap.add_argument("--detail",action="append",default=[],help="optional verified product-page sample as SKU=html-file")
    args=ap.parse_args()
    if args.fetch_only and args.apply_only:ap.error("Choose fetch-only or apply-only")
    if not args.fetch_only and not args.output:ap.error("Choose a staging path with --output")
    with tempfile.TemporaryDirectory() as tmp:
        folder=args.cache or Path(tmp)
        folder.mkdir(parents=True,exist_ok=True)
        file=args.root/"data/catalog.js"
        db=json.loads(file.read_text(encoding="utf-8").strip()[len(CATALOG_PREFIX):].rstrip(";"))
        if not args.apply_only:
            try:fetch(OfficialStore(),folder,{r["sku"] for r in db["products"]})
            except RateLimit as limited:
                print("Store rate limit. Resume after",time.ctime(limited.until),flush=True)
                raise SystemExit(2) from None
        if not args.fetch_only:
            if args.output.resolve()==file.resolve():ap.error("Choose a staging path outside the live catalog")
            print("Baseline SHA256",hashlib.sha256(file.read_bytes()).hexdigest())
            stage(db,folder,args.output,args.detail)


if __name__=="__main__":main()
