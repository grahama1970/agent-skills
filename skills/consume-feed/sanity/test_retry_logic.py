import sys
import os
import threading
import time
import subprocess

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SKILL_ROOT)

from util.http import HttpClient

def test_retries():
    # Start mock server in subprocess
    server_script = os.path.join(SCRIPT_DIR, "mock_server.py")
    proc = subprocess.Popen([sys.executable, server_script])
    
    # Give it a sec to bind
    time.sleep(1) 
    
    url = "http://localhost:9999"
    client = HttpClient()
    
    print(f"Attempting to fetch {url} (expected 2 failures, then success)...")
    
    try:
        # Tenacity shoud retry the 500s
        status, text, _ = client.fetch_text(url)
        if status == 200 and text == "Success":
            print("✅ Retry logic worked! Recovered from failures.")
        else:
            print(f"❌ Unexpected result: {status} {text}")
            sys.exit(1)
    except Exception as e:
        print(f"❌ Request failed despite retries: {e}")
        sys.exit(1)
    finally:
        proc.terminate()

if __name__ == "__main__":
    test_retries()
