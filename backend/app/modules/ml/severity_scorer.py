"""
backend/app/modules/ml/severity_scorer.py

LightGBM urgency severity scorer — loads ONNX model from S3 (cached in memory).
Maps PatientContext + XGBoost predictions → urgency level (LOW/MODERATE/URGENT/EMERGENCY).

Emergency recall target: ≥ 0.95 (threshold tuned post-training).

Used in: backend/app/api/routes/analyze.py
"""

import json
import logging
import threading
from pathlib import Path
from typing import Optional

import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)

# ── Singleton cache ────────────────────────────────────────────────────────
_lock = threading.Lock()
_ort_session = None       # ONNX Runtime InferenceSession
_thresholds = None        # Dict: {"emergency_threshold": float, ...}
_feature_names = None     # List[str]: expected feature order

MODEL_S3_KEY = "models/severity_scorer.onnx"
THRESHOLDS_S3_KEY = "models/severity_thresholds.json"
FEATURES_S3_KEY = "models/severity_feature_names.json"
LOCAL_DIR = Path("/tmp/mediassist_models")

# Urgency level labels (must match training ordinal encoding)
URGENCY_LABELS = {0: "low", 1: "moderate", 2: "urgent", 3: "emergency"}

# Urgency action plans (shown to patient in API response)
URGENCY_ACTIONS = {
    "low": [
        "Rest and stay hydrated",
        "Take OTC medication if needed",
        "Monitor symptoms — see a doctor within 1 week if not improving",
    ],
    "moderate": [
        "Book a doctor's appointment within 24–48 hours",
        "Avoid strenuous activity",
        "Take prescribed or OTC medication as directed",
        "Return to emergency if symptoms worsen significantly",
    ],
    "urgent": [
        "Visit urgent care or emergency outpatient TODAY",
        "Do not delay — symptoms require same-day evaluation",
        "Have someone accompany you if possible",
        "Bring a list of your current medications",
    ],
    "emergency": [
        "CALL 112 (Emergency) IMMEDIATELY",
        "Do NOT drive yourself — call an ambulance",
        "Stay calm and keep the patient still",
        "Do not eat or drink anything until assessed by a doctor",
    ],
}


def _load_models() -> None:
    """Download severity models from S3 and cache in memory."""
    global _ort_session, _thresholds, _feature_names

    with _lock:
        if _ort_session is not None:
            return

        LOCAL_DIR.mkdir(parents=True, exist_ok=True)

        try:
            import boto3
            import onnxruntime as ort

            s3 = boto3.client(
                "s3",
                region_name=settings.AWS_REGION,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            )
            bucket = settings.S3_BUCKET_NAME

            onnx_path = LOCAL_DIR / "severity_scorer.onnx"
            if not onnx_path.exists():
                logger.info(f"Downloading severity ONNX from s3://{bucket}/{MODEL_S3_KEY}")
                s3.download_file(bucket, MODEL_S3_KEY, str(onnx_path))

            thresh_path = LOCAL_DIR / "severity_thresholds.json"
            if not thresh_path.exists():
                logger.info(f"Downloading thresholds from s3://{bucket}/{THRESHOLDS_S3_KEY}")
                s3.download_file(bucket, THRESHOLDS_S3_KEY, str(thresh_path))

            feat_path = LOCAL_DIR / "severity_feature_names.json"
            if not feat_path.exists():
                try:
                    logger.info(f"Downloading severity feature names from s3://{bucket}/{FEATURES_S3_KEY}")
                    s3.download_file(bucket, FEATURES_S3_KEY, str(feat_path))
                except Exception:
                    logger.warning("Severity feature names not found in S3 — will use positional features")

            _ort_session = ort.InferenceSession(
                str(onnx_path), providers=["CPUExecutionProvider"]
            )
            with open(thresh_path) as f:
                _thresholds = json.load(f)

            if feat_path.exists():
                with open(feat_path) as f:
                    _feature_names = json.load(f)

            logger.info(
                f"LightGBM severity scorer loaded ✓ "
                f"(emergency_threshold={_thresholds.get('emergency_threshold', 0.5):.3f})"
            )

        except Exception as e:
            logger.warning(
                f"Could not load LightGBM severity model ({e}). "
                "Scorer will fall back to rule-based urgency."
            )
            _ort_session = None


def _build_disease_encoding_map() -> dict:
    """
    Build a disease → integer mapping consistent with the XGBoost label encoder.
    Returns a dict: {disease_name_lower: int_index}.
    Reads from the cached label_encoder in symptom_classifier (already loaded).
    """
    try:
        from app.modules.ml.symptom_classifier import _label_encoder
        if _label_encoder:
            return {disease.lower(): idx for idx, disease in enumerate(_label_encoder)}
    except Exception:
        pass
    return {}


