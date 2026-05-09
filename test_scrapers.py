from database import init_db
from scrapers.yahoo_scraper import run_all as yahoo_run
from scrapers.rbi_scraper import run_all as rbi_run
from scrapers.mospi_scraper import run_all as mospi_run
from scrapers.pib_scraper import run_all as pib_run

print("=== TESTING ALL SCRAPERS ===\n")
init_db()

print("1. Yahoo Finance:")
yahoo_run()

print("\n2. RBI:")
rbi_run()

print("\n3. MOSPI:")
mospi_run()

print("\n4. PIB:")
pib_run()

print("\n=== TEST COMPLETE ===")
print("Check http://localhost:8000/api/dashboard")
print("to verify real values are showing.")
