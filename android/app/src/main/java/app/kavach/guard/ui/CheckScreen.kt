package app.kavach.guard.ui

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
import kotlinx.coroutines.launch

@Composable
fun CheckScreen() {
    val ctx = LocalContext.current
    val clipboard = LocalClipboardManager.current
    val scope = rememberCoroutineScope()
    var text by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var result by remember { mutableStateOf<Alert?>(null) }

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
        error?.let { Text(it, color = K.Warn, fontSize = 14.sp) }
        AnimatedVisibility(result != null, enter = fadeIn() + slideInVertically { it / 6 }) {
            result?.let { AlertBody(it) }
        }
    }
}
