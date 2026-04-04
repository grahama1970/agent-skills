# toxic-comments-v2

## Goal
Classify online comments as toxic or non-toxic

## Modality
text

## Backbone & HP Recommendations (from /scillm)

Here’s a concise and specific guide for building a text classifier to classify online comments as toxic or non-toxic:

---

### 1. **Top 2-3 Backbone Models (HuggingFace Model Names)**  
- **`distilbert-base-uncased`**: Lightweight and efficient, great for quick training and deployment.  
- **`roberta-base`**: Strong performance for text classification tasks, especially for toxicity detection.  
- **`bert-base-uncased`**: Reliable and widely used, though slightly slower than DistilBERT.  

---

### 2. **Recommended Hyperparameters**  
- **Learning Rate**: `2e-5` (standard for fine-tuning transformer models).  
- **Epochs**: `3-5` (transformers typically converge quickly; avoid overfitting).  
- **Batch Size**: `16` or `32` (depending on GPU memory; 16 is safer for smaller GPUs).  

---

### 3. **Minimum Training Samples Needed**  
- **Minimum**: ~1,000 labeled samples (500 toxic, 500 non-toxic) for a basic model.  
- **Recommended**: ~10,000+ labeled samples for robust performance.  

---

### 4. **Specific HuggingFace Datasets**  
- **`jigsaw_toxicity_pred`**: A dataset specifically for toxicity classification, available on HuggingFace.  
- **`civil_comments`**: Another dataset for toxic comment classification, also available on HuggingFace.  

---

### Additional Notes:  
- Use **`transformers`** library for model training and **`datasets`** library for data loading.  
- Preprocess data by removing special characters, normalizing text, and balancing classes if necessary.  
- Evaluate using metrics like **F1-score** or **ROC-AUC** (important for imbalanced datasets).  

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
