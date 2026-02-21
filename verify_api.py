import requests
import time
import sys

BASE_URL = "http://127.0.0.1:5000"

def test_homepage_speed():
    print(f"Testing Homepage Shell Speed...")
    start = time.time()
    try:
        r = requests.get(BASE_URL + "/")
        duration = time.time() - start
        print(f"Homepage load time: {duration:.2f}s")
        if duration < 2.0:
            print("✅ Homepage is FAST (<2s)")
        else:
            print("⚠️ Homepage is SLOW (>2s)")
            
        if "skeleton-box" in r.text:
            print("✅ Skeleton loaders detected in HTML")
        else:
            print("❌ Skeleton loaders NOT found")
    except Exception as e:
        print(f"❌ Error reaching homepage: {e}")

def test_section_api(section="unified"):
    print(f"\nTesting API Section: {section}...")
    start = time.time()
    try:
        r = requests.get(f"{BASE_URL}/api/home/sections?section={section}")
        duration = time.time() - start
        data = r.json()
        count = data.get('count', 0)
        print(f"API load time: {duration:.2f}s | Items: {count}")
        
        if count > 0:
            print(f"✅ Section {section} returned content")
        else:
            print(f"⚠️ Section {section} returned empty (might be expected for guest/unified)")
            
    except Exception as e:
        print(f"❌ Error reaching API: {e}")

def test_onboarding_categories():
    print(f"\nTesting Onboarding Categories (Hybrid)...")
    # Need to simulate login? user_id is required for some things, but maybe not categories get?
    # Categories GET is login_required!
    # I can't easily bypass login in this script without auth token/cookie.
    # But I can check if it returns 401, which means endpoint exists.
    r = requests.get(f"{BASE_URL}/api/onboarding/categories")
    if r.status_code == 401:
        print("✅ Endpoint exists (401 Unauthorized expected without login)")
    elif r.status_code == 200:
        print("✅ Endpoint accessible")
        data = r.json()
        cats = data.get('categories', [])
        print(f"Categories count: {len(cats)}")
        is_web = any(c.get('is_web') for c in cats)
        if is_web:
             print("✅ Web categories detected (Hybrid working)")
        else:
             print("⚠️ Only local categories found (Web fetch might have failed or not merged)")
    else:
        print(f"❌ Unexpected status: {r.status_code}")

if __name__ == "__main__":
    test_homepage_speed()
    test_section_api("top_rated")
    test_section_api("unified") # Will be empty/fast for guest
    test_onboarding_categories()
