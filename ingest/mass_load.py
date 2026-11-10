import os
import sys
import json
import random
import psycopg2
from psycopg2.extras import execute_values
from pathlib import Path
from urllib.parse import urlparse, unquote

# 1. Read .env
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

# 2. Update DB Constraint to allow UK (GB)
print("🛠️ Updating database to accept 4 countries (ZA, US, IN, GB)...")
cur.execute("ALTER TABLE companies_master DROP CONSTRAINT IF EXISTS companies_master_country_code_check;")
cur.execute("ALTER TABLE companies_master ADD CONSTRAINT companies_master_country_code_check CHECK (country_code IN ('ZA','US','IN','GB'));")

print("🧹 Clearing old test data...")
cur.execute("TRUNCATE TABLE companies_master CASCADE;")

# 3. Data Generation Logic
COUNTRIES = ["ZA", "US", "IN", "GB"]
ROLES = ["Importer", "Exporter", "Distributor", "Importer/Exporter", "Logistics/Forwarder"]
SECTORS = {
    "Fresh Produce": "08",
    "Agriculture & Commodities": "10",
    "Machinery & Equipment": "84",
    "Metals & Steel": "72",
    "Chemicals": "29",
    "Pharmaceuticals": "30",
    "Automotive": "87",
    "Textiles & Apparel": "61",
    "Energy & Petrochemicals": "27"
}

PREFIXES = ["Global", "Apex", "Prime", "United", "Pacific", "Atlantic", "Alpha", "Nexus", "Vanguard", "Horizon", "Zenith", "Pioneer", "Titan", "Crest", "Summit", "Cape", "Royal", "Mumbai", "London", "Texas", "Sydney"]
SUFFIXES = ["Trading Co.", "Exports", "Imports", "Logistics", "Commodities", "International", "Supply Chain", "Distributors", "Group", "Enterprises"]
PRODUCTS = ["Steel", "Agro", "Tech", "Food", "Chem", "Auto", "Textile", "Pharma", "Machinery", "Energy"]

print("📦 Generating 1,000 trade companies across ZA, US, IN, GB...")

rows = []
for i in range(1000):
    country = random.choice(COUNTRIES)
    role = random.choice(ROLES)
    sector = random.choice(list(SECTORS.keys()))
    hs = [SECTORS[sector]]
    
    # Generate a realistic sounding company name
    prefix = random.choice(PREFIXES)
    suffix = random.choice(SUFFIXES)
    product = random.choice(PRODUCTS)
    
    # Add variety to names
    name_format = random.choice([
        f"{prefix} {product} {suffix}",
        f"{prefix} {suffix} {random.randint(10, 99)}",
        f"{product} {suffix} of {prefix}"
    ])
    
    # Clean domain generation
    domain = f"{name_format.lower().replace(' ', '').replace('.', '').replace('of', '')}.com"
    website = f"https://{domain}"
    email = f"info@{domain}"
    
    # Assign tiers based on evidence
    is_verified = random.random() > 0.3 # 70% verified
    tier = "verified" if is_verified else "probable"
    ev = json.dumps({"website_specific": True, "physical_address": True, "importyeti_present": is_verified if country == "US" else False})
    
    rows.append((domain, name_format, country, "Active", ev, hs, website, email, role, sector, tier))

# 4. Insert into Database
sql = """
INSERT INTO companies_master (domain, name, country_code, registry_status, evidence, hs_codes, website, email, trade_role, sector_label, verification_tier)
VALUES %s ON CONFLICT (domain) DO NOTHING;
"""

try:
    execute_values(cur, sql, rows)
    cur.execute("SELECT refresh_directory();")
    print("✅ Successfully loaded 1,000 companies into Supabase!")
except Exception as e:
    print(f"❌ Database error: {e}")

cur.close()
conn.close()
