// WHIP client: sends the phone's BACK camera (video only) to MediaMTX.
// No audio: the microphone is kept free for speech_to_text (Android can't share it).
// Same idea as dashboard/src/whep.js, but SENDING instead of receiving:
//   1) open the camera
//   2) create a WebRTC connection and add the camera track
//   3) make an SDP "offer" and POST it to http://<server-ip>:8889/cam/whip
//   4) MediaMTX replies with an SDP "answer" → video starts flowing to the server
import 'dart:async';

import 'package:flutter_webrtc/flutter_webrtc.dart';
import 'package:http/http.dart' as http;

class WhipClient {
  RTCPeerConnection? _pc;
  MediaStream? _stream;
  Uri? _resourceUrl; // URL MediaMTX gives us for this session (used to stop it)

  // Called when the WebRTC connection changes (connecting, connected, failed...).
  void Function(RTCPeerConnectionState state)? onConnectionState;

  // Starts streaming. Returns the camera stream so the screen can show a preview.
  Future<MediaStream> start(String serverIp) async {
    try {
      // 1) Back camera ("environment"), NO microphone. Android asks for permission here.
      _stream = await navigator.mediaDevices.getUserMedia({
        'audio': false,
        'video': {
          'facingMode': 'environment',
          'width': 1280,
          'height': 720,
          'frameRate': 15,
        },
      });

      // 2) WebRTC connection with our video track.
      _pc = await createPeerConnection({'sdpSemantics': 'unified-plan'});
      _pc!.onConnectionState = (state) => onConnectionState?.call(state);
      for (final track in _stream!.getTracks()) {
        await _pc!.addTrack(track, _stream!);
      }

      // 3) Offer, and wait until our network addresses (ICE candidates) are in it.
      final iceDone = _waitForIce(_pc!);
      await _pc!.setLocalDescription(await _pc!.createOffer());
      await iceDone;
      final offer = await _pc!.getLocalDescription();

      // POST the offer to MediaMTX.
      final whipUrl = Uri.parse('http://$serverIp:8889/cam/whip');
      final response = await http
          .post(whipUrl, headers: {'Content-Type': 'application/sdp'}, body: offer!.sdp)
          .timeout(const Duration(seconds: 10));
      if (response.statusCode != 201 && response.statusCode != 200) {
        throw Exception('Server answered ${response.statusCode}');
      }

      // Remember the session URL so stop() can tell MediaMTX we are leaving.
      final location = response.headers['location'];
      if (location != null) _resourceUrl = whipUrl.resolve(location);

      // 4) Apply MediaMTX's answer → the connection starts.
      await _pc!.setRemoteDescription(RTCSessionDescription(response.body, 'answer'));
      return _stream!;
    } on TimeoutException {
      await stop();
      throw Exception('Server $serverIp did not answer');
    } catch (e) {
      await stop(); // release the camera if anything failed
      rethrow;
    }
  }

  // Stops streaming and releases the camera.
  Future<void> stop() async {
    final url = _resourceUrl;
    _resourceUrl = null;
    if (url != null) {
      try {
        await http.delete(url).timeout(const Duration(seconds: 3));
      } catch (_) {
        // Not important: MediaMTX also notices when the connection closes.
      }
    }
    for (final track in _stream?.getTracks() ?? <MediaStreamTrack>[]) {
      await track.stop();
    }
    await _stream?.dispose();
    _stream = null;
    await _pc?.close();
    _pc = null;
  }

  // Wait for ICE gathering to finish (or give up after 2 seconds).
  Future<void> _waitForIce(RTCPeerConnection pc) {
    final done = Completer<void>();
    pc.onIceGatheringState = (state) {
      if (state == RTCIceGatheringState.RTCIceGatheringStateComplete && !done.isCompleted) {
        done.complete();
      }
    };
    return done.future.timeout(const Duration(seconds: 2), onTimeout: () {});
  }
}
