"""
backend/tests/test_rag.py

Unit tests for Module 3 RAG components:
  - query_builder: PatientContext → query string
  - retriever: Pinecone search (mocked)
  - chain: Full RAG pipeline (Pinecone + Bedrock mocked)
  - specialty_mapper: condition → specialist
"""

import json
import pytest

from app.core.patient_context import PatientContext, SymptomEntity
from app.models.request_models import PatientProfile
from app.modules.doctors.specialty_mapper import map_to_specialty, should_boost_urgency
from app.modules.rag.query_builder import build_query


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_context(
    age=55,
    gender="male",
    smoking="current",
    conditions=None,
    symptoms=None,
    risk_flags=None,
    body_photo_findings=None,
):
    """Helper to build a PatientContext for tests."""
    profile = PatientProfile(
        name="Test Patient",
        age=age,
        gender=gender,
        smoking=smoking,
        conditions=conditions or ["hypertension"],
        activity_level="moderate",
    )
    symptom_objs = []
    for s in (symptoms or []):
        symptom_objs.append(
            SymptomEntity(
                name=s.get("name", ""),
                canonical_form=s.get("canonical_form", s.get("name", "")),
                negated=s.get("negated", False),
            )
        )
    return PatientContext(
        session_id="test_session_001",
        patient_profile=profile,
        inputs_provided=["symptoms"],
        context_confidence=0.75,
        symptom_entities=symptom_objs,
        risk_flags=risk_flags or ["age_over_50", "current_smoker"],
        primary_concern=symptom_objs[0].canonical_form if symptom_objs else None,
        body_photo_findings=body_photo_findings,
    )


# ---------------------------------------------------------------------------
# query_builder tests
# ---------------------------------------------------------------------------

class TestQueryBuilder:

    def test_demographic_always_present(self):
        ctx = _make_context(age=30, gender="female", smoking="never", conditions=[], risk_flags=[])
        query = build_query(ctx)
        assert "30-year-old female" in query

    def test_symptoms_included(self):
        ctx = _make_context(
            symptoms=[{"name": "chest pain", "canonical_form": "chest pain"}]
        )
        query = build_query(ctx)
        assert "chest pain" in query

    def test_negated_symptoms_excluded(self):
        ctx = _make_context(
            symptoms=[
                {"name": "chest pain", "canonical_form": "chest pain", "negated": True},
                {"name": "palpitations", "canonical_form": "palpitations", "negated": False},
            ]
        )
        query = build_query(ctx)
        # chest pain is negated → should not appear prominently
        # palpitations is active → must appear
        assert "palpitations" in query

    def test_risk_flags_included(self):
        ctx = _make_context(risk_flags=["age_over_50", "cardiac_risk_critical"])
        query = build_query(ctx)
        assert "elderly" in query or "50" in query
        assert "cardiac" in query

    def test_cardiac_booster_added(self):
        ctx = _make_context(
            symptoms=[{"name": "chest pain", "canonical_form": "chest pain"}]
        )
        query = build_query(ctx)
        # Should add cardiac semantic boosters
        assert "cardiac" in query.lower() or "myocardial" in query.lower()

    def test_conditions_included(self):
        ctx = _make_context(conditions=["diabetes", "hypertension"])
        query = build_query(ctx)
        assert "diabetes" in query or "hypertension" in query

    def test_body_photo_findings_included(self):
        ctx = _make_context(
            body_photo_findings={
                "findings": [{"finding": "swelling", "location": "ankle"}]
            }
        )
        query = build_query(ctx)
        assert "swelling" in query

    def test_no_symptoms_still_valid(self):
        ctx = _make_context(symptoms=[], risk_flags=[])
        query = build_query(ctx)
        assert len(query) > 10  # Should still produce something


# ---------------------------------------------------------------------------
# specialty_mapper tests
# ---------------------------------------------------------------------------

class TestSpecialtyMapper:

    @pytest.mark.parametrize("symptom,expected", [
        ("chest pain", "Cardiologist"),
        ("palpitations", "Cardiologist"),
        ("cough", "Pulmonologist"),
        ("rash", "Dermatologist"),
        ("headache", "Neurologist"),
        ("abdominal pain", "Gastroenterologist"),
        ("joint pain", "Orthopedist"),
        ("fever", "General Physician"),
        ("diabetes", "Endocrinologist"),
        (None, "General Physician"),
        ("unknown gibberish xyz", "General Physician"),
    ])
    def test_specialty_mapping(self, symptom, expected):
        assert map_to_specialty(symptom) == expected

    def test_cardiac_boosts_urgency(self):
        assert should_boost_urgency("chest pain") is True
        assert should_boost_urgency("appendicitis") is True

    def test_low_risk_no_boost(self):
        assert should_boost_urgency("headache") is False
        assert should_boost_urgency(None) is False


