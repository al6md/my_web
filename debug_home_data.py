from flask_book_recommendation.app import create_app
import time
from flask_book_recommendation.routes.main import _generate_home_data
from flask_book_recommendation.models import User

app = create_app()

with app.app_context():
    print("Testing _generate_home_data() with user_id=1")
    user = User.query.first()
    if not user:
        print("No users found.")
    else:
        user_id = user.id
        print(f"Using user_id: {user_id}")
        start = time.time()
        try:
            data = _generate_home_data(user_id=user_id)
            print(f"Generated home data in {time.time()-start:.2f}s")
            if data:
                unified, buckets, top_rated, most_viewed, trending_libs = data
                print(f"Unified: {len(unified)}")
                print(f"Buckets: {[(k, len(v)) for k,v in buckets.items()]}")
                print(f"Top Rated: {len(top_rated)}")
                print(f"Most Viewed: {len(most_viewed)}")
                print(f"Trending Libs: {len(trending_libs)}")
        except Exception as e:
            print(f"Error in _generate_home_data: {e}")
            import traceback
            traceback.print_exc()

    print("ALL DONE")
