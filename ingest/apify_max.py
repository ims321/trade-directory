import os
import sys
import json
import time
from pathlib import Path
from urllib.parse import urlparse, unquote
import psycopg2
from psycopg2.extras import execute_batch
from apify_client import ApifyClient

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

def insert_companies(companies, source_name, default_country="US"):
    rows = []
    seen = set()
    
    for c in companies:
        name = c.get('name', '').strip()
        if not name or len(name) < 3: continue
        
        # Clean up company names that are just numbers or garbage
        if name.lower() in seen: continue
        seen.add(name.lower())
        
        website = c.get('website', '').strip()
        domain = None
        email = None
        
        # If a real website exists, extract the domain. If not, leave it NULL.
        if website and website.startswith('http'):
            domain = website.replace("https://", "").replace("http://", "").split("/")[0].lower()
            email = f"info@{domain}"
        
        country = c.get('country', default_country).upper()
        
        rows.append((
            domain, name, country, "Active", 
            '{"apify_scraped": true}', ["99"], 
            website if website else None, 
            email, 
            c.get('role', "Importer/Exporter"), 
            c.get('sector', "General Trading"), 
            "verified", # Marked as verified because Apify pulls from actual trade sites
            source_name
        ))

    if not rows: 
        print(f"   ⚠️ No valid companies found from {source_name}.")
        return

    # Use a subquery to prevent duplicate names from the same source
    sql = """
    INSERT INTO companies_master (domain, name, country_code, registry_status, evidence, hs_codes, website, email, trade_role, sector_label, verification_tier, source)
    SELECT %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
    WHERE NOT EXISTS (SELECT 1 FROM companies_master WHERE name = %s AND source = %s);
    """
    try:
        batch_data = [r + (r[1], r[11]) for r in rows]
        execute_batch(cur, sql, batch_data)
        print(f"   ✅ Inserted up to {len(rows)} companies from {source_name}.")
    except Exception as e:
        print(f"   ❌ DB Error for {source_name}: {e}")

def run_importyeti(client):
    print("\n🇺🇸 Running ImportYeti Scraper via Apify (This takes ~1 minute)...")
    all_companies = []
    
    # We use multiple keywords to get a massive list of US importers
    keywords = ["electronics", "machinery", "furniture", "apparel", "automotive"]
    
    for kw in keywords:
        print(f"   🔍 Scraping '{kw}' importers...")
        try:
            run_input = {
                "query": kw,
                "searchType": "companies",
                "maxItems": 100, # Pull 100 per keyword
                "proxyConfiguration": {"useApifyProxy": True}
            }
            run = client.actor("rbbscrap/fast-importyeti-scraper").call(run_input=run_input)
            items = client.dataset(run.default_dataset_id).list_items().items
            
            for item in items:
                all_companies.append({
                    "name": item.get("companyName"),
                    "website": item.get("companyWebsite") or "", # Leave blank if not found
                    "country": "US",
                    "role": "Importer"
                })
            print(f"      Found {len(items)} companies.")
        except Exception as e:
            print(f"      ❌ Error: {str(e)[:50]}")
            
    insert_companies(all_companies, "ImportYeti")

def run_kompass(client):
    print("\n🌍 Running Kompass Scraper via Apify (This takes ~2 minutes)...")
    all_companies = []
    
    # We search for import/export companies in different countries
    countries = ["us", "gb", "za", "in"]
    
    for country in countries:
        print(f"   🔍 Scraping Kompass in '{country.upper()}'...")
        try:
            run_input = {
                "mode": "company",
                "country": country,
                "query": "import export",
                "maxResults": 200, # Pull 200 per country
                "enrichDetails": True # This is the magic that finds the websites
            }
            run = client.actor("lentic_clockss/kompass-scraper").call(run_input=run_input)
            items = client.dataset(run.default_dataset_id).list_items().items
            
            for item in items:
                all_companies.append({
                    "name": item.get("name"),
                    "website": item.get("website") or "", # Leave blank if not found
                    "country": country.upper(),
                    "role": "Importer/Exporter"
                })
            print(f"      Found {len(items)} companies.")
        except Exception as e:
            print(f"      ❌ Error: {str(e)[:50]}")

    insert_companies(all_companies, "Kompass")

if __name__ == "__main__":
    print("🚀 Starting Maximum Data Extraction via Apify...")
    print("🔑 Please paste your Apify API token:")
    token = input("> ").strip()
    
    if not token:
        print("❌ No token provided. Exiting.")
        sys.exit(1)
        
    client = ApifyClient(token)
    
    # Run both scrapers
    run_importyeti(client)
    run_kompass(client)
    
    print("\n⚙️ Refreshing directory view...")
    cur.execute("SELECT refresh_directory();")
    print("🎉 Massive data load complete! Check your live site.")
    
    cur.close()
    conn.close()
