"""
backend/scripts/setup_mlflow.py

Configures MLflow tracking for MediAssist AI Module 4 experiments.
Sets up S3 artifact store, creates experiment groups, and provides
a log_model_run() wrapper used by all training notebooks.

Run ONCE before starting Module 4 training:
    python backend/scripts/setup_mlflow.py

Then in notebooks, import and use:
    from backend.scripts.setup_mlflow import log_model_run
"""

import json
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────
S3_BUCKET = os.getenv("S3_BUCKET_NAME", "mediassist-ml")
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
ARTIFACT_ROOT = f"s3://{S3_BUCKET}/mlflow-artifacts"

EXPERIMENTS = [
    {
        "name": "xgboost_symptom_classifier",
        "description": "41-class disease classification from symptom features. Target: macro-F1 >= 0.72",
        "tags": {"model_type": "xgboost", "module": "4", "team": "aarogya_ai"},
    },
    {
        "name": "resnet50_xray_classifier",
        "description": "14-class chest X-ray CNN (NIH ChestX-ray14). Target: mean AUC-ROC >= 0.80",
        "tags": {"model_type": "resnet50", "module": "4", "team": "aarogya_ai"},
    },
    {
        "name": "lightgbm_severity_scorer",
        "description": "4-class urgency scorer (LOW/MODERATE/URGENT/EMERGENCY). Target: Emergency recall >= 0.95",
        "tags": {"model_type": "lightgbm", "module": "4", "team": "aarogya_ai"},
    },
]


def setup_mlflow() -> None:
    """Create MLflow experiments and configure S3 artifact store."""
    try:
        import mlflow

        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        logger.info(f"MLflow tracking URI: {MLFLOW_TRACKING_URI}")
        logger.info(f"Artifact root: {ARTIFACT_ROOT}")

        for exp in EXPERIMENTS:
            existing = mlflow.get_experiment_by_name(exp["name"])
            if existing is None:
                exp_id = mlflow.create_experiment(
                    name=exp["name"],
                    artifact_location=f"{ARTIFACT_ROOT}/{exp['name']}",
                    tags=exp["tags"],
                )
                logger.info(f"Created experiment '{exp['name']}' (id={exp_id})")
            else:
                logger.info(
                    f"Experiment '{exp['name']}' already exists (id={existing.experiment_id})"
                )

        logger.info("\n✓ MLflow setup complete!")
        logger.info(f"  Open dashboard: mlflow ui --port 5000")
        logger.info(f"  Then visit: http://localhost:5000")

    except ImportError:
        logger.error("MLflow not installed. Run: pip install mlflow")
        sys.exit(1)
    except Exception as e:
        logger.error(f"MLflow setup failed: {e}")
        logger.warning("Running in local-only mode (no S3 artifacts). Continuing...")


def log_model_run(
    experiment_name: str,
    run_name: str,
    params: dict,
    metrics: dict,
    tags: dict = None,
    model=None,
    model_name: str = None,
    artifacts: dict = None,
) -> str:
    """
    Wrapper around mlflow.start_run() used by all training notebooks.

    Args:
        experiment_name: One of the 3 experiment names above
        run_name: Human-readable name (e.g. "xgb_smote_optuna_trial_42")
        params: Hyperparameters dict {param_name: value}
        metrics: Metrics dict {metric_name: float}
        tags: Optional extra tags
        model: Optional sklearn/xgb/lgbm model to log
        model_name: Name for logged model artifact
        artifacts: Dict of {local_path: artifact_name} files to log

    Returns:
        run_id: MLflow run ID string
    """
    try:
        import mlflow

        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        mlflow.set_experiment(experiment_name)

        with mlflow.start_run(run_name=run_name, tags=tags or {}) as run:
            mlflow.log_params(params)
            mlflow.log_metrics(metrics)

            if model is not None and model_name:
                # Auto-detect model type and use appropriate flavor
                model_type = type(model).__module__
                if "xgboost" in model_type:
                    mlflow.xgboost.log_model(model, artifact_path=model_name)
                elif "lightgbm" in model_type:
                    mlflow.lightgbm.log_model(model, artifact_path=model_name)
                elif "sklearn" in model_type or "pipeline" in model_type.lower():
                    mlflow.sklearn.log_model(model, artifact_path=model_name)
                else:
                    mlflow.pyfunc.log_model(
                        artifact_path=model_name,
                        python_model=model,
                    )

            if artifacts:
                for local_path, artifact_name in artifacts.items():
                    mlflow.log_artifact(local_path, artifact_name)

            run_id = run.info.run_id
            logger.info(
                f"Logged run '{run_name}' to '{experiment_name}' (run_id={run_id})"
            )
            return run_id

    except ImportError:
        logger.warning("MLflow not available — skipping experiment logging")
        return "local_run"
    except Exception as e:
        logger.warning(f"MLflow logging failed (non-fatal): {e}")
        return "failed_run"


def get_best_run(experiment_name: str, metric: str, mode: str = "max") -> dict:
    """
    Retrieve the best run from an experiment by a given metric.

    Args:
        experiment_name: Name of the MLflow experiment
        metric: Metric to optimize (e.g. "val_macro_f1")
        mode: "max" or "min"

    Returns:
        Dict with run_id, params, metrics of the best run
    """
    try:
        import mlflow

        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        client = mlflow.tracking.MlflowClient()
        exp = client.get_experiment_by_name(experiment_name)
        if exp is None:
            return {}

        order = "DESC" if mode == "max" else "ASC"
        runs = client.search_runs(
            experiment_ids=[exp.experiment_id],
            order_by=[f"metrics.{metric} {order}"],
            max_results=1,
        )
        if not runs:
            return {}

        best = runs[0]
        return {
            "run_id": best.info.run_id,
            "run_name": best.info.run_name,
            "params": best.data.params,
            "metrics": best.data.metrics,
            "artifact_uri": best.info.artifact_uri,
        }
    except Exception as e:
        logger.warning(f"Could not fetch best run: {e}")
        return {}


if __name__ == "__main__":
    setup_mlflow()

    # Print a quick-start snippet for notebooks
    print("\n" + "=" * 60)
    print("Copy this into your training notebooks:")
    print("=" * 60)
    print("""
import sys
sys.path.append("../scripts")
from setup_mlflow import log_model_run, get_best_run

# After training, log your run:
run_id = log_model_run(
    experiment_name="xgboost_symptom_classifier",
    run_name="xgb_smote_optuna_v1",
    params=best_params,
    metrics={"val_macro_f1": val_f1, "test_macro_f1": test_f1},
    model=best_model,
    model_name="xgboost_symptom",
)
print(f"Run logged: {run_id}")
""")
