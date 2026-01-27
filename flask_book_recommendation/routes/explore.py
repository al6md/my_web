from flask import Blueprint, render_template, request, make_response, redirect, url_for
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
    get_behavior_based_recommendations
)

explore_bp = Blueprint("explore", __name__, url_prefix="/explore")


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
    الصفحة الرئيسية
    """
    hero = None
    sections = []
    
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

    # الأقسام الأساسية للجميع
    trending_books = get_trending(13)
    top_rated = get_top_rated(12)
    
    if trending_books:
        hero = trending_books[0]

    sections = [
        {
            "title": "🔥 الرائج الآن",
            "subtitle": "الأكثر انتشاراً في المكتبات",
            "books": trending_books[1:] if trending_books else [],
            "style": "dark",
            "query": "trending"
        },
        {
            "title": "⭐ أعلى التقييمات",
            "subtitle": "الكتب المفضلة لدى مجتمعنا",
            "books": top_rated,
            "style": "gold",
            "icon": "star",
            "query": "top_rated"
        }
    ]
    
    # للمستخدم المسجل: أقسام إضافية
    if current_user.is_authenticated:
        user_id = current_user.id
        
        # 🧠 مختارات الذكاء الاصطناعي
        try:
            cf_books = get_cf_similar(user_id, top_n=12)
            if cf_books:
                sections.insert(0, {
                    "title": "🧠 مختارات لك",
                    "subtitle": "خوارزمياتنا اختارت لك هذه الكتب",
                    "books": cf_books,
                    "style": "accent",
                    "icon": "brain",
                    "query": "special:cf"
                })
                hero = cf_books[0]
                sections[0]["books"] = cf_books[1:]
        except Exception as e:
            print(f"CF Error: {e}")

        # 🔍 آخر بحثك - عرض سجل البحث
        try:
            recent_searches = get_user_recent_searches(user_id, limit=10)
            if recent_searches:
                # تحويل عمليات البحث إلى كتب
                search_books = []
                for search in recent_searches:
                    if search.get("book_id"):
                        book = Book.query.get(search["book_id"])
                        if book:
                            book_dict = _book_to_dict(
                                book,
                                source="بحثت عنه",
                                reason=f"🔍 {search['query'][:30]}"
                            )
                            if book_dict:
                                search_books.append(book_dict)
                    else:
                        # البحث عن كتب تطابق الاستعلام
                        matching = Book.query.filter(
                            db.or_(
                                Book.title.ilike(f"%{search['query']}%"),
                                Book.author.ilike(f"%{search['query']}%")
                            )
                        ).limit(2).all()
                        for book in matching:
                            book_dict = _book_to_dict(
                                book,
                                source="من بحثك",
                                reason=f"🔍 {search['query'][:25]}..."
                            )
                            if book_dict:
                                search_books.append(book_dict)
                
                if search_books:
                    sections.insert(1, {
                        "title": "🔍 من آخر بحثك",
                        "subtitle": "كتب بناءً على عمليات البحث الأخيرة",
                        "books": search_books[:12],
                        "style": "info",
                        "icon": "magnifying-glass",
                        "query": "special:recent-searches"
                    })
        except Exception as e:
            print(f"Recent Searches Error: {e}")

        # 🧠 مقترحات لك - بناءً على تحليل سلوكك (مثل YouTube)
        try:
            smart_recs = get_behavior_based_recommendations(user_id, limit=12)
            if smart_recs:
                sections.insert(2, {
                    "title": "🧠 مقترحات لك",
                    "subtitle": "كتب مختارة بناءً على ذوقك وسلوكك",
                    "books": smart_recs,
                    "style": "purple",
                    "icon": "brain",
                    "query": "special:behavior"
                })
        except Exception as e:
            print(f"Behavior Recommendations Error: {e}")

        # 👁️ شاهدت مؤخراً - الكتب الفعلية التي شاهدها
        try:
            viewed_books = get_recently_viewed_books(user_id, limit=12)
            if viewed_books:
                sections.insert(3, {
                    "title": "👁️ شاهدت مؤخراً",
                    "subtitle": "الكتب التي زرت صفحاتها مؤخراً",
                    "books": viewed_books,
                    "style": "teal",
                    "icon": "clock-counter-clockwise",
                    "query": "special:recently-viewed"
                })
        except Exception as e:
            print(f"Recently Viewed Error: {e}")

        # 🌟 بناءً على اهتماماتك
        try:
            interest_books = get_books_by_user_interests(user_id, limit=12)
            if interest_books:
                sections.append({
                    "title": "🌟 بناءً على اهتماماتك",
                    "subtitle": "كتب تناسب المواضيع التي تهتم بها",
                    "books": interest_books,
                    "style": "primary",
                    "icon": "heart",
                    "query": "special:interests"
                })
        except Exception as e:
            print(f"Interests Error: {e}")

        # 👀 بناءً على مشاهداتك (AI Enhanced)
        try:
            # محاولة استخدام AI Embeddings أولاً
            view_books = get_view_based_recommendations(user_id, top_n=12)
            
            # إذا لم توجد نتائج (ربما لا توجد embeddings بعد)، نستخدم الطريقة التقليدية
            if not view_books:
                view_books = get_books_by_user_views(user_id, limit=12)
                
            if view_books:
                sections.append({
                    "title": "👀 بناءً على مشاهداتك (AI)",
                    "subtitle": "تحليل ذكي للكتب التي تثير اهتمامك",
                    "books": view_books,
                    "style": "info",
                    "icon": "eye",
                    "query": "special:views"
                })
        except Exception as e:
            print(f"Views Error: {e}")

        # 💎 جواهر مخفية
        try:
            gems = get_hidden_gems(limit=8)
            if gems:
                sections.append({
                    "title": "💎 جواهر مخفية",
                    "subtitle": "كتب رائعة لم تأخذ حقها من الشهرة",
                    "books": gems,
                    "style": "warning",
                    "icon": "diamond",
                    "query": "special:hidden-gems"
                })
        except Exception as e:
            print(f"HiddenGems Error: {e}")

    resp = make_response(render_template("explore.html", sections=sections, hero=hero))
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp
