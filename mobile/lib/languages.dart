// The three supported languages, and the few sentences the app itself speaks.

class AppLanguage {
  const AppLanguage({
    required this.code,
    required this.name,
    required this.speechLocale,
    required this.ttsLocale,
    required this.isRtl,
    required this.didNotHear,
    required this.noServerIp,
    required this.serverUnreachable,
    required this.serverTimeout,
    required this.serverError,
    required this.notSure,
    required this.volumeHint,
    required this.streamingStarted,
    required this.streamingFailed,
    required this.streamingLost,
  });

  final String code; // sent to the backend: "en", "fr", "ar"
  final String name; // shown in settings
  final String speechLocale; // preferred speech_to_text locale
  final String ttsLocale; // flutter_tts voice
  final bool isRtl; // Arabic is written right-to-left
  final String didNotHear; // spoken when no question was heard
  final String noServerIp; // no IP in Settings (and mock mode is off)
  final String serverUnreachable; // nothing answers at that IP (wrong IP, other Wi-Fi, server off)
  final String serverTimeout; // the server did not answer within 15 s
  final String serverError; // the server answered, but with an error
  final String notSure; // the "I'm not sure" answer
  final String volumeHint; // spoken once, the first time the app opens
  final String streamingStarted; // the camera is now sent to the server
  final String streamingFailed; // streaming could not start
  final String streamingLost; // streaming stopped by itself
}

const english = AppLanguage(
  code: 'en',
  name: 'English',
  speechLocale: 'en_US',
  ttsLocale: 'en-US',
  isRtl: false,
  didNotHear: "I didn't hear a question. Please try again.",
  noServerIp: 'No server IP set. Please open Settings.',
  serverUnreachable: 'Server not reachable. Check the IP and the Wi-Fi.',
  serverTimeout: 'The server took too long to answer. Please try again.',
  serverError: 'The server had a problem. Please try again.',
  notSure: "I'm not sure.",
  volumeHint: 'Press volume up to ask a question.',
  streamingStarted: 'Streaming started.',
  streamingFailed: 'Streaming could not start. Check the IP and the Wi-Fi.',
  streamingLost: 'Streaming stopped. The connection was lost.',
);

const french = AppLanguage(
  code: 'fr',
  name: 'Français',
  speechLocale: 'fr_FR',
  ttsLocale: 'fr-FR',
  isRtl: false,
  didNotHear: "Je n'ai pas entendu de question. Veuillez réessayer.",
  noServerIp: "Aucune adresse IP de serveur. Ouvrez les réglages.",
  serverUnreachable: "Serveur injoignable. Vérifiez l'adresse IP et le Wi-Fi.",
  serverTimeout: 'Le serveur a mis trop de temps à répondre. Veuillez réessayer.',
  serverError: 'Le serveur a rencontré un problème. Veuillez réessayer.',
  notSure: 'Je ne suis pas sûr.',
  volumeHint: 'Appuyez sur volume plus pour poser une question.',
  streamingStarted: 'Diffusion démarrée.',
  streamingFailed: "La diffusion n'a pas pu démarrer. Vérifiez l'adresse IP et le Wi-Fi.",
  streamingLost: 'Diffusion arrêtée. La connexion a été perdue.',
);

const arabic = AppLanguage(
  code: 'ar',
  name: 'العربية',
  speechLocale: 'ar_SA',
  ttsLocale: 'ar-SA',
  isRtl: true,
  didNotHear: 'لم أسمع سؤالاً. حاول مرة أخرى.',
  noServerIp: 'لم يتم تعيين عنوان الخادم. افتح الإعدادات.',
  serverUnreachable: 'لا يمكن الوصول إلى الخادم. تحقق من عنوان IP والواي فاي.',
  serverTimeout: 'استغرق الخادم وقتاً طويلاً للرد. حاول مرة أخرى.',
  serverError: 'حدثت مشكلة في الخادم. حاول مرة أخرى.',
  notSure: 'لست متأكداً.',
  volumeHint: 'اضغط على زر رفع الصوت لطرح سؤال.',
  streamingStarted: 'بدأ البث.',
  streamingFailed: 'تعذر بدء البث. تحقق من عنوان IP والواي فاي.',
  streamingLost: 'توقف البث. انقطع الاتصال.',
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
