# scheduler.py
import schedule
import time
from scanner import KuCoinSuperScanner
from notifier import TelegramNotifier
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

def job():
    print("🔄 Running scheduled scan...")
    scanner = KuCoinSuperScanner()
    results = scanner.scan_all(limit=150)
    notifier = TelegramNotifier(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)
    report = notifier.format_report(results)
    notifier.send_sync(report)
    print("✅ Scheduled job finished.")

def start_scheduler(interval_minutes=60):
    schedule.every(interval_minutes).minutes.do(job)
    print(f"⏰ Scheduler started: every {interval_minutes} minutes.")
    while True:
        schedule.run_pending()
        time.sleep(60)
