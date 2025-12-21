# routes/public.py

import json
import os
from flask import Blueprint, render_template, request, abort, session, flash, redirect, url_for, jsonify
from flask_login import current_user, login_required
from ..models import Book, SearchHistory, UserPreference, BookReview
from ..extensions import db, csrf, cache
from datetime import datetime
import requests
import random
import urllib.parse

from ..utils import (
    fetch_google_books, fetch_book_details, 
    fetch_gutenberg_books, fetch_gutenberg_detail,
    fetch_archive_books, fetch_archive_detail,
    fetch_openlib_books, fetch_openlib_detail,
    fetch_itbook_books, fetch_itbook_detail,
    translate_to_english_with_gemini, analyze_search_intent_with_ai,
    generate_quiz_with_ai
)

public_bp = Blueprint("public", __name__, url_prefix="/public")

# قوائم المواضيع العشوائية
RANDOM_TOPICS = [
    "History", "Space", "Future", "Magic", "Mystery", "Ocean", 
    "Psychology", "Philosophy", "Art", "Travel", "Health", 
    "Biology", "Physics", "Economy", "Music", "Cinema", 
    "Adventure", "Romance", "War", "Peace", "Nature", "Animals"
]

CATEGORIES = [
    "Programming", "Artificial Intelligence", "Networking", 
    "Databases", "Security", "Cloud", "Web Development", 
    "Classic Literature", "History", "Science"
]

