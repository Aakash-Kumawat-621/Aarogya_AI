"""
backend/app/modules/ml/symptom_classifier.py

XGBoost disease classifier — loads PKL model from S3 (cached in memory).
Maps PatientContext → feature vector → top-3 disease predictions.

Used in: backend/app/api/routes/analyze.py
"""

import json
import logging
import os
import threading
from pathlib import Path
from typing import Optional

import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)

# ── Singleton cache (thread-safe) ─────────────────────────────────────────
_lock = threading.Lock()
_xgb_model = None          # XGBClassifier
_label_encoder = None      # List[str]: index → disease name
_feature_names = None      # List[str]: expected feature order

MODEL_S3_KEY = "models/xgboost_symptom.pkl"
LABELS_S3_KEY = "models/label_encoder.json"
FEATURES_S3_KEY = "models/feature_names.json"
LOCAL_DIR = Path("/tmp/mediassist_models")

# All 132 symptom columns from the Kaggle disease-symptom dataset
# (keep ordered alphabetically to match training feature order)
SYMPTOM_COLUMNS = [
    "abdominal_pain", "abnormal_menstruation", "acidity", "acute_liver_failure",
    "altered_sensorium", "anxiety", "back_pain", "belly_pain", "blackheads",
    "bladder_discomfort", "blister", "blood_in_sputum", "bloody_stool",
    "blurred_and_distorted_vision", "breathlessness", "brittle_nails",
    "bruising", "burning_micturition", "chest_pain", "chills",
    "cold_hands_and_feets", "coma", "congestion", "constipation",
    "continuous_feel_of_urine", "continuous_sneezing", "cough",
    "cramps", "dark_urine", "dehydration", "depression", "diarrhoea",
    "dischromic_patches", "distention_of_abdomen", "dizziness",
    "drying_and_tingling_lips", "enlarged_thyroid", "excessive_hunger",
    "extra_marital_contacts", "family_history", "fast_heart_rate",
    "fatigue", "fluid_overload", "foul_smell_of_urine", "headache",
    "high_fever", "hip_joint_pain", "history_of_alcohol_consumption",
    "increased_appetite", "indigestion", "inflammatory_nails",
    "internal_itching", "irregular_sugar_level", "irritability",
    "irritation_in_anus", "itching", "joint_pain", "knee_pain",
    "lack_of_concentration", "lethargy", "loss_of_appetite",
    "loss_of_balance", "loss_of_smell", "malaise", "mild_fever",
    "mood_swings", "movement_stiffness", "mucoid_sputum",
    "muscle_pain", "muscle_wasting", "muscle_weakness", "nausea",
    "neck_pain", "nodal_skin_eruptions", "obesity", "pain_behind_the_eyes",
    "pain_during_bowel_movements", "pain_in_anal_region", "painful_walking",
    "palpitations", "passage_of_gases", "patches_in_throat",
    "phlegm", "polyuria", "prominent_veins_on_calf", "puffy_face_and_eyes",
    "pus_filled_pimples", "receiving_blood_transfusion",
    "receiving_unsterile_injections", "red_sore_around_nose",
    "red_spots_over_body", "redness_of_eyes", "restlessness",
    "runny_nose", "rusty_sputum", "scurring", "shivering",
    "silver_like_dusting", "sinus_pressure", "skin_peeling",
    "skin_rash", "slurred_speech", "small_dents_in_nails",
    "spinning_movements", "spotting_urination", "stiff_neck",
    "stomach_bleeding", "stomach_pain", "sunken_eyes",
    "sweating", "swelled_lymph_nodes", "swelling_joints",
    "swelling_of_stomach", "swollen_blood_vessels", "swollen_extremeties",
    "swollen_legs", "throat_irritation", "toxic_look_typhos",
    "ulcers_on_tongue", "unsteadiness", "visual_disturbances",
    "vomiting", "watering_from_eyes", "weakness_in_limbs",
    "weakness_of_one_body_side", "weight_gain", "weight_loss",
    "yellowing_of_eyes", "yellowish_skin", "yellow_urine",
]

def _download_from_s3(s3_key: str, local_path: Path):
    import boto3
    s3 = boto3.client(
        "s3",
        region_name=settings.AWS_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    )
    bucket = settings.S3_BUCKET_NAME
    logger.info(f"Downloading {s3_key} from {bucket}...")
    s3.download_file(bucket, s3_key, str(local_path))


