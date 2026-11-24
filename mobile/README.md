# Mobile app (Flutter, Android)

- Streams the phone's back camera (video only, mic stays free for speech_to_text) to
  MediaMTX over WebRTC (WHIP): `POST http://<server-ip>:8889/cam/whip`.
- **Ask** button: listens (speech_to_text), sends `{"question","language"}` to
  `POST http://<server-ip>:8000/ask`, and speaks the answer (flutter_tts).
  English, French and Arabic. A **mock mode** (off by default) gives fake answers without a backend.
- **One server IP** in Settings is used for everything: MediaMTX on port 8889 (streaming)
  and the backend on port 8000 (`/ask`, `/ws`).
- **Clear errors**, spoken in the user's language: no server IP set, server not reachable
  (check the IP and Wi-Fi), server too slow (15 s), or server problem.
- **Warnings** (no question needed): listens on `ws://<server-ip>:8000/ws` for
  `{"type":"warning","data":{"text":"...","language":"en"}}`, vibrates 3 times and speaks the
  text. If an answer is being spoken, the warning is spoken right after it. Reconnects every
  3 s if the connection drops. Any sentence saying "safe" is removed. In mock mode a fake
  warning comes every 30 s in the chosen language.

## Files

| File | What it does |
|---|---|
| `lib/main.dart` | Starts the app, high-contrast theme (black / white / yellow) |
| `lib/stream_screen.dart` | Status text, camera preview, big Start/Stop streaming button, Ask panel |
| `lib/whip_client.dart` | Opens the back camera and publishes it to MediaMTX via WHIP |
| `lib/ask_panel.dart` | Big Ask button: vibrate → listen → vibrate → ask → speak |
| `lib/voice_service.dart` | speech_to_text (listen) and flutter_tts (speak, one sentence at a time) |
| `lib/warning_client.dart` | WebSocket `/ws` for warnings, auto-reconnect, mock warnings |
| `lib/assistant_client.dart` | `POST /ask` to the backend (15 s timeout), error kinds, mock answers |
| `lib/languages.dart` | English / French / Arabic: locales, the app's own sentences, "safe" filter |
| `lib/settings.dart` | Settings screen: server IP, language, mock mode (saved on the phone) |
| `android/app/src/main/AndroidManifest.xml` | Camera, microphone, internet permissions; plain `http://`; speech + TTS services |
| `test/widget_test.dart` | Settings save/reject tests, mock answers, warning parsing and "safe" filter |

## Run (once the Android NDK is installed)

1. On the laptop: `mediamtx mediamtx\mediamtx.yml` (repo root).
2. Find the laptop IP: `ipconfig` → "IPv4 Address" of the Wi-Fi adapter.
3. Phone and laptop on the same Wi-Fi; phone connected by USB with USB debugging on.
4. `cd mobile`, `flutter pub get`, `flutter run`.
5. In the app: Settings (gear) → IP, language, mock on/off → Save.
6. **Start streaming**, then check http://localhost:8889/cam or the dashboard.
7. Tap **Ask**, feel the vibration, ask a question, and listen to the answer.
