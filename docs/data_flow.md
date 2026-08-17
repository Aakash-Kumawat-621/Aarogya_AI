# Aarogya AI — Data Flow
> The journey of ONE user request from browser to final response.
> Each step = one function call. Plain English explanation after each step.
> **Last updated: Module 3 complete.**

---

## The Request We're Tracing

> A 55-year-old male smoker with hypertension opens Aarogya AI.
> He types: **"I have severe chest pain and palpitations"**
> He also uploads a photo of his swollen ankle and a prescription photo.
> He hits Submit.

---

## Full Step-by-Step Journey

---

### Step 1: AWS API Gateway receives `POST /api/v1/analyze`
**File:** AWS Infrastructure (not in our code)

The user's browser sends a multipart form request to our AWS API Gateway URL.
API Gateway forwards it to our AWS Lambda function.

> **What happens here in plain English:**
> The request travels over the internet and arrives at AWS. API Gateway acts like the receptionist — it checks the URL, sees it's `/api/v1/analyze`, and hands it to our Lambda function.

---

### Step 2: `handler()` in `app/main.py` receives the Lambda event
**File:** [`app/main.py`](../backend/app/main.py)
**Function:** `handler` (Mangum wrapper)

Mangum converts the Lambda event format into a standard HTTP request that FastAPI understands.

> **What happens here in plain English:**
> Lambda and FastAPI speak different languages. Mangum is the translator between them — it takes the AWS Lambda event object and converts it into something FastAPI can work with.

---

### Step 3: `analyze_symptoms()` in `app/api/routes/analyze.py` receives the request
**File:** [`app/api/routes/analyze.py`](../backend/app/api/routes/analyze.py)
**Function:** `analyze_symptoms()`

FastAPI routes the request to this function. It does 3 things:
1. Parses the `patient` field from JSON string → `PatientProfile` object
2. Reads uploaded file bytes (xray, body photo, prescription)
3. Validates at least one input exists

> **What happens here in plain English:**
> The API receives everything the user submitted. It checks: Is the patient profile valid JSON? Is the age a real number (not -1)? Did the user actually provide something (symptoms, photo, or file)? If anything is wrong, it sends back an error immediately. If everything is fine, it passes everything to the next step.

---

### Step 4: `build_patient_context()` in `app/core/patient_context.py` is called
**File:** [`app/core/patient_context.py`](../backend/app/core/patient_context.py)
**Function:** `build_patient_context(symptoms_text, patient_profile, xray_bytes, body_photo_bytes, prescription_bytes)`

This is the orchestrator. It creates 4 parallel tasks:
- Task A: Process symptoms text → NLP pipeline
- Task B: Process X-ray (none in this example)
- Task C: Process body photo → Bedrock
- Task D: Process prescription → Textract

All tasks fire simultaneously using `asyncio.gather()`.

> **What happens here in plain English:**
> Instead of doing things one at a time (symptoms first → wait → photo → wait → prescription → wait), this function kicks off ALL the AI processing simultaneously. Like opening 4 browser tabs at once instead of one at a time. This cuts the total waiting time dramatically.

---

### Step 5A (parallel): `_process_symptoms()` calls `extract_symptoms()`
**File:** [`app/modules/nlp/preprocessor.py`](../backend/app/modules/nlp/preprocessor.py)
**Function:** `extract_symptoms("I have severe chest pain and palpitations")`

The scispaCy NER model (`en_core_sci_sm`) reads the text and identifies medical entities.
It also checks for negation words like "no" or "without" before each symptom.

**Returns:**
```python
[
  {"entity": "chest pain", "canonical_form": "chest pain", "negated": False},
  {"entity": "palpitations", "canonical_form": "palpitations", "negated": False}
]
```

