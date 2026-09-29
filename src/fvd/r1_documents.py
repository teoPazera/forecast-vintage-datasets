"""R1 task 1 (the E7 code, run on the pilot documents only): download and extract.

    python -m fvd.r1_documents fetch     # download pilot/corpus.csv -> raw/documents/
    python -m fvd.r1_documents extract   # text/passages/{OBR,CBO}.parquet, pilot/documents.csv

Both refuse to run unless part 1 of pilot/preregistration.md is registered and
unchanged. E7 reuses this code for all documents and skips those done here.

Downloading follows the E0 rules: identified, throttled requests; Wayback
captures of the same URL when a host refuses scripts.

- OBR: the document's own download link; if that was never archived, an
  archived PDF on the OBR's domains whose file name names the title's month and
  year and shares its distinctive words, accepted only when its first pages carry
  those words (the rule E0 used for reports).
- CBO: the publication page, then the PDF it links to; if no PDF was archived,
  the page's own main text is the document.
"""

from __future__ import annotations

import calendar
import re
import sys
from pathlib import Path

import pymupdf as fitz
import pandas as pd
from bs4 import BeautifulSoup

from . import obr_web
from .http import FetchError, fetch, fetch_capture, load_sources, mark_challenged, sniff
from .paths import RAW_DOCS, ROOT, TEXT
from .r1_pilot import PILOT, verify_part1

MONTHS = [m.lower() for m in calendar.month_name if m]
_COMMON = {"the", "and", "for", "from", "with", "office", "budget", "responsibility", "obr", "report",
           "economic", "fiscal", "outlook", "efo", "on", "of", "to", "in", "a", "an", "-", "–"}


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", text.lower()) if len(w) > 2 and w not in _COMMON
            and w not in MONTHS}


def _month_year(row) -> tuple[str | None, int | None]:
    """Month and year the document is named after: the data month of a
    commentary, else the month and year in its title."""
    m = re.search(r"data month (\d{4})-(\d{2})", row.get("notes", "") or "")
    if m:
        return MONTHS[int(m.group(2)) - 1], int(m.group(1))
    t = row["title"].lower()
    mo = next((x for x in MONTHS if re.search(rf"\b{x}\b", t)), None)
    y = re.search(r"\b(20\d\d)\b", t)
    return mo, int(y.group(1)) if y else None


def _first_text(path: Path, n: int = 3) -> str:
    try:
        with fitz.open(path) as doc:
            return " ".join(doc[i].get_text() for i in range(min(n, len(doc)))).lower()
    except Exception:  # noqa: BLE001 - unreadable file: no match
        return ""


def _obr_candidates(row) -> list[str]:
    mo, y = _month_year(row)
    want = _words(row["title"])
    out = []
    for c in obr_web.archived_pdfs():
        name = c["original"].rsplit("/", 1)[-1].lower()
        if y and str(y) not in name and not re.search(rf"(?<!\d){str(y)[2:]}(?!\d)", name):
            continue
        if mo and mo not in name and not re.search(rf"{mo[:3]}(?![a-z])", name):
            continue
        # words run together in file names ("Sep2015-draft-commentaryC.pdf")
        overlap = sum(w in name for w in want)
        if want and overlap == 0:
            continue
        out.append((overlap, -int(c.get("length") or 0), c["original"]))
    return [u for *_, u in sorted(out, reverse=True)[:4]]


def fetch_obr(row) -> tuple[Path | None, str]:
    dest = RAW_DOCS / "obr" / "pilot" / row["collection"]
    try:
        return fetch(row["url"], dest, note="R1 pilot corpus"), "own link"
    except FetchError:
        pass
    mo, y = _month_year(row)
    want = _words(row["title"])

    def verify(path: Path) -> bool:
        if sniff(path) != "pdf":
            return False
        text = re.sub(r"\s+", " ", _first_text(path))
        hit = sum(w in text for w in want) / max(len(want), 1)
        return hit >= 0.6 and (not y or str(y) in text) and (not mo or mo in text)

    for cand in _obr_candidates(row):
        try:
            p = fetch_capture(row["url"], cand, dest, verify=verify,
                              note="R1 pilot corpus; own link not archived; same document archived "
                                   "under another URL, first pages verified")
        except FetchError:
            continue
        if p is not None:
            return p, f"archived elsewhere: {cand}"
    return None, "no usable archived copy"


