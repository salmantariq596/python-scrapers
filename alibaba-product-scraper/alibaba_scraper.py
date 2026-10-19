# Complete Alibaba Product Scraper - Fixed Version with USD Currency Support & Product Classification
# Issues fixed: Image extraction, error handling for missing selectors, price variants support, USD currency
# NEW: Added product_type, gender, audience, use_case classification

import asyncio
import random
import json
import re
import os
import time
from datetime import datetime
from typing import List, Dict, Any, Optional
from playwright.async_api import async_playwright, Page, BrowserContext

# ============= CONFIGURATION =============
SCRAPED_URLS_FILE = "ali_baba_8/scraped_urls.json"
FAILED_URLS_FILE = "ali_baba_8/failed_urls.json"
PROGRESS_FILE = "ali_baba_8/scraping_progress.json"
RESULTS_FILE = "ali_baba_8/alibaba_products.json"
COOKIES_FILE = "ali_baba_8/alibaba_cookies.json"

def load_json_file(file_path: str, default=None):
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return default if default is not None else {}
    return default if default is not None else {}

def save_json_file(file_path: str, data):
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_scraped_urls() -> set:
    data = load_json_file(SCRAPED_URLS_FILE, [])
    return set(data)

def save_scraped_url(url: str):
    urls = load_scraped_urls()
    urls.add(url)
    save_json_file(SCRAPED_URLS_FILE, list(urls))

def load_failed_urls() -> set:
    data = load_json_file(FAILED_URLS_FILE, [])
    return set(data)

def save_failed_url(url: str, reason: str = ""):
    failed = load_failed_urls()
    failed.add(url)
    save_json_file(FAILED_URLS_FILE, list(failed))
    with open("failed_log.txt", "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat()} | {url} | {reason}\n")

def load_existing_results() -> List[Dict]:
    if os.path.exists(RESULTS_FILE):
        return load_json_file(RESULTS_FILE, [])
    return []

def save_result_append(product: Dict):
    results = load_existing_results()
    results.append(product)
    save_json_file(RESULTS_FILE, results)

def save_progress(current_index: int, total: int):
    progress = {"current_index": current_index, "total": total, "last_updated": datetime.now().isoformat()}
    save_json_file(PROGRESS_FILE, progress)

def load_progress():
    return load_json_file(PROGRESS_FILE, {})

async def save_cookies(context: BrowserContext):
    cookies = await context.cookies()
    save_json_file(COOKIES_FILE, cookies)
    print(f"✅ Cookies saved")

async def load_cookies(context: BrowserContext) -> bool:
    if os.path.exists(COOKIES_FILE):
        cookies = load_json_file(COOKIES_FILE, [])
        if cookies:
            await context.add_cookies(cookies)
            print(f"✅ Cookies loaded")
            return True
    return False


