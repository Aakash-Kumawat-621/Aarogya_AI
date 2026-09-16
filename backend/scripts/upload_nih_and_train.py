"""
backend/scripts/upload_nih_and_train.py

Two-phase pipeline:
  Phase 1 (SageMaker Processing Job):
    - Runs on ml.m5.4xlarge (16 vCPU, 64GB RAM)
    - Downloads NIH ChestX-ray14 from Kaggle (~45GB) directly inside AWS
    - Uploads to s3://aarogya-ml-models/raw/chestxray14/
    - No local download needed at all

  Phase 2 (SageMaker Training Job):
    - Runs on ml.g4dn.2xlarge (T4 GPU)
    - Reads dataset directly from S3
    - Trains ResNet-50, saves model.tar.gz back to S3

Usage:
    python backend/scripts/upload_nih_and_train.py

Prerequisites:
    pip install sagemaker boto3 python-dotenv
    AWS credentials in backend/.env
    Your Kaggle username + API key (will be prompted interactively)
"""

import logging
import os
import sys
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Load .env ──────────────────────────────────────────────────────────────────
env_path = Path(__file__).parents[2] / "backend" / ".env"
from dotenv import load_dotenv
load_dotenv(env_path)

AWS_REGION          = os.environ.get("AWS_REGION", "us-east-1")
AWS_ACCOUNT_ID      = os.environ.get("AWS_ACCOUNT_ID", "248825820417")
S3_MODELS_BUCKET    = os.environ.get("S3_MODELS_BUCKET", "aarogya-ml-models")
SAGEMAKER_ROLE      = os.environ.get("SAGEMAKER_EXECUTION_ROLE", "")
MLFLOW_URI          = os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000")

S3_DATASET_PREFIX    = "raw/chestxray14"
S3_OUTPUT_PREFIX     = "sagemaker-output"
S3_CHECKPOINT_PREFIX = "checkpoints"


# ── Downloader script (runs INSIDE SageMaker Processing container) ─────────────
DOWNLOADER_SCRIPT = '''
import os, subprocess, boto3, json
from pathlib import Path

KAGGLE_USERNAME = os.environ["KAGGLE_USERNAME"]
KAGGLE_KEY      = os.environ["KAGGLE_KEY"]
S3_BUCKET       = os.environ["S3_BUCKET"]
S3_PREFIX       = os.environ["S3_PREFIX"]
AWS_REGION      = os.environ.get("AWS_REGION", "us-east-1")

# Write kaggle.json
Path("/root/.kaggle").mkdir(exist_ok=True)
with open("/root/.kaggle/kaggle.json", "w") as f:
    json.dump({"username": KAGGLE_USERNAME, "key": KAGGLE_KEY}, f)
os.chmod("/root/.kaggle/kaggle.json", 0o600)

# Install kaggle CLI
subprocess.run(["pip", "install", "-q", "kaggle"], check=True)

# Download NIH ChestX-ray14 dataset (~45GB)
DOWNLOAD_DIR = Path("/tmp/chestxray14")
DOWNLOAD_DIR.mkdir(exist_ok=True)

print("Downloading NIH ChestX-ray14 from Kaggle (~45GB)...")
subprocess.run([
    "kaggle", "datasets", "download",
    "-d", "nih-chest-xrays/data",
    "-p", str(DOWNLOAD_DIR),
    "--unzip"
], check=True)

print("Download complete. Uploading to S3...")

# Upload to S3
s3 = boto3.client("s3", region_name=AWS_REGION)
uploaded = 0
errors = 0

# Upload metadata files
for f in DOWNLOAD_DIR.glob("*.csv"):
    key = f"{S3_PREFIX}/{f.name}"
    print(f"Uploading metadata: {f.name}")
    s3.upload_file(str(f), S3_BUCKET, key)
    uploaded += 1

for f in DOWNLOAD_DIR.glob("*.txt"):
    key = f"{S3_PREFIX}/{f.name}"
    s3.upload_file(str(f), S3_BUCKET, key)
    uploaded += 1

# Upload images
IMAGES_DIR = DOWNLOAD_DIR / "images"
if not IMAGES_DIR.exists():
    IMAGES_DIR = DOWNLOAD_DIR

print("Uploading images to S3 (this takes ~30-60 min)...")
for img in IMAGES_DIR.glob("*.png"):
    key = f"{S3_PREFIX}/images/{img.name}"
    try:
        s3.upload_file(str(img), S3_BUCKET, key,
                       ExtraArgs={"StorageClass": "STANDARD_IA"})
        uploaded += 1
        if uploaded % 1000 == 0:
            print(f"  Uploaded {uploaded} images...")
    except Exception as e:
        errors += 1
        print(f"  Error uploading {img.name}: {e}")

print(f"Upload complete: {uploaded} files uploaded, {errors} errors")
print(f"Dataset at: s3://{S3_BUCKET}/{S3_PREFIX}/")
'''


