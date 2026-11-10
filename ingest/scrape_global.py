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

# --- 2. User Input (Apify Token) ---
print("🔑 (Optional) Paste your Apify API token to use advanced scrapers, or press Enter to skip:")
APIFY_TOKEN = input("> ").strip()
client = ApifyClient(APIFY_TOKEN) if APIFY_TOKEN else None

# --- 3. Target Associations (The global expansion list) ---
# In a real production environment, you would load this from the ITC BSO directory.
# Here is a curated list of real associations with different platforms.
ASSOCIATIONS = [
    # GrowthZone Example (US)
    {"name": "Northern Kentucky Chamber of Commerce", "url": "https://web.nkychamber.com/MemberDirectory", "platform": "growthzone", "country": "US"},
    # Wild Apricot Example (CA)
    {"name": "Toronto Region Board of Trade", "url": "https://www.bot.com/Membership/Directory", "platform": "wildapricot", "country": "CA"},
    # Generic HTML Example (UK) - We will use BeautifulSoup fallback
    {"name": "British International Freight Association (BIFA)", "url": "https://bifa.org/membership/member-search/search-results/", "platform": "generic", "country": "GB"},
    # Generic HTML Example (ZA)
    {"name": "Exporters Eastern Cape", "url": "https://exportersec.co.za/members/", "platform": "generic", "country": "ZA"}
]

# --- 4. Helper: Insert into Database ---
def insert_companies(companies, country, source_name):
    if not companies:
        print(f"   ⚠️ No companies extracted from {source_name}.")
        return
        
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

    # Deduplicate within the batch
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

# --- 5. The Main Scaling Loop ---
print("\n🚀 Starting Global Association Scraping Loop...")

for assoc in ASSOCIATIONS:
    print(f"\n🌍 Processing: {assoc['name']} ({assoc['country']})")
    companies = []

    if assoc['platform'] == 'growthzone' and client:
        # Use Apify GrowthZone Actor
        try:
            run = client.actor("scrapersdelight/growthzone-directory-scraper").call(
                run_input={"startUrl": assoc['url'], "maxRecords": 50}
            )
            items = client.dataset(run.default_dataset_id).list_items().items
            for item in items:
                companies.append({"name": item.get("name"), "website": item.get("website")})
        except Exception as e:
            print(f"   ❌ Apify GrowthZone error: {e}")

    elif assoc['platform'] == 'wildapricot' and client:
        # Use Apify Wild Apricot Actor
        try:
            run = client.actor("doggo/wildapricot-directory-scraper").call(
                run_input={"startUrls": [{"url": assoc['url']}]}
            )
            items = client.dataset(run.default_dataset_id).list_items().items
            for item in items:
                companies.append({"name": item.get("name"), "website": item.get("website")})
        except Exception as e:
            print(f"   ❌ Apify WildApricot error: {e}")

    else:
        # Fallback: Generic BeautifulSoup Scraper
        try:
            resp = requests.get(assoc['url'], headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # Very generic extraction: look for links or headings that might be companies
            for tag in soup.find_all(['h3', 'h4', 'a']):
                text = tag.get_text(strip=True)
                # Filter out navigation links and short text
                if len(text) > 5 and " " in text and "Contact" not in text and "Login" not in text:
                    companies.append({"name": text, "role": "Importer/Exporter"})
                    
            # Deduplicate for this specific scrape
            companies = list({c['name']: c for c in companies}.values())
            
        except Exception as e:
            print(f"   ❌ Generic scraping error: {e}")

    # Insert whatever we found
    insert_companies(companies, assoc['country'], assoc['name'])
    time.sleep(2) # Be polite to servers

print("\n⚙️ Refreshing directory view...")
cur.execute("SELECT refresh_directory();")
print("🎉 Global scraping batch complete. Check your live site!")

cur.close()
conn.close()
