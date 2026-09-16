"""
backend/scripts/sagemaker_launch.py

Launches the ResNet-50 SageMaker training job.
Dataset is read directly from S3 — no local download needed.

Usage:
    python backend/scripts/sagemaker_launch.py

Prerequisites:
    pip install sagemaker boto3
    AWS credentials in .env or ~/.aws/credentials
    Dataset already uploaded to S3:
        aws s3 sync /path/to/chestxray14/ s3://mediassist-ml/raw/chestxray14/

Approximate cost:
    ml.g4dn.2xlarge spot = $0.28/hr × 6 hrs ≈ $1.68 total
    Set billing alert at $5 for safety.
"""

import logging
import os
import sys
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def upload_training_script(s3_bucket: str, s3_prefix: str, script_path: str) -> str:
    """Upload train_xray.py to S3 so SageMaker can access it."""
    import boto3

    s3 = boto3.client("s3")
    key = f"{s3_prefix}/scripts/train_xray.py"
    logger.info(f"Uploading training script to s3://{s3_bucket}/{key}")
    s3.upload_file(script_path, s3_bucket, key)
    return f"s3://{s3_bucket}/{key}"


def launch_training_job(
    s3_bucket: str,
    aws_region: str,
    sagemaker_role: str,
    mlflow_tracking_uri: str,
    epochs: int = 20,
    batch_size: int = 32,
    use_spot: bool = True,
):
    """Launch ResNet-50 training job on SageMaker."""
    import boto3
    import sagemaker
    from sagemaker.pytorch import PyTorch

    session = sagemaker.Session(boto_session=boto3.Session(region_name=aws_region))
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    job_name = f"mediassist-xray-{timestamp}"

    logger.info(f"Job name: {job_name}")
    logger.info(f"Instance: ml.g4dn.2xlarge (spot={use_spot})")
    logger.info(f"Dataset: s3://{s3_bucket}/raw/chestxray14/")
    logger.info(f"Output:  s3://{s3_bucket}/models/")

    # SageMaker PyTorch estimator
    estimator = PyTorch(
        entry_point="train_xray.py",
        source_dir=str(Path(__file__).parent),  # backend/scripts/
        role=sagemaker_role,
        framework_version="2.1.0",
        py_version="py310",
        instance_type="ml.g4dn.2xlarge",
        instance_count=1,
        # ── Spot instance config (save ~70% cost) ─────────────────────────
        use_spot_instances=use_spot,
        max_run=28800,          # 8 hours max (job terminates after this)
        max_wait=36000,         # 10 hours total wait (includes spot queuing)
        # ── Checkpoint for spot interruption recovery ──────────────────────
        checkpoint_s3_uri=f"s3://{s3_bucket}/checkpoints/{job_name}/",
        checkpoint_local_path="/opt/ml/checkpoints",
        # ── Hyperparameters ───────────────────────────────────────────────
        hyperparameters={
            "epochs": epochs,
            "batch-size": batch_size,
            "patience": 5,
            "mlflow-uri": mlflow_tracking_uri,
        },
        # ── Output ────────────────────────────────────────────────────────
        output_path=f"s3://{s3_bucket}/sagemaker-output/",
        sagemaker_session=session,
        # ── Metric definitions (visible in SageMaker console) ─────────────
        metric_definitions=[
            {"Name": "val_mean_auc", "Regex": r"val_mean_auc=(\S+)"},
            {"Name": "train_loss", "Regex": r"train_loss=(\S+)"},
            {"Name": "val_loss", "Regex": r"val_loss=(\S+)"},
        ],
        # ── Environment variables ─────────────────────────────────────────
        environment={
            "MLFLOW_TRACKING_URI": mlflow_tracking_uri,
        },
        # ── Keep alive for debugging (disable for production) ─────────────
        keep_alive_period_in_seconds=0,
    )

    # Input channel: dataset directly from S3
    training_input = sagemaker.inputs.TrainingInput(
        s3_data=f"s3://{s3_bucket}/raw/chestxray14/",
        s3_data_type="S3Prefix",
        content_type="application/x-image",
        distribution="FullyReplicated",
    )

    logger.info("Launching training job...")
    estimator.fit(
        inputs={"training": training_input},
        job_name=job_name,
        wait=False,  # Don't block — monitor via CloudWatch
        logs=False,
    )

    logger.info(f"\n✓ Training job submitted: {job_name}")
    logger.info(f"\nMonitor via:")
    logger.info(f"  SageMaker Console → Training Jobs → {job_name}")
    logger.info(f"  CloudWatch live logs:")
    logger.info(f"    aws logs tail /aws/sagemaker/TrainingJobs --log-stream-name-prefix {job_name} --follow")
    logger.info(f"\nWhen complete, download model:")
    logger.info(f"  aws s3 cp s3://{s3_bucket}/sagemaker-output/{job_name}/output/model.tar.gz /tmp/")
    logger.info(f"  tar -xzf /tmp/model.tar.gz -C backend/ml_models/")
    logger.info(f"\nOr use the auto-upload script in export_models.py")

    return job_name, estimator


def check_job_status(job_name: str, aws_region: str):
    """Check status of a running SageMaker training job."""
    import boto3

    sm = boto3.client("sagemaker", region_name=aws_region)
    response = sm.describe_training_job(TrainingJobName=job_name)
    status = response["TrainingJobStatus"]
    secondary = response.get("SecondaryStatus", "")
    logger.info(f"Job {job_name}: {status} ({secondary})")

    if status == "Completed":
        metrics = response.get("FinalMetricDataList", [])
        logger.info("\nFinal metrics:")
        for m in metrics:
            logger.info(f"  {m['MetricName']}: {m['Value']:.4f}")
        output_uri = response["ModelArtifacts"]["S3ModelArtifacts"]
        logger.info(f"\nModel artifacts: {output_uri}")

    return status


if __name__ == "__main__":
    # Load from .env
    from dotenv import load_dotenv
    env_path = Path(__file__).parents[2] / "backend" / ".env"
    load_dotenv(env_path)

    S3_BUCKET = os.environ.get("S3_BUCKET_NAME", "mediassist-ml")
    AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")
    SAGEMAKER_ROLE = os.environ.get("SAGEMAKER_EXECUTION_ROLE")
    MLFLOW_URI = os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000")

    if not SAGEMAKER_ROLE:
        logger.error(
            "SAGEMAKER_EXECUTION_ROLE not set in .env\n"
            "Create it in AWS IAM → Roles → Create Role → SageMaker\n"
            "Attach policies: AmazonSageMakerFullAccess, AmazonS3FullAccess\n"
            "Then add to .env: SAGEMAKER_EXECUTION_ROLE=arn:aws:iam::ACCOUNT:role/SageMakerRole"
        )
        sys.exit(1)

    if "--status" in sys.argv:
        # Check status of existing job
        if len(sys.argv) < 3:
            logger.error("Usage: python sagemaker_launch.py --status <job_name>")
            sys.exit(1)
        check_job_status(sys.argv[2], AWS_REGION)
    else:
        # Launch new job
        job_name, estimator = launch_training_job(
            s3_bucket=S3_BUCKET,
            aws_region=AWS_REGION,
            sagemaker_role=SAGEMAKER_ROLE,
            mlflow_tracking_uri=MLFLOW_URI,
            epochs=20,
            batch_size=32,
            use_spot=True,
        )
