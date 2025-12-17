import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// Aurora Gradient Theme - Inspired by ALHAM Website
/// Vibrant Design System with Dark Mode and Gradient Accents
class AppTheme {
  // ══════════════════════════════════════════════════════════════════════════
  // 🌈 GRADIENT COLORS
  // ══════════════════════════════════════════════════════════════════════════
  static const Color gradient1 = Color(0xFF667eea);
  static const Color gradient2 = Color(0xFF764ba2);
  static const Color gradient3 = Color(0xFFf093fb);
  static const Color gradient4 = Color(0xFFf5576c);

  // ══════════════════════════════════════════════════════════════════════════
  // 🎨 PRIMARY PALETTE
  // ══════════════════════════════════════════════════════════════════════════
  static const Color primary = Color(0xFF667eea);
  static const Color primaryLight = Color(0xFF818cf8);
  static const Color primaryDark = Color(0xFF4f46e5);

  // ══════════════════════════════════════════════════════════════════════════
  // ✨ ACCENT COLORS
  // ══════════════════════════════════════════════════════════════════════════
  static const Color accentCyan = Color(0xFF22d3ee);
  static const Color accentMagenta = Color(0xFFf472b6);
  static const Color accentPurple = Color(0xFFa855f7);
  static const Color accentOrange = Color(0xFFfb923c);

  // ══════════════════════════════════════════════════════════════════════════
  // 🟢 SEMANTIC COLORS
  // ══════════════════════════════════════════════════════════════════════════
  static const Color success = Color(0xFF10b981);
  static const Color warning = Color(0xFFfbbf24);
  static const Color danger = Color(0xFFef4444);
  static const Color info = Color(0xFF3b82f6);

  // ══════════════════════════════════════════════════════════════════════════
  // 🌙 DARK BACKGROUNDS
  // ══════════════════════════════════════════════════════════════════════════
  static const Color bgBody = Color(0xFF0f0f23);
  static const Color bgSurface = Color(0xFF1a1a2e);
  static const Color bgElevated = Color(0xFF252542);
  static const Color bgCard = Color(0xCC1a1a2e); // 80% opacity
  static const Color bgGlass = Color(0x991a1a2e); // 60% opacity
  static const Color bgInput = Color(0xCC252542);

  // ══════════════════════════════════════════════════════════════════════════
  // 📝 TEXT COLORS
  // ══════════════════════════════════════════════════════════════════════════
  static const Color textPrimary = Colors.white;
  static const Color textSecondary = Color(0xFFa1a1aa);
  static const Color textMuted = Color(0xFF71717a);

  // ══════════════════════════════════════════════════════════════════════════
  // 🔲 BORDERS
  // ══════════════════════════════════════════════════════════════════════════
  static const Color borderSubtle = Color(0x14FFFFFF); // 8% white
  static const Color borderDefault = Color(0x1FFFFFFF); // 12% white
  static const Color borderGlow = Color(0x80667eea); // 50% primary

  // ══════════════════════════════════════════════════════════════════════════
  // 📐 SPACING & RADIUS
  // ══════════════════════════════════════════════════════════════════════════
  static const double radiusSm = 8;
  static const double radiusMd = 12;
  static const double radiusLg = 16;
  static const double radiusXl = 24;
  static const double radius2xl = 32;

