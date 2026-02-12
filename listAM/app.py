import sqlite3
import re
from flask import Flask, render_template, jsonify, request
import requests

app = Flask(__name__)
DB_NAME = 'database.db'

# --- 1. Custom SQLite Functions ---

RATES = {"USD": 1.0, "EUR": 0.93, "AMD": 405.0, "RUB": 91.5}

def update_rates():
    global RATES
    try:
        # Free API for USD base rates
        url = "https://api.exchangerate-api.com/v4/latest/USD"
        response = requests.get(url)
        data = response.json()
        
        RATES = data['rates']
        
        print("Live currency rates updated $, Դ, €, ₽:",RATES['USD'], RATES['AMD'],  RATES['EUR'], RATES['RUB'])
    except Exception as e:
        print(f"Could not fetch live rates, using defaults. Error: {e}")

update_rates()


def get_price_in_usd(p_text):
    """
    Parses price text and converts it to USD for sorting/filtering.
    Returns 0 if N/A.
    """
    if not p_text or "N/A" in p_text: return 0
    
    clean = p_text.replace(',', '')
    match = re.search(r'(\d+)', clean)
    if not match: return 0
    
    val = float(match.group(1))
    
    # Convert to USD
    if '֏' in clean or 'AMD' in clean:
        return val / RATES["AMD"]
    elif '€' in clean or 'EUR' in clean:
        return val / RATES["EUR"]
    elif '₽' in clean or 'RUB' in clean:
        return val / RATES["RUB"]
    
    # Default is USD
    return val

def get_km_from_text(at_text):
    if not at_text: return 0
    match = re.search(r'([\d,]+)\s*(km|miles|mi)', at_text, re.IGNORECASE)
    if not match: return 0
    raw_num = float(match.group(1).replace(',', ''))
    unit = match.group(2).lower()
    if 'mi' in unit: return int(raw_num * 1.60934)
    return int(raw_num)

def check_fuel_match(at_text, desired_fuels_str):
    if not desired_fuels_str: return True
    if not at_text: return False
    desired_list = desired_fuels_str.split(',')
    text_lower = at_text.lower()
    for fuel in desired_list:
        if fuel.lower() in text_lower: return True
    return False

# --- 2. Standard Parsers (For Display) ---
def parse_price(p_text):
    # Same as before
    if not p_text or "N/A" in p_text: return 0, "USD"
    clean = p_text.replace(',', '')
    match = re.search(r'(\d+)', clean)
    if not match: return 0, "USD"
    val = float(match.group(1))
    cur = "USD"
    if '֏' in clean or 'AMD' in clean: cur = "AMD"
    elif '€' in clean or 'EUR' in clean: cur = "EUR"
    elif '₽' in clean or 'RUB' in clean: cur = "RUB"
    return val, cur

def parse_l_text(l_text):
    # Same as before
    try:
        parts = l_text.split(',')
        main = parts[0].strip()
        spec = parts[1].strip() if len(parts) > 1 else ""
        tokens = main.split(' ')
        year = int(tokens[0]) if tokens[0].isdigit() else 0
        make = tokens[1]
        model = " ".join(tokens[2:])
        return year, make, model, spec
    except:
        return 0, "Other", l_text, ""

def parse_at_text(at_text):
    # Same as before
    km = get_km_from_text(at_text)
    fuel = "Other"
    if "Gasoline" in at_text: fuel = "Gasoline"
    elif "Diesel" in at_text: fuel = "Diesel"
    elif "Hybrid" in at_text: fuel = "Hybrid"
    elif "Electric" in at_text: fuel = "Electric"
    elif "LPG" in at_text: fuel = "LPG"
    elif "CNG" in at_text: fuel = "CNG"
    location = at_text.split(',')[0].strip()
    return location, f"{km:,} km", fuel

# --- 3. Database & Routes ---

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    conn.create_function("GET_KM", 1, get_km_from_text)
    conn.create_function("CHECK_FUEL", 2, check_fuel_match)
    conn.create_function("GET_PRICE_USD", 1, get_price_in_usd) # NEW FUNCTION
    return conn

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/filter-options')
def get_filter_options():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT l_text FROM items") 
    rows = cursor.fetchall()
    conn.close()

    data_tree = {} 
    for row in rows:
        _, make, model, _ = parse_l_text(row['l_text'])
        if make not in data_tree: data_tree[make] = {"count": 0, "models": {}}
        data_tree[make]["count"] += 1
        if model not in data_tree[make]["models"]: data_tree[make]["models"][model] = 0
        data_tree[make]["models"][model] += 1

    response = []
    for make_name, make_data in sorted(data_tree.items()):
        models_list = []
        for mod_name, mod_count in sorted(make_data["models"].items()):
            models_list.append({"name": mod_name, "count": mod_count})
        response.append({"name": make_name, "count": make_data["count"], "models": models_list})
    return jsonify(response)

@app.route('/api/vehicles')
def get_vehicles():
    page = int(request.args.get('page', 1))
    limit = 24
    offset = (page - 1) * limit
    
    # Text Filters
    req_make = request.args.get('make', '')
    req_model = request.args.get('model', '')
    req_fuel = request.args.get('fuel', '')
    
    # Numeric Filters
    min_km = request.args.get('min_km', '')
    max_km = request.args.get('max_km', '')
    min_price_usd = request.args.get('min_price_usd', '') # Expects USD input
    max_price_usd = request.args.get('max_price_usd', '') # Expects USD input

    conn = get_db()
    cursor = conn.cursor()

    query = "SELECT * FROM items WHERE 1=1"
    params = []

    if req_make:
        query += " AND l_text LIKE ?"
        params.append(f"%{req_make}%")
    if req_model:
        query += " AND l_text LIKE ?"
        params.append(f"%{req_model}%")
    if req_fuel:
        query += " AND CHECK_FUEL(at_text, ?) = 1"
        params.append(req_fuel)
    if min_km:
        query += " AND GET_KM(at_text) >= ?"
        params.append(int(min_km))
    if max_km:
        query += " AND GET_KM(at_text) <= ?"
        params.append(int(max_km))
        
    # Price Filter (Using the new USD Converter)
    if min_price_usd:
        query += " AND GET_PRICE_USD(p_text) >= ?"
        params.append(float(min_price_usd))
    if max_price_usd:
        query += " AND GET_PRICE_USD(p_text) <= ?"
        params.append(float(max_price_usd))

    query += f" LIMIT {limit} OFFSET {offset}"
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    results = []
    for row in rows:
        vid, img, p_txt, l_txt, at_txt = row[0], row[1], row[2], row[3], row[4]
        price_val, price_cur = parse_price(p_txt)
        year, make, model, engine = parse_l_text(l_txt)
        loc, mil, fuel = parse_at_text(at_txt)
        
        results.append({
            "id": vid, "image": img,
            "price_raw": price_val, "currency_original": price_cur,
            "year": year, "make": make, "model": model, "engine": engine,
            "location": loc, "mileage": mil, "fuel": fuel
        })

    return jsonify(results)

@app.route('/api/rates')
def get_rates():
    return jsonify(RATES)

if __name__ == '__main__':
    app.run(debug=True, port=5000)