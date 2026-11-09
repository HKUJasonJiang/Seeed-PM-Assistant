"""Reconcile URL-level coverage, publication permissions, reads and request receipts."""
from collections import Counter, defaultdict
import json
from pathlib import Path
from .document_enrichment import canonical, github_file, publisher_source


def request_receipts(folder):
    receipts=defaultdict(set)
    path=Path(folder)/"document-checks.jsonl"
    if not path.is_file():return receipts
    for line in path.read_text(encoding="utf-8").splitlines():
        try:r=json.loads(line);u=canonical(r["url"])
        except (ValueError,KeyError):continue
        flags=receipts[u];reason=r.get("reason","")
        if (r.get("finalUrl") and isinstance(r.get("bytes"),int)) or r.get("sha256"):
            flags.update(("request","response"))
            # A server may return a login/error HTML page with status 200 at a
            # .pdf address. Count receipt of its response without calling the
            # payload an original document.
            if reason not in {"not_pdf","no_wiki_article","missing_article","unreadable_workbook"}:flags.add("body")
        if r.get("requestAttempted") is True:
            flags.add("request")
        elif r.get("requestAttempted") is False:
            flags.add("queueOnly")
        elif reason in ("github_rate_limit","host_cooldown"):
            # Old records did not distinguish a response from a pause checked
            # locally before the next URL. Do not count them as requests.
            flags.add("uncertain")
        elif (reason.startswith("http_") or reason in {"network","limit_bytes","redirect_other_host","invalid_redirect","redirect_limit"}
              or r.get("status") in {"parsed","empty"}):
            flags.add("request")
    return receipts


def reconcile(checks, records, receipts):
    excluded=Counter()
    outcomes={name:Counter() for name in ("completed","attemptedIncomplete","notAttempted","attemptUncertain")}
    reads=Counter()
    for url,source in checks.items():
        reason=source.get("reason","")
        mode=source["kind"]
        if mode not in {"wiki","pdf","spreadsheet","catalogue"}:excluded["otherResourceType"]+=1;continue
        if reason=="publisher_terms":excluded["publisherTerms"]+=1;continue
        if not publisher_source(url) and not github_file(url):excluded["otherPublisher"]+=1;continue
        if reason=="excluded_robots":excluded["robotsDisallow"]+=1;continue
        if reason=="robots_unverified":excluded["unverifiedSiteRules"]+=1;continue
        if reason=="publisher_source_unavailable":excluded["publisherAccessRestricted"]+=1;continue
        if reason=="public_repository_unconfirmed":excluded["unverifiedPublicRepository"]+=1;continue
        r=records.get(url,{})
        flags=set(receipts.get(url,set()))
        # This entry is present only when the global catalogue was fetched
        # and a physical page index actually saved.
        if mode=="catalogue" and source.get("status")=="parsed":flags.update(("request","response","body"))
        checkout=bool(r.get("markdownSource"))
        if checkout:reads["offlineOriginalRead"]+=1
        if "body" in flags:reads["onlineBodyRetrieved"]+=1
        if "response" in flags or "body" in flags:reads["onlineResponseBodies"]+=1
        if "request" in flags:reads["onlineRequested"]+=1
        if checkout and "body" in flags:reads["onlineAndOfflineRead"]+=1
        if checkout or "body" in flags:reads["originalReadUnion"]+=1
        if source["status"] in ("parsed","empty"):
            outcome="completed"
        elif "request" in flags or "body" in flags or checkout:
            outcome="attemptedIncomplete"
        elif "uncertain" in flags:
            outcome="attemptUncertain"
        else:
            outcome="notAttempted"
        outcomes[outcome][reason or source["status"]]+=1
    totals={key:sum(values.values()) for key,values in outcomes.items()}
    eligible=sum(totals.values())
    assert len(checks)==sum(excluded.values())+eligible
    assert reads["originalReadUnion"]==reads["onlineBodyRetrieved"]+reads["offlineOriginalRead"]-reads["onlineAndOfflineRead"]
    return {"linked":len(checks),"excluded":sum(excluded.values()),"excludedByReason":dict(excluded),"eligible":eligible,
            **totals,"byOutcomeAndReason":{key:dict(v) for key,v in outcomes.items()},
            **{k:reads[k] for k in ("onlineRequested","onlineResponseBodies","onlineBodyRetrieved","offlineOriginalRead","onlineAndOfflineRead","originalReadUnion")},
            "unit":"distinct published URL; identical documents can have multiple URLs",
            "definition":"Eligible URLs identify a supported official source and document format with no site-level access restriction. File-level HTTP errors and extraction restrictions are recorded as incomplete attempts. Offline reads use official pinned Wiki originals. An old per-host limit without an individual request receipt is shown separately."}
