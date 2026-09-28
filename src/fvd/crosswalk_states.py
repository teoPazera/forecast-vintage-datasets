"""Per-row context ("states") for model-assisted crosswalk labelling.

    python -m fvd.crosswalk_states     # writes crosswalks/llm/

Each state holds what a labeller needs to apply crosswalks/codebook.md to one
row, and nothing about the current mapping, so the model labels blind:

- attribution labels: the label, its section, and the rows of the OBR table it
  comes from (most recent occurrence), with totals and group headings marked;
- PMD heads: the head, its largest measures and the candidate forecast series.

States are JSON objects without numbers: Jev reads numbers poorly, and the one
rule that needs them (A2, group headings) is resolved here in code.

The model's instructions are sections 2 and 3 of the codebook, copied into
system_labels.txt and system_heads.txt so the package is self-contained.
Events are checked by date, not by a model (codebook section 4).
"""

from __future__ import annotations

import json
import random
import re

import pandas as pd

from .e2_efo_tables import driver_rows
from .paths import CROSSWALKS, STATS, TABLES

OUT = CROSSWALKS / "llm"
CODEBOOK = CROSSWALKS / "codebook.md"
SEED = 20260928
N_PERIODS = 3        # target periods shown per table
GROUP_TOL = 0.011    # a group heading equals the sum of its rows to rounding

LABEL_OPTIONS = ["policy", "economic_determinants", "calibration_to_outturn",
                 "classification_one_offs", "modelling_other", "underlying_unsplit", "by_tax_head"]
LABEL_QUESTION = ("Which category does the row marked >> belong to? Apply the codebook rules in "
                  "order and answer in the JSON format of section 2.6.")
HEAD_QUESTION = ("Which forecast series does this head belong to? Apply rules B1-B5 and answer in "
                 "the JSON format of section 3.4.")
RECEIPTS = {"income_taxes", "consumption_taxes", "business_taxes", "capital_taxes", "duties",
            "other_receipts"}
# The HOFD's HSC sheet repeats the NICs sheet's unit row; its title row and the
# contents sheet say "Health and social care levy".
NAME_FIX = {"HSC": "Health and social care levy (£ billion)"}


def codebook_section(n: int) -> str:
    text = CODEBOOK.read_text(encoding="utf-8")
    m = re.search(rf"^## {n}\. .*?(?=^## |\Z)", text, flags=re.M | re.S)
    return m.group(0).strip().rstrip("-").strip()


def _vdate(label: str) -> pd.Timestamp:
    return pd.to_datetime("1 " + label)


def _groups(block: pd.DataFrame, periods: list[str]) -> dict[int, int]:
    """Component rows whose values equal the sum of the next k component rows of
    the same section, in every shown period: {row: k}. Marks group headings for
    rule A2. The tolerance is fixed, not scaled by k, so that long runs of rows
    do not match by chance."""
    comp = block[block.role == "component"]
    vals = comp[periods].to_numpy(dtype=float)
    secs = comp.section.fillna("").tolist()
    rows = comp.index.tolist()
    out = {}
    for i in range(len(rows)):
        for k in range(2, len(rows) - i):
            if secs[i + k] != secs[i]:
                break
            nxt = vals[i + 1:i + 1 + k].sum(axis=0)
            if (abs(nxt - vals[i]) <= GROUP_TOL).all() and abs(vals[i]).sum() > 0:
                out[rows[i]] = k
                break
    return out


def _table_rows(t: pd.DataFrame, block: float, target_row: int) -> tuple[list[str], int | None, str | None]:
    """The block of an OBR table as a list of row texts, without numbers (Jev reads
    numbers poorly; group headings are found here, in code). Section headings are
    rows of their own; the row to label is prefixed '>> '. Returns the rows; if
    the row to label is a group heading, the number of rows it sums; and if it
    sits inside a group, that group's heading (rule A2b)."""
    t = t.sort_values("row").copy()
    t["blk"] = t.block.bfill().ffill()
    b = t[t.blk == block]
    # periods in which (nearly) every component row has a value; the first year
    # of a table is often empty for the drivers
    comp = b[b.role == "component"]
    cover = comp.groupby("target_period").value.count() / max(comp.row.nunique(), 1)
    periods = sorted(cover[cover >= 0.8].index)[:N_PERIODS]
    wide = b.pivot_table(index="row", columns="target_period", values="value", aggfunc="first")
    info = b.drop_duplicates("row").set_index("row")
    wide = wide.reindex(info.index)
    for p in periods:
        if p not in wide:
            wide[p] = float("nan")
    info = info.join(wide[periods])
    groups = _groups(info.dropna(subset=periods), periods) if periods else {}
    parent = {}
    comp_rows = info.dropna(subset=periods)
    comp_rows = comp_rows[comp_rows.role == "component"].index.tolist()
    for g, k in groups.items():
        i = comp_rows.index(g)
        for child in comp_rows[i + 1:i + 1 + k]:
            parent.setdefault(child, g)
    lines, section = [], None
    for r, x in info.iterrows():
        sec = x.section if isinstance(x.section, str) else ""
        if sec != section and sec:
            lines.append(f"## section: {sec}")
        section = sec
        has_sub = isinstance(x.sublabel, str) and x.sublabel != ""
        has_label = isinstance(x.label, str) and x.label != ""
        text = x.sublabel if has_sub else x.label
        indent = "    " if has_sub and not has_label else ""
        tags = []
        if x.role != "component":
            tags.append({"level": "forecast level", "change": "total change", "subtotal": "subtotal",
                         "memo": "memo", "adjustment": "adjustment"}.get(x.role, x.role))
        if r in groups:
            tags.append(f"group heading: the total of the next {groups[r]} rows")
        tag = f" [{'; '.join(tags)}]" if tags else ""
        lines.append((">> " if r == target_row else "") + indent + str(text) + tag)
    head = None
    if target_row in parent:
        h = info.loc[parent[target_row]]
        head = h.sublabel if isinstance(h.sublabel, str) and h.sublabel else h.label
    return lines, groups.get(target_row), head


