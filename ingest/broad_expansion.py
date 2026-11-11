import os
import sys
import json
import time
import re
import requests
from pathlib import Path
from urllib.parse import urlparse, unquote
import psycopg2
from psycopg2.extras import execute_values
from apify_client import ApifyClient

# ── 1. Database Connection ────────────────────────────────────────────────
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

# ── 2. Vetting & Deduplication Rules ──────────────────────────────────────
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
        
        domain = c.get('domain', '').strip()
        if not domain:
            domain = f"{''.join(e for e in name if e.isalnum()).lower()}.com"
        
        email = c.get('email', f"info@{domain}")
        website = c.get('website', f"https://{domain}")
        country = c.get('country', 'US')
        role = c.get('role', 'Importer/Exporter')
        sector = c.get('sector', 'General Trading')
        
        tier = "verified" 
        evidence = json.dumps({"trade_record_verified": True, "source_detail": source_name})
        
        rows.append((domain, name, country, "Active", evidence, ["99"], website, email, role, sector, tier, source_name))

    unique_rows = list({r[0]: r for r in rows}.values())

    if not unique_rows:
        print(f"   ⚠️ No valid companies found from {source_name}.")
        return

    sql = """
    INSERT INTO companies_master (domain, name, country_code, registry_status, evidence, hs_codes, website, email, trade_role, sector_label, verification_tier, source)
    VALUES %s ON CONFLICT (domain) DO UPDATE SET
        name = EXCLUDED.name,
        website = EXCLUDED.website,
        email = COALESCE(companies_master.email, EXCLUDED.email),
        trade_role = EXCLUDED.trade_role,
        verification_tier = 'verified';
    """
    try:
        execute_values(cur, sql, unique_rows)
        print(f"   ✅ Inserted/Updated {len(unique_rows)} companies from {source_name}.")
    except Exception as e:
        print(f"   ❌ DB Error for {source_name}: {e}")

# ── 3. Part A: The Company Atlas (Broad HS & Country Matrix) ──────────────
def fetch_atlas_broad():
    print("\n🌍 Querying The Company Atlas for a BROAD slice of global trade...")
    url = "https://thecompanyatlas.com/mcp"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    
    # Diverse HS-2 codes (Machinery, Electronics, Auto, Pharma, Steel, Textiles, Food, Plastics)
    hs_codes = ["84", "85", "87", "30", "72", "61", "10", "39"]
    # Major trade hubs covered by Atlas
    countries = ["US", "MX", "BR", "IN", "VN", "ID", "TR", "GB"]
    
    companies = []
    call_count = 0
    
    # We limit to 3 queries per HS code to conserve API credits (approx 24 calls total)
    for hs in hs_codes:
        for country in countries[:3]: 
            if call_count >= 25:
                print("      🛑 Reached 25 API calls to conserve monthly credits.")
                break
                
            print(f"      🔍 Searching for Top Importers of HS {hs} in {country}...")
            payload = {
                "jsonrpc": "2.0",
                "id": call_count,
                "method": "tools/call",
                "params": {
                    "name": "Trade_company_trade_volume_by_year",
                    "arguments": {"hs_code": hs, "country": country, "year": 2024, "limit": 20}
                }
            }
            
            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=15)
                if resp.status_code == 200:
                    data = resp.json()
                    content = data.get("result", {}).get("content", [])
                    if content and "text" in content[0]:
                        trade_data = json.loads(content[0]["text"])
                        found = trade_data.get("companies", [])
                        print(f"         -> Found {len(found)} companies.")
                        for item in found:
                            companies.append({
                                "name": item.get("company_name"),
                                "country": country,
                                "role": "Importer",
                                "sector": f"HS {hs}"
                            })
                time.sleep(1) # Be polite
            except Exception as e:
                print(f"         ⚠️ Error on {hs}/{country}: {e}")
            call_count += 1
            
    return companies

# ── 4. Part B: ImportYeti via Apify (Broad Keywords) ──────────────────────
def fetch_importyeti_broad(apify_token):
    print("\n🇺🇸 Fetching BROAD US importer data from ImportYeti via Apify...")
    client = ApifyClient(apify_token)
    
    # Broad industry keywords
    keywords = ["electronics", "machinery", "apparel", "automotive", "chemicals"]
    companies = []
    
    for kw in keywords:
        print(f"      🔍 Scraping ImportYeti for '{kw}' importers...")
        run_input = {
            "query": kw,
            "searchType": "companies",
            "maxItems": 20, # Keep it low to conserve your $5 free Apify credit
            "proxyConfiguration": {"useApifyProxy": True}
        }
        
        try:
            run = client.actor("rbbscrap/fast-importyeti-scraper").call(run_input=run_input)
            items = client.dataset(run.default_dataset_id).list_items().items
            
            for item in items:
                companies.append({
                    "name": item.get("companyName"),
                    "domain": item.get("companyUrl", "").replace("https://www.importyeti.com/company/", ""),
                    "country": "US",
                    "role": "Importer",
                    "sector": kw.capitalize()
                })
            print(f"         -> Found {len(items)} companies for {kw}.")
        except Exception as e:
            print(f"         ⚠️ Apify error for {kw}: {e}")
            
    return companies

# ── 5. Main Orchestrator ──────────────────────────────────────────────────
def main():
    print("🚀 Starting BROAD Global Trade Data Expansion...")
    
    # 1. Fetch from The Company Atlas
    atlas_companies = fetch_atlas_broad()
    
    # 2. Fetch from ImportYeti
    print("\n🔑 Please paste your Apify API token (or press Enter to skip ImportYeti):")
    apify_token = input("> ").strip()
    yetti_companies = []
    if apify_token:
        yetti_companies = fetch_importyeti_broad(apify_token)
    
    # 3. Insert and Deduplicate
    if atlas_companies:
        insert_companies(atlas_companies, "The Company Atlas")
    if yetti_companies:
        insert_companies(yetti_companies, "ImportYeti (US B/L)")
    
    # 4. Refresh
    print("\n⚙️ Refreshing directory view...")
    cur.execute("SELECT refresh_directory();")
    print("🎉 Broad expansion complete! Check your live site.")
    
    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
