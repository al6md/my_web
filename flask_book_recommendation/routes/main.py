# routes/main.py
import logging
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user, login_required
import numpy as np
import pandas as pd
import requests
from ..models import BookStatus
import random
import time

logger = logging.getLogger(__name__)



from ..extensions import db, csrf, cache
import threading
import time
# في أعلى ملف main.py
from ..models import Book, UserRatingCF, BookEmbedding, UserPreference, SearchHistory, BookReview, BookQuote
# استيراد الدوال الموحدة
from ..utils import (
    fetch_openlib_detail, fetch_gutenberg_detail, fetch_archive_detail, fetch_itbook_detail, fetch_book_details,
    get_text_embedding, generate_book_embedding_if_missing,
    fetch_google_books, fetch_gutenberg_books, fetch_openlib_books, fetch_archive_books,
    fetch_itbook_books,
    translate_to_english_with_gemini,
    chat_with_ai  # مساعد AI للكتب
)
from ..recommender import log_user_view, get_deep_learning_recommendations




main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def home():
    """
    الصفحة الرئيسية — تحميل الهيكل (Skeleton) فوراً، ثم جلب البيانات عبر API.
    """
    from flask import make_response
    import time

    # We return the template immediately without data.
    resp = make_response(render_template(
        "home.html",
        unified_recommendations=[],
        algo_buckets={},
        top_rated_books_sorted=[],
        most_viewed_books=[],
        trending_by_libraries=[],
        featured_book=None,
        current_filters={'query': '', 'sort': 'ai_relevance', 'debug_ts': time.time()}
    ))
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp

@main_bp.route("/feed/home")
def home_feed():
    """
    API endpoint لجلب أقسام الصفحة الرئيسية بشكل غير متزامن.
    """
    import time
    from flask import jsonify, render_template, current_app
    import threading
    
    user_id = current_user.id if current_user.is_authenticated else None

    # ✅ FIX: Always generate fresh data on every refresh (no cache)
    # This ensures the user sees different books every time they refresh
    unified_recommendations, algo_buckets, top_rated_books_sorted, most_viewed_books, trending_by_libraries = _generate_home_data(user_id)

    # ✅ Re-shuffle and re-sample unified on EVERY request for fresh results
    import random
    if unified_recommendations:
        random.shuffle(unified_recommendations)
        sample_size = min(40, len(unified_recommendations))
        unified_recommendations = random.sample(unified_recommendations, sample_size)
        
        # Heavy jitter to ensure order varies each time and gives dynamic feel
        for b in unified_recommendations:
            base_score = float(b.get('score') or b.get('confidence') or 0.5)
            # Add significant random noise (-0.8 to +0.8) so high confidence doesn't permanently lock position
            b['_sort_score'] = base_score + random.uniform(-0.8, 0.8)
            
        unified_recommendations.sort(key=lambda x: x.get('_sort_score', 0), reverse=True)

    if algo_buckets:
        for key, books in algo_buckets.items():
            if books and len(books) > 3:
                random.shuffle(books)
                
    html = render_template("components/home_feed.html",
        unified_recommendations=unified_recommendations,
        algo_buckets=algo_buckets,
        top_rated_books_sorted=top_rated_books_sorted,
        most_viewed_books=most_viewed_books,
        trending_by_libraries=trending_by_libraries
    )
    return jsonify({"success": True, "html": html})

