package app.kavach.guard.ui

import android.text.format.DateUtils
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import app.kavach.guard.core.Alert
import app.kavach.guard.core.Store

enum class HistoryFilter(val label: String) {
    ALL("All"), GENUINE("Genuine"), SUSPICIOUS("Suspicious"), FRAUD("Fraudulent");

    fun matches(a: Alert): Boolean = when (this) {
        ALL -> true
        GENUINE -> a.isGenuine
        SUSPICIOUS -> a.verdict == "SUSPICIOUS"
        FRAUD -> a.isFraud
    }

    val color: Color
        get() = when (this) {
            ALL -> K.Info
            GENUINE -> K.Teal
            SUSPICIOUS -> K.Warn
            FRAUD -> K.Danger
        }
}

@Composable
fun HistoryScreen(filter: HistoryFilter, onFilter: (HistoryFilter) -> Unit, onOpen: (Alert) -> Unit) {
    val records by Store.alerts.collectAsStateWithLifecycle()
    val shown = records.filter { filter.matches(it) }

    LazyColumn(
        contentPadding = PaddingValues(start = 20.dp, end = 20.dp, top = 12.dp, bottom = 28.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Column {
                Text("History", style = MaterialTheme.typography.displaySmall)
                Text(
                    "Every message Kavach has scanned on this phone (latest ${records.size}). Tap one to see its full analysis.",
                    color = K.Muted, fontSize = 14.sp,
                )
            }
        }
        item {
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                HistoryFilter.entries.forEach { f ->
                    FilterPill(f, records.count { f.matches(it) }, selected = f == filter) { onFilter(f) }
                }
            }
        }
        if (shown.isEmpty()) {
            item {
                GlassCard {
                    Text(
                        if (records.isEmpty()) "No messages scanned yet" else "No ${filter.label.lowercase()} messages",
                        style = MaterialTheme.typography.titleMedium,
                    )
                    Text(
                        if (records.isEmpty()) "Once notification access is on, every incoming SMS, WhatsApp or email is checked and listed here."
                        else "Nothing in your history matches this filter.",
                        color = K.Muted, fontSize = 14.sp,
                    )
                }
            }
        }
        items(shown, key = { it.id }) { a -> GlassCard(onClick = { onOpen(a) }) { RecordRow(a) } }
    }
}

@Composable
private fun FilterPill(f: HistoryFilter, count: Int, selected: Boolean, onClick: () -> Unit) {
    val color = f.color
    Row(
        Modifier.clip(RoundedCornerShape(50))
            .background(if (selected) color.copy(alpha = 0.22f) else K.Glass)
            .border(1.dp, if (selected) color else K.GlassBorder, RoundedCornerShape(50))
            .clickable(onClick = onClick)
            .padding(horizontal = 14.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(f.label, color = if (selected) color else K.Text, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
        Spacer(Modifier.width(6.dp))
        Text("$count", color = K.Muted, fontSize = 12.sp, fontWeight = FontWeight.Bold)
    }
}

/** One scanned message: status dot, app/sender, verdict and risk, time, and the start of the message. */
@Composable
fun RecordRow(a: Alert, modifier: Modifier = Modifier) {
    val color = verdictColor(a.verdict)
    val status = when (a.status) {
        "checking" -> "Checking with AI…"
        "clean" -> "No red flags · checked on phone"
        "offline" -> verdictLabel(a.verdict) + " · on-device (AI offline)"
        "error" -> "Not checked · AI unreachable"
        else -> verdictLabel(a.verdict) + " · risk ${a.risk}"
    }
    Row(modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        if (a.status == "checking") {
            CircularProgressIndicator(color = K.Violet, strokeWidth = 2.dp, modifier = Modifier.size(12.dp))
        } else {
            Box(Modifier.size(12.dp).clip(CircleShape).background(color))
        }
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    a.appName + (if (a.sender.isNotBlank()) " · ${a.sender}" else ""),
                    color = K.Text, fontWeight = FontWeight.SemiBold, fontSize = 14.sp,
                    maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = false),
                )
                Spacer(Modifier.width(8.dp))
                Text(
                    DateUtils.getRelativeTimeSpanString(a.time, System.currentTimeMillis(), DateUtils.MINUTE_IN_MILLIS).toString(),
                    color = K.Muted, fontSize = 11.sp, maxLines = 1,
                )
            }
            Text(status, color = if (a.status == "checking") K.Violet else color, fontSize = 12.sp, fontWeight = FontWeight.Medium, maxLines = 1)
            Text(a.original.replace('\n', ' '), color = K.Muted, fontSize = 13.sp, maxLines = 2, overflow = TextOverflow.Ellipsis)
        }
    }
}
