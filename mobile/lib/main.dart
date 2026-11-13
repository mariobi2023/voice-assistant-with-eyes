// Entry point of the app: sets the high-contrast theme and opens the stream screen.
import 'package:material_ui/material_ui.dart';

import 'stream_screen.dart';

// Colours shared by all screens (same idea as the dashboard: black, white, yellow).
const Color kAccent = Color(0xFFFFD400); // yellow
const Color kOk = Color(0xFF4CFF7A); // green  → "Live"
const Color kWarn = Color(0xFFFF8C42); // orange → "Error"

void main() {
  runApp(const VoiceAssistantApp());
}

class VoiceAssistantApp extends StatelessWidget {
  const VoiceAssistantApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Voice Assistant With Eyes',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        brightness: Brightness.dark,
        scaffoldBackgroundColor: Colors.black,
        colorScheme: const ColorScheme.dark(
          primary: kAccent,
          onPrimary: Colors.black,
          surface: Colors.black,
          onSurface: Colors.white,
          error: kWarn,
        ),
        appBarTheme: const AppBarTheme(
          backgroundColor: Colors.black,
          foregroundColor: kAccent,
          titleTextStyle: TextStyle(color: kAccent, fontSize: 24, fontWeight: FontWeight.bold),
        ),
      ),
      home: const StreamScreen(),
    );
  }
}
