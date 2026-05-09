from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_yahoo_scrapers():
    logger.info(f"Running Yahoo scrapers at {datetime.now()}")
    try:
        from scrapers.yahoo_scraper import run_all
        run_all()
    except Exception as e:
        logger.error(f"Yahoo scraper failed: {e}")

def run_rbi_scrapers():
    logger.info(f"Running RBI scrapers at {datetime.now()}")
    try:
        from scrapers.rbi_scraper import run_all
        run_all()
    except Exception as e:
        logger.error(f"RBI scraper failed: {e}")

def run_mospi_scrapers():
    logger.info(f"Running MOSPI scrapers at {datetime.now()}")
    try:
        from scrapers.mospi_scraper import run_all
        run_all()
    except Exception as e:
        logger.error(f"MOSPI scraper failed: {e}")

def run_pib_scrapers():
    logger.info(f"Running PIB scrapers at {datetime.now()}")
    try:
        from scrapers.pib_scraper import run_all
        run_all()
    except Exception as e:
        logger.error(f"PIB scraper failed: {e}")

def run_all_scrapers():
    run_yahoo_scrapers()
    run_rbi_scrapers()
    run_mospi_scrapers()
    run_pib_scrapers()
    logger.info("All scrapers completed.")

def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        run_yahoo_scrapers,
        CronTrigger(hour=1, minute=0),
        id='yahoo_daily',
        name='Yahoo Finance Daily Scrape'
    )
    scheduler.add_job(
        run_rbi_scrapers,
        CronTrigger(day_of_week='mon', hour=1, minute=30),
        id='rbi_weekly',
        name='RBI Weekly Scrape'
    )
    scheduler.add_job(
        run_mospi_scrapers,
        CronTrigger(day=1, hour=2, minute=30),
        id='mospi_monthly',
        name='MOSPI Monthly Scrape'
    )
    scheduler.add_job(
        run_pib_scrapers,
        CronTrigger(day=1, hour=3, minute=30),
        id='pib_monthly',
        name='PIB Monthly Scrape'
    )
    scheduler.start()
    logger.info("Scheduler started.")
    for job in scheduler.get_jobs():
        logger.info(f"  - {job.name}: {job.trigger}")
    return scheduler

if __name__ == '__main__':
    import time
    from database import init_db
    init_db()
    print("Running all scrapers once now...")
    run_all_scrapers()
    print("\nStarting scheduler...")
    scheduler = start_scheduler()
    print("Scheduler running. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        scheduler.shutdown()
        print("Scheduler stopped.")
