import os
import sys
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
conn = psycopg2.connect(
    host=parsed.hostname, port=parsed.port or 5432,
    user=unquote(parsed.username), password=unquote(parsed.password),
    dbname=parsed.path.lstrip("/")
)
conn.autocommit = True
cur = conn.cursor()

print("🛠️ Upgrading database schema...")
# Add columns to master table
cur.execute("""
    ALTER TABLE companies_master 
    ADD COLUMN IF NOT EXISTS trade_role TEXT,
    ADD COLUMN IF NOT EXISTS sector_label TEXT;
""")

# Recreate the view to include the new columns
cur.execute("DROP VIEW IF EXISTS public.company_listing;")
cur.execute("""
    CREATE OR REPLACE VIEW public.company_listing
    WITH (security_invoker = true) AS
    SELECT id, name, country_code, website, email, sector_label, trade_role, 
           hs_codes, verification_tier, shell_risk_score, search_vector
    FROM private.company_directory;
""")
# Update the private materialized view as well
cur.execute("DROP MATERIALIZED VIEW IF EXISTS private.company_directory CASCADE;")
cur.execute("""
    CREATE MATERIALIZED VIEW private.company_directory AS
    SELECT id, name, country_code, website, email, sector_label, trade_role,
           hs_codes, verification_tier, shell_risk_score, search_vector
    FROM companies_master
    WHERE suppressed = false;
""")
cur.execute("GRANT SELECT ON public.company_listing TO anon, authenticated, service_role;")
cur.execute("GRANT SELECT ON private.company_directory TO anon, authenticated, service_role;")

print("🧹 Clearing old data...")
cur.execute("TRUNCATE TABLE companies_master CASCADE;")

