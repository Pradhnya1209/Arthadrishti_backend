import uvicorn
from database import init_db
from scheduler import run_all_scrapers, start_scheduler
import threading
import time

def start_background_tasks():
    print("\nInitialising database...")
    init_db()
    print("\nRunning scrapers for the first time...")
    run_all_scrapers()
    print("\nStarting automatic scheduler...")
    start_scheduler()

if __name__ == "__main__":
    print("=" * 50)
    print("  ARTHADRISHTI BACKEND")
    print("  India Macro Intelligence Platform")
    print("=" * 50)

    bg_thread = threading.Thread(
        target=start_background_tasks,
        daemon=True
    )
    bg_thread.start()

    time.sleep(2)

    print("\nStarting API server at http://localhost:8000")
    print("API docs at http://localhost:8000/docs")
    print("Press Ctrl+C to stop.\n")

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="warning"
    )
