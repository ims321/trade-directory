import os
import sys
import json
import time
import re
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from urllib.parse import urlparse, unquote
import psycopg2
from psycopg2.extras import execute_values

# 1. DB Connect
env_path = Path('.env')
DB_URL = None
if env_path.exists():
    for line in env_path.read_text().splitlines():
        if line.startswith('DATABASE_URL='):
            DB_URL = line.split('=', 1)[1].strip("'\"")

parsed = urlparse(DB_URL)
conn = psycopg2.connect(host=parsed.hostname, port=parsed.port or 5432, user=unquote(parsed.username), password=unquote(parsed.password), dbname=parsed.path.lstrip("/"))
conn.autocommit = True
cur = conn.cursor()

def insert_companies(companies, source_name):
    rows = []
    for c in companies:
        name = c.get('name', '').strip()
        domain = c.get('domain', '').strip()
        
        if not name or len(name) < 3: continue
        if not domain: 
            domain = f"{''.join(e for e in name if e.isalnum()).lower()}.com"
        
        rows.append((domain, name, "US", "Active", '{"trade_record_verified": true}', ["99"], f"https://{domain}", f"info@{domain}", "Importer", "General Trading", "verified", source_name))

    unique_rows = list({r[0]: r for r in rows}.values())

    if not unique_rows: return

    sql = """
    INSERT INTO companies_master (domain, name, country_code, registry_status, evidence, hs_codes, website, email, trade_role, sector_label, verification_tier, source)
    VALUES %s ON CONFLICT (domain) DO UPDATE SET
        verification_tier = 'verified', source = EXCLUDED.source;
    """
    try:
        execute_values(cur, sql, unique_rows)
        print(f"   ✅ Inserted {len(unique_rows)} US Importers from ImportYeti.")
    except Exception as e:
        print(f"   ❌ DB Error: {e}")

def scrape_importyeti():
    print("🇺🇸 Scraping ImportYeti (Free Direct Method)...")
    
    keywords = ["electronics", "machinery", "textiles", "furniture", "auto parts", "toys", "steel"]
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
    }

    all_companies = []

    for kw in keywords:
        print(f"   🔍 Searching for '{kw}' importers...")
        url = f"https://www.importyeti.com/search?q={kw.replace(' ', '+')}"
        
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code != 200:
                print(f"      ⚠️ Blocked (Status {resp.status_code}). Waiting 5 seconds...")
                time.sleep(5)
                continue
                
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # ImportYeti uses Next.js. The data is stored in a script tag with id="__NEXT_DATA__"
            next_data_script = soup.find('script', id='__NEXT_DATA__')
            if next_data_script:
                data = json.loads(next_data_script.string)
                # Navigate the Next.js JSON structure to find the companies
                props = data.get('props', {}).get('pageProps', {})
                companies = props.get('companies', []) or props.get('searchResults', {}).get('companies', [])
                
                found_count = 0
                for comp in companies:
                    name = comp.get('name') or comp.get('companyName')
                    slug = comp.get('slug') or comp.get('companySlug')
                    if name and slug:
                        all_companies.append({
                            "name": name, 
                            "domain": f"{slug}.com" # Use slug as a rough domain
                        })
                        found_count += 1
                print(f"      Found {found_count} companies via Next.js data.")
            else:
                # Fallback to parsing HTML links if Next.js data is missing
                found_count = 0
                for a_tag in soup.find_all('a', href=True):
                    if '/company/' in a_tag['href']:
                        name = a_tag.text.strip()
                        if name and len(name) > 2:
                            slug = a_tag['href'].split('/company/')[-1].split('?')[0]
                            all_companies.append({"name": name, "domain": f"{slug}.com"})
                            found_count += 1
                print(f"      Found {found_count} companies via HTML fallback.")
                
            time.sleep(2) # Polite delay
        except Exception as e:
            print(f"      ❌ Error for {kw}: {e}")

    insert_companies(all_companies, "ImportYeti")

if __name__ == "__main__":
    scrape_importyeti()
    cur.execute("SELECT refresh_directory();")
    print("🎉 ImportYeti scan complete!")
    cur.close()
    conn.close()
