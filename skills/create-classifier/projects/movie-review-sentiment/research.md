# movie-review-sentiment

## Goal
Classify movie reviews as positive or negative

## Modality
text

## Research (from /dogpile)

Found prior research on this topic in memory.
## Memory Recall (Prior Solutions Found)

1. **Problem**: Classifier training used random datalake chunks as negatives 
which polluted the negative class with real requirements — precision dropped 
beca...
Dogpiling on: text classifier for: Classify movie reviews as positive or 
negative. What HuggingFace datasets exist? What backbone models work best? 
Recommended hyperparameters for fine-tuning? (Code Related: True)...
Tailored queries:
  arxiv: sentiment analysis transformers BERT fine-tuning text classi...
  perplexity: What are the best HuggingFace datasets and pretrained models...
  brave: HuggingFace datasets sentiment movie reviews documentation 2...
  github: transformers AutoModelForSequenceClassification fine-tune se...
  youtube: how to fine-tune BERT for movie review sentiment classificat...
  readarr: Natural Language Processing with Transformers sentiment anal...
# Dogpile Report: text classifier for: Classify movie reviews as positive or negative. What HuggingFace datasets exist? What backbone models work best? Recommended hyperparameters for fine-tuning?

## Codex Technical Overview
Of course. Here is a high-reasoning technical overview of building a text classifier for movie reviews, focusing on HuggingFace resources, architectural patterns, pitfalls, and state-of-the-art approaches.

### Executive Summary

Classifying movie reviews is a canonical binary text classification task (sentiment analysis). While seemingly simple, achieving high performance requires understanding the nuances of modern Transformer architectures, data handling, and fine-tuning strategies. The dominant approach has shifted from statistical methods (like Naive Bayes with TF-IDF) to fine-tuning large pre-trained language models (LLMs). This overview will dissect the modern approach.

---

### 1. HuggingFace Datasets: The Proving Grounds

HuggingFace Datasets provides standardized, easy-to-load datasets, which are essential for reproducible research and development.

| Dataset Name | Description & Nuances | Best For |
| :--- | :--- | :--- |
| **`imdb`** | **The De Facto Standard.** Contains 25k training and 25k testing reviews. **Crucial Internal Knowledge:** Reviews are often long (multiple paragraphs), exceeding the 512-token limit of standard models like BERT. This makes it an excellent test case for long-text handling. The data is also relatively clean and well-balanced. | A robust, general-purpose benchmark, especially for testing long-text strategies. |
| **`rotten_tomatoes`** | Sourced from Rotten Tomatoes. Contains ~10k reviews. **Crucial Internal Knowledge:** The reviews are much shorter, often single sentences. This makes it a faster task to train on and less susceptible to the 512-token limit. However, it may not generalize well to models intended for longer, more detailed user feedback. | Quick baselining, and tasks where input text is expected to be short and concise. |
| **`sst2` (GLUE Benchmark)** 
