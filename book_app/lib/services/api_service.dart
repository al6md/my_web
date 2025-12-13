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
    'Accept': 'application/json',
  };
  
  Future<Map<String, String>> get _authHeaders async {
    final t = await token;
    return {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
      if (t != null) 'Authorization': 'Bearer $t',
    };
  }
  
  String _url(String endpoint) => '${ApiConfig.baseUrl}$endpoint';
  
  // GET request
  Future<Map<String, dynamic>> get(String endpoint, {bool requireAuth = false}) async {
    try {
      final headers = requireAuth ? await _authHeaders : _headers;
      final url = _url(endpoint);
      print('[API GET] $url');  // Debug
      final response = await http.get(Uri.parse(url), headers: headers);
      print('[API Response] ${response.statusCode}: ${response.body.substring(0, response.body.length.clamp(0, 200))}');  // Debug
      return _handleResponse(response);
    } catch (e) {
      print('[API Error] $e');  // Debug
      return {'success': false, 'error': 'خطأ في الاتصال: $e'};
    }
  }
  
  // POST request
  Future<Map<String, dynamic>> post(String endpoint, Map<String, dynamic> body, {bool requireAuth = false}) async {
    try {
      final headers = requireAuth ? await _authHeaders : _headers;
      final url = _url(endpoint);
      print('[API POST] $url');  // Debug
      print('[API Body] $body');  // Debug
      final response = await http.post(
        Uri.parse(url),
        headers: headers,
        body: jsonEncode(body),
      );
      print('[API Response] ${response.statusCode}: ${response.body}');  // Debug
      return _handleResponse(response);
    } catch (e) {
      print('[API Error] $e');  // Debug
      return {'success': false, 'error': 'خطأ في الاتصال: $e'};
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
      return {'success': false, 'error': 'خطأ في الاتصال: $e'};
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
    print('[Handle Response] Status: ${response.statusCode}');  // Debug
    
    // Check for empty response
    if (response.body.isEmpty) {
      return {
        'success': false,
        'error': 'الاستجابة فارغة (${response.statusCode})',
        'statusCode': response.statusCode,
      };
    }
    
    try {
      final data = jsonDecode(response.body);
      if (response.statusCode >= 200 && response.statusCode < 300) {
        return data is Map<String, dynamic> ? data : {'success': true, 'data': data};
      } else {
        return {
          'success': false,
          'error': data['error'] ?? data['message'] ?? 'حدث خطأ (${response.statusCode})',
          'statusCode': response.statusCode,
        };
      }
    } catch (e) {
      print('[JSON Parse Error] $e');  // Debug
      print('[Response Body] ${response.body}');  // Debug
      return {
        'success': false,
        'error': 'خطأ في الاتصال بالسيرفر',
        'statusCode': response.statusCode,
        'rawBody': response.body,
      };
    }
  }
}
