"""
backend/app/services/dynamodb_service.py

Handles reading and writing patient sessions to DynamoDB.

Tables (created by scripts/setup_aws_infra.py):
  - aarogya-sessions: keyed by session_id, TTL 30 days
  - aarogya-profiles: keyed by patient_id (future use)
"""

import json
import logging
import time
from decimal import Decimal
from typing import Optional

import boto3
from botocore.exceptions import ClientError

from app.config import settings

logger = logging.getLogger(__name__)

# DynamoDB session TTL: 30 days from creation
_SESSION_TTL_SECONDS = 30 * 24 * 60 * 60


def _get_table(table_name: str):
    """Returns a DynamoDB Table resource."""
    dynamodb = boto3.resource("dynamodb", **settings.boto3_kwargs)
    return dynamodb.Table(table_name)


def _to_dynamo(obj) -> dict:
    """
    Recursively convert a dict to DynamoDB-safe types.
    DynamoDB does not accept float — converts to Decimal.
    """
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _to_dynamo(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_dynamo(v) for v in obj]
    return obj


def _from_dynamo(obj) -> dict:
    """Converts Decimal back to float when reading from DynamoDB."""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {k: _from_dynamo(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_from_dynamo(v) for v in obj]
    return obj


def save_session(
    session_id: str,
    context_dict: dict,
    diagnosis_dict: Optional[dict] = None,
) -> bool:
    """
    Saves a patient session to DynamoDB aarogya-sessions table.

    Args:
        session_id: Unique session identifier (from PatientContext)
        context_dict: PatientContext serialized to dict
        diagnosis_dict: DiagnosisResult serialized to dict (can be None)

    Returns:
        True on success, False on failure (non-fatal — we log and continue)
    """
    try:
        table = _get_table(settings.DYNAMODB_SESSIONS_TABLE)
        item = {
            "session_id": session_id,
            "created_at": int(time.time()),
            "ttl": int(time.time()) + _SESSION_TTL_SECONDS,
            "context": _to_dynamo(context_dict),
        }
        if diagnosis_dict:
            item["diagnosis"] = _to_dynamo(diagnosis_dict)

        table.put_item(Item=item)
        logger.info(f"Session {session_id} saved to DynamoDB ✓")
        return True
    except ClientError as e:
        logger.error(f"DynamoDB save_session failed: {e.response['Error']['Message']}")
        return False
    except Exception as e:
        logger.error(f"DynamoDB save_session unexpected error: {e}")
        return False


def get_session(session_id: str) -> Optional[dict]:
    """
    Retrieves a patient session from DynamoDB.

    Args:
        session_id: Session identifier to look up

    Returns:
        Session dict with 'context' and optional 'diagnosis', or None if not found
    """
    try:
        table = _get_table(settings.DYNAMODB_SESSIONS_TABLE)
        response = table.get_item(Key={"session_id": session_id})
        item = response.get("Item")
        if not item:
            return None
        return _from_dynamo(item)
    except ClientError as e:
        logger.error(f"DynamoDB get_session failed: {e.response['Error']['Message']}")
        return None
    except Exception as e:
        logger.error(f"DynamoDB get_session unexpected error: {e}")
        return None
