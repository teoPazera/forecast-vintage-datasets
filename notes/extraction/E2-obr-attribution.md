# E2: OBR attribution and policy measures

Run: `python -m fvd.e2_frd_pmd`, then `python -m fvd.e2_efo_tables` (26 September 2026).

## 1. Question

Can the OBR's own attribution of forecast revisions be put on the common schema?
- at aggregate level (Forecast Revisions Database, FRD);
- for individual taxes (the receipts tables of each EFO);
- together with the costings of individual policy measures (Policy Measures
  Database, PMD).

And are these tables consistent with the HOFD forecasts parsed in E1?

## 2. What I did

- **FRD** (`fvd.e2_frd_pmd`)
  - All 34 blocks of both revision sheets (£ billion and % of GDP) were parsed.
    Each row is tagged with its place in the decomposition:
    `total`, `policy`, `policy/receipts`, `policy/spending`, `classification`,
    `underlying`, `underlying/receipts`, `underlying/debt_interest`,
    `underlying/non_interest_spending`.
  - Label variants are read as the same row: "Underlying1", "Underlying2",
    "of which policy" (March 2019).
  - PSNB attribution is stored in the FRD's own convention (positive = borrowing
    raised).
  - The receipts rows are also stored as attribution for £PSCR with the sign flipped
    (plan 4.2), and the spending rows for £TME. PSCR and TME classification changes
    come from the FRD's "Classifications and one-offs" sheet, which records each
    aggregate in its own convention.
- **Intermediate forecast.** The FRD measures November 2020 against the July 2020
  fiscal sustainability report scenario ("FSR+SEU 2020"), not against March 2020.
  That forecast is stored as the intermediate vintage `obr_2020-07_fsr`, dated
  14 July 2020 from the OBR's own page (`tables/vintages/OBR_intermediate.parquet`).
- **PMD.** Tax Measures and Spending Measures were parsed.
  - The workbook is read with cell formatting so that "extrapolated beyond the
    original scorecard period" can be read from the shading key (fill `FFE1E9EE`,
    Notes row 11).
  - Values are kept in £ million in the PMD sign (gain to the Exchequer), and also
    stored in £ billion in the affected series' convention: tax gain = receipts up,
    spending gain = spending down.
- **Crosswalks** (defaults, written before any outcome was looked at; plan 8.6). Each
  file has `confidence` and `reviewed` columns:
  - `crosswalks/pmd_events.csv`: each OBR-era event maps to the EFO published with
    it; pre-2010 Budgets and PBRs map to HM Treasury vintages by rule.
  - `crosswalks/pmd_heads.csv`: tax and spending heads to HOFD sheets.
  - `crosswalks/attribution_labels.csv`: every FRD, CBO and EFO attribution label to
    a D3 category.
