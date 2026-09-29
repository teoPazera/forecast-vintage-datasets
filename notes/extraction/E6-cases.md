# E6: Case scoring and selection (pre-registered)

Runs on 29 September 2026:

1. `python -m fvd.e6_cases register` at 09:20 UTC, committed as `3884387`.
2. First selection at 09:23 UTC, committed as `31c3c3f`.
3. Two deviations decided by Teo, logged in `cases/preregistration.md` and registered
   with `python -m fvd.e6_cases deviate`, committed as `f849abc`.
4. Current selection, run after `f849abc`.

## 1. Question

Which trajectories had large, persistent forecast errors (cases)? Which stayed
well forecast (controls)? And which random trajectories give the base rates? Each
selection had to follow a rule written and hashed before any score was computed.

## 2. What I did

- **Decisions.** Teo's answers to the E5 recommendations were recorded in plan
  section 10 (D1, D2, D3, D5, D7, D8, D11–D13, and D22 for the pre-specified tests).
- **Pre-registration.** The rule was written to `cases/preregistration.md` with a
  yaml parameter block. The code reads its parameters from that block, so it cannot
  differ from the text.
  - `register` recorded the file's SHA-256 (`1c395a20…`) and the hashes of the input
    tables in `cases/preregistration.json`.
  - The file was committed before any selection ran.
  - No score or z had been computed before registration. The only look at the data
    beforehand was the coverage of policy-adjusted errors by series, which set the
    scope.
- **Deviations** (section "Deviations" of the pre-registration):
  - The text above that section is byte-identical to the registered text. `deviate`
    checks this against the registered hash, then records the new hash of the
    whole file.
  - Each deviation's yaml block overrides section 7.
  - `select` checks the latest hash and the input hashes before scoring.
- **Choices the rule makes beyond the plan**, all within the decisions above:
  - Series without a policy-adjusted error are not scored (D2), rather than scored on
    raw errors.
  - Each quantity is scored once: balances in % of GDP, `obr.psnb_gbp` not scored,
    rate series not scored.
  - CBO balance series are put in % of GDP with CBO's own method (divided by actual
    GDP of the target year).
  - "Similar horizon coverage" for controls means a maximum horizon within
    12 months of the case's.
  - The cell table's `z` column stays empty. z is written to `cases/scored_cells`
    instead, so the registered input does not change.
- **Files written:**
  - `cases/scored_cells`;
  - `cases/trajectory_scores` (every scoreable trajectory with its score and
    selection outcome);
  - `cases/cases`, `cases/controls`, `cases/random_sample`;
  - schema files next to each;
  - `cases/selection_run.json` (run time, hashes, counts, excluded series).

## 3. Findings

**The first selection and the deviations**

The first selection (`31c3c3f`) had two problems:
- 6 of its 15 CBO cases were Fannie Mae/Freddie Mac outlays, including the top 4,
  with scores up to 2,242.
- It found only 2 controls per source.

Teo decided two deviations before R1:
1. **Fannie Mae/Freddie Mac outlays are not scored.** CBO itself removes them from
   its accuracy analyses because CBO and the Administration account for them
   differently (`raw/cbo/eval-projections-682559c/README.md`, line 123). The
   original rule should have excluded the series.
2. **Controls need mean |z| < 0.5** instead of max |z| < 0.5. Almost no trajectory
   stays within 0.5σ at every vintage.

Removing the series also changes the CBO random sample. The draw is from the sorted
list of scoreable trajectories, which is now shorter. The seed is unchanged.

**Scope** (`cases/selection_run.json`)

| | OBR | CBO |
|---|---|---|
| Series scored | 38 (37 in logs, PSNB in % of GDP) | 20 (17 in logs, 3 in % of GDP) |
| Scored cells | 5,395 | 17,150 |
| Scoreable trajectories (≥ 2 scored cells) | 528 | 769 |
| Eligible (run of ≥ 2 cells with \|z\| ≥ 1.5, same sign) | 273 (52%) | 418 (54%) |
| Median scored cells per trajectory | 11 | 26 |

