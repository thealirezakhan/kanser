import asyncio
import json

from app.pii import get_pii_guard
from app.rag import (
    Bm25Index,
    ChromaStore,
    filter_evidence,
    hybrid_search,
    rerank,
)
from app.schemas import CaseInput


def test_dense_search_finds_matching_doc(tmp_path):
    store = ChromaStore(path=str(tmp_path / "chroma"))
    store.add(
        "nccn-nsclc-2024",
        "NCCN guideline: EGFR mutant NSCLC treated with osimertinib targeted therapy",
        {"year": 2024, "source": "NCCN"},
    )
    store.add(
        "old-2015",
        "Old chemotherapy protocol for lung cancer platinum doublets",
        {"year": 2015, "source": "archive"},
    )
    hits = hybrid_search(store, "EGFR mutant targeted therapy osimertinib", k=2)
    assert hits[0]["id"] == "nccn-nsclc-2024"
    assert hits[0]["score"] > 0


def test_bm25_finds_keyword_match():
    docs = [
        "adenocarcinoma staging and resection criteria",
        "pneumonia antibiotic treatment duration",
    ]
    idx = Bm25Index(docs)
    hits = idx.search("adenocarcinoma resection", k=2)
    assert hits
    assert "adenocarcinoma" in hits[0]["text"]


def test_filter_drops_stale_evidence():
    hits = [
        {"text": "old", "metadata": {"year": 2010}},
        {"text": "new", "metadata": {"year": 2025}},
        {"text": "noyear", "metadata": {}},
    ]
    kept, dropped = filter_evidence(hits, {}, now_year=2026)
    assert [h["text"] for h in kept] == ["new", "noyear"]
    assert dropped[0]["reason"] == "stale"


def test_filter_drops_biomarker_contradiction():
    hits = [
        {
            "text": "EGFR inhibitor only for EGFR mutant patients",
            "metadata": {"year": 2025, "required_biomarker": "egfr:mutant"},
        },
        {
            "text": "general smoking cessation advice",
            "metadata": {"year": 2025},
        },
    ]
    kept, dropped = filter_evidence(hits, {"egfr": "wildtype"}, now_year=2026)
    assert [h["text"] for h in kept] == ["general smoking cessation advice"]
    assert dropped[0]["reason"] == "biomarker_contradiction"

    kept, dropped = filter_evidence(hits, {"egfr": "mutant"}, now_year=2026)
    assert len(kept) == 2


def test_rerank_with_fake_scorer_reorders():
    hits = [
        {"text": "unrelated pneumonia", "score": 0.9},
        {"text": "EGFR osimertinib targeted therapy", "score": 0.5},
    ]

    class Scorer:
        def predict(self, pairs):
            return [0.1 if "pneumonia" in p[1] else 0.95 for p in pairs]

    ranked = rerank("EGFR therapy", hits, scorer=Scorer())
    assert ranked[0]["text"].startswith("EGFR")
    assert ranked[0]["rerank_score"] > ranked[1]["rerank_score"]


def test_swarm_run_with_store_down_still_completes():
    from test_swarm import FakeLLM

    from app.swarm import run_case

    def broken_store(query: str):
        raise ConnectionError("vector store down")

    case = CaseInput(
        patient_ref="t", modalities=["ct", "notes"], clinical_notes="nodule"
    )
    final = asyncio.run(
        run_case(case, llm=FakeLLM(), guard=get_pii_guard(), rag=broken_store)
    )
    assert final["status"] == "completed"
    kinds = [e.get("type") for e in final["events"]]
    assert "evidence_unavailable" in kinds
    assert final["evidence"] == []


