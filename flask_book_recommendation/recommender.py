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

# Initialize DL Engine lazily to avoid blocking startup or script imports
_dl_engine = None

def get_dl_engine():
    global _dl_engine
    if _dl_engine is None:
        _dl_engine = DLInferenceEngine()
    return _dl_engine


logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Global Performance Caches
# ------------------------------------------------------------------
# This cache stores deserialized embeddings in memory to avoid heavy DB queries
# on every page refresh or recommendation request.
_GLOBAL_EMBEDDING_CACHE = {
    'matrix': None,      # numpy matrix (N, D)
    'book_ids': [],      # List of book IDs corresponding to rows
    'last_updated': 0,   # Timestamp
    'lock': False        # Simple flag for atomic-ish updates
}

def _get_embeddings_matrix(ttl=3600):
    """
    Helper to get the embeddings matrix from memory, loading it from DB if needed.
    TTL defaults to 1 hour to account for new books.
    """
    import time
    now = time.time()
    
    # 1. Check if cache is valid
    if (_GLOBAL_EMBEDDING_CACHE['matrix'] is not None and 
        (now - _GLOBAL_EMBEDDING_CACHE['last_updated'] < ttl)):
        return _GLOBAL_EMBEDDING_CACHE['matrix'], _GLOBAL_EMBEDDING_CACHE['book_ids']

    # 2. Loading from DB
    try:
        logger.info("[Embedding-Cache] Loading embeddings matrix from database...")
        start_time = time.perf_counter()
        
        # Pull all embeddings
        all_rows = BookEmbedding.query.all()
        if not all_rows:
            return None, []

        ids = []
        vectors = []
        target_dim = None
        
        for row in all_rows:
            if row.vector is not None:
                v = np.array(row.vector, dtype=np.float32)
                if v.ndim == 1:
                    # Initialize target_dim from the first valid vector
                    if target_dim is None:
                         target_dim = v.shape[0]
                         
                    # Only include vectors with consistent dimension
                    if v.shape[0] == target_dim:
                        ids.append(row.book_id)
                        vectors.append(v)
        
        if not vectors:
            return None, []

        # Update Cache
        _GLOBAL_EMBEDDING_CACHE['matrix'] = np.vstack(vectors)
        _GLOBAL_EMBEDDING_CACHE['book_ids'] = ids
        _GLOBAL_EMBEDDING_CACHE['last_updated'] = now
        
        elapsed = (time.perf_counter() - start_time) * 1000
        logger.info(f"[Embedding-Cache] Matrix loaded: {len(ids)} vectors in {elapsed:.2f}ms")
        
        return _GLOBAL_EMBEDDING_CACHE['matrix'], _GLOBAL_EMBEDDING_CACHE['book_ids']
        
    except Exception as e:
        logger.error(f"[Embedding-Cache] Error loading matrix: {e}", exc_info=True)
        return None, []


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _book_to_dict(book, source="Local", reason=None, extra_meta=None):
    """
    يحوّل كائن Book من الـ ORM إلى قاموس جاهز للتمبليت.
    """
    if book is None:
        return None

    cover_url = getattr(book, "cover_url", None)
    if cover_url and 'books.google.com' in cover_url and '&edge=curl' in cover_url:
        cover_url = cover_url.replace('&edge=curl', '').replace('&edge=curl&', '&')

    data = {
        "id": getattr(book, "google_id", None) or f"local_{book.id}",
        "title": getattr(book, "title", None),
        "author": getattr(book, "author", None),
        "cover": cover_url,
        "source": source,
        "reason": reason,
        "rating": getattr(book, "average_rating", None) or getattr(book, "rating", None),
    }
    
    # Add AI Metadata if provided
    if extra_meta:
        data.update(extra_meta)
        
    return data


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


