# E6: Case scoring and selection (pre-registered)

Run: `python -m fvd.e6_cases register` (29 September 2026, 09:20 UTC), commit
`3884387`, then `python -m fvd.e6_cases select` (09:23 UTC).

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
  - The file was committed (`3884387`) before `select` ran. `select` checks both sets
    of hashes before scoring.
  - No score or z had been computed before registration. The only look at the data
    beforehand was the coverage of policy-adjusted errors by series, which set the
    scope.
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

**Scope** (`cases/selection_run.json`)

| | OBR | CBO |
|---|---|---|
| Series scored | 38 (37 in logs, PSNB in % of GDP) | 21 (17 in logs, 4 in % of GDP) |
| Scored cells | 5,395 | 17,520 |
| Scoreable trajectories (≥ 2 scored cells) | 528 | 787 |
| Eligible (run of ≥ 2 cells with \|z\| ≥ 1.5, same sign) | 273 (52%) | 429 (55%) |
| Median scored cells per trajectory | 11 | 26 |

- **Not scored because there is no policy-adjusted error:** 21 OBR series.
  - PAYE and self-assessed income tax, beer and cider, wine and spirits: their
    parent series are scored.
  - Stamp taxes on shares; gross, public-sector and public-corporation debt
    interest; APF.
  - The current-budget and cyclically adjusted balances.
  - Seven small spending lines: lottery, Network Rail, funded pensions,
    depreciation and imputed pensions.
- **Not scored by the scope rules:** 5 OBR "% of GDP" rate aggregates and £PSNB.
- **Missing σ.** 12 OBR cells have no σ (0 or undefined); none for CBO. 4.7% of OBR
  cells have a σ shrunk towards their family.

**Cases** (15 per source, `cases/cases.parquet`)

| Source | Rank | Trajectory | Episode | Run | Sign | Score |
|---|---|---|---|---|---|---|
| OBR | 1 | APD 2020-21 | COVID | 10 | over | 315 |
| OBR | 2 | Student loans 2022-23 | energy | 7 | over | 156 |
| OBR | 3 | APD 2021-22 | COVID | 9 | over | 145 |
| OBR | 4 | Fuel duties 2020-21 | COVID | 12 | over | 69 |
| OBR | 5 | CDEL 2012-13 | | 5 | under | 59 |
| OBR | 6 | Unfunded public service pensions 2024-25 | | 8 | over | 54 |
| OBR | 7 | Climate change levy 2015-16 | | 11 | over | 46 |
| OBR | 8 | RDEL 2016-17 | | 13 | over | 42 |
| OBR | 9 | Net debt interest 2022-23 | energy | 9 | under | 39 |
| OBR | 10 | RDEL 2017-18 | | 13 | over | 37 |
| OBR | 11 | Electricity generators levy 2022-23 | energy | 2 | over | 34 |
| OBR | 12 | Electricity generators levy 2024-25 | | 4 | over | 33 |
| OBR | 13 | VAT refunds 2015-16 | | 12 | under | 33 |
| OBR | 14 | Oil and gas revenues 2014-15 | | 11 | over | 33 |
| OBR | 15 | PSNB (% of GDP) 2012-13 | | 7 | under | 33 |
| CBO | 1 | Fannie Mae/Freddie Mac 2009 | GFC | 3 | over | 2,242 |
| CBO | 2–4, 6, 8 | Fannie Mae/Freddie Mac 2013, 2014, 2017, 2019, 2015 | | 15–27 | over | 102–293 |
| CBO | 5 | Customs duties 2025 | | 24 | under | 160 |
| CBO | 7 | Other mandatory outlays 2023 | | 26 | under | 118 |
| CBO | 9 | Excise taxes 2009 | GFC | 30 | over | 99 |
| CBO | 10 | Total mandatory outlays 2023 | | 26 | under | 90 |
| CBO | 11 | Miscellaneous receipts 2023 | | 24 | over | 90 |
| CBO | 12 | Customs duties 2019 | | 27 | under | 87 |
| CBO | 13 | Nondefense discretionary outlays 2012 | | 33 | over | 85 |
| CBO | 14 | Excise taxes 2010 | | 28 | over | 84 |
| CBO | 15 | Deficit (% of GDP) 2021 | COVID | 29 | under | 84 |

- **OBR cases** include known episodes:
  - the collapse in air travel and driving in 2020–21 (APD, fuel duties);
  - the 2014 fall in oil prices (oil and gas revenues);
  - the RPI spike in 2022 (net debt interest, under-forecast);
  - borrowing in 2012-13 staying above the June 2010 plan (PSNB);
  - persistent DEL underspends (RDEL 2016-17 and 2017-18, over-forecast).
- **The COVID cap was binding.** Four higher-scoring COVID trajectories were passed
  over: VAT, RDEL, and locally financed current spending in 2020-21 and 2021-22.
- **CBO cases are dominated by Fannie Mae/Freddie Mac** (6 of 15, including the top
  4). See open question 1.
- The other CBO cases include:
  - the 2025 tariffs (customs duties, under-forecast);
  - Federal Reserve remittances turning negative (miscellaneous receipts 2023,
    over-forecast);
  - the COVID deficit (2021).

  The causes named in this section are my reading of well-known episodes, not
  checked against any document. The post-hoc documents establish them in R1 and E8.
