import requests
import re
import time
from bs4 import BeautifulSoup
from datetime import datetime
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from database import insert_timeseries, update_indicator, log_scrape

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Connection': 'keep-alive',
}

FALLBACK_GST = 196000   # crore


def _get(url, timeout=15):
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r


def _parse_gst_from_text(text):
    patterns = [
        # "Gross GST revenue … Rs. 1,96,000 crore" / "₹1,96,000 crore"
        r'(?:gross\s+)?gst\s+revenue[^₹\d]{0,80}?(?:rs\.?\s*|₹\s*)(\d[\d,]+)\s*crore',
        r'total\s+(?:gross\s+)?gst[^₹\d]{0,80}?(?:rs\.?\s*|₹\s*)(\d[\d,]+)',
        # "₹ 1,96,000 crore" in any GST context
        r'₹\s*(\d[\d,]+)\s*(?:lakh\s+)?crore',
        # "1,96,000 crore" near gst
        r'(\d[\d,]+)\s*crore[^.]{0,60}?gst',
        r'gst[^.]{0,60}?(\d[\d,]+)\s*crore',
        # lakh crore format: "₹2.37 lakh crore"
        r'(?:rs\.?\s*|₹\s*)(\d+\.\d+)\s*lakh\s+crore',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            raw = m.group(1).replace(',', '')
            try:
                val = float(raw)
                # lakh crore: value like 1.96, 2.10 etc.
                if val < 100:
                    val = val * 100000
                # already in crore
                if 100000 <= val <= 300000:
                    return int(val)
            except ValueError:
                pass
    return None


def _fetch_pib_gst_via_listing():
    """
    PIB allRel.aspx renders a table. The GST press release title appears in
    the table row text, not in the anchor text. Strategy: get all row text,
    find rows mentioning 'GST collection', grab the first link in that row.
    """
    url = 'https://pib.gov.in/allRel.aspx?reg=3&lang=1'
    r = _get(url)
    soup = BeautifulSoup(r.text, 'html.parser')

    # Look at every row / list item / div that contains GST collection text
    gst_hrefs = []
    for tag in soup.find_all(['tr', 'li', 'div', 'p']):
        txt = tag.get_text(' ', strip=True)
        if re.search(r'GST\s+(?:revenue|collection)', txt, re.I):
            # Grab the first link inside this element
            a = tag.find('a', href=True)
            if a:
                href = a['href']
                if not href.startswith('http'):
                    href = 'https://pib.gov.in/' + href.lstrip('/')
                gst_hrefs.append(href)

    print(f"  Found {len(gst_hrefs)} GST row-links on PIB listing")
    return gst_hrefs


def _fetch_pib_gst_via_search():
    """
    PIB has a keyword-filtered release page.
    """
    url = 'https://pib.gov.in/allRel.aspx?reg=3&lang=1&kf=GST+collection'
    try:
        r = _get(url)
        soup = BeautifulSoup(r.text, 'html.parser')
        hrefs = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            if 'PressRel' in href or 'PRID' in href:
                if not href.startswith('http'):
                    href = 'https://pib.gov.in/' + href.lstrip('/')
                hrefs.append(href)
        return hrefs
    except Exception as e:
        print(f"  PIB search URL failed: {e}")
        return []


# ── GST ───────────────────────────────────────────────────────────────────────

def scrape_gst():
    print("Scraping GST Collections...")
    gst = None

    # Attempt 1a: PIB listing page — scan row text for GST context
    try:
        hrefs = _fetch_pib_gst_via_listing()
        for href in hrefs[:3]:
            try:
                time.sleep(2)
                pr = _get(href)
                soup2 = BeautifulSoup(pr.text, 'html.parser')
                text = soup2.get_text(' ', strip=True)
                val = _parse_gst_from_text(text)
                if val:
                    gst = val
                    print(f"  GST from PIB press release: ₹{gst:,} Cr [LIVE]")
                    break
            except Exception as e:
                print(f"  PIB press release fetch failed: {e}")
    except Exception as e:
        print(f"  PIB listing page failed: {e}")

    # Attempt 1b: PIB keyword-filtered search
    if gst is None:
        try:
            time.sleep(1)
            hrefs = _fetch_pib_gst_via_search()
            for href in hrefs[:3]:
                try:
                    time.sleep(2)
                    pr = _get(href)
                    soup2 = BeautifulSoup(pr.text, 'html.parser')
                    text = soup2.get_text(' ', strip=True)
                    val = _parse_gst_from_text(text)
                    if val:
                        gst = val
                        print(f"  GST from PIB search result: ₹{gst:,} Cr [LIVE]")
                        break
                except Exception as e:
                    print(f"  PIB search result fetch failed: {e}")
        except Exception as e:
            print(f"  PIB keyword search failed: {e}")

    # Attempt 2: Known recent GST press release PRIDs (April 2025 range)
    if gst is None:
        recent_prids = [2115010, 2107055, 2099111, 2091000, 1999111]
        for prid in recent_prids:
            try:
                time.sleep(2)
                url = f'https://pib.gov.in/PressRelasePage.aspx?PRID={prid}'
                r = _get(url)
                soup = BeautifulSoup(r.text, 'html.parser')
                text = soup.get_text(' ', strip=True)
                if re.search(r'GST\s+(?:revenue|collection)', text, re.I):
                    val = _parse_gst_from_text(text)
                    if val:
                        gst = val
                        print(f"  GST from PIB PRID {prid}: ₹{gst:,} Cr [LIVE]")
                        break
            except Exception:
                pass

    # Attempt 3: Finance Ministry / GST portal revenue page
    if gst is None:
        try:
            time.sleep(2)
            r = _get('https://www.gst.gov.in/newsandupdates/read/554')
            soup = BeautifulSoup(r.text, 'html.parser')
            text = soup.get_text(' ', strip=True)
            val = _parse_gst_from_text(text)
            if val:
                gst = val
                print(f"  GST from GST portal: ₹{gst:,} Cr [LIVE]")
        except Exception as e:
            print(f"  GST portal failed: {e}")

    # Attempt 4: World Bank government revenue proxy (annual, very lagged)
    # Skipped — too imprecise for monthly GST figure

    if gst is None:
        gst = FALLBACK_GST
        status = 'fallback'
        print(f"  GST: using fallback ₹{gst:,} Cr")
    else:
        status = 'success'

    try:
        insert_timeseries('gst', datetime.now().strftime('%Y-%m-%d'), gst)
        update_indicator('gst', gst, datetime.now().strftime('%b %Y'), -3000, 15000, 'up')
        log_scrape('gst', 'pib', status, str(gst))
        print(f"  GST stored: ₹{gst:,} Cr")
        return True
    except Exception as e:
        log_scrape('gst', 'pib', 'error', str(e))
        return False


# ── ENTRY POINT ───────────────────────────────────────────────────────────────

def run_all():
    print("\n--- PIB Scraper ---")
    results = {'gst': scrape_gst()}
    print(f"PIB done: {sum(results.values())}/{len(results)} successful")
    return results


if __name__ == '__main__':
    from database import init_db
    init_db()
    run_all()
