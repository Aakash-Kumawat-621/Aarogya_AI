from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── AWS ─────────────────────────────────────────────
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "us-east-1"
    AWS_ACCOUNT_ID: str = ""

    # ── Bedrock ──────────────────────────────────────────
    # Vision model (body photo analysis)
    BEDROCK_MODEL_ID: str = "amazon.nova-pro-v1:0"
    # Diagnosis model (RAG text generation)
    BEDROCK_DIAGNOSIS_MODEL_ID: str = "amazon.nova-lite-v1:0"

    # ── Pinecone ─────────────────────────────────────────
    PINECONE_API_KEY: str = ""
    PINECONE_INDEX_NAME: str = "aarogya-index"
    # BioSentBERT embedding dimensions (768 for medical-grade BERT)
    PINECONE_DIMENSION: int = 768
    # Hybrid search: fall back to BM25 when dense score < this threshold
    PINECONE_HYBRID_THRESHOLD: float = 0.65

    # ── DynamoDB ─────────────────────────────────────────
    DYNAMODB_SESSIONS_TABLE: str = "aarogya-sessions"
    DYNAMODB_PROFILES_TABLE: str = "aarogya-profiles"
    DYNAMODB_HOSPITALS_TABLE: str = "aarogya-hospitals"

    # ── S3 ───────────────────────────────────────────────
    S3_BUCKET_NAME: str = "aarogya-uploads"
    S3_MODELS_BUCKET: str = "aarogya-ml-models"

    # ── Google Places ────────────────────────────────────
    GOOGLE_PLACES_API_KEY: str = ""

    # ── App ──────────────────────────────────────────────
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    ALLOWED_ORIGIN: str = "http://localhost:3000"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def is_local(self) -> bool:
        """Returns True if using a real IAM key (starts with AKIA)."""
        return self.AWS_ACCESS_KEY_ID.startswith("AKIA")

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def boto3_kwargs(self) -> dict:
        """Returns boto3 client kwargs with explicit credentials."""
        return {
            "region_name": self.AWS_REGION,
            "aws_access_key_id": self.AWS_ACCESS_KEY_ID,
            "aws_secret_access_key": self.AWS_SECRET_ACCESS_KEY,
        }


# Singleton — import this everywhere
settings = Settings()
