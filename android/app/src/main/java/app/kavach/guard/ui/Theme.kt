package app.kavach.guard.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

/** Kavach palette: deep night background, electric teal (safe), violet (brand), coral red (danger). */
object K {
    val Bg = Color(0xFF070B16)
    val Bg2 = Color(0xFF0B1230)
    val Teal = Color(0xFF3EF2C8)
    val Violet = Color(0xFF7C5CFF)
    val Danger = Color(0xFFFF4D6D)
    val Warn = Color(0xFFFFB547)
    val Info = Color(0xFF8AA4FF)
    val Text = Color(0xFFEAF0FF)
    val Muted = Color(0xFF8C98B8)
    val Glass = Color(0x14FFFFFF)
    val GlassStrong = Color(0x22FFFFFF)
    val GlassBorder = Color(0x26FFFFFF)
}

fun verdictColor(verdict: String): Color = when (verdict) {
    "SCAM", "LIKELY_SCAM" -> K.Danger
    "SUSPICIOUS" -> K.Warn
    "LIKELY_SAFE", "CLEAN" -> K.Teal
    "UNCHECKED" -> K.Muted
    else -> K.Info
}

fun verdictLabel(verdict: String): String = when (verdict) {
    "SCAM" -> "Scam"
    "LIKELY_SCAM" -> "Likely scam"
    "SUSPICIOUS" -> "Suspicious"
    "LIKELY_SAFE" -> "Looks safe"
    "CLEAN" -> "No red flags"
    "CHECKING" -> "Checking…"
    "UNCHECKED" -> "Not checked"
    else -> "Need more info"
}

private val KavachTypography = Typography(
    displaySmall = TextStyle(fontSize = 34.sp, fontWeight = FontWeight.Black, letterSpacing = (-0.5).sp, color = K.Text),
    headlineSmall = TextStyle(fontSize = 24.sp, fontWeight = FontWeight.Bold, letterSpacing = (-0.2).sp, color = K.Text),
    titleMedium = TextStyle(fontSize = 17.sp, fontWeight = FontWeight.SemiBold, color = K.Text),
    bodyLarge = TextStyle(fontSize = 16.sp, lineHeight = 23.sp, color = K.Text),
    bodyMedium = TextStyle(fontSize = 14.sp, lineHeight = 20.sp, color = K.Text),
    labelSmall = TextStyle(fontSize = 11.sp, fontWeight = FontWeight.SemiBold, letterSpacing = 1.4.sp, color = K.Muted),
)

@Composable
fun KavachTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = darkColorScheme(
            primary = K.Teal,
            onPrimary = K.Bg,
            secondary = K.Violet,
            background = K.Bg,
            surface = K.Bg2,
            onBackground = K.Text,
            onSurface = K.Text,
            error = K.Danger,
        ),
        typography = KavachTypography,
        content = content,
    )
}
