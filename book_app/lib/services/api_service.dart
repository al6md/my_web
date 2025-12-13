import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import '../config/api_config.dart';

/// API Service - handles all HTTP requests to the backend
class ApiService {
  static final ApiService _instance = ApiService._internal();
  factory ApiService() => _instance;
  ApiService._internal();
  
  final _storage = const FlutterSecureStorage();
  String? _token;
  
  // Token management
  Future<String?> get token async {
    _token ??= await _storage.read(key: 'jwt_token');
    return _token;
  }
  
  Future<void> setToken(String token) async {
    _token = token;
    await _storage.write(key: 'jwt_token', value: token);
  }
  
  Future<void> clearToken() async {
    _token = null;
    await _storage.delete(key: 'jwt_token');
  }
  
  Future<bool> get isLoggedIn async {
    final t = await token;
    return t != null && t.isNotEmpty;
  }
  
  // HTTP helpers
  Map<String, String> get _headers => {
    'Content-Type': 'application/json',
  };
  
  Future<Map<String, String>> get _authHeaders async {
    final t = await token;
    return {
      'Content-Type': 'application/json',
      if (t != null) 'Authorization': 'Bearer $t',
    };
  }
  
  String _url(String endpoint) => '${ApiConfig.baseUrl}$endpoint';
  
  // GET request
  Future<Map<String, dynamic>> get(String endpoint, {bool requireAuth = false}) async {
    try {
      final headers = requireAuth ? await _authHeaders : _headers;
      final response = await http.get(Uri.parse(_url(endpoint)), headers: headers);
      return _handleResponse(response);
    } catch (e) {
      return {'success': false, 'error': e.toString()};
    }
  }
  
  // POST request
  Future<Map<String, dynamic>> post(String endpoint, Map<String, dynamic> body, {bool requireAuth = false}) async {
    try {
      final headers = requireAuth ? await _authHeaders : _headers;
      final response = await http.post(
        Uri.parse(_url(endpoint)),
        headers: headers,
        body: jsonEncode(body),
      );
      return _handleResponse(response);
    } catch (e) {
      return {'success': false, 'error': e.toString()};
    }
  }
  
  // PUT request
  Future<Map<String, dynamic>> put(String endpoint, Map<String, dynamic> body, {bool requireAuth = true}) async {
    try {
      final headers = requireAuth ? await _authHeaders : _headers;
      final response = await http.put(
        Uri.parse(_url(endpoint)),
        headers: headers,
        body: jsonEncode(body),
      );
      return _handleResponse(response);
    } catch (e) {
      return {'success': false, 'error': e.toString()};
    }
  }
  
  // DELETE request
  Future<Map<String, dynamic>> delete(String endpoint, {bool requireAuth = true}) async {
    try {
      final headers = requireAuth ? await _authHeaders : _headers;
      final response = await http.delete(Uri.parse(_url(endpoint)), headers: headers);
      return _handleResponse(response);
    } catch (e) {
      return {'success': false, 'error': e.toString()};
    }
  }
  
  Map<String, dynamic> _handleResponse(http.Response response) {
    try {
      final data = jsonDecode(response.body);
      if (response.statusCode >= 200 && response.statusCode < 300) {
        return data;
      } else {
        return {
          'success': false,
          'error': data['error'] ?? 'حدث خطأ (${response.statusCode})',
          'statusCode': response.statusCode,
        };
      }
    } catch (e) {
      return {
        'success': false,
        'error': 'خطأ في معالجة الاستجابة',
        'statusCode': response.statusCode,
      };
    }
  }
}
