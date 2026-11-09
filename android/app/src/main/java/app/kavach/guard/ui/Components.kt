package app.kavach.guard.ui

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.GppBad
import androidx.compose.material.icons.rounded.GppGood
import androidx.compose.material.icons.rounded.GppMaybe
import androidx.compose.material.icons.rounded.Shield
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlin.math.cos
import kotlin.math.roundToInt
import kotlin.math.sin

/** Night background with two slowly drifting aurora glows. */
@Composable
fun AuroraBackground(content: @Composable BoxScope.() -> Unit) {
    val t = rememberInfiniteTransition(label = "aurora")
    val drift by t.animateFloat(0f, 1f, infiniteRepeatable(tween(14000, easing = LinearEasing), RepeatMode.Reverse), label = "drift")
    Box(Modifier.fillMaxSize().background(Brush.verticalGradient(listOf(K.Bg, K.Bg2, K.Bg)))) {
        Canvas(Modifier.fillMaxSize()) {
            val w = size.width
            val h = size.height
            if (w < 2f || h < 2f) return@Canvas   // Android rejects 0-radius gradients
            val c1 = Offset(w * (0.15f + 0.25f * drift), h * 0.12f)
            val c2 = Offset(w * (0.95f - 0.3f * drift), h * (0.55f + 0.1f * drift))
            drawCircle(Brush.radialGradient(listOf(K.Violet.copy(alpha = 0.28f), Color.Transparent), c1, w * 0.75f), w * 0.75f, c1)
            drawCircle(Brush.radialGradient(listOf(K.Teal.copy(alpha = 0.14f), Color.Transparent), c2, w * 0.7f), w * 0.7f, c2)
        }
        content()
    }
}

@Composable
fun GlassCard(
    modifier: Modifier = Modifier,
    accent: Color? = null,
    onClick: (() -> Unit)? = null,
    content: @Composable ColumnScope.() -> Unit,
) {
    val shape = RoundedCornerShape(24.dp)
    Column(
        modifier
            .fillMaxWidth()
            .clip(shape)
            .background(Brush.verticalGradient(listOf(K.GlassStrong, K.Glass)))
            .border(1.dp, accent?.copy(alpha = 0.45f) ?: K.GlassBorder, shape)
            .let { if (onClick != null) it.clickable(onClick = onClick) else it }
            .padding(18.dp),
        content = content,
    )
}

enum class OrbState { ACTIVE, ALERT, OFF }

/** The hero: a radar-style shield with pulse rings, a sweeping scan beam and a breathing core. */
@Composable
fun ShieldOrb(state: OrbState, modifier: Modifier = Modifier, size: Dp = 250.dp) {
    val color by animateColorAsState(
        when (state) { OrbState.ACTIVE -> K.Teal; OrbState.ALERT -> K.Danger; OrbState.OFF -> K.Muted },
        tween(700), label = "orbColor",
    )
    val t = rememberInfiniteTransition(label = "orb")
    val sweep by t.animateFloat(0f, 360f, infiniteRepeatable(tween(3200, easing = LinearEasing)), label = "sweep")
    val pulse by t.animateFloat(0f, 1f, infiniteRepeatable(tween(2600, easing = LinearEasing)), label = "pulse")
    val breathe by t.animateFloat(0.93f, 1f, infiniteRepeatable(tween(1500, easing = FastOutSlowInEasing), RepeatMode.Reverse), label = "breathe")
    val live = state != OrbState.OFF

    Box(modifier.size(size), contentAlignment = Alignment.Center) {
        Canvas(Modifier.fillMaxSize()) {
            val c = center
            val maxR = this.size.minDimension / 2f
            if (maxR < 2f) return@Canvas
            if (live) for (i in 0..2) {
                val p = (pulse + i / 3f) % 1f
                drawCircle(color.copy(alpha = (1f - p) * 0.35f), maxR * (0.45f + 0.55f * p), c, style = Stroke(2.dp.toPx()))
            }
            drawCircle(Brush.radialGradient(listOf(color.copy(alpha = 0.30f), Color.Transparent), c, maxR * 0.8f), maxR * 0.8f, c)
            val ringR = maxR * 0.62f
            for (i in 0 until 72) {
                val a = Math.toRadians(i * 5.0)
                val len = if (i % 6 == 0) 10.dp.toPx() else 4.dp.toPx()
                val start = Offset(c.x + ringR * cos(a).toFloat(), c.y + ringR * sin(a).toFloat())
                val end = Offset(c.x + (ringR + len) * cos(a).toFloat(), c.y + (ringR + len) * sin(a).toFloat())
                drawLine(color.copy(alpha = if (i % 6 == 0) 0.55f else 0.22f), start, end, 1.5.dp.toPx())
            }
            if (live) rotate(sweep, c) {
                drawCircle(
                    Brush.sweepGradient(0f to Color.Transparent, 0.72f to Color.Transparent, 1f to color.copy(alpha = 0.55f), center = c),
                    ringR, c,
                )
            }
            val coreR = maxR * 0.40f * breathe
            drawCircle(Brush.radialGradient(listOf(Color(0xFF18234F), K.Bg2), c, coreR), coreR, c)
            drawCircle(color.copy(alpha = 0.85f), coreR, c, style = Stroke(2.dp.toPx()))
        }
        Icon(
            imageVector = when (state) {
                OrbState.ACTIVE -> Icons.Rounded.GppGood
                OrbState.ALERT -> Icons.Rounded.GppBad
                OrbState.OFF -> Icons.Rounded.GppMaybe
            },
            contentDescription = null,
            tint = color,
            modifier = Modifier.size(size * 0.28f).graphicsLayer { scaleX = breathe; scaleY = breathe },
        )
    }
}

