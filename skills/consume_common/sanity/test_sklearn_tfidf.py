#!/usr/bin/env python3
"""Sanity test for scikit-learn - TF-IDF vectorization."""


def test_sklearn_tfidf():
    """Test that sklearn can perform TF-IDF vectorization."""
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
    except ImportError:
        print("FAIL: scikit-learn not installed")
        print("Install with: pip install scikit-learn")
        return False

    try:
        # Sample documents
        documents = [
            "The quick brown fox jumps over the lazy dog",
            "A quick brown dog runs in the park",
            "The lazy cat sleeps on the couch",
            "Foxes are quick and dogs are lazy"
        ]

        # Create TF-IDF vectors
        vectorizer = TfidfVectorizer(stop_words='english')
        tfidf_matrix = vectorizer.fit_transform(documents)

        # Verify shape
        assert tfidf_matrix.shape[0] == 4, f"Expected 4 documents, got {tfidf_matrix.shape[0]}"
        assert tfidf_matrix.shape[1] > 0, f"Expected >0 features, got {tfidf_matrix.shape[1]}"

        # Compute similarity between first two documents
        similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])
        assert similarity[0][0] > 0, f"Expected positive similarity, got {similarity[0][0]}"

        # Check feature names
        feature_names = vectorizer.get_feature_names_out()
        assert len(feature_names) > 0, "No feature names extracted"

        print(f"PASS: TF-IDF vectorization successful")
        print(f"  - Documents: {tfidf_matrix.shape[0]}")
        print(f"  - Features: {tfidf_matrix.shape[1]}")
        print(f"  - Similarity (doc0-doc1): {similarity[0][0]:.3f}")
        return True

    except Exception as e:
        print(f"FAIL: Error with sklearn: {e}")
        return False


if __name__ == "__main__":
    success = test_sklearn_tfidf()
    exit(0 if success else 1)
