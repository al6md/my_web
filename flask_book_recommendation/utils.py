import requests
import os
import re
from dotenv import load_dotenv

# تحميل ملف .env لضمان تحميل مفاتيح API
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
dotenv_path = os.path.join(BASE_DIR, '.env')
load_dotenv(dotenv_path)

API_URL = "https://www.googleapis.com/books/v1/volumes"

# -----------------------------------------------------------
# 1. Google Books (تم الإصلاح هنا)
# -----------------------------------------------------------
def fetch_google_books(query, max_results=12, start_index=0, order_by="relevance"):
    params = {
        "q": query, "maxResults": max_results,
        "startIndex": start_index, "orderBy": order_by, "printType": "books"
    }
    try:
        r = requests.get(API_URL, params=params, timeout=5) # تقليل الوقت لـ 5 ثواني
        if r.ok:
            data = r.json()
            return data.get("items", []), data.get("totalItems", 0)
    except Exception as e:
        print(f"Google Books Error: {e}")
    
    # في حال حدوث أي خطأ أو عدم نجاح الطلب، نرجع قيم فارغة بدلاً من None
    return [], 0

def fetch_book_details(book_id, source="google"):
    """
    جلب تفاصيل الكتاب بناءً على المصدر
    """
    if source == "gutenberg":
        return fetch_gutenberg_detail(book_id)
    elif source == "archive":
        return fetch_archive_detail(book_id)
    elif source == "openlibrary":
        return fetch_openlib_detail(book_id)
    elif source == "itbook":
        return fetch_itbook_detail(book_id)
        
    # Default: Google Books
    try:
        r = requests.get(f"https://www.googleapis.com/books/v1/volumes/{book_id}")
        if r.ok:
            data = r.json()
            vol = data.get("volumeInfo", {})
            return {
                "id": data["id"],
                "title": vol.get("title", "No Title"),
                "author": vol.get("authors", ["Unknown"])[0],
                "description": vol.get("description"),
                "cover": vol.get("imageLinks", {}).get("thumbnail"),
                "preview": vol.get("previewLink"),
                "pageCount": vol.get("pageCount"),
                "rating": vol.get("averageRating"),
                "publishedDate": vol.get("publishedDate"),
                "source": "google"
            }
    except Exception as e:
        print(f"Error fetching Google book: {e}")
        
    return None


def generate_ai_description(title: str, author: str = "") -> str:
    """
    توليد وصف قصير للكتاب باستخدام AI عندما لا يتوفر وصف.
    محسّن للسرعة - يستخدم نماذج سريعة مع timeout قصير.
    """
    groq_key = os.environ.get("GROQ_API_KEY")
    gemini_key = os.environ.get("GEMINI_API_KEY")
    
    if not groq_key and not gemini_key:
        return None
    
    if not title or title in ["عنوان غير متوفر", "No Title"]:
        return None
    
    # Prompt مختصر للسرعة
    prompt = f"""اكتب وصفاً قصيراً (40-60 كلمة) لكتاب "{title}" للمؤلف {author or 'غير محدد'}. 
اكتب الوصف مباشرة بدون مقدمات."""

    # Try Groq first (أسرع بكثير!)
    if groq_key:
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {groq_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "llama-3.1-8b-instant",  # نموذج أسرع!
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.5,
                    "max_tokens": 100
                },
                timeout=4  # timeout قصير
            )
            
            if response.ok:
                data = response.json()
                desc = data["choices"][0]["message"]["content"].strip()
                print(f"[AI Desc] ✅ Generated for: {title[:25]}...")
                return desc
        except requests.exceptions.Timeout:
            print(f"[AI Desc] ⏱️ Groq timeout")
        except Exception as e:
            print(f"[AI Desc] Groq error: {e}")
    
    # Fallback to Gemini (أبطأ قليلاً)
    if gemini_key:
        try:
            response = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}",
                headers={"Content-Type": "application/json"},
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=4
            )
            
            if response.ok:
                data = response.json()
                desc = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                if desc:
                    print(f"[AI Desc] ✅ Generated (Gemini) for: {title[:25]}...")
                    return desc.strip()
        except requests.exceptions.Timeout:
            print(f"[AI Desc] ⏱️ Gemini timeout")
        except Exception as e:
            print(f"[AI Desc] Gemini error: {e}")
    
    return None

# -----------------------------------------------------------
# 2. Project Gutenberg
# -----------------------------------------------------------
def fetch_gutenberg_books(query, page=1, limit=12, **kwargs):
    api_url = "https://gutendex.com/books"
    params = {"search": query, "page": page}
    try:
        r = requests.get(api_url, params=params, timeout=10)
        if r.ok:
            results = r.json().get("results", [])
            books = []
            seen = set()
            for b in results:
                title = b.get("title", "")
                if title[:20].lower() in seen: continue
                seen.add(title[:20].lower())
                authors = ", ".join([a.get("name") for a in b.get("authors", [])])
                books.append({
                    "id": f"gut_{b.get('id')}", "title": title, "author": authors,
                    "cover": b.get("formats", {}).get("image/jpeg"), "source": "gutenberg"
                })
            return books[:limit]
    except: pass
    return []

def fetch_gutenberg_detail(gut_id):
    clean_id = gut_id.replace("gut_", "")
    try:
        r = requests.get(f"https://gutendex.com/books/{clean_id}", timeout=4)
        if r.ok:
            b = r.json()
            formats = b.get("formats", {})
            return {
                "id": gut_id, "title": b.get("title"), 
                "author": ", ".join([a.get("name") for a in b.get("authors", [])]),
                "desc": "كلاسيكيات عالمية (Public Domain).",
                "cover": formats.get("image/jpeg"),
                "preview": formats.get("text/html") or formats.get("text/plain"),
                "source": "gutenberg"
            }
    except: pass
    return None

# -----------------------------------------------------------
# 3. OpenLibrary
# -----------------------------------------------------------
def fetch_openlib_books(query, limit=12, offset=0, **kwargs):
    """جلب كتب من OpenLibrary مع تحسين جلب الأغلفة"""
    try:
        r = requests.get("https://openlibrary.org/search.json",
                 params={"q": query, "limit": limit, "offset": offset}, timeout=4)

        if r.ok:
            docs = r.json().get("docs", [])
            books = []
            for doc in docs:
                key = doc.get("key", "").replace("/works/", "")
                if not key: 
                    continue
                
                # محاولة الحصول على الغلاف بطرق متعددة
                cover = None
                
                # 1. أولاً: استخدام cover_i (الأكثر موثوقية)
                if doc.get("cover_i"):
                    cover = f"https://covers.openlibrary.org/b/id/{doc.get('cover_i')}-M.jpg"
                
                # 2. ثانياً: استخدام ISBN إذا متوفر
                elif doc.get("isbn"):
                    isbn_list = doc.get("isbn", [])
                    if isbn_list:
                        cover = f"https://covers.openlibrary.org/b/isbn/{isbn_list[0]}-M.jpg"
                
                # 3. ثالثاً: استخدام OLID (Open Library ID)
                elif doc.get("cover_edition_key"):
                    cover = f"https://covers.openlibrary.org/b/olid/{doc.get('cover_edition_key')}-M.jpg"
                
                author = doc.get("author_name")
                if isinstance(author, list): 
                    author = ", ".join(author[:2])  # أول مؤلفين فقط
                
                title = doc.get("title")
                if not title:
                    continue
                
                # صورة افتراضية إذا لم يوجد غلاف
                if not cover:
                    cover = "https://via.placeholder.com/150x200/DB4437/ffffff?text=📚+OpenLibrary"
                
                books.append({
                    "id": f"ol_{key}", 
                    "title": title, 
                    "author": author or "مؤلف غير معروف",
                    "cover": cover, 
                    "source": "openlibrary"
                })
            
            print(f"[OpenLibrary] Found {len(books)} books for '{query}'")
            return books
    except Exception as e:
        print(f"[OpenLib] Error: {e}")
    return []

