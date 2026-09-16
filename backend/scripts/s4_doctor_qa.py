"""
Step S4 — Manual QA: 10 doctor searches from Jaipur (26.9124, 75.7873)
Evaluates Google Places results for quality, relevance, and accuracy.
"""
import asyncio
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import os
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, '.')

from app.modules.doctors.specialty_mapper import get_specialty_result
from app.modules.doctors.finder import find_doctors

JAIPUR_LAT = 26.9124
JAIPUR_LNG = 75.7873

TESTS = [
    {"condition": "chest pain",       "gender": "male",   "age": 50, "urgency": "urgent",    "label": "ACS - Cardiologist"},
    {"condition": "pneumonia",        "gender": "male",   "age": 40, "urgency": "urgent",    "label": "Pneumonia - Pulmonologist"},
    {"condition": "migraine",         "gender": "female", "age": 35, "urgency": "moderate",  "label": "Migraine - Neurologist"},
    {"condition": "gallstones",       "gender": "male",   "age": 55, "urgency": "moderate",  "label": "Gallstones - Gastroenterologist"},
    {"condition": "sepsis",           "gender": "male",   "age": 65, "urgency": "emergency", "label": "EMERGENCY - Hospital"},
    {"condition": "uti",              "gender": "female", "age": 28, "urgency": "low",       "label": "UTI Female - Gynecologist override"},
    {"condition": "fracture",         "gender": "male",   "age": 45, "urgency": "urgent",    "label": "Hip Fracture - Orthopedist"},
    {"condition": "rash",             "gender": "female", "age": 30, "urgency": "low",       "label": "Skin Rash - Dermatologist"},
    {"condition": "depression",       "gender": "male",   "age": 22, "urgency": "moderate",  "label": "Depression - Psychiatrist"},
    {"condition": "chest pain",       "gender": "male",   "age": 12, "urgency": "urgent",    "label": "ACS Age<18 - Pediatric override"},
]

PASS_EMOJI = "[PASS]"
FAIL_EMOJI = "[FAIL]"
WARN_EMOJI = "[WARN]"

async def run_s4():
    results_summary = []
    print("=" * 70)
    print("STEP S4 — Google Places Doctor Search QA")
    print(f"Location: Jaipur ({JAIPUR_LAT}, {JAIPUR_LNG})")
    print("=" * 70)

    for i, test in enumerate(TESTS, 1):
        print(f"\n[{i}/10] {test['label']}")
        print(f"        condition={test['condition']} | gender={test['gender']} | age={test['age']} | urgency={test['urgency']}")

        spec = get_specialty_result(
            condition=test['condition'],
            gender=test.get('gender'),
            age=test.get('age'),
            urgency=test.get('urgency'),
        )
        print(f"        Specialty mapper -> {spec.primary} | search='{spec.google_search_term}' | emergency={spec.emergency_dept}")

        try:
            doctors = await find_doctors(
                condition=test['condition'],
                specialty=spec.primary,
                google_search_term=spec.google_search_term,
                lat=JAIPUR_LAT,
                lng=JAIPUR_LNG,
                urgency=test['urgency'],
                emergency_dept=spec.emergency_dept,
                top_k=5,
            )
        except Exception as e:
            print(f"        {FAIL_EMOJI} ERROR: {e}")
            results_summary.append({"test": test['label'], "status": "ERROR", "count": 0, "source": "error"})
            continue

        source = doctors[0].source if doctors else "none"

        # QA checks
        issues = []
        if not doctors:
            issues.append("No results returned")
        else:
            for d in doctors:
                if d.distance_km > 40:
                    issues.append(f"Suspicious distance: {d.name} = {d.distance_km}km")
                if d.rating < 1.0:
                    issues.append(f"Suspicious rating: {d.name} = {d.rating}")
                if not d.name or d.name == "Unknown":
                    issues.append("Missing doctor name")

        # Gender override check
        if test.get('gender') == 'female' and test['condition'] == 'uti':
            if spec.primary != 'Gynecologist':
                issues.append(f"Gender override FAILED: expected Gynecologist, got {spec.primary}")

        # Age override check
        if test.get('age', 99) < 18:
            if 'pediatric' not in spec.google_search_term.lower():
                issues.append(f"Age override FAILED: expected 'pediatric' in search term")

        # Emergency check
        if test['urgency'] == 'emergency' and spec.emergency_dept:
            if 'emergency' not in spec.google_search_term.lower():
                issues.append("Emergency routing FAILED")

        status = FAIL_EMOJI if issues else PASS_EMOJI
        print(f"        {status} Source={source} | Results={len(doctors)}")

        for d in doctors[:3]:
            open_str = "OPEN" if d.is_open_now else ("CLOSED" if d.is_open_now is False else "hrs N/A")
            print(f"           {d.rating:.1f}* {d.name} [{d.hospital}] {d.distance_km}km [{open_str}]")
            if d.phone:
                print(f"                {d.phone} | {d.address[:60]}")

        for issue in issues:
            print(f"        {WARN_EMOJI} {issue}")

        results_summary.append({
            "test": test['label'],
            "status": "PASS" if not issues else "ISSUES",
            "count": len(doctors),
            "source": source,
            "issues": issues,
        })

    # Summary
    print("\n" + "=" * 70)
    print("S4 SUMMARY")
    print("=" * 70)
    passed = sum(1 for r in results_summary if r['status'] == 'PASS')
    print(f"Passed: {passed}/{len(results_summary)}")
    for r in results_summary:
        icon = PASS_EMOJI if r['status'] == 'PASS' else FAIL_EMOJI
        print(f"  {icon} {r['test']} | source={r['source']} | results={r['count']}")
        for issue in r.get('issues', []):
            print(f"       -> {issue}")
    print("=" * 70)

asyncio.run(run_s4())