def _generate_home_data(user_id):
    """
    Helper to generate all homepage data (Unified + Sections).
    Used by home() and background refresh.
    Returns: (unified, buckets, top_rated, most_viewed, trending_libs)
    """
    from ..recommender import (
        get_trending, get_top_rated, get_cf_similar,
        get_behavior_based_recommendations, get_content_similar,
        get_deep_learning_recommendations, get_view_based_recommendations,
        get_last_search_recommendations, get_topic_based
    )
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from flask import current_app

    # Try import explore helpers
    try:
        from .explore import get_trending_by_libraries, get_most_viewed_books_custom
    except ImportError:
        get_trending_by_libraries = lambda limit: []
        get_most_viewed_books_custom = lambda limit: []

    unified_recommendations = []
    algo_buckets = {
        'search_history_results': [],
        'interest_results': [],
        'hybrid_results': [],
        'transformer_results': [],
        'collaborative_results': [],
        'graph_results': [],
        'vector_results': [],
        'reranker_results': []
    }
    seen_ids = set()

    def _add(book_dict, algo_key, algo_label, confidence=0.7, reason=None, force_top=False):
        if not book_dict: return
        bid = book_dict.get('id')
        if not bid: return

        book_dict.setdefault('score', book_dict.get('ai_score', 0))
        book_dict.setdefault('confidence', confidence)
        book_dict['algo_tag'] = algo_label
        if reason:
            book_dict['reason'] = reason
        else:
            book_dict.setdefault('reason', book_dict.get('explanation', 'Recommended by AI'))

        if algo_key in algo_buckets:
            if not any(b['id'] == bid for b in algo_buckets[algo_key]):
                algo_buckets[algo_key].append(book_dict)

        if bid not in seen_ids:
            seen_ids.add(bid)
            book_dict['contributing_algorithms'] = [algo_label]
            book_dict['algo_tag'] = algo_label
            if force_top:
                unified_recommendations.insert(0, book_dict)
            else:
                unified_recommendations.append(book_dict)
        else:
            for existing in unified_recommendations:
                if existing['id'] == bid:
                    if algo_label not in existing.get('contributing_algorithms', []):
                        existing['contributing_algorithms'].append(algo_label)
                    # If forcing to top, move it
                    if force_top and existing in unified_recommendations:
                        unified_recommendations.remove(existing)
                        unified_recommendations.insert(0, existing)
                    break
    
    # Helper to run safely
    def run_safe(app_obj, func, *args, **kwargs):
        with app_obj.app_context():
            return func(*args, **kwargs)

    # 1. Unified Recommendations
    if user_id:
        tasks = [
            {'name': 'search_history', 'func': get_last_search_recommendations, 'args': (user_id,), 'kwargs': {'limit': 20, 'randomize': True}, 'bucket': 'search_history_results', 'label': 'Search History', 'conf': 0.96, 'process': lambda res: res[1] if res and res[1] else [], 'reason': lambda r, res: f"لأنك بحثت عن: {res[0]}" if res and res[0] else "Based on your search"},
            {'name': 'topic', 'func': get_topic_based, 'args': (user_id,), 'kwargs': {'limit': 50, 'randomize': True}, 'bucket': 'interest_results', 'label': 'Interest Match', 'conf': 0.94, 'process': lambda res: (res.get('books', []) if isinstance(res, dict) else res) or [], 'reason': lambda r, _: r.get('reason', "Based on your interests")},
            {'name': 'hybrid', 'func': get_behavior_based_recommendations, 'args': (user_id,), 'kwargs': {'limit': 50, 'randomize': True}, 'bucket': 'hybrid_results', 'label': 'Hybrid', 'conf': 0.92, 'process': lambda res: res or [], 'reason': lambda r, _: "Based on your overall reading behavior"},
            {'name': 'transformer', 'func': get_deep_learning_recommendations, 'args': (user_id,), 'kwargs': {'limit': 50, 'randomize': True}, 'bucket': 'transformer_results', 'label': 'Transformer', 'conf': 0.88, 'process': lambda res: res or [], 'reason': lambda r, _: "Deep Learning Match"},
            {'name': 'cf', 'func': get_cf_similar, 'args': (user_id,), 'kwargs': {'top_n': 50, 'randomize': True}, 'bucket': 'collaborative_results', 'label': 'Collaborative', 'conf': 0.82, 'process': lambda res: res or [], 'reason': lambda r, _: "Similar readers liked this"},
            {'name': 'content', 'func': get_content_similar, 'args': (user_id,), 'kwargs': {'top_n': 50, 'randomize': True}, 'bucket': 'vector_results', 'label': 'Vector Similarity', 'conf': 0.78, 'process': lambda res: res or [], 'reason': lambda r, _: "Content similarity to your library"},
            {'name': 'reranker', 'func': get_view_based_recommendations, 'args': (user_id,), 'kwargs': {'top_n': 50, 'randomize': True}, 'bucket': 'reranker_results', 'label': 'Neural Reranker', 'conf': 0.85, 'process': lambda res: res or [], 'reason': lambda r, _: "Re-ranked based on your browsing history"},
        ]
        
        app_obj = current_app._get_current_object()
        executor = ThreadPoolExecutor(max_workers=6)
        future_to_task = {executor.submit(run_safe, app_obj, t['func'], *t['args'], **t['kwargs']): t for t in tasks}
        
        try:
            from concurrent.futures import TimeoutError
            for future in as_completed(future_to_task, timeout=15.0):
                task = future_to_task[future]
                try:
                    raw_result = future.result()
                    processed_books = task['process'](raw_result)
                    for book in processed_books:
                        reason_text = task['reason'](book, raw_result)
                        _add(book, task['bucket'], task['label'], confidence=task['conf'], reason=reason_text)
                except Exception as e:
                    current_app.logger.error(f"Task {task['name']} failed: {e}")
        except TimeoutError:
            current_app.logger.warning("Unified recommendations hit 15s timeout, returning partial results.")
        finally:
            executor.shutdown(wait=False)

        # 🛑 Fallback Fix: If empty, use Topic Based with recent query, then Trending
        if not unified_recommendations:
            # Try to get recent search from DB context
            try:
                last_search = SearchHistory.query.filter_by(user_id=user_id).order_by(SearchHistory.created_at.desc()).first()
                q = last_search.query if last_search else None
                fallback_res = get_topic_based(user_id, limit=50, recent_query=q, randomize=True)
                books = fallback_res.get('books', []) if isinstance(fallback_res, dict) else fallback_res
                for b in books:
                    _add(b, 'interest_results', 'Interest Match', 0.85, "Fallback Recommendations")
            except Exception as e:
                current_app.logger.error(f"Fallback error: {e}")
            
            # 🔧 FIX #3: إذا لم نجد توصيات، نستخدم Trending أيضاً للمستخدمين المسجلين
            if not unified_recommendations:
                try:
                    for r in get_trending(limit=30):
                        _add(r, 'hybrid_results', 'Trending', confidence=0.65, reason="Trending in our community")
                except Exception as e:
                    current_app.logger.error(f"Trending fallback error: {e}")

    else:
        # Guest: Trending
        try:
            for r in get_trending(limit=30):
                _add(r, 'hybrid_results', 'Trending', confidence=0.65, reason="Trending worldwide")
        except Exception: pass

    # ═══════════════════════════════════════════════════════════════════
    # 🆕 FRESH BOOKS INJECTION — Guarantees different books on every refresh
    # Fetches directly from OpenLibrary API with random topics + random offset
    # ═══════════════════════════════════════════════════════════════════
    import random
    from concurrent.futures import ThreadPoolExecutor, as_completed
    try:
        from ..utils import fetch_openlib_books
        from ..models import UserPreference, Genre, UserGenre

        # 1. Build topic pool from user's actual interests + discovery topics
        user_topics = []
        if user_id:
            # Get user genres from onboarding
            try:
                genres = db.session.query(Genre.name).join(UserGenre).filter(UserGenre.user_id == user_id).all()
                user_topics.extend([g[0] for g in genres if g[0]])
            except Exception:
                pass
            # Get user preferences
            try:
                prefs = UserPreference.query.filter_by(user_id=user_id).all()
                for p in prefs:
                    if p.topic and not p.topic.startswith('special:') and len(p.topic) > 2:
                        user_topics.append(p.topic)
            except Exception:
                pass

        # Discovery pool — diverse real book topics
        discovery_pool = [
            "best novels 2024", "science fiction bestsellers", "self help books",
            "mystery thriller books", "historical fiction", "biography autobiography",
            "psychology books", "philosophy books", "romance novels",
            "fantasy books", "horror novels", "business leadership",
            "artificial intelligence books", "poetry collection", "adventure novels",
            "cooking books", "travel books", "children books",
            "graphic novels", "true crime books", "classic literature",
            "dystopian fiction", "space exploration", "economics books",
            "arabic novels", "programming books", "data science",
            "motivational books", "health wellness", "world history",
            "technology future", "startup business", "financial literacy"
        ]

        # Pick 5 random topics: 2 from user interests (if any) + 3 from discovery
        query_topics = []
        if user_topics:
            random.shuffle(user_topics)
            query_topics.extend(user_topics[:2])
        
        # Always add discovery topics for variety
        query_topics.extend(random.sample(discovery_pool, 5 - len(query_topics)))

        # 2. Fetch fresh books from OpenLibrary for each topic in parallel for speed
        def fetch_topic(topic):
            # Max 30 for offset to avoid empty pages for niche topics
            start_offset = random.randint(0, 30) 
            # Smart query: if topic contains arabic, append "كتب", if english append "books"
            search_query = topic
            if any("\u0600" <= c <= "\u06FF" for c in topic):
                search_query = f"{topic} كتب"
            else:
                search_query = f"{topic} books"
                
            books_list = fetch_openlib_books(search_query, limit=10, offset=start_offset)
            return topic, books_list

        with ThreadPoolExecutor(max_workers=5) as fresh_executor:
            future_to_topic = {fresh_executor.submit(fetch_topic, t): t for t in query_topics}
            
            for future in as_completed(future_to_topic, timeout=5.0):
                try:
                    topic, books_list = future.result()
                    for b in (books_list or []):
                        gid = b.get("id")
                        if not gid: continue
                        
                        book_dict = {
                            "id": gid,
                            "title": b.get("title", "Untitled"),
                            "author": b.get("author", "Unknown"),
                            "cover": b.get("cover", ""),
                            "source": "OpenLibrary",
                            "reason": f"📚 اكتشاف جديد: {topic}",
                            "rating": b.get("rating"),
                            "score": random.uniform(0.8, 0.99), # High score so they appear at top
                            "confidence": random.uniform(0.8, 0.99),
                        }
                        # force_top=True guarantees these fresh books appear in unified_recommendations
                        _add(book_dict, 'interest_results', 'Fresh Discovery', confidence=0.85, reason=f"📚 اكتشاف جديد: {topic}", force_top=True)
                except Exception as e:
                    pass

        current_app.logger.info(f"[FreshInject] After injection: {len(unified_recommendations)} total books")
    except Exception as e:
        current_app.logger.error(f"[FreshInject] Fatal error: {e}")

    # ✅ Keep full pool — re-sampling happens per-request in home_feed()
    random.shuffle(unified_recommendations)

    # Graph Results
    if user_id:
        for book in unified_recommendations:
            if len(book.get('contributing_algorithms', [])) >= 2:
                if len(algo_buckets['graph_results']) < 12:
                    algo_buckets['graph_results'].append(book)

    # 2. Sections (Top Rated etc)
    cat_tasks = [
        {'name': 'most_viewed', 'func': get_most_viewed_books_custom, 'kwargs': {'limit': 20}},
        {'name': 'trending_libs', 'func': get_trending_by_libraries, 'kwargs': {'limit': 20}}
    ]
    # Only add Top Rated if we want it separately.
    # Note: User requirement says "Only in separate top_rated section".
    cat_tasks.insert(0, {'name': 'top_rated', 'func': get_top_rated, 'kwargs': {'limit': 20}})

    cat_results = {}
    app_obj = current_app._get_current_object()
    executor2 = ThreadPoolExecutor(max_workers=3)
    f_to_name = {executor2.submit(run_safe, app_obj, t['func'], **t['kwargs']): t['name'] for t in cat_tasks}
    
    try:
        from concurrent.futures import TimeoutError
        for f in as_completed(f_to_name, timeout=3.0):
            name = f_to_name[f]
            try:
                cat_results[name] = f.result() or []
            except Exception as e:
                current_app.logger.error(f"Section {name} failed: {e}")
                cat_results[name] = []
    except TimeoutError:
        current_app.logger.warning("Category sections hit 3s timeout, returning partial results.")
    finally:
        executor2.shutdown(wait=False)

    return (
        unified_recommendations, 
        algo_buckets, 
        cat_results.get('top_rated', []), 
        cat_results.get('most_viewed', []), 
        cat_results.get('trending_libs', [])
    )

