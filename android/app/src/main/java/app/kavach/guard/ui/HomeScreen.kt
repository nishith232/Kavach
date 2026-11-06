package app.kavach.guard.ui

import android.Manifest
import android.os.Build
import android.text.format.DateUtils
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.BatteryChargingFull
import androidx.compose.material.icons.rounded.Bolt
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.NotificationsActive
import androidx.compose.material.icons.rounded.RadioButtonUnchecked
import androidx.compose.material.icons.rounded.Visibility
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import app.kavach.guard.core.Alert
import app.kavach.guard.core.Pipeline
import app.kavach.guard.core.ScanEvent
import app.kavach.guard.core.Stats
import app.kavach.guard.core.Store
import kotlinx.coroutines.launch

@Composable
fun HomeScreen(onOpen: (Alert) -> Unit) {
    val ctx = LocalContext.current
    val perms = rememberPerms()
    val alerts by Store.alerts.collectAsStateWithLifecycle()
    val stats by Store.stats.collectAsStateWithLifecycle()
    val scanLog by Store.scanLog.collectAsStateWithLifecycle()
    val scope = rememberCoroutineScope()
    var demoBusy by remember { mutableStateOf(false) }
    var demoNote by remember { mutableStateOf<String?>(null) }
    val notifyLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {}

    val latest = alerts.firstOrNull()
    val recentThreat = latest != null && latest.isThreat && System.currentTimeMillis() - latest.time < 30 * 60_000
    val orb = when {
        !perms.listener -> OrbState.OFF
        recentThreat -> OrbState.ALERT
        else -> OrbState.ACTIVE
    }

    LazyColumn(
        contentPadding = PaddingValues(start = 20.dp, end = 20.dp, top = 12.dp, bottom = 28.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Row {
                        Text("Kavach", style = MaterialTheme.typography.displaySmall)
                        Text(" Guard", style = MaterialTheme.typography.displaySmall, color = K.Teal)
                    }
                    Text("AI scam shield for your messages", color = K.Muted, fontSize = 14.sp)
                }
                LivePill(on = perms.listener)
            }
        }

        item {
            Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally) {
                ShieldOrb(orb)
                Text(
                    when (orb) {
                        OrbState.ACTIVE -> "You're protected"
                        OrbState.ALERT -> "Threat blocked"
                        OrbState.OFF -> "Shield is off"
                    },
                    style = MaterialTheme.typography.headlineSmall,
                )
                Spacer(Modifier.height(4.dp))
                Text(
                    when (orb) {
                        OrbState.ACTIVE -> "Every SMS, WhatsApp and Telegram message is checked the moment it arrives."
                        OrbState.ALERT -> "Kavach just flagged a scam. Tap the alert below to see why."
                        OrbState.OFF -> "Give Kavach notification access to start scanning incoming messages."
                    },
                    color = K.Muted, textAlign = TextAlign.Center, fontSize = 14.sp,
                    modifier = Modifier.padding(horizontal = 16.dp),
                )
            }
        }

        if (!perms.ready || !perms.battery) {
            item {
                GlassCard(accent = if (!perms.ready) K.Warn else null) {
                    Text(if (perms.ready) "Keep the shield running" else "Turn on the shield", style = MaterialTheme.typography.titleMedium)
                    Spacer(Modifier.height(10.dp))
                    SetupStep(
                        done = perms.listener, icon = Icons.Rounded.Visibility,
                        title = "Allow notification access",
                        hint = "Lets Kavach read incoming messages to check them. If Android says \"Restricted setting\", open App info → ⋮ → Allow restricted settings, then try again.",
                        action = "Open", onAction = { openListenerSettings(ctx) },
                        secondary = "App info", onSecondary = { openAppInfo(ctx) },
                    )
                    SetupStep(
                        done = perms.notify, icon = Icons.Rounded.NotificationsActive,
                        title = "Allow scam alerts",
                        hint = "So Kavach can warn you before you open a message.",
                        action = "Allow",
                        onAction = { if (Build.VERSION.SDK_INT >= 33) notifyLauncher.launch(Manifest.permission.POST_NOTIFICATIONS) },
                    )
                    SetupStep(
                        done = perms.battery, icon = Icons.Rounded.BatteryChargingFull,
                        title = "Keep Kavach running",
                        hint = "iQOO/vivo: also Settings → Battery → Background power consumption management → Kavach Guard → Allow.",
                        action = "Allow", onAction = { requestBatteryExemption(ctx) },
                    )
                }
            }
        }

        item { StatsRow(stats) }

        item {
            Column {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    SectionTitle("Live scan", Modifier.weight(1f))
                    Text("every incoming message", color = K.Muted, fontSize = 11.sp)
                }
                Spacer(Modifier.height(6.dp))
                GlassCard {
                    if (scanLog.isEmpty()) {
                        Text(
                            if (perms.listener) "Waiting for messages… ask a friend to send you an SMS or WhatsApp."
                            else "Turn on notification access to see messages being checked here.",
                            color = K.Muted, fontSize = 13.sp,
                        )
                    }
                    scanLog.take(6).forEach { e -> ScanRow(e) { e.alertId?.let { id -> alerts.firstOrNull { it.id == id }?.let(onOpen) } } }
                }
            }
        }

        item { Column {
            GradientButton(
                text = if (demoBusy) "Analysing…" else "Simulate a scam SMS",
                icon = Icons.Rounded.Bolt,
                loading = demoBusy,
            ) {
                scope.launch {
                    demoBusy = true
                    demoNote = null
                    val a = runCatching {
                        Pipeline.process(ctx.applicationContext, Pipeline.DEMO_TEXT, "demo", "Messages (demo)", Pipeline.Mode.DEMO)
                    }.getOrNull()
                    demoNote = when {
                        a == null -> "Couldn't analyse. Check the server address in Settings."
                        a.source == "on-device" -> "Server unreachable: alert came from on-device rules only."
                        else -> null
                    }
                    demoBusy = false
                }
            }
            AnimatedVisibility(demoNote != null) {
                Text(demoNote.orEmpty(), color = K.Warn, fontSize = 13.sp, modifier = Modifier.padding(top = 8.dp, start = 4.dp))
            }
        } }

        item {
            Row(verticalAlignment = Alignment.CenterVertically) {
                SectionTitle("Recent alerts", Modifier.weight(1f))
                if (alerts.isNotEmpty()) Text("${alerts.size}", color = K.Muted, fontSize = 12.sp)
            }
        }

        if (alerts.isEmpty()) {
            item {
                GlassCard {
                    Text("No alerts yet", style = MaterialTheme.typography.titleMedium)
                    Text(
                        "Messages that look like scams will appear here with a risk score and what to do. Try \"Simulate a scam SMS\" to see one.",
                        color = K.Muted, fontSize = 14.sp,
                    )
                }
            }
        }

        items(alerts.take(30), key = { it.id }) { a -> AlertRow(a) { onOpen(a) } }
    }
}

