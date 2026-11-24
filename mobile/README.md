# Mobile app (Flutter, Android)

- Streams the phone's back camera (video only, mic stays free for speech_to_text) to
  MediaMTX over WebRTC (WHIP): `POST http://<server-ip>:8889/cam/whip`.
- **Ask** button: listens (speech_to_text), sends `{"question","language"}` to
  `POST http://<server-ip>:8000/ask`, and speaks the answer (flutter_tts).
  English, French and Arabic. A **mock mode** (off by default) gives fake answers without a backend.
- **Hands-free** (no need to look at the screen):
  - **Volume up** = Ask (press again to stop listening / speaking). Only while the app is
    open; volume up does not change the volume then. Volume down works normally.
  - **TalkBack off**: tap anywhere on the main screen = Ask (except Settings and
    Start/Stop). **TalkBack on**: normal accessible buttons only.
  - Streaming **starts by itself** when the app opens if a server IP is set, and says
    "Streaming started" or that it could not start.
  - The first time, it says "Press volume up to ask a question." in the chosen language.
- **One server IP** in Settings is used for everything: MediaMTX on port 8889 (streaming)
  and the backend on port 8000 (`/ask`, `/events`, `/alerts`).
- **Clear errors**, spoken in the user's language: no server IP set, server not reachable
  (check the IP and Wi-Fi), server too slow (15 s), or server problem.
- **Warnings** (no question needed, e.g. "Stairs ahead."): keeps
  `GET http://<server-ip>:8000/events?language=<code>&after_id=<last id>` open
  (Server-Sent Events, Dart's built-in `HttpClient`) and reads each `event: alert` message
  (`{"id", "type", "text", ...}`). Vibrates 3 times and speaks the text; if an answer is being
  spoken, the warning comes right after it.
  - **Never twice:** remembers the last alert id and sends it back on reconnect
    (`after_id` + `Last-Event-ID` header); older or repeated ids are ignored.
  - **Reconnects** after the server's `retry` delay (2 s); 40 s without even a ping = dead line.
  - **Fallback:** after 3 failed `/events` attempts, polls `GET /alerts` every 1 s (and tries
    `/events` again every 60 s).
  - Any sentence saying "safe" is still removed. In mock mode a fake warning comes every 30 s
    in the chosen language.

## Files

| File | What it does |
|---|---|
| `lib/main.dart` | Starts the app, high-contrast theme (black / white / yellow) |
| `lib/stream_screen.dart` | Status text, camera preview, big Start/Stop streaming button, Ask panel |
| `lib/hardware_keys.dart` | Receives the volume-up button from `MainActivity.kt` (MethodChannel) |
| `lib/whip_client.dart` | Opens the back camera and publishes it to MediaMTX via WHIP |
| `lib/ask_panel.dart` | Big Ask button: vibrate → listen → vibrate → ask → speak |
| `lib/voice_service.dart` | speech_to_text (listen) and flutter_tts (speak, one sentence at a time) |
| `lib/warning_client.dart` | Warnings: SSE client for `/events`, `/alerts` polling fallback, no repeats, mock warnings |
| `lib/assistant_client.dart` | `POST /ask` to the backend (15 s timeout), error kinds, mock answers |
| `lib/languages.dart` | English / French / Arabic: locales, the app's own sentences, "safe" filter |
| `lib/settings.dart` | Settings screen: server IP, language, mock mode (saved on the phone) |
| `android/app/src/main/kotlin/.../MainActivity.kt` | Catches volume up and sends it to Dart (`voice_assistant_eyes/keys`) |
| `android/app/src/main/AndroidManifest.xml` | Camera, microphone, internet permissions; plain `http://`; speech + TTS services |
| `test/widget_test.dart` | Settings save/reject tests, mock answers, SSE/alert parsing, "safe" filter, no repeats |
| `test/warning_client_test.dart` | Warning client against a fake local server: reconnect with `Last-Event-ID`, polling fallback |

## Run (once the Android NDK is installed)

1. On the laptop: `mediamtx mediamtx\mediamtx.yml` (repo root).
2. Find the laptop IP: `ipconfig` → "IPv4 Address" of the Wi-Fi adapter.
3. Phone and laptop on the same Wi-Fi; phone connected by USB with USB debugging on.
4. `cd mobile`, `flutter pub get`, `flutter run`.
5. In the app: Settings (gear) → IP, language, mock on/off → Save.
6. **Start streaming**, then check http://localhost:8889/cam or the dashboard.
7. Tap **Ask**, feel the vibration, ask a question, and listen to the answer.