# @cache.memoize(timeout=60)  # DISABLED: Allow fresh results on every refresh
def get_trending(limit=12):
    """
    يحصل على الكتب الرائجة مع fallback ذكي في حال كانت قاعدة البيانات فارغة.
    """
    books_dicts = []
    seen_ids = set()

    try:
        # 1. أولاً: نحاول جلب الكتب التي أضافها المستخدمون (المفضلة)
        user_books = (
            Book.query
            .filter(Book.owner_id.isnot(None))
            .order_by(Book.created_at.desc())
            .limit(limit * 3)
            .all()
        )
        
        # 2. ثانياً: إذا لم يكن هناك يوزر بوكس كافية، نجلب أي كتب من القاعدة
        if len(user_books) < limit:
            more_books = Book.query.order_by(func.random()).limit(limit * 3).all()
            user_books.extend(more_books)
            
        random.shuffle(user_books)
        
        for b in user_books:
            book_id = f"local_{b.id}" if not b.google_id else b.google_id
            if book_id in seen_ids:
                continue
            seen_ids.add(book_id)
            
            if not b.title or b.title in ['Untitled', 'Unknown']:
                continue

            owner_name = "مستخدم"
            owner_id = None
            if getattr(b, "owner", None):
                owner_id = b.owner.id
                if b.owner.name:
                    owner_name = b.owner.name
                    
            book_dict = _book_to_dict(
                b,
                source="المكتبة",
                reason=f"👤 أضافه: {owner_name}" if getattr(b, "owner", None) else "🔥 شائع محلياً",
            )
            
            if book_dict:
                book_dict['owner_name'] = owner_name
                book_dict['owner_id'] = owner_id
                books_dicts.append(book_dict)
            
            if len(books_dicts) >= limit:
                break
                
        # 3. ثالثاً: Fallback للإنترنت إذا كانت القاعدة فارغة تماماً
        if len(books_dicts) < limit:
            try:
                from .utils import fetch_google_books
                queries = ["أفضل الكتب", "روايات", "برمجة", "تاريخ", "تطوير الذات"]
                items, _ = fetch_google_books(random.choice(queries), max_results=limit - len(books_dicts))
                for item in items:
                    v = item.get("volumeInfo", {})
                    # محاكاة شكل قاموس الكتاب
                    cover = v.get("imageLinks", {}).get("thumbnail")
                    if cover and cover.startswith("http://"): cover = "https" + cover[4:]
                    fallback_dict = {
                        "id": item.get("id"),
                        "title": v.get("title", "رائج الان"),
                        "author": v.get("authors", ["غير معروف"])[0] if v.get("authors") else "غير معروف",
                        "cover": cover,
                        "source": "Google Books",
                        "reason": "🔥 شائع عالمياً",
                        "rating": v.get("averageRating")
                    }
                    books_dicts.append(fallback_dict)
            except Exception as e:
                logger.error(f"[Trending] Internet fallback error: {e}", exc_info=True)
                
    except Exception as e:
        logger.error(f"[Trending] Error: {e}", exc_info=True)

    # خلط النتائج النهائية لضمان التنوع
    random.shuffle(books_dicts)
    books_dicts = _deduplicate_dicts(books_dicts)
    result = books_dicts[:limit]
    logger.info(f"[Trending] Returning {len(result)} trending books")
    return result





# @cache.memoize(timeout=600)  # DISABLED: Allow fresh results on every refresh
def get_cf_similar(user_id, top_n=30, min_users=2, offset=0, randomize=False):
    """
    Get recommendations based on similar users (User-User Collaborative Filtering)
    :param user_id: ID of the user
    :param top_n: Number of recommendations to return
    :param min_users: Minimum number of similar users required to make a recommendation
    :param offset: Pagination offset

        
    Returns:
        قائمة من القواميس (كتب مقترحة) للمستخدم المحدد
    """
    # 🔒 Security Hardening: Ensure user_id is valid
    if not user_id:
        return []

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
        if offset >= len(top_indices):
            return []
            
        if randomize:
            # Take a larger pool and shuffle to ensure variety on refresh
            pool_size = max(top_n * 3, 100)
            potential_indices = top_indices[offset : offset + pool_size]
            np.random.shuffle(potential_indices)
            top_indices = potential_indices
        else:
            top_indices = top_indices[offset:]
        
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


# @cache.memoize(timeout=600)  # Cache disabled for dynamic results
def get_content_similar(user_id, top_n=30, history_limit=20, randomize=False):
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
    # 🔧 FIX #3: التحقق من صحة user_id لمنع مشاركة البيانات
    if not user_id or user_id <= 0:
        return []
    
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

    if randomize:
        # Take top 100 candidates and shuffle for variety
        pool_size = max(top_n * 4, 100)
        potential = ranked_indices[:pool_size]
        np.random.shuffle(potential)
        ranked_indices = potential

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


# @cache.memoize(timeout=600)  # Cache disabled for dynamic results
def get_view_based_recommendations(user_id, top_n=12, history_limit=10, randomize=False):
    """
    توصيات ذكية بناءً على سجل المشاهدات (UserBookView) باستخدام AI Embeddings.
    
    الخوارزمية:
    1. جلب آخر الكتب التي شاهدها المستخدم
    2. استخراج المتجهات (Embeddings) لهذه الكتب
    3. حساب "متجه الاهتمام الحالي" (متوسط المتجهات)
    4. البحث عن أقرب الكتب لهذا المتجه باستخدام Cosine Similarity
    """
    # 🔧 FIX #3: التحقق من صحة user_id لمنع مشاركة البيانات
    if not user_id or user_id <= 0:
        return []

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
        
        if randomize:
            # Shuffle top pool for fresh views on refresh
            pool_size = max(top_n * 4, 40)
            potential = ranked_indices[:pool_size]
            np.random.shuffle(potential)
            ranked_indices = potential
            
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

from .ai_client import ai_client