@Composable
private fun ScanRow(e: ScanEvent, onClick: () -> Unit) {
    val (color, label) = when (e.status) {
        "checking" -> K.Violet to "Checking with AI…"
        "clean" -> K.Muted to "Clean · checked on phone"
        "done" -> verdictColor(e.verdict ?: "") to (verdictLabel(e.verdict ?: "") + (e.risk?.let { " · risk $it" } ?: ""))
        "offline" -> K.Warn to "Flagged on phone · AI offline"
        else -> K.Warn to "AI unreachable · on-device: no strong signs"
    }
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).clickable(enabled = e.alertId != null, onClick = onClick)
            .padding(vertical = 7.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (e.status == "checking") {
            CircularProgressIndicator(color = color, strokeWidth = 2.dp, modifier = Modifier.size(10.dp))
        } else {
            Box(Modifier.size(10.dp).clip(CircleShape).background(color))
        }
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(e.app, color = K.Text, fontWeight = FontWeight.SemiBold, fontSize = 13.sp, maxLines = 1)
                Spacer(Modifier.width(8.dp))
                Text(label, color = color, fontSize = 12.sp, fontWeight = FontWeight.Medium, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            Text(e.snippet, color = K.Muted, fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
    }
}

@Composable
private fun LivePill(on: Boolean) {
    val color = if (on) K.Teal else K.Muted
    Row(
        Modifier.clip(RoundedCornerShape(50)).background(color.copy(alpha = 0.12f)).padding(horizontal = 12.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(8.dp).clip(CircleShape).background(color))
        Spacer(Modifier.width(6.dp))
        Text(if (on) "LIVE" else "OFF", color = color, fontWeight = FontWeight.Bold, fontSize = 12.sp, letterSpacing = 1.sp)
    }
}

@Composable
private fun SetupStep(
    done: Boolean,
    icon: ImageVector,
    title: String,
    hint: String,
    action: String,
    onAction: () -> Unit,
    secondary: String? = null,
    onSecondary: (() -> Unit)? = null,
) {
    Row(Modifier.fillMaxWidth().padding(vertical = 6.dp), verticalAlignment = Alignment.Top) {
        Icon(
            if (done) Icons.Rounded.CheckCircle else Icons.Rounded.RadioButtonUnchecked, null,
            tint = if (done) K.Teal else K.Muted, modifier = Modifier.padding(top = 2.dp).size(22.dp),
        )
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(icon, null, tint = K.Text, modifier = Modifier.size(16.dp))
                Spacer(Modifier.width(6.dp))
                Text(title, fontWeight = FontWeight.SemiBold, fontSize = 15.sp, color = K.Text)
            }
            if (!done) {
                Text(hint, color = K.Muted, fontSize = 13.sp, lineHeight = 18.sp)
                Row {
                    TextButton(onClick = onAction) { Text(action, color = K.Teal, fontWeight = FontWeight.Bold) }
                    if (secondary != null && onSecondary != null) {
                        TextButton(onClick = onSecondary) { Text(secondary, color = K.Muted) }
                    }
                }
            }
        }
    }
}

