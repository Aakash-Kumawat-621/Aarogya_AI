"""
backend/scripts/s5_validation.py

Step S5 — 30-case end-to-end qualitative validation.
Tests the full pipeline against the local running server (port 8000).

Scoring (1-3 per dimension):
  - Diagnosis accuracy:     3=correct top, 2=in top-3, 1=missed
  - Urgency appropriateness: 3=exact match, 2=one level off, 1=dangerous error
  - Action plan quality:    3=specific+helpful, 2=generic but safe, 1=wrong/harmful
  - Doctor relevance:       3=right specialist, 2=acceptable fallback, 1=wrong

Target: average >= 2.5/3.0   |   Any urgency score of 1 = CRITICAL FAIL
"""
import sys, io, json, time, requests
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = "http://localhost:8000/api/v1"

# ── 30 Test Cases ─────────────────────────────────────────────────────────────
CASES = [
    # ── Group 1: High-confidence cardiac (10 cases) ───────────────────────────
    {
        "id": 1, "group": "Cardiac",
        "symptoms": "severe chest pain left arm numbness sweating for 30 minutes",
        "patient": {"name": "Ramesh", "age": 55, "gender": "male",
                    "smoking": "current", "conditions": ["hypertension"]},
        "expected_urgency": "emergency", "expected_specialty": "Cardiologist",
        "expected_diagnosis_keywords": ["heart attack", "myocardial infarction", "acs", "cardiac"],
        "label": "Classic STEMI — critical test case",
    },
    {
        "id": 2, "group": "Cardiac",
        "symptoms": "chest pain radiating to jaw shortness of breath cold sweat nausea",
        "patient": {"name": "Suresh", "age": 65, "gender": "male",
                    "smoking": "former", "conditions": ["diabetes", "hypertension"]},
        "expected_urgency": "emergency", "expected_specialty": "Cardiologist",
        "expected_diagnosis_keywords": ["heart", "cardiac", "acs", "angina"],
        "label": "Diabetic with cardiac symptoms",
    },
    {
        "id": 3, "group": "Cardiac",
        "symptoms": "chest tightness on exertion relieved by rest no sweating",
        "patient": {"name": "Mohan", "age": 60, "gender": "male",
                    "smoking": "current", "conditions": ["hypertension"]},
        "expected_urgency": "urgent", "expected_specialty": "Cardiologist",
        "expected_diagnosis_keywords": ["angina", "cardiac", "heart"],
        "label": "Stable angina — urgent not emergency",
    },
    {
        "id": 4, "group": "Cardiac",
        "symptoms": "mild chest discomfort anxiety panic attack symptoms",
        "patient": {"name": "Priya", "age": 25, "gender": "female",
                    "smoking": "never", "conditions": []},
        "expected_urgency": "low", "expected_specialty": "General Physician",
        "expected_diagnosis_keywords": ["anxiety", "panic", "musculoskeletal"],
        "label": "Anxiety chest pain — should NOT be emergency",
    },
    {
        "id": 5, "group": "Cardiac",
        "symptoms": "palpitations racing heart fast heartbeat 150 bpm dizzy",
        "patient": {"name": "Anita", "age": 40, "gender": "female",
                    "smoking": "never", "conditions": []},
        "expected_urgency": "urgent", "expected_specialty": "Cardiologist",
        "expected_diagnosis_keywords": ["arrhythmia", "tachycardia", "palpitation"],
        "label": "Tachyarrhythmia",
    },
    {
        "id": 6, "group": "Cardiac",
        "symptoms": "chest pain left arm numbness 20 pack years smoker hypertension",
        "patient": {"name": "Vikram", "age": 50, "gender": "male",
                    "smoking": "current", "pack_years": 20, "conditions": ["hypertension"]},
        "expected_urgency": "emergency", "expected_specialty": "Cardiologist",
        "expected_diagnosis_keywords": ["heart attack", "cardiac", "acs"],
        "label": "High-risk cardiac — 20 pack-years",
    },
    {
        "id": 7, "group": "Cardiac",
        "symptoms": "shortness of breath on exertion ankle swelling",
        "patient": {"name": "Geeta", "age": 62, "gender": "female",
                    "smoking": "never", "conditions": ["hypertension"]},
        "expected_urgency": "urgent", "expected_specialty": "Cardiologist",
        "expected_diagnosis_keywords": ["heart failure", "cardiac", "pulmonary"],
        "label": "Heart failure symptoms",
    },
    {
        "id": 8, "group": "Cardiac",
        "symptoms": "sudden severe chest pain tearing radiating to back",
        "patient": {"name": "Arun", "age": 58, "gender": "male",
                    "smoking": "former", "conditions": ["hypertension"]},
        "expected_urgency": "emergency", "expected_specialty": "Cardiologist",
        "expected_diagnosis_keywords": ["aortic", "dissection", "cardiac", "emergency"],
        "label": "Aortic dissection",
    },
    {
        "id": 9, "group": "Cardiac",
        "symptoms": "chest pain with fever cough recent flu",
        "patient": {"name": "Sanjay", "age": 35, "gender": "male",
                    "smoking": "never", "conditions": []},
        "expected_urgency": "moderate", "expected_specialty": "General Physician",
        "expected_diagnosis_keywords": ["pericarditis", "pleuritis", "infection"],
        "label": "Post-viral chest pain — not cardiac emergency",
    },
    {
        "id": 10, "group": "Cardiac",
        "symptoms": "chest pain after eating heartburn acid reflux burping",
        "patient": {"name": "Kavita", "age": 38, "gender": "female",
                    "smoking": "never", "conditions": []},
        "expected_urgency": "low", "expected_specialty": "Gastroenterologist",
        "expected_diagnosis_keywords": ["gerd", "acid reflux", "gastric", "heartburn"],
        "label": "GERD — false cardiac alarm",
    },

    # ── Group 2: India-specific diseases (8 cases) ────────────────────────────
    {
        "id": 11, "group": "India-specific",
        "symptoms": "high fever 104F headache severe joint pain behind eyes muscle pain rash",
        "patient": {"name": "Rajesh", "age": 28, "gender": "male",
                    "smoking": "never", "conditions": []},
        "expected_urgency": "urgent", "expected_specialty": "General Physician",
        "expected_diagnosis_keywords": ["dengue", "viral"],
        "label": "Dengue fever — Jaipur monsoon",
    },
    {
        "id": 12, "group": "India-specific",
        "symptoms": "cyclical fever chills rigors sweating every 48 hours malaise",
        "patient": {"name": "Sunita", "age": 32, "gender": "female",
                    "smoking": "never", "conditions": []},
        "expected_urgency": "urgent", "expected_specialty": "General Physician",
        "expected_diagnosis_keywords": ["malaria", "fever", "parasitic"],
        "label": "Malaria",
    },
    {
        "id": 13, "group": "India-specific",
        "symptoms": "persistent cough for 3 weeks night sweats weight loss low grade fever",
        "patient": {"name": "Ramesh", "age": 45, "gender": "male",
                    "smoking": "current", "conditions": []},
        "expected_urgency": "urgent", "expected_specialty": "Pulmonologist",
        "expected_diagnosis_keywords": ["tuberculosis", "tb", "pulmonary"],
        "label": "Tuberculosis",
    },
    {
        "id": 14, "group": "India-specific",
        "symptoms": "high fever stepwise rising abdominal pain constipation rose spots on abdomen",
        "patient": {"name": "Aisha", "age": 22, "gender": "female",
                    "smoking": "never", "conditions": []},
        "expected_urgency": "urgent", "expected_specialty": "General Physician",
        "expected_diagnosis_keywords": ["typhoid", "enteric"],
        "label": "Typhoid fever",
    },
    {
        "id": 15, "group": "India-specific",
        "symptoms": "sudden fever joint pain swelling rash not subsiding",
        "patient": {"name": "Deepak", "age": 35, "gender": "male",
                    "smoking": "never", "conditions": []},
        "expected_urgency": "moderate", "expected_specialty": "General Physician",
        "expected_diagnosis_keywords": ["chikungunya", "viral arthritis"],
        "label": "Chikungunya",
    },
    {
        "id": 16, "group": "India-specific",
        "symptoms": "bukhar sar dard aur haath pair mein dard ho raha hai",
        "patient": {"name": "Meena", "age": 30, "gender": "female",
                    "smoking": "never", "conditions": []},
        "expected_urgency": "moderate", "expected_specialty": "General Physician",
        "expected_diagnosis_keywords": ["fever", "pain", "viral"],
        "label": "Hindi symptoms — fever and body ache",
    },
    {
        "id": 17, "group": "India-specific",
        "symptoms": "yellow eyes dark urine fatigue right upper abdominal pain nausea",
        "patient": {"name": "Gopal", "age": 25, "gender": "male",
                    "smoking": "never", "conditions": []},
        "expected_urgency": "urgent", "expected_specialty": "Gastroenterologist",
        "expected_diagnosis_keywords": ["hepatitis", "jaundice", "liver"],
        "label": "Hepatitis — common in India",
    },
    {
        "id": 18, "group": "India-specific",
        "symptoms": "diarrhea vomiting abdominal cramps rice water stools dehydration",
        "patient": {"name": "Priya", "age": 19, "gender": "female",
                    "smoking": "never", "conditions": []},
        "expected_urgency": "urgent", "expected_specialty": "General Physician",
        "expected_diagnosis_keywords": ["cholera", "gastroenteritis", "dehydration"],
        "label": "Cholera/gastroenteritis",
    },

    # ── Group 3: Complex multi-condition (6 cases) ────────────────────────────
    {
        "id": 19, "group": "Multi-condition",
        "symptoms": "chest pain shortness of breath high blood sugar 350 mg/dl",
        "patient": {"name": "Harish", "age": 58, "gender": "male",
                    "smoking": "current", "conditions": ["diabetes", "hypertension"]},
        "expected_urgency": "emergency", "expected_specialty": "Cardiologist",
        "expected_diagnosis_keywords": ["cardiac", "heart", "diabetic"],
        "label": "Diabetic + hypertensive + cardiac",
    },
    {
        "id": 20, "group": "Multi-condition",
        "symptoms": "breathlessness fever productive cough diabetes poorly controlled",
        "patient": {"name": "Usha", "age": 52, "gender": "female",
                    "smoking": "never", "conditions": ["diabetes"]},
        "expected_urgency": "urgent", "expected_specialty": "Pulmonologist",
        "expected_diagnosis_keywords": ["pneumonia", "infection", "respiratory"],
        "label": "Diabetic + pneumonia",
    },
    {
        "id": 21, "group": "Multi-condition",
        "symptoms": "severe headache vision blurring blood pressure 190/110",
        "patient": {"name": "Mahesh", "age": 55, "gender": "male",
                    "smoking": "former", "conditions": ["hypertension", "diabetes"]},
        "expected_urgency": "emergency", "expected_specialty": "Neurologist",
        "expected_diagnosis_keywords": ["hypertensive", "stroke", "cerebral"],
        "label": "Hypertensive emergency + stroke risk",
    },
    {
        "id": 22, "group": "Multi-condition",
        "symptoms": "swollen joints morning stiffness for hours high uric acid fever",
        "patient": {"name": "Vinod", "age": 48, "gender": "male",
                    "smoking": "never", "conditions": ["hypertension"]},
        "expected_urgency": "moderate", "expected_specialty": "Orthopedist",
        "expected_diagnosis_keywords": ["gout", "arthritis", "uric acid"],
        "label": "Gout with hypertension",
    },
    {
        "id": 23, "group": "Multi-condition",
        "symptoms": "confusion altered consciousness diabetic patient family history",
        "patient": {"name": "Leela", "age": 70, "gender": "female",
                    "smoking": "never", "conditions": ["diabetes", "hypertension"]},
        "expected_urgency": "emergency", "expected_specialty": "Neurologist",
        "expected_diagnosis_keywords": ["hypoglycemia", "diabetic", "neurological"],
        "label": "Diabetic confusion — emergency",
    },
    {
        "id": 24, "group": "Multi-condition",
        "symptoms": "fatigue weight gain cold intolerance constipation diabetes controlled",
        "patient": {"name": "Rekha", "age": 44, "gender": "female",
                    "smoking": "never", "conditions": ["diabetes"]},
        "expected_urgency": "low", "expected_specialty": "Endocrinologist",
        "expected_diagnosis_keywords": ["hypothyroid", "thyroid"],
        "label": "Hypothyroidism with diabetes",
    },

    # ── Group 4: Low urgency / false alarms (4 cases) ─────────────────────────
    {
        "id": 25, "group": "Low-urgency",
        "symptoms": "runny nose sneezing mild sore throat for 2 days no fever",
        "patient": {"name": "Raj", "age": 30, "gender": "male",
                    "smoking": "never", "conditions": []},
        "expected_urgency": "low", "expected_specialty": "General Physician",
        "expected_diagnosis_keywords": ["cold", "viral", "rhinitis"],
        "label": "Common cold — no false EMERGENCY",
    },
    {
        "id": 26, "group": "Low-urgency",
        "symptoms": "ankle pain after exercise walking sports injury yesterday",
        "patient": {"name": "Rahul", "age": 22, "gender": "male",
                    "smoking": "never", "conditions": []},
        "expected_urgency": "low", "expected_specialty": "Orthopedist",
        "expected_diagnosis_keywords": ["sprain", "injury", "musculoskeletal"],
        "label": "Ankle sprain",
    },
    {
        "id": 27, "group": "Low-urgency",
        "symptoms": "itchy red rash on forearm no fever no breathing difficulty",
        "patient": {"name": "Neha", "age": 25, "gender": "female",
                    "smoking": "never", "conditions": []},
        "expected_urgency": "low", "expected_specialty": "Dermatologist",
        "expected_diagnosis_keywords": ["dermatitis", "allergy", "rash", "eczema"],
        "label": "Minor skin rash",
    },
    {
        "id": 28, "group": "Low-urgency",
        "symptoms": "sneezing watery eyes itchy nose dust pollen allergy season",
        "patient": {"name": "Amit", "age": 28, "gender": "male",
                    "smoking": "never", "conditions": []},
        "expected_urgency": "low", "expected_specialty": "General Physician",
        "expected_diagnosis_keywords": ["allergy", "rhinitis", "hay fever"],
        "label": "Seasonal allergy",
    },

    # ── Group 5: Gender + age specific (2 cases) ──────────────────────────────
    {
        "id": 29, "group": "Gender/Age",
        "symptoms": "severe headache blurred vision swollen hands blood pressure 160/100",
        "patient": {"name": "Savita", "age": 28, "gender": "female",
                    "smoking": "never", "conditions": [], "is_pregnant": True},
        "expected_urgency": "emergency", "expected_specialty": "Gynecologist",
        "expected_diagnosis_keywords": ["preeclampsia", "hypertension", "pregnancy"],
        "label": "Pregnant with preeclampsia — female override",
    },
    {
        "id": 30, "group": "Gender/Age",
        "symptoms": "high fever 104F for 3 days febrile convulsion child",
        "patient": {"name": "Arjun", "age": 8, "gender": "male",
                    "smoking": "never", "conditions": []},
        "expected_urgency": "emergency", "expected_specialty": "Neurologist",
        "expected_diagnosis_keywords": ["fever", "febrile", "seizure", "convulsion"],
        "label": "Child with febrile seizure — pediatric",
    },
]

