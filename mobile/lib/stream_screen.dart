// Main screen: status text, camera preview and one big Start / Stop button.
import 'package:flutter_webrtc/flutter_webrtc.dart';
import 'package:material_ui/material_ui.dart';

import 'main.dart' show kAccent, kOk, kWarn;
import 'settings.dart';
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
  StreamStatus _status = StreamStatus.idle;
  String _errorText = '';
  String _serverIp = '';

  @override
  void initState() {
    super.initState();
    _preview.initialize();
    _loadServerIp();

    // Update the status when the WebRTC connection really connects or drops.
    _whip.onConnectionState = (state) {
      if (!mounted) return;
      if (state == RTCPeerConnectionState.RTCPeerConnectionStateConnected) {
        setState(() => _status = StreamStatus.live);
      } else if (state == RTCPeerConnectionState.RTCPeerConnectionStateFailed ||
          state == RTCPeerConnectionState.RTCPeerConnectionStateDisconnected) {
        _showError('Connection lost');
        _whip.stop();
        _preview.srcObject = null;
      }
    };
  }

  @override
  void dispose() {
    _whip.stop();
    _preview.dispose();
    super.dispose();
  }

  Future<void> _loadServerIp() async {
    final ip = await SettingsStore.loadServerIp();
    setState(() => _serverIp = ip);
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
      return;
    }
    setState(() => _status = StreamStatus.connecting);
    try {
      final stream = await _whip.start(_serverIp);
      _preview.srcObject = stream;
      // Status becomes "Live" in onConnectionState when WebRTC is connected.
    } catch (e) {
      _showError(e.toString().replaceFirst('Exception: ', ''));
    }
  }

  Future<void> _stop() async {
    await _whip.stop();
    _preview.srcObject = null;
    setState(() => _status = StreamStatus.idle);
  }

  Future<void> _openSettings() async {
    await Navigator.push(context, MaterialPageRoute(builder: (_) => const SettingsScreen()));
    _loadServerIp(); // the IP may have changed
  }

  // Text and colour for each status.
  String get _statusText => switch (_status) {
        StreamStatus.idle => 'Not streaming',
        StreamStatus.connecting => 'Connecting…',
        StreamStatus.live => 'Live',
        StreamStatus.error => 'Error: $_errorText',
      };

  Color get _statusColor => switch (_status) {
        StreamStatus.live => kOk,
        StreamStatus.error => kWarn,
        _ => Colors.white,
      };

  @override
  Widget build(BuildContext context) {
    final streaming = _status == StreamStatus.connecting || _status == StreamStatus.live;

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
      body: Padding(
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
              _serverIp.isEmpty ? 'No server IP set' : 'Server: $_serverIp',
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 20, color: Colors.white70),
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
              height: 140,
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
          ],
        ),
      ),
    );
  }
}
