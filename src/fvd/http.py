"""Polite, caching HTTP client that records provenance for every raw file.

Rules (plan section 2):
- every request identifies the client and is throttled per host;
- every download is stored once and never overwritten;
- every download is recorded in inventory/sources.csv with URL, retrieval
  timestamp, SHA-256, size and the server's Last-Modified header;
- refused requests are recorded and retried with fuller headers before the
  file is declared unavailable.

Both obr.uk (Cloudflare) and cbo.gov (DataDome) answer every scripted request
with a browser challenge, whatever the client sends. We do not try to defeat
those challenges. After a host has refused an identified request, files from
that host are taken from the Internet Archive's Wayback Machine capture of the
same original URL, and the capture time is recorded (`via = wayback`).
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

import requests

from .paths import ROOT, SOURCES_CSV

USER_AGENT = os.environ.get(
    "FVD_USER_AGENT",
    "fvd-forecast-vintage-datasets/0.1 (academic research; public-data extraction; "
    "throttled, cached; python-requests)",
)
MIN_INTERVAL_S = {"web.archive.org": 3.0}
DEFAULT_INTERVAL_S = 1.5

SOURCES_FIELDS = [
    "path", "url", "via", "fetched_url", "capture_time", "retrieved_at", "sha256",
    "bytes", "last_modified", "content_type", "status", "note",
]

_session = requests.Session()
_session.headers.update({"User-Agent": USER_AGENT})
_last_request: dict[str, float] = {}
_challenged_hosts: set[str] = set()


class FetchError(RuntimeError):
    def __init__(self, msg: str, status: int | None = None):
        super().__init__(msg)
        self.status = status


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _throttle(url: str) -> None:
    host = urlparse(url).netloc
    interval = MIN_INTERVAL_S.get(host, DEFAULT_INTERVAL_S)
    wait = interval - (time.monotonic() - _last_request.get(host, 0.0))
    if wait > 0:
        time.sleep(wait)
    _last_request[host] = time.monotonic()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# --- provenance manifest -----------------------------------------------------

def load_sources() -> dict[str, dict]:
    if not SOURCES_CSV.exists():
        return {}
    with open(SOURCES_CSV, newline="", encoding="utf-8") as f:
        return {row["path"]: row for row in csv.DictReader(f) if row["path"]}


def _append_source(row: dict) -> None:
    SOURCES_CSV.parent.mkdir(parents=True, exist_ok=True)
    new = not SOURCES_CSV.exists()
    with open(SOURCES_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SOURCES_FIELDS)
        if new:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in SOURCES_FIELDS})


# --- naming --------------------------------------------------------------------

def safe_name(url: str) -> str:
    """File name from the last URL path segment, made filesystem-safe."""
    p = urlparse(url)
    name = unquote(Path(p.path).name) or "index"
    if p.query:
        name += "_" + hashlib.sha1(p.query.encode()).hexdigest()[:8]
    return re.sub(r"[^\w.\-]+", "_", name)[:150]


def page_name(url: str) -> str:
    """File name for an HTML page, from host and path."""
    p = urlparse(url)
    slug = re.sub(r"[^\w\-]+", "_", (p.netloc + p.path).strip("/"))[:140]
    if p.query:
        slug += "_" + hashlib.sha1(p.query.encode()).hexdigest()[:8]
    return slug + ".html"


# --- low-level GET -------------------------------------------------------------

def _is_challenge(r: requests.Response) -> bool:
    if r.status_code not in (403, 429, 503):
        return False
    body = r.text[:2000] if "html" in r.headers.get("Content-Type", "") else ""
    return ("Just a moment" in body or "captcha-delivery" in body
            or r.headers.get("X-DataDome") == "protected"
            or r.headers.get("cf-mitigated") == "challenge")


def _get(url: str) -> requests.Response:
    r = None
    for attempt in range(4):
        _throttle(url)
        try:
            r = _session.get(url, timeout=180, stream=True, allow_redirects=True)
        except requests.RequestException as exc:
            if attempt == 3:
                raise FetchError(f"{url}: {exc}") from exc
            time.sleep(10 * (attempt + 1))
            continue
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(15 * (attempt + 1))
            continue
        return r
    return r


# --- Wayback Machine -----------------------------------------------------------

CDX = "https://web.archive.org/cdx/search/cdx"


def wayback_captures(url: str, match: str = "exact", **params) -> list[dict]:
    """Successful captures of `url` (or of a prefix with match='prefix')."""
    q = {"url": url, "output": "json", "matchType": match,
         "fl": "timestamp,original,mimetype,statuscode,digest,length",
         "filter": "statuscode:200"}
    q.update(params)
    _throttle(CDX)
    r = None
    for attempt in range(4):
        try:
            r = _session.get(CDX, params=q, timeout=300)
            if r.status_code == 200:
                break
        except requests.RequestException:
            pass
        time.sleep(20 * (attempt + 1))
    if r is None or r.status_code != 200:
        raise FetchError(f"CDX query failed for {url}")
    rows = r.json() if r.text.strip() else []
    if not rows:
        return []
    head = rows[0]
    return [dict(zip(head, row)) for row in rows[1:]]


_WB_RE = re.compile(r"https?://web\.archive\.org/web/(\d{14})[a-z_]*/(.+)$")


def _wayback_lookup(url: str, prefer: str) -> tuple[dict, int] | None:
    """Pick a capture of `url`. Query strings are ignored (they are cache-busters
    on obr.uk), and redirect captures count, since /download/ links redirect."""
    p = urlparse(url)
    base = p.netloc + p.path
    if p.path.rstrip("/"):
        # Captures carrying a query string (e.g. ?tmstv=...) only match as a
        # prefix; the prefix also returns deeper paths, so keep this path only.
        caps = wayback_captures(base.rstrip("/"), match="prefix",
                                filter="statuscode:[23]..", limit="20000")
        caps = [c for c in caps
                if urlparse(c["original"]).path.rstrip("/") == p.path.rstrip("/")]
    else:
        caps = wayback_captures(base, filter="statuscode:[23]..")
    if not caps:
        return None
    caps.sort(key=lambda c: (c["statuscode"] != "200", c["timestamp"]))
    ok = [c for c in caps if c["statuscode"] == "200"] or caps
    ok.sort(key=lambda c: c["timestamp"])
    return (ok[-1] if prefer == "latest" else ok[0]), len(caps)


def _get_wayback(url: str, prefer: str) -> tuple[requests.Response, dict]:
    found = _wayback_lookup(url, prefer)
    if found is None:
        _append_source({"url": url, "via": "wayback", "retrieved_at": _now(),
                        "status": 404, "note": "no Wayback capture"})
        raise FetchError(f"{url}: no Wayback capture", status=404)
    cap, n = found
    wb_url = f"https://web.archive.org/web/{cap['timestamp']}id_/{cap['original']}"
    r = _get(wb_url)
    if r.status_code != 200:
        raise FetchError(f"{wb_url}: HTTP {r.status_code}", status=r.status_code)
    m = _WB_RE.match(r.url)
    ts, orig = (m.group(1), m.group(2)) if m else (cap["timestamp"], cap["original"])
    meta = {
        "via": "wayback", "fetched_url": r.url, "resolved_url": orig,
        "capture_time": datetime.strptime(ts, "%Y%m%d%H%M%S")
        .replace(tzinfo=timezone.utc).isoformat(),
        "last_modified": r.headers.get("x-archive-orig-last-modified", ""),
        "note": f"{n} captures of this URL",
    }
    return r, meta


def _write(r: requests.Response, tmp: Path) -> None:
    with open(tmp, "wb") as f:
        for chunk in r.iter_content(1 << 16):
            f.write(chunk)


def normalize_url(url: str) -> str:
    """Drop obr.uk's `tmstv` cache-buster so one file has one URL."""
    return re.sub(r"[?&]tmstv=\d+$", "", url)


