# toxic-v4

## Goal
Classify online comments as toxic or non-toxic

## Modality
text

## Backbone & HP Recommendations (from /scillm)

Here’s a concise and specific guide for building a text classifier to classify online comments as toxic or non-toxic:

---

### 1. **Top 2-3 Backbone Models (HuggingFace Model Names)**  
These models are pre-trained and fine-tuned for text classification tasks:  
- **`distilbert-base-uncased`**: Lightweight and efficient, suitable for quick training and deployment.  
- **`roberta-base`**: Robust and high-performing, ideal for more complex datasets.  
- **`bert-base-uncased`**: A reliable baseline model for text classification tasks.  

---

### 2. **Recommended Hyperparameters**  
These are general starting points; adjust based on your dataset size and computational resources:  
- **Learning Rate**: `2e-5` (standard for fine-tuning transformer models).  
- **Epochs**: `3-5` (transformers typically converge quickly; avoid overfitting).  
- **Batch Size**: `16` or `32` (adjust based on GPU memory; smaller batches for larger models).  

---

### 3. **Minimum Training Samples Needed**  
- **Minimum**: ~1,000 labeled samples (500 toxic, 500 non-toxic) for a basic model.  
- **Recommended**: ~10,000+ labeled samples for better generalization and performance.  

---

### 4. **Specific HuggingFace Datasets**  
These datasets are directly relevant for toxic comment classification:  
- **`jigsaw_toxicity_pred`**: A dataset from the Jigsaw Unintended Bias in Toxicity Classification competition.  
- **`hate_speech18`**: A dataset for detecting hate speech and toxic content.  
- **`civil_comments`**: A dataset of labeled comments for toxicity, obscenity, and other attributes.  

---

### Additional Tips:  
- Use **`transformers`** library from HuggingFace for model loading and fine-tuning.  
- Preprocess text by removing special characters, normalizing case, and handling emojis if necessary.  
- Evaluate using metrics like **F1-score** or **ROC-AUC** (common for imbalanced datasets).  

Let me know if you need further details!

## Dataset Search (from /brave-search)

1. google/jigsaw_toxicity_pred · Datasets at Hugging Face
   ... <strong>If words that are associated with swearing, insults or profanity are present in a comment, it is likely that it will be classified as toxic</strong>, regardless of the tone or the intent of the author e.g.
   https://huggingface.co/datasets/google/jigsaw_toxicity_pred

2. unitary/toxic-bert · Hugging Face
   # create data directory mkdir jigsaw_data cd jigsaw_data # download data kaggle competitions download -c jigsaw-toxic-comment-classification-challenge kaggle competitions download -c jigsaw-unintended-bias-in-toxicity-classification kaggle competitions download -c jigsaw-multilingual-toxic-comment-classification
   https://huggingface.co/unitary/toxic-bert

3. thesofakillers/jigsaw-toxic-comment-classification-challenge · Datasets at Hugging Face
   test.csv - the test set, you must predict the toxicity probabilities for these comments. To deter hand labeling, the test set contains some comments which are not 
