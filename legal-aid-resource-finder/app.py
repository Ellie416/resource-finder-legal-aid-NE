from pathlib import Path
import json

from flask import Flask, render_template, request, jsonify
from search_engine import SearchEngine

app = Flask(__name__)

PROJECT_DIR = Path(__file__).resolve().parent

# Load the currently published search index at startup.
print("Loading search engine...")
engine = SearchEngine()
print("Search engine loaded successfully.")

# Load Nebraska location data.
LOCATIONS_FILE = PROJECT_DIR / "locations.json"

with open(LOCATIONS_FILE, "r", encoding="utf-8") as file:
    locations = json.load(file)


@app.route("/")
def search_page():
    return render_template("search.html")


@app.route("/results")
def results_page():
    return render_template("results.html")


@app.route("/api/locations")
def get_locations():
    """
    Returns normalized location lists for the frontend.

    locations.json has:
      regions: {region_name: [county, ...]}
      counties: {
          county_name: {
              region: region_name,
              municipalities: [city, ...]
          }
      }
    """
    regions = sorted(locations.get("regions", {}).keys())

    counties = sorted(locations.get("counties", {}).keys())

    # A city can occur in more than one county, so make this list unique.
    cities = sorted({
        city
        for county in locations.get("counties", {}).values()
        for city in county.get("municipalities", [])
    })

    return jsonify({
        "state": locations.get("state", "Nebraska"),
        "regions": regions,
        "counties": counties,
        "cities": cities
    })


@app.route("/api/search", methods=["POST"])
def search():
    data = request.get_json(silent=True) or {}

    query = (data.get("query") or "").strip()
    location_type = data.get("location_type")
    location_values = data.get( 
        "location_values",
        data.get("location_value", [])
    )

    if isinstance(location_values, str):
        location_values = (
            [location_values.strip()]
            if location_values.strip()
            else []
        )

    if not isinstance(location_values, list):
        return jsonify({"error": "Locations must be a list."}), 400

    location_values = [
        value.strip()
        for value in location_values
        if isinstance(value, str) and value.strip()
    ]


    if not query:
        return jsonify({"error": "Please enter what the client needs."}), 400

    valid_types = {None, "", "region", "county", "city"}
    if location_type not in valid_types:
        return jsonify({"error": "Invalid location type."}), 400

    if location_type in {"region", "county", "city"} and not location_values:
        return jsonify({"error": "Please select a location."}), 400

    if location_type in {"region", "county", "city"}:
        if location_type == "region":
            valid_values = set(locations["regions"].keys())
        elif location_type == "county":
            valid_values = set(locations["counties"].keys())
        else:
            valid_values = {
                city
                for county in locations["counties"].values()
                for city in county.get("municipalities", [])
            }

        invalid_values = [
            value for value in location_values
            if value not in valid_values
        ]

        if invalid_values:
            return jsonify({
                "error": "Invalid Nebraska location(s): "
                + ", ".join(invalid_values)
            }), 400

        
    if location_type in {"", None}:
        location_type = None
        location_values = []

    results = engine.search(
        query=query,
        location_type=location_type,
        location_value=location_values if location_values else None,
        top_k=10
    )

    cleaned_results = []

    for resource in results:
        cleaned_results.append({
            "organization": resource.get("organization", ""),
            "services_provided": resource.get("services_provided", ""),
            "persons_served": resource.get("persons_served", ""),
            "location": resource.get("location", {}),
            "website": resource.get("website", ""),
            "contact": resource.get("contact", ""),
            "how_to_obtain": resource.get("how_to_obtain", ""),
            "client_need": resource.get("client_need", "")
        })

    return jsonify({
        "query": query,
        "location_type": location_type,
        "location_value": location_values,
        "results": cleaned_results
    })


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
