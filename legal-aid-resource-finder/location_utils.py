from pathlib import Path
import json
import re
from difflib import get_close_matches


LOCATIONS_FILE = Path("locations.json")


class LocationDatabase:
    """
    Loads and manages the Nebraska location hierarchy.

    Hierarchy:

        Region
           ↓
        County
           ↓
        Municipality
    """

    def __init__(self, filepath=LOCATIONS_FILE):
        self.filepath = filepath

        with open(filepath, "r", encoding="utf-8") as f:
            self.data = json.load(f)

        self.regions = self.data["regions"]
        self.counties = self.data["counties"]

        # --------------------------------------------------
        # Build reverse lookup tables
        # --------------------------------------------------

        self.city_to_counties = {}
        self.city_to_regions = {}

        for county_name, county_data in self.counties.items():

            region = county_data["region"]

            for city in county_data.get("municipalities", []):

                self.city_to_counties.setdefault(
                    city,
                    []
                ).append(county_name)

                self.city_to_regions.setdefault(
                    city,
                    []
                ).append(region)

        # Normalize lookup keys so:
        #
        # Lincoln
        # lincoln
        # LINCOLN
        #
        # all resolve to the same thing.
        self.region_lookup = {
            self.normalize_name(name): name
            for name in self.regions
        }

        self.county_lookup = {
            self.normalize_name(name): name
            for name in self.counties
        }

        self.city_lookup = {
            self.normalize_name(name): name
            for name in self.city_to_counties
        }

    # ======================================================
    # NORMALIZATION
    # ======================================================

    @staticmethod
    def normalize_name(value):
        """
        Normalize a location name for matching.

        Examples:

            "Lincoln, NE" -> "lincoln"
            "Lancaster County" -> "lancaster"
            " LINCOLN " -> "lincoln"
        """

        if not value:
            return ""

        value = str(value).strip().lower()

        # Remove Nebraska references
        if value not in ("nebraska", "ne"):

            value = re.sub(
                r",?\s*(ne|nebraska)$",
                "",
                value
            )

        # # Remove county suffix
        # value = re.sub(
        #     r"\s+county$",
        #     "",
        #     value
        # )

        # Replace punctuation with spaces
        value = re.sub(
            r"[^a-z0-9\s]",
            " ",
            value
        )

        # Collapse whitespace
        value = re.sub(
            r"\s+",
            " ",
            value
        )

        return value.strip()

    # ======================================================
    # LOOKUP
    # ======================================================

    def find_region(self, value):
        """
        Find a canonical region name.

        Allows minor spelling differences.
        """

        normalized = self.normalize_name(value)

        if normalized in self.region_lookup:
            return self.region_lookup[normalized]

        matches = get_close_matches(
            normalized,
            self.region_lookup.keys(),
            n=1,
            cutoff=0.85
        )

        if matches:
            return self.region_lookup[matches[0]]

        return None

    def find_county(self, value):
        """
        Find a canonical county name.
        """

        normalized = self.normalize_name(value)

        if "county" in normalized:
            # Remove county suffix
            normalized = re.sub(
                r"\s+county$",
                "",
                normalized
            )
            normalized = normalized.strip()

            if normalized in self.county_lookup:
                return self.county_lookup[normalized]

            matches = get_close_matches(
                normalized,
                self.county_lookup.keys(),
                n=1,
                cutoff=0.85
            )

            if matches:
                return self.county_lookup[matches[0]]

        return None

    def find_city(self, value):
        """
        Find a canonical municipality name.
        """

        normalized = self.normalize_name(value)

        if normalized in self.city_lookup:
            return self.city_lookup[normalized]

        matches = get_close_matches(
            normalized,
            self.city_lookup.keys(),
            n=1,
            cutoff=0.85
        )

        if matches:
            return self.city_lookup[matches[0]]

        return None

    # ======================================================
    # HIERARCHY
    # ======================================================

    def counties_in_region(self, region):
        """
        Return all counties belonging to a region.
        """

        canonical = self.find_region(region)

        if not canonical:
            return []

        return self.regions[canonical]

    def cities_in_county(self, county):
        """
        Return all municipalities in a county.
        """

        canonical = self.find_county(county)

        if not canonical:
            return []

        return self.counties[canonical].get(
            "municipalities",
            []
        )

    def cities_in_region(self, region):
        """
        Return all municipalities in a region.
        """

        cities = []

        for county in self.counties_in_region(region):
            cities.extend(
                self.cities_in_county(county)
            )

        return sorted(set(cities))

    def counties_for_city(self, city):
        """
        Return all counties associated with a municipality.

        Some municipalities can appear in more than one
        county in the source data.
        """

        canonical = self.find_city(city)

        if not canonical:
            return []

        return self.city_to_counties.get(
            canonical,
            []
        )

    def regions_for_city(self, city):
        """
        Return all regions associated with a municipality.
        """

        canonical = self.find_city(city)

        if not canonical:
            return []

        return self.city_to_regions.get(
            canonical,
            []
        )

    # ======================================================
    # PARSING EXCEL AREA SERVED
    # ======================================================

    def parse_area_served(self, area_text):
        """
        Convert the free-text Area Served field from Excel
        into structured location information.

        Returns:

        {
            "type": "city",
            "values": ["Lincoln", "Omaha"],
            "raw": "Lincoln, Omaha"
        }

        or:

        {
            "type": "statewide",
            "values": [],
            "raw": "Statewide"
        }

        or:

        {
            "type": "county",
            "values": ["Lancaster", "Seward"],
            "raw": "Lancaster County, Seward County"
        }
        """

        raw = "" if area_text is None else str(area_text).strip()

        if not raw:
            return {
                "type": "unknown",
                "values": [],
                "raw": raw
            }

        normalized = self.normalize_name(raw)

        # --------------------------------------------------
        # STATEWIDE
        # --------------------------------------------------

        statewide_phrases = [
            "statewide",
            "nebraska",
            "all nebraska",
            "entire state",
            "state wide",
            "anywhere in nebraska",
            "throughout nebraska",
            "across nebraska"
        ]

        if normalized in statewide_phrases:
            return {
                "type": "statewide",
                "values": [],
                "raw": raw
            }

        # --------------------------------------------------
        # REGION
        # --------------------------------------------------

        region_matches = []

        for region in self.regions:

            if self.normalize_name(region) in normalized:
                region_matches.append(region)

        if region_matches:

            return {
                "type": "region",
                "values": region_matches,
                "raw": raw
            }

        # --------------------------------------------------
        # Split multiple locations
        #
        # Handles:
        #
        # Lincoln, Omaha
        # Lincoln and Omaha
        # Lincoln; Omaha
        # Lincoln / Omaha
        # --------------------------------------------------

        pieces = re.split(
            r"\s*(?:,|;|/|\band\b|\&)\s*",
            raw,
            flags=re.IGNORECASE
        )

        pieces = [
            piece.strip()
            for piece in pieces
            if piece.strip()
        ]

        # --------------------------------------------------
        # Try to identify counties
        # --------------------------------------------------

        counties = []

        for piece in pieces:

            county = self.find_county(piece)

            if county and county not in counties:
                counties.append(county)

        if counties and len(counties) == len(pieces):

            return {
                "type": "county",
                "values": counties,
                "raw": raw
            }

        # --------------------------------------------------
        # Try to identify cities
        # --------------------------------------------------

        cities = []

        for piece in pieces:

            city = self.find_city(piece)

            if city and city not in cities:
                cities.append(city)

        if cities:

            return {
                "type": "city",
                "values": cities,
                "raw": raw
            }

        # --------------------------------------------------
        # Unknown
        # --------------------------------------------------

        return {
            "type": "unknown",
            "values": [],
            "raw": raw
        }

    # ======================================================
    # RESOURCE LOCATION MATCHING
    # ======================================================

    def resource_matches_location(
        self,
        resource,
        selected_type,
        selected_value
    ):
        """
        Determine whether a resource should be included
        for the user's selected location.

        Broad service areas satisfy narrower searches.

        Example:

            Resource serves Southeast Nebraska
            User searches Lincoln

        -> INCLUDE

        Resource serves Lancaster County
        User searches Lincoln

        -> INCLUDE

        Resource serves Lincoln
        User searches Lancaster County

        -> INCLUDE
        """

        selected_type = selected_type.lower()

        selected_value = selected_value.strip()

        resource_location = resource.get(
            "location",
            {}
        )

        resource_type = resource_location.get(
            "type",
            "unknown"
        )

        resource_values = resource_location.get(
            "values",
            []
        )

        # --------------------------------------------------
        # Unknown location
        # --------------------------------------------------

        if resource_type == "unknown":
            return False

        # --------------------------------------------------
        # Statewide resources ALWAYS match
        # --------------------------------------------------

        if resource_type == "statewide":
            return True

        # --------------------------------------------------
        # Normalize selected location
        # --------------------------------------------------

        if selected_type == "region":
            selected_region = self.find_region(
                selected_value
            )

            if not selected_region:
                return False

        elif selected_type == "county":
            selected_county = self.find_county(
                selected_value
            )

            if not selected_county:
                return False

        elif selected_type == "city":
            selected_city = self.find_city(
                selected_value
            )

            if not selected_city:
                return False

        else:
            return False

        # ==================================================
        # USER SELECTED REGION
        # ==================================================

        if selected_type == "region":

            region = selected_region

            # Resource serves the entire region
            if resource_type == "region":
                return region in resource_values

            # Resource serves one or more counties
            if resource_type == "county":

                counties = self.counties_in_region(
                    region
                )

                return any(
                    county in counties
                    for county in resource_values
                )

            # Resource serves one or more cities
            if resource_type == "city":

                region_cities = set(
                    self.cities_in_region(region)
                )

                return any(
                    city in region_cities
                    for city in resource_values
                )

        # ==================================================
        # USER SELECTED COUNTY
        # ==================================================

        if selected_type == "county":

            county = selected_county

            county_region = self.counties[county][
                "region"
            ]

            # Resource serves selected region
            if resource_type == "region":
                return county_region in resource_values

            # Resource serves selected county
            if resource_type == "county":
                return county in resource_values

            # Resource serves a city in selected county
            if resource_type == "city":

                county_cities = set(
                    self.cities_in_county(county)
                )

                return any(
                    city in county_cities
                    for city in resource_values
                )

        # ==================================================
        # USER SELECTED CITY
        # ==================================================

        if selected_type == "city":

            city = selected_city

            city_counties = self.counties_for_city(
                city
            )

            city_regions = self.regions_for_city(
                city
            )

            # Resource serves selected region
            if resource_type == "region":

                return any(
                    region in resource_values
                    for region in city_regions
                )

            # Resource serves selected county
            if resource_type == "county":

                return any(
                    county in resource_values
                    for county in city_counties
                )

            # Resource serves selected city
            if resource_type == "city":

                return city in resource_values

        return False