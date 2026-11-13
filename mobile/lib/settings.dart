// Settings: the server IP, saved on the phone with shared_preferences.
import 'package:material_ui/material_ui.dart';
import 'package:shared_preferences/shared_preferences.dart';

// Reads and writes the saved server IP.
class SettingsStore {
  static const _key = 'server_ip';

  static Future<String> loadServerIp() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_key) ?? '';
  }

  static Future<void> saveServerIp(String ip) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_key, ip.trim());
  }
}

// Screen where the user types the laptop's IP address (e.g. 192.168.1.20).
class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  final _controller = TextEditingController();
  String? _error;

  @override
  void initState() {
    super.initState();
    // Show the IP that is already saved.
    SettingsStore.loadServerIp().then((ip) => setState(() => _controller.text = ip));
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final ip = _controller.text.trim();
    // Simple check: we only want the IP, not a full URL.
    if (ip.isEmpty || ip.contains('://') || ip.contains(' ')) {
      setState(() => _error = 'Type only the IP, for example 192.168.1.20');
      return;
    }
    await SettingsStore.saveServerIp(ip);
    if (mounted) Navigator.pop(context); // back to the stream screen
  }

  @override
  Widget build(BuildContext context) {
    const big = TextStyle(fontSize: 24, color: Colors.white);
    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: ListView(
        padding: const EdgeInsets.all(24),
        children: [
          TextField(
            controller: _controller,
            keyboardType: TextInputType.url, // keyboard with digits and dots
            style: big,
            decoration: InputDecoration(
              labelText: 'Server IP address',
              labelStyle: const TextStyle(fontSize: 20),
              hintText: '192.168.1.20',
              errorText: _error,
              border: const OutlineInputBorder(),
            ),
            onSubmitted: (_) => _save(),
          ),
          const SizedBox(height: 12),
          const Text(
            'The laptop running MediaMTX. Phone and laptop must be on the same Wi-Fi.',
            style: TextStyle(fontSize: 18, color: Colors.white70),
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
