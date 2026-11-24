// Hands-free Ask: receives the phone's VOLUME UP button from the Android side
// (android/.../MainActivity.kt), which sends "volumeUp" on this channel.
// Uses Flutter's built-in MethodChannel: no extra package.
import 'package:flutter/services.dart';

class HardwareKeys {
  static const _channel = MethodChannel('voice_assistant_eyes/keys');

  // Call `onVolumeUp` every time volume up is pressed (only one listener at a time).
  static void listen(void Function() onVolumeUp) {
    _channel.setMethodCallHandler((call) async {
      if (call.method == 'volumeUp') onVolumeUp();
    });
  }

  // Stop listening (the screen is closed).
  static void stop() => _channel.setMethodCallHandler(null);
}
