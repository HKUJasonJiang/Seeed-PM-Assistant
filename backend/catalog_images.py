"""Verify catalogue JPEGs, reuse unchanged official sources and stage missing main photos."""
import hashlib
from io import BytesIO
from pathlib import Path
import re
import time
from urllib.parse import urlsplit

from PIL import Image

from .storage import Problem
from .storefront import OfficialStore, RateLimit, is_official


JPEG_PATH = re.compile(r"data/jpg/([a-f0-9]{64})\.jpg\Z")
IMAGE_HOSTS = {"media-cdn.seeedstudio.com", "www.seeedstudio.com"}


def valid_image(root, image):
    match = JPEG_PATH.fullmatch(image or "")
    if not match:
        return False
    try:
        raw = (root / image).read_bytes()
        if hashlib.sha256(raw).hexdigest() != match.group(1):
            return False
        with Image.open(BytesIO(raw)) as bitmap:
            if bitmap.format != "JPEG":
                return False
            bitmap.verify()
        return True
    except (OSError, ValueError):
        return False


class PhotoStore(OfficialStore):
    def __init__(self):
        self.origin = ""
        self.unavailable = set()
        super().__init__()

    def redirect_allowed(self, url):
        return urlsplit(url).hostname == self.origin and super().redirect_allowed(url)

    def fetch_photo(self, source, stage):
        if not is_official(source) or urlsplit(source).hostname not in IMAGE_HOSTS:
            raise Problem("IMAGE_EXTERNAL_SOURCE")
        self.origin = urlsplit(source).hostname
        if self.origin in self.unavailable:
            raise Problem("robots_unverified")
        try:
            self.policy_for(source)
        except Problem:
            self.unavailable.add(self.origin)
            raise Problem("robots_unverified") from None
        return self.main_image(source, stage)


def reconcile_images(previous, candidate, root, stage):
    """Only downloads official sources without an intact local image. Resume reuses the stage."""
    import json
    from .storage import packed, write

    root, stage = Path(root), Path(stage)
    if root.resolve() == stage.resolve():
        raise ValueError("Stage images separately from the installed catalogue")
    cache = stage / "photo-progress.json"
    saved = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else {}
    checked = {}
    sources = {}
    for product in previous["products"]:
        path = product.get("image", "")
        if path and product.get("imageUrl"):
            if path not in checked:
                checked[path] = valid_image(root, path)
            if checked[path]:
                sources[product["imageUrl"]] = path
    remote = PhotoStore()
    errors = {}
    reused = downloaded = missing = 0
    cooldown = saved.get("retryAfter", {})
    unavailable = saved.get("rulesUnavailableUntil", {})
    for product in candidate["products"]:
        src = product.get("imageUrl")
        product["image"] = ""
        if not src or "placeholder" in src.casefold():
            missing += 1
            continue
        if src in sources:
            product["image"] = sources[src]
            reused += 1
            continue
        if src in errors:
            continue
        host = urlsplit(src).hostname
        if cooldown.get(host, 0) > time.time():
            errors[src] = "rate_limited"
            continue
        if unavailable.get(host, 0) > time.time():
            errors[src] = "robots_unverified"
            continue
        staged = saved.get("photos", {}).get(src)
        if not staged or not valid_image(stage, staged):
            try:
                staged = remote.fetch_photo(src, stage)
            except RateLimit as error:
                cooldown[host] = error.until
                errors[src] = "rate_limited"
            except Problem as error:
                errors[src] = error.code
                if error.code=="robots_unverified":
                    unavailable[host]=time.time()+3600
            if src not in errors:
                saved.setdefault("photos", {})[src] = staged
            saved["retryAfter"] = cooldown
            saved["rulesUnavailableUntil"] = unavailable
            write(cache, packed(saved))
        if src not in errors:
            sources[src] = product["image"] = staged
            downloaded += 1
    paths = {p["image"] for p in candidate["products"] if p.get("image")}
    for product in candidate["products"]:
        reason=errors.get(product.get("imageUrl"))
        if reason:
            product["photoUnavailable"]=reason
        else:
            product.pop("photoUnavailable",None)
    return {
        "verifiedSkus": sum(bool(p["image"]) for p in candidate["products"]),
        "verifiedFiles": len(paths), "reusedSkus": reused, "stagedSources": downloaded,
        "missingSourceSkus": missing, "failedSkus": sum(p.get("imageUrl") in errors for p in candidate["products"]),
        "sourceFailures": [{"url": src, "reason": code} for src, code in errors.items()]
    }
