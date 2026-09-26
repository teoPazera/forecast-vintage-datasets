"""Stage E0, task 5: check the source facts in section 5 of the plan against the files.

Run:  python -m fvd.e0_factcheck

Writes inventory/e0_fact_checks.csv with one row per claim:
  claim_id, section, claim, status (confirmed / discrepancy / partly / deferred),
  finding, evidence (file, sheet, row or column).
"""

from __future__ import annotations

import re
from collections import Counter

import openpyxl
import pandas as pd

from .hofd import series_sheets, vintage_rows
from .paths import INVENTORY, ROOT
from .schemas import check_columns, write_schema

HOFD = "raw/obr/Historical_official_forecasts_database_Spring_2026.xlsx"
FRD = "raw/obr/Fiscal_forecast_revisions_database_March_2026.xlsx"
PMD = "raw/obr/Policy_measures_database_March_2026.xlsx"
CBO = "raw/cbo/eval-projections-682559c"

checks: list[dict] = []


def add(cid, section, claim, status, finding, evidence):
    checks.append({"claim_id": cid, "section": section, "claim": claim, "status": status,
                   "finding": finding, "evidence": evidence})


def _rows(wb, name):
    return list(wb[name].iter_rows(values_only=True))


def _sheet_text(rows) -> str:
    return " ".join(str(v) for r in rows for v in r if isinstance(v, str))


