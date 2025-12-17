import 'package:flutter/material.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:provider/provider.dart';
import '../theme/app_theme.dart';
import '../widgets/gradient_card.dart';
import '../widgets/gradient_button.dart';
import '../services/book_service.dart';
import '../services/ai_service.dart';
import '../services/auth_service.dart';

class BookDetailScreen extends StatefulWidget {
  final String gid;

  const BookDetailScreen({super.key, required this.gid});

  @override
  State<BookDetailScreen> createState() => _BookDetailScreenState();
}

class _BookDetailScreenState extends State<BookDetailScreen>
    with SingleTickerProviderStateMixin {
  final BookService _bookService = BookService();
  final AIService _aiService = AIService();

  Map<String, dynamic>? _book;
  bool _isLoading = true;
  String? _error;

  // AI Features state
  String? _aiSummary;
  List<String> _aiQuotes = [];
  List<Map<String, dynamic>> _aiQuiz = [];
  String? _whyLike;
  bool _isLoadingAI = false;
  String? _currentAIFeature;

  // Chat state
  final TextEditingController _chatController = TextEditingController();
  List<Map<String, dynamic>> _chatMessages = [];
  bool _isSendingMessage = false;

  late TabController _tabController;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 3, vsync: this);
    _loadBook();
  }

  @override
  void dispose() {
    _chatController.dispose();
    _tabController.dispose();
    super.dispose();
  }

  Future<void> _loadBook() async {
    setState(() => _isLoading = true);

    final book = await _bookService.getBookDetail(widget.gid);

    if (mounted) {
      setState(() {
        _book = book;
        _isLoading = false;
        _error = book == null ? 'لم يتم العثور على الكتاب' : null;
      });
    }
  }

  Future<void> _loadAISummary() async {
    if (_aiSummary != null) return;

    setState(() {
      _isLoadingAI = true;
      _currentAIFeature = 'summary';
    });

    final result = await _aiService.getBookSummary(widget.gid);

    if (mounted) {
      setState(() {
        _aiSummary = result['summary'] ?? result['error'];
        _isLoadingAI = false;
        _currentAIFeature = null;
      });
    }
  }

  Future<void> _loadAIQuotes() async {
    if (_aiQuotes.isNotEmpty) return;

    setState(() {
      _isLoadingAI = true;
      _currentAIFeature = 'quotes';
    });

    final result = await _aiService.getBookQuotes(widget.gid);

    if (mounted) {
      setState(() {
        _aiQuotes = List<String>.from(result['quotes'] ?? []);
        _isLoadingAI = false;
        _currentAIFeature = null;
      });
    }
  }

  Future<void> _loadAIQuiz() async {
    if (_aiQuiz.isNotEmpty) return;

    setState(() {
      _isLoadingAI = true;
      _currentAIFeature = 'quiz';
    });

    final result = await _aiService.getBookQuiz(widget.gid);

    if (mounted) {
      setState(() {
        _aiQuiz = List<Map<String, dynamic>>.from(result['quiz'] ?? []);
        _isLoadingAI = false;
        _currentAIFeature = null;
      });
    }
  }

  Future<void> _loadWhyLike() async {
    if (_whyLike != null) return;

    setState(() {
      _isLoadingAI = true;
      _currentAIFeature = 'whylike';
    });

    final result = await _aiService.getWhyLike(widget.gid);

    if (mounted) {
      setState(() {
        _whyLike = result['reasons'] ?? result['error'];
        _isLoadingAI = false;
        _currentAIFeature = null;
      });
    }
  }

  Future<void> _sendChatMessage() async {
    final message = _chatController.text.trim();
    if (message.isEmpty) return;

    setState(() {
      _chatMessages.add({'role': 'user', 'content': message});
      _isSendingMessage = true;
    });
    _chatController.clear();

    final result = await _aiService.chatWithBook(widget.gid, message);

    if (mounted) {
      setState(() {
        _chatMessages.add({
          'role': 'assistant',
          'content': result['response'] ?? result['error'] ?? 'حدث خطأ',
        });
        _isSendingMessage = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.bgBody,
      body: _isLoading
          ? const Center(
              child: CircularProgressIndicator(color: AppTheme.primary))
          : _error != null
              ? _buildErrorState()
              : _buildContent(),
    );
  }

  Widget _buildErrorState() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(40),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.error_outline, size: 64, color: AppTheme.danger),
            const SizedBox(height: 16),
            Text(
              _error!,
              style: const TextStyle(color: AppTheme.textSecondary),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 24),
            GradientButton(
              text: 'المحاولة مرة أخرى',
              icon: Icons.refresh,
              onPressed: _loadBook,
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildContent() {
    final book = _book!;
    final coverUrl = book['cover_url'] ?? '';
    final title = book['title'] ?? 'بدون عنوان';
    final author = book['author'] ?? book['authors']?.join(', ') ?? 'غير معروف';
    final description = book['description'] ?? '';
    final categories = book['categories'] as List<dynamic>? ?? [];
    final pageCount = book['page_count'] ?? 0;
    final publishedDate = book['published_date'] ?? '';
    final rating = book['average_rating'] ?? 0.0;

    return CustomScrollView(
      slivers: [
        // App Bar with cover
        _buildSliverAppBar(coverUrl, title),

        // Book Info
        SliverToBoxAdapter(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Title and Author
                Text(
                  title,
                  style: const TextStyle(
                    fontSize: 26,
                    fontWeight: FontWeight.bold,
                    color: AppTheme.textPrimary,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  author,
                  style: const TextStyle(
                    fontSize: 16,
                    color: AppTheme.textSecondary,
                  ),
                ),
                const SizedBox(height: 16),

                // Meta info row
                Wrap(
                  spacing: 16,
                  runSpacing: 8,
                  children: [
                    if (rating > 0)
                      _buildMetaChip(
                        Icons.star,
                        '$rating',
                        AppTheme.warning,
                      ),
                    if (pageCount > 0)
                      _buildMetaChip(
                        Icons.menu_book,
                        '$pageCount صفحة',
                        AppTheme.accentCyan,
                      ),
                    if (publishedDate.isNotEmpty)
                      _buildMetaChip(
                        Icons.calendar_today,
                        publishedDate,
                        AppTheme.accentMagenta,
                      ),
                  ],
                ),
                const SizedBox(height: 16),

                // Categories
                if (categories.isNotEmpty)
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: categories
                        .map((cat) => CategoryPill(text: cat.toString()))
                        .toList(),
                  ),
                const SizedBox(height: 24),

                // Action buttons
                _buildActionButtons(),
                const SizedBox(height: 24),

                // Description
                if (description.isNotEmpty) ...[
                  const Text(
                    'نبذة عن الكتاب',
                    style: TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.bold,
                      color: AppTheme.textPrimary,
                    ),
                  ),
                  const SizedBox(height: 12),
                  Text(
                    _stripHtmlTags(description),
                    style: const TextStyle(
                      color: AppTheme.textSecondary,
                      height: 1.7,
                    ),
                  ),
                  const SizedBox(height: 32),
                ],

                // AI Features Tabs
                _buildAITabs(),
              ],
            ),
          ),
        ),

        // Bottom spacing
        const SliverToBoxAdapter(child: SizedBox(height: 40)),
      ],
    );
  }

  Widget _buildSliverAppBar(String coverUrl, String title) {
    return SliverAppBar(
      expandedHeight: 300,
      pinned: true,
      backgroundColor: AppTheme.bgSurface,
      leading: IconButton(
        icon: Container(
          padding: const EdgeInsets.all(8),
          decoration: BoxDecoration(
            color: AppTheme.bgElevated.withOpacity(0.8),
            borderRadius: BorderRadius.circular(12),
          ),
          child: const Icon(Icons.arrow_back, size: 20),
        ),
        onPressed: () => Navigator.pop(context),
      ),
      actions: [
        IconButton(
          icon: Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              color: AppTheme.bgElevated.withOpacity(0.8),
              borderRadius: BorderRadius.circular(12),
            ),
            child: const Icon(Icons.share, size: 20),
          ),
          onPressed: () {},
        ),
        const SizedBox(width: 8),
      ],
      flexibleSpace: FlexibleSpaceBar(
        background: Stack(
          fit: StackFit.expand,
          children: [
            // Background gradient
            Container(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    AppTheme.gradient1.withOpacity(0.3),
                    AppTheme.bgBody,
                  ],
                ),
              ),
            ),
            // Cover image
            Center(
              child: Hero(
                tag: 'book-${widget.gid}',
                child: Container(
                  width: 150,
                  height: 220,
                  margin: const EdgeInsets.only(top: 40),
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(AppTheme.radiusMd),
                    boxShadow: AppTheme.shadowLg,
                  ),
                  child: ClipRRect(
                    borderRadius: BorderRadius.circular(AppTheme.radiusMd),
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
                                _buildCoverPlaceholder(title),
                          )
                        : _buildCoverPlaceholder(title),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildCoverPlaceholder(String title) {
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
            style: const TextStyle(
              color: Colors.white,
              fontWeight: FontWeight.bold,
              fontSize: 16,
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildMetaChip(IconData icon, String text, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: color.withOpacity(0.1),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: color.withOpacity(0.3)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 16, color: color),
          const SizedBox(width: 6),
          Text(
            text,
            style: TextStyle(color: color, fontWeight: FontWeight.w600),
          ),
        ],
      ),
    );
  }

  Widget _buildActionButtons() {
    return Row(
      children: [
        Expanded(
          child: GradientButton(
            text: 'حفظ الكتاب',
            icon: Icons.bookmark_add_outlined,
            onPressed: () {
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('تم حفظ الكتاب!')),
              );
            },
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: SecondaryButton(
            text: 'قراءة',
            icon: Icons.menu_book,
            onPressed: () {},
          ),
        ),
      ],
    );
  }

  Widget _buildAITabs() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Section title
        Row(
          children: [
            Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                gradient: AppTheme.primaryGradient,
                borderRadius: BorderRadius.circular(8),
              ),
              child:
                  const Icon(Icons.auto_awesome, color: Colors.white, size: 20),
            ),
            const SizedBox(width: 12),
            const Text(
              'ميزات الذكاء الاصطناعي',
              style: TextStyle(
                fontSize: 20,
                fontWeight: FontWeight.bold,
                color: AppTheme.textPrimary,
              ),
            ),
          ],
        ),
        const SizedBox(height: 16),

        // Tab Bar
        Container(
          decoration: BoxDecoration(
            color: AppTheme.bgElevated,
            borderRadius: BorderRadius.circular(AppTheme.radiusMd),
          ),
          child: TabBar(
            controller: _tabController,
            indicator: BoxDecoration(
              gradient: AppTheme.primaryGradient,
              borderRadius: BorderRadius.circular(AppTheme.radiusMd),
            ),
            indicatorSize: TabBarIndicatorSize.tab,
            dividerColor: Colors.transparent,
            labelColor: Colors.white,
            unselectedLabelColor: AppTheme.textMuted,
            labelStyle: const TextStyle(fontWeight: FontWeight.bold),
            tabs: const [
              Tab(text: 'ملخص'),
              Tab(text: 'اقتباسات'),
              Tab(text: 'محادثة'),
            ],
          ),
        ),
        const SizedBox(height: 16),

        // Tab Content
        SizedBox(
          height: 400,
          child: TabBarView(
            controller: _tabController,
            children: [
              _buildSummaryTab(),
              _buildQuotesTab(),
              _buildChatTab(),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildSummaryTab() {
    return GlassCard(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (_aiSummary == null) ...[
            const Spacer(),
            Center(
              child: Column(
                children: [
                  Icon(Icons.summarize, size: 48, color: AppTheme.textMuted),
                  const SizedBox(height: 16),
                  const Text(
                    'احصل على ملخص ذكي للكتاب',
                    style: TextStyle(color: AppTheme.textSecondary),
                  ),
                  const SizedBox(height: 16),
                  GradientButton(
                    text: 'توليد الملخص',
                    icon: Icons.auto_awesome,
                    isLoading: _isLoadingAI && _currentAIFeature == 'summary',
                    onPressed: _loadAISummary,
                  ),
                ],
              ),
            ),
            const Spacer(),
          ] else ...[
            Expanded(
              child: SingleChildScrollView(
                child: Text(
                  _aiSummary!,
                  style: const TextStyle(
                    color: AppTheme.textPrimary,
                    height: 1.7,
                  ),
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildQuotesTab() {
    return GlassCard(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (_aiQuotes.isEmpty) ...[
            const Spacer(),
            Center(
              child: Column(
                children: [
                  Icon(Icons.format_quote, size: 48, color: AppTheme.textMuted),
                  const SizedBox(height: 16),
                  const Text(
                    'اكتشف اقتباسات ملهمة من الكتاب',
                    style: TextStyle(color: AppTheme.textSecondary),
                  ),
                  const SizedBox(height: 16),
                  GradientButton(
                    text: 'توليد الاقتباسات',
                    icon: Icons.lightbulb_outline,
                    isLoading: _isLoadingAI && _currentAIFeature == 'quotes',
                    onPressed: _loadAIQuotes,
                  ),
                ],
              ),
            ),
            const Spacer(),
          ] else ...[
            Expanded(
              child: ListView.builder(
                itemCount: _aiQuotes.length,
                itemBuilder: (context, index) {
                  return Container(
                    margin: const EdgeInsets.only(bottom: 12),
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: AppTheme.bgElevated,
                      borderRadius: BorderRadius.circular(AppTheme.radiusMd),
                      border: Border(
                        right: BorderSide(
                          color: AppTheme.primary,
                          width: 3,
                        ),
                      ),
                    ),
                    child: Text(
                      '"${_aiQuotes[index]}"',
                      style: const TextStyle(
                        color: AppTheme.textPrimary,
                        fontStyle: FontStyle.italic,
                        height: 1.5,
                      ),
                    ),
                  );
                },
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildChatTab() {
    final auth = context.watch<AuthService>();

    if (!auth.isLoggedIn) {
      return GlassCard(
        padding: const EdgeInsets.all(20),
        child: Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(Icons.lock_outline, size: 48, color: AppTheme.textMuted),
              const SizedBox(height: 16),
              const Text(
                'سجل دخولك للمحادثة مع الكتاب',
                style: TextStyle(color: AppTheme.textSecondary),
              ),
            ],
          ),
        ),
      );
    }

    return GlassCard(
      padding: EdgeInsets.zero,
      child: Column(
        children: [
          // Messages
          Expanded(
            child: _chatMessages.isEmpty
                ? Center(
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Icon(Icons.chat_bubble_outline,
                            size: 48, color: AppTheme.textMuted),
                        const SizedBox(height: 16),
                        const Text(
                          'اسأل أي سؤال عن الكتاب',
                          style: TextStyle(color: AppTheme.textSecondary),
                        ),
                      ],
                    ),
                  )
                : ListView.builder(
                    padding: const EdgeInsets.all(16),
                    itemCount: _chatMessages.length,
                    itemBuilder: (context, index) {
                      final msg = _chatMessages[index];
                      final isUser = msg['role'] == 'user';
                      return Align(
                        alignment: isUser
                            ? Alignment.centerRight
                            : Alignment.centerLeft,
                        child: Container(
                          margin: const EdgeInsets.only(bottom: 12),
                          padding: const EdgeInsets.all(12),
                          constraints: BoxConstraints(
                            maxWidth: MediaQuery.of(context).size.width * 0.7,
                          ),
                          decoration: BoxDecoration(
                            gradient: isUser ? AppTheme.primaryGradient : null,
                            color: isUser ? null : AppTheme.bgElevated,
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: Text(
                            msg['content'],
                            style: TextStyle(
                              color:
                                  isUser ? Colors.white : AppTheme.textPrimary,
                            ),
                          ),
                        ),
                      );
                    },
                  ),
          ),

          // Input
          Container(
            padding: const EdgeInsets.all(12),
            decoration: const BoxDecoration(
              border: Border(
                top: BorderSide(color: AppTheme.borderSubtle),
              ),
            ),
            child: Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _chatController,
                    decoration: const InputDecoration(
                      hintText: 'اكتب سؤالك هنا...',
                      border: InputBorder.none,
                      contentPadding: EdgeInsets.symmetric(horizontal: 16),
                    ),
                    onSubmitted: (_) => _sendChatMessage(),
                  ),
                ),
                GradientIconButton(
                  icon: Icons.send,
                  size: 44,
                  onPressed: _isSendingMessage ? null : _sendChatMessage,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  String _stripHtmlTags(String htmlText) {
    return htmlText.replaceAll(RegExp(r'<[^>]*>'), '');
  }
}
