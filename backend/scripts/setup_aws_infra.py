"""
setup_aws_infra.py
──────────────────
Creates the following AWS resources for Aarogya AI:
  1. S3 bucket  : aarogya-uploads    (us-east-1, private, 1-day lifecycle)
  2. DynamoDB   : aarogya-sessions   (PAY_PER_REQUEST, TTL on expires_at)
  3. DynamoDB   : aarogya-profiles   (PAY_PER_REQUEST)

Run from backend/ directory with the venv activated:
    python scripts/setup_aws_infra.py
"""

import sys
import json
import boto3
from botocore.exceptions import ClientError

# ── Load settings ────────────────────────────────────────────────────────────
sys.path.insert(0, ".")
from app.config import settings

AWS_REGION    = settings.AWS_REGION
S3_BUCKET     = settings.S3_BUCKET_NAME
TBL_SESSIONS  = settings.DYNAMODB_SESSIONS_TABLE
TBL_PROFILES  = settings.DYNAMODB_PROFILES_TABLE

# ── Boto3 clients ─────────────────────────────────────────────────────────────
s3  = boto3.client("s3",       region_name=AWS_REGION)
ddb = boto3.client("dynamodb", region_name=AWS_REGION)


# ─────────────────────────────────────────────────────────────────────────────
# 1.  S3 BUCKET
# ─────────────────────────────────────────────────────────────────────────────
def create_s3_bucket():
    print(f"\n[S3] Creating bucket: {S3_BUCKET} in {AWS_REGION} ...")
    try:
        # us-east-1 does NOT accept a LocationConstraint param — it's the default
        if AWS_REGION == "us-east-1":
            s3.create_bucket(Bucket=S3_BUCKET)
        else:
            s3.create_bucket(
                Bucket=S3_BUCKET,
                CreateBucketConfiguration={"LocationConstraint": AWS_REGION},
            )
        print(f"  ✅ Bucket created: s3://{S3_BUCKET}")
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
            print(f"  ℹ️  Bucket already exists — skipping creation.")
        else:
            raise

    # Block all public access
    s3.put_public_access_block(
        Bucket=S3_BUCKET,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls": True,
            "IgnorePublicAcls": True,
            "BlockPublicPolicy": True,
            "RestrictPublicBuckets": True,
        },
    )
    print("  ✅ Public access blocked.")

    # Lifecycle rule: delete uploaded objects after 1 day
    s3.put_bucket_lifecycle_configuration(
        Bucket=S3_BUCKET,
        LifecycleConfiguration={
            "Rules": [
                {
                    "ID": "auto-delete-uploads-after-1-day",
                    "Status": "Enabled",
                    "Filter": {"Prefix": ""},
                    "Expiration": {"Days": 1},
                }
            ]
        },
    )
    print("  ✅ Lifecycle rule set: objects deleted after 1 day.")


# ─────────────────────────────────────────────────────────────────────────────
# 2.  DYNAMODB — SESSIONS TABLE
# ─────────────────────────────────────────────────────────────────────────────
def create_sessions_table():
    print(f"\n[DynamoDB] Creating table: {TBL_SESSIONS} ...")
    try:
        ddb.create_table(
            TableName=TBL_SESSIONS,
            AttributeDefinitions=[
                {"AttributeName": "session_id", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "session_id", "KeyType": "HASH"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        # Wait until table is active
        waiter = ddb.get_waiter("table_exists")
        waiter.wait(TableName=TBL_SESSIONS)
        print(f"  ✅ Table created: {TBL_SESSIONS}")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceInUseException":
            print(f"  ℹ️  Table already exists — skipping creation.")
        else:
            raise

    # Enable TTL on expires_at
    try:
        ddb.update_time_to_live(
            TableName=TBL_SESSIONS,
            TimeToLiveSpecification={
                "Enabled": True,
                "AttributeName": "expires_at",
            },
        )
        print("  ✅ TTL enabled on attribute: expires_at (auto-delete after 90 days)")
    except ClientError as e:
        print(f"  ⚠️  TTL update skipped: {e.response['Error']['Message']}")


# ─────────────────────────────────────────────────────────────────────────────
# 3.  DYNAMODB — PROFILES TABLE
# ─────────────────────────────────────────────────────────────────────────────
def create_profiles_table():
    print(f"\n[DynamoDB] Creating table: {TBL_PROFILES} ...")
    try:
        ddb.create_table(
            TableName=TBL_PROFILES,
            AttributeDefinitions=[
                {"AttributeName": "user_id", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "user_id", "KeyType": "HASH"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        waiter = ddb.get_waiter("table_exists")
        waiter.wait(TableName=TBL_PROFILES)
        print(f"  ✅ Table created: {TBL_PROFILES}")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceInUseException":
            print(f"  ℹ️  Table already exists — skipping creation.")
        else:
            raise


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  Aarogya AI — AWS Infrastructure Setup")
    print(f"  Account region : {AWS_REGION}")
    print(f"  S3 bucket      : {S3_BUCKET}")
    print(f"  DynamoDB       : {TBL_SESSIONS}, {TBL_PROFILES}")
    print("=" * 60)

    create_s3_bucket()
    create_sessions_table()
    create_profiles_table()

    print("\n" + "=" * 60)
    print("  ✅ All AWS resources created successfully!")
    print("=" * 60)
