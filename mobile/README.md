# Mobile app (Flutter, Android)

- Streams the phone's back camera (video only, mic stays free for speech_to_text) to
  MediaMTX over WebRTC (WHIP): `POST http://<server-ip>:8889/cam/whip`.
- **Ask** button: listens (speech_to_text), sends `{"question","language"}` to
  `POST http://<server-ip>:8000/ask`, and speaks the answer (flutter_tts).
  English, French and Arabic. A **mock mode** gives fake answers until the backend exists.

## Files

| File | What it does |
|---|---|
| `lib/main.dart` | Starts the app, high-contrast theme (black / white / yellow) |
| `lib/stream_screen.dart` | Status text, camera preview, big Start/Stop streaming button, Ask panel |
| `lib/whip_client.dart` | Opens the back camera and publishes it to MediaMTX via WHIP |
| `lib/ask_panel.dart` | Big Ask button: vibrate → listen → vibrate → ask → speak |
| `lib/voice_service.dart` | speech_to_text (listen) and flutter_tts (speak) |
| `lib/assistant_client.dart` | `POST /ask` to the backend (15 s timeout) + mock answers |
| `lib/languages.dart` | English / French / Arabic: locales and the app's own spoken sentences |
| `lib/settings.dart` | Settings screen: server IP, language, mock mode (saved on the phone) |
| `android/app/src/main/AndroidManifest.xml` | Camera, microphone, internet permissions; plain `http://`; speech + TTS services |
| `test/widget_test.dart` | Settings save/reject tests, mock answers test |

## Run (once the Android NDK is installed)

1. On the laptop: `mediamtx mediamtx\mediamtx.yml` (repo root).
2. Find the laptop IP: `ipconfig` → "IPv4 Address" of the Wi-Fi adapter.
3. Phone and laptop on the same Wi-Fi; phone connected by USB with USB debugging on.
4. `cd mobile`, `flutter pub get`, `flutter run`.
5. In the app: Settings (gear) → IP, language, mock on/off → Save.
6. **Start streaming**, then check http://localhost:8889/cam or the dashboard.
7. Tap **Ask**, feel the vibration, ask a question, and listen to the answer.
