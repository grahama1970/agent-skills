# toxic-v3

## Goal
Classify online comments as toxic or non-toxic

## Modality
text

## Backbone & HP Recommendations (from /scillm)

Here’s a concise and specific guide for building a text classifier to classify online comments as toxic or non-toxic:

---

### 1. **Top 2-3 Backbone Models (HuggingFace Model Names)**  
These models are pre-trained and fine-tuned for text classification tasks:  
- **`distilbert-base-uncased`**: Lightweight and efficient, great for smaller datasets.  
- **`roberta-base`**: Robust and high-performing for text classification.  
- **`bert-base-uncased`**: A reliable baseline for most NLP tasks.  

---

### 2. **Recommended Hyperparameters**  
- **Learning Rate**: `2e-5` (standard for fine-tuning transformer models).  
- **Epochs**: `3-5` (transformers typically converge quickly; avoid overfitting).  
- **Batch Size**: `16` or `32` (depending on GPU memory; larger batches can improve stability).  

---

### 3. **Minimum Training Samples Needed**  
- **Minimum**: ~1,000 labeled samples (500 toxic, 500 non-toxic) for a basic classifier.  
- **Recommended**: ~10,000+ labeled samples for better generalization and performance.  

---

### 4. **Specific HuggingFace Datasets**  
- **`jigsaw_toxicity_pred`**: Contains labeled toxic/non-toxic comments from Wikipedia discussions.  
- **`civil_comments`**: A dataset of labeled comments from news articles, focusing on toxicity.  
- **`hate_speech18`**: Focuses on hate speech, which can overlap with toxic comments.  

---

### Additional Tips:  
- Use **data augmentation** (e.g., paraphrasing) if labeled data is limited.  
- Evaluate using **F1 score** (especially for imbalanced datasets) or **ROC-AUC**.  
- Consider **class weights** if the dataset is imbalanced.  

Let me know if you need help with the implementation!

## Dataset Search (from /brave-search)

1. google/jigsaw_toxicity_pred · Datasets at Hugging Face
   ... <strong>If words that are associated with swearing, insults or profanity are present in a comment, it is likely that it will be classified as toxic</strong>, regardless of the tone or the intent of the author e.g.
   https://huggingface.co/datasets/google/jigsaw_toxicity_pred

2. unitary/toxic-bert · Hugging Face
   # create data directory mkdir jigsaw_data cd jigsaw_data # download data kaggle competitions download -c jigsaw-toxic-comment-classification-challenge kaggle competitions download -c jigsaw-unintended-bias-in-toxicity-classification kaggle competitions download -c jigsaw-multilingual-toxic-comment-classification
   https://huggingface.co/unitary/toxic-bert

3. thesofakillers/jigsaw-toxic-comment-classification-challenge · Datasets at Hugging Face
   test.csv - the test set, you must predict the toxicity probabilities for these comments. To deter hand labeling, the test set contains some comments which are not 
