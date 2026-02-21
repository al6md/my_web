
import sys
import os

# Add the project root to sys.path
sys.path.append(os.getcwd())

try:
    print("Checking imports...")
    from flask_book_recommendation.recommender import (
        get_topic_based_internet,
        _user_cache_key,
        _invalidate_user_cache,
        get_last_search_recommendations
    )
    print("✅ recommender.py imports successful")

    from flask_book_recommendation.routes.main import home
    print("✅ routes/main.py home function exists")

    from flask_book_recommendation.routes.auth import reset_user_data, confirm_reset_data
    print("✅ routes/auth.py reset routes exist")
    
    # Check if get_topic_based_internet has the right signature (inspect not possible easily without sourcing, but import works)
    import inspect
    sig = inspect.signature(get_topic_based_internet)
    print(f"✅ get_topic_based_internet signature: {sig}")

    print("\nAll checks passed! The code structure is correct.")

except ImportError as e:
    print(f"❌ ImportError: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)
