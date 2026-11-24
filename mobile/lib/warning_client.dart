// Proactive warnings ("Stairs ahead.") pushed by the backend, without the user asking.
//   connect:  GET http://<server-ip>:8000/events?after_id=<last id>&language=en|fr|ar
//             (Server-Sent Events: ONE open HTTP connection, the server writes each alert)
//   message:  id: 1795000012
//             event: alert
//             data: {"id": 1795000012, "type": "stairs", "text": "Stairs ahead.", ...}
//             (empty line = end of message)
//   fallback: GET http://<server-ip>:8000/alerts?after_id=<last id>&language=...
//             (a JSON list of the new alerts; asked every second if /events keeps failing)
// Never twice: we remember the id of the last alert we spoke and send it back (after_id and
// the standard SSE Last-Event-ID header), and we skip any id that is not newer.
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
const int kFailuresBeforePolling = 3; // /events failed this many times in a row: poll /alerts
const Duration kPollEvery = Duration(seconds: 1);
const Duration kPollTimeout = Duration(seconds: 3);
const Duration kRetryEventsAfter = Duration(seconds: 60); // while polling, try /events again
const Duration kMockWarningEvery = Duration(seconds: 30);

// What the warnings line on the main screen shows.
enum WarningStatus {
  off, // no server IP set
  mock, // fake warnings every 30 s
  connecting, // trying to connect (or reconnecting after a drop)
  connected, // /events is open: warnings arrive at once
  polling, // fallback: asking /alerts every second
  notOnServer, // the server is there but has no /events or /alerts endpoint
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
  try {
    return alertFromJson(jsonDecode(data), language);
  } on FormatException {
    return null; // not JSON: ignore it
  }
}

// One already-decoded alert (an SSE `data:` object, or one item of the /alerts list).
Warning? alertFromJson(Object? alert, AppLanguage language) {
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
  WarningClient({required this.onWarning, this.onStatusChanged, this.port = kBackendPort});

  final void Function(Warning warning) onWarning; // called for every warning
  final void Function(WarningStatus status)? onStatusChanged; // for the status line
  final int port; // the backend's port (tests point it at a small fake server)

  HttpClient? _http;
  Timer? _timer; // the reconnect timer, or the mock timer
  int _mockCount = 0;
  // Id of the last alert we spoke. Sent back on reconnect so nothing is spoken twice.
  // Kept across start()/stop(): the server's ids keep going up, even after a restart.
  int _lastId = 0;
  int _failures = 0; // /events failed this many times in a row
  DateTime? _pollingSince; // when we switched to polling /alerts (null = not polling)
  // Changes on every start()/stop(). An old connection or timer that wakes up later
  // sees a different number and does nothing (so we never have two connections).
  int _session = 0;

  // Id of the last alert we spoke (0 = none yet).
  int get lastId => _lastId;

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
    _failures = 0;
    _pollingSince = null;
    onStatusChanged?.call(WarningStatus.off);
  }

  // http://<server-ip>:<port><path>?after_id=<last id>&language=<code>
  Uri _url(AppSettings settings, String path) => Uri(
        scheme: 'http',
        host: settings.serverIp,
        port: port,
        path: path,
        queryParameters: {'after_id': '$_lastId', 'language': settings.language.code},
      );

  // Speak a warning only if it is valid and newer than the last one we spoke.
  void _deliver(Warning? warning) {
    if (warning == null || warning.id <= _lastId) return; // invalid or already spoken
    _lastId = warning.id;
    onWarning(warning);
  }

  // ---------- 1. /events (Server-Sent Events) ----------

  Future<void> _connect(AppSettings settings, int session) async {
    final http = HttpClient()..connectionTimeout = kConnectTimeout;
    _http = http;
    try {
      final request = await http.getUrl(_url(settings, '/events'));
      request.headers.set(HttpHeaders.acceptHeader, 'text/event-stream');
      if (_lastId > 0) request.headers.set('Last-Event-ID', '$_lastId'); // standard SSE resume
      final response = await request.close();
      if (session != _session) return; // stop() was called while we were connecting

      if (response.statusCode == HttpStatus.notFound) {
        // The server answered, but has no /events endpoint (older backend).
        await response.drain<void>();
        _failed(settings, session, WarningStatus.notOnServer);
        return;
      }
      if (response.statusCode != HttpStatus.ok) {
        await response.drain<void>();
        _failed(settings, session);
        return;
      }
      _failures = 0; // it works: no need to poll
      _pollingSince = null;
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
        _deliver(parseAlert(event.$2, settings.language));
      }
      _reconnectLater(settings, session); // the server closed the stream
    } catch (_) {
      // Server not reachable, Wi-Fi dropped, or silent for too long.
      _failed(settings, session);
    } finally {
      http.close(force: true);
    }
  }

  // /events did not work: try again, or after a few failures in a row poll /alerts.
  void _failed(AppSettings settings, int session,
      [WarningStatus status = WarningStatus.connecting]) {
    if (session != _session) return;
    _failures++;
    if (_failures >= kFailuresBeforePolling) {
      _pollingSince ??= DateTime.now();
      _poll(settings, session);
    } else {
      _reconnectLater(settings, session, status);
    }
  }

  // ---------- 2. /alerts (polling fallback) ----------

  Future<void> _poll(AppSettings settings, int session) async {
    if (session != _session) return;
    // Every 60 s, give /events another chance (it is faster and lighter).
    if (DateTime.now().difference(_pollingSince!) >= kRetryEventsAfter) {
      _pollingSince = DateTime.now();
      _failures = kFailuresBeforePolling - 1; // if it fails once more, poll again at once
      return _connect(settings, session);
    }
    final http = HttpClient()..connectionTimeout = kConnectTimeout;
    _http = http;
    var status = WarningStatus.connecting; // unless the server answers
    try {
      final request = await http.getUrl(_url(settings, '/alerts'));
      final response = await request.close().timeout(kPollTimeout);
      final body = await response.transform(utf8.decoder).join().timeout(kPollTimeout);
      if (session != _session) return;
      if (response.statusCode == HttpStatus.ok) {
        final list = jsonDecode(body);
        for (final item in list is List ? list : const []) {
          _deliver(alertFromJson(item, settings.language));
        }
        status = WarningStatus.polling;
      } else if (response.statusCode == HttpStatus.notFound) {
        status = WarningStatus.notOnServer;
      }
    } catch (_) {
      // Not reachable, too slow, or bad JSON: the status stays "connecting".
    } finally {
      http.close(force: true);
    }
    if (session != _session) return;
    onStatusChanged?.call(status);
    // Next poll 1 s after this one finished (never two polls at the same time).
    _timer = Timer(kPollEvery, () => _poll(settings, session));
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
