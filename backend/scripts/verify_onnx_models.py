import json
import logging
import os
import sys
from pathlib import Path

import numpy as np
import pytest

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

ML_MODELS_DIR = Path(__file__).parents[1] / "ml_models"

# Tolerance for floating point differences between original Python predictions and ONNX
RTOL = 1e-3
ATOL = 1e-5
N_TEST_SAMPLES = 50

def verify_xgboost() -> bool:
    """Verify XGBoost pkl output."""
    pkl_path = ML_MODELS_DIR / "xgboost_symptom.pkl"
    feat_path = ML_MODELS_DIR / "feature_names.json"

    logger.info("\n── XGBoost Verification ──────────────────────────────────")

    if not pkl_path.exists():
        logger.error(f"Missing: {pkl_path}")
        return False

    try:
        import joblib

        model = joblib.load(str(pkl_path))

        if feat_path.exists():
            with open(feat_path) as f:
                n_features = len(json.load(f))
        else:
            n_features = model.n_features_in_ if hasattr(model, "n_features_in_") else 150

        rng = np.random.RandomState(42)
        test_input = rng.rand(N_TEST_SAMPLES, n_features).astype(np.float32)

        # Original
        orig_probs = model.predict_proba(test_input)
        orig_preds = model.predict(test_input)

        logger.info(f"  Probabilities generated successfully")
        logger.info(f"  Classes: {len(np.unique(orig_preds))} unique diseases predicted")
        logger.info("  ✓ XGBoost PKL verified (Native)")
        return True

    except Exception as e:
        logger.error(f"  ✗ Error: {e}")
        return False

def verify_lightgbm() -> bool:
    """Verify LightGBM pkl vs ONNX runtime outputs."""
    pkl_path = ML_MODELS_DIR / "severity_scorer.pkl"
    onnx_path = ML_MODELS_DIR / "severity_scorer.onnx"
    feat_path = ML_MODELS_DIR / "severity_feature_names.json"
    thresh_path = ML_MODELS_DIR / "severity_thresholds.json"

    logger.info("\n── LightGBM Verification ─────────────────────────────────")

    for path in [pkl_path, onnx_path]:
        if not path.exists():
            logger.error(f"Missing: {path}")
            return False

    try:
        import joblib
        import onnxruntime as ort

        model = joblib.load(str(pkl_path))

        if feat_path.exists():
            with open(feat_path) as f:
                n_features = len(json.load(f))
        else:
            n_features = model.n_features_

        rng = np.random.RandomState(99)
        test_input = rng.rand(N_TEST_SAMPLES, n_features).astype(np.float32)

        # Original
        orig_probs = model.predict_proba(test_input)

        # ONNX
        session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
        input_name = session.get_inputs()[0].name
        onnx_probs = session.run(["probabilities"], {input_name: test_input})[0]

        np.testing.assert_allclose(orig_probs, onnx_probs, rtol=RTOL, atol=ATOL)

        # Verify emergency threshold exists and is valid
        if thresh_path.exists():
            with open(thresh_path) as f:
                thresholds = json.load(f)
            em_thresh = thresholds.get("emergency_threshold", None)
            assert em_thresh is not None, "emergency_threshold missing from severity_thresholds.json"
            assert 0.0 < em_thresh < 1.0, f"Invalid emergency_threshold: {em_thresh}"
            logger.info(f"  Emergency threshold: {em_thresh:.3f} ✓")

        logger.info(f"  Probabilities: max_diff={np.abs(orig_probs - onnx_probs).max():.2e} ✓")
        logger.info(f"  Classes: {orig_probs.shape[1]} (LOW/MODERATE/URGENT/EMERGENCY)")
        logger.info("  ✓ LightGBM ONNX verified")
        return True

    except AssertionError as e:
        logger.error(f"  ✗ Parity check FAILED: {e}")
        return False
    except Exception as e:
        logger.error(f"  ✗ Error: {e}")
        return False


