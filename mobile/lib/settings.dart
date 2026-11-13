// Settings saved on the phone (shared_preferences):
//   - server IP   (laptop running MediaMTX + backend)
//   - language    (English / French / Arabic) for listening and speaking
//   - mock mode   (fake answers while the backend isn't ready)
import 'package:material_ui/material_ui.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'languages.dart';

// All settings together.
class AppSettings {
  const AppSettings({required this.serverIp, required this.language, required this.mock});
  final String serverIp;
  final AppLanguage language;
  final bool mock;
}

// Reads and writes the settings.
class SettingsStore {
  static const _ipKey = 'server_ip';
  static const _languageKey = 'language';
  static const _mockKey = 'mock_mode';

  static Future<AppSettings> load() async {
    final prefs = await SharedPreferences.getInstance();
    return AppSettings(
      serverIp: prefs.getString(_ipKey) ?? '',
      language: languageFromCode(prefs.getString(_languageKey) ?? 'en'),
      mock: prefs.getBool(_mockKey) ?? true, // ON by default until the backend exists
    );
  }

  static Future<void> save(AppSettings settings) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_ipKey, settings.serverIp.trim());
    await prefs.setString(_languageKey, settings.language.code);
    await prefs.setBool(_mockKey, settings.mock);
  }
}

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  final _ipController = TextEditingController();
  AppLanguage _language = english;
  bool _mock = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    // Show the settings that are already saved.
    SettingsStore.load().then((s) {
      if (!mounted) return;
      setState(() {
        _ipController.text = s.serverIp;
        _language = s.language;
        _mock = s.mock;
      });
    });
  }

  @override
  void dispose() {
    _ipController.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final ip = _ipController.text.trim();
    // Simple check: we only want the IP, not a full URL.
    // (Empty is allowed, so mock answers can be tried without a server.)
    if (ip.contains('://') || ip.contains(' ')) {
      setState(() => _error = 'Type only the IP, for example 192.168.1.20');
      return;
    }
    await SettingsStore.save(AppSettings(serverIp: ip, language: _language, mock: _mock));
    if (mounted) Navigator.pop(context); // back to the main screen
  }

  @override
  Widget build(BuildContext context) {
    const big = TextStyle(fontSize: 24, color: Colors.white);
    const heading = TextStyle(fontSize: 22, fontWeight: FontWeight.bold, color: Color(0xFFFFD400));

    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: ListView(
        padding: const EdgeInsets.all(24),
        children: [
          // ----- Server IP -----
          TextField(
            controller: _ipController,
            keyboardType: TextInputType.url, // keyboard with digits and dots
            style: big,
            decoration: InputDecoration(
              labelText: 'Server IP address',
              labelStyle: const TextStyle(fontSize: 20),
              hintText: '192.168.1.20',
              errorText: _error,
              border: const OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 8),
          const Text(
            'The laptop running MediaMTX and the backend. Same Wi-Fi as the phone.',
            style: TextStyle(fontSize: 18, color: Colors.white70),
          ),
          const SizedBox(height: 28),

          // ----- Language -----
          Semantics(header: true, child: const Text('Language', style: heading)),
          RadioGroup<AppLanguage>(
            groupValue: _language,
            onChanged: (value) => setState(() => _language = value!),
            child: Column(
              children: [
                for (final lang in allLanguages)
                  RadioListTile<AppLanguage>(
                    value: lang,
                    title: Text(lang.name, style: big),
                  ),
              ],
            ),
          ),
          const SizedBox(height: 20),

          // ----- Mock mode -----
          SwitchListTile(
            value: _mock,
            onChanged: (value) => setState(() => _mock = value),
            title: const Text('Mock answers', style: big),
            subtitle: const Text(
              'Fake answers, no backend needed',
              style: TextStyle(fontSize: 18, color: Colors.white70),
            ),
          ),
          const SizedBox(height: 32),

          SizedBox(
            height: 80,
            child: ElevatedButton(
              onPressed: _save,
              child: const Text('Save', style: TextStyle(fontSize: 28, fontWeight: FontWeight.bold)),
            ),
          ),
        ],
      ),
    );
  }
}
