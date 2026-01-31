from flask_book_recommendation.utils import fetch_book_details

gid = "NtJj0-V-DAMC"
data = fetch_book_details(gid)
print(f"ID: {gid}")
print(f"Rating: {data.get('rating')}")
print(f"Type: {type(data.get('rating'))}")
