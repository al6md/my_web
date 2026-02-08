# -*- coding: utf-8 -*-
"""
🎓 تدريب نموذج التوصيات من قاعدة البيانات الحقيقية
====================================================

هذا السكريبت يقوم بـ:
1. تحميل بيانات التفاعلات (تقييمات، مشاهدات) من قاعدة البيانات
2. تحميل متجهات الكتب (Book Embeddings)
3. تدريب نموذج Two-Tower على البيانات الحقيقية

الاستخدام:
    python scripts/train_from_database.py
"""

import os
import sys
import numpy as np
from datetime import datetime

# إضافة المشروع إلى المسار
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# تحميل Flask app للوصول لقاعدة البيانات
from flask_book_recommendation.app import create_app
from flask_book_recommendation.extensions import db
from flask_book_recommendation.models import (
    User, Book, UserRatingCF, BookReview, UserBookView, 
    BookEmbedding, BookStatus
)

from ai_book_recommender.training.data_loader import InteractionSample, create_data_loaders
from ai_book_recommender.training.train import Trainer, TrainingConfig
from ai_book_recommender.models.two_tower_v2 import TwoTowerV2


def load_interactions_from_db():
    """
    تحميل تفاعلات المستخدمين من قاعدة البيانات.
    
    يجمع بين:
    - التقييمات الصريحة (UserRatingCF, BookReview) -> label = rating/5
    - المشاهدات الضمنية (UserBookView) -> label = 1.0
    - حالة الكتب (BookStatus: favorite, finished) -> label = 1.0
    """
    interactions = []
    
    print("📊 جاري تحميل البيانات من قاعدة البيانات...")
    
    # 1. تقييمات CF
    ratings_cf = UserRatingCF.query.all()
    print(f"  - تقييمات CF: {len(ratings_cf)}")
    for r in ratings_cf:
        interactions.append(InteractionSample(
            user_id=r.user_id,
            item_id=r.google_id,
            label=min(r.rating / 5.0, 1.0)  # تطبيع إلى 0-1
        ))
    
    # 2. مراجعات الكتب
    reviews = BookReview.query.all()
    print(f"  - مراجعات الكتب: {len(reviews)}")
    for r in reviews:
        item_id = r.google_id or f"book_{r.book_id}"
        interactions.append(InteractionSample(
            user_id=r.user_id,
            item_id=item_id,
            label=min(r.rating / 5.0, 1.0)
        ))
    
    # 3. مشاهدات الكتب (تفاعل ضمني)
    views = UserBookView.query.all()
    print(f"  - مشاهدات الكتب: {len(views)}")
    for v in views:
        item_id = v.google_id or f"book_{v.book_id}"
        # كلما زادت المشاهدات، زادت الأهمية
        label = min(0.3 + (v.view_count * 0.1), 1.0)
        interactions.append(InteractionSample(
            user_id=v.user_id,
            item_id=item_id,
            label=label
        ))
    
    # 4. حالة الكتب (المفضلة، المنتهية)
    statuses = BookStatus.query.filter(
        BookStatus.status.in_(['favorite', 'finished'])
    ).all()
    print(f"  - الكتب المفضلة/المنتهية: {len(statuses)}")
    for s in statuses:
        book = Book.query.get(s.book_id)
        if book:
            item_id = book.google_id or f"book_{book.id}"
            interactions.append(InteractionSample(
                user_id=s.user_id,
                item_id=item_id,
                label=1.0  # تفاعل إيجابي قوي
            ))
    
    print(f"\n✅ إجمالي التفاعلات: {len(interactions)}")
    return interactions


def load_embeddings_from_db():
    """
    تحميل متجهات الكتب المحسوبة مسبقاً.
    """
    print("\n📦 جاري تحميل متجهات الكتب...")
    
    item_embeddings = {}
    
    embeddings = BookEmbedding.query.all()
    for emb in embeddings:
        book = Book.query.get(emb.book_id)
        if book and emb.vector is not None:
            item_id = book.google_id or f"book_{book.id}"
            vector = np.array(emb.vector, dtype=np.float32)
            
            # التأكد من أن البعد صحيح
            if len(vector.shape) == 1:
                item_embeddings[item_id] = vector
    
    print(f"✅ تم تحميل {len(item_embeddings)} متجه")
    
    # استخراج البعد
    if item_embeddings:
        sample_vec = list(item_embeddings.values())[0]
        print(f"📏 بُعد المتجهات: {len(sample_vec)}")
    
    return item_embeddings


def create_user_embeddings(interactions, item_embeddings, target_dim=None):
    """
    إنشاء متجهات المستخدمين من متوسط متجهات الكتب التي تفاعلوا معها.
    """
    print("\n👤 جاري إنشاء متجهات المستخدمين...")
    
    from collections import defaultdict
    
    # تحديد البعد المطلوب
    if target_dim is None and item_embeddings:
        # استخدام أول متجه لتحديد البعد
        target_dim = len(list(item_embeddings.values())[0])
    
    # فلترة الـ item_embeddings ليكون لها نفس البعد
    filtered_embeddings = {
        k: v for k, v in item_embeddings.items() 
        if len(v) == target_dim
    }
    
    print(f"  - البعد المستهدف: {target_dim}")
    print(f"  - عدد الكتب بنفس البعد: {len(filtered_embeddings)}")
    
    user_items = defaultdict(list)
    for inter in interactions:
        if inter.label > 0.5 and inter.item_id in filtered_embeddings:
            user_items[inter.user_id].append(filtered_embeddings[inter.item_id])
    
    user_embeddings = {}
    for user_id, vectors in user_items.items():
        if vectors:
            avg_vec = np.mean(vectors, axis=0).astype(np.float32)
            user_embeddings[user_id] = avg_vec
    
    print(f"✅ تم إنشاء متجهات لـ {len(user_embeddings)} مستخدم")
    return user_embeddings, target_dim, filtered_embeddings