> **What happens here in plain English:**
> The AI reads "I have severe chest pain and palpitations" like a medical student would — it picks out the actual symptoms ("chest pain", "palpitations") and notes that neither is negated (the patient didn't say "no chest pain").

---

### Step 5B (parallel): `normalize_all()` in `app/modules/nlp/symptom_normalizer.py`
**File:** [`app/modules/nlp/symptom_normalizer.py`](../backend/app/modules/nlp/symptom_normalizer.py)
**Function:** `normalize_all(entities)`

Looks up each symptom in `symptom_synonyms.json` to map Hinglish/colloquial terms to standard medical names.

> **What happens here in plain English:**
> "Chest pain" is already a standard term so it stays the same. But if someone had typed "seene mein dard" (Hindi for chest pain), this step would convert it to "chest pain" so the system understands it correctly.

---

### Step 6A (parallel): `_process_body_photo()` calls `analyze_body_photo()`
**File:** [`app/services/bedrock_service.py`](../backend/app/services/bedrock_service.py)
**Function:** `analyze_body_photo(body_photo_bytes)`

1. Calls `image_to_base64()` in `image_preprocessor.py` to convert the ankle photo to base64
2. Builds a Claude message with the photo + strict medical prompt ("describe findings only, never diagnose")
3. Calls `_invoke_with_retry()` → AWS Bedrock `invoke_model`
4. Parses the JSON response

**Returns:**
```python
{
  "findings": [{"finding": "swelling", "location": "left ankle", "severity": "moderate"}],
  "confidence": 0.87,
  "body_part_detected": "left ankle",
  "requires_urgent_attention": False
}
```

> **What happens here in plain English:**
> The ankle photo is sent to Claude (an AI model running on AWS). Claude has been given strict instructions: "You are a medical assistant. Describe ONLY what you can visually see. NEVER diagnose." Claude looks at the photo and says "I see moderate swelling at the left ankle". It comes back as structured data, not free text.

---

### Step 6B (parallel): `_process_prescription()` calls `extract_prescription()`
**File:** [`app/modules/ocr/textract_handler.py`](../backend/app/modules/ocr/textract_handler.py)
**Function:** `extract_prescription(prescription_bytes)`

1. Uploads the prescription photo to S3 (`upload_file()` → `aarogya-uploads` bucket)
2. Calls AWS Textract `analyze_document()` with FORMS + TABLES detection
3. Parses each LINE block, looking for drug name patterns ("Tab", "Cap", "mg", "TDS")
4. Deletes the S3 file immediately (privacy)

**Returns:**
```python
{
  "raw_text": "Dr. Mehta\nTab Amoxicillin 500mg TDS\n...",
  "medicines": [{"name": "Amoxicillin", "dosage": "500mg", "frequency": "TDS"}],
  "doctor_name": "Dr. Mehta",
  "diagnosis_text": "Infection",
  "extraction_confidence": 0.92
}
```

> **What happens here in plain English:**
> AWS Textract reads the prescription photo like a very fast human typist — it reads every line of text. Our code then scans those lines looking for drug-related keywords ("Tab", "mg", "TDS") and extracts a structured list of medicines. The original photo is deleted from S3 immediately for patient privacy.

---

### Step 7: `asyncio.gather()` completes — all results collected
**File:** [`app/core/patient_context.py`](../backend/app/core/patient_context.py)
**Function:** `build_patient_context()` (continuing)

All 3 parallel tasks return. Results are mapped back:
- `result_map["symptoms"]` = list of SymptomEntity objects
- `result_map["body_photo"]` = Bedrock findings dict
- `result_map["prescription"]` = Textract medicines dict

---

### Step 8: Risk flag logic runs
**File:** [`app/core/patient_context.py`](../backend/app/core/patient_context.py)
**Function:** `build_patient_context()` (continuing)

The code checks patient profile + active symptoms for risk factors:

```python
risk_flags = []
if patient_profile.age > 50:          → adds "age_over_50"
if smoking == "current":              → adds "current_smoker"
if ("chest pain" or "palpitations") in active symptoms
   AND ("age_over_50" or "current_smoker"):  → adds "cardiac_risk_critical"
```

**Confidence score:** `0.3 base + (3 modalities × 0.15) = 0.75`

> **What happens here in plain English:**
> The system now knows: this patient is 55 years old ✓, is a current smoker ✓, and has chest pain + palpitations ✓. It combines these facts and raises a `cardiac_risk_critical` flag. This is not a diagnosis — it's a signal for the upcoming RAG module to treat this as a high-priority cardiac case.

---

### Step 9: `PatientContext` object is assembled and returned
**File:** [`app/core/patient_context.py`](../backend/app/core/patient_context.py)

```python
PatientContext(
    session_id = "a3f7c2...",
    patient_profile = PatientProfile(name="...", age=55, smoking="current", ...),
    inputs_provided = ["symptoms", "body_photo", "prescription"],
    context_confidence = 0.75,
    symptom_entities = [SymptomEntity("chest pain"), SymptomEntity("palpitations")],
    body_photo_findings = {"finding": "swelling", "location": "left ankle", ...},
    prescription_data = {"medicines": [...], "doctor_name": "Dr. Mehta"},
    risk_flags = ["age_over_50", "current_smoker", "cardiac_risk_critical"],
    primary_concern = "chest pain"
)
```

> **What happens here in plain English:**
> All the parallel results are now packed into one neat object. Think of it like filling out a patient form at a hospital — but instead of the patient writing it by hand, 4 AI systems filled it in simultaneously.

---

---

### Step 10: `query_builder.py` formulates the search query
**File:** [`app/modules/rag/query_builder.py`](../backend/app/modules/rag/query_builder.py)

Takes the `PatientContext` and creates a semantic search query.

> **What happens here in plain English:**
> Instead of just searching for "chest pain", it builds a smart query like: "55-year-old male current smoker presenting with chest pain and palpitations. Associated with cardiac risk critical."

---

### Step 11: `retriever.py` fetches facts from Pinecone
**File:** [`app/modules/rag/retriever.py`](../backend/app/modules/rag/retriever.py)

Embeds the query using BioSentBERT (768 dimensions) and queries Pinecone for the top 5 closest chunks.

> **What happens here in plain English:**
> It searches the medical textbook (Pinecone) we built on Kaggle. It pulls out 5 paragraphs about heart attacks and cardiovascular issues that match the patient's symptoms perfectly.

---

### Step 12: `chain.py` asks Bedrock for a diagnosis
**File:** [`app/modules/rag/chain.py`](../backend/app/modules/rag/chain.py)

Combines the patient context and the 5 retrieved facts into a massive prompt. Sends it to Bedrock Nova Lite.

> **What happens here in plain English:**
> The AI is given the textbook facts and the patient's symptoms and is told: "Based ONLY on these facts, what is the diagnosis?" It replies with a structured JSON diagnosis, an urgency level, and an action plan.

---

### Step 13: `finder.py` finds nearby doctors
**File:** [`app/modules/doctors/finder.py`](../backend/app/modules/doctors/finder.py)

Uses the patient's location and maps the condition to a specialty (e.g., Cardiology). Queries DynamoDB for doctors.

> **What happens here in plain English:**
> Since the diagnosis is cardiac-related, it finds Cardiologists within a 10km radius of the patient and returns their details.

---

### Step 14: `dynamodb_service.py` saves the session
**File:** [`app/services/dynamodb_service.py`](../backend/app/services/dynamodb_service.py)

Saves the entire report to DynamoDB with a 30-day expiration.

> **What happens here in plain English:**
> The report is safely stored in our database so the patient can view it again tomorrow.

---

### Step 15: `analyze_symptoms()` builds the HTTP response
**File:** [`app/api/routes/analyze.py`](../backend/app/api/routes/analyze.py)

Takes the diagnosis, doctors, and context, mapping it to `AnalyzeResponse`:

```python
AnalyzeResponse(
    session_id = "a3f7c2...",
    context_built = True,
    inputs_processed = ["symptoms", "body_photo", "prescription"],
    symptoms_extracted = 2,
    risk_flags = ["age_over_50", "current_smoker", "cardiac_risk_critical"],
    context_confidence = 0.75,
    primary_concern = "chest pain",
    diagnosis = Diagnosis(condition="Myocardial Infarction", severity="emergency", ...),
    urgency = Urgency(level="emergency", call_ambulance=True, ...),
    doctors = [DoctorResult(name="Dr. Sharma", specialty="Cardiologist", ...)],
    processing_time_ms = 3540
)
```

---

### Step 16: FastAPI serializes the response to JSON and sends it back
**File:** FastAPI (framework handles this)

FastAPI converts the `AnalyzeResponse` object to JSON and sends it back through API Gateway to the user's browser.

> **What happens here in plain English:**
> The user's phone receives the JSON response. The frontend reads it and flashes a massive red warning to call an ambulance, while also suggesting Dr. Sharma at the nearest Apollo hospital.

---

## Summary Diagram

```
User Browser
    │
    ▼  POST /api/v1/analyze (multipart form)
AWS API Gateway
    │
    ▼
AWS Lambda  →  main.py handler() [Mangum]
    │
    ▼
analyze.py  →  analyze_symptoms()
    │  parse patient JSON, read file bytes
    ▼
patient_context.py  →  build_patient_context()
    │
    ├──── asyncio.gather ────────────────────────────────┐
    │                                                    │
    ▼                           ▼                        ▼
_process_symptoms()     _process_body_photo()   _process_prescription()
    │                           │                        │
    ▼                           ▼                        ▼
preprocessor.py         bedrock_service.py      textract_handler.py
extract_symptoms()      analyze_body_photo()    extract_prescription()
    │                           │                        │
    ▼                           ▼                        ▼
symptom_normalizer.py   image_preprocessor.py   s3_service.py
normalize_all()         image_to_base64()       upload_file()
                                │               delete_file()
                                ▼
                        AWS Bedrock (Claude)
    │                           │                        │
    └───────────── asyncio.gather completes ─────────────┘
                                │
                                ▼
                    Risk flag calculation
                    PatientContext assembled
                                │
                                ▼
                        query_builder.py
                        Build semantic query
                                │
                                ▼
                          retriever.py
                     Fetch Pinecone knowledge
                                │
                                ▼
                            chain.py
                    Bedrock Nova Lite Diagnosis
                                │
                                ▼
                            finder.py
                     Find nearby specialists
                                │
                                ▼
                       dynamodb_service.py
                      Save session for 30 days
                                │
                                ▼
                     AnalyzeResponse JSON
                                │
                                ▼
                        User Browser ✓
```
