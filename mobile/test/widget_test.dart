// Small tests that need no camera, microphone or network.
// Run with: flutter test
import 'dart:convert';

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

  test('SSE messages from /events are read correctly', () {
    final parser = SseParser();
    final lines = [
      'retry: 2000',
      ': connected', // comment: ignored
      '',
      ': ping',
      '',
      'id: 1795000012',
      'event: alert',
      'data: {"id": 1795000012, "type": "stairs", "text": "Escalier devant vous.", "conf": 0.6}',
      '',
    ];
    final messages = [for (final l in lines) parser.addLine(l)].whereType<SseEvent>().toList();
    expect(messages.length, 1); // pings and comments produce no message
    expect(messages.single.event, 'alert');
    expect(messages.single.id, '1795000012');
    expect(parser.retryMs, 2000);

    final w = parseAlert(jsonDecode(messages.single.data), french)!;
    expect(w.id, 1795000012);
    expect(w.text, 'Escalier devant vous.');
    expect(w.language.code, 'fr'); // the language we asked for (?language=fr)

    // Not an alert (no id), or not JSON object → ignored.
    expect(parseAlert({'text': 'Door ahead.'}, english), isNull);
    expect(parseAlert('Door ahead.', english), isNull);
  });

  test('Warnings never say "safe"', () {
    expect(removeSafeClaims('Stairs ahead. The path is safe.'), 'Stairs ahead.');
    expect(removeSafeClaims('Escalier devant vous. Le passage est sans danger.'), 'Escalier devant vous.');
    expect(removeSafeClaims('Je ne suis pas sûr.'), 'Je ne suis pas sûr.'); // "not sure" is allowed
    expect(removeSafeClaims('الطريق آمن.'), '');
    expect(parseAlert({'id': 7, 'text': 'Door ahead. It is safe.'}, english)!.text, 'Door ahead.');
  });

  test('A warning is never spoken twice (ids from /events and /alerts)', () {
    final spoken = <String>[];
    final client = WarningClient(onWarning: (w) => spoken.add(w.text));
    client.deliver(Warning('Stairs ahead.', english, 100));
    client.deliver(Warning('Stairs ahead.', english, 100)); // same alert again after a reconnect
    client.deliver(Warning('Old alert.', english, 99)); // older than the last one spoken
    client.deliver(Warning('', english, 101)); // only said "safe": nothing to say...
    client.deliver(Warning('Door ahead.', english, 102));
    expect(spoken, ['Stairs ahead.', 'Door ahead.']);
    expect(client.lastId, 102); // ...but its id is remembered (sent as after_id)
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

  test('Hands-free sentences exist in every language and never say "safe"', () {
    for (final lang in allLanguages) {
      for (final text in [
        lang.volumeHint,
        lang.streamingStarted,
        lang.streamingFailed,
        lang.streamingLost,
      ]) {
        expect(text, isNotEmpty);
        expect(removeSafeClaims(text), text);
      }
    }
  });

  test('The volume-up hint is spoken only the first time', () async {
    SharedPreferences.setMockInitialValues({}); // a phone that never opened the app
    expect(await SettingsStore.isFirstHint(), true);
    expect(await SettingsStore.isFirstHint(), false);
    expect(await SettingsStore.isFirstHint(), false);
  });
}