def _get_ai_embedding_recommendations(user_id, viewed_book_ids, search_queries=None, favorite_book_ids=None, high_rated_book_ids=None, explicit_genres=None, limit=10, offset=0, randomize=False):
    """
    Hybrid Recommender: AI Engine (Two-Tower) -> Fallback to Local Embeddings.
    """
    # 1. Try AI Engine (Microservice)
    try:
        # Prepare Context for AI
        history_texts = []
        # Fetch titles of viewed books
        if viewed_book_ids:
            books = Book.query.filter(Book.id.in_(viewed_book_ids[:5])).all() # Limit history sent
            history_texts = [f"{b.title} {b.description or ''}" for b in books]
        
        # Add Search Queries to history context
        if search_queries:
            history_texts.extend(search_queries[:3])
            
        interest_texts = explicit_genres or []
        
        ai_recs = ai_client.get_recommendations(user_id, history_texts, interest_texts, k=limit+offset)
        
        if ai_recs:
            # AI Returned Data -> Sort and Fetch Book Objects
            # ai_recs = [{'book_id': 123, 'score': 0.9, 'explanation': 'xxx'}]
            
            # Extract IDs (assuming AI returns local DB IDs for now, or we need mapping)
            # In our implementation of indexer.py, we put Book.ids into FAISS.
            
            rec_ids = [r['book_id'] for r in ai_recs]
            score_map = {r['book_id']: r['score'] for r in ai_recs}
            expl_map = {r['book_id']: r.get('explanation', 'AI Choice') for r in ai_recs}
            
            # Fetch objects
            books = Book.query.filter(Book.id.in_(rec_ids)).all()
            books_map = {b.id: b for b in books}
            
            final_recs = []
            for rid in rec_ids:
                if rid in books_map:
                    b = books_map[rid]
                    # Apply offset manually if API didn't handle it strictly (API returns k top)
                    # We requested limit+offset, so we slice locally
                    pass
            
            # Build Result List
            for rid in rec_ids:
                 if rid in books_map:
                     b = books_map[rid]
                     
                     explanation = expl_map[rid]
                     score = float(score_map[rid])
                     
                     # Determine specific algorithm based on explanation keywords
                     algo = "Transformer Semantic Model"
                     if "similar to" in explanation.lower():
                         algo = "Hybrid Ranking Engine"
                     elif "interest" in explanation.lower():
                         algo = "Behavioral Learning"

                     meta = {
                         "score": f"{score:.2f}",
                         "algorithm_used": algo,
                         "model_version": "v2.1 (Two-Tower)",
                         "reason_detail": explanation
                     }

                     d = _book_to_dict(b, source="AI Neural Brain", reason=explanation, extra_meta=meta)
                     if d:
                         final_recs.append(d)
            
            # Slice for pagination
            if offset < len(final_recs):
                return final_recs[offset:offset+limit]
            else:
                return []
                
    except Exception as e:
        logger.error(f"[AI-Bridge] Error contacting AI engine: {e}")
        # Continue to fallback...

    # ---------------- FALLBACK: Local Logic ----------------
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
        
        # 🆕 Fix Dimension Mismatch: Filter vectors to ensure consistency (384 vs 768)
        # Determine target dimension from the first vector (likely from live embedding)
        target_dim = all_vectors[0].shape[0]
        
        # Filter all_vectors to match target_dim
        consistent_vectors = [v for v in all_vectors if v.shape[0] == target_dim]
        
        if not consistent_vectors:
             logger.warning(f"[AI-Embed] No consistent vectors found for dimension {target_dim}")
             return []

        # بناء بروفايل المستخدم (Centroid)
        user_profile = np.mean(np.vstack(consistent_vectors), axis=0).reshape(1, -1)
        
        # استثناء الكتب التي تفاعل معها المستخدم بالفعل
        exclude_ids = set(viewed_book_ids) | set(favorite_book_ids or []) 
        if isinstance(high_rated_book_ids, dict):
            exclude_ids |= set(high_rated_book_ids.keys())
        elif isinstance(high_rated_book_ids, list):
            exclude_ids |= set(high_rated_book_ids)

        # ---------------- OPTIMIZED: Using Global Matrix ----------------
        matrix, matrix_ids = _get_embeddings_matrix()
        
        if matrix is None:
            logger.warning("[AI-Embed] Matrix is empty or not loaded.")
            return []

        # Filter candidate matrix by dimension matching the user profile
        if matrix.shape[1] != target_dim:
             logger.warning(f"[AI-Embed] Matrix dimension mismatch ({matrix.shape[1]}) vs Target ({target_dim})")
             # Still try to find matching ones if possible? Usually matrix is consistent.
             return []

        candidate_ids = matrix_ids
        candidate_vectors = matrix
        
        # We still need to handle exclude_ids. 
        # Filtering a large matrix by ID is better done by indices.
        exclude_indices = [i for i, bid in enumerate(candidate_ids) if bid in exclude_ids]
        
        # Instead of np.delete (slow), we just mask them after similarity Calculation if possible,
        # or filter ahead if the exclude list is small.
        # Since exclude_ids is usually < 100, we can just mask.
        
        mat = candidate_vectors
        sims = cosine_similarity(user_profile, mat)[0]
        
        # Mask excluded IDs
        if exclude_indices:
            sims[exclude_indices] = -1.0

        
        # ترتيب حسب التشابه
        ranked_indices = np.argsort(sims)[::-1]
        
        recs = []
        # نأخذ شريحة أكبر قليلاً للتصفية, ثم نقص حسب الـ offset
        # offset هنا يعني "كم نتيجة نتخطى من الأفضل"
        start_idx = offset
        # إذا كنا نتخطى أكثر من عدد النتائج, نرجع فارغ
        if start_idx >= len(ranked_indices):
             return []
             
        # 🆕 Randomization: Shuffle the top candidates before slicing
        if randomize:
            # We take a larger pool (e.g., 3x limit or 50) starting from offset
            pool_size = max(limit * 3, 30)
            candidate_pool = ranked_indices[start_idx : start_idx + pool_size]
            # Shuffle this pool
            np.random.shuffle(candidate_pool)
            # Now take the loop indices from this shuffled pool
            indices_to_iter = candidate_pool
        else:
            indices_to_iter = ranked_indices[start_idx:]
            
        for idx in indices_to_iter:
            score = sims[idx]
            if score < 0.35:  # عتبة التشابه
                continue
            
            book = Book.query.get(candidate_ids[idx])
            if not book:
                continue
            
            meta = {
                "score": f"{score:.2f}",
                "algorithm_used": "Sematic Hybrid Embeddings",
                "model_version": "v1.5 (Local)",
                "reason_detail": f"Based on semantic similarity to your reading history ({int(score*100)}% match)."
            }

            book_dict = _book_to_dict(
                book,
                source="AI Smart Match",
                reason=f"🧠 تطابق ذكي: {int(score*100)}%",
                extra_meta=meta
            )
            if book_dict:
                # book_dict["score"] is already set in meta
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

