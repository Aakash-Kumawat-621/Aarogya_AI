"""
backend/scripts/index_knowledge_base.py

Production knowledge base indexer for Aarogya AI.
Run this script once locally to populate Pinecone, then set up
AWS EventBridge to trigger it weekly for fresh PubMed data.

Usage:
  cd backend
  python scripts/index_knowledge_base.py --source all
  python scripts/index_knowledge_base.py --source pubmed
  python scripts/index_knowledge_base.py --source openfda

Requirements (run on Kaggle GPU for speed):
  pip install biopython datasets rank_bm25 sentence-transformers pinecone-client langchain requests
"""

import argparse
import json
import logging
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Generator

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY", "")
PINECONE_INDEX_NAME = os.environ.get("PINECONE_INDEX_NAME", "aarogya-index")

# ---------------------------------------------------------------------------
# Disease categories — extensible registry
# Add new entries here to expand scope without changing any other code.
# ---------------------------------------------------------------------------
DISEASE_CATEGORIES = {
    "cardiovascular": [
        '"chest pain"[MeSH]', '"cardiac arrhythmia"[MeSH]',
        '"heart failure"[MeSH]', '"hypertension"[MeSH]', '"myocardial infarction"[MeSH]',
    ],
    "respiratory": [
        '"pneumonia"[MeSH]', '"asthma"[MeSH]',
        '"pulmonary disease, chronic obstructive"[MeSH]', '"tuberculosis"[MeSH]',
        '"COVID-19"[MeSH]',
    ],
    "gastrointestinal": [
        '"abdominal pain"[MeSH]', '"appendicitis"[MeSH]',
        '"gastritis"[MeSH]', '"irritable bowel syndrome"[MeSH]',
    ],
    "musculoskeletal": [
        '"fractures, bone"[MeSH]', '"sprains and strains"[MeSH]',
        '"joint diseases"[MeSH]', '"back pain"[MeSH]',
    ],
    "dermatological": [
        '"skin diseases"[MeSH]', '"wound infection"[MeSH]', '"burns"[MeSH]',
    ],
    "neurological": [
        '"headache"[MeSH]', '"migraine disorders"[MeSH]',
        '"dizziness"[MeSH]', '"seizures"[MeSH]',
    ],
    "infectious": [
        '"dengue"[MeSH]', '"malaria"[MeSH]',
        '"typhoid fever"[MeSH]', '"leptospirosis"[MeSH]',
    ],
    "endocrine": [
        '"diabetes mellitus, type 2"[MeSH]', '"thyroid diseases"[MeSH]',
        '"hypoglycemia"[MeSH]',
    ],
}

