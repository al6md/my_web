import 'package:flutter/material.dart';
import 'package:cached_network_image/cached_network_image.dart';
import '../theme/app_theme.dart';
import '../widgets/gradient_button.dart';
import '../services/book_service.dart';
import 'book_detail_screen.dart';

class LibraryScreen extends StatefulWidget {
  const LibraryScreen({super.key});

  @override
  State<LibraryScreen> createState() => _LibraryScreenState();
}

class _LibraryScreenState extends State<LibraryScreen> {
  final BookService _bookService = BookService();
  final TextEditingController _searchController = TextEditingController();

  List<Map<String, dynamic>> _books = [];
  List<Map<String, dynamic>> _categories = [];
  String? _selectedCategory;
  bool _isLoading = true;
  bool _isSearching = false;
  int _currentPage = 1;
  bool _hasMore = true;

  @override
  void initState() {
    super.initState();
    _loadInitialData();
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  Future<void> _loadInitialData() async {
    await _bookService.fetchCategories();
    _categories = _bookService.categories;
    await _loadBooks();
  }

  Future<void> _loadBooks({bool loadMore = false}) async {
    if (!loadMore) {
      setState(() {
        _isLoading = true;
        _currentPage = 1;
        _hasMore = true;
      });
    }

    List<Map<String, dynamic>> newBooks;

    if (_searchController.text.isNotEmpty) {
      newBooks = await _bookService.searchBooks(
        _searchController.text,
        page: _currentPage,
      );
    } else if (_selectedCategory != null) {
      newBooks = await _bookService.fetchByCategory(
        _selectedCategory!,
        page: _currentPage,
      );
    } else {
      await _bookService.fetchTrending();
      newBooks = _bookService.trendingBooks;
    }

    if (mounted) {
      setState(() {
        if (loadMore) {
          _books.addAll(newBooks);
        } else {
          _books = newBooks;
        }
        _isLoading = false;
        _hasMore = newBooks.length >= 20;
      });
    }
  }

  void _onSearch(String query) {
    _isSearching = query.isNotEmpty;
    _loadBooks();
  }

  void _onCategorySelected(String? categoryId) {
    setState(() {
      _selectedCategory = categoryId;
      _searchController.clear();
      _isSearching = false;
    });
    _loadBooks();
  }

  void _loadMoreBooks() {
    if (!_isLoading && _hasMore) {
      _currentPage++;
      _loadBooks(loadMore: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.bgBody,
      body: CustomScrollView(
        slivers: [
          // App Bar
          SliverAppBar(
            floating: true,
            pinned: true,
            expandedHeight: 120,
            backgroundColor: AppTheme.bgSurface,
            flexibleSpace: FlexibleSpaceBar(
              background: Container(
                padding: const EdgeInsets.fromLTRB(24, 60, 24, 16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisAlignment: MainAxisAlignment.end,
                  children: [
                    Row(
                      children: [
                        const Icon(Icons.library_books,
                            color: AppTheme.primary, size: 28),
                        const SizedBox(width: 12),
                        ShaderMask(
                          shaderCallback: (bounds) =>
                              AppTheme.accentGradient.createShader(bounds),
                          child: const Text(
                            'المكتبة',
                            style: TextStyle(
                              fontSize: 28,
                              fontWeight: FontWeight.bold,
                              color: Colors.white,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          ),

          // Search Bar
          SliverToBoxAdapter(child: _buildSearchBar()),

          // Categories
          SliverToBoxAdapter(child: _buildCategoriesBar()),

          // Books Grid
          if (_isLoading)
            const SliverFillRemaining(
              child: Center(
                child: CircularProgressIndicator(color: AppTheme.primary),
              ),
            )
          else if (_books.isEmpty)
            SliverFillRemaining(child: _buildEmptyState())
          else
            SliverPadding(
              padding: const EdgeInsets.all(16),
              sliver: SliverGrid(
                gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                  crossAxisCount: 2,
                  childAspectRatio: 0.55,
                  crossAxisSpacing: 16,
                  mainAxisSpacing: 16,
                ),
                delegate: SliverChildBuilderDelegate(
                  (context, index) {
                    if (index >= _books.length) {
                      return null;
                    }
                    return _buildBookCard(_books[index]);
                  },
                  childCount: _books.length,
                ),
              ),
            ),

          // Load More Button
          if (!_isLoading && _hasMore && _books.isNotEmpty)
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Center(
                  child: SecondaryButton(
                    text: 'تحميل المزيد',
                    icon: Icons.refresh,
                    onPressed: _loadMoreBooks,
                  ),
                ),
              ),
            ),

          // Bottom spacing
          const SliverToBoxAdapter(child: SizedBox(height: 100)),
        ],
      ),
    );
  }

  Widget _buildSearchBar() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 16, 24, 8),
      child: Container(
        decoration: BoxDecoration(
          color: AppTheme.bgElevated,
          borderRadius: BorderRadius.circular(AppTheme.radiusMd),
          border: Border.all(color: AppTheme.borderSubtle),
        ),
        child: TextField(
          controller: _searchController,
          onSubmitted: _onSearch,
          decoration: InputDecoration(
            hintText: 'ابحث عن كتاب، مؤلف، أو موضوع...',
            prefixIcon: const Icon(Icons.search, color: AppTheme.textMuted),
            suffixIcon: _searchController.text.isNotEmpty
                ? IconButton(
                    icon: const Icon(Icons.close, color: AppTheme.textMuted),
                    onPressed: () {
                      _searchController.clear();
                      _onSearch('');
                    },
                  )
                : null,
            border: InputBorder.none,
            contentPadding: const EdgeInsets.all(16),
          ),
        ),
      ),
    );
  }

  Widget _buildCategoriesBar() {
    // Add "All" option at the beginning
    final allCategories = [
      {'id': null, 'name': 'الكل', 'name_en': 'All'},
      ..._categories,
    ];

    return SizedBox(
      height: 50,
      child: ListView.builder(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
        itemCount: allCategories.length,
        itemBuilder: (context, index) {
          final cat = allCategories[index];
          final isSelected = _selectedCategory == cat['id'];

          return Padding(
            padding: const EdgeInsets.only(left: 8),
            child: CategoryPill(
              text: cat['name'] as String,
              isSelected: isSelected,
              onTap: () => _onCategorySelected(cat['id'] as String?),
            ),
          );
        },
      ),
    );
  }

  Widget _buildEmptyState() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(40),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              padding: const EdgeInsets.all(24),
              decoration: BoxDecoration(
                gradient: AppTheme.primaryGradient,
                borderRadius: BorderRadius.circular(AppTheme.radiusXl),
                boxShadow: AppTheme.glowPrimary,
              ),
              child: const Icon(
                Icons.search_off,
                size: 48,
                color: Colors.white,
              ),
            ),
            const SizedBox(height: 24),
            const Text(
              'لا توجد نتائج',
              style: TextStyle(
                fontSize: 20,
                fontWeight: FontWeight.bold,
                color: AppTheme.textPrimary,
              ),
            ),
            const SizedBox(height: 8),
            const Text(
              'جرب البحث بكلمات مختلفة أو اختر تصنيف آخر',
              textAlign: TextAlign.center,
              style: TextStyle(color: AppTheme.textSecondary),
            ),
            const SizedBox(height: 24),
            GradientButton(
              text: 'استكشف المكتبة',
              icon: Icons.explore,
              onPressed: () {
                _searchController.clear();
                _onCategorySelected(null);
              },
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildBookCard(Map<String, dynamic> book) {
    final coverUrl = book['cover_url'] ?? book['cover'] ?? '';
    final title = book['title'] ?? 'بدون عنوان';
    final author = book['author'] ?? book['authors']?.join(', ') ?? '';
    final gid = book['gid'] ?? book['google_id'] ?? book['id'] ?? '';

    return GestureDetector(
      onTap: () {
        if (gid.toString().isNotEmpty) {
          Navigator.push(
            context,
            MaterialPageRoute(
              builder: (_) => BookDetailScreen(gid: gid.toString()),
            ),
          );
        }
      },
      child: Container(
        decoration: BoxDecoration(
          color: AppTheme.bgCard,
          borderRadius: BorderRadius.circular(AppTheme.radiusLg),
          border: Border.all(color: AppTheme.borderSubtle),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Cover
            Expanded(
              flex: 4,
              child: ClipRRect(
                borderRadius: const BorderRadius.vertical(
                  top: Radius.circular(AppTheme.radiusLg),
                ),
                child: SizedBox(
                  width: double.infinity,
                  child: coverUrl.isNotEmpty
                      ? CachedNetworkImage(
                          imageUrl: coverUrl,
                          fit: BoxFit.cover,
                          placeholder: (_, __) => Container(
                            color: AppTheme.bgElevated,
                            child: const Center(
                              child: CircularProgressIndicator(
                                strokeWidth: 2,
                                color: AppTheme.primary,
                              ),
                            ),
                          ),
                          errorWidget: (_, __, ___) =>
                              _buildBookPlaceholder(title),
                        )
                      : _buildBookPlaceholder(title),
                ),
              ),
            ),

            // Info
            Expanded(
              flex: 2,
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontWeight: FontWeight.bold,
                        fontSize: 14,
                        color: AppTheme.textPrimary,
                      ),
                    ),
                    const Spacer(),
                    if (author.isNotEmpty)
                      Text(
                        author,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          color: AppTheme.textMuted,
                          fontSize: 12,
                        ),
                      ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildBookPlaceholder(String title) {
    return Container(
      decoration: BoxDecoration(
        gradient: AppTheme.primaryGradient,
      ),
      child: Center(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Text(
            title,
            textAlign: TextAlign.center,
            maxLines: 4,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
              color: Colors.white,
              fontWeight: FontWeight.bold,
              fontSize: 14,
            ),
          ),
        ),
      ),
    );
  }
}
