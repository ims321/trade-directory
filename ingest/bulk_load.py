import os
import sys
import psycopg2
from psycopg2.extras import execute_values
from pathlib import Path
from urllib.parse import urlparse, unquote

# 1. Read the .env file manually
env_path = Path('.env')
DB_URL = None
if env_path.exists():
    for line in env_path.read_text().splitlines():
        if line.startswith('DATABASE_URL='):
            DB_URL = line.split('=', 1)[1].strip("'\"")

if not DB_URL:
    print("❌ ERROR: DATABASE_URL is missing in .env")
    sys.exit(1)

# 2. Ensure the protocol is correct
if not DB_URL.startswith("postgresql://") and not DB_URL.startswith("postgres://"):
    DB_URL = "postgresql://" + DB_URL
DB_URL = DB_URL.replace("postgres://", "postgresql://")

# 3. Safely parse the URL
try:
    parsed = urlparse(DB_URL)
    user = unquote(parsed.username) if parsed.username else "postgres"
    password = unquote(parsed.password) if parsed.password else ""
    host = parsed.hostname
    port = parsed.port or 5432
    dbname = parsed.path.lstrip("/") if parsed.path else "postgres"
    
    if not host or not user:
        raise ValueError("Could not extract host or user.")
        
    print(f"🔌 Connecting to host: {host} as {user}...")
    conn = psycopg2.connect(host=host, port=port, user=user, password=password, dbname=dbname)
    cur = conn.cursor()
except Exception as e:
    print(f"❌ Connection failed: {e}")
    print(f"Please check your .env file. Here is a masked version of what we read: {DB_URL[:15]}...{DB_URL[-25:]}")
    sys.exit(1)

SEED_DATA = [
    {"name": "Sasol Ltd", "domain": "sasol.com", "country": "ZA", "status": "In Business", "ev": '{"no_filing_gap": true, "website_specific": true, "physical_address": true}'},
    {"name": "Naspers Ltd", "domain": "naspers.com", "country": "ZA", "status": "In Business", "ev": '{"no_filing_gap": true, "website_specific": true}'},
    {"name": "MTN Group", "domain": "mtn.com", "country": "ZA", "status": "In Business", "ev": '{"no_filing_gap": true, "website_specific": true, "physical_address": true}'},
    {"name": "Shoprite Holdings", "domain": "shoprite.co.za", "country": "ZA", "status": "In Business", "ev": '{"no_filing_gap": true, "website_specific": true}'},
    {"name": "Standard Bank", "domain": "standardbank.com", "country": "ZA", "status": "In Business", "ev": '{"no_filing_gap": true, "website_specific": true, "physical_address": true}'},
    {"name": "Apple Inc", "domain": "apple.com", "country": "US", "status": "Active", "ev": '{"no_filing_gap": true, "website_specific": true, "physical_address": true, "agent_not_mass_formation": true}'},
    {"name": "Microsoft Corp", "domain": "microsoft.com", "country": "US", "status": "Active", "ev": '{"no_filing_gap": true, "website_specific": true, "physical_address": true, "agent_not_mass_formation": true}'},
    {"name": "Amazon.com Inc", "domain": "amazon.com", "country": "US", "status": "Active", "ev": '{"no_filing_gap": true, "website_specific": true, "physical_address": true, "agent_not_mass_formation": true}'},
    {"name": "Tesla Inc", "domain": "tesla.com", "country": "US", "status": "Active", "ev": '{"no_filing_gap": true, "website_specific": true, "physical_address": true, "agent_not_mass_formation": true}'},
    {"name": "Walmart Inc", "domain": "walmart.com", "country": "US", "status": "Active", "ev": '{"no_filing_gap": true, "website_specific": true, "physical_address": true, "agent_not_mass_formation": true}'},
    {"name": "Reliance Industries", "domain": "ril.com", "country": "IN", "status": "Active", "ev": '{"no_filing_gap": true, "website_specific": true, "physical_address": true, "iec_verified": true}'},
    {"name": "Tata Consultancy Services", "domain": "tcs.com", "country": "IN", "status": "Active", "ev": '{"no_filing_gap": true, "website_specific": true, "physical_address": true, "iec_verified": true}'},
    {"name": "Infosys Ltd", "domain": "infosys.com", "country": "IN", "status": "Active", "ev": '{"no_filing_gap": true, "website_specific": true, "physical_address": true, "iec_verified": true}'},
    {"name": "HDFC Bank", "domain": "hdfcbank.com", "country": "IN", "status": "Active", "ev": '{"no_filing_gap": true, "website_specific": true, "physical_address": true, "iec_verified": true}'},
    {"name": "Wipro Ltd", "domain": "wipro.com", "country": "IN", "status": "Active", "ev": '{"no_filing_gap": true, "website_specific": true, "physical_address": true, "iec_verified": true}'},
]

def get_hs_code():
    import random
    return [random.choice(["84", "85", "72", "87", "39", "90", "30", "10", "26", "48"])]

def main():
    print("🚀 Starting Bulk Ingestion...")
    seen = set()
    unique = [c for c in SEED_DATA if not (c["domain"] in seen or seen.add(c["domain"]))]
            
    print(f"✅ Prepared {len(unique)} unique companies for ingestion.")

    rows = [(c["domain"], c["name"], c["country"], c["status"], c["ev"], get_hs_code()) for c in unique]

    sql = """
    INSERT INTO companies_master (domain, name, country_code, registry_status, evidence, hs_codes)
    VALUES %s
    ON CONFLICT (domain) DO UPDATE SET
        name = EXCLUDED.name, country_code = EXCLUDED.country_code, registry_status = EXCLUDED.registry_status,
        evidence = companies_master.evidence || EXCLUDED.evidence,
        hs_codes = CASE WHEN companies_master.hs_codes = '{}' THEN EXCLUDED.hs_codes ELSE companies_master.hs_codes END,
        updated_at = now();
    """
    
    try:
        execute_values(cur, sql, rows)
        conn.commit()
        print(f"✅ Successfully inserted {len(rows)} companies into the database.")
    except Exception as e:
        print(f"❌ Database insert failed: {e}")
        conn.rollback()
        sys.exit(1)

    try:
        cur.execute("SELECT refresh_directory();")
        conn.commit()
        print("✅ Scoring engine executed and directory view refreshed.")
    except Exception as e: print(f"⚠️ View refresh failed: {e}")
    
    cur.close()
    conn.close()
    print("🎉 Ingestion complete. Your frontend is now live with data.")

if __name__ == "__main__":
    main()
