import math

from app.schemas import CaseInput

# Hash bag-of-words embedder: deterministic, no model download, good enough
# for local fixture corpora. Swap for BiomedCLIP/OpenAI-clip via same interface.
_DIM = 256


class HashEmbedder:
    def __call__(self, documents: list[str]) -> list[list[float]]:
        return [self._embed(d) for d in documents]

    @staticmethod
    def _embed(text: str) -> list[float]:
        vec = [0.0] * _DIM
        for token in text.lower().split():
            vec[hash(token) % _DIM] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=False))


class ChromaStore:
    def __init__(self, path: str = "data/chroma", embedder=None) -> None:
        import chromadb

        self._client = chromadb.PersistentClient(path=path)
        self._embedder = embedder or HashEmbedder()
        self._col = self._client.get_or_create_collection(
            "guidelines", embedding_function=self
        )
        self._docs: list[str] = []
        self._meta: list[dict] = []
        self._ids: list[str] = []
        self._load_mirror()

    def __call__(self, input: list[str]) -> list[list[float]]:
        return self._embedder(input)

    @staticmethod
    def name() -> str:
        return "hash-embedder"

    def _load_mirror(self) -> None:
        got = self._col.get()
        self._ids = got["ids"]
        self._docs = got["documents"]
        self._meta = got["metadatas"]

    def add(self, doc_id: str, text: str, metadata: dict) -> None:
        self._col.upsert(ids=[doc_id], documents=[text], metadatas=[metadata])
        self._load_mirror()

    def search_dense(self, query: str, k: int = 5) -> list[dict]:
        if not self._ids:
            return []
        res = self._col.query(query_embeddings=[self([query])[0]], n_results=min(k, len(self._ids)))
        out = []
        for i, doc, meta, dist in zip(
            res["ids"][0],
            res["documents"][0],
            res["metadatas"][0],
            res["distances"][0],
            strict=False,
        ):
            out.append(
                {"id": i, "text": doc, "metadata": meta, "score": 1.0 - float(dist)}
            )
        return out


class Bm25Index:
    def __init__(self, documents: list[str], ids: list[str] | None = None) -> None:
        from rank_bm25 import BM25Plus

        self._tokenized = [d.lower().split() for d in documents]
        self._bm25 = BM25Plus(self._tokenized) if self._tokenized else None
        self._documents = documents
        self._ids = ids or [str(i) for i in range(len(documents))]

    def search(self, query: str, k: int = 5) -> list[dict]:
        if not self._bm25:
            return []
        scores = self._bm25.get_scores(query.lower().split())
        ranked = sorted(
            range(len(scores)), key=lambda i: scores[i], reverse=True
        )[:k]
        top = max((scores[i] for i in ranked), default=0.0)
        span = abs(top) or 1.0
        return [
            {
                "id": self._ids[i],
                "text": self._documents[i],
                "score": scores[i] / span,
            }
            for i in ranked
            if scores[i] != 0
        ]


def hybrid_search(store: ChromaStore, query: str, k: int = 5) -> list[dict]:
    dense = store.search_dense(query, k=k * 2)
    bm25 = Bm25Index(store._docs, store._ids).search(query, k=k * 2)
    merged: dict[str, dict] = {}
    for hit in dense:
        merged[hit["id"]] = {**hit, "dense": hit["score"], "bm25": 0.0}
    for hit in bm25:
        entry = merged.get(hit["id"])
        if entry is None:
            idx = store._ids.index(hit["id"]) if hit["id"] in store._ids else None
            entry = {
                "id": hit["id"],
                "text": hit["text"],
                "metadata": store._meta[idx] if idx is not None else {},
                "dense": 0.0,
            }
        entry["bm25"] = hit["score"]
        merged[entry["id"]] = entry
    for entry in merged.values():
        entry["score"] = 0.5 * entry["dense"] + 0.5 * entry["bm25"]
    ranked = sorted(merged.values(), key=lambda e: e["score"], reverse=True)
    return ranked[:k]


def rerank(query: str, hits: list[dict], scorer=None) -> list[dict]:
    if scorer is None:
        try:
            from sentence_transformers import CrossEncoder

            scorer = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
        except Exception:
            return hits
    pairs = [(query, h["text"]) for h in hits]
    scores = scorer.predict(pairs)
    for h, s in zip(hits, scores, strict=False):
        h["rerank_score"] = float(s)
    return sorted(hits, key=lambda h: h["rerank_score"], reverse=True)


def filter_evidence(
    hits: list[dict], case_meta: dict[str, str], now_year: int | None = None
) -> tuple[list[dict], list[dict]]:
    """Drop stale (>5yr) and biomarker-contradicted evidence. Returns (kept, dropped)."""
    year_now = now_year or __import__("datetime").datetime.now().year
    kept, dropped = [], []
    for h in hits:
        meta = h.get("metadata", {})
        year = meta.get("year")
        if year and int(year) < year_now - 5:
            dropped.append({**h, "reason": "stale"})
            continue
        required = meta.get("required_biomarker", "")
        if required:
            _, _, value = required.partition(":")
            key = required.split(":")[0]
            if value and case_meta.get(key, "").lower() != value.lower():
                dropped.append({**h, "reason": "biomarker_contradiction"})
                continue
        kept.append(h)
    return kept, dropped


def build_query(reports: dict) -> str:
    parts = [
        str(r.get("hypothesis", "")) for r in reports.values()
    ]
    return " ".join(parts)[:1000]


def case_has_data(case: CaseInput) -> bool:
    return bool(case.modalities)


_rag_singleton = None


def get_rag():
    """Production rag callable over the persistent store. Rebuilds if CHROMA_PATH changes."""
    import os

    global _rag_singleton
    path = os.environ.get("CHROMA_PATH", "data/chroma")
    if _rag_singleton is not None and getattr(_rag_singleton, "_path", None) == path:
        return _rag_singleton

    store = ChromaStore(path=path)

    def _query(query: str) -> list[dict]:
        hits = hybrid_search(store, query, k=5)
        return rerank(query, hits) if hits else []

    _query._path = path  # type: ignore[attr-defined]
    _rag_singleton = _query
    return _query