def _refresh_background(app, user_id):
    """Background task to refresh cache."""
    with app.app_context():
        try:
            data = _generate_home_data(user_id)
            cache_key = f"home_recs_{user_id}" if user_id else "home_anon"
            ttl = 90 if user_id else 300
            # Update cache with new timestamp
            cache.set(cache_key, (data, time.time()), timeout=ttl)
            logging.getLogger(__name__).info(f"Background refresh complete for user {user_id}")
        except Exception as e:
            logging.getLogger(__name__).error(f"Background refresh failed: {e}")


@main_bp.route("/browse")
def browse():
    """
    Explore page for specific categories (See All).
    """
    category = request.args.get('category', 'unified')
    limit = 60 # Show more books for browse page
    
    # Imports inside function to avoid circular dependency
    from ..recommender import (
        get_trending, get_top_rated, 
        get_deep_learning_recommendations, get_behavior_based_recommendations,
        get_cf_similar
    )
    from .explore import get_most_viewed_books_custom, get_trending_by_libraries
    from flask import current_app
    
    user_id = current_user.id if current_user.is_authenticated else None
    books = []
    title = "Browse Books"
    description = "Explore our collection"

    if category == 'top_rated':
        title = "Highest Rated by Community"
        description = "Books with the highest average ratings from our users."
        books = get_top_rated(limit=limit)
        
    elif category == 'most_viewed':
        title = "Most Viewed This Week"
        description = "The most popular books currently being viewed by our community."
        books = get_most_viewed_books_custom(limit=limit)
        
    elif category == 'trending_libs':
        title = "Trending in User Libraries"
        description = "Books that are frequently being added to user collections recently."
        books = get_trending_by_libraries(limit=limit)
        
    elif category == 'unified':
        title = "Unified AI Picks"
        description = "Top recommendations curated by our specific AI ensemble for you."
        if user_id:
            try:
                from concurrent.futures import ThreadPoolExecutor
                from ..recommender import get_topic_based # Import here


                # Helper to run safely
                def run_safe(app, func, *args, **kwargs):
                    try: 
                        with app.app_context():
                            res = func(*args, **kwargs)
                            # Ensure result is a list
                            # get_topic_based returns dict with 'books' key
                            if isinstance(res, dict) and 'books' in res:
                                return res['books']
                            return res if isinstance(res, list) else []
                    except Exception as e:
                        logger.error(f"Error in browse thread: {e}") 
                        return []
                
                app_obj = current_app._get_current_object()
                with ThreadPoolExecutor(max_workers=4) as executor:
                    f1 = executor.submit(run_safe, app_obj, get_behavior_based_recommendations, user_id, limit=30, randomize=True)
                    f2 = executor.submit(run_safe, app_obj, get_deep_learning_recommendations, user_id, limit=30, randomize=True)
                    f3 = executor.submit(run_safe, app_obj, get_cf_similar, user_id, top_n=30, randomize=True)
                    f4 = executor.submit(run_safe, app_obj, get_topic_based, user_id, limit=30, randomize=True) # Added Interest Match
                    
                    res1 = f1.result(timeout=15) or []
                    res2 = f2.result(timeout=15) or []
                    res3 = f3.result(timeout=15) or []
                    res4 = f4.result(timeout=15) or []
                    
                    logger.info(f"Browse Debug: Hybrid={len(res1)}, DL={len(res2)}, CF={len(res3)}, Topic={len(res4)}")

                    # Combine and deduplicate
                    combined = res1 + res2 + res3 + res4
                    seen = set()
                    books = []
                    
                    # Helper to safely get ID/score from dict or object
                    def get_val(item, key, default=None):
                        if isinstance(item, dict):
                            return item.get(key, default)
                        else:
                            return getattr(item, key, default)

                    for b in combined:
                        if not b: continue
                        bid = get_val(b, 'id')
                        if bid and bid not in seen:
                            seen.add(bid)
                            books.append(b)
                    
                    # Sort by score/confidence safely with float conversion
                    def safe_score(x):
                        try:
                            val = get_val(x, 'score', 0) or get_val(x, 'confidence', 0)
                            return float(val)
                        except (ValueError, TypeError):
                            return 0.0

                    # 1. Sort by Score first to get quality
                    books.sort(key=safe_score, reverse=True)
                    
                    # Randomization logic: Shuffling disabled for static feel on most algos
                    # Only Interest Match (Topic) contributes dynamic content now
                    # (Keep the sorted order by AI quality)
                    books = books[:offset+limit+20] # Take sufficient buffer
                    
                    logger.info(f"Browse Debug: Post-Shuffle Count={len(books)}")

            except Exception as e:
                 logger.error(f"Browse Sort/Processing Error: {e}", exc_info=True)
                 # If sort fails, we still have 'books' populated (hopefully)
                 if not books:
                     books = []
            
            # Fallback if AI fails or returns nothing
            if not books:
                 logger.warning("Browse Debug: Triggering Fallback to Trending")
                 books = get_trending(limit=limit)
                 logger.info(f"Browse Debug: Fallback Count={len(books)}")
            
            # Additional Random Shuffle if results are small to force change
            if len(books) > 0 and len(books) < 20:
                 random.shuffle(books)

        else:
             books = get_trending(limit=limit)

    return render_template("browse.html", books=books, title=title, description=description)