- **Not scored because there is no policy-adjusted error:** 21 OBR series.
  - PAYE and self-assessed income tax, beer and cider, wine and spirits: their
    parent series are scored.
  - Stamp taxes on shares; gross, public-sector and public-corporation debt
    interest; APF.
  - The current-budget and cyclically adjusted balances.
  - Seven small spending lines: lottery, Network Rail, funded pensions,
    depreciation and imputed pensions.
- **Not scored by the scope rules:** 5 OBR "% of GDP" rate aggregates, £PSNB, and
  CBO Fannie Mae/Freddie Mac (deviation 1).
- **Missing σ.** 12 OBR cells have no σ (0 or undefined); none for CBO. 4.7% of OBR
  cells have a σ shrunk towards their family.

**Cases** (15 per source, `cases/cases.parquet`)

| Rank | OBR | Episode | Run | Sign | Score | CBO | Episode | Run | Sign | Score |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | APD 2020-21 | COVID | 10 | over | 315 | Customs duties 2025 | | 24 | under | 160 |
| 2 | Student loans 2022-23 | energy | 7 | over | 156 | Other mandatory 2023 | | 26 | under | 118 |
| 3 | APD 2021-22 | COVID | 9 | over | 145 | Excise taxes 2009 | GFC | 30 | over | 99 |
| 4 | Fuel duties 2020-21 | COVID | 12 | over | 69 | Total mandatory 2023 | | 26 | under | 90 |
| 5 | CDEL 2012-13 | | 5 | under | 59 | Miscellaneous receipts 2023 | | 24 | over | 90 |
| 6 | Unfunded public service pensions 2024-25 | | 8 | over | 54 | Customs duties 2019 | | 27 | under | 87 |
| 7 | Climate change levy 2015-16 | | 11 | over | 46 | Nondefense discretionary 2012 | | 33 | over | 85 |
| 8 | RDEL 2016-17 | | 13 | over | 42 | Excise taxes 2010 | | 28 | over | 84 |
| 9 | Net debt interest 2022-23 | energy | 9 | under | 39 | Deficit (% of GDP) 2021 | COVID | 29 | under | 84 |
| 10 | RDEL 2017-18 | | 13 | over | 37 | Nondefense discretionary 2010 | | 32 | over | 81 |
| 11 | Electricity generators levy 2022-23 | energy | 2 | over | 34 | Other mandatory 2024 | | 25 | under | 78 |
| 12 | Electricity generators levy 2024-25 | | 4 | over | 33 | Medicare 2021 | COVID | 27 | over | 78 |
| 13 | VAT refunds 2015-16 | | 12 | under | 33 | Nondefense discretionary 2018 | | 28 | over | 74 |
| 14 | Oil and gas revenues 2014-15 | | 11 | over | 33 | Total discretionary 2012 | | 32 | over | 74 |
| 15 | PSNB (% of GDP) 2012-13 | | 7 | under | 33 | Customs duties 2022 | energy | 18 | under | 72 |

The OBR list is unchanged by the deviations.

- **Known episodes among them:**
  - the collapse in air travel and driving in 2020–21 (APD, fuel duties);
  - the 2014 fall in oil prices (oil and gas revenues);
  - the RPI spike in 2022 (net debt interest, under-forecast);
  - borrowing in 2012-13 staying above the June 2010 plan (PSNB);
  - persistent DEL underspends (RDEL, over-forecast);
  - tariffs (CBO customs duties 2019, 2022 and 2025, all under-forecast);
  - Federal Reserve remittances turning negative (CBO miscellaneous receipts 2023);
  - the COVID deficit.

  These causes are my reading of well-known episodes, not checked against any
  document. The post-hoc documents establish them in R1 and E8.
- **The COVID cap was binding for OBR.** Four higher-scoring COVID trajectories were
  passed over: VAT, RDEL, and locally financed current spending in 2020-21 and
  2021-22.
- **Onset and correction.**
  - The qualifying run starts at the first scored vintage in 12 of 15 OBR cases and
    all 15 CBO cases: most errors were large from the earliest forecast and stayed
    so.
  - Corrected by at least half before the last vintage: 13 of 15 OBR cases and 14 of
    15 CBO cases.
  - Median lead-time window: 9 vintages (OBR), 26 (CBO).

