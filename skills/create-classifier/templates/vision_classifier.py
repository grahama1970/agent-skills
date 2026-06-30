#!/usr/bin/env python3
"""Module support for the create-classifier skill."""
"""
Vision Classifier Template - Based on successful table classifier architecture

Uses timm library with EfficientNet-B0 backbone (proven success for tables).
Includes confidence head for routing decisions.
"""

import typer
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from PIL import Image
import timm
from loguru import logger
from tqdm import tqdm
import yaml


class HybridClassifier(nn.Module):
    """Multimodal classifier combining vision and text features."""
    
    def __init__(self, num_classes: int, backbone: str = "efficientnet_b0", text_feature_dim: int = 0):
        super().__init__()
        self.backbone = timm.create_model(backbone, pretrained=True, num_classes=0)
        self.text_dim = text_feature_dim
        
        combined_dim = self.backbone.num_features + text_feature_dim
        
        # Classification head
        self.classifier = nn.Linear(combined_dim, num_classes)
        
        # Confidence head
        self.confidence_head = nn.Sequential(
            nn.Linear(combined_dim, 128),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(128, 1),
            nn.Sigmoid()
        )
    
    def forward(self, x, text_features=None):
        vis_features = self.backbone(x)
        
        if self.text_dim > 0 and text_features is not None:
            combined_features = torch.cat([vis_features, text_features], dim=1)
        else:
            combined_features = vis_features
            
        logits = self.classifier(combined_features)
        confidence = self.confidence_head(combined_features).squeeze(1)
        return logits, confidence


class DocumentDataset(Dataset):
    """Dataset for document classification from images."""
    
    def __init__(self, labels_path: Path, transform=None, num_pages: int = 3):
        self.transform = transform
        self.num_pages = num_pages
        
        # Load labels from JSONL
        self.samples = []
        with open(labels_path) as f:
            for line in f:
                sample = json.loads(line)
                self.samples.append(sample)
        
        # Build label->index mapping
        unique_labels = sorted(set(s["label"] for s in self.samples))
        self.label_to_idx = {label: idx for idx, label in enumerate(unique_labels)}
        self.idx_to_label = {idx: label for label, idx in self.label_to_idx.items()}
        
        logger.info(f"Loaded {len(self.samples)} samples with {len(unique_labels)} classes")
        logger.info(f"Classes: {unique_labels}")
    
    def __len__(self):
        return len(self.samples)
    
    def __getitem__(self, idx):
        sample = self.samples[idx]
        
        # Vision extraction (same as before)
        doc_id = sample["id"]
        preset = sample["label"]
        inbox_dir = Path(__file__).parent.parent / "data" / "dataset_inbox" / preset / doc_id
        
        images = []
        if inbox_dir.exists():
            for i in range(1, self.num_pages + 1):
                img_path = inbox_dir / f"page_{i}.jpg"
                if img_path.exists():
                    try:
                        img = Image.open(img_path).convert("RGB")
                        images.append(img)
                    except Exception as e:
                        logger.debug("file read failed: {}", e)
        
        if not images:
            if "image_paths" in sample["input"] and sample["input"]["image_paths"]:
                for img_path in sample["input"]["image_paths"]:
                    try:
                        img = Image.open(img_path).convert("RGB")
                        images.append(img)
                    except Exception as e:
                        logger.warning(f"Failed to load image {img_path}: {e}")
            else:
                pdf_path = sample["input"]["pdf_path"]
                images = self._extract_pages(pdf_path, self.num_pages)
        
        image = images[0] if images else Image.new("RGB", (224, 224))
        if self.transform:
            image = self.transform(image)
            
        # Text feature extraction
        features = sample["input"].get("text_features", {})
        
        # Normalize/One-hot
        # 1. Page count (log-scaled normalization)
        import math
        page_count = features.get("page_count", 1)
        norm_pages = math.log10(max(1, page_count)) / 3.0 # Assuming max 1000 pages
        
        # 2. Binary features
        has_formulas = 1.0 if features.get("has_formulas") else 0.0
        has_tables = 1.0 if features.get("has_tables") else 0.0
        
        # 3. Categorical (Simple one-hot)
        layout_style = features.get("layout", "single")
        is_double = 1.0 if layout_style == "double" else 0.0
        
        section_style = features.get("section_style", "decimal")
        is_roman = 1.0 if section_style == "roman" else 0.0
        
        text_feat_tensor = torch.tensor([
            norm_pages, 
            has_formulas, 
            has_tables, 
            is_double, 
            is_roman
        ], dtype=torch.float32)
        
        label_idx = self.label_to_idx[sample["label"]]
        confidence = sample.get("confidence", 1.0)
        
        return image, text_feat_tensor, label_idx, confidence
    
    def _extract_pages(self, pdf_path: str, num_pages: int) -> List[Image.Image]:
        """Extract first N pages as PIL images."""
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(pdf_path)
            images = []
            
            for page_num in range(min(num_pages, len(doc))):
                page = doc[page_num]
                mat = fitz.Matrix(2, 2)  # 2x zoom for ~224x224
                pix = page.get_pixmap(matrix=mat)
                
                # Convert to PIL Image
                import io
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                img = img.resize((224, 224))
                images.append(img)
            
            doc.close()
            return images
        
        except Exception as e:
            logger.warning(f"Failed to extract pages from {pdf_path}: {e}")
            return [Image.new("RGB", (224, 224))]


