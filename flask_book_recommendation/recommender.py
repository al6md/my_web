# -*- coding: utf-8 -*-
import logging
import random
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy import func
from flask import current_app
from flask_login import current_user

from .models import (
    Book, UserRatingCF, SearchHistory,
    UserPreference, BookEmbedding, BookReview, UserBookView,
    BookStatus, UserGenre, Genre, PublicRating
)
from .utils import (
    fetch_google_books, fetch_gutenberg_books,
    fetch_openlib_books, fetch_archive_books,
    fetch_itbook_books,
    translate_to_english_with_gemini,
    get_text_embedding,
    fetch_openlib_rating,
    analyze_search_intent_with_ai  # Need this or similar for AI analysis
)
from .extensions import db, cache
from .advanced_recommender import DLInferenceEngine

# Initialize DL Engine
# We initialize it lazily or here if it doesn't block startup too much.
# Since it loads a model file, let's keep it at module level but handle errors inside the class.
dl_engine = DLInferenceEngine()


logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _book_to_dict(book, source="Local", reason=None):
    """
    يحوّل كائن Book من الـ ORM إلى قاموس جاهز للتمبليت.
    
    Args:
        book: كائن Book من SQLAlchemy
        source: مصدر الكتاب (Local, CF, Content, Google Books, etc.)
        reason: سبب التوصية (نص توضيحي)
        
    Returns:
        قاموس يحتوي على معلومات الكتاب أو None إذا كان book=None
    """
    if book is None:
        return None

    cover_url = getattr(book, "cover_url", None)
    # تنظيف روابط Google Books - إزالة edge=curl لتحسين الأداء
    if cover_url and 'books.google.com' in cover_url and '&edge=curl' in cover_url:
        cover_url = cover_url.replace('&edge=curl', '').replace('&edge=curl&', '&')

    return {
        # نستخدم google_id لو موجود, وإلا نستخدم id محلي
        "id": getattr(book, "google_id", None) or f"local_{book.id}",
        "title": getattr(book, "title", None),
        "author": getattr(book, "author", None),
        "cover": cover_url,
        "source": source,
        "reason": reason,
        "rating": getattr(book, "average_rating", None) or getattr(book, "rating", None),
    }


def _extract_rating_with_fallback(vi):
    """
    استخراج التقييم من بيانات Google Books مع محاولة Fallback إلى OpenLibrary.
    """
    rating = vi.get("averageRating")
    if rating:
        return rating
    
    # محاولة الحصول على ISBN للبحث في OpenLibrary
    isbns = vi.get("industryIdentifiers") or []
    isbn_13 = next((i["identifier"] for i in isbns if i["type"] == "ISBN_13"), None)
    isbn_10 = next((i["identifier"] for i in isbns if i["type"] == "ISBN_10"), None)
    isbn = isbn_13 or isbn_10
    
    if isbn:
        try:
            return fetch_openlib_rating(isbn=isbn)
        except:
            pass
            
    return None


def _deduplicate_dicts(items, key="id"):
    """
    يزيل التكرارات من قائمة القواميس بناءً على مفتاح محدد.
    
    Args:
        items: قائمة من القواميس
        key: المفتاح المستخدم للتحقق من التكرار (افتراضي: "id")
        
    Returns:
        قائمة من القواميس بدون تكرارات
    """
    seen = set()
    out = []
    for it in items:
        k = it.get(key)
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(it)
    return out


# ------------------------------------------------------------------
# 1) Trending – الرائج الآن
# ------------------------------------------------------------------


@cache.memoize(timeout=60)  # Cache لمدة دقيقة واحدة فقط لتحديث أسرع
def get_trending(limit=12):
    """
    يحصل على الكتب الرائجة من مكتبات المستخدمين فقط.
    يعرض فقط الكتب التي أضافها المستخدمون (100%).
    
    Args:
        limit: عدد الكتب المطلوبة
        
    Returns:
        قائمة من القواميس تمثل الكتب الرائجة
    """
    books_dicts = []
    seen_ids = set()

    # كتب من مكتبات المستخدمين فقط (100%)
    try:
        # نحصل على الكتب التي أضافها المستخدمون (owner_id موجود)
        user_books = (
            Book.query
            .filter(Book.owner_id.isnot(None))
            .order_by(Book.created_at.desc())
            .limit(limit * 3)
            .all()
        )
        
        # نخلط القائمة لتنوع أفضل
        random.shuffle(user_books)
        
        for b in user_books:
            book_id = f"local_{b.id}" if not b.google_id else b.google_id
            if book_id in seen_ids:
                continue
            seen_ids.add(book_id)
            
            # فلترة الكتب السيئة
            if not b.title or b.title in ['Untitled', 'Unknown']:
                continue

            # معلومات المالك
            owner_name = "مستخدم"
            owner_id = None
            if b.owner:
                owner_id = b.owner.id
                if b.owner.name:
                    owner_name = b.owner.name
            
            # بناء القاموس مع إضافة معلومات المالك
            book_dict = _book_to_dict(
                b,
                source="مكتبة المستخدمين",
                reason=f"👤 أضافه: {owner_name}",
            )
            
            # إضافة معلومات المالك للقاموس
            if book_dict:
                book_dict['owner_name'] = owner_name
                book_dict['owner_id'] = owner_id
                books_dicts.append(book_dict)
            
            if len(books_dicts) >= limit:
                break
    except Exception as e:
        logger.error(f"[Trending] User books error: {e}", exc_info=True)

    # خلط النتائج النهائية لضمان التنوع
    random.shuffle(books_dicts)
    books_dicts = _deduplicate_dicts(books_dicts)
    result = books_dicts[:limit]
    logger.info(f"[Trending] Returning {len(result)} trending books from user libraries")
    return result





@cache.memoize(timeout=600)
def get_cf_similar(user_id, top_n=30, min_users=2, offset=0):
    """
    Get recommendations based on similar users (User-User Collaborative Filtering)
    :param user_id: ID of the user
    :param top_n: Number of recommendations to return
    :param min_users: Minimum number of similar users required to make a recommendation
    :param offset: Pagination offset

        
    Returns:
        قائمة من القواميس (كتب مقترحة) للمستخدم المحدد
    """
    try:
        # كل التقييمات
        ratings = UserRatingCF.query.all()
        if not ratings:
            logger.debug(f"[CF] No ratings found for user {user_id}")
            return []

        # تأكد أن هذا المستخدم له تقييمات
        user_ratings = [r for r in ratings if r.user_id == user_id]
        if len(user_ratings) == 0:
            logger.debug(f"[CF] User {user_id} has no ratings")
            return []

        # بناء mapping
        user_ids = sorted({r.user_id for r in ratings})
        item_gids = sorted({r.google_id for r in ratings if r.google_id})

        if len(user_ids) < min_users or len(item_gids) == 0:
            logger.debug(f"[CF] Not enough users ({len(user_ids)}) or items ({len(item_gids)})")
            return []

        user_index = {u_id: idx for idx, u_id in enumerate(user_ids)}
        item_index = {gid: idx for idx, gid in enumerate(item_gids)}

        # مصفوفة التقييمات
        mat = np.zeros((len(user_ids), len(item_gids)), dtype=np.float32)
        for r in ratings:
            if not r.google_id:
                continue
            ui = user_index[r.user_id]
            ii = item_index[r.google_id]
            mat[ui, ii] = float(r.rating or 0.0)

        # لو المستخدم غير موجود بالمصفوفة
        if user_id not in user_index:
            logger.warning(f"[CF] User {user_id} not found in user_index")
            return []

        u_idx = user_index[user_id]
        user_vec = mat[u_idx].reshape(1, -1)

        # لو ماكو أي تقييم فعلياً (كلها صفر)
        if np.count_nonzero(user_vec) == 0:
            logger.debug(f"[CF] User {user_id} has all zero ratings")
            return []

        # تشابه كوني مع بقية المستخدمين
        sims = cosine_similarity(user_vec, mat)[0]

        # نتجاهل تشابه المستخدم مع نفسه
        sims[u_idx] = 0.0

        # نحسب درجة لكل كتاب بناءً على weighted rating
        sim_matrix = sims.reshape(-1, 1)
        weighted_sum = (sim_matrix * mat).sum(axis=0)
        sim_sum = (sim_matrix * (mat > 0)).sum(axis=0) + 1e-8
        scores = weighted_sum / sim_sum

        # ما نرشّح الكتب اللي المستخدم قيّمها مسبقاً
        user_rated_mask = mat[u_idx] > 0
        scores[user_rated_mask] = -1.0

        # أعلى الكتب حسب السكور
        top_indices = np.argsort(scores)[::-1]
        
        # Apply pagination (offset + limit)
        start_idx = offset
        if start_idx >= len(top_indices):
            return []
            
        top_indices = top_indices[start_idx:]
        
        recs = []
        for idx in top_indices:
            if scores[idx] <= 0:
                continue
            gid = item_gids[idx]
            book = Book.query.filter_by(google_id=gid).first()
            if not book:
                continue
            recs.append(
                _book_to_dict(
                    book,
                    source="CF",
                    reason="✨ مختارات بناءً على تقييـماتك وتقييمات مستخدمين مشابهين لك",
                )
            )
            if len(recs) >= top_n:
                break

        logger.info(f"[CF] Generated {len(recs)} recommendations for user {user_id}")
        return recs
        
    except Exception as e:
        logger.error(f"[CF] Error in get_cf_similar for user {user_id}: {e}", exc_info=True)
        return []


# ------------------------------------------------------------------
# 3) Content-Based – لأنك قرأت...
# ------------------------------------------------------------------


@cache.memoize(timeout=600)  # Cache لمدة 10 دقائق
def get_content_similar(user_id, top_n=30, history_limit=20):
    """
    توصيات محتوى Content-Based باستخدام جدول BookEmbedding.
    
    نبني "بروفايل" للمستخدم من آخر الكتب التي قرأها أو قيمها
    ثم نستخدم البروفايل لمقارنة باقي الكتب باستخدام Cosine Similarity.
    
    Args:
        user_id: معرف المستخدم
        top_n: عدد التوصيات المطلوبة
        history_limit: عدد آخر الكتب المستخدمة لبناء البروفايل
        
    Returns:
        قائمة من القواميس تمثل الكتب المقترحة
    """
    # 1) آخر الكتب التي قيّمها المستخدم
    user_ratings = (
        UserRatingCF.query
        .filter_by(user_id=user_id)
        .order_by(UserRatingCF.created_at.desc())
        .limit(history_limit)
        .all()
    )
    rated_gids = [r.google_id for r in user_ratings if r.google_id]

    # 2) نحاول أيضاً استخدام SearchHistory إن كان مرتبطاً بكتب معينة
    history_books_ids = []
    try:
        history_rows = (
            db.session.query(SearchHistory)
            .filter_by(user_id=user_id)
            .order_by(SearchHistory.created_at.desc())
            .limit(history_limit)
            .all()
        )
        for h in history_rows:
            if getattr(h, "book_id", None):
                history_books_ids.append(h.book_id)
    except Exception as e:
        logger.error(f"[Content] SearchHistory error: {e}", exc_info=True)

    # نحول google_id إلى book_id
    rated_books = []
    if rated_gids:
        rated_books = (
            Book.query.filter(Book.google_id.in_(rated_gids)).all()
        )
    rated_book_ids = [b.id for b in rated_books]

    seed_book_ids = list({*rated_book_ids, *history_books_ids})
    if not seed_book_ids:
        return []

    # 3) نجيب embeddings الخاصة بالكتب المصدرية
    seed_embeds = (
        BookEmbedding.query.filter(BookEmbedding.book_id.in_(seed_book_ids)).all()
    )
    if not seed_embeds:
        return []

    seed_vectors = []
    for row in seed_embeds:
        vec = row.vector
        if vec is None:
            continue
        v = np.array(vec, dtype=np.float32)
        if v.ndim == 1:
            seed_vectors.append(v)
    if not seed_vectors:
        return []

    # بروفايل المستخدم = متوسط متجهات الكتب اللي قرأها / بحث عنها
    user_profile = np.mean(np.vstack(seed_vectors), axis=0).reshape(1, -1)

    # 4) نحسب تشابه البروفايل مع جميع الكتب اللي لها Embedding
    all_embeds = BookEmbedding.query.all()
    book_ids = []
    vectors = []
    for row in all_embeds:
        vec = row.vector
        if vec is None:
            continue
        v = np.array(vec, dtype=np.float32)
        if v.ndim == 1:
            book_ids.append(row.book_id)
            vectors.append(v)

    if not vectors:
        return []

    mat = np.vstack(vectors)
    try:
        sims = cosine_similarity(user_profile, mat)[0]
    except Exception as e:
        logger.error(f"[Content] cosine_similarity error: {e}", exc_info=True)
        return []

    # نتجاهل الكتب اللي سبق للمستخدم قراءتها / بحثها
    exclude_ids = set(seed_book_ids)
    ranked_indices = np.argsort(sims)[::-1]

    recs = []
    for idx in ranked_indices:
        score = sims[idx]
        if score <= 0:
            continue
        b_id = book_ids[idx]
        if b_id in exclude_ids:
            continue

        book = Book.query.get(b_id)
        if not book:
            continue

        recs.append(
            _book_to_dict(
                book,
                source="Content",
                reason="📖 لأنك قرأت كتباً مشابهة",
            )
        )
        if len(recs) >= top_n:
            break

    return recs


@cache.memoize(timeout=600)  # Cache لمدة 10 دقائق
def get_view_based_recommendations(user_id, top_n=12, history_limit=10):
    """
    توصيات ذكية بناءً على سجل المشاهدات (UserBookView) باستخدام AI Embeddings.
    
    الخوارزمية:
    1. جلب آخر الكتب التي شاهدها المستخدم
    2. استخراج المتجهات (Embeddings) لهذه الكتب
    3. حساب "متجه الاهتمام الحالي" (متوسط المتجهات)
    4. البحث عن أقرب الكتب لهذا المتجه باستخدام Cosine Similarity
    """
    try:
        # 1. جلب آخر الكتب المشاهدة
        recent_views = (
            UserBookView.query
            .filter_by(user_id=user_id)
            .order_by(UserBookView.last_viewed_at.desc())
            .limit(history_limit)
            .all()
        )
        
        if not recent_views:
            return []

        # استخراج IDs
        viewed_book_ids = []
        viewed_google_ids = []
        for v in recent_views:
            if v.book_id: viewed_book_ids.append(v.book_id)
            if v.google_id: viewed_google_ids.append(v.google_id)
            
        # تحويل google_id إلى book_id محلي إذا وجد
        if viewed_google_ids:
            g_books = Book.query.filter(Book.google_id.in_(viewed_google_ids)).all()
            for b in g_books:
                viewed_book_ids.append(b.id)
                
        viewed_book_ids = list(set(viewed_book_ids))
        if not viewed_book_ids:
            return []

        # 2. جلب Embeddings للكتب المشاهدة
        seed_embeds = (
            BookEmbedding.query.filter(BookEmbedding.book_id.in_(viewed_book_ids)).all()
        )
        
        seed_vectors = []
        for row in seed_embeds:
            if row.vector is not None:
                v = np.array(row.vector, dtype=np.float32)
                if v.ndim == 1:
                    seed_vectors.append(v)
                    
        if not seed_vectors:
            return []

        # 3. حساب بروفايل الاهتمام (Centroid)
        interest_profile = np.mean(np.vstack(seed_vectors), axis=0).reshape(1, -1)

        # 4. مقارنة مع باقي الكتب
        all_embeds = BookEmbedding.query.all()
        candidate_ids = []
        candidate_vectors = []
        
        for row in all_embeds:
            # استثناء الكتب التي شاهدها بالفعل
            if row.book_id in viewed_book_ids:
                continue
                
            if row.vector is not None:
                v = np.array(row.vector, dtype=np.float32)
                if v.ndim == 1:
                    candidate_ids.append(row.book_id)
                    candidate_vectors.append(v)
                    
        if not candidate_vectors:
            return []
            
        mat = np.vstack(candidate_vectors)
        sims = cosine_similarity(interest_profile, mat)[0]
        
        # ترتيب النتائج
        ranked_indices = np.argsort(sims)[::-1]
        
        recs = []
        for idx in ranked_indices:
            score = sims[idx]
            if score < 0.4:  # عتبة تشابه
                continue
                
            b_id = candidate_ids[idx]
            book = Book.query.get(b_id)
            if not book:
                continue
                
            recs.append(
                _book_to_dict(
                    book,
                    source="AI Views",
                    reason=f"👀 🤖 ماتش ذكي: {int(score*100)}%",
                )
            )
            
            if len(recs) >= top_n:
                break
                
        logger.info(f"[ViewAI] Generated {len(recs)} recommendations based on {len(viewed_book_ids)} viewed books")
        return recs
        
    except Exception as e:
        logger.error(f"[ViewAI] Error: {e}", exc_info=True)
        return []


