# Aarogya AI — Codebase Explained
> Simple enough for someone who just started Python.
> **Last updated: Module 3 complete.**

---

## How the folders are organized

```
backend/app/
├── main.py                  ← Starts the server
├── config.py                ← Reads all settings from .env
├── api/routes/              ← All API endpoints (what the frontend calls)
├── core/                    ← Brain logic (builds the patient picture)
├── models/                  ← Data shapes (what does a request / response look like?)
├── modules/                 ← AI tools (NLP, OCR, Image processing)
└── services/                ← External services (AWS S3, Bedrock, DynamoDB)
```

---

## File-by-file breakdown

---

### `app/main.py`
**Single job:** Start the FastAPI web server and register all routes.

- **Input:** Nothing — runs when the server boots
- **Output:** A running web server at port 8000 (or Lambda handler in production)
- **Key functions:**
  - `handler` — the AWS Lambda entry point; Mangum wraps FastAPI for Lambda
  - `startup()` — logs "Aarogya AI is starting" when the server boots
- **Connects to:** `app/api/routes/` (loads all routes), `config.py`
- **Plain English:** When AWS Lambda gets a request, it lands here first. This file makes sure all the API routes are ready and the server is configured correctly.

---

### `app/config.py`
**Single job:** Read every secret and setting from the `.env` file and make them available to the rest of the app.

- **Input:** Environment variables (`.env` file or GitHub Secrets in CI)
- **Output:** A `settings` object that any file can import
- **Key functions/fields:**
  - `AWS_REGION`, `S3_BUCKET_NAME`, `DYNAMODB_TABLE` — AWS configuration
  - `BEDROCK_MODEL_ID` — which AI model to use for body photo analysis
  - `PINECONE_API_KEY`, `PINECONE_INDEX` — vector database for Module 3
  - `GEMINI_API_KEY` — Google Gemini for the final diagnosis (Module 3)
  - `boto3_kwargs` — a helper property that returns AWS credentials ready-to-use for boto3
- **Connects to:** Every file that talks to AWS or external APIs
- **Plain English:** Think of this as the app's memory for all passwords and addresses. Instead of hardcoding `"us-east-1"` in ten different files, everyone just imports `settings.AWS_REGION`.

---

## `app/api/routes/` — The API Endpoints

---

### `app/api/routes/analyze.py`
**Single job:** Receive the patient's submission (symptoms, photos, files) and run the full AI pipeline.

- **Input:** Multipart form-data — `symptoms_text`, `patient` (JSON), `xray_image`, `body_photo`, `prescription` (all optional, at least one required)
- **Output:** JSON with session ID, extracted symptoms, risk flags, and confidence score
- **Key functions:**
  - `analyze_symptoms()` — the main handler for `POST /api/v1/analyze`; parses inputs, reads uploaded bytes, calls `build_patient_context`, returns result
- **Connects to:** `core/patient_context.py` (calls `build_patient_context`), `models/request_models.py`, `models/response_models.py`
- **Plain English:** When a user submits chest pain symptoms and an X-ray photo, this function receives everything, validates it, then hands it all to `patient_context.py` to process. It then returns the structured result.

---

### `app/api/routes/health.py`
**Single job:** Reply "I'm alive" so AWS and monitoring tools know the server is running.

- **Input:** Nothing — just a GET request
- **Output:** `{"status": "ok"}`
- **Connects to:** Nothing else
- **Plain English:** Like a heartbeat monitor. AWS checks this URL every minute; if it stops responding, AWS restarts the container.

---

### `app/api/routes/doctors.py`
**Single job:** Find nearby doctors based on the patient's condition and location. *(Implemented in Module 3)*

- **Input:** Condition/Specialty, latitude, longitude
- **Output:** List of `DoctorResult` objects
- **Connects to:** `modules/doctors/finder.py`

---

### `app/api/routes/history.py`
**Single job:** Retrieve a patient's past diagnostic sessions from DynamoDB. *(Implemented in Module 3)*

