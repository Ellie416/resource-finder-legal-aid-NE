
from pathlib import Path
import json
import os
import subprocess
import sys
import uuid

import faiss

from resource_source import load_resources


PROJECT_DIR = Path(__file__).resolve().parent
INDEX_ROOT = PROJECT_DIR / "indexes"
VERSIONS_DIR = INDEX_ROOT / "versions"
ACTIVE_VERSION_FILE = INDEX_ROOT / "active_version.json"

BUILD_SCRIPT = PROJECT_DIR / "build_index.py"

REQUIRED_FILES = [
    "metadata.json",
    "index.faiss",
    "tfidf_vectorizer.pkl",
    "tfidf_matrix.pkl",
]


def write_metadata(resources, output_file):
    with open(output_file, "w", encoding="utf-8") as file:
        json.dump(
            resources,
            file,
            indent=2,
            ensure_ascii=False
        )


def validate_artifacts(build_dir):
    for filename in REQUIRED_FILES:
        path = build_dir / filename

        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(
                f"Missing or empty artifact: {filename}"
            )

    with open(
        build_dir / "metadata.json",
        "r",
        encoding="utf-8"
    ) as file:
        metadata = json.load(file)

    if not isinstance(metadata, list) or not metadata:
        raise RuntimeError("Metadata is empty or invalid.")

    index = faiss.read_index(str(build_dir / "index.faiss"))

    if index.ntotal != len(metadata):
        raise RuntimeError(
            "FAISS index and metadata resource counts differ."
        )

    # Verify the pickle files can be loaded by the existing
    # application's Python environment.
    import pickle

    with open(build_dir / "tfidf_vectorizer.pkl", "rb") as file:
        vectorizer = pickle.load(file)

    with open(build_dir / "tfidf_matrix.pkl", "rb") as file:
        matrix = pickle.load(file)

    if matrix.shape[0] != len(metadata):
        raise RuntimeError(
            "TF-IDF row count does not match metadata."
        )

    if matrix.shape[1] != len(vectorizer.get_feature_names_out()):
        raise RuntimeError(
            "TF-IDF matrix and vectorizer dimensions differ."
        )

    print(f"Validated {len(metadata)} resources.")


def publish_version(build_dir, version):
    """
    Move a complete validated build into its permanent
    version directory, then atomically update the active pointer.
    """

    final_dir = VERSIONS_DIR / version

    # The staging directory and versions directory are on the
    # same filesystem, so the directory rename is atomic.
    os.replace(build_dir, final_dir)

    pointer_temp = INDEX_ROOT / f".active-{uuid.uuid4().hex}.tmp"

    try:
        with open(pointer_temp, "w", encoding="utf-8") as file:
            json.dump({"version": version}, file)
            file.flush()
            os.fsync(file.fileno())

        # Readers see either the old pointer or the new pointer,
        # never a partially written pointer file.
        os.replace(pointer_temp, ACTIVE_VERSION_FILE)

    finally:
        if pointer_temp.exists():
            pointer_temp.unlink()

    print(f"Published index version: {version}")


def update_resources():
    if not BUILD_SCRIPT.is_file():
        raise FileNotFoundError(
            f"Could not find index builder: {BUILD_SCRIPT}"
        )

    INDEX_ROOT.mkdir(parents=True, exist_ok=True)
    VERSIONS_DIR.mkdir(parents=True, exist_ok=True)

    # Keep temporary builds on the same filesystem as final versions.
    version = uuid.uuid4().hex
    build_dir = VERSIONS_DIR / f".building-{version}"
    build_dir.mkdir()

    published = False

    try:
        print("Loading resource source...")
        resources = load_resources()

        if not resources:
            raise RuntimeError(
                "No resources were loaded. Nothing was published."
            )

        print(f"Loaded {len(resources)} resources.")

        print("Writing metadata...")
        write_metadata(resources, build_dir / "metadata.json")

        print("Building search indexes...")
        subprocess.run(
            [sys.executable, str(BUILD_SCRIPT)],
            cwd=build_dir,
            check=True
        )

        print("Validating generated artifacts...")
        validate_artifacts(build_dir)

        print("Publishing new version...")
        publish_version(build_dir, version)
        published = True

        print("Resource update completed successfully.")
        print(
            "Restart or reload the Flask application to load "
            "the newly published version."
        )

    finally:
        # If anything fails before publication, remove the
        # incomplete build and leave the active pointer untouched.
        if not published and build_dir.exists():
            import shutil
            shutil.rmtree(build_dir, ignore_errors=True)


if __name__ == "__main__":
    try:
        update_resources()
    except Exception as error:
        print(f"RESOURCE UPDATE FAILED: {error}")
        sys.exit(1)