@public_bp.get("/books", endpoint="list_books")
def list_books():
    q   = (request.args.get("q") or "").strip()
    cat = (request.args.get("cat") or "").strip()
    sort = request.args.get("sort") or "relevance"

    try: per = int(request.args.get("per", 12) or 12)
    except ValueError: per = 12

    try: start = int(request.args.get("start", 0) or 0)
    except ValueError: start = 0

    # ============ 🧮 معادلة مهمة جداً ============
    # نحول الـ start (0, 12, 24) إلى رقم صفحة (1, 2, 3) للمكتبات التي تستخدم نظام الصفحات
    current_page = (start // per) + 1
    # ==========================================

    # 1. حفظ سجل البحث وتحديث التفضيلات (للمستخدمين المسجلين)
    # نتجاهل الاستعلامات الخاصة بالنظام (مثل special:interests)
    if q and not q.startswith("special:") and current_user.is_authenticated:
        # أ) حفظ في الجلسة (للتجربة السريعة)
        recent = session.get("recent_public_queries", [])
        if not isinstance(recent, list): recent = []
        if q not in recent: recent.insert(0, q)
        session["recent_public_queries"] = recent[:5]
        
        # ب) حفظ في قاعدة البيانات (للنظام الذكي)
        try:
            # 1. سجل البحث
            history = SearchHistory(
                user_id=current_user.id,
                query=q,
                created_at=datetime.utcnow()
            )
            db.session.add(history)
            
            # 2. تحديث التفضيلات
            # إذا كان البحث طويلاً، نأخذ أول كلمة ذات معنى
            # أو نحفظ البحث كاملاً إذا كان قصيراً (مثل "python")
            keywords = q.lower().split()
            # نركز على أهم الكلمات (تجاهل الحروف)
            valid_kw = [k for k in keywords if len(k) > 2]
            
            # نعطي وزناً إضافياً للبحث الحالي
            for kw in valid_kw[:3]: # نأخذ أول 3 كلمات
                pref = UserPreference.query.filter_by(
                    user_id=current_user.id,
                    topic=kw
                ).first()
                
                if pref:
                    pref.weight += 10.0  # زيادة كبيرة للوزن
                    pref.updated_at = datetime.utcnow()
                else:
                    pref = UserPreference(
                        user_id=current_user.id,
                        topic=kw,
                        weight=50.0  # وزن ابتدائي ضخم جداً ليظهر فوراً
                    )
                    db.session.add(pref)
            
            db.session.commit()
            
            # إبطال الكاش (لضمان تحديث التوصيات فوراً)
            try:
                # نحتاج للدوال لإبطال الكاش الخاص بها
                from ..recommender import get_homepage_sections, get_topic_based, get_last_search_recommendations
                
                # حذف كل الكاش للدوال (بدون تحديد المعاملات لضمان الحذف الكامل)
                cache.delete_memoized(get_homepage_sections)
                cache.delete_memoized(get_topic_based)
                cache.delete_memoized(get_last_search_recommendations)
                
                print(f"🧹 Cache cleared for all users after search by user {current_user.id}.")
            except Exception as e:
                print(f"⚠️ Error clearing cache: {e}")
            
        except Exception as e:
            db.session.rollback()
            print(f"Error saving search prefs: {e}")

    # 2. تجهيز نص البحث والترجمة
    if q: base_query = q
    elif cat: base_query = f"subject:{cat}"
    else: base_query = random.choice(RANDOM_TOPICS)

    google_query = base_query
    
    # تعريف دالة الترجمة محلياً لضمان عملها بشكل صحيح
    def local_translate_to_english(text):
        try:
            # إذا كان النص بالفعل إنجليزي (حروف لاتينية فقط)
            if all(ord(c) < 128 for c in text.replace(" ", "")):
                return text
                
            import os
            gemini_key = os.environ.get("GEMINI_API_KEY")
            if not gemini_key: return text
            
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}"
            prompt = f"Translate this specific book topic or title to English. Return ONLY the English translation, no other text: '{text}'"
            
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            r = requests.post(url, json=payload, timeout=5)
            if r.ok:
                data = r.json()
                translated = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                return translated.strip()
        except: pass
        return text

    # الترجمة للمكتبات الأجنبية
    english_query = local_translate_to_english(base_query)
    
    # 🛑 لمنع نتائج IT Bookstore العشوائية:
    # نقوم بتعطيل البحث فيها إذا كان الموضوع لا يبدو تقنياً
    # لكن للتبسيط، سنعتمد على أن البحث الدقيق لا يرجع نتائج عشوائية
    if not english_query: english_query = base_query

    # -----------------------------------------------------
    # 🚀 تشغيل جميع APIs بشكل متوازي (أسرع 3-4 مرات!)
    # -----------------------------------------------------
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    clean_items = []
    gut_items = []
    ia_items = []
    ol_items = []
    it_items = []
    raw_total = 0
    
    def fetch_google():
        nonlocal raw_total
        try:
            items, total = fetch_google_books(google_query, per, start, "relevance")
            raw_total = total
            result = []
            for it in items:
                vi = it.get("volumeInfo", {}) or {}
                links = vi.get("imageLinks", {}) or {}
                cover = links.get("thumbnail") or links.get("smallThumbnail")
                if cover and cover.startswith("http://"): cover = "https://" + cover[7:]
                result.append({
                    "id": it.get("id"),
                    "title": vi.get("title"),
                    "author": ", ".join(vi.get("authors", [])) if vi.get("authors") else "",
                    "desc": vi.get("description"),
                    "cover": cover,
                    "source": "google",
                    "rating": vi.get("averageRating"),
                    "ratings_count": vi.get("ratingsCount"),
                })
            return ("google", result)
        except Exception as e:
            print(f"Google Books error: {e}")
            return ("google", [])
    
    def fetch_gut():
        try:
            return ("gutenberg", fetch_gutenberg_books(english_query, page=current_page, limit=per) or [])
        except Exception as e:
            print(f"Gutenberg error: {e}")
            return ("gutenberg", [])
    
    def fetch_ia():
        try:
            return ("archive", fetch_archive_books(english_query, limit=per) or [])
        except Exception as e:
            print(f"Archive error: {e}")
            return ("archive", [])
    
    def fetch_ol():
        try:
            return ("openlib", fetch_openlib_books(english_query, limit=per, offset=start) or [])
        except Exception as e:
            print(f"OpenLib error: {e}")
            return ("openlib", [])
    
    # 🔧 IT Bookstore فقط للمواضيع التقنية
    TECH_KEYWORDS = [
        'programming', 'python', 'java', 'javascript', 'code', 'software', 
        'database', 'web', 'machine learning', 'ai', 'data', 'algorithm',
        'network', 'security', 'cloud', 'devops', 'linux', 'react', 'node',
        'برمجة', 'بايثون', 'جافا', 'قواعد بيانات', 'تطوير', 'ذكاء اصطناعي'
    ]
    is_tech_query = any(kw in base_query.lower() or kw in english_query.lower() for kw in TECH_KEYWORDS)
    print(f"🔧 IT Bookstore Filter: query='{base_query}', is_tech={is_tech_query}")
    
    def fetch_it():
        if not is_tech_query:
            print(f"⛔ Skipping IT Bookstore for non-tech query: '{base_query}'")
            return ("itbook", [])  # لا نبحث في IT Bookstore لمواضيع غير تقنية
        try:
            return ("itbook", fetch_itbook_books(english_query, page=current_page, limit=per) or [])
        except Exception as e:
            print(f"ITBook error: {e}")
            return ("itbook", [])

    # Handling special queries
    if q.startswith("special:") and current_user.is_authenticated:
        recommendations = []
        special_type = q.split(":")[1]
        
        from ..recommender import get_topic_based, get_cf_similar, get_content_similar, get_trending
        
        # متغير لتتبع حالة انتهاء الاهتمامات
        interests_exhausted = False
        
        if special_type == "interests":
            # من اهتماماتك العامة
            result = get_topic_based(current_user.id, limit=per, offset=start)
            # النتيجة الآن dict يحتوي على books و interests_exhausted
            if isinstance(result, dict):
                recommendations = result.get('books', [])
                interests_exhausted = result.get('interests_exhausted', False)
            else:
                recommendations = result  # للتوافقية مع القديم
        elif special_type == "cf":
            # مختارات لك (Collaborative Filtering)
            recommendations = get_cf_similar(current_user.id, top_n=per*2)
        elif special_type == "content":
            # لأنك قرأت (Content-Based)
            recommendations = get_content_similar(current_user.id, top_n=per*2)
        elif special_type == "trending":
            # الرائج الآن
            recommendations = get_trending(limit=per*2)
            
        # Distribute recommendations to source lists
        if recommendations:
            for book in recommendations:
                source = book.get("source", "").lower()
                if "google" in source: clean_items.append(book)
                elif "gutenberg" in source: gut_items.append(book)
                elif "archive" in source: ia_items.append(book)
                elif "openlib" in source: ol_items.append(book)
                elif "it" in source and "store" in source: it_items.append(book)
                else: clean_items.append(book) # Default to main list
            
            # Update raw_total (approximate)
            raw_total = len(recommendations)

    else:
        # متغير لتتبع حالة انتهاء الاهتمامات (للحالات العادية)
        interests_exhausted = False
        
        # تشغيل جميع APIs بشكل متوازي (أسرع 3-4 مرات!)
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(fetch_google),
                executor.submit(fetch_gut),
                executor.submit(fetch_ia),
                executor.submit(fetch_ol),
                executor.submit(fetch_it),
            ]
            
            for future in as_completed(futures, timeout=10):
                try:
                    source, items = future.result(timeout=8)
                    if source == "google":
                        clean_items = items
                    elif source == "gutenberg":
                        gut_items = items
                    elif source == "archive":
                        ia_items = items
                    elif source == "openlib":
                        ol_items = items
                    elif source == "itbook":
                        it_items = items
                except Exception as e:
                    print(f"API timeout/error: {e}")

    # -----------------------------------------------------
    # Return
    # -----------------------------------------------------
    # display_total = max(raw_total, 1000) # Removed artificial floor for better pagination control? 
    # Actually, keep it but ensure 'shown' is accurate.
    display_total = max(raw_total, 100) 
    
    shown = len(clean_items) + len(gut_items) + len(ia_items) + len(ol_items) + len(it_items)

    return render_template(
        "public_books.html",
        items=clean_items,
        gut_items=gut_items,
        ia_items=ia_items,
        ol_items=ol_items,
        it_items=it_items,
        q=q, cat=cat, sort=sort, per=per, start=start,
        total=display_total, shown=shown, categories=CATEGORIES,
        interests_exhausted=interests_exhausted,  # 🆕 إرسال حالة انتهاء الاهتمامات
    )


