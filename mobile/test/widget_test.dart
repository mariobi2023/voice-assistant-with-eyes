// Small test of the settings screen (no camera or network needed).
// Run with: flutter test
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:voice_assistant_eyes/settings.dart';

void main() {
  testWidgets('Settings screen saves the server IP', (tester) async {
    SharedPreferences.setMockInitialValues({}); // fake phone storage

    await tester.pumpWidget(const MaterialApp(home: SettingsScreen()));
    await tester.enterText(find.byType(TextField), '192.168.1.20');
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();

    expect(await SettingsStore.loadServerIp(), '192.168.1.20');
  });

  testWidgets('Settings screen rejects a full URL', (tester) async {
    SharedPreferences.setMockInitialValues({});

    await tester.pumpWidget(const MaterialApp(home: SettingsScreen()));
    await tester.enterText(find.byType(TextField), 'http://192.168.1.20');
    await tester.tap(find.text('Save'));
    await tester.pump();

    expect(find.textContaining('Type only the IP'), findsOneWidget);
    expect(await SettingsStore.loadServerIp(), '');
  });
}
