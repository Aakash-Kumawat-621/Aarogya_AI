import requests
import json

url = "http://localhost:8000/api/v1/analyze"

payload = {
    "symptoms_text": "I am a 55 year old smoker. I've had severe crushing chest pain and shortness of breath for the last 2 hours. My left arm also hurts and I feel very sweaty.",
    "patient": json.dumps({
        "name": "Test Patient",
        "age": 55,
        "gender": "male",
        "smoking_status": "current",
        "activity_level": "sedentary",
        "pre_existing_conditions": ["hypertension"],
        "location": {"latitude": 28.6139, "longitude": 77.2090, "city": "New Delhi"}
    })
}

print("Sending request to Aarogya AI API...")
response = requests.post(url, data=payload)

print(f"Status Code: {response.status_code}")
try:
    data = response.json()
    print(json.dumps(data, indent=2))
except Exception as e:
    print("Response is not JSON:")
    print(response.text)
