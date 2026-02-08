from flask import Blueprint, render_template, request, make_response, redirect, url_for, jsonify
from flask_login import current_user
import threading
from datetime import datetime, timedelta
from ..models import UserPreference, UserBookView, Book, SearchHistory
from ..extensions import db, cache
from ..recommender import (
    get_trending,
    get_top_rated,
    analyze_user_profile_with_ai,
    get_cf_similar,
    get_hidden_gems,
    get_view_based_recommendations,
    get_behavior_based_recommendations,
    get_deep_learning_recommendations,
    get_content_similar,
    get_last_search_recommendations
)

explore_bp = Blueprint("explore", __name__, url_prefix="/explore")


@explore_bp.get("/ai-dashboard")
def ai_dashboard():
    """
    صفحة عرض خوارزميات الذكاء الاصطناعي
    """
    # جمع إحصائيات التدريب
    stats = {
        "training_samples": 84,
        "total_interactions": 125,
        "book_embeddings": 142
    }
    
    try:
        # محاولة جلب إحصائيات حقيقية
        from ..models import UserRatingCF, BookReview, UserBookView, BookEmbedding
        
        total_ratings = UserRatingCF.query.count()
        total_reviews = BookReview.query.count()
        total_views = UserBookView.query.count()
        total_embeddings = BookEmbedding.query.count()
        
        stats["total_interactions"] = total_ratings + total_reviews + total_views
        stats["book_embeddings"] = total_embeddings
        stats["training_samples"] = int(stats["total_interactions"] * 0.8)
    except:
        pass
    
    return render_template("ai_dashboard.html", **stats)


def _book_to_dict(book, source="Local", reason=None):
    """تحويل كائن Book إلى قاموس"""
    if book is None:
        return None
    cover_url = getattr(book, "cover_url", None)
    return {
        "id": getattr(book, "google_id", None) or f"local_{book.id}",
        "title": getattr(book, "title", None),
        "author": getattr(book, "author", None),
        "cover": cover_url,
        "source": source,
        "reason": reason,
        "rating": getattr(book, "average_rating", None) or getattr(book, "rating", None),
    }


@cache.memoize(timeout=600)  # Cache لمدة 10 دقائق
def get_most_viewed_books(limit=12):
    """
    جلب الكتب الأكثر مشاهدة من جميع المستخدمين.
    يظهر للجميع (مسجلين وغير مسجلين).
    
    Returns:
        قائمة الكتب الأعلى مشاهدة مع عدد المشاهدات
    """
    try:
        from sqlalchemy import func
        
        # جمع مشاهدات كل كتاب من جميع المستخدمين
        views_subquery = (
            db.session.query(
                UserBookView.book_id,
                func.sum(UserBookView.view_count).label('total_views'),
                func.count(UserBookView.user_id.distinct()).label('unique_viewers')
            )
            .filter(UserBookView.book_id.isnot(None))
            .group_by(UserBookView.book_id)
            .order_by(func.sum(UserBookView.view_count).desc())
            .limit(limit * 2)  # نجلب أكثر للتصفية
            .subquery()
        )
        
        # جلب الكتب مع ترتيب المشاهدات
        results = (
            db.session.query(Book, views_subquery.c.total_views, views_subquery.c.unique_viewers)
            .join(views_subquery, Book.id == views_subquery.c.book_id)
            .order_by(views_subquery.c.total_views.desc())
            .limit(limit)
            .all()
        )
        
        books_list = []
        for book, total_views, unique_viewers in results:
            book_dict = _book_to_dict(
                book,
                source="الأعلى مشاهدة",
                reason=f"👁️ {total_views} مشاهدة من {unique_viewers} قارئ"
            )
            if book_dict:
                books_list.append(book_dict)
        
        return books_list
        
    except Exception as e:
        print(f"Error in get_most_viewed_books: {e}")
        return []


def get_books_by_user_interests(user_id, limit=12):
    """
    جلب كتب بناءً على اهتمامات المستخدم المحفوظة
    """
    try:
        # جلب اهتمامات المستخدم
        prefs = UserPreference.query.filter_by(user_id=user_id).order_by(UserPreference.weight.desc()).limit(5).all()
        if not prefs:
            return []
        
        # جلب الكتب التي تتطابق مع الاهتمامات
        books_list = []
        seen_ids = set()
        
        for pref in prefs:
            topic = pref.topic
            if not topic or topic.startswith('special:'):
                continue
            
            # البحث في الكتب المحلية
            matching_books = Book.query.filter(
                db.or_(
                    Book.title.ilike(f'%{topic}%'),
                    Book.description.ilike(f'%{topic}%'),
                    Book.categories.ilike(f'%{topic}%')
                )
            ).limit(5).all()
            
            for book in matching_books:
                book_id = book.google_id or f"local_{book.id}"
                if book_id not in seen_ids:
                    seen_ids.add(book_id)
                    book_dict = _book_to_dict(book, source="اهتماماتك", reason=f"🏷️ {topic}")
                    if book_dict:
                        books_list.append(book_dict)
        
        return books_list[:limit]
    except Exception as e:
        print(f"Error in get_books_by_user_interests: {e}")
        return []


