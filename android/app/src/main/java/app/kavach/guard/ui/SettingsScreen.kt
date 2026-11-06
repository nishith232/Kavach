package app.kavach.guard.ui

import android.Manifest
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import app.kavach.guard.KavachApp
import app.kavach.guard.core.Api
import app.kavach.guard.core.RuleEngine
import app.kavach.guard.core.Store
import kotlinx.coroutines.launch

private val LANGUAGES = listOf(
    "auto" to "Same as message", "te-IN" to "తెలుగు", "hi-IN" to "हिन्दी", "kn-IN" to "ಕನ್ನಡ", "ta-IN" to "தமிழ்",
    "ml-IN" to "മലയാളം", "mr-IN" to "मराठी", "bn-IN" to "বাংলা", "gu-IN" to "ગુજરાતી", "pa-IN" to "ਪੰਜਾਬੀ",
    "en-IN" to "English", "hi-en" to "Hinglish",
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen() {
    val ctx = LocalContext.current
    val settings by Store.settings.collectAsStateWithLifecycle()
    val perms = rememberPerms()
    val scope = rememberCoroutineScope()
    var url by remember { mutableStateOf(settings.serverUrl) }
    var status by remember { mutableStateOf<Pair<Boolean, String>?>(null) }
    var testing by remember { mutableStateOf(false) }
    val notifyLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {}

    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 20.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Text("Settings", style = MaterialTheme.typography.displaySmall)

        SectionTitle("AI server")
        GlassCard {
            OutlinedTextField(
                value = url,
                onValueChange = { url = it; status = null; Store.updateSettings { s -> s.copy(serverUrl = it) } },
                label = { Text("Kavach server address") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(16.dp),
                colors = OutlinedTextFieldDefaults.colors(
                    focusedTextColor = K.Text, unfocusedTextColor = K.Text,
                    focusedBorderColor = K.Teal, unfocusedBorderColor = K.GlassBorder, cursorColor = K.Teal,
                    focusedLabelColor = K.Teal, unfocusedLabelColor = K.Muted,
                ),
            )
            Spacer(Modifier.height(10.dp))
            GradientButton(if (testing) "Testing…" else "Test connection", null, loading = testing) {
                scope.launch {
                    testing = true
                    val ok = Api.health(url)
                    if (ok) (ctx.applicationContext as KavachApp).refreshRules()
                    status = ok to (if (ok) "Connected · ${RuleEngine.ruleCount} on-device rules" else "Can't reach $url")
                    testing = false
                }
            }
            status?.let { (ok, msg) ->
                Text(msg, color = if (ok) K.Teal else K.Danger, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 10.dp))
            }
            Spacer(Modifier.height(8.dp))
            Text(
                "On your laptop run:  uv run uvicorn app.main:app --host 0.0.0.0 --port 8000\n" +
                    "then enter http://<laptop Wi-Fi IP>:8000 (find it with ipconfig). Phone and laptop must be on the same Wi-Fi, or use a public tunnel URL.",
                color = K.Muted, fontSize = 12.sp, lineHeight = 17.sp,
            )
        }

        SectionTitle("Warning language")
        LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            items(LANGUAGES) { (code, label) ->
                FilterChip(
                    selected = settings.replyLanguage == code,
                    onClick = { Store.updateSettings { it.copy(replyLanguage = code) } },
                    label = { Text(label) },
                    colors = FilterChipDefaults.filterChipColors(
                        containerColor = K.Glass, labelColor = K.Muted,
                        selectedContainerColor = K.Teal.copy(alpha = 0.18f), selectedLabelColor = K.Teal,
                    ),
                )
            }
        }

        SectionTitle("Alerts")
        GlassCard {
            ToggleRow("Speak warnings aloud", "Kavach reads the warning in your language using Gnani's voice.", settings.speakAlerts) { v ->
                Store.updateSettings { it.copy(speakAlerts = v) }
            }
            ToggleRow("Warn on “Suspicious” too", "Off = only alert for clear scams.", settings.alertOnSuspicious) { v ->
                Store.updateSettings { it.copy(alertOnSuspicious = v) }
            }
            ToggleRow("Scan all apps", "Off = only SMS, WhatsApp, Telegram and other chat apps.", settings.scanAllApps) { v ->
                Store.updateSettings { it.copy(scanAllApps = v) }
            }
        }

        SectionTitle("Permissions")
        GlassCard {
            PermRow("Notification access", perms.listener) { openListenerSettings(ctx) }
            PermRow("Alerts", perms.notify) {
                if (Build.VERSION.SDK_INT >= 33) notifyLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
            }
            PermRow("Run in background", perms.battery) { requestBatteryExemption(ctx) }
            TextButton(onClick = { openAppInfo(ctx) }) { Text("App info (Allow restricted settings)", color = K.Muted) }
        }

        val app = ctx.applicationContext as KavachApp
        val clipboard = LocalClipboardManager.current
        var crash by remember { mutableStateOf(runCatching { KavachApp.crashFile(app).takeIf { it.exists() }?.readText() }.getOrNull()) }
        if (crash != null || RuleEngine.skipped.isNotEmpty()) {
            SectionTitle("Diagnostics")
            GlassCard(accent = K.Warn) {
                if (RuleEngine.skipped.isNotEmpty()) {
                    Text("${RuleEngine.skipped.size} rule(s) skipped on this phone", color = K.Warn, fontWeight = FontWeight.SemiBold)
                    Text(RuleEngine.skipped.joinToString("\n"), color = K.Muted, fontSize = 11.sp)
                }
                crash?.let { report ->
                    Text("Last crash report", color = K.Warn, fontWeight = FontWeight.SemiBold)
                    Text(report.take(1200), color = K.Muted, fontSize = 11.sp, lineHeight = 14.sp)
                    Row {
                        TextButton(onClick = { clipboard.setText(AnnotatedString(report)) }) { Text("Copy report", color = K.Teal) }
                        TextButton(onClick = { KavachApp.crashFile(app).delete(); crash = null }) { Text("Clear", color = K.Muted) }
                    }
                }
            }
        }

        SectionTitle("Privacy")
        GlassCard {
            Text(
                "Every message is checked on your phone first with ${RuleEngine.ruleCount} scam rules. Only messages that look " +
                    "suspicious are sent to your Kavach server for an AI verdict. Nothing else leaves the phone.",
                color = K.Muted, fontSize = 13.sp, lineHeight = 19.sp,
            )
            TextButton(onClick = { Store.clearAlerts() }) { Text("Clear alert history", color = K.Danger) }
        }
        Spacer(Modifier.height(16.dp))
    }
}

@Composable
private fun ToggleRow(title: String, subtitle: String, checked: Boolean, onChange: (Boolean) -> Unit) {
    Row(Modifier.fillMaxWidth().padding(vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(title, color = K.Text, fontWeight = FontWeight.SemiBold, fontSize = 15.sp)
            Text(subtitle, color = K.Muted, fontSize = 12.sp)
        }
        Spacer(Modifier.width(12.dp))
        Switch(
            checked = checked, onCheckedChange = onChange,
            colors = SwitchDefaults.colors(
                checkedThumbColor = K.Bg, checkedTrackColor = K.Teal,
                uncheckedThumbColor = K.Muted, uncheckedTrackColor = K.Glass, uncheckedBorderColor = K.GlassBorder,
            ),
        )
    }
}

@Composable
private fun PermRow(title: String, granted: Boolean, onFix: () -> Unit) {
    Row(Modifier.fillMaxWidth().padding(vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(title, color = K.Text, fontSize = 15.sp, modifier = Modifier.weight(1f))
        if (granted) Text("ON", color = K.Teal, fontWeight = FontWeight.Bold, fontSize = 13.sp)
        else TextButton(onClick = onFix) { Text("Turn on", color = K.Warn, fontWeight = FontWeight.Bold) }
    }
}
