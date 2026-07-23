# Aarogya AI 🏥

> **आरोग्य** (Aarogya) — Sanskrit for *health*

A multimodal medical intelligence system that ingests symptoms, X-rays, body photos, prescriptions, and a personal health profile — then delivers grounded diagnosis, urgency scoring, and nearby specialist recommendations fully personalized to the user.

**Built by**: Aakash Kumawat — JECRC University, Jaipur  
**Stack**: FastAPI · AWS Bedrock · LangChain · Pinecone · XGBoost · ResNet-50  
**Frontend**: Lovable (React + TypeScript)  
**Timeline**: 12 Weeks · 6 Modules

---

## Project Structure

```
Aarogya_AI/
├── backend/
│   ├── app/
│   │   ├── api/routes/       # FastAPI route handlers
│   │   ├── core/             # PatientContext, ResponseBuilder
│   │   ├── modules/          # NLP, Image, OCR, RAG, ML, Doctors
│   │   ├── services/         # AWS S3, DynamoDB, Bedrock wrappers
│   │   └── models/           # Pydantic request/response schemas
│   ├── ml_models/            # Trained ONNX model artifacts
│   ├── notebooks/            # EDA + training notebooks
│   ├── scripts/              # ETL + seeding scripts
│   └── tests/                # pytest suite
├── mediassist/               # Project planning docs (HTML)
├── .env.example              # Environment variable template
├── pyproject.toml            # Tool configuration
└── README.md
```

## Modules

| # | Module | Weeks | Status |
|---|--------|-------|--------|
| 1 | Project Setup & FastAPI Skeleton | 1–2 | 🟡 In Progress |
| 2 | Multimodal Input Handler | 3–4 | 🔒 Upcoming |
| 3 | RAG Pipeline + Knowledge Base | 5–6 | 🔒 Upcoming |
| 4 | Data Science Models | 7–8 | 🔒 Upcoming |
| 5 | Doctor Finder + Output Layer | 9–10 | 🔒 Upcoming |
| 6 | Testing, Deployment & Polish | 11–12 | 🔒 Upcoming |

## Tech Stack

- **Backend**: FastAPI + Mangum (AWS Lambda)
- **LLM/AI**: AWS Bedrock Nova Pro, LangChain, Pinecone
- **ML**: XGBoost (disease classification), ResNet-50 (X-ray), LightGBM (urgency)
- **NLP**: spaCy, scispaCy, BioSentBERT
- **AWS**: Lambda, S3, DynamoDB, SageMaker, Textract
- **Frontend**: Lovable (React + TypeScript)

## Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/Aakash-Kumawat-621/Aarogya_AI.git
cd Aarogya_AI

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r backend/requirements.txt

# 4. Set up environment variables
cp .env.example .env
# Fill in your actual credentials in .env

# 5. Run locally
cd backend
uvicorn app.main:app --reload --port 8000
```

## API

- `GET /api/v1/health` — Health check
- `POST /api/v1/analyze` — Main multimodal analysis endpoint
- `GET /api/v1/doctors/search` — Doctor finder
- `GET /api/v1/history/{user_id}` — Session history
- `POST /api/v1/feedback` — Submit feedback

---

*This project is for educational/portfolio purposes. Always consult a qualified medical professional for real health concerns.*