def test_swarm_run_with_store_returns_citations(tmp_path):
    from test_swarm import FakeLLM

    from app.rag import ChromaStore as CS
    from app.rag import hybrid_search as hs
    from app.swarm import run_case

    store = CS(path=str(tmp_path / "chroma2"))
    store.add(
        "guideline-1",
        "EGFR mutant adenocarcinoma targeted therapy osimertinib evidence",
        {"year": 2024, "source": "NCCN"},
    )
    case = CaseInput(
        patient_ref="t",
        modalities=["ct", "notes"],
        clinical_notes="spiculated nodule adenocarcinoma",
    )
    final = asyncio.run(
        run_case(
            case,
            llm=FakeLLM(),
            guard=get_pii_guard(),
            rag=lambda q: hs(store, q, k=3),
        )
    )
    assert final["status"] == "completed"
    assert final["evidence"]
    cites = [e for e in final["events"] if e.get("type") == "evidence"]
    assert cites and cites[0]["citations"]


def test_evidence_query_built_from_reports():
    from app.rag import build_query

    q = build_query(
        {"radiology": {"hypothesis": "2cm spiculated nodule", "confidence": 0.9}}
    )
    assert "spiculated nodule" in q
    assert build_query({}) == ""



    from test_swarm import FakeLLM

    out = FakeLLM().complete("role: radiology x")
    assert "hypothesis" in json.loads(out)


def test_get_rag_returns_queryable_callable(tmp_path, monkeypatch):
    import app.rag as rag_mod

    path = str(tmp_path / "chroma")
    seed = ChromaStore(path=path)
    seed.add(
        "nccn-egfr-2024",
        "NCCN: EGFR mutant NSCLC first-line osimertinib targeted therapy",
        {"year": 2024, "source": "NCCN"},
    )
    monkeypatch.setenv("CHROMA_PATH", path)
    monkeypatch.setattr(rag_mod, "_rag_singleton", None)

    rag = rag_mod.get_rag()
    assert callable(rag)
    hits = rag("EGFR mutant osimertinib")
    assert hits
    assert hits[0]["id"] == "nccn-egfr-2024"


def test_diagnose_run_uses_default_rag_and_cites(tmp_path, monkeypatch):
    import asyncio

    from app.api import _execute_run
    from app.runs import run_store
    from app.schemas import CaseInput

    path = str(tmp_path / "chroma")
    seed = ChromaStore(path=path)
    seed.add(
        "guideline-2024",
        "Spiculated lung nodule adenocarcinoma resection criteria guideline",
        {"year": 2024, "source": "NCCN"},
    )
    monkeypatch.setenv("CHROMA_PATH", path)
    import app.rag as rag_mod

    monkeypatch.setattr(rag_mod, "_rag_singleton", None)

    case = CaseInput(
        patient_ref="t",
        modalities=["ct", "notes"],
        clinical_notes="spiculated nodule",
    )
    run_store.create("phase5-run")
    asyncio.run(_execute_run("phase5-run", "case-1", case))

    snap = run_store.get("phase5-run")
    assert snap["status"] == "completed"
    evidence_events = [e for e in snap["events"] if e.get("type") == "evidence"]
    assert evidence_events, "no evidence event emitted - rag not wired"
    assert evidence_events[0]["citations"], "expected citations from seeded store"
    kinds = [e.get("type") for e in snap["events"]]
    assert "evidence_unavailable" not in kinds


def test_evidence_replaced_not_concatenated_after_verify(tmp_path):
    import asyncio

    from test_swarm import FakeLLM

    from app.pii import get_pii_guard
    from app.rag import ChromaStore, hybrid_search
    from app.schemas import CaseInput
    from app.swarm import run_case

    store = ChromaStore(path=str(tmp_path / "chroma"))
    store.add(
        "g1",
        "lung nodule spiculated resection guideline",
        {"year": 2024, "source": "NCCN"},
    )
    case = CaseInput(
        patient_ref="t", modalities=["ct", "notes"], clinical_notes="nodule"
    )
    final = asyncio.run(
        run_case(
            case,
            llm=FakeLLM(),
            guard=get_pii_guard(),
            rag=lambda q: hybrid_search(store, q, k=3),
        )
    )
    ids = [h["id"] for h in final["evidence"]]
    assert len(ids) == len(set(ids)), f"evidence duplicated: {ids}"
    assert ids == ["g1"]
