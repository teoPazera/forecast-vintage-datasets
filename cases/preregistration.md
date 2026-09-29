# E6 pre-registration: case scoring and selection

Written 29 September 2026, before any case score was computed. The registration
step (`python -m fvd.e6_cases register`) records the SHA-256 of this file and of every
input table in `cases/preregistration.json`. The selection step
(`python -m fvd.e6_cases select`) refuses to run if either has changed, and reads its
parameters from the block at the end of this file.

This rule is not changed after R1 starts. Any later change is logged below under
"Deviations", with its reason.

## What was known when this was written

- The E4 cell table and the E5 results (bias, dispersion and revision persistence by
  family), which Teo reviewed on 29 September 2026.
- **No case score or z value had been computed, and no document text had been read.**
- The coverage of policy-adjusted errors by series, which decides the scope below.

## Decisions this rests on (plan section 10, decided 29 September 2026)

- **D1:** errors against the latest outturn.
- **D2:** policy-adjusted errors.
- **D6:** default horizon buckets.
- **D7:** level series in log errors; balances separate, in per cent of GDP.
- **D8:** z* = 1.5, z_low = 0.5, K = 15 and M = 30 per source; at most 3 cases per
  episode window.
- **D11–D13:** OBR vintages only, no economy series, no classification breaks.

## 1. Scope: which trajectories are scored

A trajectory is one (source, series, target period). It is scored when all of these
hold:

1. **The target period has a latest outturn** (D1).
2. **OBR: forecasts made by the OBR only**, from June 2010. HM Treasury vintages are
   not scored and do not enter σ (D11).
3. **Not an economy series** (D12).
4. **Not flagged for a classification break** in E4 (D13).
5. **The series has a policy-adjusted error** (D2).
   - In the OBR data, the series without one are:
     - the "% of GDP" aggregates other than PSNB;
     - the current-budget and cyclically adjusted balances;
     - the components with no PMD head.
   - They are listed, with counts, in the E6 note. They are not scored rather than scored on raw
     errors, so that no case is driven by a policy change the forecaster was not
     asked to predict.
   - The sub-series among them are covered by their parent series, which is scored:
     PAYE and self-assessed income tax by income tax; beer and cider, wine and
     spirits by alcohol.
6. **Each quantity is scored once.**
   - Balances are scored in per cent of GDP. The HOFD's £ version of PSNB
     (`obr.psnb_gbp`) is not scored, because `obr.psnb` (% of GDP) is.
   - Rate series (ratios to GDP, such as receipts or net debt in % of GDP) are not
     scored; the £ level series stand for them where they have a policy adjustment.
7. **Cells used**: chained cells (no memo vintages, D14) whose role is `in_progress`
   or `future` (horizon ≥ 0), with a policy-adjusted error. These are the "scored
   cells".

A trajectory with at least 2 scored cells is **scoreable**. Only scoreable
trajectories can become cases, controls or members of the random sample.

## 2. Error basis

- **Level series:** `log(F_pa / A)`, the log of the policy-adjusted forecast over
  the latest outturn.
- **Balance series:** the policy-adjusted error in percentage points of GDP.
  - OBR: `obr.psnb` is already in % of GDP.
  - CBO balance series (the deficit, Fannie Mae/Freddie Mac, net interest, estate and
    gift taxes, all in $ billion): the error divided by actual GDP of the target
    fiscal year, × 100. The GDP file is `input_data/actual_GDP.csv`, and this is
    CBO's own method (`projection_error_pct_GDP`).

Positive = over-forecast, as everywhere in the plan.

## 3. Scale σ and z

- **Buckets.** For each scored cell, σ is computed for its series and horizon bucket
  (D6: 0–6, 6–12, 12–24, 24–36, 36+ months).
- **Own σ.** `σ_own = 1.4826 × median |e − median(e)|` over the scored cells of the
  same series and bucket, **excluding every cell whose target period is the cell's
  own** (leave-one-target-out).