PUBMED_FILTERS = "2018:2024[dp] AND English[la] AND humans[mh] AND hasabstract[text]"
PUBMED_TARGET_PER_CATEGORY = 625   # 625 × 8 categories ≈ 5000 abstracts total
MIN_ABSTRACT_WORDS = 150
CHUNK_SIZE_MEDICAL = 512           # tokens
CHUNK_OVERLAP_MEDICAL = 50
CHUNK_SIZE_DRUG = 256
OPENFDA_DRUG_LIMIT = 1000
BATCH_SIZE = 100                   # Pinecone upsert batch size


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def _chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Simple word-level chunker (approximates token size at ~0.75 words/token)."""
    words = text.split()
    approx_words = int(chunk_size * 0.75)
    approx_overlap = int(overlap * 0.75)
    chunks = []
    start = 0
    while start < len(words):
        end = min(start + approx_words, len(words))
        chunks.append(" ".join(words[start:end]))
        start += approx_words - approx_overlap
        if start >= len(words):
            break
    return [c for c in chunks if len(c.split()) >= 30]  # min 30 words


# ---------------------------------------------------------------------------
# PubMed data collection
# ---------------------------------------------------------------------------

def fetch_pubmed_chunks() -> Generator[dict, None, None]:
    """Fetches PubMed abstracts and yields chunk dicts."""
    try:
        from Bio import Entrez
    except ImportError:
        logger.error("Install biopython: pip install biopython")
        return

    Entrez.email = "aarogya-ai@example.com"  # required by NCBI

    for category, mesh_terms in DISEASE_CATEGORIES.items():
        query = " OR ".join(mesh_terms) + " AND " + PUBMED_FILTERS
        logger.info(f"Fetching PubMed: {category} …")

        try:
            handle = Entrez.esearch(
                db="pubmed", term=query,
                retmax=PUBMED_TARGET_PER_CATEGORY, sort="relevance"
            )
            record = Entrez.read(handle)
            pmids = record["IdList"]
            logger.info(f"  Found {len(pmids)} PMIDs for {category}")

            if not pmids:
                continue

            # Fetch abstracts in batches of 100
            for i in range(0, len(pmids), 100):
                batch = pmids[i:i+100]
                fetch_handle = Entrez.efetch(
                    db="pubmed", id=",".join(batch),
                    rettype="abstract", retmode="xml"
                )
                fetch_record = Entrez.read(fetch_handle)
                time.sleep(0.34)  # NCBI rate limit: 3 req/sec

                for article in fetch_record.get("PubmedArticle", []):
                    try:
                        medline = article["MedlineCitation"]
                        pmid = str(medline["PMID"])
                        abstract_list = medline["Article"].get("Abstract", {}).get("AbstractText", [])
                        abstract = " ".join(str(a) for a in abstract_list)
                        year = str(medline["Article"]["Journal"]["JournalIssue"]["PubDate"].get("Year", "2020"))

                        # Quality filter
                        if len(abstract.split()) < MIN_ABSTRACT_WORDS:
                            continue

                        for idx, chunk_text in enumerate(_chunk_text(abstract, CHUNK_SIZE_MEDICAL, CHUNK_OVERLAP_MEDICAL)):
                            yield {
                                "id": f"pubmed_{pmid}_{idx}",
                                "text": chunk_text,
                                "source": "pubmed",
                                "pmid": pmid,
                                "disease_category": category,
                                "year": year,
                                "chunk_index": idx,
                                "namespace": "medical-kb",
                            }
                    except Exception:
                        continue
        except Exception as e:
            logger.error(f"PubMed fetch error for {category}: {e}")
            continue


# ---------------------------------------------------------------------------
# OpenFDA data collection
# ---------------------------------------------------------------------------

def fetch_openfda_chunks() -> Generator[dict, None, None]:
    """Fetches OpenFDA drug labels and yields chunk dicts."""
    import requests

    endpoints = [
        ("https://api.fda.gov/drug/label.json", "indications_and_usage", "contraindications", "adverse_reactions"),
    ]

    skip = 0
    fetched = 0
    while fetched < OPENFDA_DRUG_LIMIT:
        try:
            r = requests.get(
                "https://api.fda.gov/drug/label.json",
                params={"limit": 100, "skip": skip},
                timeout=30,
            )
            r.raise_for_status()
            results = r.json().get("results", [])
            if not results:
                break

            for item in results:
                drug_names = item.get("openfda", {}).get("brand_name", ["Unknown"])
                drug_name = drug_names[0] if drug_names else "Unknown"

                for field in ["indications_and_usage", "contraindications", "adverse_reactions", "warnings"]:
                    text_list = item.get(field, [])
                    text = " ".join(text_list)
                    if len(text.split()) < 20:
                        continue

                    for idx, chunk_text in enumerate(_chunk_text(text, CHUNK_SIZE_DRUG, 0)):
                        yield {
                            "id": f"openfda_{drug_name.replace(' ', '_')}_{field}_{idx}",
                            "text": chunk_text,
                            "source": "openfda",
                            "pmid": "",
                            "drug_name": drug_name,
                            "disease_category": "pharmacology",
                            "year": "2024",
                            "chunk_index": idx,
                            "namespace": "drug-db",
                        }
                fetched += len(results)
            skip += 100
            time.sleep(0.5)
        except Exception as e:
            logger.error(f"OpenFDA fetch error: {e}")
            break


# ---------------------------------------------------------------------------
# Pinecone upsert
# ---------------------------------------------------------------------------

def upsert_to_pinecone(chunks: list[dict], model, namespace: str):
    """Embeds chunks and upserts to Pinecone in batches of BATCH_SIZE."""
    from pinecone import Pinecone

    pc = Pinecone(api_key=PINECONE_API_KEY)
    index = pc.Index(PINECONE_INDEX_NAME)

    # Check existing IDs to enable incremental indexing
    try:
        existing = set()
        # Pinecone doesn't support list all IDs cheaply; skip check for now
    except Exception:
        existing = set()

    texts = [c["text"] for c in chunks]
    logger.info(f"Embedding {len(texts)} chunks for namespace={namespace}…")

    embeddings = model.encode(texts, batch_size=64, show_progress_bar=True)

    vectors = []
    for chunk, embedding in zip(chunks, embeddings):
        if chunk["id"] in existing:
            continue
        metadata = {k: v for k, v in chunk.items() if k not in ("id", "namespace")}
        vectors.append({"id": chunk["id"], "values": embedding.tolist(), "metadata": metadata})

    # Batch upsert
    total = 0
    for i in range(0, len(vectors), BATCH_SIZE):
        batch = vectors[i:i+BATCH_SIZE]
        index.upsert(vectors=batch, namespace=namespace)
        total += len(batch)
        logger.info(f"  Upserted {total}/{len(vectors)} to {namespace}")

    logger.info(f"✓ Indexed {total} vectors → Pinecone namespace '{namespace}'")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Aarogya AI Knowledge Base Indexer")
    parser.add_argument("--source", choices=["pubmed", "openfda", "all"], default="all")
    parser.add_argument("--dry-run", action="store_true", help="Print chunk counts without indexing")
    args = parser.parse_args()

    logger.info("Loading BioSentBERT model…")
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("pritamdeka/BioBERT-mnli-snli-scinli-scitail-mednli-stsb")
    logger.info("BioSentBERT loaded ✓")

    if args.source in ("pubmed", "all"):
        logger.info("=== Fetching PubMed chunks ===")
        pubmed_chunks = list(fetch_pubmed_chunks())
        logger.info(f"Total PubMed chunks: {len(pubmed_chunks)}")

        # Save to disk
        out_path = Path("data/medical_chunks.jsonl")
        out_path.parent.mkdir(exist_ok=True)
        with open(out_path, "w") as f:
            for chunk in pubmed_chunks:
                f.write(json.dumps(chunk) + "\n")
        logger.info(f"Saved to {out_path}")

        if not args.dry_run:
            upsert_to_pinecone(pubmed_chunks, model, "medical-kb")

    if args.source in ("openfda", "all"):
        logger.info("=== Fetching OpenFDA chunks ===")
        drug_chunks = list(fetch_openfda_chunks())
        logger.info(f"Total drug chunks: {len(drug_chunks)}")

        out_path = Path("data/drug_chunks.jsonl")
        out_path.parent.mkdir(exist_ok=True)
        with open(out_path, "w") as f:
            for chunk in drug_chunks:
                f.write(json.dumps(chunk) + "\n")
        logger.info(f"Saved to {out_path}")

        if not args.dry_run:
            upsert_to_pinecone(drug_chunks, model, "drug-db")

    logger.info("=== Indexing complete ===")


if __name__ == "__main__":
    main()
