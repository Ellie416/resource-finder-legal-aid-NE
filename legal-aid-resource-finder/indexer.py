from pathlib import Path
import json
import openpyxl

from location_utils import LocationDatabase


RESOURCE_FOLDER = Path("resources")
OUTPUT_FILE = Path("metadata.json")


def clean(value):
    """
    Convert a cell value to a clean string.
    """

    if value is None:
        return ""

    return str(value).strip()


def parse_workbook(filepath, location_db):
    """
    Read one Excel workbook and convert each row into
    a resource record.
    """

    workbook = openpyxl.load_workbook(
        filepath,
        data_only=True
    )

    resources = []

    for worksheet in workbook.worksheets:

        headers = [
            clean(cell.value)
            for cell in worksheet[1]
        ]

        header_map = {
            header.lower(): index
            for index, header in enumerate(headers)
            if header
        }

        required_columns = [
            "client need",
            "name of organization",
            "service(s) provided",
            "persons served",
            "area served"
        ]

        for column in required_columns:

            if column not in header_map:

                raise ValueError(
                    f"Missing required column "
                    f"'{column}' in sheet "
                    f"'{worksheet.title}'"
                )

        # Optional display fields
        website_column = (
            "website/facebook page, if any"
        )

        contact_column = (
            "telephone number/email, if any"
        )

        obtain_column = (
            "how client can obtain service(s)"
        )

        for row in worksheet.iter_rows(
            min_row=2
        ):

            client_need = clean(
                row[
                    header_map["client need"]
                ].value
            )

            organization = clean(
                row[
                    header_map["name of organization"]
                ].value
            )

            services = clean(
                row[
                    header_map["service(s) provided"]
                ].value
            )

            persons_served = clean(
                row[
                    header_map["persons served"]
                ].value
            )

            area_served = clean(
                row[
                    header_map["area served"]
                ].value
            )

            website = ""

            if website_column in header_map:

                website = clean(
                    row[
                        header_map[website_column]
                    ].value
                )

            contact = ""

            if contact_column in header_map:

                contact = clean(
                    row[
                        header_map[contact_column]
                    ].value
                )

            how_to_obtain = ""

            if obtain_column in header_map:

                how_to_obtain = clean(
                    row[
                        header_map[obtain_column]
                    ].value
                )

            # Skip completely empty rows
            if not any([
                client_need,
                organization,
                services,
                persons_served,
                area_served,
                website,
                contact,
                how_to_obtain
            ]):
                continue

            # Skip rows without an organization
            if not organization:
                continue

            # --------------------------------------------------
            # IMPORTANT:
            #
            # Area Served is parsed into structured location
            # data, but will NOT be used by semantic/keyword
            # search.
            # --------------------------------------------------

            location = location_db.parse_area_served(
                area_served
            )

            resource = {

                # ------------------------------------------
                # SEARCH FIELDS
                # ------------------------------------------

                "client_need": client_need,

                "organization": organization,

                "services_provided": services,

                "persons_served": persons_served,

                # ------------------------------------------
                # LOCATION
                # ------------------------------------------

                "location": location,

                # ------------------------------------------
                # DISPLAY-ONLY FIELDS
                # ------------------------------------------

                "website": website,

                "contact": contact,

                "how_to_obtain": how_to_obtain
            }

            resources.append(resource)

    return resources


def process_all_workbooks():

    print("Loading location database...")

    location_db = LocationDatabase()

    all_resources = []

    files = sorted(
        list(
            RESOURCE_FOLDER.glob("*.xlsx")
        )
        +
        list(
            RESOURCE_FOLDER.glob("*.xlsm")
        )
    )

    if not files:

        print(
            f"No Excel files found in "
            f"{RESOURCE_FOLDER}/"
        )

        return

    print(
        f"Found {len(files)} Excel file(s)."
    )

    for filepath in files:

        print(
            f"Processing: {filepath.name}"
        )

        try:

            resources = parse_workbook(
                filepath,
                location_db
            )

            all_resources.extend(
                resources
            )

            print(
                f"  → Found "
                f"{len(resources)} resources"
            )

        except Exception as e:

            print(
                f"  ERROR processing "
                f"{filepath.name}: {e}"
            )

    # ------------------------------------------------------
    # Save metadata
    # ------------------------------------------------------

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            all_resources,
            f,
            indent=2,
            ensure_ascii=False
        )

    print()
    print(
        f"Saved {len(all_resources)} resources "
        f"to {OUTPUT_FILE}"
    )

    # ------------------------------------------------------
    # Report location parsing
    # ------------------------------------------------------

    unknown_locations = []

    for resource in all_resources:

        location = resource["location"]

        if location["type"] == "unknown":

            unknown_locations.append({
                "organization": resource[
                    "organization"
                ],
                "area_served": location[
                    "raw"
                ]
            })

    if unknown_locations:

        print()
        print(
            "WARNING: Some Area Served entries "
            "could not be automatically recognized:"
        )

        for item in unknown_locations:

            print(
                f"  - {item['organization']}: "
                f"{item['area_served']}"
            )

        print()
        print(
            "These should be reviewed before "
            "rebuilding the search indexes."
        )


if __name__ == "__main__":
    process_all_workbooks()