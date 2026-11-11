import os
from pathlib import Path
from urllib.parse import urlparse, unquote
import psycopg2

# Connect to DB
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

print("🚨 Purging GLEIF data...")
cur.execute("DELETE FROM companies_master WHERE source ILIKE '%GLEIF%';")
print(f"   Deleted {cur.rowcount} GLEIF records.")

print("🧹 Purging fake websites from Kompass/Scraped data...")
# 1. Delete if the website is missing entirely
cur.execute("DELETE FROM companies_master WHERE website IS NULL OR website = '';")
print(f"   Deleted {cur.rowcount} records with no website.")

# 2. Delete if the country is ZA/IN/GB but the domain is a generic .com and the email is info@
# (This is a heuristic to catch the generated fake domains)
cur.execute("""
    DELETE FROM companies_master 
    WHERE country_code IN ('ZA', 'IN', 'GB', 'MX', 'VN', 'ID', 'TR', 'BR')
      AND website ILIKE '%.com%'
      AND email ILIKE 'info@%';
""")
print(f"   Deleted {cur.rowcount} records with mismatched country/website (fabricated data).")

# 3. Delete records where the domain looks like a generated slug (e.g., 'autohausimportservice.com')
# This catches domains that are just the company name without spaces.
cur.execute("""
    DELETE FROM companies_master 
    WHERE replace(lower(name), ' ', '') || '.com' = lower(replace(website, 'https://', ''));
""")
print(f"   Deleted {cur.rowcount} records with fabricated domain slugs.")

# Refresh the view
cur.execute("SELECT refresh_directory();")
print("✅ Database cleaned. Refreshing frontend...")

cur.close()
conn.close()
