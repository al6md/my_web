# routes/main.py
import logging
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user, login_required
import numpy as np
import pandas as pd
import requests
from ..models import BookStatus

logger = logging.getLogger(__name__)



from ..extensions import db, csrf
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
from ..recommender import log_user_view



main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def home():
    return redirect(url_for("explore.index"))


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

    # ============ توصيات الذكاء الاصطناعي ============
    recs = get_cf_recommendations(current_user.id, top_n=8)
    
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
