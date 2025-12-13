import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:google_fonts/google_fonts.dart';
import 'services/auth_service.dart';
import 'screens/splash_screen.dart';

void main() {
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  // ألوان الموقع الأصلية
  static const Color primaryBrown = Color(0xFF622204);
  static const Color lightCream = Color(0xFFFBF5E6);
  static const Color darkBrown = Color(0xFF301101);
  static const Color accentBrown = Color(0xFFE7D8B5);

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => AuthService()..init()),
      ],
      child: MaterialApp(
        title: 'ALHAM - توصيات ذكية',
        debugShowCheckedModeBanner: false,
        theme: ThemeData(
          colorScheme: ColorScheme(
            brightness: Brightness.light,
            primary: primaryBrown,
            onPrimary: Colors.white,
            secondary: accentBrown,
            onSecondary: darkBrown,
            surface: lightCream,
            onSurface: darkBrown,
            error: Colors.red.shade700,
            onError: Colors.white,
          ),
          scaffoldBackgroundColor: lightCream,
          useMaterial3: true,
          textTheme: GoogleFonts.cairoTextTheme(
            Theme.of(context).textTheme,
          ).apply(
            bodyColor: darkBrown,
            displayColor: darkBrown,
          ),
          appBarTheme: AppBarTheme(
            centerTitle: true,
            elevation: 0,
            backgroundColor: lightCream,
            foregroundColor: darkBrown,
            titleTextStyle: GoogleFonts.cairo(
              fontSize: 20,
              fontWeight: FontWeight.bold,
              color: darkBrown,
            ),
          ),
          cardTheme: CardTheme(
            elevation: 4,
            color: Colors.white,
            shadowColor: primaryBrown.withOpacity(0.1),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(16),
            ),
          ),
          inputDecorationTheme: InputDecorationTheme(
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(12),
              borderSide: BorderSide(color: accentBrown),
            ),
            enabledBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(12),
              borderSide: BorderSide(color: accentBrown),
            ),
            focusedBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(12),
              borderSide: BorderSide(color: primaryBrown, width: 2),
            ),
            filled: true,
            fillColor: Colors.white,
          ),
          elevatedButtonTheme: ElevatedButtonThemeData(
            style: ElevatedButton.styleFrom(
              backgroundColor: primaryBrown,
              foregroundColor: Colors.white,
              padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 16),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
              ),
              textStyle: GoogleFonts.cairo(
                fontSize: 16,
                fontWeight: FontWeight.bold,
              ),
            ),
          ),
          textButtonTheme: TextButtonThemeData(
            style: TextButton.styleFrom(
              foregroundColor: primaryBrown,
              textStyle: GoogleFonts.cairo(
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
          chipTheme: ChipThemeData(
            backgroundColor: accentBrown.withOpacity(0.3),
            labelStyle: GoogleFonts.cairo(color: darkBrown),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(20),
            ),
          ),
        ),
        home: const SplashScreen(),
      ),
    );
  }
}
