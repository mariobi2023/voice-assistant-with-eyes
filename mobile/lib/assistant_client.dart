// Sends the question to the backend: POST http://<server-ip>:8000/ask
//   request:  {"question": "...", "language": "en" | "fr" | "ar"}
//   response: {"answer": "...", "confidence": 0.8, "frame_ids": [1, 2]}
// In MOCK mode it returns fake answers instead (the backend isn't ready yet).
import 'dart:convert';

import 'package:http/http.dart' as http;

import 'languages.dart';

const int kBackendPort = 8000;
const Duration kAskTimeout = Duration(seconds: 15);

class AskResult {
  const AskResult(this.answer, this.confidence);
  final String answer;
  final double confidence;
}

// Ask the real backend.
Future<AskResult> askBackend(String serverIp, String question, AppLanguage lang) async {
  final response = await http
      .post(
        Uri.parse('http://$serverIp:$kBackendPort/ask'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'question': question, 'language': lang.code}),
      )
      .timeout(kAskTimeout);
  if (response.statusCode != 200) {
    throw Exception('Backend answered ${response.statusCode}');
  }
  final data = jsonDecode(utf8.decode(response.bodyBytes)); // utf8 → Arabic/French accents OK
  return AskResult(data['answer'] as String, (data['confidence'] as num?)?.toDouble() ?? 0);
}

// ---------- MOCK mode ----------

// Fake answers per language. The last one is the "I'm not sure" case.
// Like the real assistant: short, only about what the camera saw, never says "safe".
const _mockAnswers = {
  'en': [
    'The sign says "EXIT".',
    'I see a table and a chair in front of you.',
    "I'm not sure. The image is too dark.",
  ],
  'fr': [
    'Le panneau indique « SORTIE ».',
    'Je vois une table et une chaise devant vous.',
    "Je ne suis pas sûr. L'image est trop sombre.",
  ],
  'ar': [
    'اللافتة تقول "مخرج".',
    'أرى طاولة وكرسياً أمامك.',
    'لست متأكداً. الصورة مظلمة جداً.',
  ],
};

int _mockIndex = 0; // rotates through the answers, so every example gets heard

Future<AskResult> askMock(AppLanguage lang) async {
  await Future.delayed(const Duration(milliseconds: 800)); // pretend the server is thinking
  final answers = _mockAnswers[lang.code]!;
  final answer = answers[_mockIndex % answers.length];
  _mockIndex++;
  final isNotSure = answer == answers.last;
  return AskResult(answer, isNotSure ? 0.2 : 0.8);
}
