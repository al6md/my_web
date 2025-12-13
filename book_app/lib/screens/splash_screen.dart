import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:google_fonts/google_fonts.dart';
import '../services/auth_service.dart';
import 'login_screen.dart';
import 'home_screen.dart';

class SplashScreen extends StatefulWidget {
  const SplashScreen({super.key});

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen> {
  @override
  void initState() {
    super.initState();
    _checkAuth();
  }

  Future<void> _checkAuth() async {
    await Future.delayed(const Duration(seconds: 2));
    if (!mounted) return;
    
    final auth = context.read<AuthService>();
    
    Navigator.pushReplacement(
      context,
      MaterialPageRoute(
        builder: (_) => auth.isLoggedIn ? const HomeScreen() : const LoginScreen(),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    const primaryBrown = Color(0xFF622204);
    const lightCream = Color(0xFFFBF5E6);
    
    return Scaffold(
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [
              lightCream,
              Color(0xFFE7D8B5),
            ],
          ),
        ),
        child: Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              // Logo - مثل الموقع
              Container(
                padding: const EdgeInsets.all(24),
                decoration: BoxDecoration(
                  color: primaryBrown,
                  borderRadius: BorderRadius.circular(20),
                ),
                child: const Icon(
                  Icons.auto_stories,
                  size: 64,
                  color: Colors.white,
                ),
              ),
              const SizedBox(height: 24),
              // App Name
              Text(
                'ALHAM',
                style: GoogleFonts.cairo(
                  fontSize: 48,
                  fontWeight: FontWeight.bold,
                  color: primaryBrown,
                  letterSpacing: 4,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                'توصيات ذكية',
                style: GoogleFonts.cairo(
                  fontSize: 20,
                  color: primaryBrown.withOpacity(0.7),
                ),
              ),
              const SizedBox(height: 48),
              CircularProgressIndicator(
                color: primaryBrown,
                strokeWidth: 3,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