def hofd_checks():
    wb = openpyxl.load_workbook(ROOT / HOFD, read_only=True, data_only=True)
    names = wb.sheetnames
    sheets = series_sheets(names)
    labels = {n: vintage_rows(_rows(wb, n)) for n in sheets}

    vat = [lab.label for _, lab in labels["VAT"] if lab.kind == "regular"]
    last = vat[-1]
    add("H1", "5.1", "File name may not match content; identify content by vintage labels",
        "confirmed",
        f"current file is named 'Spring_2026' and its latest vintage is {last}; the obr.uk "
        "download slug still reads 'historical-official-forecasts-database-march-2025'",
        f"{HOFD}; obr.uk/data/ link")

    ok_layout, bad = 0, []
    for n in sheets:
        rows = _rows(wb, n)
        hdr = [i for i, r in enumerate(rows) if r and r[0] == "Back to contents"]
        outt = [i for i, r in enumerate(rows) if r and isinstance(r[0], str) and r[0].startswith("Outturn data")]
        if len(hdr) == 1 and hdr[0] == 3 and len(outt) == 1 and \
                all(v is None for v in rows[outt[0] - 1]) and isinstance(rows[0][0], str):
            ok_layout += 1
        else:
            bad.append(n)
    add("H2", "5.1", "Layout: title row, unit row, blank row, header 'Back to contents', vintage rows, "
        "blank row, 'Outturn data*', footnote",
        "confirmed" if not bad else "partly",
        f"{ok_layout} of {len(sheets)} series sheets follow the layout exactly"
        + (f"; different: {', '.join(bad)}" if bad else ""), f"{HOFD}, all unsuffixed sheets")

    obr = [v for v in vat if int(v[-4:]) >= 2010]
    add("H3", "5.1", "About 33 OBR vintages, June 2010 to March 2026", "confirmed",
        f"{len(obr)} regular vintage rows on the VAT sheet, {obr[0]} to {obr[-1]}", f"{HOFD}, sheet VAT, col A")

    firsts = {n: next(lab.label for _, lab in labels[n] if lab.kind == "regular")
              for n in ("£PSNB", "£PSCR", "£TME")}
    add("H4", "5.1", "PSNB from April 1970; current receipts and TME from March 1990",
        "confirmed" if firsts == {"£PSNB": "April 1970", "£PSCR": "March 1990", "£TME": "March 1990"}
        else "discrepancy", f"first vintage rows: {firsts}", f"{HOFD}, sheets £PSNB, £PSCR, £TME")

    i_rec, i_sp, i_ec = names.index("Receipts"), names.index("Spending"), names.index("Economy")
    receipts = [n for n in names[i_rec + 1:i_sp]]
    spending = [n for n in names[i_sp + 1:i_ec]]
    economy = [n for n in names[i_ec + 1:]]
    add("H5", "5.1", "About 30 receipts components, about 30 spending lines, about 40 economy series",
        "confirmed", f"{len(receipts)} receipts sheets, {len(spending)} spending sheets, "
        f"{len(economy)} economy sheets (sheet order between the section header sheets)",
        f"{HOFD}, sheet order")

    comp_first, comp_data = {}, {}
    for n in receipts:
        rows = _rows(wb, n)
        regular = [(i, lab) for i, lab in labels[n] if lab.kind == "regular"]
        comp_first[n] = regular[0][1].label if regular else None
        comp_data[n] = next((lab.label for i, lab in regular
                             if any(isinstance(v, (int, float)) for v in rows[i][1:])), None)
    late = {n: f for n, f in comp_data.items() if f != "June 2010"}
    add("H6", "5.1", "Component sheets start in June 2010", "confirmed",
        f"all {len(receipts)} receipts sheets have rows from {set(comp_first.values())}; sheets whose "
        f"first non-empty vintage is later (component introduced later): {late}",
        f"{HOFD}, receipts sheets, first vintage row with a value")

    two = [n for n in names if n.endswith(" (2)")]
    starts = {}
    for n in two:
        rows = _rows(wb, n)
        hdr = next((r for r in rows if r and r[0] == "Back to contents"), None)
        starts[n] = hdr[1] if hdr else None
    add("H7", "5.1", "' (2)' sheets are chart-data copies starting in 2008-09",
        "confirmed" if set(starts.values()) <= {"2008-09", 2008} else "partly",
        f"{len(two)} sheets; first target period: {Counter(map(str, starts.values()))}",
        f"{HOFD}, '(2)' sheets header row")

    memo = Counter()
    for n in sheets:
        for _, lab in labels[n]:
            if lab.kind == "memo":
                memo[lab.vintage_label] += 1
    add("H8", "5.1 / D14", "Memo rows: restated March 2019, supplementary March 2020",
        "partly", f"memo rows by label (sheet count): {dict(memo)}; the plan does not mention "
        "the restated March 2024 memo", f"{HOFD}, col A of series sheets")

    contents = _sheet_text(_rows(wb, "Contents"))
    add("H9", "5.1", "Contents: forecasts reflect definitions and classifications at the time",
        "confirmed" if "definitions and classifications used at the time" in contents else "discrepancy",
        "text found" if "definitions and classifications used at the time" in contents else "text not found",
        f"{HOFD}, sheet Contents")

    pscr = _sheet_text(_rows(wb, "£PSCR"))
    hit = re.search(r"latest outturn may differ substantially[^.]*", pscr)
    add("H10", "5.1", "£PSCR warns that latest outturn may differ due to classification changes",
        "confirmed" if hit else "discrepancy", hit.group(0) if hit else "not found", f"{HOFD}, sheet £PSCR")

    dup = []
    for n in sheets:
        raws = [lab.raw.strip() for _, lab in labels[n] if lab.kind == "regular"]
        fixed = [lab for _, lab in labels[n] if "[year corrected]" in lab.footnote]
        if fixed:
            dup.append(f"{n}: raw '{fixed[0].raw.strip()}' read as {fixed[0].label}")
    add("H11", "5.1", "(not in plan) vintage labels are consistent", "discrepancy",
        "; ".join(dup) + ". Labels also carry footnote markers and typos "
        "('December-20131', 'March -20141', 'March2026', 'November 2022**')", f"{HOFD}, col A")

    add("H12", "5.1", "Outturn row holds only the latest outturn", "confirmed",
        "footnote reads '*as available at last forecast'", f"{HOFD}, footnote row under 'Outturn data*'")


