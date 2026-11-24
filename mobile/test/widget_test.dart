// Small tests that need no camera, microphone or network.
// Run with: flutter test
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:voice_assistant_eyes/assistant_client.dart';
import 'package:voice_assistant_eyes/languages.dart';
import 'package:voice_assistant_eyes/settings.dart';
import 'package:voice_assistant_eyes/warning_client.dart';

// The default test window is 800x600: too short, the Save button ends up below the edge
// and the tap misses it. Use a phone-sized screen instead (1080x2400 pixels, like a
// typical Android phone = 411x914 on screen).
void usePhoneScreen(WidgetTester tester) {
  tester.view.physicalSize = const Size(1080, 2400);
  tester.view.devicePixelRatio = 2.625;
  addTearDown(tester.view.reset); // back to normal after the test
}

void main() {
  testWidgets('Settings screen saves IP, language and mock mode', (tester) async {
    SharedPreferences.setMockInitialValues({}); // fake phone storage
    usePhoneScreen(tester);

    await tester.pumpWidget(const MaterialApp(home: SettingsScreen()));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), '192.168.1.20');
    await tester.tap(find.text('Français'));
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();

    final saved = await SettingsStore.load();
    expect(saved.serverIp, '192.168.1.20');
    expect(saved.language.code, 'fr');
    expect(saved.mock, false); // mock is off by default: real backend
  });

  testWidgets('Settings screen rejects a full URL', (tester) async {
    SharedPreferences.setMockInitialValues({});
    usePhoneScreen(tester);

    await tester.pumpWidget(const MaterialApp(home: SettingsScreen()));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'http://192.168.1.20');
    await tester.tap(find.text('Save'));
    await tester.pump();

    expect(find.textContaining('Type only the IP'), findsOneWidget);
    expect((await SettingsStore.load()).serverIp, '');
  });

  test('Mock answers are in the chosen language and include "not sure"', () async {
    for (final lang in allLanguages) {
      final answers = [for (var i = 0; i < 3; i++) (await askMock(lang)).answer];
      expect(answers.any((a) => a.startsWith(lang.notSure.replaceAll('.', ''))), true);
      // The assistant must never say something is "safe".
      expect(answers.any((a) => a.toLowerCase().contains('safe')), false);
    }
  });

  test('A warning message from the server is read correctly', () {
    final w = parseWarning('{"type":"warning","data":{"text":"Attention : escalier.","language":"fr"}}', english);
    expect(w!.text, 'Attention : escalier.');
    expect(w.language.code, 'fr');

    // Unknown language → the language chosen in Settings.
    expect(parseWarning('{"type":"warning","data":{"text":"Door ahead."}}', arabic)!.language.code, 'ar');

    // Not a warning, broken JSON, or empty text → ignored.
    expect(parseWarning('{"type":"frame","data":{}}', english), isNull);
    expect(parseWarning('not json', english), isNull);
    expect(parseWarning('{"type":"warning","data":{"text":""}}', english), isNull);
  });

  test('Warnings never say "safe"', () {
    expect(removeSafeClaims('Stairs ahead. The path is safe.'), 'Stairs ahead.');
    expect(removeSafeClaims('Escalier devant vous. Le passage est sans danger.'), 'Escalier devant vous.');
    expect(removeSafeClaims('Je ne suis pas sûr.'), 'Je ne suis pas sûr.'); // "not sure" is allowed
    expect(removeSafeClaims('الطريق آمن.'), '');
    expect(parseWarning('{"type":"warning","data":{"text":"It is safe."}}', english), isNull);
  });

  test('Mock warnings are in the chosen language and never say "safe"', () {
    for (final lang in allLanguages) {
      for (var i = 0; i < 2; i++) {
        final w = mockWarning(lang, i);
        expect(w.language, lang);
        expect(removeSafeClaims(w.text), w.text);
      }
    }
  });

  test('Server error messages exist in every language and never say "safe"', () {
    for (final lang in allLanguages) {
      for (final kind in AskFailure.values) {
        final text = AskException(kind, '').message(lang);
        expect(text, isNotEmpty);
        expect(removeSafeClaims(text), text);
      }
      expect(removeSafeClaims(lang.noServerIp), lang.noServerIp);
    }
  });
}
