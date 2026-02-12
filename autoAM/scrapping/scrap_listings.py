import requests
import sqlite3
import threading
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

# --- Configuration ---
DB_NAME = 'database.db'
MAX_WORKERS = 30 

# Global lock for database writing
db_lock = threading.Lock()

def init_db():
    """Creates the tags table if it doesn't exist."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Create the tags table
    # We use a composite unique constraint (car_id, attribute) to prevent duplicates
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            car_id TEXT,
            attribute TEXT,
            value TEXT,
            FOREIGN KEY(car_id) REFERENCES cars(id),
            UNIQUE(car_id, attribute)
        )
    ''')
    conn.commit()
    conn.close()
    print(f"[*] Database table 'tags' checked/initialized.")

def get_headers():
    return {
        'User-Agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:147.0) Gecko/20100101 Firefox/147.0',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive',
    }

def get_pending_ids():
    """
    Fetches car IDs from the 'cars' table that do NOT yet have entries 
    in the 'tags' table. This allows the script to resume if stopped.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Get all car IDs
    cursor.execute("SELECT id FROM cars")
    all_cars = set(row[0] for row in cursor.fetchall())
    
    # Get IDs that are already processed in tags
    cursor.execute("SELECT DISTINCT car_id FROM tags")
    processed_cars = set(row[0] for row in cursor.fetchall())
    
    conn.close()
    
    pending = list(all_cars - processed_cars)
    print(f"[*] Found {len(all_cars)} total cars. {len(processed_cars)} already done. {len(pending)} pending.")
    return pending

def scrape_details(car_id):
    """Scrapes the details table for a specific car ID."""
    url = f"https://auto.am/offer/{car_id}"
    
    try:
        response = requests.get(url, headers=get_headers(), timeout=10)
        
        if response.status_code == 404:
            print(f"[!] Car {car_id} not found (404). Skipping.")
            return None # Signal to mark as done but empty
            
        if response.status_code != 200:
            print(f"[!] Failed {car_id}: Status {response.status_code}")
            return [] # Return empty list to retry later or ignore

        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find the specific table with class "pad-top-6 ad-det"
        table = soup.find('table', class_='pad-top-6 ad-det')
        
        if not table:
            # Some pages might not have the table or are different format
            return None 

        tags_found = []
        tbody = table.find('tbody')
        if tbody:
            rows = tbody.find_all('tr')
            for row in rows:
                cols = row.find_all('td')
                if len(cols) == 2:
                    # 1. Get Attribute Name (First Column)
                    attr_name = cols[0].get_text(strip=True)
                    
                    # 2. Get Value (Second Column) - CLEANUP REQUIRED
                    val_td = cols[1]
                    
                    # Remove the <span style="display: none;"> tags containing dirty JSON
                    for hidden in val_td.find_all(style=lambda s: s and 'none' in s):
                        hidden.decompose()
                        
                    val_text = val_td.get_text(strip=True)
                    
                    tags_found.append({
                        'car_id': car_id,
                        'attribute': attr_name,
                        'value': val_text
                    })
                    
        return tags_found

    except Exception as e:
        print(f"[!] Error on ID {car_id}: {e}")
        return []

def save_tags(tags, car_id_if_empty=None):
    """Saves a list of tags to the DB."""
    with db_lock:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        if tags:
            try:
                cursor.executemany('''
                    INSERT OR IGNORE INTO tags (car_id, attribute, value)
                    VALUES (:car_id, :attribute, :value)
                ''', tags)
                conn.commit()
            except sqlite3.Error as e:
                print(f"    DB Error saving tags: {e}")
        elif car_id_if_empty:
            # If a car has no tags (e.g. 404 or empty page), we insert a dummy record
            # or simply ignore it. Here we ignore, but you could mark it processed
            # in a separate table if you wanted to be strict.
            pass

        conn.close()

def main():
    init_db()
    
    ids_to_scrape = get_pending_ids()
    
    if not ids_to_scrape:
        print("[*] No pending cars to scrape.")
        return

    print(f"[*] Starting detail scrape with {MAX_WORKERS} threads...")
    
    processed_count = 0
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Submit tasks
        future_to_id = {executor.submit(scrape_details, car_id): car_id for car_id in ids_to_scrape}
        
        for future in as_completed(future_to_id):
            car_id = future_to_id[future]
            try:
                result = future.result()
                
                if result is not None:
                    # Save results
                    save_tags(result, car_id_if_empty=car_id)
                    processed_count += 1
                    if processed_count % 50 == 0:
                        print(f"[*] Processed {processed_count} cars...")
                else:
                    # Result is None implies 404 or missing table
                    print(f"[-] No data for car {car_id}")
                    
            except Exception as exc:
                print(f"[!] ID {car_id} generated exception: {exc}")

    print("[*] Detail scraping complete.")

if __name__ == "__main__":
    main()