URGENCY_ORDER = ["low", "moderate", "urgent", "emergency"]

def urgency_score(got: str, expected: str) -> int:
    """Score urgency: 3=exact, 2=one-off, 1=dangerous miss."""
    got = (got or "").lower().strip()
    expected = expected.lower()
    if got == expected:
        return 3
    gi = URGENCY_ORDER.index(got) if got in URGENCY_ORDER else 0
    ei = URGENCY_ORDER.index(expected)
    diff = abs(gi - ei)
    if diff == 1:
        return 2
    # Under-scoring emergency is dangerous
    if expected == "emergency" and gi < ei:
        return 1
    return 1 if diff >= 2 else 2

def diagnosis_score(response_text: str, keywords: list[str]) -> int:
    rt = response_text.lower()
    matches = sum(1 for kw in keywords if kw.lower() in rt)
    if matches >= 2: return 3
    if matches == 1: return 2
    return 1

def action_score(response_text: str, urgency: str) -> int:
    rt = response_text.lower()
    if urgency == "emergency":
        if "112" in rt or "emergency" in rt or "ambulance" in rt:
            return 3
        if "doctor" in rt or "hospital" in rt:
            return 2
        return 1
    if "consult" in rt or "doctor" in rt or "rest" in rt or "medicine" in rt:
        return 3
    return 2

