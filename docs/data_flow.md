# Aarogya AI — End-to-End Data Flow

> A step-by-step execution walkthrough of a single user request to `POST /api/v1/analyze` from initial API Gateway invocation to final JSON response return.

---

## Overview

When a user submits symptoms, photos, and profile data in the Aarogya AI app, their request flows through **15 distinct steps** across our serverless architecture:

```
[User App] ──> [AWS API Gateway] ──> [AWS Lambda / Mangum] ──> [FastAPI Router]
                                                                      │
┌─────────────────────────────────────────────────────────────────────┘
│
├──> 1. Pydantic Models       (Input Validation)
├──> 2. S3 Storage Service    (Image/Prescription Uploads)
├──> 3. NLP Preprocessor      (Entity, Negation & Severity Extraction)
├──> 4. Symptom Normalizer    (Exact & Fuzzy Synonym Mapping)
├──> 5. Image Preprocessor    (CLAHE Contrast & Tensor Formatting)
├──> 6. Textract OCR          (Prescription Medication Extraction)
├──> 7. PatientContext        (Multimodal Context Fusion)
├──> 8. ML & Risk Scorer      (Tabular Prediction & Severity Classification)
├──> 9. RAG Knowledge Search  (Pinecone Vector Search & Bedrock LLM)
├──> 10. Doctor Finder        (Specialty Mapping & Google Places Lookup)
└──> 11. Response Builder     (Final JSON Aggregation & Disclaimer Injection)
                                                                      │
[User App] <── [AWS API Gateway] <── [FastAPI / Mangum] <──────────────┘
```

---

## Step-by-Step Execution Walkthrough

### Step 1: AWS API Gateway receives `POST /api/v1/analyze`
- **Function / Handler**: AWS API Gateway HTTP Endpoint
- **Calls**: Mangum adapter in `app/main.py`
- **Input**: HTTP `POST` multipart/form-data request body containing `patient`, `location`, `symptoms_text`, and binary files (`xray_image`, `body_photo`, `prescription`).
- **Output**: Transformed API Gateway proxy event dict passed to AWS Lambda.
- **What happens here in plain English**: The user taps "Analyze Symptoms" in the app. AWS API Gateway receives their request securely over HTTPS and forwards it to our serverless backend running inside AWS Lambda.

---

