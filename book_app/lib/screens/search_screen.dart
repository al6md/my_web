import 'package:flutter/material.dart';
import 'package:cached_network_image/cached_network_image.dart';
import '../theme/app_theme.dart';
import '../widgets/gradient_card.dart';
import '../widgets/gradient_button.dart';
import '../services/book_service.dart';
import 'book_detail_screen.dart';

class SearchScreen extends StatefulWidget {
  const SearchScreen({super.key});

  @override
  State<SearchScreen> createState() => _SearchScreenState();
}

class _SearchScreenState extends State<SearchScreen> {
  final BookService _bookService = BookService();
  final TextEditingController _searchController = TextEditingController();
  final FocusNode _focusNode = FocusNode();

  List<Map<String, dynamic>> _results = [];
  bool _isLoading = false;
  bool _hasSearched = false;
  List<String> _recentSearches = [
    'روايات عربية',
    'تطوير الذات',
    'علم النفس',
    'تاريخ العرب',
  ];

  @override
  void initState() {
    super.initState();
    // Auto-focus search field
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _focusNode.requestFocus();
    });
  }

  @override
  void dispose() {
    _searchController.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  Future<void> _search(String query) async {
    if (query.trim().isEmpty) return;

    setState(() {
      _isLoading = true;
      _hasSearched = true;
    });

    await _bookService.search(query);

    if (mounted) {
      setState(() {
        _results = _bookService.searchResults;
        _isLoading = false;
      });
    }
  }

  void _onRecentTap(String query) {
    _searchController.text = query;
    _search(query);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.bgBody,
      appBar: AppBar(
        backgroundColor: AppTheme.bgSurface,
        elevation: 0,
        leading: IconButton(
          icon: Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              color: AppTheme.bgElevated,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: AppTheme.borderSubtle),
            ),
            child: const Icon(Icons.arrow_back, size: 20),
          ),
          onPressed: () => Navigator.pop(context),
        ),
        title: const Text('البحث'),
      ),
      body: Column(
        children: [
          // Search bar
          _buildSearchBar(),

          // Content
          Expanded(
            child: _isLoading
                ? const Center(
                    child: CircularProgressIndicator(color: AppTheme.primary),
                  )
                : _hasSearched
                    ? _buildResults()
                    : _buildSuggestions(),
          ),
        ],
      ),
    );
  }

  Widget _buildSearchBar() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppTheme.bgSurface,
        border: Border(
          bottom: BorderSide(color: AppTheme.borderSubtle),
        ),
      ),
      child: Container(
        decoration: BoxDecoration(
          color: AppTheme.bgElevated,
          borderRadius: BorderRadius.circular(AppTheme.radiusMd),
          border: Border.all(color: AppTheme.borderSubtle),
        ),
        child: Row(
          children: [
            const Padding(
              padding: EdgeInsets.only(right: 12, left: 16),
              child: Icon(Icons.search, color: AppTheme.textMuted),
            ),
            Expanded(
              child: TextField(
                controller: _searchController,
                focusNode: _focusNode,
                onSubmitted: _search,
                decoration: const InputDecoration(
                  hintText: 'ابحث عن كتاب، مؤلف، أو موضوع...',
                  border: InputBorder.none,
                  contentPadding: EdgeInsets.symmetric(vertical: 16),
                ),
              ),
            ),
            if (_searchController.text.isNotEmpty)
              IconButton(
                icon: const Icon(Icons.close, color: AppTheme.textMuted),
                onPressed: () {
                  _searchController.clear();
                  setState(() {
                    _hasSearched = false;
                    _results = [];
                  });
                },
              ),
            Container(
              margin: const EdgeInsets.only(left: 8),
              child: GradientIconButton(
                icon: Icons.search,
                size: 44,
                onPressed: () => _search(_searchController.text),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSuggestions() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Recent searches
          const Text(
            'عمليات بحث سابقة',
            style: TextStyle(
              fontSize: 18,
              fontWeight: FontWeight.bold,
              color: AppTheme.textPrimary,
            ),
          ),
          const SizedBox(height: 16),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: _recentSearches
                .map((query) => GestureDetector(
                      onTap: () => _onRecentTap(query),
                      child: Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 16, vertical: 10),
                        decoration: BoxDecoration(
                          color: AppTheme.bgElevated,
                          borderRadius: BorderRadius.circular(20),
                          border: Border.all(color: AppTheme.borderSubtle),
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            const Icon(Icons.history,
                                size: 16, color: AppTheme.textMuted),
                            const SizedBox(width: 8),
                            Text(query,
                                style: const TextStyle(
                                    color: AppTheme.textSecondary)),
                          ],
                        ),
                      ),
                    ))
                .toList(),
          ),
          const SizedBox(height: 32),

          // Popular categories
          const Text(
            'تصنيفات شائعة',
            style: TextStyle(
              fontSize: 18,
              fontWeight: FontWeight.bold,
              color: AppTheme.textPrimary,
            ),
          ),
          const SizedBox(height: 16),
          _buildCategoryGrid(),
        ],
      ),
    );
  }

  Widget _buildCategoryGrid() {
    final categories = [
      {'name': 'روايات', 'icon': Icons.auto_stories, 'color': AppTheme.primary},
      {'name': 'علوم', 'icon': Icons.science, 'color': AppTheme.accentCyan},
      {
        'name': 'تاريخ',
        'icon': Icons.history_edu,
        'color': AppTheme.accentMagenta
      },
      {
        'name': 'تطوير ذات',
        'icon': Icons.psychology,
        'color': AppTheme.success
      },
      {'name': 'أدب', 'icon': Icons.menu_book, 'color': AppTheme.warning},
      {
        'name': 'فلسفة',
        'icon': Icons.lightbulb,
        'color': AppTheme.accentPurple
      },
    ];

    return GridView.builder(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 3,
        mainAxisSpacing: 12,
        crossAxisSpacing: 12,
        childAspectRatio: 1,
      ),
      itemCount: categories.length,
      itemBuilder: (context, index) {
        final cat = categories[index];
        return GestureDetector(
          onTap: () => _onRecentTap(cat['name'] as String),
          child: Container(
            decoration: BoxDecoration(
              color: AppTheme.bgCard,
              borderRadius: BorderRadius.circular(AppTheme.radiusMd),
              border: Border.all(color: AppTheme.borderSubtle),
            ),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Container(
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: (cat['color'] as Color).withOpacity(0.1),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Icon(
                    cat['icon'] as IconData,
                    color: cat['color'] as Color,
                    size: 24,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  cat['name'] as String,
                  style: const TextStyle(
                    color: AppTheme.textPrimary,
                    fontWeight: FontWeight.w600,
                    fontSize: 12,
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildResults() {
    if (_results.isEmpty) {
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
                child:
                    const Icon(Icons.search_off, size: 48, color: Colors.white),
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
              Text(
                'لم نجد نتائج لـ "${_searchController.text}"',
                textAlign: TextAlign.center,
                style: const TextStyle(color: AppTheme.textSecondary),
              ),
              const SizedBox(height: 24),
              GhostButton(
                text: 'مسح البحث',
                icon: Icons.refresh,
                onPressed: () {
                  _searchController.clear();
                  setState(() {
                    _hasSearched = false;
                    _results = [];
                  });
                },
              ),
            ],
          ),
        ),
      );
    }

    return GridView.builder(
      padding: const EdgeInsets.all(16),
      gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 2,
        childAspectRatio: 0.6,
        crossAxisSpacing: 16,
        mainAxisSpacing: 16,
      ),
      itemCount: _results.length,
      itemBuilder: (context, index) {
        return _buildBookCard(_results[index]);
      },
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
              flex: 3,
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
              flex: 1,
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
                        fontSize: 13,
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
                          fontSize: 11,
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