@public_bp.get("/books/<gid>", endpoint="book_detail")
def book_detail(gid):
    book_data = None

    if gid.startswith("gut_"):
        book_data = fetch_gutenberg_detail(gid)
    elif gid.startswith("arch_"):
        book_data = fetch_archive_detail(gid)
    elif gid.startswith("ol_"):
        book_data = fetch_openlib_detail(gid)
    elif gid.isdigit() and len(gid) == 13:
        book_data = fetch_itbook_detail(gid)
        if book_data is None:
            book_data = {
                "id": gid, "title": f"IT Book {gid}", "author": "",
                "desc": "لم يتم العثور على تفاصيل.", "cover": None,
                "preview": f"https://itbook.store/search/{gid}", "source": "itbook",
            }
    else:
        d = fetch_book_details(gid)
        if d:
            # fetch_book_details returns flat dict with title, author, etc.
            # Not nested volumeInfo like the raw API
            cover = d.get("cover") or ""
            if cover and cover.startswith("http://"):
                cover = "https://" + cover[7:]

            book_data = {
                "id": gid, 
                "title": d.get("title") or "عنوان غير متوفر",
                "author": d.get("author") or "مؤلف غير معروف",
                "desc": d.get("description") or "لا يوجد وصف متاح لهذا الكتاب.", 
                "cover": cover,
                "preview": d.get("preview"),
                "source": d.get("source", "google"),
                "publishedDate": d.get("publishedDate"),
                "pageCount": d.get("pageCount"),
                "categories": d.get("categories") or [],
                "rating": d.get("rating"),
            }

    if not book_data: abort(404)
    book_data.setdefault("google_id", gid)

    # -------------------------------------------------
    #   توليد وصف AI تلقائي إذا لم يتوفر وصف
    # -------------------------------------------------
    if not book_data.get("desc") or book_data.get("desc") == "لا يوجد وصف متاح لهذا الكتاب.":
        try:
            from ..utils import generate_ai_description
            ai_desc = generate_ai_description(book_data.get("title", ""), book_data.get("author", ""))
            if ai_desc:
                book_data["desc"] = ai_desc
                book_data["ai_generated_desc"] = True
        except Exception as e:
            print(f"[AI Desc] Error generating description: {e}")

    # -------------------------------------------------
    #   اقتراحات متشابهة (محسّن للسرعة)
    # -------------------------------------------------
    similar = []
    seen_ids = {book_data["id"]}
    title = (book_data.get("title") or "").strip()
    categories = book_data.get("categories", [])
    
    # استخدام العنوان مباشرة بدون ترجمة AI (أسرع!)
    search_query = title[:50]  # أول 50 حرف فقط
    
    # جلب من مصادر متعددة بشكل متوازي
    if search_query:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        def fetch_google():
            try:
                # Increased limit to 40
                g_items, _ = fetch_google_books(search_query, max_results=40)
                results = []
                for it in g_items:
                    sid = it.get("id")
                    if not sid: continue
                    vi = it.get("volumeInfo", {}) or {}
                    imgs = vi.get("imageLinks", {}) or {}
                    cover = imgs.get("thumbnail") or ""
                    if cover.startswith("http://"): cover = "https://" + cover[7:]
                    
                    # Ensure rating is extracted
                    rating = vi.get("averageRating")
                    
                    results.append({
                        "id": sid, 
                        "title": vi.get("title"), 
                        "author": ", ".join(vi.get("authors", [])), 
                        "cover": cover, 
                        "source": "google",
                        "rating": rating,
                        "ratings_count": vi.get("ratingsCount")
                    })
                return results
            except: return []
        
        def fetch_ol():
            try: return fetch_openlib_books(search_query, limit=10) # Slight increase
            except: return []
        
        # تشغيل متوازي مع timeout قصير
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {
                executor.submit(fetch_google): "google",
                executor.submit(fetch_ol): "openlibrary",
            }
            
            try:
                for future in as_completed(futures, timeout=6): # Increased timeout slightly
                    try:
                        results = future.result(timeout=5)
                        for it in results:
                            sid = it.get("id")
                            if not sid or sid in seen_ids: continue
                            seen_ids.add(sid)
                            similar.append(it)
                    except Exception as e:
                        pass  # تجاهل الأخطاء للسرعة
            except:
                pass  # استمر بما لدينا

    # خلط النتائج وتحديد العدد
    import random
    random.shuffle(similar)
    similar = similar[:45] # Increased limit

    # -------------------------------------------------
    #   التحقق من حالة الكتاب في مكتبة المستخدم
    # -------------------------------------------------
    personal_recs = []
    current_status = None
    if current_user.is_authenticated:
        # البحث عن الكتاب محلياً باستخدام Google ID
        local_book = Book.query.filter_by(owner_id=current_user.id, google_id=gid).first()
        if local_book:
            # إذا وجد الكتاب، نبحث عن حالته
            from ..models import BookStatus
            status_entry = BookStatus.query.filter_by(user_id=current_user.id, book_id=local_book.id).first()
            if status_entry:
                current_status = status_entry.status

    return render_template(
        "public_book_detail.html",
        book=book_data,
        similar=similar,
        personal_recs=personal_recs,
        current_status=current_status, # تمرير الحالة للقالب
    )