def fetch_openlib_detail(ol_id):
    clean_id = ol_id.replace("ol_", "")
    try:
        r = requests.get(f"https://openlibrary.org/works/{clean_id}.json", timeout=5)
        if r.ok:
            data = r.json()
            desc = data.get("description")
            if isinstance(desc, dict): desc = desc.get("value")
            cover = f"https://covers.openlibrary.org/b/id/{data['covers'][0]}-L.jpg" if data.get("covers") else None
            return {
                "id": ol_id, "title": data.get("title"), "author": "OpenLibrary Author",
                "desc": desc or "No description.", "cover": cover,
                "preview": f"https://openlibrary.org/works/{clean_id}", "source": "openlibrary"
            }
    except: pass
    return None

# -----------------------------------------------------------
# 📚 Open Library Covers API (مجاني وعالي الجودة)
# -----------------------------------------------------------

def fetch_cover_from_openlibrary(isbn=None, title=None, author=None, size="L"):
    """
    جلب غلاف كتاب من Open Library Covers API
    
    Args:
        isbn: رقم ISBN للكتاب (أفضل طريقة)
        title: عنوان الكتاب (للبحث إذا لم يتوفر ISBN)
        author: اسم المؤلف (اختياري - يحسن نتائج البحث)
        size: حجم الصورة (S=صغير, M=متوسط, L=كبير)
    
    Returns:
        رابط الغلاف أو None
    """
    
    # 1. أولاً: البحث بـ ISBN (الأدق)
    if isbn:
        # تنظيف ISBN من الشرطات
        clean_isbn = str(isbn).replace("-", "").replace(" ", "").strip()
        if len(clean_isbn) in [10, 13]:
            cover_url = f"https://covers.openlibrary.org/b/isbn/{clean_isbn}-{size}.jpg"
            # التحقق من وجود الصورة
            if _verify_cover_exists(cover_url):
                print(f"[OpenLibrary Cover] ✅ Found by ISBN: {clean_isbn}")
                return cover_url
    
    # 2. ثانياً: البحث في OpenLibrary بالعنوان والمؤلف
    if title:
        try:
            search_query = title
            if author:
                search_query += f" {author}"
            
            params = {"q": search_query, "limit": 1}
            r = requests.get("https://openlibrary.org/search.json", params=params, timeout=5)
            
            if r.ok:
                docs = r.json().get("docs", [])
                if docs:
                    doc = docs[0]
                    
                    # محاولة 1: cover_i (ID الغلاف المباشر)
                    if doc.get("cover_i"):
                        cover_url = f"https://covers.openlibrary.org/b/id/{doc['cover_i']}-{size}.jpg"
                        print(f"[OpenLibrary Cover] ✅ Found by cover_i for '{title}'")
                        return cover_url
                    
                    # محاولة 2: ISBN من نتائج البحث
                    if doc.get("isbn"):
                        isbn_list = doc.get("isbn", [])
                        for isbn_try in isbn_list[:3]:  # نحاول أول 3 ISBNs
                            cover_url = f"https://covers.openlibrary.org/b/isbn/{isbn_try}-{size}.jpg"
                            if _verify_cover_exists(cover_url):
                                print(f"[OpenLibrary Cover] ✅ Found by search ISBN for '{title}'")
                                return cover_url
                    
                    # محاولة 3: OLID (Open Library ID)
                    if doc.get("cover_edition_key"):
                        cover_url = f"https://covers.openlibrary.org/b/olid/{doc['cover_edition_key']}-{size}.jpg"
                        print(f"[OpenLibrary Cover] ✅ Found by OLID for '{title}'")
                        return cover_url
                        
        except Exception as e:
            print(f"[OpenLibrary Cover] Search error: {e}")
    
    return None


def _verify_cover_exists(url):
    """التحقق من وجود الغلاف (لتجنب الصور الفارغة)"""
    try:
        r = requests.head(url, timeout=3)
        # OpenLibrary ترجع 200 دائماً، لكن الصورة الفارغة حجمها < 1KB
        if r.ok:
            content_length = r.headers.get("Content-Length", 0)
            return int(content_length) > 1000  # أكثر من 1KB = صورة حقيقية
    except:
        pass
    return True  # نفترض أنها موجودة إذا فشل التحقق


def get_book_cover_smart(title, author=None, isbn=None, source=None):
    """
    جلب غلاف كتاب بطريقة ذكية من مصادر متعددة
    
    يحاول من:
    1. Open Library (بـ ISBN أو بالبحث)
    2. Google Books
    3. توليد غلاف AI كـ fallback
    
    Args:
        title: عنوان الكتاب (مطلوب)
        author: اسم المؤلف (اختياري)
        isbn: رقم ISBN (اختياري)
        source: مصدر الكتاب الأصلي (اختياري)
    
    Returns:
        dict: {"cover_url": str, "source": str}
    """
    
    # 1. Open Library (الأفضل للجودة)
    ol_cover = fetch_cover_from_openlibrary(isbn=isbn, title=title, author=author)
    if ol_cover:
        return {"cover_url": ol_cover, "source": "openlibrary"}
    
    # 2. Google Books
    try:
        search_query = title
        if author:
            search_query += f" {author}"
        
        items, _ = fetch_google_books(search_query, max_results=1)
        if items:
            vi = items[0].get("volumeInfo", {}) or {}
            imgs = vi.get("imageLinks", {}) or {}
            cover = imgs.get("large") or imgs.get("medium") or imgs.get("thumbnail")
            if cover:
                if cover.startswith("http://"):
                    cover = "https://" + cover[7:]
                return {"cover_url": cover, "source": "google"}
    except Exception as e:
        print(f"[Smart Cover] Google error: {e}")
    
    # 3. AI Cover (Pollinations)
    import urllib.parse
    prompt = f"Professional book cover for '{title}'"
    if author:
        prompt += f" by {author}"
    prompt += ", elegant design, high quality"
    encoded_prompt = urllib.parse.quote(prompt)
    ai_cover = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=400&height=600&nologo=true"
    
    return {"cover_url": ai_cover, "source": "ai_generated"}


