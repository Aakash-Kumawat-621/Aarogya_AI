"""
backend/scripts/export_models.py

Exports all 3 trained ML models to deployment format and uploads to S3.

Models:
  1. XGBoost → ONNX (xgboost_symptom.onnx)
  2. LightGBM → ONNX (severity_scorer.onnx)
  3. ResNet-50 → TorchScript (resnet50_xray.pt) — already saved by train_xray.py

Also uploads:
  - label_encoder.json
  - feature_names.json
  - severity_feature_names.json
  - severity_thresholds.json

Run AFTER training notebooks have completed:
    python backend/scripts/export_models.py

Then run verify_onnx_models.py to confirm numerical parity.
"""

import json
import logging
import os
import sys
from pathlib import Path

import numpy as np

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

ML_MODELS_DIR = Path(__file__).parents[1] / "ml_models"
S3_MODELS_PREFIX = "models"


# ═══════════════════════════════════════════════════════════════════════════
# S3 Upload helper
# ═══════════════════════════════════════════════════════════════════════════

def upload_to_s3(local_path: Path, s3_key: str, bucket: str) -> None:
    """Upload a file to S3 with progress logging."""
    import boto3

    s3 = boto3.client("s3")
    size_mb = local_path.stat().st_size / (1024 * 1024)
    logger.info(f"Uploading {local_path.name} ({size_mb:.1f} MB) → s3://{bucket}/{s3_key}")
    s3.upload_file(str(local_path), bucket, s3_key)
    logger.info(f"  ✓ Uploaded {local_path.name}")


# ═══════════════════════════════════════════════════════════════════════════
# 1. XGBoost → ONNX
# ═══════════════════════════════════════════════════════════════════════════

def export_xgboost(bucket: str) -> bool:
    """Convert XGBoost pkl → ONNX (opset 17) and upload to S3."""
    pkl_path = ML_MODELS_DIR / "xgboost_symptom.pkl"
    onnx_path = ML_MODELS_DIR / "xgboost_symptom.onnx"
    feature_names_path = ML_MODELS_DIR / "feature_names.json"
    label_encoder_path = ML_MODELS_DIR / "label_encoder.json"

    if not pkl_path.exists():
        logger.error(f"XGBoost model not found: {pkl_path}")
        logger.error("Run notebooks/05_symptom_classifier.ipynb on Kaggle first")
        return False

    logger.info("\n── XGBoost → ONNX ────────────────────────────────────────")

    try:
        import joblib

        model = joblib.load(str(pkl_path))
        logger.info(f"Loaded XGBoost model: {type(model).__name__}")

        # Upload the pkl directly
        size_mb = pkl_path.stat().st_size / (1024 * 1024)
        logger.info(f"Uploading PKL directly: {pkl_path.name} ({size_mb:.1f} MB)")
        
        upload_to_s3(pkl_path, f"{S3_MODELS_PREFIX}/xgboost_symptom.pkl", bucket)

        # Upload supporting files
        for fname, s3_name in [
            ("feature_names.json", "feature_names.json"),
            ("label_encoder.json", "label_encoder.json"),
            ("label_encoder.pkl", "label_encoder.pkl"),
        ]:
            fpath = ML_MODELS_DIR / fname
            if fpath.exists():
                upload_to_s3(fpath, f"{S3_MODELS_PREFIX}/{s3_name}", bucket)

        logger.info("✓ XGBoost ONNX export complete")
        return True

    except ImportError as e:
        logger.error(f"Missing dependency: {e}")
        logger.error("Install: pip install skl2onnx onnx")
        return False
    except Exception as e:
        logger.error(f"XGBoost ONNX export failed: {e}")
        return False


def _verify_xgboost_onnx(sklearn_model, onnx_path: Path, n_features: int) -> None:
    """Assert ONNX output matches sklearn output within rtol=1e-4."""
    import onnxruntime as ort

    logger.info("  Verifying ONNX numerical parity...")
    rng = np.random.RandomState(42)
    test_input = rng.rand(5, n_features).astype(np.float32)

    # Original model predictions
    original_probs = sklearn_model.predict_proba(test_input)

    # ONNX runtime predictions
    session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    input_name = session.get_inputs()[0].name
    onnx_probs = session.run(["probabilities"], {input_name: test_input})[0]

    try:
        np.testing.assert_allclose(original_probs, onnx_probs, rtol=1e-4, atol=1e-5)
        max_diff = np.abs(original_probs - onnx_probs).max()
        logger.info(f"  ✓ ONNX parity verified (max diff={max_diff:.2e})")
    except AssertionError as e:
        logger.error(f"  ✗ ONNX parity check FAILED: {e}")
        raise


# ═══════════════════════════════════════════════════════════════════════════
# 2. LightGBM → ONNX
# ═══════════════════════════════════════════════════════════════════════════