def _load_models() -> None:
    """Download models from S3 and cache in memory (called once on first request)."""
    global _xgb_model, _label_encoder, _feature_names

    with _lock:
        if _xgb_model is not None:
            return  # Already loaded by another thread

        LOCAL_DIR.mkdir(parents=True, exist_ok=True)

        try:
            import boto3
            import joblib

            s3 = boto3.client(
                "s3",
                region_name=settings.AWS_REGION,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            )
            bucket = settings.S3_BUCKET_NAME

            # Download PKL model
            pkl_path = LOCAL_DIR / "xgboost_symptom.pkl"
            if not pkl_path.exists():
                logger.info(f"Downloading XGBoost PKL from s3://{bucket}/{MODEL_S3_KEY}")
                s3.download_file(bucket, MODEL_S3_KEY, str(pkl_path))

            # Download label encoder (JSON list: index → disease name)
            labels_path = LOCAL_DIR / "label_encoder.json"
            if not labels_path.exists():
                logger.info(f"Downloading label encoder from s3://{bucket}/{LABELS_S3_KEY}")
                s3.download_file(bucket, LABELS_S3_KEY, str(labels_path))

            # Download feature names
            features_path = LOCAL_DIR / "feature_names.json"
            if not features_path.exists():
                logger.info(f"Downloading feature names from s3://{bucket}/{FEATURES_S3_KEY}")
                s3.download_file(bucket, FEATURES_S3_KEY, str(features_path))

            # Load into memory
            _xgb_model = joblib.load(str(pkl_path))

            with open(labels_path) as f:
                _label_encoder = json.load(f)
            with open(features_path) as f:
                _feature_names = json.load(f)

            # Dynamically update SYMPTOM_COLUMNS from feature_names.json
            # The first N entries in feature_names that match the known symptom schema
            # are the binary symptom columns. We identify them by checking against
            # the hardcoded fallback list — any name in feature_names that also
            # appears in the hardcoded SYMPTOM_COLUMNS is a symptom column.
            global SYMPTOM_COLUMNS
            hardcoded_set = set(SYMPTOM_COLUMNS)
            dynamic_symptoms = [f for f in _feature_names if f in hardcoded_set]
            if dynamic_symptoms:
                SYMPTOM_COLUMNS = dynamic_symptoms
                logger.info(
                    f"SYMPTOM_COLUMNS updated from feature_names.json: "
                    f"{len(SYMPTOM_COLUMNS)} symptom columns"
                )

            logger.info(
                f"XGBoost symptom classifier loaded ✓ "
                f"({len(_label_encoder)} classes, {len(_feature_names)} features)"
            )
        except Exception as e:
            logger.error(f"Failed to load XGBoost models from S3: {e}", exc_info=True)
            _xgb_model = None
            _label_encoder = None
            _feature_names = None

