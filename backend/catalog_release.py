"""Prepare a checked public catalogue. This command never opens a user's profile."""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

from .storage import CATALOG_PREFIX, ROOT, packed, write


def inventory_digest(catalog):
    """Hash precisely the official directory fields evaluated by a change preview."""
    from .updates import CHECK_FIELDS
    seen=set()
    rows=[]
    for p in sorted(catalog["products"],key=lambda row:row["sku"].casefold()):
        sku=p["sku"].casefold()
        if sku in seen:
            raise ValueError("Duplicate SKU in public catalogue")
        seen.add(sku)
        row=[p["sku"]]
        for key in CHECK_FIELDS:
            value=p.get(key)
            row.append(sorted(value or []) if key in {"paths","groups"} else value)
        rows.append(row)
    return hashlib.sha256(packed(rows)).hexdigest()


def read_public(file):
    raw=Path(file).read_bytes()
    decoded=raw.decode("utf-8-sig").strip()
    if not decoded.startswith(CATALOG_PREFIX) or not decoded.endswith(";"):
        raise ValueError("Invalid public catalogue format")
    return raw,json.loads(decoded[len(CATALOG_PREFIX):-1])


def merge_wiki_buttons(catalog,evidence):
    def wiki_key(url):
        u=urlsplit(url)
        return u.hostname,u.path.rstrip("/")
    by_sku={p["sku"]:p for p in catalog["products"]}
    added=0
    for hit in evidence["products"]:
        p=by_sku.get(hit["sku"])
        if not p:continue
        existing={wiki_key(w["url"]) for w in p.get("wikiLinks",[])+p.get("wikiEvidence",[])}
        for w in hit["wikiLinks"]:
            key=wiki_key(w["url"])
            if key not in existing:
                p.setdefault("wikiLinks",[]).append(w)
                existing.add(key)
                added+=1
    catalog["audit"]["wikiRepository"]={key:value for key,value in evidence.items() if key in {"repository","revision","files","read","matchedSkus","pages","purchasePages","purchaseSkus","declaredPages","verifiedDeclaredPages","verifiedDeclaredSkus"}}
    catalog["audit"]["wikiRepository"]["addedLinks"]=added


def prepare(stage,documents,output,root=ROOT):
    from .catalog_images import reconcile_images
    from .document_merge import merge_document_evidence
    from .extract import section_counts
    stage,root,output=Path(stage).resolve(),Path(root).resolve(),Path(output).resolve()
    if stage.is_relative_to(root) or output.is_relative_to(root):
        raise ValueError("Stage the release outside the installed workspace")
    old_bytes,old=read_public(root/"data/catalog.js")
    _,catalog=read_public(stage/"catalog.js")
    audit=catalog["audit"]
    digest=hashlib.sha256(old_bytes).hexdigest()
    if digest!=json.loads((stage/"run.json").read_text(encoding="utf-8"))["baseDigest"]:
        raise ValueError("The installed catalogue changed during collection")
    old_skus={p["sku"] for p in old["products"]}
    new_skus={p["sku"] for p in catalog["products"]}
    if not old_skus<=new_skus or len(new_skus)!=len(catalog["products"]):
        raise ValueError("Existing SKU coverage or uniqueness changed unexpectedly")
    if (stage/"wiki-purchases.json").is_file():
        merge_wiki_buttons(catalog,json.loads((stage/"wiki-purchases.json").read_text(encoding="utf-8")))
    if "supplementarySkuLookup" not in audit and (stage/"paper-sku-lookup.json").is_file():
        search=json.loads((stage/"paper-sku-lookup.json").read_text(encoding="utf-8"))
        audit["supplementarySkuLookup"]={key:search[key] for key in ("checkedAt","source","requested","totalCount")}
    audit["documents"]=merge_document_evidence(catalog,documents)
    audit["images"]=reconcile_images(old,catalog,root,stage)
    section_counts(catalog)
    skus=catalog["products"];stats=catalog["stats"]
    stats["images"]=audit["images"]["verifiedSkus"]
    stats["documentCheckedProducts"]=sum(bool((p.get("documentAudit") or {}).get("checked")) for p in skus)
    stats["documentEvidenceProducts"]=sum(bool(p.get("verifiedDocumentRows")) for p in skus)
    stats["specProducts"]=sum(bool(p.get("specTables") or p.get("specText") or
        (p.get("referenceSections",{}).get("certification_info_tech") or {}).get("tables") or
        (p.get("referenceSections",{}).get("certification_info_tech") or {}).get("text")) for p in skus)
    before,after=inventory_digest(old),inventory_digest(catalog)
    additions=[p for p in skus if p["sku"] not in old_skus]
    unchanged_before=inventory_digest({"products":[p for p in skus if p["sku"] in old_skus]})==before
    if unchanged_before and all(p.get("catalogStatus")=="live_secondary" for p in additions):
        audit["previewCompatibility"]={"sourceDigest":digest,"fieldsDigest":after,"addedSkus":[p["sku"] for p in additions]}
    else:audit.pop("previewCompatibility",None)
    write(output,CATALOG_PREFIX.encode()+packed(catalog)+b";\n")
    return stats


def install_prepared(stage,prepared,root=ROOT):
    """Install a completed public release after the local workbench has been stopped."""
    from .catalog_images import valid_image

    stage,prepared,root=Path(stage).resolve(),Path(prepared).resolve(),Path(root).resolve()
    if stage.is_relative_to(root) or not prepared.is_relative_to(stage):
        raise ValueError("Install only a reviewed public release from its external staging directory")
    data=root/"data/catalog.js"
    current,previous=read_public(data)
    raw,candidate=read_public(prepared)
    expected=json.loads((stage/"run.json").read_text(encoding="utf-8"))["baseDigest"]
    if hashlib.sha256(current).hexdigest()!=expected:
        raise ValueError("The installed public catalogue changed since this review started")
    detail=candidate["audit"]["detail"]
    if detail["unread"] or detail["all"]!=len(candidate["products"]) or not candidate["audit"].get("documents"):
        raise ValueError("The candidate does not contain the completed catalogue and document review")
    existing={p["sku"] for p in previous["products"]}
    reviewed={p["sku"] for p in candidate["products"]}
    if not existing<=reviewed or len(reviewed)!=len(candidate["products"]):
        raise ValueError("The candidate is missing existing or unique SKU records")
    photos={p["image"] for p in candidate["products"] if p.get("image")}
    for photo in sorted(photos):
        if valid_image(root,photo):continue
        if not valid_image(stage,photo):
            raise ValueError("Main photo unavailable or its content hash does not match: "+str(photo))
        write(root/photo,(stage/photo).read_bytes())
    if hashlib.sha256(data.read_bytes()).hexdigest()!=expected:
        raise ValueError("The installed public catalogue changed while its images were being verified")
    write(data,raw)
    return {"products":len(reviewed),"photos":len(photos),"sha256":hashlib.sha256(raw).hexdigest()}


if __name__=="__main__":
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stage",required=True,type=Path)
    ap.add_argument("--documents",type=Path)
    ap.add_argument("--output",type=Path)
    ap.add_argument("--install-reviewed",type=Path,help="Install the final reviewed file after stopping the workbench")
    args=ap.parse_args()
    if args.install_reviewed:
        if args.documents or args.output:ap.error("Use --install-reviewed by itself with --stage")
        print(install_prepared(args.stage,args.install_reviewed))
    else:
        if not args.documents or not args.output:ap.error("Preparation requires --documents and --output")
        print(prepare(args.stage,args.documents,args.output))
