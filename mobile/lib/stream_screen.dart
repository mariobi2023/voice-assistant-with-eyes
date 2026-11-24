// Main screen: status text, camera preview, the big Start / Stop button,
// the big Ask button (AskPanel) and the proactive warnings (WarningClient).
//
// Usable without looking at the screen:
//   - VOLUME UP = Ask (hardware_keys.dart + MainActivity.kt), while the app is open.
//   - TalkBack OFF: a tap ANYWHERE on the screen = Ask (except Settings and Start/Stop).
//     TalkBack ON: normal accessible buttons only, so TalkBack gestures keep working.
//   - Streaming starts by itself when the app opens (if a server IP is set), and the
//     result is spoken: "Streaming started" or why it failed.
//   - The first time, the app says "Press volume up to ask a question.".
import 'dart:async';

import 'package:flutter/services.dart' show HapticFeedback;
import 'package:flutter_webrtc/flutter_webrtc.dart';
import 'package:material_ui/material_ui.dart';

import 'ask_panel.dart';
import 'hardware_keys.dart';
import 'languages.dart';
import 'main.dart' show kAccent, kOk, kWarn;
import 'settings.dart';
import 'voice_service.dart';
import 'warning_client.dart';
import 'whip_client.dart';

// The four states the screen can be in.
enum StreamStatus { idle, connecting, live, error }

class StreamScreen extends StatefulWidget {
  const StreamScreen({super.key});

  @override
  State<StreamScreen> createState() => _StreamScreenState();
}

class _StreamScreenState extends State<StreamScreen> {
  final _whip = WhipClient();
  final _preview = RTCVideoRenderer(); // shows what the camera sends
  // One voice for the whole app: answers and warnings share its speech queue.
  final _voice = VoiceService();
  late final _warnings = WarningClient(
    onWarning: _onWarning,
    onStatusChanged: (status) {
      if (mounted) setState(() => _warningStatus = status);
    },
  );
  final _askKey = GlobalKey<AskPanelState>(); // to start a question from volume up / a tap
  StreamStatus _status = StreamStatus.idle;
  String _errorText = '';
  String _serverIp = '';
  AppLanguage _language = english; // for the sentences the app speaks
  bool _announceStart = false; // speak "Streaming started" / failed once per start
  WarningStatus _warningStatus = WarningStatus.off;
  String _lastWarning = '';

  @override
  void initState() {
    super.initState();
    _preview.initialize();
    HardwareKeys.listen(_askHandsFree); // volume up = Ask
    _startUp();

    // Update the status when the WebRTC connection really connects or drops.
    _whip.onConnectionState = (state) {
      if (!mounted) return;
      if (state == RTCPeerConnectionState.RTCPeerConnectionStateConnected) {
        setState(() => _status = StreamStatus.live);
        if (_announceStart) _say(_language.streamingStarted);
        _announceStart = false;
      } else if (state == RTCPeerConnectionState.RTCPeerConnectionStateFailed ||
          state == RTCPeerConnectionState.RTCPeerConnectionStateDisconnected) {
        // Was it already live (lost later) or still starting (could not start)?
        _say(_status == StreamStatus.live ? _language.streamingLost : _language.streamingFailed);
        _announceStart = false;
        _showError('Connection lost');
        _whip.stop();
        _preview.srcObject = null;
      }
    };
  }

  // When the app opens: settings -> first-time hint -> start streaming by itself.
  Future<void> _startUp() async {
    final settings = await _loadSettings();
    if (settings == null) return; // screen already closed
    if (await SettingsStore.isFirstHint()) _say(_language.volumeHint);
    if (settings.serverIp.isNotEmpty) {
      _start();
    } else if (!settings.mock) {
      _say(_language.noServerIp); // nothing will work without it: tell the user at once
    }
  }

  // Volume up (or a tap anywhere): same as pressing the Ask button.
  // Ignored while another page (Settings) is open on top of this one.
  void _askHandsFree() {
    if (!mounted || !(ModalRoute.of(context)?.isCurrent ?? true)) return;
    _askKey.currentState?.ask();
  }

  // Speak a short status sentence (goes through the same queue as answers and warnings).
  void _say(String text) => unawaited(_voice.speak(text, _language));

  @override
  void dispose() {
    HardwareKeys.stop();
    _warnings.stop();
    _voice.stopListening();
    _voice.stopSpeaking();
    _whip.stop();
    _preview.dispose();
    super.dispose();
  }

  // Read the settings and (re)start the warnings with them (server /events or /alerts, or mock timer).
  // Returns the settings, or null if the screen was closed meanwhile.
  Future<AppSettings?> _loadSettings() async {
    final settings = await SettingsStore.load();
    if (!mounted) return null;
    setState(() {
      _serverIp = settings.serverIp;
      _language = settings.language;
    });
    _warnings.start(settings);
    return settings;
  }

  // A warning arrived: vibrate strongly, show it, and speak it.
  // speak() puts it in the queue: if an answer is being spoken, the warning comes right after.
  void _onWarning(Warning warning) {
    _vibrateStrongly();
    setState(() => _lastWarning = warning.text);
    unawaited(_voice.speak(warning.text, warning.language));
  }

  // Three vibrations in a row: different from the single buzz of the Ask button,
  // so the user feels at once that this is a warning.
  Future<void> _vibrateStrongly() async {
    for (var i = 0; i < 3; i++) {
      await HapticFeedback.vibrate();
      await Future.delayed(const Duration(milliseconds: 300));
    }
  }

  void _showError(String message) {
    setState(() {
      _status = StreamStatus.error;
      _errorText = message;
    });
  }

