from pathlib import Path
import json
import pickle

import faiss
import numpy as np

from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

from location_utils import LocationDatabase


METADATA_FILE = Path("metadata.json")

FAISS_FILE = Path("index.faiss")

TFIDF_VECTORIZER_FILE = Path(
    "tfidf_vectorizer.pkl"
)

TFIDF_MATRIX_FILE = Path(
    "tfidf_matrix.pkl"
)

MODEL_NAME = "all-MiniLM-L6-v2"


# ----------------------------------------------------------
# Search weights / constraints
# ----------------------------------------------------------

SEMANTIC_WEIGHT = 0.70
KEYWORD_WEIGHT = 0.30
SCORE_ACURACY_MINIMUM = 0.55


# ----------------------------------------------------------
# Load everything once
# ----------------------------------------------------------

class SearchEngine:

    def __init__(self):

        print(
            "Loading resources..."
        )

        with open(
            METADATA_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            self.metadata = json.load(f)

        print(
            f"Loaded "
            f"{len(self.metadata)} resources."
        )

        self.faiss_index = faiss.read_index(
            str(FAISS_FILE)
        )

        with open(
            TFIDF_VECTORIZER_FILE,
            "rb"
        ) as f:

            self.tfidf_vectorizer = (
                pickle.load(f)
            )

        with open(
            TFIDF_MATRIX_FILE,
            "rb"
        ) as f:

            self.tfidf_matrix = (
                pickle.load(f)
            )

        print(
            "Loading semantic model..."
        )

        self.model = SentenceTransformer(
            MODEL_NAME
        )

        print(
            "Loading location database..."
        )

        self.location_db = (
            LocationDatabase()
        )

        print(
            "Search engine ready."
        )

    # ======================================================
    # LOCATION FILTER
    # ======================================================

    
    def filter_by_location(self, location_type, location_value):
        """
        Return resource indexes matching ANY selected location.
        A resource is only included once, even if it matches
        multiple selected locations.
        """
        if isinstance(location_value, str):
            location_values = [location_value]
        else:
            location_values = list(location_value or [])

        eligible_indices = []

        for index, resource in enumerate(self.metadata):
            matches = any(
                self.location_db.resource_matches_location(
                    resource,
                    location_type,
                    value
                )
                for value in location_values
            )

            if matches:
                eligible_indices.append(index)

        return eligible_indices


    # ======================================================
    # SCORE NORMALIZATION
    # ======================================================

    @staticmethod
    def normalize_scores(scores):

        scores = np.asarray(
            scores,
            dtype=float
        )

        if len(scores) == 0:

            return scores

        minimum = scores.min()
        maximum = scores.max()

        if (
            maximum - minimum
            < 1e-10
        ):

            return np.zeros_like(
                scores
            )

        return (
            (scores - minimum)
            /
            (maximum - minimum)
        )

    # ======================================================
    # SEARCH
    # ======================================================

    def search(
        self,
        query,
        location_type=None,
        location_value=None,
        top_k=10
    ):
        """
        Perform:

            1. Location filtering
            2. Semantic search
            3. Keyword search
            4. Combined ranking

        Location is NOT part of the search query.
        """

        # --------------------------------------------------
        # 1. LOCATION FILTER
        # --------------------------------------------------

        if location_type and location_value:

            eligible_indices = (
                self.filter_by_location(
                    location_type,
                    location_value
                )
            )

        else:

            # No location filter
            eligible_indices = list(
                range(len(self.metadata))
            )

        if not eligible_indices:

            return []

        # --------------------------------------------------
        # 2. SEMANTIC SEARCH
        # --------------------------------------------------

        query_embedding = self.model.encode(
            [query],
            convert_to_numpy=True,
            normalize_embeddings=True
        )

        # Search all documents because FAISS gives us
        # the document index. We will only retain the
        # eligible ones.

        semantic_scores, semantic_indices = (
            self.faiss_index.search(
                query_embedding,
                len(self.metadata)
            )
        )

        semantic_scores = (
            semantic_scores[0]
        )

        semantic_indices = (
            semantic_indices[0]
        )

        semantic_score_by_resource = (
            np.zeros(
                len(self.metadata),
                dtype=float
            )
        )

        for score, index in zip(
            semantic_scores,
            semantic_indices
        ):

            if index >= 0:

                semantic_score_by_resource[
                    index
                ] = score

        # --------------------------------------------------
        # 3. KEYWORD / TF-IDF SEARCH
        # --------------------------------------------------

        query_tfidf = (
            self.tfidf_vectorizer
            .transform([query])
        )

        keyword_scores = (
            cosine_similarity(
                query_tfidf,
                self.tfidf_matrix
            )[0]
        )

        # --------------------------------------------------
        # 4. ONLY KEEP LOCATION-ELIGIBLE RESOURCES
        # --------------------------------------------------

        eligible_semantic_scores = (
            semantic_score_by_resource[
                eligible_indices
            ]
        )

        eligible_keyword_scores = (
            keyword_scores[
                eligible_indices
            ]
        )

        # --------------------------------------------------
        # 5. NORMALIZE
        # --------------------------------------------------

        semantic_normalized = (
            self.normalize_scores(
                eligible_semantic_scores
            )
        )

        keyword_normalized = (
            self.normalize_scores(
                eligible_keyword_scores
            )
        )

        # --------------------------------------------------
        # 6. COMBINE
        # --------------------------------------------------

        combined_scores = (
            SEMANTIC_WEIGHT
            * semantic_normalized
            +
            KEYWORD_WEIGHT
            * keyword_normalized
        )

        # --------------------------------------------------
        # 7. RANK
        # --------------------------------------------------

        ranked_positions = np.argsort(
            combined_scores
        )[::-1]

        # --------------------------------------------------
        # 8. BUILD RESULTS
        # --------------------------------------------------

        results = []

        for position in ranked_positions:

            # Only include results with a combined score higher than the minimum
            if combined_scores[position] < SCORE_ACURACY_MINIMUM:
                continue

            resource_index = eligible_indices[position]

            resource = self.metadata[resource_index].copy()

            resource["search_score"] = float(
                combined_scores[position]
            )

            resource["semantic_score"] = float(
                semantic_normalized[position]
            )

            resource["keyword_score"] = float(
                keyword_normalized[position]
            )

            results.append(resource)


        return results


# ==========================================================
# SIMPLE COMMAND-LINE INTERFACE
# ==========================================================

def main():

    engine = SearchEngine()

    print()
    print(
        "Location type:"
    )

    print(
        "1. None"
    )

    print(
        "2. Region"
    )

    print(
        "3. County"
    )

    print(
        "4. City"
    )

    choice = input(
        "Choose location type: "
    ).strip()

    location_type = None
    location_value = None

    if choice == "2":

        location_type = "region"

        location_value = input(
            "Enter region: "
        ).strip()

    elif choice == "3":

        location_type = "county"

        location_value = input(
            "Enter county: "
        ).strip()

    elif choice == "4":

        location_type = "city"

        location_value = input(
            "Enter city: "
        ).strip()

    query = input(
        "What does the client need? "
    ).strip()

    results = engine.search(
        query=query,
        location_type=location_type,
        location_value=location_value,
        top_k=10
    )

    print()
    print("=" * 70)
    print("SEARCH RESULTS")
    print("=" * 70)

    if not results:

        print(
            "No resources matched the "
            "selected location."
        )

        return

    for i, resource in enumerate(
        results,
        start=1
    ):

        print()
        print(
            f"{i}. "
            f"{resource['organization']}"
        )

        print(
            f"   Client need: "
            f"{resource['client_need']}"
        )

        print(
            f"   Services: "
            f"{resource['services_provided']}"
        )

        print(
            f"   Persons served: "
            f"{resource['persons_served']}"
        )

        location = resource[
            "location"
        ]

        print(
            f"   Area served: "
            f"{location['raw']}"
        )

        print(
            f"   Combined score: "
            f"{resource['search_score']:.3f}"
        )

        print(
            f"   Semantic score: "
            f"{resource['semantic_score']:.3f}"
        )

        print(
            f"   Keyword score: "
            f"{resource['keyword_score']:.3f}"
        )

        print(
            f"   Contact: "
            f"{resource['contact']}"
        )

        print(
            f"   How to obtain: "
            f"{resource['how_to_obtain']}"
        )


if __name__ == "__main__":
    main()