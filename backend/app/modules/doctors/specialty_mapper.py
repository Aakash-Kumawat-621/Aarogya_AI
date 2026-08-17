"""
backend/app/modules/doctors/specialty_mapper.py

Maps conditions / primary symptoms to the correct medical specialist.

Design: registry pattern — add new mappings to SPECIALTY_MAP or
KEYWORD_MAP without touching any other code. Categories are extensible.
"""

from typing import Optional

# --- Primary specialist lookup by canonical condition name -----------------
# Keys are lowercase condition names / primary concern strings.
# Values are (specialty, urgency_boost) tuples.
#   urgency_boost: True means always bump urgency to at least "urgent"
SPECIALTY_MAP: dict[str, tuple[str, bool]] = {
    # Cardiovascular
    "chest pain": ("Cardiologist", True),
    "palpitations": ("Cardiologist", False),
    "shortness of breath": ("Pulmonologist", False),
    "hypertension": ("Cardiologist", False),
    "heart failure": ("Cardiologist", True),
    "myocardial infarction": ("Cardiologist", True),
    "cardiac arrhythmia": ("Cardiologist", True),
    # Respiratory
    "cough": ("Pulmonologist", False),
    "pneumonia": ("Pulmonologist", True),
    "asthma": ("Pulmonologist", False),
    "tuberculosis": ("Pulmonologist", True),
    "copd": ("Pulmonologist", False),
    # Gastrointestinal
    "abdominal pain": ("Gastroenterologist", False),
    "appendicitis": ("General Surgeon", True),
    "gastritis": ("Gastroenterologist", False),
    "irritable bowel syndrome": ("Gastroenterologist", False),
    "peptic ulcer": ("Gastroenterologist", False),
    "vomiting": ("Gastroenterologist", False),
    "diarrhea": ("Gastroenterologist", False),
    # Musculoskeletal
    "joint pain": ("Orthopedist", False),
    "back pain": ("Orthopedist", False),
    "fracture": ("Orthopedist", True),
    "sprain": ("Orthopedist", False),
    # Dermatological
    "rash": ("Dermatologist", False),
    "skin lesion": ("Dermatologist", False),
    "wound": ("General Physician", False),
    "burn": ("General Physician", True),
    # Neurological
    "headache": ("Neurologist", False),
    "migraine": ("Neurologist", False),
    "dizziness": ("Neurologist", False),
    "seizure": ("Neurologist", True),
    "stroke": ("Neurologist", True),
    # Infectious (India-relevant)
    "fever": ("General Physician", False),
    "dengue": ("General Physician", True),
    "malaria": ("General Physician", True),
    "typhoid": ("General Physician", False),
    "covid-19": ("Pulmonologist", False),
    # Endocrine
    "diabetes": ("Endocrinologist", False),
    "thyroid": ("Endocrinologist", False),
    "hypoglycemia": ("Endocrinologist", True),
    # General / fallback
    "infection": ("General Physician", False),
    "fatigue": ("General Physician", False),
    "weight loss": ("General Physician", False),
}

# Keyword-based fallback — match substrings in primary_concern
KEYWORD_MAP: list[tuple[str, str]] = [
    ("cardiac", "Cardiologist"),
    ("heart", "Cardiologist"),
    ("lung", "Pulmonologist"),
    ("pulmonary", "Pulmonologist"),
    ("breath", "Pulmonologist"),
    ("stomach", "Gastroenterologist"),
    ("bowel", "Gastroenterologist"),
    ("liver", "Gastroenterologist"),
    ("bone", "Orthopedist"),
    ("joint", "Orthopedist"),
    ("skin", "Dermatologist"),
    ("brain", "Neurologist"),
    ("nerve", "Neurologist"),
    ("sugar", "Endocrinologist"),
    ("thyroid", "Endocrinologist"),
    ("kidney", "Nephrologist"),
    ("eye", "Ophthalmologist"),
    ("ear", "ENT Specialist"),
    ("throat", "ENT Specialist"),
]

DEFAULT_SPECIALTY = "General Physician"


def map_to_specialty(primary_concern: Optional[str]) -> str:
    """
    Returns the most appropriate medical specialist for the given condition.

    Args:
        primary_concern: The primary symptom / condition string (can be None)

    Returns:
        Specialist name string, e.g. "Cardiologist", "General Physician"
    """
    if not primary_concern:
        return DEFAULT_SPECIALTY

    normalized = primary_concern.lower().strip()

    # 1. Exact match
    if normalized in SPECIALTY_MAP:
        return SPECIALTY_MAP[normalized][0]

    # 2. Substring match against specialty map keys
    for key, (specialty, _) in SPECIALTY_MAP.items():
        if key in normalized or normalized in key:
            return specialty

    # 3. Keyword fallback
    for keyword, specialty in KEYWORD_MAP:
        if keyword in normalized:
            return specialty

    return DEFAULT_SPECIALTY


def should_boost_urgency(primary_concern: Optional[str]) -> bool:
    """
    Returns True if this concern should always escalate urgency to 'urgent'.
    Used by response_builder to override mild urgency for critical conditions.
    """
    if not primary_concern:
        return False
    normalized = primary_concern.lower().strip()
    entry = SPECIALTY_MAP.get(normalized)
    if entry:
        return entry[1]
    return False
