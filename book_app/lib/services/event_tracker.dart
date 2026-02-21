import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

class EventTrackerService {
  // Replace with your actual backend URL (e.g., 'http://10.0.2.2:5000/api' for Android Emulator)
  static const String baseUrl = 'http://127.0.0.1:5000/api';

  /// Helper to get the JWT token from SharedPreferences
  Future<String?> _getToken() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs
        .getString('auth_token'); // Ensure this matches your login saving key
  }

  /// Generic method to log an event
  Future<void> _logEvent({
    required String eventType,
    required String bookId,
    String? sessionId,
    int? durationSeconds,
    double? scrollDepth,
    Map<String, dynamic>? metadata,
  }) async {
    try {
      final token = await _getToken();
      if (token == null) {
        print('EventTracker: Cannot log event. No auth token found.');
        return;
      }

      final uri = Uri.parse('$baseUrl/books/event');
      final body = jsonEncode({
        'event_type': eventType,
        'book_google_id': bookId,
        if (sessionId != null) 'session_id': sessionId,
        if (durationSeconds != null) 'duration_seconds': durationSeconds,
        if (scrollDepth != null) 'scroll_depth': scrollDepth,
        if (metadata != null) 'metadata': metadata,
      });

      final response = await http.post(
        uri,
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $token',
        },
        body: body,
      );

      if (response.statusCode == 201) {
        print(
            'EventTracker: Successfully logged [$eventType] for book $bookId');
      } else {
        print(
            'EventTracker: Failed to log event. Status: ${response.statusCode}, Body: ${response.body}');
      }
    } catch (e) {
      print('EventTracker: Network error logging event - $e');
    }
  }

  /// Triggers when a user views a book detail page
  Future<void> trackView(String bookId, {String? sessionId}) async {
    await _logEvent(
      eventType: 'view',
      bookId: bookId,
      sessionId: sessionId,
    );
  }

  /// Triggers when a user leaves the book page quickly or backs out
  Future<void> trackAbandon(String bookId,
      {String? sessionId, double? scrollDepth, int? spentSeconds}) async {
    await _logEvent(
      eventType: 'abandon',
      bookId: bookId,
      sessionId: sessionId,
      scrollDepth: scrollDepth,
      durationSeconds: spentSeconds,
    );
  }

  /// Triggers when a user marks the book as "finished" or finishes reading
  Future<void> trackFinish(String bookId, {String? sessionId}) async {
    await _logEvent(
      eventType: 'finish',
      bookId: bookId,
      sessionId: sessionId,
    );
  }

  /// Triggers when the user shares the book
  Future<void> trackShare(String bookId) async {
    await _logEvent(
      eventType: 'share',
      bookId: bookId,
    );
  }
}

// Global instance for easy access
final eventTracker = EventTrackerService();
