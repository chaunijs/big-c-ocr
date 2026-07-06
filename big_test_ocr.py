import asyncio
import io
import re
import requests
import urllib3
import numpy as np
from PIL import Image
from bs4 import BeautifulSoup
import easyocr
from patchright.async_api import async_playwright

# Suppress the insecure request warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

print("🔄 Initializing EasyOCR Engine (This may take a moment to download models on first run)...")
# FIX: Added gpu=False to force CPU execution
reader = easyocr.Reader(['en', 'th'], gpu=False)

def get_condition_from_text(raw_text):
    """Maps raw OCR text to standardized promotional conditions."""
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
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, 
            args=["--disable-blink-features=AutomationControlled"]
        )
        
        for url in url_list:
            print(f"\n🚀 Starting test for URL: {url}")
            badge_url = None

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
                print(f"📦 Product Name: {name_elem.text.strip() if name_elem else 'Unknown'}")

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
                        
                        # Convert PIL Image to Numpy Array for EasyOCR
                        img_array = np.array(img)
                        
                        print("🧠 Running EasyOCR...")
                        results = reader.readtext(img_array)
                        raw_text = " ".join([res[1] for res in results])
                        
                        print("-" * 40)
                        print(f"📄 RAW TEXT EXTRACTED : '{raw_text.strip()}'")
                        
                        label = get_condition_from_text(raw_text)
                        print(f"✨ MAPPED CONDITION   : {label}")
                        print("-" * 40)
                    else:
                        print(f"❌ Failed to download image. Status code: {response.status_code}")
                except Exception as e:
                    print(f"❌ Error processing image: {e}")

        await browser.close()

if __name__ == "__main__":
    test_urls = [
        "https://www.bigc.co.th/en/product/fineline-fabric-softener-sunshine-gold-1-300-ml.11818189",
        "https://www.bigc.co.th/en/product/hygiene-fabric-softener-expert-care-tender-touch-480-ml-pack-2-free-1.32428"
    ]
    asyncio.run(test_multiple_urls_ocr(test_urls))