- **Input:** `session_id`
- **Output:** The full saved `AnalyzeResponse` from that session
- **Connects to:** `services/dynamodb_service.py`

---

## `app/core/` — The Brain

---

### `app/core/patient_context.py`
**Single job:** Take all 5 types of input (symptoms, X-ray, body photo, prescription, patient profile) and merge them into one unified `PatientContext` object — running everything in parallel so it's fast.

- **Input:** Optional symptoms text, patient profile object, optional image bytes for X-ray / body photo / prescription
- **Output:** A `PatientContext` object with all findings merged, risk flags calculated, and a confidence score
- **Key functions:**
  - `build_patient_context()` — the main function; fires all 4 sub-tasks simultaneously using `asyncio.gather`
  - `_process_symptoms(text)` — calls NLP pipeline to extract and normalize symptoms from free text
  - `_process_xray(bytes)` — uploads X-ray to S3, runs CLAHE preprocessing (actual diagnosis is Module 4)
  - `_process_body_photo(bytes)` — sends image to Bedrock AI for visual findings
  - `_process_prescription(bytes)` — uploads prescription to S3, sends to Textract, parses medicines
- **Key data classes:**
  - `PatientContext` — the final merged object (session ID, all findings, risk flags, confidence)
  - `SymptomEntity` — one extracted symptom with its canonical name, negation flag, and duration
  - `XrayResult` — S3 key + initial findings for the uploaded X-ray
- **Connects to:** `modules/nlp/preprocessor.py`, `modules/nlp/symptom_normalizer.py`, `modules/image/image_preprocessor.py`, `services/s3_service.py`, `services/bedrock_service.py`, `modules/ocr/textract_handler.py`
- **Plain English:** A 55-year-old male with chest pain submits symptoms text + an X-ray photo. This file simultaneously: (1) extracts "chest pain" from the text, (2) uploads the X-ray to S3, (3) calculates risk flags (`age_over_50`, `cardiac_risk_critical`). All 3 happen at the same time, not one after another, so the user doesn't wait 3x longer.

---

### `app/core/response_builder.py`
**Single job:** Formats the final RAG diagnosis and doctor results into the standard API response structure.

- **Input:** `PatientContext`, `Diagnosis`, `Urgency`, list of `DoctorResult`
- **Output:** `AnalyzeResponse`
- **Plain English:** Packages everything into the final JSON envelope that the frontend expects.

---

## `app/models/` — Data Shapes

---

### `app/models/request_models.py`
**Single job:** Define exactly what a valid request must look like. Pydantic automatically rejects anything that doesn't fit.

- **Input:** Raw dictionaries from the API
- **Output:** Validated Python objects
- **Key classes:**
  - `PatientProfile` — name, age, gender, conditions, smoking status, activity level, etc.
  - `LocationData` — latitude, longitude, optional city name
  - `SmokingStatus` — enum: `never`, `former`, `current`
  - `ActivityLevel` — enum: `sedentary`, `light`, `moderate`, `active`
- **Connects to:** `analyze.py`, `patient_context.py`
- **Plain English:** If someone submits `age: -5`, Pydantic catches it here and returns a 422 error before any AI code runs. It's the bouncer at the door.

---

### `app/models/response_models.py`
**Single job:** Define what the API response looks like so the frontend always gets a predictable structure.

- **Key classes:**
  - `AnalyzeResponse` — the main response: session ID, risk flags, symptoms extracted, confidence, plus optional diagnosis/urgency for Module 3
  - `Diagnosis` — condition name, confidence, explanation, severity, specialist needed (Module 3)
  - `Urgency` — urgency level, action plan, whether to call emergency (Module 3)
  - `DoctorResult` — doctor name, specialty, hospital, rating, distance (Module 3/4)
  - `SeverityLevel` — enum: `low`, `moderate`, `urgent`, `emergency`
- **Connects to:** `analyze.py`

---

## `app/modules/` — AI Tools

---