def _build_feature_vector(context) -> np.ndarray:
    """
    Build a feature vector from PatientContext matching the training feature order.

    Feature categories (same as training notebook):
    1. Direct symptom features (132 binary columns)
    2. Patient demographic features
    3. Medical history features
    4. Lifestyle risk features
    5. Engineered risk multipliers (cardiac_risk_score, etc.)
    """
    profile = context.patient_profile
    symptom_names = {s.name.lower().replace(" ", "_") for s in context.symptom_entities if not s.negated}

    features = {}

    # Category 1: Direct symptom features
    for col in SYMPTOM_COLUMNS:
        features[col] = 1 if col in symptom_names else 0

    # Category 2: Patient demographic features
    age = getattr(profile, "age", 30)
    # Age bins: 0-17=0, 18-34=1, 35-49=2, 50-64=3, 65+=4
    if age < 18:
        features["age_bin"] = 0
    elif age < 35:
        features["age_bin"] = 1
    elif age < 50:
        features["age_bin"] = 2
    elif age < 65:
        features["age_bin"] = 3
    else:
        features["age_bin"] = 4

    gender = getattr(profile, "gender", "unknown")
    features["gender_encoded"] = {"male": 0, "female": 1, "other": 2}.get(
        gender.lower() if gender else "unknown", 2
    )

    bmi = getattr(profile, "bmi", None)
    if bmi is None:
        features["bmi_category"] = 1  # Normal
    elif bmi < 18.5:
        features["bmi_category"] = 0  # Underweight
    elif bmi < 25:
        features["bmi_category"] = 1  # Normal
    elif bmi < 30:
        features["bmi_category"] = 2  # Overweight
    else:
        features["bmi_category"] = 3  # Obese

    # Category 3: Medical history features
    conditions = [c.lower() for c in getattr(profile, "conditions", []) or []]
    features["has_diabetes"] = int(any("diabet" in c for c in conditions))
    features["has_hypertension"] = int(
        any(c in ("hypertension", "high blood pressure", "htn") for c in conditions)
    )
    features["has_respiratory_condition"] = int(
        any(c in ("asthma", "copd", "bronchitis", "emphysema") for c in conditions)
    )
    features["allergy_count"] = len(getattr(profile, "allergies", []) or [])
    features["medication_count"] = len(getattr(profile, "medications", []) or [])

    # Category 4: Lifestyle risk features
    smoking_raw = getattr(profile, "smoking", None)
    # Use ml_category() to normalize extended statuses (vaping, hookah, etc.)
    if smoking_raw and hasattr(smoking_raw, "ml_category"):
        smoking_ml = smoking_raw.ml_category()
    elif smoking_raw:
        smoking_ml = str(smoking_raw)
    else:
        smoking_ml = "never"
    features["smoking_encoded"] = {"never": 0, "former": 1, "current": 2}.get(smoking_ml, 0)

    pack_years = getattr(profile, "pack_years", 0) or 0
    if pack_years == 0:
        features["pack_years_binned"] = 0
    elif pack_years <= 10:
        features["pack_years_binned"] = 1
    elif pack_years <= 20:
        features["pack_years_binned"] = 2
    else:
        features["pack_years_binned"] = 3

    alcohol_units = getattr(profile, "alcohol_units_per_week", 0) or 0
    features["alcohol_risk"] = int(alcohol_units > 14)

    activity = getattr(profile, "activity_level", "moderate")
    features["activity_score"] = {"sedentary": 0, "light": 1, "moderate": 2, "active": 3}.get(
        activity if activity else "moderate", 2
    )

    sleep_hours = getattr(profile, "sleep_hours", 7) or 7
    features["sleep_deficit"] = int(sleep_hours < 6)

    # Category 5: Engineered risk multipliers
    smoker = features["smoking_encoded"] >= 1
    age_over_50 = age > 50
    has_htn = features["has_hypertension"]
    has_dm = features["has_diabetes"]
    has_chest_pain = features.get("chest_pain", 0)
    has_cough = features.get("cough", 0)
    has_breathlessness = features.get("breathlessness", 0)
    has_fever = features.get("high_fever", 0) or features.get("mild_fever", 0)
    has_headache = features.get("headache", 0)
    has_dizziness = features.get("dizziness", 0)
    has_nausea = features.get("nausea", 0)
    has_vomiting = features.get("vomiting", 0)
    has_abdominal_pain = features.get("abdominal_pain", 0)
    has_fatigue = features.get("fatigue", 0)
    has_visual_disturbances = features.get("visual_disturbances", 0)

    # cardiac_risk_score: age_over_50 A- smoker A- (hypertension OR diabetes)
    features["cardiac_risk_score"] = int(
        age_over_50 and smoker and (has_htn or has_dm)
    )

    # respiratory_risk_score: smoker A- (chest_pain OR cough OR breathlessness)
    features["respiratory_risk_score"] = int(
        smoker and (has_chest_pain or has_cough or has_breathlessness)
    )

    # acute_abdomen_flag: abdominal_pain A- fever A- (nausea OR vomiting)
    features["acute_abdomen_flag"] = int(
        has_abdominal_pain and has_fever and (has_nausea or has_vomiting)
    )

    # neurological_flag: (headache A- sudden_onset) OR (dizziness A- vision_changes)
    features["neurological_flag"] = int(
        has_headache or (has_dizziness and has_visual_disturbances)
    )

    # infection_cluster: fever A- (fatigue OR body_aches)
    has_body_aches = features.get("muscle_pain", 0)
    features["infection_cluster"] = int(
        has_fever and (has_fatigue or has_body_aches)
    )

    # Build ordered vector matching training feature_names
    if _feature_names:
        vec = [features.get(f, 0) for f in _feature_names]
    else:
        vec = list(features.values())

    return np.array(vec, dtype=np.float32).reshape(1, -1)


def classify_symptoms(context) -> list[dict]:
    """
    Classify symptoms from PatientContext -> top-3 disease predictions.

    Args:
        context: PatientContext object

    Returns:
        List of dicts: [{"disease": str, "probability": float}, ...]
        Returns up to 3 predictions sorted by probability descending.
        Falls back to stub if model not loaded.
    """
    # Try to load model on first call
    if _xgb_model is None:
        _load_models()

    if _xgb_model is None:
        # Model not available
        logger.warning("XGBoost model unavailable — returning stub predictions")
        return [
            {"disease": "Unspecified condition", "probability": 0.0, "ml_backed": False}
        ]

    try:
        feature_vec = _build_feature_vector(context)

        # Run native XGBoost inference
        probs = _xgb_model.predict_proba(feature_vec)[0]  # shape: (n_classes,)

        # Get top-3
        top3_idx = np.argsort(probs)[::-1][:3]
        results = []
        for idx in top3_idx:
            disease = _label_encoder[int(idx)] if _label_encoder else f"class_{idx}"
            results.append({
                "disease": disease,
                "probability": round(float(probs[idx]), 4),
                "ml_backed": True,
            })

        logger.info(
            f"XGBoost top prediction: {results[0]['disease']} "
            f"(p={results[0]['probability']:.3f})"
        )
        return results

    except Exception as e:
        logger.error(f"XGBoost inference failed: {e}")
        return [{"disease": "Inference error", "probability": 0.0, "ml_backed": False}]
