import csv
import math
from flask import Flask, request, jsonify
from flask_cors import CORS

# --- Haversine Distance Formula ---
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
# ---------------------------------------------------------

app = Flask(__name__)
CORS(app)

# --- Load Pharmacy Data into Memory ---
pharmacy_data = []
CSV_FILENAME = 'enriched_pharmacies_corrected.csv'
SEARCH_RADIUS_KM = 15  # <-- Set proximity to 15km
try:
    with open(CSV_FILENAME, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                row['latitude'] = float(row['latitude'])
                row['longitude'] = float(row['longitude'])
                pharmacy_data.append(row)
            except (ValueError, TypeError, KeyError):
                pass
    
    print(f"✅ Successfully loaded {len(pharmacy_data)} pharmacies from '{CSV_FILENAME}'.")
    if len(pharmacy_data) > 0:
        print(f"--- Example row (to check column names): ---")
        print(pharmacy_data[0])
        print("---------------------------------------------")

except FileNotFoundError:
    print(f"FATAL ERROR: '{CSV_FILENAME}' not found.")
except Exception as e:
    print(f"FATAL ERROR: Could not load data: {e}")
# -----------------------------------------------------


@app.route('/api/find-pharmacies', methods=['POST'])
def find_pharmacies():
    
    try:
        data = request.json
        # --- UPDATED: We no longer get 'pincode' ---
        user_lat = float(data.get('user_lat'))
        user_lon = float(data.get('user_lon'))
    except Exception as e:
        print(f"Error parsing request: {e}")
        return jsonify({"error": f"Invalid request: {e}"}), 400

    
    print(f"\n--- NEW SEARCH ---")
    print(f"Searching for pharmacies within {SEARCH_RADIUS_KM}km of ({user_lat}, {user_lon})")
    
    pharmacies_with_distance = []
    
    # --- UPDATED LOGIC ---
    # 1. Iterate through ALL pharmacies
    for pharmacy in pharmacy_data:
        try:
            # 2. Calculate distance from user
            dist = haversine(
                user_lat, 
                user_lon,
                pharmacy['latitude'], 
                pharmacy['longitude']
            )
            
            # 3. If within radius, add it to the list
            if dist <= SEARCH_RADIUS_KM:
                pharmacies_with_distance.append({
                    'name': pharmacy.get('Name', 'N/A'),
                    'address': pharmacy.get('Address', ''),
                    'distance_km': dist,
                    'google_map_link': pharmacy.get('Google_Maps_Link', '#'),
                    'latitude': pharmacy['latitude'],   # <-- Send lat/lon for the map
                    'longitude': pharmacy['longitude'] # <-- Send lat/lon for the map
                })
        except Exception as e:
            print(f"Error processing {pharmacy.get('Name')}: {e}")
            
    
    if not pharmacies_with_distance:
        print(f"--- RESULT: No pharmacies found within {SEARCH_RADIUS_KM}km. ---")
        return jsonify([])

    
    # 4. Sort the list by proximity (distance)
    sorted_pharmacies = sorted(pharmacies_with_distance, key=lambda p: p['distance_km'])
    
    print(f"--- RESULT: Found {len(sorted_pharmacies)} matches, returning sorted list. ---")
    return jsonify(sorted_pharmacies)

if __name__ == '__main__':
    app.run(debug=True, port=5000)