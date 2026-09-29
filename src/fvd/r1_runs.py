"""R1 task 5: retrieval runs, and the pool for labelling (task 6).

    python -m fvd.r1_runs run     # pilot/runs/*.parquet
    python -m fvd.r1_runs pool    # pilot/pool.csv, blind, for labelling

Refuses to run unless both parts of pilot/preregistration.md are registered
and unchanged (queries and dictionary are fixed before any run).

At each vintage v of a case's lead-time window, only corpus passages of that
case are searched whose document has `available_from` strictly before v's
publication date, plus the forecaster's own narrative of v (plan section 8,
rules 2 and 3). Post-hoc documents are never searched (rule 4).

Runs (pilot/preregistration.md section 5), top 50 each:
- topical: passages linked to the case's series and target period
  (text/links), newest document first; no query;
- bm25: Okapi BM25 (k1 1.5, b 0.75), statistics over the searchable passages
  at v, lowercased alphanumeric tokens;
- dense: BAAI/bge-small-en-v1.5, cosine similarity, the model's query
  instruction on queries.
"""

from __future__ import annotations

import re
import sys

import numpy as np
import pandas as pd
from scipy import sparse

from .paths import TEXT
from .r1_pilot import PILOT

TOP = 50
POOL_DEPTH = 10          # D19
K1, B = 1.5, 0.75
MODEL = "BAAI/bge-small-en-v1.5"
QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "
_TOKEN = re.compile(r"[a-z0-9]+")


def tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


class BM25:
    """Term counts for every passage once; statistics per searchable subset."""

    def __init__(self, texts: list[str]):
        vocab: dict[str, int] = {}
        rows, cols, vals = [], [], []
        for i, t in enumerate(texts):
            counts: dict[int, int] = {}
            for w in tokens(t):
                j = vocab.setdefault(w, len(vocab))
                counts[j] = counts.get(j, 0) + 1
            rows += [i] * len(counts)
            cols += list(counts)
            vals += list(counts.values())
        self.vocab = vocab
        self.tf = sparse.csr_matrix((vals, (rows, cols)), shape=(len(texts), len(vocab)), dtype=np.float32)
        self.dl = np.asarray(self.tf.sum(axis=1)).ravel()

    def scores(self, query: str, mask: np.ndarray) -> np.ndarray:
        idx = np.flatnonzero(mask)
        q = [self.vocab[w] for w in dict.fromkeys(tokens(query)) if w in self.vocab]
        out = np.zeros(len(idx), dtype=np.float32)
        if not q or not len(idx):
            return out
        sub = self.tf[idx][:, q].toarray()
        n = len(idx)
        df = (sub > 0).sum(axis=0)
        idf = np.log((n - df + 0.5) / (df + 0.5) + 1.0)
        dl = self.dl[idx][:, None]
        avg = self.dl[idx].mean()
        out = (idf * sub * (K1 + 1) / (sub + K1 * (1 - B + B * dl / avg))).sum(axis=1)
        return out


def embed_passages(passages: pd.DataFrame) -> np.ndarray:
    """Normalized passage embeddings, cached by passage id in pilot/embeddings/."""
    from sentence_transformers import SentenceTransformer
    cache = PILOT / "embeddings"
    cache.mkdir(exist_ok=True)
    f_ids, f_vec = cache / "passage_ids.txt", cache / "passages.npy"
    ids = passages.passage_id.tolist()
    if f_ids.exists() and f_ids.read_text(encoding="utf-8").split("\n") == ids:
        return np.load(f_vec)
    model = SentenceTransformer(MODEL, device="cpu")
    vec = model.encode(passages.text.tolist(), batch_size=64, normalize_embeddings=True,
                       show_progress_bar=True, convert_to_numpy=True).astype(np.float32)
    np.save(f_vec, vec)
    f_ids.write_text("\n".join(ids), encoding="utf-8")
    return vec


def searchable(docs: pd.DataFrame, trajectory: str, vintage: str, pub: pd.Timestamp) -> set[str]:
    d = docs[docs.trajectories.str.split(";").apply(lambda x: trajectory in x) & (docs.role == "corpus")]
    ok = (pd.to_datetime(d.available_from) < pub) | ((d.doc_type == "forecast_narrative") & (d.vintage_id == vintage))
    return set(d[ok].doc_id)