# -----------------------------------------------------------
# 4. IT Bookstore
# -----------------------------------------------------------
def fetch_itbook_detail(isbn):
    try:
        r = requests.get(f"https://api.itbook.store/1.0/books/{isbn}", timeout=5)
        if r.ok:
            data = r.json()
            return {
                "id": data.get("isbn13"), "title": data.get("title"), "author": data.get("authors"),
                "desc": data.get("desc"), "cover": data.get("image"), "preview": data.get("url"), "source": "itbook"
            }
    except: pass
    return None

# utils.py

# ... (باقي الكود في الأعلى كما هو) ...

def fetch_itbook_books(query, page=1, limit=8, **kwargs): # 👈 أضفنا متغير page
    try:
        # 👈 نضع رقم الصفحة في الرابط بدلاً من الرقم 1 الثابت
        url = f"https://api.itbook.store/1.0/search/{query}/{page}"
        r = requests.get(url, timeout=4)
        if not r.ok: return []

        data = r.json()
        books_raw = data.get("books", [])
        # هذا الـ API يعيد 10 نتائج دائماً، فنقوم بقصها حسب الـ limit
        books_raw = books_raw[:limit] 
        
        books = []
        for b in books_raw:
            isbn13 = b.get("isbn13")
            if not isbn13: continue
            title = b.get("title") or "Untitled"
            subtitle = b.get("subtitle") or ""
            author = subtitle or "IT Book"
            books.append({
                "id": isbn13, "title": title, "author": author,
                "cover": b.get("image"), "source": "itbook"
            })
        return books
    except Exception as e:
        print(f"ITBook Error: {e}")
    return []

# ... (باقي الكود في الأسفل كما هو) ...
# -----------------------------------------------------------
# 5. Archive.org
# -----------------------------------------------------------
def fetch_archive_detail(archive_id, max_results=1): # تم تعديل التوقيع ليتوافق
    # إذا تم تمرير ID كنص عادي (للبحث عن التفاصيل)
    if isinstance(archive_id, str) and not archive_id.startswith("http"):
        clean_id = archive_id.replace("arch_", "")
        url = f"https://archive.org/metadata/{clean_id}"
        try:
            r = requests.get(url, timeout=4)
            if r.ok:
                data = r.json()
                meta = data.get("metadata", {})
                if meta and meta.get("title"):
                    desc = meta.get("description", "No description available.")
                    if isinstance(desc, list):
                        desc = " ".join(desc)
                    return {
                        "id": archive_id, "title": meta.get("title"),
                        "author": meta.get("creator") if isinstance(meta.get("creator"), str) else ", ".join(meta.get("creator", [])) if meta.get("creator") else "Unknown Author",
                        "desc": desc,
                        "cover": f"https://archive.org/services/img/{clean_id}",
                        "preview": f"https://archive.org/details/{clean_id}",
                        "source": "archive"
                    }
        except Exception as e:
            print(f"[Archive Detail] Error: {e}")
        
        # Fallback: إرجاع بيانات افتراضية
        return {
            "id": archive_id, 
            "title": clean_id.replace("_", " ").replace("00", " ").title(),
            "author": "Internet Archive",
            "desc": "هذا الكتاب متوفر على Internet Archive. اضغط على معاينة للقراءة المجانية.",
            "cover": f"https://archive.org/services/img/{clean_id}",
            "preview": f"https://archive.org/details/{clean_id}",
            "source": "archive"
        }
    
    # إذا تم استخدامها للبحث (كما في book_detail سابقاً)
    return fetch_archive_books(archive_id, limit=max_results), 0

def fetch_archive_books(query, limit=12, **kwargs):
    """جلب كتب من Internet Archive مع معالجة أفضل للأخطاء"""
    base_url = "https://archive.org/advancedsearch.php"
    
    # تنظيف الاستعلام
    clean_query = query.strip()
    if not clean_query:
        clean_query = "books"
    
    # استعلام بسيط
    search_query = f"{clean_query} mediatype:texts"
    params = {
        "q": search_query, 
        "rows": limit, 
        "output": "json",
        "fl": "identifier,title,creator"
    }
    
    try:
        print(f"[Archive] Searching for: {clean_query}")
        r = requests.get(base_url, params=params, timeout=8)  # timeout سريع
        if r.ok:
            data = r.json()
            docs = data.get("response", {}).get("docs", [])
            books = []
            for doc in docs:
                identifier = doc.get("identifier")
                if not identifier:
                    continue
                title = doc.get("title")
                if not title:
                    continue
                creator = doc.get("creator", "Unknown Author")
                if isinstance(creator, list): 
                    creator = ", ".join(creator)
                books.append({
                    "id": f"arch_{identifier}", 
                    "title": title, 
                    "author": creator,
                    "cover": f"https://archive.org/services/img/{identifier}", 
                    "source": "archive"
                })
            print(f"[Archive] Found {len(books)} books for '{clean_query}'")
            if books:
                return books
    except requests.exceptions.Timeout:
        print(f"[Archive] Timeout for '{clean_query}' - using fallback")
    except Exception as e:
        print(f"[Archive] Error: {e} - using fallback")
    
    # Fallback: لا نعرض كتب عشوائية - أفضل عدم عرض شيء من عرض كتب غير متعلقة
    print(f"[Archive] ⚠️ No results for '{clean_query}' - returning empty")
    return []

# -----------------------------------------------------------
# 6. AI Helpers (Gemini)
# -----------------------------------------------------------
def analyze_search_intent_with_ai(text: str) -> dict:
    """
    تحليل نية البحث باستخدام الذكاء الاصطناعي.
    Input: "أبي روايات بوليسية تشبه شارلوك هولمز"
    Output: {"query": "sherlock holmes detective novels", "is_tech": False}
    """
    if not text or len(text.split()) < 2:
        return {"query": text, "is_tech": False}

    api_key = os.environ.get("GEMINI_API_KEY")
    groq_key = os.environ.get("GROQ_API_KEY")
    
    # Prompt محسن لاستخراج الكلمات المفتاحية
    prompt = f"""
    You are a search query optimizer for a book library.
    Convert this natural language request into a precise search query for Google Books/OpenLibrary APIs.
    
    User Request: "{text}"
    
    Rules:
    1. Extract core keywords (genre, author, topic).
    2. Keep English terms if they are better for search.
    3. Remove fluff ("I want", "books about", "please").
    4. Detect if it's a technical/programming query.
    
    Return JSON ONLY: {{"query": "keywords_here", "is_tech": boolean}}
    """
    
    try:
        # 1. محاولة استخدام Groq (أسرع)
        if groq_key:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {groq_key}"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "response_format": {"type": "json_object"}
                },
                timeout=5
            )
            if response.ok:
                data = response.json()
                content = data['choices'][0]['message']['content']
                return json.loads(content)

        # 2. Fallback إلى Gemini
        if api_key:
            response = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}",
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"response_mime_type": "application/json"}
                },
                timeout=5
            )
            if response.ok:
                data = response.json()
                text_resp = data['candidates'][0]['content']['parts'][0]['text']
                return json.loads(text_resp)
                
    except Exception as e:
        print(f"[Search Analysis] Error: {e}")
    
    # في حال الفشل، نعيد النص كما هو
    return {"query": text, "is_tech": False}

