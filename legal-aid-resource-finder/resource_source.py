
from pathlib import Path
import os

from indexer import parse_workbook
from location_utils import LocationDatabase


# ----------------------------------------------------------
# RESOURCE SOURCE CONFIGURATION
# ----------------------------------------------------------

# "local" works now.
# "sharepoint" will be enabled after IT configures access.
RESOURCE_SOURCE = os.getenv(
    "RESOURCE_SOURCE",
    "local"
).strip().lower()

LOCAL_RESOURCE_FILE = Path(
    os.getenv(
        "LOCAL_RESOURCE_FILE",
        "resources/Resource Bank reformatted v2.xlsx"
    )
)


# ----------------------------------------------------------
# LOCAL EXCEL SOURCE
# ----------------------------------------------------------

def load_local_resources():
    """
    Load resources from the configured local Excel workbook.

    Returns:
        list[dict]: Normalized resource records in the format
        expected by the existing search engine.
    """

    if not LOCAL_RESOURCE_FILE.exists():
        raise FileNotFoundError(
            "The configured resource workbook was not found: "
            f"{LOCAL_RESOURCE_FILE.resolve()}"
        )

    print(
        f"Loading resources from {LOCAL_RESOURCE_FILE}..."
    )

    location_db = LocationDatabase()

    resources = parse_workbook(
        LOCAL_RESOURCE_FILE,
        location_db
    )

    if not resources:
        raise ValueError(
            "The resource workbook produced zero valid "
            "resource records. The existing data has not "
            "been replaced."
        )

    print(
        f"Loaded {len(resources)} resources."
    )

    return resources


# ----------------------------------------------------------
# FUTURE SHAREPOINT SOURCE
# ----------------------------------------------------------

def load_sharepoint_resources():
    """
    Load resources from a SharePoint-hosted Excel workbook.

    This provider is intentionally not implemented yet.
    Legal Aid IT must configure Microsoft Graph access,
    authentication, and the workbook location first.
    """

    raise NotImplementedError(
        "SharePoint integration is not configured yet. "
        "Set RESOURCE_SOURCE=local to use the local workbook, "
        "or implement the SharePoint provider after IT "
        "supplies the required configuration."
    )


# ----------------------------------------------------------
# COMMON SOURCE INTERFACE
# ----------------------------------------------------------

def load_resources():
    """
    Load resources using the configured source.

    Both providers must return the same normalized resource
    structure so the indexing pipeline remains independent
    of the source.
    """

    if RESOURCE_SOURCE == "local":
        return load_local_resources()

    if RESOURCE_SOURCE == "sharepoint":
        return load_sharepoint_resources()

    raise ValueError(
        f"Unsupported RESOURCE_SOURCE: {RESOURCE_SOURCE!r}. "
        "Supported values are 'local' and 'sharepoint'."
    )
