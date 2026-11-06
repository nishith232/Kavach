package app.kavach.guard

import android.app.Application
import android.util.Log
import java.io.File
import app.kavach.guard.core.Api
import app.kavach.guard.core.Notifier
import app.kavach.guard.core.RuleEngine
import app.kavach.guard.core.Store
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

class KavachApp : Application() {
    val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    override fun onCreate() {
        super.onCreate()
        installCrashReporter()
        Store.init(this)
        runCatching { RuleEngine.init(this) }.onFailure { Log.e("Kavach", "rules init failed", it) }
        runCatching { Notifier.createChannels(this) }
        refreshRules()
    }

    /** Save any crash to a file so it can be viewed and copied from Settings on the next launch. */
    private fun installCrashReporter() {
        val previous = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { thread, error ->
            runCatching {
                crashFile(this).writeText(
                    "Kavach Guard ${BuildConfig.VERSION_NAME} · Android ${android.os.Build.VERSION.RELEASE} · " +
                        "${android.os.Build.MANUFACTURER} ${android.os.Build.MODEL}\n\n" + Log.getStackTraceString(error),
                )
            }
            previous?.uncaughtException(thread, error)
        }
    }

    companion object {
        fun crashFile(app: Application) = File(app.filesDir, "last_crash.txt")
    }

    /** Pull the latest keyword rules from the server; keep the bundled ones if it's unreachable. */
    fun refreshRules() = scope.launch {
        val json = Api.rules(Store.settings.value.serverUrl) ?: return@launch
        if (runCatching { RuleEngine.load(json) }.isSuccess) Store.cacheRules(json)
    }
}
