import 'api_service.dart';
import '../config/api_config.dart';

/// AI Service - handles AI-powered features
class AIService {
  final _api = ApiService();

  // General AI Chat
  Future<Map<String, dynamic>> chat(String message) async {
    final result = await _api.post(
      ApiConfig.aiChat,
      {'message': message},
      requireAuth: true,
    );
    return result;
  }

  // Chat with specific book
  Future<Map<String, dynamic>> chatWithBook(String gid, String message) async {
    final result = await _api.post(
      ApiConfig.aiBookChat(gid),
      {'message': message},
      requireAuth: true,
    );
    return result;
  }

  // Get AI summary for a book
  Future<Map<String, dynamic>> getBookSummary(String gid) async {
    final result = await _api.get(ApiConfig.aiBookSummary(gid));
    return result;
  }

  // Get AI-generated quotes for a book
  Future<Map<String, dynamic>> getBookQuotes(String gid) async {
    final result = await _api.get(ApiConfig.aiBookQuotes(gid));
    return result;
  }

  // Get AI quiz for a book
  Future<Map<String, dynamic>> getBookQuiz(String gid) async {
    final result = await _api.get(ApiConfig.aiBookQuiz(gid));
    return result;
  }

  // Get "Why you might like this" for a book
  Future<Map<String, dynamic>> getWhyLike(String gid) async {
    final result = await _api.get(
      ApiConfig.aiBookChat(gid).replaceAll('/chat', '/why-like'),
      requireAuth: true,
    );
    return result;
  }
}
