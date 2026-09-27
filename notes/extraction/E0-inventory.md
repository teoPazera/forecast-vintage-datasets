# E0: Inventory and vintage calendar

Run: `python -m fvd.e0_inventory` then `python -m fvd.e0_factcheck` (26 September 2026).

## 1. Question

Can every forecast vintage in the OBR and CBO sources be tied to a publication and an
exact publication date? Is every document needed later retrievable, with recorded
provenance? Do the plan's statements about the sources (section 5) hold in the files?

## 2. What I did

- **Access.** `obr.uk` (Cloudflare) and `cbo.gov` (DataDome) answered every scripted
  request with a browser challenge, whatever the client sent. The refusals are recorded
  in `inventory/sources.csv` (status 403). No attempt was made to get past the
  challenges. From then on, files from those hosts come from the Wayback Machine
  capture of the same URL (`via = wayback`), and the capture time and the original
  server's `Last-Modified` header are recorded. GitHub (the CBO repository) is
  reached directly.
- **Databases.** The HOFD, FRD and PMD come from the links on `obr.uk/data/`. The CBO
  repository `US-CBO/eval-projections` was taken at commit `682559c`
  (17 February 2026, "Update baseline and baseline_changes data for February 2026
  baseline").
- **OBR documents.** The EFO list was built by following the "Previous forecast" links
  back from the March 2026 EFO landing page, and the FER list by following "Previous
  report" from June 2026. Monthly commentaries come from the yearly archive pages of
  `obr.uk/monthly-public-finances-briefing/`. The archived index page stops at 2022-23;
  the 2023-24 to 2025-26 year pages were found in the Wayback index and parsed the
  same way.
- **CBO documents.** The current "Major Recurring Reports" page lists Budget and
  Economic Outlooks and updates, Analyses of the President's Budget, accuracy reports
  and Monthly Budget Reviews since 2000. Pre-2000 items come from the pre-2012 site's
  "Publications by Subject" pages (categories 0, 1 and 35, captured December 2011).
  The three evaluation reports come from the repository README.
- **Main-report availability.** 11 EFO/FER main reports were never archived under
  their `/download/` link. For each, the Wayback index of PDFs on `obr.uk` and on the
  OBR's former domains (`budgetresponsibility.org.uk`,
  `budgetresponsibility.independent.gov.uk`) was searched for file names naming the
  month and year. A candidate was accepted only if it has at least 25 pages and its
  first pages carry the report title and "Month YYYY" as one phrase. Where the cover
  is an image with no text layer, the PDF's own title and creation date must match
  instead. Both URLs are kept (`via = wayback-alternate`).
- **Correction (27 September 2026).** The first version of this check accepted the
  month and the year anywhere in the first pages. For FER October 2011 it therefore
  accepted the October 2023 FER, whose imprint page cites the "Budget Responsibility
  and National Audit Act 2011". That capture is marked `invalid` in
  `inventory/sources.csv`. The October 2011 FER now comes from
  `budgetresponsibility.independent.gov.uk/wordpress/docs/Forecast-evaluation-report-2011.pdf`.
  That file has 70 pages and an image cover; its PDF title is "Forecast evaluation
  report", its author the OBR, and it was created on 10 October 2011. A second bug
  had made the `notes` column name the wrong candidate file for three EFO reports;
  the stored files were right. Both are fixed.
- **Defaults taken.**
  - D5: dates known only to the month are set to the last day of the month and
    flagged `month_only`.
  - D11: HM Treasury vintages are kept as a separate forecaster.
  - The HOFD "June 2010" row is mapped to the June Budget 2010 forecast (22 June), not
    the Pre-Budget forecast (14 June). Flag `june2010_budget_assumed`, to be checked
    against values in E2.
- **Files written:**
  - `inventory/sources.csv`, `documents.csv`, `vintage_calendar.csv`,
    `hofd_vintage_labels.csv`, `e0_fact_checks.csv`, `e0_summary.json`, each with a
    `.schema.yaml`;
  - code in `src/fvd/{http,obr_web,cbo_web,hofd,e0_inventory,e0_factcheck,schemas}.py`.

## 3. Findings

**Vintage calendar** (`inventory/vintage_calendar.csv`)

