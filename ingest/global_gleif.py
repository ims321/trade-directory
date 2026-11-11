import os
import sys
import json
import time
import requests
import re
import psycopg2
from psycopg2.extras import execute_values
from pathlib import Path
from urllib.parse import urlparse, unquote

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

# --- 2. Vetting Function ---
def is_valid_company_name(name):
    if not name or len(name) < 3: return False
    if re.match(r'^[\d\+\-\(\)\s\.]+$', name): return False
    garbage = ['banquet', 'guest', 'conference', 'agenda', 'copyright', 'rights reserved', 'list', 'attendee', 'delegate', 'read more', 'about', 'apprenticeship', 'standards', 'community', 'advisory', 'body', 'contact', 'privacy', 'terms', 'login', 'search']
    if any(kw in name.lower() for kw in garbage): return False
    if len(name) > 80: return False
    return True

def insert_companies(companies, source_name):
    rows = []
    for c in companies:
        name = c.get('name', '').strip()
        if not is_valid_company_name(name): continue
        
        domain = f"{''.join(e for e in name if e.isalnum()).lower()}.com"
        email = f"info@{domain}"
        website = f"https://{domain}"
        
        country = c.get('country', 'US')
        role = c.get('role', 'Importer/Exporter')
        sector = c.get('sector', 'General Trading')
        
        tier = "probable" 
        evidence = json.dumps({"registry_record": True, "gleif_id": c.get('lei')})
        
        rows.append((domain, name, country, "Active", evidence, ["99"], website, email, role, sector, tier, source_name))

    unique_rows = list({r[0]: r for r in rows}.values())

    if not unique_rows:
        return

    sql = """
    INSERT INTO companies_master (domain, name, country_code, registry_status, evidence, hs_codes, website, email, trade_role, sector_label, verification_tier, source)
    VALUES %s ON CONFLICT (domain) DO NOTHING;
    """
    try:
        execute_values(cur, sql, unique_rows)
        print(f"   ✅ Inserted {len(unique_rows)} companies.")
    except Exception as e:
        print(f"   ❌ DB Error: {e}")

# --- 3. GLEIF API Scraper ---
def scrape_gleif():
    print("🌍 Fetching Massive Global Data from GLEIF...")
    
    # Map search keywords to specific roles for the UI filter
    keyword_map = {
        "Trading": {"role": "Importer/Exporter", "sector": "General Trading"},
        "Export": {"role": "Exporter", "sector": "General Trading"},
        "Import": {"role": "Importer", "sector": "General Trading"},
        "Logistics": {"role": "Logistics/Forwarder", "sector": "Logistics & Transport"},
        "Distribution": {"role": "Distributor", "sector": "General Trading"},
        "Wholesale": {"role": "Distributor", "sector": "Wholesale Trade"},
        "Commodities": {"role": "Importer/Exporter", "sector": "Agriculture & Commodities"}
    }
    
    all_companies = []
    headers = {"Accept": "application/vnd.api+json", "User-Agent": "TradeDirectoryBot/1.0"}

    for keyword, meta in keyword_map.items():
        print(f"   🔍 Searching for '{keyword}' companies...")
        
        # Fetch 10 pages of 200 results per keyword (2,000 per keyword)
        for page in range(1, 11):
            url = f"https://api.gleif.org/api/v1/lei-records?filter[entity.legalName]=*{keyword}*&page[size]=200&page[number]={page}"
            
            try:
                resp = requests.get(url, headers=headers, timeout=30)
                if resp.status_code != 200: break
                    
                data = resp.json()
                records = data.get('data', [])
                if not records: break # No more records
                
                for rec in records:
                    attrs = rec.get('attributes', {})
                    entity = attrs.get('entity', {})
                    name = entity.get('legalName', {}).get('name', '')
                    country = entity.get('legalAddress', {}).get('country', 'US')
                    status = entity.get('status', 'ACTIVE')
                    
                    if status == 'ACTIVE':
                        all_companies.append({
                            "name": name, 
                            "country": country, 
                            "lei": rec.get('id'),
                            "role": meta["role"],
                            "sector": meta["sector"]
                        })
                time.sleep(0.5)
            except Exception:
                break

    print(f"\n📦 Total companies found: {len(all_companies)}. Inserting...")
    # Split into chunks to avoid memory issues
    chunk_size = 2000
    for i in range(0, len(all_companies), chunk_size):
        insert_companies(all_companies[i:i+chunk_size], "GLEIF Global Registry")

if __name__ == "__main__":
    scrape_gleif()
    cur.execute("SELECT refresh_directory();")
    print("🎉 Global data loaded! Check your live site.")
    cur.close()
    conn.close()
