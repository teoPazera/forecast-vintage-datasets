# R1 pre-registration: retrieval pilot

Written 29 September 2026, before any document text for the pilot was extracted.

The file has two parts, each registered when it is complete:

1. **Part 1** (this text, down to "Part 2") fixes the pilot cases, the post-hoc
   coverage rule, the corpus, the pool depth and the retrieval set-up.
   - It is registered with `python -m fvd.r1_pilot register` before any pilot
     document is downloaded or extracted.
2. **Part 2** fixes the series dictionary and the queries.
   - It is registered with `python -m fvd.r1_pilot register-queries` after Teo has
     written the cause texts and before any retrieval run.
   - Registering it checks that part 1 is unchanged.

Any later change is logged under "Deviations", with its reason.

## What was known when part 1 was written

- The E6 cases and their scores (`cases/cases.parquet`, selection of commit
  `c0d72ae`).
- The inventory metadata of every document: titles, dates, URLs
  (`inventory/documents.csv`).
- **No pilot document's text had been read or extracted.** Two corpus PDFs had
  been downloaded in earlier stages, for vintage and date checks: the July 2015
  EFO and the restated March 2019 forecast. Their text was not used for anything
  here.

## 1. Which target periods a post-hoc document covers

Derived from the inventory's titles and publication dates only (plan R1). Code:
`fvd.r1_pilot.coverage`; result: `pilot/post_hoc_coverage.csv`.

- **OBR forecast evaluation report** (main report only): the UK fiscal year that
  ended (31 March) most recently before publication. Example: December 2021 →
  2020-21.
- **CBO accuracy report**: the US fiscal year that ended (30 September) most
  recently before publication. Example: January 2026 → 2025.
