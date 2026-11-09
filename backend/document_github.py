"""Explicit maintainer access to public Seeed attachments through the installed GitHub CLI."""
import base64
import binascii
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from urllib.parse import unquote, urlsplit


class PublicGitHubCLI:
    owners={"seeed-studio":"Seeed-Studio","seeeddocument":"SeeedDocument"}

    def __init__(self):
        self.executable=shutil.which("gh")
        self.public={}
        self.last_request=0.
        self.next_request=0
        self.stop_reason=""

    def call(self,path,media="application/vnd.github+json"):
        # No shell, token access, account switching, CLI debug output, or arbitrary URL.
        if not self.executable or path.startswith(("/", "-")) or "://" in path:
            return 0,{},b""
        wait=1.1-(time.monotonic()-self.last_request)
        if wait>0:time.sleep(wait)
        self.last_request=time.monotonic()
        env=os.environ.copy()
        for field in ("GH_DEBUG","GODEBUG","DEBUG"):
            env.pop(field,None)
        env.update(GH_PROMPT_DISABLED="1",GH_NO_UPDATE_NOTIFIER="1",GH_NO_EXTENSION_UPDATE_NOTIFIER="1",NO_COLOR="1")
        command=[self.executable,"api","--hostname","github.com","--method","GET","--include","-H","Accept: "+media,
                 "-H","X-GitHub-Api-Version: 2022-11-28",path]
        try:
            response=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env=env,timeout=65)
        except (OSError,subprocess.TimeoutExpired):
            return 0,{},b""
        raw=response.stdout
        start=re.match(br"HTTP/\S+\s+(\d{3})\b",raw)
        end=re.search(br"\r?\n\r?\n",raw[:65536])
        if not start or not end:return 0,{},b""
        code=int(start[1])
        headers={}
        for line in raw[:end.start()].splitlines()[1:]:
            key,_,value=line.partition(b":")
            if key.lower() in {b"x-ratelimit-remaining",b"x-ratelimit-reset",b"retry-after"}:
                headers[key.decode("ascii").lower()]=value.strip().decode("ascii","ignore")
        body=raw[end.end():]
        if code in (401,407) or (response.returncode and code==200):
            self.stop_reason="github_cli_unavailable"
        if code==429 or (code==403 and (headers.get("retry-after") or b"secondary rate limit" in body[:2000].lower())):
            self.stop_reason="github_secondary_limit"
            retry=headers.get("retry-after","")
            self.next_request=int(time.time())+(max(60,int(retry)) if retry.isdigit() else 180)
        elif headers.get("x-ratelimit-remaining")=="0":
            end_time=headers.get("x-ratelimit-reset","")
            self.next_request=max(int(time.time())+60,int(end_time)+1 if end_time.isdigit() else 0)
        return code,headers,body

    def prepare(self,targets):
        """List only public repositories for these owners, before reading any file path."""
        code,_,raw=self.call("rate_limit")
        try:budget=json.loads(raw)["resources"]["core"]
        except (ValueError,KeyError,TypeError):budget={}
        if code!=200 or budget.get("limit",0)<=60:
            raise RuntimeError("The local GitHub CLI account is unavailable; the document queue is preserved.")
        if budget.get("remaining",0)<1 or self.next_request>time.time():
            raise RuntimeError("The account's public API limit is reached; keep the queue until its reset.")
        needed={}
        for endpoint in targets:
            p=urlsplit(endpoint).path.strip("/").split("/")
            if len(p)<5 or p[0]!="repos" or p[1].lower() not in self.owners:continue
            needed.setdefault(p[1].lower(),set()).add((p[1]+"/"+p[2]).lower())
        for owner,names in needed.items():
            for page in range(1,101):
                if self.next_request>time.time() or self.stop_reason:raise RuntimeError("GitHub requested a pause during the public repository check.")
                host_owner=self.owners[owner]
                route=f"users/{host_owner}/repos?type=owner&per_page=100&page={page}"
                code,_,data=self.call(route)
                if code!=200:raise RuntimeError("The public repository list could not be verified; the document queue is preserved.")
                items=json.loads(data)
                for item in items:
                    full=item.get("full_name","")
                    if (full.lower() in names and item.get("private") is False and item.get("visibility")=="public"
                            and item.get("owner",{}).get("login","").lower()==owner):
                        self.public[full.lower()]=full
                if len(items)<100 or names.issubset(self.public):break

    def fetch(self,urls):
        api,source=urls
        location=urlsplit(api)
        path=location.path.strip("/").split("/")
        if (location.scheme!="https" or location.netloc!="api.github.com" or len(path)<5 or path[0]!="repos" or path[3]!="contents"
                or not path[-1].lower().endswith((".pdf",".xlsx"))
                or (path[1]+"/"+path[2]).lower() not in self.public):
            return {"status":"unread","reason":"public_repository_unconfirmed","requestAttempted":False},None
        if self.next_request>time.time() or self.stop_reason:
            return {"status":"unread","reason":self.stop_reason or "github_rate_limit","retryAt":self.next_request,"requestAttempted":False},None
        code,_,body=self.call("/".join(path)+"?"+location.query)
        receipt={"githubBudget":"account","requestAttempted":bool(code)}
        if self.next_request:receipt["retryAt"]=self.next_request
        if code==200:
            limit=6_000_000 if location.path.lower().endswith(".xlsx") else 36_000_000
            try:meta=json.loads(body)
            except (ValueError,UnicodeError):meta={}
            if (not isinstance(meta,dict) or meta.get("type")!="file" or meta.get("path")!=unquote("/".join(path[4:]))
                    or not re.fullmatch(r"[0-9a-f]{40}",str(meta.get("sha",""))) or type(meta.get("size")) is not int):
                return {**receipt,"status":"unread","reason":"github_file_metadata_unverified"},None
            size=meta["size"]
            sha=meta["sha"]
            expected_blob="https://api.github.com/"+"/".join(path[:3])+"/git/blobs/"+sha
            if str(meta.get("git_url","")).lower()!=expected_blob.lower():
                return {**receipt,"status":"unread","reason":"github_file_metadata_unverified"},None
            if size>limit:return {**receipt,"status":"unread","reason":"limit_bytes","bytes":size},None
            if not meta.get("content") or meta.get("encoding")!="base64":
                if self.next_request>time.time() or self.stop_reason:
                    return {**receipt,"status":"unread","reason":self.stop_reason or "github_rate_limit"},None
                # The contents endpoint omits large inline data. Read the same
                # verified public repository's exact Git blob, still on api.github.com.
                code,_,raw=self.call("/".join(path[:3])+"/git/blobs/"+sha)
                if code==200:
                    try:meta=json.loads(raw)
                    except (ValueError,UnicodeError):meta={}
                    if not isinstance(meta,dict) or meta.get("sha")!=sha or meta.get("size")!=size or meta.get("encoding")!="base64":
                        return {**receipt,"status":"unread","reason":"github_blob_unverified"},None
            if code==200:
                try:data=base64.b64decode("".join(meta["content"].split()),validate=True)
                except (binascii.Error,ValueError,AttributeError,KeyError,TypeError):data=None
                if data is None or len(data)!=size or hashlib.sha1(b"blob "+str(size).encode("ascii")+b"\0"+data).hexdigest()!=sha:
                    return {**receipt,"status":"unread","reason":"github_blob_unverified"},None
                if self.next_request:receipt["retryAt"]=self.next_request
                return {**receipt,"finalUrl":source,"bytes":size,"gitBlobSha":sha},data
        if not code:self.stop_reason="github_cli_unavailable"
        reason=self.stop_reason or ("github_rate_limit" if self.next_request>time.time() else "http_"+str(code))
        return {**receipt,"status":"unread" if self.stop_reason or self.next_request else "failed","reason":reason,
                **({"retryAt":self.next_request} if self.next_request else {})},None