# ------------------------------------------------------------------
# 🧠 Behavior-Based Recommendations V2 – محسّن بـ AI + CF + Diversity
# ------------------------------------------------------------------


def _apply_mmr_diversity(books, lambda_param=0.5, max_per_category=2):
    """
    تطبيق خوارزمية MMR (Maximal Marginal Relevance) لضمان التنوع.
    
    Args:
        books: قائمة الكتب
        lambda_param: معامل التوازن بين الصلة والتنوع (0.5 = توازن)
        max_per_category: الحد الأقصى لكل تصنيف/مؤلف
        
    Returns:
        قائمة كتب متنوعة
    """
    if not books or len(books) <= 3:
        return books
    
    selected = []
    remaining = books.copy()
    category_counts = {}
    author_counts = {}
    
    while remaining and len(selected) < len(books):
        best_score = -1
        best_idx = 0
        
        for idx, book in enumerate(remaining):
            # حساب عقوبة التكرار
            category = book.get("category", "unknown")
            author = book.get("author", "unknown")
            
            cat_count = category_counts.get(category, 0)
            auth_count = author_counts.get(author, 0)
            
            # عقوبة التكرار
            diversity_penalty = 0
            if cat_count >= max_per_category:
                diversity_penalty += 0.5
            if auth_count >= max_per_category:
                diversity_penalty += 0.3
            
            # الدرجة = الصلة الأصلية - عقوبة التكرار
            original_score = book.get("score", 1.0)
            final_score = original_score * (1 - lambda_param * diversity_penalty)
            
            if final_score > best_score:
                best_score = final_score
                best_idx = idx
        
        # إضافة الكتاب المختار
        chosen = remaining.pop(best_idx)
        selected.append(chosen)
        
        # تحديث العدادات
        category = chosen.get("category", "unknown")
        author = chosen.get("author", "unknown")
        category_counts[category] = category_counts.get(category, 0) + 1
        author_counts[author] = author_counts.get(author, 0) + 1
    
    return selected

def run_in_context(app, func, *args, **kwargs):
    """Helper to run function within app context"""
    with app.app_context():
        return func(*args, **kwargs)

def _get_ai_embedding_recommendations(user_id, viewed_book_ids, search_queries=None, favorite_book_ids=None, high_rated_book_ids=None, explicit_genres=None, limit=10, offset=0):
    """
    توصيات بناءً على AI Embeddings - تشابه دلالي شامل.
    يدمج (المشاهدات + البحث + المفضلة + التقييمات العالية) لبناء بروفايل دقيق.
    
    Args:
        user_id: معرف المستخدم
        viewed_book_ids: قائمة IDs الكتب المشاهدة
        search_queries: قائمة عبارات البحث الأخيرة
        favorite_book_ids: قائمة IDs الكتب المفضلة (Likes)
        high_rated_book_ids: قاموس أو قائمة بـ IDs الكتب ذات التقييم العالي (مع الدرجة)
        limit: عدد التوصيات
        offset: بداية النتائج (للتصفح)
        
    Returns:
        قائمة كتب مقترحة بناءً على التشابه الدلالي
    """
    try:
        search_queries = search_queries or []
        favorite_book_ids = favorite_book_ids or []
        high_rated_book_ids = high_rated_book_ids or []
        
        all_vectors = []
        
        # 1. متجهات الكتب المشاهدة (وزن 1x)
        if viewed_book_ids:
            view_embeds = BookEmbedding.query.filter(BookEmbedding.book_id.in_(viewed_book_ids)).all()
            for row in view_embeds:
                if row.vector is not None:
                    v = np.array(row.vector, dtype=np.float32)
                    if v.ndim == 1:
                        all_vectors.append(v)

        # 2. متجهات الكتب المفضلة (Likes/Favorites) (وزن 3x - قوي جداً)
        if favorite_book_ids:
            fav_embeds = BookEmbedding.query.filter(BookEmbedding.book_id.in_(favorite_book_ids)).all()
            for row in fav_embeds:
                if row.vector is not None:
                    v = np.array(row.vector, dtype=np.float32)
                    if v.ndim == 1:
                        # نضيف المتجه 3 مرات لزيادة وزنه
                        all_vectors.append(v)
                        all_vectors.append(v)
                        all_vectors.append(v)

        # 3. متجهات الكتب ذات التقييم العالي (Ratings)
        # إذا كانت dict: {id: stars}, إذا كانت list: نفترض 4 نجوم
        if high_rated_book_ids:
            # استخراج الـ IDs فقط للاستعلام
            ids_only = list(high_rated_book_ids.keys()) if isinstance(high_rated_book_ids, dict) else high_rated_book_ids
            
            rated_embeds = BookEmbedding.query.filter(BookEmbedding.book_id.in_(ids_only)).all()
            for row in rated_embeds:
                if row.vector is not None:
                    v = np.array(row.vector, dtype=np.float32)
                    if v.ndim == 1:
                        weight = 2 # افتراضي (4 نجوم)
                        if isinstance(high_rated_book_ids, dict):
                            stars = high_rated_book_ids.get(row.book_id, 4)
                            if stars >= 5: weight = 4 # 5 نجوم وزنها 4x
                            elif stars >= 4: weight = 2 # 4 نجوم وزنها 2x
                        
                        # تكرار المتجه حسب الوزن
                        for _ in range(weight):
                            all_vectors.append(v)

        # 4. متجهات البحث (وزن مضاعف جداً لأحدث بحث)
        processed_queries = 0
        for i, query in enumerate(search_queries):
             if not query: continue
             if processed_queries >= 5: break # Max 5 queries to save API time
             
             try:
                 q_vec = get_text_embedding(query)
                 if q_vec:
                     v = np.array(q_vec, dtype=np.float32)
                     
                     if i == 0: 
                         # البحث الأحدث: وزن 5x (للتأثير الفوري)
                         for _ in range(5): all_vectors.append(v)
                     elif i == 1:
                         # البحث الثاني: وزن 3x
                         for _ in range(3): all_vectors.append(v)
                     else:
                         # الباقي: وزن 1x
                         all_vectors.append(v)
                         
                     processed_queries += 1
             except Exception as e:
                 logger.error(f"[AI-Embed] Search embed error: {e}")

        # 5. التصنيفات المختارة (Explicit Genres) - مهمة جداً للـ Cold Start
        if explicit_genres:
            for genre in explicit_genres:
                try:
                    # نعزز النص بكلمة "Genre"
                    g_vec = get_text_embedding(f"Genre: {genre}")
                    if g_vec:
                        v = np.array(g_vec, dtype=np.float32)
                        
                        # وزن عالي (4x) لأن المستخدم اختارها بنفسه
                        for _ in range(4): all_vectors.append(v)
                except Exception as e:
                    logger.error(f"[AI-Embed] Genre embed error: {e}")

        if not all_vectors:
            logger.debug(f"[AI-Embed] No vectors found for user profile")
            return []
        
        # بناء بروفايل المستخدم (Centroid)
        user_profile = np.mean(np.vstack(all_vectors), axis=0).reshape(1, -1)
        
        # مقارنة مع جميع الكتب
        all_embeds = BookEmbedding.query.all()
        candidate_ids = []
        candidate_vectors = []
        
        # استثناء الكتب التي تفاعل معها المستخدم بالفعل (إلا إذا أردنا إعادة اقتراحها؟ عادة لا)
        exclude_ids = set(viewed_book_ids) | set(favorite_book_ids) 
        if isinstance(high_rated_book_ids, dict):
            exclude_ids |= set(high_rated_book_ids.keys())
        elif isinstance(high_rated_book_ids, list):
            exclude_ids |= set(high_rated_book_ids)
        
        for row in all_embeds:
            if row.book_id in exclude_ids:
                continue
            if row.vector is not None:
                v = np.array(row.vector, dtype=np.float32)
                if v.ndim == 1:
                    candidate_ids.append(row.book_id)
                    candidate_vectors.append(v)
        
        if not candidate_vectors:
            return []
        
        mat = np.vstack(candidate_vectors)
        sims = cosine_similarity(user_profile, mat)[0]
        
        # ترتيب حسب التشابه
        ranked_indices = np.argsort(sims)[::-1]
        
        recs = []
        # نأخذ شريحة أكبر قليلاً للتصفية, ثم نقص حسب الـ offset
        # offset هنا يعني "كم نتيجة نتخطى من الأفضل"
        start_idx = offset
        # إذا كنا نتخطى أكثر من عدد النتائج, نرجع فارغ
        if start_idx >= len(ranked_indices):
             return []
             
        for idx in ranked_indices[start_idx:]:
            score = sims[idx]
            if score < 0.35:  # عتبة التشابه
                continue
            
            book = Book.query.get(candidate_ids[idx])
            if not book:
                continue
            
            book_dict = _book_to_dict(
                book,
                source="AI Smart Match",
                reason=f"🧠 تطابق ذكي: {int(score*100)}%"
            )
            if book_dict:
                book_dict["score"] = float(score)
                book_dict["category"] = book.categories.split(",")[0].strip() if book.categories else "unknown"
                book_dict["rec_type"] = "ai_embedding"
                recs.append(book_dict)
            
            if len(recs) >= limit:
                break
        
        logger.info(f"[AI-Embed] Found {len(recs)} semantic recommendations from mixed signals")
        return recs
        
    except Exception as e:
        logger.error(f"[AI-Embed] Error: {e}", exc_info=True)
        return []


def _get_cf_recommendations(user_id, limit=6, offset=0):
    # ... existing code ...
    pass 

# ------------------------------------------------------------------
# 4) Deep Learning - Two-Tower Model (Added Step)
# ------------------------------------------------------------------

def get_deep_learning_recommendations(user_id, limit=10):
    """
    Get recommendations using the Two-Tower Deep Learning model.
    Includes Hybrid Ranking logic.
    """
    try:
        # 1. Fetch User Data
        recent_views = []
        if user_id:
            recent_views = (
                UserBookView.query
                .filter_by(user_id=user_id)
                .order_by(UserBookView.last_viewed_at.desc())
                .limit(10)
                .all()
            )
        
        print(f"DEBUG: [DL] user_id={user_id}, recent_views={len(recent_views)}")
        
        history_vectors = [] # Should be (10, 768)
        viewed_ids = []
        for v in recent_views:
            # Resolve book
            book_id = v.book_id
            if not book_id and v.google_id:
                 b = Book.query.filter_by(google_id=v.google_id).first()
                 if b: book_id = b.id
            
            if book_id:
                viewed_ids.append(book_id)
                emb = BookEmbedding.query.filter_by(book_id=book_id).first()
                if emb and emb.vector is not None:
                    history_vectors.append(np.array(emb.vector, dtype=np.float32))
        
        # Pad history to 10
        if len(history_vectors) < 10:
            pad_len = 10 - len(history_vectors)
            # Pad with zeros
            for _ in range(pad_len):
                history_vectors.append(np.zeros(768, dtype=np.float32))
        else:
            history_vectors = history_vectors[:10]
            
        history_arr = np.array(history_vectors) # (10, 768)
        
        # Interest Vector (Average of liked books or explicit interests)
        # For simplicity, using mean of history as interest
        interest_vec = np.mean(history_arr, axis=0)

        # 2. Prepare Candidates
        # We need a set of candidate books to score.
        # In production, we'd use Annoy/Faiss index.
        # Here, we score ALL books (OK for small DB of ~500 books).
        all_books = Book.query.all()
        candidate_features = {}
        book_metadata = {}
        
        for b in all_books:
            if b.id in viewed_ids: continue # Skip viewed
            
            emb = BookEmbedding.query.filter_by(book_id=b.id).first()
            if emb and emb.vector is not None:
                 candidate_features[b.id] = np.array(emb.vector, dtype=np.float32)
                 book_metadata[b.id] = {

                     'id': b.id,
                     'vector': candidate_features[b.id],
                     'popularity': 0.5, # Placeholder
                     'semantic_score': 0.0 # Placeholder
                 }
        
        if not candidate_features:
            return []

        # 3. Predict & Rank
        user_data = {'history': history_arr, 'interests': interest_vec}
        candidates_list = list(book_metadata.values())
        
        ranked_results = dl_engine.generate_recommendations(
            user_id, 
            user_data, 
            candidates_list, 
            top_k=limit
        )
        
        # 4. Convert to Dicts
        recs = []
        for res in ranked_results:
            b_id = res['id']
            book = Book.query.get(b_id)
            if book:
                d = _book_to_dict(
                    book,
                    source="Deep Learning",
                    reason=f"🧠 AI Score: {res['final_score']:.2f}"
                )
                recs.append(d)
                
        return recs

    except Exception as e:
        logger.error(f"[DL-Rec] Error: {e}", exc_info=True)
        return []

    """
    توصيات Collaborative Filtering - مستخدمون مشابهون.
    
    Args:
        user_id: معرف المستخدم
        limit: عدد التوصيات
        offset: إزاحة التصفح
        
    Returns:
        قائمة كتب أعجبت مستخدمين مشابهين
    """
    try:
        # استخدام الدالة الموجودة مع تمرير الـ offset
        cf_books = get_cf_similar(user_id, top_n=limit, offset=offset)
        
        # تحويل إلى صيغة موحدة
        for book in cf_books:
            book["score"] = 0.8  # درجة ثابتة للـ CF
            book["rec_type"] = "collaborative"
            if "reason" not in book or not book["reason"]:
                book["reason"] = "👥 أعجب مستخدمين بذوق مشابه"
        
        logger.info(f"[CF] Found {len(cf_books)} CF recommendations for user {user_id}")
        return cf_books
        
    except Exception as e:
        logger.error(f"[CF-V2] Error: {e}", exc_info=True)
        return []


