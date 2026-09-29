"""Merge the second model's answers for pending attribution labels (plan D20, D21).

    python -m fvd.merge_second_model          # settle by agreement, queue the rest
    python -m fvd.merge_second_model apply    # write decided queue rows back as reviewed

Reads crosswalks/pending_second_model/results.jsonl (written on another machine
by run_second_model.py) and applies the D20 rule to the second model: a pending
label is settled when the second model's top answer equals the provisional
(keyword) category, its confidence is at least D20, the label has no negation
and the row is not a group heading. Settled rows keep their category and name
the second model as labeller. Every other pending row goes to
crosswalks/review_queue_labels.csv for Teo, with the keyword answer, Jev's top
two and the second model's answer and reason side by side.
"""

from __future__ import annotations

import json

import pandas as pd

from .jev_label import states
from .jev_route import D20, NEGATION
from .paths import CROSSWALKS

PKG = CROSSWALKS / "pending_second_model"


def main() -> None:
    res = {}
    for line in (PKG / "results.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            res[r["key"]] = r          # the latest line per row wins
    S = {s["key"]: s for s in states().values() if s["crosswalk"] == "attribution_labels"}
    cw = pd.read_csv(CROSSWALKS / "attribution_labels.csv", dtype=str, keep_default_na=False)
    queue, settled, missing = [], 0, 0
    for i, row in cw[(cw.source_table == "EFO") & (cw.status == "pending")].iterrows():
        r, s = res.get(row.label_key), S[row.label_key]
        reasons = []
        if r is None:
            missing += 1
            reasons.append("no second-model result")
        else:
            if r["answer"] != row.category:
                reasons.append(f"disagree: keyword {row.category}, second model {r['answer']}")
            if r["confidence"] < D20:
                reasons.append(f"second-model confidence {r['confidence']:.2f} < {D20}")
        if NEGATION.search(row.label):
            reasons.append("negation in label (guard)")
        if s.get("group_heading_of"):
            reasons.append("group heading (A2): follows the rows beneath it")
        if not reasons:
            cw.loc[i, "status"] = "settled_agreement"
            cw.loc[i, "labeller"] = f"keyword rules + {r['model_version'] or r['model_name']} (second model)"
            cw.loc[i, "route_reason"] = ""
            settled += 1
            continue
        st = s["state"]
        both = r is not None and r["answer"] == row.jev_choice and r["answer"] != row.category
        queue.append({
            "label": row.label, "section": st["section"], "group_heading_above": st.get("group_heading_above", ""),
            "table": st["table_title"],
            "keyword_answer": row.category,
            "jev_first": row.jev_choice, "jev_p1": row.jev_p1, "jev_second": row.jev_second,
            "jev_p2": row.jev_p2, "jev_confidence": row.jev_confidence,
            "second_answer": r["answer"] if r else "", "second_confidence": f"{r['confidence']:.3f}" if r else "",
            "second_reason": r["reason"] if r else "",
            "both_models_say": r["answer"] if both else "",
            "why_in_queue": "; ".join(reasons),
            "key": row.label_key, "your_answer": "", "comment": "",
        })
    cw.to_csv(CROSSWALKS / "attribution_labels.csv", index=False)
    pd.DataFrame(queue).to_csv(CROSSWALKS / "review_queue_labels.csv", index=False)
    print(f"{settled} pending labels settled, {len(queue)} to review_queue_labels.csv, "
          f"{missing} without a second-model result")


CATEGORIES = ["policy", "economic_determinants", "calibration_to_outturn", "classification_one_offs",
              "modelling_other", "underlying_unsplit", "by_tax_head"]


def apply(path=CROSSWALKS / "review_queue_labels_decisions.csv") -> None:
    """Write decided queue rows into crosswalks/attribution_labels.csv as reviewed
    rows, which E2 keeps on every rerun. Columns: key, answer (a category of
    codebook section 2.3), labeller, comment."""
    d = pd.read_csv(path, dtype=str, keep_default_na=False)
    bad = sorted(set(d.answer) - set(CATEGORIES))
    if bad:
        raise ValueError(f"answers that are not categories: {bad}")
    cw = pd.read_csv(CROSSWALKS / "attribution_labels.csv", dtype=str, keep_default_na=False)
    changed = 0
    for _, r in d.iterrows():
        m = (cw.source_table == "EFO") & (cw.label_key == r["key"])
        if m.sum() != 1:
            raise ValueError(f"{r['key']}: {m.sum()} crosswalk rows")
        changed += int(cw.loc[m, "category"].iloc[0] != r["answer"])
        cw.loc[m, ["category", "reviewed", "status", "labeller", "route_reason"]] = \
            [r["answer"], "True", "reviewed", r["labeller"], ""]
        if r.get("comment"):
            cw.loc[m, "comment"] = r["comment"]
    cw.to_csv(CROSSWALKS / "attribution_labels.csv", index=False)
    print(f"{len(d)} labels marked reviewed, {changed} categories changed. "
          "Next: python -m fvd.e2_efo_tables, then python -m fvd.e5_stylized_facts")


if __name__ == "__main__":
    import sys
    apply() if sys.argv[1:2] == ["apply"] else main()
