// Proactive warnings ("Stairs ahead.") pushed by the backend, without the user asking.
//   connect:  GET http://<server-ip>:8000/events?after_id=<last id>&language=en|fr|ar
//             (Server-Sent Events: ONE open HTTP connection, the server writes each alert)
//   message:  id: 1795000012
//             event: alert
//             data: {"id": 1795000012, "type": "stairs", "text": "Stairs ahead.", ...}
//             (empty line = end of message)
// The server already writes the text in the language we ask for (?language=).
// Uses Dart's built-in HttpClient (dart:io): no extra package.
// In MOCK mode there is no connection: a fake warning comes every 30 seconds instead.
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'assistant_client.dart' show kBackendPort;
import 'languages.dart';
import 'settings.dart';

const Duration kReconnectDelay = Duration(seconds: 3); // wait before trying again
const Duration kConnectTimeout = Duration(seconds: 5);
// The server sends a ": ping" line every 15 s when quiet. If we hear NOTHING for 30 s,
// the Wi-Fi is probably dead: close and reconnect.
const Duration kSilenceTimeout = Duration(seconds: 30);
const Duration kMockWarningEvery = Duration(seconds: 30);

// What the warnings line on the main screen shows.
enum WarningStatus {
  off, // no server IP set
  mock, // fake warnings every 30 s
  connecting, // trying to connect (or reconnecting after a drop)
  connected, // listening for warnings
  notOnServer, // the server is there but has no /events endpoint
}

// One warning: the sentence to speak, its language, and the server's alert id (0 in mock).
class Warning {
  const Warning(this.text, this.language, [this.id = 0]);
  final String text;
  final AppLanguage language;
  final int id;
}

// Turn the `data:` JSON of one alert event into a Warning, or null if it is not valid.
// `language` is the one we asked the server for (the alert JSON has no language field).
Warning? parseAlert(String data, AppLanguage language) {
  final Object? alert;
  try {
    alert = jsonDecode(data);
  } on FormatException {
    return null; // not JSON: ignore it
  }
  if (alert is! Map) return null;
  final id = alert['id'];
  if (id is! int) return null;

  // Project rule: never say "safe", even if the server sent it.
  final text = removeSafeClaims((alert['text'] ?? '').toString());
  if (text.isEmpty) return null;
  return Warning(text, language, id);
}

// Reads a Server-Sent Events stream line by line and returns each complete event.
// Only the fields we use: "event:" and "data:". Lines starting with ":" are comments (pings).
class SseParser {
  String _event = 'message'; // SSE default event name
  final _data = <String>[];

  // Feed one line (without the newline). Returns (event, data) when an event ends, else null.
  (String, String)? addLine(String line) {
    if (line.isEmpty) {
      // Empty line = end of one event.
      final result = _data.isEmpty ? null : (_event, _data.join('\n'));
      _event = 'message';
      _data.clear();
      return result;
    }
    if (line.startsWith(':')) return null; // comment, e.g. ": ping"
    final colon = line.indexOf(':');
    final field = colon < 0 ? line : line.substring(0, colon);
    var value = colon < 0 ? '' : line.substring(colon + 1);
    if (value.startsWith(' ')) value = value.substring(1); // "data: x" → "x"
    if (field == 'event') _event = value;
    if (field == 'data') _data.add(value);
    return null; // "id" and "retry" are not needed: we keep the id from the JSON
  }
}

// ---------- MOCK mode ----------

const _mockWarnings = {
  'en': ['Warning: stairs ahead.', 'Warning: there is a door in front of you.'],
  'fr': ['Attention : escalier devant vous.', 'Attention : il y a une porte devant vous.'],
  'ar': ['تنبيه: يوجد درج أمامك.', 'تنبيه: يوجد باب أمامك.'],
};

// The n-th fake warning in this language (rotates through the list).
Warning mockWarning(AppLanguage lang, int n) {
  final list = _mockWarnings[lang.code]!;
  return Warning(list[n % list.length], lang);
}

// ---------- The client ----------

class WarningClient {
  WarningClient({required this.onWarning, this.onStatusChanged});

  final void Function(Warning warning) onWarning; // called for every warning
  final void Function(WarningStatus status)? onStatusChanged; // for the status line

  HttpClient? _http;
  Timer? _timer; // the reconnect timer, or the mock timer
  int _mockCount = 0;
  // Id of the last alert we spoke. Sent back on reconnect so nothing is spoken twice.
  // Kept across start()/stop(): the server's ids keep going up, even after a restart.
  int _lastId = 0;
  // Changes on every start()/stop(). An old connection or timer that wakes up later
  // sees a different number and does nothing (so we never have two connections).
  int _session = 0;

  // Start (or restart) with these settings: mock timer, or real connection.
  void start(AppSettings settings) {
    stop();
    final session = _session;
    if (settings.mock) {
      onStatusChanged?.call(WarningStatus.mock);
      _timer = Timer.periodic(kMockWarningEvery, (_) {
        onWarning(mockWarning(settings.language, _mockCount++));
      });
    } else if (settings.serverIp.isNotEmpty) {
      onStatusChanged?.call(WarningStatus.connecting);
      _connect(settings, session);
    }
  }

  // Stop everything: no more warnings, no more reconnecting.
  void stop() {
    _session++;
    _timer?.cancel();
    _timer = null;
    _http?.close(force: true); // also ends the open /events response
    _http = null;
    onStatusChanged?.call(WarningStatus.off);
  }

  Future<void> _connect(AppSettings settings, int session) async {
    final http = HttpClient()..connectionTimeout = kConnectTimeout;
    _http = http;
    try {
      final url = Uri.http('${settings.serverIp}:$kBackendPort', '/events', {
        'after_id': '$_lastId',
        'language': settings.language.code,
      });
      final request = await http.getUrl(url);
      request.headers.set(HttpHeaders.acceptHeader, 'text/event-stream');
      final response = await request.close();
      if (session != _session) return; // stop() was called while we were connecting

      if (response.statusCode == HttpStatus.notFound) {
        // The server answered, but has no /events endpoint (older backend).
        // Keep trying, so warnings start working as soon as the backend has it.
        await response.drain<void>();
        _reconnectLater(settings, session, WarningStatus.notOnServer);
        return;
      }
      if (response.statusCode != HttpStatus.ok) {
        await response.drain<void>();
        _reconnectLater(settings, session);
        return;
      }
      onStatusChanged?.call(WarningStatus.connected);

      // Read the stream line by line until it ends (or goes silent too long).
      final parser = SseParser();
      final lines = response
          .transform(utf8.decoder) // UTF-8: Arabic text arrives correctly
          .transform(const LineSplitter())
          .timeout(kSilenceTimeout);
      await for (final line in lines) {
        if (session != _session) return;
        final event = parser.addLine(line);
        if (event == null || event.$1 != 'alert') continue;
        final warning = parseAlert(event.$2, settings.language);
        if (warning == null || warning.id <= _lastId) continue; // invalid or already spoken
        _lastId = warning.id;
        onWarning(warning);
      }
      _reconnectLater(settings, session); // the server closed the stream
    } catch (_) {
      // Server not reachable, Wi-Fi dropped, or silent for too long.
      _reconnectLater(settings, session);
    } finally {
      http.close(force: true);
    }
  }

  // The connection is gone: try again in a few seconds (forever, until stop()).
  void _reconnectLater(AppSettings settings, int session,
      [WarningStatus status = WarningStatus.connecting]) {
    if (session != _session) return;
    _http = null;
    onStatusChanged?.call(status);
    _timer = Timer(kReconnectDelay, () => _connect(settings, session));
  }
}
