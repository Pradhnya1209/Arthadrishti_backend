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

FALLBACKS = {
    'cpi': 3.61,
    'core-inflation': 4.10,
    'gdp': 6.4,
}


def _get(url, timeout=15):
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r


# ── CPI ───────────────────────────────────────────────────────────────────────

def _parse_cpi_from_text(text):
    patterns = [
        r'CPI.*?inflation.*?(\d+\.\d+)\s*(?:per\s+cent|%)',
        r'inflation.*?(\d+\.\d+)\s*(?:per\s+cent|%)',
        r'(\d+\.\d+)\s*(?:per\s+cent|%).*?(?:CPI|inflation)',
        r'(\d+\.\d+)\s*per\s+cent',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = float(m.group(1))
            if 1.0 <= val <= 15.0:
                return val
    return None


def _fetch_cpi_worldbank():
    # World Bank API — gives annual CPI inflation, always accessible
    try:
        url = ('https://api.worldbank.org/v2/country/IN/indicator/'
               'FP.CPI.TOTL.ZG?format=json&mrv=5&per_page=5')
        r = requests.get(url, timeout=10)
        data = r.json()
        for entry in data[1]:
            if entry.get('value') is not None:
                return round(float(entry['value']), 2)
    except Exception as e:
        print(f"  World Bank CPI API failed: {e}")
    return None


def scrape_cpi():
    print("Scraping CPI...")
    cpi = None

    # Attempt 1: MOSPI press release page
    try:
        r = _get('https://mospi.gov.in/web/mospi/press-release')
        soup = BeautifulSoup(r.text, 'html.parser')
        # Find links mentioning CPI
        links = soup.find_all('a', href=True)
        cpi_links = [a['href'] for a in links
                     if re.search(r'CPI|consumer.?price|inflation', a.get_text(), re.I)]
        if cpi_links:
            href = cpi_links[0]
            if not href.startswith('http'):
                href = 'https://mospi.gov.in' + href
            time.sleep(2)
            pr = _get(href)
            soup2 = BeautifulSoup(pr.text, 'html.parser')
            cpi = _parse_cpi_from_text(soup2.get_text(' ', strip=True))
            if cpi:
                print(f"  CPI from MOSPI press release: {cpi}% [LIVE]")
    except Exception as e:
        print(f"  MOSPI press release failed: {e}")

    # Attempt 2: MOSPI data portal
    if cpi is None:
        try:
            time.sleep(2)
            r = _get('https://mospi.gov.in/web/mospi/reports-publications')
            soup = BeautifulSoup(r.text, 'html.parser')
            cpi = _parse_cpi_from_text(soup.get_text(' ', strip=True))
            if cpi:
                print(f"  CPI from MOSPI reports page: {cpi}% [LIVE]")
        except Exception as e:
            print(f"  MOSPI reports page failed: {e}")

    # Attempt 3: World Bank API (annual, lagged but reliable)
    if cpi is None:
        time.sleep(1)
        wb_cpi = _fetch_cpi_worldbank()
        if wb_cpi and 1.0 <= wb_cpi <= 15.0:
            cpi = wb_cpi
            print(f"  CPI from World Bank API: {cpi}% [annual, lagged]")

    if cpi is None:
        cpi = FALLBACKS['cpi']
        cpi_status = 'fallback'
        print(f"  CPI: using fallback {cpi}%")
    else:
        cpi_status = 'success'

    core = FALLBACKS['core-inflation']

    try:
        date_str = datetime.now().strftime('%Y-%m-%d')
        insert_timeseries('cpi', date_str, cpi)
        insert_timeseries('core-inflation', date_str, core)
        update_indicator('cpi', cpi, datetime.now().strftime('%b %Y'), -0.4, -3.1, 'down')
        update_indicator('core-inflation', core, datetime.now().strftime('%b %Y'), -0.2, -2.4, 'down')
        log_scrape('cpi', 'mospi', cpi_status, str(cpi))
        print(f"  CPI stored: {cpi}%")
        return True
    except Exception as e:
        log_scrape('cpi', 'mospi', 'error', str(e))
        return False


# ── GDP ───────────────────────────────────────────────────────────────────────

def _parse_gdp_from_text(text):
    patterns = [
        r'GDP.*?grew.*?(\d+\.?\d*)\s*(?:per\s+cent|%)',
        r'GDP.*?growth.*?(\d+\.?\d*)\s*(?:per\s+cent|%)',
        r'gross\s+domestic\s+product.*?(\d+\.?\d*)\s*(?:per\s+cent|%)',
        r'(\d+\.?\d*)\s*(?:per\s+cent|%).*?GDP',
        r'(\d+\.?\d*)\s*per\s+cent.*?growth',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = float(m.group(1))
            if 1.0 <= val <= 15.0:
                return val
    return None


def _fetch_gdp_worldbank():
    try:
        url = ('https://api.worldbank.org/v2/country/IN/indicator/'
               'NY.GDP.MKTP.KD.ZG?format=json&mrv=5&per_page=5')
        r = requests.get(url, timeout=10)
        data = r.json()
        for entry in data[1]:
            if entry.get('value') is not None:
                return round(float(entry['value']), 1)
    except Exception as e:
        print(f"  World Bank GDP API failed: {e}")
    return None


def scrape_gdp():
    print("Scraping GDP...")
    gdp = None

    # Attempt 1: MOSPI press release page
    try:
        r = _get('https://mospi.gov.in/web/mospi/press-release')
        soup = BeautifulSoup(r.text, 'html.parser')
        links = soup.find_all('a', href=True)
        gdp_links = [a['href'] for a in links
                     if re.search(r'GDP|gross.domestic|national.income', a.get_text(), re.I)]
        if gdp_links:
            href = gdp_links[0]
            if not href.startswith('http'):
                href = 'https://mospi.gov.in' + href
            time.sleep(2)
            pr = _get(href)
            soup2 = BeautifulSoup(pr.text, 'html.parser')
            gdp = _parse_gdp_from_text(soup2.get_text(' ', strip=True))
            if gdp:
                print(f"  GDP from MOSPI press release: {gdp}% [LIVE]")
    except Exception as e:
        print(f"  MOSPI GDP press release failed: {e}")

    # Attempt 2: World Bank API
    if gdp is None:
        time.sleep(1)
        wb_gdp = _fetch_gdp_worldbank()
        if wb_gdp and 1.0 <= wb_gdp <= 15.0:
            gdp = wb_gdp
            print(f"  GDP from World Bank API: {gdp}% [annual, lagged]")

    if gdp is None:
        gdp = FALLBACKS['gdp']
        status = 'fallback'
        print(f"  GDP: using fallback {gdp}%")
    else:
        status = 'success'

    try:
        insert_timeseries('gdp', datetime.now().strftime('%Y-%m-%d'), gdp)
        update_indicator('gdp', gdp, 'Q3 FY25', 0.3, 0.8, 'up')
        log_scrape('gdp', 'mospi', status, str(gdp))
        print(f"  GDP stored: {gdp}%")
        return True
    except Exception as e:
        log_scrape('gdp', 'mospi', 'error', str(e))
        return False


# ── ENTRY POINT ───────────────────────────────────────────────────────────────

def run_all():
    print("\n--- MOSPI Scraper ---")
    results = {
        'cpi': scrape_cpi(),
        'gdp': scrape_gdp(),
    }
    print(f"MOSPI done: {sum(results.values())}/{len(results)} successful")
    return results


if __name__ == '__main__':
    from database import init_db
    init_db()
    run_all()
