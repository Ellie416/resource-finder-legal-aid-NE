
from pathlib import Path
import json
import os
import pickle
import shutil
import subprocess
import sys
import tempfile

import faiss

from resource_source import load_resources


# ----------------------------------------------------------
# CONFIGURATION
# ----------------------------------------------------------

PROJECT_DIR = Path(__file__).resolve().parent

ACTIVE_FILES = [
    "metadata.json",
    "index.faiss",
    "tfidf_vectorizer.pkl",
    "tfidf_matrix.pkl",
]

BUILD_SCRIPT = PROJECT_DIR / "build_index.py"


# ----------------------------------------------------------
# WRITE RESOURCE METADATA
# ----------------------------------------------------------

def write_metadata(resources, output_file):
    """
    Save normalized resource records to a JSON file.
    This writes to the staging directory, not the live files.
    """

    with open(output_file, "w", encoding="utf-8") as file:
        json.dump(
            resources,
            file,
            indent=2,
            ensure_ascii=False
        )

    print(
        f"Prepared metadata for {len(resources)} resources."
    )


# ----------------------------------------------------------
# VALIDATE GENERATED ARTIFACTS
# ----------------------------------------------------------

def validate_artifacts(build_dir):
    """
    Confirm that all required artifacts exist and that their
    document counts agree before publishing the new version.
    """

    for filename in ACTIVE_FILES:
        path = build_dir / filename

        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(
                f"Missing or empty build artifact: {filename}"
            )

    with open(
        build_dir / "metadata.json",
        "r",
        encoding="utf-8"
    ) as file:
        metadata = json.load(file)

    if not isinstance(metadata, list) or not metadata:
        raise RuntimeError(
            "Generated metadata is empty or has an invalid format."
        )

    # Verify that the FAISS index can be loaded.
    faiss_index = faiss.read_index(
        str(build_dir / "index.faiss")
    )

    if faiss_index.ntotal != len(metadata):
        raise RuntimeError(
            "FAISS document count does not match metadata count: "
            f"{faiss_index.ntotal} vs {len(metadata)}."
        )

    # Verify the TF-IDF artifacts can be loaded.
    with open(
        build_dir / "tfidf_vectorizer.pkl",
        "rb"
    ) as file:
        vectorizer = pickle.load(file)

    with open(
        build_dir / "tfidf_matrix.pkl",
        "rb"
    ) as file:
        tfidf_matrix = pickle.load(file)

    if tfidf_matrix.shape[0] != len(metadata):
        raise RuntimeError(
            "TF-IDF document count does not match metadata count."
        )

    if tfidf_matrix.shape[1] != len(vectorizer.get_feature_names_out()):
        raise RuntimeError(
            "TF-IDF matrix and vectorizer dimensions do not match."
        )

    print(
        f"Validation passed: {len(metadata)} resources, "
        f"{faiss_index.ntotal} FAISS vectors, "
        f"{tfidf_matrix.shape[0]} TF-IDF rows."
    )


# ----------------------------------------------------------
# PUBLISH NEW ARTIFACTS
# ----------------------------------------------------------

def publish_artifacts(build_dir):
    """
    Replace the active files only after the new build validates.

    Existing files are backed up first. If publication fails,
    the previous files are restored.
    """

    backup_dir = build_dir / "previous"
    backup_dir.mkdir()

    existing_files = [
        filename
        for filename in ACTIVE_FILES
        if (PROJECT_DIR / filename).exists()
    ]

    # Save copies of the current files before replacing anything.
    for filename in existing_files:
        shutil.copy2(
            PROJECT_DIR / filename,
            backup_dir / filename
        )

    replaced_files = []

    try:
        for filename in ACTIVE_FILES:
            source = build_dir / filename
            destination = PROJECT_DIR / filename

            # Source and destination are on the same filesystem
            # when the temporary build directory is created here.
            os.replace(source, destination)
            replaced_files.append(filename)

    except Exception:
        print(
            "Publication failed. Attempting to restore "
            "the previous artifacts..."
        )

        for filename in reversed(replaced_files):
            backup = backup_dir / filename
            destination = PROJECT_DIR / filename

            if backup.exists():
                shutil.copy2(backup, destination)
            else:
                # This file did not exist before the update.
                destination.unlink(missing_ok=True)

        raise

    print("New artifacts published successfully.")


# ----------------------------------------------------------
# MAIN UPDATE PIPELINE
# ----------------------------------------------------------

def update_resources():
    """
    Load the configured source, build a complete new index,
    validate it, and publish it only after successful validation.
    """

    print("=" * 60)
    print("RESOURCE UPDATE")
    print("=" * 60)

    if not BUILD_SCRIPT.is_file():
        raise FileNotFoundError(
            f"Index builder not found: {BUILD_SCRIPT}"
        )

    # Keep the staging directory under the project directory
    # so publication can use same-filesystem file replacements.
    with tempfile.TemporaryDirectory(
        prefix=".resource_update_",
        dir=PROJECT_DIR
    ) as temporary_directory:

        build_dir = Path(temporary_directory)

        print("\nStep 1: Loading resource source...")

        resources = load_resources()

        if not resources:
            raise RuntimeError(
                "No valid resources were loaded. "
                "The current index will not be changed."
            )

        print("\nStep 2: Writing staged metadata...")

        write_metadata(
            resources,
            build_dir / "metadata.json"
        )

        print("\nStep 3: Building search indexes...")

        # build_index.py uses relative paths for its input/output.
        # Run it from the staging directory so it reads the staged
        # metadata and writes new artifacts there.
        subprocess.run(
            [
                sys.executable,
                str(BUILD_SCRIPT)
            ],
            cwd=build_dir,
            check=True
        )

        print("\nStep 4: Validating new artifacts...")

        validate_artifacts(build_dir)

        print("\nStep 5: Publishing the new artifacts...")

        publish_artifacts(build_dir)

    print("\nResource update completed successfully.")
    print(
        "The running Flask process may still be using the "
        "previously loaded index. Restart or reload the "
        "application using the deployment procedure."
    )


if __name__ == "__main__":
    try:
        update_resources()

    except Exception as error:
        print("\nRESOURCE UPDATE FAILED")
        print(f"Reason: {error}")
        print(
            "The existing index was not intentionally replaced "
            "unless publication had already begun."
        )
        sys.exit(1)
