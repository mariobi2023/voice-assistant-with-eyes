// Proactive warnings ("Stairs ahead") pushed by the backend, without the user asking.
//   connect:  ws://<server-ip>:8000/ws   (same IP as in Settings)
//   message:  {"type": "warning", "data": {"text": "...", "language": "en" | "fr" | "ar"}}
// Uses Dart's built-in WebSocket (dart:io): no extra package.
// In MOCK mode there is no connection: a fake warning comes every 30 seconds instead.
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'assistant_client.dart' show kBackendPort;
import 'languages.dart';
import 'settings.dart';

const Duration kReconnectDelay = Duration(seconds: 3); // wait before trying again
const Duration kConnectTimeout = Duration(seconds: 5);
const Duration kPingInterval = Duration(seconds: 10); // notices a dead Wi-Fi connection
const Duration kMockWarningEvery = Duration(seconds: 30);

// What the warnings line on the main screen shows.
enum WarningStatus {
  off, // no server IP set
  mock, // fake warnings every 30 s
  connecting, // trying to connect (or reconnecting after a drop)
  connected, // listening for warnings
  notOnServer, // the server is there but has no /ws endpoint (yet)
}

// One warning: the sentence to speak and its language.
class Warning {
  const Warning(this.text, this.language);
  final String text;
  final AppLanguage language;
}

// Turn one WebSocket message into a Warning, or null if it is not a (valid) warning.
// `fallback` is used when the message has no known language code.
Warning? parseWarning(String raw, AppLanguage fallback) {
  final Object? message;
  try {
    message = jsonDecode(raw);
  } on FormatException {
    return null; // not JSON: ignore it
  }
  if (message is! Map || message['type'] != 'warning') return null;
  final data = message['data'];
  if (data is! Map) return null;

  // Project rule: never say "safe", even if the server sent it.
  final text = removeSafeClaims((data['text'] ?? '').toString());
  if (text.isEmpty) return null;

  final code = data['language'];
  final language = allLanguages.where((l) => l.code == code).firstOrNull ?? fallback;
  return Warning(text, language);
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

  WebSocket? _socket;
  Timer? _timer; // the reconnect timer, or the mock timer
  int _mockCount = 0;
  // Changes on every start()/stop(). An old connection or timer that wakes up later
  // sees a different number and does nothing (so we never have two connections).
  int _session = 0;

  // Start (or restart) with these settings: mock timer, or real WebSocket.
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
    _socket?.close();
    _socket = null;
    onStatusChanged?.call(WarningStatus.off);
  }

  Future<void> _connect(AppSettings settings, int session) async {
    try {
      final client = HttpClient()..connectionTimeout = kConnectTimeout;
      final socket = await WebSocket.connect(
        'ws://${settings.serverIp}:$kBackendPort/ws',
        customClient: client,
      );
      if (session != _session) {
        socket.close(); // stop() was called while we were connecting
        return;
      }
      socket.pingInterval = kPingInterval;
      _socket = socket;
      onStatusChanged?.call(WarningStatus.connected);

      socket.listen(
        (message) {
          if (message is! String) return;
          final warning = parseWarning(message, settings.language);
          if (warning != null) onWarning(warning);
        },
        onDone: () => _reconnectLater(settings, session), // server closed / Wi-Fi dropped
        onError: (_) => _reconnectLater(settings, session),
        cancelOnError: true, // after an error, onDone is not called too
      );
    } on WebSocketException {
      // The server answered, but refused the WebSocket: it has no /ws endpoint yet.
      // Keep trying, so warnings start working as soon as the backend adds it.
      _reconnectLater(settings, session, WarningStatus.notOnServer);
    } catch (_) {
      _reconnectLater(settings, session); // server not reachable (yet)
    }
  }

  // The connection is gone: try again in a few seconds (forever, until stop()).
  void _reconnectLater(AppSettings settings, int session,
      [WarningStatus status = WarningStatus.connecting]) {
    if (session != _session) return;
    _socket = null;
    onStatusChanged?.call(status);
    _timer = Timer(kReconnectDelay, () => _connect(settings, session));
  }
}
