from flask import Blueprint, render_template, request, make_response, redirect, url_for
from flask_login import current_user

from ..recommender import (
    get_homepage_sections,
    get_trending
)

explore_bp = Blueprint("explore", __name__, url_prefix="/explore")


@explore_bp.get("/", endpoint="index")
def index():
    hero = None
    sections = []
    
    # فحص الـ onboarding للمستخدمين المسجلين
    if current_user.is_authenticated:
        # إذا تم تخطي الـ onboarding عبر الرابط
        if request.args.get('skip_onboarding'):
            current_user.onboarding_completed = True
            from ..extensions import db
            db.session.commit()
        # إذا لم يكمل الـ onboarding، وجهه لصفحة الاهتمامات
        elif not current_user.onboarding_completed:
            return redirect(url_for("auth.onboarding"))
    
    if not current_user.is_authenticated:
        trending_books = get_trending(13)  # +1 for hero
        if trending_books:
            hero = trending_books[0]

        sections = [{
            "title": "🔥 الرائج الآن",
            "subtitle": "الأكثر انتشاراً في المكتبات",
            "books": trending_books[1:] if trending_books else [],
            "style": "dark"
        }]
    else:
        # مستخدم مسجل → توصيات كاملة مثل Netflix/Amazon

        # التحقق من وجود استعلام بحث حديث لتحديث التوصيات
        # هذا سيساعد في ربط عمليات البحث مباشرة بالتوصيات المعروضة
        from_search_query = request.args.get('from_search')
        sections = get_homepage_sections(
            user_id=current_user.id,
            recent_query=from_search_query
        )

        # Use the first book of the first section as a hero
        if sections and sections[0].get("books"):
            hero = sections[0]["books"][0]
            # Remove it from the list to avoid duplication
            sections[0]["books"] = sections[0]["books"][1:]

    resp = make_response(render_template("explore.html", sections=sections, hero=hero))
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp
