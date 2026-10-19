# Python Scrapers

Production scrapers built with **Playwright (async)** for client data projects. Each one is resumable: stop it at any time and it continues where it left off.

| Scraper | Target | What it collects | Output |
|---|---|---|---|
| [`alibaba-product-scraper`](alibaba-product-scraper/) | Alibaba.com product pages | Tiered prices and MOQ, variants, images, specifications, seller profile, shipping, lead times, packaging, certifications, plus rule-based tags (product type, gender, audience, use case) | JSON |
| [`fsc-register-scraper`](fsc-register-scraper/) | FSC Mauritius public register (Oracle APEX) | Every licensee: licence type and date, status, address, contact details, website | Excel (data + statistics sheet) |

## Alibaba product scraper
- Forces **USD** pricing through cookies, URL parameters and the currency selector.
- Detects captchas, pauses for a manual solve, and **saves cookies** so later runs skip it.
- Tracks scraped and failed URLs separately, logs failure reasons, and resumes from the last index.
- Pulls descriptions from inside the product's iframe and handles pages where selectors are missing.

```bash
pip install -r alibaba-product-scraper/requirements.txt && playwright install chromium
python alibaba-product-scraper/alibaba_scraper.py   # edit product_urls in main()
```

## FSC Mauritius register scraper
- **Phase 1:** pages through the whole interactive report and saves every licensee name.
- **Phase 2:** **5 parallel browser workers** search each name, open its detail view and extract 13 fields; progress is saved every 25 records.
- Blocks images, CSS and fonts for speed; recovers from timeouts by reloading the register.
- Final workbook de-duplicates by licensee and adds a statistics sheet (records with email, phone, address, website).

```bash
pip install -r fsc-register-scraper/requirements.txt && playwright install chromium
python fsc-register-scraper/fsc_scraper.py
```

> Scrape responsibly: respect each site's terms, keep request rates polite, and use public data only.

## Author
**Salman Tariq** · [GitHub](https://github.com/salmantariq596)
