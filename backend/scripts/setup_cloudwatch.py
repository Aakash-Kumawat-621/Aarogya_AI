"""
backend/scripts/setup_cloudwatch.py

Creates CloudWatch dashboard, alarms, and AWS Budget for Aarogya AI.

Run once after deploying to Lambda:
    cd backend
    python scripts/setup_cloudwatch.py

What it creates:
  - CloudWatch Dashboard: 5 widgets (latency, urgency, requests, errors, cold starts)
  - 3 CloudWatch Alarms: high latency, high error rate, emergency anomaly
  - AWS Budget: $20/month with alerts at $10 and $20
"""

import sys
import io
import json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import os
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, '.')

import boto3
from app.config import settings

LAMBDA_FUNCTION = settings.__dict__.get("LAMBDA_FUNCTION_NAME", "aarogya-api")
REGION = settings.AWS_REGION
ACCOUNT_ID = settings.AWS_ACCOUNT_ID
DASHBOARD_NAME = "AarogyaAI-Production"
SNS_TOPIC_NAME = "aarogya-alerts"

cw = boto3.client("cloudwatch", **settings.boto3_kwargs)
budgets = boto3.client("budgets", **settings.boto3_kwargs)
sns = boto3.client("sns", **settings.boto3_kwargs)


def create_sns_topic() -> str:
    """Create or get SNS alert topic, return ARN."""
    resp = sns.create_topic(Name=SNS_TOPIC_NAME)
    arn = resp["TopicArn"]
    print(f"[OK] SNS Topic: {arn}")
    return arn


def create_dashboard():
    """Create a 5-widget CloudWatch dashboard."""
    widgets = [
        {
            "type": "metric",
            "x": 0, "y": 0, "width": 12, "height": 6,
            "properties": {
                "title": "Analyze Latency (ms)",
                "metrics": [["mediassist", "AnalyzeLatency", {"stat": "Average", "period": 300}]],
                "view": "timeSeries",
                "stat": "Average",
                "period": 300,
                "region": REGION,
            }
        },
        {
            "type": "metric",
            "x": 12, "y": 0, "width": 12, "height": 6,
            "properties": {
                "title": "Urgency Distribution (7 days)",
                "metrics": [
                    ["mediassist", "UrgencyDistribution", "UrgencyLevel", "LOW",       {"stat": "Sum", "period": 86400}],
                    ["mediassist", "UrgencyDistribution", "UrgencyLevel", "MODERATE",  {"stat": "Sum", "period": 86400}],
                    ["mediassist", "UrgencyDistribution", "UrgencyLevel", "URGENT",    {"stat": "Sum", "period": 86400}],
                    ["mediassist", "UrgencyDistribution", "UrgencyLevel", "EMERGENCY", {"stat": "Sum", "period": 86400}],
                ],
                "view": "bar",
                "region": REGION,
            }
        },
        {
            "type": "metric",
            "x": 0, "y": 6, "width": 8, "height": 6,
            "properties": {
                "title": "Daily Requests",
                "metrics": [["mediassist", "InputModalities", {"stat": "SampleCount", "period": 86400}]],
                "view": "timeSeries",
                "region": REGION,
            }
        },
        {
            "type": "metric",
            "x": 8, "y": 6, "width": 8, "height": 6,
            "properties": {
                "title": "Lambda Error Rate",
                "metrics": [
                    ["AWS/Lambda", "Errors", "FunctionName", LAMBDA_FUNCTION, {"stat": "Sum", "period": 300}],
                ],
                "view": "timeSeries",
                "region": REGION,
            }
        },
        {
            "type": "metric",
            "x": 16, "y": 6, "width": 8, "height": 6,
            "properties": {
                "title": "Lambda Duration (Cold Start Proxy)",
                "metrics": [
                    ["AWS/Lambda", "InitDuration", "FunctionName", LAMBDA_FUNCTION, {"stat": "p95", "period": 3600}],
                ],
                "view": "timeSeries",
                "region": REGION,
            }
        },
    ]

    cw.put_dashboard(
        DashboardName=DASHBOARD_NAME,
        DashboardBody=json.dumps({"widgets": widgets}),
    )
    print(f"[OK] Dashboard created: https://{REGION}.console.aws.amazon.com/cloudwatch/home#dashboards:name={DASHBOARD_NAME}")


