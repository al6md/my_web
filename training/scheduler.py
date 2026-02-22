import os
from apscheduler.schedulers.background import BackgroundScheduler
from pathlib import Path
from flask_book_recommendation.extensions import db
from flask_book_recommendation.models import UserPreference, UserGenre

def update_all_embeddings(app):
    """
    Background job to update user embeddings based on latest interests and interactions.
    """
    with app.app_context():
        print("🕒 [Scheduler] Starting 24h user embedding update job...")
        try:
            from ai_book_recommender.feature_store.user_embeddings import user_embedding_manager
            
            # Fetch all distinct user IDs that have preferences or genres
            pref_users = set(u[0] for u in db.session.query(UserPreference.user_id).distinct().all())
            genre_users = set(u[0] for u in db.session.query(UserGenre.user_id).distinct().all())
            
            all_users = pref_users.union(genre_users)
            
            for user_id in all_users:
                # Re-initialize or update their vector based on explicit interests
                # (You could also fetch recent interactions from the log here)
                interests = []
                prefs = UserPreference.query.filter_by(user_id=user_id).order_by(UserPreference.weight.desc()).limit(5).all()
                genres = db.session.query(UserGenre.genre_id).filter_by(user_id=user_id).all()
                
                interests.extend([p.topic for p in prefs])
                # Note: To get genre names, we'd need to join, but simple topics are usually enough
                if interests:
                    try:
                        # Re-calculate the base vector
                        user_embedding_manager.initialize_from_interests(user_id, interests)
                    except Exception as e:
                        print(f"Failed to update embedding for user {user_id}: {e}")
                        
            print("✅ [Scheduler] Finished updating user embeddings.")
            
        except Exception as e:
            print(f"❌ [Scheduler] Error during embedding update: {e}")

def start_scheduler(app):
    """
    Initializes and starts the APScheduler.
    """
    # Check if we're running in the main Werkzeug process (avoids double execution in debug mode)
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true" and app.debug:
        return

    scheduler = BackgroundScheduler(daemon=True)
    
    # Run every 24 hours
    scheduler.add_job(
        func=update_all_embeddings,
        trigger="interval",
        hours=24,
        args=[app],
        id="update_embeddings_job",
        name="Update all user embeddings daily",
        replace_existing=True
    )
    
    scheduler.start()
    print("⏰ [Scheduler] APScheduler started successfully.")
