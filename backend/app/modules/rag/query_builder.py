"""
backend/app/modules/rag/query_builder.py

Converts a PatientContext into a rich natural-language query string
for Pinecone vector search.

Design: extensible registry pattern — adding new risk factors or
context fields requires only a new entry in the mapper dictionaries.
"""

from app.core.patient_context import PatientContext


# Maps risk_flag → plain-English phrase added to the query.
# Add new entries here to extend without changing build_query().
_RISK_FLAG_PHRASES = {
    "age_over_50": "elderly patient over 50 years old",
    "current_smoker": "current smoker with tobacco history",
    "cardiac_risk_critical": "high cardiac risk",
    "age_under_5": "infant or toddler",
    "pregnant": "pregnant patient",
    "immunocompromised": "immunocompromised patient",
}

# Maps disease category keywords found in symptoms to search boosters.
_CATEGORY_BOOSTERS = {
    "chest pain": "cardiac myocardial infarction angina",
    "palpitations": "cardiac arrhythmia heart rhythm",
    "shortness of breath": "respiratory pulmonary dyspnoea",
    "fever": "infectious febrile illness",
    "rash": "dermatological skin eruption",
    "headache": "neurological cephalgia migraine",
    "abdominal pain": "gastrointestinal abdominal acute abdomen",
    "joint pain": "musculoskeletal arthralgia arthritis",
    "cough": "respiratory pulmonary airway",
    "dizziness": "neurological vertigo vestibular",
    "high blood sugar": "endocrine diabetes hyperglycemia",
}


def build_query(context: PatientContext) -> str:
    """
    Builds a rich query string from a PatientContext for Pinecone retrieval.

    Example output:
      "55-year-old male patient with chest pain palpitations.
       cardiac myocardial infarction angina cardiac arrhythmia heart rhythm.
       Risk factors: elderly patient over 50 years old, current smoker with tobacco history.
       Medical history: hypertension."

    Args:
        context: The PatientContext assembled by patient_context.py

    Returns:
        A plain-English query string optimized for medical vector search.
    """
    parts = []

    # 1. Demographic prefix (always present)
    age = context.patient_profile.age
    gender = getattr(context.patient_profile, "gender", "patient") or "patient"
    parts.append(f"{age}-year-old {gender} patient")

    # 2. Active (non-negated) symptoms
    active = [s for s in context.symptom_entities if not s.negated]
    if active:
        symptom_names = " ".join(s.canonical_form or s.name for s in active)
        parts.append(f"with {symptom_names}")

    # 3. Disease-category semantic boosters
    boosters = set()
    for symptom in active:
        name_lower = (symptom.canonical_form or symptom.name).lower()
        for keyword, booster in _CATEGORY_BOOSTERS.items():
            if keyword in name_lower:
                boosters.add(booster)
    if boosters:
        parts.append(". ".join(boosters))

    # 4. Risk flags → human-readable phrases
    flag_phrases = [
        _RISK_FLAG_PHRASES[f]
        for f in context.risk_flags
        if f in _RISK_FLAG_PHRASES
    ]
    if flag_phrases:
        parts.append(f"Risk factors: {', '.join(flag_phrases)}")

    # 5. Known medical conditions from patient profile
    conditions = getattr(context.patient_profile, "conditions", None) or []
    if conditions:
        parts.append(f"Medical history: {', '.join(conditions)}")

    # 6. Body photo findings (if present)
    if context.body_photo_findings:
        findings = context.body_photo_findings.get("findings", [])
        if findings:
            finding_text = ", ".join(
                f.get("finding", "") for f in findings if f.get("finding")
            )
            if finding_text:
                parts.append(f"Visible findings: {finding_text}")

    return ". ".join(p for p in parts if p)