# ---------------------------------------------------------------------------
#                 خوارزمية Collaborative Filtering
# ---------------------------------------------------------------------------
def get_cf_recommendations(user_id: int, top_n: int = 8):
    try:
        ratings = UserRatingCF.query.all()
        if not ratings: return []

        rows = [{"user_id": r.user_id, "google_id": r.google_id, "rating": float(r.rating)} for r in ratings]
        df = pd.DataFrame(rows)

        if df.empty or len(df) < 2: return []

        pivot = df.pivot_table(index="user_id", columns="google_id", values="rating", aggfunc="mean").fillna(0.0)
        if user_id not in pivot.index: return []

        u_vec = pivot.loc[user_id].values.astype(np.float32)
        u_norm = np.linalg.norm(u_vec) + 1e-8
        all_mat = pivot.values.astype(np.float32)
        norms = np.linalg.norm(all_mat, axis=1) + 1e-8
        sims = (all_mat @ u_vec) / (norms * u_norm)

        sim_series = pd.Series(sims, index=pivot.index)
        sim_series = sim_series.drop(labels=[user_id], errors="ignore")
        sim_series = sim_series.sort_values(ascending=False).head(10)

        if sim_series.empty: return []

        sim_users = sim_series.index.values
        sim_scores = sim_series.values
        sim_matrix = pivot.loc[sim_users].values
        weighted = sim_matrix.T @ sim_scores
        scores = pd.Series(weighted, index=pivot.columns)
        
        user_rated = df[df["user_id"] == user_id]["google_id"].unique()
        scores = scores.drop(labels=list(user_rated), errors="ignore")
        
        scores = scores.sort_values(ascending=False).head(top_n)
        recommended_ids = list(scores.index)

        if not recommended_ids: return []

        recommended_books = []
        for gid in recommended_ids:
            book_sample = Book.query.filter_by(google_id=gid).first()
            if book_sample: recommended_books.append(book_sample)
                
        return recommended_books
    except Exception as e:
        print(f"CF Error: {e}")
        return []


# ---------------------------------------------------------------------------
#                           مكتبة المستخدم (كتبي)
# ---------------------------------------------------------------------------

# في ملف routes/main.py
# تأكد من استيراد دالة normalize_text إذا وضعتها في utils
# from ..utils import normalize_text 
# أو إذا وضعتها في نفس الملف كدالة عادية، اتركها كما هي.