### `app/modules/nlp/preprocessor.py`
**Single job:** Take a patient's free-text description ("I have chest pain and high fever") and extract structured medical entities from it using scispaCy NLP models.

- **Input:** A string of symptom text
- **Output:** A list of dictionaries, each with an `entity` (symptom name), `negated` (True/False), and `duration`
- **Key functions:**
  - `extract_symptoms(text)` — main function; runs text through scispaCy NER, detects negations ("no chest pain"), and pulls out durations ("for 3 days")
  - `_load_nlp_model()` — loads the scispaCy `en_core_sci_sm` model (only once, cached)
- **Connects to:** `core/patient_context.py` (called by `_process_symptoms`)
- **Plain English:** If a patient types "I have chest pain but no fever for 2 days", this file returns: `[{"entity": "chest pain", "negated": False, "duration": None}, {"entity": "fever", "negated": True}]`

---

### `app/modules/nlp/symptom_normalizer.py`
**Single job:** Convert colloquial or Hinglish symptom names into standard medical terms using a synonym dictionary.

- **Input:** A list of symptom entity dictionaries
- **Output:** The same list but with `canonical_form` filled in (e.g. "bukhar" → "fever")
- **Key functions:**
  - `normalize_all(entities)` — loops through entities, looks each up in the synonym dictionary
  - `normalize_symptom(name)` — normalizes a single symptom name
- **Connects to:** `core/patient_context.py`, `modules/nlp/symptom_synonyms.json`
- **Plain English:** Indian patients often say "bukhar" instead of "fever" or "sar dard" instead of "headache". This file translates those into the standard medical terms that the AI model understands.

---

### `app/modules/nlp/symptom_synonyms.json`
**Single job:** A big dictionary mapping 200+ colloquial, Hinglish, and alternate symptom names to their canonical medical forms.

- **Example:** `"pet dard"` → `"abdominal pain"`, `"ulti"` → `"vomiting"`
- **Connects to:** `symptom_normalizer.py`

---

### `app/modules/image/image_preprocessor.py`
**Single job:** Prepare medical images (X-rays, photos) for AI analysis — resize, normalize, and enhance them.

- **Input:** Raw image bytes
- **Output:** Processed image tensor (for X-rays) or base64 string (for body photos)
- **Key functions:**
  - `preprocess_xray(image_bytes)` — applies CLAHE contrast enhancement and resizes to 224×224 for the chest X-ray classifier
  - `image_to_base64(image_bytes)` — converts image bytes to base64 string so Bedrock can receive it
- **Connects to:** `core/patient_context.py`, `services/bedrock_service.py`
- **Plain English:** Raw X-ray images are often dark and low-contrast. CLAHE makes the lung structures much clearer before the AI classifier sees them. Like applying a filter to make things easier to see.

---

### `app/modules/ocr/textract_handler.py`
**Single job:** Read a photo of a prescription and extract the medicines, doctor name, and diagnosis using AWS Textract (OCR).

- **Input:** Raw image bytes of a prescription photo
- **Output:** Dictionary with `raw_text`, `medicines` list, `doctor_name`, `diagnosis_text`, and `extraction_confidence`
- **Key functions:**
  - `extract_prescription(image_bytes)` — uploads image to S3, calls Textract `analyze_document`, parses the blocks to find drug names/dosages, cleans up S3 file afterwards
- **Connects to:** `services/s3_service.py` (upload + delete), `core/patient_context.py`
- **Plain English:** A patient photographs their old prescription. This file uploads it to S3, asks Textract to read the text, then hunts through the lines looking for patterns like "Tab 500mg TDS" to identify medicines and their dosages.

---

### `app/modules/ml/` (symptom_classifier.py, severity_scorer.py)
**Single job:** Placeholder files for the ML-based symptom classifier and severity scorer. *(Implemented in Module 4)*

---

### `app/modules/doctors/` (finder.py, specialty_mapper.py)
**Single job:** Match a patient's condition to the right type of specialist (e.g., "Cardiologist"), then find actual doctors nearby.

