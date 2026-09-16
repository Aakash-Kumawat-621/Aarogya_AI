"""
backend/app/modules/image/xray_classifier.py

ResNet-50 chest X-ray classifier — loads TorchScript model from S3 (cached).
Maps X-ray image bytes → 14-class NIH ChestX-ray14 condition scores.

14 classes (multi-label, not mutually exclusive):
    Atelectasis, Cardiomegaly, Consolidation, Edema, Effusion,
    Emphysema, Fibrosis, Hernia, Infiltration, Mass,
    No Finding, Nodule, Pleural_Thickening, Pneumonia, Pneumothorax

Model is a ResNet-50 fine-tuned on NIH ChestX-ray14 with:
- BCE loss (multi-label)
- Class-weighted pos_weight tensor
- TorchScript export (not ONNX — more reliable for PyTorch CNNs)

Used in: backend/app/api/routes/analyze.py
"""

import logging
import threading
from pathlib import Path

import numpy as np

from app.config import settings
from app.modules.image.image_preprocessor import preprocess_xray

logger = logging.getLogger(__name__)

# ── Singleton cache ────────────────────────────────────────────────────────
_lock = threading.Lock()
_model = None

MODEL_S3_KEY = "models/resnet50_xray.pt"
LOCAL_DIR = Path("/tmp/mediassist_models")

# 14 NIH ChestX-ray14 class labels (training order)
XRAY_CLASSES = [
    "Atelectasis",
    "Cardiomegaly",
    "Consolidation",
    "Edema",
    "Effusion",
    "Emphysema",
    "Fibrosis",
    "Hernia",
    "Infiltration",
    "Mass",
    "No Finding",
    "Nodule",
    "Pleural_Thickening",
    "Pneumonia",
    "Pneumothorax",
]

# Positive threshold per class (default 0.5 — can be tuned per class)
DEFAULT_THRESHOLD = 0.5


def _load_model() -> None:
    """Download ResNet-50 TorchScript from S3 and cache in memory."""
    global _model

    with _lock:
        if _model is not None:
            return

        LOCAL_DIR.mkdir(parents=True, exist_ok=True)

        try:
            import boto3
            import torch

            s3 = boto3.client(
                "s3",
                region_name=settings.AWS_REGION,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            )
            bucket = settings.S3_BUCKET_NAME

            model_path = LOCAL_DIR / "resnet50_xray.pt"
            if not model_path.exists():
                logger.info(f"Downloading ResNet-50 TorchScript from s3://{bucket}/{MODEL_S3_KEY}")
                s3.download_file(bucket, MODEL_S3_KEY, str(model_path))

            _model = torch.jit.load(str(model_path), map_location=torch.device("cpu"))
            _model.eval()

            logger.info(f"ResNet-50 X-ray classifier loaded ✓ ({len(XRAY_CLASSES)} classes)")

        except Exception as e:
            logger.warning(
                f"Could not load ResNet-50 model ({e}). "
                "X-ray classifier will return empty results."
            )
            _model = None


def classify_xray(image_bytes: bytes) -> dict:
    """
    Classify a chest X-ray image into 14 NIH ChestX-ray14 conditions.

    Args:
        image_bytes: Raw JPEG/PNG bytes of the X-ray image

    Returns:
        Dict: {
            "conditions": [{"name": str, "score": float, "positive": bool}, ...],
            "top_condition": str,
            "top_score": float,
            "positive_conditions": list[str],
            "ml_backed": bool,
        }
    """
    # Try to load model on first call
    if _model is None:
        _load_model()

    if _model is None:
        logger.warning("ResNet-50 model unavailable — skipping X-ray classification")
        return {
            "conditions": [],
            "top_condition": None,
            "top_score": 0.0,
            "positive_conditions": [],
            "ml_backed": False,
        }

    try:
        import torch

        # Preprocess using the existing image_preprocessor (CLAHE + normalize)
        # Returns a NumPy array of shape (224, 224, 3) or (1, 3, 224, 224)
        processed = preprocess_xray(image_bytes)

        # Convert to torch tensor
        if processed.ndim == 3:
            # (H, W, C) → (1, C, H, W)
            tensor = torch.from_numpy(processed).permute(2, 0, 1).unsqueeze(0).float()
        elif processed.ndim == 4:
            tensor = torch.from_numpy(processed).float()
        else:
            raise ValueError(f"Unexpected preprocess output shape: {processed.shape}")

        # Normalize to ImageNet stats if not already done
        mean = torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1)
        std = torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1)
        if tensor.max() > 1.0:
            tensor = tensor / 255.0
        tensor = (tensor - mean) / std

        # Inference
        with torch.no_grad():
            logits = _model(tensor)  # shape: (1, 14) or (1, 15)

        # Apply sigmoid (BCE model — outputs are NOT mutually exclusive)
        scores = torch.sigmoid(logits).squeeze().numpy()

        # Trim to match XRAY_CLASSES length
        scores = scores[:len(XRAY_CLASSES)]

        # Build condition list
        conditions = [
            {
                "name": cls,
                "score": round(float(scores[i]), 4),
                "positive": float(scores[i]) >= DEFAULT_THRESHOLD,
            }
            for i, cls in enumerate(XRAY_CLASSES)
        ]

        # Sort by score descending
        conditions_sorted = sorted(conditions, key=lambda x: x["score"], reverse=True)

        # Top condition (highest score, excluding "No Finding" if other positives exist)
        positive_conditions = [c["name"] for c in conditions if c["positive"] and c["name"] != "No Finding"]
        top = conditions_sorted[0]

        logger.info(
            f"X-ray classified: top={top['name']} (score={top['score']:.3f}), "
            f"positives={positive_conditions}"
        )

        return {
            "conditions": conditions_sorted,
            "top_condition": positive_conditions[0] if positive_conditions else top["name"],
            "top_score": top["score"],
            "positive_conditions": positive_conditions,
            "ml_backed": True,
        }

    except Exception as e:
        logger.error(f"ResNet-50 inference failed: {e}")
        return {
            "conditions": [],
            "top_condition": None,
            "top_score": 0.0,
            "positive_conditions": [],
            "ml_backed": False,
        }
