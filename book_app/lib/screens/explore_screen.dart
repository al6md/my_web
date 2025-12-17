import 'package:flutter/material.dart';
import 'package:cached_network_image/cached_network_image.dart';
import '../theme/app_theme.dart';
import '../widgets/gradient_card.dart';
import '../widgets/gradient_button.dart';
import '../services/book_service.dart';
import '../config/api_config.dart';
import 'book_detail_screen.dart';
import 'search_screen.dart';

class ExploreScreen extends StatefulWidget {
  const ExploreScreen({super.key});

  @override
  State<ExploreScreen> createState() => _ExploreScreenState();
}

class _ExploreScreenState extends State<ExploreScreen> {
  final BookService _bookService = BookService();
  List<Map<String, dynamic>> _sections = [];
  Map<String, dynamic>? _heroBook;
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _loadData();
  }

  Future<void> _loadData() async {
    setState(() => _isLoading = true);

    // Fetch trending for hero
    await _bookService.fetchTrending();
    if (_bookService.trendingBooks.isNotEmpty) {
      _heroBook = _bookService.trendingBooks.first;
    }

    // Create sections
    _sections = [
      {
        'title': 'الكتب الرائجة',
        'icon': Icons.local_fire_department,
        'books': _bookService.trendingBooks,
      },
    ];

    // Fetch by categories
    await _fetchCategoryBooks();

    if (mounted) setState(() => _isLoading = false);
  }

  Future<void> _fetchCategoryBooks() async {
    final categories = [
      {'id': 'fiction', 'title': 'روايات الخيال', 'icon': Icons.auto_stories},
      {'id': 'science', 'title': 'العلوم والطبيعة', 'icon': Icons.science},
      {'id': 'history', 'title': 'التاريخ والحضارة', 'icon': Icons.history_edu},
      {'id': 'self-help', 'title': 'تطوير الذات', 'icon': Icons.psychology},
    ];

    for (var cat in categories) {
      final books = await _bookService.fetchByCategory(cat['id'] as String);
      if (books.isNotEmpty) {
        _sections.add({
          'title': cat['title'],
          'icon': cat['icon'],
          'books': books,
          'query': cat['id'],
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.bgBody,
      body: RefreshIndicator(
        onRefresh: _loadData,
        color: AppTheme.primary,
        child: CustomScrollView(
          slivers: [
            // Hero Section
            SliverToBoxAdapter(child: _buildHeroSection()),

            // Book Sections
            if (_isLoading)
              const SliverFillRemaining(
                child: Center(
                  child: CircularProgressIndicator(color: AppTheme.primary),
                ),
              )
            else ...[
              for (var section in _sections)
                SliverToBoxAdapter(child: _buildBookSection(section)),

              // Features Section
              SliverToBoxAdapter(child: _buildFeaturesSection()),

              // Bottom spacing
              const SliverToBoxAdapter(child: SizedBox(height: 100)),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildHeroSection() {
    return Container(
      padding: const EdgeInsets.fromLTRB(24, 60, 24, 32),
      child: Column(
        children: [
          // Badge
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            decoration: BoxDecoration(
              color: AppTheme.bgElevated,
              borderRadius: BorderRadius.circular(30),
              border: Border.all(color: AppTheme.borderSubtle),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.auto_awesome, size: 16, color: AppTheme.accentCyan),
                const SizedBox(width: 8),
                const Text(
                  'مدعوم بالذكاء الاصطناعي',
                  style: TextStyle(
                    color: AppTheme.accentCyan,
                    fontWeight: FontWeight.w600,
                    fontSize: 14,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 24),

          // Title
          RichText(
            textAlign: TextAlign.center,
            text: TextSpan(
              style: const TextStyle(
                fontSize: 30,
                fontWeight: FontWeight.w800,
                height: 1.2,
                fontFamily: 'Cairo',
              ),
              children: [
                const TextSpan(
                  text: 'اكتشف كتابك القادم\n',
                  style: TextStyle(color: AppTheme.textPrimary),
                ),
                TextSpan(
                  text: 'بذكاء وإلهام',
                  style: TextStyle(
                    foreground: Paint()
                      ..shader = AppTheme.accentGradient.createShader(
                        const Rect.fromLTWH(0, 0, 200, 50),
                      ),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),

          // Subtitle
          const Text(
            'خوارزميات ذكية تحلل اهتماماتك وتقترح لك الكتب المثالية',
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: 15,
              color: AppTheme.textSecondary,
            ),
          ),
          const SizedBox(height: 24),

          // Actions
          Wrap(
            spacing: 12,
            runSpacing: 12,
            alignment: WrapAlignment.center,
            children: [
              GradientButton(
                text: 'تصفح المكتبة',
                icon: Icons.search,
                onPressed: () {
                  Navigator.push(
                    context,
                    MaterialPageRoute(builder: (_) => const SearchScreen()),
                  );
                },
              ),
            ],
          ),
          const SizedBox(height: 32),

          // Stats
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              _buildStatItem('+١٠٠٠', 'كتاب متاح'),
              Container(
                width: 1,
                height: 40,
                color: AppTheme.borderSubtle,
                margin: const EdgeInsets.symmetric(horizontal: 24),
              ),
              _buildStatItem('AI', 'توصيات ذكية'),
              Container(
                width: 1,
                height: 40,
                color: AppTheme.borderSubtle,
                margin: const EdgeInsets.symmetric(horizontal: 24),
              ),
              _buildStatItem('٢٤/٧', 'متاح دائماً'),
            ],
          ),

          // Featured book card
          if (_heroBook != null) ...[
            const SizedBox(height: 32),
            _buildFeaturedBook(),
          ],
        ],
      ),
    );
  }

  Widget _buildStatItem(String value, String label) {
    return Column(
      children: [
        ShaderMask(
          shaderCallback: (bounds) =>
              AppTheme.accentGradient.createShader(bounds),
          child: Text(
            value,
            style: const TextStyle(
              fontSize: 24,
              fontWeight: FontWeight.w800,
              color: Colors.white,
            ),
          ),
        ),
        const SizedBox(height: 4),
        Text(
          label,
          style: const TextStyle(
            fontSize: 12,
            color: AppTheme.textMuted,
          ),
        ),
      ],
    );
  }

  Widget _buildFeaturedBook() {
    if (_heroBook == null) return const SizedBox();

    final book = _heroBook!;
    final coverUrl = book['cover_url'] ?? book['cover'] ?? '';
    final title = book['title'] ?? '';
    final author = book['author'] ?? '';
    final gid = book['gid'] ?? book['google_id'] ?? book['id'] ?? '';

    return GlassCard(
      padding: const EdgeInsets.all(16),
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
      child: Row(
        children: [
          // Cover
          ClipRRect(
            borderRadius: BorderRadius.circular(AppTheme.radiusMd),
            child: Container(
              width: 100,
              height: 140,
              color: AppTheme.bgElevated,
              child: coverUrl.isNotEmpty
                  ? CachedNetworkImage(
                      imageUrl: coverUrl,
                      fit: BoxFit.cover,
                      errorWidget: (_, __, ___) => _buildBookPlaceholder(title),
                    )
                  : _buildBookPlaceholder(title),
            ),
          ),
          const SizedBox(width: 16),

          // Info
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Icon(Icons.star, size: 16, color: AppTheme.warning),
                    const SizedBox(width: 6),
                    const Text(
                      'ترشيح اليوم لك',
                      style: TextStyle(
                        color: AppTheme.warning,
                        fontWeight: FontWeight.bold,
                        fontSize: 13,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Text(
                  title,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.bold,
                    color: AppTheme.textPrimary,
                  ),
                ),
                if (author.isNotEmpty) ...[
                  const SizedBox(height: 4),
                  Text(
                    author,
                    style: const TextStyle(
                      color: AppTheme.textMuted,
                      fontSize: 14,
                    ),
                  ),
                ],
                const SizedBox(height: 12),
                Row(
                  children: [
                    GradientButton(
                      text: 'عرض التفاصيل',
                      icon: Icons.visibility,
                      padding: const EdgeInsets.symmetric(
                        horizontal: 12,
                        vertical: 8,
                      ),
                      onPressed: () {
                        if (gid.toString().isNotEmpty) {
                          Navigator.push(
                            context,
                            MaterialPageRoute(
                              builder: (_) =>
                                  BookDetailScreen(gid: gid.toString()),
                            ),
                          );
                        }
                      },
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildBookSection(Map<String, dynamic> section) {
    final books = section['books'] as List<dynamic>;
    if (books.isEmpty) return const SizedBox();

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 24),
            child: Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    gradient: AppTheme.primaryGradient,
                    borderRadius: BorderRadius.circular(AppTheme.radiusMd),
                    boxShadow: AppTheme.glowPrimary,
                  ),
                  child: Icon(
                    section['icon'] as IconData? ?? Icons.auto_awesome,
                    color: Colors.white,
                    size: 20,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    section['title'] as String,
                    style: const TextStyle(
                      fontSize: 20,
                      fontWeight: FontWeight.bold,
                      color: AppTheme.textPrimary,
                    ),
                  ),
                ),
                GhostButton(
                  text: 'عرض الكل',
                  icon: Icons.arrow_back,
                  onPressed: () {
                    Navigator.push(
                      context,
                      MaterialPageRoute(builder: (_) => const SearchScreen()),
                    );
                  },
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),

          // Books horizontal list
          SizedBox(
            height: 260,
            child: ListView.builder(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(horizontal: 24),
              itemCount: books.length,
              itemBuilder: (context, index) {
                final book = books[index] as Map<String, dynamic>;
                return _buildBookCard(book);
              },
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildBookCard(Map<String, dynamic> book) {
    final coverUrl = book['cover_url'] ?? book['cover'] ?? '';
    final title = book['title'] ?? 'بدون عنوان';
    final author = book['author'] ?? '';
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
        width: 140,
        margin: const EdgeInsets.only(left: 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Cover
            Container(
              height: 195,
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(AppTheme.radiusMd),
                boxShadow: AppTheme.shadowMd,
              ),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(AppTheme.radiusMd),
                child: coverUrl.isNotEmpty
                    ? CachedNetworkImage(
                        imageUrl: coverUrl,
                        fit: BoxFit.cover,
                        width: double.infinity,
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
            const SizedBox(height: 10),

            // Title
            Text(
              title,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                fontWeight: FontWeight.w600,
                fontSize: 14,
                color: AppTheme.textPrimary,
              ),
            ),

            // Author
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
    );
  }

  Widget _buildBookPlaceholder(String title) {
    return Container(
      decoration: BoxDecoration(
        gradient: AppTheme.primaryGradient,
      ),
      child: Center(
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Text(
            title,
            textAlign: TextAlign.center,
            maxLines: 4,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
              color: Colors.white,
              fontWeight: FontWeight.bold,
              fontSize: 13,
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildFeaturesSection() {
    return Container(
      margin: const EdgeInsets.all(24),
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: AppTheme.bgSurface,
        borderRadius: BorderRadius.circular(AppTheme.radiusXl),
        border: Border.all(color: AppTheme.borderSubtle),
      ),
      child: Column(
        children: [
          RichText(
            textAlign: TextAlign.center,
            text: TextSpan(
              style: const TextStyle(
                fontSize: 22,
                fontWeight: FontWeight.bold,
                fontFamily: 'Cairo',
              ),
              children: [
                const TextSpan(
                  text: 'لماذا ',
                  style: TextStyle(color: AppTheme.textPrimary),
                ),
                TextSpan(
                  text: 'مكتبة الإلهام',
                  style: TextStyle(
                    foreground: Paint()
                      ..shader = AppTheme.accentGradient.createShader(
                        const Rect.fromLTWH(0, 0, 150, 30),
                      ),
                  ),
                ),
                const TextSpan(
                  text: '؟',
                  style: TextStyle(color: AppTheme.textPrimary),
                ),
              ],
            ),
          ),
          const SizedBox(height: 8),
          const Text(
            'تجربة قراءة فريدة مع أحدث تقنيات الذكاء الاصطناعي',
            textAlign: TextAlign.center,
            style: TextStyle(color: AppTheme.textSecondary),
          ),
          const SizedBox(height: 24),

          // Features
          _buildFeatureItem(
            Icons.psychology,
            'توصيات ذكية',
            'خوارزميات AI متقدمة تحلل ذوقك',
            AppTheme.primaryGradient,
          ),
          const SizedBox(height: 16),
          _buildFeatureItem(
            Icons.chat_bubble_outline,
            'تحدث مع الكتب',
            'اسأل أي سؤال واحصل على إجابات فورية',
            AppTheme.magentaGradient,
          ),
          const SizedBox(height: 16),
          _buildFeatureItem(
            Icons.auto_awesome,
            'ملخصات AI',
            'ملخصات ذكية لمساعدتك في اتخاذ القرار',
            AppTheme.cyanGradient,
          ),
        ],
      ),
    );
  }

  Widget _buildFeatureItem(
    IconData icon,
    String title,
    String description,
    Gradient gradient,
  ) {
    return Row(
      children: [
        Container(
          width: 56,
          height: 56,
          decoration: BoxDecoration(
            gradient: gradient,
            borderRadius: BorderRadius.circular(AppTheme.radiusMd),
          ),
          child: Icon(icon, color: Colors.white, size: 28),
        ),
        const SizedBox(width: 16),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                title,
                style: const TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.bold,
                  color: AppTheme.textPrimary,
                ),
              ),
              const SizedBox(height: 2),
              Text(
                description,
                style: const TextStyle(
                  fontSize: 13,
                  color: AppTheme.textSecondary,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}
