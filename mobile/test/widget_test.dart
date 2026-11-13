// Small tests that need no camera, microphone or network.
// Run with: flutter test
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:voice_assistant_eyes/assistant_client.dart';
import 'package:voice_assistant_eyes/languages.dart';
import 'package:voice_assistant_eyes/settings.dart';

void main() {
  testWidgets('Settings screen saves IP, language and mock mode', (tester) async {
    SharedPreferences.setMockInitialValues({}); // fake phone storage

    await tester.pumpWidget(const MaterialApp(home: SettingsScreen()));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), '192.168.1.20');
    await tester.tap(find.text('Français'));
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();

    final saved = await SettingsStore.load();
    expect(saved.serverIp, '192.168.1.20');
    expect(saved.language.code, 'fr');
    expect(saved.mock, true); // mock is on by default
  });

  testWidgets('Settings screen rejects a full URL', (tester) async {
    SharedPreferences.setMockInitialValues({});

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
}