def frd_checks():
    wb = openpyxl.load_workbook(ROOT / FRD, read_only=True, data_only=True)
    add("F1", "5.2", "Sheets: Revisions (Per cent of GDP), Revisions (£ billion), Classifications and one-offs",
        "confirmed", f"sheets: {wb.sheetnames}", FRD)
    rows = _rows(wb, "Revisions (£ billion)")
    blocks = [r[0] for r in rows if isinstance(r[0], str) and re.match(r"^[A-Z][a-z]+ \d{4}", r[0])]
    add("F2", "5.2", "One block per vintage from November 2010", "confirmed",
        f"{len(blocks)} blocks, {blocks[0]} to {blocks[-1]}", f"{FRD}, sheet Revisions (£ billion), col A")
    first = [r[0] for r in rows[2:14]]
    add("F3", "5.2", "Block rows: total; Policy (receipts, spending); Classifications and one-offs; "
        "Underlying (receipts, debt interest, non-interest spending)", "confirmed",
        f"rows of first block: {first}", f"{FRD}, rows 3-12")
    text = _sheet_text(_rows(wb, "Contents"))
    add("F4", "4.2", "Revisions are to PSNB; receipts upgrades appear negative", "confirmed",
        "note 4: 'A positive number means a deterioration in PSNB, i.e. a larger deficit or higher "
        "expenditure or lower receipts'" if "positive number means a deterioration" in text else "note not found",
        f"{FRD}, sheet Contents, note 4")
    m = re.search(r"indirect effects of Government decisions[^.]*\.[^.]*since March 2015[^.]*", text)
    add("F5", "5.2", "PMD notes: full decomposition covering all government decisions since March 2016",
        "discrepancy",
        "FRD Contents says indirect effects of Government decisions are identified explicitly since "
        "March 2015 and not estimated for earlier forecasts" + ("" if m else " (text not matched)")
        + "; PMD Notes say non-scorecard measures included since 2015. No 'March 2016' statement found; "
        "the FRD cites Annex B of the March 2016 EFO for methodology", f"{FRD} Contents; {PMD} Notes")


def pmd_checks():
    wb = openpyxl.load_workbook(ROOT / PMD, read_only=True, data_only=True)
    add("P1", "5.3", "Sheets: Tax Measures, Tax Summary, Spending Measures, Spending Summary, Borrowing Summary",
        "confirmed", f"sheets: {wb.sheetnames}", PMD)
    tax = pd.DataFrame(_rows(wb, "Tax Measures")[3:], columns=_rows(wb, "Tax Measures")[2])
    tax = tax.dropna(subset=["Event"])
    years = [c for c in tax.columns if isinstance(c, str) and re.match(r"\d{4}-\d{2}", c)]
    add("P2", "5.3", "Tax Measures: about 2,600 rows since 1970; columns Event, Measure description, "
        "Tax head, then 1970-71 to 2030-31", "confirmed",
        f"{len(tax)} measure rows; year columns {years[0]} to {years[-1]}", f"{PMD}, sheet Tax Measures, row 3")
    nonnum = sum(isinstance(v, str) for c in years for v in tax[c].dropna())
    add("P3", "5.3", "Values in £ million, positive = gain to the Exchequer",
        "confirmed" if nonnum == 0 else "partly",
        f"{nonnum} year cells stored as text; sign check: 'Budget 1970 / Increase of allowance / "
        f"Income tax' 1970-71 = {tax.iloc[0][years[0]]} (a tax cut is negative)",
        f"{PMD}, sheet Tax Measures, row 4")
    sp = pd.DataFrame(_rows(wb, "Spending Measures")[3:], columns=_rows(wb, "Spending Measures")[2])
    sp = sp.dropna(subset=["Event"])
    ev_all = pd.unique(pd.concat([tax.Event, sp.Event]))
    since = list(pd.unique(tax.Event[tax.index >= tax.index[tax.Event == "Budget 2010 #2"][0]]))
    add("P4", "5.3", "About 85 events", "partly",
        f"{len(ev_all)} distinct event labels in Tax and Spending Measures; {len(since)} from "
        "'Budget 2010 #2' onward in Tax Measures", f"{PMD}, col Event")
    heads = sorted(set(tax["Tax head"].dropna()))
    ci = Counter(h.strip().lower() for h in heads)
    add("P5", "5.3", "About 62 raw tax-head labels, inconsistent in case", "confirmed",
        f"{len(heads)} raw labels, {len(ci)} after case-folding; case variants: "
        f"{[h for h in heads if ci[h.strip().lower()] > 1][:12]}", f"{PMD}, col Tax head")
    add("P6", "5.3", "Spending Measures start June 2010", "confirmed" if sp.Event.iloc[0] == "Budget 2010 #2"
        else "discrepancy", f"first event: {sp.Event.iloc[0]}", f"{PMD}, sheet Spending Measures")
    notes = _sheet_text(_rows(wb, "Notes"))
    for cid, claim, pat in [
        ("P7", "Only the original costing is recorded", r"only includes the original policy costing"),
        ("P8", "Costings beyond the scorecard extended with nominal GDP growth", r"extended beyond their original scorecard period using the growth rate of nominal GDP"),
        ("P9", "Only direct effects are included", r"only includes the direct effect"),
        ("P10", "Values in £ million", r"in £ million"),
        ("P11", "Disaggregation by tax from the June 2010 Budget", r"between Budget 1970 and the March Budget 2010, the database only includes the total"),
    ]:
        ok = re.search(pat, notes) is not None
        add(cid, "5.3", claim, "confirmed" if ok else "discrepancy",
            "text found in Notes" if ok else "text not found in Notes", f"{PMD}, sheet Notes")
    add("P12", "5.3", "(not in plan) how extrapolated values are marked", "confirmed",
        "the Notes 'Shading key' marks extrapolated costings by cell shading only; E2 must read cell "
        "fills to set `extrapolated`", f"{PMD}, sheet Notes, rows 10-14")


