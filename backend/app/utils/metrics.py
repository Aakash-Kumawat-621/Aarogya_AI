"""
backend/app/utils/metrics.py

CloudWatch custom metrics emitter — fire-and-forget, non-blocking.
Wraps boto3 put_metric_data in a thread pool so it never blocks request handling.

Usage:
    from app.utils.metrics import emit_metric
    await emit_metric("AnalyzeLatency", processing_ms, "Milliseconds")
    await emit_metric("UrgencyDistribution", 1, "Count", {"UrgencyLevel": "EMERGENCY"})
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="cw-metrics")
NAMESPACE = "mediassist"


def _put_metric(name: str, value: float, unit: str, dimensions: dict) -> None:
    """Synchronous CloudWatch put — runs in thread pool."""
    try:
        import boto3
        from app.config import settings

        cw = boto3.client(
            "cloudwatch",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )
        metric_data = {
            "MetricName": name,
            "Value": value,
            "Unit": unit,
        }
        if dimensions:
            metric_data["Dimensions"] = [
                {"Name": k, "Value": str(v)} for k, v in dimensions.items()
            ]
        cw.put_metric_data(Namespace=NAMESPACE, MetricData=[metric_data])
    except Exception as e:
        # Metrics are non-critical — never let them crash the request
        logger.debug(f"CloudWatch metric failed (non-fatal): {e}")


async def emit_metric(
    name: str,
    value: float,
    unit: str = "Count",
    dimensions: Optional[dict] = None,
) -> None:
    """
    Emit a CloudWatch custom metric asynchronously (fire-and-forget).

    Args:
        name:       Metric name e.g. 'AnalyzeLatency'
        value:      Numeric value
        unit:       CloudWatch unit: 'Count' | 'Milliseconds' | 'None' | etc.
        dimensions: Optional dict of {DimensionName: DimensionValue}
    """
    loop = asyncio.get_event_loop()
    loop.run_in_executor(_executor, _put_metric, name, value, unit, dimensions or {})
