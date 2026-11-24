// Proactive warnings ("Stairs ahead.") pushed by the backend, without the user asking.
// The backend (server/app/main.py, alerts.py) offers two ways; we use both:
//
//   1. GET http://<ip>:8000/events?language=<code>&after_id=<last id>    (preferred)
//      Server-Sent Events (SSE): ONE request that stays open; the server writes each alert
//      into it as soon as YOLO sees stairs or a door:
//          id: 1795000012
//          event: alert
//          data: {"id": 1795000012, "type": "stairs", "text": "Stairs ahead.", ...}
//          (empty line = end of this message)
//      Lines starting with ":" are keep-alive pings (every 15 s), ignored.
//
//   2. GET http://<ip>:8000/alerts?language=<code>&after_id=<last id>    (fallback)
//      Returns the new alerts as a JSON list. Used every 1 s if /events keeps failing.
//
// Never twice: every alert has an increasing id. We remember the last one we spoke and send
// it back (after_id, and the Last-Event-ID header), so after a reconnect the server only sends
// newer ones; we also skip any id we have already seen.
// The text is already in the user's language (we send it as ?language=). Any sentence saying
// "safe" is still removed. Uses Dart's built-in HttpClient (dart:io): no extra package.
// In MOCK mode there is no connection: a fake warning comes every 30 seconds instead.
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'assistant_client.dart' show kBackendPort;
import 'languages.dart';
import 'settings.dart';

const Duration kConnectTimeout = Duration(seconds: 5);
const Duration kReconnectDelay = Duration(seconds: 3); // until the server sends its own "retry:"
// The server sends a ping at least every 15 s: silence for longer = dead connection (e.g. Wi-Fi).
const Duration kSilenceTimeout = Duration(seconds: 40);
const int kFailuresBeforePolling = 3; // /events failed this many times in a row → poll /alerts
const Duration kPollEvery = Duration(seconds: 1);
const Duration kPollTimeout = Duration(seconds: 3);
const Duration kRetryEventsAfter = Duration(seconds: 60); // while polling, try /events again
const Duration kMockWarningEvery = Duration(seconds: 30);

// What the warnings line on the main screen shows.
enum WarningStatus {
  off, // no server IP set
  mock, // fake warnings every 30 s
  connecting, // trying to connect (or reconnecting after a drop)
  connected, // /events is open: alerts arrive at once
  polling, // fallback: asking /alerts every second
  notOnServer, // the server answers, but has no /events or /alerts (old backend)
}

// One warning: the sentence to speak, its language, and the server's alert id (null in mock mode).
class Warning {
  const Warning(this.text, this.language, [this.id]);
  final String text;
  final AppLanguage language;
  final int? id;
}

// ---------- Reading the SSE stream ----------

// One complete SSE message.
class SseEvent {
  const SseEvent(this.event, this.data, this.id);
  final String event; // e.g. "alert" ("message" if the server gave no name)
  final String data; // the data: lines joined (here: one line of JSON)
  final String? id;
}

// Turns the stream's text lines into messages. Give it one line at a time (without the
// line break); it returns a message when the empty line that ends it arrives.
class SseParser {
  String _event = '';
  final List<String> _data = [];
  String? _id;
  int? retryMs; // reconnect delay the server asked for ("retry: 2000")

  SseEvent? addLine(String line) {
    if (line.isEmpty) {
      // End of a message.
      final message = _data.isEmpty ? null : SseEvent(_event.isEmpty ? 'message' : _event, _data.join('\n'), _id);
      _event = '';
      _data.clear();
      _id = null;
      return message;
    }
    if (line.startsWith(':')) return null; // comment: ": connected", ": ping"
    final colon = line.indexOf(':');
    final field = colon < 0 ? line : line.substring(0, colon);
    var value = colon < 0 ? '' : line.substring(colon + 1);
    if (value.startsWith(' ')) value = value.substring(1); // "data: x" → "x"
    switch (field) {
      case 'event':
        _event = value;
      case 'data':
        _data.add(value);
      case 'id':
        _id = value;
      case 'retry':
        retryMs = int.tryParse(value);
    }
    return null;
  }
}

