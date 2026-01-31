
import unittest
from flask_book_recommendation.app import create_app, db
from flask_book_recommendation.models import User, Book
from flask_login import login_user

class TestAICoverGeneration(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.app.config['WTF_CSRF_ENABLED'] = False  # Disable CSRF for testing
        self.client = self.app.test_client()
        
        with self.app.app_context():
            db.create_all()
            
            # Create a test user with unique email
            import random
            rand_id = random.randint(1000, 9999)
            self.user = User(name=f'TestUser_{rand_id}', email=f'test_{rand_id}@example.com', password_hash='hash')
            db.session.add(self.user)
            db.session.commit()
            self.user_id = self.user.id
            
            # Create a test book owned by the user
            self.book = Book(
                title='Test Book for AI Cover', 
                author='Test Author', 
                owner_id=self.user.id,
                cover_url='http://old.cover/image.jpg'
            )
            db.session.add(self.book)
            db.session.commit()
            self.book_id = self.book.id
            db.session.add(self.book)
            db.session.commit()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def test_generate_cover(self):
        with self.client:
            # Login
            with self.client.session_transaction() as sess:
                sess['_user_id'] = str(self.user_id)
                sess['_fresh'] = True

            # Call the generate route
            response = self.client.post(f'/books/{self.book_id}/generate_cover', follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            
            # Verify database update
            with self.app.app_context():
                updated_book = Book.query.get(self.book_id)
                self.assertIn('pollinations.ai', updated_book.cover_url)
                print(f"\n[SUCCESS] Cover updated to: {updated_book.cover_url}")

if __name__ == '__main__':
    unittest.main()