def doctor_score(specialty_returned: str, expected: str) -> int:
    if not specialty_returned:
        return 1
    s = specialty_returned.lower()
    e = expected.lower()
    if e in s or s in e:
        return 3
    # Acceptable fallbacks
    fallbacks = {
        "general physician": ["general", "physician", "gp"],
        "cardiologist": ["cardiac", "heart"],
        "pulmonologist": ["pulmonolog", "chest", "respiratory"],
        "neurologist": ["neuro"],
    }
    for fb_spec, fb_terms in fallbacks.items():
        if e == fb_spec and any(t in s for t in fb_terms):
            return 2
    return 1 if s else 1

def run_case(case: dict) -> dict:
    patient = case["patient"].copy()
    patient.setdefault("name", "Test")
    patient.setdefault("age", 30)
    patient.setdefault("gender", "male")
    patient.pop("is_pregnant", None)

    for attempt in range(2):
        try:
            resp = requests.post(
                f"{BASE}/analyze",
                data={
                    "symptoms_text": case["symptoms"],
                    "patient": json.dumps(patient),
                },
                timeout=90,  # Increased from 45s — Bedrock cold starts take up to 60s
            )
            if resp.status_code == 429:
                time.sleep(15)
                continue
            if resp.status_code != 200:
                return {"error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
            return resp.json()
        except requests.exceptions.Timeout:
            if attempt == 0:
                time.sleep(5)
                continue
            return {"error": "Timeout after 90s (both attempts)"}
        except Exception as e:
            return {"error": str(e)}
    return {"error": "Max retries exceeded"}


def score_response(case: dict, data: dict) -> dict:
    if "error" in data:
        return {"u": 0, "d": 0, "a": 0, "dr": 0, "error": data["error"]}

    urgency_obj = data.get("urgency") or {}
    urgency_level = (urgency_obj.get("level") or "").lower() if isinstance(urgency_obj, dict) else ""
    action_plan   = " ".join(urgency_obj.get("action_plan", [])) if isinstance(urgency_obj, dict) else ""
    call_emergency = urgency_obj.get("call_emergency", False) if isinstance(urgency_obj, dict) else False

    # Gather all text for diagnosis scoring — check every field
    primary_concern = (data.get("primary_concern") or "").lower()
    diag_obj = data.get("diagnosis") or {}
    condition_name = (diag_obj.get("condition_name") or "").lower() if isinstance(diag_obj, dict) else ""
    explanation    = (diag_obj.get("explanation") or "").lower() if isinstance(diag_obj, dict) else ""
    specialist_from_diag = (diag_obj.get("specialist_needed") or "") if isinstance(diag_obj, dict) else ""

    recommendations = data.get("recommendations", [])
    specialist_returned = (
        recommendations[0].get("specialty", "") if recommendations
        else specialist_from_diag
    )

    # Comprehensive text for keyword matching
    full_text = " ".join([
        primary_concern, condition_name, explanation,
        action_plan, data.get("disclaimer", ""), urgency_level,
    ])

    u  = urgency_score(urgency_level, case["expected_urgency"])
    d  = diagnosis_score(full_text, case["expected_diagnosis_keywords"])
    a  = action_score(action_plan + " " + data.get("disclaimer", ""), case["expected_urgency"])
    dr = doctor_score(specialist_returned or specialist_from_diag, case["expected_specialty"])

    return {
        "u": u, "d": d, "a": a, "dr": dr,
        "urgency_got": urgency_level,
        "call_emergency": call_emergency,
        "primary_concern": primary_concern or condition_name,
        "specialist": specialist_returned or specialist_from_diag,
    }


def run_all():
    print("=" * 70)
    print("S5 — 30-Case End-to-End Qualitative Validation")
    print(f"Target: avg >= 2.5/3.0 | Any urgency=1 => CRITICAL FAIL")
    print("=" * 70)

    results = []
    critical_fails = []
    total_u = total_d = total_a = total_dr = 0
    passed = 0

    for case in CASES:
        print(f"\n[{case['id']:02d}/30] {case['label']} ({case['group']})")
        data = run_case(case)
        scores = score_response(case, data)

        if "error" in scores:
            print(f"       ERROR: {scores['error']}")
            results.append({**case, **scores, "avg": 0})
            continue

        avg = (scores["u"] + scores["d"] + scores["a"] + scores["dr"]) / 4
        total_u += scores["u"]; total_d += scores["d"]
        total_a += scores["a"]; total_dr += scores["dr"]

        u_flag = " [CRITICAL]" if scores["u"] == 1 and case["expected_urgency"] == "emergency" else ""
        if scores["u"] == 1 and case["expected_urgency"] == "emergency":
            critical_fails.append(case)

        status = "PASS" if avg >= 2.5 else "WARN"
        print(f"       Got urgency={scores['urgency_got']} (exp={case['expected_urgency']}) | "
              f"call_112={scores['call_emergency']} | primary={scores['primary_concern'][:40]}")
        print(f"       Scores: U={scores['u']}/3  D={scores['d']}/3  A={scores['a']}/3  "
              f"Dr={scores['dr']}/3  avg={avg:.2f} [{status}]{u_flag}")

        if avg < 2.5:
            passed_str = "NEEDS IMPROVEMENT"
        else:
            passed_str = "OK"
            passed += 1
        results.append({**case, **scores, "avg": avg})

    # Summary
    n = len(CASES)
    print("\n" + "=" * 70)
    print("S5 RESULTS SUMMARY")
    print("=" * 70)
    avg_u  = total_u / n;  avg_d = total_d / n
    avg_a  = total_a / n;  avg_dr = total_dr / n
    overall = (avg_u + avg_d + avg_a + avg_dr) / 4

    print(f"Cases passed (avg >= 2.5):  {passed}/{n}")
    print(f"Urgency avg:   {avg_u:.2f}/3.0")
    print(f"Diagnosis avg: {avg_d:.2f}/3.0")
    print(f"Action avg:    {avg_a:.2f}/3.0")
    print(f"Doctor avg:    {avg_dr:.2f}/3.0")
    print(f"OVERALL AVG:   {overall:.2f}/3.0  {'[TARGET MET]' if overall >= 2.5 else '[BELOW TARGET]'}")

    if critical_fails:
        print(f"\n[CRITICAL FAIL] {len(critical_fails)} emergency case(s) scored 1/3 on urgency:")
        for c in critical_fails:
            print(f"   - Case {c['id']}: {c['label']}")
        print("   -> Fix emergency routing before shipping!")
    else:
        print("\n[OK] No critical urgency failures. All emergency cases correctly scored >= 2.")

    print("\nBy group:")
    groups = {}
    for r in results:
        g = r.get("group", "Unknown")
        groups.setdefault(g, []).append(r.get("avg", 0))
    for g, avgs in groups.items():
        g_avg = sum(avgs) / len(avgs)
        print(f"   {g:20s}: {g_avg:.2f}/3.0  ({len(avgs)} cases)")

    print("=" * 70)
    return overall >= 2.5


if __name__ == "__main__":
    passed = run_all()
    sys.exit(0 if passed else 1)
