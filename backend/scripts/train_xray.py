"""
backend/scripts/train_xray.py

SageMaker training entry point for ResNet-50 X-ray classifier.

Dataset: NIH ChestX-ray14 on S3:
    s3://mediassist-ml/raw/chestxray14/images/
    s3://mediassist-ml/raw/chestxray14/Data_Entry_2017.csv
    s3://mediassist-ml/raw/chestxray14/train_val_list.txt
    s3://mediassist-ml/raw/chestxray14/test_list.txt

SageMaker channels:
    /opt/ml/input/data/training/   → images + CSVs
    /opt/ml/model/                 → saved model output

Run via sagemaker_launch.py — do NOT run this locally.

Architecture decisions (S5):
- Freeze ResNet-50 layer1, layer2, layer3 (load pretrained from torchvision)
- Fine-tune layer4 + FC layer (replace FC with nn.Linear(2048, 14))
- Differential LRs: FC head 1e-3, layer4 1e-4
- Loss: BCEWithLogitsLoss with pos_weight (neg/pos per class)
- Augmentations: HorizontalFlip, Rotate ±10°, RandomBrightnessContrast
  FORBIDDEN: vertical flip, random crop (anatomically invalid)
- LR schedule: CosineAnnealingLR(T_max=20)
- Metrics: AUC-ROC per class + mean-AUC (NOT accuracy)
- Early stop: if val mean-AUC doesn't improve for 5 epochs
- Checkpoint: best val mean-AUC model saved every epoch
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("train_xray")

# ── NIH ChestX-ray14 class labels (14 classes) ───────────────────────────
CLASSES = [
    "Atelectasis", "Cardiomegaly", "Consolidation", "Edema", "Effusion",
    "Emphysema", "Fibrosis", "Hernia", "Infiltration", "Mass",
    "No Finding", "Nodule", "Pleural_Thickening", "Pneumonia", "Pneumothorax",
]
N_CLASSES = len(CLASSES)


# ═══════════════════════════════════════════════════════════════════════════
# Dataset
# ═══════════════════════════════════════════════════════════════════════════

class ChestXrayDataset:
    """NIH ChestX-ray14 multi-label dataset loaded from SageMaker input channel."""

    def __init__(self, data_dir: str, image_list: list, transform=None):
        import torch
        from PIL import Image
        self.data_dir = Path(data_dir)
        self.image_list = image_list  # List of (filename, label_vector)
        self.transform = transform
        self.Image = Image
        self.torch = torch
        
        # The Kaggle dataset splits images across folders like images_001/images/, images_002/images/
        # Build a map of filename -> full absolute path
        self.image_map = {}
        for img_path in self.data_dir.rglob("*.png"):
            self.image_map[img_path.name] = img_path

    def __len__(self):
        return len(self.image_list)

    def __getitem__(self, idx):
        img_name, label_vec = self.image_list[idx]
        
        # Use the absolute path from our map if found, else fallback to standard path
        full_path = self.image_map.get(img_name, self.data_dir / img_name)
        
        # Grayscale → RGB (X-rays are grayscale)
        img = self.Image.open(full_path).convert("RGB")
        if self.transform:
            img = self.transform(image=np.array(img))["image"]
        return img, self.torch.tensor(label_vec, dtype=self.torch.float32)


def parse_labels(csv_path: str, image_dir: str, split_list_path: str) -> list:
    """
    Parse NIH Data_Entry_2017.csv and return list of (filename, label_vector).

    Args:
        csv_path: Path to Data_Entry_2017.csv
        image_dir: Path to images directory
        split_list_path: Path to train_val_list.txt or test_list.txt

    Returns:
        List of (relative_image_path, np.array of shape [14]) tuples
    """
    df = pd.read_csv(csv_path)
    df.columns = df.columns.str.strip()

    # Build set of allowed image filenames
    with open(split_list_path) as f:
        allowed = set(line.strip() for line in f if line.strip())

    df = df[df["Image Index"].isin(allowed)].reset_index(drop=True)
    logger.info(f"Loaded {len(df)} images from {split_list_path}")

    samples = []
    for _, row in df.iterrows():
        fname = row["Image Index"]
        findings = row["Finding Labels"].split("|")
        label_vec = np.zeros(N_CLASSES, dtype=np.float32)
        for finding in findings:
            finding = finding.strip()
            if finding in CLASSES:
                label_vec[CLASSES.index(finding)] = 1.0
        samples.append((fname, label_vec))

    return samples


def compute_pos_weights(samples: list) -> "torch.Tensor":
    """Compute pos_weight = (# negatives) / (# positives) per class."""
    import torch
    labels = np.stack([s[1] for s in samples], axis=0)  # (N, 14)
    pos_count = labels.sum(axis=0)  # (14,)
    neg_count = len(labels) - pos_count  # (14,)
    pos_weight = neg_count / (pos_count + 1e-6)
    pos_weight = np.clip(pos_weight, 1.0, 50.0)  # Cap extreme weights
    logger.info(f"Pos weights range: [{pos_weight.min():.1f}, {pos_weight.max():.1f}]")
    return torch.tensor(pos_weight, dtype=torch.float32)


# ═══════════════════════════════════════════════════════════════════════════
# Model
# ═══════════════════════════════════════════════════════════════════════════

def build_model(n_classes: int = N_CLASSES):
    """
    Build ResNet-50 with:
    - Pretrained ImageNet weights
    - Layers 1-3 frozen
    - Layer 4 + new FC head trainable
    - FC replaced with Linear(2048, n_classes)
    """
    import torch.nn as nn
    from torchvision import models

    model = models.resnet50(weights=models.ResNet50_Weights.IMAGENET1K_V2)

    # Freeze layers 1, 2, 3
    for name, param in model.named_parameters():
        if any(name.startswith(f"layer{i}") for i in [1, 2, 3]):
            param.requires_grad = False
        elif name.startswith("conv1") or name.startswith("bn1"):
            param.requires_grad = False

    # Replace FC head with 14-class output
    model.fc = nn.Linear(model.fc.in_features, n_classes)

    # Log trainable vs frozen params
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    logger.info(f"Model: {trainable:,} trainable / {total:,} total parameters")

    return model


def get_optimizer(model):
    """
    Differential learning rates (S5 decision):
    - New FC head: lr=1e-3
    - Fine-tuned layer4: lr=1e-4
    - Frozen layers: not included
    """
    import torch.optim as optim

    param_groups = [
        {"params": model.fc.parameters(), "lr": 1e-3, "name": "fc_head"},
        {"params": model.layer4.parameters(), "lr": 1e-4, "name": "layer4"},
    ]
    optimizer = optim.Adam(param_groups, weight_decay=1e-4)
    return optimizer


# ═══════════════════════════════════════════════════════════════════════════
# Training loop
# ═══════════════════════════════════════════════════════════════════════════

def compute_auc(labels: np.ndarray, scores: np.ndarray) -> dict:
    """Compute per-class and mean AUC-ROC."""
    from sklearn.metrics import roc_auc_score

    aucs = {}
    for i, cls in enumerate(CLASSES):
        y_true = labels[:, i]
        y_score = scores[:, i]
        if y_true.sum() == 0 or y_true.sum() == len(y_true):
            aucs[cls] = float("nan")
        else:
            aucs[cls] = roc_auc_score(y_true, y_score)

    valid_aucs = [v for v in aucs.values() if not np.isnan(v)]
    aucs["mean_auc"] = np.mean(valid_aucs) if valid_aucs else 0.0
    return aucs


def train_epoch(model, loader, criterion, optimizer, device):
    """Train for one epoch. Returns average loss."""
    import torch

    model.train()
    total_loss = 0.0
    n_batches = 0

    for images, labels in loader:
        images, labels = images.to(device), labels.to(device)
        optimizer.zero_grad()
        logits = model(images)
        loss = criterion(logits, labels)
        loss.backward()
        optimizer.step()
        total_loss += loss.item()
        n_batches += 1

    return total_loss / max(n_batches, 1)


def eval_epoch(model, loader, criterion, device):
    """Evaluate for one epoch. Returns loss + AUC dict."""
    import torch

    model.eval()
    total_loss = 0.0
    all_labels = []
    all_scores = []
    n_batches = 0

    with torch.no_grad():
        for images, labels in loader:
            images, labels = images.to(device), labels.to(device)
            logits = model(images)
            loss = criterion(logits, labels)
            scores = torch.sigmoid(logits)
            total_loss += loss.item()
            all_labels.append(labels.cpu().numpy())
            all_scores.append(scores.cpu().numpy())
            n_batches += 1

    all_labels = np.concatenate(all_labels, axis=0)
    all_scores = np.concatenate(all_scores, axis=0)
    avg_loss = total_loss / max(n_batches, 1)
    auc_dict = compute_auc(all_labels, all_scores)
    return avg_loss, auc_dict


# ═══════════════════════════════════════════════════════════════════════════
# MLflow integration
# ═══════════════════════════════════════════════════════════════════════════

def setup_mlflow(tracking_uri: str, experiment_name: str):
    """Configure MLflow for SageMaker training."""
    try:
        import mlflow
        mlflow.set_tracking_uri(tracking_uri)
        mlflow.set_experiment(experiment_name)
        logger.info(f"MLflow tracking: {tracking_uri} / {experiment_name}")
        return True
    except Exception as e:
        logger.warning(f"MLflow not available: {e}. Continuing without experiment tracking.")
        return False


# ═══════════════════════════════════════════════════════════════════════════
# Main training function
# ═══════════════════════════════════════════════════════════════════════════

def main(args):
    import torch
    import torch.nn as nn
    import albumentations as A
    from albumentations.pytorch import ToTensorV2
    from torch.utils.data import DataLoader, random_split
    from torch.optim.lr_scheduler import CosineAnnealingLR

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info(f"Training on device: {device}")

    # ── Paths ──────────────────────────────────────────────────────────────
    data_dir = Path(args.data_dir)
    model_dir = Path(args.model_dir)
    model_dir.mkdir(parents=True, exist_ok=True)

    csv_path = data_dir / "Data_Entry_2017.csv"
    train_list = data_dir / "train_val_list.txt"
    test_list = data_dir / "test_list.txt"

    # ── Load data ──────────────────────────────────────────────────────────
    train_samples = parse_labels(str(csv_path), str(data_dir), str(train_list))
    test_samples = parse_labels(str(csv_path), str(data_dir), str(test_list))

    # Split train → train + val (85/15)
    n_val = max(1, int(len(train_samples) * 0.15))
    n_train = len(train_samples) - n_val
    # Deterministic split (same random seed as training run)
    rng = np.random.RandomState(42)
    idx = rng.permutation(len(train_samples))
    val_samples = [train_samples[i] for i in idx[:n_val]]
    train_samples = [train_samples[i] for i in idx[n_val:]]
    logger.info(f"Split: {len(train_samples)} train / {len(val_samples)} val / {len(test_samples)} test")

    # ── Augmentations (S5 decision — X-ray valid only) ────────────────────
    train_transform = A.Compose([
        A.HorizontalFlip(p=0.5),                         # ✅ valid — lung pathology appears in both orientations
        A.Rotate(limit=10, p=0.3),                        # ✅ valid — mimics patient positioning variance
        A.RandomBrightnessContrast(p=0.3),                # ✅ valid — exposure variation
        # ❌ NO vertical flip — anatomically impossible (heart on wrong side)
        # ❌ NO random crop — removes lung edges where pathology hides
        A.Resize(224, 224),
        A.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ToTensorV2(),
    ])
    val_transform = A.Compose([
        A.Resize(224, 224),
        A.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ToTensorV2(),
    ])

    train_ds = ChestXrayDataset(data_dir, train_samples, transform=train_transform)
    val_ds = ChestXrayDataset(data_dir, val_samples, transform=val_transform)
    test_ds = ChestXrayDataset(data_dir, test_samples, transform=val_transform)

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True, num_workers=4, pin_memory=True)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False, num_workers=4, pin_memory=True)
    test_loader = DataLoader(test_ds, batch_size=args.batch_size, shuffle=False, num_workers=2, pin_memory=True)

    # ── Model, optimizer, loss ────────────────────────────────────────────
    model = build_model(N_CLASSES).to(device)
    optimizer = get_optimizer(model)

    # Compute class-balanced pos_weight (S5 decision)
    pos_weight = compute_pos_weights(train_samples).to(device)
    criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)

    scheduler = CosineAnnealingLR(optimizer, T_max=args.epochs)

    # ── MLflow ────────────────────────────────────────────────────────────
    mlflow_enabled = setup_mlflow(args.mlflow_uri, "resnet50_xray_classifier")
    if mlflow_enabled:
        import mlflow
        with mlflow.start_run(run_name=f"resnet50_xray_e{args.epochs}_b{args.batch_size}"):
            mlflow.log_params({
                "epochs": args.epochs,
                "batch_size": args.batch_size,
                "lr_fc": 1e-3,
                "lr_layer4": 1e-4,
                "frozen_layers": "layer1,layer2,layer3",
                "loss": "BCEWithLogitsLoss",
                "augmentations": "HFlip,Rotate10,BrightnessContrast",
                "scheduler": "CosineAnnealingLR",
                "early_stop_patience": args.patience,
            })
            _train_loop(
                model, optimizer, scheduler, criterion, device,
                train_loader, val_loader, test_loader, model_dir, args, mlflow
            )
    else:
        _train_loop(
            model, optimizer, scheduler, criterion, device,
            train_loader, val_loader, test_loader, model_dir, args, None
        )