def load_config(config_path: Path) -> Dict[str, Any]:
    """Load training configuration from YAML."""
    with open(config_path) as f:
        return yaml.safe_load(f)


def train_epoch(model, dataloader, criterion, optimizer, device):
    """Train for one epoch."""
    model.train()
    total_loss = 0
    correct = 0
    total = 0
    
    pbar = tqdm(dataloader, desc="Training")
    for images, text_feats, labels, confidences in pbar:
        images = images.to(device)
        text_feats = text_feats.to(device)
        labels = labels.to(device)
        confidences = confidences.to(device)
        
        optimizer.zero_grad()
        logits, pred_confidence = model(images, text_feats)
        
        # Classification loss
        cls_loss = criterion(logits, labels)
        
        # Confidence loss (MSE with ground truth confidence)
        conf_loss = nn.MSELoss()(pred_confidence, confidences.float())
        
        # Combined loss
        loss = cls_loss + 0.1 * conf_loss
        
        loss.backward()
        optimizer.step()
        
        total_loss += loss.item()
        _, predicted = logits.max(1)
        correct += predicted.eq(labels).sum().item()
        total += labels.size(0)
        
        pbar.set_postfix({"loss": f"{loss.item():.4f}", "acc": f"{100.*correct/total:.2f}%"})
    
    return total_loss / len(dataloader), 100. * correct / total


def evaluate(model, dataloader, criterion, device):
    """Evaluate model."""
    model.eval()
    total_loss = 0
    correct = 0
    total = 0
    
    with torch.no_grad():
        for images, text_feats, labels, confidences in tqdm(dataloader, desc="Evaluating"):
            images = images.to(device)
            text_feats = text_feats.to(device)
            labels = labels.to(device)
            confidences = confidences.to(device)
            
            logits, pred_confidence = model(images, text_feats)
            
            cls_loss = criterion(logits, labels)
            conf_loss = nn.MSELoss()(pred_confidence, confidences.float())
            loss = cls_loss + 0.1 * conf_loss
            
            total_loss += loss.item()
            _, predicted = logits.max(1)
            correct += predicted.eq(labels).sum().item()
            total += labels.size(0)
    
    return total_loss / len(dataloader), 100. * correct / total


def main(
    config: str = typer.Option(..., help="Path to config YAML"),
    labels: str = typer.Option(..., help="Path to labels JSONL"),
    output: str = typer.Option(Path("models", help="Output directory"),
    device: str = typer.Option("cuda" if torch.cuda.is_available(, help=""),
):
    
    # Load config
    config = load_config(config)
    logger.info(f"Config: {config}")
    
    # Prepare dataset
    from torchvision import transforms
    transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
    ])
    
    dataset = DocumentDataset(labels, transform=transform, num_pages=config["model"].get("num_pages", 3))
    
    # Train/val split
    train_size = int(0.85 * len(dataset))
    val_size = len(dataset) - train_size
    train_dataset, val_dataset = torch.utils.data.random_split(dataset, [train_size, val_size])
    
    train_loader = DataLoader(train_dataset, batch_size=config["training"]["batch_size"], shuffle=True, num_workers=4)
    val_loader = DataLoader(val_dataset, batch_size=config["training"]["batch_size"], shuffle=False, num_workers=4)
    
    # Model
    num_classes = len(dataset.label_to_idx)
    model = HybridClassifier(
        num_classes=num_classes,
        backbone=config["model"]["architecture"],
        text_feature_dim=5 # norm_pages, formulas, tables, double, roman
    ).to(device)
    
    logger.info(f"Model: {config['model']['architecture']}, Classes: {num_classes}")
    
    # Loss and optimizer
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=config["training"]["learning_rate"])
    
    # Training loop
    best_acc = 0
    for epoch in range(config["training"]["epochs"]):
        logger.info(f"\nEpoch {epoch+1}/{config['training']['epochs']}")
        
        train_loss, train_acc = train_epoch(model, train_loader, criterion, optimizer, device)
        val_loss, val_acc = evaluate(model, val_loader, criterion, device)
        
        logger.info(f"Train Loss: {train_loss:.4f}, Train Acc: {train_acc:.2f}%")
        logger.info(f"Val Loss: {val_loss:.4f}, Val Acc: {val_acc:.2f}%")
        
        # Save best model
        if val_acc > best_acc:
            best_acc = val_acc
            save_path = output / config["task"] / "best_model.pt"
            save_path.parent.mkdir(parents=True, exist_ok=True)
            
            torch.save({
                "model_state_dict": model.state_dict(),
                "label_to_idx": dataset.label_to_idx,
                "idx_to_label": dataset.idx_to_label,
                "config": config,
                "epoch": epoch,
                "val_acc": val_acc
            }, save_path)
            
            logger.info(f"Saved best model (acc={val_acc:.2f}%) to {save_path}")
    
    logger.info(f"\nTraining complete. Best val accuracy: {best_acc:.2f}%")


if __name__ == "__main__":
    main()
