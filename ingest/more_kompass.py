import os
import sys
import json
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

def insert_companies(companies, source_name):
    rows = []
    seen_domains = set()
    seen_names = set()
    banned = ['facebook.com', 'linkedin.com', 'twitter.com', 'instagram.com', 'youtube.com', 'google.com']

    for c in companies:
        name = c.get('name', '').strip()
        website = c.get('website', '').strip()
        
        if not name or len(name) < 3: continue
        if name.lower() in seen_names: continue
        seen_names.add(name.lower())
        
        domain = None
        email = None
        
        if website and website.startswith('http'):
            domain = website.replace("https://", "").replace("http://", "").split("/")[0].lower()
            if any(b in domain for b in banned): continue
            if domain in seen_domains: continue
            seen_domains.add(domain)
            email = f"info@{domain}"

        rows.append((
            domain, name, c.get('country', 'US'), "Active", 
            '{"directory_verified": true}', ["99"], 
            website if website else None, email, 
            "Importer/Exporter", "General Trading", "probable", source_name
        ))

    if not rows: 
        print(f"   ⚠️ No valid companies found for {source_name}.")
        return

    sql = """
    INSERT INTO companies_master (domain, name, country_code, registry_status, evidence, hs_codes, website, email, trade_role, sector_label, verification_tier, source)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (domain) DO NOTHING;
    """
    try:
        execute_batch(cur, sql, rows)
        print(f"   ✅ Successfully inserted {len(rows)} companies from {source_name}.")
    except Exception as e:
        print(f"   ❌ DB Error for {source_name}: {e}")

def run_kompass(client):
    # We use our remaining 3 runs on high-volume markets: Germany, France, Brazil
    countries = {
        "DE": "Germany",
        "FR": "France",
        "BR": "Brazil"
    }
    
    for code, name in countries.items():
        print(f"\n🌍 Scraping Kompass in '{name}' ({code})...")
        try:
            run_input = {
                "mode": "company",
                "country": code.lower(),
                "query": "distributor trading", # Using a broader search term
                "maxResults": 200, 
                "enrichDetails": True
            }
            
            # Run the actor
            run = client.actor("lentic_clockss/kompass-scraper").call(run_input=run_input)
            
            # Fetch dataset ID safely
            dataset_id = getattr(run, 'default_dataset_id', None) or run.get('defaultDatasetId')
            if not dataset_id:
                print(f"   ⚠️ No dataset returned for {name}.")
                continue
                
            items = client.dataset(dataset_id).list_items().items
            print(f"   Found {len(items)} raw records.")
            
            companies = []
            for item in items:
                companies.append({
                    "name": item.get("name"),
                    "website": item.get("website") or "",
                    "country": code
                })
                
            insert_companies(companies, f"Kompass ({code})")
            
        except Exception as e:
            print(f"   ❌ Error scraping {name}: {str(e)[:80]}")
            print("   (You may have hit your 10-run free tier limit on Apify).")

if __name__ == "__main__":
    print("🚀 Starting Expansion into Europe & South America...")
    print("🔑 Please paste your Apify API token:")
    token = input("> ").strip()
    
    if not token:
        sys.exit(1)
        
    client = ApifyClient(token)
    run_kompass(client)

    print("\n⚙️ Refreshing directory view...")
    cur.execute("SELECT refresh_directory();")
    print("🎉 Expansion complete! Check your live site.")
    
    cur.close()
    conn.close()
