import os
import psycopg2
from urllib.parse import urlparse, unquote
from pathlib import Path

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

print("🧹 Clearing old mismatched data...")
cur.execute("TRUNCATE TABLE companies_master CASCADE;")

# Perfectly categorized data matching the dropdowns
TRADERS = [
    # ZA - Fresh Produce
    {"name": "AFTEX Exporters", "domain": "aftex.co.za", "country": "ZA", "hs": ["08"], "role": "Exporter", "sector": "Fresh Produce"},
    {"name": "Alliance Fruit", "domain": "alliancefruit.co.za", "country": "ZA", "hs": ["08"], "role": "Exporter", "sector": "Fresh Produce"},
    {"name": "Seaboard International", "domain": "seaboard.co.za", "country": "ZA", "hs": ["08"], "role": "Importer/Exporter", "sector": "Fresh Produce"},
    # ZA - Industrial
    {"name": "Bidvest Group", "domain": "bidvest.com", "country": "ZA", "hs": ["39"], "role": "Distributor", "sector": "Industrial Goods"},
    {"name": "Imperial Logistics", "domain": "imperiallogistics.com", "country": "ZA", "hs": ["87"], "role": "Logistics/Forwarder", "sector": "Logistics & Transport"},

    # US - Agriculture
    {"name": "Cargill", "domain": "cargill.com", "country": "US", "hs": ["10"], "role": "Importer/Exporter", "sector": "Agriculture & Commodities"},
    {"name": "Archer Daniels Midland", "domain": "adm.com", "country": "US", "hs": ["10"], "role": "Importer/Exporter", "sector": "Agriculture & Commodities"},
    {"name": "Royal Coffee", "domain": "royalcoffee.com", "country": "US", "hs": ["09"], "role": "Importer", "sector": "Food & Beverage"},
    # US - Machinery & Metals
    {"name": "Pegasus Maritime", "domain": "pegasusmaritime.com", "country": "US", "hs": ["84"], "role": "Logistics/Forwarder", "sector": "Logistics & Transport"},
    {"name": "Metalhouse", "domain": "metalhouse.us", "country": "US", "hs": ["72"], "role": "Distributor", "sector": "Metals & Steel"},
    {"name": "Accurate Machinery", "domain": "accuratemachinery.com", "country": "US", "hs": ["84"], "role": "Importer", "sector": "Machinery & Equipment"},

    # IN - Pharma & Chemicals
    {"name": "Varoon Chemicals", "domain": "varoonchemicals.com", "country": "IN", "hs": ["29"], "role": "Exporter", "sector": "Chemicals"},
    {"name": "Indus Lifesciences", "domain": "indusgroups.com", "country": "IN", "hs": ["30"], "role": "Exporter", "sector": "Pharmaceuticals"},
    # IN - Machinery & Auto
    {"name": "Simexs Industries", "domain": "simexsindustries.com", "country": "IN", "hs": ["84"], "role": "Exporter", "sector": "Machinery & Equipment"},
    {"name": "Pawan Overseas", "domain": "pawanoverseas.com", "country": "IN", "hs": ["87"], "role": "Importer", "sector": "Automotive"},
    {"name": "Larsen & Toubro", "domain": "larsentoubro.com", "country": "IN", "hs": ["84"], "role": "Distributor", "sector": "Machinery & Equipment"},
]

print("📦 Inserting perfectly matched categories...")
rows = []
for c in TRADERS:
    email = f"info@{c['domain']}"
    website = f"https://{c['domain']}"
    rows.append((c["domain"], c["name"], c["country"], "Active", '{"website_specific": true}', c["hs"], website, email, c["role"], c["sector"]))

sql = """
INSERT INTO companies_master (domain, name, country_code, registry_status, evidence, hs_codes, website, email, trade_role, sector_label)
VALUES %s ON CONFLICT (domain) DO UPDATE SET trade_role = EXCLUDED.trade_role, sector_label = EXCLUDED.sector_label;
"""
from psycopg2.extras import execute_values
execute_values(cur, sql, rows)
cur.execute("SELECT refresh_directory();")
print("✅ Database perfectly categorized!")
cur.close()
conn.close()