- **EFO tables.**
  - The charts-and-tables workbooks of every EFO were downloaded (`fvd.efo_tables`).
    Where the OBR's own link was never archived, the same workbook was taken from
    another archived URL on obr.uk or its former domains. It was accepted only if its
    file name names the same month, year and part (chapter, annex, fiscal/economy)
    and it opens with several "Table/Chart" sheets.
  - Every sheet was read with a generic table reader (`fvd.e2_efo_tables`) and
    classified by title into three kinds:
    - receipts by type ("sources of change to the receipts forecast", "Receipts:
      changes since …");
    - receipts by tax head;
    - per-tax driver tables ("Key changes to the VAT forecast since …", "VAT: changes
      since …").
  - Row roles (forecast level, change, subtotal, driver, memo) come from the labels.
    Each "Change since …" row governs the driver rows below it, which gives each row
    its own previous forecast.
- **Defaults taken.** D3 categories by keyword (`default_category`). The FRD's
  "underlying" cannot be split into D3 categories and gets its own value,
  `underlying_unsplit`. PSNB-neutral items are mapped to `modelling_other`.
- **Files written:**
  - `tables/attribution/OBR_FRD.parquet` and `OBR_EFO.parquet`;
  - `tables/policy_measures/OBR.parquet`;
  - `tables/series/OBR_derived.parquet`: three income-tax aggregates that EFO tables
    report and the HOFD does not hold as sheets;
  - the three crosswalks;
  - `stats/e2_checks/`.

## 3. Findings

**FRD** (`stats/e2_checks/summary_frd_pmd.json`)

- 34 blocks, November 2010 to March 2026, including "March 2019 restated" and
  "FSR+SEU 2020"; 4,379 attribution rows.
- **Block totals vs the HOFD.** The FRD block total equals the change in HOFD £PSNB
  between consecutive vintages in **181 of 181** comparable cells
  (`frd_vs_hofd.csv`).
  - The tolerance is 0.1 plus half the last published digit of each HOFD value,
    because the HOFD rounds early OBR vintages to whole £ billion (e.g. 2011-12: 116,
    117).
  - At a flat 0.1 the match is 161 of 187.
  - November 2020 is compared through the FSR scenario (March 2020 → FSR → November
    2020).
- **Restated March 2019 block.** It is all zeros, while the HOFD memo row sits
  £18–21bn above March 2019. The FRD records that restatement on its Classifications
  sheet ("Various changes"), not as a revision block. These 6 cells are reported
  separately.
- **Parts vs totals.** Policy + classification + underlying = total within 0.1 in 180
  of 182 cells (`frd_parts_sum.csv`).
- **Label drift inside the FRD.** From October 2021 the block reads "Underlying2" and
  includes classification changes (FRD footnote 2), so classification cannot be
  separated after that date. Policy rows extend one year beyond the total in autumn
  blocks: that is the revision relative to the pre-measures forecast (FRD note *),
  flagged `pre_measures_year`.

**PMD**

- 73,450 cells from 4,522 measures; 48,902 cells are shaded as extrapolated.
- **Events.** All 85 events map to a vintage. The 33 events since June 2010 cover
  all 33 OBR vintages one to one.
- **Heads** (94 in total):
  - tax: 28 exact, 3 assumed (stamp duty → property transaction taxes, bank
    surcharge → onshore CT, energy profits levy → oil and gas), 31 with no HOFD
    series;
  - spending: 10 exact, 6 assumed, 16 with no HOFD series.

**EFO receipts tables** (`stats/e2_checks/summary_efo_tables.json`,
`efo_table_coverage.csv`)

- **Workbooks.** 95 of 97 workbooks retrieved:
  - 85 via Wayback captures of their own link and 7 via verified alternate captures;
  - 3 downloaded in a browser by Teo, because the archive never saved them: March
    2011 and December 2014 (single workbooks) and October 2018 fiscal. They are in
    `raw/manual/`, recorded with `via = manual` (`python -m fvd.manual`).
  - The two missing parts (March 2026 chapter 6 and November 2017 economy) have no
    receipts tables.
  - The March 2011 workbook names its sheets by code (`t4.9`) and titles them only
    on its Contents sheet; titles are taken from there.
- **Coverage.** Receipts tables were found for 32 of the 33 regular OBR vintages.
  None for June 2010, the first OBR forecast, which has no "changes since" tables.
  There are no per-tax driver tables in November 2020 or November 2022.
- **Per-tax driver tables.** 106 tables:
  - onshore CT 27;
  - VAT 25;
  - income tax and NICs 14 (to 2016), then non-SA income tax and NICs 13;
  - SA income tax 11;
  - property transaction taxes 8;
  - CGT 2, NICs 2, non-SA income tax 2, fuel 2.
- **Other tables.** 25 receipts-by-type tables and 36 receipts-by-head tables.
- **Attribution.** 6,822 rows with 559 distinct labels. Default categories: 255
  modelling/other, 158 economic determinants, 82 policy, 41 calibration to outturn,
  17 split by tax head (not a cause), 3 underlying (unsplit), 3 classification.
- **Correction (27 September 2026).** In the total-receipts tables, the section
  heading "By policy and forecast differences" had made the keyword rule file
  "Underlying forecast differences" and "PSNB-neutral forecast differences" under
  policy. A heading that names a split no longer decides a row's cause:
  - the underlying rows are now `underlying_unsplit`;
  - the PSNB-neutral rows are `modelling_other`;
  - the "By tax head" rows are `by_tax_head`.

  None of these rows enter the E5 attribution shares, which use the per-tax
  tables, so no E4 or E5 result changes.
- **Consistency checks:**
  - **Forecast levels vs the HOFD** (0.05 + 0.5% of the value): **95.9%** of 1,643
    cells pass (current forecast 96.7%, previous 95.2%). Single-tax tables for SA IT,
    NICs, CGT, property taxes and fuel match 100%, VAT 98% and onshore CT 93%. The
    three hand-downloaded workbooks pass all 130 of their level checks.
  - **"Non-SA income tax".** It is *not* the HOFD's PAYE sheet: there is a steady gap
    of about £8bn. It equals income tax minus self-assessed income tax, which matches
    100%.
  - **Where levels fail:** combined income tax + NICs tables before 2017 (91%),
    non-SA income tax + NICs (94%), onshore CT (93%), and total receipts in December
    2013 and March 2014. There, "current receipts" in the
    EFO table is about £12bn below the HOFD's £PSCR; the table uses a different
    receipts measure.
  - **Drivers add up to the stated change** (0.1 × number of rows): **92.4%** of
    1,133 checks.
    - 86.0% pass using the groupings the tables mark ("of which:" lines and indented
      labels).
    - The other 6.4 points pass only when groupings are inferred from sums, because
      some tables indent sub-items by formatting alone. The `nesting` column of
      `efo_driver_sums.csv` says which applied.
    - Remaining failures are mostly receipts-by-type tables whose totals include
      items not listed as rows (e.g. "Total (including indirect effects)").
  - **EFO "direct effect of Government decisions" rows vs PMD costings** of the same
    event (the E4 cross-check): within 0.1 in 104 of 156 cells; median absolute
    difference £0.02bn (`efo_direct_effects_vs_pmd.csv`).

**Crosswalk review (28–29 September 2026)**

Teo is not a specialist in UK fiscal statistics, so the crosswalk rows were labelled
against a written codebook (`crosswalks/codebook.md`) rather than by judgement.
Section 1 of the codebook records Teo's rulings. The labelling was done by the
keyword rules and Jev (TypeSafe, `jev-1.13.0`) independently, with every call logged
in `crosswalks/llm/jev_results.jsonl`. A row is settled when the two agree, Jev's
confidence is at least 0.7, and the label contains no negation (D20). Pipeline:
`python -m fvd.crosswalk_states`, `python -m fvd.jev_label all`,
`python -m fvd.jev_route`.

- **Events** (`crosswalks/pmd_events.csv`, `status`). The codebook's date check
  (section 4), run in `fvd.e2_frd_pmd`, settles **33 of 33** events since June 2010.
  Each forecast was published in the year the event names and in the half of the
  year its type names, and no two events share a forecast. The 52 pre-2010 events
  are `not_checked`: component forecasts start in June 2010, so they change no result.
- **PMD heads** (`crosswalks/pmd_heads.csv`): **all 94 are final.**
  - 59 were settled by agreement (81% of Jev's top answers matched the keyword
    mapping).
  - The other 35 went to `crosswalks/review_queue_heads.csv`. A separate Claude
    session proposed an answer for each, which Teo accepted. This session then
    checked the 10 answers marked `check` against the source files, and 14 rows in
    total now cite the file used. Three answers were overridden on that evidence
    (`crosswalks/review_queue_heads_decisions.csv`, columns `labeller` and
    `verified_in`).
  - Examples, from EFO March 2026 annex table A.5: Pillar 2 taxes are in onshore
    CT (footnote 2); the energy profits levy is in oil and gas (footnote 6); the
    diverted and residential property developer taxes are "other HMRC taxes"
    (footnote 5), so no series. PMD spending "VAT refunds" maps to no series:
    mapping it to the receipts series would count those measures twice.
- **Attribution labels** (`crosswalks/attribution_labels.csv`, `status`): 572 rows.
  - The 13 FRD and CBO rows are fixed in code.
  - Of the 559 EFO labels, **343 are settled by agreement, 3 are reviewed and 213
    are pending.** Jev's top answer matched the keyword category for 78%.
  - Reasons a row was left pending at routing, where a row can have several:
    - Jev disagreed (123);
    - confidence below 0.7 (119);
    - the row is a group heading, which follows the rows under it (21);
    - negation in the label (21).
  - Pending rows keep the keyword category as a **provisional** value. By category:
    147 modelling and other, 38 economic determinants, 14 policy, 9 calibration to
    outturn, 2 underlying, 2 by tax head, 1 classification.
  - They carry 2,172 of the 6,822 EFO attribution rows.
  - They go to a second model (D21). The package in
    `crosswalks/pending_second_model/` is written and runs standalone on another
    machine; its results are merged with `python -m fvd.merge_second_model`, which
    writes `crosswalks/review_queue_labels.csv`. Neither step has been run.
- **Spot-check of settled rows.** 20 of the 403 rows settled at the time (labels and
  heads) were drawn with seed 20260929 (`crosswalks/llm/spot_check_draw.json`) and
  answered blind in `crosswalks/spot_check_filled.csv`. **19 of 20 match**
  (`python -m fvd.spot_check score crosswalks/spot_check_filled.csv`).
  - The miss ("SRS of household consumption") came from the wording of rule A11.
    The rule now requires an economic cause of the change in the standard-rated
    share; saying what the share is of is modelling.
  - Three wordings (45 attribution rows) moved from economic determinants to
    modelling and other, and are marked reviewed.
- **Where provisional labels are used.** Every use reports how many rows rest on a
  pending label:
  - **E5 attribution shares**: 1,134 of 3,788 OBR EFO driver rows, or 33% of the
    absolute attributed revision (`stats/attribution_shares.csv`, columns
    `n_pending` and `pending_share_of_abs`).
  - **E5 calibration test**: 62 of 364 "calibration to outturn" rows.
  - **E8 case packs**, which carry attribution per vintage. Pending rows will be
    marked there.

  E4 policy adjustment and E6 case selection do not use attribution labels: they use
  the FRD decomposition, fixed in code, and the PMD heads, which are final.

## 4. Open questions

1. **213 pending attribution labels** (gate item, D21). The events and heads are
   final. The labels wait for the second model and then for Teo's review of any rows
   the two models still leave unsettled. Until then, the E5 attribution results are
   provisional to the extent reported above. The workbook review planned on
   27 September (`python -m fvd.review`) is superseded by the codebook route.
2. **D3 for the FRD.** Decided (Teo, 29 September 2026): the FRD's "underlying"
   stays one unsplit category.
3. **Plan vs files:**
   - Receipts are chapter 4 of the EFO until 2019 and in 2023–25, and chapter 3 in
     2020–22 and 2026. Tables are located by title, so chapter numbering does not
     matter.
   - The PMD notes do not say the full decomposition starts in March 2016 (E0 F5).
4. **HOFD "June 2010" mapping** (E0 open question 2). The pre-budget and Budget
   forecasts both have archived reports. This E2 run does not compare values with
   them, because neither has a charts-and-tables workbook with "changes since"
   tables. It remains open for E7, where the report text can be read.

## 5. Implications for the thesis

- **Component-level attribution exists for the main taxes across most vintages.**
  - VAT, onshore CT and income tax + NICs are covered from 2010 to 2026 (with the
    gaps above);
  - SA income tax and property taxes from 2017.
  - The case packs (E8) will carry, per vintage, the OBR's own split of each revision
    into economy, outturn calibration, modelling and policy.
- **Driver labels change over time** (e.g. "Latest receipts data", "Outturn receipts
  and modelling", "Calibration to outturn"). The harmonized categories depend on the
  label crosswalk, so the crosswalk review matters for every attribution result in
  E5.
- **Aggregate attribution is exact.** The FRD reproduces the HOFD's PSNB revisions,
  which makes it a sound basis for policy-adjusted aggregate errors (E4).

## 6. Gate result

| Criterion | Measured | Result |
|---|---|---|
| ≥ 95% of matched cells pass the checks | levels 1,576 / 1,643; driver sums 1,047 / 1,133; FRD totals 181 / 181; combined 2,804 / 2,957 = **94.8%** | **fail** (narrowly). Causes identified: different receipts definitions in two tables and totals that include unlisted items. No parsing errors found in the single-tax tables |
| Event crosswalk covers every event since June 2010 | 33 / 33 events → 33 / 33 OBR vintages | **pass** |
| Coverage of per-tax driver tables reported by vintage and tax | `stats/e2_checks/efo_table_coverage.csv` | **pass** |
| Teo reviews the three crosswalks | events 33 / 33 settled by the date check; heads 94 / 94 final; labels 346 / 559 settled or reviewed, 213 pending the second model (D21), with a spot-check match of 19 / 20 | **pass** for events and heads; **open** for labels |
