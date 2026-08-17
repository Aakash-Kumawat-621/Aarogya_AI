"""
backend/app/services/bedrock_service.py

AWS Bedrock service for Aarogya AI — handles vision analysis of body photos.
Uses Amazon Nova Pro to analyze body part images and return structured JSON findings.
"""

import json
import logging
import time

import boto3
from botocore.exceptions import ClientError

from app.config import settings
from app.modules.image.image_preprocessor import image_to_base64

logger = logging.getLogger(__name__)

VISION_SYSTEM_PROMPT = """You are a medical image analysis assistant. Analyze the provided body part photograph.

TASK: Identify visible physical findings only. Do NOT diagnose.

Look for:
- Swelling or edema (location, severity: mild/moderate/severe)
- Skin color changes (redness, pallor, cyanosis, jaundice, bruising)
- Rash characteristics (type: macular/papular/vesicular, distribution, color)
- Wounds or injuries (type, approximate size, signs of infection)
- Visible deformity or asymmetry
- Any other clinically relevant visible finding

RULES:
- If you cannot clearly see a body part, return confidence < 0.3
- Never identify faces or personal information
- Never make a definitive diagnosis — only describe visible findings
- Use clinical terminology

Return ONLY valid JSON:
{
  "findings": [
    {"finding": "swelling", "location": "left ankle", "severity": "moderate", "description": "pitting edema visible"}
  ],
  "image_quality": "good/fair/poor",
  "confidence": 0.0,
  "body_part_detected": "left ankle",
  "requires_urgent_attention": false,
  "disclaimer": "This is a visual finding description only, not a medical diagnosis."
}"""


def _invoke_with_retry(client, body, max_retries=3):
    """Calls Bedrock invoke_model with exponential backoff on throttling."""
    for attempt in range(max_retries):
        try:
            response = client.invoke_model(
                modelId=settings.BEDROCK_MODEL_ID,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(body),
            )
            return response
        except ClientError as e:
            if (
                e.response["Error"]["Code"] == "ThrottlingException"
                and attempt < max_retries - 1
            ):
                time.sleep(2**attempt)
            else:
                raise


def analyze_body_photo(image_bytes: bytes) -> dict:
    """Analyzes a body photo using AWS Bedrock and returns structured JSON findings."""
    try:
        client = boto3.client("bedrock-runtime", region_name=settings.AWS_REGION)
        b64_image = image_to_base64(image_bytes)
        body = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "image": {
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": b64_image,
                                }
                            },
                        },
                        {
                            "type": "text",
                            "text": "Analyze this body photo and return findings as JSON.",
                        },
                    ],
                }
            ],
            "system": [{"text": VISION_SYSTEM_PROMPT}],
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1024,
        }
        response = _invoke_with_retry(client, body)
        resp_body = json.loads(response["body"].read())
        text = resp_body["content"][0]["text"]
        return json.loads(text)
    except Exception as e:
        logger.error(f"Bedrock body photo analysis failed: {e}")
        return {"findings": [], "confidence": 0.0, "error": str(e)}
