"""validate_shadow_mode - scripts.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""


import json
import random
import sys
import os
from pathlib import Path
from typing import List, Dict, Any
from tqdm import tqdm
from loguru import logger
import statistics

# Ensure extractor src is in path (relative to this script in pi-mono/.pi/skills/create-classifier/scripts)
# ../../../../../extractor/src
sys.path.append(str(Path(__file__).parent.parent.parent.parent.parent.parent / "extractor" / "src"))

from extractor.pipeline.steps.s00_profile_detector import run, detect_preset

def load_dataset(jsonl_path: Path) -> List[Dict[str, Any]]:
    samples = []
    with open(jsonl_path) as f:
        for line in f:
            try:
                samples.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return samples

def validate_shadow_mode(dataset_path: Path, sample_size: int = 50):
    """Run shadow mode validation on a random sample of the dataset."""
    
    # 1. Load dataset
    all_samples = load_dataset(dataset_path)
    logger.info(f"Loaded {len(all_samples)} samples from {dataset_path}")
    
    # 2. Filter for existing files
    valid_samples = []
    for s in all_samples:
        path = Path(s["input"]["pdf_path"])
        if path.exists():
            valid_samples.append(s)
            
    logger.info(f"Found {len(valid_samples)} accessible files out of {len(all_samples)}")
    
    if not valid_samples:
        logger.error("No accessible files found for validation.")
        return

    # 3. Sample
    if sample_size > len(valid_samples):
        sample_size = len(valid_samples)
    
    samples = random.sample(valid_samples, sample_size)
    logger.info(f"Validating on {len(samples)} samples...")
    
    # 4. Run validation
    results = []
    
    # Enable shadow mode
    os.environ["USE_PRESET_CLASSIFIER"] = "true"
    
    correct_classifier = 0
    correct_heuristic = 0
    total = 0
    
    for sample in tqdm(samples):
        pdf_path = Path(sample["input"]["pdf_path"])
        ground_truth = sample["label"]
        
        try:
            # Run detection
            # We use detect_preset directly to avoid writing files
            profile = detect_preset(pdf_path)
            
            heuristic_pred = profile.get("detected_preset")
            classifier_info = profile.get("classifier", {})
            classifier_pred = classifier_info.get("classifier_result")
            classifier_conf = classifier_info.get("classifier_confidence", 0.0)
            
            # evaluate
            is_heuristic_correct = (heuristic_pred == ground_truth)
            is_classifier_correct = (classifier_pred == ground_truth)
            
            if is_heuristic_correct:
                correct_heuristic += 1
            if is_classifier_correct:
                correct_classifier += 1
            
            total += 1
            
            results.append({
                "file": pdf_path.name,
                "ground_truth": ground_truth,
                "heuristic": heuristic_pred,
                "classifier": classifier_pred,
                "confidence": classifier_conf,
                "heuristic_correct": is_heuristic_correct,
                "classifier_correct": is_classifier_correct
            })
            
        except Exception as e:
            logger.error(f"Error processing {pdf_path}: {e}")
            
    # 5. Report
    if total == 0:
        logger.warning("No samples processed successfully.")
        return

    acc_heuristic = (correct_heuristic / total) * 100
    acc_classifier = (correct_classifier / total) * 100
    
    print("\n" + "="*60)
    print(f"Validation Results (N={total})")
    print("="*60)
    print(f"Heuristic Accuracy: {acc_heuristic:.2f}%")
    print(f"Classifier Accuracy: {acc_classifier:.2f}%")
    print("-" * 60)
    
    # Detail on mismatches where classifier was correct and heuristic wrong (Value Add)
    value_adds = [r for r in results if r["classifier_correct"] and not r["heuristic_correct"]]
    print(f"\nValue Add Cases (Classifier Correct, Heuristic Wrong): {len(value_adds)}")
    for r in value_adds:
        print(f"  {r['file']}: GT={r['ground_truth']}, Heur={r['heuristic']}, Cls={r['classifier']} ({r['confidence']:.2f})")
        
    # Detail on regressions (Classifier Wrong, Heuristic Correct)
    regressions = [r for r in results if not r["classifier_correct"] and r["heuristic_correct"]]
    print(f"\nRegressions (Classifier Wrong, Heuristic Correct): {len(regressions)}")
    for r in regressions:
        print(f"  {r['file']}: GT={r['ground_truth']}, Heur={r['heuristic']}, Cls={r['classifier']} ({r['confidence']:.2f})")

if __name__ == "__main__":
    # Resolve data path relative to this script
    # Script is in scripts/, data is in data/labels/
    data_dir = Path(__file__).parent.parent / "data" / "labels"
    dataset_path = data_dir / "combined.jsonl"
    
    if not dataset_path.exists():
        logger.error(f"Dataset not found at {dataset_path}")
        # Fallback to CWD relative
        dataset_path = Path("data/labels/combined.jsonl")
        
    validate_shadow_mode(dataset_path, sample_size=50)
