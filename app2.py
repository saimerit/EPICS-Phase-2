import csv
import math
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
import re

# --- CONSTANTS ---
OVERPASS_URL = "http://overpass-api.de/api/interpreter"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
# ---------------------------------------------------------

# --- Haversine Distance Formula (Unchanged) ---
def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    rad_lat1 = math.radians(lat1)
    rad_lon1 = math.radians(lon1)
    rad_lat2 = math.radians(lat2)
    rad_lon2 = math.radians(lon2)
    d_lon = rad_lon2 - rad_lon1
    d_lat = rad_lat2 - rad_lat1
    a = math.sin(d_lat / 2)**2 + math.cos(rad_lat1) * math.cos(rad_lat2) * math.sin(d_lon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# --- Utility to process data and sort results (Updated link generation) ---
def process_and_sort_results(user_lat, user_lon, search_radius, results_list):
    """Calculates distance, filters by radius, and sorts the results."""
    
    final_results = []
    
    for item in results_list:
        try:
            dist = haversine(
                user_lat, 
                user_lon,
                item['latitude'], 
                item['longitude']
            )
            
            if dist <= search_radius:
                final_results.append({
                    'name': item.get('name', 'N/A'),
                    'address': item.get('Address', ''),
                    'distance_km': dist,
                    'latitude': float(item['latitude']),
                    'longitude': float(item['longitude']),
                    # RESTORED: Generate Google Maps link from coordinates
                    'google_map_link': f'https://www.google.com/maps/search/?api=1&query={item["latitude"]},{item["longitude"]}',
                })
        except Exception as e:
            print(f"Error processing item: {e}")
            
    return sorted(final_results, key=lambda p: p['distance_km'])

# --- Overpass API Logic (Updated link generation) ---
def fetch_from_overpass(user_lat, user_lon, search_radius, amenity_type="pharmacy"):
    """Fetches amenity data from OpenStreetMap via Overpass API."""
    
    search_radius_m = search_radius * 1000 
    
    amenities = []
    if amenity_type == 'pharmacy':
        amenities = ['pharmacy', 'hospital']
    elif amenity_type == 'hospital':
        amenities = ['hospital']

    amenity_filter = "".join([f'node["amenity"="{a}"](around:{search_radius_m},{user_lat},{user_lon});' for a in amenities])

    overpass_query = f"""
        [out:json][timeout:30];
        (
          {amenity_filter}
        );
        out center;
    """
    
    print(f"🌍 Running Overpass query for {amenity_type} around ({user_lat}, {user_lon}) within {search_radius}km...")
    
    headers = {
        'User-Agent': 'NearbyAmenityFinderApp/1.0 (saiardhendu10@gmail.com)'
    }
    
    try:
        response = requests.post(OVERPASS_URL, data={'data': overpass_query}, headers=headers)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        print(f"FATAL ERROR: Overpass API request failed: {e}")
        return [], f"External API Error: Overpass API request failed. Please check connection and try again. Detail: {e}"

    items_from_api = []
    
    for element in data.get('elements', []):
        if element['type'] == 'node':
            lat = element.get('lat')
            lon = element.get('lon')
            name = element.get('tags', {}).get('name', f'Unnamed {amenity_type.title()} (OSM)')
            address_tags = element.get('tags', {})
            
            address_parts = [
                address_tags.get('addr:housename'),
                address_tags.get('addr:street'),
                address_tags.get('addr:city'),
                address_tags.get('addr:postcode')
            ]
            address = ", ".join(filter(None, address_parts))
            
            items_from_api.append({
                'name': name,
                'address': address,
                'latitude': lat,
                'longitude': lon,
                # RESTORED: Generate Google Maps link from coordinates
                'google_map_link': f'https://www.google.com/maps/search/?api=1&query={lat},{lon}',
            })

    print(f"✅ Overpass API fetched {len(items_from_api)} results for {amenity_type}.")
    return items_from_api, None

# --- Removed CSV Loading Block ---

app = Flask(__name__)
CORS(app)

# ==========================================================
# --- ENDPOINT: Nominatim Geocoding (Unchanged) ---
# ==========================================================
@app.route('/api/geocode', methods=['POST'])
def geocode_location():
    try:
        data = request.json
        search_term = data.get('search_term', '').strip()
        
        if not search_term:
            return jsonify({"error": "Search term cannot be empty."}), 400

        params = {
            'q': search_term,
            'format': 'json',
            'limit': 1,
            'countrycodes': 'in', 
        }

        headers = {
            'User-Agent': 'NearbyAmenityFinderApp/1.0 (saiardhendu10@gmail.com)'
        }
        
        print(f"🔍 Geocoding search term: '{search_term}' using Nominatim...")
        response = requests.get(NOMINATIM_URL, params=params, headers=headers)
        response.raise_for_status()
        results = response.json()
        
        if not results:
            return jsonify({"error": f"Could not find coordinates for '{search_term}'. Please refine your search."}), 404
        
        best_match = results[0]
        
        return jsonify({
            "latitude": float(best_match['lat']),
            "longitude": float(best_match['lon']),
            "display_name": best_match['display_name']
        }), 200

    except requests.exceptions.RequestException as e:
        print(f"Error connecting to Nominatim: {e}")
        return jsonify({"error": f"External API Error: Failed to geocode location. Nominatim API may be rate-limiting you. Detail: {e}"}), 500
    except Exception as e:
        print(f"Error during geocoding: {e}")
        return jsonify({"error": f"An unexpected error occurred during geocoding: {e}"}), 500

# ==========================================================
# --- MAIN ENDPOINT: Find Amenities (Unchanged) ---
# ==========================================================
@app.route('/api/find-amenities', methods=['POST'])
def find_amenities():
    
    try:
        data = request.json
        
        user_lat_str = data.get('user_lat')
        user_lon_str = data.get('user_lon')
        search_radius = float(data.get('radius', 15))
        amenity_type = data.get('amenity_type', 'pharmacy')
        
        if user_lat_str is None or user_lon_str is None:
             raise ValueError("Missing 'user_lat' or 'user_lon' in request payload.")

        user_lat = float(user_lat_str)
        user_lon = float(user_lon_str)
        
    except ValueError as e:
        print(f"Error parsing request parameters: {e}")
        return jsonify({"error": f"Invalid request: Coordinates are missing or invalid. Please search for a location or use Geolocation first."}), 400
    except Exception as e:
        print(f"Error parsing request: {e}")
        return jsonify({"error": f"Invalid request: {e}"}), 400

    
    print(f"\n--- NEW SEARCH (OVERPASS API ONLY) for {amenity_type.upper()} ---")

    raw_results, error_message = fetch_from_overpass(user_lat, user_lon, search_radius, amenity_type)
    if error_message:
        return jsonify({"error": error_message}), 500
        
    sorted_amenities = process_and_sort_results(user_lat, user_lon, search_radius, raw_results)
    
    if not sorted_amenities:
        print(f"--- RESULT: No {amenity_type} found within {search_radius}km. ---")
        return jsonify([])

    print(f"--- RESULT: Found {len(sorted_amenities)} matches, returning sorted list. ---")
    return jsonify(sorted_amenities)

if __name__ == '__main__':
    app.run(debug=True, port=5000)