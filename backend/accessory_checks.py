"""Attach reproducible public-store checks to accessories during an explicit catalogue refresh."""
from datetime import datetime, timezone
import json
from pathlib import Path

PREFIX="window.SEEED_ACCESSORY_LOOKUP="


def read_reports(root):
    path=Path(root)/"data/accessory-lookup.js"
    if not path.is_file():
        return {}
    text=path.read_text("utf-8-sig").strip()
    if not text.startswith(PREFIX):
        return {}
    try:
        return json.loads(text[len(PREFIX):].rstrip(";")).get("rows",{})
    except (ValueError,AttributeError):
        return {}


def attach_checks(product, known, remote, reports):
    from .bazaar_lookup import check_accessory
    from .storefront import RateLimit
    if not callable(getattr(remote,"public_query",None)):
        return
    for item in product.get("accessories",[]):
        name=item.get("name","")
        code=item.get("sku") or item.get("publishedSku") or ""
        if not name or code.casefold() in known:
            continue
        key=json.dumps([name,code],ensure_ascii=False,separators=(",",":"))
        report=reports.get(key)
        fresh=False
        if report:
            try:
                age=datetime.now(timezone.utc)-datetime.fromisoformat(report.get("checkedAt",""))
                fresh=age.total_seconds()<7*86400 and report.get("status") not in {"rate_limited","source_error"}
            except (ValueError,TypeError):
                pass
        if not fresh:
            previous=item.get("bazaarCheck") or report
            failure=getattr(remote,"accessory_lookup_failure",None)
            report=({"query":name,"expectedSku":code,"checkedAt":datetime.now(timezone.utc).isoformat(timespec="seconds"),
                     "status":"source_error","error":failure,"candidates":[]} if failure
                    else check_accessory(name,remote,code,item.get("productUrl","")))
            if report.get("status") in {"source_error","excluded"}:
                remote.accessory_lookup_failure=report.get("error") or "ACCESSORY_CHECK_FAILED"
                if previous:
                    report["lastSuccessful"]=previous if previous.get("status") in {"confirmed","candidates"} else previous.get("lastSuccessful")
            reports[key]=report
            if report.get("status")=="rate_limited":
                raise RateLimit(report["retryAfter"])
        item["bazaarCheck"]={k:v for k,v in report.items() if k not in {"hostSkus","accessorySource"}}
