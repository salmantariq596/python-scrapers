#!/usr/bin/env python3
"""
FSC Mauritius Complete Scraper v3
Handles empty data, resume properly, robust DOM interactions
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
import pandas as pd

# ==================== CONFIG ====================
NUM_WORKERS = 5
BATCH_SAVE = 50
HEADLESS = True
PHASE1_FILE = "phase1_all_names.json"
PROGRESS_FILE = "phase2_progress.xlsx"
FINAL_FILE = "fsc_complete_database.xlsx"
# ===============================================

DETAIL_FIELDS = {
    'Name of Licensee': '',
    'Mc Name': '',
    'Date of Licence / Approval / Authorisation / Registration (DD/MM/YYYY)': '',
    'Type of Licence': '',
    'Licensee Status': '',
    'Annotations': '',
    'Business Address / Registered Office Address': '',
    'Email': '',
    'Fax Number': '',
    'Mobile': '',
    'Telephone': '',
    'Website': '',
    'Contact Person': '',
    'Scraping_Date': ''
}


# ============================================================
# PHASE 1: EXTRACT ALL NAMES
# ============================================================

async def phase1_extract_all_names():
    """Scan every table page and collect all licensee names."""
    print("=" * 60)
    print("PHASE 1: Extracting all licensee names")
    print("=" * 60)

    all_records = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(viewport={'width': 1280, 'height': 720})
        page = await context.new_page()

        await page.route("**/*.{png,jpg,jpeg,gif,svg,css,woff,woff2,ttf,ico}",
                       lambda route: route.abort())

        print("Loading site...")
        await page.goto(
            "https://opr.fscmauritius.org/ords/opr/r/fsc-opr/fsc-online-public-register-opr",
            wait_until="domcontentloaded", timeout=60000
        )
        await page.wait_for_selector('table.a-IRR-table tbody tr', timeout=30000)
        await asyncio.sleep(3)

        # Sort by Name DESC using JavaScript
        print("Sorting by Name DESC...")
        await page.evaluate("""() => {
            const headers = document.querySelectorAll('table.a-IRR-table th');
            for (let h of headers) {
                if (h.innerText.includes('Name of Licensee')) {
                    h.click();
                    return;
                }
            }
        }""")
        await asyncio.sleep(2)
        await page.evaluate("""() => {
            const headers = document.querySelectorAll('table.a-IRR-table th');
            for (let h of headers) {
                if (h.innerText.includes('Name of Licensee')) {
                    h.click();
                    return;
                }
            }
        }""")
        await asyncio.sleep(2)

        last_first_name = None
        last_count = 0
        page_num = 0
        no_change_count = 0

        while True:
            page_num += 1
            print(f"  Page {page_num}...", end=" ", flush=True)

            for _ in range(3):
                try:
                    await page.wait_for_selector('table.a-IRR-table tbody tr', timeout=10000)
                    break
                except:
                    await asyncio.sleep(1)
            else:
                print("table not found - stopping")
                break

            await asyncio.sleep(1.5)

            page_records = await page.evaluate("""() => {
                const rows = document.querySelectorAll('table.a-IRR-table tbody tr');
                const records = [];
                for (let row of rows) {
                    const cells = row.querySelectorAll('td');
                    if (cells.length >= 5) {
                        const name = cells[1]?.innerText?.trim();
                        const date = cells[2]?.innerText?.trim();
                        const type = cells[3]?.innerText?.trim();
                        const annot = cells[4]?.innerText?.trim();
                        if (name) records.push({name, date, type, annotations: annot});
                    }
                }
                return records;
            }""")

            if not page_records:
                print("no records - stopping")
                break

            current_first = page_records[0]['name']
            if current_first == last_first_name:
                no_change_count += 1
                if no_change_count >= 2:
                    print("duplicate page - stopping")
                    break
            else:
                no_change_count = 0
                last_first_name = current_first

            if len(all_records) == last_count:
                print("no new records - stopping")
                break
            last_count = len(all_records) + len(page_records)

            all_records.extend(page_records)
            print(f"{len(page_records)} records (total: {len(all_records)})")

            next_clicked = await page.evaluate("""() => {
                const btn = document.querySelector('button[title="Next"]');
                if (btn && !btn.disabled) { btn.click(); return true; }
                return false;
            }""")

            if not next_clicked:
                print("Next disabled - stopping")
                break

            await asyncio.sleep(2)

        await browser.close()

    with open(PHASE1_FILE, 'w', encoding='utf-8') as f:
        json.dump(all_records, f, ensure_ascii=False, indent=2)

    print(f"\n✅ PHASE 1: {len(all_records)} records saved to {PHASE1_FILE}")
    return all_records


# ============================================================
# PHASE 2: PARALLEL DETAIL SCRAPING
# ============================================================

async def extract_detail_popup(page):
    """Extract all fields from detail popup."""
    data = DETAIL_FIELDS.copy()
    data['Scraping_Date'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    try:
        rows = await page.query_selector_all('.a-IRR-singleRow-row')
        for row in rows:
            try:
                name_elem = await row.query_selector('.a-IRR-singleRow-name')
                value_elem = await row.query_selector('.a-IRR-singleRow-value')
                if not name_elem or not value_elem:
                    continue

                field_name = (await name_elem.inner_text()).strip()
                field_value = (await value_elem.inner_text()).strip().replace('&#x2F;', '/')

                if 'Name of Licensee' in field_name:
                    data['Name of Licensee'] = field_value
                elif 'Mc Name' in field_name or 'Management Company' in field_name:
                    data['Mc Name'] = field_value
                elif 'Date of Licence' in field_name:
                    data['Date of Licence / Approval / Authorisation / Registration (DD/MM/YYYY)'] = field_value
                elif 'Type of Licence' in field_name:
                    data['Type of Licence'] = field_value
                elif 'Licensee Status' in field_name:
                    data['Licensee Status'] = field_value
                elif 'Annotations' in field_name:
                    data['Annotations'] = field_value
                elif 'Business Address' in field_name or 'Registered Office' in field_name:
                    data['Business Address / Registered Office Address'] = field_value
                elif field_name == 'Email':
                    data['Email'] = field_value
                elif field_name == 'Fax Number':
                    data['Fax Number'] = field_value
                elif field_name == 'Mobile':
                    data['Mobile'] = field_value
                elif field_name == 'Telephone':
                    data['Telephone'] = field_value
                elif field_name == 'Website':
                    data['Website'] = field_value
                elif field_name == 'Contact Person':
                    data['Contact Person'] = field_value
            except Exception:
                continue
    except Exception as e:
        print(f"    Detail extraction error: {e}")

    return data


def save_progress(results, filename=PROGRESS_FILE):
    """Save progress to Excel."""
    if not results:
        return
    try:
        df = pd.DataFrame(results)
        # Ensure all columns exist even if empty
        for col in DETAIL_FIELDS.keys():
            if col not in df.columns:
                df[col] = ''
        df.to_excel(filename, index=False)
        print(f"    💾 Saved {len(results)} records")
    except Exception as e:
        print(f"    Save error: {e}")


def load_progress():
    """Load previous progress."""
    if not os.path.exists(PROGRESS_FILE):
        return set(), []
    try:
        df = pd.read_excel(PROGRESS_FILE)
        # Handle empty or malformed file
        if df.empty or 'Name of Licensee' not in df.columns:
            return set(), []
        names = set(df['Name of Licensee'].astype(str).str.strip().str.upper())
        records = df.to_dict('records')
        print(f"🔄 Resuming from {len(records)} previously scraped")
        return names, records
    except Exception as e:
        print(f"⚠️ Progress load error: {e}")
        return set(), []


async def scrape_worker(worker_id, name_list, all_results, already_scraped, lock):
    """Worker that searches and extracts details."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(viewport={'width': 1280, 'height': 720})
        page = await context.new_page()

        await page.route("**/*.{png,jpg,jpeg,gif,svg,css,woff,woff2,ttf,ico}",
                       lambda route: route.abort())

        print(f"[W{worker_id}] Loading site...")
        await page.goto(
            "https://opr.fscmauritius.org/ords/opr/r/fsc-opr/fsc-online-public-register-opr",
            wait_until="domcontentloaded", timeout=60000
        )
        await page.wait_for_selector('table.a-IRR-table', timeout=30000)

        batch = []

        for i, item in enumerate(name_list):
            name = item['name']

            if name.upper() in already_scraped:
                print(f"[W{worker_id}] {i+1}/{len(name_list)} SKIP: {name[:50]}")
                continue

            print(f"[W{worker_id}] {i+1}/{len(name_list)}: {name[:50]}")

            try:
                # Search
                search_success = await page.evaluate("""(searchName) => {
                    const input = document.querySelector('input.a-IRR-search-field') ||
                                  document.querySelector('input[placeholder*="Search" i]');
                    if (!input) return false;
                    input.value = searchName;
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
                    return true;
                }""", name)

                if not search_success:
                    print(f"[W{worker_id}]   No search box, reloading...")
                    await page.goto(
                        "https://opr.fscmauritius.org/ords/opr/r/fsc-opr/fsc-online-public-register-opr",
                        wait_until="domcontentloaded", timeout=60000
                    )
                    await page.wait_for_selector('table.a-IRR-table', timeout=30000)
                    continue

                await asyncio.sleep(2)

                # Verify
                first_name = await page.evaluate("""() => {
                    const cell = document.querySelector('table.a-IRR-table tbody tr:first-child td:nth-child(2)');
                    return cell ? cell.innerText.trim() : '';
                }""")

                if name.lower() not in first_name.lower() and first_name.lower() not in name.lower():
                    print(f"[W{worker_id}]   Mismatch: '{name[:40]}' vs '{first_name[:40]}'")
                    await page.evaluate("""() => {
                        const input = document.querySelector('input.a-IRR-search-field');
                        if (input) { input.value = ''; input.dispatchEvent(new Event('input', { bubbles: true })); }
                    }""")
                    await asyncio.sleep(0.5)
                    continue

                # Click eye
                eye_clicked = await page.evaluate("""() => {
                    const eye = document.querySelector('a.a-IRR-detail-row');
                    if (eye) { eye.click(); return true; }
                    return false;
                }""")

                if not eye_clicked:
                    print(f"[W{worker_id}]   No eye icon")
                    await page.evaluate("""() => {
                        const input = document.querySelector('input.a-IRR-search-field');
                        if (input) { input.value = ''; input.dispatchEvent(new Event('input', { bubbles: true })); }
                    }""")
                    await asyncio.sleep(0.5)
                    continue

                await page.wait_for_selector('.a-IRR-singleRow-row', timeout=15000)
                await asyncio.sleep(0.5)

                # Extract
                data = await extract_detail_popup(page)
                if not data.get('Name of Licensee'):
                    data['Name of Licensee'] = name

                batch.append(data)

                # Close popup
                await page.evaluate("""() => {
                    const closeBtn = document.querySelector('button.ui-dialog-titlebar-close, .ui-dialog-titlebar-close, .ui-icon-closethick');
                    if (closeBtn) closeBtn.click();
                }""")
                await asyncio.sleep(0.3)

                # Clear search
                await page.evaluate("""() => {
                    const input = document.querySelector('input.a-IRR-search-field');
                    if (input) { 
                        input.value = ''; 
                        input.dispatchEvent(new Event('input', { bubbles: true }));
                        input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
                    }
                }""")
                await asyncio.sleep(0.5)

            except PlaywrightTimeout:
                print(f"[W{worker_id}]   TIMEOUT: {name[:50]}")
                try:
                    await page.goto(
                        "https://opr.fscmauritius.org/ords/opr/r/fsc-opr/fsc-online-public-register-opr",
                        wait_until="domcontentloaded", timeout=60000
                    )
                    await page.wait_for_selector('table.a-IRR-table', timeout=30000)
                except Exception:
                    pass

            except Exception as e:
                print(f"[W{worker_id}]   ERROR: {name[:50]}: {e}")
                try:
                    await page.goto(
                        "https://opr.fscmauritius.org/ords/opr/r/fsc-opr/fsc-online-public-register-opr",
                        wait_until="domcontentloaded", timeout=60000
                    )
                    await page.wait_for_selector('table.a-IRR-table', timeout=30000)
                except Exception:
                    pass

            # Batch save
            if len(batch) >= 25:
                async with lock:
                    all_results.extend(batch)
                    for b in batch:
                        already_scraped.add(b['Name of Licensee'].upper())
                    save_progress(all_results)
                batch = []

        # Final batch
        if batch:
            async with lock:
                all_results.extend(batch)
                for b in batch:
                    already_scraped.add(b['Name of Licensee'].upper())
                save_progress(all_results)

        await browser.close()


