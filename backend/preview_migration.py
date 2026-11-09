"""Install a detail-only catalogue migration while retaining any pending inventory preview."""
from contextlib import closing
import hashlib
import json
import sqlite3

from .storage import CATALOG_PREFIX, read_json, write
from .updates import CHECK_FIELDS


def read_catalog(raw):
    if not raw.startswith(CATALOG_PREFIX.encode()) or not raw.rstrip().endswith(b";"):
        raise ValueError("Invalid catalogue file")
    return json.loads(raw[len(CATALOG_PREFIX):].rstrip()[:-1])


def compare_inventory(old, new):
    """Preview selections can be retained only if every compared inventory field is identical."""
    old_by_sku={p["sku"]:p for p in old["products"]}
    new_by_sku={p["sku"]:p for p in new["products"]}
    if len(old_by_sku)!=len(old["products"]) or len(new_by_sku)!=len(new["products"]) or old_by_sku.keys()!=new_by_sku.keys():
        raise ValueError("SKU set changed")
    for sku,product in old_by_sku.items():
        if any(product.get(k)!=new_by_sku[sku].get(k) for k in CHECK_FIELDS):
            raise ValueError("Preview comparison would change for "+sku)


def recover_preview(catalog_file, local):
    """Called with the service's exclusive instance lock. Recover either side of an interrupted replace."""
    path=local/"update-work.sqlite"
    if not path.is_file():return
    with closing(sqlite3.connect(path)) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='kv'").fetchone():return
        row=db.execute("SELECT v FROM kv WHERE k='detailRelease'").fetchone()
        if not row:return
        old,new=json.loads(row[0])
        installed=hashlib.sha256(catalog_file.read_bytes()).hexdigest()
        if installed not in {old,new}:raise ValueError("Unexpected catalogue file during preview recovery")
        with db:
            db.execute("UPDATE kv SET v=? WHERE k='baseDigest'",(json.dumps(installed),))
            db.execute("DELETE FROM kv WHERE k='detailRelease'")


def publish(catalog_file, local, candidate, baseline):
    """The caller holds the service's instance lock for the entire publication."""
    recover_preview(catalog_file,local)
    original=catalog_file.read_bytes()
    before=hashlib.sha256(original).hexdigest()
    after=hashlib.sha256(candidate).hexdigest()
    if before!=baseline:raise ValueError("The live catalogue changed since collection began")
    compare_inventory(read_catalog(original),read_catalog(candidate))
    dbfile=local/"update-work.sqlite"
    state=read_json(local/"update-state.json",{})
    if state.get("status")=="running":raise ValueError("Wait for the active update to finish")
    if dbfile.is_file() and state.get("status") not in {None,"done","idle"}:
        if state.get("action")!="preview":raise ValueError("A product update is pending")
        with closing(sqlite3.connect(dbfile)) as db:
            row=db.execute("SELECT v FROM kv WHERE k='baseDigest'").fetchone()
            if not row or json.loads(row[0])!=before:raise ValueError("Preview baseline mismatch")
            if db.execute("SELECT COUNT(*) FROM pending WHERE done!=0").fetchone()[0]:
                raise ValueError("A product update has already been staged")
            with db:
                db.execute("INSERT INTO kv(k,v) VALUES ('detailRelease',?)",(json.dumps([before,after]),))
    try:
        write(catalog_file,candidate)
    finally:
        recover_preview(catalog_file,local)


if __name__=="__main__":
    import argparse
    from pathlib import Path
    from .server import Instance
    from .storage import ROOT
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate",type=Path)
    parser.add_argument("--baseline",required=True,help="SHA256 of the catalogue used for staging")
    parser.add_argument("--root",type=Path,default=ROOT)
    parser.add_argument("--check",action="store_true",help="validate inventory equivalence without installing")
    args=parser.parse_args()
    catalog=args.root/"data"/"catalog.js"
    content=args.candidate.read_bytes()
    if args.check:
        raw=catalog.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=args.baseline:raise SystemExit("Baseline mismatch")
        compare_inventory(read_catalog(raw),read_catalog(content))
        print("Inventory comparison fields match for every SKU.")
    else:
        directory=args.root/".local-workbench"
        instance=Instance(directory)
        try:publish(catalog,directory,content,args.baseline)
        finally:instance.close()
        print("Catalogue published; pending inventory preview retained.")
