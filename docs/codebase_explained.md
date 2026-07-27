# Aarogya AI — Backend Codebase Explained

> A simple, beginner-friendly guide to every Python file inside `backend/app/`.
> Designed for anyone learning Python or exploring the codebase for the first time.

---

## Table of Contents

1. [Application Entrypoint & Configuration](#1-application-entrypoint--configuration)
   - [`backend/app/main.py`](#backendappmainpy)
   - [`backend/app/config.py`](#backendappconfigpy)
2. [Data Models (Schemas)](#2-data-models-schemas)
   - [`backend/app/models/request_models.py`](#backendappmodelsrequest_modelspy)
   - [`backend/app/models/response_models.py`](#backendappmodelsresponse_modelspy)
3. [API Routes (Endpoints)](#3-api-routes-endpoints)
   - [`backend/app/api/routes/health.py`](#backendappapirouteshealthpy)
   - [`backend/app/api/routes/analyze.py`](#backendappapiroutesanalyzepy)
   - [`backend/app/api/routes/doctors.py`](#backendappapiroutesdoctorspy)
   - [`backend/app/api/routes/history.py`](#backendappapirouteshistorypy)
   - [`backend/app/api/routes/feedback.py`](#backendappapiroutesfeedbackpy)
4. [External Cloud Services](#4-external-cloud-services)
   - [`backend/app/services/s3_service.py`](#backendappservicess3_servicepy)
   - [`backend/app/services/bedrock_service.py`](#backendappservicesbedrock_servicepy)
   - [`backend/app/services/dynamodb_service.py`](#backendappservicesdynamodb_servicepy)
5. [NLP Module (Text Processing)](#5-nlp-module-text-processing)
   - [`backend/app/modules/nlp/preprocessor.py`](#backendappmodulesnlppreprocessorpy)
   - [`backend/app/modules/nlp/symptom_normalizer.py`](#backendappmodulesnlpsymptom_normalizerpy)
6. [Image Module (Medical Vision & Preprocessing)](#6-image-module-medical-vision--preprocessing)
   - [`backend/app/modules/image/image_preprocessor.py`](#backendappmodulesimageimage_preprocessorpy)
   - [`backend/app/modules/image/xray_classifier.py`](#backendappmodulesimagexray_classifierpy)
7. [OCR Module (Prescription Extraction)](#7-ocr-module-prescription-extraction)
   - [`backend/app/modules/ocr/textract_handler.py`](#backendappmodulesocrtextract_handlerpy)
8. [Doctors & Location Module](#8-doctors--location-module)
   - [`backend/app/modules/doctors/finder.py`](#backendappmodulesdoctorsfinderpy)
   - [`backend/app/modules/doctors/specialty_mapper.py`](#backendappmodulesdoctorsspecialty_mapperpy)
9. [Machine Learning & Severity Module](#9-machine-learning--severity-module)
   - [`backend/app/modules/ml/severity_scorer.py`](#backendappmodulesmlseverity_scorerpy)
   - [`backend/app/modules/ml/symptom_classifier.py`](#backendappmodulesmlsymptom_classifierpy)
10. [RAG Module (Medical Knowledge Search)](#10-rag-module-medical-knowledge-search)
    - [`backend/app/modules/rag/chain.py`](#backendappmodulesragchainpy)
    - [`backend/app/modules/rag/query_builder.py`](#backendappmodulesragquery_builderpy)
    - [`backend/app/modules/rag/retriever.py`](#backendappmodulesragretrieverpy)
11. [Core Engine (Context & Response Aggregation)](#11-core-engine-context--response-aggregation)
    - [`backend/app/core/patient_context.py`](#backendappcorepatient_contextpy)
    - [`backend/app/core/response_builder.py`](#backendappcoreresponse_builderpy)

---

## 1. Application Entrypoint & Configuration

### `backend/app/main.py`
- **Single Job**: Starts the web server and hooks up all API routes together.
- **Input**: HTTP web requests coming from browsers, frontend, or AWS Lambda triggers.
- **Output**: JSON HTTP responses sent back to the client.
- **Key functions**:
  - `startup_event()`: Runs when the app boots up and logs that the server is active.
- **Connects to**: 
  - Imports all routes from `app.api.routes` (`health`, `analyze`, `doctors`, `history`, `feedback`).
  - Wrapped by `mangum` to make FastAPI run inside AWS Lambda functions.
- **Plain English example**: "When a user visits `https://api.aarogya.ai/api/v1/health`, this file hears the request, sends it to `health.py`, and returns the JSON answer."

---

### `backend/app/config.py`
- **Single Job**: Loads configuration settings and secret API keys from the `.env` file.
- **Input**: Environment variables and local `.env` settings file.
- **Output**: A global `settings` Python object holding configuration values.
- **Key functions**:
  - `is_local`: Helper property that returns `True` if you are using real AWS access keys starting with `AKIA`.
  - `is_production`: Helper property that returns `True` if `APP_ENV` is set to `"production"`.
- **Connects to**: 
  - Called by `s3_service.py`, `bedrock_service.py`, `preprocessor.py`, and almost every module that needs cloud keys or table names.
- **Plain English example**: "When S3 upload service needs to know which bucket to upload images to, it reads `settings.S3_BUCKET_NAME` from this file."

---

## 2. Data Models (Schemas)

### `backend/app/models/request_models.py`
- **Single Job**: Defines and validates the structure of data sent by users to the server.
- **Input**: Raw JSON dictionary inputs sent from forms or mobile apps.
- **Output**: Validated Python Pydantic model objects (e.g., `PatientProfile`).
- **Key functions**:
  - `PatientProfile`: Blueprint holding patient demographics (age, gender), body metrics, medical conditions, allergies, and lifestyle factors.
  - `LocationData`: Blueprint validating latitude, longitude, and city name.
  - `AnalyzeRequest`: Schema ensuring at least one symptom or image input is provided.
- **Connects to**: 
  - Used by `app/api/routes/analyze.py` to validate user profile data.
- **Plain English example**: "If a user enters an invalid age like `-5` or `300`, this file catches the error immediately and rejects the request before it reaches the backend algorithms."

---

### `backend/app/models/response_models.py`
- **Single Job**: Defines the exact JSON layout of answers returned by the API to the frontend.
- **Input**: Python dictionaries containing calculated diagnosis, urgency, and recommended doctors.
- **Output**: Formatted and type-checked JSON response models.
- **Key functions**:
  - `Diagnosis`: Blueprint for disease name, confidence score, medical explanation, and web citations.
  - `Urgency`: Blueprint specifying severity level, action plan checklist, and emergency flags.
  - `DoctorResult`: Blueprint for nearby doctor details (name, specialty, rating, distance).
  - `AnalyzeResponse`: The master response blueprint combining diagnosis, urgency, doctor list, and legal disclaimers.
- **Connects to**: 
  - Used by `app/api/routes/analyze.py` and `app/core/response_builder.py`.
- **Plain English example**: "When the AI finishes analyzing symptoms, this file formats the final diagnosis, urgency level, and doctor list into a neat JSON packet that the frontend can render."

---

## 3. API Routes (Endpoints)

### `backend/app/api/routes/health.py`
- **Single Job**: Checks if the API server is alive and functioning correctly.
- **Input**: HTTP `GET /api/v1/health` requests.
- **Output**: JSON status dictionary `{"status": "ok", "service": "aarogya-ai", "version": "0.1.0"}`.
- **Key functions**:
  - `health_check()`: Liveness handler returning simple status confirmation.
- **Connects to**: 
  - Called by AWS Lambda, load balancers, and frontend health monitors.
- **Plain English example**: "AWS pings this file every 5 minutes to verify the Aarogya AI service is online and ready for traffic."

---

### `backend/app/api/routes/analyze.py`
- **Single Job**: Receives patient symptoms, medical photos, and profile data to trigger analysis.
- **Input**: `multipart/form-data` containing text strings (`symptoms_text`, `patient`, `location`) and optional uploaded files (`xray_image`, `body_photo`, `prescription`).
- **Output**: `AnalyzeResponse` JSON object containing diagnosis, recommendations, and emergency flags.
- **Key functions**:
  - `analyze_symptoms()`: Primary API endpoint handler parsing inputs, performing validations, and returning analysis output.
- **Connects to**: 
  - Imports `PatientProfile`, `LocationData` from `app.models.request_models`.
  - Imports `AnalyzeResponse` from `app.models.response_models`.
  - Will connect to `preprocessor.py`, `image_preprocessor.py`, `patient_context.py` in Module 2 Step S11.
- **Plain English example**: "When a patient submits their symptom text along with a chest X-ray image, this file receives both, validates the form data, and orchestrates the AI processing pipeline."

---

### `backend/app/api/routes/doctors.py`
- **Single Job**: Provides API endpoints to search for nearby doctors and view medical specialties.
- **Input**: HTTP `GET /api/v1/doctors/search` and `GET /api/v1/doctors/specialties`.
- **Output**: JSON dictionary of matching doctors or specialty lists.
- **Key functions**:
  - `search_doctors()`: Search endpoint for locating nearby medical specialists.
  - `list_specialties()`: Endpoint returning supported doctor categories.
- **Connects to**: 
  - Will connect to `app/modules/doctors/finder.py` in Module 5.
- **Plain English example**: "When a user needs to find a Neurologist near their city, the frontend calls this endpoint to get a list of rated specialists."

---

### `backend/app/api/routes/history.py`
- **Single Job**: Retrieves previous symptom analysis sessions for a given patient.
- **Input**: HTTP `GET /api/v1/history/{user_id}`.
- **Output**: JSON list of past medical checks.
- **Key functions**:
  - `get_history()`: Route handler fetching user history.
- **Connects to**: 
  - Will connect to `app/services/dynamodb_service.py` in Module 5.
- **Plain English example**: "When a user opens their profile page to look at their diagnostic checkup from last week, this file fetches their records from the database."

---

### `backend/app/api/routes/feedback.py`
- **Single Job**: Collects user feedback on AI diagnostic accuracy to improve the model.
- **Input**: HTTP `POST /api/v1/feedback` with ratings and user comments.
- **Output**: JSON acknowledgement response.
- **Key functions**:
  - `submit_feedback()`: Route handler accepting feedback submissions.
- **Connects to**: 
  - Will connect to `app/services/dynamodb_service.py` in Module 5.
- **Plain English example**: "If a user clicks 'Helpful' or leaves a comment on their AI diagnosis, this file stores their feedback in DynamoDB."

---

## 4. External Cloud Services

### `backend/app/services/s3_service.py`
- **Single Job**: Manages uploading, downloading, and deleting files stored in AWS S3 buckets.
- **Input**: Raw file bytes, filenames, content MIME types, or S3 object key strings.
- **Output**: S3 storage keys, downloaded file bytes, presigned URLs, or boolean deletion flags.
- **Key functions**:
  - `upload_file()`: Uploads raw binary image data into the AWS S3 `aarogya-uploads` bucket with a unique UUID key.
  - `download_file()`: Retrieves file contents from AWS S3 as raw bytes.
  - `generate_presigned_url()`: Creates a secure, temporary web link so users can view or upload files directly.
  - `delete_file()`: Removes a specified object from the S3 bucket.
  - `file_exists()`: Checks if a given object exists in the S3 bucket.
- **Connects to**: 
  - Called by `image_preprocessor.py`, `textract_handler.py`, and `analyze.py`.
  - Uses `app.config.settings` for credentials and bucket names.
- **Plain English example**: "When a user uploads a photo of their rash, this file saves it securely inside AWS S3 and gives back a unique file link like `uploads/550e84-rash.jpg`."

---

### `backend/app/services/bedrock_service.py`
- **Single Job**: Handles communication with AWS Bedrock generative AI models (Amazon Nova / Claude).
- **Input**: Text prompts or base64-encoded images.
- **Output**: AI-generated text responses or medical image visual findings.
- **Key functions**:
  - *(Stub file — to be implemented in Module 2 Step S8 for visual analysis & Module 3 for LLM diagnostic synthesis)*.
- **Connects to**: 
  - Will connect to `app/modules/image/image_preprocessor.py` and `app/modules/rag/chain.py`.
- **Plain English example**: "This file sends a body photo to AWS Bedrock's Vision AI to ask: 'Describe any visible skin redness or swelling in this image.'"

---

### `backend/app/services/dynamodb_service.py`
- **Single Job**: Reads and writes session history and patient profiles to AWS DynamoDB database tables.
- **Input**: Session IDs, user IDs, patient profile JSONs, or analysis records.
- **Output**: Saved status confirmations or retrieved database records.
- **Key functions**:
  - *(Stub file — to be implemented in Module 3 & 5)*.
- **Connects to**: 
  - Will connect to `app/api/routes/history.py` and `app/api/routes/feedback.py`.
- **Plain English example**: "After an analysis is complete, this file saves the patient's record into AWS DynamoDB so they can view it later."

---

## 5. NLP Module (Text Processing)

### `backend/app/modules/nlp/preprocessor.py`
- **Single Job**: Extracts clinical entities (symptoms, severity, duration, negation, uncertainty) from free text symptoms.
- **Input**: Patient's free text input string (e.g., `"I have severe chest pain and fever for 3 days. No cough."`).
- **Output**: Structured dictionary containing extracted symptom entities, medical history, duration categories, and negation flags.
- **Key functions**:
  - `extract_symptoms()`: Primary function running scispaCy biomedical models to detect symptoms, negation (`"no chest pain"`), uncertainty (`"possible pneumonia"`), and duration (`"acute"`/`"chronic"`).
  - `detect_disease_history()`: Regex extractor identifying past conditions like `"history of diabetes"` or `"diagnosed with hypertension"`.
- **Connects to**: 
  - Called by `symptom_normalizer.py` and `patient_context.py`.
  - Uses medical NLP models `en_ner_bc5cdr_md` and `en_core_sci_sm`.
- **Plain English example**: "When a patient types 'I have no fever but severe headache for 2 weeks', this file detects that 'fever' is negated (False), 'headache' is severe, and the duration is subacute."

---

### `backend/app/modules/nlp/symptom_normalizer.py`
- **Single Job**: Maps extracted symptom phrases to standardized medical names using exact and fuzzy matching.
- **Input**: Raw symptom strings or entity dictionary lists (e.g., `"chest ache"`, `"saans nahi aa rahi"`, `"chset pain"`).
- **Output**: Normalized canonical symptom names (e.g., `"chest pain"`, `"dyspnea"`).
- **Key functions**:
  - `normalize_symptom()`: Looks up text against `symptom_synonyms.json` using exact match, or falls back to fuzzy string matching (via RapidFuzz).
  - `normalize_all()`: Processes a list of symptom entity dictionaries and updates their `canonical_form` fields.
- **Connects to**: 
  - Imports dictionary mappings from `symptom_synonyms.json`.
  - Called by `patient_context.py` after `preprocessor.py` runs.
- **Plain English example**: "If an Indian patient types 'saans nahi aa rahi' or a user misspells 'chset pain', this file converts both into official medical search terms like 'dyspnea' and 'chest pain'."

---

## 6. Image Module (Medical Vision & Preprocessing)

### `backend/app/modules/image/image_preprocessor.py`
- **Single Job**: Preprocesses uploaded medical images (resizing, contrast enhancement, ImageNet normalization, base64 encoding).
- **Input**: Raw image bytes from uploaded JPEG/PNG/X-ray files.
- **Output**: Preprocessed float32 NumPy arrays (224x224x3) or base64 string encodings.
- **Key functions**:
  - `preprocess_for_model()`: Decodes image, resizes to 224x224, and normalizes pixel values using standard ImageNet mean & std.
  - `preprocess_xray()`: Enhances X-ray contrast using CLAHE (Contrast Limited Adaptive Histogram Equalization) before resizing and normalizing.
  - `image_to_base64()`: Converts raw image bytes into base64 text for AWS Bedrock Vision API prompts.
- **Connects to**: 
  - Uses `OpenCV` (`cv2`), `Pillow` (`PIL`), and `NumPy`.
  - Called by `xray_classifier.py` and `bedrock_service.py`.
- **Plain English example**: "When a dark X-ray image is uploaded, this file applies contrast enhancement (CLAHE) to reveal subtle lung patterns and converts it into a tensor ready for AI models."

---

### `backend/app/modules/image/xray_classifier.py`
- **Single Job**: Classifies X-ray images to detect abnormalities like Pneumonia or Pneumothorax.
- **Input**: Preprocessed X-ray image tensor array.
- **Output**: Classification labels and confidence scores.
- **Key functions**:
  - *(Stub file — to be implemented in Module 4)*.
- **Connects to**: 
  - Will call `image_preprocessor.py` and feed findings into `patient_context.py`.
- **Plain English example**: "This file runs a PyTorch computer vision model on the preprocessed X-ray tensor to predict if there is a 92% chance of pneumonia."

---

## 7. OCR Module (Prescription Extraction)

### `backend/app/modules/ocr/textract_handler.py`
- **Single Job**: Extracts printed or handwritten drug names and dosages from prescription scans using AWS Textract.
- **Input**: Prescription image bytes or S3 object keys.
- **Output**: List of extracted medication names, dosages, and frequency instructions.
- **Key functions**:
  - *(Stub file — to be implemented in Module 2 Step S7)*.
- **Connects to**: 
  - Calls `app/services/s3_service.py` and AWS Textract API.
  - Feeds extracted medications into `patient_context.py`.
- **Plain English example**: "When a patient uploads a photo of a doctor's handwritten prescription, this file uses AWS Textract OCR to read medication names like 'Amoxicillin 500mg'."

---

## 8. Doctors & Location Module

### `backend/app/modules/doctors/finder.py`
- **Single Job**: Searches Google Places API and medical directories to locate relevant specialists near the user.
- **Input**: Medical specialty required (e.g., `"Cardiologist"`) and user location coordinates (latitude, longitude).
- **Output**: List of nearby hospitals, clinic names, ratings, phone numbers, and distances.
- **Key functions**:
  - *(Stub file — to be implemented in Module 5)*.
- **Connects to**: 
  - Called by `app/api/routes/doctors.py`.
- **Plain English example**: "If the AI determines the patient needs a Cardiologist, this file queries Google Places to find top-rated heart specialists within 5 km of the user."

---

### `backend/app/modules/doctors/specialty_mapper.py`
- **Single Job**: Maps diagnosed medical conditions to the correct medical doctor specialty.
- **Input**: Diagnosed condition string (e.g., `"Migraine"`, `"Pneumonia"`).
- **Output**: Required specialist title (e.g., `"Neurologist"`, `"Pulmonologist"`).
- **Key functions**:
  - *(Stub file — to be implemented in Module 5)*.
- **Connects to**: 
  - Used by `app/core/response_builder.py` and `app/modules/doctors/finder.py`.
- **Plain English example**: "This file knows that if the diagnosed condition is 'Asthma', the patient should be directed to a 'Pulmonologist'."

---

## 9. Machine Learning & Severity Module

### `backend/app/modules/ml/severity_scorer.py`
- **Single Job**: Calculates clinical risk level (Low, Moderate, Urgent, Emergency) using ML models and vital signs.
- **Input**: Symptoms list, age, vitals, and identified medical conditions.
- **Output**: Severity score and emergency action recommendations.
- **Key functions**:
  - *(Stub file — to be implemented in Module 4)*.
- **Connects to**: 
  - Reads from `patient_context.py` and provides risk scores to `response_builder.py`.
- **Plain English example**: "If a 65-year-old patient reports severe chest pain radiating to the left arm, this file flags the situation as an IMMEDIATE EMERGENCY."

---

### `backend/app/modules/ml/symptom_classifier.py`
- **Single Job**: Runs XGBoost / LightGBM classical machine learning models to predict disease probability distributions.
- **Input**: Vectorized feature representation of patient symptoms and medical history.
- **Output**: Predicted condition candidates with probabilities.
- **Key functions**:
  - *(Stub file — to be implemented in Module 4)*.
- **Connects to**: 
  - Reads from `patient_context.py` and feeds probabilities to the RAG knowledge retriever.
- **Plain English example**: "This file evaluates tabular symptom features against trained ML algorithms to narrow down potential causes."

---

## 10. RAG Module (Medical Knowledge Search)

### `backend/app/modules/rag/query_builder.py`
- **Single Job**: Builds optimized vector search queries from patient context for Pinecone vector database lookups.
- **Input**: Patient context, extracted symptoms, and age group.
- **Output**: Dense vector embedding search query.
- **Key functions**:
  - *(Stub file — to be implemented in Module 3)*.
- **Connects to**: 
  - Called by `retriever.py`.
- **Plain English example**: "This file converts the patient's symptoms into a search query string to look up matching medical textbook guidelines in Pinecone."

---

### `backend/app/modules/rag/retriever.py`
- **Single Job**: Queries Pinecone vector index to fetch relevant medical evidence and clinical guidelines.
- **Input**: Search vector query from `query_builder.py`.
- **Output**: Top matching medical literature chunks and citation links.
- **Key functions**:
  - *(Stub file — to be implemented in Module 3)*.
- **Connects to**: 
  - Communicates with Pinecone Vector Database and feeds evidence to `chain.py`.
- **Plain English example**: "This file searches millions of medical articles in Pinecone and returns trusted reference links from MedlinePlus or WHO."

---

### `backend/app/modules/rag/chain.py`
- **Single Job**: Combines retrieved medical evidence, patient context, and Bedrock LLM to synthesize final clinical reasoning.
- **Input**: Retrieved knowledge chunks and merged `PatientContext`.
- **Output**: Final structured diagnosis explanation and safe medical advice.
- **Key functions**:
  - *(Stub file — to be implemented in Module 3)*.
- **Connects to**: 
  - Calls `retriever.py` and `bedrock_service.py`, feeding output to `response_builder.py`.
- **Plain English example**: "This file takes the evidence retrieved from Pinecone and asks the LLM to write a clear, patient-friendly explanation for the diagnosis."

---

## 11. Core Engine (Context & Response Aggregation)

### `backend/app/core/patient_context.py`
- **Single Job**: Combines all 5 input modalities (Text, X-ray, Body Photo, Prescription, Profile) into a single master `PatientContext` object.
- **Input**: Outputs from `preprocessor.py`, `image_preprocessor.py`, `textract_handler.py`, and `request_models.py`.
- **Output**: Unified `PatientContext` object.
- **Key functions**:
  - *(Stub file — full implementation in Module 2 Step S10)*.
- **Connects to**: 
  - Called by `analyze.py`; consumed by RAG, ML classifiers, and severity scorers.
- **Plain English example**: "Whether the patient typed text, uploaded an X-ray, or sent a prescription photo, this file merges all information into one master patient file."

---

### `backend/app/core/response_builder.py`
- **Single Job**: Packages diagnostic findings, urgency level, recommendations, and disclaimers into the final `AnalyzeResponse`.
- **Input**: Outputs from RAG chain, severity scorer, doctor finder, and patient context.
- **Output**: Final `AnalyzeResponse` Pydantic object ready for API return.
- **Key functions**:
  - *(Stub file — full implementation in Module 5)*.
- **Connects to**: 
  - Called by `app/api/routes/analyze.py`.
- **Plain English example**: "This file puts the bow on the package—it takes the diagnosis, urgency score, doctor recommendations, and mandatory legal disclaimers, assembling them into the final JSON response sent to the frontend."
