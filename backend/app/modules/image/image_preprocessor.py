"""
backend/app/modules/image/image_preprocessor.py

Image preprocessing pipeline for Aarogya AI.

Exports:
  preprocess_for_model(image_bytes: bytes) -> np.ndarray
      General preprocessing: resize 224×224, RGB, ImageNet normalization.

  preprocess_xray(image_bytes: bytes) -> np.ndarray
      X-ray specific: applies CLAHE contrast enhancement before normalization.
      CLAHE = Contrast Limited Adaptive Histogram Equalization.
      Rationale: X-ray images have low local contrast; CLAHE reveals subtle
      infiltrates and pathology borders without amplifying noise.

  image_to_base64(image_bytes: bytes) -> str
      Convert image bytes to base64 string (used for Bedrock vision API).
"""

from __future__ import annotations

import base64
import logging
from io import BytesIO

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# ── ImageNet normalization constants ─────────────────────────────────────────
_IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

# Target size for all model inputs
_TARGET_SIZE = (224, 224)


# ── Internal helpers ─────────────────────────────────────────────────────────


def _load_image(image_bytes: bytes) -> np.ndarray:
    """
    Load image bytes → RGB uint8 numpy array.
    Uses PIL to handle JPEG, PNG, DICOM-preview, WebP, etc.
    """
    pil_img = Image.open(BytesIO(image_bytes)).convert("RGB")
    return np.array(pil_img, dtype=np.uint8)


def _resize(image_rgb: np.ndarray) -> np.ndarray:
    """Resize to TARGET_SIZE using Lanczos interpolation for quality."""
    return cv2.resize(image_rgb, _TARGET_SIZE, interpolation=cv2.INTER_LANCZOS4)


def _normalize(image_rgb_f32: np.ndarray) -> np.ndarray:
    """
    ImageNet normalization:
        output = (pixel / 255.0 - mean) / std
    Returns float32 array.
    """
    normalized = (image_rgb_f32 / 255.0 - _IMAGENET_MEAN) / _IMAGENET_STD
    return normalized.astype(np.float32)


def _apply_clahe(image_rgb: np.ndarray) -> np.ndarray:
    """
    Apply CLAHE (Contrast Limited Adaptive Histogram Equalization) to improve
    local contrast in X-ray images.

    CLAHE is applied per-channel in LAB colour space so luminance is enhanced
    without shifting hue/saturation.

    Parameters (chosen for medical imaging):
        clipLimit   = 2.0   — limits noise amplification
        tileGridSize = (8, 8) — 8×8 tiles for local adaptation
    """
    # Convert RGB → LAB
    lab = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l_eq = clahe.apply(l_channel)

    # Merge back and convert LAB → RGB
    lab_eq = cv2.merge([l_eq, a_channel, b_channel])
    enhanced_rgb = cv2.cvtColor(lab_eq, cv2.COLOR_LAB2RGB)
    return enhanced_rgb


# ── Public API ────────────────────────────────────────────────────────────────


def preprocess_for_model(image_bytes: bytes) -> np.ndarray:
    """
    Standard preprocessing pipeline for a model input.

    Steps:
        1. Decode → RGB uint8
        2. Resize → 224×224
        3. Normalize with ImageNet mean/std → float32

    Args:
        image_bytes: Raw bytes of any common image format.

    Returns:
        numpy array of shape (224, 224, 3), dtype float32.
    """
    if not image_bytes:
        raise ValueError("image_bytes must not be empty.")

    logger.debug("preprocess_for_model: %d bytes", len(image_bytes))
    img_rgb = _load_image(image_bytes)
    img_resized = _resize(img_rgb)
    img_f32 = img_resized.astype(np.float32)
    result = _normalize(img_f32)

    logger.debug(
        "preprocess_for_model output shape=%s dtype=%s", result.shape, result.dtype
    )
    return result


def preprocess_xray(image_bytes: bytes) -> np.ndarray:
    """
    X-ray specific preprocessing pipeline.

    Steps (on top of standard pipeline):
        1. Decode → RGB uint8
        2. Apply CLAHE for local contrast enhancement
        3. Resize → 224×224
        4. Normalize with ImageNet mean/std → float32

    CLAHE is performed BEFORE resize so the enhancement grid aligns
    with the full-resolution image features.

    Args:
        image_bytes: Raw bytes of an X-ray image (JPEG/PNG/DICOM preview).

    Returns:
        numpy array of shape (224, 224, 3), dtype float32.
    """
    if not image_bytes:
        raise ValueError("image_bytes must not be empty.")

    logger.debug("preprocess_xray: %d bytes", len(image_bytes))
    img_rgb = _load_image(image_bytes)

    # CLAHE on full-resolution image for best enhancement
    img_enhanced = _apply_clahe(img_rgb)

    img_resized = _resize(img_enhanced)
    img_f32 = img_resized.astype(np.float32)
    result = _normalize(img_f32)

    logger.debug("preprocess_xray output shape=%s dtype=%s", result.shape, result.dtype)
    return result


def image_to_base64(image_bytes: bytes, format: str = "JPEG") -> str:
    """
    Convert raw image bytes to a base64-encoded string.

    Used for sending images to the AWS Bedrock vision API (Nova Pro / Claude 3).
    The base64 string is returned without a data-URI prefix.

    Args:
        image_bytes: Raw image bytes.
        format:      Output format for re-encoding ("JPEG" or "PNG").
                     If the input is already JPEG/PNG, pass-through is used.

    Returns:
        Base64-encoded string.
    """
    if not image_bytes:
        raise ValueError("image_bytes must not be empty.")

    # Re-encode through PIL to ensure consistent format + strip EXIF
    pil_img = Image.open(BytesIO(image_bytes)).convert("RGB")
    buffer = BytesIO()
    pil_img.save(buffer, format=format, quality=95)
    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")

    logger.debug("image_to_base64: %d chars", len(encoded))
    return encoded


def get_image_metadata(image_bytes: bytes) -> dict:
    """
    Return basic metadata about an image (for logging / debugging).

    Returns:
        {width, height, mode, format, size_bytes}
    """
    pil_img = Image.open(BytesIO(image_bytes))
    return {
        "width": pil_img.width,
        "height": pil_img.height,
        "mode": pil_img.mode,
        "format": pil_img.format,
        "size_bytes": len(image_bytes),
    }
