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
from ..models import Book, UserRatingCF, BookEmbedding, UserPreference, SearchHistory # <--- أضفنا آخر اثنين
# استيراد الدوال الموحدة
from ..utils import (
    fetch_openlib_detail, fetch_gutenberg_detail, fetch_archive_detail, fetch_itbook_detail, fetch_book_details,
    get_text_embedding, generate_book_embedding_if_missing,
    fetch_google_books, fetch_gutenberg_books, fetch_openlib_books, fetch_archive_books,
    fetch_itbook_books,
    translate_to_english_with_gemini,
    chat_with_ai  # مساعد AI للكتب
)



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

    favorites_ids = [s.book_id for s in statuses if s.status == "favorite"]
    later_ids     = [s.book_id for s in statuses if s.status == "later"]
    finished_ids  = [s.book_id for s in statuses if s.status == "finished"]

    # هنا أيضاً يجب التأكد أننا نعرض الكتب حتى لو بحثنا
    # لكن عادة القوائم الجانبية (المفضلة..) لا تتأثر ببحث الجدول الرئيسي
    favorites = Book.query.filter(Book.id.in_(favorites_ids)).all() if favorites_ids else []
    later     = Book.query.filter(Book.id.in_(later_ids)).all()     if later_ids else []
    finished  = Book.query.filter(Book.id.in_(finished_ids)).all()  if finished_ids else []

    # ============ توصيات الذكاء الاصطناعي ============
    recs = get_cf_recommendations(current_user.id, top_n=8)
    
    # ============ المكتبات الخمس ============
    from ..recommender import get_all_libraries_showcase
    library_sections = get_all_libraries_showcase(query="programming books", limit_per_source=8)

    return render_template(
        "books.html",
        books=my_books,
        favorites=favorites,
        later=later,
        finished=finished,
        cf_recs=recs,
        library_sections=library_sections
    )


@main_bp.route("/books/<int:book_id>")
@login_required
def book_detail(book_id):
    book = Book.query.get_or_404(book_id)
    
    # التحقق من الملكية (اختياري - حسب منطق التطبيق)
    # هنا نسمح برؤية أي كتاب، لكن التعديل مقيد
    
    # جلب تقييم المستخدم
    user_rating = UserRatingCF.query.filter_by(user_id=current_user.id, google_id=book.google_id).first()
    
    # جلب حالة الكتاب
    book_status_obj = BookStatus.query.filter_by(user_id=current_user.id, book_id=book.id).first()
    book_status = book_status_obj.status if book_status_obj else None
    
    # جلب كتب مشابهة إذا كان كتاب Google
    similar = []
    if book.google_id:
        try:
            # استيراد هنا لتجنب Circular Import إذا كان موجوداً
            from ..utils import fetch_google_books
            # نبحث عن كتب مشابهة بالعنوان
            similar_items, _ = fetch_google_books(book.title, max_results=5)
            # تنظيف البيانات
            for item in similar_items:
                if item['id'] == book.google_id: continue
                vi = item.get('volumeInfo', {})
                imgs = vi.get('imageLinks', {})
                cov = imgs.get('thumbnail') or imgs.get('smallThumbnail')
                if cov and cov.startswith('http://'): cov = cov.replace('http://', 'https://')
                
                similar.append({
                    'id': item['id'],
                    'title': vi.get('title'),
                    'author': ", ".join(vi.get('authors', [])),
                    'cover': cov,
                    'source': 'google'  # للدلالة على أنه من جوجل
                })
        except Exception as e:
            logger.error(f"Error fetching similar books: {e}")

    return render_template(
        "book_detail.html",
        book=book,
        user_rating=user_rating,
        book_status=book_status,
        similar=similar
    )


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
    if status not in ['favorite', 'later', 'finished']:
        flash("حالة غير معروفة", "danger")
        return redirect(url_for("main.book_detail", book_id=book_id))
        
    book = Book.query.get_or_404(book_id)
    
    # التحقق هل الحالة موجودة مسبقاً
    s = BookStatus.query.filter_by(user_id=current_user.id, book_id=book.id).first()
    
    if s:
        # إذا ضغط نفس الحالة -> حذف (Toggle)
        if s.status == status:
            db.session.delete(s)
            flash(f"تمت إزالة الكتاب من قائمة {status}", "info")
        else:
            # تغيير الحالة
            s.status = status
            flash(f"تم تغيير الحالة إلى {status}", "success")
    else:
        # إنشاء حالة جديدة
        s = BookStatus(user_id=current_user.id, book_id=book.id, status=status)
        db.session.add(s)
        flash(f"تمت الإضافة إلى قائمة {status}", "success")
        
    db.session.commit()
    return redirect(url_for("main.books"))


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


@main_bp.post("/books/<int:book_id>/delete")
@login_required
def delete_book(book_id: int):
    b = Book.query.get_or_404(book_id)
    if b.owner_id != current_user.id:
        flash("ليس لديك صلاحية", "danger"); return redirect(url_for("main.books"))
    db.session.delete(b); db.session.commit(); flash("تم الحذف", "info")
    return redirect(url_for("main.books"))


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
