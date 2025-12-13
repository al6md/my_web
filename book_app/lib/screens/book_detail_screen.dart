import 'package:flutter/material.dart';
import 'package:cached_network_image/cached_network_image.dart';
import '../services/book_service.dart';

class BookDetailScreen extends StatefulWidget {
  final String gid;

  const BookDetailScreen({super.key, required this.gid});

  @override
  State<BookDetailScreen> createState() => _BookDetailScreenState();
}

class _BookDetailScreenState extends State<BookDetailScreen> {
  final _bookService = BookService();
  Map<String, dynamic>? _book;
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _loadBook();
  }

  Future<void> _loadBook() async {
    final book = await _bookService.getBookDetail(widget.gid);
    if (mounted) {
      setState(() {
        _book = book;
        _isLoading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : _book == null
              ? const Center(child: Text('الكتاب غير موجود'))
              : CustomScrollView(
                  slivers: [
                    // App Bar with cover
                    SliverAppBar(
                      expandedHeight: 300,
                      pinned: true,
                      flexibleSpace: FlexibleSpaceBar(
                        background: Stack(
                          fit: StackFit.expand,
                          children: [
                            // Background blur
                            if (_book!['cover_url'] != null)
                              CachedNetworkImage(
                                imageUrl: _book!['cover_url'],
                                fit: BoxFit.cover,
                                color: Colors.black45,
                                colorBlendMode: BlendMode.darken,
                              ),
                            // Cover image
                            Center(
                              child: Hero(
                                tag: 'book_${widget.gid}',
                                child: ClipRRect(
                                  borderRadius: BorderRadius.circular(8),
                                  child: SizedBox(
                                    height: 200,
                                    width: 130,
                                    child: _book!['cover_url'] != null
                                        ? CachedNetworkImage(
                                            imageUrl: _book!['cover_url'],
                                            fit: BoxFit.cover,
                                          )
                                        : Container(
                                            color: Colors.grey[300],
                                            child: const Icon(
                                              Icons.book,
                                              size: 48,
                                            ),
                                          ),
                                  ),
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                    // Book details
                    SliverToBoxAdapter(
                      child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            // Title
                            Text(
                              _book!['title'] ?? 'بدون عنوان',
                              style: const TextStyle(
                                fontSize: 24,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                            const SizedBox(height: 8),
                            // Author
                            if (_book!['author'] != null)
                              Text(
                                _book!['author'],
                                style: TextStyle(
                                  fontSize: 18,
                                  color: Colors.grey[600],
                                ),
                              ),
                            const SizedBox(height: 16),
                            // Stats row
                            Row(
                              children: [
                                if (_book!['average_rating'] != null) ...[
                                  const Icon(Icons.star, color: Colors.amber, size: 20),
                                  const SizedBox(width: 4),
                                  Text('${_book!['average_rating']}'),
                                  const SizedBox(width: 16),
                                ],
                                if (_book!['page_count'] != null) ...[
                                  const Icon(Icons.menu_book, size: 20),
                                  const SizedBox(width: 4),
                                  Text('${_book!['page_count']} صفحة'),
                                ],
                              ],
                            ),
                            const SizedBox(height: 24),
                            // Action buttons
                            Row(
                              children: [
                                Expanded(
                                  child: ElevatedButton.icon(
                                    onPressed: () {
                                      // Add to library
                                      ScaffoldMessenger.of(context).showSnackBar(
                                        const SnackBar(
                                          content: Text('تم إضافة الكتاب للمكتبة'),
                                        ),
                                      );
                                    },
                                    icon: const Icon(Icons.add),
                                    label: const Text('أضف للمكتبة'),
                                  ),
                                ),
                                const SizedBox(width: 12),
                                IconButton(
                                  onPressed: () {
                                    // Share
                                  },
                                  icon: const Icon(Icons.share),
                                  style: IconButton.styleFrom(
                                    backgroundColor: Colors.grey[200],
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(height: 24),
                            // Description
                            if (_book!['description'] != null) ...[
                              const Text(
                                'الوصف',
                                style: TextStyle(
                                  fontSize: 18,
                                  fontWeight: FontWeight.bold,
                                ),
                              ),
                              const SizedBox(height: 8),
                              Text(
                                _removeHtmlTags(_book!['description']),
                                style: const TextStyle(
                                  height: 1.6,
                                ),
                              ),
                            ],
                            const SizedBox(height: 24),
                            // Categories
                            if (_book!['categories'] != null && (_book!['categories'] as List).isNotEmpty) ...[
                              const Text(
                                'التصنيفات',
                                style: TextStyle(
                                  fontSize: 18,
                                  fontWeight: FontWeight.bold,
                                ),
                              ),
                              const SizedBox(height: 8),
                              Wrap(
                                spacing: 8,
                                children: (_book!['categories'] as List)
                                    .map((cat) => Chip(label: Text(cat.toString())))
                                    .toList(),
                              ),
                            ],
                            const SizedBox(height: 32),
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
    );
  }

  String _removeHtmlTags(String html) {
    return html.replaceAll(RegExp(r'<[^>]*>'), '');
  }
}
