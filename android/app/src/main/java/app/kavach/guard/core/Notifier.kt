package app.kavach.guard.core

import android.Manifest
import android.annotation.SuppressLint
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.media.AudioAttributes
import android.media.MediaPlayer
import android.net.Uri
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import app.kavach.guard.MainActivity
import app.kavach.guard.R

object Notifier {
    const val CHANNEL_ALERTS = "kavach_alerts"
    const val EXTRA_ALERT_ID = "alert_id"

    fun createChannels(ctx: Context) {
        val nm = ctx.getSystemService(NotificationManager::class.java)
        val ch = NotificationChannel(CHANNEL_ALERTS, "Scam alerts", NotificationManager.IMPORTANCE_HIGH).apply {
            description = "Warnings when a message looks like a scam"
            enableVibration(true)
            vibrationPattern = longArrayOf(0, 250, 120, 250)
        }
        nm.createNotificationChannel(ch)
    }

    fun canPost(ctx: Context): Boolean =
        Build.VERSION.SDK_INT < 33 ||
            ContextCompat.checkSelfPermission(ctx, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED

    fun verdictTitle(v: String): String = when (v) {
        "SCAM" -> "Scam detected"
        "LIKELY_SCAM" -> "Likely scam"
        "SUSPICIOUS" -> "Suspicious message"
        "LIKELY_SAFE" -> "Looks safe"
        else -> "Needs a closer look"
    }

    @SuppressLint("MissingPermission")
    fun showAlert(ctx: Context, a: Alert) {
        if (!canPost(ctx)) return
        val open = PendingIntent.getActivity(
            ctx, a.id.hashCode(),
            Intent(ctx, MainActivity::class.java).putExtra(EXTRA_ALERT_ID, a.id)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val dial = PendingIntent.getActivity(
            ctx, 1930, Intent(Intent.ACTION_DIAL, Uri.parse("tel:1930")), PendingIntent.FLAG_IMMUTABLE,
        )
        val type = a.scamTypeLocal.ifBlank { a.scamType }.takeIf { it.isNotBlank() && it != "None" }
        val title = "⚠️ ${verdictTitle(a.verdict)}" + (type?.let { " · $it" } ?: "")
        val body = a.summary.ifBlank { a.localLabels.joinToString(" · ") }
        val n = NotificationCompat.Builder(ctx, CHANNEL_ALERTS)
            .setSmallIcon(R.drawable.ic_stat_shield)
            .setColor(0xFFFF4D6D.toInt())
            .setContentTitle(title)
            .setContentText(body)
            .setSubText("${a.appName} · risk ${a.risk}")
            .setStyle(NotificationCompat.BigTextStyle().bigText("$body\n\n“${a.original.take(160)}”"))
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_MESSAGE)
            .setAutoCancel(true)
            .setContentIntent(open)
            .addAction(R.drawable.ic_stat_call, "Call 1930", dial)
            .build()
        NotificationManagerCompat.from(ctx).notify(a.id.hashCode(), n)
    }

    private var player: MediaPlayer? = null

    /** Play a spoken warning (WAV saved from the server's Gnani TTS reply). */
    fun speak(path: String?, onDone: (() -> Unit)? = null) {
        if (path.isNullOrBlank()) { onDone?.invoke(); return }
        runCatching {
            player?.release()
            player = MediaPlayer().apply {
                setAudioAttributes(
                    AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_ASSISTANT)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                        .build(),
                )
                setDataSource(path)
                setOnCompletionListener { it.release(); if (player === it) player = null; onDone?.invoke() }
                prepare()
                start()
            }
        }.onFailure { onDone?.invoke() }
    }

    fun stopSpeaking() {
        runCatching { player?.stop(); player?.release() }
        player = null
    }
}