def _cbo_pdf_link(html: str) -> str | None:
    s = BeautifulSoup(html, "lxml")
    links = [a["href"] for a in s.find_all("a", href=True) if a["href"].lower().split("?")[0].endswith(".pdf")]
    links = [re.sub(r"^https?://web\.archive\.org/web/\d+[a-z_]*/", "", h) for h in links]
    links = [("https://www.cbo.gov" + h) if h.startswith("/") else h for h in links]
    # the report itself, not a figure file or a supplemental data note
    main = [h for h in links if "/system/files/" in h and not re.search(r"figure|slides|data", h, re.I)]
    return (main or links or [None])[0]


def fetch_cbo(row) -> tuple[Path | None, str]:
    dest = RAW_DOCS / "cbo" / "pilot" / row["collection"]
    try:
        page = fetch(row["url"], dest, note="R1 pilot corpus: publication page")
    except FetchError:
        return None, "publication page not archived"
    pdf = _cbo_pdf_link(page.read_text(encoding="utf-8", errors="replace"))
    if pdf:
        try:
            return fetch(pdf, dest, note=f"R1 pilot corpus: PDF linked from {row['url']}"), f"PDF {pdf}"
        except FetchError:
            pass
    return page, "publication page (no archived PDF)"


def fetch_all() -> None:
    verify_part1()
    mark_challenged("obr.uk")
    mark_challenged("www.cbo.gov")
    cor = pd.read_csv(PILOT / "corpus.csv", dtype=str, keep_default_na=False)
    inv = pd.read_csv(ROOT / "inventory" / "documents.csv", dtype=str, keep_default_na=False)
    notes = dict(zip(inv.doc_id, inv.notes))
    out_p = PILOT / "fetch_log.csv"
    done = pd.read_csv(out_p, dtype=str, keep_default_na=False) if out_p.exists() else pd.DataFrame(
        columns=["doc_id", "path", "how"])
    have = set(done[done.path != ""].doc_id)
    rows = done.to_dict("records")
    rows = [r for r in rows if r["doc_id"] in have]
    for i, r in enumerate(cor.drop_duplicates("doc_id").to_dict("records")):
        if r["doc_id"] in have:
            continue
        r["notes"] = notes.get(r["doc_id"], "")
        path, how = (fetch_obr if r["source"] == "OBR" else fetch_cbo)(r)
        rows.append({"doc_id": r["doc_id"], "path": path.relative_to(ROOT).as_posix() if path else "", "how": how})
        print(f"{i}: {r['doc_id']} {r['title'][:50]!r}: {how[:60]}", flush=True)
        pd.DataFrame(rows).to_csv(out_p, index=False)
    d = pd.DataFrame(rows)
    print(f"{(d.path != '').sum()} of {len(d)} documents retrieved")


# --- extraction ----------------------------------------------------------------

MIN_CHARS = 30          # shorter blocks are page numbers, running heads, labels
MAX_CHARS = 1500        # longer passages are split at sentence ends into <= CHUNK
CHUNK = 1200
_END = re.compile(r"[.!?:;)\]”\"]\s*$")
_BOX = re.compile(r"^\s*box\s+[a-z]?\d+(\.\d+)?", re.I)
_LEADER = re.compile(r"(\.\s*){5,}\d*\s*$|…{2,}")        # table-of-contents lines
_BULLET = re.compile(r"(^|\s)[•■▪●◦]\s")


def _digit_share(text: str) -> float:
    toks = text.split()
    return sum(bool(re.fullmatch(r"[-–(]?[\d.,]+%?\)?", t)) for t in toks) / max(len(toks), 1)


def _split(text: str) -> list[str]:
    if len(text) <= MAX_CHARS:
        return [text]
    out, cur = [], ""
    for s in re.split(r"(?<=[.!?])\s+", text):
        if cur and len(cur) + len(s) > CHUNK:
            out.append(cur)
            cur = ""
        cur = f"{cur} {s}".strip()
    return out + ([cur] if cur else [])


