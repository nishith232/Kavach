package app.kavach.guard.ui

import android.annotation.SuppressLint
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.PowerManager
import android.provider.Settings
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.core.app.NotificationManagerCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect
import app.kavach.guard.core.Notifier

data class PermState(val listener: Boolean, val notify: Boolean, val battery: Boolean) {
    val ready: Boolean get() = listener && notify
}

fun readPerms(ctx: Context): PermState = PermState(
    listener = NotificationManagerCompat.getEnabledListenerPackages(ctx).contains(ctx.packageName),
    notify = Notifier.canPost(ctx),
    battery = ctx.getSystemService(PowerManager::class.java)?.isIgnoringBatteryOptimizations(ctx.packageName) == true,
)

/** Permission state that refreshes every time the user comes back from Settings. */
@Composable
fun rememberPerms(): PermState {
    val ctx = LocalContext.current
    var state by remember { mutableStateOf(readPerms(ctx)) }
    LifecycleEventEffect(Lifecycle.Event.ON_RESUME) { state = readPerms(ctx) }
    return state
}

fun openListenerSettings(ctx: Context) = runCatching {
    ctx.startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
}

/** App info page: on Android 13+ sideloaded apps need "⋮ → Allow restricted settings" before notification access. */
fun openAppInfo(ctx: Context) = runCatching {
    ctx.startActivity(
        Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.fromParts("package", ctx.packageName, null))
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
    )
}

@SuppressLint("BatteryLife")
fun requestBatteryExemption(ctx: Context) = runCatching {
    ctx.startActivity(
        Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:${ctx.packageName}"))
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
    )
}

fun dial1930(ctx: Context) = runCatching {
    ctx.startActivity(Intent(Intent.ACTION_DIAL, Uri.parse("tel:1930")).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
}