def get_deep_learning_recommendations(user_id, limit=10, randomize=False):
    """
    Get recommendations using the Two-Tower Deep Learning model.
    Includes Hybrid Ranking logic with full logging and traceability.
    """
    import time
    from .recommendation_logger import (
        RecommendationPipelineLogger, 
        RecommendationTrace,
        validate_embedding,
        rec_logger
    )
    
    with RecommendationPipelineLogger(user_id or 0) as pipeline_log:
        try:
            # 1. Stage 1: Behavioral (User Context & Interest Analysis)
            behavioral_start = time.perf_counter()
            
            recent_views = []
            if user_id:
                recent_views = (
                    UserBookView.query
                    .filter_by(user_id=user_id)
                    .order_by(UserBookView.last_viewed_at.desc())
                    .limit(10)
                    .all()
                )
            
            rec_logger.debug(f"[DL] user_id={user_id}, recent_views={len(recent_views)}")
            
            history_vectors = []
            viewed_ids = []
            for v in recent_views:
                book_id = v.book_id
                if not book_id and v.google_id:
                     b = Book.query.filter_by(google_id=v.google_id).first()
                     if b: book_id = b.id
                
                if book_id:
                    viewed_ids.append(book_id)
                    emb = BookEmbedding.query.filter_by(book_id=book_id).first()
                    if emb and emb.vector is not None:
                        history_vectors.append(np.array(emb.vector, dtype=np.float32))
            
            # Validate embeddings
            if history_vectors:
                validate_embedding(history_vectors[0], context="user_history[0]")
            
            # Pad history to 10
            if len(history_vectors) < 10:
                pad_len = 10 - len(history_vectors)
                for _ in range(pad_len):
                    history_vectors.append(np.zeros(384, dtype=np.float32))
            else:
                history_vectors = history_vectors[:10]
                
            history_arr = np.array(history_vectors)
            interest_vec = np.mean(history_arr, axis=0)

            # 🆕 Randomization: Add noise to user profile
            if randomize:
                noise = np.random.normal(0, 0.08, interest_vec.shape).astype(np.float32)
                interest_vec = interest_vec + noise
            
            behavioral_time = (time.perf_counter() - behavioral_start) * 1000
            pipeline_log.log_stage("behavioral", time_ms=behavioral_time, results=len(recent_views))

            # 2. Stage 2: Transformer (Candidate Retrieval & Embedding Lookup)
            transformer_start = time.perf_counter()
            
            # 🆕 DYNAMIC INJECTION
            if randomize:
                try:
                    from .utils import fetch_google_books, generate_book_embedding_if_missing
                    import random
                    
                    themes = ["Machine Learning", "Classic Literature", "Future Technologies", "Startup Culture", "World History", "Psychology", "Science Fiction", "Data Science", "Modern Art"]
                    theme = random.choice(themes)
                    
                    rec_logger.debug(f"[DL] Injecting dynamic books from theme: {theme}")
                    items, _ = fetch_google_books(theme, max_results=4)
                    
                    for it in (items or []):
                        gid = it.get("id")
                        if not gid: continue
                        vi = it.get("volumeInfo", {})
                        title = vi.get("title")
                        if not title: continue
                        
                        existing = Book.query.filter_by(google_id=gid).first()
                        if not existing:
                            imgs = vi.get("imageLinks", {}) or {}
                            cover = imgs.get("thumbnail") or ""
                            if cover.startswith("http://"): cover = "https://" + cover[7:]
                            
                            new_book = Book(
                                google_id=gid,
                                title=title[:150],
                                author=", ".join(vi.get("authors", []))[:150],
                                description=vi.get("description", ""),
                                cover_image=cover,
                                categories=", ".join(vi.get("categories", []))[:100]
                            )
                            db.session.add(new_book)
                            db.session.commit()
                            generate_book_embedding_if_missing(new_book)
                except Exception as e:
                    rec_logger.error(f"[DL-Inject] Failed dynamic injection: {e}")
                    db.session.rollback()

            all_books = Book.query.all()
            candidate_features = {}
            book_metadata = {}
            
            for b in all_books:
                if b.id in viewed_ids: continue
                
                emb = BookEmbedding.query.filter_by(book_id=b.id).first()
                if emb and emb.vector is not None:
                     candidate_features[b.id] = np.array(emb.vector, dtype=np.float32)
                     book_metadata[b.id] = {
                         'id': b.id,
                         'vector': candidate_features[b.id],
                         'popularity': 0.5,
                         'semantic_score': 0.0
                     }
            
            if not candidate_features:
                pipeline_log.log_fallback("No candidate books with embeddings")
                pipeline_log.set_final_count(0)
                return []

            transformer_time = (time.perf_counter() - transformer_start) * 1000
            pipeline_log.log_stage("transformer", time_ms=transformer_time, results=len(candidate_features))
            
            # 3. Stage 3: Neural (Two-Tower Prediction & Ranking)
            neural_start = time.perf_counter()
            user_data = {'history': history_arr, 'interests': interest_vec}
            candidates_list = list(book_metadata.values())
            
            # 🆕 Randomization: Request more results from engine if randomizing
            top_k_request = limit * 3 if randomize else limit
            
            # Generate candidates using the Two-Tower model
            try:
                engine = get_dl_engine()
                ranked_results = engine.generate_recommendations(
                    user_id,
                    user_data,
                    candidates_list,
                    top_k=top_k_request
                )
            except Exception as e:
                rec_logger.error(f"[DL-Rec] Error generating recommendations: {e}", exc_info=True)
                return []
            
            # 🆕 Randomization: Shuffle top candidates
            if randomize and len(ranked_results) > 0:
                 import random
                 # Logic: Take a larger pool from results to ensure variety
                 # We take up to 4x limit (e.g. 40 items) and shuffle them
                 pool_size = min(len(ranked_results), limit * 5) 
                 pool = ranked_results[:pool_size]
                 random.shuffle(pool)
                 
                 # Combine shuffled pool with rest (if any)
                 ranked_results = pool + ranked_results[pool_size:]
                 
                 # Trim to original limit
                 ranked_results = ranked_results[:limit]
            
            neural_time = (time.perf_counter() - neural_start) * 1000
            pipeline_log.log_stage("neural", time_ms=neural_time, results=len(ranked_results))
            
            # 4. Convert to Dicts with Trace
            recs = []
            for idx, res in enumerate(ranked_results):
                b_id = res['id']
                book = Book.query.get(b_id)
                if book:
                    # Build trace metadata
                    trace = RecommendationTrace(
                        algorithm="Two-Tower Neural Network",
                        model_version="v2.1 (PyTorch)",
                        score=res.get('final_score', 0),
                        rank=idx + 1,
                        features_used=["user_history_embeddings", "interest_vector", "book_embedding"],
                        execution_time_ms=neural_time,
                        is_fallback=False,
                        debug_info={
                            "neural_score": res.get('neural_score', 0),
                            "semantic_score": res.get('semantic_score', 0),
                            "popularity_boost": res.get('popularity', 0)
                        }
                    )
                    
                    d = _book_to_dict(
                        book,
                        source="Transformer",
                        reason=f"🧠 AI Score: {res['final_score']:.2f}",
                        extra_meta={
                            "algorithm_used": trace.algorithm,
                            "model_version": trace.model_version,
                            "score": f"{trace.score:.2f}",
                            "rank": trace.rank,
                            "features_used": trace.features_used,
                            "reason_detail": f"Neural confidence: {res.get('neural_score', 0):.2f}, "
                                           f"Semantic match: {res.get('semantic_score', 0):.2f}",
                            "_trace": trace.to_dict()
                        }
                    )
                    recs.append(d)
            
            # 🆕 TRANSFORMER INJECTION: Add fresh external books if randomizing
            # This ensures even if the neural model is static, we see new things.
            if randomize:
                try:
                    import random
                    from .utils import fetch_google_books
                    
                    # Same discovery pool
                    discovery_pool = [
                        "Best selling books 2024", "New York Times Best Sellers", "Man Booker Prize", 
                        "Science Fiction Classics", "Must read biographies", "Self improvement trends",
                        "Hidden gems literature", "Cyberpunk novels", "Psychological thrillers",
                        "History of Science", "Modern Philosophy", "Artificial Intelligence Production"
                    ]
                    
                    # Pick a random topic
                    random_topic = random.choice(discovery_pool)
                    # Random offset
                    rnd_offset = random.randint(0, 100)
                    
                    gb_res = fetch_google_books(random_topic, max_results=4, start_index=rnd_offset)
                    items = gb_res[0] if isinstance(gb_res, tuple) else gb_res
                    
                    for it in items or []:
                        if not isinstance(it, dict): continue
                        gid = it.get("id")
                        if not gid: continue
                        
                        # Avoid duplicates
                        if any(r['id'] == gid for r in recs): continue
                        
                        vi = it.get("volumeInfo") or {}
                        img = (vi.get("imageLinks") or {}).get("thumbnail")
                        if img:
                             if img.startswith("http://"): img = img.replace("http://", "https://")
                             if '&edge=curl' in img: img = img.replace('&edge=curl', '').replace('&edge=curl&', '&')
                        
                        recs.append({
                            "id": gid,
                            "title": vi.get("title"),
                            "author": ", ".join(vi.get("authors") or []),
                            "cover": img,
                            "source": "Transformer (External)",
                            "reason": f"✨ Discovery: {random_topic}",
                            "rating": vi.get("averageRating"),
                            "score": 0.5 + (random.random() * 0.4), # Random score to mix in
                            "algo_tag": "Transformer"
                        })
                        
                    # Shuffle again to mix external with neural
                    random.shuffle(recs)
                    
                except Exception as e:
                    rec_logger.error(f"[DL-Rec] Error injecting external books: {e}")
            
            print(f"DEBUG: Transformer generated {len(recs)} recommendations")
            rec_logger.info(f"DEBUG: Transformer generated {len(recs)} recommendations")

            pipeline_log.set_final_count(len(recs))
            return recs

        except Exception as e:
            pipeline_log.log_error(str(e))
            logger.error(f"[DL-Rec] Error: {e}", exc_info=True)
            return []