def extract_pdf(path: Path) -> tuple[list[dict], dict]:
    """Passages of a PDF: text blocks in reading order, with the heading above
    them, merged across column or page breaks mid-sentence."""
    doc = fitz.open(path)
    pages, sizes = [], {}
    for pno, page in enumerate(doc, start=1):
        h = page.rect.height
        blocks = []
        for b in page.get_text("dict")["blocks"]:
            if b.get("type") != 0:
                continue
            spans = [s for ln in b["lines"] for s in ln["spans"] if s["text"].strip()]
            if not spans:
                continue
            text = re.sub(r"\s+", " ", " ".join(" ".join(s["text"] for s in ln["spans"]) for ln in b["lines"])).strip()
            size = max(spans, key=lambda s: len(s["text"]))["size"]
            bold = all(s["flags"] & 16 for s in spans)
            for s in spans:
                sizes[round(s["size"], 1)] = sizes.get(round(s["size"], 1), 0) + len(s["text"])
            blocks.append({"text": text, "size": size, "bold": bold, "y0": b["bbox"][1] / h})
        pages.append(blocks)
    n_pages = len(doc)
    chars = [sum(len(b["text"]) for b in p) for p in pages]
    doc.close()
    body = max(sizes, key=sizes.get) if sizes else 10.0
    # running heads and feet: short texts repeated on many pages
    freq: dict[str, int] = {}
    for p in pages:
        for t in {re.sub(r"\d+", "#", b["text"]) for b in p if len(b["text"]) < 120}:
            freq[t] = freq.get(t, 0) + 1
    running = {t for t, n in freq.items() if n >= max(3, 0.2 * n_pages)}

    out, section, prev = [], "", None
    for pno, p in enumerate(pages, start=1):
        for b in p:
            t = b["text"]
            if re.sub(r"\d+", "#", t) in running or len(t) < 3 or _LEADER.search(t):
                continue
            is_head = (len(t) < 150 and not _END.search(t) and _digit_share(t) < 0.3
                       and (b["size"] > body + 0.9 or (b["bold"] and len(t) < 100)))
            if is_head:
                section = t
                prev = None
                continue
            if len(t) < MIN_CHARS:
                continue
            if b["size"] < body - 0.9 and b["y0"] > 0.7:
                kind = "footnote"
            elif _digit_share(t) > 0.4 and len(t.split()) >= 5:
                kind = "table"
            elif _BOX.match(section):
                kind = "box"
            else:
                kind = "paragraph"
            same = prev is not None and kind == prev["kind"] and kind in ("paragraph", "box")
            # a sentence broken across columns or pages; a bullet list and its lead-in
            if same and ((not _END.search(prev["text"]) and t[:1].islower())
                         or (_BULLET.match(t) and (prev["text"].rstrip().endswith(":") or _BULLET.search(prev["text"])))):
                prev["text"] = f"{prev['text']} {t}"
                continue
            prev = {"page": pno, "section_path": section, "kind": kind, "text": t}
            out.append(prev)
    passages = [{**x, "text": c} for x in out for c in _split(x["text"])]
    quality = {"n_pages": n_pages, "chars_per_page": round(sum(chars) / max(n_pages, 1)),
               "empty_pages": sum(c < 50 for c in chars)}
    return passages, quality


def extract_html(path: Path) -> tuple[list[dict], dict]:
    s = BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"), "lxml")
    for t in s(["script", "style", "nav", "header", "footer", "form", "aside"]):
        t.decompose()
    main = (s.find("main") or s.find("article") or s.find("div", id=re.compile("content", re.I)) or s.body or s)
    out, section = [], ""
    for el in main.find_all(["h1", "h2", "h3", "h4", "p", "li", "table"]):
        if el.find_parent("table") is not None and el.name != "table":
            continue
        t = re.sub(r"\s+", " ", el.get_text(" ", strip=True))
        if el.name in ("h1", "h2", "h3", "h4"):
            section = t
            continue
        if len(t) < MIN_CHARS:
            continue
        kind = "table" if el.name == "table" else ("box" if _BOX.match(section) else "paragraph")
        out += [{"page": 1, "section_path": section, "kind": kind, "text": c} for c in _split(t)]
    n = sum(len(x["text"]) for x in out)
    return out, {"n_pages": 1, "chars_per_page": n, "empty_pages": int(n < 50)}


