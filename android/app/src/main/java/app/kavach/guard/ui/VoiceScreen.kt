package app.kavach.guard.ui

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
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
import androidx.compose.material.icons.automirrored.rounded.VolumeUp
import androidx.compose.material.icons.rounded.Mic
import androidx.compose.material.icons.rounded.Stop
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import app.kavach.guard.core.Alert
import app.kavach.guard.core.AssistantReply
import app.kavach.guard.core.Notifier
import app.kavach.guard.core.Store
import app.kavach.guard.core.VoiceAssistant
import app.kavach.guard.core.VoiceRecorder
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

private enum class Phase { IDLE, LISTENING, THINKING, SPEAKING }

/** "Ask Kavach": voice commands about the messages Kavach has scanned (Gnani Prisma in, Gnani Timbre out). */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun VoiceScreen(onOpen: (Alert) -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val records by Store.alerts.collectAsStateWithLifecycle()
    val recorder = remember { VoiceRecorder() }
    var phase by remember { mutableStateOf(Phase.IDLE) }
    var reply by remember { mutableStateOf<AssistantReply?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var seconds by remember { mutableFloatStateOf(0f) }
    var level by remember { mutableFloatStateOf(0f) }

    DisposableEffect(Unit) { onDispose { recorder.cancel(); Notifier.stopSpeaking() } }

    fun play(r: AssistantReply) {
        if (r.audioPath == null) { phase = Phase.IDLE; return }
        phase = Phase.SPEAKING
        Notifier.speak(r.audioPath) { scope.launch { if (phase == Phase.SPEAKING) phase = Phase.IDLE } }
    }

    fun send(wav: ByteArray?, text: String?) {
        phase = Phase.THINKING
        error = null
        scope.launch {
            runCatching { VoiceAssistant.ask(ctx.applicationContext, wav, text) }
                .onSuccess { reply = it; play(it) }
                .onFailure {
                    error = "Couldn't get an answer (${it.message?.take(100)}). Check Settings → AI server."
                    phase = Phase.IDLE
                }
        }
    }

    fun finish() {
        if (phase != Phase.LISTENING) return
        phase = Phase.THINKING
        scope.launch {
            val wav = recorder.stop()
            if (wav.size < 44 + VoiceRecorder.RATE) {        // under half a second
                error = "That was too short. Tap the mic, say your command, then tap again."
                phase = Phase.IDLE
            } else {
                send(wav, null)
            }
        }
    }

    fun startListening() {
        Notifier.stopSpeaking()
        error = null
        runCatching { recorder.start(scope) { scope.launch { finish() } } }
            .onSuccess { phase = Phase.LISTENING }
            .onFailure { error = "Microphone unavailable: ${it.message}" }
    }

    val micPermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) {
            startListening()
        } else {
            error = "Kavach needs microphone permission to hear your command."
        }
    }

    LaunchedEffect(phase) {
        while (phase == Phase.LISTENING) {
            seconds = recorder.seconds
            level = recorder.level
            delay(100)
        }
        level = 0f
    }

    LazyColumn(
        contentPadding = PaddingValues(start = 20.dp, end = 20.dp, top = 12.dp, bottom = 28.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item {
            Column {
                Text("Ask Kavach", style = MaterialTheme.typography.displaySmall)
                Text(
                    "Ask about the messages Kavach has scanned, in your language. Answers come only from your real history.",
                    color = K.Muted, fontSize = 14.sp,
                )
            }
        }

        item {
            Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally) {
                MicOrb(phase, level) {
                    when (phase) {
                        Phase.IDLE -> {
                            val granted = ContextCompat.checkSelfPermission(ctx, Manifest.permission.RECORD_AUDIO) ==
                                PackageManager.PERMISSION_GRANTED
                            if (granted) startListening() else micPermission.launch(Manifest.permission.RECORD_AUDIO)
                        }
                        Phase.LISTENING -> finish()
                        Phase.SPEAKING -> { Notifier.stopSpeaking(); phase = Phase.IDLE }
                        Phase.THINKING -> Unit
                    }
                }
                Spacer(Modifier.height(10.dp))
                Text(
                    when (phase) {
                        Phase.IDLE -> "Tap and speak"
                        Phase.LISTENING -> "Listening… %.0fs · tap to finish".format(seconds)
                        Phase.THINKING -> "Understanding (Gnani Prisma)…"
                        Phase.SPEAKING -> "Speaking (Gnani Timbre) · tap to stop"
                    },
                    style = MaterialTheme.typography.titleMedium,
                    color = if (phase == Phase.LISTENING) K.Danger else K.Text,
                )
                if (records.isEmpty()) {
                    Text(
                        "No scanned messages yet, so answers will say there is nothing to report.",
                        color = K.Muted, fontSize = 12.sp, textAlign = TextAlign.Center, modifier = Modifier.padding(top = 4.dp),
                    )
                }
            }
        }

        item {
            Column {
                SectionTitle("Try saying")
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    VoiceAssistant.QUICK_COMMANDS.forEach { (label, command) ->
                        Text(
                            label, color = K.Text, fontSize = 13.sp, fontWeight = FontWeight.Medium,
                            modifier = Modifier.clip(RoundedCornerShape(50)).background(K.Glass)
                                .border(1.dp, K.GlassBorder, RoundedCornerShape(50))
                                .clickable(enabled = phase == Phase.IDLE || phase == Phase.SPEAKING) {
                                    Notifier.stopSpeaking(); send(null, command)
                                }
                                .padding(horizontal = 14.dp, vertical = 8.dp),
                        )
                    }
                }
                Text(
                    "e.g. \"Show my suspicious messages\", \"पिछले घंटे के मैसेज चेक करो\", \"నా అలర్ట్స్ చదువు\"",
                    color = K.Muted, fontSize = 12.sp, modifier = Modifier.padding(top = 6.dp),
                )
            }
        }

        error?.let { msg -> item { Text(msg, color = K.Warn, fontSize = 14.sp) } }

        reply?.let { r ->
            item {
                GlassCard {
                    Text("YOU SAID", style = MaterialTheme.typography.labelSmall)
                    Text("“${r.transcript}”", color = K.Text, fontSize = 15.sp)
                    if (r.heardByGnani) Text("Heard by Gnani Prisma", color = K.Muted, fontSize = 11.sp)
                }
            }
            item {
                GlassCard(accent = K.Teal) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("KAVACH" + (if (r.languageName.isNotBlank()) " · ${r.languageName}" else ""),
                            style = MaterialTheme.typography.labelSmall, modifier = Modifier.weight(1f))
                        if (r.audioPath != null) {
                            TextButton(onClick = { play(r) }) {
                                Icon(Icons.AutoMirrored.Rounded.VolumeUp, null, tint = K.Teal, modifier = Modifier.size(18.dp))
                                Text(" Replay", color = K.Teal, fontSize = 13.sp)
                            }
                        }
                    }
                    Text(r.reply, style = MaterialTheme.typography.bodyLarge)
                    r.ttsError?.let { Text("Voice unavailable right now ($it). Showing text only.", color = K.Muted, fontSize = 11.sp) }
                }
            }
            val matched = r.recordIds.mapNotNull { id -> records.firstOrNull { it.id == id } }
            if (matched.isNotEmpty()) {
                item { SectionTitle("Messages (${matched.size}) · tap to open") }
                items(matched, key = { "v_" + it.id }) { a -> GlassCard(onClick = { onOpen(a) }) { RecordRow(a) } }
            }
        }
    }
}

