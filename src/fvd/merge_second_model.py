"""Merge the second model's answers for pending attribution labels (plan D20, D21).

    python -m fvd.merge_second_model          # settle by agreement, queue the rest
    python -m fvd.merge_second_model apply    # write the reviewed queue back as reviewed rows

Reads crosswalks/pending_second_model/results.jsonl (written on another machine
by run_second_model.py) and crosswalks/pending_second_model/codebook_review.csv
(a codebook answer and the rule behind it for every pending label, written by
the pipeline session after reading the tables).

The second model returns one category and its reasoning but no probability, so
the D20 confidence test cannot be applied to it. Instead (Teo, 29 September
2026) a pending label is settled when the keyword mapping, Jev's top answer, the
second model and the codebook review all agree. Group headings are left to E2,
which resolves them by rule A2 from the rows beneath them. Every other pending
label, and every settled label the codebook review changes, goes to
crosswalks/review_queue_labels.csv for Teo with all four answers side by side.
"""

from __future__ import annotations

import json

import pandas as pd

from .jev_label import states
from .paths import CROSSWALKS

PKG = CROSSWALKS / "pending_second_model"
QUEUE = CROSSWALKS / "review_queue_labels.csv"
CATEGORIES = ["policy", "economic_determinants", "calibration_to_outturn", "classification_one_offs",
              "modelling_other", "underlying_unsplit", "by_tax_head"]
MIXED = "label mixes outturn with modelling or other"


def results() -> dict[str, dict]:
    res = {}
    for line in (PKG / "results.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            res[r["key"]] = r          # the latest line per row wins
    return res


def main() -> None:
    res = results()
    rev = pd.read_csv(PKG / "codebook_review.csv", dtype=str, keep_default_na=False).set_index("key")
    S = {s["key"]: s for s in states().values() if s["crosswalk"] == "attribution_labels"}
    cw = pd.read_csv(CROSSWALKS / "attribution_labels.csv", dtype=str, keep_default_na=False)
    queue, settled, headings = [], 0, 0
    efo = (cw.source_table == "EFO") & ((cw.status == "pending") | cw.label_key.isin(rev.index))
    for i, row in cw[efo].iterrows():
        s, r = S[row.label_key], res.get(row.label_key)
        if s.get("group_heading_of"):
            headings += 1                       # E2 resolves these by rule A2
            continue
        p = rev.loc[row.label_key]
        second = r["answer"] if r else ""
        if row.status == "pending" and row.category == row.jev_choice == second == p.proposed:
            model = r["model_version"] or r["model_name"]
            cw.loc[i, ["status", "labeller", "route_reason"]] = [
                "settled_agreement", f"keyword rules + jev-1.13.0 + {model} (second model) + codebook review", ""]
            settled += 1
            continue
        st = s["state"]
        queue.append({
            "look_closely": "yes" if p.look_closely == "1" else "",
            "label": row.label, "section": st["section"], "group_heading_above": st.get("group_heading_above", ""),
            "table": st["table_title"], "n_rows": row.n_rows, "status_now": row.status,
            "keyword_answer": row.category, "jev_first": row.jev_choice, "jev_p1": row.jev_p1,
            "second_answer": second, "second_reasoning": r["reasoning"] if r else "",
            "proposed": p.proposed, "rule": p.rule,
            "your_answer": "", "comment": "", "key": row.label_key,
        })
    cw.to_csv(CROSSWALKS / "attribution_labels.csv", index=False)
    q = pd.DataFrame(queue).sort_values(["look_closely", "status_now", "label"], ascending=[False, True, True])
    q.to_csv(QUEUE, index=False)
    print(f"{settled} pending labels settled by agreement of all four, {headings} group headings left to "
          f"E2 (rule A2), {len(q)} to {QUEUE.name} ({(q.look_closely == 'yes').sum()} to look at closely)")


def apply(path=QUEUE) -> None:
    """Write the reviewed queue into crosswalks/attribution_labels.csv as reviewed
    rows, which E2 keeps on every rerun. A row takes `your_answer` where Teo filled
    it in, otherwise the proposed answer he accepted."""
    d = pd.read_csv(path, dtype=str, keep_default_na=False)
    d["answer"] = d.your_answer.where(d.your_answer != "", d.proposed)
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
        who = "Teo" if r["your_answer"] not in ("", r["proposed"]) else \
            "Teo, accepting the codebook review's proposal"
        note = MIXED if r["rule"].startswith("A3") and r["answer"] == "calibration_to_outturn" \
            else cw.loc[m, "note"].iloc[0]
        cw.loc[m, ["category", "note", "reviewed", "status", "labeller", "route_reason"]] = \
            [r["answer"], note, "True", "reviewed", f"{who} (29 Sep 2026); rule: {r['rule']}", ""]
        if r["comment"]:
            cw.loc[m, "comment"] = r["comment"]
    cw.to_csv(CROSSWALKS / "attribution_labels.csv", index=False)
    print(f"{len(d)} labels marked reviewed, {changed} categories changed. "
          "Next: python -m fvd.e2_efo_tables, then python -m fvd.e5_stylized_facts")


if __name__ == "__main__":
    import sys
    apply() if sys.argv[1:2] == ["apply"] else main()