# --- public API ----------------------------------------------------------------

def cached_path(url: str) -> Path | None:
    """Most recently retrieved local copy of `url`, if any."""
    url = normalize_url(url)
    hits = [(row["retrieved_at"], rel) for rel, row in load_sources().items()
            if row["url"] == url and row["status"] == "200" and (ROOT / rel).exists()]
    return ROOT / max(hits)[1] if hits else None


def fetch(url: str, dest_dir: Path, name: str | None = None, note: str = "",
          prefer: str = "latest", refresh: bool = False) -> Path:
    """Download `url` into `dest_dir` once and return the local path.

    A cached, recorded copy is returned without any request unless `refresh`.
    If the host serves a bot challenge, the Wayback capture of the same URL is
    used (`prefer` picks the latest or earliest capture). Without `name`, the
    file is named after the last path segment of the URL it resolved to. A
    refreshed download identical to a recorded file is not stored twice.
    """
    url = normalize_url(url)
    hit = cached_path(url)
    if hit is not None and not refresh:
        return hit
    dest_dir.mkdir(parents=True, exist_ok=True)

    host = urlparse(url).netloc
    meta: dict = {}
    r = None
    if host not in _challenged_hosts:
        r = _get(url)
        if r.status_code == 200:
            meta = {"via": "direct", "fetched_url": r.url, "resolved_url": r.url,
                    "last_modified": r.headers.get("Last-Modified", "")}
        elif _is_challenge(r):
            _challenged_hosts.add(host)
            _append_source({"url": url, "via": "direct", "retrieved_at": _now(),
                            "status": r.status_code,
                            "note": "identified request refused with a bot challenge; "
                                    "host switched to Wayback captures"})
            r = None
        else:
            _append_source({"url": url, "via": "direct", "retrieved_at": _now(),
                            "status": r.status_code, "note": "unavailable"})
            raise FetchError(f"{url}: HTTP {r.status_code}", status=r.status_code)
    if r is None:
        r, meta = _get_wayback(url, prefer)

    dest = dest_dir / (name or safe_name(meta["resolved_url"]))
    if dest.exists():  # never overwrite a raw file: disambiguate by URL hash
        dest = dest.with_name(f"{dest.stem}_{hashlib.sha1(url.encode()).hexdigest()[:8]}"
                              f"{dest.suffix}")
    tmp = dest.with_suffix(dest.suffix + ".part")
    _write(r, tmp)
    digest = sha256_file(tmp)
    for rel, row in load_sources().items():
        if row["sha256"] == digest and (ROOT / rel).exists():
            tmp.unlink()
            return ROOT / rel
    tmp.rename(dest)
    _append_source({
        "path": dest.relative_to(ROOT).as_posix(), "url": url, "via": meta["via"],
        "fetched_url": meta["fetched_url"], "capture_time": meta.get("capture_time", ""),
        "retrieved_at": _now(), "sha256": sha256_file(dest), "bytes": dest.stat().st_size,
        "last_modified": meta["last_modified"],
        "content_type": r.headers.get("Content-Type", "").split(";")[0],
        "status": 200, "note": "; ".join(x for x in [note, meta.get("note", "")] if x),
    })
    return dest


def fetch_page(url: str, dest_dir: Path) -> str:
    """Fetch an HTML page (cached as a raw file) and return its text."""
    path = fetch(url, dest_dir, name=page_name(normalize_url(url)))
    return path.read_text(encoding="utf-8", errors="replace")


def mark_challenged(host: str) -> None:
    """Skip direct requests to a host already known to refuse scripted clients."""
    _challenged_hosts.add(host)
