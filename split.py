import os

base_dir = r"c:\Users\al6md\Desktop\project alham\flask_book_recommendation_starter\flask_book_recommendation\templates"
detail_path = os.path.join(base_dir, 'public_book_detail.html')
async_path = os.path.join(base_dir, 'public_book_detail_async.html')

with open(detail_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

async_lines = lines[6:-2] # everything inside <main>

with open(async_path, 'w', encoding='utf-8') as f:
    f.writelines(async_lines)

main_content = lines[:6] + [
    '    {% if deferred_load %}\n',
    '    {% set async_url = request.full_path ~ \'&async_load=1\' if \'?\' in request.full_path else request.full_path ~ \'?async_load=1\' %}\n',
    '    <div id="book-detail-skeleton"\n',
    '         hx-get="{{ async_url }}"\n',
    '         hx-trigger="load" hx-swap="outerHTML">\n',
    '        <div class="py-40 text-center flex flex-col items-center justify-center min-h-[70vh]">\n',
    '            <div class="animate-spin rounded-full h-24 w-24 border-[6px] border-primary border-t-transparent shadow-xl mb-8"></div>\n',
    '            <h3 class="text-4xl font-black text-on-surface font-headline tracking-widest animate-pulse" dir="rtl">جاري التحليل المعرفي...</h3>\n',
    '            <p class="text-on-surface-variant font-medium opacity-60 mt-4 text-xl" dir="rtl">نستدعي محرك الذكاء الاصطناعي لاستخراج التفاصيل وبناء التوصيات</p>\n',
    '        </div>\n',
    '    </div>\n',
    '    {% else %}\n',
    '       {% include "public_book_detail_async.html" %}\n',
    '    {% endif %}\n'
] + lines[-2:]

with open(detail_path, 'w', encoding='utf-8') as f:
    f.writelines(main_content)

print('Split successful')
