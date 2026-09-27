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

Every download is checked for integrity (zip, OLE2 and PDF structure). Some
Wayback captures are truncated (often at exactly 1 MiB); a broken capture is
recorded as `invalid` and the next capture of the same URL is tried.
"""

from __future__ import annotations

import csv
import hashlib
import os
import re
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests

from .paths import ROOT, SOURCES_CSV

USER_AGENT = os.environ.get(
    "FVD_USER_AGENT",
    "fvd-forecast-vintage-datasets/0.1 (academic research; public-data extraction; "
    "throttled, cached; python-requests)",
)
MIN_INTERVAL_S = {"web.archive.org": 3.0}
DEFAULT_INTERVAL_S = 1.5
MAX_CAPTURE_TRIES = 6

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


def invalidate(path: Path, reason: str) -> None:
    """Mark a stored download as broken (e.g. a truncated capture) and remove it.

    The manifest row is kept with status 'invalid', its hash and the reason, so
    the failed download stays on record; the path moves into the note.
    """
    rel = path.relative_to(ROOT).as_posix()
    with open(SOURCES_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        if r["path"] == rel:
            r["status"] = "invalid"
            r["note"] = f"{r['note']}; INVALID ({reason}); was stored as {rel}".lstrip("; ")
            r["path"] = ""
    with open(SOURCES_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SOURCES_FIELDS)
        w.writeheader()
        w.writerows(rows)
    path.unlink(missing_ok=True)


# --- file integrity and naming ------------------------------------------------------

def sniff(path: Path) -> str:
    """File type from content: xlsx, zip, xls, pdf, html or bin."""
    with open(path, "rb") as f:
        head = f.read(8)
    if head.startswith(b"PK"):
        try:
            with zipfile.ZipFile(path) as z:
                names = z.namelist()
        except zipfile.BadZipFile:
            return "zip"
        return "xlsx" if "[Content_Types].xml" in names and any(n.startswith("xl/") for n in names) \
            else "zip"
    if head.startswith(b"\xd0\xcf\x11\xe0"):
        return "xls"
    if head.startswith(b"%PDF"):
        return "pdf"
    if head.lstrip()[:1] == b"<":
        return "html"
    return "bin"


def check_integrity(path: Path) -> str:
    """Empty string if the file looks complete, else the reason it does not."""
    kind = sniff(path)
    try:
        if kind in ("xlsx", "zip"):
            with zipfile.ZipFile(path) as z:
                bad = z.testzip()
            return f"corrupt member {bad}" if bad else ""
        if kind == "xls":
            import io

            import xlrd
            log = io.StringIO()   # xlrd reports truncation as a warning, not an error
            xlrd.open_workbook(str(path), on_demand=True, logfile=log).release_resources()
            return "OLE2 file truncated" if "truncated" in log.getvalue().lower() else ""
        if kind == "pdf":
            with open(path, "rb") as f:
                f.seek(max(0, path.stat().st_size - 2048))
                return "" if b"%%EOF" in f.read() else "PDF has no end-of-file marker (truncated)"
    except Exception as exc:   # any parser failure means the file is not usable
        return f"{type(exc).__name__}: {exc}"[:200]
    return ""


def safe_name(url: str) -> str:
    """File name from the last URL path segment, made filesystem-safe."""
    p = urlparse(url)
    name = unquote(Path(p.path.rstrip("/")).name) or "index"
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


def _write(r: requests.Response, tmp: Path) -> None:
    try:
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                f.write(chunk)
    except requests.RequestException as exc:
        tmp.unlink(missing_ok=True)
        raise FetchError(f"interrupted download: {exc}") from exc


# --- Wayback Machine -----------------------------------------------------------

CDX = "https://web.archive.org/cdx/search/cdx"
_WB_RE = re.compile(r"https?://web\.archive\.org/web/(\d{14})[a-z_]*/(.+)$")


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


def wayback_ordered(url: str, prefer: str = "latest") -> list[dict]:
    """Captures of `url`, best first: direct (200) captures before redirects, and
    within each the latest (or earliest) first. Query strings are ignored unless
    they select content (obr.uk's `tmstv` is a cache-buster), and redirect
    captures count, since obr.uk /download/ links redirect to the file."""
    p = urlparse(url)
    base = p.netloc + p.path
    if p.query:
        caps = wayback_captures(f"{base}?{p.query}", filter="statuscode:[23]..")
    elif p.path.rstrip("/"):
        # captures with a query string only match as a prefix; keep this path only
        caps = wayback_captures(base.rstrip("/"), match="prefix",
                                filter="statuscode:[23]..", limit="20000")
        caps = [c for c in caps
                if urlparse(c["original"]).path.rstrip("/") == p.path.rstrip("/")]
    else:
        caps = wayback_captures(base, filter="statuscode:[23]..")
    rev = prefer == "latest"
    ok = sorted([c for c in caps if c["statuscode"] == "200"], key=lambda c: c["timestamp"], reverse=rev)
    redir = sorted([c for c in caps if c["statuscode"] != "200"], key=lambda c: c["timestamp"], reverse=rev)
    # one attempt per distinct content digest is enough
    seen, out = set(), []
    for c in ok + redir:
        key = (c["digest"], c["statuscode"])
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


def _wayback_lookup(url: str, prefer: str) -> tuple[dict, int] | None:
    caps = wayback_ordered(url, prefer)
    return (caps[0], len(caps)) if caps else None


def _download_wayback(url: str, tmp_dir: Path, prefer: str, verify=None
                      ) -> tuple[Path, dict, str] | None:
    """Download the best usable capture of `url` to a temporary file.

    Returns (tmp path, metadata, content type) or None when no capture exists.
    Captures that fail the integrity check (or `verify`) are recorded as invalid
    and the next capture is tried.
    """
    caps = wayback_ordered(url, prefer)
    if not caps:
        _append_source({"url": url, "via": "wayback", "retrieved_at": _now(),
                        "status": 404, "note": "no Wayback capture"})
        return None
    tmp_dir.mkdir(parents=True, exist_ok=True)
    for cap in caps[:MAX_CAPTURE_TRIES]:
        wb_url = f"https://web.archive.org/web/{cap['timestamp']}id_/{cap['original']}"
        r = _get(wb_url)
        if r.status_code != 200:
            _append_source({"url": url, "via": "wayback", "fetched_url": wb_url,
                            "retrieved_at": _now(), "status": r.status_code,
                            "note": "capture not served"})
            continue
        tmp = tmp_dir / f".download_{hashlib.sha1(wb_url.encode()).hexdigest()[:12]}.part"
        try:
            _write(r, tmp)
        except FetchError:
            continue
        problem = check_integrity(tmp)
        if not problem and verify is not None and not verify(tmp):
            problem = "content check failed"
        m = _WB_RE.match(r.url)
        ts, orig = (m.group(1), m.group(2)) if m else (cap["timestamp"], cap["original"])
        meta = {"via": "wayback", "fetched_url": r.url, "resolved_url": orig,
                "capture_time": datetime.strptime(ts, "%Y%m%d%H%M%S")
                .replace(tzinfo=timezone.utc).isoformat(),
                "last_modified": r.headers.get("x-archive-orig-last-modified", ""),
                "note": f"{len(caps)} distinct captures of this URL"}
        if problem:
            _append_source({"url": url, "via": "wayback", "fetched_url": r.url,
                            "capture_time": meta["capture_time"], "retrieved_at": _now(),
                            "sha256": sha256_file(tmp), "bytes": tmp.stat().st_size,
                            "status": "invalid", "note": f"capture rejected: {problem}"})
            tmp.unlink()
            continue
        return tmp, meta, r.headers.get("Content-Type", "").split(";")[0]
    return None


def normalize_url(url: str) -> str:
    """Drop obr.uk's `tmstv` cache-buster so one file has one URL."""
    return re.sub(r"[?&]tmstv=\d+$", "", url)


# --- public API ----------------------------------------------------------------

def _same_resource(a: str, b: str) -> bool:
    """Same URL up to scheme, www. and port, as the Wayback index records them."""
    def key(u):
        return re.sub(r"^https?://(www\.)?([^/:]+)(:\d+)?", r"\2", u.strip()).rstrip("/").lower()
    return key(a) == key(b)


def cached_path(url: str) -> Path | None:
    """Most recently retrieved usable local copy of `url`, if any."""
    url = normalize_url(url)
    hits = [(row["retrieved_at"], rel) for rel, row in load_sources().items()
            if row["url"] == url and row["status"] == "200" and (ROOT / rel).exists()]
    return ROOT / max(hits)[1] if hits else None


def _store(tmp: Path, dest_dir: Path, name: str, url: str, meta: dict, ctype: str,
           via: str, note: str) -> Path:
    """Move a verified download into place, record it, and return its path."""
    digest = sha256_file(tmp)
    for rel, row in load_sources().items():
        if row["sha256"] == digest and row["status"] == "200" and (ROOT / rel).exists():
            tmp.unlink()
            return ROOT / rel
    if not Path(name).suffix:
        kind = sniff(tmp)
        if kind in ("xlsx", "zip", "xls", "pdf"):
            name += f".{kind}"
    dest = dest_dir / name
    if dest.exists():  # never overwrite a raw file: disambiguate by URL hash
        dest = dest.with_name(f"{dest.stem}_{hashlib.sha1(url.encode()).hexdigest()[:8]}{dest.suffix}")
    tmp.rename(dest)
    _append_source({
        "path": dest.relative_to(ROOT).as_posix(), "url": url, "via": via,
        "fetched_url": meta["fetched_url"], "capture_time": meta.get("capture_time", ""),
        "retrieved_at": _now(), "sha256": digest, "bytes": dest.stat().st_size,
        "last_modified": meta["last_modified"], "content_type": ctype, "status": 200,
        "note": "; ".join(x for x in [note, meta.get("note", "")] if x),
    })
    return dest


def record_manual(path: Path, url: str, note: str = "") -> Path:
    """Record a file downloaded by hand in a browser as the raw copy of `url`.

    Used where a host refuses scripts and no archived capture exists. The file
    stays where it was saved; its hash makes a later download checkable.
    """
    path = Path(path).resolve()
    rel = path.relative_to(ROOT).as_posix()
    if rel in load_sources():
        return path
    problem = check_integrity(path)
    if problem:
        raise FetchError(f"{rel}: {problem}")
    saved = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")
    _append_source({
        "path": rel, "url": normalize_url(url), "via": "manual", "fetched_url": url,
        "retrieved_at": saved, "sha256": sha256_file(path), "bytes": path.stat().st_size,
        "content_type": sniff(path), "status": 200,
        "note": "; ".join(x for x in ["downloaded in a browser; the server's Last-Modified "
                                      "header is not kept", note] if x),
    })
    return path


def fetch_capture(original_url: str, capture_of: str, dest_dir: Path, note: str,
                  verify=None) -> Path | None:
    """Store the Wayback capture of `capture_of` as the raw copy of `original_url`.

    Used when the source's own link was never archived but the same document
    was archived under another URL (e.g. the OBR's former domain). The
    manifest keeps both URLs. Returns None if no capture passes `verify`.
    """
    hit = cached_path(original_url)
    if hit is not None:
        # a cached copy stands for this candidate only if it was captured from it
        row = load_sources()[hit.relative_to(ROOT).as_posix()]
        return hit if _same_resource(row["fetched_url"].split("id_/", 1)[-1], capture_of) else None
    got = _download_wayback(capture_of, dest_dir, "latest", verify)
    if got is None:
        return None
    tmp, meta, ctype = got
    return _store(tmp, dest_dir, safe_name(meta["resolved_url"]), normalize_url(original_url),
                  meta, ctype, "wayback-alternate", f"{note}; capture of {capture_of}")


def fetch(url: str, dest_dir: Path, name: str | None = None, note: str = "",
          prefer: str = "latest", refresh: bool = False) -> Path:
    """Download `url` into `dest_dir` once and return the local path.

    A cached, recorded copy is returned without any request unless `refresh`.
    If the host serves a bot challenge, the Wayback capture of the same URL is
    used (`prefer` picks the latest or earliest capture). Without `name`, the
    file is named after the last path segment of the URL it resolved to, with an
    extension added from its content when the URL has none. A refreshed download
    identical to a recorded file is not stored twice.
    """
    url = normalize_url(url)
    hit = cached_path(url)
    if hit is not None and not refresh:
        return hit
    dest_dir.mkdir(parents=True, exist_ok=True)

    host = urlparse(url).netloc
    if host not in _challenged_hosts:
        r = _get(url)
        if r.status_code == 200:
            tmp = dest_dir / f".download_{hashlib.sha1(url.encode()).hexdigest()[:12]}.part"
            _write(r, tmp)
            problem = check_integrity(tmp)
            if problem:
                tmp.unlink()
                raise FetchError(f"{url}: broken download ({problem})")
            meta = {"fetched_url": r.url, "resolved_url": r.url,
                    "last_modified": r.headers.get("Last-Modified", "")}
            return _store(tmp, dest_dir, name or safe_name(r.url), url, meta,
                          r.headers.get("Content-Type", "").split(";")[0], "direct", note)
        if _is_challenge(r):
            _challenged_hosts.add(host)
            _append_source({"url": url, "via": "direct", "retrieved_at": _now(),
                            "status": r.status_code,
                            "note": "identified request refused with a bot challenge; "
                                    "host switched to Wayback captures"})
        else:
            _append_source({"url": url, "via": "direct", "retrieved_at": _now(),
                            "status": r.status_code, "note": "unavailable"})
            raise FetchError(f"{url}: HTTP {r.status_code}", status=r.status_code)

    got = _download_wayback(url, dest_dir, prefer)
    if got is None:
        raise FetchError(f"{url}: no usable Wayback capture", status=404)
    tmp, meta, ctype = got
    return _store(tmp, dest_dir, name or safe_name(meta["resolved_url"]), url, meta, ctype,
                  "wayback", note)


def fetch_page(url: str, dest_dir: Path) -> str:
    """Fetch an HTML page (cached as a raw file) and return its text."""
    path = fetch(url, dest_dir, name=page_name(normalize_url(url)))
    return path.read_text(encoding="utf-8", errors="replace")


def mark_challenged(host: str) -> None:
    """Skip direct requests to a host already known to refuse scripted clients."""
    _challenged_hosts.add(host)