- **Onset and correction.** The qualifying run starts at the first scored vintage
  in 12 of 15 OBR cases and 14 of 15 CBO cases: most errors were large from the
  earliest forecast and stayed so.
  - Corrected by at least half before the last vintage: 13 of 15 cases per source.
  - Median lead-time window: 9 vintages (OBR), 25 (CBO).

**Controls** (`cases/controls.parquet`): **2 per source**, where up to 30 were
possible. See open question 2.

**Random sample** (`cases/random_sample.parquet`, seed 20260930): 30 per source.
- OBR: 12 of the 30 are eligible and 2 are also cases.
- CBO: 11 of the 30 are eligible and none are cases.

**Counts per stratum (gate)**

| | OBR | CBO |
|---|---|---|
| Cases by family | business taxes 4, duties 3, DEL spending 3, other spending 2, aggregate 1, consumption taxes 1, debt interest 1 | mandatory outlays 8, customs 2, excise 2, aggregate 1, discretionary outlays 1, miscellaneous receipts 1 |
| Cases by episode | COVID 3, energy 3, none 9 | GFC 2, COVID 1, none 12 |
| Controls | 2 (other spending) | 2 (mandatory outlays) |
| Random sample by episode | COVID 4, energy 3, none 23 | none 30 |
| Distinct target periods: cases / controls / random / all | 9 / 2 / 13 / 15 | 11 / 2 / 21 / 25 |

The full breakdown by source × family × episode is reproducible with
`cases/*.parquet`.

**Pending attribution labels.** E6 does not use them. Policy adjustment uses the FRD
decomposition, fixed in code, and the PMD heads, which are final (E2 note).

## 4. Open questions (for Teo; each would be a logged deviation)

1. **Exclude CBO Fannie Mae/Freddie Mac from case selection?**
   - CBO's own README (`raw/cbo/eval-projections-682559c/README.md`, line 123)
     removes these outlays from all its accuracy analyses. The reason: "CBO and the
     Administration account for those entities' transactions differently". CBO's
     totals, mandatory outlays and deficit already exclude them.
   - The series therefore measures an accounting difference, not a forecast error.
     It is the kind of measurement break D13 excludes. E4 could not flag it, because
     CBO records no classification changes.
   - Its σ comes from years with near-zero outlays, which gives z values in the
     hundreds.
   - **Recommendation:** exclude `cbo.outlay.fannie_freddie` from scoring. The reason
     is in CBO's documentation and does not depend on the scores. The pre-registration
     should have done this; that is my omission.
2. **Controls.** The rule requires max |z| < 0.5 over every scored cell. Only 15 OBR
   and 11 CBO scoreable trajectories meet it, mostly short ones with 2–3 cells.
   Matching on family, year and horizon then leaves 2 per source. Pool sizes under
   other definitions (trajectories meeting them, before matching):

   | Control definition | OBR | CBO |
   |---|---|---|
   | max \|z\| < 0.5 (registered) | 15 | 11 |
   | max \|z\| < 1.0 | 62 | 99 |
   | mean \|z\| < 0.5 | 71 | 154 |
   | max \|z\| < 1.5 (never beyond the case threshold) | 166 | 234 |

   **Recommendation:** mean |z| < z_low (0.5), keeping the matching rules. It keeps
   the plan's threshold, means "well forecast on average", and gives pools large
   enough to match every case. The random sample already covers base rates.
   Alternatively, max |z| < 1.0.
3. **Short trajectories.** A run of 2 cells can make a case: the electricity
   generators levy 2022-23 has only 2 scored cells. This is within the rule and is
   noted only.
4. **Score scale.** The score is a sum over the run, so long trajectories score
   higher: CBO's have about 26 cells, the OBR's about 11. Selection is per source, so
   this does not mix the two sources. Within CBO, it favours early targets with long
   histories.

## 5. Implications for the thesis

- **The OBR case list is substantive** and spans unforeseeable shocks (COVID, energy
  prices) and slow-moving errors (DEL underspends, PSNB 2012-13). That is the mix
  research question 3 needs: causes absent from earlier documents, and causes present
  but not acted on.
- **CBO needs the Fannie Mae/Freddie Mac decision** before the list is usable. The
  other nine CBO cases look substantive.
- **Controls, as registered, are too few** for case–control comparisons. The random
  sample (30 per source) is intact.
- **R1 pilot** (next stage) picks the top 3 per source among cases whose target
  period has a post-hoc document. It should run only after questions 1 and 2 are
  settled, because the rule freezes when R1 starts.

## 6. Gate result

| Criterion | Measured | Result |
|---|---|---|
| Pre-registration written and hashed before selection | registered 09:20 UTC, committed `3884387`, selection 09:23 UTC; hashes verified at run | **pass** |
| Counts reported per stratum (source, family, episode) | section 3 | **pass** |
| Distinct target periods reported per source | OBR 15, CBO 25 across cases, controls and random sample | **pass** |
| (substance) enough controls | 2 per source of up to 30 | **flagged**: open question 2 |