def label_states() -> list[dict]:
    cw = pd.read_csv(CROSSWALKS / "attribution_labels.csv", dtype=str, keep_default_na=False)
    cw = cw[cw.source_table == "EFO"]
    rows = pd.read_parquet(STATS / "e2_checks" / "efo_table_rows.parquet")
    drv = driver_rows(rows)
    occ = (drv.drop_duplicates(["label_key", "vintage_label", "table", "block"])
           .assign(d=lambda d: d.vintage_label.map(_vdate))
           .sort_values("d", ascending=False))
    tables = {k: g for k, g in rows[rows.kind.isin(["tax_drivers", "receipts_sources"])]
              .groupby(["vintage_label", "table"])}
    out = []
    for i, c in enumerate(cw.itertuples()):
        o = occ[occ.label_key == c.label_key]
        ex = o.iloc[0]
        others = [f"{r.title} ({r.vintage_label}, {r.table})" for r in o.iloc[1:4].itertuples()]
        rows_, group, inside = _table_rows(tables[(ex.vintage_label, ex.table)], ex.block, ex.row)
        state = {
            "label": c.label,
            "section": c.section or "(none)",
            "group_heading_above": inside or "(none)",
            "table_title": f"{ex.title} ({ex.vintage_label}, {ex.table})",
            "table_rows": rows_,
            "other_tables_with_this_row": others,
        }
        out.append({"id": f"L{i + 1:04d}", "crosswalk": "attribution_labels", "key": c.label_key,
                    "group_heading_of": group, "state": state, "question": LABEL_QUESTION,
                    "options": LABEL_OPTIONS})
    return out


def head_states() -> list[dict]:
    h = pd.read_csv(CROSSWALKS / "pmd_heads.csv", dtype=str, keep_default_na=False)
    pm = pd.read_parquet(TABLES / "policy_measures" / "OBR.parquet")
    pm = pm[~pm.extrapolated]
    series = pd.read_parquet(TABLES / "series" / "OBR.parquet")
    series["name"] = (series.source_code.map(NAME_FIX).fillna(series.name)
                      .str.replace(r"\)\d+$", ")", regex=True))   # footnote markers
    fam = series.family.fillna("")
    opts = {"tax": series[fam.isin(RECEIPTS)], "spending": series[fam.str.startswith("spending")]}
    out = []
    for i, r in enumerate(h.itertuples()):
        m = pm[(pm.measure_type == r.measure_type) & (pm.head_raw == r.head_raw)]
        recent = m[m.vintage_id.fillna("").str.startswith("obr_")]
        use = recent if len(recent) else m
        top = (use.groupby(["event_raw", "measure"]).value.agg(lambda s: s.abs().sum()).rename("size")
               .reset_index().sort_values("size", ascending=False).head(6))
        o = opts[r.measure_type]
        state = {
            "head": r.head_raw,
            "head_type": f"{r.measure_type} head in the OBR Policy Measures Database",
            "number_of_measures": f"{m.measure.nunique()} in total, {recent.measure.nunique()} since June 2010",
            "largest_measures": [f"{t.event_raw}: {t.measure}" for t in top.itertuples()],
            "candidate_series": {s.source_code: s.name for s in o.itertuples()},
        }
        out.append({"id": f"H{i + 1:03d}", "crosswalk": "pmd_heads",
                    "key": f"{r.measure_type}|{r.head_raw}", "state": state,
                    "question": HEAD_QUESTION, "options": o.source_code.tolist() + ["(none)"]})
    return out


def pilot(labels: list[dict], heads: list[dict]) -> list[str]:
    """10 rows for the pilot: one label per current category (7) and one head per
    confidence level (3), drawn with a fixed seed. The current mapping is used
    only to spread the draw, never shown to the model."""
    rng = random.Random(SEED)
    cw = pd.read_csv(CROSSWALKS / "attribution_labels.csv", dtype=str, keep_default_na=False)
    cat = dict(zip(cw.label_key, cw.category))
    ids = []
    for c in LABEL_OPTIONS:
        pool = [s["id"] for s in labels if cat.get(s["key"]) == c]
        ids.append(rng.choice(pool))
    hc = pd.read_csv(CROSSWALKS / "pmd_heads.csv", dtype=str, keep_default_na=False)
    conf = dict(zip(hc.measure_type + "|" + hc.head_raw, hc.confidence))
    for c in ["exact", "assumed", "none"]:
        ids.append(rng.choice([s["id"] for s in heads if conf.get(s["key"]) == c]))
    return ids


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    labels, heads = label_states(), head_states()
    for name, states in [("states_labels.jsonl", labels), ("states_heads.jsonl", heads)]:
        with open(OUT / name, "w", encoding="utf-8") as f:
            for s in states:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")
    (OUT / "system_labels.txt").write_text(codebook_section(2) + "\n", encoding="utf-8")
    (OUT / "system_heads.txt").write_text(codebook_section(3) + "\n", encoding="utf-8")
    # the pilot draw is a record: made once, not redrawn when categories change later
    p = OUT / "pilot_ids.json"
    if not p.exists():
        p.write_text(json.dumps({"seed": SEED, "ids": pilot(labels, heads)}, indent=1), encoding="utf-8")
    ids = json.loads(p.read_text(encoding="utf-8"))["ids"]
    print(f"{len(labels)} label states, {len(heads)} head states, pilot: {', '.join(ids)}")


if __name__ == "__main__":
    main()
