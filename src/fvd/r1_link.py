"""R1 task 2 (the E8 code, for the pilot series only): series dictionary and
deterministic series-and-period linking.

    python -m fvd.r1_link            # pilot/series_dictionary.csv -> text/links/{OBR,CBO}.parquet
    python -m fvd.r1_link post-hoc   # pilot/post_hoc_passages.csv and a pilot/causes.csv template

The dictionary is built from series names and the forecaster's own terms (HOFD
and CBO series names, EFO table labels, PMD head names), not from case outcomes
(plan section 8, rule 6). Terms marked `proposed` are Teo's to accept or drop
before part 2 of pilot/preregistration.md is registered; only `in` terms link.

A passage is linked to (series, target period) when it names the series and
the period in the same passage:
- explicit periods: "2020-21", "2020–21", "2020/21" (UK); "fiscal year 2025",
  "FY2025" (US); a bare "2025" in a CBO document is linked but marked ambiguous,
  since it may be a calendar year;
- relative periods: "this year", "next year", "last year" and their fiscal-year
  variants, resolved against the document's publication date and marked
  ambiguous.
"""

from __future__ import annotations

import re

import pandas as pd

from .paths import ROOT, TEXT
from .r1_pilot import PILOT

DICTIONARY = [
    # series_id, term, basis, status
    ("obr.apd", "air passenger duty", "HOFD series name; EFO table label; PMD head", "in"),
    ("obr.apd", "APD", "HOFD sheet code; the OBR's abbreviation", "in"),
    ("obr.fuel", "fuel duty", "PMD head; EFO label 'Fuel duties'", "in"),
    ("obr.fuel", "fuel duties", "HOFD series name; EFO table label", "in"),
    ("obr.studentloans", "student loans", "HOFD series name; EFO table label", "in"),
    ("obr.studentloans", "student loan", "EFO table labels ('Student loan repayments')", "in"),
    ("cbo.revenue.customs_duties", "customs duties", "CBO revenue category", "in"),
    ("cbo.revenue.customs_duties", "customs duty", "singular of the category", "in"),
    ("cbo.revenue.customs_duties", "tariffs", "synonym of customs duties; also names the 2025 cause", "proposed"),
    ("cbo.outlay.other_mandatory", "other mandatory", "CBO outlay category ('other mandatory spending/programs')", "in"),
    ("cbo.revenue.miscellaneous_receipts", "miscellaneous receipts", "CBO revenue category", "in"),
    ("cbo.revenue.miscellaneous_receipts", "Federal Reserve remittances",
     "the category's main component; also names the 2023 cause", "proposed"),
]


def dictionary() -> pd.DataFrame:
    return pd.DataFrame(DICTIONARY, columns=["series_id", "term", "basis", "status"])


def _term_re(terms: list[str]) -> re.Pattern:
    # abbreviations match case-sensitively; words case-insensitively
    parts = [re.escape(t) if t.isupper() else f"(?i:{re.escape(t)})" for t in terms]
    return re.compile(r"\b(" + "|".join(parts) + r")\b")


def _uk_fy(d: pd.Timestamp) -> int:
    """First calendar year of the UK fiscal year containing d (April-March)."""
    return d.year if d.month >= 4 else d.year - 1


def _us_fy(d: pd.Timestamp) -> int:
    """US fiscal year containing d (October-September, named by its end)."""
    return d.year + 1 if d.month >= 10 else d.year


_REL = [(r"\b(this|the current) (financial |fiscal )?year\b", 0), (r"\bnext (financial |fiscal )?year\b", 1),
        (r"\b(last|previous) (financial |fiscal )?year\b", -1)]


def period_links(text: str, source: str, target: str, pub: pd.Timestamp) -> list[tuple[str, bool]]:
    """(link_type, ambiguous) for every way the passage names the target period."""
    out = []
    if source == "OBR":
        y0 = int(target[:4])
        if re.search(rf"\b{y0}\s*[-–/]\s*(20)?{str(y0 + 1)[2:]}\b", text):
            out.append(("explicit period", False))
        base = _uk_fy(pub)
    else:
        y = int(target)
        if re.search(rf"\b(fiscal year|FY)\s*'?{y}\b", text, re.I):
            out.append(("explicit period", False))
        elif re.search(rf"\b{y}\b", text):
            out.append(("year mention (fiscal or calendar)", True))
        base = _us_fy(pub)
        y0 = y
    for pat, k in _REL:
        if base + k == (y0 if source == "CBO" else int(target[:4])) and re.search(pat, text, re.I):
            out.append(("relative period resolved", True))
    return out


