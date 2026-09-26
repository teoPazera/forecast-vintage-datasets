# E3: CBO forecasts, outturns and attribution, with replication

Run: `python -m fvd.e3_cbo` (26 September 2026).

## 1. Question

Can CBO's baseline projections, actuals and baseline changes be put on the common
schema with exact publication dates? Do the hierarchy identities hold? How do the
baseline changes relate to consecutive baselines? Does an independent
reimplementation of CBO's error calculation reproduce CBO's own output files?

## 2. What I did

- **Input.** The four input CSVs of `US-CBO/eval-projections` at commit `682559c`
  were loaded (`raw/cbo/eval-projections-682559c/input_data/`).
- **Series.** 21 series: 8 revenue (7 categories and the total), 11 outlay lines, the
  deficit and the debt.
  - Identifiers are `cbo.<component>.<subcategory>`, e.g.
    `cbo.revenue.individual_income_taxes`.
  - Families follow D7: each revenue category is its own family; outlays are grouped
    by category (discretionary, mandatory, net interest); totals, deficit and debt
    are `aggregate`.
  - The deficit is stored as CBO stores it: the budget balance, negative = deficit
    (e.g. 2025 actual −1,781.8, `actuals.csv`). It is typed `balance`.
- **Dates.** Vintages and publication dates come from E0
  (`inventory/vintage_calendar.csv`); 64 of 117 are month-only (D5).
- **Horizons.** Cell roles and horizons use the US fiscal year (1 October to
  30 September).
- **Attribution.** All rows of `baseline_changes.csv` were loaded into
  `tables/attribution/CBO.parquet` with the D3 default mapping: Legislative → policy,
  Economic → economic_determinants, Technical → modelling_other.
  - Each change is attributed to the change date's vintage and measured against the
    immediately preceding baseline of the same series.
  - Change dates with no baseline of their own (year-end records) are stored as
    intermediate vintages `cbo_YYYY-MM_yearend` in
    `tables/vintages/CBO_intermediate.parquet`.
- **Replication.** The error calculation was reimplemented from CBO's documented
  method (`fvd.e3_cbo.replicate_errors`), not by running CBO's code:
  - revenue uses Winter and Spring baselines, the other components Spring baselines;
  - projection error = projection + legislative changes dated after the baseline −
    actual; the sign is flipped for the deficit; debt uses cumulative deficit effects;
  - Fannie Mae/Freddie Mac and projection year 0 are excluded; only baselines with a
    later legislative-change record are kept.

  The results were compared with every file in `output_data/`, after rounding as CBO
  does (3 decimals for errors, 1 for summaries).
- **Files written:**
  - `tables/{series,vintages,forecasts,outturns,attribution}/CBO.parquet`;
  - `tables/vintages/CBO_intermediate.parquet`;
  - `stats/cbo_replication/` (row-level comparisons and `summary.json`);
  - `stats/e3_checks/` (`hierarchy_residuals.csv`, `baseline_changes_relation.csv`,
    `summary.json`).

## 3. Findings

**Row counts.**
- 21 series, 117 vintages and 20,342 forecast cells (17,936 future, 1,950 in
  progress, 456 past).
- 790 outturns: `actuals.csv` has 792 rows; the two "Student Loan Foregiveness" rows
  for 2022–23 have no projection series and are excluded, as the README describes.
- 36,187 attribution rows.

**Replication** (`stats/cbo_replication/summary.json`)

| Component | Error rows (CBO / ours) | Rows matching within 0.01 | Summary rows matching |
|---|---|---|---|
| Revenue | 5,082 / 5,082 | 5,082 | 88 / 88 |
| Outlays | 2,946 / 2,946 | 2,946 | 110 / 110 |
| Deficit | 347 / 347 | 347 | 11 / 11 |
| Debt | 347 / 347 | 347 | 11 / 11 |

The largest absolute difference after rounding is 0.000.

**Hierarchy identities** (`stats/e3_checks/hierarchy_residuals.csv`)

- **Revenue total = sum of the 7 categories:** within 0.5 for 99.4% of
  baseline-years; the largest residual is 1.3 ($ billion), consistent with rounding in
  the source.
- **Outlays total = discretionary + mandatory + net interest:** largest residual 0.01.
- **Discretionary = defense + nondefense:** exact.
- **Mandatory = Social Security + Medicare + Medicaid + other:** exact. Adding
  Fannie Mae/Freddie Mac breaks the identity (residual up to 290.6), which confirms
  that the mandatory and outlay totals exclude them, as the README says.

**Baseline changes vs consecutive baselines**
(`stats/e3_checks/baseline_changes_relation.csv`)

- **Relative to which baseline.** Each change date that is also a baseline date was
  compared with the immediately preceding baseline of the same series.
- **Where all three change types are published** (7,855 category-years), previous
  baseline + legislative + economic + technical = current baseline within 0.5 in
  **99.2%** of cases. By component: deficit 100%, revenue 100%, outlays 99.2%.
- **Where they fail.** The 60 failures cluster in:
  - defense and nondefense discretionary, April and May 2018 (42 rows). The
    repository's CHANGE_LOG (version 0.7.0) records corrections to "the allocation of
    baseline changes between the April 2018 and May 2018 baselines";
  - total outlays, February 2021 (10) and July 2021 (4);
  - four mandatory rows in 2012.
- **Revenue before February 2024:** only legislative changes are published (E0 finding
  C7), so the relation cannot close; 22.6% of those category-years happen to fall
  within 0.5.
- **Change dates without a baseline for the series** (285 rows):
  - nine year-end records (2017-11, 2018-11, 2019-11, 2020-12 to 2025-12). The
    README describes them as changes recorded after the last outlook of the year;
  - 1984–1991 dates on which only revenue has a baseline.

## 4. Open questions

1. **CBO revenue attribution** is legislative-only before 2024. For revenue, the D3
   categories "economic determinants" and "modelling and other" can be computed only
   for the last four change dates. Keep revenue in the attribution analysis
   (policy only), or leave it out?
2. **Year-end change records** have no publication date (`date_certainty = unknown`).
   They matter only for policy adjustment in E4, which follows CBO's rule: all
   legislative changes dated after the vintage.

## 5. Implications for the thesis

- The CBO numbers are fully reproducible. The policy-adjusted errors in E4 can use
  CBO's own definition and are tied to CBO's published statistics.
- Revenue has 108 vintages per category and outlays up to 92 per line. That is far
  more complete target years than the OBR, so CBO carries most of the statistical
  power in E5.
- The attribution identity holds, so the revision decomposition in E5 can use CBO
  outlays and deficits with all three categories.

## 6. Gate result

| Criterion | Measured | Result |
|---|---|---|
| Replicated errors match CBO's output files within 0.01 for every row | 8,722 / 8,722 error rows and 220 / 220 summary rows | **pass** |
| Baseline + changes = next baseline within 0.5 for ≥ 95% of category-years, or the actual relation documented | 99.2% where all three change types are published; revenue before 2024 documented as legislative-only | **pass** |
| Kill: replication fails and the cause cannot be found | not triggered | — |
