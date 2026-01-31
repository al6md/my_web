
with open('flask_book_recommendation/recommender.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

count = 0
for i, line in enumerate(lines):
    if '"""' in line:
        count += line.count('"""')
        print(f"Line {i+1}: {line.strip()} (Count: {count})")

if count % 2 != 0:
    print("ODD NUMBER OF TRIPLE QUOTES!")
else:
    print("Even number of triple quotes.")