### Step 2: Mangum adapter forwards event in `app/main.py`
- **Function / Handler**: `handler(event, context)` in [`backend/app/main.py`](file:///C:/Users/aakas/Documents/Agent/Aarogya_AI/backend/app/main.py)
- **Calls**: `analyze_symptoms()` in `app/api/routes/analyze.py`
- **Input**: AWS Lambda WSGI/ASGI event payload.
- **Output**: FastAPI request context.
- **What happens here in plain English**: AWS Lambda wakes up Python. The `Mangum` library converts the raw AWS serverless event into a standard HTTP request that our FastAPI web framework understands, routing it straight to our `analyze` route.

---

### Step 3: `analyze_symptoms()` receives request in `app/api/routes/analyze.py`
- **Function / Handler**: `analyze_symptoms()` in [`backend/app/api/routes/analyze.py`](file:///C:/Users/aakas/Documents/Agent/Aarogya_AI/backend/app/api/routes/analyze.py)
- **Calls**: Pydantic validators in `app/models/request_models.py`
- **Input**: Form parameters (`patient`, `location`, `symptoms_text`) and uploaded file objects (`xray_image`, `body_photo`, `prescription`).
- **Output**: Extracted form parameters ready for parsing and validation.
- **What happens here in plain English**: The API route function catches all incoming form fields and uploaded medical files. It checks if at least one input modality (text or image) was provided.

---

### Step 4: `PatientProfile` validates demographic data in `app/models/request_models.py`
- **Function / Handler**: `PatientProfile(**patient_dict)` and `LocationData(**loc_dict)` in [`backend/app/models/request_models.py`](file:///C:/Users/aakas/Documents/Agent/Aarogya_AI/backend/app/models/request_models.py)
- **Calls**: Pydantic internal parsing engine
- **Input**: Raw JSON string representations of patient profile and location.
- **Output**: Validated Python `PatientProfile` and `LocationData` objects.
- **What happens here in plain English**: The server parses the patient's JSON profile (age, gender, height, weight, medical conditions, allergies) and validates every field. If an age is invalid (e.g., negative), it immediately stops execution and returns a clear 422 error.

---

### Step 5: `upload_file()` saves images to S3 in `app/services/s3_service.py`
- **Function / Handler**: `upload_file()` in [`backend/app/services/s3_service.py`](file:///C:/Users/aakas/Documents/Agent/Aarogya_AI/backend/app/services/s3_service.py)
- **Calls**: AWS S3 Boto3 API (`put_object`)
- **Input**: Raw bytes of `xray_image`, `body_photo`, or `prescription`, filename, and MIME type.
- **Output**: Unique S3 storage keys (e.g., `"uploads/550e8400-xray.jpg"`).
- **What happens here in plain English**: If the user uploaded any images or prescription documents, this function streams their raw bytes to our secure AWS S3 bucket (`aarogya-uploads`) and returns permanent cloud file references.

---

### Step 6: `extract_symptoms()` parses text in `app/modules/nlp/preprocessor.py`
- **Function / Handler**: `extract_symptoms(symptoms_text)` in [`backend/app/modules/nlp/preprocessor.py`](file:///C:/Users/aakas/Documents/Agent/Aarogya_AI/backend/app/modules/nlp/preprocessor.py)
- **Calls**: spaCy pipelines `en_ner_bc5cdr_md` and `en_core_sci_sm`
- **Input**: Raw symptom text string (e.g., `"I have severe chest pain and fever for 3 days. No cough."`).
- **Output**: Dictionary of extracted medical entities with `negated`, `uncertain`, `severity`, and `duration_category` flags.
- **What happens here in plain English**: The NLP engine reads the patient's text. It uses medical AI models to identify symptom entities, determines if any symptoms are denied ("no cough" -> negated), extracts severity ("severe"), and calculates duration ("3 days" -> acute).

---

### Step 7: `normalize_all()` standardizes terms in `app/modules/nlp/symptom_normalizer.py`
- **Function / Handler**: `normalize_all(symptom_entities)` in [`backend/app/modules/nlp/symptom_normalizer.py`](file:///C:/Users/aakas/Documents/Agent/Aarogya_AI/backend/app/modules/nlp/symptom_normalizer.py)
- **Calls**: Exact dictionary lookup & `rapidfuzz.process.extractOne()` against `symptom_synonyms.json`
- **Input**: Raw extracted symptom dictionary list.
- **Output**: Symptom list updated with normalized `canonical_form` strings (e.g., `"chest ache"` -> `"chest pain"`, `"saans nahi aa rahi"` -> `"dyspnea"`).
- **What happens here in plain English**: Colloquial descriptions, typos, or Hinglish phrases typed by the patient are mapped to standard medical concepts so downstream diagnostic models can recognize them accurately.

---

### Step 8: `preprocess_xray()` enhances image contrast in `app/modules/image/image_preprocessor.py`
- **Function / Handler**: `preprocess_xray(image_bytes)` / `image_to_base64()` in [`backend/app/modules/image/image_preprocessor.py`](file:///C:/Users/aakas/Documents/Agent/Aarogya_AI/backend/app/modules/image/image_preprocessor.py)
- **Calls**: OpenCV CLAHE (`cv2.createCLAHE`) & PIL Image
- **Input**: Raw X-ray or body photo image bytes.
- **Output**: 224x224x3 float32 NumPy tensor array (for ML models) and base64 strings (for Bedrock Vision API).
- **What happens here in plain English**: If an X-ray was uploaded, this step applies CLAHE contrast enhancement to sharpen subtle lung patterns, resizes the image to 224x224 pixels, and formats it as a tensor ready for computer vision analysis.

---

### Step 9: `extract_prescription_text()` reads drugs in `app/modules/ocr/textract_handler.py`
- **Function / Handler**: `extract_prescription_text(s3_key)` in `app/modules/ocr/textract_handler.py` *(Module 2 S7)*
- **Calls**: AWS Textract API
- **Input**: S3 storage key of prescription image.
- **Output**: Structured list of recognized drug names, dosages, and usage frequency.
- **What happens here in plain English**: If a prescription photo was provided, AWS Textract OCR scans the document to extract medication names and dosages currently taken by the patient.

---

### Step 10: `build_patient_context()` merges all inputs in `app/core/patient_context.py`
- **Function / Handler**: `build_patient_context(...)` in [`backend/app/core/patient_context.py`](file:///C:/Users/aakas/Documents/Agent/Aarogya_AI/backend/app/core/patient_context.py) *(Module 2 S10)*
- **Calls**: Synthesizes output from Steps 4, 5, 6, 7, 8, and 9
- **Input**: Patient profile, normalized symptoms, image tensors, OCR drug lists, and location data.
- **Output**: Single unified `PatientContext` master object.
- **What happens here in plain English**: All 5 input sources (symptoms, X-rays, body photos, prescriptions, personal profile) are merged into one clean, comprehensive patient profile object that powers all downstream AI reasoning.

---

### Step 11: `calculate_severity()` evaluates risk in `app/modules/ml/severity_scorer.py`
- **Function / Handler**: `calculate_severity(patient_context)` & `predict_conditions()` in `app/modules/ml/` *(Module 4)*
- **Calls**: XGBoost / LightGBM classification models
- **Input**: Merged `PatientContext` object.
- **Output**: Predicted condition candidates and risk urgency score (`low`, `moderate`, `urgent`, `emergency`).
- **What happens here in plain English**: Tabular machine learning models analyze the patient's symptoms, age, and vitals to score clinical risk and predict probable medical condition candidates.

---

### Step 12: `search_knowledge_base()` retrieves evidence in `app/modules/rag/chain.py`
- **Function / Handler**: `search_knowledge_base()` & `generate_diagnosis()` in `app/modules/rag/` *(Module 3)*
- **Calls**: Pinecone Vector Index & AWS Bedrock LLM (Amazon Nova / Claude)
- **Input**: `PatientContext` and candidate conditions.
- **Output**: Evidence-backed medical explanation, diagnosis summary, and peer-reviewed web citations.
- **What happens here in plain English**: Our RAG pipeline searches millions of medical articles in Pinecone for clinical guidelines matching the patient's context, then passes the evidence to AWS Bedrock LLM to draft a safe, human-readable medical explanation.

---

### Step 13: `search_doctors()` locates specialists in `app/modules/doctors/finder.py`
- **Function / Handler**: `search_doctors(specialty, location)` in `app/modules/doctors/` *(Module 5)*
- **Calls**: Google Places API & Medical Registry
- **Input**: Required medical specialty (e.g., `"Pulmonologist"`) and user location coordinates.
- **Output**: List of nearby qualified doctors, hospital names, ratings, and phone numbers.
- **What happens here in plain English**: The system determines which specialist the patient should see and queries Google Places to find top-rated doctors within traveling distance of the user's location.

---

### Step 14: `build_response()` packages final JSON in `app/core/response_builder.py`
- **Function / Handler**: `build_response(...)` in [`backend/app/core/response_builder.py`](file:///C:/Users/aakas/Documents/Agent/Aarogya_AI/backend/app/core/response_builder.py) *(Module 5)*
- **Calls**: `AnalyzeResponse` Pydantic model
- **Input**: Diagnosis findings, urgency score, doctor recommendations, and session ID.
- **Output**: Complete `AnalyzeResponse` object populated with mandatory legal disclaimers and processing metrics.
- **What happens here in plain English**: The response builder gathers the diagnosis, urgency action plan, doctor recommendations, and safety disclaimers, packing them into the final JSON payload.

---

### Step 15: API Gateway sends HTTP 200 response back to User
- **Function / Handler**: FastAPI response return -> Mangum -> AWS API Gateway -> App Client
- **Calls**: Network HTTP transmission
- **Input**: `AnalyzeResponse` Pydantic instance.
- **Output**: HTTP 200 OK JSON response delivered to patient's mobile/web app.
- **What happens here in plain English**: FastAPI serializes the response into JSON. AWS API Gateway transmits it over HTTPS back to the user's phone, where the frontend renders the diagnostic dashboard, urgency warnings, and nearby doctor cards.