@main_bp.get("/books")
@login_required
def books():
    # المدخلات من الـ GET
    q      = request.args.get("q", "").strip()
    sort   = request.args.get("sort", "")
    source = request.args.get("source", "")

    # 1) قاعدة البحث الأساسية (بدون فلترة العنوان هنا)
    query = Book.query.filter_by(owner_id=current_user.id)

    # ============ الفلترة حسب المصدر ============
    if source == "google":
        query = query.filter(Book.google_id.isnot(None))
    elif source == "local":
        query = query.filter(Book.google_id.is_(None))

    # ============ الفرز ============
    if sort == "new":
        query = query.order_by(Book.created_at.desc())
    elif sort == "alpha":
        query = query.order_by(Book.title.asc())
    elif sort == "rating":
        query = query.outerjoin(UserRatingCF, UserRatingCF.google_id == Book.google_id)
        query = query.group_by(Book.id)
        query = query.order_by(db.func.avg(UserRatingCF.rating).desc())
    
    # جلب جميع الكتب المطابقة للشروط السابقة
    my_books = query.all()

    # ============ 🔥 الإصلاح هنا: البحث الذكي داخل بايثون ============
    if q:
        # تعريف دالة التوحيد هنا إذا لم تستوردها من utils
        import re
        def normalize_local(text):
            if not text: return ""
            text = str(text).lower().strip()
            text = re.sub("[أإآ]", "ا", text)
            text = re.sub("ة", "ه", text)
            text = re.sub("ى", "ي", text)
            return text

        search_term = normalize_local(q)
        
        # تصفية القائمة يدوياً لضمان ظهور النتائج بغض النظر عن الهمزات
        filtered_books = []
        for book in my_books:
            book_title_norm = normalize_local(book.title)
            book_author_norm = normalize_local(book.author)
            
            # البحث في العنوان أو اسم المؤلف
            if search_term in book_title_norm or search_term in book_author_norm:
                filtered_books.append(book)
        
        my_books = filtered_books

    # ============ القوائم الثلاث (المفضلة وغيرها) ============
    statuses = BookStatus.query.filter_by(user_id=current_user.id).all()
    
    # 🆕 إنشاء قاموس للحالات والتقدم
    status_map = {}
    for s in statuses:
        status_map[s.book_id] = {
            'status': s.status,
            'progress': s.reading_progress or 0,
            'last_read': s.last_read_at,
            'created_at': s.created_at
        }

    favorites_ids = [s.book_id for s in statuses if s.status == "favorite"]
    later_ids     = [s.book_id for s in statuses if s.status == "later"]
    finished_ids  = [s.book_id for s in statuses if s.status == "finished"]
    reading_ids   = [s.book_id for s in statuses if s.status == "reading"]
    on_hold_ids   = [s.book_id for s in statuses if s.status == "on_hold"]
    dropped_ids   = [s.book_id for s in statuses if s.status == "dropped"]

    favorites = Book.query.filter(Book.id.in_(favorites_ids)).all() if favorites_ids else []
    later     = Book.query.filter(Book.id.in_(later_ids)).all()     if later_ids else []
    finished  = Book.query.filter(Book.id.in_(finished_ids)).all()  if finished_ids else []
    reading_books = Book.query.filter(Book.id.in_(reading_ids)).all() if reading_ids else []
    on_hold_books = Book.query.filter(Book.id.in_(on_hold_ids)).all() if on_hold_ids else []
    dropped_books = Book.query.filter(Book.id.in_(dropped_ids)).all() if dropped_ids else []
    
    # 🆕 إضافة بيانات الحالة والتقدم لكل كتاب
    for book in my_books:
        book_status_data = status_map.get(book.id, {})
        book.status = book_status_data.get('status')
        book.reading_progress = book_status_data.get('progress', 0)
        book.last_read_at = book_status_data.get('last_read')
        book.status_created_at = book_status_data.get('created_at')
        
        # حساب وقت القراءة المقدر (بافتراض 2 دقيقة لكل صفحة)
        if book.page_count:
            book.estimated_read_time = book.page_count * 2  # دقائق
        else:
            book.estimated_read_time = None
    
    # 🆕 إحصائيات القراءة الشاملة
    reading_stats = {
        'total_books': len(my_books),
        'finished_count': len(finished_ids),
        'favorite_count': len(favorites_ids),
        'later_count': len(later_ids),
        'reading_count': len(reading_ids),
        'on_hold_count': len(on_hold_ids),
        'dropped_count': len(dropped_ids),
        'in_progress': len([b for b in my_books if status_map.get(b.id, {}).get('progress', 0) > 0 and status_map.get(b.id, {}).get('progress', 0) < 100]),
        'total_pages': sum(b.page_count or 0 for b in my_books),
        'avg_progress': round(sum(status_map.get(b.id, {}).get('progress', 0) for b in my_books) / max(len(my_books), 1), 1)
    }
    
    # 🆕 جمع التصنيفات الفريدة للفلترة
    all_categories = set()
    all_languages = set()
    for book in my_books:
        if book.categories:
            for cat in book.categories.split(','):
                all_categories.add(cat.strip())
        if book.language:
            all_languages.add(book.language)

    # ============ توصيات الذكاء الاصطناعي (Deep Learning) ============
    recs = get_deep_learning_recommendations(current_user.id, limit=8)
    
    # ============ المكتبات الخمس ============
    from ..recommender import get_all_libraries_showcase, get_hybrid_recommendations, get_author_books # Added imports
    library_sections = get_all_libraries_showcase(query="programming books", limit_per_source=8)

    return render_template(
        "books.html",
        books=my_books,
        favorites=favorites,
        later=later,
        finished=finished,
        reading_books=reading_books,
        on_hold_books=on_hold_books,
        dropped_books=dropped_books,
        cf_recs=recs,
        library_sections=library_sections,
        reading_stats=reading_stats,
        all_categories=sorted(all_categories),
        all_languages=sorted(all_languages)
    )


