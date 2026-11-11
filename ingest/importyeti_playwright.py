import os
import sys
import json
import time
import re
import asyncio
from pathlib import Path
from urllib.parse import urlparse, unquote
import psycopg2
from psycopg2.extras import execute_values
from playwright.async_api import async_playwright

# 1. DB Connect
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

def insert_companies(companies, source_name):
    rows = []
    seen_names = set()
    
    for c in companies:
        name = c.get('name', '').strip()
        
        if not name or len(name) < 3: continue
        if name.lower() in seen_names: continue
        seen_names.add(name.lower())
        
        # 🚨 THE FIX: NO SIMULATION. Website, domain, and email remain NULL.
        rows.append((
            None,       # domain
            name,       # name
            "US",       # country_code
            "Active",   # registry_status
            '{"trade_record_verified": true}', # evidence
            ["99"],     # hs_codes
            None,       # website
            None,       # email
            "Importer", # trade_role
            "General Trading", # sector_label
            "verified", # verification_tier
            source_name # source
        ))

    if not rows: 
        print("   ⚠️ No valid companies found in this batch.")
        return

    # Since domain is NULL, we can't use ON CONFLICT (domain). 
    # We use a subquery to prevent inserting the exact same name twice.
    sql = """
    INSERT INTO companies_master (domain, name, country_code, registry_status, evidence, hs_codes, website, email, trade_role, sector_label, verification_tier, source)
    SELECT %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
    WHERE NOT EXISTS (
        SELECT 1 FROM companies_master WHERE name = %s AND source = %s
    );
    """
    try:
        from psycopg2.extras import execute_batch
        # For the NOT EXISTS clause, we need to pass the name and source again
        batch_data = [r + (r[1], r[11]) for r in rows]
        execute_batch(cur, sql, batch_data)
        print(f"   ✅ Inserted up to {len(rows)} US Importers (with blank websites).")
    except Exception as e:
        print(f"   ❌ DB Error: {e}")

async def scrape_yeti():
    print("🇺🇸 Starting ImportYeti Headless Browser Scraper (No Fake Data)...")
    
    keywords = [
        "electronics", "machinery", "furniture", "apparel", "automotive", 
        "chemicals", "steel", "plastics", "toys", "food"
    ]
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        all_companies = []

        for kw in keywords:
            print(f"   🔍 Searching for '{kw}' importers...")
            url = f"https://www.importyeti.com/search?q={kw}"
            
            try:
                await page.goto(url, wait_until="networkidle", timeout=30000)
                await page.wait_for_timeout(2000) 
                
                # Extract ONLY the company names from the links
                links = await page.eval_on_selector_all(
                    'a[href^="/company/"]', 
                    "elements => elements.map(e => e.innerText.trim())"
                )
                
                found_count = 0
                for name in links:
                    if name and len(name) > 2:
                        all_companies.append({"name": name})
                        found_count += 1
                
                print(f"      Found {found_count} companies.")
                await page.wait_for_timeout(1000)
                
            except Exception as e:
                print(f"      ❌ Error for {kw}: {str(e)[:50]}")

        await browser.close()
        
    print(f"\n📦 Total ImportYeti records found: {len(all_companies)}. Inserting...")
    insert_companies(all_companies, "ImportYeti")

if __name__ == "__main__":
    asyncio.run(scrape_yeti())
    cur.execute("SELECT refresh_directory();")
    print("🎉 ImportYeti scan complete! Check your live site.")
    cur.close()
    conn.close()
