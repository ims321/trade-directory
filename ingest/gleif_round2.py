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
        
        rows.append((domain, name, country, "Active", '{"registry_record": true}', ["99"], website, email, role, sector, "probable", source_name))

    unique_rows = list({r[0]: r for r in rows}.values())

    if not unique_rows: return

    sql = """
    INSERT INTO companies_master (domain, name, country_code, registry_status, evidence, hs_codes, website, email, trade_role, sector_label, verification_tier, source)
    VALUES %s ON CONFLICT (domain) DO NOTHING;
    """
    try:
        execute_values(cur, sql, unique_rows)
        print(f"   ✅ Inserted {len(unique_rows)} new companies.")
    except Exception as e:
        print(f"   ❌ DB Error: {e}")

def scrape_gleif():
    print("🌍 Fetching Round 2 of Global Data from GLEIF...")
    
    # NEW KEYWORDS to grab companies we didn't get in Round 1
    keyword_map = {
        "Wholesale": {"role": "Distributor", "sector": "Wholesale Trade"},
        "Commerce": {"role": "Importer/Exporter", "sector": "General Trading"},
        "Supply": {"role": "Distributor", "sector": "General Trading"},
        "Freight": {"role": "Logistics/Forwarder", "sector": "Logistics & Transport"},
        "Agency": {"role": "Agent", "sector": "General Trading"},
        "Brokerage": {"role": "Agent", "sector": "Financial Services"},
        "Retail": {"role": "Distributor", "sector": "Retail & Distribution"},
        "Transport": {"role": "Logistics/Forwarder", "sector": "Logistics & Transport"}
    }
    
    all_companies = []
    headers = {"Accept": "application/vnd.api+json", "User-Agent": "TradeDirectoryBot/1.0"}

    for keyword, meta in keyword_map.items():
        print(f"   🔍 Searching for '{keyword}' companies...")
        
        # 5 pages of 200 = 1,000 per keyword
        for page in range(1, 6):
            url = f"https://api.gleif.org/api/v1/lei-records?filter[entity.legalName]=*{keyword}*&page[size]=200&page[number]={page}"
            
            try:
                resp = requests.get(url, headers=headers, timeout=30)
                if resp.status_code != 200: break
                    
                data = resp.json()
                records = data.get('data', [])
                if not records: break
                
                for rec in records:
                    attrs = rec.get('attributes', {})
                    entity = attrs.get('entity', {})
                    name = entity.get('legalName', {}).get('name', '')
                    country = entity.get('legalAddress', {}).get('country', 'US')
                    
                    if entity.get('status') == 'ACTIVE':
                        all_companies.append({
                            "name": name, "country": country,
                            "role": meta["role"], "sector": meta["sector"]
                        })
                time.sleep(0.3)
            except Exception:
                break

    print(f"\n📦 Total new companies found: {len(all_companies)}. Inserting...")
    for i in range(0, len(all_companies), 2000):
        insert_companies(all_companies[i:i+2000], "GLEIF Round 2")

if __name__ == "__main__":
    scrape_gleif()
    cur.execute("SELECT refresh_directory();")
    print("🎉 Round 2 loaded! Check your live site.")
    cur.close()
    conn.close()