**Controls** (`cases/controls.parquet`): **5 OBR and 8 CBO**, where up to 30 per
source were possible. They matched 3 OBR and 5 CBO cases. Because the rule now uses
the mean, a control can have one vintage that was well off: the largest max |z|
among controls is 2.0.

**Random sample** (`cases/random_sample.parquet`, seed 20260930): 30 per source.
- OBR: 12 of the 30 are eligible and 2 are also cases.
- CBO: 14 of the 30 are eligible and none are cases.

**Counts per stratum (gate)**

| | OBR | CBO |
|---|---|---|
| Cases by family | business taxes 4, duties 3, DEL spending 3, other spending 2, aggregate 1, consumption taxes 1, debt interest 1 | discretionary outlays 4, mandatory outlays 4, customs 3, excise 2, aggregate 1, miscellaneous receipts 1 |
| Cases by episode | COVID 3, energy 3, none 9 | COVID 2, GFC 1, energy 1, none 11 |
| Controls by family | business taxes 2, other spending 2, duties 1 | mandatory outlays 5, discretionary outlays 3 |
| Controls by episode | none 5 | COVID 2, GFC 2, none 4 |
| Random sample by episode | COVID 4, energy 3, none 23 | energy 1, none 29 |
| Distinct target periods: cases / controls / random / all | 9 / 4 / 13 / 15 | 10 / 6 / 20 / 26 |

**Pending attribution labels.** E6 does not use them. Policy adjustment uses the FRD
decomposition, fixed in code, and the PMD heads, which are final (E2 note).

## 4. Open questions

1. **Controls are still few**, and the cause is the matching, not the threshold.
   - A control must come from the case's **family** and have a target period
     within **±2 years**.
   - Several families have only one or two series: CBO customs, excise and
     miscellaneous receipts; OBR DEL spending; PSNB. They have no well-forecast
     trajectory that close to the case.
   - Cases with at least one candidate, after the year and horizon conditions:

     | Matching | OBR | CBO |
     |---|---|---|
     | same family, ±2 years (current) | 5 / 15 | 7 / 15 |
     | same family, ±4 years | 7 / 15 | 10 / 15 |
     | same side (receipts or spending), ±2 years | 11 / 15 | 14 / 15 |

   - Options:
     - **(a)** Accept the controls as they are. The random sample carries the base
       rates, and the plan says "up to 2".
     - **(b)** A third deviation: match on the same side of the budget instead of the
       same family.

     The plan's family rule was meant to keep a control comparable in its drivers.
     For single-series families that is impossible within ±2 years, and the same
     side is the closest comparable group. **Recommendation: (b).**
2. **Short trajectories.** A run of 2 cells can make a case: the electricity
   generators levy 2022-23 has only 2 scored cells. This is within the rule and is
   noted only.
3. **Score scale.** The score is a sum over the run, so long trajectories score
   higher: CBO's have about 26 cells, the OBR's about 11. Selection is per source, so
   this does not mix the two sources. Within CBO, it favours early targets with long
   histories.

## 5. Implications for the thesis

- **Both case lists now look substantive**, pending the post-hoc documents. They
  span:
  - unforeseeable shocks: COVID, energy prices, tariffs;
  - slow-moving errors: DEL underspends, PSNB 2012-13, CBO discretionary outlays.

  That is the mix research question 3 needs: causes absent from earlier documents,
  and causes present but not acted on.
- **Case–control comparisons are thin** until open question 1 is settled. The random
  sample (30 per source) is intact.
- **R1 pilot** (next stage) picks the top 3 per source among cases whose target
  period has a post-hoc document. The rule freezes when R1 starts, so open question
  1 should be settled first.

## 6. Gate result

| Criterion | Measured | Result |
|---|---|---|
| Pre-registration written and hashed before selection | registered 09:20 UTC, committed `3884387` before the first selection; deviations logged, hashed and committed (`f849abc`) before the current selection; hashes verified at each run | **pass** |
| Counts reported per stratum (source, family, episode) | section 3 | **pass** |
| Distinct target periods reported per source | OBR 15, CBO 26 across cases, controls and random sample | **pass** |
| (substance) enough controls | OBR 5, CBO 8 (up to 30 each) | **flagged**: open question 1 |
