import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:cached_network_image/cached_network_image.dart';
import '../theme/app_theme.dart';
import '../widgets/gradient_card.dart';
import '../widgets/gradient_button.dart';
import '../services/auth_service.dart';
import '../services/book_service.dart';
import 'login_screen.dart';
import 'search_screen.dart';
import 'book_detail_screen.dart';
import 'explore_screen.dart';
import 'library_screen.dart';
import 'profile_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> with TickerProviderStateMixin {
  final BookService _bookService = BookService();
  int _currentIndex = 0;
  late PageController _pageController;

  // Animation controllers
  late AnimationController _carouselController;

  @override
  void initState() {
    super.initState();
    _pageController = PageController();
    _carouselController = AnimationController(
      duration: const Duration(seconds: 4),
      vsync: this,
    )..repeat();
    _loadData();
  }

  @override
  void dispose() {
    _pageController.dispose();
    _carouselController.dispose();
    super.dispose();
  }

  Future<void> _loadData() async {
    await _bookService.fetchCategories();
    await _bookService.fetchTrending();
    if (mounted) setState(() {});
  }

  void _onNavTap(int index) {
    setState(() => _currentIndex = index);
    _pageController.animateToPage(
      index,
      duration: const Duration(milliseconds: 300),
      curve: Curves.easeInOut,
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.bgBody,
      body: PageView(
        controller: _pageController,
        onPageChanged: (index) => setState(() => _currentIndex = index),
        children: [
          _buildHomePage(),
          const ExploreScreen(),
          const LibraryScreen(),
          const ProfileScreen(),
        ],
      ),
      bottomNavigationBar: _buildBottomNav(),
    );
  }

  Widget _buildBottomNav() {
    return Container(
      decoration: BoxDecoration(
        color: AppTheme.bgSurface,
        border: Border(
          top: BorderSide(color: AppTheme.borderSubtle),
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.3),
            blurRadius: 20,
            offset: const Offset(0, -5),
          ),
        ],
      ),
      child: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceAround,
            children: [
              _buildNavItem(
                  0, Icons.home_outlined, Icons.home_rounded, 'الرئيسية'),
              _buildNavItem(1, Icons.explore_outlined, Icons.explore, 'استكشف'),
              _buildNavItem(2, Icons.library_books_outlined,
                  Icons.library_books, 'المكتبة'),
              _buildNavItem(3, Icons.person_outline, Icons.person, 'حسابي'),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildNavItem(
      int index, IconData icon, IconData activeIcon, String label) {
    final isSelected = _currentIndex == index;
    return GestureDetector(
      onTap: () => _onNavTap(index),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        decoration: BoxDecoration(
          gradient: isSelected ? AppTheme.primaryGradient : null,
          borderRadius: BorderRadius.circular(AppTheme.radiusLg),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              isSelected ? activeIcon : icon,
              color: isSelected ? Colors.white : AppTheme.textMuted,
              size: 24,
            ),
            if (isSelected) ...[
              const SizedBox(width: 8),
              Text(
                label,
                style: const TextStyle(
                  color: Colors.white,
                  fontWeight: FontWeight.bold,
                  fontSize: 13,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildHomePage() {
    return CustomScrollView(
      slivers: [
        // App Bar
        _buildSliverAppBar(),

        // Hero Section
        SliverToBoxAdapter(child: _buildHeroSection()),

        // Stats Section
        SliverToBoxAdapter(child: _buildStatsSection()),

        // Trending Books
        SliverToBoxAdapter(child: _buildTrendingSection()),

        // Features Section
        SliverToBoxAdapter(child: _buildFeaturesSection()),

        // CTA Section
        SliverToBoxAdapter(child: _buildCTASection()),

        // Bottom spacing
        const SliverToBoxAdapter(child: SizedBox(height: 100)),
      ],
    );
  }

  Widget _buildSliverAppBar() {
    final auth = context.watch<AuthService>();

    return SliverAppBar(
      floating: true,
      backgroundColor: AppTheme.bgSurface.withOpacity(0.95),
      elevation: 0,
      title: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              gradient: AppTheme.primaryGradient,
              borderRadius: BorderRadius.circular(10),
            ),
            child: const Icon(Icons.auto_stories_rounded,
                color: Colors.white, size: 20),
          ),
          const SizedBox(width: 12),
          ShaderMask(
            shaderCallback: (bounds) =>
                AppTheme.accentGradient.createShader(bounds),
            child: const Text(
              'ALHAM',
              style: TextStyle(
                fontSize: 22,
                fontWeight: FontWeight.w800,
                color: Colors.white,
                letterSpacing: 2,
              ),
            ),
          ),
        ],
      ),
      actions: [
        OutlinedIconButton(
          icon: Icons.search,
          onPressed: () {
            Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const SearchScreen()),
            );
          },
        ),
        const SizedBox(width: 8),
        if (auth.isLoggedIn)
          PopupMenuButton<String>(
            icon: Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: AppTheme.bgElevated,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: AppTheme.borderSubtle),
              ),
              child: const Icon(Icons.more_vert, size: 20),
            ),
            color: AppTheme.bgSurface,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(AppTheme.radiusMd),
            ),
            onSelected: (value) async {
              if (value == 'logout') {
                await auth.logout();
                if (mounted) {
                  Navigator.pushReplacement(
                    context,
                    MaterialPageRoute(builder: (_) => const LoginScreen()),
                  );
                }
              }
            },
            itemBuilder: (context) => [
              PopupMenuItem(
                value: 'logout',
                child: Row(
                  children: [
                    Icon(Icons.logout, color: AppTheme.danger, size: 20),
                    const SizedBox(width: 12),
                    const Text('تسجيل خروج'),
                  ],
                ),
              ),
            ],
          )
        else
          Padding(
            padding: const EdgeInsets.only(right: 12),
            child: GradientButton(
              text: 'دخول',
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              onPressed: () {
                Navigator.push(
                  context,
                  MaterialPageRoute(builder: (_) => const LoginScreen()),
                );
              },
            ),
          ),
        const SizedBox(width: 8),
      ],
    );
  }

  Widget _buildHeroSection() {
    return Container(
      padding: const EdgeInsets.fromLTRB(24, 40, 24, 40),
      child: Column(
        children: [
          // Badge
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            decoration: BoxDecoration(
              color: AppTheme.bgElevated,
              borderRadius: BorderRadius.circular(AppTheme.radiusSm),
              border: Border.all(color: AppTheme.borderSubtle),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.auto_awesome, size: 16, color: AppTheme.accentCyan),
                const SizedBox(width: 8),
                const Text(
                  'مكتبة الإلهام الذكية',
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

          // Main heading
          RichText(
            textAlign: TextAlign.center,
            text: TextSpan(
              style: const TextStyle(
                fontSize: 32,
                fontWeight: FontWeight.w800,
                height: 1.2,
                fontFamily: 'Cairo',
              ),
              children: [
                const TextSpan(
                  text: 'رحلتك لاكتشاف\n',
                  style: TextStyle(color: AppTheme.textPrimary),
                ),
                TextSpan(
                  text: 'المعرفة تبدأ هنا',
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
            'اكتشف كتباً تناسب ذوقك تماماً باستخدام تقنيات الذكاء الاصطناعي.\nانضم لآلاف القراء في تجربة فريدة.',
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: 16,
              color: AppTheme.textSecondary,
              height: 1.6,
            ),
          ),
          const SizedBox(height: 28),

          // CTA Buttons
          Wrap(
            spacing: 12,
            runSpacing: 12,
            alignment: WrapAlignment.center,
            children: [
              GradientButton(
                text: 'ابدأ الاستكشاف',
                icon: Icons.explore,
                onPressed: () => _onNavTap(1),
              ),
              SecondaryButton(
                text: 'الكتب الرائجة',
                icon: Icons.local_fire_department,
                onPressed: () => _onNavTap(2),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildStatsSection() {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 32),
      decoration: BoxDecoration(
        border: Border.symmetric(
          horizontal: BorderSide(color: AppTheme.borderSubtle),
        ),
      ),
      child: const Row(
        mainAxisAlignment: MainAxisAlignment.spaceEvenly,
        children: [
          StatsCard(value: '5M+', label: 'كتاب متوفر'),
          StatsCard(value: 'AI', label: 'توصيات دقيقة'),
          StatsCard(value: '24/7', label: 'مساعدة فورية'),
          StatsCard(value: '100%', label: 'مجاني'),
        ],
      ),
    );
  }

  Widget _buildTrendingSection() {
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      const Text(
                        'كتب رائجة ',
                        style: TextStyle(
                          fontSize: 22,
                          fontWeight: FontWeight.bold,
                          color: AppTheme.textPrimary,
                        ),
                      ),
                      ShaderMask(
                        shaderCallback: (bounds) =>
                            AppTheme.accentGradient.createShader(bounds),
                        child: const Text(
                          'هذا الأسبوع',
                          style: TextStyle(
                            fontSize: 22,
                            fontWeight: FontWeight.bold,
                            color: Colors.white,
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 4),
                  const Text(
                    'اختيارات القراء الأكثر طلباً',
                    style: TextStyle(
                      fontSize: 14,
                      color: AppTheme.textSecondary,
                    ),
                  ),
                ],
              ),
              GhostButton(
                text: 'عرض الكل',
                icon: Icons.arrow_back,
                onPressed: () => _onNavTap(2),
              ),
            ],
          ),
          const SizedBox(height: 20),

          // Books list
          if (_bookService.isLoading)
            const Center(
              child: Padding(
                padding: EdgeInsets.all(40),
                child: CircularProgressIndicator(color: AppTheme.primary),
              ),
            )
          else if (_bookService.trendingBooks.isEmpty)
            Center(
              child: Padding(
                padding: const EdgeInsets.all(40),
                child: Column(
                  children: [
                    Icon(Icons.library_books_outlined,
                        size: 64, color: AppTheme.textMuted),
                    const SizedBox(height: 16),
                    const Text(
                      'لا توجد كتب حالياً',
                      style: TextStyle(color: AppTheme.textSecondary),
                    ),
                  ],
                ),
              ),
            )
          else
            SizedBox(
              height: 280,
              child: ListView.builder(
                scrollDirection: Axis.horizontal,
                itemCount: _bookService.trendingBooks.length,
                itemBuilder: (context, index) {
                  final book = _bookService.trendingBooks[index];
                  return _BookCard(book: book);
                },
              ),
            ),
        ],
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
          // Title
          const Text(
            'تقنيات مصممة لأجلك',
            style: TextStyle(
              fontSize: 24,
              fontWeight: FontWeight.bold,
              color: AppTheme.textPrimary,
            ),
          ),
          const SizedBox(height: 8),
          const Text(
            'نستخدم أحدث تقنيات الذكاء الاصطناعي لضمان أفضل تجربة قراءة',
            textAlign: TextAlign.center,
            style: TextStyle(
              color: AppTheme.textSecondary,
            ),
          ),
          const SizedBox(height: 32),

          // Features grid
          Wrap(
            spacing: 16,
            runSpacing: 16,
            alignment: WrapAlignment.center,
            children: [
              SizedBox(
                width: 160,
                child: FeatureCard(
                  icon: Icons.psychology,
                  title: 'توصيات مخصصة',
                  description: 'نحلل قراءاتك لنقترح كتباً ستعشقها',
                  iconGradient: AppTheme.primaryGradient,
                ),
              ),
              SizedBox(
                width: 160,
                child: FeatureCard(
                  icon: Icons.chat_bubble_outline,
                  title: 'محادثة مع الكتب',
                  description: 'اسأل أي سؤال عن محتوى الكتاب',
                  iconGradient: AppTheme.magentaGradient,
                ),
              ),
              SizedBox(
                width: 160,
                child: FeatureCard(
                  icon: Icons.analytics_outlined,
                  title: 'تحليلات ذكية',
                  description: 'تتبع عادات قراءتك واحصل على رؤى',
                  iconGradient: AppTheme.cyanGradient,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildCTASection() {
    final auth = context.watch<AuthService>();
    if (auth.isLoggedIn) return const SizedBox();

    return Container(
      margin: const EdgeInsets.all(24),
      padding: const EdgeInsets.all(32),
      decoration: BoxDecoration(
        gradient: AppTheme.fullGradient,
        borderRadius: BorderRadius.circular(AppTheme.radiusXl),
      ),
      child: Column(
        children: [
          const Text(
            'جاهز للبدء؟',
            style: TextStyle(
              fontSize: 28,
              fontWeight: FontWeight.bold,
              color: Colors.white,
            ),
          ),
          const SizedBox(height: 12),
          const Text(
            'انضم اليوم مجاناً وابدأ رحلة استكشاف لا تنتهي من المعرفة والمتعة.',
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: 16,
              color: Colors.white70,
            ),
          ),
          const SizedBox(height: 24),
          ElevatedButton(
            onPressed: () {
              Navigator.push(
                context,
                MaterialPageRoute(builder: (_) => const LoginScreen()),
              );
            },
            style: ElevatedButton.styleFrom(
              backgroundColor: Colors.white,
              foregroundColor: AppTheme.gradient2,
              padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 16),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(AppTheme.radiusLg),
              ),
            ),
            child: const Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  'أنشئ حساب مجاني',
                  style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
                ),
                SizedBox(width: 8),
                Icon(Icons.arrow_back),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// Book Card Widget
class _BookCard extends StatelessWidget {
  final Map<String, dynamic> book;

  const _BookCard({required this.book});

  @override
  Widget build(BuildContext context) {
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
        width: 150,
        margin: const EdgeInsets.only(left: 16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Cover
            Container(
              height: 210,
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(AppTheme.radiusMd),
                boxShadow: AppTheme.shadowMd,
              ),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(AppTheme.radiusMd),
                child: Stack(
                  fit: StackFit.expand,
                  children: [
                    // Cover image
                    coverUrl.isNotEmpty
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
                                _buildPlaceholder(title),
                          )
                        : _buildPlaceholder(title),

                    // Gradient overlay
                    Positioned(
                      bottom: 0,
                      left: 0,
                      right: 0,
                      height: 60,
                      child: Container(
                        decoration: BoxDecoration(
                          gradient: LinearGradient(
                            begin: Alignment.topCenter,
                            end: Alignment.bottomCenter,
                            colors: [
                              Colors.transparent,
                              Colors.black.withOpacity(0.7),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
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

  Widget _buildPlaceholder(String title) {
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
