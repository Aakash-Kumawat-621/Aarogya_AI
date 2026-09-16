"""
backend/app/modules/doctors/specialty_mapper.py

Maps conditions / symptoms to the correct medical specialist.
Handles gender overrides (UTI/OB-GYN), age overrides (pediatric/geriatric),
and emergency department routing.
"""

from typing import NamedTuple, Optional


class SpecialtyResult(NamedTuple):
    primary: str           # e.g. "Cardiologist"
    google_search_term: str  # e.g. "cardiologist heart specialist"
    emergency_dept: bool   # if True + EMERGENCY urgency → search "emergency hospital"


# ── Primary condition → specialist map ───────────────────────────────────────
# Keys: lowercase canonical condition / symptom string
# Values: (specialist, google_search_term, emergency_dept)
_CONDITION_MAP: dict[str, tuple[str, str, bool]] = {

    # ── Cardiovascular ────────────────────────────────────────────────────
    "chest pain":               ("Cardiologist",     "cardiologist heart specialist",      True),
    "heart attack":             ("Cardiologist",     "cardiologist heart specialist",      True),
    "myocardial infarction":    ("Cardiologist",     "cardiologist heart specialist",      True),
    "acute coronary syndrome":  ("Cardiologist",     "cardiologist heart specialist",      True),
    "acs":                      ("Cardiologist",     "cardiologist heart specialist",      True),
    "angina":                   ("Cardiologist",     "cardiologist heart specialist",      True),
    "palpitations":             ("Cardiologist",     "cardiologist heart specialist",      False),
    "cardiac arrhythmia":       ("Cardiologist",     "cardiologist heart specialist",      True),
    "atrial fibrillation":      ("Cardiologist",     "cardiologist heart specialist",      True),
    "heart failure":            ("Cardiologist",     "cardiologist heart specialist",      True),
    "hypertension":             ("Cardiologist",     "cardiologist hypertension specialist",False),
    "high blood pressure":      ("Cardiologist",     "cardiologist hypertension specialist",False),
    "hypotension":              ("Cardiologist",     "cardiologist heart specialist",      True),
    "shock":                    ("Cardiologist",     "emergency hospital",                 True),
    "deep vein thrombosis":     ("Cardiologist",     "vascular surgeon",                   False),
    "peripheral vascular disease": ("Cardiologist", "vascular surgeon",                   False),

    # ── Respiratory ──────────────────────────────────────────────────────
    "shortness of breath":      ("Pulmonologist",   "pulmonologist chest specialist",     False),
    "breathlessness":           ("Pulmonologist",   "pulmonologist chest specialist",     False),
    "cough":                    ("Pulmonologist",   "pulmonologist chest specialist",     False),
    "chronic cough":            ("Pulmonologist",   "pulmonologist chest specialist",     False),
    "pneumonia":                ("Pulmonologist",   "pulmonologist chest specialist",     True),
    "asthma":                   ("Pulmonologist",   "pulmonologist asthma specialist",    False),
    "copd":                     ("Pulmonologist",   "pulmonologist copd specialist",      False),
    "tuberculosis":             ("Pulmonologist",   "pulmonologist tb specialist",        True),
    "tb":                       ("Pulmonologist",   "pulmonologist tb specialist",        True),
    "pulmonary embolism":       ("Pulmonologist",   "pulmonologist chest specialist",     True),
    "pleurisy":                 ("Pulmonologist",   "pulmonologist chest specialist",     False),
    "bronchitis":               ("Pulmonologist",   "pulmonologist chest specialist",     False),
    "covid-19":                 ("Pulmonologist",   "pulmonologist covid specialist",     False),
    "covid":                    ("Pulmonologist",   "pulmonologist chest specialist",     False),
    "respiratory distress":     ("Pulmonologist",   "pulmonologist chest specialist",     True),

    # ── Gastrointestinal ─────────────────────────────────────────────────
    "abdominal pain":           ("Gastroenterologist","gastroenterologist liver specialist",False),
    "stomach pain":             ("Gastroenterologist","gastroenterologist liver specialist",False),
    "appendicitis":             ("General Surgeon",  "general surgeon appendicitis",       True),
    "gastritis":                ("Gastroenterologist","gastroenterologist liver specialist",False),
    "peptic ulcer":             ("Gastroenterologist","gastroenterologist liver specialist",False),
    "gerd":                     ("Gastroenterologist","gastroenterologist acidity specialist",False),
    "acid reflux":              ("Gastroenterologist","gastroenterologist acidity specialist",False),
    "irritable bowel syndrome": ("Gastroenterologist","gastroenterologist ibs specialist",False),
    "ibs":                      ("Gastroenterologist","gastroenterologist ibs specialist",False),
    "vomiting":                 ("Gastroenterologist","gastroenterologist liver specialist",False),
    "nausea":                   ("Gastroenterologist","gastroenterologist liver specialist",False),
    "diarrhea":                 ("Gastroenterologist","gastroenterologist liver specialist",False),
    "constipation":             ("Gastroenterologist","gastroenterologist liver specialist",False),
    "jaundice":                 ("Gastroenterologist","gastroenterologist hepatologist",   True),
    "hepatitis":                ("Gastroenterologist","gastroenterologist hepatologist",   False),
    "liver disease":            ("Gastroenterologist","gastroenterologist hepatologist",   False),
    "gallstones":               ("Gastroenterologist","gastroenterologist liver specialist",False),
    "pancreatitis":             ("Gastroenterologist","gastroenterologist liver specialist",True),
    "gastrointestinal bleed":   ("Gastroenterologist","gastroenterologist liver specialist",True),

    # ── Musculoskeletal ──────────────────────────────────────────────────
    "joint pain":               ("Orthopedist",     "orthopedic surgeon",                 False),
    "back pain":                ("Orthopedist",     "orthopedic surgeon spine specialist", False),
    "neck pain":                ("Orthopedist",     "orthopedic surgeon spine specialist", False),
    "fracture":                 ("Orthopedist",     "orthopedic surgeon",                 True),
    "sprain":                   ("Orthopedist",     "orthopedic surgeon",                 False),
    "arthritis":                ("Rheumatologist",  "rheumatologist arthritis specialist", False),
    "rheumatoid arthritis":     ("Rheumatologist",  "rheumatologist arthritis specialist", False),
    "gout":                     ("Rheumatologist",  "rheumatologist arthritis specialist", False),
    "hip pain":                 ("Orthopedist",     "orthopedic surgeon",                 False),
    "knee pain":                ("Orthopedist",     "orthopedic surgeon",                 False),
    "muscle pain":              ("Orthopedist",     "orthopedic surgeon physiotherapist",  False),
    "fibromyalgia":             ("Rheumatologist",  "rheumatologist fibromyalgia",         False),

    # ── Neurological ─────────────────────────────────────────────────────
    "headache":                 ("Neurologist",     "neurologist headache specialist",    False),
    "migraine":                 ("Neurologist",     "neurologist headache specialist",    False),
    "severe headache":          ("Neurologist",     "neurologist headache specialist",    True),
    "dizziness":                ("Neurologist",     "neurologist headache specialist",    False),
    "vertigo":                  ("Neurologist",     "ent specialist neurologist",          False),
    "seizure":                  ("Neurologist",     "neurologist epilepsy specialist",    True),
    "epilepsy":                 ("Neurologist",     "neurologist epilepsy specialist",    False),
    "stroke":                   ("Neurologist",     "neurologist stroke specialist",      True),
    "paralysis":                ("Neurologist",     "neurologist stroke specialist",      True),
    "tia":                      ("Neurologist",     "neurologist stroke specialist",      True),
    "numbness":                 ("Neurologist",     "neurologist",                        False),
    "tingling":                 ("Neurologist",     "neurologist",                        False),
    "memory loss":              ("Neurologist",     "neurologist dementia specialist",    False),
    "dementia":                 ("Neurologist",     "neurologist dementia specialist",    False),
    "parkinson":                ("Neurologist",     "neurologist parkinson specialist",   False),

    # ── Dermatological ───────────────────────────────────────────────────
    "rash":                     ("Dermatologist",   "dermatologist skin specialist",      False),
    "skin lesion":              ("Dermatologist",   "dermatologist skin specialist",      False),
    "eczema":                   ("Dermatologist",   "dermatologist skin specialist",      False),
    "psoriasis":                ("Dermatologist",   "dermatologist skin specialist",      False),
    "acne":                     ("Dermatologist",   "dermatologist skin specialist",      False),
    "urticaria":                ("Dermatologist",   "dermatologist skin specialist",      False),
    "hives":                    ("Dermatologist",   "dermatologist skin specialist",      False),
    "wound":                    ("General Physician","general physician doctor",           False),
    "burn":                     ("General Physician","emergency hospital burn center",     True),
    "abscess":                  ("General Surgeon",  "general surgeon",                    False),

    # ── Endocrine ────────────────────────────────────────────────────────
    "diabetes":                 ("Endocrinologist", "endocrinologist diabetologist",      False),
    "diabetic":                 ("Endocrinologist", "endocrinologist diabetologist",      False),
    "thyroid":                  ("Endocrinologist", "endocrinologist thyroid specialist",  False),
    "hypothyroid":              ("Endocrinologist", "endocrinologist thyroid specialist",  False),
    "hyperthyroid":             ("Endocrinologist", "endocrinologist thyroid specialist",  False),
    "hypoglycemia":             ("Endocrinologist", "endocrinologist diabetologist",      True),
    "low blood sugar":          ("Endocrinologist", "endocrinologist diabetologist",      True),
    "adrenal":                  ("Endocrinologist", "endocrinologist",                    False),
    "obesity":                  ("Endocrinologist", "endocrinologist weight management",  False),

    # ── Infectious / Tropical (India-relevant) ───────────────────────────
    "fever":                    ("General Physician","general physician doctor",           False),
    "high fever":               ("General Physician","general physician doctor",           True),
    "dengue":                   ("General Physician","general physician infectious disease",True),
    "malaria":                  ("General Physician","general physician infectious disease",True),
    "typhoid":                  ("General Physician","general physician infectious disease",False),
    "chikungunya":              ("General Physician","general physician infectious disease",False),
    "viral infection":          ("General Physician","general physician doctor",           False),
    "bacterial infection":      ("General Physician","general physician doctor",           False),
    "sepsis":                   ("General Physician","emergency hospital",                 True),

    # ── Reproductive / Urological ────────────────────────────────────────
    "uti":                      ("General Physician","general physician doctor",           False),
    "urinary tract infection":  ("General Physician","general physician doctor",           False),
    "kidney stone":             ("Urologist",        "urologist kidney specialist",         False),
    "renal colic":              ("Urologist",        "urologist kidney specialist",         True),
    "prostate":                 ("Urologist",        "urologist",                           False),
    "erectile dysfunction":     ("Urologist",        "urologist andrology",                 False),
    "preeclampsia":             ("Obstetrician",     "obstetrician gynecologist",           True),
    "pregnancy":                ("Obstetrician",     "obstetrician gynecologist",           False),
    "menstrual":                ("Gynecologist",     "gynecologist women specialist",       False),
    "pcos":                     ("Gynecologist",     "gynecologist pcos specialist",        False),
    "endometriosis":            ("Gynecologist",     "gynecologist",                        False),

    # ── Kidney ───────────────────────────────────────────────────────────
    "kidney failure":           ("Nephrologist",    "nephrologist kidney specialist",     True),
    "kidney disease":           ("Nephrologist",    "nephrologist kidney specialist",     False),
    "chronic kidney disease":   ("Nephrologist",    "nephrologist kidney specialist",     False),
    "ckd":                      ("Nephrologist",    "nephrologist kidney specialist",     False),

    # ── Mental Health ────────────────────────────────────────────────────
    "depression":               ("Psychiatrist",    "psychiatrist mental health",          False),
    "anxiety":                  ("Psychiatrist",    "psychiatrist mental health",          False),
    "panic attack":             ("Psychiatrist",    "psychiatrist mental health",          False),
    "bipolar":                  ("Psychiatrist",    "psychiatrist mental health",          False),
    "schizophrenia":            ("Psychiatrist",    "psychiatrist mental health",          False),
    "insomnia":                 ("Psychiatrist",    "psychiatrist sleep specialist",       False),
    "stress":                   ("Psychiatrist",    "psychiatrist mental health",          False),
    "suicidal":                 ("Psychiatrist",    "psychiatrist mental health emergency",True),

    # ── ENT ──────────────────────────────────────────────────────────────
    "ear pain":                 ("ENT Specialist",  "ent specialist ear nose throat",     False),
    "hearing loss":             ("ENT Specialist",  "ent specialist ear nose throat",     False),
    "sinusitis":                ("ENT Specialist",  "ent specialist ear nose throat",     False),
    "throat pain":              ("ENT Specialist",  "ent specialist ear nose throat",     False),
    "tonsillitis":              ("ENT Specialist",  "ent specialist ear nose throat",     False),
    "nose bleed":               ("ENT Specialist",  "ent specialist ear nose throat",     False),

    # ── Ophthalmology ────────────────────────────────────────────────────
    "eye pain":                 ("Ophthalmologist", "eye specialist ophthalmologist",      False),
    "vision loss":              ("Ophthalmologist", "eye specialist ophthalmologist",      True),
    "blurred vision":           ("Ophthalmologist", "eye specialist ophthalmologist",      False),
    "glaucoma":                 ("Ophthalmologist", "eye specialist ophthalmologist",      False),
    "cataract":                 ("Ophthalmologist", "eye specialist ophthalmologist",      False),
    "conjunctivitis":           ("Ophthalmologist", "eye specialist ophthalmologist",      False),

    # ── Oncology ─────────────────────────────────────────────────────────
    "cancer":                   ("Oncologist",      "oncologist cancer specialist",        True),
    "tumor":                    ("Oncologist",      "oncologist cancer specialist",        True),
    "lump":                     ("General Surgeon", "general surgeon oncologist",          False),

    # ── General / Fallback ───────────────────────────────────────────────
    "fatigue":                  ("General Physician","general physician doctor",           False),
    "weight loss":              ("General Physician","general physician doctor",           False),
    "weight gain":              ("Endocrinologist", "endocrinologist",                    False),
    "infection":                ("General Physician","general physician doctor",           False),
    "allergy":                  ("General Physician","general physician allergist",        False),
    "anemia":                   ("Hematologist",    "hematologist blood specialist",       False),
    "dehydration":              ("General Physician","general physician doctor",           False),
    "food poisoning":           ("General Physician","general physician doctor",           True),
}