def main():
    # إنشاء Flask app وسياق التطبيق
    app = create_app()
    
    with app.app_context():
        print("="*60)
        print("🎓 بدء عملية التدريب على البيانات الحقيقية")
        print("="*60)
        
        # 1. تحميل البيانات
        interactions = load_interactions_from_db()
        
        if len(interactions) < 10:
            print("\n⚠️ عدد التفاعلات قليل جداً للتدريب!")
            print("💡 جرب إضافة المزيد من التقييمات والمشاهدات في التطبيق أولاً.")
            return
        
        # 2. تحميل المتجهات
        item_embeddings = load_embeddings_from_db()
        
        if len(item_embeddings) < 5:
            print("\n⚠️ عدد متجهات الكتب قليل!")
            print("💡 تحتاج لتشغيل عملية حساب embeddings أولاً.")
            
            # إنشاء متجهات عشوائية للتجربة
            print("🔄 سيتم إنشاء متجهات عشوائية للتجربة...")
            unique_items = set(i.item_id for i in interactions)
            for item_id in unique_items:
                if item_id not in item_embeddings:
                    item_embeddings[item_id] = np.random.randn(384).astype(np.float32)
        
        # 3. إنشاء متجهات المستخدمين (مع التأكد من تناسق الأبعاد)
        user_embeddings, embedding_dim, item_embeddings = create_user_embeddings(interactions, item_embeddings)
        
        # 4. تصفية التفاعلات - فقط التي لها user و item embeddings
        print("\n🔍 تصفية التفاعلات...")
        valid_interactions = []
        for inter in interactions:
            if inter.user_id in user_embeddings and inter.item_id in item_embeddings:
                valid_interactions.append(inter)
        
        print(f"  - تفاعلات صالحة (لها embeddings): {len(valid_interactions)} من {len(interactions)}")
        
        if len(valid_interactions) < 10:
            print("\n⚠️ عدد التفاعلات الصالحة قليل جداً!")
            print("💡 تحتاج لمزيد من البيانات أو حساب المزيد من embeddings.")
            return
        
        interactions = valid_interactions
        
        # 5. تقسيم البيانات
        np.random.shuffle(interactions)
        split_idx = int(0.8 * len(interactions))
        train_data = interactions[:split_idx]
        val_data = interactions[split_idx:]
        
        print(f"\n📊 تقسيم البيانات:")
        print(f"  - بيانات التدريب: {len(train_data)}")
        print(f"  - بيانات التحقق: {len(val_data)}")
        
        # 5. إنشاء DataLoaders
        train_loader, val_loader = create_data_loaders(
            train_data=train_data,
            val_data=val_data,
            user_embeddings=user_embeddings,
            item_embeddings=item_embeddings,
            batch_size=32,
            num_workers=0  # Windows fix
        )
        
        # 6. إنشاء نموذج MLP بسيط للعمل مع المتجهات المحسوبة مسبقاً
        print(f"\n🧠 إنشاء نموذج MLP (input_dim={embedding_dim})")
        
        import torch
        import torch.nn as nn
        
        class SimpleScoringModel(nn.Module):
            """نموذج بسيط لحساب التوافق بين المستخدم والكتاب"""
            def __init__(self, embedding_dim, hidden_dim=256):
                super().__init__()
                # يأخذ تمثيل المستخدم + تمثيل الكتاب
                self.scorer = nn.Sequential(
                    nn.Linear(embedding_dim * 2, hidden_dim),
                    nn.ReLU(),
                    nn.Dropout(0.3),
                    nn.Linear(hidden_dim, hidden_dim // 2),
                    nn.ReLU(),
                    nn.Dropout(0.2),
                    nn.Linear(hidden_dim // 2, 1)
                )
            
            def forward(self, user_embedding, item_embedding, **kwargs):
                combined = torch.cat([user_embedding, item_embedding], dim=-1)
                return self.scorer(combined).squeeze(-1)
        
        model = SimpleScoringModel(embedding_dim, hidden_dim=256)
        
        # 7. إعداد التدريب
        config = TrainingConfig(
            model_name="simple_recommender",
            epochs=10,
            batch_size=32,
            learning_rate=0.001,
            checkpoint_dir="instance/checkpoints",
            device="cpu"  # غيّر إلى "cuda" إذا كان لديك GPU
        )
        
        trainer = Trainer(
            model=model,
            config=config,
            train_loader=train_loader,
            val_loader=val_loader
        )
        
        # 8. بدء التدريب
        print(f"\n{'='*60}")
        print(f"🚀 بدء التدريب - {datetime.now().strftime('%H:%M:%S')}")
        print(f"{'='*60}")
        
        results = trainer.train()
        
        print(f"\n{'='*60}")
        print(f"✅ انتهى التدريب - {datetime.now().strftime('%H:%M:%S')}")
        print(f"{'='*60}")
        
        print(f"\n📈 النتائج:")
        print(f"  - أفضل أداء: {results['best_metric']:.4f}")
        print(f"  - أفضل Epoch: {results['best_epoch'] + 1}")
        print(f"  - آخر Loss: {results['final_loss']:.4f}")
        print(f"\n💾 تم حفظ النموذج في: {config.checkpoint_dir}/{config.model_name}")


if __name__ == "__main__":
    main()