@Composable
private fun StatsRow(stats: Stats) {
    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        StatCard("Scanned today", stats.scannedToday, K.Info, Modifier.weight(1f))
        StatCard("Threats flagged", stats.flaggedTotal, K.Danger, Modifier.weight(1f))
        StatCard("AI checks", stats.aiChecks, K.Violet, Modifier.weight(1f))
    }
}

@Composable
private fun StatCard(label: String, value: Int, color: androidx.compose.ui.graphics.Color, modifier: Modifier) {
    GlassCard(modifier) {
        Text("$value", fontSize = 26.sp, fontWeight = FontWeight.Black, color = color)
        Text(label, color = K.Muted, fontSize = 12.sp, maxLines = 1)
    }
}

@Composable
fun AlertRow(a: Alert, onClick: () -> Unit) {
    val color = verdictColor(a.verdict)
    GlassCard(onClick = onClick) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.width(4.dp).height(56.dp).clip(RoundedCornerShape(4.dp)).background(color))
            Spacer(Modifier.width(14.dp))
            Column(Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    VerdictChip(a.verdict)
                    Spacer(Modifier.weight(1f))
                    Text(
                        DateUtils.getRelativeTimeSpanString(a.time, System.currentTimeMillis(), DateUtils.MINUTE_IN_MILLIS).toString(),
                        color = K.Muted, fontSize = 12.sp,
                    )
                }
                Spacer(Modifier.height(6.dp))
                Text(
                    a.scamTypeLocal.ifBlank { a.scamType }.takeIf { it.isNotBlank() && it != "None" } ?: "Message check",
                    fontWeight = FontWeight.Bold, fontSize = 15.sp, color = K.Text, maxLines = 1, overflow = TextOverflow.Ellipsis,
                )
                Text(
                    "${a.appName} · “${a.original.replace('\n', ' ')}”",
                    color = K.Muted, fontSize = 13.sp, maxLines = 2, overflow = TextOverflow.Ellipsis,
                )
            }
        }
    }
}
