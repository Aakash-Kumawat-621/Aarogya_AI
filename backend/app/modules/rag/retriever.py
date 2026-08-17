"""
backend/app/modules/rag/retriever.py

Hybrid retriever — BioSentBERT dense search on Pinecone with BM25
keyword fallback for rare conditions.

Strategy (decided in S5):
  - Dense search first (BioSentBERT cosine similarity)
  - If top_score < settings.PINECONE_HYBRID_THRESHOLD → re-rank with BM25
  - Searches two namespaces: medical-kb (clinical) and drug-db (drug info)
"""

import logging
import time
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

# --- Singletons (loaded once at module import) ----------------------------
_nlp_model = None     # BioSentBERT sentence transformer
_pinecone_index = None  # Pinecone Index object


def _get_model():
    """Lazy-loads BioSentBERT once and caches it."""
    global _nlp_model
    if _nlp_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            logger.info("Loading BioSentBERT model…")
            _nlp_model = SentenceTransformer(
                "pritamdeka/BioBERT-mnli-snli-scinli-scitail-mednli-stsb"
            )
            logger.info("BioSentBERT loaded ✓")
        except Exception as e:
            logger.error(f"Failed to load BioSentBERT: {e}")
            raise
    return _nlp_model


def _get_index():
    """Lazy-loads the Pinecone index once and caches it."""
    global _pinecone_index
    if _pinecone_index is None:
        if not settings.PINECONE_API_KEY:
            raise RuntimeError("PINECONE_API_KEY is not set")
        try:
            from pinecone import Pinecone
            pc = Pinecone(api_key=settings.PINECONE_API_KEY)
            _pinecone_index = pc.Index(settings.PINECONE_INDEX_NAME)
            logger.info(f"Pinecone index '{settings.PINECONE_INDEX_NAME}' connected ✓")
        except Exception as e:
            logger.error(f"Failed to connect to Pinecone: {e}")
            raise
    return _pinecone_index


def _embed(text: str) -> list[float]:
    """Embeds a query string using BioSentBERT → 768-dim vector."""
    model = _get_model()
    return model.encode([text])[0].tolist()


def _bm25_rerank(query: str, matches: list[dict], top_k: int) -> list[dict]:
    """
    BM25 keyword re-ranking for rare conditions where dense score is low.
    Combines dense score (0.7) + BM25 score (0.3) and re-sorts.
    """
    try:
        from rank_bm25 import BM25Okapi
        texts = [m["metadata"].get("text", "") for m in matches]
        tokenized_corpus = [t.lower().split() for t in texts]
        bm25 = BM25Okapi(tokenized_corpus)
        tokenized_query = query.lower().split()
        bm25_scores = bm25.get_scores(tokenized_query)

        # Normalize BM25 scores to 0-1 range
        max_bm25 = max(bm25_scores) if max(bm25_scores) > 0 else 1
        for i, match in enumerate(matches):
            dense_score = match.get("score", 0.0)
            bm25_norm = bm25_scores[i] / max_bm25
            match["combined_score"] = dense_score * 0.7 + bm25_norm * 0.3

        return sorted(matches, key=lambda x: x["combined_score"], reverse=True)[:top_k]
    except ImportError:
        logger.warning("rank_bm25 not installed — skipping BM25 re-rank")
        return matches[:top_k]


def _query_namespace(
    query_vector: list[float],
    namespace: str,
    top_k: int,
) -> list[dict]:
    """Queries a single Pinecone namespace and returns raw match dicts."""
    index = _get_index()
    try:
        response = index.query(
            vector=query_vector,
            top_k=top_k,
            namespace=namespace,
            include_metadata=True,
        )
        return [
            {
                "id": m.id,
                "score": m.score,
                "metadata": m.metadata or {},
            }
            for m in response.matches
        ]
    except Exception as e:
        logger.error(f"Pinecone query failed [{namespace}]: {e}")
        return []


def retrieve(query: str, top_k: int = 5) -> dict:
    """
    Main retrieval function. Searches medical-kb and drug-db namespaces.
    Falls back to hybrid (dense + BM25) if top score < threshold.

    Args:
        query: The rich query string from query_builder.build_query()
        top_k: Number of top chunks to return per namespace

    Returns:
        {
          "medical_chunks": [{text, source, pmid, score, disease_category}, ...],
          "drug_chunks": [{text, drug_name, score}, ...],
          "retrieval_method": "dense" | "hybrid",
          "top_score": float,
          "query_embedding_time_ms": int
        }
    """
    t0 = time.time()
    query_vector = _embed(query)
    embed_ms = int((time.time() - t0) * 1000)

    # Query both namespaces
    medical_matches = _query_namespace(query_vector, "medical-kb", top_k)
    drug_matches = _query_namespace(query_vector, "drug-db", 3)

    top_score = medical_matches[0]["score"] if medical_matches else 0.0
    retrieval_method = "dense"

    # Hybrid fallback for rare conditions
    if top_score < settings.PINECONE_HYBRID_THRESHOLD and medical_matches:
        logger.info(
            f"Low dense score ({top_score:.3f}) — applying BM25 re-rank"
        )
        medical_matches = _bm25_rerank(query, medical_matches, top_k)
        retrieval_method = "hybrid"

    # Format medical chunks
    medical_chunks = [
        {
            "text": m["metadata"].get("text", ""),
            "source": m["metadata"].get("source", "unknown"),
            "pmid": m["metadata"].get("pmid", ""),
            "disease_category": m["metadata"].get("disease_category", ""),
            "year": m["metadata"].get("year", ""),
            "score": round(m.get("combined_score", m["score"]), 4),
        }
        for m in medical_matches
    ]

    # Format drug chunks
    drug_chunks = [
        {
            "text": m["metadata"].get("text", ""),
            "drug_name": m["metadata"].get("drug_name", ""),
            "score": round(m["score"], 4),
        }
        for m in drug_matches
    ]

    logger.info(
        f"Retrieved {len(medical_chunks)} medical + {len(drug_chunks)} drug chunks "
        f"via {retrieval_method} (top_score={top_score:.3f}, embed={embed_ms}ms)"
    )

    return {
        "medical_chunks": medical_chunks,
        "drug_chunks": drug_chunks,
        "retrieval_method": retrieval_method,
        "top_score": round(top_score, 4),
        "query_embedding_time_ms": embed_ms,
    }


def retrieve_for_namespace(
    query: str, namespace: str, top_k: int = 5
) -> list[dict]:
    """
    Queries a single arbitrary namespace.
    Used by doctor finder (Module 5) to search hospital-db.
    """
    query_vector = _embed(query)
    return _query_namespace(query_vector, namespace, top_k)