- **Input:** Diagnosis condition or body part
- **Output:** Doctor details (name, hospital, rating)
- **Connects to:** DynamoDB (mock hospital database)
- **Plain English:** Recommends "Dr. Sharma at Apollo" based on the heart condition found by the AI.

---

### `app/modules/rag/` (chain.py, retriever.py, query_builder.py)
**Single job:** The core medical brain. Takes the symptoms, searches the medical knowledge base (Pinecone) for facts, and asks Amazon Bedrock to generate a safe diagnosis.

- **`query_builder.py`**: Translates the patient's symptoms into a search query.
- **`retriever.py`**: Embeds the query using BioSentBERT and searches Pinecone for the top 5 medical facts.
- **`chain.py`**: Combines the facts + patient data into a strict prompt for Bedrock Nova Lite, ensuring no hallucinations.
- **Plain English:** Instead of letting the AI guess, this pipeline forces the AI to read an actual medical textbook (Pinecone) before answering.

---

## `app/services/` — External Services

---

### `app/services/bedrock_service.py`
**Single job:** Send a body photo to Amazon Bedrock (Claude model) and get back a structured JSON description of visible medical findings.

- **Input:** Raw image bytes of a body part photo
- **Output:** Dictionary with `findings` list, `confidence`, `body_part_detected`, `requires_urgent_attention`
- **Key functions:**
  - `analyze_body_photo(image_bytes)` — converts image to base64, builds the Claude message payload, calls Bedrock, parses JSON response
  - `_invoke_with_retry(client, body)` — retries up to 3 times with exponential backoff if AWS is throttling
- **Connects to:** `core/patient_context.py`, `modules/image/image_preprocessor.py`, `config.py`
- **Plain English:** A patient uploads a photo of a swollen ankle. This file sends it to Claude (via Bedrock) with a strict medical prompt saying "describe only visible findings, never diagnose". Claude replies with structured JSON like `{"finding": "swelling", "location": "left ankle", "severity": "moderate"}`.

---

### `app/services/s3_service.py`
**Single job:** Upload files to and delete files from the Aarogya AI S3 bucket (`aarogya-uploads`).

- **Input:** File bytes + filename + content type
- **Output:** The S3 key (file path) where the file was stored
- **Key functions:**
  - `upload_file(bytes, filename, content_type)` — uploads to S3, returns the key
  - `delete_file(s3_key)` — deletes a file from S3 (used after Textract finishes reading a prescription)
- **Connects to:** `core/patient_context.py`, `modules/ocr/textract_handler.py`
- **Plain English:** When a patient uploads an X-ray, this service stores it safely in our AWS S3 bucket with a unique random name so no two files clash.

---

### `app/services/dynamodb_service.py`
**Single job:** Save and load patient session data from DynamoDB so the frontend can retrieve past diagnoses.

- **Input:** `AnalyzeResponse` or `session_id`
- **Output:** Success status or retrieved session data
- **Plain English:** Stores the final medical report so the patient can view it later. Automatically deletes it after 30 days for privacy.

---

## `backend/tests/`

---

### `backend/tests/test_analyze.py`
**Single job:** Automatically verify that the `/analyze` endpoint works correctly for 5 different scenarios — without actually calling AWS.

- **Key tests:**
  - `test_text_only_input` — symptoms text for a 55-year-old smoker → must flag `cardiac_risk_critical`
  - `test_with_xray_upload` — uploading an X-ray → must appear in `inputs_processed`, confidence ≥ 0.5
  - `test_negation_handling` — "no chest pain" → `cardiac_risk_critical` must NOT be flagged
  - `test_invalid_patient_age` — age of -1 → must return HTTP 422
  - `test_no_input_returns_400` — no symptoms or files → must return HTTP 400
- **How AWS is faked:** `mock_aws_services` fixture patches S3, Textract, Bedrock, and NLP so tests run instantly with no real AWS calls
- **Connects to:** `api/routes/analyze.py`, `core/patient_context.py`
