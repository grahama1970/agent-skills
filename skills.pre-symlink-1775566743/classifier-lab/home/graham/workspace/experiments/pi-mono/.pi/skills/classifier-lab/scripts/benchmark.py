"""benchmark - scripts.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

import json
from sklearn.metrics import f1_score
from transformers import pipeline

def main(labels_jsonl, modality, backbones, epochs, lr, batch_size, output_json, store_memory):
    # Load data
    with open(labels_jsonl) as f:
        data = [json.loads(line) for line in f]
    
    texts = [d['text'] for d in data]
    labels = [d['label'] for d in data]
    
    # Initialize classifier
    classifier = pipeline('text-classification', model=backbones)
    
    # Predict
    preds = classifier(texts)
    pred_labels = [1 if p['label'] == 'LABEL_1' else 0 for p in preds]
    
    # Calculate metrics
    f1 = f1_score(labels, pred_labels, average='macro')
    
    # Save results
    result = {
        'selected_metrics': {
            'macro_f1': f1
        }
    }
    with open(output_json, 'w') as f:
        json.dump(result, f)

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--labels-jsonl', required=True)
    parser.add_argument('--modality', required=True)
    parser.add_argument('--backbones', required=True)
    parser.add_argument('--epochs', type=int, required=True)
    parser.add_argument('--lr', type=float, required=True)
    parser.add_argument('--batch-size', type=int, required=True)
    parser.add_argument('--output-json', required=True)
    parser.add_argument('--store-memory', action='store_true')
    args = parser.parse_args()
    
    main(
        args.labels_jsonl,
        args.modality,
        args.backbones,
        args.epochs,
        args.lr,
        args.batch_size,
        args.output_json,
        args.store_memory
    )