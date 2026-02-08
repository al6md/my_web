import requests
import time

print("Checking AI Engine Health...")
for i in range(5):
    try:
        r = requests.get("http://localhost:8001/health", timeout=2)
        if r.ok:
            print(f"Health Check Passed: {r.json()}")
            exit(0)
    except Exception as e:
        print(f"Attempt {i+1}: Failed - {e}")
        time.sleep(2)

print("Health Check Failed after 5 attempts")
exit(1)
