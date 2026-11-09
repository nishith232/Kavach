package app.kavach.guard.service

import android.app.Notification
import android.content.ComponentName
import android.content.pm.PackageManager
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import androidx.core.app.NotificationCompat
import app.kavach.guard.core.Pipeline
import app.kavach.guard.core.Store
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch

/**
 * Reads every incoming notification (SMS, WhatsApp, Telegram, email...) the moment it arrives,
 * before the user opens it. Text is scanned on-device; only suspicious text goes to the AI.
 */
class ShieldListener : NotificationListenerService() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    override fun onListenerConnected() {
        Store.setListenerConnected(true)
    }

    override fun onListenerDisconnected() {
        Store.setListenerConnected(false)
        requestRebind(ComponentName(this, ShieldListener::class.java))
    }

    override fun onNotificationPosted(sbn: StatusBarNotification) {
        val pkg = sbn.packageName ?: return
        if (pkg == packageName || pkg in IGNORED) return
        if (!Store.settings.value.scanAllApps && !isMessagingApp(pkg)) return
        val (sender, body) = extractText(sbn) ?: return
        if (Store.isDuplicate("$sender\n$body")) return
        Store.countScanned()
        val app = appLabel(pkg)
        scope.launch {
            runCatching { Pipeline.process(applicationContext, body, pkg, app, Pipeline.Mode.AUTO, sender) }
        }
    }

    override fun onDestroy() {
        scope.cancel()
        super.onDestroy()
    }

    /** (sender, message body) of a notification, or null if it carries no message worth checking. */
    private fun extractText(sbn: StatusBarNotification): Pair<String, String>? {
        val n = sbn.notification ?: return null
        if (n.flags and Notification.FLAG_GROUP_SUMMARY != 0) return null   // "5 new messages" summaries
        if (sbn.isOngoing) return null                                      // music, downloads, calls in progress
        val ex = n.extras ?: return null

        val parts = mutableListOf<String>()
        runCatching {
            NotificationCompat.MessagingStyle.extractMessagingStyleFromNotification(n)
                ?.messages?.lastOrNull()?.text?.toString()?.let(parts::add)
        }
        ex.getCharSequence(Notification.EXTRA_BIG_TEXT)?.toString()?.let(parts::add)
        ex.getCharSequence(Notification.EXTRA_TEXT)?.toString()?.let(parts::add)
        ex.getCharSequenceArray(Notification.EXTRA_TEXT_LINES)?.lastOrNull()?.toString()?.let(parts::add)

        val body = parts.map { it.trim() }.filter { it.isNotEmpty() }.distinct().maxByOrNull { it.length } ?: return null
        if (body.length < 12) return null
        val sender = ex.getCharSequence(Notification.EXTRA_TITLE)?.toString()?.trim().orEmpty()
        return sender to body
    }

    private fun appLabel(pkg: String): String = KNOWN[pkg] ?: runCatching {
        packageManager.getApplicationLabel(packageManager.getApplicationInfo(pkg, PackageManager.GET_META_DATA)).toString()
    }.getOrElse { pkg.substringAfterLast('.').replaceFirstChar { it.uppercase() } }

    companion object {
        private val IGNORED = setOf("android", "com.android.systemui", "com.android.providers.downloads")

        private val KNOWN = mapOf(
            "com.whatsapp" to "WhatsApp",
            "com.whatsapp.w4b" to "WhatsApp Business",
            "org.telegram.messenger" to "Telegram",
            "com.google.android.apps.messaging" to "Messages",
            "com.android.mms" to "Messages",
            "com.truecaller" to "Truecaller",
            "com.google.android.gm" to "Gmail",
            "com.instagram.android" to "Instagram",
            "com.facebook.orca" to "Messenger",
        )

        fun isMessagingApp(pkg: String): Boolean =
            pkg in KNOWN || listOf("mms", "messag", "sms", "chat").any { it in pkg.lowercase() }
    }
}
