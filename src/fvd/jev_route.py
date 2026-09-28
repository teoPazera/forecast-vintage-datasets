"""Route crosswalk rows by Jev's answers (Teo's amendment, step 5; plan D20).

    python -m fvd.jev_route

A row is settled by agreement when Jev's top answer equals the current (keyword)
mapping, its confidence is at least D20, and the label contains no negation.
Otherwise:

- PMD heads go to crosswalks/review_queue_heads.csv for Teo to decide now: the
  head crosswalk must be final before E6, whose case scores use policy-adjusted
  errors that depend on it.
- Attribution labels are marked `pending`: the keyword mapping stays as the
  provisional category and stages that use it report how many pending rows they
  used. They go to the second model (crosswalks/pending_second_model/).

Group headings (rule A2) are always pending: their category follows the rows
beneath them, which code resolves once those rows are final. Rows Teo has
reviewed are left as they are.
"""

from __future__ import annotations

import json
import re

import pandas as pd

from . import crosswalks as X
from .jev_label import latest_results, states
from .paths import CROSSWALKS

D20 = 0.7   # confidence threshold for settling by agreement (Teo, 28 September 2026)
# Jev reads labels literally, so a label that negates a term ("Non classification
# GOS changes") can be misread by Jev and the keyword rules alike (pilot, 28 Sep).
NEGATION = re.compile(r"\bnon\b|\bnon-|\bnot\b|\bexcl?\b\.?|\bex\.|\bexc\.|excluding|\bwithout\b", re.I)


def _route(current: str, r: dict | None, label: str, group: bool = False) -> dict:
    if r is None:
        return {"status": "pending", "route_reason": "no Jev result"}
    (c1, p1), (c2, p2) = list(r["probabilities"].items())[:2]
    # strings: the crosswalks are read and written as text
    out = {"jev_choice": c1, "jev_p1": f"{p1:.3f}", "jev_second": c2, "jev_p2": f"{p2:.3f}",
           "jev_confidence": f"{r['confidence']:.3f}"}
    reasons = []
    if c1 != current:
        reasons.append(f"disagree: keyword {current}, Jev {c1}")
    if r["confidence"] < D20:
        reasons.append(f"confidence {r['confidence']:.2f} < {D20}")
    if NEGATION.search(label):
        reasons.append("negation in label (guard)")
    if group:
        reasons.append("group heading (A2): follows the rows beneath it")
    out["status"] = "pending" if reasons else "settled_agreement"
    out["labeller"] = "" if reasons else f"keyword rules + {r['model']}"
    out["route_reason"] = "; ".join(reasons)
    return out