@main_bp.route("/books/<int:book_id>")
@login_required
def book_detail(book_id):
    book = Book.query.get_or_404(book_id)

    # 🆕 تسجيل المشاهدة (Implicit Tracking)
    try:
        log_user_view(current_user.id, book)
    except Exception as e:
        logger.error(f"Failed to log view: {e}")
    
    # التحقق من الملكية (اختياري - حسب منطق التطبيق)
    # هنا نسمح برؤية أي كتاب، لكن التعديل مقيد
    
    # جلب تقييم المستخدم
    user_rating = UserRatingCF.query.filter_by(user_id=current_user.id, google_id=book.google_id).first()
    
    # جلب حالة الكتاب
    book_status_obj = BookStatus.query.filter_by(user_id=current_user.id, book_id=book.id).first()
    book_status = book_status_obj.status if book_status_obj else None
    
    # ---------------------------------------------------------
    # 🆕 التوصيات الهجينة (Hybrid Recommendations)
    # ---------------------------------------------------------
    from ..recommender import get_hybrid_recommendations, get_author_books

    # 1. كتب قد تعجبك (You Might Also Like)
    similar = get_hybrid_recommendations(current_user.id, book, limit=12)

    # 2. المزيد لنفس المؤلف (More by this Author)
    author_books = []
    if book.author and book.author != "Unknown":
         author_books = get_author_books(book.author, exclude_book_id=book.google_id, limit=8)

    # جلب تفاصيل إضافية وتحديث قاعدة البيانات إذا كانت ناقصة
    if book.google_id:
        try:
            from ..utils import fetch_book_details
            details = fetch_book_details(book.google_id)
            if details:
                # تحديث قاعدة البيانات
                changed = False
                if not book.published_date and details.get('publishedDate'):
                    book.published_date = details.get('publishedDate')
                    changed = True
                if not book.page_count and details.get('pageCount'):
                    book.page_count = details.get('pageCount')
                    changed = True
                if not book.categories and details.get('categories'):
                    # Convert list to string safely
                    cats = details.get('categories')
                    if isinstance(cats, list):
                        book.categories = ", ".join(cats)
                    else:
                        book.categories = str(cats)
                    changed = True
                if not book.publisher and details.get('publisher'):
                    book.publisher = details.get('publisher')
                    changed = True
                if not book.language and details.get('language'):
                    book.language = details.get('language')
                    changed = True
                
                # تخزين التقييم العالمي للعرض فقط (غير موجود في جدول الكتب)
                setattr(book, 'global_rating', details.get('rating'))
                setattr(book, 'global_ratings_count', details.get('ratingsCount'))

                if changed:
                    db.session.commit()
        except Exception as e:
            logger.error(f"Error fetching extra book details: {e}")

    # جلب المراجعات (للكتب المشتركة عبر Google ID)
    reviews = []
    if book.google_id:
        reviews = BookReview.query.filter_by(google_id=book.google_id).order_by(BookReview.created_at.desc()).limit(20).all()

    # جلب اقتباسات المستخدم
    quotes = BookQuote.query.filter_by(user_id=current_user.id, book_id=book.id).order_by(BookQuote.created_at.desc()).all()

    return render_template(
        "book_detail.html",
        book=book,
        user_rating=user_rating,
        book_status=book_status,
        status_entry=book_status_obj,
        similar=similar,
        author_books=author_books,
        reviews=reviews,
        quotes=quotes
    )


@main_bp.post("/books/<int:book_id>/notes")
@login_required
def save_notes(book_id):
    book = Book.query.get_or_404(book_id)
    if book.owner_id != current_user.id:
        # Check if user owns logic or return 403
        flash("غير مصرح لك بتعديل ملاحظات هذا الكتاب", "danger")
        return redirect(url_for("main.book_detail", book_id=book.id))
    
    notes = request.form.get("notes")
    book.notes = notes
    db.session.commit()
    flash("تم حفظ الملاحظات بنجاح ✨", "success")
    return redirect(url_for("main.book_detail", book_id=book.id))


@main_bp.route("/books/<int:book_id>/read")
@login_required
def book_read(book_id):
    book = Book.query.get_or_404(book_id)
    
    # 1. إذا كان هناك ملف محلي/رابط مباشر، نوجه المستخدم إليه
    if book.file_url:
        return redirect(book.file_url)
    
    # 2. إذا كان كتاب Google، نستخدم القارئ المدمج
    if book.google_id:
        # يمكننا إعادة توجيه المستخدم لصفحة القارئ العام
        # أو عرض نفس القالب هنا
        vi = {}
        target_link = ""
        try: 
            # محاولة جلب رابط المعاينة
            from ..utils import fetch_book_details
            d = fetch_book_details(book.google_id)
            if d:
                vi = d.get("volumeInfo", {})
                target_link = vi.get("previewLink") or vi.get("infoLink")
        except: pass
        
        return render_template(
            "reader_frame.html", 
            book_title=book.title, 
            book_id=book.google_id,
            external_link=target_link
        )

    flash("لا يوجد ملف للقراءة لهذا الكتاب.", "warning")
    return redirect(url_for("main.book_detail", book_id=book.id))



@main_bp.post("/books/<int:book_id>/status/<status>")
@csrf.exempt
@login_required
def set_book_status(book_id, status):
    allowed_statuses = ['favorite', 'later', 'finished', 'reading', 'on_hold', 'dropped']
    if status not in allowed_statuses:
        flash("حالة غير معروفة", "danger")
        return redirect(url_for("main.book_detail", book_id=book_id))
        
    book = Book.query.get_or_404(book_id)
    
    # التقاط الوقت الحالي
    from datetime import datetime
    now = datetime.utcnow()

    # التحقق هل الحالة موجودة مسبقاً
    s = BookStatus.query.filter_by(user_id=current_user.id, book_id=book.id).first()
    
    if s:
        # إذا ضغط نفس الحالة -> حذف (Toggle)
        if s.status == status:
            db.session.delete(s)
            flash(f"تمت إزالة الكتاب من قائمة {status}", "info")
        else:
            # منطق تحديث التواريخ
            if status == 'reading' and s.status != 'reading':
                if not s.started_at:
                    s.started_at = now
            
            if status == 'finished' and s.status != 'finished':
                s.finished_at = now
                s.reading_progress = 100
            elif status != 'finished' and s.status == 'finished':
                s.finished_at = None # إعادة تعيين إذا خرج من المنتهية
                if status == 'reading':
                     s.reading_progress = s.reading_progress # Keep as is or reset? Usually keep.
                else:
                     pass

            # تغيير الحالة
            s.status = status
            flash(f"تم تغيير الحالة إلى {status}", "success")
    else:
        # إنشاء حالة جديدة
        s = BookStatus(user_id=current_user.id, book_id=book.id, status=status)
        
        if status == 'reading':
            s.started_at = now
        elif status == 'finished':
            s.finished_at = now
            s.reading_progress = 100
            
        db.session.add(s)
        flash(f"تمت الإضافة إلى قائمة {status}", "success")
        
    db.session.commit()
    # return redirect(url_for("main.books"))
    return redirect(request.referrer or url_for("main.books"))


