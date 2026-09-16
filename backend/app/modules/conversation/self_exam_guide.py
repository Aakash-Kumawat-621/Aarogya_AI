"""
backend/app/modules/conversation/self_exam_guide.py

Static library of step-by-step self-examination protocols that the AI can
assign to patients during a multi-turn diagnostic session.

All exams are doable with just a smartphone and hands — no equipment required
(thermometer is optional). Each exam record includes:
  - id: unique key used in API responses
  - title: short display name
  - why_useful: which conditions this helps differentiate
  - steps: ordered list of patient instructions
  - input_type: "number" | "choice" | "text"
  - unit: display unit (e.g. "bpm")
  - choices: list of options (for input_type="choice")
  - normal_range: string describing normal values
  - differentiates: list of condition pairs this exam helps separate
"""

from typing import Optional

# ── Self-exam library ──────────────────────────────────────────────────────────

SELF_EXAM_LIBRARY: dict[str, dict] = {

    "pulse_rate": {
        "id": "pulse_rate",
        "title": "Check Your Resting Pulse (Heart Rate)",
        "why_useful": (
            "Heart rate separates cardiac emergencies (ACS: usually >100 bpm with irregularity) "
            "from anxiety/panic attacks (>100 bpm but regular) and normal presentations."
        ),
        "steps": [
            "Sit or lie down quietly for at least 2 minutes.",
            "Hold your right hand palm-up.",
            "Place the index and middle fingers of your left hand on the inside of your right wrist, "
            "just below the base of the thumb.",
            "Press gently until you feel a steady beat.",
            "Count the number of beats you feel in 30 seconds.",
            "Multiply that number by 2 — this is your heart rate in beats per minute (bpm).",
            "Also note: is the rhythm steady (regular) or irregular/skipping?",
        ],
        "input_type": "number",
        "unit": "bpm",
        "min_value": 20,
        "max_value": 300,
        "normal_range": "60–100 bpm (resting adult)",
        "differentiates": ["ACS vs Panic Attack", "Tachycardia vs Bradycardia"],
    },

    "breathing_rate": {
        "id": "breathing_rate",
        "title": "Count Your Breathing Rate",
        "why_useful": (
            "Breathing rate >20/min suggests respiratory distress (pneumonia, asthma attack, PE). "
            "Normal rate with chest pain points more toward cardiac or musculoskeletal causes."
        ),
        "steps": [
            "Sit or lie still and try to breathe normally (don't consciously control it).",
            "Place one hand on your chest.",
            "Count each time your chest rises (= 1 breath) for 60 full seconds.",
            "Record the total count — this is your breathing rate.",
        ],
        "input_type": "number",
        "unit": "breaths/min",
        "min_value": 1,
        "max_value": 60,
        "normal_range": "12–20 breaths/min (adult at rest)",
        "differentiates": ["Pneumonia vs Cardiac", "Asthma vs Anxiety", "PE vs Musculoskeletal"],
    },

    "pain_scale": {
        "id": "pain_scale",
        "title": "Rate Your Pain (1–10)",
        "why_useful": (
            "Pain intensity helps prioritize urgency. Scores ≥7 with cardiac symptoms → EMERGENCY. "
            "Helps differentiate severe acute events from chronic/moderate conditions."
        ),
        "steps": [
            "Think about your pain right now.",
            "On a scale of 0 to 10:",
            "  0 = No pain at all",
            "  1–3 = Mild pain, barely noticeable",
            "  4–6 = Moderate pain, affects daily activities",
            "  7–9 = Severe pain, very difficult to ignore",
            "  10 = Worst pain imaginable",
            "Enter the number that best describes your current pain.",
        ],
        "input_type": "number",
        "unit": "/ 10",
        "min_value": 0,
        "max_value": 10,
        "normal_range": "0–3 is mild; ≥7 is medically significant",
        "differentiates": ["Acute vs Chronic", "Emergency vs Urgent"],
    },

    "skin_color": {
        "id": "skin_color",
        "title": "Check Skin and Lip Color",
        "why_useful": (
            "Blue/grey lips or fingertips (cyanosis) indicate low blood oxygen — "
            "a sign of cardiac or respiratory emergency. Pale skin suggests poor circulation."
        ),
        "steps": [
            "Go to good lighting (natural light is best).",
            "Look at your lips, the skin around your mouth, and the tips of your fingers.",
            "Gently press a fingernail until it turns white, then release.",
            "Observe carefully and choose the option that best matches what you see.",
        ],
        "input_type": "choice",
        "choices": [
            "Normal pink/healthy color",
            "Pale or ashy (lighter than usual)",
            "Blue or grey tinge (especially lips or fingertips)",
            "Yellowish tinge",
            "Flushed/very red",
        ],
        "unit": None,
        "normal_range": "Normal pink/healthy color",
        "differentiates": ["Cardiac Emergency vs Non-Cardiac", "Liver Disease vs Anemia", "Cyanosis"],
    },

    "capillary_refill": {
        "id": "capillary_refill",
        "title": "Capillary Refill Time (Circulation Check)",
        "why_useful": (
            "Slow refill (>2 seconds) indicates poor peripheral circulation, "
            "suggesting shock, severe dehydration, or cardiac compromise."
        ),
        "steps": [
            "Hold your hand at heart level.",
            "Press firmly on the tip of your index fingernail for 5 seconds until it turns white.",
            "Release the pressure and watch the fingertip.",
            "Count how many seconds it takes for the pink color to return.",
            "Enter the number of seconds.",
        ],
        "input_type": "number",
        "unit": "seconds",
        "min_value": 0,
        "max_value": 30,
        "normal_range": "<2 seconds is normal; >2 seconds may indicate poor circulation",
        "differentiates": ["Shock vs Normal", "Dehydration vs Cardiac"],
    },

    "grip_strength": {
        "id": "grip_strength",
        "title": "Compare Grip Strength (Both Hands)",
        "why_useful": (
            "Unilateral weakness is a key stroke indicator. "
            "Equal weakness on both sides may suggest metabolic or systemic cause."
        ),
        "steps": [
            "Make a tight fist with your RIGHT hand and hold for 5 seconds. Note how easy it feels.",
            "Make a tight fist with your LEFT hand and hold for 5 seconds.",
            "Compare the strength of both hands.",
        ],
        "input_type": "choice",
        "choices": [
            "Both hands feel equally strong",
            "Right hand feels noticeably weaker",
            "Left hand feels noticeably weaker",
            "Both hands feel weak",
        ],
        "unit": None,
        "normal_range": "Both hands equally strong",
        "differentiates": ["Stroke vs TIA vs Non-Neurological", "Unilateral vs Bilateral weakness"],
    },

    "facial_symmetry": {
        "id": "facial_symmetry",
        "title": "FAST Facial Symmetry Test (Stroke Screen)",
        "why_useful": (
            "Facial droop is one of the FAST stroke signs. "
            "Any asymmetry with sudden onset → EMERGENCY."
        ),
        "steps": [
            "Stand in front of a mirror (or use your phone's front camera).",
            "Smile as widely as you can.",
            "Look at both sides of your mouth.",
            "Now raise both eyebrows as high as you can.",
            "Observe if one side of your face droops or moves differently.",
        ],
        "input_type": "choice",
        "choices": [
            "Face looks symmetric — both sides move equally",
            "One side of my mouth droops when I smile",
            "One eyebrow doesn't raise as high as the other",
            "Both face and eyebrows seem droopy",
        ],
        "unit": None,
        "normal_range": "Symmetric movement on both sides",
        "differentiates": ["Stroke vs Bell's Palsy vs Non-Neurological"],
    },

    "skin_turgor": {
        "id": "skin_turgor",
        "title": "Skin Turgor (Dehydration Check)",
        "why_useful": (
            "Poor skin turgor (skin stays 'tented') indicates significant dehydration "
            "which can cause dizziness, fainting, and electrolyte emergencies."
        ),
        "steps": [
            "Using your thumb and index finger, gently pinch the skin on the back of your hand.",
            "Hold the pinch for 2 seconds.",
            "Release and watch how quickly the skin returns to normal.",
        ],
        "input_type": "choice",
        "choices": [
            "Skin snaps back immediately (<1 second)",
            "Skin returns slowly (1–2 seconds)",
            "Skin stays tented or takes >2 seconds to return",
        ],
        "unit": None,
        "normal_range": "Snaps back immediately",
        "differentiates": ["Dehydration vs Normal", "Severe vs Mild dehydration"],
    },

    "urine_color": {
        "id": "urine_color",
        "title": "Urine Color Check",
        "why_useful": (
            "Urine color indicates hydration status and can reveal kidney problems "
            "(dark/brown urine) or blood in urine (pink/red). "
            "Critical for UTI, kidney stones, liver disease differentiation."
        ),
        "steps": [
            "Next time you urinate, look at the color carefully in good lighting.",
            "Choose the best matching color from the options below.",
        ],
        "input_type": "choice",
        "choices": [
            "Clear / almost no color (very hydrated)",
            "Pale yellow (normal, well hydrated)",
            "Dark yellow / amber (mildly dehydrated)",
            "Orange or brown (concerning, possibly liver/kidney issue)",
            "Pink, red, or bloody (urgent — possible bleeding)",
            "Cloudy or milky (possible infection)",
        ],
        "unit": None,
        "normal_range": "Pale to medium yellow",
        "differentiates": ["UTI vs Other", "Kidney stones", "Dehydration", "Liver disease"],
    },

    "temperature": {
        "id": "temperature",
        "title": "Body Temperature (If You Have a Thermometer)",
        "why_useful": (
            "Fever confirms infection/inflammation. "
            "High fever (>103°F / 39.4°C) with other symptoms → URGENT or EMERGENCY."
        ),
        "steps": [
            "This exam is OPTIONAL — only do it if you have a thermometer at home.",
            "Place the thermometer under your tongue for 30 seconds (oral) or "
            "hold it in your armpit for 1 minute.",
            "Read and record the temperature.",
            "If you do not have a thermometer, select 'No thermometer available'.",
        ],
        "input_type": "choice",
        "choices": [
            "No thermometer available",
            "Below 98°F / 37°C (low)",
            "98–99.5°F / 37–37.5°C (normal)",
            "99.5–101°F / 37.5–38.3°C (low-grade fever)",
            "101–103°F / 38.3–39.4°C (fever)",
            "Above 103°F / 39.4°C (high fever)",
        ],
        "unit": None,
        "normal_range": "98–99.5°F / 37–37.5°C",
        "differentiates": ["Infection vs Non-Infection", "Fever severity", "Hypothermia"],
    },
}


