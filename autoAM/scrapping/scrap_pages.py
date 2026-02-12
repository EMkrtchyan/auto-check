import requests
import sqlite3
import json
import threading
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import os
from dotenv import load_dotenv

# --- Configuration ---
DB_NAME = 'database.db'

# The site limits results to 10,000 cars. 
MAX_PAGES_PER_RANGE = 200
MAX_WORKERS = 1

# Define your price ranges here (min, max)
# Overlap slightly (e.g. 20000) to ensure no cars are missed on the boundary
PRICE_RANGES = [
    (1, 20000),       # First batch: 0 to 20k
    (20000, 50000000) # Second batch: 20k to 50M ("the rest")
]

# Global lock for database writing
db_lock = threading.Lock()

# Global flag to signal threads to stop current range early if needed
stop_current_range = False

def init_db():
    """Initializes the SQLite database."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cars (
            id TEXT PRIMARY KEY,
            brand TEXT,
            model TEXT,
            price REAL,
            currency TEXT,
            taxed BOOL,
            year INT,
            original_price_text TEXT,
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()
    print(f"[*] Database '{DB_NAME}' initialized.")

# load dotenv
base_dir = os.path.dirname(os.path.abspath(__file__))
dotenv_path = os.path.join(base_dir, '.env')
load_dotenv(dotenv_path)


def get_headers():
    """
    Returns headers using environment variables for sensitive data.
    """
    return {
        'User-Agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:147.0) Gecko/20100101 Firefox/147.0',
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'X-CSRF-Token': str(os.getenv('CSRF_TOKEN')), 
        'X-Requested-With': 'XMLHttpRequest',
        'Origin': 'https://auto.am',
        'Referer': 'https://auto.am/search/passenger-cars',
        'Cookie': str(os.getenv('USER_SESSION_COOKIE'))
    }

def scrape_page(page_num, min_price, max_price):
    """Scrapes a single page for a specific price range."""
    global stop_current_range
    if stop_current_range:
        return []

    url = 'https://auto.am/search'
    
    # Dynamic payload with price range
    search_params = {
        "category": "1",
        "page": str(page_num),
        "sort": "latest",
        "layout": "list",
        "user": {"dealer": "0", "official": "0", "id": ""},
        "year": {"gt": "1911", "lt": "2027"},
        "usdprice": {"gt": str(min_price), "lt": str(max_price)},
        "mileage": {"gt": "0", "lt": "1000000"}
    }

    data = {'search': json.dumps(search_params)}

    try:
        response = requests.post(url, headers=get_headers(), data=data, timeout=15)
        
        if response.status_code != 200:
            # 419 usually means CSRF token expired
            print(f"[!] Error Page {page_num}: Status {response.status_code}")
            return []

        soup = BeautifulSoup(response.text, 'html.parser')
        car_cards = soup.find_all('div', class_='card')
        
        if not car_cards:
            # If a page returns 0 cars, we might have reached the end of this range
            # We don't stop immediately because async threads might be out of order,
            # but getting empty results is a strong hint.
            return []

        extracted_data = []
        for card in car_cards:
            link_tag = card.find('a', class_='click-for-gtag')
            
            if link_tag:
                car_id = link_tag.get('data-id')
                brand = link_tag.get('data-brand')
                model = link_tag.get('data-model')
                price_raw = link_tag.get('data-price')
                
                taxed = False
                
                tax_div = card.find('div', class_='card-loc')
                tax_text = tax_div.find('span', class_='green-text')
                if tax_text:
                    taxed = True
                
                year = card.find('span', class_='grey-text').text
                
                
                print(year)
                # Currency extraction
                currency = "?"
                original_price_text = ""
                
                price_div = card.find('div', class_='price')
                if not price_div:
                    price_div = card.find('div', class_='ad-mob-price')
                
                if price_div:
                    span = price_div.find('span')
                    if span:
                        text = span.get_text(strip=True)
                        original_price_text = text
                        parts = text.split(' ')
                        if len(parts) > 0:
                            currency = parts[0]

                extracted_data.append({
                    'id': car_id,
                    'brand': brand,
                    'model': model,
                    'price': price_raw,
                    'currency': currency,
                    'taxed': taxed,
                    'year': year,
                    'original_price_text': original_price_text,
                })
        
        return extracted_data

    except Exception as e:
        print(f"[!] Exception on page {page_num}: {e}")
        return []

def save_batch(cars):
    """Saves a batch of cars to the DB."""
    if not cars:
        return

    with db_lock:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        count = 0
        for car in cars:
            try:
                cursor.execute('''
                    INSERT OR REPLACE INTO cars (id, brand, model, price, currency, taxed, year, original_price_text)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (car['id'], car['brand'], car['model'], car['price'], car['currency'], car['taxed'], car['year'], car['original_price_text']))
                count += 1
            except sqlite3.Error:
                pass 
        conn.commit()
        conn.close()
        # Optional: Print progress
        # print(f"   Saved {count} cars.")

def run_price_range(min_p, max_p):
    """Orchestrates scraping for a specific price bracket."""
    global stop_current_range
    stop_current_range = False
    
    print(f"\n[>>>] Starting Range: ${min_p} - ${max_p}")
    
    empty_page_streak = 0
    total_cars_in_range = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Map futures to page numbers
        future_to_page = {
            executor.submit(scrape_page, i, min_p, max_p): i 
            for i in range(1, MAX_PAGES_PER_RANGE + 1)
        }
        
        for future in as_completed(future_to_page):
            page = future_to_page[future]
            try:
                cars = future.result()
                if cars:
                    save_batch(cars)
                    total_cars_in_range += len(cars)
                    print(f"    Page {page}: {len(cars)} cars (Total in range: {total_cars_in_range})")
                    empty_page_streak = 0 
                else:
                    # If we hit empty pages, we track them. 
                    # Note: Due to threading, page 50 might finish before page 10, 
                    # so this is just a loose indicator.
                    empty_page_streak += 1
            except Exception as exc:
                print(f"    Page {page} generated an exception: {exc}")

    print(f"[<<<] Finished Range ${min_p}-${max_p}. Total cars: {total_cars_in_range}")

def main():
    init_db()
    
    # Iterate through the defined price ranges sequentially
    for min_price, max_price in PRICE_RANGES:
        run_price_range(min_price, max_price)
        # Small delay between ranges
        time.sleep(2)

    print("\n[*] All ranges complete. Check database.db")

if __name__ == "__main__":
    main()