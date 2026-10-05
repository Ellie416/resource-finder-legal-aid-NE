from flask import Flask, render_template, request, jsonify
from search_engine import SearchEngine
import json

app = Flask(__name__)

# Load the search engine once when the server starts.
engine = SearchEngine()

# Load Nebraska location data once.
with open("locations.json", "r", encoding="utf-8") as f:
    locations = json.load(f)


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
    location_value = (data.get("location_value") or "").strip()

    if not query:
        return jsonify({"error": "Please enter what the client needs."}), 400

    valid_types = {None, "", "region", "county", "city"}
    if location_type not in valid_types:
        return jsonify({"error": "Invalid location type."}), 400

    if location_type in {"region", "county", "city"} and not location_value:
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

        if location_value not in valid_values:
            return jsonify({"error": "Please select a valid Nebraska location."}), 400

    if location_type in {"", None}:
        location_type = None
        location_value = None

    results = engine.search(
        query=query,
        location_type=location_type,
        location_value=location_value,
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
        "location_value": location_value,
        "results": cleaned_results
    })


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
