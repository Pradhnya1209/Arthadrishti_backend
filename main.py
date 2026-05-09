from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from database import (
    init_db, get_all_indicators, get_indicator,
    get_timeseries
)
from datetime import datetime

app = FastAPI(
    title="Arthadrishti API",
    description="India Macro Intelligence Platform API",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

@app.on_event('startup')
async def startup():
    init_db()
    print('Arthadrishti API started')

@app.get('/')
def root():
    return {
        'name': 'Arthadrishti API',
        'status': 'running',
        'timestamp': datetime.now().isoformat()
    }

@app.get('/api/indicators')
def list_indicators():
    try:
        indicators = get_all_indicators()
        return {'count': len(indicators), 'indicators': indicators}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/api/indicators/{indicator_id}')
def get_indicator_detail(indicator_id: str):
    indicator = get_indicator(indicator_id)
    if not indicator:
        raise HTTPException(status_code=404,
            detail=f"Indicator '{indicator_id}' not found")
    return indicator

@app.get('/api/timeseries/{indicator_id}')
def get_indicator_timeseries(indicator_id: str, limit: int = 120):
    indicator = get_indicator(indicator_id)
    if not indicator:
        raise HTTPException(status_code=404,
            detail=f"Indicator '{indicator_id}' not found")
    data = get_timeseries(indicator_id, limit)
    return {
        'indicator_id': indicator_id,
        'name': indicator['name'],
        'unit': indicator['unit'],
        'count': len(data),
        'data': data
    }

@app.get('/api/dashboard')
def get_dashboard():
    key_ids = [
        'cpi','repo-rate','nifty50','usdinr',
        'gdp','brent','forex','yield-10y'
    ]
    results = []
    for ind_id in key_ids:
        indicator = get_indicator(ind_id)
        if indicator:
            results.append(indicator)
    return {'indicators': results}

@app.post('/api/scrape')
def trigger_scrape(source: str = 'all'):
    try:
        from scrapers.yahoo_scraper import run_all as yahoo_run
        from scrapers.rbi_scraper import run_all as rbi_run
        from scrapers.mospi_scraper import run_all as mospi_run
        from scrapers.pib_scraper import run_all as pib_run
        results = {}
        if source in ('all','yahoo'):
            results['yahoo'] = yahoo_run()
        if source in ('all','rbi'):
            results['rbi'] = rbi_run()
        if source in ('all','mospi'):
            results['mospi'] = mospi_run()
        if source in ('all','pib'):
            results['pib'] = pib_run()
        return {'status': 'success', 'results': str(results)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/api/status')
def scrape_status():
    from database import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT indicator_id, scraper, status, message, timestamp
        FROM scrape_log
        ORDER BY timestamp DESC
        LIMIT 50
    ''')
    rows = cursor.fetchall()
    conn.close()
    return {'logs': [dict(r) for r in rows]}

if __name__ == '__main__':
    uvicorn.run('main:app', host='0.0.0.0', port=8000, reload=True)