def _train_loop(model, optimizer, scheduler, criterion, device,
                train_loader, val_loader, test_loader, model_dir, args, mlflow):
    """Core training loop with checkpointing and early stopping."""
    import torch

    best_val_auc = 0.0
    epochs_no_improve = 0
    best_epoch = 0
    metrics_history = []

    for epoch in range(1, args.epochs + 1):
        # ── Train ──────────────────────────────────────────────────────────
        train_loss = train_epoch(model, train_loader, criterion, optimizer, device)
        scheduler.step()

        # ── Validate ───────────────────────────────────────────────────────
        val_loss, val_aucs = eval_epoch(model, val_loader, criterion, device)
        val_mean_auc = val_aucs["mean_auc"]

        logger.info(
            f"Epoch {epoch:02d}/{args.epochs} | "
            f"train_loss={train_loss:.4f} | "
            f"val_loss={val_loss:.4f} | "
            f"val_mean_auc={val_mean_auc:.4f}"
        )

        # Log per-class AUCs
        per_class_log = {f"val_auc_{cls}": v for cls, v in val_aucs.items() if cls != "mean_auc"}
        epoch_metrics = {
            "epoch": epoch,
            "train_loss": train_loss,
            "val_loss": val_loss,
            "val_mean_auc": val_mean_auc,
            **per_class_log,
        }
        metrics_history.append(epoch_metrics)

        if mlflow:
            mlflow.log_metrics({"train_loss": train_loss, "val_loss": val_loss, "val_mean_auc": val_mean_auc}, step=epoch)
            mlflow.log_metrics(per_class_log, step=epoch)

        # ── Checkpoint best model ──────────────────────────────────────────
        if val_mean_auc > best_val_auc:
            best_val_auc = val_mean_auc
            best_epoch = epoch
            epochs_no_improve = 0
            ckpt_path = model_dir / "resnet50_xray_best.pt"
            scripted = torch.jit.script(model)
            scripted.save(str(ckpt_path))
            logger.info(f"  ✓ New best val mean-AUC={best_val_auc:.4f} — checkpoint saved")
        else:
            epochs_no_improve += 1
            logger.info(f"  No improvement ({epochs_no_improve}/{args.patience})")

        # Save every-epoch checkpoint for spot interruption recovery
        torch.save({
            "epoch": epoch,
            "model_state_dict": model.state_dict(),
            "optimizer_state_dict": optimizer.state_dict(),
            "best_val_auc": best_val_auc,
        }, model_dir / "checkpoint_latest.pth")

        # ── Early stopping ─────────────────────────────────────────────────
        if epochs_no_improve >= args.patience:
            logger.info(f"Early stopping at epoch {epoch} (no improvement for {args.patience} epochs)")
            break

    # ── Final evaluation on test set (touch only once!) ───────────────────
    logger.info(f"\nBest model: epoch {best_epoch}, val mean-AUC={best_val_auc:.4f}")
    logger.info("Evaluating best model on TEST set (held out — touching only once)...")

    # Load best model
    best_model_path = model_dir / "resnet50_xray_best.pt"
    best_model = torch.jit.load(str(best_model_path), map_location=device)
    test_loss, test_aucs = eval_epoch(best_model, test_loader, criterion, device)

    logger.info(f"\n{'='*60}")
    logger.info(f"TEST RESULTS (best model from epoch {best_epoch})")
    logger.info(f"{'='*60}")
    logger.info(f"Test loss: {test_loss:.4f}")
    logger.info(f"Test mean AUC-ROC: {test_aucs['mean_auc']:.4f}")
    logger.info(f"\nPer-class AUC-ROC:")
    for cls, auc in sorted(test_aucs.items(), key=lambda x: x[1] if not np.isnan(x[1] if isinstance(x[1], float) else 0) else 0):
        if cls != "mean_auc":
            logger.info(f"  {cls:30s}: {auc:.4f}" if not np.isnan(auc) else f"  {cls:30s}: N/A")
    logger.info(f"{'='*60}")

    if mlflow:
        mlflow.log_metrics({f"test_auc_{cls}": v for cls, v in test_aucs.items()})
        mlflow.log_metric("test_mean_auc", test_aucs["mean_auc"])

    # Save final model (renamed from best)
    final_path = model_dir / "resnet50_xray.pt"
    import shutil
    shutil.copy(str(best_model_path), str(final_path))

    # Save metrics JSON for reference
    results = {
        "best_epoch": int(best_epoch),
        "best_val_mean_auc": float(best_val_auc),
        "test_mean_auc": float(test_aucs["mean_auc"]),
        "test_per_class_auc": {k: float(v) for k, v in test_aucs.items() if k != "mean_auc"},
        "target_met": bool(test_aucs["mean_auc"] >= 0.80),
    }
    with open(model_dir / "training_results.json", "w") as f:
        json.dump(results, f, indent=2)

    logger.info(f"\n{'✓' if results['target_met'] else '✗'} Target (mean AUC ≥ 0.80): {results['target_met']}")
    logger.info(f"Model saved to: {final_path}")


# ═══════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    # SageMaker passes these as environment variables / CLI args
    parser.add_argument("--data-dir", type=str, default=os.environ.get("SM_CHANNEL_TRAINING", "/opt/ml/input/data/training"))
    parser.add_argument("--model-dir", type=str, default=os.environ.get("SM_MODEL_DIR", "/opt/ml/model"))
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--patience", type=int, default=5)
    parser.add_argument("--mlflow-uri", type=str, default=os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000"))

    args = parser.parse_args()
    logger.info(f"Training args: {vars(args)}")

    main(args)
