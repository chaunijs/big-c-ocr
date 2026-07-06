import asyncio
import io
import re
import requests
import urllib3
import numpy as np
import datetime
from PIL import Image
from bs4 import BeautifulSoup
import easyocr
import polars as pl
from patchright.async_api import async_playwright

# Suppress the insecure request warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

print("🔄 Initializing EasyOCR Engine (This may take a moment to download models on first run)...")
# Force CPU execution
reader = easyocr.Reader(['en', 'th'], gpu=False)

def get_condition_from_text(raw_text):
    """Maps raw OCR text to standardized promotional conditions."""
    if not raw_text:
        return None
        
    t = raw_text.upper().replace(" ", "")
    t = t.replace("BUV", "BUY")
    digits = re.findall(r'\d', t)
    n = digits[0] if digits else ""

    if any(k in t for k in ["SUPERSAVE", "SAVE", "ประหยัด"]):
        return "Supersave"
    if any(k in t for k in ["GET", "แถม"]):
        if n:
            if n == "1" or "1แถม1" in t or "1GET1" in t:
                return "Buy 1 Get 1"
            return f"Buy {n} Get 1"
        return "Buy 1 Get"
    if "CHEAPER" in t:
        if n:
            return f"Buy {n} Cheaper"
        return "Buy 2 Cheaper"
    
    return raw_text.strip() if raw_text.strip() else None

async def test_multiple_urls_ocr(url_list):
    scraped_data = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, 
            args=["--disable-blink-features=AutomationControlled"]
        )
        
        for url in url_list:
            print(f"\n🚀 Starting test for URL: {url}")
            badge_url = None
            product_name = "Unknown"
            extracted_text = None

            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080}
            )
            
            await context.add_cookies([
                {'name': 'language', 'value': 'en', 'domain': '.bigc.co.th', 'path': '/'},
                {'name': 'NEXT_LOCALE', 'value': 'en', 'domain': '.bigc.co.th', 'path': '/'}
            ])

            page = await context.new_page()
            
            try:
                print("🌐 Loading webpage...")
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(3) 
                
                html_content = await page.content()
                soup = BeautifulSoup(html_content, "html.parser")
                
                name_elem = soup.find("h1")
                product_name = name_elem.text.strip() if name_elem else "Unknown"
                print(f"📦 Product Name: {product_name}")

                badge_div = soup.find("div", class_=lambda x: x and "imageSlider_badge_warpper" in x)
                if badge_div:
                    badge_img = badge_div.find("img")
                    if badge_img and badge_img.has_attr('src'):
                        badge_url = badge_img['src']
                        print(f"🔗 Found Badge URL: {badge_url}")
                else:
                    print("⚠️ No badge found on this product page.")

            except Exception as e:
                print(f"❌ Error scraping page: {e}")
            finally:
                await context.close()

            if badge_url and badge_url != "null":
                print("🔍 Downloading and processing image...")
                try:
                    headers = {"User-Agent": "Mozilla/5.0"}
                    response = requests.get(badge_url, headers=headers, timeout=10, verify=False)
                    
                    if response.status_code == 200:
                        img = Image.open(io.BytesIO(response.content))
                        
                        if img.mode in ("RGBA", "P"):
                            img = img.convert("RGBA")
                            background = Image.new("RGB", img.size, (255, 255, 255))
                            background.paste(img, mask=img.split()[3]) 
                            img = background
                        else:
                            img = img.convert("RGB")

                        img = img.resize((img.width * 4, img.height * 4), resample=Image.LANCZOS)
                        
                        img_array = np.array(img)
                        
                        print("🧠 Running EasyOCR...")
                        results = reader.readtext(img_array)
                        extracted_text = " ".join([res[1] for res in results])
                        
                        print("-" * 40)
                        print(f"📄 RAW TEXT EXTRACTED : '{extracted_text.strip()}'")
                        
                        label = get_condition_from_text(extracted_text)
                        print(f"✨ MAPPED CONDITION   : {label}")
                        print("-" * 40)
                    else:
                        print(f"❌ Failed to download image. Status code: {response.status_code}")
                except Exception as e:
                    print(f"❌ Error processing image: {e}")

            # Append the iteration's result to our data list
            scraped_data.append({
                "product_name": product_name,
                "url": url,
                "text_extract": extracted_text
            })

        await browser.close()

    # --- Data Export ---
    if scraped_data:
        df = pl.DataFrame(scraped_data)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save as CSV
        csv_filename = f"ocr_results_{timestamp}.csv"
        df.write_csv(csv_filename)
        print(f"\n✅ Saved results to {csv_filename}")
        
        # Save as Excel 
        try:
            excel_filename = f"ocr_results_{timestamp}.xlsx"
            df.write_excel(excel_filename)
            print(f"✅ Saved results to {excel_filename}")
        except ImportError:
            print("💡 Note: Install a writer like 'xlsxwriter' to enable Excel export. CSV was generated successfully.")
    else:
        print("\n⚠️ No data was scraped to save.")

if __name__ == "__main__":
    test_urls = [
        "https://www.bigc.co.th/en/product/fineline-fabric-softener-sunshine-gold-1-300-ml.11818189",
        "https://www.bigc.co.th/en/product/hygiene-fabric-softener-expert-care-tender-touch-480-ml-pack-2-free-1.32428"
    ]
    asyncio.run(test_multiple_urls_ocr(test_urls))