class CompleteAlibabaScraper:
    def __init__(self, headless: bool = False, max_retries: int = 3, currency: str = "USD"):
        self.headless = headless
        self.max_retries = max_retries
        self.currency = currency  # Currency preference (USD, EUR, GBP, etc.)
        self.scraped_urls = load_scraped_urls()
        self.failed_urls = load_failed_urls()
        self.existing_results = load_existing_results()
        self.stats = {'successful': 0, 'failed': 0}
        self.start_time = None
        self.captcha_solved = False
        self.browser = None
        self.context = None
        self.page = None
        
        # ========== PRODUCT CLASSIFICATION MAPPINGS ==========
        self.GENDER_VALUES = ["Men", "Women", "Unisex", "Kids", "Baby", "Pet", "N/A"]
        self.AUDIENCE_VALUES = ["Adult", "Kids", "Baby", "Pet", "Business", "Industrial"]
        self.USE_CASES = ["Everyday", "Fitness", "Travel", "Work", "Home", "Industrial"]
        
        self.GENDER_KEYWORDS = {
            "Men": ["men", "male", "man", "gentleman", "boys", "mens", "for men"],
            "Women": ["women", "female", "woman", "ladies", "girls", "womens", "for women", "feminine"],
            "Unisex": ["unisex", "unisex adult", "adult unisex", "both men and women"],
            "Kids": ["kids", "children", "child", "young", "toddler", "boys and girls", "kid"],
            "Baby": ["baby", "infant", "newborn", "toddler", "babies"],
            "Pet": ["pet", "dog", "cat", "animal", "puppy", "kitten", "pets"]
        }
        
        self.AUDIENCE_KEYWORDS = {
            "Adult": ["adult", "grown-up", "mature", "adults"],
            "Kids": ["kids", "children", "child", "young", "toddler"],
            "Baby": ["baby", "infant", "newborn", "babies"],
            "Pet": ["pet", "dog", "cat", "animal", "pets"],
            "Business": ["business", "commercial", "office", "corporate", "enterprise", "bulk", "wholesale"],
            "Industrial": ["industrial", "factory", "manufacturing", "heavy duty", "industrial grade"]
        }
        
        self.USE_CASE_KEYWORDS = {
            "Everyday": ["everyday", "daily", "regular", "casual", "day to day", "all day"],
            "Fitness": ["fitness", "sport", "gym", "workout", "exercise", "athletic", "training", "sports"],
            "Travel": ["travel", "trip", "vacation", "journey", "luggage", "portable", "on the go"],
            "Work": ["work", "professional", "office", "business", "corporate", "workplace"],
            "Home": ["home", "household", "residential", "indoor", "kitchen", "living room"],
            "Industrial": ["industrial", "heavy duty", "commercial", "factory", "warehouse", "construction"]
        }
        
        self.PRODUCT_TYPE_KEYWORDS = {
            "Electronics": ["laptop", "computer", "phone", "tablet", "electronic", "gadget", "device", "charger", "cable", "battery"],
            "Clothing": ["shirt", "pant", "dress", "jacket", "coat", "sweater", "hoodie", "jeans", "trousers", "skirt", "blouse", "t-shirt"],
            "Footwear": ["shoe", "boot", "sandal", "sneaker", "footwear", "loafer", "heel"],
            "Accessories": ["bag", "watch", "jewelry", "hat", "scarf", "belt", "wallet", "sunglasses", "glasses"],
            "Home & Garden": ["furniture", "decor", "lighting", "bedding", "towel", "rug", "curtain", "garden", "plant"],
            "Sports & Outdoors": ["sport", "outdoor", "camping", "hiking", "fitness", "exercise", "yoga", "bike", "cycling"],
            "Beauty & Personal Care": ["beauty", "cosmetic", "skin care", "hair", "makeup", "perfume", "lotion"],
            "Toys & Hobbies": ["toy", "game", "puzzle", "doll", "action figure", "board game", "hobby"],
            "Baby Products": ["baby", "infant", "stroller", "crib", "diaper", "baby care", "nursery"],
            "Pet Supplies": ["pet", "dog", "cat", "pet food", "pet toy", "pet bed", "leash", "collar"],
            "Industrial Equipment": ["industrial", "machine", "equipment", "tool", "manufacturing", "heavy duty"],
            "Office Supplies": ["office", "desk", "chair", "stationery", "printer", "paper"],
            "Food & Beverage": ["food", "beverage", "drink", "snack", "ingredient", "cooking"],
            "Health & Medical": ["health", "medical", "wellness", "supplement", "vitamin", "healthcare"],
        }
    
    async def init_browser(self):
        playwright = await async_playwright().start()
        
        self.browser = await playwright.chromium.launch(
            headless=self.headless,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
            ]
        )
        
        self.context = await self.browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            locale='en-US'
        )
        
        await load_cookies(self.context)
        
        # Set currency cookies before creating page
        await self.set_currency_cookies()
        
        self.page = await self.context.new_page()
        
        return playwright
    
    async def set_currency_cookies(self):
        """Add cookies to set preferred currency (USD by default)"""
        try:
            cookies_to_add = [
                {
                    "name": "aep_usuc_f",
                    "value": f"site=glo&c_tp={self.currency}&x_al={self.currency}",
                    "domain": ".alibaba.com",
                    "path": "/"
                },
                {
                    "name": "currency",
                    "value": self.currency,
                    "domain": ".alibaba.com",
                    "path": "/"
                },
                {
                    "name": "cur",
                    "value": self.currency,
                    "domain": ".alibaba.com",
                    "path": "/"
                }
            ]
            await self.context.add_cookies(cookies_to_add)
            print(f"   ✅ Currency cookies set to {self.currency}")
            return True
        except Exception as e:
            print(f"   ⚠️ Could not set currency cookies: {e}")
            return False
    
    async def set_currency_via_selector(self, page: Page):
        """Click currency selector and choose preferred currency"""
        try:
            print(f"   🌍 Setting currency to {self.currency} via selector...")
            
            # Wait a bit for page to stabilize
            await page.wait_for_timeout(2000)
            
            # Try multiple selectors for currency button
            currency_selectors = [
                '[data-testid="currency-selector"]',
                '.currency-selector',
                '.header-currency',
                'button:has-text("Currency")',
                '.currency-switcher',
                '[aria-label="Currency selector"]',
                'div:has-text("Currency")'
            ]
            
            currency_btn = None
            for selector in currency_selectors:
                try:
                    currency_btn = await page.query_selector(selector)
                    if currency_btn:
                        print(f"      Found currency selector: {selector}")
                        break
                except:
                    continue
            
            if currency_btn:
                # Click to open dropdown
                await currency_btn.click()
                await page.wait_for_timeout(1000)
                
                # Look for target currency option
                usd_selectors = [
                    f'button:has-text("{self.currency}")',
                    f'a:has-text("{self.currency}")',
                    f'li:has-text("{self.currency}")',
                    f'[value="{self.currency}"]',
                    f'div:has-text("{self.currency}")',
                    f'span:has-text("{self.currency}")'
                ]
                
                currency_option = None
                for selector in usd_selectors:
                    try:
                        currency_option = await page.query_selector(selector)
                        if currency_option:
                            print(f"      Found {self.currency} option: {selector}")
                            break
                    except:
                        continue
                
                if currency_option:
                    await currency_option.click()
                    print(f"      ✅ Currency set to {self.currency}")
                    await page.wait_for_timeout(3000)  # Wait for page to refresh
                    return True
                else:
                    print(f"      ⚠️ {self.currency} option not found")
                    return False
            else:
                print(f"      ⚠️ Currency selector not found")
                return False
                
        except Exception as e:
            print(f"      Error setting currency via selector: {e}")
            return False
    
    def add_currency_to_url(self, url: str) -> str:
        """Add currency parameter to URL"""
        if '?' in url:
            return url + f'&currency={self.currency}'
        else:
            return url + f'?currency={self.currency}'
    
    async def check_and_handle_captcha(self) -> bool:
        if self.captcha_solved:
            return True
        
        captcha_selectors = ['.captcha-container', '.nc_wrapper', '#captcha', '.geetest_panel', 
                            'iframe[src*="captcha"]', 'iframe[src*="verify"]']
        
        for selector in captcha_selectors:
            if await self.page.query_selector(selector):
                print("\n" + "🔐"*20)
                print("⚠️  CAPTCHA DETECTED!")
                print("🔐"*20)
                print("\n📌 Please solve CAPTCHA manually in the browser window.")
                print("⏳ You have 60 seconds...\n")
                
                start = time.time()
                while time.time() - start < 60:
                    captcha_still_there = False
                    for selector in captcha_selectors:
                        if await self.page.query_selector(selector):
                            captcha_still_there = True
                            break
                    
                    if not captcha_still_there:
                        print("\n✅ CAPTCHA SOLVED! Continuing...\n")
                        self.captcha_solved = True
                        await save_cookies(self.context)
                        await asyncio.sleep(2)
                        return True
                    
                    remaining = int(60 - (time.time() - start))
                    if remaining % 10 == 0 and remaining > 0:
                        print(f"⏳ Waiting... {remaining} seconds remaining")
                    await asyncio.sleep(2)
                
                print("\n❌ CAPTCHA timeout!")
                return False
        
        self.captcha_solved = True
        return True
    
    async def scrape_all_urls(self, urls: List[str], resume: bool = True) -> List[Dict]:
        print("\n" + "="*70)
        print("🚀 ALIBABA COMPLETE SCRAPER - ALL FIELDS INCLUDED")
        print(f"💰 Currency: {self.currency}")
        print("="*70)
        
        # Add currency parameter to all URLs
        urls_with_currency = [self.add_currency_to_url(url) for url in urls]
        
        # Filter URLs
        urls_to_scrape = []
        for url in urls_with_currency:
            # Check original URL (without currency) for tracking
            original_url = url.split('?')[0] if '?' in url else url
            if original_url in self.scraped_urls:
                continue
            if original_url in self.failed_urls:
                continue
            urls_to_scrape.append(url)
        
        if resume:
            progress = load_progress()
            if progress and progress.get('current_index', 0) > 0:
                start_index = progress.get('current_index', 0)
                urls_to_scrape = urls_to_scrape[start_index:]
                print(f"\n🔄 Resuming from index {start_index}")
        
        total = len(urls_to_scrape)
        print(f"\n📊 Statistics:")
        print(f"  Total URLs: {len(urls)}")
        print(f"  Already scraped: {len([u for u in urls if u in self.scraped_urls])}")
        print(f"  Previously failed: {len([u for u in urls if u in self.failed_urls])}")
        print(f"  New to scrape: {total}")
        
        if total == 0:
            print("\n✅ All URLs already processed!")
            return self.existing_results
        
        self.start_time = time.time()
        all_results = self.existing_results.copy()
        
        playwright = await self.init_browser()
        
        try:
            print("\n🔍 Checking for CAPTCHA...")
            await self.page.goto("https://www.alibaba.com", timeout=50000, wait_until='domcontentloaded')
            await asyncio.sleep(3)
            
            # Try to set currency via selector on homepage
            await self.set_currency_via_selector(self.page)
            
            if not await self.check_and_handle_captcha():
                print("\n❌ Cannot proceed!")
                return all_results
            
            print("\n" + "="*50)
            print("🚀 Starting product scraping...")
            print("="*50)
            
            for idx, url in enumerate(urls_to_scrape, 1):
                product_start_time = time.time()
                print(f"\n[{idx}/{total}] Processing: {url[:70]}...")
                
                page = await self.context.new_page()
                
                try:
                    success = False
                    for attempt in range(self.max_retries):
                        try:
                            if attempt > 0:
                                print(f"    🔄 Retry {attempt + 1}/{self.max_retries}...")
                                await asyncio.sleep(random.uniform(3, 5))
                            
                            await page.goto(url, timeout=60000, wait_until='domcontentloaded')
                            await asyncio.sleep(random.uniform(3, 5))
                            
                            # Try to set currency on product page if not already set
                            if attempt == 0:  # Only try on first attempt
                                await self.set_currency_via_selector(page)
                            
                            # Extract COMPLETE product data
                            data = await self.extract_complete_product(page, url)
                            
                            if data and data.get('title'):
                                # Add classification fields
                                classification = await self.classify_product(data, page)
                                data.update(classification)
                                
                                time_taken = time.time() - product_start_time
                                all_results.append(data)
                                save_result_append(data)
                                # Save original URL (without currency) for tracking
                                original_url = url.split('?')[0] if '?' in url else url
                                save_scraped_url(original_url)
                                
                                self.stats['successful'] += 1
                                print(f"    ✅ SUCCESS!")
                                print(f"       Title: {data['title'][:50]}...")
                                print(f"       Price: {data.get('price', 'N/A')} {data.get('currency', '')}")
                                print(f"       Product Type: {data.get('product_type', 'N/A')}")
                                print(f"       Gender: {data.get('gender', 'N/A')}")
                                print(f"       Audience: {data.get('audience', 'N/A')}")
                                print(f"       Use Cases: {', '.join(data.get('use_cases', []))}")
                                print(f"       Images: {len(data.get('image_urls', []))}")
                                print(f"       Variants: {len(data.get('variants', []))}")
                                print(f"       Specs: {len(data.get('specifications', {}))}")
                                print(f"       Time: {time_taken:.1f}s")
                                
                                elapsed = time.time() - self.start_time
                                rate = self.stats['successful'] / elapsed if elapsed > 0 else 0
                                remaining = (total - idx) / rate if rate > 0 else 0
                                print(f"    📈 Progress: {self.stats['successful']}/{total} | ⚡ {rate:.2f} prod/sec | ETA: {remaining/60:.1f} min")
                                
                                success = True
                                break
                            else:
                                raise Exception("No data extracted")
                                
                        except Exception as e:
                            print(f"    ❌ Attempt {attempt + 1} failed: {str(e)[:100]}")
                            if attempt == self.max_retries - 1:
                                self.stats['failed'] += 1
                                original_url = url.split('?')[0] if '?' in url else url
                                save_failed_url(original_url, str(e))
                    
                    if not success:
                        print(f"    ❌ FAILED after {self.max_retries} attempts")
                    
                    save_progress(idx, total)
                    
                    if idx % 5 == 0:
                        save_json_file(RESULTS_FILE, all_results)
                    
                finally:
                    await page.close()
                
                await asyncio.sleep(random.uniform(2, 4))
            
        finally:
            await self.browser.close()
            await playwright.stop()
        
        save_json_file(RESULTS_FILE, all_results)
        self.print_summary()
        
        return all_results
    
    # ========== PRODUCT CLASSIFICATION METHODS ==========
    
    def classify_product_type(self, title: str, description: str, specifications: Dict) -> str:
        """Classify product type based on title, description, and specifications"""
        text = f"{title} {description}".lower()
        
        # Also check specifications values
        for key, value in specifications.items():
            text += f" {key} {value}".lower()
        
        scores = {}
        for product_type, keywords in self.PRODUCT_TYPE_KEYWORDS.items():
            score = 0
            for keyword in keywords:
                if keyword.lower() in text:
                    score += 1
            if score > 0:
                scores[product_type] = score
        
        if scores:
            return max(scores, key=scores.get)
        return "General"
    
    def classify_gender(self, title: str, description: str, category: str, variants: List) -> str:
        """Classify gender based on product information"""
        text = f"{title} {description} {category}".lower()
        
        # Check variants for gender indicators
        for variant in variants:
            if variant.get('value'):
                text += f" {variant['value'].lower()}"
        
        scores = {gender: 0 for gender in self.GENDER_VALUES if gender != "N/A"}
        
        for gender, keywords in self.GENDER_KEYWORDS.items():
            for keyword in keywords:
                if keyword.lower() in text:
                    scores[gender] += 1
        
        # Check for specific patterns
        if "for men and women" in text or "men & women" in text:
            scores["Unisex"] += 3
        
        # Get highest score
        max_score = max(scores.values()) if scores else 0
        if max_score > 0:
            top_genders = [g for g, s in scores.items() if s == max_score]
            if len(top_genders) > 1:
                return "Unisex"
            return top_genders[0]
        
        return "N/A"
    
    def classify_audience(self, title: str, description: str, gender: str, price_info: Dict) -> str:
        """Classify target audience"""
        text = f"{title} {description}".lower()
        
        scores = {audience: 0 for audience in self.AUDIENCE_VALUES}
        
        # Check keywords
        for audience, keywords in self.AUDIENCE_KEYWORDS.items():
            for keyword in keywords:
                if keyword.lower() in text:
                    scores[audience] += 2
        
        # Check price indicators
        if price_info.get('min_price'):
            min_price = price_info['min_price']
            if min_price > 500:
                scores["Business"] += 2
            if min_price > 1000:
                scores["Industrial"] += 2
        
        # Check for quantity indicators (bulk/wholesale)
        if any(term in text for term in ["bulk", "wholesale", "case pack", "carton"]):
            scores["Business"] += 3
        
        # Use gender to inform audience
        if gender in ["Kids", "Baby"]:
            if gender == "Kids":
                scores["Kids"] += 5
            else:
                scores["Baby"] += 5
        
        # Get highest score
        max_score = max(scores.values())
        if max_score > 0:
            top_audiences = [a for a, s in scores.items() if s == max_score]
            return top_audiences[0]
        
        return "Adult"  # Default
    
    def classify_use_case(self, title: str, description: str, specifications: Dict, category: str) -> List[str]:
        """Classify use cases (can be multiple)"""
        text = f"{title} {description} {category}".lower()
        
        # Add specifications to text
        for key, value in specifications.items():
            text += f" {key} {value}".lower()
        
        use_cases = []
        
        for use_case, keywords in self.USE_CASE_KEYWORDS.items():
            for keyword in keywords:
                if keyword.lower() in text:
                    if use_case not in use_cases:
                        use_cases.append(use_case)
                    break  # Found a match for this use case
        
        # If no use cases found, try to infer from title
        if not use_cases:
            if any(term in text for term in ["home", "household", "indoor"]):
                use_cases.append("Home")
            elif any(term in text for term in ["work", "office", "business"]):
                use_cases.append("Work")
            else:
                use_cases.append("Everyday")
        
        return use_cases[:3]  # Max 3 use cases
    
    async def detect_gender_from_selectors(self, page: Page) -> Optional[str]:
        """Try to detect gender from page selectors"""
        try:
            # Look for gender-specific text in filters or attributes
            gender_selectors = [
                '.gender-selector',
                '[data-gender]',
                '.product-tags .tag'
            ]
            
            for selector in gender_selectors:
                elements = await page.query_selector_all(selector)
                for elem in elements:
                    text = await elem.text_content()
                    if text:
                        text_lower = text.lower()
                        for gender, keywords in self.GENDER_KEYWORDS.items():
                            if any(keyword in text_lower for keyword in keywords):
                                return gender
        except:
            pass
        return None
    
    async def classify_product(self, data: Dict, page: Page) -> Dict[str, Any]:
        """Classify product with all new fields"""
        
        title = data.get('title', '')
        description = data.get('description', '')
        category = data.get('category', '')
        specifications = data.get('specifications', {})
        variants = data.get('variants', [])
        pricing = {
            'min_price': data.get('min_price'),
            'max_price': data.get('max_price'),
            'price': data.get('price')
        }
        
        # Detect gender (try selectors first, then classification)
        detected_gender = await self.detect_gender_from_selectors(page)
        if not detected_gender:
            detected_gender = self.classify_gender(title, description, category, variants)
        
        # Classify all fields
        product_type = self.classify_product_type(title, description, specifications)
        gender = detected_gender
        audience = self.classify_audience(title, description, gender, pricing)
        use_cases = self.classify_use_case(title, description, specifications, category)
        
        # Confidence scores (for analysis)
        confidence = {
            "product_type": "auto",
            "gender": "auto",
            "audience": "auto",
            "use_cases": "auto"
        }
        
        return {
            "product_type": product_type,
            "gender": gender,
            "audience": audience,
            "use_cases": use_cases,
            "classification_confidence": confidence,
            "classification_timestamp": datetime.now().isoformat()
        }
    
    # ========== EXTRACTION METHODS ==========
    
    async def extract_complete_product(self, page: Page, url: str) -> Dict[str, Any]:
        """Extract ALL product data - Complete version with improved error handling"""
        
        # Wait for page - but don't fail if selector not found
        try:
            await page.wait_for_selector("h1", timeout=10000)
        except:
            pass
        
        # ========== BASIC INFO ==========
        title = await self.safe_get_text(page, ["h1", ".product-title", ".title", "[data-testid='product-title']"])
        
        # Get category from breadcrumbs
        category = ""
        subcategory = ""
        subcategory_child = ""
        try:
            breadcrumb_items = await page.locator('.detail-breadcrumb-layout .id-flex a, .breadcrumb a').all()
            if len(breadcrumb_items) >= 1:
                category = await breadcrumb_items[0].inner_text()
            if len(breadcrumb_items) >= 2:
                subcategory = await breadcrumb_items[1].inner_text()
            if len(breadcrumb_items) >= 3:
                subcategory_child = await breadcrumb_items[2].inner_text()
        except:
            pass
        
        # ========== PRICING ==========
        print(f"    Extracting pricing...")
        pricing = await self.extract_complete_pricing(page)
        
        # ========== SELLER INFO ==========
        print(f"    Extracting seller information...")
        seller_info = await self.extract_complete_seller_info(page)
        
        # ========== DESCRIPTION ==========
        print(f"    Extracting description...")
        description_data = await self.extract_complete_description(page)
        
        # ========== IMAGES (FIXED) ==========
        images = await self.extract_complete_images(page)
        
        # ========== VARIANTS ==========
        variants = await self.extract_complete_variants(page)
        
        # ========== SPECIFICATIONS ==========
        specifications = await self.extract_complete_specifications(page)
        
        # ========== CUSTOMIZATION ==========
        customization = await self.extract_customization(page)
        
        # ========== LEAD TIMES ==========
        lead_times = await self.extract_lead_times(page)
        
        # ========== PACKAGING ==========
        packaging = await self.extract_packaging(page)
        
        # ========== SHIPPING INFO ==========
        shipping_info = await self.extract_shipping_info(page)
        sku_shipping = await self.extract_shipping_info_from_sku(page)
        
        # ========== PAYMENT INFO ==========
        payment_info = await self.extract_payment_info(page)
        
        # ========== SOCIAL PROOF ==========
        social_proof = await self.extract_social_proof(page)
        
        # ========== CERTIFICATIONS ==========
        certifications = await self.extract_certifications(page)
        
        # ========== SAMPLE AVAILABLE ==========
        sample_available = await self.has_sample_available(page)
        
        # Use MOQ from pricing if available
        moq = pricing.get("moq")
        moq_unit = "piece"
        
        # Create product dictionary (classification will be added later)
        product_dict = {
            "product_id": url.split("/")[-1].split(".")[0] if "/product-detail/" in url else "",
            "title": title.strip() if title else "",
            "short_title": title[:80] if title else "",
            "category": category.strip() if category else "",
            "subcategory": subcategory.strip() if subcategory else "",
            "subcategory_child": subcategory_child.strip() if subcategory_child else "",
            
            # ========== DESCRIPTION ==========
            "description": description_data.get("description", "")[:5000],
            "description_type": description_data.get("description_type", "unknown"),
            "description_highlights": description_data.get("highlights", []),
            "description_images": description_data.get("description_images", []),
            "supplier_info": description_data.get("supplier_info", ""),
            "company_overview": description_data.get("company_overview", ""),
            "factory_profile": description_data.get("factory_profile", ""),
            "competitive_advantages": description_data.get("competitive_advantages", ""),
            "packaging_shipping_info": description_data.get("packaging_shipping", ""),
            "faqs": description_data.get("faqs", []),
            "video_url": description_data.get("video_url", ""),
            "has_video": description_data.get("has_video", False),
            
            "keywords": [],
            
            # ========== PRICING ==========
            "price": pricing.get("price", ""),
            "price_text": pricing.get("price_text", ""),
            "currency": pricing.get("currency", ""),
            "min_price": pricing.get("min_price"),
            "max_price": pricing.get("max_price"),
            "sample_price": pricing.get("sample_price", ""),
            "sample_price_value": pricing.get("sample_price_value"),
            
            # ========== IMAGES ==========
            "primary_image_url": images[0] if images else "",
            "image_urls": images,
            
            # ========== VARIANTS ==========
            "variants": variants,
            
            # ========== SPECIFICATIONS ==========
            "specifications": specifications,
            
            # ========== PRICING TIERS ==========
            "pricing_tiers": pricing.get("pricing_tiers", []),
            
            # ========== MOQ ==========
            "moq": moq,
            "moq_unit": moq_unit,
            "moq_text": pricing.get("moq_text", ""),
            "supply_ability": "",
            "sample_available": sample_available,
            "sample_lead_time_days": None,
            
            # ========== CUSTOMIZATION ==========
            **customization,
            
            # ========== LEAD TIMES ==========
            "lead_time_days_min": lead_times.get("min"),
            "lead_time_days_max": lead_times.get("max"),
            
            # ========== SHIPPING ==========
            "shipping_origin_country": shipping_info.get("country", ""),
            "shipping_origin_region": shipping_info.get("region", ""),
            "shipping_origin_port": shipping_info.get("port", ""),
            "ready_to_ship": False,
            "shipping_method": sku_shipping.get("shipping_method", ""),
            "shipping_fee": sku_shipping.get("shipping_fee", ""),
            "shipping_fee_value": sku_shipping.get("shipping_fee_value"),
            "shipping_currency": sku_shipping.get("shipping_currency", ""),
            "delivery_estimate": sku_shipping.get("delivery_estimate", ""),
            "delivery_days_min": sku_shipping.get("delivery_days_min"),
            "delivery_days_max": sku_shipping.get("delivery_days_max"),
            
            # ========== PACKAGING ==========
            **packaging,
            
            # ========== INCOTERMS & METHODS ==========
            "incoterms": shipping_info.get("incoterms", []),
            "shipping_methods": shipping_info.get("methods", []),
            "estimated_delivery_days_min": shipping_info.get("delivery_min"),
            "estimated_delivery_days_max": shipping_info.get("delivery_max"),
            
            # ========== PAYMENT ==========
            "payment_methods": payment_info.get("methods", []),
            "payment_terms_text": payment_info.get("text", ""),
            
            # ========== SOCIAL PROOF ==========
            **social_proof,
            
            # ========== CERTIFICATIONS ==========
            "certifications": certifications,
            "compliance_notes": "",
            
            # ========== SUPPLIER INFO ==========
            "supplier_id": seller_info.get("supplier_id", ""),
            "supplier_name": seller_info.get("supplier_name", ""),
            "supplier_location": seller_info.get("supplier_location", ""),
            "supplier_country": seller_info.get("supplier_country", ""),
            "supplier_years_on_alibaba": seller_info.get("supplier_years_on_alibaba", ""),
            "supplier_logo_url": seller_info.get("supplier_logo_url", ""),
            "supplier_verified": seller_info.get("supplier_verified", False),
            "supplier_verification_type": seller_info.get("supplier_verification_type", ""),
            "trade_assurance_available": seller_info.get("trade_assurance_available", False),
            "supplier_type": seller_info.get("supplier_type", ""),
            
            # ========== SELLER METRICS ==========
            "seller_rating": seller_info.get("seller_rating", ""),
            "seller_rating_value": seller_info.get("seller_rating_value"),
            "seller_review_count": seller_info.get("seller_review_count", ""),
            "seller_review_count_value": seller_info.get("seller_review_count_value"),
            "reorder_rate": seller_info.get("reorder_rate", ""),
            "reorder_rate_value": seller_info.get("reorder_rate_value"),
            "response_time": seller_info.get("response_time", ""),
            "response_time_value": seller_info.get("response_time_value", ""),
            "on_time_delivery_rate": seller_info.get("on_time_delivery_rate", ""),
            "on_time_delivery_rate_value": seller_info.get("on_time_delivery_rate_value"),
            "online_revenue": seller_info.get("online_revenue", ""),
            "online_revenue_value": seller_info.get("online_revenue_value"),
            
            # ========== SELLER BADGES ==========
            "seller_badges": seller_info.get("seller_badges", []),
            "is_gold_supplier": seller_info.get("is_gold_supplier", False),
            "is_verified_supplier": seller_info.get("is_verified_supplier", False),
            
            "supplier_description": seller_info.get("supplier_description", ""),
            "supplier_url": seller_info.get("supplier_url", ""),
            
            "product_url": url,
            "scraped_at": datetime.now().isoformat()
        }
        
        return product_dict
    
    # ========== PRICING EXTRACTION ==========
    async def extract_complete_pricing(self, page: Page) -> Dict[str, Any]:
        """Extract all pricing information - Using STABLE selectors only"""
        
        pricing_info = {
            "price": "",
            "price_text": "",
            "currency": "",
            "min_price": None,
            "max_price": None,
            "pricing_tiers": [],
            "moq": None,
            "moq_text": "",
            "discount_percentage": None,
            "original_price": None,
            "original_price_text": "",
            "sample_price": "",
            "sample_price_value": None
        }

        def parse_price_text(price_text: str):
            """Extract currency and numeric value from price text"""
            if not price_text:
                return None, None
            
            patterns = [
                r'(US\$|USD|\$|€|£)\s*([\d,]+\.?\d*)',
                r'([A-Z]{2,3})\s*([\d,]+\.?\d*)',
            ]
            
            for pattern in patterns:
                m = re.search(pattern, price_text)
                if m:
                    currency = m.group(1)
                    price_str = m.group(2).replace(',', '')
                    try:
                        return currency, float(price_str)
                    except:
                        pass
            
            num_match = re.search(r'([\d,]+\.?\d*)', price_text)
            if num_match:
                try:
                    return "USD", float(num_match.group(1).replace(',', ''))
                except:
                    pass
            
            return None, None

        def parse_qty_text(qty_text: str):
            """Parse quantity text - works with any format"""
            if not qty_text:
                return None, None
            
            qty_text = qty_text.replace('&gt;', '>').strip()
            
            # Range: "10 - 49 boxes"
            range_m = re.search(r'(\d+(?:,\d+)?)\s*[-–]\s*(\d+(?:,\d+)?)', qty_text)
            if range_m:
                return int(range_m.group(1).replace(',', '')), int(range_m.group(2).replace(',', ''))
            
            # Greater than: ">= 500 boxes"
            gte_m = re.search(r'[>≥]=?\s*(\d+(?:,\d+)?)', qty_text)
            if gte_m:
                return int(gte_m.group(1).replace(',', '')), None
            
            # Single number
            single_m = re.search(r'(\d+(?:,\d+)?)', qty_text)
            if single_m:
                return int(single_m.group(1).replace(',', '')), None
            
            return None, None

        def extract_moq_from_text(text: str):
            """Extract MOQ using text pattern, not classes"""
            if not text:
                return None
            m = re.search(r'[Mm]inimum\s+order\s+quantity\s*:\s*(\d+(?:,\d+)?)', text)
            if m:
                return int(m.group(1).replace(',', ''))
            return None

        try:
            await page.wait_for_timeout(3000)
            
            # ========== METHOD 1: Find by DATA TESTID (Most Stable) ==========
            # Check for range-price
            range_price = await page.query_selector('[data-testid="range-price"]')
            if range_price:
                print(f"      Found range-price (stable selector)")
                
                # Get ALL text from range-price - then extract what we need
                range_html = await range_price.evaluate("el => el.innerText")
                
                # Extract MOQ using regex
                moq_match = re.search(r'[Mm]inimum\s+order\s+quantity\s*:\s*(\d+(?:,\d+)?)', range_html)
                if moq_match:
                    pricing_info["moq"] = int(moq_match.group(1).replace(',', ''))
                    pricing_info["moq_text"] = moq_match.group(0)
                    print(f"      MOQ: {pricing_info['moq']}")
                
                # Extract price (any number with currency)
                price_match = re.search(r'(US\$|\$|€|£)\s*([\d,]+\.?\d*)\s*[-–]\s*([\d,]+\.?\d*)', range_html)
                if price_match:
                    currency = price_match.group(1)
                    min_price = float(price_match.group(2).replace(',', ''))
                    max_price = float(price_match.group(3).replace(',', ''))
                    
                    pricing_info["currency"] = currency
                    pricing_info["min_price"] = min_price
                    pricing_info["max_price"] = max_price
                    pricing_info["price"] = f"{min_price}-{max_price}"
                    pricing_info["price_text"] = price_match.group(0)
                    
                    pricing_info["pricing_tiers"].append({
                        "min_quantity": pricing_info["moq"],
                        "max_quantity": None,
                        "unit_price_min": min_price,
                        "unit_price_max": max_price,
                        "unit_price_text": price_match.group(0),
                        "currency": currency,
                        "quantity_text": pricing_info["moq_text"]
                    })
                    
                    print(f"      Range price: {currency} {min_price} - {max_price}")
            
            # Check for ladder-price
            ladder_price = await page.query_selector('[data-testid="ladder-price"]')
            if ladder_price:
                print(f"      Found ladder-price (stable selector)")
                
                # Get all price items - they have class "price-item" (stable)
                price_items = await ladder_price.query_selector_all('.price-item')
                print(f"      Found {len(price_items)} price items")
                
                for idx, item in enumerate(price_items):
                    try:
                        # Get ALL text from this item
                        item_text = await item.evaluate("el => el.innerText")
                        
                        # Extract quantity (look for numbers with ranges)
                        qty_match = re.search(r'(\d+(?:,\d+)?)\s*[-–]\s*(\d+(?:,\d+)?)', item_text)
                        if not qty_match:
                            qty_match = re.search(r'[>≥]=?\s*(\d+(?:,\d+)?)', item_text)
                        if not qty_match:
                            qty_match = re.search(r'^(\d+(?:,\d+)?)', item_text)
                        
                        min_q = None
                        max_q = None
                        if qty_match:
                            if ' - ' in item_text or '-' in item_text:
                                # It's a range
                                nums = re.findall(r'(\d+(?:,\d+)?)', item_text)
                                if len(nums) >= 2:
                                    min_q = int(nums[0].replace(',', ''))
                                    max_q = int(nums[1].replace(',', ''))
                            else:
                                # Single number
                                min_q = int(qty_match.group(1).replace(',', ''))
                        
                        # Check if this is MOQ format
                        if 'Minimum order quantity' in item_text:
                            moq_val = extract_moq_from_text(item_text)
                            if moq_val:
                                pricing_info["moq"] = moq_val
                                pricing_info["moq_text"] = item_text[:100]
                                min_q = moq_val
                        
                        # Extract price
                        price_match = re.search(r'(US\$|\$|€|£)\s*([\d,]+\.?\d*)', item_text)
                        if not price_match:
                            price_match = re.search(r'([\d,]+\.?\d*)', item_text)
                        
                        if price_match:
                            currency = price_match.group(1) if len(price_match.groups()) > 1 else "USD"
                            price_str = price_match.group(2) if len(price_match.groups()) > 1 else price_match.group(1)
                            price_val = float(price_str.replace(',', ''))
                            
                            # Check for original price (strikethrough)
                            original_match = re.search(r'was\s*(?:US\$|\$|€|£)\s*([\d,]+\.?\d*)', item_text, re.IGNORECASE)
                            if not original_match:
                                original_match = re.search(r'(?:US\$|\$|€|£)\s*([\d,]+\.?\d*).*?(?:US\$|\$|€|£)\s*([\d,]+\.?\d*)', item_text)
                            
                            tier = {
                                "min_quantity": min_q,
                                "max_quantity": max_q,
                                "unit_price": price_val,
                                "unit_price_text": price_match.group(0),
                                "currency": currency,
                                "quantity_text": item_text[:100]
                            }
                            
                            if original_match:
                                original_val = float(original_match.group(1).replace(',', ''))
                                tier["original_price"] = original_val
                                tier["original_price_text"] = original_match.group(0)
                                
                                if pricing_info["original_price"] is None:
                                    pricing_info["original_price"] = original_val
                            
                            pricing_info["pricing_tiers"].append(tier)
                            
                            # Track min/max
                            if pricing_info["min_price"] is None or price_val < pricing_info["min_price"]:
                                pricing_info["min_price"] = price_val
                            if pricing_info["max_price"] is None or price_val > pricing_info["max_price"]:
                                pricing_info["max_price"] = price_val
                            
                            if not pricing_info["price"]:
                                pricing_info["price"] = str(price_val)
                                pricing_info["price_text"] = price_match.group(0)
                                pricing_info["currency"] = currency
                            
                            # Update MOQ from first tier
                            if min_q and min_q > 0:
                                if pricing_info["moq"] is None or min_q < pricing_info["moq"]:
                                    pricing_info["moq"] = min_q
                            
                            print(f"      Tier {idx+1}: qty={min_q}-{max_q}, price={price_val}")
                            
                    except Exception as e:
                        print(f"      Error parsing tier {idx+1}: {e}")
            
            # ========== METHOD 2: If no data-testid found, search by text patterns ==========
            if not pricing_info["pricing_tiers"]:
                print(f"      No data-testid found, searching by text patterns...")
                
                # Get all elements that might contain prices
                page_text = await page.evaluate("""
                    () => {
                        const results = [];
                        // Look for elements containing currency symbols
                        const elements = document.querySelectorAll('*');
                        for (const el of elements) {
                            const text = el.innerText;
                            if (text && /US\\$|\\$|€|£/.test(text) && text.length < 200) {
                                // Check if it's a price element (not too large)
                                const hasNumber = /\\d/.test(text);
                                if (hasNumber) {
                                    results.push({
                                        text: text.trim(),
                                        html: el.outerHTML.substring(0, 500)
                                    });
                                }
                            }
                        }
                        return results.slice(0, 10); // Limit to 10
                    }
                """)
                
                for item in page_text:
                    text = item.get('text', '')
                    if not text:
                        continue
                    
                    # Extract price
                    price_match = re.search(r'(US\$|\$|€|£)\s*([\d,]+\.?\d*)', text)
                    if price_match:
                        currency = price_match.group(1)
                        price_val = float(price_match.group(2).replace(',', ''))
                        
                        # Check for MOQ
                        moq_match = re.search(r'[Mm]inimum\s+order\s*:\s*(\d+)', text)
                        if not moq_match:
                            moq_match = re.search(r'MOQ\s*:\s*(\d+)', text, re.IGNORECASE)
                        
                        if moq_match:
                            pricing_info["moq"] = int(moq_match.group(1))
                            pricing_info["moq_text"] = moq_match.group(0)
                        
                        pricing_info["price"] = str(price_val)
                        pricing_info["price_text"] = price_match.group(0)
                        pricing_info["currency"] = currency
                        pricing_info["min_price"] = price_val
                        pricing_info["max_price"] = price_val
                        
                        pricing_info["pricing_tiers"].append({
                            "min_quantity": pricing_info["moq"],
                            "max_quantity": None,
                            "unit_price": price_val,
                            "unit_price_text": price_match.group(0),
                            "currency": currency,
                            "quantity_text": text
                        })
                        
                        print(f"      Found price via text search: {price_match.group(0)}")
                        break
            
            # Extract sample price
            sample_price_elem = await page.query_selector('[data-testid="sample-price"], .sample-price')
            if sample_price_elem:
                sample_text = await sample_price_elem.text_content()
                if sample_text:
                    pricing_info["sample_price"] = sample_text.strip()
                    sample_match = re.search(r'([\d,]+\.?\d*)', sample_text)
                    if sample_match:
                        pricing_info["sample_price_value"] = float(sample_match.group(1).replace(',', ''))
            
            # ========== FINAL SUMMARY ==========
            if pricing_info["pricing_tiers"]:
                print(f"      ✅ Extracted {len(pricing_info['pricing_tiers'])} tier(s)")
            else:
                print(f"      ⚠️ No pricing extracted!")
            
            if pricing_info["moq"]:
                print(f"      ✅ MOQ: {pricing_info['moq']}")
            
            if pricing_info["price"]:
                print(f"      ✅ Price: {pricing_info['currency']} {pricing_info['price']}")
            
        except Exception as e:
            print(f"      ❌ Pricing extraction error: {e}")
            import traceback
            traceback.print_exc()
        
        return pricing_info
    
    # ========== SELLER INFO EXTRACTION ==========
    async def extract_complete_seller_info(self, page: Page) -> Dict[str, Any]:
        """Extract complete seller/supplier information from ALL formats"""
        
        seller_info = {
            "supplier_id": "",
            "supplier_name": "",
            "supplier_location": "",
            "supplier_country": "",
            "supplier_years_on_alibaba": "",
            "supplier_logo_url": "",
            "supplier_verified": False,
            "supplier_verification_type": "",
            "trade_assurance_available": False,
            "supplier_type": "",
            
            # Seller metrics
            "seller_rating": "",
            "seller_rating_value": None,
            "seller_review_count": "",
            "seller_review_count_value": None,
            "reorder_rate": "",
            "reorder_rate_value": None,
            "response_time": "",
            "response_time_value": "",
            "on_time_delivery_rate": "",
            "on_time_delivery_rate_value": None,
            "online_revenue": "",
            "online_revenue_value": None,
            
            # Seller badges
            "seller_badges": [],
            "is_gold_supplier": False,
            "is_verified_supplier": False,
            
            "supplier_description": "",
            "supplier_url": ""
        }
        
        try:
            # ========== METHOD 1: Unified Company Card (NEW FORMAT) ==========
            unified_card = await page.query_selector('[data-testid="module-details-unifed-company-card"], .module_unifed_company_card')
            
            if unified_card:
                print(f"      Found unified company card")
                
                # Company name
                company_link = await unified_card.query_selector('a[href*=".m.en.alibaba.com"]')
                if company_link:
                    company_name = await company_link.text_content()
                    if company_name:
                        seller_info["supplier_name"] = company_name.strip()
                        supplier_url = await company_link.get_attribute('href')
                        if supplier_url:
                            seller_info["supplier_url"] = supplier_url
                
                # Company logo
                logo_img = await unified_card.query_selector('img[alt="company logo"]')
                if not logo_img:
                    logo_img = await unified_card.query_selector('.id-size-16 img')
                if logo_img:
                    logo_url = await logo_img.get_attribute('src')
                    if logo_url:
                        if logo_url.startswith('//'):
                            logo_url = 'https:' + logo_url
                        seller_info["supplier_logo_url"] = logo_url
                
                # Supplier type and years
                type_elem = await unified_card.query_selector('.id-mt-2 .id-flex.id-items-center')
                if type_elem:
                    type_text = await type_elem.text_content()
                    if type_text:
                        # Extract supplier type
                        type_match = re.search(r'(Trading Company|Manufacturer|Distributor|Wholesaler)', type_text)
                        if type_match:
                            seller_info["supplier_type"] = type_match.group(1)
                        
                        # Extract years on Alibaba
                        years_match = re.search(r'(\d+)\s*yrs?\s*on\s*Alibaba', type_text)
                        if years_match:
                            seller_info["supplier_years_on_alibaba"] = years_match.group(1)
                
                # Location
                location_elem = await unified_card.query_selector('.id-mt-1 .id-flex.id-items-center')
                if location_elem:
                    location_text = await location_elem.text_content()
                    if location_text:
                        country_match = re.search(r'Located in\s*([A-Z]{2}|[A-Za-z]+)', location_text)
                        if country_match:
                            seller_info["supplier_country"] = country_match.group(1)
                            seller_info["supplier_location"] = country_match.group(1)
                
                # Company metrics
                metric_buttons = await unified_card.query_selector_all('.id-grid-cols-3 button, [data-state]')
                
                for button in metric_buttons:
                    try:
                        label_elem = await button.query_selector('.id-text-sm, div:first-child')
                        value_elem = await button.query_selector('.id-text-xl, .id-font-semibold')
                        
                        if label_elem and value_elem:
                            label = await label_elem.text_content()
                            value = await value_elem.text_content()
                            
                            if label and value:
                                label_lower = label.lower()
                                value_text = value.strip()
                                
                                if 'delivery rate' in label_lower:
                                    seller_info["on_time_delivery_rate"] = value_text
                                    rate_match = re.search(r'(\d+(?:\.\d+)?)%', value_text)
                                    if rate_match:
                                        seller_info["on_time_delivery_rate_value"] = float(rate_match.group(1))
                                
                                elif 'revenue' in label_lower:
                                    seller_info["online_revenue"] = value_text
                                    revenue_match = re.search(r'([A-Z]{3,4})?\s*([\d,]+\+?)', value_text)
                                    if revenue_match:
                                        seller_info["online_revenue_value"] = revenue_match.group(2)
                                
                                elif 'response time' in label_lower:
                                    seller_info["response_time"] = value_text
                                    seller_info["response_time_value"] = value_text
                    
                    except Exception as e:
                        print(f"      Error parsing metric: {e}")
            
            # ========== METHOD 2: Seller Overview Card (OLD FORMAT) ==========
            if not seller_info["supplier_name"]:
                seller_card = await page.query_selector('[data-testid="module-overview-seller-card"], [data-testid="seller-overview-card"]')
                
                if seller_card:
                    print(f"      Found seller overview card")
                    
                    # Company name
                    company_link = await seller_card.query_selector('[data-testid="seller-overview-card-company-link"]')
                    if company_link:
                        seller_info["supplier_name"] = await company_link.text_content()
                        supplier_url = await company_link.get_attribute('href')
                        if supplier_url:
                            seller_info["supplier_url"] = supplier_url
                    
                    # Location and years
                    meta_elem = await seller_card.query_selector('[data-testid="seller-overview-card-meta"]')
                    if meta_elem:
                        meta_text = await meta_elem.text_content()
                        if meta_text:
                            years_match = re.search(r'(\d+)\s+yr', meta_text)
                            if years_match:
                                seller_info["supplier_years_on_alibaba"] = years_match.group(1)
                            
                            if 'CN' in meta_text:
                                seller_info["supplier_country"] = "China"
                    
                    # Company logo
                    logo_img = await seller_card.query_selector('img[alt="company logo"]')
                    if logo_img:
                        logo_url = await logo_img.get_attribute('src')
                        if logo_url:
                            if logo_url.startswith('//'):
                                logo_url = 'https:' + logo_url
                            seller_info["supplier_logo_url"] = logo_url
                    
                    # Seller metrics
                    metrics = await seller_card.query_selector('[data-testid="seller-overview-card-metrics"]')
                    if metrics:
                        metric_items = await metrics.query_selector_all('[data-testid="seller-overview-card-metric-item"]')
                        
                        for item in metric_items:
                            item_text = await item.text_content()
                            if item_text:
                                item_text = item_text.strip()
                                
                                if 'reorder rate' in item_text.lower():
                                    seller_info["reorder_rate"] = item_text
                                    rate_match = re.search(r'(\d+(?:\.\d+)?)%', item_text)
                                    if rate_match:
                                        seller_info["reorder_rate_value"] = float(rate_match.group(1))
                                
                                elif 'response time' in item_text.lower():
                                    seller_info["response_time"] = item_text
                                    seller_info["response_time_value"] = item_text
                                
                                elif 'delivery rate' in item_text.lower():
                                    seller_info["on_time_delivery_rate"] = item_text
                                    rate_match = re.search(r'(\d+(?:\.\d+)?)%', item_text)
                                    if rate_match:
                                        seller_info["on_time_delivery_rate_value"] = float(rate_match.group(1))
                    
                    # Rating
                    rating_elem = await seller_card.query_selector('[data-testid="seller-overview-card-review"]')
                    if rating_elem:
                        rating_text = await rating_elem.text_content()
                        if rating_text:
                            seller_info["seller_rating"] = rating_text.strip()
                            rating_match = re.search(r'(\d+(?:\.\d+)?)/\d+\.?\d*', rating_text)
                            if rating_match:
                                seller_info["seller_rating_value"] = float(rating_match.group(1))
                            
                            review_match = re.search(r'\((\d+)\s*reviews?\)', rating_text)
                            if review_match:
                                seller_info["seller_review_count_value"] = int(review_match.group(1))
            
            # ========== METHOD 3: Trade Assurance ==========
            ta_selectors = [
                '.ta-semi',
                '[data-testid="trade-assurance"]',
                '.trade-assurance'
            ]
            
            for selector in ta_selectors:
                try:
                    ta_elem = await page.query_selector(selector)
                    if ta_elem:
                        seller_info["trade_assurance_available"] = True
                        break
                except:
                    pass
            
            # ========== METHOD 4: Verification Badges ==========
            badge_selectors = [
                '[data-testid="seller-badge"]',
                '.seller-badge',
                '.gold-supplier',
                '.verified-supplier',
                '[class*="badge"]'
            ]
            
            for selector in badge_selectors:
                try:
                    badges = await page.query_selector_all(selector)
                    for badge in badges:
                        badge_text = await badge.text_content()
                        if badge_text:
                            seller_info["seller_badges"].append(badge_text.strip())
                            if 'gold' in badge_text.lower():
                                seller_info["is_gold_supplier"] = True
                            if 'verified' in badge_text.lower():
                                seller_info["is_verified_supplier"] = True
                                seller_info["supplier_verified"] = True
                        else:
                            # Check alt attribute for images
                            alt_text = await badge.get_attribute('alt')
                            if alt_text:
                                seller_info["seller_badges"].append(alt_text.strip())
                                if 'gold' in alt_text.lower():
                                    seller_info["is_gold_supplier"] = True
                                if 'verified' in alt_text.lower():
                                    seller_info["is_verified_supplier"] = True
                                    seller_info["supplier_verified"] = True
                except:
                    pass
            
            # ========== METHOD 5: Extract from specifications ==========
            if not seller_info["supplier_location"]:
                specs = await self.extract_complete_specifications(page)
                if "Place of Origin" in specs:
                    seller_info["supplier_location"] = specs["Place of Origin"]
                    if "China" in specs["Place of Origin"]:
                        seller_info["supplier_country"] = "China"
                    elif "India" in specs["Place of Origin"]:
                        seller_info["supplier_country"] = "India"
            
        except Exception as e:
            print(f"      Error extracting seller info: {e}")
        
        return seller_info
    
    # ========== DESCRIPTION EXTRACTION ==========
    async def extract_complete_description(self, page: Page) -> Dict[str, Any]:
        """Extract complete product description from ALL possible formats"""
        
        description_data = {
            "description": "",
            "highlights": [],
            "supplier_info": "",
            "company_overview": "",
            "factory_profile": "",
            "competitive_advantages": "",
            "packaging_shipping": "",
            "faqs": [],
            "description_images": [],
            "video_url": "",
            "has_video": False,
            "description_type": "unknown"
        }
        
        try:
            # ========== METHOD 1: Structured Description ==========
            structured_selectors = [
                '[data-testid="module-structure-description"]',
                '[data-testid="module-details-structure-description"]', 
            ]
            
            structured_desc = None
            for selector in structured_selectors:
                structured_desc = await page.query_selector(selector)
                if structured_desc:
                    print(f"      Found structured description with: {selector}")
                    break
            
            if structured_desc:
                description_data["description_type"] = "structured_image"
                print(f"      Extracting structured (image-based) description")
                
                # Extract images
                image_container = await structured_desc.query_selector('[data-testid="product-detail-image-simple"]')
                if image_container:
                    images = await image_container.query_selector_all('img')
                    for img in images:
                        src = await img.get_attribute('src')
                        if src:
                            src = src.replace('_80x80', '_960x960').replace('_100x100', '_960x960')
                            if src not in description_data["description_images"]:
                                description_data["description_images"].append(src)
                    print(f"      Found {len(description_data['description_images'])} images in structured description")
                
                # Extract highlights
                highlight_items = await structured_desc.query_selector_all('[data-testid="product-detail-text-sort"]')
                for item in highlight_items:
                    text = await item.text_content()
                    if text and text.strip():
                        clean_text = re.sub(r'^[•●○■◆]', '', text.strip())
                        if clean_text and len(clean_text) > 5:
                            description_data["highlights"].append(clean_text)
            
            # ========== METHOD 2: Iframe Description ==========
            iframe_desc = await self.extract_description_from_iframe(page)
            if iframe_desc and len(iframe_desc) > len(description_data["description"]):
                description_data["description"] = iframe_desc
                if description_data["description_type"] == "unknown":
                    description_data["description_type"] = "iframe"
                print(f"      Extracted description from iframe: {len(iframe_desc)} chars")
            
            # ========== METHOD 3: Standard Module Description ==========
            if not description_data["description"]:
                module_desc = await page.query_selector('[data-testid="module-details-description"]')
                if module_desc:
                    desc_text = await module_desc.evaluate("""
                        (element) => {
                            const clone = element.cloneNode(true);
                            const removeElements = clone.querySelectorAll('iframe, video, .module_detail_video, .module_product_specification');
                            removeElements.forEach(el => el.remove());
                            return clone.innerText || clone.textContent || '';
                        }
                    """)
                    if desc_text and len(desc_text) > 100:
                        description_data["description"] = desc_text.strip()
                        if description_data["description_type"] == "unknown":
                            description_data["description_type"] = "standard"
                        print(f"      Extracted from module-details-description: {len(desc_text)} chars")
            
            # ========== Extract Video ==========
            video_selectors = [
                'video[src*="alibaba"]',
                '.widget-detail-video video',
                '[data-module-name="module_detail_video"] video',
                'video[playsinline]'
            ]
            
            for selector in video_selectors:
                try:
                    video_elem = await page.query_selector(selector)
                    if video_elem:
                        video_url = await video_elem.get_attribute('src')
                        if video_url and video_url.startswith('//'):
                            video_url = 'https:' + video_url
                        if video_url:
                            description_data["video_url"] = video_url
                            description_data["has_video"] = True
                            print(f"      Found product video: {video_url[:80]}...")
                            break
                except:
                    pass
            
            # ========== Extract Images from Description ==========
            image_containers = [
                '.module_description',
                '.description-layout',
                '[data-testid="module-details-description"]',
                '[data-testid="product-detail-image-simple"]'
            ]
            
            for container_selector in image_containers:
                container = await page.query_selector(container_selector)
                if container:
                    images = await container.query_selector_all('img')
                    for img in images[:20]:
                        try:
                            src = await img.get_attribute('src')
                            if src and ('alicdn' in src or 'sc04' in src or 'aliimg' in src):
                                if src.startswith('//'):
                                    src = 'https:' + src
                                src = src.replace('_80x80', '_960x960').replace('_100x100', '_960x960').replace('_50x50', '_960x960')
                                if src not in description_data["description_images"]:
                                    description_data["description_images"].append(src)
                        except:
                            pass
            
            if description_data["description_images"]:
                print(f"      Total images extracted: {len(description_data['description_images'])}")
            
            # ========== Clean up description ==========
            if description_data["description"]:
                description_data["description"] = re.sub(r'\n\s*\n', '\n\n', description_data["description"])
                description_data["description"] = re.sub(r' +', ' ', description_data["description"])
                description_data["description"] = description_data["description"].strip()
                
                # Remove common boilerplate text
                boilerplate_patterns = [
                    r'Product descriptions from the supplier\s*',
                    r'Report abuse\s*',
                    r'Video Description\s*',
                ]
                for pattern in boilerplate_patterns:
                    description_data["description"] = re.sub(pattern, '', description_data["description"], flags=re.IGNORECASE)
                
                if len(description_data["description"]) > 5000:
                    description_data["description"] = description_data["description"][:5000] + "..."
            
        except Exception as e:
            print(f"      Error extracting description: {e}")
        
        return description_data

    async def extract_description_from_iframe(self, page: Page) -> str:
        """Extract description from iframe"""
        description = ""
        
        try:
            await page.wait_for_timeout(1000)
            
            iframe_selectors = [
                '.module_product_specification iframe',
                'iframe[src*="descIframe"]',
                'iframe[src*="description"]',
                '#layout-other-wrapper iframe',
                '[data-module-name="module_product_specification"] iframe'
            ]
            
            for selector in iframe_selectors:
                try:
                    iframe_element = await page.query_selector(selector)
                    if iframe_element:
                        iframe_src = await iframe_element.get_attribute('src')
                        print(f"      Found description iframe: {iframe_src[:80]}...")
                        
                        frames = page.frames
                        for frame in frames:
                            if frame.url and ('descIframe' in frame.url or 'description' in frame.url):
                                try:
                                    body_text = await frame.evaluate("""
                                        () => {
                                            const body = document.body;
                                            if (!body) return '';
                                            let text = body.innerText || body.textContent || '';
                                            text = text.replace(/\\s+/g, ' ').trim();
                                            return text;
                                        }
                                    """)
                                    
                                    if body_text and len(body_text) > 100:
                                        description = body_text
                                        print(f"      Extracted {len(description)} chars from iframe")
                                        return description
                                        
                                except Exception:
                                    continue
                        break
                except Exception:
                    continue
            
        except Exception as e:
            print(f"      Error extracting iframe description: {e}")
        
        return description

    # ========== IMAGES EXTRACTION ==========
    async def extract_complete_images(self, page: Page) -> List[str]:
        """Extract all product images - Fixed version with better selectors"""
        images = []
        
        # Strategy 1: Main product image
        main_image_selectors = [
            '.product-image img',
            '.magnifier-image img',
            '.detail-gallery img',
            '[data-testid="media-image"] img',
            '.current-main-image img',
            '.main-image img',
            '.product-view img'
        ]
        
        for selector in main_image_selectors:
            try:
                main_img = await page.query_selector(selector)
                if main_img:
                    src = await main_img.get_attribute('src')
                    if src:
                        if src.startswith('//'):
                            src = 'https:' + src
                        src = src.replace('_80x80', '_960x960').replace('_100x100', '_960x960').replace('_350x350', '_960x960')
                        images.append(src)
                        break
            except:
                continue
        
        # Strategy 2: Thumbnails
        thumbnail_selectors = [
            '.thumbnail img',
            '.gallery-thumb img',
            '.detail-thumb img',
            '[data-testid="product-image-list"] img',
            '.image-item img',
            '.swiper-slide img'
        ]
        
        for selector in thumbnail_selectors:
            try:
                thumbnails = await page.query_selector_all(selector)
                for thumb in thumbnails[:10]:
                    src = await thumb.get_attribute('src')
                    if src:
                        if src.startswith('//'):
                            src = 'https:' + src
                        src = src.replace('_80x80', '_960x960').replace('_100x100', '_960x960').replace('_350x350', '_960x960')
                        if src not in images:
                            images.append(src)
            except:
                continue
        
        # Strategy 3: Media items
        try:
            media_items = await page.query_selector_all('[data-testid="media-image"] img, .media-item img')
            for img in media_items[:10]:
                src = await img.get_attribute('src')
                if src and 'logo' not in src.lower() and 'icon' not in src.lower():
                    if src.startswith('//'):
                        src = 'https:' + src
                    src = src.replace('_80x80', '_960x960').replace('_100x100', '_960x960')
                    if src not in images:
                        images.append(src)
        except:
            pass
        
        # Strategy 4: Fallback
        if len(images) < 3:
            try:
                all_imgs = await page.query_selector_all('img[src*="alicdn"], img[src*="sc04"]')
                for img in all_imgs[:10]:
                    src = await img.get_attribute('src')
                    if src and 'logo' not in src.lower() and 'icon' not in src.lower() and 'thumbnail' not in src.lower():
                        if src.startswith('//'):
                            src = 'https:' + src
                        src = src.replace('_80x80', '_960x960').replace('_100x100', '_960x960')
                        if src not in images:
                            images.append(src)
            except:
                pass
        
        return images[:10]
    
    # ========== VARIANTS EXTRACTION ==========
    async def extract_complete_variants(self, page: Page) -> List[Dict]:
        """Extract all variants/SKU options from ALL possible formats"""
        
        variants = []
        
        try:
            # Find SKU module
            sku_module = await page.query_selector('[data-module-name="module_sku"]')
            if not sku_module:
                sku_module = page
            
            # Color variants with images
            color_lists = await sku_module.query_selector_all('[data-testid="sku-list"]:has(h4:has-text("Color"))')
            
            for color_list in color_lists:
                title_elem = await color_list.query_selector('[data-testid="sku-list-title"] span')
                attribute_name = await title_elem.text_content() if title_elem else "Color"
                attribute_name = attribute_name.replace(':', '').strip()
                
                color_items = await color_list.query_selector_all('[data-testid="sku-list-item"] > div[data-testid="non-last-sku-item"]')
                
                for item in color_items:
                    try:
                        is_selected = await item.query_selector('.selected') is not None
                        img = await item.query_selector('img')
                        color_name = ""
                        color_image = ""
                        
                        if img:
                            color_name = await img.get_attribute('alt')
                            color_image = await img.get_attribute('src')
                            if color_image and color_image.startswith('//'):
                                color_image = 'https:' + color_image
                        
                        if not color_name:
                            span = await item.query_selector('span')
                            if span:
                                color_name = await span.text_content()
                        
                        if color_name:
                            variants.append({
                                "type": attribute_name,
                                "value": color_name.strip(),
                                "image_url": color_image,
                                "is_selected": is_selected,
                                "format": "color_with_image"
                            })
                    except Exception:
                        continue
            
            # Text-based variants
            text_variant_sections = await sku_module.query_selector_all('[data-testid="sku-list"]')
            
            for section in text_variant_sections:
                try:
                    title_elem = await section.query_selector('[data-testid="sku-list-title"] span')
                    if not title_elem:
                        continue
                    
                    title_text = await title_elem.text_content()
                    if not title_text:
                        continue
                    
                    attribute_name = title_text.replace(':', '').strip()
                    
                    if attribute_name.lower() in ['color', 'colour']:
                        continue
                    
                    option_items = await section.query_selector_all('[data-testid="sku-list-item"] > div[data-testid="non-last-sku-item"]')
                    
                    for item in option_items:
                        try:
                            is_selected = await item.query_selector('.selected') is not None
                            span = await item.query_selector('span')
                            option_value = await span.text_content() if span else ""
                            
                            if not option_value:
                                inner_span = await item.query_selector('.id-text-secondary-foreground')
                                if inner_span:
                                    option_value = await inner_span.text_content()
                            
                            if option_value and option_value.strip():
                                variants.append({
                                    "type": attribute_name,
                                    "value": option_value.strip(),
                                    "image_url": "",
                                    "is_selected": is_selected,
                                    "format": "text"
                                })
                        except Exception:
                            continue
                except Exception:
                    continue
            
            # Remove duplicates
            unique_variants = []
            seen = set()
            
            for variant in variants:
                key = f"{variant['type']}_{variant['value']}"
                if key not in seen:
                    seen.add(key)
                    unique_variants.append(variant)
            
            print(f"      Extracted {len(unique_variants)} variants")
            return unique_variants
            
        except Exception as e:
            print(f"      Error extracting variants: {e}")
            return []
    
    # ========== SPECIFICATIONS EXTRACTION ==========
    async def extract_complete_specifications(self, page: Page) -> Dict[str, str]:
        specs = {}
        try:
            spec_selectors = [
                '[data-testid="module-attribute-row"]',
                '.product-attributes li',
                '.attribute-item',
                '.specification-item',
                '.product-specs tr'
            ]
            
            for selector in spec_selectors:
                try:
                    rows = await page.locator(selector).all()
                    for row in rows:
                        name_elem = row.locator('[data-testid="module-attribute-name"], .attr-name, .spec-name, th').first
                        value_elem = row.locator('[data-testid="module-attribute-value"], .attr-value, .spec-value, td').first
                        name = await name_elem.inner_text() if await name_elem.count() > 0 else ""
                        value = await value_elem.inner_text() if await value_elem.count() > 0 else ""
                        if name and value:
                            specs[name.strip()] = value.strip()
                    if specs:
                        break
                except:
                    continue
        except:
            pass
        return specs
    
    # ========== CUSTOMIZATION EXTRACTION ==========
    async def extract_customization(self, page: Page) -> Dict[str, Any]:
        custom = {
            "custom_logo_available": False, "custom_packaging_available": False,
            "graphic_customization_available": False, "oem_available": False,
            "odm_available": False, "customization_notes": ""
        }
        try:
            custom_items = await page.locator('.module_supplier_customization .id-flex.id-items-center span, .customization-item').all()
            texts = []
            for item in custom_items:
                text = await item.inner_text()
                texts.append(text)
                tl = text.lower()
                if "logo" in tl:
                    custom["custom_logo_available"] = True
                if "packaging" in tl:
                    custom["custom_packaging_available"] = True
                if "oem" in tl:
                    custom["oem_available"] = True
                if "odm" in tl:
                    custom["odm_available"] = True
            custom["customization_notes"] = ", ".join(texts)
        except:
            pass
        return custom
    
    # ========== LEAD TIMES EXTRACTION ==========
    async def extract_lead_times(self, page: Page) -> Dict[str, Optional[int]]:
        lead_times = {"min": None, "max": None}
        try:
            lead_table = page.locator('.lead-list table')
            if await lead_table.count() > 0:
                rows = await lead_table.locator('tr').all()
                for row in rows:
                    cells = await row.locator('td').all()
                    if len(cells) >= 2:
                        qty_text = await cells[0].inner_text()
                        lead_text = await cells[1].inner_text()
                        if "1" in qty_text or "1 -" in qty_text:
                            numbers = re.findall(r'\d+', lead_text)
                            if numbers:
                                lead_times["min"] = int(numbers[0])
                                break
        except:
            pass
        return lead_times
    
    # ========== PACKAGING EXTRACTION ==========
    async def extract_packaging(self, page: Page) -> Dict[str, Any]:
        packaging = {
            "units_per_carton": None, "carton_length_cm": None, "carton_width_cm": None,
            "carton_height_cm": None, "carton_volume_cbm": None, "gross_weight_kg": None,
            "net_weight_kg": None, "packaging_description": ""
        }
        try:
            rows = await page.locator('[data-testid="module-attribute-row"]').all()
            for row in rows:
                name_elem = row.locator('[data-testid="module-attribute-name"]').first
                value_elem = row.locator('[data-testid="module-attribute-value"]').first
                name = await name_elem.inner_text() if await name_elem.count() > 0 else ""
                value = await value_elem.inner_text() if await value_elem.count() > 0 else ""
                if "package size" in name.lower() or "carton size" in name.lower():
                    dims = re.findall(r'(\d+(?:\.\d+)?)', value)
                    if len(dims) >= 3:
                        packaging["carton_length_cm"] = float(dims[0])
                        packaging["carton_width_cm"] = float(dims[1])
                        packaging["carton_height_cm"] = float(dims[2])
                elif "gross weight" in name.lower():
                    match = re.search(r'([\d.]+)\s*kg', value.lower())
                    if match:
                        packaging["gross_weight_kg"] = float(match.group(1))
                elif "selling units" in name.lower():
                    packaging["packaging_description"] = value
        except:
            pass
        return packaging
    
    # ========== SHIPPING INFO EXTRACTION ==========
    async def extract_shipping_info(self, page: Page) -> Dict[str, Any]:
        info = {"country": "", "region": "", "port": "", "incoterms": [], "methods": [], "delivery_min": None, "delivery_max": None}
        try:
            specs = await self.extract_complete_specifications(page)
            if "Place of Origin" in specs:
                info["country"] = specs["Place of Origin"]
        except:
            pass
        return info
    
    async def extract_shipping_info_from_sku(self, page: Page) -> Dict[str, Any]:
        """Extract shipping information from SKU module"""
        
        shipping_info = {
            "shipping_method": "",
            "shipping_fee": "",
            "shipping_fee_value": None,
            "shipping_currency": "",
            "delivery_estimate": "",
            "delivery_days_min": None,
            "delivery_days_max": None
        }
        
        try:
            sku_module = await page.query_selector('[data-module-name="module_sku"]')
            if not sku_module:
                return shipping_info
            
            # Find shipping section
            logistic_section = await sku_module.query_selector('.sku-logistic, [data-testid="sku-logistic"]')
            if logistic_section:
                # Shipping method
                method_elem = await logistic_section.query_selector('.logistics-method')
                if method_elem:
                    shipping_info["shipping_method"] = await method_elem.text_content()
                
                # Shipping fee
                fee_elem = await logistic_section.query_selector('[data-testid="logistics-total-price"]')
                if fee_elem:
                    fee_text = await fee_elem.text_content()
                    shipping_info["shipping_fee"] = fee_text.strip() if fee_text else ""
                    
                    # Extract numeric value and currency
                    fee_match = re.search(r'([A-Z]{3,4}|\$|€|£)\s*([\d,]+\.?\d*)', fee_text) if fee_text else None
                    if fee_match:
                        shipping_info["shipping_currency"] = fee_match.group(1)
                        shipping_info["shipping_fee_value"] = float(fee_match.group(2).replace(',', ''))
                
                # Delivery estimate
                delivery_elem = await logistic_section.query_selector('[data-testid="logistics-delivery-date"]')
                if delivery_elem:
                    delivery_text = await delivery_elem.text_content()
                    shipping_info["delivery_estimate"] = delivery_text.strip() if delivery_text else ""
                    
                    # Extract days
                    days_match = re.search(r'(\d+)\s*-\s*(\d+)\s*(?:business\s*)?days?', delivery_text) if delivery_text else None
                    if days_match:
                        shipping_info["delivery_days_min"] = int(days_match.group(1))
                        shipping_info["delivery_days_max"] = int(days_match.group(2))
                    
        except Exception as e:
            print(f"      Error extracting shipping info: {e}")
        
        return shipping_info
    
    # ========== PAYMENT INFO EXTRACTION ==========
    async def extract_payment_info(self, page: Page) -> Dict[str, Any]:
        info = {"methods": [], "text": ""}
        try:
            ta_text = await self.safe_get_text(page, ['.ta-semi'])
            info["text"] = ta_text
            if "secure payments" in ta_text.lower():
                info["methods"].append("Trade Assurance")
        except:
            pass
        return info
    
    # ========== SOCIAL PROOF EXTRACTION ==========
    async def extract_social_proof(self, page: Page) -> Dict[str, Any]:
        proof = {"review_count": "", "average_rating": "", "order_count_text": "", "units_sold_text": ""}
        try:
            proof["review_count"] = await self.safe_get_text(page, ['.detail-review-item'])
            proof["order_count_text"] = await self.safe_get_text(page, ['.order-count', '.sold-count'])
        except:
            pass
        return proof
    
    # ========== CERTIFICATIONS EXTRACTION ==========
    async def extract_certifications(self, page: Page) -> List[str]:
        certs = []
        try:
            verified = await self.safe_get_text(page, ['[data-testid="seller-overview-card-badge"]'])
            if verified:
                certs.append(verified)
        except:
            pass
        return certs
    
    # ========== SAMPLE AVAILABLE ==========
    async def has_sample_available(self, page: Page) -> bool:
        try:
            text = await self.safe_get_text(page, ['.module_supplier_customization'])
            return "sample" in text.lower()
        except:
            return False
    
    # ========== HELPER METHODS ==========
    async def safe_get_text(self, page: Page, selectors: List[str]) -> str:
        for selector in selectors:
            try:
                elem = page.locator(selector).first
                if await elem.count() > 0:
                    return await elem.inner_text()
            except:
                continue
        return ""
    
    def print_summary(self):
        total_time = time.time() - self.start_time if self.start_time else 0
        
        print("\n" + "="*70)
        print("📊 SCRAPING SUMMARY")
        print("="*70)
        print(f"✅ Successful: {self.stats['successful']}")
        print(f"❌ Failed: {self.stats['failed']}")
        print(f"⏱️  Total time: {total_time/60:.1f} minutes")
        
        if self.stats['successful'] > 0:
            avg_time = total_time / self.stats['successful']
            print(f"📈 Average time per product: {avg_time:.1f} seconds")
        
        # Show classification stats from results
        results = load_existing_results()
        if results:
            print(f"\n📊 Classification Summary:")
            
            # Gender distribution
            gender_counts = {}
            for r in results[-self.stats['successful']:]:  # Only new results
                gender = r.get('gender', 'N/A')
                gender_counts[gender] = gender_counts.get(gender, 0) + 1
            if gender_counts:
                print(f"   Gender: {gender_counts}")
            
            # Audience distribution
            audience_counts = {}
            for r in results[-self.stats['successful']:]:
                audience = r.get('audience', 'N/A')
                audience_counts[audience] = audience_counts.get(audience, 0) + 1
            if audience_counts:
                print(f"   Audience: {audience_counts}")
        
        print(f"\n💾 Results saved to: {RESULTS_FILE}")
        print("="*70)