# Best-Practice Trade Roles & Sectors
TRADERS = [
    # ZA - Fresh Produce Exporters
    {"name": "AFTEX Exporters", "domain": "aftex.co.za", "country": "ZA", "hs": ["08"], "role": "Exporter", "sector": "Fresh Produce", "ev": '{"website_specific": true, "physical_address": true, "association_member": true}'},
    {"name": "Alliance Fruit", "domain": "alliancefruit.co.za", "country": "ZA", "hs": ["08"], "role": "Exporter", "sector": "Fresh Produce", "ev": '{"website_specific": true, "physical_address": true, "association_member": true}'},
    {"name": "Orex Export", "domain": "orexexport.co.za", "country": "ZA", "hs": ["08"], "role": "Exporter", "sector": "Fresh Produce", "ev": '{"website_specific": true, "physical_address": true, "association_member": true}'},
    {"name": "Seaboard International Trading", "domain": "seaboard.co.za", "country": "ZA", "hs": ["08"], "role": "Importer/Exporter", "sector": "Fresh Produce", "ev": '{"website_specific": true, "physical_address": true, "association_member": true}'},
    
    # ZA - Industrial & Logistics
    {"name": "Bidvest Group", "domain": "bidvest.com", "country": "ZA", "hs": ["39", "84"], "role": "Distributor", "sector": "Industrial Goods", "ev": '{"website_specific": true, "physical_address": true}'},
    {"name": "Imperial Logistics", "domain": "imperiallogistics.com", "country": "ZA", "hs": ["87", "39"], "role": "Logistics/Forwarder", "sector": "Logistics & Transport", "ev": '{"website_specific": true, "physical_address": true}'},
    {"name": "Sappi", "domain": "sappi.com", "country": "ZA", "hs": ["48"], "role": "Manufacturer", "sector": "Paper & Packaging", "ev": '{"website_specific": true, "physical_address": true}'},
    {"name": "Aspen Pharmacare", "domain": "aspenpharma.com", "country": "ZA", "hs": ["30"], "role": "Manufacturer", "sector": "Pharmaceuticals", "ev": '{"website_specific": true, "physical_address": true}'},

    # US - Agriculture, Food & Beverage
    {"name": "Cargill", "domain": "cargill.com", "country": "US", "hs": ["10", "12"], "role": "Importer/Exporter", "sector": "Agriculture & Commodities", "ev": '{"website_specific": true, "physical_address": true, "importyeti_present": true}'},
    {"name": "Archer Daniels Midland", "domain": "adm.com", "country": "US", "hs": ["10", "15"], "role": "Importer/Exporter", "sector": "Agriculture & Commodities", "ev": '{"website_specific": true, "physical_address": true, "importyeti_present": true}'},
    {"name": "Royal Coffee", "domain": "royalcoffee.com", "country": "US", "hs": ["09"], "role": "Importer", "sector": "Food & Beverage", "ev": '{"website_specific": true, "physical_address": true, "importyeti_present": true}'},
    {"name": "Vinifera Imports", "domain": "viniferaimports.com", "country": "US", "hs": ["22"], "role": "Importer", "sector": "Food & Beverage", "ev": '{"website_specific": true, "physical_address": true}'},
    
    # US - Machinery & Metals
    {"name": "Caterpillar Inc", "domain": "caterpillar.com", "country": "US", "hs": ["84"], "role": "Manufacturer", "sector": "Machinery & Equipment", "ev": '{"website_specific": true, "physical_address": true, "importyeti_present": true}'},
    {"name": "Pegasus Maritime", "domain": "pegasusmaritime.com", "country": "US", "hs": ["87", "84"], "role": "Logistics/Forwarder", "sector": "Logistics & Transport", "ev": '{"website_specific": true, "physical_address": true}'},
    {"name": "Metalhouse", "domain": "metalhouse.us", "country": "US", "hs": ["72", "73"], "role": "Distributor", "sector": "Metals & Steel", "ev": '{"website_specific": true, "physical_address": true}'},
    {"name": "Accurate Machinery", "domain": "accuratemachinery.com", "country": "US", "hs": ["84", "73"], "role": "Importer", "sector": "Machinery & Equipment", "ev": '{"website_specific": true, "physical_address": true}'},

    # IN - Chemicals & Pharma
    {"name": "Varoon Chemicals", "domain": "varoonchemicals.com", "country": "IN", "hs": ["29"], "role": "Manufacturer", "sector": "Chemicals", "ev": '{"website_specific": true, "physical_address": true, "iec_verified": true, "epc_member": true}'},
    {"name": "Sun Pharma", "domain": "sunpharma.com", "country": "IN", "hs": ["30"], "role": "Manufacturer", "sector": "Pharmaceuticals", "ev": '{"website_specific": true, "physical_address": true, "iec_verified": true}'},
    {"name": "Indus Lifesciences", "domain": "indusgroups.com", "country": "IN", "hs": ["30"], "role": "Manufacturer", "sector": "Pharmaceuticals", "ev": '{"website_specific": true, "physical_address": true, "iec_verified": true, "epc_member": true}'},
    
    # IN - Machinery, Metals & Auto
    {"name": "Simexs Industries", "domain": "simexsindustries.com", "country": "IN", "hs": ["84", "73"], "role": "Manufacturer", "sector": "Machinery & Equipment", "ev": '{"website_specific": true, "physical_address": true, "iec_verified": true, "epc_member": true}'},
    {"name": "Tata Steel", "domain": "tatasteel.com", "country": "IN", "hs": ["72"], "role": "Manufacturer", "sector": "Metals & Steel", "ev": '{"website_specific": true, "physical_address": true, "iec_verified": true}'},
    {"name": "JSW Steel", "domain": "jsw.in", "country": "IN", "hs": ["72"], "role": "Manufacturer", "sector": "Metals & Steel", "ev": '{"website_specific": true, "physical_address": true, "iec_verified": true}'},
    {"name": "Mahindra & Mahindra", "domain": "mahindra.com", "country": "IN", "hs": ["87"], "role": "Manufacturer", "sector": "Automotive", "ev": '{"website_specific": true, "physical_address": true, "iec_verified": true}'},
    {"name": "Bajaj Auto", "domain": "bajajauto.com", "country": "IN", "hs": ["87"], "role": "Manufacturer", "sector": "Automotive", "ev": '{"website_specific": true, "physical_address": true, "iec_verified": true}'},
    {"name": "Pawan Overseas", "domain": "pawanoverseas.com", "country": "IN", "hs": ["84", "87"], "role": "Exporter", "sector": "Automotive", "ev": '{"website_specific": true, "physical_address": true, "iec_verified": true, "epc_member": true}'},
]

print(f"📦 Inserting {len(TRADERS)} enriched trade records...")
rows = []
for c in TRADERS:
    email = f"info@{c['domain']}"
    website = f"https://{c['domain']}"
    rows.append((
        c["domain"], c["name"], c["country"], "Active", 
        c["ev"], c["hs"], website, email, c["role"], c["sector"]
    ))

sql = """
INSERT INTO companies_master 
(domain, name, country_code, registry_status, evidence, hs_codes, website, email, trade_role, sector_label)
VALUES %s
ON CONFLICT (domain) DO UPDATE SET
    name = EXCLUDED.name, trade_role = EXCLUDED.trade_role, sector_label = EXCLUDED.sector_label;
"""
execute_values(cur, sql, rows)

print("⚙️ Rebuilding scoring and views...")
cur.execute("SELECT refresh_directory();")
conn.commit()
print("✅ Database upgraded successfully!")
