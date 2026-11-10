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

print("🧹 Deleting garbage data...")
cur.execute(r"DELETE FROM companies_master WHERE name ~ '^[\d\+\-\(\)\s\.]+$';")
cur.execute("DELETE FROM companies_master WHERE name ILIKE '%copyright%' OR name ILIKE '%all rights reserved%';")
cur.execute("DELETE FROM companies_master WHERE length(name) > 70;")
cur.execute("DELETE FROM companies_master WHERE domain ~ '^[0-9]+\.com$';")
cur.execute("SELECT refresh_directory();")
print("✅ Garbage data removed.")
cur.close()
conn.close()