@Composable
private fun MicOrb(phase: Phase, level: Float, onClick: () -> Unit) {
    val pulse by rememberInfiniteTransition(label = "mic").animateFloat(
        initialValue = 1f, targetValue = 1.08f,
        animationSpec = infiniteRepeatable(tween(700), RepeatMode.Reverse), label = "pulse",
    )
    val listening = phase == Phase.LISTENING
    val colors = if (listening) listOf(K.Danger, K.Violet) else listOf(K.Violet, K.Teal)
    Box(
        Modifier.size(150.dp).scale(if (listening) pulse + level * 0.15f else 1f),
        contentAlignment = Alignment.Center,
    ) {
        Box(Modifier.size(150.dp).clip(CircleShape).background(colors.first().copy(alpha = 0.15f)))
        Box(
            Modifier.size(112.dp).clip(CircleShape).background(Brush.linearGradient(colors))
                .clickable(enabled = phase != Phase.THINKING, onClick = onClick),
            contentAlignment = Alignment.Center,
        ) {
            when (phase) {
                Phase.THINKING -> CircularProgressIndicator(color = K.Bg, strokeWidth = 3.dp, modifier = Modifier.size(40.dp))
                Phase.LISTENING, Phase.SPEAKING -> Icon(Icons.Rounded.Stop, "Stop", tint = K.Bg, modifier = Modifier.size(48.dp))
                Phase.IDLE -> Icon(Icons.Rounded.Mic, "Speak", tint = K.Bg, modifier = Modifier.size(52.dp))
            }
        }
    }
}
