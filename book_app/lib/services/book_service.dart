import 'package:flutter/foundation.dart';
import 'api_service.dart';
import '../config/api_config.dart';

/// Book Service - handles book operations
class BookService extends ChangeNotifier {
  final _api = ApiService();
  
  List<Map<String, dynamic>> _categories = [];
  List<Map<String, dynamic>> _trendingBooks = [];
  List<Map<String, dynamic>> _searchResults = [];
  List<dynamic> _recommendations = [];
  bool _isLoading = false;
  String? _error;
  
  List<Map<String, dynamic>> get categories => _categories;
  List<Map<String, dynamic>> get trendingBooks => _trendingBooks;
  List<Map<String, dynamic>> get searchResults => _searchResults;
  List<dynamic> get recommendations => _recommendations;
  bool get isLoading => _isLoading;
  String? get error => _error;
  
  // Fetch categories
  Future<void> fetchCategories() async {
    final result = await _api.get(ApiConfig.booksCategories);
    if (result['success'] == true) {
      _categories = List<Map<String, dynamic>>.from(result['categories'] ?? []);
      notifyListeners();
    }
  }
  
  // Fetch trending books
  Future<void> fetchTrending({int limit = 12}) async {
    _isLoading = true;
    notifyListeners();
    
    final result = await _api.get('${ApiConfig.booksTrending}?limit=$limit');
    
    _isLoading = false;
    if (result['success'] == true) {
      _trendingBooks = List<Map<String, dynamic>>.from(result['books'] ?? []);
    }
    notifyListeners();
  }
  
  // Search books
  Future<void> search(String query, {int page = 1}) async {
    if (query.isEmpty) {
      _searchResults = [];
      notifyListeners();
      return;
    }
    
    _isLoading = true;
    _error = null;
    notifyListeners();
    
    final result = await _api.get('${ApiConfig.booksSearch}?q=$query&page=$page');
    
    _isLoading = false;
    if (result['success'] == true) {
      _searchResults = List<Map<String, dynamic>>.from(result['books'] ?? []);
    } else {
      _error = result['error'];
    }
    notifyListeners();
  }
  
  // Get book detail
  Future<Map<String, dynamic>?> getBookDetail(String gid) async {
    final result = await _api.get(ApiConfig.bookDetail(gid));
    if (result['success'] == true) {
      return result['book'];
    }
    return null;
  }
  
  // Fetch recommendations (requires auth)
  Future<void> fetchRecommendations() async {
    _isLoading = true;
    notifyListeners();
    
    final result = await _api.get(ApiConfig.booksRecommendations, requireAuth: true);
    
    _isLoading = false;
    if (result['success'] == true) {
      _recommendations = result['sections'] ?? [];
    }
    notifyListeners();
  }
  
  // Get books by category
  Future<List<Map<String, dynamic>>> getBooksByCategory(String categoryId, {int page = 1}) async {
    final result = await _api.get('${ApiConfig.booksByCategory(categoryId)}?page=$page');
    if (result['success'] == true) {
      return List<Map<String, dynamic>>.from(result['books'] ?? []);
    }
    return [];
  }
  
  void clearSearch() {
    _searchResults = [];
    notifyListeners();
  }
}
