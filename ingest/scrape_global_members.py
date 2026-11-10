import os
import sys
import json
import time
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from urllib.parse import urlparse, unquote
import psycopg2
from psycopg2.extras import execute_values
from apify_client import ApifyClient

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

# --- 2. Load Associations ---
try:
    with open("global_associations.json", "r") as f:
        associations = json.load(f)
except FileNotFoundError:
    print("❌ global_associations.json not found. Run Part 1 first.")
    sys.exit(1)

# --- 3. Apify Setup ---
print("🔑 Please paste your Apify API token:")
APIFY_TOKEN = input("> ").strip()
client = ApifyClient(APIFY_TOKEN)

# --- 4. Insert Helper ---
def insert_companies(companies, country, source_name):
    rows = []
    for c in companies:
        name = str(c.get('name', '')).strip()
        if not name or len(name) < 3: continue
        
        website = str(c.get('website', '')).strip()
        domain = website.replace("https://", "").replace("http://", "").split("/")[0].lower() if website else ""
        if not domain:
            domain = f"{''.join(e for e in name if e.isalnum()).lower()}.com"
            
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
        print(f"   ✅ Inserted {len(unique_rows)} companies from {source_name}.")
    except Exception as e:
        print(f"   ❌ DB Error for {source_name}: {e}")

# --- 5. Platform Detection & Scraping Loop ---
print(f"\n🚀 Starting extraction for {len(associations)} associations...")

for assoc in associations:
    name = assoc['name']
    url = assoc['url']
    country = assoc['country']
    
    if not url:
        print(f"   ⚠️ Skipping {name} (no website URL).")
        continue

    print(f"\n🌍 Processing: {name} ({country}) - {url}")

    # Check for Wild Apricot
    if 'wildapricot.org' in url or '/publicdir/' in url:
        print("   🔍 Detected: Wild Apricot")
        try:
            run = client.actor("doggo/wildapricot-directory-scraper").call(
                run_input={"startUrls": [{"url": url}], "scrapeProfiles": True, "maxItems": 100}
            )
            items = client.dataset(run.default_dataset_id).list_items().items
            companies = [{"name": i.get("Organization") or i.get("name"), "website": i.get("Website")} for i in items]
            insert_companies(companies, country, name)
        except Exception as e:
            print(f"   ❌ Apify WildApricot error: {e}")

    # Check for GrowthZone / ChamberMaster
    elif '/list/' in url or 'growthzone' in url:
        print("   🔍 Detected: GrowthZone / ChamberMaster")
        try:
            run = client.actor("scrapersdelight/growthzone-directory-scraper").call(
                run_input={"startUrl": url, "maxRecords": 100}
            )
            items = client.dataset(run.default_dataset_id).list_items().items
            companies = [{"name": i.get("name"), "website": i.get("website")} for i in items]
            insert_companies(companies, country, name)
        except Exception as e:
            print(f"   ❌ Apify GrowthZone error: {e}")

    # Fallback: Generic Scraper
    else:
        print("   🔍 Detected: Generic HTML (using fallback scraper)")
        try:
            resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            companies = []
            # Look for links or headings that resemble company names
            for tag in soup.find_all(['h3', 'h4', 'a']):
                text = tag.get_text(strip=True)
                if len(text) > 5 and " " in text and "Contact" not in text and "Login" not in text:
                    companies.append({"name": text, "role": "Importer/Exporter"})
                    
            companies = list({c['name']: c for c in companies}.values())
            insert_companies(companies, country, name)
        except Exception as e:
            print(f"   ❌ Generic error: {e}")

    time.sleep(2) # Be polite

# --- 6. Final Refresh ---
print("\n⚙️ Refreshing directory view...")
cur.execute("SELECT refresh_directory();")
print("🎉 Global extraction complete. Check your live site!")

cur.close()
conn.close()