- **CBO evaluation report**:
  - the fiscal years of the range its title names, for the series its title
    names. "Deficits and Debt From 1984 to 2023" covers deficit and debt series
    in 1984–2023.
  - A title without a range covers nothing ("An Evaluation of CBO's Past Revenue
    Projections").

Whether a report actually discusses the case's series is not checked here; R1
reports it.

## 2. Pilot cases (D17: P = 3 per source)

- **Rule** (Teo, 29 September 2026). Go through the E6 cases of each source in
  order of case rank, keeping only those covered by at least one post-hoc
  document. Take the first 3, skipping a case whose series was already taken, or
  whose series is the parent or child of a taken case's series in the same target
  period. This keeps the pilot to distinct causes.
- **Result** (`pilot/pilot_cases.csv`):

  | Source | Pilot rank | E6 rank | Trajectory | Post-hoc documents |
  |---|---|---|---|---|
  | OBR | 1 | 1 | APD 2020-21 | FER December 2021 |
  | OBR | 2 | 2 | Student loans 2022-23 | FER October 2023 |
  | OBR | 3 | 4 | Fuel duties 2020-21 | FER December 2021 |
  | CBO | 1 | 1 | Customs duties 2025 | Accuracy reports January 2026, August 2026 |
  | CBO | 2 | 2 | Other mandatory outlays 2023 | Accuracy report December 2023 |
  | CBO | 3 | 5 | Miscellaneous receipts 2023 | Accuracy report December 2023 |

- **Skipped:**
  - OBR APD 2021-22 (E6 rank 3): same series as pilot case 1.
  - CBO excise taxes 2009 (rank 3): no post-hoc document covers it.
  - CBO total mandatory outlays 2023 (rank 4): the parent of pilot case 2 in the
    same year.

## 3. Corpus (D18)

- **Window.** For each pilot case, documents published from the first vintage
  that forecast the target period (`window_start`) to the last vintage of its
  lead-time window (`window_end`), both inclusive (`pilot/pilot_cases.csv`):
  - OBR APD and fuel 2020-21: 8 July 2015 to 25 November 2020.
  - OBR student loans 2022-23: 11 March 2020 to 22 November 2023.
  - CBO customs 2025: 26 January 2015 to 17 January 2025.
  - CBO other mandatory 2023: 5 February 2013 to 12 May 2023.
  - CBO miscellaneous receipts 2023: 5 February 2013 to 25 May 2022.
- **Documents.** Every inventoried document of the forecaster in the window whose
  type is `forecast_narrative`, `in_period_commentary` or `other`, where `other`
  means the forecaster's supplementary text.
  - `forecast_tables` (spreadsheets) are not text, and their numbers are already
    parsed in E1–E3.
  - Post-hoc documents are fetched for labelling only and never enter a run
    (section 8, rule 4).
  - Result: `pilot/corpus.csv`, with 275 OBR and 198 CBO corpus documents and 5
    post-hoc documents.
- **Formats.**
  - A document that turns out to be a spreadsheet or has no text layer is recorded
    and dropped. The OBR monthly commentaries and CBO Monthly Budget Reviews are
    included (D9).
  - A document with no usable archived copy is recorded as unavailable and
    reported.
- **`available_from`.**
  - It is the publication date; for month-only dates, the last day of the month
    (section 8, rule 1; D5).
  - The retrieved file's last-modified date (server or archive header) is recorded
    too.
  - A document whose last-modified date is more than 7 days after its publication
    date is flagged `possibly_revised`. Retrieval metrics are reported with and
    without the flagged documents: a site migration can also change that header,
    so it is not used to move `available_from`.

## 4. Extraction and linking (reused by E7 and E8)

- **Extraction.**
  - PDF text is read with PyMuPDF, page by page, in reading order. HTML pages are
    read with BeautifulSoup from the main content element.
  - Passages are paragraphs (blocks), with the page, the section heading above
    them, and their kind: paragraph, box, table or footnote.
  - Quality per document: characters per page, empty pages.
- **Linking** (E8, deterministic). A series dictionary for the six pilot series is
  built from:
  - the HOFD and CBO series names;
  - the forecaster's own terms for the series in the E2 table labels and titles.

  It is not built from case outcomes (section 8, rule 6). Target periods are
  matched explicitly ("2020-21", "2020–21", "fiscal year 2025", "FY2025") and
  relatively ("this year", "next year"), the relative ones resolved against the
  publication date and marked `ambiguous`. The dictionary is fixed in part 2,
  before any run.

## 5. Queries, runs, pool and metrics

- **Queries** (fixed in part 2):
  - **Prospective:** a template from the series name, its dictionary synonyms and
    the target period only.
  - **Retrospective:** the `cause_text` Teo writes for each cause from the
    post-hoc passages (plan R1, task 3).
- **Vintages.** Each run is made at each vintage of the case's lead-time window.
  Only passages with `available_from` strictly before that vintage's publication
  date are searched, plus the forecaster's own narrative of that vintage (section
  8, rule 3).
- **Runs:**
  1. **Topical filter.** The passages linked to the series and target period,
     newest first. It uses no query, so it is reported once per vintage.
  2. **BM25**, per query type: Okapi BM25 with k1 = 1.5 and b = 0.75, on
     lowercased alphanumeric tokens.
  3. **Dense**, per query type, with `BAAI/bge-small-en-v1.5` (D16, Teo,
     29 September 2026):
     - cosine similarity;
     - the model's recommended query instruction ("Represent this sentence for
       searching relevant passages: ");
     - library and model revision recorded in part 2.
- **Output.** The top 50 per run, query and vintage are saved (`pilot/runs`).
- **Pool** (D19). The union, per case, of the top 10 of every run at every vintage.
  Each distinct passage is labelled once per case. Passages Teo finds by manual
  search are added and marked as such.
- **Labels** (`tables/qrels`):
  - `mentions_cause`: yes / partial / no;
  - `acted_on`: adjusted / stated not adjusted / not stated;
  - `cause_id`.
- **Metrics** (plan R1, task 7), per source and query type:
  - recall@5, @10 and @50 against the pool;
  - the rank of the first relevant passage;
  - the share of topical links that mention the cause;
  - the earliest lead-time vintage at which a relevant passage exists, and at which
    one is retrieved in the top 10.

  Recall is measured against a pool and is an upper bound.

## Part 2: series dictionary and queries (registered before any retrieval run)

Pending.

## Deviations

None.
