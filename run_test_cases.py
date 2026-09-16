import requests
import json
import time

url = "http://localhost:8000/api/v1/analyze"

test_cases = [
    {
        "id": "TC-01",
        "expected_urgency": "EMERGENCY",
        "symptoms": "Chest pain, left arm pain, sweating",
        "patient": {
            "name": "Test Patient", "age": 55, "gender": "male",
            "smoking": "current", "conditions": ["hypertension"]
        }
    },
    {
        "id": "TC-02",
        "expected_urgency": "LOW",
        "symptoms": "Mild cough, runny nose, 2 days",
        "patient": {
            "name": "Test Patient", "age": 25, "gender": "female",
            "smoking": "never", "conditions": []
        }
    },
    {
        "id": "TC-03",
        "expected_urgency": "URGENT",
        "symptoms": "High fever, rash, joint pain, 4 days",
        "patient": {
            "name": "Test Patient", "age": 35, "gender": "male",
            "smoking": "never", "conditions": []
        }
    },
    {
        "id": "TC-04",
        "expected_urgency": "MODERATE",
        "symptoms": "Frequent urination, fatigue, blurred vision",
        "patient": {
            "name": "Test Patient", "age": 60, "gender": "female",
            "smoking": "never", "conditions": ["diabetes"]
        }
    },
    {
        "id": "TC-05",
        "expected_urgency": "EMERGENCY",
        "symptoms": "Sudden worst headache of life",
        "patient": {
            "name": "Test Patient", "age": 40, "gender": "male",
            "smoking": "never", "conditions": []
        }
    },
    {
        "id": "TC-06",
        "expected_urgency": "EMERGENCY",
        "symptoms": "High BP, protein urine, swelling",
        "patient": {
            "name": "Test Patient", "age": 28, "gender": "female",
            "smoking": "never", "conditions": ["pregnancy"]
        }
    },
    {
        "id": "TC-07",
        "expected_urgency": "MODERATE",
        "symptoms": "Right upper abdominal pain after fatty food",
        "patient": {
            "name": "Test Patient", "age": 45, "gender": "male",
            "smoking": "never", "bmi": 32, "conditions": []
        }
    },
    {
        "id": "TC-08",
        "expected_urgency": "URGENT",
        "symptoms": "Fall, hip pain, cannot bear weight",
        "patient": {
            "name": "Test Patient", "age": 70, "gender": "male",
            "smoking": "never", "conditions": []
        }
    },
    {
        "id": "TC-09",
        "expected_urgency": "MODERATE",
        "symptoms": "Burning urination, frequency, no fever",
        "patient": {
            "name": "Test Patient", "age": 22, "gender": "female",
            "smoking": "never", "conditions": []
        }
    },
    {
        "id": "TC-10",
        "expected_urgency": "URGENT",
        "symptoms": "Chronic cough 3 months, weight loss",
        "patient": {
            "name": "Test Patient", "age": 50, "gender": "male",
            "smoking": "current", "conditions": []
        }
    },
    {
        "id": "TC-11",
        "expected_urgency": "LOW",
        "symptoms": "Mild headache, feeling stressed",
        "patient": {
            "name": "Test Patient", "age": 30, "gender": "male",
            "smoking": "never", "conditions": []
        }
    },
    {
        "id": "TC-12",
        "expected_urgency": "EMERGENCY",
        "symptoms": "Difficulty breathing, chest tightness, asthma attack",
        "patient": {
            "name": "Test Patient", "age": 18, "gender": "female",
            "smoking": "never", "conditions": ["asthma"]
        }
    },
    {
        "id": "TC-13",
        "expected_urgency": "MODERATE",
        "symptoms": "Knee pain, swelling, after running",
        "patient": {
            "name": "Test Patient", "age": 35, "gender": "female",
            "smoking": "never", "conditions": []
        }
    },
    {
        "id": "TC-14",
        "expected_urgency": "URGENT",
        "symptoms": "Severe abdominal pain, vomiting blood",
        "patient": {
            "name": "Test Patient", "age": 45, "gender": "male",
            "smoking": "current", "conditions": ["ulcer"]
        }
    },
    {
        "id": "TC-15",
        "expected_urgency": "EMERGENCY",
        "symptoms": "Sudden weakness in left arm, facial droop, slurred speech",
        "patient": {
            "name": "Test Patient", "age": 72, "gender": "male",
            "smoking": "current", "conditions": ["hypertension"]
        }
    },
    {
        "id": "TC-16",
        "expected_urgency": "MODERATE",
        "symptoms": "Itchy eyes, sneezing, runny nose",
        "patient": {
            "name": "Test Patient", "age": 20, "gender": "male",
            "smoking": "never", "conditions": []
        }
    },
    {
        "id": "TC-17",
        "expected_urgency": "URGENT",
        "symptoms": "High fever, stiff neck, sensitive to light",
        "patient": {
            "name": "Test Patient", "age": 25, "gender": "female",
            "smoking": "never", "conditions": []
        }
    },
    {
        "id": "TC-18",
        "expected_urgency": "LOW",
        "symptoms": "Small cut on finger, stopped bleeding",
        "patient": {
            "name": "Test Patient", "age": 40, "gender": "male",
            "smoking": "never", "conditions": []
        }
    },
    {
        "id": "TC-19",
        "expected_urgency": "EMERGENCY",
        "symptoms": "Allergic reaction, throat swelling, can't breathe",
        "patient": {
            "name": "Test Patient", "age": 28, "gender": "female",
            "smoking": "never", "conditions": ["peanut allergy"]
        }
    },
    {
        "id": "TC-20",
        "expected_urgency": "MODERATE",
        "symptoms": "Lower back pain, radiating down leg",
        "patient": {
            "name": "Test Patient", "age": 55, "gender": "male",
            "smoking": "never", "conditions": []
        }
    }
]

print(f"{'Case':<8} | {'Expected':<10} | {'Actual':<10} | {'Top Disease':<30} | {'Time (s)':<8} | Status")
print("-" * 85)

all_passed = True
for tc in test_cases:
    payload = {
        "symptoms_text": tc["symptoms"],
        "patient": json.dumps(tc["patient"])
    }
    
    start_time = time.time()
    try:
        resp = requests.post(url, data=payload, timeout=120)
        elapsed = time.time() - start_time
        
        if resp.status_code == 200:
            data = resp.json()
            # Extract urgency and top disease
            actual_urgency = data.get("urgency", {}).get("level", "UNKNOWN").upper()
            
            top_disease = "None"
            if "primary_concern" in data:
                top_disease = data["primary_concern"]
                    
            status = "PASS" if actual_urgency == tc["expected_urgency"] else "FAIL"
            if status == "FAIL":
                all_passed = False
                
            print(f"{tc['id']:<8} | {tc['expected_urgency']:<10} | {actual_urgency:<10} | {top_disease[:28]:<30} | {elapsed:.2f}s   | {status}", flush=True)
        else:
            all_passed = False
            print(f"{tc['id']:<8} | {tc['expected_urgency']:<10} | ERROR      | {resp.status_code} {resp.reason[:25]:<26} | {elapsed:.2f}s   | FAIL", flush=True)
            
    except Exception as e:
        all_passed = False
        print(f"{tc['id']:<8} | {tc['expected_urgency']:<10} | TIMEOUT    | {str(e)[:28]:<30} | -        | FAIL", flush=True)

print("-" * 85)
print(f"Overall Status: {'PASS' if all_passed else 'FAIL'}")
