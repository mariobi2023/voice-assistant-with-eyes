// WarningClient against a small fake backend running inside the test (real HTTP, no phone).
// Kept in its own file: widget tests (testWidgets) block real network calls.
// Run with: flutter test
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:voice_assistant_eyes/languages.dart';
import 'package:voice_assistant_eyes/settings.dart';
import 'package:voice_assistant_eyes/warning_client.dart';

// One alert as the backend writes it on /events.
String sseAlert(int id, String text) =>
    'id: $id\nevent: alert\ndata: ${jsonEncode({'id': id, 'type': 'stairs', 'text': text})}\n\n';

void main() {
  late HttpServer server;
  late WarningClient client;
  final spoken = <String>[];
  final statuses = <WarningStatus>[];

  setUp(() async {
    server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0); // any free port
    spoken.clear();
    statuses.clear();
  });

  tearDown(() async {
    client.stop();
    await server.close(force: true);
  });

  WarningClient makeClient() => WarningClient(
        onWarning: (w) => spoken.add(w.text),
        onStatusChanged: statuses.add,
        port: server.port,
      );

  // Wait (max 15 s) until `n` warnings were spoken.
  Future<void> waitForSpoken(int n) async {
    final deadline = DateTime.now().add(const Duration(seconds: 15));
    while (spoken.length < n && DateTime.now().isBefore(deadline)) {
      await Future<void>.delayed(const Duration(milliseconds: 50));
    }
  }

  test('/events: speaks alerts, reconnects with Last-Event-ID, never speaks one twice', () async {
    final requests = <HttpRequest>[];
    server.listen((request) async {
      requests.add(request);
      final response = request.response
        ..bufferOutput = false // send each write at once, like the real server's stream
        ..headers.contentType = ContentType('text', 'event-stream', charset: 'utf-8');
      if (requests.length == 1) {
        // First connection: a ping, one alert, then the server drops the line.
        response.write('retry: 100\n: connected\n\n: ping\n\n');
        response.write(sseAlert(5, 'Escalier devant vous.'));
        await response.close();
      } else {
        // After the reconnect, the server (wrongly) sends alert 5 again, then a new one.
        response.write(sseAlert(5, 'Escalier devant vous.'));
        response.write(sseAlert(6, 'Porte devant vous. Le passage est sans danger.'));
        await response.flush(); // stays open, like the real /events
      }
    });

    client = makeClient();
    client.start(const AppSettings(serverIp: '127.0.0.1', language: french, mock: false));
    await waitForSpoken(2);

    expect(spoken, ['Escalier devant vous.', 'Porte devant vous.']); // 5 once, "safe" removed
    expect(client.lastId, 6);
    expect(requests.first.uri.path, '/events');
    expect(requests.first.uri.queryParameters, {'language': 'fr', 'after_id': '0'});
    expect(requests[1].uri.queryParameters['after_id'], '5');
    expect(requests[1].headers.value('Last-Event-ID'), '5');
    expect(statuses, contains(WarningStatus.connected));
  });

  test('/events keeps failing: falls back to polling /alerts', () async {
    var polls = 0;
    server.listen((request) async {
      if (request.uri.path == '/events') {
        request.response.statusCode = HttpStatus.internalServerError;
      } else if (request.uri.path == '/alerts') {
        polls++;
        request.response.headers.contentType = ContentType.json;
        // Every poll returns the same alert: it must be spoken only once.
        request.response.write(jsonEncode([
          {'id': 42, 'type': 'door', 'text': 'Door ahead.'},
        ]));
      }
      await request.response.close();
    });

    client = makeClient();
    client.start(const AppSettings(serverIp: '127.0.0.1', language: english, mock: false));
    await waitForSpoken(1);
    await Future<void>.delayed(const Duration(milliseconds: 2500)); // a few more polls

    expect(spoken, ['Door ahead.']);
    expect(polls, greaterThan(1));
    expect(statuses, contains(WarningStatus.polling));
  }, timeout: const Timeout(Duration(seconds: 30)));
}