# ── Condition → recommended self-exams mapping ──────────────────────────────

# Which self-exams help most when these conditions are in the differential
CONDITION_EXAM_MAP: dict[str, list[str]] = {
    "acute coronary syndrome": ["pulse_rate", "pain_scale", "skin_color", "capillary_refill"],
    "acs": ["pulse_rate", "pain_scale", "skin_color"],
    "angina": ["pulse_rate", "pain_scale"],
    "stroke": ["facial_symmetry", "grip_strength", "pulse_rate"],
    "tia": ["facial_symmetry", "grip_strength"],
    "panic attack": ["pulse_rate", "breathing_rate", "pain_scale"],
    "anxiety": ["pulse_rate", "breathing_rate"],
    "pneumonia": ["breathing_rate", "temperature"],
    "asthma": ["breathing_rate", "pulse_rate"],
    "copd": ["breathing_rate", "skin_color"],
    "pulmonary embolism": ["breathing_rate", "pulse_rate", "skin_color"],
    "heart failure": ["pulse_rate", "skin_color", "capillary_refill"],
    "dengue": ["temperature", "skin_color"],
    "typhoid": ["temperature", "urine_color"],
    "malaria": ["temperature", "skin_turgor"],
    "dehydration": ["skin_turgor", "urine_color"],
    "uti": ["urine_color", "temperature"],
    "kidney stones": ["pain_scale", "urine_color"],
    "appendicitis": ["pain_scale"],
    "gastroenteritis": ["skin_turgor", "urine_color"],
    "migraine": ["pain_scale"],
    "hypertension": ["pulse_rate"],
    "hypoglycemia": ["pulse_rate", "skin_color"],
}


def get_exams_for_differential(diseases: list[str]) -> list[dict]:
    """
    Given a list of differential diagnoses, return the most relevant
    self-exams (deduplicated, max 3).
    """
    exam_ids: list[str] = []
    seen: set[str] = set()

    for disease in diseases:
        key = disease.lower().strip()
        for exam_id in CONDITION_EXAM_MAP.get(key, []):
            if exam_id not in seen:
                seen.add(exam_id)
                exam_ids.append(exam_id)

    # Limit to max 3 exams to avoid overwhelming the patient
    exam_ids = exam_ids[:3]
    return [SELF_EXAM_LIBRARY[eid] for eid in exam_ids if eid in SELF_EXAM_LIBRARY]


def get_exam(exam_id: str) -> Optional[dict]:
    """Return a single self-exam by ID."""
    return SELF_EXAM_LIBRARY.get(exam_id)
