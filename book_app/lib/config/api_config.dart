/// API Configuration for Book Recommendation App
class ApiConfig {
  // Change this to your server URL
  // For local testing: http://10.0.2.2:5000 (Android emulator)
  // For Windows testing: http://127.0.0.1:5000
  // For production: https://your-api.onrender.com

  // ✅ Production API on Render
  static const String baseUrl = 'https://my-web1-h144.onrender.com';

  // API Endpoints
  static const String authRegister = '/api/auth/register';
  static const String authLogin = '/api/auth/login';
  static const String authLogout = '/api/auth/logout';
  static const String authMe = '/api/auth/me';
  static const String authOnboarding = '/api/auth/onboarding';

  static const String booksSearch = '/api/books/search';
  static const String booksTrending = '/api/books/trending';
  static const String booksCategories = '/api/books/categories';
  static const String booksRecommendations = '/api/books/recommendations';
  static const String booksMoodRecommendations =
      '/api/books/mood-recommendations';

  static String bookDetail(String gid) => '/api/books/$gid';
  static String booksByCategory(String categoryId) =>
      '/api/books/category/$categoryId';

  static const String userLibrary = '/api/user/library';
  static const String userPreferences = '/api/user/preferences';
  static const String userStats = '/api/user/stats';

  static String addToLibrary(String gid) => '/api/user/library/$gid';
  static String removeFromLibrary(String gid) => '/api/user/library/$gid';
  static String rateBook(String gid) => '/api/user/rate/$gid';

  static const String aiChat = '/api/ai/chat';
  static String aiBookChat(String gid) => '/api/ai/book/$gid/chat';
  static String aiBookSummary(String gid) => '/api/ai/book/$gid/summary';
  static String aiBookQuotes(String gid) => '/api/ai/book/$gid/quotes';
  static String aiBookQuiz(String gid) => '/api/ai/book/$gid/quiz';
}
