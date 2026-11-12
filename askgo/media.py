"""Extract and (optionally) download media from the latest assistant reply.

A single media item failing never blocks the text result: it is recorded with
ok=false and a reason, and processing continues.
"""
from __future__ import annotations

import time
from pathlib import Path

from playwright.sync_api import BrowserContext, Page

from .config import Config
from .selectors import Selectors

_EXT = {
    "image": (".png", ".jpg", ".jpeg", ".webp", ".gif"),
    "video": (".mp4", ".webm", ".mov"),
    "audio": (".mp3", ".wav", ".m4a", ".aac", ".ogg"),
}


def _kind_for_url(url: str) -> str:
    lower = url.lower().split("?")[0]
    for kind, exts in _EXT.items():
        if any(lower.endswith(e) for e in exts):
            return kind
    return "image"


def _save_one(context: BrowserContext, url: str, kind: str, media_dir: Path, ts: int) -> str:
    ext = _EXT[kind][0]
    name = f"{kind}_{ts}_{abs(hash(url)) % 100000}{ext}"
    dest = media_dir / name
    resp = context.request.get(url, timeout=60000)
    if resp.status >= 400:
        raise RuntimeError(f"HTTP {resp.status} for {url}")
    dest.write_bytes(resp.body())
    return str(dest)


def extract_media(
    page: Page,
    context: BrowserContext,
    config: Config,
    selectors: Selectors,
    save: bool = True,
) -> list[dict]:
    """Return a list of media dicts. Empty list if none found."""
    items: list[dict] = []
    # Prefer media inside the latest assistant message; fall back to whole page.
    loc = selectors.assistant(page)
    scope = loc.last if loc.count() else page.locator("body")
    found = scope.locator(selectors.media_selector)
    count = found.count()
    ts = int(time.time())
    for i in range(count):
        el = found.nth(i)
        try:
            url = el.get_attribute("src") or el.get_attribute("href") or ""
            url = (url or "").strip()
            if not url or url.startswith("data:"):
                continue
            kind = _kind_for_url(url)
            entry = {"type": kind, "url": url, "ok": False, "path": None, "reason": None}
            if not save:
                entry["ok"] = True
                items.append(entry)
                continue
            try:
                path = _save_one(context, url, kind, config.media_dir, ts + i)
                entry["ok"] = True
                entry["path"] = path
            except Exception as exc:  # noqa: BLE001 - single item must not block others
                entry["reason"] = str(exc)
            items.append(entry)
        except Exception as exc:  # noqa: BLE001
            items.append({"type": "unknown", "url": None, "ok": False, "path": None, "reason": str(exc)})
    return items