| Group | Vintages | Exact date | Month only | Unknown |
|---|---|---|---|---|
| OBR, regular (June 2010 to March 2026) | 33 | 33 | 0 | 0 |
| OBR, memo vintages | 3 | 0 | 0 | 3 |
| HM Treasury (April 1970 to March 2010) | 73 | 0 | 73 | 0 |
| CBO baselines (1982-02 to 2026-02) | 117 | 53 (45%) | 64 | 0 |

- **OBR dates.** All 33 regular OBR vintages match an EFO landing page by
  "Month YYYY". The date is the page's `<time class="date">` (e.g. March 2026 →
  3 March 2026, `raw/web/obr_uk_efo_economic-and-fiscal-outlook-march-2026.html`).
- **CBO dates.** Every CBO baseline from 1982 to 1999 is month-only. The pre-2012
  listing gives reports as "January 1999" and gives full dates only to testimony
  and statements. The current listing stamps several 2000–2006 reports with day 01
  (e.g. 2006-01-01); these are treated as month-level. Exact dates run from
  2002-08 onward, with gaps to 2006.
- **Candidate proxy dates.** 34 of the 64 month-only CBO baselines have a dated CBO
  statement or testimony on the outlook in the same month (`related_date`, e.g.
  1999-01 → 29 January 1999). It is a candidate proxy date and is not used.

**Documents** (`inventory/documents.csv`, 1,448 rows)

- OBR:
  - EFO: 34 landing pages, 690 files (34 main reports, 287 table workbooks, 369 other);
  - FER: 16 landing pages (October 2011 to June 2026, none in 2020), 69 files;
  - monthly commentary: 160 documents. 137 are dated to the month (data months
    April 2013 to early 2026, a few months missing per year). 23 from 2011-12 and
    2012-13 are labelled only "Commentary on the public sector finances release"; their
    month is to be read from the files in E7.
- CBO:
  - 130 outlooks and updates (1976–2026);
  - 73 budget analyses;
  - 192 Monthly Budget Reviews (August 1997 to August 2026; 29 month-only);
  - 10 accuracy reports;
  - 3 evaluation reports;
  - 121 testimonies on the outlook (1975–2011).
- **Main reports:** all 34 EFO and 16 FER main reports can be retrieved. 39 come
  through their own link and 11 through verified alternate captures. The alternates:
  EFO November 2010, March 2011, December 2012, March 2013, December 2013,
  December 2014, March 2015 and July 2015; the Budget and Pre-Budget forecasts of
  June 2010; FER October 2011. Details are in the `notes` column.