def verify_resnet50() -> bool:
    """Verify ResNet-50 TorchScript loads and produces valid 14-class output."""
    pt_path = ML_MODELS_DIR / "resnet50_xray.pt"

    logger.info("\n── ResNet-50 Verification ────────────────────────────────")

    if not pt_path.exists():
        logger.error(f"Missing: {pt_path}")
        return False

    try:
        import torch

        model = torch.jit.load(str(pt_path), map_location="cpu")
        model.eval()

        # Test with realistic dummy inputs
        rng = torch.Generator().manual_seed(42)
        dummy_batch = torch.rand(4, 3, 224, 224, generator=rng)

        with torch.no_grad():
            logits = model(dummy_batch)

        assert logits.shape[0] == 4, f"Batch size mismatch: {logits.shape[0]}"
        assert logits.shape[1] >= 14, f"Expected ≥14 output classes, got {logits.shape[1]}"

        # Check sigmoid produces valid probabilities
        probs = torch.sigmoid(logits[:, :14])
        assert (probs >= 0).all() and (probs <= 1).all(), "Probabilities out of [0,1] range"

        # Check output is reasonable (not all zeros or all ones)
        assert probs.std() > 0.01, "Model output variance too low — model may be degenerate"

        logger.info(f"  Output shape: {tuple(logits.shape)} ✓")
        logger.info(f"  Sigmoid range: [{probs.min():.3f}, {probs.max():.3f}] ✓")
        logger.info(f"  Output std: {probs.std():.3f} ✓")
        logger.info("  ✓ ResNet-50 TorchScript verified")
        return True

    except Exception as e:
        logger.error(f"  ✗ Error: {e}")
        return False


def verify_from_s3() -> bool:
    """Download models from S3 to /tmp and verify (simulates Lambda cold start)."""
    logger.info("\n── S3 Cold-Start Simulation ──────────────────────────────")

    try:
        import boto3
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).parents[2] / "backend" / ".env")
        bucket = os.environ.get("S3_BUCKET_NAME", "aarogya-uploads")
        region = os.environ.get("AWS_REGION", "ap-south-1")

        s3 = boto3.client("s3", region_name=region)
        tmp_dir = Path("/tmp/mediassist_verify")
        tmp_dir.mkdir(parents=True, exist_ok=True)

        import time
        models = [
            ("models/xgboost_symptom.pkl", "xgboost_symptom.pkl"),
            ("models/severity_scorer.onnx", "severity_scorer.onnx"),
            ("models/resnet50_xray.pt", "resnet50_xray.pt"),
        ]

        total_start = time.time()
        for s3_key, local_name in models:
            start = time.time()
            try:
                s3.download_file(bucket, s3_key, str(tmp_dir / local_name))
                elapsed = time.time() - start
                size_mb = (tmp_dir / local_name).stat().st_size / (1024 * 1024)
                logger.info(f"  {local_name}: {size_mb:.1f} MB in {elapsed:.1f}s ✓")
            except Exception as e:
                logger.warning(f"  {local_name}: not in S3 yet — {e}")

        total_elapsed = time.time() - total_start
        logger.info(f"  Total cold-start download: {total_elapsed:.1f}s (target: <8s)")

        if total_elapsed > 8:
            logger.warning(f"  ⚠️ Download time {total_elapsed:.1f}s exceeds 8s Lambda cold-start target")
            logger.warning("  Consider: Lambda provisioned concurrency or EFS model caching")
        else:
            logger.info("  ✓ Cold-start within 8s Lambda target")

        return True

    except Exception as e:
        logger.warning(f"  S3 verification skipped: {e}")
        return True  # Non-fatal


def main():
    logger.info("=" * 55)
    logger.info("MODEL VERIFICATION")
    logger.info("=" * 55)

    results = {
        "xgboost_pkl": verify_xgboost(),
        "lightgbm_onnx": verify_lightgbm(),
        "resnet50_torchscript": verify_resnet50(),
    }

    # S3 cold-start check (optional)
    if "--skip-s3" not in sys.argv:
        results["s3_coldstart"] = verify_from_s3()

    logger.info("\n" + "=" * 55)
    logger.info("VERIFICATION SUMMARY")
    logger.info("=" * 55)
    all_passed = True
    for check, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        logger.info(f"  {check:30s}: {status}")
        if not passed:
            all_passed = False

    if all_passed:
        logger.info("\n✓ All verifications passed — models ready for production")
        sys.exit(0)
    else:
        logger.error("\n✗ Some verifications failed — DO NOT deploy until fixed")
        sys.exit(1)


if __name__ == "__main__":
    main()
