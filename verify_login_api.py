import requests
import sys

BASE_URL = "http://127.0.0.1:5000"
LOGIN_URL = f"{BASE_URL}/api/auth/login"
DEMO_USER = {
    "email": "admin@example.com",
    "password": "1234"
}

def seed_user():
    try:
        print("Seeding demo user...")
        resp = requests.get(f"{BASE_URL}/auth/seed/demo")
        if resp.status_code == 200:
            print("[OK] User seeded successfully.")
            return True
        else:
            print(f"[WARN] Seeding returned {resp.status_code}. User might already exist.")
            return True
    except Exception as e:
        print(f"[FAIL] Could not seed user: {e}")
        return False

def check_server_health():
    try:
        response = requests.get(f"{BASE_URL}/ping")
        if response.status_code == 200:
            print("[OK] Server is running and accessible.")
            return True
        else:
            print(f"[FAIL] Server returned status code: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("[FAIL] Could not connect to server at 127.0.0.1:5000. Is it running?")
        return False

def verify_login():
    try:
        print(f"Attempting login with {DEMO_USER['email']}...")
        response = requests.post(LOGIN_URL, json=DEMO_USER)
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success") and "token" in data:
                print("[OK] Login Successful!")
                print(f"   User: {data['user']['name']}")
                print(f"   Token received (first 10 chars): {data['token'][:10]}...")
                return True
            else:
                print("[FAIL] Login response format unexpected.")
                print(response.text)
                return False
        else:
            print(f"[FAIL] Login failed with status code: {response.status_code}")
            print(response.text)
            return False
    except Exception as e:
        print(f"[FAIL] Error during login verification: {e}")
        return False

if __name__ == "__main__":
    print("--- Verifying Login API ---")
    if check_server_health():
        seed_user() # Attempt to seed/ensure user exists
        if verify_login():
            print("\n[OK] Verification Passed. The API is working correctly.")
        else:
            print("\n[FAIL] Verification Failed for Login.")
            sys.exit(1)
    else:
        print("\n[FAIL] Verification Failed: Server not reachable.")
        sys.exit(1)