@public_bp.route("/books/<gid>/add-to-shelf/<status>", methods=["POST"])
@login_required
@csrf.exempt
def add_to_shelf(gid, status):
    """إضافة كتاب إلى رف معين (قراءة لاحقاً، مفضلة، تم)"""
    if status not in ['later', 'favorite', 'finished']:
        return jsonify({"success": False, "error": "Invalid status"}), 400

    from ..models import BookStatus
    
    try:
        # 1. التحقق هل الكتاب موجود في مكتبة المستخدم
        local_book = Book.query.filter_by(owner_id=current_user.id, google_id=gid).first()
        
        # 2. إذا لم يكن موجوداً، نقوم باستيراده
        if not local_book:
            # جلب البيانات
            data = None
            if gid.startswith("gut_"): data = fetch_gutenberg_detail(gid)
            elif gid.startswith("arch_"): data = fetch_archive_detail(gid)
            elif gid.startswith("ol_"): data = fetch_openlib_detail(gid)
            elif gid.isdigit() and len(gid) == 13: data = fetch_itbook_detail(gid)
            else: data = fetch_book_details(gid)

            if not data:
                return jsonify({"success": False, "error": "Book not found"}), 404

            # استخراج البيانات
            title = data.get("title")
            author = data.get("author")
            desc = data.get("desc") or data.get("description")
            cover = data.get("cover")
            
            if "volumeInfo" in data:
                vi = data["volumeInfo"]
                title = vi.get("title")
                author = ", ".join(vi.get("authors", [])) if vi.get("authors") else "Unknown"
                desc = vi.get("description")
                imgs = vi.get("imageLinks", {})
                cover = imgs.get("thumbnail") or imgs.get("smallThumbnail")

            if cover and cover.startswith("http://"):
                cover = cover.replace("http://", "https://")

            local_book = Book(
                title=title or "Untitled",
                author=author or "Unknown",
                description=desc,
                cover_url=cover,
                owner_id=current_user.id,
                google_id=gid
            )
            db.session.add(local_book)
            db.session.commit()
            
            # محاولة إنشاء Embedding
            try:
                from ..utils import generate_book_embedding_if_missing
                generate_book_embedding_if_missing(local_book)
            except: pass

        # 3. تحديث الحالة
        status_entry = BookStatus.query.filter_by(user_id=current_user.id, book_id=local_book.id).first()
        
        if status_entry:
            if status_entry.status == status:
                # إذا ضغط نفس الزر، نحذف الحالة (Toggle Off)
                db.session.delete(status_entry)
                msg = "تم إزالة الكتاب من القائمة"
                new_status = None
            else:
                # تغيير الحالة
                status_entry.status = status
                msg = f"تم نقل الكتاب إلى {status}"
                new_status = status
        else:
            # حالة جديدة
            status_entry = BookStatus(user_id=current_user.id, book_id=local_book.id, status=status)
            db.session.add(status_entry)
            msg = f"تم إضافة الكتاب إلى {status}"
            new_status = status
            
        db.session.commit()
        
        # إبطال الكاشات المهمة
        try:
            from ..recommender import get_homepage_sections
            cache.delete_memoized(get_homepage_sections)
        except: pass

        return jsonify({"success": True, "message": msg, "status": new_status})

    except Exception as e:
        db.session.rollback()
        print(f"Error adding to shelf: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@public_bp.get("/reader/<gid>", endpoint="reader")
def reader(gid):
    # ... (الكود كما هو) ...
    target_link = ""
    title = ""
    if gid.startswith("ia_"):
        clean_id = gid.replace("ia_", "")
        target_link = f"https://archive.org/embed/{clean_id}"
        title = "Archive Reader"
    elif gid.startswith("gut_"):
        d = fetch_gutenberg_detail(gid)
        if d: target_link, title = d["preview"], d["title"]
    elif gid.startswith("ol_"):
        d = fetch_openlib_detail(gid)
        if d: target_link, title = d["preview"], d["title"]
    elif gid.isdigit() and len(gid) == 13:
        try:
            r = requests.get(f"https://api.itbook.store/1.0/books/{gid}", timeout=5)
            if r.ok:
                data = r.json()
                target_link = data.get("url")
                title = data.get("title")
        except: pass
    else:
        d = fetch_book_details(gid)
        if d:
            vi = d.get("volumeInfo", {})
            target_link = vi.get("previewLink") or vi.get("infoLink")
            title = vi.get("title")
    return render_template("reader_frame.html", book_title=title, book_id=gid, external_link=target_link)


# ===========================================================================
#                          نظام التقييم والمراجعات
# ===========================================================================

@public_bp.post("/books/<gid>/review")
@login_required
@csrf.exempt
def submit_review(gid):
    """إرسال مراجعة جديدة أو تحديث مراجعة موجودة"""
    try:
        rating = int(request.form.get("rating", 0))
        review_text = request.form.get("review_text", "").strip()
        
        # التحقق من صحة التقييم
        if not 1 <= rating <= 5:
            flash("يجب أن يكون التقييم بين 1 و 5 نجوم", "warning")
            return redirect(url_for("public.book_detail", gid=gid))
        
        # البحث عن مراجعة موجودة
        existing_review = BookReview.query.filter_by(
            user_id=current_user.id,
            google_id=gid
        ).first()
        
        if existing_review:
            # تحديث المراجعة الموجودة
            existing_review.rating = rating
            existing_review.review_text = review_text
            flash("تم تحديث مراجعتك بنجاح! ✨", "success")
        else:
            # إنشاء مراجعة جديدة
            new_review = BookReview(
                user_id=current_user.id,
                google_id=gid,
                rating=rating,
                review_text=review_text
            )
            db.session.add(new_review)
            flash("شكراً لمراجعتك! 🌟", "success")
        
        # ---------------------------------------------------------
        # 🧠 نظام الاهتمامات الذكي: تحديث التفضيلات بناءً على التقييم
        # ---------------------------------------------------------
        if rating >= 4:
            try:
                # نحتاج لعنوان الكتاب والمؤلف للتحليل
                # (يمكننا جلبه من قاعدة البيانات أو APs)
                book_title = "Unknown"
                book_author = "Unknown"
                
                # نحاول جلبه من DB أولاً (لأنه أسرع)
                local_book = Book.query.filter_by(google_id=gid).first()
                if local_book:
                    book_title = local_book.title
                    book_author = local_book.author
                else:
                    # إذا لم يكن محلياً، نحاول تخمينه أو تركه للـ AI
                    # (هنا سنعتمد على أن دالة التحليل ستتعامل مع النقص أو يمكننا جلبه)
                    # للسرعة، سنمرر "Book ID {gid}" إذا لم نجد الاسم، والـ AI قد يفهم لو كان معروفاً
                    pass 

                # استدعاء دالة التحليل (يفضل أن تكون async في الإنتاج)
                from ..utils import extract_interests_from_text_ai
                
                # استخدام Thread لعدم تعطيل السيرفر
                from threading import Thread
                
                def background_interest_update(app, uid, b_title, b_author, r_text):
                    with app.app_context():
                        topics = extract_interests_from_text_ai(b_title, b_author, r_text)
                        print(f"🎯 [Interest System] Extracted topics for {b_title}: {topics}")
                        
                        for topic in topics:
                            pref = UserPreference.query.filter_by(user_id=uid, topic=topic).first()
                            if pref:
                                pref.weight += 5.0 # زيادة الوزن
                                pref.updated_at = datetime.utcnow()
                            else:
                                new_pref = UserPreference(user_id=uid, topic=topic, weight=10.0)
                                db.session.add(new_pref)
                        
                        db.session.commit()

                # تشغيل في الخلفية
                from flask import current_app
                # ملاحظة: current_app is a proxy, need real app object for thread
                real_app = current_app._get_current_object()
                Thread(target=background_interest_update, args=(real_app, current_user.id, book_title, book_author, review_text)).start()
                
            except Exception as e:
                print(f"[Interest System] Error: {e}")

        db.session.commit()
        
        # إبطال كاش أعلى التقييمات لتظهر التحديثات فوراً
        try:
            from ..recommender import get_top_rated
            cache.delete_memoized(get_top_rated)
            print(f"🧹 Top Rated cache cleared after review submission.")
        except Exception as e:
            print(f"⚠️ Error clearing top rated cache: {e}")
        
    except Exception as e:
        db.session.rollback()
        print(f"[Review] Error: {e}")
        flash("حدث خطأ أثناء حفظ المراجعة", "danger")
    
    return redirect(url_for("public.book_detail", gid=gid))


@public_bp.get("/books/<gid>/reviews")
def get_reviews(gid):
    """جلب جميع مراجعات كتاب معين (JSON API)"""
    reviews = BookReview.query.filter_by(google_id=gid).order_by(
        BookReview.created_at.desc()
    ).limit(50).all()
    
    # حساب متوسط التقييم
    avg_rating = 0
    total_count = len(reviews)
    
    # حساب توزيع التقييمات (عدد كل نجمة)
    rating_counts = {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}
    
    if reviews:
        for r in reviews:
            if 1 <= r.rating <= 5:
                rating_counts[r.rating] += 1
        avg_rating = sum(r.rating for r in reviews) / total_count
    
    # حساب النسب المئوية لكل تقييم
    rating_distribution = {}
    for stars in range(5, 0, -1):
        count = rating_counts[stars]
        percentage = round((count / total_count * 100), 1) if total_count > 0 else 0
        rating_distribution[str(stars)] = {
            "count": count,
            "percentage": percentage
        }
    
    return {
        "count": total_count,
        "average_rating": round(avg_rating, 1),
        "rating_distribution": rating_distribution,
        "reviews": [
            {
                "id": r.id,
                "user_name": r.user.name if r.user else "مستخدم",
                "rating": r.rating,
                "review_text": r.review_text,
                "created_at": r.created_at.strftime("%Y-%m-%d") if r.created_at else None
            }
            for r in reviews
        ]
    }


# ===========================================================================
#                          📝 ملخص AI للكتب
# ===========================================================================

@public_bp.post("/books/<gid>/ai-summary")
@csrf.exempt
def generate_ai_summary(gid):
    """توليد ملخص ذكي للكتاب باستخدام AI"""
    from ..utils import generate_book_summary
    from flask import jsonify
    
    try:
        # جلب معلومات الكتاب
        book_data = None
        
        if gid.startswith("gut_"):
            book_data = fetch_gutenberg_detail(gid)
        elif gid.startswith("arch_"):
            book_data = fetch_archive_detail(gid)
        elif gid.startswith("ol_"):
            book_data = fetch_openlib_detail(gid)
        elif gid.isdigit() and len(gid) == 13:
            book_data = fetch_itbook_detail(gid)
        else:
            d = fetch_book_details(gid)
            if d:
                vi = d.get("volumeInfo", {}) or {}
                book_data = {
                    "title": vi.get("title", ""),
                    "author": ", ".join(vi.get("authors", [])) if vi.get("authors") else "",
                    "description": vi.get("description", ""),
                    "categories": ", ".join(vi.get("categories", [])) if vi.get("categories") else ""
                }
        
        if not book_data:
            return jsonify({"success": False, "error": "لم يتم العثور على الكتاب"}), 404
        
        # توليد الملخص
        result = generate_book_summary({
            "title": book_data.get("title", ""),
            "author": book_data.get("author", ""),
            "description": book_data.get("desc") or book_data.get("description", ""),
            "categories": book_data.get("categories", "")
        })
        
        return jsonify(result)
        
    except Exception as e:
        print(f"[AI Summary] Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ===========================================================================
#                     🎯 لماذا قد يعجبك هذا الكتاب
# ===========================================================================

@public_bp.post("/books/<gid>/why-like")
@login_required
@csrf.exempt
def generate_why_like(gid):
    """تحليل لماذا قد يعجب الكتاب المستخدم"""
    from ..utils import generate_why_you_like
    from flask import jsonify
    
    try:
        # جلب معلومات الكتاب
        book_data = None
        
        if gid.startswith("gut_"):
            book_data = fetch_gutenberg_detail(gid)
        elif gid.startswith("arch_"):
            book_data = fetch_archive_detail(gid)
        elif gid.startswith("ol_"):
            book_data = fetch_openlib_detail(gid)
        elif gid.isdigit() and len(gid) == 13:
            book_data = fetch_itbook_detail(gid)
        else:
            d = fetch_book_details(gid)
            if d:
                vi = d.get("volumeInfo", {}) or {}
                book_data = {
                    "title": vi.get("title", ""),
                    "author": ", ".join(vi.get("authors", [])) if vi.get("authors") else "",
                    "description": vi.get("description", ""),
                    "categories": ", ".join(vi.get("categories", [])) if vi.get("categories") else ""
                }
        
        if not book_data:
            return jsonify({"success": False, "error": "لم يتم العثور على الكتاب"}), 404
        
        # جمع سياق المستخدم
        user_context = {
            "interests": [],
            "recent_books": [],
            "favorite_genres": []
        }
        
        # جلب اهتمامات المستخدم من التفضيلات
        prefs = UserPreference.query.filter_by(user_id=current_user.id).order_by(
            UserPreference.weight.desc()
        ).limit(10).all()
        user_context["interests"] = [p.topic for p in prefs]
        
        # جلب الكتب الأخيرة من المكتبة
        recent_books = Book.query.filter_by(owner_id=current_user.id).order_by(
            Book.created_at.desc()
        ).limit(10).all()
        user_context["recent_books"] = [b.title for b in recent_books if b.title]
        
        # توليد التحليل
        result = generate_why_you_like(
            {
                "title": book_data.get("title", ""),
                "author": book_data.get("author", ""),
                "description": book_data.get("desc") or book_data.get("description", ""),
                "categories": book_data.get("categories", "")
            },
            user_context
        )
        
        return jsonify(result)
        
    except Exception as e:
        print(f"[AI WhyLike] Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ===========================================================================
#                     📅 خطة القراءة الذكية
# ===========================================================================

@public_bp.post("/books/<gid>/plan")
@csrf.exempt
def generate_plan_route(gid):
    """توليد خطة قراءة للكتاب"""
    from ..utils import generate_reading_plan
    from flask import jsonify
    
    try:
        # جلب معلومات الكتاب (نفس المنطق المكرر لجلب البيانات - يمكن تحسينه لاحقاً)
        book_data = None
        if gid.startswith("gut_"): book_data = fetch_gutenberg_detail(gid)
        elif gid.startswith("arch_"): book_data = fetch_archive_detail(gid)
        elif gid.startswith("ol_"): book_data = fetch_openlib_detail(gid)
        elif gid.isdigit() and len(gid) == 13: book_data = fetch_itbook_detail(gid)
        else:
            d = fetch_book_details(gid)
            if d:
                vi = d.get("volumeInfo", {}) or {}
                book_data = {
                    "title": vi.get("title", ""),
                    "pageCount": vi.get("pageCount", 0)
                }
        
        if not book_data:
            return jsonify({"success": False, "error": "Book not found"}), 404
            
        days = int(request.json.get("days", 7))
        result = generate_reading_plan(book_data, days=days)
        return jsonify(result)
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ===========================================================================
#                     🗣️ التحدث مع الكتاب
# ===========================================================================

@public_bp.post("/books/<gid>/chat")
@csrf.exempt
def chat_with_book_route(gid):
    """الدردشة مع سياق الكتاب"""
    from ..utils import chat_with_book_context
    from flask import jsonify
    
    try:
        message = request.json.get("message", "")
        history = request.json.get("history", [])
        
        # جلب معلومات الكتاب
        book_data = None
        if gid.startswith("gut_"): book_data = fetch_gutenberg_detail(gid)
        elif gid.startswith("arch_"): book_data = fetch_archive_detail(gid)
        elif gid.startswith("ol_"): book_data = fetch_openlib_detail(gid)
        elif gid.isdigit() and len(gid) == 13: book_data = fetch_itbook_detail(gid)
        else:
            d = fetch_book_details(gid)
            if d:
                vi = d.get("volumeInfo", {}) or {}
                book_data = {
                    "title": vi.get("title", ""),
                    "author": ", ".join(vi.get("authors", [])) if vi.get("authors") else "",
                    "description": vi.get("description", ""),
                }
        
        if not book_data:
            return jsonify({"success": False, "reply": "عذراً، لم أجد الكتاب.", "error": "Not found"}), 404
            
        result = chat_with_book_context(book_data, message, history)
        return jsonify(result)
        
    except Exception as e:
        print(f"[Book Chat] Error: {e}")
        return jsonify({"success": False, "reply": "حدث خطأ غير متوقع.", "error": str(e)}), 500


# ===========================================================================
#                     🧠 مسابقة الكتاب
# ===========================================================================

@public_bp.post("/books/<gid>/quiz")
@csrf.exempt
def book_quiz_route(gid):
    """توليد مسابقة للكتاب"""
    from ..utils import generate_book_quiz
    from flask import jsonify
    
    try:
        # جلب معلومات الكتاب
        book_data = None
        if gid.startswith("gut_"): book_data = fetch_gutenberg_detail(gid)
        elif gid.startswith("arch_"): book_data = fetch_archive_detail(gid)
        elif gid.startswith("ol_"): book_data = fetch_openlib_detail(gid)
        elif gid.isdigit() and len(gid) == 13: book_data = fetch_itbook_detail(gid)
        else:
            d = fetch_book_details(gid)
            if d:
                vi = d.get("volumeInfo", {}) or {}
                book_data = {
                    "title": vi.get("title", ""),
                    "description": vi.get("description", ""),
                }
        
        if not book_data:
            return jsonify({"success": False, "error": "Book not found"}), 404
            
        result = generate_book_quiz(book_data)
        return jsonify(result)
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500




# ===========================================================================
#                     📊 تحليل عادات القراءة
# ===========================================================================

@public_bp.get("/user/reading-analytics")
@login_required
def reading_analytics_page():
    """صفحة تحليل عادات القراءة"""
    return render_template("reading_analytics.html")


@public_bp.get("/api/reading-analytics")
@login_required
def reading_analytics_api():
    """API لجلب إحصائيات القراءة"""
    from ..utils import analyze_reading_habits
    from flask import jsonify
    
    result = analyze_reading_habits(current_user.id)
    return jsonify(result)


# ===========================================================================
#                     🎨 توليد غلاف AI
# ===========================================================================

@public_bp.post("/books/<gid>/generate-cover")
@csrf.exempt
def generate_cover_route(gid):
    """توليد غلاف AI للكتاب"""
    from ..utils import generate_ai_cover
    from flask import jsonify
    
    try:
        # جلب معلومات الكتاب
        book_data = None
        if gid.startswith("gut_"): book_data = fetch_gutenberg_detail(gid)
        elif gid.startswith("arch_"): book_data = fetch_archive_detail(gid)
        elif gid.startswith("ol_"): book_data = fetch_openlib_detail(gid)
        elif gid.isdigit() and len(gid) == 13: book_data = fetch_itbook_detail(gid)
        else:
            d = fetch_book_details(gid)
            if d:
                vi = d.get("volumeInfo", {}) or {}
                book_data = {
                    "title": vi.get("title", ""),
                    "author": ", ".join(vi.get("authors", [])) if vi.get("authors") else "",
                    "description": vi.get("description", ""),
                }
        
        if not book_data:
            return jsonify({"success": False, "error": "Book not found"}), 404
            
        result = generate_ai_cover(book_data)
        return jsonify(result)
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ===========================================================================
#                     🤖 دردشة AI عامة
# ===========================================================================

@public_bp.post("/api/ai-chat")
@csrf.exempt
def general_ai_chat():
    """دردشة عامة مع مساعد AI للموقع"""
    from flask import jsonify
    import os
    
    try:
        message = request.json.get("message", "")
        history = request.json.get("history", [])
        
        if not message:
            return jsonify({"success": False, "reply": "الرجاء كتابة رسالة"}), 400
        
        # استدعاء دالة الذكاء الاصطناعي الموحدة (التي تجلب الكتب أيضاً)
        from ..utils import chat_with_ai
        
        # تحويل التاريخ إلى سياق بسيط إذا لزم الأمر، أو الاعتماد على الرسالة الحالية
        # حالياً chat_with_ai تدعم رسالة واحدة + سياق مستخدم (غير متوفر للمجهول)
        result = chat_with_ai(message)
        
        return jsonify({
            "success": True, 
            "reply": result.get("reply", ""),
            "books": result.get("books", [])
        })

    except Exception as e:
        print(f"[AI Chat] Error: {e}")
        return jsonify({"success": False, "reply": "عذراً، حدث خطأ غير متوقع."}), 500


# ═══════════════════════════════════════════════════════════════════════════
#  🎨 توليد أغلفة الكتب بالذكاء الاصطناعي
# ═══════════════════════════════════════════════════════════════════════════

@public_bp.get("/api/smart-cover")
@csrf.exempt
def get_smart_cover():
    """
    🔥 جلب غلاف كتاب من مصادر متعددة (Open Library + Google Books + AI)
    
    هذا الـ endpoint يبحث عن أفضل غلاف متاح من:
    1. Open Library Covers API (مجاني وعالي الجودة)
    2. Google Books API
    3. توليد AI كـ fallback
    
    Parameters:
        title: عنوان الكتاب (مطلوب)
        author: اسم المؤلف (اختياري)
        isbn: رقم ISBN (اختياري - يحسن النتائج كثيراً)
    
    Returns:
        JSON: {"success": bool, "cover_url": str, "source": str}
    """
    from flask import jsonify
    from ..utils import get_book_cover_smart
    
    title = request.args.get("title", "").strip()
    author = request.args.get("author", "").strip()
    isbn = request.args.get("isbn", "").strip()
    
    if not title:
        return jsonify({"success": False, "error": "عنوان الكتاب مطلوب"}), 400
    
    try:
        result = get_book_cover_smart(title=title, author=author, isbn=isbn)
        return jsonify({
            "success": True,
            "cover_url": result["cover_url"],
            "source": result["source"]
        })
    except Exception as e:
        print(f"[Smart Cover API] Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@public_bp.get("/api/openlibrary-cover")
@csrf.exempt
def get_openlibrary_cover():
    """
    جلب غلاف مباشرة من Open Library Covers API فقط
    
    Parameters:
        isbn: رقم ISBN (الأفضل)
        title: عنوان الكتاب
        author: اسم المؤلف
        size: حجم الصورة (S, M, L) - الافتراضي L
    
    Returns:
        Redirect إلى صورة الغلاف أو صورة افتراضية
    """
    from flask import redirect
    from ..utils import fetch_cover_from_openlibrary
    
    isbn = request.args.get("isbn", "").strip()
    title = request.args.get("title", "").strip()
    author = request.args.get("author", "").strip()
    size = request.args.get("size", "L").strip().upper()
    
    if size not in ["S", "M", "L"]:
        size = "L"
    
    cover_url = fetch_cover_from_openlibrary(isbn=isbn, title=title, author=author, size=size)
    
    if cover_url:
        return redirect(cover_url)
    
    # Fallback إلى placeholder
    return redirect("/static/images/placeholders/openlibrary.png")


@public_bp.get("/api/generate-cover")
@csrf.exempt
def generate_book_cover():
    """
    توليد غلاف كتاب بالذكاء الاصطناعي مع دعم خاص للغة العربية
    """
    import urllib.parse
    import re
    from flask import redirect

    title = request.args.get("title", "Book").strip()
    author = request.args.get("author", "").strip()
    
    # 1. التحقق من اللغة العربية
    def is_arabic(text):
        return bool(re.search(r'[\u0600-\u06FF]', text))

    is_arabic_book = is_arabic(title) or is_arabic(author)
    
    # 2. بناء Prompt ذكي
    if is_arabic_book:
        # Prompt مخصص للكتب العربية
        prompt = f"Book cover for '{title}'"
        if author:
            prompt += f" by {author}"
        
        # كلمات مفتاحية للتصميم العربي/الإسلامي
        keywords = [
            "Arabic calligraphy style",
            "Islamic geometric patterns",
            "elegant oriental design",
            "minimalist sophisticated",
            "high quality book cover",
            "cultural artistic representation"
        ]
        prompt += ", " + ", ".join(keywords)
        
    else:
        # Prompt للكتب الإنجليزية/العالمية
        prompt = f"Professional book cover for '{title}'"
        if author:
            prompt += f" by {author}"
            
        keywords = [
            "award winning design",
            "modern minimalist",
            "cinematic lighting",
            "high resolution 4k",
            "elegant typography"
        ]
        prompt += ", " + ", ".join(keywords)

    # 3. توجيه الطلب إلى Pollinations.ai
    encoded_prompt = urllib.parse.quote(prompt)
    
    # نستخدم seed عشوائي ثابت بناءً على العنوان لضمان نفس الصورة لنفس الكتاب
    seed = sum(ord(c) for c in title) % 1000
    
    pollinations_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=400&height=600&nologo=true&seed={seed}&model=flux"
    
    return redirect(pollinations_url)


@public_bp.get("/api/generate-cover-gemini")
@csrf.exempt  
def generate_book_cover_gemini():
    """
    توليد غلاف كتاب باستخدام Gemini Imagen API (جودة أعلى)
    
    ملاحظة: يحتاج GEMINI_API_KEY مع صلاحيات Imagen
    """
    import os
    import hashlib
    from flask import jsonify
    
    title = request.args.get("title", "Book").strip()
    author = request.args.get("author", "").strip()
    category = request.args.get("category", "").strip()
    
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_key:
        return jsonify({"success": False, "error": "GEMINI_API_KEY not configured"}), 500
    
    # إنشاء hash للـ caching
    cache_key = hashlib.md5(f"gemini_{title}_{author}_{category}".encode()).hexdigest()[:16]
    cache_dir = os.path.join(os.path.dirname(__file__), "..", "static", "images", "generated")
    cache_path = os.path.join(cache_dir, f"{cache_key}_gemini.jpg")
    
    # التحقق من الـ cache
    if os.path.exists(cache_path):
        return jsonify({
            "success": True, 
            "url": f"/static/images/generated/{cache_key}_gemini.jpg"
        })
    
    # بناء prompt
    prompt = f"Create a beautiful book cover for '{title}'"
    if author:
        prompt += f" by {author}"
    if category:
        prompt += f", {category} genre"
    prompt += ". Modern, elegant design with dark theme."
    
    try:
        # استخدام Gemini Imagen API
        response = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/imagen-3.0-generate-001:predict?key={gemini_key}",
            json={
                "instances": [{"prompt": prompt}],
                "parameters": {
                    "sampleCount": 1,
                    "aspectRatio": "2:3"
                }
            },
            timeout=60
        )
        
        if response.ok:
            data = response.json()
            # استخراج الصورة من الاستجابة
            predictions = data.get("predictions", [])
            if predictions:
                import base64
                image_data = predictions[0].get("bytesBase64Encoded", "")
                if image_data:
                    os.makedirs(cache_dir, exist_ok=True)
                    with open(cache_path, 'wb') as f:
                        f.write(base64.b64decode(image_data))
                    return jsonify({
                        "success": True,
                        "url": f"/static/images/generated/{cache_key}_gemini.jpg"
                    })
        
        # Fallback إلى Pollinations
        return redirect(url_for('public.generate_book_cover', title=title, author=author, category=category))
        
    except Exception as e:
        print(f"[Gemini Cover] Error: {e}")
        # Fallback إلى Pollinations
        return redirect(url_for('public.generate_book_cover', title=title, author=author, category=category))

@public_bp.route("/api/coach/plan", methods=["POST"])
@csrf.exempt
def get_reading_plan():
    """
    API Returns personalized reading plan
    """
    data = request.json
    title = data.get('title')
    pages = data.get('pages', 200) # Default 200 if unknown
    days = data.get('days', 7)
    
    if not title:
        return jsonify({"error": "Missing title"}), 400
        
    # Import here to avoid circular dependencies if any
    from ..utils import generate_reading_plan_with_ai
    
    plan = generate_reading_plan_with_ai(title, pages, days)
    return jsonify(plan)

@public_bp.route("/api/quote/generate", methods=["POST"])
def generate_quote_options():
    """
    API Returns quotes for Insta-Quote
    """
    data = request.json
    title = data.get('title')
    author = data.get('author')
    
    if not title:
        return jsonify({"error": "Missing info"}), 400
        
    from ..utils import extract_quotes_with_ai
    
    result = extract_quotes_with_ai(title, author)
    return jsonify(result)

@public_bp.route("/api/quiz/generate", methods=["POST"])
@csrf.exempt
def generate_quiz():
    """
    API Returns AI Quiz questions
    """
    data = request.json
    title = data.get('title')
    author = data.get('author')
    
    if not title:
        return jsonify({"error": "Missing info"}), 400
        
    from ..utils import generate_quiz_with_ai
    
    result = generate_quiz_with_ai(title, author)
    return jsonify(result)
