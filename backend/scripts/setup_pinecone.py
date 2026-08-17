"""
setup_pinecone.py
─────────────────
Creates the Aarogya AI Pinecone index with:
  - Index name  : aarogya-index
  - Dimensions  : 768  (BioSentBERT output size)
  - Metric      : cosine
  - Cloud       : aws
  - Region      : us-east-1  (Pinecone serverless free tier)

Namespaces (created by inserting a dummy vector then deleting it):
  - medical-kb    : medical knowledge base
  - drug-db       : drug information
  - hospital-db   : hospital / doctor data

Run from backend/ directory with the venv activated:
    python scripts/setup_pinecone.py
"""

import sys
import time

sys.path.insert(0, ".")
from app.config import settings

from pinecone import Pinecone, ServerlessSpec

INDEX_NAME  = settings.PINECONE_INDEX_NAME   # aarogya-index
DIMENSION   = 768
METRIC      = "cosine"
CLOUD       = "aws"
REGION      = "us-east-1"

NAMESPACES  = ["medical-kb", "drug-db", "hospital-db"]

def main():
    print("=" * 60)
    print("  Aarogya AI — Pinecone Index Setup")
    print(f"  Index   : {INDEX_NAME}")
    print(f"  Dims    : {DIMENSION}")
    print(f"  Metric  : {METRIC}")
    print(f"  Cloud   : {CLOUD} / {REGION}")
    print("=" * 60)

    pc = Pinecone(api_key=settings.PINECONE_API_KEY)

    # ── Create index if it doesn't exist ─────────────────────────────────────
    existing = [idx.name for idx in pc.list_indexes()]
    if INDEX_NAME in existing:
        print(f"\n[SKIP] Index '{INDEX_NAME}' already exists -- skipping creation.")
    else:
        print(f"\n[Pinecone] Creating serverless index: {INDEX_NAME} ...")
        pc.create_index(
            name=INDEX_NAME,
            dimension=DIMENSION,
            metric=METRIC,
            spec=ServerlessSpec(cloud=CLOUD, region=REGION),
        )

        # Wait until index is ready
        print("  [WAIT] Waiting for index to become ready ...")
        while True:
            status = pc.describe_index(INDEX_NAME).status
            if status.get("ready"):
                break
            time.sleep(2)
        print(f"  [OK] Index '{INDEX_NAME}' is ready.")

    # ── Seed namespaces ───────────────────────────────────────────────────────
    index = pc.Index(INDEX_NAME)

    print("\n[Pinecone] Initialising namespaces ...")
    # Pinecone requires at least one non-zero value in a vector
    dummy_vector = [1.0] + [0.0] * (DIMENSION - 1)

    for ns in NAMESPACES:
        # Upsert a dummy vector to create the namespace
        index.upsert(
            vectors=[{"id": f"_init_{ns}", "values": dummy_vector}],
            namespace=ns,
        )
        # Delete the dummy vector immediately (namespace stays)
        index.delete(ids=[f"_init_{ns}"], namespace=ns)
        print(f"  ✅ Namespace ready: {ns}")

    # ── Final stats ───────────────────────────────────────────────────────────
    stats = index.describe_index_stats()
    print(f"\n[Pinecone] Index stats:")
    print(f"  Total vector count : {stats.total_vector_count}")
    print(f"  Namespaces         : {list(stats.namespaces.keys()) or NAMESPACES}")

    print("\n" + "=" * 60)
    print("  ✅ Pinecone setup complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
