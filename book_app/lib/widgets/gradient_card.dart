import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

/// Gradient Card Widget - Glass effect with gradient border on hover
class GradientCard extends StatefulWidget {
  final Widget child;
  final EdgeInsetsGeometry? padding;
  final VoidCallback? onTap;
  final bool enableHover;
  final BorderRadius? borderRadius;

  const GradientCard({
    super.key,
    required this.child,
    this.padding,
    this.onTap,
    this.enableHover = true,
    this.borderRadius,
  });

  @override
  State<GradientCard> createState() => _GradientCardState();
}

class _GradientCardState extends State<GradientCard>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _scaleAnimation;
  bool _isHovered = false;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      duration: const Duration(milliseconds: 200),
      vsync: this,
    );
    _scaleAnimation = Tween<double>(begin: 1.0, end: 1.02).animate(
      CurvedAnimation(parent: _controller, curve: Curves.easeOut),
    );
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _onHoverChanged(bool isHovered) {
    if (!widget.enableHover) return;
    setState(() => _isHovered = isHovered);
    if (isHovered) {
      _controller.forward();
    } else {
      _controller.reverse();
    }
  }

  @override
  Widget build(BuildContext context) {
    final borderRadius =
        widget.borderRadius ?? BorderRadius.circular(AppTheme.radiusXl);

    return MouseRegion(
      onEnter: (_) => _onHoverChanged(true),
      onExit: (_) => _onHoverChanged(false),
      child: GestureDetector(
        onTap: widget.onTap,
        child: AnimatedBuilder(
          animation: _scaleAnimation,
          builder: (context, child) {
            return Transform.scale(
              scale: _scaleAnimation.value,
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 200),
                decoration: BoxDecoration(
                  borderRadius: borderRadius,
                  gradient: _isHovered
                      ? LinearGradient(
                          begin: Alignment.topLeft,
                          end: Alignment.bottomRight,
                          colors: [
                            AppTheme.gradient1.withOpacity(0.3),
                            AppTheme.gradient3.withOpacity(0.3),
                          ],
                        )
                      : null,
                  border: Border.all(
                    color: _isHovered
                        ? AppTheme.gradient1.withOpacity(0.5)
                        : AppTheme.borderSubtle,
                    width: 1,
                  ),
                  boxShadow: _isHovered ? AppTheme.shadowLg : AppTheme.shadowSm,
                ),
                child: ClipRRect(
                  borderRadius: borderRadius,
                  child: Container(
                    decoration: BoxDecoration(
                      color: AppTheme.bgCard,
                      borderRadius: borderRadius,
                    ),
                    padding: widget.padding ?? const EdgeInsets.all(16),
                    child: widget.child,
                  ),
                ),
              ),
            );
          },
        ),
      ),
    );
  }
}

/// Glass Card - Frosted glass effect
class GlassCard extends StatelessWidget {
  final Widget child;
  final EdgeInsetsGeometry? padding;
  final VoidCallback? onTap;
  final BorderRadius? borderRadius;
  final Color? backgroundColor;

  const GlassCard({
    super.key,
    required this.child,
    this.padding,
    this.onTap,
    this.borderRadius,
    this.backgroundColor,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        decoration: BoxDecoration(
          color: backgroundColor ?? AppTheme.bgGlass,
          borderRadius:
              borderRadius ?? BorderRadius.circular(AppTheme.radiusXl),
          border: Border.all(color: AppTheme.borderSubtle),
          boxShadow: AppTheme.shadowMd,
        ),
        padding: padding ?? const EdgeInsets.all(16),
        child: child,
      ),
    );
  }
}

/// Gradient Border Card - Shows gradient border on all sides
class GradientBorderCard extends StatelessWidget {
  final Widget child;
  final EdgeInsetsGeometry? padding;
  final double borderWidth;
  final List<Color>? gradientColors;

  const GradientBorderCard({
    super.key,
    required this.child,
    this.padding,
    this.borderWidth = 2,
    this.gradientColors,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: gradientColors ??
              [
                AppTheme.gradient1,
                AppTheme.gradient2,
                AppTheme.gradient3,
              ],
        ),
        borderRadius: BorderRadius.circular(AppTheme.radiusXl),
      ),
      padding: EdgeInsets.all(borderWidth),
      child: Container(
        decoration: BoxDecoration(
          color: AppTheme.bgSurface,
          borderRadius: BorderRadius.circular(AppTheme.radiusXl - borderWidth),
        ),
        padding: padding ?? const EdgeInsets.all(16),
        child: child,
      ),
    );
  }
}

/// Feature Card - Icons with gradient background
class FeatureCard extends StatelessWidget {
  final IconData icon;
  final String title;
  final String description;
  final Gradient? iconGradient;
  final VoidCallback? onTap;

  const FeatureCard({
    super.key,
    required this.icon,
    required this.title,
    required this.description,
    this.iconGradient,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GradientCard(
      onTap: onTap,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // Icon with gradient background
          Container(
            width: 70,
            height: 70,
            decoration: BoxDecoration(
              gradient: iconGradient ?? AppTheme.primaryGradient,
              borderRadius: BorderRadius.circular(AppTheme.radiusLg),
              boxShadow: AppTheme.glowPrimary,
            ),
            child: Icon(
              icon,
              size: 32,
              color: Colors.white,
            ),
          ),
          const SizedBox(height: 16),
          // Title
          Text(
            title,
            style: const TextStyle(
              fontSize: 18,
              fontWeight: FontWeight.bold,
              color: AppTheme.textPrimary,
            ),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 8),
          // Description
          Text(
            description,
            style: const TextStyle(
              fontSize: 14,
              color: AppTheme.textSecondary,
            ),
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }
}

/// Stats Card - For displaying statistics
class StatsCard extends StatelessWidget {
  final String value;
  final String label;
  final bool useGradient;

  const StatsCard({
    super.key,
    required this.value,
    required this.label,
    this.useGradient = true,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        ShaderMask(
          shaderCallback: useGradient
              ? (bounds) => AppTheme.accentGradient.createShader(bounds)
              : (bounds) => const LinearGradient(
                    colors: [AppTheme.textPrimary, AppTheme.textPrimary],
                  ).createShader(bounds),
          child: Text(
            value,
            style: const TextStyle(
              fontSize: 32,
              fontWeight: FontWeight.w800,
              color: Colors.white,
            ),
          ),
        ),
        const SizedBox(height: 4),
        Text(
          label,
          style: const TextStyle(
            fontSize: 14,
            color: AppTheme.textMuted,
          ),
        ),
      ],
    );
  }
}
