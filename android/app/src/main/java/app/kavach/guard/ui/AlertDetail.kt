package app.kavach.guard.ui

import android.text.format.DateUtils
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.automirrored.rounded.VolumeUp
import androidx.compose.material.icons.rounded.Call
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.material.icons.automirrored.rounded.ManageSearch
import androidx.compose.material.icons.rounded.RecordVoiceOver
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import app.kavach.guard.core.Alert
import app.kavach.guard.core.Notifier
import app.kavach.guard.core.Pipeline
import app.kavach.guard.core.VoiceAssistant
import kotlinx.coroutines.launch

@Composable
fun AlertDetailScreen(a: Alert, onBack: () -> Unit) {
    Column(
        Modifier.fillMaxSize().statusBarsPadding().navigationBarsPadding()
            .verticalScroll(rememberScrollState()).padding(horizontal = 20.dp, vertical = 8.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = { Notifier.stopSpeaking(); onBack() }) {
                Icon(Icons.AutoMirrored.Rounded.ArrowBack, "Back", tint = K.Text)
            }
            Text("Alert details", style = MaterialTheme.typography.titleMedium)
        }
        AlertBody(a)
        Spacer(Modifier.height(24.dp))
    }
}

/** Shared by the alert screen and the manual Check screen. */
@Composable
fun AlertBody(a: Alert) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val color = verdictColor(a.verdict)
    var busy by remember(a.id) { mutableStateOf(false) }
    var note by remember(a.id) { mutableStateOf<String?>(null) }
    var explanation by remember(a.id) { mutableStateOf<String?>(null) }
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally) {
            RiskGauge(a.risk, color)
            VerdictChip(a.verdict, big = true)
            val type = a.scamTypeLocal.ifBlank { a.scamType }.takeIf { it.isNotBlank() && it != "None" }
            if (type != null) {
                Spacer(Modifier.height(10.dp))
                Text(type, style = MaterialTheme.typography.headlineSmall, textAlign = TextAlign.Center)
            }
            Spacer(Modifier.height(4.dp))
            Text(
                a.appName + (if (a.sender.isNotBlank()) " · from ${a.sender}" else ""),
                color = K.Text, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, textAlign = TextAlign.Center,
            )
            Text(
                DateUtils.formatDateTime(
                    ctx, a.time, DateUtils.FORMAT_SHOW_DATE or DateUtils.FORMAT_SHOW_TIME or DateUtils.FORMAT_ABBREV_MONTH,
                ) + " · " + DateUtils.getRelativeTimeSpanString(a.time, System.currentTimeMillis(), DateUtils.MINUTE_IN_MILLIS),
                color = K.Muted, fontSize = 13.sp,
            )
        }

        if (a.status == "checking") {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.Center, verticalAlignment = Alignment.CenterVertically) {
                CircularProgressIndicator(color = K.Violet, strokeWidth = 2.dp, modifier = Modifier.size(16.dp))
                Spacer(Modifier.width(10.dp))
                Text("Kavach AI is analysing this message…", color = K.Violet, fontSize = 14.sp)
            }
        }

        // Messages only checked on the phone (or not checked because the server was down) can get a full AI check.
        if (a.status == "clean" || a.status == "error") {
            GradientButton(if (busy) "Analysing…" else "Analyse with AI", Icons.AutoMirrored.Rounded.ManageSearch, loading = busy) {
                if (busy) return@GradientButton
                scope.launch {
                    busy = true
                    note = null
                    runCatching { Pipeline.recheck(ctx.applicationContext, a) }
                        .onFailure { note = "Couldn't reach the Kavach server (${it.message?.take(80)})." }
                    busy = false
                }
            }
        }

        // Threats: the voice assistant explains this exact message aloud (Gnani Timbre), from its saved analysis.
        if (a.isThreat && a.status != "checking") {
            GradientButton(
                if (busy) "Preparing voice…" else "Explain aloud", Icons.Rounded.RecordVoiceOver, loading = busy,
                colors = listOf(K.Danger, K.Violet),
            ) {
                if (busy) return@GradientButton
                scope.launch {
                    busy = true
                    note = null
                    runCatching {
                        VoiceAssistant.ask(ctx.applicationContext, null, "Explain why this message is suspicious", focusId = a.id)
                    }.onSuccess { r ->
                        explanation = r.reply
                        Notifier.speak(r.audioPath)
                        if (r.ttsError != null) note = "Voice unavailable right now; showing text."
                    }.onFailure { note = "Couldn't reach the Kavach server (${it.message?.take(80)})." }
                    busy = false
                }
            }
        }
        note?.let { Text(it, color = K.Warn, fontSize = 13.sp) }
        explanation?.let { GlassCard(accent = K.Violet) { Text(it, style = MaterialTheme.typography.bodyLarge) } }

        if (a.audioPath != null) {
            GradientButton("Hear the warning", Icons.AutoMirrored.Rounded.VolumeUp) { Notifier.speak(a.audioPath) }
        }

        if (a.summary.isNotBlank()) {
            GlassCard(accent = color) { Text(a.summary, style = MaterialTheme.typography.bodyLarge) }
        }

        if (a.redFlags.isNotEmpty()) {
            SectionTitle("Red flags")
            a.redFlags.forEach { f ->
                Column {
                    if (f.quote.isNotBlank()) {
                        Box(
                            Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(K.Danger.copy(alpha = 0.10f))
                                .border(1.dp, K.Danger.copy(alpha = 0.35f), RoundedCornerShape(12.dp)).padding(12.dp),
                        ) { Text("“${f.quote}”", color = K.Text, fontSize = 14.sp, fontWeight = FontWeight.Medium) }
                    }
                    Text(f.why, color = K.Muted, fontSize = 14.sp, modifier = Modifier.padding(start = 4.dp, top = 6.dp))
                }
            }
        }

        if (a.facts.isNotEmpty()) {
            SectionTitle("The truth")
            GlassCard {
                a.facts.forEach { fact ->
                    Row(Modifier.padding(vertical = 5.dp)) {
                        Icon(Icons.Rounded.CheckCircle, null, tint = K.Teal, modifier = Modifier.size(18.dp).padding(top = 2.dp))
                        Spacer(Modifier.width(10.dp))
                        Text(fact, fontSize = 14.sp, color = K.Text)
                    }
                }
            }
        }

        if (a.actions.isNotEmpty()) {
            SectionTitle("What to do now")
            GlassCard {
                a.actions.forEachIndexed { i, step ->
                    Row(Modifier.padding(vertical = 6.dp), verticalAlignment = Alignment.Top) {
                        Box(
                            Modifier.size(24.dp).clip(CircleShape).background(K.Violet.copy(alpha = 0.25f)),
                            contentAlignment = Alignment.Center,
                        ) { Text("${i + 1}", color = K.Text, fontSize = 12.sp, fontWeight = FontWeight.Bold) }
                        Spacer(Modifier.width(12.dp))
                        Text(step, fontSize = 14.sp, color = K.Text, fontWeight = if (i == 0) FontWeight.SemiBold else FontWeight.Normal)
                    }
                }
            }
        }

        if (a.isThreat) {
            Row(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(18.dp)).background(K.Danger.copy(alpha = 0.15f))
                    .border(1.dp, K.Danger.copy(alpha = 0.5f), RoundedCornerShape(18.dp))
                    .clickable { dial1930(ctx) }.padding(16.dp),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.Center,
            ) {
                Icon(Icons.Rounded.Call, null, tint = K.Danger)
                Spacer(Modifier.width(10.dp))
                Text("Call 1930 · Cyber fraud helpline", color = K.Danger, fontWeight = FontWeight.Bold)
            }
        }

        if (a.localLabels.isNotEmpty()) {
            SectionTitle("On-device signals")
            GlassCard { Text(a.localLabels.joinToString(" · "), color = K.Muted, fontSize = 13.sp) }
        }

        SectionTitle("Original message")
        GlassCard {
            if (a.sender.isNotBlank()) Text("From: ${a.sender}", color = K.Text, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
            Text(a.original, color = K.Muted, fontSize = 14.sp)
        }

        Text(
            when {
                a.source == "ai" -> "Verdict by Kavach AI${if (a.language.isNotBlank()) " · reply in ${a.language}" else ""}"
                a.status == "clean" -> "Checked on the phone only (no warning signs found)"
                a.status == "checking" -> "Waiting for the AI verdict"
                a.status == "error" -> "Not judged: the AI server was unreachable"
                else -> "On-device rules only (AI server was unreachable)"
            },
            color = K.Muted, fontSize = 12.sp, modifier = Modifier.fillMaxWidth(), textAlign = TextAlign.Center,
        )
    }
}
