import sys

file_path = r'c:\Users\al6md\Desktop\project alham\flask_book_recommendation_starter\flask_book_recommendation\templates\home.html'

with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Replace lines 248 to 344 (using 0-based index: 247 to 344)
new_lines = lines[:247] + [
    '    <div id="home-feed-container">\n',
    '       <!-- SKELETON LOADER -->\n',
    '       <div class="skeleton-feed">\n',
    '          {% for i in range(3) %}\n',
    '          <div class="mb-5">\n',
    '             <div class="d-flex justify-content-between align-items-center mb-4">\n',
    '                <div class="skeleton-pulse rounded" style="width: 200px; height: 32px;"></div>\n',
    '                <div class="skeleton-pulse rounded-pill" style="width: 80px; height: 28px;"></div>\n',
    '             </div>\n',
    '             <div class="d-flex gap-3 overflow-hidden">\n',
    '                {% for j in range(6) %}\n',
    '                <div class="skeleton-pulse rounded-4" style="min-width: 180px; height: 280px; flex-shrink: 0;"></div>\n',
    '                {% endfor %}\n',
    '             </div>\n',
    '          </div>\n',
    '          {% endfor %}\n',
    '          <style>\n',
    '            .skeleton-pulse {\n',
    '                background: linear-gradient(90deg, rgba(255,255,255,0.03) 25%, rgba(255,255,255,0.08) 50%, rgba(255,255,255,0.03) 75%);\n',
    '                background-size: 200% 100%;\n',
    '                animation: skeleton-loading 1.5s infinite;\n',
    '            }\n',
    '            @keyframes skeleton-loading {\n',
    '                0% { background-position: 200% 0; }\n',
    '                100% { background-position: -200% 0; }\n',
    '            }\n',
    '            .fadeInAnimation {\n',
    '                animation: fadeIn 0.5s ease-in;\n',
    '            }\n',
    '            @keyframes fadeIn {\n',
    '                from { opacity: 0; transform: translateY(10px); }\n',
    '                to { opacity: 1; transform: translateY(0); }\n',
    '            }\n',
    '          </style>\n',
    '       </div>\n',
    '    </div>\n'
] + lines[344:]

# Insert the fetch script at the end of the script block
script_insert_idx = -1
for i, line in enumerate(new_lines):
    if line.strip() == '})();':
        script_insert_idx = i
        break

if script_insert_idx != -1:
    fetch_script = [
        '    // Fetch async home feed\n',
        '    document.addEventListener("DOMContentLoaded", function() {\n',
        '        const feedContainer = document.getElementById("home-feed-container");\n',
        '        if (feedContainer) {\n',
        '            fetch("/api/home_feed")\n',
        '            .then(res => res.json())\n',
        '            .then(data => {\n',
        '                if(data.html) {\n',
        '                    feedContainer.innerHTML = data.html;\n',
        '                    // Initialize any tooltips inside newly loaded content\n',
        '                    var tooltipTriggerList = [].slice.call(feedContainer.querySelectorAll(\'[data-bs-toggle="tooltip"]\'));\n',
        '                    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {\n',
        '                        return new bootstrap.Tooltip(tooltipTriggerEl);\n',
        '                    });\n',
        '                }\n',
        '            })\n',
        '            .catch(err => console.error("Failed to load home feed:", err));\n',
        '        }\n',
        '    });\n'
    ]
    new_lines = new_lines[:script_insert_idx] + fetch_script + new_lines[script_insert_idx:]

with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print('Updated home.html successfully.')
