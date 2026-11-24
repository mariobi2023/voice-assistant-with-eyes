// Sends the question to the backend: POST http://<server-ip>:8000/ask  (server/app/main.py)
//   request:  {"question": "...", "language": "en" | "fr" | "ar"}   (question: 1-500 characters)
//   response: {"answer": "...", "confidence": 0.8, "frame_ids": [1, 2]}
//   errors:   {"detail": ...} with HTTP 422 (bad request) or 500 (server problem)
// In MOCK mode it returns fake answers instead (no backend needed).
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import 'languages.dart';

const int kBackendPort = 8000;
const Duration kAskTimeout = Duration(seconds: 15); // the server answers within 12 s
const int kMaxQuestionLength = 500; // the server refuses longer questions (HTTP 422)

class AskResult {
  const AskResult(this.answer, this.confidence);
  final String answer;
  final double confidence;
}

// Why asking failed. Each kind has its own spoken sentence (languages.dart).
enum AskFailure { unreachable, timeout, serverError }

class AskException implements Exception {
  const AskException(this.kind, this.detail);
  final AskFailure kind;
  final String detail; // technical detail, for the debug log only

  // The sentence to speak to the user, in their language.
  String message(AppLanguage lang) => switch (kind) {
        AskFailure.unreachable => lang.serverUnreachable,
        AskFailure.timeout => lang.serverTimeout,
        AskFailure.serverError => lang.serverError,
      };

  @override
  String toString() => 'AskException($kind: $detail)';
}

// Ask the real backend. Throws AskException if anything goes wrong.
Future<AskResult> askBackend(String serverIp, String question, AppLanguage lang) async {
  final http.Response response;
  try {
    response = await http
        .post(
          Uri.parse('http://$serverIp:$kBackendPort/ask'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({
            'question': question.length > kMaxQuestionLength
                ? question.substring(0, kMaxQuestionLength)
                : question,
            'language': lang.code,
          }),
        )
        .timeout(kAskTimeout);
  } on TimeoutException {
    throw const AskException(AskFailure.timeout, 'no answer within 15 s');
  } on SocketException catch (e) {
    throw AskException(AskFailure.unreachable, e.message); // wrong IP, other Wi-Fi, server off
  } on http.ClientException catch (e) {
    throw AskException(AskFailure.unreachable, e.message);
  } on FormatException catch (e) {
    throw AskException(AskFailure.unreachable, 'bad server IP: ${e.message}');
  }

  if (response.statusCode != 200) {
    throw AskException(AskFailure.serverError, 'HTTP ${response.statusCode}: ${response.body}');
  }
  try {
    final data = jsonDecode(utf8.decode(response.bodyBytes)); // utf8 → Arabic/French accents OK
    return AskResult(data['answer'] as String, (data['confidence'] as num?)?.toDouble() ?? 0);
  } catch (e) {
    throw AskException(AskFailure.serverError, 'unexpected reply: $e');
  }
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