/** 270° animated gauge for the risk score. */
@Composable
fun RiskGauge(score: Int, color: Color, modifier: Modifier = Modifier, size: Dp = 190.dp) {
    val anim by animateFloatAsState(score.coerceIn(0, 100) / 100f, tween(1300, easing = FastOutSlowInEasing), label = "gauge")
    Box(modifier.size(size), contentAlignment = Alignment.Center) {
        Canvas(Modifier.fillMaxSize()) {
            val stroke = 16.dp.toPx()
            val inset = stroke / 2f
            val arcSize = Size(this.size.width - stroke, this.size.height - stroke)
            drawArc(K.GlassStrong, 135f, 270f, false, Offset(inset, inset), arcSize, style = Stroke(stroke, cap = StrokeCap.Round))
            drawArc(
                Brush.sweepGradient(listOf(color.copy(alpha = 0.35f), color, color.copy(alpha = 0.35f))),
                135f, 270f * anim, false, Offset(inset, inset), arcSize, style = Stroke(stroke, cap = StrokeCap.Round),
            )
        }
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text("${(anim * 100).roundToInt()}", fontSize = 52.sp, fontWeight = FontWeight.Black, color = color)
            Text("RISK SCORE", style = MaterialTheme.typography.labelSmall)
        }
    }
}

@Composable
fun VerdictChip(verdict: String, big: Boolean = false) {
    val color = verdictColor(verdict)
    val icon = when (verdict) {
        "SCAM", "LIKELY_SCAM" -> Icons.Rounded.GppBad
        "SUSPICIOUS" -> Icons.Rounded.GppMaybe
        "LIKELY_SAFE", "CLEAN" -> Icons.Rounded.GppGood
        else -> Icons.Rounded.Shield
    }
    Row(
        Modifier
            .clip(RoundedCornerShape(50))
            .background(color.copy(alpha = 0.16f))
            .border(1.dp, color.copy(alpha = 0.45f), RoundedCornerShape(50))
            .padding(horizontal = if (big) 14.dp else 10.dp, vertical = if (big) 7.dp else 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(icon, null, tint = color, modifier = Modifier.size(if (big) 18.dp else 14.dp))
        Spacer(Modifier.width(6.dp))
        Text(verdictLabel(verdict), color = color, fontWeight = FontWeight.Bold, fontSize = if (big) 15.sp else 12.sp)
    }
}

@Composable
fun GradientButton(
    text: String,
    icon: ImageVector?,
    modifier: Modifier = Modifier,
    loading: Boolean = false,
    colors: List<Color> = listOf(K.Violet, K.Teal),
    onClick: () -> Unit,
) {
    Box(
        modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(18.dp))
            .background(Brush.horizontalGradient(colors))
            .clickable(enabled = !loading, onClick = onClick)
            .padding(vertical = 16.dp),
        contentAlignment = Alignment.Center,
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.Center) {
            if (loading) {
                CircularProgressIndicator(color = K.Bg, strokeWidth = 2.5.dp, modifier = Modifier.size(20.dp))
            } else if (icon != null) {
                Icon(icon, null, tint = K.Bg, modifier = Modifier.size(20.dp))
            }
            Spacer(Modifier.width(10.dp))
            Text(text, color = K.Bg, fontWeight = FontWeight.Bold, fontSize = 16.sp)
        }
    }
}

@Composable
fun SectionTitle(text: String, modifier: Modifier = Modifier) {
    Text(text.uppercase(), style = MaterialTheme.typography.labelSmall, modifier = modifier.padding(top = 6.dp, bottom = 2.dp))
}
