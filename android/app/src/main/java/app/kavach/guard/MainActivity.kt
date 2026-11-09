package app.kavach.guard

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.togetherWith
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
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ManageSearch
import androidx.compose.material.icons.rounded.History
import androidx.compose.material.icons.rounded.Mic
import androidx.compose.material.icons.rounded.Settings
import androidx.compose.material.icons.rounded.Shield
import androidx.compose.material3.Icon
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.MutableState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import app.kavach.guard.core.Notifier
import app.kavach.guard.core.Pipeline
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.util.UUID
import app.kavach.guard.core.Store
import app.kavach.guard.ui.AlertDetailScreen
import app.kavach.guard.ui.AuroraBackground
import app.kavach.guard.ui.CheckScreen
import app.kavach.guard.ui.HistoryFilter
import app.kavach.guard.ui.HistoryScreen
import app.kavach.guard.ui.HomeScreen
import app.kavach.guard.ui.K
import app.kavach.guard.ui.KavachTheme
import app.kavach.guard.ui.SettingsScreen
import app.kavach.guard.ui.VoiceScreen

class MainActivity : ComponentActivity() {
    private val openAlertId = mutableStateOf<String?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        openAlertId.value = intent?.getStringExtra(Notifier.EXTRA_ALERT_ID)
        handleSharedRecording(intent)
        setContent { KavachTheme { KavachRoot(openAlertId) } }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        intent.getStringExtra(Notifier.EXTRA_ALERT_ID)?.let { openAlertId.value = it }
        handleSharedRecording(intent)
    }

    /** "Share → Kavach Guard" from the dialer / file manager / WhatsApp: analyse the recording and open its record. */
    private fun handleSharedRecording(intent: Intent?) {
        if (intent?.action != Intent.ACTION_SEND) return
        @Suppress("DEPRECATION")
        val uri = intent.getParcelableExtra<Uri>(Intent.EXTRA_STREAM) ?: return
        val id = UUID.randomUUID().toString()
        val app = application as KavachApp
        app.scope.launch {
            runCatching { Pipeline.readRecording(applicationContext, uri) }
                .onSuccess { (name, bytes) ->
                    withContext(Dispatchers.Main) { openAlertId.value = id }
                    Pipeline.processRecording(applicationContext, name, bytes, id)
                }
                .onFailure { e ->
                    withContext(Dispatchers.Main) {
                        Toast.makeText(this@MainActivity, e.message ?: "Couldn't read this recording", Toast.LENGTH_LONG).show()
                    }
                }
        }
        setIntent(Intent(this, MainActivity::class.java))   // don't re-run on rotation
    }
}

private data class Tab(val label: String, val icon: ImageVector)

private val TABS = listOf(
    Tab("Shield", Icons.Rounded.Shield),
    Tab("History", Icons.Rounded.History),
    Tab("Ask", Icons.Rounded.Mic),
    Tab("Check", Icons.AutoMirrored.Rounded.ManageSearch),
    Tab("Settings", Icons.Rounded.Settings),
)

@Composable
private fun KavachRoot(openAlertId: MutableState<String?>) {
    var tab by rememberSaveable { mutableIntStateOf(0) }
    var historyFilter by rememberSaveable { mutableStateOf(HistoryFilter.ALL) }
    val alerts by Store.alerts.collectAsStateWithLifecycle()
    val detail = alerts.firstOrNull { it.id == openAlertId.value }

    AuroraBackground {
        AnimatedContent(detail, transitionSpec = { fadeIn() togetherWith fadeOut() }, label = "detail") { current ->
            if (current != null) {
                BackHandler { Notifier.stopSpeaking(); openAlertId.value = null }
                AlertDetailScreen(current) { openAlertId.value = null }
            } else {
                Scaffold(
                    containerColor = Color.Transparent,
                    bottomBar = { GlassNavBar(tab) { tab = it } },
                ) { pad ->
                    Box(Modifier.fillMaxSize().padding(pad)) {
                        AnimatedContent(tab, transitionSpec = { fadeIn() togetherWith fadeOut() }, label = "tab") { t ->
                            when (t) {
                                0 -> HomeScreen(
                                    onOpen = { openAlertId.value = it.id },
                                    onFilter = { historyFilter = it; tab = 1 },
                                )
                                1 -> HistoryScreen(historyFilter, onFilter = { historyFilter = it }) { openAlertId.value = it.id }
                                2 -> VoiceScreen(onOpen = { openAlertId.value = it.id })
                                3 -> CheckScreen()
                                else -> SettingsScreen()
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun GlassNavBar(selected: Int, onSelect: (Int) -> Unit) {
    val shape = RoundedCornerShape(28.dp)
    Row(
        Modifier
            .navigationBarsPadding()
            .padding(horizontal = 20.dp, vertical = 10.dp)
            .fillMaxWidth()
            .clip(shape)
            .background(Color(0xE60E1426))
            .border(1.dp, K.GlassBorder, shape)
            .padding(6.dp),
        horizontalArrangement = Arrangement.SpaceEvenly,
    ) {
        TABS.forEachIndexed { i, t ->
            val on = i == selected
            Column(
                Modifier
                    .weight(1f)
                    .clip(RoundedCornerShape(22.dp))
                    .background(if (on) K.Teal.copy(alpha = 0.14f) else Color.Transparent)
                    .clickable { onSelect(i) }
                    .padding(vertical = 8.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Icon(t.icon, t.label, tint = if (on) K.Teal else K.Muted, modifier = Modifier.size(24.dp))
                Spacer(Modifier.height(2.dp))
                Text(t.label, color = if (on) K.Teal else K.Muted, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
            }
        }
    }
}