def _get_cf_recommendations(user_id, limit=6, offset=0):
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


# 🔧 FIX #3: تمت إزالة @cache.memoize لتجنب مشاركة البيانات بين المستخدمين
# نستخدم كاش مخصص داخل الدالة بدلاً من ذلك
def _fetch_behavior_hybrid_candidates(user_id, limit=12, offset=0, randomize=False, salt=0):
    """
    Heavy lifting: Fetches a large pool of hybrid candidates from various sources.
    🔧 FIX #3: تم إزالة الكاش المشترك لضمان عزل بيانات المستخدمين
    """
    from datetime import datetime, timedelta
    from collections import defaultdict
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from flask import current_app

    try:
        logger.info(f"[Behavior-Hybrid] Fetching pool for user {user_id}")
        
        # 1. Data Gathering
        recent_views = UserBookView.query.filter_by(user_id=user_id).order_by(UserBookView.last_viewed_at.desc()).limit(40).all()
        viewed_book_ids = [v.book_id for v in recent_views if v.book_id]
        viewed_google_ids = [v.google_id for v in recent_views if v.google_id]
        
        recent_searches = db.session.query(SearchHistory).filter_by(user_id=user_id).order_by(SearchHistory.created_at.desc()).limit(10).all()
        search_queries = [s.query for s in recent_searches if s.query]
        
        favorites = BookStatus.query.filter_by(user_id=user_id, status='favorite').all()
        favorite_book_ids = [f.book_id for f in favorites if f.book_id]

        user_ratings = UserRatingCF.query.filter(UserRatingCF.user_id==user_id, UserRatingCF.rating >= 4).all()
        high_rated_books = {r.id: r.rating for r in user_ratings}

        user_genres = db.session.query(Genre.name).join(UserGenre).filter(UserGenre.user_id == user_id).all()
        explicit_genres = [g[0] for g in user_genres]
        
        if not (viewed_book_ids or search_queries or favorite_book_ids or explicit_genres):
             return []

        # ---------------------------------------------------------
        # 2. تشغيل محركات التوصية بالتوازي
        # ---------------------------------------------------------
        
        all_recs = []
        
        # Capture real app object to pass to threads
        app = current_app._get_current_object()
        
        # INCREASED pool sizes for high variety on refresh
        ai_limit = 60
        cf_limit = 30
        explore_limit = 40
        
        # 2. Parallel Recommendation Source Fetching
        app = current_app._get_current_object()
        
        # INCREASED pool sizes
        ai_pool_limit = 80
        cf_pool_limit = 40
        explore_pool_limit = 40
        
        all_recs = []
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {}
            
            # AI
            futures["ai"] = executor.submit(
                run_in_context, app, _get_ai_embedding_recommendations,
                user_id, list(viewed_book_ids), search_queries[:5], list(favorite_book_ids),
                high_rated_books, explicit_genres, ai_pool_limit, 0, randomize
            )
            
            # CF
            futures["cf"] = executor.submit(
                run_in_context, app, get_cf_similar, user_id, top_n=cf_pool_limit
            )
            
            # Explore
            def fetch_simple_explore():
                results = []
                seen_ex = set(viewed_google_ids)
                
                # 🆕 DYNAMIC EXPLORE: If randomize, pick a random topic!
                target = search_queries[0] if search_queries else (explicit_genres[0] if explicit_genres else "Best Sellers")
                
                if randomize:
                    import random
                    discovery_pool = [
                        "Best selling books 2024", "New York Times Best Sellers", "Man Booker Prize", 
                        "Science Fiction Classics", "Must read biographies", "Self improvement trends",
                        "Hidden gems literature", "Cyberpunk novels", "Psychological thrillers",
                        "History of Science", "Modern Philosophy", "Artificial Intelligence Production"
                    ]
                    target = random.choice(discovery_pool)
                    logger.info(f"[Hybrid-Explore] Switched target to '{target}' for variety")
                try:
                    # 🆕 Randomization for Explore
                    start_index = 0
                    if randomize:
                        import random
                        # Use salt to deterministically shift window per cached version
                        start_index = (salt * 10) % 200
                    
                    books, _ = fetch_google_books(target, max_results=explore_pool_limit, start_index=start_index)
                    for b in books or []:
                        gid = b.get('id')
                        if gid and gid not in seen_ex:
                            vi = b.get('volumeInfo', {})
                            results.append({
                                "id": gid,
                                "title": vi.get("title"),
                                "author": ", ".join(vi.get("authors") or []),
                                "cover": (vi.get("imageLinks") or {}).get("thumbnail", "").replace("http://", "https://"),
                                "source": "استكشاف الذكاء الاصطناعي",
                                "reason": f"✨ مقترح بناءً على اهتمامك بـ {target}",
                                "score": 0.5,
                                "rec_type": "exploration"
                            })
                            seen_ex.add(gid)
                except: pass
                return results

            futures["explore"] = executor.submit(run_in_context, app, fetch_simple_explore)

            for key, future in futures.items():
                try:
                    res = future.result(timeout=30)
                    if res: all_recs.extend(res)
                except Exception as e:
                    logger.error(f"[Behavior-Hybrid] Future {key} failed: {e}")

        # Remove duplicates
        unique_final = []
        seen_ids = set()
        for r in all_recs:
            rid = r.get('id')
            if rid and rid not in seen_ids:
                seen_ids.add(rid)
                unique_final.append(r)
        
        logger.info(f"[Behavior-Hybrid] Pool fetching complete. Total candidates: {len(unique_final)}")
        return unique_final

    except Exception as e:
        logger.error(f"[Behavior-Hybrid] Pool fetch fatal error: {e}", exc_info=True)
        return []