# ── Gender overrides ─────────────────────────────────────────────────────────
# Applied when patient is female AND condition matches
_FEMALE_OVERRIDES: dict[str, tuple[str, str]] = {
    "uti":                  ("Gynecologist",    "gynecologist women specialist"),
    "urinary tract infection": ("Gynecologist","gynecologist women specialist"),
    "kidney stone":         ("Gynecologist",    "gynecologist urologist"),
}

# ── Age suffix overrides ─────────────────────────────────────────────────────
_PEDIATRIC_SUFFIX = "pediatric"   # appended when patient age < 18
_GERIATRIC_SUFFIX = "geriatric"   # appended when patient age >= 65

# ── Keyword fallback ─────────────────────────────────────────────────────────
_KEYWORD_MAP: list[tuple[str, str, str]] = [
    ("cardiac",    "Cardiologist",      "cardiologist heart specialist"),
    ("heart",      "Cardiologist",      "cardiologist heart specialist"),
    ("lung",       "Pulmonologist",     "pulmonologist chest specialist"),
    ("pulmonary",  "Pulmonologist",     "pulmonologist chest specialist"),
    ("breath",     "Pulmonologist",     "pulmonologist chest specialist"),
    ("stomach",    "Gastroenterologist","gastroenterologist liver specialist"),
    ("bowel",      "Gastroenterologist","gastroenterologist liver specialist"),
    ("liver",      "Gastroenterologist","gastroenterologist hepatologist"),
    ("bone",       "Orthopedist",       "orthopedic surgeon"),
    ("joint",      "Orthopedist",       "orthopedic surgeon"),
    ("skin",       "Dermatologist",     "dermatologist skin specialist"),
    ("brain",      "Neurologist",       "neurologist"),
    ("nerve",      "Neurologist",       "neurologist"),
    ("sugar",      "Endocrinologist",   "endocrinologist diabetologist"),
    ("thyroid",    "Endocrinologist",   "endocrinologist thyroid specialist"),
    ("kidney",     "Nephrologist",      "nephrologist kidney specialist"),
    ("eye",        "Ophthalmologist",   "eye specialist ophthalmologist"),
    ("ear",        "ENT Specialist",    "ent specialist ear nose throat"),
    ("throat",     "ENT Specialist",    "ent specialist ear nose throat"),
    ("mental",     "Psychiatrist",      "psychiatrist mental health"),
    ("gynec",      "Gynecologist",      "gynecologist women specialist"),
    ("uterus",     "Gynecologist",      "gynecologist women specialist"),
    ("cancer",     "Oncologist",        "oncologist cancer specialist"),
    ("tumor",      "Oncologist",        "oncologist cancer specialist"),
    ("blood",      "Hematologist",      "hematologist blood specialist"),
]

