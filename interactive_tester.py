import requests
import json
import time

API_URL = "http://localhost:8000/api/v1/analyze"

print("=" * 60)
print("🩺 Aarogya AI - Interactive Terminal Tester 🩺")
print("=" * 60)
print("Type 'quit' or 'exit' to stop.\n")

while True:
    symptoms = input("Enter symptoms (e.g. 'chest pain, sweating'): ").strip()
    
    if symptoms.lower() in ['quit', 'exit', 'q']:
        print("Goodbye!")
        break
        
    if not symptoms:
        continue
        
    age = input("Patient Age (default 35): ").strip() or "35"
    gender = input("Patient Gender (male/female, default male): ").strip() or "male"
    smoking = input("Smoking Status (never/current/former, default never): ").strip() or "never"
    
    payload = {
        "symptoms_text": symptoms,
        "patient": json.dumps({
            "age": int(age),
            "gender": gender,
            "smoking": smoking,
            "conditions": []
        })
    }
    
    print("\n⏳ Analyzing (Calling NLP -> ML -> Pinecone -> Bedrock)...")
    start = time.time()
    
    try:
        response = requests.post(API_URL, data=payload, timeout=60)
        elapsed = time.time() - start
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Success! ({elapsed:.2f}s)\n")
            print("-" * 40)
            
            # Print Urgency
            urgency = data.get("urgency", {})
            urgency_level = urgency.get("level", "UNKNOWN").upper()
            print(f"🚨 URGENCY: {urgency_level}")
            
            # Print Diagnosis / Primary Concern
            if "primary_concern" in data:
                print(f"🦠 TOP CONCERN: {data['primary_concern']}")
            
            if "analysis" in data and "possible_conditions" in data["analysis"]:
                print("\n📋 CONDITIONS & EXPLANATIONS:")
                for i, cond in enumerate(data["analysis"]["possible_conditions"][:2], 1):
                    name = cond.get("condition", "Unknown")
                    exp = cond.get("explanation", "")
                    print(f"  {i}. {name}")
                    print(f"     {exp}")
            
            if "urgency" in data and "action_plan" in data["urgency"]:
                print("\n🏃 ACTION PLAN:")
                for action in data["urgency"]["action_plan"]:
                    print(f"  - {action}")
                    
            print("-" * 40)
            print("\n")
        else:
            print(f"❌ Error {response.status_code}: {response.text}\n")
            
    except requests.exceptions.Timeout:
        print("❌ Request timed out (Bedrock might be slow). Try again.\n")
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to API. Is Uvicorn running?\n")
