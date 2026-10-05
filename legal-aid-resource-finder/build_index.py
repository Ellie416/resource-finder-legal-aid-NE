from pathlib import Path
import json
import pickle

import faiss
import numpy as np

from sentence_transformers import SentenceTransformer
from sklearn.feature_extraction.text import TfidfVectorizer


METADATA_FILE = Path("metadata.json")

FAISS_FILE = Path("index.faiss")

TFIDF_VECTORIZER_FILE = Path(
    "tfidf_vectorizer.pkl"
)

TFIDF_MATRIX_FILE = Path(
    "tfidf_matrix.pkl"
)

MODEL_NAME = "all-MiniLM-L6-v2"


def create_search_text(resource):
    """
    Create the text used by semantic and keyword search.

    IMPORTANT:
    Location is deliberately NOT included here.

    Area served is handled separately by the
    structured location filter.
    """

    return f"""
Client need: {resource["client_need"]}

Organization: {resource["organization"]}

Services provided: {resource["services_provided"]}

Persons served: {resource["persons_served"]}
""".strip()


def build_faiss_index(search_texts):

    print(
        "Loading semantic model..."
    )

    model = SentenceTransformer(
        MODEL_NAME
    )

    print(
        "Creating semantic embeddings..."
    )

    embeddings = model.encode(
        search_texts,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=True
    )

    # Normalized embeddings allow inner product
    # to function as cosine similarity.

    index = faiss.IndexFlatIP(
        embeddings.shape[1]
    )

    index.add(embeddings)

    faiss.write_index(
        index,
        str(FAISS_FILE)
    )

    print(
        f"Saved FAISS index to {FAISS_FILE}"
    )


def build_tfidf_index(search_texts):

    print(
        "Creating TF-IDF keyword index..."
    )

    vectorizer = TfidfVectorizer(
        lowercase=True,
        stop_words="english",
        ngram_range=(1, 2)
    )

    tfidf_matrix = (
        vectorizer.fit_transform(
            search_texts
        )
    )

    with open(
        TFIDF_VECTORIZER_FILE,
        "wb"
    ) as f:

        pickle.dump(
            vectorizer,
            f
        )

    with open(
        TFIDF_MATRIX_FILE,
        "wb"
    ) as f:

        pickle.dump(
            tfidf_matrix,
            f
        )

    print(
        f"Saved TF-IDF vectorizer to "
        f"{TFIDF_VECTORIZER_FILE}"
    )

    print(
        f"Saved TF-IDF matrix to "
        f"{TFIDF_MATRIX_FILE}"
    )


def main():

    print(
        "Loading metadata..."
    )

    with open(
        METADATA_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        metadata = json.load(f)

    print(
        f"Loaded {len(metadata)} resources."
    )

    search_texts = [
        create_search_text(resource)
        for resource in metadata
    ]

    build_faiss_index(
        search_texts
    )

    build_tfidf_index(
        search_texts
    )

    print()
    print(
        "Index building complete."
    )


if __name__ == "__main__":
    main()