def translate_to_english_with_gemini(text: str) -> str:
    """Wrapper for backward compatibility"""
    res = analyze_search_intent_with_ai(text)
    return res.get("query", text)

def generate_reading_plan_with_ai(book_title, pages, days):
    """
    إنشاء خطة قراءة ذكية باستخدام AI
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    prompt = f"""
    Create a reading plan for book: "{book_title}" ({pages} pages) to finish in {days} days.
    
    Return JSON ONLY:
    {{
        "daily_quota": "number of pages",
        "strategy": "brief strategy advice (1 sentence)",
        "schedule": [
            {{"day": 1, "focus": "pages x-y", "tip": "brief tip"}},
            ... (for each day)
        ]
    }}
    """
    
    try:
        if api_key:
            response = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}",
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"response_mime_type": "application/json"}
                },
                timeout=8
            )
            if response.ok:
                data = response.json()
                text_resp = data['candidates'][0]['content']['parts'][0]['text']
                return json.loads(text_resp)
    except Exception as e:
        print(f"Plan error: {e}")
        
    # Fallback plan
    quota =  int(int(pages) / int(days))
    return {
        "daily_quota": quota,
        "strategy": "Consistent daily reading is key.",
        "schedule": [{"day": i+1, "focus": f"Read {quota} pages", "tip": "Keep going!"} for i in range(int(days))]
    }

def extract_quotes_with_ai(title, author):
    """
    استخراج اقتباسات ملهمة من الكتاب باستخدام AI
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    prompt = f"""
    Extract 4 short, inspiring, and beautiful quotes from the book "{title}" by {author}.
    If the exact text is not available, generate 4 quotes that capture the essence and style of the book perfectly.
    
    Return JSON ONLY:
    {{
        "quotes": [
            "Quote 1 text...",
            "Quote 2 text...",
            "Quote 3 text...",
            "Quote 4 text..."
        ]
    }}
    """
    
    try:
        if api_key:
            response = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}",
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"response_mime_type": "application/json"}
                },
                timeout=8
            )
            if response.ok:
                data = response.json()
                text_resp = data['candidates'][0]['content']['parts'][0]['text']
                return json.loads(text_resp)
    except Exception as e:
        print(f"Quote error: {e}")
        
    return {
        "quotes": [
            f"The love of books is a love which requires neither justification, apology, nor defense. - {author}",
            f"A room without books is like a body without a soul. - {title}",
            "So many books, so little time.",
            "I have always imagined that Paradise will be a kind of library."
        ]
    }

def analyze_book_mood_with_ai(title, description):
    """
    تحليل مزاج الكتاب لتفعيل وضع الانغماس
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    prompt = f"""
    Analyze the mood/atmosphere of the book "{title}": {description[:200]}...
    
    Classify into ONE of these:
    - dark (Horror, Thriller, Mystery)
    - happy (Comedy, Romance, Kids)
    - calm (Philosophy, Nature, Self-help)
    - epic (Fantasy, History, Sci-Fi)
    
    Return JSON ONLY: {{"mood": "dark|happy|calm|epic"}}
    """
    
    try:
        if api_key:
            response = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}",
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"response_mime_type": "application/json"}
                },
                timeout=5
            )
            if response.ok:
                data = response.json()
                text_resp = data['candidates'][0]['content']['parts'][0]['text']
                return json.loads(text_resp)
    except Exception as e:
        print(f"Mood error: {e}")
        
    return {"mood": "calm"}

def generate_quiz_with_ai(title, author):
    """
    Generate 5 MCQ questions about the book using AI
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    prompt = f"""
    Create a fun quiz for the book "{title}" by {author}.
    Generate 5 multiple-choice questions (MCQs).
    
    Format JSON ONLY:
    {{
        "questions": [
            {{
                "question": "Question text?",
                "options": ["A", "B", "C"],
                "correct_index": 0
            }}
        ]
    }}
    
    Make questions testing plot key points.
    Language: Arabic (Translate if needed).
    """
    
    try:
        if api_key:
            response = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}",
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"response_mime_type": "application/json"}
                },
                timeout=8
            )
            if response.ok:
                data = response.json()
                text_resp = data['candidates'][0]['content']['parts'][0]['text']
                return json.loads(text_resp)
    except Exception as e:
        print(f"Quiz error: {e}")
        
    # Fallback
    return {
        "questions": [
            {
                "question": f"من هو مؤلف كتاب {title}؟",
                "options": [author, "نجيب محفوظ", "طه حسين"],
                "correct_index": 0
            },
            {
                "question": "ما هو نوع هذا الكتاب؟",
                "options": ["رواية", "شعر", "سيرة ذاتية"],
                "correct_index": 0
            }
        ]
    }

# ... (دالة get_text_embedding اتركها كما هي) ...

import time