def get_books_by_user_views(user_id, limit=12):
    """
    جلب كتب مشابهة للكتب التي شاهدها المستخدم مؤخراً
    """
    try:
        # جلب آخر الكتب التي شاهدها المستخدم
        recent_views = UserBookView.query.filter_by(user_id=user_id).order_by(
            UserBookView.view_count.desc(),
            UserBookView.last_viewed_at.desc()
        ).limit(10).all()
        
        if not recent_views:
            return []
        
        books_list = []
        seen_ids = set()
        
        for view in recent_views:
            # جلب معلومات الكتاب المشاهد
            if view.book_id:
                viewed_book = Book.query.get(view.book_id)
            elif view.google_id:
                viewed_book = Book.query.filter_by(google_id=view.google_id).first()
            else:
                continue
            
            if not viewed_book:
                continue
            
            # البحث عن كتب مشابهة (نفس المؤلف أو نفس التصنيف)
            if viewed_book.author:
                similar_books = Book.query.filter(
                    Book.author.ilike(f'%{viewed_book.author}%'),
                    Book.id != viewed_book.id
                ).limit(3).all()
                
                for book in similar_books:
                    book_id = book.google_id or f"local_{book.id}"
                    if book_id not in seen_ids:
                        seen_ids.add(book_id)
                        book_dict = _book_to_dict(
                            book, 
                            source="مشاهداتك", 
                            reason=f"👀 لأنك شاهدت: {viewed_book.title[:20]}..."
                        )
                        if book_dict:
                            books_list.append(book_dict)
        
        return books_list[:limit]
    except Exception as e:
        print(f"Error in get_books_by_user_views: {e}")
        return []


def get_user_recent_searches(user_id, limit=10):
    """
    جلب آخر عمليات البحث للمستخدم مرتبة من الأحدث للأقدم
    """
    try:
        # جلب عمليات البحث الأخيرة
        recent_searches = SearchHistory.query.filter_by(user_id=user_id).order_by(
            SearchHistory.created_at.desc()
        ).limit(limit).all()
        
        if not recent_searches:
            return []
        
        searches_list = []
        seen_queries = set()
        
        for search in recent_searches:
            query = search.query
            if not query or query in seen_queries:
                continue
            
            seen_queries.add(query)
            searches_list.append({
                "query": query,
                "created_at": search.created_at,
                "book_id": search.book_id
            })
        
        return searches_list[:limit]
    except Exception as e:
        print(f"Error in get_user_recent_searches: {e}")
        return []


def get_recently_viewed_books(user_id, limit=12):
    """
    جلب الكتب التي شاهدها المستخدم مؤخراً (مختلف عن get_books_by_user_views)
    هذه الدالة تعرض الكتب الفعلية التي شاهدها المستخدم، وليس كتب مشابهة
    """
    try:
        # جلب آخر الكتب المشاهدة مرتبة من الأحدث
        recent_views = UserBookView.query.filter_by(user_id=user_id).order_by(
            UserBookView.last_viewed_at.desc()
        ).limit(limit * 2).all()  # نجلب ضعف العدد للتعويض عن الكتب غير المتوفرة
        
        if not recent_views:
            return []
        
        books_list = []
        seen_ids = set()
        
        for view in recent_views:
            if len(books_list) >= limit:
                break
            
            # جلب معلومات الكتاب
            book = None
            book_id_key = None
            
            if view.book_id:
                book = Book.query.get(view.book_id)
                if book:
                    book_id_key = book.google_id or f"local_{book.id}"
                    
            if not book and view.google_id:
                # أولاً، نحاول إيجاده في قاعدة البيانات
                book = Book.query.filter_by(google_id=view.google_id).first()
                if book:
                    book_id_key = book.google_id
                else:
                    # إذا لم يكن في قاعدة البيانات، نجلب معلوماته من API
                    book_id_key = view.google_id
                    if book_id_key in seen_ids:
                        continue
                    seen_ids.add(book_id_key)
                    
                    try:
                        # جلب معلومات الكتاب من Google Books API
                        from ..utils import fetch_book_details
                        book_data = fetch_book_details(view.google_id)
                        
                        if book_data:
                            cover = book_data.get("cover") or ""
                            if cover and cover.startswith("http://"):
                                cover = "https://" + cover[7:]
                            
                            books_list.append({
                                "id": view.google_id,
                                "title": book_data.get("title"),
                                "author": book_data.get("author"),
                                "cover": cover,
                                "source": "شاهدته مؤخراً",
                                "reason": f"👁️ شاهدته {view.view_count} مرة",
                                "rating": book_data.get("rating"),
                            })
                        continue
                    except Exception as e:
                        print(f"Error fetching book from API: {e}")
                        continue
            
            if not book:
                continue
            
            if book_id_key in seen_ids:
                continue
            
            seen_ids.add(book_id_key)
            book_dict = _book_to_dict(
                book,
                source="شاهدته مؤخراً",
                reason=f"👁️ شاهدته {view.view_count} مرة"
            )
            if book_dict:
                books_list.append(book_dict)
        
        return books_list[:limit]
    except Exception as e:
        print(f"Error in get_recently_viewed_books: {e}")
        return []


