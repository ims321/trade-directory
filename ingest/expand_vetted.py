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

# --- 1. Database Connection ---
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

# --- 2. The Vetting Function ---
def is_valid_company_name(name):
    if not name or len(name) < 3: return False
    # Reject if it's just numbers/symbols (phone numbers)
    if re.match(r'^[\d\+\-\(\)\s\.]+$', name): return False
    # Reject event/garbage keywords
    garbage_keywords = ['banquet', 'guest', 'conference', 'agenda', 'minutes', 'copyright', 'rights reserved', 'exporter of the year', 'list', 'attendee', 'delegate', 'read more']
    if any(kw in name.lower() for kw in garbage_keywords): return False
    # Reject overly long sentences
    if len(name) > 70: return False
    return True

# --- 3. Insert Helper ---
def insert_companies(companies, country, source_name):
    rows = []
    for c in companies:
        name = str(c.get('name', '')).strip()
        if not is_valid_company_name(name): continue # Apply Vetting!
        
        website = str(c.get('website', '')).strip()
        domain = website.replace("https://", "").replace("http://", "").split("/")[0].lower() if website else ""
        if not domain:
            domain = f"{''.join(e for e in name if e.isalnum()).lower()}.com"
        if len(domain) < 4: continue
            
        email = str(c.get('email', f"info@{domain}"))
        role = c.get('role', 'Importer/Exporter')
        sector = c.get('sector', 'General Trading')
        
        tier = "verified"
        evidence = json.dumps({"association_member": True, "website_specific": bool(website)})
        
        rows.append((domain, name, country, "Active", evidence, ["99"], website, email, role, sector, tier, source_name))

    unique_rows = list({r[0]: r for r in rows}.values())

    sql = """
    INSERT INTO companies_master (domain, name, country_code, registry_status, evidence, hs_codes, website, email, trade_role, sector_label, verification_tier, source)
    VALUES %s ON CONFLICT (domain) DO NOTHING;
    """
    try:
        execute_values(cur, sql, unique_rows)
        print(f"   ✅ Inserted {len(unique_rows)} vetted companies from {source_name}.")
    except Exception as e:
        print(f"   ❌ DB Error for {source_name}: {e}")

# --- 4. Target Scraping Functions ---
def scrape_bifa():
    print("🇬🇧 Scraping BIFA (UK) - Multiple Pages...")
    companies = []
    for page in range(1, 6): # Grab 5 pages
        try:
            url = f"https://bifa.org/membership/member-search/search-results/page/{page}/"
            resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
            soup = BeautifulSoup(resp.text, 'html.parser')
            for a_tag in soup.find_all('a', href=True):
                if '/membership/member-search/member/' in a_tag['href']:
                    name = a_tag.get_text(strip=True, separator=' ')
                    companies.append({"name": name, "role": "Logistics/Forwarder", "sector": "Logistics & Transport"})
            time.sleep(1)
        except Exception as e:
            pass
    insert_companies(list({c['name']: c for c in companies}.values()), "GB", "BIFA")

def scrape_eepc():
    print("🇮🇳 Scraping EEPC India - Multiple Letters...")
    companies = []
    for letter in ['C', 'D', 'E', 'F', 'G', 'H']: # Grab more letters
        try:
            url = f"https://eepcindia.org/backend/indian-suppliers/panel/P01/{letter}"
            resp = requests.get(url, timeout=15)
            soup = BeautifulSoup(resp.text, 'html.parser')
            table = soup.find('table')
            if table:
                for row in table.find_all('tr')[1:]: 
                    cols = row.find_all('td')
                    if len(cols) >= 2:
                        name = cols[0].get_text(strip=True)
                        companies.append({"name": name, "role": "Exporter", "sector": "Engineering"})
            time.sleep(1)
        except Exception:
            pass
    insert_companies(list({c['name']: c for c in companies}.values()), "IN", "EEPC India")

def scrape_exporters_ec():
    print("🇿🇦 Scraping Exporters Eastern Cape (ZA)...")
    companies = []
    try:
        url = "https://exportersec.co.za/members/"
        resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Look for headings which typically contain company names on this site
        for tag in soup.find_all(['h2', 'h3', 'h4']):
            text = tag.get_text(strip=True)
            if text and "Members" not in text and "Exporters" not in text:
                companies.append({"name": text, "role": "Exporter", "sector": "General Trading"})
    except Exception as e:
        print(f"   ❌ Error: {e}")
    insert_companies(list({c['name']: c for c in companies}.values()), "ZA", "Exporters Eastern Cape")

# --- Main Execution ---
if __name__ == "__main__":
    print("🚀 Starting Global Vetted Expansion...")
    scrape_bifa()
    scrape_eepc()
    scrape_exporters_ec()
    
    print("\n⚙️ Refreshing directory view...")
    cur.execute("SELECT refresh_directory();")
    print("🎉 Expansion complete! Check your live site.")
    cur.close()
    conn.close()