def get_text_embedding(text, max_retries=3):
    """
    تحويل النص إلى embedding vector باستخدام Gemini API.
    
    Args:
        text: النص المراد تحويله
        max_retries: عدد محاولات إعادة المحاولة في حال الفشل
        
    Returns:
        قائمة من الأرقام (768 بُعد) أو None في حال الفشل
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[Embedding] ⚠️ GEMINI_API_KEY not found!")
        return None
    
    if not text or not text.strip():
        return None
    
    # تنظيف النص وتقليل طوله
    clean_text = text.strip()[:2000]  # Gemini يدعم حتى 2048 حرف
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/embedding-001:embedContent?key={api_key}"
    payload = {
        "model": "models/embedding-001", 
        "content": {"parts": [{"text": clean_text}]}
    }
    
    for attempt in range(max_retries):
        try:
            response = requests.post(url, json=payload, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                embedding = data.get('embedding', {}).get('values')
                if embedding:
                    return embedding
                    
            elif response.status_code == 429:
                # Rate limit - انتظر ثم حاول مجدداً
                wait_time = (attempt + 1) * 2
                print(f"[Embedding] Rate limited, waiting {wait_time}s...")
                time.sleep(wait_time)
                continue
                
            else:
                print(f"[Embedding] API error: {response.status_code}")
                
        except requests.exceptions.Timeout:
            print(f"[Embedding] Timeout on attempt {attempt + 1}")
        except Exception as e:
            print(f"[Embedding] Error: {e}")
        
        # انتظار قبل المحاولة التالية
        if attempt < max_retries - 1:
            time.sleep(1)
    
    return None


def get_book_embedding(book):
    """
    توليد embedding لكتاب بناءً على عنوانه ومؤلفه ووصفه.
    
    Args:
        book: كائن Book من قاعدة البيانات
        
    Returns:
        embedding vector أو None
    """
    if not book:
        return None
    
    # جمع المعلومات المتاحة عن الكتاب
    parts = []
    
    if book.title:
        parts.append(f"Title: {book.title}")
    
    if book.author:
        parts.append(f"Author: {book.author}")
    
    if book.description:
        # نأخذ أول 500 حرف من الوصف
        desc = book.description[:500]
        parts.append(f"Description: {desc}")
    
    if not parts:
        return None
    
    text = ". ".join(parts)
    return get_text_embedding(text)


def generate_book_embedding_if_missing(book):
    """
    توليد وحفظ embedding للكتاب إذا لم يكن موجوداً.
    
    Args:
        book: كائن Book
        
    Returns:
        True إذا تم التوليد بنجاح، False خلاف ذلك
    """
    from .models import BookEmbedding
    from .extensions import db
    
    if not book or not book.id:
        return False
    
    # تحقق إذا كان موجوداً مسبقاً
    existing = BookEmbedding.query.filter_by(book_id=book.id).first()
    if existing and existing.vector:
        return True  # موجود مسبقاً
    
    # توليد embedding جديد
    embedding = get_book_embedding(book)
    if not embedding:
        return False
    
    try:
        if existing:
            existing.vector = embedding
        else:
            new_embed = BookEmbedding(book_id=book.id, vector=embedding)
            db.session.add(new_embed)
        
        db.session.commit()
        print(f"[Embedding] ✅ Generated for book: {book.title[:30]}...")
        return True
        
    except Exception as e:
        db.session.rollback()
        print(f"[Embedding] ❌ Failed to save: {e}")
        return False


# utils.py - أضف هذا في النهاية
import re

def normalize_text(text):
    if not text: return ""
    # تحويل النص إلى string وضمان الأحرف الصغيرة
    text = str(text).lower().strip()
    # توحيد الألف (أ إ آ -> ا)
    text = re.sub("[أإآ]", "ا", text)
    # توحيد التاء المربوطة والهاء (ة -> ه)
    text = re.sub("ة", "ه", text)
    # توحيد الياء (ى -> ي)
    text = re.sub("ى", "ي", text)
    # إزالة التشكيل (اختياري)
    text = re.sub("[\u064B-\u065F]", "", text)
    return text


# -----------------------------------------------------------
# 7. AI Chatbot للكتب (Groq + Gemini Fallback)
# -----------------------------------------------------------

def chat_with_ai(user_message: str, user_context: dict = None) -> dict:
    """
    مساعد AI ذكي للكتب يجيب على أسئلة المستخدمين ويقدم توصيات.
    يستخدم Groq API (مجاني وسريع) كأولوية أولى.
    
    Args:
        user_message: رسالة المستخدم
        user_context: سياق إضافي (اهتمامات، كتب سابقة، إلخ)
        
    Returns:
        قاموس يحتوي على رد AI وتوصيات الكتب
    """
    
    if not user_message or not user_message.strip():
        return {
            "reply": "مرحباً! كيف يمكنني مساعدتك في اختيار كتاب؟",
            "books": [],
            "search_query": None
        }
    
    # بناء السياق
    context_info = ""
    if user_context:
        if user_context.get("interests"):
            context_info += f"\nاهتمامات المستخدم: {', '.join(user_context['interests'])}"
        if user_context.get("recent_books"):
            context_info += f"\nآخر الكتب التي اطلع عليها: {', '.join(user_context['recent_books'])}"
    
    # بناء الـ prompt
    system_prompt = """أنت مساعد ذكي متخصص في الكتب واسمك "مكتبي". مهمتك:
1. فهم ما يبحث عنه المستخدم من كتب
2. تقديم توصيات مفيدة ومحددة
3. الإجابة على أسئلة عن الكتب والقراءة

قواعد مهمة:
- كن ودوداً ومختصراً (جملتين إلى 3 جمل كحد أقصى)
- إذا طلب المستخدم كتاباً، استخرج الموضوع الرئيسي للبحث
- رد بالعربية دائماً
- أضف إيموجي واحد مناسب

في نهاية ردك، اكتب في سطر جديد:
SEARCH_QUERY: [كلمات البحث بالإنجليزية للموضوع المطلوب]

مثال:
المستخدم: أريد كتاب عن الذكاء الاصطناعي
الرد: مجال رائع! 🤖 الذكاء الاصطناعي من أهم مجالات العصر. سأبحث لك عن أفضل الكتب.
SEARCH_QUERY: Artificial Intelligence books"""

    full_prompt = f"{system_prompt}{context_info}\n\nالمستخدم: {user_message}"
    
    # محاولة 1: Groq API (مجاني وسريع)
    groq_key = os.environ.get("GROQ_API_KEY")
    if groq_key:
        result = _call_groq_api(groq_key, full_prompt)
        if result:
            return _process_ai_response(result)
    
    # محاولة 2: Gemini API (fallback)
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        result = _call_gemini_api(gemini_key, full_prompt)
        if result:
            return _process_ai_response(result)
    
    # لا يوجد مفتاح متاح
    return {
        "reply": "عذراً، المساعد غير متاح حالياً. يرجى إضافة مفتاح API في الإعدادات.",
        "books": [],
        "search_query": None
    }


def _call_groq_api(api_key: str, prompt: str) -> str:
    """استدعاء Groq API - مجاني وسريع جداً"""
    url = "https://api.groq.com/openai/v1/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # قائمة النماذج المدعومة للمحاولة
    models = ["llama-3.3-70b-versatile", "mixtral-8x7b-32768"]
    
    payload = {
        "model": "llama-3.3-70b-versatile",  # النموذج الأحدث والأسرع
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 300
    }
    
    try:
        print("[AI Chat] Using Groq API...")
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            try:
                ai_text = data['choices'][0]['message']['content'].strip()
                print(f"[AI Chat] Groq success!")
                return ai_text
            except (KeyError, IndexError) as e:
                print(f"[AI Chat] Groq parsing error: {e}")
                return None
                
        elif response.status_code == 429:
            print("[AI Chat] Groq rate limited, trying fallback...")
            return None
        else:
            print(f"[AI Chat] Groq error: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"[AI Chat] Groq exception: {e}")
        return None


def _call_gemini_api(api_key: str, prompt: str) -> str:
    """استدعاء Gemini API كـ fallback"""
    # استخدام 1.5-flash المتوفر والمستقر
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 200
        }
    }
    
    try:
        print("[AI Chat] Using Gemini API (fallback)...")
        response = requests.post(url, json=payload, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            try:
                # التحقق الآمن من وجود المرشحات
                candidates = data.get('candidates', [])
                if not candidates:
                    print("[AI Chat] Gemini returned no candidates (Safety filter?)")
                    return None
                    
                parts = candidates[0].get('content', {}).get('parts', [])
                if not parts:
                    return None
                    
                ai_text = parts[0].get('text', '').strip()
                print(f"[AI Chat] Gemini success!")
                return ai_text
            except (KeyError, IndexError, AttributeError) as e:
                print(f"[AI Chat] Gemini parsing error: {e}")
                return None
        elif response.status_code == 429:
            print("[AI Chat] Gemini rate limited")
            return None
        else:
            print(f"[AI Chat] Gemini error: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        print(f"[AI Chat] Gemini exception: {e}")
        return None


def _process_ai_response(ai_text: str) -> dict:
    """معالجة رد AI واستخراج الكتب"""
    # استخراج query البحث
    search_query = None
    reply = ai_text
    
    if "SEARCH_QUERY:" in ai_text:
        parts = ai_text.split("SEARCH_QUERY:")
        reply = parts[0].strip()
        if len(parts) > 1:
            search_query = parts[1].strip()
    
    # جلب كتب إذا وجد query
    books = []
    if search_query:
        try:
            items, _ = fetch_google_books(search_query, max_results=6)
            for item in items[:6]:
                vi = item.get("volumeInfo", {}) or {}
                imgs = vi.get("imageLinks", {}) or {}
                cover = imgs.get("thumbnail", "")
                if cover.startswith("http://"):
                    cover = "https://" + cover[7:]
                
                books.append({
                    "id": item.get("id"),
                    "title": vi.get("title"),
                    "author": ", ".join(vi.get("authors", [])) if vi.get("authors") else "",
                    "cover": cover,
                    "source": "google"
                })
        except Exception as e:
            print(f"[AI Chat] Book fetch error: {e}")
    
    return {
        "reply": reply,
        "books": books,
        "search_query": search_query
    }


# -----------------------------------------------------------
# 📝 ملخص AI للكتب
# -----------------------------------------------------------
def generate_book_summary(book_info: dict) -> dict:
    """
    توليد ملخص ذكي للكتاب باستخدام Groq (أو Gemini كاحتياطي)
    
    Args:
        book_info: قاموس يحتوي معلومات الكتاب (title, author, description, categories)
    
    Returns:
        قاموس يحتوي {"success": bool, "summary": str, "error": str}
    """
    import json
    
    groq_key = os.environ.get("GROQ_API_KEY")
    gemini_key = os.environ.get("GEMINI_API_KEY")
    
    if not groq_key and not gemini_key:
        return {"success": False, "summary": "", "error": "لا يوجد مفتاح API متاح"}
    
    # تجميع معلومات الكتاب
    title = book_info.get("title", "غير معروف")
    author = book_info.get("author", "غير معروف")
    description = book_info.get("description", "")
    categories = book_info.get("categories", "")
    
    prompt = f"""أنت ناقد أدبي محترف. قم بكتابة ملخص شامل وجذاب لهذا الكتاب:

📚 عنوان الكتاب: {title}
✍️ المؤلف: {author}
📂 التصنيف: {categories}
📝 الوصف الأصلي: {description[:500] if description else 'غير متوفر'}

اكتب ملخصاً باللغة العربية يتضمن:
1. موضوع الكتاب الرئيسي (2-3 جمل)
2. الأفكار الرئيسية المتوقعة (3-4 نقاط)
3. الفئة المستهدفة من القراء

اجعل الملخص جذاباً ومختصراً (150-200 كلمة كحد أقصى).
لا تذكر أنك ذكاء اصطناعي، اكتب كأنك خبير في الكتب."""

    # محاولة Groq أولاً
    if groq_key:
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {groq_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7,
                    "max_tokens": 500
                },
                timeout=30
            )
            
            if response.ok:
                data = response.json()
                summary = data["choices"][0]["message"]["content"].strip()
                return {"success": True, "summary": summary, "error": ""}
            else:
                print(f"[AI Summary] Groq error: {response.status_code}")
        except Exception as e:
            print(f"[AI Summary] Groq exception: {e}")
    
    # Fallback إلى Gemini
    if gemini_key:
        try:
            response = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}",
                headers={"Content-Type": "application/json"},
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=30
            )
            
            if response.ok:
                data = response.json()
                summary = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                if summary:
                    return {"success": True, "summary": summary.strip(), "error": ""}
        except Exception as e:
            print(f"[AI Summary] Gemini exception: {e}")
    
    return {"success": False, "summary": "", "error": "تعذر توليد الملخص"}


# -----------------------------------------------------------
# 🎯 لماذا قد يعجبك هذا الكتاب
# -----------------------------------------------------------
def generate_why_you_like(book_info: dict, user_context: dict) -> dict:
    """
    تحليل لماذا قد يعجب هذا الكتاب المستخدم بناءً على اهتماماته
    
    Args:
        book_info: معلومات الكتاب
        user_context: سياق المستخدم (interests, recent_books, favorite_genres)
    
    Returns:
        قاموس يحتوي {"success": bool, "analysis": str, "error": str}
    """
    import json
    
    groq_key = os.environ.get("GROQ_API_KEY")
    gemini_key = os.environ.get("GEMINI_API_KEY")
    
    if not groq_key and not gemini_key:
        return {"success": False, "analysis": "", "error": "لا يوجد مفتاح API متاح"}
    
    # معلومات الكتاب
    title = book_info.get("title", "غير معروف")
    author = book_info.get("author", "غير معروف")
    description = book_info.get("description", "")
    categories = book_info.get("categories", "")
    
    # سياق المستخدم
    interests = user_context.get("interests", [])
    recent_books = user_context.get("recent_books", [])
    favorite_genres = user_context.get("favorite_genres", [])
    
    prompt = f"""أنت مستشار قراءة شخصي ذكي. حلل هذا الكتاب واشرح للقارئ لماذا قد يناسبه:

📚 الكتاب:
- العنوان: {title}
- المؤلف: {author}
- التصنيف: {categories}
- الوصف: {description[:300] if description else 'غير متوفر'}

👤 ملف القارئ:
- الاهتمامات: {', '.join(interests) if interests else 'متنوعة'}
- الكتب الأخيرة: {', '.join(recent_books[:5]) if recent_books else 'لم يُحدد'}
- الأنواع المفضلة: {', '.join(favorite_genres) if favorite_genres else 'متنوعة'}

اكتب تحليلاً شخصياً باللغة العربية يوضح:
1. 🎯 نقاط التوافق بين الكتاب واهتمامات القارئ
2. ✨ ما الذي سيستفيده القارئ من هذا الكتاب
3. 💡 لماذا هذا الوقت مناسب لقراءته