def create_alarms(sns_arn: str):
    """Create 3 CloudWatch alarms."""
    # 1. High latency (p95 > 20s) — uses ExtendedStatistics for percentiles
    cw.put_metric_alarm(
        AlarmName="aarogya-high-latency",
        AlarmDescription="p95 analyze latency exceeded 20 seconds",
        Namespace="mediassist",
        MetricName="AnalyzeLatency",
        ExtendedStatistic="p95",
        Period=300,
        EvaluationPeriods=2,
        Threshold=20000,
        ComparisonOperator="GreaterThanThreshold",
        TreatMissingData="notBreaching",
        AlarmActions=[sns_arn],
    )
    print("[OK] Alarm created: aarogya-high-latency (p95 > 20s)")

    # 2. Lambda error rate > 5%
    cw.put_metric_alarm(
        AlarmName="aarogya-lambda-errors",
        AlarmDescription="Lambda error rate exceeded 5%",
        Namespace="AWS/Lambda",
        MetricName="Errors",
        Dimensions=[{"Name": "FunctionName", "Value": LAMBDA_FUNCTION}],
        Statistic="Sum",
        Period=300,
        EvaluationPeriods=3,
        Threshold=5,
        ComparisonOperator="GreaterThanThreshold",
        TreatMissingData="notBreaching",
        AlarmActions=[sns_arn],
    )
    print("[OK] Alarm created: aarogya-lambda-errors (>5 errors in 5min)")

    # 3. Emergency surge (>20 EMERGENCY classifications in 1 hour — anomaly)
    cw.put_metric_alarm(
        AlarmName="aarogya-emergency-surge",
        AlarmDescription="Unusually high number of EMERGENCY urgency classifications",
        Namespace="mediassist",
        MetricName="UrgencyDistribution",
        Dimensions=[{"Name": "UrgencyLevel", "Value": "EMERGENCY"}],
        Statistic="Sum",
        Period=3600,
        EvaluationPeriods=1,
        Threshold=20,
        ComparisonOperator="GreaterThanThreshold",
        TreatMissingData="notBreaching",
        AlarmActions=[sns_arn],
    )
    print("[OK] Alarm created: aarogya-emergency-surge (>20 EMERGENCYs/hour)")


def create_budget(email: str):
    """Create $20/month budget with alerts at $10 and $20."""
    try:
        budgets.create_budget(
            AccountId=ACCOUNT_ID,
            Budget={
                "BudgetName": "AarogyaAI-Monthly",
                "BudgetLimit": {"Amount": "20", "Unit": "USD"},
                "TimeUnit": "MONTHLY",
                "BudgetType": "COST",
            },
            NotificationsWithSubscribers=[
                {
                    "Notification": {
                        "NotificationType": "ACTUAL",
                        "ComparisonOperator": "GREATER_THAN",
                        "Threshold": 50,
                        "ThresholdType": "PERCENTAGE",
                    },
                    "Subscribers": [{"SubscriptionType": "EMAIL", "Address": email}],
                },
                {
                    "Notification": {
                        "NotificationType": "ACTUAL",
                        "ComparisonOperator": "GREATER_THAN",
                        "Threshold": 100,
                        "ThresholdType": "PERCENTAGE",
                    },
                    "Subscribers": [{"SubscriptionType": "EMAIL", "Address": email}],
                },
            ],
        )
        print(f"[OK] Budget created: $20/month | alerts at $10 and $20 -> {email}")
    except budgets.exceptions.DuplicateRecordException:
        print("[INFO] Budget 'AarogyaAI-Monthly' already exists, skipping.")
    except Exception as e:
        print(f"[WARN] Budget creation failed (non-critical): {e}")


def run(alert_email: str = "aakash@example.com"):
    print("\n=== Aarogya AI — CloudWatch Setup ===\n")
    sns_arn = create_sns_topic()
    create_dashboard()
    create_alarms(sns_arn)
    create_budget(alert_email)
    print("\n[DONE] CloudWatch dashboard, alarms, and budget created.")
    print(f"       Dashboard: https://{REGION}.console.aws.amazon.com/cloudwatch/home#dashboards:name={DASHBOARD_NAME}")


if __name__ == "__main__":
    import sys
    email = sys.argv[1] if len(sys.argv) > 1 else "your-email@example.com"
    run(alert_email=email)
