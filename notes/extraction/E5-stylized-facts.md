# E5: Stylized facts and numbers-only predictability

Run: `python -m fvd.e5_stylized_facts` (26 September 2026). This stage reports
results only; Teo reviews them before case selection (E6).

## 1. Question

How large, biased and persistent are the errors and revisions of each forecaster?
Are they predictable from the numbers alone (bias, Mincer–Zarnowitz, revision
autocorrelation, error on revision)? What calibration targets should the synthetic
generator match?

## 2. What I did

- **Sample.** Every chained cell of `tables/cells` (memo vintages excluded) with a
  latest outturn. The data are grouped by forecaster (OBR, HM Treasury, CBO) and
  series family (D7), and by horizon bucket (D6: <0, 0–6, 6–12, 12–24, 24–36, 36+
  months to the end of the target period). Each result is computed:
  - for raw and policy-adjusted errors (D2);
  - with and without episode windows (D8).
- **Error basis.**
  - Level series use the log error log(F/A) and the log revision, which lets the
    series of a family be pooled.
  - Balance and rate series (PSNB, current budget and debt in % of GDP; the CBO
    deficit and debt in $bn; economy rates) are analysed series by series in their
    own unit and never pooled.
- **Statistics:**
  - **Bias:** mean error with standard errors clustered by target (series × target
    period).
  - **Mincer–Zarnowitz:** outturn on forecast (in logs for levels), with a joint Wald
    test of intercept 0 and slope 1, clustered.
  - **Revision autocorrelation (Nordhaus):** correlation and clustered slope of
    consecutive revisions of the same target, and the share of consecutive revisions
    with the same sign (binomial test against 0.5).
  - **Error on revision (Coibion–Gorodnichenko):** e_v on r_v, clustered. Here
    e = F − A, so CG's positive coefficient (under-reaction) appears as a **negative**
    coefficient.
  - **Attribution shares:** the share of the absolute revision coming from each
    harmonized category, by horizon bucket.
  - **Calibration test:** whether the OBR's "calibration to outturn" revisions are
    predictable from the previous revision.
- **Files written:**
  - `stats/stylized_facts.csv` (1,286 rows);
  - `stats/efficiency_tests.csv` (2,750 rows);
  - `stats/attribution_shares.csv`;
  - `stats/complete_target_periods.csv`;
  - `stats/calibration_targets.json` (targets for the synthetic generator: error SD
    and bias by bucket, revision autocorrelation, same-sign share, with sample sizes).

## 3. Findings

**Sample sizes.** Complete target periods (with an outturn) per series:

| Forecaster | Median | Range |
|---|---|---|
| OBR | 16 | 3–17 |
| HM Treasury | 26 | 15–45 |
| CBO | 42 | 18–44 |

With 12–24 month horizons, families have 28–112 target periods for the OBR and
43–165 for CBO. Every figure below carries its n in the CSV files.

**Headline results at 12–24 months, raw errors, episodes included** (pooled level
series: log points; balance series in their units):

| Forecaster / family | n cells (targets) | Mean error (s.e.) | SD | Revision autocorr. | Same-sign share | CG coef. (p) |
|---|---|---|---|---|---|---|
| OBR aggregates (£PSCR, £TME) | 58 (28) | −0.054 (0.005) | 0.034 | 0.02 | 0.53 | 0.21 (0.43) |
| OBR income taxes | 116 (56) | 0.003 (0.009) | 0.069 | 0.14 | 0.60*** | 0.00 (0.99) |
| OBR consumption taxes | 87 (42) | −0.063 (0.013) | 0.084 | −0.21 | 0.47 | 0.19 (0.16) |
| OBR capital taxes | 116 (56) | −0.034 (0.019) | 0.149 | −0.18 | 0.51 | 0.31 (0.08) |
| OBR business taxes | 141 (70) | 0.038 (0.048) | 0.427 | 0.07 | 0.54* | 0.20 (0.59) |
| OBR local-authority spending | 87 (42) | −0.171 (0.040) | 0.262 | −0.18 | 0.45* | 0.03 (0.81) |
| OBR PSNB (% of GDP) | 29 (14) | −0.44 pp (0.57) | 2.68 | 0.02 | 0.55 | 0.43 (0.31) |
| CBO individual income taxes | 105 (43) | 0.031 (0.018) | 0.116 | 0.21 | 0.60*** | −0.30 (0.38) |
| CBO payroll taxes | 105 (43) | 0.012 (0.006) | 0.039 | 0.15 | 0.58*** | −0.65 (0.17) |
| CBO corporate income taxes | 105 (43) | 0.070 (0.045) | 0.278 | −0.01 | 0.53 | 0.44 (0.37) |
| CBO mandatory outlays | 450 (165) | −0.027 (0.014) | 0.176 | 0.21 | 0.58*** | −0.46 (0.26) |
| CBO discretionary outlays | 236 (87) | −0.035 (0.007) | 0.067 | −0.19 | 0.49 | 0.20 (0.01) |
| CBO budget balance ($bn) | 98 (41) | +210 (86) | 507 | 0.08 | 0.55** | −0.39 (0.09) |

