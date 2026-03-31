import os
import sys
from flask_book_recommendation.app import create_app
from flask_book_recommendation.utils import fetch_google_books, fetch_archive_books, fetch_openlib_books

app = create_app()
with app.app_context():
    query = "War"
    print(f"\n--- Testing Search Robustness for Query: '{query}' ---\n")
    
    # 1. Test Google Books
    print("Testing Google Books...")
    google_items, google_total = fetch_google_books(query)
    print(f"Google Result: {len(google_items)} items, Total estimate: {google_total}")
    
    # 2. Test Archive
    print("\nTesting Archive.org...")
    archive_items = fetch_archive_books(query)
    print(f"Archive Result: {len(archive_items)} items")
    
    # 3. Test OpenLib
    print("\nTesting OpenLibrary...")
    openlib_items = fetch_openlib_books(query)
    print(f"OpenLib Result: {len(openlib_items)} items")
    
    print("\n--- Summary ---")
    total_found = len(google_items) + len(archive_items) + len(openlib_items)
    print(f"Total items found across 3 sources: {total_found}")
    if total_found > 0:
        print("✅ SUCCESS: Search is returning results.")
    else:
        print("❌ FAILURE: No results found for 'War'. Check network or API keys.")