@main_bp.post("/books/<int:book_id>/progress")
@csrf.exempt
@login_required
def update_reading_progress(book_id):
    """تحديث نسبة تقدم القراءة للكتاب"""
    from flask import jsonify
    from datetime import datetime
    
    book = Book.query.get_or_404(book_id)
    
    try:
        progress = int(request.form.get("progress") or request.json.get("progress", 0))
    except (ValueError, TypeError):
        progress = 0
    
    # ضمان أن النسبة بين 0 و 100
    progress = max(0, min(100, progress))
    
    # البحث عن حالة الكتاب أو إنشاء واحدة جديدة
    status = BookStatus.query.filter_by(user_id=current_user.id, book_id=book.id).first()
    
    if not status:
        status = BookStatus(user_id=current_user.id, book_id=book.id, status="later")
        db.session.add(status)
    
    status.reading_progress = progress
    status.last_read_at = datetime.utcnow()
    
    # إذا وصل لـ 100% تلقائياً نحوله لـ finished
    if progress >= 100 and status.status != "finished":
        status.status = "finished"
    
    db.session.commit()
    
    return jsonify({
        "success": True,
        "progress": progress,
        "status": status.status
    })

@main_bp.post("/books/<int:book_id>/rate")
@login_required
def rate_book(book_id: int):
    book = Book.query.get_or_404(book_id)
    if not book.google_id:
        flash("لا يمكن تقييم كتاب محلي (بدون Google ID) لنظام التوصيات.", "warning")
        return redirect(url_for("main.book_detail", book_id=book.id))

    try: value = float(request.form.get("rating") or 0)
    except ValueError: value = 0.0
    if value < 1: value = 1
    if value > 5: value = 5

    r = UserRatingCF.query.filter_by(user_id=current_user.id, google_id=book.google_id).first()
    if r is None:
        r = UserRatingCF(user_id=current_user.id, google_id=book.google_id, rating=value)
        db.session.add(r)
        msg = "تم إضافة التقييم."
    else:
        r.rating = value
        msg = "تم تحديث التقييم."
    db.session.commit()
    flash(msg, "success")
    return redirect(url_for("main.book_detail", book_id=book.id))


@main_bp.post("/books/create")
@login_required
def create_book():
    b = Book(
        title=request.form.get("title"), author=request.form.get("author"),
        description=request.form.get("description"), cover_url=request.form.get("cover_url") or None,
        file_url=request.form.get("file_url") or None, owner_id=current_user.id
    )
    db.session.add(b); db.session.commit()
    flash("تمت إضافة الكتاب", "success")
    return redirect(url_for("main.books"))


@main_bp.post("/books/<int:book_id>/update")
@login_required
def update_book(book_id: int):
    b = Book.query.get_or_404(book_id)
    if b.owner_id != current_user.id:
        flash("ليس لديك صلاحية", "danger"); return redirect(url_for("main.books"))
    b.title = request.form.get("u_title"); b.author = request.form.get("u_author")
    b.description = request.form.get("u_description"); b.cover_url = request.form.get("u_cover_url") or None
    b.file_url = request.form.get("u_file_url") or None
    db.session.commit(); flash("تم التحديث", "success")
    return redirect(url_for("main.books"))


@main_bp.post("/books/<int:book_id>/generate_cover")
@login_required
def generate_book_cover(book_id):
    """توليد غلاف للكتاب باستخدام AI"""
    book = Book.query.get_or_404(book_id)
    
    # التحقق من الملكية
    if book.owner_id != current_user.id:
        flash("غير مصرح لك بتعديل هذا الكتاب", "danger")
        return redirect(url_for("main.book_detail", book_id=book.id))
    
    # استدعاء دالة التوليد
    from ..utils import generate_ai_cover_url
    new_cover = generate_ai_cover_url(book.title, book.author)
    
    if new_cover:
        book.cover_url = new_cover
        db.session.commit()
        flash("تم توليد الغلاف بنجاح ✨", "success")
    else:
        flash("فشل توليد الغلاف", "error")
        
    return redirect(url_for("main.book_detail", book_id=book.id))


@main_bp.post("/books/<int:book_id>/delete")
@login_required
def delete_book(book_id: int):
    b = Book.query.get_or_404(book_id)
    if b.owner_id != current_user.id:
        flash("ليس لديك صلاحية", "danger"); return redirect(url_for("main.books"))
    db.session.delete(b); db.session.commit(); flash("تم الحذف", "info")
    return redirect(url_for("main.books"))


# ---------------------------------------------------------------------------
#                 إدارة الاقتباسات (Quotes)
# ---------------------------------------------------------------------------

@main_bp.post("/books/<int:book_id>/quotes")
@csrf.exempt
@login_required
def save_quote(book_id):
    """حفظ اقتباس جديد للكتاب"""
    from flask import jsonify
    
    book = Book.query.get_or_404(book_id)
    
    data = request.get_json() if request.is_json else request.form
    quote_text = data.get("quote_text", "").strip()
    
    if not quote_text:
        return jsonify({"success": False, "error": "الاقتباس فارغ"}), 400
    
    page_number = data.get("page_number")
    if page_number:
        try:
            page_number = int(page_number)
        except ValueError:
            page_number = None
    
    quote = BookQuote(
        user_id=current_user.id,
        book_id=book.id,
        google_id=book.google_id,
        quote_text=quote_text,
        page_number=page_number
    )
    db.session.add(quote)
    db.session.commit()
    
    return jsonify({
        "success": True,
        "quote": {
            "id": quote.id,
            "text": quote.quote_text,
            "page": quote.page_number,
            "created_at": quote.created_at.strftime("%Y-%m-%d %H:%M")
        }
    })


