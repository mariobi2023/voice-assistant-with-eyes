// The big "Ask" button and the last question/answer.
// One tap: vibrate → listen → vibrate → send question → speak the answer.
// Works whether or not the camera is streaming (streaming uses no microphone).
import 'package:flutter/services.dart' show HapticFeedback;
import 'package:material_ui/material_ui.dart';

import 'assistant_client.dart';
import 'languages.dart';
import 'main.dart' show kAccent;
import 'settings.dart';
import 'voice_service.dart';

enum AskState { idle, listening, thinking, speaking }

class AskPanel extends StatefulWidget {
  const AskPanel({super.key});

  @override
  State<AskPanel> createState() => _AskPanelState();
}

class _AskPanelState extends State<AskPanel> {
  final _voice = VoiceService();
  AskState _state = AskState.idle;
  String _question = '';
  String _answer = '';
  AppLanguage _language = english;

  @override
  void dispose() {
    _voice.stopListening();
    _voice.stopSpeaking();
    super.dispose();
  }

  Future<void> _onPressed() async {
    // A second tap stops listening early / stops speaking.
    if (_state == AskState.listening) return _voice.stopListening();
    if (_state == AskState.speaking) return _voice.stopSpeaking();
    if (_state != AskState.idle) return; // thinking: wait for the answer

    // Read the latest settings (language, mock mode, IP).
    final settings = await SettingsStore.load();
    final lang = settings.language;
    setState(() {
      _language = lang;
      _question = '';
      _answer = '';
    });

    // 1) Listen. Vibrate at the start and at the end.
    String question = '';
    _setState(AskState.listening);
    HapticFeedback.vibrate();
    try {
      question = await _voice.listen(lang);
    } catch (_) {
      // Speech recognition not available: question stays empty.
    }
    HapticFeedback.vibrate();

    if (question.isEmpty) {
      await _say(lang.didNotHear, lang);
      return;
    }
    setState(() => _question = question);

    // 2) Ask (mock or real backend).
    _setState(AskState.thinking);
    String answer;
    try {
      final result = settings.mock
          ? await askMock(lang)
          : await askBackend(settings.serverIp, question, lang);
      answer = result.answer;
    } catch (_) {
      answer = lang.serverError; // no server, timeout (15 s), or bad reply
    }

    // 3) Speak the answer in the same language.
    await _say(answer, lang);
  }

  // Show and speak a sentence, then go back to idle.
  Future<void> _say(String text, AppLanguage lang) async {
    setState(() => _answer = text);
    _setState(AskState.speaking);
    await _voice.speak(text, lang);
    _setState(AskState.idle);
  }

  void _setState(AskState state) {
    if (mounted) setState(() => _state = state);
  }

  String get _buttonText => switch (_state) {
        AskState.idle => 'Ask',
        AskState.listening => 'Listening… tap to stop',
        AskState.thinking => 'Thinking…',
        AskState.speaking => 'Speaking… tap to stop',
      };

  @override
  Widget build(BuildContext context) {
    // Arabic text is shown right-to-left.
    final direction = _language.isRtl ? TextDirection.rtl : TextDirection.ltr;
    const textStyle = TextStyle(fontSize: 22, color: Colors.white);
    const labelStyle = TextStyle(fontSize: 16, color: Colors.white70);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        // Last question and answer (also useful for a sighted helper).
        // Labels are on their own line so they don't get mixed into Arabic text.
        if (_question.isNotEmpty) ...[
          const Text('You asked', style: labelStyle),
          Text(_question, style: textStyle, textDirection: direction),
        ],
        if (_answer.isNotEmpty) ...[
          const Text('Answer', style: labelStyle),
          Text(_answer,
              style: textStyle.copyWith(fontWeight: FontWeight.bold), textDirection: direction),
        ],
        const SizedBox(height: 12),

        // The big Ask button. TalkBack reads the label and the hint.
        Semantics(
          button: true,
          liveRegion: true, // TalkBack announces "Listening", "Thinking"...
          hint: 'Ask a question about what the camera sees',
          child: SizedBox(
            height: 140,
            child: ElevatedButton(
              style: ElevatedButton.styleFrom(
                backgroundColor: _state == AskState.idle ? Colors.white : kAccent,
                foregroundColor: Colors.black,
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
              ),
              onPressed: _state == AskState.thinking ? null : _onPressed,
              child: Text(
                _buttonText,
                textAlign: TextAlign.center,
                style: const TextStyle(fontSize: 34, fontWeight: FontWeight.bold),
              ),
            ),
          ),
        ),
      ],
    );
  }
}
