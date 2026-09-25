"""Ingest PubMed lung-cancer abstracts into the hybrid vector store.

Usage: python scripts/ingest_corpus.py [query] [max_results]
Requires network. Re-run monthly; evidence_verify drops anything >5yr old.
"""

import hashlib
import sys
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.rag import ChromaStore  # noqa: E402

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def esearch(query: str, max_results: int) -> list[str]:
    import httpx

    r = httpx.get(
        f"{EUTILS}/esearch.fcgi",
        params={"db": "pubmed", "term": query, "retmax": max_results, "retmode": "json"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["esearchresult"]["idlist"]


def efetch(pmid_ids: list[str]) -> list[dict]:
    import httpx

    r = httpx.get(
        f"{EUTILS}/efetch.fcgi",
        params={"db": "pubmed", "id": ",".join(pmid_ids), "retmode": "xml"},
        timeout=60,
    )
    r.raise_for_status()
    root = ET.fromstring(r.text)
    docs = []
    for article in root.iter("PubmedArticle"):
        pmid = article.findtext(".//PMID", "")
        title_el = article.find(".//ArticleTitle")
        title = "".join(title_el.itertext()) if title_el is not None else ""
        abstract = " ".join(
            (t.text or "") for t in article.iter("AbstractText")
        )
        year_text = article.findtext(".//PubDate/Year") or article.findtext(
            ".//PubDate/MedlineDate", ""
        )
        try:
            year = int(str(year_text)[:4])
        except ValueError:
            year = datetime.now(UTC).year
        if title or abstract:
            doc_id = (
                f"pmid:{pmid}"
                if pmid
                else hashlib.sha256(title.encode()).hexdigest()[:16]
            )
            docs.append(
                {
                    "id": doc_id,
                    "text": f"{title}\n{abstract}".strip(),
                    "metadata": {"year": year, "source": "pubmed", "pmid": pmid},
                }
            )
    return docs


def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else (
        'lung cancer OR pulmonary nodule OR NSCLC AND "clinical guideline"[pt]'
    )
    max_results = int(sys.argv[2]) if len(sys.argv) > 2 else 50

    store = ChromaStore(path="data/chroma")
    ids = esearch(query, max_results)
    print(f"found {len(ids)} pmids")
    for i in range(0, len(ids), 20):
        for doc in efetch(ids[i : i + 20]):
            store.add(doc["id"], doc["text"], doc["metadata"])
            print(f"ingested {doc['id']}")
        time.sleep(0.34)  # NCBI free-tier: max 3 req/s without API key
    print("done")


if __name__ == "__main__":
    main()
