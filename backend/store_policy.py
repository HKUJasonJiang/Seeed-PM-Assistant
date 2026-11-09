"""Robots path matching for the exact store/media host being requested."""
import re
from urllib.parse import urlsplit
from .storage import Problem


class Policy:
    def __init__(self,raw,agent="SeeedCatalogLocal",host="www.seeedstudio.com"):
        if isinstance(raw,bytes):
            try:raw=raw.decode("utf-8-sig")
            except UnicodeDecodeError:raise Problem("ROBOTS_UNVERIFIED",502) from None
        self.text=raw.lstrip("\ufeff")
        active=[line.partition("#")[0].strip() for line in self.text.splitlines()]
        active=[line for line in active if line]
        if active and (re.search(r"<(?:!doctype\b|/?(?:html|body|head|script|title|error)\b)","\n".join(active[:12]),re.I)
                or active[0][0] in "<[{" or not any(re.match(r"(?:user-agent|sitemap|host)\s*:\s*\S",line,re.I) for line in active)):
            raise Problem("ROBOTS_UNVERIFIED",502)
        self.host=host
        groups=[];agents=[];rules=[]
        for raw_line in self.text.splitlines()+["User-agent: __end__"]:
            name,sep,value=raw_line.partition("#")[0].partition(":")
            if not sep:continue
            name=name.strip().lower();value=value.strip()
            if name=="user-agent":
                if rules:groups.append((agents,rules));agents=[];rules=[]
                agents.append(value.casefold())
            elif name in ("disallow","allow","crawl-delay") and agents:rules.append((name,value))
        specific=[rules for agents,rules in groups if any(a!="*" and a in agent.casefold() for a in agents)]
        selected=specific or [rules for agents,rules in groups if "*" in agents]
        self.rules=[];self.delay=1
        for rules in selected:
            for command,value in rules:
                if command=="crawl-delay":
                    try:self.delay=max(self.delay,float(value))
                    except ValueError:pass
                elif value:
                    rx=re.escape(value.rstrip("$")).replace(r"\*",".*")+("$" if value.endswith("$") else "")
                    self.rules.append((re.compile("^"+rx),len(value.replace("*","").rstrip("$")),command=="allow"))

    def allows(self,url):
        u=urlsplit(url)
        if u.scheme!="https" or u.hostname!=self.host:return False
        target=u.path+("?"+u.query if u.query else "")
        return max(((n,ok) for rx,n,ok in self.rules if rx.search(target)),default=(0,True))[1]
