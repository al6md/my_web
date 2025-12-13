import logging
import random
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy import func
from flask import current_app

from .models import (
    Book, UserRatingCF, SearchHistory,
    UserPreference, BookEmbedding,
)
from .utils import (
    fetch_google_books, fetch_gutenberg_books,
    fetch_openlib_books, fetch_archive_books,
    fetch_itbook_books,
    translate_to_english_with_gemini,
    get_text_embedding,
)
from .extensions import db, cache

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
        # نستخدم google_id لو موجود، وإلا نستخدم id محلي
        "id": getattr(book, "google_id", None) or f"local_{book.id}",
        "title": getattr(book, "title", None),
        "author": getattr(book, "author", None),
        "cover": cover_url,
        "source": source,
        "reason": reason,
    }


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

            # اسم المضيف (اختياري)
            owner_name = "مستخدم"
            if b.owner and b.owner.name:
                owner_name = b.owner.name
            
            books_dicts.append(
                _book_to_dict(
                    b,
                    source="مكتبة المستخدمين",
                    reason=f"👤 أضافه: {owner_name}",
                )
            )
            
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
    
    # 1) جمع المواضيع من آخر بحث
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
    
    # 3) إذا لم توجد مواضيع، نستخدم الكتب الرائجة العامة
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
                })
                
                if len(books_dicts) >= limit:
                    break
        except Exception as e:
            logger.error(f"[PersonalTrending] Google Books error for '{topic}': {e}", exc_info=True)
        
        if len(books_dicts) >= limit:
            break
    
    # 5) إذا لم تكن كافية، نضيف كتب رائجة عامة
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


