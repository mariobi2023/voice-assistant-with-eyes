package com.voiceassistanteyes.voice_assistant_eyes

import android.view.KeyEvent
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

// Hands-free Ask: the phone's VOLUME UP button = the Ask button (lib/hardware_keys.dart).
// Android only sends key events to the app on screen, so this works only while the app
// is in the foreground. Volume DOWN is not touched: it keeps changing the volume.
class MainActivity : FlutterActivity() {
    private var keys: MethodChannel? = null

    // Open the channel the Dart side listens on.
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        keys = MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "voice_assistant_eyes/keys")
    }

    // Every key press passes here first, before Flutter and before Android changes the volume.
    override fun dispatchKeyEvent(event: KeyEvent): Boolean {
        if (event.keyCode == KeyEvent.KEYCODE_VOLUME_UP) {
            // Only the first "down" of a press: holding the button does not ask again and again.
            if (event.action == KeyEvent.ACTION_DOWN && event.repeatCount == 0) {
                keys?.invokeMethod("volumeUp", null)
            }
            return true // handled: volume up does NOT raise the volume while the app is open
        }
        return super.dispatchKeyEvent(event) // everything else (volume down...) as normal
    }
}
