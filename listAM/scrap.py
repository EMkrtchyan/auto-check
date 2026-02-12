import sqlite3
import time
import random
import undetected_chromedriver as uc
from bs4 import BeautifulSoup

#CONFIGURATION
BASE_URL = "https://www.list.am/en/category/23"
TOTAL_PAGES = 250
DB_NAME = 'database.db'

#DATABASE SETUP
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS items (
            id TEXT PRIMARY KEY,
            image_src TEXT,
            p_text TEXT,
            l_text TEXT,
            at_text TEXT
        )
    ''')
    conn.commit()
    conn.close()

def save_items(items):
    if not items: return
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.executemany('''
            INSERT OR REPLACE INTO items (id, image_src, p_text, l_text, at_text)
            VALUES (?, ?, ?, ?, ?)
        ''', items)
        conn.commit()
    except Exception as e:
        print(f"DB Error: {e}")
    conn.close()

def main():
    init_db()
    
    #SETUP UNDETECTED CHROME
    options = uc.ChromeOptions()
    
    print("Starting Browser...")
    driver = uc.Chrome(options=options, version_main=144, use_subprocess=True)
    
    try:
        for page_num in range(1, TOTAL_PAGES + 1):
            
            url = BASE_URL if page_num == 1 else f"{BASE_URL}/{page_num}"
            
            print(f"Navigating to Page {page_num}...")
            driver.get(url)
            
            #Check for Cloudflare/CAPTCHA
            title = driver.title
            if "Just a moment" in title or "Security" in title:
                print("Cloudflare detected. Waiting 15s for auto-redirect")
                time.sleep(15)
            
            #Human-like Scroll
            driver.execute_script("window.scrollTo(0, 500);")
            time.sleep(random.uniform(1.5, 3.0))
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
            time.sleep(random.uniform(1.5, 3.0))
            
            #Parse
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            containers = soup.find_all('div', class_='gl')
            
            if not containers:
                print(f"Page {page_num}: No items found (Possible soft block). Waiting 10s...")
                time.sleep(10)
                continue

            #Extract
            extracted_items = []
            all_links = []
            for container in containers:
                all_links.extend(container.find_all('a'))
                
            for link in all_links:
                href = link.get('href')
                if not href: continue
                try:
                    item_id = href.split('/item/')[1].split('?')[0]
                except IndexError:
                    continue

                img_tag = link.find('img')
                img_src = "N/A"
                if img_tag:
                    raw_src = img_tag.get('data-original') or img_tag.get('src')
                    if raw_src and raw_src.startswith('//'):
                        img_src = 'https:' + raw_src
                    elif raw_src:
                        img_src = raw_src

                p_text = link.find('div', class_='p').get_text(strip=True) if link.find('div', class_='p') else "N/A"
                l_text = link.find('div', class_='l').get_text(strip=True) if link.find('div', class_='l') else "N/A"
                at_text = link.find('div', class_='at').get_text(strip=True) if link.find('div', class_='at') else "N/A"

                extracted_items.append((item_id, img_src, p_text, l_text, at_text))
            
            #Save
            save_items(extracted_items)
            print(f"--> Page {page_num}: Saved {len(extracted_items)} items.")

    except Exception as e:
        print(f"Critical Error: {e}")
        
    finally:
        print("Closing Driver...")
        driver.quit()

if __name__ == '__main__':
    main()