اجعل التحليل شخصياً وحميمياً كأنك صديق يقترح كتاباً (100-150 كلمة).
ابدأ مباشرة بالتحليل بدون مقدمات."""

    # محاولة Groq أولاً
    if groq_key:
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {groq_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.8,
                    "max_tokens": 400
                },
                timeout=30
            )
            
            if response.ok:
                data = response.json()
                analysis = data["choices"][0]["message"]["content"].strip()
                return {"success": True, "analysis": analysis, "error": ""}
            else:
                print(f"[AI WhyLike] Groq error: {response.status_code}")
        except Exception as e:
            print(f"[AI WhyLike] Groq exception: {e}")
    
    # Fallback إلى Gemini
    if gemini_key:
        try:
            response = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}",
                headers={"Content-Type": "application/json"},
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=30
            )
            
            if response.ok:
                data = response.json()
                analysis = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                if analysis:
                    return {"success": True, "analysis": analysis.strip(), "error": ""}
        except Exception as e:
            print(f"[AI WhyLike] Gemini exception: {e}")
    
    return {"success": False, "analysis": "", "error": "تعذر توليد التحليل"}


# -----------------------------------------------------------
# 📅 خطة القراءة الذكية
# -----------------------------------------------------------
def generate_reading_plan(book_info: dict, days: int = 7) -> dict:
    """
    توليد خطة قراءة ذكية للكتاب
    """
    groq_key = os.environ.get("GROQ_API_KEY")
    gemini_key = os.environ.get("GEMINI_API_KEY")
    
    if not groq_key and not gemini_key:
        return {"success": False, "plan": "", "error": "لا يوجد مفتاح API متاح"}
        
    title = book_info.get("title", "كتاب")
    pages = book_info.get("pageCount", 0)
    
    if not pages or pages == 0:
        pages = "غير محدد (افترض متوسط 300 صفحة)"
    
    prompt = f"""قم بإنشاء خطة قراءة لمدة {days} أيام لهذا الكتاب:
    
- الكتاب: {title}
- عدد الصفحات: {pages}

المطلوب: جدول markdown بسيط يوضح ماذا أقرأ كل يوم.
اجعل الخطة مشجعة وعملية.
Format:
| اليوم | الصفحات | الهدف |
|-------|---------|-------|
...
"""

    # ... (نفس منطق الاستدعاء لـ Groq/Gemini مثل الدوال السابقة)
    # للاختصار سأستخدم دالة مساعدة داخلية لو كان ممكناً، لكن سأكرر الكود للأسف لضمان الاستقلالية
    import requests
    
    # Try Groq
    if groq_key:
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {groq_key}"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.5
                },
                timeout=30
            )
            if response.ok:
                return {"success": True, "plan": response.json()["choices"][0]["message"]["content"], "error": ""}
        except: pass
        
    # Try Gemini
    if gemini_key:
        try:
            response = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}",
                headers={"Content-Type": "application/json"},
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=30
            )
            if response.ok:
                text = response.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                if text: return {"success": True, "plan": text, "error": ""}
        except: pass

    return {"success": False, "error": "AI unavailable"}


# -----------------------------------------------------------
# 🗣️ التحدث مع الكتاب
# -----------------------------------------------------------
def chat_with_book_context(book_info: dict, user_msg: str, history: list = None) -> dict:
    """
    الدردشة مع سياق الكتاب (يتقمص الـ AI دور الكتاب/المؤلف)
    """
    groq_key = os.environ.get("GROQ_API_KEY")
    gemini_key = os.environ.get("GEMINI_API_KEY")
    
    if not groq_key and not gemini_key:
        return {"success": False, "reply": "عذراً، خدمة الذكاء الاصطناعي غير متوفرة.", "error": "No API Key"}
        
    title = book_info.get("title", "")
    author = book_info.get("author", "")
    desc = book_info.get("description", "")
    
    system_prompt = f"""أنت الآن تتقمص شخصية هذا الكتاب أو مؤلفه:
العنوان: {title}
المؤلف: {author}
الوصف: {desc[:500]}

تعليمات:
1. أجب عن أسئلة المستخدم بصيغة المتكلم (أنا الكتاب/المؤلف).
2. استخدم المعلومات المتوفرة عن الكتاب للإجابة.
3. كن ودوداً وعميقاً في إجاباتك.
4. تحدث باللغة العربية.
"""
    
    messages = [{"role": "system", "content": system_prompt}]
    
    # إضافة السجل السابق (آخر 4 رسائل)
    if history:
        for msg in history[-4:]:
            role = "user" if msg.get("is_user") else "assistant"
            messages.append({"role": role, "content": msg.get("text", "")})
            
    messages.append({"role": "user", "content": user_msg})
    
    import requests
    
    # Groq First
    if groq_key:
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {groq_key}"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": messages,
                    "temperature": 0.7
                }, 
                timeout=30
            )
            if response.ok:
                return {"success": True, "reply": response.json()["choices"][0]["message"]["content"], "error": ""}
        except Exception as e: print(f"Book Chat Groq Error: {e}")

    # Gemini Fallback (Simplified, no history in same format easily, just prompt)
    if gemini_key:
        try:
            # Combine for Gemini (since it's stateless here effectively unless we construct chat structure)
            full_prompt = system_prompt + "\n\n"
            if history:
                for h in history[-4:]:
                    role = "User" if h.get("is_user") else "Book"
                    full_prompt += f"{role}: {h.get('text')}\n"
            full_prompt += f"User: {user_msg}\nBook:"
            
            response = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}",
                headers={"Content-Type": "application/json"},
                json={"contents": [{"parts": [{"text": full_prompt}]}]},
                timeout=30
            )
            if response.ok:
                if text: return {"success": True, "reply": text, "error": ""}
        except Exception as e: print(f"Book Chat Gemini Error: {e}")

    return {"success": False, "reply": "عذراً، حدث خطأ أثناء الاتصال بالكتاب.", "error": "Failed"}


# -----------------------------------------------------------
# 🧠 مسابقة الكتاب
# -----------------------------------------------------------
def generate_book_quiz(book_info: dict) -> dict:
    """
    توليد أسئلة اختبار قصيرة من محتوى الكتاب
    """
    groq_key = os.environ.get("GROQ_API_KEY")
    gemini_key = os.environ.get("GEMINI_API_KEY")
    
    if not groq_key and not gemini_key:
        return {"success": False, "quiz": [], "error": "No API Key"}
        
    title = book_info.get("title", "")
    desc = book_info.get("description", "")
    
    prompt = f"""Generate a short 3-question quiz (JSON format) about this book concept/genre:
Title: {title}
Description: {desc[:800]}

Format Requirements:
- Output ONLY valid JSON list.
- Each item: {{"question": "...", "options": ["A", "B", "C", "D"], "answer": "The correct option text"}}
- Language: Arabic.
- Questions should be general enough to be answerable from the distinct description or general knowledge about this famous book (if famous). If obscure, base it strictly on description.
"""
    
    import requests
    import json
    import re

    def parse_quiz_json(text):
        try:
            # Extract JSON array
            match = re.search(r'\[.*\]', text, re.DOTALL)
            if match:
                return json.loads(match.group())
            return json.loads(text)
        except:
            return []

    # Try Groq
    if groq_key:
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {groq_key}"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.5
                },
                timeout=30
            )
            if response.ok:
                content = response.json()["choices"][0]["message"]["content"]
                quiz = parse_quiz_json(content)
                if quiz: return {"success": True, "quiz": quiz, "error": ""}
        except Exception as e: print(f"Quiz Groq Error: {e}")

    # Try Gemini
    if gemini_key:
        try:
            response = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}",
                headers={"Content-Type": "application/json"},
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=30
            )
            if response.ok:
                text = response.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                quiz = parse_quiz_json(text)
                if quiz: return {"success": True, "quiz": quiz, "error": ""}
        except: pass

    return {"success": False, "quiz": [], "error": "Failed to generate"}


# -----------------------------------------------------------
# 📜 اقتباسات ذكية
# -----------------------------------------------------------
def extract_book_quotes(book_info: dict) -> dict:
    """
    استخراج اقتباسات ملهمة من الكتاب
    """
    groq_key = os.environ.get("GROQ_API_KEY")
    gemini_key = os.environ.get("GEMINI_API_KEY")
    
    if not groq_key and not gemini_key:
        return {"success": False, "quotes": [], "error": "No API Key"}
        
    title = book_info.get("title", "")
    author = book_info.get("author", "")
    
    prompt = f"""Extract or generate 3 inspiring quotes (Arabic) attributed to the book "{title}" by {author}.