# Non-cached entry point to allow randomization on every refresh
def get_behavior_based_recommendations(user_id, limit=12, offset=0, randomize=False):
    """
    توصيات ذكية شاملة (YouTube-Style) - نسخة محسنة بالأداء
    """
    # 🔧 FIX: Validate user_id
    if not user_id:
        return []

    import random
    import time
    try:
        # Instead of user_id based salt that might be static, use time for true reshuffle
        salt = int(time.time() * 1000) % 100 if randomize else 0
        
        candidates = _fetch_behavior_hybrid_candidates(user_id, limit=limit, offset=offset, randomize=randomize, salt=salt)
        
        if not candidates:
            return get_trending(limit=limit)

        # 2. التنوع والخلط السريع (Refresh)
        if randomize and len(candidates) > 0:
            random.shuffle(candidates)
            sampled = candidates[:limit]
        else:
            sampled = candidates[:limit]
            
        logger.info(f"[Behavior-Hybrid] Refresh Fast-Sample: Returned {len(sampled)} books (Pool: {len(candidates)})")
        return sampled

    except Exception as e:
        logger.error(f"[Behavior-Hybrid] Wrapper Error: {e}")
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
        # ضمان تطابق الأبعاد
        if v.ndim == 1 and v.shape[0] == query_vec.shape[1]:
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
def get_topic_based(user_id, limit=24, offset=0, prefs_limit=3, recent_query=None, randomize=False):
    """
    توصيات مبنية على اهتمامات المستخدم (Topic-Based Recommendations).
    محسّن: يستخدم التشغيل المتوازي لجلب الكتب من 5 مصادر في آن واحد!
    
    Args:
        user_id: معرف المستخدم
        limit: الحد الأقصى لعدد التوصيات
        offset: بداية النتائج (للتصفح)
        prefs_limit: عدد التفضيلات المستخدمة
        recent_query: استعلام بحث فوري لتجاوز سجل البحث.
        randomize: خلط الاهتمامات لضمان التنوع عند التحديث.
        
    Returns:
        قائمة من القواميس تمثل الكتب المقترحة من مصادر مختلفة
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    # 🔒 Security Hardening: Ensure user_id is valid
    if not user_id:
        logger.warning(f"[Topic] No user_id provided, returning empty.")
        return {'books': [], 'interests_exhausted': True, 'total_interests': 0, 'current_page': 0}

    logger.info(f"[Topic] Getting topic-based recommendations for user {user_id}, limit={limit}, offset={offset}")

    topics = []
    seen_topics = set()
    potential_topics = []

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

    # 🆕 DYNAMIC INJECTION: If randomizing, inject fresh "Discovery" topics from the web/list
    # This solves the "static" feeling by querying for something new every time.
    if randomize:
        import random
        # List of dynamic discovery topics
        discovery_pool = [
            "Best selling books 2024", "New York Times Best Sellers", "Man Booker Prize", 
            "Science Fiction Classics", "Must read biographies", "Self improvement trends",
            "Hidden gems literature", "Cyberpunk novels", "Psychological thrillers",
            "History of Science", "Modern Philosophy", "Artificial Intelligence Production"
        ]
        # Inject 2 random topics from pool
        new_topics = random.sample(discovery_pool, 2)
        for t in new_topics:
            if t.lower() not in seen_topics:
                # Insert at random positions to mix with personal interests
                insert_pos = random.randint(1, len(all_unique_topics)) if len(all_unique_topics) > 0 else 0
                all_unique_topics.insert(insert_pos, t)
                seen_topics.add(t.lower())
                logger.info(f"[Topic] Injected discovery topic: '{t}'")

    if not all_unique_topics:
        logger.debug(f"[Topic] No topics found for user {user_id}")
        return []

    # 🔧 FIX: التصفح عبر الاهتمامات حسب الصفحة
    # كل صفحة تعرض اهتمامات مختلفة (3 اهتمامات لكل صفحة)
    topics_per_page = 3
    
    # 🆕 Randomization logic for dynamic refresh
    if randomize:
        import random
        # If randomizing, we pick a random subset of interests to show
        # but we try to keep high-priority ones (first 3) in the mix more often
        if len(all_unique_topics) > 3:
             # Keep top 1 always roughly, shuffle rest?
             # Or just shuffle specific slices.
             # Simple approach: Shuffle everything to give total freshness
             # But keep "recent query" (index 0 if exists) somewhat prioritized?
             
             # Let's shuffle the pool that comes AFTER the mandatory recent query
             start_shuffle = 1 if recent_query else 0
             pool_to_shuffle = all_unique_topics[start_shuffle:]
             random.shuffle(pool_to_shuffle)
             all_unique_topics = all_unique_topics[:start_shuffle] + pool_to_shuffle
             
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
    
    # 🆕 Randomization: Add random offset to API calls to get different books
    # APIs differ in how they handle offsets/pagination.
    # Google: startIndex (0-based index)
    # OpenLib: offset (0-based index)
    # ITBook/Gutenberg: page (1-based page number)
    
    global_offset = 0
    if randomize:
        import random
        # Random offset for index-based APIs (0 to 100) - Increased to ensure deep variety
        # 🔧 FIX: Ensure randomness is actually effective per request
        global_offset = random.randint(0, 200)
        # Random page for page-based APIs (1 to 10)
        api_page = random.randint(1, 10)
    
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
                for future in as_completed(futures, timeout=2.5):
                    try:
                        source, books = future.result(timeout=2.0)
                        results.extend(books)
                    except Exception as e:
                        logger.error(f"[Topic] Future error for '{topic}': {e}")
            except TimeoutError:
                logger.warning(f"[Topic] ⏱️ Timeout fetching sources for '{topic}', using partial results")
        
        return results
    
    # جلب الكتب لكل موضوع بالتوازي
    def _fetch_topic_books(t, index):
        current_limit = per_topic_limit + 2 if index == 0 else per_topic_limit
        per_source = max(4, int(current_limit / 3))
        logger.debug(f"[Topic] Searching for '{t}' with limit {per_source}, offset {global_offset}, page {api_page}")
        return fetch_all_sources_for_topic(t, per_source, global_offset, api_page)

    with ThreadPoolExecutor(max_workers=len(topics)) as executor:
        topic_futures = [executor.submit(_fetch_topic_books, t, i) for i, t in enumerate(topics)]
        
        for future in as_completed(topic_futures, timeout=3.5):
            try:
                topic_books = future.result()
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
                        continue
                        
                    seen_ids.add(bid)
                    all_books.append(book)
                    
                    if len(all_books) >= limit:
                        break
            except Exception as e:
                logger.error(f"[Topic] Error processing topic future: {e}")
            if len(all_books) >= limit:
                break

    if randomize and len(all_books) > 0:
        import random
        random.shuffle(all_books)

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
    # 🔧 FIX #3: التحقق من صحة user_id لمنع مشاركة البيانات
    if not user_id or user_id <= 0:
        return get_trending(limit)
    
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


def get_last_search_recommendations(user_id, limit=12, randomize=False):
    """
    جلب توصيات بناءً على آخر عملية بحث قام بها المستخدم حصراً.
    الغرض: إعطاء المستخدم شعوراً فورياً بتجاوب النظام.
    """
    # 🔒 Security Hardening: Ensure user_id is valid
    if not user_id:
        return None, None

    books_dicts = []
    seen_ids = set()
    
    try:
        # 1. جلب آخر بحث (Explicitly using sessions to avoid attribute errors)
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
        # Use a random startIndex if randomizing to get different pages of results
        start_index = 0
        if randomize:
            # Safer range for search specific queries (0-40)
            start_index = random.randint(0, 40)
            
        logger.info(f"[LastSearch] Fetching books for '{search_term}' (orig: '{query_text}') at index {start_index}")
        gb_res = fetch_google_books(search_term, max_results=(limit * 3 if randomize else limit), start_index=start_index)
        items = gb_res[0] if isinstance(gb_res, tuple) else gb_res
        
        for it in items or []:
            if not isinstance(it, dict): continue
            gid = it.get("id")
            if not gid or gid in seen_ids: continue
            seen_ids.add(gid)

            vi = it.get("volumeInfo") or {}
            img = (vi.get("imageLinks") or {}).get("thumbnail")
            
            # 🧹 Data Quality Filters
            # 1. Skip if no cover
            if not img: continue
            
            # 2. Skip if title is too short (likely noise)
            title = vi.get("title")
            if not title or len(title) < 4: continue
            
            # 3. Skip if no authors
            authors = vi.get("authors")
            if not authors: continue

            if img:
                if img.startswith("http://"):
                    img = img.replace("http://", "https://")
                if '&edge=curl' in img:
                    img = img.replace('&edge=curl', '').replace('&edge=curl&', '&')

            books_dicts.append({
                "id": gid,
                "title": title,
                "author": ", ".join(authors),
                "cover": img,
                "source": "Google Books",
                "reason": f"لأنك بحثت عن: {display_query}",
                "rating": vi.get("averageRating"),
                "ratings_count": vi.get("ratingsCount"),
                "algo_tag": "Search History" # Explicit tag for badge color
            })
            
            if len(books_dicts) >= (limit * 3 if randomize else limit):
                break
        
        if randomize and len(books_dicts) > 0:
            random.shuffle(books_dicts)
        
        logger.info(f"[LastSearch] Found {len(books_dicts)} valid books for user {user_id}")
        return display_query, books_dicts[:limit]
        
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
    # 🔧 FIX #3: التحقق من صحة user_id لمنع مشاركة البيانات
    if not user_id or user_id <= 0:
        return []
    
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
