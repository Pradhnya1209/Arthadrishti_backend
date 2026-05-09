import requests
import re
import time
import yfinance as yf
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
    'repo-rate': 6.25,
    'forex': 645.0,
    'yield-10y': 6.84,
    'yield-curve': 0.59,
}


def _get(url, timeout=15):
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r


# ── REPO RATE ─────────────────────────────────────────────────────────────────

def _parse_repo_from_text(text):
    # Tight patterns — require "policy repo rate" + adjacent value.
    # Must NOT match CRR, SLR, MSF, SDF or any other rate.
    patterns = [
        r'policy\s+repo\s+rate[^%\d]{0,60}?(\d+\.?\d*)\s*(?:per\s+cent|%)',
        r'repo\s+rate\s+(?:stands?\s+at|unchanged\s+at|revised\s+to|increased\s+to|reduced\s+to|hiked\s+to|cut\s+to|at)\s*(\d+\.?\d*)',
        r'repo\s+rate[^%\d]{0,40}?(\d+\.?\d*)\s*per\s+cent',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = float(m.group(1))
            # Sanity: repo rate has been between 4% and 9% in recent history
            if 4.0 <= val <= 9.0:
                return val
    return None


def scrape_repo_rate():
    print("Scraping Repo Rate...")
    rate = None

    # Attempt 1: RBI Monetary Policy page
    try:
        r = _get('https://www.rbi.org.in/Scripts/BS_ViewMonetaryPolicy.aspx')
        soup = BeautifulSoup(r.text, 'html.parser')
        rate = _parse_repo_from_text(soup.get_text(' ', strip=True))
        if rate:
            print(f"  Repo Rate from RBI Monetary Policy page: {rate}% [LIVE]")
    except Exception as e:
        print(f"  RBI Monetary Policy page failed: {e}")

    # Attempt 2: RBI Press Release page (latest MPC statement)
    if rate is None:
        try:
            time.sleep(1)
            r = _get('https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx')
            soup = BeautifulSoup(r.text, 'html.parser')
            # Find the most recent monetary policy link
            links = soup.find_all('a', href=True)
            mpc_links = [a['href'] for a in links
                         if re.search(r'monetary.?policy|MPC|repo', a.get_text(), re.I)]
            for href in mpc_links[:2]:
                if not href.startswith('http'):
                    href = 'https://www.rbi.org.in' + href
                try:
                    time.sleep(1)
                    pr = _get(href)
                    soup2 = BeautifulSoup(pr.text, 'html.parser')
                    rate = _parse_repo_from_text(soup2.get_text(' ', strip=True))
                    if rate:
                        print(f"  Repo Rate from MPC press release: {rate}% [LIVE]")
                        break
                except Exception:
                    pass
        except Exception as e:
            print(f"  RBI press release page failed: {e}")

    # Attempt 3: RBI homepage (last resort — tightest pattern only)
    if rate is None:
        try:
            time.sleep(1)
            r = _get('https://www.rbi.org.in/home.aspx')
            soup = BeautifulSoup(r.text, 'html.parser')
            rate = _parse_repo_from_text(soup.get_text(' ', strip=True))
            if rate:
                print(f"  Repo Rate from RBI homepage: {rate}% [LIVE]")
        except Exception as e:
            print(f"  RBI homepage failed: {e}")

    # Final sanity check — reject anything below 5.0 (repo has never been that low in India)
    if rate is not None and rate < 5.0:
        print(f"  Repo Rate {rate}% failed sanity check (too low) — using fallback")
        rate = None

    if rate is None:
        rate = FALLBACKS['repo-rate']
        status = 'fallback'
        print(f"  Repo Rate: using fallback {rate}%")
    else:
        status = 'success'

    try:
        insert_timeseries('repo-rate', datetime.now().strftime('%Y-%m-%d'), rate)
        update_indicator('repo-rate', rate, datetime.now().strftime('%b %Y'), -0.25, -0.25, 'down')
        log_scrape('repo-rate', 'rbi', status, str(rate))
        print(f"  Repo Rate stored: {rate}%")
        return True
    except Exception as e:
        log_scrape('repo-rate', 'rbi', 'error', str(e))
        return False


# ── FOREX RESERVES ────────────────────────────────────────────────────────────

def _fetch_forex_worldbank():
    # World Bank: FI.RES.TOTL.CD = Total reserves (includes gold), in current USD
    try:
        url = ('https://api.worldbank.org/v2/country/IND/indicator/'
               'FI.RES.TOTL.CD?format=json&mrv=2&per_page=2')
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()
        for entry in data[1]:
            if entry.get('value') is not None:
                usd = float(entry['value'])
                billions = round(usd / 1_000_000_000, 1)
                if 300 <= billions <= 900:   # sanity
                    return billions
    except Exception as e:
        print(f"  World Bank forex API failed: {e}")
    return None


def _parse_forex_from_text(text):
    patterns = [
        r'[Tt]otal\s+[Ff]oreign\s+[Ee]xchange\s+[Rr]eserves?[^0-9]{0,60}?(\d[\d,]*\.?\d*)',
        r'[Ff]oreign\s+[Ee]xchange\s+[Rr]eserves?[^0-9]{0,60}?(\d[\d,]*\.?\d*)',
        r'(\d{3}[,\d]*\.\d+)\s*(?:[Bb]illion|bn)',
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            val_str = m.group(1).replace(',', '')
            try:
                val = float(val_str)
                if 400000 <= val <= 900000:
                    return round(val / 1000, 1)   # millions → billions
                if 400 <= val <= 900:
                    return round(val, 1)
            except ValueError:
                pass
    return None


def scrape_forex_reserves():
    print("Scraping Forex Reserves...")
    reserves = None

    # Attempt 1: World Bank API (reliable, official data, ~6-month lag)
    reserves = _fetch_forex_worldbank()
    if reserves:
        print(f"  Forex Reserves from World Bank API: ${reserves}B [LIVE, lagged]")

    # Attempt 2: RBI Weekly Statistical Supplement
    if reserves is None:
        try:
            time.sleep(1)
            r = _get('https://www.rbi.org.in/Scripts/WSSViewDetail.aspx?TYPE=Section&PARAM1=2')
            soup = BeautifulSoup(r.text, 'html.parser')
            reserves = _parse_forex_from_text(soup.get_text(' ', strip=True))
            if reserves:
                print(f"  Forex Reserves from RBI WSS: ${reserves}B [LIVE]")
        except Exception as e:
            print(f"  RBI WSS failed: {e}")

    if reserves is None:
        reserves = FALLBACKS['forex']
        status = 'fallback'
        print(f"  Forex Reserves: using fallback ${reserves}B")
    else:
        status = 'success'

    try:
        insert_timeseries('forex', datetime.now().strftime('%Y-%m-%d'), reserves)
        update_indicator('forex', reserves, datetime.now().strftime('%b %Y'), 2.1, 42.0, 'up')
        log_scrape('forex', 'rbi', status, str(reserves))
        print(f"  Forex Reserves stored: ${reserves}B")
        return True
    except Exception as e:
        log_scrape('forex', 'rbi', 'error', str(e))
        return False


# ── BOND YIELDS ───────────────────────────────────────────────────────────────

def _fetch_yield_yahoo(symbol):
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period='5d', interval='1d', auto_adjust=True, prepost=False)
        if hist is not None and not hist.empty:
            val = round(float(hist['Close'].iloc[-1]), 2)
            if 5.0 <= val <= 10.0:
                return val
    except Exception as e:
        print(f"  Yahoo yield {symbol} failed: {e}")
    return None


def _parse_yield_from_text(text):
    patterns = [
        r'10.year\s+(?:g.sec|gsec|benchmark|bond)[^0-9]{0,40}?(\d+\.\d+)\s*(?:per\s+cent|%)?',
        r'(\d+\.\d+)\s*(?:per\s+cent|%)[^a-z]{0,30}?10.year',
        r'10Y[^0-9]{0,20}?(\d+\.\d+)',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = float(m.group(1))
            if 5.0 <= val <= 10.0:
                return val
    return None


def _scrape_ccil_yield():
    try:
        r = _get('https://www.ccilindia.com/Research/Statistics/Pages/GSecBenchmark.aspx')
        soup = BeautifulSoup(r.text, 'html.parser')
        text = soup.get_text(' ', strip=True)
        m = re.search(r'10\s*[Yy][^0-9]{0,20}?(\d+\.\d+)', text)
        if m:
            val = float(m.group(1))
            if 5.0 <= val <= 10.0:
                return val
    except Exception as e:
        print(f"  CCIL failed: {e}")
    return None


def scrape_bond_yield():
    print("Scraping Bond Yields...")
    yield_val = None
    repo_rate = FALLBACKS['repo-rate']

    # Attempt 1: Several Yahoo Finance tickers for India bond yield
    for symbol in ['IN10YT=RR', 'GSEC10Y.NS', 'IN10Y=X']:
        if yield_val:
            break
        time.sleep(0.5)
        val = _fetch_yield_yahoo(symbol)
        if val:
            yield_val = val
            print(f"  10Y Yield from Yahoo ({symbol}): {yield_val}% [LIVE]")

    # Attempt 2: CCIL benchmark page
    if yield_val is None:
        time.sleep(1)
        yield_val = _scrape_ccil_yield()
        if yield_val:
            print(f"  10Y Yield from CCIL: {yield_val}% [LIVE]")

    # Attempt 3: RBI bulletin page
    if yield_val is None:
        try:
            time.sleep(1)
            r = _get('https://www.rbi.org.in/Scripts/PublicationsView.aspx?id=22219')
            soup = BeautifulSoup(r.text, 'html.parser')
            yield_val = _parse_yield_from_text(soup.get_text(' ', strip=True))
            if yield_val:
                print(f"  10Y Yield from RBI bulletin: {yield_val}% [LIVE]")
        except Exception as e:
            print(f"  RBI bulletin failed: {e}")

    # Attempt 4: Estimate from repo rate + typical spread (0.59pp historically)
    if yield_val is None:
        # Try to get the stored repo rate for a better estimate
        try:
            from database import get_indicator
            ind = get_indicator('repo-rate')
            if ind and ind.get('latest_value'):
                repo_rate = float(ind['latest_value'])
        except Exception:
            pass
        yield_val = round(repo_rate + 0.59, 2)
        print(f"  10Y Yield estimated from repo ({repo_rate}%) + spread: {yield_val}%")
        status = 'estimated'
    else:
        status = 'success'

    # Final sanity check
    if not (5.0 <= yield_val <= 10.0):
        print(f"  10Y Yield {yield_val}% outside sanity range — using fallback")
        yield_val = FALLBACKS['yield-10y']
        status = 'fallback'

    spread = round(yield_val - repo_rate, 2) if status == 'success' else FALLBACKS['yield-curve']

    try:
        date_str = datetime.now().strftime('%Y-%m-%d')
        insert_timeseries('yield-10y', date_str, yield_val)
        insert_timeseries('yield-curve', date_str, spread)
        update_indicator('yield-10y', yield_val, datetime.now().strftime('%b %Y'), -0.06, -0.18, 'down')
        update_indicator('yield-curve', spread, datetime.now().strftime('%b %Y'), 0.04, 0.12, 'up')
        log_scrape('yield-10y', 'rbi', status, str(yield_val))
        print(f"  10Y Yield stored: {yield_val}%")
        return True
    except Exception as e:
        log_scrape('yield-10y', 'rbi', 'error', str(e))
        return False


# ── ENTRY POINT ───────────────────────────────────────────────────────────────

def run_all():
    print("\n--- RBI Scraper ---")
    results = {
        'repo-rate': scrape_repo_rate(),
        'forex': scrape_forex_reserves(),
        'yield-10y': scrape_bond_yield(),
    }
    print(f"RBI done: {sum(results.values())}/{len(results)} successful")
    return results


if __name__ == '__main__':
    from database import init_db
    init_db()
    run_all()
