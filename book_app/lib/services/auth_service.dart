import 'package:flutter/foundation.dart';
import 'api_service.dart';
import '../config/api_config.dart';

/// Auth Service - handles login, register, and user state
class AuthService extends ChangeNotifier {
  final _api = ApiService();
  
  Map<String, dynamic>? _user;
  bool _isLoading = false;
  String? _error;
  
  Map<String, dynamic>? get user => _user;
  bool get isLoading => _isLoading;
  String? get error => _error;
  bool get isLoggedIn => _user != null;
  String get userName => _user?['name'] ?? 'مستخدم';
  
  // Initialize - check if user has token
  Future<void> init() async {
    if (await _api.isLoggedIn) {
      await fetchCurrentUser();
    }
  }
  
  // Register new user
  Future<bool> register(String name, String email, String password) async {
    _isLoading = true;
    _error = null;
    notifyListeners();
    
    final result = await _api.post(ApiConfig.authRegister, {
      'name': name,
      'email': email,
      'password': password,
    });
    
    _isLoading = false;
    
    if (result['success'] == true) {
      await _api.setToken(result['token']);
      _user = result['user'];
      notifyListeners();
      return true;
    } else {
      _error = result['error'] ?? 'فشل التسجيل';
      notifyListeners();
      return false;
    }
  }
  
  // Login
  Future<bool> login(String email, String password) async {
    _isLoading = true;
    _error = null;
    notifyListeners();
    
    final result = await _api.post(ApiConfig.authLogin, {
      'email': email,
      'password': password,
    });
    
    _isLoading = false;
    
    if (result['success'] == true) {
      await _api.setToken(result['token']);
      _user = result['user'];
      notifyListeners();
      return true;
    } else {
      _error = result['error'] ?? 'فشل تسجيل الدخول';
      notifyListeners();
      return false;
    }
  }
  
  // Logout
  Future<void> logout() async {
    await _api.post(ApiConfig.authLogout, {}, requireAuth: true);
    await _api.clearToken();
    _user = null;
    notifyListeners();
  }
  
  // Fetch current user info
  Future<void> fetchCurrentUser() async {
    final result = await _api.get(ApiConfig.authMe, requireAuth: true);
    if (result['success'] == true) {
      _user = result['user'];
      notifyListeners();
    } else {
      // Token invalid, clear it
      await _api.clearToken();
      _user = null;
      notifyListeners();
    }
  }
  
  // Complete onboarding with interests
  Future<bool> completeOnboarding(List<String> interests) async {
    final result = await _api.post(ApiConfig.authOnboarding, {
      'interests': interests,
    }, requireAuth: true);
    
    if (result['success'] == true) {
      // Update user data
      _user?['onboarding_completed'] = true;
      notifyListeners();
      return true;
    }
    return false;
  }
  
  void clearError() {
    _error = null;
    notifyListeners();
  }
}