  Future<void> _start() async {
    if (_serverIp.isEmpty) {
      _showError('Set the server IP in Settings');
      _say(_language.noServerIp);
      return;
    }
    setState(() => _status = StreamStatus.connecting);
    _announceStart = true; // "Streaming started" is spoken when WebRTC is really connected
    try {
      final stream = await _whip.start(_serverIp);
      _preview.srcObject = stream;
      // Status becomes "Live" in onConnectionState when WebRTC is connected.
    } catch (e) {
      _announceStart = false;
      _showError(e.toString().replaceFirst('Exception: ', ''));
      _say(_language.streamingFailed);
    }
  }

  Future<void> _stop() async {
    _announceStart = false;
    await _whip.stop();
    _preview.srcObject = null;
    setState(() => _status = StreamStatus.idle);
  }

  Future<void> _openSettings() async {
    await Navigator.push(context, MaterialPageRoute(builder: (_) => const SettingsScreen()));
    _loadSettings(); // IP, language or mock mode may have changed: restart the warnings
  }

  // Text and colour for each status.
  String get _statusText => switch (_status) {
        StreamStatus.idle => 'Not streaming',
        StreamStatus.connecting => 'Connecting…',
        StreamStatus.live => 'Live',
        StreamStatus.error => 'Error: $_errorText',
      };

  String get _warningsText => switch (_warningStatus) {
        WarningStatus.off => 'Warnings: off (no server IP)',
        WarningStatus.mock => 'Warnings: mock (every 30 s)',
        WarningStatus.connecting => 'Warnings: server not reachable, retrying…',
        WarningStatus.connected => 'Warnings: connected',
        WarningStatus.polling => 'Warnings: connected (checking every second)',
        WarningStatus.notOnServer => 'Warnings: not available on this server yet',
      };

  Color get _statusColor => switch (_status) {
        StreamStatus.live => kOk,
        StreamStatus.error => kWarn,
        _ => Colors.white,
      };

  @override
  Widget build(BuildContext context) {
    final streaming = _status == StreamStatus.connecting || _status == StreamStatus.live;
    // true when TalkBack (or another screen reader) is on.
    final talkBackOn = MediaQuery.of(context).accessibleNavigation;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Voice Assistant'),
        actions: [
          IconButton(
            icon: const Icon(Icons.settings, size: 36),
            tooltip: 'Settings', // read aloud by TalkBack
            onPressed: streaming ? null : _openSettings,
          ),
        ],
      ),
      // TalkBack OFF: a tap anywhere on the body = Ask. The Start/Stop and Ask buttons are
      // deeper in the tree, so they win their own taps. The Settings icon is in the app bar,
      // outside this area. TalkBack ON: no tap-anywhere (TalkBack uses taps to read things).
      body: GestureDetector(
        behavior: HitTestBehavior.opaque, // empty space reacts too
        excludeFromSemantics: true, // invisible to TalkBack
        onTap: talkBackOn ? null : _askHandsFree,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // liveRegion: TalkBack announces the status every time it changes.
              Semantics(
                liveRegion: true,
                child: Text(
                  _statusText,
                  textAlign: TextAlign.center,
                  style: TextStyle(fontSize: 34, fontWeight: FontWeight.bold, color: _statusColor),
                ),
              ),
              const SizedBox(height: 8),
              Text(
                talkBackOn ? 'Volume up = Ask' : 'Volume up or tap anywhere = Ask',
                textAlign: TextAlign.center,
                style: const TextStyle(fontSize: 20, color: kAccent),
              ),
              Text(
                _serverIp.isEmpty ? 'No server IP set' : 'Server: $_serverIp',
                textAlign: TextAlign.center,
                style: const TextStyle(fontSize: 20, color: Colors.white70),
              ),
              Text(
                _warningsText,
                textAlign: TextAlign.center,
                style: const TextStyle(fontSize: 20, color: Colors.white70),
              ),
              // Last warning on screen for a sighted helper. Not a liveRegion:
              // TalkBack would read it too, on top of our own voice.
              if (_lastWarning.isNotEmpty)
                Text(
                  _lastWarning,
                  textAlign: TextAlign.center,
                  style: const TextStyle(fontSize: 22, fontWeight: FontWeight.bold, color: kWarn),
                ),
              const SizedBox(height: 16),

              // Camera preview (useful for a sighted helper during the demo).
              Expanded(
                child: ExcludeSemantics(
                  child: Container(
                    decoration: BoxDecoration(border: Border.all(color: Colors.white, width: 2)),
                    child: RTCVideoView(_preview, objectFit: RTCVideoViewObjectFit.RTCVideoViewObjectFitCover),
                  ),
                ),
              ),
              const SizedBox(height: 16),

              // One big button: Start when idle, Stop when streaming.
              SizedBox(
                height: 110,
                child: ElevatedButton(
                  style: ElevatedButton.styleFrom(
                    backgroundColor: streaming ? kWarn : kAccent,
                    foregroundColor: Colors.black,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                  ),
                  // Disabled while connecting, so the user can't press twice.
                  onPressed: _status == StreamStatus.connecting ? null : (streaming ? _stop : _start),
                  child: Text(
                    streaming ? 'Stop streaming' : 'Start streaming',
                    style: const TextStyle(fontSize: 34, fontWeight: FontWeight.bold),
                  ),
                ),
              ),
              const SizedBox(height: 16),

              // Voice: big Ask button + last question/answer.
              AskPanel(key: _askKey, voice: _voice),
            ],
          ),
        ),
      ),
    );
  }
}