Format: JSON list of strings ["Quote 1", "Quote 2", "Quote 3"].
If the book is not famous, generate quotes reflecting its likely themes based on title.
"""

    import requests
    import json
    import re
    
    def parse_quotes_json(text):
        try:
            match = re.search(r'\[.*\]', text, re.DOTALL)
            if match: return json.loads(match.group())
            return []
        except: return []

    # Try Groq
    if groq_key:
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {groq_key}"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.6
                },
                timeout=30
            )
            if response.ok:
                content = response.json()["choices"][0]["message"]["content"]
                quotes = parse_quotes_json(content)
                if quotes: return {"success": True, "quotes": quotes}
        except: pass
        
    # Try Gemini
    if gemini_key:
        try:
            response = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}",
                headers={"Content-Type": "application/json"},
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=30
            )
            if response.ok:
                text = response.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                quotes = parse_quotes_json(text)
                if quotes: return {"success": True, "quotes": quotes}
        except: pass

    return {"success": False, "quotes": [], "error": "Failed"}


# -----------------------------------------------------------
# 📊 تحليل عادات القراءة
# -----------------------------------------------------------
def analyze_reading_habits(user_id: int) -> dict:
    """
    تحليل شامل لعادات القراءة للمستخدم مع نصائح AI
    """
    from .models import BookStatus, UserRatingCF, BookReview, Book, SearchHistory
    from .extensions import db
    from sqlalchemy import func
    from datetime import datetime, timedelta
    
    stats = {
        "total_books": 0,
        "finished_books": 0,
        "favorite_books": 0,
        "later_books": 0,
        "average_rating": 0,
        "total_reviews": 0,
        "recent_searches": 0,
        "top_genres": [],
        "monthly_activity": [],
        "ai_tips": []
    }
    
    try:
        # إحصائيات الكتب
        stats["total_books"] = Book.query.filter_by(owner_id=user_id).count()
        
        # حالات الكتب
        statuses = BookStatus.query.filter_by(user_id=user_id).all()
        for s in statuses:
            if s.status == "finished": stats["finished_books"] += 1
            elif s.status == "favorite": stats["favorite_books"] += 1
            elif s.status == "later": stats["later_books"] += 1
        
        # متوسط التقييمات
        avg_rating = db.session.query(func.avg(UserRatingCF.rating)).filter_by(user_id=user_id).scalar()
        stats["average_rating"] = round(avg_rating, 1) if avg_rating else 0
        
        # عدد المراجعات
        stats["total_reviews"] = BookReview.query.filter_by(user_id=user_id).count()
        
        # عمليات البحث الأخيرة (آخر 30 يوم)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        stats["recent_searches"] = SearchHistory.query.filter(
            SearchHistory.user_id == user_id,
            SearchHistory.created_at >= thirty_days_ago
        ).count()
        
        # النشاط الشهري (آخر 6 أشهر)
        for i in range(6):
            month_start = datetime.utcnow().replace(day=1) - timedelta(days=30*i)
            month_end = month_start + timedelta(days=30)
            count = BookStatus.query.filter(
                BookStatus.user_id == user_id,
                BookStatus.status == "finished",
                BookStatus.created_at >= month_start,
                BookStatus.created_at < month_end
            ).count()
            stats["monthly_activity"].append({
                "month": month_start.strftime("%b"),
                "count": count
            })
        stats["monthly_activity"].reverse()
        
        # توليد نصائح AI
        stats["ai_tips"] = _generate_reading_tips(stats)
        
    except Exception as e:
        print(f"Reading Analytics Error: {e}")
    
    return {"success": True, "stats": stats}


def _generate_reading_tips(stats: dict) -> list:
    """توليد نصائح مخصصة بناءً على الإحصائيات"""
    tips = []
    
    if stats["finished_books"] == 0:
        tips.append("📚 ابدأ بإنهاء كتاب واحد هذا الأسبوع!")
    elif stats["finished_books"] < 5:
        tips.append("🎯 أنت على المسار الصحيح! حاول إنهاء كتاب إضافي هذا الشهر.")
    else:
        tips.append("🌟 قارئ نشط! استمر في هذا المعدل الرائع.")
    
    if stats["later_books"] > 10:
        tips.append("📖 لديك قائمة انتظار طويلة! حاول تحديد الأولويات.")
    
    if stats["average_rating"] > 4:
        tips.append("💡 ذوقك في الكتب ممتاز! جرب استكشاف أنواع جديدة.")
    elif stats["average_rating"] > 0 and stats["average_rating"] < 3:
        tips.append("🔍 حاول البحث عن توصيات مخصصة لاهتماماتك.")
    
    if stats["total_reviews"] == 0:
        tips.append("✍️ شارك رأيك! كتابة المراجعات تساعد الآخرين.")
    
    return tips


# -----------------------------------------------------------
# 🎨 توليد غلاف AI
# -----------------------------------------------------------
def generate_ai_cover(book_info: dict) -> dict:
    """
    توليد غلاف فني للكتاب باستخدام Pollinations.ai (مجاني)
    """
    import urllib.parse
    
    title = book_info.get("title", "Book")
    author = book_info.get("author", "")
    description = book_info.get("description", "")[:200]
    
    # بناء prompt للصورة
    prompt = f"Book cover art for '{title}'"
    if author:
        prompt += f" by {author}"
    prompt += ". Professional book cover design, artistic, high quality, detailed illustration"
    
    # إضافة سياق من الوصف
    if "fiction" in description.lower() or "novel" in description.lower():
        prompt += ", fantasy elements, dramatic lighting"
    elif "science" in description.lower() or "programming" in description.lower():
        prompt += ", modern tech aesthetic, clean design"
    elif "history" in description.lower():
        prompt += ", historical elements, vintage style"
    else:
        prompt += ", elegant typography, minimalist"
    
    # Pollinations.ai URL (مجاني بدون API Key)
    encoded_prompt = urllib.parse.quote(prompt)
    image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=400&height=600&nologo=true"
    
    return {
        "success": True,
        "cover_url": image_url,
        "prompt": prompt
    }

