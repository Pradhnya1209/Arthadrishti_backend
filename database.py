import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'arthadrishti.db')

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS indicators (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            unit TEXT,
            source TEXT,
            frequency TEXT,
            last_updated TEXT,
            next_update TEXT,
            latest_value REAL,
            latest_period TEXT,
            mom_change REAL,
            yoy_change REAL,
            trend TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS timeseries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            indicator_id TEXT NOT NULL,
            date TEXT NOT NULL,
            value REAL NOT NULL,
            UNIQUE(indicator_id, date),
            FOREIGN KEY (indicator_id) REFERENCES indicators(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS scrape_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            indicator_id TEXT,
            scraper TEXT,
            status TEXT,
            message TEXT,
            timestamp TEXT
        )
    ''')

    indicators = [
        ('gdp','GDP Growth Rate','Growth','%','MOSPI','Quarterly',None,None,None,None,None,None,None),
        ('pmi-mfg','PMI Manufacturing','Growth','Index','S&P Global','Monthly',None,None,None,None,None,None,None),
        ('pmi-services','PMI Services','Growth','Index','S&P Global','Monthly',None,None,None,None,None,None,None),
        ('credit','Credit Growth','Growth','%','RBI','Monthly',None,None,None,None,None,None,None),
        ('gst','GST Collections','Growth','INR Crore','PIB','Monthly',None,None,None,None,None,None,None),
        ('cpi','CPI Inflation','Inflation','%','MOSPI','Monthly',None,None,None,None,None,None,None),
        ('core-inflation','Core Inflation','Inflation','%','MOSPI','Monthly',None,None,None,None,None,None,None),
        ('repo-rate','Repo Rate','Rates','%','RBI','Per Meeting',None,None,None,None,None,None,None),
        ('yield-10y','10Y Bond Yield','Rates','%','RBI DBIE','Daily',None,None,None,None,None,None,None),
        ('yield-curve','Yield Curve Spread','Rates','%','RBI DBIE','Daily',None,None,None,None,None,None,None),
        ('usdinr','USD/INR','External','INR','RBI','Daily',None,None,None,None,None,None,None),
        ('brent','Brent Crude Oil','External','USD','Yahoo Finance','Daily',None,None,None,None,None,None,None),
        ('forex','Forex Reserves','External','USD Billion','RBI','Weekly',None,None,None,None,None,None,None),
        ('current-account','Current Account','External','% of GDP','RBI','Quarterly',None,None,None,None,None,None,None),
        ('liquidity','Banking System Liquidity','Liquidity','INR Lakh Crore','RBI','Daily',None,None,None,None,None,None,None),
        ('fii-flows','FII/FPI Flows','Liquidity','USD Million','NSDL','Daily',None,None,None,None,None,None,None),
        ('nifty50','Nifty 50','Markets','Index','NSE','Daily',None,None,None,None,None,None,None),
        ('midcap','Nifty Midcap 100','Markets','Index','NSE','Daily',None,None,None,None,None,None,None),
        ('sector','Sector Performance','Markets','%','NSE','Daily',None,None,None,None,None,None,None),
        ('npa','NPAs','Risk','% of Advances','RBI FSR','Semi-Annual',None,None,None,None,None,None,None),
        ('credit-spreads','Credit Spreads','Risk','%','NSE/RBI','Daily',None,None,None,None,None,None,None),
    ]

    cursor.executemany('''
        INSERT OR IGNORE INTO indicators
        (id,name,category,unit,source,frequency,last_updated,
        next_update,latest_value,latest_period,mom_change,yoy_change,trend)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    ''', indicators)

    conn.commit()
    conn.close()
    print(f"Database initialised at {DB_PATH}")

def update_indicator(indicator_id, latest_value, latest_period, mom_change=None, yoy_change=None, trend=None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE indicators SET
            latest_value=?, latest_period=?, mom_change=?,
            yoy_change=?, trend=?, last_updated=?
        WHERE id=?
    ''', (latest_value, latest_period, mom_change, yoy_change, trend,
          datetime.now().strftime('%b %Y'), indicator_id))
    conn.commit()
    conn.close()

def insert_timeseries(indicator_id, date, value):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO timeseries (indicator_id, date, value)
        VALUES (?, ?, ?)
    ''', (indicator_id, date, value))
    conn.commit()
    conn.close()

def get_timeseries(indicator_id, limit=120):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT date, value FROM timeseries
        WHERE indicator_id=?
        ORDER BY date ASC
        LIMIT ?
    ''', (indicator_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return [{'date': r['date'], 'value': r['value']} for r in rows]

def get_indicator(indicator_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM indicators WHERE id=?', (indicator_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_all_indicators():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM indicators ORDER BY category, name')
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def log_scrape(indicator_id, scraper, status, message=''):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO scrape_log
        (indicator_id, scraper, status, message, timestamp)
        VALUES (?,?,?,?,?)
    ''', (indicator_id, scraper, status, message,
          datetime.now().isoformat()))
    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