def _build_severity_features(context, xgb_predictions: list[dict]) -> np.ndarray:
    """
    Build feature vector for severity scorer.

    Feature set:
    - Symptom features (same columns as XGBoost, loaded from feature_names.json)
    - Demographic features (age_bin, gender_encoded, bmi_category)
    - Medical history (has_diabetes, has_hypertension, etc.)
    - Lifestyle risk (smoking_encoded, alcohol_risk, sleep_deficit)
    - Risk multipliers (cardiac_risk_score, etc.)
    - XGBoost top disease (properly encoded) + top probability
    - symptom_count, risk_flag_count, symptom_severity_max
    - nlp_severity_score (from NLP extraction — mild=1, moderate=2, severe=3)
    - duration_category (acute=0, subacute=1, chronic=2, unknown=-1)
    """
    from app.modules.ml.symptom_classifier import _build_feature_vector

    # Reuse the same base feature vector from symptom classifier
    base_vec = _build_feature_vector(context).flatten()

    # ── Additional severity-specific features ─────────────────────────────

    active_symptoms = [s for s in context.symptom_entities if not s.negated]
    symptom_count = len(active_symptoms)
    risk_flag_count = len(context.risk_flags)

    # XGBoost top prediction — use real disease encoding (fixes the =0 bug)
    top_xgb_prob = 0.0
    top_disease_encoded = 0
    if xgb_predictions:
        top_xgb_prob = float(xgb_predictions[0].get("probability", 0.0))
        top_disease_name = xgb_predictions[0].get("disease", "").lower()
        disease_map = _build_disease_encoding_map()
        top_disease_encoded = disease_map.get(top_disease_name, 0)

    # Symptom severity max — count of canonically "severe" symptom names
    severe_symptom_names = {
        "chest_pain", "breathlessness", "high_fever", "vomiting",
        "loss_of_consciousness", "slurred_speech", "weakness_of_one_body_side",
        "coma", "stomach_bleeding", "blood_in_sputum",
    }
    symptom_names_set = {
        s.name.lower().replace(" ", "_") for s in active_symptoms
    }
    symptom_severity_max = len(severe_symptom_names & symptom_names_set)

    # NLP severity score — use the severity field extracted by preprocessor
    # mild → 1, moderate → 2, severe → 3, None → 0
    severity_map = {"mild": 1, "moderate": 2, "severe": 3}
    nlp_severity_score = 0
    for s in active_symptoms:
        sev = getattr(s, "severity", None)
        if sev:
            nlp_severity_score = max(nlp_severity_score, severity_map.get(sev, 0))

    # Duration category from NLP extraction
    # acute=0, subacute=1, chronic=2, unknown=-1
    duration_category_map = {"acute": 0, "subacute": 1, "chronic": 2}
    duration_encoded = -1
    for s in active_symptoms:
        dur_cat = getattr(s, "duration_category", None)
        if dur_cat in duration_category_map:
            # Use the longest (most chronic) duration seen
            duration_encoded = max(duration_encoded, duration_category_map[dur_cat])

    extra = np.array(
        [
            symptom_count,
            risk_flag_count,
            top_xgb_prob,
            top_disease_encoded,
            symptom_severity_max,
            nlp_severity_score,
            duration_encoded,
        ],
        dtype=np.float32,
    )

    return np.concatenate([base_vec, extra]).reshape(1, -1)


