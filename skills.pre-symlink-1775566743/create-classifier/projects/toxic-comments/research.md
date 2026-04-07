# toxic-comments

## Goal
Classify online comments as toxic or non-toxic

## Modality
text

## Backbone & HP Recommendations (from /scillm)

No LLM recommendations available.

## Dataset Search (from /brave-search)

1. google/jigsaw_toxicity_pred · Datasets at Hugging Face
   ... <strong>If words that are associated with swearing, insults or profanity are present in a comment, it is likely that it will be classified as toxic</strong>, regardless of the tone or the intent of the author e.g.
   https://huggingface.co/datasets/google/jigsaw_toxicity_pred

2. unitary/toxic-bert · Hugging Face
   # create data directory mkdir jigsaw_data cd jigsaw_data # download data kaggle competitions download -c jigsaw-toxic-comment-classification-challenge kaggle competitions download -c jigsaw-unintended-bias-in-toxicity-classification kaggle competitions download -c jigsaw-multilingual-toxic-comment-classification
   https://huggingface.co/unitary/toxic-bert

3. thesofakillers/jigsaw-toxic-comment-classification-challenge · Datasets at Hugging Face
   test.csv - the test set, you must predict the toxicity probabilities for these comments. To deter hand labeling, the test set contains some comments which are not 
