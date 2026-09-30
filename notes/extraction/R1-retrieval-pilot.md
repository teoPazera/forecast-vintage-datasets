# R1 — Retrieval pilot

Status: **in progress** (30 September 2026). Tasks 1–2 are done. The next step is Teo's (task 3 and two dictionary decisions); the retrieval runs follow. This note is completed when the gate is reported.

## 1. Question

Is retrieving the passages that explain a forecast error hard? How much harder is it when the cause is unknown (prospective query) than when it is known (retrospective query)? This is measured on 3 pilot cases per source, before full extraction (plan R1).

## 2. What I did

- **Pre-registration part 1** (`pilot/preregistration.md`, hashed in `pilot/preregistration.json`; commit 3783a84). It fixes the post-hoc coverage rule, the pilot cases, the corpus window (D18), extraction and linking, the runs, the pool depth (D19) and the metrics.
  - Pilot cases (`pilot/pilot_cases.csv`): OBR APD 2020-21, student loans 2022-23, fuel duties 2020-21; CBO customs duties 2025, other mandatory outlays 2023, miscellaneous receipts 2023.
- **Task 1, documents** (`python -m fvd.r1_documents fetch | manual-list | manual | extract`). All 478 pilot documents were retrieved (`pilot/fetch_log.csv`):
  - 418 from the source's own link (220 OBR, 198 CBO PDFs);
  - 36 archived under another URL, first pages verified;
  - 23 downloaded by Teo in a browser (`raw/manual/pilot/`, recorded `via = manual`);
  - 1 CBO publication page whose text is the report. The July 2021 *Analysis of the President's Budget* was published as page text plus a workbook; the workbook is also kept.
- **Extraction.** 69,327 passages in `text/passages/{OBR,CBO}.parquet` (34,659 OBR, 34,668 CBO), with page, heading and kind. Per-document status and quality are in `pilot/documents.csv`: 466 documents have text; the other 12 are 11 spreadsheets and 1 scanned letter.
- **Task 2, dictionary and links** (`python -m fvd.r1_link`). The dictionary is `pilot/series_dictionary.csv`. Links are in `text/links/{OBR,CBO}.parquet`, and only `in` terms link.
- **Post-hoc passages for the cause texts** (`python -m fvd.r1_link post-hoc`). `pilot/post_hoc_passages.csv` lists the passages of each case's post-hoc documents that name its series. The template is `pilot/causes.csv`.
- **Fixes made on the way:**
  - The fetch accepted an empty archive capture. The OBR April 2023 commentary was 0 bytes, and the May 2023 link was filed under the same file. `fvd.http.check_integrity` now rejects empty files; no other pilot file was empty.
  - CBO's page template puts `<main>` inside `<header>`, and the HTML cleanup deleted the text. The main content is now found first.
  - The manual-download check now also accepts a PDF whose first pages carry the title's month and year, because slide decks do not name themselves.

## 3. Findings so far

Links (passage names the series and the target period):

| Case | Links | Unambiguous | Post-hoc passages naming the series |
|---|---|---|---|
| OBR APD 2020-21 | 51 | 49 | 5 |
| OBR fuel duties 2020-21 | 82 | 78 | 3 |
| OBR student loans 2022-23 | 68 | 65 | 2 |
| CBO customs duties 2025 | 8 | 0 | 29 |
| CBO other mandatory 2023 | 10 | 1 | 1 |
| CBO miscellaneous receipts 2023 | 1 | 0 | 2 |

CBO text rarely names a category and a fiscal year in the same passage, so the CBO topical filter is thin. That is a finding about the topical baseline, not a defect.

## 4. Open questions

1. **Dictionary terms marked `proposed`** (Teo decides before part 2 is registered):
   - "tariffs" (customs duties) adds 0 links;
   - "Federal Reserve remittances" (miscellaneous receipts) adds 5, all ambiguous.

   Both name the known cause of their case, so in the prospective query they would leak it (plan section 8, rule 6). Recommendation: drop both.
2. **CBO post-hoc documents explain only the final baseline's error.** Each accuracy report compares the last baseline before the fiscal year with the actual. The CBO cases are runs of misses that start about 10 years earlier, so the cause text describes the end of the run, not necessarily its start. State this as a limit of the ground truth.
3. **Student loans 2022-23 may be a classification or accounting change, not a forecast miss.** The forecast went from £11.9bn to £0.5bn. If the FER (October 2023) says so, this is a classification break (D13) that E4 did not flag. Replacing the case would be a deviation, logged before any run.
4. **Case design**, raised by Teo on 29 September 2026; decide after the pilot's numbers:
   - E6 favours long runs. Every CBO case's run starts about 128 months ahead, and 87% of all 30 cases start more than 36 months ahead, where no text could foresee the cause.
   - 90% of cases still have at least 2 run cells within 24 months of the target's end.
   - 20 of the 30 cases are outside the episode windows, e.g. departmental underspends (RDEL, CDEL) and CBO non-defence discretionary.
   - Two options: (a) report cases by type, shock or policy break versus slow adjustment; (b) judge text only on the part of the run after the cause could be visible, e.g. the last 24–36 months. R1's metric "earliest vintage at which a relevant passage exists, versus the correction vintage" already measures the lag from visibility to adjustment.
5. **`crosswalks/pending_second_model/results.jsonl`** names the endpoint host used for the second model (D21). It is on the public repository; Teo to decide whether it should be removed.

## 5. Implications for the thesis

To be written when the runs and labels are in.

## 6. Gate result

Pending: recall@10 difference between query types per source, number of labelled passages, and number of distinct target periods among the pilot cases.

## 7. Next steps

1. **Teo:**
   - decide the two `proposed` terms: in `pilot/series_dictionary.csv`, set `status` to `in` or `out`. The code copy is `DICTIONARY` in `src/fvd/r1_link.py`, and `python -m fvd.r1_link` rewrites the CSV from it, so change both.
   - write one `cause_text` per cause in `pilot/causes.csv`, from the post-hoc passages, citing `post_hoc_passage_id`.
2. `python -m fvd.r1_link`, then `python -m fvd.r1_pilot register-queries`: registers and hashes part 2 (dictionary, causes, queries, model revision) before any run.
3. `python -m fvd.r1_runs run`: topical, BM25 and dense (`BAAI/bge-small-en-v1.5`, D16) at each lead-time vintage. Then `python -m fvd.r1_runs pool`, which writes the blind pool to `pilot/pool.csv`.
4. **Teo** labels `pilot/pool.csv` (`mentions_cause`, `acted_on`, `cause_id`), and these become the qrels.
5. Metrics (recall@5/10/50, first relevant rank, earliest relevant vintage) go to `stats/retrieval_pilot`, then this note is completed and the stage stops for Teo's review.

**Working from another machine or a remote session.** Set up with `pip install -e ".[retrieval]"`. The committed files are enough for steps 2–5: passages, links, documents and pilot files are all in the repository. The raw PDFs are not (`raw/` is gitignored), so re-extraction needs the local machine. The dense run downloads the embedding model from Hugging Face on first use.