// One alert (the JSON from /events "data:" or one item of /alerts) → Warning.
// Returns null if it is not a valid alert (no id). The text may come back empty if it only
// said "safe": the caller still remembers the id, but says nothing.
Warning? parseAlert(Object? json, AppLanguage language) {
  if (json is! Map) return null;
  final id = json['id'];
  if (id is! int) return null;
  // Project rule: never say "safe", even if the server sent it.
  final text = removeSafeClaims((json['text'] ?? '').toString());
  return Warning(text, language, id);
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

  final void Function(Warning warning) onWarning; // called once for every NEW warning
  final void Function(WarningStatus status)? onStatusChanged; // for the status line
  final int port; // backend port (8000); tests use a local test server on another port

  // Last alert id we handled. Kept across reconnects AND restarts (e.g. after Settings),
  // so the same alert is never spoken twice. Server ids keep growing, even after a restart.
  int lastId = 0;

  HttpClient? _http;
  StreamSubscription<String>? _stream; // the open /events response
  Timer? _timer; // reconnect timer, poll timer, or mock timer
  int _failures = 0; // /events failures in a row
  DateTime? _pollingSince;
  int _mockCount = 0;
  // Changes on every start()/stop(). An old request or timer that wakes up later sees a
  // different number and does nothing (so we never have two connections at once).
  int _session = 0;

  // Start (or restart) with these settings: mock timer, or the real server.
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
      _http = HttpClient()..connectionTimeout = kConnectTimeout;
      _failures = 0;
      _pollingSince = null;
      _connectEvents(settings, session);
    }
  }

  // Stop everything: no more warnings, no more reconnecting.
  void stop() {
    _session++;
    _timer?.cancel();
    _timer = null;
    _stream?.cancel();
    _stream = null;
    _http?.close(force: true); // also aborts the open /events request
    _http = null;
    onStatusChanged?.call(WarningStatus.off);
  }

  // A warning from the server (SSE or polling): speak it only if we have not seen it yet.
  // Public so the "never twice" rule can be tested.
  void deliver(Warning warning) {
    final id = warning.id;
    if (id != null) {
      if (id <= lastId) return; // already spoken (e.g. sent again after a reconnect)
      lastId = id;
    }
    if (warning.text.isNotEmpty) onWarning(warning);
  }

  Uri _url(AppSettings settings, String path) => Uri(
        scheme: 'http',
        host: settings.serverIp,
        port: port,
        path: path,
        queryParameters: {'language': settings.language.code, 'after_id': '$lastId'},
      );

  // ---------- 1. /events (Server-Sent Events) ----------

  Future<void> _connectEvents(AppSettings settings, int session) async {
    final parser = SseParser();
    try {
      final request = await _http!.getUrl(_url(settings, '/events'));
      request.headers.set(HttpHeaders.acceptHeader, 'text/event-stream');
      request.headers.set(HttpHeaders.cacheControlHeader, 'no-cache');
      if (lastId > 0) request.headers.set('Last-Event-ID', '$lastId'); // standard SSE resume
      final response = await request.close();
      if (session != _session) return;

      if (response.statusCode == HttpStatus.notFound) {
        await response.drain<void>();
        return _eventsFailed(settings, session, WarningStatus.notOnServer);
      }
      if (response.statusCode != HttpStatus.ok) {
        await response.drain<void>();
        return _eventsFailed(settings, session);
      }

      _failures = 0;
      _pollingSince = null;
      onStatusChanged?.call(WarningStatus.connected);
      _stream = response
          .transform(utf8.decoder) // Arabic / French accents
          .transform(const LineSplitter()) // handles \n and \r\n
          .timeout(kSilenceTimeout) // no ping for 40 s → the connection is dead
          .listen(
        (line) {
          final message = parser.addLine(line);
          if (message == null || message.event != 'alert') return;
          try {
            final warning = parseAlert(jsonDecode(message.data), settings.language);
            if (warning != null) deliver(warning);
          } on FormatException {
            // Broken JSON: ignore this one message.
          }
        },
        onDone: () => _reconnectEvents(settings, session, parser), // server closed / restarted
        onError: (_) => _reconnectEvents(settings, session, parser), // Wi-Fi lost / silence
        cancelOnError: true, // after an error, onDone is not called too
      );
    } catch (_) {
      if (session == _session) _eventsFailed(settings, session); // server not reachable
    }
  }

  // The open stream ended after working: reconnect (after the delay the server asked for).
  void _reconnectEvents(AppSettings settings, int session, SseParser parser) {
    if (session != _session) return;
    _stream = null;
    onStatusChanged?.call(WarningStatus.connecting);
    final delay = parser.retryMs != null ? Duration(milliseconds: parser.retryMs!) : kReconnectDelay;
    _timer = Timer(delay, () => _connectEvents(settings, session));
  }

  // /events could not be opened: try again, or after a few failures switch to polling.
  void _eventsFailed(AppSettings settings, int session, [WarningStatus status = WarningStatus.connecting]) {
    if (session != _session) return;
    _failures++;
    if (_failures >= kFailuresBeforePolling) {
      _pollingSince ??= DateTime.now();
      _poll(settings, session);
    } else {
      onStatusChanged?.call(status);
      _timer = Timer(kReconnectDelay, () => _connectEvents(settings, session));
    }
  }

  // ---------- 2. /alerts (polling fallback) ----------

  Future<void> _poll(AppSettings settings, int session) async {
    if (session != _session) return;
    // Every 60 s, give /events another chance (it is faster and lighter).
    if (_pollingSince != null && DateTime.now().difference(_pollingSince!) >= kRetryEventsAfter) {
      _pollingSince = DateTime.now();
      return _connectEvents(settings, session); // if it fails again, we come straight back here
    }
    WarningStatus status;
    try {
      final request = await _http!.getUrl(_url(settings, '/alerts')).timeout(kPollTimeout);
      final response = await request.close().timeout(kPollTimeout);
      final body = await response.transform(utf8.decoder).join().timeout(kPollTimeout);
      if (session != _session) return;
      if (response.statusCode == HttpStatus.ok) {
        final list = jsonDecode(body);
        for (final item in list is List ? list : const []) {
          final warning = parseAlert(item, settings.language);
          if (warning != null) deliver(warning);
        }
        status = WarningStatus.polling;
      } else {
        status = response.statusCode == HttpStatus.notFound
            ? WarningStatus.notOnServer
            : WarningStatus.connecting;
      }
    } catch (_) {
      if (session != _session) return;
      status = WarningStatus.connecting; // server not reachable / timeout / bad JSON
    }
    onStatusChanged?.call(status);
    // Next poll 1 s after this one finished (never two polls at the same time).
    _timer = Timer(kPollEvery, () => _poll(settings, session));
  }
}
