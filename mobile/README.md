# Mobile app (Flutter, Android)

Streams the phone's back camera (video only, mic stays free for speech_to_text) to MediaMTX over WebRTC (WHIP):
`POST http://<server-ip>:8889/cam/whip`.

## Files

| File | What it does |
|---|---|
| `lib/main.dart` | Starts the app, high-contrast theme (black / white / yellow) |
| `lib/stream_screen.dart` | Status text (Not streaming / Connecting / Live / Error), camera preview, big Start/Stop button |
| `lib/whip_client.dart` | Opens the back camera and publishes it to MediaMTX via WHIP |
| `lib/settings.dart` | Settings screen; saves the server IP on the phone (`shared_preferences`) |
| `android/app/src/main/AndroidManifest.xml` | Camera, microphone (for speech_to_text), internet permissions; allows plain `http://` |
| `test/widget_test.dart` | Tests that the settings screen saves / rejects an IP |

## Run (once the Android NDK is installed)

1. On the laptop: `mediamtx mediamtx\mediamtx.yml` (repo root).
2. Find the laptop IP: `ipconfig` → "IPv4 Address" of the Wi-Fi adapter.
3. Phone and laptop on the same Wi-Fi; phone connected by USB with USB debugging on.
4. `cd mobile`, `flutter pub get`, `flutter run`.
5. In the app: Settings (gear) → type the IP → Save → **Start streaming**.
6. Check the stream on the laptop: http://localhost:8889/cam or the dashboard.