@cache.memoize(timeout=600)  # Cache لمدة 10 دقائق
def get_cf_similar(user_id, top_n=30, min_users=2):
    """
    Collaborative Filtering بسيط يعتمد على مصفوفة المستخدم-الكتاب (ratings matrix).
    
    Args:
        user_id: معرف المستخدم
        top_n: عدد التوصيات المطلوبة
        min_users: الحد الأدنى لعدد المستخدمين المطلوب
        
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
    
    نبني "بروفايل" للمستخدم من آخر الكتب التي قرأها / قيّمها،
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

@cache.memoize(timeout=60)  # إعادة الكاش مع تقليل المدة لـ 60 ثانية لضمان التحديث
def get_topic_based(user_id, limit=24, offset=0, prefs_limit=3, recent_query=None):
    """
    توصيات مبنية على اهتمامات المستخدم (Topic-Based Recommendations).
    🚀 محسّن: يستخدم التشغيل المتوازي لجلب الكتب من 5 مصادر في آن واحد!
    
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

    # 1. تجميع المواضيع المحتملة بالترتيب حسب الأولوية
    if recent_query:
        potential_topics.append(recent_query)

    try:
        last_search = db.session.query(SearchHistory).filter_by(user_id=user_id).order_by(SearchHistory.created_at.desc(), SearchHistory.id.desc()).first()
        if last_search:
            potential_topics.append(last_search.query)
    except Exception as e:
        logger.error(f"[Topic] History error: {e}", exc_info=True)

    try:
        # Increase limit to get more old interests
        prefs = UserPreference.query.filter_by(user_id=user_id).order_by(UserPreference.weight.desc()).limit(20).all()
        for p in prefs:
            potential_topics.append(p.topic)
    except Exception as e:
        logger.error(f"[Topic] prefs error: {e}", exc_info=True)

    # 2. معالجة المواضيع (ترجمة + إزالة تكرار)
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
            topics.append(topic_to_use)
            seen_topics.add(topic_to_use.lower())
            
        # نتوقف بعد الحصول على عدد كاف من المواضيع الفريدة
        # Increased to 6 to show more local/old interests
        if len(topics) >= 6:
            break

    if not topics:
        logger.debug(f"[Topic] No topics found for user {user_id}")
        return []

    logger.info(f"[Topic] Found {len(topics)} topics for user {user_id}: {topics}")
    all_books = []
    seen_ids = set()
    
    # 🚀 جلب الكتب من جميع المصادر بالتوازي لكل موضوع
    per_topic_limit = max(4, int(limit / len(topics)))
    # حساب الإزاحة لكل موضوع تقريبياً
    per_topic_offset = 0
    if offset > 0:
        per_topic_offset = int(offset / len(topics))
        
    # حساب الصفحة التقريبية (للمصادر التي تستخدم نظام الصفحات)
    # نفرض كل صفحة فيها حوالي 10 نتائج
    current_page = (per_topic_offset // 10) + 1
    
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
            img = (vi.get("imageLinks") or {}).get("thumbnail")
            if img:
                if img.startswith("http://"):
                    img = img.replace("http://", "https://")
                if '&edge=curl' in img:
                    img = img.replace('&edge=curl', '').replace('&edge=curl&', '&')
            books.append({
                "id": gid,
                "title": vi.get("title"),
                "author": ", ".join(vi.get("authors") or []),
                "cover": img,
                "source": "Google Books",
                "reason": f"🎯 لأنك بحثت مؤخراً عن «{topic}»",
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
                # لا يمكننا تحديد offset دقيق، لذا نستخدم الصفحة
                # ITBS صفحتها عادة 10 كتب
                books = fetch_itbook_books(topic, limit=per_source, page=topic_page) or []
                return ("itbook", [{
                    "id": b.get("id"),
                    "title": b.get("title"),
                    "author": b.get("author"),
                    "cover": b.get("cover"),
                    "source": "IT Bookstore",
                    "reason": f"🎯 كتب تقنية: «{topic}»",
                } for b in books if b.get("id")])
            except Exception as e:
                logger.error(f"[Topic] ITBook error for '{topic}': {e}")
                return ("itbook", [])
        
        def fetch_openlib():
            try:
                # OpenLibrary يدعم offset
                books = fetch_openlib_books(topic, limit=per_source, offset=topic_offset) or []
                return ("openlib", [{
                    "id": b.get("id"),
                    "title": b.get("title"),
                    "author": b.get("author"),
                    "cover": b.get("cover"),
                    "source": "OpenLibrary",
                    "reason": f"🎯 OpenLibrary: «{topic}»",
                } for b in books if b.get("id")])
            except Exception as e:
                logger.error(f"[Topic] OpenLib error for '{topic}': {e}")
                return ("openlib", [])
        
        def fetch_archive():
            try:
                # Archive يدعم page (تقريبي)
                books = fetch_archive_books(topic, limit=per_source) or [] # Archive wrapper might not support explicit page arg easily yet in standard utils?
                # Actually fetch_archive_books in utils.py usually takes just limit, let's verify if we updated it.
                # Assuming simple support for now, or just re-fetching (limited effective pagination for archive without deeper changes)
                # But let's try calling with page if supported or just rely on randomness if not
                return ("archive", [{
                    "id": b.get("id"),
                    "title": b.get("title"),
                    "author": b.get("author"),
                    "cover": b.get("cover"),
                    "source": "Internet Archive",
                    "reason": f"📚 من أرشيف الإنترنت: «{topic}»",
                } for b in books if b.get("id")])
            except Exception as e:
                logger.error(f"[Topic] Archive error for '{topic}': {e}")
                return ("archive", [])
        
        def fetch_gutenberg():
            try:
                # Gutenberg uses page
                books = fetch_gutenberg_books(topic, limit=per_source, page=topic_page) or []
                return ("gutenberg", [{
                    "id": b.get("id"),
                    "title": b.get("title"),
                    "author": b.get("author"),
                    "cover": b.get("cover"),
                    "source": "Project Gutenberg",
                    "reason": f"📖 كلاسيكيات: «{topic}»",
                } for b in books if b.get("id")])
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
        
        # حساب إزاحة خاصة لهذا الموضوع (لتوزيع النتائج بشكل جيد)
        # إذا كان topics=3 و offset=12، فكل موضوع يأخذ offset=4
        this_offset = per_topic_offset 
        this_page = current_page
        
        logger.debug(f"[Topic] Searching for '{t}' with limit {per_source}, offset {this_offset}, page {this_page}")
        
        topic_books = fetch_all_sources_for_topic(t, per_source, this_offset, this_page)
        
        for book in topic_books:
            bid = book.get("id")
            if bid and bid not in seen_ids:
                seen_ids.add(bid)
                all_books.append(book)
        
        if len(all_books) >= limit:
            break

    result = all_books[:limit]
    logger.info(f"[Topic] Returning {len(result)} books for user {user_id} (from {len(all_books)} total found)")
    if len(result) == 0:
        logger.warning(f"[Topic] No books found for user {user_id} with topics: {topics}")
    return result


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
    
    # 3) إذا لم توجد مواضيع، نستخدم الكتب الرائجة العامة
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
                })
                
                if len(books_dicts) >= limit:
                    break
        except Exception as e:
            logger.error(f"[PersonalTrending] Google Books error for '{topic}': {e}", exc_info=True)
        
        if len(books_dicts) >= limit:
            break
    
    # 5) إذا لم تكن كافية، نضيف كتب رائجة عامة
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
    
    # إذا لا توجد اهتمامات، استخدم موضوعات افتراضية
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


@cache.memoize(timeout=120)  # Cache لمدة 2 دقيقة
def get_homepage_sections(user_id, recent_query=None):
    """
    ترجع قائمة أقسام لصفحة /explore مع توصيات متنوعة.
    """
    sections = []

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
    topics_raw = get_topic_based(user_id, limit=60, recent_query=recent_query)
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
    sections.append({
        "title": "🔥 الرائج في مجتمع القرّاء",
        "subtitle": "كتب يقرأها ويضيفها أصدقاؤك في المنصة",
        "books": community_trend,
        "style": "warning",
        "icon": "fire",
        "query": "special:trending"
    })

    return sections


def get_all_libraries_showcase(query="books", limit_per_source=6):
    """
    جلب كتب من جميع المصادر الخمسة لعرضها معاً.
    
    Args:
        query: كلمة البحث (افتراضي: books)
        limit_per_source: عدد الكتب من كل مصدر
        
    Returns:
        قائمة من أقسام، كل قسم يمثل مصدر مختلف
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


