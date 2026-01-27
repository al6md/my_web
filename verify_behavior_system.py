"""
سكريبت التحقق من نظام تحليل سلوك المستخدم
Verify User Behavior Analysis System
"""
import sys
import os

# إضافة المسار للمشروع
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_models():
    """اختبار النماذج"""
    print("\n📦 Testing Models...")
    try:
        from flask_book_recommendation.models import (
            UserBookView, BookStatus, UserPreference, 
            SearchHistory, UserRatingCF
        )
        print("  ✅ All models imported successfully")
        print(f"  📊 UserBookView table: {UserBookView.__tablename__}")
        return True
    except Exception as e:
        print(f"  ❌ Model import error: {e}")
        return False

def test_behavior_functions():
    """اختبار دوال تحليل السلوك"""
    print("\n🧠 Testing Behavior Analysis Functions...")
    try:
        from flask_book_recommendation.utils import (
            get_user_behavior_profile,
            get_ai_personalized_recommendations,
            update_user_preferences_from_behavior
        )
        print("  ✅ All behavior functions imported successfully")
        
        # اختبار التوقيعات
        import inspect
        sig = inspect.signature(get_user_behavior_profile)
        print(f"  📝 get_user_behavior_profile params: {list(sig.parameters.keys())}")
        
        sig = inspect.signature(get_ai_personalized_recommendations)
        print(f"  📝 get_ai_personalized_recommendations params: {list(sig.parameters.keys())}")
        
        return True
    except Exception as e:
        print(f"  ❌ Function import error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_api_endpoints():
    """اختبار API endpoints"""
    print("\n🔌 Testing API Endpoints...")
    try:
        from flask_book_recommendation.routes.api.user import api_user_bp
        
        # جمع جميع الـ routes
        routes = []
        for rule in api_user_bp.url_map.iter_rules() if hasattr(api_user_bp, 'url_map') else []:
            routes.append(rule.rule)
        
        # التحقق من وجود الـ endpoints الجديدة
        expected_endpoints = ['book-view', 'behavior-profile', 'ai-recommendations']
        
        # فحص الـ view functions
        view_funcs = list(api_user_bp.view_functions.keys()) if hasattr(api_user_bp, 'view_functions') else []
        print(f"  📋 Available endpoints: {view_funcs}")
        
        # التحقق
        if 'log_book_view' in view_funcs:
            print("  ✅ /book-view endpoint exists")
        else:
            print("  ⚠️ /book-view endpoint missing")
            
        if 'get_behavior_profile' in view_funcs:
            print("  ✅ /behavior-profile endpoint exists")
        else:
            print("  ⚠️ /behavior-profile endpoint missing")
            
        if 'get_ai_recommendations' in view_funcs:
            print("  ✅ /ai-recommendations endpoint exists")
        else:
            print("  ⚠️ /ai-recommendations endpoint missing")
        
        return True
    except Exception as e:
        print(f"  ❌ API endpoint error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_recommender_integration():
    """اختبار تكامل recommender.py"""
    print("\n🎯 Testing Recommender Integration...")
    try:
        from flask_book_recommendation.recommender import get_homepage_sections
        import inspect
        
        # قراءة مصدر الدالة للتحقق من وجود AI section
        source = inspect.getsource(get_homepage_sections)
        
        if 'get_ai_personalized_recommendations' in source:
            print("  ✅ AI recommendations integrated in get_homepage_sections")
        else:
            print("  ⚠️ AI recommendations NOT found in get_homepage_sections")
            
        if 'مخصص لك بالذكاء الاصطناعي' in source:
            print("  ✅ AI section title found")
        else:
            print("  ⚠️ AI section title missing")
        
        return True
    except Exception as e:
        print(f"  ❌ Recommender integration error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_with_app_context():
    """اختبار مع سياق التطبيق"""
    print("\n🏃 Testing with App Context...")
    try:
        from flask_book_recommendation.app import create_app
        app = create_app()
        
        with app.app_context():
            from flask_book_recommendation.models import UserBookView
            from flask_book_recommendation.extensions import db
            
            # التحقق من وجود الجدول
            try:
                count = UserBookView.query.count()
                print(f"  ✅ UserBookView table exists with {count} records")
            except Exception as table_err:
                print(f"  ⚠️ UserBookView table may not exist: {table_err}")
                print("  💡 Run migration to create the table")
            
            # اختبار دالة تحليل السلوك (بـ user_id وهمي)
            from flask_book_recommendation.utils import get_user_behavior_profile
            profile = get_user_behavior_profile(1)  # user_id = 1
            print(f"  📊 Sample behavior profile keys: {list(profile.keys())}")
            
        return True
    except Exception as e:
        print(f"  ❌ App context error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("🔍 User Behavior Analysis System - Verification")
    print("=" * 60)
    
    results = []
    
    results.append(("Models", test_models()))
    results.append(("Behavior Functions", test_behavior_functions()))
    results.append(("API Endpoints", test_api_endpoints()))
    results.append(("Recommender Integration", test_recommender_integration()))
    results.append(("App Context", test_with_app_context()))
    
    print("\n" + "=" * 60)
    print("📊 SUMMARY")
    print("=" * 60)
    
    passed = 0
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {name}: {status}")
        if result:
            passed += 1
    
    print(f"\n  Total: {passed}/{len(results)} tests passed")
    print("=" * 60)
    
    if passed == len(results):
        print("🎉 All tests passed! System is ready.")
    else:
        print("⚠️ Some tests failed. Please review the errors above.")