def get_or_find_role() -> str:
    """Use existing IAM role from .env or auto-discover."""
    if SAGEMAKER_ROLE:
        logger.info(f"Using role from .env: {SAGEMAKER_ROLE}")
        return SAGEMAKER_ROLE

    import boto3
    iam = boto3.client("iam", region_name=AWS_REGION)

    logger.info("SAGEMAKER_EXECUTION_ROLE not in .env — auto-discovering IAM role...")
    paginator = iam.get_paginator("list_roles")
    for page in paginator.paginate():
        for role in page["Roles"]:
            name = role["RoleName"].lower()
            if "sagemaker" in name:
                arn = role["Arn"]
                logger.info(f"Found SageMaker role: {arn}")
                return arn

    logger.error(
        "No SageMaker IAM role found!\n"
        "Go to AWS Console -> IAM -> Roles -> Create Role\n"
        "  Trusted entity: SageMaker\n"
        "  Policies: AmazonSageMakerFullAccess + AmazonS3FullAccess\n"
        "Then add to backend/.env:\n"
        "  SAGEMAKER_EXECUTION_ROLE=arn:aws:iam::248825820417:role/YourRoleName"
    )
    sys.exit(1)


def ensure_s3_bucket() -> None:
    """Create S3 bucket if it doesn't exist."""
    import boto3
    s3 = boto3.client("s3", region_name=AWS_REGION)
    try:
        s3.head_bucket(Bucket=S3_MODELS_BUCKET)
        logger.info(f"S3 bucket exists: s3://{S3_MODELS_BUCKET}")
    except Exception:
        logger.info(f"Creating S3 bucket: s3://{S3_MODELS_BUCKET}")
        if AWS_REGION == "us-east-1":
            s3.create_bucket(Bucket=S3_MODELS_BUCKET)
        else:
            s3.create_bucket(
                Bucket=S3_MODELS_BUCKET,
                CreateBucketConfiguration={"LocationConstraint": AWS_REGION},
            )
        s3.put_public_access_block(
            Bucket=S3_MODELS_BUCKET,
            PublicAccessBlockConfiguration={
                "BlockPublicAcls": True,
                "IgnorePublicAcls": True,
                "BlockPublicPolicy": True,
                "RestrictPublicBuckets": True,
            },
        )
        logger.info(f"Created: s3://{S3_MODELS_BUCKET}")


def check_dataset_already_uploaded() -> bool:
    """Check if NIH images already exist in S3."""
    import boto3
    s3 = boto3.client("s3", region_name=AWS_REGION)
    try:
        response = s3.list_objects_v2(
            Bucket=S3_MODELS_BUCKET,
            Prefix=f"{S3_DATASET_PREFIX}/images/",
            MaxKeys=10,
        )
        count = response.get("KeyCount", 0)
        if count > 0:
            logger.info(f"Dataset already in S3 ({count}+ images found) — skipping download.")
            return True
        return False
    except Exception:
        return False


def run_download_phase(role: str, kaggle_username: str, kaggle_key: str) -> None:
    """
    Phase 1: SageMaker Processing Job — download NIH dataset from Kaggle into S3.
    Runs on ml.m5.4xlarge inside AWS. ~2 hrs, ~$0.20.
    """
    import boto3, sagemaker
    from sagemaker.processing import ScriptProcessor

    logger.info("=" * 60)
    logger.info("PHASE 1: Downloading NIH ChestX-ray14 -> S3")
    logger.info("  Instance: ml.m5.4xlarge (~$0.096/hr x ~2hrs = ~$0.20)")
    logger.info("=" * 60)

    # Write downloader script to temp file
    script_path = Path("/tmp/nih_downloader.py")
    script_path.write_text(DOWNLOADER_SCRIPT)

    session = sagemaker.Session(boto_session=boto3.Session(region_name=AWS_REGION))
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    processor = ScriptProcessor(
        command=["python3"],
        image_uri=(
            f"763104351884.dkr.ecr.{AWS_REGION}.amazonaws.com"
            "/pytorch-training:2.1.0-cpu-py310-ubuntu20.04-sagemaker"
        ),
        role=role,
        instance_count=1,
        instance_type="ml.m5.4xlarge",
        sagemaker_session=session,
        env={
            "KAGGLE_USERNAME": kaggle_username,
            "KAGGLE_KEY": kaggle_key,
            "S3_BUCKET": S3_MODELS_BUCKET,
            "S3_PREFIX": S3_DATASET_PREFIX,
            "AWS_REGION": AWS_REGION,
        },
        max_runtime_in_seconds=14400,  # 4 hours max
    )

    processor.run(
        code=str(script_path),
        job_name=f"nih-download-{timestamp}",
        wait=True,
        logs=True,
    )
    logger.info("Phase 1 complete — NIH dataset is now in S3")