def run() -> None:
    from .r1_pilot import verify_part2
    verify_part2()
    docs = pd.read_csv(PILOT / "documents.csv", dtype=str, keep_default_na=False)
    cases = pd.read_csv(PILOT / "pilot_cases.csv", dtype=str)
    queries = pd.read_csv(PILOT / "queries.csv", dtype=str, keep_default_na=False)
    passages = pd.concat([pd.read_parquet(f) for f in sorted((TEXT / "passages").glob("*.parquet"))])
    passages = passages[passages.doc_id.isin(docs[docs.role == "corpus"].doc_id)].reset_index(drop=True)
    links = pd.concat([pd.read_parquet(f) for f in sorted((TEXT / "links").glob("*.parquet"))])
    vint = pd.concat([pd.read_parquet(f) for f in sorted((PILOT.parent / "tables" / "vintages").glob("*.parquet"))])
    vpub = dict(zip(vint.vintage_id, pd.to_datetime(vint.publication_date)))
    dpub = dict(zip(docs.doc_id, pd.to_datetime(docs.publication_date)))
    passages["doc_date"] = passages.doc_id.map(dpub)
    passages["order"] = passages.passage_id.str.rsplit("_p", n=1).str[1].astype(int)

    bm = BM25(passages.text.tolist())
    vec = embed_passages(passages[["passage_id", "text"]])
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(MODEL, device="cpu")
    qvec = dict(zip(queries.query_id, model.encode([QUERY_INSTRUCTION + t for t in queries.text],
                                                   normalize_embeddings=True, convert_to_numpy=True)))
    out = []
    for c in cases.itertuples():
        lk = set(links[(links.series_id == c.series_id) & (links.target_period == c.target_period)].passage_id)
        qs = queries[queries.trajectory_id == c.trajectory_id]
        for v in c.lead_time_vintages.split(";"):
            docs_ok = searchable(docs, c.trajectory_id, v, vpub[v])
            mask = passages.doc_id.isin(docs_ok).to_numpy()
            base = {"trajectory_id": c.trajectory_id, "vintage_id": v, "n_searchable": int(mask.sum())}
            top = (passages[mask & passages.passage_id.isin(lk).to_numpy()]
                   .sort_values(["doc_date", "doc_id", "order"], ascending=[False, True, True]).head(TOP))
            out += [{**base, "run": "topical", "query_id": "", "query_type": "", "rank": i + 1,
                     "passage_id": p, "score": np.nan} for i, p in enumerate(top.passage_id)]
            idx = np.flatnonzero(mask)
            for q in qs.itertuples():
                for name, sc in (("bm25", bm.scores(q.text, mask)), ("dense", vec[idx] @ qvec[q.query_id])):
                    order = np.argsort(-sc, kind="stable")[:TOP]
                    out += [{**base, "run": name, "query_id": q.query_id, "query_type": q.query_type,
                             "rank": r + 1, "passage_id": passages.passage_id.iloc[idx[j]], "score": float(sc[j])}
                            for r, j in enumerate(order) if sc[j] > 0 or name == "dense"]
    runs = pd.DataFrame(out)
    (PILOT / "runs").mkdir(exist_ok=True)
    for name, g in runs.groupby("run"):
        g.to_parquet(PILOT / "runs" / f"{name}.parquet", index=False)
    print(runs.groupby(["trajectory_id", "run", "query_type"]).size().to_string())


def pool() -> None:
    """The union per case of the top POOL_DEPTH of every run at every vintage;
    each passage once per case, in random order and without run or rank, so
    labels are blind to which run found it."""
    runs = pd.concat([pd.read_parquet(f) for f in sorted((PILOT / "runs").glob("*.parquet"))])
    top = runs[runs["rank"] <= POOL_DEPTH][["trajectory_id", "passage_id"]].drop_duplicates()
    passages = pd.concat([pd.read_parquet(f) for f in sorted((TEXT / "passages").glob("*.parquet"))])
    docs = pd.read_csv(PILOT / "documents.csv", dtype=str, keep_default_na=False)
    p = (top.merge(passages, on="passage_id").merge(docs[["doc_id", "title", "publication_date"]], on="doc_id")
         .sample(frac=1, random_state=20260929))
    p = p[["trajectory_id", "passage_id", "title", "publication_date", "page", "section_path", "text"]]
    p = p.assign(mentions_cause="", acted_on="", cause_id="", comment="")
    p.to_csv(PILOT / "pool.csv", index=False)
    print(p.groupby("trajectory_id").size().to_string())


if __name__ == "__main__":
    {"run": run, "pool": pool}[sys.argv[1]]()