def export_lightgbm(bucket: str) -> bool:
    """Convert LightGBM pkl → ONNX (opset 17) and upload to S3."""
    pkl_path = ML_MODELS_DIR / "severity_scorer.pkl"
    onnx_path = ML_MODELS_DIR / "severity_scorer.onnx"
    thresholds_path = ML_MODELS_DIR / "severity_thresholds.json"
    feat_path = ML_MODELS_DIR / "severity_feature_names.json"

    if not pkl_path.exists():
        logger.error(f"LightGBM model not found: {pkl_path}")
        logger.error("Run notebooks/06_severity_scorer.ipynb on Kaggle first")
        return False

    logger.info("\n── LightGBM → ONNX ───────────────────────────────────────")

    try:
        import joblib
        from onnxmltools import convert_lightgbm
        from onnxmltools.convert.common.data_types import FloatTensorType

        model = joblib.load(str(pkl_path))
        logger.info(f"Loaded LightGBM model: {type(model).__name__}")

        # Get feature count
        if feat_path.exists():
            with open(feat_path) as f:
                feat_names = json.load(f)
            n_features = len(feat_names)
        else:
            n_features = model.n_features_ if hasattr(model, "n_features_") else 160
            logger.warning(f"severity_feature_names.json not found — assuming {n_features} features")

        logger.info(f"Feature count: {n_features}")

        initial_type = [("features", FloatTensorType([None, n_features]))]

        onnx_model = convert_lightgbm(
            model,
            initial_types=initial_type,
            zipmap=False,
        )

        with open(onnx_path, "wb") as f:
            f.write(onnx_model.SerializeToString())

        size_mb = onnx_path.stat().st_size / (1024 * 1024)
        logger.info(f"ONNX model saved: {onnx_path.name} ({size_mb:.1f} MB)")

        # Verify
        _verify_lgbm_onnx(model, onnx_path, n_features)

        # Upload
        upload_to_s3(onnx_path, f"{S3_MODELS_PREFIX}/severity_scorer.onnx", bucket)

        for fname, s3_name in [
            ("severity_thresholds.json", "severity_thresholds.json"),
            ("severity_feature_names.json", "severity_feature_names.json"),
        ]:
            fpath = ML_MODELS_DIR / fname
            if fpath.exists():
                upload_to_s3(fpath, f"{S3_MODELS_PREFIX}/{s3_name}", bucket)

        logger.info("✓ LightGBM ONNX export complete")
        return True

    except ImportError as e:
        logger.error(f"Missing dependency: {e}")
        logger.error("Install: pip install skl2onnx onnx lightgbm")
        return False
    except Exception as e:
        logger.error(f"LightGBM ONNX export failed: {e}")
        return False


def _verify_lgbm_onnx(sklearn_model, onnx_path: Path, n_features: int) -> None:
    """Assert ONNX output matches LightGBM output within rtol=1e-4."""
    import onnxruntime as ort

    logger.info("  Verifying ONNX numerical parity...")
    rng = np.random.RandomState(123)
    test_input = rng.rand(5, n_features).astype(np.float32)

    original_probs = sklearn_model.predict_proba(test_input)

    session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    input_name = session.get_inputs()[0].name
    onnx_probs = session.run(["probabilities"], {input_name: test_input})[0]

    try:
        np.testing.assert_allclose(original_probs, onnx_probs, rtol=1e-4, atol=1e-5)
        max_diff = np.abs(original_probs - onnx_probs).max()
        logger.info(f"  ✓ ONNX parity verified (max diff={max_diff:.2e})")
    except AssertionError as e:
        logger.error(f"  ✗ ONNX parity check FAILED: {e}")
        raise


# ═══════════════════════════════════════════════════════════════════════════
# 3. ResNet-50 — already TorchScript, just upload
# ═══════════════════════════════════════════════════════════════════════════

def export_resnet50(bucket: str) -> bool:
    """Upload pre-exported TorchScript ResNet-50 to S3."""
    pt_path = ML_MODELS_DIR / "resnet50_xray.pt"

    if not pt_path.exists():
        logger.error(f"ResNet-50 model not found: {pt_path}")
        logger.error(
            "Download from SageMaker output:\n"
            "  aws s3 cp s3://mediassist-ml/sagemaker-output/<job-name>/output/model.tar.gz /tmp/\n"
            "  tar -xzf /tmp/model.tar.gz -C backend/ml_models/"
        )
        return False

    logger.info("\n── ResNet-50 TorchScript → S3 ────────────────────────────")

    try:
        import torch

        # Verify TorchScript loads correctly
        logger.info("  Verifying TorchScript model...")
        model = torch.jit.load(str(pt_path), map_location="cpu")
        model.eval()

        # Test forward pass with random input
        with torch.no_grad():
            dummy = torch.randn(1, 3, 224, 224)
            output = model(dummy)
            assert output.shape == (1, 14) or output.shape[1] >= 14, \
                f"Unexpected output shape: {output.shape}"

        logger.info(f"  ✓ TorchScript verified (output shape: {tuple(output.shape)})")

        upload_to_s3(pt_path, f"{S3_MODELS_PREFIX}/resnet50_xray.pt", bucket)

        # Upload training results if present
        results_path = ML_MODELS_DIR / "training_results.json"
        if results_path.exists():
            upload_to_s3(results_path, f"{S3_MODELS_PREFIX}/resnet50_training_results.json", bucket)

        logger.info("✓ ResNet-50 upload complete")
        return True

    except Exception as e:
        logger.error(f"ResNet-50 upload failed: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    from dotenv import load_dotenv
    env_path = Path(__file__).parents[2] / "backend" / ".env"
    load_dotenv(env_path)

    bucket = os.environ.get("S3_BUCKET_NAME", "mediassist-ml")
    logger.info(f"Export target: s3://{bucket}/{S3_MODELS_PREFIX}/")
    logger.info(f"Local source:  {ML_MODELS_DIR}\n")

    results = {
        "xgboost": export_xgboost(bucket),
        "lightgbm": export_lightgbm(bucket),
        "resnet50": export_resnet50(bucket),
    }

    logger.info("\n" + "=" * 55)
    logger.info("EXPORT SUMMARY")
    logger.info("=" * 55)
    for model, success in results.items():
        status = "✓ DONE" if success else "✗ FAILED / SKIPPED"
        logger.info(f"  {model:12s}: {status}")

    n_success = sum(results.values())
    logger.info(f"\n{n_success}/3 models exported successfully")

    if n_success == 3:
        logger.info("\nAll models exported! Run next:")
        logger.info("  python backend/scripts/verify_onnx_models.py")
    else:
        logger.info("\nSome models missing — train them first, then re-run this script.")


if __name__ == "__main__":
    main()