def run_training_phase(role: str) -> str:
    """
    Phase 2: SageMaker Training Job — ResNet-50 on T4 GPU.
    Spot instance: ml.g4dn.2xlarge (~$0.28/hr x ~6hrs = ~$1.68).
    """
    import boto3, sagemaker
    from sagemaker.pytorch import PyTorch

    logger.info("=" * 60)
    logger.info("PHASE 2: ResNet-50 Training on SageMaker")
    logger.info(f"  Dataset: s3://{S3_MODELS_BUCKET}/{S3_DATASET_PREFIX}/")
    logger.info("  Instance: ml.g4dn.2xlarge spot (~$1.68 total)")
    logger.info("=" * 60)

    session = sagemaker.Session(boto_session=boto3.Session(region_name=AWS_REGION))
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    job_name = f"mediassist-xray-{timestamp}"

    estimator = PyTorch(
        entry_point="train_xray.py",
        source_dir=str(Path(__file__).parent),
        role=role,
        framework_version="2.1.0",
        py_version="py310",
        instance_type="ml.g4dn.2xlarge",
        instance_count=1,
        use_spot_instances=True,
        max_run=28800,
        max_wait=36000,
        checkpoint_s3_uri=f"s3://{S3_MODELS_BUCKET}/{S3_CHECKPOINT_PREFIX}/{job_name}/",
        checkpoint_local_path="/opt/ml/checkpoints",
        hyperparameters={
            "epochs": 20,
            "batch-size": 32,
            "patience": 5,
            "mlflow-uri": MLFLOW_URI,
        },
        output_path=f"s3://{S3_MODELS_BUCKET}/{S3_OUTPUT_PREFIX}/",
        sagemaker_session=session,
        metric_definitions=[
            {"Name": "val_mean_auc",  "Regex": r"val_mean_auc=(\S+)"},
            {"Name": "train_loss",    "Regex": r"train_loss=(\S+)"},
            {"Name": "val_loss",      "Regex": r"val_loss=(\S+)"},
        ],
        environment={"MLFLOW_TRACKING_URI": MLFLOW_URI},
        keep_alive_period_in_seconds=0,
    )

    training_input = sagemaker.inputs.TrainingInput(
        s3_data=f"s3://{S3_MODELS_BUCKET}/{S3_DATASET_PREFIX}/",
        s3_data_type="S3Prefix",
        content_type="application/x-image",
        distribution="FullyReplicated",
    )

    estimator.fit(
        inputs={"training": training_input},
        job_name=job_name,
        wait=False,  # Non-blocking
        logs=False,
    )

    logger.info(f"Training job submitted: {job_name}")
    logger.info(f"Monitor: https://console.aws.amazon.com/sagemaker/home?region={AWS_REGION}#/jobs/{job_name}")
    logger.info(f"Live logs: aws logs tail /aws/sagemaker/TrainingJobs --log-stream-name-prefix {job_name} --follow")
    logger.info(f"When done: aws s3 cp s3://{S3_MODELS_BUCKET}/{S3_OUTPUT_PREFIX}/{job_name}/output/model.tar.gz backend/ml_models/")
    return job_name


if __name__ == "__main__":
    logger.info("Aarogya AI — NIH Dataset Upload + ResNet-50 Training")
    logger.info(f"AWS Account: {AWS_ACCOUNT_ID} | Region: {AWS_REGION}")
    logger.info(f"S3 Bucket:   s3://{S3_MODELS_BUCKET}")

    # Find IAM role
    role = get_or_find_role()

    # Ensure bucket exists
    ensure_s3_bucket()

    # Check if dataset already uploaded
    already_uploaded = check_dataset_already_uploaded()

    if not already_uploaded:
        print("\n" + "=" * 60)
        print("Kaggle credentials needed to download NIH ChestX-ray14")
        print("Get from: https://www.kaggle.com/settings -> API -> Create New Token")
        print("=" * 60)
        kaggle_username = input("Kaggle username: ").strip()
        kaggle_key = input("Kaggle API key: ").strip()

        if not kaggle_username or not kaggle_key:
            logger.error("Kaggle credentials required.")
            sys.exit(1)

        run_download_phase(role, kaggle_username, kaggle_key)
    else:
        logger.info("Skipping download — starting training directly.")

    job_name = run_training_phase(role)
    logger.info(f"Job '{job_name}' is running on AWS. You can close this terminal.")