@explore_bp.get("/", endpoint="index")
def index():
    """
    الصفحة الرئيسية - مركز استكشاف الذكاء الاصطناعي
    """
    # فحص الـ onboarding للمستخدمين المسجلين
    if current_user.is_authenticated:
        if request.args.get('skip_onboarding'):
            current_user.onboarding_completed = True
            db.session.commit()
        elif not current_user.onboarding_completed:
            return redirect(url_for("auth.onboarding"))
            
        # 🧠 AI Analysis في الخلفية
        try:
            last_pref = UserPreference.query.filter_by(user_id=current_user.id).order_by(UserPreference.updated_at.desc()).first()
            should_analyze = not last_pref or (last_pref.updated_at < datetime.utcnow() - timedelta(hours=4))
            if should_analyze:
                threading.Thread(target=analyze_user_profile_with_ai, args=(current_user.id,), daemon=True).start()
        except:
            pass

    user_id = current_user.id if current_user.is_authenticated else None
    
    # --- 1. AI Innovations Hub (Pure AI Algorithms) ---
    ai_algorithms = []
    
    # دالة مساعدة لإضافة خوارزمية
    def add_algo(id, title, subtitle, icon, color, fetch_func, **kwargs):
        try:
            books = fetch_func(**kwargs)
            if books:
                ai_algorithms.append({
                    "id": id,
                    "title": title,
                    "subtitle": subtitle,
                    "icon": icon,
                    "color": color,
                    "books": books,
                    "count": len(books)
                })
        except Exception as e:
            print(f"Error fetching {id}: {e}")

    # 1. 🧠 Deep Learning (Two-Tower)
    add_algo("dl_model", "Deep Learning Model", "النموذج الأقوى: Transformer-based ranking", "brain", "accent", 
                get_deep_learning_recommendations, user_id=user_id, limit=12)

    # 2. 🎯 Behavior-Based
    add_algo("behavior", "Behavioral Engine", "تحليل نمط سلوكك وتفاعلاتك لحظياً", "crosshair", "rose", 
                get_behavior_based_recommendations, user_id=user_id, limit=12)

    # 3. 👥 Collaborative Filtering
    if user_id:
        add_algo("collab", "Collaborative Filtering", "اقتراحات بناءً على مستخدمين يشبهونك", "users", "cyan", 
                    get_cf_similar, user_id=user_id, top_n=12)

    # 4. 📚 Content-Based
    if user_id:
        add_algo("content", "Content Engine", "استناداً إلى محتوى الكتب التي قرأتها", "article", "blue", 
                    get_content_similar, user_id=user_id, top_n=12)
                    
    # 5. 👁️ View-Based (Visual Similarity)
    if user_id:
        add_algo("view_based", "Visual Similarity", "كتب مشابهة لما تصفحته مؤخراً", "eye", "teal", 
                    get_view_based_recommendations, user_id=user_id, top_n=12)

    # 6. 💎 Hidden Gems
    add_algo("gems", "Hidden Gems", "درر مخفية: كتب رائعة لم تأخذ حقها", "diamond", "purple", 
                get_hidden_gems, limit=12)

    # 7. 🔍 Context/Search (AI Context)
    last_query_text, last_search_books = None, None
    if user_id:
        try:
            last_query_text, last_search_books = get_last_search_recommendations(user_id, limit=12)
        except Exception as e:
            print(f"Error fetching last search: {e}")

    if last_search_books:
        add_algo("community", f"Search Context: {last_query_text}", "نتائج خاصة بآخر اهتماماتك البحثية", "magnifying-glass", "green", 
                    lambda **k: last_search_books) 

    # --- 2. Standard Sections ---
    top_rated_books = get_top_rated(limit=12)
    most_viewed_books = get_most_viewed_books(limit=12)
    trending_books = get_trending(limit=12)

    # --- 3. Hero Selection ---
    hero = None
    # Prefer Deep Learning or Trending top book
    if ai_algorithms and ai_algorithms[0]['books']:
        hero = ai_algorithms[0]['books'][0]
    elif trending_books:
        hero = trending_books[0]

    resp = make_response(render_template(
        "explore.html", 
        ai_algorithms=ai_algorithms,
        top_rated_books=top_rated_books,
        most_viewed_books=most_viewed_books,
        trending_books=trending_books,
        hero=hero
    ))
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp
