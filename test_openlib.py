import requests

def test_openlibrary():
    r = requests.get("https://openlibrary.org/subjects/scifi.json?limit=15")
    print(r.status_code)
    if r.status_code == 200:
        data = r.json()
        print(f"Total: {data.get('work_count')}")
        covers = []
        for work in data.get('works', []):
            cover_id = work.get('cover_id')
            if cover_id:
                covers.append(f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg")
        print("Covers:", covers)

def test_series():
    # Search for Harry Potter
    r = requests.get("https://openlibrary.org/search.json?q=harry+potter&limit=15")
    if r.status_code == 200:
        data = r.json()
        print(f"Total search: {data.get('numFound')}")
        covers = []
        for work in data.get('docs', []):
            cover_i = work.get('cover_i')
            if cover_i:
                covers.append(f"https://covers.openlibrary.org/b/id/{cover_i}-M.jpg")
        print("Series Covers:", covers)

if __name__ == "__main__":
    test_openlibrary()
    test_series()
