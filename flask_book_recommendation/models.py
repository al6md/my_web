from flask_login import UserMixin
from .extensions import db
from datetime import datetime


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(200), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    onboarding_completed = db.Column(db.Boolean, default=False)  # هل اختار اهتماماته؟

class Book(db.Model):
    __tablename__ = "books"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False)
    author = db.Column(db.String(300))
    description = db.Column(db.Text)
    cover_url = db.Column(db.String(1000))
    
    # --- التعديل هنا: حذفنا unique=True ---
    google_id = db.Column(db.String(128), nullable=True, index=True)
    
    file_url    = db.Column(db.String(1024))
    owner_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    owner = db.relationship("User", backref=db.backref("books", lazy="dynamic"))

    # --- إضافة شرط مركب: يمنع المستخدم نفسه من إضافة الكتاب مرتين، لكن يسمح لغيره ---
    __table_args__ = (
        db.UniqueConstraint('owner_id', 'google_id', name='uq_owner_book'),
    )

class Genre(db.Model):
    __tablename__ = "genres"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)

class UserGenre(db.Model):
    __tablename__ = "user_genres"
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    genre_id = db.Column(db.Integer, db.ForeignKey("genres.id"), primary_key=True)

class BookGenre(db.Model):
    __tablename__ = "book_genres"
    book_id = db.Column(db.Integer, db.ForeignKey("books.id"), primary_key=True)
    genre_id = db.Column(db.Integer, db.ForeignKey("genres.id"), primary_key=True)

class SearchEvent(db.Model):
    __tablename__ = "search_events"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, index=True, nullable=True)
    query = db.Column(db.String(255), nullable=False)
    topics = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

class UserPreference(db.Model):
    __tablename__ = "user_preferences"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, index=True, nullable=False)
    topic = db.Column(db.String(80), index=True, nullable=False)
    weight = db.Column(db.Float, default=1.0)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('user_id', 'topic', name='uq_user_topic'),)

class PublicRating(db.Model):
    __tablename__ = "public_ratings"
    id = db.Column(db.Integer, primary_key=True)
    google_id = db.Column(db.String(64), index=True, nullable=False)
    user_id = db.Column(db.Integer, nullable=True)
    stars = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

class UserRatingCF(db.Model):
    __tablename__ = "user_ratings_cf"

    id        = db.Column(db.Integer, primary_key=True)
    user_id   = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    google_id = db.Column(db.String(128), nullable=False, index=True) 
    rating    = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    user = db.relationship("User", backref=db.backref("ratings_cf", lazy="dynamic"))

    __table_args__ = (
        db.UniqueConstraint("user_id", "google_id", name="uq_user_google_cf"),
        db.Index("idx_user_rating", "user_id", "rating"),
        db.Index("idx_google_rating", "google_id", "rating"),
    )

    def __repr__(self) -> str:
        return f"<UserRatingCF user={self.user_id} google_id={self.google_id} rating={self.rating}>"

class SearchHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id'), nullable=True, index=True)
    query = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    user = db.relationship('User', backref='search_history')
    book = db.relationship('Book')
    
    __table_args__ = (
        db.Index("idx_user_created", "user_id", "created_at"),
    )

class BookEmbedding(db.Model):
    __tablename__ = "book_embeddings"

    id = db.Column(db.Integer, primary_key=True)
    
    # المفتاح الصحيح
    book_id = db.Column(db.Integer, db.ForeignKey("books.id"), nullable=False, unique=True, index=True)

    vector = db.Column(db.PickleType)
class BookStatus(db.Model):
    __tablename__ = "book_status"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    user = db.relationship("User", backref="book_statuses", lazy=True)

    book_id = db.Column(db.Integer, db.ForeignKey("books.id"), nullable=False, index=True)
    book = db.relationship("Book", backref="status_entries", lazy=True)

    # one of: favorite / later / finished
    status = db.Column(db.String(20), nullable=False, index=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint("user_id", "book_id", name="uq_user_book_status"),
        db.Index("idx_user_status", "user_id", "status"),
    )


class BookReview(db.Model):
    """نموذج مراجعات الكتب - يسمح للمستخدمين بتقييم الكتب وكتابة مراجعات"""
    __tablename__ = "book_reviews"

    id = db.Column(db.Integer, primary_key=True)
    
    # المستخدم الذي كتب المراجعة
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    user = db.relationship("User", backref=db.backref("reviews", lazy="dynamic"))
    
    # الكتاب (يمكن أن يكون google_id للكتب الخارجية أو book_id للمحلية)
    google_id = db.Column(db.String(128), nullable=True, index=True)
    book_id = db.Column(db.Integer, db.ForeignKey("books.id"), nullable=True, index=True)
    book = db.relationship("Book", backref=db.backref("reviews", lazy="dynamic"))
    
    # التقييم والمراجعة
    rating = db.Column(db.Integer, nullable=False)  # 1-5 نجوم
    review_text = db.Column(db.Text, nullable=True)  # نص المراجعة (اختياري)
    
    # التواريخ
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        # مستخدم واحد يمكنه كتابة مراجعة واحدة لكل كتاب
        db.UniqueConstraint("user_id", "google_id", name="uq_user_review_google"),
        db.UniqueConstraint("user_id", "book_id", name="uq_user_review_book"),
        db.Index("idx_google_rating", "google_id", "rating"),
    )

    def __repr__(self):
        return f"<BookReview user={self.user_id} rating={self.rating}>"