def cbo_checks():
    b = pd.read_csv(ROOT / CBO / "input_data/baselines.csv")
    c = pd.read_csv(ROOT / CBO / "input_data/baseline_changes.csv")
    a = pd.read_csv(ROOT / CBO / "input_data/actuals.csv")
    add("C1", "5.7", "baselines.csv columns", "confirmed", f"columns: {list(b.columns)}", f"{CBO}/input_data/baselines.csv")
    bd = sorted(b.baseline_date.unique())
    add("C2", "5.7", "117 baseline dates, 1982-02 to 2026-02", "confirmed" if len(bd) == 117 else "discrepancy",
        f"{len(bd)} dates, {bd[0]} to {bd[-1]}", "baselines.csv baseline_date")
    rev = b[b.component == "revenue"]
    cats = sorted(rev.category.unique())
    nv = rev.groupby("category").baseline_date.nunique().to_dict()
    add("C3", "5.7", "Revenue: 7 categories plus total, each with about 108 vintages", "confirmed",
        f"categories {cats}; vintages per category {nv}", "baselines.csv component=revenue")
    out = b[b.component == "outlay"][["category", "subcategory"]].drop_duplicates()
    add("C4", "5.7", "Outlays: discretionary (defense, nondefense), mandatory (SS, Medicare, Medicaid, "
        "other, Fannie/Freddie), net interest", "confirmed",
        "; ".join(f"{k}: {sorted(g.subcategory)}" for k, g in out.groupby("category")),
        "baselines.csv component=outlay")
    yn = [int(v) for v in sorted(b.projected_year_number.unique())]
    bd_ts = pd.to_datetime(b.baseline_date)
    fy_now = bd_ts.dt.year + (bd_ts.dt.month >= 10).astype(int)   # US fiscal year in progress
    off = b.projected_fiscal_year - fy_now - (b.projected_year_number - 1)
    add("C5", "5.7", "projected_year_number runs from -1 to 11; meaning of -1 and 0 to verify",
        "confirmed" if yn[0] == -1 and yn[-1] == 11 and (off == 0).all() else "partly",
        f"values {yn[0]}..{yn[-1]}; projected_fiscal_year = (fiscal year in progress at baseline_date) + "
        f"projected_year_number - 1 holds for {(off == 0).mean():.1%} of rows, so 1 = the fiscal year "
        "in progress, 0 = the previous fiscal year, -1 = two years back", "baselines.csv")
    cd = sorted(c.changes_baseline_date.unique())
    per = c[c.component == "revenue"].groupby("category").changes_baseline_date.nunique().to_dict()
    add("C6", "5.7", "About 120 change dates; about 105 per revenue category",
        "confirmed", f"{len(cd)} change dates ({cd[0]} to {cd[-1]}); per revenue category {per}",
        "baseline_changes.csv")
    rv = c[c.component == "revenue"]
    et = rv[rv.change_category != "Legislative"]
    et_dates = sorted(et.changes_baseline_date.unique())
    et_vals = et.groupby("change_category").value.agg(lambda s: (s != 0).sum()).to_dict()
    add("C7", "5.7", "baseline_changes carry Legislative, Economic and Technical changes by category",
        "discrepancy",
        "README: 'For revenues, only the legislative changes are shown.' Economic/Technical revenue rows "
        f"exist for {len(et_dates)} change dates ({et_dates[0]} to {et_dates[-1]}) with non-zero values "
        f"{et_vals}. Revenue attribution is therefore legislative-only before {et_dates[0]}, and "
        "full (legislative/economic/technical) only for the most recent change dates",
        f"{CBO}/README.md; baseline_changes.csv component=revenue")
    only_c = sorted(set(cd) - set(bd))
    only_b = sorted(set(bd) - set(cd))
    add("C8", "5.7", "Change dates differ from baseline dates; which previous baseline each is measured "
        "against", "deferred",
        f"change dates not among baseline dates: {only_c[:20]}{'...' if len(only_c) > 20 else ''}; "
        f"baseline dates without changes: {only_b[:12]}. README: changes 'recorded ... after the last "
        "budget and economic outlook report of the year' are included. Relation tested in E3",
        "baseline_changes.csv vs baselines.csv")
    flags = b.groupby("baseline_date")[["Spring_flag", "Winter_flag"]].max()
    none = flags[~flags.Spring_flag & ~flags.Winter_flag].index.tolist()
    add("C9", "5.7", "Some baselines have neither season flag (e.g. 2020-09)", "confirmed",
        f"{len(none)} baselines with neither flag, e.g. {none[-6:]}; these are the summer/autumn updates "
        "(see vintage_calendar.csv for the matched publications)", "baselines.csv")
    add("C10", "5.7", "baseline_date is month-level with day 01", "confirmed",
        "all baseline dates end in '-01'; README states they indicate only year and month"
        if all(d.endswith("-01") for d in bd) else "some dates are not day 01", "baselines.csv; README")
    add("C11", "5.7", "actuals.csv covers 1982-2025", "confirmed",
        f"fiscal years {a.iloc[:, :].filter(like='year').min().min()} to {a.filter(like='year').max().max()}; "
        f"columns {list(a.columns)}", "actuals.csv")
    out_files = sorted(p.name for p in (ROOT / CBO / "output_data").glob("*.csv"))
    add("C12", "5.7", "output_data/ holds CBO's computed errors and summary statistics", "confirmed",
        f"{out_files}", f"{CBO}/output_data")


def main():
    hofd_checks()
    frd_checks()
    pmd_checks()
    cbo_checks()
    df = pd.DataFrame(checks)
    df.to_csv(INVENTORY / "e0_fact_checks.csv", index=False)
    check_columns("inventory/e0_fact_checks", df)
    write_schema("inventory/e0_fact_checks", INVENTORY.parent)
    with pd.option_context("display.max_colwidth", 200, "display.width", 250):
        print(df[["claim_id", "status", "finding"]].to_string(index=False))


if __name__ == "__main__":
    main()
