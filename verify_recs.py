
import sys
import os

# Add the project root to the path
sys.path.append(os.getcwd())

print("Checking imports...")

try:
    from flask_book_recommendation import recommender
    print("✅ recommender.py imported successfully")
except Exception as e:
    print(f"❌ Error importing recommender.py: {e}")
    sys.exit(1)

try:
    from flask_book_recommendation.routes import main
    print("✅ routes/main.py imported successfully")
except Exception as e:
    print(f"❌ Error importing routes/main.py: {e}")
    sys.exit(1)

print("Verifying new functions exist...")
if hasattr(recommender, 'get_hybrid_recommendations'):
    print("✅ get_hybrid_recommendations found")
else:
    print("❌ get_hybrid_recommendations NOT found")
    sys.exit(1)

if hasattr(recommender, 'get_author_books'):
    print("✅ get_author_books found")
else:
    print("❌ get_author_books NOT found")
    sys.exit(1)

print("All checks passed! 🎉")
