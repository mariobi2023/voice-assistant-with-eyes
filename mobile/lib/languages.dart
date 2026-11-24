// The three supported languages, and the few sentences the app itself speaks.

class AppLanguage {
  const AppLanguage({
    required this.code,
    required this.name,
    required this.speechLocale,
    required this.ttsLocale,
    required this.isRtl,
    required this.didNotHear,
    required this.serverError,
    required this.notSure,
  });

  final String code; // sent to the backend: "en", "fr", "ar"
  final String name; // shown in settings
  final String speechLocale; // preferred speech_to_text locale
  final String ttsLocale; // flutter_tts voice
  final bool isRtl; // Arabic is written right-to-left
  final String didNotHear; // spoken when no question was heard
  final String serverError; // spoken when the backend can't be reached
  final String notSure; // the "I'm not sure" answer
}

const english = AppLanguage(
  code: 'en',
  name: 'English',
  speechLocale: 'en_US',
  ttsLocale: 'en-US',
  isRtl: false,
  didNotHear: "I didn't hear a question. Please try again.",
  serverError: "I can't reach the server right now.",
  notSure: "I'm not sure.",
);

const french = AppLanguage(
  code: 'fr',
  name: 'Français',
  speechLocale: 'fr_FR',
  ttsLocale: 'fr-FR',
  isRtl: false,
  didNotHear: "Je n'ai pas entendu de question. Veuillez réessayer.",
  serverError: "Je n'arrive pas à joindre le serveur.",
  notSure: 'Je ne suis pas sûr.',
);

const arabic = AppLanguage(
  code: 'ar',
  name: 'العربية',
  speechLocale: 'ar_SA',
  ttsLocale: 'ar-SA',
  isRtl: true,
  didNotHear: 'لم أسمع سؤالاً. حاول مرة أخرى.',
  serverError: 'لا أستطيع الوصول إلى الخادم الآن.',
  notSure: 'لست متأكداً.',
);

const allLanguages = [english, french, arabic];

// Find a language by its code ("en", "fr", "ar"); English if unknown.
AppLanguage languageFromCode(String code) =>
    allLanguages.firstWhere((l) => l.code == code, orElse: () => english);

// ---------- Never say "safe" ----------
// Project rule: the assistant must NEVER tell the user that something is safe.
// Same idea as the server (server/app/languages.py): any sentence with one of these
// words, in any of the three languages, is removed before it is spoken.
// "pas sûr" (= not sure) is allowed, so "Je ne suis pas sûr" is kept.
final _safePatterns = [
  RegExp('safe', caseSensitive: false), // also "safely", "safety", "unsafe"
  RegExp(r'\bno danger\b', caseSensitive: false),
  RegExp(r'\bsans (danger|risque)\b', caseSensitive: false),
  RegExp(r'\ben sécurité|\bsécuritaire|\bsécurisée?s?\b', caseSensitive: false),
  RegExp(r'(?<!pas )\bsûre?s?\b', caseSensitive: false),
  RegExp('آمن|أمان|مأمون|لا خطر|بدون خطر'),
];

// Drop every sentence that says something is safe. Returns the rest ('' if nothing is left).
String removeSafeClaims(String text) {
  final sentences = text.trim().split(RegExp(r'(?<=[.!?؟])\s+'));
  final kept = sentences.where((s) => !_safePatterns.any((p) => p.hasMatch(s)));
  return kept.join(' ').trim();
}