# @cache.memoize(timeout=300)  # Cache disabled for debugging
def get_behavior_based_recommendations(user_id, limit=12, offset=0):
    print(f"DEBUG: get_behavior_based_recommendations called for user {user_id} with limit {limit}, offset {offset}")
    """
    توصيات ذكية شاملة (YouTube-Style)
    
    تدمج بين:
    1. سجل البحث (Search History) - لمعرفة ما تبحث عنه الآن.
    2. المفضلة (Favorites) - لمعرفة ذوقك الدقيق.
    3. المشاهدات (Views) - لمعرفة اهتمامك الضمني.
    4. التصنيفات المختارة (Explicit Genres) - اهتماماتك العامة.
    5. التشابه مع مستخدمين آخرين (Collaborative Filtering).
    
    Args:
        user_id: معرف المستخدم
        limit: عدد التوصيات المطلوبة per source type roughly
        
    Returns:
        قائمة كتب متنوعة وشخصية جداً
    """
    from datetime import datetime, timedelta
    from collections import defaultdict
    from concurrent.futures import ThreadPoolExecutor
    
    try:
        logger.info(f"[Behavior-Hybrid] Starting comprehensive recommendations for user {user_id}")
        
        # ---------------------------------------------------------
        # 1. جمع البيانات (Data Gathering)
        # ---------------------------------------------------------
        
        # أ) الكتب المشاهدة حديثاً
        recent_views = (
            UserBookView.query
            .filter_by(user_id=user_id)
            .order_by(UserBookView.last_viewed_at.desc())
            .limit(40)
            .all()
        )
        viewed_book_ids = set()
        viewed_google_ids = set()
        
        category_weights = defaultdict(float)
        author_weights = defaultdict(float)
        
        for view in recent_views:
            if view.book_id: viewed_book_ids.add(view.book_id)
            if view.google_id: viewed_google_ids.add(view.google_id)
            
            # تحليل مبسط للأوزان من المشاهدات
            book = None
            if view.book_id: book = Book.query.get(view.book_id)
            elif view.google_id: book = Book.query.filter_by(google_id=view.google_id).first()
            
            if book:
                w = view.view_count or 1
                if book.categories:
                    for cat in book.categories.split(','):
                        if len(cat) > 2: category_weights[cat.strip()] += w
                if book.author:
                    author_weights[book.author.split(',')[0].strip()] += w

        # ب) سجل البحث (آخر 10 عمليات بحث)
        recent_searches = (
            db.session.query(SearchHistory)
            .filter_by(user_id=user_id)
            .order_by(SearchHistory.created_at.desc())
            .limit(10)
            .all()
        )
        search_queries = [s.query for s in recent_searches if s.query]
        
            # ج) الكتب المفضلة (Status = favorite)
        favorites = (
            BookStatus.query
            .filter_by(user_id=user_id, status='favorite')
            .order_by(BookStatus.created_at.desc())
            .all()
        )
        favorite_book_ids = [f.book_id for f in favorites if f.book_id]

        # د) الكتب الأعلى تقييماً (4 نجوم فأكثر)
        high_rated_books = {}  # {book_id: stars}
        
        # 1. تقييمات محلية (UserRatingCF)
        user_ratings = UserRatingCF.query.filter(UserRatingCF.user_id==user_id, UserRatingCF.rating >= 4).all()
        for r in user_ratings:
             if r.google_id:
                 # محاولة العثور على book_id محلي
                 b = Book.query.filter_by(google_id=r.google_id).first()
                 if b: high_rated_books[b.id] = r.rating

        # 2. تقييمات عامة (PublicRating) - إذا كنا نربط المستخدمين بها بطريقة ما (حالياً PublicRating بـ u_id)
        public_ratings = PublicRating.query.filter(PublicRating.user_id==user_id, PublicRating.stars >= 4).all()
        for r in public_ratings:
             if r.google_id:
                 b = Book.query.filter_by(google_id=r.google_id).first()
                 if b: 
                     # نأخذ التقييم الأعلى إذا تكرر
                     old = high_rated_books.get(b.id, 0)
                     high_rated_books[b.id] = max(old, r.stars)

        # هـ) التصنيفات المختارة صراحةً
        user_genres = (
            db.session.query(Genre.name)
            .join(UserGenre)
            .filter(UserGenre.user_id == user_id)
            .all()
        )
        explicit_genres = [g[0] for g in user_genres]
        
        # 🆕 أضفنا تفضيلات المستخدم المخصصة (Topics)
        user_prefs = UserPreference.query.filter_by(user_id=user_id).all()
        for p in user_prefs:
            explicit_genres.append(p.topic)
        
        # إذا لم يكن هناك أي داتا, نرجع للرائج
        if not (viewed_book_ids or search_queries or favorite_book_ids or explicit_genres or high_rated_books):
             logger.info("[Behavior-Hybrid] No user history, falling back to Trending")
             return get_trending(limit=limit)

        # ---------------------------------------------------------
        # 2. تشغيل محركات التوصية بالتوازي
        # ---------------------------------------------------------
        
        all_recs = []
        
        # Capture real app object to pass to threads
        app = current_app._get_current_object()
        
        # حساب الحصص التقريبية
        # نعطي مساحة أكبر للـ AI لأنه الأذكى الآن
        ai_limit = int(limit * 0.6) + 4 
        cf_limit = int(limit * 0.2) + 2
        explore_limit = int(limit * 0.2) + 2
        
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {}
            
            # حساب offset مخصص للـ AI
            # الـ AI يأخذ تقريباً 50-60% من الصفحة
            # إذا الصفحة 0 (offset 0) -> ai_offset = 0
            # إذا الصفحة 12 (offset 12) -> ai_offset = ~6 (نصف الـ offset)
            # ولكن, هنا المنطق دقيق:
            # نحن نطلب ai_limit لكل صفحة.
            # لاستمرار النتائج بشكل صحيح, يجب أن نتخطى ما عرضناه سابقاً.
            # إذا كنا نعرض في كل صفحة (ai_limit) من نتائج الـ AI, فالـ offset يجب أن يكون (page_num * ai_limit)
            
            # حساب رقم الصفحة التقريبي
            page_num = offset // limit if limit > 0 else 0
            
            ai_offset = page_num * ai_limit
            cf_offset = page_num * cf_limit
            
            logger.info(f"[Behavior-Hybrid] Page {page_num} (Offset {offset}): AI={ai_limit} (Off:{ai_offset}), CF={cf_limit} (Off:{cf_offset})")

            # 1. AI Hybrid Match (Semantic Profile)
            futures["ai"] = executor.submit(
                run_in_context,
                app,
                _get_ai_embedding_recommendations,
                user_id,
                list(viewed_book_ids),
                search_queries[:5], 
                favorite_book_ids,
                high_rated_books, 
                explicit_genres,  # 🆕 Pass explicit genres
                ai_limit,
                ai_offset
            )
            
            # 2. Collaborative Filtering (Similar Users)
            futures["cf"] = executor.submit(
                run_in_context,
                app,
                _get_cf_recommendations,
                user_id, cf_limit, cf_offset
            )
            
            # 3. Exploration (Google Books / OpenLib based on explicit interests & searches)
            def fetch_exploration():
                # We reuse the same page logic for exploration
                # 'offset' passed to parent function represents global offset
                # We map it to 'page' for external APIs if needed
                explore_page_num = page_num 
                results = []
                seen_ex = set(viewed_google_ids)
                
                # Check if this is "View All" (High Limit)
                is_view_all = limit > 25
                
                targets = []
                
                if is_view_all:
                    # ✅ View All Strategy: Time Machine (Pagination = Back in Time)
                    # Instead of showing EVERYTHING, we show a SLICE based on offset
                    # Page 1 (offset 0): Newest Interests
                    # Page 2 (offset > 0): Older Interests
                    
                    # 1. Build Full Chronological Timeline
                    timeline = []
                    
                    # A) Search History (Newest First)
                    seen_timeline = set()
                    for q in search_queries:
                        if q and q not in seen_timeline:
                            timeline.append(q)
                            seen_timeline.add(q)
                            
                    # B) High Weight Categories (After searches)
                    sorted_cats = sorted(category_weights.items(), key=lambda x: x[1], reverse=True)
                    for cat, _ in sorted_cats:
                         if cat and cat not in seen_timeline:
                             timeline.append(cat)
                             seen_timeline.add(cat)
                             
                    # C) Explicit Genres
                    for g in explicit_genres:
                        if g and g not in seen_timeline:
                            timeline.append(g)
                            seen_timeline.add(g)
                    
                    # 2. Determine "Page" of interests
                    # Assume we show 3-4 distinct topics per "page" of results
                    # Each topic yields ~6 books. So 24 books ~= 4 topics.
                    topics_per_page = 4
                    current_page = page_num  # Use the calculated page number
                    
                    start_idx = current_page * topics_per_page
                    end_idx = start_idx + topics_per_page
                    
                    # Get targets for THIS page
                    targets = timeline[start_idx:end_idx]
                    
                    # If we ran out of timeline, maybe random fallback or loop?
                    # Let's loop for infinite discovery but slightly shuffled
                    if not targets and timeline:
                        # Modulo wrap around
                        wraparound_idx = start_idx % len(timeline)
                        # Pick from there but randomize slightly to avoid exact duplicate pages
                        targets = timeline[wraparound_idx:wraparound_idx+topics_per_page]
                        if len(targets) < topics_per_page:
                             targets.extend(timeline[:topics_per_page-len(targets)])
                    
                    logger.info(f"[Exploration] View All Page {current_page}: targets={targets}")
                    
                else:
                    # ✅ Homepage Strategy: Focused & Diverse
                    pass_pool = list(explicit_genres)

                    # Add heavy weights
                    for cat, count in category_weights.items():
                        if count >= 2: pass_pool.append(cat)
                    
                    # 1. Top Priority: Last Search
                    if search_queries:
                        last_search = search_queries[0]
                        targets.append(last_search)
                    
                    # 2. Random fill
                    remaining_slots = 3 - len(targets)
                    if remaining_slots > 0 and pass_pool:
                        import random
                        pool_set = set(pass_pool) - set(targets)
                        if pool_set:
                            picked = random.sample(list(pool_set), min(remaining_slots, len(pool_set)))
                            targets.extend(picked)

                for i, topic in enumerate(targets):
                    try:
                        # Determine count based on mode
                        # View All: 6 books per topic
                        # Homepage: 8 for main, 4 for others
                        if is_view_all:
                            count = 6
                        else:
                            count = 8 if (search_queries and topic == search_queries[0]) else 4
                        
                        # Calculate offset for this specific topic based on page number
                        # to ensure we don't show the same books for the same topic on page 2, 3, etc.
                        topic_offset = page_num * count
                        
                        items, _ = fetch_google_books(f"subject:{topic}", max_results=count, start_index=topic_offset)
                        if not items and search_queries and topic == search_queries[0]:
                             items, _ = fetch_google_books(topic, max_results=count, start_index=topic_offset)

                        for it in items or []:
                            gid = it.get("id")
                            if not gid or gid in seen_ex: continue
                            seen_ex.add(gid)
                            
                            vi = it.get("volumeInfo", {})
                            title = vi.get("title")
                            if not title: continue
                            
                            img = (vi.get("imageLinks") or {}).get("thumbnail") or ""
                            if img.startswith("http://"): img = "https://" + img[7:]
                            
                            # Score calculation for sorting preservation
                            # Newest topics get higher score
                            base_score = 0.95 - (i * 0.05) 
                            if base_score < 0.5: base_score = 0.5
                            
                            results.append({
                                "id": gid,
                                "title": title,
                                "author": ", ".join(vi.get("authors") or []),
                                "cover": img,
                                "source": "اهتماماتك",
                                "reason": f"✨ لأنك مهتم بـ: {topic}",
                                "rating": vi.get("averageRating"),
                                "score": base_score, 
                                "rec_type": "exploration",
                                "sort_index": i # Help preserve order
                            })
                    except Exception as e:
                        logger.error(f"[Exploration] Error for {topic}: {e}")
                return results

            futures["explore"] = executor.submit(fetch_exploration)
            
            # تجميع النتائج
            ai_recs = []
            cf_recs = []
            explore_recs = []
            
            for key, future in futures.items():
                try:
                    res = future.result(timeout=12)
                    if key == "ai": ai_recs = res
                    elif key == "cf": cf_recs = res
                    elif key == "explore": explore_recs = res
                except Exception as e:
                    logger.error(f"[Behavior-Hybrid] Future {key} failed: {e}")

        # ---------------------------------------------------------
        # 3. الدمج والتنوع (Ranking & Diversity)
        # ---------------------------------------------------------
        
        # دمج الكل
        combined = ai_recs + cf_recs + explore_recs
        
        # إزالة التكرار
        unique_recs = []
        seen_final = set()
        
        # نضيف كتب من المكتبة المحلية أولاً (AI results usually local)
        for r in combined:
            rid = r.get("id")
            if not rid or rid in seen_final: continue
            seen_final.add(rid)
            unique_recs.append(r)
            
        # تطبيق MMR للتنوع (اختياري, أو مجرد خلط ذكي)
        # لنستخدم دالة التنوع الموجودة إذا أحببنا, أو نكتفي بالخلط
        if limit > 25:
             # ✅ View All Mode: Strict sorting by Score (Time/Relevance)
             # We want to preserve the chronological order implied by scores in fetch_exploration
             final_diverse = sorted(unique_recs, key=lambda x: x.get("score", 0), reverse=True)
             
             # Still ensure we don't have 10 books from same author in a row?
             # For "My Interests" timeline, it's okay to have blocks of related content.
        else:
             # Homepage Mode: Use MMR for diversity
             # سنستخدم _apply_mmr_diversity لضمان عدم طغيان مؤلف واحد
             final_diverse = _apply_mmr_diversity(unique_recs, lambda_param=0.5, max_per_category=2)
        
        # تنظيف البيانات
        final_output = []
        for rec in final_diverse[:limit]:
            # نحتفظ بالسبب والمصدر
            # rec["reason"] is already set by helper functions
            final_output.append(rec)
            
        logger.info(f"[Behavior-Hybrid] Returning {len(final_output)} recommendations. "
                    f"(AI: {len(ai_recs)}, CF: {len(cf_recs)}, Explore: {len(explore_recs)})")
        
        return final_output

    except Exception as e:
        logger.error(f"[Behavior-Hybrid] Critical Error: {e}", exc_info=True)
        # Fallback to trending
        return get_trending(limit=limit)


# ------------------------------------------------------------------
# 🧠 Behavior-Based Recommendations – مثل YouTube
# ------------------------------------------------------------------


