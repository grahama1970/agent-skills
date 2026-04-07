#!/usr/bin/env python3
"""train_hybrid - scripts.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

import os
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from transformers import AutoTokenizer, get_linear_schedule_with_warmup
import json
import yaml
import typer
from pathlib import Path
from loguru import logger
import numpy as np
from tqdm import tqdm
from sklearn.metrics import f1_score, classification_report

app = typer.Typer()

from templates.hybrid_classifier import HybridStructuralClassifier

class StructuralDataset(Dataset):
    def __init__(self, data_path, tokenizer, max_length=256):
        self.samples = []
        with open(data_path, 'r') as f:
            for line in f:
                self.samples.append(json.loads(line))
        self.tokenizer = tokenizer
        self.max_length = max_length
        self.label_map = {"Header": 0, "Footnote": 1, "Reference": 2, "BodyText": 3}
        
    def __len__(self):
        return len(self.samples)
    
    def __getitem__(self, idx):
        sample = self.samples[idx]
        text = sample["input"]["text"]
        label = self.label_map.get(sample["label"], 3)
        
        # Layout features: [bbox(4), y_pos_rel, block_width_rel, size, body_size_ref, is_bold, flags]
        layout = sample["input"]["layout"]
        font = sample["input"]["font"]
        layout_features = [
            *layout["bbox"],
            layout["y_pos_rel"],
            layout["block_width_rel"],
            font["size"],
            font["body_size_ref"],
            1.0 if font["is_bold"] else 0.0,
            float(font.get("flags", 0))
        ]
        
        tokens = self.tokenizer(
            text, 
            padding="max_length", 
            truncation=True, 
            max_length=self.max_length, 
            return_tensors="pt"
        )
        
        return {
            "input_ids": tokens["input_ids"].squeeze(0),
            "attention_mask": tokens["attention_mask"].squeeze(0),
            "layout_features": torch.tensor(layout_features, dtype=torch.float32),
            "labels": torch.tensor(label, dtype=torch.long)
        }

def train(config_path: Path, data_path: Path):
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    tokenizer = AutoTokenizer.from_pretrained(config["model"]["text_encoder"])
    dataset = StructuralDataset(data_path, tokenizer)
    
    # Split dataset
    train_size = int(0.8 * len(dataset))
    val_size = len(dataset) - train_size
    train_set, val_set = torch.utils.data.random_split(dataset, [train_size, val_size])
    
    train_loader = DataLoader(train_set, batch_size=config["training"]["batch_size"], shuffle=True)
    val_loader = DataLoader(val_set, batch_size=config["training"]["batch_size"])
    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = HybridStructuralClassifier(config).to(device)
    
    optimizer = torch.optim.AdamW(model.parameters(), lr=float(config["training"]["learning_rate"]))
    criterion = nn.CrossEntropyLoss()
    
    num_epochs = config["training"].get("epochs", 10)
    logger.info(f"Starting training for {num_epochs} epochs on {device}")
    
    for epoch in range(num_epochs):
        model.train()
        total_loss = 0
        pbar = tqdm(train_loader, desc=f"Epoch {epoch+1}")
        
        for batch in pbar:
            optimizer.zero_grad()
            
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            layout_features = batch["layout_features"].to(device)
            labels = batch["labels"].to(device)
            
            logits = model(input_ids, attention_mask, layout_features)
            loss = criterion(logits, labels)
            
            loss.backward()
            optimizer.step()
            
            total_loss += loss.item()
            pbar.set_postfix({"loss": f"{loss.item():.4f}"})
            
        # Validation
        model.eval()
        val_preds = []
        val_labels = []
        with torch.no_grad():
            for batch in val_loader:
                input_ids = batch["input_ids"].to(device)
                attention_mask = batch["attention_mask"].to(device)
                layout_features = batch["layout_features"].to(device)
                labels = batch["labels"].to(device)
                
                logits = model(input_ids, attention_mask, layout_features)
                preds = torch.argmax(logits, dim=1)
                
                val_preds.extend(preds.cpu().numpy())
                val_labels.extend(labels.cpu().numpy())
                
        f1 = f1_score(val_labels, val_preds, average="macro")
        logger.info(f"Epoch {epoch+1} finished. Val F1: {f1:.4f}")
        logger.info("\n" + classification_report(val_labels, val_preds, target_names=dataset.label_map.keys()))
        
        # Save checkpoint
        torch.save(model.state_dict(), f"models/structural_epoch_{epoch+1}.pt")

@app.command()
def main(
    config: Path = typer.Option(..., help="Path to config YAML file"),
    data: Path = typer.Option(..., help="Path to training data JSONL"),
):
    """Train hybrid structural classifier."""
    os.makedirs("models", exist_ok=True)
    train(config, data)


if __name__ == "__main__":
    app()