async def phase2_scrape_details(all_names):
    """Launch parallel workers."""
    print("\n" + "=" * 60)
    print("PHASE 2: Scraping details")
    print(f"Workers: {NUM_WORKERS} | Headless: {HEADLESS}")
    print("=" * 60)

    already_scraped, all_results = load_progress()
    todo = [n for n in all_names if n['name'].upper() not in already_scraped]
    print(f"Total: {len(all_names)} | Done: {len(already_scraped)} | Remaining: {len(todo)}")

    if not todo:
        print("Nothing left to scrape!")
        # Return whatever we have (could be from progress file)
        return all_results

    chunks = [[] for _ in range(NUM_WORKERS)]
    for i, item in enumerate(todo):
        chunks[i % NUM_WORKERS].append(item)

    lock = asyncio.Lock()
    tasks = []
    for i, chunk in enumerate(chunks):
        if chunk:
            tasks.append(scrape_worker(i, chunk, all_results, already_scraped, lock))

    await asyncio.gather(*tasks)
    print(f"\n✅ PHASE 2: {len(all_results)} total records")
    return all_results


# ============================================================
# FINAL SAVE (FIXED FOR EMPTY DATA)
# ============================================================

def save_final_excel(results, filename=FINAL_FILE):
    """Save final Excel with stats. Handles empty results gracefully."""
    
    if not results:
        print("\n⚠️ No results to save! Creating empty template file.")
        df = pd.DataFrame(columns=list(DETAIL_FIELDS.keys()))
        stats = pd.DataFrame({
            'Metric': ['Total Records', 'Unique Licensees', 'Export Date'],
            'Count': [0, 0, datetime.now().strftime('%Y-%m-%d %H:%M:%S')]
        })
        with pd.ExcelWriter(filename, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Licensees', index=False)
            stats.to_excel(writer, sheet_name='Statistics', index=False)
        print(f"✅ Empty template saved: {filename}")
        return filename

    df = pd.DataFrame(results)

    # Ensure all expected columns exist
    for col in DETAIL_FIELDS.keys():
        if col not in df.columns:
            df[col] = ''

    col_order = [
        'Name of Licensee', 'Mc Name',
        'Date of Licence / Approval / Authorisation / Registration (DD/MM/YYYY)',
        'Type of Licence', 'Licensee Status', 'Annotations',
        'Business Address / Registered Office Address',
        'Email', 'Fax Number', 'Mobile', 'Telephone', 'Website',
        'Contact Person', 'Scraping_Date'
    ]
    existing_cols = [c for c in col_order if c in df.columns]
    df = df[existing_cols]
    df = df.drop_duplicates(subset=['Name of Licensee'], keep='last')

    stats = pd.DataFrame({
        'Metric': [
            'Total Records', 'Unique Licensees', 'Records with Email',
            'Records with Phone', 'Records with Address', 'Records with Website', 'Export Date'
        ],
        'Count': [
            len(df),
            df['Name of Licensee'].nunique(),
            len(df[df['Email'].astype(str).str.strip() != '']),
            len(df[df['Telephone'].astype(str).str.strip() != '']),
            len(df[df['Business Address / Registered Office Address'].astype(str).str.strip() != '']),
            len(df[df['Website'].astype(str).str.strip() != '']),
            datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        ]
    })

    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Licensees', index=False)
        stats.to_excel(writer, sheet_name='Statistics', index=False)

    print(f"\n{'=' * 60}")
    print(f"✅ FINAL: {filename}")
    print(f"   Records: {len(df)} | Unique: {df['Name of Licensee'].nunique()}")
    print(f"   Email: {stats.iloc[2]['Count']} | Phone: {stats.iloc[3]['Count']}")
    print(f"{'=' * 60}")
    return filename


# ============================================================
# MAIN
# ============================================================

async def main():
    print("=" * 60)
    print("FSC MAURITIUS - COMPLETE SCRAPER v3")
    print("=" * 60)

    # Phase 1
    if os.path.exists(PHASE1_FILE):
        print(f"\n📂 Found {PHASE1_FILE}")
        with open(PHASE1_FILE, 'r', encoding='utf-8') as f:
            all_names = json.load(f)
        print(f"   Loaded {len(all_names)} names")
        resp = input("   Re-run Phase 1? (y/N): ").strip().lower()
        if resp == 'y':
            all_names = await phase1_extract_all_names()
    else:
        all_names = await phase1_extract_all_names()

    # Phase 2
    results = await phase2_scrape_details(all_names)

    # Save
    save_final_excel(results)

    # Cleanup
    if os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE)
        print(f"🗑️ Cleaned {PROGRESS_FILE}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️ INTERRUPTED! Resume by re-running.")
        sys.exit(1)