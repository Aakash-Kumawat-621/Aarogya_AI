"""
backend/scripts/launch_sagemaker_boto3.py

Launches SageMaker ResNet-50 training job using ONLY boto3 (no sagemaker SDK).
Dataset is read directly from s3://aarogya-ml-models/raw/chestxray14/

Usage:
    python backend/scripts/launch_sagemaker_boto3.py

Prerequisites:
    pip install boto3 python-dotenv  (already installed)
    AWS credentials in backend/.env
    NIH dataset in s3://aarogya-ml-models/raw/chestxray14/
"""

import json
import logging
import os
import sys
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Load .env
env_path = Path(__file__).parents[2] / "backend" / ".env"
try:
    from dotenv import load_dotenv
    load_dotenv(env_path)
except ImportError:
    # Parse .env manually if dotenv not available
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip())

AWS_REGION       = os.environ.get("AWS_REGION", "us-east-1")
AWS_ACCOUNT_ID   = os.environ.get("AWS_ACCOUNT_ID", "248825820417")
S3_BUCKET        = os.environ.get("S3_MODELS_BUCKET", "aarogya-ml-models")
SAGEMAKER_ROLE   = os.environ.get("SAGEMAKER_EXECUTION_ROLE", "")
MLFLOW_URI       = os.environ.get("MLFLOW_TRACKING_URI", "")

S3_DATASET_URI   = f"s3://{S3_BUCKET}/raw/chestxray14/"
S3_OUTPUT_URI    = f"s3://{S3_BUCKET}/sagemaker-output/"


def ensure_s3_bucket(s3_client) -> None:
    """Create S3 bucket if it doesn't exist."""
    try:
        s3_client.head_bucket(Bucket=S3_BUCKET)
        logger.info(f"S3 bucket exists: s3://{S3_BUCKET}")
    except Exception:
        logger.info(f"Creating S3 bucket: s3://{S3_BUCKET}")
        if AWS_REGION == "us-east-1":
            s3_client.create_bucket(Bucket=S3_BUCKET)
        else:
            s3_client.create_bucket(
                Bucket=S3_BUCKET,
                CreateBucketConfiguration={"LocationConstraint": AWS_REGION},
            )
        s3_client.put_public_access_block(
            Bucket=S3_BUCKET,
            PublicAccessBlockConfiguration={
                "BlockPublicAcls": True,
                "IgnorePublicAcls": True,
                "BlockPublicPolicy": True,
                "RestrictPublicBuckets": True,
            },
        )
        logger.info(f"Created: s3://{S3_BUCKET}")


def check_dataset_in_s3(s3_client) -> bool:
    """Check if NIH images already exist in S3."""
    try:
        response = s3_client.list_objects_v2(
            Bucket=S3_BUCKET,
            Prefix="raw/chestxray14/images_001/",
            MaxKeys=5,
        )
        count = response.get("KeyCount", 0)
        if count > 0:
            logger.info(f"NIH dataset found in S3 ({count}+ objects). Ready for training!")
            return True
        return False
    except Exception as e:
        logger.warning(f"Could not check S3 dataset: {e}")
        return False


def upload_training_script(s3_client) -> str:
    """Package train_xray.py as a tar.gz and upload to S3."""
    script_path = Path(__file__).parent / "train_xray.py"
    if not script_path.exists():
        logger.error(f"train_xray.py not found at {script_path}")
        sys.exit(1)

    # Create sourcedir.tar.gz (SageMaker expects this format)
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create requirements.txt with all potential third-party dependencies
        req_path = Path(tmpdir) / "requirements.txt"
        with open(req_path, "w") as f:
            f.write("numpy<2\n")
            f.write("albumentations\n")
            f.write("scikit-learn\n")
            f.write("pandas\n")

        tar_path = Path(tmpdir) / "sourcedir.tar.gz"
        with tarfile.open(tar_path, "w:gz") as tar:
            tar.add(str(script_path), arcname="train_xray.py")
            tar.add(str(req_path), arcname="requirements.txt")

        s3_key = "sagemaker-source/sourcedir.tar.gz"
        logger.info(f"Uploading training script to s3://{S3_BUCKET}/{s3_key}")
        s3_client.upload_file(str(tar_path), S3_BUCKET, s3_key)
        return f"s3://{S3_BUCKET}/{s3_key}"


