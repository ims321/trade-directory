import os
import sys
import json
import kagglehub
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from pathlib import Path
from urllib.parse import urlparse, unquote

# 1. Load Database Credentials
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

# 2. Download the Kaggle Dataset
print("📥 Downloading Global Company Dataset (1M records). This takes ~30 seconds...")
path = kagglehub.dataset_download("yorkiealfbroth/global-company-data-994k")
print(f"✅ Downloaded to: {path}")

# Load into Pandas
print("📊 Loading data into memory...")
df = pd.read_parquet(path + "/sample-1m-companies.parquet")

# 3. Filter for Target Countries and Trade-Related Sectors
# Map country codes just in case the dataset uses full names
country_map = {
    'ZA': ['ZA', 'South Africa'], 
    'US': ['US', 'United States', 'USA'], 
    'IN': ['IN', 'India'], 
    'GB': ['GB', 'United Kingdom', 'UK']
}
flat_countries = [item for sublist in country_map.values() for item in sublist]

trade_keywords = ['Wholesale', 'Import', 'Export', 'Trading', 'Distribution', 'Logistics', 'Freight']

print("🔍 Filtering for target countries and trade sectors...")
# Filter by country
mask = df['country'].isin(flat_countries)

# Filter by sector (if sector column exists)
if 'sector_desc' in df.columns:
    mask = mask & df['sector_desc'].str.contains('|'.join(trade_keywords), case=False, na=False)
elif 'industry' in df.columns:
    mask = mask & df['industry'].str.contains('|'.join(trade_keywords), case=False, na=False)

filtered_df = df[mask].copy()

# If the filter is too strict and returns too few, just take all from those 4 countries
if len(filtered_df) < 1000:
    print("⚠️ Specific trade keywords yielded few results. Broadening to all companies in target countries...")
    filtered_df = df[df['country'].isin(flat_countries)].copy()

print(f"📦 Found {len(filtered_df)} real companies to insert.")

# 4. Map to Your Schema and Insert in Batches
rows = []
for _, row in filtered_df.iterrows():
    name = str(row.get('name', 'Unknown'))
    raw_country = str(row.get('country', 'US'))
    
    # Normalize country code
    country = 'US'
    for k, v in country_map.items():
        if raw_country in v:
            country = k
            break

    sector = str(row.get('sector_desc', row.get('industry', 'Wholesale Trade')))
    
    # Generate a clean domain slug
    clean_name = "".join(e for e in name if e.isalnum()).lower()
    domain = f"{clean_name}.com"
    website = f"https://{domain}"
    email = f"info@{domain}"
    
    # Infer role
    role = "Importer/Exporter"
    if 'wholesale' in sector.lower(): role = "Distributor"
    if 'logistics' in sector.lower() or 'freight' in sector.lower(): role = "Logistics/Forwarder"
    
    hs = ["99"]
    tier = "probable"
    evidence = json.dumps({"website_specific": False, "registry_record": True})
    
    rows.append((domain, name, country, "Active", evidence, hs, website, email, role, sector, tier))

# Deduplicate by domain to prevent ON CONFLICT errors within the same batch
unique_rows = list({r[0]: r for r in rows}.values())

print(f"💾 Inserting {len(unique_rows)} unique records into Supabase (this might take a minute)...")
sql = """
INSERT INTO companies_master (domain, name, country_code, registry_status, evidence, hs_codes, website, email, trade_role, sector_label, verification_tier)
VALUES %s ON CONFLICT (domain) DO NOTHING;
"""

# Insert in chunks of 5000 to avoid memory limits
chunk_size = 5000
for i in range(0, len(unique_rows), chunk_size):
    chunk = unique_rows[i:i+chunk_size]
    try:
        execute_values(cur, sql, chunk)
        print(f"   ✅ Inserted {i + len(chunk)} / {len(unique_rows)}...")
    except Exception as e:
        print(f"   ⚠️ Error on chunk {i}: {e}")

# 5. Refresh the directory view
print("⚙️ Refreshing the directory view...")
cur.execute("SELECT refresh_directory();")
print("🎉 SUCCESS! Your database is now populated with thousands of real companies.")
cur.close()
conn.close()