@main_bp.delete("/quotes/<int:quote_id>")
@csrf.exempt
@login_required
def delete_quote(quote_id):
    """حذف اقتباس"""
    from flask import jsonify
    
    quote = BookQuote.query.get_or_404(quote_id)
    
    if quote.user_id != current_user.id:
        return jsonify({"success": False, "error": "غير مصرح"}), 403
    
    db.session.delete(quote)
    db.session.commit()
    
    return jsonify({"success": True})


@main_bp.get("/books/<int:book_id>/quotes")
@login_required
def get_quotes(book_id):
    """جلب اقتباسات الكتاب"""
    from flask import jsonify
    
    book = Book.query.get_or_404(book_id)
    
    quotes = BookQuote.query.filter_by(
        user_id=current_user.id,
        book_id=book.id
    ).order_by(BookQuote.created_at.desc()).all()
    
    return jsonify({
        "success": True,
        "quotes": [{
            "id": q.id,
            "text": q.quote_text,
            "page": q.page_number,
            "created_at": q.created_at.strftime("%Y-%m-%d %H:%M")
        } for q in quotes]
    })


# ... (باقي الكود كما هو) ...

# دالة الاستيراد المحدثة (مع الذكاء الاصطناعي)
@main_bp.post("/import/<gid>")
@csrf.exempt
@login_required
def import_book_generic(gid):
    # 1. جلب البيانات من المصدر المناسب
    data = None
    if gid.startswith("gut_"): data = fetch_gutenberg_detail(gid)
    elif gid.startswith("ia_"): data = fetch_archive_detail(gid)
    elif gid.startswith("ol_"): data = fetch_openlib_detail(gid)
    elif gid.isdigit() and len(gid) == 13: data = fetch_itbook_detail(gid)
    else: data = fetch_book_details(gid) # Google Books

    if not data:
        flash("فشل جلب بيانات الكتاب.", "danger")
        return redirect(url_for("explore.index")) # تم تعديل التوجيه لصفحة الاستكشاف

    # 2. التحقق من التكرار
    exists = Book.query.filter_by(owner_id=current_user.id, google_id=gid).first()
    if exists:
        flash("الكتاب موجود لديك مسبقاً.", "info")
        return redirect(url_for("main.books"))

    # 3. استخراج البيانات (التصحيح هنا) 🛠️
    # تهيئة المتغيرات
    title = data.get("title")
    author = data.get("author")
    desc = data.get("desc") or data.get("description")
    cover = data.get("cover")

    # معالجة خاصة لـ Google Books (لأن البيانات تكون داخل volumeInfo)
    if "volumeInfo" in data:
        vi = data["volumeInfo"]
        title = vi.get("title")
        author = ", ".join(vi.get("authors", [])) if vi.get("authors") else "Unknown"
        desc = vi.get("description")
        
        # استخراج الصورة من Google
        imgs = vi.get("imageLinks", {})
        cover = imgs.get("thumbnail") or imgs.get("smallThumbnail")

    # تحسين الروابط (تأكد أنها https)
    if cover and cover.startswith("http://"):
        cover = cover.replace("http://", "https://")

    # القيم الافتراضية إذا فشل كل شيء
    final_title = title or "Untitled"
    final_author = author or "Unknown"

    # إنشاء كائن الكتاب
    book = Book(
        title=final_title, 
        author=final_author, 
        description=desc, 
        cover_url=cover,
        owner_id=current_user.id, 
        google_id=gid 
    )

    db.session.add(book)
    db.session.commit()

    # 4. الذكاء الاصطناعي: حفظ البصمة (Embedding) تلقائياً
    try:
        generate_book_embedding_if_missing(book)
    except Exception as e:
        print(f"[AI Embedding] Non-critical error: {e}")

    flash("تمت الإضافة للمكتبة بنجاح.", "success")
    # توجيه المستخدم لمكتبته ليرى الكتاب الجديد
    return redirect(url_for("main.books"))


# ---------------------------------------------------------------------------
#                 (تم حذف البحث الذكي بناءً على الطلب)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
#                 مساعد AI للكتب (Chatbot)
# ---------------------------------------------------------------------------

@main_bp.post("/ai/chat")
@csrf.exempt
def ai_chat():
    """
    API endpoint للمساعد الذكي
    يستقبل رسالة المستخدم ويرد بتوصيات كتب
    """
    try:
        data = request.get_json() or {}
        user_message = data.get("message", "").strip()
        
        if not user_message:
            return {
                "reply": "مرحباً! أنا مكتبي، مساعدك الذكي للكتب 📚 كيف يمكنني مساعدتك؟",
                "books": []
            }
        
        # جمع سياق المستخدم
        user_context = None
        if current_user.is_authenticated:
            # جلب اهتمامات المستخدم
            prefs = UserPreference.query.filter_by(user_id=current_user.id).order_by(
                UserPreference.weight.desc()
            ).limit(5).all()
            
            # جلب آخر الكتب
            recent_books = Book.query.filter_by(owner_id=current_user.id).order_by(
                Book.created_at.desc()
            ).limit(3).all()
            
            user_context = {
                "interests": [p.topic for p in prefs],
                "recent_books": [b.title for b in recent_books]
            }
        
        # استدعاء AI
        result = chat_with_ai(user_message, user_context)
        
        return {
            "reply": result.get("reply", ""),
            "books": result.get("books", [])
        }
        
    except Exception as e:
        print(f"[AI Chat Route] Error: {e}")
        return {
            "reply": "عذراً، حدث خطأ. يرجى المحاولة مرة أخرى.",
            "books": []
        }, 500