@cache.memoize(timeout=300)  # Cache لمدة 5 دقائق
def _get_behavior_based_recommendations_legacy(user_id, limit=12):
    """
    [DEPRECATED] Legacy function replaced by get_behavior_based_recommendations
    
    YouTube-style recommendations based on user behavior.
    Algorithm:
    1. Analyze viewed books -> Extract categories + authors
    2. Calculate weight (views * recency)
    3. Find books from top weighted categories/authors
    4. Mix results with diversity
    """
    from datetime import datetime, timedelta
    from collections import defaultdict
    from concurrent.futures import ThreadPoolExecutor, as_completed

    
    try:
        # 1. جلب آخر 50 كتاب مشاهد مع تفاصيلها
        recent_views = (
            UserBookView.query
            .filter_by(user_id=user_id)
            .order_by(UserBookView.last_viewed_at.desc())
            .limit(50)
            .all()
        )
        
        if not recent_views:
            logger.debug(f"[Behavior] No views found for user {user_id}")
            return []
        
        # 2. تحليل السلوك: استخراج التصنيفات والمؤلفين مع الأوزان
        category_weights = defaultdict(float)
        author_weights = defaultdict(float)
        now = datetime.utcnow()
        week_ago = now - timedelta(days=7)
        
        viewed_google_ids = set()  # لاستثناء الكتب المشاهدة
        
        for view in recent_views:
            # حساب عامل الحداثة (كتب الأسبوع الأخير تحصل على 1.5x)
            recency_factor = 1.5 if view.last_viewed_at and view.last_viewed_at > week_ago else 1.0
            view_weight = (view.view_count or 1) * recency_factor
            
            if view.google_id:
                viewed_google_ids.add(view.google_id)
            
            # جلب معلومات الكتاب
            book = None
            if view.book_id:
                book = Book.query.get(view.book_id)
            elif view.google_id:
                book = Book.query.filter_by(google_id=view.google_id).first()
            
            if not book:
                continue
            
            # استخراج التصنيفات
            categories = book.categories or ""
            if categories:
                # التصنيفات قد تكون JSON أو مفصولة بفاصلة
                try:
                    import json
                    cats = json.loads(categories) if categories.startswith('[') else categories.split(',')
                except:
                    cats = categories.split(',')
                
                for cat in cats:
                    cat = cat.strip()
                    if cat and len(cat) > 2:
                        category_weights[cat] += view_weight
            
            # استخراج المؤلف (وزن أعلى 1.5x)
            if book.author:
                # أخذ المؤلف الأول فقط
                first_author = book.author.split(',')[0].strip()
                if first_author and first_author not in ['Unknown', 'مؤلف غير معروف']:
                    author_weights[first_author] += view_weight * 1.5
        
        # 3. ترتيب التصنيفات والمؤلفين حسب الوزن
        top_categories = sorted(category_weights.items(), key=lambda x: x[1], reverse=True)[:5]
        top_authors = sorted(author_weights.items(), key=lambda x: x[1], reverse=True)[:3]
        
        logger.info(f"[Behavior] User {user_id} - Top categories: {top_categories[:3]}, Top authors: {top_authors[:2]}")
        
        if not top_categories and not top_authors:
            logger.debug(f"[Behavior] No behavior patterns found for user {user_id}")
            return []
        
        # 4. البحث عن كتب مشابهة بالتوازي
        all_recs = []
        seen_ids = set(viewed_google_ids)  # استثناء الكتب المشاهدة
        
        def search_by_category(category, weight):
            """البحث بالتصنيف"""
            try:
                items, _ = fetch_google_books(f"subject:{category}", max_results=8)
                results = []
                for it in items or []:
                    gid = it.get("id")
                    if not gid:
                        continue
                    vi = it.get("volumeInfo", {})
                    title = vi.get("title")
                    if not title:
                        continue
                    imgs = vi.get("imageLinks", {}) or {}
                    cover = imgs.get("thumbnail") or ""
                    if cover.startswith("http://"):
                        cover = "https://" + cover[7:]
                    
                    results.append({
                        "id": gid,
                        "title": title,
                        "author": ", ".join(vi.get("authors", [])),
                        "cover": cover,
                        "source": "سلوكك",
                        "reason": f"📚 من تصنيف: {category}",
                        "rating": vi.get("averageRating"),
                        "weight": weight,
                        "type": "category"
                    })
                return results
            except Exception as e:
                logger.error(f"[Behavior] Category search error for {category}: {e}")
                return []
        
        def search_by_author(author, weight):
            """البحث بالمؤلف"""
            try:
                items, _ = fetch_google_books(f"inauthor:{author}", max_results=6)
                results = []
                for it in items or []:
                    gid = it.get("id")
                    if not gid:
                        continue
                    vi = it.get("volumeInfo", {})
                    title = vi.get("title")
                    if not title:
                        continue
                    imgs = vi.get("imageLinks", {}) or {}
                    cover = imgs.get("thumbnail") or ""
                    if cover.startswith("http://"):
                        cover = "https://" + cover[7:]
                    
                    results.append({
                        "id": gid,
                        "title": title,
                        "author": ", ".join(vi.get("authors", [])),
                        "cover": cover,
                        "source": "سلوكك",
                        "reason": f"✍️ أعمال: {author}",
                        "rating": vi.get("averageRating"),
                        "weight": weight * 1.2,  # المؤلف أهم قليلاً
                        "type": "author"
                    })
                return results
            except Exception as e:
                logger.error(f"[Behavior] Author search error for {author}: {e}")
                return []
        
        # تشغيل البحث بالتوازي
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = []
            
            # البحث بالتصنيفات
            for cat, weight in top_categories:
                futures.append(executor.submit(search_by_category, cat, weight))
            
            # البحث بالمؤلفين
            for author, weight in top_authors:
                futures.append(executor.submit(search_by_author, author, weight))
            
            # جمع النتائج
            for future in as_completed(futures, timeout=10):
                try:
                    results = future.result(timeout=8)
                    for book in results:
                        if book["id"] not in seen_ids:
                            seen_ids.add(book["id"])
                            all_recs.append(book)
                except Exception as e:
                    logger.error(f"[Behavior] Future error: {e}")
        
        # 5. ترتيب النتائج بشكل ذكي
        # نجمع بين الوزن والتنوع
        all_recs.sort(key=lambda x: x.get("weight", 0), reverse=True)
        
        # نختار مع تنوع: 60% من التصنيفات, 40% من المؤلفين
        category_recs = [r for r in all_recs if r.get("type") == "category"]
        author_recs = [r for r in all_recs if r.get("type") == "author"]
        
        final_recs = []
        cat_count = int(limit * 0.6)
        auth_count = limit - cat_count
        
        final_recs.extend(category_recs[:cat_count])
        final_recs.extend(author_recs[:auth_count])
        
        # إذا لم يكتمل العدد, نكمل من الباقي
        if len(final_recs) < limit:
            remaining = [r for r in all_recs if r not in final_recs]
            final_recs.extend(remaining[:limit - len(final_recs)])
        
        # خلط خفيف للتنوع
        random.shuffle(final_recs)
        
        # تنظيف الحقول الإضافية
        for rec in final_recs:
            rec.pop("weight", None)
            rec.pop("type", None)
        
        logger.info(f"[Behavior] Generated {len(final_recs)} recommendations for user {user_id}")
        return final_recs[:limit]
        
    except Exception as e:
        logger.error(f"[Behavior] Error: {e}", exc_info=True)
        return []

# ------------------------------------------------------------------
# 3.5) Semantic Search – بحث دلالي بالـ AI
# ------------------------------------------------------------------


def semantic_search(query: str, limit: int = 12, exclude_book_ids: list = None):
    """
    بحث دلالي: يحول الاستعلام إلى embedding ويقارنه مع embeddings الكتب.
    
    يفهم المعنى وليس فقط الكلمات:
    - "تعلم البرمجة" يجد كتب Python, JavaScript, etc.
    - "روايات رومانسية" يجد كتب الحب والعلاقات
    
    Args:
        query: نص البحث
        limit: عدد النتائج المطلوبة
        exclude_book_ids: قائمة IDs الكتب المستثناة
        
    Returns:
        قائمة من القواميس تمثل الكتب المطابقة
    """
    if not query or not query.strip():
        return []
    
    exclude_book_ids = exclude_book_ids or []
    
    # 1. تحويل الاستعلام إلى embedding
    query_embedding = get_text_embedding(query)
    if not query_embedding:
        logger.warning(f"[SemanticSearch] Failed to get embedding for: {query}")
        return []
    
    query_vec = np.array(query_embedding, dtype=np.float32).reshape(1, -1)
    
    # 2. جلب جميع embeddings الكتب
    all_embeds = BookEmbedding.query.all()
    if not all_embeds:
        logger.info("[SemanticSearch] No book embeddings found")
        return []
    
    book_ids = []
    vectors = []
    
    for row in all_embeds:
        if row.book_id in exclude_book_ids:
            continue
        if row.vector is None:
            continue
        
        v = np.array(row.vector, dtype=np.float32)
        if v.ndim == 1:
            book_ids.append(row.book_id)
            vectors.append(v)
    
    if not vectors:
        return []
    
    # 3. حساب التشابه
    mat = np.vstack(vectors)
    try:
        similarities = cosine_similarity(query_vec, mat)[0]
    except Exception as e:
        logger.error(f"[SemanticSearch] Similarity error: {e}")
        return []
    
    # 4. ترتيب حسب التشابه
    ranked_indices = np.argsort(similarities)[::-1]
    
    results = []
    for idx in ranked_indices[:limit * 2]:  # نأخذ أكثر للتصفية
        score = similarities[idx]
        if score < 0.3:  # عتبة الحد الأدنى للتشابه
            continue
        
        book = Book.query.get(book_ids[idx])
        if not book:
            continue
        
        results.append(
            _book_to_dict(
                book,
                source="AI Search",
                reason=f"🔍 تشابه: {score:.0%}",
            )
        )
        
        if len(results) >= limit:
            break
    
    logger.info(f"[SemanticSearch] Found {len(results)} matches for '{query}'")
    return results


# ------------------------------------------------------------------
# 4) Topic-based – من اهتماماتك
# ------------------------------------------------------------------


# recommender.py

