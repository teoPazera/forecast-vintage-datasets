"""Stage R1, part 1: pilot case selection and corpus (plan R1; D17, D18, D19).

    python -m fvd.r1_pilot plan        # coverage, pilot cases and corpus -> pilot/
    python -m fvd.r1_pilot register    # hash part 1 of pilot/preregistration.md and its inputs

Which target periods a post-hoc document covers is derived from the inventory's
titles and publication dates only (plan R1), never from document text:

- OBR forecast evaluation report (the main report): the UK fiscal year that
  ended most recently before publication (years end 31 March);
- CBO accuracy report: the US fiscal year that ended most recently before
  publication (years end 30 September);
- CBO evaluation report: the fiscal years of the range its title names
  ("from 1984 to 2023"), for the series its title names (deficits and debt,
  outlays, revenue); none if the title names no range.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import date, datetime, timezone

import pandas as pd

from .paths import CASES, INVENTORY, ROOT, TABLES

PILOT = ROOT / "pilot"


def _last_fy_end(d: date, month: int) -> int:
    """Calendar year of the most recent fiscal-year end (last day of `month`)
    strictly before d."""
    return d.year if (d.month, d.day) > (month, 31 if month == 3 else 30) else d.year - 1


def coverage() -> pd.DataFrame:
    """One row per (post-hoc document, source, target period) it covers."""
    docs = pd.read_csv(INVENTORY / "documents.csv", dtype=str, keep_default_na=False)
    post = docs[docs.doc_type == "post_hoc_evaluation"]
    rows = []
    for r in post.itertuples():
        d = date.fromisoformat(r.publication_date) if r.publication_date else None
        periods, rule, subject = [], "", ""
        if r.collection == "fer" and r.primary == "True" and d:
            y = _last_fy_end(d, 3)                     # UK year ends 31 March of y
            periods, rule = [f"{y - 1}-{str(y)[2:]}"], "FER: UK fiscal year ended before publication"
        elif r.collection == "cbo_accuracy" and d:
            y = _last_fy_end(d, 9)                     # US FY y ends 30 September y
            periods, rule = [str(y)], "accuracy report: US fiscal year ended before publication"
        elif r.collection == "cbo_evaluation":
            m = re.search(r"from (\d{4}) to (\d{4})", r.title, re.I)
            if m:
                periods = [str(y) for y in range(int(m.group(1)), int(m.group(2)) + 1)]
                rule = "evaluation: fiscal years and series named in the title"
                t = r.title.lower()
                subject = "|".join(k for k, w in (("deficit", "deficit"), ("debt", "debt"), ("outlay", "outlay"),
                                                  ("revenue", "revenue")) if w in t)
        for p in periods:
            rows.append({"doc_id": r.doc_id, "source": r.source, "title": r.title,
                         "publication_date": r.publication_date, "target_period": p, "rule": rule,
                         "series_component": subject})
    return pd.DataFrame(rows)


def pilot_candidates(p: int = 3) -> pd.DataFrame:
    cases = pd.read_parquet(CASES / "cases.parquet")
    cov = coverage()
    # series component as CBO ids name it: cbo.<component>.<name>
    comp = cases.series_id.str.split(".").str[1]
    cases["post_hoc_docs"] = [
        cov[(cov.source == s) & (cov.target_period == t)
            & ((cov.series_component == "") | cov.series_component.str.split("|").apply(lambda x: c in x))
            ].doc_id.tolist()
        for s, t, c in zip(cases.source, cases.target_period, comp)]
    cases["covered"] = cases.post_hoc_docs.str.len() > 0
    return cases.sort_values(["source", "case_rank"])


def select_pilot(p: int = 3) -> pd.DataFrame:
    """Top p covered cases per source by score, skipping a case whose series was
    already picked, or is the parent or child of a picked case's series in the
    same target period (Teo, 29 September 2026: distinct cases)."""
    c = pilot_candidates()
    series = pd.concat([pd.read_parquet(f) for f in sorted((TABLES / "series").glob("*.parquet"))])
    parent = dict(zip(series.series_id, series.parent_series_id))
    out = []
    for src, g in c[c.covered].groupby("source"):
        picked = []
        for _, r in g.sort_values("case_rank").iterrows():
            if len(picked) == p:
                break
            if any(r.series_id == q.series_id or (r.target_period == q.target_period and
                   (parent.get(r.series_id) == q.series_id or parent.get(q.series_id) == r.series_id))
                   for q in picked):
                continue
            picked.append(r)
        out += picked
    d = pd.DataFrame(out)
    d["pilot_rank"] = d.groupby("source").cumcount() + 1
    return d


# Documents the pilot reads: the forecaster's own text. Spreadsheets
# (forecast_tables) are numbers already parsed in E1-E3; post-hoc documents are
# labels only (section 8, rule 4).
CORPUS_TYPES = ["forecast_narrative", "in_period_commentary", "other"]


def windows(pilot: pd.DataFrame) -> pd.DataFrame:
    """D18: from the first vintage that forecast the target to the last vintage
    of the lead-time window."""
    cells = pd.concat([pd.read_parquet(f) for f in sorted((TABLES / "cells").glob("*.parquet"))])
    cells = cells[cells.forecaster.isin(["OBR", "CBO"]) & cells.in_revision_chain]
    vint = pd.concat([pd.read_parquet(f) for f in sorted((TABLES / "vintages").glob("*.parquet"))])
    pub = dict(zip(vint.vintage_id, pd.to_datetime(vint.publication_date)))
    rows = []
    for r in pilot.itertuples():
        t = cells[(cells.series_id == r.series_id) & (cells.target_period == r.target_period)]
        first = t.sort_values("publication_date").iloc[0]
        lead = r.lead_time_vintages.split(";")
        rows.append({"trajectory_id": r.trajectory_id, "first_vintage_id": first.vintage_id,
                     "window_start": pub[first.vintage_id].date(), "lead_time_vintages": r.lead_time_vintages,
                     "window_end": max(pub[v] for v in lead).date(), "n_lead_vintages": len(lead)})
    return pd.DataFrame(rows)


def corpus(pilot: pd.DataFrame, win: pd.DataFrame) -> pd.DataFrame:
    docs = pd.read_csv(INVENTORY / "documents.csv", dtype=str, keep_default_na=False)
    docs["d"] = pd.to_datetime(docs.publication_date, errors="coerce")
    rows = []
    for r, w in zip(pilot.itertuples(), win.itertuples()):
        inside = docs[(docs.source == r.source) & docs.doc_type.isin(CORPUS_TYPES)
                      & (docs.d >= pd.Timestamp(w.window_start)) & (docs.d <= pd.Timestamp(w.window_end))]
        rows += [{**x, "trajectory_id": r.trajectory_id, "role": "corpus"} for x in inside.to_dict("records")]
        post = docs[docs.doc_id.isin(r.post_hoc_docs)]
        rows += [{**x, "trajectory_id": r.trajectory_id, "role": "post_hoc"} for x in post.to_dict("records")]
    d = pd.DataFrame(rows)
    return (d.groupby(["doc_id", "role"], sort=False)
            .agg(source=("source", "first"), collection=("collection", "first"), doc_type=("doc_type", "first"),
                 title=("title", "first"), url=("url", "first"), publication_date=("publication_date", "first"),
                 date_certainty=("date_certainty", "first"), trajectories=("trajectory_id", ";".join))
            .reset_index().sort_values(["source", "role", "publication_date", "doc_id"]))


def plan() -> None:
    PILOT.mkdir(exist_ok=True)
    pilot = select_pilot()
    win = windows(pilot)
    cor = corpus(pilot, win)
    cols = ["source", "pilot_rank", "case_rank", "trajectory_id", "series_id", "target_period", "family",
            "episode", "score", "run_sign", "onset_vintage_id", "correction_vintage_id", "lead_time_n"]
    out = pilot[cols].merge(win, on="trajectory_id")
    out["post_hoc_docs"] = pilot.post_hoc_docs.str.join(";").values
    out.to_csv(PILOT / "pilot_cases.csv", index=False)
    cor.to_csv(PILOT / "corpus.csv", index=False)
    coverage().to_csv(PILOT / "post_hoc_coverage.csv", index=False)
    print(out[["source", "pilot_rank", "trajectory_id", "window_start", "window_end", "n_lead_vintages"]].to_string())
    print(cor.groupby(["source", "role", "collection"]).size().to_string())


PREREG = PILOT / "preregistration.md"
REG = PILOT / "preregistration.json"
PART2 = "## Part 2:"


def _sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b.replace(b"\r\n", b"\n")).hexdigest()


def _part1() -> str:
    return PREREG.read_text(encoding="utf-8").replace("\r\n", "\n").split(PART2, 1)[0]


def register() -> None:
    """Part 1: hash the text above 'Part 2', the pilot lists and their inputs,
    before any pilot document is downloaded or extracted."""
    if REG.exists():
        sys.exit("Part 1 is registered; log changes under Deviations.")
    files = [PILOT / "pilot_cases.csv", PILOT / "corpus.csv", PILOT / "post_hoc_coverage.csv",
             CASES / "cases.parquet", INVENTORY / "documents.csv"]
    reg = {"part1_sha256": _sha_bytes(_part1().encode("utf-8")),
           "file_sha256": _sha_bytes(PREREG.read_bytes()),
           "registered_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "files": {f.relative_to(ROOT).as_posix(): _sha_bytes(f.read_bytes()) if f.suffix in (".csv", ".md")
                     else hashlib.sha256(f.read_bytes()).hexdigest() for f in files}}
    REG.write_text(json.dumps(reg, indent=1) + "\n", encoding="utf-8")
    print(f"part 1 registered {reg['part1_sha256'][:12]} at {reg['registered_at']}")


def verify_part1() -> dict:
    reg = json.loads(REG.read_text(encoding="utf-8"))
    if _sha_bytes(_part1().encode("utf-8")) != reg["part1_sha256"]:
        sys.exit("pilot/preregistration.md part 1 has changed since registration.")
    for rel, h in reg["files"].items():
        b = (ROOT / rel).read_bytes()
        if h not in (_sha_bytes(b), hashlib.sha256(b).hexdigest()):
            sys.exit(f"{rel} has changed since registration.")
    return reg


if __name__ == "__main__":
    {"plan": plan, "register": register}[sys.argv[1]]()