def _rule_based_urgency(context) -> str:
    """
    Hard-coded rule-based urgency classifier used when:
    1. ML model is not loaded
    2. As a sanity check / override for EMERGENCY cases

    Emergency triggers (from S7 criteria) — any single trigger → EMERGENCY
    """
    profile = context.patient_profile
    age = getattr(profile, "age", 30)
    smoking = getattr(profile, "smoking", None)
    conditions = [c.lower() for c in getattr(profile, "conditions", []) or []]
    symptom_names = {s.name.lower() for s in context.symptom_entities if not s.negated}
    risk_flags = set(context.risk_flags)

    # ── EMERGENCY triggers ─────────────────────────────────────────────────
    has_chest_pain = any(s in symptom_names for s in ("chest pain", "chest_pain"))
    has_breathlessness = any(s in symptom_names for s in ("breathlessness", "shortness of breath"))
    has_headache = any(s in symptom_names for s in ("headache",))
    is_smoker = smoking == "current"
    is_over_45 = age > 45

    if has_chest_pain and has_breathlessness and (is_over_45 or is_smoker):
        return "emergency"  # Likely ACS

    if has_headache and any(s in symptom_names for s in ("sudden onset", "worst headache")):
        return "emergency"  # Possible SAH

    facial_droop = any(s in symptom_names for s in ("facial droop", "slurred speech", "facial_droop"))
    arm_weakness = any(s in symptom_names for s in ("weakness_of_one_body_side", "arm weakness"))
    if facial_droop or arm_weakness:
        return "emergency"  # Possible stroke

    if "cardiac_risk_critical" in risk_flags and has_chest_pain:
        return "emergency"

    # ── URGENT triggers ────────────────────────────────────────────────────
    has_high_fever = any(s in symptom_names for s in ("high_fever", "high fever"))
    has_rash = any(s in symptom_names for s in ("skin_rash", "red_spots_over_body"))
    has_severe_abdominal = any(s in symptom_names for s in ("abdominal_pain", "stomach_pain"))

    if has_high_fever and has_rash:
        return "urgent"

    if has_severe_abdominal and has_high_fever:
        return "urgent"

    if "age_over_50" in risk_flags and has_breathlessness:
        return "urgent"

    # ── MODERATE triggers ──────────────────────────────────────────────────
    if has_high_fever:
        return "moderate"

    if len(symptom_names) >= 3:
        return "moderate"

    if "age_over_50" in risk_flags:
        return "moderate"

    # ── LOW default ────────────────────────────────────────────────────────
    return "low"


def score_urgency(context, xgb_predictions: list[dict] = None) -> dict:
    """
    Score urgency level from PatientContext and XGBoost predictions.

    Args:
        context: PatientContext object
        xgb_predictions: Top-3 disease predictions from classify_symptoms()

    Returns:
        Dict: {
            "level": "low" | "moderate" | "urgent" | "emergency",
            "score": float (probability of predicted class),
            "call_emergency": bool,
            "action_plan": list[str],
            "ml_backed": bool,
        }
    """
    xgb_predictions = xgb_predictions or []

    # Always run rule-based check first as an override guard
    rule_level = _rule_based_urgency(context)

    # Try to load model on first call
    if _ort_session is None:
        _load_models()

    # If model still not available, use rule-based
    if _ort_session is None:
        logger.warning("LightGBM model unavailable — using rule-based urgency")
        level = rule_level
        return {
            "level": level,
            "score": 0.5,
            "call_emergency": level == "emergency",
            "action_plan": URGENCY_ACTIONS[level],
            "ml_backed": False,
        }

    try:
        feature_vec = _build_severity_features(context, xgb_predictions)
        feature_vec = feature_vec.astype(np.float32)

        input_name = _ort_session.get_inputs()[0].name
        outputs = _ort_session.run(["probabilities"], {input_name: feature_vec})
        probs = outputs[0][0]  # shape: (4,)

        # Apply tuned emergency threshold
        emergency_threshold = (_thresholds or {}).get("emergency_threshold", 0.5)
        urgent_threshold = (_thresholds or {}).get("urgent_threshold", 0.5)

        # Override class decision if emergency probability exceeds tuned threshold
        if probs[3] >= emergency_threshold:
            level = "emergency"
            score = float(probs[3])
        elif probs[2] >= urgent_threshold:
            level = "urgent"
            score = float(probs[2])
        else:
            pred_class = int(np.argmax(probs))
            level = URGENCY_LABELS[pred_class]
            score = float(probs[pred_class])

        # Safety override: rule-based EMERGENCY always takes precedence
        if rule_level == "emergency" and level != "emergency":
            logger.warning(
                f"Rule-based override: ML predicted '{level}' but rule-based says EMERGENCY"
            )
            level = "emergency"
            score = max(score, float(probs[3]))

        logger.info(
            f"Urgency scored: {level.upper()} (score={score:.3f}, "
            f"emergency_prob={probs[3]:.3f}, threshold={emergency_threshold:.3f})"
        )

        return {
            "level": level,
            "score": round(score, 4),
            "call_emergency": level == "emergency",
            "action_plan": URGENCY_ACTIONS[level],
            "ml_backed": True,
        }

    except Exception as e:
        logger.error(f"LightGBM inference failed: {e} — falling back to rule-based")
        level = rule_level
        return {
            "level": level,
            "score": 0.5,
            "call_emergency": level == "emergency",
            "action_plan": URGENCY_ACTIONS[level],
            "ml_backed": False,
        }
