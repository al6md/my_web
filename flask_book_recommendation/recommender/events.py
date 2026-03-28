# -*- coding: utf-8 -*-
"""
User events — log_user_view + analyze_user_profile_with_ai.
"""
import logging
from datetime import datetime

from ..models import (
    Book, UserRatingCF, SearchHistory,
    UserPreference, UserBookView
)
from ..extensions import db

logger = logging.getLogger(__name__)


def log_user_view(user_id, book):
    """
    تسجيل مشاهدة المستخدم للكتاب.
    يتم استدعاؤها عند فتح صفحة التفاصيل.
    Now also creates a UserEvent record for richer analytics.
    """
    try:
        if not user_id: return
        
        b_id = getattr(book, 'id', None)
        g_id = getattr(book, 'google_id', None)
        
        criteria = {'user_id': user_id}
        if g_id:
            criteria['google_id'] = g_id
        elif b_id:
            criteria['book_id'] = b_id
        else:
            return

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

        # Create UserEvent for richer analytics
        try:
            from ..models import UserEvent
            event = UserEvent(
                user_id=user_id,
                event_type='view',
                book_google_id=g_id,
            )
            db.session.add(event)
        except Exception:
            pass  # UserEvent table may not exist yet (pre-migration)

        db.session.commit()
        
        # --- 🆕 User Embedding Update (Phase 2) ---
        try:
            from ai_book_recommender.feature_store.user_embeddings import user_embedding_manager
            user_embedding_manager.update_user_embedding(user_id, book_id=b_id, google_id=g_id)
        except Exception as e_emb:
            logger.error(f"Embedding update error: {e_emb}")
            
        # --- 🆕 Online Learning Feedback Update ---
        try:
            from ai_book_recommender.engine import get_engine
            b_id_val = str(g_id or b_id or "")
            if b_id_val:
                get_engine().record_feedback(
                    user_id=user_id,
                    item_id=b_id_val,
                    feedback_type="view",
                    value=1.0
                )
        except Exception as e_ol:
            logger.error(f"Online learning feedback error (view): {e_ol}")
        # ------------------------------------------

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
    
    try:
        views = UserBookView.query.filter_by(user_id=user_id).order_by(UserBookView.last_viewed_at.desc()).limit(15).all()
        viewed_books = []
        for v in views:
            title = "Unknown"
            if v.book: title = v.book.title
            elif v.google_id:
                 b = Book.query.filter_by(google_id=v.google_id).first()
                 if b: title = b.title
            
            if title != "Unknown":
                viewed_books.append(title)
        
        ratings = UserRatingCF.query.filter_by(user_id=user_id).filter(UserRatingCF.rating >= 4).limit(10).all()

        searches = SearchHistory.query.filter_by(user_id=user_id).order_by(SearchHistory.created_at.desc()).limit(10).all()
        search_terms = [s.query for s in searches if s.query]

        if not viewed_books and not search_terms:
            return

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
            
            for item in suggestions:
                topic = item.get("topic")
                weight = item.get("weight", 1.0)
                
                if not topic: continue
                
                pref = UserPreference.query.filter_by(user_id=user_id, topic=topic).first()
                if pref:
                    pref.weight = min(5.0, (pref.weight + weight) / 2 + 1)
                else:
                    new_pref = UserPreference(user_id=user_id, topic=topic, weight=weight)
                    db.session.add(new_pref)
            
            db.session.commit()
            logger.info(f"[AI Analysis] Updated preferences for user {user_id}")

    except Exception as e:
        logger.error(f"[AI Analysis] Error: {e}")

def update_user_model_online(user_id: int, event):
    """
    تحديث نظام التوصيات للمستخدم مباشرة في الوقت الفعلي بناءً على الحدث المدخل.
    """
    if not user_id or not event:
        return

    # استخراج التصنيف/الموضوع للكتاب المعني
    topic = 'general'
    if event.book_google_id:
        book = Book.query.filter_by(google_id=event.book_google_id).first()
        if book and book.categories:
            # افتراض أن Categories محفوظ كـ String مقسم بـ comma أو ككلمة واحدة
            cats = [c.strip() for c in book.categories.split(",")]
            if cats:
                topic = cats[0]

    # جلب أو إنشاء تفضيل للمستخدم
    preference = UserPreference.query.filter_by(user_id=user_id, topic=topic).first()
    if not preference:
        preference = UserPreference(user_id=user_id, topic=topic, weight=1.0)
        db.session.add(preference)

    # حساب التعديل على الوزن حسب الحدث
    weight_change = 0.0
    
    if event.event_type == 'finish':
        weight_change = 0.5
    elif event.event_type == 'view':
        duration = event.duration_seconds or 0
        if duration > 300: # أكثر من 5 دقائق
            weight_change = 0.2
        elif duration < 10:
            weight_change = -0.1
    elif event.event_type == 'abandon':
        scroll = event.scroll_depth or 0.0
        if scroll < 0.2:
            weight_change = -0.3

    if weight_change != 0.0:
        preference.weight = max(0.0, preference.weight + weight_change)
        
        try:
            db.session.commit()
            logger.info(f"Updated user {user_id} preference {topic} by {weight_change}. New weight: {preference.weight}")
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating online model for user {user_id}: {e}")

def decay_preferences():
    """
    تتلاشى التفضيلات تدريجياً مع مرور الوقت للتركيز على الاهتمامات الأحدث.
    هذه الدالة يُفترض أن تُشغل عبر مهمة مجدولة (Celery Beat مثلاً) أسبوعياً كـ: `كل أحد 2 صباحاً`
    """
    try:
        db.session.execute('UPDATE user_preferences SET weight = weight * 0.95')
        db.session.commit()
        logger.info("Executed weekly preference weight decay (0.95).")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error decaying preferences: {e}")