# ============================================
# MAIN EXECUTION
# ============================================

async def main():
    # Your product URLs (add as many as you want)
    product_urls = [
    "https://www.alibaba.com/product-detail/Non-toxic-Harmless-Double-sided-Yellow_1601421857899.html",
"https://www.alibaba.com/product-detail/Low-Price-Non-toxic-Harmless-Yellow_1601421945302.html",
"https://www.alibaba.com/product-detail/OEM-Customize-Silicone-Glass-Bottle-Wholesale_1601562021916.html",
"https://www.alibaba.com/product-detail/Hot-Sales-Blackout-Roller-Blinds-Office_706169935.html",
"https://www.alibaba.com/product-detail/Factory-Customization-Carton-Steel-Heavy-duty_1601606041060.html",
"https://www.alibaba.com/product-detail/Shaving-Kit-for-Men-Badger-Shaving_10000012530525.html",
"https://www.alibaba.com/product-detail/Men-s-Grooming-Set-Stainless-Steel_1601736402353.html",
"https://www.alibaba.com/product-detail/Wholesale-Men-Skin-Care-Set-Body_1600731590858.html",
"https://www.alibaba.com/product-detail/OEM-Men-s-Beard-Grooming-Care_1600644447682.html",
"https://www.alibaba.com/product-detail/Wooden-Shaving-Set-for-Men-s_10000012546225.html",
"https://www.alibaba.com/product-detail/Soft-Professional-Men-Beard-Brush-Set_11000009319873.html",
"https://www.alibaba.com/product-detail/Promotional-Beard-Care-Growth-Grooming-Kit_62385195073.html",
"https://www.alibaba.com/product-detail/6-Difference-Beard-Micro-Needle-Roller_1601384328485.html",
"https://www.alibaba.com/product-detail/Men-s-Cut-Throat-Straight-Edge_10000039183263.html",
"https://www.alibaba.com/product-detail/Madhav-Metal-Industries-Men-s-Grooming_10000027921686.html",
"https://www.alibaba.com/product-detail/Customized-Shaving-razor-with-5-Layer_1601691350608.html",
"https://www.alibaba.com/product-detail/BENJIE-4K-64MP-Popular-Compact-Digital_1601517747113.html",
"https://www.alibaba.com/product-detail/High-Quality-10-Piece-Cookware-Set_1601274825995.html",
"https://www.alibaba.com/product-detail/Pure-White-Outdoor-Sports-Riding-Racing_1601370109214.html",
"https://www.alibaba.com/product-detail/LVD293-Wholesales-Famous-Brand-Sports-Bra_1601609025359.html",
"https://www.alibaba.com/product-detail/Hot-Selling-C-70D-Digital-Camera_1601708489569.html",
"https://www.alibaba.com/product-detail/1L-TPU-Ultralight-Foldable-Eco-Friendly_11000029070207.html",
"https://www.alibaba.com/product-detail/2025-New-Design-Ultra-5G-Smartphone_1601538921279.html",
"https://www.alibaba.com/product-detail/Rotary-Kiln-Plant-for-Gypsum-Calcination_1601691371508.html",
"https://www.alibaba.com/product-detail/Custom-Logo-Women-s-Solid-Colour_1601294631326.html",
"https://www.alibaba.com/product-detail/Beambox-1-53inch-Digital-Photo-Badge_1601656224423.html",
"https://www.alibaba.com/product-detail/Custom-Logo-Quick-Dry-Football-Tracksuits_1601610332125.html",
"https://www.alibaba.com/product-detail/Luxury-Modern-Chesterfield-Sofa-Set-High_1601603534748.html",
"https://www.alibaba.com/product-detail/Modern-Style-Household-Multi-Purpose-Kitchen_1601235519012.html",
"https://www.alibaba.com/product-detail/Men-s-Clothing-2026-Spring-Autumn_1601709717682.html",
"https://www.alibaba.com/product-detail/Lightweight-Simple-Cheap-Down-Camping-Quilt_62010550343.html",
"https://www.alibaba.com/product-detail/Wholesale-Original-S24U-Smartphone-5G-Ultra_1601537741925.html",
"https://www.alibaba.com/product-detail/Wholesale-Different-Functions-Comfortable-PU-Leather_1601043097805.html",
"https://www.alibaba.com/product-detail/Soccer-Jersey-Durable-Fabric-Men-s_1601678978805.html",
"https://www.alibaba.com/product-detail/Factory-Wholesale-Luxury-Decorative-Soft-Blackout_1601274604847.html",
"https://www.alibaba.com/product-detail/Modern-Office-Furniture-Table-Executive-Office_1600909375013.html",
"https://www.alibaba.com/product-detail/New-Smart-Ring-Digital-BT-Control_11000022396925.html",
"https://www.alibaba.com/product-detail/FREE-DESIGN-MOCK-UP-Custom-Logo_1601204154095.html",
"https://www.alibaba.com/product-detail/Free-Shipping-High-Quality-S25-Ultra_1601524100265.html",
"https://www.alibaba.com/product-detail/Dr-Wool-New-Arrival-Bedding-Set_1601404622623.html",
"https://www.alibaba.com/product-detail/Hot-Selling-Good-Quality-Folding-Camping_1601296264345.html",
"https://www.alibaba.com/product-detail/Wholesale-High-quality-220GSM-Men-s_1601763939035.html",
"https://www.alibaba.com/product-detail/Yoga-Active-Wear-Set-Ropa-De_1600714640510.html",
"https://www.alibaba.com/product-detail/Indoor-Steel-Cricket-Set-Foldable-Stumps_10000042299320.html",
"https://www.alibaba.com/product-detail/Customizable-Modern-Minimalist-Style-Environmentally-Friendly_1601738257525.html",
"https://www.alibaba.com/product-detail/UEMON-Smart-Home-Automation-Radars-IPS_11000020734944.html",
"https://www.alibaba.com/product-detail/Portable-4K-Digital-Camera-Autofocus-10X_1601283198226.html",
"https://www.alibaba.com/product-detail/Unisex-Fashion-Printed-Breathable-Reversible-Waterproof_1601521468223.html",
"https://www.alibaba.com/product-detail/Hot-Selling-Women-Seamless-Yoga-Sets_1601757885071.html",
"https://www.alibaba.com/product-detail/Zayshine-Italian-Modern-Luxury-White-Linen_1601671060668.html",
"https://www.alibaba.com/product-detail/19PCS-Kitchen-Utensils-Set-Non-Stick_1601208983905.html",
"https://www.alibaba.com/product-detail/Janya-2-Piece-Gym-Fitness-Women_1601512592155.html",
"https://www.alibaba.com/product-detail/Advanced-Training-Cricket-Ball-With-Balanced_11000032703951.html",
"https://www.alibaba.com/product-detail/Wholesale-Outdoor-Fitness-Running-Grip-Socks_1601201950918.html",
"https://www.alibaba.com/product-detail/SOS-Wilderness-Survival-Equipment-Camping-Outdoor_11000031754526.html",
"https://www.alibaba.com/product-detail/Digital-Camera-35mm-Colorful-Reusable-Film_62554253556.html",
"https://www.alibaba.com/product-detail/Factory-Price-S24-Ultra-16GB-1TB_1601623343259.html",
"https://www.alibaba.com/product-detail/Modern-Luxury-Chairman-Timber-Bookcase-And_1601694079645.html",
"https://www.alibaba.com/product-detail/Light-Weight-Classic-Type-Hiking-Tent_12000002407803.html",
"https://www.alibaba.com/product-detail/Modular-High-Partition-Customizable-Office-Cubicle_1601685814166.html",
"https://www.alibaba.com/product-detail/Wholesale-Well-Designed-Men-s-for_11000018485582.html",
"https://www.alibaba.com/product-detail/15-pcs-Cookware-Set-w-Lids_1601196175676.html",
"https://www.alibaba.com/product-detail/Cross-Border-Men-s-Clothing-European_1601728807266.html",
"https://www.alibaba.com/product-detail/Modern-Office-L-shaped-Boss-Desk_1600888237222.html",
"https://www.alibaba.com/product-detail/Custom-Wholesale-19-Kitchenware-Set-Silicone_1600924898788.html",
"https://www.alibaba.com/product-detail/New-Fashion-Design-Summer-Casual-Breathable_1600908085918.html",
"https://www.alibaba.com/product-detail/Professional-10X-Optical-Zoom-Auto-Focus_1601659266855.html",
"https://www.alibaba.com/product-detail/Customized-Men-s-Cross-Border-Winter_1601638430155.html",
"https://www.alibaba.com/product-detail/YETFUL-YETFUL-Custom-Logo-Non-Slip_1601717768097.html",
"https://www.alibaba.com/product-detail/TREGUI-TRE-028-Fun-Tennis-Training_1601740539458.html",
"https://www.alibaba.com/product-detail/Custom-Sport-Training-Jackets-Windproof-Soccer_1601749222414.html",
"https://www.alibaba.com/product-detail/English-Willow-Wholesale-Price-Top-Grade_10000031538997.html",
"https://www.alibaba.com/product-detail/Ultralight-Eco-friendly-Portable-Outdoor-Camping_11000033571022.html",
"https://www.alibaba.com/product-detail/Export-8-Piece-Stainless-Steel-Non_1601000741190.html",
"https://www.alibaba.com/product-detail/New-Winter-Ski-Jacket-for-Men_1601612098605.html",
"https://www.alibaba.com/product-detail/2L-3L-5L-8L-10L-15L_60846729630.html",
"https://www.alibaba.com/product-detail/S24-Ultra-5G-Smartphone-512GB-6_1601536225473.html",
"https://www.alibaba.com/product-detail/2025-2026-Football-Sportswear-Customized-Basketball_1601612178842.html",
"https://www.alibaba.com/product-detail/Ton-Super-English-Willow-Cricket-Bat_10000014140026.html",
"https://www.alibaba.com/product-detail/Factory-Direct-Wholesale-Luxury-Modern-Wooden_1600344397151.html",
"https://www.alibaba.com/product-detail/SK1286-Women-s-Cotton-Wide-Leg_1601300928367.html",
"https://www.alibaba.com/product-detail/Men-s-Clothing-Customized-Men-s_1601459132004.html",
"https://www.alibaba.com/product-detail/Custom-Style-Yoga-Socks-Sports-Casual_1601608051505.html",
"https://www.alibaba.com/product-detail/Custom-Hooded-Outdoor-Varsity-Sportswear-Athletic_1601712018625.html",
"https://www.alibaba.com/product-detail/Wholesale-Thailand-Sport-Coat-Blank-and_1600679586794.html",
"https://www.alibaba.com/product-detail/10-Piece-Kitchen-Gadget-Set-Storage_1601516033812.html",
"https://www.alibaba.com/product-detail/7-Piece-Comforter-Set-Striped-Modern_10000034292346.html",
"https://www.alibaba.com/product-detail/Customizable-Organic-Muslin-Cotton-Gauze-Waffle_1601762565641.html",
"https://www.alibaba.com/product-detail/100-Cotton-Solid-color-Terry-Cloth_1601660367259.html",
"https://www.alibaba.com/product-detail/Custom-Design-Men-s-UPF50-UV_1601585448464.html",
"https://www.alibaba.com/product-detail/Premium-Embroidered-Throw-Blanket-Cotton-Polyester_1601726627244.html",
"https://www.alibaba.com/product-detail/2022-New-Product-Turkish-Cotton-Weave_1600087542143.html",
"https://www.alibaba.com/product-detail/S25-Ultra-Smart-Cell-Phone-Wi_1601539193915.html",
"https://www.alibaba.com/product-detail/Cross-border-Best-selling-Football-Socks_1601715151044.html",
"https://www.alibaba.com/product-detail/Foyer-Metal-Shoe-Storage-Cabinet-Multi_1601748934235.html",
"https://www.alibaba.com/product-detail/Durable-PVC-Plastic-Cricket-Stumps-with_10000029780015.html",
"https://www.alibaba.com/product-detail/Cross-Border-Men-s-Clothing-European_1601737847414.html",
"https://www.alibaba.com/product-detail/Free-Shipping-Original-Smart-Phone-S25_1601524051384.html",
"https://www.alibaba.com/product-detail/U-Shape-Boneless-Sectional-Modular-Black_1601689204451.html",
"https://www.alibaba.com/product-detail/Smart-Ring-With-LED-Display-Screen_1601683207083.html",
"https://www.alibaba.com/product-detail/Custom-Gym-Fitness-Set-One-Piece_1600898619210.html",
"https://www.alibaba.com/product-detail/Newest-Smart-Translation-Pen-With-Touch_1600807947866.html",
"https://www.alibaba.com/product-detail/Mountaineering-Clothing-Outdoor-Sports-Anti-static_1601578674386.html",
"https://www.alibaba.com/product-detail/Factory-wholesale-10pcs-14Pcs-Aluminum-Cookware_1601003994785.html",
"https://www.alibaba.com/product-detail/Professional-Foldable-Camping-Chair-Folding-Stool_1601297495983.html",
"https://www.alibaba.com/product-detail/Hiking-Camping-Supplies-Hiking-Sticks-Mountain_11000029448811.html",
"https://www.alibaba.com/product-detail/Bath-Towel-Set-100-Cotton-Yarn_1601627194240.html",
"https://www.alibaba.com/product-detail/Heavy-Thick-7-Aluminum-Pot-Cookware_1601060236755.html",
"https://www.alibaba.com/product-detail/Men-s-Jackets-Spring-and-Autumn_1601674369253.html",
"https://www.alibaba.com/product-detail/HAD-2024-Most-Popular-NEW-Men_1601449275304.html",
"https://www.alibaba.com/product-detail/S24-Smart-Cell-Phone-120Hz-Adaptive_1601534232174.html",
"https://www.alibaba.com/product-detail/Hot-Selling-S24-ULTRA-Original-16GB_1601634123420.html",
"https://www.alibaba.com/product-detail/Men-s-XL-Active-Bottoms-Lightweight_1601410609699.html",
"https://www.alibaba.com/product-detail/Smart-Watch-Technology-and-Accessories-M72143634_12000000402535.html",
"https://www.alibaba.com/product-detail/Low-MOQ-Men-Trousers-Figure-Flattering_1601700156874.html",
"https://www.alibaba.com/product-detail/Breathable-Women-s-Yoga-Wear-Set_1601687270750.html",
"https://www.alibaba.com/product-detail/Trusted-Supplier-Bulk-3-2-Touch_1601564000464.html",
"https://www.alibaba.com/product-detail/Wifi-Solar-Camera-Outdoor-Build-in_1601420917066.html",
"https://www.alibaba.com/product-detail/APEX-Panoramic-Padre-Tennis-Court-Roof_1601763337439.html",
"https://www.alibaba.com/product-detail/Wholesale-Quilt-Soft-Tassel-Woven-Breathe_1601255586781.html",
"https://www.alibaba.com/product-detail/New-Popular-Custom-Home-Textiles-High_1601690795342.html",
"https://www.alibaba.com/product-detail/Home-Textile-Microfiber-Easy-Care-Modern_1600871431200.html",
"https://www.alibaba.com/product-detail/Wholesale-new-Deodorant-custom-LOGO-sports_1600165964551.html",
"https://www.alibaba.com/product-detail/FOR-Original-New-for-G7-X_1601741027535.html",
"https://www.alibaba.com/product-detail/Ultralight-Duck-Filled-Nylon-Outdoor-Hiking_11000028110342.html",
"https://www.alibaba.com/product-detail/180-degree-Flip-Screen-Autofocus-Video_1601587760772.html",
"https://www.alibaba.com/product-detail/Wholesale-Men-Utah-Ice-Hockey-Jerseys_1601579258218.html",
"https://www.alibaba.com/product-detail/2025-Ultra-High-Speed-S24-Ultra_1601536257795.html",
"https://www.alibaba.com/product-detail/Best-Selling-High-Accuracy-Crew-Socks_1601517781762.html",
"https://www.alibaba.com/product-detail/2026-AI-Smart-Glasses-Touch-Control_11000031628664.html",
"https://www.alibaba.com/product-detail/Advanced-Mystery-Gift-Boxes-for-Smart_11000033079497.html",
"https://www.alibaba.com/product-detail/Black-Metal-Shoe-Rack-With-Door_1601749255899.html",
"https://www.alibaba.com/product-detail/Sport-Crew-Socks-Custom-100-Cotton_1601617537426.html",
"https://www.alibaba.com/product-detail/Smart-Watch-Technology-and-Accessories-M72143634_12000000503528.html",
"https://www.alibaba.com/product-detail/Casual-Wide-Leg-Flared-Joggers-Embroidered_1601764617503.html",
"https://www.alibaba.com/product-detail/Men-s-Lightweight-Breathable-Polyester-Cotton_1601416770980.html",
"https://www.alibaba.com/product-detail/Modern-Luxury-L-U-Shaped-Sectional_1601540420402.html",
"https://www.alibaba.com/product-detail/Ultralight-2-3-Person-Backpacking-Tent_11000033282650.html",
"https://www.alibaba.com/product-detail/Summer-Sustainable-Recycled-Polyester-Nylon-Stretch_1601709023830.html",
"https://www.alibaba.com/product-detail/New-Winter-Jacket-Unisex-Workouts-Sports_1601581207439.html",
"https://www.alibaba.com/product-detail/Color-blocking-for-Women-U-shaped_1601598289923.html",
"https://www.alibaba.com/product-detail/Outdoor-Motion-Activated-WiFi-Bluetooth-Control_1601258173815.html",
"https://www.alibaba.com/product-detail/Custom-Graphic-Printing-Blank-Black-White_1600533756634.html",
"https://www.alibaba.com/product-detail/Clothing-Manufacturers-Custom-Men-Women-s_1601397559416.html",
"https://www.alibaba.com/product-detail/Custom-High-End-Men-s-Baggy_1601703104347.html",
"https://www.alibaba.com/product-detail/PASUXI-High-Elasticity-Quick-Dry-Men_10000040323357.html",
"https://www.alibaba.com/product-detail/wholesale-hot-selling-low-moq-football_1601277489627.html",
"https://www.alibaba.com/product-detail/Luxury-Eco-Friendly-Flannel-Blanket-Knitted_1601568485898.html",
"https://www.alibaba.com/product-detail/New-product-ideas-2022-home-and_1600578335771.html",
"https://www.alibaba.com/product-detail/Rotary-Kiln-for-Cement-Clinker-LECA_1601462176784.html",
"https://www.alibaba.com/product-detail/Wholesale-Gumten-Brand-Lightweight-Jogging-Ultra_11000032445010.html",
"https://www.alibaba.com/product-detail/Sg-Ss-Ca-gm-Hardball-Hard_1601714916258.html",
"https://www.alibaba.com/product-detail/Black-Men-s-Summer-Loose-Ankle_1601711329769.html",
"https://www.alibaba.com/product-detail/PFAS-Free-Envases-Biodegradable-Disposable-Take_1600352224646.html",
"https://www.alibaba.com/product-detail/Aoyema-Women-s-Sports-Wear-Breathable_1601572502942.html",
"https://www.alibaba.com/product-detail/Wooden-Cricket-Spring-Wickets-3-Stumps_10000002408054.html",
"https://www.alibaba.com/product-detail/Custom-Men-s-Polo-T-Shirt_1601369023006.html",
"https://www.alibaba.com/product-detail/Custom-Men-s-Classic-LOGO-Winter_1601628518643.html",
"https://www.alibaba.com/product-detail/White-Lul-Design-Sports-Men-Casual_1601582832802.html",
"https://www.alibaba.com/product-detail/Outdoor-Camping-1-8KG-Lightweight-Hooded_11000022893098.html",
"https://www.alibaba.com/product-detail/Cricket-Kit-Set-Includes-Jersey-and_1601543068879.html",
"https://www.alibaba.com/product-detail/GUANGRUI-TENT-6061-T6-Extended-Type_1601769172622.html",
"https://www.alibaba.com/product-detail/Transparent-Acrylic-Round-Coffee-Table-Clear_1601623219139.html",
"https://www.alibaba.com/product-detail/Free-Sample-Low-MOQ-Custom-Made_1601459909081.html",
"https://www.alibaba.com/product-detail/Ultra-High-Resolution-S25-Camera-Professional_1601536410378.html",
"https://www.alibaba.com/product-detail/Compports-20-30mmHg-Nylon-Elastic-Knee_1601439336711.html",
"https://www.alibaba.com/product-detail/Hot-Selling-Domestic-Kitchen-Non-Stick_1601166045711.html",
"https://www.alibaba.com/product-detail/Custom-Logo-Breathable-Cotton-Men-s_1601454402559.html",
"https://www.alibaba.com/product-detail/Modern-Wooden-Office-Desk-With-Storage_1601758022701.html",
"https://www.alibaba.com/product-detail/Modern-Simple-Corner-Sectional-Sofa-for_1601544876866.html",
"https://www.alibaba.com/product-detail/2024-S24-Ultra-5G-Smartphone-16GB_1601252217612.html",
"https://www.alibaba.com/product-detail/Modern-Style-Leather-Living-Room-Sofas_1600878194318.html",
"https://www.alibaba.com/product-detail/2024-Hot-40oz-Adventure-Leakproof-Vacuum_1600755708987.html",
"https://www.alibaba.com/product-detail/Quality-assurance-Hot-sale-Heat-resistant_1601277997699.html",
"https://www.alibaba.com/product-detail/Manufacturers-Wholesale-Custom-Home-Textile-Solid_1601158868695.html",
"https://www.alibaba.com/product-detail/Factory-Direct-Sale-Strong-and-Durable_11000022414938.html",
"https://www.alibaba.com/product-detail/Wholesale-Customized-Cloth-of-Force-Polyester_1600694036154.html",
"https://www.alibaba.com/product-detail/Professional-Foldable-Camping-Chair-Folding-Stool_1601386669924.html",
"https://www.alibaba.com/product-detail/Home-Textile-Super-Soft-Printed-Flannel_60681838251.html",
"https://www.alibaba.com/product-detail/In-Stock-Good-100-Soild-Color_1601383925498.html",
"https://www.alibaba.com/product-detail/New-Trending-2025-Health-Sleep-tracker_11000022413903.html",
"https://www.alibaba.com/product-detail/Tuya-Wireless-Wifi-Smart-App-Remote_1600969711190.html",
"https://www.alibaba.com/product-detail/12-Level-Plastic-Shoe-Organizer-Cabinet_1601401930760.html",
"https://www.alibaba.com/product-detail/1-0L-Ultralight-Collapsible-Outdoor-Survive_11000029002292.html",
"https://www.alibaba.com/product-detail/Blank-Embroidery-logo-Men-s-Polo_1601722181807.html",
"https://www.alibaba.com/product-detail/Wholesale-HIgh-Quality-Customize-Wooden-Cricket_11000029313491.html",
"https://www.alibaba.com/product-detail/Comfortable-DUCK-Down-Mummy-Sleeping-Bag_11000028080456.html",
"https://www.alibaba.com/product-detail/Multi-Functional-Smart-Bracelet-For-Kids_60776462627.html",
"https://www.alibaba.com/product-detail/Adult-Wave-Arrow-Pointed-Non-Slip_1601561619428.html",
"https://www.alibaba.com/product-detail/Cotton-Scan-Unisex-Men-s-T_1601757179375.html",
"https://www.alibaba.com/product-detail/Bubaba-Bohemian-Printed-Beige-Tassel-Decorative_1601489046209.html",
"https://www.alibaba.com/product-detail/Hot-Top-Quality-Cheap-Customized-logo_11000010461493.html",
"https://www.alibaba.com/product-detail/Manufacturer-High-Quality-7-Piece-Metal_1601367090546.html",
"https://www.alibaba.com/product-detail/Custom-Designed-Cotton-Woven-Tapestry-Blanket_1601402114763.html",
"https://www.alibaba.com/product-detail/Kids-Leisure-Outdoor-Wear-Bottoms-Unisex_11000034684540.html",
"https://www.alibaba.com/product-detail/New-Sport-SmartWatch-K56-Pro-Men_11000020019060.html",
"https://www.alibaba.com/product-detail/Green-Metal-Shoe-Rack-Cabinet-With_1601749243526.html",
"https://www.alibaba.com/product-detail/L-Shaped-Pedestal-Desk-With-Storage_1601758027056.html",
"https://www.alibaba.com/product-detail/22GB-2TB-S26-Ultra-Android-16_1601514358587.html",
"https://www.alibaba.com/product-detail/Custom-Kitchen-Tea-Towels-Home-Textiles_1600918423757.html",
"https://www.alibaba.com/product-detail/XW-AWX8002-2-ACK8002-Gym-Clothing_1601707941839.html",
"https://www.alibaba.com/product-detail/Gym-Activewear-Workout-Sports-Yoga-Wear_1601427205254.html",
"https://www.alibaba.com/product-detail/Wholesale-Trendy-Design-Cricket-Pads-Custom_11000034657857.html",
"https://www.alibaba.com/product-detail/Wholesale-Running-Custom-Unisex-Sports-Socks_1601608757544.html",
"https://www.alibaba.com/product-detail/Customized-High-Quality-Modern-Wooden-Office_1601397973439.html",
"https://www.alibaba.com/product-detail/Custom-Logo-High-Waist-Fitness-Six_1601570385194.html",
"https://www.alibaba.com/product-detail/Basket-Collapsible-Colander-Set-of-2_1600458333575.html",
"https://www.alibaba.com/product-detail/Custom-Ladies-Golf-Clothing-220G-75_1601645097838.html",
"https://www.alibaba.com/product-detail/High-Quality-100-Cotton-Men-s_1601562664355.html",
"https://www.alibaba.com/product-detail/12-Piece-Stainless-Steel-Non-Stick_1601174780394.html",
"https://www.alibaba.com/product-detail/Top-Selling-Power-Shot-G7-X_1601681546223.html",
"https://www.alibaba.com/product-detail/Luxury-100-Polyester-Designer-Home-Textile_1601011495081.html",
"https://www.alibaba.com/product-detail/Unitree-Go2-Pro-Robot-Dog-Quadruped_1601608989767.html",
"https://www.alibaba.com/product-detail/S25-Ultra-5G-enabled-Smart-Cell_1601538994304.html",
"https://www.alibaba.com/product-detail/Smart-Watch-Technology-and-Accessories-M72674634_12000000546430.html",
"https://www.alibaba.com/product-detail/Breathable-Waterproof-Hunting-Apparel-Winter-Hunting_1601548768478.html",
"https://www.alibaba.com/product-detail/JAKIJAYI-European-and-American-Men-s_1601300947381.html",
"https://www.alibaba.com/product-detail/Polartec-Winter-Outdoor-Sports-Overalls-for_1600796692437.html",
"https://www.alibaba.com/product-detail/Solid-Quilted-Microfiber-3-Piece-Bedding_1601706140046.html",
"https://www.alibaba.com/product-detail/Custom-Clothing-Casual-Thin-Solid-Color_1601043135640.html",
"https://www.alibaba.com/product-detail/6K-High-definition-Handheld-Digital-Camera_1601623635944.html",
"https://www.alibaba.com/product-detail/Atunus-Leather-Sofa-Luxury-Couches-7_1600544117034.html",
"https://www.alibaba.com/product-detail/RTS-35-38-40CM-3-Pot_1601395828267.html",
"https://www.alibaba.com/product-detail/Commercial-Juicer-Heavy-Duty-Commercial-High_1601762178642.html",
"https://www.alibaba.com/product-detail/6-3-Square-Meters-Recording-Pod_1600472512469.html",
"https://www.alibaba.com/product-detail/Portable-Waterproof-Nylon-Camping-Sleeping-Bags_11000030596446.html",
"https://www.alibaba.com/product-detail/Manufacturer-Professional-Cotton-Breathable-Deodorant-Anti_1601612115580.html",
"https://www.alibaba.com/product-detail/Children-s-Instant-Print-Camera-Kids_1601525775966.html",
"https://www.alibaba.com/product-detail/Fabric-Soft-Dry-Knitting-Process-Best_1601286244035.html",
"https://www.alibaba.com/product-detail/AI-Smart-Glasses-M89-Dual-Optical_1601723915917.html",
"https://www.alibaba.com/product-detail/Can-on-RF15-35mm-F2-8_1601515522072.html",
"https://www.alibaba.com/product-detail/Portable-Workstation-Luxury-Office-Furniture-Laptop_1601046999202.html",
"https://www.alibaba.com/product-detail/Wholesale-for-for-G7-X-Mark_1601630573645.html",
"https://www.alibaba.com/product-detail/Customizable-Kitchen-Cook-Pots-and-Pans_1600992882949.html",
"https://www.alibaba.com/product-detail/Modern-Minimalist-Ultra-Thin-Three-Layer_1601617496641.html",
"https://www.alibaba.com/product-detail/Large-Capacity-12L-Outdoor-Camping-Handheld_1601578394607.html",
"https://www.alibaba.com/product-detail/Factory-Wholesale-Customization-Rectangular-Kitchen-Thick_1601138347371.html",
"https://www.alibaba.com/product-detail/Modern-Design-Wooden-Mobile-Filing-Cabinet_1601716105617.html",
"https://www.alibaba.com/product-detail/Winait-NVC400-96MP-Retro-Style-Night_1601524040311.html",
"https://www.alibaba.com/product-detail/Wholesale-100-Cotton-Crew-Socks-Thick_1601638652656.html",
"https://www.alibaba.com/product-detail/7-Inch-Touch-Screen-Smart-Home_1601027991458.html",
"https://www.alibaba.com/product-detail/Custom-Pure-English-Willow-Cricket-Bat_11000032672500.html",
"https://www.alibaba.com/product-detail/wholesale-professional-men-s-football-grip_1600972100993.html",
"https://www.alibaba.com/product-detail/2025-Ultra-High-Speed-S25Ultra-5G_1601534112543.html",
"https://www.alibaba.com/product-detail/Kitchen-Pots-Products-Items-Wares-Wholesale_1601285470383.html",
"https://www.alibaba.com/product-detail/Retro-Corduroy-Fabric-Pure-Sponge-No_1601495456773.html",
"https://www.alibaba.com/product-detail/OEM-Tapestry-Clothing-Manufacturer-MOQ-1pc_1601216817669.html",
"https://www.alibaba.com/product-detail/Fashion-Causal-Business-Style-Mens-Coat_60819406882.html",
"https://www.alibaba.com/product-detail/High-Quality-Modern-Office-Furniture-Walnut_1601747247477.html",
"https://www.alibaba.com/product-detail/A-Simple-Two-Door-Four-Person_1601741949778.html",
"https://www.alibaba.com/product-detail/Used-C-Anon-G7-X-Touchscreen_1601680072995.html",
"https://www.alibaba.com/product-detail/Smart-Watch-Technology-and-Accessories-M72134534_12000000546485.html",
"https://www.alibaba.com/product-detail/250w-Led-Lighting-for-Padel-Courts_1601574076549.html",
"https://www.alibaba.com/product-detail/New-Arrival-S26-Ultra-Smart-Phone_1601578571116.html",
"https://www.alibaba.com/product-detail/100-Cotton-Plus-Size-Men-s_1600450118773.html",
"https://www.alibaba.com/product-detail/NBD-Camera-2000mAh-Lithium-Battery-16x_1601293122209.html",
"https://www.alibaba.com/product-detail/Super-Thin-Digital-Camera-4K-Portable_1601623699759.html",
"https://www.alibaba.com/product-detail/Solid-Color-With-Beautiful-Embossed-Design_1601423736995.html",
"https://www.alibaba.com/product-detail/LINGTU-Wholesale-sports-non-slip-socks_1600462975607.html",
"https://www.alibaba.com/product-detail/Premium-Nylon-4-Season-Sleeping-Bags_11000030618438.html",
"https://www.alibaba.com/product-detail/Custom-Made-Men-s-Holidays-Casual_1601691664659.html",
"https://www.alibaba.com/product-detail/S25-Ultra-5G-Smart-Dual-SIM_1601539212879.html",
"https://www.alibaba.com/product-detail/Microfiber-Cute-Household-Hand-Towel-Modern_1601628593195.html",
"https://www.alibaba.com/product-detail/95-New-Sonys-A6700-Mirrorless-4K_1601706709129.html",
"https://www.alibaba.com/product-detail/Smartphone-S24-Ultra-5g-Mobile-Phone_1601536225070.html",
"https://www.alibaba.com/product-detail/Italian-High-Quality-Multi-Functional-Modern_1601439597975.html",
"https://www.alibaba.com/product-detail/Cool-Touch-Men-s-Lightweight-Ribbed_1601467527979.html",
"https://www.alibaba.com/product-detail/2025-New-Ultra-High-Speed-S24_1601536316377.html",
"https://www.alibaba.com/product-detail/CEO-Wood-Table-Modular-Office-Furniture_1601602975438.html",
"https://www.alibaba.com/product-detail/Any-Pot-Can-Used-Single-Infrared_11000029898186.html",
"https://www.alibaba.com/product-detail/Comfortable-Cricket-Uniform-and-Jersey-with_11000034546574.html",
"https://www.alibaba.com/product-detail/HOSA-Lightweight-Family-Size-Tent-Hot_11000032072041.html",
"https://www.alibaba.com/product-detail/Women-s-Tennis-Skirts-Outdoor-Skirt_1601411581396.html",
"https://www.alibaba.com/product-detail/Custom-Professional-Sports-Socks-Mid-Cut_1601563902911.html",
"https://www.alibaba.com/product-detail/Smart-Watch-Technology-and-Accessories-M72134434_12000000510527.html",
"https://www.alibaba.com/product-detail/Office-Furniture-Comfortable-Modern-Computer-Executive_1600906152584.html",
"https://www.alibaba.com/product-detail/Camping-Hiking-TSA-Approved-Leak-proof_11000029335907.html",
"https://www.alibaba.com/product-detail/Tennis-Dress-Autumn-Outdoor-Sports-Wear_1601673382188.html",
"https://www.alibaba.com/product-detail/220V-Smart-Home-Automation-Smartphone-App_60753012069.html",
"https://www.alibaba.com/product-detail/Hot-Sale-European-American-Men-s_1600465500439.html",
"https://www.alibaba.com/product-detail/Fashionable-Simple-Men-s-Stand-up_1601641504896.html",
"https://www.alibaba.com/product-detail/Luxury-Boss-Desk-Manager-Modern-and_1601732792100.html",
"https://www.alibaba.com/product-detail/Men-s-Clothing-Men-s-Casual_1601451334592.html",
"https://www.alibaba.com/product-detail/Custom-Wall-Mounted-Nightstand-Drawer-Particleboard_1601740706338.html",
"https://www.alibaba.com/product-detail/Workstation-Modern-Work-Ceo-Executive-Office_1601198801190.html",
"https://www.alibaba.com/product-detail/White-Flowers-Plants-Botanical-Cosy-Elegant_1601755124393.html",
"https://www.alibaba.com/product-detail/long-distance-dual-sensor-IP-thermal_60611198285.html",
"https://www.alibaba.com/product-detail/Best-rated-Winter-Waterproof-Cold-Weather_11000029716546.html",
"https://www.alibaba.com/product-detail/Custom-Scrunch-Sports-Bra-High-Waisted_1601461365690.html",
"https://www.alibaba.com/product-detail/Solid-Color-Leg-Sleeve-Running-Sports_1600466814312.html",
"https://www.alibaba.com/product-detail/Portable-Foldable-Fresh-Water-Filter-Bag_11000029050233.html",
"https://www.alibaba.com/product-detail/Wholesale-100-Polyester-Breathable-Digital-Soccer_1601751784909.html",
"https://www.alibaba.com/product-detail/Custom-Anti-Slip-Long-Football-Socks_1601651329515.html",
"https://www.alibaba.com/product-detail/100-Polyester-Professional-Factory-Breathable-Outdoors_1600554889373.html",
"https://www.alibaba.com/product-detail/OEM-Wholesale-100-Egyptian-Cotton-Bath_62337360151.html",
"https://www.alibaba.com/product-detail/Spring-Autumn-Fashion-Leisure-New-Men_1601474951998.html",
"https://www.alibaba.com/product-detail/New-Design-Smart-Home-Kit-Golden_11000007077332.html",
"https://www.alibaba.com/product-detail/Wholesale-Breathable-Quality-Football-Jersey-Outdoor_1601605747674.html",
"https://www.alibaba.com/product-detail/Custom-Women-s-Fitness-Active-Wear_1601460761189.html",
"https://www.alibaba.com/product-detail/Manufacturer-Direct-Supply-Industrial-Survival-First_1601592704461.html",
"https://www.alibaba.com/product-detail/Home-Textile-200x230cm-Reversible-Polyester-Blanket_1600931176732.html",
"https://www.alibaba.com/product-detail/AVATTO-WOT20-EU-Smart-Wall-Socket_1601670127037.html",
"https://www.alibaba.com/product-detail/Ready-to-Ship-Summer-Clothes-Linen_1601764991328.html",
"https://www.alibaba.com/product-detail/Custom-Outside-Summer-Sunscreen-Jacket-Outdoor_1601032249021.html",
"https://www.alibaba.com/product-detail/New-Design-Sports-Custom-Polyester-Nylon_1601757232528.html",
"https://www.alibaba.com/product-detail/Modern-Soft-Bag-Dining-Chair-Apartment_1601709118293.html",
"https://www.alibaba.com/product-detail/New-Embroidered-Yuni-Badminton-Sports-Socks_1601600292696.html",
"https://www.alibaba.com/product-detail/China-Manufacture-First-Aid-Rescue-Outdoor_1601600928980.html",
"https://www.alibaba.com/product-detail/China-Manufacturing-Men-Trousers-Casual-Elastic_1601700380943.html",
"https://www.alibaba.com/product-detail/Custom-Home-Textiles-Woven-Jacquard-Blanket_1601063738123.html",
"https://www.alibaba.com/product-detail/Active-Bottoms-Men-s-Casual-Pants_1601567266882.html",
"https://www.alibaba.com/product-detail/Wifi-Smart-Custom-Infrared-TV-Air_1600108833698.html",
"https://www.alibaba.com/product-detail/Top-Quality-Promotional-Cricket-Set-Customize_11000002568761.html",
"https://www.alibaba.com/product-detail/Mens-Clothing-Designer-Manufacturers-Pullover-Cotton_1601769956466.html",
"https://www.alibaba.com/product-detail/Modern-Style-Office-Furniture-Set-Wooden_1601768436989.html",
"https://www.alibaba.com/product-detail/High-Quality-UV-Protected-Sunscreen-Window_1601403777889.html",
"https://www.alibaba.com/product-detail/Wholesale-Hot-Selling-New-Style-Lightweight_11000031451281.html",
"https://www.alibaba.com/product-detail/Modern-Portable-Round-Living-Room-Coffee_1601674719686.html",
"https://www.alibaba.com/product-detail/Men-s-Quick-Dry-Polyester-Joggers_1601352441205.html",
"https://www.alibaba.com/product-detail/M01-PRO-AI-Smart-Glasses-Translation_1601725929977.html",
"https://www.alibaba.com/product-detail/Dinner-Plate-Ceramic-Porcelain-Floral-Design_1600520155230.html",
"https://www.alibaba.com/product-detail/Hot-Selling-Fashion-Business-Men-Clothing_1600304740238.html",
"https://www.alibaba.com/product-detail/SONOFF-TRVZB-Winter-Smart-Home-Zigbee_1601557712443.html",
"https://www.alibaba.com/product-detail/High-Quality-Men-Luxury-Heavy-100_1600873072417.html",
"https://www.alibaba.com/product-detail/Cordless-Immersion-Blender-200W-3-in_1601608502542.html",
]
    
    # Option: Load from file
    # with open('product_urls.txt', 'r') as f:
    #     product_urls = [line.strip() for line in f if line.strip()]
    
    # Specify currency here
    scraper = CompleteAlibabaScraper(
        headless=False,     # False = visible browser for CAPTCHA
        max_retries=3,      # Retry failed products
        currency="USD"      # Set currency to USD (can be EUR, GBP, etc.)
    )
    
    results = await scraper.scrape_all_urls(product_urls, resume=True)
    
    print(f"\n✅ Complete! Total products: {len(results)}")
    print(f"💰 All prices are in {scraper.currency}")

if __name__ == "__main__":
    asyncio.run(main())