_DEFAULT = SpecialtyResult(
    primary="General Physician",
    google_search_term="general physician doctor",
    emergency_dept=False,
)


def get_specialty_result(
    condition: Optional[str],
    gender: Optional[str] = None,
    age: Optional[int] = None,
    urgency: Optional[str] = None,
) -> SpecialtyResult:
    """
    Returns a SpecialtyResult with specialist name and Google search term.
    Applies gender and age overrides.
    """
    if not condition:
        return _DEFAULT

    normalized = condition.lower().strip()

    # 1. Exact match
    entry = _CONDITION_MAP.get(normalized)

    # 2. Substring match
    if not entry:
        for key, val in _CONDITION_MAP.items():
            if key in normalized or normalized in key:
                entry = val
                break

    # 3. Keyword fallback
    if not entry:
        for keyword, specialist, search_term in _KEYWORD_MAP:
            if keyword in normalized:
                entry = (specialist, search_term, False)
                break

    if not entry:
        return _DEFAULT

    specialist, search_term, emergency = entry

    # ── Gender override ───────────────────────────────────────────────────
    if gender and gender.lower() == "female":
        override = _FEMALE_OVERRIDES.get(normalized)
        if override:
            specialist, search_term = override

    # ── Age override ─────────────────────────────────────────────────────
    if age is not None:
        if age < 18:
            search_term = f"{_PEDIATRIC_SUFFIX} {search_term}"
        elif age >= 65:
            search_term = f"{_GERIATRIC_SUFFIX} {search_term}"

    # ── Emergency routing ─────────────────────────────────────────────────
    if urgency and urgency.lower() == "emergency" and emergency:
        search_term = "emergency hospital 24 hours"

    return SpecialtyResult(
        primary=specialist,
        google_search_term=search_term,
        emergency_dept=emergency,
    )


# Backward-compatible alias
def map_to_specialty(condition: Optional[str]) -> str:
    return get_specialty_result(condition).primary


def should_boost_urgency(condition: Optional[str]) -> bool:
    if not condition:
        return False
    entry = _CONDITION_MAP.get(condition.lower().strip())
    return bool(entry and entry[2])