def launch_training_job(sm_client, source_uri: str, timestamp: str) -> str:
    """Launch SageMaker Training Job using boto3 directly."""
    job_name = f"mediassist-xray-{timestamp}"

    # PyTorch 2.1.0 DLC image for us-east-1
    training_image = (
        f"763104351884.dkr.ecr.{AWS_REGION}.amazonaws.com"
        "/pytorch-training:2.1.0-gpu-py310-cu121-ubuntu20.04-sagemaker"
    )

    hyperparameters = {
        "epochs": "20",
        "batch-size": "32",
        "patience": "5",
    }
    if MLFLOW_URI:
        hyperparameters["mlflow-uri"] = MLFLOW_URI

    request = {
        "TrainingJobName": job_name,
        "RoleArn": SAGEMAKER_ROLE,
        "AlgorithmSpecification": {
            "TrainingImage": training_image,
            "TrainingInputMode": "File",
            "EnableSageMakerMetricsTimeSeries": True,
            "MetricDefinitions": [
                {"Name": "val_mean_auc",  "Regex": "val_mean_auc=(\\S+)"},
                {"Name": "train_loss",    "Regex": "train_loss=(\\S+)"},
                {"Name": "val_loss",      "Regex": "val_loss=(\\S+)"},
            ],
        },
        "HyperParameters": {
            **hyperparameters,
            "sagemaker_program": "train_xray.py",
            "sagemaker_submit_directory": source_uri,
            "sagemaker_region": AWS_REGION,
        },
        "InputDataConfig": [
            {
                "ChannelName": "training",
                "DataSource": {
                    "S3DataSource": {
                        "S3DataType": "S3Prefix",
                        "S3Uri": S3_DATASET_URI,
                        "S3DataDistributionType": "FullyReplicated",
                    }
                },
                "ContentType": "application/x-image",
                "InputMode": "File",
            },

        ],
        "OutputDataConfig": {
            "S3OutputPath": S3_OUTPUT_URI,
        },
        "ResourceConfig": {
            "InstanceType": "ml.g4dn.2xlarge",
            "InstanceCount": 1,
            "VolumeSizeInGB": 100,
        },
        "StoppingCondition": {
            "MaxRuntimeInSeconds": 28800,      # 8 hours
            "MaxWaitTimeInSeconds": 172800,    # 48 hours to wait for a Spot Instance
        },
        "EnableManagedSpotTraining": True,
        "CheckpointConfig": {
            "S3Uri": f"s3://{S3_BUCKET}/checkpoints/{job_name}/",
            "LocalPath": "/opt/ml/checkpoints",
        },
        "EnableNetworkIsolation": False,
        "EnableInterContainerTrafficEncryption": False,
    }

    logger.info(f"Submitting training job: {job_name}")
    logger.info(f"  Instance:  ml.g4dn.2xlarge (T4 GPU, spot pricing)")
    logger.info(f"  Dataset:   {S3_DATASET_URI}")
    logger.info(f"  Output:    {S3_OUTPUT_URI}")
    logger.info(f"  Max cost:  ~$1.68 (~6 hrs x $0.28/hr spot)")

    response = sm_client.create_training_job(**request)
    return job_name


if __name__ == "__main__":
    import boto3

    logger.info("Aarogya AI - SageMaker ResNet-50 Training Launcher")
    logger.info(f"AWS Account: {AWS_ACCOUNT_ID} | Region: {AWS_REGION}")
    logger.info(f"Role:        {SAGEMAKER_ROLE}")

    if not SAGEMAKER_ROLE:
        logger.error("SAGEMAKER_EXECUTION_ROLE not set in backend/.env")
        sys.exit(1)

    s3  = boto3.client("s3",        region_name=AWS_REGION)
    sm  = boto3.client("sagemaker", region_name=AWS_REGION)

    # Step 1: Ensure bucket exists
    ensure_s3_bucket(s3)

    # Step 2: Check if dataset is in S3
    dataset_ready = check_dataset_in_s3(s3)
    if not dataset_ready:
        logger.warning("NIH dataset not found in S3!")
        logger.warning(f"Expected at: s3://{S3_BUCKET}/raw/chestxray14/images/")
        logger.warning("Please upload the dataset first, then re-run this script.")
        logger.warning("You can download it from Kaggle: nih-chest-xrays/data")
        sys.exit(1)

    # Step 3: Upload training script
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    source_uri = upload_training_script(s3)

    # Step 4: Launch training job
    job_name = launch_training_job(sm, source_uri, timestamp)

    logger.info(f"")
    logger.info(f"Training job submitted successfully!")
    logger.info(f"Job name: {job_name}")
    logger.info(f"")
    logger.info(f"Monitor at:")
    logger.info(f"  https://console.aws.amazon.com/sagemaker/home?region={AWS_REGION}#/jobs/{job_name}")
    logger.info(f"")
    logger.info(f"Live logs (run in terminal):")
    logger.info(f"  aws logs tail /aws/sagemaker/TrainingJobs --log-stream-name-prefix {job_name} --follow")
    logger.info(f"")
    logger.info(f"When training completes, download model:")
    logger.info(f"  aws s3 cp s3://{S3_BUCKET}/sagemaker-output/{job_name}/output/model.tar.gz backend/ml_models/")
    logger.info(f"  cd backend/ml_models && tar -xzf model.tar.gz")
    logger.info(f"")
    logger.info(f"You can now close this terminal. AWS runs it unattended!")