# @cache.memoize(timeout=60)  # DISABLED for pagination to work
def get_topic_based(user_id, limit=24, offset=0, prefs_limit=3, recent_query=None):
    """
    توصيات مبنية على اهتمامات المستخدم (Topic-Based Recommendations).
    محسّن: يستخدم التشغيل المتوازي لجلب الكتب من 5 مصادر في آن واحد!
    
    Args:
        user_id: معرف المستخدم
        limit: الحد الأقصى لعدد التوصيات
        offset: بداية النتائج (للتصفح)
        prefs_limit: عدد التفضيلات المستخدمة
        recent_query: استعلام بحث فوري لتجاوز سجل البحث.
        
    Returns:
        قائمة من القواميس تمثل الكتب المقترحة من مصادر مختلفة
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    topics = []
    seen_topics = set()
    potential_topics = []
    
    logger.info(f"[Topic] Getting topic-based recommendations for user {user_id}, offset={offset}")

    # ---------------------------------------------------------
    # 🆕 تصفية الكتب التي يمتلكها المستخدم أو مهتم بها مسبقاً
    # ---------------------------------------------------------
    exclude_gids = set()
    try:
        # 1. كتب رفعها المستخدم
        user_books = Book.query.filter_by(owner_id=user_id).all()
        for b in user_books:
            if b.google_id: exclude_gids.add(b.google_id)
            
        # 2. كتب في مفضلة/قائمة المستخدم (BookStatus)
        from .models import BookStatus
        statuses = BookStatus.query.filter_by(user_id=user_id).all()
        for s in statuses:
            if s.book and s.book.google_id:
                exclude_gids.add(s.book.google_id)
                
        # 3. كتب تم تقييمها (UserRatingCF)
        ratings = UserRatingCF.query.filter_by(user_id=user_id).all()
        for r in ratings:
            if r.google_id: exclude_gids.add(r.google_id)
            
    except Exception as e:
        logger.error(f"[Topic] Error getting excluded books: {e}")

    # 1. تجميع المواضيع المحتملة بالترتيب حسب الأولوية
    # 🔧 FIX: نعطي الأولوية للاهتمامات المسجلة من الـ onboarding أولاً
    if recent_query:
        potential_topics.append(recent_query)

    # 🎯 الأولوية الأولى: اهتمامات المستخدم الفعلية من الـ onboarding
    try:
        # جلب الاهتمامات بترتيب الوزن (الأعلى أولاً = الأحدث/الأهم)
        prefs = UserPreference.query.filter_by(user_id=user_id).order_by(UserPreference.weight.desc()).all()
        for p in prefs:
            # 🔧 FIX: تجاهل المواضيع الخاصة بالنظام
            if p.topic and not p.topic.startswith('special:'):
                potential_topics.append(p.topic)
    except Exception as e:
        logger.error(f"[Topic] prefs error: {e}", exc_info=True)

    # الأولوية الثانوية: آخر بحث
    try:
        last_search = db.session.query(SearchHistory).filter_by(user_id=user_id).order_by(SearchHistory.created_at.desc(), SearchHistory.id.desc()).first()
        if last_search:
            potential_topics.append(last_search.query)
    except Exception as e:
        logger.error(f"[Topic] History error: {e}", exc_info=True)

    # 2. معالجة المواضيع (ترجمة + إزالة تكرار)
    all_unique_topics = []  # كل المواضيع الفريدة بالترتيب
    for t in potential_topics:
        if not t or not t.strip():
            continue
        
        query_text = t.strip()
        topic_to_use = query_text
        
        # ترجمة إذا كان عربياً
        if any("\u0600" <= c <= "\u06FF" for c in query_text):
            try:
                translated = translate_to_english_with_gemini(query_text)
                if translated and translated.strip():
                    topic_to_use = translated
                    logger.info(f"[Topic] Translated '{query_text}' to '{topic_to_use}'")
            except Exception as e:
                logger.warning(f"[Topic] Translation failed for '{query_text}': {e}")
        
        # إضافة الموضوع إذا لم يكن مكرراً
        if topic_to_use.lower() not in seen_topics:
            all_unique_topics.append(topic_to_use)
            seen_topics.add(topic_to_use.lower())

    if not all_unique_topics:
        logger.debug(f"[Topic] No topics found for user {user_id}")
        return []

    # 🔧 FIX: التصفح عبر الاهتمامات حسب الصفحة
    # كل صفحة تعرض اهتمامات مختلفة (3 اهتمامات لكل صفحة)
    topics_per_page = 3
    current_page = (offset // limit) if limit > 0 else 0
    start_topic_idx = current_page * topics_per_page
    
    # اختيار الاهتمامات لهذه الصفحة
    topics = all_unique_topics[start_topic_idx:start_topic_idx + topics_per_page]
    
    # 🆕 تحديد ما إذا انتهت الاهتمامات
    # الاهتمامات تنتهي إذا كانت الصفحة التالية ستكون فارغة
    next_page_start = (current_page + 1) * topics_per_page
    interests_exhausted = next_page_start >= len(all_unique_topics)
    
    # إذا انتهت الاهتمامات في هذه الصفحة (لا توجد اهتمامات لعرضها)
    if not topics:
        # نعرض آخر اهتمامات متاحة بدلاً من العودة للبداية
        interests_exhausted = True
        start_topic_idx = max(0, len(all_unique_topics) - topics_per_page)
        topics = all_unique_topics[start_topic_idx:]
    
    logger.info(f"[Topic] Page {current_page + 1}: Using topics {start_topic_idx + 1}-{start_topic_idx + len(topics)} of {len(all_unique_topics)}: {topics} (exhausted: {interests_exhausted})")
    all_books = []
    seen_ids = set()
    
    # 🚀 جلب الكتب من جميع المصادر بالتوازي لكل موضوع
    per_topic_limit = max(4, int(limit / len(topics))) if topics else limit
    
    # 🔧 استخدام رقم الصفحة للـ APIs
    # الصفحة الأولى من كل اهتمام (لأننا غيرنا الاهتمام نفسه)
    api_page = 1
    global_offset = 0
    
    def process_google_result(items, topic):
        """معالجة نتائج Google Books"""
        books = []
        for it in items or []:
            if not isinstance(it, dict):
                continue
            gid = it.get("id")
            if not gid:
                continue
            vi = it.get("volumeInfo") or {}
            title = vi.get("title")
            # 🔧 FIX: تجاهل الكتب بدون عنوان
            if not title or not title.strip():
                continue
            img = (vi.get("imageLinks") or {}).get("thumbnail")
            if img:
                if img.startswith("http://"):
                    img = img.replace("http://", "https://")
                if '&edge=curl' in img:
                    img = img.replace('&edge=curl', '').replace('&edge=curl&', '&')
            
            # 🆕 جلب التقييم من Google Books API مع Fallback
            rating = _extract_rating_with_fallback(vi)
            ratings_count = vi.get("ratingsCount")
            
            books.append({
                "id": gid,
                "title": title,
                "author": ", ".join(vi.get("authors") or []),
                "cover": img,
                "source": "Google Books",
                "reason": f"🎯 لأنك بحثت مؤخراً عن «{topic}»",
                "rating": rating,
                "ratings_count": ratings_count,
            })
        return books
    
    def fetch_all_sources_for_topic(topic, per_source, topic_offset, topic_page):
        """جلب الكتب من جميع المصادر لموضوع واحد بالتوازي"""
        results = []
        
        def fetch_google():
            try:
                # Google يستخدم startIndex
                gb_res = fetch_google_books(topic, max_results=per_source, start_index=topic_offset)
                items = gb_res[0] if isinstance(gb_res, tuple) else gb_res
                return ("google", process_google_result(items, topic))
            except Exception as e:
                logger.error(f"[Topic] Google error for '{topic}': {e}")
                return ("google", [])
        
        def fetch_itbook():
            try:
                # IT Bookstore يستخدم page
                # لا يمكننا تحديد offset دقيق, لذا نستخدم الصفحة
                # ITBS صفحتها عادة 10 كتب
                books = fetch_itbook_books(topic, limit=per_source, page=topic_page) or []
                # 🔧 FIX: تحقق من وجود العنوان والـ ID
                return ("itbook", [{
                    "id": b.get("id"),
                    "title": b.get("title"),
                    "author": b.get("author"),
                    "cover": b.get("cover"),
                    "source": "IT Bookstore",
                    "reason": f"🎯 كتب تقنية: «{topic}»",
                } for b in books if b.get("id") and b.get("title")])
            except Exception as e:
                logger.error(f"[Topic] ITBook error for '{topic}': {e}")
                return ("itbook", [])
        
        def fetch_openlib():
            try:
                # OpenLibrary يدعم offset
                books = fetch_openlib_books(topic, limit=per_source, offset=topic_offset) or []
                # 🔧 FIX: تحقق من وجود العنوان والـ ID
                return ("openlib", [{
                    "id": b.get("id"),
                    "title": b.get("title"),
                    "author": b.get("author"),
                    "cover": b.get("cover"),
                    "source": "OpenLibrary",
                    "reason": f"🎯 OpenLibrary: «{topic}»",
                } for b in books if b.get("id") and b.get("title")])
            except Exception as e:
                logger.error(f"[Topic] OpenLib error for '{topic}': {e}")
                return ("openlib", [])
        
        def fetch_archive():
            try:
                # Archive يدعم page (تقريبي)
                books = fetch_archive_books(topic, limit=per_source) or []
                # 🔧 FIX: تحقق من وجود العنوان والـ ID
                return ("archive", [{
                    "id": b.get("id"),
                    "title": b.get("title"),
                    "author": b.get("author"),
                    "cover": b.get("cover"),
                    "source": "Internet Archive",
                    "reason": f"📚 من أرشيف الإنترنت: «{topic}»",
                } for b in books if b.get("id") and b.get("title")])
            except Exception as e:
                logger.error(f"[Topic] Archive error for '{topic}': {e}")
                return ("archive", [])
        
        def fetch_gutenberg():
            try:
                # Gutenberg uses page
                books = fetch_gutenberg_books(topic, limit=per_source, page=topic_page) or []
                # 🔧 FIX: تحقق من وجود العنوان والـ ID
                return ("gutenberg", [{
                    "id": b.get("id"),
                    "title": b.get("title"),
                    "author": b.get("author"),
                    "cover": b.get("cover"),
                    "source": "Project Gutenberg",
                    "reason": f"📖 كلاسيكيات: «{topic}»",
                } for b in books if b.get("id") and b.get("title")])
            except Exception as e:
                logger.error(f"[Topic] Gutenberg error for '{topic}': {e}")
                return ("gutenberg", [])
        
        # 🚀 تشغيل كل المصادر بالتوازي!
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(fetch_google),
                executor.submit(fetch_itbook),
                executor.submit(fetch_openlib),
                executor.submit(fetch_archive),
                executor.submit(fetch_gutenberg),
            ]
            
            # 🛡️ معالجة الـ timeout بأمان
            try:
                for future in as_completed(futures, timeout=8):
                    try:
                        source, books = future.result(timeout=6)
                        results.extend(books)
                    except Exception as e:
                        logger.error(f"[Topic] Future error for '{topic}': {e}")
            except TimeoutError:
                logger.warning(f"[Topic] ⏱️ Timeout fetching sources for '{topic}', using partial results")
        
        return results
    
    # جلب الكتب لكل موضوع
    for i, t in enumerate(topics):
        current_limit = per_topic_limit + 2 if i == 0 else per_topic_limit
        per_source = max(4, int(current_limit / 3))
        
        # 🔧 FIX: نستخدم الصفحة الأولى من كل اهتمام جديد
        this_offset = global_offset
        this_page = api_page
        
        logger.debug(f"[Topic] Searching for '{t}' with limit {per_source}, offset {this_offset}, page {this_page}")
        
        topic_books = fetch_all_sources_for_topic(t, per_source, this_offset, this_page)
        
        for book in topic_books:
            bid = book.get("id")
            title = book.get("title")
            
            # 🔧 FIX: ضمان أن العنوان نص وليس كائن
            if title:
                title = str(title).strip()
                book["title"] = title
            
            # 🔧 FIX: تجاهل الكتب التي ليس لها عنوان صحيح أو تبدو ككائنات تالفة
            if not bid or bid in seen_ids or bid in exclude_gids: # 🆕 Check against exclude_gids
                continue
            
            # تجاهل العناوين التي تبدو كتمثيل لكائن Python (<...>)
            if title and (title.startswith('<') and '>' in title and 'object at' in title):
                 logger.warning(f"[Topic] Skipping corrupted title book: {bid} - {title}")
                 continue

            if not title:
                logger.debug(f"[Topic] Skipping book {bid} - no title")
                continue
            seen_ids.add(bid)
            all_books.append(book)
        
        if len(all_books) >= limit:
            break

    result = all_books[:limit]
    logger.info(f"[Topic] Returning {len(result)} books for user {user_id} (from {len(all_books)} total found)")
    if len(result) == 0:
        logger.warning(f"[Topic] No books found for user {user_id} with topics: {topics}")
    
    # 🆕 إرجاع النتائج مع معلومات عن حالة الاهتمامات
    # نضيف الـ metadata كـ attribute على القائمة لتجنب كسر التوافقية
    result_with_meta = {
        'books': result,
        'interests_exhausted': interests_exhausted,
        'total_interests': len(all_unique_topics),
        'current_page': current_page + 1
    }
    return result_with_meta


def get_personal_trending(user_id, limit=12):
    """
    يحصل على كتب رائجة مخصصة للمستخدم بناءً على اهتماماته.
    
    يجمع بين:
    - آخر بحث قام به المستخدم
    - تفضيلاته (UserPreference)
    - الكتب الرائجة في مواضيع اهتمامه
    
    Args:
        user_id: معرف المستخدم
        limit: عدد الكتب المطلوبة
        
    Returns:
        قائمة من القواميس تمثل الكتب الرائجة المخصصة
    """
    books_dicts = []
    seen_ids = set()
    topics_to_search = []
    
    try:
        last_search = (
            db.session.query(SearchHistory)
            .filter_by(user_id=user_id)
            .order_by(SearchHistory.created_at.desc(), SearchHistory.id.desc())
            .first()
        )
        if last_search and last_search.query:
            query_text = last_search.query.strip()
            # ترجمة إذا كان عربياً
            if any("\u0600" <= c <= "\u06FF" for c in query_text):
                try:
                    translated = translate_to_english_with_gemini(query_text)
                    if translated and translated.strip():
                        topics_to_search.append(translated)
                        logger.info(f"[PersonalTrending] Using last search: '{query_text}' -> '{translated}'")
                    else:
                        topics_to_search.append(query_text)
                except Exception as e:
                    logger.warning(f"[PersonalTrending] Translation failed: {e}")
                    topics_to_search.append(query_text)
            else:
                topics_to_search.append(query_text)
    except Exception as e:
        logger.error(f"[PersonalTrending] Error getting last search: {e}", exc_info=True)
    
    # 2) جمع المواضيع من التفضيلات
    try:
        prefs = (
            UserPreference.query
            .filter_by(user_id=user_id)
            .order_by(UserPreference.weight.desc())
            .limit(3)
            .all()
        )
        for pref in prefs:
            if pref.topic:
                # ترجمة إذا كان عربياً
                if any("\u0600" <= c <= "\u06FF" for c in pref.topic):
                    try:
                        translated = translate_to_english_with_gemini(pref.topic)
                        if translated and translated.strip() and translated.lower() not in [t.lower() for t in topics_to_search]:
                            topics_to_search.append(translated)
                    except:
                        if pref.topic.lower() not in [t.lower() for t in topics_to_search]:
                            topics_to_search.append(pref.topic)
                else:
                    if pref.topic.lower() not in [t.lower() for t in topics_to_search]:
                        topics_to_search.append(pref.topic)
    except Exception as e:
        logger.error(f"[PersonalTrending] Error getting preferences: {e}", exc_info=True)
    
    # 3) إذا لم توجد مواضيع, نستخدم الكتب الرائجة العامة
    if not topics_to_search:
        logger.info(f"[PersonalTrending] No personal topics found for user {user_id}, using general trending")
        return get_trending(limit)
    
    logger.info(f"[PersonalTrending] Searching for books in topics: {topics_to_search}")
    
    # 4) البحث عن كتب في مواضيع اهتمامه
    per_topic_limit = max(4, limit // len(topics_to_search))
    
    for topic in topics_to_search[:3]:  # أول 3 مواضيع فقط
        # Google Books
        try:
            gb_res = fetch_google_books(topic, max_results=per_topic_limit)
            items = gb_res[0] if isinstance(gb_res, tuple) else gb_res
            
            for it in items or []:
                if not isinstance(it, dict):
                    continue
                gid = it.get("id")
                if not gid or gid in seen_ids:
                    continue
                seen_ids.add(gid)
                
                vi = it.get("volumeInfo") or {}
                img = (vi.get("imageLinks") or {}).get("thumbnail")
                if img:
                    if img.startswith("http://"):
                        img = img.replace("http://", "https://")
                    # إزالة edge=curl من روابط Google Books لتحسين الأداء
                    if '&edge=curl' in img:
                        img = img.replace('&edge=curl', '').replace('&edge=curl&', '&')
                
                books_dicts.append({
                    "id": gid,
                    "title": vi.get("title"),
                    "author": ", ".join(vi.get("authors") or []),
                    "cover": img,
                    "source": "Google Books",
                    "reason": f"🔥 رائج في موضوع: {topic}",
                    "rating": _extract_rating_with_fallback(vi),
                    "ratings_count": vi.get("ratingsCount"),
                })
                
                if len(books_dicts) >= limit:
                    break
        except Exception as e:
            logger.error(f"[PersonalTrending] Google Books error for '{topic}': {e}", exc_info=True)
        
        if len(books_dicts) >= limit:
            break
    
    # 5) إذا لم تكن كافية, نضيف كتب رائجة عامة
    if len(books_dicts) < limit:
        needed = limit - len(books_dicts)
        general_trending = get_trending(needed * 2)
        for book in general_trending:
            book_id = book.get("id")
            if book_id and book_id not in seen_ids:
                seen_ids.add(book_id)
                books_dicts.append(book)
                if len(books_dicts) >= limit:
                    break
    
    # خلط النتائج
    random.shuffle(books_dicts)
    result = books_dicts[:limit]
    logger.info(f"[PersonalTrending] Returning {len(result)} personalized trending books for user {user_id}")
    return result


def get_last_search_recommendations(user_id, limit=12):
    """
    جلب توصيات بناءً على آخر عملية بحث قام بها المستخدم حصراً.
    الغرض: إعطاء المستخدم شعوراً فورياً بتجاوب النظام.
    """
    books_dicts = []
    seen_ids = set()
    
    try:
        # 1. جلب آخر بحث
        last_search = (
            db.session.query(SearchHistory)
            .filter_by(user_id=user_id)
            .order_by(SearchHistory.created_at.desc(), SearchHistory.id.desc())
            .first()
        )
        
        if not last_search or not last_search.query:
            return None, None # لا يوجد بحث سابق
            
        query_text = last_search.query.strip()
        display_query = query_text
        
        # ترجمة إذا لزم الأمر للبحث (لكن نعرض الكلمة الأصلية للمستخدم)
        search_term = query_text
        if any("\u0600" <= c <= "\u06FF" for c in query_text):
            try:
                translated = translate_to_english_with_gemini(query_text)
                if translated and translated.strip():
                    search_term = translated
            except:
                pass
                
        # 2. البحث في المصادر (Google Books بشكل أساسي للسرعة والتنوع)
        gb_res = fetch_google_books(search_term, max_results=limit)
        items = gb_res[0] if isinstance(gb_res, tuple) else gb_res
        
        for it in items or []:
            if not isinstance(it, dict): continue
            gid = it.get("id")
            if not gid or gid in seen_ids: continue
            seen_ids.add(gid)

            vi = it.get("volumeInfo") or {}
            img = (vi.get("imageLinks") or {}).get("thumbnail")
            if img:
                if img.startswith("http://"):
                    img = img.replace("http://", "https://")
                if '&edge=curl' in img:
                    img = img.replace('&edge=curl', '').replace('&edge=curl&', '&')

            books_dicts.append({
                "id": gid,
                "title": vi.get("title"),
                "author": ", ".join(vi.get("authors") or []),
                "cover": img,
                "source": "Google Books",
                "reason": f"لأنك بحثت عن: {display_query}",
                "rating": vi.get("averageRating"),
                "ratings_count": vi.get("ratingsCount"),
            })
            
            if len(books_dicts) >= limit:
                break
                
        return display_query, books_dicts
        
    except Exception as e:
        logger.error(f"[LastSearch] Error: {e}", exc_info=True)
        return None, None


def get_archive_ai_recommendations(user_id, limit=16):
    """
    توصيات ذكية من Internet Archive بناءً على اهتمامات المستخدم.
    يستخدم الذكاء الاصطناعي لترجمة الاستعلام العربي.
    
    Args:
        user_id: معرف المستخدم
        limit: عدد النتائج
        
    Returns:
        قائمة من القواميس تمثل الكتب من Archive
    """
    books = []
    seen_ids = set()
    search_topics = []
    
    # 1) جلب اهتمامات المستخدم
    try:
        # آخر بحث
        last_search = (
            db.session.query(SearchHistory)
            .filter_by(user_id=user_id)
            .order_by(SearchHistory.created_at.desc())
            .first()
        )
        if last_search and last_search.query:
            search_topics.append(last_search.query.strip())
            
        # التفضيلات
        prefs = UserPreference.query.filter_by(user_id=user_id).limit(2).all()
        for p in prefs:
            if p.topic and p.topic not in search_topics:
                search_topics.append(p.topic)
    except Exception as e:
        logger.error(f"[ArchiveAI] Error getting user interests: {e}")
    
    # إذا لا توجد اهتمامات, استخدم موضوعات افتراضية
    if not search_topics:
        search_topics = ["programming", "science", "literature"]
    
    # 2) البحث في Archive لكل موضوع
    per_topic = max(4, limit // len(search_topics))
    
    for topic in search_topics[:3]:
        try:
            # ترجمة إذا كان عربياً
            search_term = topic
            if any("\u0600" <= c <= "\u06FF" for c in topic):
                translated = translate_to_english_with_gemini(topic)
                if translated and translated.strip():
                    search_term = translated
                    logger.info(f"[ArchiveAI] Translated '{topic}' to '{search_term}'")
            
            # البحث في Archive
            ia_results = fetch_archive_books(search_term, limit=per_topic)
            
            for b in ia_results or []:
                bid = b.get("id")
                if not bid or bid in seen_ids:
                    continue
                seen_ids.add(bid)
                
                books.append({
                    "id": bid,
                    "title": b.get("title"),
                    "author": b.get("author"),
                    "cover": b.get("cover"),
                    "source": "Internet Archive",
                    "reason": f"🤖 AI وجد هذا من اهتماماتك: «{topic}»",
                })
                
                if len(books) >= limit:
                    break
        except Exception as e:
            logger.error(f"[ArchiveAI] Error for topic '{topic}': {e}")
        
        if len(books) >= limit:
            break
    
    logger.info(f"[ArchiveAI] Returning {len(books)} books for user {user_id}")
    return books


@cache.memoize(timeout=300)  # Cache لمدة 5 دقائق (محسّن للأداء)
def get_homepage_sections(user_id, recent_query=None):
    """
    ترجع قائمة أقسام لصفحة /explore مع توصيات متنوعة.
    """
    from .utils import get_ai_personalized_recommendations
    
    sections = []

    # 🤖 NEW: قسم التوصيات الذكية بالـ AI (الأولوية القصوى)
    try:
        ai_recs = get_ai_personalized_recommendations(user_id, limit=12)
        if ai_recs.get("success") and ai_recs.get("books"):
            ai_analysis = ai_recs.get("ai_analysis", "")
            subtitle = ai_analysis if ai_analysis else "توصيات مخصصة بناءً على سلوكك وتفضيلاتك"
            sections.append({
                "title": "🤖 مخصص لك بالذكاء الاصطناعي",
                "subtitle": subtitle,
                "books": ai_recs["books"],
                "style": "gradient",  # نمط مميز
                "icon": "robot",
                "query": "special:ai-personalized",
                "ai_topics": ai_recs.get("suggested_topics", [])
            })
    except Exception as e:
        logger.error(f"[Homepage] AI recommendations error: {e}")

    # 💎 Discovery Picks (Surprise Me)
    try:
        discovery = get_discovery_picks(limit=12)
        if discovery:
            sections.append({
                "title": "✨ اكتشافات اليوم",
                "subtitle": "عناوين متنوعة اخترناها لك لتجربة قراءة مختلفة",
                "books": discovery,
                "style": "info",
                "icon": "compass",
                "query": "special:discovery"
            })
    except Exception as e:
        logger.error(f"[Homepage] Discovery error: {e}")

    # 0) قسم "لأنك بحثت عن..." (جديد - الأولوية القصوى)
    last_query_text, last_search_books = get_last_search_recommendations(user_id, limit=20)
    if last_search_books:
        sections.append({
            "title": f"🔍 لأنك بحثت عن «{last_query_text}»",
            "subtitle": "نتائج خاصة بآخر اهتماماتك البحثية",
            "books": last_search_books,
            "style": "danger",
            "icon": "magnifying-glass",
            "query": last_query_text  # استخدام نص البحث مباشرة
        })

    # A) مختارات لك – CF
    cf_raw = get_cf_similar(user_id, top_n=40)
    if cf_raw:
        sections.append({
            "title": "✨ مختارات لك",
            "subtitle": "باستخدام التوصية التعاونية (مستخدمون يشبهونك في الذوق)",
            "books": cf_raw[:20],
            "style": "primary",
            "icon": "sparkle",
            "query": "special:cf"
        })

    # B) لأنك قرأت – Content-Based
    content_raw = get_content_similar(user_id, top_n=40)
    if content_raw:
        sections.append({
            "title": "📖 لأنك قرأت كتباً معينة",
            "subtitle": "كتب مشابهة في المحتوى والموضوع",
            "books": content_raw[:20],
            "style": "success",
            "icon": "book-open",
            "query": "special:content"
        })

    # C) من اهتماماتك – Topic-based
    topics_result = get_topic_based(user_id, limit=60, recent_query=recent_query)
    # 🔧 FIX: get_topic_based الآن ترجع قاموساً يحتوي على 'books'
    if isinstance(topics_result, dict):
        topics_raw = topics_result.get('books', [])
    else:
        topics_raw = topics_result if topics_result else []
    
    if topics_raw:
        sections.append({
            "title": "🎯 من اهتماماتك العامة",
            "subtitle": "بناءً على سجل اهتماماتك الطويل (القديم والجديد)",
            "books": topics_raw,
            "style": "info",
            "icon": "target",
            "query": "special:interests"
        })

    # D) Trending – الرائج الآن
    community_trend = get_trending(limit=24)
    if community_trend:
        sections.append({
            "title": "🔥 الرائج في مجتمع القرّاء",
            "subtitle": "كتب يقرأها ويضيفها أصدقاؤك في المنصة",
            "books": community_trend,
            "style": "warning",
            "icon": "fire",
            "query": "special:trending"
        })

    # ═══════════════════════════════════════════════════════════════════════════
    # 🆕 NEW: إضافة جميع الخوارزميات المفقودة
    # ═══════════════════════════════════════════════════════════════════════════

    # E) 💎 Hidden Gems - الجواهر المخفية
    try:
        hidden_gems = get_hidden_gems(limit=12)
        if hidden_gems:
            sections.append({
                "title": "💎 جواهر مخفية",
                "subtitle": "كتب رائعة لم تحظَ بالشهرة التي تستحقها بعد",
                "books": hidden_gems,
                "style": "gold",
                "icon": "diamond",
                "query": "special:hidden-gems"
            })
    except Exception as e:
        logger.error(f"[Homepage] Hidden Gems error: {e}")

    # F) 🧭 Genre Explorer - استكشف تصنيفاً جديداً
    try:
        genre_explorer = get_genre_explorer(user_id, limit=12)
        if genre_explorer:
            sections.append({
                "title": "🧭 استكشف تصنيفاً جديداً",
                "subtitle": "وسّع آفاقك مع تصنيفات لم تجربها من قبل",
                "books": genre_explorer,
                "style": "accent",
                "icon": "compass",
                "query": "special:genre-explorer"
            })
    except Exception as e:
        logger.error(f"[Homepage] Genre Explorer error: {e}")

    # G) 📚 Because You Read - لأنك قرأت كتاباً معيناً
    try:
        because_result = get_because_you_read(user_id, limit=12)
        if because_result and because_result.get('recommendations'):
            source_book = because_result.get('source_book', {})
            source_title = source_book.get('title', 'كتاب')
            sections.append({
                "title": f"📚 لأنك قرأت «{source_title[:30]}»",
                "subtitle": "كتب مشابهة لما أحببته مؤخراً",
                "books": because_result['recommendations'],
                "style": "success",
                "icon": "heart",
                "query": "special:because-you-read"
            })
    except Exception as e:
        logger.error(f"[Homepage] Because You Read error: {e}")

    # H) 👥 Similar Users Favorites - مفضلات قراء مشابهين
    try:
        similar_users = get_similar_users_favorites(user_id, limit=12)
        if similar_users:
            sections.append({
                "title": "👥 مفضلات قراء مشابهين",
                "subtitle": "كتب يحبها مستخدمون لديهم ذوق مشابه لذوقك",
                "books": similar_users,
                "style": "primary",
                "icon": "users-three",
                "query": "special:similar-users"
            })
    except Exception as e:
        logger.error(f"[Homepage] Similar Users error: {e}")

    # I) 📈 Trending by Period - رائج هذا الأسبوع
    try:
        weekly_trending = get_trending_by_period('week', limit=12)
        if weekly_trending:
            sections.append({
                "title": "📈 رائج هذا الأسبوع",
                "subtitle": "أكثر الكتب شعبية في الأيام السبعة الماضية",
                "books": weekly_trending,
                "style": "danger",
                "icon": "trend-up",
                "query": "special:weekly-trending"
            })
    except Exception as e:
        logger.error(f"[Homepage] Weekly Trending error: {e}")

    # J) ⭐ Top Rated - الأعلى تقييماً
    try:
        top_rated = get_top_rated(limit=12)
        if top_rated:
            sections.append({
                "title": "⭐ الأعلى تقييماً",
                "subtitle": "أفضل الكتب حسب تقييمات المجتمع",
                "books": top_rated,
                "style": "gold",
                "icon": "star",
                "query": "special:top-rated"
            })
    except Exception as e:
        logger.error(f"[Homepage] Top Rated error: {e}")

    # K) 🌐 Archive AI - من أرشيف الإنترنت
    try:
        archive_recs = get_archive_ai_recommendations(user_id, limit=12)
        if archive_recs:
            sections.append({
                "title": "🌐 كنوز من أرشيف الإنترنت",
                "subtitle": "كتب نادرة ومجانية من Internet Archive",
                "books": archive_recs,
                "style": "info",
                "icon": "globe",
                "query": "special:archive"
            })
    except Exception as e:
        logger.error(f"[Homepage] Archive AI error: {e}")

    # L) 🆕 Cold Start - للمستخدمين الجدد بدون سجل
    if len(sections) < 2:
        # إذا لم نجد توصيات كافية, نعرض كتب من موضوعات متنوعة
        try:
            default_topics = ["programming", "science fiction", "history", "psychology"]
            cold_start_books = []
            
            for topic in default_topics[:2]:
                topic_result = fetch_google_books(topic, max_results=8)
                items = topic_result[0] if isinstance(topic_result, tuple) else topic_result
                
                for it in items or []:
                    if not isinstance(it, dict): continue
                    gid = it.get("id")
                    if not gid: continue
                    
                    vi = it.get("volumeInfo") or {}
                    img = (vi.get("imageLinks") or {}).get("thumbnail")
                    if img:
                        if img.startswith("http://"): img = img.replace("http://", "https://")
                    
                    cold_start_books.append({
                        "id": gid,
                        "title": vi.get("title"),
                        "author": ", ".join(vi.get("authors") or []),
                        "cover": img,
                        "source": "Google Books",
                        "reason": f"🌟 موصى به في {topic}",
                        "rating": vi.get("averageRating"),
                    })
            
            if cold_start_books:
                sections.insert(0, {
                    "title": "🌟 اكتشف كتباً رائعة",
                    "subtitle": "ابدأ رحلتك في القراءة مع هذه الاقتراحات",
                    "books": cold_start_books[:16],
                    "style": "gradient",
                    "icon": "compass",
                    "query": "special:discover"
                })
        except Exception as e:
            logger.error(f"[Homepage] Cold start error: {e}")

    return sections


def get_all_libraries_showcase(query="books", limit_per_source=6):
    """
    جلب كتب من جميع المصادر الخمسة لعرضها معاً.
    
    Args:
        query: كلمة البحث (افتراضي: books)
        limit_per_source: عدد الكتب من كل مصدر
        
    Returns:
        قائمة من أقسام, كل قسم يمثل مصدر مختلف
    """
    sections = []
    
    # ترجمة الاستعلام للإنجليزية إذا كان عربياً
    search_query = query
    if any("\u0600" <= c <= "\u06FF" for c in query):
        try:
            translated = translate_to_english_with_gemini(query)
            if translated and translated.strip():
                search_query = translated
        except:
            pass
    
    # 1. Google Books
    try:
        gb_res = fetch_google_books(search_query, max_results=limit_per_source)
        items = gb_res[0] if isinstance(gb_res, tuple) else gb_res
        if items:
            google_books = []
            for it in items or []:
                if not isinstance(it, dict):
                    continue
                gid = it.get("id")
                if not gid:
                    continue
                vi = it.get("volumeInfo") or {}
                img = (vi.get("imageLinks") or {}).get("thumbnail")
                if img and img.startswith("http://"):
                    img = img.replace("http://", "https://")
                google_books.append({
                    "id": gid,
                    "title": vi.get("title"),
                    "author": ", ".join(vi.get("authors") or []),
                    "cover": img,
                    "source": "Google Books",
                    "rating": vi.get("averageRating"),
                    "ratings_count": vi.get("ratingsCount"),
                })
            if google_books:
                sections.append({
                    "title": "🔵 Google Books",
                    "subtitle": "أكبر مكتبة رقمية في العالم",
                    "books": google_books,
                    "style": "google",
                    "icon": "google-logo",
                })
    except Exception as e:
        logger.error(f"[AllLibs] Google error: {e}")
    
    # 2. Internet Archive
    try:
        ia_books = fetch_archive_books(search_query, limit=limit_per_source)
        if ia_books:
            sections.append({
                "title": "🟡 Internet Archive",
                "subtitle": "ملايين الكتب المجانية",
                "books": ia_books,
                "style": "archive",
                "icon": "archive",
            })
    except Exception as e:
        logger.error(f"[AllLibs] Archive error: {e}")
    
    # 3. Project Gutenberg
    try:
        gut_books = fetch_gutenberg_books(search_query, limit=limit_per_source)
        if gut_books:
            sections.append({
                "title": "🟢 Project Gutenberg",
                "subtitle": "كلاسيكيات الأدب العالمي",
                "books": gut_books,
                "style": "gutenberg",
                "icon": "book-open-text",
            })
    except Exception as e:
        logger.error(f"[AllLibs] Gutenberg error: {e}")
    
    # 4. OpenLibrary
    try:
        ol_books = fetch_openlib_books(search_query, limit=limit_per_source)
        if ol_books:
            sections.append({
                "title": "🔴 OpenLibrary",
                "subtitle": "مكتبة مفتوحة المصدر",
                "books": ol_books,
                "style": "openlib",
                "icon": "books",
            })
    except Exception as e:
        logger.error(f"[AllLibs] OpenLib error: {e}")
    
    # 5. IT Bookstore
    try:
        it_books = fetch_itbook_books(search_query, limit=limit_per_source)
        if it_books:
            sections.append({
                "title": "💙 IT Bookstore",
                "subtitle": "كتب البرمجة والتقنية",
                "books": it_books,
                "style": "itbook",
                "icon": "code",
            })
    except Exception as e:
        logger.error(f"[AllLibs] ITBook error: {e}")
    
    return sections



# ------------------------------------------------------------------
# 5) Hybrid Recommendations - التوصية الهجينة الذكية
# ------------------------------------------------------------------

def get_hybrid_recommendations(user_id, book, limit=12):
    """
    توصيات هجينة للكتاب الحالي:
    1. تحاول Collaborative Filtering
    2. تحاول Content-Based (AI Embeddings)
    3. تحاول Metadata (نفس المؤلف / نفس التصنيف)
    4. Fallback إلى البحث التقليدي
    """
    if not book: return []
    
    recs = []
    seen_ids = {book.google_id} if book.google_id else {f"local_{book.id}"}
    
    # --- 1. Collaborative Filtering (Item-based) ---
    try:
        if book.google_id:
            fans = UserRatingCF.query.filter(
                UserRatingCF.google_id == book.google_id, 
                UserRatingCF.rating >= 4
            ).limit(20).all()
            
            fan_ids = [f.user_id for f in fans if f.user_id != user_id]
            if fan_ids:
                suggested_ratings = UserRatingCF.query.filter(
                    UserRatingCF.user_id.in_(fan_ids),
                    UserRatingCF.rating >= 4,
                    UserRatingCF.google_id != book.google_id
                ).limit(limit * 2).all()
                
                from collections import Counter
                gids = [r.google_id for r in suggested_ratings]
                common_gids = [gid for gid, count in Counter(gids).most_common(limit)]
                
                for gid in common_gids:
                    if gid in seen_ids: continue
                    b = Book.query.filter_by(google_id=gid).first()
                    if b:
                        recs.append(_book_to_dict(b, source="Community", reason="👥 أحبه قراء آخرون لهم نفس ذوقك"))
                        seen_ids.add(gid)
    except Exception as e:
        logger.error(f"[Hybrid] CF error: {e}")

    # --- 2. More by Same Author (High Priority for Hybrid) ---
    if len(recs) < limit and book.author and book.author not in ['Unknown', 'غير معروف']:
        try:
            author_recs = get_author_books(book.author, exclude_book_id=book.google_id, limit=limit//2)
            for r in author_recs:
                if r['id'] not in seen_ids:
                    r['reason'] = f"✍️ للمؤلف {book.author}"
                    recs.append(r)
                    seen_ids.add(r['id'])
        except Exception as e:
            logger.error(f"[Hybrid] Author fallback error: {e}")

    # --- 3. Content-Based (AI Embeddings) ---
    if len(recs) < limit:
        try:
            current_embedding = None
            if hasattr(book, 'id') and book.id:
                emb_entry = BookEmbedding.query.filter_by(book_id=book.id).first()
                if emb_entry and emb_entry.vector:
                    current_embedding = np.array(emb_entry.vector, dtype=np.float32).reshape(1, -1)
            
            if current_embedding is not None:
                all_embeds = BookEmbedding.query.all()
                vectors = []
                b_ids = []
                for row in all_embeds:
                    if hasattr(book, 'id') and row.book_id == book.id: continue
                    if row.vector:
                        vectors.append(np.array(row.vector, dtype=np.float32))
                        b_ids.append(row.book_id)
                
                if vectors:
                    mat = np.vstack(vectors)
                    sims = cosine_similarity(current_embedding, mat)[0]
                    indices = np.argsort(sims)[::-1][:limit]
                    
                    for idx in indices:
                        score = sims[idx]
                        if score < 0.6: continue
                        target_book = Book.query.get(b_ids[idx])
                        if not target_book: continue
                        bid = target_book.google_id or f"local_{target_book.id}"
                        if bid in seen_ids: continue
                        recs.append(_book_to_dict(target_book, source="AI Similarity", reason=f"🤖 محتوى مشابه ({score:.0%})"))
                        seen_ids.add(bid)
                        if len(recs) >= limit: break
        except Exception as e:
            logger.error(f"[Hybrid] Content-based error: {e}")

    # --- 4. Search Fallback (Keyword based) ---
    if len(recs) < limit:
        try:
            query = book.title
            gb_res = fetch_google_books(query, max_results=limit)
            items = gb_res[0] if isinstance(gb_res, tuple) else gb_res
            for it in items or []:
                gid = it.get("id")
                if not gid or gid in seen_ids: continue
                vi = it.get("volumeInfo") or {}
                if gid == book.google_id or vi.get("title") == book.title: continue
                
                img = (vi.get("imageLinks") or {}).get("thumbnail")
                if img:
                    if img.startswith("http://"): img = img.replace("http://", "https://")
                    if '&edge=curl' in img: img = img.replace('&edge=curl', '').replace('&edge=curl&', '&')

                recs.append({
                    "id": gid,
                    "title": vi.get("title"),
                    "author": ", ".join(vi.get("authors") or []),
                    "cover": img,
                    "source": "Google Books",
                    "reason": "📚 كتب ذات صلة",
                    "rating": vi.get("averageRating"),
                })
                seen_ids.add(gid)
                if len(recs) >= limit: break
        except Exception as e:
            logger.error(f"[Hybrid] Metadata fallback error: {e}")

    return recs[:limit]


def get_author_books(author_name, exclude_book_id=None, limit=8):
    """
    جلب كتب أخرى لنفس المؤلف.
    """
    if not author_name or author_name.lower() in ['unknown', 'غير معروف']:
        return []

    books_dicts = []
    seen_ids = set()
    if exclude_book_id:
        seen_ids.add(exclude_book_id)

    # 1. بحث محلي (Local DB)
    try:
        local_books = Book.query.filter(
            Book.author.ilike(f"%{author_name}%"),
            Book.google_id != exclude_book_id # التقريب
        ).limit(5).all()
        
        for b in local_books:
            bid = b.google_id or f"local_{b.id}"
            if bid in seen_ids: continue
            
            books_dicts.append(_book_to_dict(b, source="Local", reason=f"✍️ للمؤلف {author_name}"))
            seen_ids.add(bid)
    except Exception as e:
        logger.error(f"[AuthorBooks] Local search error: {e}")

    # 2. بحث Google Books API
    # نستخدم inauthor: operator
    try:
        query = f"inauthor:\"{author_name}\""
        gb_res = fetch_google_books(query, max_results=limit)
        items = gb_res[0] if isinstance(gb_res, tuple) else gb_res
        
        for it in items or []:
            if not isinstance(it, dict): continue
            gid = it.get("id")
            if not gid or gid in seen_ids: continue
            
            vi = it.get("volumeInfo") or {}
            
            # تأكد من تطابق اسم المؤلف تقريباً لضمان الدقة
            authors = vi.get("authors", [])
            if not any(author_name.lower() in a.lower() for a in authors):
                continue

            img = (vi.get("imageLinks") or {}).get("thumbnail")
            if img:
                if img.startswith("http://"): img = img.replace("http://", "https://")
                if '&edge=curl' in img: img = img.replace('&edge=curl', '').replace('&edge=curl&', '&')

            books_dicts.append({
                "id": gid,
                "title": vi.get("title"),
                "author": ", ".join(authors),
                "cover": img,
                "source": "Google Books",
                "reason": f"✍️ للمؤلف {author_name}",
                "rating": vi.get("averageRating"),
            })
            seen_ids.add(gid)
            if len(books_dicts) >= limit: break
            
    except Exception as e:
        logger.error(f"[AuthorBooks] API error: {e}")

    return books_dicts[:limit]


# ------------------------------------------------------------------
# Top Rated    ا أع 0  ت ``& ا9 
# ------------------------------------------------------------------

@cache.memoize(timeout=60)  # Cache for 1 minute
def get_top_rated(limit=10):
    """
    Get top rated books based on user reviews (BookReview).
    Returns a list of dicts.
    """
    try:
        # 1. Aggregate ratings: Average Rating & Count
        # Filter for books with at least 1 review
        # Order by Average DESC, then Count DESC
        results = (
            db.session.query(
                BookReview.google_id,
                func.avg(BookReview.rating).label('avg_rating'),
                func.count(BookReview.id).label('review_count')
            )
            .group_by(BookReview.google_id)
            .having(func.count(BookReview.id) >= 1) # At least 1 review
            .order_by(func.avg(BookReview.rating).desc(), func.count(BookReview.id).desc())
            .limit(limit)
            .all()
        )
        
        books_dicts = []
        for row in results:
            gid = row.google_id
            avg = float(row.avg_rating)
            count = int(row.review_count)
            
            # 2. Get Book Details
            # Try local DB first
            book = Book.query.filter_by(google_id=gid).first()
            if book:
                d = _book_to_dict(book, source="Community", reason=f"⭐ {avg:.1f} ({count})")
                d['rating'] = avg # Explicit rating for UI
                books_dicts.append(d)
            else:
                # Fallback to API/Utils if not in DB (slower but necessary)
                # We can use fetch_book_details from utils (imported)
                from .utils import fetch_book_details
                details = fetch_book_details(gid)
                if details:
                    cover = details.get("cover")
                    if cover and cover.startswith("http://"): cover = "https://" + cover[7:]
                    
                    books_dicts.append({
                        "id": gid,
                        "title": details.get("title"),
                        "author": details.get("author"),
                        "cover": cover,
                        "source": "Community",
                        "reason": f"⭐ {avg:.1f} ({count})",
                        "rating": avg
                    })
        
        return books_dicts

    except Exception as e:
        logger.error(f"[TopRated] Error: {e}", exc_info=True)
        return []


# ------------------------------------------------------------------
# Mood-Based – مزاجك اليوم
# ------------------------------------------------------------------

MOOD_MAPPING = {
    "happy": {
        "title": "سعید",
        "emoji": "😃",
        "queries": ["Comedy", "Humor", "Feel-good", "Funny"],
        "color": "var(--warning)"
    },
    "sad": {
        "title": "حزین",
        "emoji": "😔",
        "queries": ["Drama", "Tragedy", "Emotional", "Sad"],
        "color": "var(--accent-purple)"
    },
    "adventurous": {
        "title": "متحمس",
        "emoji": "🚀",
        "queries": ["Adventure", "Action", "Science Fiction", "Thriller"],
        "color": "var(--accent-cyan)"
    },
    "calm": {
        "title": "هادئ",
        "emoji": "🧘",
        "queries": ["Meditation", "Philosophy", "Nature", "Calm"],
        "color": "var(--primary)"
    },
    "curious": {
        "title": "فضولي",
        "emoji": "🧐",
        "queries": ["Science", "Mystery", "History", "Nonfiction"],
        "color": "var(--accent-magenta)"
    },
    "romantic": {
        "title": "رومانسي",
        "emoji": "❤️",
        "queries": ["Romance", "Love", "Poetry"],
        "color": "var(--accent-pink, #f472b6)"
    }
}

def get_mood_based_recommendations(mood_key, limit=12):
    """
    جلب توصيات بناءً على مزاج المستخدم.
    """
    mood_info = MOOD_MAPPING.get(mood_key)
    if not mood_info:
        logger.warning(f"[Mood] Invalid mood key: {mood_key}")
        return []

    queries = mood_info.get("queries", [])
    if not queries: queries = ["Books"]
    
    # خلط الاستعلامات لتنويع البداية
    random.shuffle(queries)
    
    # --- تخصيص التوصيات بناءً على سجل البحث (ميزة احترافية جديدة) ---
    personalization_reason = None
    if current_user.is_authenticated:
        try:
            # جلب آخر بحث للمستخدم
            last_search = SearchHistory.query.filter_by(user_id=current_user.id)\
                .order_by(SearchHistory.created_at.desc()).first()
            
            if last_search and last_search.query:
                # دمج آخر بحث مع تصنيف المزاج
                # مثال: بحث عن "space" والمزاج "happy" -> "space comedy" أو "space humor"
                mood_term = queries[0] # نأخذ أول مصطلح مزاج بعد الخلط
                personalized_query = f"{last_search.query} {mood_term}"
                
                # إضافة الاستعلام المخصص في بداية القائمة لتكون له الأولوية
                queries.insert(0, personalized_query)
                personalization_reason = f"لأنك مهتم بـ '{last_search.query}' وتشعر بـ {mood_info['title']}"
                logger.info(f"[Mood] Personalized query added: {personalized_query}")
        except Exception as e:
            logger.warning(f"[Mood] Error adding personalization: {e}")
    # ---------------------------------------------------------------

    
    all_books = []
    seen_ids = set()
    
    # محاولة البحث باستخدام الاستعلامات المتاحة حتى نجد نتائج
    for query in queries:
        try:
            # البحث في Google Books
            gb_res = fetch_google_books(query, max_results=limit)
            items = gb_res[0] if isinstance(gb_res, tuple) else gb_res
            
            if not items:
                continue  # لم نجد نتائج لهذا الاستعلام, نجرب التالي
            
            # معالجة النتائج
            for it in items:
                if not isinstance(it, dict): continue
                gid = it.get("id")
                if not gid or gid in seen_ids: continue
                seen_ids.add(gid)
                
                vi = it.get("volumeInfo") or {}
                title = vi.get("title")
                if not title: continue
                
                img = (vi.get("imageLinks") or {}).get("thumbnail")
                if img:
                    if img.startswith("http://"): img = img.replace("http://", "https://")
                    if '&edge=curl' in img: img = img.replace('&edge=curl', '').replace('&edge=curl&', '&')
                
                
                # تحديد سبب التوصية
                reason_text = f"{mood_info['emoji']} لأنك تشعر بـ {mood_info['title']}"
                
                # إذا كان هذا الكتاب ناتجاً عن الاستعلام المخصص (أول واحد في القائمة)
                if personalization_reason and query == queries[0]:
                    reason_text = f"✨ {personalization_reason}"
                
                all_books.append({
                    "id": gid,
                    "title": title,
                    "author": ", ".join(vi.get("authors") or []),
                    "cover": img,
                    "source": "Mood API",
                    "reason": reason_text,
                    "rating": vi.get("averageRating"),
                    "ratings_count": vi.get("ratingsCount"),
                })
            
            # إذا وجدنا كتباً كافية, نتوقف عن البحث
            if all_books:
                break
                
        except Exception as e:
            logger.warning(f"[Mood] Error with query '{query}': {e}")
            continue

    return all_books[:limit]


def get_recommendations_by_title(title, limit=24):
    """
    جلب توصيات بناءً على عنوان كتاب مشابه.
    1. نبحث عن الكتاب ونأخذ معلوماته.
    2. نبحث عن كتب لها نفس التصنيف أو المؤلف.
    """
    if not title: return []
    
    # 1. البحث عن الكتاب المستهدف
    target_res, _ = fetch_google_books(title, max_results=1) # 👈 تم التصحيح هنا لفك التوبل
    if not target_res:
        return []
        
    target_book = target_res[0]
    vi = target_book.get("volumeInfo", {})
    categories = vi.get("categories", [])
    authors = vi.get("authors", [])
    
    # 2. تكوين استعلام للكتب المشابهة
    queries = []
    
    # تحسين للكتب التقنية: إذا كان التصنيف بالعربي أو مفقود, نحاول استخراجه بالذكاء الاصطناعي
    if not categories or any(any('\u0600' <= c <= '\u06FF' for c in cat) for cat in categories):
        try:
            from .utils import analyze_search_intent_with_ai
            ai_info = analyze_search_intent_with_ai(vi.get("title", title))
            if ai_info and ai_info.get("query"):
                queries.append(ai_info["query"])
                logger.info(f"[Similar] AI Recommended query for technical book: {ai_info['query']}")
        except:
            pass

    # استراتيجية البحث التقليدية
    if categories:
        cat = categories[0].split("/")[0].strip()
        queries.append(f"subject:{cat}")
    
    if authors:
        queries.append(f"inauthor:{authors[0]}")
        
    if not queries:
        queries.append(title)
        
    all_books = []
    seen_ids = set()
    target_id = target_book.get("id")
    seen_ids.add(target_id)
    
    for q in queries:
        try:
            res_items, _ = fetch_google_books(q, max_results=limit) # 👈 تم التصحيح هنا لفك التوبل
            if not res_items: continue
            
            for it in res_items:
                gid = it.get("id")
                if not gid or gid in seen_ids: continue
                seen_ids.add(gid)
                
                vi_it = it.get("volumeInfo") or {}
                
                img = (vi_it.get("imageLinks") or {}).get("thumbnail")
                if img:
                    if img.startswith("http://"): img = img.replace("http://", "https://")
                    if '&edge=curl' in img: img = img.replace('&edge=curl', '').replace('&edge=curl&', '&')
                
                reason = "🔥 لأنك أحببت كتاباً مشابهاً"
                if q.startswith("subject:"):
                    reason = f"📚 من نفس التصنيف: {categories[0] if categories else 'مواضيع مشابهة'}"
                elif q.startswith("inauthor:"):
                    reason = f"✍️ لنفس المؤلف: {authors[0]}"
                elif q == queries[0] and len(queries) > 1: # إذا كان استعلام AI
                     reason = "🤖 مقترح ذكي لمجال الكتاب"
                    
                all_books.append({
                    "id": gid,
                    "title": vi_it.get("title"),
                    "author": ", ".join(vi_it.get("authors") or []),
                    "cover": img,
                    "source": "Similar API",
                    "reason": reason,
                    "rating": vi_it.get("averageRating"),
                    "ratings_count": vi_it.get("ratingsCount"),
                })
                
        except Exception as e:
            logger.error(f"[Similar] Error fetching similar books for {q}: {e}")
            
    random.shuffle(all_books)
    return all_books[:limit]


# ------------------------------------------------------------------
# 5) Hybrid AI Behavioral Analysis
# ------------------------------------------------------------------

def log_user_view(user_id, book):
    """
    تسجيل مشاهدة المستخدم للكتاب.
    يتم استدعاؤها عند فتح صفحة التفاصيل.
    """
    try:
        if not user_id: return
        
        # استخراج المعرفات
        b_id = getattr(book, 'id', None)
        g_id = getattr(book, 'google_id', None)
        
        # إذا كان الكتاب محلياً فقط, g_id قد يكون None
        # إذا كان من Google, قد يكون له id محلي أيضاً إذا تم حفظه
        
        # محاولة العثور على سجل سابق
        criteria = {'user_id': user_id}
        if g_id:
            criteria['google_id'] = g_id
        elif b_id:
            criteria['book_id'] = b_id
        else:
            return # لا يوجد معرف

        # البحث بمرونة
        view = None
        if g_id:
            view = UserBookView.query.filter_by(user_id=user_id, google_id=g_id).first()
        if not view and b_id:
            view = UserBookView.query.filter_by(user_id=user_id, book_id=b_id).first()
            
        if view:
            view.view_count += 1
            view.last_viewed_at = datetime.utcnow()
        else:
            view = UserBookView(
                user_id=user_id,
                book_id=b_id if hasattr(book, 'id') and isinstance(book.id, int) else None,
                google_id=g_id,
                view_count=1
            )
            db.session.add(view)
            
        db.session.commit()
    except Exception as e:
        logger.error(f"[LogView] Error: {e}")

def analyze_user_profile_with_ai(user_id):
    """
    تحليل سلوك المستخدم باستخدام Generative AI (Gemini).
    يقرأ: المشاهدات, التقييمات, المفضلة, البحث.
    يكتب: تحديث UserPreference.
    """
    import os
    import json
    import requests
    from datetime import timedelta
    
    # 1. جمع البيانات
    try:
        # أ. المشاهدات الأخيرة (آخر 20)
        views = UserBookView.query.filter_by(user_id=user_id).order_by(UserBookView.last_viewed_at.desc()).limit(15).all()
        viewed_books = []
        for v in views:
            # نحاول نجيب العنوان
            title = "Unknown"
            if v.book: title = v.book.title
            elif v.google_id:
                 b = Book.query.filter_by(google_id=v.google_id).first()
                 if b: title = b.title
                 # إذا لم يكن في قاعدة بياناتنا, يمكننا تجاهل الاسم أو جلبه لاحقاً, لكن للسرعة سنكتفي بالمتاح
            
            if title != "Unknown":
                viewed_books.append(title)
        
        # ب. التقييمات العالية
        ratings = UserRatingCF.query.filter_by(user_id=user_id).filter(UserRatingCF.rating >= 4).limit(10).all()
        rated_books = [] # نحتاج عناوين
        # اختصاراً, سنعتمد على المشاهدات والبحث لأنها الأغنى حالياً

        # ج. سجل البحث
        searches = SearchHistory.query.filter_by(user_id=user_id).order_by(SearchHistory.created_at.desc()).limit(10).all()
        search_terms = [s.query for s in searches if s.query]

        if not viewed_books and not search_terms:
            return # لا توجد بيانات كافية

        # 2. Prompt Construction
        prompt = f"""
        Analyze this users reading behavior and suggest interests.
        
        Viewed Books: {", ".join(viewed_books)}
        Search Terms: {", ".join(search_terms)}
        
        Task:
        1. Identify 5 core topics/genres this user is interested in.
        2. Format as JSON list of objects: {{"topic": "topic_name", "weight": float_1_to_3, "reason_en": "reason", "reason_ar": "reason_in_arabic"}}
        3. Topics should be broad enough for book search (e.g. "Science Fiction", "Python Programming").
        """

        gemini_key = os.environ.get("GEMINI_API_KEY")
        if not gemini_key: return

        response = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"response_mime_type": "application/json"}
            },
            timeout=10
        )
        
        if response.ok:
            data = response.json()
            text_resp = data['candidates'][0]['content']['parts'][0]['text']
            suggestions = json.loads(text_resp)
            
            # 3. تحديث التفضيلات
            # نحذف التفضيلات القديمة التي تم استنتاجها آلياً (يمكننا تمييزها بوزن معين أو إضافة حقل source مستقبلاً)
            # حالياً سنقوم بالتحديث/الإضافة
            
            for item in suggestions:
                topic = item.get("topic")
                weight = item.get("weight", 1.0)
                
                if not topic: continue
                
                # البحث عن تفضيل موجود
                pref = UserPreference.query.filter_by(user_id=user_id, topic=topic).first()
                if pref:
                    # تحديث الوزن (Max 5.0)
                    pref.weight = min(5.0, (pref.weight + weight) / 2 + 1) # معادلة بسيطة
                else:
                    new_pref = UserPreference(user_id=user_id, topic=topic, weight=weight)
                    db.session.add(new_pref)
            
            db.session.commit()
            logger.info(f"[AI Analysis] Updated preferences for user {user_id}")

    except Exception as e:
        logger.error(f"[AI Analysis] Error: {e}")
def get_discovery_picks(limit=10):
    """
    مختارات عشوائية متنوعة تظهر للمستخدم لإثراء تجربته.
    """
    from .utils import fetch_google_books
    discovery_topics = ["Philosophy of Life", "Future History", "Minimalism", "Classic Adventures", "Scientific Mysteries"]
    topic = random.choice(discovery_topics)
    try:
        gb_res = fetch_google_books(topic, max_results=limit)
        items = gb_res[0] if isinstance(gb_res, tuple) else gb_res
        books = []
        for it in items or []:
            vi = it.get("volumeInfo", {})
            img = (vi.get("imageLinks") or {}).get("thumbnail")
            if img:
                if img.startswith("http://"): img = img.replace("http://", "https://")
                if '&edge=curl' in img: img = img.replace('&edge=curl', '').replace('&edge=curl&', '&')
            
            books.append({
                "id": it.get("id"),
                "title": vi.get("title"),
                "author": ", ".join(vi.get("authors", [])),
                "cover": img,
                "source": "Discovery",
                "reason": f"✨ اكتشاف جديد: في مجال {topic}",
                "rating": vi.get("averageRating")
            })
        return books
    except:
        return []

def rerank_search_results(user_id, books):
    """
    إعادة ترتيب نتائج البحث بناءً على اهتمامات المستخدم.
    """
    if not user_id or not books: return books
    
    try:
        from .models import UserPreference
        prefs = UserPreference.query.filter_by(user_id=user_id).all()
        if not prefs: return books
        
        pref_map = {p.topic.lower(): p.weight for p in prefs}
        
        def calculate_score(book):
            score = 0.0
            title = (book.get("title") or "").lower()
            author = (book.get("author") or "").lower()
            
            for topic, weight in pref_map.items():
                if topic in title: score += weight * 1.5
                if topic in author: score += weight
            
            # احتفظ بالترتيب الأصلي كعامل ثانوي
            return score
            
        # Re-sort books based on score
        # Note: We use stable sort (sort books by score preserved original order for equal scores)
        sorted_books = sorted(books, key=calculate_score, reverse=True)
        return sorted_books
    except Exception as e:
        logger.error(f"[Reranking] Error: {e}")
        return books


# ------------------------------------------------------------------
# NEW: Trending by Time Period
# ------------------------------------------------------------------
@cache.memoize(timeout=300)
def get_trending_by_period(period='week', limit=12):
    """
    جلب الكتب الرائجة بناءً على فترة زمنية محددة.
    
    Args:
        period: 'day', 'week', 'month', 'all'
        limit: عدد النتائج
    """
    from datetime import datetime, timedelta
    from .models import BookStatus, UserBookView
    
    try:
        # تحديد الفترة الزمنية
        now = datetime.utcnow()
        if period == 'day':
            start_date = now - timedelta(days=1)
            period_label = "اليوم"
        elif period == 'week':
            start_date = now - timedelta(weeks=1)
            period_label = "هذا الأسبوع"
        elif period == 'month':
            start_date = now - timedelta(days=30)
            period_label = "هذا الشهر"
        else:
            start_date = None
            period_label = "كل الأوقات"
        
        # جمع الكتب من BookStatus (favorites, finished)
        query = db.session.query(
            BookStatus.book_id,
            func.count(BookStatus.id).label('count')
        ).filter(
            BookStatus.status.in_(['favorite', 'finished'])
        )
        
        if start_date:
            query = query.filter(BookStatus.created_at >= start_date)
        
        popular_books = query.group_by(BookStatus.book_id).order_by(
            func.count(BookStatus.id).desc()
        ).limit(limit * 2).all()
        
        books = []
        seen_ids = set()
        
        for book_id, count in popular_books:
            if len(books) >= limit:
                break
            book = Book.query.get(book_id)
            if book and book.google_id not in seen_ids:
                seen_ids.add(book.google_id)
                books.append(_book_to_dict(
                    book, 
                    source="Trending",
                    reason=f"🔥 رائج {period_label} ({count} قارئ)"
                ))
        
        # إضافة من UserBookView إذا لم نحصل على كفاية
        if len(books) < limit:
            view_query = db.session.query(
                UserBookView.book_id,
                func.sum(UserBookView.view_count).label('views')
            )
            
            if start_date:
                view_query = view_query.filter(UserBookView.last_viewed_at >= start_date)
            
            popular_views = view_query.group_by(UserBookView.book_id).order_by(
                func.sum(UserBookView.view_count).desc()
            ).limit(limit).all()
            
            for book_id, views in popular_views:
                if len(books) >= limit:
                    break
                book = Book.query.get(book_id)
                if book and book.google_id not in seen_ids:
                    seen_ids.add(book.google_id)
                    books.append(_book_to_dict(
                        book,
                        source="Trending",
                        reason=f"👀 الأكثر مشاهدة {period_label}"
                    ))
        
        logger.info(f"[Trending] Found {len(books)} books for period '{period}'")
        return books
        
    except Exception as e:
        logger.error(f"[Trending by Period] Error: {e}")
        return []


# ------------------------------------------------------------------
# NEW: "Because You Read X" Personalized Recommendations
# ------------------------------------------------------------------
@cache.memoize(timeout=300)
def get_because_you_read(user_id, limit=12):
    """
    توصيات بناءً على كتاب قرأه المستخدم مؤخراً.
    
    Returns:
        dict: {
            'source_book': {...},  # الكتاب المرجع
            'recommendations': [...]  # التوصيات
        }
    """
    from .models import BookStatus
    
    if not user_id:
        return {'source_book': None, 'recommendations': []}
    
    try:
        # اختيار كتاب عشوائي من المكتبة (مفضل أو منتهي)
        user_books = BookStatus.query.filter(
            BookStatus.user_id == user_id,
            BookStatus.status.in_(['favorite', 'finished'])
        ).order_by(func.random()).limit(5).all()
        
        if not user_books:
            return {'source_book': None, 'recommendations': []}
        
        # اختيار واحد عشوائياً
        status_entry = random.choice(user_books)
        source_book = Book.query.get(status_entry.book_id)
        
        if not source_book:
            return {'source_book': None, 'recommendations': []}
        
        # جلب توصيات مشابهة
        recs = get_hybrid_recommendations(user_id, source_book, limit=limit)
        
        # تحديث السبب ليذكر الكتاب المرجع
        for rec in recs:
            rec['reason'] = f"📖 لأنك قرأت: {source_book.title[:30]}..."
        
        source_dict = _book_to_dict(source_book, source="Reference")
        
        logger.info(f"[BecauseYouRead] Generated {len(recs)} recs based on '{source_book.title}'")
        return {
            'source_book': source_dict,
            'recommendations': recs
        }
        
    except Exception as e:
        logger.error(f"[BecauseYouRead] Error: {e}")
        return {'source_book': None, 'recommendations': []}


# ------------------------------------------------------------------
# NEW: Similar Users' Favorites
# ------------------------------------------------------------------
@cache.memoize(timeout=600)
def get_similar_users_favorites(user_id, limit=12):
    """
    جلب الكتب المفضلة لدى مستخدمين لهم ذوق مشابه.
    """
    from .models import BookStatus
    
    if not user_id:
        return []
    
    try:
        # 1. جلب كتب المستخدم الحالي (favorites)
        user_favorites = BookStatus.query.filter(
            BookStatus.user_id == user_id,
            BookStatus.status == 'favorite'
        ).all()
        
        user_book_ids = {s.book_id for s in user_favorites}
        
        if not user_book_ids:
            return []
        
        # 2. إيجاد مستخدمين آخرين لديهم نفس الكتب المفضلة
        similar_users = db.session.query(
            BookStatus.user_id,
            func.count(BookStatus.id).label('overlap')
        ).filter(
            BookStatus.book_id.in_(user_book_ids),
            BookStatus.status == 'favorite',
            BookStatus.user_id != user_id
        ).group_by(BookStatus.user_id).order_by(
            func.count(BookStatus.id).desc()
        ).limit(10).all()
        
        if not similar_users:
            return []
        
        similar_user_ids = [u[0] for u in similar_users]
        
        # 3. جلب الكتب المفضلة لدى هؤلاء المستخدمين (التي لا يملكها المستخدم الحالي)
        their_favorites = BookStatus.query.filter(
            BookStatus.user_id.in_(similar_user_ids),
            BookStatus.status == 'favorite',
            ~BookStatus.book_id.in_(user_book_ids)
        ).all()
        
        # عدّ التكرارات
        from collections import Counter
        book_counts = Counter(s.book_id for s in their_favorites)
        top_book_ids = [bid for bid, _ in book_counts.most_common(limit)]
        
        books = []
        for book_id in top_book_ids:
            book = Book.query.get(book_id)
            if book:
                count = book_counts[book_id]
                books.append(_book_to_dict(
                    book,
                    source="Similar Users",
                    reason=f"❤️ أحبه {count} قارئ يشبهونك في الذوق"
                ))
        
        logger.info(f"[SimilarUsers] Found {len(books)} favorites from similar users")
        return books
        
    except Exception as e:
        logger.error(f"[SimilarUsers] Error: {e}")
        return []


# ------------------------------------------------------------------
# NEW (Phase 2): Hidden Gems
# ------------------------------------------------------------------
@cache.memoize(timeout=300)
def get_hidden_gems(limit=12):
    """
    جلب الكتب التي لها تقييم عالٍ (>= 4.0) ولكن عدد مشاهدات منخفض.
    """
    from .models import UserRatingCF, UserBookView
    
    try:
        # 1. تجميع التقييمات المحلية
        high_rated_subquery = db.session.query(
            UserRatingCF.google_id,
            func.avg(UserRatingCF.rating).label('avg_rating'),
            func.count(UserRatingCF.id).label('rating_count')
        ).group_by(UserRatingCF.google_id).having(func.avg(UserRatingCF.rating) >= 4.0).subquery()
        
        # 2. ربط مع المشاهدات
        # نريد كتباً بتقييم عالٍ ولكن مشاهدات قليلة (أقل من 50 مشاهدة مثلاً) أو معدومة
        
        # سنجلب الكتب المرشحة أولاً
        candidates = db.session.query(
            high_rated_subquery.c.google_id,
            high_rated_subquery.c.avg_rating
        ).all()
        
        results = []
        for gid, rating in candidates:
            if len(results) >= limit: break
            
            # التحقق من المشاهدات
            # نجمع مشاهدات هذا الكتاب لكل المستخدمين
            views_sum = db.session.query(func.sum(UserBookView.view_count))\
                .filter(UserBookView.google_id == gid).scalar() or 0
                
            if views_sum < 50: # شرط "جوهرة مخفية"
                # جلب تفاصيل الكتاب
                # نحاول إيجاده في Book أولاً (إذا تم تخزينه)
                book = Book.query.filter_by(google_id=gid).first()
                if book:
                    # تحويله
                    book_dict = _book_to_dict(
                        book, 
                        source="Hidden Gem", 
                        reason=f"💎 جوهرة مخفية (تقييم {rating:.1f}/5)"
                    )
                    results.append(book_dict)
                else:
                    # إذا لم يكن في Local DB, قد نحتاج لجلبه من API
                    # في النسخة الحالية, نكتفي بالموجود محلياً لتفادي البطء
                    pass

        logger.info(f"[Hidden Gems] Found {len(results)} books")
        return results
        
    except Exception as e:
        logger.error(f"[Hidden Gems] Error: {e}")
        return []


# ------------------------------------------------------------------
# NEW (Phase 2): Genre Explorer
# ------------------------------------------------------------------
def get_genre_explorer(user_id, limit=12):
    """
    Suggestions for new genres.
    """
    return None
