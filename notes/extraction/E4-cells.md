# E4: Harmonized cell table, policy adjustment and checks

Run: `python -m fvd.e4_cells` (26 September 2026).

## 1. Question

Can every forecast cell carry its previous vintage, revision, errors against the
latest and first-estimate outturns, and a policy-adjusted error? Does the identity
e_v = e_last − Σ(later revisions) hold? Which trajectories show classification
breaks?

## 2. What I did

- **Revision chains.** For every (series, target period) the vintages are ordered by
  publication date.
  - Memo vintages are excluded from the chains (D14 default) but kept, flagged
    `memo_vintage`.
  - HM Treasury and OBR vintages share a chain. The one revision that crosses from
    HM Treasury to the OBR (March 2010 → June 2010) is flagged
    `prev_forecaster_differs`.
- **First estimates** (D4 default): the value in the `past` column of the first
  chained vintage published after the target period ended. This fills
  `outturns.value_first_estimate` and `first_estimate_vintage_id`. The latest outturn
  stays the primary one (D1).
- **Policy adjustment.** Adjusted forecast = forecast + the effect of policy
  announced after the vintage, in the series' own convention; both raw and adjusted
  errors are stored (D2 default for later case selection: adjusted).
  - **CBO:** legislative changes dated after the baseline, including year-end
    records. For debt: minus the cumulative legislative deficit changes over the
    projection years. This is CBO's method (E3).
  - **OBR aggregates** (£PSNB, PSNB % of GDP, £PSCR, £TME): FRD "policy" and
    "classifications and one-offs" revisions of later vintages. For £PSCR and £TME,
    the FRD receipts and spending policy rows and their own classification lines are
    used.
  - **OBR components:** PMD direct effects of measures from later fiscal events,
    for the series' head (`crosswalks/pmd_heads.csv`). Indirect effects are not in
    the PMD, and this is flagged in `policy_adjustment_basis`. The cross-check against
    the EFO "direct effect of Government decisions" rows needs the E2 EFO tables and
    is reported with E2.
- **Classification breaks** (plan E4 task 4): a trajectory's latest outturn lies
  outside the range of all its chained forecasts by more than 3 × the series' median
  absolute revision, and the FRD records a classification change for that series and
  period.
- **Episode windows** (D8 default): a target period is tagged when its midpoint falls
  in:
  - GFC, April 2008 to March 2010;
  - COVID, April 2020 to March 2022;
  - energy, April 2022 to March 2023.

  In calendar time this tags UK 2008-09 and US FY2009 alike.
- **Files written:**
  - `tables/cells/{OBR,CBO}.parquet` and `tables/cells.schema.yaml`;
  - updated `tables/outturns/*.parquet`;
  - `stats/e4_checks/`.

## 3. Findings

(`stats/e4_checks/summary.json`)

| | OBR | CBO |
|---|---|---|
| Cells | 26,423 | 20,342 |
| In revision chains | 26,209 | 20,342 |
| With a revision | 23,593 | 19,321 |
| With a latest outturn | 21,007 | 17,979 |
| With a first estimate | 20,578 | 7,634 |
| Policy-adjusted | 9,744 | 20,342 |
| Identity cells checked / max abs. deviation | 20,797 / 5.7e-14 | 17,979 / 9.1e-13 |

- **CBO adjustment check.** Our policy-adjusted CBO errors equal CBO's published
  projection errors in all 8,722 rows (max difference 4.5e-12;
  `stats/e4_checks/cbo_policy_adjustment_vs_cbo_errors.csv`). The deficit sign is
  flipped, as CBO does.
- **OBR adjustment coverage.** 2,048 aggregate cells are adjusted with the FRD, and
  7,696 component cells with the PMD. That covers 38 of the 60 receipts and spending
  series. Economy series, the "% of GDP" aggregates other than PSNB, and components
  without a PMD head (PAYE and self-assessed income tax, the alcohol sub-duties,
  several spending lines) are not adjusted.
- **CBO first estimates** exist only for the eight revenue series: only revenue
  baselines carry a value for the fiscal year just ended (projection year 0). That is
  7,634 cells. Outlays, deficit and debt have latest outturns only.
- **Classification breaks:**
  - OBR: 208 trajectories pass the size criterion; 7 also have a recorded
    classification change and are flagged:
    - £PSCR 2016-17 and 2017-18;
    - £TME 2012-13 and 2014-15 to 2017-18.

    The recorded changes behind them are the ESA10/PSF review (December 2014), the
    reclassification of housing associations (November 2015) and the move to
    time-shifted accruals for corporate taxes (March 2017). Share of flagged cells:
    0.41%.
  - Size-only candidates without a recorded change are listed for Teo in
    `stats/e4_checks/classification_break_candidates_OBR.csv`. They are mostly
    nominal GDP (33) and the % of GDP aggregates (PSCR 20, TME 14), where ONS
    revisions to the GDP level move the outturn.
  - CBO: 15 size-only candidates, none flagged, since CBO records no classification
    changes. Examples: customs duties 2025 (tariffs: 118 × the median revision),
    excise and payroll taxes 2023.
- **Episodes:**
  - OBR cells: 613 GFC, 2,840 COVID, 1,378 energy (18.3% in total);
  - CBO cells: 635, 599 and 559 (8.8%).

## 4. Open questions

1. **Size-only break candidates.** The criterion needs a recorded classification
   change, and for OBR components and all CBO series only aggregate-level records
   exist. Teo may want to flag some size-only candidates by hand (e.g. GDP-level
   revisions, or CBO Medicaid 2023–25 after the continuous-enrolment unwinding).
2. **Classification changes after October 2021** are folded into the FRD's
   "Underlying2" and cannot be removed from OBR aggregates. Policy adjustment of
   aggregates after that date removes policy only.
3. **Indirect policy effects** are missing for OBR components (PMD notes). An
   adjusted component error still contains the macroeconomic effects of policy.

## 5. Implications for the thesis

- The error–revision identity holds exactly, so predictability tests on revisions
  and on errors are two views of one dataset, as the design assumes.
- The policy-adjusted CBO errors are CBO's own. The OBR aggregate adjustment follows
  the OBR's own decomposition.
- Only about 37% of OBR cells (9,744 of 26,423) can be policy-adjusted. Under the
  D2 default (policy-adjusted errors for case selection), OBR cases will come mainly
  from the major tax heads and the aggregates.

## 6. Gate result

| Criterion | Measured | Result |
|---|---|---|
| Identity holds to floating-point precision for every cell | max deviation 5.7e-14 (OBR), 9.1e-13 (CBO) | **pass** |
| Share of flagged cells reported by series and by source | `stats/e4_checks/flag_shares_by_series_{OBR,CBO}.csv`; OBR 0.41% classification break, 0.81% memo, 18.3% episode; CBO 0%, 0%, 8.8% | **pass** |
