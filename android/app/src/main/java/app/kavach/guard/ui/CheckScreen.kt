package app.kavach.guard.ui

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.slideInVertically
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.ContentPaste
import androidx.compose.material.icons.rounded.PhoneInTalk
import androidx.compose.material.icons.automirrored.rounded.ManageSearch
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
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
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import app.kavach.guard.core.Alert
import app.kavach.guard.core.Pipeline
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

@Composable
fun CheckScreen() {
    val ctx = LocalContext.current
    val clipboard = LocalClipboardManager.current
    val scope = rememberCoroutineScope()
    var text by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var result by remember { mutableStateOf<Alert?>(null) }
    var recBusy by remember { mutableStateOf(false) }

    // Saved call recording (the phone's own call recorder, WhatsApp voice note, etc.) -> Gnani Prisma -> verdict.
    val pickRecording = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri == null) return@rememberLauncherForActivityResult
        scope.launch {
            recBusy = true
            error = null
            result = null
            runCatching {
                val (name, bytes) = withContext(Dispatchers.IO) { Pipeline.readRecording(ctx, uri) }
                Pipeline.processRecording(ctx.applicationContext, name, bytes)
            }.onSuccess { a ->
                result = a
                if (a.status == "error") error = a.summary
            }.onFailure { error = it.message ?: "Couldn't read this recording." }
            recBusy = false
        }
    }

    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 20.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Text("Check a message", style = MaterialTheme.typography.displaySmall)
        Text(
            "Paste any SMS, WhatsApp forward, email or call script, in any Indian language.",
            color = K.Muted, fontSize = 14.sp,
        )
        OutlinedTextField(
            value = text,
            onValueChange = { text = it; error = null },
            modifier = Modifier.fillMaxWidth(),
            minLines = 5,
            placeholder = { Text("e.g. Dear customer, your KYC is pending. Share the OTP to avoid account block…", color = K.Muted) },
            shape = RoundedCornerShape(20.dp),
            colors = OutlinedTextFieldDefaults.colors(
                focusedTextColor = K.Text, unfocusedTextColor = K.Text,
                focusedContainerColor = K.Glass, unfocusedContainerColor = K.Glass,
                focusedBorderColor = K.Teal, unfocusedBorderColor = K.GlassBorder, cursorColor = K.Teal,
            ),
        )
        Row(verticalAlignment = Alignment.CenterVertically) {
            TextButton(onClick = { clipboard.getText()?.text?.let { text = it } }) {
                Icon(Icons.Rounded.ContentPaste, null, tint = K.Teal)
                Text("  Paste", color = K.Teal)
            }
            if (text.isNotEmpty()) TextButton(onClick = { text = ""; result = null }) { Text("Clear", color = K.Muted) }
        }
        GradientButton(if (busy) "Analysing…" else "Analyse with Kavach", Icons.AutoMirrored.Rounded.ManageSearch, loading = busy) {
            if (text.isBlank() || busy) return@GradientButton
            scope.launch {
                busy = true
                error = null
                result = null
                runCatching {
                    Pipeline.process(ctx.applicationContext, text.trim(), "manual", "Pasted text", Pipeline.Mode.MANUAL)
                }.onSuccess { result = it }
                    .onFailure { error = "Couldn't reach the Kavach server (${it.message?.take(80)}). Check Settings → AI server." }
                busy = false
            }
        }
        SectionTitle("Or check a call recording")
        Text(
            "Pick a recorded call or voice note (m4a, mp3, amr, ogg, opus, wav · up to 10 MB). Kavach separates the speakers, " +
                "finds the scam lines and saves the result in History. Tip: you can also Share a recording to Kavach.",
            color = K.Muted, fontSize = 13.sp,
        )
        GradientButton(
            if (recBusy) "Transcribing with Gnani… (up to 2 min)" else "Check a call recording", Icons.Rounded.PhoneInTalk,
            loading = recBusy, colors = listOf(K.Teal, K.Violet),
        ) {
            if (!recBusy && !busy) pickRecording.launch(arrayOf("audio/*", "video/mp4", "application/ogg"))
        }
        error?.let { Text(it, color = K.Warn, fontSize = 14.sp) }
        AnimatedVisibility(result != null, enter = fadeIn() + slideInVertically { it / 6 }) {
            result?.let { AlertBody(it) }
        }
    }
}
