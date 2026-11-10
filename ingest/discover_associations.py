import requests
from bs4 import BeautifulSoup
import json
import time
import re

# --- 1. Scrape ITC BSO Directory ---
print("🌐 Scraping ITC BSO Directory...")
itc_urls = []
base_itc = "https://www.itcbenchmarking.org/bso-directory?field_organization_mandate_target_id=All&order=field_country&page={}&search=&sort=desc"

# The ITC directory shows 878 results across multiple pages
# We will scrape the first 5 pages to get a solid sample (approx 50 associations)
for page in range(0, 5):
    try:
        url = base_itc.format(page)
        resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # The table rows contain the association data
        table = soup.find('table')
        if table:
            for row in table.find_all('tr')[1:]: # Skip header
                cols = row.find_all('td')
                if len(cols) >= 5:
                    name = cols[0].get_text(strip=True)
                    country = cols[1].get_text(strip=True)
                    website_tag = cols[4].find('a')
                    website = website_tag['href'] if website_tag else ""
                    
                    if name and website:
                        itc_urls.append({
                            "name": name,
                            "country": country,
                            "url": website,
                            "source": "ITC BSO Directory"
                        })
        time.sleep(1)
    except Exception as e:
        print(f"   ⚠️ ITC page {page} error: {e}")

print(f"✅ Found {len(itc_urls)} associations from ITC.")

# --- 2. Scrape FIEO MoU List ---
print("🇮🇳 Scraping FIEO MoU List...")
fieo_urls = []
try:
    url = "https://fieo.org/en/view_section.php?lang=0&id=0,34,1124"
    resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
    soup = BeautifulSoup(resp.text, 'html.parser')
    
    # Find the table containing the MoU list
    table = soup.find('table')
    if table:
        for row in table.find_all('tr')[1:]:
            cols = row.find_all('td')
            if len(cols) >= 4:
                country = cols[0].get_text(strip=True)
                name = cols[1].get_text(strip=True)
                website_tag = cols[3].find('a') if len(cols) > 3 else None
                website = website_tag['href'] if website_tag else ""
                
                if name and len(name) > 3:
                    # If no website is listed, we leave it blank for now
                    fieo_urls.append({
                        "name": name,
                        "country": country,
                        "url": website,
                        "source": "FIEO MoU List"
                    })
except Exception as e:
    print(f"   ⚠️ FIEO error: {e}")

print(f"✅ Found {len(fieo_urls)} associations from FIEO.")

# --- 3. Combine and Save ---
all_associations = itc_urls + fieo_urls

with open("global_associations.json", "w") as f:
    json.dump(all_associations, f, indent=2)

print(f"\n💾 Saved {len(all_associations)} associations to global_associations.json")
print("You can now run the extraction script (Part 2) to scrape their member directories.")