- The June Budget 2010 forecast was published as Annex C of the Treasury's June 2010
  Budget document (`junebudget_annexc.pdf`, 31 pages; page 1: "Budget forecast June
  2010").

**Section 5 checks** (`inventory/e0_fact_checks.csv`, 41 claims: 34 confirmed, 3 partly
confirmed, 3 discrepancies, 1 deferred). The points that change later stages:

- **HOFD**
  - The current file is `Historical_official_forecasts_database_Spring_2026.xlsx`,
    with latest vintage March 2026 (sheet VAT, row 37). The `obr.uk/data/` link slug
    still says "march-2025" (H1).
  - Label problems in column A (H11):
    - "July 1996" appears twice on £PSNB, PSNB, £PSCR, PSCR, £TME and TME. The second
      one sits between November 1996 and November 1997 and is the July 1997 Budget;
      `hofd.vintage_rows` corrects it and records `[year corrected]`.
    - Other labels carry footnote markers or typos ("December-20131",
      "March -20141", "March2026", "November 2022**").
    - Three sheets (Taxlit, R&D, SUME) store labels as Excel dates.
  - Memo rows (H8): "restated March 2019" on 16 sheets, "supplementary March 2020" on
    14, and **"restated March 2024" on 1 sheet, which the plan does not mention**.
  - 107 of 114 series sheets follow the stated layout exactly. Scotland, HSC, Taxlit,
    R&D, SUME, Outputgap and CC carry extra note rows (H2).
  - The HSC sheet's title cell reads "National insurance contributions (NICs)
    (£ billion)", which looks like a copy error in the source.
  - Sheet counts: 32 receipts, 28 spending, 41 economy (H5).
  - Receipts components first carrying values later than June 2010: CCL, ETS
    (March 2011), Licence fee (November 2010), Scottish taxes (July 2015),
    HSC (October 2021), EGL (November 2022), CBAM and vaping (March 2024) (H6).
- **FRD**
  - 33 blocks, November 2010 to March 2026. Sign: "a positive number means a
    deterioration in PSNB" (Contents, note 4) (F2, F4).
  - **Discrepancy (F5):** the plan attributes to the PMD notes a statement that the
    full decomposition runs "since March 2016". Neither file says so. The FRD Contents
    say indirect effects of Government decisions are identified explicitly "since
    March 2015", and the FRD cites Annex B of the March 2016 EFO for methodology.
- **PMD**
  - 2,593 tax-measure rows, year columns 1970-71 to 2030-31, values numeric (P2, P3).
  - 85 event labels, 62 raw tax heads (57 after case-folding) (P4, P5).
  - Extrapolated costings are marked only by cell shading, so E2 must read cell fills
    (P12).
- **CBO**
  - `projected_year_number`: 1 = the fiscal year in progress at the baseline date,
    0 = the previous year, −1 = two years back. This holds for 100% of rows (C5).
  - 120 change dates. Nine year-end change dates (2017-11, 2018-11, 2019-11,
    2020-12 to 2025-12) have no baseline of their own. Six baselines have no change
    record (C8, tested in E3).
  - **Discrepancy (C7):** the README says "For revenues, only the legislative changes
    are shown". Economic and technical revenue changes exist only for the four most
    recent change dates (2024-02 to 2026-02). Revenue attribution is therefore
    legislative-only for most of the sample.
  - 36 baselines have neither season flag. They are the summer and autumn updates
    (e.g. 2020-09 → *An Update to the Budget Outlook*, 2 September 2020) (C9).

## 4. Open questions

1. **CBO exact dates (gate failure, see section 6).** Should month-only CBO baselines
   use the same-month CBO statement or testimony date (`related_date`, available for
   34 of 64) as a proxy, stay month-only (default D5), or be excluded from
   text-based analyses? The date only matters for text leakage (section 8 of the
   plan) and for horizons in months.
2. **HOFD "June 2010".** Mapped to the June Budget forecast (22 June). This will be
   confirmed in E2 by comparing values with the Budget forecast annex. If it is the
   Pre-Budget forecast, the date moves to 14 June.
3. **Memo vintages.** The restated March 2019, supplementary March 2020 and restated
   March 2024 forecasts have no landing page with a date. Default in E1: date them
   from the matching download's `Last-Modified` header (e.g. "Restated March 2019
   forecast" on the March 2019 EFO page), flagged. The restated March 2024 row is
   not covered by D14; the same default (keep, flag, exclude from revision chains)
   is applied.
4. **Access method.** All OBR and CBO files come from the Wayback Machine, because
   both sites block scripted clients. Wayback captures can lag a revision.
   Mitigation: capture time and `Last-Modified` are recorded for every file. If
   direct copies are wanted, the three database workbooks could be downloaded once
   in a browser and their SHA-256 compared with `inventory/sources.csv`.
5. **Monthly commentary gaps.** Roughly 10 to 12 of 12 months are listed per year;
   some months are missing from the OBR's own year pages. Whether this matters
   depends on D9.

## 5. Implications for the thesis

- OBR vintages are fully dated to the day. The OBR text arm (EFO narratives, FERs)
  is complete for all 33 vintages, so the OBR side can carry the text-based
  questions.
- CBO pre-2000 vintages can only be dated to the month. For numbers-only analyses
  (E5) this changes horizons by at most a month. For text analyses the leakage rule
  (plan section 8.1) makes every document from that month unavailable until
  month-end, which is conservative.
- CBO revenue attribution is legislative-only before 2024. This removes CBO revenue
  series from the "economic vs technical" attribution analysis. CBO outlays keep all
  three categories.

## 6. Gate result

| Criterion | Measured | Result |
|---|---|---|
| Every OBR vintage in the HOFD has an EFO with an exact publication date | 33 / 33 | **pass** |
| ≥ 90% of CBO baselines have an exact publication date; the rest flagged | 53 / 117 = 45%; the other 64 flagged `month_only` | **fail** (source limitation: CBO's listings give only months before 2000 and for several 2000–2006 reports) |
| Kill: EFO report unavailable for more than 3 OBR vintages | 0 unavailable | not triggered |
