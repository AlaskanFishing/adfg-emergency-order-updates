import asyncio
import json
import os
import sys
from datetime import datetime
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Browser, BrowserContext

REGIONS = ["R1", "R2", "R3"]
CURRENT_YEAR = datetime.now().year
IS_DELTA = "--delta" in sys.argv

START_YEAR = CURRENT_YEAR if IS_DELTA else 1998
END_YEAR = CURRENT_YEAR

MAX_WORKERS = 12

DATA_DIR = os.path.join(os.getcwd(), "data")

async def get_pdf_deep_link(context: BrowserContext, semaphore: asyncio.Semaphore, url: str):
    async with semaphore:                
        try:
            page = await context.new_page()
            # Intercept and block unnecessary media/styles to maximize speed 
            await page.route("**/*", lambda route: route.abort() if route.request.resource_type in ["image", "stylesheet", "font", "media"] else route.continue_())
            
            await page.goto(url, timeout=45000, wait_until="domcontentloaded")
            content = await page.content()
            await page.close()
            
            soup = BeautifulSoup(content, 'html.parser')
            pdf_link = ""
            for a in soup.find_all('a'):
                href = a.get('href', '')
                if href.lower().endswith('.pdf') or 'action=eo_pdf' in href.lower():
                    pdf_link = href
                    break
            
            if pdf_link and not pdf_link.startswith("http"):
                 if pdf_link.startswith("/"):
                     pdf_link = f"https://www.adfg.alaska.gov{pdf_link}"
                 else:
                     pdf_link = f"https://www.adfg.alaska.gov/sf/EONR/{pdf_link}"
                     
            return pdf_link
        except Exception as e:
            # Silently catch and return empty PDF if deep dive fails or timeouts
            try:
                await page.close()
            except:
                pass
            return ""

async def scrape_year_region(context: BrowserContext, semaphore: asyncio.Semaphore, region: str, year: int):
    url = f"https://www.adfg.alaska.gov/sf/EONR/index.cfm?ADFG=region.{region}&Year={year}"
    print(f"[*] Crawling: {region} | {year}")
    
    page = await context.new_page()
    await page.goto(url, timeout=60000, wait_until="domcontentloaded")
    html = await page.content()
    await page.close()
    
    soup = BeautifulSoup(html, 'html.parser')
    rows = soup.find_all('tr')
    
    records = []
    deep_tasks = []
    
    for row in rows:
        th = row.find('th')
        if th: continue
        cols = row.find_all('td')
        if len(cols) >= 3:
            date_col = cols[0].get_text(" ", strip=True)
            area_col = cols[1].get_text(" ", strip=True)
            link_tag = cols[2].find('a')
            if not link_tag: continue
            
            title = link_tag.get_text(" ", strip=True)
            link_href = link_tag.get('href', '')
            
            if link_href:
                absolute_url = link_href
                if not absolute_url.startswith("http"):
                    if absolute_url.startswith("/"):
                        absolute_url = f"https://www.adfg.alaska.gov{absolute_url}"
                    else:
                        absolute_url = f"https://www.adfg.alaska.gov/sf/EONR/{absolute_url}"
                        
                record = {
                    "year": year,
                    "date": date_col,
                    "area": area_col,
                    "title": title,
                    "url": absolute_url,
                    "pdf_url": ""
                }
                records.append(record)
                
                task = asyncio.create_task(get_pdf_deep_link(context, semaphore, absolute_url))
                deep_tasks.append((record, task))
    
    # Wait for all 12-worker pool tasks for this year/region to finish
    if deep_tasks:
        sys.stdout.write(f"    Executing {len(deep_tasks)} deep PDF harvests... ")
        sys.stdout.flush()
        for r, t in deep_tasks:
            r['pdf_url'] = await t
        print("Done.")
            
    # Save to data/[Region]/[Year].json
    region_dir = os.path.join(DATA_DIR, region)
    os.makedirs(region_dir, exist_ok=True)
    out_path = os.path.join(region_dir, f"{year}.json")
    
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)
        
async def main():
    print(f"🚀 Initializing Playwright 12-Worker Pipeline")
    print(f"🛠️ Mode: {'DELTA' if IS_DELTA else 'FULL ARCHIVE'}")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        semaphore = asyncio.Semaphore(MAX_WORKERS)
        
        for region in REGIONS:
            print(f"\n======================\n📍 Region {region}\n======================")
            for year in range(END_YEAR, START_YEAR - 1, -1):
                try:
                   await scrape_year_region(context, semaphore, region, year)
                except Exception as e:
                   print(f"❌ Failed to parse {region} {year}: {e}")
        
        await browser.close()
    
    print("\n🎉 Pipeline Execution Complete!")

if __name__ == "__main__":
    asyncio.run(main())