def main() -> None:
    res = latest_results()
    S = states()
    by_key = {(s["crosswalk"], s["key"]): s for s in S.values()}

    # --- attribution labels ---
    lab = pd.read_csv(CROSSWALKS / "attribution_labels.csv", dtype=str, keep_default_na=False)
    for c in X.LLM_COLS:
        if c not in lab:
            lab[c] = ""
    for i, row in lab[lab.source_table == "EFO"].iterrows():
        if X.is_true(row.reviewed):
            lab.loc[i, "status"] = "reviewed"
            continue
        s = by_key[("attribution_labels", row.label_key)]
        for k, v in _route(row.category, res.get(s["id"]), row.label, bool(s.get("group_heading_of"))).items():
            lab.loc[i, k] = v
    lab.loc[lab.source_table != "EFO", "status"] = "fixed_in_code"
    lab.to_csv(CROSSWALKS / "attribution_labels.csv", index=False)

    # --- PMD heads ---
    hd = pd.read_csv(CROSSWALKS / "pmd_heads.csv", dtype=str, keep_default_na=False)
    for c in X.LLM_COLS:
        if c not in hd:
            hd[c] = ""
    queue = []
    all_names = {c: n for s in S.values() if s["crosswalk"] == "pmd_heads"
                 for c, n in s["state"]["candidate_series"].items()}
    for i, row in hd.iterrows():
        if X.is_true(row.reviewed):
            hd.loc[i, "status"] = "reviewed"
            continue
        current = row.hofd_sheet or "(none)"
        s = by_key[("pmd_heads", f"{row.measure_type}|{row.head_raw}")]
        r = res.get(s["id"])
        routed = _route(current, r, row.head_raw)
        for k, v in routed.items():
            hd.loc[i, k] = v
        if routed["status"] == "pending":
            st = s["state"]
            names = {**st["candidate_series"], "(none)": "no forecast series"}
            why = routed["route_reason"]
            if current not in names:
                why += ("; the keyword answer is a series of the other type (receipts vs spending), "
                        "which Jev was not offered")
            name = lambda c: f"{c}: {names.get(c, all_names.get(c, '?'))}"
            queue.append({
                "measure_type": row.measure_type, "head": row.head_raw,
                "context": f"Measures: {st['number_of_measures']}. Largest: " + " | ".join(st["largest_measures"][:3]),
                "keyword_answer": name(current),
                "jev_first": name(routed["jev_choice"]) if "jev_choice" in routed else "",
                "jev_p1": routed.get("jev_p1", ""),
                "jev_second": name(routed["jev_second"]) if "jev_second" in routed else "",
                "jev_p2": routed.get("jev_p2", ""),
                "jev_confidence": routed.get("jev_confidence", ""),
                "jev_covers_several_series": f"{r['nouls']['broad']:.2f}" if r else "",
                "why_in_queue": why,
                "your_answer": "", "comment": "",
            })
    hd.to_csv(CROSSWALKS / "pmd_heads.csv", index=False)
    q = pd.DataFrame(queue)
    q.to_csv(CROSSWALKS / "review_queue_heads.csv", index=False)

    # series codes Teo can answer with
    codes = []
    for s in S.values():
        if s["crosswalk"] == "pmd_heads":
            t = "tax" if s["key"].startswith("tax|") else "spending"
            codes += [{"measure_type": t, "code": c, "name": n} for c, n in s["state"]["candidate_series"].items()]
    pd.DataFrame(codes).drop_duplicates().to_csv(CROSSWALKS / "llm" / "series_codes.csv", index=False)

    e = lab[lab.source_table == "EFO"]
    summary = {
        "D20": D20,
        "labels": e.status.value_counts().to_dict(),
        "labels_pending_reasons": e[e.status == "pending"].route_reason.str.split("; ").explode()
            .str.replace(r":.*| \d.*", "", regex=True).value_counts().to_dict(),
        "labels_agreement_top_answer": round(float((e.jev_choice == e.category).mean()), 3),
        "heads": hd.status.value_counts().to_dict(),
        "heads_in_queue": len(q),
        "heads_agreement_top_answer": round(float((hd.jev_choice == hd.hofd_sheet.replace("", "(none)")).mean()), 3),
    }
    (CROSSWALKS / "llm" / "routing_summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))


def apply_heads(path=CROSSWALKS / "review_queue_heads_decisions.csv") -> None:
    """Write the decided queue rows into crosswalks/pmd_heads.csv as reviewed rows,
    which E2 keeps on every rerun. `answer` is an HOFD sheet code or (none)."""
    d = pd.read_csv(path, dtype=str, keep_default_na=False)
    hd = pd.read_csv(CROSSWALKS / "pmd_heads.csv", dtype=str, keep_default_na=False)
    changed = 0
    for _, r in d.iterrows():
        m = (hd.measure_type == r["measure_type"]) & (hd.head_raw == r["head"])
        if m.sum() != 1:
            raise ValueError(f"{r['measure_type']}|{r['head']}: {m.sum()} crosswalk rows")
        sheet = "" if r["answer"] == "(none)" else r["answer"]
        changed += int(hd.loc[m, "hofd_sheet"].iloc[0] != sheet)
        hd.loc[m, "hofd_sheet"] = sheet
        hd.loc[m, "confidence"] = "exact" if sheet else "none"
        hd.loc[m, "note"] = r["verified_in"] or f"review: {r['review_comment']}"
        hd.loc[m, "reviewed"] = "True"
        hd.loc[m, "status"] = "reviewed"
        hd.loc[m, "labeller"] = r["labeller"]
        hd.loc[m, "route_reason"] = ""
    hd.to_csv(CROSSWALKS / "pmd_heads.csv", index=False)
    print(f"{len(d)} heads marked reviewed, {changed} mappings changed")


if __name__ == "__main__":
    import sys
    if sys.argv[1:2] == ["apply-heads"]:
        apply_heads()
    else:
        main()