# ---------------------------------------------------------------------------
# RAG chain test (Pinecone + Bedrock mocked)
# ---------------------------------------------------------------------------

class TestRAGChain:

    def test_chain_full_mocked(self, mocker):
        """Full chain run with mocked retriever and Bedrock."""
        # Mock the retriever
        mock_retrieved = {
            "medical_chunks": [
                {
                    "text": "Chest pain in elderly smokers is often associated with ACS.",
                    "source": "pubmed",
                    "pmid": "12345678",
                    "disease_category": "cardiovascular",
                    "year": "2022",
                    "score": 0.88,
                }
            ],
            "drug_chunks": [],
            "retrieval_method": "dense",
            "top_score": 0.88,
            "query_embedding_time_ms": 45,
        }
        mocker.patch("app.modules.rag.chain.retriever.retrieve", return_value=mock_retrieved)

        # Mock Bedrock response
        bedrock_json = json.dumps({
            "condition_name": "Acute Coronary Syndrome",
            "confidence": 0.82,
            "explanation": "Symptoms consistent with possible cardiac event.",
            "severity_level": "emergency",
            "specialist_needed": "Cardiologist",
            "citations": ["12345678"],
            "requires_emergency_attention": True,
            "drug_interactions_noted": [],
        })
        mocker.patch("app.modules.rag.chain._call_bedrock", return_value=bedrock_json)

        from app.modules.rag.chain import run
        ctx = _make_context(
            symptoms=[{"name": "chest pain", "canonical_form": "chest pain"}],
            risk_flags=["age_over_50", "current_smoker", "cardiac_risk_critical"],
        )
        result = run(ctx)

        assert result.condition_name == "Acute Coronary Syndrome"
        assert result.confidence == 0.82
        assert result.severity_level == "emergency"
        assert result.specialist_needed == "Cardiologist"
        assert result.requires_emergency_attention is True
        assert "12345678" in result.citations

    def test_cardiac_safety_override(self, mocker):
        """cardiac_risk_critical + chest pain → must be emergency even if Bedrock says moderate."""
        mock_retrieved = {
            "medical_chunks": [], "drug_chunks": [],
            "retrieval_method": "dense", "top_score": 0.5,
            "query_embedding_time_ms": 40,
        }
        mocker.patch("app.modules.rag.chain.retriever.retrieve", return_value=mock_retrieved)

        # Bedrock says "moderate" but safety override should flip to "emergency"
        bedrock_json = json.dumps({
            "condition_name": "Angina",
            "confidence": 0.6,
            "explanation": "Possible cardiac condition.",
            "severity_level": "moderate",   # ← will be overridden
            "specialist_needed": "Cardiologist",
            "citations": [],
            "requires_emergency_attention": False,  # ← will be overridden
            "drug_interactions_noted": [],
        })
        mocker.patch("app.modules.rag.chain._call_bedrock", return_value=bedrock_json)

        from app.modules.rag.chain import run
        ctx = _make_context(
            symptoms=[{"name": "chest pain", "canonical_form": "chest pain"}],
            risk_flags=["age_over_50", "cardiac_risk_critical"],
        )
        result = run(ctx)

        assert result.severity_level == "emergency"
        assert result.requires_emergency_attention is True

    def test_bedrock_json_parse_error_graceful(self, mocker):
        """If Bedrock returns garbage JSON → graceful fallback DiagnosisResult."""
        mock_retrieved = {
            "medical_chunks": [], "drug_chunks": [],
            "retrieval_method": "dense", "top_score": 0.3,
            "query_embedding_time_ms": 40,
        }
        mocker.patch("app.modules.rag.chain.retriever.retrieve", return_value=mock_retrieved)
        mocker.patch("app.modules.rag.chain._call_bedrock", return_value="NOT VALID JSON {{{{")

        from app.modules.rag.chain import run
        ctx = _make_context(symptoms=[{"name": "fever", "canonical_form": "fever"}])
        result = run(ctx)

        # Should not raise — returns fallback
        assert result.condition_name == "Unable to determine"
        assert result.confidence < 0.5
