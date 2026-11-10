import os
import sys
import json
import psycopg2
from psycopg2.extras import execute_values
from pathlib import Path
from urllib.parse import urlparse, unquote
from apify_client import ApifyClient

# 1. Connect to DB
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

# 2. Ask for Apify Token
print("🔑 Please paste your Apify API token and press Enter:")
APIFY_TOKEN = input("> ").strip()
client = ApifyClient(APIFY_TOKEN)

print("🚀 Starting Kompass Scraper via Apify...")
run_input = {
    "mode": "company",
    "country": "za",       
    "query": "import",     
    "maxResults": 100,     
    "maxPages": 1,
    "enrichDetails": True  
}

try:
    run = client.actor("lentic_clockss/kompass-scraper").call(run_input=run_input)
    dataset_id = run.default_dataset_id 
    print(f"✅ Scraping complete. Dataset ID: {dataset_id}")
except Exception as e:
    print(f"❌ Apify error: {e}")
    sys.exit(1)

print("📥 Downloading results...")
dataset_items = client.dataset(dataset_id).list_items().items
print(f"📦 Found {len(dataset_items)} real companies from Kompass.")

rows = []
for item in dataset_items:
    # Safely handle None values for all fields
    raw_name = item.get("name")
    name = str(raw_name).strip() if raw_name else "Unknown Company"

    raw_website = item.get("website")
    website = str(raw_website).strip() if raw_website else ""
    
    domain = website.replace("https://", "").replace("http://", "").split("/")[0].lower() if website else ""
    if not domain:
        clean_name = "".join(e for e in name if e.isalnum()).lower()
        domain = f"{clean_name or 'unknown'}.com"
        
    raw_email = item.get("email")
    email = str(raw_email).strip() if raw_email else f"info@{domain}"
    
    raw_sector = item.get("industry")
    sector = str(raw_sector).strip() if raw_sector else "Wholesale Trade"
    
    country = "ZA" 
    
    role = "Importer/Exporter"
    if "distribut" in sector.lower(): role = "Distributor"
    if "logistic" in sector.lower() or "freight" in sector.lower(): role = "Logistics/Forwarder"
    
    hs = ["99"]
    tier = "verified"
    source = "Kompass"
    evidence = json.dumps({"website_specific": bool(website), "directory_listing": True})
    
    rows.append((domain, name, country, "Active", evidence, hs, website, email, role, sector, tier, source))

unique_rows = list({r[0]: r for r in rows if r[0]}.values())

print(f"💾 Inserting {len(unique_rows)} unique companies into Supabase...")
sql = """
INSERT INTO companies_master (domain, name, country_code, registry_status, evidence, hs_codes, website, email, trade_role, sector_label, verification_tier, source)
VALUES %s ON CONFLICT (domain) DO UPDATE SET
    name = EXCLUDED.name,
    website = EXCLUDED.website,
    email = COALESCE(companies_master.email, EXCLUDED.email),
    source = EXCLUDED.source;
"""

try:
    execute_values(cur, sql, unique_rows)
    cur.execute("SELECT refresh_directory();")
    print("🎉 SUCCESS! Kompass data successfully loaded into your directory.")
except Exception as e:
    print(f"❌ Database error: {e}")

cur.close()
conn.close()