def build_links(passages: pd.DataFrame, docs: pd.DataFrame, cases: pd.DataFrame) -> pd.DataFrame:
    d = dictionary()
    d = d[d.status == "in"]
    pub = dict(zip(docs.doc_id, pd.to_datetime(docs.publication_date)))
    rows = []
    for c in cases.itertuples():
        pat = _term_re(d[d.series_id == c.series_id].term.tolist())
        src = passages[passages.source == c.source]
        hit = src[src.text.str.contains(pat)]
        for p in hit.itertuples():
            links = period_links(p.text, c.source, c.target_period, pub[p.doc_id])
            if links:
                rows.append({"source": c.source, "passage_id": p.passage_id, "series_id": c.series_id,
                             "target_period": c.target_period,
                             "link_type": "; ".join(dict.fromkeys(t for t, _ in links)),
                             "ambiguous": all(a for _, a in links)})
    return pd.DataFrame(rows, columns=["source", "passage_id", "series_id", "target_period", "link_type",
                                       "ambiguous"])


def post_hoc_passages() -> None:
    """For Teo's cause texts (plan R1, task 3): per pilot case, the passages of
    its post-hoc documents that name the series (proposed terms included), and a
    template pilot/causes.csv. Post-hoc text is a label source only."""
    passages = pd.concat([pd.read_parquet(f) for f in sorted((TEXT / "passages").glob("*.parquet"))])
    docs = pd.read_csv(PILOT / "documents.csv", dtype=str, keep_default_na=False)
    cases = pd.read_csv(PILOT / "pilot_cases.csv", dtype=str)
    d = dictionary()
    rows = []
    for c in cases.itertuples():
        pat = _term_re(d[d.series_id == c.series_id].term.tolist())
        ids = c.post_hoc_docs.split(";")
        p = passages[passages.doc_id.isin(ids) & passages.text.str.contains(pat)]
        p = p.merge(docs[["doc_id", "title"]], on="doc_id")
        rows += [{"trajectory_id": c.trajectory_id, "passage_id": r.passage_id, "document": r.title,
                  "page": r.page, "section": r.section_path, "text": r.text} for r in p.itertuples()]
    pd.DataFrame(rows).to_csv(PILOT / "post_hoc_passages.csv", index=False)
    tpl = PILOT / "causes.csv"
    if not tpl.exists():
        pd.DataFrame({"trajectory_id": cases.trajectory_id, "cause_id": cases.trajectory_id + "__c1",
                      "cause_text": "", "post_hoc_passage_id": "", "attribution_category": ""}).to_csv(tpl, index=False)
    print(pd.DataFrame(rows).groupby("trajectory_id").size().to_string())


def main() -> None:
    from .schemas import check_columns, write_schema
    dictionary().to_csv(PILOT / "series_dictionary.csv", index=False)
    passages = pd.concat([pd.read_parquet(f) for f in sorted((TEXT / "passages").glob("*.parquet"))])
    docs = pd.read_csv(PILOT / "documents.csv", dtype=str, keep_default_na=False)
    docs = docs[docs.role == "corpus"]           # post-hoc documents are never linked as inputs
    passages = passages[passages.doc_id.isin(docs.doc_id)]
    cases = pd.read_csv(PILOT / "pilot_cases.csv", dtype=str)
    links = build_links(passages, docs, cases)
    (TEXT / "links").mkdir(parents=True, exist_ok=True)
    for s, g in links.groupby("source"):
        check_columns("text/links", g)
        g.to_parquet(TEXT / "links" / f"{s}.parquet", index=False)
    write_schema("text/links", ROOT)
    print(links.groupby(["series_id", "target_period", "ambiguous"]).size().to_string())


if __name__ == "__main__":
    import sys
    post_hoc_passages() if sys.argv[1:2] == ["post-hoc"] else main()
