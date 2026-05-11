# main.py
import sys
import threading
from scheduler import start_scheduler
import subprocess

def run_dashboard():
    subprocess.run(["streamlit", "run", "dashboard.py"])

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "scheduler":
        start_scheduler(interval_minutes=60)
    else:
        # تشغيل الجدولة في خلفية ولوحة التحكم
        scheduler_thread = threading.Thread(target=start_scheduler, args=(60,), daemon=True)
        scheduler_thread.start()
        run_dashboard()
