"""hybrid_classifier - templates.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

import torch
import torch.nn as nn
from transformers import AutoModel, AutoConfig

class HybridStructuralClassifier(nn.Module):
    def __init__(self, config):
        super().__init__()
        self.config = config
        
        # 1. Text Encoder (Backbone)
        text_model_name = config.get("model", {}).get("text_encoder", "microsoft/deberta-v3-small")
        self.text_config = AutoConfig.from_pretrained(text_model_name)
        self.text_encoder = AutoModel.from_pretrained(text_model_name)
        
        # 2. Layout Encoder (MLP)
        # Features: [bbox(4), y_pos_rel, block_width_rel, size, body_size_ref, is_bold, flags]
        # Total features: 4 + 1 + 1 + 1 + 1 + 1 + 1 = 10
        layout_input_dim = 10 
        layout_hidden_dims = [64, 128]
        
        layers = []
        input_dim = layout_input_dim
        for h_dim in layout_hidden_dims:
            layers.append(nn.Linear(input_dim, h_dim))
            layers.append(nn.ReLU())
            layers.append(nn.Dropout(0.1))
            input_dim = h_dim
        self.layout_encoder = nn.Sequential(*layers)
        
        # 3. Fusion and Classifier
        fusion_dim = self.text_config.hidden_size + layout_hidden_dims[-1]
        classifier_hidden_dims = config.get("model", {}).get("hidden_dims", [256, 128])
        
        classifier_layers = []
        input_dim = fusion_dim
        for h_dim in classifier_hidden_dims:
            classifier_layers.append(nn.Linear(input_dim, h_dim))
            classifier_layers.append(nn.ReLU())
            classifier_layers.append(nn.Dropout(0.15))
            input_dim = h_dim
            
        num_classes = len(config.get("classes", ["Header", "Footnote", "Reference", "BodyText"]))
        classifier_layers.append(nn.Linear(input_dim, num_classes))
        
        self.classifier = nn.Sequential(*classifier_layers)
        
    def forward(self, input_ids, attention_mask, layout_features):
        # Text encoding
        text_outputs = self.text_encoder(input_ids=input_ids, attention_mask=attention_mask)
        text_features = text_outputs.last_hidden_state[:, 0, :] # CLS token
        
        # Layout encoding
        layout_emb = self.layout_encoder(layout_features)
        
        # Fusion
        combined = torch.cat([text_features, layout_emb], dim=1)
        
        # Classification
        logits = self.classifier(combined)
        return logits
