import json

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

# Mock patient profile for a 55-year-old male smoker with hypertension
MOCK_PATIENT_PROFILE = {
    "name": "Test Patient",
    "age": 55,
    "gender": "male",
    "smoking": "current",
    "conditions": ["hypertension"],
    "activity_level": "moderate",
}


@pytest.fixture
def mock_aws_services(mocker):
    """Mock all external AWS/NLP services so tests run without real credentials."""
    # Mock S3 upload
    mocker.patch("app.core.patient_context.upload_file", return_value="mock-s3-key.jpg")

    # Mock Textract
    mocker.patch(
        "app.core.patient_context.extract_prescription",
        return_value={
            "raw_text": "Amoxicillin 500mg",
            "medicines": [
                {"name": "Amoxicillin", "dosage": "500mg", "frequency": "TDS"}
            ],
            "doctor_name": "Dr. Smith",
            "diagnosis_text": "Infection",
            "extraction_confidence": 0.95,
        },
    )

    # Mock Bedrock vision
    mocker.patch(
        "app.core.patient_context.analyze_body_photo",
        return_value={
            "findings": [{"finding": "rash", "location": "arm", "severity": "mild"}],
            "confidence": 0.9,
            "body_part_detected": "arm",
        },
    )

    # Mock X-ray preprocessing (CLAHE)
    mocker.patch("app.core.patient_context.preprocess_xray", return_value=None)

    # Mock NLP to be deterministic
    def mock_nlp_normalize(entities):
        return entities

    mocker.patch(
        "app.core.patient_context.normalize_all", side_effect=mock_nlp_normalize
    )

    def mock_extract(text):
        if "no chest pain" in text:
            return [
                {
                    "entity": "chest pain",
                    "canonical_form": "chest pain",
                    "negated": True,
                }
            ]
        elif "chest pain" in text:
            return [
                {
                    "entity": "chest pain",
                    "canonical_form": "chest pain",
                    "negated": False,
                }
            ]
        elif "palpitations" in text:
            return [
                {
                    "entity": "palpitations",
                    "canonical_form": "palpitations",
                    "negated": False,
                }
            ]
        return []

    mocker.patch("app.core.patient_context.extract_symptoms", side_effect=mock_extract)


@pytest.mark.asyncio
async def test_text_only_input(mock_aws_services):
    """Symptoms text + patient profile → cardiac risk flags for smoker over 50."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.post(
            "/api/v1/analyze",
            data={
                "symptoms_text": "I have severe chest pain and palpitations.",
                "patient": json.dumps(MOCK_PATIENT_PROFILE),
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["context_built"] is True
    # Should flag cardiac_risk_critical due to smoking + cardiac symptom + age > 50
    assert "cardiac_risk_critical" in data["risk_flags"]
    assert "age_over_50" in data["risk_flags"]
    assert data["symptoms_extracted"] > 0


@pytest.mark.asyncio
async def test_with_xray_upload(mock_aws_services):
    """X-ray upload → xray in inputs_processed, confidence ≥ 0.5."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        files = {"xray_image": ("test_xray.jpg", b"dummy_image_data", "image/jpeg")}
        data = {
            "symptoms_text": "Coughing for 2 weeks",
            "patient": json.dumps(MOCK_PATIENT_PROFILE),
        }
        response = await ac.post("/api/v1/analyze", data=data, files=files)

    assert response.status_code == 200
    resp_data = response.json()
    assert "xray" in resp_data["inputs_processed"]
    assert resp_data["context_confidence"] >= 0.5


@pytest.mark.asyncio
async def test_negation_handling(mock_aws_services):
    """'no chest pain' → cardiac_risk_critical should NOT be triggered."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.post(
            "/api/v1/analyze",
            data={
                "symptoms_text": "no chest pain, has headache",
                "patient": json.dumps(MOCK_PATIENT_PROFILE),
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert "cardiac_risk_critical" not in data["risk_flags"]


@pytest.mark.asyncio
async def test_invalid_patient_age(mock_aws_services):
    """Negative age → Pydantic validation rejects with 422."""
    invalid_profile = MOCK_PATIENT_PROFILE.copy()
    invalid_profile["age"] = -1

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.post(
            "/api/v1/analyze",
            data={
                "symptoms_text": "fever",
                "patient": json.dumps(invalid_profile),
            },
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_no_input_returns_400(mock_aws_services):
    """No symptoms, no files → 400 Bad Request."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.post(
            "/api/v1/analyze",
            data={"patient": json.dumps(MOCK_PATIENT_PROFILE)},
        )

    assert response.status_code == 400