def extract_all() -> None:
    verify_part1()
    cor = pd.read_csv(PILOT / "corpus.csv", dtype=str, keep_default_na=False)
    log = pd.read_csv(PILOT / "fetch_log.csv", dtype=str, keep_default_na=False)
    src = load_sources()
    vint = pd.concat([pd.read_parquet(f) for f in sorted((ROOT / "tables" / "vintages").glob("*.parquet"))])
    obr_vid = dict(zip(vint.label, vint.vintage_id))
    cbo_vid = dict(zip(vint.primary_document_id, vint.vintage_id))
    inv = pd.read_csv(ROOT / "inventory" / "documents.csv", dtype=str, keep_default_na=False)
    vlabel = dict(zip(inv.doc_id, inv.vintage_label))
    docs, passages = [], []
    for r in cor.groupby("doc_id", sort=False).agg(
            lambda s: ";".join(dict.fromkeys(";".join(s).split(";")))).reset_index().to_dict("records"):
        r["role"] = r["role"].split(";")[0]
        f = log[log.doc_id == r["doc_id"]]
        path = ROOT / f.path.iloc[0] if len(f) and f.path.iloc[0] else None
        rec = {k: r[k] for k in ("doc_id", "source", "collection", "doc_type", "role", "title", "url",
                                 "publication_date", "date_certainty", "trajectories")}
        vid = obr_vid.get(vlabel.get(r["doc_id"], "")) if r["source"] == "OBR" else cbo_vid.get(r["doc_id"])
        row = src.get(f.path.iloc[0], {}) if path else {}
        lm = pd.to_datetime(row.get("last_modified") or None, errors="coerce", utc=True)
        pub = pd.Timestamp(r["publication_date"])
        rec.update({"vintage_id": vid or "", "path": f.path.iloc[0] if path else "",
                    "how": f.how.iloc[0] if len(f) else "not fetched", "sha256": row.get("sha256", ""),
                    "last_modified": lm.date().isoformat() if pd.notna(lm) else "",
                    "available_from": r["publication_date"],
                    "possibly_revised": bool(pd.notna(lm) and lm.tz_localize(None) > pub + pd.Timedelta(days=7))})
        kind = sniff(path) if path else ""
        if path is None:
            q, ps, status = {}, [], "unavailable"
        elif kind == "pdf":
            ps, q = extract_pdf(path)
            status = "ok" if ps else "no text layer"
        elif kind in ("html", ""):
            ps, q = extract_html(path)
            status = "ok (html)" if ps else "no text"
        else:
            q, ps, status = {}, [], f"not text ({kind})"
        rec.update({"file_type": kind, "extraction_status": status, "n_passages": len(ps),
                    "n_pages": q.get("n_pages", 0), "chars_per_page": q.get("chars_per_page", 0),
                    "empty_pages": q.get("empty_pages", 0)})
        docs.append(rec)
        passages += [{"source": r["source"], "doc_id": r["doc_id"], "passage_id": f"{r['doc_id']}_p{i:05d}", **p}
                     for i, p in enumerate(ps)]
    d, p = pd.DataFrame(docs), pd.DataFrame(passages)
    d.to_csv(PILOT / "documents.csv", index=False)
    (TEXT / "passages").mkdir(parents=True, exist_ok=True)
    from .schemas import check_columns, write_schema
    for s, g in p.groupby("source"):
        g = g[["source", "doc_id", "passage_id", "section_path", "page", "kind", "text"]]
        check_columns("text/passages", g)
        g.to_parquet(TEXT / "passages" / f"{s}.parquet", index=False)
    write_schema("text/passages", ROOT)
    print(d.groupby(["source", "role", "extraction_status"]).size().to_string())
    print(p.groupby(["source", "kind"]).size().to_string())


if __name__ == "__main__":
    {"fetch": fetch_all, "extract": extract_all}[sys.argv[1]]()