- **Shrinkage.** Let n be the number of distinct target periods behind σ_own.
  - If n ≥ 8, σ = σ_own.
  - Otherwise σ = (n/8) · σ_own + (1 − n/8) · σ_family.
  - σ_family is the same statistic over the scored cells of every series in the same
    source, family and error basis, in the same bucket, again excluding the target
    period.
  - If σ_own is 0 or undefined, it gets weight 0.
- **z.** `z = e / σ`. A cell whose σ is 0 or undefined gets no z and breaks any
  run.

## 4. Runs, score, onset, correction

1. **Order.** The scored cells of a trajectory, ordered by vintage publication date.
2. **Run.** A maximal sequence of consecutive scored cells with the same sign of z
   and `|z| ≥ z*`.
3. **Longest run.** The longest run is the qualifying run. Ties go to the larger sum
   of |z|, then to the earlier onset.
4. **Score.** The case score is the sum of |z| over the qualifying run. A trajectory
   is **eligible** as a case if its qualifying run has length ≥ 2.
5. **Recorded for every scoreable trajectory:**
   - **Onset vintage:** the first vintage of the qualifying run.
   - **Correction vintage:** the first chained vintage after the onset, of any cell
     role and with a policy-adjusted error, whose error has fallen to at most half
     of the onset error in the same direction (`e_v / e_onset ≤ 0.5`). This is the
     first forecast that moved at least half way from its onset value toward the
     outturn. If there is none, the trajectory is recorded as not corrected.
   - **Lead-time window:** the vintages from the onset to the correction, both
     included. If there is no correction, it runs to the last chained vintage.

## 5. Selection, per source

1. **Cases.**
   - Go through the eligible trajectories in order of score, highest first. Ties go
     to series_id, then target period.
   - Take a trajectory unless it would give its episode window more than 3 cases,
     or give its series family more than 2 cases for the same target period.
   - Stop at K cases.
2. **Controls.**
   - For each case, in selection order, take up to 2 scoreable trajectories that meet
     all of these conditions:
     - same source, family and error basis;
     - max |z| < z_low over all their scored cells;
     - the first year of the target period within ±2 years of the case's;
     - maximum horizon among scored cells within ±12 months of the case's (similar
       horizon coverage);
     - not a case and not already a control.
   - Candidates are ranked by, in order:
     1. |difference in the number of scored cells|;
     2. |difference in the maximum horizon|;
     3. |difference in year|;
     4. series_id, then target period.
3. **Random sample.**
   - M trajectories drawn uniformly, without replacement, from all scoreable
     trajectories of the source, sorted by trajectory id. The draw uses Python's
     `random.Random(seed).sample`.
   - The draw does not look at scores. It may include cases and controls, which are
     flagged.

## 6. Pre-specified numbers-only tests

D22: the same-sign share of consecutive revisions with the later revision at 12–24
months, and the error-on-revision coefficient at 12–24 months (policy-adjusted),
by source and family, in `stats/prespecified_tests.csv`. They were computed in E5
before this file was written. They are listed here so that the text-based results in
later stages are compared against these two tests and no others.

## 7. Parameters (read by the code)

```yaml
error_basis: {outturn: latest, errors: policy_adjusted}
z_star: 1.5
z_low: 0.5
K: 15
M: 30
min_run: 2
max_cases_per_episode: 3
max_cases_per_family_target: 2
shrink_n: 8
mad_scale: 1.4826
buckets: [[0, 6, "0-6"], [6, 12, "6-12"], [12, 24, "12-24"], [24, 36, "24-36"], [36, .inf, "36+"]]
control_years: 2
control_max_horizon_months: 12
controls_per_case: 2
correction_share: 0.5
random_seed: 20260930
not_scored_duplicates: [obr.psnb_gbp]
not_scored_kinds: [rate]
not_scored_families: [economy]
forecasters: [OBR, CBO]
```

## Deviations

None.
