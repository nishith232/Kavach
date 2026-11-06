package app.kavach.guard

import android.app.Application
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
        Store.init(this)
        RuleEngine.init(this)
        Notifier.createChannels(this)
        refreshRules()
    }

    /** Pull the latest keyword rules from the server; keep the bundled ones if it's unreachable. */
    fun refreshRules() = scope.launch {
        val json = Api.rules(Store.settings.value.serverUrl) ?: return@launch
        if (runCatching { RuleEngine.load(json) }.isSuccess) Store.cacheRules(json)
    }
}
