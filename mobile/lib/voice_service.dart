// Voice in and out:
//   listen() → speech_to_text turns the user's voice into text
//   speak()  → flutter_tts reads the answer aloud
import 'dart:async';

import 'package:flutter_tts/flutter_tts.dart';
import 'package:speech_to_text/speech_to_text.dart';

import 'languages.dart';

class VoiceService {
  final _speech = SpeechToText();
  final _tts = FlutterTts();
  bool _ready = false;

  Completer<String>? _pending; // completes with the question when listening ends
  String _words = ''; // what has been recognised so far

  // Prepare speech recognition once (Android asks for microphone permission here).
  Future<bool> _init() async {
    if (_ready) return true;
    _ready = await _speech.initialize(
      onStatus: (status) {
        if (status == 'done') _finish(); // recogniser has stopped
      },
      onError: (_) => _finish(), // e.g. nothing was said
    );
    await _tts.awaitSpeakCompletion(true); // speak() waits until speech is finished
    return _ready;
  }

  // Listen for one question. Stops by itself after 3 s of silence (max 15 s).
  // Returns the recognised text ('' if nothing was heard).
  Future<String> listen(AppLanguage lang) async {
    if (!await _init()) throw Exception('Speech recognition is not available');
    _words = '';
    _pending = Completer<String>();
    await _speech.listen(
      onResult: (result) {
        _words = result.recognizedWords;
        if (result.finalResult) _finish();
      },
      listenOptions: SpeechListenOptions(
        localeId: await _localeFor(lang),
        listenFor: const Duration(seconds: 15),
        pauseFor: const Duration(seconds: 3),
        cancelOnError: true,
      ),
    );
    // Safety net: never wait forever.
    return _pending!.future.timeout(const Duration(seconds: 20), onTimeout: () => _words.trim());
  }

  // Stop listening early (user tapped the button again). The final text still arrives.
  Future<void> stopListening() => _speech.stop();

  void _finish() {
    final pending = _pending;
    _pending = null;
    if (pending != null && !pending.isCompleted) pending.complete(_words.trim());
  }

  // Pick the phone's recognition locale for this language
  // (phones name them differently, e.g. ar_SA or ar_EG).
  Future<String> _localeFor(AppLanguage lang) async {
    final ids = (await _speech.locales()).map((l) => l.localeId).toList();
    if (ids.contains(lang.speechLocale)) return lang.speechLocale;
    return ids.firstWhere((id) => id.toLowerCase().startsWith(lang.code), orElse: () => lang.speechLocale);
  }

  // Read the text aloud in the given language. Returns when speaking is finished.
  Future<void> speak(String text, AppLanguage lang) async {
    await _init();
    await _tts.setLanguage(lang.ttsLocale);
    await _tts.speak(text);
  }

  Future<void> stopSpeaking() => _tts.stop();
}