  // ══════════════════════════════════════════════════════════════════════════
  // 🎭 GRADIENTS
  // ══════════════════════════════════════════════════════════════════════════
  static const LinearGradient primaryGradient = LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [gradient1, gradient2],
  );

  static const LinearGradient accentGradient = LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [gradient1, gradient3],
  );

  static const LinearGradient fullGradient = LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [gradient1, gradient2, gradient3],
  );

  static const LinearGradient cyanGradient = LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [accentCyan, primary],
  );

  static const LinearGradient magentaGradient = LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [accentMagenta, accentPurple],
  );

  // ══════════════════════════════════════════════════════════════════════════
  // 💫 SHADOWS & GLOWS
  // ══════════════════════════════════════════════════════════════════════════
  static List<BoxShadow> get shadowSm => [
        BoxShadow(
          color: Colors.black.withOpacity(0.3),
          blurRadius: 4,
          offset: const Offset(0, 2),
        ),
      ];

  static List<BoxShadow> get shadowMd => [
        BoxShadow(
          color: Colors.black.withOpacity(0.4),
          blurRadius: 12,
          offset: const Offset(0, 4),
        ),
      ];

  static List<BoxShadow> get shadowLg => [
        BoxShadow(
          color: Colors.black.withOpacity(0.5),
          blurRadius: 24,
          offset: const Offset(0, 8),
        ),
      ];

  static List<BoxShadow> get glowPrimary => [
        BoxShadow(
          color: primary.withOpacity(0.4),
          blurRadius: 20,
          spreadRadius: 0,
        ),
        BoxShadow(
          color: primary.withOpacity(0.2),
          blurRadius: 40,
          spreadRadius: 0,
        ),
      ];

  static List<BoxShadow> get glowCyan => [
        BoxShadow(
          color: accentCyan.withOpacity(0.4),
          blurRadius: 20,
          spreadRadius: 0,
        ),
      ];

  static List<BoxShadow> get glowMagenta => [
        BoxShadow(
          color: accentMagenta.withOpacity(0.4),
          blurRadius: 20,
          spreadRadius: 0,
        ),
      ];

  // ══════════════════════════════════════════════════════════════════════════
  // 🎨 THEME DATA
  // ══════════════════════════════════════════════════════════════════════════
  static ThemeData get darkTheme {
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      colorScheme: const ColorScheme.dark(
        primary: primary,
        onPrimary: Colors.white,
        secondary: accentCyan,
        onSecondary: bgBody,
        tertiary: accentMagenta,
        surface: bgSurface,
        onSurface: textPrimary,
        error: danger,
        onError: Colors.white,
      ),
      scaffoldBackgroundColor: bgBody,

      // AppBar Theme
      appBarTheme: AppBarTheme(
        backgroundColor: bgSurface.withOpacity(0.85),
        foregroundColor: textPrimary,
        elevation: 0,
        centerTitle: true,
        titleTextStyle: GoogleFonts.cairo(
          fontSize: 20,
          fontWeight: FontWeight.bold,
          color: textPrimary,
        ),
      ),

      // Text Theme
      textTheme: GoogleFonts.cairoTextTheme(
        const TextTheme(
          displayLarge:
              TextStyle(color: textPrimary, fontWeight: FontWeight.w800),
          displayMedium:
              TextStyle(color: textPrimary, fontWeight: FontWeight.w700),
          displaySmall:
              TextStyle(color: textPrimary, fontWeight: FontWeight.w700),
          headlineLarge:
              TextStyle(color: textPrimary, fontWeight: FontWeight.w700),
          headlineMedium:
              TextStyle(color: textPrimary, fontWeight: FontWeight.w600),
          headlineSmall:
              TextStyle(color: textPrimary, fontWeight: FontWeight.w600),
          titleLarge:
              TextStyle(color: textPrimary, fontWeight: FontWeight.w600),
          titleMedium:
              TextStyle(color: textPrimary, fontWeight: FontWeight.w500),
          titleSmall:
              TextStyle(color: textSecondary, fontWeight: FontWeight.w500),
          bodyLarge: TextStyle(color: textPrimary),
          bodyMedium: TextStyle(color: textSecondary),
          bodySmall: TextStyle(color: textMuted),
          labelLarge:
              TextStyle(color: textPrimary, fontWeight: FontWeight.w600),
          labelMedium: TextStyle(color: textSecondary),
          labelSmall: TextStyle(color: textMuted),
        ),
      ),

      // Card Theme
      cardTheme: CardTheme(
        color: bgCard,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(radiusXl),
          side: const BorderSide(color: borderSubtle),
        ),
      ),

      // Input Theme
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: bgInput,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(radiusMd),
          borderSide: const BorderSide(color: borderSubtle),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(radiusMd),
          borderSide: const BorderSide(color: borderSubtle),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(radiusMd),
          borderSide: const BorderSide(color: primary, width: 2),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(radiusMd),
          borderSide: const BorderSide(color: danger),
        ),
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
        hintStyle: const TextStyle(color: textMuted),
      ),

      // Elevated Button Theme
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: primary,
          foregroundColor: Colors.white,
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(radiusLg),
          ),
          elevation: 0,
          textStyle: GoogleFonts.cairo(
            fontSize: 16,
            fontWeight: FontWeight.bold,
          ),
        ),
      ),

      // Text Button Theme
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: primaryLight,
          textStyle: GoogleFonts.cairo(
            fontWeight: FontWeight.w600,
          ),
        ),
      ),

      // Icon Theme
      iconTheme: const IconThemeData(
        color: textSecondary,
        size: 24,
      ),

      // Chip Theme
      chipTheme: ChipThemeData(
        backgroundColor: bgElevated,
        labelStyle: GoogleFonts.cairo(color: textPrimary),
        side: const BorderSide(color: borderSubtle),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(radiusSm),
        ),
      ),

      // Bottom Navigation Bar Theme
      bottomNavigationBarTheme: const BottomNavigationBarThemeData(
        backgroundColor: bgSurface,
        selectedItemColor: primary,
        unselectedItemColor: textMuted,
        type: BottomNavigationBarType.fixed,
        elevation: 0,
      ),

      // Navigation Bar Theme (Material 3)
      navigationBarTheme: NavigationBarThemeData(
        backgroundColor: bgSurface,
        indicatorColor: primary.withOpacity(0.2),
        labelTextStyle: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.selected)) {
            return GoogleFonts.cairo(
              color: primary,
              fontWeight: FontWeight.w600,
              fontSize: 12,
            );
          }
          return GoogleFonts.cairo(
            color: textMuted,
            fontSize: 12,
          );
        }),
        iconTheme: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.selected)) {
            return const IconThemeData(color: primary);
          }
          return const IconThemeData(color: textMuted);
        }),
      ),

      // Dialog Theme
      dialogTheme: DialogTheme(
        backgroundColor: bgSurface,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(radiusXl),
        ),
      ),

      // Snackbar Theme
      snackBarTheme: SnackBarThemeData(
        backgroundColor: bgElevated,
        contentTextStyle: GoogleFonts.cairo(color: textPrimary),
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(radiusMd),
        ),
      ),

      // Divider Theme
      dividerTheme: const DividerThemeData(
        color: borderSubtle,
        thickness: 1,
      ),

      // Progress Indicator Theme
      progressIndicatorTheme: const ProgressIndicatorThemeData(
        color: primary,
      ),
    );
  }
}