\* p < 0.05, \*\* p < 0.01, \*\*\* p < 0.001 (binomial test of the same-sign share
against 0.5).

- **Bias.**
  - OBR forecasts of the receipts and spending totals (£PSCR, £TME) are below
    outturn by about 5 log points at 12–24 months. Part of that is classification
    (E4 flags £PSCR and £TME trajectories) and nominal growth surprises.
  - OBR local-authority spending and debt interest are over-forecast in logs
    (−0.17 and −0.11: the forecast is below outturn).
  - CBO discretionary outlays are under-forecast by 3.5 log points.
  - The CBO budget balance is over-forecast by $210bn on average at 12–24 months
    (clustered s.e. 86): the deficit came out larger than projected.
- **Revision persistence** (the numbers-only signal the research question starts
  from).
  - Consecutive revisions have the same sign more often than 50% for:
    - income taxes, for both forecasters (OBR 0.60, CBO individual income 0.60);
    - CBO payroll taxes (0.58), CBO mandatory outlays (0.58) and the CBO aggregates
      (0.59, ρ = 0.46).
  - Also, more weakly, OBR other receipts (0.57) and business taxes (0.54, p = 0.047).
    Not for OBR consumption or capital taxes, or for spending other than DEL.
  - Several families show *negative* revision autocorrelation, i.e. revisions partly
    reversed: OBR consumption taxes −0.21, capital taxes −0.18, debt interest −0.20;
    CBO discretionary −0.19.
- **Mincer–Zarnowitz** rejects intercept 0 / slope 1 at 12–24 months for most
  aggregates and several families (p < 0.05): OBR aggregates, consumption taxes,
  income taxes, local spending; CBO aggregates, outlays, excise and payroll taxes. It
  does not reject for OBR business, capital and other taxes, or for CBO corporate and
  individual income taxes.
- **Error on revision.** Mostly not significant at 12–24 months. Exceptions: CBO
  aggregates (−0.26, p = 0.03, i.e. under-reaction in CG terms); CBO discretionary
  outlays (+0.20, p = 0.01, over-reaction); OBR welfare (+0.24, p = 0.03).
- **Attribution shares** (share of the absolute revision; `attribution_shares.csv`):
  - **OBR PSNB (FRD):** "underlying" 50–68% by bucket, policy 27–49%,
    classification 0–8%.
  - **OBR tax drivers (EFO):** economic determinants 20–38%, modelling and other
    28–50%, calibration to outturn 6–30% (highest at 6–12 months), policy 9–29%.
  - **CBO:** policy 57–71%, economic 5–25%, technical 19–26%. The policy share is
    inflated because CBO revenue changes are legislative-only before 2024 (E3).
- **Calibration to outturn** (OBR EFO driver tables, 177 cells, 68 targets): not
  predictable from the previous revision overall (slope −0.03, p = 0.73). At 36+
  months, however, the slope is −0.19 (p = 0.002, 71 cells): long-horizon calibration
  revisions partly reverse the previous revision.
- **Episodes.** Excluding the GFC, COVID and energy windows changes the pooled 12–24
  month biases only slightly. Exceptions:
  - OBR business taxes: +0.038 → +0.086;
  - OBR debt interest: −0.108 → −0.045;
  - CBO mandatory outlays: −0.027 → −0.008.

## 4. Open questions

1. **Error basis for pooling.** Level series use log errors. Balances are not pooled,
   because per cent of GDP is available only for OBR PSNB, CB and PSND and the CBO
   deficit and debt (via GDP). Is that the pooling Teo wants for E6? E6 uses the same
   basis, per the plan.
2. **Classification.** The OBR aggregate bias includes classification changes. The
   policy-adjusted OBR aggregate errors remove FRD classification changes only up to
   October 2021 (E4).
3. **Multiple testing.** 2,750 tests are reported without adjustment. For the
   thesis, pre-specify the few tests that matter (e.g. same-sign share of revisions
   by family at 12–24 months).

## 5. Implications for the thesis

- **Numbers-only predictability is real but uneven.** Revisions to income-based taxes
  (both forecasters) and CBO mandatory outlays are persistent. Revisions to taxes
  driven by volatile bases (corporation, capital and consumption taxes) are not, and
  some partly reverse. That points case selection (E6) at persistent-run
  trajectories in income taxes and aggregates, and makes the "text adds information
  beyond numbers" test hardest there.
- **The OBR has 14–17 complete target periods per series.** Tests pooled within
  family are essential; single-series OBR results will be noisy (E6 already shrinks
  σ when fewer than 8 target periods are available).
- **Calibration targets for the synthetic generator** are saved per forecaster,
  family and bucket. The generator should reproduce:
  - persistent revisions for income-type series (ρ ≈ 0.14–0.46, same-sign ≈ 0.58–0.61);
  - mean-reverting revisions for volatile bases (ρ ≈ −0.2);
  - error SDs rising with horizon.

## 6. Gate result

| Criterion | Measured | Result |
|---|---|---|
| Report only; Teo reviews before case selection | this note and `stats/` | **awaiting review** |
